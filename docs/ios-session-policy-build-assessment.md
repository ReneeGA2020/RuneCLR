# Read-only combined iOS build assessment

`eng/ios-session-policy-build-assess.py` checks the combined CID / diagnostic
selection / immutable-session-policy source and matching Release simulator
build. Its pinned source identity is commit
`1724cdec553a7aff7a373a271a4be612651c7625`, tree
`71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2`, based on official
`0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.

Run the assessor on the Mac host after the build completes. Supply the trusted
metadata inspector DLL and its neighboring `.deps.json` / `.runtimeconfig.json`.
These are built from [the PE-reader source](../eng/runtime-metadata-inspector/Program.cs).
The inspector reads metadata bytes without loading the inspected assemblies.
The assessor explicitly selects the build SDK host runtime with `--fx-version`;
it does not execute the candidate CoreLib, player, or simulator.

```sh
python3 ios-session-policy-build-assess.py \
  --build /absolute/ios-session-policy-release-20261013 \
  --metadata-tool /absolute/metadata-inspector/RuneCLR.MetadataInspector.dll \
  --output /absolute/build-assessment-20261013
```

The output directory must be new and outside the runtime worktree. Failures
retain partial receipts and a `results.json` traceback. The assessed source and
critical products are hashed again at the end. The assessor never builds or
modifies them.

The checks bind the 27 changed files to the committed tree and build receipts;
verify seven actual native compile owners and object files; inspect Release
simulator CMake settings, interpreter / R2R / CID definitions and absence of
dynamic native compilation; distinguish the simulator runtime Mach-O platform
from macOS-host compiler tools; and verify statically linked interpreter symbols.

Compiler-interface evidence combines source consumers, native GUID bytes in
CoreCLR and the host JIT, and actual ARM64 instruction bytes in the host
`JitCompileMethod` version comparison. AppleClang optimizes that comparison
into two immediate-register comparisons, so absence of a contiguous GUID literal
in `libjitinterface_arm64.dylib` is expected for this build. The decoder checks
the two GUID halves and the preceding version-query virtual slot.

CoreLib PreTrim, PostTrim and ProductIL stages must all retain the five private
bridge wrappers, three QCall imports, and the nested context constructor / managed
Load / native-load rejection methods. Generated linker descriptors must retain
the three reflection entry points. The compiled managed CORJIT mirror must
contain required-interpreter enum value 33. PostTrim and ProductIL must match.

A successful build assessment establishes source, configuration, trimming and
matching compiler identities. It deliberately records `executionVerified=false`.
Player lifecycle, native policy acknowledgement, fail-closed refusal recovery
and method-level interpreter execution remain separate runtime acceptances.

On 2026-10-13 the full assessor passed against the actual completed Mac build.
Raw receipts are in
`/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr/ios-session-policy-build-assessment-20261013`.
The committed source remained tracked-clean; all 27 source hashes, seven compile
owners, Release simulator / static-interpreter configuration, native GUID checks,
three CoreLib IL metadata stages and the compiled managed bit33 mirror passed.
The assessor hash was
`bada00fed05717d5d8b16e50e73705754bfe8629cd6b5a09fba38ca27c6e4645`.
This was a read-only build assessment, with `executionVerified=false`; player
execution and native method-entry receipts are recorded separately.

Archive the original compile databases and caches rather than just the selected
compile entries copied into assessment JSON. The native database is 14,627,056
bytes and the macOS-host database is 14,957,378 bytes; their caches are 58,766 and
39,132 bytes. The actual generated linker descriptor is 48,588 bytes. The ten
assessment files total 103,696 bytes, and seven top-level build receipts / logs
total 397,163 bytes. Raw PreTrim / PostTrim / ProductIL CoreLib and compiled
managed flag-mirror PEs add 19,971,072 bytes and permit independent trimming
checks later.

`eng/ios-session-policy-archive-manifest.py` prints a read-only archive manifest
with size and hash per file. Use `--format paths` for a tar file list, with the
experiment root as the archive working directory. Its default set includes source
snapshots, original build configuration, build logs and all assessment files;
`--include-pe` additionally includes the four managed evidence files. No archive
or output file is created by the manifest tool.

The original configuration files and four raw PEs are now included in the
completed [session-policy evidence archives](ios-session-policy-build.md#retained-evidence).
The build archive has 59 members; source/configuration/metadata checks can be
reviewed from those raw inputs rather than only the selected assessment JSON.
These archives are separate from the original product and execution receipts.
