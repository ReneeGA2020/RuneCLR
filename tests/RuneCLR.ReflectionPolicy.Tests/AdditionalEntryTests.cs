using System.Reflection;
using System.Reflection.Emit;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    private static void ExerciseAdditionalEntries(Assembly assembly, IApiAccessPolicy policy)
    {
        var entry = assembly.GetType("ReflectionPolicy.Author.AttributeEntry")!;
        T Callback<T>(string name) where T : Delegate => entry.GetMethod(name)!.CreateDelegate<T>();
        int Count(string name) => (int)entry.GetField(name)!.GetValue(null)!;
        var read = Callback<Action>("Read");
        var readDefault = Callback<Action>("ReadDefault");
        var snapshot = Callback<Func<int>>("Snapshot");
        using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, ".ctor")))
        {
            Expect<InvalidOperationException>(read);
            Expect<InvalidOperationException>(readDefault);
        }
        Assert(Count("StaticRuns") == 0 && Count("Constructors") == 0 && Count("Defaults") == 0,
            "Denied attribute construction initialized or executed an attribute.");
        using (PrototypeReflectionPolicy.Enter(policy)) { read(); readDefault(); }
        Assert(Count("Constructors") == 1 && Count("Defaults") == 1 && snapshot() == 17, "Allowed attribute initialization failed.");
        Pass("attribute default and optimized parameterized construction checks precede cctor/body");
        var setters = Count("Setters");
        using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.Invoke, "ReflectionPolicy.Author.GateAttribute", "set_Number")))
        {
            var error = Expect<CustomAttributeFormatException>(read);
            Assert(error.InnerException is InvalidOperationException, "Attribute setter did not reject via policy.");
        }
        Assert(Count("Setters") == setters, "Denied named attribute setter executed.");
        using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.WriteField, "ReflectionPolicy.Author.GateAttribute", "Field")))
        {
            var error = Expect<CustomAttributeFormatException>(read);
            Assert(error.InnerException is InvalidOperationException, "Attribute field did not reject via policy.");
        }
        Pass("attribute named properties and fields retain per-target enforcement");

        var payload = assembly.GetType("ReflectionPolicy.Author.Payload")!;
        var target = payload.GetMethod("ABC")!;
        var bound = target.CreateDelegate<Func<int, int>>();
        var dynamic = new DynamicMethod("UnsupportedAuthorCode", typeof(int), Type.EmptyTypes);
        var il = dynamic.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4, 23); il.Emit(OpCodes.Ret);
        var cachedDynamicInvoker = MethodInvoker.Create(dynamic);
        var reflectedInvoke = bound.GetType().GetMethod("Invoke")!;
        var cachedDelegateInvoker = MethodInvoker.Create(reflectedInvoke);
        var unsupported = new (string Name, Action Call)[]
        {
            ("MethodInfo.CreateDelegate", () => target.CreateDelegate(typeof(Func<int, int>))),
            ("Delegate.CreateDelegate method", () => Delegate.CreateDelegate(typeof(Func<int, int>), target)),
            ("Delegate.CreateDelegate closed method", () => Delegate.CreateDelegate(typeof(Func<int, int>), null, target)),
            ("Delegate.CreateDelegate static name", () => Delegate.CreateDelegate(typeof(Func<int, int>), payload, "ABC")),
            ("Delegate.CreateDelegate instance name", () => Delegate.CreateDelegate(typeof(Func<string>), "x", "ToString")),
            ("DynamicInvoke", () => bound.DynamicInvoke(1)),
            ("reflected delegate Invoke", () => reflectedInvoke.Invoke(bound, [1])),
            ("cached delegate MethodInvoker", () => cachedDelegateInvoker.Invoke(bound, 1)),
            ("DynamicMethod.Invoke", () => dynamic.Invoke(null, null)),
            ("DynamicMethod.CreateDelegate", () => dynamic.CreateDelegate(typeof(Func<int>))),
            ("dynamic MethodInvoker creation", () => MethodInvoker.Create(dynamic)),
            ("cached dynamic MethodInvoker", () => cachedDynamicInvoker.Invoke(null)),
        };
        using (PrototypeReflectionPolicy.Enter(policy))
            foreach (var test in unsupported)
            {
                try { test.Call(); throw new InvalidOperationException(test.Name + " unexpectedly executed."); }
                catch (NotSupportedException) { }
                catch (InvalidOperationException error) when (test.Name == "cached dynamic MethodInvoker" && error.Message.StartsWith("Reflection access:", StringComparison.Ordinal)) { }
            }
        Assert(bound(1) == 2 && (int)dynamic.Invoke(null, null)! == 23, "Outside-scope trusted behavior changed.");
        Pass("twelve unsupported delegate and dynamic-code routes refuse while scoped, including pre-cached invokers");
        entry.GetField("Last")!.SetValue(null, null);
    }
}
