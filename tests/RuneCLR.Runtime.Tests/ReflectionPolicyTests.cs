using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class ReflectionPolicyTests
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Reflection policy rejects null before runtime binding", () => Expect<ArgumentNullException>(() => PrototypeReflectionPolicy.Enter(null!)));
        yield return ("Reflection policy rejects stock or disabled support before author loading", Disabled);
        yield return ("Session API policy requires interpretation before opening author files", () =>
            Expect<ArgumentException>(() => new MapRunner().Start(Missing(), new MapRunOptions { PrototypeApiPolicy = Policy() })));
        yield return ("Session API policy rejects unavailable bridge before opening author files", () =>
        {
            AppContext.TryGetSwitch("RuneCLR.EnableReflectionPolicy", out bool previous);
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", false);
            try
            {
                Expect<PlatformNotSupportedException>(() => new MapRunner().Start(Missing(), new MapRunOptions
                { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter, PrototypeApiPolicy = Policy() }));
            }
            finally { AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", previous); }
        });
        yield return ("Explicit shared assemblies require session API policy before opening author files", () =>
            Expect<ArgumentException>(() => new MapRunner().Start(Missing(), new MapRunOptions
            { PrototypeSharedAssemblies = [typeof(object).Assembly] })));
    }

    private static MapPackage Missing() => new("reflection-policy-missing", Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".dll"), "Missing");
    private static IApiAccessPolicy Policy() => GameplayCapabilityPolicy.CreateApiPolicy([], typeof(RuneCLR.IMapScript).Assembly.FullName!);

    private static void Disabled()
    {
        AppContext.TryGetSwitch("RuneCLR.EnableReflectionPolicy", out bool previous);
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", false);
        try
        {
            var policy = GameplayCapabilityPolicy.CreateApiPolicy([], typeof(RuneCLR.IMapScript).Assembly.FullName!);
            Expect<PlatformNotSupportedException>(() => PrototypeReflectionPolicy.Enter(policy));
        }
        finally { AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", previous); }
    }

    private static void Expect<T>(Action run) where T : Exception
    {
        try { run(); }
        catch (T) { return; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }
}
