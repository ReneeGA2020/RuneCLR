using System.Collections.Immutable;
using System.Reflection;

namespace RuneCLR.Packages;

public enum ApiRuleEffect { Include, Exclude }

public enum ApiPolicyDefault { Allow, Deny }

/// <summary>
/// One host-owned selector for the rule-based API access policy. Selectors are combined with AND and
/// are compared as plain scalar values; no assembly, type, member or delegate is stored.
/// </summary>
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

/// <summary>
/// Opt-in composable include/exclude policy for API access from an untrusted context. Explicit rules
/// are evaluated first; an unmatched valid target marked IsSessionCode is allowed, otherwise the
/// configured default applies. The policy is immutable and stores only scalar selector copies.
/// </summary>
public sealed class RuleBasedApiAccessPolicy : IApiAccessPolicy
{
    private const int MaximumIdLength = 128;
    private const int MaximumReasonLength = 512;
    private const int MaximumSelectorLength = 1024;
    private const int MaximumSignatureParameters = 256;
    private const int MaximumSignatureArity = 256;

    private readonly ImmutableArray<Snapshot> _rules;
    private readonly ApiPolicyDefault _defaultDecision;

    public RuleBasedApiAccessPolicy(ApiPolicyDefault defaultDecision, IEnumerable<ApiRule> rules)
    {
        if (!Enum.IsDefined(defaultDecision))
            throw new ArgumentException("The default decision must be Allow or Deny.", nameof(defaultDecision));
        ArgumentNullException.ThrowIfNull(rules);
        _defaultDecision = defaultDecision;

        var snapshot = ImmutableArray.CreateBuilder<Snapshot>();
        var identifiers = new HashSet<string>(StringComparer.Ordinal);
        foreach (var rule in rules)
        {
            if (rule is null) throw new ArgumentException("A null API rule is not valid.", nameof(rules));
            var id = rule.Id ?? throw new ArgumentException("A rule identifier is required.", nameof(rules));
            if (id.Length == 0 || string.IsNullOrWhiteSpace(id))
                throw new ArgumentException("A rule identifier must be nonempty.", nameof(rules));
            if (id.Length > MaximumIdLength)
                throw new ArgumentException("A rule identifier must be at most " + MaximumIdLength + " characters: " + id, nameof(rules));
            if (!identifiers.Add(id))
                throw new ArgumentException("Duplicate rule identifier: " + id, nameof(rules));
            if (!Enum.IsDefined(rule.Effect))
                throw new ArgumentException("A rule effect must be Include or Exclude: " + id, nameof(rules));
            if (rule.MemberKind is { } kind && kind is not (ApiTargetKind.Method or ApiTargetKind.Field))
                throw new ArgumentException("A rule member kind must be Method or Field: " + id, nameof(rules));
            snapshot.Add(CreateSnapshot(rule, id));
        }
        _rules = snapshot.ToImmutable();
    }

    public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
    {
        if (target is null) return ApiDecision.Deny("Invalid API target.");
        if (!Enum.IsDefined(operation) || !Enum.IsDefined(target.Kind))
            return ApiDecision.Deny("Unsupported API target or operation.");
        var shape = ValidateTarget(target, operation);
        if (shape is not null) return ApiDecision.Deny(shape);

        Snapshot? winner = null;
        var winnerKey = default(Specificity);
        var topExcludes = new List<Snapshot>();
        foreach (var rule in _rules)
        {
            if (!Matches(rule, target)) continue;
            var key = rule.Specificity;
            var comparison = Compare(key, winnerKey);
            if (winner is null || comparison > 0)
            {
                winner = rule;
                winnerKey = key;
                topExcludes.Clear();
            }
            if (Compare(key, winnerKey) == 0 && rule.Effect == ApiRuleEffect.Exclude)
                topExcludes.Add(rule);
        }

        if (winner is not null)
        {
            if (topExcludes.Count == 0) return ApiDecision.Allow;
            // A strict-descendant Include keeps a container Reference reachable under a broader denial;
            // member operations are never granted this way, and an equal-scope Include does not qualify.
            if (operation == ApiOperation.Reference &&
                target.Kind is ApiTargetKind.Assembly or ApiTargetKind.Type &&
                IsStrictDescendantReachable(target))
                return ApiDecision.Allow;
            var reasonId = topExcludes.Select(candidate => candidate.Id).Min(StringComparer.Ordinal)!;
            return ApiDecision.Deny(Bound("Rule '" + reasonId + "' excludes this target."));
        }

        if (operation == ApiOperation.Reference &&
            target.Kind is ApiTargetKind.Assembly or ApiTargetKind.Type &&
            IsStrictDescendantReachable(target))
            return ApiDecision.Allow;

        if (target.IsSessionCode) return ApiDecision.Allow;

        return _defaultDecision == ApiPolicyDefault.Allow
            ? ApiDecision.Allow
            : ApiDecision.Deny("The configured default denies this target.");
    }

