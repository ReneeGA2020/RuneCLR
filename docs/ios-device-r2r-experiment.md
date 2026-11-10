# iPad device R2R experiment (2026-11-10)

Status: bounded physical-device experiment for trusted, developer-signed C# hot
updates on iOS. A developer-signed iPad host was installed once, then two
independently compiled ReadyToRun (R2R) update owners were built after that
install, delivered into the app data container, loaded by the host and executed
natively. The native entry of the owner method was captured with a debugger for
both versions, and both runs finished with the expected managed result and exit
code 0.

This page records what was measured, the exact chain that was verified, and the
boundaries of the claim. It does not claim production delivery, unload,
same-process switching, interpreter-mode proof, performance or sandboxing.

## What was demonstrated

- **Signed host installed first.** A developer-signed iPad application containing
  the fixed host (private CoreCLR runtime, host R2R composite, entry assembly and
  the shared contract) installed successfully at 09:18:07-09:18:11Z. The install
  receipt was archived before any update code was compiled.
- **Fresh update builds after install.** The A and B owners were compiled and
  cross-compiled afterwards (generator start 09:18:16Z), each with its own nonce
  and version stamp, then signed as a normal development dylib.
- **Delivered and read back.** Each payload directory (owner dylib, compiled
  update assembly, private dependency, IL-only helper and the payload hash list)
  was pushed into the app data container and freshly read back; every hash
  matched the local signed file and the payload list.
- **Loaded from the app data container.** The host's native-image callback
  resolved the component header of the downloaded update assembly to
  `TrustedUpdate.<A|B>.r2r.dylib` next to it and mapped that file, so the
  runtime used the downloaded owner rather than anything inside the bundle.
- **Native execution observed.** With the process stopped before the owner was
  loaded, a breakpoint on the owner's `Business.Execute` was armed from the
  mapped module. Both runs stopped inside that method at an actual PC inside the
  owner's executable region, with the host R2R frames and `Update.Run` on the
  stack.
- **Shared objects and host calls.** The update assembly resolved the contract
  from the host's default context (`contractFromDefault: true`), and the owner
  called back into the host through the shared interface and a host-provided
  delegate. The host then reached the private dependency and the IL-only helper
  through its reflection path.
- **Per-version results.** Nonce and version stamps matched the launched values,
  results were 216 for both versions with private values 100 (A) / 200 (B) and
  helper outputs 307 (A) / 607 (B), and both processes exited with code 0.

## Candidate and runtime

| Item | Value |
| --- | --- |
| Host build record | `READY` SHA-256 `a18682d8cd347d5da5ee5b82b56fb074118356e58e56244f95fd7ffe01d734cc` |
| Host bundle | `org.runeclr.ipadr2r20261110`, 208 files, 297,277,672 bytes |
| Host inventory digest | `b9f145fc1e80cb2793cf2eeee97c18e5f33323fb4976945b30fe1dc82629ec13` |
| Managed entry | `RunEntry.dll` SHA-256 `97e761ab6f1eab32c04acf71bf8804ba88dc7f1978c043371aa65918f7376a87`, token `0x6000004` |
| Entry source | `RunEntry.cs` SHA-256 `3996ce37be8870645ec61cd11cda529b9bf896442086357aa86c2a34b7fb3674` |
| Signed host | app tree digest `97994aa52d621daebe801c22506e951e868951c7d3a5993ff4bcd582800597e4` |
| Shared contract (deployed component) | `277f3596fb60f958acf4cbdf20fd5c1e5dd99653ef4a1c1403aa574f4520870c`, MVID `685c96ae3a1656478d66eb3c5719c12b` (raw IL `f0bffe24...`) |
| Runtime branch | `runeclr/mobile-batch-interval` at `3126bbc9a8851a09ac6435b18a12882bad48f3ee` |
| Device `libcoreclr` | `34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b` |
| Device | iPad Air 11-inch (M4), iPadOS 27.2.1, arm64, Mach-O platform 2 |

