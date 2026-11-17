using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.GroupedHost.Fixtures;
using RuneCLR.GroupedHost.Tests;
using RuneCLR.Packages;
using RuneCLR.Runtime;

var mode = args.Length == 0 ? "" : args[0];
// Primary runs use the real trusted framework image (with the kernel32 DllImport). The portable
// framework is a clearly-labelled diagnostic variant and must be requested explicitly.
FixtureMode.PortableFramework = args.Contains("--portable", StringComparer.Ordinal);
if (mode.Length == 0)
{
    Usage();
    return 2;
}

switch (mode)
{
    case "--stock-negative":
        return StockNegative();
    case "--positive":
        return Positive();
    case "--origin-negative":
        return OriginNegative();
    case "--callback-policy":
        return CallbackPolicy();
    case "--dynamic-rejected":
        return RunGuarded("dynamic-rejected", DynamicRejected);
    case "--unload-retry":
        return RunGuarded("unload-retry", UnloadRetry);
    case "--framework-copy":
        return RunGuarded("framework-copy", FrameworkCopy);
    case "--rollback":
        return RunGuarded("rollback", Rollback);
    case "--policy-negative":
        return PolicyNegative();
    case "--diagnose-prewarm":
        return DiagnosePrewarm();
    case "--positive-prewarm":
        return RunPrewarmThenPositive();
    case "--runtime-check":
        return RuntimeCheck();
    case "--rejected-author":
        FixtureMode.PortableFramework = false;
        Console.WriteLine(FrameworkRole());
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
        PrepareFixtureOverlay(FixtureMode.PortableFramework);
        return RunSingle(RejectedAuthor, "Author.NativeRejected is rejected at the author admission phase");
    case "--framework-native":
        return FrameworkNative();
    case "--probe-entry":
        return ProbeEntry();
    case "--method-witness":
        return MethodWitness.Run(fixtureOnly: false, jsonlPath: Environment.GetEnvironmentVariable("GROUPED_WITNESS_JSONL"));
    case "--method-witness-fixture":
        return MethodWitness.Run(fixtureOnly: true, jsonlPath: Environment.GetEnvironmentVariable("GROUPED_WITNESS_JSONL"));
    case "--policy-audit":
        return PolicyAudit();
    case "--dump-refs":
        return DumpReferences(args);
    default:
        Console.Error.WriteLine("Unknown mode: " + mode);
        Usage();
        return 2;
}

static void Usage() => Console.Error.WriteLine(
    "Usage: RuneCLR.GroupedHost.Tests --stock-negative | --positive | --framework-native | " +
    "--probe-entry | --policy-audit | --dump-refs <assembly.dll>");

// ---------------------------------------------------------------------------------------------
// Stock runtime negative controller. A clean rejection is the expected outcome here; it is not a
// grouped positive PASS and must never be counted as one.
// ---------------------------------------------------------------------------------------------
static int StockNegative()
{
    Console.WriteLine(FrameworkRole());
    PrepareFixtureOverlay(FixtureMode.PortableFramework);
    var failures = 0;
    foreach (var switchOn in new[] { false, true })
    {
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", switchOn);
        var label = switchOn ? "policy switch on, no private CoreLib/runtime support" : "policy switch off";
        var host = new TestHost();
        try
        {
            _ = GroupedHostSession.Open(Options("author-a"), host);
            Console.Error.WriteLine($"FAIL stock negative ({label}): Open succeeded on the stock runtime; no grouped fallback is allowed.");
            failures++;
        }
        catch (PlatformNotSupportedException error)
        {
            // The grouped preflight now binds the required-interpreter bridge and the origin-scan
            // capability before any context exists, so the stock runtime may report any of these
            // clean fail-closed rejections regardless of the reflection-policy switch.
            var clean = error.Message.Contains("CoreLib", StringComparison.Ordinal) ||
                        error.Message.Contains("experiment is disabled", StringComparison.Ordinal) ||
                        error.Message.Contains("origin-scan capability is unavailable", StringComparison.Ordinal);
            if (!clean)
            {
                Console.Error.WriteLine($"FAIL stock negative ({label}): unexpected rejection: {error.Message}");
                failures++;
            }
            else if (host.Records.Count != 0 || host.RetainedCount != 0)
            {
                Console.Error.WriteLine($"FAIL stock negative ({label}): host saw {host.Records.Count} record(s); code ran before rejection.");
                failures++;
            }
            else
            {
                Console.WriteLine($"PASS stock negative ({label}): rejected before author entry; {error.Message}");
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"FAIL stock negative ({label}): unexpected {error}");
            failures++;
        }
    }

    Console.WriteLine($"stock-negative: {2 - failures}/2 expected rejections observed (negative control, not a grouped PASS)");
    return failures == 0 ? 0 : 1;
}

// ---------------------------------------------------------------------------------------------
// Private runtime positive suite.
// ---------------------------------------------------------------------------------------------
static int Positive()
{
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);
    var notRun = 0;

    var tests = new List<(string Name, Action Run)>
    {
        ("A/B/A groups reset framework and author statics and share one framework per group", AbaGroups),
        ("Pending cleanup rejects entry, Close and pending Dispose; drain ack is required", PendingCleanup),
        ("Duplicate Close is idempotent and keeps the terminal ticket", DuplicateClose),
        ("Host-retained resolver assembly lease keeps the group alive until released", ResolverLease),
        ("Author.NativeRejected is rejected at the author admission phase", RejectedAuthor),
        ("Wrong-group cleanup token is rejected", WrongToken),
        ("Reentrant entry from a host callback is rejected and the group stays usable", ReentrantEntry),
        ("Framework and author exceptions retire cleanly and the next group succeeds", ExceptionThenNextGroup)
    };

    var failures = 0;
    foreach (var (name, run) in tests)
    {
        try
        {
            run();
            Console.WriteLine("PASS " + name);
        }
        catch (NotRunException error)
        {
            notRun++;
            Console.Error.WriteLine($"NOT-RUN {name}: {error.Message}");
        }
        catch (Exception error)
        {
            failures++;
            Console.Error.WriteLine($"FAIL {name}: {error}");
        }
    }

    GC.KeepAlive(Evidence.Retained);
    Console.WriteLine($"{tests.Count - failures - notRun} passed, {notRun} not-run, {failures} failed of {tests.Count}");
    return failures == 0 && notRun == 0 ? 0 : 1;
}

static void AbaGroups()
{
    var a1 = RunGroup("author-a", [1, 2]);
    var a1Tokens = AssertGroupShape(a1, "A", [1, 2]);
    var b1 = RunGroup("author-b", [1]);
    var b1Tokens = AssertGroupShape(b1, "B", [1]);
    var a2 = RunGroup("author-a", [3]);
    var a2Tokens = AssertGroupShape(a2, "A", [3]);

    var frameworkTokens = new[] { a1Tokens.Framework, b1Tokens.Framework, a2Tokens.Framework };
    Check(frameworkTokens.Distinct(StringComparer.Ordinal).Count() == 3,
        "each group must load a fresh framework instance token.");
    Check(a1Tokens.Author != a2Tokens.Author, "author statics must reset between groups with the same author variant.");
    Check(b1Tokens.Author.StartsWith("author-B-", StringComparison.Ordinal), "author B token missing its tag.");

    Evidence.Retained.Add(a1);
    Evidence.Retained.Add(b1);
    Evidence.Retained.Add(a2);
    WaitCollected(a1.Ticket, "A group 1");
    WaitCollected(b1.Ticket, "B group");
    WaitCollected(a2.Ticket, "A group 2");
}

static void PendingCleanup()
{
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    Check(session.InvokeAuthor(1) == 101, "the pre-cleanup entry must run normally.");
    var before = host.AuthorRecords;
    host.ReleaseRetained();

    var token = session.BeginCleanup();
    Check(ReferenceEquals(token, session.BeginCleanup()), "BeginCleanup must return the same pending token.");

    var entry = Catch<InvalidOperationException>(() => session.InvokeAuthor(2));
    Check(entry.Message.Contains("Entry is closed", StringComparison.Ordinal), "pending cleanup must reject author entry: " + entry.Message);
    var frameworkEntry = Catch<InvalidOperationException>(() => session.InvokeFramework());
    Check(frameworkEntry.Message.Contains("Entry is closed", StringComparison.Ordinal), "pending cleanup must reject framework entry: " + frameworkEntry.Message);
    var missingAck = Catch<InvalidOperationException>(() => session.CompleteCleanup(token));
    Check(missingAck.Message.Contains("Drain acknowledgement is required", StringComparison.Ordinal), "CompleteCleanup must require the drain ack: " + missingAck.Message);
    var close = Catch<InvalidOperationException>(() => session.Close());
    Check(close.Message.Contains("Close requires a completed cleanup", StringComparison.Ordinal), "Close must stay rejected while cleanup is incomplete: " + close.Message);
    var dispose = Catch<InvalidOperationException>(() => session.Dispose());
    Check(dispose.Message.Contains("Dispose requires a completed cleanup", StringComparison.Ordinal), "Dispose must stay rejected while cleanup is incomplete: " + dispose.Message);

    Check(!session.IsClosed, "rejected lifecycle calls must leave the group retryable.");
    Check(host.AuthorRecords == before, $"rejected entry must not execute author code ({before} -> {host.AuthorRecords}).");

    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    var ticket = session.Close();
    Check(ticket.FrameworkUnloadRequested && ticket.AuthorUnloadRequested && ticket.LeasesReleased,
        "the terminal ticket must report both unload requests and released leases.");
    Check(ticket.FrameworkUnloadFailure is null && ticket.AuthorUnloadFailure is null,
        "a clean Close must not report an unload failure: " + ticket.FrameworkUnloadFailure + "/" + ticket.AuthorUnloadFailure);
    WaitCollected(ticket, "pending-cleanup retry");
}

