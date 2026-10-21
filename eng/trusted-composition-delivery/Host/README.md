# Trusted composition delivery host

Desktop IL host that publishes a signed update with the existing staging helper, restarts it with the existing recovery helper, and executes the signed entry plus its private dependency. This is stock desktop JIT. It is not R2R evidence, not interpreter evidence, and not iOS.

The private key stays in the self-test parent. Child processes receive only the host SPKI file. There is no unsigned last-known-good path.

## CLI

From `eng/trusted-composition-delivery/Host/bin/Release/net11.0/TrustedComposition.DeliveryHost.exe`:

```text
stage-start --releases <root> --final <dir> --document <file> --spki <file> --receipt <file> --file <relative>=<path> [--file <relative>=<path>] [--fail]
recover --releases <root> --spki <file> --receipt <file> [--fail]
--self-test
--integration
```

`stage-start` copies the listed streams into a new final directory and then offers only that final directory. There is no `--offer` switch. A present `--offer`, a missing argument, or a bad `--file` pair prints `ERROR argument` and exits 2 without loading author code.

If publish or signature verification fails, the host calls recovery with no offer. It does not activate the source directory, even when that directory is a valid signed tree inside the releases root. Exit 0 means activated. Exit 1 means not activated. Failures are short codes on the facts lines, not exception objects.

`recover` starts from the host receipt only.

The receipt path must be host state outside the releases root. The host does not write the staging path as last-known-good.

## Output

For stage-start and recover, the last line is `FACTS` plus one JSON object of primitive `DeliveryFacts` fields. It has no author object, exception, or reflection handle. The self-test and integration commands instead print their own check summaries.

When `TRUSTED_COMPOSITION_WITNESS=1` on Windows x64, each witness is one line:

```text
WITNESS {"Label":"...","Pc":"...","Image":"...","AllocationBase":"...","Rva":0,"Executable":true}
```

`Image` is a JSON string, so spaces in a path are not split. The default self-test does not set this variable.

When `RUNECLR_POST_EXECUTION_PRECODE=1` on Windows x64, and the helper assembly was actually loaded by this `Execute`, the host captures `TrustedComposition.IlOnlyHelper.Compute` once through the linked `WindowsEntryObservation.Capture`. `RUNECLR_DELIVERY_EXPECT_HELPER_INTERPRETED` must be `1` or `0`. The line is:

```text
ENTRYOBSERVATION {"AssemblyPath":"...","Entry":{...Capture record...}}
```

The invocation evidence is either the checked helper result from this call or the expected author exception after the helper ran. The host does not call `Compute` again and does not keep the `MethodInfo`. A mismatched precode prints `ENTRYOBSERVATION {"Error":"precode"}` and does not change the activation result. The variable itself is not execution proof. The default self-test leaves it unset.

`DeliveryHostObject.Touch` is `NoInlining` and calls `ExecutionWitness.Capture("host")`. Its symbol is not `TrustedComposition_HostObject__Touch`. This host does not adapt the old native assessor.

## What the self-test runs

`--self-test` builds nothing. Build first, then run the apphost:

```text
dotnet build eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --nologo
eng/trusted-composition-delivery/Host/bin/Release/net11.0/TrustedComposition.DeliveryHost.exe --self-test
```

On this machine that command exited 0 with `SELFTEST PASS`. Stage A returned private 101, helper 310, private version 1.0.0.0, touch 112, interface 20, delegate 20, generic 310, and shared-object identity. An independent stage B returned 202, 613, and private version 2.0.0.0. The next process restored A from the receipt without staging again.

Also covered: a bad signature and a tampered source private restore A before activation; `DestinationExists` against an already published final restores A and does not execute a signed B source that sits inside the releases root; an author exception after the helper keeps the old receipt, reports `None/ProcessSelectionLocked/None/locked` on the same-process second recover, and the next process restores A; an unlisted helper copied into the final directory is not loaded (`helper-not-listed`, one activator call, not an already locked gate); a tampered final private is `ContentMismatch` with no activator call. A signed Private A plus Private B collision returns `duplicate-assembly` with `LOADED_ENTRY` empty, calls 1, and the old receipt unchanged. A signed non-assembly file returns `assembly-identity` the same way. `DeliveryAppDep` is in host deps and TPA, but the unlisted caller does not execute it (`LOADED_DEP False`, `unlisted-assembly`, no receipt).

