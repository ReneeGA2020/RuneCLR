using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

public sealed class HostContractSession : IDisposable
{
    private HostContractLoadContext? _context;
    private bool _disposed;

    public HostContractSession(Type contract, object instance, string assemblyPath, string entryTypeName)
    {
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(instance);
        ArgumentException.ThrowIfNullOrWhiteSpace(assemblyPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(entryTypeName);
        if (!contract.IsInterface || !contract.IsInstanceOfType(instance))
            throw new InvalidOperationException("The host contract must be the interface implemented by the supplied instance.");

        _context = new HostContractLoadContext();
        ContextReference = new WeakReference(_context, trackResurrection: true);
        try
        {
            var bytes = File.ReadAllBytes(Path.GetFullPath(assemblyPath));
            using var stream = new MemoryStream(bytes, writable: false);
            var assembly = _context.LoadFromStream(stream);
            var entry = assembly.GetType(entryTypeName, throwOnError: false);
            var start = RequireOnStart(entry, contract);
            var script = Activator.CreateInstance(entry!)!;
            start.Invoke(script, [instance]);
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    public WeakReference ContextReference { get; }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _context?.Unload();
        _context = null;
    }

    private static MethodInfo RequireOnStart(Type? entry, Type contract)
    {
        if (entry is null || !entry.IsClass || !entry.IsPublic || entry.IsAbstract || entry.IsGenericType || entry.IsNested)
            throw new InvalidOperationException("The script entry must be a public non-abstract, non-generic, non-nested class.");

        var constructors = entry.GetConstructors(BindingFlags.Public | BindingFlags.Instance);
        if (constructors.Length != 1 || constructors[0].GetParameters().Length != 0)
            throw new InvalidOperationException("The script entry must have exactly one public parameterless constructor.");

        var starts = entry.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(method => method.Name == "OnStart")
            .ToArray();
        if (starts.Length != 1)
            throw new InvalidOperationException("The script entry must declare exactly one public instance method named OnStart.");

        var parameters = starts[0].GetParameters();
        if (parameters.Length != 1 || parameters[0].ParameterType != contract)
            throw new InvalidOperationException("OnStart must take exactly one parameter of the host contract interface.");
        return starts[0];
    }

    private sealed class HostContractLoadContext : AssemblyLoadContext
    {
        public HostContractLoadContext()
            : base("RuneCLR.HostContract:" + Guid.NewGuid().ToString("n"), isCollectible: true)
        {
        }

        protected override Assembly? Load(AssemblyName assemblyName)
        {
            foreach (var assembly in Default.Assemblies)
            {
                if (string.Equals(assembly.GetName().Name, assemblyName.Name, StringComparison.OrdinalIgnoreCase))
                    return assembly;
            }

            return null;
        }
    }
}
