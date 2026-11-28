using System.Reflection;
using System.Collections;
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
        yield return ("Default-defined generic pairs, arrays, lists and nests copy bounded fields and retire", BoundedGenericShapes);
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

    private static void BoundedGenericShapes()
    {
        foreach (var shape in new[] { "pair", "array", "list", "nest" })
        {
            var retired = RetireGenericBounded(shape);
            using var document = JsonDocument.Parse(retired.Payload);
            Check(document.RootElement.GetProperty("left").GetInt32() == 123 &&
                document.RootElement.GetProperty("right").GetInt32() == 23, "Cross-domain scalar sentinels changed.");
            RequireCollected(retired.References);
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Retired RetireGenericBounded(string shape)
    {
        using var pair = Pair.Open("generic", 23);
        var graph = CreateGraph(pair, shape);
        return new(pair.References with { Envelope = new(graph.GetType(), trackResurrection: true) }, WriteGraphBounded(graph));
    }

    private static object CreateGraph(Pair pair, string shape)
    {
        var type = typeof(RuneCLR.SerializationFixtures.Pair<,>).MakeGenericType(pair.Framework.GetType(), pair.Author.GetType());
        Check(type.IsCollectible && !type.Assembly.IsCollectible &&
            AssemblyLoadContext.GetLoadContext(type.Assembly) == AssemblyLoadContext.Default,
            "The closed cross-domain type must be collectible despite its Default defining assembly.");
        object graph = Activator.CreateInstance(type)!;
        type.GetField("Left")!.SetValue(graph, pair.Framework);
        type.GetField("Right")!.SetValue(graph, pair.Author);
        if (shape == "array")
        {
            var array = Array.CreateInstance(type, 1);
            array.SetValue(graph, 0);
            graph = array;
        }
        else if (shape == "list")
        {
            var list = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(type))!;
            list.Add(graph);
            graph = list;
        }
        else if (shape == "nest")
            for (var depth = 0; depth < 4; depth++)
            {
                var nestType = typeof(RuneCLR.SerializationFixtures.Nest<>).MakeGenericType(graph.GetType());
                var nest = Activator.CreateInstance(nestType)!;
                nestType.GetField("Value")!.SetValue(nest, graph);
                graph = nest;
            }
        Check(graph.GetType().IsCollectible && !graph.GetType().Assembly.IsCollectible,
            "Every selected generic/array/collection envelope must preserve the collectible type boundary.");
        return graph;
    }

    private static (object Left, object Right) GraphValues(object graph)
    {
        if (graph is Array array && array.Length == 1) graph = array.GetValue(0)!;
        else if (graph is IList list && list.Count == 1) graph = list[0]!;
        for (var depth = 0; depth < 4 && graph.GetType().IsGenericType &&
            graph.GetType().GetGenericTypeDefinition() == typeof(RuneCLR.SerializationFixtures.Nest<>); depth++)
            graph = graph.GetType().GetField("Value")!.GetValue(graph)!;
        var type = graph.GetType();
        if (!type.IsGenericType || type.GetGenericTypeDefinition() != typeof(RuneCLR.SerializationFixtures.Pair<,>))
            throw new InvalidDataException("Unsupported bounded generic envelope.");
        return (type.GetField("Left")!.GetValue(graph)!, type.GetField("Right")!.GetValue(graph)!);
    }

    private static byte[] WriteGraphBounded(object graph)
    {
        var (left, right) = GraphValues(graph);
        using var output = new MemoryStream();
        using (var writer = new Utf8JsonWriter(output))
        {
            writer.WriteStartObject();
            writer.WriteNumber("left", ReadField<int>(left, "Value"));
            writer.WriteNumber("right", ReadField<int>(right, "Value"));
            writer.WriteEndObject();
        }
        return output.ToArray();
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
    internal static int Probe(string mode, string shape = "pair")
    {
        if (mode is not ("none" or "bounded" or "owned" or "held" or "equivalent" or "default" or "failure") ||
            shape is not ("pair" or "array" or "list" or "nest"))
        {
            Console.Error.WriteLine("Serialization probe mode: none|bounded|owned|held|equivalent|default|failure; shape: pair|array|list|nest");
            return 2;
        }
        var result = RunProbe(mode, shape);
        var foreignCycles = Observe(result.Foreign);
        var foreignCollected = result.Foreign.Collected;
        // All lifetime snapshots are complete before printing with STJ. No accessor
        // request is allowed to drive cache expiry during the collection observations.
        var foreignSnapshot = result.Foreign.Snapshot();
        var foreignMetadata = result.ForeignMetadata?.Snapshot();
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            probeSchema = 2, mode, shape, runtime = RuntimeInformation.FrameworkDescription,
            serializer = typeof(JsonSerializer).Assembly.GetName().Version?.ToString(),
            serializerMvid = typeof(JsonSerializer).Assembly.ManifestModule.ModuleVersionId,
            result.BeforeRelease, result.AfterRelease, foreign = foreignSnapshot,
            result.MetadataBefore, result.MetadataAfter, foreignMetadata,
            result.FunctionalOracle, result.ErrorText, result.CacheIdentityVerified, result.SharingVerified,
            heldRoot = mode == "held" ? "cached-type-info" : mode is "default" or "equivalent" ? "Default-options-context" : "none",
            observation = result.AfterRelease.Collected && foreignCollected ? "collected" : "retained-after-observation",
            result.HeldCycles, result.ReleasedCycles, foreignCycles,
            maximumDiagnosticCycles = ObservationRounds
        }));
        // 3 is an incomplete collection observation, not proof of a leak or a passing test.
        return result.AfterRelease.Collected && foreignCollected ? 0 : 3;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static ProbeResult RunProbe(string mode, string shape)
    {
        using var foreign = Pair.Open("foreign", 7);
        var foreignGraph = CreateGraph(foreign, shape);
        var foreignReferences = foreign.References with { Envelope = new(foreignGraph.GetType(), trackResurrection: true) };
        var foreignOptions = NewReflectionOptions();
        MetadataReferences? foreignMetadata = null;
        if (mode is not ("none" or "bounded"))
        {
            ValidateReflection(foreignGraph, foreignOptions);
            foreignMetadata = CachedMetadata(foreignGraph.GetType(), foreignOptions).References;
        }
        var lease = new Lease();
        var retired = RetireReflection(mode, shape, lease);
        try
        {
            // The old contexts have requested Unload. Verify the foreign session's
            // non-default round-trip values and exact types BEFORE the first GC phase.
            if (mode is "none" or "bounded") AssertPayload(WriteBounded(foreign.Author), "foreign", 7);
            else ValidateReflection(foreignGraph, foreignOptions);
            if (mode is "default" or "equivalent") _ = WarmDefault();
            var heldCycles = Observe(retired.References);
            var held = retired.References.Snapshot();
            var metadataBefore = retired.Metadata?.Snapshot();
            if (mode is "held" or "default" or "equivalent") RequireBothAlive(held);
            Release(lease);
            var releasedCycles = Observe(retired.References);
            var released = retired.References.Snapshot();
            var metadataAfter = retired.Metadata?.Snapshot();
            if (mode is "default" or "equivalent") RequireBothAlive(released);
            GC.KeepAlive(foreignOptions);
            GC.KeepAlive(foreignGraph);
            return new(held, released, foreignReferences, foreignMetadata, metadataBefore, metadataAfter,
                true, retired.ErrorText, retired.CacheIdentityVerified, retired.SharingVerified, heldCycles, releasedCycles);
        }
        finally { Release(lease); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static ReflectionRetired RetireReflection(string mode, string shape, Lease lease)
    {
        using var pair = Pair.Open("retired", 11, throwing: mode == "failure");
        var graph = CreateGraph(pair, shape);
        var references = pair.References with { Envelope = new(graph.GetType(), trackResurrection: true) };
        if (mode == "none") return new(references, null, null, false, false);
        if (mode == "bounded")
        {
            using var snapshot = JsonDocument.Parse(WriteGraphBounded(graph));
            Check(snapshot.RootElement.GetProperty("left").GetInt32() == 111 &&
                snapshot.RootElement.GetProperty("right").GetInt32() == 11, "Bounded generic oracle.");
            return new(references, null, null, false, false);
        }
        var sharingVerified = false;
        if (mode is "default" or "equivalent") _ = WarmDefault();
        var options = mode switch
        {
            "default" => JsonSerializerOptions.Default,
            "equivalent" => new JsonSerializerOptions(JsonSerializerOptions.Default),
            _ => NewReflectionOptions()
        };
        if (mode == "equivalent")
        {
            options.MakeReadOnly();
            sharingVerified = ReferenceEquals(options.GetTypeInfo(typeof(RuneCLR.SerializationFixtures.StableRecord)),
                JsonSerializerOptions.Default.GetTypeInfo(typeof(RuneCLR.SerializationFixtures.StableRecord)));
            Check(sharingVerified, "Equivalent options must demonstrably share cached metadata with the real Default.");
        }
        var errorText = mode == "failure" ? SerializeFailure(graph, options) : null;
        if (mode != "failure") ValidateReflection(graph, options);
        var cached = CachedMetadata(graph.GetType(), options);
        if (mode == "held") lease.Value = cached.Info;
        if (mode is "default" or "equivalent") _ = WarmDefault();
        return new(references, errorText, cached.References, true, sharingVerified);
    }

    private static JsonSerializerOptions NewReflectionOptions() => new() { TypeInfoResolver = new DefaultJsonTypeInfoResolver() };

    private static (JsonTypeInfo Info, MetadataReferences References) CachedMetadata(Type type, JsonSerializerOptions options)
    {
        Check(options.IsReadOnly, "Capture cached metadata only after serialization has frozen the options.");
        var info = options.GetTypeInfo(type);
        Check(ReferenceEquals(info, options.GetTypeInfo(type)), "Repeated frozen-options requests must return the cached type info.");
        return (info, new(new(options), new(options.TypeInfoResolver!), new(info)));
    }

    private static JsonTypeInfo WarmDefault()
    {
        var stable = new RuneCLR.SerializationFixtures.StableRecord { Value = 73 };
        var json = JsonSerializer.Serialize(stable, JsonSerializerOptions.Default);
        Check(JsonSerializer.Deserialize<RuneCLR.SerializationFixtures.StableRecord>(json, JsonSerializerOptions.Default)!.Value == 73,
            "Stable Default metadata warm-up oracle.");
        return JsonSerializerOptions.Default.GetTypeInfo(typeof(RuneCLR.SerializationFixtures.StableRecord));
    }

    private static void ValidateReflection(object graph, JsonSerializerOptions options)
    {
        var json = JsonSerializer.Serialize(graph, graph.GetType(), options);
        var copy = JsonSerializer.Deserialize(json, graph.GetType(), options)!;
        Check(copy.GetType() == graph.GetType(), "Round-trip envelope type identity changed.");
        var original = GraphValues(graph);
        var restored = GraphValues(copy);
        Check(restored.Left.GetType() == original.Left.GetType() && restored.Right.GetType() == original.Right.GetType() &&
            ReadField<int>(restored.Left, "Value") == ReadField<int>(original.Left, "Value") &&
            ReadField<int>(restored.Right, "Value") == ReadField<int>(original.Right, "Value") &&
            ReadField<int>(restored.Left, "Value") != ReadField<int>(restored.Right, "Value"),
            "Serializer must restore both actual collectible types and their distinct non-default sentinels.");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static string SerializeFailure(object graph, JsonSerializerOptions options)
    {
        try { _ = JsonSerializer.Serialize(graph, graph.GetType(), options); }
        catch (Exception error) when (error.Message.Contains("synthetic serialization getter failure", StringComparison.Ordinal))
        { return error.GetType().FullName + ": " + error.Message; }
        throw new InvalidOperationException("Expected synthetic getter failure.");
    }

    private static void RequireBothAlive(PairSnapshot snapshot)
    {
        Check(snapshot.Framework.ContextAlive && snapshot.Framework.AssemblyAlive && snapshot.Framework.TypeAlive &&
            snapshot.Author.ContextAlive && snapshot.Author.AssemblyAlive && snapshot.Author.TypeAlive && snapshot.EnvelopeTypeAlive == true,
            "The explicit held/Default control must retain every context/type/assembly and the cross-domain envelope.");
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

    private sealed record PairReferences(RoleReferences Framework, RoleReferences Author, WeakReference? Envelope = null)
    {
        internal bool Collected => Framework.Collected && Author.Collected && Envelope?.IsAlive != true;
        internal PairSnapshot Snapshot() => new(Framework.Snapshot(), Author.Snapshot(), Envelope?.IsAlive);
    }
    private sealed record RoleSnapshot(bool ContextAlive, bool AssemblyAlive, bool TypeAlive);
    private sealed record PairSnapshot(RoleSnapshot Framework, RoleSnapshot Author, bool? EnvelopeTypeAlive)
    {
        public bool Collected => !Framework.ContextAlive && !Framework.AssemblyAlive && !Framework.TypeAlive &&
            !Author.ContextAlive && !Author.AssemblyAlive && !Author.TypeAlive && EnvelopeTypeAlive != true;
    }
    private sealed record Retired(PairReferences References, byte[] Payload);
    private sealed record ReflectionRetired(PairReferences References, string? ErrorText, MetadataReferences? Metadata,
        bool CacheIdentityVerified, bool SharingVerified);
    private sealed record MetadataReferences(WeakReference Options, WeakReference Resolver, WeakReference Info)
    {
        internal MetadataSnapshot Snapshot() => new(Options.IsAlive, Resolver.IsAlive, Info.IsAlive);
    }
    private sealed record MetadataSnapshot(bool OptionsAlive, bool ResolverAlive, bool TypeInfoAlive);
    private sealed record ProbeResult(PairSnapshot BeforeRelease, PairSnapshot AfterRelease, PairReferences Foreign,
        MetadataReferences? ForeignMetadata, MetadataSnapshot? MetadataBefore, MetadataSnapshot? MetadataAfter,
        bool FunctionalOracle, string? ErrorText, bool CacheIdentityVerified, bool SharingVerified, int HeldCycles, int ReleasedCycles);
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
