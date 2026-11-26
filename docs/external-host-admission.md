# Managed delegate admission for external hosts

An embedding host can keep its own loader and opt in to the same standard BCL
delegate construction checks used by `GroupedHostSession`. It need not migrate
to `GroupedHostSession` or call an internal RuneCLR method. The additive public
entry point in `RuneCLR.Packages` is:

```csharp
public static void GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(
    ReadOnlyMemory<byte> image,
    IReadOnlyCollection<string> privateAssemblyIdentities,
    string contractAssemblyIdentity,
    IApiAccessPolicy apiPolicy,
    bool allowReflectionTypeTokens = false,
    bool allowSessionAssemblyNames = false);
```

This method runs strict `ManagedAssemblyInspector.Inspect` author intake and
the shared capability checker against one owned snapshot of the image. It does
not load or execute input assemblies. Rejection throws `InvalidDataException`;
a policy denial includes its bounded reason, including a rule ID when using
`RuleBasedApiAccessPolicy`. No assembly, delegate or collectible reflection
metadata is returned or retained by the validator.

`Validate`, `ValidateWithApiPolicy`, and versioned package defaults retain their
strict behavior, including rejection of delegate native-int constructors. The
new entry point is an explicit host-owned opt-in, not a new package manifest
profile or a global permission switch. Its two optional flags retain their
existing separate meaning: a delegate opt-in alone does not enable type-token
reflection inputs or reserved session assembly names. Leave both false unless
the host deliberately needs and controls those routes.

## Accepted scope

The exception covers known standard BCL delegates: `Action`, `Action<T...>`
(1–16 arguments), `Func<T...>` (1–17 type arguments including the result),
`Predicate<T>`, `Comparison<T>`, `Converter<TIn,TOut>`, `EventHandler`, and
`EventHandler<TEventArgs>`. Ordinary C# method groups, closures, and virtual
method callbacks can use those types. Custom delegates, including delegates
declared in a game's contract assembly, remain unsupported by this exception.

A constructor must reference one of those types under `System.Runtime` or
`System.Private.CoreLib` with the expected .NET public key token, have exactly
the instance `void(object, native int)` signature, and be used only by `newobj`
directly following `ldftn` or `ldvirtftn`. A branch/switch target or exception
region boundary at that `newobj` is rejected. Generic arguments, target methods,
and other signatures still pass through their normal checks and API rules.
The native-int slot is scoped to this constructor; arbitrary `IntPtr`, pointer,
function-pointer, P/Invoke, InternalCall, unsupported IL, and malformed delegate
uses do not gain permission. A policy can still deny the delegate type,
constructor, target method, or a dependency.

This is metadata and bounded instruction-pattern validation, **not semantic IL
verification**. It does not prove full stack/type correctness or authenticate a
reference just because its name/token matches. Normal CLR validation and the
host's trusted binding and execution controls remain necessary.

## Minimum host integration

Use the existing [composable rules](api-access-rules.md). A host may choose
default-allow and exclude API families, or default-deny and explicitly include
the BCL, attributes, contract and shared API dependencies it needs. Supplying
`contractAssemblyIdentity` does not automatically allow that contract under a
custom policy. The following fragment illustrates an already configured
external loader; it does not configure that loader or its execution backend:

```csharp
using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.Packages;

static Assembly AdmitAndLoad(
    AssemblyLoadContext authorContext, string authorPath,
    IReadOnlyCollection<string> approvedPrivateIdentities,
    string sharedContractIdentity, IApiAccessPolicy policy)
{
    // The trusted host owns this buffer for validation AND loading. Do not read
    // the path again after validation or allow this buffer to be mutated.
    byte[] ownedImage = File.ReadAllBytes(authorPath);
    GameplayCapabilityPolicy.ValidateWithStandardManagedDelegates(
        ownedImage, approvedPrivateIdentities, sharedContractIdentity, policy);
    using var input = new MemoryStream(ownedImage, writable: false);
    return authorContext.LoadFromStream(input);
}

IApiAccessPolicy policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow,
[
    new("deny-io", ApiRuleEffect.Exclude, Namespace: "System.IO"),
    new("allow-exists", ApiRuleEffect.Include, TypeName: "System.IO.File",
        MemberKind: ApiTargetKind.Method, MemberName: "Exists",
        Signature: new("System.Boolean", ["System.String"], 0, false))
]);
```

The containing application references `RuneCLR.Packages`; it supplies its own
contract identity and load context. For example, default-deny code using only
CoreLib or the framework reference facade might start with Includes for
`System.Private.CoreLib` and `System.Runtime`, then add the chosen host APIs.
These are dependency examples, not a complete allowlist for every game.
Exact-signature rules see declaration shapes (including `!0`/`!!0`). A rule for
the supported delegate constructor sees `System.Void`, parameters
`System.Object`/`System.IntPtr`, generic arity 0 and `IsInstance=true`; it can
deny that constructor despite the structural exception. A narrow Include of a
target method under a wider Exclude does not grant its sibling methods.

## Binding and trust obligations

- Build the approved private identity set from the host's controlled image
  inventory, not an author's name claims. Every private image and dynamically
  discovered dependency needs its own admission **before** any CLR load.
  An identity listed here marks session ownership; it does not itself validate
  or authorize those dependency bytes.
- Bind the exact intended shared contract/provider assembly instances, approved
  private bytes and genuine runtime BCL assemblies. The delegate name/public key
  token check is a metadata selector, not cryptographic authentication. A custom
  resolver must not satisfy an apparently trusted BCL reference with an author's
  replacement, even one advertising the same full identity or token.
- Keep an owned, stable snapshot from validation through loading. Use that
  buffer/stream for loading as above, or enforce an equivalent byte-identity
  binding for a path-based loader. A SHA-256 alone does not prevent a later path
  replacement; validation of one file followed by loading different bytes is
  outside the contract. The validator's internal snapshot protects its two
  passes; it cannot make the host's later load immutable.
- API policy is trusted host code. Keep it deterministic and stable across all
  images and runtime checks. Exact full-identity rules see AssemblyRef identities
  during admission; runtime reflection sees actual defining identities, which
  binding/forwarding may change. Prefer simple-name/namespace selectors for
  exclusions that must span those versions.
- Configure required interpretation and any execution limits before author
  loading/execution when the selected integration requires them. This entry
  point does not select an execution backend, install a runtime loading hook,
  or grant native loading. It does not widen trusted framework permissions.
- Apply the same policy at actual reflection targets through an explicit trusted
  `ReflectionAccessProbe` boundary or separately verified runtime enforcement.
  Static acceptance does not automatically intercept arbitrary author reflection,
  nor expand the probe's independent delegate-factory restrictions.
- Own callback registration, drain/unregister, roots and group retirement. A
  legal delegate can still keep an author context alive. Clear callbacks and
  shared resources before observing collection after execution stacks return.

These responsibilities apply even under default-allow. An external host must
not use author admission as a security sandbox or mistake it for a guarantee
that every original game entry is supported. Other managed-IL restrictions can
still reject that entry after its ordinary delegate creation becomes supported.

## Validation scope

The executable Packaging harness covers both the public and internal grouped
routes on the existing delegate construction/control-flow mutations, plus
public-only rules, malformed/signature/identity controls, native import rejection,
independent options, no-author-load/side-effect observation and image snapshot
ownership. See the current results in [the development handoff](development.md).
These are stock .NET checks. No real-engine run, CoreCLR change, interpreter
method-entry proof, iOS validation, performance or sandbox claim is part of this
increment.
