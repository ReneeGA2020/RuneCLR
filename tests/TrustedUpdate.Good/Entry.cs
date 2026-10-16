namespace TrustedUpdate.Good;

public static class Entry
{
    public static void Activate()
    {
        var marker = Environment.GetEnvironmentVariable("RUNECLR_TRUSTED_UPDATE_MARKER");
        if (!string.IsNullOrEmpty(marker))
            File.WriteAllText(marker, "activated");
    }

    public static int Tick(int value) => value + 7;
}
