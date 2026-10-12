# CoreCLR interpreter integration

## Why it matters

Desktop JIT runtimes can execute newly downloaded IL. A pure AOT runtime cannot
generally execute arbitrary new IL that has no precompiled native body. An IL
interpreter provides an execution path on platforms that prohibit dynamic native
code generation, including iOS. Dynamic assembly loading and collectible-context
support must also be verified for the selected platform and publishing pipeline.

Upstream references:

- [CoreCLR interpreter tracking issue](https://github.com/dotnet/runtime/issues/112748)
- [CoreCLR on WebAssembly](https://github.com/dotnet/runtime/issues/121511)
- [.NET 11 runtime changes](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-11/runtime)
- [CoreCLR build workflow](https://github.com/dotnet/runtime/blob/main/docs/workflow/building/coreclr/README.md)

## Baseline

The initial prototype targets `net11.0`. It is locally verified using the
installed .NET 11 Preview 6 SDK. CI selects the latest .NET 11 prerelease SDK
available to `setup-dotnet`. No .NET installation is modified, no upstream
runtime binaries are replaced, and no CoreCLR source is vendored in this commit.

Interpreter configuration is runtime-build-dependent. An environment variable
such as `DOTNET_InterpMode` must not be treated as proof that a shipping runtime
supports or selected interpretation: unsupported configuration can be ignored.
Runtime execution traces, interpreter breakpoints, or equivalent diagnostics
must establish which methods execute through the interpreter. The demo therefore
reports its runtime version and makes no interpretation claim.

## Verified desktop baseline and next platform experiment

On 2026-10-12, a pinned unpatched Checked CoreCLR build passed all twelve
lifecycle tests with interpreted maps, including private dependency versions,
generics, failure cleanup and a map compiled after the host. Mode 1 permits
CoreLib JIT; R2R and tiering were disabled, successful interpreter bytecode dumps
were checked, and map JIT compilation was not observed. The build, mode
definitions, launcher and raw evidence references are recorded in
[the desktop experiment](interpreter-experiment.md).

Full-framework mode 3 hits an object-reference assertion in the selected build.
The current `AssemblyDependencyResolver` API is also marked unsupported on iOS.
The next platform experiment must address these limits and verify dynamic
loading and repeated collection on a real iOS device, accounting for trimming,
runtime packaging, missing precompiled methods and framework APIs. Desktop
success does not establish that capability.

## Runtime patch boundary

The first likely patch is per-session execution accounting and a host-requested
stop check in interpreter dispatch / loop-backedge paths. It must cover more
than script-inserted cooperative checkpoints.

Design questions to resolve before calling this a sandbox:

- How is the active session associated with interpreted calls and nested host
  calls without leaking state to another session?
- Can a map catch a quota exception and continue indefinitely? A terminal budget
  violation needs runtime semantics that regain host control safely.
- Which map methods must remain interpreted, and how are JIT/R2R bypasses avoided?
- How are costly framework/native calls restricted, interrupted, or charged?
- How do constructors, exception filters, cleanup blocks, and finalizers behave
  during termination?
- How can allocations be attributed in a shared heap, including framework and
  host allocations on the map's behalf?

Hard termination must preserve runtime invariants; an arbitrary native jump out
of the interpreter is not a safe implementation. Keep proposed patches behind
explicit build/runtime switches, with regression tests and a documented upstream
base commit. Framework allowlists, source checks, and host API design complement
this work but are not substitutes for enforcement.
