using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RuneCLR.TrustedUpdate;

if (args.Length > 0 && args[0] == "--child")
    return RecoveryChild.Run(args);

return RecoverySuite.Run();

static class RecoverySuite
{
    public static int Run()
    {
        var failures = 0;
        var tests = new (string Name, Action Run)[]
        {
            ("A saved release is restored when the next offer is absent", RestoresWithoutOffer),
            ("A bad signature falls back to the saved release", BadSignatureRestores),
            ("A bad target falls back to the saved release", BadTargetRestores),
            ("A missing signed file falls back to the saved release", MissingFileRestores),
            ("Activation failure keeps the receipt and the process gate", ActivationFailureKeepsReceipt),
            ("A thrown activator keeps the receipt and the process gate", ThrownActivatorKeepsReceipt),
            ("The next process restores A after an activation failure", NextProcessRestoresAfterFailure),
            ("The wrong host key cannot activate the receipt", WrongKeyRejected),
            ("A tampered signature in a valid receipt is rejected", TamperedReceiptRejected),
            ("A receipt content root swap is not authorization", SwappedContentRootRejected),
            ("A releases-root ancestor link cannot place the receipt inside", RootAliasInsideRejected),
            ("An aliased releases root still accepts an outside receipt", RootAliasOutsideAccepted),
            ("A multi-hop releases alias cannot place the receipt inside", RootAliasMultiHopRejected),
            ("An intermediate releases alias cannot place the receipt inside", RootAliasIntermediateRejected),
            ("A link target with an intermediate alias cannot place the receipt inside", RootAliasTargetInsideRejected),
            ("A link target with an intermediate alias still accepts an outside receipt", RootAliasTargetOutsideAccepted),
            ("A system temp alias still rejects a receipt inside the releases tree", SystemTempAliasInsideRejected),
            ("A system temp alias still accepts a receipt outside the releases tree", SystemTempAliasOutsideAccepted),
            ("A receipt path cannot escape the releases root", TraversalRejected),
            ("Replacing an additional file cannot activate", ReplacedAdditionalRejected),
            ("Fallback keeps the additional file", FallbackKeepsAdditional),
            ("Receipt write failure still reports activation and keeps the old receipt", PersistFailureKeepsOldReceipt),
            ("An oversized receipt is rejected before activation", OversizedReceiptRejected),
            ("A receipt inside the releases root is rejected before load", ReceiptInsideReleasesRejected),
            ("A short SPKI is rejected before load", ShortSpkiRejected),
            ("A prefix sibling of the releases root stays outside", PrefixSiblingIsOutside),
            ("A case-different releases path follows the platform comparison", CaseBoundaryFollowsPlatform),
            ("A second plan failure before the activator still restores", SecondPlanRestoresBeforeActivation),
            ("A spaced content root is rejected before activation", SpacedRelativeRejectedBeforeActivation),
            ("A too-long relative content root is rejected before activation", LongRelativeRejectedBeforeActivation),
            ("A receipt file symlink is rejected before read", ReceiptFileLinkRejected),
            ("An ancestor link into the releases root is rejected", AncestorLinkRejected),
            ("Extra candidate fields in the receipt are not trusted", ExtraFieldsAreNotTrusted),
            ("The document byte limit is separate from the receipt limit", DocumentLimitIsSeparate),
            ("An offered start then a no-offer start reports the process lock", LockAfterOfferedStart),
            ("A restored start then a no-offer start reports the process lock", LockAfterRecoveryStart),
            ("A failed restore then a no-offer start reports the process lock", LockAfterRecoveryActivationFailure),
        };
        foreach (var (name, run) in tests)
        {
            try
            {
                run();
                Console.WriteLine("PASS " + name);
            }
            catch (Exception exception)
            {
                failures++;
                Console.Error.WriteLine("FAIL " + name + ": " + exception.Message);
            }
        }

        Console.WriteLine((tests.Length - failures) + "/" + tests.Length + " tests passed");
        return failures == 0 ? 0 : 1;
    }

    static void RestoresWithoutOffer() => RunRestore("recover-none", "-", "-");

    static void BadSignatureRestores()
    {
        using var world = World.Create();
        var bad = world.DocumentB.ToArray();
        bad[bad.Length / 2] ^= 0x20;
        var path = Path.Combine(world.Root, "bad-sig.bin");
        File.WriteAllBytes(path, bad);
        Run(world, "recover-signature", world.PackageB, path);
    }

    static void BadTargetRestores()
    {
        using var world = World.Create();
        Run(world, "recover-target", world.PackageArm, world.DocumentArmPath);
    }

    static void MissingFileRestores()
    {
        using var world = World.Create();
        File.Delete(Path.Combine(world.PackageB, "Data", "Notes.txt"));
        Run(world, "recover-missing", world.PackageB, world.DocumentBPath);
    }

    static void ActivationFailureKeepsReceipt() => RunGate("activate-fail");

    static void ThrownActivatorKeepsReceipt() => RunGate("activate-throw");

