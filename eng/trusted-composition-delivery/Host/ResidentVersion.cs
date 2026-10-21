using System.Reflection;
using System.Runtime.CompilerServices;
using RuneCLR.TrustedUpdate;

internal sealed class ResidentVersion<TModule> where TModule : class
{
    readonly ListedContext context;
    readonly Type entryType;
    readonly Assembly contractAssembly;

    ResidentVersion(ListedContext context, Type entryType, string version, Assembly contractAssembly)
    {
        this.context = context;
        this.entryType = entryType;
        this.contractAssembly = contractAssembly;
        Version = version;
    }

    public string Version { get; }
    public int Constructions { get; private set; }
    public string ContractName => contractAssembly.GetName().Name ?? "";
    public string ContractFullName => contractAssembly.GetName().FullName;

    public static bool TryBind(TrustedUpdateCandidate candidate, string expectedType, string expectedMethod, out ResidentVersion<TModule>? owner, out string failure)
    {
        owner = null;
        failure = "";
        var contract = typeof(TModule).Assembly;
        if (!string.Equals(candidate.EntryTypeName, expectedType, StringComparison.Ordinal)
            || !string.Equals(candidate.EntryMethodName, expectedMethod, StringComparison.Ordinal))
        {
            failure = "bootstrap";
            return false;
        }

        if (!DeliverySession.TryInventory(candidate, out var listed, out var detail))
        {
            failure = detail.Length == 0 ? "inventory" : detail;
            return false;
        }

        var contractName = contract.GetName().Name ?? "";
        if (listed.Keys.Any(name => name.Equals(contractName, StringComparison.OrdinalIgnoreCase)))
        {
            failure = "shadow-contract";
            return false;
        }

        try
        {
            var load = new ListedContext(listed, contract);
            var assembly = load.LoadFromAssemblyPath(candidate.AssemblyPath);
            var referenced = assembly.GetReferencedAssemblies().FirstOrDefault(name => name.Name == contractName);
            if (referenced is null || !string.Equals(referenced.FullName, contract.GetName().FullName, StringComparison.Ordinal))
            {
                failure = "contract-identity";
                return false;
            }

            var type = assembly.GetType(candidate.EntryTypeName, throwOnError: true);
            if (type is null || type.GetConstructor(Type.EmptyTypes) is null || !typeof(TModule).IsAssignableFrom(type))
            {
                failure = "entry";
                return false;
            }

            owner = new ResidentVersion<TModule>(load, type, candidate.VersionName, contract);
            return true;
        }
        catch (Exception ex) when (ex is FileLoadException or FileNotFoundException or BadImageFormatException or TypeLoadException or ReflectionTypeLoadException)
        {
            failure = ex is FileLoadException && ex.Message.Contains("contract", StringComparison.Ordinal) ? "contract-identity" : "bind";
            return false;
        }
    }

    public bool TryOpen(out TypedSession<TModule>? session, out string failure)
    {
        session = null;
        failure = "";
        try
        {
            if (Activator.CreateInstance(entryType) is not TModule module)
            {
                failure = "constructor-failed";
                return false;
            }

            Constructions++;
            session = new TypedSession<TModule>(module);
            return true;
        }
        catch (Exception)
        {
            failure = "constructor-failed";
            return false;
        }
    }

    public void SetStatic(string name, int value)
    {
        var field = entryType.GetField(name, BindingFlags.Public | BindingFlags.Static) ?? throw new InvalidOperationException(name);
        field.SetValue(null, value);
    }

    public int GetStatic(string name)
    {
        var field = entryType.GetField(name, BindingFlags.Public | BindingFlags.Static);
        return field?.GetValue(null) is int value ? value : -1;
    }

    public bool RejectsUnlisted(string name)
    {
        try
        {
            context.LoadFromAssemblyName(new AssemblyName(name));
            return false;
        }
        catch (FileNotFoundException)
        {
            return true;
        }
    }

    public int ContextId => RuntimeHelpers.GetHashCode(context);
}
