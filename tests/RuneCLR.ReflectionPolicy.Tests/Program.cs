using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using ReflectionPolicy.CompiledLibrary;
using RuneCLR.Packages;
using RuneCLR.Runtime;

return ReflectionPolicyTests.Run(args);

internal static partial class ReflectionPolicyTests
{
    private static int passed;
    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;

    internal static int Run(string[] args)
    {
        try
        {
            if (args.Length == 0)
            {
                AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", false);
                Expect<ArgumentNullException>(() => PrototypeReflectionPolicy.Enter(null!));
                Expect<PlatformNotSupportedException>(() => PrototypeReflectionPolicy.Enter(GameplayCapabilityPolicy.CreateApiPolicy([], Contract)));
                Pass("stock/disabled support refuses before author loading");
                Console.WriteLine("REFLECTION_POLICY_STOCK_TESTS PASS");
                return 0;
            }
            if (args.Length != 1 || args[0] != "--require-private-runtime") return 2;
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
            using (PrototypeReflectionPolicy.Enter(GameplayCapabilityPolicy.CreateApiPolicy([], Contract))) { }
            var retired = Exercise();
            for (int i = 0; i < 15 && retired.Context.IsAlive; i++)
            {
                GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            }
            Assert(!retired.Context.IsAlive, "A retired scope retained author metadata.");
            GC.KeepAlive(retired.Flow);
            Pass("collectible author retires while its captured execution context remains alive");
            ExerciseSessions();
            ExerciseHostAllowedMethods();
            ExerciseHostPolicy();
            ExerciseGenericHostContract();
            Console.WriteLine($"REFLECTION_POLICY_PRIVATE_TESTS PASS cases={passed}");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (WeakReference Context, ExecutionContext Flow) Exercise()
    {
        var create = typeof(AssemblyLoadContext).GetMethod("RuneCLR_CreateInterpreterRequired", BindingFlags.Static | BindingFlags.NonPublic)!
            .CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>();
        var context = create("reflection-required-author", (_, name) => name.Name == typeof(ReflectionLibrary).Assembly.GetName().Name
            ? typeof(ReflectionLibrary).Assembly : null);
        ExecutionContext? flow = null;
        try
        {
            var acknowledge = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicy", BindingFlags.Instance | BindingFlags.NonPublic)!
                .CreateDelegate<Func<AssemblyLoadContext, int>>();
            Assert(context.IsCollectible && acknowledge(context) == 1, "Interpreter-required context was not acknowledged.");
            var assembly = context.LoadFromAssemblyPath(Path.Combine(AppContext.BaseDirectory, "author", "ReflectionPolicy.Author.dll"));
            var type = assembly.GetType("ReflectionPolicy.Author.Entry")!;
            var counters = assembly.GetType("ReflectionPolicy.Author.Counters")!;
            T Callback<T>(string name) where T : Delegate => type.GetMethod(name)!.CreateDelegate<T>();
            int Count(string name) => (int)counters.GetField(name)!.GetValue(null)!;
            // The host's waits and exception resource lookup also use ordinary reflection.
            // Grant their narrow test permissions explicitly, without a framework bypass.
            IApiAccessPolicy policy = new HostInfrastructurePolicy(GameplayCapabilityPolicy.CreateApiPolicy([assembly.FullName!], Contract));
            var own = Callback<Func<int>>("Own");
            var library = Callback<Func<int>>("ThroughLibrary");
            var libraryTouch = Callback<Action>("LibraryTouch");
            var touch = Callback<Action>("Touch");
            var caught = Callback<Func<int>>("CatchDenied");
            var generic = Callback<Func<int>>("Generic");
            var badGeneric = Callback<Action>("ForbiddenGeneric");
            var baseVirtual = Callback<Func<int>>("BaseVirtual");
            var concreteVirtual = Callback<Func<int>>("ConcreteVirtual");
            var throwing = Callback<Action>("Throwing");
            var framework = Callback<Func<bool>>("Framework");
            var fileWrite = Callback<Action<string>>("FileWrite");
            var deny = new DenyMember(policy, "Touch");

            using (PrototypeReflectionPolicy.Enter(deny))
            {
                Assert(own() == 41 && framework(), "Approved author/framework invocation failed.");
                Pass("ordinary MethodInfo.Invoke permits author ABC and approved framework targets");
                Assert(library() == 41, "Compiled-library reflection lost the current policy.");
                Expect<InvalidOperationException>(libraryTouch);
                Assert(Count("StaticRuns") == 0 && Count("BodyRuns") == 0, "A compiled library bypassed the reflection policy.");
                Assert(AssemblyLoadContext.GetLoadContext(typeof(ReflectionLibrary).Assembly) == AssemblyLoadContext.Default,
                    "The library was not running outside the interpreted author context.");
                Pass("compiled library uses ordinary reflection under the author scope");
                var output = Path.Combine(Path.GetTempPath(), "runeclr-reflection-" + Guid.NewGuid().ToString("N") + ".txt");
                Expect<InvalidOperationException>(() => fileWrite(output));
                Assert(!File.Exists(output), "Denied file operation wrote output.");
                Pass("file access denied before creating output");
                Expect<InvalidOperationException>(touch);
                Assert(Count("StaticRuns") == 0 && Count("BodyRuns") == 0, "A denied target initialized or executed.");
                Assert(caught() == 2 && Count("BodyRuns") == 0, "Catching denial removed enforcement.");
                Pass("denial precedes target type initialization and remains enforced after catch");
                Assert(generic() == 41 && Count("GenericRuns") == 1, "Approved generic target failed.");
                Expect<InvalidOperationException>(badGeneric);
                Assert(Count("GenericRuns") == 1, "A forbidden generic target executed.");
                Pass("constructed generic arguments checked before invocation");
                Assert(baseVirtual() == 2 && concreteVirtual() == 2 && Count("VirtualRuns") == 2,
                    "Checked virtual dispatch failed.");
                Pass("base virtual and concrete override targets are checked before execution");
                var exception = Expect<TargetInvocationException>(throwing);
                Assert(exception.InnerException is InvalidOperationException { Message: "author-failure" }, "Target exception semantics changed.");
                Pass("allowed target retains ordinary reflection exception wrapping");
                using (PrototypeReflectionPolicy.Enter(policy)) Expect<InvalidOperationException>(touch);
                Pass("nested scope cannot widen outer permissions");
                Task.Run(() =>
                {
                    Assert(library() == 41, "ExecutionContext propagation lost policy.");
                    Expect<InvalidOperationException>(libraryTouch);
                }).GetAwaiter().GetResult();
                Pass("host-managed ExecutionContext flow retains the reflection policy");
            }

            ExerciseAccess(assembly, policy);
            ExerciseDispatch(assembly, policy);
            ExerciseFactories(assembly, policy);
            ExerciseAdditionalEntries(assembly, policy);
            using (PrototypeReflectionPolicy.Enter(new CapturingPolicy(policy, assembly))) flow = ExecutionContext.Capture()!;
            Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => own(), null));
            ExerciseRetiredAccess(assembly, flow);
            ExerciseRetiredFactories(assembly, flow);
            Assert(own() == 41, "Trusted host behavior outside a scope changed.");
            Pass("captured retired scope refuses instead of becoming unrestricted");
            var outer = PrototypeReflectionPolicy.Enter(policy);
            var inner = PrototypeReflectionPolicy.Enter(policy);
            Expect<InvalidOperationException>(outer.Dispose);
            inner.Dispose(); outer.Dispose(); outer.Dispose();
            Pass("scope disposal requires nesting order and is idempotent after retirement");
        }
        finally { context.Unload(); }
        return (new WeakReference(context), flow!);
    }

