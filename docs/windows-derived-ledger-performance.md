# Windows terminal derived-ledger performance

On 2026-10-14, four new sequential Windows x64 Release measurements compare
the accepted phase-load parent with the terminal derived-ledger child OFF/ON.
ON reduces configured callback time by 8.0859% and 9.6342% relative to the
bracketing parents, and by 12.8930% relative to the child's OFF control. Its
configured/no-config callback ratio is 3.60042x. These are results of one
arithmetic kernel, with per-opcode admission retained and no batching.

## Inputs And Acceptance

Parent: `a24661dd1dccfb4b0c6adfb7b06fd8a7f6df6186`.
Child: `29ff781e157be82ba5a398a60bb05291e4a865af`.
Upstream: `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de`.
Both are private interpreter-enabled Release layouts. The child switch
`DOTNET_RuneCLRDerivedLedger` defaults to 0; each child profile explicitly sets
it to 0/1. All four groups set `DOTNET_RuneCLRPhaseAcquireLoad=1`.

The [candidate acceptance](windows-derived-ledger-candidate.md) passes the
fresh build, all 16 functional commands, the static native-path review and
four actual normal-admission branch witnesses before timing. Cleanup branch
code is statically reviewed; its live branch frequency is not measured.

The [fresh preparation](../artifacts/derived-ledger/windows-benchmark-preparation-20261014-attempt2/preparation.json)
binds 785 inputs and rejects 19 alterations. It requires exact source/build
and original/snapshot inventories, including explicit snapshot-to-original
hash correspondence and live-to-build native binding. Earlier generation
and Windows-separator failures are preserved separately. The accepted parent
uses its unchanged frozen phase-load preparation. Historical timing samples
are not reused.

## Actual Results

Each group runs four paired rounds alternating no-config/high-budget order,
nine measured samples per process and three warmups. All children pin logical
CPU2, mask4. No other owned build, debugger or audit runs during measurement;
audits run after the four groups finish. Idle build-server processes were
observed without CPU-time growth rather than terminating unrelated servers.
This does not provide machine-wide isolation or a frequency governor.

| Group | No-config callback ms | Configured callback ms | No-config session ms | Configured session ms | Callback ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| Parent before | 11.79920 | 45.32410 | 34.37190 | 137.78210 | 3.84129x |
| Child OFF | 11.55805 | 47.82540 | 34.43645 | 142.61705 | 4.13784x |
| Child ON | 11.57065 | 41.65925 | 34.62415 | 125.61765 | 3.60042x |
| Parent after | 11.91325 | 46.10070 | 34.33670 | 139.16455 | 3.86970x |

Values are pooled medians. A callback performs 100000 kernel iterations.
The whole-session scope includes a new context, lifecycle, three ticks and
retirement; collection is checked separately using diagnostic GC. Callback
and session timing scopes must not be substituted for one another.

ON configured session time falls 8.8288%/9.7344% against the parents and
11.9196% against OFF. Parent-after configured callback time rises 1.7134%
relative to parent-before; session time rises 1.0034%. No-config callback
drift is +0.9666%, session drift -0.1024%. The child OFF machine code and
64-byte meter differ from the parent's 48-byte implementation. OFF remains
a useful same-child switch control, not an identical parent binary.

## Raw Verification

The [four-run driver](../artifacts/derived-ledger/performance-bracket-20261014-attempt1/results.json)
completes four measurements, four raw audits and the joined comparison.
The [comparison receipt](../artifacts/derived-ledger/performance-comparison-20261014-attempt1/results.json)
passes 32 distinct process/nonce identities, 416 collected contexts, exactly
24 common source files and 20 identical managed products across all groups.
Four audits reject 54 alterations in total, and the join rejects eight more.

All kernel checksums are `12749776`; high-budget callbacks admit `2600016`
dispatches and three-tick sessions retain the expected `7800101` count.
Author entry records retain interpreted status and StubType6. PID, nonce,
raw streams, exact native products, managed identities and dispatch counts
are checked independently of timing summaries. This is selected entry proof,
not a complete trace of every invoked method.

## Meaning And Next Work

The measured benefit comes from removing the separate terminal executed
increment after each successful remaining debit. Connected normal/cleanup
admitted code has two locked RMWs ON and three OFF with phase-load enabled.
Diagnostic saturation retains the independent counter. Reducing this static
instruction count does not imply a proportional timing improvement.

This is configured-meter incremental cost versus no configured meter on the
same instrumented runtime. It is not total instrumentation overhead versus
stock CLR, a JIT comparison, a confidence interval, mobile performance or a
game-frame result. The earlier phase-load experiment's 4.07x and historical
4.68x are separate runs, not controls for this bracket.

The 100/1000 batching question remains open; this candidate preserves exact
per-opcode admission without reservations or delayed counter flushes. Next
extend representative entity/host-boundary workloads and build matching mobile
products, with physical-device execution validated separately. The switch
remains default-OFF while those capabilities are pending.
