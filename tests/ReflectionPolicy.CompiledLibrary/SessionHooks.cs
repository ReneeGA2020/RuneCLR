using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;

namespace ReflectionPolicy.CompiledLibrary;

public interface IHostProbeBase
{
    int Hidden(int value);
}

public interface IHostProbe : IHostProbeBase
{
    int Echo(int value);
    int Denied(int value);
}

public interface IGenericProbeBase<T>
{
    int Hidden(int value);
}

public interface IGenericProbe<T> : IGenericProbeBase<T>
{
    int Echo(int value);
}

public static class SessionHooks
{
    public static ExecutionContext? Flow;
    public static int Effects;
    public static int LoadedEffects;
    public static int Route;
    public static string TargetPath = "";
    public static Func<AssemblyLoadContext, int> InterpreterPolicy = null!;
    public static void Capture() => Flow = ExecutionContext.Capture();
    public static void Effect() => Effects++;
    public static void ReflectEffect() => typeof(SessionHooks).GetMethod(nameof(Effect))!.Invoke(null, null);
    public static int Read() => 41;
    public static void MarkLoaded() => LoadedEffects++;
    public static bool LoadTarget(Assembly caller)
    {
        Assembly loaded;
        using var stream = new MemoryStream(File.ReadAllBytes(TargetPath));
        using var child = new TemporaryContext();
        loaded = Route switch
        {
            0 => Assembly.Load(File.ReadAllBytes(TargetPath)),
            1 => Assembly.Load(File.ReadAllBytes(TargetPath), null),
            2 => Assembly.LoadFrom(TargetPath),
            3 => Assembly.LoadFile(TargetPath),
            4 => AssemblyLoadContext.Default.LoadFromAssemblyPath(TargetPath),
            5 => AssemblyLoadContext.Default.LoadFromStream(stream),
            6 => child.Context.LoadFromAssemblyPath(TargetPath),
            7 => AssemblyLoadContext.Default.LoadFromNativeImagePath(TargetPath, TargetPath),
            8 => AssemblyLoadContext.Default.LoadFromAssemblyName(AssemblyName.GetAssemblyName(TargetPath)),
            9 => Assembly.Load(AssemblyName.GetAssemblyName(TargetPath)),
            10 => Assembly.Load(AssemblyName.GetAssemblyName(TargetPath).FullName),
            11 => Assembly.UnsafeLoadFrom(TargetPath),
            12 => Type.GetType("DynamicDependency.Payload, " + AssemblyName.GetAssemblyName(TargetPath).FullName, throwOnError: true)!.Assembly,
            _ => throw new ArgumentOutOfRangeException()
        };
        var context = AssemblyLoadContext.GetLoadContext(loaded)!;
        if (context != AssemblyLoadContext.GetLoadContext(caller) || !context.IsCollectible || InterpreterPolicy(context) != 1)
            throw new InvalidOperationException("A UGC load escaped its interpreter-required session.");
        return (int)loaded.GetType("DynamicDependency.Payload")!.GetMethod("ABC")!.Invoke(null, null)! == 41;
    }

    // Review-finding probes. Helpers run in the compiled host library so interpreted
    // author IL can exercise runtime-only surfaces without emitting DynamicMethod IL
    // directly from admitted author code.
    public static string DynamicFactoryResult = "";
    public static string StubFactoryResult = "";
    public static int RepeatedReflectionSum;
    public static int MethodInvokerSum;

    public static string ProbeDynamicFactory()
    {
        var factory = typeof(DynamicMethod).GetMethod(
            "CreateDelegateForInvoker", BindingFlags.Instance | BindingFlags.NonPublic);
        if (factory is null) return "unavailable";
        var method = CreateDynamicMethod();
        try
        {
            var created = (Delegate)factory.Invoke(method, new object?[] { typeof(Func<int>), null })!;
            return "escaped:" + ((Func<int>)created)();
        }
        catch (TargetInvocationException error)
        {
            return "refused:" + (error.InnerException?.GetType().Name ?? nameof(TargetInvocationException));
        }
        catch (Exception error)
        {
            return "refused:" + error.GetType().Name;
        }
    }

