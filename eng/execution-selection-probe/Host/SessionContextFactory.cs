using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using SelectionProbe.Contract;

static class SessionContextFactory
{
    private static readonly string? Mode = Environment.GetEnvironmentVariable("RUNECLR_PROBE_FACTORY");
    private static MethodInfo? query;
    private static MethodInfo? create;
    public static void Initialize(string evidence)
    {
        if (Mode is null) return;
        if (Mode is not ("required" or "ordinary")) throw new ArgumentException("Unknown probe factory mode.");
        var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
        var methods = typeof(AssemblyLoadContext).GetMethods(flags).Where(m => m.Name.StartsWith("RuneCLR_")).ToArray();
        create = typeof(AssemblyLoadContext).GetMethod("RuneCLR_CreateInterpreterRequired", BindingFlags.NonPublic | BindingFlags.Static,
            binder: null, types: [typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly>)], modifiers: null);
        query = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicy", BindingFlags.NonPublic | BindingFlags.Instance,
            binder: null, types: Type.EmptyTypes, modifiers: null);
        var version = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicyVersion", BindingFlags.NonPublic | BindingFlags.Static,
            binder: null, types: Type.EmptyTypes, modifiers: null);
        if (create is null || query is null || version is null) throw new NotSupportedException("Matching private CoreLib session policy API unavailable.");
        if (create.ReturnType != typeof(AssemblyLoadContext) || query.ReturnType != typeof(int) || version.ReturnType != typeof(int))
            throw new NotSupportedException("Session policy API return types do not match the fixture contract.");
        int observedVersion = (int)version.Invoke(null, null)!;
        if (observedVersion != 1 || (int)query.Invoke(AssemblyLoadContext.Default, null)! != 0)
            throw new InvalidOperationException("Policy version/default context acknowledgement mismatch.");
        var names = methods.Select(m => m.Name).Order().ToArray();
        string[] expectedNames = ["RuneCLR_CreateInterpreterRequired", "RuneCLR_GetExecutionPolicy",
            "RuneCLR_GetExecutionPolicyNative", "RuneCLR_GetExecutionPolicyVersion", "RuneCLR_GetExecutionPolicyVersionNative"];
        var meterSignatures = new (string Name, bool Static, Type Result, Type[] Parameters)[]
        {
            ("RuneCLR_CreateInstructionMetered", true, typeof(AssemblyLoadContext),
                [typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly>), typeof(long)]),
            ("RuneCLR_GetInstructionMeterVersion", true, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetInstructionMeterVersionNative", true, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetInstructionMeterRemaining", false, typeof(long), Type.EmptyTypes),
            ("RuneCLR_GetInstructionMeterRemainingNative", true, typeof(long), [typeof(IntPtr)]),
            ("RuneCLR_GetInstructionMeterExecuted", false, typeof(long), Type.EmptyTypes),
            ("RuneCLR_GetInstructionMeterExecutedNative", true, typeof(long), [typeof(IntPtr)]),
            ("RuneCLR_GetInstructionMeterExhausted", false, typeof(bool), Type.EmptyTypes)
        };
        bool hasMeter = methods.Any(m => m.Name.Contains("InstructionMeter"));
        var terminalSignatures = new (string Name, bool Static, Type Result, Type[] Parameters)[]
        {
            ("RuneCLR_CreateTerminalPrototype", true, typeof(AssemblyLoadContext),
                [typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly>), typeof(long), typeof(long)]),
            ("RuneCLR_GetTerminalPrototypeVersion", true, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeVersionNative", true, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeIsTerminated", false, typeof(bool), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeReason", false, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeReasonNative", true, typeof(int), [typeof(IntPtr)]),
            ("RuneCLR_GetTerminalPrototypePhase", false, typeof(int), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypePhaseNative", true, typeof(int), [typeof(IntPtr)]),
            ("RuneCLR_GetTerminalPrototypeCleanupRemaining", false, typeof(long), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeCleanupRemainingNative", true, typeof(long), [typeof(IntPtr)]),
            ("RuneCLR_GetTerminalPrototypeCleanupExecuted", false, typeof(long), Type.EmptyTypes),
            ("RuneCLR_GetTerminalPrototypeCleanupExecutedNative", true, typeof(long), [typeof(IntPtr)])
        };
        bool hasTerminal = methods.Any(m => m.Name.Contains("TerminalPrototype"));
        var allowedNames = expectedNames.Concat(hasMeter ? meterSignatures.Select(s => s.Name) : [])
            .Concat(hasTerminal ? terminalSignatures.Select(s => s.Name) : []).Order().ToArray();
        if (!names.SequenceEqual(allowedNames)) throw new InvalidOperationException("Unexpected policy API, including a potential policy setter.");
        if (hasMeter)
        {
            foreach (var signature in meterSignatures)
            {
                var method = methods.Single(m => m.Name == signature.Name);
                if (!method.IsPrivate || method.IsStatic != signature.Static || method.ReturnType != signature.Result ||
                    !method.GetParameters().Select(p => p.ParameterType).SequenceEqual(signature.Parameters))
                    throw new InvalidOperationException("Unexpected diagnostic instruction meter API shape.");
            }
        }
        if (hasTerminal)
        {
            if (!hasMeter) throw new InvalidOperationException("Terminal prototype API requires the complete diagnostic meter family.");
            foreach (var signature in terminalSignatures)
            {
                var method = methods.Single(m => m.Name == signature.Name);
                if (!method.IsPrivate || method.IsStatic != signature.Static || method.ReturnType != signature.Result ||
                    !method.GetParameters().Select(p => p.ParameterType).SequenceEqual(signature.Parameters))
                    throw new InvalidOperationException("Unexpected terminal prototype API shape.");
            }
        }
        // Keep the policy-v1 receipt scoped to its original five methods. A
        // separately validated optional meter family must not change that ABI.
        var policyMethods = methods.Where(m => expectedNames.Contains(m.Name)).ToArray();
        var imports = policyMethods.Where(m => m.Name.EndsWith("Native")).ToArray();
        if (imports.Length != 2 || imports.Any(m => !m.IsPrivate || !m.IsStatic || m.ReturnType != typeof(int)))
            throw new InvalidOperationException("Unexpected native read-only policy import shape.");
        File.WriteAllText(Path.Combine(evidence, "policy-api.json"), JsonSerializer.Serialize(new { version = observedVersion,
            mode = Mode, defaultPolicy = 0, noSetterInDeclaredPolicyApi = true,
            bridgeSignatures = new[] { create, query, version }.Select(m => m.ToString()).Order().ToArray(),
            nativeImportSignatures = imports.Select(m => m.ToString()).Order().ToArray(),
            allDeclaredPolicySignatures = policyMethods.Select(m => m.ToString()).Order().ToArray(),
            additionalDeclaredMeterSignatures = methods.Where(m => meterSignatures.Any(s => s.Name == m.Name)).Select(m => m.ToString()).Order().ToArray(),
            additionalDeclaredTerminalPrototypeSignatures = methods.Where(m => terminalSignatures.Any(s => s.Name == m.Name)).Select(m => m.ToString()).Order().ToArray() },
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"POLICY API version=1 factory={Mode} default=0 immutable-api=true");
    }
    public static AssemblyLoadContext Create(string directory)
    {
        AssemblyLoadContext context;
        if (Mode == "required")
        {
            Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver = (owner, name) => Resolve(owner, directory, name);
            context = (AssemblyLoadContext)create!.Invoke(null, ["required-probe", resolver])!;
        }
        else context = new ProbeContext(directory);
        Check(context, "before-load");
        return context;
    }
    public static void Check(AssemblyLoadContext context, string phase)
    {
        if (Mode is null) return;
        int expected = Mode == "required" ? 1 : 0;
        int observed = (int)query!.Invoke(context, null)!;
        if (!context.IsCollectible || observed != expected) throw new InvalidOperationException($"Policy mismatch {phase}: {observed}");
        Console.WriteLine($"POLICY context={context.Name} phase={phase} value={observed} collectible=true");
    }
    public static Assembly Load(AssemblyLoadContext context, string path)
    {
        Check(context, "before-explicit-load");
        Assembly assembly = context.LoadFromAssemblyPath(path);
        if (AssemblyLoadContext.GetLoadContext(assembly) != context) throw new InvalidOperationException("Explicit body escaped owning context.");
        Check(context, "after-explicit-load");
        return assembly;
    }
    public static Assembly? Resolve(AssemblyLoadContext context, string directory, AssemblyName name)
    {
        Check(context, "resolver-before");
        if (name.Name == typeof(IProbe).Assembly.GetName().Name)
        {
            if (Mode is not null && (int)query!.Invoke(AssemblyLoadContext.GetLoadContext(typeof(IProbe).Assembly), null)! != 0)
                throw new InvalidOperationException("Shared contract acquired required execution policy.");
            return typeof(IProbe).Assembly;
        }
        if (name.Name is "SelectionProbe.Payload" or "SelectionProbe.Private")
        {
            Assembly dependency = Load(context, Path.Combine(directory, name.Name + ".dll"));
            Check(context, "resolver-after-private");
            if (Mode is not null) Console.WriteLine($"DEPENDENCY resolved-private={name.Name} owning-context=true");
            return dependency;
        }
        return null;
    }
    public static void CheckLatePrivate(AssemblyLoadContext context, bool beforeRun)
    {
        if (Mode is null) return;
        int count = context.Assemblies.Count(a => a.GetName().Name == "SelectionProbe.Private");
        if (count != (beforeRun ? 0 : 1)) throw new InvalidOperationException("Private dependency did not cross the intended late-body-load boundary.");
        Check(context, beforeRun ? "before-run" : "after-run");
        Console.WriteLine($"LATE private={(beforeRun ? "absent" : "loaded")} policy={(Mode == "required" ? 1 : 0)}");
    }
    public static void AssertUnloadedQuery(AssemblyLoadContext context)
    {
        if (Mode is null) return;
        try { query!.Invoke(context, null); }
        catch (TargetInvocationException exception) when (exception.InnerException is InvalidOperationException)
        {
            Console.WriteLine("RETIRED query=System.InvalidOperationException protected=true");
            return;
        }
        throw new InvalidOperationException("Execution policy query accepted an unloaded context.");
    }
}
