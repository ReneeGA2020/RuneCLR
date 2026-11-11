using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.TrustedUpdate;

/// <summary>
/// Optional signed compatibility description. The sidecar is one file inside the
/// signed file set, so <see cref="TrustedRelease.Verify"/> authenticates it; the
/// envelope schema is unchanged. Only a sidecar that appears in the verified
/// candidate's additional content is considered. An unlisted file that merely sits
/// on disk is never treated as authenticated compatibility.
///
/// Legacy callers run unchecked. The integrated download flow and the device host
/// run required, where a missing or invalid sidecar rejects the offer before
/// <c>TryStartHostLoaded</c>: no process gate, no author activation.
/// </summary>
static class ContractCompatibility
{
    public const string SidecarName = "runeclr.compat.json";
    public const string Schema = "runeclr.compat.v1";

    public readonly record struct AssemblyIdentity(string Name, string Version, string Mvid);

    public static bool Required()
    {
        var configured = Environment.GetEnvironmentVariable("RUNECLR_COMPAT_REQUIRED");
        return configured is "1" or "true" or "TRUE";
    }

    public static bool TryReadAssembly(string path, out AssemblyIdentity identity, out string detail)
    {
        identity = default;
        detail = "";
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            using var pe = new PEReader(stream);
            if (!pe.HasMetadata)
            {
                detail = "no-metadata";
                return false;
            }

            var metadata = pe.GetMetadataReader();
            if (!metadata.IsAssembly)
            {
                detail = "not-assembly";
                return false;
            }

            var definition = metadata.GetAssemblyDefinition();
            var module = metadata.GetModuleDefinition();
            identity = new AssemblyIdentity(
                metadata.GetString(definition.Name),
                definition.Version.ToString(),
                metadata.GetGuid(module.Mvid).ToString("D"));
            return true;
        }
        catch (Exception ex) when (ex is IOException or BadImageFormatException or UnauthorizedAccessException or ArgumentException)
        {
            detail = ex.GetType().Name;
            return false;
        }
    }

    /// <summary>
    /// Checks the verified offer. <paramref name="candidate"/> must come from
    /// <see cref="TrustedRelease.Verify"/> for the same content root. Status is
    /// "checked", "sidecar-absent" (legacy unchecked) or "rejected".
    /// </summary>
    public static bool Check(
        string contentRoot,
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget target,
        string deploymentContractPath,
        bool require,
        out string status,
        out string detail)
    {
        status = "";
        detail = "";

        var matches = (candidate.AdditionalContent ?? Array.Empty<TrustedUpdateContentFile>())
            .Where(file => string.Equals(Path.GetFileName(file.Path), SidecarName, StringComparison.Ordinal))
            .ToArray();
        if (matches.Length == 0)
        {
            status = "sidecar-absent";
            detail = require ? "sidecar-missing" : "unchecked";
            return !require;
        }

        if (matches.Length > 1)
        {
            status = "rejected";
            detail = "sidecar-duplicate";
            return false;
        }

        var sidecar = matches[0];
        if (!IsInside(contentRoot, sidecar.Path))
        {
            status = "rejected";
            detail = "sidecar-outside-root";
            return false;
        }

        byte[] bytes;
        try
        {
            bytes = File.ReadAllBytes(sidecar.Path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            status = "rejected";
            detail = "sidecar-" + ex.GetType().Name;
            return false;
        }

        // One read: the same buffer that is hashed is the one that is parsed.
        var actualHash = Convert.ToHexStringLower(SHA256.HashData(bytes));
        if (!string.Equals(actualHash, sidecar.ContentSha256, StringComparison.OrdinalIgnoreCase))
        {
            status = "rejected";
            detail = "sidecar-hash";
            return false;
        }

        JsonDocument parsed;
        try
        {
            parsed = JsonDocument.Parse(bytes);
        }
        catch (JsonException)
        {
            status = "rejected";
            detail = "sidecar-json";
            return false;
        }

        using (parsed)
        {
            var root = parsed.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                status = "rejected";
                detail = "sidecar-shape";
                return false;
            }

            if (!string.Equals(Text(root, "schema"), Schema, StringComparison.Ordinal))
            {
                status = "rejected";
                detail = "sidecar-schema";
                return false;
            }

            var runtime = Text(root, "runtime");
            var architecture = Text(root, "architecture");
            if (runtime.Length == 0 || architecture.Length == 0)
            {
                status = "rejected";
                detail = "sidecar-target-missing";
                return false;
            }

            if (!string.Equals(runtime, target.Runtime, StringComparison.Ordinal)
                || !string.Equals(architecture, target.Architecture, StringComparison.Ordinal))
            {
                status = "rejected";
                detail = "target-mismatch";
                return false;
            }

            if (!root.TryGetProperty("contract", out var contract) || contract.ValueKind != JsonValueKind.Object)
            {
                status = "rejected";
                detail = "contract-missing";
                return false;
            }

            var name = Text(contract, "name");
            var version = Text(contract, "version");
            var mvid = Text(contract, "mvid");
            if (name.Length == 0 || version.Length == 0 || mvid.Length == 0)
            {
                status = "rejected";
                detail = "contract-field-missing";
                return false;
            }

            if (!TryParseCanonicalMvid(mvid, out var sidecarMvid))
            {
                status = "rejected";
                detail = "contract-mvid-format";
                return false;
            }

            if (!TryReadAssembly(deploymentContractPath, out var actual, out var assemblyDetail))
            {
                status = "rejected";
                detail = "contract-" + assemblyDetail;
                return false;
            }

            if (!string.Equals(name, actual.Name, StringComparison.OrdinalIgnoreCase))
            {
                status = "rejected";
                detail = "contract-name";
                return false;
            }

            if (!string.Equals(version, actual.Version, StringComparison.Ordinal))
            {
                status = "rejected";
                detail = "contract-version";
                return false;
            }

            if (!Guid.TryParseExact(actual.Mvid, "D", out var deploymentMvid) || sidecarMvid != deploymentMvid)
            {
                status = "rejected";
                detail = "contract-mvid";
                return false;
            }

            status = "checked";
            detail = "match";
            return true;
        }
    }

    public static string ContractFile()
    {
        var configured = Environment.GetEnvironmentVariable("RUNECLR_CONTRACT_FILE");
        return string.IsNullOrEmpty(configured) ? "TrustedComposition.Contract.dll" : configured;
    }

    public static string DeploymentContractPath() => Path.Combine(AppContext.BaseDirectory, ContractFile());

    /// <summary>
    /// The sidecar text is a standard Guid: canonical "D" (8-4-4-4-12) or canonical
    /// "N" (32 hex). Other Guid formats (braces, parentheses, hex pairs) and raw
    /// metadata-heap byte strings are not accepted. The comparison is by Guid value,
    /// never by raw text, so a little-endian heap dump cannot accidentally match.
    /// </summary>
    static bool TryParseCanonicalMvid(string text, out Guid value)
    {
        value = default;
        if (text.Length == 36)
            return Guid.TryParseExact(text, "D", out value);
        if (text.Length == 32)
            return Guid.TryParseExact(text, "N", out value);
        return false;
    }

    static string Text(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? ""
            : "";

    static bool IsInside(string root, string path)
    {
        string fullRoot;
        string fullPath;
        try
        {
            fullRoot = Path.GetFullPath(root);
            fullPath = Path.GetFullPath(path);
        }
        catch (Exception ex) when (ex is IOException or ArgumentException or NotSupportedException)
        {
            return false;
        }

        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var prefix = fullRoot.EndsWith(Path.DirectorySeparatorChar) ? fullRoot : fullRoot + Path.DirectorySeparatorChar;
        return fullPath.StartsWith(prefix, comparison);
    }

}
