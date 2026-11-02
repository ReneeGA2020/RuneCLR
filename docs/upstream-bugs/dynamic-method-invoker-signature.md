# RCLR-UP-004: Dynamic MethodInvoker reads an uninitialized signature handle

Recorded 2026-10-27. Pre-existing CoreLib defect observed on the pinned private
Windows x64 Checked layout; no upstream issue has been filed. The implicated
logic is present at the upstream base 0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de
and the session-policy tip 5972a86966e56ae5f468a3e042327f0051e923d5. A fresh
unmodified-upstream binary build has not been run for this finding.

## Reproduction and cause

Create a DynamicMethod, emit a constant return, and call MethodInvoker.Create
before invoking the method or creating a delegate:

```csharp
var method = new DynamicMethod("Unfinalized", typeof(int), Type.EmptyTypes);
var il = method.GetILGenerator();
il.Emit(OpCodes.Ldc_I4, 23);
il.Emit(OpCodes.Ret);
var invoker = MethodInvoker.Create(method);
Console.WriteLine(invoker.Invoke(null));
```

The preserved version 2 private layout, outside any reflection-policy scope,
exits -2146232797 at the assertion `_methodHandle != null` in DynamicMethod's
Signature getter, reached through MethodInvoker's constructor. MethodInvoker
constructs its signature before GetMethodDescriptor has initialized that handle.
The version 2 patch did not modify MethodInvoker or DynamicMethod. This is
separate from a policy rejection and from RuneCLR's interpreter execution proof.

## Local disposition

The current uncommitted CoreLib candidate calls GetMethodDescriptor before
constructing a DynamicMethod-backed MethodInvoker. The same reduced process
then exits 0 and returns 23, with Checked assertions retained. A policy scope
still explicitly refuses dynamic invoker creation and cached dynamic execution;
the fix enables the ordinary trusted-host control rather than granting UGC
dynamic-code permission.

Archival/local evidence is under
E:/RuneCLR-reflection-dispatch-evidence-20261027/dynamic-invoker-probe:
Probe.csproj, Program.cs, build.log, v2-result.log and v3-result.log. The first
full replay's assertion is preserved separately in repro-r7/private.stderr.log.
These are local evidence identifiers, not GitHub download links.

## Official-fix acceptance

Before filing, run the reduced process on a clean source-matched upstream
Checked build and check current upstream source/issues for a duplicate or fix.
Do not retarget RuneCLR's patch stack while doing that investigation. Adoption
of an official fix requires the reduced case, ordinary dynamic invocation,
the scoped refusal controls, and the reflection/lifecycle regression gates
without the overlapping local initialization change. Latest upstream fix
status is unknown. See the [defect register](README.md).
