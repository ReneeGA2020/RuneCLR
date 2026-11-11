using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Reflection.Metadata;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OrbitBridge;
using RuneCLR.IpadDelivery;
using RuneCLR.TrustedUpdate;

/// <summary>
/// Real-flow acceptance for the portable bridge: a real HttpListener serves a signed document and
/// signed content built from real C# sources; DeliverAsync returns the verified offer; a separate
/// child process loads the author DLL through a collectible AssemblyLoadContext and executes the
/// author method against the shared Contract interface; a later offline child restores the
/// last-known-good release. Desktop stock JIT only: no device, no signing identity, no R2R.
/// </summary>
internal static class RealFlow
{
    private const string Entry = "Update.dll";
    private const string TypeName = "OrbitBridge.Rules";
    private const string MethodName = "Step";
    private const string ContractName = "OrbitBridge.Contracts";
    private static readonly TrustedUpdateTarget Target = new("ios-arm64", "arm64");
    private static int _run;
    private static int _pass;
    private static int _fail;

    private static void Check(bool ok, string name)
    {
        _run++;
        if (ok) _pass++; else _fail++;
        Console.WriteLine((ok ? "PASS " : "FAIL ") + name);
    }

    public static int Run(string outRoot)
    {
        // Everything the child receives must be absolute: the child working directory differs
        // between the apphost and "dotnet <dll>" launch forms.
        outRoot = Path.GetFullPath(outRoot);
        Directory.CreateDirectory(outRoot);
        var work = Path.Combine(outRoot, "work");
        if (Directory.Exists(work)) Directory.Delete(work, true);
        Directory.CreateDirectory(work);
        try { RunAsync(work).GetAwaiter().GetResult(); }
        catch (Exception error)
        {
            _run++;
            _fail++;
            Console.WriteLine("FAIL real-flow-exception " + error.GetType().Name + ": " + error.Message);
        }

        Console.WriteLine(_fail == 0
            ? "REAL-FLOW PASS " + _pass + "/" + _run
            : "REAL-FLOW FAIL " + _fail + "/" + _run + " (pass=" + _pass + ")");
        return _fail == 0 ? 0 : 1;
    }

