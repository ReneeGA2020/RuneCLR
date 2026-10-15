# Fresh Release native CID candidate build

This experiment builds candidate `8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d`
from base `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` for
`iossimulator.arm64.Release`. It is separate from the completed
[fresh Debug build and acceptance](ios-r2r-clean-build.md). The runtime source
and native outputs remain private, and no installed runtime is replaced.

## Build request

On 2026-10-12, the baseline and candidate tracked worktrees were checked clean,
their commits were verified, and no Release output or active Release job was
present. The existing [clean-build driver](../eng/ios-r2r-clean-build.py) was
snapshotted without edits and started with `--configuration Release` in a fresh
output root:

```sh
python3 eng/ios-r2r-clean-build.py --root ROOT \
  --output ROOT/ios-r2r-clean-release-20261012 --configuration Release
```

The configured Mac root is
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr`. The new detached
candidate worktree is `ios-r2r-clean-release-20261012/runtime`. Only the fixed
SDK `11.0.100-rc.1.26420.103` is privately APFS-cloned. Native objects, PCH,
generated headers, framework composites and earlier build outputs are not
copied into the new tree.

The recorded command is the official runtime entry point:

```sh
./build.sh clr.runtime+clr.native -os iossimulator -arch arm64 -cross \
  -c Release -ninja -cmakeargs -DCMAKE_OSX_DEPLOYMENT_TARGET=15.3 /m:1
```

`request.json` records `cleanNativeObjects=true`, source/base, configuration,
SDK, command, baseline native hash and driver SHA-256
`6550a6cc75a6fe85018d1a6495bb8519bcb24a30b5efa5adc537cf6dfc2ea943`.
The single fresh invocation completed with `build.exit=0` on 2026-10-12 at
15:47:00 UTC. MSBuild reports zero warnings and zero errors, elapsed 3m33s.
No completion/retry invocation or baseline native-object reuse was required.

The configured compile database has 2,604 entries, all using source paths in
the fresh worktree, with zero baseline source/object-root references. The CID
worker defines interpreter, cached interface dispatch and Apple mapped thunks;
dynamic native compilation is absent. It has `-O3`, `NDEBUG`, and
`URTBLDENV_FRIENDLY=Retail`, with neither `DEBUG` nor `_DEBUG`. CMake records
`CMAKE_BUILD_TYPE=RELEASE`, iPhone simulator sysroot and minimum deployment
target 15.3. `configuration-verified.json` validates these conditions after the
successful build, checks the exact candidate/patch and final native hashes, and
records `success=true`. The candidate worktree remains tracked-clean, and the
original baseline native hash is unchanged.

The final unsigned native library is
`runtime/artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib`
under the new output root, SHA-256
`8ed0a3cae73584f69f59ab43020b3d6a5ae17be9ce9a0f74b7099cffbbfd1a8e`.
The source/base and source patch match the accepted Debug v2 candidate; native
configuration, code and artifact identity are distinct. `logs/source.json` and
`logs/artifacts.json` expose the candidate/native receipt used by independent
execution verification.

## Managed compatibility and evidence scope

`clr.runtime+clr.native` supplies native runtime components, rather than a
complete managed CoreLib/framework/packs build. Replacing only Debug native
CoreCLR with this Release binary while retaining Debug CoreLib fails during
`AppContext.Setup -> StaticsHelpers.GetGCStaticBase`, before successful
initialization or test callbacks. That mixed build cannot establish Release
acceptance or a regression in the CID candidate.

The source explains an explicit managed/native layout mismatch. In
`src/coreclr/System.Private.CoreLib/src/System/Runtime/CompilerServices/RuntimeHelpers.CoreCLR.cs:896`,
`DebugClassNamePtr` is eight bytes on ARM64 with `DEBUG`, and zero otherwise.
`AuxiliaryDataOffset` at line 911 is `0x20 + DebugClassNamePtr`: Debug CoreLib
therefore reads the MethodTable auxiliary pointer at `MT+0x28`. Release native
`src/coreclr/vm/methodtable.h:3978` omits the `_DEBUG` class-name field, placing
that pointer at `MT+0x20`.
`src/coreclr/System.Private.CoreLib/src/System/Runtime/CompilerServices/StaticsHelpers.cs:64`
reads `mt->AuxiliaryData` directly in `GetGCStaticBase`. These are source-level
ABI facts; exact fault-instruction attribution belongs to the startup debugger
capture.

The upstream guide's recommended Debug runtime with Release libraries refers
to separately configurable ordinary libraries. CoreLib is part of the CLR
configuration and contains layout-sensitive code; that recommendation does
not justify Debug CoreLib with Release native CoreCLR. Matching source,
architecture, runtime features and managed/native layout contracts all matter.

At the pinned source,
`src/coreclr/System.Private.CoreLib/System.Private.CoreLib.csproj:79` distinguishes
Debug/Checked from Release: Debug/Checked add `_LOGGING;DEBUG`, with separate
optimization settings. A complete Release stack therefore needs separately
built Release CoreLib outputs and a trusted R2R composite regenerated against
them. Ordinary framework libraries retain their independently recorded
configuration. This requires new artifact evidence rather than
relabeling the existing Debug evidence. Execution acceptance is maintained
separately from this build receipt.

## Matching Release managed build

On 2026-10-12, a separate
[managed-build driver](../eng/ios-r2r-release-managed-build.py) was started
against the same fresh Release candidate worktree, with no active managed
build and both baseline and candidate tracked-clean. Its output and logs are
in `ROOT/ios-r2r-release-managed-20261012`; it preserves the native-stage
receipts and checks the completed Release library hash before and after:

```sh
./build.sh clr.corelib+clr.tools+clr.crossarchtools \
  -os iossimulator -arch arm64 -cross -c Release -ninja \
  -cmakeargs -DCMAKE_OSX_DEPLOYMENT_TARGET=15.3 /m:1