static void DuplicateClose()
{
    var evidence = RunGroup("author-a", [1]);
    var again = evidence.Session.Close();
    Check(ReferenceEquals(again.FrameworkContext, evidence.Ticket.FrameworkContext) &&
          ReferenceEquals(again.AuthorContext, evidence.Ticket.AuthorContext),
        "a duplicate Close must return the cached terminal ticket, not a new one.");
    Check(again.FrameworkUnloadRequested && again.AuthorUnloadRequested && again.LeasesReleased,
        "the cached ticket must stay terminal.");
    Evidence.Retained.Add(evidence);
    WaitCollected(again, "duplicate Close");
}

static void ResolverLease()
{
    var leases = new Dictionary<string, object>(StringComparer.Ordinal);
    var evidence = RunGroupWithHostLease("author-a", [1], leases);
    Check(leases.Count == 2, "the host lease must capture the framework load context and assembly.");

    for (var attempt = 0; attempt < 6 && !evidence.Ticket.FrameworkContext!.IsAlive; attempt++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Thread.Sleep(20);
    }

    Check(evidence.Ticket.FrameworkContext!.IsAlive,
        "negative control failed: a host-retained resolver lease must keep the framework context alive.");
    Check(evidence.Ticket.AuthorContext!.IsAlive,
        "the framework static callback must keep the author context alive while the framework lease is held.");

    leases.Clear();
    WaitCollected(evidence.Ticket, "resolver lease release");
}
static void RejectedAuthor()
{
    if (!PrivateRuntimeSurfacePresent())
        throw new NotRunException(
            "the grouped author-phase gates need the private runtime; the stock runtime fails the capability " +
            "preflight before the role catalogs, so it cannot show the admission-phase shape");

    // Gate A (framework provenance, real image): a grouped Open with the normal trusted framework and
    // a normal author must not fail in the framework catalog phase. A later failure (for example a
    // known entry-signature defect) still proves the trusted framework image was accepted.
    var provenance = ProbeFrameworkPhase();
    Console.WriteLine("gate A PASS: " + provenance);

    // Gate B: the rejected author image fails the strict author intake on its own direct P/Invoke.
    var rejectedImage = File.ReadAllBytes(Path.Combine(FixturesRoot(), "author-native-rejected", "RuneCLR.GroupedHost.Author.NativeRejected.dll"));
    var authorRejection = CatchAny(() => ManagedAssemblyInspector.Inspect(rejectedImage));
    Check(DescribeFailure(authorRejection).Contains("P/Invoke or InternalCall", StringComparison.Ordinal),
        "the author image must be rejected for its direct P/Invoke: " + DescribeFailure(authorRejection));
    Console.WriteLine("gate B PASS: rejected author image fails strict intake on its own P/Invoke");

    // Gate C: the same image is rejected during the author catalog phase of a real grouped Open, and
    // the message names the author image rather than the framework.
    var host = new TestHost();
    try
    {
        _ = GroupedHostSession.Open(
            Options("author-native-rejected", portableFramework: false,
                authorAssembly: "RuneCLR.GroupedHost.Author.NativeRejected.dll"),
            host);
        throw new InvalidOperationException("a direct author P/Invoke assembly was admitted.");
    }
    catch (InvalidDataException error)
    {
        var chain = DescribeFailure(error);
        Check(chain.Contains("RuneCLR.GroupedHost.Author.NativeRejected", StringComparison.Ordinal),
            "the grouped rejection must name the rejected author image, not the framework: " + chain);
        Check(chain.Contains("P/Invoke or InternalCall", StringComparison.Ordinal),
            "the grouped rejection must name the author P/Invoke: " + chain);
    }

    Check(host.Records.Count == 0 && host.RetainedCount == 0,
        "rejected author admission must not execute author code or install host roots.");
    Console.WriteLine("gate C PASS: grouped Open rejects in the author catalog phase with zero host records");
}

static string ProbeFrameworkPhase()
{
    var host = new TestHost();
    try
    {
        var session = GroupedHostSession.Open(Options("author-a", portableFramework: false), host);
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        WaitCollected(session.Close(), "framework provenance group");
        return "real trusted framework image opened and the empty group retired";
    }
    catch (InvalidDataException error) when (
        DescribeFailure(error).Contains("framework", StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "the framework catalog rejected the real trusted framework image: " + DescribeFailure(error));
    }
    catch (Exception error)
    {
        return "real trusted framework image passed the framework catalog; later failure recorded: " +
            DescribeFailure(error);
    }
}

static void WrongToken()
{
    var first = RunGroup("author-a", [1]);
    WaitCollected(first.Ticket, "wrong-token first group");

    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    var foreign = Catch<InvalidOperationException>(() => session.AcknowledgeCleanup(first.Token));
    Check(foreign.Message.Contains("does not belong", StringComparison.Ordinal),
        "a foreign cleanup token must be rejected: " + foreign.Message);
    var nullToken = Catch<ArgumentNullException>(() => session.AcknowledgeCleanup(null!));
    Check(nullToken.ParamName == "token", "a null cleanup token must be rejected before any state change.");

    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    WaitCollected(session.Close(), "wrong-token group");
}

static void ReentrantEntry()
{
    var host = new TestHost();
    GroupedHostSession? session = null;
    var reentered = false;
    host.Observer = message =>
    {
        if (reentered || !message.StartsWith("author:A:initial", StringComparison.Ordinal)) return;
        reentered = true;
        try
        {
            _ = session!.InvokeAuthor(7);
            host.ObserverError = null;
        }
        catch (Exception error)
        {
            host.ObserverError = error;
        }
    };

    session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    Check(session.InvokeAuthor(1) == 101, "the outer entry must complete normally.");
    Check(reentered, "the reentrant probe did not run.");
    var observerError = host.ObserverError;
    Check(observerError is not null && observerError.Message.Contains("Reentrant entry is not allowed", StringComparison.Ordinal),
        "the nested entry must be rejected: " + DescribeFailure(observerError));

    host.Observer = null;
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    WaitCollected(session.Close(), "reentrant group");
}

static void ExceptionThenNextGroup()
{
    var throwHost = new TestHost { Mode = "throw-init" };
    var throwSession = GroupedHostSession.Open(Options("author-a"), throwHost);
    var frameworkError = CatchAny(() => throwSession.InvokeFramework());
    AssertHostOwnedInvocationError(frameworkError, "RuneCLR.GroupedHost.Fixtures.FrameworkInitException", "framework init failure");
    Check(throwSession.InvokeAuthor(1) == 101, "the group must stay usable after a framework entry failure.");
    throwHost.ReleaseRetained();
    var throwToken = throwSession.BeginCleanup();
    throwSession.AcknowledgeCleanup(throwToken);
    throwSession.CompleteCleanup(throwToken);
    WaitCollected(throwSession.Close(), "framework exception group");

    var authorHost = new TestHost();
    var authorSession = GroupedHostSession.Open(Options("author-b"), authorHost);
    authorSession.InvokeFramework();
    var authorError = CatchAny(() => authorSession.InvokeAuthor(-1));
    AssertHostOwnedInvocationError(authorError, "RuneCLR.GroupedHost.Fixtures.AuthorCallbackException", "author callback failure");
    var authorInitError = CatchAny(() => authorSession.InvokeAuthor(-2));
    AssertHostOwnedInvocationError(authorInitError, "RuneCLR.GroupedHost.Fixtures.AuthorInitException", "author init failure");
    authorHost.ReleaseRetained();
    var authorToken = authorSession.BeginCleanup();
    authorSession.AcknowledgeCleanup(authorToken);
    authorSession.CompleteCleanup(authorToken);
    WaitCollected(authorSession.Close(), "author exception group");

    var next = RunGroup("author-a", [5]);
    var tokens = AssertGroupShape(next, "A", [5]);
    Check(tokens.Framework.StartsWith("fw-", StringComparison.Ordinal), "the next group must start with fresh framework statics.");
    WaitCollected(next.Ticket, "post-exception group");
}

