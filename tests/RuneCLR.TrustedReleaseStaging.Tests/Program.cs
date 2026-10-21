using System.Runtime.Loader;
using System.Security.Cryptography;
using RuneCLR.TrustedUpdate;

var failures = 0;
var tests = new (string Name, Func<Task> Run)[]
{
    ("A signed payload publishes final paths that Plan can rehash", SuccessFeedsPlan),
    ("An oversized SPKI does not open a stream or create a directory", OversizedSpki),
    ("An open callback cannot replace the validated source snapshot", SnapshotIgnoresListMutation),
    ("Cancellation before publish does not create the final directory", CanceledBeforeOpen),
    ("Cancellation after the bytes are copied does not publish", CanceledBeforeCommit),
    ("The final directory stays absent while the first read is paused", PausedReadDoesNotPublish),
    ("An existing final directory is left unchanged", ExistingFinalStays),
    ("A missing signed file does not publish", MissingFile),
    ("An extra unsigned file does not publish", ExtraFile),
    ("The wrong key does not publish", WrongKey),
    ("Changed bytes do not publish", TamperedBytes),
    ("An empty stream does not publish", IncompleteStream),
    ("A stream that throws does not publish", StreamThrows),
    ("A seekable stream over the file cap does not copy", SeekableFileCap),
    ("A generated stream over the file cap does not publish", StreamingFileCap),
    ("Duplicate and case-conflicting paths are rejected before open", RejectedPaths),
    ("Opened streams are disposed", StreamsDisposed),
};
foreach (var (name, run) in tests)
{
    try
    {
        await run();
        Console.WriteLine("PASS " + name);
    }
    catch (Exception exception)
    {
        failures++;
        Console.Error.WriteLine("FAIL " + name + ": " + exception);
    }
}

Console.WriteLine((tests.Length - failures) + "/" + tests.Length + " tests passed");
return failures == 0 ? 0 : 1;

static async Task SuccessFeedsPlan()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()), ("Data/Notes.txt", noteBytes()));
    using (signed.Key)
    {
        var entryStream = new ByteStream(entryBytes());
        var noteStream = new ByteStream(noteBytes());
        var before = AssemblyLoadContext.All.Count();
        var result = await TrustedReleaseStaging.PublishAsync(
            workspace.Final,
            signed.Document,
            signed.Spki,
            new[]
            {
                StageSources.From("Game.dll", entryStream),
                StageSources.From("Data/Notes.txt", noteStream),
            });
        Check(result.Succeeded, Result(result));
        Check(result.FinalDirectory == Path.GetFullPath(workspace.Final), result.FinalDirectory ?? "");
        Check(result.Candidate is not null && result.Approval is not null, "missing candidate");
        var candidate = result.Candidate!;
        var approval = result.Approval!;
        Check(Under(result.FinalDirectory!, candidate.AssemblyPath), candidate.AssemblyPath);
        Check(!Path.GetRelativePath(result.FinalDirectory!, candidate.AssemblyPath).Contains("runeclr-stage-", StringComparison.Ordinal), candidate.AssemblyPath);
        Check(candidate.AdditionalContent is not null && candidate.AdditionalContent.Count == 1, "additional");
        var extra = candidate.AdditionalContent![0];
        Check(Under(result.FinalDirectory!, extra.Path), extra.Path);
        Check(extra.ContentSha256.Length == 64, "extra hash");
        Check(File.ReadAllBytes(candidate.AssemblyPath).AsSpan().SequenceEqual(entryBytes()), "entry bytes");
        Check(File.ReadAllBytes(extra.Path).AsSpan().SequenceEqual(noteBytes()), "note bytes");
        Check(approval.ContentSha256 == candidate.ContentSha256, "approval hash");
        Check(approval.VersionName == candidate.VersionName, "approval version");
        var plan = new TrustedUpdateProcess().TryPlanCandidate(
            candidate,
            new TrustedUpdateTarget("net11.0", "x64"),
            approval,
            result.FinalDirectory!);
        Check(plan.Succeeded && plan.SelectedVersionName == "1.0.0", plan.Failure.ToString());
        Check(AssemblyLoadContext.All.Count() == before, "plan loaded an assembly");
        Check(entryStream.Disposed && noteStream.Disposed, "streams");
        CheckNoStage(workspace);
        CheckKeep(workspace);
        Check(!File.Exists(Path.Combine(workspace.Parent, "last-known-good.json")), "lkg");
    }
}