    private static async Task RunAsync(string work)
    {
        var contractDll = Path.Combine(AppContext.BaseDirectory, ContractName + ".dll");
        if (!File.Exists(contractDll))
            throw new FileNotFoundException("contract fixture missing beside the self-test", contractDll);
        var identity = BridgeIdentity(contractDll);
        var contract = new RuntimeContractIdentity(identity.Name, identity.Version, Guid.Parse(identity.Mvid));

        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var spki = key.ExportSubjectPublicKeyInfo();
        var spkiPath = Path.Combine(work, "host.spki");
        File.WriteAllBytes(spkiPath, spki);

        var packageA = BuildAndSeal(work, "A", 3, contract, contractDll, key);
        var packageB = BuildAndSeal(work, "B", 5, contract, contractDll, key);

        var served = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        ServePackage(served, "a", packageA);
        ServePackage(served, "b", packageB);

        var releases = Path.Combine(work, "releases");
        Directory.CreateDirectory(releases);
        var receipt = Path.Combine(work, "state", "receipt.bin");
        Directory.CreateDirectory(Path.GetDirectoryName(receipt)!);

        DeliveryOptions Options(string final, TimeSpan? deadline = null, int maxDocument = 0, int maxSidecar = 0) => new()
        {
            HostSubjectPublicKeyInfo = spki,
            Target = Target,
            HostContract = contract,
            HostDeploymentContractPath = contractDll,
            AllowedReleasesRoot = releases,
            RecoveryReceiptPath = receipt,
            FinalReleaseDirectory = final,
            DownloadDeadline = deadline ?? TimeSpan.FromSeconds(10),
            MaxDocumentBytes = maxDocument == 0 ? TrustedRelease.MaxDocumentBytes : maxDocument,
            MaxCompatSidecarBytes = maxSidecar == 0 ? 64 * 1024 : maxSidecar,
        };

        using var server = TestServer.Start(served);
        Uri Uri(string path) => new("http://127.0.0.1:" + server.Port + path);

        // 1. Real download -> verified offer -> new process loads and executes the author module.
        var finalA = Path.Combine(releases, "A");
        var deliverA = await IpadDeliveryBridge.DeliverAsync(Options(finalA), Offer(Uri, "A", "a", packageA));
        if (!deliverA.Succeeded) Console.WriteLine("detail deliver-a " + deliverA.Failure + ":" + deliverA.Detail);
        Check(deliverA.Succeeded && deliverA.Offer is not null, "real.deliver.a.verified-offer");
        Check(deliverA.Offer is not null &&
              deliverA.Offer.SignedDocument.Span.SequenceEqual(packageA.Document), "real.offer.document-is-the-verified-download");
        var documentA = Path.Combine(work, "handoff-a.bin");
        File.WriteAllBytes(documentA, deliverA.Offer!.SignedDocument.ToArray());
        var childA = RunChild(work, "start", deliverA.Offer.ContentRoot, documentA, finalA, spkiPath, contractDll, contract, "A");
        Check(childA.Activated && childA.Value == 3 && childA.SharedContract && childA.PidMatches && childA.FreshResult &&
              childA.Version == "A", "real.start.a.author-business-3-shared-contract");

        // 2. A second, genuinely different signed version in a new process.
        var finalB = Path.Combine(releases, "B");
        var deliverB = await IpadDeliveryBridge.DeliverAsync(Options(finalB), Offer(Uri, "B", "b", packageB));
        if (!deliverB.Succeeded) Console.WriteLine("detail deliver-b " + deliverB.Failure + ":" + deliverB.Detail);
        Check(deliverB.Succeeded && deliverB.Offer is not null, "real.deliver.b.verified-offer");
        var documentB = Path.Combine(work, "handoff-b.bin");
        File.WriteAllBytes(documentB, deliverB.Offer!.SignedDocument.ToArray());
        var childB = RunChild(work, "start", deliverB.Offer.ContentRoot, documentB, finalB, spkiPath, contractDll, contract, "B");
        Check(childB.Activated && childB.Value == 5 && childB.SharedContract && childB.PidMatches && childB.FreshResult &&
              childB.Version == "B", "real.start.b.author-business-5-shared-contract");


        // 4. P1 pre-request rejections: no request, no write, receipt unchanged.
        var receiptBefore = File.ReadAllBytes(receipt);
        var requestsBefore = server.Requests;
        var outside = Path.Combine(work, "outside", "A");
        var outsideRejected = false;
        try { await IpadDeliveryBridge.DeliverAsync(Options(outside), Offer(Uri, "A", "a", packageA)); }
        catch (ArgumentException) { outsideRejected = true; }
        Check(outsideRejected && server.Requests == requestsBefore && !Directory.Exists(Path.GetDirectoryName(outside)) &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBefore), "real.reject.final-outside-root-before-request-or-write");

