# One-shot experiment archive transfer

Cindy SSH can execute commands but its bounded stdout is unsuitable for large
binary archives. The [one-shot server](../eng/serve-experiment-artifact.py) exposes
one explicitly named, independently hashed archive over the build-host LAN for
at most 180 seconds. It does not install software, change a firewall, register a
service or persist a restart job. Root coordinates its actual launch and download.

Create the archive and independently compute its SHA256 before invoking the tool:

~~~sh
python3 serve-experiment-artifact.py \
  --root /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr \
  --archive /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/EXACT-ARCHIVE.tar.gz \
  --sha256 VERIFIED-SHA256 \
  --output /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/FRESH-TRANSFER-RECEIPT \
  --bind 172.26.202.95
~~~

127.0.0.1 is also accepted for a local connectivity check. Binding all interfaces
is rejected. The operating system selects an ephemeral port. The archive must
resolve within the explicitly supplied root; startup hashes the opened file and
keeps that same file handle, with no arbitrary path or directory-listing handler.

The private output directory is mode0700. request.json is created owner-only
mode0600 and contains the exact URL, size, SHA256 and a 24-byte random access
token. Read it through Cindy SSH; do not paste the token into shared logs or a
URL. Authentication uses the X-Experiment-Token header and constant-time compare.
Only GET /archive is served. Other paths, duplicate/missing/wrong token headers
and HEAD requests cannot read an archive. Transfer uses HTTP on the explicitly
selected trusted LAN; the temporary token is access control, not transport
encryption. If that network is unsuitable, use an existing authenticated
transport instead of opening this endpoint.

After saving the private request manifest locally, PowerShell7 can download with
proxy bypass and verify before publishing the final artifact:

~~~powershell
$transfer = Get-Content -LiteralPath 'PRIVATE-REQUEST.json' -Raw | ConvertFrom-Json
$destination = 'E:\RuneCLR\artifacts\EXACT-ARCHIVE.tar.gz'
$partial = $destination + '.part'
if ((Test-Path -LiteralPath $destination) -or (Test-Path -LiteralPath $partial)) {
    throw 'Use fresh destination and .part paths.'
}
$headers = @{ $transfer.header = $transfer.token }
Invoke-WebRequest -Uri $transfer.url -Headers $headers -NoProxy -TimeoutSec 180 -OutFile $partial
$actualSize = (Get-Item -LiteralPath $partial).Length
$actualHash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSize -ne $transfer.size -or $actualHash -ne $transfer.sha256) {
    throw 'Archive size/SHA256 mismatch; keep .part for inspection and retry with a fresh server.'
}
Move-Item -LiteralPath $partial -Destination $destination
$headers.Clear()
$transfer.token = $null
~~~

A complete authenticated GET terminates the server. The server also hashes the
actual bytes it sends and rejects changed content. results.json records bytes,
hash, successful GET count, failed request count and exit status without the
token. Failed request/transfer tracebacks are retained without header dumps.
Incomplete downloads stay .part; the receiver's exact size/SHA256 check, not just
HTTP200 or server success, establishes the downloaded artifact identity.

First test an already verified small SDK/toolchain evidence archive to check LAN
reachability. A failed connection does not authorize firewall modifications;
retain the failed receipt and use a permitted transfer route or fresh bounded
server after correcting the cause. The tool never starts itself on another host.

Local preparation validation on 2026-10-13 passed a real loopback transfer of a
61KB fixture with exact size/SHA256 and a .part-to-final rename. Wrong path,
wrong token and HEAD returned 404/403/405; one complete GET exited the process.
The token was absent from results/stdout/stderr. A deliberately incorrect
preverified SHA failed before creating request.json. Those checks do not
establish Mac-to-Windows LAN reachability.

Actual Mac 172.26.202.95 to Windows transfers also passed on 2026-10-13. Each
receiver bypassed proxies and verified exact size/SHA256 before the .part rename:

| Archive | Bytes | SHA256 |
| --- | ---: | --- |
| SDK/JDK metadata and probe evidence | 61358 | 4df71f95d78c7ec5ed8ca16be95473b62a8372908395d03702ca11d4f33b7d89 |
| Matching Android private layout | 18578161 | 583f9fd4abed7aec54bbc65d9c53c39237f4c63de8963693a8f16b9796fd9e29 |
| Framework and frozen CoreLib raw evidence | 6849217 | aed8f702e25588746de05a95a0c9243aef8573e2a0fd1d7790e9f70f2c8c8f80 |

The layout archive's local verification covers 229 members and 228 individual
file hashes. The [framework raw archive verification](../artifacts/android-session-policy/20261013-framework-evidence/verification-results.json)
covers 30 members, including the manifest and 29 exact size/hash checks: 16
framework-stage raw receipts/logs, nine CoreLib evidence-refresh files including
four frozen managed PEs and one linker descriptor, one original failed-layout
receipt, and three bound metadata/deps inputs. Original remote files remain;
SDK caches and partial failed-layout product copies were excluded. The first
overbroad packing attempt remains remote and was not downloaded.

The raw-evidence server receipt at
ROOT/android-transfer-framework-evidence-20261013-attempt1/results.json records
exactly one successful GET, 6849217 sent bytes, the matching SHA256, and zero
failed requests. The layout server receipt similarly records one successful GET.
These receipts establish artifact transport and identity; Android application
execution remains a separate validation step.
