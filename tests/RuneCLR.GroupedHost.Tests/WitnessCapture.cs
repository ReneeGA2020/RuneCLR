using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Security.Cryptography;

namespace RuneCLR.GroupedHost.Tests;

/// <summary>Byte-derived identity of one staged role image (read without loading anything).</summary>
internal readonly record struct WitnessImage(string SimpleName, string FullName, string Sha256, string Mvid, int Bytes);

/// <summary>
/// Loaded-image identity copied to scalars. The capture helpers are NoInlining so the metadata objects
/// (Assembly/Type/MethodInfo/ALC) die with the helper frame and never enter a retained record.
/// </summary>
internal readonly record struct WitnessGroupIdentity(
    string SimpleName,
    string FullName,
    string Mvid,
    string AlcName,
    int MethodToken,
    long MethodHandle,
    string DeclaredEntry,
    string EntrySignature);

internal static class WitnessCapture
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static WitnessImage ReadImage(byte[] bytes)
    {
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        var metadata = pe.GetMetadataReader();
        var definition = metadata.GetAssemblyDefinition();
        var name = metadata.GetString(definition.Name);
        var fullName = definition.GetAssemblyName().FullName ?? name;
        var mvid = metadata.GetGuid(metadata.GetModuleDefinition().Mvid).ToString("D");
        var sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        return new WitnessImage(name, fullName, sha, mvid, bytes.Length);
    }

    /// <summary>
    /// Exact MethodDef token of one method in the staged image bytes. Used as the byte-side truth for
    /// the loaded-method token comparison; nothing is loaded or invoked.
    /// </summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int FindMethodToken(byte[] bytes, string typeName, string methodName)
    {
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        var metadata = pe.GetMetadataReader();
        foreach (var typeHandle in metadata.TypeDefinitions)
        {
            var type = metadata.GetTypeDefinition(typeHandle);
            var namespaceName = metadata.GetString(type.Namespace);
            var typeNameOnly = metadata.GetString(type.Name);
            var qualified = namespaceName.Length == 0 ? typeNameOnly : namespaceName + "." + typeNameOnly;
            if (!string.Equals(qualified, typeName, StringComparison.Ordinal)) continue;
            foreach (var methodHandle in type.GetMethods())
            {
                var method = metadata.GetMethodDefinition(methodHandle);
                if (string.Equals(metadata.GetString(method.Name), methodName, StringComparison.Ordinal))
                    return MetadataTokens.GetToken(methodHandle);
            }
        }
        return 0;
    }

    /// <summary>
    /// Copies one explicitly requested method's identity from the loaded group assembly. nonPublic=true
    /// is only for host metadata reads of documented fixture members (the author callback); nothing is
    /// invoked and no MethodInfo/Type/Assembly/ALC leaves this frame.
    /// </summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static WitnessGroupIdentity? CaptureMethod(string rolePrefix, HashSet<AssemblyLoadContext> known,
        string assemblySimpleName, string typeName, string methodName, bool nonPublic)
    {
        var flags = BindingFlags.Static | (nonPublic ? BindingFlags.NonPublic : BindingFlags.Public);
        foreach (var context in AssemblyLoadContext.All)
        {
            if (known.Contains(context)) continue;
            if (context.Name is null || !context.Name.StartsWith(rolePrefix, StringComparison.Ordinal)) continue;
            var assembly = context.Assemblies.FirstOrDefault(candidate =>
                string.Equals(candidate.GetName().Name, assemblySimpleName, StringComparison.Ordinal));
            if (assembly is null) continue;
            var type = assembly.GetType(typeName, throwOnError: false);
            var method = type?.GetMethod(methodName, flags);
            if (type is null || method is null) continue;
            var declared = (type.FullName ?? type.Name) + "." + method.Name;
            var policy = ReadContextPolicy(context);
            Console.WriteLine("witness-context-policy alc=" + context.Name + " method=" + declared + " policy=" + (policy is null ? "unavailable" : policy.Value.ToString()));
            return new WitnessGroupIdentity(
                assemblySimpleName,
                assembly.GetName().FullName ?? string.Empty,
                assembly.ManifestModule.ModuleVersionId.ToString("D"),
                context.Name,
                method.MetadataToken,
                method.MethodHandle.Value.ToInt64(),
                (type.FullName ?? type.Name) + "." + method.Name,
                method.ToString() ?? string.Empty);
        }
        return null;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int? ReadContextPolicy(AssemblyLoadContext context)
    {
        try
        {
            var getter = typeof(AssemblyLoadContext).GetMethod(
                "RuneCLR_GetExecutionPolicy", BindingFlags.Instance | BindingFlags.NonPublic);
            if (getter is null) return null;
            return (int)getter.Invoke(context, null)!;
        }
        catch
        {
            return null;
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void PlantControlRoot(string rolePrefix, HashSet<AssemblyLoadContext> known,
        string assemblySimpleName, string entryType, string entryMethod)
    {
        foreach (var context in AssemblyLoadContext.All)
        {
            if (known.Contains(context)) continue;
            if (context.Name is null || !context.Name.StartsWith(rolePrefix, StringComparison.Ordinal)) continue;
            var assembly = context.Assemblies.FirstOrDefault(candidate =>
                string.Equals(candidate.GetName().Name, assemblySimpleName, StringComparison.Ordinal));
            var type = assembly?.GetType(entryType, throwOnError: false);
            var method = type?.GetMethod(entryMethod, BindingFlags.Public | BindingFlags.Static);
            if (method is null) continue;
            WitnessControlRoot.Root = method;
            return;
        }
    }
}
