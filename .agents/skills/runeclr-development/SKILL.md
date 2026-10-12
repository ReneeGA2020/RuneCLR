---
name: runeclr-development
description: Develop RuneCLR map lifecycle and restricted execution features, or coordinate its host with a dotnet/runtime CoreCLR interpreter checkout. Use for interpreter integration, unload behavior, execution budgets, and platform feasibility work in this project.
---

# RuneCLR development

Use the project constraints and validation entry points in
[AGENTS.md](../../../AGENTS.md). Read [the handoff](../../../docs/development.md)
to distinguish the existing lifecycle prototype from unverified interpreter
capabilities. If available, [local setup](../../../docs/development.local.md)
identifies this machine's separate runtime checkout.

## Choose the relevant workflow

For map lifecycle or host API changes, read
[architecture](../../../docs/architecture.md), inspect the runtime code and
integration fixtures, and preserve map-reference-free host results. Test cleanup
and completed unloading after both normal execution and managed failures.

For interpreter or execution-limit work, read
[CoreCLR integration](../../../docs/coreclr.md). Inspect the actual checked-out
runtime source and configuration definitions before choosing switches or patch
locations. An installed SDK version or accepted environment variable does not
establish that the interpreter is built, selected, or used for map methods.

For iOS work, separately verify dynamic loading, execution of IL produced after
the host build, and repeated collectible-context retirement on a real device.
Desktop and macOS host tests are useful baselines, not iOS evidence.

## Coordinate host and runtime

Keep host behavior and packaging in RuneCLR and runtime enforcement in the
separate CoreCLR checkout. Use that checkout's own instructions and build tools.
Record its base commit, patch branch/commit, platform, configuration, interpreter
selection, artifact path, and relevant test results when an experiment actually
establishes them. Use private runtime outputs with matching framework libraries.

Advance one observable capability at a time. The next baseline is running the
existing map lifecycle suite through a proven interpreter path before introducing
runtime enforcement. Cooperative budgets can remain useful during prototyping;
identify them accurately.

When adding terminal execution budgets, include a regression where script code
catches the limit exception and tries to continue. Account for constructors,
cleanup, finalizers, and transitions into framework or host code. Keep recovery
compatible with CLR invariants; do not implement termination as an arbitrary
jump that skips runtime unwinding. Scope deeper memory and hostile-code work to
the current milestone rather than expanding every experiment into a full audit.

Update the handoff or milestone evidence when capabilities change. Explain what
was demonstrated and what still requires a different runtime build or device.
