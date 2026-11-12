using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32.SafeHandles;

namespace RuneCLR.Runtime;

/// <summary>
/// Process-wide trusted ticker for the opt-in epoch callback deadline. It owns at most one worker
/// thread, is leased by live epoch sessions, and advances only the native epoch counter. It never
/// holds an author load context, policy, session callback or author metadata.
/// </summary>
/// <remarks>
/// Clock/default sessions never touch this type (no thread, no capability probe, no epoch call).
/// The period is latched permanently by the first acquisition and is never reset, including after a
/// failed bootstrap or after the last release; the native side latches independently inside the
/// epoch factory. A fault is persistent for the process: later acquisitions and every live lease
/// fail closed with the captured type name, which the worker release can never erase.
/// The final release joins the worker with no timeout because the only bound calls are the trusted,
/// non-blocking native tick/read entry points and a blocking wait; that is not a general guarantee
/// for arbitrary delegated work. The host owns the dispose obligation: stop/dispose sessions from
/// ordinary host code, never from inside the ticker's own path.
/// Exception contract: configuration/environment failures detected before author files (missing
/// native capability, unsupported or conflicting period) are PlatformNotSupportedException;
/// runtime-health failures (a live lease observing a ticker fault, or any later Acquire after the
/// permanent process fault) are InvalidOperationException carrying the captured type name only.
/// </remarks>
internal static class CallbackEpochTicker
{
    private static readonly object Gate = new();
    private static Worker? _worker;
    private static int _leases;
    private static long _totalTicks;
    private static int _latchedPeriodMicros;
    private static string? _lastFaultType;
    private static int _liveWorkers;
    private static int _maxLiveWorkers;

    internal static int ActiveLeases { get { lock (Gate) return _leases; } }
    internal static int LatchedPeriodMicros { get { lock (Gate) return _latchedPeriodMicros; } }
    internal static bool Faulted => Volatile.Read(ref _lastFaultType) is not null;
    internal static string? FaultType => Volatile.Read(ref _lastFaultType);
    internal static long TotalTicks => Interlocked.Read(ref _totalTicks);

    // Concurrency diagnostics for tests: a regression that allowed two tickers would be visible as
    // MaxLiveWorkerCount > 1 even though TotalTicks alone cannot prove spacing.
    internal static int LiveWorkerCount => Volatile.Read(ref _liveWorkers);
    internal static int MaxLiveWorkerCount => Volatile.Read(ref _maxLiveWorkers);

    private static void NoteWorkerStarted()
    {
        int live = Interlocked.Increment(ref _liveWorkers);
        int max = Volatile.Read(ref _maxLiveWorkers);
        while (live > max)
        {
            int seen = Interlocked.CompareExchange(ref _maxLiveWorkers, live, max);
            if (seen == max) break;
            max = seen;
        }
    }

    private static void NoteWorkerStopped() => Interlocked.Decrement(ref _liveWorkers);

    /// <summary>Leases the shared ticker, starting it (and proving the counter advanced) on first use.</summary>
    internal static Lease Acquire(int periodMicros, Func<long> tick, Func<long> read)
    {
        ArgumentNullException.ThrowIfNull(tick);
        ArgumentNullException.ThrowIfNull(read);
        if (periodMicros is < 1 or > 1_000_000)
            throw new ArgumentOutOfRangeException(nameof(periodMicros), "The epoch period must be 1..1000000 microseconds.");
        lock (Gate)
        {
            // A process fault is permanent: no later acquisition may silently restart a ticker.
            string? latchedFault = Volatile.Read(ref _lastFaultType);
            if (latchedFault is not null)
                throw new InvalidOperationException($"The process epoch ticker failed ({latchedFault}).");

            // Permanent host latch: set on the first acquisition and never reset, even when the
            // bootstrap below fails or the last lease is released.
            if (_latchedPeriodMicros == 0)
                _latchedPeriodMicros = periodMicros;
            else if (_latchedPeriodMicros != periodMicros)
                throw new PlatformNotSupportedException(
                    $"The process epoch period is latched at {_latchedPeriodMicros} us and cannot serve {periodMicros} us.");

            if (_worker is null)
            {
                var worker = new Worker(periodMicros, tick, read);
                worker.Start(); // rolls back its own resources on failure; not published on throw
                NoteWorkerStarted();
                _worker = worker;
            }
            else
            {
                _worker.ThrowIfFaulted();
                if (_worker.Read() <= 0)
                    throw new PlatformNotSupportedException("The process epoch ticker did not advance the native counter.");
            }
            _leases++;
            return new Lease(_worker);
        }
    }