    static void NextProcessRestoresAfterFailure()
    {
        using var world = World.Create();
        Run(world, "activate-fail", world.PackageB, world.DocumentBPath);
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "recover-none", "-", "-");
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "next process rewrote the receipt");
    }

    static void WrongKeyRejected()
    {
        using var world = World.Create();
        using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var spki = Path.Combine(world.Root, "other.spki");
        File.WriteAllBytes(spki, other.ExportSubjectPublicKeyInfo());
        Run(world, "wrong-key", "-", "-", spki);
    }

    static void TamperedReceiptRejected()
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        File.WriteAllBytes(world.Receipt, FlipReceiptSignature(before));
        Run(world, "tamper-sig", "-", "-");
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(FlipReceiptSignature(before)), "signature tamper rewrote the receipt");
    }

    static void SwappedContentRootRejected()
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        File.WriteAllBytes(world.Receipt, RewriteReceipt(before, "b", ReadReceiptDocument(before)));
        Run(world, "swap-root", "-", "-");
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(RewriteReceipt(before, "b", ReadReceiptDocument(before))), "content root swap rewrote the receipt");
    }

    static void RootAliasInsideRejected() => RunRootAlias(multiHop: false, intermediate: false, outside: false);

    static void RootAliasOutsideAccepted() => RunRootAlias(multiHop: false, intermediate: false, outside: true);

    static void RootAliasMultiHopRejected() => RunRootAlias(multiHop: true, intermediate: false, outside: false);

    static void RootAliasIntermediateRejected() => RunRootAlias(multiHop: false, intermediate: true, outside: false);

    static void RootAliasTargetInsideRejected() => RunRootAlias(multiHop: false, intermediate: false, outside: false, targetAlias: true);

    static void RootAliasTargetOutsideAccepted() => RunRootAlias(multiHop: false, intermediate: false, outside: true, targetAlias: true);

    static void RunRootAlias(bool multiHop, bool intermediate, bool outside, bool targetAlias = false)
    {
        using var world = World.Create();
        var physical = Path.Combine(world.Root, "physical");
        Directory.CreateDirectory(physical);
        string alias;
        if (targetAlias)
        {
            var bridge = Path.Combine(world.Root, "bridge");
            LinkDirectory(bridge, world.Root);
            alias = Path.Combine(world.Root, "alias");
            LinkDirectory(alias, Path.Combine(bridge, "physical"));
        }
        else if (intermediate)
        {
            var container = Path.Combine(world.Root, "container");
            Directory.CreateDirectory(container);
            alias = Path.Combine(container, "jump");
            LinkDirectory(alias, physical);
        }
        else if (multiHop)
        {
            var hop = Path.Combine(world.Root, "hop");
            LinkDirectory(hop, physical);
            alias = Path.Combine(world.Root, "alias");
            if (OperatingSystem.IsWindows())
                LinkDirectory(alias, hop);
            else
                Directory.CreateSymbolicLink(alias, hop);
        }
        else
        {
            alias = Path.Combine(world.Root, "alias");
            LinkDirectory(alias, physical);
        }

        var allowed = Path.Combine(alias, "releases");
        var physicalContent = Path.Combine(physical, "releases", "a");
        var document = world.SignAt(physicalContent, "1.0.0", "x64", "Game.dll");
        var docPath = Path.Combine(world.Root, "alias-offer.bin");
        File.WriteAllBytes(docPath, document);
        var offer = Path.Combine(alias, "releases", "a");
        string receipt;
        string mode;
        if (outside)
        {
            var state = Path.Combine(world.Root, "external-state");
            Directory.CreateDirectory(state);
            receipt = Path.Combine(state, "current.json");
            mode = "root-alias-outside";
        }
        else
        {
            receipt = Path.Combine(physical, "releases", "receipt.json");
            mode = "root-alias-inside";
        }

        Run(world, mode, offer, docPath, receipt: receipt, releases: allowed);
        if (outside)
        {
            Check(File.Exists(receipt), "outside receipt was not written");
            Check(!File.Exists(Path.Combine(physical, "releases", "receipt.json")), "outside run wrote inside releases");
        }
        else
        {
            Check(!File.Exists(receipt), "alias wrote the physical receipt");
            Check(!File.Exists(Path.Combine(allowed, "receipt.json")), "alias wrote through the releases link");
        }
    }

    static void SystemTempAliasInsideRejected() => RunSystemTempAlias(outside: false);

    static void SystemTempAliasOutsideAccepted() => RunSystemTempAlias(outside: true);

    static void RunSystemTempAlias(bool outside)
    {
        using var world = World.Create();
        var physical = Path.Combine(world.Root, "private-tree");
        Directory.CreateDirectory(physical);
        var ancestor = Path.Combine(world.Root, "temp-alias");
        LinkDirectory(ancestor, physical);
        var allowed = Path.Combine(ancestor, "app", "releases");
        var document = world.SignAt(Path.Combine(physical, "app", "releases", "a"), "1.0.0", "x64", "Game.dll");
        var docPath = Path.Combine(world.Root, "temp-alias-offer.bin");
        File.WriteAllBytes(docPath, document);
        var offer = Path.Combine(ancestor, "app", "releases", "a");
        if (outside)
        {
            var state = Path.Combine(physical, "app", "state");
            Directory.CreateDirectory(state);
            var receipt = Path.Combine(ancestor, "app", "state", "current.json");
            Run(world, "root-alias-outside", offer, docPath, receipt: receipt, releases: allowed);
            Check(File.Exists(Path.Combine(state, "current.json")), "outside receipt was not written");
            Check(!File.Exists(Path.Combine(physical, "app", "releases", "receipt.json")), "outside run wrote inside releases");
            return;
        }

        var inside = Path.Combine(physical, "app", "releases", "receipt.json");
        Run(world, "root-alias-inside", offer, docPath, receipt: inside, releases: allowed);
        Check(!File.Exists(inside), "temp alias wrote the physical receipt");
        Check(!File.Exists(Path.Combine(allowed, "receipt.json")), "temp alias wrote through the releases link");
    }

    static void LinkDirectory(string link, string target)
    {
        if (OperatingSystem.IsWindows())
        {
            using var proc = Process.Start(new ProcessStartInfo
            {
                FileName = "cmd.exe",
                ArgumentList = { "/d", "/c", "mklink", "/J", link, target },
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            }) ?? throw new InvalidOperationException("junction did not start");
            var stdout = proc.StandardOutput.ReadToEnd();
            var stderr = proc.StandardError.ReadToEnd();
            proc.WaitForExit();
            if (proc.ExitCode != 0)
                throw new InvalidOperationException(stdout + stderr);
        }
        else
        {
            Directory.CreateSymbolicLink(link, target);
        }

        if ((File.GetAttributes(link) & FileAttributes.ReparsePoint) == 0)
            throw new InvalidOperationException("link was not a reparse point");
    }

    static byte[] ReadReceiptDocument(byte[] receipt)
    {
        using var json = JsonDocument.Parse(receipt);
        return Convert.FromBase64String(json.RootElement.GetProperty("document").GetString()!);
    }

    static byte[] RewriteReceipt(byte[] receipt, string contentRoot, byte[] document)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            writer.WriteNumber("v", 1);
            writer.WriteString("contentRoot", contentRoot);
            writer.WriteString("document", Convert.ToBase64String(document));
            writer.WriteEndObject();
        }

        return buffer.ToArray();
    }

    static byte[] FlipReceiptSignature(byte[] receipt)
    {
        var document = ReadReceiptDocument(receipt);
        var text = System.Text.Encoding.UTF8.GetString(document);
        if (text.Contains('\r'))
            throw new InvalidOperationException("receipt document has CR");
        var first = text.IndexOf('\n');
        var second = first < 0 ? -1 : text.IndexOf('\n', first + 1);
        if (first <= 0 || second <= first || text[..first] != "RTRSIG1" || text[(second + 1)..].Contains('\n'))
            throw new InvalidOperationException("receipt document is not RTRSIG1");
        var signature = Convert.FromBase64String(text[(first + 1)..second]);
        if (signature.Length != TrustedRelease.SignatureBytes)
            throw new InvalidOperationException("signature length");
        signature[0] ^= 0x01;
        var rebuilt = System.Text.Encoding.UTF8.GetBytes("RTRSIG1\n" + Convert.ToBase64String(signature) + "\n" + text[(second + 1)..]);
        return RewriteReceipt(receipt, "a", rebuilt);
    }

    static void TraversalRejected()
    {
        using var world = World.Create();
        var text = File.ReadAllText(world.Receipt).Replace("\"contentRoot\":\"a\"", "\"contentRoot\":\"../outside\"", StringComparison.Ordinal);
        File.WriteAllText(world.Receipt, text);
        File.WriteAllBytes(Path.Combine(world.Root, "outside-secret.bin"), "secret"u8.ToArray());
        Run(world, "traversal", "-", "-");
    }

    static void ReplacedAdditionalRejected()
    {
        using var world = World.Create();
        File.WriteAllBytes(Path.Combine(world.PackageA, "Data", "Notes.txt"), "tampered-notes"u8.ToArray());
        Run(world, "replace-extra", "-", "-");
    }

    static void FallbackKeepsAdditional() => RunRestore("recover-none", "-", "-");

    static void PersistFailureKeepsOldReceipt()
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "persist-fail", world.PackageB, world.DocumentBPath);
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "failed write replaced the receipt");
        var temps = Directory.GetFiles(Path.GetDirectoryName(world.Receipt)!, "receipt-*.tmp");
        Check(temps.Length == 0, "persist failure left a temp file");
        Run(world, "recover-none", "-", "-");
    }

    static void OversizedReceiptRejected()
    {
        using var world = World.Create();
        File.WriteAllBytes(world.Receipt, new byte[TrustedReleaseRecovery.MaxReceiptBytes + 1]);
        Run(world, "oversized", "-", "-");
    }

    static void ReceiptInsideReleasesRejected()
    {
        using var world = World.Create();
        var inside = Path.Combine(world.Releases, "current.json");
        File.Copy(world.Receipt, inside);
        Run(world, "config-receipt", "-", "-", world.SpkiPath, inside);
    }

    static void ShortSpkiRejected()
    {
        using var world = World.Create();
        var shortSpki = Path.Combine(world.Root, "short.spki");
        File.WriteAllBytes(shortSpki, new byte[TrustedRelease.SpkiBytes - 1]);
        Run(world, "config-spki", "-", "-", shortSpki);
    }

    static void PrefixSiblingIsOutside()
    {
        using var world = World.Create();
        var package = Path.Combine(world.Root, "releases-extra", "pkg");
        var document = world.SignAt(package, "9.9.9", "x64", "Game.dll");
        var path = Path.Combine(world.Root, "extra.bin");
        File.WriteAllBytes(path, document);
        Run(world, "prefix-outside", package, path);
    }

    static void CaseBoundaryFollowsPlatform()
    {
        using var world = World.Create();
        var parent = Path.GetDirectoryName(world.Releases)!;
        var name = Path.GetFileName(world.Releases).ToCharArray();
        name[0] = char.IsUpper(name[0]) ? char.ToLowerInvariant(name[0]) : char.ToUpperInvariant(name[0]);
        var flipped = Path.Combine(parent, new string(name), "b");
        Run(world, "case-boundary", flipped, world.DocumentBPath);
    }

    static void SecondPlanRestoresBeforeActivation()
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "second-plan", world.PackageB, world.DocumentBPath);
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "second plan recovery rewrote the receipt");
    }

    static void SpacedRelativeRejectedBeforeActivation()
    {
        using var world = World.Create();
        var package = Path.Combine(world.Releases, "bad name");
        var document = world.SignAt(package, "3.0.0", "x64", "Game.dll");
        var path = Path.Combine(world.Root, "spaced.bin");
        File.WriteAllBytes(path, document);
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "unsafe-relative", package, path);
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "unsafe relative replaced the receipt");
    }

    static void LongRelativeRejectedBeforeActivation()
    {
        var root = Path.Combine(Path.GetTempPath(), "rr" + Guid.NewGuid().ToString("n")[..8]);
        using var world = World.Create(root: root);
        var package = Path.Combine(world.Releases, new string('b', TrustedRelease.MaxPathLength + 1));
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "long-relative", package, world.DocumentBPath);
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "long relative replaced the receipt");
    }

    static void ReceiptFileLinkRejected()
    {
        using var world = World.Create();
        var elsewhere = Path.Combine(world.Root, "elsewhere.json");
        File.Copy(world.Receipt, elsewhere);
        var linked = Path.Combine(Path.GetDirectoryName(world.Receipt)!, "linked.json");
        File.CreateSymbolicLink(linked, elsewhere);
        Run(world, "config-link", "-", "-", receipt: linked);
    }

    static void AncestorLinkRejected()
    {
        using var world = World.Create();
        var hidden = Path.Combine(world.Releases, "hidden");
        Directory.CreateDirectory(hidden);
        var planted = Path.Combine(hidden, "current.json");
        File.Copy(world.Receipt, planted);
        var plantedBytes = File.ReadAllBytes(planted);
        var jump = Path.Combine(world.Root, "jump");
        Directory.CreateSymbolicLink(jump, hidden);
        Run(world, "config-ancestor", "-", "-", receipt: Path.Combine(jump, "current.json"));
        Check(File.ReadAllBytes(planted).AsSpan().SequenceEqual(plantedBytes), "ancestor link changed the planted receipt");
    }

    static void ExtraFieldsAreNotTrusted()
    {
        using var world = World.Create();
        using var json = JsonDocument.Parse(File.ReadAllBytes(world.Receipt));
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            foreach (var property in json.RootElement.EnumerateObject())
                property.WriteTo(writer);
            writer.WritePropertyName("candidate");
            writer.WriteStartObject();
            writer.WriteString("version", "9.9.9");
            writer.WriteString("contentSha256", "deadbeef");
            writer.WriteEndObject();
            writer.WritePropertyName("approval");
            writer.WriteStartObject();
            writer.WriteString("version", "9.9.9");
            writer.WriteString("approvalId", "forged");
            writer.WriteEndObject();
            writer.WriteEndObject();
        }

        File.WriteAllBytes(world.Receipt, buffer.ToArray());
        Run(world, "extra-fields", "-", "-");
        Check(File.ReadAllText(world.Receipt).Contains("9.9.9", StringComparison.Ordinal), "forged receipt fields were removed");
    }

    static void DocumentLimitIsSeparate()
    {
        using var world = World.Create();
        var body = new byte[TrustedRelease.MaxDocumentBytes + 1];
        var text = "{\"v\":1,\"contentRoot\":\"a\",\"document\":\"" + Convert.ToBase64String(body) + "\"}";
        var bytes = Encoding.UTF8.GetBytes(text);
        Check(bytes.Length <= TrustedReleaseRecovery.MaxReceiptBytes, "fixture exceeds the receipt cap");
        File.WriteAllBytes(world.Receipt, bytes);
        Run(world, "document-limit", "-", "-");
    }

    static void LockAfterOfferedStart()
    {
        using var world = World.Create();
        Run(world, "lock-after-offer", world.PackageB, world.DocumentBPath);
    }

    static void LockAfterRecoveryStart()
    {
        using var world = World.Create();
        Run(world, "lock-after-recover", "-", "-");
    }

    static void LockAfterRecoveryActivationFailure()
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, "lock-after-recover-fail", "-", "-");
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "failed restore replaced the receipt");
    }

    static void RunRestore(string mode, string content, string document)
    {
        using var world = World.Create();
        Run(world, mode, content, document);
    }

    static void RunGate(string mode)
    {
        using var world = World.Create();
        var before = File.ReadAllBytes(world.Receipt);
        Run(world, mode, world.PackageB, world.DocumentBPath);
        Check(File.ReadAllBytes(world.Receipt).AsSpan().SequenceEqual(before), "activation failure changed the receipt");
    }

    static void Run(World world, string mode, string content, string document, string? spki = null, string? receipt = null, string? releases = null)
    {
        var output = RecoveryChild.Launch(mode, releases ?? world.Releases, receipt ?? world.Receipt, spki ?? world.SpkiPath, content, document);
        Check(output.Contains("OK " + mode, StringComparison.Ordinal), output);
    }
    static void Check(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }
}

