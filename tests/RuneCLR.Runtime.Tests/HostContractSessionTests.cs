using System.Reflection;
using System.Reflection.Emit;
using RuneCLR.Runtime;

internal static class HostContractSessionTests
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract OnStart receives the host instance and the context unloads", EchoAndUnload);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectWrongParameter);
    }

    private static void EchoAndUnload()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "echo.dll");
            WriteScript(path, "HostContract.EchoScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
            var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.EchoScript.Script");
            var reference = session.ContextReference;
            session.Dispose();
            Check(host.Seen == 41, "The host did not observe Echo(41).");
            for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }

            Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
        }
        finally
        {
            directory.Dispose();
        }
    }

    private static void RejectWrongParameter()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "wrong.dll");
            WriteScript(path, "HostContract.WrongScript", typeof(object), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 7, cast: true);
            var error = CheckThrows<InvalidOperationException>(() =>
                new HostContractSession(typeof(IHostEcho), host, path, "HostContract.WrongScript.Script"));
            Check(error.Message.Contains("host contract interface", StringComparison.Ordinal), error.Message);
            Check(host.Seen is null, "The author method was called.");
        }
        finally
        {
            directory.Dispose();
        }
    }

    private static void WriteScript(string path, string assemblyName, Type parameterType, MethodInfo echo, int value, bool cast)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [parameterType]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        if (cast) il.Emit(OpCodes.Castclass, typeof(IHostEcho));
        il.Emit(OpCodes.Ldc_I4, value);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private static T CheckThrows<T>(Action action) where T : Exception
    {
        try
        {
            action();
        }
        catch (T exception)
        {
            return exception;
        }

        throw new InvalidOperationException("Expected " + typeof(T).Name + ".");
    }

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "runeclr-host-contract-" + Guid.NewGuid().ToString("n"));
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}

public interface IHostEcho
{
    int Echo(int value);
}

sealed class RecordingEcho : IHostEcho
{
    public int? Seen { get; private set; }

    public int Echo(int value)
    {
        Seen = value;
        return value;
    }
}
