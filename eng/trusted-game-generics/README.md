# Trusted-game generics fixture

This directory is a focused, stock-SDK compatibility fixture for ordinary CLR
generic interaction between a host and independently built trusted modules. It
does not use the restricted UGC loader, a private CoreCLR build, crossgen2,
R2R execution, signing, a device, or a remote machine.

The host references only TrustedGameGenerics.Contracts and
src/RuneCLR.TrustedUpdate/RuneCLR.TrustedUpdate.csproj. It has no project
reference to either module, no module in its dependency list, and no module
output in its output directory. The two module projects are separate builds of
the same assembly identity (TrustedGameGenerics.Module, version 1.0.0.0) with
different variant constants. They are built after the host with
-p:BuildProjectReferences=false so the host, contract, and RuneCLR.TrustedUpdate
outputs are not rebuilt.

Covered shapes:

- generic reference T (Echo<ScorePacket>) with reference identity and state;
- three structurally different generic struct T values (ScoreVector,
  ScorePair, ScoreStamp) through a constrained host method;
- a nested generic container (IReadOnlyList<ScoreEnvelope<ScoreVector>> where
  each envelope owns Dictionary<string, List<ScoreVector>>);
- a generic contract interface and virtual dispatch (IScoreReducer<ScorePair>
  implemented by the module);
- a generic delegate callback (Func<T, int, int> passed to a host generic
  method);
- an author-private late value type (LateToken) passed to a host generic
  callback whose concrete type was unknown when the host was built. The type is
  internal to the module assembly and is not present in the host or contract
  images.

The module also writes six effects into a host-owned IScoreLedger, then reports
per-shape checksums through a shared contract sink. The host verifies that each
reported checksum is derived from the actual value its own method returned, so a
constant return cannot satisfy the fixture. A/B differ in bytes, MVID, ledger
total, and every per-shape checksum.

The ordinary failure path throws before the ledger is mutated. The session
returns CallbackFailed, the ledger stays unchanged, the session is closed, and
a subsequent invocation returns Closed. This fixture does not claim assembly
unloading, collection, exception retention, or module retention beyond those
session observations.

## Run

From the repository root, using Python 3 explicitly (bare python may be
Python 2):

    python3 eng/test-trusted-game-generics.py --output D:\RuneCLR-artifacts\trusted-game-generics-20261021-example

The default output is a fresh directory under artifacts/trusted-game-generics/
in this repository. The runner rejects an existing output directory. It uses the
current dotnet on PATH unless --sdk names another CLI. It performs three managed
builds: host first, then module A, then module B (both with
BuildProjectReferences=false), and two fresh host processes (A and B).

The Host accepts --context-mode collectible or resident, default collectible.
The runner passes the canonical mode in the Host argv. New-format reports must
contain requestedContextMode, contextIsCollectible, unloadRequested and
collectionClaimed; these values are checked against the requested mode and the
exact argv. Invalid, duplicate, or missing --context-mode values fail before any
product run.

Historical w01/w02 reports predate requestedContextMode, contextIsCollectible
and the flag. Their existing unloadRequested=true and collectionClaimed=false
are accepted only as implicit collectible. Both fields are required; missing
either is rejected. Partial or malformed new-format resident records are
rejected. Resident mode is implemented and compile-checked
in the Host but has not been executed; this fixture makes no resident, R2R,
interpreter or execution-mode claim.

## Offline replay

To validate a retained campaign without rebuilding or re-executing anything:

    python3 eng/test-trusted-game-generics.py --replay-root <retained-root> --output <fresh-output>

Replay reads the retained summary.json, commands.json, source-hashes.json,
runs/A and runs/B report and process files, and build/snapshots. It launches no
subprocess, SDK, build, or Host. It writes replay.json, VALIDATION-REPLAY.md,
and non-key SHA256/size/mtime pins before and after the replay
(pins.before.json and pins.after.json). The retained campaign status is recorded
as historical and is not overwritten. Replay refuses an existing output
directory and an output directory inside the retained root.

Replay recomputes fixture-specific expected values from the source inputs, not
from the shared contract helper. It checks all six shape checksums, aggregate,
ledger, exact echo and measure type order, reducer type and assembly, late
digest, Host/Contracts/TrustedUpdate identities and actual PE MVID/hash binding,
known artifact paths, command/process/report PID and argv joins, and module
AssemblyRef metadata for no module-to-Host dependency. These are fixture
expectations, not general generic-correctness proof.

## Offline self-test

    python3 eng/test-trusted-game-generics.py --self-test

Plain --self-test runs the shape, environment, and independent fixture-golden
checks without any machine artifact. It reports retained mutation tests as
SKIPPED. To run the retained base case and all mutations:

    python3 eng/test-trusted-game-generics.py --self-test --self-test-root <retained-root>

This uses no subprocess. It covers the singular structChecksum and plural shape
name mapping, including a clear failure for a report that contains the plural
key, and case-insensitive removal of DOTNET_ environment variables. It also
checks the documented fixture goldens against independent source-input
recomputation and runs offline mutations over report fields, identities, types,
shapes, process and command joins, and artifact metadata. Without
--self-test-root, mutation tests are reported as SKIPPED and no retained
artifact path is discovered automatically. An explicitly supplied missing or
invalid root fails with the root and required-file details.

Portability checks:

    python3 eng/test-trusted-game-generics.py --self-test-portability --self-test-root <retained-root>

This patches all subprocess entrypoints to raise, verifies that plain
--self-test does not discover a machine artifact root, verifies that an
explicit invalid root fails, and verifies that an explicit retained root still
runs the base case and all 66 mutations. It uses no subprocess.

Normal runs sanitize RUNECLR_, TRUSTED_, COMPLUS_, __TEST and DOTNET_ environment
variables case-insensitively before launching the SDK or Host.

## Evidence

The output directory contains:

- source/ and source-hashes.json: exact fixture and referenced input copies;
- logs/sdk/: resolved CLI version, info, SDKs, and runtimes;
- logs/build/: raw build stdout and stderr;
- build/artifacts/: isolated build output (host, contract, trusted update,
  and the two modules);
- build/snapshots/: host, contract, and trusted-update byte and timestamp
  snapshots after the host build and after each late build;
- runs/A/ and runs/B/: raw Host stdout and stderr, process metadata, and the
  Host JSON report;
- commands.json: every process, its arguments, process id, timing, and exit;
- summary.json and VALIDATION.md: checks, per-shape results, identities,
  resident observations, and scope limits.

## Scope

These are managed compatibility facts on the stock SDK and runtime. They do not
establish R2R specialization, interpreter fallback, execution-mode attribution,
assembly collection, iOS or physical-device behavior, or the restricted UGC
capability profile.