static class RecoveryChild
{
    public static string Launch(string mode, string releases, string receipt, string spki, string content, string document)
    {
        var start = new ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = AppContext.BaseDirectory,
        };
        start.ArgumentList.Add("--child");
        start.ArgumentList.Add(mode);
        start.ArgumentList.Add(releases);
        start.ArgumentList.Add(receipt);
        start.ArgumentList.Add(spki);
        start.ArgumentList.Add(content);
        start.ArgumentList.Add(document);
        using var child = Process.Start(start) ?? throw new InvalidOperationException("child did not start");
        var stdout = child.StandardOutput.ReadToEnd();
        var stderr = child.StandardError.ReadToEnd();
        child.WaitForExit();
        if (child.ExitCode != 0)
            throw new InvalidOperationException(stdout + stderr);
        return stdout + stderr;
    }

    public static int Run(string[] args)
    {
        var mode = args[1];
        var releases = args[2];
        var receipt = args[3];
        var spki = File.ReadAllBytes(args[4]);
        var content = args[5];
        var documentPath = args[6];
        var target = new TrustedUpdateTarget("net11.0", "x64");
        TrustedReleaseOffer? offer = documentPath == "-"
            ? null
            : new TrustedReleaseOffer(content, File.ReadAllBytes(documentPath));
        var trace = new Trace();
        TrustedUpdateActivation Activate(TrustedUpdateCandidate candidate, TrustedUpdateStartSource source, TrustedUpdateFailure failure)
        {
            trace.Calls++;
            trace.Source = source.ToString();
            trace.Failure = failure;
            trace.Version = candidate.VersionName;
            var files = candidate.AdditionalContent;
            trace.Additional = files?.Count ?? 0;
            if (files is { Count: > 0 })
                trace.ExtraHash = files[0].ContentSha256;
            if (mode == "activate-fail" || mode == "lock-after-recover-fail")
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            if (mode == "activate-throw")
                throw new InvalidOperationException("activator-threw");
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, 7);
        }

        if (mode == "persist-fail")
            return PersistFail(offer, spki, target, releases, receipt, Activate, trace);
        if (mode == "lock-after-offer" || mode == "lock-after-recover" || mode == "lock-after-recover-fail")
            return LockPair(mode, offer, spki, target, releases, receipt, Activate, trace);
        if (mode == "second-plan")
        {
            TrustedReleaseRecoveryDiagnostics.BeforeHostStart = () => File.Delete(Path.Combine(content, "Game.dll"));
        }

        var before = File.Exists(receipt) ? File.ReadAllBytes(receipt) : Array.Empty<byte>();
        var result = TrustedReleaseRecovery.TryStart(offer, spki, target, releases, receipt, Activate);
        var after = File.Exists(receipt) ? File.ReadAllBytes(receipt) : Array.Empty<byte>();
        var ok = Expect(mode, result, trace, releases, receipt, documentPath, before, after, offer, spki, target);
        Console.WriteLine(ok ? "OK " + mode : Describe(mode, result, trace));
        return ok ? 0 : 1;
    }

    static int PersistFail(
        TrustedReleaseOffer? offer,
        byte[] spki,
        TrustedUpdateTarget target,
        string releases,
        string receipt,
        TrustedUpdateActivator activate,
        Trace trace)
    {
        var before = File.ReadAllBytes(receipt);
        TrustedReleaseRecoveryDiagnostics.FailNextPersist = true;
        var first = TrustedReleaseRecovery.TryStart(offer, spki, target, releases, receipt, activate);
        var second = TrustedReleaseRecovery.TryStart(offer, spki, target, releases, receipt, activate);
        var after = File.ReadAllBytes(receipt);
        var directory = Path.GetDirectoryName(receipt)!;
        var temps = Directory.GetFiles(directory, "receipt-*.tmp");
        var ok = first.Activated
            && first.SelectedVersion == "2.0.0"
            && first.Source == TrustedUpdateStartSource.Candidate
            && first.Value == 7
            && first.Persistence == TrustedReleasePersistenceFailure.IoFailure
            && first.PersistenceDetail == "write"
            && trace.Calls == 1
            && before.AsSpan().SequenceEqual(after)
            && temps.Length == 0
            && second.Candidate.Plan == TrustedUpdateFailure.ProcessSelectionLocked
            && second.Candidate.Activation == TrustedUpdateFailure.ProcessSelectionLocked;
        Console.WriteLine(ok ? "OK persist-fail" : Describe("persist-fail", first, trace) + " second=" + second.Candidate.Activation + " temps=" + temps.Length);
        return ok ? 0 : 1;
    }

    static int LockPair(
        string mode,
        TrustedReleaseOffer? offer,
        byte[] spki,
        TrustedUpdateTarget target,
        string releases,
        string receipt,
        TrustedUpdateActivator activate,
        Trace trace)
    {
        var before = File.ReadAllBytes(receipt);
        var firstOffer = mode == "lock-after-offer" ? offer : null;
        var first = TrustedReleaseRecovery.TryStart(firstOffer, spki, target, releases, receipt, activate);
        var second = TrustedReleaseRecovery.TryStart(null, spki, target, releases, receipt, activate);
        var after = File.ReadAllBytes(receipt);
        var locked = !second.Activated
            && second.Recovery.Plan == TrustedUpdateFailure.ProcessSelectionLocked
            && second.Recovery.Detail == "locked"
            && second.Recovery.Activation == TrustedUpdateFailure.None
            && second.Candidate.Plan == TrustedUpdateFailure.None
            && second.Candidate.Activation == TrustedUpdateFailure.None
            && second.Candidate.Detail == "absent"
            && trace.Calls == 1;
        var ok = mode switch
        {
            "lock-after-offer" => first.Activated && first.Source == TrustedUpdateStartSource.Candidate && first.SelectedVersion == "2.0.0" && first.Persistence == TrustedReleasePersistenceFailure.None && first.Value == 7 && locked,
            "lock-after-recover" => first.Activated && first.Source == TrustedUpdateStartSource.LastKnownGood && first.SelectedVersion == "1.0.0" && first.Value == 7 && before.AsSpan().SequenceEqual(after) && locked,
            "lock-after-recover-fail" => !first.Activated && first.Recovery.Activation == TrustedUpdateFailure.ActivationFailed && first.Recovery.Detail == "activation" && before.AsSpan().SequenceEqual(after) && locked,
            _ => false,
        };
        Console.WriteLine(ok ? "OK " + mode : Describe(mode, second, trace) + " first=" + first.Activated + "/" + first.Source + "/" + first.SelectedVersion + "/" + first.Recovery.Activation + "/" + first.Recovery.Detail);
        return ok ? 0 : 1;
    }

    static bool Expect(
        string mode,
        TrustedReleaseRecoveryStart result,
        Trace trace,
        string releases,
        string receipt,
        string documentPath,
        byte[] before,
        byte[] after,
        TrustedReleaseOffer? offer,
        byte[] spki,
        TrustedUpdateTarget target)
    {
        var notes = Path.Combine(releases, "a", "Data", "Notes.txt");
        var expectedHash = File.Exists(notes) ? Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(notes))) : "";
        var sameReceipt = before.AsSpan().SequenceEqual(after);
        var restored = result.Activated
            && result.Source == TrustedUpdateStartSource.LastKnownGood
            && result.SelectedVersion == "1.0.0"
            && result.Value == 7
            && trace.Calls == 1
            && trace.Source == "LastKnownGood"
            && trace.Version == "1.0.0"
            && trace.Additional == 1
            && trace.ExtraHash == expectedHash
            && sameReceipt;
        return mode switch
        {
            "save" => result.Activated && result.Source == TrustedUpdateStartSource.Candidate && result.SelectedVersion == "1.0.0" && result.Value == 7 && result.Persistence == TrustedReleasePersistenceFailure.None && trace.Additional == 1 && trace.ExtraHash == expectedHash && trace.Source == "Candidate" && trace.Calls == 1 && ReceiptSaved(receipt, spki, documentPath),
            "recover-none" => restored && result.Candidate.Detail == "absent" && trace.Failure == TrustedUpdateFailure.None,
            "recover-signature" => restored && result.Candidate.Verification == TrustedReleaseFailure.InvalidSignature && trace.Failure == TrustedUpdateFailure.None,
            "recover-target" => restored && result.Candidate.Plan == TrustedUpdateFailure.IncompatibleTarget && trace.Failure == TrustedUpdateFailure.IncompatibleTarget,
            "recover-missing" => restored && result.Candidate.Verification == TrustedReleaseFailure.ContentMismatch && trace.Failure == TrustedUpdateFailure.None,
            "extra-fields" => restored && trace.Failure == TrustedUpdateFailure.None,
            "prefix-outside" => restored && result.Candidate.Verification == TrustedReleaseFailure.OutsideContentRoot && result.Candidate.Detail == "root" && trace.Failure == TrustedUpdateFailure.None,
            "second-plan" => restored && result.Candidate.Plan == TrustedUpdateFailure.MissingContent && result.Candidate.Detail == "plan" && result.Candidate.Activation == TrustedUpdateFailure.None && trace.Failure == TrustedUpdateFailure.MissingContent,
            "unsafe-relative" or "long-relative" => restored && result.Candidate.Verification == TrustedReleaseFailure.InvalidPath && result.Candidate.Detail == "relative" && result.Candidate.Activation == TrustedUpdateFailure.None && trace.Failure == TrustedUpdateFailure.None,
            "case-boundary" => OperatingSystem.IsWindows()
                ? result.Activated && result.Source == TrustedUpdateStartSource.Candidate && result.SelectedVersion == "2.0.0" && result.Value == 7 && trace.Calls == 1 && trace.Source == "Candidate" && trace.Version == "2.0.0" && trace.Additional == 1
                : restored && result.Candidate.Verification == TrustedReleaseFailure.OutsideContentRoot && result.Candidate.Detail == "root" && trace.Failure == TrustedUpdateFailure.None,
            "activate-fail" or "activate-throw" => !result.Activated && result.Candidate.Activation == TrustedUpdateFailure.ActivationFailed && trace.Calls == 1 && sameReceipt && SecondIsLocked(offer, spki, target, releases, receipt, trace),
            "wrong-key" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.InvalidSignature,
            "tamper-sig" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.InvalidSignature && sameReceipt,
            "swap-root" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.ContentMismatch && sameReceipt,
            "root-alias-inside" => !result.Activated && trace.Calls == 0 && result.ConfigurationDetail == "receipt-root",
            "root-alias-outside" => result.Activated && result.Source == TrustedUpdateStartSource.Candidate && result.SelectedVersion == "1.0.0" && result.Value == 7 && result.Persistence == TrustedReleasePersistenceFailure.None && trace.Calls == 1 && trace.Source == "Candidate",
            "traversal" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.OutsideContentRoot && result.Recovery.Detail == "path",
            "replace-extra" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.ContentMismatch,
            "oversized" => !result.Activated && trace.Calls == 0 && result.Recovery.Detail == "receipt-size",
            "document-limit" => !result.Activated && trace.Calls == 0 && result.Recovery.Verification == TrustedReleaseFailure.InvalidDocument && result.Recovery.Detail == "document-size",
            "config-receipt" => !result.Activated && trace.Calls == 0 && result.ConfigurationDetail == "receipt-root",
            "config-spki" => !result.Activated && trace.Calls == 0 && result.ConfigurationDetail == "spki",
            "config-link" => !result.Activated && trace.Calls == 0 && result.ConfigurationDetail == "receipt-link",
            "config-ancestor" => !result.Activated && trace.Calls == 0 && result.ConfigurationDetail == "receipt-root",
            _ => false,
        };
    }

    static bool SecondIsLocked(TrustedReleaseOffer? offer, byte[] spki, TrustedUpdateTarget target, string releases, string receipt, Trace trace)
    {
        var second = TrustedReleaseRecovery.TryStart(offer, spki, target, releases, receipt, (_, _, _) =>
        {
            trace.Calls++;
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, 9);
        });
        return second.Candidate.Activation == TrustedUpdateFailure.ProcessSelectionLocked
            && second.Candidate.Plan == TrustedUpdateFailure.ProcessSelectionLocked
            && trace.Calls == 1;
    }

    static bool ReceiptSaved(string receipt, byte[] spki, string documentPath)
    {
        var bytes = File.ReadAllBytes(receipt);
        if (IndexOf(bytes, spki) >= 0)
            return false;
        using var json = JsonDocument.Parse(bytes);
        var root = json.RootElement;
        if (root.GetProperty("contentRoot").GetString() != "a")
            return false;
        var document = Convert.FromBase64String(root.GetProperty("document").GetString()!);
        return document.AsSpan().SequenceEqual(File.ReadAllBytes(documentPath));
    }

    static int IndexOf(byte[] haystack, byte[] needle)
    {
        for (var i = 0; i <= haystack.Length - needle.Length; i++)
        {
            var same = true;
            for (var j = 0; j < needle.Length; j++)
            {
                if (haystack[i + j] != needle[j])
                {
                    same = false;
                    break;
                }
            }

            if (same)
                return i;
        }

        return -1;
    }

    static string Describe(string mode, TrustedReleaseRecoveryStart result, Trace trace) =>
        "BAD " + mode
        + " activated=" + result.Activated
        + " version=" + result.SelectedVersion
        + " source=" + result.Source
        + " value=" + result.Value
        + " seen=" + trace.Source
        + " seenVersion=" + trace.Version
        + " seenFailure=" + trace.Failure
        + " calls=" + trace.Calls
        + " files=" + trace.Additional
        + " config=" + result.ConfigurationDetail
        + " cand=" + result.Candidate.Verification + "/" + result.Candidate.Plan + "/" + result.Candidate.Activation + "/" + result.Candidate.Detail
        + " rec=" + result.Recovery.Verification + "/" + result.Recovery.Plan + "/" + result.Recovery.Activation + "/" + result.Recovery.Detail
        + " persist=" + result.Persistence + "/" + result.PersistenceDetail;
}



