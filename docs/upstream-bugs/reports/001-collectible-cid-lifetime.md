# [CoreCLR][iOS] Cached interface dispatch uses a retired collectible target after ALC unload

### Description

On an unmodified, source-built CoreCLR, a noncollectible ReadyToRun caller can
retain a cached interface-dispatch target belonging to a collectible
`AssemblyLoadContext`. After completed context retirement and address reuse,
the caller dispatches through a retired/reused target and faults with
`SIGSEGV` / PC zero.

The reduced managed fixture has a shared interface, a trusted R2R caller, an IL
plugin and an entrypoint. It has no RuneCLR runtime, packaging, gameplay API or
execution-budget dependencies. Confirmed failing baseline: official runtime
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`, .NET 12, ARM64 iOS simulator.
The simulator host uses a private native wrapper; physical-device and complete
upstream XHarness reproduction remain unverified.

### Reproduction Steps

1. Build matching CoreCLR, CoreLib, framework and crossgen2 inputs from the
   baseline above for `iossimulator/arm64`. Use an R2R host with the CoreCLR
   interpreter for newly loaded IL and dynamic native-code compilation disabled.
   Do not mix Debug CoreLib with Release native code.
2. Build the accompanying ordinary fixture's four source files:
   `ProbeContract.cs`, `ProbeHost.cs`, `ProbeEntry.cs`, `ProbePlugin.cs`.
   Its shared contract is:

   ~~~csharp
   public readonly record struct Tick(int Index, TimeSpan DeltaTime);
   public interface IProbe
   {
       void Start();
       void Tick(Tick tick);
       void Stop();
   }
   ~~~

3. Precompile the trusted caller/contract/entry into R2R. Keep `ProbePlugin.dll`
   as IL outside the composite and TPA list, at `plugin/ProbePlugin.dll` under
   the managed application's base directory. Share `ProbeContract` from the
   default context; cache its Assembly reference before collectible loading.
4. Set `PROBE_MODE=collect`, `PROBE_CYCLES=20`, `PROBE_TICKS=2`. Each
   cycle loads a new collectible plugin and calls `Tick` twice at the same
   no-inline R2R callsite. Request unload, return from the frame holding plugin
   references, then perform diagnostic GC until the context weak reference dies.
   Start the next cycle in the same process.
5. Observe the first `Tick` of cycle 2. Compare `PROBE_TICKS=1`,
   `PROBE_MODE=retain`, and an IL caller.

The fixture's reference ownership follows this shape (the attachment contains
the complete original source, including its logging):

~~~csharp
[MethodImpl(MethodImplOptions.NoInlining)]
private static WeakReference Cycle(int index, int ticks,
    bool unload, List<object> retained)
{
    var context = new Context();
    var assembly = context.LoadFromAssemblyPath(Path.Combine(
        AppContext.BaseDirectory, "plugin", "ProbePlugin.dll"));
    var probe = (IProbe)Activator.CreateInstance(
        assembly.GetType("Plugin", throwOnError: true));
    CallSite(probe, ticks);
    var weak = new WeakReference(context);
    if (unload) context.Unload(); else retained.Add(context);
    return weak;
}

// Only after Cycle has returned:
for (int attempt = 0; attempt < 20 && weak.IsAlive; attempt++)
{
    GC.Collect();
    GC.WaitForPendingFinalizers();
    GC.Collect();
}
~~~

Public source generation and measured reduction:

- [Base managed sources and platform build driver](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/eng/ios-r2r-repro.py).
- [Two-callback reduction, matrix and LLDB capture driver](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/eng/ios-r2r-minimal.py).

Those platform drivers expect our preserved source-build layout, rather than
being standalone SDK publishing commands. The attachment exports the exact
managed inputs for adaptation to upstream test infrastructure.

### Expected behavior

New contexts execute normally, have fresh static state and can be collected.
A longer-lived caller cache must not use a target after its owning loader
allocator has retired.

### Actual behavior

The original native runtime faults at the first Tick of cycle 2 for two- and
three-callback cases after the first context is observed collected. Before the
two-callback fault, markers show three attempted callbacks, two completed
callbacks, one returned cycle, one unload request and one collected context.

| Original runtime, ordinary fixture | Recorded result |
| --- | --- |
| R2R caller, 20 cycles, 1 Tick, collect | Pass; 20 collected contexts |
| R2R caller, 20 cycles, 2 Ticks, collect | Native fault, cycle 2 first Tick |
| R2R caller, 20 cycles, 3 Ticks, retain | Pass |
| R2R caller, 20 cycles, 3 Ticks, collect | Native fault, cycle 2 first Tick |
| IL caller, 20 cycles, 2 or 3 Ticks, collect | Pass; 20 collected contexts per lane |

LLDB separately captured a caller cache whose MethodTable matched a reused
collectible MethodTable address. The cached target was nonzero, but its precode
loaded zero target/MethodDesc data and branched to PC zero:

~~~text
object MethodTable = cached MethodTable = 0x1057910f8
cached target = 0x107f80030
0x107f80030: ldr x10, 0x107f84038
0x107f80034: ldr x12, 0x107f84030
0x107f80038: br  x10
x10 = 0, x12 = 0, pc = 0
~~~

The debugger changes reuse timing. The cycle-2 observation comes from the
separate non-debugger matrix, not the LLDB capture.

A second fixture keeps a **noncollectible** `IDynamicInterfaceCastable`
receiver alive while loading its implementation interface from a collectible
context each cycle. After three calls, the host clears its implementation
`Type` reference before unloading. Both context and Type weak references
must die. Original R2R and a receiver-only collectible guard fault on cycle 2;
the broader private guard and original-runtime IL-caller controls each complete
60 callbacks / 20 collections. Receiver collectibility alone misses this
collectible implementation-owner case.

### Regression?

No introducing commit has been bisected. Source review on 2026-10-15 at
upstream main `2ef0256337f918788487bde223a7bce2f16dffc1` found
`virtualcallstub.cpp` unchanged from the failing baseline (Git blob
`940c3440f455c21ae0576c2d56eaa84beb526b7c`). That newer main has not been
rebuilt/rerun; changes elsewhere could affect behavior.

### Known Workarounds

An IL caller or avoiding completed context retirement changes the outcome in
the measured controls. Retaining contexts is unsuitable as an unloading fix.

Our conservative private candidate suppresses CID cache publication for
collectible or dynamic-interface receivers, while still resolving/invoking the
target:

~~~cpp
if (objectType->Collectible() || objectType->IsIDynamicInterfaceCastable())
    patch = FALSE;
~~~

It passes the measured Debug and matching Release simulator regressions. This
is a diagnostic candidate, not an assertion of the optimal upstream fix.
Caching performance and concurrent publication still require review.

### Configuration

- Failing native baseline: official .NET 12 commit above, Debug.
- Build SDK: the checkout's .NET 11 RC1 SDK.
- Apple Silicon / ARM64 iOS simulator; R2R caller, interpreted IL plugin.
- No RuneCLR runtime or budget patches are required for the original failure.
- Windows controls did not reproduce this failure. Physical iOS is unverified.

### Other information

Please review loader-allocator ownership/invalidation around
`CachedInterfaceDispatchResolveWorker` in
[virtualcallstub.cpp](https://github.com/dotnet/runtime/blob/0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de/src/coreclr/vm/virtualcallstub.cpp)
and `InterfaceDispatch_UpdateDispatchCellCache`.

- [Failure/control matrix and live attribution](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/docs/ios-r2r-minimal.md).
- [Dynamic implementation-owner source and results](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/docs/ios-cid-dynamic-repro.md).
- [Conservative candidate patch](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/eng/runtime-patches/0001-collectible-cid-publication.patch).
- [Matching Release controls](https://github.com/ReneeGA2020/RuneCLR/blob/13d6154860cdf7ea4b6389ae81f778f76d78f969/docs/ios-r2r-release-validation.md).

Related: #111771 introduced CoreCLR cached interface dispatch. #126199 concerns
open-virtual-delegate argument handling rather than post-retirement cache targets.
