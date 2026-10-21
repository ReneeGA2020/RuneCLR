using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

/// <summary>A synchronous script session pumped by the host's game loop.</summary>
/// <remarks>Dispose or Stop every session. Callbacks are serialized; reentrant lifecycle calls are rejected.</remarks>
public sealed class MapSession : IDisposable
{
    private const string TerminationError = "The native prototype instruction budget terminated author execution.";
    private const string DeadlineTerminationError = "The native prototype callback deadline terminated author execution.";
    private readonly object _gate = new();
    private readonly string _mapId;
    private readonly MapRunOptions _options;
    private readonly int _policyVersion;
    private readonly UnloadTicket _unload;
    private AssemblyLoadContext? _loadContext;
    private TerminalPrototypeBridge? _terminal;
    private CallbackDeadlineBridge? _deadline;
    private long _deadlineToken;
    private string? _deadlineFailure;
    private MapContext? _context;
    private IMapScript? _script;
    private MapRunResult? _result;
    private string? _error;
    private int _completedTicks;
    private bool _invoking;

    private MapSession(MapPackage package, MapRunOptions options, CallbackDeadlineBridge? deadlineBridge = null)
    {
        _mapId = package.Id;
        _options = options;
        // Capability failure is a host configuration error, before opening author files.
        var required = options.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter
            ? RequiredInterpreterBridge.Bind() : null;
        _deadline = options.PrototypeCallbackDeadline is not null ? deadlineBridge ?? CallbackDeadlineBridge.Bind() : null;
        _terminal = options.PrototypeInstructionBudget is not null || _deadline is not null ? TerminalPrototypeBridge.Bind(required!) : null;
        _policyVersion = required is null ? 0 : 1;
        var resolver = new MapDependencyResolver(package);
        _loadContext = MapLoadContext.Create(package, resolver, required, _terminal, options, _deadline);
        try
        {
            _unload = new UnloadTicket(new WeakReference(_loadContext, trackResurrection: true));
            _context = new MapContext(package.Id, options);
        }
        catch
        {
            _loadContext.Unload();
            _loadContext = null;
            throw;
        }

        Initialize(resolver.EntryPath, package.EntryType);
    }

