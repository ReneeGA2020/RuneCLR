using System.Reflection;
using System.Security.Cryptography;
using System.Reflection.Emit;
using System.Runtime.Loader;

using RuneCLR.Packages;

namespace RuneCLR.Runtime;

public sealed class HostContractSession : IDisposable
{
    private HostContractLoadContext? _context;
    private object? _script;
    private object? _host;
    private Type? _contract;
    private HashSet<string>? _allowedMethods;
    private bool _disposed;
    private bool _invoking;

    public static HostContractSession Open(string manifestPath, Type contract, object instance)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(manifestPath);
        ArgumentNullException.ThrowIfNull(contract);
        var manifest = PackageManifestIO.Read(manifestPath);
        if (!string.Equals(PackageManifestIO.ComputeContentSha256(manifest), manifest.ContentSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The package content identity does not match the manifest.");
        if (string.IsNullOrWhiteSpace(manifest.HostInterface) || manifest.AllowedMethods is null ||
            manifest.AllowedMethods.Length == 0 || manifest.AllowedMethods.Any(string.IsNullOrWhiteSpace) ||
            manifest.AllowedMethods.Distinct(StringComparer.Ordinal).Count() != manifest.AllowedMethods.Length)
            throw new InvalidDataException("The host interface and allowed methods must both be present, nonempty and unique.");
        if (!string.Equals(manifest.HostInterface, contract.FullName, StringComparison.Ordinal))
            throw new InvalidOperationException("The package host interface does not match the supplied contract.");
        var directory = Path.GetDirectoryName(Path.GetFullPath(manifestPath))
            ?? throw new InvalidDataException("The package manifest requires a directory.");
        var entry = ResolveEntry(directory, manifest.EntryAssembly);
        var hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(entry)));
        if (!string.Equals(hash, manifest.EntrySha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package file hash mismatch: " + manifest.EntryAssembly + ".");
        return new HostContractSession(contract, instance, entry, manifest.EntryType, manifest.AllowedMethods);
    }

    private static string ResolveEntry(string directory, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.IndexOf((char)92) >= 0 || relative.IndexOf((char)58) >= 0 ||
            relative.Split('/').Any(part => part is "" or "." or ".."))
            throw new InvalidDataException("Package content paths must be canonical relative DLL paths using forward slashes.");
        var full = Path.GetFullPath(Path.Combine(directory, relative.Replace('/', Path.DirectorySeparatorChar)));
        var root = Path.GetFullPath(directory + Path.DirectorySeparatorChar);
        if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package content paths must be canonical relative DLL paths using forward slashes.");
        return full;
    }

