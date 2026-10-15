# Required interpreter candidate acceptance

Measured on 2026-10-13. The private Checked candidate
`6bb5f60be8de39b22fb19b95aea03e3252756cb3` passes the five-lane desktop
matrix and the separate concrete native-caller inline comparison below.
The [new driver](../eng/verify-required-interpreter.ps1) requires an explicitly
committed candidate and a separately prepared matching private runtime layout.
It does not replace the installed runtime or alter the original
[mode 1 baseline driver](../eng/verify-execution-selection-probe.ps1).

## Measured candidate results

| Comparison | Actual result |
| --- | --- |
| mode 0 required, R2R/tiering on | 20/20 correct sessions, 20/20 collected; 26 body groups × 20 successful bytecode dumps; trusted `RunFrame` JIT positive; no reported UGC native body |
| Same bytes, switch off | 20/20 correct/collected; payload `Entry:Run` native JIT positive; no UGC bytecode |
| Required compiler skip | Actual scoped `CORJIT_SKIPPED` once; `NotSupportedException`; refused context collected; next 20 normal sessions/collection pass in same process, 520 bytecode dumps |
| Unmarked same-IL compiler skip | Actual scoped `CORJIT_SKIPPED` once; native fallback `Reject` JIT positive and executed value 73 |
| Boxed value/interface/delegate | 20/20 correct/collected; native trusted caller, five IL body groups × 20 bytecode dumps; no reported UGC native body |
| Concrete trusted generic caller, switch off | 20/20 correct/collected; 20 native trusted caller compilations; 20 actual successful UGC inlines |
| Same generic caller, required | 20/20 correct/collected; 20 native trusted caller compilations; 20 concrete UGC inline rejections and body bytecode dumps; no UGC-owner native compilation |

Runtime source is `E:/runtime-selection-20261013`, candidate commit above,
based on `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
Fresh matching CoreCLR/native JIT/interpreter/CoreLib outputs come from
`artifacts/bin/coreclr/windows.x64.Checked`; the independent private testhost
layout is `E:/RuneCLR/artifacts/execution-selection/runtime-build-20261013/layout`.
Each driver verifies source stamp, exact matching artifact hashes and clean
committed source before invocation. Native JIT diagnostics use the existing
`DOTNET_JitStdOutFile` facility to avoid interleaving with interpreter stdout.
Raw stderr separately holds managed values/collection markers.

| Evidence directory under `artifacts/execution-selection/` | Archive bytes | SHA256 |
| --- | --- | --- |
| `required-20261013-022325-b8c3d53d7dc045068b0b9e060f59d506` | 1,170,599 | `2eee91aa092053c3d0163fafa79a2d994846b9240ac9161d5dc0b419ace94d49` |
| `inline-20261013-022438-81dca336f79b44d2a06da425d9c497d9` | 616,437 | `0f23a9d9f677eeab03a08d68949bcfdc08f693557be25e2975de8683a932350b` |

Each `evidence.tar.gz` contains request/results, source/driver snapshots,
fixtures, method inventories, separate native/JIT/managed logs and a read-only
`independent-assessment.json`. The assessment rechecks raw method-group counts,
functional markers, inline decisions, actual scoped skips, module inventories,
and unchanged source/managed hashes. It records `appRerun=false`.

Two earlier driver failures remain in separate evidence directories.
`required-20261013-022100-6829c812b0d24e50853d50449a21fa68` had 20 correct
boxed sessions but only 19 intact constructor dump lines: background tiered
native JIT text split an interpreter `Compiled method:` line. Separating JIT
output preserved tiering and resolved that diagnostic corruption.
`inline-20261013-022347-60658c2e66c64ae9b9f626e8f4d9053a` completed its real
inline comparison but the driver expected enum-style `NEVER`/`FAILURE` strings;
actual JIT output uses `failed this callee`. The next independent run checks
that exact result and `noinline per IL/cached result` reason. These are
experiment-tool failures, not runtime defects, and no success receipt replaces
their original logs.

## Fixture and pass gates

The existing trusted [execution-selection fixture](execution-selection-probe.md)
keeps its default 20 independent collectible sessions and 26 executed method
groups. Its optional refusal modes use a separate valid IL assembly:
`SelectionProbe.Refusal`, `SelectionUGC.Refusal.Entry.Reject()`, token
`0x06000001`. This `NoInlining` body returns 73. A scoped diagnostic compiler
switch is intended to return actual `CORJIT_SKIPPED` for this body. It is not
invalid IL, a source-thrown managed exception or a production capability.

The measured candidate lanes use the exact same host/payload/helper/refusal
bytes, record child-scoped settings, separate native stdout from managed
stderr, and verify hashes before/after all runs:

| Lane | Configuration | Required evidence |
| --- | --- | --- |
| Required | mode 0, `RuneCLRInterpretCollectible=1`, R2R/tiering on | 20 correct sessions and 20 collected contexts; 26 bytecode groups each compiled 20 times; host `RunFrame` JIT positive; no reported UGC JIT fallback |
| Switch off | mode 0, switch 0, R2R/tiering on | Same 20 values/collection and metadata inventory; actual `Entry:Run` native JIT; no UGC bytecode dump |
| Required refusal/recovery | mode 0, switch 1, scoped refusal method set | Delegate call to collectible `Reject` throws `NotSupportedException`; rejected context collected after frame return; next 20 normal collectible sessions pass in the same process; no UGC native JIT |
| Unmarked fallback | mode 1, switch 1, same refusal method set; default ALC load | Same `Reject` IL is actually attempted by interpreter and skipped; existing native fallback executes and returns 73; `Reject` JIT positive |
| Boxed bridge | mode 0, switch 1, R2R/tiering on; separate collectible struct | 20 correct/collected sessions; cold and warm interface invocation plus a closed delegate on the boxed struct return 17; five actual IL body groups each compiled 20 times; native trusted `BoxedFrame`; no UGC JIT |

The test-only refusal switch must also reach the unmarked method. Restricting
the injection to required methods would turn the unmarked lane into an ordinary
JIT invocation without exercising skipped-compiler fallback. Native scoped
refusal diagnostics, return/exception values and body compilation observations
are complementary evidence; a printed refusal string alone is insufficient.

The [host optional branches](../eng/execution-selection-probe/Host/Program.cs)
share the ordinary default path unless explicitly selected. The refusal frame
returns only a weak context reference and copied exception type string, then
checks collection after the frame has returned. Delegates/reflection metadata
and the managed exception do not escape the collectible frame.

## Preparation measured separately

Using the ordinary RC1 SDK, all three projects build with warnings treated as
errors. The changed host default still passes 20/20 sessions and 20/20
collection. Its optional unmarked ordinary load executes the refusal body and
returns 73 with MethodDef `0x06000001`. This smoke test does not enable the
candidate switch and establishes no compiler-refusal or interpreter-policy
claim. Logs are retained at:
`artifacts/execution-selection/required-fixture-prepare-20261013-020357-c98b4d8ceb9543c08fb89e7f51a04e0a`.

The separate boxed fixture ordinary SDK smoke also passes 20/20 contexts:
both interface calls and the closed delegate return 17, with static and
constructor counts 1 in every context. Its logs are at
`artifacts/execution-selection/boxed-fixture-prepare-20261013-020738-fa4926dc24594199a328546d1ab896af`.
The struct body is distinct from runtime-generated unboxing/interface/delegate
bridges; future interpreter evidence must identify the underlying IL body,
while legitimate native marshalling bridges may remain native.

## Running after a matching candidate exists

```powershell
./eng/verify-required-interpreter.ps1 `
  -RuntimeRepo E:/runtime-selection-20261013 `
  -RuntimeLayout <new-private-testhost-layout> `
  -BuiltProduct E:/runtime-selection-20261013/artifacts/bin/coreclr/windows.x64.Checked `
  -CandidateCommit <validated-local-candidate-commit>
