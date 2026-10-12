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

## Next experiment

1. Pin a `dotnet/runtime` commit and build a separate runtime in an isolated
   checkout using upstream instructions. Record its platform/build settings.
2. Run the existing sample and lifecycle tests with that runtime. Establish
   interpreted execution independently from the application logs.
3. Verify interpreted map code in collectible contexts, including private
   dependencies, generics, map-defined exceptions, and repeated unloading.
4. Prove execution of a package compiled after the host was built.
5. On a real iOS device, repeat dynamic loading and multi-session collection,
   accounting for trimming, runtime packaging, missing precompiled methods, and
   the available framework surface. Windows-only tests do not establish this.

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
