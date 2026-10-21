using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using RuneCLR.Experiments;
using RuneCLR.TrustedUpdate;
using TrustedComposition.Contract;

sealed class DeliveryFacts
{
    public bool Activated;
    public string Version = "";
    public string Source = "";
    public int Value;
    public int PrivateValue;
    public int HelperValue;
    public int TouchValue;
    public int InterfaceValue;
    public int DelegateValue;
    public int GenericValue;
    public int StaticCount;
    public int PrivateCount;
    public string PrivateVersion = "";
    public bool Identity;
    public int Calls;
    public string Detail = "";
    public string Stage = "";
    public string Candidate = "";
    public string Recovery = "";
    public string Persist = "";
    public string Entry = "";
    public string ListedPrivate = "";
    public string ListedHelper = "";
    public string LoadedEntry = "";
    public string LoadedPrivate = "";
    public string LoadedHelper = "";
    public bool HelperLoaded;
    public int Witnesses;
}

static class DeliverySession
{
    public static int TotalActivations { get; private set; }
    public static TypedSession<IUpdateModule>? LogicalSession { get; private set; }
    public static DeliveryHostObject? LogicalHost { get; private set; }

    public static void CloseLogical()
    {
        LogicalSession?.Close();
        LogicalHost = null;
    }

    public static SessionCall InvokeLogical(Func<IUpdateModule, int> call)
    {
        var session = LogicalSession;
        if (session is null)
            return new SessionCall(false, 0, "closed");
        var result = session.Invoke(call);
        if (session.IsClosed)
            LogicalHost = null;
        return result;
    }

    public static TrustedUpdateTarget Target { get; } = new("net11.0", HostArchitecture());

    public static async Task<DeliveryFacts> StageAsync(
        string releasesRoot,
        string finalDirectory,
        string documentPath,
        string spkiPath,
        string receiptPath,
        IReadOnlyList<(string Relative, string Absolute)> files,
        bool fail)
    {
        var facts = new DeliveryFacts();
        if (!TryReadBounded(spkiPath, TrustedRelease.SpkiBytes, exact: true, out var spki, out var spkiDetail))
        {
            facts.Detail = spkiDetail;
            facts.Stage = "InvalidRequest/" + spkiDetail + "/None";
            return facts;
        }

        if (!TryReadBounded(documentPath, TrustedRelease.MaxDocumentBytes, exact: false, out var document, out var documentDetail))
        {
            facts.Stage = "InvalidRequest/" + documentDetail + "/None";
            return Recover(releasesRoot, null, null, spki, receiptPath, fail, facts);
        }

        if (files.Count == 0)
        {
            facts.Stage = "InvalidRequest/files/None";
            return Recover(releasesRoot, null, null, spki, receiptPath, fail, facts);
        }

        var sources = files.Select(file => new TrustedReleaseStageSource(
            file.Relative,
            _ => new ValueTask<Stream>(File.OpenRead(file.Absolute)))).ToArray();
        var staged = await TrustedReleaseStaging.PublishAsync(finalDirectory, document, spki, sources);
        facts.Stage = staged.Failure + "/" + staged.Detail + "/" + staged.VerificationFailure;
        if (!staged.Succeeded || string.IsNullOrEmpty(staged.FinalDirectory))
            return Recover(releasesRoot, null, null, spki, receiptPath, fail, facts);
        return Recover(releasesRoot, staged.FinalDirectory, document, spki, receiptPath, fail, facts);
    }

    public static DeliveryFacts ActivateStaged(string releasesRoot, string finalDirectory, string documentPath, string spkiPath, string receiptPath, bool fail)
    {
        var facts = new DeliveryFacts();
        if (!TryReadBounded(spkiPath, TrustedRelease.SpkiBytes, exact: true, out var spki, out var spkiDetail))
        {
            facts.Detail = spkiDetail;
            facts.Stage = "InvalidRequest/" + spkiDetail + "/None";
            return facts;
        }

        if (!TryReadBounded(documentPath, TrustedRelease.MaxDocumentBytes, exact: false, out var document, out var documentDetail))
        {
            facts.Stage = "InvalidRequest/" + documentDetail + "/None";
            return Recover(releasesRoot, null, null, spki, receiptPath, fail, facts);
        }

        facts.Stage = "None//None";
        return Recover(releasesRoot, finalDirectory, document, spki, receiptPath, fail, facts);
    }

    public static DeliveryFacts RecoverOnly(string releasesRoot, string spkiPath, string receiptPath, bool fail)
    {
        var facts = new DeliveryFacts();
        if (!TryReadBounded(spkiPath, TrustedRelease.SpkiBytes, exact: true, out var spki, out var spkiDetail))
        {
            facts.Detail = spkiDetail;
            facts.Stage = "InvalidRequest/" + spkiDetail + "/None";
            return facts;
        }

        return Recover(releasesRoot, null, null, spki, receiptPath, fail, facts);
    }

