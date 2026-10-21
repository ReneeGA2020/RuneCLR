# Score game desktop session

This sample is a managed-IL host contract. It is not first-party R2R delivery, not interpreter evidence, not iOS, and not a sandbox.

The game owns `samples/ScoreGame.Contracts`. Its interface is `ScoreGame.IScoreRules`. The host executable does not define it and does not reference `IMapContext` or `SpawnEntity`. The contract assembly does not reference `RuneCLR.Abstractions`. Ordinary gameplay packages without a host interface still require `RuneCLR.Abstractions` and `IMapScript`.

`eng/score-game.ps1` compiles three source directories with `RuneCLR.PackageTool`, validates each `package.json`, then runs `samples/ScoreGame.Host`. Version A adds the tick amount. Version B adds ten times that amount. Each session calls `OnTick` three times with 1, then `Total`. Dispose drops the script reference and unloads the collectible context. A diagnostic GC must show the context collected before the next version opens.

The failing script divides by zero inside `OnTick`. That failure is host-owned text containing `DivideByZeroException`. The score stays 0. The same version A package then runs again.

Expected host lines:

```text
SCORE_A total=3 callback=3 collected=true
SCORE_B total=30 callback=30 collected=true
SCORE_FAIL DivideByZeroException total=0 collected=true
SCORE_RECOVER total=3 callback=3 collected=true
SCORE_DESKTOP managed-il not-interpreter not-ios not-sandbox
```

Allowed calls are only `Add` and `Total` on `ScoreGame.IScoreRules`. A package that names a different contract identity is rejected. `IMapContext` members are unchanged. BCL calls such as `string` or `Exception` construction remain rejected.

Open a score package with HostContractSession. The map sample host and MapPackage reject it before loading when the host interface is not RuneCLR.IMapContext.
