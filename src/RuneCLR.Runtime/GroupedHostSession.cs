using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

/// <summary>
/// Opt-in grouped host: one collectible ordinary context for a trusted framework and one collectible
/// required-interpreter context for an author module, retired together.
/// The framework may use ordinary CLR/JIT and trusted native interop (what an ordinary collectible
/// context may do; not a sandbox claim). The author always gets an audited required-interpreter context.
/// A method the author calls on the shared framework assembly executes in the framework context, so
/// trusted native interop inside that framework method is legitimate; an author image's own native
/// import stays rejected by the required-interpreter context and by admission.
/// </summary>
public sealed record GroupedHostOptions
{
    public required Type Contract { get; init; }
    public required string FrameworkDirectory { get; init; }
    public required string FrameworkAssembly { get; init; }
    public required string FrameworkEntryType { get; init; }
    public required string FrameworkEntryMethod { get; init; }
    public required string AuthorDirectory { get; init; }
    public required string AuthorAssembly { get; init; }
    public required string AuthorEntryType { get; init; }
    public required string AuthorEntryMethod { get; init; }

    /// <summary>Extra Default-context assemblies shared with both roles; same rules as the single-domain option.</summary>
    public IReadOnlyList<Assembly> SharedAssemblies { get; init; } = [];

    public required IApiAccessPolicy AuthorApiPolicy { get; init; }
}

/// <summary>Host-owned cleanup acknowledgement. A pending token rejects all new entry.</summary>
public sealed class GroupedHostCleanupToken
{
    internal GroupedHostCleanupToken(object owner) => Owner = owner;
    internal object Owner { get; }
    public bool Pending { get; internal set; } = true;
    public bool DrainAcknowledged { get; internal set; }
    public bool Completed { get; internal set; }
}

/// <summary>Terminal view: scalars and weak tickets only, no live Assembly/Type/delegate/instance.</summary>
public readonly struct GroupedHostTicket
{
    internal GroupedHostTicket(WeakReference? framework, WeakReference? author,
        bool frameworkUnloadRequested, bool authorUnloadRequested, bool leasesReleased,
        string? frameworkUnloadFailure, string? authorUnloadFailure)
    {
        FrameworkContext = framework;
        AuthorContext = author;
        FrameworkUnloadRequested = frameworkUnloadRequested;
        AuthorUnloadRequested = authorUnloadRequested;
        LeasesReleased = leasesReleased;
        FrameworkUnloadFailure = frameworkUnloadFailure;
        AuthorUnloadFailure = authorUnloadFailure;
    }

    public WeakReference? FrameworkContext { get; }
    public WeakReference? AuthorContext { get; }
    public bool FrameworkUnloadRequested { get; }
    public bool AuthorUnloadRequested { get; }
    public bool LeasesReleased { get; }

    /// <summary>Host-owned failure type name from the last unload attempt, or null when it succeeded.</summary>
    public string? FrameworkUnloadFailure { get; }
    public string? AuthorUnloadFailure { get; }

    /// <summary>True only when a weak target exists and is dead; a missing target stays unknown.</summary>
    public bool FrameworkCollected => FrameworkContext is { IsAlive: false };
    public bool AuthorCollected => AuthorContext is { IsAlive: false };
    public bool BothCollected => FrameworkCollected && AuthorCollected;
}

public sealed class GroupedHostSession : IDisposable
{
    private enum Phase { Open, CleanupPending, CleanupComplete, Retiring, Closed }

    private readonly object _gate = new();
    private Phase _phase = Phase.Open;
    private bool _inFlight;
    private GroupedHostCleanupToken? _cleanup;
    private GroupedHostTicket? _ticket;

    // Frozen option data; no caller-owned mutable collection is consulted after Open.
    private Assembly _contractAssembly = null!;
    private Type _contractType = null!;
    private Assembly[] _sharedAssemblies = [];
    private Dictionary<string, Assembly> _sharedByName = new(StringComparer.OrdinalIgnoreCase);
    private IApiAccessPolicy _policy = null!;
    private string _frameworkDirectory = "";
    private string _frameworkAssemblyName = "";
    private string _frameworkEntryType = "";
    private string _frameworkEntryMethod = "";
    private string _authorDirectory = "";
    private string _authorAssemblyName = "";
    private string _authorEntryType = "";
    private string _authorEntryMethod = "";
    private object? _host;

