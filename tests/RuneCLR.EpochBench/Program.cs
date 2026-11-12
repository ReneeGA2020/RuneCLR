using System.Diagnostics;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using RuneCLR.Runtime;

namespace RuneCLR.EpochBench;

internal static class Program
{
    private static string AuthorPath => Path.Combine(AppContext.BaseDirectory, "bench", "EpochBench.Author.dll");

    private static int Main(string[] args)
    {
        try
        {
            var options = Options.Parse(args);
            return options.Command switch
            {
                "probe" => Probe(),
                "selfcheck" => SelfCheck(),
                "mechanical" => Mechanical(options),
                "timing" => Timing(options),
                "cutoff" => Cutoff(options),
                "ticker" => TickerProbe(options),
                "concurrent" => Concurrent(options),
                "nextgood" => NextGood(options),
                "proof" => Proof(options),
                "pauseprobe" => PauseProbe(options),
                _ => Fail("unknown command: " + options.Command)
            };
        }
        catch (Exception error)
        {
            Console.WriteLine(Json(new { ok = false, error = error.GetType().FullName, message = error.Message,
                                          stack = error.StackTrace }));
            return 1;
        }
    }

    private static int Probe()
    {
        var version = DeadlineVersion();
        var epoch = EpochCapability();
        Console.WriteLine(Json(new
        {
            ok = true,
            deadlineVersion = version,
            epochCapability = epoch,
            interpreterBridge = InterpreterVersion(),
            runtime = Environment.Version.ToString(),
            framework = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription
        }));
        return 0;
    }

    private static int SelfCheck()
    {
        var results = new List<object>();
        void Check(string name, Func<Exception?> action, Type expected)
        {
            Exception? error = null;
            try { error = action(); }
            catch (Exception caught) { error = caught; }
            var actual = error?.GetType();
            results.Add(new { name, passed = actual == expected, expected = expected.FullName, actual = actual?.FullName });
        }

        var missing = MissingPackage();
        Check("epoch-requires-deadline", () =>
        {
            new MapRunner().Start(missing, new MapRunOptions { PrototypeDeadlineMode = MapDeadlineMode.Epoch });
            return null;
        }, typeof(ArgumentException));

        var epochMissing = MissingPackage();
        Check("epoch-refused-before-author-file", () =>
        {
            new MapRunner().Start(epochMissing, Deadline("epoch", 5000, 100));
            return null;
        }, typeof(PlatformNotSupportedException));
        results.Add(new { name = "epoch-author-file-absent", passed = !File.Exists(epochMissing.AssemblyPath) });

        Check("clock-invalid-interval", () =>
        {
            new MapRunner().Start(MissingPackage(), Deadline("clock", 100, 7));
            return null;
        }, typeof(ArgumentOutOfRangeException));

        Check("deadline-requires-interpreter", () =>
        {
            new MapRunner().Start(MissingPackage(), new MapRunOptions
            {
                PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(100)
            });
            return null;
        }, typeof(ArgumentException));

        var version = DeadlineVersion();
        results.Add(new { name = "deadline-version-not-bumped", passed = version <= 1, version });
        results.Add(new { name = "clock-capability-reported", passed = true, clock = ClockCapability() });

        var passed = results.All(item => item.GetType().GetProperty("passed")!.GetValue(item) is true);
        Console.WriteLine(Json(new { ok = passed, checks = results }));
        return passed ? 0 : 1;
    }

    private static int Mechanical(Options options)
    {
        var samples = new List<object>();
        for (var index = 0; index < options.Samples; index++)
        {
            var sample = RunSession(options, "off", options.EntryPath, options.EntryType);
            samples.Add(sample);
        }

        var totals = samples.Select(item => (double)item.GetType().GetProperty("totalMs")!.GetValue(item)!).ToList();
        Console.WriteLine(Json(new
        {
            ok = true,
            lane = "mechanical",
            samples,
            medianMs = Stats.Median(totals),
            p10Ms = Stats.Quantile(totals, 0.1),
            p90Ms = Stats.Quantile(totals, 0.9)
        }));
        return 0;
    }