static async Task OversizedSpki()
{
    using var workspace = new Workspace();
    var opened = false;
    var before = Directory.GetFileSystemEntries(workspace.Parent).OrderBy(item => item, StringComparer.Ordinal).ToArray();
    var result = await TrustedReleaseStaging.PublishAsync(
        workspace.Final,
        new byte[] { 1 },
        new byte[TrustedRelease.SpkiBytes + 1],
        new[] { new TrustedReleaseStageSource("Game.dll", _ => { opened = true; return ValueTask.FromResult<Stream>(new ByteStream(entryBytes())); }) });
    Check(result.Failure == TrustedReleaseStageFailure.VerificationFailed, Result(result));
    Check(result.VerificationFailure == TrustedReleaseFailure.UntrustedKey && result.Detail == "spki", Result(result));
    Check(!opened, "opened");
    Check(!Directory.Exists(workspace.Final), "final");
    var after = Directory.GetFileSystemEntries(workspace.Parent).OrderBy(item => item, StringComparer.Ordinal).ToArray();
    Check(before.SequenceEqual(after, StringComparer.Ordinal), "directory created");
    CheckNoStage(workspace);
    CheckKeep(workspace);
}

static async Task SnapshotIgnoresListMutation()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var sources = new List<TrustedReleaseStageSource>();
        var stream = new ByteStream(entryBytes());
        sources.Add(StageSources.From("Game.dll", _ =>
        {
            sources.Clear();
            sources.Add(StageSources.From("Evil.dll", new ByteStream(noteBytes())));
            return ValueTask.FromResult<Stream>(stream);
        }));
        var result = await TrustedReleaseStaging.PublishAsync(workspace.Final, signed.Document, signed.Spki, sources);
        Check(result.Succeeded, Result(result));
        Check(result.Candidate is not null && Under(result.FinalDirectory!, result.Candidate.AssemblyPath), result.Candidate?.AssemblyPath ?? "");
        Check(result.Candidate!.AssemblyPath.EndsWith("Game.dll", StringComparison.Ordinal), result.Candidate.AssemblyPath);
        Check(File.ReadAllBytes(result.Candidate.AssemblyPath).AsSpan().SequenceEqual(entryBytes()), "bytes");
        Check(!File.Exists(Path.Combine(workspace.Final, "Evil.dll")), "evil published");
        Check(stream.Disposed, "disposed");
        CheckNoStage(workspace);
    }
}

static async Task CanceledBeforeOpen()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    using (var cancel = new CancellationTokenSource())
    {
        cancel.Cancel();
        var opened = false;
        var result = await TrustedReleaseStaging.PublishAsync(
            workspace.Final,
            signed.Document,
            signed.Spki,
            new[] { new TrustedReleaseStageSource("Game.dll", _ => { opened = true; return ValueTask.FromResult<Stream>(new ByteStream(entryBytes())); }) },
            cancel.Token);
        Check(result.Failure == TrustedReleaseStageFailure.Canceled, Result(result));
        Check(!opened, "opened");
        Check(!Directory.Exists(workspace.Final), "final");
        CheckNoStage(workspace);
        CheckKeep(workspace);
    }
}

