using System.Runtime.CompilerServices;

namespace RuneCLR.Performance;

public sealed class Entity
{
    public int X, Y, Vx, Vy, Hp, State, Cooldown;
}

public sealed class SoA
{
    public readonly int[] X, Y, Vx, Vy, Hp;
    public SoA(int count)
    {
        X = new int[count]; Y = new int[count]; Vx = new int[count];
        Vy = new int[count]; Hp = new int[count];
    }
}

public static class Workloads
{
    // Only this assembly owns gameplay logic. The supplied context is implemented
    // by the trusted timing host, exercising the shared map API boundary.
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long HostApi(IMapContext context, int operations)
    {
        long checksum = 0;
        for (int i = 0; i < operations; i++)
        {
            context.Charge();
            EntityId entity = context.SpawnEntity("benchmark-unit");
            checksum += entity.Value;
            context.DestroyEntity(entity);
            if ((i & 63) == 0) context.Log("benchmark-tick");
        }
        return checksum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long AllocationsGenerics(int batches, int width)
    {
        long checksum = 0;
        for (int batch = 0; batch < batches; batch++)
        {
            var groups = new Dictionary<int, List<int>>(8);
            for (int group = 0; group < 8; group++) groups.Add(group, new List<int>());
            var labels = new Dictionary<string, int>(width);
            for (int i = 0; i < width; i++)
            {
                int value = (batch * 17 + i * 13) % 1000;
                groups[i & 7].Add(value);
                labels.Add("unit-" + i.ToString(), value);
            }
            foreach (List<int> group in groups.Values) checksum += GenericSum(group);
            checksum += labels["unit-0"] + labels.Count;
        }
        return checksum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static long GenericSum<T>(List<T> values) where T : struct, IConvertible
    {
        long sum = 0;
        foreach (T value in values) sum += value.ToInt64(null);
        return sum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long Numeric(int iterations)
    {
        int x = 123;
        long checksum = 0;
        for (int i = 0; i < iterations; i++)
        {
            x = (x * 17 + 31) % 65521;
            checksum += x;
        }
        return checksum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long EntitiesSoA(SoA data, int ticks)
    {
        for (int tick = 0; tick < ticks; tick++)
            for (int i = 0; i < data.X.Length; i++)
            {
                data.X[i] = (data.X[i] + data.Vx[i]) % 65521;
                data.Y[i] = (data.Y[i] + data.Vy[i]) % 65521;
                data.Hp[i] = (data.Hp[i] + tick + i) % 1000;
            }
        long checksum = 0;
        for (int i = 0; i < data.X.Length; i++)
            checksum += data.X[i] + data.Y[i] + data.Hp[i];
        return checksum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long EntitiesObjects(Entity[] data, int ticks)
    {
        for (int tick = 0; tick < ticks; tick++)
            for (int i = 0; i < data.Length; i++)
            {
                Entity e = data[i];
                e.X = (e.X + e.Vx) % 65521;
                e.Y = (e.Y + e.Vy) % 65521;
                e.Hp = (e.Hp + tick + i) % 1000;
            }
        long checksum = 0;
        foreach (Entity e in data) checksum += e.X + e.Y + e.Hp;
        return checksum;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long Skills(Entity[] data, int ticks)
    {
        for (int tick = 0; tick < ticks; tick++)
            for (int i = 0; i < data.Length; i++)
            {
                Entity e = data[i];
                if (e.State == 0)
                {
                    e.Cooldown--;
                    if (e.Cooldown <= 0) { e.State = 1; e.Cooldown = 3; }
                }
                else if (e.State == 1)
                {
                    e.Hp -= 3; e.State = 2; e.Cooldown = 5;
                }
                else
                {
                    e.Cooldown--;
                    if (e.Cooldown <= 0) { e.State = 0; e.Cooldown = 11; }
                }
            }
        long checksum = 0;
        foreach (Entity e in data) checksum += e.Hp + e.State + e.Cooldown;
        return checksum;
    }
}