    internal static MapSession Start(MapPackage package, MapRunOptions? options)
    {
        ArgumentNullException.ThrowIfNull(package);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.Id);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.AssemblyPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.EntryType);
        options ??= new MapRunOptions();
        options.Validate();
        return new MapSession(package, options);
    }

    public bool IsRunning { get { lock (_gate) return _result is null; } }
    public int CompletedTicks { get { lock (_gate) return _completedTicks; } }

    /// <summary>The final host-owned result, or null until the session stops.</summary>
    public MapRunResult? Result { get { lock (_gate) return _result; } }

    /// <summary>Copies current entity ids and names. Call it between callbacks; the session has stopped after Stop.</summary>
    public MapEntityInfo[] CopyEntities()
    {
        lock (_gate)
        {
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            return _context!.CopyEntities();
        }
    }

    /// <summary>Copies work the script requested and the host has not completed. Call it between callbacks.</summary>
    public MapWorkInfo[] CopyPendingWork()
    {
        lock (_gate)
        {
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            return _context!.CopyPendingWork();
        }
    }

    /// <summary>Copies resource names the script has registered. Call it between callbacks.</summary>
    public MapResourceInfo[] CopyResources()
    {
        lock (_gate)
        {
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            return _context!.CopyResources();
        }
    }

    /// <summary>Posts one primitive event for a subscription. Call it between callbacks.</summary>
    public void Post(int id, int value)
    {
        lock (_gate)
        {
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            _context!.Post(id, value);
        }
    }

    /// <summary>Supplies a primitive success value for one open request. The script can take it on a later callback.</summary>
    public void CompleteWork(long id, int value) => FinishWork(id, value, fail: false);

    /// <summary>Supplies a primitive failure code for one open request. No exception is stored.</summary>
    public void FailWork(long id, int reason) => FinishWork(id, reason, fail: true);

    private void FinishWork(long id, int value, bool fail)
    {
        lock (_gate)
        {
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            if (fail) _context!.FailWork(id, value);
            else _context!.CompleteWork(id, value);
        }
    }

    /// <summary>Runs one tick with the configured delta. TickCount does not limit a pumped session.</summary>
    public bool Tick() => Tick(_options.TickDuration);

    /// <summary>Runs one host-scheduled tick; on script failure, stops the session and returns false.</summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public bool Tick(TimeSpan delta)
    {
        lock (_gate)
        {
            CheckReentry();
            if (_result is not null) throw new InvalidOperationException("The session has stopped.");
            ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(delta, TimeSpan.Zero);
            if (_completedTicks == int.MaxValue) throw new InvalidOperationException("The session tick index is exhausted.");
            _invoking = true;
            var completed = false;
            try
            {
                CheckPrototypeState();
                _context!.BeginTick(_completedTicks);
                BeginDeadline();
                _script!.OnTick(new MapTick(_completedTicks, delta));
                EndDeadline();
                CheckPrototypeState();
                _context.CheckViolation();
                _completedTicks++;
                completed = true;
                return true;
            }
            catch (Exception exception)
            {
                _error = DescribeFailure(exception);
                return false;
            }
            finally
            {
                try
                {
                    EndDeadline();
                    _context?.EndCallback();
                    if (!completed) StopCore();
                }
                finally { _invoking = false; }
            }
        }
    }

    /// <summary>Stops once and returns the same result on subsequent calls.</summary>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public MapRunResult Stop()
    {
        lock (_gate)
        {
            CheckReentry();
            if (_result is not null) return _result;
            _invoking = true;
            try { return StopCore(); }
            finally { _invoking = false; }
        }
    }

    public void Dispose() => Stop();

    [MethodImpl(MethodImplOptions.NoInlining)]
    private void Initialize(string entryPath, string entryTypeName)
    {
        _invoking = true;
        var started = false;
        try
        {
            BeginDeadline();
            var assembly = _loadContext!.LoadFromAssemblyPath(entryPath);
            var entryType = assembly.GetType(entryTypeName, throwOnError: true)!;
            if (!typeof(IMapScript).IsAssignableFrom(entryType) || entryType.IsAbstract)
                throw new InvalidDataException("The entry type must implement IMapScript and be concrete.");

            CheckPrototypeState();
            _script = (IMapScript)Activator.CreateInstance(entryType)!;
            EndDeadline();
            CheckPrototypeState();
            _context!.BeginCallback();
            BeginDeadline();
            _script.OnStart(_context);
            EndDeadline();
            CheckPrototypeState();
            _context.CheckViolation();
            started = true;
        }
        catch (Exception exception)
        {
            _error = DescribeFailure(exception);
        }
        finally
        {
            try
            {
                EndDeadline();
                _context?.EndCallback();
                if (!started) StopCore();
            }
            finally { _invoking = false; }
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private MapRunResult StopCore()
    {
        var loadContext = _loadContext!;
        var context = _context!;
        var terminal = _terminal;
        PrototypeBudgetSnapshot? prototypeBudget = null;
        CallbackDeadlineSnapshot? deadlineSnapshot = null;
        try
        {
            context.CancelScheduled();
            context.CancelWork();
            context.CancelResources();
            context.CancelPosted();
            try
            {
                if (_script is not null && _deadlineFailure is null)
                {
                    // A failed native query also prevents this extra author callback.
                    var beforeStop = terminal?.Snapshot(loadContext);
                    if (beforeStop?.IsTerminated != true)
                    {
                        context.BeginCallback();
                        var stopReturned = false;
                        try
                        {
                            BeginDeadline();
                            _script.OnStop();
                            EndDeadline();
                            CheckPrototypeState();
                            stopReturned = true;
                        }
                        catch (Exception exception)
                        {
                            _error = Append(_error, $"OnStop: {DescribeFailure(exception)}");
                        }
                        finally { EndDeadline(); }

                        // A latched limit is already the callback failure. Do not call a successful OnStop a stop failure.
                        if (stopReturned)
                        {
                            try { context.CheckViolation(); }
                            catch (Exception exception)
                            {
                                var described = DescribeFailure(exception);
                                if (_error?.Contains(described, StringComparison.Ordinal) != true)
                                    _error = Append(_error, described);
                            }
                        }
                    }
                }
            }
            catch (Exception exception)
            {
                _error = Append(_error, $"OnStop: {DescribeFailure(exception)}");
            }
        }
        finally
        {
            try
            {
                context.EndCallback();
                context.Dispose();
            }
            finally
            {
                // A retained, stopped session must not keep its author context alive.
                _script = null;
                _loadContext = null;
                _context = null;
                _terminal = null;
                try
                {
                    if (terminal is not null)
                    {
                        prototypeBudget = terminal.Snapshot(loadContext);
                        if (prototypeBudget.IsTerminated) _error = Append(_error,
                            _deadline is null ? TerminationError : DeadlineTerminationError);
                    }
                    deadlineSnapshot = _deadline?.Snapshot(loadContext);
                }
                catch (Exception)
                {
                    _error = Append(_error, "The native prototype state snapshot could not be read.");
                }
                finally { _deadline = null; loadContext.Unload(); }
            }
        }

        var report = new MapRunReport(_mapId,
            _error is null ? MapRunOutcome.Completed : MapRunOutcome.Failed,
            _completedTicks, context.CreatedEntities, context.ReleasedEntities,
            context.RemainingEntities, context.Logs, _error)
        {
            ExecutionPolicy = _options.ExecutionPolicy,
            ExecutionPolicyVersion = _policyVersion,
            PrototypeBudget = prototypeBudget,
            PrototypeDeadline = deadlineSnapshot
        };
        return _result = new MapRunResult(report, _unload);
    }

    private void CheckReentry()
    {
        if (_invoking) throw new InvalidOperationException("A session lifecycle callback is already running.");
    }

    private void CheckPrototypeState()
    {
        if (_deadlineFailure is not null) throw new InvalidOperationException(_deadlineFailure);
        bool terminated;
        try { terminated = _terminal?.IsTerminated(_loadContext!) == true; }
        catch (Exception)
        {
            if (_deadline is not null) FailDeadlineBridge("The native callback deadline state could not be queried.");
            throw;
        }
        if (terminated)
            throw new InvalidOperationException(_deadline is null ? TerminationError : DeadlineTerminationError);
    }

    private void BeginDeadline()
    {
        if (_deadlineFailure is not null) throw new InvalidOperationException(_deadlineFailure);
        if (_deadline is null) return;
        try
        {
            _deadlineToken = _deadline.Begin(_loadContext!);
            if (_deadlineToken <= 0) throw new InvalidOperationException("Invalid native callback deadline token.");
        }
        catch (Exception)
        {
            FailDeadlineBridge("The native callback deadline activation could not be opened.");
            throw;
        }
    }

    private void EndDeadline()
    {
        if (_deadlineToken == 0) return;
        var token = _deadlineToken;
        _deadlineToken = 0;
        try
        {
            if (!_deadline!.End(_loadContext!, token))
                FailDeadlineBridge("The native callback deadline activation did not close successfully.");
        }
        catch (Exception)
        {
            FailDeadlineBridge("The native callback deadline activation could not be closed.");
        }
    }

    private void FailDeadlineBridge(string message)
    {
        _deadlineFailure ??= message;
        _error = Append(_error, _deadlineFailure);
    }

    private string DescribeFailure(Exception exception)
    {
        if (_deadlineFailure is not null) return _deadlineFailure;
        if (_terminal is not null)
        {
            try
            {
                if (_terminal.IsTerminated(_loadContext!)) return _deadline is null ? TerminationError : DeadlineTerminationError;
            }
            catch (Exception)
            {
                if (_deadline is not null) FailDeadlineBridge("The native callback deadline state could not be queried.");
                return "The native prototype instruction-budget state could not be queried.";
            }
        }

        if (exception is TargetInvocationException { InnerException: { } inner }) exception = inner;
        var typeName = exception.GetType().FullName ?? "Exception";
        if (_terminal is not null)
        {
            // Message/ToString may invoke author code even before native termination.
            return typeName.Length <= 512 ? typeName : typeName[..512];
        }

        try
        {
            var described = $"{typeName}: {exception.Message}";
            if (exception is TypeInitializationException { InnerException: { } initializer })
            {
                string? innerName = null;
                try { innerName = initializer.GetType().FullName; }
                catch (Exception) { innerName = null; }
                if (!string.IsNullOrEmpty(innerName)) described = $"{described} ({innerName})";
            }
            return described;
        }
        catch (Exception) { return $"{typeName}: The exception message could not be read."; }
    }

    private static string Append(string? previous, string next) =>
        previous is null || previous == next ? next : $"{previous}; {next}";
}
