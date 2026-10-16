using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR;
using RuneCLR.Runtime;

internal static class SessionTests
{
    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host-pumped sessions obey host tick cadence and delta", ManualCadence);
        yield return ("A map signal closes when its callback returns", ClosedMapSignal);
        yield return ("A host tick schedule survives the callback and stop cancels it", ScheduledSignal);
        yield return ("A repeating tick schedule stays one slot and a one-shot schedule does not repeat", RepeatingSchedule);
        yield return ("The host posts a subscribed event between callbacks and stop drops it", HostPostedEvent);
        yield return ("Duplicate and negative subscriptions are rejected", PostedEventRejects);
        yield return ("Overlapping sessions do not share posted events", OverlappingPosts);
        yield return ("A closed callback cannot change host entities or logs", ClosedResources);
        yield return ("The host can copy live entities between callbacks", HostEntitySnapshot);
        yield return ("The host completes or fails work between callbacks and stop drops the rest", HostCompletedWork);
        yield return ("The host copies registered resources between callbacks and stop drops them", HostRegisteredResources);
        yield return ("Author failure cancels work the host has not finished", AuthorFailureCancelsWork);
        yield return ("A retired session does not block the next session's work", NextSessionAfterFailedWork);
        yield return ("A retired session does not leave scheduled signals for the next session", NextSessionAfterFailedSchedule);
        yield return ("Caught work and schedule limits still stop the session", CaughtResourceLimits);
        yield return ("A caught resource limit stops the session and drops the accepted name", CaughtResourceLimit);
        yield return ("Invalid tick deltas leave the session active", InvalidDelta);
        yield return ("Stopping and disposing sessions are idempotent", StopAndDispose);
        yield return ("Failed startup stops and releases a pumped session", StartupFailure);
        yield return ("Constructor failures release pumped session contexts", ConstructorFailure);
        yield return ("Failed ticks stop without counting incomplete work", TickFailure);
        yield return ("Pumped stop failures still release resources", StopFailure);
        yield return ("Caught cooperative violations stop pumped sessions", CaughtQuota);
        yield return ("Author error message failures cannot interrupt pumped cleanup", ThrowingErrorMessage);
        yield return ("Overlapping pumped sessions keep independent state", OverlappingSessions);
        yield return ("Overlapping sessions keep independent host work", OverlappingWork);
        yield return ("Overlapping sessions do not share registered resources", OverlappingResources);
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

