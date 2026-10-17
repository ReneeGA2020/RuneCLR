using System.Buffers.Binary;
using System.Reflection;
using System.Runtime.Loader;
using System.Reflection.Metadata;
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
        yield return ("Host contract unloads when a later callback is rejected", RejectedCallbackUnloads);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectWrongParameter);
        yield return ("Host contract rejects an OnStart call that is not a host contract member", RejectForeignCall);
        yield return ("Host contract rejects an interface method that is not allowed", RejectUnlistedInterfaceMethod);
        yield return ("Host contract Invoke runs a later callback on the same session", InvokeLaterCallback);
        yield return ("Host contract Invoke passes an int to a later callback", InvokePassesAnInt);
        yield return ("Host contract allows an unsupported public method", OpenAllowsUnsupportedMethod);
        yield return ("Host contract runs a later callback into a private assembly", OpenLaterPrivateCallback);
        yield return ("Host contract unloads when a later private call is rejected", OpenRejectsLaterPrivateCall);
        yield return ("Host contract constructs a private type from a later callback", OpenLaterConstructsPrivateType);
        yield return ("Host contract rejects a private constructor from a later callback before OnStart", OpenRejectsLaterPrivateConstructor);
        yield return ("Host contract rejects a bad int callback before OnStart", InvokeIntRejectsBcl);
        yield return ("Host contract Invoke without an int does not run an int callback", InvokeIntRequiresTheValue);
        yield return ("Host contract InvokeInt returns an int from a later callback", InvokeIntReturns);
        yield return ("Host contract rejects a bad int return before OnStart", InvokeIntReturnRejectsBcl);
        yield return ("Host contract InvokeInt rejects a void callback", InvokeIntRejectsVoid);
        yield return ("Host contract Invoke passes the host and an int", InvokePassesHostAndInt);
        yield return ("Host contract InvokeInt passes the host and returns an int", InvokeIntPassesHost);
        yield return ("Host contract rejects a bad host-and-int callback before OnStart", InvokeHostAndIntRejectsBcl);
        yield return ("Host contract rejects an unlisted later call before OnStart", InvokeRejectsUnlisted);
        yield return ("Host contract Invoke passes the host interface into a later callback", InvokePassesTheHostAgain);
        yield return ("Host contract Invoke rejects a reentrant callback", InvokeRejectsReentry);
        yield return ("Host contract Invoke reports callback failure as text and continues", InvokeFailureIsText);
        yield return ("Host contract OnStart failure is text and does not return the session", OnStartFailureIsText);
        yield return ("Host contract unloads when OnStart fails", OnStartFailureUnloads);
        yield return ("Host contract Open uses the manifest allow list", OpenUsesManifest);
        yield return ("Host contract Open rejects a call outside the manifest allow list", OpenRejectsUnlisted);
        yield return ("Host contract Open rejects a different host interface", OpenRejectsInterface);
        yield return ("Host contract Open rejects a changed entry file", OpenRejectsEntryTamper);
        yield return ("Host contract Open rejects a manifest whose content hash does not match", OpenRejectsContentTamper);
        yield return ("Host contract Open rejects an unsupported package format", OpenRejectsUnsupportedFormat);
        yield return ("Host contract Open rejects an entry over the assembly size limit", OpenRejectsOversizedEntry);
        yield return ("Host contract Open rejects a filesystem link", OpenRejectsFilesystemLink);
        yield return ("Host contract Open rejects a package directory nested too deeply", OpenRejectsDeepDirectory);
        yield return ("Host contract Open rejects an unsupported producer input kind", OpenRejectsProducerKind);
        yield return ("Host contract Open rejects an entry path that escapes the package", OpenRejectsEscapingPath);
        yield return ("Host contract Open rejects an entry that is not a DLL", OpenRejectsNonDll);
        yield return ("Host contract Open rejects an entry missing from the file list", OpenRejectsUnlistedEntry);
        yield return ("Host contract Open rejects an entry hash that disagrees with the file list", OpenRejectsMismatchedFileHash);
        yield return ("Host contract Open rejects a dependency path that escapes the package", OpenRejectsEscapingDependency);
        yield return ("Host contract Open rejects a file that is not the entry or a dependency", OpenRejectsExtraFile);
        yield return ("Host contract Open rejects an extra file on disk", OpenRejectsExtraDiskFile);
        yield return ("Host contract Open accepts a dependency whose bytes match", OpenAcceptsDependency);
        yield return ("Host contract Open calls a method on a declared private assembly", OpenCallsPrivateAssembly);
        yield return ("Host contract Open rejects a private call outside the host contract", OpenRejectsPrivateForeignCall);
        yield return ("Host contract Open lets a private method call the entry", OpenPrivateCallsEntry);
        yield return ("Host contract Open rejects a BCL call reached through the entry", OpenRejectsEntryCallFromPrivate);
        yield return ("Host contract constructs an author type", OpenConstructsAuthorType);
        yield return ("Host contract Open constructs a private assembly type", OpenConstructsPrivateType);
        yield return ("Host contract Open rejects a BCL call inside a private constructor", OpenRejectsPrivateConstructorCall);
        yield return ("Host contract Open lets one private assembly call another", OpenPrivateCallsPrivate);
        yield return ("Host contract Open rejects a BCL call reached through a second private assembly", OpenRejectsSecondPrivateCall);
        yield return ("Host contract rejects a framework constructor", OpenRejectsFrameworkNew);
        yield return ("Host contract Open rejects a missing dependency file", OpenRejectsMissingDependency);
        yield return ("Host contract Open rejects a changed dependency file", OpenRejectsChangedDependency);
        yield return ("Host contract Open rejects a dependency that is not a managed assembly", OpenRejectsOpaqueDependency);
        yield return ("Host contract Open rejects a dependency that spoofs a framework name", OpenRejectsSpoofedDependency);
        yield return ("Host contract Open rejects a dependency whose assembly identity does not match", OpenRejectsDependencyIdentity);
        yield return ("Host contract rejects a type initializer before the author runs", RejectTypeInitializer);
        yield return ("Host contract rejects a constructor call other than Object..ctor", RejectConstructorCall);
        yield return ("Host contract rejects an assembly that is not IL-only", RejectNativeImage);
        yield return ("Host contract rejects an assembly name that spoofs the framework", RejectSpoofedAssemblyName);
        yield return ("Host contract rejects a reference outside the contract assembly", RejectUnapprovedReference);
        yield return ("Host contract rejects unsafe IL before the author runs", RejectUnsafeIl);
        yield return ("Host contract rejects a static field load before the author runs", RejectStaticFieldLoad);
        yield return ("Host contract rejects boxing an author value type", RejectAuthorBox);
        yield return ("Host contract rejects an author array type before the author runs", RejectAuthorArray);
        yield return ("Host contract rejects a cast to an author type", RejectAuthorCast);
        yield return ("Host contract rejects a function pointer before the author runs", RejectFunctionPointer);
        yield return ("Host contract rejects copying an author value type", RejectAuthorCopy);
        yield return ("Host contract rejects a field of another type", RejectForeignFieldLoad);
        yield return ("Host contract rejects an author catch type", RejectAuthorCatch);
        yield return ("Host contract still runs a catch of System.Exception", CoreCatchStillRuns);
        yield return ("Host contract rejects an exception filter", RejectExceptionFilter);
        yield return ("Host contract rejects a generic OnStart", RejectGenericOnStart);
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

    private static void RejectedCallbackUnloads()
    {
        var before = HostContractContextCount();
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "tick.dll");
        WriteStartAndInt(path, "HostContract.UnloadForeignScript", foreign: true);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.UnloadForeignScript.Script", ["Echo"]));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the rejected callback.");
        for (var attempt = 0; attempt < 10 && HostContractContextCount() > before; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(HostContractContextCount() == before, "The rejected session context was still loaded.");
        GC.KeepAlive(error);
    }

    private static int HostContractContextCount() =>
        AssemblyLoadContext.All.Count(context => context.Name != null &&
            context.Name.StartsWith("RuneCLR.HostContract:", StringComparison.Ordinal));

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

    private static void OpenLaterConstructsPrivateType()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateBox(library, "HostContract.LaterBox", foreignCtor: false);
        WriteTickConstructsBox(entry, "HostContract.LaterBoxCaller", library, "HostContract.LaterBox.Box");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.LaterBoxCaller.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick", 41);
        Check(host.Calls.SequenceEqual([1, 41]), "The later constructor did not return 41.");
        session.Dispose();
    }

    private static void OpenRejectsLaterPrivateConstructor()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateBox(library, "HostContract.LaterForeignBox", foreignCtor: true);
        WriteTickConstructsBox(entry, "HostContract.LaterForeignBoxCaller", library, "HostContract.LaterForeignBox.Box");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.LaterForeignBoxCaller.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the later constructor.");
    }

    private static void WriteTickConstructsBox(string path, string assemblyName, string libraryPath, string boxType)
    {
        var library = Assembly.Load(File.ReadAllBytes(libraryPath));
        var box = library.GetType(boxType, throwOnError: true)!;
        var ctor = box.GetConstructor(new[] { typeof(int) })!;
        var get = box.GetMethod("Get")!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho), typeof(int) });
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Ldarg_2);
        tickIl.Emit(OpCodes.Newobj, ctor);
        tickIl.Emit(OpCodes.Call, get);
        tickIl.Emit(OpCodes.Callvirt, echo);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void OpenLaterPrivateCallback()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateAdd(library, "HostContract.LaterLib", foreign: false);
        WriteTickCallsPrivate(entry, "HostContract.LaterCaller", library, "HostContract.LaterLib.Math");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.LaterCaller.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick", 40);
        Check(host.Calls.SequenceEqual([1, 41]), "The later private call did not return 41.");
        session.Dispose();
    }

    private static void OpenRejectsLaterPrivateCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateAdd(library, "HostContract.LaterForeignLib", foreign: true);
        WriteTickCallsPrivate(entry, "HostContract.LaterForeignCaller", library, "HostContract.LaterForeignLib.Math");
        var before = HostContractContextCount();
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.LaterForeignCaller.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("The callback OnTick calls a method that is not a host contract member.", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("ReadAllText", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the later private call.");
        for (var attempt = 0; attempt < 10 && HostContractContextCount() > before; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(HostContractContextCount() == before, "The rejected private-call context was still loaded.");
        GC.KeepAlive(error);
    }

    private static void WriteTickCallsPrivate(string path, string assemblyName, string libraryPath, string mathType)
    {
        var library = Assembly.Load(File.ReadAllBytes(libraryPath));
        var addOne = library.GetType(mathType, throwOnError: true)!.GetMethod("AddOne")!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho), typeof(int) });
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Ldarg_2);
        tickIl.Emit(OpCodes.Call, addOne);
        tickIl.Emit(OpCodes.Callvirt, echo);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void OpenAllowsUnsupportedMethod()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "unused.dll");
        WriteUnusedStringMethod(path, "HostContract.UnusedScript");
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.UnusedScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not run.");
        session.Dispose();
    }

    private static void WriteUnusedStringMethod(string path, string assemblyName)
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var unused = type.DefineMethod("Unused", MethodAttributes.Public, typeof(void), new[] { typeof(string) });
        var unusedIl = unused.GetILGenerator();
        unusedIl.Emit(OpCodes.Ldarg_1);
        unusedIl.Emit(OpCodes.Callvirt, typeof(string).GetMethod(nameof(string.ToString), Type.EmptyTypes)!);
        unusedIl.Emit(OpCodes.Pop);
        unusedIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void InvokePassesAnInt()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "tick.dll");
        WriteStartAndInt(path, "HostContract.IntScript", foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.IntScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick", 41);
        Check(host.Calls.SequenceEqual([1, 41]), "OnTick did not receive 41.");
        session.Dispose();
    }

    private static void InvokeIntRejectsBcl()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "tick.dll");
        WriteStartAndInt(path, "HostContract.IntForeignScript", foreign: true);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.IntForeignScript.Script", ["Echo"]));
        Check(error.Message.Contains("The callback OnTick calls a method that is not a host contract member.", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("IsNullOrEmpty", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the bad callback.");
    }

    private static void InvokeIntRequiresTheValue()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "tick.dll");
        WriteStartAndInt(path, "HostContract.IntShapeScript", foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.IntShapeScript.Script", ["Echo"]);
        var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
        Check(error.Message.Contains("no parameters or one host-contract parameter", StringComparison.Ordinal), error.Message);
        Check(host.Calls.SequenceEqual([1]), "The int callback ran without a value.");
        session.Dispose();
    }

    private static void InvokeIntReturns()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "measure.dll");
        WriteStartAndMeasure(path, "HostContract.MeasureScript", foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.MeasureScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        var result = session.InvokeInt("Measure", 40);
        Check(result == 41, "Measure did not return 41.");
        Check(host.Calls.SequenceEqual([1]), "Measure called the host.");
        session.Dispose();
    }

    private static void InvokeIntReturnRejectsBcl()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "measure.dll");
        WriteStartAndMeasure(path, "HostContract.MeasureForeignScript", foreign: true);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.MeasureForeignScript.Script", ["Echo"]));
        Check(error.Message.Contains("The callback Measure calls a method that is not a host contract member.", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("IsNullOrEmpty", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the bad callback.");
    }

    private static void InvokeIntRejectsVoid()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "measure.dll");
        WriteStartAndInt(path, "HostContract.MeasureVoidScript", foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.MeasureVoidScript.Script", ["Echo"]);
        var error = CheckThrows<InvalidOperationException>(() => session.InvokeInt("OnTick", 40));
        Check(error.Message.Contains("one public int method", StringComparison.Ordinal), error.Message);
        Check(host.Calls.SequenceEqual([1]), "The void callback ran through InvokeInt.");
        session.Dispose();
    }

    private static void InvokePassesHostAndInt()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "both.dll");
        WriteHostAndInt(path, "HostContract.HostIntScript", returning: false, foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.HostIntScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick", 41);
        Check(host.Calls.SequenceEqual([1, 41]), "OnTick did not receive the host and 41.");
        session.Dispose();
    }

    private static void InvokeIntPassesHost()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "both.dll");
        WriteHostAndInt(path, "HostContract.HostMeasureScript", returning: true, foreign: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.HostMeasureScript.Script", ["Echo"]);
        var result = session.InvokeInt("Measure", 40);
        Check(result == 41, "Measure did not return 41.");
        Check(host.Calls.SequenceEqual([1, 40]), "Measure did not echo the supplied int.");
        session.Dispose();
    }

    private static void InvokeHostAndIntRejectsBcl()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "both.dll");
        WriteHostAndInt(path, "HostContract.HostIntForeignScript", returning: false, foreign: true);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.HostIntForeignScript.Script", ["Echo"]));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0, "OnStart ran despite the bad callback.");
    }

    private static void WriteHostAndInt(string path, string assemblyName, bool returning, bool foreign)
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var later = type.DefineMethod(returning ? "Measure" : "OnTick", MethodAttributes.Public,
            returning ? typeof(int) : typeof(void), new[] { typeof(IHostEcho), typeof(int) });
        var laterIl = later.GetILGenerator();
        if (foreign)
        {
            laterIl.Emit(OpCodes.Ldnull);
            laterIl.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            laterIl.Emit(OpCodes.Pop);
        }

        laterIl.Emit(OpCodes.Ldarg_1);
        laterIl.Emit(OpCodes.Ldarg_2);
        laterIl.Emit(OpCodes.Callvirt, echo);
        laterIl.Emit(OpCodes.Pop);
        if (returning)
        {
            laterIl.Emit(OpCodes.Ldarg_2);
            laterIl.Emit(OpCodes.Ldc_I4_1);
            laterIl.Emit(OpCodes.Add);
        }

        laterIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndMeasure(string path, string assemblyName, bool foreign)
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var measure = type.DefineMethod("Measure", MethodAttributes.Public, typeof(int), new[] { typeof(int) });
        var measureIl = measure.GetILGenerator();
        if (foreign)
        {
            measureIl.Emit(OpCodes.Ldnull);
            measureIl.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            measureIl.Emit(OpCodes.Pop);
        }

        measureIl.Emit(OpCodes.Ldarg_1);
        measureIl.Emit(OpCodes.Ldc_I4_1);
        measureIl.Emit(OpCodes.Add);
        measureIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndInt(string path, string assemblyName, bool foreign)
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Stfld, field);
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldfld, field);
        startIl.Emit(OpCodes.Ldc_I4, 1);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), new[] { typeof(int) });
        var tickIl = tick.GetILGenerator();
        if (foreign)
        {
            tickIl.Emit(OpCodes.Ldnull);
            tickIl.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            tickIl.Emit(OpCodes.Pop);
        }

        tickIl.Emit(OpCodes.Ldarg_0);
        tickIl.Emit(OpCodes.Ldfld, field);
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Callvirt, echo);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void InvokeRejectsUnlisted()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "later-other.dll");
        var other = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Other))!;
        WriteStartAndLater(path, "HostContract.LaterOtherScript", other, 1, 5);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.LaterOtherScript.Script", ["Echo"]));
        Check(error.Message.Contains("The callback OnTick calls a method that is not a host contract member.", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains(".Other", StringComparison.Ordinal), error.Message);
        Check(host.Calls.Count == 0 && host.OtherSeen is null, "OnStart ran despite the unlisted callback.");
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

    private static void OnStartFailureUnloads()
    {
        var before = HostContractContextCount();
        var host = new RecordingEcho { ThrowOn = 9 };
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "start-failure.dll");
        WriteScript(path, "HostContract.StartUnloadScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 9, cast: false);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.StartUnloadScript.Script", ["Echo"]));
        Check(error.InnerException is null, "The OnStart exception was retained.");
        Check(error.Message.Contains("System.InvalidOperationException: host-failed", StringComparison.Ordinal), error.Message);
        Check(host.Calls.SequenceEqual([9]), "OnStart did not reach the host.");
        for (var attempt = 0; attempt < 10 && HostContractContextCount() > before; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(HostContractContextCount() == before, "The failed OnStart context was still loaded.");
        GC.KeepAlive(error);
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

    private static void OpenRejectsEntryTamper()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenEntryScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenEntryScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var bytes = File.ReadAllBytes(path);
        bytes[^1] ^= 0xFF;
        File.WriteAllBytes(path, bytes);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The tampered entry ran.");
    }

    private static void OpenRejectsContentTamper()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenContentScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenContentScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var json = File.ReadAllText(manifest).Replace(typeof(IHostEcho).FullName!, nameof(IHostEcho) + "0", StringComparison.Ordinal);
        File.WriteAllText(manifest, json);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("content identity", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The tampered manifest ran.");
    }

    private static void OpenRejectsUnsupportedFormat()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenFormatScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifestPath = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenFormatScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var manifest = PackageManifestIO.Read(manifestPath);
        manifest = manifest with { FormatVersion = PackageFormat.CurrentVersion + 1 };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(manifestPath, manifest);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifestPath, typeof(IHostEcho), host));
        Check(error.Message.Contains("Unsupported package format", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unsupported format ran.");
    }


    private static void OpenRejectsOversizedEntry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenSizeScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenSizeScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        using (var stream = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None))
            stream.SetLength(PackageValidator.MaximumAssemblyBytes + 1);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("size limits", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The oversized entry ran.");
    }

    private static void OpenRejectsFilesystemLink()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var package = Path.Combine(directory.Path, "package");
        Directory.CreateDirectory(package);
        var path = Path.Combine(package, "echo.dll");
        WriteScript(path, "HostContract.OpenLinkScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(package, "echo.dll", "HostContract.OpenLinkScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var target = Path.Combine(directory.Path, "target.dll");
        File.Move(path, target);
        File.CreateSymbolicLink(path, target);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("filesystem links", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The linked entry ran.");
    }

    private static void OpenRejectsDeepDirectory()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenDeepScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenDeepScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var nested = directory.Path;
        for (var level = 0; level < 17; level++)
        {
            nested = Path.Combine(nested, "n");
            Directory.CreateDirectory(nested);
        }

        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("nesting limit", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The deep directory ran.");
    }

    private static void OpenRejectsProducerKind()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenProducerScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifestPath = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenProducerScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var manifest = PackageManifestIO.Read(manifestPath);
        manifest = manifest with { Producer = manifest.Producer with { InputKind = "native" } };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(manifestPath, manifest);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifestPath, typeof(IHostEcho), host));
        Check(error.Message.Contains("Unsupported producer input kind", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unsupported producer ran.");
    }


    private static void OpenRejectsEscapingPath()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteManifestUnchecked(directory.Path, "../echo.dll");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The escaping entry ran.");
    }

    private static void OpenRejectsNonDll()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteManifestUnchecked(directory.Path, "echo.txt");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The non-DLL entry ran.");
    }

    private static void OpenRejectsUnlistedEntry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteListedManifest(directory.Path, "echo.dll", new string('a', 64), "other.dll", new string('b', 64));
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unlisted entry ran.");
    }

    private static void OpenRejectsMismatchedFileHash()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteListedManifest(directory.Path, "echo.dll", new string('a', 64), "echo.dll", new string('b', 64));
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The mismatched entry ran.");
    }

    private static void OpenRejectsEscapingDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteDependencyManifest(directory.Path, "../lib.dll", false);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The escaping dependency ran.");
    }

    private static void OpenRejectsExtraDiskFile()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.ExtraDiskScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.ExtraDiskScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        File.WriteAllBytes(Path.Combine(directory.Path, "extra.dll"), [1, 2, 3, 4]);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("missing or extra files", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra disk file ran.");
    }

    private static void OpenRejectsExtraFile()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteDependencyManifest(directory.Path, "lib.dll", true);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra file ran.");
    }

    private static void OpenAcceptsDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenDependencyScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        WriteScript(library, "HostContract.Library", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenDependencyScript.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "A matching dependency blocked the host call.");
    }

    private static void OpenCallsPrivateAssembly()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateAdd(library, "HostContract.PrivateAdd", foreign: false);
        WritePrivateCaller(entry, "HostContract.PrivateCaller", library, "HostContract.PrivateAdd.Math", "AddOne");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.PrivateCaller.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "The private method did not reach the host.");
    }

    private static void OpenRejectsPrivateForeignCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateAdd(library, "HostContract.PrivateForeign", foreign: true);
        WritePrivateCaller(entry, "HostContract.PrivateForeignCaller", library, "HostContract.PrivateForeign.Math", "AddOne");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.PrivateForeignCaller.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The private foreign call ran.");
    }


    private static void OpenPrivateCallsEntry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteMutual(entry, library, foreignEntry: false);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.CallbackEntry.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "The private method did not call back into the entry.");
    }

    private static void OpenRejectsEntryCallFromPrivate()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteMutual(entry, library, foreignEntry: true);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.CallbackEntry.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The entry BCL call ran.");
    }


    private static void OpenConstructsAuthorType()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteAuthorBox(path, frameworkNew: false);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.BoxScript.Script", ["Echo"]);
        session.Dispose();
        Check(host.Seen == 41, "The author object did not reach the host.");
    }

    private static void OpenRejectsFrameworkNew()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteAuthorBox(path, frameworkNew: true);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.BoxScript.Script", ["Echo"]));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The framework constructor ran.");
    }

    private static void OpenPrivateCallsPrivate()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var first = Path.Combine(directory.Path, "a.dll");
        var second = Path.Combine(directory.Path, "b.dll");
        WriteSecondAdd(second, "HostContract.LibB", foreign: false);
        WriteFirstPass(first, "HostContract.LibA", second, "HostContract.LibB.Math");
        WriteEntryCallsFirst(entry, "HostContract.TwoCaller", first, "HostContract.LibA.Math");
        var manifest = WriteTwoDependencies(directory.Path, entry, first, second, "HostContract.TwoCaller.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "The second private assembly did not reach the host.");
    }

    private static void OpenRejectsSecondPrivateCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var first = Path.Combine(directory.Path, "a.dll");
        var second = Path.Combine(directory.Path, "b.dll");
        WriteSecondAdd(second, "HostContract.ForeignLibB", foreign: true);
        WriteFirstPass(first, "HostContract.ForeignLibA", second, "HostContract.ForeignLibB.Math");
        WriteEntryCallsFirst(entry, "HostContract.ForeignTwoCaller", first, "HostContract.ForeignLibA.Math");
        var manifest = WriteTwoDependencies(directory.Path, entry, first, second, "HostContract.ForeignTwoCaller.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The second private BCL call ran.");
    }

    private static void WriteSecondAdd(string path, string assemblyName, bool foreign)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Math", TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var method = type.DefineMethod("AddOne", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = method.GetILGenerator();
        if (foreign)
        {
            il.Emit(OpCodes.Ldnull);
            il.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            il.Emit(OpCodes.Pop);
        }

        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Add);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteFirstPass(string path, string assemblyName, string secondPath, string secondType)
    {
        var second = Assembly.Load(File.ReadAllBytes(secondPath));
        var addOne = second.GetType(secondType, throwOnError: true)!.GetMethod("AddOne")!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Math", TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var method = type.DefineMethod("Through", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Call, addOne);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteEntryCallsFirst(string path, string assemblyName, string firstPath, string firstType)
    {
        var first = Assembly.Load(File.ReadAllBytes(firstPath));
        var through = first.GetType(firstType, throwOnError: true)!.GetMethod("Through")!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 40);
        il.Emit(OpCodes.Call, through);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static string WriteTwoDependencies(string directory, string entryPath, string firstPath, string secondPath, string entryType)
    {
        var entryHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(entryPath)));
        var firstHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(firstPath)));
        var secondHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(secondPath)));
        var empty = new string('c', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity("echo.dll", entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", "echo.dll", entryType, entryHash,
            [
                new PackageDependency("a.dll", ManagedAssemblyInspector.Inspect(File.ReadAllBytes(firstPath)).AssemblyName, firstHash),
                new PackageDependency("b.dll", ManagedAssemblyInspector.Inspect(File.ReadAllBytes(secondPath)).AssemblyName, secondHash)
            ],
            [new PackageFile("echo.dll", entryHash), new PackageFile("a.dll", firstHash), new PackageFile("b.dll", secondHash)],
            producer, "", typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static void OpenConstructsPrivateType()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateBox(library, "HostContract.PrivateBox", foreignCtor: false);
        WriteEntryConstructsBox(entry, "HostContract.PrivateBoxCaller", library, "HostContract.PrivateBox.Box");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.PrivateBoxCaller.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "The private object did not reach the host.");
    }

    private static void OpenRejectsPrivateConstructorCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WritePrivateBox(library, "HostContract.PrivateForeignBox", foreignCtor: true);
        WriteEntryConstructsBox(entry, "HostContract.PrivateForeignBoxCaller", library, "HostContract.PrivateForeignBox.Box");
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.PrivateForeignBoxCaller.Script");
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The private constructor call ran.");
    }

    private static void WritePrivateBox(string path, string assemblyName, bool foreignCtor)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var box = module.DefineType(assemblyName + ".Box", TypeAttributes.Public | TypeAttributes.Class);
        var field = box.DefineField("Value", typeof(int), FieldAttributes.Public);
        var ctor = box.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, new[] { typeof(int) });
        var il = ctor.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        if (foreignCtor)
        {
            il.Emit(OpCodes.Ldnull);
            il.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            il.Emit(OpCodes.Pop);
        }

        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Stfld, field);
        il.Emit(OpCodes.Ret);
        var get = box.DefineMethod("Get", MethodAttributes.Public, typeof(int), Type.EmptyTypes);
        var getIl = get.GetILGenerator();
        getIl.Emit(OpCodes.Ldarg_0);
        getIl.Emit(OpCodes.Ldfld, field);
        getIl.Emit(OpCodes.Ret);
        box.CreateType();
        builder.Save(path);
    }

    private static void WriteEntryConstructsBox(string path, string assemblyName, string libraryPath, string boxType)
    {
        var library = Assembly.Load(File.ReadAllBytes(libraryPath));
        var box = library.GetType(boxType, throwOnError: true)!;
        var ctor = box.GetConstructor(new[] { typeof(int) })!;
        var get = box.GetMethod("Get")!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 41);
        il.Emit(OpCodes.Newobj, ctor);
        il.Emit(OpCodes.Call, get);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteAuthorBox(string path, bool frameworkNew)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.BoxScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.BoxScript");
        var box = module.DefineType("HostContract.BoxScript.Box", TypeAttributes.Public | TypeAttributes.Class);
        var field = box.DefineField("Value", typeof(int), FieldAttributes.Public);
        var boxCtor = box.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, new[] { typeof(int) });
        var boxIl = boxCtor.GetILGenerator();
        boxIl.Emit(OpCodes.Ldarg_0);
        boxIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        boxIl.Emit(OpCodes.Ldarg_0);
        boxIl.Emit(OpCodes.Ldarg_1);
        boxIl.Emit(OpCodes.Stfld, field);
        boxIl.Emit(OpCodes.Ret);
        var get = box.DefineMethod("Get", MethodAttributes.Public, typeof(int), Type.EmptyTypes);
        var getIl = get.GetILGenerator();
        getIl.Emit(OpCodes.Ldarg_0);
        getIl.Emit(OpCodes.Ldfld, field);
        getIl.Emit(OpCodes.Ret);
        var type = module.DefineType("HostContract.BoxScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var il = start.GetILGenerator();
        if (frameworkNew)
        {
            il.Emit(OpCodes.Ldstr, "x");
            il.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
            il.Emit(OpCodes.Pop);
        }

        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 41);
        il.Emit(OpCodes.Newobj, boxCtor);
        il.Emit(OpCodes.Call, get);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        box.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteMutual(string entryPath, string libraryPath, bool foreignEntry)
    {
        WriteCallbackEntry(entryPath, "HostContract.CallbackEntry", null, foreign: false);
        var loaded = Assembly.Load(File.ReadAllBytes(entryPath));
        var adjust = loaded.GetType("HostContract.CallbackEntry.Script", throwOnError: true)!.GetMethod("Adjust")!;
        WriteHelperCallsAdjust(libraryPath, "HostContract.CallbackHelper", adjust);
        var helper = Assembly.Load(File.ReadAllBytes(libraryPath));
        var addOne = helper.GetType("HostContract.CallbackHelper.Math", throwOnError: true)!.GetMethod("AddOne")!;
        WriteCallbackEntry(entryPath, "HostContract.CallbackEntry", addOne, foreignEntry);
    }

    private static void WriteHelperCallsAdjust(string path, string assemblyName, MethodInfo adjust)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Math", TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var method = type.DefineMethod("AddOne", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Call, adjust);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Add);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteCallbackEntry(string path, string assemblyName, MethodInfo? helper, bool foreign)
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
        var adjust = type.DefineMethod("Adjust", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var adjustIl = adjust.GetILGenerator();
        if (foreign)
        {
            adjustIl.Emit(OpCodes.Ldnull);
            adjustIl.Emit(OpCodes.Call, typeof(string).GetMethod(nameof(string.IsNullOrEmpty), new[] { typeof(string) })!);
            adjustIl.Emit(OpCodes.Pop);
        }

        adjustIl.Emit(OpCodes.Ldarg_0);
        adjustIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, helper is null ? 1 : 40);
        if (helper is not null) il.Emit(OpCodes.Call, helper);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WritePrivateAdd(string path, string assemblyName, bool foreign)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Math", TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var method = type.DefineMethod("AddOne", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = method.GetILGenerator();
        if (foreign)
        {
            il.Emit(OpCodes.Ldstr, "x");
            il.Emit(OpCodes.Call, typeof(System.IO.File).GetMethod(nameof(System.IO.File.ReadAllText), new[] { typeof(string) })!);
            il.Emit(OpCodes.Pop);
        }

        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Add);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WritePrivateCaller(string path, string assemblyName, string libraryPath, string helperType, string helperMethod)
    {
        var helperAssembly = Assembly.Load(File.ReadAllBytes(libraryPath));
        var addOne = helperAssembly.GetType(helperType, throwOnError: true)!.GetMethod(helperMethod)!;
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
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), new[] { typeof(IHostEcho) });
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 40);
        il.Emit(OpCodes.Call, addOne);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void OpenRejectsMissingDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        WriteScript(entry, "HostContract.OpenMissingScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, null, "HostContract.OpenMissingScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("lib.dll", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The missing dependency ran.");
    }

    private static void OpenRejectsChangedDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenChangedScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        File.WriteAllBytes(library, [1, 2, 3, 4]);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenChangedScript.Script");
        File.WriteAllBytes(library, [1, 2, 3, 5]);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The changed dependency ran.");
    }

    private static void OpenRejectsOpaqueDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenOpaqueScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        File.WriteAllBytes(library, [1, 2, 3, 4]);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenOpaqueScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("PE", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The opaque dependency ran.");
    }

    private static void OpenRejectsSpoofedDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenSpoofDepScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        WriteScript(library, "System.IO", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenSpoofDepScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("spoofs", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The spoofed dependency ran.");
    }

    private static void OpenRejectsDependencyIdentity()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.IdentityScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        WriteScript(library, "HostContract.NotLib", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var manifestPath = WriteHashedDependency(directory.Path, entry, library, "HostContract.IdentityScript.Script");
        var manifest = PackageManifestIO.Read(manifestPath);
        manifest = manifest with
        {
            Dependencies = [manifest.Dependencies[0] with { AssemblyName = "Lib, Version=9.0.0.0, Culture=neutral, PublicKeyToken=null" }]
        };
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        PackageManifestIO.Write(manifestPath, manifest);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifestPath, typeof(IHostEcho), host));
        Check(error.Message.Contains("identity mismatch", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("lib.dll", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The mismatched dependency ran.");
    }


    private static string DeclaredDependencyName(string? libraryPath)
    {
        const string placeholder = "Lib, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
        if (libraryPath is null || !File.Exists(libraryPath)) return placeholder;
        try
        {
            return ManagedAssemblyInspector.Inspect(File.ReadAllBytes(libraryPath)).AssemblyName;
        }
        catch (Exception error) when (error is InvalidDataException or BadImageFormatException)
        {
            return placeholder;
        }
    }

    private static string WriteHashedDependency(string directory, string entryPath, string? libraryPath, string entryType)
    {
        var entryHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(entryPath)));
        var dependencyHash = libraryPath is null ? new string('b', 64) : Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(libraryPath)));
        var dependencyName = DeclaredDependencyName(libraryPath);
        var empty = new string('c', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity("echo.dll", entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", "echo.dll", entryType, entryHash,
            [new PackageDependency("lib.dll", dependencyName, dependencyHash)],
            [new PackageFile("echo.dll", entryHash), new PackageFile("lib.dll", dependencyHash)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteDependencyManifest(string directory, string dependencyPath, bool extraFile)
    {
        var entryHash = new string('a', 64);
        var dependencyHash = new string('b', 64);
        var empty = new string('c', 64);
        var files = extraFile
            ? new[] { new PackageFile("echo.dll", entryHash), new PackageFile("extra.dll", dependencyHash) }
            : new[] { new PackageFile("echo.dll", entryHash), new PackageFile(dependencyPath, dependencyHash) };
        var dependencies = extraFile ? Array.Empty<PackageDependency>() : new[] { new PackageDependency(dependencyPath, "Lib, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", dependencyHash) };
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity("echo.dll", entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", "echo.dll", "HostContract.OpenDependencyScript.Script", entryHash, dependencies, files, producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteListedManifest(string directory, string entryPath, string entryHash, string filePath, string fileHash)
    {
        var empty = new string('c', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(entryPath, entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", entryPath, "HostContract.OpenListScript.Script", entryHash, [], [new PackageFile(filePath, fileHash)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteManifestUnchecked(string directory, string entryPath)
    {
        var empty = new string('a', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(entryPath, empty)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", entryPath, "HostContract.OpenPathScript.Script", empty, [], [new PackageFile(entryPath, empty)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
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

    private static void RejectStaticFieldLoad()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "static.dll");
        WriteStaticFieldLoad(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.StaticScript.Script", ["Echo"]));
        Check(error.Message.Contains("Static field", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The static field load ran.");
    }

    private static void WriteStaticFieldLoad(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.StaticScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.StaticScript");
        var type = module.DefineType("HostContract.StaticScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldsfld, typeof(string).GetField(nameof(string.Empty))!);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorBox()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "box.dll");
        WriteAuthorBox(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.BoxScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author box ran.");
    }

    private static void WriteAuthorBox(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.BoxScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.BoxScript");
        var bomb = module.DefineType("HostContract.BoxScript.Bomb",
            TypeAttributes.Public | TypeAttributes.Sealed | TypeAttributes.SequentialLayout | TypeAttributes.BeforeFieldInit, typeof(ValueType));
        bomb.DefineField("value", typeof(int), FieldAttributes.Public);
        var type = module.DefineType("HostContract.BoxScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_0);
        il.Emit(OpCodes.Box, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorArray()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "array.dll");
        WriteAuthorArray(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ArrayScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author array ran.");
    }

    private static void WriteAuthorArray(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ArrayScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ArrayScript");
        var bomb = module.DefineType("HostContract.ArrayScript.Bomb", TypeAttributes.Public | TypeAttributes.Class);
        var type = module.DefineType("HostContract.ArrayScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Newarr, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorCast()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "cast.dll");
        WriteAuthorCast(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.CastScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author cast ran.");
    }

    private static void WriteAuthorCast(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.CastScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.CastScript");
        var bomb = module.DefineType("HostContract.CastScript.Bomb", TypeAttributes.Public | TypeAttributes.Class);
        var type = module.DefineType("HostContract.CastScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldnull);
        il.Emit(OpCodes.Castclass, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectFunctionPointer()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "fnptr.dll");
        WriteFunctionPointer(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.FnPtrScript.Script", ["Echo"]));
        Check(error.Message.Contains("Function pointers", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The function pointer ran.");
    }

    private static void WriteFunctionPointer(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.FnPtrScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.FnPtrScript");
        var type = module.DefineType("HostContract.FnPtrScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldftn, typeof(object).GetMethod(nameof(object.ToString), Type.EmptyTypes)!);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorCopy()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "copy.dll");
        WriteAuthorCopy(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.CopyScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author copy ran.");
    }

    private static void WriteAuthorCopy(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.CopyScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.CopyScript");
        var bomb = module.DefineType("HostContract.CopyScript.Bomb",
            TypeAttributes.Public | TypeAttributes.Sealed | TypeAttributes.SequentialLayout | TypeAttributes.BeforeFieldInit, typeof(ValueType));
        bomb.DefineField("value", typeof(int), FieldAttributes.Public);
        var type = module.DefineType("HostContract.CopyScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        var local = il.DeclareLocal(bomb);
        il.Emit(OpCodes.Ldloca, local);
        il.Emit(OpCodes.Ldloca, local);
        il.Emit(OpCodes.Cpobj, bomb);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectForeignFieldLoad()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "field.dll");
        WriteForeignField(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.FieldScript.Script", ["Echo"]));
        Check(error.Message.Contains("another type", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The foreign field ran.");
    }

    private static void WriteForeignField(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.FieldScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.FieldScript");
        var other = module.DefineType("HostContract.FieldScript.Other", TypeAttributes.Public | TypeAttributes.Class);
        var field = other.DefineField("item", typeof(int), FieldAttributes.Public);
        var type = module.DefineType("HostContract.FieldScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldnull);
        il.Emit(OpCodes.Ldfld, field);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        other.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorCatch()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "catch.dll");
        WriteAuthorCatch(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.CatchScript.Script", ["Echo"]));
        Check(error.Message.Contains("author catch type", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author catch ran.");

    }

    private static void WriteAuthorCatch(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.CatchScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.CatchScript");
        var bomb = module.DefineType("HostContract.CatchScript.Bomb", TypeAttributes.Public | TypeAttributes.Class, typeof(Exception));
        var bombCtor = bomb.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var bombIl = bombCtor.GetILGenerator();
        bombIl.Emit(OpCodes.Ldarg_0);
        bombIl.Emit(OpCodes.Call, typeof(Exception).GetConstructor(Type.EmptyTypes)!);
        bombIl.Emit(OpCodes.Ret);
        var type = module.DefineType("HostContract.CatchScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.BeginExceptionBlock();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.BeginCatchBlock(bomb);
        il.Emit(OpCodes.Pop);
        il.EndExceptionBlock();
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void CoreCatchStillRuns()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "core-catch.dll");
        WriteCoreCatch(path);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.CoreCatchScript.Script", ["Echo"]);
        session.Dispose();
        Check(host.Seen == 7, "A core catch blocked the host call.");
    }

    private static void RejectExceptionFilter()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "filter.dll");
        WriteExceptionFilter(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.FilterScript.Script", ["Echo"]));
        Check(error.Message.Contains("Exception filters", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The exception filter ran.");
    }

    private static void WriteCoreCatch(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.CoreCatchScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.CoreCatchScript");
        var type = module.DefineType("HostContract.CoreCatchScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.BeginExceptionBlock();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 7);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.BeginCatchBlock(typeof(Exception));
        il.Emit(OpCodes.Pop);
        il.EndExceptionBlock();
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteExceptionFilter(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.FilterScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.FilterScript");
        var type = module.DefineType("HostContract.FilterScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.BeginExceptionBlock();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.BeginExceptFilterBlock();
        il.Emit(OpCodes.Ldc_I4_0);
        il.BeginCatchBlock(null!);
        il.Emit(OpCodes.Pop);
        il.EndExceptionBlock();
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectGenericOnStart()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "generic.dll");
        WriteGenericOnStart(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.GenericScript.Script", ["Echo"]));
        Check(error.Message.Contains("must not be generic", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The generic OnStart ran.");
    }

    private static void WriteGenericOnStart(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.GenericScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.GenericScript");
        var type = module.DefineType("HostContract.GenericScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        start.DefineGenericParameters("T");
        var il = start.GetILGenerator();
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
