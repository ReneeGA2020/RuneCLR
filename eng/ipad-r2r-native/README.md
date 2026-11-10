# iPad device R2R native host (unsigned) + post-install owner generator

Source-only package for the trusted-update route on an **iOS device (platform 2,
arm64)**: a fixed CoreCLR host app that loads an independently crossgen-compiled
R2R owner dylib from the app Documents directory, plus the generator that builds
those owners **after** the signed host has been installed.

This directory contains no binaries, no generated apps and no evidence logs.

## Layout

    host/src/      native wrapper: main.m, runtime.m, util.m, path_norm.c/h,
                   rn_test.c (C path tests), RunEntry.cs (managed result entry)
    host/test/     offline managed fixtures: Stamp, Contract, Harness
    host/tools/    build_host.py, generate_update_v2.py, selftest.py
    source/update-src/         managed host fixture sources (Host.cs, Entry.cs, ...)
    source/trusted-update-src/ RuneCLR.TrustedUpdate sources
    docs/CAPTURE.md            on-device loader/native-entry capture contract

## Prerequisites (not vendored)

- A private **ios.arm64** CoreCLR build containing `libcoreclr.dylib`,
  `System.Private.CoreLib.dll` and a device `crossgen2`
  (`--runtime-root`, optional `--crossgen2`).
- A matching **device framework layout** with `input/` (raw IL) and `layout/`
  (R2R components + device dylibs + `Microsoft.NETCore.App.deps.json`)
  (`--framework-root`).
- dotnet 11 SDK with Roslyn csc (`--dotnet`, optional `--csc`) and Xcode
  `iphoneos` toolchain (clang).

The package never downloads or rebuilds the runtime; point it at existing,
pinned build outputs.

## Build the unsigned host

    python3 host/tools/build_host.py \
      --framework-root <device-framework-root> \
      --runtime-root   <private-runtime-root> \
      --output         <fresh-output-dir> \
      [--crossgen2 <crossgen2>] [--dotnet <dotnet>] [--csc <csc.dll>] \
      [--bundle-id org.example.probe] [--min-os 15.3] [--label <name>]

It compiles the host fixtures from `source/`, crossgens them into
`TrustedUpdate.host.dylib`, links the Objective-C wrapper and writes an unsigned
`.app`, `inventory.json` and `results.json` (with every stage's argv/PID/exit and
stream hashes). It never signs, installs or touches a device.

The host exports these runtime markers on stdout:

    RUNECLR_PATH_OK pid=.. runId=.. payload=<abs> result=<abs>
    RUNECLR_PATH_REJECT pid=.. status=.. raw=..
    RUNECLR_NATIVE_CALLBACK owner=.. assembly=.. path=.. base=.. rtr_header=.. image_size=.. file_size=..

## Generate an owner (only after a signed install)

    python3 host/tools/generate_update_v2.py \
      --version A|B \
      --sources <update-fixture-sources> \
      --host-app <installed-signed-.app> \
      --install-receipt <archived-install-receipt.json> \
      --udid <device-udid> --bundle-id <host-bundle-id> \
      --framework-root <device-framework-root> --runtime-root <private-runtime-root> \
      --output <fresh-output-dir> [--nonce <32 hex>]

The generator compiles Update/Private/IlOnlyHelper from source with a fresh
nonce/version stamp, crossgens a composite owner (`--targetos:ios`), links
`TrustedUpdate.<A|B>.r2r.dylib`, verifies the READYTORUN component flag, MVID and
owner name, and writes a closed `deploy/` set plus `owner.json` (raw hash, UUID,
`_RTR_HEADER`, receipt binding). The install receipt must prove a signed install
(status/installed/signed, bundle, UDID, platform 2, install time before
generation, signed app digest and raw CoreDevice receipt hash).

Signing the owner changes its bytes; record the final signed hash separately and
verify the UUID and business-method code range are unchanged.

## Offline self-test (no device, no signing)

    python3 -B host/tools/selftest.py [--dotnet <dotnet11>] [--clang clang] [--keep]

Covers the C path-normalization suite (absolute/token/trailing slash/symlink
escape/flat result path), the managed RunEntry result contract (final
TRUSTED_UPDATE_SUCCESS result 216, not the intermediate 215; nonce/version/golden/
write-failure paths), install-receipt validation and the component-header parser.
All artifacts go to a temporary directory; fake fixtures are clearly synthetic and
are not device evidence.
