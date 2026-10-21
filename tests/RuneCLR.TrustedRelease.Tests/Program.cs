using System.ComponentModel;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using RuneCLR.TrustedUpdate;

var failed = 0;
void Check(bool condition, string name)
{
    if (condition)
    {
        Console.WriteLine("PASS " + name);
        return;
    }

    Console.WriteLine("FAIL " + name);
    failed++;
}

using var publisher = ECDsa.Create(ECCurve.NamedCurves.nistP256);
var spki = publisher.ExportSubjectPublicKeyInfo();
var root = Path.Combine(Path.GetTempPath(), "trusted-release-" + Guid.NewGuid().ToString("n"));
Directory.CreateDirectory(root);
var lkg = Path.Combine(root, "not-written.json");
try
{
    var names = new[]
    {
        "TrustedUpdate.Update.dll",
        "TrustedUpdate.Private.dll",
        "TrustedUpdate.IlOnlyHelper.dll",
        "TrustedUpdate.A.r2r.dylib",
    };
    var originals = new Dictionary<string, byte[]>(StringComparer.Ordinal);
    for (var i = 0; i < names.Length; i++)
    {
        var data = new byte[48];
        RandomNumberGenerator.Fill(data);
        data[0] = (byte)(i + 1);
        originals[names[i]] = data;
        File.WriteAllBytes(Path.Combine(root, names[i]), data);
    }

    File.WriteAllBytes(Path.Combine(root, "unlisted.bin"), [9, 9, 9]);
    var identity = new TrustedReleaseIdentity(
        "1.2.3",
        "net11.0",
        "arm64",
        "TrustedUpdate.Update",
        "Run",
        "TrustedUpdate.Update.dll");
    var signed = TrustedRelease.Sign(root, identity, names, publisher);
    Check(signed.Succeeded && signed.Document is not null, "sign");
    if (signed.Document is null)
        return FailEarly();

    var verified = TrustedRelease.Verify(root, signed.Document, spki);
    Check(verified.Succeeded && verified.Candidate is not null && verified.Approval is not null, "verify " + verified.Failure + " " + verified.Detail);
    if (!verified.Succeeded || verified.Candidate is null || verified.Approval is null)
        return FailEarly();

    var listed = verified.Candidate.AdditionalContent!;
    var extraNames = listed.Select(item => Path.GetFileName(item.Path)).OrderBy(item => item, StringComparer.Ordinal).ToArray();
    Check(extraNames.SequenceEqual([
        "TrustedUpdate.A.r2r.dylib",
        "TrustedUpdate.IlOnlyHelper.dll",
        "TrustedUpdate.Private.dll",
    ]), "full-package " + string.Join(",", extraNames));
    Check(!extraNames.Contains("unlisted.bin"), "unlisted-not-authenticated");
    Check(verified.Approval.ContentSha256 == verified.Candidate.ContentSha256, "approval-binds-entry");
    Check(verified.Approval.ApprovalId.StartsWith("spki-sha256:", StringComparison.Ordinal), "approval-id");

    var host = new TrustedUpdateTarget("net11.0", "arm64");
    var plan = new TrustedUpdateProcess().TryPlanCandidate(verified.Candidate, host, verified.Approval, root);
    Check(plan.Succeeded && plan.SelectedVersionName == "1.2.3", "plan " + plan.Failure);
    File.WriteAllBytes(Path.Combine(root, "TrustedUpdate.Private.dll"), Flip(originals["TrustedUpdate.Private.dll"]));
    var rehash = new TrustedUpdateProcess().TryPlanCandidate(verified.Candidate, host, verified.Approval, root);
    Check(rehash.Failure == TrustedUpdateFailure.ContentHashMismatch, "selector-rehash " + rehash.Failure);
    File.WriteAllBytes(Path.Combine(root, "TrustedUpdate.Private.dll"), originals["TrustedUpdate.Private.dll"]);

    var activated = false;
    var started = new TrustedUpdateProcess().TryStartHostLoaded(
        verified.Candidate,
        host,
        null,
        verified.Approval,
        root,
        null,
        null,
        "1.2.3",
        (candidate, source, failure) =>
        {
            activated = source == TrustedUpdateStartSource.Candidate && candidate.AdditionalContent is not null;
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, 7);
        });
    Check(started.Succeeded && started.Value == 7 && activated && !File.Exists(lkg), "start-host-loaded " + started.Failure);

    using var other = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    var wrongKey = TrustedRelease.Verify(root, signed.Document, other.ExportSubjectPublicKeyInfo());
    Check(wrongKey.Failure == TrustedReleaseFailure.InvalidSignature && wrongKey.Candidate is null && wrongKey.Approval is null, "wrong-key " + wrongKey.Failure);

    Check(RejectsContent(root, signed.Document, spki, "TrustedUpdate.Private.dll", originals), "replace-private");
    Check(RejectsContent(root, signed.Document, spki, "TrustedUpdate.A.r2r.dylib", originals), "replace-native");
    var helperPath = Path.Combine(root, "TrustedUpdate.IlOnlyHelper.dll");
    File.Delete(helperPath);
    var deleted = TrustedRelease.Verify(root, signed.Document, spki);
    Check(deleted.Failure == TrustedReleaseFailure.ContentMismatch && deleted.Candidate is null && !File.Exists(lkg), "delete-helper " + deleted.Detail);
    File.WriteAllBytes(helperPath, originals["TrustedUpdate.IlOnlyHelper.dll"]);

    var restored = TrustedRelease.Verify(root, signed.Document, spki);
    Check(restored.Succeeded, "restored");


    Check(Tamper(signed.Document, spki, "\"version\":\"1.2.3\"", "\"version\":\"9.9.9\""), "version-tamper");
    Check(Tamper(signed.Document, spki, "\"architecture\":\"arm64\"", "\"architecture\":\"x64\""), "target-tamper");
    Check(Tamper(signed.Document, spki, "\"entryMethod\":\"Run\"", "\"entryMethod\":\"Stop\""), "entry-tamper");
    Check(Tamper(signed.Document, spki, "\"path\":\"TrustedUpdate.Private.dll\"", "\"path\":\"TrustedUpdate.Other.dll\""), "remove-listed-file");

    var text = Encoding.UTF8.GetString(signed.Document);
    var newline = text.IndexOf((char)10);
    var second = text.IndexOf((char)10, newline + 1);
    var payload = text[(second + 1)..];
    var insertion = payload.Replace(
        "\"files\":[",
        "\"files\":[{\"path\":\"Extra.dll\",\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"},",
        StringComparison.Ordinal);
    var added = TrustedRelease.Verify(root, Encoding.UTF8.GetBytes(text[..(second + 1)] + insertion), spki);
    Check(added.Failure == TrustedReleaseFailure.InvalidSignature && added.Candidate is null, "add-listed-file " + added.Failure);

    Check(BadSignature(signed.Document, spki, "!!!!"), "bad-base64");
    Check(BadSignature(signed.Document, spki, Convert.ToBase64String(new byte[32])), "short-signature");
    Check(FlippedSignature(signed.Document, spki), "flipped-signature");
    Check(TrustedRelease.Verify(root, [], spki).Failure == TrustedReleaseFailure.InvalidDocument, "empty-document");

    Check(PathRejected(root, identity, publisher, ["../secret.dll"], "../secret.dll"), "dotdot");
    Check(PathRejected(root, identity, publisher, ["a/../TrustedUpdate.Update.dll"], "a/../TrustedUpdate.Update.dll"), "dotdot-middle");
    Check(PathRejected(root, identity, publisher, ["dir\\TrustedUpdate.Update.dll"], "dir\\TrustedUpdate.Update.dll"), "backslash");
    Check(PathRejected(root, identity, publisher, ["dir//TrustedUpdate.Update.dll"], "dir//TrustedUpdate.Update.dll"), "double-slash");
    Check(PathRejected(root, identity, publisher, ["/TrustedUpdate.Update.dll"], "/TrustedUpdate.Update.dll"), "absolute");
    Check(PathRejected(root, identity, publisher, ["TrustedUpdate.Update.dll", "TrustedUpdate.Update.dll"], "TrustedUpdate.Update.dll"), "duplicate");
    Check(PathRejected(root, identity, publisher, ["TrustedUpdate.Update.dll", "trustedupdate.update.dll"], "TrustedUpdate.Update.dll"), "case-conflict");

    var evilPayload = "{\"formatVersion\":1,\"version\":\"1.2.3\",\"runtime\":\"net11.0\",\"architecture\":\"arm64\",\"entryType\":\"TrustedUpdate.Update\",\"entryMethod\":\"Run\",\"entryPath\":\"../secret.dll\",\"files\":[{\"path\":\"../secret.dll\",\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}]}";
    var evilSig = Convert.ToBase64String(publisher.SignData(Encoding.UTF8.GetBytes(evilPayload), HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation));
    var evilDoc = Encoding.UTF8.GetBytes("RTRSIG1" + (char)10 + evilSig + (char)10 + evilPayload);
    var evil = TrustedRelease.Verify(root, evilDoc, spki);
    Check(!evil.Succeeded && evil.Candidate is null && evil.Approval is null && !File.Exists(lkg), "signed-illegal-path " + evil.Failure + " " + evil.Detail);

    using var p384 = ECDsa.Create(ECCurve.NamedCurves.nistP384);
    var wrongCurve = TrustedRelease.Sign(root, identity, names, p384);
    Check(wrongCurve.Failure == TrustedReleaseFailure.UntrustedKey && wrongCurve.Document is null, "reject-p384");
    var fileRoot = TrustedRelease.Sign(Path.Combine(root, "TrustedUpdate.Update.dll"), identity, names, publisher);
    Check(fileRoot.Failure == TrustedReleaseFailure.InvalidPath && fileRoot.Document is null && fileRoot.Detail == "file", "root-is-file " + fileRoot.Failure + " " + fileRoot.Detail);
    var missingRoot = TrustedRelease.Sign(Path.Combine(root, "missing-root"), identity, names, publisher);
    Check(!missingRoot.Succeeded && missingRoot.Document is null, "missing-root " + missingRoot.Failure + " " + missingRoot.Detail);
    var nestedIdentity = identity with { EntryPath = "TrustedUpdate.Update.dll/nested.dll" };
    var nested = TrustedRelease.Sign(root, nestedIdentity, [nestedIdentity.EntryPath], publisher);
    Check(nested.Failure == TrustedReleaseFailure.InvalidPath && nested.Document is null, "file-as-directory " + nested.Failure + " " + nested.Detail);
    CheckParentJunction(root, identity, publisher, spki);
    CheckSecp256k1(root, identity, names);
}
finally
{
    Directory.Delete(root, recursive: true);
}

