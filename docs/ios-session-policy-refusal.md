# iOS Release session-policy refusal and recovery

On 2026-10-13 (local date), a new owned arm64 iOS27 simulator run passed an
actual interpreter compiler refusal followed by 20 normal sessions and context
collections in the same process. The matching Release1724 player was reused
unchanged, with InterpMode=0 and the global collectible diagnostic off. No
runtime/player rebuild or replay of the earlier four acceptance lanes occurred.

## Actual refusal control and inputs

The checked-out candidate is 1724cdec553a7aff7a373a271a4be612651c7625,
tree71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2, on official base
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de. The original
[matching Release build/player](ios-session-policy-acceptance.md) has a
RELEASE_CONFIG_METHODSET for RuneCLRInterpreterRefuseMethods. In eeinterp.cpp,
an explicit method-set plus the exact assembly/type/method identity
SelectionProbe.Refusal / SelectionUGC.Refusal.Entry / Reject prints the refusal
marker and returns real CORJIT_SKIPPED. This is an intentional scoped regression
control, not naturally unsupported IL. It cannot refuse arbitrary production
methods merely by supplying a broad method-set.

The actual signed native image contains that marker and its file-backed Mach-O
sections match the source build. Source native SHA256 is
891cec1e2880ef983110ba4487ed63f8cd2a524c3fad8f1ea7acd7495b509c69.
The trusted SelectionProbe.Host/Contract, SessionBridge and RuneCLR.Runtime
components have actual R2R headers and retain the existing trusted composite.
The original app, its new copied app and its new installed app have identical
recorded bundle hashes.

The new driver installs a byte-identical player copy in a new owned simulator,
then copies three pure-IL fixtures into Documents/refusal-plugin. They are
outside the trusted TPA/composite and are loaded by the required-context factory.
Their actual managed-native RVA/size are0:

| Fixture | SHA256 |
| --- | --- |
| SelectionProbe.Payload.dll | f1d8d94e3357a64c423eac74658338535df2b1c761a5d80cf5de2af7b6332ae9 |
| SelectionProbe.Private.dll | b1b69321166cebdf709aebfdba05c9753fac7ca49e0763717281798967b4246e |
| Refusal/SelectionProbe.Refusal.dll | c254463bb9571902664cd5d0a0f9f445e1a9a57c8b9538fdde879f91dbd8f68e |

These are existing compiled fixture bytes copied into a new independent input
directory after installation. This experiment makes no new-compilation claim.
Installation occurred at 2026-10-12T21:41:19.831097Z and fixture transfer
completed at 21:41:22.333122Z, both 2026-10-13 locally. Original fixture inputs
and the installed fixture hashes remain unchanged.

## Measured run

Remote output is
ROOT/ios-session-policy-refusal-20261013-attempt2, where ROOT is
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr. App PID39762 and
nonce e38b77c51133420d9a26080b67834c64 identify the one actual run.
At the real coreclr_initialize breakpoint, LLDB recorded the installed runtime
path, exact refusal method-set, Documents fixture path and nonce from getenv.
The native wrapper independently reports mode0/global diagnostic0 before
initialization; managed output reports DynamicCodeCompiled=False.

The [original results](../artifacts/ios-session-policy/20261013-refusal-attempt2/extracted/run-refusal/results.json)
pass with:

- Exactly one native RuneCLRInterpreterRefusal CORJIT_SKIPPED marker.
- The required context's actual System.NotSupportedException, followed by its
  confirmed collection; the valid return73 body did not execute.
- 20 normal session values PASS and 20 collected contexts after that refusal,
  including constructor/static/generic/private/delegate/interface body results.
- Policy API version1, default0 and required1; 265 live native policy queries
  all report1, and 21 retired-query guards throw InvalidOperationException.
- Native initialization/execute HRESULT0, managed exit0, LLDB exit0 and normal
  process exit; no assertion/crash, unchanged host bundle and payload.

