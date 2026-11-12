using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace RuneCLR.EpochBench;

public enum TickerWait
{
    Sleep,
    Spin,
    TimerResolution,
    HighResolution,
    Hybrid
}

/// <summary>Host epoch ticker shared by every session in the process.
///
/// The next publication is spaced from the actual previous publication time, so a
/// late wake never produces a catch-up burst or a short interval. Pausing stops
/// publications without accumulating a backlog. Wall and CPU cost are reported so
/// a high-resolution spin never hides its own price.</summary>
public sealed class EpochTicker : IDisposable
{
    private const uint CreateWaitableTimerHighResolution = 0x00000002;
    private const uint TimerAllAccess = 0x1F0003;

    private readonly int _periodMicros;
    private readonly Action<long> _publish;
    private readonly TickerWait _wait;
    private readonly ManualResetEventSlim _stop = new(false);
    private readonly object _sync = new();
    private Thread? _thread;
    private SafeWaitHandle? _timer;
    private string _timerStatus = "not-used";
    private volatile bool _paused;
    private long _ticks;
    private long _late;
    private long _violations;
    private long _pauses;
    private long _lastPublish;
    private long _iterations;
    private long _publishWork;
    private long _maxInterval;
    private long _publishFailures;
    private long _publishOverruns;
    private volatile bool _disposed;
    private long _minInterval = long.MaxValue;
    private TimeSpan _cpu;
    private readonly List<long> _intervals = new(1 << 14);

    public EpochTicker(int periodMicros, Action<long> publish, TickerWait wait = TickerWait.Sleep)
    {
        if (periodMicros < 1 || periodMicros > 1_000_000)
            throw new ArgumentOutOfRangeException(nameof(periodMicros));
        _periodMicros = periodMicros;
        _publish = publish;
        _wait = wait;
    }

    public int PeriodMicros => _periodMicros;

    public long Ticks { get { lock (_sync) return _ticks; } }
    public long LateTicks { get { lock (_sync) return _late; } }
    public long Violations { get { lock (_sync) return _violations; } }
    public long Pauses { get { lock (_sync) return _pauses; } }
    public long Iterations { get { lock (_sync) return _iterations; } }
    public long PublishWorkTicks { get { lock (_sync) return _publishWork; } }
    public long PublishFailures { get { lock (_sync) return _publishFailures; } }
    public long PublishOverruns { get { lock (_sync) return _publishOverruns; } }
    public long LastPublished { get { lock (_sync) return _lastPublish; } }
    public long MaxIntervalTicks { get { lock (_sync) return _maxInterval; } }
    public double MeanIntervalTicks
    {
        get { lock (_sync) return _intervals.Count == 0 ? 0 : _intervals.Sum() / (double)_intervals.Count; }
    }
    public long MinIntervalTicks { get { lock (_sync) return _minInterval == long.MaxValue ? 0 : _minInterval; } }
    public TimeSpan CpuTime { get { lock (_sync) return _cpu; } }
    public string TimerStatus { get { lock (_sync) return _timerStatus; } }
    public long[] Intervals { get { lock (_sync) return _intervals.ToArray(); } }

    public void Start()
    {
        if (_thread is not null) throw new InvalidOperationException("The ticker is already started.");
        // The hybrid needs a 1 ms timer floor for its sleep phase, then spins the tail.
        if (_wait is TickerWait.TimerResolution or TickerWait.Hybrid) timeBeginPeriod(1);
        if (_wait == TickerWait.HighResolution) _timer = CreateHighResolutionTimer();
        _thread = new Thread(Loop) { IsBackground = true, Name = "epoch-ticker" };
        _thread.Start();
    }

    public void Pause()
    {
        lock (_sync) _pauses++;
        _paused = true;
    }

    public void Resume() => _paused = false;

    private SafeWaitHandle? CreateHighResolutionTimer()
    {
        var handle = CreateWaitableTimerExW(IntPtr.Zero, null, CreateWaitableTimerHighResolution, TimerAllAccess);
        if (handle is null || handle.IsInvalid)
        {
            lock (_sync) _timerStatus = "unsupported:" + Marshal.GetLastWin32Error();
            handle?.Dispose();
            return null;
        }

        lock (_sync) _timerStatus = "high-resolution";
        return handle;
    }

