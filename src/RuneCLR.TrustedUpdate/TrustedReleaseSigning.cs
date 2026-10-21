using System.Collections.ObjectModel;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace RuneCLR.TrustedUpdate;

public enum TrustedReleaseFailure
{
    None = 0,
    InvalidDocument,
    InvalidSignature,
    UntrustedKey,
    InvalidPath,
    OutsideContentRoot,
    ContentMismatch,
    InvalidIdentity,
}

public readonly record struct TrustedReleaseIdentity(
    string Version,
    string Runtime,
    string Architecture,
    string EntryType,
    string EntryMethod,
    string EntryPath);

public sealed class TrustedReleaseSigned
{
    internal TrustedReleaseSigned(TrustedReleaseFailure failure, string detail, byte[]? document)
    {
        Failure = failure;
        Detail = detail;
        Document = document;
    }

    public TrustedReleaseFailure Failure { get; }
    public string Detail { get; }
    public byte[]? Document { get; }
    public bool Succeeded => Failure == TrustedReleaseFailure.None;
}

public sealed class TrustedReleaseVerification
{
    internal TrustedReleaseVerification(
        TrustedReleaseFailure failure,
        string detail,
        TrustedUpdateCandidate? candidate,
        TrustedUpdateApproval? approval)
    {
        Failure = failure;
        Detail = detail;
        Candidate = candidate;
        Approval = approval;
    }

    public TrustedReleaseFailure Failure { get; }
    public string Detail { get; }
    public TrustedUpdateCandidate? Candidate { get; }
    public TrustedUpdateApproval? Approval { get; }
    public bool Succeeded => Failure == TrustedReleaseFailure.None;
}

public static class TrustedRelease
{
    public const int FormatVersion = 1;
    public const int MaxDocumentBytes = 64 * 1024;
    public const int MaxFiles = 64;
    public const int MaxPathLength = 180;
    public const int MaxIdentityLength = 128;
    public const int MaxFileBytes = 32 * 1024 * 1024;
    public const int SignatureBytes = 64;
    public const int SpkiBytes = 91;

    static readonly byte[] SpkiPrefix =
    [
        0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01,
        0x06, 0x08, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00, 0x04,
    ];

    static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    public static TrustedReleaseSigned Sign(
        string contentRoot,
        TrustedReleaseIdentity identity,
        IReadOnlyList<string> relativePaths,
        ECDsa privateKey)
    {
        ArgumentNullException.ThrowIfNull(privateKey);
        if (!IsPrime256v1(privateKey))
            return SignedFail(TrustedReleaseFailure.UntrustedKey, "curve");
        if (!TryDescribe(contentRoot, identity, relativePaths, out var described, out var failure, out var detail))
            return SignedFail(failure, detail);
        byte[] payload;
        try
        {
            payload = Utf8.GetBytes(described);
        }
        catch (EncoderFallbackException)
        {
            return SignedFail(TrustedReleaseFailure.InvalidDocument, "encoding");
        }

        byte[] signature;
        try
        {
            signature = privateKey.SignData(payload, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation);
        }
        catch (CryptographicException)
        {
            return SignedFail(TrustedReleaseFailure.InvalidSignature, "sign");
        }

        if (signature.Length != SignatureBytes)
            return SignedFail(TrustedReleaseFailure.InvalidSignature, "sign-length");
        var document = Utf8.GetBytes(Envelope(Convert.ToBase64String(signature), described));
        if (document.Length > MaxDocumentBytes)
            return SignedFail(TrustedReleaseFailure.InvalidDocument, "document-size");
        return new TrustedReleaseSigned(TrustedReleaseFailure.None, "", document);
    }

