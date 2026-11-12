using System;
using System.Collections.Generic;
using RuneCLR.TrustedUpdate;

namespace RuneCLR.IpadDelivery;

/// <summary>
/// Host-supplied delivery configuration. Every trust input is a fixed host value: the pinned
/// SubjectPublicKeyInfo bytes, the deployment contract identity and the allowed roots never come
/// from the network, the package or the environment.
/// </summary>
public sealed record DeliveryOptions
{
    /// <summary>Pinned ECDSA P-256 SubjectPublicKeyInfo bytes (host constant, required).</summary>
    public required byte[] HostSubjectPublicKeyInfo { get; init; }

    /// <summary>Host runtime/architecture pair used for exact compatibility comparison.</summary>
    public required TrustedUpdateTarget Target { get; init; }

    /// <summary>Host-owned Contract identity (name/version/mvid). Never filled from the package sidecar.</summary>
    public required RuntimeContractIdentity HostContract { get; init; }

    /// <summary>Host-owned deployment Contract assembly path used by the compatibility gate.</summary>
    public required string HostDeploymentContractPath { get; init; }

    /// <summary>Existing directory that already contains a last-known-good release layout.</summary>
    public required string AllowedReleasesRoot { get; init; }

    /// <summary>Host-controlled last-known-good receipt path (outside the package).</summary>
    public required string RecoveryReceiptPath { get; init; }

    /// <summary>Target directory for a newly staged release (must not already exist).</summary>
    public required string FinalReleaseDirectory { get; init; }

    /// <summary>Process-wide compatibility gate. Required must stay true; there is no downgrade switch.</summary>
    public bool RequireRuntimeContractCompatibility { get; init; } = true;

    /// <summary>Bounded download deadline applied to headers AND the complete body.</summary>
    public TimeSpan DownloadDeadline { get; init; } = TimeSpan.FromSeconds(30);

    /// <summary>Maximum accepted release document size.</summary>
    public int MaxDocumentBytes { get; init; } = TrustedRelease.MaxDocumentBytes;

    /// <summary>Maximum accepted compatibility sidecar size.</summary>
    public int MaxCompatSidecarBytes { get; init; } = 64 * 1024;

    private static string CanonicalPath(string path, string name)
    {
        try { return Path.GetFullPath(path); }
        catch (Exception) { throw new ArgumentException("Path is not canonical.", name); }
    }

    private static string CanonicalDirectory(string path, bool mustExist, string name)
    {
        var full = CanonicalPath(path, name);
        if (mustExist && !Directory.Exists(full)) throw new ArgumentException("Directory does not exist.", name);
        return full;
    }

    private static void RejectReparse(string path, string name)
    {
        var current = path;
        while (!string.IsNullOrEmpty(current))
        {
            if (Directory.Exists(current) || File.Exists(current))
            {
                var attributes = File.GetAttributes(current);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new ArgumentException("A reparse point/alias is not allowed in " + name + ".", name);
            }
            current = Path.GetDirectoryName(current);
        }
    }

    public void Validate()
    {
        if (HostSubjectPublicKeyInfo is null || HostSubjectPublicKeyInfo.Length == 0)
            throw new ArgumentException("A pinned host SubjectPublicKeyInfo is required.", nameof(HostSubjectPublicKeyInfo));
        if (string.IsNullOrWhiteSpace(AllowedReleasesRoot) || string.IsNullOrWhiteSpace(RecoveryReceiptPath) ||
            string.IsNullOrWhiteSpace(FinalReleaseDirectory))
            throw new ArgumentException("Delivery roots are required.");
        if (HostContract is null) throw new ArgumentException("A host-owned Contract identity is required.", nameof(HostContract));
        if (string.IsNullOrWhiteSpace(HostDeploymentContractPath))
            throw new ArgumentException("A host-owned deployment Contract path is required.", nameof(HostDeploymentContractPath));
        if (!RequireRuntimeContractCompatibility)
            throw new ArgumentException("The required compatibility gate cannot be disabled.", nameof(RequireRuntimeContractCompatibility));
        // P1-1: canonical containment is checked BEFORE anything is downloaded or written.
        // final must live inside the allowed releases root, the receipt must live outside it, and
        // no component may be a reparse point/alias.
        var root = CanonicalDirectory(AllowedReleasesRoot, mustExist: true, "AllowedReleasesRoot");
        var final = CanonicalPath(FinalReleaseDirectory, "FinalReleaseDirectory");
        var relative = Path.GetRelativePath(root, final);
        if (relative == "." || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal) ||
            relative == ".." || Path.IsPathRooted(relative))
            throw new ArgumentException("FinalReleaseDirectory must be inside AllowedReleasesRoot.", nameof(FinalReleaseDirectory));
        foreach (var segment in relative.Split(Path.DirectorySeparatorChar))
            if (segment.Length == 0) throw new ArgumentException("FinalReleaseDirectory has an empty segment.", nameof(FinalReleaseDirectory));
        if (final == root) throw new ArgumentException("FinalReleaseDirectory cannot be the releases root.", nameof(FinalReleaseDirectory));

