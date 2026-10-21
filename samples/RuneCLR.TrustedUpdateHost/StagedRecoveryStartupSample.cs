using System.Security.Cryptography;
using RuneCLR.TrustedUpdate;

static class StagedRecoveryStartupSample
{
    const string EntryFile = "TrustedUpdate.SampleCandidate.dll";
    const string PrivateFile = "TrustedUpdate.Private.bin";
    const string HelperFile = "TrustedUpdate.Helper.bin";
    const string DottedFile = "TrustedUpdate.Helper..bin";

    public static int Usage()
    {
        Console.WriteLine("STAGED-RECOVERY-USAGE --stage-recoverable-start <releases-root> <receipt-file> <host-spki-file> <source-content-root> <signed-release-file> <new-final-dir>");
        Console.WriteLine("STAGED-RECOVERY-USAGE --staged-recovery-self-test");
        return 1;
    }

    public static int Start(
        string releasesRoot,
        string receiptFile,
        string hostSpkiFile,
        string sourceRoot,
        string signedReleaseFile,
        string finalDirectory,
        TrustedUpdateTarget hostTarget)
    {
        try
        {
            releasesRoot = RecoveryStartupSample.RealPath(releasesRoot);
            receiptFile = Path.GetFullPath(receiptFile);
            sourceRoot = RecoveryStartupSample.RealPath(sourceRoot);
            finalDirectory = RecoveryStartupSample.RealPath(finalDirectory);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            Console.WriteLine("STAGED-RECOVERY REJECTED config=path");
            Console.WriteLine("STAGED-RECOVERY-CALLS " + Calls);
            return 2;
        }

        if (!SignedStartupSample.TryReadExact(hostSpkiFile, TrustedRelease.SpkiBytes, out var spki, out var keyDetail))
        {
            Console.WriteLine("STAGED-RECOVERY REJECTED config=spki " + keyDetail);
            Console.WriteLine("STAGED-RECOVERY-CALLS " + Calls);
            return 2;
        }

        if (!SignedStartupSample.TryReadBounded(signedReleaseFile, TrustedRelease.MaxDocumentBytes, out var document, out var readDetail))
        {
            Console.WriteLine("STAGED-RECOVERY SOURCE Read " + readDetail);
            return Recover(releasesRoot, receiptFile, spki, hostTarget);
        }

        var listed = TrustedRelease.Verify(sourceRoot, document, spki);
        if (!listed.Succeeded || listed.Candidate is null || listed.Approval is null)
        {
            Console.WriteLine("STAGED-RECOVERY SOURCE Verify " + listed.Failure + " " + listed.Detail);
            return Recover(releasesRoot, receiptFile, spki, hostTarget);
        }

        if (!TrySources(sourceRoot, listed.Candidate, out var sources))
        {
            Console.WriteLine("STAGED-RECOVERY SOURCE Verify InvalidPath source");
            return Recover(releasesRoot, receiptFile, spki, hostTarget);
        }

        var published = TrustedReleaseStaging.PublishAsync(finalDirectory, document, spki, sources).GetAwaiter().GetResult();
        if (!published.Succeeded || string.IsNullOrWhiteSpace(published.FinalDirectory))
        {
            var reason = published.Failure == TrustedReleaseStageFailure.VerificationFailed
                ? "Verify " + published.VerificationFailure + " " + published.Detail
                : "Stage " + published.Failure + " " + published.Detail;
            Console.WriteLine("STAGED-RECOVERY SOURCE " + reason);
            return Recover(releasesRoot, receiptFile, spki, hostTarget);
        }

        var offer = new TrustedReleaseOffer(published.FinalDirectory, document);
        return Report(TrustedReleaseRecovery.TryStart(offer, spki, hostTarget, releasesRoot, receiptFile, Activate));
    }