static async Task CanceledBeforeCommit()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    using (var cancel = new CancellationTokenSource())
    {
        var stream = new CancelOnEndStream(entryBytes(), cancel);
        var result = await TrustedReleaseStaging.PublishAsync(
            workspace.Final,
            signed.Document,
            signed.Spki,
            new[] { StageSources.From("Game.dll", stream) },
            cancel.Token);
        Check(result.Failure == TrustedReleaseStageFailure.Canceled, Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        Check(stream.Disposed, "disposed");
        CheckNoStage(workspace);
        CheckKeep(workspace);
    }
}

static async Task PausedReadDoesNotPublish()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var stream = new GateStream(entryBytes(), entered, release);
        var publishing = TrustedReleaseStaging.PublishAsync(workspace.Final, signed.Document, signed.Spki, new[] { StageSources.From("Game.dll", stream) }).AsTask();
        var finished = await Task.WhenAny(publishing, entered.Task, Task.Delay(TimeSpan.FromSeconds(10)));
        Check(finished == entered.Task, "first read was not reached");
        Check(!Directory.Exists(workspace.Final), "final appeared during the read");
        release.TrySetResult();
        var result = await publishing;
        Check(result.Succeeded, Result(result));
        Check(Directory.Exists(workspace.Final), "final missing");
        Check(stream.Disposed, "disposed");
        CheckNoStage(workspace);
    }
}

static async Task ExistingFinalStays()
{
    using var workspace = new Workspace();
    Directory.CreateDirectory(workspace.Final);
    var marker = Path.Combine(workspace.Final, "marker.txt");
    File.WriteAllBytes(marker, entryBytes());
    var opened = false;
    var result = await TrustedReleaseStaging.PublishAsync(
        workspace.Final,
        new byte[] { 1 },
        new byte[TrustedRelease.SpkiBytes],
        new[] { new TrustedReleaseStageSource("Game.dll", _ => { opened = true; return ValueTask.FromResult<Stream>(new ByteStream(noteBytes())); }) });
    Check(result.Failure == TrustedReleaseStageFailure.DestinationExists, Result(result));
    Check(!opened, "opened");
    Check(File.ReadAllBytes(marker).AsSpan().SequenceEqual(entryBytes()), "marker changed");
    CheckNoStage(workspace);
    CheckKeep(workspace);
}

static async Task MissingFile()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()), ("Data/Notes.txt", noteBytes()));
    using (signed.Key)
    {
        var stream = new ByteStream(entryBytes());
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", stream));
        Check(result.Failure == TrustedReleaseStageFailure.VerificationFailed, Result(result));
        Check(result.VerificationFailure == TrustedReleaseFailure.ContentMismatch, Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        Check(stream.Disposed, "disposed");
        CheckNoStage(workspace);
    }
}

static async Task ExtraFile()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", entryBytes()), StageSources.From("Evil.txt", noteBytes()));
        Check(result.Failure == TrustedReleaseStageFailure.InventoryMismatch, Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        Check(!File.Exists(Path.Combine(workspace.Parent, "Evil.txt")), "evil left behind");
        CheckNoStage(workspace);
    }
}

static async Task WrongKey()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    using (var other = ECDsa.Create(ECCurve.NamedCurves.nistP256))
    {
        var result = await TrustedReleaseStaging.PublishAsync(
            workspace.Final,
            signed.Document,
            other.ExportSubjectPublicKeyInfo(),
            new[] { StageSources.From("Game.dll", entryBytes()) });
        Check(result.Failure == TrustedReleaseStageFailure.VerificationFailed, Result(result));
        Check(result.VerificationFailure == TrustedReleaseFailure.InvalidSignature, Result(result));
        Check(result.Candidate is null && result.Approval is null, "candidate");
        Check(!Directory.Exists(workspace.Final), "final");
        CheckNoStage(workspace);
    }
}

static async Task TamperedBytes()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var tampered = entryBytes().ToArray();
        tampered[0] ^= 0x01;
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", tampered));
        Check(result.Failure == TrustedReleaseStageFailure.VerificationFailed, Result(result));
        Check(result.VerificationFailure == TrustedReleaseFailure.ContentMismatch, Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        CheckNoStage(workspace);
    }
}

