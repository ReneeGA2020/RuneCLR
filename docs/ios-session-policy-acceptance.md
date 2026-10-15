# iOS simulator session-policy acceptance driver

[ios-session-policy-accept.py](../eng/ios-session-policy-accept.py) prepares a
fresh current player and separates build, installation, transfer, execution,
cleanup and archive phases. On 2026-10-13 the fresh arm64 Release simulator
player passes all four actual acceptance lanes: 15/15 packages, current 24/24
lifecycle, three collected sample contexts, and 20/20 selection sessions with
20 collected contexts. Native method-entry sampling remains separate from
these functional and policy-acknowledgement results.
The later [Release refusal/recovery run](ios-session-policy-refusal.md) separately
verifies a scoped compiler refusal, collection and twenty subsequent successful
sessions using the unchanged player. It does not replay these four lanes.

The driver never builds dotnet/runtime. Its build phase consumes an external
successful receipt and verifies the official base, exact clean source commit
and tree, native/CoreLib/crossgen2 hashes, simulator target, Release
configuration and actual arm64 native CPU. App build uses the matching
compiler, regenerates component DLLs, links the new composite, rebuilds the
native wrapper and signs only its new output. Old applications remain intact.

## Actual inputs and changed topology

Remote experiment root is
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr. The old player is
ios-r2r-release-packages-20261013/app/Packages.app, based on CID-only runtime
8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d. Its old bridge does not pass the
required-policy flag. It cannot establish current session-policy support.

| Original IL input | Old player input SHA-256 | Current frozen input SHA-256 |
| --- | --- | --- |
| RuneCLR.Runtime.dll | b224b60925de45c0b7e3c2c8cf57c0e06d6f113278452dd782ec9feb56fc4301 | 3c8d3915291aedb4afa0ac82ab8d693aca5ea7218cf9d99bf2126cd01044456f |
| RuneCLR.PackageExecution.Tests.dll | ac355f97052d21b6978cad9fa592165942dd3ee9a85dafe0dd33e8d22c0a9291 | 9155363b60b24fe7ef5666eaacaa1114a99731b217c95c38ac0a510fc7af0318 |
| RuneCLR.Abstractions.dll | 86bc966dd4e9f5f349b0c3d8fb869e180f76823af0ee6aa6e1ce64e7bbd16f31 | unchanged |
| RuneCLR.Packages.dll | bf16e2abe3d085509bec1b3019b51915221bc4cebec683c206ebb538e1a74de8 | unchanged |

Input hashes identify IL before crossgen2. Component DLLs in an app have new
R2R metadata and different hashes; state.json records both identities.

The frozen host directories are ios-session-policy-host-inputs-20261013/player,
lifecycle and sample. The independent selection fixture is
ios-session-policy-selection-inputs-20261013/selection, with trusted and plugin
subdirectories. A 32-file cross-platform host snapshot is
[ios-session-accept-host-snapshot-20261013.json](../artifacts/session-policy/ios-session-accept-host-snapshot-20261013.json),
SHA-256 44e1fef3bd58cd5aa32ca1d804f90a3eef467c41e8569caf29927ab266c7542f.
The existing root-produced identity receipt is retained separately. No
production DLL rebuild is needed for transfer.

This mode-0 iOS lane requires the trusted Runtime and Packages assemblies to
join CoreLib/framework, contract, both production harnesses, sample and the
new SessionBridge in the fresh R2R composite. The previous selective
Runtime/Packages IL topology depended on interpretation of ordinary trusted
definitions; it is unsuitable here because iOS has no dynamic JIT.
UGC/map/private fixtures remain outside the composite and root TPA inventory.
Operator compilers and Roslyn are rejected from the app inventory.

One explicit exception supports the unchanged lifecycle default-collision
test. Version A RuneCLR.PrivateDependency.dll is compiled into the composite;
its generated component is also placed in dependency-a. An uncalled trusted
bridge method references PrivateState<int>.Start to prepare that native
instantiation without seeding default state early. The ordinary final default
seed must execute natively, while required private copies must interpret
those same definitions despite available R2R. Version B remains IL. The
original IL and generated component hashes are recorded separately. The
native loader maps the known framework.dylib owner to the immutable bundle
root so copied components can resolve it from fixture/temporary directories.
The actual unchanged 24/24 harness completes, including its final default
collision seed, with mode 0; the test is neither skipped nor enabled through
global mode 1. Generated version A component SHA-256 is
9290dcebe84d74f8248e12fbcd708edff4f7d2db195b66988956a2c07cb96ee3,
versus original IL 00b5686547f107f1b1f5ba1590206dce46abc9c2b53b22e65e62382fc2a34a03.
Its managed-native RVA/size are 67160/28. This successful functional control
does not independently capture the native PC of the seed or interpreter entry
of each private copy.

