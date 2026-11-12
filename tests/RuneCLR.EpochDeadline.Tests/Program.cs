using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.Runtime;

internal static class Program
{
    private static string AuthorPath => Path.Combine(AppContext.BaseDirectory, "epoch-author", "EpochDeadline.Author.dll");

    private static MapRunOptions Options(string mode, int periodMicros = 10_000, int deadlineMs = 1_000, int poll = 100)
    {
        var options = new MapRunOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(deadlineMs),
            PrototypeDeadlinePollInterval = poll,
            TickCount = 0,
            MaxLogMessages = 512
        };
        return DeadlineApi.WithMode(options, mode, periodMicros);
    }

    private static MapRunOptions Off() => new() { TickCount = 0, MaxLogMessages = 512 };

    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--fault") return FaultMode(args[1]);
        if (args.Length == 2 && args[0] == "--fault-stop") return FaultDuringLastStop(args[1]);
        if (args.Length == 2 && args[0] == "--sanity") return Sanity(args[1]);
        var filter = args.Length > 0 ? args[0] : null;
        var cases = Cases().Where(item => filter is null || item.Name.Contains(filter, StringComparison.OrdinalIgnoreCase)).ToList();
        var passed = 0;
        var skipped = 0;
        var failed = 0;
        foreach (var (name, run) in cases)
        {
            try
            {
                run();
                passed++;
                Console.WriteLine("PASS " + name);
            }
            catch (SkipException error)
            {
                skipped++;
                Console.WriteLine("SKIP " + name + " :: " + error.Message);
            }
            catch (Exception error)
            {
                failed++;
                Console.WriteLine("FAIL " + name + " :: " + error.GetType().Name + ": " + error.Message +
                                  " @ " + (error.StackTrace ?? "").Split('\n').FirstOrDefault());
            }
        }

        Console.WriteLine("EPOCH_DEADLINE_TESTS passed=" + passed + " skipped=" + skipped + " failed=" + failed);
        return failed == 0 ? 0 : 1;
    }

    /// <summary>Separate-process deadlock probe: the fault fires while the last lease is
    /// being stopped. A hang is a failure; the driver also applies a hard watchdog.</summary>
    private static int Sanity(string mode)
    {
        if (mode != "clock" && mode != "epoch") { Console.WriteLine("FAIL sanity mode " + mode); return 2; }
        if (mode == "epoch" && (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge))
        { Console.WriteLine("SKIP native epoch is not available"); return 3; }
        foreach (var deadline in new[] { 100, 1000, 5000 })
        {
            using var process = System.Diagnostics.Process.GetCurrentProcess();
            process.Refresh();
            var cpuBefore = process.TotalProcessorTime;
            var watch = System.Diagnostics.Stopwatch.StartNew();
            using var session = new MapRunner().Start(Package("EpochDeadline.Author.TickOnlyLong"),
                Options(mode, 10_000, deadlineMs: deadline, poll: 100));
            var ok = session.Tick();
            watch.Stop();
            var result = session.Stop();
            process.Refresh();
            var cpu = (process.TotalProcessorTime - cpuBefore).TotalMilliseconds;
            var snapshot = result.Report.PrototypeDeadline;
            Console.WriteLine("SANITY mode=" + mode + " deadlineMs=" + deadline +
                              " tripped=" + (!ok) + " wallMs=" + watch.Elapsed.TotalMilliseconds.ToString("F1") +
                              " cpuMs=" + cpu.ToString("F1") +
                              " reason=" + (snapshot?.Reason.ToString() ?? "none") +
                              " modeField=" + (snapshot?.Mode.ToString() ?? "none") +
                              " leases=" + DeadlineApi.ActiveLeaseCount +
                              " live=" + DeadlineApi.LiveWorkers + " max=" + DeadlineApi.MaxLiveWorkers +
                              " latched=" + DeadlineApi.LatchedPeriodMicros);
        }
        return 0;
    }
    private static int FaultDuringLastStop(string kind)
    {
        var armFails = kind == "arm";
        var waitFails = kind == "wait";
        if (!armFails && !waitFails) { Console.WriteLine("FAIL unknown fault kind " + kind); return 2; }
        var ticker = typeof(MapRunOptions).Assembly.GetType("RuneCLR.Runtime.CallbackEpochTicker", throwOnError: false);
        var gateField = ticker?.GetField("Gate", BindingFlags.NonPublic | BindingFlags.Static);
        var acquire = ticker?.GetMethod("Acquire", BindingFlags.NonPublic | BindingFlags.Static);
        var install = ticker?.GetMethod("InstallTestTimerFault", BindingFlags.NonPublic | BindingFlags.Static);
        if (ticker is null || gateField is null || acquire is null || install is null)
        {
            Console.WriteLine("SKIP internal ticker surface is not available");
            return 3;
        }

        var tick = typeof(AssemblyLoadContext).GetMethod("RuneCLR_TickCallbackDeadlineEpoch",
            BindingFlags.NonPublic | BindingFlags.Static)!.CreateDelegate<Func<long>>();
        var read = typeof(AssemblyLoadContext).GetMethod("RuneCLR_ReadCallbackDeadlineEpoch",
            BindingFlags.NonPublic | BindingFlags.Static)!.CreateDelegate<Func<long>>();
        var gate = gateField.GetValue(null)!;
        Monitor.Enter(gate);
        try
        {
            using var hook = (IDisposable)install.Invoke(null, new object[] { armFails, waitFails })!;
            var lease = acquire.Invoke(null, new object[] { 10_000, tick, read })!;
            var faultProperty = lease.GetType().GetProperty("FaultType", BindingFlags.NonPublic | BindingFlags.Instance);
            var wait = System.Diagnostics.Stopwatch.StartNew();
            while (wait.Elapsed < TimeSpan.FromSeconds(10))
            {
                if (!string.IsNullOrEmpty(faultProperty?.GetValue(lease) as string)) break;
                Thread.Sleep(10);
            }

            var observed = faultProperty?.GetValue(lease) as string;
            var stop = System.Diagnostics.Stopwatch.StartNew();
            ((IDisposable)lease).Dispose();
            stop.Stop();
            var ok = !string.IsNullOrEmpty(observed) && stop.Elapsed < TimeSpan.FromSeconds(5)
                     && DeadlineApi.LiveWorkers == 0 && DeadlineApi.MaxLiveWorkers <= 1
                     && DeadlineApi.ActiveLeaseCount == 0 && DeadlineApi.Faulted
                     && DeadlineApi.LatchedPeriodMicros == 10_000;
            Console.WriteLine((ok ? "PASS" : "FAIL") + " fault-stop-" + kind +
                              " fault=" + (observed ?? "none") + " disposeMs=" + stop.Elapsed.TotalMilliseconds.ToString("F0") +
                              " live=" + DeadlineApi.LiveWorkers + " max=" + DeadlineApi.MaxLiveWorkers +
                              " leases=" + DeadlineApi.ActiveLeaseCount + " latched=" + DeadlineApi.LatchedPeriodMicros);
            return ok ? 0 : 1;
        }
        finally
        {
            Monitor.Exit(gate);
        }
    }

    /// <summary>Separate-process fault case: install the internal timer fault while idle,
    /// then require the existing lease and future acquires to fail.</summary>
    private static int FaultMode(string kind)
    {
        var armFails = kind == "arm";
        var waitFails = kind == "wait";
        if (!armFails && !waitFails) { Console.WriteLine("FAIL unknown fault kind " + kind); return 2; }
        var install = typeof(MapRunOptions).Assembly.GetType("RuneCLR.Runtime.CallbackEpochTicker", throwOnError: false)?
            .GetMethod("InstallTestTimerFault", BindingFlags.NonPublic | BindingFlags.Static);
        if (install is null) { Console.WriteLine("SKIP fault hook is not available"); return 3; }
        if (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge) { Console.WriteLine("SKIP native epoch is not available"); return 3; }
        using var hook = (IDisposable)install.Invoke(null, new object[] { armFails, waitFails })!;
        try
        {
            using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
            var threw = Capture(() => session.Tick()) is InvalidOperationException;
            var acquire = Capture(() => new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000)));
            session.Stop();
            Check(threw, "an existing lease did not surface the fault as InvalidOperationException");
            Check(acquire is InvalidOperationException, "a future acquire did not fail after the fault: " + acquire?.GetType().Name);
            Check(DeadlineApi.Faulted, "the fault was not latched");
            Check(!string.IsNullOrEmpty(DeadlineApi.FaultTypeName), "no fault type was captured");
            using var clock = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Clock"));
            Check(clock.Tick(), "clock mode was affected by the epoch fault");
            clock.Stop();
            Console.WriteLine("PASS fault-" + kind + " latched=" + DeadlineApi.FaultTypeName);
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("FAIL fault-" + kind + " :: " + error.GetType().Name + ": " + error.Message);
            return 1;
        }
    }

    private static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("default Clock starts no thread and reports no deadline evidence", DefaultNoTicker);
        yield return ("explicit Epoch is refused before the missing author file when native support is absent", EpochRefusedBeforeFile);
        yield return ("invalid option combinations are rejected", InvalidCombinations);
        yield return ("clock mode keeps the version-1 contract", ClockOnV1);
        yield return ("first epoch session sees a positive native epoch", FirstEpochPositive);
        yield return ("four concurrent sessions share one ticker", FourConcurrent);
        yield return ("stopping one session does not stop the others", StopOneKeepsOthers);
        yield return ("last stop joins the ticker", LastStopJoins);
        yield return ("failure during ctor/OnStart rolls back the lease", FailureRollback);
        yield return ("a stopped session does not root its ALC", StoppedDoesNotRoot);
        yield return ("duplicate Stop is idempotent", DuplicateStop);
        yield return ("period mismatch is rejected before the author file while a ticker is active", PeriodMismatchWhileActive);
        yield return ("catch/filter cannot resume a terminated callback", CatchCannotResume);
        yield return ("next good session completes after termination and unloads", NextGoodAfterTermination);
        yield return ("no public pause/escape API is exposed", NoPauseApi);
        yield return ("default epoch period is 10000 microseconds", DefaultPeriod);
        yield return ("clock mode never starts or latches the epoch ticker", ClockKeepsTickerIdle);
        yield return ("epoch ticker diagnostics reset leases and keep the latched period", TickerDiagnostics);
        yield return ("last stop racing a new start never overlaps or double-ticks", LastStopRacesStart);
        yield return ("a conflicting period is rejected before files after the last lease is gone", PeriodLatchedAfterLastLease);
        yield return ("a failed start leaves no lease behind", FailedStartLeavesNoLease);
        yield return ("the ticker thread does not inherit the caller ExecutionContext", TickerDoesNotInheritFlow);
        yield return ("injected ticker faults surface to an existing lease", InjectedFaultVisibility);
        yield return ("legacy Query fields stay -1 on the clock path", LegacyQueryUnchanged);
    }

    private static void DefaultNoTicker()
    {
        var before = ThreadCount();
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Off());
        session.Tick();
        session.Stop();
        var after = ThreadCount();
        Check(after <= before + 1, "default run started persistent threads: " + before + " -> " + after);
    }

    private static void EpochRefusedBeforeFile()
    {
        var missing = MissingPackage();
        var options = Options("Epoch");
        var error = Capture(() => new MapRunner().Start(missing, options));
        if (DeadlineApi.NativeEpoch)
        {
            Check(error is not PlatformNotSupportedException,
                "native epoch support is present but the session refused as unsupported");
        }
        else
        {
            Check(error is PlatformNotSupportedException,
                "epoch mode without native support must refuse: " + error?.GetType().Name);
        }

        Check(!File.Exists(missing.AssemblyPath), "refusal opened or created the author path");
    }

    private static void InvalidCombinations()
    {
        var plain = Capture(() => new MapRunner().Start(MissingPackage(),
            new MapRunOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter }));
        Check(plain is not ArgumentException,
            "valid interpreter options were rejected by validation: " + plain?.GetType().Name);
        if (!DeadlineApi.EpochSupported) return;
        var noDeadline = DeadlineApi.WithMode(Off(), "Epoch", 10_000);
        Check(Capture(() => new MapRunner().Start(MissingPackage(), noDeadline)) is ArgumentException,
            "epoch mode without a deadline must be an ArgumentException");
        var badPeriod = Options("Epoch", 0);
        Check(Capture(() => new MapRunner().Start(MissingPackage(), badPeriod)) is ArgumentException,
            "an out-of-range epoch period must be an ArgumentException");
    }

    private static void ClockOnV1()
    {
        if (DeadlineVersion() != 1) throw new SkipException("the runtime does not expose the version-1 clock bridge");
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Clock"));
        Check(session.Tick(), "clock session failed on a healthy tick");
        var result = session.Stop();
        Check(result.Report.PrototypeDeadline is not null, "clock mode did not report deadline evidence");
    }

    private static void FirstEpochPositive()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch"));
        Check(session.Tick(), "epoch session failed on a healthy tick");
        var result = session.Stop();
        var snapshot = result.Report.PrototypeDeadline;
        Check(snapshot is not null, "epoch mode did not report deadline evidence");
    }

    private static void FourConcurrent()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        var sessions = Enumerable.Range(0, 4)
            .Select(_ => new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch")))
            .ToList();
        try
        {
            foreach (var session in sessions) Check(session.Tick(), "a concurrent session failed a healthy tick");
        }
        finally
        {
            foreach (var session in sessions) session.Stop();
        }
    }

    private static void StopOneKeepsOthers()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        var first = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch"));
        var second = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch"));
        first.Stop();
        Check(second.IsRunning, "stopping one session stopped another");
        Check(second.Tick(), "the surviving session failed a tick");
        second.Stop();
    }

    private static void LastStopJoins()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        var before = ThreadCount();
        var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch"));
        session.Tick();
        session.Stop();
        Thread.Sleep(200);
        Check(ThreadCount() <= before + 1, "the ticker thread survived the last stop: " + before + " -> " + ThreadCount());
    }

    private static void FailureRollback()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        foreach (var entry in new[] { "EpochDeadline.Author.CtorFails", "EpochDeadline.Author.StartFails" })
        {
            using var session = new MapRunner().Start(Package(entry), Options("Epoch"));
            Check(!session.IsRunning, entry + " should not stay running");
            session.Stop();
        }

        var missing = MissingPackage();
        var error = Capture(() => new MapRunner().Start(missing, Options("Epoch")));
        Check(error is not null, "a missing author file must surface an error");
    }

    private static void StoppedDoesNotRoot()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        var weak = RunAndCaptureContext("EpochDeadline.Author.ArithmeticSmall");
        for (var attempt = 0; attempt < 3 && weak.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
        }

        Check(!weak.IsAlive, "a stopped session still roots its load context");
    }

    private static void DuplicateStop()
    {
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Off());
        var first = session.Stop();
        var second = session.Stop();
        Check(ReferenceEquals(first, second), "duplicate Stop returned a different result");
    }

    private static void PeriodMismatchWhileActive()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch mode is not available on this runtime");
        using var active = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
        var error = Capture(() => new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 5_000)));
        Check(error is not null, "a conflicting period was accepted while the ticker was active");
        active.Stop();
        using var restart = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
        Check(restart.Tick(), "restart with the same period failed");
        restart.Stop();
    }

    private static void CatchCannotResume()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge)
            throw new SkipException("native epoch mode is not available on this runtime");
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.TickOnlyCatchLong"),
            Options("Epoch", 10_000, deadlineMs: 50, poll: 100));
        var ok = session.Tick();
        Check(!ok, "the catch/filter workload was not terminated");
        var result = session.Stop();
        Check(result.Report.Outcome == MapRunOutcome.Failed, "the terminated session did not report failure");
        Check(result.Report.PrototypeDeadline is { } snapshot && snapshot.Reason == 2,
            "termination was not the deadline reason 2");
    }

    private static void NextGoodAfterTermination()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge)
            throw new SkipException("native epoch mode is not available on this runtime");
        for (var index = 0; index < 2; index++)
        {
            using var terminated = new MapRunner().Start(Package("EpochDeadline.Author.TickOnlyLong"),
                Options("Epoch", 10_000, deadlineMs: 50, poll: 100));
            Check(!terminated.Tick(), "the long tick was not terminated");
            terminated.Stop();
        }

        using var good = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
        Check(good.Tick(), "the good session after terminations failed");
        var result = good.Stop();
        Check(result.Report.Outcome == MapRunOutcome.Completed, "the good session did not complete");
    }

    private static void NoPauseApi()
    {
        var exposed = typeof(MapRunOptions).Assembly.GetExportedTypes()
            .SelectMany(type => type.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance))
            .Any(method => method.Name.Contains("Pause", StringComparison.OrdinalIgnoreCase));
        Check(!exposed, "a public pause/escape API is exposed");
    }

    private static void DefaultPeriod()
    {
        if (!DeadlineApi.EpochSupported || !DeadlineApi.PrivateBridge) throw new SkipException("epoch options are not available on this runtime");
        Check(DeadlineApi.DefaultPeriodMicros == 10_000,
            "default epoch period is " + DeadlineApi.DefaultPeriodMicros);
    }

    private static void ClockKeepsTickerIdle()
    {
        if (!DeadlineApi.TickerAvailable || !DeadlineApi.PrivateBridge)
            throw new SkipException("the production ticker diagnostics or private bridge are not available");
        var periodBefore = DeadlineApi.LatchedPeriodMicros;
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Clock"));
        session.Tick();
        Check(DeadlineApi.ActiveLeases == 0, "clock mode acquired epoch ticker leases");
        Check(DeadlineApi.LatchedPeriodMicros == periodBefore, "clock mode changed the latched epoch period");
        session.Stop();
    }

    private static void TickerDiagnostics()
    {
        if (!DeadlineApi.TickerAvailable || !DeadlineApi.NativeEpoch)
            throw new SkipException("the production ticker or native epoch is not available");
        DeadlineApi.ResetDiagnostics();
        for (var index = 0; index < 2; index++)
        {
            using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
            Check(DeadlineApi.ActiveLeases == 1, "active leases should be 1 while a session runs");
            Check(DeadlineApi.LatchedPeriodMicros == 10_000,
                "latched period while active is " + DeadlineApi.LatchedPeriodMicros);
            Check(session.Tick(), "epoch session failed a healthy tick");
            session.Stop();
        }

        Check(DeadlineApi.ActiveLeases == 0, "leases were not released after the last stop: " + DeadlineApi.ActiveLeases);
        Check(DeadlineApi.TotalTicks > 0, "the ticker published no ticks");
        Check(DeadlineApi.LatchedPeriodMicros == 10_000,
            "the latched period should persist after the last stop, got " + DeadlineApi.LatchedPeriodMicros);
        Check(!DeadlineApi.Faulted, "ticker faulted: " + DeadlineApi.FaultType);
        var error = Capture(() => new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 5_000)));
        Check(error is not null, "a conflicting period was accepted after the last stop");
    }

    private static void LastStopRacesStart()
    {
        if (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge) throw new SkipException("native epoch mode is not available");
        var faults = 0;
        var before = DeadlineApi.TotalTicks;
        var clock = System.Diagnostics.Stopwatch.StartNew();
        for (var round = 0; round < 12; round++)
        {
            var first = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
            using var barrier = new Barrier(2);
            Exception? startError = null;
            var starter = new Thread(() =>
            {
                barrier.SignalAndWait();
                try
                {
                    using var second = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000));
                    second.Tick();
                    second.Stop();
                }
                catch (Exception error) { startError = error; }
            });
            starter.Start();
            barrier.SignalAndWait();
            first.Stop();
            starter.Join(TimeSpan.FromSeconds(10));
            if (startError is not null) faults++;
        }

        clock.Stop();
        var ticks = DeadlineApi.TotalTicks - before;
        var seconds = Math.Max(0.001, clock.Elapsed.TotalSeconds);
        var rate = ticks / seconds;
        // One ticker at a 10 ms period yields about 100 ticks/s; two tickers would double it.
        Check(rate <= 200.0, "ticker rate " + rate.ToString("F1") + "/s suggests two tickers");
        Check(faults == 0, "a racing start failed: " + faults + " rounds");
        Check(DeadlineApi.ActiveLeaseCount == 0, "leases leaked after the race: " + DeadlineApi.ActiveLeaseCount);
        Check(!DeadlineApi.Faulted, "the ticker faulted during the race: " + DeadlineApi.FaultTypeName);
    }

    private static void PeriodLatchedAfterLastLease()
    {
        if (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge) throw new SkipException("native epoch mode is not available");
        using (var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000)))
        {
            session.Tick();
            session.Stop();
        }

        Check(DeadlineApi.ActiveLeaseCount == 0, "the last lease was not released");
        var missing = MissingPackage();
        var error = Capture(() => new MapRunner().Start(missing, Options("Epoch", 5_000)));
        Check(error is not null, "a conflicting period was accepted after the last lease");
        Check(!File.Exists(missing.AssemblyPath), "the conflict was rejected only after opening the author file");
    }

    private static void FailedStartLeavesNoLease()
    {
        if (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge) throw new SkipException("native epoch mode is not available");
        var before = DeadlineApi.ActiveLeaseCount;
        foreach (var entry in new[] { "EpochDeadline.Author.CtorFails", "EpochDeadline.Author.StartFails" })
        {
            using var session = new MapRunner().Start(Package(entry), Options("Epoch", 10_000));
            Check(!session.IsRunning, entry + " should not stay running");
            session.Stop();
        }

        Check(DeadlineApi.ActiveLeaseCount == before, "a failed start leaked a lease");
    }

    private static void TickerDoesNotInheritFlow()
    {
        if (!DeadlineApi.NativeEpoch || !DeadlineApi.PrivateBridge) throw new SkipException("native epoch mode is not available");
        var weak = LeaseWithFlowSentinel();
        for (var attempt = 0; attempt < 5 && weak.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
        }

        Check(!weak.IsAlive, "the ticker thread inherited and rooted the caller ExecutionContext");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference LeaseWithFlowSentinel()
    {
        var sentinel = new object();
        var flow = new AsyncLocal<object?>();
        flow.Value = sentinel;
        var weak = new WeakReference(sentinel);
        using (var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Epoch", 10_000)))
        {
            session.Tick();
        }

        flow.Value = null;
        return weak;
    }

    private static void LegacyQueryUnchanged()
    {
        if (DeadlineVersion() != 1) throw new SkipException("the runtime does not expose the version-1 clock bridge");
        using var session = new MapRunner().Start(Package("EpochDeadline.Author.ArithmeticSmall"), Options("Clock"));
        var contextField = typeof(MapSession).GetField("_loadContext", BindingFlags.NonPublic | BindingFlags.Instance);
        var context = contextField?.GetValue(session) as AssemblyLoadContext;
        Check(context is not null, "could not reach the session load context for the legacy query");
        var query = typeof(AssemblyLoadContext).GetMethod("RuneCLR_QueryCallbackDeadline",
            BindingFlags.NonPublic | BindingFlags.Instance, binder: null, types: new[] { typeof(int) }, modifiers: null);
        Check(query is not null, "the legacy Query entry is missing");
        var delegateQuery = query!.CreateDelegate<Func<AssemblyLoadContext, int, long>>();
        Check(delegateQuery(context!, 7) == -1, "legacy field 7 must stay -1");
        Check(delegateQuery(context!, 99) == -1, "an unknown legacy field must stay -1");
        session.Tick();
        session.Stop();
    }

    private static void InjectedFaultVisibility()
    {
        // Real regression: each fault case runs in its own child process (the hook is process-wide
        // and a latched fault is permanent), under the same private host/runtime as this test.
        if (!DeadlineApi.FaultHookAvailable) throw new SkipException("no internal timer fault hook is available");
        foreach (var kind in new[] { "arm", "wait" })
        {
            var r1 = RunFaultChild("--fault", kind);
            Check(r1.Exit == 0, "fault " + kind + " child exit=" + r1.Exit + " :: " + r1.Output);
            var r2 = RunFaultChild("--fault-stop", kind);
            Check(r2.Exit == 0, "fault-stop " + kind + " child exit=" + r2.Exit + " :: " + r2.Output);
        }
    }

    private static (int Exit, string Output) RunFaultChild(string mode, string kind)
    {
        var host = Environment.ProcessPath ?? "dotnet";
        var assembly = typeof(Program).Assembly.Location;
        var info = new System.Diagnostics.ProcessStartInfo(host)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            WorkingDirectory = AppContext.BaseDirectory,
            // Resolve the same private runtime the parent is running on (the muxer lives beside
            // shared/Microsoft.NETCore.App/<version>); an inherited DOTNET_ROOT may point elsewhere.
            Environment =
            {
                ["DOTNET_ROOT"] = string.IsNullOrEmpty(Environment.GetEnvironmentVariable("DOTNET_ROOT"))
                    ? System.IO.Path.GetFullPath(System.IO.Path.Combine(AppContext.BaseDirectory, "..", "..", ".."))
                    : Environment.GetEnvironmentVariable("DOTNET_ROOT")!,
                ["DOTNET_MULTILEVEL_LOOKUP"] = "0",
            },
        };
        info.ArgumentList.Add("exec");
        info.ArgumentList.Add("--fx-version");
        info.ArgumentList.Add("12.0.0");
        if (!string.Equals(System.IO.Path.GetFileNameWithoutExtension(host),
                System.IO.Path.GetFileNameWithoutExtension(assembly), StringComparison.OrdinalIgnoreCase))
            info.ArgumentList.Add(assembly);
        info.ArgumentList.Add(mode);
        info.ArgumentList.Add(kind);
        using var process = System.Diagnostics.Process.Start(info)!;
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit(60000))
        {
            try { process.Kill(true); } catch { }
            throw new InvalidOperationException("fault child watchdog");
        }
        var output = (stdout.GetAwaiter().GetResult() + " " + stderr.GetAwaiter().GetResult()).Trim();
        return (process.ExitCode, output.Length > 400 ? output[..400] : output);
    }


    private static WeakReference RunAndCaptureContext(string entry)
    {
        var session = new MapRunner().Start(Package(entry), Options("Epoch"));
        session.Tick();
        var result = session.Stop();
        var weak = new WeakReference(null);
        var field = typeof(UnloadTicket).GetField("_context", BindingFlags.NonPublic | BindingFlags.Instance);
        if (field?.GetValue(result.Unload) is WeakReference context) weak = context;
        session.Dispose();
        return weak;
    }

    private static MapPackage Package(string entry) => new("epoch-tests", AuthorPath, entry);

    private static MapPackage MissingPackage() => new(
        "epoch-missing", Path.Combine(Path.GetTempPath(), "runeclr-epoch-" + Guid.NewGuid().ToString("N") + ".dll"), "Unused");

    private static int ThreadCount()
    {
        GC.Collect();
        return System.Diagnostics.Process.GetCurrentProcess().Threads.Count;
    }

    private static Exception? Capture(Action action)
    {
        try
        {
            action();
            return null;
        }
        catch (Exception error)
        {
            return error;
        }
    }

    private static long DeadlineVersion()
    {
        try
        {
            var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetCallbackDeadlineVersion",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method is null ? 0 : method.CreateDelegate<Func<long>>()();
        }
        catch { return 0; }
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private sealed class SkipException : Exception
    {
        public SkipException(string message) : base(message) { }
    }
}

