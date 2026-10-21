using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using RuneCLR.TrustedUpdate;

static class SignedStartupSample
{
    const string MarkerVariable = "TRUSTED_RELEASE_MARKER";
    const string EntryTypeName = "TrustedUpdate.SampleCandidate.Entry";
    const string EntryMethodName = "Activate";
    const string EntryFileName = "TrustedUpdate.SampleCandidate.dll";
    const string PrivateFileName = "TrustedUpdate.Private.bin";
    const string HelperFileName = "TrustedUpdate.Helper.bin";
    const int ComputedValue = 130;

    public static int Start(string contentRoot, string signedReleaseFile, string hostSpkiFile, string lastKnownGoodFile, TrustedUpdateTarget hostTarget)
    {
        if (!TryReadBounded(signedReleaseFile, TrustedRelease.MaxDocumentBytes, out var document, out var readDetail))
        {
            Console.WriteLine("SIGNED-START REJECTED Verify InvalidDocument " + readDetail);
            return 2;
        }

        if (!TryReadExact(hostSpkiFile, TrustedRelease.SpkiBytes, out var spki, out var keyDetail))
        {
            Console.WriteLine("SIGNED-START REJECTED Verify UntrustedKey " + keyDetail);
            return 2;
        }

        var verified = TrustedRelease.Verify(contentRoot, document, spki);
        if (!verified.Succeeded || verified.Candidate is null || verified.Approval is null)
        {
            Console.WriteLine("SIGNED-START REJECTED Verify " + verified.Failure + " " + verified.Detail);
            return 2;
        }

        var additional = verified.Candidate.AdditionalContent?.Count ?? 0;
        var started = new TrustedUpdateProcess().TryStartHostLoaded(
            verified.Candidate,
            hostTarget,
            lastKnownGoodFile,
            verified.Approval,
            contentRoot,
            null,
            null,
            verified.Candidate.VersionName,
            ActivateLoaded);
        if (!started.Succeeded)
        {
            Console.WriteLine("SIGNED-START REJECTED Start " + started.Failure);
            return 3;
        }

        Console.WriteLine("SIGNED-START OK version=" + started.SelectedVersionName + " value=" + started.Value + " additional=" + additional);
        return 0;
    }

