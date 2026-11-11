using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using RuneCLR.IpadDelivery;
using RuneCLR.TrustedUpdate;

/// <summary>
/// Desktop sealer for one signed release directory. Runs AFTER native owner signing so the
/// payload list and envelope are computed from the final bytes.
///
///   seal --content DIR --version V --runtime ios-arm64 --architecture arm64
///        --entry-type T --entry-method M --entry-path P
///        --files a.dll,b.dll --contract PATH/TrustedUpdate.Contract.dll --key PEM
///
/// The private key is read from a file path the operator supplies, used once and never logged.
/// </summary>
static class Program
{
    static int Main(string[] args)
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal) || i + 1 >= args.Length)
            {
                Console.Error.WriteLine("seal: bad arguments");
                return 2;
            }
            map[args[i].Substring(2)] = args[++i];
        }
        foreach (var required in new[] { "content", "version", "runtime", "architecture", "entry-type", "entry-method", "entry-path", "files", "contract", "key" })
            if (!map.ContainsKey(required))
            {
                Console.Error.WriteLine("seal: missing --" + required);
                return 2;
            }

        var files = new List<string>();
        foreach (var raw in map["files"].Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            files.Add(raw);

        if (!File.Exists(map["key"]))
        {
            Console.Error.WriteLine("seal: private key not found");
            return 3;
        }
        if (!File.Exists(map["contract"]))
        {
            Console.Error.WriteLine("seal: contract not found");
            return 3;
        }

        RuntimeContractIdentity contract;
        using (var stream = File.OpenRead(map["contract"]))
        using (var pe = new PEReader(stream))
        {
            MetadataReader md = pe.GetMetadataReader();
            AssemblyDefinition def = md.GetAssemblyDefinition();
            contract = new RuntimeContractIdentity(md.GetString(def.Name), def.Version.ToString(),
                md.GetGuid(md.GetModuleDefinition().Mvid));
        }

        var identity = new TrustedReleaseIdentity(map["version"], map["runtime"], map["architecture"],
            map["entry-type"], map["entry-method"], map["entry-path"]);
        var target = new TrustedUpdateTarget(map["runtime"], map["architecture"]);

        try
        {
            using var key = ECDsa.Create();
            key.ImportFromPem(File.ReadAllText(map["key"]));
            SealedPackage sealedPackage = PackageSealer.Seal(map["content"], identity, files, contract, target, key);
            Console.WriteLine("SEALED root=" + sealedPackage.ContentRoot);
            Console.WriteLine("SEALED document=" + sealedPackage.DocumentPath);
            Console.WriteLine("SEALED sidecar=" + sealedPackage.SidecarPath);
            Console.WriteLine("SEALED payloadList=" + sealedPackage.PayloadListPath);
            foreach (var file in sealedPackage.Files) Console.WriteLine("SEALED file=" + file);
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("seal: " + error.GetType().Name + ": " + error.Message);
            return 4;
        }
    }
}