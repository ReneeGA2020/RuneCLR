namespace TrustedUpdate.Throwing;

public static class Entry
{
    public static void Activate() =>
        throw new InvalidOperationException("update-private-failure-9f3c");
}
