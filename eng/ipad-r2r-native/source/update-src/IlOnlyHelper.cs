using System;

namespace TrustedUpdate;

public static class IlOnlyHelper
{
    public static int Compute(int value)
    {
        int result = checked(value * 3 + 7);
        Console.WriteLine("IL_HELPER_RESULT=" + result);
        return result;
    }
}
