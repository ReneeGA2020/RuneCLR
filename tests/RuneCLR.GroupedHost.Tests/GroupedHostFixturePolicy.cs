using System.Reflection;
using RuneCLR.Packages;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>
/// Explicit allow policy for the grouped-host fixtures. It is default-deny:
/// - session code may use its own metadata and members (delegate creation stays denied);
/// - the contract surface is the stable fixture contract only;
/// - the grouped framework fixture assembly is granted its documented member list;
/// - ordinary BCL stays on the shared gameplay surface, plus a small explicit list of members the
///   fixture contract needs (System.Action delegate construction/invocation, System.Guid.NewGuid
///   and ArgumentNullException.ThrowIfNull).
/// This is a test-host policy, not a proposal to widen the production gameplay profile.
/// </summary>
internal sealed class GroupedHostFixturePolicy : IApiAccessPolicy
{
    public const string ContractTypeName = "RuneCLR.GroupedHost.Fixtures.IGroupedHostContract";
    public const string FrameworkEntryTypeName = "RuneCLR.GroupedHost.Fixtures.FrameworkEntry";

    private readonly IApiAccessPolicy _baseline;
    private readonly string _frameworkIdentity;
    private readonly string _hostAssemblyIdentity;

    private static readonly Dictionary<string, HashSet<string>> FrameworkSurface = new(StringComparer.Ordinal)
    {
        [FrameworkEntryTypeName] = new(
            ["Initialize", "Describe", "Touch", "SubscribeFrameworkEvent", "UnsubscribeFrameworkEvent",
             "RaiseFrameworkEvent", "NativeThreadProbe"],
            StringComparer.Ordinal)
    };

    private static readonly Dictionary<string, HashSet<string>> AdditionalSurface = new(StringComparer.Ordinal)
    {
        ["System.Action"] = new([".ctor", "Invoke", "BeginInvoke", "EndInvoke"], StringComparer.Ordinal),
        ["System.Guid"] = new(["NewGuid", "ToString", "Equals", "GetHashCode", "CompareTo"], StringComparer.Ordinal),
        ["System.ArgumentNullException"] = new(["ThrowIfNull", ".ctor", "get_Message"], StringComparer.Ordinal),
        // Reflection plumbing for the callback-policy regression (plumbing only; the reflected target
        // is decided by the same policy at runtime, and String.StartsWith stays explicitly denied).
        ["System.Object"] = new(["GetType", "ToString", "Equals", "GetHashCode", "ReferenceEquals"], StringComparer.Ordinal),
        ["System.Exception"] = new([".ctor", "get_Message", "get_InnerException", "GetType"], StringComparer.Ordinal),
        ["System.RuntimeTypeHandle"] = new([], StringComparer.Ordinal),
        ["System.Reflection.MemberInfo"] = new(["get_Name"], StringComparer.Ordinal),
        ["System.Reflection.MethodBase"] = new(["Invoke"], StringComparer.Ordinal),
        ["System.Reflection.MethodInfo"] = new(["Invoke"], StringComparer.Ordinal),
        ["System.Reflection.Assembly"] = new([], StringComparer.Ordinal),
        ["System.Type"] = new(["GetMethod", "GetTypeFromHandle", "get_Assembly"], StringComparer.Ordinal),
        ["System.Runtime.Loader.AssemblyLoadContext"] = new(["GetLoadContext", "LoadFromStream"], StringComparer.Ordinal),
        ["System.IO.MemoryStream"] = new([".ctor"], StringComparer.Ordinal),
        ["System.IO.Stream"] = new([], StringComparer.Ordinal)
    };

    // Explicit test-specific denials evaluated at runtime by the reflection probe. They must be a
    // narrow override, not a broad profile change; the normal author baseline never references these.
    private static readonly Dictionary<string, HashSet<string>> DeniedMembers = new(StringComparer.Ordinal)
    {
        ["System.String"] = new(["StartsWith"], StringComparer.Ordinal)
    };

    private GroupedHostFixturePolicy(IApiAccessPolicy baseline, string frameworkIdentity, string hostAssemblyIdentity)
    {
        _baseline = baseline;
        _frameworkIdentity = frameworkIdentity;
        _hostAssemblyIdentity = hostAssemblyIdentity;
    }

    public static GroupedHostFixturePolicy Create(string contractIdentity, string frameworkIdentity, string? hostAssemblyIdentity = null)
    {
        var baseline = GameplayCapabilityPolicy.CreateApiPolicy(
            scriptAssemblyIdentities: [],
            contractAssemblyIdentity: contractIdentity,
            hostInterface: ContractTypeName,
            allowedMethods: ["Record", "Subscribe", "Unsubscribe", "get_Mode", "get_DynamicImage"]);
        return new GroupedHostFixturePolicy(baseline, frameworkIdentity,
            hostAssemblyIdentity ?? typeof(GroupedHostFixturePolicy).Assembly.FullName!);
    }

