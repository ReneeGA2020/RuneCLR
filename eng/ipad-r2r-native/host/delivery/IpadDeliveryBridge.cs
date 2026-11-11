using System;
using RuneCLR.TrustedUpdate;

namespace RuneCLR.IpadDelivery;

/// <summary>
/// Portable entry used by the iPad host: the required compatibility gate is passed to the core
/// recovery selector as its candidateCheck, so it runs after the host-SPKI verification of the
/// offered candidate AND of the last-known-good candidate from the receipt, and before the
/// host-loaded activation. No temporary activator wrapper is used.
/// </summary>
public static partial class IpadDeliveryBridge
{
    /// <summary>
    /// Process start: offered release (may be null) then receipt fallback, both gated by the same
    /// required compatibility check. The check receives the real content root and the candidate
    /// verified from the host SPKI for that same root.
    /// </summary>
    public static TrustedReleaseRecoveryStart Start(
        DeliveryOptions options,
        TrustedReleaseOffer? offer,
        TrustedUpdateActivator activator)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(activator);
        options.Validate();
        var spki = options.HostSubjectPublicKeyInfo;
        var target = options.Target;
        var contract = options.HostDeploymentContractPath;

        return TrustedReleaseRecovery.TryStart(offer, spki, target, options.AllowedReleasesRoot,
            options.RecoveryReceiptPath, activator,
            (contentRoot, candidate) => Check(options, contentRoot, candidate));
    }

    // Single compatibility predicate used by EVERY entry point (DeliverAsync, Start with an offer,
    // Start with a null offer restoring the receipt). It combines the host-owned Contract identity
    // cross-check with the verified signed-sidecar membership/hash/schema/identity check and passes
    // the bounded sidecar read. No caller may run a parallel, weaker check.
    private static bool Check(DeliveryOptions options, string contentRoot, TrustedUpdateCandidate candidate)
        => Check(options, contentRoot, candidate, out _, out _);

    internal static bool Check(DeliveryOptions options, string contentRoot, TrustedUpdateCandidate candidate,
        out string status, out string detail)
    {
        status = "";
        detail = "";
        if (!ContractCompatibility.TryReadAssembly(options.HostDeploymentContractPath, out var actual, out var readDetail))
        {
            detail = "contract-" + readDetail;
            return false;
        }
        if (!string.Equals(actual.Name, options.HostContract.Name, StringComparison.OrdinalIgnoreCase))
        {
            detail = "host-contract-name";
            return false;
        }
        if (!string.Equals(actual.Version, options.HostContract.Version, StringComparison.Ordinal))
        {
            detail = "host-contract-version";
            return false;
        }
        if (!Guid.TryParseExact(actual.Mvid, "D", out var mvid) || mvid != options.HostContract.Mvid)
        {
            detail = "host-contract-mvid";
            return false;
        }
        return ContractCompatibility.Check(contentRoot, candidate, options.Target,
            options.HostDeploymentContractPath, require: true, out status, out detail,
            maxSidecarBytes: options.MaxCompatSidecarBytes);
    }

    /// <summary>Required compatibility check as a standalone delegate.</summary>
    public static Func<string, TrustedUpdateCandidate, bool> RequiredCheck(DeliveryOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        options.Validate();
        var target = options.Target;
        var contract = options.HostDeploymentContractPath;
        return (contentRoot, candidate) => Check(options, contentRoot, candidate);
    }
}

