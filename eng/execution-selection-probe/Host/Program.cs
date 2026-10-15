using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using SelectionProbe.Contract;

// Keep managed result markers separate from buffered native dump stdout.
Console.SetOut(Console.Error);
if (args.Length != 2 && args.Length != 4)
    throw new ArgumentException("Expected payload directory, evidence directory, and optional refusal mode/directory.");
string payloadDirectory = Path.GetFullPath(args[0]);
string evidenceDirectory = Path.GetFullPath(args[1]);
Directory.CreateDirectory(evidenceDirectory);
Console.WriteLine($"RUNTIME {RuntimeInformation.FrameworkDescription}");
SessionContextFactory.Initialize(evidenceDirectory);
if (args.Length == 4)
{
    if (args[2] == "--inline")
    {
        for (int session = 1; session <= 20; session++)
        {
            var inline = InlineFrame(Path.Combine(Path.GetFullPath(args[3]), "SelectionProbe.Inline.dll"), session == 1 ? evidenceDirectory : null);
            if (inline.First != 53 || inline.Warm != 38) throw new InvalidOperationException("Native generic callback returned wrong values.");
            for (int pass = 0; pass < 12 && inline.Context.IsAlive; pass++)
            {
                GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            }
            if (inline.Context.IsAlive) throw new InvalidOperationException("Native generic callback context retained.");
            Console.WriteLine($"PASS inline-session={session} first=53 warm=38 trusted-definition=true collectible-argument=true collected=true");
        }
        Console.WriteLine("20/20 native generic caller sessions passed; 20/20 contexts collected");
        return 0;
    }
    if (args[2] == "--bridges")
    {
        for (int session = 1; session <= 20; session++)
        {
            var bridge = BoxedFrame(Path.Combine(Path.GetFullPath(args[3]), "SelectionProbe.Boxed.dll"), session == 1 ? evidenceDirectory : null);
            if (bridge.First != 17 || bridge.Warm != 17 || bridge.Delegate != 17 || bridge.Starts != 1 || bridge.Instances != 1)
                throw new InvalidOperationException("Boxed bridge body returned wrong values or retained static state.");
            for (int pass = 0; pass < 12 && bridge.Context.IsAlive; pass++)
            {
                GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            }
            if (bridge.Context.IsAlive) throw new InvalidOperationException("Boxed bridge context retained.");
            Console.WriteLine($"PASS bridge-session={session} interface=17 warm-interface=17 closed-delegate=17 starts=1 instances=1 collected=true");
        }
        Console.WriteLine("20/20 boxed bridge sessions passed; 20/20 contexts collected");
        return 0;
    }
    string refusalAssembly = Path.Combine(Path.GetFullPath(args[3]), "SelectionProbe.Refusal.dll");
    if (args[2] == "--refusal-fallback")
    {
        // Same body as the collectible refusal test, but a trusted unmarked
        // default-context load; mode 1 must actually attempt interpretation.
        Assembly assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(refusalAssembly);
        var method = assembly.GetType("SelectionUGC.Refusal.Entry", true)!.GetMethod("Reject")!;
        int result = method.CreateDelegate<Func<int>>()();
        if (result != 73) throw new InvalidOperationException("Unmarked fallback body returned wrong value.");
        Console.WriteLine($"PASS unmarked-refusal value={result} module={assembly.ManifestModule.ModuleVersionId} token=0x{method.MetadataToken:x8}");
        return 0;
    }
    if (args[2] != "--refusal-required") throw new ArgumentException("Unknown optional refusal mode.");
    var refusal = RefusalFrame(refusalAssembly);
    for (int pass = 0; pass < 12 && refusal.Context.IsAlive; pass++)
    {
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
    }
    if (refusal.Context.IsAlive) throw new InvalidOperationException("Refused context retained.");
    Console.WriteLine($"PASS required-refusal exception={refusal.ExceptionType} collected=true");
    // Continue the unchanged normal-session loop in this process: compiler
    // refusal must not poison the next independent collectible session.
}
var expected = new ProbeResult(1, 1, 7, 12, 1, 19, 11, 13, 17, 1, 1, 1, 30, 38, 1, 41, 42);
for (int session = 1; session <= 20; session++)
{
    var outcome = RunFrame(payloadDirectory, session == 1 ? evidenceDirectory : null);
    if (outcome.Result != expected)
        throw new InvalidOperationException($"Session {session}: values differ: {outcome.Result}");
    for (int pass = 0; pass < 12 && outcome.Context.IsAlive; pass++)
    {
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
    }
    if (outcome.Context.IsAlive) throw new InvalidOperationException($"Session {session} context retained.");
    Console.WriteLine($"PASS session={session} values={JsonSerializer.Serialize(outcome.Result)} collected=true");
}
Console.WriteLine("20/20 execution-selection sessions passed; 20/20 contexts collected");
return 0;