    private static int Timing(Options options)
    {
        if (options.Mode == "epoch" && options.TickerMicros <= 0)
            throw new ArgumentException("Epoch mode requires the host ticker.");
        using var ticker = StartTicker(options);
        var samples = new List<object>();
        for (var index = 0; index < options.Warmup + options.Samples; index++)
        {
            var sample = RunSession(options, options.Mode, options.EntryPath, options.EntryType);
            if (index >= options.Warmup) samples.Add(sample);
        }

        var totals = samples.Select(item => (double)item.GetType().GetProperty("totalMs")!.GetValue(item)!).ToList();
        Console.WriteLine(Json(new
        {
            ok = true,
            lane = "timing",
            mode = options.Mode,
            entry = options.EntryType,
            interval = options.PollInterval,
            deadlineMs = options.DeadlineMs,
            ticks = options.Ticks,
            epochPeriodUs = options.EpochPeriodMicros,
            tickerUs = options.TickerMicros,
            tickerPeriodUs = ticker?.PeriodMicros,
            ticker = TickerReport(ticker, options.Wait),
            samples,
            medianMs = Stats.Median(totals),
            p10Ms = Stats.Quantile(totals, 0.1),
            p90Ms = Stats.Quantile(totals, 0.9),
            minMs = totals.Min(),
            maxMs = totals.Max()
        }));
        return 0;
    }

    private static int Cutoff(Options options)
    {
        using var ticker = StartTicker(options);
        Thread? pauser = null;
        if (ticker is not null && options.PauseAtMs > 0)
        {
            pauser = new Thread(() =>
            {
                Thread.Sleep(options.PauseAtMs);
                ticker.Pause();
                Thread.Sleep(options.PauseForMs > 0 ? options.PauseForMs : 60_000);
                ticker.Resume();
            }) { IsBackground = true };
            pauser.Start();
        }

        var sample = RunSession(options, options.Mode, options.EntryPath, options.EntryType);
        pauser?.Join(TimeSpan.FromSeconds(1));
        Console.WriteLine(Json(new
        {
            ok = true,
            lane = "cutoff",
            mode = options.Mode,
            entry = options.EntryType,
            interval = options.PollInterval,
            deadlineMs = options.DeadlineMs,
            ticker = TickerReport(ticker, options.Wait),
            pauseAtMs = options.PauseAtMs,
            pauseForMs = options.PauseForMs,
            sample
        }));
        return 0;
    }

