# Managed method identity for native entry traces

This trusted tool reads PE metadata and IL with `PEReader`. It never loads the
inspected assemblies. The output binds each file SHA256 and module MVID to
method owner, name, token, signature, RVA and original IL hash.

Run with the project's selected private SDK:

```powershell
dotnet build eng/managed-entry-metadata/ManagedEntryMetadata.csproj -c Release
dotnet exec eng/managed-entry-metadata/bin/Release/net11.0/RuneCLR.ManagedEntryMetadata.dll entry.dll private.dll
```

Pair these identities with actual native Module/MethodDesc observations from
the same files. Metadata inspection alone does not prove interpreter execution.
`managedNativeRva=0` identifies absence of an R2R header; it does not establish
which path a loaded method eventually takes.

The 2026-10-13 [budget author inspection](../../artifacts/mobile-session-budget/author-entry-metadata-20261013/verification.json)
checks the two original author DLL hashes, 45 method identities and pure IL
headers. Build completed with zero warnings/errors.
