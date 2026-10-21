# Trusted update startup lifetime

One process starts one business version. This note is the current startup
boundary only. It does not add in-process multi-version switching, a new
security sandbox, or an unload API.

## Boundary

Hash, approval, target, missing-file, and content-root checks are plan
checks. They do not load an assembly and do not occupy the process. A plan
rejection can still fall back to the last known good record in that same
start, which is the existing rule.

After a plan succeeds, the process occupies a static gate at the first
irreversible step:

- Built-in selection does this before `AssemblyLoadContext.LoadFromAssemblyPath`.
  The context is not collectible. This host does not unload it.
- Host-loaded selection does this before calling the host activator. Calling
  the activator is the boundary even if the host fails before its own load.
  The selector does not guess whether that callback mapped native code.

If activation fails, or the activator throws, the gate stays occupied. A
thrown activator is reported as `ActivationFailed` and the exception is not
retained. The last known good file is not replaced. The same process does not
fall back or retry, including a callback reentry or a second thread that
arrives while the activator is running. `CompareExchange` is the occupation;
the loser gets `ProcessSelectionLocked` and does not load or call the
activator.

A successful selection also stays for the process lifetime. Recovery from a
failed activation is a later process reading the unchanged last known good
record. No version is selected in the failed process.

## Desktop evidence

Checked on stock desktop JIT. This is not interpreter evidence and not iOS.

Before the gate moved, child processes still using the old order showed:

- A throwing built-in `Activate` returned `ActivationFailed`, then the same
  process selected `good` and loaded it.
- A host activator that returned `ActivationFailed` was followed by a last
  known good start in that process (`LastKnownGood`, two activator calls).
- A thrown activator escaped, and the next host start selected the candidate.
- Reentry from built-in `Activate`, or from the host activator, could
  `TrySelectCandidate` successfully and load the other assembly.
- Two threads overlapped inside the activator and both ran it.

A `NotApproved` plan did not occupy the process: the following approved start
still succeeded. That case still succeeds after the fix.

After the fix, the same child processes reported `ProcessSelectionLocked` for
the second start, one activator call, an unchanged previous record, and
`TrustedUpdate.Good` not loaded. The throwing built-in image stayed loaded,
which is the non-collectible context, not a second version. Focused command:

`dotnet run --project tests/RuneCLR.TrustedUpdate.Tests -c Release`

Result: 272/272 passed, exit 0.

## Residual risk

A failed built-in load can leave its non-collectible context mapped until the
process exits, with no selected version. A host activator can have loaded code
before it fails. Neither case is unloaded here. The gate is in-memory and ends
when the process ends.
