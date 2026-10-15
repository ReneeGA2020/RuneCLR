# Reports ready for manual upstream filing

Prepared on 2026-10-15. These reports have **not** been submitted to
`dotnet/runtime`. Use each report's first heading as the issue title, and paste
the content starting at `### Description` into the issue body. Each report
follows the upstream bug-report template and can be filed independently.

| Report | Scope | Suggested areas |
| --- | --- | --- |
| [RCLR-UP-001](001-collectible-cid-lifetime.md) | Native CID crash after collectible context retirement, including a dynamic implementation-owner control | CoreCLR VM / interpreter / iOS |
| [RCLR-UP-002](002-apple-simulator-test-generator.md) | Standalone generator skips conditional bodies for simulator TargetOS aliases | CoreCLR test infrastructure / Apple |

Optional local attachment:
`artifacts/upstream-bugs/report-preparation-20261015/RuneCLR-CoreCLR-upstream-repros-20261015.zip`.
It contains the original ordinary/dynamic managed CID sources, selected
machine-readable observations, the existing source-linked generator probe,
both candidate patches and a SHA-256 inventory. It contains no runtime binaries
or complete runtime checkout. The reports also link to public, commit-pinned
source and investigation records.

## Current source and duplicate review

- Execution evidence belongs to official runtime base
  `0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de` and separately identified
  private candidates. No current-main runtime build was performed for reporting.
- The pinned-source generator probe was freshly rebuilt/rerun on Windows on
  2026-10-15: zero warnings/errors and 19/19 expected-baseline checks,
  reproducing the skipped simulator bodies. Original patched/mobile results
  retain their original dates; no mobile runtime experiment was replayed.
- On 2026-10-15, upstream main was inspected at
  `2ef0256337f918788487bde223a7bce2f16dffc1`. Both
  `src/coreclr/vm/virtualcallstub.cpp` and
  `src/tests/Common/XUnitWrapperGenerator/XUnitWrapperGenerator.cs` have the
  same Git blobs as the affected baseline. Changes elsewhere could affect
  behavior; source equality is not a current-main execution result.
- Searches covered the CID resolve-worker name, cached-interface/collectible
  terms, collectible/dispatch/iOS, and generator/simulator terms. No exact
  duplicate was identified in the reviewed results. This is a scoped search,
  not proof that no related issue exists.
- [runtime #134766](https://github.com/dotnet/runtime/issues/134766) concerns
  executable-path arguments filtering all tests in merged Apple runners.
  RCLR-UP-002 instead produces a literal false condition in standalone code
  generation before any Apple launcher is involved.
- [runtime #126199](https://github.com/dotnet/runtime/pull/126199) fixes an
  interpreter/open-virtual-delegate argument shift. RCLR-UP-001 concerns native
  interface cache entries surviving collectible target retirement.

## Not ready to file as a confirmed defect

[RCLR-UP-003](../full-framework-interpreter-assert.md) remains a suspected
Checked full-framework interpreter assertion. Its configuration, original
failure and reduction work are documented there; a framework-only minimal
reproduction and validated root cause are still missing.

After filing, add the actual issue URLs to the
[defect register](../README.md) and individual records. Retain the private
fixes until the relevant official-fix acceptance gates pass.
