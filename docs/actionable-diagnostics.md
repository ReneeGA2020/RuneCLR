# Actionable diagnostics

Draft of desktop diagnostics already thrown. This does not close #15. It is not an iOS result.

These checks throw InvalidDataException. Callers distinguish them by message prefix, not by exception type.

| Condition | Message prefix |
| --- | --- |
| Restricted UGC capability denial | Capability profile 'managed-il-gameplay-v1': |
| Dependency metadata identity mismatch | Dependency metadata identity mismatch: |
| Unsupported managed-IL shape, such as P/Invoke or a native entry point | The inspector reason itself, without the capability-profile prefix |

A capability denial is not an identity mismatch, and neither prefix means the package ran. Source-location and symbol mappings are not described here. Full .NET and arbitrary NuGet compatibility are not accepted. Physical iOS was not run.

Package InvalidDataException messages still do not include a source file line. GameplayCapabilityPolicy.cs now includes the IL byte offset for an unsupported, unknown, or truncated opcode and for a truncated operand or switch, for example "IL opcode 'calli' is unsupported at IL offset 0." ManagedAssemblyInspector.cs can include the method name, as in "Method '...' uses P/Invoke or InternalCall, unsupported in managed-il-v1.", but not a source line or an IL offset. Symbol mappings remain a #15 gap.

Source compilation is separate. SourceCompiler.ConvertDiagnostic copies Roslyn's diagnostic id, invariant message, severity, and, when the location is in source, the file plus a 1-based line and column into CompilationDiagnostic. It uses GetLineSpan and does not honor an author #line remap. That source path does not add an IL offset to the package inspector exceptions above.