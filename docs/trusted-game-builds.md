# Trusted game IL/R2R builds

eng/verify-trusted-game-builds.py is a stdlib-Python driver for the same-source TrustedGame sample. It builds one IL set, crossgens resident Host/Contracts/RuneCLR.TrustedUpdate and the late Update separately, stages separate IL and R2R layouts, and runs each layout once on the same private runtime.

## Usage

    python -B eng/verify-trusted-game-builds.py --sdk <dotnet> --runtime <runtime-repo> --output <new-output-directory> [--signed-ab]

The maintained runner self-test has no machine-specific output path. It creates a
fresh portable `tempfile.mkdtemp` root by default and prints the full path; pass
`--output <new-directory>` to choose a fresh root explicitly. An existing
`--output` is rejected before any check runs. The self-test does not launch
dotnet or the private runtime.

`--signed-ab` is an optional source/tooling mode; the default remains the
A-only four-image path. With it, Publisher and UpdateV2 are built separately
after Host with `BuildProjectReferences=false`, B gets its own fifth crossgen
output, and A/B same-name modules stay in separate IL/R2R directories and
processes. For each layout the driver signs the actual A and B layout bytes with
the existing Publisher using one generated demo key/SPKI for that lane, and both
stages use one releases root and one receipt. It stages A with multiplier 1,
then stages B with multiplier 2 against the same trust/receipt (asserting the
receipt changes A->B), then recovers B in a fresh process with multiplier 2
(asserting the B receipt is unchanged). Signed and staged module hashes must
match their layout inputs, and staged lookup follows the receipt's contentRoot
rather than assuming only one module remains. A/B layout hashes and MVIDs must
be distinct. The existing wrong-hash control is kept and B gets the same
wrong-hash control. Publisher uses the stock SDK while Host uses the supplied
private testhost. The demo key is not production key management, and the signed
gameplay result is not proof of which method body executed.

The runtime root must contain:

- artifacts/bin/coreclr/windows.x64.Checked/crossgen2-published/crossgen2.exe
- artifacts/bin/testhost/net11.0-windows-Release-x64/dotnet.exe
- artifacts/bin/testhost/net11.0-windows-Release-x64/shared/Microsoft.NETCore.App/12.0.0

The driver checks that the private package coreclr, clrinterpreter, clrjit and System.Private.CoreLib match the Checked build, and that CMakeCache is Checked. It does not build or modify the private runtime.

## What it does

1. Builds Host with the supplied SDK and an isolated artifacts path under the output directory. This also builds Contracts and RuneCLR.TrustedUpdate.
2. Hashes Host, Contracts and RuneCLR.TrustedUpdate.
3. Builds Update later with BuildProjectReferences=false, using the same SDK, source, configuration and artifacts path.
4. Rechecks the resident hashes and rejects a Host output or deps file that contains TrustedGame.Update.
5. Crossgens Contracts, RuneCLR.TrustedUpdate, Host and Update as four independent inputs. No composite image is made.
6. Stages il/host, il/update, r2r/host and r2r/update. Each host layout gets a runtimeconfig for Microsoft.NETCore.App 12.0.0 with rollForward Disable.
7. Runs the IL and R2R layouts on the same private dotnet.exe with the same child-scoped switches (ReadyToRun 1, InterpMode 1, tiering/QuickJit/OSR off, rollForward Disable). The switches are selection requests only.
8. Runs each layout once for functional validation and once with a wrong expected module hash. The expected hash for the functional run is derived from that layout's actual Update DLL.

The driver records commands and exits, stdout/stderr, source pins, runtime/tool hashes, original IL and derivative SHA-256/MVID, crossgen maps where produced, and PE managed-native-header/R2R status in commands.json, source-pins.json, products.json, image-maps.json and results.json.

The command record is written before a process is spawned and contains argv, cwd, the child environment settings and a start status. A normal exit records the integer exit code and both streams. A timeout records ended status `timeout`, the partial stdout/stderr bytes that were available, and no invented process exit code. A failed spawn (for example a missing executable) records the OSError type/message, argv, cwd and ended status `os-error`, keeps empty logs, and raises a useful error without a process exit. `check=False` returns a nonzero process; `check=True` writes the logs and records the exit before raising. These are plain logs and JSON, not a campaign/freeze framework.

## Captured source pins

The source snapshot is a captured project-source/build-config set: the three baseline sample project directories, and with `--signed-ab` also the Publisher and UpdateV2 project directories; the compiled `src/RuneCLR.TrustedUpdate` `.cs` and `.csproj` files, and the existing repository-level build configuration files (`Directory.Build.props`, and `global.json`, `Directory.Build.targets`, `Directory.Packages.props` or `NuGet.config` when present), plus this driver, the sample script and the two TrustedGame docs. `bin`/`obj` are excluded. The driver resolves the requested SDK executable (path or `PATH` lookup), hashes that actual executable, and reports it with the tool pins where practical.

