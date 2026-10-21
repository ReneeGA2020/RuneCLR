using System.Runtime.CompilerServices;
using System.Text.Json;

[assembly: InternalsVisibleTo("RuneCLR.TrustedReleaseRecovery.Tests")]

namespace RuneCLR.TrustedUpdate;

/// <summary>
/// Restarts a signed release across process launches. The receipt is host-owned
/// state outside the immutable releases root. It stores a relative content root
/// and the original signed document, never a package public key or a trusted
/// candidate. Calling the activator is the irreversible boundary. This is not a
/// race-proof snapshot, a crash-durable directory replace, anti-rollback, network
/// authentication, or an iOS native gate.
/// </summary>
public static class TrustedReleaseRecovery
{
    public const int MaxReceiptBytes = 96 * 1024;

    public static TrustedReleaseRecoveryStart TryStart(
        TrustedReleaseOffer? offer,
        ReadOnlyMemory<byte> hostSubjectPublicKeyInfo,
        TrustedUpdateTarget target,
        string allowedReleasesRoot,
        string recoveryReceiptPath,
        TrustedUpdateActivator activator)
    {
        ArgumentNullException.ThrowIfNull(activator);
        if (hostSubjectPublicKeyInfo.Length != TrustedRelease.SpkiBytes)
            return Configure("spki");
        if (!TryConfigure(allowedReleasesRoot, recoveryReceiptPath, out var releasesRoot, out var receiptPath, out var configDetail))
            return Configure(configDetail);

        var spki = hostSubjectPublicKeyInfo.ToArray();
        var selector = new TrustedUpdateProcess();
        if (offer is not null)
        {
            var offered = TryOffer(offer, spki, target, releasesRoot, receiptPath, selector, activator);
            if (offered.Stop)
                return offered.Start;
            return TryRecover(releasesRoot, receiptPath, spki, target, selector, activator, offered.Start.Candidate);
        }

        return TryRecover(
            releasesRoot,
            receiptPath,
            spki,
            target,
            selector,
            activator,
            Candidate(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "absent"));
    }

    static Attempt TryOffer(
        TrustedReleaseOffer offer,
        byte[] spki,
        TrustedUpdateTarget target,
        string releasesRoot,
        string receiptPath,
        TrustedUpdateProcess selector,
        TrustedUpdateActivator activator)
    {
        if (string.IsNullOrWhiteSpace(offer.ContentRoot))
            return Continue(Candidate(TrustedReleaseFailure.InvalidPath, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "root"));
        if (offer.SignedDocument.Length == 0 || offer.SignedDocument.Length > TrustedRelease.MaxDocumentBytes)
            return Continue(Candidate(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "document-size"));
        string contentRoot;
        try
        {
            if (!TryCanonicalize(Path.GetFullPath(offer.ContentRoot), out contentRoot, out _))
                return Continue(Candidate(TrustedReleaseFailure.InvalidPath, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "root"));
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return Continue(Candidate(TrustedReleaseFailure.InvalidPath, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "root"));
        }

        if (!IsInside(releasesRoot, contentRoot))
            return Continue(Candidate(TrustedReleaseFailure.OutsideContentRoot, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "root"));
        if (Relative(releasesRoot, contentRoot) is null)
            return Continue(Candidate(TrustedReleaseFailure.InvalidPath, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "relative"));

        var document = offer.SignedDocument.ToArray();
        var verified = TrustedRelease.Verify(contentRoot, document, spki);
        if (!verified.Succeeded || verified.Candidate is null || verified.Approval is null)
            return Continue(Candidate(verified.Failure, TrustedUpdateFailure.None, TrustedUpdateFailure.None, verified.Detail));

        var planned = selector.TryPlanCandidate(verified.Candidate, target, verified.Approval, contentRoot);
        if (planned.Failure == TrustedUpdateFailure.ProcessSelectionLocked)
            return Stop(Locked(Candidate(TrustedReleaseFailure.None, TrustedUpdateFailure.ProcessSelectionLocked, TrustedUpdateFailure.ProcessSelectionLocked, "locked")));
        if (!planned.Succeeded)
            return Continue(Candidate(TrustedReleaseFailure.None, planned.Failure, TrustedUpdateFailure.None, "plan"));

        var hook = TrustedReleaseRecoveryDiagnostics.BeforeHostStart;
        if (hook is not null)
        {
            TrustedReleaseRecoveryDiagnostics.BeforeHostStart = null;
            hook();
        }

        var entered = false;
        var started = selector.TryStartHostLoaded(
            verified.Candidate,
            target,
            null,
            verified.Approval,
            contentRoot,
            null,
            null,
            verified.Candidate.VersionName,
            (chosen, _, _) =>
            {
                entered = true;
                return activator(chosen, TrustedUpdateStartSource.Candidate, TrustedUpdateFailure.None);
            });
        if (!entered)
        {
            if (started.Failure == TrustedUpdateFailure.ProcessSelectionLocked)
                return Stop(Locked(Candidate(TrustedReleaseFailure.None, TrustedUpdateFailure.ProcessSelectionLocked, TrustedUpdateFailure.ProcessSelectionLocked, "locked")));
            return Continue(Candidate(TrustedReleaseFailure.None, started.Failure, TrustedUpdateFailure.None, "plan"));
        }

        if (!started.Succeeded)
            return Stop(ActivationFailed(started.Failure, Candidate(TrustedReleaseFailure.None, TrustedUpdateFailure.None, started.Failure, "activation")));

        var candidateRecord = Candidate(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "");
        if (!TryPersist(releasesRoot, contentRoot, receiptPath, document, out var persistence, out var persistenceDetail))
        {
            return Stop(new TrustedReleaseRecoveryStart(
                true,
                started.SelectedVersionName,
                TrustedUpdateStartSource.Candidate,
                started.Value,
                "",
                candidateRecord,
                Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, ""),
                persistence,
                persistenceDetail));
        }

