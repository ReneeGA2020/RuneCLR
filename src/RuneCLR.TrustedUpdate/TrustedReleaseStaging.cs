namespace RuneCLR.TrustedUpdate;

/// <summary>
/// Copies a signed release into a new private stage directory beside the
/// destination, then publishes it with one directory move. Plan checks and
/// <see cref="TrustedRelease.Verify"/> stay in the signing helper. This type
/// does not load author code or write a last-known-good record.
/// Directory.Move is the commit point: after it succeeds this method does not
/// verify or delete the final directory. It does not claim a race-proof
/// snapshot, network authentication, anti-rollback, or a sandbox.
/// </summary>
public static class TrustedReleaseStaging
{
    public const int MaxFiles = TrustedRelease.MaxFiles;
    public const int MaxFileBytes = TrustedRelease.MaxFileBytes;
    public const long MaxTotalBytes = (long)MaxFiles * MaxFileBytes;
    public const int CopyBufferBytes = 80 * 1024;

    public static async ValueTask<TrustedReleaseStageResult> PublishAsync(
        string finalDirectory,
        ReadOnlyMemory<byte> signedDocument,
        ReadOnlyMemory<byte> hostSubjectPublicKeyInfo,
        IReadOnlyList<TrustedReleaseStageSource> files,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(finalDirectory))
            return Fail(TrustedReleaseStageFailure.InvalidRequest, "final");
        if (files is null || files.Count == 0)
            return Fail(TrustedReleaseStageFailure.InvalidRequest, "files");
        if (files.Count > MaxFiles)
            return Fail(TrustedReleaseStageFailure.LimitExceeded, "files");
        if (signedDocument.Length == 0 || signedDocument.Length > TrustedRelease.MaxDocumentBytes)
            return Verify(TrustedReleaseFailure.InvalidDocument, "document-size");
        if (hostSubjectPublicKeyInfo.Length != TrustedRelease.SpkiBytes)
            return Verify(TrustedReleaseFailure.UntrustedKey, "spki");

        var snapshot = new TrustedReleaseStageSource[files.Count];
        for (var i = 0; i < snapshot.Length; i++)
            snapshot[i] = files[i];
        if (!TryValidateSources(snapshot, out var failure, out var detail))
            return Fail(failure, detail);

        string finalFull;
        string parent;
        try
        {
            finalFull = Path.GetFullPath(finalDirectory);
            var directory = Path.GetDirectoryName(finalFull);
            if (string.IsNullOrEmpty(directory))
                return Fail(TrustedReleaseStageFailure.InvalidRequest, "parent");
            parent = directory;
            if (File.Exists(finalFull) || Directory.Exists(finalFull))
                return Fail(TrustedReleaseStageFailure.DestinationExists, "final");
            if (!IsRealParent(parent, out failure, out detail))
                return Fail(failure, detail);
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return Fail(TrustedReleaseStageFailure.InvalidRequest, "path");
        }

        if (cancellationToken.IsCancellationRequested)
            return Fail(TrustedReleaseStageFailure.Canceled, "cancel");

        var document = signedDocument.ToArray();
        var spki = hostSubjectPublicKeyInfo.ToArray();
        var opened = new List<Stream>(snapshot.Length);
        string? stage = null;
        var created = false;
        var streamsDisposed = false;
        async ValueTask DisposeOpened()
        {
            if (streamsDisposed)
                return;
            streamsDisposed = true;
            foreach (var stream in opened)
            {
                try
                {
                    await stream.DisposeAsync().ConfigureAwait(false);
                }
                catch (Exception)
                {
                }
            }
        }

