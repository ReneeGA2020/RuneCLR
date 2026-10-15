# Matching session-policy build and acceptance

Measured on 2026-10-13, Windows x64 Checked. A host-selected required context
now interprets its metadata IL definitions with both `InterpMode=0` and
`RuneCLRInterpretCollectible=0`. An ordinary collectible context executing the
same managed bytes remains native. This follows the
[diagnostic selection build](runtime-execution-selection-build.md).

## Source and matching inputs

Official base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, product .NET 12.
Diagnostic parent: `6bb5f60be8de39b22fb19b95aea03e3252756cb3`. Current private
candidate: `5972a86966e56ae5f468a3e042327f0051e923d5`, branch
`runeclr/session-policy` in the separate `E:/runtime-selection-20261013`.
The original official checkout remains untouched.
[Source description](runtime-session-policy-candidate.md) and
[incremental patch](../eng/runtime-patches/0004-interpreter-required-load-context.patch)
record the immutable binder scalar, private factory, acknowledgement and
definition-owner predicate. Patch SHA-256:
`714ba322b3df83ccb3feb5b91043b779e4c75b212ea9d4dbf95db06c0e330657`.

SDK: `11.0.100-rc.1.26420.103`. Build from the runtime worktree:

```powershell
./build.cmd -subset clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib -configuration Checked -arch x64 -clrinterpreter
```

Final build: **0 warnings, 0 errors**. Evidence:
`artifacts/session-policy/runtime-build-20261013`, including source-stamped
native outputs, actual compiled-object hashes/feature flags, fresh CoreLib
crossgen, compiler inputs and the complete layout inventory. The private
layout keeps unchanged same-base Release framework libraries/hosts and
overlays matching Checked runtime, interpreter, JIT, CoreLib and debugger
binaries. It is not a complete shipping pack.

| Consumed file | SHA-256 |
| --- | --- |
| coreclr.dll | `8fe29dda5b339b2153d8825c3364b5b1aed6fb26c95bd27ebbe827fa86895d67` |
| clrinterpreter.dll | `f79dc9fab38e5332e415ba8404d020bb317c9099cb0b4a8ed16323c67fe586a3` |
| clrjit.dll | `3b31161123b94206d90a70af54b5485de6fd9d443db4b20dfd66ac4ba53957e4` |
| System.Private.CoreLib.dll | `de80124a4f1536e6fc565ec9c9007c80f279c78b60ba90dec36b7520e623fc37` |

Failures are retained: an allocation-macro compile error, a successful build
whose library trimming removed the unrooted private bridge, and an idle
MSBuild task-host file lock. Three exact descriptor roots fix the bridge
integration; no whole-ALC preservation or visibility change is used. These
are local issues, not official runtime defects.

`artifacts/session-policy/corelib-metadata-5972-verified` confirms five
bridge/import wrappers, three actual native entries and the nested
constructor/Load/native-load rejection at all five stages. PostTrim matches
product IL; product R2R matches deployed CoreLib. This check alone is not
execution evidence.

## Executed acceptance

The [session matrix](session-interpreter-validation.md) passes before/after
load policy queries, late private loading, ordinary native controls, 26
interpreted body groups across 20 sessions, boxed bridges, actual compiler
refusal and recovery. The native generic caller has 20 ordinary inline
successes versus 20 required inline rejections and bytecode bodies. Unload
is followed by a rejected query and completed weak-reference collection.
Those comparisons use identical managed bytes and diagnostic switch 0.

The production [host option](session-execution-policy.md) is exercised by:

```powershell
$env:PATH = 'E:/RuneCLR/artifacts/toolchains/dotnet-11-rc1;' + $env:PATH
./eng/verify-interpreter.ps1 -RuntimeRepo E:/runtime-selection-20261013 -RuntimeLayout E:/RuneCLR/artifacts/session-policy/runtime-build-20261013/layout -Mode 0 -RequiredCandidateCommit 5972a86966e56ae5f468a3e042327f0051e923d5 -SessionPolicy
```

`artifacts/session-policy/lifecycle-20261013-attempt1` passes **24/24 lifecycle**,
**15/15 player package** tests, the three-context sample, late-built IL and
source/import/source with fresh statics and three collected contexts. Every
entry point requests `--require-interpreter` and reports native version 1
after actual context acknowledgement. Callback/private/generic bytecode
and native trusted MapRunner diagnostics pass. The intentional default-ALC
dependency seed is the single accepted native collision control. Host files
remain unchanged while late IL and packages are produced.

R2R/tiering are enabled, global no-inline is disabled, both selection
switches are 0 and no interpreter method-set is supplied. Native JIT
streams are separate; managed markers can interleave with buffered
interpreter dumps. This is not a complete invocation or native entry trace.

The stock SDK full verifier also passes **24/24**, **84/84 packaging**,
**15/15 player** and three collected sample contexts. Unsupported required
mode rejects before any collectible author assembly loads, including a
missing author path; invalid enum values fail before opening files. The
stock CLI required run fails explicitly without success acknowledgement.
Logs: `artifacts/session-policy-stock-build-20261013.log` and
`artifacts/session-policy-stock-verify-20261013.log`.

Four unchanged [official loader regressions](runtime-session-upstream.md)
pass on this final candidate. They retain ordinary ALCs and diagnostic
switch 1, validating ordinary binding/shared guards rather than the factory.

An independent [raw-evidence assessment](../artifacts/session-policy/root-assessment-20261013.json)
checks method-body counts, actual JIT refusal and recovery, native ownership
controls, policy acknowledgements, collection, metadata and archive identities.
The [archive index](../artifacts/session-policy/root-archives-20261013.json)
records two additional evidence bundles; every archived member was compared
byte-for-byte with its source file. Large runtime binaries are represented by
the complete layout hash inventory rather than copied into these bundles.

| Evidence bundle | Files | SHA-256 |
| --- | --- | --- |
| Build, failed attempts, metadata and patches | 30 | `0de78012211986339a4693249589effdaeb2a0e22db83cca759c8dfa1408dd4f` |
| Production lifecycle/player, stock logs and independent audit | 52 | `e1a37a2c933f41739f88a1cb21ac683cd8963c0e9c148485f1c06526e9161b5e` |

## Remaining scope

Default host selection remains ordinary. Required mode is an explicit
opt-in needing the matching private CoreLib/runtime. Private visibility
does not enforce an author-resistant loader boundary; unmarked ALCs,
dynamic methods and unsupported author routes remain outside this
registered metadata-definition claim. No sandbox or terminal CPU budget
is established.

Windows native entry capture, no-feature candidate execution, concurrent
preparation/multicore controls, additional submitted R2R-body controls and
matching Windows Release execution remains unperformed. The subsequent
[Android Checked prerequisite build](android-session-policy-build.md) and independent
assessment pass; Android framework/APK execution remain pending. Previous CID-only
mobile results do not validate this policy. The subsequent
[matching iOS simulator Release candidate](ios-session-policy-build.md) now
combines the CID fix and compiler interface, with 24/24 current lifecycle,
15/15 packages and twenty collected selection contexts passing under diagnostic
0. A separate native capture covers nine method groups with eleven actual
interpreter-entry samples. Mobile refusal/recovery and physical-device new-IL
loading/repeated retirement remain pending.