// ---------------------------------------------------------------------------------------------
// Framework trusted-native probe. The trusted framework role must permit ordinary native interop;
// the author role must stay strict. Currently expected to be blocked by the framework intake.
// ---------------------------------------------------------------------------------------------
static int FrameworkNative()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);
    var host = new TestHost();
    try
    {
        var session = GroupedHostSession.Open(Options("author-a", portableFramework: false), host);
        session.InvokeFramework();
        var threadId = session.InvokeAuthor(-3);
        host.ReleaseRetained();
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        WaitCollected(session.Close(), "framework native group");
        Check(threadId > 0, "the trusted framework native bridge must return a real thread id.");
        Console.WriteLine($"PASS framework trusted native interop (threadId={threadId})");
        return 0;
    }
    catch (Exception error)
    {
        Console.WriteLine("BLOCKED framework trusted native interop: " + DescribeFailure(error));
        Console.WriteLine("expected: the trusted framework role permits ordinary native interop; the author role stays strict.");
        return 2;
    }
}

// ---------------------------------------------------------------------------------------------
// Preflight: the staged portable framework entry signature must match the contract type.
// ---------------------------------------------------------------------------------------------
static int ProbeEntry()
{
    var contract = typeof(IGroupedHostContract);
    var directory = Path.Combine(FixturesRoot(), FixtureMode.PortableFramework ? "framework-portable" : "framework");
    var image = File.ReadAllBytes(Path.Combine(directory, "RuneCLR.GroupedHost.Framework.dll"));
    var context = new AssemblyLoadContext("probe", isCollectible: true);
    try
    {
        var assembly = context.LoadFromStream(new MemoryStream(image));
        var type = assembly.GetType("RuneCLR.GroupedHost.Fixtures.FrameworkEntry", throwOnError: true)!;
        var method = type.GetMethod("Initialize", BindingFlags.Public | BindingFlags.Static)!;
        var parameter = method.GetParameters()[0].ParameterType;
        Console.WriteLine("contract:  " + contract.AssemblyQualifiedName +
            " alc=" + (AssemblyLoadContext.GetLoadContext(contract.Assembly)?.Name ?? "<default>"));
        Console.WriteLine("parameter: " + parameter.AssemblyQualifiedName +
            " alc=" + (AssemblyLoadContext.GetLoadContext(parameter.Assembly)?.Name ?? "<default>"));
        var same = ReferenceEquals(parameter, contract);
        Console.WriteLine("same=" + same);
        return same ? 0 : 1;
    }
    finally
    {
        context.Unload();
    }
}

// ---------------------------------------------------------------------------------------------
// Preflight: evaluate the fixture policy against every staged author member reference so the API
// policy is not a hidden blocker when the grouped host can finally open sessions.
// ---------------------------------------------------------------------------------------------
static int PolicyAudit()
{
    var contractIdentity = typeof(IGroupedHostContract).Assembly.FullName!;
    var frameworkIdentity = AssemblyName
        .GetAssemblyName(Path.Combine(FixturesRoot(), FixtureMode.PortableFramework ? "framework-portable" : "framework", "RuneCLR.GroupedHost.Framework.dll")).FullName!;
    var policy = GroupedHostFixturePolicy.Create(contractIdentity, frameworkIdentity);

    var total = 0;
    foreach (var folder in new[] { "author-a", "author-b" })
    {
        var path = Path.Combine(FixturesRoot(), folder, "RuneCLR.GroupedHost.Author.dll");
        var count = AuditAssembly(policy, path);
        total += count;
        Console.WriteLine(folder + ": denials=" + count);
    }

    Console.WriteLine("policy-audit denials=" + total);
    return total == 0 ? 0 : 1;
}

static int AuditAssembly(IApiAccessPolicy policy, string path)
{
    using var stream = File.OpenRead(path);
    using var pe = new PEReader(stream);
    var metadata = pe.GetMetadataReader();
    var ownIdentity = metadata.GetAssemblyDefinition().GetAssemblyName().FullName;
    var denials = new List<string>();

    foreach (var handle in metadata.AssemblyReferences)
    {
        var reference = metadata.GetAssemblyReference(handle);
        var identity = ReferenceIdentity(metadata, reference);
        var decision = policy.Evaluate(new ApiTarget(identity, ApiTargetKind.Assembly), ApiOperation.Reference);
        if (!decision.Allowed) denials.Add("assembly " + identity + ": " + decision.Reason);
    }

    foreach (var handle in metadata.TypeReferences)
    {
        var identity = TypeRefIdentity(metadata, handle);
        var session = string.Equals(identity, ownIdentity, StringComparison.OrdinalIgnoreCase);
        var decision = policy.Evaluate(
            new ApiTarget(identity, ApiTargetKind.Type, TypeRefName(metadata, handle)) { IsSessionCode = session },
            ApiOperation.Reference);
        if (!decision.Allowed) denials.Add("type " + TypeRefName(metadata, handle) + ": " + decision.Reason);
    }

    foreach (var handle in metadata.MemberReferences)
    {
        var member = metadata.GetMemberReference(handle);
        if (member.Parent.Kind != HandleKind.TypeReference) continue;
        var typeHandle = (TypeReferenceHandle)member.Parent;
        var identity = TypeRefIdentity(metadata, typeHandle);
        var session = string.Equals(identity, ownIdentity, StringComparison.OrdinalIgnoreCase);
        var kind = member.GetKind() == MemberReferenceKind.Method ? ApiTargetKind.Method : ApiTargetKind.Field;
        var decision = policy.Evaluate(
            new ApiTarget(identity, kind, TypeRefName(metadata, typeHandle), metadata.GetString(member.Name)) { IsSessionCode = session },
            ApiOperation.Reference);
        if (!decision.Allowed)
            denials.Add(kind + " " + TypeRefName(metadata, typeHandle) + "." + metadata.GetString(member.Name) + ": " + decision.Reason);
    }

    foreach (var denial in denials) Console.WriteLine("  DENY " + denial);
    return denials.Count;
}

static string ReferenceIdentity(MetadataReader metadata, AssemblyReference reference) =>
    metadata.GetString(reference.Name) + ", Version=" + reference.Version +
    ", Culture=" + (reference.Culture.IsNil ? "neutral" : metadata.GetString(reference.Culture)) +
    ", PublicKeyToken=" + Token(metadata.GetBlobBytes(reference.PublicKeyOrToken));

static string TypeRefName(MetadataReader metadata, TypeReferenceHandle handle)
{
    var type = metadata.GetTypeReference(handle);
    var name = metadata.GetString(type.Name);
    if (type.ResolutionScope.Kind == HandleKind.TypeReference)
        return TypeRefName(metadata, (TypeReferenceHandle)type.ResolutionScope) + "+" + name;
    var ns = metadata.GetString(type.Namespace);
    return ns.Length == 0 ? name : ns + "." + name;
}

static string TypeRefIdentity(MetadataReader metadata, TypeReferenceHandle handle)
{
    var type = metadata.GetTypeReference(handle);
    if (type.ResolutionScope.Kind == HandleKind.TypeReference)
        return TypeRefIdentity(metadata, (TypeReferenceHandle)type.ResolutionScope);
    if (type.ResolutionScope.Kind != HandleKind.AssemblyReference) return "?";
    return ReferenceIdentity(metadata, metadata.GetAssemblyReference((AssemblyReferenceHandle)type.ResolutionScope));
}

// ---------------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------------
static string FixturesRoot() => Path.Combine(AppContext.BaseDirectory, "fixtures");

static string FrameworkRole() => FixtureMode.PortableFramework
    ? "framework role: framework-portable (DIAGNOSTIC: no P/Invoke; not an acceptance image)"
    : "framework role: framework (normal trusted image with kernel32 DllImport)";

static void PrepareFixtureOverlay(bool portableFramework)
{
    var frameworkDll = Path.Combine(FixturesRoot(), portableFramework ? "framework-portable" : "framework",
        "RuneCLR.GroupedHost.Framework.dll");
    Check(File.Exists(frameworkDll), "missing staged framework image: " + frameworkDll);
    foreach (var folder in new[] { "author-a", "author-b", "author-native-rejected" })
    {
        var directory = Path.Combine(FixturesRoot(), folder);
        if (!Directory.Exists(directory)) continue;
        var target = Path.Combine(directory, "RuneCLR.GroupedHost.Framework.dll");
        if (folder == "author-native-rejected" && !File.Exists(target)) continue;
        // Author role dirs hold no framework copy; the framework resolves from the group context.
        if (File.Exists(target)) File.Delete(target);
    }
}

static GroupedHostOptions Options(string authorFolder, bool? portableFramework = null,
    string authorAssembly = "RuneCLR.GroupedHost.Author.dll", string authorEntryMethod = "Run")
{
    return OptionsFromDirectory(Path.Combine(FixturesRoot(), authorFolder), portableFramework, authorAssembly, authorEntryMethod);
}