[MethodImpl(MethodImplOptions.NoInlining)]
static (WeakReference Context, int First, int Warm) InlineFrame(string path, string? evidence)
{
    var context = SessionContextFactory.Create(Path.GetDirectoryName(path)!);
    var weak = new WeakReference(context);
    try
    {
        Assembly assembly = SessionContextFactory.Load(context, path);
        Type type = assembly.GetType("SelectionUGC.Inline.Entry", true)!;
        MethodInfo definition = typeof(TrustedInlineCaller).GetMethod("NativeInlineCall")!;
        if (definition.Module.Assembly.IsCollectible || !type.Assembly.IsCollectible)
            throw new InvalidOperationException("Generic callback ownership differs from fixture topology.");
        MethodInfo constructed = definition.MakeGenericMethod(type);
        if (constructed.Module != definition.Module) throw new InvalidOperationException("Constructed callback lost trusted definition module.");
        var callback = constructed.CreateDelegate<Func<int, int>>();
        int first = callback(22);
        int warm = callback(7);
        if (evidence is not null)
        {
            MethodInfo body = type.GetMethod("ReadInline")!;
            var inventory = new { trustedAssembly = definition.Module.Assembly.GetName().Name,
                trustedModule = definition.Module.ModuleVersionId.ToString(), definition = definition.ToString(),
                trustedDefinitionToken = $"0x{definition.MetadataToken:x8}", constructed = constructed.ToString(),
                collectibleAssembly = assembly.GetName().Name, collectibleModule = assembly.ManifestModule.ModuleVersionId.ToString(),
                collectibleType = type.FullName, collectibleMethod = body.Name, bodyToken = $"0x{body.MetadataToken:x8}" };
            File.WriteAllText(Path.Combine(evidence, "method-inventory.json"), JsonSerializer.Serialize(inventory, new JsonSerializerOptions { WriteIndented = true }));
        }
        return (weak, first, warm);
    }
    finally { SessionContextFactory.Check(context, "before-unload"); context.Unload(); SessionContextFactory.AssertUnloadedQuery(context); }
}

