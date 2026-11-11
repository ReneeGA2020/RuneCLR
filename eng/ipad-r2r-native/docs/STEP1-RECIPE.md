# Step 1 device recipe (signed install -> postinstall A/B -> Business.Execute PC -> process exit)

This is the verified recipe from the 2026-11-10 dev run (474eb8ad + iOS 15.3 target
patches). Keep failures and successes in separate per-attempt directories.

## 1. Sign the host through the GUI Terminal window

Create a .command that copies the unsigned .app to a fresh destination, embeds the
wildcard development profile, derives entitlements from the profile, signs nested
dylibs, the main executable and the bundle with the configured identity, then runs
codesign --verify --deep --strict. Launch it with "open -a Terminal <file>" so the
signing happens in the user GUI session. The evidence receipt must record
start/end/exit. Do NOT sign in a headless SSH session (errSecInternalComponent).

## 2. Install once and keep the raw receipt

    xcrun devicectl device install app --device <UDID> <signed.app> --json-output <raw-install.json>

Then derive the generator install receipt from that raw file: status/installed/signed,
bundleId, deviceUdid, platform 2, installedUtc (must be before owner generation),
appDigestSha256 of the SIGNED app, rawReceiptPath + rawReceiptSha256.

## 3. Sign and seal the payload with the maintained deploy tool

Use the deploy tool that ships with this repository:

    eng/ipad-r2r-deploy/ipad_stage.py

(the earlier draft referenced eng/ipad_stage.py; that path does not exist). It already
implements the raw -> signed reconciliation: sign-payload -> sign-collect-payload ->
seal-payload -> push-payload. seal-payload recomputes every signed file hash, compares
the signed file set with the raw manifest, verifies the owner UUID and _RTR_HEADER are
unchanged by signing, and writes the final manifest. Do NOT hand-edit payload-files.txt
(that was a one-off workaround; its failure evidence is retained).

Signing changes every Mach-O file, so keep two hash sets and never mix them:

- raw/pre-sign: what the generator compiled and crossgen'ed.
- signed: what the device actually loads, recomputed after the GUI signing step.

## 4. Attach, capture PC, and let the process exit

One run must produce the PC plus the process-level termination, otherwise the PC is
only a debugger observation and the exit is only an app-printed string.

    1. Launch in the background with console streaming and a JSON receipt, stopped:
       xcrun devicectl device process launch --console --start-stopped --terminate-existing \
         --device <UDID> --json-output launch.json --environment-variables '<goldens>' \
         <bundle> --payload <runId> --nonce <owner nonce>
       Keep the devicectl process attached until the app terminates; its JSON then
       carries result.terminationResult.exitCode.
    2. Discover the PID from the running process list (a diff against a pre-launch
       snapshot, filtering TrustedUpdateHost.app/TrustedUpdateHost), because with
       --console the launch JSON is only written at termination.
    3. LLDB Python driver with SetAsync(False): target create <host executable>;
       device select <CoreDevice UUID>; device process attach -p <pid>.
    4. Verify the attach really is stopped: GetProcess() valid and
       GetState() == eStateStopped (lldb reports 5). A pending breakpoint alone is
       NOT proof of attach.
    5. breakpoint set -n TrustedUpdate_Update_TrustedUpdate_Business__Execute, then
       Continue(); the pending symbol resolves when the owner is dlopened.
    6. On the stop: confirm the stop function is Business.Execute, take the owner
       module by path, base = module.GetObjectFileHeaderAddress().GetLoadAddress(target),
       assert pc - base equals the owner's Business.Execute file offset (0x4050 on this
       build), and check "memory region <pc>" is an r-x __TEXT region.
    7. breakpoint disable --all, then SBProcess.Detach(). The app now runs with no
       debugger attached; the detached state is lldb.eStateDetached (9).
    8. Wait for devicectl to report termination, then read terminationResult.exitCode
       AND the native RUNE_IPAD_EXIT line, and copy Documents/results/<runId>.json
       from the device. All three must describe the same PID.

Capture assertions: one launch is accepted only when ALL of these hold. They are joint
necessary conditions, and any single mismatch rejects the run.

1. mode: the native start line names the intended mode (payload, probe or delivery) and the
   process does not print RUNE_IPAD_REJECT reason=conflicting-mode.
2. fresh result: the result JSON belongs to this run id (mtime after launch), and its run id,
   nonce and golden fields match the launched arguments; the launch PID, the attached PID and
   that result describe one process.
3. native exit: the same process prints RUNE_IPAD_EXIT with actualExit=0.
4. tool exit: devicectl reports terminationResult.exitCode 0 for the same PID.

