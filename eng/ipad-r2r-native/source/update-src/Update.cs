using System;

namespace TrustedUpdate;

public sealed class Update
{
    public int Run(IHostApi host, Func<int, int> callback)
    {
        int value = Business.Execute(host, callback);
        Console.WriteLine($"UPDATE_RUN result={value}");
        return value + 1;
    }
}
