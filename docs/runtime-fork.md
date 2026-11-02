# Runtime fork targets

## Published automatic session/reflection-loading candidate (2026-11-02)

The reflection-policy runtime source is published on ReneeGA2020/runtime branch
`runeclr/reflection-policy-20261027` at commit
[`7cbdad39669188c1f49f0a41216829d9a9005591`](https://github.com/ReneeGA2020/runtime/commit/7cbdad39669188c1f49f0a41216829d9a9005591),
with parent `5972a86966e56ae5f468a3e042327f0051e923d5` (the tested
session-policy base). The RuneCLR host still requires private bridge version 4.
The runtime has 22 managed CoreLib/build/linker files (21 tracked modifications
plus the new RuneCLRReflectionPolicy.cs), no native VM delta/rebuild, and the
[automatic MapSession and managed-loading receipt](ugc-session-policy.md).
CoreLib SHA-256 is ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d.
The commit changes no source bytes from the accepted private snapshot; those
22 files are byte-equal to the accepted private source. The
post-commit private Windows replay (123 groups, Runtime 156/156, four targeted
upstream methods, 732 stable pins) pins runtimeCommit/runtimeHead 7cbdad... and
requires a clean worktree with the exact 22-file delta. The
RuneCLR host integration remains an opt-in/private experimental candidate;
default loader/host behavior and README claims are unchanged; the opt-in policy
adapter intentionally recognizes IsSessionCode and author Type construction. HostContract policy closure composes
allowedMethods with the evaluator for admission and reflection, seeds declared
identities, and rejects framework shadows by exact runtime inventory rather than
a System.* name rule. HostContractSession now consumes the same
opt-in options contract in a bounded Windows policy route; its legacy options-free
path is unchanged. Review regressions cover internal delegate
factories, bounded stream admission, resolver-depth event/cross-session loading,
private DynamicMethod MethodInvoker construction/invocation and oversized byte[]
symbol-store caps. Session-owned non-seekable assembly/symbol streams use the
bounded chunked path; stock/non-session LoadFromStream keeps the original
Length/ReadAllBytes behavior. Earlier fixed-runtime history remains: repro-hostcontract-generic-final (121 groups;
CoreLib ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d),
repro-hostcontract-closure-final (115 groups;
CoreLib ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d),
repro-hostcontract-final (107 groups; CoreLib ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d),
repro-adjacent-fixes-final (98 groups; CoreLib ddbf9e33d75e2188278ee8d37a58981ced6ccf90f6ab49b69406b9bc27b2ec5d),
repro-review-fixes-final (95 groups; CoreLib
721b2a13aeccebcf5861579307b792658ce54d20874d3a8feeb0e4ee1ee60dea) and the
pre-fix repro-final3 (86 groups; CoreLib
f3bb7aca7e60da4bdfb2a873b0bfb3adf9a2cbc49b3358aa49d3df0b04909f7c). This is not
global all-load/session, suppressed-flow/unmanaged, mobile or sandbox acceptance. Earlier bridge 1-3
receipts below remain historical and cannot substitute for this matching build.

RuneCLR does not contain the CoreCLR source. The runtime candidates used by
recorded experiments are branches of
[ReneeGA2020/runtime](https://github.com/ReneeGA2020/runtime), pushed on
2026-10-15. In the local runtime checkout, `origin` stays
`https://github.com/dotnet/runtime` and these branches track `fork`.

The fork's `main` is reserved for upstream tracking; neither it nor upstream
`main` is modified by this candidate. Use a named RuneCLR candidate branch.
Every branch below is based on `runeclr/interpreter-baseline` at
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` and does not include later upstream
commits. Check out the named branch. Do not apply files in
[`eng/runtime-patches`](../eng/runtime-patches) onto a newer upstream `main`
and treat the result as that candidate.

The patch files are incremental slices. A later branch already contains the
earlier commits in its stack. Applying only the last slice to the baseline
does not reproduce the branch tip.

## Baseline

| Branch | Commit | What it is |
| --- | --- | --- |
| `runeclr/interpreter-baseline` | `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` | No RuneCLR commits. Use this for work that records the unpatched baseline, including the current product checkout. |

## Desktop stack

Each tip includes the baseline and every branch above it in this table.

| Branch | Tip | Tip commit | Recorded slice, not a substitute for the tip |
| --- | --- | --- | --- |
| `runeclr/execution-selection` | `6bb5f60be8de39b22fb19b95aea03e3252756cb3` | Define the interpreter request constructor after `MethodDesc` is complete | [`0003`](../eng/runtime-patches/0003-collectible-interpreter-selection.patch) is an earlier commit on this branch |
| `runeclr/session-policy` | `5972a86966e56ae5f468a3e042327f0051e923d5` | Root the private CoreLib session-policy bridge during trimming | [`0004`](../eng/runtime-patches/0004-interpreter-required-load-context.patch) |
| `runeclr/session-meter` | `b8e5b0b4b7db30385265f935c00a39a3ba507aea` | Add the diagnostic interpreter instruction meter | [`0005`](../eng/runtime-patches/0005-native-session-instruction-meter.patch) |
| `runeclr/session-terminal` | `7660f3069b3751b648f038bf7f3e9cfc6f96ff09` | Add the session-terminal prototype | [`0006`](../eng/runtime-patches/0006-session-terminal-prototype.patch) |
| `runeclr/session-finalizer` | `099dacd07d8d890822f7422f895337733457ab3c` | Handle terminal finalizer owners at the trusted queue boundary | [`0007`](../eng/runtime-patches/0007-session-terminal-finalizer-boundary.patch) |
| `runeclr/terminal-counter-increment` | `20405f7ae23e183e038703aa5e356b3310fef427` | Use one atomic increment for admitted terminal dispatch counts | [`0008`](../eng/runtime-patches/0008-terminal-counter-increment.patch) is only that tip commit |
| `runeclr/phase-acquire-load` | `a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186` | Cache acquire loads for the terminal meter phase | [`0009`](../eng/runtime-patches/phase-load/0009-terminal-phase-acquire-load.patch) |
| `runeclr/terminal-derived-ledger` | `29ff781e157be82ba5a398a60bb05291e4a865af` | Derive terminal admitted counts from allowances and remaining budget | [`0010`](../eng/runtime-patches/derived-ledger/0010-terminal-derived-ledger.patch) |
| `runeclr/batch-interval` | `d0da7dfafc0c4894ae7aa5332ee171f023a0a88e` | Add opt-in post-admission batch intervals | No separate patch file; this branch is the target |

## Published reflection-policy candidate (2026-11-02)

This branch is based on `runeclr/session-policy`, not on the later
session-meter/terminal/batch stack.

| Branch | Tip | Parent/base | Scope |
| --- | --- | --- | --- |
| `runeclr/reflection-policy-20261027` | [`7cbdad39669188c1f49f0a41216829d9a9005591`](https://github.com/ReneeGA2020/runtime/commit/7cbdad39669188c1f49f0a41216829d9a9005591) | `5972a86966e56ae5f468a3e042327f0051e923d5` | 22 managed CoreLib/build/linker files; no native VM delta |

## Apple branch

This branch is one commit on the baseline. It is not part of the desktop stack.

| Branch | Tip | Recorded slice |
| --- | --- | --- |
| `runeclr/apple-simulator-generator` | `2f3ef1faaf3630f3f57c5402ebd1ab20445b0692` | [`0002`](../eng/runtime-patches/0002-apple-simulator-test-generator.patch) |

## Mobile compositions

These are three separate branches, not one stack. Each adds the same
collectible interface-dispatch guard as
[`0001`](../eng/runtime-patches/0001-collectible-cid-publication.patch) on top
of a different desktop tip. There is no standalone `0001` branch.

| Branch | Tip | Composes |
| --- | --- | --- |
| `runeclr/mobile-session-budget` | `bd9a19c29e2785f6551d47dfb8180da9bf6ef896` | `runeclr/session-finalizer` plus `0001` |
| `runeclr/mobile-derived-ledger` | `2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c` | `runeclr/terminal-derived-ledger` plus `0001` |
| `runeclr/mobile-batch-interval` | `3126bbc9a8851a09ac6435b18a12882bad48f3ee` | `runeclr/batch-interval` plus `0001` |

## Checkout

### Local reflection-policy experiment (2026-10-27)

The historical 2026-10-27 state was version 3, with sixteen managed CoreLib
files on the same base. Beyond the version 2 files listed below, it changes MethodInvoker,
ConstructorInvoker, Activator.RuntimeType, RuntimeType.CoreCLR, Delegate.CoreCLR,
DynamicMethod.CoreCLR, InvokerEmitUtil and RuntimeCustomAttributeData.CoreCLR.
Only managed CoreLib is rebuilt; native binaries remain pinned reused inputs.
The Checked x64 build passes with zero warnings/errors and produces SHA-256
deecf26a610e13a86bf647a64bb93b99b2513d2258e64a3549b9467fd35f8240.
The new layout is E:/RuneCLR-reflection-dispatch-evidence-20261027/layout;
the version 1 and 2 layouts are preserved. See the [version 3 result](ugc-api-policy.md#actual-dispatch-factories-and-attribute-targets-2026-10-27).
Generic Activator's intrinsic is disabled in this experimental CoreLib to
retain target checks in compiled callers; no performance acceptance is claimed.

The following version 2 build/layout receipt is historical. It had eight files.
The first version's four-file description and CoreLib hash below are historical
receipts. Version 2 additionally changes shared RuntimeConstructorInfo.cs,
CoreCLR RuntimeMethodInfo.CoreCLR.cs (the fast property setter), RtFieldInfo.cs
and MdFieldInfo.cs. It still changes only managed CoreLib source.

The same Checked x64 CoreLib command passed with zero warnings/errors and
produced SHA-256
3508143255833afdd99076a6ca6b52c8426cb97a9ccc3bada9b7d844c7472dcb.
The fresh private layout at E:/RuneCLR-reflection-access-evidence-20261027/layout
reuses the prior native product and replaces only managed CoreLib. The previous
layout remains unchanged for the version-mismatch control. Current scope and
receipts are in the [version 2 increment](ugc-api-policy.md#construction-property-and-field-runtime-increment-2026-10-27).

The historical local branch runeclr/reflection-policy-20261027 at
E:/runtime-reflection-20261027 started from the session-policy tip
5972a86966e56ae5f468a3e042327f0051e923d5 and has since been published as
[the commit above](https://github.com/ReneeGA2020/runtime/commit/7cbdad39669188c1f49f0a41216829d9a9005591).
Its first version's source delta was four files:

- Shared RuntimeMethodInfo.cs: CORECLR-only check at Invoke entry.
- CoreCLR RuneCLRReflectionPolicy.cs: opt-in ambient policy scopes.
- CoreCLR System.Private.CoreLib.csproj: include the new source.
- ILLink.Descriptors.Shared.xml: preserve the two private bridge methods.

Build command in that runtime worktree:

~~~powershell
./build.cmd -subset clr.corelib -configuration Checked -arch x64 -ci
~~~

The measured Windows x64 build produced IL/System.Private.CoreLib.dll, SHA-256
df126821eeeb365819d513a7642894c3448041527ce390247e88e1a38ef2f87f,
with zero warnings/errors. There are no native C++ edits or new native build
claims. The private test layout reuses the clean session-policy tree's existing
native binaries from E:/runtime-selection-20261013 (coreclr.dll version records
commit 5972a869...), combined with the newly built managed CoreLib and the
existing net11.0-windows-Release-x64 framework layout. native-layout-inputs.json
records all 20 copied native/product inputs; the maintained experiment driver
pins the entire consumed layout and checks the CoreLib against its build output.
Installed runtimes and both original runtime trees remain unchanged.

See [the reflection experiment](ugc-api-policy.md#ordinary-methodinfoinvoke-runtime-experiment-2026-10-27)
for scope, reproducible commands, actual results and remaining entry points.
That publication is now the branch/commit above. The current source/build
binding uses the published commit plus the CoreLib receipt; the v1/v2/v3
layouts below remain historical and cannot substitute for it.

A new clone can use the fork directly:

```sh
git clone https://github.com/ReneeGA2020/runtime.git
git switch runeclr/interpreter-baseline
```

An existing checkout whose `origin` is `https://github.com/dotnet/runtime`
keeps that remote and adds the fork beside it:

```sh
git remote add fork https://github.com/ReneeGA2020/runtime.git
git fetch fork
git switch --track fork/runeclr/interpreter-baseline
```

Replace the branch name with the row for the experiment being reproduced.
Do not push these branches to `https://github.com/dotnet/runtime`.