static GroupedHostOptions OptionsFromDirectory(string authorDirectory, bool? portableFramework = null,
    string authorAssembly = "RuneCLR.GroupedHost.Author.dll", string authorEntryMethod = "Run")
{
    var contract = typeof(IGroupedHostContract);
    var portable = portableFramework ?? FixtureMode.PortableFramework;
    var frameworkDirectory = Path.Combine(FixturesRoot(), portable ? "framework-portable" : "framework");
    var frameworkIdentity = AssemblyName
        .GetAssemblyName(Path.Combine(frameworkDirectory, "RuneCLR.GroupedHost.Framework.dll")).FullName!;
    return new GroupedHostOptions
    {
        Contract = contract,
        FrameworkDirectory = frameworkDirectory,
        FrameworkAssembly = "RuneCLR.GroupedHost.Framework.dll",
        FrameworkEntryType = "RuneCLR.GroupedHost.Fixtures.FrameworkEntry",
        FrameworkEntryMethod = "Initialize",
        AuthorDirectory = authorDirectory,
        AuthorAssembly = authorAssembly,
        AuthorEntryType = "RuneCLR.GroupedHost.Fixtures.AuthorEntry",
        AuthorEntryMethod = authorEntryMethod,
        AuthorApiPolicy = GroupedHostFixturePolicy.Create(contract.Assembly.FullName!, frameworkIdentity)
    };
}

[MethodImpl(MethodImplOptions.NoInlining)]
static GroupEvidence RunGroup(string authorFolder, int[] values, string mode = "normal")
{
    var host = new TestHost { Mode = mode };
    var session = GroupedHostSession.Open(Options(authorFolder), host);
    session.InvokeFramework();
    var results = values.Select(session.InvokeAuthor).ToArray();
    var retained = host.RetainedCount;
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    var ticket = session.Close();
    return new GroupEvidence(session, token, ticket, host, results, retained);
}

[MethodImpl(MethodImplOptions.NoInlining)]
static GroupEvidence RunGroupWithHostLease(string authorFolder, int[] values, Dictionary<string, object> leases)
{
    var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options(authorFolder), host);
    session.InvokeFramework();
    var results = values.Select(session.InvokeAuthor).ToArray();

    var frameworkContext = AssemblyLoadContext.All.FirstOrDefault(context =>
        !known.Contains(context) &&
        context.Name is not null &&
        context.Name.StartsWith("RuneCLR.Group.Framework:", StringComparison.Ordinal));
    Check(frameworkContext is not null, "the group framework load context was not observable.");
    var frameworkAssembly = frameworkContext!.Assemblies
        .FirstOrDefault(assembly => assembly.GetName().Name == "RuneCLR.GroupedHost.Framework");
    Check(frameworkAssembly is not null, "the framework assembly was not loaded in its group context.");
    leases["framework-context"] = frameworkContext;
    leases["framework-assembly"] = frameworkAssembly!;

    var retained = host.RetainedCount;
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    var ticket = session.Close();
    return new GroupEvidence(session, token, ticket, host, results, retained);
}

static (string Framework, string Author) AssertGroupShape(GroupEvidence evidence, string tag, int[] values)
{
    var expected = values.Select(value => value + (tag == "B" ? 200 : 100)).ToArray();
    Check(evidence.Results.SequenceEqual(expected),
        $"[{tag}] unexpected author results {string.Join(",", evidence.Results)}; expected {string.Join(",", expected)}.");
    Check(evidence.RetainedBeforeRelease == values.Length,
        $"[{tag}] the host must hold {values.Length} author subscription(s); saw {evidence.RetainedBeforeRelease}.");

    var host = evidence.Host;
    var init = host.Lines("framework:init:").ToArray();
    Check(init.Length == 1, $"[{tag}] exactly one framework Initialize must run per group; saw {init.Length}.");
    Check(Field(init[0], "count") == "1", $"[{tag}] framework StaticInitCount did not reset per group: {init[0]}");
    var frameworkToken = Field(init[0], "token");
    Check(frameworkToken.StartsWith("fw-", StringComparison.Ordinal), $"[{tag}] missing framework instance token: {init[0]}");

    var describe = host.Lines("framework:describe:").ToArray();
    Check(describe.Length == values.Length, $"[{tag}] each author call must observe the framework; saw {describe.Length} describe line(s).");
    for (var i = 0; i < describe.Length; i++)
    {
        Check(Field(describe[i], "caller") == tag, $"[{tag}] wrong caller tag: {describe[i]}");
        Check(Field(describe[i], "count") == "1", $"[{tag}] framework init count leaked between groups: {describe[i]}");
        Check(Field(describe[i], "token") == frameworkToken, $"[{tag}] the author did not observe the same framework instance: {describe[i]}");
        Check(Field(describe[i], "calls") == i.ToString(), $"[{tag}] framework Touch count inconsistent: {describe[i]}");
    }

    var touch = host.Lines("author:" + tag + ":framework-touch=").ToArray();
    Check(touch.Length == values.Length, $"[{tag}] expected {values.Length} framework touch line(s); saw {touch.Length}.");
    for (var i = 0; i < touch.Length; i++)
        Check(touch[i].EndsWith("=" + (i + 1), StringComparison.Ordinal), $"[{tag}] unexpected touch result: {touch[i]}");

    var initial = host.Lines("author:" + tag + ":initial:").ToArray();
    var current = host.Lines("author:" + tag + ":current:").ToArray();
    Check(initial.Length == values.Length && current.Length == values.Length,
        $"[{tag}] author entry markers missing (initial={initial.Length}, current={current.Length}).");
    for (var i = 0; i < initial.Length; i++)
        Check(Field(initial[i], "run") == (i + 1).ToString(), $"[{tag}] author run counter leaked: {initial[i]}");
    var authorToken = Field(initial[0], "token");
    Check(authorToken.StartsWith("author-" + tag + "-", StringComparison.Ordinal), $"[{tag}] missing author token: {initial[0]}");
    Check(Field(current[^1], "token") == authorToken, $"[{tag}] the author static token must persist inside one group.");
    Check(!host.Lines("author:").Any(line => line.Contains("framework-event-fired", StringComparison.Ordinal)),
        $"[{tag}] the framework static event must not fire without an explicit raise.");
    return (frameworkToken, authorToken);
}

static void WaitCollected(GroupedHostTicket ticket, string what)
{
    var framework = ticket.FrameworkContext;
    var author = ticket.AuthorContext;
    Check(framework is not null && author is not null,
        what + ": the terminal ticket must carry both weak references.");
    for (var attempt = 0; attempt < 12 && (framework!.IsAlive || author!.IsAlive); attempt++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Thread.Sleep(20);
    }
    Check(!framework!.IsAlive, what + ": the framework context stayed alive after Close.");
    Check(!author!.IsAlive, what + ": the author context stayed alive after Close.");
}

static string Field(string line, string key)
{
    var marker = ":" + key + "=";
    var index = line.IndexOf(marker, StringComparison.Ordinal);
    if (index < 0) return "";
    var start = index + marker.Length;
    var end = line.IndexOf(':', start);
    return end < 0 ? line[start..] : line[start..end];
}

static TException Catch<TException>(Action action) where TException : Exception
{
    try
    {
        action();
    }
    catch (TException error)
    {
        return error;
    }
    catch (Exception error)
    {
        throw new InvalidOperationException(
            $"expected {typeof(TException).Name} but saw {error.GetType().Name}: {error.Message}", error);
    }
    throw new InvalidOperationException($"expected {typeof(TException).Name} but no exception was thrown.");
}

// Host-owned validation failures: bad or missing entry metadata/signature. The documented validation
// API reports InvalidDataException, preserves that type through an after-context Open rollback, and
// must not carry an inner exception, a stack trace, or domain-owned Type metadata. The message must
// still name the offending entry so the host can act on it.
static void AssertHostOwnedValidationError(Exception error, string expectedEntryName, string what)
{
    if (error is TargetInvocationException)
        throw new InvalidOperationException(
            what + ": the validation error must not leak the reflection wrapper. Observed: " + DescribeFailure(error));
    Check(error is InvalidDataException,
        what + ": expected a host-owned InvalidDataException; saw " + DescribeFailure(error));
    Check(error.InnerException is null,
        what + ": the validation error must not carry an inner exception: " + DescribeFailure(error));
    Check(error.Message.Contains(expectedEntryName, StringComparison.Ordinal),
        what + ": the validation message must name the offending entry '" + expectedEntryName + "': " + error.Message);
    Check(!error.Message.Contains("   at ", StringComparison.Ordinal),
        what + ": the validation message must not carry a stack trace: " + error.Message);
    Check(!error.Message.Contains(Environment.NewLine, StringComparison.Ordinal),
        what + ": the validation message must be single-line: " + error.Message);
    Console.WriteLine("  " + what + ": host-owned InvalidDataException naming '" + expectedEntryName + "' without inner exception");
}

