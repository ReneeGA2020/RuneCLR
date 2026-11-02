using System.Globalization;
using System.Reflection;
using System.Runtime.CompilerServices;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ExerciseAccess(Assembly assembly, IApiAccessPolicy policy)
    {
        var type = assembly.GetType("ReflectionPolicy.Author.AccessEntry")!;
        var counters = assembly.GetType("ReflectionPolicy.Author.Counters")!;
        T Callback<T>(string name) where T : Delegate => type.GetMethod(name)!.CreateDelegate<T>();
        int Count(string name) => (int)counters.GetField(name)!.GetValue(null)!;
        var snapshot = Callback<Func<int>>("Snapshot");
        var number = Callback<Func<int>>("NumberSnapshot");
        var readonlySnapshot = Callback<Func<int>>("ReadonlySnapshot");
        var objectSnapshot = Callback<Func<object?>>("ObjectSnapshot");
        _ = snapshot(); // Initialize the fixture outside a policy scope.
        var roundTrip = Callback<Func<int>>("RoundTrip");
        var libraryRoundTrip = Callback<Func<int>>("LibraryRoundTrip");
        var construct = Callback<Action>("ConstructDenied");
        var libraryConstruct = Callback<Action>("LibraryConstructDenied");
        var existing = Callback<Action>("ConstructExisting");
        var throwing = Callback<Action>("ConstructThrowing");
        var read = Callback<Func<int>>("ReadField");
        var write = Callback<Action>("WriteField");
        var libraryRead = Callback<Func<int>>("LibraryReadField");
        var libraryWrite = Callback<Action>("LibraryWriteField");
        var readProperty = Callback<Func<int>>("ReadProperty");
        var writeProperty = Callback<Action>("WriteProperty");
        var libraryReadProperty = Callback<Func<int>>("LibraryReadProperty");
        var libraryWriteProperty = Callback<Action>("LibraryWriteProperty");
        var readIndex = Callback<Func<int>>("ReadIndex");
        var writeIndex = Callback<Action>("WriteIndex");
        var readStatic = Callback<Func<int>>("ReadStatic");
        var writeStatic = Callback<Action>("WriteStatic");
        var readConstant = Callback<Func<int>>("ReadConstant");
        var readRawConstant = Callback<Func<int>>("ReadRawConstant");
        var readonlyWrite = Callback<Action>("WriteReadonly");
        var badValue = Callback<Action>("WriteForbiddenValue");
        var generic = Callback<Func<int>>("GenericFields");
        var badGeneric = Callback<Action>("ForbiddenGenericConstructor");
        var constructorBinder = Callback<Action<Binder>>("ConstructWithBinder");
        var fieldBinder = Callback<Action<Binder>>("FieldWithBinder");
        var propertyBinder = Callback<Action<Binder>>("PropertyWithBinder");

        IDisposable Deny(ApiOperation operation, string declaringType, string member) =>
            PrototypeReflectionPolicy.Enter(new DenyAccess(policy, operation, "ReflectionPolicy.Author." + declaringType, member));
        var trace = new TracingPolicy(policy);
        using (PrototypeReflectionPolicy.Enter(trace))
            Assert(roundTrip() == 85 && libraryRoundTrip() == 42, "DTO roundtrip changed values.");
        Assert(new[] { ApiOperation.Construct, ApiOperation.ReadField, ApiOperation.WriteField, ApiOperation.Invoke }
            .All(trace.Operations.Contains), "The runtime did not distinguish reflection operations.");
        Pass("ordinary and compiled-library constructor/field/property DTO roundtrips use the common evaluator");

        using (Deny(ApiOperation.Construct, "DeniedConstruction", ".ctor"))
        {
            Expect<InvalidOperationException>(construct);
            Expect<InvalidOperationException>(libraryConstruct);
        }
        Assert(Count("ConstructorStaticRuns") == 0 && Count("ConstructorBodyRuns") == 0,
            "A denied constructor initialized its type or ran its body.");
        Pass("ordinary and compiled-library constructor denial precedes type initialization and body");

        var before = snapshot();
        using (Deny(ApiOperation.Construct, "Dto", ".ctor")) Expect<InvalidOperationException>(existing);
        Assert(snapshot() == before, "A denied constructor modified its existing receiver.");
        using (PrototypeReflectionPolicy.Enter(policy)) existing();
        Assert(snapshot() == 99, "Approved construction on an existing receiver failed.");
        Pass("both allocating and existing-receiver ConstructorInfo.Invoke routes are checked");

        using (Deny(ApiOperation.ReadField, "Dto", "Value"))
        {
            Expect<InvalidOperationException>(() => read());
            Expect<InvalidOperationException>(() => libraryRead());
            write();
        }
        before = snapshot();
        using (Deny(ApiOperation.WriteField, "Dto", "Value"))
        {
            Assert(read() == before && libraryRead() == before, "Read permission inherited write denial.");
            Expect<InvalidOperationException>(write);
            Expect<InvalidOperationException>(libraryWrite);
        }
        Assert(snapshot() == before, "Denied field writes mutated storage.");
        Pass("field reads and writes have independent policy decisions, including compiled-library paths");

        using (Deny(ApiOperation.ReadField, "StaticFieldTarget", "Value")) Expect<InvalidOperationException>(() => readStatic());
        using (Deny(ApiOperation.WriteField, "StaticFieldTarget", "Value")) Expect<InvalidOperationException>(writeStatic);
        Assert(Count("FieldStaticRuns") == 0, "Denied static field access initialized its type.");
        using (PrototypeReflectionPolicy.Enter(policy)) Assert(readStatic() == 77, "Approved static field read failed.");
        Assert(Count("FieldStaticRuns") == 1, "Positive static field control did not initialize its type.");
        Pass("static field denial precedes initialization, with a live allowed control");

        using (Deny(ApiOperation.ReadField, "Dto", "Constant"))
        {
            Expect<InvalidOperationException>(() => readConstant());
            Expect<InvalidOperationException>(() => readRawConstant());
        }
        using (PrototypeReflectionPolicy.Enter(policy)) Assert(readConstant() == 23 && readRawConstant() == 23, "Constant field read failed.");
        Pass("literal GetValue and GetRawConstantValue share the field-read policy");

        var reads = Count("PropertyReads");
        var writes = Count("PropertyWrites");
        var priorNumber = number();
        using (Deny(ApiOperation.Invoke, "Dto", "get_Number"))
        {
            Expect<InvalidOperationException>(() => readProperty());
            Expect<InvalidOperationException>(() => libraryReadProperty());
        }
        using (Deny(ApiOperation.Invoke, "Dto", "set_Number"))
        {
            Expect<InvalidOperationException>(writeProperty);
            Expect<InvalidOperationException>(libraryWriteProperty);
        }
        Assert(Count("PropertyReads") == reads && Count("PropertyWrites") == writes && number() == priorNumber,
            "Denied property access reached a getter, fast setter or backing storage.");
        Pass("property getter and fast setter refusal precedes accessor effects, including compiled libraries");

        reads = Count("IndexReads");
        writes = Count("IndexWrites");
        using (Deny(ApiOperation.Invoke, "Dto", "get_Item")) Expect<InvalidOperationException>(() => readIndex());
        using (Deny(ApiOperation.Invoke, "Dto", "set_Item")) Expect<InvalidOperationException>(writeIndex);
        Assert(Count("IndexReads") == reads && Count("IndexWrites") == writes, "Denied indexers executed.");
        Pass("indexed property getter and setter are checked before dispatch");

        using (PrototypeReflectionPolicy.Enter(policy))
        {
            Expect<InvalidOperationException>(readonlyWrite);
            Assert(readonlySnapshot() == 10, "Denied readonly field write changed storage.");
            Expect<InvalidOperationException>(badValue);
            Assert(objectSnapshot() is null, "A forbidden field value was stored.");
        }
        Pass("readonly field writes and forbidden runtime value types refuse before mutation");

        using (PrototypeReflectionPolicy.Enter(policy))
        {
            Assert(generic() == 42 && Count("BoxRuns") == 1, "Constructed generic DTO failed.");
            Expect<InvalidOperationException>(badGeneric);
            Assert(Count("BoxRuns") == 1, "A forbidden constructed generic constructor executed.");
        }
        Pass("constructed generic constructor and field signatures use their actual type arguments");

        using (PrototypeReflectionPolicy.Enter(policy))
        {
            var error = Expect<TargetInvocationException>(throwing);
            Assert(error.InnerException is InvalidOperationException { Message: "constructor-failure" }, "Constructor exception wrapping changed.");
        }
        Pass("allowed constructors retain ordinary TargetInvocationException wrapping");

        var binder = new TrackingBinder();
        using (Deny(ApiOperation.Construct, "Dto", ".ctor")) Expect<InvalidOperationException>(() => constructorBinder(binder));
        using (Deny(ApiOperation.WriteField, "Dto", "Value")) Expect<InvalidOperationException>(() => fieldBinder(binder));
        using (Deny(ApiOperation.Invoke, "Dto", "set_Number")) Expect<InvalidOperationException>(() => propertyBinder(binder));
        Assert(binder.Conversions == 0, "Denied reflection invoked custom Binder.ChangeType.");
        using (PrototypeReflectionPolicy.Enter(policy))
        {
            constructorBinder(binder); fieldBinder(binder); propertyBinder(binder);
        }
        Assert(binder.Conversions == 3 && snapshot() == 99 && number() == 99, "Allowed Binder conversion controls failed.");
        Pass("constructor, field and fast property setter denial precedes custom Binder conversion");

        var nestedTarget = assembly.GetType("ReflectionPolicy.Author.Payload")!.GetMethod("ABC")!;
        using (PrototypeReflectionPolicy.Enter(new RecursivePolicy(nestedTarget))) Expect<InvalidOperationException>(() => roundTrip());
        using (PrototypeReflectionPolicy.Enter(policy)) Assert(roundTrip() == 85, "Recursive rejection left enforcement stuck.");
        Pass("recursive reflection in a policy callback rejects and restores subsequent checks");

        var direct = assembly.GetType("ReflectionPolicy.Author.Dto")!.GetField("Value")!;
        using (PrototypeReflectionPolicy.Enter(policy))
        {
            Expect<NotSupportedException>(() => direct.GetValueDirect(default));
            Expect<NotSupportedException>(() => direct.SetValueDirect(default, 1));
        }
        Pass("unsupported TypedReference field routes refuse before native access");
    }

    private static void ExerciseRetiredAccess(Assembly assembly, ExecutionContext flow)
    {
        var type = assembly.GetType("ReflectionPolicy.Author.AccessEntry")!;
        foreach (var name in new[] { "ConstructDenied", "WriteField", "WriteProperty" })
        {
            var action = type.GetMethod(name)!.CreateDelegate<Action>();
            Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => action(), null));
        }
        Pass("retired execution contexts refuse constructor, field and property operations");
    }

    private sealed class DenyAccess(IApiAccessPolicy inner, ApiOperation denied, string type, string member) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) => operation == denied && target.TypeName == type && target.MemberName == member
            ? ApiDecision.Deny("Access denied by the operation-specific test policy.") : inner.Evaluate(target, operation);
    }

    private sealed class TracingPolicy(IApiAccessPolicy inner) : IApiAccessPolicy
    {
        public HashSet<ApiOperation> Operations { get; } = [];
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            Operations.Add(operation);
            return inner.Evaluate(target, operation);
        }
    }

    private sealed class RecursivePolicy(MethodInfo target) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget _, ApiOperation operation)
        {
            target.Invoke(null, [1]);
            return ApiDecision.Allow;
        }
    }

    private sealed class TrackingBinder : Binder
    {
        public int Conversions;
        public override object ChangeType(object value, Type type, CultureInfo? culture)
        {
            Conversions++;
            return Convert.ChangeType(value, type, CultureInfo.InvariantCulture);
        }
        public override FieldInfo BindToField(BindingFlags flags, FieldInfo[] match, object value, CultureInfo? culture) => throw new NotSupportedException();
        public override MethodBase BindToMethod(BindingFlags flags, MethodBase[] match, ref object?[] args, ParameterModifier[]? modifiers,
            CultureInfo? culture, string[]? names, out object? state) => throw new NotSupportedException();
        public override void ReorderArgumentArray(ref object?[] args, object state) => throw new NotSupportedException();
        public override MethodBase? SelectMethod(BindingFlags flags, MethodBase[] match, Type[] types, ParameterModifier[]? modifiers) => throw new NotSupportedException();
        public override PropertyInfo? SelectProperty(BindingFlags flags, PropertyInfo[] match, Type? returnType, Type[]? indexes, ParameterModifier[]? modifiers) => throw new NotSupportedException();
    }
}