sealed class Trace
{
    public int Calls;
    public string Source = "";
    public TrustedUpdateFailure Failure;
    public string Version = "";
    public int Additional = -1;
    public string ExtraHash = "";
}

sealed class World : IDisposable
{
    public required string Root { get; init; }
    public required string Releases { get; init; }
    public required string Receipt { get; init; }
    public required string SpkiPath { get; init; }
    public required string PackageA { get; init; }
    public required string PackageB { get; init; }
    public required string PackageArm { get; init; }
    public required byte[] DocumentB { get; init; }
    public required string DocumentBPath { get; init; }
    public required string DocumentArmPath { get; init; }
    public required byte[] KeyPkcs8 { get; init; }

    public static World Create(bool arm = false, string? root = null)
    {
        root ??= Path.Combine(Path.GetTempPath(), "runeclr-recovery-" + Guid.NewGuid().ToString("n"));
        var releases = Path.Combine(root, "releases");
        var state = Path.Combine(root, "state");
        Directory.CreateDirectory(state);
        var packageA = Path.Combine(releases, "a");
        var packageB = Path.Combine(releases, "b");
        var packageArm = Path.Combine(releases, "arm");
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var spkiPath = Path.Combine(root, "host.spki");
        File.WriteAllBytes(spkiPath, key.ExportSubjectPublicKeyInfo());
        var docA = Sign(packageA, "1.0.0", "x64", key, "Game.dll", "Data/Notes.txt");
        var docB = Sign(packageB, "2.0.0", "x64", key, "Game.dll", "Data/Notes.txt");
        var docArm = Sign(packageArm, "2.0.0", "arm64", key, "Game.dll");
        var docAPath = Path.Combine(root, "a.bin");
        var docBPath = Path.Combine(root, "b.bin");
        var docArmPath = Path.Combine(root, "arm.bin");
        File.WriteAllBytes(docAPath, docA);
        File.WriteAllBytes(docBPath, docB);
        File.WriteAllBytes(docArmPath, docArm);
        var receipt = Path.Combine(state, "current.json");
        var world = new World
        {
            Root = root,
            Releases = releases,
            Receipt = receipt,
            SpkiPath = spkiPath,
            PackageA = packageA,
            PackageB = packageB,
            PackageArm = packageArm,
            DocumentB = docB,
            DocumentBPath = docBPath,
            DocumentArmPath = docArmPath,
            KeyPkcs8 = key.ExportPkcs8PrivateKey(),
        };
        var output = RecoveryChild.Launch("save", releases, receipt, spkiPath, packageA, docAPath);
        if (!output.Contains("OK save", StringComparison.Ordinal))
            throw new InvalidOperationException(output);
        return world;
    }

    public byte[] SignAt(string contentRoot, string version, string architecture, params string[] files)
    {
        using var key = ECDsa.Create();
        key.ImportPkcs8PrivateKey(KeyPkcs8, out _);
        return Sign(contentRoot, version, architecture, key, files);
    }

    static byte[] Sign(string contentRoot, string version, string architecture, ECDsa key, params string[] files)
    {
        foreach (var relative in files)
        {
            var directory = contentRoot;
            var segments = relative.Split('/');
            for (var i = 0; i < segments.Length - 1; i++)
                directory = Path.Combine(directory, segments[i]);
            Directory.CreateDirectory(directory);
            File.WriteAllBytes(Path.Combine(directory, segments[^1]), System.Text.Encoding.UTF8.GetBytes(version + ":" + segments[^1]));
        }

        var signed = TrustedRelease.Sign(
            contentRoot,
            new TrustedReleaseIdentity(version, "net11.0", architecture, "Game.Entry", "Activate", "Game.dll"),
            files,
            key);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("sign " + signed.Failure + " " + signed.Detail);
        return signed.Document;
    }

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(Root))
                Directory.Delete(Root, recursive: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }
}
