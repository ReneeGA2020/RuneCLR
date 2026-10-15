# Official loader regressions for required collectible interpretation

The [parameterized verifier](../eng/verify-required-upstream.ps1) rebuilds four
unchanged official standalone managed tests in a new output directory and runs
their actual generated Main against a selected private Windows x64 Checked
candidate. This lane uses InterpMode=0 and RuneCLRInterpretCollectible=1:
trusted test callers execute natively while collectible IL must be interpreted.
On 2026-10-13 (UTC+8), all four official generated Main entrypoints actually
pass with the fresh matching Checked candidate. The final receipt records
success=true, complete=true, all four body/native-caller checks true and unchanged
runtime/managed inputs. PowerShell AST checks and independent raw-log/source/hash
verification also pass.

## Source, build and input ownership

The read-only baseline source is
0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de in E:/runtime. The actual older four-test
build receipt is artifacts/cid-upstream-cached-dispatch-20261012/request.json,
with exact standalone DLL/wrapper hashes in results.json. Those receipts prove
the earlier baseline builds; their native mode1 results do not prove the new
required-selection candidate. Old dump filters omit some payload methods, and
the old build does not preserve emitted SimpleRunner.g.cs files.

This new lane therefore performs fresh official-project builds, using the
candidate checkout's private SDK, owned copies of baseline targeting-pack and
live reference-pack inputs, and a new BaseOutputPath/__TestBinDir. It never builds the runtime,
invokes the baseline SDK or writes to the baseline checkout. Every official
source/project file in the four test folders is compared byte-for-byte with the
pinned clean baseline and copied to the evidence directory. Candidate and
baseline must be tracked-clean; source and actual build commands are recorded.

Restore test_dependencies, then build each actual upstream project in Checked
configuration with BuildAsStandalone=true, TargetOS=windows,
TargetArchitecture=x64, RuntimeFlavor=coreclr, CLRTestPriorityToBuild=1,
EmitCompilerGeneratedFiles=true and -t:Rebuild. A unique generated Main must
contain the expected test-body call, retain the GC-stress guards where declared,
and lack a false body guard. The source and generated runner are preserved.
All supplied managed DLLs must lack a managed native header.

## Actual-body acceptance

All project paths are under src/tests/Loader/CollectibleAssemblies.

| Official project | Required evidence beyond exit100 |
| --- | --- |
| GenericVirtualMethod/GenericVirtualMethod.csproj | Native CallGenericVirtualMethodAcrossUnloads plus ten collectible DerivedMachine.Construct bytecode dumps; original expected-exception and unload/cache assertions execute |
| Statics/CollectibleStatics.csproj | Native Program.TestEntryPoint plus bytecode for SetStatic/GetStatic/SetStaticObject/GetStaticObject; original integer/object/static/thread checks execute |
| ResolvedFromDifferentContext/ResolvedFromDifferentContext.csproj | Native Test.TestEntryPoint, two collectible Class.MainTest bytecode dumps and all four scenario markers; original unload and non-collectible-parent failure checks execute |
| ByRefLocals/ByRefLocals.csproj | Native Program.TestEntryPoint, metadata SpanAccessor.GetSpan and emitted GetSpanType.GetSpan bytecode, plus twenty literal loop outputs; original byref-liveness and final collection checks execute |

Measured body counts are ten generic Construct dumps, one each for the four
static methods, two MainTest dumps with all four context scenarios, and one
each metadata/emitted GetSpan dump with twenty loop outputs. Each trusted
entrypoint has positive JIT evidence and no interpreter dump; none of the
designated collectible types reports JIT compilation.

Each process must return managed exit100 without timeout or native/assertion
failure. Its trusted test method must have positive native JIT evidence and no
interpreter dump. The designated collectible types must have no reported native
JIT fallback. Bytecode dumps show successful interpreter compilation; original
assertions and actual value/scenario outputs separately establish functional
execution. No native stub/first-opcode entry samples are collected by this lane.

The launch uses the private layout's dotnet exec with an owned runtimeconfig
selecting exactly Microsoft.NETCore.App 12.0.0, then the unmodified official
test DLL. The original assertions and generated Main are retained. This is a
four-project standalone regression, not the full upstream test suite, Helix,
iOS or a security-sandbox claim.

