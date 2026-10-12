namespace RuneCLR.PrivateDependency;

public static class PrivateState<T>
{
    private static int _starts;

    public static string Start(T value)
    {
#if DEPENDENCY_A
        const string flavor = "A";
#else
        const string flavor = "B";
#endif
        return $"{flavor}:v{typeof(PrivateState<T>).Assembly.GetName().Version}:starts={++_starts}:value={value}";
    }
}