    private static void Release()
    {
        lock (Gate)
        {
            if (_leases == 0) return;
            _leases--;
            if (_leases != 0 || _worker is null) return;
            // Stop and join BEFORE any new acquisition can start another ticker, otherwise a
            // replacement worker would tick alongside the old one (too-short spacing, early
            // expiry). The worker never takes this gate, so joining here cannot deadlock.
            if (!_worker.Stop())
            {
                // The bound tick is expected to be non-blocking; if the join cannot complete, keep the
                // worker published and latch a permanent fault so no second ticker can ever start.
                ReportFault("RuntimeException:ThreadJoinIncomplete");
                return;
            }
            NoteWorkerStopped();
            _worker = null;
        }
    }

    /// <summary>
    /// Test-only, process-wide scoped override of the timer facade. It can be installed only while
    /// the ticker is idle (no leases, no worker), and disposal restores the facade flags only - it
    /// never clears the permanent fault latch or the latched period. The override makes Arm fail or
    /// Wait report the unexpected result, so the worker runs the SAME real fault path as a genuine
    /// SetWaitableTimer failure / WAIT_FAILED instead of short-circuiting the latch.
    /// </summary>
    internal static IDisposable InstallTestTimerFault(bool armFails, bool waitFails)
    {
        lock (Gate)
        {
            if (_leases != 0 || _worker is not null || Volatile.Read(ref _liveWorkers) != 0)
                throw new InvalidOperationException(
                    "The test timer fault hook requires an idle ticker (no leases and no live worker).");
            HighResolutionTimer.SetTestFault(armFails, waitFails);
            return new TestFaultScope();
        }
    }

