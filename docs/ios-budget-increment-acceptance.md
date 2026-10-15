# iOS simulator acceptance of the minimal counter increment

The exact counter candidate passes a fresh Release application run on
2026-10-14: **15 budget scenarios and 73 collectible-context collections**
in one process. Physical iOS execution remains separate.

## New application and unchanged author inputs

The [matching core build](mobile-budget-increment-builds.md) uses commit
`112e97408de1ae1c2a6cbd2967dcd250cd2d491c`, tree
`91673a7980bda79006259e525741fecb04324444`. The new
[acceptance driver](../eng/ios-budget-increment-accept.py) binds the live
37 changed source files, three candidate products, original six trusted/author
DLLs, and all 180 original framework IL inputs before building. Three actual
negative controls reject changed proof/receipt bytes and the old runtime tree.

The old signed application supplies only the bundle template. A new executable
bridge is compiled; the current compiler regenerates the 186-input composite
from the original framework IL, new CoreLib, four trusted DLLs and bridge.
The wrapper is relinked and the application freshly signed. Both original
author DLLs remain absent until after the new application is installed.
Original source, inputs and old application are checked again after the build.

Remote root is `/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr`.
New application output is `ios-budget-increment-acceptance-20261014-attempt1`;
its independent normal run is the sibling with suffix `-functional`.
Owned simulator is `98017E27-E6AB-4C00-928F-4D7D4DEFF4D5`.

## Actual normal run

PID `27973`, nonce `05fa545c32694a79b2df063e4593fcd1`, completes all
15 scenarios and 73 collections with InterpMode0, collectible diagnostic0
and ReadyToRun1, without a debugger. Native initialization/execution and
managed completion exits are zero; the owned simulator shutdown exits zero.
The frozen functional observer reads the actual installed bundle and author
files before launch and after completion. All files match.

The [strict audit](../artifacts/mobile-budget-increment/ios-functional-receipts-20261014-attempt1/audit/results.json)
checks every business row, scenario/child nonce, resource release, terminal
catch/filter suppression, bounded cleanup and recovery. It reports
`mobileVerified=true`, with all 15 corruption controls rejected.
Normal execution consumes 96 measured opcodes; finite cleanup consumes 38.
Execution exhaustion remains 8192, and infinite cleanup exhausts its 4096
reserve. These architecture-specific counts are observed, not assumed.

The [downloaded receipt archive](../artifacts/mobile-budget-increment/ios-functional-receipts-20261014-attempt1/receipts.zip)
has 80 members and 197527 bytes. SHA256 is
`64f8be16e2a87bf7a0aa42bc6be63be158a11c96bfe76390a8cb186a94314f3a`.
Local extraction independently validates its SHA, size and all 79 indexed
member hashes. Large application/composite binaries remain on the Mac; their
identities are retained in the bundle and compilation receipts.

## Method-entry boundary

Functional success is not method-entry proof. A separate new debugger lane
passes against this candidate. Offline matching native/DWARF
inspection locates child dispatch at source line3751 and file PC0x2dd7b8.
The new native image loads its first opcode into w25 rather than the old
image's w26; the x24 opcode pointer and x19+0x88 context spill remain present.
The independently named [entry driver](../eng/ios-budget-increment-entry.py)
and [assessor](../eng/ios-budget-increment-entry-assess.py) retain the original
drivers and bind this observed instruction difference.

PID `28227`, nonce `a13e075823114c249b09a80335c791d8`, captures 147 valid
samples across all nine requested method groups, with zero capture errors.
Constructor, lifecycle, finite-cleanup, private-helper and nested-delegate
entries bind the actual loaded Module MVID, MethodTable/MethodDesc ownership,
independent author PE hashes/tokens and bytecode header/first opcode.
The same debugger launch completes 15 scenarios and 73 context collections.
LLDB, application and owned simulator shutdown exits are zero.

The [raw-sample assessment](../artifacts/mobile-budget-increment/ios-entry-20261014-attempt1/assessment.json)
reparses original LLDB samples and pFrame DWARF, binds the matching Release
core receipt, and rejects four token/PC/MVID/bytecode corruption controls.
It reports `nativeEntryProof=true` for this sampled scope. The
[entry archive](../artifacts/mobile-budget-increment/ios-entry-20261014-attempt1/evidence.zip)
has 50 members, 105696 bytes and SHA256
`00894e35492ca1b8f2d6dad25b94120def0ca8728244fbf1f33e3f799e01a246`;
downloaded zip size/SHA and all 49 indexed member hashes pass.

This lane does not accept physical devices, complete invocation coverage,
finalizer/concurrent termination, blocking native work or hostile-code
isolation. The existing [device readiness](ios-device-readiness.md) and
[budget trust model](host-instruction-budget.md) still apply.
