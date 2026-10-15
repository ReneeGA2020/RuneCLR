# Fresh native build of the iOS CID candidate

On 2026-10-12, candidate `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d`
was rebuilt in a new detached runtime worktree, starting with no native objects
or generated headers. This supplies independent build provenance in addition to
the earlier [incremental candidate](ios-r2r-fix-candidate.md). It does not replace
the original baseline, diagnostic, v1 or incremental v2 outputs.

## Source and build

The base remains `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`. Only the
candidate's five-line CID publication guard differs from that base. The worktree
and all native outputs are under
`ios-r2r-clean-debug-20261012/runtime` in the configured Mac experiment root.
The fixed source SDK `11.0.100-rc.1.26420.103` is privately APFS-cloned;
native objects, libraries, generated files and PCH are not cloned.

The documented build entry point is used for `iossimulator.arm64.Debug`,
interpreter enabled and minimum simulator deployment target 15.3.
[`eng/ios-r2r-clean-build.py`](../eng/ios-r2r-clean-build.py) now selects
`clr.runtime+clr.native` so the native installation dependencies are built.

The first invocation selected only `clr.runtime`. CoreCLR compilation and
linking succeeded, but its component install script requested
`libSystem.IO.Compression.Native.a` without building that native-library target;
the attempt failed with `MSB3073` and build exit 1. Those logs and results remain
unchanged. The follow-up `clr.runtime+clr.native` invocation in the same fresh
tree built the missing and remaining native targets, then installed successfully.
Its `native-completion-build.exit` is 0, with MSBuild reporting zero errors.
This is a build that began with an empty native tree and completed in two
recorded stages, not reuse of any baseline native objects.

The final unsigned native library SHA-256 is
`e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8`.
Its product path is
`runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib`.
The fresh worktree remains tracked-clean, the original native baseline hash is
unchanged, and the patch hash matches the incremental v2 candidate.

## Configuration checks

`configuration-verified.json` and the full CMake cache/compile commands establish:

- All 2,604 compile entries use sources/generated files in the new worktree.
- No compile command points into the baseline runtime source/object root.
- `FEATURE_INTERPRETER`, `FEATURE_CACHED_INTERFACE_DISPATCH` and
  `FEATURE_MAP_THUNKS_FROM_IMAGE` are defined for the CID worker.
- `FEATURE_DYNAMIC_CODE_COMPILED` is absent from that worker's definitions.
- CMake source/object directories and the candidate commit identify this build.

These are build checks; execution evidence requires the separate acceptance
run. CoreCLR is rebuilt here. The matching-base trusted framework/CoreLib and
managed fixtures remain the preserved simulator inputs; this is not a rebuild
of the full shipping managed libraries or packs.

## Execution acceptance

The fresh native binary passed an independent repetition of the
[five-group verifier](ios-r2r-fix-validation.md). Original full R2R host/native
still SIGSEGVs; the same full R2R host with fresh candidate native passes 21/21
with twenty CounterMap bytecode dumps. Reduced two- and three-tick sequences
each return from twenty sessions and collect all twenty contexts. Controlled
packages pass 15/15 with successful callback/private/generic interpreter dumps.
All installed bundles remain unchanged and the dedicated simulator shuts down
successfully. `verify-clean-debug.exit=0` and `results.json` reports success.

The verified remote output is
`ios-r2r-fix-verifier-20261012/run-clean-debug`. Local acceptance evidence is
`artifacts/ios-r2r-investigation/20261012-clean-debug-validation/evidence.tar.gz`,
103,557 bytes, SHA-256
`701497c2a7fc26cf226484ccf7e6d28c57adaab3f6dcd6fb5f013884895ef64a`.
The downloaded archive hash, run receipt and simulator shutdown were checked.
Managed/composite full-file identities and wrapper/native Mach-O section
identities are checked just as in the incremental comparison.

## Reproduction and evidence

```sh
python3 eng/ios-r2r-clean-build.py --root ROOT --output NEW_OUTPUT \
  --configuration Debug
```

Each new build requires a new output directory. `--complete-native` supports
one recorded follow-up to a failed clean attempt without overwriting its
request, build log or result. It verifies source/configuration identity and
preserves separate `native-completion-*` receipts. The original and completion
driver snapshots are retained independently.

Downloaded evidence is
`artifacts/ios-r2r-investigation/20261012-clean-debug-build/evidence.tar.gz`,
208,912 bytes, SHA-256
`6ae55f3002beaf8fc7115c6008135f12569f3affb01e90e6bbe3cf594a129b55`.
Its twenty archive members include both build attempts, driver snapshots,
request/result/source/native/configuration identities, CMake cache, complete
compile commands, native link command and patch. The hash-verified local copy
has been extracted; large build outputs remain on the Mac.

Release/Checked configurations, complete managed-pack builds, the official
patched-platform upstream runner, dispatch cost and real iOS hardware remain
separate acceptance work. The incremental binary's
[interface regressions](ios-r2r-patched-regressions.md) and
[dynamic-owner regression](ios-cid-dynamic-repro.md) retain their own native
identities; their results must not be silently attributed to this fresh binary.
