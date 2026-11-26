namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    /// <summary>
    /// Validates author IL for a host that owns its loader, with explicit support for standard BCL
    /// managed delegate construction. Runs strict structural intake and the supplied API policy
    /// without loading or executing the image. Existing Validate/ValidateWithApiPolicy stay strict.
    /// </summary>
    /// <remarks>
    /// Only the known BCL delegate constructor (object, native int), immediately preceded by
    /// ldftn/ldvirtftn and satisfying the shared control-flow checks, receives the signature exception.
    /// Custom delegates, other native signatures and P/Invoke remain rejected. This does not verify
    /// semantic IL type safety or authenticate referenced assembly identities. The trusted host must
    /// bind references to the intended assemblies, validate every private image, load the same owned
    /// bytes it validated, and enforce its execution, reflection and lifetime policies separately.
    /// See docs/external-host-admission.md for the binding and trust contract.
    /// </remarks>
    public static void ValidateWithStandardManagedDelegates(ReadOnlyMemory<byte> image,
        IReadOnlyCollection<string> privateAssemblyIdentities, string contractAssemblyIdentity,
        IApiAccessPolicy apiPolicy, bool allowReflectionTypeTokens = false, bool allowSessionAssemblyNames = false)
    {
        ArgumentNullException.ThrowIfNull(privateAssemblyIdentities);
        ArgumentNullException.ThrowIfNull(apiPolicy);
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw Invalid("Provide a nonempty assembly within the managed-IL image limit.");

        // Own one snapshot across structural intake and capability inspection. A policy callback
        // cannot change the caller's input buffer between the two passes and bypass author intake.
        var snapshot = image.ToArray();
        _ = ManagedAssemblyInspector.Inspect(snapshot);
        ValidateCore(snapshot, privateAssemblyIdentities, contractAssemblyIdentity, null, null, apiPolicy,
            allowReflectionTypeTokens, allowSessionAssemblyNames, allowManagedDelegateConstruction: true);
    }
}