    private static Snapshot CreateSnapshot(ApiRule rule, string id)
    {
        var assembly = NormalizeSelector(rule.AssemblyName, "assembly name", id);
        var namespaceName = NormalizeSelector(rule.Namespace, "namespace", id);
        var typeName = NormalizeSelector(rule.TypeName, "type name", id);
        var memberName = NormalizeSelector(rule.MemberName, "member name", id);

        if (assembly is null && namespaceName is null && typeName is null && memberName is null)
            throw new ArgumentException("A rule requires at least one selector: " + id, nameof(rule));
        if (typeName is not null && InvalidTypeName(typeName))
            throw new ArgumentException("A rule type name must not contain empty dotted or nested segments: " + id, nameof(rule));
        // IncludeChildNamespaces only applies to a Namespace selector; it is deliberately not rejected when
        // Namespace is null (the record default true is allowed on rules without a namespace selector).
        if (namespaceName is not null && InvalidNamespace(namespaceName))
            throw new ArgumentException("A rule namespace must be a dotted name without empty segments: " + id, nameof(rule));
        if (memberName is not null && typeName is null)
            throw new ArgumentException("A member name requires a type name: " + id, nameof(rule));
        if (rule.MemberKind is not null && memberName is null)
            throw new ArgumentException("A member kind requires a member name: " + id, nameof(rule));

        ApiMethodSignature? storedSignature = null;
        if (rule.Signature is not null)
        {
            if (memberName is null)
                throw new ArgumentException("A signature requires a member name: " + id, nameof(rule));
            if (rule.MemberKind is { } signatureKind && signatureKind != ApiTargetKind.Method)
                throw new ArgumentException("A signature requires a method member: " + id, nameof(rule));
            var problem = SignatureProblem(rule.Signature);
            if (problem is not null)
                throw new ArgumentException("A rule signature is invalid (" + problem + "): " + id, nameof(rule));
            // Copy the parameter string values so a caller-owned backing array cannot change the policy.
            var parameters = ImmutableArray.CreateBuilder<string>(rule.Signature.ParameterTypes.Length);
            foreach (var parameter in rule.Signature.ParameterTypes) parameters.Add(parameter);
            storedSignature = rule.Signature with { ParameterTypes = parameters.MoveToImmutable() };
        }

        string? assemblySimple = null;
        string? assemblyFull = null;
        if (assembly is not null)
        {
            if (assembly.Contains(',', StringComparison.Ordinal))
            {
                var parsed = ParseFullIdentity(assembly)
                    ?? throw new ArgumentException("A rule assembly identity must be complete (name, version, culture and public key token): " + id, nameof(rule));
                assemblyFull = parsed.FullName;
            }
            else
            {
                if (!IsSimpleName(assembly))
                    throw new ArgumentException("A rule assembly name is not a valid simple name: " + id, nameof(rule));
                assemblySimple = assembly;
            }
        }

        var rank = storedSignature is not null ? 5
            : memberName is not null ? 4
            : typeName is not null ? 3
            : namespaceName is not null ? 2
            : 1;
        // Namespace depth only distinguishes namespace-scoped rules; a redundant namespace qualifier on a
        // type/member/signature rule must not add specificity.
        var namespaceDepth = rank == 2 && namespaceName is not null ? namespaceName.Split('.').Length : 0;
        var assemblySpecificity = assemblyFull is not null ? 2 : assemblySimple is not null ? 1 : 0;
        var kindSpecificity = rule.MemberKind is null ? 0 : 1;

        return new Snapshot(id, rule.Effect, assemblySimple, assemblyFull, namespaceName, namespaceDepth,
            rule.IncludeChildNamespaces, typeName, rule.MemberKind, memberName, storedSignature,
            new Specificity(rank, namespaceDepth, assemblySpecificity, kindSpecificity));
    }

