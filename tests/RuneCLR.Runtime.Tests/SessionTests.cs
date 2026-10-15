using System.Reflection;
using System.Runtime.CompilerServices;
using RuneCLR.Runtime;

internal static class SessionTests
{
    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host-pumped sessions obey host tick cadence and delta", ManualCadence);
        yield return ("Invalid tick deltas leave the session active", InvalidDelta);
        yield return ("Stopping and disposing sessions are idempotent", StopAndDispose);
        yield return ("Failed startup stops and releases a pumped session", StartupFailure);
        yield return ("Constructor failures release pumped session contexts", ConstructorFailure);
        yield return ("Failed ticks stop without counting incomplete work", TickFailure);
        yield return ("Pumped stop failures still release resources", StopFailure);
        yield return ("Caught cooperative violations stop pumped sessions", CaughtQuota);
        yield return ("Author error message failures cannot interrupt pumped cleanup", ThrowingErrorMessage);
        yield return ("Overlapping pumped sessions keep independent state", OverlappingSessions);
        yield return ("Concurrent host ticks are serialized", ConcurrentTicks);
        yield return ("A retained stopped session does not retain author code", RetainedSession);
        yield return ("Pumped required interpretation rejects before author loading", RequiredPolicy);
    }

    private static void ManualCadence()
    {
        using var session = Start("ManualTickMap", new MapRunOptions
        {
            TickCount = 0,
            TickDuration = TimeSpan.FromMilliseconds(17)
        });
        Check(session.IsRunning && session.Result is null && session.CompletedTicks == 0, "Startup consumed ticks or completed the session.");
        Check(session.Tick(TimeSpan.FromMilliseconds(5)), "First host tick failed.");
        Check(session.Tick(), "Default-duration host tick failed.");
        Check(session.IsRunning && session.Result is null && session.CompletedTicks == 2, "TickCount limited a manually pumped session.");
        var result = session.Stop();
        Check(result.Report.Logs.SequenceEqual(new[] { "started", "tick=0:delta=50000", "tick=1:delta=170000", "stopped" }),
            "The host tick index, duration, or lifecycle order changed.");
        Check(result.Report.CompletedTicks == 2, "Report omitted completed host ticks.");
        CheckCompleted(result);
        CheckReleased(result);
    }

    private static void InvalidDelta()
    {
        using var session = Start("ManualTickMap");
        Expect<ArgumentOutOfRangeException>(() => session.Tick(TimeSpan.Zero));
        Expect<ArgumentOutOfRangeException>(() => session.Tick(TimeSpan.FromTicks(-1)));
        Check(session.IsRunning && session.Result is null && session.CompletedTicks == 0, "Invalid delta altered the session.");
        Check(session.Tick(TimeSpan.FromTicks(1)), "Valid tick failed after rejected deltas.");
        var result = session.Stop();
        Check(result.Report.Logs.SequenceEqual(new[] { "started", "tick=0:delta=1", "stopped" }), "Rejected deltas reached author code.");
        CheckCompleted(result);
        CheckReleased(result);
    }

    private static void StopAndDispose()
    {
        var session = Start("CounterMap");
        var result = session.Stop();
        Check(ReferenceEquals(result, session.Stop()), "Repeated Stop replaced the completed result.");
        session.Dispose();
        session.Dispose();
        Check(!session.IsRunning && ReferenceEquals(result, session.Result), "Disposal changed terminal state.");
        Expect<InvalidOperationException>(() => session.Tick());
        Check(result.Report.CompletedTicks == 0 && result.Report.Logs.SequenceEqual(new[] { "starts=1", "stopped" }),
            "Stop or Dispose ran additional ticks or callbacks.");
        CheckCompleted(result);
        CheckReleased(result);

        var disposed = Start("CounterMap");
        disposed.Dispose();
        var disposedResult = disposed.Result ?? throw new InvalidOperationException("Dispose did not finish the session.");
        Check(ReferenceEquals(disposedResult, disposed.Stop()), "Stop after Dispose replaced the result.");
        Check(disposedResult.Report.CompletedTicks == 0, "Dispose pumped author ticks.");
        CheckCompleted(disposedResult);
        CheckReleased(disposedResult);
    }

    private static void StartupFailure()
    {
        using var session = Start("StartThrowingMap");
        Check(!session.IsRunning && session.CompletedTicks == 0, "Failed OnStart left the session running.");
        var result = session.Result ?? throw new InvalidOperationException("Startup failure has no result.");
        CheckFailed(result, "MapDefinedException");
        Check(result.Report.Logs.SequenceEqual(new[] { "stopped-after-start-error" }), "OnStop was not attempted after failed startup.");
        Check(ReferenceEquals(result, session.Stop()), "Stop changed the startup failure result.");
        CheckReleased(result);
    }

    private static void TickFailure()
    {
        using var session = Start("ThrowAfterFirstTickMap");
        Check(session.Tick(), "The successful first tick failed.");
        Check(!session.Tick(), "Author failure was reported as a completed tick.");
        Check(!session.IsRunning && session.CompletedTicks == 1, "Failed tick was counted or session remained active.");
        var result = session.Result ?? throw new InvalidOperationException("Tick failure has no result.");
        CheckFailed(result, "MapDefinedException");
        Check(result.Report.CompletedTicks == 1 && result.Report.Logs.SequenceEqual(new[] { "stopped-after-tick-error" }),
            "Failed tick lost prior progress or skipped OnStop.");
        Expect<InvalidOperationException>(() => session.Tick());
        CheckReleased(result);
    }

    private static void ConstructorFailure()
    {
        using var session = Start("ConstructorThrowingMap");
        Check(!session.IsRunning && session.CompletedTicks == 0, "Constructor failure left the session active.");
        var result = session.Result ?? throw new InvalidOperationException("Constructor failure has no result.");
        CheckFailed(result, "MapDefinedException");
        CheckReleased(result);
    }

    private static void ThrowingErrorMessage()
    {
        using var session = Start("ThrowingMessageMap");
        Check(!session.Tick(), "Throwing exception Message escaped failure reporting.");
        var result = session.Result ?? throw new InvalidOperationException("Error reporting left the session without a result.");
        Check(!session.IsRunning, "Error reporting left the session active.");
        CheckFailed(result, "ThrowingMessageException");
        Check(result.Report.Error?.Contains("OnStop:", StringComparison.Ordinal) == true, "OnStop failure was lost when its Message threw.");
        CheckReleased(result);
    }

    private static void StopFailure()
    {
        using var session = Start("StopThrowingMap");
        Check(session.Tick(), "Tick failed before OnStop.");
        var result = session.Stop();
        CheckFailed(result, "OnStop:");
        Check(!session.IsRunning && session.CompletedTicks == 1 && ReferenceEquals(result, session.Result), "Stop failure left inconsistent state.");
        CheckReleased(result);
    }

    private static void CaughtQuota()
    {
        using var startup = Start("CatchingBudgetMap");
        Check(!startup.IsRunning, "Caught startup quota left the session active.");
        var startupResult = startup.Result ?? throw new InvalidOperationException("Caught startup quota has no result.");
        CheckFailed(startupResult, "operation budget");
        CheckReleased(startupResult);

        using var ticking = Start("TickCatchingBudgetMap");
        Check(!ticking.Tick(), "Caught tick quota counted as a successful callback.");
        var tickResult = ticking.Result ?? throw new InvalidOperationException("Caught tick quota has no result.");
        Check(!ticking.IsRunning && ticking.CompletedTicks == 0, "Caught tick quota left the session active.");
        CheckFailed(tickResult, "operation budget");
        CheckReleased(tickResult);
    }

    private static void OverlappingSessions()
    {
        var runner = new MapRunner();
        for (var iteration = 0; iteration < 3; iteration++)
        {
            using var first = Start("CounterMap", runner: runner);
            using var second = Start("CounterMap", runner: runner);
            Check(first.Tick() && second.Tick() && first.Tick(), "Interleaved ticks failed.");
            var firstResult = first.Stop();
            Check(second.IsRunning && second.Result is null && second.CompletedTicks == 1, "Stopping one session altered another.");
            Check(second.Tick(), "Surviving session failed after the other stopped.");
            var secondResult = second.Stop();
            foreach (var result in new[] { firstResult, secondResult })
            {
                CheckCompleted(result);
                Check(result.Report.Logs.SequenceEqual(new[] { "starts=1", "tick=0", "tick=1", "stopped" }), "Session static state or tick index was shared.");
                CheckReleased(result);
            }
        }
    }

    private static void ConcurrentTicks()
    {
        using var session = Start("CounterMap");
        Parallel.For(0, 20, _ => Check(session.Tick(), "Concurrent tick failed."));
        var result = session.Stop();
        CheckCompleted(result);
        Check(result.Report.CompletedTicks == 20 && result.Report.Logs.Skip(1).Take(20).SequenceEqual(Enumerable.Range(0, 20).Select(index => $"tick={index}")),
            "Concurrent ticks overlapped or lost tick indices.");
        CheckReleased(result);
    }

    private static void RetainedSession()
    {
        var session = CreateStoppedSession();
        var result = session.Result ?? throw new InvalidOperationException("Stopped session has no result.");
        CheckCompleted(result);
        CheckReleased(result);
        GC.KeepAlive(session);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static MapSession CreateStoppedSession()
    {
        var session = Start("CounterMap");
        Check(session.Tick(), "Retained-session tick failed.");
        session.Stop();
        return session;
    }

    private static void RequiredPolicy()
    {
        var version = typeof(System.Runtime.Loader.AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicyVersion",
            BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
        var supported = version is not null && version.ReturnType == typeof(int) && version.CreateDelegate<Func<int>>()() == 1;
        var loads = 0;
        void Observe(object? sender, AssemblyLoadEventArgs loaded)
        {
            if (loaded.LoadedAssembly.IsCollectible && loaded.LoadedAssembly.GetName().Name == "RuneCLR.TestMaps") loads++;
        }
        AppDomain.CurrentDomain.AssemblyLoad += Observe;
        try
        {
            if (supported)
            {
                using var session = new MapRunner().Start(Package("CounterMap"),
                    new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter });
                Check(session.IsRunning && session.Tick(), "Supported required policy failed to start or tick.");
                var result = session.Stop();
                Check(result.Report.Outcome == MapRunOutcome.Completed && result.Report.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter
                    && result.Report.ExecutionPolicyVersion == 1, "Pumped session did not acknowledge required interpretation.");
                Check(loads == 1 && result.Report.Logs.SequenceEqual(new[] { "starts=1", "tick=0", "stopped" }),
                    "Required pumped session did not execute fresh author state.");
                CheckReleased(result);
                return;
            }
            Expect<PlatformNotSupportedException>(() => new MapRunner().Start(Package("CounterMap"),
                new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter }));
            Check(loads == 0, "Pumped required policy loaded author IL before rejection.");
        }
        finally { AppDomain.CurrentDomain.AssemblyLoad -= Observe; }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static MapSession Start(string type, MapRunOptions? options = null, MapRunner? runner = null) =>
        (runner ?? new MapRunner()).Start(Package(type),
            (options ?? new MapRunOptions()) with { ExecutionPolicy = RuntimeTestSettings.ExecutionPolicy });

    private static MapPackage Package(string type) => new("fixture",
        Path.Combine(AppContext.BaseDirectory, "fixtures", "RuneCLR.TestMaps.dll"), $"RuneCLR.TestMaps.{type}");

    private static void CheckCompleted(MapRunResult result)
    {
        Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Pumped session failed.");
        CheckPolicy(result);
    }

    private static void CheckFailed(MapRunResult result, string expectedError)
    {
        Check(result.Report.Outcome == MapRunOutcome.Failed, "Author failure completed successfully.");
        Check(result.Report.Error?.Contains(expectedError, StringComparison.Ordinal) == true, "Missing author failure description.");
        CheckPolicy(result);
    }

    private static void CheckPolicy(MapRunResult result)
    {
        Check(result.Report.ExecutionPolicy == RuntimeTestSettings.ExecutionPolicy, "Pumped session lost the requested execution policy.");
        Check(result.Report.ExecutionPolicyVersion == (RuntimeTestSettings.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter ? 1 : 0),
            "Pumped session reported the wrong native policy acknowledgment.");
        Check(result.Report.PrototypeBudget is null, "Pumped session unexpectedly acquired a native instruction budget.");
    }

    private static void CheckReleased(MapRunResult result)
    {
        Check(result.Report.RemainingEntities == 0 && result.Report.CreatedEntities == result.Report.ReleasedEntities, "Pumped session leaked host entities.");
        for (var attempt = 0; attempt < 10 && !result.Unload.IsCollected; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }
        Check(result.Unload.IsCollected, "Stopped pumped session retained its collectible context.");
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private static void Expect<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }
}
