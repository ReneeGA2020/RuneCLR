using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

public sealed record HostContractSessionOptions
{
    public MapExecutionPolicy ExecutionPolicy { get; init; } = MapExecutionPolicy.Default;
    public IApiAccessPolicy? PrototypeApiPolicy { get; init; }
    public IReadOnlyList<Assembly> PrototypeSharedAssemblies { get; init; } = [];
    public bool PrototypeRequireOriginScan { get; init; }

    internal void Validate()
    {
        if (!Enum.IsDefined(ExecutionPolicy))
            throw new ArgumentOutOfRangeException(nameof(ExecutionPolicy));
        ArgumentNullException.ThrowIfNull(PrototypeSharedAssemblies);
        if (PrototypeApiPolicy is not null && ExecutionPolicy != MapExecutionPolicy.RequireInterpreter)
            throw new ArgumentException("A HostContract API policy requires RequireInterpreter.", nameof(ExecutionPolicy));
        if (ExecutionPolicy == MapExecutionPolicy.RequireInterpreter && PrototypeApiPolicy is null)
            throw new ArgumentException("RequireInterpreter requires a HostContract API policy.", nameof(PrototypeApiPolicy));
        if (PrototypeSharedAssemblies.Count != 0 && PrototypeApiPolicy is null)
            throw new ArgumentException("Explicit shared assemblies require a HostContract API policy.");
        if (PrototypeRequireOriginScan &&
            (PrototypeApiPolicy is null || ExecutionPolicy != MapExecutionPolicy.RequireInterpreter))
            throw new ArgumentException("Prototype origin scanning requires RequireInterpreter and a HostContract API policy.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var assembly in PrototypeSharedAssemblies)
        {
            if (assembly is null || assembly.IsDynamic ||
                AssemblyLoadContext.GetLoadContext(assembly) != AssemblyLoadContext.Default ||
                !names.Add(assembly.GetName().Name!))
                throw new ArgumentException("Shared assemblies must be unique, existing default-context assemblies.");
        }
    }
}