    private GroupedLoadContext? _frameworkContext;
    private AssemblyLoadContext? _authorContext;
    private UgcAssemblyAdmission? _admission;
    private ReflectionPolicySession? _reflectionPolicy;
    private Assembly? _frameworkAssembly;
    private Assembly? _authorAssembly;
    private MethodInfo? _frameworkEntry;
    private MethodInfo? _authorEntry;

    private RoleCatalog? _frameworkCatalog;
    private RoleCatalog? _authorCatalog;
    private readonly Dictionary<string, Assembly> _frameworkLoaded = new(StringComparer.OrdinalIgnoreCase);
    // Protects the loaded-instance cache and tracks CLR-initiated resolutions so retirement cannot
    // clear a cache entry while a load is still running. No managed lock is held across LoadFromStream.
    private int _resolutionInFlight;
    private readonly HashSet<string> _resolutionPending = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<Assembly> _leases = [];
    private bool _frameworkUnloadRequested;
    private bool _authorUnloadRequested;
    private bool _leasesReleased;
    private string? _frameworkUnloadFailure;
    private string? _authorUnloadFailure;

    private GroupedHostSession() { }

    public static GroupedHostSession Open(GroupedHostOptions options, object host)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(host);
        if (options.Contract is null) throw new ArgumentException("A contract type is required.", nameof(options));
        if (options.AuthorApiPolicy is null) throw new ArgumentException("An author API policy is required.", nameof(options));
        if (!options.Contract.IsInstanceOfType(host))
            throw new ArgumentException("The host instance must implement the supplied contract.", nameof(host));

