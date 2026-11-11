using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace RuneCLR.IpadDelivery;

/// <summary>
/// Bounded HTTP fetch for a release document or one signed content file. The deadline covers
/// headers AND the whole body; caller cancellation is honoured; every response is disposed on
/// every path; redirects are refused instead of followed.
/// </summary>
public static class BoundedHttpFetch
{
    private static readonly HttpClient Client = CreateClient();

    private static HttpClient CreateClient() => new(new SocketsHttpHandler
    {
        AllowAutoRedirect = false,
        AutomaticDecompression = DecompressionMethods.None,
    })
    {
        Timeout = Timeout.InfiniteTimeSpan, // the per-download deadline below is the only timeout
    };

    public static async ValueTask<byte[]> DownloadAsync(Uri uri, int maxBytes, TimeSpan deadline, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(uri);
        if (maxBytes <= 0) throw new ArgumentOutOfRangeException(nameof(maxBytes));
        if (deadline <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(deadline));

        using var scope = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        scope.CancelAfter(deadline);
        using var response = await Client
            .GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, scope.Token)
            .ConfigureAwait(false);

        var code = (int)response.StatusCode;
        if (code is >= 300 and < 400) throw new IOException("redirect-refused");
        if (!response.IsSuccessStatusCode) throw new IOException("http-status-" + code);

        using var body = await response.Content.ReadAsStreamAsync(scope.Token).ConfigureAwait(false);
        using var buffer = new MemoryStream();
        var chunk = new byte[80 * 1024];
        while (true)
        {
            int read = await body.ReadAsync(chunk.AsMemory(0, chunk.Length), scope.Token).ConfigureAwait(false);
            if (read == 0) break;
            if (buffer.Length + read > maxBytes) throw new IOException("download-too-large");
            buffer.Write(chunk, 0, read);
        }
        return buffer.ToArray();
    }
}