Console.WriteLine(failed == 0
    ? "TRUSTED_RELEASE_TESTS passed"
    : "TRUSTED_RELEASE_TESTS failed=" + failed);
return failed == 0 ? 0 : 1;

int FailEarly()
{
    Console.WriteLine("TRUSTED_RELEASE_TESTS failed=early");
    return 1;
}

bool RejectsContent(string root, byte[] document, byte[] spki, string name, Dictionary<string, byte[]> originals)
{
    var path = Path.Combine(root, name);
    File.WriteAllBytes(path, Flip(originals[name]));
    var result = TrustedRelease.Verify(root, document, spki);
    File.WriteAllBytes(path, originals[name]);
    return result.Failure == TrustedReleaseFailure.ContentMismatch && result.Candidate is null && result.Approval is null;
}

bool Tamper(byte[] document, byte[] spki, string oldText, string newText)
{
    var text = Encoding.UTF8.GetString(document).Replace(oldText, newText, StringComparison.Ordinal);
    var result = TrustedRelease.Verify(root, Encoding.UTF8.GetBytes(text), spki);
    return result.Failure == TrustedReleaseFailure.InvalidSignature && result.Candidate is null && result.Approval is null;
}

bool BadSignature(byte[] document, byte[] spki, string signature)
{
    var text = Encoding.UTF8.GetString(document);
    var first = text.IndexOf((char)10);
    var second = text.IndexOf((char)10, first + 1);
    var edited = text[..(first + 1)] + signature + text[second..];
    var result = TrustedRelease.Verify(root, Encoding.UTF8.GetBytes(edited), spki);
    return result.Failure == TrustedReleaseFailure.InvalidSignature && result.Candidate is null;
}

