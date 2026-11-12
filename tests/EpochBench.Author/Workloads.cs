using RuneCLR;

namespace EpochBench.Author;

/// <summary>Deterministic interpreter kernels. The same compiled bytes run in every lane.</summary>
public static class Kernel
{
    public static long Arithmetic(int units, long seed)
    {
        long state = seed | 1;
        long accumulator = 0;
        for (var index = 0; index < units; index++)
        {
            state ^= state << 13;
            state ^= (long)((ulong)state >> 7);
            state ^= state << 17;
            if ((state & 0x100) != 0)
                accumulator += state & 0xFFFF;
            else
                accumulator -= state & 0xFF;
            if ((index & 0x3FF) == 0) accumulator ^= state;
        }

        return accumulator;
    }

    public static long CallHeavy(int units, int seed)
    {
        IWorker worker = new AddWorker();
        var state = seed | 1;
        long accumulator = 0;
        for (var index = 0; index < units; index++)
        {
            var value = worker.Step((int)(state & 0xFF));
            var squared = Square(value);
            var twisted = Twist(squared);
            if ((twisted & 1) != 0) accumulator += twisted;
            else accumulator -= Bias(squared);
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF;
        }

        return accumulator;
    }

    public static long Mixed(int units, int seed)
    {
        long accumulator = 0;
        long state = seed | 1;
        for (var index = 0; index < units; index++)
        {
            state ^= state << 13;
            state ^= (long)((ulong)state >> 7);
            state ^= state << 17;
            accumulator += Square((int)(state & 0xFF));
            if ((state & 0x1F) == 0) accumulator ^= Twist((int)(state & 0xFF));
        }

        return accumulator;
    }

    private static int Square(int value) => (value * value) & 0xFFFF;

    private static int Twist(int value) => ((value << 3) ^ (value >> 2)) & 0xFFFF;

    private static int Bias(int value) => value + 1;
}

public interface IWorker
{
    int Step(int value);
}

public sealed class AddWorker : IWorker
{
    public int Step(int value) => value + 3;
}

/// <summary>Runs one kernel call per start/tick and logs a running checksum.</summary>
public abstract class BenchmarkScript : IMapScript
{
    private long checksum;
    private int steps;
    private IMapContext? context;

    protected abstract int Units { get; }

    protected abstract long Run(int units);

    public void OnStart(IMapContext context)
    {
        this.context = context;
        Step();
    }

    public void OnTick(MapTick tick) => Step();

    public void OnStop() => context = null;

    private void Step()
    {
        // Accumulating golden: the per-tick value is folded in with the step index so
        // repeated runs of the same kernel cannot cancel to a constant.
        checksum = unchecked(checksum * 1_000_003 + (Run(Units) ^ (steps * 2_654_435_761L)));
        steps++;
        context?.Log("checksum=" + checksum + ";steps=" + steps);
    }
}

public sealed class ArithmeticSmall : BenchmarkScript
{
    protected override int Units => 200_000;

    protected override long Run(int units) => Kernel.Arithmetic(units, 17);
}

public sealed class ArithmeticMedium : BenchmarkScript
{
    protected override int Units => 2_000_000;

    protected override long Run(int units) => Kernel.Arithmetic(units, 17);
}

public sealed class ArithmeticLong : BenchmarkScript
{
    protected override int Units => 40_000_000;

    protected override long Run(int units) => Kernel.Arithmetic(units, 17);
}

public sealed class CallHeavyMedium : BenchmarkScript
{
    protected override int Units => 400_000;

    protected override long Run(int units) => Kernel.CallHeavy(units, 17);
}

public sealed class CallHeavyLong : BenchmarkScript
{
    protected override int Units => 8_000_000;

    protected override long Run(int units) => Kernel.CallHeavy(units, 17);
}

public sealed class MixedSmall : BenchmarkScript
{
    protected override int Units => 100_000;

    protected override long Run(int units) => Kernel.Mixed(units, 17);
}

public sealed class MixedMedium : BenchmarkScript
{
    protected override int Units => 1_000_000;

    protected override long Run(int units) => Kernel.Mixed(units, 17);
}

/// <summary>Author tries to swallow whatever the deadline check raises and keeps working.</summary>
public sealed class CatchLoopLong : BenchmarkScript
{
    protected override int Units => 40_000_000;

    protected override long Run(int units)
    {
        long result = 0;
        for (var attempt = 0; attempt < 2; attempt++)
        {
            try
            {
                result += Kernel.Arithmetic(units, 17);
            }
            catch (Exception)
            {
                result -= 1;
            }
            finally
            {
                result ^= 3;
            }
        }

        return result;
    }
}

public sealed class ThrowingScript : IMapScript
{
    public void OnStart(IMapContext context) { }

    public void OnTick(MapTick tick) => throw new InvalidOperationException("author tick failure");

    public void OnStop() { }
}

public sealed class CleanupHeavyScript : IMapScript
{
    public void OnStart(IMapContext context) { }

    public void OnTick(MapTick tick) { }

    public void OnStop() => Kernel.Arithmetic(40_000_000, 17);
}

public sealed class CtorFails : IMapScript
{
    public CtorFails() => throw new InvalidOperationException("author constructor failure");

    public void OnStart(IMapContext context) { }

    public void OnTick(MapTick tick) { }

    public void OnStop() { }
}

/// <summary>Tick-only variants: nothing runs during OnStart, so a deadline trip
/// happens inside the pumped tick and the host can observe it.</summary>
public abstract class TickOnlyScript : IMapScript
{
    private long checksum;
    private int steps;

    protected abstract int Units { get; }

    protected abstract long Run(int units);

    public void OnStart(IMapContext context) { }

    public void OnTick(MapTick tick)
    {
        checksum ^= Run(Units) + steps;
        steps++;
    }

    public void OnStop() { }
}

public sealed class TickOnlyLong : TickOnlyScript
{
    protected override int Units => 40_000_000;

    protected override long Run(int units) => Kernel.Arithmetic(units, 17);
}

public sealed class TickOnlyCatchLong : TickOnlyScript
{
    protected override int Units => 40_000_000;

    protected override long Run(int units)
    {
        long result = 0;
        try
        {
            result += Kernel.Arithmetic(units, 17);
        }
        catch (Exception)
        {
            result -= 1;
        }
        finally
        {
            result ^= 3;
        }

        return result;
    }
}
