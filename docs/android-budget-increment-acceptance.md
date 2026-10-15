# Android acceptance of the minimal counter increment

On 2026-10-14 the new Android x64 Release application passes15 budget scenarios
and73 collectible-context collections in one process. This is the exact
minimal counter candidate, with a new matching framework composite and APK.
Method-entry sampling on this application and physical devices remain open.
The later [offline observer contract](android-budget-increment-entry-preparation.md)
passes separately; its receipt contains no live entry samples.

## New Application

The [core and source bindings](mobile-budget-increment-builds.md) fix commit
112e97408de1ae1c2a6cbd2967dcd250cd2d491c and tree
91673a7980bda79006259e525741fecb04324444. The
[CoreLib ABI and framework increment](android-budget-increment-layout.md)
passes before the executable bridge is added. The new
[APK adapter](../eng/android-budget-increment-apk.py) fixes the parent driver
hash, source-proof bytes, seven actual core product hashes and original
six-DLL/30-source input manifest. Bridge compilation also checks the actual
185 input IL files and fixed metadata-inspector hash before crossgen.

The executable bridge yields186 composite inputs,187 outputs and201 layout
files. The Mac bridge/layout zip is15104124 bytes, SHA256
8d8c6f8d162f5a06ac9ce7f16e68a2dfb33165bbac30db6e38d53e2c9472cf31;
all224 indexed files are checked after download. Existing framework R2R
images and the old application are not inputs to this new composite.

The fresh APK package is net.dot.RuneCLR_Budget_fccd23cb758f, SHA256
d351f14895b347a8c1e267be7b3fc811e6ccd2acda0f7ababa27186e727425be.
Its packaged native and managed bytes match the new layout. Original author
IL is excluded from the APK and copied after installation unchanged.

## Actual Run And Recovery

The [actual run receipt](../artifacts/mobile-budget-increment/android-apk-20261014-attempt1/run-all-9a0e42f2d7d34deab0ee000a18f2dde3/mobile-run.json)
records PID4751, nonce9a0e42f2d7d34deab0ee000a18f2dde3, owned API35 x64
emulator5556, InterpMode0, collectible diagnostic0, ReadyToRun1 and no debugger.
Java, native and managed identities match. Initialization, native execution,
managed and instrumentation exits are zero. Both actual installed inventories
contain203 identical hashes, including original author DLLs and the APK.

The [strict audit](../artifacts/mobile-budget-increment/android-functional-audit-20261014-attempt2/results.json)
checks all73 rows, terminal catch/filter suppression, constructors, bounded
finite/infinite cleanup, resource release, static reset and bad/good recovery.
All15 semantic/input corruption controls reject altered records. It reports
mobileVerified=true and nativeEntryProof=false. Normal execution measures96
opcodes, finite cleanup38, execution exhaustion8192 and infinite cleanup4096;
these are observed ledgers. The owned app is uninstalled and emulator shutdown
is recorded in the [cleanup receipt](../artifacts/mobile-budget-increment/android-apk-20261014-attempt1/cleanup.json).

An [independent frozen-product review](../artifacts/mobile-budget-increment/root-android-acceptance-review-20261014-attempt1/results.json)
rechecks all 224 indexed archive files, 201 layout files, actual APK contents,
203 before/after observations and 42 raw run files. Four additional transport
controls reject a changed hash, malformed nonempty line, missing observation
and duplicate observation. Its
[scenario supplement](../artifacts/mobile-budget-increment/root-android-acceptance-review-20261014-attempt1/supplement-results.json)
independently matches all 73 rows, exact logs and recovery roles, mapped native
paths and the 69-plus-121 asset transfer recovery. This review binds all seven
critical products through receipts and compile evidence; it directly rehashes
the three downloaded native ELF images, without claiming local inspection of
the four compiler binaries retained on the Mac. It performs no device actions
and does not supply method-entry evidence.

## Preserved Transfer And Observer Failures

ADB's local socket connection reported10055 after installation while transferring
assets. The installed APK was retained. A later controller reads existing hashes,
preserves69 verified files and transfers only the121 missing files in one tar.
All190 non-native assets match before post-install author transfer. Two failed
resume prechecks are preserved; neither transferred assets or launched the app.
The [successful resume receipt](../artifacts/mobile-budget-increment/android-apk-20261014-attempt1/resume-transfer-attempt3/results.json)
binds the controller, archive and unchanged original APK/driver.

A first run precheck rejected the valid tilde in Android's native-library path
and never launched instrumentation. Its receipt is retained. The successful
[controller](../artifacts/mobile-budget-increment/android-apk-20261014-attempt1/run-controller-attempt2.py)
adds the observed path character and gathers each203-file inventory with one
actual sha256sum command, avoiding hundreds of short-lived ADB connections.
APK/native/managed execution bytes and settings remain fixed.

The bulk output's CRLF combined with Windows text-mode output produced CRCRLF
in the raw hash logs. The old auditor verified all business rows but retained
404 empty-line parsing errors and mobileVerified=false. The separately named
[new auditor](../eng/mobile-budget-increment-audit.py) ignores empty lines while
retaining strict nonempty hash/path parsing, duplicate rejection and equality
of every observation with the complete expected inventory. Original log bytes
and the old audit result are preserved. These are experiment transport/observer
issues, not upstream CoreCLR defects or failed budget execution.

This run does not establish exhaustive invocation traces, Android method-entry
samples, mobile finalizer/concurrent termination, physical devices or a
RuneCLR100/1000 [batched meter](budget-batching-experiment.md).
