# Runtime fork targets

RuneCLR does not contain the CoreCLR source. The runtime candidates used by
recorded experiments are branches of
[ReneeGA2020/runtime](https://github.com/ReneeGA2020/runtime), pushed on
2026-10-15. In the local runtime checkout, `origin` stays
`https://github.com/dotnet/runtime` and these branches track `fork`.

The fork's `main` matches upstream `main`. It is not a RuneCLR candidate.
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