        return Stop(new TrustedReleaseRecoveryStart(
            true,
            started.SelectedVersionName,
            TrustedUpdateStartSource.Candidate,
            started.Value,
            "",
            candidateRecord,
            Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, ""),
            TrustedReleasePersistenceFailure.None,
            ""));
    }


    static TrustedReleaseRecoveryStart TryRecover(
        string releasesRoot,
        string receiptPath,
        byte[] spki,
        TrustedUpdateTarget target,
        TrustedUpdateProcess selector,
        TrustedUpdateActivator activator,
        TrustedReleaseRecoveryReason candidate)
    {
        if (!TryReadReceipt(receiptPath, out var relative, out var document, out var recovery))
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, recovery, TrustedReleasePersistenceFailure.None, "");
        if (!TryMap(releasesRoot, relative, out var contentRoot))
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(TrustedReleaseFailure.OutsideContentRoot, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "path"), TrustedReleasePersistenceFailure.None, "");

        var verified = TrustedRelease.Verify(contentRoot, document, spki);
        if (!verified.Succeeded || verified.Candidate is null || verified.Approval is null)
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(verified.Failure, TrustedUpdateFailure.None, TrustedUpdateFailure.None, verified.Detail), TrustedReleasePersistenceFailure.None, "");

        var planned = selector.TryPlanCandidate(verified.Candidate, target, verified.Approval, contentRoot);
        if (planned.Failure == TrustedUpdateFailure.ProcessSelectionLocked)
            return RecoveryLocked(candidate);
        if (!planned.Succeeded)
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(TrustedReleaseFailure.None, planned.Failure, TrustedUpdateFailure.None, "plan"), TrustedReleasePersistenceFailure.None, "");

        var entered = false;
        var offerPlan = candidate.Plan;
        var started = selector.TryStartHostLoaded(
            verified.Candidate,
            target,
            null,
            verified.Approval,
            contentRoot,
            null,
            null,
            verified.Candidate.VersionName,
            (chosen, _, _) =>
            {
                entered = true;
                return activator(chosen, TrustedUpdateStartSource.LastKnownGood, offerPlan);
            });
        if (!entered)
        {
            if (started.Failure == TrustedUpdateFailure.ProcessSelectionLocked)
                return RecoveryLocked(candidate);
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(TrustedReleaseFailure.None, started.Failure, TrustedUpdateFailure.None, "plan"), TrustedReleasePersistenceFailure.None, "");
        }

        if (!started.Succeeded)
            return new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, started.Failure, "activation"), TrustedReleasePersistenceFailure.None, "");

        return new TrustedReleaseRecoveryStart(
            true,
            started.SelectedVersionName,
            TrustedUpdateStartSource.LastKnownGood,
            started.Value,
            "",
            candidate,
            Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, ""),
            TrustedReleasePersistenceFailure.None,
            "");
    }

    static bool TryPersist(
        string releasesRoot,
        string contentRoot,
        string receiptPath,
        byte[] document,
        out TrustedReleasePersistenceFailure failure,
        out string detail)
    {
        var relative = Relative(releasesRoot, contentRoot);
        if (relative is null)
        {
            failure = TrustedReleasePersistenceFailure.InvalidPath;
            detail = "root";
            return false;
        }

        var directory = Path.GetDirectoryName(Path.GetFullPath(receiptPath));
        if (string.IsNullOrEmpty(directory))
        {
            failure = TrustedReleasePersistenceFailure.InvalidPath;
            detail = "receipt";
            return false;
        }

        if (TryGetAttributes(receiptPath, out var existing) && (existing & FileAttributes.ReparsePoint) != 0)
        {
            failure = TrustedReleasePersistenceFailure.InvalidPath;
            detail = "receipt-link";
            return false;
        }

        var temp = Path.Combine(directory, "receipt-" + Guid.NewGuid().ToString("n") + ".tmp");
        FileStream? stream = null;
        var owned = false;
        try
        {
            var payload = Encode(relative, document);
            if (payload.Length == 0 || payload.Length > MaxReceiptBytes)
            {
                failure = TrustedReleasePersistenceFailure.IoFailure;
                detail = "size";
                return false;
            }

            stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            owned = true;
            if (TrustedReleaseRecoveryDiagnostics.FailNextPersist)
            {
                TrustedReleaseRecoveryDiagnostics.FailNextPersist = false;
                throw new IOException("persist-seam");
            }

            stream.Write(payload, 0, payload.Length);
            stream.Flush(flushToDisk: true);
            stream.Dispose();
            stream = null;
            File.Move(temp, receiptPath, overwrite: true);
            owned = false;
            failure = TrustedReleasePersistenceFailure.None;
            detail = "";
            return true;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            failure = TrustedReleasePersistenceFailure.IoFailure;
            detail = "write";
            return false;
        }
        finally
        {
            if (stream is not null)
            {
                try
                {
                    stream.Dispose();
                }
                catch (Exception ex) when (IsOperational(ex))
                {
                }
            }

            if (owned)
                DeleteTemp(directory, temp);
        }
    }

    static byte[] Encode(string relative, byte[] document)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            writer.WriteNumber("v", 1);
            writer.WriteString("contentRoot", relative);
            writer.WriteString("document", Convert.ToBase64String(document));
            writer.WriteEndObject();
        }

        return buffer.ToArray();
    }

    static bool TryReadReceipt(
        string receiptPath,
        out string relative,
        out byte[] document,
        out TrustedReleaseRecoveryReason failure)
    {
        relative = "";
        document = Array.Empty<byte>();
        try
        {
            if (TryGetAttributes(receiptPath, out var attributes) && (attributes & FileAttributes.ReparsePoint) != 0)
            {
                failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "receipt-link");
                return false;
            }

            using var stream = new FileStream(receiptPath, FileMode.Open, FileAccess.Read, FileShare.Read);
            var buffer = new byte[MaxReceiptBytes + 1];
            var filled = 0;
            while (filled < buffer.Length)
            {
                var read = stream.Read(buffer, filled, buffer.Length - filled);
                if (read == 0)
                    break;
                filled += read;
            }

            if (filled > MaxReceiptBytes)
            {
                failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "receipt-size");
                return false;
            }

            using var json = JsonDocument.Parse(buffer.AsMemory(0, filled));
            var root = json.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("v", out var version)
                || version.ValueKind != JsonValueKind.Number
                || !version.TryGetInt32(out var format)
                || format != 1
                || !root.TryGetProperty("contentRoot", out var content)
                || content.ValueKind != JsonValueKind.String
                || !root.TryGetProperty("document", out var encoded)
                || encoded.ValueKind != JsonValueKind.String)
            {
                failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "receipt");
                return false;
            }

            relative = content.GetString() ?? "";
            var text = encoded.GetString() ?? "";
            if (text.Length > ((TrustedRelease.MaxDocumentBytes + 2) / 3) * 4)
            {
                failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "document-size");
                return false;
            }

            document = Convert.FromBase64String(text);
            if (document.Length == 0 || document.Length > TrustedRelease.MaxDocumentBytes)
            {
                failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "document-size");
                return false;
            }

            failure = Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "");
            return true;
        }
        catch (FileNotFoundException)
        {
            failure = Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "absent");
            return false;
        }
        catch (FormatException)
        {
            failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "document");
            return false;
        }
        catch (JsonException)
        {
            failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "json");
            return false;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            failure = Recovery(TrustedReleaseFailure.InvalidDocument, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "io");
            return false;
        }
    }

    static bool TryConfigure(
        string allowedReleasesRoot,
        string recoveryReceiptPath,
        out string releasesRoot,
        out string receiptPath,
        out string detail)
    {
        releasesRoot = "";
        receiptPath = "";
        detail = "config";
        if (string.IsNullOrWhiteSpace(allowedReleasesRoot) || string.IsNullOrWhiteSpace(recoveryReceiptPath))
            return false;
        try
        {
            var lexicalReleases = Path.GetFullPath(allowedReleasesRoot);
            var lexicalReceipt = Path.GetFullPath(recoveryReceiptPath);
            if (!TryCanonicalize(lexicalReleases, out var canonicalReleases, out _))
            {
                detail = "releases";
                return false;
            }

            if (!TryGetAttributes(canonicalReleases, out var releaseAttributes)
                || (releaseAttributes & FileAttributes.Directory) == 0
                || (releaseAttributes & FileAttributes.ReparsePoint) != 0)
            {
                detail = "releases";
                return false;
            }

            if (!TryCanonicalize(lexicalReceipt, out var canonicalReceipt, out var receiptLeafReparse))
            {
                detail = "receipt-link";
                return false;
            }

            if (receiptLeafReparse)
            {
                detail = "receipt-link";
                return false;
            }

            if (IsInside(canonicalReleases, canonicalReceipt))
            {
                detail = "receipt-root";
                return false;
            }

            var parent = Path.GetDirectoryName(canonicalReceipt);
            if (string.IsNullOrEmpty(parent)
                || !TryGetAttributes(parent, out var parentAttributes)
                || (parentAttributes & FileAttributes.Directory) == 0)
            {
                detail = "receipt-parent";
                return false;
            }

            releasesRoot = canonicalReleases;
            receiptPath = canonicalReceipt;
            detail = "";
            return true;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            detail = "path";
            return false;
        }
    }

    static bool TryCanonicalize(string fullPath, out string canonical, out bool leafIsReparse)
    {
        var hops = 32;
        return TryWalk(fullPath, ref hops, out canonical, out leafIsReparse);
    }

    static bool TryWalk(string fullPath, ref int hops, out string canonical, out bool leafIsReparse)
    {
        canonical = "";
        leafIsReparse = false;
        string rooted;
        try
        {
            rooted = Path.GetFullPath(fullPath);
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return false;
        }

        var root = Path.GetPathRoot(rooted);
        if (string.IsNullOrEmpty(root))
            return false;
        var segments = rooted[root.Length..].Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries);
        var current = root;
        for (var index = 0; index < segments.Length; index++)
        {
            string next;
            try
            {
                next = Path.Combine(current, segments[index]);
            }
            catch (Exception ex) when (IsOperational(ex))
            {
                return false;
            }

            if (!TryGetAttributes(next, out var attributes))
            {
                for (var rest = index + 1; rest < segments.Length; rest++)
                {
                    try
                    {
                        next = Path.Combine(next, segments[rest]);
                    }
                    catch (Exception ex) when (IsOperational(ex))
                    {
                        return false;
                    }
                }

                try
                {
                    canonical = Path.GetFullPath(next);
                }
                catch (Exception ex) when (IsOperational(ex))
                {
                    return false;
                }

                return true;
            }

            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                if (hops <= 0)
                    return false;
                hops--;
                if (!TryReadLinkTarget(next, out var target))
                    return false;
                if (!TryWalk(target, ref hops, out var resolved, out _))
                    return false;
                if (index == segments.Length - 1)
                    leafIsReparse = true;
                current = resolved;
                continue;
            }

            current = next;
        }

        try
        {
            canonical = Path.GetFullPath(current);
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return false;
        }

        return true;
    }

    static bool TryReadLinkTarget(string path, out string target)
    {
        target = "";
        try
        {
            if (!TryGetAttributes(path, out var attributes))
                return false;
            FileSystemInfo info = (attributes & FileAttributes.Directory) != 0
                ? new DirectoryInfo(path)
                : new FileInfo(path);
            var link = info.ResolveLinkTarget(returnFinalTarget: false);
            if (link is null || string.IsNullOrWhiteSpace(link.FullName))
                return false;
            target = Path.GetFullPath(link.FullName);
            return true;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return false;
        }
    }

    static bool TryMap(string releasesRoot, string relative, out string contentRoot)
    {
        contentRoot = "";
        if (relative == ".")
        {
            contentRoot = Path.GetFullPath(releasesRoot);
            return true;
        }

        if (!IsSafeRelative(relative))
            return false;
        var full = Path.GetFullPath(releasesRoot);
        foreach (var segment in relative.Split('/'))
            full = Path.Combine(full, segment);
        full = Path.GetFullPath(full);
        if (!IsInside(releasesRoot, full))
            return false;
        contentRoot = full;
        return true;
    }

    static string? Relative(string releasesRoot, string contentRoot)
    {
        var relative = Path.GetRelativePath(Path.GetFullPath(releasesRoot), Path.GetFullPath(contentRoot));
        if (relative == ".")
            return ".";
        relative = relative.Replace(Path.DirectorySeparatorChar, '/').Replace(Path.AltDirectorySeparatorChar, '/');
        return IsSafeRelative(relative) ? relative : null;
    }

    static bool IsSafeRelative(string? relative)
    {
        if (string.IsNullOrEmpty(relative) || relative.Length > TrustedRelease.MaxPathLength)
            return false;
        if (relative[0] == '/' || relative[relative.Length - 1] == '/')
            return false;
        foreach (var segment in relative.Split('/'))
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

    static bool IsInside(string root, string path)
    {
        var full = Path.GetFullPath(path);
        var baseDir = Path.GetFullPath(root);
        if (SamePath(full, baseDir))
            return true;
        var prefix = baseDir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return full.StartsWith(prefix, PlatformPathComparison);
    }

    static StringComparison PlatformPathComparison =>
        OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    static bool SamePath(string left, string right) =>
        string.Equals(left, right, PlatformPathComparison);

    static bool TryGetAttributes(string path, out FileAttributes attributes)
    {
        try
        {
            attributes = File.GetAttributes(path);
            return true;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            attributes = 0;
            return false;
        }
    }

    static void DeleteTemp(string directory, string temp)
    {
        try
        {
            var full = Path.GetFullPath(temp);
            var name = Path.GetFileName(full);
            if (!name.StartsWith("receipt-", StringComparison.Ordinal)
                || !name.EndsWith(".tmp", StringComparison.Ordinal)
                || !IsInside(directory, full)
                || SamePath(full, directory))
                return;
            if (File.Exists(full))
                File.Delete(full);
        }
        catch (Exception ex) when (IsOperational(ex))
        {
        }
    }

    static bool IsOperational(Exception exception) =>
        exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException;

    static TrustedReleaseRecoveryStart Configure(string detail) =>
        new(false, null, TrustedUpdateStartSource.None, 0, detail, Blank(), Blank(), TrustedReleasePersistenceFailure.None, "");

    static TrustedReleaseRecoveryStart Locked(TrustedReleaseRecoveryReason candidate) =>
        new(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Blank(), TrustedReleasePersistenceFailure.None, "");

    static TrustedReleaseRecoveryStart RecoveryLocked(TrustedReleaseRecoveryReason candidate) =>
        new(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Recovery(TrustedReleaseFailure.None, TrustedUpdateFailure.ProcessSelectionLocked, TrustedUpdateFailure.None, "locked"), TrustedReleasePersistenceFailure.None, "");

    static TrustedReleaseRecoveryStart ActivationFailed(TrustedUpdateFailure failure, TrustedReleaseRecoveryReason candidate) =>
        new(false, null, TrustedUpdateStartSource.None, 0, "", candidate with { Activation = failure, Detail = "activation" }, Blank(), TrustedReleasePersistenceFailure.None, "");

    static Attempt Stop(TrustedReleaseRecoveryStart start) => new(true, start);

    static Attempt Continue(TrustedReleaseRecoveryReason candidate) =>
        new(false, new TrustedReleaseRecoveryStart(false, null, TrustedUpdateStartSource.None, 0, "", candidate, Blank(), TrustedReleasePersistenceFailure.None, ""));

    static TrustedReleaseRecoveryReason Candidate(
        TrustedReleaseFailure verification,
        TrustedUpdateFailure plan,
        TrustedUpdateFailure activation,
        string detail) =>
        new(verification, plan, activation, detail);

    static TrustedReleaseRecoveryReason Recovery(
        TrustedReleaseFailure verification,
        TrustedUpdateFailure plan,
        TrustedUpdateFailure activation,
        string detail) =>
        new(verification, plan, activation, detail);

    static TrustedReleaseRecoveryReason Blank() =>
        new(TrustedReleaseFailure.None, TrustedUpdateFailure.None, TrustedUpdateFailure.None, "");

    readonly record struct Attempt(bool Stop, TrustedReleaseRecoveryStart Start);
}

