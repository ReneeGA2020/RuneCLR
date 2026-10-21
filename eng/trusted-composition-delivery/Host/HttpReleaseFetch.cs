using System.Diagnostics;
using RuneCLR.TrustedUpdate;
using System.Net;
using System.Net.Sockets;

// TrustedReleaseStaging.IsOperational does not treat HttpRequestException as an
// IO failure, and its finally only disposes streams returned to PublishAsync.
// This adapter therefore converts expected HTTP failures to IOException, lets
// OperationCanceledException through unchanged, and disposes any response that
// never becomes a returned stream.
// Each document fetch and each payload Open keeps its own DownloadDeadline
// across SendAsync and the later body reads. HttpClient.Timeout is not that
// read deadline: the reviewed runtime source disposes SendAsync's temporary
// timeout once ResponseHeadersRead returns. This comment is not a measurement
// of the installed framework.

static class HttpReleaseFetch
{
    public static readonly TimeSpan DownloadDeadline = TimeSpan.FromSeconds(2);
    static readonly HttpClient Client = CreateClient();
    static Dictionary<string, string>? map;
    static FetchStats? stats;
    static CancellationTokenSource? cancel;

    public static bool IsBound => map is not null;

    public static bool Bind(Dictionary<string, string> request)
    {
        map = request;
        stats = new FetchStats();
        cancel = new CancellationTokenSource();
        Console.WriteLine("HTTP_DEADLINE_MS " + (int)DownloadDeadline.TotalMilliseconds + " scope=per-download");
        if (request.TryGetValue("stallFile", out var stall) && stall.Length > 0)
        {
            var signal = stall;
            var source = cancel;
            var watcher = new Thread(() =>
            {
                var started = Environment.TickCount64;
                while (!source.IsCancellationRequested && Environment.TickCount64 - started < 15000)
                {
                    if (File.Exists(signal))
                    {
                        source.Cancel();
                        return;
                    }

                    Thread.Sleep(20);
                }
            });
            watcher.IsBackground = true;
            watcher.Start();
        }

        try
        {
            ReadDocument("documentA");
            ReadDocument("documentB");
            return true;
        }
        catch (OperationCanceledException ex)
        {
            NoteStop();
            Console.WriteLine("HTTP_DOCUMENT OperationCanceledException " + ex.Message);
            return false;
        }
        catch (Exception ex) when (ex is IOException or HttpRequestException)
        {
            Console.WriteLine("HTTP_DOCUMENT " + ex.GetType().Name + " " + ex.Message);
            return false;
        }
    }

    public static void Print()
    {
        if (stats is null)
            return;
        Console.WriteLine("HTTP_FETCH responses=" + stats.Responses + " disposed=" + stats.Disposed + " documentBytes=" + stats.DocumentBytes + " bodyBytes=" + stats.BodyBytes + " redirectsRefused=" + stats.RedirectsRefused + " fileOpens=" + stats.FileOpens);
    }

    public static void Unbind()
    {
        cancel?.Dispose();
        cancel = null;
        map = null;
        stats = null;
    }

    public static bool Stage(Dictionary<string, string> request, string finalKey, string documentKey, string contentKey)
    {
        if (map is null || stats is null || cancel is null)
            return false;
        if (!TrySources(documentKey, contentKey, out var document, out var sources))
            return false;
        TrustedReleaseStageResult staged;
        try
        {
            staged = TrustedReleaseStaging.PublishAsync(request[finalKey], document, File.ReadAllBytes(request["spki"]), sources, cancel.Token).GetAwaiter().GetResult();
        }
        catch (OperationCanceledException)
        {
            NoteStop();
            Console.WriteLine("STAGE " + finalKey + " False Canceled cancel verification=None");
            return false;
        }
        catch (HttpRequestException ex)
        {
            Console.WriteLine("STAGE " + finalKey + " False IoFailure http verification=None");
            Console.WriteLine("HTTP_UNHANDLED_AVOIDED " + ex.GetType().Name);
            return false;
        }

        if (staged.Failure == TrustedReleaseStageFailure.Canceled)
            NoteStop();
        Console.WriteLine("STAGE " + finalKey + " " + staged.Succeeded + " " + staged.Failure + " " + staged.Detail + " verification=" + staged.VerificationFailure);
        return staged.Succeeded;
    }

