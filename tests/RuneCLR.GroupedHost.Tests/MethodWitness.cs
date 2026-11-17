using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.GroupedHost.Fixtures;
using RuneCLR.Runtime;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>
/// Opt-in identity and lifecycle capture for the grouped method-witness milestone. It records exact
/// image MVIDs, per-method MetadataTokens, ALC names and fixture markers as scalars only; every record
/// stays witness_verified=false because no validated external execution records are consumed here.
/// </summary>
internal static class MethodWitness
{
    private static string FixturesRoot => Path.Combine(AppContext.BaseDirectory, "fixtures");

    private const string FrameworkAssembly = "RuneCLR.GroupedHost.Framework";
    private const string AuthorAssembly = "RuneCLR.GroupedHost.Author";
    private const string FrameworkType = "RuneCLR.GroupedHost.Fixtures.FrameworkEntry";
    private const string AuthorType = "RuneCLR.GroupedHost.Fixtures.AuthorEntry";

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int Run(bool fixtureOnly, string? jsonlPath)
    {
        var gate = new WitnessGate();
        using var log = new WitnessLog(jsonlPath);
        WitnessCheckpoint checkpoint;
        try { checkpoint = WitnessCheckpoint.Create(log.RunId); }
        catch (Exception error)
        {
            Console.WriteLine("checkpoint configuration error: " + error.Message);
            return 1;
        }
        using var checkpointScope = checkpoint;
        if (checkpoint.Enabled) Console.WriteLine("checkpoints enabled: " + checkpoint.CheckpointPath);
        Console.WriteLine("method-witness schema=runeclr-grouped-witness/1 witness_verified=false run=" + log.RunId + " pid=" + Environment.ProcessId);
        if (!OriginScanCapabilityPresent(out var capabilities))
        {
            Console.WriteLine("origin-scan capability: ABSENT (capabilities=" + capabilities + ")");
            Console.WriteLine("method-witness requires the private ordered cut with both switches; no identity records were produced");
            return 1;
        }
        Console.WriteLine("origin-scan capability: present (capabilities=" + capabilities + ")");

        try
        {
            var frameworkBytes = File.ReadAllBytes(Path.Combine(FixturesRoot, "framework", FrameworkAssembly + ".dll"));
            var authorABytes = File.ReadAllBytes(Path.Combine(FixturesRoot, "author-a", AuthorAssembly + ".dll"));
            var authorBBytes = File.ReadAllBytes(Path.Combine(FixturesRoot, "author-b", AuthorAssembly + ".dll"));
            var frameworkImage = WitnessCapture.ReadImage(frameworkBytes);
            var authorAImage = WitnessCapture.ReadImage(authorABytes);
            var authorBImage = WitnessCapture.ReadImage(authorBBytes);

            var frameworkTokens = new MethodTokens(
                WitnessCapture.FindMethodToken(frameworkBytes, FrameworkType, "Initialize"),
                WitnessCapture.FindMethodToken(frameworkBytes, FrameworkType, "Touch"),
                0, 0);
            var authorTokensA = new MethodTokens(0, 0,
                WitnessCapture.FindMethodToken(authorABytes, AuthorType, "Run"),
                WitnessCapture.FindMethodToken(authorABytes, AuthorType, "OnFrameworkEvent"));
            var authorTokensB = new MethodTokens(0, 0,
                WitnessCapture.FindMethodToken(authorBBytes, AuthorType, "Run"),
                WitnessCapture.FindMethodToken(authorBBytes, AuthorType, "OnFrameworkEvent"));
            gate.Check(frameworkTokens.FrameworkInitialize != 0 && frameworkTokens.FrameworkTouch != 0,
                "staged framework bytes must contain Initialize and Touch MethodDefs");
            gate.Check(authorTokensA.AuthorRun != 0 && authorTokensA.AuthorCallback != 0,
                "staged author A bytes must contain Run and OnFrameworkEvent MethodDefs");
            gate.Check(authorTokensB.AuthorRun != 0 && authorTokensB.AuthorCallback != 0,
                "staged author B bytes must contain Run and OnFrameworkEvent MethodDefs");
            Console.WriteLine("byte tokens: framework Initialize=0x" + frameworkTokens.FrameworkInitialize.ToString("X8")
                + " Touch=0x" + frameworkTokens.FrameworkTouch.ToString("X8")
                + " authorA Run=0x" + authorTokensA.AuthorRun.ToString("X8")
                + " OnFrameworkEvent=0x" + authorTokensA.AuthorCallback.ToString("X8"));

            var a1 = RunWitnessGroup("author-a", "A", 1, "A1", 1, frameworkImage, authorAImage, frameworkTokens, authorTokensA, checkpoint, log, gate);
            var b1 = RunWitnessGroup("author-b", "B", 2, "B1", 1, frameworkImage, authorBImage, frameworkTokens, authorTokensB, checkpoint, log, gate);
            var a2 = RunWitnessGroup("author-a", "A", 3, "A2", 2, frameworkImage, authorAImage, frameworkTokens, authorTokensA, checkpoint, log, gate);

            gate.Check(a1.AuthorToken != a2.AuthorToken, "author static token must reset between groups");
            gate.Check(a1.FrameworkToken != b1.FrameworkToken && b1.FrameworkToken != a2.FrameworkToken,
                "framework instance token must be fresh per group");
            gate.Check(a1.AuthorRun == 1 && b1.AuthorRun == 1 && a2.AuthorRun == 1,
                "author run counter must start at 1 per group");

            WaitForCollected(a1.Ticket, gate, "A group 1");
            WaitForCollected(b1.Ticket, gate, "B group");
            WaitForCollected(a2.Ticket, gate, "A group 2");

            var frameworkFailure = RunWitnessFailureGroup("author-a", frameworkFailure: true, 4, "failure-framework", gate);
            var authorFailure = RunWitnessFailureGroup("author-a", frameworkFailure: false, 5, "failure-author", gate);
            var recovered = RunWitnessGroup("author-a", "A", 6, "recovered", 5, frameworkImage, authorAImage, frameworkTokens, authorTokensA, checkpoint, log, gate);
            gate.Check(frameworkFailure.HostOwned, "framework failure must be a host-owned InvalidOperationException without inner");
            gate.Check(frameworkFailure.NamedFixtureType, "framework failure must name the bounded fixture exception type");
            gate.Check(authorFailure.HostOwned, "author failure must be a host-owned InvalidOperationException without inner");
            gate.Check(authorFailure.NamedFixtureType, "author failure must name the bounded fixture exception type");
            WaitForCollected(frameworkFailure.Ticket, gate, "framework failure group");
            WaitForCollected(authorFailure.Ticket, gate, "author failure group");
            WaitForCollected(recovered.Ticket, gate, "recovered group");

            RunObserverRootControl(log, gate);
        }
        catch (Exception error)
        {
            gate.Check(false, "unhandled: " + error.GetType().Name + ": " + error.Message);
        }

        Console.WriteLine(gate.Summary());
        if (!gate.Passed) return 1;
        if (fixtureOnly)
        {
            Console.WriteLine("FIXTURE-ONLY identity/lifecycle gates PASS (not a method witness; every record has witness_verified=false)");
            return 0;
        }
        Console.WriteLine("NOT-VERIFIED: no validated external execution records were supplied; every record has witness_verified=false");
        return 3;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static GroupResult RunWitnessGroup(string authorFolder, string tag, int groupOrdinal, string groupLabel,
        int value, WitnessImage frameworkImage, WitnessImage authorImage, MethodTokens frameworkTokens,
        MethodTokens authorTokens, WitnessCheckpoint checkpoint, WitnessLog log, WitnessGate gate)
    {
        var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
        var host = new TestHost();
        var session = GroupedHostSession.Open(Options(authorFolder), host);

        var frameworkInitialize = WitnessCapture.CaptureMethod("RuneCLR.Group.Framework:", known, FrameworkAssembly, FrameworkType, "Initialize", nonPublic: false);
        var frameworkTouch = WitnessCapture.CaptureMethod("RuneCLR.Group.Framework:", known, FrameworkAssembly, FrameworkType, "Touch", nonPublic: false);
        var authorRun = WitnessCapture.CaptureMethod("RuneCLR.Group.Author:", known, AuthorAssembly, AuthorType, "Run", nonPublic: false);
        var authorCallback = WitnessCapture.CaptureMethod("RuneCLR.Group.Author:", known, AuthorAssembly, AuthorType, "OnFrameworkEvent", nonPublic: true);

        gate.Check(frameworkInitialize is not null, "[" + groupLabel + "] framework Initialize identity was not captured");
        gate.Check(frameworkTouch is not null, "[" + groupLabel + "] framework Touch identity was not captured");
        gate.Check(authorRun is not null, "[" + groupLabel + "] author Run identity was not captured");
        gate.Check(authorCallback is not null, "[" + groupLabel + "] author OnFrameworkEvent identity was not captured");

        if (frameworkInitialize is { } fi)
        {
            gate.Check(fi.Mvid == frameworkImage.Mvid, "[" + groupLabel + "] loaded framework MVID must match the staged bytes");
            gate.Check(fi.MethodToken == frameworkTokens.FrameworkInitialize, "[" + groupLabel + "] loaded Initialize token must match the staged bytes");
            log.Write(Record("identity", "framework", 0, log, groupLabel, groupOrdinal, fi, frameworkImage, "identity", 0, ""));
        }
        if (frameworkTouch is { } ft)
        {
            gate.Check(ft.MethodToken == frameworkTokens.FrameworkTouch, "[" + groupLabel + "] loaded Touch token must match the staged bytes");
            log.Write(Record("identity", "framework", 0, log, groupLabel, groupOrdinal, ft, frameworkImage, "identity", 0, ""));
        }
        if (authorRun is { } ar)
        {
            gate.Check(ar.Mvid == authorImage.Mvid, "[" + groupLabel + "] loaded author MVID must match the staged bytes");
            gate.Check(ar.MethodToken == authorTokens.AuthorRun, "[" + groupLabel + "] loaded Run token must match the staged bytes");
            log.Write(Record("identity", "author", 0, log, groupLabel, groupOrdinal, ar, authorImage, "identity", 0, ""));
        }
        if (authorCallback is { } ac)
        {
            gate.Check(ac.MethodToken == authorTokens.AuthorCallback, "[" + groupLabel + "] loaded OnFrameworkEvent token must match the staged bytes");
            log.Write(Record("identity", "author", 0, log, groupLabel, groupOrdinal, ac, authorImage, "identity", 0, ""));
        }

        checkpoint.Enter(log, "before-framework", groupLabel, groupOrdinal);
        host.Mode = "witness:" + log.RunId;
        session.InvokeFramework();
        var frameworkMarkers = host.Lines("framework:witness-entry:");
        gate.Check(frameworkMarkers.Count == 1, "[" + groupLabel + "] framework witness marker is missing");
        if (frameworkInitialize is { } frameworkEntryIdentity && frameworkMarkers.Count == 1)
        {
            log.Write(Record("entry", "framework", 1, log, groupLabel, groupOrdinal, frameworkEntryIdentity, frameworkImage,
                "framework:witness-entry", ParseInt(frameworkMarkers[0], "count"), Field(frameworkMarkers[0], "token")));
        }

        checkpoint.Enter(log, "before-author", groupLabel, groupOrdinal);
        var result = session.InvokeAuthor(value);
        var expected = value + (tag == "B" ? 200 : 100);
        gate.Check(result == expected, "[" + groupLabel + "] author business result must be " + expected + "; saw " + result);
        var authorMarkers = host.Lines("author:" + tag + ":witness-entry:");
        gate.Check(authorMarkers.Count == 1, "[" + groupLabel + "] author witness marker is missing");
        if (authorRun is { } authorRunIdentity && authorMarkers.Count == 1)
        {
            log.Write(Record("entry", "author", 1, log, groupLabel, groupOrdinal, authorRunIdentity, authorImage,
                "author:witness-entry", ParseInt(authorMarkers[0], "run"), Field(authorMarkers[0], "token")));
        }

        var initBefore = host.Lines("framework:init:").Count;
        checkpoint.Enter(log, "before-callback", groupLabel, groupOrdinal);
        host.Mode = "witness-raise";
        session.InvokeFramework();
        var callbackMarkers = host.Lines("author:" + tag + ":witness-callback:");
        gate.Check(callbackMarkers.Count == 1, "[" + groupLabel + "] callback witness marker is missing");
        gate.Check(host.Lines("framework:init:").Count == initBefore,
            "[" + groupLabel + "] witness-raise must raise the event without reinitializing framework statics");
        if (authorCallback is { } callbackIdentity && callbackMarkers.Count == 1)
        {
            log.Write(Record("callback", "author", 1, log, groupLabel, groupOrdinal, callbackIdentity, authorImage,
                "author:witness-callback", 0, ""));
        }

        checkpoint.Enter(log, "before-cleanup", groupLabel, groupOrdinal);
        host.ReleaseRetained();
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        var ticket = session.Close();

        var initLine = host.Lines("framework:init:");
        var initialLine = host.Lines("author:" + tag + ":initial:");
        return new GroupResult(
            result,
            ticket,
            initLine.Count == 1 ? Field(initLine[0], "token") : string.Empty,
            initialLine.Count == 1 ? Field(initialLine[0], "token") : string.Empty,
            initialLine.Count == 1 ? ParseInt(initialLine[0], "run") : 0,
            frameworkInitialize?.Mvid ?? string.Empty,
            authorRun?.Mvid ?? string.Empty);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static FailureResult RunWitnessFailureGroup(string authorFolder, bool frameworkFailure,
        int groupOrdinal, string groupLabel, WitnessGate gate)
    {
        var host = new TestHost { Mode = frameworkFailure ? "throw-init" : "normal" };
        var session = GroupedHostSession.Open(Options(authorFolder), host);
        Exception? failure = null;
        if (frameworkFailure)
        {
            try { session.InvokeFramework(); }
            catch (Exception error) { failure = error; }
        }
        else
        {
            session.InvokeFramework();
            try { session.InvokeAuthor(-1); }
            catch (Exception error) { failure = error; }
        }
        var expectedType = frameworkFailure ? "FrameworkInitException" : "AuthorCallbackException";
        var hostOwned = failure is InvalidOperationException && failure.InnerException is null;
        var named = failure is not null && failure.Message.Contains(expectedType, StringComparison.Ordinal);
        gate.Check(failure is not null, "[" + groupLabel + "] the failure group did not fail");
        host.ReleaseRetained();
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        var ticket = session.Close();
        return new FailureResult(hostOwned, named, ticket);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static GroupedHostTicket RunRootedGroup(WitnessLog log, WitnessGate gate)
    {
        var known = new HashSet<AssemblyLoadContext>(AssemblyLoadContext.All, ReferenceEqualityComparer.Instance);
        var host = new TestHost { Mode = "witness:" + log.RunId };
        var session = GroupedHostSession.Open(Options("author-a"), host);
        session.InvokeFramework();
        session.InvokeAuthor(1);
        // Plant the deliberate host-side root while the author context definitely exists, before cleanup.
        WitnessCapture.PlantControlRoot("RuneCLR.Group.Author:", known, AuthorAssembly, AuthorType, "Run");
        gate.Check(WitnessControlRoot.Root is not null, "observer-root control could not plant the deliberate root");
        host.ReleaseRetained();
        var token = session.BeginCleanup();
        session.AcknowledgeCleanup(token);
        session.CompleteCleanup(token);
        return session.Close();
    }

    private static void RunObserverRootControl(WitnessLog log, WitnessGate gate)
    {
        var ticket = RunRootedGroup(log, gate);
        try
        {
            for (var attempt = 0; attempt < 8; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
                Thread.Sleep(10);
            }
            gate.Check(ticket.AuthorContext is { IsAlive: true },
                "observer-root control: the deliberate author root must keep the author context alive");
            Console.WriteLine("observer-root held: authorAlive=" + (ticket.AuthorContext is { IsAlive: true })
                + " frameworkAlive=" + (ticket.FrameworkContext is { IsAlive: true }));
        }
        finally
        {
            WitnessControlRoot.Root = null;
        }
        WaitForCollected(ticket, gate, "observer-root release");
    }

    private static void WaitForCollected(GroupedHostTicket ticket, WitnessGate gate, string what)
    {
        if (ticket.FrameworkContext is null || ticket.AuthorContext is null)
        {
            gate.Check(false, what + ": the terminal ticket is missing weak references");
            return;
        }
        for (var attempt = 0; attempt < 12 && (ticket.FrameworkContext.IsAlive || ticket.AuthorContext.IsAlive); attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
            Thread.Sleep(20);
        }
        gate.Check(!ticket.FrameworkContext.IsAlive, what + ": the framework context stayed alive");
        gate.Check(!ticket.AuthorContext.IsAlive, what + ": the author context stayed alive");
    }

    private static WitnessRecord Record(string phase, string role, int callOrdinal, WitnessLog log,
        string group, int groupOrdinal, WitnessGroupIdentity identity, WitnessImage image,
        string markerKind, int markerRun, string markerToken)
    {
        return new WitnessRecord(
            0,
            phase,
            role,
            callOrdinal,
            group,
            groupOrdinal,
            log.RunId,
            Environment.ProcessId,
            identity.SimpleName,
            identity.FullName,
            image.Sha256,
            identity.Mvid,
            image.Bytes,
            identity.AlcName,
            identity.MethodToken,
            identity.MethodHandle,
            identity.DeclaredEntry,
            markerKind,
            markerRun,
            markerToken,
            "host",
            false,
            string.Empty);
    }

    private static string Field(string line, string key)
    {
        var marker = ":" + key + "=";
        var index = line.IndexOf(marker, StringComparison.Ordinal);
        if (index < 0) return string.Empty;
        var start = index + marker.Length;
        var end = line.IndexOf(':', start);
        return end < 0 ? line[start..] : line[start..end];
    }

    private static int ParseInt(string line, string key)
    {
        return int.TryParse(Field(line, key), out var value) ? value : 0;
    }

    private static bool OriginScanCapabilityPresent(out int capabilities)
    {
        capabilities = -1;
        var policy = typeof(object).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", throwOnError: false);
        var method = policy?.GetMethod("RuneCLR_GetReflectionPolicyCapabilities", BindingFlags.NonPublic | BindingFlags.Static);
        if (method is null) return false;
        capabilities = (int)method.Invoke(null, null)!;
        return (capabilities & 1) != 0;
    }

    private static GroupedHostOptions Options(string authorFolder)
    {
        var contract = typeof(IGroupedHostContract);
        var frameworkDirectory = Path.Combine(FixturesRoot, "framework");
        var frameworkIdentity = AssemblyName.GetAssemblyName(Path.Combine(frameworkDirectory, FrameworkAssembly + ".dll")).FullName!;
        return new GroupedHostOptions
        {
            Contract = contract,
            FrameworkDirectory = frameworkDirectory,
            FrameworkAssembly = FrameworkAssembly + ".dll",
            FrameworkEntryType = FrameworkType,
            FrameworkEntryMethod = "Initialize",
            AuthorDirectory = Path.Combine(FixturesRoot, authorFolder),
            AuthorAssembly = AuthorAssembly + ".dll",
            AuthorEntryType = AuthorType,
            AuthorEntryMethod = "Run",
            AuthorApiPolicy = GroupedHostFixturePolicy.Create(contract.Assembly.FullName!, frameworkIdentity)
        };
    }

    private readonly record struct MethodTokens(int FrameworkInitialize, int FrameworkTouch, int AuthorRun, int AuthorCallback);

    private readonly record struct GroupResult(
        int Value,
        GroupedHostTicket Ticket,
        string FrameworkToken,
        string AuthorToken,
        int AuthorRun,
        string FrameworkMvid,
        string AuthorMvid);

    private readonly record struct FailureResult(bool HostOwned, bool NamedFixtureType, GroupedHostTicket Ticket);
}
