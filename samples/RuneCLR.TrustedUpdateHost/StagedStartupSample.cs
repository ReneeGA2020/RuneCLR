using System.Security.Cryptography;
using System.Text;
using RuneCLR.TrustedUpdate;

static class StagedStartupSample
{
    public static int Start(
        string sourceRoot,
        string signedReleaseFile,
        string hostSpkiFile,
        string finalDirectory,
        string lastKnownGoodFile,
        TrustedUpdateTarget hostTarget)
    {
        if (!SignedStartupSample.TryReadBounded(signedReleaseFile, TrustedRelease.MaxDocumentBytes, out var document, out var readDetail))
        {
            Console.WriteLine("STAGED-START REJECTED Verify InvalidDocument " + readDetail);
            return 2;
        }

        if (!SignedStartupSample.TryReadExact(hostSpkiFile, TrustedRelease.SpkiBytes, out var spki, out var keyDetail))
        {
            Console.WriteLine("STAGED-START REJECTED Verify UntrustedKey " + keyDetail);
            return 2;
        }

        var listed = TrustedRelease.Verify(sourceRoot, document, spki);
        if (!listed.Succeeded || listed.Candidate is null || listed.Approval is null)
        {
            Console.WriteLine("STAGED-START REJECTED Verify " + listed.Failure + " " + listed.Detail);
            return 2;
        }

        if (!TrySources(sourceRoot, listed.Candidate, out var sources))
        {
            Console.WriteLine("STAGED-START REJECTED Verify InvalidPath source");
            return 2;
        }

        var published = TrustedReleaseStaging.PublishAsync(finalDirectory, document, spki, sources).GetAwaiter().GetResult();
        if (!published.Succeeded || published.Candidate is null || published.Approval is null || string.IsNullOrWhiteSpace(published.FinalDirectory))
        {
            var reason = published.Failure == TrustedReleaseStageFailure.VerificationFailed
                ? "Verify " + published.VerificationFailure
                : "Stage " + published.Failure;
            Console.WriteLine("STAGED-START REJECTED " + reason);
            return published.Failure == TrustedReleaseStageFailure.VerificationFailed ? 2 : 4;
        }

        var additional = published.Candidate.AdditionalContent?.Count ?? 0;
        var started = new TrustedUpdateProcess().TryStartHostLoaded(
            published.Candidate,
            hostTarget,
            lastKnownGoodFile,
            published.Approval,
            published.FinalDirectory,
            null,
            null,
            published.Candidate.VersionName,
            SignedStartupSample.ActivateLoaded);
        if (!started.Succeeded)
        {
            Console.WriteLine("STAGED-START REJECTED Start " + started.Failure);
            return 3;
        }

        Console.WriteLine("STAGED-START OK version=" + started.SelectedVersionName + " value=" + started.Value + " additional=" + additional);
        return 0;
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

    public static int SelfTest(TrustedUpdateTarget hostTarget)
    {
        var root = Path.Combine(Path.GetTempPath(), "trusted-staged-start-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(root);
        var failed = 0;
        try
        {
            using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var spkiFile = Path.Combine(root, "host.spki");
            File.WriteAllBytes(spkiFile, key.ExportSubjectPublicKeyInfo());
            var goodRoot = Path.Combine(root, "good-source");
            var throwRoot = Path.Combine(root, "throw-source");
            Directory.CreateDirectory(goodRoot);
            Directory.CreateDirectory(throwRoot);
            SignedStartupSample.WritePackage(goodRoot, throws: false);
            SignedStartupSample.WritePackage(throwRoot, throws: true);
            var goodDoc = SignedStartupSample.SignPackage(goodRoot, SignedStartupSample.Identity(hostTarget, "good-1"), key);
            var throwDoc = SignedStartupSample.SignPackage(throwRoot, SignedStartupSample.Identity(hostTarget, "throw-1"), key);
            if (goodDoc is null || throwDoc is null)
            {
                Console.WriteLine("STAGED-SELF-TEST failed=sign");
                return 1;
            }

            var goodFile = Path.Combine(root, "good.signed");
            var throwFile = Path.Combine(root, "throw.signed");
            File.WriteAllBytes(goodFile, goodDoc);
            File.WriteAllBytes(throwFile, throwDoc);
            var lkg = Path.Combine(root, "last-known-good.json");
            var marker = Path.Combine(root, "marker.txt");
            var finalGood = Path.Combine(root, "final-good");
            var started = RunChild(goodRoot, goodFile, spkiFile, finalGood, lkg, marker);
            failed += Check(started.ExitCode == 0 && started.Output.Contains("STAGED-START OK version=good-1 value=130 additional=2", StringComparison.Ordinal) && ReadText(marker) == "130" && ReadText(lkg).Contains("good-1", StringComparison.Ordinal) && Directory.Exists(finalGood), "staged-start");
            var lkgBytes = File.ReadAllBytes(lkg);
            File.Delete(marker);
            using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var wrongSpki = Path.Combine(root, "wrong.spki");
            File.WriteAllBytes(wrongSpki, other.ExportSubjectPublicKeyInfo());
            var wrongFinal = Path.Combine(root, "final-wrong");
            var wrong = RunChild(goodRoot, goodFile, wrongSpki, wrongFinal, lkg, marker);
            failed += Check(Absent(wrong, "STAGED-START REJECTED Verify InvalidSignature", marker, lkgBytes, lkg, wrongFinal), "wrong-key");
            var tamperRoot = Path.Combine(root, "tamper-source");
            CopyDirectory(goodRoot, tamperRoot);
            var privatePath = Path.Combine(tamperRoot, "TrustedUpdate.Private.bin");
            var privateBytes = File.ReadAllBytes(privatePath);
            privateBytes[0] = (byte)(privateBytes[0] ^ 0x5A);
            File.WriteAllBytes(privatePath, privateBytes);
            var tamperFinal = Path.Combine(root, "final-tamper");
            var tampered = RunChild(tamperRoot, goodFile, spkiFile, tamperFinal, lkg, marker);
            failed += Check(Absent(tampered, "STAGED-START REJECTED Verify ContentMismatch", marker, lkgBytes, lkg, tamperFinal), "private-tamper");
            var occupied = Path.Combine(root, "final-occupied");
            Directory.CreateDirectory(occupied);
            File.WriteAllText(Path.Combine(occupied, "sentinel.txt"), "keep");
            var occupiedRun = RunChild(goodRoot, goodFile, spkiFile, occupied, lkg, marker);
            failed += Check(occupiedRun.ExitCode != 0 && occupiedRun.Output.Contains("STAGED-START REJECTED Stage DestinationExists", StringComparison.Ordinal) && ReadText(Path.Combine(occupied, "sentinel.txt")) == "keep" && !File.Exists(marker) && SameBytes(lkgBytes, File.ReadAllBytes(lkg)), "existing-final");
            var throwFinal = Path.Combine(root, "final-throw");
            var thrown = RunChild(throwRoot, throwFile, spkiFile, throwFinal, lkg, marker);
            failed += Check(thrown.ExitCode != 0 && thrown.Output.Contains("STAGED-START REJECTED Start ActivationFailed", StringComparison.Ordinal) && !thrown.Output.Contains("STAGED-START OK", StringComparison.Ordinal) && !thrown.Output.Contains("signed-activate-fault", StringComparison.Ordinal) && !File.Exists(marker) && SameBytes(lkgBytes, File.ReadAllBytes(lkg)) && !ReadText(lkg).Contains("throw-1", StringComparison.Ordinal), "throwing-activate");
            var recoverFinal = Path.Combine(root, "final-recover");
            var recovered = RunChild(goodRoot, goodFile, spkiFile, recoverFinal, lkg, marker);
            failed += Check(recovered.ExitCode == 0 && recovered.Output.Contains("STAGED-START OK version=good-1 value=130 additional=2", StringComparison.Ordinal) && ReadText(marker) == "130" && ReadText(lkg).Contains("good-1", StringComparison.Ordinal) && !ReadText(lkg).Contains("throw-1", StringComparison.Ordinal) && Directory.Exists(recoverFinal), "recover-next-process");
            failed += DottedHelper(root, hostTarget, key, spkiFile);
            Console.WriteLine("shape=local-file-stream standalone-il additional=file-verification-not-dependency-execution");
            Console.WriteLine("evidence=desktop-il-not-ios-native-r2r");
            Console.WriteLine(failed == 0 ? "STAGED-SELF-TEST passed" : "STAGED-SELF-TEST failed=" + failed);
            return failed == 0 ? 0 : 1;
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    static int Check(bool condition, string name)
    {
        Console.WriteLine((condition ? "PASS " : "FAIL ") + name);
        return condition ? 0 : 1;
    }

    static bool Absent((int ExitCode, string Output) child, string expected, string marker, byte[] previousLkg, string lkg, string finalDirectory) =>
        child.ExitCode != 0 && child.Output.Contains(expected, StringComparison.Ordinal) && !File.Exists(marker) && SameBytes(previousLkg, File.ReadAllBytes(lkg)) && !Exists(finalDirectory);

    static bool Exists(string path) => File.Exists(path) || Directory.Exists(path);

    static string ReadText(string path) => File.Exists(path) ? File.ReadAllText(path) : "";

    static bool SameBytes(byte[] left, byte[] right)
    {
        if (left.Length != right.Length)
            return false;
        for (var i = 0; i < left.Length; i++)
        {
            if (left[i] != right[i])
                return false;
        }

        return true;
    }

    static (int ExitCode, string Output) RunChild(string sourceRoot, string signedFile, string spkiFile, string finalDirectory, string lkg, string marker)
    {
        var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add("--stage-signed-start");
        start.ArgumentList.Add(sourceRoot);
        start.ArgumentList.Add(signedFile);
        start.ArgumentList.Add(spkiFile);
        start.ArgumentList.Add(finalDirectory);
        start.ArgumentList.Add(lkg);
        start.Environment["TRUSTED_RELEASE_MARKER"] = marker;
        using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
        var stdout = child.StandardOutput.ReadToEnd();
        var stderr = child.StandardError.ReadToEnd();
        child.WaitForExit();
        return (child.ExitCode, stdout + stderr);
    }

    static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.GetFiles(source))
            File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), overwrite: true);
    }