/// <summary>Binds the optional epoch options reflectively so the harness compiles before
/// the production change lands and fails closed when it is absent.</summary>
internal static class DeadlineApi
{
    private static readonly PropertyInfo? ModeProperty = typeof(MapRunOptions).GetProperty("PrototypeDeadlineMode");
    private static readonly PropertyInfo? PeriodProperty = typeof(MapRunOptions).GetProperty("PrototypeDeadlineEpochPeriodMicros");
    private static readonly Type? ModeType = typeof(MapRunOptions).Assembly.GetType("RuneCLR.Runtime.MapDeadlineMode");

    public static bool EpochSupported => ModeProperty is not null && PeriodProperty is not null && ModeType is not null;

    private static readonly Type? TickerType = typeof(MapRunOptions).Assembly.GetType("RuneCLR.Runtime.CallbackEpochTicker");

    public static bool TickerAvailable => typeof(CallbackEpochDiagnostics) is not null;

    public static bool PrivateBridge
    {
        get
        {
            try
            {
                var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicyVersion",
                    BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
                return method is not null && method.CreateDelegate<Func<int>>()() == 1;
            }
            catch { return false; }
        }
    }

    public static bool FaultHookAvailable =>
        typeof(MapRunOptions).Assembly.GetType("RuneCLR.Runtime.CallbackEpochTicker", throwOnError: false)?
            .GetMethod("InstallTestTimerFault", BindingFlags.NonPublic | BindingFlags.Static) is not null;

