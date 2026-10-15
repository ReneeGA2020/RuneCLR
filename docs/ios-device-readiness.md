# Physical iOS device readiness

A read-only inspection on 2026-10-13 local date checked the configured remote
Mac without installing an app, changing signing settings or exporting
credentials. This is preparation evidence, not physical-device execution.

| Item | Measured result |
| --- | --- |
| Xcode | 27.0, build 27A266a |
| iphoneos SDK | 27.0 |
| devicectl inventory | 32 simulator entries and one cached physical iPad |
| Physical hardware | iPad Pro 11-inch, 2nd generation; iPad8,9; supports arm64/arm64e |
| Cached device OS | iOS 27.0.1 |
| Cached preparation | Paired; developer mode enabled |
| Present connection | tunnelState=unavailable; ddiServicesAvailable=false; last connection 2026-10-08 |
| Codesigning identities | One valid identity; one Apple Development identity |
| Provisioning profiles | 209 decoded; 14 unexpired iOS profiles; 3 unexpired development profiles |
| Development profiles covering cached physical device | 3 |
| Development profiles matching a currently valid signing identity | 1 |
| Development profiles matching org.runeclr.deviceprobe | 0 |
| Profiles matching device, valid identity and proposed probe bundle together | 0 |

Profile checks compared certificate fingerprints and device coverage locally;
private keys, device identifiers, account/team identifiers, profile contents
and certificate identity names are not included in this record. Availability
of signing material does not authorize use of any unrelated application's
bundle/profile. A cached device listing does not prove it is presently reachable.

## Read-only refresh — 2026-10-13 05:36 China Standard Time

A new CoreDevice query at 2026-10-12T21:36:38Z found 38 entries: 37 explicitly
classified as simulated and one physical iPad8,9. The physical device remains
paired with developer mode enabled, but its tunnel is unavailable and DDI
services are unavailable. Its last recorded connection remains
2026-10-08T08:40:00Z. There is currently no reachable physical iOS target for
the RuneCLR device experiment. Xcode27.0/27A266a and iphoneos SDK27.0 are
available.

The signing inspection again found one valid Apple Development identity and
209 decoded profiles, including 14 unexpired iOS profiles and three unexpired
development profiles. Three cover the cached physical device, one matches a
valid signing identity, and none matches org.runeclr.deviceprobe. No profile
matches that device, identity and proposed bundle together. These are distinct
intersection checks; an available identity alone does not prepare this probe.
Reconnect the intended device and provide a development profile for the chosen
project bundle and signing team before a physical-device run. The
[sanitized readiness receipt](../artifacts/device-readiness/20261013-053638/ios-readiness.json)
contains only nonpersonal capabilities, counts and an identity-set hash. No
application was installed or run, and no signing material was changed/exported.

The Android tools were inspected on Windows without launching them.
D:/RuneCLR-Android/sdk/lldb does not exist, but the pinned NDK r27c contains:

| Tool | Actual path beneath D:/RuneCLR-Android/sdk/ndk/27.2.12479018 | SHA256 |
| --- | --- | --- |
| Windows host LLDB | toolchains/llvm/prebuilt/windows-x86_64/bin/lldb.exe | 448e636bb8b4f65bf01f41dbc243ab589cf8409f95409593c3549e1efd85f02f |
| Android x86_64 server | toolchains/llvm/prebuilt/windows-x86_64/lib/clang/18/lib/linux/x86_64/lldb-server | 873ecfdf9fe588ace2a64122ac7f4b77b8c18bf684eb608653e0b127c9b651c7 |
| Android ARM64 server | toolchains/llvm/prebuilt/windows-x86_64/lib/clang/18/lib/linux/aarch64/lldb-server | 338d31eb9d395f05f22cbe14ede5023551a821ef615bb9472b304a9eb623f802 |

File availability establishes debugger preparation only. Server deployment,
ptrace/attach permissions, native symbol compatibility and actual method-entry
capture remain unverified. No emulator/device/debugger process was started by
this inspection.

## Read-only availability refresh recorded on 2026-10-13 10:31 China Standard Time