    internal static TrustedUpdateActivation ActivateLoaded(TrustedUpdateCandidate chosen, TrustedUpdateStartSource source, TrustedUpdateFailure candidateFailure)
    {
        if (source != TrustedUpdateStartSource.Candidate && source != TrustedUpdateStartSource.LastKnownGood)
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        try
        {
            var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(chosen.AssemblyPath));
            var type = assembly.GetType(chosen.EntryTypeName, throwOnError: true, ignoreCase: false);
            var method = type?.GetMethod(chosen.EntryMethodName, BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly, binder: null, Type.EmptyTypes, modifiers: null);
            if (method is null || method.ReturnType != typeof(int) || method.GetParameters().Length != 0)
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            var returned = method.Invoke(null, null);
            if (returned is not int value)
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, value);
        }
        catch (Exception)
        {
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    internal static bool TryReadBounded(string path, int maxBytes, out byte[] bytes, out string detail)
    {
        bytes = Array.Empty<byte>();
        if (maxBytes < 0 || maxBytes == int.MaxValue)
        {
            detail = "size";
            return false;
        }

        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            var limit = maxBytes + 1;
            var buffer = new byte[limit];
            var read = 0;
            while (read < limit)
            {
                var count = stream.Read(buffer, read, limit - read);
                if (count == 0)
                    break;
                read += count;
            }

            if (read == 0 || read > maxBytes)
            {
                detail = "size";
                return false;
            }

            bytes = new byte[read];
            Buffer.BlockCopy(buffer, 0, bytes, 0, read);
            detail = "";
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            bytes = Array.Empty<byte>();
            detail = "io";
            return false;
        }
    }
    internal static bool TryReadExact(string path, int exactBytes, out byte[] bytes, out string detail)
    {
        if (!TryReadBounded(path, exactBytes, out bytes, out detail))
            return false;
        if (bytes.Length != exactBytes)
        {
            bytes = Array.Empty<byte>();
            detail = "size";
            return false;
        }

        detail = "";
        return true;
    }

    public static int SelfTest(TrustedUpdateTarget hostTarget)
    {
        var root = Path.Combine(Path.GetTempPath(), "trusted-signed-start-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(root);
        var failed = 0;
        try
        {
            using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var spkiFile = Path.Combine(root, "host.spki");
            File.WriteAllBytes(spkiFile, key.ExportSubjectPublicKeyInfo());
            var goodRoot = Path.Combine(root, "good");
            var throwRoot = Path.Combine(root, "throw");
            Directory.CreateDirectory(goodRoot);
            Directory.CreateDirectory(throwRoot);
            WritePackage(goodRoot, throws: false);
            WritePackage(throwRoot, throws: true);
            var goodDoc = SignPackage(goodRoot, Identity(hostTarget, "good-1"), key);
            var throwDoc = SignPackage(throwRoot, Identity(hostTarget, "throw-1"), key);
            if (goodDoc is null || throwDoc is null)
            {
                Console.WriteLine("SIGNED-SELF-TEST failed=sign");
                return 1;
            }
            var goodFile = Path.Combine(root, "good.signed");
            var throwFile = Path.Combine(root, "throw.signed");
            File.WriteAllBytes(goodFile, goodDoc);
            File.WriteAllBytes(throwFile, throwDoc);
            var lkg = Path.Combine(root, "last-known-good.json");
            var marker = Path.Combine(root, "marker.txt");
            var ok = RunChild(goodRoot, goodFile, spkiFile, lkg, marker);
            failed += Check(Passed(ok, "SIGNED-START OK version=good-1 value=130 additional=2", marker, "130", lkg, "good-1"), "signed-start");
            var lkgBytes = File.ReadAllBytes(lkg);
            File.Delete(marker);
            var hugeRelease = Path.Combine(root, "huge.signed");
            File.WriteAllBytes(hugeRelease, new byte[TrustedRelease.MaxDocumentBytes + 1]);
            var huge = RunChild(goodRoot, hugeRelease, spkiFile, lkg, marker);
            failed += Check(Rejected(huge, "SIGNED-START REJECTED Verify InvalidDocument size", marker, lkgBytes, lkg), "oversized-document");
            var hugeSpki = Path.Combine(root, "huge.spki");
            File.WriteAllBytes(hugeSpki, new byte[TrustedRelease.SpkiBytes + 1]);
            var hugeKey = RunChild(goodRoot, goodFile, hugeSpki, lkg, marker);
            failed += Check(Rejected(hugeKey, "SIGNED-START REJECTED Verify UntrustedKey size", marker, lkgBytes, lkg), "oversized-spki");
            using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var wrongSpki = Path.Combine(root, "wrong.spki");
            File.WriteAllBytes(wrongSpki, other.ExportSubjectPublicKeyInfo());
            var wrong = RunChild(goodRoot, goodFile, wrongSpki, lkg, marker);
            failed += Check(Rejected(wrong, "SIGNED-START REJECTED Verify InvalidSignature", marker, lkgBytes, lkg), "wrong-key");
            var tamperRoot = Path.Combine(root, "tamper");
            CopyDirectory(goodRoot, tamperRoot);
            var privatePath = Path.Combine(tamperRoot, PrivateFileName);
            var privateBytes = File.ReadAllBytes(privatePath);
            privateBytes[0] = (byte)(privateBytes[0] ^ 0x5A);
            File.WriteAllBytes(privatePath, privateBytes);
            var tampered = RunChild(tamperRoot, goodFile, spkiFile, lkg, marker);
            failed += Check(Rejected(tampered, "SIGNED-START REJECTED Verify ContentMismatch", marker, lkgBytes, lkg), "private-tamper");
            var metaFile = Path.Combine(root, "meta.signed");
            var metaText = Encoding.UTF8.GetString(goodDoc).Replace("good-1", "good-9", StringComparison.Ordinal);
            File.WriteAllBytes(metaFile, Encoding.UTF8.GetBytes(metaText));
            var meta = RunChild(goodRoot, metaFile, spkiFile, lkg, marker);
            failed += Check(Rejected(meta, "SIGNED-START REJECTED Verify InvalidSignature", marker, lkgBytes, lkg), "metadata-tamper");
            var thrown = RunChild(throwRoot, throwFile, spkiFile, lkg, marker);
            failed += Check(Rejected(thrown, "SIGNED-START REJECTED Start ActivationFailed", marker, lkgBytes, lkg) && !thrown.Output.Contains("signed-activate-fault", StringComparison.Ordinal) && !ReadText(lkg).Contains("throw-1", StringComparison.Ordinal), "throwing-activate");
            var recovered = RunChild(goodRoot, goodFile, spkiFile, lkg, marker);
            failed += Check(Passed(recovered, "SIGNED-START OK version=good-1 value=130 additional=2", marker, "130", lkg, "good-1") && !ReadText(lkg).Contains("throw-1", StringComparison.Ordinal), "recover-next-process");
            Console.WriteLine("shape=standalone-il additional=file-verification-not-dependency-execution");
            Console.WriteLine(failed == 0 ? "SIGNED-SELF-TEST passed" : "SIGNED-SELF-TEST failed=" + failed);
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

    static bool Passed((int ExitCode, string Output) child, string expected, string marker, string markerText, string lkg, string version) =>
        child.ExitCode == 0 && child.Output.Contains(expected, StringComparison.Ordinal) && ReadText(marker) == markerText && ReadText(lkg).Contains(version, StringComparison.Ordinal);

    static bool Rejected((int ExitCode, string Output) child, string expected, string marker, byte[] previousLkg, string lkg) =>
        child.ExitCode != 0 && child.Output.Contains(expected, StringComparison.Ordinal) && !File.Exists(marker) && SameBytes(previousLkg, File.ReadAllBytes(lkg));

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

    static (int ExitCode, string Output) RunChild(string contentRoot, string signedFile, string spkiFile, string lkg, string marker)
    {
        var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.ArgumentList.Add("--signed-start");
        start.ArgumentList.Add(contentRoot);
        start.ArgumentList.Add(signedFile);
        start.ArgumentList.Add(spkiFile);
        start.ArgumentList.Add(lkg);
        start.Environment[MarkerVariable] = marker;
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

    internal static TrustedReleaseIdentity Identity(TrustedUpdateTarget hostTarget, string version) =>
        new(version, hostTarget.Runtime, hostTarget.Architecture, EntryTypeName, EntryMethodName, EntryFileName);

    internal static byte[]? SignPackage(string contentRoot, TrustedReleaseIdentity identity, ECDsa key)
    {
        var signed = TrustedRelease.Sign(contentRoot, identity, new[] { EntryFileName, PrivateFileName, HelperFileName }, key);
        return signed.Succeeded ? signed.Document : null;
    }

    internal static void WritePackage(string contentRoot, bool throws)
    {
        WriteAssembly(Path.Combine(contentRoot, EntryFileName), throws);
        File.WriteAllBytes(Path.Combine(contentRoot, PrivateFileName), new byte[] { 1, 2, 3, 4 });
        File.WriteAllBytes(Path.Combine(contentRoot, HelperFileName), new byte[] { 5, 6, 7, 8 });
    }

    internal static void WriteAssembly(string path, bool throws)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
        var type = module.DefineType(EntryTypeName, TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var method = type.DefineMethod(EntryMethodName, MethodAttributes.Public | MethodAttributes.Static, typeof(int), Type.EmptyTypes);
        var il = method.GetILGenerator();
        if (throws)
        {
            il.Emit(OpCodes.Ldstr, "signed-activate-fault");
            il.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
            il.Emit(OpCodes.Throw);
        }
        else
        {
            var value = il.DeclareLocal(typeof(int));
            var marker = il.DeclareLocal(typeof(string));
            var skip = il.DefineLabel();
            il.Emit(OpCodes.Ldc_I4, 41);
            il.Emit(OpCodes.Ldc_I4_3);
            il.Emit(OpCodes.Mul);
            il.Emit(OpCodes.Ldc_I4_7);
            il.Emit(OpCodes.Add);
            il.Emit(OpCodes.Stloc, value);
            il.Emit(OpCodes.Ldstr, MarkerVariable);
            il.Emit(OpCodes.Call, typeof(Environment).GetMethod(nameof(Environment.GetEnvironmentVariable), new[] { typeof(string) })!);
            il.Emit(OpCodes.Stloc, marker);
            il.Emit(OpCodes.Ldloc, marker);
            il.Emit(OpCodes.Brfalse, skip);
            il.Emit(OpCodes.Ldloc, marker);
            il.Emit(OpCodes.Ldloca, value);
            il.Emit(OpCodes.Call, typeof(int).GetMethod(nameof(int.ToString), Type.EmptyTypes)!);
            il.Emit(OpCodes.Call, typeof(File).GetMethod(nameof(File.WriteAllText), new[] { typeof(string), typeof(string) })!);
            il.MarkLabel(skip);
            il.Emit(OpCodes.Ldloc, value);
            il.Emit(OpCodes.Ret);
        }

        type.CreateType();
        builder.Save(path);
    }
}