    public static TrustedReleaseVerification Verify(
        string contentRoot,
        ReadOnlySpan<byte> signedDocument,
        ReadOnlySpan<byte> hostSubjectPublicKeyInfo)
    {
        if (signedDocument.Length == 0 || signedDocument.Length > MaxDocumentBytes)
            return VerifyFail(TrustedReleaseFailure.InvalidDocument, "document-size");
        if (!IsPinnedSpki(hostSubjectPublicKeyInfo))
            return VerifyFail(TrustedReleaseFailure.UntrustedKey, "spki");
        string text;
        try
        {
            text = Utf8.GetString(signedDocument);
        }
        catch (DecoderFallbackException)
        {
            return VerifyFail(TrustedReleaseFailure.InvalidDocument, "encoding");
        }

        if (!TrySplit(text, out var signatureText, out var payload))
            return VerifyFail(TrustedReleaseFailure.InvalidDocument, "envelope");
        if (!TryDecodeSignature(signatureText, out var signature))
            return VerifyFail(TrustedReleaseFailure.InvalidSignature, "encoding");

        var payloadBytes = Utf8.GetBytes(payload);
        try
        {
            using var key = ECDsa.Create();
            key.ImportSubjectPublicKeyInfo(hostSubjectPublicKeyInfo, out var read);
            if (read != hostSubjectPublicKeyInfo.Length || key.KeySize != 256)
                return VerifyFail(TrustedReleaseFailure.UntrustedKey, "spki");
            if (!key.VerifyData(payloadBytes, signature, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation))
                return VerifyFail(TrustedReleaseFailure.InvalidSignature, "mismatch");
        }
        catch (CryptographicException)
        {
            return VerifyFail(TrustedReleaseFailure.UntrustedKey, "spki");
        }

        if (!TryReadPayload(payload, out var model, out var failure, out var detail))
            return VerifyFail(failure, detail);
        if (!string.Equals(payload, Canonical(model), StringComparison.Ordinal))
            return VerifyFail(TrustedReleaseFailure.InvalidDocument, "canonical");
        if (!TryBind(contentRoot, model, hostSubjectPublicKeyInfo, out var candidate, out var approval, out failure, out detail))
            return VerifyFail(failure, detail);
        return new TrustedReleaseVerification(TrustedReleaseFailure.None, "", candidate, approval);
    }

    static bool TryDescribe(
        string contentRoot,
        TrustedReleaseIdentity identity,
        IReadOnlyList<string> relativePaths,
        out string canonical,
        out TrustedReleaseFailure failure,
        out string detail)
    {
        canonical = "";
        if (relativePaths is null)
        {
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "files";
            return false;
        }

        if (!TryIdentity(identity, out failure, out detail))
            return false;
        if (!TryPathSet(relativePaths, identity.EntryPath, out var paths, out failure, out detail))
            return false;
        var files = new List<PackageFile>(paths.Count);
        foreach (var relative in paths)
        {
            if (!TryMap(contentRoot, relative, out var full, out failure, out detail))
                return false;
            if (!TryHash(full, out var hash, out failure, out detail))
                return false;
            files.Add(new PackageFile(relative, hash));
        }

        canonical = Canonical(new PackageModel(
            identity.Version,
            identity.Runtime,
            identity.Architecture,
            identity.EntryType,
            identity.EntryMethod,
            identity.EntryPath,
            files));
        failure = TrustedReleaseFailure.None;
        detail = "";
        return true;
    }

