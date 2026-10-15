# Source-fixed official iOS simulator managed tests

On 2026-10-13 (UTC+8), four unchanged official CoreCLR test projects were
rebuilt and passed on the ARM64 iOS simulator with the direct generator alias
fix. Managed generation, crossgen2 and native execution all use iossimulator;
this run requires no TargetOS=ios managed-generation workaround. The independent
verifier reports success=true with **41/41 checks** in
apps-iossimulator/verified.json.

The managed entrypoints are the actual upstream generated standalone Main,
including their original conditions and assertions. Packaging and launching use
the existing private UIKit/native wrapper. This validates the four standalone
projects; full upstream XHarness/Helix, the complete official suite, tvOS,
Release and physical-device execution remain separate unmeasured scopes. No
full XHarness lane was attempted in this run.

## Executed tests and acceptance

All project paths are under src/tests/Loader/CollectibleAssemblies.

| Official project | Required positive payload evidence | Measured result |
| --- | --- | --- |
| GenericVirtualMethod/GenericVirtualMethod.csproj | Ten .DerivedMachine:Construct[System.__Canon]() dumps, one per load/unload iteration | Main assertion accepted managed exit 100 |
| Statics/CollectibleStatics.csproj | One dump each for SetStatic, GetStatic, SetStaticObject and GetStaticObject | Main assertion accepted managed exit 100 |
| ResolvedFromDifferentContext/ResolvedFromDifferentContext.csproj | Two .TestClass.Class:MainTest() dumps for the positive scenarios | Main assertion accepted managed exit 100 |
| ByRefLocals/ByRefLocals.csproj | One .SpanAccessor:GetSpan() dump, emitted GetSpanType:GetSpan compilation and twenty loop outputs | Main assertion accepted managed exit 100 |

All four launcher exits are zero, CoreCLR execute HRESULT is zero and managed
exit is 100, with no native fault or assertion failure. Broader interpreter
dump counts are 30, 7, 4 and 3; they include constructors/helpers and are not
callback invocation counts. Exit 100 alone is insufficient: the verifier also
requires these specific payload bodies and outputs, valid generated guards,
unchanged official assertions and the input/native identities.

These are interpreter method-dump and functional execution observations;
this experiment did not collect LLDB stub/first-opcode entry samples. Trusted
test callers retain their native symbols and a managed native header, while
collectible payloads remain outside the trusted composite. The private native
runtime is the previously validated matching Debug CID candidate.

All four actual SimpleRunner.g.cs files lack the old false guard. The two
conditional projects, GenericVirtualMethod and ResolvedFromDifferentContext,
contain the existing OperatingSystem.IsIOS condition excluding MacCatalyst,
with the original GC-stress skip condition. The other two entrypoints have no
such conditional platform guard. The preserved generated files and hashes are
in generated/ and generated-guards.json.

## Isolated source and actual project build

Experiment root on the configured Mac:
/Users/editor/RuneCLR-experiments/20261012-iossim-coreclr.
New output: ios-generator-fixed-tests-20261013-attempt3.
The driver ran from 2026-10-12T17:47:02Z through 17:49:30Z.

Native/source baseline is CID v2 commit
8f5815a5a067c3d61e3b2f253a0bf4d9f143c21d. The new detached worktree commit
4ffb6fe2a784aa36a83c9382498f0767edfaec92 adds only the two generator switch-arm
changes from the [direct source fix](apple-generator-regression.md). All four
official test projects, assertions and payload sources are unchanged relative
to the CID baseline. Native candidate and new test worktrees are tracked-clean.

The generator source SHA-256 changes from
8afc40fe5dd4bf05d46575ebe3d4ced92ee1fd005075a3a9ac2612dbffee6277 to
5ff1565c91baa12682ac2cdadcfe8e6fcd085304de0687975e7729ab6d08a008 in this LF
Mac checkout. Native libcoreclr.dylib input SHA-256 remains
e97efd27370d02b6767bbaa1e4cb968f92fa3341d53e345626ff6f8498f572d8.
Signed app native code/data sections match that candidate. Request/state
receipts record SDK, source commits, DLL inputs, signed native hashes and
composite hashes.