    static void ReadDocument(string key)
    {
        var bytes = ReadBounded(map![key + "Url"], TrustedRelease.MaxDocumentBytes + 1);
        Directory.CreateDirectory(Path.GetDirectoryName(map[key])!);
        File.WriteAllBytes(map[key], bytes);
        stats!.DocumentBytes += bytes.Length;
    }

    static bool TrySources(string documentKey, string contentKey, out byte[] document, out TrustedReleaseStageSource[] sources)
    {
        document = File.ReadAllBytes(map![documentKey]);
        var filesKey = contentKey == "contentA" ? "filesA" : "filesB";
        var baseKey = contentKey == "contentA" ? "contentBaseA" : "contentBaseB";
        var names = map[filesKey].Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var prefix = map[baseKey];
        sources = names.Select(name => new TrustedReleaseStageSource(name, token => OpenFile(prefix, name, token))).ToArray();
        return sources.Length > 0;
    }

    static async ValueTask<Stream> OpenFile(string prefix, string name, CancellationToken token)
    {
        stats!.FileOpens++;
        DownloadScope? scope = new DownloadScope(token);
        HttpResponseMessage? response = null;
        try
        {
            response = await Send(prefix + name, scope.Token).ConfigureAwait(false);
            var inner = await response.Content.ReadAsStreamAsync(scope.Token).ConfigureAwait(false);
            var stream = new OwnedHttpStream(inner, response, stats, scope);
            response = null;
            scope = null;
            return stream;
        }
        catch (OperationCanceledException)
        {
            NoteStop();
            throw;
        }
        catch (Exception ex)
        {
            if (ex is IOException)
                throw;
            throw new IOException("http-open", ex);
        }
        finally
        {
            if (response is not null)
                DisposeResponse(response);
            scope?.Dispose();
        }
    }

    static byte[] ReadBounded(string url, int cap)
    {
        HttpResponseMessage? response = null;
        try
        {
            using var scope = new DownloadScope(cancel!.Token);
            response = Send(url, scope.Token).GetAwaiter().GetResult();
            using var stream = response.Content.ReadAsStream(scope.Token);
            var buffer = new byte[cap];
            var got = 0;
            while (got < cap)
            {
                var read = stream.ReadAsync(buffer.AsMemory(got, cap - got), scope.Token).GetAwaiter().GetResult();
                if (read == 0)
                    break;
                got += read;
            }

            return buffer[..got];
        }
        catch (OperationCanceledException)
        {
            NoteStop();
            throw;
        }
        catch (Exception ex) when (ex is not IOException)
        {
            throw new IOException("http-document", ex);
        }
        finally
        {
            DisposeResponse(response);
        }
    }

    static void DisposeResponse(HttpResponseMessage? response)
    {
        if (response is null || stats is null)
            return;
        response.Dispose();
        stats.Disposed++;
    }

    static async Task<HttpResponseMessage> Send(string url, CancellationToken token)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        HttpResponseMessage response;
        try
        {
            response = await Client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new IOException("http-send", ex);
        }

        stats!.Responses++;
        var code = (int)response.StatusCode;
        if (code >= 300 && code < 400)
        {
            stats.RedirectsRefused++;
            DisposeResponse(response);
            throw new IOException("redirect " + code);
        }

        if (code != 200)
        {
            Console.WriteLine("HTTP_STATUS " + code);
            DisposeResponse(response);
            throw new IOException("http-status " + code);
        }

