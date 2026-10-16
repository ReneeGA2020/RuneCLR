# Trusted update iOS simulator experiment

This experiment builds a fixed CoreCLR host and a host composite, installs that
app in a private iPhone 17/iOS 27 simulator, then creates independent A/B R2R
owners only after installation. Each version is launched in a fresh process.
The noncollectible update context lives until that process exits. The same
process does not unload native code or switch versions.

The configured Mac is reached through Cindy SSH alias mac-172-26-202-95. The
driver must be copied to that Mac by the operator and run from the RuneCLR
checkout with Python 3:

    python3 eng/ios-trusted-update.py all --root /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr --output artifacts/ios-trusted-update/<unique-output>
    python3 eng/verify-ios-trusted-update.py --output artifacts/ios-trusted-update/<unique-output>

Local structural checks, with no simulator and no author execution:

    py -3 eng/verify-ios-trusted-update.py --local-audit --output artifacts/ios-trusted-update/<unique-local-output>

build records the matching runtime commit, private SDK, crossgen2 hash, managed
inputs, generated wrapper and fixed bundle hashes. run installs the bundle first,
compiles and copies A/B payloads into Documents, and retains each attempt under
the unique output directory. A and B use different owner composite filenames,
TrustedUpdate.A.r2r.dylib and TrustedUpdate.B.r2r.dylib. On this runtime the
native-image cache key is that filename only, not a path or hash. A dylib of
the same name already inside the app bundle is not the downloaded version.

Before a process starts, the host audits each owner with the read-only Mach-O
inspector (inspect_macho and require_platform for iossimulator). The receipt
records byte count, SHA-256, UUID, platform 7/iossimulator, and the one
executable segment static vmaddr, vmsize, fileoff and filesize.
provesNativeExecution stays false. Those fields are file structure only. They
are not a runtime program counter and do not prove R2R native execution.

The host also rejects a wrong owner filename or a dylib without an exported
RTR_HEADER before starting the runtime. The fixed runtime does not fall back
to IL when the Apple native-image callback fails: the non-Windows path
fail-fasts. This experiment does not catch that fail-fast and does not start a
process to observe it. The negative log says fixedRuntimeFailFastNotIntercepted.
Choosing the other version means a later process start after another preflight.

The generated Apple callback prints OwnerCompositeExecutable, assembly path,
resolved absolute owner path, dlopen base, RTR_HEADER pointer, image size and
file size. The receipt adds the callback file SHA-256 and requires that path
and hash to be the downloaded owner. The entry capture binds one selected
TrustedUpdate R2R method PC to that owner symbol range. An InterpreterStub
event for the IL-only helper is recorded separately and is not R2R native
execution.

A passing simulator receipt requires unchanged fixed-host hashes, post-install
payload hashes, install-before-download timestamps, distinct A/B owner names
and process IDs, Mach-O structural acceptance, callback identity, an
owner-bound native PC, and helper identity/call evidence. Missing LLDB symbols,
owner mapping, callback, or native method range remains an explicit blocker.
Static Mach-O acceptance or a process that merely stayed up is not native
execution.

This is simulator evidence only. It does not establish physical-device code
signing, iOS device loader behavior, runtime changes, collectible R2R unloading,
or same-process A/B switching. Unloadable hot-update R2R is not a current goal.

## Measured result - 2026-10-15

Local synthetic preflight passed and is not a simulator receipt. An independent
lead recheck wrote
artifacts/ios-trusted-update/lead-recheck-20261015-macho-audit/local-audit.json.
It records distinct owner filenames TrustedUpdate.A.r2r.dylib and
TrustedUpdate.B.r2r.dylib, accepts one synthetic iOS Simulator image, and
rejects a missing RTR_HEADER, a mismatched owner filename, platform ios,
and a same-name bundled dylib. provesNativeExecution stays false. No runtime
program counter was captured.

