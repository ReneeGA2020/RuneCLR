# iOS CID candidate acceptance

On 2026-10-12, the private default-behavior candidate described in
[the build record](ios-r2r-fix-candidate.md) passed the five-group Debug ARM64
iOS simulator comparison below. The original all-host-R2R application still
crashes with the original native runtime. Replacing only the native runtime
with the candidate makes the unchanged application pass its lifecycle suite.
The [minimal reproduction](ios-r2r-minimal.md) separately records the stale
cached MethodTable/entrypoint and address-reuse evidence.

## Identity and isolation

- Upstream base: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
- Candidate commit: `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d`, branch
  `runeclr/iossim-cid-collectible-fix-v2`, tracked worktree clean.
- Unsigned candidate `libcoreclr.dylib` SHA-256:
  `475e10c45d81c62d212a631dc6fc61ea6a40dcaf369fa97a3870426b1ec8c438`.
- Native configuration: .NET 12 source, `iossimulator.arm64.Debug`, with the
  matching source-built framework/managed libraries. The candidate uses the
  recorded private incremental build; this was not a clean full rebuild.

The verifier checks the source commit, base, clean tracked state and native
build receipt before creating independently signed application copies. All
managed DLLs and trusted composites retain their original full-file hashes.
Every file-backed Mach-O code/data section in the native wrapper and substituted
CoreCLR is compared across signing. Installed bundles equal the prepared
copies and remain unchanged after execution. This associates the signed
runtime with the verified unsigned candidate without assuming their complete
file hashes survive signing.

The verifier clears inherited `SIMCTL_CHILD_DOTNET_*`, `COMPlus_*` and probe
settings before launching each group. No diagnostic cache flag or tracing is
needed for the candidate behavior. A dedicated iOS 27.0 iPhone 17 simulator was
shut down successfully after all groups. System runtimes, baseline applications
and runtime worktrees remain separate.

## Measured results

| Group | Required and observed outcome | Interpreter/retirement evidence |
| --- | --- | --- |
| Original full R2R host / original native runtime | Native SIGSEGV, no successful managed exit | Negative control still reproduces |
| Same full R2R host / candidate native runtime | 21/21 lifecycle tests, managed exit 0, no native fault/assertion | 20 `CounterMap.OnTick` bytecode dumps |
| Reduced R2R caller / candidate, 20 sessions with two ticks | 40 callback returns, 20 session returns and unload requests | 20 completed context collections |
| Same caller / candidate, 20 sessions with three ticks | 60 callback returns, 20 session returns and unload requests | 20 completed context collections |
| Controlled package player / candidate | 15/15 cases, managed exit 0, no native fault/assertion | Start/tick/stop, private helper and generic bytecode dumps |

Every successful group reports dynamic native compilation disabled and the
pinned .NET 12 source runtime. The controlled-player group records respectively
11, 10, 11, 5 and 5 dumps for `GameScript.OnStart`, `GameScript.OnTick`,
`GameScript.OnStop`, `SharedHelper.Read` and `GenericCounter<T>`. It covers
source/import/source packages, fresh private/generic state, author-failure
cleanup, invalid-package rejection and subsequent recovery.

This acceptance reuses preserved managed/composite fixtures. It is a native
fix comparison; it does not claim a second post-install compilation experiment.
The earlier [unpatched controlled-package acceptance](ios-controlled-packages.md)
established that separate capability.

## Reproduction and evidence

[`eng/ios-r2r-fix-verify.py`](../eng/ios-r2r-fix-verify.py) requires the helper
scripts `verify-ios-packages.py` and `ios-r2r-minimal.py` beside it. Its six
required arguments are `--root`, `--candidate`, `--minimal`, `--controlled`,
`--packages` and `--output`; use `--help` for the entry point. Inputs in this
run are the candidate v2 root, minimal probe root, controlled player `run` and
its `incoming/packages`, under the configured source experiment root.

The output must be new; existing results are never reused as a fresh run.
Actual verified remote output is
`ios-r2r-fix-verifier-20261012/run-retry1` under the experiment root.
`results.json` reports five expected outcomes and `success=true`; the launcher
receipt is `verify-retry1.exit=0`, and `simulator.json` reports shutdown exit 0.
The first output, `run`, is preserved: a parent-directory creation error stopped
that attempt before simulator creation or any managed tests.

Downloaded, hash-verified local evidence:
`artifacts/ios-r2r-investigation/20261012-fix-validation/evidence.tar.gz`,
SHA-256 `1b01dd2b6ba9df16c25b9a5cb01f3a4fb25884a84e57a79800fb83518808593b`.
The 36-member compact archive retains complete console/install/signing/shutdown
logs, source/native/application identities, results, verifier snapshot and patch.
Large applications and native object trees remain on the experiment Mac.

## Remaining acceptance

These results establish a conservative candidate for the reproduced simulator
failure. The subsequent focused
[dynamic-interface regression](ios-cid-dynamic-repro.md) also passes on v2 and
its IL-host control: sixty calls and twenty context/type retirements through
one noncollectible receiver. Original and receiver-only v1 controls both crash
after the first implementation retires, demonstrating why v2 needs the dynamic
receiver guard. The subsequent
[patched interface regressions](ios-r2r-patched-regressions.md) also pass four
twenty-session cases for value arguments/returns, inherited default-interface
implementation, closed generic interfaces and exception recovery, plus two
unchanged upstream source-adapter tests. The source adaptations are not the
official upstream runner. The official patched-platform runner remains a
separate requirement. The [official Windows controls](ios-r2r-upstream-validation.md)
used an unpatched runtime and cannot substitute for that validation.

The subsequent [fresh native Debug build](ios-r2r-clean-build.md) repeats all
five expected outcomes successfully, with its own source/native/application
identities and archives. This supplies independent evidence without baseline
native-object reuse. Complete managed-pack builds, Release/Checked
configurations, performance impact,
concurrent publication and real iOS hardware remain unverified. Keep the passing
Runtime-IL layout available until the candidate meets the appropriate release
gates. This does not change the supported trust model or supply hard execution
budgets.