CoreDevice still lists one physical iPad8,9 in state unavailable. No physical
iOS target is reachable. The simulator booted list and local ADB device list
were empty at observation; later budget debugger/emulator runs have their own
ownership and cleanup receipts. Signing profiles were not reinspected and no
signing settings or physical-device applications were changed. The
[sanitized availability receipt](../artifacts/device-readiness/20261013-023116Z/results.json)
records only capability/state observations.

## Read-only availability refresh recorded on 2026-10-13 12:48 China Standard Time

The current CoreDevice query lists forty entries and one physical iPad8,9.
Its developer mode is enabled, but its tunnel remains unavailable. No physical
iOS target is reachable and no iOS simulator is booted. DDI availability is
not established by this query; signing profiles were not reinspected. The
[sanitized receipt](../artifacts/device-readiness/20261013-044831Z/results.json)
and [executed query](../artifacts/device-readiness/20261013-044831Z/query.py)
retain this observation without personal identifiers, signing changes or
physical-device application operations. Android capture runs have their own
separate emulator ownership and cleanup records.

## Read-only availability refresh recorded on 2026-10-14 15:14 China Standard Time

A fresh CoreDevice query still lists forty entries and one physical iPad8,9.
Developer mode is enabled, but the tunnel is unavailable; DDI availability is
not established. No iOS simulator is booted. Signing profiles were not
reinspected and no physical-device application or signing material was changed.
The [sanitized receipt](../artifacts/device-readiness/20261014-071436Z/results.json)
and [executed query](../artifacts/device-readiness/20261014-071436Z/query.py)
record this observation. Reconnect the intended device before attempting a
physical run; the separate iphoneos.arm64 build and bundle/profile matching
remain prerequisites.

## Read-only availability refresh recorded on 2026-10-14 22:15 China Standard Time

The [fresh sanitized query](../artifacts/mobile-derived-ledger/ios-functional-receipts-20261014-attempt1/frozen/device-readiness/results.json)
records UTC14:15:30.788753:42 entries and one physical iPad8,9 with developer
mode enabled. Its tunnel remains unavailable and DDI services are unknown.
No iOS simulator is booted. No signing inspection/change or physical-device
application operation occurred. This refresh accompanies the new simulator
functional run; it does not establish physical-device execution.

## Read-only availability refresh recorded on 2026-10-15 02:00 China Standard Time

The [sanitized inventory](../artifacts/device-readiness/20261014-180023Z/results.json)
still reports one physical iPad8,9 with developer mode enabled and an unavailable
CoreDevice tunnel. DDI services remain unknown. This query does not inspect
signing, boot or shut down simulators, or install a physical-device application.
The current matching mobile batch experiment therefore continues on its
separately owned simulator/emulator targets.

## Read-only availability refresh recorded on 2026-10-15 04:17 China Standard Time

The new query at UTC `2026-10-14T20:17:39.383449+00:00` reports 51 CoreDevice
entries and one paired physical iPad8,9 with developer mode enabled. Reachable
physical targets remain zero: the tunnel is unavailable and DDI availability
is unknown. Of 209 decoded profiles, 14 are unexpired iOS profiles and three
are development profiles. Three cover the device; one also intersects a valid
development identity. None matches `org.runeclr.deviceprobe`, so the full
bundle/device/identity intersection is zero. No signing, installation, pairing
or device-setting operation was performed.

The sanitized receipt and separate review are retained at
`D:/RuneCLR-Android/device-build/device-readiness-refresh-20261015-attempt1/readiness.json`
and `review.json` in the same directory. Their SHA256 values are respectively
`1e01e973d9d3c7ad266816652799f0f4c7d705e4d81c4163ad06a54171e9d38f` and
`0c9cd196b843f6422b4a824f3cad147145b090510917312a12f4b5b261ec67c9`.
The query's old `existingDeviceRuntimeProduct=false` field describes its
original simulator worktree; the subsequently accepted device runtime and
unsigned application are recorded in their separate build receipts.

## Read-only refresh after live simulator capture - 2026-10-15

At `2026-10-15T06:12:55.923512+00:00` (14:12 China time), a new CoreDevice
query reports 52 entries: 51 simulated and one physical, with zero unclassified.
The physical target remains unavailable: its tunnel is `unavailable`, developer
mode is `enabled`, and DDI availability is unknown. Its last connection is
`2026-10-08T08:40:00.000Z`. This does not establish physical execution after
the separate successful simulator method-entry capture.