## Measured matching acceptance

Combined runtime commit is 1724cdec553a7aff7a373a271a4be612651c7625, tree
71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, based on official
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The matching native/CoreLib/compiler
input SHA-256 values are respectively
891cec1e2880ef983110ba4487ed63f8cd2a524c3fad8f1ea7acd7495b509c69,
ae328f90d5feb596d1331581d54be6c2a455bcb42175690fddd90bd962c1e1eb and
18ef35a8431cd794b3850a2ef1bd0b1508b53b7458ec636a4245771da9d8ad01.
The native source build and fresh trusted composite are distinct steps, both
completed before installation.

Evidence is under remote root ios-session-policy-player-20261013-attempt1.
The original build driver.py remains SHA-256
a3e54a66d792a84132675373ca7880bca5464e36e1eb455ec46d1f08b3870784;
run-driver-v2.py is 1d1b88d8f4ed39b00a0e2e5bdeb068fca1c1ef311d7f30569b2ac47f091eccf0.
The revised run driver explicitly records selection plugin/evidence paths
without rebuilding or changing the app.

| Run directory | Owned app PID | Actual completion | results.json SHA-256 |
| --- | --- | --- | --- |
| run-sample | 84598 | Three contexts collected; both Hello start-count=1 | a6034c4a188ee2bbf897728eae6a4708bd1fe1a398496e97e3d05cc9b582b154 |
| run-packages | 84747 | 15 individual PASS and 15/15 summary | b44ec4b461c4f7da25570fe73784d7111804f78a4a24ad00da67ed7f5bd482b6 |
| run-lifecycle | 84793 | 24 individual PASS and 24/24 summary, including late map and default collision | ea60ae02d6d0f9b3e05368bb329d790446149c9bace8512b787fa5060719dac2 |
| run-selection | 84833 | 20 session values PASS and 20/20 contexts collected | ddca8a15bf17755f1536ead33d54dbf7eb1f33ba729b692283807b557fb77b23 |

All four receipts report policy version 1 acknowledgement, explicit
InterpMode=0/global collectible diagnostic 0, native managed-exit 0, normal
process exit, LLDB exit 0, unchanged installed bundle and payload, and no
assertion/crash. Independent read-only checking recomputed every recorded raw
file hash, decoded the original unified JSON, checked every event against the
owned PID, and matched parsed eventMessage values to the stored messages.
Managed summaries are not inferred from native exit alone.

This run used new post-install production, not the old incoming directory.
The app installed at 2026-10-12T19:44:39.718534Z. Original producer output
directory CreationTime is 2026-10-12T19:45:58.232329Z and fixtures.json records
generation at 2026-10-12T19:46:01.7264786Z. Post-install late IL SHA-256 is
6aeef807374c9eb10ba4b85bca319766adcc631795506542f51acd24c6c28539;
its native RVA/size are zero. Source/import/source, ordinary/generic private
state, author-failure cleanup, admission rejection and recovery pass in the
15-case player harness. Some deterministic generated bytes equal previous
fixtures; original production commands/logs and chronology establish the new
production event separately.

The producer's receipt formatter failed after both generation commands had
completed. postinstall-producer.json and late-producer.json preserve that
failure and a read-only assessment, with SHA-256
a96c48e7d1e0c49974b56576e3138a5ac0d8893082a1340d1507ba30a0bd89b0.
The exact in-memory start timestamp was lost; directory CreationTime is
explicitly identified as the observed start evidence. No compiler/package
replay was performed. state.json's generic transfer productionClaim remains
conservative; this separate producer assessment supplies the chronology.
The original build receipt's executionVerified=false is also retained as a
build-time snapshot; the four subsequent run receipts establish execution.

The owned functional simulator AF411A2C-F497-4074-93D4-0577E296D71B was shut
down with exit 0 at 2026-10-12T20:00:12.027476Z, recorded in cleanup.json.
This is simulator evidence; physical-device policy acceptance remains pending.

## Integration commands

Copy the driver and its two helpers, ios-r2r-fix-verify.py and
verify-ios-packages.py, into the same remote directory. A local snapshot can
be created with phase snapshot and --player, --lifecycle, --sample,
--selection-dir and --host-receipt. Build consumes that snapshot unchanged.
The matching build receipt must contain success, base, commit, tree,
nativeSha256, corelibSha256, crossgen2Sha256, target and configuration.

