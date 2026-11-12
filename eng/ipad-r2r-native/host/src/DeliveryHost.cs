using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Runtime.Loader;
using RuneCLR.IpadDelivery;
using RuneCLR.TrustedUpdate;

namespace TrustedUpdate;

/// <summary>
/// Host-mode process start for the fixed iPad host. The delivery mode performs an HTTP
/// delivery (or an offline last-known-good restore) and then hands the verified offer to the
/// core recovery selector. Trust inputs are host constants: the pinned public SPKI and the
/// deployment Contract identity read from the Contract assembly that is actually installed.
/// URL, content mapping, release root and receipt root are placement configuration only; they
/// can never lower the signature/compatibility gate.
/// </summary>
public static class DeliveryHost
{
    public const string RuntimeIdentifier = "ios-arm64";
    public const string Architecture = "arm64";

    static string Env(string name, string fallback = "")
    {
        var value = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrEmpty(value) ? fallback : value;
    }

    static bool ReadContractIdentity(string path, out RuntimeContractIdentity identity)
    {
        identity = null;
        try
        {
            using var stream = File.OpenRead(path);
            using var pe = new PEReader(stream);
            MetadataReader md = pe.GetMetadataReader();
            AssemblyDefinition def = md.GetAssemblyDefinition();
            identity = new RuntimeContractIdentity(md.GetString(def.Name), def.Version.ToString(),
                md.GetGuid(md.GetModuleDefinition().Mvid));
            return true;
        }
        catch (Exception)
        {
            return false;
        }
    }

