using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class HostContractPolicyTests
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract policy requires required interpretation before author files", PolicyRequiresInterpreter);
        yield return ("Host contract shared assemblies require a policy before author files", SharedRequiresPolicy);
        yield return ("Host contract shared assemblies must be default-context instances", SharedMustBeDefaultContext);
        yield return ("Host contract missing/disabled bridge rejects before author files", BridgeRejectsBeforeAuthorFile);
        yield return ("Host contract duplicate shared assemblies are rejected before author files", DuplicateSharedRejected);
        yield return ("Host contract RequireInterpreter without policy never silently defaults", RequireInterpreterWithoutPolicy);
    }

    private static void PolicyRequiresInterpreter()
    {
        var options = new HostContractSessionOptions { PrototypeApiPolicy = new AllowAllPolicy() };
        var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
            MissingPath(), "HostContract.Missing.Entry", ["Echo"], options));
        Check(error.Message.Contains("RequireInterpreter", StringComparison.OrdinalIgnoreCase) ||
            error.Message.Contains("interpreter", StringComparison.OrdinalIgnoreCase), error.Message);
    }

    private static void SharedRequiresPolicy()
    {
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeSharedAssemblies = [typeof(object).Assembly]
        };
        var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
            MissingPath(), "HostContract.Missing.Entry", ["Echo"], options));
        Check(error.Message.Contains("policy", StringComparison.OrdinalIgnoreCase), error.Message);
    }

    private static void SharedMustBeDefaultContext()
    {
        var bytes = File.ReadAllBytes(typeof(RecordingEcho).Assembly.Location);
        var isolated = Assembly.Load(bytes);
        Check(!ReferenceEquals(AssemblyLoadContext.GetLoadContext(isolated), AssemblyLoadContext.Default),
            "The isolated shared control did not leave the default context.");
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeApiPolicy = new AllowAllPolicy(),
            PrototypeSharedAssemblies = [isolated]
        };
        var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
            MissingPath(), "HostContract.Missing.Entry", ["Echo"], options));
        Check(error.Message.Contains("default", StringComparison.OrdinalIgnoreCase), error.Message);
    }

    private static void BridgeRejectsBeforeAuthorFile()
    {
        bool previous = AppContext.TryGetSwitch("RuneCLR.EnableReflectionPolicy", out bool enabled) && enabled;
        AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", false);
        try
        {
            var options = new HostContractSessionOptions
            {
                ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                PrototypeApiPolicy = new AllowAllPolicy()
            };
            string path = MissingPath();
            var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
                path, "HostContract.Missing.Entry", ["Echo"], options));
            Check(error is not FileNotFoundException, "The author file was read before preparing the bridge.");
            Check(error.Message.Contains("reflection-policy", StringComparison.OrdinalIgnoreCase) ||
                error.Message.Contains("CoreLib", StringComparison.OrdinalIgnoreCase) ||
                error.Message.Contains("disabled", StringComparison.OrdinalIgnoreCase), error.Message);
        }
        finally
        {
            AppContext.SetSwitch("RuneCLR.EnableReflectionPolicy", previous);
        }
    }

    private static void DuplicateSharedRejected()
    {
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeApiPolicy = new AllowAllPolicy(),
            PrototypeSharedAssemblies = [typeof(object).Assembly, typeof(object).Assembly]
        };
        var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
            MissingPath(), "HostContract.Missing.Entry", ["Echo"], options));
        Check(error.Message.Contains("unique", StringComparison.OrdinalIgnoreCase), error.Message);
    }

    private static void RequireInterpreterWithoutPolicy()
    {
        var options = new HostContractSessionOptions { ExecutionPolicy = MapExecutionPolicy.RequireInterpreter };
        string path = MissingPath();
        var error = Capture(() => new HostContractSession(typeof(IHostEcho), new RecordingEcho(),
            path, "HostContract.Missing.Entry", ["Echo"], options));
        Check(error is not FileNotFoundException, "RequireInterpreter without a policy read the author file.");
        Check(error.Message.Contains("RequireInterpreter", StringComparison.OrdinalIgnoreCase) ||
            error.Message.Contains("policy", StringComparison.OrdinalIgnoreCase) ||
            error.Message.Contains("CoreLib", StringComparison.OrdinalIgnoreCase) ||
            error.Message.Contains("bridge", StringComparison.OrdinalIgnoreCase), error.Message);
    }

    private static string MissingPath() =>
        Path.Combine(Path.GetTempPath(), "runeclr-host-missing-" + Guid.NewGuid().ToString("N") + ".dll");

    private static Exception Capture(Action action)
    {
        try { action(); }
        catch (Exception error) { return error; }
        throw new InvalidOperationException("Expected a host contract options failure.");
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private sealed class AllowAllPolicy : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) => ApiDecision.Allow;
    }
}
