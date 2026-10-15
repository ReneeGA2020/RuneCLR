# Managed IL intake profile

The structural inspector introduced by `managed-il-v1` supports controlled packaging work in
[#4](https://github.com/ReneeGA2020/RuneCLR/issues/4). Authors supply source or
IL; the operator/server builds the runnable package.
[ManagedAssemblyInspector](../src/RuneCLR.Packages/ManagedAssemblyInspector.cs)
reads submitted PE images and ECMA-335 metadata without loading their assemblies
or executing constructors, initializers, callbacks or author build projects.
New versioned packages use `managed-il-gameplay-v1`, combining these structural
checks with [the static gameplay API policy](capability-policy.md). The structural
inspector itself remains independently usable by the trusted operator tooling.

This is structural input validation. It does **not** verify complete IL
instruction, type, stack, token, control-flow or exception semantics, and it
does not establish a hostile-code sandbox. Passing intake does not enforce
interpretation or hard execution/memory limits. Execution selection remains a
separate [CoreCLR integration concern](coreclr.md).

## Assembly checks

`Inspect(ReadOnlyMemory<byte>)` and `Inspect(string)` return the assembly's full
identity, simple name, and full AssemblyRef identities. Neutral culture and
unsigned `PublicKeyToken=null` are explicit; signed public-key blobs are hashed
to their identity token. Computing an identity is not verifying a strong-name
signature or approving its publisher. The builder separately checks references
against its fixed trusted framework/contract inventory and explicit private
dependency identities.

The initial inspector checks:

- Nonempty input no larger than 32 MiB; complete PE headers and raw section
  bounds; managed metadata describing an assembly rather than a module.
- CLR `ILOnly`; absence of native entry points, managed native/R2R headers and
  native code-manager, vtable-fixup or export-jump directories.
- Managed metadata/resources/strong-name-directory RVA and size bounds.
- Type/member names and basic field/method signature headers, method generic
  counts where present, parameter-row bounds, and method body header/RVA bounds.
- No P/Invoke, InternalCall, native/non-IL, unmanaged or forward implementations.
  Runtime-implemented methods, including custom delegate declarations, are not
  supported by this initial profile. Abstract methods can omit their bodies.
- Nonempty IL bodies, local-signature headers and exception-region byte ranges
  within their method bodies. This does not check whether region boundaries
  coincide with valid instructions or prove that the method can execute.
- Portable assembly simple basenames of 1–128 characters. Path separators,
  control characters, reserved filename punctuation, `.`/`..`, trailing dot or
  space, and Windows device basenames are rejected before the builder uses
  these names for reference/private DLL paths. Unicode names are otherwise
  allowed.

Malformed or unsupported images produce `InvalidDataException` with a reason.
Path opening/access/read failures retain normal I/O exceptions. Trusted host
and framework references use their own operator-selected metadata inventory;
the author's no-native-implementation profile is not applied to CoreLib or
trusted R2R framework assemblies.

## Initial entry shape

`ValidateEntry(image, entryType, contractAssemblyIdentity)` first applies the
assembly checks, then requires a public, nonabstract, nongeneric, nonnested class
that directly extends `System.Object` and directly implements
`RuneCLR.IMapScript`. That interface TypeRef must resolve to the exact approved
contract assembly identity, not merely an assembly with the same simple name.

The class must declare one public instance parameterless constructor and these
public nongeneric instance callbacks:

```csharp
void OnStart(RuneCLR.IMapContext context);
void OnTick(RuneCLR.MapTick tick);
void OnStop();
```

Callback parameter TypeRefs must also resolve to the approved contract, with
the expected class/value-type signature encoding. Explicit interface methods,
inherited implementations and overloaded callback names are unsupported in
this initial entry profile and receive an explanatory rejection. Helpers,
nested types, generics and ordinary inheritance elsewhere in the assembly are
not rejected solely because the entry shape is restricted.

## Regression evidence

On 2026-10-12, the 24
[intake cases](../tests/RuneCLR.Packaging.Tests/IntakeCases.cs) passed using the
private official SDK `11.0.100-rc.1.26425.128`. They cover full identities and
no submitted-assembly loading; accepted direct entry; size/I/O/PE truncation;
mixed/native entry and CLR directory flags; P/Invoke, InternalCall and native
method flags; invalid method RVAs, body sizes and exception ranges; contract
identity, abstract/constructor/callback rejection; and metadata names unsafe
for package paths.

Mutations start from the real compiled test assembly. The managed-native
directory case tests the R2R/native-directory rejection guard; it is **not**
presented as a genuine crossgen-generated R2R fixture. These tests do not claim
complete malformed-IL detection. The executable packaging harness is run with:

```sh
dotnet run --project tests/RuneCLR.Packaging.Tests -c Release
```

This packaging check is independent of the measured platform execution and
collectible-session results in the development handoff.