    static int DottedHelper(string root, TrustedUpdateTarget hostTarget, ECDsa key, string spkiFile)
    {
        var source = Path.Combine(root, "dotted-source");
        Directory.CreateDirectory(source);
        var entry = "TrustedUpdate.SampleCandidate.dll";
        var helper = "TrustedUpdate.Helper..bin";
        SignedStartupSample.WriteAssembly(Path.Combine(source, entry), throws: false);
        File.WriteAllBytes(Path.Combine(source, "TrustedUpdate.Private.bin"), new byte[] { 1, 2, 3, 4 });
        File.WriteAllBytes(Path.Combine(source, helper), new byte[] { 9, 9, 9, 9 });
        var signed = TrustedRelease.Sign(source, SignedStartupSample.Identity(hostTarget, "dot-1"), new[] { entry, "TrustedUpdate.Private.bin", helper }, key);
        if (!signed.Succeeded || signed.Document is null)
            return Check(false, "dotted-helper sign " + signed.Failure + " " + signed.Detail);
        var signedFile = Path.Combine(root, "dotted.signed");
        File.WriteAllBytes(signedFile, signed.Document);
        var finalDirectory = Path.Combine(root, "final-dotted");
        var lkg = Path.Combine(root, "dotted-lkg.json");
        var marker = Path.Combine(root, "dotted-marker.txt");
        var started = RunChild(source, signedFile, spkiFile, finalDirectory, lkg, marker);
        var helperLanded = File.Exists(Path.Combine(finalDirectory, helper));
        return Check(started.ExitCode == 0 && started.Output.Contains("STAGED-START OK version=dot-1 value=130 additional=2", StringComparison.Ordinal) && ReadText(marker) == "130" && helperLanded && ReadText(lkg).Contains("dot-1", StringComparison.Ordinal), "dotted-helper");
    }
}