    static bool TryReadBounded(string path, int maxBytes, bool exact, out byte[] bytes, out string detail)
    {
        bytes = [];
        detail = "io";
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            var buffer = new byte[maxBytes + 1];
            var filled = 0;
            while (filled < buffer.Length)
            {
                var read = stream.Read(buffer, filled, buffer.Length - filled);
                if (read == 0)
                    break;
                filled += read;
            }

            if (exact)
            {
                if (filled != maxBytes)
                {
                    detail = "spki";
                    return false;
                }
            }
            else if (filled == 0 || filled > maxBytes)
            {
                detail = "document-size";
                return false;
            }

            bytes = buffer[..filled];
            detail = "";
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            detail = "io";
            return false;
        }
    }

    static DeliveryFacts Recover(
        string releasesRoot,
        string? offerRoot,
        byte[]? document,
        byte[] spki,
        string receiptPath,
        bool fail,
        DeliveryFacts facts)
    {
        TrustedReleaseOffer? offer = offerRoot is null || document is null
            ? null
            : new TrustedReleaseOffer(offerRoot, document);
        var result = TrustedReleaseRecovery.TryStart(offer, spki, Target, releasesRoot, receiptPath, (candidate, source, _) =>
            Activate(candidate, source, fail, facts));
        facts.Activated = result.Activated;
        facts.Version = result.SelectedVersion ?? "";
        if (result.Source != TrustedUpdateStartSource.None || facts.Calls == 0)
            facts.Source = result.Source.ToString();
        facts.Value = result.Value;
        facts.Candidate = result.Candidate.Verification + "/" + result.Candidate.Plan + "/" + result.Candidate.Activation + "/" + result.Candidate.Detail;
        facts.Recovery = result.Recovery.Verification + "/" + result.Recovery.Plan + "/" + result.Recovery.Activation + "/" + result.Recovery.Detail;
        facts.Persist = result.Persistence + "/" + result.PersistenceDetail;
        if (!string.IsNullOrEmpty(result.ConfigurationDetail) && string.IsNullOrEmpty(facts.Detail))
            facts.Detail = result.ConfigurationDetail;
        return facts;
    }

    static TrustedUpdateActivation Activate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateStartSource source,
        bool fail,
        DeliveryFacts facts)
    {
        TotalActivations++;
        facts.Calls++;
        facts.Source = source.ToString();
        facts.Entry = candidate.AssemblyPath;
        if (!TryInventory(candidate, out var listed, out var inventoryDetail))
        {
            facts.Detail = inventoryDetail;
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }

        facts.ListedPrivate = FindListed(listed, "TrustedComposition.Private");
        facts.ListedHelper = FindListed(listed, "TrustedComposition.IlOnlyHelper");
        var context = new ListedContext(listed);
        try
        {
            var assembly = context.LoadFromAssemblyPath(candidate.AssemblyPath);
            var type = assembly.GetType("TrustedComposition.UpdateModule", throwOnError: true)!;
            var module = (IUpdateModule)Activator.CreateInstance(type)!;
            var host = new DeliveryHostObject();
            var session = new TypedSession<IUpdateModule>(module);
            UpdateOutcome? outcome = null;
            Exception? loadError = null;
            var call = session.Invoke(candidate =>
            {
                try
                {
                    outcome = candidate.Execute(host, fail);
                    return outcome.PrivateValue;
                }
                catch (Exception error) when (error.GetType().FullName != "TrustedComposition.UpdateFailureException")
                {
                    loadError = error;
                    return 0;
                }
            });
            if (loadError is not null)
            {
                session.Close();
                LogicalSession = null;
                LogicalHost = null;
                throw loadError;
            }
            if (call.Failure == "author-failed")
            {
                LogicalSession = session;
                LogicalHost = null;
                NoteLoads(context, facts);
                DrainWitnesses(facts);
                facts.Detail = "author-failed";
                ObserveHelper(context, facts, authorFailed: true);
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            }

            if (!call.Completed || outcome is null)
            {
                LogicalSession = null;
                LogicalHost = null;
                facts.Detail = call.Failure.Length == 0 ? "activation-failed" : call.Failure;
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            }

            facts.PrivateValue = outcome.PrivateValue;
            facts.HelperValue = outcome.HelperValue;
            facts.TouchValue = outcome.TouchValue;
            facts.InterfaceValue = outcome.InterfaceValue;
            facts.DelegateValue = outcome.DelegateValue;
            facts.GenericValue = outcome.GenericValue;
            facts.StaticCount = outcome.StaticCount;
            facts.PrivateCount = outcome.PrivateCount;
            facts.PrivateVersion = outcome.PrivateVersion;
            facts.Identity = ReferenceEquals(host, outcome.ReturnedHost) && ReferenceEquals(host, outcome.GenericHost);
            NoteLoads(context, facts);
            DrainWitnesses(facts);
            facts.Detail = "executed";
            ObserveHelper(context, facts, authorFailed: false);
            LogicalSession = session;
            LogicalHost = host;
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, outcome.PrivateValue);
        }
        catch (Exception error)
        {
            NoteLoads(context, facts);
            DrainWitnesses(facts);
            if (!facts.HelperLoaded && string.IsNullOrEmpty(facts.ListedHelper) && facts.LoadedEntry.Length > 0)
                facts.Detail = "helper-not-listed";
            else if (string.IsNullOrEmpty(facts.Detail) && HasUnlistedLoad(error))
                facts.Detail = "unlisted-assembly";
            else if (string.IsNullOrEmpty(facts.Detail))
                facts.Detail = "activation-failed";
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    internal static bool TryInventory(TrustedUpdateCandidate candidate, out Dictionary<string, string> listed, out string detail)
    {
        listed = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        detail = "";
        var paths = new List<string> { candidate.AssemblyPath };
        if (candidate.AdditionalContent is not null)
        {
            foreach (var file in candidate.AdditionalContent)
                paths.Add(file.Path);
        }

        foreach (var path in paths)
        {
            AssemblyName actual;
            try
            {
                actual = AssemblyName.GetAssemblyName(path);
            }
            catch (Exception ex) when (ex is BadImageFormatException or IOException or ArgumentException or UnauthorizedAccessException or NotSupportedException)
            {
                detail = "assembly-identity";
                return false;
            }

            if (string.IsNullOrWhiteSpace(actual.Name))
            {
                detail = "assembly-identity";
                return false;
            }

            if (!listed.TryAdd(actual.Name, Path.GetFullPath(path)))
            {
                detail = "duplicate-assembly";
                return false;
            }
        }

        return true;
    }

    static bool HasUnlistedLoad(Exception error)
    {
        for (var current = error; current is not null; current = current.InnerException)
        {
            if (current is FileNotFoundException or FileLoadException)
                return true;
        }

        return false;
    }

    static string FindListed(Dictionary<string, string> listed, string name) =>
        listed.TryGetValue(name, out var path) ? path : "";

    static void NoteLoads(ListedContext context, DeliveryFacts facts)
    {
        foreach (var assembly in context.Assemblies)
        {
            var name = assembly.GetName().Name;
            var location = assembly.Location;
            if (name == "TrustedComposition.Update.A" || name == "TrustedComposition.Update.B")
                facts.LoadedEntry = location;
            else if (name == "TrustedComposition.Private")
                facts.LoadedPrivate = location;
            else if (name == "TrustedComposition.IlOnlyHelper")
            {
                facts.LoadedHelper = location;
                facts.HelperLoaded = true;
            }
        }
    }

    static void DrainWitnesses(DeliveryFacts facts)
    {
        foreach (var item in ExecutionWitness.Drain())
        {
            facts.Witnesses++;
            Console.WriteLine("WITNESS " + JsonSerializer.Serialize(item));
        }
    }

    static void ObserveHelper(ListedContext context, DeliveryFacts facts, bool authorFailed)
    {
        if (!facts.HelperLoaded || Environment.GetEnvironmentVariable("RUNECLR_POST_EXECUTION_PRECODE") != "1")
            return;
        if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
            return;
        var expect = Environment.GetEnvironmentVariable("RUNECLR_DELIVERY_EXPECT_HELPER_INTERPRETED");
        if (expect is not ("0" or "1"))
        {
            Console.WriteLine("ENTRYOBSERVATION {\"Error\":\"expect\"}");
            return;
        }

        Assembly? helper = null;
        foreach (var assembly in context.Assemblies)
        {
            if (assembly.GetName().Name == "TrustedComposition.IlOnlyHelper")
            {
                helper = assembly;
                break;
            }
        }

        var method = helper?.GetType("TrustedComposition.IlOnlyHelper")?.GetMethod("Compute");
        if (method is null)
            return;
        var evidence = authorFailed
            ? "Execute threw expected author exception after helper"
            : "Execute returned checked helper result " + facts.HelperValue;
        try
        {
            var entry = WindowsEntryObservation.Capture(method, expect == "1", evidence);
            Console.WriteLine("ENTRYOBSERVATION " + JsonSerializer.Serialize(new EntryObservationLine(facts.LoadedHelper, entry)));
        }
        catch (InvalidOperationException)
        {
            Console.WriteLine("ENTRYOBSERVATION {\"Error\":\"precode\"}");
        }
    }

    static string HostArchitecture() => RuntimeInformation.ProcessArchitecture switch
    {
        Architecture.X64 => "x64",
        Architecture.Arm64 => "arm64",
        Architecture.X86 => "x86",
        _ => RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
    };
}