Host `deps.json` references `TrustedComposition.Contract` and `DeliveryAppDep`, and not Update, Private, or IlOnlyHelper. `DeliveryAppDep` is the TPA application assembly used by the unlisted-call regression.

## Typed session integration

After a Release build, run the same apphost with --integration. The ten checks
use the real signed activator and resolver, then invoke the same module through
the typed logical session. Call 2 advances module/private counts to 2 and
interface/delegate values to 21. Close during call 3 still lets that borrowed
signed call finish with counts 3 and callback values 22. Reentry and later
closed calls do not enter the module.

The generic session owns only its module and borrows each synchronous callback.
The delivery owner keeps its host reference separately and clears it on close
or callback failure. Results contain only completed/value/failure primitives.
The fixed author-failed token means a managed callback exception occurred; it
does not identify its source. Close keeps the process version occupied and
leaves the receipt unchanged. Both normal close and later failure are followed
by successful receipt recovery in a new process. Diagnostic GC after the call
stack returns checks host reference ownership, not assembly unloading.

Local verification and the CI matrix include this command after --self-test.
See the [typed acceptance brief](../../../docs/trusted-embedding-next.md) for
source hashes and platform-specific evidence. This remains an experimental
Host interface outside the public libraries.

## Limits

One process runs one business version. The activator call is the irreversible gate. This host does not unload the context and does not claim that GC collected it.

Loaded entry, private, and helper paths must be the same canonical file as the signed final file. Directory junctions and symlinks, including an ancestor alias, are resolved component by component with a hop limit. Windows comparison is ordinal ignore case. Other systems use ordinal comparison. A sibling prefix is not inside the final directory. Listed manifest paths load only when the assembly full name matches. Assembly simple names use ordinal ignore case, and a duplicate simple name fails with `duplicate-assembly` before the author assembly loads. The process gate stays occupied and the receipt is not replaced. Contract is shared only for the exact host identity. Framework fall-through is limited to TPA files inside the real `System.Private.CoreLib` directory. `DeliveryAppDep`, the host assembly, and `RuneCLR.TrustedUpdate` do not get that fall-through. `helper-not-listed` does not by itself prove the manifest boundary. The self-test also shows `DeliveryAppDep.Marker.Touch` is not called, and a Private A/B simple-name collision does not load Update A or change the receipt.

This host does not claim a sandbox, a race-proof snapshot, network authentication, anti-rollback, or an iOS native gate. `Directory.Move` inside the existing staging helper remains the publish commit. After that commit this host does not delete the final directory.


## Opt-in distinct business versions

This path is experimental stock desktop IL. It is not a public SDK, not native
R2R execution, and not an iOS result. It is not part of eng/verify.ps1 or CI.
Run it only when you pass --distinct-http explicitly.

Build the maintained Host from source, then point the driver at a fresh output
directory outside the source tree:

```
dotnet build eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --nologo
eng/trusted-composition-delivery/Host/bin/Release/net11.0/TrustedComposition.DeliveryHost.exe --distinct-http <fresh-output>
```

Use WITNESS=0 and ReadyToRun=0. The driver copies the already built
OrbitGame.Contracts.dll into the output and records that seal before it writes
or builds the late modules. Module A calls host.Move(3). Module B calls
host.Move(5). They are separate compiles, not a renamed copy of one DLL.

Five processes share one receipt, in order: HTTP offer A (start 0, step 3,
step 6, calls 0/1/2), restore A with the server stopped, a tampered B body
(ContentMismatch, no activation, then the same A sequence and the same
receipt), a new process HTTP offer B (0, 5, 10), and restore B with the server
stopped. After A is active, a second TryStart of the already verified B is
ProcessSelectionLocked. That is process-boundary selection, not a same-process
version switch. The server process is stopped separately from the client exit.
Signing uses an in-memory P-256 key. The run must not leave a private key file.

Process-log limit: the e5 driver writes client started.json after Process.Start.
That file is not an immutable prelaunch command record. A bare suite.exit value
is not a hash-linked launcher record. Count a lane only from its own integer
exit, PID, and raw stdout.

