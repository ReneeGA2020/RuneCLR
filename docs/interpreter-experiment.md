# Desktop interpreter lifecycle experiment

This is the reproduction procedure for [issue #1](https://github.com/ReneeGA2020/RuneCLR/issues/1).
An invocation is successful only when the launcher verifies runtime diagnostics
and the lifecycle results. A completed SDK build or accepted switch is insufficient.

## Source and build

The selected upstream base is `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`
in the separate `dotnet/runtime` repository. No runtime patch is required by this
procedure. Its product version is **12.0.0-alpha**, even though its build SDK is
`11.0.100-rc.1.26420.103`. RuneCLR continues to compile `net11.0` IL with its
own SDK. Do not substitute an installed SDK's framework libraries for those
built with this runtime.

Read that checkout's build instructions and install their required Windows
C++ tools. From a clean dedicated checkout/branch at the pinned base:

```powershell
# Run from the separate dotnet/runtime checkout.
./build.cmd -subset clr+libs -configuration Checked -librariesConfiguration Release -arch x64
```

The resulting private host layout is
`artifacts/bin/testhost/net11.0-windows-Release-x64`. Its
`shared/Microsoft.NETCore.App/12.0.0` directory contains the Checked CoreCLR,
interpreter, matching CoreLib and Release libraries. Use its adjacent
`dotnet.exe` and `host/fxr/12.0.0/hostfxr.dll` together. The build scripts acquire
their SDK into that checkout's `.dotnet` directory. The layout name describes
the libraries build; it does not imply that CoreCLR is Release.

`AssemblyDependencyResolver` requires an initialized real `hostpolicy`. A plain
Core_Root/corerun invocation does not provide this hosting contract. The launcher
therefore uses the built private `dotnet.exe exec --fx-version 12.0.0`, which
initializes hostpolicy and pins the framework without changing host runtimeconfig
files. This keeps the existing package resolver intact.

Existing Debug or WebAssembly artifact directories have no established
provenance for this experiment. Keep them untouched. The build above uses
Checked outputs; it does not install a shared framework or modify Program Files.

## Interpreter gates and bypasses

The following definitions refer to the pinned source, not arbitrary SDK releases:

- `src/coreclr/clrfeatures.cmake` enables `FEATURE_INTERPRETER` by default for
  desktop x64/arm64 **Debug and Checked** configurations. A normal Release build
  does not have that default.
- `src/coreclr/interpreter/interpconfigvalues.h` and `eeinterp.cpp` define
  `InterpMode=1` to interpret methods without R2R bodies outside CoreLib.
  CoreLib may JIT. Mode 2 excludes intrinsics and disables R2R. Mode 3 selects
  all methods and disables R2R and hardware intrinsics.
- `src/coreclr/vm/eeconfig.cpp` applies the R2R and hardware-intrinsic overrides.
  `src/coreclr/vm/jitinterface.cpp` still contains a JIT fallback when an
  interpreter compilation returns no code. Mode selection alone is therefore
  not evidence that every method completed interpreter compilation.
- `src/coreclr/interpreter/compiler.cpp` emits `Interpreter compile method`
  before compilation, and `Compiled method:` with interpreter bytecode after
  emission. The latter is stronger evidence. Both diagnostics are enabled
  in Checked builds. `DOTNET_JitDisasmSummary=1` separately reports JIT code.

The verified launcher uses mode 1 by default, disables R2R and tiering explicitly,
requests successful bytecode dumps for lifecycle callbacks and relevant generic
helpers, and rejects reported map JIT compilation. CoreLib JIT is expected in
this mode. Modes 2 and 3 are available for separately recorded experiments, with
the same map-evidence checks; mode 3 currently fails as described below.
These settings are an experiment configuration, not a host-enforced map policy
or a hostile-code boundary. Native runtime helpers and OS calls still exist.

## Reproduce the host experiment

From RuneCLR, after the private runtime build and layout generation:

```powershell
./eng/verify-interpreter.ps1 -RuntimeRepo E:/runtime
# If the checkout/layout lives elsewhere:
./eng/verify-interpreter.ps1 -RuntimeRepo <runtime-checkout> -RuntimeLayout <private-dotnet-layout>
# Separately reproduce the known full-interpreter failure:
./eng/verify-interpreter.ps1 -RuntimeRepo E:/runtime -Mode 3
```

The launcher builds the host and integration harness first. It then rebuilds
`tests/RuneCLR.LateMap`, deliberately excluded from the solution and host
dependency graph, without rebuilding project references. It verifies a new
map DLL timestamp and unchanged hashes/timestamps for the host and harness files.
Finally it runs the harness, Hello -> Arena -> Hello, and the late map through
the private `dotnet` host. Process-local interpreter settings are restored afterward.

Each run saves build logs, runtime diagnostics, binary hashes, source revisions,
configuration and outcomes under a fresh `artifacts/interpreter/` directory.
`request.json` records the requested mode and layout even if execution fails;
`evidence.json` is written only after all acceptance checks pass. The launcher
also checks that the native CoreCLR file embeds the selected source commit. Keep the raw
logs with the machine's experiment artifacts and record a portable result
summary here when actual interpreted execution is established.

The harness covers twenty successive sessions, ordinary managed failures,
host resource cleanup, cooperative quota violations, generic collections and
constrained value-type calls. Its dependency packages use the same map assembly
name and same dependency assembly name with dependency versions 1 and 2. The
A -> B -> A sequence retains only host-owned reports while checking version
selection, value/reference generic static reset, default-context exclusion,
and completed unloading. Supplying the late map adds the twelfth test.

## Measured status

On 2026-10-12, the private **mode 1** run completed all five acceptance criteria
of issue #1. This is interpreted map execution with a JIT-enabled framework,
not a runtime build without native code generation.

| Item | Measured result |
| --- | --- |
| Upstream base / runtime patch | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` / none |
| Runtime branch | `runeclr/interpreter-baseline`, clean tracked tree |
| Host base | `073bdb47a5cce3bfb4c717bbe75d6d79cead6aaf` plus issue-1 working changes; binary hashes in evidence |
| OS / architecture | Windows NT 10.0.26300.0 / x64 |
| Native toolchain | VS 2022 17.14.41, MSVC 14.44.35207, CMake 4.2.1, Ninja |
| Build | CoreCLR Checked, libraries Release; `FEATURE_INTERPRETER` present in generated Ninja definitions |
| Build SDK / host SDK | `11.0.100-rc.1.26420.103` / `11.0.100-preview.6.26359.118` |
| Reported runtime | .NET 12.0.0; local file version uses `42.42.42.42424` and embeds the pinned commit |
| Private layout | `artifacts/bin/testhost/net11.0-windows-Release-x64` in the separate runtime checkout |
| Mode / R2R / tiering | `InterpMode=1`, `ReadyToRun=0`, `TieredCompilation=0` |
| Harness | 12/12 passed, including twenty successive sessions, failure cleanup, private dependency A -> B -> A, generics and late map |
| Sample | Hello -> Arena -> Hello completed; both Hello starts are 1; all three contexts collected |
| Late IL | Compiled after the host, host files unchanged, executed and collected in both harness and sample |
| Map interpreter proof | Successful `Compiled method:` bytecode dumps for map callbacks and generic helpers; no map JIT compilation matched in the three diagnostic logs |

The final successful raw evidence directory in this checkout is
`artifacts/interpreter/20261012-140335-a477fa3b2f0641f9b7d10ea7ef087371`.
It contains `request.json`, `evidence.json`, `tests.log`, `sample.log`, `late-sample.log` and both
host/map build logs. These machine artifacts are ignored by Git. The separate
runtime build log is `artifacts/runeclr-interpreter-build.log` in that checkout.
For binary identification, the successful runtime hashes are:

```text
coreclr.dll: A9391606E33AFCD41E2F117EA2C83F4A045C5E0BDDC32320D50205A95FBF36DD
clrinterpreter.dll: 6F9C915791E34054415EF7A3E0FF763F6ABCA0025432D3161D190E73F6D26CCC
System.Private.CoreLib.dll: F3B765D3D04F816A418282BCA88B05679084D70B42A4FF88533C7F0D71346DB1
```

The installed .NET 11 desktop runtime separately passed the 12-test JIT baseline
and the sample. Those results do not supply interpreter evidence.

## Failed experiments and platform limits

The initial Core_Root/corerun experiment failed to load hostpolicy; its mode 1
run passed only the two cases that do not construct the dependency resolver.
The private host layout corrected this packaging/hosting mismatch. No host loader
or runtime source changes were needed.

Mode 3 was then retried with the correct private host layout. Seven lifecycle
cases completed, but the process hit the Checked assertion
`Thread::IsObjRefValid(this)` in `OBJECTREF::operator->`, called by
`InterpExecMethod`/`InvokeCalliStub`, during the manifest serialization/reflection
path. Exit code was `-1073740286` (`0xC0000602`). It did not finish the harness,
and the launcher did not emit successful evidence. Its raw log is under
`artifacts/interpreter/20261012-135731-9dd2d0a864474ff69b350d88b67d53a5`.
This failure is retained as an upstream investigation item before relying on
full-framework interpretation. Mode 2 has not been validated in this experiment.

Also, the pinned CoreLib source marks `AssemblyDependencyResolver` unsupported
on iOS. This was the resolver used by the original experiment. The later
[explicit resolver increment](package-resolution.md) removes that API and
passes the expanded 22-case suite on the same mode 1 layout. Issue #2 still
requires mobile hosting, dynamic IL execution and repeated unloading evidence.

This experiment does not establish iOS support, terminal CPU interruption,
allocation isolation, or a comprehensive security sandbox.
