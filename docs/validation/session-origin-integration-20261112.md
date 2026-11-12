
# Session-origin integration branch (2026-11-12)

Status: review-ready integration branch, not merged into `main` or `runeclr/dev`.

| repository | branch | base |
| --- | --- | --- |
| `ReneeGA2020/RuneCLR` | `feature/session-origin-integration-20261112` | `origin/main` `cbac2a657793dca7f22b1e1feff4aab26b898b4e` |
| `ReneeGA2020/runtime` | `runeclr/session-origin-integration-20261112` | `fork/runeclr/dev` `474eb8ad7230122cc0d34318b25d673da63fd138` |

The archived experiment (`experiment/session-origin-20261112`,
`runeclr/session-origin-20261112`) is the source reference only; this branch is
rebuilt on the current integration bases and does not copy the old files over
the newer upstream state.

## Opt-in contract

- Runtime: capability bit 0 (`SessionOriginCapability`) is reported only when the
  process is started with `RuneCLR.EnableReflectionPolicyOriginScan=true` in its
  runtime configuration. An absent switch means **disabled**.
- When enabled, `RuneCLRReflectionPolicy_GetStackLoadContext` returns the
  managed `AssemblyLoadContext` of a bounded 16-frame stack walk; saturation or a
  walk error returns no context and the caller fails closed.
- Host: `PrototypeRequireOriginScan` on `MapRunOptions` and
  `HostContractSessionOptions` binds the capability before author loading and
  throws `PlatformNotSupportedException` when bit 0 is absent, so no author
  assembly loads. The option asserts the capability; it does not enable scanning
  by itself, and it requires `RequireInterpreter` plus an API policy.
- Consequence: a host that does not opt in keeps the pre-existing
  reflection-policy behavior - no stack scanning and no capability bit. A host
  that wants origin scanning must set both the process startup switch and the
  host option.

## Tests

`eng/verify-runtime-session-origin.py --expect-fixed` drives the matrix against a
matching private runtime layout: fixed, frame, retirement, conflict, overflow,
disposal, default-off, capability-on, capability-off, map-gate-on/off,
host-gate-on/off, toggle-on/off and invalid option combinations. The `default-off`
mode starts without the switch and requires capability bit 0 to be absent.

Measured results for this branch are recorded in the integration artifact
(`session-origin-integration-20261112/`), together with the fresh source,
runtime, toolchain and binary identities and the before/after pins.

## Measured on 2026-11-12

- Runtime build: `build.cmd -subset clr -configuration Checked -arch x64` on
  `474eb8ad7230122cc0d34318b25d673da63fd138` plus the five source files below;
  SDK `12.0.100-alpha.1.26480.102`, CMake 4.2.1, MSVC 19.44.35229.0; build exit 0.
- Private binary identities: `coreclr.dll`
  `42933493ffeb20c2b97baca808afc7d5f3d1cadeaa48354e2502a5f77134d7d9`,
  `clrjit.dll` `dd432f9e7f4383be0e352a76ed592a47cb0b1831d89371fe1e25e2c666b13898`,
  `clrinterpreter.dll` `83b2f6bbb25f95e01904788b7fb9d8d44a3b594e96bde2b626d8869350ef56b3`,
  `corerun.exe` `cda4877d19e629ba8175cc55fa4553e4006f87cc53e26a3c054f93a62198b7ee`,
  `System.Private.CoreLib.dll` `578089837a4d6695e0b581827bb50e21d8e005a546e926c136511d9bb5311fae`.
- Private layout: fresh Checked native output and CoreLib over the `runeclr/dev`
  Release managed framework (same source pin); the matrix verifies the native
  outputs and CoreLib against the fresh build hashes.
- Matrix: `SESSION_ORIGIN_FIXED LOCAL_UNCOMMITTED_SOURCE_MANIFEST PASS`,
  16 modes, 696 pins, runtime head `474eb8ad` plus the five uncommitted source
  files; `default-off` reports capability 0, `capability-on` reports bit 0, and both
  host gates reject before author loading with `PlatformNotSupportedException`.
- Host stock runtime: `REFLECTION_POLICY_STOCK_TESTS PASS` and the lifecycle suite
  `156/156`.

## Limits

Native walker status 1 (saturation) and status 2 (walker error) have only
indirect coverage; the compiled-only suppressed child has no author frame;
unmanaged entry, AOT/mobile, global all-load and the published walk-cost bound
remain out of scope. No sandbox, native/R2R body, device or unload claim is made
by this branch.