// Host-owned invocation failures: author or framework execution. Type-only InvalidOperationException
// without an inner exception; the message names the bounded fixture exception type. The obsolete
// original fixture message is neither required nor asserted.
static void AssertHostOwnedInvocationError(Exception error, string fixtureType, string what)
{
    if (error is TargetInvocationException)
        throw new InvalidOperationException(
            what + ": the boundary still leaks the reflection wrapper (TargetInvocationException); expected a host-owned " +
            "InvalidOperationException with InnerException == null and only the fixture exception type name. Observed: " +
            DescribeFailure(error));
    Check(error is InvalidOperationException,
        what + ": expected a host-owned InvalidOperationException; saw " + DescribeFailure(error));
    Check(error.InnerException is null,
        what + ": the host-owned failure must not carry an inner exception: " + DescribeFailure(error));
    Check(error.Message.Contains(fixtureType, StringComparison.Ordinal),
        what + ": the host-owned message must name the fixture exception type '" + fixtureType + "': " + error.Message);
    Check(!error.Message.Contains("   at ", StringComparison.Ordinal),
        what + ": the host-owned message must not carry a stack trace: " + error.Message);
    Console.WriteLine("  " + what + ": host-owned InvalidOperationException names " + fixtureType);
}

static Exception CatchAny(Action action)
{
    try
    {
        action();
    }
    catch (Exception error)
    {
        return error;
    }
    throw new InvalidOperationException("expected an exception but the call succeeded.");
}

static string DescribeFailure(Exception? error)
{
    var parts = new List<string>();
    for (Exception? current = error; current is not null; current = current.InnerException)
        parts.Add(current.GetType().Name + ": " + current.Message);
    return string.Join(" <- ", parts);
}

static int DumpReferences(string[] args)
{
    if (args.Length != 2)
    {
        Console.Error.WriteLine("--dump-refs requires one assembly path.");
        return 2;
    }
    using var stream = File.OpenRead(Path.GetFullPath(args[1]));
    using var pe = new PEReader(stream);
    var metadata = pe.GetMetadataReader();
    foreach (var handle in metadata.MemberReferences)
    {
        var member = metadata.GetMemberReference(handle);
        var parent = member.Parent.Kind == HandleKind.TypeReference
            ? TypeRefName(metadata, (TypeReferenceHandle)member.Parent)
            : "?";
        Console.WriteLine(parent + "::" + metadata.GetString(member.Name));
    }
    return 0;
}

static int RunGuarded(string name, Func<int> run)
{
    try
    {
        return run();
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("FAIL " + name + ": " + error);
        return 1;
    }
}

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static string Token(byte[] value) => value.Length == 0 ? "null" : Convert.ToHexString(value).ToLowerInvariant();

// Diagnostic only: validate the author image bytes in the Default context before any grouped Open, so
// the opcode table used by the capability profile is initialized outside the required-interpreter
// load hook. This distinguishes a harness policy gap from a runtime class-initialization hazard.
static int DiagnosePrewarm()
{
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    var authorPath = Path.Combine(FixturesRoot(), "author-a", "RuneCLR.GroupedHost.Author.dll");
    var authorImage = File.ReadAllBytes(authorPath);
    var authorIdentity = AssemblyName.GetAssemblyName(authorPath).FullName!;
    var contractIdentity = typeof(IGroupedHostContract).Assembly.FullName!;
    var frameworkIdentity = AssemblyName
        .GetAssemblyName(Path.Combine(FixturesRoot(), FixtureMode.PortableFramework ? "framework-portable" : "framework", "RuneCLR.GroupedHost.Framework.dll")).FullName!;
    var policy = GroupedHostFixturePolicy.Create(contractIdentity, frameworkIdentity);
    try
    {
        GameplayCapabilityPolicy.ValidateWithApiPolicy(authorImage, [authorIdentity], contractIdentity, policy,
            allowReflectionTypeTokens: true, allowSessionAssemblyNames: true);
        Console.WriteLine("prewarm PASS: author IL validation completed in the Default context");
        return 0;
    }
    catch (Exception error)
    {
        Console.WriteLine("prewarm FAIL: " + DescribeFailure(error));
        return 1;
    }
}