sealed record EntryObservationLine(string AssemblyPath, EntryObservation Entry);

sealed class ListedContext : AssemblyLoadContext
{
    static readonly FrameworkShare Framework = FrameworkShare.Create();
    readonly Dictionary<string, string> listed;
    readonly Assembly contract;

    public ListedContext(Dictionary<string, string> listed, Assembly? sharedContract = null)
        : base("trusted-composition-delivery", isCollectible: false)
    {
        this.listed = listed;
        contract = sharedContract ?? typeof(IUpdateModule).Assembly;
    }

    protected override Assembly? Load(AssemblyName name)
    {
        if (string.IsNullOrWhiteSpace(name.Name))
            throw new FileLoadException("assembly-identity");
        if (name.Name.Equals(contract.GetName().Name, StringComparison.OrdinalIgnoreCase))
        {
            if (!string.Equals(name.FullName, contract.GetName().FullName, StringComparison.Ordinal))
                throw new FileLoadException("contract");
            return contract;
        }

        if (listed.TryGetValue(name.Name, out var path))
        {
            var actual = AssemblyName.GetAssemblyName(path);
            if (!string.Equals(actual.FullName, name.FullName, StringComparison.Ordinal))
                throw new FileLoadException("identity");
            return LoadFromAssemblyPath(path);
        }

        if (name.Name.Equals("TrustedComposition.DeliveryHost", StringComparison.OrdinalIgnoreCase)
            || name.Name.Equals("RuneCLR.TrustedUpdate", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("unlisted", name.Name);
        if (Framework.TryMatch(name, out var frameworkPath))
        {
            var actual = AssemblyName.GetAssemblyName(frameworkPath);
            if (!FrameworkShare.Compatible(name, actual) || !Framework.Contains(frameworkPath))
                throw new FileLoadException("framework");
            return null;
        }

        throw new FileNotFoundException("unlisted", name.Name);
    }
}

sealed class FrameworkShare
{
    readonly string root;
    readonly Dictionary<string, string> paths;

    FrameworkShare(string root, Dictionary<string, string> paths)
    {
        this.root = root;
        this.paths = paths;
    }

    public static FrameworkShare Create()
    {
        var paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var blocked = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var location = typeof(object).Assembly.Location;
        if (string.IsNullOrEmpty(location))
            return new FrameworkShare("", paths);
        var root = Path.GetDirectoryName(Path.GetFullPath(location)) ?? "";
        if (root.Length == 0 || AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") is not string list)
            return new FrameworkShare(root, paths);
        foreach (var entry in list.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            string full;
            try
            {
                full = Path.GetFullPath(entry);
            }
            catch (Exception ex) when (ex is ArgumentException or NotSupportedException or IOException)
            {
                continue;
            }

            var simple = Path.GetFileNameWithoutExtension(full);
            if (string.IsNullOrEmpty(simple))
                continue;
            if (!IsUnder(root, full) || blocked.Contains(simple) || !paths.TryAdd(simple, full))
            {
                blocked.Add(simple);
                paths.Remove(simple);
            }
        }

        return new FrameworkShare(root, paths);
    }

    public bool TryMatch(AssemblyName name, out string path)
    {
        if (name.Name is not null && paths.TryGetValue(name.Name, out var found) && found is not null)
        {
            path = found;
            return true;
        }

        path = "";
        return false;
    }

    public bool Contains(string path) => root.Length > 0 && IsUnder(root, path);

    public static bool Compatible(AssemblyName request, AssemblyName actual)
    {
        if (request.Name is null || actual.Name is null
            || !request.Name.Equals(actual.Name, StringComparison.OrdinalIgnoreCase))
            return false;
        if (request.Version is not null && actual.Version is not null && request.Version != actual.Version)
            return false;
        if (request.CultureName is not null && actual.CultureName is not null
            && !string.Equals(request.CultureName, actual.CultureName, StringComparison.OrdinalIgnoreCase))
            return false;
        var requestedToken = request.GetPublicKeyToken();
        var actualToken = actual.GetPublicKeyToken();
        return requestedToken is not { Length: > 0 } || actualToken is not { Length: > 0 }
            || requestedToken.AsSpan().SequenceEqual(actualToken);
    }

    static bool IsUnder(string root, string full)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var prefix = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return full.StartsWith(prefix, comparison);
    }
}

sealed class DeliveryHostObject : IHostObject
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Touch(int value)
    {
        ExecutionWitness.Capture("host");
        return value + 11;
    }

    public int Invoke(IUpdateCallback callback, int value) => callback.Apply(value);

    public int InvokeDelegate(Func<int, int> callback, int value) => callback(value);

    public T Echo<T>(T value) => value;
}


