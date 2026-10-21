using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.TrustedUpdate;

static class SelfTest
{
    const string EntryA = "TrustedComposition.Update.A.dll";
    const string EntryB = "TrustedComposition.Update.B.dll";
    const string PrivateName = "TrustedComposition.Private.dll";
    const string HelperName = "TrustedComposition.IlOnlyHelper.dll";
    static readonly JsonSerializerOptions FactsJson = new() { IncludeFields = true };

    public static int Run()
    {
        var deps = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "TrustedComposition.DeliveryHost.deps.json"));
        if (deps.Contains("TrustedComposition.Update", StringComparison.Ordinal) || deps.Contains("TrustedComposition.Private", StringComparison.Ordinal) || deps.Contains("TrustedComposition.IlOnlyHelper", StringComparison.Ordinal))
            return Fail("host deps include an update or private assembly");
        if (File.Exists(Path.Combine(AppContext.BaseDirectory, PrivateName)) || File.Exists(Path.Combine(AppContext.BaseDirectory, HelperName)))
            return Fail("private or helper dll was copied beside the host");

        var config = AppContext.BaseDirectory.Contains($"{Path.DirectorySeparatorChar}Release{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase) ? "Release" : "Debug";
        var fixture = FindFixture();
        var builtA = Locate(fixture, "A", config);
        var builtB = Locate(fixture, "B", config);
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var spki = key.ExportSubjectPublicKeyInfo();
        var failures = 0;
        var root = Path.Combine(Path.GetTempPath(), "trusted-delivery-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(root);
        try
        {
            var world = Prepare(root, "world-a", builtA, key, spki, includeHelper: true);
            failures += Check("stage A executes 101/310", RunChild(world, "stage"));
            var receipt = File.ReadAllBytes(world.Receipt);
            var hashes = HashTree(world.Final);
            failures += Check("next process restores A without staging", RunChild(world, "recover") && Same(world.Receipt, receipt) && SameTree(world.Final, hashes));
            failures += Check("bad signature restores A before activation", RunChild(world, "bad-signature"));
            failures += Check("tampered source private restores A before activation", RunChild(world, "tamper-source"));
            var inside = Path.Combine(world.Releases, "b-inside");
            Directory.CreateDirectory(inside);
            File.Copy(builtB.Entry, Path.Combine(inside, EntryB));
            File.Copy(builtB.Private, Path.Combine(inside, PrivateName));
            File.Copy(builtB.Helper, Path.Combine(inside, HelperName));
            File.WriteAllBytes(Path.Combine(inside, "sentinel.txt"), "source-b"u8.ToArray());
            File.WriteAllBytes(Path.Combine(world.Root, "inside.bin"), Sign(inside, "B", EntryB, key, null, true));
            failures += Check("existing final restores A and does not execute source B", RunChild(world, "destination-exists"));
            var failWorld = Prepare(root, "world-fail", builtA, key, spki, includeHelper: true);
            failures += Check("seed A before author failure", RunChild(failWorld, "stage"));
            var bSource = Path.Combine(failWorld.Root, "b-source");
            Directory.CreateDirectory(bSource);
            File.Copy(builtB.Entry, Path.Combine(bSource, EntryB));
            File.Copy(builtB.Private, Path.Combine(bSource, PrivateName));
            File.Copy(builtB.Helper, Path.Combine(bSource, HelperName));
            File.WriteAllBytes(Path.Combine(failWorld.Root, "b.bin"), Sign(bSource, "B", EntryB, key, null, true));
            var failReceipt = File.ReadAllBytes(failWorld.Receipt);
            failures += Check("author failure does not fall back or replace the receipt", RunChild(failWorld, "fail-b", builtB) && Same(failWorld.Receipt, failReceipt));
            failures += Check("next process restores A after the locked failure", RunChild(failWorld, "recover") && Same(failWorld.Receipt, failReceipt));
            var omit = Prepare(root, "world-omit", builtA, key, spki, includeHelper: false);
            failures += Check("unlisted helper on disk is not loaded", RunChild(omit, "omit-helper"));
            var independent = Prepare(root, "world-b", builtB, key, spki, includeHelper: true);
            failures += Check("independent stage B executes 202/613", RunChild(independent, "stage"));
            var duplicate = Prepare(root, "world-duplicate", builtA, key, spki, includeHelper: true);
            failures += Check("seed A before duplicate assembly names", RunChild(duplicate, "stage"));
            var collision = PrepareCollision(duplicate, builtA, builtB, key);
            var duplicateReceipt = File.ReadAllBytes(duplicate.Receipt);
            failures += Check("duplicate simple name does not load or replace the receipt", RunChild(collision, "duplicate-assembly") && Same(duplicate.Receipt, duplicateReceipt));
            var invalid = Prepare(root, "world-invalid", builtA, key, spki, includeHelper: true);
            failures += Check("seed A before invalid assembly identity", RunChild(invalid, "stage"));
            var invalidPackage = PrepareInvalid(invalid, builtA, key);
            var invalidReceipt = File.ReadAllBytes(invalid.Receipt);
            failures += Check("invalid assembly identity does not load or replace the receipt", RunChild(invalidPackage, "invalid-identity") && Same(invalid.Receipt, invalidReceipt));
            var caller = LocateCaller(config);
            var unlisted = PrepareCaller(root, caller, key, spki);
            failures += Check("unlisted TPA application dependency is not called", RunChild(unlisted, "unlisted-appdep"));
            var destroyed = CopyWorld(world, Path.Combine(root, "world-tamper"));
            var beforeTamper = File.ReadAllBytes(destroyed.Receipt); failures += Check("tampered final private is refused with no call", RunChild(destroyed, "tamper-final") && Same(destroyed.Receipt, beforeTamper));
            failures += Check("ancestor alias is the signed file and sibling prefix is not", PathAliasChecks());
            var typed = TypedSessionCompatibility();
            failures += Check("typed session constructor rejects null", typed.Constructor);
            failures += Check("typed session null callback returns invalid", typed.Invalid);
            failures += Check("typed session valid invocation after null", typed.Valid);
            if (typed.Constructor)
                Console.WriteLine("PASS typed session constructor rejects null");
            if (typed.Invalid)
                Console.WriteLine("PASS typed session null callback returns invalid");
            if (typed.Valid)
                Console.WriteLine("PASS typed session valid invocation after null");
        }
        finally
        {
            try { Directory.Delete(root, true); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }

        Console.WriteLine(failures == 0 ? "SELFTEST PASS" : "SELFTEST FAIL " + failures);
        return failures == 0 ? 0 : 1;
    }

    public static int Child(string[] args)
    {
        var mode = args[1];
        var request = Read(args[2]);
        var releases = request["releases"];
        var finalDir = request["final"];
        var document = request["document"];
        var spki = request["spki"];
        var receipt = request["receipt"];
        var source = request["source"];
        var files = request["files"].Split('|', StringSplitOptions.RemoveEmptyEntries).Select(pair =>
        {
            var split = pair.IndexOf('=');
            return (pair[..split], pair[(split + 1)..]);
        }).ToArray();
        DeliveryFacts facts;
        if (mode == "recover")
            facts = DeliverySession.RecoverOnly(releases, spki, receipt, false);
        else if (mode == "bad-signature")
        {
            var bad = FlipSignature(File.ReadAllBytes(document));
            var badPath = Path.Combine(source, "bad.bin");
            File.WriteAllBytes(badPath, bad);
            facts = DeliverySession.StageAsync(releases, Path.Combine(releases, "bad-final"), badPath, spki, receipt, files, false).GetAwaiter().GetResult();
        }
        else if (mode == "tamper-source")
        {
            var copy = Path.Combine(releases, "tampered-src");
            CopyDirectory(source, copy);
            var privateFile = Path.Combine(copy, PrivateName);
            var bytes = File.ReadAllBytes(privateFile);
            bytes[^1] ^= 0x5a;
            File.WriteAllBytes(privateFile, bytes);
            var stagedFiles = files.Select(file => (file.Item1, Path.Combine(copy, file.Item1))).ToArray();
            facts = DeliverySession.StageAsync(releases, Path.Combine(releases, "tampered-final"), document, spki, receipt, stagedFiles, false).GetAwaiter().GetResult();
        }
        else if (mode == "destination-exists")
        {
            var inside = Path.Combine(releases, "b-inside");
            var sentinelPath = Path.Combine(inside, "sentinel.txt");
            var sentinel = File.ReadAllBytes(sentinelPath);
            var beforeTree = HashTree(finalDir);
            var offerFiles = new (string Relative, string Absolute)[]
            {
                (EntryB, Path.Combine(inside, EntryB)),
                (PrivateName, Path.Combine(inside, PrivateName)),
                (HelperName, Path.Combine(inside, HelperName)),
            };
            facts = DeliverySession.StageAsync(releases, finalDir, request["documentInside"], spki, receipt, offerFiles, false).GetAwaiter().GetResult();
            var ok = facts.Activated
                && facts.Version == "A"
                && facts.Source == "LastKnownGood"
                && facts.PrivateValue == 101
                && facts.HelperValue == 310
                && facts.Calls == 1
                && DeliverySession.TotalActivations == 1
                && facts.Stage.StartsWith("DestinationExists/", StringComparison.Ordinal)
                && SameSignedFile(facts.LoadedEntry, finalDir, EntryA)
                && SameSignedFile(facts.LoadedPrivate, finalDir, PrivateName)
                && SameSignedFile(facts.LoadedHelper, finalDir, HelperName)
                && !InsideDirectory(inside, facts.LoadedEntry)
                && !InsideDirectory(inside, facts.LoadedPrivate)
                && !SameFile(facts.LoadedEntry, Path.Combine(inside, EntryB))
                && File.Exists(Path.Combine(inside, EntryB))
                && Same(sentinelPath, sentinel)
                && SameTree(finalDir, beforeTree)
                && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK destination-exists" : "BAD destination-exists");
            return ok ? 0 : 1;
        }
        else if (mode == "tamper-final")
        {
            var privateFile = Path.Combine(finalDir, PrivateName);
            var before = File.ReadAllBytes(receipt);
            var bytes = File.ReadAllBytes(privateFile);
            bytes[^1] ^= 0x5a;
            File.WriteAllBytes(privateFile, bytes);
            facts = DeliverySession.RecoverOnly(releases, spki, receipt, false);
            var after = File.ReadAllBytes(receipt);
            var ok = !facts.Activated && facts.Calls == 0 && facts.Recovery.StartsWith("ContentMismatch/", StringComparison.Ordinal) && before.AsSpan().SequenceEqual(after) && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine(ok ? "OK tamper-final" : "BAD tamper-final");
            return ok ? 0 : 1;
        }
        else if (mode == "omit-helper")
        {
            var docBytes = File.ReadAllBytes(document);
            var spkiBytes = File.ReadAllBytes(spki);
            var sources = files.Select(file => new TrustedReleaseStageSource(file.Item1, _ => new ValueTask<Stream>(File.OpenRead(file.Item2)))).ToArray();
            var staged = TrustedReleaseStaging.PublishAsync(finalDir, docBytes, spkiBytes, sources).GetAwaiter().GetResult();
            if (!staged.Succeeded || staged.FinalDirectory is null || !SameDirectory(staged.FinalDirectory, finalDir))
            {
                Console.WriteLine("BAD omit-helper stage " + staged.Failure + " " + staged.Detail);
                return 1;
            }

            if (File.Exists(Path.Combine(finalDir, HelperName)))
            {
                Console.WriteLine("BAD omit-helper helper was already published");
                return 1;
            }

            File.Copy(request["helper"], Path.Combine(finalDir, HelperName), true);
            facts = DeliverySession.ActivateStaged(releases, finalDir, document, spki, receipt, false);
            var locked = facts.Candidate.Contains("ProcessSelectionLocked", StringComparison.Ordinal)
                || facts.Recovery.Contains("ProcessSelectionLocked", StringComparison.Ordinal);
            var ok = !facts.Activated
                && facts.Calls == 1
                && DeliverySession.TotalActivations == 1
                && !facts.HelperLoaded
                && facts.ListedHelper.Length == 0
                && facts.Detail == "helper-not-listed"
                && facts.LoadedPrivate.Length > 0
                && facts.LoadedHelper.Length == 0
                && facts.Candidate == "None/None/ActivationFailed/activation"
                && facts.Recovery == "None/None/None/"
                && !locked
                && File.Exists(Path.Combine(finalDir, HelperName))
                && !HelperInProcess()
                && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK omit-helper" : "BAD omit-helper");
            return ok ? 0 : 1;
        }
        else if (mode == "fail-b")
        {
            var offerDir = Path.Combine(Path.GetDirectoryName(releases)!, "b-source");
            var offerFiles = new (string Relative, string Absolute)[]
            {
                (EntryB, Path.Combine(offerDir, EntryB)),
                (PrivateName, Path.Combine(offerDir, PrivateName)),
                (HelperName, Path.Combine(offerDir, HelperName)),
            };
            var before = File.ReadAllBytes(receipt);
            facts = DeliverySession.StageAsync(releases, Path.Combine(releases, "b"), request["documentB"], spki, receipt, offerFiles, true).GetAwaiter().GetResult();
            var after = File.ReadAllBytes(receipt);
            var second = DeliverySession.RecoverOnly(releases, spki, receipt, false);
            var ok = !facts.Activated
                && facts.Detail == "author-failed"
                && facts.HelperLoaded
                && facts.Calls == 1
                && before.AsSpan().SequenceEqual(after)
                && !second.Activated
                && second.Calls == 0
                && DeliverySession.TotalActivations == 1
                && second.Recovery == "None/ProcessSelectionLocked/None/locked"
                && FactsRoundTrip(facts)
                && FactsRoundTrip(second);
            Cli.Print(facts);
            Console.WriteLine("SECOND " + second.Recovery + " calls=" + second.Calls);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK fail-b" : "BAD fail-b");
            return ok ? 0 : 1;
        }
                else if (mode == "duplicate-assembly")
        {
            var before = File.ReadAllBytes(receipt);
            facts = DeliverySession.StageAsync(releases, finalDir, document, spki, receipt, files, false).GetAwaiter().GetResult();
            var after = File.ReadAllBytes(receipt);
            var loadedAuthor = AppDomain.CurrentDomain.GetAssemblies().Any(assembly => assembly.GetName().Name == "TrustedComposition.Update.A");
            var second = DeliverySession.RecoverOnly(releases, spki, receipt, false);
            var ok = !facts.Activated
                && facts.Detail == "duplicate-assembly"
                && facts.Calls == 1
                && facts.LoadedEntry.Length == 0
                && facts.Source == "Candidate"
                && facts.PrivateValue == 0
                && !loadedAuthor
                && facts.Candidate == "None/None/ActivationFailed/activation"
                && facts.Recovery == "None/None/None/"
                && before.AsSpan().SequenceEqual(after)
                && !second.Activated
                && second.Calls == 0
                && second.Recovery == "None/ProcessSelectionLocked/None/locked"
                && DeliverySession.TotalActivations == 1
                && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine("SECOND " + second.Recovery + " calls=" + second.Calls);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK duplicate-assembly" : "BAD duplicate-assembly");
            return ok ? 0 : 1;
        }
        else if (mode == "invalid-identity")
        {
            var before = File.ReadAllBytes(receipt);
            facts = DeliverySession.StageAsync(releases, finalDir, document, spki, receipt, files, false).GetAwaiter().GetResult();
            var after = File.ReadAllBytes(receipt);
            var loadedAuthor = AppDomain.CurrentDomain.GetAssemblies().Any(assembly => assembly.GetName().Name == "TrustedComposition.Update.A");
            var second = DeliverySession.RecoverOnly(releases, spki, receipt, false);
            var ok = !facts.Activated
                && facts.Detail == "assembly-identity"
                && facts.Calls == 1
                && facts.LoadedEntry.Length == 0
                && facts.Source == "Candidate"
                && facts.PrivateValue == 0
                && !loadedAuthor
                && facts.Candidate == "None/None/ActivationFailed/activation"
                && before.AsSpan().SequenceEqual(after)
                && !second.Activated
                && second.Calls == 0
                && second.Recovery == "None/ProcessSelectionLocked/None/locked"
                && DeliverySession.TotalActivations == 1
                && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK invalid-identity" : "BAD invalid-identity");
            return ok ? 0 : 1;
        }
        else if (mode == "unlisted-appdep")
        {
            var sentinel = request["sentinel"];
            if (File.Exists(sentinel))
                File.Delete(sentinel);
            Environment.SetEnvironmentVariable("DELIVERY_APPDEP_SENTINEL", sentinel);
            var tpa = AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") as string ?? "";
            var listedInTpa = tpa.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries)
                .Any(path => SameFile(path, Path.Combine(AppContext.BaseDirectory, "DeliveryAppDep.dll")));
            facts = DeliverySession.StageAsync(releases, finalDir, document, spki, receipt, files, false).GetAwaiter().GetResult();
            var loadedDep = AppDomain.CurrentDomain.GetAssemblies().Any(assembly => assembly.GetName().Name == "DeliveryAppDep");
            var ok = listedInTpa
                && !facts.Activated
                && facts.Detail == "unlisted-assembly"
                && facts.Calls == 1
                && facts.PrivateValue == 0
                && facts.Source == "Candidate"
                && DeliverySession.TotalActivations == 1
                && !loadedDep
                && !File.Exists(sentinel)
                && !File.Exists(receipt)
                && FactsRoundTrip(facts);
            Cli.Print(facts);
            Console.WriteLine("TPA " + listedInTpa);
            Console.WriteLine("LOADED_DEP " + loadedDep);
            Console.WriteLine("TOTAL " + DeliverySession.TotalActivations);
            Console.WriteLine(ok ? "OK unlisted-appdep" : "BAD unlisted-appdep");
            return ok ? 0 : 1;
        }
        else
            facts = DeliverySession.StageAsync(releases, finalDir, document, spki, receipt, files, false).GetAwaiter().GetResult();

        Cli.Print(facts);
        var passed = FactsRoundTrip(facts) && mode switch
        {
            "stage" when request["version"] == "A" => Executed(facts, "A", 101, 310, "1.0.0.0", "Candidate", finalDir),
            "stage" when request["version"] == "B" => Executed(facts, "B", 202, 613, "2.0.0.0", "Candidate", finalDir),
            "recover" => Executed(facts, "A", 101, 310, "1.0.0.0", "LastKnownGood", finalDir) && facts.Stage.Length == 0,
            "bad-signature" => facts.Activated && facts.Source == "LastKnownGood" && facts.PrivateValue == 101 && facts.HelperValue == 310 && facts.Calls == 1 && facts.Stage.Contains("VerificationFailed", StringComparison.Ordinal) && SameSignedFile(facts.LoadedEntry, finalDir, EntryA),
            "tamper-source" => facts.Activated && facts.Source == "LastKnownGood" && facts.PrivateValue == 101 && facts.HelperValue == 310 && facts.Calls == 1 && facts.Stage.Contains("VerificationFailed", StringComparison.Ordinal) && SameSignedFile(facts.LoadedEntry, finalDir, EntryA) && !InsideDirectory(Path.Combine(releases, "tampered-src"), facts.LoadedEntry),
            _ => false,
        };
        Console.WriteLine(passed ? "OK " + mode : "BAD " + mode);
        return passed ? 0 : 1;
    }

    static bool Executed(DeliveryFacts facts, string version, int privateValue, int helper, string privateVersion, string source, string finalDir)
    {
        var entryName = version == "A" ? EntryA : EntryB;
        return facts.Activated
            && facts.Version == version
            && facts.Source == source
            && facts.PrivateValue == privateValue
            && facts.HelperValue == helper
            && facts.PrivateVersion == privateVersion
            && facts.Identity
            && facts.TouchValue == privateValue + 11
            && facts.InterfaceValue == facts.StaticCount + 19
            && facts.DelegateValue == facts.StaticCount + 19
            && facts.GenericValue == helper
            && facts.Calls == 1
            && facts.Detail == "executed"
            && SameSignedFile(facts.LoadedEntry, finalDir, entryName)
            && SameSignedFile(facts.LoadedPrivate, finalDir, PrivateName)
            && SameSignedFile(facts.LoadedHelper, finalDir, HelperName)
            && SameFile(facts.LoadedEntry, facts.Entry)
            && SameFile(facts.LoadedPrivate, facts.ListedPrivate)
            && SameFile(facts.LoadedHelper, facts.ListedHelper);
    }


    const int MaxPathHops = 32;

    static bool SameSignedFile(string loaded, string finalDirectory, string fileName) =>
        SameFile(loaded, Path.Combine(finalDirectory, fileName)) && InsideDirectory(finalDirectory, loaded);

    static bool SameDirectory(string left, string right) => SameFile(left, right);

    static bool SameFile(string left, string right) =>
        TryCanonicalize(left, out var leftPath) && TryCanonicalize(right, out var rightPath) && SameCanonical(leftPath, rightPath);

    static bool InsideDirectory(string root, string candidate) =>
        TryCanonicalize(root, out var rootPath) && TryCanonicalize(candidate, out var candidatePath) && IsStrictChild(rootPath, candidatePath);

    static bool SameCanonical(string left, string right)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return string.Equals(TrimPath(left), TrimPath(right), comparison);
    }

    static bool IsStrictChild(string root, string candidate)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var prefix = TrimPath(root) + Path.DirectorySeparatorChar;
        var full = TrimPath(candidate);
        return full.StartsWith(prefix, comparison);
    }

    static string TrimPath(string path)
    {
        var root = Path.GetPathRoot(path) ?? "";
        var trimmed = path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return trimmed.Length < root.Length ? root : trimmed;
    }

    static bool TryCanonicalize(string path, out string canonical)
    {
        canonical = "";
        if (string.IsNullOrWhiteSpace(path))
            return false;
        string full;
        try
        {
            full = Path.GetFullPath(path);
        }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or IOException)
        {
            return false;
        }

        var root = Path.GetPathRoot(full);
        if (string.IsNullOrEmpty(root))
            return false;
        var pending = Segments(full).ToList();
        var done = new List<string>();
        var hops = 0;
        var index = 0;
        while (index < pending.Count)
        {
            var next = Combine(root, done.Append(pending[index]));
            if (!TryInspect(next, out var reparse, out var missing))
                return false;
            if (missing)
            {
                done.AddRange(pending.Skip(index));
                break;
            }

            if (reparse)
            {
                if (++hops > MaxPathHops)
                    return false;
                FileSystemInfo? target;
                try
                {
                    target = File.ResolveLinkTarget(next, returnFinalTarget: false);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
                {
                    return false;
                }

                if (target is null)
                    return false;
                string targetFull;
                try
                {
                    targetFull = Path.GetFullPath(target.FullName);
                }
                catch (Exception ex) when (ex is ArgumentException or NotSupportedException or IOException)
                {
                    return false;
                }

                var targetRoot = Path.GetPathRoot(targetFull);
                if (string.IsNullOrEmpty(targetRoot))
                    return false;
                pending = Segments(targetFull).Concat(pending.Skip(index + 1)).ToList();
                root = targetRoot;
                done.Clear();
                index = 0;
                continue;
            }

            done.Add(pending[index]);
            index++;
        }

        canonical = Combine(root, done);
        return canonical.Length > 0;
    }

    static bool TryInspect(string path, out bool reparse, out bool missing)
    {
        reparse = false;
        missing = false;
        try
        {
            reparse = (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
            return true;
        }
        catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException)
        {
            missing = true;
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }

    static IEnumerable<string> Segments(string fullPath)
    {
        var root = Path.GetPathRoot(fullPath) ?? "";
        return fullPath.Length > root.Length
            ? fullPath[root.Length..].Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }, StringSplitOptions.RemoveEmptyEntries)
            : Array.Empty<string>();
    }

    static string Combine(string root, IEnumerable<string> segments)
    {
        var path = root;
        foreach (var segment in segments)
            path = Path.Combine(path, segment);
        return path;
    }

    static bool PathAliasChecks()
    {
        var root = Path.Combine(Path.GetTempPath(), "trusted-path-alias-" + Guid.NewGuid().ToString("n"));
        var physical = Path.Combine(root, "physical");
        var published = Path.Combine(physical, "published");
        var bridge = Path.Combine(root, "bridge");
        var alias = Path.Combine(root, "alias");
        try
        {
            Directory.CreateDirectory(published);
            var signed = Path.Combine(published, EntryA);
            File.WriteAllBytes(signed, new byte[] { 1, 2, 3 });
            var siblingRoot = Path.Combine(root, "physical-extra", "published");
            Directory.CreateDirectory(siblingRoot);
            var sibling = Path.Combine(siblingRoot, EntryA);
            File.WriteAllBytes(sibling, new byte[] { 9 });
            var prefixDir = Path.Combine(physical, "published-extra");
            Directory.CreateDirectory(prefixDir);
            var prefixFile = Path.Combine(prefixDir, EntryA);
            File.WriteAllBytes(prefixFile, new byte[] { 4 });
            if (!TryCreateAlias(bridge, root) || !TryCreateAlias(alias, Path.Combine(bridge, "physical")))
            {
                Console.Error.WriteLine("FAIL path alias was not created");
                return false;
            }

            var aliasFile = Path.Combine(alias, "published", EntryA);
            return SameSignedFile(aliasFile, published, EntryA)
                && SameFile(aliasFile, signed)
                && InsideDirectory(Path.Combine(alias, "published"), aliasFile)
                && !SameFile(aliasFile, sibling)
                && !InsideDirectory(published, sibling)
                && !InsideDirectory(Path.Combine(alias, "published"), prefixFile)
                && !SameSignedFile(prefixFile, published, EntryA);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            Console.Error.WriteLine("FAIL path alias " + ex.GetType().Name);
            return false;
        }
        finally
        {
            DeleteAlias(alias);
            DeleteAlias(bridge);
            try
            {
                if (Directory.Exists(root))
                    Directory.Delete(root, recursive: true);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    static bool TryCreateAlias(string link, string target)
    {
        if (OperatingSystem.IsWindows())
        {
            var start = new ProcessStartInfo("cmd.exe")
            {
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            start.ArgumentList.Add("/c");
            start.ArgumentList.Add("mklink");
            start.ArgumentList.Add("/J");
            start.ArgumentList.Add(link);
            start.ArgumentList.Add(target);
            using var process = Process.Start(start) ?? throw new InvalidOperationException("mklink");
            process.WaitForExit();
            return process.ExitCode == 0 && (File.GetAttributes(link) & FileAttributes.ReparsePoint) != 0;
        }

        Directory.CreateSymbolicLink(link, target);
        return (File.GetAttributes(link) & FileAttributes.ReparsePoint) != 0;
    }

    static void DeleteAlias(string path)
    {
        try
        {
            if (!Directory.Exists(path))
                return;
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                Directory.Delete(path, recursive: false);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
        }
    }

    static bool FactsRoundTrip(DeliveryFacts facts)
    {
        var json = JsonSerializer.Serialize(facts, FactsJson);
        var clone = JsonSerializer.Deserialize<DeliveryFacts>(json, FactsJson);
        return clone is not null
            && clone.Activated == facts.Activated
            && clone.Version == facts.Version
            && clone.Source == facts.Source
            && clone.PrivateValue == facts.PrivateValue
            && clone.HelperValue == facts.HelperValue
            && clone.Calls == facts.Calls
            && clone.Detail == facts.Detail
            && clone.HelperLoaded == facts.HelperLoaded;
    }

    static bool HelperInProcess() =>
        AppDomain.CurrentDomain.GetAssemblies().Any(assembly => assembly.GetName().Name == "TrustedComposition.IlOnlyHelper");

    static int Check(string name, bool passed)
    {
        Console.WriteLine((passed ? "PASS " : "FAIL ") + name);
        return passed ? 0 : 1;
    }

    static int Fail(string message)
    {
        Console.Error.WriteLine("FAIL " + message);
        return 1;
    }

    static bool RunChild(PackageWorld world, string mode, Outputs? builtB = null)
    {
        var request = Path.Combine(world.Root, mode + ".request");
        var lines = new List<string>
        {
            "releases=" + world.Releases,
            "final=" + world.Final,
            "document=" + world.Document,
            "spki=" + world.Spki,
            "receipt=" + world.Receipt,
            "source=" + world.Source,
            "version=" + world.Version,
            "helper=" + world.Helper,
            "documentB=" + Path.Combine(world.Root, "b.bin"),
            "documentInside=" + Path.Combine(world.Root, "inside.bin"),
            "sentinel=" + Path.Combine(world.Root, "appdep-sentinel.txt"),
            "files=" + string.Join('|', world.Files.Select(file => file.Relative + "=" + file.Absolute)),
            "built=" + (builtB is null ? "" : builtB.Entry + "|" + builtB.Private + "|" + builtB.Helper),
        };
        File.WriteAllLines(request, lines);
        var start = new ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = AppContext.BaseDirectory,
        };
        start.ArgumentList.Add("--child");
        start.ArgumentList.Add(mode);
        start.ArgumentList.Add(request);
        using var child = Process.Start(start) ?? throw new InvalidOperationException("child");
        var stdout = child.StandardOutput.ReadToEnd();
        var stderr = child.StandardError.ReadToEnd();
        child.WaitForExit();
        Console.WriteLine(stdout);
        if (child.ExitCode != 0)
            Console.Error.WriteLine(stderr);
        return child.ExitCode == 0 && stdout.Contains("OK " + mode, StringComparison.Ordinal);
    }

    static PackageWorld Prepare(string root, string name, Outputs built, ECDsa key, byte[] spki, bool includeHelper)
    {
        var worldRoot = Path.Combine(root, name);
        var releases = Path.Combine(worldRoot, "releases");
        var source = Path.Combine(releases, "src");
        var state = Path.Combine(worldRoot, "state");
        Directory.CreateDirectory(source);
        Directory.CreateDirectory(state);
        var entryName = built.Version == "A" ? EntryA : EntryB;
        File.Copy(built.Entry, Path.Combine(source, entryName));
        File.Copy(built.Private, Path.Combine(source, PrivateName));
        if (includeHelper)
            File.Copy(built.Helper, Path.Combine(source, HelperName));
        var files = new List<(string Relative, string Absolute)> { (entryName, Path.Combine(source, entryName)), (PrivateName, Path.Combine(source, PrivateName)) };
        if (includeHelper)
            files.Add((HelperName, Path.Combine(source, HelperName)));
        var document = Sign(source, built.Version, entryName, key, null, includeHelper);
        var documentPath = Path.Combine(worldRoot, "package.bin");
        var spkiPath = Path.Combine(worldRoot, "host.spki");
        File.WriteAllBytes(documentPath, document);
        File.WriteAllBytes(spkiPath, spki);
        return new PackageWorld(worldRoot, releases, Path.Combine(releases, "published"), documentPath, spkiPath, Path.Combine(state, "current.json"), source, built.Helper, built.Version, files);
    }

    static PackageWorld PrepareCollision(PackageWorld seeded, Outputs builtA, Outputs builtB, ECDsa key)
    {
        var source = Path.Combine(seeded.Root, "collision-src");
        Directory.CreateDirectory(Path.Combine(source, "extra"));
        File.Copy(builtA.Entry, Path.Combine(source, EntryA));
        File.Copy(builtA.Private, Path.Combine(source, PrivateName));
        File.Copy(builtB.Private, Path.Combine(source, "extra", PrivateName));
        var relative = new[] { EntryA, PrivateName, "extra/" + PrivateName };
        var document = SignFiles(source, "A", EntryA, relative, key);
        var documentPath = Path.Combine(seeded.Root, "collision.bin");
        File.WriteAllBytes(documentPath, document);
        return seeded with
        {
            Final = Path.Combine(seeded.Releases, "collision-final"),
            Document = documentPath,
            Source = source,
            Files = relative.Select(name => (name, Path.Combine(source, name.Replace('/', Path.DirectorySeparatorChar)))).ToList(),
        };
    }

    static PackageWorld PrepareInvalid(PackageWorld seeded, Outputs builtA, ECDsa key)
    {
        var source = Path.Combine(seeded.Root, "invalid-src");
        Directory.CreateDirectory(source);
        File.Copy(builtA.Entry, Path.Combine(source, EntryA));
        File.Copy(builtA.Private, Path.Combine(source, PrivateName));
        File.WriteAllText(Path.Combine(source, "readme.txt"), "not-an-assembly");
        var relative = new[] { EntryA, PrivateName, "readme.txt" };
        var document = SignFiles(source, "A", EntryA, relative, key);
        var documentPath = Path.Combine(seeded.Root, "invalid.bin");
        File.WriteAllBytes(documentPath, document);
        return seeded with
        {
            Final = Path.Combine(seeded.Releases, "invalid-final"),
            Document = documentPath,
            Source = source,
            Files = relative.Select(name => (name, Path.Combine(source, name))).ToList(),
        };
    }

    static PackageWorld PrepareCaller(string root, string callerDll, ECDsa key, byte[] spki)
    {
        var worldRoot = Path.Combine(root, "world-unlisted");
        var releases = Path.Combine(worldRoot, "releases");
        var source = Path.Combine(releases, "src");
        var state = Path.Combine(worldRoot, "state");
        Directory.CreateDirectory(source);
        Directory.CreateDirectory(state);
        const string entryName = "DeliveryUnlistedCaller.dll";
        File.Copy(callerDll, Path.Combine(source, entryName));
        var files = new List<(string Relative, string Absolute)> { (entryName, Path.Combine(source, entryName)) };
        var document = SignFiles(source, "U", entryName, new[] { entryName }, key);
        var documentPath = Path.Combine(worldRoot, "package.bin");
        var spkiPath = Path.Combine(worldRoot, "host.spki");
        File.WriteAllBytes(documentPath, document);
        File.WriteAllBytes(spkiPath, spki);
        return new PackageWorld(worldRoot, releases, Path.Combine(releases, "published"), documentPath, spkiPath, Path.Combine(state, "current.json"), source, "", "U", files);
    }

    static string LocateCaller(string config)
    {
        var path = Path.Combine(FindFixture(), "..", "trusted-composition-delivery", "Host", "UnlistedCaller", "bin", config, "net11.0", "DeliveryUnlistedCaller.dll");
        path = Path.GetFullPath(path);
        if (!File.Exists(path))
            throw new FileNotFoundException(path);
        return path;
    }

    static byte[] SignFiles(string contentRoot, string version, string entry, IReadOnlyList<string> relativeFiles, ECDsa key)
    {
        var signed = TrustedRelease.Sign(contentRoot, new TrustedReleaseIdentity(version, "net11.0", DeliverySession.Target.Architecture, "TrustedComposition.UpdateModule", "Execute", entry), relativeFiles, key);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("sign " + signed.Failure + " " + signed.Detail);
        return signed.Document;
    }

    static byte[] Sign(string contentRoot, string version, string entry, ECDsa? key, string? unused, bool includeHelper)
    {
        var files = new List<string> { entry, PrivateName };
        if (includeHelper)
            files.Add(HelperName);
        if (key is null)
            throw new InvalidOperationException("key");
        var signed = TrustedRelease.Sign(contentRoot, new TrustedReleaseIdentity(version, "net11.0", DeliverySession.Target.Architecture, "TrustedComposition.UpdateModule", "Execute", entry), files, key);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("sign " + signed.Failure + " " + signed.Detail);
        return signed.Document;
    }

    static byte[] FlipSignature(byte[] document)
    {
        var text = System.Text.Encoding.UTF8.GetString(document);
        var first = text.IndexOf('\n');
        var second = text.IndexOf('\n', first + 1);
        var signature = Convert.FromBase64String(text[(first + 1)..second]);
        signature[0] ^= 0x01;
        return System.Text.Encoding.UTF8.GetBytes("RTRSIG1\n" + Convert.ToBase64String(signature) + "\n" + text[(second + 1)..]);
    }

    static PackageWorld CopyWorld(PackageWorld world, string destination)
    {
        CopyDirectory(world.Root, destination);
        var source = Path.Combine(destination, "releases", "src");
        return world with
        {
            Root = destination,
            Releases = Path.Combine(destination, "releases"),
            Final = Path.Combine(destination, "releases", "published"),
            Document = Path.Combine(destination, "package.bin"),
            Spki = Path.Combine(destination, "host.spki"),
            Receipt = Path.Combine(destination, "state", "current.json"),
            Source = source,
            Files = world.Files.Select(file => (file.Relative, Path.Combine(source, file.Relative))).ToList(),
        };
    }

    static (bool Constructor, bool Invalid, bool Valid) TypedSessionCompatibility()
    {
        var constructorThrew = false;
        try
        {
            _ = new TypedSession<object>(null!);
        }
        catch (ArgumentNullException)
        {
            constructorThrew = true;
        }

        var session = new TypedSession<object>(new object());
        var invalid = session.Invoke(null!);
        var valid = session.Invoke(_ => 7);
        var validOk = valid.Completed && valid.Value == 7 && valid.Failure.Length == 0 && !session.IsClosed;
        session.Close();
        return (constructorThrew, !invalid.Completed && invalid.Value == 0 && invalid.Failure == "invalid", validOk);
    }

    static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(directory.Replace(source, destination));
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            File.Copy(file, file.Replace(source, destination), true);
    }

    static Dictionary<string, string> Read(string path) =>
        File.ReadAllLines(path).Select(line => line.Split('=', 2)).ToDictionary(pair => pair[0], pair => pair[1]);

    static string FindFixture()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "eng", "trusted-composition", "Update.A");
            if (Directory.Exists(candidate))
                return Path.Combine(dir.FullName, "eng", "trusted-composition");
            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("fixture");
    }

    static Outputs Locate(string fixture, string version, string config)
    {
        var entry = Path.Combine(fixture, "Update." + version, "bin", config, "net11.0", "TrustedComposition.Update." + version + ".dll");
        var privateDll = Path.Combine(fixture, "Private." + version, "bin", config, "net11.0", PrivateName);
        var helper = Path.Combine(fixture, "IlOnlyHelper", "bin", config, "net11.0", HelperName);
        if (!File.Exists(entry) || !File.Exists(privateDll) || !File.Exists(helper))
            throw new FileNotFoundException(entry);
        return new Outputs(version, entry, privateDll, helper);
    }

    static Dictionary<string, byte[]> HashTree(string root)
    {
        var map = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            map[Path.GetRelativePath(root, file)] = SHA256.HashData(File.ReadAllBytes(file));
        return map;
    }

    static bool SameTree(string root, Dictionary<string, byte[]> hashes)
    {
        var current = HashTree(root);
        return current.Count == hashes.Count && hashes.All(pair => current.TryGetValue(pair.Key, out var value) && value.AsSpan().SequenceEqual(pair.Value));
    }

    static bool Same(string path, byte[] bytes) => File.ReadAllBytes(path).AsSpan().SequenceEqual(bytes);

    sealed record Outputs(string Version, string Entry, string Private, string Helper);
    sealed record PackageWorld(string Root, string Releases, string Final, string Document, string Spki, string Receipt, string Source, string Helper, string Version, List<(string Relative, string Absolute)> Files);
}



