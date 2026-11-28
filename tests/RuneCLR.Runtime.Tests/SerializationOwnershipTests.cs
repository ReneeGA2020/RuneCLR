using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

internal static class SerializationOwnershipTests
{
    private const int ObservationRounds = 12;
    private const string RecordName = "RuneCLR.SerializationFixtures.Record";

    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Bounded field serialization retires independent dual-context sessions A-B-A", BoundedSessions);
        yield return ("Bounded field codec rejects unknown shapes and does not invoke properties", BoundedCodecBoundary);
        foreach (var root in Enum.GetValues<RootKind>())
        {
            var captured = root;
            yield return ($"Retained serialization {root} owns both contexts until explicitly released", () => OwnedRoot(captured));
        }
    }

    private static void BoundedSessions()
        => RequireCollected(RunBoundedSessions());

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static PairReferences RunBoundedSessions()
    {
        using var foreign = Pair.Open("foreign", 7);
        foreach (var (label, value) in new[] { ("A", 41), ("B", 42), ("A", 41) })
        {
            var retired = RetireBounded(label, value);
            AssertPayload(retired.Payload, label, value);
            RequireCollected(retired.References);
            AssertPayload(WriteBounded(foreign.Author), "foreign", 7);
        }
        GC.KeepAlive(foreign);
        return foreign.References;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Retired RetireBounded(string label, int value, bool throwing = false)
    {
        using var pair = Pair.Open(label, value, throwing);
        return new(pair.References, WriteBounded(pair.Author));
    }

    private static void BoundedCodecBoundary()
    {
        var retired = RetireBounded("fields-only", 5, throwing: true);
        AssertPayload(retired.Payload, "fields-only", 5);
        RequireCollected(retired.References);
        Throws<InvalidDataException>(() => WriteBounded(new { Value = 1, Label = "properties are not fields" }));
        Throws<InvalidDataException>(() => WriteBounded(new InvalidRecord()));
    }

    private static void OwnedRoot(RootKind kind)
        => RequireCollected(RunOwnedRoot(kind));

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static PairReferences RunOwnedRoot(RootKind kind)
    {
        using var foreign = Pair.Open("foreign", 7);
        var lease = new Lease();
        var retired = RetireWithRoot(lease, kind);
        try
        {
            Observe(retired);
            Check(retired.Framework.Type.IsAlive && retired.Author.Type.IsAlive,
                "The explicit serialization owner did not retain both DTO types.");
            Check(lease.Value is not null, "The retaining control lost its strong root.");
            AssertPayload(WriteBounded(foreign.Author), "foreign", 7);
            Release(lease);
            RequireCollected(retired);
            AssertPayload(WriteBounded(foreign.Author), "foreign", 7);
            GC.KeepAlive(lease);
            GC.KeepAlive(foreign);
            return foreign.References;
        }
        finally { Release(lease); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static PairReferences RetireWithRoot(Lease lease, RootKind kind)
    {
        using var pair = Pair.Open("owned", 19);
        var options = new JsonSerializerOptions();
        var info = JsonTypeInfo.CreateJsonTypeInfo(pair.Author.GetType(), options);
        // The metadata graph deliberately includes the second collectible role. This is
        // a public-API ownership control, not a reflection serializer's cache behaviour.
        info.Properties.Add(info.CreateJsonPropertyInfo(pair.Framework.GetType(), "Peer"));
        var resolver = new OwnedResolver(info);
        options.TypeInfoResolver = resolver;
        Check(ReferenceEquals(resolver.GetTypeInfo(pair.Author.GetType(), options), info), "Resolver oracle.");
        lease.Value = kind switch
        {
            RootKind.Options => options,
            RootKind.Resolver => resolver,
            RootKind.TypeInfo => info,
            RootKind.Instance => pair.Author,
            _ => throw new ArgumentOutOfRangeException(nameof(kind))
        };
        return pair.References;
    }

    // Reflection getters, arbitrary graphs, polymorphism and general .NET serialization
    // are intentionally outside this small codec. Only these exact scalar fields cross.
    private static byte[] WriteBounded(object record)
    {
        var value = ReadField<int>(record, "Value");
        var label = ReadField<string>(record, "Label");
        if (label.Length > 64) throw new InvalidDataException("Label exceeds the fixture contract.");
        var peer = ReadField<object?>(record, "Peer");
        var peerValue = peer is null ? 0 : ReadField<int>(peer, "Value");
        using var output = new MemoryStream();
        using (var writer = new Utf8JsonWriter(output))
        {
            writer.WriteStartObject();
            writer.WriteNumber("value", value);
            writer.WriteString("label", label);
            writer.WriteNumber("peerValue", peerValue);
            writer.WriteEndObject();
        }
        return output.ToArray();
    }

    private static T ReadField<T>(object record, string name)
    {
        var field = record.GetType().GetField(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
        if (field is null || field.FieldType != typeof(T))
            throw new InvalidDataException("Unsupported scalar field: " + name);
        return (T)field.GetValue(record)!;
    }

    private static void AssertPayload(byte[] bytes, string label, int value)
    {
        using var document = JsonDocument.Parse(bytes);
        Check(document.RootElement.GetProperty("value").GetInt32() == value &&
            document.RootElement.GetProperty("label").GetString() == label &&
            document.RootElement.GetProperty("peerValue").GetInt32() == value + 100,
            "The scalar snapshot changed across the ownership boundary.");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Release(Lease lease) => lease.Value = null;

    private static int Observe(PairReferences references)
    {
        // Never dereference weak targets in the collecting frame. First let finalizers
        // release native loader state, then collect again, then inspect the weak handles.
        for (var round = 0; round < ObservationRounds; round++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
            if (references.Collected) return round + 1;
        }
        return ObservationRounds;
    }

    private static void RequireCollected(PairReferences references)
    {
        Observe(references);
        Check(references.Collected,
            "Collection not observed after stack return and diagnostic finalizer/GC cycles: " + references.Snapshot());
    }

    // Run one mode per fresh process. An external serializer's cache retention is an
    // observation, never silently converted into a successful collection regression.
    internal static int Probe(string mode)
    {
        if (mode is not ("none" or "bounded" or "owned" or "equivalent" or "default" or "failure"))
        {
            Console.Error.WriteLine("Serialization probe mode: none|bounded|owned|equivalent|default|failure");
            return 2;
        }
        var result = RunProbe(mode);
        var foreignCycles = Observe(result.Foreign);
        var foreignCollected = result.Foreign.Collected;
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            mode, runtime = RuntimeInformation.FrameworkDescription,
            serializer = typeof(JsonSerializer).Assembly.GetName().Version?.ToString(),
            serializerMvid = typeof(JsonSerializer).Assembly.ManifestModule.ModuleVersionId,
            result.WhileHeld, result.AfterRelease, foreign = result.Foreign.Snapshot(),
            result.FunctionalOracle, result.ErrorText,
            observation = result.AfterRelease.Collected && foreignCollected ? "collected" : "retained-after-observation",
            result.HeldCycles, result.ReleasedCycles, foreignCycles,
            maximumDiagnosticCycles = ObservationRounds
        }));
        // 3 is an incomplete collection observation, not proof of a leak or a passing test.
        return result.AfterRelease.Collected && foreignCollected ? 0 : 3;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static ProbeResult RunProbe(string mode)
    {
        using var foreign = Pair.Open("foreign", 7);
        var sharedResolver = new DefaultJsonTypeInfoResolver();
        var foreignOptions = mode == "default" ? JsonSerializerOptions.Default : NewReflectionOptions(sharedResolver);
        // Default visits the DTO's scalar/peer properties. Explicit reflection options
        // additionally visit fields, so both paths must really traverse both roles.
        if (mode is not ("none" or "bounded")) ValidateReflection(foreign.Author, foreignOptions, includeFields: mode != "default");
        var lease = new Lease();
        var retired = RetireReflection(mode, sharedResolver, foreignOptions, lease);
        try
        {
            var heldCycles = Observe(retired.References);
            var held = retired.References.Snapshot();
            Release(lease);
            var releasedCycles = Observe(retired.References);
            var released = retired.References.Snapshot();
            // Foreign metadata and objects stay live and usable throughout old-session retirement.
            if (mode is "none" or "bounded") AssertPayload(WriteBounded(foreign.Author), "foreign", 7);
            else ValidateReflection(foreign.Author, foreignOptions, includeFields: mode != "default");
            GC.KeepAlive(foreignOptions);
            GC.KeepAlive(sharedResolver);
            return new(held, released, foreign.References, true, retired.ErrorText, heldCycles, releasedCycles);
        }
        finally { Release(lease); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static ReflectionRetired RetireReflection(string mode, DefaultJsonTypeInfoResolver shared,
        JsonSerializerOptions foreignOptions, Lease lease)
    {
        using var pair = Pair.Open("retired", 11, throwing: mode == "failure");
        if (mode == "none") return new(pair.References, null);
        if (mode == "bounded")
        {
            AssertPayload(WriteBounded(pair.Author), "retired", 11);
            return new(pair.References, null);
        }
        var options = mode switch
        {
            "default" => JsonSerializerOptions.Default,
            "equivalent" => new JsonSerializerOptions(foreignOptions),
            _ => NewReflectionOptions(new DefaultJsonTypeInfoResolver())
        };
        if (mode == "equivalent") Check(ReferenceEquals(options.TypeInfoResolver, shared), "Equivalent resolver oracle.");
        lease.Value = options;
        if (mode == "failure")
        {
            try { _ = JsonSerializer.Serialize(pair.Author, pair.Author.GetType(), options); }
            catch (Exception error) when (error.Message.Contains("synthetic serialization getter failure", StringComparison.Ordinal))
            {
                return new(pair.References, error.GetType().FullName + ": " + error.Message);
            }
            throw new InvalidOperationException("Expected synthetic getter failure.");
        }
        ValidateReflection(pair.Author, options, includeFields: mode != "default");
        return new(pair.References, null);
    }

    private static JsonSerializerOptions NewReflectionOptions(DefaultJsonTypeInfoResolver resolver) =>
        new() { IncludeFields = true, TypeInfoResolver = resolver };

    private static void ValidateReflection(object author, JsonSerializerOptions options, bool includeFields)
    {
        var json = JsonSerializer.Serialize(author, author.GetType(), options);
        using var document = JsonDocument.Parse(json);
        if (includeFields)
            Check(document.RootElement.GetProperty("Value").GetInt32() == ReadField<int>(author, "Value") &&
                document.RootElement.GetProperty("Peer").GetProperty("Value").GetInt32() == ReadField<int>(author, "Value") + 100,
                "Reflection serializer did not traverse both collectible DTOs.");
        else Check(document.RootElement.GetProperty("Number").GetInt32() == ReadField<int>(author, "Value") &&
            document.RootElement.GetProperty("Link").GetProperty("Number").GetInt32() == ReadField<int>(author, "Value") + 100,
            "Default serializer did not traverse both collectible DTOs.");
    }

    private sealed class Pair : IDisposable
    {
        private readonly AssemblyLoadContext frameworkContext;
        private readonly AssemblyLoadContext authorContext;
        internal object Framework { get; }
        internal object Author { get; }
        internal PairReferences References { get; }

        private Pair(AssemblyLoadContext framework, AssemblyLoadContext author, object frameworkObject, object authorObject)
        {
            frameworkContext = framework;
            authorContext = author;
            Framework = frameworkObject;
            Author = authorObject;
            References = new(new(framework, frameworkObject.GetType()), new(author, authorObject.GetType()));
        }

        internal static Pair Open(string label, int value, bool throwing = false)
        {
            var framework = new AssemblyLoadContext("Serialization.Framework:" + label, isCollectible: true);
            var author = new AssemblyLoadContext("Serialization.Author:" + label, isCollectible: true);
            try
            {
                var bytes = File.ReadAllBytes(typeof(SerializationOwnershipTests).Assembly.Location);
                using var frameworkImage = new MemoryStream(bytes, writable: false);
                using var authorImage = new MemoryStream(bytes, writable: false);
                var frameworkType = framework.LoadFromStream(frameworkImage).GetType(RecordName, throwOnError: true)!;
                var authorType = author.LoadFromStream(authorImage).GetType(throwing
                    ? "RuneCLR.SerializationFixtures.ThrowingRecord" : RecordName, throwOnError: true)!;
                Check(frameworkType != authorType && frameworkType.Assembly.IsCollectible && authorType.Assembly.IsCollectible,
                    "Fixture roles must have independent collectible type identities.");
                var peer = Activator.CreateInstance(frameworkType)!;
                var record = Activator.CreateInstance(authorType)!;
                frameworkType.GetField("Value")!.SetValue(peer, value + 100);
                frameworkType.GetField("Label")!.SetValue(peer, label + "-peer");
                authorType.GetField("Value")!.SetValue(record, value);
                authorType.GetField("Label")!.SetValue(record, label);
                authorType.GetField("Peer")!.SetValue(record, peer);
                return new(framework, author, peer, record);
            }
            catch { author.Unload(); framework.Unload(); throw; }
        }

        public void Dispose() { authorContext.Unload(); frameworkContext.Unload(); }
    }

    private sealed class RoleReferences(AssemblyLoadContext context, Type type)
    {
        internal WeakReference Context { get; } = new(context, trackResurrection: true);
        internal WeakReference Assembly { get; } = new(type.Assembly, trackResurrection: true);
        internal WeakReference Type { get; } = new(type, trackResurrection: true);
        internal bool Collected => !Context.IsAlive && !Assembly.IsAlive && !Type.IsAlive;
        internal RoleSnapshot Snapshot() => new(Context.IsAlive, Assembly.IsAlive, Type.IsAlive);
    }

    private sealed record PairReferences(RoleReferences Framework, RoleReferences Author)
    {
        internal bool Collected => Framework.Collected && Author.Collected;
        internal PairSnapshot Snapshot() => new(Framework.Snapshot(), Author.Snapshot());
    }
    private sealed record RoleSnapshot(bool ContextAlive, bool AssemblyAlive, bool TypeAlive);
    private sealed record PairSnapshot(RoleSnapshot Framework, RoleSnapshot Author)
    {
        public bool Collected => !Framework.ContextAlive && !Framework.AssemblyAlive && !Framework.TypeAlive &&
            !Author.ContextAlive && !Author.AssemblyAlive && !Author.TypeAlive;
    }
    private sealed record Retired(PairReferences References, byte[] Payload);
    private sealed record ReflectionRetired(PairReferences References, string? ErrorText);
    private sealed record ProbeResult(PairSnapshot WhileHeld, PairSnapshot AfterRelease, PairReferences Foreign,
        bool FunctionalOracle, string? ErrorText, int HeldCycles, int ReleasedCycles);
    private sealed class Lease { internal object? Value; }
    private enum RootKind { Options, Resolver, TypeInfo, Instance }
    private sealed class OwnedResolver(JsonTypeInfo owned) : IJsonTypeInfoResolver
    {
        public JsonTypeInfo? GetTypeInfo(Type type, JsonSerializerOptions options) => type == owned.Type ? owned : null;
    }
    private sealed class InvalidRecord { public string Value = "not an int"; }
    private static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
    private static void Throws<T>(Action action) where T : Exception
    {
        try { action(); } catch (T) { return; }
        throw new InvalidOperationException("Expected " + typeof(T).Name);
    }
}
