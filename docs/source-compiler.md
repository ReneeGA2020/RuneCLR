# Controlled source compilation

This document describes the restricted UGC compiler, not the complete C#
compatibility contract for trusted hot updates. The broader
[product direction](product-direction.md) requires separate reporting of source
language version, emitted runtime features, framework availability and policy
restrictions. Modern-language compatibility remains explicit acceptance work.

RuneCLR.Compiler.SourceCompiler is the source-text increment of
[issue #4](https://github.com/ReneeGA2020/RuneCLR/issues/4). It compiles a managed
DLL without running author code. Package construction and IL intake are separate
steps; successful compilation is not package approval or a security guarantee.
`PackageBuilder` additionally applies the [gameplay capability policy](capability-policy.md)
to the emitted entry and every private dependency. C# 12 is the compiler language
version; some valid C# output (for example, async/delegates or reflection) is
outside the initial package profile and receives a capability rejection.

The server calls:

~~~csharp
CompilationResult result = SourceCompiler.Compile(
    assemblyName,
    sourceFiles,
    approvedReferencePaths);
~~~

Authors supply source labels and text. The reference paths are trusted server
configuration, not an author-controlled list. The compiler reads only those
reference files and snapshots their bytes before creating Roslyn metadata
references. It does not discover assemblies from the installed framework,
default load context, working directory or NuGet. The caller must use a private,
stable reference staging directory and record the identities and hashes of the
same bytes in its package provenance.

## Fixed compilation profile

- Regular C# 12.0; newer SDK language defaults do not change the source language.
- Release, deterministic DLL, AnyCPU, nullable enabled, unsafe disabled.
- No PDB output, source-file reads, author MSBuild projects, response files,
  analyzers or source generators. Regular source rejects #r and #load.
- At most 64 source files, 2,000,000 total UTF-16 source characters and 256
  server-supplied references. Source labels are relative forward-slash .cs
  paths, at most 240 characters, without absolute paths, traversal, empty
  segments or duplicates (compared case-insensitively).

Identical inputs, source order, reference bytes and compiler binaries produce
identical DLL bytes. Reproducibility across different SDK compiler versions is
not assumed.

## Results and diagnostics

Failure returns Assembly = null; partial emitted bytes are not returned.
Warnings and errors are limited to 100 diagnostic entries with messages bounded
to 1,024 characters. Source locations use the original supplied label and
one-based line and column, rather than an author's #line remapping. Input and
reference failures return actionable RC1xxx diagnostics; internal stack traces
and server reference paths are not included in those messages.

Compiler provenance records the actual loaded Microsoft.CodeAnalysis.dll and
Microsoft.CodeAnalysis.CSharp.dll names, full assembly identities (including
versions) and SHA-256 hashes. It contains no absolute compiler installation
paths. These are SDK tool identities, distinct from the runtime used to execute
the resulting script.

The executable packaging harness includes compiler cases for a real
multi-source IMapScript, deterministic PE output without a PDB, actual source
positions, unapproved references, unsupported language features, unsafe and
script directives, malformed labels and input limits. Its source fixture also
contains a throwing module initializer: compilation and metadata inspection
succeed without loading or executing the resulting assembly. On 2026-10-12,
all ten compiler cases passed using the private official SDK
11.0.100-rc.1.26425.128; this result is separate from the complete packaging
pipeline's acceptance.

## Current limits

This API does not enforce instruction execution, permissions or CPU/memory
isolation. Disabling unsafe syntax does not remove capabilities exposed by
approved framework or host APIs. The text and diagnostic limits bound request
size, not worst-case Roslyn compilation time or memory. A production intake
service still needs its controlled worker environment and package policy;
device execution and interpreter enforcement remain separate experiments.
