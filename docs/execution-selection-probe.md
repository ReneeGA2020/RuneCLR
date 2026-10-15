# Execution selection regression fixture

Measured on 2026-10-13 on Windows x64. This independent trusted fixture gives
future runtime selection patches a small, repeatable method inventory. It does
not change RuneCLR production projects, controlled packages, policy, or the
existing lifecycle/player test lanes.

## Measured baseline

The operator SDK control passes 20/20 sessions with 20/20 collectible contexts
observed collected after the execution frame returns. The private unpatched
Checked CoreCLR mode 1 lane passes the same 20/20 sessions and 20/20 collection.
All 17 returned values match their expected values in every session, including
fresh per-session constructor/static counts. The JIT control records actual
`SelectionUGC.Payload.Entry:Run` compilation; the interpreter lane records no
reported `SelectionUGC` JIT fallback and 26 distinct successful bytecode method
groups, each with 20 dumps (520 total).

`DOTNET_JitNoInline=0` leaves normal JIT inlining enabled; this does not establish
whether a future selectively trusted JIT caller can inline UGC IL. In mode 1
this fixture's non-CoreLib host is also interpreted.

| Executed path | Observable result |
| --- | --- |
| Payload `.cctor` / `.ctor`, base `.ctor` | static/instance counts both 1 in every context |
| Property getter and `AggressiveInlining` tiny method | 7 and 12 |
| Generic class `.cctor` / static next / generic method | 1 and 19 |
| Compiler-generated capturing delegate body/constructor | callback returns 11 |
| Virtual override and default interface body | 13 and 17 |
| Actually evaluated managed exception filter | filter count 1; failure handled |
| Private dependency `.cctor` / `.ctor` / getters / tiny method | 1, 1, 30, 38 |
| Private generic class `.cctor` / next / generic method | 1 and 41 |
| Private dependency capturing delegate body/constructor | callback returns 42 |

Inventory includes 27 MethodDefs from two collectible assemblies. The unused
base `VirtualRead` implementation is inventoried but is not counted among the
26 executed bytecode groups; virtual dispatch reaches the override. Constructed
generic dumps use `System.__Canon` class sharing and `Identity[int]` method
instantiation. Inventory includes assembly/module MVID, declaring type, token
and definition signature. A later native entry trace must additionally bind
these to the actual module bytes and instantiated MethodDesc.

## Isolation and reproduction

The [host](../eng/execution-selection-probe/Host/Program.cs) loads payload and
its private helper into a fresh collectible ALC. It shares only the trusted
contract assembly. Results are a host-owned value record and a weak context
reference; reflection metadata stays within the `NoInlining` execution frame.
Forced GC is a diagnostic after that frame returns, not a runtime scheduling
policy. Managed result markers use stderr to avoid interleaving them with
buffered native dump stdout; the driver retains each stream separately.

From the repository root using PowerShell 7:

```powershell
./eng/verify-execution-selection-probe.ps1
```

The [driver](../eng/verify-execution-selection-probe.ps1) builds only the four
fixture projects. It uses the private RC1 SDK, then separately starts the
source-private runtime with child-scoped settings. It verifies the baseline
commit, tracked-clean runtime source, source-stamped CoreCLR and byte-for-byte
matching Checked native/interpreter/CoreLib outputs. No global environment or
installed runtime is changed. Every invocation requires a fresh evidence
directory; failed receipts and streams remain available.

- SDK: `11.0.100-rc.1.26425.128`; control runtime
  `.NET 11.0.0-rc.1.26425.128`.
- Source: `E:/runtime`, branch `runeclr/interpreter-baseline`,
  `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, no runtime patch.
- Layout: `E:/runtime/artifacts/bin/testhost/net11.0-windows-Release-x64`,
  framework version `12.0.0`; actual runtime `.NET 12.0.0-dev`.
- Configuration: CoreCLR/interpreter/CoreLib Windows x64 Checked; framework
  libraries Release, matching the existing private baseline.
- Settings: `InterpMode=1`, `ReadyToRun=0`, `TieredCompilation=0`,
  `InterpList=1`, `InterpDump=*:*`, `JitDisasmSummary=1`, `JitNoInline=0`.
  The driver clears inherited `DOTNET_` / `COMPlus_` overrides only in children.

| Runtime file | SHA256 |
| --- | --- |
| coreclr.dll | `a9391606e33afcd41e2f117ea2c83f4a045c5e0bddc32320d50205a95fbf36dd` |
| clrinterpreter.dll | `6f9c915791e34054415ef7a3e0ff763f6abca0025432d3161d190e73f6d26ccc` |
| System.Private.CoreLib.dll | `f3b765d3d04f816a418282bca88b05679084d70b42a4ff88533c7f0d71346db1` |

## Evidence and limits

Successful run:
`artifacts/execution-selection/20261013-015010-f556c2e16b104e7f83403b4c6fd96411`.
`request.json` binds settings/runtime hashes, `results.json` binds fixture
hashes, both method inventories bind definitions, and
`independent-assessment.json` independently checks all 520 dump records,
20 result markers in each lane, matching inventories and unchanged
source/driver snapshots. Additional private host hashes are in that assessment.
The archive `evidence.tar.gz` is 2,423,560 bytes, SHA256
`0fac41bbcfc4bbf15b76b8deca788b7c6a4192c2ba7d5eafca1f9b89dfc7e3e2`.

Earlier attempts remain in sibling directories: the initial driver stopped
after successful builds because `$Host` is a reserved PowerShell variable; a
later strict check saw only 19 complete private closure-constructor dump lines
because a managed `PASS session=9` split native `Compiled method:` text. Both
are fixture tooling defects, not upstream runtime failures. The split-stream
host resolves that issue without relaxing the 20-per-target requirement.

Correct result values, accepted environment switches and successful bytecode
compilation are distinct evidence. This baseline combines executed functional
paths with successful bytecode dumps and a working reported-JIT observation
channel; it does not collect per-method native interpreter execution entries,
enforce interpretation against a different policy, reject R2R input, or prove
that every possible UGC path has no JIT bypass. Trusted-host inlining,
selective host/framework native execution and future runtime-backed marking
need separate patched-runtime controls. No mobile-platform capability is
established by this Windows result.

This is trusted experimental IL. Default interface methods, delegates and
the exception fixture do not extend the production `managed-il-gameplay-v1`
accepted profile. See [the execution strategy](execution-strategy.md) and
[CoreCLR integration](coreclr.md) for the actual policy boundary.
