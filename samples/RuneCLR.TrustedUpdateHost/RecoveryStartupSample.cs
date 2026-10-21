using System.Security.Cryptography;
using RuneCLR.TrustedUpdate;

static class RecoveryStartupSample
{
    public static int Usage()
    {
        Console.WriteLine("RECOVERY-USAGE --recoverable-start <releases-root> <receipt-file> <host-spki-file> [offered-content-root signed-release-file]");
        Console.WriteLine("RECOVERY-USAGE --recovery-self-test");
        return 1;
    }

    public static int Start(
        string releasesRoot,
        string receiptFile,
        string hostSpkiFile,
        TrustedUpdateTarget hostTarget,
        string? offeredContentRoot,
        string? offeredReleaseFile) =>
        Execute(releasesRoot, receiptFile, hostSpkiFile, hostTarget, offeredContentRoot, offeredReleaseFile).Code;

    public static int ThrowThenLocked(
        string releasesRoot,
        string receiptFile,
        string hostSpkiFile,
        TrustedUpdateTarget hostTarget,
        string offeredContentRoot,
        string offeredReleaseFile)
    {
        if (Environment.GetEnvironmentVariable("TRUSTED_RECOVERY_CHILD") == "offer-then-locked")
            return OfferThenLocked(releasesRoot, receiptFile, hostSpkiFile, hostTarget, offeredContentRoot, offeredReleaseFile);

        var first = Execute(releasesRoot, receiptFile, hostSpkiFile, hostTarget, offeredContentRoot, offeredReleaseFile);
        var second = Execute(releasesRoot, receiptFile, hostSpkiFile, hostTarget, null, null);
        return first.Code == 3 && Locked(second) && Calls == 1 ? 3 : 1;
    }

    public static int OfferThenLocked(
        string releasesRoot,
        string receiptFile,
        string hostSpkiFile,
        TrustedUpdateTarget hostTarget,
        string offeredContentRoot,
        string offeredReleaseFile)
    {
        var first = Execute(releasesRoot, receiptFile, hostSpkiFile, hostTarget, offeredContentRoot, offeredReleaseFile);
        var second = Execute(releasesRoot, receiptFile, hostSpkiFile, hostTarget, null, null);
        return first.Code == 0 && first.Result?.Activated == true && Locked(second) && Calls == 1 ? 0 : 1;
    }

    static bool Locked(StartReport report) =>
        report.Result is { Activated: false } result
        && result.Recovery.Plan == TrustedUpdateFailure.ProcessSelectionLocked
        && result.Recovery.Detail == "locked";

    static StartReport Execute(
        string releasesRoot,
        string receiptFile,
        string hostSpkiFile,
        TrustedUpdateTarget hostTarget,
        string? offeredContentRoot,
        string? offeredReleaseFile)
    {
        try
        {
            releasesRoot = RealPath(releasesRoot);
            receiptFile = Path.GetFullPath(receiptFile);
            if (offeredContentRoot is not null && offeredReleaseFile is not null)
                offeredContentRoot = RealPath(offeredContentRoot);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            Console.WriteLine("RECOVERY-START REJECTED config=path");
            Console.WriteLine("RECOVERY-CALLS " + Calls);
            return new StartReport(2, null);
        }

        if (!SignedStartupSample.TryReadExact(hostSpkiFile, TrustedRelease.SpkiBytes, out var spki, out var keyDetail))
        {
            Console.WriteLine("RECOVERY-START REJECTED config=spki " + keyDetail);
            Console.WriteLine("RECOVERY-CALLS " + Calls);
            return new StartReport(2, null);
        }

        TrustedReleaseOffer? offer = null;
        if (offeredContentRoot is not null || offeredReleaseFile is not null)
        {
            if (offeredContentRoot is null || offeredReleaseFile is null)
                return new StartReport(Usage(), null);
            if (!SignedStartupSample.TryReadBounded(offeredReleaseFile, TrustedRelease.MaxDocumentBytes, out var document, out var readDetail))
            {
                Console.WriteLine("RECOVERY-START OFFER-READ " + readDetail);
                if (readDetail == "size")
                    offer = new TrustedReleaseOffer(offeredContentRoot, new byte[TrustedRelease.MaxDocumentBytes + 1]);
            }
            else
            {
                offer = new TrustedReleaseOffer(offeredContentRoot, document);
            }
        }

        var result = TrustedReleaseRecovery.TryStart(offer, spki, hostTarget, releasesRoot, receiptFile, Activate);
        if (result.Activated)
        {
            Console.WriteLine(
                "RECOVERY-START OK source=" + result.Source
                + " version=" + result.SelectedVersion
                + " value=" + result.Value
                + " additional=" + Additional
                + " persistence=" + result.Persistence
                + (result.Persistence == TrustedReleasePersistenceFailure.None ? "" : " " + result.PersistenceDetail)
                + " candidate=" + Format(result.Candidate)
                + " recovery=" + Format(result.Recovery));
            Console.WriteLine("RECOVERY-CALLS " + Calls);
            return new StartReport(0, result);
        }

        var code = 2;
        if (result.Candidate.Activation != TrustedUpdateFailure.None || result.Recovery.Activation != TrustedUpdateFailure.None)
            code = 3;
        else if (result.Candidate.Plan != TrustedUpdateFailure.None || result.Recovery.Plan != TrustedUpdateFailure.None)
            code = 4;
        Console.WriteLine(
            "RECOVERY-START REJECTED source=" + result.Source
            + " config=" + result.ConfigurationDetail
            + " candidate=" + Format(result.Candidate)
            + " recovery=" + Format(result.Recovery)
            + " persistence=" + result.Persistence);
        Console.WriteLine("RECOVERY-CALLS " + Calls);
        return new StartReport(code, result);
    }