bool FlippedSignature(byte[] document, byte[] spki)
{
    var text = Encoding.UTF8.GetString(document);
    var first = text.IndexOf((char)10);
    var second = text.IndexOf((char)10, first + 1);
    var raw = Convert.FromBase64String(text[(first + 1)..second]);
    raw[0] ^= 0x01;
    return BadSignature(document, spki, Convert.ToBase64String(raw));
}

bool PathRejected(string root, TrustedReleaseIdentity identity, ECDsa key, string[] paths, string entry)
{
    var bad = identity with { EntryPath = entry };
    var signed = TrustedRelease.Sign(root, bad, paths, key);
    return !signed.Succeeded && signed.Document is null && signed.Failure == TrustedReleaseFailure.InvalidPath;
}

byte[] Flip(byte[] value)
{
    var copy = (byte[])value.Clone();
    copy[0] ^= 0xFF;
    return copy;
}

void CheckParentJunction(string root, TrustedReleaseIdentity identity, ECDsa key, byte[] spki)
{
    var outside = Path.Combine(root, "outside-payload");
    var parent = Path.Combine(root, "link-parent");
    var via = Path.Combine(parent, "via");
    var rootLink = Path.Combine(parent, "root-link");
    Directory.CreateDirectory(outside);
    Directory.CreateDirectory(parent);
    File.WriteAllBytes(Path.Combine(outside, "TrustedUpdate.Update.dll"), File.ReadAllBytes(Path.Combine(root, "TrustedUpdate.Update.dll")));
    if (!TryCreateJunction(via, outside) || !TryCreateJunction(rootLink, outside))
    {
        Console.WriteLine("SKIP parent-junction");
        RemoveJunction(via);
        RemoveJunction(rootLink);
        return;
    }

    try
    {
        var through = identity with { EntryPath = "via/TrustedUpdate.Update.dll" };
        var signed = TrustedRelease.Sign(parent, through, [through.EntryPath], key);
        Check(signed.Failure == TrustedReleaseFailure.InvalidPath && signed.Detail == "reparse" && signed.Document is null, "parent-junction " + signed.Failure + " " + signed.Detail);
        var direct = TrustedRelease.Sign(outside, identity, ["TrustedUpdate.Update.dll"], key);
        Check(direct.Succeeded && direct.Document is not null, "outside-sign " + direct.Failure + " " + direct.Detail);
        if (direct.Document is null)
            return;
        var verified = TrustedRelease.Verify(rootLink, direct.Document, spki);
        Check(verified.Failure == TrustedReleaseFailure.InvalidPath && verified.Detail == "reparse" && verified.Candidate is null && verified.Approval is null, "root-junction " + verified.Failure + " " + verified.Detail);
    }
    finally
    {
        RemoveJunction(via);
        RemoveJunction(rootLink);
    }
}