The remote run on mac-172-26-202-95,
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-trusted-update-20261015-macho-audit,
built and ad-hoc signed the fixed host, booted a simulator and installed the
app. Post-install composite crossgen for version A then failed. crossgen2
exited -6 with AccessViolationException in
MethodDefinition.get_RelativeVirtualAddress, called from CopiedMethodILNode
while RewriteComponentFile rewrote TrustedUpdate.Update.dll. The Mach-O
object TrustedUpdate.A.r2r.obj is 42476 bytes and was not linked. No owner
dylib, callback or method-entry receipt exists, and results.json was not
written. After the crash the component DLL is 0 bytes. The fixed-host composite
did emit TrustedUpdate.host.obj and its component assemblies, so this does
not show that every composite Mach-O crossgen fails.

Copied logs: artifacts/ios-trusted-update/remote-macho-audit-20261015/.
The simulator created for this run was shut down and simctl delete was invoked;
no simulator was left booted. This is not runtime IL fallback, device signing,
or downloaded native execution.

## Crossgen isolation - 2026-10-15

The in-place composite crash reproduced without booting a simulator or rebuilding
the host. The pre-crash snapshot snapshot/TrustedUpdate.Update.dll is 4096 bytes,
SHA-256 3639cd7795124670d4b4dc5541b336fc571f0fdbdc457053f89a6410559d106a, and was
not modified. crossgen2 again exited -6 with AccessViolationException in
MethodDefinition.get_RelativeVirtualAddress, through CopiedMethodILNode.GetData,
while RewriteComponentFile rewrote the component. TrustedUpdate.A.r2r.obj is
42476 bytes and was not linked. The in-place Update.dll is 0 bytes afterward.
ReadyToRunObjectWriter.EmitObject opens that output with FileMode.Create, and
this command used the input directory as the output directory, so the crash
leaves a truncated component. The fixed-host composite still shows that not
every composite Mach-O rewrite fails. This is not native execution.

The single-assembly Mach-O control also exited -6, but it is a different
failure. No object was written. crossgen2 threw, before codegen, that Mach-O
ReadyToRun output is only supported for composite images. Program.cs rejects
non-composite non-PE formats. An unhandled exception aborts the process, so
the exit code matches the access violation without identifying the same bug.
Copied evidence: artifacts/ios-trusted-update/remote-crossgen-isolate-20261015/.

## Split-directory composite - 2026-10-15

The same preserved inputs succeeded when the composite object was written
outside the input directory. No simulator was booted and no dylib was linked.
input/TrustedUpdate.Update.dll stayed 4096 bytes with SHA-256
3639cd7795124670d4b4dc5541b336fc571f0fdbdc457053f89a6410559d106a. crossgen2
exited 0. out/TrustedUpdate.A.r2r.obj is 42476 bytes. Rewritten components are
non-zero: Update.dll 3072, Contract.dll 2560, AnchorHost.dll 6144, and
AnchorEntry.dll 3072. The log only emits the Mach-O object and four PE
components; it has no AccessViolationException. Copied evidence:
artifacts/ios-trusted-update/remote-crossgen-split-20261015/. This shows the
in-place rewrite was the crash, not composite Mach-O output itself. It does
not prove native method execution.

## Linked owner image - 2026-10-15

The split-directory object linked to out/TrustedUpdate.A.r2r.dylib. It is 66800
bytes, SHA-256 806e9fc303004202814483af7659f104cc452396b87e366bb868277e52cb9bfd,
UUID cf9e82d0-8d59-31e4-8bb2-eda1d222c7e3, platform 7/iossimulator, with one
executable __TEXT segment at static vmaddr 0. The ad-hoc signature is present,
and nm shows _RTR_HEADER. The object file remained 42476 bytes. The offline
checker reports proves_native_execution false. No simulator was booted.
eng/ios-trusted-update.py now writes owner crossgen output under
lane/crossgen-out and fails if an input dll changes. The local synthetic
preflight passed at
artifacts/ios-trusted-update/local-preflight-20261015-crossgen-out; its 557-byte
image is not this dylib. A linked simulator image is not a runtime method entry.

