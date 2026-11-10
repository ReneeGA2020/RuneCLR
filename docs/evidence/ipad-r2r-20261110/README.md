# iPad device R2R experiment - evidence appendix (2026-11-10)

Scope: minimal, redacted excerpts from one measured physical-device run of the
[iPad device R2R experiment](../../ios-device-r2r-experiment.md). The experiment
installed a developer-signed host once, then built and delivered two independently
compiled R2R update owners and captured the native entry of the owner's
`Business.Execute` for both versions.

Everything in this folder is **derived**. It is not a sealed receipt, not an
original artifact and not a replacement for the retained raw run. The raw run is
kept outside the repository; only the excerpts below are published.

## Contents

| File | What it is |
| --- | --- |
| [summary.json](summary.json) | Machine-readable derived summary of the candidate, install, payload, capture and result facts (schema `runeclr.ipad-r2r-summary.v1`, `kind: derived-summary`). Generated for publication; not a device receipt. |
| [excerpts/console-A.txt](excerpts/console-A.txt) | Selected stdout lines of the A run: native start, path contract, the three R2R callback lines, business output, success marker and exit. |
| [excerpts/console-B.txt](excerpts/console-B.txt) | Same for the B run. |
| [excerpts/pc-stop-A.txt](excerpts/pc-stop-A.txt) | A run LLDB capture: attach/stop, owner module mapping, address lookup, stop PC, register `pc`, executable memory region and backtrace. |
| [excerpts/pc-stop-B.txt](excerpts/pc-stop-B.txt) | Same for the B run. |
| [excerpts/result-A.json](excerpts/result-A.json) | A run result JSON as read back from the app data container. |
| [excerpts/result-B.json](excerpts/result-B.json) | Same for the B run. |

## Provenance and redaction

Each excerpt records the SHA-256 of the retained source file it was taken from and
the SHA-256 of the published excerpt. The two differ whenever text was redacted,
so a published hash never claims to be the original artifact hash.

| Excerpt | Retained source (label) | Source SHA-256 | Published SHA-256 | Redaction |
| --- | --- | --- | --- | --- |
| excerpts/console-A.txt | run-5 `pc-address-capture/console2.log` | `c7d3f09017a5bca1e201344329355ab05a5fd9831cc03da394e11108179e1171` | `bda5a95e2b74ad7ae8806286d862faa13f9b9e01e418687e6feb4ef3d7a7ef21` | container and host paths replaced; the single-line `RUNE_IPAD_RESULT {...}` record removed (duplicated by result-A.json); other lines retained with the whitespace normalization below |
| excerpts/console-B.txt | run-5 `pc-address-capture/consoleB.log` | `795ca56cc87109b322d7676bf563f5d2936a8eaa4d9071b21d6697ef6e114e9b` | `8da3e33beb4e432523f3875b84d8e321538a1f560b72e50f32cbc66ad30d7d30` | same |
| excerpts/pc-stop-A.txt | run-5 `pc-address-capture/pc-driver.out` | `66b8a8132b9770046a8bd8b29d5e1dea8f0bf51ae20315fc3a08e868a193db0f` | `74121a0b96bae83ba2583ba664c9879407e079bcd5c588e4b6629965f96bc23d` | container and host paths replaced; full image list (about 849 entries) truncated to the host and owner modules; the remaining captured text retained with the whitespace normalization below |
| excerpts/pc-stop-B.txt | run-5 `pc-address-capture/pc-driver-B.out` | `cb702542e04985c73b8bbff2d9613378a744e2341df936fa9db76ab001562b20` | `749f42840ea3cb1ffd733494265baa8f37b64fa8fa06de22dc3472565fdbe13f` | same |
| excerpts/result-A.json | run-5 device result for A | `cf3a8ff0a3f6a781134f612976759e60b40669d414aaaf1e761e5b277db86e08` | `e17db24887a7126dfa16ad6e70f2aeec2e3025ef6da7673cee1dedd24a4f38ce` | the embedded `logExcerpt` directory path replaced; every other field unchanged |
| excerpts/result-B.json | run-5 device result for B | `3e4c561334cfd3410960466446175c5b75ff0df4b9f981b2d07b09128bdec33f` | `ca475bf8e3ab5b7dd9e660d1bcce5d9c3d1ff37574ab74a785c41c4c55fb35f0` | same |

Published text uses LF line endings, and excerpt lines have trailing horizontal whitespace removed. The source hashes above still identify the untouched retained files; the published hashes identify these normalized, redacted excerpts.

Placeholders used consistently across every file here:

| Placeholder | Replaces |
| --- | --- |
| `<app-data-container>` | the app data container directory (per-install UUID path) |
| `<app-bundle>` | the installed application bundle directory (per-install UUID path) |
| `<host-workdir>` | the local build/evidence working directory on the host machine |

The device UDID, CoreDevice identifier, team identifier, signing certificate and
signing profile are **not** published; they were removed rather than replaced.

## What is deliberately not published

- The full LLDB image list (about 849 system modules) and unrelated system paths.
- Raw device logs outside the two runs above, and the earlier failed debugger
  attempts from the same session (those are historical, not evidence).
- The unsigned build tree, signing keys, provisioning profile, and the retained
  run directory itself. The raw run stays where it was produced.
- Any second-run or baseline-console material; see the note on process IDs in the
  [experiment report](../../ios-device-r2r-experiment.md).

## How to read a capture excerpt

`pc-stop-*.txt` starts with the attach and the stop at `dyld` start, then shows
the owner image being mapped, the address lookup, the actual stop and the
backtrace. The trustworthy fields are the load base, the module file offset,
the stop PC, the register `pc`, the executable region that contains it and the
frame names. A callback line alone, a module base alone or an injected breakpoint
address alone is not a PC witness.

## Limits

These excerpts support one bounded claim: on this run the downloaded,
independently built R2R owners executed the owner method natively at an observed
PC, and both runs completed with the expected managed result and process exit.
They do not support interpreter-mode proof for the IL helper, whole-method native
compilation, distribution, unload, same-process switching, performance, sandbox
or security claims. See the experiment report for the full scope statement.
