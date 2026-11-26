# Composable API access rules (2026-11-17)

Status: implemented and functionally accepted on stock .NET on 2026-11-17.
This adds an opt-in implementation of IApiAccessPolicy for API access from an
untrusted context. It does not select a new package profile, widen the managed-IL
envelope, or establish new runtime interception coverage. Existing gameplay
policy and host defaults remain unchanged.

## Public model

The initial C# surface is:

```csharp
public enum ApiRuleEffect { Include, Exclude }
public enum ApiPolicyDefault { Allow, Deny }

public sealed record ApiRule(
    string Id,
    ApiRuleEffect Effect,
    string? AssemblyName = null,
    string? Namespace = null,
    bool IncludeChildNamespaces = true,
    string? TypeName = null,
    ApiTargetKind? MemberKind = null,
    string? MemberName = null,
    ApiMethodSignature? Signature = null);

public sealed class RuleBasedApiAccessPolicy : IApiAccessPolicy
{
    public RuleBasedApiAccessPolicy(ApiPolicyDefault defaultDecision,
        IEnumerable<ApiRule> rules);
    public ApiDecision Evaluate(ApiTarget target, ApiOperation operation);
}
```

All configuration is host-owned and snapshotted; no reflection metadata,
collectible types, assemblies, delegates or author objects are stored. Mutating
the input collection after construction must not change decisions. Rule IDs
are nonempty and unique. Invalid configuration rejects at construction.

Selectors are constraints combined with AND. At least one selector is required.
AssemblyName accepts an exact simple name or a complete assembly identity;
simple names are matching conveniences, not authentication or ownership.
An exact full identity matches the identity supplied at that check: IL admission
sees the AssemblyRef identity, while a runtime reflection check sees the actual
defining assembly. Binding, forwarding or version unification can make those
different. Use simple assembly names or namespaces for version-independent
exclusions; this policy does not resolve binding or authenticate an assembly.
Namespace uses an exact namespace boundary, with optional descendants:
Game.Api matches Game.Api and Game.Api.Child but never Game.ApiOther.
TypeName is the ordinal full declaring type name; nested types use '+'.
MemberName requires TypeName; MemberKind, when supplied, is Method or Field and
requires MemberName. Signature requires a method member and uses the existing
ApiMethodSignature declaration representation, including !0/!!0 generic slots,
return type, parameters, generic arity and instance/static shape.
Selectors reject leading/trailing whitespace and empty dotted/nested type
segments rather than silently storing a rule that cannot match. A constructor
member is spelled .ctor; accessor and explicit-interface names stay literal.
IncludeChildNamespaces has no effect when Namespace is not supplied.

This first slice has no wildcard/regex/string-expression parser and no separate
per-operation rule filter. A selected member's rule applies consistently to
IL Reference and the corresponding runtime operation. Properties/events are
matched by their actual accessor methods. Invalid target/operation shapes fail
closed even under default-allow.

## Precedence and scope

Rules are unordered. Compare matching rules by this lexicographic tuple:

1. Exact method signature > member name > exact type > namespace > assembly.
2. For namespace rules, a deeper namespace is more specific.
3. A complete assembly identity > simple assembly name > no assembly qualifier.
4. A specified member kind > unspecified member kind.

At equal specificity, Exclude wins. The result is independent of enumeration
order. A specific Include can reopen a member under a broader Exclude; a
specific Exclude can close a member under a broader Include. Denials identify
the winning rule or default decision in a bounded host-owned reason string.

Explicit rules are evaluated first, including for session-owned targets. When
no rule matches, a valid target marked IsSessionCode by trusted admission/runtime
ownership is allowed; otherwise the configured default applies. Never infer
session ownership from an assembly name. This keeps ordinary author-defined
types usable without maintaining a name list, while allowing explicit rules.

## Structural references

IL admission checks assembly and type references before member references.
Default-deny must still support opening one method without granting its whole
assembly or type. Therefore an Include descendant may make the necessary
assembly/type ApiOperation.Reference structurally reachable, even when the
broader rule/default denies. This is container reachability, not permission
to invoke or construct arbitrary members. Apply it only to Assembly/Type
Reference, not Invoke/Construct/ReadField/WriteField/CreateDelegate/ReadMetadata.
It must never grant sibling methods or override an excluded exact member.
A broad assembly/namespace Include or an equal-type Include is not a strict
descendant exception and cannot erase a winning exclusion of that type.