SDK 11.0.100-rc.1.26420.103 and matching prior Debug managed artifacts were
APFS-cloned into the new checkout. The installed .NET runtime and old worktrees,
apps and evidence were not modified. Official dotnet.sh restore and external
targeting-pack builds succeed, followed by four actual project builds with
-t:Rebuild. Build logs explicitly show the official XUnitWrapperGenerator
project producing its generator DLL inside the new iossimulator output.

Properties recorded for every command:

~~~text
-p:Configuration=Debug
-p:TargetOS=iossimulator -p:TargetArchitecture=arm64
-p:RuntimeFlavor=coreclr -p:LibrariesConfiguration=Debug
-p:BuildAsStandalone=true -p:CLRTestPriorityToBuild=1
-p:EmitCompilerGeneratedFiles=true -p:BuildTestsOnHelix=false
-p:EnableAggressiveTrimming=false -p:PublishTrimmed=false
~~~

Six build commands complete with exit zero. Private native packaging uses
crossgen2 targetos=iossimulator and clang arm64-apple-ios15.3-simulator. An owned
iPhone 17 / iOS 27.0 simulator executes all four apps and is verified Shutdown
(UUID 95192E1B-A64D-429F-8834-7A7EB69AC69F). The driver PID was 50077 and has
exited.

## Preserved failures and archive

Two preparation attempts failed before any build or app run. The exported
patch used CRLF context lines while the Mac source checkout uses LF; git apply
--check rejected it. The first text transfer also changed its trailing bytes.
The second attempt preserves the byte-exact original export with SHA-256
62a683fff82bf70eedcf838ae2a974e6c33bc0aa917cc6424db45de9c2a89ffe.
The successful attempt preserves that original and records a separate LF apply
copy with SHA-256
caad7cb0a870c43b28f0507adc891720889e4ce9b1a2b02466047099993ec239, matching the
[current LF portable patch](../eng/runtime-patches/0002-apple-simulator-test-generator.patch).
The two failed receipts are preparation/patch-format diagnostics, not runtime
test failures. No app rerun was needed: the first native execution attempt
passed all four tests.

Local archives were downloaded and independently hashed:

| Attempt | Bytes | SHA-256 |
| --- | --- | --- |
| preparation attempt1 | 8,744 | c2cc1802fa08ad81142fd6db894f598c35a6b2daad497ae90586405c84c0ce99 |
| preparation attempt2 | 8,758 | b51f81eb4ecc01c1404d7cc09ba47fdb16245b179bcd995984b274aeec5c39a4 |
| successful attempt3 | 447,268 | f035d56f77d524a53cab93ecdbaad06910831779b6f46afc8ed5a1e89fb30b68 |

Local directory: artifacts/ios-r2r-investigation/20261013-generator-fixed-tests;
each attempt subdirectory contains evidence.tar.gz. Remote archives retain
their original name generator-fixed-official-tests-evidence.tar.gz in each
experiment output. The successful archive includes exact driver snapshots,
source patch/source evidence, command/build receipts, generated Main, original
managed inputs, wrappers, symbols and actual run logs. Local archive checks
also verify all six build statuses, all 41 acceptance checks and each generated
Main/run-log hash. Full large app/SDK/framework clone outputs stay on the Mac.

The [independent driver](../eng/ios-generator-fixed-tests.py) reuses the existing
[managed package/runner/verifier](../eng/ios-r2r-official-managed-runner.py), whose
optional test_commit parameter separates the generator-fixed test source from
the unchanged native CID source. Its default behavior for old experiments is
unchanged. Reproduction requires copies of those two files and the portable
patch in a fresh owned tools directory, then:

~~~text
python3 ios-generator-fixed-tests.py --root /path/to/experiment-root --output /path/to/new-output
~~~

The [earlier workaround evidence](ios-r2r-official-managed-tests.md) remains
unchanged. [RCLR-UP-002](upstream-bugs/apple-simulator-test-generator.md) records
this source-fixed standalone result separately from full official-lane and
future upstream-fix acceptance. No upstream issue or PR was submitted.

