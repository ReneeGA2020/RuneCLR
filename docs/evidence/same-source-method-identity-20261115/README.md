# Same-source method identity: selected observations (2026-11-15)

The [experiment record](../../experiments/same-source-method-identity-20261115.md) explains the
partial result: R2R native-entry observations exist; IL method mode/body is still unproven.

- [summary.json](summary.json): selected image/runtime identities, four-launch ledger, process
  exits, source artifact hashes, observed sites and explicit limitations.
- [native-entry-hits.csv](native-entry-hits.csv): four R2R entry PCs/RVAs and signed delta arguments.

The summary preserves the two failed IL observations, including an unavailable debugger exit
and an absent operator log as null. It does not classify the successful IL process as JIT or
interpreter. Process success and method-mode acceptance are different facts.

| file | SHA256 |
| --- | --- |
| summary.json | 9451346425e62606d7b173a92bf61a4ef5db57da05baa49d1b6ab7d52a8bfb05 |
| native-entry-hits.csv | de558d39c6810f61952af02fc5a7759e100e47b5f75ab48c6c48708f7e0d4c48 |

Orca Worker developer-5 executed the captures; Orca Workers developer-3 and developer-4 performed
separate raw-evidence reviews. Lead generated this allowlisted extract and checked all sixteen
retained input hashes, four ledger entries, native PCs/deltas and bindings to the audit raw hashes.
The extract contains no inherited environment values or absolute runtime/payload paths. The full
local raw streams, operator commands, events and receipts remain under
D:/RuneCLR-artifacts/same-source-method-proof-20261115/runs/ and are not uploaded here.

These are correctness/identity observations, not a benchmark, whole-method coverage, mobile
acceptance, generic-method-mode proof or unload acceptance. Do not treat duplicated exit events
in the original controller log as additional Host processes.