```

The driver checks candidate source ancestry, tracked-clean committed inputs,
source-stamped CoreCLR and exact layout/build SHA256 matches for CoreCLR,
native JIT, interpreter and CoreLib. Hostfxr/hostpolicy/private host hashes
are recorded as separate runtime inputs. The original official baseline and
all prior evidence remain unchanged. New failures always get new evidence
directories; no old success receipt can satisfy a new invocation.

## Limits

### Independent concrete native caller control

The separate [inline driver](../eng/verify-required-interpreter-inline.ps1)
does not affect the first five lanes or their 26/5 method-group counts.
It constructs `TrustedInlineCaller.NativeInlineCall<T>(int)` from its trusted
host definition using reflection, with concrete collectible struct
`SelectionUGC.Inline.Entry` as `T`. The trusted generic body invokes
`T.ReadInline(value)` through shared `IStaticProbe` static abstract dispatch.
The author body is one `AggressiveInlining` method returning `value + 31`.
The caller is `NoInlining` to preserve its own native body without preventing
inlining of its callee.

Managed checks require the definition's assembly to be non-collectible, its
constructed MethodInfo to retain the same trusted definition module, and its
concrete argument's assembly to be collectible. Runtime loader-allocator
ownership is a separate native fact; these managed checks do not claim to
directly inspect that allocator. The definition-module predicate must leave
the trusted caller native even when its generic arguments need collectible
lifetimes. Negative JIT classification is anchored to the definition owner;
a trusted generic method's signature may legitimately mention UGC arguments.

Ordinary SDK preparation passes 20/20 sessions and collection, with cold/warm
values 53 and 38. Metadata identifies author MethodDef `0x06000001` and
the trusted host definition/module. Logs:
`artifacts/execution-selection/inline-fixture-prepare-20261013-021858-d363c650856c446b96d035e4f1ff304d`.
This value smoke does not establish actual inlining. Candidate acceptance is
now measured separately using Checked JIT full-optimization diagnostics.
The off lane produces 20 actual `fgInline` `result 'success'` decisions
for this precise caller/callee, with reason `aggressive inline attribute`.
The required lane preserves 20 native caller compilations, rejects 20
concrete callee inline attempts (`failed this callee`,
`noinline per IL/cached result`), compiles 20 bytecode bodies and produces no
reported native UGC definition body. Both lanes retain exact same managed
bytes/inventory and observe 20 returned/collected contexts.

The inline control disables tiering for immediate full optimization, while
the initial five-lane acceptance keeps its R2R/tiering-on settings. Its JIT
diagnostics and body bytecode evidence are not native interpreter entry
samples.

R2R/tiering being enabled does not demonstrate rejection of a submitted R2R
method body: this fixture is IL-only, and pinned upstream already excludes
collectible modules from its ordinary R2R and code-versioning routes. Those
existing exclusions must not be credited to the new candidate. Direct hostile
R2R input, multicore cached native winners and concurrent preparation are
separate controls.

The ordinary tiny `AggressiveInlining` methods in the first five lanes run
inside interpreted UGC callers; the independent concrete native caller
control above measures that separate escape path. Neither
driver captures per-method native interpreter entries. Successful bytecode
compilation and correct body values remain distinct from that later entry
evidence. The scoped global collectible diagnostic is not per-session policy,
does not cover dynamic methods or stop unmarked new loader contexts, and does
not expand the production `managed-il-gameplay-v1` intake profile. Windows
acceptance alone establishes no mobile capability.
