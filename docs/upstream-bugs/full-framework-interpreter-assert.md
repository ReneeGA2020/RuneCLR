# RCLR-UP-003: Full-framework interpreter object-reference assertion

Status on 2026-10-13: suspected upstream issue, not a confirmed attribution;
root cause and reduced repro pending. Not ready for an upstream defect claim.

## Observed result

Unpatched official source 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de,
Windows x64 Checked CoreCLR with matching CoreLib and Release libraries,
InterpMode=3, ReadyToRun=0 and TieredCompilation=0.
The RuneCLR lifecycle harness completes seven cases before a manifest
serialization/reflection path hits Thread::IsObjRefValid(this), inside
OBJECTREF::operator->, with InterpExecMethod and InvokeCalliStub on the native stack.
The process exits with 0xC0000602; there is no successful harness receipt.

The raw retained tests.log is under
artifacts/interpreter/20261012-135731-9dd2d0a864474ff69b350d88b67d53a5.
The assertion text and stack were checked directly when creating this record.
See [the original experiment](../interpreter-experiment.md) for configuration,
source/binary identities and hosting controls.

## Confidence and local disposition

The failure is inside unmodified interpreter code, but that alone does not prove
the host inputs are valid or identify an upstream root cause. There is currently
no reduced framework-only reproduction, allocator/GC-transition diagnosis or
validated corrective patch. Keep this distinct from the confirmed iOS CID issue.

Selective mode 1 remains the verified desktop execution path. Avoid relying on
full-framework mode 3 for the project baseline. Do not disable the assertion or
invent a GC/rooting fix without reproducing and diagnosing the CLR invariants.
This workaround concerns our experimental execution selection, not a resolution
of the mode 3 failure or proof that mode 3 is generally broken.

## Investigation and future report

Reduce the serialization/reflection failure without RuneCLR lifecycle/packaging
dependencies, retaining the original Checked configuration and a mode 1 control.
Check source/artifact matching, isolate the GC/object-reference transition and
run relevant upstream tests before classifying it as a confirmed upstream bug.
A future draft title is: Checked full-framework interpreter assertion during
serialization/reflection. Include only the diagnosis and execution conditions
actually established when filing.

An official fix must pass the reduced case and original mode 3 harness without
disabling assertions, plus the mode 1 baseline and ordinary managed failure
recovery. A nearby interpreter or GC change is not sufficient evidence that
this particular failure has been corrected. Latest upstream fix status is unknown.