    sealed class StartReport
    {
        internal StartReport(int code, TrustedReleaseRecoveryStart? result)
        {
            Code = code;
            Result = result;
        }

        internal int Code { get; }
        internal TrustedReleaseRecoveryStart? Result { get; }
    }

    public static int SelfTest(TrustedUpdateTarget hostTarget)
    {
        var root = RealPath(Path.Combine(RealPath(Path.GetTempPath()), "trusted-recovery-" + Guid.NewGuid().ToString("n")));
        Directory.CreateDirectory(root);
        var failed = 0;
        try
        {
            using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var spkiFile = Path.Combine(root, "host.spki");
            File.WriteAllBytes(spkiFile, key.ExportSubjectPublicKeyInfo());
            var releases = Path.Combine(root, "releases");
            var state = Path.Combine(root, "state");
            var offers = Path.Combine(root, "offers");
            Directory.CreateDirectory(releases);
            Directory.CreateDirectory(state);
            Directory.CreateDirectory(offers);
            var receipt = Path.Combine(state, "receipt.bin");
            var marker = Path.Combine(root, "marker.txt");
            var goodRoot = Path.Combine(releases, "A");
            var signatureRoot = Path.Combine(releases, "Bsig");
            var targetRoot = Path.Combine(releases, "Btarget");
            var missingRoot = Path.Combine(releases, "Bmissing");
            var throwRoot = Path.Combine(releases, "Bthrow");
            Directory.CreateDirectory(goodRoot);
            Directory.CreateDirectory(signatureRoot);
            Directory.CreateDirectory(targetRoot);
            Directory.CreateDirectory(missingRoot);
            Directory.CreateDirectory(throwRoot);
            SignedStartupSample.WritePackage(goodRoot, throws: false);
            SignedStartupSample.WritePackage(signatureRoot, throws: false);
            SignedStartupSample.WritePackage(targetRoot, throws: false);
            SignedStartupSample.WritePackage(missingRoot, throws: false);
            SignedStartupSample.WritePackage(throwRoot, throws: true);
            var privateFile = Path.Combine(goodRoot, "TrustedUpdate.Private.bin");
            var helperFile = Path.Combine(goodRoot, "TrustedUpdate.Helper.bin");
            var privateHash = Hash(privateFile);
            var helperHash = Hash(helperFile);
            var goodDoc = SignedStartupSample.SignPackage(goodRoot, SignedStartupSample.Identity(hostTarget, "good-a"), key);
            using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var badDoc = SignedStartupSample.SignPackage(signatureRoot, SignedStartupSample.Identity(hostTarget, "sig-b"), other);
            var wrongTarget = SignForArchitecture(targetRoot, hostTarget, "target-b", "wrong-arch", key);
            var missingDoc = SignedStartupSample.SignPackage(missingRoot, SignedStartupSample.Identity(hostTarget, "missing-b"), key);
            var throwDoc = SignedStartupSample.SignPackage(throwRoot, SignedStartupSample.Identity(hostTarget, "throw-b"), key);
            if (goodDoc is null || badDoc is null || wrongTarget is null || missingDoc is null || throwDoc is null)
            {
                Console.WriteLine("RECOVERY-SELF-TEST failed=sign");
                return 1;
            }

            File.Delete(Path.Combine(missingRoot, "TrustedUpdate.Helper.bin"));
            var goodFile = Path.Combine(offers, "good.signed");
            var badFile = Path.Combine(offers, "bad.signed");
            var targetFile = Path.Combine(offers, "target.signed");
            var missingFile = Path.Combine(offers, "missing.signed");
            var throwFile = Path.Combine(offers, "throw.signed");
            File.WriteAllBytes(goodFile, goodDoc);
            File.WriteAllBytes(badFile, badDoc);
            File.WriteAllBytes(targetFile, wrongTarget);
            File.WriteAllBytes(missingFile, missingDoc);
            File.WriteAllBytes(throwFile, throwDoc);

            Delete(marker);
            var offered = Run(marker, "--recoverable-start", releases, receipt, spkiFile, goodRoot, goodFile);
            failed += Check(offered.ExitCode == 0
                && offered.Output.Contains("RECOVERY-CALL source=Candidate version=good-a additional=2 calls=1", StringComparison.Ordinal)
                && offered.Output.Contains("RECOVERY-START OK source=Candidate version=good-a value=130 additional=2 persistence=None", StringComparison.Ordinal)
                && Read(marker) == "130"
                && File.Exists(receipt)
                && Hash(privateFile) == privateHash
                && Hash(helperFile) == helperHash, "offered-a");
            var receiptBytes = File.ReadAllBytes(receipt);

            if (!TryFileLink(Path.Combine(state, "receipt-link.bin"), receipt, out var linkSkip))
            {
                if (linkSkip == "unsupported")
                    Console.WriteLine("SKIP receipt-leaf-link unsupported");
                else
                    failed += Check(false, "receipt-leaf-link");
            }
            else
            {
                Delete(marker);
                var linked = Run(marker, "--recoverable-start", releases, Path.Combine(state, "receipt-link.bin"), spkiFile);
                failed += Check(linked.ExitCode == 2
                    && linked.Output.Contains("config=receipt-link", StringComparison.Ordinal)
                    && linked.Output.Contains("RECOVERY-CALLS 0", StringComparison.Ordinal)
                    && !linked.Output.Contains("RECOVERY-CALL source=", StringComparison.Ordinal)
                    && !linked.Output.Contains("RECOVERY-START OK", StringComparison.Ordinal)
                    && !File.Exists(marker)
                    && Same(receiptBytes, receipt), "receipt-leaf-link");
            }

            Delete(marker);
            var recovered = Run(marker, "--recoverable-start", releases, receipt, spkiFile);
            failed += Check(recovered.ExitCode == 0
                && recovered.Output.Contains("RECOVERY-CALL source=LastKnownGood version=good-a additional=2 calls=1", StringComparison.Ordinal)
                && recovered.Output.Contains("RECOVERY-START OK source=LastKnownGood version=good-a value=130 additional=2 persistence=None", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt), "recover-a");

            failed += Recovered(marker, receipt, receiptBytes, releases, spkiFile, signatureRoot, badFile, "candidate=InvalidSignature/None/None/mismatch", "bad-signature-recovers-a");
            failed += Recovered(marker, receipt, receiptBytes, releases, spkiFile, targetRoot, targetFile, "candidate=None/IncompatibleTarget/None/plan", "wrong-target-recovers-a");
            failed += Recovered(marker, receipt, receiptBytes, releases, spkiFile, missingRoot, missingFile, "candidate=ContentMismatch/None/None/missing", "missing-file-recovers-a");

            var hugeFile = Path.Combine(offers, "huge.signed");
            File.WriteAllBytes(hugeFile, new byte[TrustedRelease.MaxDocumentBytes + 1]);
            Delete(marker);
            var huge = Run(marker, "--recoverable-start", releases, receipt, spkiFile, goodRoot, hugeFile);
            failed += Check(huge.ExitCode == 0
                && huge.Output.Contains("RECOVERY-START OFFER-READ size", StringComparison.Ordinal)
                && huge.Output.Contains("RECOVERY-CALL source=LastKnownGood version=good-a additional=2 calls=1", StringComparison.Ordinal)
                && huge.Output.Contains("candidate=InvalidDocument/None/None/document-size", StringComparison.Ordinal)
                && !huge.Output.Contains("source=Candidate", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt), "oversized-offer-recovers-a");

            Delete(marker);
            var missingOffer = Run(marker, "--recoverable-start", releases, receipt, spkiFile, goodRoot, Path.Combine(offers, "absent.signed"));
            failed += Check(missingOffer.ExitCode == 0
                && missingOffer.Output.Contains("RECOVERY-START OFFER-READ io", StringComparison.Ordinal)
                && missingOffer.Output.Contains("RECOVERY-CALL source=LastKnownGood version=good-a additional=2 calls=1", StringComparison.Ordinal)
                && missingOffer.Output.Contains("candidate=None/None/None/absent", StringComparison.Ordinal)
                && !missingOffer.Output.Contains("source=Candidate", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt), "missing-offer-recovers-a");

            Delete(marker);
            var thrown = Run(marker, "--recovery-child", "throw-then-locked", releases, receipt, spkiFile, throwRoot, throwFile);
            failed += Check(thrown.ExitCode == 3
                && Count(thrown.Output, "RECOVERY-CALL source=") == 1
                && thrown.Output.Contains("RECOVERY-CALL source=Candidate version=throw-b additional=2 calls=1", StringComparison.Ordinal)
                && thrown.Output.Contains("candidate=None/None/ActivationFailed/activation", StringComparison.Ordinal)
                && !thrown.Output.Contains("RECOVERY-START OK", StringComparison.Ordinal)
                && !thrown.Output.Contains("source=LastKnownGood", StringComparison.Ordinal)
                && thrown.Output.Contains("recovery=None/ProcessSelectionLocked/None/locked", StringComparison.Ordinal)
                && Count(thrown.Output, "recovery=None/ProcessSelectionLocked/None/locked") == 1
                && !thrown.Output.Contains("signed-activate-fault", StringComparison.Ordinal)
                && Count(thrown.Output, "RECOVERY-CALLS 1") == 2
                && !File.Exists(marker)
                && Same(receiptBytes, receipt), "throw-no-fallback");

            Delete(marker);
            var afterThrow = Run(marker, "--recoverable-start", releases, receipt, spkiFile);
            failed += Check(afterThrow.ExitCode == 0
                && afterThrow.Output.Contains("RECOVERY-START OK source=LastKnownGood version=good-a value=130 additional=2 persistence=None", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt), "recover-after-throw");

            var offerReceipt = Path.Combine(state, "offer-lock.bin");
            var offerMarker = Path.Combine(root, "marker-offer.txt");
            Delete(offerMarker);
            var offeredLock = RunWithMode(offerMarker, "offer-then-locked", "--recovery-child", "throw-then-locked", releases, offerReceipt, spkiFile, goodRoot, goodFile);
            failed += Check(offeredLock.ExitCode == 0
                && Count(offeredLock.Output, "RECOVERY-CALL source=") == 1
                && offeredLock.Output.Contains("RECOVERY-CALL source=Candidate version=good-a additional=2 calls=1", StringComparison.Ordinal)
                && Count(offeredLock.Output, "RECOVERY-START OK source=Candidate version=good-a value=130 additional=2 persistence=None") == 1
                && offeredLock.Output.Contains("recovery=None/ProcessSelectionLocked/None/locked", StringComparison.Ordinal)
                && Count(offeredLock.Output, "recovery=None/ProcessSelectionLocked/None/locked") == 1
                && !offeredLock.Output.Contains("source=LastKnownGood", StringComparison.Ordinal)
                && Count(offeredLock.Output, "RECOVERY-CALLS 1") == 2
                && Read(offerMarker) == "130"
                && File.Exists(offerReceipt)
                && Same(receiptBytes, receipt), "offer-then-locked");

            Delete(marker);
            var badPath = Run(marker, "--recoverable-start", "", receipt, spkiFile);
            failed += Check(badPath.ExitCode == 2
                && badPath.Output.Contains("RECOVERY-START REJECTED config=path", StringComparison.Ordinal)
                && badPath.Output.Contains("RECOVERY-CALLS 0", StringComparison.Ordinal)
                && !badPath.Output.Contains("RECOVERY-CALL source=", StringComparison.Ordinal)
                && !badPath.Output.Contains("RECOVERY-START OK", StringComparison.Ordinal)
                && !badPath.Output.Contains("Exception", StringComparison.Ordinal)
                && !badPath.Output.Contains("RecoveryStartupSample.RealPath", StringComparison.Ordinal)
                && Same(receiptBytes, receipt), "path-normalization");

            var wrongSpki = Path.Combine(root, "wrong.spki");
            File.WriteAllBytes(wrongSpki, other.ExportSubjectPublicKeyInfo());
            Delete(marker);
            var wrongKey = Run(marker, "--recoverable-start", releases, receipt, wrongSpki);
            failed += Check(wrongKey.ExitCode != 0
                && wrongKey.Output.Contains("recovery=InvalidSignature/None/None/mismatch", StringComparison.Ordinal)
                && !wrongKey.Output.Contains("RECOVERY-START OK", StringComparison.Ordinal)
                && !wrongKey.Output.Contains("RECOVERY-CALL source=", StringComparison.Ordinal)
                && !File.Exists(marker)
                && Same(receiptBytes, receipt)
                && Hash(helperFile) == helperHash, "wrong-host-key");

            var hugeSpki = Path.Combine(root, "huge.spki");
            File.WriteAllBytes(hugeSpki, new byte[TrustedRelease.SpkiBytes + 1]);
            Delete(marker);
            var badLength = Run(marker, "--recoverable-start", releases, receipt, hugeSpki);
            failed += Check(badLength.ExitCode == 2
                && badLength.Output.Contains("RECOVERY-START REJECTED config=spki size", StringComparison.Ordinal)
                && !badLength.Output.Contains("RECOVERY-CALL source=", StringComparison.Ordinal)
                && !File.Exists(marker)
                && Same(receiptBytes, receipt), "spki-length");

            var helperBytes = File.ReadAllBytes(helperFile);
            helperBytes[0] ^= 0x5A;
            File.WriteAllBytes(helperFile, helperBytes);
            Delete(marker);
            var tampered = Run(marker, "--recoverable-start", releases, receipt, spkiFile);
            failed += Check(tampered.ExitCode != 0
                && tampered.Output.Contains("recovery=ContentMismatch/None/None/hash", StringComparison.Ordinal)
                && !tampered.Output.Contains("RECOVERY-START OK", StringComparison.Ordinal)
                && !tampered.Output.Contains("RECOVERY-CALL source=", StringComparison.Ordinal)
                && !File.Exists(marker)
                && Same(receiptBytes, receipt)
                && Hash(privateFile) == privateHash, "tampered-additional");

            Console.WriteLine("shape=standalone-il additional=file-verification-not-dependency-execution");
            Console.WriteLine("evidence=desktop-il-not-ios-native-r2r");
            Console.WriteLine(failed == 0 ? "RECOVERY-SELF-TEST passed" : "RECOVERY-SELF-TEST failed=" + failed);
            return failed == 0 ? 0 : 1;
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    static int Recovered(string marker, string receipt, byte[] receiptBytes, string releases, string spkiFile, string contentRoot, string signedFile, string candidate, string name)
    {
        Delete(marker);
        var run = Run(marker, "--recoverable-start", releases, receipt, spkiFile, contentRoot, signedFile);
        return Check(run.ExitCode == 0
            && run.Output.Contains("RECOVERY-CALL source=LastKnownGood version=good-a additional=2 calls=1", StringComparison.Ordinal)
            && run.Output.Contains("RECOVERY-START OK source=LastKnownGood version=good-a value=130 additional=2 persistence=None", StringComparison.Ordinal)
            && run.Output.Contains(candidate, StringComparison.Ordinal)
            && !run.Output.Contains("source=Candidate", StringComparison.Ordinal)
            && Read(marker) == "130"
            && Same(receiptBytes, receipt), name);
    }

    static byte[]? SignForArchitecture(string contentRoot, TrustedUpdateTarget hostTarget, string version, string architecture, ECDsa key)
    {
        var identity = SignedStartupSample.Identity(hostTarget, version);
        var signed = TrustedRelease.Sign(
            contentRoot,
            new TrustedReleaseIdentity(identity.Version, identity.Runtime, architecture, identity.EntryType, identity.EntryMethod, identity.EntryPath),
            new[] { "TrustedUpdate.SampleCandidate.dll", "TrustedUpdate.Private.bin", "TrustedUpdate.Helper.bin" },
            key);
        return signed.Succeeded ? signed.Document : null;
    }

    static int Calls;
    static int Additional;

    static TrustedUpdateActivation Activate(TrustedUpdateCandidate chosen, TrustedUpdateStartSource source, TrustedUpdateFailure candidateFailure)
    {
        Calls++;
        Additional = chosen.AdditionalContent?.Count ?? 0;
        Console.WriteLine("RECOVERY-CALL source=" + source + " version=" + chosen.VersionName + " additional=" + Additional + " calls=" + Calls);
        return SignedStartupSample.ActivateLoaded(chosen, source, candidateFailure);
    }

    static string Format(TrustedReleaseRecoveryReason reason) =>
        reason.Verification + "/" + reason.Plan + "/" + reason.Activation + "/" + reason.Detail;

    static (int ExitCode, string Output) Run(string marker, params string[] args) =>
        RunWithMode(marker, null, args);

    static (int ExitCode, string Output) RunWithMode(string marker, string? childMode, params string[] args)
    {
        var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var arg in args)
            start.ArgumentList.Add(arg);
        start.Environment["TRUSTED_RELEASE_MARKER"] = marker;
        if (!string.IsNullOrEmpty(childMode))
            start.Environment["TRUSTED_RECOVERY_CHILD"] = childMode;
        using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
        var stdout = child.StandardOutput.ReadToEnd();
        var stderr = child.StandardError.ReadToEnd();
        child.WaitForExit();
        return (child.ExitCode, stdout + stderr);
    }

    static int Check(bool condition, string name)
    {
        Console.WriteLine((condition ? "PASS " : "FAIL ") + name);
        return condition ? 0 : 1;
    }

    static int Count(string text, string token)
    {
        var count = 0;
        var index = 0;
        while ((index = text.IndexOf(token, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += token.Length;
        }

        return count;
    }

    static string Read(string path) => File.Exists(path) ? File.ReadAllText(path) : "";

    static void Delete(string path)
    {
        if (File.Exists(path))
            File.Delete(path);
    }

    static bool Same(byte[] previous, string path) =>
        File.Exists(path) && previous.AsSpan().SequenceEqual(File.ReadAllBytes(path));

    static string Hash(string path) => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

    internal static string RealPath(string path)
    {
        var full = Path.GetFullPath(path);
        var root = Path.GetPathRoot(full);
        if (string.IsNullOrEmpty(root))
            return full;
        var current = ResolveLink(root) ?? root;
        foreach (var segment in full[root.Length..].Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            current = ResolveLink(current) ?? current;
        }

        return current;
    }

    static string? ResolveLink(string path, int depth = 0)
    {
        if (depth > 32 || (!Directory.Exists(path) && !File.Exists(path)))
            return null;
        FileSystemInfo info = Directory.Exists(path) ? new DirectoryInfo(path) : new FileInfo(path);
        var target = info.LinkTarget;
        if (string.IsNullOrEmpty(target))
            return Path.GetFullPath(path);
        var absolute = Path.IsPathRooted(target)
            ? target
            : Path.GetFullPath(Path.Combine(Path.GetDirectoryName(path) ?? path, target));
        return ResolveLink(absolute, depth + 1) ?? Path.GetFullPath(absolute);
    }

    static bool TryFileLink(string link, string target, out string skip)
    {
        skip = "";
        try
        {
            File.CreateSymbolicLink(link, target);
            if ((File.GetAttributes(link) & FileAttributes.ReparsePoint) == 0)
            {
                skip = "not-reparse";
                return false;
            }

            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or PlatformNotSupportedException or NotSupportedException)
        {
            skip = "unsupported";
            return false;
        }
    }
}