        var receiptInside = Path.Combine(releases, "state", "receipt.bin");
        var receiptInsideRejected = false;
        try
        {
            var bad = Options(Path.Combine(releases, "C")) with { RecoveryReceiptPath = receiptInside };
            await IpadDeliveryBridge.DeliverAsync(bad, Offer(Uri, "A", "a", packageA));
        }
        catch (ArgumentException) { receiptInsideRejected = true; }
        Check(receiptInsideRejected && server.Requests == requestsBefore && !Directory.Exists(Path.Combine(releases, "state")) &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBefore), "real.reject.receipt-inside-root-before-request-or-write");

        // 5. Expected entry metadata must match the signed manifest.
        var mismatchRejected = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "M")),
            Offer(Uri, "A", "a", packageA) with { EntryTypeName = "Not.The.Entry" });
        if (mismatchRejected.Failure != DeliveryFailure.None) Console.WriteLine("detail entry-mismatch " + mismatchRejected.Failure + ":" + mismatchRejected.Detail);
        Check(mismatchRejected.Failure == DeliveryFailure.VerificationFailed && mismatchRejected.Detail == "entry-type-mismatch" &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBefore), "real.reject.expected-entry-mismatch");

        // 6. Network failure shapes on the real server.
        var stall = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "S"), TimeSpan.FromMilliseconds(400)),
            Offer(Uri, "A", "a", packageA) with { DocumentUri = Uri("/stall/a/envelope") }, CancellationToken.None);
        Console.WriteLine("detail stall " + stall.Failure + ":" + stall.Detail);
        Check(stall.Failure == DeliveryFailure.DownloadFailed &&
              (stall.Detail == "OperationCanceledException" || stall.Detail == "TaskCanceledException"),
            "real.net.headers-then-body-stall-deadline");

        var partial = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "P")),
            Offer(Uri, "A", "a", packageA) with
            {
                Content = packageA.Files.Select(file => new DeliveryContentSource(file,
                    file == Entry ? Uri("/abort/a/" + Entry) : Uri("/a/" + file))).ToArray(),
            });
        Check(partial.Failure is DeliveryFailure.DownloadFailed or DeliveryFailure.StagingFailed &&
              !Directory.Exists(Path.Combine(releases, "P")) &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBefore), "real.net.partial-body-no-final-receipt-unchanged");

        var redirect = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "R")),
            Offer(Uri, "A", "a", packageA) with { DocumentUri = Uri("/redirect/envelope") });
        Check(redirect.Failure == DeliveryFailure.DownloadFailed, "real.net.redirect-refused");

        var capped = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "C2"), maxDocument: 8),
            Offer(Uri, "A", "a", packageA));
        Check(capped.Failure == DeliveryFailure.DownloadFailed, "real.net.document-byte-cap");

        using (var canceled = new CancellationTokenSource())
        {
            canceled.Cancel();
            var threw = false;
            try { await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "X")), Offer(Uri, "A", "a", packageA), canceled.Token); }
            catch (OperationCanceledException) { threw = true; }
            Check(threw, "real.net.caller-pre-canceled-token");
        }

        {
            // Cancel only after the server flushed headers and part of the body: this is a body-phase cancel.
            server.HeadersFlushed.Reset();
            using var bodyCancel = new CancellationTokenSource();
            var bodyCanceled = false;
            var pending = IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "YB"), TimeSpan.FromSeconds(20)),
                Offer(Uri, "A", "a", packageA) with { DocumentUri = Uri("/stall/a/envelope") }, bodyCancel.Token).AsTask();
            var flushed = server.HeadersFlushed.Wait(TimeSpan.FromSeconds(5));
            if (flushed)
                bodyCancel.Cancel();
            var bodyFailure = "";
            try { await pending; }
            catch (OperationCanceledException) { bodyCanceled = true; }
            catch (Exception error) { bodyFailure = error.GetType().Name; }
            var finalYB = Directory.Exists(Path.Combine(releases, "YB"));
            if (!bodyCanceled || finalYB) Console.WriteLine("detail cancel-body flushed=" + flushed + " canceled=" + bodyCanceled + " failure=" + bodyFailure + " final=" + finalYB);
            Check(bodyCanceled && !finalYB, "real.net.caller-cancel-during-body");
        }

        // 7. Required compatibility rejections, then the legal last known good still starts.
        var missingPackage = SignWithoutSidecar(work, "missing", packageA, contract, key);
        ServePackage(served, "n", missingPackage);
        var missing = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "MISS")),
            Offer(Uri, "A", "n", missingPackage) with { VersionName = "N" });
        if (missing.Failure != DeliveryFailure.CompatibilityRejected || missing.Detail != "sidecar-missing")
            Console.WriteLine("detail sidecar-missing " + missing.Failure + ":" + missing.Detail);
        Check(missing.Failure == DeliveryFailure.CompatibilityRejected && missing.Detail == "sidecar-missing",
            "real.required.sidecar-missing-rejected");
        var receiptBeforeBadOffer = File.ReadAllBytes(receipt);
        var missingDocument = Path.Combine(work, "missing-doc.bin");
        File.WriteAllBytes(missingDocument, missingPackage.Document);
        var missingStart = RunChild(work, "start", Path.Combine(releases, "MISS"), missingDocument,
            Path.Combine(releases, "MISS"), spkiPath, contractDll, contract, "B");
        Check(missingStart.Activated && missingStart.Value == 5 && missingStart.Source == "LastKnownGood" &&
              missingStart.SharedContract && missingStart.PidMatches && missingStart.FreshResult && missingStart.Version == "B" &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBeforeBadOffer),
            "real.required.sidecar-missing-then-lkg-start-and-receipt-unchanged");

        var wrongContract = new RuntimeContractIdentity(contract.Name, contract.Version, Guid.NewGuid());
        var wrongRoot = BuildAndSeal(work, "W", 7, wrongContract, contractDll, key, directorySuffix: "-wrong");
        ServePackage(served, "w", wrongRoot);
        var wrong = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "W")), Offer(Uri, "W", "w", wrongRoot));
        if (wrong.Failure != DeliveryFailure.CompatibilityRejected || wrong.Detail != "contract-mvid")
            Console.WriteLine("detail contract-mismatch " + wrong.Failure + ":" + wrong.Detail);
        Check(wrong.Failure == DeliveryFailure.CompatibilityRejected && wrong.Detail == "contract-mvid",
            "real.required.sidecar-contract-mismatch-rejected");
        var receiptBeforeWrongOffer = File.ReadAllBytes(receipt);
        var wrongDocument = Path.Combine(work, "wrong-doc.bin");
        File.WriteAllBytes(wrongDocument, wrongRoot.Document);
        var wrongStart = RunChild(work, "start", Path.Combine(releases, "W"), wrongDocument,
            Path.Combine(releases, "W"), spkiPath, contractDll, contract, "B");
        Check(wrongStart.Activated && wrongStart.Value == 5 && wrongStart.Source == "LastKnownGood" &&
              wrongStart.SharedContract && wrongStart.PidMatches && wrongStart.FreshResult && wrongStart.Version == "B" &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBeforeWrongOffer),
            "real.required.sidecar-contract-mismatch-then-lkg-start-and-receipt-unchanged");

        var unlimitedSidecar = StartWithOptions(work, deliverB.Offer!.ContentRoot, deliverB.Offer.SignedDocument.ToArray(),
            Path.Combine(releases, "B"), spkiPath, contractDll, contract, maxSidecar: 8);
        Check(!unlimitedSidecar.Activated && unlimitedSidecar.Detail.Contains("compat", StringComparison.Ordinal),
            "real.required.sidecar-byte-bound");

        // 7b. The DeliverAsync entry itself must enforce the declared host Contract and the sidecar byte bound.
        // These are expected RED until the producer routes DeliverAsync through the same guard as Start.
        var receiptBeforeDeliverGuard = File.ReadAllBytes(receipt);
        var wrongHostContract = new RuntimeContractIdentity(contract.Name, contract.Version, Guid.NewGuid());
        var wrongHostDeliver = await IpadDeliveryBridge.DeliverAsync(
            Options(Path.Combine(releases, "DH")) with { HostContract = wrongHostContract }, Offer(Uri, "A", "a", packageA));
        if (wrongHostDeliver.Succeeded) Console.WriteLine("detail deliver-wrong-host " + wrongHostDeliver.Failure + ":" + wrongHostDeliver.Detail);
        Check(!wrongHostDeliver.Succeeded && wrongHostDeliver.Offer is null &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBeforeDeliverGuard),
            "real.deliver.wrong-declared-host-contract-rejected");

        var tinySidecarDeliver = await IpadDeliveryBridge.DeliverAsync(
            Options(Path.Combine(releases, "DSB"), maxSidecar: 1), Offer(Uri, "A", "a", packageA));
        if (tinySidecarDeliver.Succeeded) Console.WriteLine("detail deliver-sidecar-bound " + tinySidecarDeliver.Failure + ":" + tinySidecarDeliver.Detail);
        Check(!tinySidecarDeliver.Succeeded && tinySidecarDeliver.Offer is null &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBeforeDeliverGuard),
            "real.deliver.max-sidecar-bytes-rejected");

        // 8. Server stopped: the receipt alone restores B offline, and an activation throw keeps it.
        server.Stop();
        var offline = RunChild(work, "restore", "", "", Path.Combine(releases, "unused"), spkiPath, contractDll, contract, "B");
        Check(offline.Activated && offline.Value == 5 && offline.Source == "LastKnownGood" && offline.SharedContract &&
              offline.PidMatches && offline.FreshResult && offline.Version == "B",
            "real.offline.lkg-restores-b-business-5");

        // 8. Activation throw keeps the receipt; a new process restores the last known good.
        var receiptBeforeThrow = File.ReadAllBytes(receipt);
        var thrown = RunChild(work, "throw", deliverB.Offer!.ContentRoot, documentB, finalB, spkiPath, contractDll, contract, "B");
        Check(!thrown.Activated && thrown.PidMatches && thrown.FreshResult &&
              File.ReadAllBytes(receipt).AsSpan().SequenceEqual(receiptBeforeThrow),
            "real.activation.throw-keeps-receipt");
        var afterThrow = RunChild(work, "restore", "", "", Path.Combine(releases, "unused"), spkiPath, contractDll, contract, "B");
        Check(afterThrow.Activated && afterThrow.Value == 5 && afterThrow.Source == "LastKnownGood" &&
              afterThrow.SharedContract && afterThrow.PidMatches && afterThrow.FreshResult && afterThrow.Version == "B",
            "real.activation.new-process-restores-receipt");

        // 9. Sealer refuses an escaping consumed path before touching the filesystem.
        var escapeRejected = false;
        try
        {
            PackageSealer.Seal(packageA.Root, new TrustedReleaseIdentity("Z", Target.Runtime, Target.Architecture, TypeName, MethodName, Entry),
                new[] { "../evil.dll" }, contract, Target, key);
        }
        catch (ArgumentException) { escapeRejected = true; }
        Check(escapeRejected && !File.Exists(Path.Combine(work, "evil.dll")), "real.sealer.rejects-escaping-path");

        File.WriteAllText(Path.Combine(work, "summary.json"), JsonSerializer.Serialize(new
        {
            run = _run,
            pass = _pass,
            fail = _fail,
            serverRequests = server.Requests,
            serverResponsesClosedByServer = server.Disposed,
            note = "server counters describe the test server only; client response/stream disposal is the using-declaration fact in BoundedHttpFetch, not measured here",
        }, new JsonSerializerOptions { WriteIndented = true }));
    }

    private static void ServePackage(Dictionary<string, byte[]> served, string slot, Sealed package)
    {
        served["/" + slot + "/envelope"] = package.Document;
        foreach (var file in package.Files)
            served["/" + slot + "/" + file] = File.ReadAllBytes(Path.Combine(package.Root, file));
    }

    private static DeliveryOffer Offer(Func<string, Uri> uri, string version, string slot, Sealed package) => new()
    {
        VersionName = version,
        DocumentUri = uri("/" + slot + "/envelope"),
        Content = package.Files.Select(file => new DeliveryContentSource(file, uri("/" + slot + "/" + file))).ToArray(),
        EntryAssemblyName = Entry,
        EntryTypeName = TypeName,
        EntryMethodName = MethodName,
    };

    private sealed record Sealed(string Root, byte[] Document, string[] Files);

    private static Sealed BuildAndSeal(string work, string version, int delta, RuntimeContractIdentity contract,
        string contractDll, ECDsa key, string directorySuffix = "")
    {
        var module = Path.Combine(work, "module-" + version + directorySuffix);
        Directory.CreateDirectory(module);
        File.WriteAllText(Path.Combine(module, "Module.cs"),
            "using OrbitBridge; namespace OrbitBridge; public sealed class Rules : IRules { public int Step(IHost host) => host.Move(" + delta + "); }\n");
        File.WriteAllText(Path.Combine(module, "mod.csproj"),
            "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net11.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings>" +
            "<Nullable>enable</Nullable><AssemblyName>Update</AssemblyName><EnableDefaultCompileItems>false</EnableDefaultCompileItems>" +
            "<OutputPath>out/</OutputPath><AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath></PropertyGroup>" +
            "<ItemGroup><Compile Include=\"Module.cs\" /><Reference Include=\"OrbitBridge.Contracts\"><HintPath>" + contractDll +
            "</HintPath><Private>false</Private></Reference></ItemGroup></Project>");
        Build(module);
        var built = Path.Combine(module, "out", Entry);
        if (!File.Exists(built)) throw new InvalidOperationException("fixture build produced no " + Entry);

        var root = Path.Combine(work, "pkg-" + version + directorySuffix);
        Directory.CreateDirectory(root);
        File.Copy(built, Path.Combine(root, Entry), true);
        var sealedPackage = PackageSealer.Seal(root,
            new TrustedReleaseIdentity(version, Target.Runtime, Target.Architecture, TypeName, MethodName, Entry),
            new[] { Entry }, contract, Target, key);
        File.AppendAllText(Path.Combine(work, "fixtures.log"),
            version + " module=" + Sha(built) + " envelope=" + Sha(sealedPackage.DocumentPath) + "\n");
        return new Sealed(root, sealedPackage.Document, sealedPackage.Files.ToArray());
    }

    private static void Build(string dir)
    {
        var info = new ProcessStartInfo("dotnet", "build mod.csproj -c Release --nologo")
        {
            WorkingDirectory = dir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        using var process = Process.Start(info) ?? throw new InvalidOperationException("dotnet build");
        var stdout = process.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        if (process.ExitCode != 0)
            throw new InvalidOperationException("fixture build failed: " + stdout + stderr);
    }

    private static Sealed SignWithoutSidecar(string work, string name, Sealed package, RuntimeContractIdentity contract, ECDsa key)
    {
        var dir = Path.Combine(work, "pkg-" + name + "-nosidecar");
        Directory.CreateDirectory(dir);
        File.Copy(Path.Combine(package.Root, Entry), Path.Combine(dir, Entry), true);
        var signed = TrustedRelease.Sign(dir,
            new TrustedReleaseIdentity("N", Target.Runtime, Target.Architecture, TypeName, MethodName, Entry),
            new[] { Entry }, key);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("sign-nosidecar:" + signed.Failure);
        File.WriteAllBytes(Path.Combine(dir, "envelope.bin"), signed.Document);
        return new Sealed(dir, signed.Document, new[] { Entry });
    }

    private sealed record ChildResult(bool Activated, int Value, string Source, bool SharedContract, string Detail,
        int Exit, string Version, int Pid, string RunId, bool FreshResult, bool PidMatches, string LaunchRecord);

    private static ChildResult RunChild(string work, string mode, string offerRoot, string documentPath, string finalDir, string spkiPath,
        string contractDll, RuntimeContractIdentity contract, string expectedVersion)
    {
        static string Abs(string path) => string.IsNullOrEmpty(path) ? "" : Path.GetFullPath(path);

        var runId = Guid.NewGuid().ToString("N");
        var request = Path.Combine(work, "child-" + mode + "-" + runId + ".json");
        var result = Path.ChangeExtension(request, ".result.json");
        var launchRecord = Path.ChangeExtension(request, ".launch.json");
        if (File.Exists(result)) File.Delete(result);
        File.WriteAllText(request, JsonSerializer.Serialize(new
        {
            mode,
            runId,
            offerRoot = Abs(offerRoot),
            document = Abs(documentPath),
            finalDir = Abs(finalDir),
            spkiPath = Abs(spkiPath),
            contractDll = Abs(contractDll),
            contractName = contract.Name,
            contractVersion = contract.Version,
            contractMvid = contract.CanonicalMvid,
            releases = Abs(Path.Combine(work, "releases")),
            receipt = Abs(Path.Combine(work, "state", "receipt.bin")),
            result = Abs(result),
        }));

        var host = Environment.ProcessPath ?? throw new InvalidOperationException("host");
        var hostStem = Path.GetFileNameWithoutExtension(host);
        var argv = new List<string> { host };
        if (string.Equals(hostStem, "dotnet", StringComparison.OrdinalIgnoreCase))
        {
            // "dotnet <dll>" form: the host needs the absolute self-test assembly before the mode.
            argv.Add(typeof(RealFlow).Assembly.Location);
        }

        argv.Add("real-child");
        argv.Add(mode);
        argv.Add(request);

        var info = new ProcessStartInfo(host)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = AppContext.BaseDirectory,
        };
        for (var i = 1; i < argv.Count; i++)
            info.ArgumentList.Add(argv[i]);

        var startedAt = DateTime.UtcNow;
        using var child = Process.Start(info) ?? throw new InvalidOperationException("child");
        var pid = child.Id;
        var stdout = child.StandardOutput.ReadToEnd();
        var stderr = child.StandardError.ReadToEnd();
        child.WaitForExit();
        var endedAt = DateTime.UtcNow;
        File.WriteAllText(launchRecord, JsonSerializer.Serialize(new
        {
            mode,
            runId,
            pid,
            argv,
            cwd = AppContext.BaseDirectory,
            startedUtc = startedAt.ToString("o"),
            endedUtc = endedAt.ToString("o"),
            exit = child.ExitCode,
            expectedVersion,
            stdout = stdout.Trim(),
            stderr = stderr.Trim(),
        }, new JsonSerializerOptions { WriteIndented = true }));

        if (!File.Exists(result))
            return new ChildResult(false, 0, "", false, "no-result", child.ExitCode, "", pid, runId, false, false, launchRecord);
        var fresh = File.GetLastWriteTimeUtc(result) >= startedAt.AddSeconds(-1);
        using var json = JsonDocument.Parse(File.ReadAllText(result));
        var root = json.RootElement;
        var childPid = root.GetProperty("pid").GetInt32();
        var childRun = root.GetProperty("runId").GetString() ?? "";
        var version = root.GetProperty("version").GetString() ?? "";
        var pidMatches = childPid == pid && childRun == runId;
        return new ChildResult(
            root.GetProperty("activated").GetBoolean(),
            root.GetProperty("value").GetInt32(),
            root.GetProperty("source").GetString() ?? "",
            root.GetProperty("shared").GetBoolean(),
            pidMatches ? root.GetProperty("detail").GetString() ?? "" : "pid-mismatch",
            child.ExitCode, version, pid, runId, fresh, pidMatches, launchRecord);
    }

    private static ChildResult StartWithOptions(string work, string offerRoot, byte[] document, string finalDir,
        string spkiPath, string contractDll, RuntimeContractIdentity contract, int maxSidecar)
    {
        // Runs in this process on purpose: Start's sidecar bound must reject before any activation.
        var options = new DeliveryOptions
        {
            HostSubjectPublicKeyInfo = File.ReadAllBytes(spkiPath),
            Target = Target,
            HostContract = contract,
            HostDeploymentContractPath = contractDll,
            AllowedReleasesRoot = Path.Combine(work, "releases"),
            RecoveryReceiptPath = Path.Combine(work, "state", "receipt.bin"),
            FinalReleaseDirectory = finalDir,
            MaxCompatSidecarBytes = maxSidecar,
        };
        var started = IpadDeliveryBridge.Start(options, new TrustedReleaseOffer(offerRoot, document),
            (candidate, source, failure) => new TrustedUpdateActivation(TrustedUpdateFailure.None, 99));
        return new ChildResult(started.Activated, started.Value, started.Source.ToString(), false,
            started.Candidate.Plan + "/" + started.Candidate.Detail + "/" + started.Recovery.Plan + "/" + started.Recovery.Detail,
            0, started.SelectedVersion ?? "", 0, "", true, true, "");
    }

    // ---------------- child process ----------------

    public static int Child(string mode, string requestPath)
    {
        using var json = JsonDocument.Parse(File.ReadAllText(requestPath));
        var root = json.RootElement;
        var contract = new RuntimeContractIdentity(
            root.GetProperty("contractName").GetString()!,
            root.GetProperty("contractVersion").GetString()!,
            Guid.Parse(root.GetProperty("contractMvid").GetString()!));
        var options = new DeliveryOptions
        {
            HostSubjectPublicKeyInfo = File.ReadAllBytes(root.GetProperty("spkiPath").GetString()!),
            Target = Target,
            HostContract = contract,
            HostDeploymentContractPath = root.GetProperty("contractDll").GetString()!,
            AllowedReleasesRoot = root.GetProperty("releases").GetString()!,
            RecoveryReceiptPath = root.GetProperty("receipt").GetString()!,
            FinalReleaseDirectory = root.GetProperty("finalDir").GetString()!,
        };
        TrustedReleaseOffer? offer = null;
        if (mode != "restore")
        {
            // The exact document handed over by DeliverAsync; the published directory does not
            // contain the envelope, and nothing is re-downloaded.
            var offerRoot = root.GetProperty("offerRoot").GetString()!;
            offer = new TrustedReleaseOffer(offerRoot, File.ReadAllBytes(root.GetProperty("document").GetString()!));
        }

        var resultPath = root.GetProperty("result").GetString()!;
        var shared = false;
        var value = 0;
        TrustedUpdateActivation Activate(TrustedUpdateCandidate candidate, TrustedUpdateStartSource source, TrustedUpdateFailure failure)
        {
            if (mode == "throw")
                throw new InvalidOperationException("activation-boom");
            var context = new AssemblyLoadContext("author-" + Guid.NewGuid().ToString("N"), isCollectible: true);
            context.Resolving += (ctx, name) => name.Name == ContractName ? typeof(IRules).Assembly : null;
            var assembly = context.LoadFromAssemblyPath(candidate.AssemblyPath);
            var type = assembly.GetType(candidate.EntryTypeName, throwOnError: true)!;
            var instance = Activator.CreateInstance(type)!;
            var method = type.GetMethod(candidate.EntryMethodName) ?? throw new InvalidOperationException("entry-method");
            shared = method.GetParameters()[0].ParameterType.Assembly == typeof(IRules).Assembly;
            var host = new BridgeHost();
            value = (int)method.Invoke(instance, new object[] { host })!;
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, value);
        }

        var started = IpadDeliveryBridge.Start(options, offer, Activate);
        File.WriteAllText(resultPath, JsonSerializer.Serialize(new
        {
            pid = Environment.ProcessId,
            runId = root.GetProperty("runId").GetString()!,
            version = started.SelectedVersion ?? "",
            activated = started.Activated,
            value,
            source = started.Source.ToString(),
            shared,
            detail = started.Candidate.Plan + "/" + started.Candidate.Detail,
        }));
        Console.WriteLine("CHILD " + mode + " activated=" + started.Activated + " value=" + value + " shared=" + shared +
                          " source=" + started.Source);
        return 0;
    }

    private sealed class BridgeHost : IHost
    {
        public int Position { get; private set; }

        public int Move(int delta)
        {
            Position += delta;
            return Position;
        }
    }

    private static (string Name, string Version, string Mvid) BridgeIdentity(string path)
    {
        using var stream = File.OpenRead(path);
        using var pe = new System.Reflection.PortableExecutable.PEReader(stream);
        var metadata = pe.GetMetadataReader();
        var definition = metadata.GetAssemblyDefinition();
        var module = metadata.GetModuleDefinition();
        return (metadata.GetString(definition.Name), definition.Version.ToString(),
            metadata.GetGuid(module.Mvid).ToString("D"));
    }

    private static string Sha(string path) =>
        Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

    // ---------------- loopback server with real headers/bodies ----------------

    private sealed class TestServer : IDisposable
    {
        private readonly HttpListener _listener = new();
        private readonly Dictionary<string, byte[]> _content;
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _loop;
        private int _requests;
        private int _disposed;

        public int Port { get; }
        public ManualResetEventSlim HeadersFlushed { get; } = new(false);
        public int Requests => Volatile.Read(ref _requests);
        public int Disposed => Volatile.Read(ref _disposed);

        private TestServer(Dictionary<string, byte[]> content, int port)
        {
            _content = content;
            Port = port;
            _listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
            _listener.Start();
            _loop = Task.Run(Loop);
        }

        public static TestServer Start(Dictionary<string, byte[]> content)
        {
            for (var attempt = 0; attempt < 20; attempt++)
            {
                var listener = new HttpListener();
                var probe = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
                probe.Start();
                var port = ((IPEndPoint)probe.LocalEndpoint).Port;
                probe.Stop();
                try { return new TestServer(content, port); }
                catch (HttpListenerException) { Thread.Sleep(50); }
            }

            throw new InvalidOperationException("no loopback port");
        }

        public void Stop()
        {
            _stop.Cancel();
            try { _listener.Stop(); } catch { }
            try { _loop.Wait(TimeSpan.FromSeconds(5)); } catch { }
        }

        public void Dispose()
        {
            Stop();
            _listener.Close();
            _stop.Dispose();
        }

        private async Task Loop()
        {
            while (!_stop.IsCancellationRequested)
            {
                HttpListenerContext context;
                try { context = await _listener.GetContextAsync().ConfigureAwait(false); }
                catch (Exception) { return; }
                Interlocked.Increment(ref _requests);
                _ = Task.Run(() => Serve(context));
            }
        }

        private void Serve(HttpListenerContext context)
        {
            var path = context.Request.Url?.AbsolutePath ?? "/";
            var response = context.Response;
            try
            {
                if (path.StartsWith("/redirect/", StringComparison.Ordinal))
                {
                    response.StatusCode = 302;
                    response.RedirectLocation = "/a/envelope";
                    return;
                }

                var stall = path.StartsWith("/stall/", StringComparison.Ordinal);
                var abort = path.StartsWith("/abort/", StringComparison.Ordinal);
                var key = stall ? path["/stall".Length..] : abort ? path["/abort".Length..] : path;
                if (!_content.TryGetValue(key, out var bytes))
                {
                    response.StatusCode = 404;
                    return;
                }

                response.StatusCode = 200;
                response.SendChunked = true;
                if (stall)
                {
                    response.OutputStream.Write(bytes, 0, Math.Min(16, bytes.Length));
                    response.OutputStream.Flush();
                    HeadersFlushed.Set();
                    Thread.Sleep(TimeSpan.FromSeconds(30));
                    return;
                }

                if (abort)
                {
                    response.ContentLength64 = bytes.Length;
                    response.OutputStream.Write(bytes, 0, bytes.Length / 2);
                    response.OutputStream.Flush();
                    response.Abort();
                    return;
                }

                response.OutputStream.Write(bytes, 0, bytes.Length);
                response.OutputStream.Flush();
            }
            catch (Exception)
            {
            }
            finally
            {
                try { response.OutputStream.Close(); } catch { }
                try { response.Close(); } catch { }
                Interlocked.Increment(ref _disposed);
            }
        }
    }
}
