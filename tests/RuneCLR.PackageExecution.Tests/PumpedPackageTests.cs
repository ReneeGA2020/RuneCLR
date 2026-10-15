using System.Runtime.CompilerServices;
using RuneCLR.Packages;
using RuneCLR.Runtime;

namespace RuneCLR.PackageExecution.Tests;

public static partial class PackageExecutionHarness
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (MapRunResult Result, MapSession? Session) Execute(MapPackage package, MapRunOptions options, bool pump)
    {
        if (!pump) return (new MapRunner().Run(package, options), null);
        using var session = new MapRunner().Start(package, options);
        if (session.IsRunning)
        {
            Running(session, 0);
            for (var index = 0; index < options.TickCount; index++)
            {
                Require(session.Tick(options.TickDuration), "Expected a successful host-scheduled tick.");
                Running(session, index + 1);
            }
        }
        var result = session.Stop();
        Stopped(session, result);
        return (result, session);
    }

    private static IEnumerable<(string Name, Action Test)> PumpedCases(string root, MapRunOptions options, Action<MapRunResult> proof)
    {
        string Manifest(string name) => Path.Combine(root, name, PackageFormat.ManifestFileName);
        void Recovery() => Successful(Manifest("source"), ["starts=1", "tick=0", "tick=1", "stopped"], options, proof, pump: true);
        yield return ("Pumped source and same-name private versions overlap without sharing state",
            () => OverlappingPackages(root, options, proof));
        yield return ("Pumped package stops before its first scheduled tick",
            () => StopBeforeTick(Manifest("source"), options, proof));
        yield return ("Pumped package receives host deltas and continues beyond TickCount",
            () => HostDeltas(Manifest("frames"), options, proof));
        yield return ("Pumped tick and stop failures clean up and allow a fresh package", () =>
        {
            ScheduledFailures(Manifest("tick-failure"), Manifest("stop-failure"), options, proof, Recovery);
        });
        yield return ("Prevalidated package rejects changed entry bytes before loading author code", () =>
        {
            WithPackageCopy(Manifest("source"), manifest =>
            {
                var package = MapPackage.FromManifest(manifest);
                using (var stream = new FileStream(package.AssemblyPath, FileMode.Append)) stream.WriteByte(1);
                RejectedBeforeAuthorLoad(package, options, "hash");
            });
            Recovery();
        });
        yield return ("Prevalidated package rejects a newly rehashed manifest before loading author code", () =>
        {
            WithPackageCopy(Manifest("source"), path =>
            {
                var package = MapPackage.FromManifest(path);
                var manifest = PackageManifestIO.Read(path) with { Id = "ChangedAfterValidation" };
                manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
                PackageManifestIO.Write(path, manifest);
                RejectedBeforeAuthorLoad(package, options, "manifest changed");
            });
            Recovery();
        });
        yield return ("Prevalidated package rejects a rewritten entry snapshot before loading author code", () =>
        {
            WithPackageCopy(Manifest("source"), manifest =>
            {
                var package = MapPackage.FromManifest(manifest);
                RejectedBeforeAuthorLoad(package with { EntryType = "ChangedAfterValidation" }, options, "cannot be modified");
            });
            Recovery();
        });
    }

    private static void Running(MapSession session, int ticks)
    {
        Require(session.IsRunning && session.Result is null && session.CompletedTicks == ticks,
            "Host return did not preserve the running session and successful tick index.");
    }

    private static void Stopped(MapSession session, MapRunResult result)
    {
        Require(!session.IsRunning && ReferenceEquals(session.Result, result) &&
            ReferenceEquals(session.Stop(), result) && session.CompletedTicks == result.Report.CompletedTicks,
            "Stopped session state or stable final result changed.");
        session.Dispose();
        Require(ReferenceEquals(session.Result, result), "Dispose replaced the final result.");
        try { session.Tick(); }
        catch (InvalidOperationException) { return; }
        throw new InvalidOperationException("Stopped session accepted another author tick.");
    }

    private static void OverlappingPackages(string root, MapRunOptions options, Action<MapRunResult> proof)
    {
        MapPackage Package(string name) => MapPackage.FromManifest(Path.Combine(root, name, PackageFormat.ManifestFileName));
        using var source = new MapRunner().Start(Package("source"), options);
        using var sourceAgain = new MapRunner().Start(Package("source"), options);
        using var a = new MapRunner().Start(Package("private-a"), options);
        using var b = new MapRunner().Start(Package("private-b"), options);
        var sessions = new[] { source, sourceAgain, a, b };
        foreach (var session in sessions) Running(session, 0);
        Require(source.Tick() && b.Tick() && sourceAgain.Tick() && a.Tick(), "Overlapping first tick failed.");
        var resultA = a.Stop();
        Completed(a, resultA, 1, ["A:1:1", "stopped"], proof);
        CleanedAndCollected(resultA);
        // Retiring A must not retire B or either independently loaded source instance.
        foreach (var session in new[] { source, sourceAgain, b })
        {
            Running(session, 1);
            Require(session.Tick(), "A surviving session could not advance after another package retired.");
        }
        var resultB = b.Stop();
        Completed(b, resultB, 2, ["B:1:1", "stopped"], proof);
        CleanedAndCollected(resultB);
        foreach (var session in new[] { source, sourceAgain })
        {
            var result = session.Stop();
            Completed(session, result, 2, ["starts=1", "tick=0", "tick=1", "stopped"], proof);
            CleanedAndCollected(result);
        }
        GC.KeepAlive(sessions);
    }

    private static void StopBeforeTick(string manifest, MapRunOptions options, Action<MapRunResult> proof)
    {
        using var session = new MapRunner().Start(MapPackage.FromManifest(manifest), options);
        Running(session, 0);
        var result = session.Stop();
        Completed(session, result, 0, ["starts=1", "stopped"], proof);
        CleanedAndCollected(result);
        GC.KeepAlive(session);
    }

    private static void HostDeltas(string manifest, MapRunOptions options, Action<MapRunResult> proof)
    {
        using var session = new MapRunner().Start(MapPackage.FromManifest(manifest), options with { TickCount = 0 });
        Running(session, 0);
        Require(session.Tick(TimeSpan.FromMilliseconds(5)), "First custom-delta tick failed.");
        Running(session, 1);
        Require(session.Tick(TimeSpan.FromMilliseconds(17)), "Second custom-delta tick failed.");
        Running(session, 2);
        var result = session.Stop();
        Completed(session, result, 2, ["started", "tick=0:delta=50000:total=50000", "tick=1:delta=170000:total=220000", "stopped"], proof);
        CleanedAndCollected(result);
        GC.KeepAlive(session);
    }

    private static void Completed(MapSession session, MapRunResult result, int ticks, string[] logs, Action<MapRunResult> proof)
    {
        Stopped(session, result);
        proof(result);
        Require(result.Report.Outcome == MapRunOutcome.Completed && result.Report.CompletedTicks == ticks,
            result.Report.Error ?? "Unexpected pumped completion or tick count.");
        Require(result.Report.Logs.SequenceEqual(logs), "Pumped callback order, host delta or isolated static state changed.");
    }

    private static void ScheduledFailures(string tickManifest, string stopManifest, MapRunOptions options, Action<MapRunResult> proof, Action recover)
    {
        using (var session = new MapRunner().Start(MapPackage.FromManifest(tickManifest), options))
        {
            Running(session, 0);
            Require(session.Tick(), "First tick should return normally.");
            Running(session, 1);
            Require(!session.Tick(TimeSpan.FromMilliseconds(17)), "Author failure should close the session.");
            var result = session.Result ?? throw new InvalidOperationException("Tick failure did not publish a final result.");
            Failed(session, result, 1, ["tick=0", "stopped-after-tick-error"], proof);
            CleanedAndCollected(result);
            GC.KeepAlive(session);
        }
        recover();
        using (var session = new MapRunner().Start(MapPackage.FromManifest(stopManifest), options))
        {
            Running(session, 0);
            Require(session.Tick(), "Tick before stop failure did not succeed.");
            Running(session, 1);
            var result = session.Stop();
            Failed(session, result, 1, ["tick=0"], proof);
            Require(result.Report.Error!.Contains("OnStop:", StringComparison.Ordinal), "Stop failure lost its callback context.");
            CleanedAndCollected(result);
            GC.KeepAlive(session);
        }
        recover();
    }

    private static void Failed(MapSession session, MapRunResult result, int ticks, string[] logs, Action<MapRunResult> proof)
    {
        Stopped(session, result);
        proof(result);
        Require(result.Report.Outcome == MapRunOutcome.Failed && result.Report.CompletedTicks == ticks &&
            result.Report.Error?.Contains("AuthorFailureException", StringComparison.Ordinal) == true,
            "Author failure did not preserve successful ticks and a host-owned error.");
        Require(result.Report.Logs.SequenceEqual(logs), "Author failure changed callback order or cleanup logs.");
    }

    private static void RejectedBeforeAuthorLoad(MapPackage package, MapRunOptions options, string expectedReason)
    {
        var authorLoads = 0;
        void Observe(object? sender, AssemblyLoadEventArgs loaded)
        {
            if (loaded.LoadedAssembly.IsCollectible) authorLoads++;
        }
        AppDomain.CurrentDomain.AssemblyLoad += Observe;
        var rejected = false;
        try
        {
            try { using var unexpected = new MapRunner().Start(package, options); }
            catch (InvalidDataException error)
            {
                Require(error.Message.Contains(expectedReason, StringComparison.OrdinalIgnoreCase),
                    "Prevalidated package failed for an unexpected reason: " + error.Message);
                rejected = true;
            }
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= Observe; }
        Require(rejected && authorLoads == 0, "Changed prevalidated package loaded author code or passed admission.");
    }

    private static void WithPackageCopy(string sourceManifest, Action<string> test)
    {
        var parent = Path.GetFullPath(Path.GetTempPath());
        var directory = Path.Combine(parent, "runeclr-pumped-package-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var source = Path.GetDirectoryName(sourceManifest)!;
            foreach (var input in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            {
                var output = Path.Combine(directory, Path.GetRelativePath(source, input));
                Directory.CreateDirectory(Path.GetDirectoryName(output)!);
                File.Copy(input, output);
            }
            test(Path.Combine(directory, PackageFormat.ManifestFileName));
        }
        finally
        {
            var cleanup = Path.GetFullPath(directory);
            Require(Path.TrimEndingDirectorySeparator(Path.GetDirectoryName(cleanup)!) == Path.TrimEndingDirectorySeparator(parent) &&
                Path.GetFileName(cleanup).StartsWith("runeclr-pumped-package-", StringComparison.Ordinal), "Invalid temporary package cleanup target.");
            Directory.Delete(cleanup, recursive: true);
        }
    }
}
