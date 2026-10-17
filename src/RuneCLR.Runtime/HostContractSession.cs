using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

public sealed class HostContractSession : IDisposable
{
    private HostContractLoadContext? _context;
    private bool _disposed;

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
            RequireContractCalls(start, contract, allowedMethods);
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


    private static void RequireContractCalls(MethodInfo start, Type contract, IReadOnlyCollection<string> allowedMethods)
    {
        var body = start.GetMethodBody() ?? throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        var il = body.GetILAsByteArray() ?? throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        var index = 0;
        while (index < il.Length)
        {
            var operation = ReadOpCode(il, ref index);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
            {
                var token = ReadInt32(il, ref index);
                MethodBase? called;
                try { called = start.Module.ResolveMethod(token); }
                catch (ArgumentException) { called = null; }
                var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
                if (called?.DeclaringType != contract || !allowed.Contains(called.Name))
                    throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
            }
            else if (operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Newobj.Value || operation.Value == OpCodes.Jmp.Value)
            {
                throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
            }
            else
            {
                SkipOperand(operation, il, ref index);
            }
        }
    }

    private static OpCode ReadOpCode(byte[] il, ref int index)
    {
        if (index >= il.Length)
            throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        var first = il[index++];
        var value = (short)first;
        if (first == 0xFE)
        {
            if (index >= il.Length)
                throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
            value = (short)(0xFE00 | il[index++]);
        }

        if (!Opcodes.TryGetValue(value, out var operation))
            throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        return operation;
    }

    private static int ReadInt32(byte[] il, ref int index)
    {
        if (index + 4 > il.Length)
            throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        var value = BitConverter.ToInt32(il, index);
        index += 4;
        return value;
    }

    private static void SkipOperand(OpCode operation, byte[] il, ref int index)
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
                var count = ReadInt32(il, ref index);
                index += count * 4;
                break;
            default:
                throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
        }

        if (index > il.Length)
            throw new InvalidOperationException("OnStart calls a method that is not a host contract member.");
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