    public static string ProbeStubFactory()
    {
        var util = typeof(DynamicMethod).Assembly.GetType("System.Reflection.InvokerEmitUtil");
        var factory = util?.GetMethod("CreateStubDelegate", BindingFlags.Static | BindingFlags.NonPublic);
        if (factory is null) return "unavailable";
        try
        {
            var created = (Delegate)factory.Invoke(null, new object?[] { CreateDynamicMethod(), typeof(Func<int>) })!;
            return "escaped:" + ((Func<int>)created)();
        }
        catch (TargetInvocationException error)
        {
            return "refused:" + (error.InnerException?.GetType().Name ?? nameof(TargetInvocationException));
        }
        catch (Exception error)
        {
            return "refused:" + error.GetType().Name;
        }
    }

    public static void ProbeFactories()
    {
        DynamicFactoryResult = ProbeDynamicFactory();
        StubFactoryResult = ProbeStubFactory();
        var read = typeof(SessionHooks).GetMethod(nameof(Read))!;
        int sum = 0;
        for (int i = 0; i < 25; i++) sum += (int)read.Invoke(null, null)!;
        RepeatedReflectionSum = sum;
        var invoker = MethodInvoker.Create(read);
        int cached = 0;
        for (int i = 0; i < 25; i++) cached += (int)invoker.Invoke(null)!;
        MethodInvokerSum = cached;
    }

