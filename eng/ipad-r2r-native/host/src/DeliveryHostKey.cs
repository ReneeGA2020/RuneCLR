using System;
using System.Security.Cryptography;

namespace TrustedUpdate;

/// <summary>
/// Host-pinned delivery trust anchor: a P-256 SubjectPublicKeyInfo (PUBLIC key only).
/// Generated once on the build Mac for test builds; see docs/DELIVERY.md for provenance and
/// the sealing recipe. The private key never enters this repository, the package, the
/// device, or any log.
/// </summary>
public static class DeliveryHostKey
{
    public const string PinnedSpkiBase64 = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEpzwSXIQSZ5Zq3yWoIgIVSzeMeoxnTGoAVGD3T1WMpoZxz86JTXc0PLZPG6Pxg2L1tg9FzAVJhCkO8WUI5ygpBg==";

    /// <summary>sha256 of the DER SPKI above, so an accidental edit is caught at startup.</summary>
    public const string PinnedSpkiSha256 = "936c3bbc98b7725b467deb1e18380d49ccb9caf088709b9a0a4ab781c759c732";

    public static byte[] PinnedSpki() => Convert.FromBase64String(PinnedSpkiBase64);

    public static bool SpkiMatchesPin()
    {
        byte[] bytes = PinnedSpki();
        return string.Equals(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            PinnedSpkiSha256, StringComparison.Ordinal);
    }
}