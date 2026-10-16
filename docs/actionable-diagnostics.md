# Actionable diagnostics

Draft of desktop diagnostics already thrown. This does not close #15. It is not an iOS result.

These checks throw InvalidDataException. Callers distinguish them by message prefix, not by exception type.

| Condition | Message prefix |
| --- | --- |
| Restricted UGC capability denial | Capability profile 'managed-il-gameplay-v1': |
| Dependency metadata identity mismatch | Dependency metadata identity mismatch: |
| Unsupported managed-IL shape, such as P/Invoke or a native entry point | The inspector reason itself, without the capability-profile prefix |

A capability denial is not an identity mismatch, and neither prefix means the package ran. Source-location and symbol mappings are not described here. Full .NET and arbitrary NuGet compatibility are not accepted. Physical iOS was not run.

Author-facing InvalidDataException messages do not include a source file line or an IL offset. GameplayCapabilityPolicy.cs reports "IL opcode '...' is unsupported." and "Truncated IL opcode." without the byte offset it used internally. ManagedAssemblyInspector.cs can include the method name, as in "Method '...' uses P/Invoke or InternalCall, unsupported in managed-il-v1.", but not a source line. Source-location diagnostics remain a #15 gap.