The actual query phases are 21 before load, 41 before and 41 after explicit
load, 81 resolver-before, 21 before unload, 20 before run, 20 after private
resolution and 20 after run. Unified logging retained 627 events, each verified
against PID39762; parsing actual eventMessage values provides the managed
results. Exit0 alone is not the functional acceptance check.

The [independent assessment](../artifacts/ios-session-policy/20261013-refusal-attempt2/supplemental-extracted/independent-assessment.json)
passes 15 checks: all raw hashes, actual PID-bound messages, exact expected
values in all 20 sessions, actual refusal, byte-identical original/copied/
installed bundles, unchanged fixture inputs and confirmed shutdown. The
[owned simulator cleanup](../artifacts/ios-session-policy/20261013-refusal-attempt2/extracted/cleanup.json)
records shutdown exit0 and actual Shutdown state for
8690A500-26CB-45D9-B770-6C6FF97E85F4 at 2026-10-12T21:42:09.090092Z.

## Preserved failures, driver and archives

The first attempt's generated background launcher had a newline-escaping
SyntaxError before any simulator/device action. Its script, log, state and
failure assessment remain preserved in the supplemental archive. A fresh
attempt2 launcher passed actual Python AST parsing before launch. No app ran
in attempt1, and no app replay was used for the successful result or its
read-only independent assessment.

[ios-session-policy-refusal.py](../eng/ios-session-policy-refusal.py) separates
prepare/install/run/cleanup/archive. It reuses the existing helper readers,
verifies Release retail control/native/R2R/IL identities before installation,
captures actual initialization and refusal evidence, and retains failed runs.
The executed driver SHA256 is
65ec821da37f45381a24d56ac18110994b4c75e0b4f98e6495c7b759253d1c69.
Use a fresh --output with --player pointing to the completed matching player,
--build to its original Release build receipt directory, and --fixtures to the
selection/plugin directory; then run install, run, cleanup and archive on that
new output. Do not overwrite the original player or its old run directories.

| Preserved archive | Bytes / members | SHA256 |
| --- | --- | --- |
| [Original evidence](../artifacts/ios-session-policy/20261013-refusal-attempt2/evidence.tar.gz) | 122768 / 32 | 645e65b4fecbcef27d4361f50aa8af65a2c1ec6fc2cd7348444081839785f536 |
| [Supplemental evidence](../artifacts/ios-session-policy/20261013-refusal-attempt2/supplemental-evidence.tar.gz) | 45511 / 21 | ea7572f7b346b92a7711574ee148d5747b89f61a6e71c01dd6f52c3679a3c898 |

Both archives were downloaded through Cindy SSH and
[locally verified](../artifacts/ios-session-policy/20261013-refusal-attempt2/local-verification.json):
53 members, 51 manifest file hashes, 14 original raw-log hashes and all 627
owned events. The original results SHA256 is
9e36e3b7611fc030ed36353dc3449c45dd9e6c9013ff2be20a7206d7d5172d6a.
The supplemental archive adds launcher/failure records, frozen helper sources
and the independent assessment without modifying the original evidence archive.
App/native binaries remain in the private experiment; their identities are
recorded rather than copied into these small log/provenance archives.

## Scope

This proves scoped compiler refusal, required-context retirement and subsequent
same-process recovery on the matching Release simulator. It does not sample
native entries for the recovery methods or claim complete invocation counts.
The prior [native entry experiment](ios-session-policy-entry.md) is separate
evidence for the installed selection fixtures, not new entry sampling for this
Documents copy. iOS has no dynamic JIT in this build, so an ordinary positive
SKIPPED-to-JIT fallback comparison belongs to the separate
[Android matrix](android-session-policy-validation.md). Physical iOS-device
build/signing/new-IL retirement and broader naturally unsupported-IL recovery
remain unverified. This diagnostic experiment does not establish a hostile-code
security sandbox or runtime-enforced CPU/memory budgets.
