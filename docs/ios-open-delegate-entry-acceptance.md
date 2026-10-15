# Open Delegate Interpreter Entry Acceptance

On 2026-10-15, a new owned iOS 27 ARM64 simulator passed all three prepared
interpreter entry paths for the same nine fresh-author method groups. This
extends the earlier [two-path capture](ios-fresh-author-entry-acceptance.md).
The original closed-delegate capture and its frozen tools remain unchanged.

## Fixture And Actual Execution

The [new fixed-source compiler](../eng/prepare-ios-open-delegate-author.py)
retains the original capturing lambda in `Helper.Finite`. It instantiates
`OpenInvoke<T>` using the closure's runtime type, creates `Action<T>` from the
original method, checks that its Target is null, then calls it with the closure
as the explicit receiver. The compiler-generated method remains
`<>c__DisplayClass0_0.<Finite>b__0`. The Payload source is byte-identical.
The expected logs remain `private-finally`, `private-delegate`.

This trusted diagnostic fixture uses reflection to construct that exact call
shape. It does not expand the gameplay capability policy or establish a
reflection sandbox. A stock CLR smoke first verified the exact logs and
preserved method identity; the subsequent simulator run establishes the
interpreter behavior separately.

The unsigned native/runtime/trusted application are identical to the earlier
capture, using [runtime3126bbc/tree710936a](mobile-batch-builds.md), upstream
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Exact accounting is selected:
phase-acquire-load1, derived-ledger1, batch interval0, InterpMode0,
InterpretCollectible0, ReadyToRun1 and tiering0. No runtime patch, host rebuild
or change to the live capture driver was needed.

Both author DLLs were compiled after installing and reading back the owned
diagnostic application's bytes. The actual target was PID81740, nonce
`77f2c96de0ad481e8103b6fd7bb3ca2c`.

| Observation | Result |
| --- | --- |
| Nine selected method groups | All covered, zero capture errors |
| Actual path kinds | Function entry, ordinary child, delegate child |
| Original closure | Delegate child at file PC `0x2e6df8` |
| Closure meter | Terminated execution, phase1, cleanup owner equals definition meter |
| Delegate opcode pointer x26 | 5230610808; advance8 gives first opcode address5230610816 |
| Full budget harness | 15 cases, all73 contexts collected |
| Target process | LLDB observes exit0, native completion markers match |
| Inputs | Installed bundle/authors and original app unchanged |
| Owned simulator | Shut down and deleted after evidence was copied |

There were16,434 breakpoint hits and nine retained entries. These hits are
not opcode/invocation counts. The callback validates native bytes/UUID/slide,
loaded author MVID/token/path/hash, current frame, first-opcode address,
definition owner and thread cleanup owner. This proves selected entry/child
dispatch samples; complete invocation tracing and individual opcode execution
are outside the claim.

## Evidence And Recheck

Remote output: `fresh-author-open-delegate-entry-20261015-attempt1`.
The [downloaded archive](../artifacts/ios-open-delegate-entry/20261015-attempt1/evidence.zip)
is271,613 bytes, SHA256
`605fe0537e97081f64501d15ba13578fef87249d15a4810a922e448e98c28068`.
It retains original and transformed author source, fresh DLLs, compiler
responses/process logs, live capture, managed results, installed inventories,
owned cleanup and the frozen tool/binding snapshots.

The [specialized offline reviewer](../eng/review-ios-open-delegate-entry.py)
first runs the pinned complete fresh-author archive reviewer, then requires
all three actual paths and this exact closure in cleanup-phase delegate
dispatch. It additionally checks the compiler variant, baseline and transformed
source bytes, compiler source hash and process output hashes. The
[actual local review](../artifacts/ios-open-delegate-entry/20261015-attempt1/local-review.json)
passes, including13 semantic corruption controls on copies of the actual
managed results.
The [independent actual-archive review](../artifacts/ios-open-delegate-entry/20261015-attempt1/independent-review-controls.json)
rejects11 modified copies. This includes disguising the closure as an ordinary
child while consistently changing its PC/register/summary fields, and changing
the transformed source while recomputing its recorded hashes. The combined
general and specialized checks are both required.

```sh
py -3 eng/review-ios-open-delegate-entry.py --archive-root artifacts/ios-open-delegate-entry/20261015-attempt1/extracted
py -3 eng/verify-ios-open-delegate-entry.py
```

The second command passes23 synthetic checks of the additional requirements,
including22 corruption rejections. It does not replace the complete actual
archive review or the existing43 live-driver controls.

The [physical-device refresh](ios-device-readiness.md) at
2026-10-15T06:12:55Z found one physical iPad record with an unavailable tunnel
and zero reachable physical targets. Device execution remains pending: connect
and unlock the intended device on the configured Mac, establish tunnel/DDI
availability, then verify development signing for the intended bundle.
