using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class ApiAccessCases
{
    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Shared policy preserves framework type/member and field decisions", PolicyTargets);
        yield return ("Shared policy snapshots script and host member identities", PolicySnapshots);
        yield return ("Shared policy rejects identity spoofing and invalid operations", PolicyIdentity);
        yield return ("IL and reflection share declaration signatures and denial decisions", SignatureParity);
        yield return ("Reflection probe roundtrips an IL-approved DTO and calls author ABC", ReflectionRoundtrip);
        yield return ("Reflection probe rejects file access before creating a file", ReflectionFileDenied);
        yield return ("Reflection probe checks property accessors before side effects", ReflectionPropertyDenied);
        yield return ("Reflection probe checks constructors and fields before side effects", ReflectionConstructorAndFieldDenied);
        yield return ("Reflection probe validates constructed generic arguments", ReflectionGenerics);
        yield return ("Reflection probe checks declaring type instead of reflected type", ReflectionInheritedMember);
        yield return ("Reflection probe refuses unchecked polymorphic dispatch", ReflectionVirtualDispatch);
        yield return ("Reflection probe refuses delegate creation and open generic invocation", ReflectionUnsupported);
        yield return ("Reflection probe does not root retired script metadata", ReflectionUnloads);
    }

    private const string Script = """
        namespace Author;
        public sealed class Payload
        {
            public static int Constructions;
            public static int Writes;
            public static int Reads;
            public int Value;
            private int number;
            public string Name { get; set; } = "";
            public int Number { get { Reads++; return number; } set { Writes++; number = value; } }
            public Payload() { Constructions++; }
            public int ABC(int value) => value + 1;
            public bool Starts(string value) => value.StartsWith("x");
            public int Collection(int value)
            {
                var values = new System.Collections.Generic.List<int>();
                values.Add(value);
                return values.Count;
            }
            public static T Echo<T>(T value) => value;
        }
        public class Base { public virtual int Read() => 1; }
        public sealed class Derived : Base
        {
            public static int Calls;
            public override int Read() { Calls++; return 2; }
        }
        """;

    private static readonly Lazy<byte[]> Image = new(() =>
    {
        var compiled = SourceCompiler.Compile("AuthorReflectionProbe", [new("Payload.cs", Script)], CompilerFixture.ApprovedReferences());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        var image = compiled.Assembly!;
        GameplayCapabilityPolicy.Validate(image, [ManagedAssemblyInspector.Inspect(image).AssemblyName], Contract);
        return image;
    });
    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;
    private static IApiAccessPolicy Policy(params string[] scripts) => GameplayCapabilityPolicy.CreateApiPolicy(scripts, Contract);
    private static ApiTarget Target(Type type, ApiTargetKind kind = ApiTargetKind.Type, string? member = null) =>
        new(type.Assembly.FullName!, kind, type.IsGenericType ? type.GetGenericTypeDefinition().FullName : type.FullName, member);

    private static void PolicyTargets()
    {
        var policy = Policy();
        Check.Assert(policy.Evaluate(Target(typeof(string)), ApiOperation.Reference).Allowed, "String type denied.");
        Check.Assert(policy.Evaluate(Target(typeof(string), ApiTargetKind.Method, "StartsWith"), ApiOperation.Invoke).Allowed, "String method denied.");
        Check.Assert(!policy.Evaluate(Target(typeof(object), ApiTargetKind.Method, "GetType"), ApiOperation.Invoke).Allowed, "GetType allowed.");
        Check.Assert(!policy.Evaluate(Target(typeof(File)), ApiOperation.Reference).Allowed, "File type allowed.");
        Check.Assert(!policy.Evaluate(Target(typeof(string), ApiTargetKind.Field, "Empty"), ApiOperation.ReadField).Allowed, "Framework field allowed.");
        Check.Assert(!policy.Evaluate(Target(typeof(string), ApiTargetKind.Method, "StartsWith"), ApiOperation.WriteField).Allowed, "Wrong operation allowed.");
    }

    private static void PolicySnapshots()
    {
        var scripts = new List<string> { "Author, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null" };
        var methods = new List<string> { "Ping" };
        const string contract = "Game.Contracts, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
        var policy = GameplayCapabilityPolicy.CreateApiPolicy(scripts, contract, "Game.IApi", methods);
        scripts.Clear(); methods.Add("Forbidden");
        Check.Assert(policy.Evaluate(new("Author, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", ApiTargetKind.Method, "NewType", "ABC"), ApiOperation.Invoke).Allowed,
            "Author names required predeclaration or mutable input changed policy.");
        Check.Assert(policy.Evaluate(new(contract, ApiTargetKind.Method, "Game.IApi", "Ping"), ApiOperation.Invoke).Allowed, "Host Ping denied.");
        Check.Assert(!policy.Evaluate(new(contract, ApiTargetKind.Method, "Game.IApi", "Forbidden"), ApiOperation.Invoke).Allowed, "Mutable method list expanded policy.");
    }

    private static void PolicyIdentity()
    {
        var policy = Policy();
        Check.Assert(!policy.Evaluate(new("System.Runtime, Version=11.0.0.0, Culture=neutral, PublicKeyToken=null", ApiTargetKind.Type, "System.String"), ApiOperation.Reference).Allowed, "Spoofed framework identity accepted.");
        Check.Assert(!policy.Evaluate(new("System.Runtime", ApiTargetKind.Assembly), ApiOperation.Reference).Allowed, "Partial identity accepted.");
        Check.Assert(!policy.Evaluate(Target(typeof(string)), (ApiOperation)999).Allowed, "Invalid operation accepted.");
        Check.Throws<InvalidDataException>(() => Policy("System.Fake, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"));
    }

    private static void SignatureParity()
    {
        var identity = ManagedAssemblyInspector.Inspect(Image.Value).AssemblyName;
        var recorder = new RecordingPolicy(Policy(identity));
        GameplayCapabilityPolicy.ValidateWithApiPolicy(Image.Value, [identity], Contract, recorder);
        var probe = new ReflectionAccessProbe(Policy(identity));
        Compare(typeof(string).GetMethod("StartsWith", [typeof(string)])!, "System.String", "StartsWith");
        Compare(typeof(List<int>).GetMethod("Add")!, "System.Collections.Generic.List`1", "Add");
        var denied = new DenyMember(Policy(identity), "StartsWith");
        Check.Throws<InvalidDataException>(() => GameplayCapabilityPolicy.ValidateWithApiPolicy(Image.Value, [identity], Contract, denied));
        Check.Throws<InvalidOperationException>(() => new ReflectionAccessProbe(denied).Invoke(typeof(string).GetMethod("StartsWith", [typeof(string)])!, "x", "x"));

        void Compare(MethodInfo method, string typeName, string memberName)
        {
            var actual = probe.Inspect(method).Signature!;
            var expected = recorder.Targets.Single(target => target.TypeName == typeName && target.MemberName == memberName).Signature!;
            Check.Assert(actual.ReturnType == expected.ReturnType && actual.GenericArity == expected.GenericArity &&
                actual.IsInstance == expected.IsInstance && actual.ParameterTypes.SequenceEqual(expected.ParameterTypes), "IL/reflection signature mismatch.");
        }
    }

    private static void ReflectionRoundtrip() => WithScript((type, probe) =>
    {
        var instance = probe.Construct(type.GetConstructor(Type.EmptyTypes)!);
        var field = type.GetField("Value")!;
        var property = type.GetProperty("Name")!;
        probe.Write(field, instance, 41);
        probe.Write(property, instance, "player");
        var snapshot = new Dictionary<string, object?> { ["Value"] = probe.Read(field, instance), ["Name"] = probe.Read(property, instance) };
        var restored = probe.Construct(type.GetConstructor(Type.EmptyTypes)!);
        probe.Write(field, restored, snapshot["Value"]);
        probe.Write(property, restored, snapshot["Name"]);
        Check.Assert((int)probe.Read(field, restored)! == 41 && (string)probe.Read(property, restored)! == "player", "DTO roundtrip failed.");
        Check.Assert((int)probe.Invoke(type.GetMethod("ABC")!, restored, 40)! == 41, "Own ABC was denied.");
        var method = typeof(string).GetMethod("StartsWith", [typeof(string)])!;
        Check.Assert((bool)probe.Invoke(method, "player", "play")!, "Approved framework call failed.");
        var target = probe.Inspect(type.GetMethod("ABC")!);
        Check.Assert(target.AssemblyIdentity == type.Assembly.FullName && target.MemberName == "ABC", "Wrong actual target identity.");
    });

    private static void ReflectionFileDenied()
    {
        using var temp = new TempDirectory();
        var output = Path.Combine(temp.Path, "must-not-exist.txt");
        var method = typeof(File).GetMethod("WriteAllText", [typeof(string), typeof(string)])!;
        var probe = new ReflectionAccessProbe(Policy());
        Check.Throws<InvalidOperationException>(() => probe.Invoke(method, null, output, "forbidden"));
        Check.Assert(!File.Exists(output), "Denied operation created a file.");
    }

    private static void ReflectionPropertyDenied() => WithScript((type, probe) =>
    {
        var instance = probe.Construct(type.GetConstructor(Type.EmptyTypes)!);
        var denied = new ReflectionAccessProbe(new DenyMember(Policy(type.Assembly.FullName!), "set_Number", "get_Number"));
        Check.Throws<InvalidOperationException>(() => denied.Write(type.GetProperty("Number")!, instance, 42));
        Check.Throws<InvalidOperationException>(() => denied.Read(type.GetProperty("Number")!, instance));
        Check.Assert((int)type.GetField("Writes")!.GetValue(null)! == 0 && (int)type.GetField("Reads")!.GetValue(null)! == 0, "Denied accessor ran.");
    });

    private static void ReflectionConstructorAndFieldDenied() => WithScript((type, _) =>
    {
        var policy = Policy(type.Assembly.FullName!);
        var denied = new ReflectionAccessProbe(new DenyMember(policy, ".ctor"));
        Check.Throws<InvalidOperationException>(() => denied.Construct(type.GetConstructor(Type.EmptyTypes)!));
        Check.Assert((int)type.GetField("Constructions")!.GetValue(null)! == 0, "Denied constructor ran.");
        var normal = new ReflectionAccessProbe(policy);
        var instance = normal.Construct(type.GetConstructor(Type.EmptyTypes)!);
        denied = new ReflectionAccessProbe(new DenyMember(policy, "Value"));
        Check.Throws<InvalidOperationException>(() => denied.Write(type.GetField("Value")!, instance, 42));
        Check.Throws<InvalidOperationException>(() => denied.Read(type.GetField("Value")!, instance));
        Check.Assert((int)type.GetField("Value")!.GetValue(instance)! == 0, "Denied field write ran.");
    });

    private static void ReflectionGenerics() => WithScript((type, probe) =>
    {
        var echo = type.GetMethod("Echo")!.MakeGenericMethod(typeof(int));
        Check.Assert((int)probe.Invoke(echo, null, 41)! == 41, "Approved generic invocation failed.");
        var forbidden = type.GetMethod("Echo")!.MakeGenericMethod(typeof(FileInfo));
        Check.Throws<InvalidOperationException>(() => probe.Invoke(forbidden, null, new object?[] { null }));
        Check.Throws<InvalidOperationException>(() => probe.Invoke(typeof(List<FileInfo>).GetMethod("Clear")!, new List<FileInfo>()));
    });

    private static void ReflectionInheritedMember() => WithScript((type, probe) =>
    {
        var instance = probe.Construct(type.GetConstructor(Type.EmptyTypes)!);
        var method = type.GetMethod("GetType")!;
        Check.Assert(method.ReflectedType == type && method.DeclaringType == typeof(object), "Fixture is not an inherited member.");
        Check.Throws<InvalidOperationException>(() => probe.Invoke(method, instance));
    });

    private static void ReflectionVirtualDispatch() => WithScript((type, probe) =>
    {
        var derived = type.Assembly.GetType("Author.Derived")!;
        var parent = type.Assembly.GetType("Author.Base")!;
        var instance = probe.Construct(derived.GetConstructor(Type.EmptyTypes)!);
        Check.Throws<InvalidOperationException>(() => probe.Invoke(parent.GetMethod("Read")!, instance));
        Check.Assert((int)derived.GetField("Calls")!.GetValue(null)! == 0, "Unchecked override ran.");
        Check.Assert((int)probe.Invoke(derived.GetMethod("Read")!, instance)! == 2, "Concrete override target failed.");
    });

    private static void ReflectionUnsupported() => WithScript((type, probe) =>
    {
        var echo = type.GetMethod("Echo")!;
        Check.Throws<InvalidOperationException>(() => probe.Invoke(echo, null, 41));
        Check.Throws<InvalidOperationException>(() => probe.CreateDelegate(echo.MakeGenericMethod(typeof(int)), typeof(Func<int, int>)));
    });

    private static void ReflectionUnloads()
    {
        var (weak, policy) = Retire();
        for (var i = 0; i < 10 && weak.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Check.Assert(!weak.IsAlive, "Policy retained collectible metadata.");
        GC.KeepAlive(policy);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (WeakReference, IApiAccessPolicy) Retire()
    {
        var context = new AssemblyLoadContext("api-policy-retirement", true);
        using var stream = new MemoryStream(Image.Value);
        var assembly = context.LoadFromStream(stream);
        var policy = Policy(assembly.FullName!);
        var probe = new ReflectionAccessProbe(policy);
        var type = assembly.GetType("Author.Payload")!;
        _ = probe.Construct(type.GetConstructor(Type.EmptyTypes)!);
        var weak = new WeakReference(context);
        context.Unload();
        return (weak, policy);
    }

    private static void WithScript(Action<Type, ReflectionAccessProbe> run)
    {
        var context = new AssemblyLoadContext("api-reflection-probe", true);
        try
        {
            using var stream = new MemoryStream(Image.Value);
            var assembly = context.LoadFromStream(stream);
            run(assembly.GetType("Author.Payload")!, new ReflectionAccessProbe(Policy(assembly.FullName!)));
        }
        finally { context.Unload(); }
    }

    private sealed class DenyMember(IApiAccessPolicy inner, params string[] names) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) =>
            names.Contains(target.MemberName, StringComparer.Ordinal) ? ApiDecision.Deny("Probe target explicitly denied.") : inner.Evaluate(target, operation);
    }

    private sealed class RecordingPolicy(IApiAccessPolicy inner) : IApiAccessPolicy
    {
        public List<ApiTarget> Targets { get; } = [];
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            Targets.Add(target);
            return inner.Evaluate(target, operation);
        }
    }
}