This is **not** a full hermetic compiler/reference-pack closure: it does not enumerate the C# compiler (`csc`), framework reference packs, NuGet package contents or every transitive tool. Those remain outside the captured set and should be pinned separately if a future delivery requires them.

## Expected result

Both layouts must print and exit with:

- normal results 1, 3, 6 and Score 6 / Ticks 3
- negative delta CallbackFailed and Closed, with no mutation
- TRUSTED-GAME OK

The wrong-hash run must exit 3 with ContentHashMismatch. The Host must load the shared Contracts identity from the Host layout, not a module-local copy.

## Scope and limits

This establishes functional behavior and separate IL/R2R artifact kinds. It does not prove which method bodies actually executed, R2R versus interpreter selection, whole-method coverage, a complete native execution mode, performance, assembly unload, or iOS/mobile/device behavior. There is no native PC observer, interpreter dump, debugger or sampling. The sample remains stock desktop managed/JIT scope; same-source R2R composition is a build/layout proof, not an execution-mode proof.

If the supplied SDK or runtime layout is incompatible, the driver retains the concrete command, exit, stdout/stderr and failure in results.json rather than building a private runtime or inventing a fallback.

## Offline observation verification

`eng/verify-trusted-game-observations.py` is the maintained offline entry for a
retained trusted-game observation run. It is deliberately separate from the
build driver and does not execute Host, Publisher, crossgen, signing, a private
CLR, a device or a remote machine.

    python -B eng/verify-trusted-game-observations.py \
        --run-root <retained-run> --output <new-directory>

`--output` must not already exist and must not be the run root or inside it.
The tool refuses both cases before any write. A passing invocation creates a
new `report.json` and `report.sha256`; a validation failure creates no report.
Exit code 0 means the current checks passed and a report was written, 1 means
the output location was refused, and 2 means validation or I/O failed.

Every invocation rebuilds the expected call set from that run root: the nine
commands and their raw logs, the five IL/R2R image SHA-256/MVID identities, the
named map row for Host/A/B, actual PE executable sections and PE
exception-directory RUNTIME_FUNCTION records (the directory may live in
`.text`; the helper's `pdata()` name does not imply a literal `.pdata`
section), staged manifests, signed A/B payloads, and the
stage-B/recover receipt document and hash. There is no `--expected` input and
no replay against an externally supplied descriptor. The 36 calls are then
replayed directly against that fresh result. Stage-A's receipt is treated as
superseded: its recorded hash is checked, but no retained A receipt document
is required.

The report separates current observation checks from overall acceptance. On
the retained run-2 data the current checks are 18 target-image bindings and 18
sealed runtime-image observations, while `overallAcceptance`,
`interpreterIdentityProven` and `targetMethodBodyProven` remain false. A
runtime-image PC is only shown to lie in an executable section of the sealed
`coreclr.dll`; it is not interpreter identity or method-body proof. The
original checker failure and parent failure are read from the retained
`checker-full.json` and `failure.json` and marked historical and not
recomputed.

Receipt checks compare the decoded receipt document with the captured B signed
bytes and compare the payload with the staged manifest. They do not perform
signature cryptography. The signing private key is not opened, read, hashed or
included in the before/after pins, and the signing directory is not
recursively traversed. The preflight-recorded `dotnet.exe` SHA-256 remains an
external pin and is not verified here. Contracts and
RuneCLR.TrustedUpdate are bound by actual IL/R2R SHA-256 and MVID; they have no
target method binding. Publish and assembly-identities commands are bound by
name, argv paths, lifecycle, logs and raw hashes, but their products are not
re-run.

The Publisher DLL, SDK/private `dotnet.exe` bytes and runtime DLLs other than
`coreclr.dll` are not hashed here; command argv/logs and the coreclr image are
the bound evidence. The assembly-identities JSON is raw-hash pinned but not
re-parsed. These remain external pins or out-of-scope checks, not new
acceptance claims.

The self-test has a self-contained synthetic run root and needs no machine
artifacts or private runtime:

    python -B eng/test-trusted-game-observations.py

The portable default selftest is also invoked by `eng/verify.ps1` and the
three-OS CI matrix. That is CI configuration, not evidence that every OS has
executed it.

To additionally replay one immutable retained root read-only:

    python -B eng/test-trusted-game-observations.py --run-root <retained-run>

The optional run reports the same target18/runtime18 result and verifies that
all before/after input and raw pins are unchanged. The test does not write to
the retained root and does not leave system temporary directories behind.
