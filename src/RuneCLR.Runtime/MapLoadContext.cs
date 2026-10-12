using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

internal sealed class MapLoadContext : AssemblyLoadContext
{
    private readonly AssemblyDependencyResolver _resolver;
    private static readonly Assembly Contract = typeof(IMapScript).Assembly;

    public MapLoadContext(MapPackage package) : base($"map:{package.Id}:{Guid.NewGuid():N}", isCollectible: true)
    {
        _resolver = new AssemblyDependencyResolver(Path.GetFullPath(package.AssemblyPath));
    }

    protected override Assembly? Load(AssemblyName assemblyName)
    {
        if (assemblyName.Name == Contract.GetName().Name)
        {
            if (assemblyName.Version != Contract.GetName().Version)
            {
                throw new FileLoadException("The map uses an incompatible RuneCLR API version.");
            }

            return Contract;
        }

        var path = _resolver.ResolveAssemblyToPath(assemblyName);
        return path is null ? null : LoadFromAssemblyPath(path);
    }

    protected override nint LoadUnmanagedDll(string unmanagedDllName)
    {
        throw new NotSupportedException("Native libraries cannot be loaded through the map context.");
    }
}
