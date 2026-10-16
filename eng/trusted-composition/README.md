# Trusted independent-module fixture

This focused fixture uses ordinary collectible AssemblyLoadContext loading and
trusted first-party APIs. It does not use the restricted UGC loader or policy.
Use [the one-command driver](../verify-trusted-composition.py) for builds,
execution evidence and regressions; see the [measured report](../../docs/independent-r2r-composition.md).
The selected runtime disables R2R for collectible modules. Native R2R
composition is therefore a noncollectible control, and the combined native
execution/unloading acceptance remains blocked.

Build `Host/TrustedComposition.Host.csproj` in Release. Its project references
also build updates A/B, their same-named private dependencies (versions 1/2),
the shared contract, and the intentionally IL-only helper. Both update projects
link exactly the same `Business.cs`. Host and updates are separate crossgen2
inputs; no composite image is required.

Stage the host and contract together. Under a separate updates root, put the
three DLLs from each update's `bin/Release/net11.0` in `A/` or `B/`: the update,
`TrustedComposition.Private.dll`, and `TrustedComposition.IlOnlyHelper.dll`.
Do not crossgen the helper. Run:

```powershell
dotnet <host-directory>/TrustedComposition.Host.dll --updates <updates-root>
```

The exit code is nonzero on any failed assertion. One final JSON line reports
the result; `--report <file>` also writes that JSON directly to a file before
printing, keeping it separate from native diagnostic output. The result describes
five sessions: A, B, A, failing A, recovered A. Successful sessions each execute
twice to check private/static state progression as well as fresh-session reset.
Every retired context must collect after its non-inlined execution frame returns.
Forced collections here are diagnostic and are not a game frame policy.

`--noncollectible` runs a separate composition control with noncollectible
contexts. It reports `Collectible=false`, `Collected=false`; it supplies no
unloading acceptance. Each session copies its input DLLs to a distinct physical
directory under `<updates-root>/.sessions/`. This avoids reuse of an R2R image
already owned by another context. Files remain available for evidence review.

`--observe` adds pinned Windows x64 post-invocation entry observations. In the
mixed R2R lane it expects native host/update/private entries and interpreted
helper entries. Add `--expect-interpreted` for IL updates/private dependencies
on a matching interpreter runtime. Add `--jit-control` for a desktop JIT
control (all selected methods native).
Add `--expect-host-interpreted` when explicitly testing a fully interpreted
control with R2R disabled, including the host. Native entry bytes alone do not prove
R2R ownership: the external driver must bind the address to the loaded PE's
R2R RuntimeFunctions ranges. The observer alone supplies no iOS evidence.

Set `TRUSTED_COMPOSITION_WITNESS=1` to collect native stack return PCs while
the selected methods run. The final `Witnesses` array contains only shared
contract records of labels, addresses and mapped-image paths. An external
review must bind those PCs to the exact selected R2R RuntimeFunctions, rather
than treating any frame in the same image as proof for that selected method.
