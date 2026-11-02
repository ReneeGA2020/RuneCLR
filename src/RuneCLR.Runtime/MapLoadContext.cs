using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

internal sealed class MapLoadContext : AssemblyLoadContext
{
    private readonly MapDependencyResolver _resolver;
    private static readonly Assembly Contract = typeof(IMapScript).Assembly;

    private MapLoadContext(string name, MapDependencyResolver resolver) : base(name, isCollectible: true)
    {
        _resolver = resolver;
    }

    public static AssemblyLoadContext Create(MapPackage package, MapDependencyResolver resolver,
        RequiredInterpreterBridge? required, TerminalPrototypeBridge? terminal, MapRunOptions options,
        CallbackDeadlineBridge? deadline = null, UgcAssemblyAdmission? admission = null)
    {
        var name = $"map:{package.Id}:{Guid.NewGuid():N}";
        var shared = new Dictionary<string, Assembly>(StringComparer.OrdinalIgnoreCase);
        foreach (var assembly in options.PrototypeSharedAssemblies)
        {
            if (assembly is null || assembly.IsDynamic || GetLoadContext(assembly) != Default ||
                !shared.TryAdd(assembly.GetName().Name!, assembly))
                throw new ArgumentException("Shared assemblies must be unique, existing default-context assemblies.");
        }
        Assembly? ResolveRequired(AssemblyLoadContext context, AssemblyName requested)
        {
            if (admission is not null) return admission.Resolve(context, requested);
            if (shared.TryGetValue(requested.Name ?? "", out var assembly))
            {
                MapDependencyResolver.RequireIdentity(requested, assembly.GetName());
                return assembly;
            }
            return Resolve(context, resolver, requested);
        }
        if (deadline is not null)
        {
            var created = deadline.Create(name, ResolveRequired, options);
            try { required!.Acknowledge(created); return created; }
            catch { created.Unload(); throw; }
        }
        if (terminal is not null)
            return terminal.Create(name, ResolveRequired,
                options.PrototypeInstructionBudget!.Value, options.PrototypeCleanupInstructionBudget);
        return required is null ? new MapLoadContext(name, resolver) :
            required.Create(name, ResolveRequired);
    }

    protected override Assembly? Load(AssemblyName assemblyName)
        => Resolve(this, _resolver, assemblyName);

    private static Assembly? Resolve(AssemblyLoadContext context, MapDependencyResolver resolver, AssemblyName assemblyName)
    {
        if (string.Equals(assemblyName.Name, Contract.GetName().Name, StringComparison.OrdinalIgnoreCase))
        {
            MapDependencyResolver.RequireIdentity(assemblyName, Contract.GetName());
            return Contract;
        }

        var path = resolver.Resolve(assemblyName);
        return path is null ? null : context.LoadFromAssemblyPath(path);
    }

    protected override nint LoadUnmanagedDll(string unmanagedDllName)
    {
        throw new NotSupportedException("Native libraries cannot be loaded through the map context.");
    }
}
