using System.Reflection;

namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    /// <summary>Creates an immutable adapter for the existing gameplay surface.
    /// Script identities must come from the caller's validated script images, not author claims.</summary>
    public static IApiAccessPolicy CreateApiPolicy(IReadOnlyCollection<string> scriptAssemblyIdentities,
        string contractAssemblyIdentity, string? hostInterface = null, IReadOnlyCollection<string>? allowedMethods = null)
        => new GameplayApiAccessPolicy(scriptAssemblyIdentities, contractAssemblyIdentity, hostInterface, allowedMethods);

    private sealed class GameplayApiAccessPolicy : IApiAccessPolicy
    {
        private readonly HashSet<string> scripts = new(StringComparer.Ordinal);
        private readonly string contract;
        private readonly string? hostInterface;
        private readonly HashSet<string>? hostMethods;

        internal GameplayApiAccessPolicy(IReadOnlyCollection<string> identities, string contract,
            string? hostInterface, IReadOnlyCollection<string>? allowedMethods)
        {
            ArgumentNullException.ThrowIfNull(identities);
            this.contract = FullIdentity(contract);
            if (hostInterface is null && new AssemblyName(this.contract).Name != "RuneCLR.Abstractions")
                throw Invalid("The approved contract must be RuneCLR.Abstractions.");
            this.hostInterface = hostInterface;
            hostMethods = allowedMethods is null ? null : new(allowedMethods, StringComparer.Ordinal);
            if (hostInterface is not null && hostMethods is null)
                throw Invalid("The host interface and allowed methods must both be present, nonempty and unique.");
            foreach (var identity in identities)
            {
                var full = FullIdentity(identity);
                if (Reserved(new AssemblyName(full).Name!))
                    throw Invalid($"Private assembly '{full}' spoofs a framework or host assembly name.");
                scripts.Add(full);
            }
        }

        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            ArgumentNullException.ThrowIfNull(target);
            if (!Enum.IsDefined(operation) || !Enum.IsDefined(target.Kind))
                return ApiDecision.Deny("Unsupported API target or operation.");
            string identity;
            try { identity = FullIdentity(target.AssemblyIdentity); }
            catch (Exception error) when (error is ArgumentException or FileLoadException or InvalidDataException)
            { return ApiDecision.Deny("A full assembly identity is required."); }
            var assembly = CheckAssembly(identity);
            if (!assembly.Allowed) return assembly;
            if (target.Kind == ApiTargetKind.Assembly)
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata ? ApiDecision.Allow :
                    ApiDecision.Deny("The operation requires a type or member target.");
            if (string.IsNullOrEmpty(target.TypeName)) return ApiDecision.Deny("A declaring type is required.");
            var customHost = identity == contract && target.TypeName == hostInterface && !Contract.ContainsKey(target.TypeName);
            var script = scripts.Contains(identity);
            var surface = identity == contract ? Contract : Framework;
            if (!script && !customHost && !surface.ContainsKey(target.TypeName))
                return ApiDecision.Deny($"Type '{target.TypeName}' is not approved.");
            if (target.Kind == ApiTargetKind.Type)
                return operation is ApiOperation.Reference or ApiOperation.ReadMetadata ? ApiDecision.Allow :
                    ApiDecision.Deny("The operation requires a member target.");
            if (string.IsNullOrEmpty(target.MemberName)) return ApiDecision.Deny("A member name is required.");
            if (operation == ApiOperation.CreateDelegate)
                return ApiDecision.Deny("Delegate creation is not approved by the initial gameplay profile.");
            if (target.Kind == ApiTargetKind.Field)
            {
                if (script && operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.ReadField or ApiOperation.WriteField)
                    return ApiDecision.Allow;
                if (script) return ApiDecision.Deny("The operation does not match a field target.");
                return ApiDecision.Deny(customHost || !surface[target.TypeName].Contains(target.MemberName)
                    ? $"Member '{target.TypeName}.{target.MemberName}' is not approved."
                    : $"Field '{target.TypeName}.{target.MemberName}' is not approved.");
            }
            if (operation is not (ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Invoke or ApiOperation.Construct))
                return ApiDecision.Deny("The operation does not match a method target.");
            if ((operation == ApiOperation.Construct && target.MemberName != ".ctor") ||
                (operation == ApiOperation.Invoke && target.MemberName is ".ctor" or ".cctor"))
                return ApiDecision.Deny("The operation does not match the constructor target.");
            if (script || (customHost ? hostMethods!.Contains(target.MemberName) : surface[target.TypeName].Contains(target.MemberName)))
                return ApiDecision.Allow;
            return ApiDecision.Deny($"Member '{target.TypeName}.{target.MemberName}' is not approved.");
        }

        private ApiDecision CheckAssembly(string identity)
        {
            if (identity == contract || scripts.Contains(identity)) return ApiDecision.Allow;
            var name = new AssemblyName(identity);
            var token = Convert.ToHexString(name.GetPublicKeyToken() ?? []).ToLowerInvariant();
            var allowed = name.Name is "System.Runtime" or "System.Collections" or "System.Linq" or "System.ObjectModel" or "System.Runtime.Extensions";
            if (((allowed && token == "b03f5f7f11d50a3a") ||
                 (name.Name == "System.Private.CoreLib" && token == "7cec85d7bea7798e")) &&
                string.IsNullOrEmpty(name.CultureName) && name.ContentType == AssemblyContentType.Default &&
                (name.Flags & AssemblyNameFlags.Retargetable) == 0) return ApiDecision.Allow;
            return ApiDecision.Deny($"Assembly '{identity}' is not approved.");
        }
    }

    private static bool Reserved(string name) => new[] { "mscorlib", "netstandard", "System", "Microsoft", "RuneCLR" }.Contains(name, StringComparer.OrdinalIgnoreCase) ||
        name.StartsWith("System.", StringComparison.OrdinalIgnoreCase) ||
        name.StartsWith("Microsoft.", StringComparison.OrdinalIgnoreCase) ||
        name.StartsWith("RuneCLR.", StringComparison.OrdinalIgnoreCase);

    private static string FullIdentity(string identity)
    {
        var name = new AssemblyName(identity);
        if (name.Version is null || string.IsNullOrEmpty(name.Name) || !identity.Contains("PublicKeyToken=", StringComparison.OrdinalIgnoreCase) ||
            !identity.Contains("Culture=", StringComparison.OrdinalIgnoreCase))
            throw Invalid("Assembly identities must include version, culture and public-key token.");
        return name.FullName!;
    }
}