The [sanitized result](../artifacts/device-readiness/20261015-live-capture-refresh-attempt1/results.json)
and [executed query](../artifacts/device-readiness/20261015-live-capture-refresh-attempt1/query.py)
retain only counts, capability states and the last connection date. Their
SHA256 values are `e95c9afd62fe0af56eeb856be148bf85505c631f16aa9118e84f7a4c162e80f3`
and `4deac13777f7dd66d801e81696ad1d9693db27283391e3130c0a1b806c510b01`,
respectively. The query did not reinspect signing profiles, pair a device,
change settings, install an application or run a physical application. The
previously missing profile intersection remains historical evidence; the
current signing intersection was not remeasured.

Reconnect the intended physical device to the configured Mac and unlock it
until Xcode/CoreDevice reports a usable tunnel and DDI services. Then confirm
the intended project bundle/signing team and supply a development profile
covering that bundle, the connected device and an available development
identity before physical application installation.

## Next device experiment (unchanged prerequisites)

The later one-shot read-only refresh at `2026-10-14T21:24:39.158592+00:00`
(2026-10-15 05:24 China time) still reports zero reachable physical targets
and zero `org.runeclr.deviceprobe`/device/development-identity profile
intersections. The cached paired iPad has developer mode enabled; its
tunnel remains unavailable and DDI availability unknown. One development
identity is valid, but no matching bundle profile exists. Sanitized actual
receipts are retained at
`D:/RuneCLR-Android/device-build/device-readiness-refresh-20261015-attempt2/readiness.json`
and `review.json` in that directory. Their SHA256 values are
`14e6f896ed3c81c846ec5ecf566e39ee989ffdf9fa21962e322836792523169c` and
`85eb484d1df7460062315fe0b4406c8404c494804e3823cb4a57e0efb2626345`.
The query is reused once without retry, pairing/settings/profile/signing
changes, installation or execution. Its legacy runtime-directory fields
remain scoped to that older location; the newer
[unsigned device scene child](ios-device-scene-acceptance.md) is independently
accepted in its separate layout.

The [2026-10-15 source-build readiness check](../artifacts/device-readiness/20261015-sourcebuild-readiness-attempt1/results.json)
confirms one paired physical iPad8,9 with developer mode enabled, but its
CoreDevice tunnel is unavailable and DDI service availability is unknown.
There is one valid development signing identity; no current profile matches
the candidate org.runeclr.deviceprobe bundle, device and identity together.
Only sanitized counts/capabilities are retained. No profile, signing setting,
device setting or physical application was changed.

An independent device runtime build can proceed while these run prerequisites
are unresolved. Xcode27, iphoneos SDK27, the private RC1 SDK and scoped build
tools are actually available. The matching3126bbc/710936a source is tracked
clean. A subsequent [separate device-target runtime build](ios-device-batch-build.md)
now passes native/CoreLib/compiler checks. Its subsequent
[matching framework](ios-device-batch-framework.md) and
[unsigned application/post-build author binding](ios-device-application-build.md)
also pass; physical-device execution remains unperformed. The
[source-reviewed build plan](../artifacts/device-readiness/20261015-sourcebuild-readiness-attempt1/source-build-plan.json)
uses the actual target -os ios -arch arm64, sysroot iphoneos and the private
ios.arm64.Release product directory, rather than simulator outputs. Building
native/CoreLib/crossarch tools requires neither a signing credential nor a
connected device. A separate worktree/build must retain source provenance,
interpreter configuration, actual iOS Mach-O platform and compile sysroot
evidence. Readiness is preparation; this receipt does not claim a build.

Reconnect the intended physical device and verify a usable CoreDevice tunnel
and DDI services. Select the project's intended signing team and bundle ID,
then prepare a development profile covering that bundle, connected device
and available development identity. No credentials/profile were created or
modified by this inspection.

Compose a matching framework/application from the new ios.arm64.Release
runtime-critical products; simulator Mach-O artifacts cannot be installed on
the device. Establish actual interpreted
execution of IL delivered after host installation, repeated fresh static
state, ordinary author-failure recovery and completed context retirement.
Keep source/configuration/native/CoreLib/compiler/signing provenance and
physical-device logs separate from simulator evidence. The current
[Release package functional acceptance](ios-r2r-release-packages.md) remains
an independent simulator result.
