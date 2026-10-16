using System;

namespace TrustedUpdate;

public static class Business
{
    public static int Execute(IHostApi host, Func<int, int> callback)
    {
        // Keep the selected R2R body independent of the late IL-only helper
        // assemblies; the host invokes those dependencies by reflection.
        int privateValue = 41;
        int echoed = host.Echo(privateValue);
        int callbackValue = callback(privateValue);
        int helperValue = privateValue * 3 + 7;
        Console.WriteLine($"UPDATE_BUSINESS private={privateValue} echo={echoed} callback={callbackValue} helper={helperValue}");
        return echoed + callbackValue + helperValue;
    }
}