        var receipt = CanonicalPath(RecoveryReceiptPath, "RecoveryReceiptPath");
        var receiptRelative = Path.GetRelativePath(root, receipt);
        if (!receiptRelative.StartsWith("..", StringComparison.Ordinal) && !Path.IsPathRooted(receiptRelative))
            throw new ArgumentException("RecoveryReceiptPath must be outside AllowedReleasesRoot.", nameof(RecoveryReceiptPath));
        RejectReparse(root, "AllowedReleasesRoot");
        RejectReparse(final, "FinalReleaseDirectory");
        RejectReparse(receipt, "RecoveryReceiptPath");

        if (DownloadDeadline <= TimeSpan.Zero || DownloadDeadline > TimeSpan.FromMinutes(5))
            throw new ArgumentOutOfRangeException(nameof(DownloadDeadline));
        if (MaxDocumentBytes <= 0 || MaxDocumentBytes > TrustedRelease.MaxDocumentBytes)
            throw new ArgumentOutOfRangeException(nameof(MaxDocumentBytes));
        if (MaxCompatSidecarBytes <= 0 || MaxCompatSidecarBytes > 1024 * 1024)
            throw new ArgumentOutOfRangeException(nameof(MaxCompatSidecarBytes));
    }
}

/// <summary>Downloaded release offer: signed envelope, compatibility sidecar, entry metadata.</summary>
/// <summary>Downloaded release offer. Expected entry fields are optional and, when set, must match the signed manifest exactly.</summary>
public sealed record DeliveryOffer
{
    public required string VersionName { get; init; }
    public required Uri DocumentUri { get; init; }
    /// <summary>One entry per consumed file; staging rejects missing/duplicate/extra against the signed list.</summary>
    public required IReadOnlyList<DeliveryContentSource> Content { get; init; }
    public string EntryAssemblyName { get; init; } = "";
    public string EntryTypeName { get; init; } = "";
    public string EntryMethodName { get; init; } = "";
}

/// <summary>One signed content entry: relative path plus the URI that serves its bytes.</summary>
public sealed record DeliveryContentSource(string RelativePath, Uri Uri);

public enum DeliveryFailure
{
    None = 0,
    InvalidRequest,
    DownloadFailed,
    DownloadTooLarge,
    StagingFailed,
    VerificationFailed,
    CompatibilityMissing,
    CompatibilityRejected,
    ProcessGateRejected,
    ActivationFailed,
    ReceiptNotWritten,
}

/// <summary>
/// One delivery attempt result. It never carries an author assembly, exception or metadata object;
/// strings are host-owned diagnostics only.
/// </summary>
public readonly record struct DeliveryResult(
    DeliveryFailure Failure,
    string Detail,
    bool ReceiptAdvanced,
    string? CompatStatus,
    string? SelectedVersionName)
{
    public bool Succeeded => Failure == DeliveryFailure.None;

    /// <summary>
    /// On success: the verified content root and a private copy of the exact signed document that was
    /// verified. Pass this offer to IpadDeliveryBridge.Start; do not re-download or rebuild it.
    /// </summary>
    public TrustedReleaseOffer? Offer { get; init; }
}

/// <summary>Canonical contract identity declared by runeclr.compat.json.</summary>
public sealed record RuntimeContractIdentity(string Name, string Version, Guid Mvid)
{
    /// <summary>Canonical lowercase Guid "D" form used in sidecars and envelopes.</summary>
    public string CanonicalMvid => Mvid.ToString("D");
}