~~~sh
R=/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr
B="$R/ios-session-policy-release-20261013"
H="$R/ios-session-policy-host-inputs-20261013"
O="$R/ios-session-policy-player-20261013-attempt1"
P="$B/runtime/artifacts/bin/coreclr/iossimulator.arm64.Release"
python3 "$R/eng/ios-session-policy-accept.py" build \
  --output "$O" --runtime "$B/runtime" --build-receipt "$B/results.json" \
  --native "$P/libcoreclr.dylib" --corelib "$P/IL/System.Private.CoreLib.dll" \
  --compiler "$P/arm64/crossgen2/crossgen2" \
  --baseline "$R/preview6-experiment/pinned-debug-harness" \
  --player "$H/player" --lifecycle "$H/lifecycle" --sample "$H/sample" \
  --selection-dir "$R/ios-session-policy-selection-inputs-20261013/selection" \
  --host-receipt "$H/ios-session-accept-host-snapshot-20261013.json" \
  --previous-player "$R/ios-r2r-release-packages-20261013"
python3 "$R/eng/ios-session-policy-accept.py" install --output "$O"
python3 "$R/eng/ios-session-policy-accept.py" transfer --output "$O" \
  --packages "$R/ios-session-policy-postinstall-inputs-20261013/packages"
~~~

Both the original inventory and the new production contain nine manifests: source/import/
failure/tampered/forbidden and private-a/private-b/private-import/
private-forbidden. Their profile is managed-il-gameplay-v1 and producer contract
hash matches current original contract IL. Transfer verifies producer manifest
hashes and pure IL, preserving deliberately invalid contents for rejection
tests. The driver also permits reusing old incoming fixtures, which establishes
new execution of existing IL without a fresh production claim. The measured
run above instead preserves separate new post-install producer evidence.

After installation, rebuild the late map separately without rebuilding the
host, transfer its RuneCLR.LateMap.dll and map.json, and preserve the producer
command/log/source evidence. Phase transfer requires --late <directory>,
--late-produced-utc <UTC timestamp after installation>, and accepts
--late-receipt <producer JSON>. The timestamp is explicitly caller-supplied;
it does not replace the producer evidence. Then execute each requested lane:

~~~sh
python3 "$R/eng/ios-session-policy-accept.py" run --output "$O" --lane packages
python3 "$R/eng/ios-session-policy-accept.py" run --output "$O" --lane lifecycle
python3 "$R/eng/ios-session-policy-accept.py" run --output "$O" --lane sample
python3 "$R/eng/ios-session-policy-accept.py" run --output "$O" --lane selection
python3 "$R/eng/ios-session-policy-accept.py" cleanup --output "$O"
python3 "$R/eng/ios-session-policy-accept.py" archive --output "$O"
~~~

Installation creates an owned simulator. A run uses a single host-owned
phase argument to SessionBridge; packages, lifecycle and sample invoke their
current trusted harnesses with explicit --require-interpreter. The native
wrapper sets InterpMode=0 and RuneCLRInterpretCollectible=0 before CoreCLR
initialization. Selection invokes its zero-argument mobile adapter, with
actual installedApp/plugin and Documents/selection-evidence paths.

Each run has its own never-overwritten directory, PID-bound unified-log query
and UTC interval, separate stdout/stderr, raw JSON and parsed eventMessage
values, LLDB normal-exit evidence and input hashes. Acceptance requires native
acknowledgement version 1, native/managed exit 0, exact individual and summary
counts (15 packages or current 24 lifecycle), clean shutdown separately, and
unchanged bundle/payload. The sample requires three collected contexts and
both Hello start-count=1 reports. An older 21-case harness is not accepted as
the current 24-case suite. Failed runs remain evidence.

## Method execution evidence remains independent

Functional completion and version acknowledgement do not identify every
method's execution backend. Use the independent
[session-policy native entry probe](ios-session-policy-entry.md) on the
matching built app/native/DWARF and actual installed plugin paths. Its
execution samples bind Module path, MethodDef token, original fixture SHA and
actual interpreter bytecode pointer; preparation is only a sampling gate.
The existing package capture can separately cover its fixed 23 callback/helper
groups on the new app, with its actual acknowledgement markers and mode-0
wrapper identities checked. Sampling is not complete invocation counting.

Archive output retains original source snapshots, response files, logs,
receipts and original current player IL. Hash the downloaded archive locally.
Simulator acceptance does not establish a physical-device build, signing,
new-IL execution or repeated retirement on a real device.

The completed [build/player/entry archives](ios-session-policy-build.md#retained-evidence)
have been downloaded and independently verified locally: 214 member files,
72 raw-log hashes and 27 committed-source hashes match. The first archiver's
manifest-name collision remains recorded separately; corrected repacking
did not rebuild or rerun the app. The owned simulator is confirmed Shutdown.