The host contract used here is the platform-native callback `get_native_code_data`
from `host_runtime_contract`; the contract header and its invocation site are
unchanged between this runtime base and the later upstream merge pin (see
[coreclr.md](coreclr.md) for the integration boundary).

## Measured sequence

1. **Install** 09:18:07Z - 09:18:11Z, outcome success, receipt SHA-256
   `c8bbf0f00500dad3e40a4e1466c17836190eb425104b65d7eb651fd48a4f1287`.
2. **Generate A and B** at 09:18:16Z from pinned sources with the private
   compiler, then cross-compile the owner composite and sign the dylib:

   | | A | B |
   | --- | --- | --- |
   | nonce | `c1d2e3f405162738495a6b7c8d9e0f10` | `d2e3f405162738495a6b7c8d9e0f1011` |
   | owner (signed) | `efd9302941607ce43793741f8e2e5a70c93e5ecc3c2147edf4a7c4834f687771` | `38059910e8b786c93e14cf635598d45daea72f95459d2ddb8eb2263938c95061` |
   | owner UUID | `5537271B-CF18-361C-A722-357B01AC114B` | `54DFE7A2-4E78-3AAE-9DBD-6D89F802C56A` |
   | owner bytes | 56,488 raw / 75,360 signed | 56,488 raw / 75,360 signed |

3. **Push and read back** the five payload files per version; the owner, update
   assembly, private dependency, helper and payload list all matched on the
   device copy.
4. **Launch under the debugger** with the launch request stopped at start, then
   attach, continue to the owner module, arm the method address and continue.
5. **Stop at the method entry** and capture the PC, register, executable region
   and backtrace (see the table below).
6. **Complete** the run: managed result JSON written, console markers printed,
   process exit 0.

## PC witness

| | A | B |
| --- | --- | --- |
| process | 860 | 862 |
| owner path on device | `<app-data-container>/Documents/payload/run5-A/TrustedUpdate.A.r2r.dylib` | `<app-data-container>/Documents/payload/run5-B/TrustedUpdate.B.r2r.dylib` |
| load base | `0x14d7e8000` | `0x1086c4000` |
| method file offset | `0x4050` | `0x4050` |
| stop PC | `0x14d7ec050` | `0x1086c8050` |
| executable region at PC | `[0x14d7ec000,0x14d7f0000) r-x __TEXT` | `[0x1086c8000,0x1086cc000) r-x __TEXT` |
| stop reason | `breakpoint 1.1 2.1` | `breakpoint 1.1 2.1` |
| result file | `cf3a8ff0a3f6a781134f612976759e60b40669d414aaaf1e761e5b277db86e08` | `3e4c561334cfd3410960466446175c5b75ff0df4b9f981b2d07b09128bdec33f` |
| process exit | 0 | 0 |

Reading notes for this table:

- `0x4050` is the method's file offset inside the owner image. A symbol lookup at
  `load base + 0x4050` resolves to `__TEXT.__managedcode + 0` with the summary
  `...Business__Execute`, so the address breakpoint targets the method entry.
- The reported region is the executable subrange returned for the stop PC, not
  the whole Mach-O `__TEXT` segment. The PC sits inside that subrange.
- The symbol breakpoint (armed by name before the owner was loaded) and the
  address breakpoint both fired (`1.1 2.1`), so the address is confirmed by the
  symbol table, not only by the breakpoint we placed.
- The backtrace at the stop is the owner method, then `Update.Run` in the same
  owner image, then CoreLib reflection invoke frames, then the host R2R frames
  `Driver.ExecuteLoaded`, `Driver.TryStartLoaded`, `Driver.Run`, the entry
  assembly's `ProbeEntry.Main` and CoreLib's entry-point caller.

## Result contract

The managed entry writes one result file per run (the host prints the same record
on stdout):

```text
schema, runId, expectedVersion, scriptVersion, observedVersion, scriptNonce,
nonceMatches, versionMatches, goldenMatches, observedResult, observedPrivate,
observedHelper, goldenResult, goldenPrivate, goldenHelper, driverExitCode,
contractMvid, contractFromDefault, resultWriteFailed, ok, error, logLength,
logExcerpt
```