        return response;
    }

    static HttpClient CreateClient()
    {
        var handler = new SocketsHttpHandler { AllowAutoRedirect = false, AutomaticDecompression = DecompressionMethods.None };
        return new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(20) };
    }

    sealed class FetchStats
    {
        public int Responses;
        public int Disposed;
        public int DocumentBytes;
        public long BodyBytes;
        public int RedirectsRefused;
        public int FileOpens;
        public bool StopNoted;
        public bool DeadlineExpired;
    }

    sealed class DownloadScope : IDisposable
    {
        readonly CancellationTokenSource deadline = new(DownloadDeadline);
        readonly CancellationTokenSource linked;

        public DownloadScope(CancellationToken caller)
        {
            linked = CancellationTokenSource.CreateLinkedTokenSource(caller, cancel!.Token, deadline.Token);
            deadline.Token.Register(static () =>
            {
                if (stats is not null)
                    stats.DeadlineExpired = true;
            });
        }

        public CancellationToken Token => linked.Token;

        public void Dispose()
        {
            linked.Dispose();
            deadline.Dispose();
        }
    }

    static void NoteStop()
    {
        if (stats is null || stats.StopNoted)
            return;
        stats.StopNoted = true;
        var caller = cancel?.IsCancellationRequested == true;
        var expired = stats.DeadlineExpired;
        var reason = caller ? "caller" : expired ? "deadline" : "unknown";
        Console.WriteLine("HTTP_STOP callerCanceled=" + caller + " deadline=" + (expired ? "expired" : "live") + " reason=" + reason);
    }

    sealed class OwnedHttpStream : Stream
    {
        readonly Stream inner;
        readonly HttpResponseMessage response;
        readonly FetchStats stats;
        readonly DownloadScope scope;
        bool disposed;

        public OwnedHttpStream(Stream inner, HttpResponseMessage response, FetchStats stats, DownloadScope scope)
        {
            this.inner = inner;
            this.response = response;
            this.stats = stats;
            this.scope = scope;
        }

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count)
        {
            return ReadAsync(buffer.AsMemory(offset, count), scope.Token).AsTask().GetAwaiter().GetResult();
        }

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            using var read = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, scope.Token);
            try
            {
                var count = await inner.ReadAsync(buffer, read.Token).ConfigureAwait(false);
                stats.BodyBytes += count;
                return count;
            }
            catch (OperationCanceledException)
            {
                NoteStop();
                throw;
            }
        }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            if (disposed)
                return;
            disposed = true;
            if (disposing)
            {
                inner.Dispose();
                response.Dispose();
                scope.Dispose();
                stats.Disposed++;
            }

            base.Dispose(disposing);
        }
    }
}

static class HttpLoopbackServer
{
    public static int Run(string[] args)
    {
        var root = args[1];
        var portFile = args[2];
        var logFile = args[3];
        var stallFile = args[4];
        var tcp = new TcpListener(IPAddress.Loopback, 0);
        tcp.Start();
        var port = ((IPEndPoint)tcp.LocalEndpoint).Port;
        tcp.Stop();
        var listener = new HttpListener();
        listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
        listener.Start();
        File.WriteAllText(portFile, port.ToString());
        try
        {
            while (listener.IsListening)
            {
                HttpListenerContext context;
                try
                {
                    context = listener.GetContext();
                }
                catch (Exception ex) when (ex is HttpListenerException or ObjectDisposedException or InvalidOperationException)
                {
                    break;
                }

                long sent = 0;
                try
                {
                    sent = Serve(context, root, stallFile, logFile);
                }
                catch (Exception ex)
                {
                    File.AppendAllText(logFile, "REQ error path=" + context.Request.RawUrl + " " + ex.GetType().Name + Environment.NewLine);
                }
            }
        }
        finally
        {
            listener.Close();
        }

        return 0;
    }

