# Collectible IL selection diagnostic — private candidate

On 2026-10-13 a private execution-selection candidate was implemented against
official runtime base `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
Local branch `runeclr/execution-selection`, commit
`6bb5f60be8de39b22fb19b95aea03e3252756cb3`; cumulative diff is 17 files,
125 insertions and 21 deletions. This is RuneCLR-specific diagnostic policy development,
not an official runtime defect or an upstream submission.

The [source plan](runtime-execution-selection.md) describes why this increment
is needed. The candidate implements opt-in selection mechanics; build and
execution acceptance are owned by the matching-build experiment and are not
established by the source checks below. The subsequent
[matching Windows acceptance](runtime-execution-selection-build.md) passes
the desktop selection matrix, native-caller inline control, full lifecycle
and player regressions, and four official loader tests. It is not production per-session
registration, a sandbox or terminal budget enforcement.

## Operator switches and scope

`DOTNET_RuneCLRInterpretCollectible=1` is a private startup diagnostic, default
off. `EEConfig::Init` initializes it false and `sync` reads the request once at
startup. The config definition is present in candidate builds even without
`FEATURE_INTERPRETER`; an enabled request there returns
`COR_E_PLATFORMNOTSUPPORTED`. Actual unsupported-build execution remains to be
tested. An unmodified runtime can still ignore this unknown switch; operators
must verify the candidate build identity and backend evidence.

The diagnostic covers metadata IL defined in collectible modules, including
trusted collectible plugins if they are loaded in the process. It does not use
an author-controlled assembly name or attribute to select UGC. Ordinary trusted
host/framework definitions remain under their normal native selection even
when instantiated with a collectible type argument. Dynamic methods without
such a definition module are outside this increment.

Two VM predicates make the bridge boundary explicit:

- `MethodDesc::HasRequiredInterpreterPolicy`: startup switch enabled, `IsIL()`
  and defining `GetModule()->IsCollectible()`. `IsIL()` includes instantiated
  descriptors. This broader predicate guards R2R lookup, native inlining,
  multicore code retrieval and tier eligibility, including wrapper descriptors.
- `MethodDesc::RequiresInterpreterBody`: broader predicate and
  `!IsWrapperStub()`. Runtime-created unboxing/instantiating ABI adapters may
  dispatch natively, while the underlying author's IL body remains required.
  Force-compilation and null-bytecode guards apply to bodies, avoiding an
  incorrect rejection just because a native ABI bridge has no own bytecode.

The independent [selection probe](execution-selection-probe.md) has an additional
boxed struct/interface/closed-delegate lane to test that distinction. Original
mode-1 probe evidence remains an independent diagnostic baseline.

## Patch locations and precedence

| Source | Candidate behavior |
| --- | --- |
| `inc/clrconfigvalues.h`, `vm/eeconfig.h/.cpp` | Recognize request in all candidate builds, store startup scalar, reject enabled unsupported build |
| `vm/method.hpp/.cpp` | Central definition-module policy/body predicates; explicit policy exclusion from tier eligibility |
| `vm/prestub.cpp` | Skip precompiled native body retrieval, gate entire direct/alternate/unrelated R2R search, skip multicore native cache retrieval |
| `vm/jitinterface.h/.cpp` | Out-of-line `CInterpreterJitInfo` constructor sets required flag after base constructor computes ordinary flags |
| `interpreter/eeinterp.cpp` | Read required flag before mode/method-set gate, bypass diagnostic selection refusal for required bodies |
| `vm/jitinterface.cpp` | Force interpreter loading independently of normal config for required bodies; native-inline refusal; reject OSR and compiler skip before native JIT fallback |
| `vm/interpexec.cpp` | Reject missing required bytecode before poisoning/calling the native path |
| `inc/corjitflags.h`, `jit/jitee.h`, managed `CorInfoTypes.cs`, SuperPMI formatting | Bit 33 required-interpretation flag and corresponding mirrors |
| `inc/jiteeversionguid.h` | Versioned compiler GUID `7c844228-f051-4b9b-9b8f-4e221230806f` |

Compiler skip for a required body throws managed `NotSupportedException` with
message `Required interpreted body was declined by the interpreter.` before
native JIT is attempted. Null bytecode and OSR guards also use managed
`NotSupportedException`. Malformed IL and ordinary compiler failures retain
their original error handling. Trusted unmarked methods retain ordinary native
fallback. No assertion was removed or bypassed.

The GUID changes the VM/compiler contract even when the host still uses native
JIT. Build matching CoreCLR, interpreter, native clrjit and any consumed
crossgen/JIT-interface tools; do not reuse the earlier native-only CID patch
replacement workflow. The separate CID and Apple generator patches are not
included in this diagnostic source commit.

## Scoped compiler-skip regression injection

`DOTNET_RuneCLRInterpreterRefuseMethods=SelectionUGC.Refusal.Entry:Reject` is
test-only diagnostic input, empty by default. The interpreter refuses a method
only when the startup diagnostic switch is enabled, the method-set matches,
and metadata exactly identifies:

| Item | Allowed fixture identity |
| --- | --- |
| Assembly simple name | `SelectionProbe.Refusal` |
| Namespace | `SelectionUGC.Refusal` |
| Class / method | `Entry` / `Reject` |
| Fixture IL | `static int Reject() => 73`, `NoInlining` |

Even `*` in the operator method-set cannot refuse arbitrary production methods.
This is explicit experiment input, not an automatic author-facing policy.
The matching method returns actual `CORJIT_SKIPPED` from the interpreter
compiler and emits:

```text
RuneCLRInterpreterRefusal: SelectionUGC.Refusal.Entry:Reject CORJIT_SKIPPED
```

The marked collectible mode-0 lane must throw the specified managed exception,
collect its context, and run twenty subsequent normal contexts. The unmarked
default-context mode-1 control must execute the exact same DLL bytes, see the
same skip diagnostic and successfully return 73 through native fallback, with
positive native-JIT evidence. Merely seeing the text or an exception is not
sufficient acceptance. The independent fixture/driver implements these lanes.

## Source checks and portable patch

[Portable patch](../eng/runtime-patches/0003-collectible-interpreter-selection.patch)
uses LF bytes, SHA-256
`b7d446243a099c6fc01c19bdc6e83c151eb4771112001fd9bd7185a0d1950ccb`.
It applies cleanly under `git apply --check` to the untouched official base.
The original baseline checkout stayed tracked-clean; the candidate worktree
was tracked-clean after its local commit. Nothing was pushed.

Twelve static source checks passed: three enum mirrors, unsupported-config
handling, whole-function R2R gating, skip-before-native-JIT ordering, required
compiler-gate precedence, fixture identity restriction, LF patch bytes and
SuperPMI symbol consistency, declaration-only header and out-of-line constructor
flag ordering. `git diff --check` passed. These checks are source
sanity checks, not executed policy coverage or substitutes for compilation.

The initial commit `1d395e3591a69bc3ce4fda0b963a8ecad3c92f1e` failed the
Checked native build with `C2027` in `jitinterface.h`: VM/DAC precompiled headers
can see only a forward declaration of `MethodDesc`, so the newly added inline
constructor member call was invalid. This is a local candidate implementation
error, not an upstream defect. The follow-up moves the constructor to
`jitinterface.cpp`, retaining base-then-required-flag ordering without adding
a circular include. The root experiment preserves that failed build and runs a
new commit-stamped rebuild; its outcome remains separate from source checks.

Initial source hashes, patch and check receipts are retained under
`artifacts/runtime-selection-source/20261013-initial`; the committed receipt
additionally binds the initial commit and normalized source bytes. Corrected
commit/patch and twelve checks are in
`artifacts/runtime-selection-source/20261013-constructor-fix`. The following
[executed subset](runtime-execution-selection-validation.md) covers host-native
mode-0 operation, wrappers, actual fail-closed compiler skip and native-inline
refusal; lifecycle/player/official regressions also pass. The full
[proposed matrix](runtime-execution-selection.md#validation-matrix-and-pass-gates)
still needs no-feature startup, concurrent/multicore/native-path controls,
production creation-time registration and mobile acceptance.