        try
        {
            long declared = 0;
            foreach (var source in snapshot)
            {
                cancellationToken.ThrowIfCancellationRequested();
                Stream stream;
                try
                {
                    stream = await source.Open(cancellationToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return Fail(TrustedReleaseStageFailure.Canceled, "cancel");
                }
                catch (Exception ex) when (IsOperational(ex))
                {
                    return Fail(TrustedReleaseStageFailure.IoFailure, "open");
                }

                if (stream is null)
                    return Fail(TrustedReleaseStageFailure.IoFailure, "stream");
                opened.Add(stream);
                if (!stream.CanSeek)
                    continue;
                long length;
                try
                {
                    length = stream.Length;
                }
                catch (Exception ex) when (IsOperational(ex))
                {
                    return Fail(TrustedReleaseStageFailure.IoFailure, "length");
                }

                if (length < 0 || length > MaxFileBytes)
                    return Fail(TrustedReleaseStageFailure.LimitExceeded, "file-size");
                if (declared > MaxTotalBytes - length)
                    return Fail(TrustedReleaseStageFailure.LimitExceeded, "total-size");
                declared += length;
            }

            stage = Path.Combine(parent, "runeclr-stage-" + Guid.NewGuid().ToString("n"));
            if (File.Exists(stage) || Directory.Exists(stage))
                return Fail(TrustedReleaseStageFailure.PublishFailed, "stage");
            Directory.CreateDirectory(stage);
            created = true;

            var buffer = new byte[CopyBufferBytes];
            long total = 0;
            for (var index = 0; index < snapshot.Length; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var relative = snapshot[index].RelativePath;
                var destination = Combine(stage, relative);
                if (!IsUnder(stage, destination))
                    return Fail(TrustedReleaseStageFailure.InvalidPath, "path");
                var folder = Path.GetDirectoryName(destination);
                if (!string.IsNullOrEmpty(folder))
                    Directory.CreateDirectory(folder);
                var stream = opened[index];
                await using var output = new FileStream(
                    destination,
                    FileMode.CreateNew,
                    FileAccess.Write,
                    FileShare.None,
                    CopyBufferBytes,
                    FileOptions.Asynchronous | FileOptions.SequentialScan);
                long fileBytes = 0;
                while (true)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    int read;
                    try
                    {
                        read = await stream.ReadAsync(buffer.AsMemory(0, buffer.Length), cancellationToken).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        return Fail(TrustedReleaseStageFailure.Canceled, "cancel");
                    }
                    catch (Exception ex) when (IsOperational(ex))
                    {
                        return Fail(TrustedReleaseStageFailure.IoFailure, "read");
                    }

                    if (read == 0)
                        break;
                    if (read < 0 || fileBytes > MaxFileBytes - read)
                        return Fail(TrustedReleaseStageFailure.LimitExceeded, "file-size");
                    if (total > MaxTotalBytes - read)
                        return Fail(TrustedReleaseStageFailure.LimitExceeded, "total-size");
                    try
                    {
                        await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        return Fail(TrustedReleaseStageFailure.Canceled, "cancel");
                    }
                    catch (Exception ex) when (IsOperational(ex))
                    {
                        return Fail(TrustedReleaseStageFailure.IoFailure, "write");
                    }

                    fileBytes += read;
                    total += read;
                }
            }

            await DisposeOpened().ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            var staged = TrustedRelease.Verify(stage, document, spki);
            if (!staged.Succeeded || staged.Candidate is null || staged.Approval is null)
                return Verify(staged.Failure, staged.Detail);
            if (!InventoryMatches(stage, staged.Candidate))
                return Fail(TrustedReleaseStageFailure.InventoryMismatch, "extra");
            if (!TryRetarget(stage, finalFull, staged.Candidate, out var published))
                return Fail(TrustedReleaseStageFailure.PublishFailed, "final-path");
            if (cancellationToken.IsCancellationRequested)
                return Fail(TrustedReleaseStageFailure.Canceled, "cancel");
            if (File.Exists(finalFull) || Directory.Exists(finalFull))
                return Fail(TrustedReleaseStageFailure.DestinationExists, "final");
            try
            {
                // Commit point. The stage directory is now the final directory.
                Directory.Move(stage, finalFull);
            }
            catch (Exception ex) when (IsOperational(ex))
            {
                if (File.Exists(finalFull) || Directory.Exists(finalFull))
                    return Fail(TrustedReleaseStageFailure.DestinationExists, "final");
                return Fail(TrustedReleaseStageFailure.PublishFailed, "move");
            }

            created = false;
            return new TrustedReleaseStageResult(
                TrustedReleaseStageFailure.None,
                "",
                TrustedReleaseFailure.None,
                finalFull,
                published,
                staged.Approval);
        }
        catch (OperationCanceledException)
        {
            return Fail(TrustedReleaseStageFailure.Canceled, "cancel");
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            return Fail(TrustedReleaseStageFailure.IoFailure, "io");
        }
        finally
        {
            await DisposeOpened().ConfigureAwait(false);
            if (created && stage is not null)
                DeleteCreatedStage(parent, stage);
        }
    }

    static bool TryValidateSources(
        IReadOnlyList<TrustedReleaseStageSource> files,
        out TrustedReleaseStageFailure failure,
        out string detail)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var folded = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var source in files)
        {
            if (source is null || source.Open is null)
            {
                failure = TrustedReleaseStageFailure.InvalidRequest;
                detail = "source";
                return false;
            }

            if (!IsCanonicalRelative(source.RelativePath))
            {
                failure = TrustedReleaseStageFailure.InvalidPath;
                detail = "path";
                return false;
            }

            if (!seen.Add(source.RelativePath))
            {
                failure = TrustedReleaseStageFailure.DuplicatePath;
                detail = "duplicate";
                return false;
            }

            if (!folded.Add(source.RelativePath))
            {
                failure = TrustedReleaseStageFailure.CaseConflict;
                detail = "case";
                return false;
            }
        }

        failure = TrustedReleaseStageFailure.None;
        detail = "";
        return true;
    }

    static bool IsCanonicalRelative(string? relative)
    {
        if (string.IsNullOrEmpty(relative) || relative.Length > TrustedRelease.MaxPathLength)
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

    static bool IsRealParent(string parent, out TrustedReleaseStageFailure failure, out string detail)
    {
        try
        {
            var attributes = File.GetAttributes(parent);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                failure = TrustedReleaseStageFailure.InvalidRequest;
                detail = "reparse";
                return false;
            }

            if ((attributes & FileAttributes.Directory) == 0)
            {
                failure = TrustedReleaseStageFailure.InvalidRequest;
                detail = "parent";
                return false;
            }

            failure = TrustedReleaseStageFailure.None;
            detail = "";
            return true;
        }
        catch (FileNotFoundException)
        {
            failure = TrustedReleaseStageFailure.InvalidRequest;
            detail = "parent";
            return false;
        }
        catch (DirectoryNotFoundException)
        {
            failure = TrustedReleaseStageFailure.InvalidRequest;
            detail = "parent";
            return false;
        }
        catch (Exception ex) when (IsOperational(ex))
        {
            failure = TrustedReleaseStageFailure.IoFailure;
            detail = "parent";
            return false;
        }
    }

    static bool InventoryMatches(string root, TrustedUpdateCandidate candidate)
    {
        var expected = ExpectedPaths(candidate);
        var actual = new HashSet<string>(StringComparer.Ordinal);
        foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
        {
            var full = Path.GetFullPath(file);
            if (!IsUnder(root, full))
                return false;
            var attributes = File.GetAttributes(full);
            if ((attributes & (FileAttributes.ReparsePoint | FileAttributes.Directory)) != 0)
                return false;
            if (!actual.Add(full))
                return false;
        }

        return actual.SetEquals(expected);
    }

    static bool TryRetarget(
        string stageRoot,
        string finalRoot,
        TrustedUpdateCandidate staged,
        out TrustedUpdateCandidate retargeted)
    {
        retargeted = null!;
        if (!TryMapToFinal(stageRoot, finalRoot, staged.AssemblyPath, out var entryPath))
            return false;
        IReadOnlyList<TrustedUpdateContentFile>? additional = null;
        if (staged.AdditionalContent is not null)
        {
            var copy = new TrustedUpdateContentFile[staged.AdditionalContent.Count];
            for (var i = 0; i < staged.AdditionalContent.Count; i++)
            {
                var file = staged.AdditionalContent[i];
                if (file is null || string.IsNullOrWhiteSpace(file.Path))
                    return false;
                if (!TryMapToFinal(stageRoot, finalRoot, file.Path, out var path))
                    return false;
                copy[i] = new TrustedUpdateContentFile(path, file.ContentSha256);
            }

            additional = copy;
        }

        retargeted = staged with
        {
            AssemblyPath = entryPath,
            AdditionalContent = additional,
        };
        return true;
    }

    static bool TryMapToFinal(string stageRoot, string finalRoot, string stagedPath, out string finalPath)
    {
        finalPath = "";
        var stagedFull = Path.GetFullPath(stagedPath);
        var stageFull = Path.GetFullPath(stageRoot);
        var finalFull = Path.GetFullPath(finalRoot);
        if (!IsUnder(stageFull, stagedFull))
            return false;
        var relative = Path.GetRelativePath(stageFull, stagedFull);
        if (relative == "."
            || relative == ".."
            || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            || relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal)
            || Path.IsPathRooted(relative))
            return false;
        finalPath = Path.GetFullPath(Path.Combine(finalFull, relative));
        return IsUnder(finalFull, finalPath);
    }

    static HashSet<string> ExpectedPaths(TrustedUpdateCandidate candidate)
    {
        var expected = new HashSet<string>(StringComparer.Ordinal)
        {
            Path.GetFullPath(candidate.AssemblyPath),
        };
        if (candidate.AdditionalContent is not null)
        {
            foreach (var file in candidate.AdditionalContent)
            {
                if (file is null || string.IsNullOrWhiteSpace(file.Path))
                    continue;
                expected.Add(Path.GetFullPath(file.Path));
            }
        }

        return expected;
    }

    static string Combine(string root, string relative)
    {
        var full = root;
        foreach (var segment in relative.Split('/'))
            full = Path.Combine(full, segment);
        return Path.GetFullPath(full);
    }

    static bool IsUnder(string root, string full)
    {
        var relative = Path.GetRelativePath(Path.GetFullPath(root), Path.GetFullPath(full));
        return relative != "."
            && relative != ".."
            && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            && !relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal)
            && !Path.IsPathRooted(relative);
    }

    static void DeleteCreatedStage(string parent, string stage)
    {
        var full = Path.GetFullPath(stage);
        var name = Path.GetFileName(full);
        if (!name.StartsWith("runeclr-stage-", StringComparison.Ordinal) || !IsUnder(parent, full))
            return;
        DeleteTree(full);
    }

    static void DeleteTree(string path)
    {
        try
        {
            if (Directory.Exists(path))
                Directory.Delete(path, recursive: true);
            else if (File.Exists(path))
                File.Delete(path);
        }
        catch (Exception ex) when (IsOperational(ex))
        {
        }
    }

    static bool IsOperational(Exception exception) =>
        exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException;

    static TrustedReleaseStageResult Fail(TrustedReleaseStageFailure failure, string detail) =>
        new(failure, detail, TrustedReleaseFailure.None, null, null, null);

    static TrustedReleaseStageResult Verify(TrustedReleaseFailure failure, string detail) =>
        new(TrustedReleaseStageFailure.VerificationFailed, detail, failure, null, null, null);
}

