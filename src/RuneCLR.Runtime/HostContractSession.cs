using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
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
    private byte[]? _image;
    private Dictionary<string, byte[]>? _images;
    private string? _entryTypeName;
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
        RequireListedEntry(manifest);
        var directory = Path.GetDirectoryName(Path.GetFullPath(manifestPath))
            ?? throw new InvalidDataException("The package manifest requires a directory.");
        RequireNoExtraFiles(directory, manifest);
        var privateAssemblies = new List<PrivateImage>();
        var privateNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var dependency in manifest.Dependencies)
        {
            var image = ReadPrivateImage(directory, dependency.Path, dependency.Sha256, dependency.AssemblyName);
            if (!privateNames.Add(image.Name))
                throw new InvalidDataException("Duplicate private dependency identity: " + image.Name + ".");
            privateAssemblies.Add(image);
        }

        var entry = ResolveEntry(directory, manifest.EntryAssembly);
        RequireFileHash(directory, manifest.EntryAssembly, manifest.EntrySha256);
        return new HostContractSession(contract, instance, entry, manifest.EntryType, manifest.AllowedMethods, privateAssemblies);
    }

    private static void RequireNoExtraFiles(string directory, PackageManifest manifest)
    {
        var listed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var file in manifest.Files)
        {
            if (file is null || string.IsNullOrWhiteSpace(file.Path) || !listed.Add(file.Path))
                throw new InvalidDataException("The package contains missing or extra files.");
        }

        foreach (var path in Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories))
        {
            var full = Path.GetFullPath(path);
            var manifestPath = Path.GetFullPath(Path.Combine(directory, PackageFormat.ManifestFileName));
            if (string.Equals(full, manifestPath, StringComparison.OrdinalIgnoreCase))
                continue;
            var relative = Path.GetRelativePath(directory, full).Replace(Path.DirectorySeparatorChar, '/');
            if (!listed.Contains(relative))
                throw new InvalidDataException("The package contains missing or extra files.");
        }
    }

    private static void RequireListedEntry(PackageManifest manifest)
    {
        const string failure = "The file list must exactly match the entry and private dependencies.";
        if (manifest.Files is null || manifest.Dependencies is null)
            throw new InvalidDataException(failure);
        RequireRelativeDll(manifest.EntryAssembly);
        var expected = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            [manifest.EntryAssembly] = manifest.EntrySha256
        };
        foreach (var dependency in manifest.Dependencies)
        {
            if (dependency is null || string.IsNullOrWhiteSpace(dependency.Sha256) || !expected.TryAdd(dependency.Path, dependency.Sha256))
                throw new InvalidDataException(failure);
            RequireRelativeDll(dependency.Path);
        }

        if (manifest.Files.Length != expected.Count)
            throw new InvalidDataException(failure);
        foreach (var file in manifest.Files)
        {
            if (file is null || !expected.Remove(file.Path, out var hash) ||
                !string.Equals(file.Sha256, hash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(failure);
        }
    }

    private static void RequireRelativeDll(string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.IndexOf((char)92) >= 0 || relative.IndexOf((char)58) >= 0 ||
            relative.Split('/').Any(part => part is "" or "." or "..") ||
            !relative.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package content paths must be canonical relative DLL paths using forward slashes.");
    }

    private static PrivateImage ReadPrivateImage(string directory, string relative, string expected, string declaredIdentity)
    {
        var bytes = ReadHashed(directory, relative, expected);
        var info = ManagedAssemblyInspector.Inspect(bytes);
        if (ReservedAssembly(info.SimpleName))
            throw new InvalidDataException("Author assembly '" + info.SimpleName + "' spoofs a framework or host assembly name.");
        if (string.IsNullOrWhiteSpace(declaredIdentity) ||
            !string.Equals(info.AssemblyName, declaredIdentity, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Dependency metadata identity mismatch: " + relative + ".");
        return new PrivateImage(info.SimpleName, bytes);
    }

    private static void RequireFileHash(string directory, string relative, string expected) =>
        ReadHashed(directory, relative, expected);

    private static byte[] ReadHashed(string directory, string relative, string expected)
    {
        var path = ResolveEntry(directory, relative);
        if (!File.Exists(path))
            throw new InvalidDataException("Package file hash mismatch: " + relative + ".");
        var bytes = File.ReadAllBytes(path);
        var actual = Convert.ToHexString(SHA256.HashData(bytes));
        if (!string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package file hash mismatch: " + relative + ".");
        return bytes;
    }

    private static string ResolveEntry(string directory, string relative)
    {
        RequireRelativeDll(relative);
        var full = Path.GetFullPath(Path.Combine(directory, relative.Replace('/', Path.DirectorySeparatorChar)));
        var root = Path.GetFullPath(directory + Path.DirectorySeparatorChar);
        if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package content paths must be canonical relative DLL paths using forward slashes.");
        return full;
    }

    public HostContractSession(Type contract, object instance, string assemblyPath, string entryTypeName, IReadOnlyCollection<string> allowedMethods)
        : this(contract, instance, assemblyPath, entryTypeName, allowedMethods, Array.Empty<PrivateImage>())
    {
    }

    private HostContractSession(Type contract, object instance, string assemblyPath, string entryTypeName,
        IReadOnlyCollection<string> allowedMethods, IReadOnlyList<PrivateImage> privateAssemblies)
    {
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(instance);
        ArgumentException.ThrowIfNullOrWhiteSpace(assemblyPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(entryTypeName);
        ArgumentNullException.ThrowIfNull(allowedMethods);
        ArgumentNullException.ThrowIfNull(privateAssemblies);
        if (!contract.IsInterface || !contract.IsInstanceOfType(instance))
            throw new InvalidOperationException("The host contract must be the interface implemented by the supplied instance.");

        var privateNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var images = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
        var contractName = contract.Assembly.GetName().Name ?? "";
        foreach (var image in privateAssemblies)
        {
            if (string.Equals(image.Name, contractName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Author assembly '" + image.Name + "' duplicates the host contract assembly.");
            if (!privateNames.Add(image.Name))
                throw new InvalidDataException("Duplicate private dependency identity: " + image.Name + ".");
            images.Add(image.Name, image.Bytes);
        }

        _context = new HostContractLoadContext(privateAssemblies);
        ContextReference = new WeakReference(_context, trackResurrection: true);
        try
        {
            var bytes = File.ReadAllBytes(Path.GetFullPath(assemblyPath));
            RequireCoreCatchTypes(bytes, entryTypeName, ".ctor");
            RequireCoreCatchTypes(bytes, entryTypeName, "OnStart");
            var info = ManagedAssemblyInspector.Inspect(bytes);
            if (ReservedAssembly(info.SimpleName))
                throw new InvalidDataException("Author assembly '" + info.SimpleName + "' spoofs a framework or host assembly name.");
            if (privateNames.Contains(info.SimpleName))
                throw new InvalidDataException("Duplicate private dependency identity: " + info.SimpleName + ".");
            RequireApprovedReferences(info, contract, privateNames);
            var authorNames = new HashSet<string>(privateNames, StringComparer.OrdinalIgnoreCase) { info.SimpleName };
            foreach (var image in privateAssemblies)
                RequireApprovedReferences(ManagedAssemblyInspector.Inspect(image.Bytes), contract, authorNames);
            images.Add(info.SimpleName, bytes);
            using var stream = new MemoryStream(bytes, writable: false);
            var assembly = _context.LoadFromStream(stream);
            var entry = assembly.GetType(entryTypeName, throwOnError: false);
            var start = RequireOnStart(entry, contract);
            var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
            RequireContractCalls(start, contract, allowed, "OnStart calls a method that is not a host contract member.", images);
            RequireLaterCallbacks(entry!, contract, allowed, images);
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
                _image = bytes;
                _images = images;
                _entryTypeName = entryTypeName;
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
        RequireCoreCatchTypes(_image!, _entryTypeName!, methodName);
        const string failure = "The callback calls a method that is not a host contract member.";
        RequireContractCalls(method, _contract, _allowedMethods, failure, _images!);
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

    public void Invoke(string methodName, int value)
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
        var takesInt = parameters.Length == 1 && parameters[0].ParameterType == typeof(int);
        var takesHostAndInt = parameters.Length == 2 && parameters[0].ParameterType == _contract && parameters[1].ParameterType == typeof(int);
        if (method is null || method.ReturnType != typeof(void) || method.IsGenericMethod || (!takesInt && !takesHostAndInt))
            throw new InvalidOperationException("The callback must be one public void method with one int parameter or the host contract and one int.");
        RequireCoreCatchTypes(_image!, _entryTypeName!, methodName);
        const string failure = "The callback calls a method that is not a host contract member.";
        RequireContractCalls(method, _contract, _allowedMethods, failure, _images!);
        _invoking = true;
        try
        {
            try
            {
                method.Invoke(_script, takesHostAndInt ? [_host, value] : [value]);
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

    public int InvokeInt(string methodName, int value)
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
        var takesInt = parameters.Length == 1 && parameters[0].ParameterType == typeof(int);
        var takesHostAndInt = parameters.Length == 2 && parameters[0].ParameterType == _contract && parameters[1].ParameterType == typeof(int);
        if (method is null || method.ReturnType != typeof(int) || method.IsGenericMethod || (!takesInt && !takesHostAndInt))
            throw new InvalidOperationException("The callback must be one public int method with one int parameter or the host contract and one int.");
        RequireCoreCatchTypes(_image!, _entryTypeName!, methodName);
        const string failure = "The callback calls a method that is not a host contract member.";
        RequireContractCalls(method, _contract, _allowedMethods, failure, _images!);
        _invoking = true;
        try
        {
            object? result;
            try
            {
                result = method.Invoke(_script, takesHostAndInt ? [_host, value] : [value]);
            }
            catch (Exception exception)
            {
                throw HostFailure(exception);
            }

            if (result is not int number)
                throw new InvalidOperationException("The callback must return an int.");
            return number;
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
        _image = null;
        _images = null;
        _entryTypeName = null;
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
        if (entry.TypeInitializer is not null)
            throw new InvalidOperationException("The script entry must not declare a type initializer.");
        RequireOnlyObjectConstructor(constructors[0]);

        var starts = entry.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(method => method.Name == "OnStart")
            .ToArray();
        if (starts.Length != 1)
            throw new InvalidOperationException("The script entry must declare exactly one public instance method named OnStart.");

        if (starts[0].IsGenericMethod)
            throw new InvalidOperationException("OnStart must not be generic.");
        var parameters = starts[0].GetParameters();
        if (parameters.Length != 1 || parameters[0].ParameterType != contract)
            throw new InvalidOperationException("OnStart must take exactly one parameter of the host contract interface.");
        return starts[0];
    }

    private static void RequireApprovedReferences(ManagedAssemblyInfo info, Type contract, IReadOnlySet<string> privateNames)
    {
        var contractName = contract.Assembly.GetName().Name;
        foreach (var reference in info.References)
        {
            string? simple;
            try { simple = new AssemblyName(reference).Name; }
            catch (Exception exception) when (exception is ArgumentException or FileLoadException)
            {
                throw new InvalidDataException("A referenced assembly identity is invalid.", exception);
            }

            if (simple is "System.Runtime" or "System.Private.CoreLib" or "netstandard") continue;
            if (string.Equals(simple, contractName, StringComparison.OrdinalIgnoreCase)) continue;
            if (simple is not null && privateNames.Contains(simple)) continue;
            throw new InvalidDataException("Assembly '" + simple + "' is not approved.");
        }
    }

    private static bool ReservedAssembly(string name) =>
        name.Equals("mscorlib", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("netstandard", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("System", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("Microsoft", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("RuneCLR", StringComparison.OrdinalIgnoreCase) ||
        name.StartsWith("System.", StringComparison.OrdinalIgnoreCase) ||
        name.StartsWith("Microsoft.", StringComparison.OrdinalIgnoreCase) ||
        name.StartsWith("RuneCLR.", StringComparison.OrdinalIgnoreCase);

    private static void RequireOnlyObjectConstructor(ConstructorInfo constructor)
    {
        const string failure = "The script constructor calls a method that is not Object..ctor.";
        var body = constructor.GetMethodBody() ?? throw new InvalidOperationException(failure);
        var il = body.GetILAsByteArray() ?? throw new InvalidOperationException(failure);
        var index = 0;
        var sawBase = false;
        while (index < il.Length)
        {
            var operation = ReadOpCode(il, ref index, failure);
            RejectUnsafe(operation);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
            {
                var token = ReadInt32(il, ref index, failure);
                MethodBase? called;
                try { called = constructor.Module.ResolveMethod(token); }
                catch (ArgumentException) { called = null; }
                if (called?.DeclaringType != typeof(object) || called.Name != ".ctor")
                    throw new InvalidOperationException(failure);
                sawBase = true;
            }
            else if (operation.Value == OpCodes.Newobj.Value || operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Jmp.Value)
            {
                throw new InvalidOperationException(failure);
            }
            else if (HasForeignTypeOperand(operation))
            {
                RejectForeignBox(constructor.Module, il, ref index);
            }
            else if (IsInstanceField(operation))
            {
                RejectForeignField(constructor.Module, constructor.DeclaringType, il, ref index);
            }
            else
            {
                SkipOperand(operation, il, ref index, failure);
            }
        }

        if (!sawBase) throw new InvalidOperationException(failure);
    }

    private static void RequireLaterCallbacks(Type entry, Type contract, HashSet<string> allowed, IReadOnlyDictionary<string, byte[]> images)
    {
        foreach (var method in entry.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        {
            if (method.Name == "OnStart" || !IsSupportedCallback(method, contract)) continue;
            RequireContractCalls(method, contract, allowed,
                "The callback " + method.Name + " calls a method that is not a host contract member.", images);
        }
    }

    private static bool IsSupportedCallback(MethodInfo method, Type contract)
    {
        if (method.IsGenericMethod) return false;
        var parameters = method.GetParameters();
        var returnsVoid = method.ReturnType == typeof(void);
        var returnsInt = method.ReturnType == typeof(int);
        if (!returnsVoid && !returnsInt) return false;
        if (parameters.Length == 0) return returnsVoid;
        if (parameters.Length == 1)
        {
            if (parameters[0].ParameterType == typeof(int)) return true;
            return returnsVoid && parameters[0].ParameterType == contract;
        }

        return parameters.Length == 2 && parameters[0].ParameterType == contract && parameters[1].ParameterType == typeof(int);
    }

    private static void RequireContractCalls(MethodInfo method, Type contract, HashSet<string> allowedMethods, string failure, IReadOnlyDictionary<string, byte[]> images)
    {
        WalkCalls(method, contract, allowedMethods, failure, images, new HashSet<MethodBase>());
    }

    private static void WalkCalls(MethodBase method, Type contract, HashSet<string> allowedMethods, string failure,
        IReadOnlyDictionary<string, byte[]> images, HashSet<MethodBase> seen)
    {
        if (!seen.Add(method)) return;
        var owner = method.DeclaringType?.Assembly.GetName().Name;
        if (owner is null || !images.TryGetValue(owner, out var image))
            throw new InvalidOperationException(failure);
        RequireCoreCatchTypes(image, method.DeclaringType!.FullName ?? method.Name, method.Name);

        var body = method.GetMethodBody() ?? throw new InvalidOperationException(failure);
        var il = body.GetILAsByteArray() ?? throw new InvalidOperationException(failure);
        var index = 0;
        while (index < il.Length)
        {
            var operation = ReadOpCode(il, ref index, failure);
            RejectUnsafe(operation);
            if (operation.Value == OpCodes.Call.Value || operation.Value == OpCodes.Callvirt.Value)
            {
                var token = ReadInt32(il, ref index, failure);
                MethodBase? called;
                try { called = method.Module.ResolveMethod(token); }
                catch (ArgumentException) { called = null; }
                if (method.IsConstructor && called?.DeclaringType == typeof(object) && called.Name == ".ctor" && !called.IsGenericMethod)
                    continue;
                if (IsAllowedContractCall(called, contract, allowedMethods))
                    continue;
                if (called is MethodInfo author && IsAuthorAssembly(author, images))
                {
                    if (author.IsGenericMethod || author.DeclaringType!.TypeInitializer is not null)
                        throw new InvalidOperationException(failure);
                    WalkCalls(author, contract, allowedMethods, failure, images, seen);
                    continue;
                }

                throw RejectedCall(failure, called);
            }
            else if (operation.Value == OpCodes.Newobj.Value)
            {
                var token = ReadInt32(il, ref index, failure);
                MethodBase? created;
                try { created = method.Module.ResolveMethod(token); }
                catch (ArgumentException) { created = null; }
                if (created is ConstructorInfo authorCtor && IsAuthorAssembly(authorCtor, images))
                {
                    if (authorCtor.IsGenericMethod || authorCtor.DeclaringType!.TypeInitializer is not null)
                        throw new InvalidOperationException(failure);
                    WalkCalls(authorCtor, contract, allowedMethods, failure, images, seen);
                    continue;
                }

                throw RejectedCall(failure, created);
            }
            else if (operation.Value == OpCodes.Calli.Value || operation.Value == OpCodes.Jmp.Value)
            {
                throw new InvalidOperationException(failure);
            }
            else if (HasForeignTypeOperand(operation))
            {
                RejectForeignBox(method.Module, il, ref index);
            }
            else if (IsInstanceField(operation))
            {
                RejectForeignField(method.Module, method.DeclaringType, il, ref index);
            }
            else
            {
                SkipOperand(operation, il, ref index, failure);
            }
        }
    }

    private static InvalidOperationException RejectedCall(string failure, MethodBase? called)
    {
        var type = called?.DeclaringType;
        if (type is null || string.IsNullOrEmpty(called?.Name))
            return new InvalidOperationException(failure);
        var typeName = type.FullName ?? type.Name;
        return new InvalidOperationException(failure + " " + typeName + "." + called!.Name);
    }

    private static bool IsAllowedContractCall(MethodBase? called, Type contract, HashSet<string> allowedMethods) =>
        called?.DeclaringType == contract && !called.IsGenericMethod && allowedMethods.Contains(called.Name);

    private static bool IsAuthorAssembly(MethodBase method, IReadOnlyDictionary<string, byte[]> images)
    {
        var name = method.DeclaringType?.Assembly.GetName().Name;
        return name is not null && images.ContainsKey(name);
    }

    private static void RequireCoreCatchTypes(byte[] image, string typeFullName, string methodName)
    {
        using var pe = new PEReader(ImmutableArray.CreateRange(image));
        var reader = pe.GetMetadataReader();
        foreach (var typeHandle in reader.TypeDefinitions)
        {
            var type = reader.GetTypeDefinition(typeHandle);
            var typeName = reader.GetString(type.Name);
            var typeNamespace = reader.GetString(type.Namespace);
            var full = typeNamespace.Length == 0 ? typeName : typeNamespace + "." + typeName;
            if (full != typeFullName && typeName != typeFullName) continue;
            foreach (var methodHandle in type.GetMethods())
            {
                var definition = reader.GetMethodDefinition(methodHandle);
                if (reader.GetString(definition.Name) != methodName || definition.RelativeVirtualAddress == 0) continue;
                foreach (var region in pe.GetMethodBody(definition.RelativeVirtualAddress).ExceptionRegions)
                {
                    if (region.Kind == ExceptionRegionKind.Filter)
                        throw new InvalidOperationException("Exception filters are unsupported.");
                    if (region.Kind != ExceptionRegionKind.Catch) continue;
                    var assembly = CatchAssembly(reader, region.CatchType);
                    if (assembly is not ("System.Private.CoreLib" or "System.Runtime"))
                        throw new InvalidOperationException("An author catch type is unsupported.");
                }
            }
        }
    }

    private static string CatchAssembly(MetadataReader reader, EntityHandle handle)
    {
        if (handle.Kind != HandleKind.TypeReference) return "";
        var type = reader.GetTypeReference((TypeReferenceHandle)handle);
        if (type.ResolutionScope.Kind != HandleKind.AssemblyReference) return "";
        var assembly = reader.GetAssemblyReference((AssemblyReferenceHandle)type.ResolutionScope);
        return reader.GetString(assembly.Name);
    }

    private static bool IsInstanceField(OpCode operation) =>
        operation.Value == OpCodes.Ldfld.Value || operation.Value == OpCodes.Stfld.Value || operation.Value == OpCodes.Ldflda.Value;

    private static void RejectForeignField(Module module, Type? owner, byte[] il, ref int index)
    {
        const string failure = "A field of another type is unsupported.";
        var token = ReadInt32(il, ref index, failure);
        FieldInfo? field;
        try { field = module.ResolveField(token); }
        catch (ArgumentException) { field = null; }
        if (field?.DeclaringType != owner)
            throw new InvalidOperationException(failure);
    }

    private static bool HasForeignTypeOperand(OpCode operation) =>
        operation.Value == OpCodes.Box.Value || operation.Value == OpCodes.Newarr.Value ||
        operation.Value == OpCodes.Initobj.Value || operation.Value == OpCodes.Castclass.Value ||
        operation.Value == OpCodes.Isinst.Value || operation.Value == OpCodes.Unbox.Value ||
        operation.Value == OpCodes.Unbox_Any.Value || operation.Value == OpCodes.Ldobj.Value ||
        operation.Value == OpCodes.Stobj.Value || operation.Value == OpCodes.Mkrefany.Value ||
        operation.Value == OpCodes.Refanyval.Value || operation.Value == OpCodes.Sizeof.Value ||
        operation.Value == OpCodes.Constrained.Value || operation.Value == OpCodes.Ldelem.Value ||
        operation.Value == OpCodes.Stelem.Value || operation.Value == OpCodes.Ldelema.Value || operation.Value == OpCodes.Cpobj.Value;

    private static void RejectForeignBox(Module module, byte[] il, ref int index)
    {
        const string failure = "Author type initialization is unsupported.";
        var token = ReadInt32(il, ref index, failure);
        Type? resolved;
        try { resolved = module.ResolveType(token); }
        catch (ArgumentException) { resolved = null; }
        var name = resolved?.Assembly.GetName().Name;
        if (name is not ("System.Private.CoreLib" or "System.Runtime"))
            throw new InvalidOperationException(failure);
    }

    private static void RejectUnsafe(OpCode operation)
    {
        var name = operation.Name ?? string.Empty;
        if (operation.Value == OpCodes.Localloc.Value || operation.Value == OpCodes.Cpblk.Value ||
            operation.Value == OpCodes.Initblk.Value ||
            name.StartsWith("ldind.", StringComparison.Ordinal) ||
            name.StartsWith("stind.", StringComparison.Ordinal))
            throw new InvalidOperationException("Unsafe IL is unsupported.");
        if (operation.Value == OpCodes.Ldsfld.Value || operation.Value == OpCodes.Stsfld.Value ||
            operation.Value == OpCodes.Ldsflda.Value || operation.Value == OpCodes.Ldtoken.Value)
            throw new InvalidOperationException("Static field and token loads are unsupported.");
        if (operation.Value == OpCodes.Ldftn.Value || operation.Value == OpCodes.Ldvirtftn.Value)
            throw new InvalidOperationException("Function pointers are unsupported.");
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

    private readonly record struct PrivateImage(string Name, byte[] Bytes);

    private sealed class HostContractLoadContext : AssemblyLoadContext
    {
        private readonly Dictionary<string, byte[]> _private;

        public HostContractLoadContext(IReadOnlyList<PrivateImage> privateAssemblies)
            : base("RuneCLR.HostContract:" + Guid.NewGuid().ToString("n"), isCollectible: true)
        {
            _private = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
            foreach (var image in privateAssemblies)
                _private.Add(image.Name, image.Bytes);
        }

        protected override Assembly? Load(AssemblyName assemblyName)
        {
            if (assemblyName.Name is not null && _private.TryGetValue(assemblyName.Name, out var bytes))
                return LoadFromStream(new MemoryStream(bytes, writable: false));

            foreach (var assembly in Assemblies)
            {
                if (string.Equals(assembly.GetName().Name, assemblyName.Name, StringComparison.OrdinalIgnoreCase))
                    return assembly;
            }

            foreach (var assembly in Default.Assemblies)
            {
                if (string.Equals(assembly.GetName().Name, assemblyName.Name, StringComparison.OrdinalIgnoreCase))
                    return assembly;
            }

            return null;
        }
    }
}