    /// <summary>B2: pause the ticker while the callback is provably running, prove the
    /// native epoch is stable and nothing terminated, then resume and require a
    /// deadline trip (reason 2) that returns to the host.</summary>
    private static int PauseProbe(Options options)
    {
        if (options.Mode != "epoch") throw new ArgumentException("pauseprobe requires epoch mode.");
        var read = EpochRead();
        if (read is null) throw new PlatformNotSupportedException("The runtime has no epoch reader.");
        var ticker = StartTicker(options) ?? throw new ArgumentException("pauseprobe requires the host ticker.");
        using (ticker)
        {
            var package = new MapPackage("epoch-bench", options.EntryPath, options.EntryType);
            var runOptions = OptionsFor("epoch", options);
            var callbackActive = 0;
            long epochBeforePause = 0, epochAtPauseEnd = 0, epochAfterResume = 0;
            double pausedAtMs = 0;
            var stable = false;
            var terminatedDuringPause = false;
            var incremented = false;
            var pauseStarted = false;
            var clock = Stopwatch.StartNew();
            using var session = new MapRunner().Start(package, runOptions);
            var pauser = new Thread(() =>
            {
                var wait = Stopwatch.StartNew();
                while (Volatile.Read(ref callbackActive) == 0 && wait.ElapsedMilliseconds < 5000) Thread.Sleep(1);
                if (Volatile.Read(ref callbackActive) == 0) return;
                epochBeforePause = read();
                pausedAtMs = clock.Elapsed.TotalMilliseconds;
                pauseStarted = true;
                ticker.Pause();
                Thread.Sleep(options.PauseForMs > 0 ? options.PauseForMs : 400);
                epochAtPauseEnd = read();
                stable = epochAtPauseEnd == epochBeforePause;
                terminatedDuringPause = Volatile.Read(ref callbackActive) == 0;
                ticker.Resume();
                var resumeWait = Stopwatch.StartNew();
                while (resumeWait.ElapsedMilliseconds < 2000)
                {
                    var current = read();
                    if (current > epochAtPauseEnd) { epochAfterResume = current; incremented = true; return; }
                    Thread.Sleep(1);
                }

                epochAfterResume = read();
            }) { IsBackground = true };
            pauser.Start();
            Volatile.Write(ref callbackActive, 1);
            var returned = session.Tick();
            var tripMs = clock.Elapsed.TotalMilliseconds;
            Volatile.Write(ref callbackActive, 0);
            pauser.Join(TimeSpan.FromSeconds(10));
            var stopped = !session.IsRunning;
            var reason = session.Result?.Report.PrototypeDeadline?.Reason ?? -1;

            var deadline = options.DeadlineMs;
            var ok = pauseStarted && pausedAtMs < deadline * 0.5 && stable && !terminatedDuringPause &&
                     incremented && !returned && stopped && reason == 2 &&
                     tripMs < deadline * 3 + options.PauseForMs + 5000;
            Console.WriteLine(Json(new
            {
                ok,
                lane = "pauseprobe",
                deadlineMs = deadline,
                pauseAtMs = pausedAtMs,
                pauseForMs = options.PauseForMs,
                pauseStarted,
                callbackActiveAtPause = pauseStarted,
                callbackActiveBeforePause = pausedAtMs > 0,
                epochBeforePause,
                epochAtPauseEnd,
                epochAfterResume,
                epochStableDuringPause = stable,
                terminatedDuringPause,
                epochIncrementedAfterResume = incremented,
                tickReturnedAfterResume = returned,
                sessionStopped = stopped,
                reason,
                tripMs,
                processCpuMs = 0.0
            }));
            return ok ? 0 : 1;
        }
    }

    /// <summary>Same work in every mode: all three rows must complete with the full
    /// tick count, a non-empty identical checksum and positive interpreter admissions.</summary>
    private static int Proof(Options options)
    {
        var rows = new List<object>();
        var checksums = new List<string?>();
        var checks = new List<(string Mode, bool Completed, int Ticks, long Admitted, string? Checksum)>();
        using var ticker = StartTicker(options);
        foreach (var mode in new[] { "off", "clock", "epoch" })
        {
            try
            {
                var sample = RunSession(options, mode, options.EntryPath, options.EntryType);
                var type = sample.GetType();
                var checksum = (string?)type.GetProperty("checksum")!.GetValue(sample);
                var outcome = (string?)type.GetProperty("outcome")!.GetValue(sample);
                var ticks = (int)type.GetProperty("completedTicks")!.GetValue(sample)!;
                var snapshot = type.GetProperty("snapshot")!.GetValue(sample);
                var admitted = snapshot is null ? 0L : (long)snapshot.GetType().GetProperty("AdmittedOperations")!.GetValue(snapshot)!;
                checksums.Add(checksum);
                checks.Add((mode, outcome == "Completed", ticks, admitted, checksum));
                rows.Add(sample);
            }
            catch (Exception error)
            {
                checksums.Add(null);
                checks.Add((mode, false, 0, 0, null));
                rows.Add(new { mode, error = error.GetType().FullName, message = error.Message });
            }
        }

        var allCompleted = checks.All(c => c.Completed && c.Ticks == options.Ticks &&
                                           !string.IsNullOrEmpty(c.Checksum) && c.Checksum == checksums[0]);
        var admittedPositive = checks.Where(c => c.Mode != "off").All(c => c.Admitted > 0);
        var equal = allCompleted && admittedPositive;
        Console.WriteLine(Json(new
        {
            ok = equal,
            lane = "proof",
            entry = options.EntryType,
            ticks = options.Ticks,
            checksums,
            checksumsEqual = equal,
            checks = checks.Select(c => new { mode = c.Mode, completed = c.Completed, ticks = c.Ticks,
                                              admitted = c.Admitted, checksum = c.Checksum }),
            rows
        }));
        return equal ? 0 : 1;
    }