public enum TrustedReleaseStageFailure
{
    None = 0,
    InvalidRequest,
    InvalidPath,
    DuplicatePath,
    CaseConflict,
    LimitExceeded,
    IoFailure,
    Canceled,
    VerificationFailed,
    InventoryMismatch,
    DestinationExists,
    PublishFailed,
}

public sealed class TrustedReleaseStageSource
{
    public TrustedReleaseStageSource(string relativePath, Func<CancellationToken, ValueTask<Stream>> open)
    {
        RelativePath = relativePath;
        Open = open;
    }

    public string RelativePath { get; }
    public Func<CancellationToken, ValueTask<Stream>> Open { get; }
}

public sealed class TrustedReleaseStageResult
{
    internal TrustedReleaseStageResult(
        TrustedReleaseStageFailure failure,
        string detail,
        TrustedReleaseFailure verificationFailure,
        string? finalDirectory,
        TrustedUpdateCandidate? candidate,
        TrustedUpdateApproval? approval)
    {
        Failure = failure;
        Detail = detail;
        VerificationFailure = verificationFailure;
        FinalDirectory = finalDirectory;
        Candidate = candidate;
        Approval = approval;
    }

    public TrustedReleaseStageFailure Failure { get; }
    public string Detail { get; }
    public TrustedReleaseFailure VerificationFailure { get; }
    public string? FinalDirectory { get; }
    public TrustedUpdateCandidate? Candidate { get; }
    public TrustedUpdateApproval? Approval { get; }
    public bool Succeeded => Failure == TrustedReleaseStageFailure.None;
}