static async Task IncompleteStream()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", Array.Empty<byte>()));
        Check(result.Failure == TrustedReleaseStageFailure.VerificationFailed, Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        CheckNoStage(workspace);
    }
}

static async Task StreamThrows()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()));
    using (signed.Key)
    {
        var stream = new ThrowingStream();
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", stream));
        Check(result.Failure == TrustedReleaseStageFailure.IoFailure && result.Detail == "read", Result(result));
        Check(!Directory.Exists(workspace.Final), "final");
        Check(stream.Disposed, "disposed");
        CheckNoStage(workspace);
        Check(!result.Detail.Contains("Exception", StringComparison.Ordinal), result.Detail);
    }
}

static async Task SeekableFileCap()
{
    using var workspace = new Workspace();
    var stream = new DeclaredLengthStream(TrustedReleaseStaging.MaxFileBytes + 1);
    var result = await TrustedReleaseStaging.PublishAsync(
        workspace.Final,
        new byte[] { 1 },
        new byte[TrustedRelease.SpkiBytes],
        new[] { StageSources.From("Game.dll", stream) });
    Check(result.Failure == TrustedReleaseStageFailure.LimitExceeded && result.Detail == "file-size", Result(result));
    Check(stream.Reads == 0, "read " + stream.Reads);
    Check(stream.Disposed, "disposed");
    Check(!Directory.Exists(workspace.Final), "final");
    CheckNoStage(workspace);
}

static async Task StreamingFileCap()
{
    using var workspace = new Workspace();
    var stream = new BoundedZeroStream(TrustedReleaseStaging.MaxFileBytes + 4096);
    var result = await TrustedReleaseStaging.PublishAsync(
        workspace.Final,
        new byte[] { 1 },
        new byte[TrustedRelease.SpkiBytes],
        new[] { StageSources.From("Game.dll", stream) });
    Check(result.Failure == TrustedReleaseStageFailure.LimitExceeded && result.Detail == "file-size", Result(result));
    Check(stream.Served <= TrustedReleaseStaging.MaxFileBytes + TrustedReleaseStaging.CopyBufferBytes, "served " + stream.Served);
    Check(!Directory.Exists(workspace.Final), "final");
    Check(stream.Disposed, "disposed");
    CheckNoStage(workspace);
}

static async Task RejectedPaths()
{
    using var workspace = new Workspace();
    await Reject(workspace, TrustedReleaseStageFailure.DuplicatePath, "Game.dll", "Game.dll");
    await Reject(workspace, TrustedReleaseStageFailure.CaseConflict, "Game.dll", "game.dll");
    await Reject(workspace, TrustedReleaseStageFailure.InvalidPath, "../Game.dll");
    await Reject(workspace, TrustedReleaseStageFailure.InvalidPath, "dir\\Game.dll");
    var many = new TrustedReleaseStageSource[TrustedReleaseStaging.MaxFiles + 1];
    for (var i = 0; i < many.Length; i++)
        many[i] = new TrustedReleaseStageSource("f" + i + ".bin", _ => throw new InvalidOperationException("opened"));
    var limited = await TrustedReleaseStaging.PublishAsync(workspace.Final, new byte[] { 1 }, new byte[TrustedRelease.SpkiBytes], many);
    Check(limited.Failure == TrustedReleaseStageFailure.LimitExceeded && limited.Detail == "files", Result(limited));
    Check(!Directory.Exists(workspace.Final), "final");
    CheckNoStage(workspace);
    CheckKeep(workspace);
}

