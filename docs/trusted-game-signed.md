# Trusted game signed release

This composes the existing signing, staging and recovery helpers with the maintained TrustedGame sample. It is stock desktop managed/JIT scope, not R2R/interpreter mode proof, iOS delivery, unload or a security sandbox.

## Publisher

TrustedGame.Publisher references RuneCLR.TrustedUpdate only. It signs one explicit module identity:

    dotnet TrustedGame.Publisher.dll --module <TrustedGame.Update.dll> --version game-rules-a --entry-type TrustedGame.Update.GameRules --entry-method Entry --runtime net11.0 --architecture <native-arch> --signed <A.signed.json> --spki <host.spki> --private-key <demo-private.pem>

The publisher uses TrustedRelease.Sign and writes the signed document, the host SPKI and, if absent, a local demo P256 private key. The key/SPKI/signed paths must be outside the release content root. The host receives only the SPKI path; it never receives or reads the private key. Demo key generation is a local convenience: production must pin its own trusted key material. On reuse, an existing key is imported and an existing SPKI must match it. The local-trusted-build value used by local mode remains an approval, not a signature; signed stage and recovery verify the signed document with the host SPKI.

The invalid-entry control is a separate negative, not business B. It signs the A bytes with a deliberately wrong entry type:

    dotnet TrustedGame.Publisher.dll --module <TrustedGame.Update.dll> --version game-rules-invalid --entry-type TrustedGame.Update.MissingRules --entry-method Entry --runtime net11.0 --architecture <native-arch> --signed <InvalidEntry.signed.json> --spki <host.spki> --private-key <demo-private.pem>

Real B is the independently built UpdateV2 output. Put it in a separate directory because its file name is also TrustedGame.Update.dll:

    dotnet TrustedGame.Publisher.dll --module <path-to-UpdateV2>/TrustedGame.Update.dll --version game-rules-b --entry-type TrustedGame.Update.GameRules --entry-method Entry --runtime net11.0 --architecture <native-arch> --signed <B.signed.json> --spki <host.spki> --private-key <demo-private.pem>

A and B share AssemblyName TrustedGame.Update, Version 1.0.0.0, the same namespace/type TrustedGame.Update.GameRules and Contracts identity, but have different bytes/MVIDs. A gameplay is 1/3/6 with Score 6; real B gameplay is 2/6/12 with Score 12. Invalid entry uses the A bytes and fails activation before gameplay.

## Host modes

Local mode remains compatible:

    dotnet TrustedGame.Host.dll --module <TrustedGame.Update.dll> --sha256 <64-hex> --approval local-trusted-build

Signed staging:

    dotnet TrustedGame.Host.dll --stage-signed <source-dir> --signed <A.signed.json> --spki <host.spki> --releases-root <releases> --receipt <state/receipt.json>

Signed next-process recovery:

    dotnet TrustedGame.Host.dll --recover-signed --spki <host.spki> --releases-root <releases> --receipt <state/receipt.json>

Both signed modes accept an optional trailing --expected-score-multiplier 1|2 (default 1). It changes only the host assertion expectations. Author Tick always receives the same deltas 1, 2, 3; host inputs, callback results and state are never multiplied to manufacture a version.

Stage verifies the signed manifest, uses only the listed source files, publishes through TrustedReleaseStaging.PublishAsync to a new final directory under the releases root, and then calls TrustedReleaseRecovery.TryStart with the published final offer. The receipt is outside the immutable releases root. A failed preverification or stage attempts recovery of the existing authenticated receipt through the same API. A failed activator is not followed by a second activation in the same process.

Local mode accepts only Candidate. Signed stage and recovery accept Candidate and LastKnownGood from the signed flow. The Host prints a SIGNED-FACTS line with stage, candidate, recovery, persistence and source facts. Activation, gameplay and receipt persistence are separate facts; successful activation does not imply successful gameplay or persistence. The typed gameplay uses deltas 1, 2, 3 and checks the actual callback/state values: A 1/3/6 with Score 6, real B 2/6/12 with Score 12; the negative-delta CallbackFailed/Closed no-mutation check remains.

