using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using RuneCLR.TrustedUpdate;

return Run(args);

static int Run(string[] args)
{
    if (args.Length == 0 || args.Contains("--help", StringComparer.Ordinal))
        return Usage();

    var values = new Dictionary<string, string>(StringComparer.Ordinal);
    for (var i = 0; i < args.Length; i += 2)
    {
        if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal))
            return Usage();
        values[args[i]] = args[i + 1];
    }

    if (!values.TryGetValue("--module", out var moduleText)
        || !values.TryGetValue("--version", out var version)
        || !values.TryGetValue("--entry-type", out var entryType)
        || !values.TryGetValue("--signed", out var signedPathText)
        || !values.TryGetValue("--spki", out var spkiPathText)
        || !values.TryGetValue("--private-key", out var privateKeyPathText))
        return Usage();

    var entryMethod = values.GetValueOrDefault("--entry-method", "Entry");
    var runtime = values.GetValueOrDefault("--runtime", "net11.0");
    var architecture = values.GetValueOrDefault("--architecture", HostArchitecture());

    try
    {
        var modulePath = Path.GetFullPath(moduleText);
        if (!File.Exists(modulePath))
        {
            Console.Error.WriteLine("PUBLISHER FAILED module-missing");
            return 2;
        }
        var contentRoot = Path.GetFullPath(values.GetValueOrDefault("--content-root", Path.GetDirectoryName(modulePath)!));
        if (!Directory.Exists(contentRoot))
        {
            Console.Error.WriteLine("PUBLISHER FAILED content-root-missing");
            return 2;
        }

        var relative = Path.GetRelativePath(contentRoot, modulePath).Replace('\\', '/');
        if (relative == ".." || relative.StartsWith("../", StringComparison.Ordinal) || Path.IsPathRooted(relative))
        {
            Console.Error.WriteLine("PUBLISHER FAILED module-outside-content-root");
            return 2;
        }

        var signedPath = Path.GetFullPath(signedPathText);
        var spkiPath = Path.GetFullPath(spkiPathText);
        var privateKeyPath = Path.GetFullPath(privateKeyPathText);
        if (!Outside(contentRoot, signedPath) || !Outside(contentRoot, spkiPath) || !Outside(contentRoot, privateKeyPath))
        {
            Console.Error.WriteLine("PUBLISHER FAILED output-inside-release-content-root");
            return 2;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(signedPath)!);
        Directory.CreateDirectory(Path.GetDirectoryName(spkiPath)!);
        Directory.CreateDirectory(Path.GetDirectoryName(privateKeyPath)!);

        ECDsa key;
        var generated = false;
        if (File.Exists(privateKeyPath))
        {
            key = ECDsa.Create();
            key.ImportFromPem(File.ReadAllText(privateKeyPath, Encoding.UTF8));
        }
        else
        {
            key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            File.WriteAllText(privateKeyPath, key.ExportPkcs8PrivateKeyPem(), new UTF8Encoding(false));
            generated = true;
        }

        using (key)
        {
            var spki = key.ExportSubjectPublicKeyInfo();
            if (spki.Length != TrustedRelease.SpkiBytes)
            {
                Console.Error.WriteLine("PUBLISHER FAILED spki-size");
                return 3;
            }
            if (File.Exists(spkiPath))
            {
                if (!File.ReadAllBytes(spkiPath).AsSpan().SequenceEqual(spki))
                {
                    Console.Error.WriteLine("PUBLISHER FAILED spki-key-mismatch");
                    return 3;
                }
            }
            else
            {
                File.WriteAllBytes(spkiPath, spki);
            }

            var identity = new TrustedReleaseIdentity(
                version, runtime, architecture, entryType, entryMethod, relative);
            var signed = TrustedRelease.Sign(contentRoot, identity, new[] { relative }, key);
            if (!signed.Succeeded || signed.Document is null)
            {
                Console.Error.WriteLine("PUBLISHER FAILED " + signed.Failure + "/" + signed.Detail);
                return 3;
            }

            File.WriteAllBytes(signedPath, signed.Document);
            Console.WriteLine("PUBLISHER OK version=" + version
                + " entryType=" + entryType
                + " entryMethod=" + entryMethod
                + " entryPath=" + relative
                + " moduleSha256=" + Hash(modulePath)
                + " signed=" + signedPath
                + " signedSha256=" + Hash(signedPath)
                + " spki=" + spkiPath
                + " spkiSha256=" + Hash(spkiPath)
                + " privateKey=" + privateKeyPath
                + " keyGenerated=" + generated);
            return 0;
        }
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("PUBLISHER FAILED " + error.GetType().Name + ": " + error.Message);
        return 3;
    }
}

static bool Outside(string root, string path)
{
    var relative = Path.GetRelativePath(root, path);
    var parent = ".." + Path.DirectorySeparatorChar;
    return relative == ".."
        || relative.StartsWith(parent, StringComparison.Ordinal)
        || relative.StartsWith("../", StringComparison.Ordinal)
        || Path.IsPathRooted(relative);
}

static string Hash(string path) =>
    Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

static string HostArchitecture() => RuntimeInformation.ProcessArchitecture switch
{
    Architecture.X64 => "x64",
    Architecture.X86 => "x86",
    Architecture.Arm64 => "arm64",
    Architecture.Arm => "arm",
    _ => "unknown",
};

static int Usage()
{
    Console.Error.WriteLine("usage: TrustedGame.Publisher --module <module.dll> --version <version> --entry-type <type> --signed <release.signed.json> --spki <host.spki> --private-key <publisher.pem> [--content-root <dir>] [--entry-method Entry] [--runtime net11.0] [--architecture <native-arch>]");
    return 2;
}