    public static int Run()
    {
        string baseDirectory = AppContext.BaseDirectory;
        string contractPath = Path.Combine(baseDirectory, "TrustedUpdate.Contract.dll");
        if (!ReadContractIdentity(contractPath, out RuntimeContractIdentity hostContract))
        {
            Console.WriteLine("DELIVERY_FAILURE stage=contract-identity path=" + contractPath);
            Console.Out.Flush();
            return 21;
        }

        // iOS exposes Documents under /var, which is itself a symlink to /private/var. The
        // delivery options reject reparse points in the root chain, so prefer the physical path
        // the native host resolved with realpath(3).
        string documents = Env("RUNECLR_DOCUMENTS_PHYSICAL", Env("RUNECLR_DOCUMENTS", baseDirectory));
        string releasesRoot = Env("RUNECLR_DELIVERY_RELEASES", Path.Combine(documents, "releases"));
        string receiptPath = Env("RUNECLR_DELIVERY_RECEIPT", Path.Combine(documents, "state", "recovery-receipt.json"));
        string expected = Env("RUNECLR_EXPECTED_VERSION");
        string mode = Env("RUNECLR_DELIVERY_MODE", "offline");
        string releaseName = Env("RUNECLR_DELIVERY_RELEASE_NAME", expected.Length > 0 ? expected : "release");

        Directory.CreateDirectory(releasesRoot);
        string receiptDirectory = Path.GetDirectoryName(receiptPath);
        if (!string.IsNullOrEmpty(receiptDirectory)) Directory.CreateDirectory(receiptDirectory);

        var options = new DeliveryOptions
        {
            HostSubjectPublicKeyInfo = DeliveryHostKey.PinnedSpki(),
            Target = new TrustedUpdateTarget(RuntimeIdentifier, Architecture),
            HostContract = hostContract,
            HostDeploymentContractPath = contractPath,
            AllowedReleasesRoot = releasesRoot,
            RecoveryReceiptPath = receiptPath,
            FinalReleaseDirectory = Path.Combine(releasesRoot, releaseName),
            RequireRuntimeContractCompatibility = true,
        };
        if (!DeliveryHostKey.SpkiMatchesPin())
        {
            Console.WriteLine("DELIVERY_FAILURE stage=spki-pin");
            Console.Out.Flush();
            return 21;
        }
        options.Validate();
        Console.WriteLine("DELIVERY_BEGIN mode=" + mode + " version=" + expected + " final=" + options.FinalReleaseDirectory + " contract=" +
                          hostContract.Name + "/" + hostContract.Version + "/" + hostContract.CanonicalMvid);
        Console.Out.Flush();

        TrustedReleaseOffer offer = null;
        if (string.Equals(mode, "http", StringComparison.Ordinal))
        {
            string documentUrl = Env("RUNECLR_DELIVERY_DOCUMENT_URL");
            string contentBase = Env("RUNECLR_DELIVERY_CONTENT_BASE");
            string contentList = Env("RUNECLR_DELIVERY_CONTENT");
            if (expected.Length == 0 || documentUrl.Length == 0 || contentBase.Length == 0 || contentList.Length == 0)
            {
                Console.WriteLine("DELIVERY_FAILURE stage=config");
                Console.Out.Flush();
                return 22;
            }

            // A base without a trailing slash would resolve as a sibling file, so force a directory.
            var baseUri = new Uri(contentBase.EndsWith("/", StringComparison.Ordinal) ? contentBase : contentBase + "/", UriKind.Absolute);
            var content = new List<DeliveryContentSource>();
            foreach (string raw in contentList.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                content.Add(new DeliveryContentSource(raw, new Uri(baseUri, raw)));
            var request = new DeliveryOffer
            {
                VersionName = expected,
                DocumentUri = new Uri(documentUrl, UriKind.Absolute),
                Content = content,
            };

            DeliveryResult delivered;
            try
            {
                delivered = IpadDeliveryBridge.DeliverAsync(options, request).AsTask().GetAwaiter().GetResult();
            }
            catch (Exception error)
            {
                Console.WriteLine("DELIVERY_FAILURE stage=deliver type=" + error.GetType().Name);
                Console.Out.Flush();
                return 23;
            }
            Console.WriteLine("DELIVERY_RESULT failure=" + delivered.Failure + " detail=" + delivered.Detail +
                              " compat=" + delivered.CompatStatus + " version=" + delivered.SelectedVersionName);
            Console.Out.Flush();
            if (!delivered.Succeeded || delivered.Offer is null)
                return 24;
            offer = delivered.Offer;
        }
        else if (!string.Equals(mode, "offline", StringComparison.Ordinal))
        {
            Console.WriteLine("DELIVERY_FAILURE stage=mode value=" + mode);
            Console.Out.Flush();
            return 22;
        }

        TrustedReleaseRecoveryStart start;
        try
        {
            start = IpadDeliveryBridge.Start(options, offer, Activate);
        }
        catch (Exception error)
        {
            Console.WriteLine("DELIVERY_FAILURE stage=start type=" + error.GetType().Name);
            Console.Out.Flush();
            return 25;
        }

        Console.WriteLine("DELIVERY_START activated=" + start.Activated + " version=" + start.SelectedVersion +
                          " source=" + start.Source + " value=" + start.Value + " detail=" + start.ConfigurationDetail);
        Console.Out.Flush();
        if (!start.Activated)
        {
            Console.WriteLine("TRUSTED_UPDATE_FAILURE version=" + expected + " failure=" + FailureName(start));
            Console.Out.Flush();
            return 26;
        }

        long managedBytes = GC.GetTotalMemory(false);
        Console.WriteLine("TRUSTED_UPDATE_SUCCESS version=" + (start.SelectedVersion ?? expected) +
                          " result=" + start.Value + " MANAGED_BYTES=" + managedBytes);
        Console.Out.Flush();
        return 0;
    }

    static string FailureName(TrustedReleaseRecoveryStart start)
    {
        if (start.Persistence != TrustedReleasePersistenceFailure.None)
            return "ReceiptNotWritten";
        return "Recovery:" + start.Source;
    }

    // Loads the assembly the selector verified (candidate.AssemblyPath is inside the verified
    // content root) and invokes the entry type/method the signed manifest declared.
    static TrustedUpdateActivation Activate(TrustedUpdateCandidate candidate, TrustedUpdateStartSource source,
        TrustedUpdateFailure candidateFailure)
    {
        Console.WriteLine("DELIVERY_ACTIVATE source=" + source + " version=" + candidate.VersionName +
                          " entry=" + candidate.EntryTypeName + "." + candidate.EntryMethodName +
                          " assembly=" + candidate.AssemblyPath);
        Console.Out.Flush();
        string directory = Path.GetDirectoryName(candidate.AssemblyPath);
        if (string.IsNullOrEmpty(directory) || !File.Exists(candidate.AssemblyPath))
            return new TrustedUpdateActivation(TrustedUpdateFailure.InvalidCandidate, 0);
        try
        {
            var context = new AssemblyLoadContext("trusted-delivery", isCollectible: false);
            context.Resolving += (_, name) =>
            {
                if (string.Equals(name.Name, "TrustedUpdate.Contract", StringComparison.Ordinal))
                {
                    foreach (Assembly shared in AssemblyLoadContext.Default.Assemblies)
                        if (string.Equals(shared.GetName().Name, "TrustedUpdate.Contract", StringComparison.Ordinal))
                            return shared;
                    throw new InvalidOperationException("shared TrustedUpdate.Contract is not loaded in Default");
                }
                foreach (Assembly shared in AssemblyLoadContext.Default.Assemblies)
                    if (string.Equals(shared.GetName().Name, name.Name, StringComparison.Ordinal))
                        return shared;
                string sibling = Path.Combine(directory, name.Name + ".dll");
                return File.Exists(sibling) ? context.LoadFromAssemblyPath(sibling) : null;
            };
            Assembly assembly = context.LoadFromAssemblyPath(candidate.AssemblyPath);
            Type type = assembly.GetType(candidate.EntryTypeName, throwOnError: true);
            object instance = Activator.CreateInstance(type);
            MethodInfo method = type.GetMethod(candidate.EntryMethodName,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static);
            if (method is null) throw new MissingMethodException(candidate.EntryTypeName, candidate.EntryMethodName);

            var scope = new DeliveryScope(new HostApi());
            object[] arguments = BuildArguments(method, scope);
            object returned = method.Invoke(instance, arguments);
            scope.Close();
            int value = returned is int number ? number : 0;
            ReportFixtureReflection(assembly, directory);
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, value);
        }
        catch (Exception error)
        {
            Exception inner = error is TargetInvocationException && error.InnerException is not null
                ? error.InnerException
                : error;
            Console.WriteLine("DELIVERY_ACTIVATION_FAILURE type=" + inner.GetType().Name);
            Console.Out.Flush();
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    static object[] BuildArguments(MethodInfo method, DeliveryScope scope)
    {
        ParameterInfo[] parameters = method.GetParameters();
        if (parameters.Length == 0) return Array.Empty<object>();
        if (parameters.Length == 1) return new object[] { scope };
        if (parameters.Length == 2) return new object[] { scope, scope.CreateCallback() };
        throw new InvalidOperationException("unsupported entry signature");
    }

    // Fixture-only evidence: report the private/helper values the business entry pulled in, so the
    // same result JSON keeps its observed fields. Absent types are not an error.
    static void ReportFixtureReflection(Assembly update, string directory)
    {
        try
        {
            Assembly privateAssembly = LoadSibling(update, directory, "TrustedUpdate.Private.dll");
            if (privateAssembly is null) return;
            Type privateType = privateAssembly.GetType("TrustedUpdate.PrivateBehavior");
            MethodInfo privateMethod = privateType?.GetMethod("Value", BindingFlags.Public | BindingFlags.Static);
            if (privateMethod is null) return;
            int privateValue = (int)privateMethod.Invoke(null, null);

            Assembly helperAssembly = LoadSibling(update, directory, "TrustedUpdate.IlOnlyHelper.dll");
            Type helperType = helperAssembly?.GetType("TrustedUpdate.IlOnlyHelper");
            MethodInfo helperMethod = helperType?.GetMethod("Compute", BindingFlags.Public | BindingFlags.Static);
            if (helperMethod is null) return;
            int helperValue = (int)helperMethod.Invoke(null, new object[] { privateValue });

            Console.WriteLine("HOST_REFLECTION_PRIVATE=" + privateValue + " HOST_REFLECTION_HELPER=" + helperValue);
            Console.Out.Flush();
        }
        catch (Exception error)
        {
            Console.WriteLine("HOST_REFLECTION_SKIPPED type=" + error.GetType().Name);
            Console.Out.Flush();
        }
    }

    static Assembly LoadSibling(Assembly update, string directory, string file)
    {
        string path = Path.Combine(directory, file);
        if (!File.Exists(path)) return null;
        AssemblyLoadContext context = AssemblyLoadContext.GetLoadContext(update);
        return context is null ? null : context.LoadFromAssemblyPath(path);
    }

    sealed class DeliveryScope : IHostApi
    {
        readonly HostApi host;
        bool accepting;

        public DeliveryScope(HostApi host)
        {
            this.host = host;
            accepting = true;
        }

        public void Close() => accepting = false;

        public int Echo(int value)
        {
            if (!accepting) throw new InvalidOperationException("host callback closed");
            return host.Echo(value);
        }

        public Func<int, int> CreateCallback() => value =>
        {
            if (!accepting) throw new InvalidOperationException("host callback closed");
            Console.WriteLine("HOST_DELEGATE=" + value);
            return value + 2;
        };
    }
}