    static bool TryBind(
        string contentRoot,
        PackageModel model,
        ReadOnlySpan<byte> spki,
        out TrustedUpdateCandidate? candidate,
        out TrustedUpdateApproval? approval,
        out TrustedReleaseFailure failure,
        out string detail)
    {
        candidate = null;
        approval = null;
        string? entryFull = null;
        string? entryHash = null;
        var additional = new List<TrustedUpdateContentFile>();
        foreach (var file in model.Files)
        {
            if (!TryMap(contentRoot, file.Path, out var full, out failure, out detail))
                return false;
            if (!TryHash(full, out var actual, out failure, out detail))
                return false;
            if (!string.Equals(actual, file.Sha256, StringComparison.Ordinal))
            {
                failure = TrustedReleaseFailure.ContentMismatch;
                detail = "hash";
                return false;
            }

            if (string.Equals(file.Path, model.EntryPath, StringComparison.Ordinal))
            {
                entryFull = full;
                entryHash = actual;
            }
            else
            {
                additional.Add(new TrustedUpdateContentFile(full, actual));
            }
        }

        if (entryFull is null || entryHash is null)
        {
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "entry";
            return false;
        }

        IReadOnlyList<TrustedUpdateContentFile>? extras = additional.Count == 0
            ? null
            : new ReadOnlyCollection<TrustedUpdateContentFile>(additional.ToArray());
        candidate = new TrustedUpdateCandidate(
            model.Version,
            entryHash,
            entryFull,
            model.EntryType,
            model.EntryMethod,
            new TrustedUpdateTarget(model.Runtime, model.Architecture),
            extras);
        approval = new TrustedUpdateApproval(model.Version, entryHash, ApprovalId(spki));
        failure = TrustedReleaseFailure.None;
        detail = "";
        return true;
    }

    static string ApprovalId(ReadOnlySpan<byte> spki) =>
        "spki-sha256:" + Convert.ToHexStringLower(SHA256.HashData(spki));

    static bool TryIdentity(TrustedReleaseIdentity identity, out TrustedReleaseFailure failure, out string detail)
    {
        if (!IsToken(identity.Version)
            || !IsToken(identity.Runtime)
            || !IsToken(identity.Architecture)
            || !IsToken(identity.EntryType)
            || !IsToken(identity.EntryMethod))
        {
            failure = TrustedReleaseFailure.InvalidIdentity;
            detail = "field";
            return false;
        }

        failure = TrustedReleaseFailure.None;
        detail = "";
        return true;
    }

    static bool TryPathSet(
        IReadOnlyList<string> relativePaths,
        string entryPath,
        out List<string> paths,
        out TrustedReleaseFailure failure,
        out string detail)
    {
        paths = [];
        if (relativePaths.Count == 0 || relativePaths.Count > MaxFiles)
        {
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "files";
            return false;
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        var folded = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var relative in relativePaths)
        {
            if (!IsCanonicalRelative(relative))
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "path";
                return false;
            }

            if (!seen.Add(relative))
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "duplicate";
                return false;
            }