    public static int DefaultPeriodMicros =>
        PeriodProperty is null ? -1 : (int)PeriodProperty.GetValue(new MapRunOptions())!;

    public static int ActiveLeases => CallbackEpochDiagnostics.ActiveLeaseCount;
    public static int ActiveLeaseCount => CallbackEpochDiagnostics.ActiveLeaseCount;

    /// <summary>Optional worker-count diagnostic; -1 when production does not expose one.</summary>
    public static int LiveWorkers
    {
        get
        {
            var property = TickerType?.GetProperty("LiveWorkerCount", BindingFlags.NonPublic | BindingFlags.Static);
            return property is null ? -1 : Convert.ToInt32(property.GetValue(null) ?? -1);
        }
    }

    public static int MaxLiveWorkers
    {
        get
        {
            var property = TickerType?.GetProperty("MaxLiveWorkerCount", BindingFlags.NonPublic | BindingFlags.Static);
            return property is null ? -1 : Convert.ToInt32(property.GetValue(null) ?? -1);
        }
    }
    public static int LatchedPeriodMicros => CallbackEpochDiagnostics.LatchedPeriodMicros;
    public static long TotalTicks => CallbackEpochDiagnostics.TotalTicks;
    public static bool Faulted => CallbackEpochDiagnostics.Faulted;
    public static string? FaultType => CallbackEpochDiagnostics.FaultTypeName;
    public static string? FaultTypeName => CallbackEpochDiagnostics.FaultTypeName;

    public static void ResetDiagnostics()
    {
        // Diagnostics are read-only; this exists so a test can state intent explicitly.
    }

    public static bool NativeEpoch
    {
        get
        {
            try
            {
                var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetCallbackDeadlineCapabilities",
                    BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
                return method is not null && (method.CreateDelegate<Func<int>>()() & 2) != 0;
            }
            catch { return false; }
        }
    }

    public static MapRunOptions WithMode(MapRunOptions options, string mode, int periodMicros)
    {
        if (ModeType is null || ModeProperty is null) return options;
        var value = Enum.Parse(ModeType, mode, ignoreCase: true);
        if (PeriodProperty?.SetMethod is { } setter) setter.Invoke(options, new object[] { periodMicros });
        ModeProperty.SetValue(options, value);
        return options;
    }
}