[MethodImpl(MethodImplOptions.NoInlining)]
static (WeakReference Context, int First, int Warm, int Delegate, int Starts, int Instances) BoxedFrame(string path, string? evidence)
{
    var context = SessionContextFactory.Create(Path.GetDirectoryName(path)!);
    var weak = new WeakReference(context);
    try
    {
        Assembly assembly = SessionContextFactory.Load(context, path);
        object boxed = Activator.CreateInstance(assembly.GetType("SelectionUGC.Boxed.Entry", true)!)!;
        var probe = (IBoxProbe)boxed;
        int first = probe.Read();
        int warm = probe.Read();
        var callback = boxed.GetType().GetMethod("Read")!.CreateDelegate<Func<int>>(boxed);
        int delegated = callback();
        if (evidence is not null)
        {
            Type type = boxed.GetType();
            var flags = BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
            var inventory = type.GetMethods(flags).Cast<MethodBase>().Concat(type.GetConstructors(flags))
                .OrderBy(method => method.MetadataToken).Select(method => new { assembly = assembly.GetName().Name,
                    module = assembly.ManifestModule.ModuleVersionId.ToString(), type = type.FullName, method = method.Name,
                    token = $"0x{method.MetadataToken:x8}", signature = method.ToString() }).ToArray();
            File.WriteAllText(Path.Combine(evidence, "method-inventory.json"), JsonSerializer.Serialize(inventory, new JsonSerializerOptions { WriteIndented = true }));
        }
        return (weak, first, warm, delegated, probe.Starts, probe.Instances);
    }
    finally { SessionContextFactory.Check(context, "before-unload"); context.Unload(); SessionContextFactory.AssertUnloadedQuery(context); }
}

[MethodImpl(MethodImplOptions.NoInlining)]
static (WeakReference Context, string ExceptionType) RefusalFrame(string path)
{
    var context = SessionContextFactory.Create(Path.GetDirectoryName(path)!);
    var weak = new WeakReference(context);
    try
    {
        Assembly assembly = SessionContextFactory.Load(context, path);
        var method = assembly.GetType("SelectionUGC.Refusal.Entry", true)!.GetMethod("Reject")!;
        var body = method.CreateDelegate<Func<int>>();
        try { body(); }
        catch (NotSupportedException exception) { return (weak, exception.GetType().FullName!); }
        throw new InvalidOperationException("Required interpreter refusal executed instead of rejecting.");
    }
    finally { SessionContextFactory.Check(context, "before-unload"); context.Unload(); SessionContextFactory.AssertUnloadedQuery(context); }
}

[MethodImpl(MethodImplOptions.NoInlining)]
static (ProbeResult Result, WeakReference Context) RunFrame(string directory, string? evidence)
{
    var context = SessionContextFactory.Create(directory);
    var weak = new WeakReference(context);
    try
    {
        Assembly payload = SessionContextFactory.Load(context, Path.Combine(directory, "SelectionProbe.Payload.dll"));
        var probe = (IProbe)Activator.CreateInstance(payload.GetType("SelectionUGC.Payload.Entry", true)!)!;
        SessionContextFactory.CheckLatePrivate(context, beforeRun: true);
        ProbeResult result = probe.Run();
        SessionContextFactory.CheckLatePrivate(context, beforeRun: false);
        if (evidence is not null)
        {
            // Materialize only strings/integers; reflection metadata stays in this frame.
            var inventory = context.Assemblies.OrderBy(a => a.GetName().Name).SelectMany(a =>
                a.GetTypes().OrderBy(t => t.FullName).SelectMany(t =>
                    t.GetMethods(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance)
                        .Cast<MethodBase>().Concat(t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance))
                        .OrderBy(m => m.MetadataToken).Select(m => new { assembly = a.GetName().Name,
                            module = a.ManifestModule.ModuleVersionId.ToString(), type = t.FullName, method = m.Name,
                            token = $"0x{m.MetadataToken:x8}", signature = m.ToString() }))).ToArray();
            File.WriteAllText(Path.Combine(evidence, "method-inventory.json"), JsonSerializer.Serialize(inventory, new JsonSerializerOptions { WriteIndented = true }));
        }
        return (result, weak);
    }
    finally { SessionContextFactory.Check(context, "before-unload"); context.Unload(); SessionContextFactory.AssertUnloadedQuery(context); }
}

sealed class ProbeContext(string directory) : AssemblyLoadContext(isCollectible: true)
{
    protected override Assembly? Load(AssemblyName name) => SessionContextFactory.Resolve(this, directory, name);
}

public static class TrustedInlineCaller
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int NativeInlineCall<T>(int value) where T : struct, IStaticProbe => T.ReadInline(value);
}



