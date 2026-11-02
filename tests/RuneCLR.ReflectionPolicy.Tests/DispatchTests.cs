using System.Reflection;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    private static void ExerciseDispatch(Assembly assembly, IApiAccessPolicy policy)
    {
        var entry = assembly.GetType("ReflectionPolicy.Author.DispatchEntry")!;
        var runs = entry.GetField("Runs")!;
        int Count() => (int)runs.GetValue(null)!;
        var tests = new (string Entry, string Implementation, string Member, object Expected)[]
        {
            ("Virtual", "DispatchChild", "Read", 2),
            ("LibraryVirtual", "DispatchChild", "Read", 2),
            ("Inherited", "DispatchBase", "Read", 1),
            ("Hidden", "DispatchBase", "Read", 1),
            ("Abstract", "DispatchConcrete", "Value", 3),
            ("Interface", "ExplicitDispatch", "ReflectionPolicy.Author.IDispatch.Value", 4),
            ("DefaultInterface", "IDefaultDispatch", "Value", 6),
            ("StructInterface", "StructDispatch", "Value", 5),
            ("Generic", "DispatchChild", "Echo", 43),
            ("GenericType", "GenericDispatchChild", "Echo", "dispatch"),
            ("VariantInterface", "VariantDispatch", "Read", "variant"),
            ("Covariant", "CovariantChild", "Read", "covariant"),
            ("Property", "DispatchChild", "get_Number", 2),
        };
        foreach (var test in tests)
        {
            var method = entry.GetMethod(test.Entry)!;
            var before = Count();
            var denied = new DenyAccess(policy, ApiOperation.Invoke, "ReflectionPolicy.Author." + test.Implementation, test.Member);
            using (PrototypeReflectionPolicy.Enter(denied))
            {
                var error = Expect<TargetInvocationException>(() => method.Invoke(null, null));
                Assert(error.InnerException is InvalidOperationException { Message: var message } && message.StartsWith("Reflection access:", StringComparison.Ordinal),
                    test.Entry + " failed for a reason other than policy rejection.");
            }
            Assert(Count() == before, test.Entry + " executed its denied implementation.");
            var trace = new TargetTrace(policy);
            using (PrototypeReflectionPolicy.Enter(trace))
                Assert(Equals(method.Invoke(null, null), test.Expected), test.Entry + " returned a wrong value.");
            Assert(Count() == before + 1 && trace.Targets.Any(target => target.TypeName == "ReflectionPolicy.Author." + test.Implementation && target.MemberName == test.Member),
                test.Entry + " did not check the actual implementation.");
            Pass("resolved dispatch target and denial-before-body: " + test.Entry);
        }
        var virtualCall = entry.GetMethod("Virtual")!.CreateDelegate<Func<int>>();
        var beforeDeclaration = Count();
        using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.Invoke, "ReflectionPolicy.Author.DispatchBase", "Read")))
            Expect<InvalidOperationException>(() => virtualCall());
        Assert(Count() == beforeDeclaration, "The requested declaration was not checked.");
        Pass("requested declaration is checked independently of the final override");
        foreach (var test in new[] { (Entry: "SetProperty", Member: "set_Number"), (Entry: "Event", Member: "add_Changed") })
        {
            var call = entry.GetMethod(test.Entry)!.CreateDelegate<Action>();
            var before = Count();
            using (PrototypeReflectionPolicy.Enter(new DenyAccess(policy, ApiOperation.Invoke, "ReflectionPolicy.Author.DispatchChild", test.Member)))
                Expect<InvalidOperationException>(call);
            Assert(Count() == before, "Denied property/event override executed.");
            using (PrototypeReflectionPolicy.Enter(policy)) call();
            Assert(Count() > before, "Allowed property/event did not execute.");
            Pass("actual accessor dispatch checked: " + test.Entry);
        }
        var dynamicReceiver = new DynamicReceiver();
        var interfaceMethod = assembly.GetType("ReflectionPolicy.Author.IDispatch")!.GetMethod("Value")!;
        using (PrototypeReflectionPolicy.Enter(policy))
            Expect<NotSupportedException>(() => interfaceMethod.Invoke(dynamicReceiver, null));
        Assert(dynamicReceiver.Casts == 0, "An unsupported dynamic cast ran before target checking.");
        Pass("object-dependent interface dispatch refuses before user cast callbacks");
    }

    private sealed class DynamicReceiver : System.Runtime.InteropServices.IDynamicInterfaceCastable
    {
        public int Casts;
        public bool IsInterfaceImplemented(RuntimeTypeHandle interfaceType, bool throwIfNotImplemented) { Casts++; return false; }
        public RuntimeTypeHandle GetInterfaceImplementation(RuntimeTypeHandle interfaceType) { Casts++; throw new NotSupportedException(); }
    }

    private sealed class TargetTrace(IApiAccessPolicy inner) : IApiAccessPolicy
    {
        public List<ApiTarget> Targets { get; } = [];
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (operation == ApiOperation.Invoke) Targets.Add(target);
            return inner.Evaluate(target, operation);
        }
    }
}