bool TryCreateJunction(string link, string target)
{
    if (Directory.Exists(link))
        return true;
    if (OperatingSystem.IsWindows())
        return TryCreateWindowsJunction(link, target);
    return TryCreateDirectorySymlink(link, target);
}

bool TryCreateWindowsJunction(string link, string target)
{
    try
    {
        var start = new ProcessStartInfo("cmd.exe", "/c mklink /J \"" + link + "\" \"" + target + "\"")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        using var process = Process.Start(start);
        if (process is null)
            return false;
        process.WaitForExit();
        return process.ExitCode == 0 && Directory.Exists(link);
    }
    catch (Win32Exception)
    {
        return false;
    }
    catch (IOException)
    {
        return false;
    }
    catch (UnauthorizedAccessException)
    {
        return false;
    }
}

bool TryCreateDirectorySymlink(string link, string target)
{
    try
    {
        Directory.CreateSymbolicLink(link, target);
        return Directory.Exists(link);
    }
    catch (IOException)
    {
        return false;
    }
    catch (UnauthorizedAccessException)
    {
        return false;
    }
    catch (PlatformNotSupportedException)
    {
        return false;
    }
    catch (NotSupportedException)
    {
        return false;
    }
}

void RemoveJunction(string link)
{
    if (Directory.Exists(link))
        Directory.Delete(link, recursive: false);
}

void CheckSecp256k1(string root, TrustedReleaseIdentity identity, string[] names)
{
    ECDsa? k1;
    try
    {
        k1 = ECDsa.Create(ECCurve.CreateFromValue("1.3.132.0.10"));
    }
    catch (Exception)
    {
        Console.WriteLine("SKIP secp256k1");
        return;
    }

    if (k1 is null)
    {
        Console.WriteLine("SKIP secp256k1");
        return;
    }

    using (k1)
    {
        if (k1.KeySize != 256)
        {
            Console.WriteLine("SKIP secp256k1-keysize");
            return;
        }

        var signed = TrustedRelease.Sign(root, identity, names, k1);
        Check(signed.Failure == TrustedReleaseFailure.UntrustedKey && signed.Document is null, "secp256k1 " + signed.Failure + " " + signed.Detail);
    }
}

