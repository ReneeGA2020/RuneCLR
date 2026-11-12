using RuneCLR;

namespace EpochDeadline.Author;

/// <summary>Maintained copy of the measured interpreter workloads (same kernels and sizes
/// as the sealed measurement campaign).</summary>
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
            if ((state & 0x100) != 0) accumulator += state & 0xFFFF;
            else accumulator -= state & 0xFF;
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

public abstract class Script : IMapScript
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
        checksum = unchecked(checksum * 1_000_003 + (Run(Units) ^ (steps * 2_654_435_761L)));
        steps++;
        context?.Log("checksum=" + checksum + ";steps=" + steps);
    }
}

public abstract class TickOnlyScript : IMapScript
{
    protected abstract int Units { get; }

    protected abstract long Run(int units);

    public void OnStart(IMapContext context) { }

    public void OnTick(MapTick tick) => Run(Units);

    public void OnStop() { }
}

public sealed class ArithmeticSmall : Script
{
    protected override int Units => 200_000;

    protected override long Run(int units) => Kernel.Arithmetic(units, 17);
}

public sealed class MixedSmall : Script
{
    protected override int Units => 100_000;

    protected override long Run(int units) => Kernel.Mixed(units, 17);
}

public sealed class CallHeavySmall : Script
{
    protected override int Units => 20_000;

    protected override long Run(int units) => Kernel.CallHeavy(units, 17);
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

public sealed class CleanupHeavy : IMapScript
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

public sealed class StartFails : IMapScript
{
    public void OnStart(IMapContext context) => throw new InvalidOperationException("author start failure");

    public void OnTick(MapTick tick) { }

    public void OnStop() { }
}
