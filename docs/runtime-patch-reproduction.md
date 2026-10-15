# Reconstructing the private runtime source from exported patches

The exported patches now have a source-only reproduction check. On 2026-10-13,
five desktop patches applied to official base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de reconstruct all thirty-six changed
files in candidate099dacd07d8d890822f7422f895337733457ab3c byte-for-byte against
its Git blobs. The collectible CID and Apple generator fixes also apply
separately on top. This establishes exported-source coherence, not another
runtime build, mobile execution result or upstream-approved implementation.

The [checker](../eng/verify-runtime-patch-stack.py) reads committed source from a
tracked-clean candidate checkout, copies only affected files into a fresh
private evidence directory, and applies patches there. It rejects output inside
the runtime checkout. It does not edit either runtime source or installed .NET.
Git blob hashes use committed bytes; Windows checkout files can have different
raw hashes due to CRLF conversion. Runtime build receipts retain the actual
compiler-input hashes separately.

~~~powershell
py -3 -B eng/verify-runtime-patch-stack.py --runtime-repo E:/runtime-finalizer-20261013 --output artifacts/runtime-patch-stack/new-run
~~~

| Stage | Exported patches | Measured result |
| --- | --- | --- |
| Desktop required interpretation and budgets | 0003 through0007 | Five application checks and applications exit0; exact36-file099dacd reconstruction |
| Optional upstream defect fixes | 0001 and0002 | Both checks and applications exit0 in a separate source snapshot |

The checker requires the precise fixed base and candidate, verifies that the
desktop patch paths cover every changed candidate file, and preserves patch,
driver, base-source and resulting-source hashes. It rechecks source status and
exported patch hashes after application. Failures retain partial receipts and
require a fresh output directory for retry.

The [current result](../artifacts/runtime-patch-stack/20261013-attempt2/results.json)
and [request](../artifacts/runtime-patch-stack/20261013-attempt2/request.json)
record all seven actual checks/applications. The
[root hash review](../artifacts/runtime-patch-stack/20261013-attempt2/root-review.json)
also confirms only the two optional source files differ and the interpreter
source matches the Android budget symbol/source snapshot. The earlier passing attempt is
preserved; the current checker adds an output-location guard and final optional
source hashes. An initial Python syntax error was corrected before either
application run. No source application was performed by that failed invocation.

Build and execute the reconstructed runtime using its checked-out build
instructions and the [platform acceptance records](coreclr.md). The separate
[upstream defect register](upstream-bugs/README.md) continues to own attribution,
future reporting and official-fix replacement gates. Applying a patch alone
does not pass those gates.

## Minimal terminal-counter candidate - 2026-10-14

The separate direct child
`20405f7ae23e183e038703aa5e356b3310fef427` now has a sixth desktop patch,
[0008-terminal-counter-increment.patch](../eng/runtime-patches/0008-terminal-counter-increment.patch).
It changes only the terminal TryConsume counter increment; the five previous
desktop patches and two optional upstream fixes remain intact. This is a
RuneCLR-specific optimization, not an upstream defect fix.

The [fresh source reconstruction](../artifacts/budget-increment/patch-stack-20261014-attempt2/results.json)
passes six desktop patches, exactly 36 changed files and both separately
applied optional fixes. The original099 candidate still reconstructs with
0003 through0007 in the
[compatibility run](../artifacts/budget-increment/baseline-patch-stack-20261014-attempt1/results.json).
The candidate checker accepts only099 or its exact single-file, single-parent
increment change, with explicit committed identity and tracked-clean source.
Source-only reconstruction remains separate from
[native acceptance](windows-budget-increment-acceptance.md) and
[concurrent/production execution](windows-budget-increment-concurrency.md).

~~~powershell
py -3 -B eng/verify-runtime-patch-stack.py --candidate-commit 20405f7ae23e183e038703aa5e356b3310fef427 --runtime-repo E:/runtime-increment-20261014 --output artifacts/runtime-patch-stack/increment-new
~~~

## Opt-in phase-load child - 2026-10-14

The [isolated acquire-load candidate](windows-phase-load-hotpath.md) a24661d
adds [a separate ninth patch](../eng/runtime-patches/phase-load/0009-terminal-phase-acquire-load.patch)
on top of20405f7. Its subdirectory preserves the original eight-patch
inventory and old candidate checker. The
[dedicated reproduction tool](../eng/verify-phase-load-patch-stack.py) checks
the exact two-file direct child, then reconstructs all36 changed committed
files using seven desktop patches. The two optional upstream defect patches
also apply separately. The
[fresh result](../artifacts/phase-load/patch-stack-20261014-attempt1/results.json)
passes all nine application checks; runtime source remains tracked-clean.
This source check is separate from native build, functional acceptance and timing.

~~~powershell
py -3 -B eng/verify-phase-load-patch-stack.py --runtime-repo E:/runtime-phase-load-20261014 --output artifacts/runtime-patch-stack/phase-load-new
~~~

## Opt-in derived-ledger child - 2026-10-14

The [terminal derived-ledger candidate](windows-derived-ledger-candidate.md)
29ff781 adds [a separate tenth patch](../eng/runtime-patches/derived-ledger/0010-terminal-derived-ledger.patch)
on top ofa24661d. It implements a RuneCLR-specific counter optimization,
preserving diagnostic saturation and per-opcode admission. Its separate
directory preserves all original patch inventories and candidate guards.

The [dedicated source reconstruction](../eng/verify-derived-ledger-patch-stack.py)
accepts only the exact two-file child/tree. The
[fresh result](../artifacts/derived-ledger/patch-stack-20261014-attempt1/results.json)
passes eight desktop patches, exactly36 changed committed files and two
optional upstream defect fixes in a separate snapshot. All ten patch checks
and applications pass; the candidate runtime remains tracked-clean.
This source-only reconstruction does not build or execute the runtime.

~~~powershell
py -3 -B eng/verify-derived-ledger-patch-stack.py --runtime-repo E:/runtime-derived-ledger-20261014 --output artifacts/runtime-patch-stack/derived-ledger-new
~~~
