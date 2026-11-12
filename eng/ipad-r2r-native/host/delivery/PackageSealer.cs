using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RuneCLR.TrustedUpdate;

namespace RuneCLR.IpadDelivery;

/// <summary>The signed file set produced for one release directory.</summary>
public sealed record SealedPackage(
    string ContentRoot,
    IReadOnlyList<string> Files,
    byte[] Document,
    string DocumentPath,
    string SidecarPath,
    string PayloadListPath);

/// <summary>
/// Packaging entry for the owner. It runs AFTER native code signing: payload-files.txt is recomputed
/// from the final bytes, the canonical compatibility sidecar is written, and the ECDSA release
/// envelope signs the complete consumed set. The private key is only used through the supplied
/// instance and is never written, logged or echoed.
/// </summary>
public static class PackageSealer
{
    public const string SidecarName = "runeclr.compat.json";
    public const string EnvelopeName = "runeclr.release.json";
    public const string PayloadListName = "payload-files.txt";

    public static SealedPackage Seal(
        string contentRoot,
        TrustedReleaseIdentity identity,
        IReadOnlyList<string> consumedRelativePaths,
        RuntimeContractIdentity contract,
        TrustedUpdateTarget target,
        ECDsa privateKey)
    {
        ArgumentNullException.ThrowIfNull(privateKey);
        if (!Directory.Exists(contentRoot)) throw new DirectoryNotFoundException(contentRoot);
        if (consumedRelativePaths is null || consumedRelativePaths.Count == 0)
            throw new ArgumentException("consumed files are required", nameof(consumedRelativePaths));

        // P2-7: validate every consumed path canonically BEFORE reading or writing anything.
        var rootFull = Path.GetFullPath(contentRoot);
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var folded = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var relative in consumedRelativePaths)
        {
            if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative))
                throw new ArgumentException("consumed path must be relative", nameof(consumedRelativePaths));
            var normalized = relative.Replace('\\', '/');
            if (normalized.Split('/').Any(seg => seg.Length == 0 || seg == "." || seg == ".."))
                throw new ArgumentException("consumed path has an empty or escaping segment", nameof(consumedRelativePaths));
            if (!seen.Add(normalized) || !folded.Add(normalized))
                throw new ArgumentException("consumed path is duplicated/case-conflicting", nameof(consumedRelativePaths));
            if (string.Equals(normalized, SidecarName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(normalized, PayloadListName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(normalized, EnvelopeName, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("consumed path collides with a reserved packaging file", nameof(consumedRelativePaths));
            var full = Path.GetFullPath(Path.Combine(rootFull, normalized));
            if (!full.StartsWith(rootFull + Path.DirectorySeparatorChar, StringComparison.Ordinal))
                throw new ArgumentException("consumed path escapes the content root", nameof(consumedRelativePaths));
            if (!File.Exists(full)) throw new FileNotFoundException("consumed file missing", relative);
        }

        // 1. Recompute payload-files.txt from the final (already signed) bytes.
        var payload = new StringBuilder();
        foreach (var relative in consumedRelativePaths.OrderBy(p => p, StringComparer.Ordinal))
        {
            var full = Path.Combine(contentRoot, relative);
            if (!File.Exists(full)) throw new FileNotFoundException("consumed file missing", relative);
            payload.Append(Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(full))))
                .Append("  ").Append(relative).Append('\n');
        }
        File.WriteAllText(Path.Combine(contentRoot, PayloadListName), payload.ToString(), new UTF8Encoding(false));

        // 2. Canonical compatibility sidecar (schema runeclr.compat.v1).
        var sidecar = JsonSerializer.SerializeToUtf8Bytes(new
        {
            schema = ContractCompatibility.Schema,
            runtime = target.Runtime,
            architecture = target.Architecture,
            contract = new
            {
                name = contract.Name,
                version = contract.Version,
                mvid = contract.CanonicalMvid,
            },
        }, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllBytes(Path.Combine(contentRoot, SidecarName), sidecar);

        // 3. Sign the complete consumed set (owner files + sidecar + payload list).
        var set = consumedRelativePaths
            .Concat(new[] { SidecarName, PayloadListName })
            .Distinct(StringComparer.Ordinal)
            .OrderBy(p => p, StringComparer.Ordinal)
            .ToArray();

        var signed = TrustedRelease.Sign(contentRoot, identity, set, privateKey);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("seal-sign:" + signed.Failure + ":" + signed.Detail);

        var documentPath = Path.Combine(contentRoot, EnvelopeName);
        File.WriteAllBytes(documentPath, signed.Document);

        // Final-bytes check: verify the just-written envelope against the files on disk with the
        // public half of the same key, so a hash/sign mismatch can never be packaged.
        var verification = TrustedRelease.Verify(contentRoot, signed.Document, privateKey.ExportSubjectPublicKeyInfo());
        if (!verification.Succeeded)
            throw new InvalidOperationException("seal-verify:" + verification.Failure + ":" + verification.Detail);

        return new SealedPackage(contentRoot, set, signed.Document, documentPath,
            Path.Combine(contentRoot, SidecarName), Path.Combine(contentRoot, PayloadListName));
    }

    /// <summary>Verifies a sealed directory with the host SPKI (no private key, no env).</summary>
    public static TrustedReleaseVerification Verify(string contentRoot, byte[] hostSubjectPublicKeyInfo, string documentPath)
    {
        var document = File.ReadAllBytes(documentPath);
        return TrustedRelease.Verify(contentRoot, document, hostSubjectPublicKeyInfo);
    }
}