## Simulator load - 2026-10-15

One startup-selected run used the split-output driver, SHA-256
cb72e246cb59d0ad771497f0ac494a12935ed247a820dd7d02ec6a563fd7052b. Crossgen did
not hit the access violation, and the A input Update.dll stayed 4096 bytes.
Separate processes 8505 and 8597 loaded TrustedUpdate.A.r2r.dylib and
TrustedUpdate.B.r2r.dylib. Each callback path and hash matched the downloaded
owner. Bases were 0x14a8b8000 and 0x114cac000, with image size 81920. The host
bundle hash was unchanged. The created simulator was deleted, and none remained
booted.

nativeExecutionProven is false. No nativeEntry was recorded. The capture
selected _TrustedUpdate_AnchorHost_TrustedUpdate_Driver__Run at file address
1792 because its name contains both Update and Run. Update.Run and
Business.Execute exist later in __managedcode and were outside that breakpoint
range. InterpreterStub was recorded only for IlOnlyHelper.Compute.
PrivateBehavior.Value and VersionValue.Get were interpreter-compiled. The
captured stdout has no TRUSTED_UPDATE_SUCCESS, so managedSuccess is false, while
both processes exited 0. Loading the owner and a zero exit do not prove R2R
native execution. Receipt:
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-trusted-update-20261015-simload/results.json.

## Execute breakpoint recapture - 2026-10-15

A second load reused the existing host and prepared A output. No crossgen was
rerun. The capture selected __TEXT Business.Execute at file address 5472, ending
at Update.Run 6384. The downloaded dylib hash remained
5287adf15b833579245ea02b78c33440333f6fde4a2a973153f26408486d9c89. Process 9635
loaded that owner and exited 0. There is no native-entry.json. The interpreter
compile list includes HostApi.Echo but not Business.Execute or Update.Run. The
address breakpoint is created from the dlopen entry callback, which can run
before the owner module is mapped, so a miss does not prove the native body was
absent. Native execution remains unproven. Receipt:
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-trusted-update-20261015-entry-execute/results.json.

## Business.Execute entry - 2026-10-15

After the address breakpoint was armed on dlopen return, one A process hit it.
Process 10362, address-breakpoint locations 1. The PC was 5277013344, equal to
owner base 5277007872 plus file address 5472, and below base plus 6384. The
stop module was the downloaded TrustedUpdate.A.r2r.dylib, SHA-256
5287adf15b833579245ea02b78c33440333f6fde4a2a973153f26408486d9c89, in an
executable, non-writable mapping. The symbol is Business.Execute. The
interpreter stub was not counted. Version B was not loaded in this run, and the
captured stdout still has no TRUSTED_UPDATE_SUCCESS. This is one simulator
method entry, not device signing, native unloading, or same-process switching.
Receipt:
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-trusted-update-20261015-entry-return/results.json.

## Business.Execute entry for B - 2026-10-15

A separate process loaded prepared B without rerunning crossgen. Process 10894
hit Business.Execute at PC 5241820512, which is owner base 5241815040 plus file
address 5472 and below base plus 6384. The module was the downloaded
TrustedUpdate.B.r2r.dylib, SHA-256
e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589, matching the
prepared file. The mapping was executable and not writable. Address-breakpoint
locations were 1. The interpreter stub was not counted, and the captured stdout
still has no TRUSTED_UPDATE_SUCCESS. The simulator was deleted. This pairs the
A entry but does not add device signing, native unloading, or same-process
switching. Receipt:
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-trusted-update-20261015-entry-return-b/results.json.

## Managed result for A - 2026-10-15

