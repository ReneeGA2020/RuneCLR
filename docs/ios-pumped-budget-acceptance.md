# iOS simulator host-pumped budget acceptance

On 2026-10-15 the updated [host-pumped session](host-pumped-sessions.md) and
portable mobile budget adapter passed **16 cases / 74 collected contexts** in a
fresh ARM64 iOS 27 simulator application. This is an actual simulator execution
of the current managed host, using the existing private Release native runtime.
It does not establish physical-device execution or new method-entry samples.

## Bound build and execution

The new [controller](../eng/ios-pumped-budget-application.py) keeps the accepted
scene application and framework inputs immutable. It compiles 21 frozen C#
sources with the private official runtime-build Roslyn toolchain, then builds
a new trusted 186-component R2R composite and signs a fresh simulator bundle.
The trusted composite contains `RuneCLR.Abstractions`, `RuneCLR.Packages`,
`RuneCLR.Runtime`, `MobileHostBudgetProbe` and a bridge selecting `--pumped`.
The raw author payload and its private helper are absent during installation.
This direct fixed-source compiler route is separate from the SDK project build.

Native provenance remains the accepted iOS Release candidate:

| Input | Identity |
| --- | --- |
| Runtime commit | `3126bbc9a8851a09ac6435b18a12882bad48f3ee` |
| Runtime tree | `710936ae1729a5689ab0e0896f3cf722ddd3d31c` |
| Upstream base | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` |
| Unsigned native runtime SHA-256 | `b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae` |
| Original scene state SHA-256 | `dad906720793ac28271f3c81f3ae5532100005bb3a9842dfc2987fb81dad09af` |
| Target | `iossimulator.arm64`, Release, static interpreter, dynamic JIT disabled |

The controller checks committed tracked-clean native source, actual native,
CoreLib and crossgen2 hashes, original signed scene inventory, raw framework
hashes and new trusted component MVIDs/R2R headers. The exported native source
proof is also checked against the live checkout. No runtime rebuild is needed.

The installed bundle readback finishes at `2026-10-15T06:59:30.469709+00:00`.
Two actual author compilations start later at
`2026-10-15T06:59:30.481560+00:00` and finish at
`2026-10-15T06:59:34.210900+00:00`; both outputs have no managed native body.
The payload SHA-256 is
`a1ca5fc8b915390866cb85c82716447e08aad04fca528a67772ecb0162212c8a`;
the private helper SHA-256 is
`d01d579e9b34a91f1d8712c1b806f35aea5c5ca0f12be58f31384f66ca99b87b`.
The installed author readback and bundle inventories match before/after execution.

Actual application PID `84304`, nonce `be44e0008fd545dfb1554191b73f1079`, emits
all six native configuration/initialization/delegate/invoke/exit markers and
exits zero. The native profile is phase-acquire 1, derived-ledger 1, exact
batch interval 0, global interpreter mode 0, collectible diagnostic 0, R2R 1
and tiering 0. These markers bind this functional run to its launch and native
configuration; they do not independently sample author method entries.

## Observed behavior

All 74 rows report `pumped=true`, a successful completed-tick count matching
actual host returns, released host-owned resources, and collection while the
stopped `MapSession` remains retained by its trusted caller. The adapter runs
the original fifteen scenarios plus the new finite per-frame `TickWork` case.
There are twenty normal sessions, twenty bad/good recovery pairs and fourteen
single-session cases, for 74 total contexts.

| Boundary | Actual result |
| --- | --- |
| Cumulative budget across frames | Six `TickWork` callbacks return successfully; tick seven terminates at exactly 8192 execution dispatches. |
| No budget refill on host return | Final execution remaining is 0, execution executed 8192, cleanup untouched at 4096. |
| Constructors / static constructors / start | Exhaust at the same 8192 allowance; host regains control and unloads. |
| Catch, broad catch and filters | Terminal author continuations remain suppressed. |
| Finite private finally/delegate cleanup | Completes with 38 cleanup dispatches and 4058 remaining. |
| Infinite private cleanup | Stops at exactly 4096 cleanup dispatches, cleanup remaining 0, phase 2. |
| Ordinary authored errors | Malicious `Message` and explicit cancellation retain ordinary-error reporting and allowed `OnStop`. |
| Recovery and retained sessions | Twenty exhausted/good pairs recover in the same process; all retained stopped sessions release author state. |

The owned simulator `C5428CAC-6732-40F9-B065-28FFCD2A5BC4` is shut down and
deleted after the passing run. Cleanup readback passes at
`2026-10-15T07:00:09.340541+00:00`; no physical device is queried or changed.

## Evidence and preserved correction

Downloaded evidence is under
`artifacts/ios-pumped-budget/20261015-attempt1/remote-evidence`.
The complete compact archive has 290 files, 928951 bytes, SHA-256
`4326ace8d19fdf495d598b24fec4463e98b394190e52241ed572a9b7ce3a3dbc`.
Its manifest SHA-256 is
`83906b957d322e658179bb34dc13914c6517c8c92747d6d500326ce173933826`;
all exported file hashes pass local readback verification.

The `application` directory holds build requests/results, frozen managed
sources, all 186 raw/component identities and signed bundle hashes, all stage
requests/processes/logs, actual 74 rows, install readbacks and cleanup receipts.
`export` holds both frozen controller revisions, unchanged helper scripts and
native source/proof. `trusted-il` holds the five newly compiled trusted IL files.
`launcher` preserves the original build, failed receipt write and resumed run.
The parent agent's `root-review.py` / `root-review.json` independently check
the archive and all 289 manifest-bound files, 21 current/frozen host sources,
38 native source hashes, trusted IL/R2R identities, installation-before-author
ordering, both controller identities, process streams, all 74 ledgers and
retained-session collections, and successful owned-simulator deletion.

The initial controller successfully installed the app and read back its bytes,
then failed to write its install receipt because the new build request omitted
the `driverSha256` key required by the reused helper. Its failure and automatic
simulator shutdown are preserved. This is our controller defect. The corrected
controller reboots the same owned simulator, verifies the existing installation
and absent author destination, then continues with fresh author compilation.
It does not reinstall or rebuild the accepted app. The frozen build driver SHA
is `6f46c2803083f2e28a115fa3bcee84e2d4270913489fe895b8c8848eec558584`;
the actual resumed-run/current controller SHA is
`51b87e4978902f578b4eac08ae81e3f2cc37c7842ca165a9f4e55ffe6310600d`.
The new receipt records both identities explicitly.

The five original trusted C# compiler logs contain `CS2023`: `-noconfig` was
placed inside a response file and ignored. Their exit codes remain zero.
The corrected controller passes `-noconfig` directly to the compiler, and the
two actual post-install author compilations complete without that warning.
Original warning logs and trusted binaries remain preserved; no warning-free
trusted-build claim is made for this attempt.

## Remaining scope

The fixture is fixed diagnostic raw IL and includes exception/delegate shapes
outside the production gameplay capability profile. This run establishes the
updated host-pumped mobile budget route, separately from controlled-package
admission acceptance. It uses exact accounting; it adds no mobile batch-100 or
batch-1000 performance result. Earlier accepted fifteen-case applications and
method-entry evidence remain unchanged. Updated Android applications, new
method-level samples and actual physical-device acceptance remain separate work.