    public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (!Enum.IsDefined(operation) || !Enum.IsDefined(target.Kind))
            return ApiDecision.Deny("Unsupported API target or operation.");
        if (target.IsSessionCode)
            return EvaluateSessionCode(target, operation);
        // The host instance itself crosses into entry invocations; approve only its type identity so the host
        // type is not rejected as an unapproved assembly. No host member is approved here.
        if (string.Equals(target.AssemblyIdentity, _hostAssemblyIdentity, StringComparison.OrdinalIgnoreCase) &&
            target.Kind == ApiTargetKind.Type &&
            operation is ApiOperation.Reference or ApiOperation.ReadMetadata)
            return ApiDecision.Allow;
        if (string.Equals(target.AssemblyIdentity, _frameworkIdentity, StringComparison.OrdinalIgnoreCase))
            return EvaluateFrameworkFixture(target, operation);

        if (target.Kind == ApiTargetKind.Assembly && IsPlumbingAssembly(target.AssemblyIdentity) &&
            operation is ApiOperation.Reference or ApiOperation.ReadMetadata)
            return ApiDecision.Allow;
        var type = target.TypeName ?? "";
        var member = target.MemberName ?? "";
        if (DeniedMembers.TryGetValue(type, out var denied) && denied.Contains(member))
            return ApiDecision.Deny("Denied by the grouped-host fixture policy for " + type + "." + member);
        var decision = _baseline.Evaluate(target, operation);
        if (decision.Allowed) return decision;
        if (AdditionalSurface.TryGetValue(type, out var members) &&
            target.Kind == ApiTargetKind.Type &&
            operation is ApiOperation.Reference or ApiOperation.ReadMetadata)
            return ApiDecision.Allow;
        if (AdditionalSurface.TryGetValue(type, out members) && members.Contains(member) &&
            operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Invoke or
                ApiOperation.Construct or ApiOperation.ReadField or ApiOperation.WriteField)
            return ApiDecision.Allow;
        return decision;
    }

    // Exact plumbing assembly for the byte-based load into the author context; token/culture/flags checked.
    private static bool IsPlumbingAssembly(string identity)
    {
        try
        {
            var name = new AssemblyName(identity);
            return string.Equals(name.Name, "System.Runtime.Loader", StringComparison.Ordinal)
                && name.Version is not null
                && string.Equals(Convert.ToHexString(name.GetPublicKeyToken() ?? []).ToLowerInvariant(), "b03f5f7f11d50a3a", StringComparison.Ordinal)
                && string.IsNullOrEmpty(name.CultureName)
                && (name.Flags & AssemblyNameFlags.Retargetable) == 0;
        }
        catch (Exception error) when (error is ArgumentException or FileLoadException)
        {
            return false;
        }
    }

    private static ApiDecision EvaluateSessionCode(ApiTarget target, ApiOperation operation)
    {
        if (operation == ApiOperation.CreateDelegate)
            return ApiDecision.Deny("Delegate creation is not approved by the grouped-host test policy.");
        if (target.Kind == ApiTargetKind.Assembly)
            return operation is ApiOperation.Reference or ApiOperation.ReadMetadata
                ? ApiDecision.Allow
                : ApiDecision.Deny("The operation requires a type or member target.");
        if (target.Kind == ApiTargetKind.Type)
            return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Construct
                ? ApiDecision.Allow
                : ApiDecision.Deny("The operation does not match a type target.");
        return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Invoke or
                ApiOperation.Construct or ApiOperation.ReadField or ApiOperation.WriteField
            ? ApiDecision.Allow
            : ApiDecision.Deny("The operation does not match a member target.");
    }

    private static ApiDecision EvaluateFrameworkFixture(ApiTarget target, ApiOperation operation)
    {
        if (operation == ApiOperation.CreateDelegate)
            return ApiDecision.Deny("Delegate creation is not approved by the grouped-host test policy.");
        if (target.Kind == ApiTargetKind.Assembly)
            return operation is ApiOperation.Reference or ApiOperation.ReadMetadata
                ? ApiDecision.Allow
                : ApiDecision.Deny("The operation requires a type or member target.");

        var type = target.TypeName ?? "";
        if (!FrameworkSurface.TryGetValue(type, out var members))
            return ApiDecision.Deny($"Grouped framework fixture type '{type}' is not approved.");
        if (target.Kind == ApiTargetKind.Type)
            return operation is ApiOperation.Reference or ApiOperation.ReadMetadata
                ? ApiDecision.Allow
                : ApiDecision.Deny("The operation does not match a type target.");

        var member = target.MemberName ?? "";
        if (DeniedMembers.TryGetValue(type, out var denied) && denied.Contains(member))
            return ApiDecision.Deny("Denied by the grouped-host fixture policy for " + type + "." + member);
        if (member.Length == 0 || !members.Contains(member))
            return ApiDecision.Deny($"Grouped framework fixture member '{type}.{member}' is not approved.");
        return operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Invoke
            ? ApiDecision.Allow
            : ApiDecision.Deny("The operation does not match a framework fixture member target.");
    }
}