static async Task StreamsDisposed()
{
    using var workspace = new Workspace();
    var signed = Sign(workspace, ("Game.dll", entryBytes()), ("Data/Notes.txt", noteBytes()));
    using (signed.Key)
    {
        var first = new ByteStream(entryBytes());
        var second = new ByteStream(noteBytes());
        var result = await Publish(workspace, signed, StageSources.From("Game.dll", first), StageSources.From("Data/Notes.txt", second));
        Check(result.Succeeded, Result(result));
        Check(first.Disposed && second.Disposed, "disposed");
    }
}

static async Task Reject(Workspace workspace, TrustedReleaseStageFailure expected, params string[] paths)
{
    var sources = paths.Select(path => new TrustedReleaseStageSource(path, _ => throw new InvalidOperationException("opened"))).ToArray();
    var result = await TrustedReleaseStaging.PublishAsync(workspace.Final, new byte[] { 1 }, new byte[TrustedRelease.SpkiBytes], sources);
    Check(result.Failure == expected, Result(result));
    Check(!Directory.Exists(workspace.Final), "final");
    CheckNoStage(workspace);
}

static async Task<TrustedReleaseStageResult> Publish(Workspace workspace, SignedRelease signed, params TrustedReleaseStageSource[] sources) =>
    await TrustedReleaseStaging.PublishAsync(workspace.Final, signed.Document, signed.Spki, sources);



static SignedRelease Sign(Workspace workspace, params (string Path, byte[] Bytes)[] files)
{
    foreach (var (path, bytes) in files)
        File.WriteAllBytes(workspace.SourceFile(path), bytes);
    var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
    var signed = TrustedRelease.Sign(workspace.Source, Identity(), files.Select(file => file.Path).ToArray(), key);
    if (!signed.Succeeded || signed.Document is null)
        throw new InvalidOperationException("sign " + signed.Failure + " " + signed.Detail);
    return new SignedRelease(signed.Document, key.ExportSubjectPublicKeyInfo(), key);
}

static TrustedReleaseIdentity Identity() =>
    new("1.0.0", "net11.0", "x64", "Game.Entry", "Activate", "Game.dll");

static byte[] entryBytes() => "game-bytes-v1"u8.ToArray();
static byte[] noteBytes() => "notes-v1"u8.ToArray();

static bool Under(string root, string path)
{
    var full = Path.GetFullPath(path);
    var prefix = Path.GetFullPath(root) + Path.DirectorySeparatorChar;
    if (!full.StartsWith(prefix, StringComparison.Ordinal))
        return false;
    return !full.Substring(prefix.Length).Contains("runeclr-stage-", StringComparison.Ordinal);
}

static void CheckNoStage(Workspace workspace)
{
    foreach (var entry in Directory.EnumerateFileSystemEntries(workspace.Parent))
        Check(!Path.GetFileName(entry).StartsWith("runeclr-stage-", StringComparison.Ordinal), entry);
}

static void CheckKeep(Workspace workspace) =>
    Check(File.ReadAllText(Path.Combine(workspace.Parent, "keep", "keep.txt")) == "keep", "keep");

static string Result(TrustedReleaseStageResult result) =>
    result.Failure + " " + result.VerificationFailure + " " + result.Detail;

static void Check(bool condition, string message)
{
    if (!condition)
        throw new InvalidOperationException(message);
}


static class StageSources
{
    public static TrustedReleaseStageSource From(string path, byte[] bytes) => From(path, new ByteStream(bytes));

    public static TrustedReleaseStageSource From(string path, Stream stream) =>
        new(path, _ => ValueTask.FromResult(stream));

    public static TrustedReleaseStageSource From(string path, Func<CancellationToken, ValueTask<Stream>> open) =>
        new(path, open);
}
sealed class Workspace : IDisposable
{
    public Workspace()
    {
        Root = Path.Combine(Path.GetTempPath(), "runeclr-stage-test-" + Guid.NewGuid().ToString("n"));
        Parent = Path.Combine(Root, "parent");
        Source = Path.Combine(Root, "source");
        Final = Path.Combine(Parent, "publish");
        Directory.CreateDirectory(Parent);
        Directory.CreateDirectory(Source);
        Directory.CreateDirectory(Path.Combine(Parent, "keep"));
        File.WriteAllText(Path.Combine(Parent, "keep", "keep.txt"), "keep");
    }

