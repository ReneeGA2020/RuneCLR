using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.TrustedUpdate;
using TrustedGame.Contracts;

internal sealed class SampleActivation
{
    readonly bool allowLastKnownGood;

    public SampleActivation(bool allowLastKnownGood) => this.allowLastKnownGood = allowLastKnownGood;

    public TrustedModuleSession<IGameRules>? Session { get; private set; }
    public Type? RulesType { get; private set; }
    public AssemblyLoadContext? Context { get; private set; }
    public int ActivatorCalls { get; private set; }

    public TrustedUpdateActivation Activate(TrustedUpdateCandidate chosen, TrustedUpdateStartSource source,
        TrustedUpdateFailure candidateFailure)
    {
        ActivatorCalls++;
        if (source != TrustedUpdateStartSource.Candidate &&
            !(allowLastKnownGood && source == TrustedUpdateStartSource.LastKnownGood))
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        if (Session is not null)
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);

        try
        {
            Context = new GameModuleLoadContext(typeof(IGameRules).Assembly);
            var assembly = Context.LoadFromAssemblyPath(Path.GetFullPath(chosen.AssemblyPath));
            var type = assembly.GetType(chosen.EntryTypeName, throwOnError: true, ignoreCase: false);
            if (type is null || type.IsAbstract || type.IsInterface || type.ContainsGenericParameters ||
                !typeof(IGameRules).IsAssignableFrom(type))
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);

            RulesType = type;
            Session = new TrustedModuleSession<IGameRules>(CreateRules());
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, 0);
        }
        catch (Exception)
        {
            Session?.Dispose();
            Session = null;
            RulesType = null;
            Context = null;
            return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    public IGameRules CreateRules() => (IGameRules)Activator.CreateInstance(RulesType!)!;
}

sealed class GameModuleLoadContext : AssemblyLoadContext
{
    readonly Assembly contracts;
    readonly AssemblyName contractsName;

    public GameModuleLoadContext(Assembly contracts)
        : base("TrustedGame.Update.Resident", isCollectible: false)
    {
        this.contracts = contracts;
        contractsName = contracts.GetName();
    }

    protected override Assembly? Load(AssemblyName assemblyName)
    {
        if (!string.Equals(assemblyName.Name, contractsName.Name, StringComparison.OrdinalIgnoreCase))
            return null;
        if (!string.Equals(assemblyName.FullName, contractsName.FullName, StringComparison.Ordinal))
            throw new FileLoadException($"The update requested Contracts identity '{assemblyName.FullName}', expected '{contractsName.FullName}'.");
        return contracts;
    }
}
