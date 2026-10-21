# Trusted-game generic size fixture

Small, dependency-free C# template used to measure how closed generic
instantiations change managed IL and ReadyToRun DLL size. The same
`Cell<T>` / `Ops.Relay<T>` method bodies and the same eight-slot public root
are used in every variant. Only the compile define selects which closed
instantiations the root reaches.

| Variant | Define | Closed instantiations |
| --- | --- | --- |
| `baseline` | `BASELINE` | none; eight non-generic `CellB` blocks |
| `ref1` | `REF1` | `Cell<string>` |
| `ref8` | `REF8` | `string`, `object`, `InvalidOperationException`, `int[]`, `string[]`, `RefA`, `RefB`, `RefC` |
| `val1` | `VAL1` | `Cell<int>` |
| `val8` | `VAL8` | `byte`, `short`, `int`, `long`, `float`, `double`, `Guid`, `Blob` |

Each generic block constructs the cell, calls `Set`, then calls the
`[NoInlining]` `Relay<T>` method, which calls the `[NoInlining]` `Get`
method. The body performs only a field load/store so it is legal for every
`T`; there are no struct-only arithmetic or formatting operations that
would invalidate cross-variant comparison. The root calls the same number of
blocks as its declared instantiations (eight for `ref8`/`val8`, one for
`ref1`/`val1`, eight non-generic blocks for the baseline).

Run the driver from the RuneCLR root:

```powershell
py -3 -B eng/measure-trusted-game-generic-size.py `
  --sdk E:/runtime/.dotnet/dotnet.exe `
  --runtime E:/runtime `
  --crossgen2 E:/runtime/artifacts/bin/coreclr/windows.x64.Checked/crossgen2-published/crossgen2.exe `
  --framework E:/runtime/artifacts/bin/testhost/net11.0-windows-Release-x64/shared/Microsoft.NETCore.App/12.0.0 `
  --output D:/RuneCLR-artifacts/trusted-game-generic-size-<unique>
```

The driver builds five separate artifacts roots, crossgens each IL image once
with identical per-assembly x64 Windows options, and saves IL, R2R, full map
files, raw command logs, PE/R2R header fields, MVIDs, metadata sizes and
deterministic gzip sizes under `results.json`, `results.csv` and `README.md`.

### Offline replay

Replay retained bytes without builds, crossgen, dotnet, a host, author code or
any subprocess:

```powershell
py -3 -B eng/measure-trusted-game-generic-size.py `
  --replay-retained D:/RuneCLR-artifacts/trusted-game-generic-size-<retained> `
  --output D:/RuneCLR-artifacts/trusted-game-generic-size-replay-<unique>
```

Portable offline tests for pin failures, malformed input, output refusal and
the no-subprocess guarantee:

```powershell
py -3 -B eng/trusted-game-generic-size/test-offline-replay.py
```

Replay rejects an existing output or an output inside the retained root before
creating anything. It verifies the retained image, map, log and source-fixture
pins, IL/R2R MVID parity and R2R headers before recomputing sizes. It writes
`input-pins.before.json`, `input-pins.after.json`, `verification.json`, a copy
of the parent report failure, and fresh `results.json`/`results.csv`/`README.md`
in the new output root. It does not claim the current checkout is immutable at
the launch pin; launch and final harness hashes are recorded separately.

Method-node bytes are `.text` code-node lengths (`MethodWithGCInfo`, `Method`
and stubs), and `MethodWithGCInfo` includes its GC/unwind payload. In the
retained measurement, the 258 added exact method-node bytes span six additional
specialized value types (24 method nodes); they are not 43 bytes per individual
method body. `Guid` has no exact body in the retained map; that is map-level
sharing/omission evidence only and does not establish interpreter or fallback
execution.

This fixture measures file composition only. It does not execute the images,
exercise a host, prove interpreter fallback, or establish production size
multipliers. Compression figures describe distribution size; images must be
decompressed before loading.