    private void Loop()
    {
        // Checked ceil conversion: the declared period must never be shorter than the
        // requested microseconds by a rounding fraction (M3 precondition for +1 budget).
        var periodTicks = checked((long)Math.Ceiling(_periodMicros * (double)Stopwatch.Frequency / 1_000_000.0));
        if (periodTicks < 1) periodTicks = 1;
        var process = Process.GetCurrentProcess();
        var next = Stopwatch.GetTimestamp() + periodTicks;
        long previous = 0;
        try
        {
            while (!_stop.IsSet)
            {
                lock (_sync) _iterations++;
                var now = Stopwatch.GetTimestamp();
                var remainingMs = (next - now) * 1000.0 / Stopwatch.Frequency;
                if (remainingMs > 0)
                {
                    Wait(remainingMs, next);
                    continue;
                }

                if (_paused)
                {
                    next = Stopwatch.GetTimestamp() + periodTicks;
                    previous = 0;
                    _stop.Wait(1);
                    continue;
                }

                if (_disposed) break;
                var publishStart = Stopwatch.GetTimestamp();
                long published;
                lock (_sync) published = ++_ticks * (long)periodTicks;
                try { if (!_disposed) _publish(published); }
                catch { lock (_sync) _publishFailures++; }
                var publishEnd = Stopwatch.GetTimestamp();

                if (previous != 0)
                {
                    var interval = publishStart - previous;
                    lock (_sync)
                    {
                        if (interval < periodTicks) _violations++;
                        if (interval > periodTicks * 1.5) _late++;
                        if (interval > _maxInterval) _maxInterval = interval;
                        if (interval < _minInterval) _minInterval = interval;
                        if (_intervals.Count < 1 << 20) _intervals.Add(interval);
                    }
                }

                lock (_sync) { _lastPublish = published; _publishWork += publishEnd - publishStart; }
                previous = publishStart;
                next = publishStart + periodTicks;
                if (publishEnd - publishStart > periodTicks) lock (_sync) _publishOverruns++;
            }
        }
        finally
        {
            if (_wait is TickerWait.TimerResolution or TickerWait.Hybrid) timeEndPeriod(1);
            try
            {
                process.Refresh();
                lock (_sync) _cpu = process.TotalProcessorTime;
            }
            catch { }
            process.Dispose();
        }
    }

    private void Wait(double remainingMs, double next)
    {
        switch (_wait)
        {
            case TickerWait.Spin:
                while (Stopwatch.GetTimestamp() < next && !_stop.IsSet) Thread.SpinWait(64);
                break;
            case TickerWait.Hybrid:
                if (remainingMs > 0.7)
                    Thread.Sleep(Math.Max(1, (int)Math.Floor(remainingMs - 0.5)));
                else
                    while (Stopwatch.GetTimestamp() < next && !_stop.IsSet) Thread.SpinWait(32);
                break;
            case TickerWait.HighResolution:
                if (_timer is not null)
                {
                    var due = -(long)Math.Max(1, Math.Round(remainingMs * 10_000));
                    if (SetWaitableTimer(_timer, ref due, 0, IntPtr.Zero, IntPtr.Zero, false))
                    {
                        WaitForSingleObject(_timer, (uint)Math.Max(1, Math.Ceiling(Math.Min(remainingMs, 2.0))));
                        break;
                    }

                    lock (_sync) _timerStatus = "set-failed:" + Marshal.GetLastWin32Error();
                }

                Thread.Sleep(Math.Clamp((int)Math.Ceiling(remainingMs), 1, 2));
                break;
            default:
                Thread.Sleep(Math.Clamp((int)Math.Ceiling(remainingMs), 1, 2));
                break;
        }
    }

    public void Dispose()
    {
        _disposed = true;
        _stop.Set();
        var joined = _thread?.Join(TimeSpan.FromSeconds(10)) ?? true;
        if (!joined)
        {
            // Keep the wait resources alive: the loop may still be inside Wait.
            throw new InvalidOperationException("The epoch ticker did not stop within 10 seconds.");
        }

        _thread = null;
        _timer?.Dispose();
        _timer = null;
        _stop.Dispose();
    }

    [DllImport("winmm.dll", EntryPoint = "timeBeginPeriod")]
    private static extern uint timeBeginPeriod(uint period);

    [DllImport("winmm.dll", EntryPoint = "timeEndPeriod")]
    private static extern uint timeEndPeriod(uint period);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern SafeWaitHandle CreateWaitableTimerExW(IntPtr attributes, string? name, uint flags, uint access);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetWaitableTimer(SafeWaitHandle handle, ref long dueTime, int period,
        IntPtr completionRoutine, IntPtr argument, bool resume);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(SafeWaitHandle handle, uint milliseconds);
}