Neither the native line nor the devicectl receipt proves a complete success on its own. The two
disagree in a recorded case: a payload-path rejection that called exit(123) was still reported by
devicectl as exit code 0 (see the Step1 exit evidence README and its exp2/ notes), so the tool
receipt alone can hide a failure, while the native line alone is app-reported text. The Step1
exit report therefore states its native-primary reading as scoped to that run, and this recipe
requires both plus the mode and fresh-result checks.

--probe and --delivery are mutually exclusive. runtime.m resolves the mode with
rn_start_mode_select() (path_norm.c) and exits 122 with RUNE_IPAD_REJECT reason=conflicting-mode
before coreclr_initialize, so a conflicting launch can never print a fake success. The pure C
selector is covered by rn_test.c cases mode-payload / mode-probe / mode-delivery /
mode-conflict-is-rejected.

Reference scripts in the 2026-11-10 experiment root: capture-exit.sh (launch, PID
discovery, bounded lldb wait, devicectl wait, result copy) and pc_driver7.py (attach,
breakpoint, PC/region record, detach). They are evidence-side scripts, not shipped
tools.

## 5. Measured artifact hashes (Step1, 2026-11-10)

| file | raw/pre-sign sha256 | signed sha256 |
| --- | --- | --- |
| TrustedUpdateHost (exe) | e3265c08785fb04066c2b9755a2c633cdb08d810381f0ba032326a50525b9140 | e0ccef540d5dcd3284c2c08a4c3a1a68c95f23c7f6b9c80a3d10707495353c4f |
| framework.dylib | 1949fab68b348d0ef2ec150417f02904a4369e7268109b94ac665d085b29cf21 | 8b569f2c1e5e340e49e910411a41d27389d5886bf144a807d13e927a3bc4b9d3 |
| TrustedUpdate.host.dylib | 7cce5ef44b5045da991a08b6d018ec0a56ba70d4ca8a6d166fc3a714a68f7984 | 416505ba57487608b763c9a48d9fa84193772af0a15c51286c0fdf2a94c0cbab |
| libcoreclr.dylib | 0c38cfff49c5d419ed4f7a974cb20d96a00bb25eab265ed38caaa7870b2eaaa7 | 5ebba42d58eca1a0fce077815f3c32aa1a32e106fd36a7e3bc4925e549332a01 |
| System.Private.CoreLib.dll (app copy) | 552e9fb713ff9f02f1da68840807116a9cd43c7b4baf9fcfb08d7fa09fafb9f6 | 552e9fb713ff9f02f1da68840807116a9cd43c7b4baf9fcfb08d7fa09fafb9f6 |

Signing appends signature data; the Mach-O UUID and the __TEXT vmaddr/vmsize stay
identical, which is what binds the PC to the same code range. CoreLib IL (runtime
build output d6f4a42a304facb8135b7bbf86b555645ff2b05a5bf5416ada357075c9b055bd) is a
separate layer from the app copy; record them separately.

Measured signing effect on identity: sign the copy that will be installed and compare
against that same copy, not against an older build. On the Step1 run the signed app was a
ditto copy of host-build-2 (exe e3265c08, UUID 93665D6B-1B77-3CED-B571-9793833514EB).
codesign appends the signature to __LINKEDIT, so the file hash changes, while LC_UUID and
all section bytes stay identical (exe 23/23 sections, __text 41421a4c / 9988 bytes;
__LINKEDIT 9976 -> 30208, file 108280 -> 128512). framework.dylib, TrustedUpdate.host.dylib
and libcoreclr.dylib keep their UUIDs and all sections too. host-build-1 (exe 00b451f1,
UUID 6DA894FD, __text 832a9418 / 10084 bytes) is a different earlier build, not the signing
source, so do not use it as the raw side of the comparison.

## Failure modes seen (kept for reference)

- "error: Process must be launched." when Continue() runs before a real stopped
  attach -> always check attach state first.
- A pending-symbol breakpoint that reports "no locations" is expected before the
  owner loads; it is not an attach failure.
- First run "payload file hash mismatch" when owners were signed after generation ->
  use the sign/seal ordering above.
- pc_driver5 (retained under pc-A5/pc-B5) continued once after capturing the PC and
  did not wait for termination or read the JSON receipt, so it never proved a
  process-level exit. capture-exit.sh + pc_driver7.py replace it for that gate.
- devicectl terminationResult.exitCode is discriminative in this environment: a
  deliberately wrong nonce produced exitCode 1 and devicectl exit 1. One early
  exit(123) payload-path rejection was still reported as exitCode 0; that path is
  not used as evidence and the quirk is recorded, not explained.