static int RunPrewarmThenPositive()
{
    var code = DiagnosePrewarm();
    Console.WriteLine("prewarm result=" + code);
    return Positive();
}
static int PolicyNegative()
{
    var contractIdentity = typeof(IGroupedHostContract).Assembly.FullName!;
    var frameworkIdentity = AssemblyName
        .GetAssemblyName(Path.Combine(FixturesRoot(), FixtureMode.PortableFramework ? "framework-portable" : "framework", "RuneCLR.GroupedHost.Framework.dll")).FullName!;
    var authorIdentity = AssemblyName
        .GetAssemblyName(Path.Combine(FixturesRoot(), "author-a", "RuneCLR.GroupedHost.Author.dll")).FullName!;
    var policy = GroupedHostFixturePolicy.Create(contractIdentity, frameworkIdentity);
    const string coreLib = "System.Private.CoreLib, Version=12.0.0.0, Culture=neutral, PublicKeyToken=7cec85d7bea7798e";
    var checks = new (string Name, ApiTarget Target, ApiOperation Operation, bool Expected)[]
    {
        ("author direct P/Invoke-like member is not approved", new(authorIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.AuthorEntry", "GetCurrentThreadId"), ApiOperation.Reference, false),
        ("author delegate creation is not approved", new(authorIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.AuthorEntry", "Run") { IsSessionCode = true }, ApiOperation.CreateDelegate, false),
        ("unlisted BCL type is denied", new(coreLib, ApiTargetKind.Type, "System.IO.File"), ApiOperation.Reference, false),
        ("unlisted BCL member is denied", new(coreLib, ApiTargetKind.Method, "System.IO.File", "ReadAllBytes"), ApiOperation.Reference, false),
        ("unknown assembly is denied", new("Evil, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", ApiTargetKind.Assembly), ApiOperation.Reference, false),
        ("foreign framework member is denied", new(frameworkIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.FrameworkEntry", "GetType"), ApiOperation.Reference, false),
        ("contract member outside the surface is denied", new(contractIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.IGroupedHostContract", "Equals"), ApiOperation.Reference, false),
        ("framework Touch is approved", new(frameworkIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.FrameworkEntry", "Touch"), ApiOperation.Reference, true),
        ("contract Record is approved", new(contractIdentity, ApiTargetKind.Method, "RuneCLR.GroupedHost.Fixtures.IGroupedHostContract", "Record"), ApiOperation.Reference, true),
        ("standard BCL delegate construction is approved", new(coreLib, ApiTargetKind.Method, "System.Action", ".ctor"), ApiOperation.Reference, true),
        ("explicit Guid.NewGuid is approved", new(coreLib, ApiTargetKind.Method, "System.Guid", "NewGuid"), ApiOperation.Reference, true)
    };
    var failures = 0;
    foreach (var (name, target, operation, expected) in checks)
    {
        var actual = policy.Evaluate(target, operation).Allowed;
        if (actual == expected)
        {
            Console.WriteLine($"PASS policy {name} (allowed={actual})");
        }
        else
        {
            failures++;
            Console.Error.WriteLine($"FAIL policy {name}: allowed={actual}, expected={expected}");
        }
    }
    Console.WriteLine($"policy-negative: {checks.Length - failures}/{checks.Length} expectations observed");
    return failures == 0 ? 0 : 1;
}
static int RuntimeCheck()
{
    var corelib = typeof(object).Assembly;
    var policy = corelib.GetType("System.Reflection.RuneCLRReflectionPolicy", throwOnError: false);
    var create = typeof(AssemblyLoadContext).GetMethod(
        "RuneCLR_CreateInterpreterRequired", BindingFlags.NonPublic | BindingFlags.Static);
    var version = typeof(AssemblyLoadContext).GetMethod(
        "RuneCLR_GetExecutionPolicyVersion", BindingFlags.NonPublic | BindingFlags.Static);
    Console.WriteLine("runtime: " + System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription);
    Console.WriteLine("environment version: " + Environment.Version);
    Console.WriteLine("CoreLib: " + corelib.FullName);
    Console.WriteLine("CoreLib path: " + corelib.Location);
    Console.WriteLine("CoreLib sha256: " + HashFile(corelib.Location));
    Console.WriteLine("policy switch: " + SwitchState("RuneCLR.EnableReflectionPolicy"));
    Console.WriteLine("origin-scan switch: " + SwitchState("RuneCLR.EnableReflectionPolicyOriginScan"));
    Console.WriteLine("reflection-policy type: " + (policy is null ? "MISSING" : policy.FullName));
    if (policy is not null)
    {
        foreach (var name in new[] { "RuneCLR_GetReflectionPolicyVersion", "RuneCLR_EnterReflectionPolicy", "RuneCLR_CreateReflectionPolicySession", "RuneCLR_GetReflectionPolicyCapabilities" })
            Console.WriteLine("  " + name + ": " + (policy.GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static) is null ? "MISSING" : "present"));
    }
    Console.WriteLine("interpreter required factory: " + (create is null ? "MISSING" : "present"));
    Console.WriteLine("execution policy version: " + (version is null ? "MISSING" : "present"));
    var capabilities = ReflectionCapabilities();
    Console.WriteLine("reflection capabilities: " + (capabilities is null ? "UNAVAILABLE" : capabilities.Value.ToString()));
    Console.WriteLine("origin-scan capability bit 0: " + (capabilities is null ? "UNAVAILABLE" : ((capabilities.Value & 1) != 0 ? "present" : "absent")));
    var ok = policy is not null && create is not null && version is not null;
    Console.WriteLine(ok ? "runtime-check PASS (private runtime surface)" : "runtime-check MISSING private runtime support");
    return ok ? 0 : 1;
}

static string SwitchState(string name) =>
    AppContext.TryGetSwitch(name, out var enabled) ? enabled.ToString() : "unset";

static int? ReflectionCapabilities()
{
    var policy = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", throwOnError: false);
    var method = policy?.GetMethod("RuneCLR_GetReflectionPolicyCapabilities", BindingFlags.NonPublic | BindingFlags.Static);
    if (method is null) return null;
    try
    {
        return (int)method.Invoke(null, null)!;
    }
    catch (TargetInvocationException)
    {
        return null;
    }
}

static void RequireOriginScanCapability()
{
    var capabilities = ReflectionCapabilities();
    Check(capabilities is not null,
        "the session-origin-scan capability cannot be queried; start the process on a private CoreLib that provides it.");
    Check((capabilities!.Value & 1) != 0,
        "session-origin-scan capability bit 0 is absent. Start the private test process with " +
        "RuneCLR.EnableReflectionPolicyOriginScan=true (runtimeconfig configProperties) before any grouped Open.");
    Console.WriteLine("origin-scan capability: bit 0 present (capabilities=" + capabilities.Value + ")");
}

static int OriginNegative()
{
    // Runs in a process whose runtimeconfig enables the reflection policy but NOT origin scanning.
    // The grouped profile must fail closed before any author entry.
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    var capabilities = ReflectionCapabilities();
    Console.WriteLine("reflection capabilities: " + (capabilities is null ? "UNAVAILABLE" : capabilities.Value.ToString()));
    Console.WriteLine("origin-scan capability bit 0: " +
        (capabilities is null ? "UNAVAILABLE" : ((capabilities.Value & 1) != 0 ? "present" : "absent")));
    if (capabilities is { } value && (value & 1) != 0)
    {
        Console.Error.WriteLine("FAIL origin-negative: this process reports the origin-scan capability; run it with an origin-off runtimeconfig.");
        return 1;
    }

    PrepareFixtureOverlay(portableFramework: true);
    var host = new TestHost();
    try
    {
        _ = GroupedHostSession.Open(Options("author-a"), host);
        Console.Error.WriteLine("FAIL origin-negative: Open succeeded without the session-origin-scan capability.");
        return 1;
    }
    catch (PlatformNotSupportedException error)
    {
        var chain = DescribeFailure(error);
        if (chain.Contains("origin", StringComparison.OrdinalIgnoreCase) ||
            chain.Contains("capability", StringComparison.OrdinalIgnoreCase))
        {
            if (host.Records.Count != 0 || host.RetainedCount != 0)
            {
                Console.Error.WriteLine("FAIL origin-negative: code ran before the capability rejection.");
                return 1;
            }
            Console.WriteLine("PASS origin-negative: grouped Open fails closed without the origin-scan capability; " + chain);
            return 0;
        }
        Console.Error.WriteLine("FAIL origin-negative: unexpected rejection shape: " + chain);
        return 1;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("FAIL origin-negative: unexpected " + error);
        return 1;
    }
}

static string HashFile(string path)
{
    if (!File.Exists(path)) return "MISSING";
    using var stream = File.OpenRead(path);
    return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(stream)).ToLowerInvariant();
}
static bool PrivateRuntimeSurfacePresent()
{
    var policy = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", throwOnError: false);
    var create = typeof(AssemblyLoadContext).GetMethod(
        "RuneCLR_CreateInterpreterRequired", BindingFlags.NonPublic | BindingFlags.Static);
    var version = typeof(AssemblyLoadContext).GetMethod(
        "RuneCLR_GetExecutionPolicyVersion", BindingFlags.NonPublic | BindingFlags.Static);
    return policy is not null && create is not null && version is not null;
}

static int RunSingle(Action run, string name)
{
    try
    {
        run();
        Console.WriteLine("PASS " + name);
        return 0;
    }
    catch (NotRunException error)
    {
        Console.WriteLine($"NOT-RUN {name}: {error.Message}");
        return 3;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine($"FAIL {name}: {error}");
        return 1;
    }
}
// ---------------------------------------------------------------------------------------------
// Callback reflection policy: the author-installed callback runs during InvokeFramework with no
// InvokeAuthor scope; origin scanning must still reject the explicitly denied reflected target.
// ---------------------------------------------------------------------------------------------
static int CallbackPolicy()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);

    var tests = new List<(string Name, Action Run)>
    {
        ("author callback reflection is denied without an entry scope", CallbackReflectionDenied),
        ("framework-owned reflection stays allowed", FrameworkOwnReflection)
    };
    var failures = 0;
    var notRun = 0;
    foreach (var (name, run) in tests)
    {
        try
        {
            run();
            Console.WriteLine("PASS " + name);
        }
        catch (NotRunException error)
        {
            notRun++;
            Console.Error.WriteLine("NOT-RUN " + name + ": " + error.Message);
        }
        catch (Exception error)
        {
            failures++;
            Console.Error.WriteLine("FAIL " + name + ": " + error);
        }
    }
    Console.WriteLine((tests.Count - failures - notRun) + " passed, " + notRun + " not-run, " + failures + " failed of " + tests.Count);
    return failures == 0 && notRun == 0 ? 0 : 1;
}

static void AssertHostOwnedBoundaryError(Exception error, string what)
{
    if (error is TargetInvocationException)
        throw new InvalidOperationException(what + ": the boundary still leaks TargetInvocationException; " +
            "a host-owned type-only error is required: " + DescribeFailure(error));
    Check(error is InvalidOperationException, what + ": expected a host-owned InvalidOperationException; saw " + DescribeFailure(error));
    Check(error.InnerException is null, what + ": the host-owned error must not carry an inner exception: " + DescribeFailure(error));
    Console.WriteLine("  " + what + ": host-owned InvalidOperationException without inner exception");
}

static void CallbackReflectionDenied()
{
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-a"), host);
    Check(session.InvokeAuthor(1) == 101, "the normal author entry must succeed before the callback case.");
    Check(host.Lines("author:A:framework-event-fired").Count == 0, "the callback must not run before the framework raises it.");
    Check(host.Lines("author:A:reflection-attempt").Count == 0, "the reflection attempt must happen only inside the callback.");

    host.Mode = "raise-denied-reflection";
    var error = CatchAny(() => session.InvokeFramework());

    Check(host.Lines("author:A:framework-event-fired").Count == 1, "the framework did not raise the author callback.");
    Check(host.Lines("author:A:reflection-attempt").Count == 1, "the callback did not attempt reflection.");
    Check(host.Lines("author:A:reflection-allowed:").Count == 0, "the denied reflection target was allowed.");
    var denials = host.Lines("author:A:reflection-denied:");
    Check(denials.Count == 1, "the reflected target was not denied (records: " + string.Join(" | ", host.Lines("author:A:reflection" )) + ")");
    Check(denials[0].Contains("type=InvalidOperationException", StringComparison.Ordinal), "unexpected denial type: " + denials[0]);
    Check(denials[0].Contains("inner=null", StringComparison.Ordinal), "the denial must not carry an inner exception: " + denials[0]);
    Check(denials[0].Contains("StartsWith", StringComparison.Ordinal), "the denial must name the denied target: " + denials[0]);
    Console.WriteLine("  in-process denial: " + denials[0]);
    AssertHostOwnedBoundaryError(error, "callback reflection denial");

    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    WaitCollected(session.Close(), "callback-policy group");
}

static void FrameworkOwnReflection()
{
    var host = new TestHost { Mode = "framework-own-reflection" };
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    var lines = host.Lines("framework:own-reflection:");
    Check(lines.Count == 1, "the framework-owned reflection record is missing (records: " + string.Join(" | ", host.Records) + ")");
    Check(lines[0].EndsWith(":7001:allowed", StringComparison.Ordinal), "framework-owned reflection must stay allowed: " + lines[0]);
    Check(host.Lines("framework:init:").Count == 0, "the reflection mode must not re-initialize the framework state.");
    Check(session.InvokeAuthor(1) == 101, "the group must stay usable after framework-owned reflection.");
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    WaitCollected(session.Close(), "framework-own-reflection group");
}

// ---------------------------------------------------------------------------------------------
// Dynamic admission: an already open group loads a NativeRejected image outside its role
// catalogs; the strict load hook must reject it without a process fatal or native execution.
// ---------------------------------------------------------------------------------------------
static int DynamicRejected()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);

    var dynamicPath = Path.Combine(FixturesRoot(), "dynamic", "RuneCLR.GroupedHost.Author.NativeRejected.dll");
    Check(File.Exists(dynamicPath), "missing dynamic rejection fixture: " + dynamicPath);
    // The host reads the bytes before Open and before any author scope exists; the author never reads files.
    var image = File.ReadAllBytes(dynamicPath);
    Check(image.Length > 0, "the dynamic rejection fixture is empty.");

    var host = new TestHost { DynamicImage = image };
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    var result = session.InvokeAuthor(1);
    Check(result == 101, "the author entry must complete after the rejected dynamic load: " + result);
    Check(host.Lines("author:A:dynamic-load-attempt").Count == 1, "the dynamic load attempt was not recorded.");
    Check(host.Lines("author:").Any(line => line.Contains("dynamic-load-ALLOWED", StringComparison.Ordinal)) == false,
        "a NativeRejected author image was loaded dynamically.");
    var rejected = host.Lines("author:A:dynamic-load-rejected:");
    Check(rejected.Count == 1, "the dynamic load was not rejected (records: " + string.Join(" | ", host.Lines("author:")) + ")");
    Check(rejected[0].Contains("InvalidDataException", StringComparison.Ordinal), "unexpected dynamic rejection type: " + rejected[0]);
    Check(rejected[0].Contains("P/Invoke", StringComparison.OrdinalIgnoreCase) ||
          rejected[0].Contains("managed-il", StringComparison.OrdinalIgnoreCase) ||
          rejected[0].Contains("admission", StringComparison.OrdinalIgnoreCase),
        "the dynamic rejection must carry the native-import/intake reason: " + rejected[0]);
    Console.WriteLine("  dynamic rejection: " + rejected[0]);

    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);
    WaitCollected(session.Close(), "dynamic-rejected group");

    var next = RunGroup("author-a", [7]);
    var tokens = AssertGroupShape(next, "A", [7]);
    Check(tokens.Framework.StartsWith("fw-", StringComparison.Ordinal), "the next normal group must start fresh.");
    WaitCollected(next.Ticket, "post-dynamic group");
    Console.WriteLine("PASS dynamic NativeRejected load rejected; group retired and the next group succeeded");
    return 0;
}

// ---------------------------------------------------------------------------------------------
// Approved framework copy: an exact byte copy in the author role opens and shares the selected
// framework instance; the same identity with different bytes must reject before execution.
// ---------------------------------------------------------------------------------------------
static int FrameworkCopy()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);

    var tempRoot = Path.Combine(Path.GetTempPath(), "runeclr-grouped-copy-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempRoot);
    try
    {
        var exact = Path.Combine(tempRoot, "exact");
        var mismatch = Path.Combine(tempRoot, "mismatch");
        CopyAuthorRole(exact, Path.Combine(FixturesRoot(), "framework", "RuneCLR.GroupedHost.Framework.dll"));
        CopyAuthorRole(mismatch, Path.Combine(FixturesRoot(), "framework-portable", "RuneCLR.GroupedHost.Framework.dll"));

        var host = new TestHost();
        var session = GroupedHostSession.Open(OptionsFromDirectory(exact), host);
        session.InvokeFramework();
        Check(session.InvokeAuthor(1) == 101, "an author role with an exact framework copy must open and run.");
        var init = host.Lines("framework:init:");
        var describe = host.Lines("framework:describe:");
        Check(init.Count == 1 && describe.Count == 1, "the exact copy group is missing framework records.");
        Check(Field(init[0], "token") == Field(describe[0], "token"), "the exact copy group did not share the selected framework instance.");
        host.ReleaseRetained();
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        WaitCollected(session.Close(), "framework-copy exact group");

        var rejectHost = new TestHost();
        var rejection = CatchAny(() => GroupedHostSession.Open(OptionsFromDirectory(mismatch), rejectHost));
        Check(rejection is InvalidDataException, "a framework copy with different bytes must be rejected: " + DescribeFailure(rejection));
        Check(DescribeFailure(rejection).Contains("differs from the selected framework bytes", StringComparison.Ordinal),
            "the rejection must name the byte mismatch: " + DescribeFailure(rejection));
        Check(rejectHost.Records.Count == 0, "the rejected copy group executed code.");
        Console.WriteLine("PASS exact framework copy opens and shares the instance; different bytes rejected before execution");
        return 0;
    }
    finally
    {
        var full = Path.GetFullPath(tempRoot);
        var tempRootPath = Path.GetFullPath(Path.GetTempPath());
        if (full.StartsWith(tempRootPath, StringComparison.OrdinalIgnoreCase) && Directory.Exists(full))
            Directory.Delete(full, recursive: true);
    }
}

static void CopyAuthorRole(string directory, string frameworkSource)
{
    Directory.CreateDirectory(directory);
    File.Copy(Path.Combine(FixturesRoot(), "author-a", "RuneCLR.GroupedHost.Author.dll"),
        Path.Combine(directory, "RuneCLR.GroupedHost.Author.dll"));
    File.Copy(Path.Combine(FixturesRoot(), "author-a", "RuneCLR.GroupedHost.Contracts.dll"),
        Path.Combine(directory, "RuneCLR.GroupedHost.Contracts.dll"));
    File.Copy(frameworkSource, Path.Combine(directory, "RuneCLR.GroupedHost.Framework.dll"));
}

// ---------------------------------------------------------------------------------------------
// Failed Open after context creation: the wrong author entry method must roll back the new
// contexts. Contexts are observed only through weak references captured on AssemblyLoad.
// ---------------------------------------------------------------------------------------------
static int Rollback()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);

    var observed = new List<WeakReference>();
    AssemblyLoadEventHandler handler = (_, args) =>
    {
        var name = args.LoadedAssembly.GetName().Name;
        if (name is "RuneCLR.GroupedHost.Framework" or "RuneCLR.GroupedHost.Author")
        {
            var context = AssemblyLoadContext.GetLoadContext(args.LoadedAssembly);
            if (context is not null) observed.Add(new WeakReference(context, trackResurrection: true));
        }
    };
    Exception? failure = null;
    var records = 0;
    var retained = 0;
    AppDomain.CurrentDomain.AssemblyLoad += handler;
    try
    {
        var host = new TestHost();
        failure = CatchAny(() => GroupedHostSession.Open(Options("author-a", authorEntryMethod: "MissingEntry"), host));
        records = host.Records.Count;
        retained = host.RetainedCount;
    }
    finally
    {
        AppDomain.CurrentDomain.AssemblyLoad -= handler;
    }

    var error = failure ?? throw new InvalidOperationException("the wrong author entry method did not fail Open.");
    AssertHostOwnedValidationError(error, "MissingEntry", "failed Open rollback");
    Check(records == 0, "the failed Open executed framework or author code (host records present).");
    Check(retained == 0, "the failed Open installed host roots before the entry rejection.");
    Check(observed.Count >= 1, "the AssemblyLoad observer captured no group context.");
    for (var attempt = 0; attempt < 12 && observed.Any(reference => reference.IsAlive); attempt++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Thread.Sleep(20);
    }
    foreach (var reference in observed)
        Check(!reference.IsAlive, "a context created before the failed Open was not rolled back.");

    var next = RunGroup("author-a", [4]);
    AssertGroupShape(next, "A", [4]);
    WaitCollected(next.Ticket, "post-rollback group");
    Console.WriteLine("PASS failed Open rolled back its contexts; the next group succeeded");
    return 0;
}