    private static string? NormalizeSelector(string? value, string label, string id)
    {
        if (value is null) return null;
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("A rule " + label + " must be nonempty: " + id, nameof(value));
        if (value.Length != value.Trim().Length)
            throw new ArgumentException("A rule " + label + " must not have leading or trailing whitespace: " + id, nameof(value));
        if (value.Contains('*') || value.Contains('?'))
            throw new ArgumentException("Wildcard selectors are not supported (no glob engine): " + id, nameof(value));
        if (value.Length > MaximumSelectorLength)
            throw new ArgumentException("A rule " + label + " must be at most " + MaximumSelectorLength + " characters: " + id, nameof(value));
        return value;
    }

    private static bool InvalidTypeName(string value)
    {
        if (value.Length == 0) return true;
        if (value[0] == '.' || value[^1] == '.' || value[0] == '+' || value[^1] == '+') return true;
        foreach (var segment in value.Split(['.', '+']))
        {
            if (segment.Length == 0 || string.IsNullOrWhiteSpace(segment)) return true;
        }
        return false;
    }

    private static bool InvalidNamespace(string value)
    {
        if (value.Length == 0 || value[0] == '.' || value[^1] == '.' || value.Contains("..", StringComparison.Ordinal)) return true;
        foreach (var segment in value.Split('.'))
        {
            if (segment.Length == 0 || string.IsNullOrWhiteSpace(segment)) return true;
            if (segment.Contains('+', StringComparison.Ordinal)) return true;
        }
        return false;
    }

    private static bool IsSimpleName(string value)
    {
        if (value.Length == 0 || string.IsNullOrWhiteSpace(value)) return false;
        foreach (var character in value)
        {
            if (char.IsWhiteSpace(character) || character is ',' or '=' or '+' or '/' or (char)92 or ':') return false;
        }
        return true;
    }

    /// <summary>
    /// Parses a complete assembly identity: name, version, an explicit culture and an explicit public
    /// key token in the text, then a successful AssemblyName parse. Partial identities are rejected.
    /// </summary>
    private static AssemblyName? ParseFullIdentity(string identity)
    {
        if (!identity.Contains(',', StringComparison.Ordinal) ||
            !identity.Contains("Version=", StringComparison.OrdinalIgnoreCase) ||
            !identity.Contains("Culture=", StringComparison.OrdinalIgnoreCase) ||
            !identity.Contains("PublicKeyToken=", StringComparison.OrdinalIgnoreCase))
            return null;
        try
        {
            var name = new AssemblyName(identity);
            if (string.IsNullOrEmpty(name.Name) || name.Version is null) return null;
            return name;
        }
        catch (Exception error) when (error is ArgumentException or FileLoadException)
        {
            return null;
        }
    }

    private static string? SignatureProblem(ApiMethodSignature signature)
    {
        if (string.IsNullOrWhiteSpace(signature.ReturnType)) return "missing return type";
        if (signature.ReturnType.Length > MaximumSelectorLength) return "unbounded return type";
        if (signature.ParameterTypes.IsDefault) return "missing parameter types";
        if (signature.ParameterTypes.Length > MaximumSignatureParameters) return "too many parameters";
        foreach (var parameter in signature.ParameterTypes)
        {
            if (string.IsNullOrWhiteSpace(parameter)) return "empty parameter type";
            if (parameter.Length > MaximumSelectorLength) return "unbounded parameter type";
        }
        if (signature.GenericArity < 0 || signature.GenericArity > MaximumSignatureArity)
            return "generic arity out of range";
        return null;
    }

    private static int Compare(Specificity left, Specificity right)
    {
        if (left.Rank != right.Rank) return left.Rank.CompareTo(right.Rank);
        if (left.NamespaceDepth != right.NamespaceDepth) return left.NamespaceDepth.CompareTo(right.NamespaceDepth);
        if (left.AssemblySpecificity != right.AssemblySpecificity) return left.AssemblySpecificity.CompareTo(right.AssemblySpecificity);
        return left.KindSpecificity.CompareTo(right.KindSpecificity);
    }

