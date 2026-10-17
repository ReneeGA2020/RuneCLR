using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;

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
                start.Invoke(script, [instance]);
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
            method.Invoke(_script, takesHost ? [_host] : null);
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
