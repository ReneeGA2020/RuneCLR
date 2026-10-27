using System.Collections.Immutable;

namespace RuneCLR.Packages;

public enum ApiTargetKind { Assembly, Type, Method, Field }

public enum ApiOperation
{
    Reference, ReadMetadata, Invoke, Construct, ReadField, WriteField, CreateDelegate
}

// Value-only identities can cross the policy boundary without rooting a collectible assembly.
// The legacy policy matches member names; signature/IL validation remains a separate gate.
public sealed record ApiTarget(string AssemblyIdentity, ApiTargetKind Kind,
    string? TypeName = null, string? MemberName = null, ApiMethodSignature? Signature = null);

public sealed record ApiMethodSignature(string ReturnType, ImmutableArray<string> ParameterTypes,
    int GenericArity, bool IsInstance);

public readonly record struct ApiDecision(bool Allowed, string? Reason)
{
    public static ApiDecision Allow => new(true, null);
    public static ApiDecision Deny(string reason) => new(false, reason);
}

/// <summary>A decision over a resolved target, not an assembly loader or runtime interceptor.</summary>
public interface IApiAccessPolicy
{
    ApiDecision Evaluate(ApiTarget target, ApiOperation operation);
}