    private static bool Matches(Snapshot rule, ApiTarget target)
    {
        if (!AssemblySelectorMatches(rule, target.AssemblyIdentity)) return false;

        if (rule.Namespace is not null)
        {
            var typeNamespace = NamespaceOf(target.TypeName);
            if (!NamespaceMatches(rule, typeNamespace)) return false;
        }
        if (rule.TypeName is not null && !string.Equals(rule.TypeName, target.TypeName, StringComparison.Ordinal))
            return false;
        if (rule.MemberName is not null && !string.Equals(rule.MemberName, target.MemberName, StringComparison.Ordinal))
            return false;
        if (rule.MemberKind is { } kind && target.Kind != kind) return false;
        if (rule.Signature is not null)
        {
            if (target.Kind != ApiTargetKind.Method || target.Signature is null) return false;
            if (!SignatureMatches(rule.Signature, target.Signature)) return false;
        }
        return true;
    }

    private static bool AssemblySelectorMatches(Snapshot rule, string identity)
    {
        if (rule.AssemblySimpleName is null && rule.AssemblyFullName is null) return true;
        var target = ParseFullIdentity(identity);
        if (target is null) return false;
        if (rule.AssemblyFullName is not null)
        {
            var expected = ParseFullIdentity(rule.AssemblyFullName);
            return expected is not null && IdentityEquals(expected, target);
        }
        return string.Equals(rule.AssemblySimpleName, target.Name, StringComparison.OrdinalIgnoreCase);
    }

    private static bool IdentityEquals(AssemblyName expected, AssemblyName actual)
    {
        if (!string.Equals(expected.Name, actual.Name, StringComparison.OrdinalIgnoreCase)) return false;
        if (expected.Version != actual.Version) return false;
        if (!string.Equals(expected.CultureName ?? string.Empty, actual.CultureName ?? string.Empty, StringComparison.OrdinalIgnoreCase))
            return false;
        var expectedToken = expected.GetPublicKeyToken() ?? [];
        var actualToken = actual.GetPublicKeyToken() ?? [];
        if (expectedToken.Length != actualToken.Length) return false;
        for (var index = 0; index < expectedToken.Length; index++)
        {
            if (expectedToken[index] != actualToken[index]) return false;
        }
        return true;
    }

    private static string? NamespaceOf(string? typeName)
    {
        if (string.IsNullOrEmpty(typeName)) return null;
        var separator = typeName.IndexOf('+', StringComparison.Ordinal);
        var outer = separator < 0 ? typeName : typeName[..separator];
        var lastDot = outer.LastIndexOf('.');
        return lastDot <= 0 ? string.Empty : outer[..lastDot];
    }

    private static bool NamespaceMatches(Snapshot rule, string? typeNamespace)
    {
        if (typeNamespace is null) return false;
        if (string.Equals(rule.Namespace, typeNamespace, StringComparison.Ordinal)) return true;
        return rule.IncludeChildNamespaces &&
            typeNamespace.StartsWith(rule.Namespace + ".", StringComparison.Ordinal);
    }

    private static bool SignatureMatches(ApiMethodSignature declared, ApiMethodSignature actual)
    {
        if (!string.Equals(declared.ReturnType, actual.ReturnType, StringComparison.Ordinal)) return false;
        if (declared.GenericArity != actual.GenericArity || declared.IsInstance != actual.IsInstance) return false;
        if (declared.ParameterTypes.IsDefault || actual.ParameterTypes.IsDefault) return false;
        if (declared.ParameterTypes.Length != actual.ParameterTypes.Length) return false;
        for (var index = 0; index < declared.ParameterTypes.Length; index++)
        {
            if (!string.Equals(declared.ParameterTypes[index], actual.ParameterTypes[index], StringComparison.Ordinal))
                return false;
        }
        return true;
    }

