using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.PortableExecutable;
using System.Reflection.Emit;
using System.Security.Cryptography;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class HostContractSessionTests
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract OnStart receives the host instance and the context unloads", EchoAndUnload);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectWrongParameter);
        yield return ("Host contract rejects an OnStart call that is not a host contract member", RejectForeignCall);
        yield return ("Host contract rejects an interface method that is not allowed", RejectUnlistedInterfaceMethod);
        yield return ("Host contract Invoke runs a later callback on the same session", InvokeLaterCallback);
        yield return ("Host contract Invoke rejects an unlisted later call before it runs", InvokeRejectsUnlisted);
        yield return ("Host contract Invoke passes the host interface into a later callback", InvokePassesTheHostAgain);
        yield return ("Host contract Invoke rejects a reentrant callback", InvokeRejectsReentry);
        yield return ("Host contract Invoke reports callback failure as text and continues", InvokeFailureIsText);
        yield return ("Host contract OnStart failure is text and does not return the session", OnStartFailureIsText);
        yield return ("Host contract Open uses the manifest allow list", OpenUsesManifest);
        yield return ("Host contract Open rejects a call outside the manifest allow list", OpenRejectsUnlisted);
        yield return ("Host contract Open rejects a different host interface", OpenRejectsInterface);
        yield return ("Host contract rejects a type initializer before the author runs", RejectTypeInitializer);
        yield return ("Host contract rejects a constructor call other than Object..ctor", RejectConstructorCall);
        yield return ("Host contract rejects an assembly that is not IL-only", RejectNativeImage);
        yield return ("Host contract rejects an assembly name that spoofs the framework", RejectSpoofedAssemblyName);
        yield return ("Host contract rejects a reference outside the contract assembly", RejectUnapprovedReference);
        yield return ("Host contract rejects unsafe IL before the author runs", RejectUnsafeIl);
    }

    private static void EchoAndUnload()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "echo.dll");
            WriteScript(path, "HostContract.EchoScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
            var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.EchoScript.Script", ["Echo"]);
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
                new HostContractSession(typeof(IHostEcho), host, path, "HostContract.WrongScript.Script", ["Echo"]));
            Check(error.Message.Contains("host contract interface", StringComparison.Ordinal), error.Message);
            Check(host.Seen is null, "The author method was called.");
        }
        finally
        {
            directory.Dispose();
        }
    }


    private static void RejectForeignCall()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "foreign.dll");
            WriteEchoAndForeignCall(path);
            var error = CheckThrows<InvalidOperationException>(() =>
                new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ForeignScript.Script", ["Echo"]));
            Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
            Check(host.Seen is null, "The author method was called.");
        }
        finally
        {
            directory.Dispose();
        }
    }


    private static void InvokeLaterCallback()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "later.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndLater(path, "HostContract.LaterScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.LaterScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick");
        Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not call Echo(2) after Echo(1).");
        var reference = session.ContextReference;
        session.Dispose();
        var disposed = CheckThrows<ObjectDisposedException>(() => session.Invoke("OnTick"));
        Check(disposed.ObjectName == nameof(HostContractSession), disposed.Message);
        for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
    }

    private static void InvokeRejectsUnlisted()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "later-other.dll");
        var other = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Other))!;
        WriteStartAndLater(path, "HostContract.LaterOtherScript", other, 1, 5);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.LaterOtherScript.Script", ["Echo"]);
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1]) && host.OtherSeen is null, "The unlisted callback ran.");
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void InvokePassesTheHostAgain()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "host-again.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndHostParameter(path, "HostContract.HostAgainScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.HostAgainScript.Script", ["Echo"]);
        try
        {
            Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
            session.Invoke("OnTick");
            Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not receive the host instance.");
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void InvokeRejectsReentry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "reentry.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndHostParameter(path, "HostContract.ReentryScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ReentryScript.Script", ["Echo"]);
        host.Nested = session;
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.InnerException is null, "The callback exception was retained.");
            Check(error.Message.Contains("already running", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1, 2]), "The nested callback ran.");
        }
        finally
        {
            host.Nested = null;
            session.Dispose();
        }
    }

    private static void InvokeFailureIsText()
    {
        var host = new RecordingEcho { ThrowOn = 2 };
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "failure.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartTickStop(path, "HostContract.FailureScript", echo);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.FailureScript.Script", ["Echo"]);
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.InnerException is null, "The callback exception was retained.");
            Check(error.Message.Contains("System.InvalidOperationException: host-failed", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not reach the host.");
            session.Invoke("OnStop");
            Check(host.Calls.SequenceEqual([1, 2, 3]), "The session did not continue after the failure.");
            var reference = session.ContextReference;
            session.Dispose();
            for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }

            Check(!reference.IsAlive, error.Message);
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void OnStartFailureIsText()
    {
        var host = new RecordingEcho { ThrowOn = 9 };
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "start-failure.dll");
        WriteScript(path, "HostContract.StartFailureScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 9, cast: false);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.StartFailureScript.Script", ["Echo"]));
        Check(error.InnerException is null, "The OnStart exception was retained.");
        Check(error.Message.Contains("System.InvalidOperationException: host-failed", StringComparison.Ordinal), error.Message);
        Check(host.Calls.SequenceEqual([9]), "OnStart did not reach the host.");
        GC.KeepAlive(error);
    }

    private static void OpenUsesManifest()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        var reference = session.ContextReference;
        session.Dispose();
        Check(host.Seen == 41, "The manifest allow list did not reach Echo.");
        for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
    }

    private static void OpenRejectsUnlisted()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenRejectScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenRejectScript.Script", typeof(IHostEcho).FullName!, ["Other"]);
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unlisted manifest call ran.");
    }

    private static void OpenRejectsInterface()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenInterfaceScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenInterfaceScript.Script", "Other.Contract", ["Echo"]);
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("does not match", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The mismatched interface ran.");
    }

    private static string WriteManifest(string directory, string assemblyFile, string entryType, string hostInterface, string[] methods)
    {
        var hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(directory, assemblyFile))));
        var empty = new string('0', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(assemblyFile, hash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", assemblyFile, entryType, hash, [], [new PackageFile(assemblyFile, hash)], producer, "",
            hostInterface, methods);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static void RejectTypeInitializer()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "initializer.dll");
        WriteInitializer(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.InitializerScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initializer", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The type initializer ran.");
    }

    private static void RejectConstructorCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "constructor.dll");
        WriteExtraConstructorCall(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ConstructorScript.Script", ["Echo"]));
        Check(error.Message.Contains("Object..ctor", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra constructor call ran.");
    }

    private static void WriteInitializer(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.InitializerScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.InitializerScript");
        var type = module.DefineType("HostContract.InitializerScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var initializer = type.DefineConstructor(MethodAttributes.Private | MethodAttributes.Static, CallingConventions.Standard, Type.EmptyTypes);
        var initializerIl = initializer.GetILGenerator();
        initializerIl.Emit(OpCodes.Ldstr, "initializer-ran");
        initializerIl.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
        initializerIl.Emit(OpCodes.Throw);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteExtraConstructorCall(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ConstructorScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ConstructorScript");
        var type = module.DefineType("HostContract.ConstructorScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Callvirt, typeof(object).GetMethod(nameof(object.ToString), Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Pop);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectNativeImage()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "native.dll");
        WriteScript(path, "HostContract.NativeScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        ClearIlOnly(path);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.NativeScript.Script", ["Echo"]));
        Check(error.Message.Contains("IL-only", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The native image ran.");
    }

    private static void ClearIlOnly(string path)
    {
        var bytes = File.ReadAllBytes(path);
        using var stream = new MemoryStream(bytes, writable: false);
        using var pe = new PEReader(stream, PEStreamOptions.LeaveOpen);
        var flags = (uint)(pe.PEHeaders.CorHeader!.Flags & ~CorFlags.ILOnly);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(pe.PEHeaders.CorHeaderStartOffset + 16), flags);
        File.WriteAllBytes(path, bytes);
    }

    private static void RejectSpoofedAssemblyName()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "spoof.dll");
        WriteScript(path, "System.IO", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "System.IO.Script", ["Echo"]));
        Check(error.Message.Contains("spoofs", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("System.IO", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The spoofed assembly ran.");
    }

    private static void RejectUnapprovedReference()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "reference.dll");
        WriteExtraReference(path);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ReferenceScript.Script", ["Echo"]));
        Check(error.Message.Contains("not approved", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("RuneCLR.Packages", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra reference ran.");
    }

    private static void WriteExtraReference(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ReferenceScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ReferenceScript");
        var type = module.DefineType("HostContract.ReferenceScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        type.DefineField("extra", typeof(PackageManifest), FieldAttributes.Private);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectUnsafeIl()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "unsafe.dll");
        WriteUnsafeOnStart(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.UnsafeScript.Script", ["Echo"]));
        Check(error.Message.Contains("Unsafe IL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "Unsafe IL ran.");
    }

    private static void WriteUnsafeOnStart(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.UnsafeScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.UnsafeScript");
        var type = module.DefineType("HostContract.UnsafeScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_4);
        il.Emit(OpCodes.Localloc);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectUnlistedInterfaceMethod()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "other.dll");
        WriteScript(path, "HostContract.OtherScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Other))!, 5, cast: false);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.OtherScript.Script", ["Echo"]));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null && host.OtherSeen is null, "The author method was called.");
    }
    private static void WriteStartTickStop(string path, string assemblyName, MethodInfo echo)
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
        void EmitCall(string name, int value)
        {
            var method = type.DefineMethod(name, MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
            var il = method.GetILGenerator();
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Ldc_I4, value);
            il.Emit(OpCodes.Callvirt, echo);
            il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Ret);
        }

        EmitCall("OnStart", 1);
        EmitCall("OnTick", 2);
        EmitCall("OnStop", 3);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndHostParameter(string path, string assemblyName, MethodInfo later, int startValue, int laterValue)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, startValue);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Ldc_I4, laterValue);
        tickIl.Emit(OpCodes.Callvirt, later);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndLater(string path, string assemblyName, MethodInfo later, int startValue, int laterValue)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var field = type.DefineField("host", typeof(IHostEcho), FieldAttributes.Private);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Stfld, field);
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldfld, field);
        startIl.Emit(OpCodes.Ldc_I4, startValue);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), Type.EmptyTypes);
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_0);
        tickIl.Emit(OpCodes.Ldfld, field);
        tickIl.Emit(OpCodes.Ldc_I4, laterValue);
        tickIl.Emit(OpCodes.Callvirt, later);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteEchoAndForeignCall(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var toString = typeof(object).GetMethod(nameof(object.ToString), Type.EmptyTypes)!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ForeignScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ForeignScript");
        var type = module.DefineType("HostContract.ForeignScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 41);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Callvirt, toString);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
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
    int Other(int value);
}

sealed class RecordingEcho : IHostEcho
{
    public int? Seen { get; private set; }

    public int? OtherSeen { get; private set; }

    public List<int> Calls { get; } = [];

    public HostContractSession? Nested { get; set; }

    public int? ThrowOn { get; set; }

    public int Echo(int value)
    {
        Seen = value;
        Calls.Add(value);
        if (value == 2 && Nested is not null)
            Nested.Invoke("OnTick");
        if (ThrowOn == value) throw new InvalidOperationException("host-failed");
        return value;
    }

    public int Other(int value)
    {
        OtherSeen = value;
        return value;
    }
}
