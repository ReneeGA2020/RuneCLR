using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using OrbitGame.Contracts;
using RuneCLR.TrustedUpdate;

static class DistinctHttpDriver
{
    const string Entry = "OrbitGame.Module.dll";
    const string TypeName = "OrbitGame.OrbitRules";
    const string MethodName = "Step";

    public static int Run(string output)
    {
        Directory.CreateDirectory(output);
        var timeline = Path.Combine(output, "timeline.txt");
        void Mark(string text) => File.AppendAllText(timeline, DateTime.UtcNow.ToString("o") + " " + text + Environment.NewLine);
        Mark("start");
        var contract = Path.Combine(AppContext.BaseDirectory, "OrbitGame.Contracts.dll");
        if (!File.Exists(contract))
            return Fail(output, "missing-contract");
        var sealDir = Path.Combine(output, "seal");
        Directory.CreateDirectory(sealDir);
        var sealedContract = Path.Combine(sealDir, "OrbitGame.Contracts.dll");
        File.Copy(contract, sealedContract, true);
        var sealHash = Sha(sealedContract);
        File.WriteAllText(Path.Combine(output, "seal.json"), JsonSerializer.Serialize(new { contract = sealedContract, sha256 = sealHash, sdk = SdkVersion() }));
        Mark("sealed " + sealHash);
        var late = Path.Combine(output, "late");
        WriteModule(Path.Combine(late, "a"), sealedContract, 3);
        WriteModule(Path.Combine(late, "b"), sealedContract, 5);
        Mark("sources-written");
        if (Build(Path.Combine(late, "a"), Path.Combine(output, "build-a")) != 0)
            return Fail(output, "build-a");
        if (Build(Path.Combine(late, "b"), Path.Combine(output, "build-b")) != 0)
            return Fail(output, "build-b");
        if (!string.Equals(Sha(sealedContract), sealHash, StringComparison.OrdinalIgnoreCase))
            return Fail(output, "seal-changed");
        var dllA = Path.Combine(late, "a", "out", Entry);
        var dllB = Path.Combine(late, "b", "out", Entry);
        var hashA = Sha(dllA);
        var hashB = Sha(dllB);
        File.WriteAllText(Path.Combine(output, "modules.json"), JsonSerializer.Serialize(new { a = hashA, b = hashB, same = string.Equals(hashA, hashB, StringComparison.OrdinalIgnoreCase) }));
        if (string.Equals(hashA, hashB, StringComparison.OrdinalIgnoreCase))
            return Fail(output, "modules-identical");
        Mark("modules " + hashA + " " + hashB);
        string spkiPath = Path.Combine(output, "host.spki");
        byte[] docA;
        byte[] docB;
        using (var key = ECDsa.Create(ECCurve.NamedCurves.nistP256))
        {
            File.WriteAllBytes(spkiPath, key.ExportSubjectPublicKeyInfo());
            docA = Sign(key, Path.Combine(late, "a", "out"), "A");
            docB = Sign(key, Path.Combine(late, "b", "out"), "B");
        }
        if (docA.Length == 0 || docB.Length == 0)
            return Fail(output, "sign");
        var serverRoot = Path.Combine(output, "server-root");
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-a"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-b"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "bad-body"));
        File.WriteAllBytes(Path.Combine(serverRoot, "a.bin"), docA);
        File.WriteAllBytes(Path.Combine(serverRoot, "b.bin"), docB);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-a", Entry), true);
        File.Copy(dllB, Path.Combine(serverRoot, "orbit-b", Entry), true);
        var bad = File.ReadAllBytes(dllB);
        bad[^1] ^= 0xFF;
        File.WriteAllBytes(Path.Combine(serverRoot, "bad-body", Entry), bad);
        if (File.Exists(Path.Combine(output, "private-key.bin")) || File.Exists(Path.Combine(output, "host.pkcs8")))
            return Fail(output, "key-persisted");
        Mark("signed-public-only");
        var world = Path.Combine(output, "world");
        var releases = Path.Combine(world, "releases");
        var receipt = Path.Combine(world, "state", "receipt.bin");
        Directory.CreateDirectory(releases);
        Directory.CreateDirectory(Path.GetDirectoryName(receipt)!);
        var finalA = Path.Combine(releases, "published-a");
        var verifiedB = Path.Combine(releases, "verified-b");
        var publishedB = Path.Combine(releases, "published-b");
        var finalBad = Path.Combine(releases, "published-bad-b");
        var problems = new List<string>();
        RunLane(output, "offer-a", true, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems);
        var receiptA = File.Exists(receipt) ? File.ReadAllBytes(receipt) : Array.Empty<byte>();
        var publishedAHash = File.Exists(Path.Combine(finalA, Entry)) ? Sha(Path.Combine(finalA, Entry)) : "";
        RunLane(output, "restore-a", false, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems);
        if (!Same(receipt, receiptA))
            problems.Add("restore-a-receipt");
        RunLane(output, "bad-b", true, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems);
        if (!Same(receipt, receiptA) || Directory.Exists(finalBad))
            problems.Add("bad-b-residue");
        RunLane(output, "offer-b", true, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems);
        var receiptB = File.Exists(receipt) ? File.ReadAllBytes(receipt) : Array.Empty<byte>();
        if (receiptB.Length == 0 || receiptB.AsSpan().SequenceEqual(receiptA) || Sha(Path.Combine(finalA, Entry)) != publishedAHash)
            problems.Add("offer-b-preservation");
        if (Sha(Path.Combine(publishedB, Entry)) != hashB || Sha(Path.Combine(verifiedB, Entry)) != hashB || publishedAHash != hashA)
            problems.Add("content-hash");
        RunLane(output, "restore-b", false, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems);
        if (!Same(receipt, receiptB))
            problems.Add("restore-b-receipt");
        var report = problems.Count == 0 ? "DISTINCT_HTTP_OBSERVED" : "DISTINCT_HTTP_FAIL " + string.Join(",", problems);
        Console.WriteLine(report);
        File.WriteAllText(Path.Combine(output, "driver-result.txt"), report + Environment.NewLine);
        Mark(report);
        return problems.Count == 0 ? 0 : 1;
    }

    public static int Child(string mode, string requestPath)
    {
        var map = File.ReadAllLines(requestPath).Select(line => line.Split('=', 2)).Where(part => part.Length == 2).ToDictionary(part => part[0], part => part[1]);
        try
        {
            return mode switch
            {
                "offer-a" => OfferA(map),
                "restore-a" => Restore(map, "A", 3),
                "bad-b" => BadB(map),
                "offer-b" => OfferB(map),
                "restore-b" => Restore(map, "B", 5),
                _ => FailMode("mode"),
            };
        }
        finally
        {
            if (HttpReleaseFetch.IsBound)
            {
                HttpReleaseFetch.Print();
                HttpReleaseFetch.Unbind();
            }
        }
    }

    static int OfferA(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalA", "documentA", "contentA"))
            return FailMode("stage-a");
        var before = Activations;
        var started = Offer(map, map["finalA"], File.ReadAllBytes(map["documentA"]));
        Console.WriteLine("START " + Describe(started) + " activations=" + Activations);
        if (!started.Activated || started.Source != TrustedUpdateStartSource.Candidate || started.SelectedVersion != "A" || !DistinctOrbit.Publish(started))
            return FailMode("start-a");
        if (Activations != before + 1)
            return FailMode("activation-count");
        if (!Play("A", 3, map["finalA"]))
            return FailMode("play-a");
        var receipt = File.ReadAllBytes(map["receipt"]);
        if (!HttpReleaseFetch.Stage(map, "finalVerifiedB", "documentB", "contentB"))
            return FailMode("stage-b-pre");
        var verified = Path.Combine(map["finalVerifiedB"], Entry);
        Console.WriteLine("VERIFY_B path=" + verified + " sha256=" + Sha(verified) + " sourceFolder=" + verified.Contains("late", StringComparison.OrdinalIgnoreCase));
        var lockedBefore = Activations;
        var locked = Offer(map, map["finalVerifiedB"], File.ReadAllBytes(map["documentB"]));
        Console.WriteLine("LOCK " + Describe(locked) + " activations=" + Activations);
        if (locked.Activated || locked.Candidate.Plan != TrustedUpdateFailure.ProcessSelectionLocked || Activations != lockedBefore)
            return FailMode("lock");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("lock-receipt");
        Console.WriteLine("DISTINCT_OK offer-a");
        return 0;
    }

    static int OfferB(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (Directory.Exists(map["finalB"]))
            return FailMode("final-b-exists");
        if (!HttpReleaseFetch.Stage(map, "finalB", "documentB", "contentB"))
            return FailMode("stage-b");
        var started = Offer(map, map["finalB"], File.ReadAllBytes(map["documentB"]));
        Console.WriteLine("START " + Describe(started) + " activations=" + Activations);
        if (!started.Activated || started.Source != TrustedUpdateStartSource.Candidate || started.SelectedVersion != "B" || !DistinctOrbit.Publish(started))
            return FailMode("start-b");
        if (!Play("B", 5, map["finalB"]))
            return FailMode("play-b");
        Console.WriteLine("DISTINCT_OK offer-b");
        return 0;
    }

    static int BadB(Dictionary<string, string> map)
    {
        var receipt = File.ReadAllBytes(map["receipt"]);
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        var staged = HttpReleaseFetch.Stage(map, "finalBad", "documentB", "contentB");
        Console.WriteLine("BAD_STAGE staged=" + staged + " exists=" + Directory.Exists(map["finalBad"]) + " activations=" + Activations);
        if (staged || Directory.Exists(map["finalBad"]) || Activations != 0)
            return FailMode("bad-stage");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("bad-receipt");
        HttpReleaseFetch.Print();
        HttpReleaseFetch.Unbind();
        return Restore(map, "A", 3);
    }

    static int Restore(Dictionary<string, string> map, string version, int delta)
    {
        var before = File.ReadAllBytes(map["receipt"]);
        var started = TrustedReleaseRecovery.TryStart(null, File.ReadAllBytes(map["spki"]), DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate);
        Console.WriteLine("RECOVER " + Describe(started) + " activations=" + Activations);
        if (!started.Activated || started.Source != TrustedUpdateStartSource.LastKnownGood || started.SelectedVersion != version || !DistinctOrbit.Publish(started))
            return FailMode("restore");
        var final = version == "A" ? map["finalA"] : map["finalB"];
        if (!Play(version, delta, final))
            return FailMode("restore-play");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(before))
            return FailMode("restore-receipt");
        Console.WriteLine("DISTINCT_OK restore-" + version.ToLowerInvariant());
        return 0;
    }

    static bool Play(string version, int delta, string final)
    {
        var modulePath = Path.GetFullPath(Path.Combine(final, Entry));
        Console.WriteLine("MODULE path=" + modulePath + " sha256=" + Sha(modulePath));
        if (modulePath.Contains(Path.DirectorySeparatorChar + "late" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            return false;
        var owner = DistinctOrbit.Owner!;
        var host = new CountingOrbitHost();
        if (host.Position != 0 || host.Calls != 0 || !owner.TryOpen(out var session, out _) || session is null)
            return false;
        var expected = new[] { 0, delta, delta * 2 };
        if (!Step(session, host, version, "start", module => module.Start(host), expected[0], 0))
            return false;
        if (!Step(session, host, version, "step1", module => module.Step(host), expected[1], 1))
            return false;
        if (!Step(session, host, version, "step2", module => module.Step(host), expected[2], 2))
            return false;
        return true;
    }

    static bool Step(TypedSession<IOrbitRules> session, CountingOrbitHost host, string version, string kind, Func<IOrbitRules, int> call, int expected, int calls)
    {
        var result = session.Invoke(call);
        Console.WriteLine("RECORD version=" + version + " kind=" + kind + " value=" + result.Value + " position=" + host.Position + " calls=" + host.Calls + " completed=" + result.Completed + " failure=" + result.Failure);
        return result.Completed && result.Failure.Length == 0 && result.Value == expected && host.Position == expected && host.Calls == calls;
    }

    static TrustedReleaseRecoveryStart Offer(Dictionary<string, string> map, string final, byte[] document) =>
        TrustedReleaseRecovery.TryStart(new TrustedReleaseOffer(final, document), File.ReadAllBytes(map["spki"]), DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate);

    static string Describe(TrustedReleaseRecoveryStart started) =>
        "activated=" + started.Activated + " version=" + started.SelectedVersion + " source=" + started.Source + " plan=" + started.Candidate.Plan + " detail=" + started.Candidate.Detail;

    static int Activations => DistinctOrbit.Activations;

    static void RunLane(string output, string mode, bool server, string serverRoot, string releases, string receipt, string spki, string finalA, string verifiedB, string publishedB, string finalBad, List<string> problems)
    {
        var lane = Path.Combine(output, "lanes", mode);
        Directory.CreateDirectory(lane);
        int port = 0;
        Process? serverProcess = null;
        if (server)
        {
            var portFile = Path.Combine(lane, "port.txt");
            var log = Path.Combine(lane, "server.log");
            var stall = Path.Combine(lane, "stall.signal");
            File.WriteAllText(log, "");
            serverProcess = Start(new[] { "--http-server", serverRoot, portFile, log, stall }, lane, "server");
            if (!WaitFile(portFile, 10000))
            {
                Stop(serverProcess, lane, "server");
                problems.Add(mode + ":no-port");
                return;
            }
            port = int.Parse(File.ReadAllText(portFile).Trim());
        }
        var badBase = server && mode == "bad-b";
        var request = Path.Combine(lane, "request.txt");
        File.WriteAllLines(request, new[]
        {
            "releases=" + releases,
            "receipt=" + receipt,
            "spki=" + spki,
            "finalA=" + finalA,
            "finalVerifiedB=" + verifiedB,
            "finalB=" + publishedB,
            "finalBad=" + finalBad,
            "documentA=" + Path.Combine(lane, "document-a.bin"),
            "documentB=" + Path.Combine(lane, "document-b.bin"),
            "documentAUrl=http://127.0.0.1:" + port + "/a.bin",
            "documentBUrl=http://127.0.0.1:" + port + "/b.bin",
            "contentBaseA=http://127.0.0.1:" + port + "/orbit-a/",
            "contentBaseB=http://127.0.0.1:" + port + "/" + (badBase ? "bad-body" : "orbit-b") + "/",
            "filesA=" + Entry,
            "filesB=" + Entry,
            "entry=" + Entry,
        });
        CopyReceipt(output, mode + "-before", receipt);
        var client = Start(new[] { "--distinct-http-child", mode, request }, lane, "client");
        var finished = Finish(client, lane, "client", 20000);
        if (serverProcess is not null)
            Stop(serverProcess, lane, "server");
        CopyReceipt(output, mode + "-after", receipt);
        var stdout = File.ReadAllText(Path.Combine(lane, "client.stdout"));
        if (finished.Watchdog || finished.Exit != 0 || !stdout.Contains("DISTINCT_OK", StringComparison.Ordinal))
            problems.Add(mode);
        if (mode == "bad-b" && !stdout.Contains("verification=ContentMismatch", StringComparison.Ordinal))
            problems.Add("bad-b-mismatch");
        if (!server && (stdout.Contains("HTTP_FETCH ", StringComparison.Ordinal) || stdout.Contains("HTTP_DEADLINE_MS", StringComparison.Ordinal)))
            problems.Add(mode + ":network");
        Console.WriteLine("LANE " + mode + " pid=" + finished.Pid + " exit=" + finished.Exit + " watchdog=" + finished.Watchdog + " server=" + server);
    }

    static void CopyReceipt(string output, string name, string receipt)
    {
        var dest = Path.Combine(output, "receipts");
        Directory.CreateDirectory(dest);
        if (File.Exists(receipt))
            File.Copy(receipt, Path.Combine(dest, name + ".bin"), true);
    }

    static bool Same(string path, byte[] expected) => File.Exists(path) && File.ReadAllBytes(path).AsSpan().SequenceEqual(expected);

    static Process Start(string[] args, string lane, string role)
    {
        var exe = Environment.ProcessPath ?? throw new InvalidOperationException("host");
        var info = new ProcessStartInfo(exe) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
        info.Environment["TRUSTED_COMPOSITION_WITNESS"] = "0";
        info.Environment["DOTNET_ReadyToRun"] = "0";
        info.Environment["DOTNET_TieredCompilation"] = "0";
        info.Environment["DOTNET_TC_QuickJit"] = "0";
        info.Environment["DOTNET_MULTILEVEL_LOOKUP"] = "0";
        info.Environment["DOTNET_ROLL_FORWARD"] = "Disable";
        foreach (var arg in args)
            info.ArgumentList.Add(arg);
        var process = Process.Start(info) ?? throw new InvalidOperationException("start");
        var record = new
        {
            role,
            argv = new[] { exe }.Concat(args).ToArray(),
            pid = process.Id,
            host = exe,
            hostDll = Path.Combine(AppContext.BaseDirectory, "TrustedComposition.DeliveryHost.dll"),
            witness = "0",
            readyToRun = "0",
        };
        File.WriteAllText(Path.Combine(lane, role + ".started.json"), JsonSerializer.Serialize(record));
        return process;
    }

    static Finished Finish(Process process, string lane, string role, int timeoutMs)
    {
        var completed = process.WaitForExit(timeoutMs);
        if (!completed)
        {
            try { process.Kill(entireProcessTree: true); process.WaitForExit(5000); } catch (Exception) { }
        }
        var stdout = process.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        File.WriteAllText(Path.Combine(lane, role + ".stdout"), stdout);
        File.WriteAllText(Path.Combine(lane, role + ".stderr"), stderr);
        File.WriteAllText(Path.Combine(lane, role + ".exit"), process.ExitCode + " pid=" + process.Id + " watchdog=" + (!completed).ToString().ToLowerInvariant());
        return new Finished(process.Id, process.ExitCode, !completed);
    }

    static void Stop(Process process, string lane, string role)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(5000);
            }
        }
        catch (Exception) { }
        Finish(process, lane, role, 1000);
        File.WriteAllText(Path.Combine(lane, role + ".stopped"), "killed=true pid=" + process.Id + " exit=" + process.ExitCode);
    }

    static bool WaitFile(string path, int timeoutMs)
    {
        var started = Environment.TickCount64;
        while (Environment.TickCount64 - started < timeoutMs)
        {
            if (File.Exists(path) && new FileInfo(path).Length > 0)
                return true;
            Thread.Sleep(20);
        }
        return false;
    }

    static int Build(string dir, string logDir)
    {
        Directory.CreateDirectory(logDir);
        var info = new ProcessStartInfo("dotnet", "build mod.csproj -c Release --nologo")
        {
            WorkingDirectory = dir,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        var process = Process.Start(info) ?? throw new InvalidOperationException("build");
        var stdout = process.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        File.WriteAllText(Path.Combine(logDir, "stdout.txt"), stdout);
        File.WriteAllText(Path.Combine(logDir, "stderr.txt"), stderr);
        File.WriteAllText(Path.Combine(logDir, "exit.txt"), process.ExitCode + " pid=" + process.Id);
        return process.ExitCode;
    }

    static void WriteModule(string dir, string contract, int delta)
    {
        Directory.CreateDirectory(dir);
        var source = "using OrbitGame.Contracts; namespace OrbitGame; public sealed class OrbitRules : IOrbitRules { public static int Constructions; public OrbitRules() { Constructions++; } public int Start(IOrbitHost host) => host.Position; int steps; [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)] public int Step(IOrbitHost host) { steps++; if (steps > 2) throw new InvalidOperationException(\"orbit-stop\"); return host.Move(" + delta + "); } }";
        File.WriteAllText(Path.Combine(dir, "Module.cs"), source);
        File.WriteAllText(Path.Combine(dir, "mod.csproj"), "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net11.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><TreatWarningsAsErrors>true</TreatWarningsAsErrors><AssemblyName>OrbitGame.Module</AssemblyName><EnableDefaultCompileItems>false</EnableDefaultCompileItems><OutputPath>out/</OutputPath><AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath></PropertyGroup><ItemGroup><Compile Include=\"Module.cs\" /><Reference Include=\"OrbitGame.Contracts\"><HintPath>" + contract + "</HintPath><Private>false</Private></Reference></ItemGroup></Project>");
    }

    static byte[] Sign(ECDsa key, string dir, string version)
    {
        var signed = TrustedRelease.Sign(dir, new TrustedReleaseIdentity(version, "net11.0", DeliverySession.Target.Architecture, TypeName, MethodName, Entry), new[] { Entry }, key);
        return signed.Succeeded && signed.Document is not null ? signed.Document : Array.Empty<byte>();
    }

    static string SdkVersion()
    {
        var info = new ProcessStartInfo("dotnet", "--version") { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
        var process = Process.Start(info);
        if (process is null)
            return "";
        var version = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        return version;
    }

    static string Sha(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    static int Fail(string output, string reason)
    {
        Console.Error.WriteLine("DISTINCT_FAIL " + reason);
        File.WriteAllText(Path.Combine(output, "driver-result.txt"), "DISTINCT_FAIL " + reason + Environment.NewLine);
        return 1;
    }

    static int FailMode(string reason)
    {
        Console.Error.WriteLine("DISTINCT_BAD " + reason);
        return 1;
    }

    readonly record struct Finished(int Pid, int Exit, bool Watchdog);
}

static class DistinctOrbit
{
    static ResidentVersion<IOrbitRules>? pending;
    public static ResidentVersion<IOrbitRules>? Owner { get; private set; }
    public static int Activations { get; private set; }

    public static TrustedUpdateActivation Activate(TrustedUpdateCandidate candidate, TrustedUpdateStartSource source, TrustedUpdateFailure _)
    {
        Activations++;
        Console.WriteLine("ACTIVATE version=" + candidate.VersionName + " source=" + source + " path=" + candidate.AssemblyPath);
        if (Owner is not null)
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        if (!ResidentVersion<IOrbitRules>.TryBind(candidate, "OrbitGame.OrbitRules", "Step", out var bound, out var failure))
        {
            Console.WriteLine("BIND " + failure);
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }
        pending = bound;
        Console.WriteLine("BOOT " + candidate.VersionName + " source=" + source);
        return new TrustedUpdateActivation(TrustedUpdateFailure.None, 0);
    }

    public static bool Publish(TrustedReleaseRecoveryStart started)
    {
        if (!started.Activated || pending is null)
        {
            pending = null;
            return false;
        }
        Owner = pending;
        pending = null;
        return true;
    }
}

sealed class CountingOrbitHost : IOrbitHost
{
    public int Calls { get; private set; }
    public int Position { get; private set; }
    public int Move(int delta) { Calls++; Position += delta; return Position; }
}