    /// <summary>
    /// True only when an Include rule selects something strictly below the queried container, so a
    /// broader denial on the container does not make that descendant unreachable. An equal-scope Include,
    /// an ancestor assembly/namespace Include, and any Include that does not satisfy all of its own
    /// selector constraints (including a Namespace qualifier next to a TypeName) do not qualify.
    /// </summary>
    private bool IsStrictDescendantReachable(ApiTarget target)
    {
        foreach (var rule in _rules)
        {
            if (rule.Effect != ApiRuleEffect.Include) continue;
            if (!AssemblySelectorMatches(rule, target.AssemblyIdentity)) continue;
            // Every selector of the candidate rule must be satisfiable together, at every container level:
            // a Namespace qualifier has to cover the namespace of the rule own TypeName when both are present.
            if (rule.Namespace is not null && rule.TypeName is not null &&
                !NamespaceMatches(rule, NamespaceOf(rule.TypeName))) continue;

            if (target.Kind == ApiTargetKind.Assembly)
            {
                // Assembly-only includes are direct matches; only namespace/type/member includes are below it.
                if (rule.Namespace is not null || rule.TypeName is not null || rule.MemberName is not null) return true;
                continue;
            }

            var container = target.TypeName;
            if (string.IsNullOrEmpty(container)) continue;
            if (rule.Namespace is not null && !NamespaceMatches(rule, NamespaceOf(container))) continue;
            if (rule.TypeName is null) continue;
            if (rule.MemberName is not null && string.Equals(rule.TypeName, container, StringComparison.Ordinal)) return true;
            if (rule.TypeName.StartsWith(container + "+", StringComparison.Ordinal)) return true;
        }
        return false;
    }

    private static string? ValidateTarget(ApiTarget target, ApiOperation operation)
    {
        if (string.IsNullOrWhiteSpace(target.AssemblyIdentity)) return "A target assembly identity is required.";
        if (ParseFullIdentity(target.AssemblyIdentity) is null)
            return "A target requires a complete assembly identity (name, version, culture and public key token).";

        switch (target.Kind)
        {
            case ApiTargetKind.Assembly:
                if (target.TypeName is not null || target.MemberName is not null || target.Signature is not null)
                    return "An assembly target cannot carry type or member fields.";
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata
                    ? null
                    : "The operation requires a type or member target.";
            case ApiTargetKind.Type:
                if (string.IsNullOrWhiteSpace(target.TypeName)) return "A target declaring type is required.";
                if (target.MemberName is not null || target.Signature is not null)
                    return "A type target cannot carry member or signature fields.";
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Construct
                    ? null
                    : "The operation does not match a type target.";
            case ApiTargetKind.Field:
                if (string.IsNullOrWhiteSpace(target.TypeName)) return "A target declaring type is required.";
                if (string.IsNullOrWhiteSpace(target.MemberName)) return "A target member name is required.";
                if (target.Signature is not null) return "A field target cannot carry a method signature.";
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.ReadField or ApiOperation.WriteField
                    ? null
                    : "The operation does not match a field target.";
            case ApiTargetKind.Method:
                if (string.IsNullOrWhiteSpace(target.TypeName)) return "A target declaring type is required.";
                if (string.IsNullOrWhiteSpace(target.MemberName)) return "A target member name is required.";
                if (target.Signature is { } signature)
                {
                    var problem = SignatureProblem(signature);
                    if (problem is not null) return "A method target signature is malformed (" + problem + ").";
                }
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Invoke or
                        ApiOperation.Construct or ApiOperation.CreateDelegate
                    ? null
                    : "The operation does not match a method target.";
            default:
                return "Unsupported API target kind.";
        }
    }

    private static string Bound(string reason) =>
        reason.Length <= MaximumReasonLength ? reason : reason[..MaximumReasonLength];

    private readonly record struct Specificity(int Rank, int NamespaceDepth, int AssemblySpecificity, int KindSpecificity);

    private sealed record Snapshot(
        string Id,
        ApiRuleEffect Effect,
        string? AssemblySimpleName,
        string? AssemblyFullName,
        string? Namespace,
        int NamespaceDepth,
        bool IncludeChildNamespaces,
        string? TypeName,
        ApiTargetKind? MemberKind,
        string? MemberName,
        ApiMethodSignature? Signature,
        Specificity Specificity);
}