## Identity and reproduction

RuntimeRepo, RuntimeLayout, BuiltProduct and CandidateCommit identify the actual
candidate. Layout coreclr.dll, clrinterpreter.dll, clrjit.dll and
System.Private.CoreLib.dll must hash-match BuiltProduct; all three native DLL
source stamps must contain CandidateCommit. Candidate must descend from the pinned
baseline. The launcher, hostfxr and hostpolicy are also hashed. Runtime and
managed input hashes are checked again after executing all tests.

~~~powershell
./eng/verify-required-upstream.ps1 -RuntimeRepo E:/runtime-selection-20261013 -RuntimeLayout /path/to/private-layout -BuiltProduct /path/to/Checked-product -CandidateCommit <actual-committed-candidate> -EvidenceDirectory /path/to/new-evidence
~~~

Per-child DOTNET_/COMPlus_ environment settings are cleared before applying
recorded settings, avoiding inherited interpreter modes or refusal switches.
stdout/stderr are separately preserved and hashed, with combined readable logs.
Request, official sources/generated guards, managed hashes, build commands,
per-test body counts and partial/failure receipts remain in the new evidence
directory. Earlier experiments are never overwritten.

## Measured candidate, failures and receipts

Runtime candidate commit:
6bb5f60be8de39b22fb19b95aea03e3252756cb3. Product:
E:/runtime-selection-20261013/artifacts/bin/coreclr/windows.x64.Checked.
Private layout:
E:/RuneCLR/artifacts/execution-selection/runtime-build-20261013/layout.
SDK: 11.0.100-rc.1.26420.103. Five actual commands (dependency restore and four
official project builds) return zero. Generated GenericVirtualMethod and
ResolvedFromDifferentContext Main contain the actual Windows runtime condition
and original GC-stress guard; the other two preserve their original active-issue
conditions. No test source or generator was edited for this lane.

Successful output is
artifacts/execution-selection/upstream-required-20261013-attempt4.
Request timestamp is 2026-10-12T18:25:42Z and completion is
2026-10-12T18:26:01.2426274Z. The original 24 official source/project files match
both candidate and baseline. Separate post-run validation rechecks raw bytecode
counts, native caller evidence, stream/generated/input hashes and runtime
identity without rerunning the tests. Both runtime source trees remain tracked-clean.

Three earlier failed attempts remain unchanged. Attempts1/2 fail during
MSBuild live-artifact resolution because the fresh native-only checkout lacks
the framework ref pack, then the all-library reference pack. The final driver
copies those pinned baseline inputs into owned directories and supplies the
official override properties; it does not disable artifact checks or build
libraries/runtime. Attempt3 builds all four projects and valid generated Main,
then the first Main returns101 with FileNotFoundException for xunit.assert3.2.2
before entering the test body. The final packaging copies matching xunit.* and
Microsoft.DotNet.XUnitExtensions dependencies from the owned targeting pack
to each test directory and records their hashes. These are build/launch
preparation failures, not interpreter compiler refusals. Attempt4 performs fresh
builds and executes all four unchanged entrypoints successfully.

Final results.json SHA-256:
5c19425be6eeb049141fcbd95cfcbc41057fb4d73057af53b87842900cfb0d1e.
Request SHA-256:
ce97f711d5b8cbb3e5ea412236b896ca2a8cc7d86ed3bfd1fd36ae9ff7807ac0.
The append-only receipt-validation.json records the independent checks.

The local archive
artifacts/execution-selection/required-upstream-evidence-20261013.tar.gz
contains all four attempts' driver/receipt/raw streams, source snapshots,
generated Main and original official managed inputs. It is 3,911,717 bytes,
SHA-256 029794170ff5a2c8bb0f3f74849a126bc3a3f752d6f9975a73b6438731dcbff4;
membership and original failure/success receipts were checked after creation.
Large reference/targeting packs remain in their owned directories with complete
hash inventories in request.json. No old baseline or iOS experiment was rerun.