// ---------------------------------------------------------------------------------------------
// Unload retry: HOST-owned ALC.Unloading handlers (no product hook). A throwing handler must fail
// retirement without completing it, keep the roots for a retry, and let one retry succeed. Strong
// ALC locals stay inside NoInlining helpers; only scalars, host records and the terminal ticket
// (weak references) leave the frame.
// ---------------------------------------------------------------------------------------------
static int UnloadRetry()
{
    FixtureMode.PortableFramework = false;
    Console.WriteLine(FrameworkRole());
    AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", true);
    RequireOriginScanCapability();
    PrepareFixtureOverlay(FixtureMode.PortableFramework);

    var tests = new List<(string Name, Action Run)>
    {
        ("framework Unloading handler throws once; Close retry succeeds", FrameworkUnloadRetry),
        ("author Unloading handler throws after the framework request; retry stays single-request", AuthorUnloadRetry),
        ("Dispose retirement failure then controlled retry succeeds", DisposeRetry)
    };
    var failures = 0;
    var notRun = 0;
    foreach (var (name, run) in tests)
    {
        try { run(); Console.WriteLine("PASS " + name); }
        catch (NotRunException error) { notRun++; Console.Error.WriteLine("NOT-RUN " + name + ": " + error.Message); }
        catch (Exception error) { failures++; Console.Error.WriteLine("FAIL " + name + ": " + error); }
    }
    Console.WriteLine((tests.Count - failures - notRun) + " passed, " + notRun + " not-run, " + failures + " failed of " + tests.Count);
    return failures == 0 && notRun == 0 ? 0 : 1;
}

