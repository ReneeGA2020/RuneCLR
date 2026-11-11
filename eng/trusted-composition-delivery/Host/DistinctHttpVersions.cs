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
        byte[] docC;
        byte[] docD;
        byte[] docE;
        byte[] docF;
        byte[] docG;
        byte[] docH;
        byte[] docI;
        byte[] docJ;
        foreach (var name in new[] { "c", "d", "e", "f", "g", "h", "i", "j" })
        {
            Directory.CreateDirectory(Path.Combine(late, name));
            File.Copy(dllA, Path.Combine(late, name, Entry), true);
        }
        using (var key = ECDsa.Create(ECCurve.NamedCurves.nistP256))
        {
            File.WriteAllBytes(spkiPath, key.ExportSubjectPublicKeyInfo());
            docA = Sign(key, Path.Combine(late, "a", "out"), "A");
            docB = Sign(key, Path.Combine(late, "b", "out"), "B");
            docC = Sign(key, Path.Combine(late, "c"), "C", runtime: "net10.0");
            docD = Sign(key, Path.Combine(late, "d"), "D", badContract: true);
            docE = Sign(key, Path.Combine(late, "e"), "E", architecture: "x86");
            docF = Sign(key, Path.Combine(late, "f"), "F", includeSidecar: false);
            docG = Sign(key, Path.Combine(late, "g"), "G", includeSidecar: false);
            docH = Sign(key, Path.Combine(late, "h"), "H");
            var contractPath = Path.Combine(AppContext.BaseDirectory, "OrbitGame.Contracts.dll");
            if (!ContractCompatibility.TryReadAssembly(contractPath, out var contractIdentity, out var contractDetail))
                return Fail(output, "contract-" + contractDetail);
            var contractMvid = Guid.Parse(contractIdentity.Mvid);
            var canonicalN = contractMvid.ToString("N");
            var heapOrder = Convert.ToHexString(contractMvid.ToByteArray()).ToLowerInvariant();
            docI = Sign(key, Path.Combine(late, "i"), "I", mvidOverride: canonicalN);
            docJ = Sign(key, Path.Combine(late, "j"), "J", mvidOverride: heapOrder);
        }
        if (docA.Length == 0 || docB.Length == 0 || docC.Length == 0 || docD.Length == 0
            || docE.Length == 0 || docF.Length == 0 || docG.Length == 0 || docH.Length == 0
            || docI.Length == 0 || docJ.Length == 0)
            return Fail(output, "sign");
        var serverRoot = Path.Combine(output, "server-root");
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-a"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-b"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "bad-body"));
        File.WriteAllBytes(Path.Combine(serverRoot, "a.bin"), docA);
        File.WriteAllBytes(Path.Combine(serverRoot, "b.bin"), docB);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-a", Entry), true);
        File.Copy(dllB, Path.Combine(serverRoot, "orbit-b", Entry), true);
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-c"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "orbit-d"));
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-c", Entry), true);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-d", Entry), true);
        Directory.CreateDirectory(Path.Combine(serverRoot, "eof"));
        Directory.CreateDirectory(Path.Combine(serverRoot, "oversize"));
        File.WriteAllBytes(Path.Combine(serverRoot, "eof", "a.bin"), docA);
        File.WriteAllBytes(Path.Combine(serverRoot, "oversize", "a.bin"), new byte[TrustedRelease.MaxDocumentBytes + 1024]);
        File.WriteAllBytes(Path.Combine(serverRoot, "c.bin"), docC);
        File.WriteAllBytes(Path.Combine(serverRoot, "d.bin"), docD);
        File.WriteAllBytes(Path.Combine(serverRoot, "e.bin"), docE);
        File.WriteAllBytes(Path.Combine(serverRoot, "f.bin"), docF);
        File.WriteAllBytes(Path.Combine(serverRoot, "g.bin"), docG);
        File.WriteAllBytes(Path.Combine(serverRoot, "h.bin"), docH);
        File.WriteAllBytes(Path.Combine(serverRoot, "i.bin"), docI);
        File.WriteAllBytes(Path.Combine(serverRoot, "j.bin"), docJ);
        foreach (var name in new[] { "orbit-e", "orbit-f", "orbit-g", "orbit-h", "orbit-i", "orbit-j" })
            Directory.CreateDirectory(Path.Combine(serverRoot, name));
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-e", Entry), true);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-f", Entry), true);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-g", Entry), true);
        File.Copy(dllA, Path.Combine(serverRoot, "orbit-h", Entry), true);
        File.Copy(Path.Combine(late, "e", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-e", ContractCompatibility.SidecarName), true);
        File.Copy(Path.Combine(late, "h", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-h", ContractCompatibility.SidecarName), true);
        foreach (var name in new[] { "i", "j" })
        {
            File.Copy(dllA, Path.Combine(serverRoot, "orbit-" + name, Entry), true);
            File.Copy(Path.Combine(late, name, ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-" + name, ContractCompatibility.SidecarName), true);
        }
        File.Copy(Path.Combine(late, "a", "out", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-a", ContractCompatibility.SidecarName), true);
        File.Copy(Path.Combine(late, "b", "out", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-b", ContractCompatibility.SidecarName), true);
        File.Copy(Path.Combine(late, "c", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-c", ContractCompatibility.SidecarName), true);
        File.Copy(Path.Combine(late, "d", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "orbit-d", ContractCompatibility.SidecarName), true);
        var bad = File.ReadAllBytes(dllB);
        bad[^1] ^= 0xFF;
        File.WriteAllBytes(Path.Combine(serverRoot, "bad-body", Entry), bad);
        File.Copy(Path.Combine(late, "b", "out", ContractCompatibility.SidecarName), Path.Combine(serverRoot, "bad-body", ContractCompatibility.SidecarName), true);
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

        // New lanes: transport deadline, incompatible target, signed-but-incompatible
        // Contract sidecar, and a process killed inside the activator.
        RunExtraLane(output, "stall-body", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string> { ["documentAUrl"] = "http://127.0.0.1:{port}/hold/a.bin" });
        if (Directory.Exists(Path.Combine(releases, "published-stall")))
            problems.Add("stall-final");
        if (!Same(receipt, receiptB))
            problems.Add("stall-receipt");
        RunExtraLane(output, "incompatible", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("incompatible-receipt");
        RunExtraLane(output, "contract-bad", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("contract-bad-receipt");
        RunExtraLane(output, "eof-body", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string> { ["documentAUrl"] = "http://127.0.0.1:{port}/eof/a.bin" });
        if (!Same(receipt, receiptB))
            problems.Add("eof-receipt");
        RunExtraLane(output, "oversize", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string> { ["documentAUrl"] = "http://127.0.0.1:{port}/oversize/a.bin" });
        if (!Same(receipt, receiptB))
            problems.Add("oversize-receipt");
        RunExtraLane(output, "throw", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("throw-receipt");
        RunExtraLane(output, "incompatible-arch", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("incompatible-arch-receipt");
        RunExtraLane(output, "sidecar-missing", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("sidecar-missing-receipt");
        RunExtraLane(output, "sidecar-unlisted", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("sidecar-unlisted-receipt");
        RunExtraLane(output, "sidecar-tampered", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, receiptB))
            problems.Add("sidecar-tampered-receipt");
        var crashReceipt = File.Exists(receipt) ? File.ReadAllBytes(receipt) : Array.Empty<byte>();
        RunCrashLane(output, serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems, ref crashReceipt);
        RunExtraLane(output, "restore-after-crash", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, crashReceipt))
            problems.Add("crash-restore-receipt");
        RunExtraLane(output, "check-throw-offer", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, crashReceipt))
            problems.Add("check-throw-offer-receipt");
        RunExtraLane(output, "check-throw-lkg", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, crashReceipt))
            problems.Add("check-throw-lkg-receipt");
        // A callback exception must not leak its message into the host output.
        foreach (var lane in new[] { "check-throw-offer", "check-throw-lkg" })
        {
            var laneOut = Path.Combine(output, "lanes", lane, "client.stdout");
            if (File.Exists(laneOut) && File.ReadAllText(laneOut).Contains("secret", StringComparison.Ordinal))
                problems.Add(lane + "-leak");
        }
        RunExtraLane(output, "sidecar-mvid-heap-order", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        if (!Same(receipt, crashReceipt))
            problems.Add("mvid-heap-receipt");
        RunExtraLane(output, "sidecar-mvid-n-format", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        Directory.CreateDirectory(Path.Combine(output, "world-lkg", "releases"));
        Directory.CreateDirectory(Path.Combine(output, "world-lkg", "state"));
        RunExtraLane(output, "lkg-seed-legacy", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());
        RunExtraLane(output, "lkg-required-restore", serverRoot, releases, receipt, spkiPath, finalA, verifiedB, publishedB, finalBad, problems,
            new Dictionary<string, string>());

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
                "stall-body" => StallBody(map),
                "incompatible" => Incompatible(map),
                "contract-bad" => ContractBad(map),
                "crash" => Crash(map),
                "eof-body" => BodyFailure(map, "eof"),
                "oversize" => BodyFailure(map, "oversize"),
                "throw" => Throw(map),
                "incompatible-arch" => RejectThenRecover(map, "finalE", "documentE", "contentE", "none", "incompatible-arch"),
                "sidecar-missing" => RejectThenRecover(map, "finalF", "documentF", "contentF", "none", "sidecar-missing"),
                "sidecar-unlisted" => RejectThenRecover(map, "finalG", "documentG", "contentG", "unlisted", "sidecar-unlisted"),
                "sidecar-tampered" => RejectThenRecover(map, "finalH", "documentH", "contentH", "tampered", "sidecar-tampered"),
                "sidecar-mvid-heap-order" => RejectThenRecover(map, "finalJ", "documentJ", "contentJ", "none", "sidecar-mvid-heap-order"),
                "sidecar-mvid-n-format" => MvidAccepted(map),
                "lkg-seed-legacy" => LkgSeedLegacy(map),
                "lkg-required-restore" => LkgRequiredRestore(map),
                "check-throw-offer" => CheckThrowOffer(map),
                "check-throw-lkg" => CheckThrowLkg(map),
                "restore-after-crash" => Restore(map, "B", 5),
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
        if (!TryOffer(map, map["finalA"], File.ReadAllBytes(map["documentA"]), out var started))
            return FailMode("compat-a");
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
        if (!TryOffer(map, map["finalVerifiedB"], File.ReadAllBytes(map["documentB"]), out var locked))
            return FailMode("compat-b");
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
        if (!TryOffer(map, map["finalB"], File.ReadAllBytes(map["documentB"]), out var started))
            return FailMode("compat-b2");
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
        var started = TrustedReleaseRecovery.TryStart(null, File.ReadAllBytes(map["spki"]), DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate, CandidateCheck);
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

    static bool CandidateCheck(string contentRoot, TrustedUpdateCandidate candidate)
    {
        var contract = Path.Combine(AppContext.BaseDirectory, "OrbitGame.Contracts.dll");
        var allowed = ContractCompatibility.Check(contentRoot, candidate, DeliverySession.Target, contract, require: true, out var status, out var compatibility);
        Console.WriteLine("COMPAT " + status + ":" + compatibility + " selected=" + candidate.VersionName);
        return allowed;
    }

    static bool TryOffer(Dictionary<string, string> map, string final, byte[] document, out TrustedReleaseRecoveryStart started)
    {
        var spki = File.ReadAllBytes(map["spki"]);
        var verified = TrustedRelease.Verify(final, document, spki);
        if (!verified.Succeeded || verified.Candidate is null)
        {
            Console.WriteLine("COMPAT unverified " + verified.Failure + "/" + verified.Detail);
            started = null!;
            return false;
        }

        var contract = Path.Combine(AppContext.BaseDirectory, "OrbitGame.Contracts.dll");
        if (!ContractCompatibility.Check(final, verified.Candidate, DeliverySession.Target, contract, require: true, out var status, out var compatibility))
        {
            Console.WriteLine("COMPAT rejected " + status + ":" + compatibility);
            started = null!;
            return false;
        }

        Console.WriteLine("COMPAT " + status + ":" + compatibility);
        started = TrustedReleaseRecovery.TryStart(new TrustedReleaseOffer(final, document), spki, DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate, CandidateCheck);
        return true;
    }

    static string Describe(TrustedReleaseRecoveryStart started) =>
        "activated=" + started.Activated + " version=" + started.SelectedVersion + " source=" + started.Source + " plan=" + started.Candidate.Plan + " detail=" + started.Candidate.Detail;

    static int Activations => DistinctOrbit.Activations;

    static int StallBody(Dictionary<string, string> map)
    {
        var receipt = File.ReadAllBytes(map["receipt"]);
        var bound = HttpReleaseFetch.Bind(map);
        Console.WriteLine("STALL bound=" + bound);
        if (bound)
            return FailMode("stall-bound");
        if (Directory.Exists(map["finalStall"]))
            return FailMode("stall-final");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("stall-receipt");
        Console.WriteLine("DISTINCT_OK stall-body");
        return 0;
    }

    static int Incompatible(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalC", "documentC", "contentC"))
            return FailMode("stage-c");
        var receipt = File.ReadAllBytes(map["receipt"]);
        if (!TryOffer(map, map["finalC"], File.ReadAllBytes(map["documentC"]), out var started))
            return FailMode("compat-c");
        Console.WriteLine("INCOMPAT " + Describe(started));
        if (started.Candidate.Plan != TrustedUpdateFailure.IncompatibleTarget)
            return FailMode("incompatible-plan");
        if (!started.Activated || started.Source != TrustedUpdateStartSource.LastKnownGood || started.SelectedVersion != "B" || !DistinctOrbit.Publish(started))
            return FailMode("incompatible-fallback");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("incompatible-receipt");
        if (!Play("B", 5, map["finalB"]))
            return FailMode("incompatible-play");
        Console.WriteLine("DISTINCT_OK incompatible");
        return 0;
    }

    static int ContractBad(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalD", "documentD", "contentD"))
            return FailMode("stage-d");
        var receipt = File.ReadAllBytes(map["receipt"]);
        var before = Activations;
        if (TryOffer(map, map["finalD"], File.ReadAllBytes(map["documentD"]), out var started))
            return FailMode("contract-accepted");
        if (Activations != before)
            return FailMode("contract-activated");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("contract-receipt");
        var fallback = TrustedReleaseRecovery.TryStart(null, File.ReadAllBytes(map["spki"]), DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate);
        Console.WriteLine("CONTRACT_FALLBACK " + Describe(fallback));
        if (!fallback.Activated || fallback.Source != TrustedUpdateStartSource.LastKnownGood || fallback.SelectedVersion != "B" || !DistinctOrbit.Publish(fallback))
            return FailMode("contract-fallback");
        if (!Play("B", 5, map["finalB"]))
            return FailMode("contract-play");
        Console.WriteLine("DISTINCT_OK contract-bad");
        return 0;
    }

    static int BodyFailure(Dictionary<string, string> map, string kind)
    {
        var receipt = File.ReadAllBytes(map["receipt"]);
        var finalKey = kind == "eof" ? "finalEof" : "finalOversize";
        var staged = HttpReleaseFetch.Bind(map) && HttpReleaseFetch.Stage(map, finalKey, "documentA", "contentA");
        Console.WriteLine("BODY " + kind + " staged=" + staged + " exists=" + Directory.Exists(map[finalKey]));
        if (staged || Directory.Exists(map[finalKey]))
            return FailMode(kind + "-staged");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode(kind + "-receipt");
        Console.WriteLine("DISTINCT_OK " + kind);
        return 0;
    }

    static int RejectThenRecover(Dictionary<string, string> map, string finalKey, string documentKey, string contentKey, string setup, string mode)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, finalKey, documentKey, contentKey))
            return FailMode("stage-" + mode);
        var final = map[finalKey];
        if (setup == "unlisted")
        {
            // Valid-looking sidecar that is NOT in the signed file set: it must be ignored.
            File.Copy(map["validSidecar"], Path.Combine(final, ContractCompatibility.SidecarName), true);
        }
        else if (setup == "tampered")
        {
            var sidecar = Path.Combine(final, ContractCompatibility.SidecarName);
            var json = File.ReadAllText(sidecar);
            var index = json.IndexOf("\"mvid\":\"", StringComparison.Ordinal);
            if (index < 0)
                return FailMode("tamper-shape");
            json = json[..(index + 9)] + "0" + json[(index + 9)..];
            File.WriteAllText(sidecar, json);
        }

        var receipt = File.ReadAllBytes(map["receipt"]);
        var before = Activations;
        if (TryOffer(map, final, File.ReadAllBytes(map[documentKey]), out _))
            return FailMode(mode + "-accepted");
        if (Activations != before)
            return FailMode(mode + "-activated");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode(mode + "-receipt");
        var fallback = TrustedReleaseRecovery.TryStart(null, File.ReadAllBytes(map["spki"]), DeliverySession.Target, map["releases"], map["receipt"], DistinctOrbit.Activate);
        Console.WriteLine("REJECT_FALLBACK " + Describe(fallback));
        if (!fallback.Activated || fallback.Source != TrustedUpdateStartSource.LastKnownGood || fallback.SelectedVersion != "B" || !DistinctOrbit.Publish(fallback))
            return FailMode(mode + "-fallback");
        if (!Play("B", 5, map["finalB"]))
            return FailMode(mode + "-play");
        Console.WriteLine("DISTINCT_OK " + mode);
        return 0;
    }

    static int MvidAccepted(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalI", "documentI", "contentI"))
            return FailMode("stage-i");
        if (!TryOffer(map, map["finalI"], File.ReadAllBytes(map["documentI"]), out var started))
            return FailMode("mvid-n-rejected");
        Console.WriteLine("MVID_N " + Describe(started));
        if (!started.Activated || started.Source != TrustedUpdateStartSource.Candidate || started.SelectedVersion != "I" || !DistinctOrbit.Publish(started))
            return FailMode("mvid-n-start");
        if (!Play("I", 3, map["finalI"]))
            return FailMode("mvid-n-play");
        Console.WriteLine("DISTINCT_OK sidecar-mvid-n-format");
        return 0;
    }

    static int CheckThrowOffer(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalK", "documentC", "contentC"))
            return FailMode("stage-k");
        var receipt = File.ReadAllBytes(map["receipt"]);
        var before = Activations;
        bool ThrowForOffer(string root, TrustedUpdateCandidate candidate)
        {
            if (candidate.VersionName == "C")
                throw new InvalidOperationException("offer-check-secret");
            return CandidateCheck(root, candidate);
        }

        var started = TrustedReleaseRecovery.TryStart(
            new TrustedReleaseOffer(map["finalK"], File.ReadAllBytes(map["documentC"])),
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            DistinctOrbit.Activate,
            ThrowForOffer);
        Console.WriteLine("THROW_OFFER " + Describe(started));
        if (started.Activated && started.SelectedVersion == "C")
            return FailMode("offer-throw-activated");
        if (started.Candidate.Plan != TrustedUpdateFailure.InvalidCandidate || started.Candidate.Detail != "compat")
            return FailMode("offer-throw-plan");
        if (!started.Activated || started.Source != TrustedUpdateStartSource.LastKnownGood || started.SelectedVersion != "B" || !DistinctOrbit.Publish(started))
            return FailMode("offer-throw-fallback");
        if (Activations != before + 1)
            return FailMode("offer-throw-activations");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("offer-throw-receipt");
        if (!Play("B", 5, map["finalB"]))
            return FailMode("offer-throw-play");
        Console.WriteLine("DISTINCT_OK check-throw-offer");
        return 0;
    }

    static int CheckThrowLkg(Dictionary<string, string> map)
    {
        var receipt = File.ReadAllBytes(map["receipt"]);
        var before = Activations;
        var thrown = TrustedReleaseRecovery.TryStart(
            null,
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            DistinctOrbit.Activate,
            (root, candidate) => throw new InvalidOperationException("lkg-check-secret"));
        Console.WriteLine("THROW_LKG " + Describe(thrown));
        if (thrown.Activated)
            return FailMode("lkg-throw-activated");
        if (thrown.Recovery.Plan != TrustedUpdateFailure.LastKnownGoodUnusable || thrown.Recovery.Detail != "compat")
            return FailMode("lkg-throw-plan");
        if (Activations != before)
            return FailMode("lkg-throw-activations");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("lkg-throw-receipt");

        // The gate must still be free after a throwing check: a second, valid selection works.
        var recovered = TrustedReleaseRecovery.TryStart(
            null,
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            DistinctOrbit.Activate,
            CandidateCheck);
        Console.WriteLine("THROW_LKG_RETRY " + Describe(recovered));
        if (!recovered.Activated || recovered.Source != TrustedUpdateStartSource.LastKnownGood || recovered.SelectedVersion != "B" || !DistinctOrbit.Publish(recovered))
            return FailMode("lkg-retry");
        if (!Play("B", 5, map["finalB"]))
            return FailMode("lkg-retry-play");
        Console.WriteLine("DISTINCT_OK check-throw-lkg");
        return 0;
    }

    static int LkgSeedLegacy(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "lkgFinal", "documentF", "contentF"))
            return FailMode("stage-lkg");
        var started = TrustedReleaseRecovery.TryStart(
            new TrustedReleaseOffer(map["lkgFinal"], File.ReadAllBytes(map["documentF"])),
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["lkgReleases"],
            map["lkgReceipt"],
            DistinctOrbit.Activate);
        Console.WriteLine("LKG_SEED " + Describe(started));
        if (!started.Activated || started.Source != TrustedUpdateStartSource.Candidate || started.SelectedVersion != "F" || !DistinctOrbit.Publish(started))
            return FailMode("lkg-seed");
        Console.WriteLine("DISTINCT_OK lkg-seed-legacy");
        return 0;
    }

    static int LkgRequiredRestore(Dictionary<string, string> map)
    {
        if (!File.Exists(map["lkgReceipt"]))
            return FailMode("lkg-receipt-missing");
        var before = File.ReadAllBytes(map["lkgReceipt"]);
        var started = TrustedReleaseRecovery.TryStart(
            null,
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["lkgReleases"],
            map["lkgReceipt"],
            DistinctOrbit.Activate,
            CandidateCheck);
        Console.WriteLine("LKG_REQUIRED " + Describe(started));
        if (started.Activated)
            return FailMode("lkg-activated");
        if (Activations != 0)
            return FailMode("lkg-activation-count");
        if (!File.ReadAllBytes(map["lkgReceipt"]).AsSpan().SequenceEqual(before))
            return FailMode("lkg-receipt");
        if (started.Recovery.Plan != TrustedUpdateFailure.LastKnownGoodUnusable)
            return FailMode("lkg-plan");
        Console.WriteLine("DISTINCT_OK lkg-required-restore");
        return 0;
    }

    static int Throw(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalThrow", "documentB", "contentB"))
            return FailMode("stage-throw");
        var receipt = File.ReadAllBytes(map["receipt"]);
        var failed = TrustedReleaseRecovery.TryStart(
            new TrustedReleaseOffer(map["finalThrow"], File.ReadAllBytes(map["documentB"])),
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            (candidate, source, _) => throw new InvalidOperationException("activation-throw"));
        Console.WriteLine("THROW " + Describe(failed));
        if (failed.Activated)
            return FailMode("throw-activated");
        if (failed.Candidate.Activation != TrustedUpdateFailure.ActivationFailed)
            return FailMode("throw-plan");
        if (!File.ReadAllBytes(map["receipt"]).AsSpan().SequenceEqual(receipt))
            return FailMode("throw-receipt");
        var locked = TrustedReleaseRecovery.TryStart(
            new TrustedReleaseOffer(map["finalThrow"], File.ReadAllBytes(map["documentB"])),
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            DistinctOrbit.Activate);
        Console.WriteLine("THROW_LOCK " + Describe(locked));
        if (locked.Activated || locked.Candidate.Plan != TrustedUpdateFailure.ProcessSelectionLocked)
            return FailMode("throw-lock");
        if (Activations != 0)
            return FailMode("throw-activations");
        Console.WriteLine("DISTINCT_OK throw");
        return 0;
    }

    static int Crash(Dictionary<string, string> map)
    {
        if (!HttpReleaseFetch.Bind(map))
            return FailMode("bind");
        if (!HttpReleaseFetch.Stage(map, "finalCrash", "documentB", "contentB"))
            return FailMode("stage-crash");
        var started = TrustedReleaseRecovery.TryStart(
            new TrustedReleaseOffer(map["finalCrash"], File.ReadAllBytes(map["documentB"])),
            File.ReadAllBytes(map["spki"]),
            DeliverySession.Target,
            map["releases"],
            map["receipt"],
            (candidate, source, _) =>
            {
                File.WriteAllText(map["crashMarker"], "entered " + candidate.VersionName);
                Thread.Sleep(60000);
                return new TrustedUpdateActivation(TrustedUpdateFailure.None, 0);
            });
        Console.WriteLine("CRASH_RETURNED " + Describe(started));
        return FailMode("crash-returned");
    }

    static Dictionary<string, string> ExtraRequest(string output, string mode, int port, string serverRoot, string releases, string receipt, string spki, string finalA, string verifiedB, string publishedB, string finalBad, Dictionary<string, string> overrides)
    {
        var lane = Path.Combine(output, "lanes", mode);
        var lines = new Dictionary<string, string>
        {
            ["releases"] = releases,
            ["receipt"] = receipt,
            ["spki"] = spki,
            ["finalA"] = finalA,
            ["finalVerifiedB"] = verifiedB,
            ["finalB"] = publishedB,
            ["finalBad"] = finalBad,
            ["finalStall"] = Path.Combine(releases, "published-stall"),
            ["finalC"] = Path.Combine(releases, "published-c"),
            ["finalD"] = Path.Combine(releases, "published-bad-contract"),
            ["finalCrash"] = Path.Combine(releases, "published-crash"),
            ["finalThrow"] = Path.Combine(releases, "published-throw"),
            ["finalEof"] = Path.Combine(releases, "published-eof"),
            ["finalE"] = Path.Combine(releases, "published-arch"),
            ["finalF"] = Path.Combine(releases, "published-missing-sidecar"),
            ["finalG"] = Path.Combine(releases, "published-unlisted-sidecar"),
            ["finalH"] = Path.Combine(releases, "published-tampered-sidecar"),
            ["finalI"] = Path.Combine(releases, "published-mvid-n"),
            ["finalJ"] = Path.Combine(releases, "published-mvid-heap"),
            ["documentE"] = Path.Combine(lane, "document-e.bin"),
            ["documentF"] = Path.Combine(lane, "document-f.bin"),
            ["documentG"] = Path.Combine(lane, "document-g.bin"),
            ["documentH"] = Path.Combine(lane, "document-h.bin"),
            ["documentI"] = Path.Combine(lane, "document-i.bin"),
            ["documentJ"] = Path.Combine(lane, "document-j.bin"),
            ["documentEUrl"] = "http://127.0.0.1:" + port + "/e.bin",
            ["documentFUrl"] = "http://127.0.0.1:" + port + "/f.bin",
            ["documentGUrl"] = "http://127.0.0.1:" + port + "/g.bin",
            ["documentHUrl"] = "http://127.0.0.1:" + port + "/h.bin",
            ["documentIUrl"] = "http://127.0.0.1:" + port + "/i.bin",
            ["documentJUrl"] = "http://127.0.0.1:" + port + "/j.bin",
            ["contentBaseE"] = "http://127.0.0.1:" + port + "/orbit-e/",
            ["contentBaseF"] = "http://127.0.0.1:" + port + "/orbit-f/",
            ["contentBaseG"] = "http://127.0.0.1:" + port + "/orbit-g/",
            ["contentBaseH"] = "http://127.0.0.1:" + port + "/orbit-h/",
            ["contentBaseI"] = "http://127.0.0.1:" + port + "/orbit-i/",
            ["contentBaseJ"] = "http://127.0.0.1:" + port + "/orbit-j/",
            ["filesE"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesF"] = Entry,
            ["filesG"] = Entry,
            ["filesH"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesI"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesJ"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["finalOversize"] = Path.Combine(releases, "published-oversize"),
            ["documentA"] = Path.Combine(lane, "document-a.bin"),
            ["documentB"] = Path.Combine(lane, "document-b.bin"),
            ["documentC"] = Path.Combine(lane, "document-c.bin"),
            ["documentD"] = Path.Combine(lane, "document-d.bin"),
            ["documentAUrl"] = "http://127.0.0.1:" + port + "/a.bin",
            ["documentBUrl"] = "http://127.0.0.1:" + port + "/b.bin",
            ["documentCUrl"] = "http://127.0.0.1:" + port + "/c.bin",
            ["documentDUrl"] = "http://127.0.0.1:" + port + "/d.bin",
            ["contentBaseA"] = "http://127.0.0.1:" + port + "/orbit-a/",
            ["contentBaseB"] = "http://127.0.0.1:" + port + "/orbit-b/",
            ["contentBaseC"] = "http://127.0.0.1:" + port + "/orbit-c/",
            ["contentBaseD"] = "http://127.0.0.1:" + port + "/orbit-d/",
            ["filesA"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesB"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesC"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["filesD"] = Entry + ";" + ContractCompatibility.SidecarName,
            ["entry"] = Entry,
            ["crashMarker"] = Path.Combine(lane, "crash.entered"),
            ["validSidecar"] = Path.Combine(output, "late", "a", "out", ContractCompatibility.SidecarName),
            ["lkgReleases"] = Path.Combine(output, "world-lkg", "releases"),
            ["lkgReceipt"] = Path.Combine(output, "world-lkg", "state", "receipt.bin"),
            ["lkgFinal"] = Path.Combine(output, "world-lkg", "releases", "published-legacy"),
            ["finalK"] = Path.Combine(releases, "published-check-throw"),
        };
        foreach (var pair in overrides)
            lines[pair.Key] = pair.Value.Replace("{port}", port.ToString());
        var request = Path.Combine(lane, "request.txt");
        File.WriteAllLines(request, lines.Select(pair => pair.Key + "=" + pair.Value));
        return lines;
    }

    static bool StartServer(string lane, string serverRoot, out int port, out Process serverProcess)
    {
        var portFile = Path.Combine(lane, "port.txt");
        var log = Path.Combine(lane, "server.log");
        var stall = Path.Combine(lane, "stall.signal");
        File.WriteAllText(log, "");
        serverProcess = Start(new[] { "--http-server", serverRoot, portFile, log, stall }, lane, "server");
        if (!WaitFile(portFile, 10000))
        {
            Stop(serverProcess, lane, "server");
            port = 0;
            return false;
        }

        for (var attempt = 0; attempt < 40; attempt++)
        {
            try
            {
                port = int.Parse(File.ReadAllText(portFile).Trim());
                return true;
            }
            catch (IOException)
            {
                Thread.Sleep(50);
            }
        }

        Stop(serverProcess, lane, "server");
        port = 0;
        return false;
    }

    static void RunExtraLane(string output, string mode, string serverRoot, string releases, string receiptPath, string spki, string finalA, string verifiedB, string publishedB, string finalBad, List<string> problems, Dictionary<string, string> overrides)
    {
        var lane = Path.Combine(output, "lanes", mode);
        Directory.CreateDirectory(lane);
        if (!StartServer(lane, serverRoot, out var port, out var serverProcess))
        {
            problems.Add(mode + ":no-port");
            return;
        }

        ExtraRequest(output, mode, port, serverRoot, releases, receiptPath, spki, finalA, verifiedB, publishedB, finalBad, overrides);
        var request = Path.Combine(lane, "request.txt");
        CopyReceipt(output, mode + "-before", receiptPath);
        var client = Start(new[] { "--distinct-http-child", mode, request }, lane, "client");
        var finished = Finish(client, lane, "client", 25000);
        Stop(serverProcess, lane, "server");
        CopyReceipt(output, mode + "-after", receiptPath);
        var stdout = File.ReadAllText(Path.Combine(lane, "client.stdout"));
        Console.WriteLine("LANE " + mode + " pid=" + finished.Pid + " exit=" + finished.Exit + " watchdog=" + finished.Watchdog);
        if (finished.Watchdog || finished.Exit != 0 || !stdout.Contains("DISTINCT_OK", StringComparison.Ordinal))
            problems.Add(mode);
    }

    static void RunCrashLane(string output, string serverRoot, string releases, string receiptPath, string spki, string finalA, string verifiedB, string publishedB, string finalBad, List<string> problems, ref byte[] receiptBefore)
    {
        const string mode = "crash";
        var lane = Path.Combine(output, "lanes", mode);
        Directory.CreateDirectory(lane);
        if (!StartServer(lane, serverRoot, out var port, out var serverProcess))
        {
            problems.Add(mode + ":no-port");
            return;
        }

        var lines = ExtraRequest(output, mode, port, serverRoot, releases, receiptPath, spki, finalA, verifiedB, publishedB, finalBad, new Dictionary<string, string>());
        var request = Path.Combine(lane, "request.txt");
        CopyReceipt(output, mode + "-before", receiptPath);
        var client = Start(new[] { "--distinct-http-child", mode, request }, lane, "client");
        var marker = lines["crashMarker"];
        var entered = WaitFile(marker, 20000);
        var alive = !client.HasExited;
        Stop(client, lane, "client");
        Stop(serverProcess, lane, "server");
        CopyReceipt(output, mode + "-after", receiptPath);
        Console.WriteLine("LANE crash entered=" + entered + " killed-while-running=" + alive + " pid=" + client.Id);
        if (!entered || !alive)
            problems.Add("crash-not-interrupted");
        if (!File.ReadAllBytes(receiptPath).AsSpan().SequenceEqual(receiptBefore))
            problems.Add("crash-receipt");
    }

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
            "filesA=" + Entry + ";" + ContractCompatibility.SidecarName,
            "filesB=" + Entry + ";" + ContractCompatibility.SidecarName,
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

    static byte[] Sign(ECDsa key, string dir, string version, bool badContract = false, string? runtime = null, string? architecture = null, bool includeSidecar = true, string? mvidOverride = null)
    {
        if (includeSidecar)
            WriteSidecar(dir, badContract, architecture, mvidOverride);
        var files = includeSidecar ? new[] { Entry, ContractCompatibility.SidecarName } : new[] { Entry };
        var signed = TrustedRelease.Sign(
            dir,
            new TrustedReleaseIdentity(version, runtime ?? "net11.0", architecture ?? DeliverySession.Target.Architecture, TypeName, MethodName, Entry),
            files,
            key);
        return signed.Succeeded && signed.Document is not null ? signed.Document : Array.Empty<byte>();
    }

    // The sidecar is one signed file, not a new envelope field. The expected
    // Contract identity comes from the host deployment, not from the package.
    static void WriteSidecar(string dir, bool badContract, string? architecture = null, string? mvidOverride = null)
    {
        var contract = Path.Combine(AppContext.BaseDirectory, "OrbitGame.Contracts.dll");
        if (!ContractCompatibility.TryReadAssembly(contract, out var identity, out var detail))
            throw new InvalidOperationException("contract " + detail);
        var mvid = mvidOverride ?? (badContract ? Guid.NewGuid().ToString("D") : identity.Mvid);
        var json = JsonSerializer.Serialize(new
        {
            schema = ContractCompatibility.Schema,
            runtime = "net11.0",
            architecture = architecture ?? DeliverySession.Target.Architecture,
            contract = new { name = identity.Name, version = identity.Version, mvid, source = "host deployment config" },
        });
        File.WriteAllText(Path.Combine(dir, ContractCompatibility.SidecarName), json);
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