        // Grouped-profile preflight: the required-interpreter bridge and the session-origin scan
        // capability must exist before any context or author image is created. Missing capability
        // fails closed with PlatformNotSupportedException; no global switch is enabled here.
        RequiredInterpreterBridge.Bind();
        PrototypeReflectionPolicy.Prepare();
        PrototypeReflectionPolicy.PrepareOriginScan();
        var session = new GroupedHostSession { _host = host };
        session.FreezeOptions(options);
        try
        {
            session.BuildCatalogs();
            // Admission construction, group metadata registration and exact initial-image preflight all
            // run here, after catalogs but before ANY context exists.
            session.PrepareAuthorAdmission();
            session.CreateFrameworkContext();
            session.CreateAuthorContext();
            return session;
        }
        catch (Exception error)
        {
            var hadContext = session._frameworkContext is not null || session._authorContext is not null;
            try { session.RollbackPartial(); } catch { }
            // Pre-context validation errors stay exactly as they are; anything that could carry domain
            // frames/inner/Type after a context was created is replaced by a host-owned failure.
            if (!hadContext) throw;
            throw NormalizeOpenFailure(error);
        }
    }

    public bool IsClosed { get { lock (_gate) { return _phase == Phase.Closed; } } }

    public GroupedHostCleanupToken BeginCleanup()
    {
        lock (_gate)
        {
            RequireNoFlight();
            if (_phase == Phase.Closed) throw new ObjectDisposedException(nameof(GroupedHostSession));
            if (_phase is Phase.CleanupPending or Phase.CleanupComplete)
                return _cleanup ?? throw new InvalidOperationException("Cleanup state is inconsistent.");
            if (_phase != Phase.Open) throw new InvalidOperationException("The group is already retiring.");
            _cleanup = new GroupedHostCleanupToken(this);
            _phase = Phase.CleanupPending;
            return _cleanup;
        }
    }

    public void AcknowledgeCleanup(GroupedHostCleanupToken token)
    {
        ArgumentNullException.ThrowIfNull(token);
        lock (_gate)
        {
            RequireNoFlight();
            RequireToken(token);
            if (!token.Pending) throw new InvalidOperationException("Cleanup was already completed.");
            token.DrainAcknowledged = true;
        }
    }

    public void CompleteCleanup(GroupedHostCleanupToken token)
    {
        ArgumentNullException.ThrowIfNull(token);
        lock (_gate)
        {
            RequireNoFlight();
            RequireToken(token);
            if (!token.Pending) throw new InvalidOperationException("Cleanup was already completed.");
            if (!token.DrainAcknowledged)
                throw new InvalidOperationException("Drain acknowledgement is required before completing cleanup.");
            token.Completed = true;
            token.Pending = false;
            _phase = Phase.CleanupComplete;
        }
    }

    public void InvokeFramework()
    {
        MethodInfo entry;
        object? host;
        lock (_gate) { EnterCore(); entry = _frameworkEntry!; host = _host; }
        try { entry.Invoke(null, [host]); }
        catch (TargetInvocationException error) { throw HostFailure(error); }
        finally { lock (_gate) { _inFlight = false; } }
    }

    public int InvokeAuthor(int value)
    {
        MethodInfo entry;
        object? host;
        ReflectionPolicySession policy;
        lock (_gate) { EnterCore(); entry = _authorEntry!; host = _host; policy = _reflectionPolicy!; }
        try
        {
            using var scope = policy.Activate();
            try { return (int)entry.Invoke(null, [host, value])!; }
            catch (TargetInvocationException error) { throw HostFailure(error); }
        }
        finally { lock (_gate) { _inFlight = false; } }
    }

    public GroupedHostTicket Close()
    {
        GroupedLoadContext? framework;
        AssemblyLoadContext? author;
        lock (_gate)
        {
            RequireNoFlight();
            if (_ticket is not null) return _ticket.Value;
            if (_phase == Phase.Retiring) throw new InvalidOperationException("Another retire attempt owns this group.");
            if (_phase != Phase.CleanupComplete)
                throw new InvalidOperationException("Close requires a completed cleanup; pending state is preserved.");
            if (_resolutionInFlight != 0)
                throw new InvalidOperationException("A framework resolution is still in flight; retry retirement after it completes.");
            _phase = Phase.Retiring;
            framework = _frameworkContext;
            author = _authorContext;
        }

        GroupedHostTicket ticket;
        try { ticket = RetireStaged(framework, author); }
        catch
        {
            lock (_gate) { _phase = Phase.CleanupComplete; }
            throw;
        }
        lock (_gate)
        {
            // Success: the ticket already holds the weak targets, so the strong roots must go.
            _ticket = ticket;
            _frameworkContext = null;
            _authorContext = null;
            _phase = Phase.Closed;
        }
        return ticket;
    }

    /// <summary>
    /// Safe rejection is intentional: Dispose never acknowledges cleanup for the host. A group without a
    /// completed cleanup throws and stays retryable; use the explicit cleanup methods and Close.
    /// </summary>
    public void Dispose()
    {
        GroupedLoadContext? framework;
        AssemblyLoadContext? author;
        lock (_gate)
        {
            RequireNoFlight();
            if (_phase == Phase.Closed) return;
            if (_phase == Phase.Retiring) throw new InvalidOperationException("Another retire attempt owns this group.");
            if (_phase != Phase.CleanupComplete)
                throw new InvalidOperationException(
                    "Dispose requires a completed cleanup; the group stays open for a controlled retirement.");
            if (_resolutionInFlight != 0)
                throw new InvalidOperationException("A framework resolution is still in flight; retry retirement after it completes.");
            _phase = Phase.Retiring;
            framework = _frameworkContext;
            author = _authorContext;
        }

        try
        {
            var ticket = RetireStaged(framework, author);
            lock (_gate)
            {
                _ticket = ticket;
                _frameworkContext = null;
                _authorContext = null;
                _phase = Phase.Closed;
            }
        }
        catch
        {
            lock (_gate) { _phase = Phase.CleanupComplete; }
            throw;
        }
    }

    /// <summary>
    /// Staged retirement. Unload is requested outside the state lock; a throwing Unloading handler leaves
    /// the request unmarked and the contexts/leases in place so a retry is correct. Only after both
    /// requests succeed are resolver leases, the reflection policy and live references released.
    /// </summary>
    private GroupedHostTicket RetireStaged(GroupedLoadContext? framework, AssemblyLoadContext? author)
    {
        lock (_gate)
        {
            if (_resolutionInFlight != 0)
                throw new InvalidOperationException("A framework resolution is still in flight; retry retirement after it completes.");
        }

        if (!_frameworkUnloadRequested && framework is not null)
        {
            try { framework.Unload(); }
            catch (Exception error)
            {
                _frameworkUnloadFailure = HostFailureName(error);
                throw new InvalidOperationException("Framework unload request failed; state preserved: " + _frameworkUnloadFailure);
            }
            _frameworkUnloadRequested = true;
            _frameworkUnloadFailure = null;
        }

        if (!_authorUnloadRequested && author is not null)
        {
            try { author.Unload(); }
            catch (Exception error)
            {
                _authorUnloadFailure = HostFailureName(error);
                throw new InvalidOperationException("Author unload request failed; state preserved: " + _authorUnloadFailure);
            }
            _authorUnloadRequested = true;
            _authorUnloadFailure = null;
        }

        if (!_leasesReleased)
        {
            try { _reflectionPolicy?.Dispose(); }
            catch (Exception error)
            {
                throw new InvalidOperationException("Reflection policy release failed; leases preserved: " + HostFailureName(error));
            }
            lock (_gate)
            {
                _reflectionPolicy = null;
                _leases.Clear();
                _admission = null;
                _frameworkLoaded.Clear();
                _frameworkEntry = null;
                _authorEntry = null;
                _frameworkAssembly = null;
                _authorAssembly = null;
                _frameworkCatalog = null;
                _authorCatalog = null;
                _host = null;
                _sharedAssemblies = [];
                _sharedByName.Clear();
                _policy = null!;
                _contractAssembly = null!;
                _contractType = null!;
            }
            _leasesReleased = true;
        }

        var frameworkWeak = framework is null ? null : new WeakReference(framework, trackResurrection: true);
        var authorWeak = author is null ? null : new WeakReference(author, trackResurrection: true);
        return new GroupedHostTicket(frameworkWeak, authorWeak, _frameworkUnloadRequested, _authorUnloadRequested,
            _leasesReleased, _frameworkUnloadFailure, _authorUnloadFailure);
    }

    private static string HostFailureName(Exception error)
    {
        var inner = error is TargetInvocationException { InnerException: { } captured } ? captured : error;
        var name = inner.GetType().FullName ?? "Exception";
        return name.Length <= 512 ? name : name[..512];
    }

    /// <summary>
    /// Partial-open rollback of a session that is never published. The phase moves to Retiring under the
    /// state lock BEFORE any resolver input is cleared, so a resolution triggered from an Unloading handler
    /// rejects deterministically; an already in-flight resolution is not waited for (its counter decrement
    /// stays harmless). Field cleanup stays under short locks, the policy release and both Unload calls run
    /// outside, and the phase ends Closed under a final short lock.
    /// </summary>
    private void RollbackPartial()
    {
        GroupedLoadContext? framework;
        AssemblyLoadContext? author;
        ReflectionPolicySession? policy;
        lock (_gate)
        {
            _phase = Phase.Retiring;
            framework = _frameworkContext;
            author = _authorContext;
            policy = _reflectionPolicy;
        }

        try { policy?.Dispose(); } catch { }

        lock (_gate)
        {
            _reflectionPolicy = null;
            _leases.Clear();
            _frameworkLoaded.Clear();
            _admission = null;
            _frameworkEntry = null;
            _authorEntry = null;
            _frameworkAssembly = null;
            _authorAssembly = null;
            _frameworkCatalog = null;
            _authorCatalog = null;
            _host = null;
            _sharedAssemblies = [];
            _sharedByName.Clear();
            _policy = null!;
            _contractAssembly = null!;
            _contractType = null!;
        }

        if (framework is not null) { try { framework.Unload(); } catch { } }
        if (author is not null) { try { author.Unload(); } catch { } }

        lock (_gate)
        {
            _frameworkContext = null;
            _authorContext = null;
            _phase = Phase.Closed;
        }
    }

    private void EnterCore()
    {
        if (_phase != Phase.Open)
            throw new InvalidOperationException(_phase == Phase.Closed
                ? "The group is closed."
                : "Entry is closed while cleanup is pending or the group is retiring.");
        if (_inFlight) throw new InvalidOperationException("Reentrant entry is not allowed.");
        _inFlight = true;
    }

    private void RequireNoFlight()
    {
        if (_inFlight) throw new InvalidOperationException("Lifecycle calls are not allowed while an entry is active.");
    }

    private void RequireToken(GroupedHostCleanupToken token)
    {
        if (!ReferenceEquals(token.Owner, this) || !ReferenceEquals(token, _cleanup))
            throw new InvalidOperationException("The cleanup token does not belong to this group.");
        if (_phase is not (Phase.CleanupPending or Phase.CleanupComplete))
            throw new InvalidOperationException("The group is not in a cleanup state.");
    }

    private void FreezeOptions(GroupedHostOptions options)
    {
        _contractAssembly = options.Contract.Assembly;
        _contractType = options.Contract;
        _policy = options.AuthorApiPolicy;
        _frameworkDirectory = RequireDirectory(options.FrameworkDirectory);
        _frameworkAssemblyName = RequireFileName(options.FrameworkAssembly, "framework");
        _frameworkEntryType = options.FrameworkEntryType;
        _frameworkEntryMethod = options.FrameworkEntryMethod;
        _authorDirectory = RequireDirectory(options.AuthorDirectory);
        _authorAssemblyName = RequireFileName(options.AuthorAssembly, "author");
        _authorEntryType = options.AuthorEntryType;
        _authorEntryMethod = options.AuthorEntryMethod;

        if (_contractAssembly.IsDynamic ||
            AssemblyLoadContext.GetLoadContext(_contractAssembly) != AssemblyLoadContext.Default)
            throw new ArgumentException("The contract must be an existing Default-context assembly.");

        var byName = new Dictionary<string, Assembly>(StringComparer.OrdinalIgnoreCase)
        {
            [_contractAssembly.GetName().Name!] = _contractAssembly
        };
        var shared = new List<Assembly>();
        foreach (var assembly in options.SharedAssemblies.ToArray())
        {
            if (assembly is null || assembly.IsDynamic ||
                AssemblyLoadContext.GetLoadContext(assembly) != AssemblyLoadContext.Default ||
                !byName.TryAdd(assembly.GetName().Name!, assembly))
                throw new ArgumentException("Shared assemblies must be unique, existing default-context assemblies.");
            shared.Add(assembly);
        }
        _sharedAssemblies = shared.ToArray();
        _sharedByName = byName;
    }

    private static string RequireDirectory(string directory)
    {
        if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
            throw new ArgumentException("A role directory must exist: " + directory);
        return Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    }

    private static string RequireFileName(string file, string role)
    {
        if (string.IsNullOrWhiteSpace(file) || file != Path.GetFileName(file) ||
            !file.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("A role image must be a plain .dll file name: " + role);
        return file;
    }

    private void BuildCatalogs()
    {
        _frameworkCatalog = RoleCatalog.Build("framework", _frameworkDirectory, _frameworkAssemblyName,
            _contractAssembly.GetName(), _sharedAssemblies, approvedFramework: null);
        _authorCatalog = RoleCatalog.Build("author", _authorDirectory, _authorAssemblyName,
            _contractAssembly.GetName(), _sharedAssemblies, approvedFramework: _frameworkCatalog);

        if (_sharedByName.ContainsKey(_authorCatalog.Primary.SimpleName))
            throw new InvalidDataException("The author primary image cannot be a shared or contract identity.");
        if (_frameworkCatalog.Find(_authorCatalog.Primary.SimpleName) is not null)
            throw new InvalidDataException("The author primary image cannot take a framework identity.");
    }

    private void CreateFrameworkContext()
    {
        var catalog = _frameworkCatalog!;
        _frameworkContext = new GroupedLoadContext("RuneCLR.Group.Framework:" + Guid.NewGuid().ToString("n"),
            (context, requested) => ResolveFramework(context, requested));
        _frameworkAssembly = LoadFramework(catalog.Primary);
        _frameworkEntry = Entry(_frameworkAssembly, _frameworkEntryType, _frameworkEntryMethod,
            returnsVoid: true, _contractType);
    }

    /// <summary>
    /// Author-side resolution: the whole lifetime (retire check, shared/BCL handling, catalog lookup,
    /// identity check, cache hit, load registration and lease publication) is coordinated by the single
    /// state lock. Only LoadFromStream itself runs outside the lock.
    /// </summary>
    private Assembly? ResolveForAuthor(AssemblyName requested)
    {
        var name = requested.Name ?? throw new FileLoadException("A simple name is required.");
        AssemblyLoadContext context;
        RoleImage image;
        lock (_gate)
        {
            if (_phase is Phase.Retiring or Phase.Closed)
                throw new InvalidOperationException("Framework resolution is not allowed after retirement started.");
            if (_sharedByName.TryGetValue(name, out var shared))
            {
                MapDependencyResolver.RequireIdentity(requested, shared.GetName());
                return shared;
            }
            if (MapDependencyResolver.IsFrameworkName(name)) return null;
            image = _frameworkCatalog?.Find(name)
                ?? throw new FileNotFoundException("No role image matches the requested framework dependency: " + requested.FullName);
            MapDependencyResolver.RequireIdentity(requested, new AssemblyName(image.Identity));
            if (_frameworkLoaded.TryGetValue(name, out var cached))
            {
                MapDependencyResolver.RequireIdentity(requested, cached.GetName());
                if (!_leases.Contains(cached)) _leases.Add(cached);
                return cached;
            }
            context = _frameworkContext
                ?? throw new InvalidOperationException("The framework context was already released.");
            if (!_resolutionPending.Add(name))
                throw new InvalidOperationException("Concurrent resolution of " + name + " is not supported.");
            _resolutionInFlight++;
        }

        try
        {
            var assembly = context.LoadFromStream(new MemoryStream(image.Bytes, writable: false));
            MapDependencyResolver.RequireIdentity(requested, assembly.GetName());
            lock (_gate)
            {
                _frameworkLoaded[name] = assembly;
                if (!_leases.Contains(assembly)) _leases.Add(assembly);
            }
            return assembly;
        }
        finally
        {
            lock (_gate)
            {
                _resolutionInFlight--;
                _resolutionPending.Remove(name);
            }
        }
    }

    private Assembly LoadFramework(RoleImage image)
    {
        AssemblyLoadContext context;
        lock (_gate)
        {
            if (_phase is Phase.Retiring or Phase.Closed)
                throw new InvalidOperationException("Framework resolution is not allowed after retirement started.");
            if (_frameworkLoaded.TryGetValue(image.SimpleName, out var cached))
            {
                MapDependencyResolver.RequireIdentity(new AssemblyName(image.Identity), cached.GetName());
                return cached;
            }
            context = _frameworkContext
                ?? throw new InvalidOperationException("The framework context was already released.");
            if (!_resolutionPending.Add(image.SimpleName))
                throw new InvalidOperationException("Concurrent resolution of " + image.SimpleName + " is not supported.");
            _resolutionInFlight++;
        }

        try
        {
            // Load outside the lock: this crosses into the CLR binder and must not hold a managed lock.
            var assembly = context.LoadFromStream(new MemoryStream(image.Bytes, writable: false));
            MapDependencyResolver.RequireIdentity(new AssemblyName(image.Identity), assembly.GetName());
            lock (_gate) { _frameworkLoaded[image.SimpleName] = assembly; }
            return assembly;
        }
        finally
        {
            lock (_gate)
            {
                _resolutionInFlight--;
                _resolutionPending.Remove(image.SimpleName);
            }
        }
    }

    private Assembly? ResolveFramework(AssemblyLoadContext context, AssemblyName requested)
    {
        var name = requested.Name ?? throw new FileLoadException("A simple name is required.");
        Assembly? shared;
        RoleImage? image = null;
        lock (_gate)
        {
            if (_phase is Phase.Retiring or Phase.Closed)
                throw new InvalidOperationException("Framework resolution is not allowed after retirement started.");
            _sharedByName.TryGetValue(name, out shared);
            if (shared is null && !MapDependencyResolver.IsFrameworkName(name))
            {
                image = _frameworkCatalog?.Find(name)
                    ?? throw new FileNotFoundException("No role image matches the requested framework dependency: " + requested.FullName);
            }
        }

        if (shared is not null)
        {
            MapDependencyResolver.RequireIdentity(requested, shared.GetName());
            return shared;
        }
        if (image is null) return null;
        MapDependencyResolver.RequireIdentity(requested, new AssemblyName(image.Identity));
        return LoadFramework(image);
    }

    /// <summary>
    /// Builds the author admission, registers the group framework metadata and validates the exact
    /// immutable initial author images with the same policy rules before ANY context exists. The framework
    /// resolver delegate captures the catalog lazily, so metadata validation never needs a framework
    /// Assembly. All later loads still go through the attached policy Admit callback.
    /// </summary>
    private void PrepareAuthorAdmission()
    {
        var catalog = _authorCatalog!;
        var sources = new List<UgcAssemblySource>();
        foreach (var image in catalog.Privates)
            sources.Add(new UgcAssemblySource(image.SimpleName, image.Identity, null, image.Bytes, image.Sha256));

        _admission = new UgcAssemblyAdmission(_policy, _contractAssembly, sources, _sharedAssemblies);
        _admission.RegisterGroupFramework(
            _frameworkCatalog!.Privates.Select(i => new AssemblyName(i.Identity)).ToArray(),
            requested => ResolveForAuthor(requested));

        foreach (var image in catalog.Privates)
        {
            try
            {
                _admission.Admit(image.Bytes, null);
            }
            catch (Exception error)
            {
                throw new InvalidDataException(
                    "Initial author image was rejected by admission before loading: " + image.SimpleName + ": " + error.Message, error);
            }
        }
    }

    /// <summary>
    /// Host-owned failure for an Open that already created a context. Exactly known host validation types
    /// keep their message in a NEW instance of that same type; anything else (including author-defined
    /// subclasses of those types) becomes a type-name-only InvalidOperationException, so no domain message,
    /// inner exception or stack escapes.
    /// </summary>
    private static Exception NormalizeOpenFailure(Exception error)
    {
        var inner = error is TargetInvocationException { InnerException: { } captured } ? captured : error;
        var type = inner.GetType();
        if (type == typeof(InvalidDataException)) return new InvalidDataException(inner.Message);
        if (type == typeof(ArgumentException)) return new ArgumentException(inner.Message);
        if (type == typeof(PlatformNotSupportedException)) return new PlatformNotSupportedException(inner.Message);
        return new InvalidOperationException(HostFailureName(inner));
    }

    private void CreateAuthorContext()
    {
        var catalog = _authorCatalog!;
        // The admission instance and its group metadata were prepared before any context existed.
        if (_admission is null) throw new InvalidOperationException("Author admission was not prepared.");
        var bridge = RequiredInterpreterBridge.Bind();
        _authorContext = bridge.Create("RuneCLR.Group.Author:" + Guid.NewGuid().ToString("n"),
            (context, requested) => _admission!.Resolve(context, requested));
        _reflectionPolicy = PrototypeReflectionPolicy.Create(_policy, _authorContext, _admission.Admit);
        // Bounded author scope covers the initial author load and entry binding, priming the policy
        // session before any framework -> author callback can run.
        using (var initialScope = _reflectionPolicy.Activate())
        {
            _authorAssembly = _authorContext.LoadFromStream(new MemoryStream(catalog.Primary.Bytes, writable: false));
            _authorEntry = Entry(_authorAssembly!, _authorEntryType, _authorEntryMethod,
                returnsVoid: false, _contractType);
        }
    }

    /// <summary>
    /// Normalizes a session-defined failure into a host-owned exception: the type name only, never the
    /// original exception, its stack, its metadata or an author ToString value.
    /// </summary>
    private static InvalidOperationException HostFailure(Exception exception)
    {
        var inner = exception is TargetInvocationException { InnerException: { } captured } ? captured : exception;
        var typeName = inner.GetType().FullName ?? "Exception";
        return new InvalidOperationException(typeName.Length <= 512 ? typeName : typeName[..512]);
    }
    private static MethodInfo Entry(Assembly assembly, string typeName, string methodName, bool returnsVoid, Type contract)
    {
        var type = assembly.GetType(typeName, throwOnError: false)
            ?? throw new InvalidDataException("Entry type not found: " + typeName);
        if (type.IsGenericTypeDefinition || type.ContainsGenericParameters)
            throw new InvalidDataException("The entry type must not be an open generic: " + typeName);
        var method = type.GetMethod(methodName, BindingFlags.Public | BindingFlags.Static)
            ?? throw new InvalidDataException("Public static entry method not found: " + typeName + "." + methodName);
        if ((method.CallingConvention & CallingConventions.VarArgs) != 0)
            throw new InvalidDataException("Entry methods may not use CLR varargs: " + typeName + "." + methodName);
        if (method.IsGenericMethodDefinition || method.ContainsGenericParameters)
            throw new InvalidDataException("The entry method must not be generic: " + typeName + "." + methodName);
        var expected = returnsVoid ? new[] { contract } : new[] { contract, typeof(int) };
        var expectedReturn = returnsVoid ? typeof(void) : typeof(int);
        var parameters = method.GetParameters();
        if (method.ReturnType != expectedReturn || parameters.Length != expected.Length)
            throw new InvalidDataException("Unexpected entry signature: " + typeName + "." + methodName);
        for (var i = 0; i < expected.Length; i++)
        {
            if (parameters[i].ParameterType != expected[i] || parameters[i].IsOut || parameters[i].ParameterType.IsByRef)
                throw new InvalidDataException("Unexpected entry parameter: " + typeName + "." + methodName);
        }
        return method;
    }

    private sealed record RoleImage(string FileName, string Path, byte[] Bytes, string Identity, string SimpleName, string Sha256);

    /// <summary>
    /// Immutable per-role catalog built from bytes before any context exists. Every file is inspected from
    /// the same bytes that are later loaded or admitted; the directory is never re-read afterwards.
    /// </summary>
    private sealed class RoleCatalog
    {
        private RoleCatalog(RoleImage primary, Dictionary<string, RoleImage> privates, List<RoleImage> references)
        {
            Primary = primary;
            Privates = privates.Values.ToArray();
            References = references;
        }

        public RoleImage Primary { get; }
        public IReadOnlyList<RoleImage> Privates { get; }
        public IReadOnlyList<RoleImage> References { get; }

        public RoleImage? Find(string simpleName) =>
            Privates.FirstOrDefault(p => string.Equals(p.SimpleName, simpleName, StringComparison.OrdinalIgnoreCase));

        public static RoleCatalog Build(string role, string directory, string primaryFile,
            AssemblyName contract, IReadOnlyList<Assembly> shared, RoleCatalog? approvedFramework)
        {
            var root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var sharedByName = new Dictionary<string, AssemblyName>(StringComparer.OrdinalIgnoreCase)
            {
                [contract.Name!] = contract
            };
            foreach (var assembly in shared)
                sharedByName[assembly.GetName().Name!] = assembly.GetName();

            var privates = new Dictionary<string, RoleImage>(StringComparer.OrdinalIgnoreCase);
            var references = new List<RoleImage>();
            RoleImage? primary = null;

            foreach (var file in Directory.EnumerateFiles(root, "*.dll", SearchOption.TopDirectoryOnly).OrderBy(f => f, StringComparer.Ordinal))
            {
                var full = Path.GetFullPath(file);
                if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("A role image path escapes its role directory: " + file);
                var name = Path.GetFileName(full);
                if (!name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Unexpected role image name: " + name);

                var bytes = File.ReadAllBytes(full);

                var sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
                // Identity-only classification first: a host-selected framework or shared copy in ordinary
                // compiler output must not be re-inspected as untrusted author code, and a mismatched copy
                // is denied. Only private images reach strict/trusted inspection below.
                if (!ManagedAssemblyInspector.TryReadIdentity(bytes, out var identity, out var simpleName))
                    throw new InvalidDataException("A role directory contains an unreadable managed image: " + name);
                var image = new RoleImage(name, full, bytes, identity, simpleName, sha);
                var isPrimary = string.Equals(name, primaryFile, StringComparison.OrdinalIgnoreCase);
                if (sharedByName.TryGetValue(simpleName, out var sharedIdentity))
                {
                    RequireSameIdentity(role, image, sharedIdentity, "a shared or contract reference copy");
                    references.Add(image);
                    if (isPrimary)
                        throw new InvalidDataException("A role primary image cannot be a shared or contract identity: " + role);
                    continue;
                }
                if (approvedFramework is not null && approvedFramework.Find(simpleName) is { } approved)
                {
                    RequireSameIdentity(role, image, new AssemblyName(approved.Identity), "a framework reference copy");
                    if (!string.Equals(image.Sha256, approved.Sha256, StringComparison.Ordinal))
                        throw new InvalidDataException("A copied framework image differs from the selected framework bytes: " + name);
                    references.Add(image);
                    if (isPrimary)
                        throw new InvalidDataException("A role primary image cannot be a framework identity: " + role);
                    continue;
                }
                ManagedAssemblyInfo info;
                try
                {
                    info = string.Equals(role, "framework", StringComparison.Ordinal)
                        ? ManagedAssemblyInspector.InspectTrustedFramework(bytes)
                        : ManagedAssemblyInspector.Inspect(bytes);
                }
                catch (Exception error)
                {
                    throw new InvalidDataException("A role private image was rejected: " + name + ": " + error.Message, error);
                }
                if (!string.Equals(info.SimpleName, simpleName, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(info.AssemblyName, identity, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("A role image identity changed between classification and inspection: " + name);
                if (MapDependencyResolver.IsFrameworkName(simpleName))
                    throw new InvalidDataException("A role directory contains a framework/BCL image that is not host-selected: " + name);
                if (!privates.TryAdd(simpleName, image))
                    throw new InvalidDataException("Duplicate private image identity in a role directory: " + name);
                if (isPrimary) primary = image;
            }

            if (primary is null)
                throw new InvalidDataException("The role primary image was not found in its directory: " + role + "/" + primaryFile);
            return new RoleCatalog(primary, privates, references);
        }

        private static void RequireSameIdentity(string role, RoleImage image, AssemblyName expected, string what)
        {
            if (!AssemblyName.ReferenceMatchesDefinition(expected, new AssemblyName(image.Identity)) ||
                !string.Equals(expected.FullName, image.Identity, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("A " + role + " image claiming " + what + " has a different identity: " + image.FileName);
        }
    }

    private sealed class GroupedLoadContext(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver)
        : AssemblyLoadContext(name, isCollectible: true)
    {
        protected override Assembly? Load(AssemblyName assemblyName) => resolver(this, assemblyName);
    }
}