/// <summary>
/// Test-only faults. Production hosts do not set these. A failed persist still
/// means the activator already ran.
/// </summary>
internal static class TrustedReleaseRecoveryDiagnostics
{
    internal static bool FailNextPersist { get; set; }

    internal static Action? BeforeHostStart { get; set; }
}

public sealed class TrustedReleaseOffer
{
    public TrustedReleaseOffer(string contentRoot, ReadOnlyMemory<byte> signedDocument)
    {
        ContentRoot = contentRoot;
        SignedDocument = signedDocument;
    }

    public string ContentRoot { get; }
    public ReadOnlyMemory<byte> SignedDocument { get; }
}

public enum TrustedReleasePersistenceFailure
{
    None = 0,
    IoFailure,
    InvalidPath,
}

public readonly record struct TrustedReleaseRecoveryReason(
    TrustedReleaseFailure Verification,
    TrustedUpdateFailure Plan,
    TrustedUpdateFailure Activation,
    string Detail);

public sealed class TrustedReleaseRecoveryStart
{
    internal TrustedReleaseRecoveryStart(
        bool activated,
        string? selectedVersion,
        TrustedUpdateStartSource source,
        int value,
        string configurationDetail,
        TrustedReleaseRecoveryReason candidate,
        TrustedReleaseRecoveryReason recovery,
        TrustedReleasePersistenceFailure persistence,
        string persistenceDetail)
    {
        Activated = activated;
        SelectedVersion = selectedVersion;
        Source = source;
        Value = value;
        ConfigurationDetail = configurationDetail;
        Candidate = candidate;
        Recovery = recovery;
        Persistence = persistence;
        PersistenceDetail = persistenceDetail;
    }

    public bool Activated { get; }
    public string? SelectedVersion { get; }
    public TrustedUpdateStartSource Source { get; }
    public int Value { get; }
    public string ConfigurationDetail { get; }
    public TrustedReleaseRecoveryReason Candidate { get; }
    public TrustedReleaseRecoveryReason Recovery { get; }
    public TrustedReleasePersistenceFailure Persistence { get; }
    public string PersistenceDetail { get; }
}