    private static void ClosedMapSignal()
    {
        using var session = Start("SignalMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "Signal tick failed.");
        Check(LateSignalRejected(), "A closed map signal still ran or accepted a subscriber.");
        var result = session.Stop();
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["seen=4", "stopped"]), "The closed signal changed the callback log.");
        CheckReleased(result);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateSignalRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.SignalMap")
            ?? throw new InvalidOperationException("SignalMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        var raised = false;
        try
        {
            kept.RaiseSignal(9);
        }
        catch (InvalidOperationException exception) when (exception.Message == "The map signal is closed.")
        {
            raised = true;
        }

        var subscribed = false;
        try
        {
            kept.Signal += ClosedProbe;
        }
        catch (InvalidOperationException exception) when (exception.Message == "The map signal is closed.")
        {
            subscribed = true;
        }

        var seen = (int)(map.GetField("Seen", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
            ?? throw new InvalidOperationException("SignalMap did not expose Seen."));
        return raised && subscribed && seen == 4;
    }

    private static void ClosedProbe(int value)
    {
    }

    private static void RepeatingSchedule()
    {
        using var repeat = Start("RepeatMap", new MapRunOptions { TickCount = 0 });
        Check(repeat.Tick() && repeat.Tick() && repeat.Tick(), "Repeat ticks failed.");
        var repeatResult = repeat.Stop();
        CheckCompleted(repeatResult);
        Check(repeatResult.Report.Logs.SequenceEqual(["t0 pending=1", "t1 pending=1", "t2 pending=1", "stop=0"]),
            "Repeat did not stay on one slot or survive stop.");
        CheckReleased(repeatResult);

        using var once = Start("OneShotMap", new MapRunOptions { TickCount = 0 });
        Check(once.Tick() && once.Tick() && once.Tick(), "One-shot ticks failed.");
        var onceResult = once.Stop();
        CheckCompleted(onceResult);
        Check(onceResult.Report.Logs.SequenceEqual(["s0 pending=1", "s1 value=4 pending=0", "s2 took=false", "stop=0"]),
            "A one-shot schedule repeated.");
        CheckReleased(onceResult);
    }

    private static void ScheduledSignal()
    {
        using var session = Start("TimerMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "The first scheduled tick failed.");
        Check(LateScheduleRejected(), "A closed callback accepted another scheduled signal.");
        Check(session.Tick(), "The second scheduled tick failed.");
        var result = session.Stop();
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["tick=0:taken=4", "tick=1:taken=9", "pending=0"]),
            "A scheduled signal was delivered early, kept after stop, or accepted a zero delay.");
        CheckReleased(result);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateScheduleRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.TimerMap")
            ?? throw new InvalidOperationException("TimerMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        var scheduled = false;
        var repeated = false;
        var taken = false;
        var counted = false;
        try { kept.Schedule(1, 7); }
        catch (InvalidOperationException exception) when (exception.Message == "The map schedule is closed.")
        { scheduled = true; }
        try { kept.Repeat(1, 3); }
        catch (InvalidOperationException exception) when (exception.Message == "The map schedule is closed.")
        { repeated = true; }
        try { kept.TryTakeScheduled(out _); }
        catch (InvalidOperationException exception) when (exception.Message == "The map schedule is closed.")
        { taken = true; }
        try { _ = kept.PendingScheduled; }
        catch (InvalidOperationException exception) when (exception.Message == "The map schedule is closed.")
        { counted = true; }
        return scheduled && repeated && taken && counted;
    }

    private static void ClosedResources()
    {
        using var session = Start("ResourceMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "Resource tick failed.");
        Check(LateResourceRejected(), "A closed callback changed host resources.");
        var result = session.Stop();
        CheckCompleted(result);
        Check(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0,
            "The host did not release the entity created during the callback.");
        Check(result.Report.Logs.SequenceEqual(["spawned", "stopped"]), "A closed callback wrote a host log.");
        CheckReleased(result);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateResourceRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.ResourceMap")
            ?? throw new InvalidOperationException("ResourceMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        var entity = (long)(map.GetField("KeptEntity", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
            ?? throw new InvalidOperationException("ResourceMap did not retain its entity."));
        var spawned = RejectClosed(() => kept.SpawnEntity("late"));
        var logged = RejectClosed(() => kept.Log("late"));
        var destroyed = RejectClosed(() => kept.DestroyEntity(new EntityId(entity)));
        var charged = RejectClosed(() => kept.Charge());
        return entity > 0 && spawned && logged && destroyed && charged;
    }

    private static void HostEntitySnapshot()
    {
        using var session = Start("HostViewMap", new MapRunOptions { TickCount = 0 });
        Check(session.CopyEntities().Length == 0, "Startup published an entity before a tick.");
        Check(session.Tick(), "The first host-view tick failed.");
        var first = session.CopyEntities();
        Check(first.Length == 1 && first[0].Name == "kept" && first[0].Id.Value > 0, "The host snapshot missed the live entity.");
        Check(session.Tick(), "The replacement tick failed.");
        var second = session.CopyEntities();
        Check(first.Length == 1 && first[0].Name == "kept", "A later tick mutated the earlier host snapshot.");
        Check(second.Length == 1 && second[0].Name == "next" && second[0].Id != first[0].Id, "The live snapshot did not replace the entity.");
        var result = session.Stop();
        Expect<InvalidOperationException>(() => session.CopyEntities());
        CheckCompleted(result);
        Check(result.Report.CreatedEntities == 2 && result.Report.ReleasedEntities == 2 && result.Report.RemainingEntities == 0,
            "The host snapshot changed entity release.");
        Check(result.Report.Logs.SequenceEqual(["spawned", "replaced", "stopped"]), "The host snapshot changed the callback log.");
        CheckReleased(result);
    }

    private static void HostCompletedWork()
    {
        using var session = Start("HostWorkMap", new MapRunOptions { TickCount = 0 });
        Check(session.CopyPendingWork().Length == 0, "Startup published work before a request.");
        Check(session.Tick(), "The work request tick failed.");
        Check(LateWorkRejected(), "A closed callback accepted another work request.");
        var open = session.CopyPendingWork();
        var load = open.Single(item => item.Name == "load");
        var bad = open.Single(item => item.Name == "bad");
        Check(load.Id > 0 && bad.Id != load.Id, "The host did not see both work requests.");
        Expect<ArgumentException>(() => session.CompleteWork(load.Id + 99, 1));
        session.CompleteWork(load.Id, 4);
        session.FailWork(bad.Id, 9);
        Expect<InvalidOperationException>(() => session.CompleteWork(load.Id, 5));
        Expect<InvalidOperationException>(() => session.FailWork(bad.Id, 3));
        Check(!HoldsException(session), "Failed work retained an exception.");
        Check(session.CopyPendingWork().Length == 0, "Finished work stayed pending.");
        Check(session.Tick(), "The work result tick failed.");
        Expect<ArgumentException>(() => session.FailWork(bad.Id, 9));
        var later = session.CopyPendingWork();
        Check(later.Length == 1 && later[0].Name == "later" && later[0].Id != load.Id && later[0].Id != bad.Id,
            "The untaken request was lost before stop.");
        var result = session.Stop();
        Expect<InvalidOperationException>(() => session.FailWork(later[0].Id, 9));
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["requested", "taken=4:failed=9", "pending=0"]),
            "Work was delivered without the host, kept a failure object, or ran during OnStop.");
        CheckReleased(result);
    }