Acceptance used here: `ok`, `nonceMatches`, `versionMatches`, `goldenMatches`,
`contractFromDefault` all true; `driverExitCode` 0; `resultWriteFailed` false;
process exit 0. `observedVersion` is the host's selected version (it defaults to
the requested value); the independent version evidence is `scriptVersion`, which
comes from the stamp compiled into the update assembly.

## Boundaries

- The PC capture is bound to the debugger runs (processes 860 and 862). The
  same payloads were also launched without the debugger (processes 820 and 821)
  for functional output only; those runs are not part of the PC evidence.
- This run used host build 5. An earlier host 4 attempt is history and is not
  reused; build 5 was installed exactly once for this experiment.
- The earlier post-install IL experiment with twenty sessions and unload
  observations is separate evidence and is not reused here. This experiment did
  not exercise unload or version switching.
- The measured update source snapshot and the current repository source can
  differ. The measured `RunEntry.cs` hash is recorded above; an older file with
  a different hash belongs to the host 4 snapshot and is not this candidate.
- The runtime merge against a newer upstream pin is an experimental Windows
  baseline. It is **not** the device base for this experiment.

Not claimed by this page: per-method interpreter proof for the IL-only helper in
this run (only its normal output through the host reflection path), whole-method
native compilation mode, production HTTP delivery, App Store distribution,
unload or same-process switching, performance, Epoch/deadline behavior, sandbox
or security hardening.

## Reproduction recipe

The exact local artifacts are not published; this is the minimum recipe an iOS
engineer needs. Paths use placeholders and a development signing setup.

1. Build the host from the pinned runtime base (branch `runeclr/mobile-batch-interval`
   at `3126bbc9`), producing the platform-2 host executable, the host R2R
   composite, the entry assembly and the shared contract. Record the inventory
   digest, entry hash and contract hashes.
2. Sign the host with a normal development identity and the
   `get-task-allow` entitlement, install it once, and archive the install receipt
   (timestamp, bundle id, device, outcome). Nothing below may run before this.
3. Run the update generator for version A and B against the installed host
   assembly directory: it compiles the update sources with the pinned compiler,
   stamps a fresh nonce and the version, cross-compiles the owner composite,
   and emits the deployable set (owner dylib, update assembly, private
   dependency, IL-only helper, payload hash list) plus a manifest.
4. Sign the owner dylib as a development dylib; the UUID and the method offset
   must not change.
5. Push the deployable set to
   `<app-data-container>/Documents/payload/<run>` and read it back; compare the
   hashes with the manifest.
6. Launch with the console attached and the process stopped at start, passing
   only the expected version, the three expected values and the payload token:

   ```text
   <devicectl> device process launch --console --start-stopped \
     --environment-variables '{"RUNECLR_EXPECTED_VERSION":"A", ...}' \
     <bundle-id> -- --payload <run> --nonce <nonce>
   ```

7. Attach LLDB to the launched process, wait for the stop, resolve the owner
   module after it is mapped, set a breakpoint at `load base + 0x4050` (or by the
   `...Business__Execute` symbol before the owner loads), continue, and record
   the stop PC, the register, the executable region and the backtrace.
8. Let the run finish and read
   `<app-data-container>/Documents/results/<run>.json`; require the acceptance
   fields above and process exit 0.

The debugger step is essential: a host callback line, a module base or a
breakpoint address alone is not evidence by itself. The process must be stopped
before the owner loads, and the recorded PC must be the actual stop.

## Evidence appendix

Minimal redacted excerpts, a derived summary and the provenance of each excerpt
are in [docs/evidence/ipad-r2r-20261110](evidence/ipad-r2r-20261110/README.md).

The publication source also normalizes text line endings to LF. Together with the parameterized build paths, this means the current source and generated binaries need not be byte-identical to the measured snapshot above.