    private static int Concurrent(Options options)
    {
        if (options.Mode == "epoch" && options.TickerMicros <= 0)
            throw new ArgumentException("Epoch mode requires the host ticker.");
        using var ticker = StartTicker(options);
        using var process = Process.GetCurrentProcess();
        process.Refresh();
        var cpuBefore = process.TotalProcessorTime;
        var results = new object?[options.Sessions];
        var threads = new Thread[options.Sessions];
        var barrier = new Barrier(options.Sessions);
        var wall = Stopwatch.StartNew();
        for (var index = 0; index < options.Sessions; index++)
        {
            var slot = index;
            threads[slot] = new Thread(() =>
            {
                barrier.SignalAndWait();
                try { results[slot] = RunSession(options, options.Mode, options.EntryPath, options.EntryType); }
                catch (Exception error) { results[slot] = new { error = error.GetType().FullName, message = error.Message }; }
            }) { IsBackground = true };
            threads[slot].Start();
        }

        foreach (var thread in threads) thread.Join();
        wall.Stop();
        process.Refresh();
        var cpu = process.TotalProcessorTime - cpuBefore;
        Console.WriteLine(Json(new
        {
            ok = true,
            lane = "concurrent",
            mode = options.Mode,
            sessions = options.Sessions,
            startBarrier = true,
            processorCount = Environment.ProcessorCount,
            affinity = OperatingSystem.IsWindows() ? process.ProcessorAffinity.ToInt64() : -1L,
            wallMs = wall.Elapsed.TotalMilliseconds,
            processCpuMs = cpu.TotalMilliseconds,
            ticker = TickerReport(ticker, options.Wait),
            results
        }));
        return 0;
    }

    /// <summary>Two terminated sessions, then a good session; unload tickets observed after GC.</summary>
    private static int NextGood(Options options)
    {
        var outcomes = new List<object>();
        var terminated = new List<UnloadTicket>();
        for (var index = 0; index < 2; index++)
        {
            var sample = RunSession(options, options.Mode, options.EntryPath, options.EntryType, collectTicket: terminated);
            outcomes.Add(sample);
        }

        var good = RunSession(options, "off", options.EntryPath, options.EntryType);
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        var collected = terminated.Select(ticket => ticket.IsCollected).ToList();
        var goodOutcome = (string?)good.GetType().GetProperty("outcome")!.GetValue(good);
        Console.WriteLine(Json(new
        {
            ok = collected.Count > 0 && goodOutcome == "Completed",
            lane = "nextgood",
            terminations = outcomes.Count,
            goodCompleted = goodOutcome == "Completed",
            unloadTickets = terminated.Count,
            unloadCollected = collected,
            good
        }));
        return collected.Count > 0 && goodOutcome == "Completed" ? 0 : 1;
    }

    private static int TickerProbe(Options options)
    {
        using var process = Process.GetCurrentProcess();
        process.Refresh();
        var cpuBefore = process.TotalProcessorTime;
        var ticker = StartTicker(options);
        Thread.Sleep(options.Ticks);
        ticker?.Dispose();
        process.Refresh();
        var cpuAfter = process.TotalProcessorTime;
        Console.WriteLine(Json(new
        {
            ok = true,
            lane = "ticker",
            ticker = TickerReport(ticker, options.Wait),
            tickerProcessCpuMs = (cpuAfter - cpuBefore).TotalMilliseconds,
            wallMs = options.Ticks
        }));
        return 0;
    }