    private static T Expect<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T error) { return error; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }
    private static void Assert(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
    private static void Pass(string name) { passed++; Console.WriteLine("PASS " + name); }

    private sealed class DenyMember(IApiAccessPolicy inner, string name) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) => target.MemberName == name
            ? ApiDecision.Deny("Target denied by this test policy.") : inner.Evaluate(target, operation);
    }
    private sealed class CapturingPolicy(IApiAccessPolicy inner, Assembly author) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            GC.KeepAlive(author);
            return inner.Evaluate(target, operation);
        }
    }
    private sealed class HostInfrastructurePolicy(IApiAccessPolicy inner) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (target.AssemblyIdentity == typeof(object).Assembly.FullName)
            {
                bool handle = target.TypeName == "Microsoft.Win32.SafeHandles.SafeWaitHandle";
                bool resources = target.TypeName == "System.Resources.NeutralResourcesLanguageAttribute";
                bool fallback = target.TypeName == "System.Resources.UltimateResourceFallbackLocation";
                if ((handle || resources || fallback) && target.Kind == ApiTargetKind.Type && operation == ApiOperation.Reference)
                    return ApiDecision.Allow;
                if ((handle || resources) && target.Kind == ApiTargetKind.Method && target.MemberName == ".ctor" && operation == ApiOperation.Construct &&
                    target.Signature is { ParameterTypes: var args } && (handle ? args.Length == 0 :
                        args.SequenceEqual(new[] { "System.String" }) ||
                        args.SequenceEqual(new[] { "System.String", "System.Resources.UltimateResourceFallbackLocation" })))
                    return ApiDecision.Allow;
            }
            return inner.Evaluate(target, operation);
        }
    }
}
