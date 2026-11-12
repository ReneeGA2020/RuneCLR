using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection.Metadata;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using RuneCLR.IpadDelivery;
using RuneCLR.TrustedUpdate;

internal static class Program
{
    private static int _failures;

    private static void Check(bool ok, string name)
    {
        Console.WriteLine((ok ? "PASS " : "FAIL ") + name);
        if (!ok) _failures++;
    }

    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "child") return Child(args);
        if (args.Length > 1 && args[0] == "real-flow") return RealFlow.Run(args[1]);
        if (args.Length > 2 && args[0] == "real-child") return RealFlow.Child(args[1], args[2]);
        try { Parent().GetAwaiter().GetResult(); }
        catch (Exception error)
        {
            Console.WriteLine("FAIL selftest-exception " + error.GetType().Name + ": " + error.Message);
            _failures++;
        }
        Console.WriteLine(_failures == 0 ? "SELFTEST PASS" : "SELFTEST FAIL " + _failures);
        return _failures == 0 ? 0 : 1;
    }

    // ---------------- child: one process start ----------------
    private static int Child(string[] args)
    {
        var mode = args[1];
        var release = args[2];
        var receipt = args[3];
        var contractPath = args[4];
        var spkiPath = args[5];
        var contractName = args[6];
        var documentPath = args[7];
        var spki = File.ReadAllBytes(spkiPath);
        var identity = Identity(contractPath);
        var contract = new RuntimeContractIdentity(contractName, identity.Version, Guid.Parse(identity.Mvid));
        var target = new TrustedUpdateTarget("ios-arm64", "arm64");
        var options = new DeliveryOptions
        {
            HostSubjectPublicKeyInfo = spki,
            Target = target,
            HostContract = contract,
            HostDeploymentContractPath = contractPath,
            AllowedReleasesRoot = Path.Combine(release, ".."),
            RecoveryReceiptPath = receipt,
            FinalReleaseDirectory = release,
            DownloadDeadline = TimeSpan.FromSeconds(10),
        };
        var document = File.ReadAllBytes(documentPath);
        var offer = new TrustedReleaseOffer(release, document);
        try
        {
            if (mode == "throw")
            {
                // The core converts an activation throw into a failed start and keeps the old receipt.
                var thrown = IpadDeliveryBridge.Start(options, offer,
                    (candidate, source, failure) => throw new InvalidOperationException("activation-boom"));
                Console.WriteLine("CHILD throw activated=" + thrown.Activated);
                return thrown.Activated ? 3 : 1;
            }
            var started = IpadDeliveryBridge.Start(options, mode == "restore" ? null : offer,
                (candidate, source, failure) => new TrustedUpdateActivation(TrustedUpdateFailure.None, 42));
            Console.WriteLine("CHILD " + mode + " activated=" + started.Activated + " source=" + started.Source +
                " candidate=" + started.Candidate.Verification + "/" + started.Candidate.Plan +
                " recovery=" + started.Recovery.Verification + "/" + started.Recovery.Plan);
            return started.Activated ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.WriteLine("CHILD " + mode + " exception=" + error.GetType().Name);
            return 2;
        }
    }

    // ---------------- parent: delivery + process-start orchestration ----------------
    private static async Task Parent()
    {
        var work = Path.Combine(Path.GetTempPath(), "ipad-delivery-selftest-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        var port = FreePort();
        using var listener = new HttpListener();
        listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
        listener.Start();
        var served = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        var redirects = new HashSet<string>(StringComparer.Ordinal);
        var cts = new CancellationTokenSource();
        var server = Task.Run(() => Serve(listener, served, redirects, cts.Token));
        try { await Scenarios(work, port, served, redirects).ConfigureAwait(false); }
        finally
        {
            cts.Cancel();
            try { listener.Stop(); } catch { }
            try { await server.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); } catch { }
        }
    }

    private static async Task Scenarios(string work, int port, Dictionary<string, byte[]> served, HashSet<string> redirects)
    {
        served["/doc"] = Encoding.UTF8.GetBytes("hello");
        var bytes = await BoundedHttpFetch.DownloadAsync(new Uri("http://127.0.0.1:" + port + "/doc"), 64, TimeSpan.FromSeconds(5), CancellationToken.None);
        Check(bytes.Length == 5, "fetch-normal");

        redirects.Add("/r");
        var redirected = false;
        try { await BoundedHttpFetch.DownloadAsync(new Uri("http://127.0.0.1:" + port + "/r"), 64, TimeSpan.FromSeconds(5), CancellationToken.None); }
        catch (IOException) { redirected = true; }
        Check(redirected, "fetch-redirect-refused");

        var capped = false;
        try { await BoundedHttpFetch.DownloadAsync(new Uri("http://127.0.0.1:" + port + "/doc"), 2, TimeSpan.FromSeconds(5), CancellationToken.None); }
        catch (IOException) { capped = true; }
        Check(capped, "fetch-body-cap");

        served["/slow"] = Encoding.UTF8.GetBytes("slow");
        var timedOut = false;
        try { await BoundedHttpFetch.DownloadAsync(new Uri("http://127.0.0.1:" + port + "/slow"), 64, TimeSpan.FromMilliseconds(50), CancellationToken.None); }
        catch (OperationCanceledException) { timedOut = true; }
        Check(timedOut, "fetch-deadline");

        var design = Path.Combine(work, "design");
        Directory.CreateDirectory(design);
        var contractPath = typeof(PackageSealer).Assembly.Location;
        var id = Identity(contractPath);
        var contract = new RuntimeContractIdentity(id.Name, id.Version, Guid.Parse(id.Mvid));
        var target = new TrustedUpdateTarget("ios-arm64", "arm64");
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var spki = key.ExportSubjectPublicKeyInfo();
        File.WriteAllBytes(Path.Combine(work, "spki.bin"), spki);

        File.WriteAllBytes(Path.Combine(design, "Owner.dylib"), RandomNumberGenerator.GetBytes(128));
        File.WriteAllBytes(Path.Combine(design, "Update.dll"), RandomNumberGenerator.GetBytes(128));
        var sealedPackage = PackageSealer.Seal(design, new TrustedReleaseIdentity("B", target.Runtime,
            target.Architecture, "Update.Entry", "Run", "Update.dll"), new[] { "Owner.dylib", "Update.dll" },
            contract, target, key);
        Check(sealedPackage.Document.Length > 0, "seal-document");
        Check(PackageSealer.Verify(design, spki, sealedPackage.DocumentPath).Succeeded, "seal-verify");

        var files = new List<DeliveryContentSource>();
        foreach (var relative in sealedPackage.Files)
        {
            served["/" + relative] = File.ReadAllBytes(Path.Combine(design, relative));
            files.Add(new DeliveryContentSource(relative, new Uri("http://127.0.0.1:" + port + "/" + relative)));
        }
        served["/envelope"] = sealedPackage.Document;

        var releases = Path.Combine(work, "releases");
        Directory.CreateDirectory(releases);
        var receipt = Path.Combine(work, "receipt.json");
        var finalDir = Path.Combine(releases, "B");
        DeliveryOptions Options(string final) => new()
        {
            HostSubjectPublicKeyInfo = spki,
            Target = target,
            HostContract = contract,
            HostDeploymentContractPath = contractPath,
            AllowedReleasesRoot = releases,
            RecoveryReceiptPath = receipt,
            FinalReleaseDirectory = final,
            DownloadDeadline = TimeSpan.FromSeconds(10),
        };

        // P1-1 fixture: a final directory outside the allowed root must be rejected before any write.
        var outside = Path.Combine(work, "outside-root", "B");
        var outsideThrew = false;
        try
        {
            await IpadDeliveryBridge.DeliverAsync(new DeliveryOptions
            {
                HostSubjectPublicKeyInfo = spki,
                Target = target,
                HostContract = contract,
                HostDeploymentContractPath = contractPath,
                AllowedReleasesRoot = releases,
                RecoveryReceiptPath = receipt,
                FinalReleaseDirectory = outside,
                DownloadDeadline = TimeSpan.FromSeconds(10),
            }, new DeliveryOffer
            {
                VersionName = "B", DocumentUri = new Uri("http://127.0.0.1:" + port + "/envelope"),
                Content = files,
                EntryAssemblyName = "Update.dll", EntryTypeName = "Update.Entry", EntryMethodName = "Run",
            });
        }
        catch (ArgumentException) { outsideThrew = true; }
        Check(outsideThrew && !Directory.Exists(Path.Combine(work, "outside-root")), "outside-root-rejected-no-write");

        // receipt inside the releases root must also be rejected.
        var receiptInsideThrew = false;
        try
        {
            await IpadDeliveryBridge.DeliverAsync(new DeliveryOptions
            {
                HostSubjectPublicKeyInfo = spki,
                Target = target,
                HostContract = contract,
                HostDeploymentContractPath = contractPath,
                AllowedReleasesRoot = releases,
                RecoveryReceiptPath = Path.Combine(releases, "receipt.json"),
                FinalReleaseDirectory = finalDir,
                DownloadDeadline = TimeSpan.FromSeconds(10),
            }, new DeliveryOffer
            {
                VersionName = "B", DocumentUri = new Uri("http://127.0.0.1:" + port + "/envelope"),
                Content = files,
                EntryAssemblyName = "Update.dll", EntryTypeName = "Update.Entry", EntryMethodName = "Run",
            });
        }
        catch (ArgumentException) { receiptInsideThrew = true; }
        Check(receiptInsideThrew, "receipt-inside-root-rejected");

        // partial stage: one served body is short -> staging fails, no final directory.
        var truncated = new List<DeliveryContentSource>();
        foreach (var f in files)
        {
            if (f.RelativePath == "Update.dll")
            {
                served["/short"] = new byte[8];
                truncated.Add(new DeliveryContentSource(f.RelativePath, new Uri("http://127.0.0.1:" + port + "/short")));
            }
            else truncated.Add(f);
        }
        var partial = await IpadDeliveryBridge.DeliverAsync(Options(finalDir), new DeliveryOffer
        {
            VersionName = "B", DocumentUri = new Uri("http://127.0.0.1:" + port + "/envelope"), Content = truncated,
            EntryAssemblyName = "Update.dll", EntryTypeName = "Update.Entry", EntryMethodName = "Run",
        });
        Check(!partial.Succeeded && !Directory.Exists(finalDir), "partial-stage-rejected");

        // unlisted sidecar (not in the signed set) is rejected.
        var unlisted = await IpadDeliveryBridge.DeliverAsync(Options(Path.Combine(releases, "C")), new DeliveryOffer
        {
            VersionName = "B", DocumentUri = new Uri("http://127.0.0.1:" + port + "/envelope"),
            Content = files.Where(f => f.RelativePath != PackageSealer.SidecarName).ToArray(),
            EntryAssemblyName = "Update.dll", EntryTypeName = "Update.Entry", EntryMethodName = "Run",
        });
        Check(!unlisted.Succeeded, "unlisted-sidecar-rejected");

        // normal offer
        var delivered = await IpadDeliveryBridge.DeliverAsync(Options(finalDir), new DeliveryOffer
        {
            VersionName = "B", DocumentUri = new Uri("http://127.0.0.1:" + port + "/envelope"), Content = files,
            EntryAssemblyName = "Update.dll", EntryTypeName = "Update.Entry", EntryMethodName = "Run",
        });
        Check(delivered.Succeeded && Directory.Exists(finalDir), "offer-delivered");

        // process starts must each run in a fresh process (selection is process-lifetime)
        var child = RunChild("start", finalDir, receipt, contractPath, Path.Combine(work, "spki.bin"), id.Name, sealedPackage.DocumentPath);
        Check(child == 0 && File.Exists(receipt), "start-offer-success");
        var offline = RunChild("restore", finalDir, receipt, contractPath, Path.Combine(work, "spki.bin"), id.Name, sealedPackage.DocumentPath);
        Check(offline == 0, "offline-restore");

        var before = File.ReadAllBytes(receipt);
        var thrown = RunChild("throw", finalDir, receipt, contractPath, Path.Combine(work, "spki.bin"), id.Name, sealedPackage.DocumentPath);
        var after = File.ReadAllBytes(receipt);
        Check((thrown == 1 || thrown == 2) && before.SequenceEqual(after), "activation-throw-keeps-receipt");

        // required gate: a host contract name that does not match the signed sidecar rejects the offer
        var wrong = RunChild("start", finalDir, Path.Combine(work, "receipt2.json"), contractPath,
            Path.Combine(work, "spki.bin"), "Wrong.Contract", sealedPackage.DocumentPath);
        Check(wrong == 1 && !File.Exists(Path.Combine(work, "receipt2.json")), "required-contract-mismatch");
    }

    private static int RunChild(string mode, string release, string receipt, string contractPath, string spkiPath, string contractName, string documentPath)
    {
        // When the test runs as "dotnet <dll>", MainModule is dotnet itself; spawn that host explicitly.
        var host = Environment.ProcessPath ?? "dotnet";
        var assembly = typeof(Program).Assembly.Location;
        var info = new ProcessStartInfo(host)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        if (!string.Equals(Path.GetFileNameWithoutExtension(host), "IpadDelivery.SelfTest", StringComparison.Ordinal))
            info.ArgumentList.Add(assembly);
        info.ArgumentList.Add("child");
        info.ArgumentList.Add(mode);
        info.ArgumentList.Add(release);
        info.ArgumentList.Add(receipt);
        info.ArgumentList.Add(contractPath);
        info.ArgumentList.Add(spkiPath);
        info.ArgumentList.Add(contractName);
        info.ArgumentList.Add(documentPath);
        using var process = Process.Start(info)!;
        var output = process.StandardOutput.ReadToEnd();
        var error = process.StandardError.ReadToEnd();
        process.WaitForExit();
        foreach (var line in output.Split('\n')) if (line.Trim().Length > 0) Console.WriteLine("  " + line.Trim());
        if (error.Trim().Length > 0) Console.WriteLine("  stderr " + error.Trim().Split('\n')[0]);
        return process.ExitCode;
    }

    private static (string Name, string Version, string Mvid) Identity(string path)
    {
        using var stream = File.OpenRead(path);
        using var pe = new System.Reflection.PortableExecutable.PEReader(stream);
        var md = pe.GetMetadataReader();
        var def = md.GetAssemblyDefinition();
        var module = md.GetModuleDefinition();
        return (md.GetString(def.Name), def.Version.ToString(), md.GetGuid(module.Mvid).ToString("D"));
    }

    private static int FreePort()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }

    private static void Serve(HttpListener listener, Dictionary<string, byte[]> served, HashSet<string> redirects, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            HttpListenerContext context;
            try { context = listener.GetContext(); } catch { return; }
            try
            {
                var path = context.Request.Url!.AbsolutePath;
                if (redirects.Contains(path))
                {
                    context.Response.StatusCode = 302;
                    context.Response.RedirectLocation = "/doc";
                    context.Response.Close();
                    continue;
                }
                if (path == "/slow") { Thread.Sleep(500); context.Response.StatusCode = 200; context.Response.Close(); continue; }
                if (served.TryGetValue(path, out var body))
                {
                    context.Response.StatusCode = 200;
                    context.Response.ContentLength64 = body.Length;
                    try { context.Response.OutputStream.Write(body, 0, body.Length); } catch { }
                    context.Response.Close();
                    continue;
                }
                context.Response.StatusCode = 404;
                context.Response.Close();
            }
            catch { try { context.Response.Abort(); } catch { } }
        }
    }
}