    public HostContractSession(Type contract, object instance, string assemblyPath, string entryTypeName, IReadOnlyCollection<string> allowedMethods)
    {
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(instance);
        ArgumentException.ThrowIfNullOrWhiteSpace(assemblyPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(entryTypeName);
        ArgumentNullException.ThrowIfNull(allowedMethods);
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
            var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
            RequireContractCalls(start, contract, allowed, "OnStart calls a method that is not a host contract member.");
            var script = Activator.CreateInstance(entry!)!;
            _invoking = true;
            try
            {
                try
                {
                    start.Invoke(script, [instance]);
                }
                catch (Exception exception)
                {
                    throw HostFailure(exception);
                }

                _script = script;
                _host = instance;
                _contract = contract;
                _allowedMethods = allowed;
            }
            finally
            {
                _invoking = false;
            }
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    public WeakReference ContextReference { get; }

    public void Invoke(string methodName)
    {
        if (_disposed || _script is null || _host is null || _contract is null || _allowedMethods is null)
            throw new ObjectDisposedException(nameof(HostContractSession));
        if (_invoking)
            throw new InvalidOperationException("A session lifecycle callback is already running.");
        ArgumentException.ThrowIfNullOrWhiteSpace(methodName);
        if (methodName == "OnStart")
            throw new InvalidOperationException("OnStart has already run.");
        var methods = _script.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(method => method.Name == methodName)
            .ToArray();
        var method = methods.Length == 1 ? methods[0] : null;
        var parameters = method?.GetParameters() ?? [];
        var takesHost = parameters.Length == 1 && parameters[0].ParameterType == _contract;
        if (method is null || method.ReturnType != typeof(void) || method.IsGenericMethod || (parameters.Length != 0 && !takesHost))
            throw new InvalidOperationException("The callback must be one public void method with no parameters or one host-contract parameter.");
        const string failure = "The callback calls a method that is not a host contract member.";
        RequireContractCalls(method, _contract, _allowedMethods, failure);
        _invoking = true;
        try
        {
            try
            {
                method.Invoke(_script, takesHost ? [_host] : null);
            }
            catch (Exception exception)
            {
                throw HostFailure(exception);
            }
        }
        finally
        {
            _invoking = false;
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _script = null;
        _host = null;
        _contract = null;
        _allowedMethods = null;
        _context?.Unload();
        _context = null;
    }

    private static InvalidOperationException HostFailure(Exception exception)
    {
        if (exception is TargetInvocationException { InnerException: { } inner }) exception = inner;
        var typeName = exception.GetType().FullName ?? "Exception";
        string described;
        try
        {
            described = typeName + ": " + exception.Message;
        }
        catch (Exception)
        {
            described = typeName + ": The exception message could not be read.";
        }

        if (described.Length > 2048) described = described[..2045] + "...";
        return new InvalidOperationException(described);
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

    private static void RequireContractCalls(MethodInfo method, Type contract, HashSet<string> allowedMethods, string failure)
    {
        var body = method.GetMethodBody() ?? throw new InvalidOperationException(failure);
        var il = body.GetILAsByteArray() ?? throw new InvalidOperationException(failure);
        var index = 0;
        while (index < il.Length)
        {
            var operation = ReadOpCode(il, ref index, failure);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
            {
                var token = ReadInt32(il, ref index, failure);
                MethodBase? called;
                try { called = method.Module.ResolveMethod(token); }
                catch (ArgumentException) { called = null; }
                if (called?.DeclaringType != contract || !allowedMethods.Contains(called.Name))
                    throw new InvalidOperationException(failure);
            }
            else if (operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Newobj.Value || operation.Value == OpCodes.Jmp.Value)
            {
                throw new InvalidOperationException(failure);
            }
            else
            {
                SkipOperand(operation, il, ref index, failure);
            }
        }
    }

    private static OpCode ReadOpCode(byte[] il, ref int index, string failure)
    {
        if (index >= il.Length)
            throw new InvalidOperationException(failure);
        var first = il[index++];
        var value = (short)first;
        if (first == 0xFE)
        {
            if (index >= il.Length)
                throw new InvalidOperationException(failure);
            value = (short)(0xFE00 | il[index++]);
        }

        if (!Opcodes.TryGetValue(value, out var operation))
            throw new InvalidOperationException(failure);
        return operation;
    }

    private static int ReadInt32(byte[] il, ref int index, string failure)
    {
        if (index + 4 > il.Length)
            throw new InvalidOperationException(failure);
        var value = BitConverter.ToInt32(il, index);
        index += 4;
        return value;
    }

    private static void SkipOperand(OpCode operation, byte[] il, ref int index, string failure)
    {
        switch (operation.OperandType)
        {
            case OperandType.InlineNone:
                return;
            case OperandType.ShortInlineBrTarget:
            case OperandType.ShortInlineI:
            case OperandType.ShortInlineVar:
                index += 1;
                break;
            case OperandType.InlineVar:
                index += 2;
                break;
            case OperandType.InlineBrTarget:
            case OperandType.InlineField:
            case OperandType.InlineI:
            case OperandType.InlineMethod:
            case OperandType.InlineSig:
            case OperandType.InlineString:
            case OperandType.InlineTok:
            case OperandType.InlineType:
            case OperandType.ShortInlineR:
                index += 4;
                break;
            case OperandType.InlineI8:
            case OperandType.InlineR:
                index += 8;
                break;
            case OperandType.InlineSwitch:
                var count = ReadInt32(il, ref index, failure);
                index += count * 4;
                break;
            default:
                throw new InvalidOperationException(failure);
        }

        if (index > il.Length)
            throw new InvalidOperationException(failure);
    }

    private static readonly Dictionary<short, OpCode> Opcodes = typeof(OpCodes)
        .GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(field => field.FieldType == typeof(OpCode))
        .Select(field => (OpCode)field.GetValue(null)!)
        .ToDictionary(operation => operation.Value);

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