    private static DynamicMethod CreateDynamicMethod()
    {
        var method = new DynamicMethod("ReviewProbe", typeof(int), Type.EmptyTypes,
            typeof(SessionHooks).Module, skipVisibility: true);
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4, 77);
        il.Emit(OpCodes.Ret);
        return method;
    }

    public static string SeekableStreamResult = "";
    public static long SeekableStreamBytes;
    public static string NonseekableStreamResult = "";
    public static long NonseekableStreamBytes;

    public static void ProbeStreams()
    {
        (SeekableStreamResult, SeekableStreamBytes) = ProbeStream(seekable: true);
        (NonseekableStreamResult, NonseekableStreamBytes) = ProbeStream(seekable: false);
    }

    private static (string Result, long BytesRead) ProbeStream(bool seekable)
    {
        var stream = new SyntheticStream(seekable, 64L * 1024 * 1024);
        try
        {
            using (stream)
            {
                AssemblyLoadContext.Default.LoadFromStream(stream);
            }
            return ("loaded", stream.BytesRead);
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            return ("refused:" + error.GetType().Name, stream.BytesRead);
        }
    }

    public static string ProbeStreamOutsidePolicy(string path)
    {
        var context = new AssemblyLoadContext("stream-control-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        try
        {
            using var stream = new MemoryStream(File.ReadAllBytes(path));
            var assembly = context.LoadFromStream(stream);
            return assembly.GetName().Name ?? "unknown";
        }
        catch (Exception error)
        {
            return "failed:" + error.GetType().Name;
        }
        finally
        {
            context.Unload();
        }
    }

    private sealed class SyntheticStream : Stream
    {
        private readonly bool seekable;
        private readonly long length;
        private long position;

        internal SyntheticStream(bool seekable, long length)
        {
            this.seekable = seekable;
            this.length = length;
        }

        internal long BytesRead { get; private set; }
        public override bool CanRead => true;
        public override bool CanSeek => seekable;
        public override bool CanWrite => false;
        public override long Length => seekable ? length : throw new NotSupportedException("Length is unknown.");
        public override long Position
        {
            get => seekable ? position : throw new NotSupportedException("Length is unknown.");
            set
            {
                if (!seekable) throw new NotSupportedException("Length is unknown.");
                position = value;
            }
        }

        public override void Flush() { }

        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));

        public override int Read(Span<byte> buffer)
        {
            if (BytesRead >= length) return 0;
            int count = (int)Math.Min(buffer.Length, length - BytesRead);
            buffer[..count].Clear();
            BytesRead += count;
            position += count;
            return count;
        }

        public override long Seek(long offset, SeekOrigin origin)
        {
            if (!seekable) throw new NotSupportedException("Length is unknown.");
            long target = origin switch
            {
                SeekOrigin.Begin => offset,
                SeekOrigin.Current => position + offset,
                SeekOrigin.End => length + offset,
                _ => throw new ArgumentOutOfRangeException(nameof(origin))
            };
            if (target < 0) throw new IOException("Invalid seek.");
            position = target;
            return position;
        }

        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Write(ReadOnlySpan<byte> buffer) => throw new NotSupportedException();
    }

    public static string CrossSessionResult = "";
    public static AssemblyLoadContext? CrossSessionTarget;
    public static string CrossSessionPath = "";

    public static void ProbeCrossSession()
    {
        CrossSessionResult = "";
        try
        {
            CrossSessionTarget!.LoadFromAssemblyPath(CrossSessionPath);
            CrossSessionResult = "loaded";
        }
        catch (Exception error)
        {
            CrossSessionResult = "refused:" + error.GetType().Name;
        }
    }

    public static string ResolverEventResult = "";
    public static bool ResolverEventSeen;
    public static bool ResolverEventDenied;
    public static string ResolverPath = "";
    public static string ResolverDeniedPath = "";

    public static void ProbeResolverEvent()
    {
        ResolverEventSeen = false;
        ResolverEventDenied = false;
        ResolverEventResult = "";
        var context = new AssemblyLoadContext("host-resolver-depth-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        AssemblyLoadEventHandler handler = (_, args) =>
        {
            if (args.LoadedAssembly.GetName().Name != "System.Custom.UgcDependency") return;
            ResolverEventSeen = true;
            try
            {
                ResolverEventResult = Assembly.LoadFile(ResolverDeniedPath) is null ? "denied-null" : "allowed";
            }
            catch (Exception error)
            {
                ResolverEventDenied = true;
                ResolverEventResult = "denied:" + error.GetType().Name;
            }
        };
        AppDomain.CurrentDomain.AssemblyLoad += handler;
        try
        {
            context.LoadFromAssemblyPath(ResolverPath);
            if (!ResolverEventSeen) ResolverEventResult = "not-observed";
        }
        catch (Exception error)
        {
            if (!ResolverEventSeen) ResolverEventResult = "host-failed:" + error.GetType().Name;
        }
        finally
        {
            AppDomain.CurrentDomain.AssemblyLoad -= handler;
            context.Unload();
        }
    }

    public static bool ProbeResolverEventOutside(string safePath, string deniedPath)
    {
        bool allowed = false;
        var context = new AssemblyLoadContext("host-resolver-outside-" + Guid.NewGuid().ToString("N"), isCollectible: true);
        AssemblyLoadEventHandler handler = (_, args) =>
        {
            if (args.LoadedAssembly.GetName().Name != "System.Custom.UgcDependency") return;
            try { allowed = Assembly.LoadFile(deniedPath) is not null; }
            catch { allowed = false; }
        };
        AppDomain.CurrentDomain.AssemblyLoad += handler;
        try { context.LoadFromAssemblyPath(safePath); }
        catch { allowed = false; }
        finally
        {
            AppDomain.CurrentDomain.AssemblyLoad -= handler;
            context.Unload();
        }
        return allowed;
    }

    // Adjacent review findings: private DynamicMethod invoker and oversized symbols.
    public static string PrivateDynamicInvokerResult = "";
    public static string PreCreatedInvokerCreateResult = "";
    public static string PreCreatedInvokerResult = "";
    public static string OversizedSymbolsResult = "";
    public static string OversizedSymbolsOutsideResult = "";
    public static string ProbeAssemblyPath = "";
    private static MethodInvoker? s_preCreatedInvoker;

    private static DynamicMethod CreateOwnedDynamicMethod()
    {
        var method = new DynamicMethod("ReviewProbe", typeof(int), Type.EmptyTypes,
            typeof(SessionHooks), skipVisibility: true);
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4, 77);
        il.Emit(OpCodes.Ret);
        return method;
    }

    private static string ProbeError(Exception error)
    {
        var text = (error is TargetInvocationException && error.InnerException is not null ? error.InnerException : error).Message;
        if (text.Length > 200) text = text[..200];
        var type = error is TargetInvocationException && error.InnerException is not null
            ? error.InnerException.GetType().Name : error.GetType().Name;
        return "refused:" + type + ":" + text;
    }

    public static string ProbePrivateDynamicInvoker()
    {
        try
        {
            var descriptor = typeof(DynamicMethod).GetMethod(
                "GetMethodDescriptor", BindingFlags.Instance | BindingFlags.NonPublic);
            var ctor = typeof(MethodInvoker).GetConstructor(
                BindingFlags.Instance | BindingFlags.NonPublic, null, new[] { typeof(DynamicMethod) }, null);
            if (descriptor is null || ctor is null) return "unavailable";
            var method = CreateOwnedDynamicMethod();
            descriptor.Invoke(method, null);
            var invoker = (MethodInvoker)ctor.Invoke(new object?[] { method })!;
            return "escaped:" + (int)invoker.Invoke(null)!;
        }
        catch (Exception error)
        {
            return ProbeError(error);
        }
    }

    public static string CreatePreCreatedDynamicInvoker()
    {
        try
        {
            var descriptor = typeof(DynamicMethod).GetMethod(
                "GetMethodDescriptor", BindingFlags.Instance | BindingFlags.NonPublic);
            var ctor = typeof(MethodInvoker).GetConstructor(
                BindingFlags.Instance | BindingFlags.NonPublic, null, new[] { typeof(DynamicMethod) }, null);
            if (descriptor is null || ctor is null) return "unavailable";
            var method = CreateOwnedDynamicMethod();
            descriptor.Invoke(method, null);
            s_preCreatedInvoker = (MethodInvoker)ctor.Invoke(new object?[] { method })!;
            return "created";
        }
        catch (Exception error)
        {
            return ProbeError(error);
        }
    }

    public static string ProbePreCreatedDynamicInvoker()
    {
        if (s_preCreatedInvoker is null) return "unavailable";
        try
        {
            return "escaped:" + (int)s_preCreatedInvoker.Invoke(null)!;
        }
        catch (Exception error)
        {
            return ProbeError(error);
        }
    }

    public static string ProbeOversizedSymbols()
    {
        try
        {
            var assembly = File.ReadAllBytes(ProbeAssemblyPath);
            var symbols = new byte[33 * 1024 * 1024];
            Assembly.Load(assembly, symbols);
            return "loaded";
        }
        catch (Exception error)
        {
            return "threw:" + error.GetType().Name + ":" + error.Message;
        }
    }

    public static string ProbeOversizedSymbolsOutside()
    {
        try
        {
            var assembly = File.ReadAllBytes(ProbeAssemblyPath);
            var symbols = new byte[33 * 1024 * 1024];
            Assembly.Load(assembly, symbols);
            return "loaded";
        }
        catch (Exception error)
        {
            return "threw:" + error.GetType().Name + ":" + error.Message;
        }
    }

    // HostContractSession policy probes. The author entry calls these shared
    // helpers so ctor/OnStart/later callbacks exercise reflection under the
    // session scope without emitting reflection IL by hand.
    public static IHostProbe? HostProbe;
    public static bool HostDeniedReflectionDenied;
    public static bool HostEffectDenied;
    public static void HostCtorProbe()
    {
        var read = typeof(SessionHooks).GetMethod(nameof(Read))!;
        if ((int)read.Invoke(null, null)! != 41) throw new InvalidOperationException("Host ctor reflection failed.");
        Capture();
    }

    public static void HostStartProbe(IHostProbe host)
    {
        HostProbe = host;
        var echo = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!;
        if ((int)echo.Invoke(host, new object[] { 2 })! != 2)
            throw new InvalidOperationException("Host OnStart reflection failed.");
        if ((int)ReflectionLibrary.Call(echo, host, new object[] { 3 })! != 3)
            throw new InvalidOperationException("Compiled-library host reflection failed.");
        var denied = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Denied))!;
        bool deniedRefused = false;
        try { denied.Invoke(host, new object[] { 4 }); }
        catch (InvalidOperationException) { deniedRefused = true; }
        if (!deniedRefused) throw new InvalidOperationException("Denied host target executed under the policy.");
        HostDeniedReflectionDenied = true;

        var effect = typeof(SessionHooks).GetMethod(nameof(Effect))!;
        bool effectRefused = false;
        try { effect.Invoke(null, null); }
        catch (InvalidOperationException) { effectRefused = true; }
        if (!effectRefused) throw new InvalidOperationException("Denied shared target executed under the policy.");
        HostEffectDenied = true;

        Capture();
    }

    public static void HostLaterProbe(IHostProbe host)
    {
        var echo = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!;
        if ((int)echo.Invoke(host, new object[] { 6 })! != 6)
            throw new InvalidOperationException("Host later reflection failed.");
        Capture();
    }

    public static void HostTickProbe(int value)
    {
        var echo = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!;
        if ((int)echo.Invoke(HostProbe, new object[] { value })! != value)
            throw new InvalidOperationException("Host int callback reflection failed.");
    }

    public static int HostReturnProbe(int value)
    {
        var echo = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!;
        return (int)echo.Invoke(HostProbe, new object[] { value })! + 1;
    }

    public static bool HostHiddenReflectionDenied;
    public static bool GenericHiddenReflectionDenied;
    public static bool GenericBaseAliasDenied;
    public static bool GenericBaseObjectControlSucceeded;
    public static bool GenericBaseObjectContractDenied;
    public static MethodInfo? GenericBaseAliasMethod;
    public static MethodInfo? GenericBaseObjectMethod;
    public static bool GenericBaseReflectionDenied;
    public static bool HostPrivateWrapperDenied;
    public static bool HostDynamicAuthorDenied;
    public static bool HostBaseAliasDenied;
    public static bool HostImplementationAliasDenied;
    public static bool HostMessageRead;
    public static byte[]? DynamicAuthorBytes;

    public static void HostGenericBaseAliasProbe(IGenericProbe<int> host)
    {
        bool denied = false;
        try { GenericBaseAliasMethod!.Invoke(host, new object[] { 74 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Exact-parameter nonvirtual base alias executed.");
        GenericBaseAliasDenied = true;
    }

    public static void HostGenericBaseObjectControlProbe(IGenericProbe<int> host)
    {
        bool executed = false;
        try
        {
            object? result = GenericBaseObjectMethod!.Invoke(host, new object[] { 75 });
            if (result is not int number || number != 75)
                throw new InvalidOperationException("Base overload control returned an unexpected value.");
            executed = true;
        }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException)
        {
            throw new InvalidOperationException("Non-alias base Hidden(object) was incorrectly denied.", error);
        }
        GenericBaseObjectControlSucceeded = executed;

        var contractHidden = typeof(IGenericProbeBase<int>).GetMethod(nameof(IGenericProbeBase<int>.Hidden))!;
        bool denied = false;
        try { contractHidden.Invoke(host, new object[] { 76 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Contract Hidden(int) alias executed.");
        GenericBaseObjectContractDenied = true;
    }

    public static void HostGenericReflectProbe(IGenericProbe<int> host)
    {
        var hidden = typeof(IGenericProbeBase<int>).GetMethod(nameof(IGenericProbeBase<int>.Hidden))!;
        bool denied = false;
        try { hidden.Invoke(host, new object[] { 71 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Constructed generic unlisted host target executed.");
        GenericHiddenReflectionDenied = true;
        var echo = typeof(IGenericProbe<int>).GetMethod(nameof(IGenericProbe<int>.Echo))!;
        if ((int)echo.Invoke(host, new object[] { 72 })! != 72)
            throw new InvalidOperationException("Allowed constructed generic target failed.");
        Capture();
    }

    public static void HostGenericBaseReflectProbe(IGenericProbe<int> host)
    {
        var hidden = typeof(IGenericProbeBase<int>).GetMethod(nameof(IGenericProbeBase<int>.Hidden))!;
        bool denied = false;
        try { hidden.Invoke(host, new object[] { 73 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Inherited generic unlisted host target executed.");
        GenericBaseReflectionDenied = true;
    }

    public static void HostReflectHiddenProbe(IHostProbe host)
    {
        var hidden = typeof(IHostProbeBase).GetMethod(nameof(IHostProbeBase.Hidden))!;
        bool denied = false;
        try { hidden.Invoke(host, new object[] { 61 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Reflected unlisted host target executed.");
        HostHiddenReflectionDenied = true;
        var echo = typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!;
        if ((int)echo.Invoke(host, new object[] { 62 })! != 62)
            throw new InvalidOperationException("Allowed reflected host target failed.");
        Capture();
    }

    public static void HostPrivateWrapperProbe(IHostProbe host, Type entryType)
    {
        var wrapper = entryType.GetMethod("Wrapper", BindingFlags.NonPublic | BindingFlags.Static)!;
        bool denied = false;
        try { wrapper.Invoke(null, new object[] { host }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { denied = true; }
        if (!denied) throw new InvalidOperationException("Private author wrapper reached an unlisted host target.");
        HostPrivateWrapperDenied = true;
    }

    public static void HostDynamicAuthorProbe(IHostProbe host)
    {
        bool denied = false;
        try
        {
            var assembly = Assembly.Load(DynamicAuthorBytes!);
            var call = assembly.GetType("System.Custom.DynamicAuthor.Call", throwOnError: true)!
                .GetMethod("Hidden", BindingFlags.Public | BindingFlags.Static)!;
            call.Invoke(null, new object[] { host });
        }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException)
        {
            denied = true;
        }
        if (!denied) throw new InvalidOperationException("Dynamically loaded author helper reached an unlisted host target.");
        HostDynamicAuthorDenied = true;
    }

    public static void HostAliasProbe(IHostProbe host)
    {
        var baseHidden = typeof(IHostProbeBase).GetMethod(nameof(IHostProbeBase.Hidden))!;
        bool baseDenied = false;
        try { baseHidden.Invoke(host, new object[] { 63 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { baseDenied = true; }
        if (!baseDenied) throw new InvalidOperationException("Base-interface unlisted host target executed.");
        HostBaseAliasDenied = true;

        var implementation = host.GetType().GetMethod(nameof(IHostProbe.Hidden))!;
        bool implementationDenied = false;
        try { implementation.Invoke(host, new object[] { 64 }); }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException) { implementationDenied = true; }
        if (!implementationDenied) throw new InvalidOperationException("Implementation alias unlisted host target executed.");
        HostImplementationAliasDenied = true;
    }

    public static void HostThrow() => throw new HostMessageException();

    public sealed class HostMessageException : Exception
    {
        public override string Message
        {
            get
            {
                HostMessageRead = true;
                return "author-failed";
            }
        }
    }

    private sealed class TemporaryContext : IDisposable
    {
        internal AssemblyLoadContext Context = new("ugc-requested-context", isCollectible: true);
        public void Dispose() => Context.Unload();
    }
}