            if (!folded.Add(relative))
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "case";
                return false;
            }
        }

        if (!seen.Contains(entryPath))
        {
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "entry";
            return false;
        }

        paths.AddRange(seen);
        paths.Sort(StringComparer.Ordinal);
        failure = TrustedReleaseFailure.None;
        detail = "";
        return true;
    }

    static bool TryMap(
        string contentRoot,
        string relative,
        out string full,
        out TrustedReleaseFailure failure,
        out string detail)
    {
        full = "";
        try
        {
            if (string.IsNullOrWhiteSpace(contentRoot) || !IsCanonicalRelative(relative))
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "path";
                return false;
            }

            var root = Path.GetFullPath(contentRoot);
            if (!IsRealDirectory(root, out failure, out detail))
                return false;
            full = root;
            var segments = relative.Split('/');
            for (var i = 0; i < segments.Length - 1; i++)
            {
                full = Path.Combine(full, segments[i]);
                if (!IsRealDirectory(full, out failure, out detail))
                {
                    full = "";
                    return false;
                }
            }

            full = Path.GetFullPath(Path.Combine(full, segments[^1]));
            var compared = Path.GetRelativePath(root, full);
            var parentPrefix = ".." + Path.DirectorySeparatorChar;
            var altPrefix = ".." + Path.AltDirectorySeparatorChar;
            if (compared == "."
                || compared == ".."
                || compared.StartsWith(parentPrefix, StringComparison.Ordinal)
                || compared.StartsWith(altPrefix, StringComparison.Ordinal)
                || Path.IsPathRooted(compared))
            {
                failure = TrustedReleaseFailure.OutsideContentRoot;
                detail = "root";
                full = "";
                return false;
            }

            failure = TrustedReleaseFailure.None;
            detail = "";
            return true;
        }
        catch (Exception ex) when (IsPathFailure(ex))
        {
            full = "";
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "io";
            return false;
        }
    }

    static bool TryHash(string full, out string hash, out TrustedReleaseFailure failure, out string detail)
    {
        hash = "";
        try
        {
            if (!File.Exists(full))
            {
                failure = TrustedReleaseFailure.ContentMismatch;
                detail = "missing";
                return false;
            }

            var attributes = File.GetAttributes(full);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "reparse";
                return false;
            }

            if ((attributes & FileAttributes.Directory) != 0)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "file";
                return false;
            }

            if (new FileInfo(full).Length > MaxFileBytes)
            {
                failure = TrustedReleaseFailure.ContentMismatch;
                detail = "file-size";
                return false;
            }

            using var stream = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.Read);
            hash = Convert.ToHexStringLower(SHA256.HashData(stream));
            failure = TrustedReleaseFailure.None;
            detail = "";
            return true;
        }
        catch (Exception ex) when (IsPathFailure(ex))
        {
            hash = "";
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "io";
            return false;
        }
    }

    static bool IsRealDirectory(string path, out TrustedReleaseFailure failure, out string detail)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "reparse";
                return false;
            }

            if ((attributes & FileAttributes.Directory) == 0)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "file";
                return false;
            }

            failure = TrustedReleaseFailure.None;
            detail = "";
            return true;
        }
        catch (FileNotFoundException)
        {
            failure = TrustedReleaseFailure.ContentMismatch;
            detail = "missing";
            return false;
        }
        catch (DirectoryNotFoundException)
        {
            failure = TrustedReleaseFailure.ContentMismatch;
            detail = "missing";
            return false;
        }
        catch (Exception ex) when (IsPathFailure(ex))
        {
            failure = TrustedReleaseFailure.InvalidPath;
            detail = "io";
            return false;
        }
    }

    static bool IsPrime256v1(ECDsa key)
    {
        try
        {
            return IsPinnedSpki(key.ExportSubjectPublicKeyInfo());
        }
        catch (CryptographicException)
        {
            return false;
        }
    }

    static bool IsPathFailure(Exception exception) =>
        exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException;

    static bool TryReadPayload(string payload, out PackageModel model, out TrustedReleaseFailure failure, out string detail)
    {
        model = null!;
        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("formatVersion", out var format)
                || format.ValueKind != JsonValueKind.Number
                || !format.TryGetInt32(out var version)
                || version != FormatVersion)
            {
                failure = TrustedReleaseFailure.InvalidDocument;
                detail = "format";
                return false;
            }

            if (!TryJsonString(root, "version", out var packageVersion)
                || !TryJsonString(root, "runtime", out var runtime)
                || !TryJsonString(root, "architecture", out var architecture)
                || !TryJsonString(root, "entryType", out var entryType)
                || !TryJsonString(root, "entryMethod", out var entryMethod)
                || !TryJsonString(root, "entryPath", out var entryPath)
                || !root.TryGetProperty("files", out var filesElement)
                || filesElement.ValueKind != JsonValueKind.Array)
            {
                failure = TrustedReleaseFailure.InvalidDocument;
                detail = "field";
                return false;
            }

            if (root.EnumerateObject().Count() != 8)
            {
                failure = TrustedReleaseFailure.InvalidDocument;
                detail = "field";
                return false;
            }

            var identity = new TrustedReleaseIdentity(packageVersion, runtime, architecture, entryType, entryMethod, entryPath);
            if (!TryIdentity(identity, out failure, out detail))
                return false;
            if (filesElement.GetArrayLength() == 0 || filesElement.GetArrayLength() > MaxFiles)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "files";
                return false;
            }

            var files = new List<PackageFile>(filesElement.GetArrayLength());
            string? previous = null;
            foreach (var item in filesElement.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object
                    || item.EnumerateObject().Count() != 2
                    || !TryJsonString(item, "path", out var path)
                    || !TryJsonString(item, "sha256", out var sha)
                    || !IsSha256(sha)
                    || !IsCanonicalRelative(path))
                {
                    failure = TrustedReleaseFailure.InvalidDocument;
                    detail = "file";
                    return false;
                }

                if (previous is not null && string.CompareOrdinal(previous, path) >= 0)
                {
                    failure = TrustedReleaseFailure.InvalidPath;
                    detail = string.Equals(previous, path, StringComparison.Ordinal) ? "duplicate" : "order";
                    return false;
                }

                previous = path;
                files.Add(new PackageFile(path, sha));
            }

            var folded = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var entrySeen = false;
            foreach (var file in files)
            {
                if (!folded.Add(file.Path))
                {
                    failure = TrustedReleaseFailure.InvalidPath;
                    detail = "case";
                    return false;
                }

                if (string.Equals(file.Path, entryPath, StringComparison.Ordinal))
                    entrySeen = true;
            }

            if (!entrySeen)
            {
                failure = TrustedReleaseFailure.InvalidPath;
                detail = "entry";
                return false;
            }

            model = new PackageModel(packageVersion, runtime, architecture, entryType, entryMethod, entryPath, files);
            failure = TrustedReleaseFailure.None;
            detail = "";
            return true;
        }
        catch (JsonException)
        {
            failure = TrustedReleaseFailure.InvalidDocument;
            detail = "json";
            return false;
        }
    }

    static bool TryJsonString(JsonElement parent, string name, out string value)
    {
        value = "";
        if (!parent.TryGetProperty(name, out var property) || property.ValueKind != JsonValueKind.String)
            return false;
        value = property.GetString() ?? "";
        return true;
    }

    static readonly char Quote = (char)34;
    static readonly char Backslash = (char)92;
    static readonly char Newline = (char)10;
    static readonly char Return = (char)13;

    static string Canonical(PackageModel model)
    {
        var builder = new StringBuilder(256);
        builder.Append('{').Append(Quote).Append("formatVersion").Append(Quote).Append(':').Append(FormatVersion);
        AppendField(builder, "version", model.Version);
        AppendField(builder, "runtime", model.Runtime);
        AppendField(builder, "architecture", model.Architecture);
        AppendField(builder, "entryType", model.EntryType);
        AppendField(builder, "entryMethod", model.EntryMethod);
        AppendField(builder, "entryPath", model.EntryPath);
        builder.Append(',').Append(Quote).Append("files").Append(Quote).Append(":[");
        for (var i = 0; i < model.Files.Count; i++)
        {
            if (i != 0)
                builder.Append(',');
            builder.Append('{').Append(Quote).Append("path").Append(Quote).Append(':');
            AppendJson(builder, model.Files[i].Path);
            builder.Append(',').Append(Quote).Append("sha256").Append(Quote).Append(':');
            AppendJson(builder, model.Files[i].Sha256);
            builder.Append('}');
        }

        builder.Append("]}");
        return builder.ToString();
    }

    static void AppendField(StringBuilder builder, string name, string value)
    {
        builder.Append(',').Append(Quote).Append(name).Append(Quote).Append(':');
        AppendJson(builder, value);
    }

    static void AppendJson(StringBuilder builder, string value)
    {
        builder.Append(Quote);
        foreach (var character in value)
        {
            if (character == Quote || character == Backslash)
            {
                builder.Append(Backslash);
                builder.Append(character);
                continue;
            }

            if (character < 0x20)
            {
                builder.Append(Backslash);
                builder.Append('u');
                builder.Append(((int)character).ToString("x4"));
                continue;
            }

            builder.Append(character);
        }

        builder.Append(Quote);
    }

    static string Envelope(string signature, string payload) =>
        "RTRSIG1" + Newline + signature + Newline + payload;

    static bool TrySplit(string text, out string signature, out string payload)
    {
        signature = "";
        payload = "";
        if (text.IndexOf(Return) >= 0)
            return false;
        var parts = text.Split(Newline);
        if (parts.Length != 3 || parts[0] != "RTRSIG1" || parts[1].Length == 0 || parts[2].Length == 0)
            return false;
        signature = parts[1];
        payload = parts[2];
        return true;
    }

    static bool TryDecodeSignature(string text, out byte[] signature)
    {
        signature = [];
        if (text.Length == 0 || text.Length % 4 != 0)
            return false;
        foreach (var character in text)
        {
            var ok = character >= 'A' && character <= 'Z'
                || character >= 'a' && character <= 'z'
                || character >= '0' && character <= '9'
                || character == '+' || character == '/' || character == '=';
            if (!ok)
                return false;
        }

        try
        {
            signature = Convert.FromBase64String(text);
        }
        catch (FormatException)
        {
            return false;
        }

        return signature.Length == SignatureBytes;
    }

    static bool IsPinnedSpki(ReadOnlySpan<byte> spki)
    {
        if (spki.Length != SpkiBytes)
            return false;
        for (var i = 0; i < SpkiPrefix.Length; i++)
        {
            if (spki[i] != SpkiPrefix[i])
                return false;
        }

        return true;
    }

    static bool IsToken(string? value)
    {
        if (string.IsNullOrEmpty(value) || value.Length > MaxIdentityLength)
            return false;
        foreach (var character in value)
        {
            var ok = character >= 'A' && character <= 'Z'
                || character >= 'a' && character <= 'z'
                || character >= '0' && character <= '9'
                || character == '.' || character == '_' || character == '+' || character == '-';
            if (!ok)
                return false;
        }

        return true;
    }

    static bool IsSha256(string value)
    {
        if (value.Length != 64)
            return false;
        foreach (var character in value)
        {
            var ok = character >= '0' && character <= '9' || character >= 'a' && character <= 'f';
            if (!ok)
                return false;
        }

        return true;
    }

    static bool IsCanonicalRelative(string? relative)
    {
        if (string.IsNullOrEmpty(relative) || relative.Length > MaxPathLength)
            return false;
        if (relative[0] == '/' || relative[relative.Length - 1] == '/')
            return false;
        var segments = relative.Split('/');
        foreach (var segment in segments)
        {
            if (segment.Length == 0 || segment == "." || segment == "..")
                return false;
            foreach (var character in segment)
            {
                var ok = character >= 'A' && character <= 'Z'
                    || character >= 'a' && character <= 'z'
                    || character >= '0' && character <= '9'
                    || character == '.' || character == '_' || character == '-';
                if (!ok)
                    return false;
            }
        }

        return true;
    }

    static TrustedReleaseSigned SignedFail(TrustedReleaseFailure failure, string detail) =>
        new(failure, detail, null);

    static TrustedReleaseVerification VerifyFail(TrustedReleaseFailure failure, string detail) =>
        new(failure, detail, null, null);

    sealed class PackageModel(
        string version,
        string runtime,
        string architecture,
        string entryType,
        string entryMethod,
        string entryPath,
        List<PackageFile> files)
    {
        public string Version { get; } = version;
        public string Runtime { get; } = runtime;
        public string Architecture { get; } = architecture;
        public string EntryType { get; } = entryType;
        public string EntryMethod { get; } = entryMethod;
        public string EntryPath { get; } = entryPath;
        public List<PackageFile> Files { get; } = files;
    }

    readonly record struct PackageFile(string Path, string Sha256);
}