    public string Root { get; }
    public string Parent { get; }
    public string Source { get; }
    public string Final { get; }

    public string SourceFile(string relative)
    {
        var directory = Source;
        var segments = relative.Split('/');
        for (var i = 0; i < segments.Length - 1; i++)
            directory = Path.Combine(directory, segments[i]);
        Directory.CreateDirectory(directory);
        return Path.Combine(directory, segments[^1]);
    }

    public void Dispose()
    {
        if (Directory.Exists(Root))
            Directory.Delete(Root, recursive: true);
    }
}

sealed record SignedRelease(byte[] Document, byte[] Spki, ECDsa Key);

class ByteStream : Stream
{
    readonly byte[] data;
    int offset;
    public bool Disposed;
    public ByteStream(byte[] data) => this.data = data;
    public override bool CanRead => true;
    public override bool CanSeek => true;
    public override bool CanWrite => false;
    public override long Length => data.Length;
    public override long Position { get => offset; set => offset = (int)value; }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
    public override int Read(Span<byte> buffer)
    {
        var count = Math.Min(buffer.Length, data.Length - offset);
        data.AsSpan(offset, count).CopyTo(buffer);
        offset += count;
        return count;
    }
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(Read(buffer.Span));
    }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override ValueTask DisposeAsync()
    {
        Disposed = true;
        return ValueTask.CompletedTask;
    }
    protected override void Dispose(bool disposing)
    {
        Disposed = true;
        base.Dispose(disposing);
    }
}

sealed class GateStream : ByteStream
{
    readonly TaskCompletionSource entered;
    readonly TaskCompletionSource release;
    int armed = 1;
    public GateStream(byte[] data, TaskCompletionSource entered, TaskCompletionSource release) : base(data)
    {
        this.entered = entered;
        this.release = release;
    }
    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
    {
        if (Interlocked.Exchange(ref armed, 0) == 1)
        {
            entered.TrySetResult();
            await release.Task.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        return Read(buffer.Span);
    }
}

sealed class CancelOnEndStream : ByteStream
{
    readonly CancellationTokenSource cancel;
    public CancelOnEndStream(byte[] data, CancellationTokenSource cancel) : base(data) => this.cancel = cancel;
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
    {
        var read = Read(buffer.Span);
        if (read == 0)
            cancel.Cancel();
        return ValueTask.FromResult(read);
    }
}

sealed class ThrowingStream : Stream
{
    public bool Disposed;
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count) => throw new IOException("read-failed");
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) =>
        ValueTask.FromException<int>(new IOException("read-failed"));
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
}

sealed class DeclaredLengthStream : Stream
{
    public int Reads;
    public bool Disposed;
    readonly long length;
    public DeclaredLengthStream(long length) => this.length = length;
    public override bool CanRead => true;
    public override bool CanSeek => true;
    public override bool CanWrite => false;
    public override long Length => length;
    public override long Position { get; set; }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count) { Reads++; return 0; }
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
    {
        Reads++;
        return ValueTask.FromResult(0);
    }
    public override long Seek(long offset, SeekOrigin origin) => 0;
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
}

sealed class BoundedZeroStream : Stream
{
    long remaining;
    public long Served;
    public bool Disposed;
    public BoundedZeroStream(long bytes) => remaining = bytes;
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
    public override int Read(Span<byte> buffer)
    {
        if (remaining == 0)
            return 0;
        var count = (int)Math.Min(buffer.Length, remaining);
        remaining -= count;
        Served += count;
        buffer[..count].Clear();
        return count;
    }
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult(Read(buffer.Span));
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    public override ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
}
