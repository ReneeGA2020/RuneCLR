using System.Reflection;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    private static void ExerciseFactories(Assembly assembly, IApiAccessPolicy policy)
    {
        var entry = assembly.GetType("ReflectionPolicy.Author.FactoryEntry")!;
        T Callback<T>(string name) where T : Delegate => entry.GetMethod(name)!.CreateDelegate<T>();
        int Count(string name = "Runs") => (int)entry.GetField(name)!.GetValue(null)!;
        Callback<Action>("Prepare")(); // Reuse factories prepared before policy activation.
        var method = Callback<Func<int, int>>("FastMethod");
        var construct = Callback<Action<int>>("FastConstructor");
        for (int count = 0; count <= 5; count++)
        {
            int before = Count();
            using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, "M" + count)))
                Expect<InvalidOperationException>(() => method(count));
            Assert(Count() == before, "Cached MethodInvoker ran a denied method.");
            using (PrototypeReflectionPolicy.Enter(policy))
                Assert(method(count) == count, "Allowed MethodInvoker returned a wrong result.");
            Assert(Count() == before + 1, "Allowed MethodInvoker did not execute.");
            before = Count();
            using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, ".ctor")))
                Expect<InvalidOperationException>(() => construct(count));
            Assert(Count() == before, "Cached ConstructorInvoker ran a denied constructor.");
            using (PrototypeReflectionPolicy.Enter(policy)) construct(count);
            Assert(Count() == before + 1, "Allowed ConstructorInvoker did not execute.");
        }
        Pass("cached MethodInvoker and ConstructorInvoker check every invocation for arities 0 through 5");
        var existing = Activator.CreateInstance(assembly.GetType("ReflectionPolicy.Author.FastTarget")!)!;
        var existingConstructor = MethodInvoker.Create(existing.GetType().GetConstructor([typeof(int)])!);
        var beforeExisting = Count();
        using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, ".ctor")))
            Expect<InvalidOperationException>(() => existingConstructor.Invoke(existing, 1));
        Assert(Count() == beforeExisting, "A denied cached invoker re-ran an existing receiver's constructor.");
        using (PrototypeReflectionPolicy.Enter(policy)) existingConstructor.Invoke(existing, 1);
        Assert(Count() == beforeExisting + 1, "An allowed existing-receiver constructor did not execute.");
        Pass("MethodInvoker constructor on an existing receiver uses Construct before body");
        var virtualCall = Callback<Func<int>>("FastVirtual");
        using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.Invoke, "ReflectionPolicy.Author.DispatchChild", "Read")))
            Expect<InvalidOperationException>(() => virtualCall());
        using (PrototypeReflectionPolicy.Enter(policy)) Assert(virtualCall() == 2, "Fast virtual dispatch failed.");
        Pass("cached MethodInvoker resolves the actual virtual implementation");
        foreach (var name in new[] { "Default", "Generic", "LibraryGeneric" })
        {
            var call = Callback<Action>(name);
            var before = Count();
            using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, ".ctor"))) Expect<InvalidOperationException>(call);
            Assert(Count() == before && Count("StaticRuns") == 0, "Denied activation initialized or executed its target.");
        }
        foreach (var name in new[] { "Default", "Generic", "LibraryGeneric" })
        {
            var call = Callback<Action>(name);
            var before = Count();
            using (PrototypeReflectionPolicy.Enter(policy)) call();
            Assert(Count() == before + 1, "Allowed activation did not execute its constructor.");
        }
        Pass("Activator default and generic factories check before target cctor/body in interpreted and compiled code");
        foreach (var name in new[] { "DefaultStruct", "GenericStruct" })
        {
            var call = Callback<Action>(name);
            using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.Construct, "ReflectionPolicy.Author.ImplicitValue", null!)))
                Expect<InvalidOperationException>(call);
            using (PrototypeReflectionPolicy.Enter(policy)) call();
        }
        Pass("implicit value-type activation checks type construction without inventing a constructor");
        foreach (var name in new[] { "ExplicitStruct", "Parameterized" })
        {
            var call = Callback<Action>(name);
            var before = Count();
            using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, ".ctor"))) Expect<InvalidOperationException>(call);
            Assert(Count() == before, "Denied parameterized/value constructor executed.");
            using (PrototypeReflectionPolicy.Enter(policy)) call();
            Assert(Count() == before + 1, "Allowed constructor did not execute.");
        }
        Pass("Activator parameterized and explicit value-type constructors use the same policy");
        var invokeMember = Callback<Action>("TypeInvoke");
        var initial = Count();
        using (PrototypeReflectionPolicy.Enter(new DenyMember(policy, "M1"))) Expect<InvalidOperationException>(invokeMember);
        Assert(Count() == initial, "Type.InvokeMember bypassed method checks.");
        using (PrototypeReflectionPolicy.Enter(policy)) invokeMember();
        Assert(Count() == initial + 1, "Allowed Type.InvokeMember failed.");
        Pass("Type.InvokeMember converges on checked invocation");
    }

    private static void ExerciseRetiredFactories(Assembly assembly, ExecutionContext flow)
    {
        var factories = assembly.GetType("ReflectionPolicy.Author.FactoryEntry")!;
        var attributes = assembly.GetType("ReflectionPolicy.Author.AttributeEntry")!;
        var dispatch = assembly.GetType("ReflectionPolicy.Author.DispatchEntry")!;
        var fastMethod = factories.GetMethod("FastMethod")!.CreateDelegate<Func<int, int>>();
        var fastConstructor = factories.GetMethod("FastConstructor")!.CreateDelegate<Action<int>>();
        var readAttribute = attributes.GetMethod("Read")!.CreateDelegate<Action>();
        var virtualCall = dispatch.GetMethod("Virtual")!.CreateDelegate<Func<int>>();
        int Count(Type type, string field) => (int)type.GetField(field)!.GetValue(null)!;
        var before = (Count(factories, "Runs"), Count(attributes, "Constructors"), Count(dispatch, "Runs"));
        var actions = new List<Action> { () => fastMethod(1), () => fastConstructor(1), readAttribute, () => virtualCall() };
        foreach (var name in new[] { "Default", "Generic", "Parameterized", "ExplicitStruct" })
            actions.Add(factories.GetMethod(name)!.CreateDelegate<Action>());
        foreach (var action in actions)
        {
            var error = Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => action(), null));
            Assert(error.Message.Contains("scope has retired", StringComparison.Ordinal), "Retired operation failed for the wrong reason.");
        }
        Assert(before == (Count(factories, "Runs"), Count(attributes, "Constructors"), Count(dispatch, "Runs")),
            "A new reflection route executed under a retired context.");
        Pass("retired scope rejects dispatch, cached invokers, activation and attributes before target effects");
    }
}
