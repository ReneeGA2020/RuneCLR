# Trusted game sample

This is a stock-SDK desktop managed/JIT sample of a game-owned interface and a late-built module. It is not R2R, interpreter, iOS, unload or security-sandbox evidence.

## Entry

Run:

    ./eng/trusted-game.ps1

The script builds the host first, then builds the module with BuildProjectReferences=false, checks that the host DLL did not change, computes the module SHA-256, and launches the host with that host-provided value. The sample uses the normal stock-SDK framework selection. For the independent same-source IL/R2R build driver, see [Trusted game IL/R2R builds](trusted-game-builds.md). For signed publication, staging and next-process recovery, see [Trusted game signed release](trusted-game-signed.md). Run eng/trusted-game-signed.ps1 with no args for a fresh artifacts/trusted-game-signed path, or pass a new -OutputRoot. Local mode keeps --module/--sha256/--approval; signed mode adds --stage-signed and --recover-signed, with optional --expected-score-multiplier 1|2 used only for gameplay assertions.

## Projects

- samples/TrustedGame.Contracts: game-owned IGameRules and mutable GameState. It has no RuneCLR.Abstractions or RuneCLR.Runtime reference.
- samples/TrustedGame.Update: one GameRules implementation. Tick adds a non-negative delta to the shared state and returns the new score; a negative delta throws a normal exception before mutation. It has no IMapContext, entity quota or native probe.
- samples/TrustedGame.Host: references Contracts and src/RuneCLR.TrustedUpdate. It does not reference or copy the Update project.

## Typed call

The host loads the exact selected module in a non-collectible AssemblyLoadContext, shares the already loaded Contracts assembly only for its exact full identity, verifies that the entry type implements IGameRules, and then constructs the public session:

    var state = new GameState();
    using var session = new TrustedModuleSession<IGameRules>(rules);
    var result = session.Invoke(rules => rules.Tick(state, 1));

The session owns the module instance. The host owns GameState and passes it through each call. The host uses a scoped local session, not a permanent host field.

The host fixes version game-rules-1 and entry type TrustedGame.Update.GameRules. The build script computes the SHA-256 after the module build and passes it on the host CLI; the host does not read the expected hash from the module. It passes the module path and expected SHA-256 to TrustedUpdateProcess.TryStartHostLoaded for candidate, hash, target, host approval and the process gate. The selector's entry-method field is required to be nonempty, but this host-loaded activator resolves the entry type directly and does not invoke that field.

## Expected sample result

For the two ordinary sessions:

- Normal ticks 1, 2, 3 return 1, 3, 6 and leave the host GameState at Score 6 and Ticks 3.
- Close and Dispose are idempotent. A later call on the closed normal session returns Failure Closed without entering the module.
- A negative delta returns Failure CallbackFailed and closes that session before mutation. The next call returns Failure Closed and leaves Score 0 and Ticks 0.

The host exits nonzero on a failed assertion; it does not print a hard-coded success line.

## Approval and package boundary

The CLI approval value local-trusted-build is a local trusted build-pipeline example. It is NOT a signature and does not mean the host accepts arbitrary downloaded packages. A production path must use the existing signed staging, verification and recovery helpers.

To connect to the existing signed pipeline, use the links below rather than copying their implementation:

- [Signed release signing](trusted-release-signing.md)
- [Signed release staging](trusted-release-staging.md)
- [Signed release recovery](trusted-release-recovery.md)
- [Trusted composition delivery](trusted-composition-delivery.md)

## Scope

This is stock desktop managed/JIT selection only. It does not establish same-source R2R builds, interpreter fallback, iOS or other devices, assembly unload, complete native execution, a security sandbox, or a general download/approval service. Same-source R2R module composition is the next separate increment.

The sample uses the actual public contract in src/RuneCLR.TrustedUpdate/TrustedModuleSession.cs: TrustedModuleSession<TContract> (where TContract : class), TrustedModuleCallResult(TrustedModuleCallFailure Failure, int Value) with Succeeded, and TrustedModuleCallFailure values None/Closed/ReentrantCall/CallbackFailed.