    public static int SelfTest(TrustedUpdateTarget hostTarget)
    {
        var root = RecoveryStartupSample.RealPath(Path.Combine(RecoveryStartupSample.RealPath(Path.GetTempPath()), "trusted-staged-recovery-" + Guid.NewGuid().ToString("n")));
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
            var goodRoot = Prepare(Path.Combine(root, "source-good"), throws: false);
            var signatureRoot = Prepare(Path.Combine(root, "source-sig"), throws: false);
            var tamperRoot = Prepare(Path.Combine(root, "source-tamper"), throws: false);
            var throwRoot = Prepare(Path.Combine(root, "source-throw"), throws: true);
            var goodDoc = Sign(goodRoot, hostTarget, "good-a", key);
            using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var badDoc = Sign(signatureRoot, hostTarget, "sig-b", other);
            var tamperDoc = Sign(tamperRoot, hostTarget, "tamper-b", key);
            var throwDoc = Sign(throwRoot, hostTarget, "throw-b", key);
            if (goodDoc is null || badDoc is null || tamperDoc is null || throwDoc is null)
            {
                Console.WriteLine("STAGED-RECOVERY-SELF-TEST failed=sign");
                return 1;
            }

            var privateFile = Path.Combine(tamperRoot, PrivateFile);
            var privateBytes = File.ReadAllBytes(privateFile);
            privateBytes[0] ^= 0x5A;
            File.WriteAllBytes(privateFile, privateBytes);
            var goodFile = Path.Combine(offers, "good.signed");
            var badFile = Path.Combine(offers, "bad.signed");
            var tamperFile = Path.Combine(offers, "tamper.signed");
            var throwFile = Path.Combine(offers, "throw.signed");
            File.WriteAllBytes(goodFile, goodDoc);
            File.WriteAllBytes(badFile, badDoc);
            File.WriteAllBytes(tamperFile, tamperDoc);
            File.WriteAllBytes(throwFile, throwDoc);
            var finalA = Path.Combine(releases, "final-a");
            var finalBad = Path.Combine(releases, "final-bad");
            var finalTamper = Path.Combine(releases, "final-tamper");
            var finalB = Path.Combine(releases, "final-b");
            var dotted = new byte[] { 9, 9, 9, 9 };
            var privateHash = Hash(Path.Combine(goodRoot, PrivateFile));
            var helperHash = Hash(Path.Combine(goodRoot, HelperFile));

            Delete(marker);
            var staged = Run(marker, "--stage-recoverable-start", releases, receipt, spkiFile, goodRoot, goodFile, finalA);
            failed += Check(staged.ExitCode == 0
                && staged.Output.Contains("STAGED-RECOVERY-CALL source=Candidate version=good-a additional=3 calls=1", StringComparison.Ordinal)
                && staged.Output.Contains("STAGED-RECOVERY OK source=Candidate version=good-a value=130 additional=3 persistence=None", StringComparison.Ordinal)
                && !staged.Output.Contains("source=LastKnownGood", StringComparison.Ordinal)
                && Read(marker) == "130"
                && File.Exists(receipt)
                && SameBytes(dotted, Path.Combine(finalA, DottedFile))
                && Hash(Path.Combine(finalA, PrivateFile)) == privateHash
                && Hash(Path.Combine(finalA, HelperFile)) == helperHash, "stage-a");
            var receiptBytes = File.ReadAllBytes(receipt);

            var receiptLink = Path.Combine(state, "receipt-link.bin");
            if (!TryFileLink(receiptLink, receipt, out var linkSkip))
            {
                if (linkSkip == "unsupported")
                    Console.WriteLine("SKIP receipt-leaf-link unsupported");
                else
                    failed += Check(false, "receipt-leaf-link");
            }
            else
            {
                Delete(marker);
                var linkedFinal = Path.Combine(releases, "final-leaf");
                var linkedStage = Run(marker, "--stage-recoverable-start", releases, receiptLink, spkiFile, goodRoot, goodFile, linkedFinal);
                failed += Check(linkedStage.ExitCode == 2
                    && linkedStage.Output.Contains("config=receipt-link", StringComparison.Ordinal)
                    && linkedStage.Output.Contains("STAGED-RECOVERY-CALLS 0", StringComparison.Ordinal)
                    && !linkedStage.Output.Contains("STAGED-RECOVERY-CALL source=", StringComparison.Ordinal)
                    && !linkedStage.Output.Contains("STAGED-RECOVERY OK", StringComparison.Ordinal)
                    && !File.Exists(marker)
                    && Same(receiptBytes, receipt), "receipt-leaf-link");
                Delete(marker);
                var linkedVerify = Run(marker, "--stage-recoverable-start", releases, receiptLink, spkiFile, signatureRoot, badFile, Path.Combine(releases, "final-leaf-verify"));
                failed += Check(linkedVerify.ExitCode == 2
                    && linkedVerify.Output.Contains("STAGED-RECOVERY SOURCE Verify InvalidSignature mismatch", StringComparison.Ordinal)
                    && linkedVerify.Output.Contains("config=receipt-link", StringComparison.Ordinal)
                    && linkedVerify.Output.Contains("STAGED-RECOVERY-CALLS 0", StringComparison.Ordinal)
                    && !linkedVerify.Output.Contains("STAGED-RECOVERY-CALL source=", StringComparison.Ordinal)
                    && !linkedVerify.Output.Contains("STAGED-RECOVERY OK", StringComparison.Ordinal)
                    && !File.Exists(marker)
                    && Same(receiptBytes, receipt), "receipt-leaf-link-after-verify");
            }
            var finalPrivate = Hash(Path.Combine(finalA, PrivateFile));
            var finalHelper = Hash(Path.Combine(finalA, HelperFile));

            Delete(marker);
            var recovered = Run(marker, "--recoverable-start", releases, receipt, spkiFile);
            failed += Check(recovered.ExitCode == 0
                && recovered.Output.Contains("RECOVERY-CALL source=LastKnownGood version=good-a additional=3 calls=1", StringComparison.Ordinal)
                && recovered.Output.Contains("RECOVERY-START OK source=LastKnownGood version=good-a value=130 additional=3 persistence=None", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt), "recover-a");

            failed += SourceRejects(marker, receipt, receiptBytes, releases, spkiFile, signatureRoot, badFile, finalBad, "STAGED-RECOVERY SOURCE Verify InvalidSignature mismatch", "wrong-key-recovers-a");
            failed += SourceRejects(marker, receipt, receiptBytes, releases, spkiFile, tamperRoot, tamperFile, finalTamper, "STAGED-RECOVERY SOURCE Verify ContentMismatch hash", "tampered-private-recovers-a");
            Delete(marker);
            var occupied = Run(marker, "--stage-recoverable-start", releases, receipt, spkiFile, goodRoot, goodFile, finalA);
            failed += Check(occupied.ExitCode == 0
                && occupied.Output.Contains("STAGED-RECOVERY SOURCE Stage DestinationExists final", StringComparison.Ordinal)
                && occupied.Output.Contains("STAGED-RECOVERY-CALL source=LastKnownGood version=good-a additional=3 calls=1", StringComparison.Ordinal)
                && occupied.Output.Contains("STAGED-RECOVERY OK source=LastKnownGood version=good-a value=130 additional=3 persistence=None", StringComparison.Ordinal)
                && !occupied.Output.Contains("source=Candidate", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt)
                && Hash(Path.Combine(finalA, PrivateFile)) == finalPrivate
                && Hash(Path.Combine(finalA, HelperFile)) == finalHelper
                && SameBytes(dotted, Path.Combine(finalA, DottedFile)), "existing-final-recovers-a");

            Delete(marker);
            var thrown = Run(marker, "--stage-recoverable-start", releases, receipt, spkiFile, throwRoot, throwFile, finalB);
            failed += Check(thrown.ExitCode == 3
                && Count(thrown.Output, "STAGED-RECOVERY-CALL source=") == 1
                && thrown.Output.Contains("STAGED-RECOVERY-CALL source=Candidate version=throw-b additional=3 calls=1", StringComparison.Ordinal)
                && thrown.Output.Contains("candidate=None/None/ActivationFailed/activation", StringComparison.Ordinal)
                && !thrown.Output.Contains("STAGED-RECOVERY OK", StringComparison.Ordinal)
                && !thrown.Output.Contains("source=LastKnownGood", StringComparison.Ordinal)
                && !thrown.Output.Contains("signed-activate-fault", StringComparison.Ordinal)
                && thrown.Output.Contains("STAGED-RECOVERY-CALLS 1", StringComparison.Ordinal)
                && !File.Exists(marker)
                && Directory.Exists(finalB)
                && File.Exists(Path.Combine(finalB, DottedFile))
                && Same(receiptBytes, receipt), "throw-no-fallback");

            Delete(marker);
            var afterThrow = Run(marker, "--recoverable-start", releases, receipt, spkiFile);
            failed += Check(afterThrow.ExitCode == 0
                && afterThrow.Output.Contains("RECOVERY-START OK source=LastKnownGood version=good-a value=130 additional=3 persistence=None", StringComparison.Ordinal)
                && Read(marker) == "130"
                && Same(receiptBytes, receipt)
                && Directory.Exists(finalA)
                && Directory.Exists(finalB), "recover-after-throw");

            Console.WriteLine("shape=local-file-stream standalone-il additional=file-verification-not-dependency-execution");
            Console.WriteLine("evidence=desktop-il-not-http-interpreter-ios-native-r2r");
            Console.WriteLine(failed == 0 ? "STAGED-RECOVERY-SELF-TEST passed" : "STAGED-RECOVERY-SELF-TEST failed=" + failed);
            return failed == 0 ? 0 : 1;
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    static int SourceRejects(string marker, string receipt, byte[] receiptBytes, string releases, string spkiFile, string sourceRoot, string signedFile, string finalDirectory, string sourceLine, string name)
    {
        Delete(marker);
        var run = Run(marker, "--stage-recoverable-start", releases, receipt, spkiFile, sourceRoot, signedFile, finalDirectory);
        return Check(run.ExitCode == 0
            && run.Output.Contains(sourceLine, StringComparison.Ordinal)
            && run.Output.Contains("STAGED-RECOVERY-CALL source=LastKnownGood version=good-a additional=3 calls=1", StringComparison.Ordinal)
            && run.Output.Contains("STAGED-RECOVERY OK source=LastKnownGood version=good-a value=130 additional=3 persistence=None", StringComparison.Ordinal)
            && !run.Output.Contains("source=Candidate", StringComparison.Ordinal)
            && !Directory.Exists(finalDirectory)
            && Read(marker) == "130"
            && Same(receiptBytes, receipt), name);
    }

    static int Recover(string releasesRoot, string receiptFile, byte[] spki, TrustedUpdateTarget hostTarget) =>
        Report(TrustedReleaseRecovery.TryStart(null, spki, hostTarget, releasesRoot, receiptFile, Activate));

    static int Report(TrustedReleaseRecoveryStart result)
    {
        if (result.Activated)
        {
            Console.WriteLine(
                "STAGED-RECOVERY OK source=" + result.Source
                + " version=" + result.SelectedVersion
                + " value=" + result.Value
                + " additional=" + Additional
                + " persistence=" + result.Persistence
                + (result.Persistence == TrustedReleasePersistenceFailure.None ? "" : " " + result.PersistenceDetail)
                + " candidate=" + Format(result.Candidate)
                + " recovery=" + Format(result.Recovery));
            Console.WriteLine("STAGED-RECOVERY-CALLS " + Calls);
            return 0;
        }

        var code = 2;
        if (result.Candidate.Activation != TrustedUpdateFailure.None || result.Recovery.Activation != TrustedUpdateFailure.None)
            code = 3;
        else if (result.Candidate.Plan != TrustedUpdateFailure.None || result.Recovery.Plan != TrustedUpdateFailure.None)
            code = 4;
        Console.WriteLine(
            "STAGED-RECOVERY REJECTED source=" + result.Source
            + " config=" + result.ConfigurationDetail
            + " candidate=" + Format(result.Candidate)
            + " recovery=" + Format(result.Recovery)
            + " persistence=" + result.Persistence);
        Console.WriteLine("STAGED-RECOVERY-CALLS " + Calls);
        return code;
    }

    static int Calls;
    static int Additional;

    static TrustedUpdateActivation Activate(TrustedUpdateCandidate chosen, TrustedUpdateStartSource source, TrustedUpdateFailure candidateFailure)
    {
        Calls++;
        Additional = chosen.AdditionalContent?.Count ?? 0;
        Console.WriteLine("STAGED-RECOVERY-CALL source=" + source + " version=" + chosen.VersionName + " additional=" + Additional + " calls=" + Calls);
        return SignedStartupSample.ActivateLoaded(chosen, source, candidateFailure);
    }

    static string Prepare(string contentRoot, bool throws)
    {
        Directory.CreateDirectory(contentRoot);
        SignedStartupSample.WritePackage(contentRoot, throws);
        File.WriteAllBytes(Path.Combine(contentRoot, DottedFile), new byte[] { 9, 9, 9, 9 });
        return contentRoot;
    }

    static byte[]? Sign(string contentRoot, TrustedUpdateTarget hostTarget, string version, ECDsa key)
    {
        var signed = TrustedRelease.Sign(
            contentRoot,
            SignedStartupSample.Identity(hostTarget, version),
            new[] { EntryFile, PrivateFile, HelperFile, DottedFile },
            key);
        return signed.Succeeded ? signed.Document : null;
    }

    static bool TrySources(string sourceRoot, TrustedUpdateCandidate candidate, out IReadOnlyList<TrustedReleaseStageSource> sources)
    {
        sources = Array.Empty<TrustedReleaseStageSource>();
        var relative = new List<string>();
        if (!TryRelative(sourceRoot, candidate.AssemblyPath, out var entry))
            return false;
        relative.Add(entry);
        if (candidate.AdditionalContent is not null)
        {
            foreach (var file in candidate.AdditionalContent)
            {
                if (!TryRelative(sourceRoot, file.Path, out var path))
                    return false;
                relative.Add(path);
            }
        }

        var opened = new TrustedReleaseStageSource[relative.Count];
        for (var i = 0; i < relative.Count; i++)
        {
            var name = relative[i];
            var full = Path.GetFullPath(Path.Combine(sourceRoot, name.Replace('/', Path.DirectorySeparatorChar)));
            opened[i] = new TrustedReleaseStageSource(name, _ => new ValueTask<Stream>(OpenRead(full)));
        }

        sources = opened;
        return true;
    }

    static Stream OpenRead(string path) =>
        new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);

