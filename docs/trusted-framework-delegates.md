# Trusted framework delegate metadata for external loaders

An external loader can optionally admit delegates defined by a trusted framework
without loading author code or migrating to `GroupedHostSession`. The host supplies
actual provider bytes and selects the delegate TypeDefs it intends to share. A
type name selects a definition to verify; it is not a standalone trust grant.

```csharp
TrustedDelegateProvider evidence = TrustedDelegateProvider.Create(
    trustedProviderBytes, "Game.Callbacks.RequestHandler`1");

// Check evidence.AssemblyIdentity AND evidence.ImageSha256 against the approved
// inventory and the exact provider bytes/Assembly instance returned by the binder.
GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(
    ownedAuthorImage, approvedAuthorPrivateIdentities, contractIdentity,
    apiPolicy, [evidence],
    allowReflectionTypeTokens: false,
    allowSessionAssemblyNames: false);
// Load this same ownedAuthorImage through the already-configured author loader.
```

## Public API

```csharp
public sealed class TrustedDelegateProvider
{
    public string AssemblyIdentity { get; }
    public string ImageSha256 { get; }
    public ImmutableArray<string> DelegateTypeNames { get; }
    public static TrustedDelegateProvider Create(
        ReadOnlyMemory<byte> providerImage, params string[] delegateTypeNames);
}

public static void GameplayCapabilityPolicy.ValidateWithTrustedManagedDelegates(
    ReadOnlyMemory<byte> image,
    IReadOnlyCollection<string> privateAssemblyIdentities,
    string contractAssemblyIdentity,
    IApiAccessPolicy apiPolicy,
    IReadOnlyCollection<TrustedDelegateProvider> trustedProviders,
    bool allowReflectionTypeTokens = false,
    bool allowSessionAssemblyNames = false);
```

This entry includes standard BCL delegate support, strict author structural
intake and the supplied API policy. `Validate`, `ValidateWithApiPolicy` and
`ValidateWithStandardManagedDelegates` retain their existing semantics. Evidence
has no effect unless passed to the new entry. Both independent type-token/name
options retain default false.

## Definition evidence

`Create` snapshots a provider image (at most 32 MiB), records its SHA-256 and full
assembly identity, and reads the selected definitions without loading the
provider. It retains immutable definition/signature values, not image bytes,
`Type`, `Assembly`, delegates or a `MetadataReader` lifetime. Select 1–256 unique
names per image; validation accepts at most 64 providers. Duplicate/conflicting
provider simple names reject, even if versions or selected type sets differ.
Select all needed types from one provider in a single evidence object.

Selected types must be sealed, field/interface-free direct descendants of the
BCL `System.MulticastDelegate` reference shape, with public managed runtime
`.ctor` and virtual `Invoke` definitions. Ordinary generated `BeginInvoke` and
`EndInvoke` definitions are recognized too. The constructor requires exact
instance `void(object, native int)` and constructor flags. Selected native
signatures, missing definitions and malformed shapes reject. Unrelated native
methods in a trusted provider are not author code: the whole provider is **not**
put through author P/Invoke/InternalCall rejection to obtain this evidence.

Author references must match full provider identity, declaring type, generic
arity and actual method signature. Signatures preserve type identities,
declaration generic slots, array/byref and generic instantiations. Arguments are
checked normally, substituted into `Invoke`, and its dependencies are checked by
the same API policy. The constructor exception still requires `newobj` directly
after `ldftn`/`ldvirtftn` and the existing branch/switch/EH-boundary checks.

The target method, including an author's own MethodDef, is checked by the API
policy. Its resolved parameters and return type must **exactly** match the
substituted `Invoke`: closed generic methods and ordinary instance handlers are
supported. Covariant/contravariant conversions requiring assignability analysis,
custom modifiers and nonstandard delegate signatures are outside this slice.
Unresolved method-generic arguments and signature identities that need assembly
version unification/type-forwarding equivalence are not inferred by this proof;
such unsupported cases reject rather than assuming the binder's equivalence.
This is not full semantic stack/type verification; CLR validation and host trust
remain necessary. `Task<bool>(object,T)` is a supported shape, but this does not
establish asynchronous scheduling, callback drain or execution budgets.

## Host obligations and policy

- Acquire provider bytes from a controlled host inventory. Bind the recorded
  **identity and hash** to the exact provider bytes/shared Assembly instance and
  its trusted dependencies. Names, public key tokens and metadata hashes do not
  authenticate an untrusted source by themselves.
- Keep trusted framework evidence separate from author-private identities.
  Provider simple-name overlap with the author image or private inventory rejects.
  An author's delegate declaration gains no exception. Do not relabel trusted
  framework providers as author-private to work around a refusal.
- The resolver must return that intended shared provider and contract instance,
  not replacement bytes advertising the same identity. Genuine BCL binding is
  the host's responsibility too. No loading or resolver hook is installed here.
- Validate every author-private/dynamically discovered image before loading,
  and load those same owned bytes. Follow the
  [external-host byte-binding contract](external-host-admission.md). A recorded
  hash does not prevent later replacement of a mutable filesystem path.
- Delegate type, constructor, actual `Invoke` references, handler, generic
  arguments and signature dependencies still obey include/exclude. Same-rank
  Exclude wins; structural reachability never grants sibling calls or arbitrary
  native signatures. Default-deny requires the chosen BCL/provider/contract and
  other dependency Includes. An identity argument is not a policy grant.
- Reflection target checks remain a separate trusted boundary. This API does
  not automatically intercept author reflection or expand `ReflectionAccessProbe`
  delegate-factory support. Configure required execution mode before author load.
- Own callback registration, drain, resource cleanup and retirement. A legal
  framework delegate can retain an author context; observe collection after
  execution stacks return.

## Verification scope

The public fixture supplies generic `Task<bool>` delegates plus an unrelated
trusted InternalCall. Controls cover definitions, generic substitution, evidence
identity/signature conflicts, author/private overlap, unsafe arguments, handler
signatures, construction IL and rules. Neither evidence creation nor author
validation loads provider or author images. Current stock-.NET results are in
[the handoff](development.md).

Company bytes, source and raw logs are not public fixtures. Any separate local
engine metadata-only comparison is not a real-client run, interpreter witness
or lifecycle acceptance. No CoreCLR, tiering, iOS, performance or sandbox claim
is established.