Signature and argument types still require their own reference permission;
an included method must not silently allow unrelated signature dependencies.
Static admission and ReflectionAccessProbe must use the same evaluator. Test
actual compiled IL and reflection side effects, not only synthetic targets.
Default-deny image admission also checks referenced BCL/attribute/contract APIs.
The host must explicitly include those dependencies needed by its chosen author
surface; passing a contract identity is not an automatic rule-policy grant.
The one-member example below is a policy decision example, not a complete
allow-list for an arbitrary compiled image.

## Examples and boundaries

Default-allow, closing System.IO except its exact File.Exists(string) overload:

```csharp
IApiAccessPolicy policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow,
[
    new("deny-io", ApiRuleEffect.Exclude, Namespace: "System.IO"),
    new("allow-file-exists", ApiRuleEffect.Include,
        TypeName: "System.IO.File", MemberKind: ApiTargetKind.Method,
        MemberName: "Exists",
        Signature: new("System.Boolean", ["System.String"], 0, false))
]);
```

Allowing a type while excluding one member uses a type rule plus a more specific
member rule. Names here are an example host-owned API, not a built-in RuneCLR
gameplay interface:

```csharp
IApiAccessPolicy policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
[
    new("allow-score-api", ApiRuleEffect.Include,
        AssemblyName: "Game.Contracts", TypeName: "Game.Api.Score"),
    new("deny-delete", ApiRuleEffect.Exclude,
        AssemblyName: "Game.Contracts", TypeName: "Game.Api.Score",
        MemberKind: ApiTargetKind.Method, MemberName: "Delete")
]);
```

Supply the chosen policy through the existing
GroupedHostOptions.AuthorApiPolicy slot, or pass it to the existing explicit
ValidateWithApiPolicy/ReflectionAccessProbe paths. These snippets construct
policies only; a default-deny compiled-image setup must additionally include its
required BCL/attribute/contract dependencies as described above.

- Default-allow plus Exclude namespace System.IO denies that API family.
- Include type Game.Api.Score plus Exclude member Delete permits the remaining
  type surface while closing Delete.
- Default-deny plus Include exact method Game.Api.Score.Read permits that member
  and its structural containers, not sibling calls or type construction.
- Exclude namespace Game.Internal plus Include Game.Internal.Diagnostics.Read
  permits that explicit exception.

The existing loader, P/Invoke rejection, invalid IL/signature checks, delegate
shape restrictions and runtime capability requirements remain separate gates.
Default-allow does not disable them. GroupedHostOptions.AuthorApiPolicy can
consume this policy through its existing slot; no new global switch is needed.
Trusted framework execution is not reclassified as author code.

External hosts that retain their own loaders can explicitly opt in to
[standard managed delegate admission](external-host-admission.md) through
`ValidateWithStandardManagedDelegates`. The existing `ValidateWithApiPolicy`
entry stays strict; API Include rules alone do not enable the delegate exception.

## Verified scope

The solution Release build passed with zero warnings and errors. The Packaging
executable harness passed 363/363, including 30 API-rule cases; Runtime.Tests
passed 156/156; SampleHost --collect exited successfully with both maps collected.

The rule cases cover defaults, precedence, selectors, overload signatures,
immutable snapshots, compiled-IL/reflection agreement, refusal before side
effects, and collection of a retired author context while its policy remains
alive. Structural-reference controls reject contradictory Namespace+TypeName
selectors at the assembly container and preserve matching combinations, true
member descendants and nested-type containers. Default-allow still rejects
P/Invoke and other unsupported intake/signature/delegate shapes; default-deny
requires explicit BCL and contract permissions.

This is stock .NET functional acceptance. Real Spark host configuration remains
an integration follow-up. No interpreter, iOS, performance or security claim
follows from these tests; no private runtime build or performance run was added.
