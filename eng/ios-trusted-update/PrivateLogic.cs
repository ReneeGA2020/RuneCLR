using System;

namespace TrustedUpdate;

public static class PrivateBehavior
{
    public static int Value()
    {
        int value = VersionValue.Get();
        Console.WriteLine("PRIVATE_VALUE=" + value);
        return value;
    }
}