static void AssertRetirementFailure(UnloadCaseResult result, string expectedPhase)
{
    var failure = result.Failure ?? throw new InvalidOperationException("the throwing Unloading handler did not fail retirement.");
    Check(failure is InvalidOperationException, "the retirement failure must be host-owned: " + DescribeFailure(failure));
    Check(failure.InnerException is null, "the retirement failure must not carry an inner exception: " + DescribeFailure(failure));
    Check(failure.Message.Contains(expectedPhase, StringComparison.Ordinal), "unexpected retirement phase in: " + failure.Message);
    Check(failure.Message.Contains("UnloadHandlerException", StringComparison.Ordinal), "the retirement failure must name the bounded handler failure: " + failure.Message);
    Check(!result.ClosedAfterFailure, "a failed retirement must not report the group closed.");
    Check(result.RetryEntryError.Contains("Entry is closed", StringComparison.Ordinal),
        "entries must stay rejected after a failed retirement: " + result.RetryEntryError);
    Check(result.ClosedAfterRetry, "the retry must complete the group.");
    Check(result.Ticket.FrameworkUnloadRequested && result.Ticket.AuthorUnloadRequested && result.Ticket.LeasesReleased,
        "the terminal ticket must report both unload requests and released leases.");
    Check(result.Ticket.FrameworkUnloadFailure is null && result.Ticket.AuthorUnloadFailure is null,
        "a successful retry must clear the failure fields: " + result.Ticket.FrameworkUnloadFailure + "/" + result.Ticket.AuthorUnloadFailure);
}

static void FrameworkUnloadRetry()
{
    var result = RunFrameworkHandlerCase();
    AssertRetirementFailure(result, "Framework unload request failed");
    // The CLR raises the Unloading event of a context once; the retry succeeds without re-raising it.
    Check(result.FrameworkUnloadCalls == 1, "the framework Unloading event must be raised exactly once; calls=" + result.FrameworkUnloadCalls);
    WaitCollected(result.Ticket, "framework unload retry group");
    var next = RunGroup("author-a", [6]);
    AssertGroupShape(next, "A", [6]);
    WaitCollected(next.Ticket, "post-unload-retry group");
}

static void AuthorUnloadRetry()
{
    var result = RunAuthorHandlerCase();
    AssertRetirementFailure(result, "Author unload request failed");
    Check(result.FrameworkUnloadCalls == 1, "the framework unload must not be requested twice; calls=" + result.FrameworkUnloadCalls);
    Check(result.AuthorUnloadCalls == 1, "the author Unloading event must be raised exactly once; calls=" + result.AuthorUnloadCalls);
    WaitCollected(result.Ticket, "author unload retry group");
    var next = RunGroup("author-a", [8]);
    AssertGroupShape(next, "A", [8]);
    WaitCollected(next.Ticket, "post-author-unload-retry group");
}

static void DisposeRetry()
{
    var result = RunDisposeHandlerCase();
    AssertRetirementFailure(result, "Framework unload request failed");
    // The CLR raises the Unloading event of a context once; the retry succeeds without re-raising it.
    Check(result.FrameworkUnloadCalls == 1, "the framework Unloading event must be raised exactly once; calls=" + result.FrameworkUnloadCalls);
    WaitCollected(result.Ticket, "dispose retry group");
    var next = RunGroup("author-b", [9]);
    AssertGroupShape(next, "B", [9]);
    WaitCollected(next.Ticket, "post-dispose-retry group");
}

static (AssemblyLoadContext Framework, AssemblyLoadContext Author) CaptureNewGroupContexts(HashSet<AssemblyLoadContext> known)
{
    var framework = AssemblyLoadContext.All.FirstOrDefault(context =>
        !known.Contains(context) && context.Name is not null &&
        context.Name.StartsWith("RuneCLR.Group.Framework:", StringComparison.Ordinal));
    var author = AssemblyLoadContext.All.FirstOrDefault(context =>
        !known.Contains(context) && context.Name is not null &&
        context.Name.StartsWith("RuneCLR.Group.Author:", StringComparison.Ordinal));
    Check(framework is not null, "the group framework context was not observable.");
    Check(author is not null, "the group author context was not observable.");
    return (framework!, author!);
}

[MethodImpl(MethodImplOptions.NoInlining)]
static UnloadCaseResult RunFrameworkHandlerCase()
{
    var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    Check(session.InvokeAuthor(1) == 101, "the pre-retirement entry must succeed.");
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);

    var contexts = CaptureNewGroupContexts(known);
    var frameworkCalls = 0;
    Action<AssemblyLoadContext> handler = _ =>
    {
        if (Interlocked.Increment(ref frameworkCalls) == 1) throw new UnloadHandlerException("framework-unload-handler-once");
    };
    contexts.Framework.Unloading += handler;
    Exception? failure = null;
    var closedAfterFailure = false;
    var retryEntry = "";
    var closedAfterRetry = false;
    GroupedHostTicket ticket = default;
    try
    {
        failure = CatchAny(() => session.Close());
        closedAfterFailure = session.IsClosed;
        retryEntry = CatchAny(() => session.InvokeAuthor(1)).Message;
        ticket = session.Close();
        closedAfterRetry = session.IsClosed;
    }
    finally
    {
        contexts.Framework.Unloading -= handler;
    }
    return new UnloadCaseResult(failure, closedAfterFailure, retryEntry, ticket, frameworkCalls, 0, closedAfterRetry);
}

[MethodImpl(MethodImplOptions.NoInlining)]
static UnloadCaseResult RunAuthorHandlerCase()
{
    var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-a"), host);
    session.InvokeFramework();
    Check(session.InvokeAuthor(1) == 101, "the pre-retirement entry must succeed.");
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);

    var contexts = CaptureNewGroupContexts(known);
    var frameworkCalls = 0;
    var authorCalls = 0;
    Action<AssemblyLoadContext> frameworkCounter = _ => Interlocked.Increment(ref frameworkCalls);
    Action<AssemblyLoadContext> authorHandler = _ =>
    {
        if (Interlocked.Increment(ref authorCalls) == 1) throw new UnloadHandlerException("author-unload-handler-once");
    };
    contexts.Framework.Unloading += frameworkCounter;
    contexts.Author.Unloading += authorHandler;
    Exception? failure = null;
    var closedAfterFailure = false;
    var retryEntry = "";
    var closedAfterRetry = false;
    GroupedHostTicket ticket = default;
    try
    {
        failure = CatchAny(() => session.Close());
        closedAfterFailure = session.IsClosed;
        retryEntry = CatchAny(() => session.InvokeAuthor(1)).Message;
        ticket = session.Close();
        closedAfterRetry = session.IsClosed;
    }
    finally
    {
        contexts.Framework.Unloading -= frameworkCounter;
        contexts.Author.Unloading -= authorHandler;
    }
    return new UnloadCaseResult(failure, closedAfterFailure, retryEntry, ticket, frameworkCalls, authorCalls, closedAfterRetry);
}

[MethodImpl(MethodImplOptions.NoInlining)]
static UnloadCaseResult RunDisposeHandlerCase()
{
    var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
    var host = new TestHost();
    var session = GroupedHostSession.Open(Options("author-b"), host);
    session.InvokeFramework();
    Check(session.InvokeAuthor(1) == 201, "the pre-retirement entry must succeed.");
    host.ReleaseRetained();
    var token = session.BeginCleanup();
    session.AcknowledgeCleanup(token);
    session.CompleteCleanup(token);

    var contexts = CaptureNewGroupContexts(known);
    var frameworkCalls = 0;
    Action<AssemblyLoadContext> handler = _ =>
    {
        if (Interlocked.Increment(ref frameworkCalls) == 1) throw new UnloadHandlerException("dispose-unload-handler-once");
    };
    contexts.Framework.Unloading += handler;
    Exception? failure = null;
    var closedAfterFailure = false;
    var retryEntry = "";
    var closedAfterRetry = false;
    GroupedHostTicket ticket = default;
    try
    {
        failure = CatchAny(() => session.Dispose());
        closedAfterFailure = session.IsClosed;
        retryEntry = CatchAny(() => session.InvokeAuthor(1)).Message;
        session.Dispose();
        ticket = session.Close();
        closedAfterRetry = session.IsClosed;
    }
    finally
    {
        contexts.Framework.Unloading -= handler;
    }
    return new UnloadCaseResult(failure, closedAfterFailure, retryEntry, ticket, frameworkCalls, 0, closedAfterRetry);
}

internal sealed record GroupEvidence(
    GroupedHostSession Session,
    GroupedHostCleanupToken Token,
    GroupedHostTicket Ticket,
    TestHost Host,
    int[] Results,
    int RetainedBeforeRelease);

internal sealed class NotRunException(string reason) : Exception(reason);

internal sealed class UnloadHandlerException : Exception
{
    public UnloadHandlerException(string message) : base(message)
    {
    }
}

internal sealed record UnloadCaseResult(
    Exception? Failure,
    bool ClosedAfterFailure,
    string RetryEntryError,
    GroupedHostTicket Ticket,
    int FrameworkUnloadCalls,
    int AuthorUnloadCalls,
    bool ClosedAfterRetry);

internal static class FixtureMode
{
    /// <summary>Selected framework role image for this process.</summary>
    public static bool PortableFramework { get; set; }
}

internal static class Evidence
{
    /// <summary>Closed groups, tokens and terminal tickets retained on purpose.</summary>
    public static List<GroupEvidence> Retained { get; } = [];
}