## Expected integration sequence

Run the maintained one-command entry:

    ./eng/trusted-game-signed.ps1

or:

    ./eng/trusted-game-signed.ps1 -OutputRoot <new-directory>

With no arguments it creates a fresh directory under artifacts/trusted-game-signed/<timestamp>-<guid>. An explicit -OutputRoot must not already exist; the script fails before creating logs or build output. The script uses the current PowerShell executable for the local regression, propagates -Configuration, and adds -ExecutionPolicy only on Windows. The Windows, Linux and macOS CI matrix was not executed; only Windows local PowerShell 7.6.7 and 5.1 were exercised. The publisher defaults to the current process architecture, with explicit --architecture override retained.

eng/trusted-game-signed.ps1 builds Host first, Publisher separately, Update (A) and UpdateV2 (B) late with BuildProjectReferences=false, checks that Host/Contracts/TrustedUpdate hashes/timestamps did not change, and writes logs under the output directory. It then:

1. Signs A, the invalid-entry control and real B with one local demo key and SPKI.
2. Stages A, runs 1/3/6 and failure/Closed, and records the receipt.
3. Recovers A in a fresh process and confirms the receipt bytes are stable.
4. Stages a tampered A payload; signature verification fails, no tampered code runs, and the existing A receipt recovers A.
5. Recovers A in a fresh process again and confirms the same gameplay and receipt.
6. Stages a validly signed invalid-entry control (version game-rules-invalid, entry type MissingRules); activation fails with no fallback and the old A receipt is unchanged. A fresh process recovers A.
7. Uses the already late-built UpdateV2 B output (same AssemblyName TrustedGame.Update, same namespace/type and Contracts, different bytes/MVID, version game-rules-b) for the real B offer.
8. Stages real B in a fresh process with --expected-score-multiplier 2; asserts 2/6/12, Score 12, Ticks 3, version game-rules-b and a changed persisted receipt.
9. Recovers B in a fresh process with multiplier 2; then stages a tampered B offer, which is rejected and recovers authenticated B with the B receipt unchanged.
10. Runs a fresh recovery of B with the wrong multiplier 1; gameplay assertions fail nonzero and the B receipt is unchanged. A subsequent multiplier-2 recovery succeeds.
11. Runs the original eng/trusted-game.ps1 local regression.

## Process lock scope

Existing API/library tests cover offered-start, recovered-start, failed-restore and second selection/start locking: they report ProcessSelectionLocked and zero second activation. Relevant tests are tests/RuneCLR.TrustedReleaseRecovery.Tests/Program.cs and tests/RuneCLR.TrustedUpdate.Tests/Program.cs. The sample E2E uses fresh processes for A and B and has not directly demonstrated a same-process second request. This is API-level test coverage, not a missing feature and not a sample E2E claim.

## Current Lead evidence

Lead A/B execution evidence (2026-10-20) is under D:/RuneCLR-artifacts/lead-trusted-game-ab-20261020: lead-checks.json records 18 command result lines, real B stage/recovery and rejected wrong expectation; source-review-checks.json records 13 inputs and 0 drift; actual-image-metadata.json records the four images read with .NET PEReader. These paths are traceable execution/review references, not a new acceptance gate.

## Boundaries

One version is selected per process; recovery happens in a later process. There is no active-stack replacement, in-process version switch or unload. The receipt is host-owned state outside the releases root. A successful B stage/recovery changes the persisted receipt; a wrong-multiplier gameplay failure does not mutate it. The validly signed invalid-entry control is distinct from real B: invalid entry fails before gameplay, while real B is the same assembly identity with a different module hash/MVID and a multiplier-2 business result. This sample does not claim network authentication, anti-rollback, race-proof file identity, a security sandbox, iOS or other-device delivery, or execution-mode proof.