    static long Serve(HttpListenerContext context, string root, string stallFile, string logFile)
    {
        var path = context.Request.Url?.AbsolutePath ?? "/";
        var response = context.Response;
        long sent = 0;
        try
        {
            if (path.Contains("..", StringComparison.Ordinal))
            {
                response.StatusCode = 400;
                return 0;
            }

            var relative = path.TrimStart('/').Replace('/', Path.DirectorySeparatorChar);
            var kind = "file";
            var eofPrefix = "eof" + Path.DirectorySeparatorChar;
            var stallPrefix = "stall" + Path.DirectorySeparatorChar;
            var holdPrefix = "hold" + Path.DirectorySeparatorChar;
            var missingPrefix = "missing" + Path.DirectorySeparatorChar;
            if (relative.StartsWith(eofPrefix, StringComparison.OrdinalIgnoreCase))
            {
                kind = "eof";
                relative = relative[eofPrefix.Length..];
            }
            else if (relative.StartsWith(stallPrefix, StringComparison.OrdinalIgnoreCase))
            {
                kind = "stall";
                relative = relative[stallPrefix.Length..];
            }
            else if (relative.StartsWith(holdPrefix, StringComparison.OrdinalIgnoreCase))
            {
                kind = "hold";
                relative = relative[holdPrefix.Length..];
            }
            else if (relative.StartsWith(missingPrefix, StringComparison.OrdinalIgnoreCase))
            {
                response.StatusCode = 404;
                File.AppendAllText(logFile, "REQ path=" + path + " status=404 sent=0" + Environment.NewLine);
                return 0;
            }

            var fullRoot = Path.GetFullPath(root);
            var full = Path.GetFullPath(Path.Combine(root, relative));
            if (!full.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
            {
                response.StatusCode = 404;
                return 0;
            }

            var data = File.ReadAllBytes(full);
            if (kind == "eof")
            {
                response.StatusCode = 200;
                response.ContentLength64 = data.Length + 32;
                response.SendChunked = false;
                var count = Math.Max(1, data.Length / 2);
                try
                {
                    response.OutputStream.Write(data, 0, count);
                    response.OutputStream.Flush();
                    response.Abort();
                }
                catch (Exception)
                {
                }

                File.AppendAllText(logFile, "REQ path=" + path + " status=200 sent=" + count + " declared=" + (data.Length + 32) + " early=true" + Environment.NewLine);
                return count;
            }

            if (kind == "stall")
            {
                response.SendChunked = true;
                response.OutputStream.Write(data, 0, 1);
                response.OutputStream.Flush();
                sent = 1;
                File.WriteAllText(stallFile, "stalled");
                File.AppendAllText(logFile, "REQ path=" + path + " status=200 sent=1 stalled=true" + Environment.NewLine);
                try
                {
                    var offset = 1;
                    while (offset < data.Length)
                    {
                        var count = Math.Min(64, data.Length - offset);
                        response.OutputStream.Write(data, offset, count);
                        response.OutputStream.Flush();
                        sent += count;
                        offset += count;
                        Thread.Sleep(50);
                    }
                }
                catch (Exception)
                {
                    return sent;
                }

                return sent;
            }

            if (kind == "hold")
            {
                response.StatusCode = 200;
                response.SendChunked = true;
                var prefixCount = Math.Min(128, data.Length);
                response.OutputStream.Write(data, 0, prefixCount);
                response.OutputStream.Flush();
                var barrier = Path.Combine(Path.GetDirectoryName(stallFile)!, "prefix.signal");
                File.WriteAllText(barrier, "prefix");
                File.AppendAllText(logFile, "REQ path=" + path + " status=200 sent=" + prefixCount + " hold-prefix=true stalled=true" + Environment.NewLine);
                var until = Environment.TickCount64 + 15000;
                while (Environment.TickCount64 < until)
                    Thread.Sleep(50);
                return prefixCount;
            }

            response.StatusCode = 200;
            response.SendChunked = true;
            response.OutputStream.Write(data);
            response.OutputStream.Flush();
            File.AppendAllText(logFile, "REQ path=" + path + " status=200 sent=" + data.Length + " chunked=true" + Environment.NewLine);
            return data.Length;
        }
        finally
        {
            try { response.OutputStream.Close(); } catch (Exception) { }
            try { response.Close(); } catch (Exception) { }
        }
    }
}