```

`clr.corelib` builds CoreLib IL with Release definitions; `clr.tools` supplies
the in-build crossgen2, and `clr.crossarchtools` requests the host JIT dependency
for cross compilation. The managed stage has separate request, build log, exit,
artifact hashes and results. It does not rebuild framework composites or run
simulator acceptance. The build completed on 2026-10-12 at 16:03:29 UTC with
`build.exit=0`, zero warnings and zero errors (1m41s). `results.json` records
`success=true`, candidate tracked-clean, the original baseline native unchanged
and the fresh Release native still at SHA-256
`8ed0a3cae73584f69f59ab43020b3d6a5ae17be9ce9a0f74b7099cffbbfd1a8e`.

Under `runtime/artifacts/bin/coreclr/iossimulator.arm64.Release` in the fresh
native stage, the outputs are:

| Artifact | SHA-256 |
| --- | --- |
| `IL/System.Private.CoreLib.dll` | `ded93699ccfef5942e26aec98644a80725497c1021c125389ebf849be442a16d` |
| `arm64/crossgen2/crossgen2` | `ec80c592fe2547536ca4b29b49e9fd5458d0b79c3ee9f2ece3b021a5c4ec41f7` |
| `arm64/crossgen2/libclrjit_universal_arm64_arm64.dylib` | `c6221b5a63e64730f7ac40949c30dfedf73a1498734715b5c1b29d0c47684569` |
| `arm64/crossgen2/libjitinterface_arm64.dylib` | `b5bde4c20427204ba5f3536854de3e9d908c4fc74c0a502bcb9228fafd6af38f` |

An independent MSBuild property evaluation with the recorded target, platform
and Release configuration confirms `TARGET_ARM64`, `FEATURE_INTERPRETER`,
cached interface dispatch and Apple/iOS definitions, with no `DEBUG`. Its
`OutputPath` is the Release `IL` directory. `configuration-verified.json`
records these evaluated properties separately from actual execution evidence;
source receipts preserve the layout-sensitive CoreLib and MethodTable files
and the completed CoreLib file list.

The managed-stage archive is `ios-r2r-release-managed-20261012/evidence.tar.gz`
under the remote root: 81106 bytes, SHA-256
`ad85cb0f3c4ba8ca28a7f503be31660c42860f0432a341a913649d83aca63a9d`.
It is downloaded to
`artifacts/ios-r2r-investigation/20261012-release-managed-build/evidence.tar.gz`
and extracted there. Six binary chunks preserve exact bytes; all sixteen
members pass path/type checks before extraction. Local verification checks the
archive size/hash, build exit, native preservation, driver hash and six source
receipts. These outputs are ready for a newly generated trusted composite;
the earlier mixed Debug-CoreLib startup failure remains preserved.

## Interpreter diagnostics in Release

`src/coreclr/interpreter/interpconfigvalues.h:4` excludes `InterpList` and
`InterpDump` configuration from non-Debug native builds. The method-list print
at `src/coreclr/interpreter/compiler.cpp:2299` is also inside `#ifdef DEBUG`.
The Release build must still have `FEATURE_INTERPRETER`, but the earlier Debug
verifier's positive dump requirement cannot be copied unchanged. Setting
Debug-only environment variables or observing no dump does not prove Release
method execution.

Release acceptance should retain native/source identities, managed success and
collection checks, then separately establish the interpreter path with native
breakpoints/call-stack evidence or another supported method-level diagnostic.
Build definitions alone identify capabilities, not the path actually taken by
any script method. The existing Debug dumps remain evidence for their own
Debug binaries.
The Release native library retains 24 filtered interpreter entry/compiler
symbols in `logs/interpreter-symbols.txt`, suitable for locating interpreter
breakpoints without relying on Debug-only dump settings. Symbol presence alone
does not establish that a particular script invocation reached them.

## Build evidence

Compact evidence is available at
`ios-r2r-clean-release-20261012/evidence.tar.gz` under the experiment root.
Its size is 209047 bytes; SHA-256:
`9bc8f17e3581a64bce18e59fee41a13f3662d420dbec71fed887ec2daeb54d7d`.
The archive is downloaded to
`artifacts/ios-r2r-investigation/20261012-clean-release-build/evidence.tar.gz`
and extracted in that directory. Fourteen 16,000-byte-or-smaller binary chunks
preserve exact bytes; the assembled size and SHA-256 match the remote archive.
All seventeen archive members pass path/type checks before extraction. The
extracted build exit, source/native/configuration receipts and compiler/CMake
file hashes are verified against their recorded identities.
The archive retains the unedited driver snapshot, request/result/build log and
exit, source/native/configuration receipts, full CMake cache and compile
database, CID worker command/object hash, native link command, Mach-O image
metadata, interpreter symbols and candidate patch. Large native objects and
libraries remain in the private worktree.

This build creates no simulator and does not repeat the Debug acceptance suite.
Release-native execution acceptance, its exact managed/composite configuration
and method-level interpreter evidence are separate work. Release CoreLib and
tools are now built; a regenerated composite, execution acceptance, performance
and physical-device acceptance remain outstanding.