One A launch reused the host shell and the existing owner. Host.dll and
Entry.dll were rebuilt with Console.Out.Flush after the status lines. Crossgen
was not rerun, and TrustedUpdate.A.r2r.dylib stayed
5287adf15b833579245ea02b78c33440333f6fde4a2a973153f26408486d9c89. Process exit
was 0. managed.stdout.log contains RUNECLR_EXIT=0 and no TRUSTED_UPDATE_SUCCESS.
managed.stderr.log contains TRUSTED_UPDATE_BEGIN expected=A, HOST_ECHO=41,
UPDATE_BUSINESS private=41 echo=42 callback=43 helper=130, UPDATE_RUN result=215,
and TRUSTED_UPDATE_SUCCESS version=A result=216 MANAGED_BYTES=41040. Those
values match the source formulas. iOS Console.WriteLine was captured on stderr
with an os_log prefix, while runtime printf stayed on stdout. This proves the A
managed path completed. It does not recapture a native PC, and B's managed line
was not part of this launch. The simulator was deleted.

## Managed result for B - 2026-10-15

One B launch reused the flushed host shell and the existing B owner. Crossgen
was not rerun. The dylib hash stayed
e9dcf6ff668d3dbb14b242d2dfc3b64d605152ae06aab45430a2392215a1a589. Process exit
was 0. managed.stdout.log has RUNECLR_EXIT=0 and no success line.
managed.stderr.log contains TRUSTED_UPDATE_SUCCESS version=B result=216,
PRIVATE_VALUE=200, IL_HELPER_RESULT=607, and HOST_REFLECTION_PRIVATE=200
HOST_REFLECTION_HELPER=607. The business path still uses the fixed value 41, so
result 216 matches A; the private assembly value 200 is the B-specific result.
The simulator was deleted. This does not add a new native PC sample.

## Startup approval gate on the simulator - 2026-10-15

A new iPhone 17 / iOS 27 simulator booted, and the flushed host app was installed.
Prepared B was copied into that app container. Its Update.dll hash remained
d83ec82a13f71d54dc9817ffde348d30711a6145f12b59d803513a1ea8b373f5. The approval
record hash was 64 zeroes, so the startup plan returned NotApproved before
simctl launch. No business process id exists. The simulator was then deleted.
Receipt: ios-trusted-update-20261015-sim-plan-reject-b/results.json on the Mac.

A matching approval then took the same install path and was allowed to launch.
Simulator 4A19680F-572F-4677-BF7B-3BDF35DE4D23 booted, the host was installed, and
prepared B was staged. The approval hash matched
d83ec82a13f71d54dc9817ffde348d30711a6145f12b59d803513a1ea8b373f5. simctl launch
exited 0. stderr contains TRUSTED_UPDATE_SUCCESS version=B result=216,
PRIVATE_VALUE=200 and IL_HELPER_RESULT=607. stdout still has no success line,
but it does record RUNECLR_EXIT=0. The simulator was deleted. Receipt:
ios-trusted-update-20261015-sim-plan-accept-b/results.json on the Mac.




## Clean receipt - 2026-10-16

The sections above are earlier launches. They do not replace the later clean receipt. A clean checkout of commit c268026 at /Users/editor/RuneCLR-experiments/RuneCLR-c268026 produced artifacts/ios-trusted-update/rerun-c268026-20261016-01. python3 eng/verify-ios-trusted-update.py --output on that directory exited 0 with passed=true and nativeExecutionProven=true. A and B both recorded RUNECLR_EXIT=0 and TRUSTED_UPDATE_SUCCESS result=216. After success the host printed GC.GetTotalMemory(false) as MANAGED_BYTES=74248 for A and MANAGED_BYTES=74264 for B. That snapshot is not a forced collection and not physical footprint.

A separate 2026-10-16 relaunch of version A, not that receipt process, stopped at libsystem_c exit while the process was still alive. footprint --noCategories printed phys_footprint 24 MB and phys_footprint_peak 24 MB, a formatted summary with 16384-byte pages, not --format bytes. The same process printed MANAGED_BYTES=41040 and result=216. Do not treat 24 MB as an exact byte count or as the c268026 process.

The host is not a Unity host and not a supported distribution SDK. The only phone is an iPhone XR locked to iOS 18.7. Do not build or install an iphoneos runtime for it. Do not repeat the c268026 simulator receipt. Issue 12 stays open.