    static bool TryRelative(string sourceRoot, string fullPath, out string relative)
    {
        relative = "";
        var root = Path.GetFullPath(sourceRoot);
        var full = Path.GetFullPath(fullPath);
        var compared = Path.GetRelativePath(root, full);
        if (compared == "."
            || compared == ".."
            || compared.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            || compared.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal)
            || Path.IsPathRooted(compared))
            return false;
        relative = compared.Replace(Path.DirectorySeparatorChar, '/').Replace(Path.AltDirectorySeparatorChar, '/');
        if (relative.Length == 0 || relative[0] == '/' || relative[relative.Length - 1] == '/')
            return false;
        foreach (var segment in relative.Split('/'))
        {
            if (segment.Length == 0 || segment == "." || segment == "..")
                return false;
        }

        return true;
    }

    static string Format(TrustedReleaseRecoveryReason reason) =>
        reason.Verification + "/" + reason.Plan + "/" + reason.Activation + "/" + reason.Detail;

    static (int ExitCode, string Output) Run(string marker, params string[] args)
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

    static bool SameBytes(byte[] expected, string path)
    {
        if (!File.Exists(path))
            return false;
        var actual = File.ReadAllBytes(path);
        return expected.AsSpan().SequenceEqual(actual);
    }

    static string Hash(string path) => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

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