    private static void HostRegisteredResources()
    {
        using var session = Start("HostResourceMap", new MapRunOptions { TickCount = 0 });
        Check(session.CopyResources().Length == 0, "Startup published a resource.");
        Check(session.Tick(), "The resource registration tick failed.");
        Check(LateRegisteredResourceRejected(), "A closed callback accepted another resource.");
        var names = session.CopyResources().Select(item => item.Name).ToArray();
        Check(names.Length == 2 && names.Contains("alpha") && names.Contains("beta"),
            "The host did not see both registered resources.");
        Check(session.Tick(), "The resource release tick failed.");
        var left = session.CopyResources();
        Check(left.Length == 1 && left[0].Name == "beta", "Release did not keep the other resource.");
        var result = session.Stop();
        Expect<InvalidOperationException>(() => session.CopyResources());
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["registered", "pending=1", "pending=0"]),
            "Stop did not drop the remaining resource before OnStop.");
        CheckReleased(result);

        using var next = Start("HostResourceMap", new MapRunOptions { TickCount = 0 });
        Check(next.CopyResources().Length == 0, "The next session saw a retired resource.");
        next.Stop();
    }

    private static void AuthorFailureCancelsWork()
    {
        using var session = Start("FaultingWorkMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "The work request tick failed.");
        var open = session.CopyPendingWork();
        Check(open.Length == 1 && open[0].Name == "load" && open[0].Id > 0, "The host did not see the open request.");
        Check(!session.Tick(), "Author failure was reported as a completed tick.");
        Check(!session.IsRunning && session.CompletedTicks == 1, "The failed tick stayed active or counted the incomplete callback.");
        Expect<InvalidOperationException>(() => session.CompleteWork(open[0].Id, 4));
        Expect<InvalidOperationException>(() => session.FailWork(open[0].Id, 9));
        Expect<InvalidOperationException>(() => session.CopyPendingWork());
        var result = session.Result ?? throw new InvalidOperationException("Author failure has no result.");
        CheckFailed(result, "MapDefinedException");
        Check(result.Report.Logs.SequenceEqual(["requested", "requested-again", "pending=0:0"]),
            "Author failure left work or a scheduled signal for the host.");
        Check(result.Report.CompletedTicks == 1, "The successful request tick was discarded.");
        CheckReleased(result);
    }

    private static void NextSessionAfterFailedWork()
    {
        long failedId;
        using (var failed = Start("FaultingWorkMap", new MapRunOptions { TickCount = 0 }))
        {
            Check(failed.Tick(), "The request before author failure failed.");
            failedId = failed.CopyPendingWork().Single(item => item.Name == "load").Id;
            Check(!failed.Tick(), "Author failure did not stop the first session.");
            Expect<InvalidOperationException>(() => failed.CompleteWork(failedId, 4));
            var failedResult = failed.Result ?? throw new InvalidOperationException("Failed work session has no result.");
            CheckFailed(failedResult, "MapDefinedException");
            CheckReleased(failedResult);
        }

        using var next = Start("HostWorkMap", new MapRunOptions { TickCount = 0 });
        Check(next.Tick(), "The next session did not accept work.");
        var load = next.CopyPendingWork().Single(item => item.Name == "load");
        var bad = next.CopyPendingWork().Single(item => item.Name == "bad");
        Check(load.Id == failedId, "The next session did not reuse a retired work id.");
        next.CompleteWork(load.Id, 4);
        next.FailWork(bad.Id, 9);
        Check(next.Tick(), "The next session did not take its own result.");
        var result = next.Stop();
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["requested", "taken=4:failed=9", "pending=0"]),
            "A retired session's cancelled work changed the next session.");
        CheckReleased(result);
    }

    private static void NextSessionAfterFailedSchedule()
    {
        using (var failed = Start("FaultingWorkMap", new MapRunOptions { TickCount = 0 }))
        {
            Check(failed.Tick() && !failed.Tick(), "The schedule owner did not fail on its second tick.");
            var failedResult = failed.Result ?? throw new InvalidOperationException("Failed schedule session has no result.");
            CheckFailed(failedResult, "MapDefinedException");
            Check(failedResult.Report.Logs.Contains("pending=0:0"), "The failed session left a scheduled signal pending.");
            CheckReleased(failedResult);
        }

        using var next = Start("NextScheduleMap", new MapRunOptions { TickCount = 0 });
        Check(next.Tick() && next.Tick() && next.Tick(), "The next session did not take its own scheduled signal.");
        var result = next.Stop();
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["tick=0:taken=6", "tick=1:taken=none", "tick=2:taken=none", "pending=0"]),
            "A retired session's cancelled signal was delivered to the next session.");
        CheckReleased(result);
    }

    private static void CaughtResourceLimits()
    {
        using (var work = Start("CatchingWorkLimitMap", new MapRunOptions { MaxWorkItems = 1, TickCount = 0 }))
        {
            Check(!work.IsRunning && work.CompletedTicks == 0, "A caught work limit left the session active.");
            var result = work.Result ?? throw new InvalidOperationException("Caught work limit has no result.");
            CheckFailed(result, "work limit");
            Check(result.Report.Error?.Contains("pending-work", StringComparison.Ordinal) != true, "The accepted work request survived the limit.");
            Check(result.Report.Error?.Contains("OnStop:", StringComparison.Ordinal) != true, "A successful OnStop was reported as a stop failure.");
            Expect<InvalidOperationException>(() => work.CompleteWork(1, 4));
            Expect<InvalidOperationException>(() => work.FailWork(1, 9));
            CheckReleased(result);
        }

        using var schedule = Start("CatchingScheduleLimitMap", new MapRunOptions { MaxScheduledSignals = 1, TickCount = 0 });
        Check(!schedule.IsRunning && schedule.CompletedTicks == 0, "A caught schedule limit left the session active.");
        var scheduleResult = schedule.Result ?? throw new InvalidOperationException("Caught schedule limit has no result.");
        CheckFailed(scheduleResult, "scheduled signal limit");
        Check(scheduleResult.Report.Error?.Contains("pending-schedule", StringComparison.Ordinal) != true, "The accepted signal survived the limit.");
        Check(scheduleResult.Report.Error?.Contains("OnStop:", StringComparison.Ordinal) != true, "A successful OnStop was reported as a stop failure.");
        CheckReleased(scheduleResult);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateWorkRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.HostWorkMap")
            ?? throw new InvalidOperationException("HostWorkMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        try
        {
            kept.RequestWork("late");
        }
        catch (InvalidOperationException exception) when (exception.Message == "The map callback is closed.")
        {
            return true;
        }

        return false;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateRegisteredResourceRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.HostResourceMap")
            ?? throw new InvalidOperationException("HostResourceMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        return RejectClosed(() => kept.RegisterResource("late"))
            && RejectClosed(() => kept.ReleaseResource("late"))
            && RejectClosed(() => _ = kept.PendingResources);
    }

    private static bool RejectClosed(Action call)
    {
        try { call(); }
        catch (InvalidOperationException exception) when (exception.Message == "The map callback is closed.")
        {
            return true;
        }

        return false;
    }

    private static void CaughtResourceLimit()
    {
        using var session = Start("CatchingResourceLimitMap", new MapRunOptions { MaxResources = 1, TickCount = 0 });
        Check(!session.IsRunning && session.CompletedTicks == 0, "A caught resource limit left the session active.");
        var result = session.Result ?? throw new InvalidOperationException("Caught resource limit has no result.");
        CheckFailed(result, "resource limit");
        Check(result.Report.Error?.Contains("pending-resource", StringComparison.Ordinal) != true, "The accepted resource survived the limit.");
        Check(result.Report.Error?.Contains("OnStop:", StringComparison.Ordinal) != true, "A successful OnStop was reported as a stop failure.");
        Expect<InvalidOperationException>(() => session.CopyResources());
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

    private static void OverlappingResources()
    {
        using var first = Start("HostResourceMap", new MapRunOptions { TickCount = 0 });
        using var second = Start("HostResourceMap", new MapRunOptions { TickCount = 0 });
        Check(first.Tick() && second.Tick(), "The overlapping resource registrations failed.");
        Check(Names(first).Order().SequenceEqual(["alpha", "beta"]), "The first session did not register both names.");
        Check(Names(second).Order().SequenceEqual(["alpha", "beta"]), "The second session did not register both names.");
        Check(first.Tick(), "The first session did not release its own resource.");
        Check(Names(first).SequenceEqual(["beta"]), "Release removed another session's resource or the wrong name.");
        Check(Names(second).Order().SequenceEqual(["alpha", "beta"]), "The other session changed while the first released a name.");
        var firstResult = first.Stop();
        Expect<InvalidOperationException>(() => first.CopyResources());
        Check(second.IsRunning && second.Result is null, "Stopping one session stopped the other.");
        Check(Names(second).Order().SequenceEqual(["alpha", "beta"]), "Stopping one session dropped the other's resources.");
        var secondResult = second.Stop();
        Expect<InvalidOperationException>(() => second.CopyResources());
        CheckCompleted(firstResult);
        CheckCompleted(secondResult);
        Check(firstResult.Report.Logs.SequenceEqual(["registered", "pending=1", "pending=0"]),
            "The releasing session did not keep its own resource log.");
        Check(secondResult.Report.Logs.SequenceEqual(["registered", "pending=0"]),
            "The untouched session released a name or kept one after Stop.");
        CheckReleased(firstResult);
        CheckReleased(secondResult);
    }

    private static string[] Names(MapSession session) => session.CopyResources().Select(item => item.Name).ToArray();

    private static void OverlappingWork()
    {
        using var first = Start("HostWorkMap", new MapRunOptions { TickCount = 0 });
        using var second = Start("HostWorkMap", new MapRunOptions { TickCount = 0 });
        Check(first.Tick() && second.Tick(), "The overlapping work requests failed.");
        var firstLoad = first.CopyPendingWork().Single(item => item.Name == "load");
        var firstBad = first.CopyPendingWork().Single(item => item.Name == "bad");
        first.CompleteWork(firstLoad.Id, 4);
        first.FailWork(firstBad.Id, 9);
        Check(second.CopyPendingWork().Select(item => item.Name).Order().SequenceEqual(["bad", "load"]),
            "Completing one session finished the other session's work.");
        Check(first.Tick(), "The completed session did not take its own result.");
        Check(first.CopyPendingWork().Select(item => item.Name).SequenceEqual(["later"]),
            "The completed session did not keep its own later request.");
        Check(second.CopyPendingWork().Select(item => item.Name).Order().SequenceEqual(["bad", "load"]),
            "The other session changed while the first ticked.");
        var secondLoad = second.CopyPendingWork().Single(item => item.Name == "load");
        var secondBad = second.CopyPendingWork().Single(item => item.Name == "bad");
        second.CompleteWork(secondLoad.Id, 4);
        second.FailWork(secondBad.Id, 9);
        Check(second.Tick(), "The second session did not take its own result.");
        var firstResult = first.Stop();
        Check(second.IsRunning && second.Result is null, "Stopping one session stopped the other.");
        var secondResult = second.Stop();
        foreach (var result in new[] { firstResult, secondResult })
        {
            CheckCompleted(result);
            Check(result.Report.Logs.SequenceEqual(["requested", "taken=4:failed=9", "pending=0"]),
                "Overlapping sessions shared a work result.");
            CheckReleased(result);
        }
    }

    private static void HostPostedEvent()
    {
        using var session = Start("PostedEventMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "The subscribe tick failed.");
        Check(LateSubscribeRejected(), "A closed callback accepted another subscription.");
        Expect<ArgumentException>(() => session.Post(5, 1));
        session.Post(4, 9);
        Check(session.Tick(), "The posted event tick failed.");
        var result = session.Stop();
        try
        {
            session.Post(4, 1);
            throw new InvalidOperationException("Post after stop succeeded.");
        }
        catch (InvalidOperationException exception) when (exception.Message == "The session has stopped.")
        {
        }

        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["subscribed", "taken=4:9", "pending=0"]),
            "A posted event was delivered without a subscription, kept after stop, or left pending.");
        CheckReleased(result);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool LateSubscribeRejected()
    {
        var assembly = AssemblyLoadContext.All
            .SelectMany(context => context.Assemblies)
            .Single(item => item.IsCollectible && item.GetName().Name == "RuneCLR.TestMaps");
        var map = assembly.GetType("RuneCLR.TestMaps.PostedEventMap")
            ?? throw new InvalidOperationException("PostedEventMap was not loaded.");
        var kept = map.GetField("Kept", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IMapContext
            ?? throw new InvalidOperationException("The map did not retain its context.");
        return RejectClosed(() => kept.Subscribe(8));
    }

    private static void OverlappingPosts()
    {
        using var first = Start("PostedEventMap", new MapRunOptions { TickCount = 0 });
        using var second = Start("PostedEventMap", new MapRunOptions { TickCount = 0 });
        Check(first.Tick() && second.Tick(), "The overlapping subscriptions failed.");
        first.Post(4, 9);
        Check(first.Tick(), "The first session did not take its own post.");
        Check(second.Tick(), "The second session failed before its own post.");
        second.Post(4, 8);
        Check(second.Tick(), "The second session did not take its own post.");
        Check(first.Tick(), "The first session failed after the other post.");
        var firstResult = first.Stop();
        Check(second.IsRunning && second.Result is null, "Stopping one session stopped the other.");
        var secondResult = second.Stop();
        CheckCompleted(firstResult);
        Check(firstResult.Report.Logs.SequenceEqual(["subscribed", "taken=4:9", "mismatch", "pending=0"]),
            "The first session did not keep its own posted value.");
        CheckReleased(firstResult);
        CheckCompleted(secondResult);
        Check(secondResult.Report.Logs.SequenceEqual(["subscribed", "mismatch", "taken=4:8", "pending=0"]),
            "The second session saw the other post or missed its own.");
        CheckReleased(secondResult);
    }

    private static void PostedEventRejects()
    {
        using var session = Start("PostedEventRejectMap", new MapRunOptions { TickCount = 0 });
        Check(session.Tick(), "The subscription rejection tick failed.");
        var result = session.Stop();
        CheckCompleted(result);
        Check(result.Report.Logs.SequenceEqual(["duplicate-rejected", "negative-rejected", "pending=0"]),
            "Duplicate or negative subscriptions were accepted or left pending.");
        CheckReleased(result);
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

    private static bool HoldsException(object instance)
    {
        var seen = new HashSet<object>(ReferenceEqualityComparer.Instance);
        return HoldsException(instance, seen);
    }

    private static bool HoldsException(object? instance, HashSet<object> seen)
    {
        if (instance is null or string or int or long or bool) return false;
        if (instance is Exception) return true;
        if (!seen.Add(instance)) return false;
        if (instance is System.Collections.IEnumerable enumerable)
        {
            foreach (var item in enumerable)
            {
                if (HoldsException(item, seen)) return true;
            }
        }

        var type = instance.GetType();
        if (type.Namespace != "RuneCLR.Runtime") return false;
        foreach (var field in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
        {
            if (HoldsException(field.GetValue(instance), seen)) return true;
        }

        return false;
    }

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
