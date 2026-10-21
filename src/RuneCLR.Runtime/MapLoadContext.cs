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
        CallbackDeadlineBridge? deadline = null)
    {
        var name = $"map:{package.Id}:{Guid.NewGuid():N}";
        if (deadline is not null)
        {
            var created = deadline.Create(name, (context, assemblyName) => Resolve(context, resolver, assemblyName), options);
            try { required!.Acknowledge(created); return created; }
            catch { created.Unload(); throw; }
        }
        if (terminal is not null)
            return terminal.Create(name, (context, assemblyName) => Resolve(context, resolver, assemblyName),
                options.PrototypeInstructionBudget!.Value, options.PrototypeCleanupInstructionBudget);
        return required is null ? new MapLoadContext(name, resolver) :
            required.Create(name, (context, assemblyName) => Resolve(context, resolver, assemblyName));
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