    private static object RunSession(Options options, string mode, string entryPath, string entryType,
        List<UnloadTicket>? collectTicket = null)
    {
        var package = new MapPackage("epoch-bench", entryPath, entryType);
        var runOptions = OptionsFor(mode, options);
        var timings = new List<double>(options.Ticks);
        using var process = Process.GetCurrentProcess();
        process.Refresh();
        var cpuBefore = process.TotalProcessorTime;
        var wall = Stopwatch.StartNew();
        var terminatedAtTick = -1;
        var total = Stopwatch.StartNew();
        using var session = new MapRunner().Start(package, runOptions);
        var startMs = total.Elapsed.TotalMilliseconds;
        var checksums = new List<string>();
        var completed = 0;
        var stoppedDuringStart = !session.IsRunning;
        for (var index = 0; index < options.Ticks && !stoppedDuringStart; index++)
        {
            var tick = Stopwatch.StartNew();
            var ok = session.Tick();
            tick.Stop();
            timings.Add(tick.Elapsed.TotalMilliseconds);
            if (!ok) { terminatedAtTick = index; break; }
            completed++;
        }

        var running = session.IsRunning;
        var stop = Stopwatch.StartNew();
        var result = session.Stop();
        collectTicket?.Add(result.Unload);
        stop.Stop();
        total.Stop();
        wall.Stop();
        process.Refresh();
        var cpu = process.TotalProcessorTime - cpuBefore;
        var report = result.Report;
        checksums.AddRange(report.Logs.Where(line => line.StartsWith("checksum=", StringComparison.Ordinal)));
        return new
        {
            mode,
            startMs,
            tickMs = timings,
            stopMs = stop.Elapsed.TotalMilliseconds,
            totalMs = total.Elapsed.TotalMilliseconds,
            wallMs = wall.Elapsed.TotalMilliseconds,
            processCpuMs = cpu.TotalMilliseconds,
            terminatedAtTick,
            tripPhase = stoppedDuringStart ? "onStart" : (terminatedAtTick >= 0 ? "tick" : "none"),
            tripMs = stoppedDuringStart ? startMs : (terminatedAtTick >= 0 ? timings[terminatedAtTick] : (double?)null),
            completedTicks = completed,
            logCount = report.Logs.Count,
            wasRunning = running,
            outcome = report.Outcome.ToString(),
            error = report.Error,
            checksum = checksums.Count > 0 ? checksums[^1] : null,
            snapshot = Snapshot(report.PrototypeDeadline)
        };
    }

    private static object? Snapshot(CallbackDeadlineSnapshot? snapshot) => snapshot is null ? null : new
    {
        snapshot.ClockFrequency,
        snapshot.ClockChecks,
        snapshot.AdmittedOperations,
        snapshot.Active,
        snapshot.PollInterval,
        snapshot.LastToken,
        snapshot.Reason,
        snapshot.Mode,
        snapshot.EpochBudgetTicks,
        snapshot.CurrentGlobalEpoch
    };