    private sealed class TestFaultScope : IDisposable
    {
        private int _disposed;

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
            HighResolutionTimer.SetTestFault(false, false); // flags only; latch/period untouched
        }
    }

    /// <summary>
    /// Lock-free fault publication. The worker calls this from its fault/exit path, and the last
    /// release holds Gate while joining the worker, so taking Gate here would deadlock.
    /// </summary>
    internal static void ReportFault(string typeName)
    {
        Interlocked.CompareExchange(ref _lastFaultType, typeName, null);
    }

    internal sealed class Lease : IDisposable
    {
        private readonly Worker _worker;
        private int _released;
        private string? _faultType;

        internal Lease(Worker worker) => _worker = worker;

        internal string? FaultType => _faultType ?? _worker.FaultType;

        /// <summary>Host-gate fault check. It never rescues an infinite body; it only fails closed.</summary>
        internal void ThrowIfFaulted()
        {
            var fault = _faultType ?? _worker.FaultType;
            if (fault is null) return;
            _faultType = fault; // preserved on the lease even after the worker is released
            throw new InvalidOperationException($"The process epoch ticker failed ({fault}).");
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _released, 1) == 0) Release();
        }
    }

    internal sealed class Worker
    {
        private readonly int _periodMicros;
        private readonly Func<long> _tick;
        private readonly Func<long> _read;
        private readonly CancellationTokenSource _cancel = new();
        private readonly Thread _thread;
        private volatile string? _faultType;

        internal Worker(int periodMicros, Func<long> tick, Func<long> read)
        {
            _periodMicros = periodMicros;
            _tick = tick;
            _read = read;
            _thread = new Thread(Run) { IsBackground = true, Name = "RuneCLR epoch ticker" };
        }

        internal int PeriodMicros => _periodMicros;
        internal string? FaultType => _faultType;

        internal long Read() => _read();

        internal void ThrowIfFaulted()
        {
            var fault = _faultType;
            if (fault is not null)
                throw new InvalidOperationException($"The process epoch ticker failed ({fault}).");
        }

        internal void Start()
        {
            try
            {
                // Bootstrap before any author code exists: one tick plus a positive read proves the
                // native counter is live, so a callback Begin can never observe epoch 0.
                long value = _tick();
                if (value <= 0 || _read() <= 0)
                    throw new PlatformNotSupportedException("The native epoch counter did not start.");
                // The trusted worker must not inherit the caller's ExecutionContext (policy scopes,
                // AsyncLocal state) into its thread.
                if (ExecutionContext.IsFlowSuppressed())
                    _thread.Start();
                else
                    using (ExecutionContext.SuppressFlow()) _thread.Start();
            }
            catch
            {
                // Roll back an unstarted worker. No thread is running, so no join is attempted.
                try { _cancel.Cancel(); } catch (Exception) { }
                _cancel.Dispose();
                throw;
            }
        }

        private void Run()
        {
            SafeWaitHandle? timer = null;
            try
            {
                (timer, var createFault) = HighResolutionTimer.Create();
                if (createFault is not null)
                {
                    Fault(createFault);
                    return;
                }
                while (!_cancel.IsCancellationRequested)
                {
                    if (timer is not null)
                    {
                        if (!HighResolutionTimer.Arm(timer, _periodMicros))
                        {
                            Fault(HighResolutionTimer.Describe("SetWaitableTimer"));
                            return;
                        }
                        var outcome = HighResolutionTimer.Wait(timer, _cancel.Token);
                        if (outcome == WaitOutcome.Cancelled) return;   // exact cancellation index only
                        if (outcome == WaitOutcome.Failed)
                        {
                            Fault(HighResolutionTimer.Describe("WaitForMultipleObjects"));
                            return;
                        }
                    }
                    else if (_cancel.Token.WaitHandle.WaitOne(Milliseconds(_periodMicros)))
                    {
                        return;
                    }
                    if (_cancel.IsCancellationRequested) return;
                    _tick();
                    Interlocked.Increment(ref _totalTicks);
                }
            }
            catch (Exception error)
            {
                // Scalar only: the fault is reported by type name, never by reading an author message.
                Fault(error.GetType().FullName ?? "Exception");
            }
            finally
            {
                try { timer?.Dispose(); } catch (Exception) { }
            }
        }

        private void Fault(string typeName)
        {
            _faultType ??= typeName;
            CallbackEpochTicker.ReportFault(_faultType!);
        }

        private static int Milliseconds(int periodMicros) => (periodMicros + 999) / 1000;

        /// <summary>Stops and joins the worker; false means the thread is still alive afterwards.</summary>
        internal bool Stop()
        {
            try { _cancel.Cancel(); } catch (Exception) { }
            if (_thread.IsAlive && _thread != Thread.CurrentThread)
            {
                try { _thread.Join(); } catch (Exception) { }
            }
            bool stopped = !_thread.IsAlive;
            if (stopped)
            {
                try { _cancel.Dispose(); } catch (Exception) { }
            }
            return stopped;
        }
    }

    private enum WaitOutcome { Tick, Cancelled, Failed }

    /// <summary>
    /// Windows high-resolution waitable timer when the OS supports it; the waiting thread blocks,
    /// so the normal path never spins. Each iteration re-arms exactly one period: spacing is never
    /// shorter than declared and a late tick is never replayed as a burst.
    /// </summary>
    private static class HighResolutionTimer
    {
        private const uint HighResolution = 0x00000002;
        private const uint AllAccess = 0x1F0003;
        private const uint Infinite = 0xFFFFFFFF;
        private const int ErrorInvalidParameter = 87;

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern SafeWaitHandle CreateWaitableTimerExW(IntPtr attributes, string? name, uint flags, uint access);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetWaitableTimer(SafeWaitHandle handle, ref long dueTime, int period,
            IntPtr completionRoutine, IntPtr completionArg, bool resume);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint WaitForMultipleObjects(uint count, IntPtr[] handles, bool waitAll, uint milliseconds);

        private static int s_testArmFails;
        private static int s_testWaitFails;

        internal static void SetTestFault(bool armFails, bool waitFails)
        {
            Volatile.Write(ref s_testArmFails, armFails ? 1 : 0);
            Volatile.Write(ref s_testWaitFails, waitFails ? 1 : 0);
        }

        internal static string Describe(string call) =>
            $"Win32Exception:{call}:{Marshal.GetLastWin32Error()}";

        internal static (SafeWaitHandle? Handle, string? Fault) Create()
        {
            if (!OperatingSystem.IsWindows()) return (null, null);
            try
            {
                var handle = CreateWaitableTimerExW(IntPtr.Zero, null, HighResolution, AllAccess);
                if (!handle.IsInvalid) return (handle, null);
                int error = Marshal.GetLastWin32Error();
                handle.Dispose();
                // ERROR_INVALID_PARAMETER means this OS predates the high-resolution flag; that is
                // the documented coarse fallback, not a fault.
                if (error == ErrorInvalidParameter) return (null, null);
                return (null, $"Win32Exception:CreateWaitableTimerExW:{error}");
            }
            catch (Exception error)
            {
                return (null, error.GetType().FullName ?? "Exception");
            }
        }

        internal static bool Arm(SafeWaitHandle handle, int periodMicros)
        {
            // Test override only: same return path as a genuine SetWaitableTimer failure.
            if (Volatile.Read(ref s_testArmFails) != 0) return false;
            long due = -(long)periodMicros * 10; // negative = relative, 100 ns units
            return SetWaitableTimer(handle, ref due, 0, IntPtr.Zero, IntPtr.Zero, false);
        }

        internal static WaitOutcome Wait(SafeWaitHandle handle, CancellationToken cancel)
        {
            // Test override only: same path as WAIT_FAILED (unexpected result -> Fault).
            if (Volatile.Read(ref s_testWaitFails) != 0) return WaitOutcome.Failed;
            IntPtr[] handles = [handle.DangerousGetHandle(), cancel.WaitHandle.SafeWaitHandle.DangerousGetHandle()];
            uint result = WaitForMultipleObjects(2, handles, false, Infinite);
            if (result == 0) return WaitOutcome.Tick;       // WAIT_OBJECT_0: timer
            if (result == 1) return WaitOutcome.Cancelled;  // WAIT_OBJECT_0 + 1: cancellation event
            return WaitOutcome.Failed;                      // WAIT_FAILED / abandoned / unexpected
        }
    }
}