    private static MapRunOptions OptionsFor(string mode, Options options)
    {
        var run = new MapRunOptions { TickCount = 0, MaxLogMessages = 512 };
        if (mode == "off") return run with { ExecutionPolicy = options.Policy };
        return run with
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(options.DeadlineMs),
            PrototypeDeadlinePollInterval = options.PollInterval,
            PrototypeDeadlineMode = mode == "epoch" ? MapDeadlineMode.Epoch : MapDeadlineMode.Clock,
            PrototypeDeadlineEpochPeriodMicros = options.EpochPeriodMicros
        };
    }

    private static EpochTicker? StartTicker(Options options)
    {
        if (options.TickerMicros <= 0) return null;
        var tick = EpochTick();
        var read = EpochRead();
        var ticker = new EpochTicker(options.TickerMicros, _ => tick?.Invoke(), options.Wait);
        ticker.Start();
        // Bootstrap on the native counter (not the ticker's own pre-publish counter):
        // the first publication must be visible before any Begin, or Begin refuses 0.
        var deadline = Stopwatch.GetTimestamp() + Stopwatch.Frequency * 5;
        while (Stopwatch.GetTimestamp() < deadline)
        {
            if (read is not null ? read() > 0 : ticker.Ticks > 0) break;
            Thread.Sleep(1);
        }

        return ticker;
    }

    private static object? TickerReport(EpochTicker? ticker, TickerWait wait)
    {
        if (ticker is null) return null;
        var intervals = ticker.Intervals;
        var ordered = intervals.Order().ToArray();
        var declaredUs = ticker.PeriodMicros;
        var p50 = TicksToMicros(ordered.Length == 0 ? 0 : ordered[ordered.Length / 2]);
        var mean = TicksToMicros((long)Math.Round(ticker.MeanIntervalTicks));
        var histogram = ordered
            .GroupBy(value => (long)Math.Round(TicksToMicros(value)))
            .OrderBy(group => group.Key)
            .Select(group => new { us = group.Key, count = group.Count() })
            .ToArray();
        return new
        {
            waitMode = wait.ToString(),
            declaredUs,
            highResolutionUnsupported = wait == TickerWait.HighResolution && ticker.TimerStatus != "high-resolution",
            ticks = ticker.Ticks,
            lateTicks = ticker.LateTicks,
            violations = ticker.Violations,
            publishFailures = ticker.PublishFailures,
            publishOverruns = ticker.PublishOverruns,
            actualMeanUs = mean,
            meanDilation = declaredUs > 0 ? mean / declaredUs : 0,
            p50Dilation = declaredUs > 0 ? p50 / declaredUs : 0,
            pauses = ticker.Pauses,
            iterations = ticker.Iterations,
            publishWorkMs = TicksToMicros(ticker.PublishWorkTicks) / 1000.0,
            declaredMicros = declaredUs,
            minIntervalUs = TicksToMicros(ticker.MinIntervalTicks),
            p50IntervalUs = TicksToMicros(ordered.Length == 0 ? 0 : ordered[ordered.Length / 2]),
            p99IntervalUs = TicksToMicros(ordered.Length == 0 ? 0 : ordered[Math.Min(ordered.Length - 1, ordered.Length * 99 / 100)]),
            maxIntervalUs = TicksToMicros(ticker.MaxIntervalTicks),
            lastPublished = ticker.LastPublished,
            cpuMs = ticker.CpuTime.TotalMilliseconds,
            timerStatus = ticker.TimerStatus,
            frequency = Stopwatch.Frequency,
            histogram = histogram.Length > 64 ? histogram.Take(64).ToArray() : histogram,
            histogramBuckets = histogram.Length
        };
    }

    private static double TicksToMicros(long ticks) => ticks * 1_000_000.0 / Stopwatch.Frequency;

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

    private static long EpochCapability()
    {
        try
        {
            var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetCallbackDeadlineCapabilities",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method is null ? 0 : method.CreateDelegate<Func<int>>()();
        }
        catch { return 0; }
    }

    private static Func<long>? EpochTick()
    {
        try
        {
            var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_TickCallbackDeadlineEpoch",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method?.CreateDelegate<Func<long>>();
        }
        catch { return null; }
    }

    private static Func<long>? EpochRead()
    {
        try
        {
            var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_ReadCallbackDeadlineEpoch",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method?.CreateDelegate<Func<long>>();
        }
        catch { return null; }
    }

    private static long ClockCapability() => DeadlineVersion() == 1 ? 1 : 0;

    private static int InterpreterVersion()
    {
        try
        {
            var method = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicyVersion",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            return method is null ? 0 : method.CreateDelegate<Func<int>>()();
        }
        catch { return 0; }
    }

    private static MapRunOptions Deadline(string mode, int deadlineMs, int interval) => new()
    {
        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
        PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(deadlineMs),
        PrototypeDeadlinePollInterval = interval,
        PrototypeDeadlineMode = mode == "epoch" ? MapDeadlineMode.Epoch : MapDeadlineMode.Clock,
        TickCount = 0
    };

    private static MapPackage MissingPackage() => new(
        "epoch-missing",
        Path.Combine(Path.GetTempPath(), "runeclr-epoch-" + Guid.NewGuid().ToString("N") + ".dll"),
        "Unused");

    private static int Fail(string message)
    {
        Console.WriteLine(Json(new { ok = false, error = message }));
        return 2;
    }

    private static string Json(object value) => JsonSerializer.Serialize(value);

    private sealed record Options
    {
        public string Command { get; private init; } = "probe";
        public string Mode { get; private init; } = "off";
        public string EntryType { get; private init; } = "EpochBench.Author.ArithmeticSmall";
        public int Ticks { get; private init; } = 20;
        public int Samples { get; private init; } = 7;
        public int Warmup { get; private init; } = 2;
        public int PollInterval { get; private init; } = 100;
        public int DeadlineMs { get; private init; } = 10_000;
        public int TickerMicros { get; private init; } = 1_000;
        public int EpochPeriodMicros { get; private init; }
        public TickerWait Wait { get; private init; } = TickerWait.Sleep;
        public int Sessions { get; private init; } = 4;
        public int PauseAtMs { get; private init; }
        public int PauseForMs { get; private init; }
        public string EntryPath { get; private init; } = AuthorPath;
        public MapExecutionPolicy Policy { get; private init; } = MapExecutionPolicy.RequireInterpreter;

        public static Options Parse(string[] args)
        {
            var options = new Options();
            for (var index = 0; index < args.Length; index++)
            {
                var value = index + 1 < args.Length ? args[index + 1] : null;
                switch (args[index])
                {
                    case "probe": options = options with { Command = "probe" }; break;
                    case "selfcheck": options = options with { Command = "selfcheck" }; break;
                    case "mechanical": options = options with { Command = "mechanical" }; break;
                    case "timing": options = options with { Command = "timing" }; break;
                    case "cutoff": options = options with { Command = "cutoff" }; break;
                    case "ticker": options = options with { Command = "ticker" }; break;
                    case "--mode": options = options with { Mode = value! }; index++; break;
                    case "--entry": options = options with { EntryType = value! }; index++; break;
                    case "--ticks": options = options with { Ticks = int.Parse(value!) }; index++; break;
                    case "--samples": options = options with { Samples = int.Parse(value!) }; index++; break;
                    case "--warmup": options = options with { Warmup = int.Parse(value!) }; index++; break;
                    case "--interval": options = options with { PollInterval = int.Parse(value!) }; index++; break;
                    case "--deadline-ms": options = options with { DeadlineMs = int.Parse(value!) }; index++; break;
                    case "--ticker-us": options = options with { TickerMicros = int.Parse(value!) }; index++; break;
                    case "--sessions": options = options with { Sessions = int.Parse(value!) }; index++; break;
                    case "--pause-at-ms": options = options with { PauseAtMs = int.Parse(value!) }; index++; break;
                    case "--pause-for-ms": options = options with { PauseForMs = int.Parse(value!) }; index++; break;
                    case "concurrent": options = options with { Command = "concurrent" }; break;
                    case "proof": options = options with { Command = "proof" }; break;
                    case "nextgood": options = options with { Command = "nextgood" }; break;
                    case "pauseprobe": options = options with { Command = "pauseprobe" }; break;
                    case "--ticker-wait":
                        options = options with
                        {
                            Wait = value switch
                            {
                                "spin" => TickerWait.Spin,
                                "timer" => TickerWait.TimerResolution,
                                "hr" => TickerWait.HighResolution,
                                "hybrid" => TickerWait.Hybrid,
                                _ => TickerWait.Sleep
                            }
                        };
                        index++;
                        break;
                    case "--epoch-period-us":
                        options = options with { EpochPeriodMicros = int.Parse(value!) };
                        index++;
                        break;
                    case "--entry-path": options = options with { EntryPath = value! }; index++; break;
                    case "--policy":
                        options = options with
                        {
                            Policy = value == "default" ? MapExecutionPolicy.Default : MapExecutionPolicy.RequireInterpreter
                        };
                        index++;
                        break;
                    default: throw new ArgumentException("Unknown argument: " + args[index]);
                }
            }

            if (options.EpochPeriodMicros == 0)
                options = options with { EpochPeriodMicros = options.TickerMicros > 0 ? options.TickerMicros : 1_000 };
            if (options.TickerMicros > 0 && options.TickerMicros < options.EpochPeriodMicros)
                throw new ArgumentException("The ticker period must be at least the declared epoch period.");
            if (options.EpochPeriodMicros is < 1 or > 1_000_000)
                throw new ArgumentException("The declared epoch period must be 1..1000000 microseconds.");
            return options;
        }
    }
}
