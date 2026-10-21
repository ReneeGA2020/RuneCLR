using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.Runtime;

internal static class CallbackDeadlineTests
{
    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Invalid callback deadlines are rejected before opening author files", InvalidDeadlines);
        yield return ("Default policy requires RequireInterpreter for a callback deadline", DefaultPolicyRequiresInterpreter);
        yield return ("Instruction budget and callback deadline cannot be combined", BudgetAndDeadlineCannotCombine);
        yield return ("Callback deadline poll intervals are restricted to 1/100/1000", PollIntervalValidation);
        yield return ("Valid callback deadline intervals fail on stock mode before missing author IL", ValidIntervalsFailOnStock);
        yield return ("Default options preserve stock map behavior without prototype deadline", DefaultOptionsPreserveStock);
    }

    static void InvalidDeadlines()
    {
        foreach (var deadline in new[] { TimeSpan.Zero, TimeSpan.FromTicks(-1), TimeSpan.FromMilliseconds(-1) })
        {
            var options = new MapRunOptions { PrototypeCallbackDeadline = deadline };
            Expect<ArgumentOutOfRangeException>(() => new MapRunner().Start(MissingPackage(), options));
            Expect<ArgumentOutOfRangeException>(() => new MapRunner().Run(MissingPackage(), options));
        }
    }

    static void DefaultPolicyRequiresInterpreter()
    {
        var options = new MapRunOptions
        {
            PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(1)
        };
        Expect<ArgumentException>(() => new MapRunner().Start(MissingPackage(), options));
        Expect<ArgumentException>(() => new MapRunner().Run(MissingPackage(), options));
    }

    static void BudgetAndDeadlineCannotCombine()
    {
        var options = new MapRunOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeInstructionBudget = 1,
            PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(1)
        };
        Expect<ArgumentException>(() => new MapRunner().Start(MissingPackage(), options));
        Expect<ArgumentException>(() => new MapRunner().Run(MissingPackage(), options));
    }

    static void PollIntervalValidation()
    {
        foreach (var interval in new[] { 0, -1, 2, 99, 10000 })
        {
            var options = new MapRunOptions
            {
                ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(1),
                PrototypeDeadlinePollInterval = interval
            };
            Expect<ArgumentOutOfRangeException>(() => new MapRunner().Start(MissingPackage(), options));
        }
    }

    static void ValidIntervalsFailOnStock()
    {
        if (CallbackBridgeAvailable())
        {
            Console.WriteLine("SKIP valid callback-deadline lane: private bridge is available");
            return;
        }

        foreach (var interval in new[] { 1, 100, 1000 })
        {
            var options = new MapRunOptions
            {
                ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                PrototypeCallbackDeadline = TimeSpan.FromMilliseconds(1),
                PrototypeDeadlinePollInterval = interval,
                TickCount = 0
            };
            var missing = MissingPackage();
            Expect<PlatformNotSupportedException>(() => new MapRunner().Start(missing, options));
            Check(!File.Exists(missing.AssemblyPath), "Deadline rejection created or opened the missing author path.");
        }
    }

    static void DefaultOptionsPreserveStock()
    {
        using var session = new MapRunner().Start(Package("CounterMap"), new MapRunOptions { TickCount = 0 });
        Check(session.IsRunning, "Default stock session did not start.");
        var result = session.Stop();
        Check(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Default stock session failed.");
        Check(result.Report.PrototypeBudget is null, "Default session unexpectedly acquired instruction budget evidence.");
        Check(result.Report.PrototypeDeadline is null, "Default session unexpectedly acquired deadline evidence.");
        Check(result.Report.ExecutionPolicy == MapExecutionPolicy.Default, "Default session policy changed.");
        Check(result.Report.ExecutionPolicyVersion == 0, "Default session unexpectedly acquired a native policy version.");
    }

    static bool CallbackBridgeAvailable()
    {
        try
        {
            var type = typeof(AssemblyLoadContext);
            var required = type.GetMethod("RuneCLR_GetExecutionPolicyVersion",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            var deadline = type.GetMethod("RuneCLR_GetCallbackDeadlineVersion",
                BindingFlags.NonPublic | BindingFlags.Static, binder: null, types: Type.EmptyTypes, modifiers: null);
            if (required is null || required.ReturnType != typeof(int) || required.IsGenericMethod ||
                deadline is null || deadline.ReturnType != typeof(long) || deadline.IsGenericMethod)
                return false;
            return required.CreateDelegate<Func<int>>()() == 1 &&
                   deadline.CreateDelegate<Func<long>>()() == 1;
        }
        catch
        {
            return false;
        }
    }

    static MapPackage MissingPackage() => new(
        "deadline-missing",
        Path.Combine(Path.GetTempPath(), "runeclr-deadline-" + Guid.NewGuid().ToString("N") + ".dll"),
        "Unused");

    static MapPackage Package(string type) => new(
        "fixture",
        Path.Combine(AppContext.BaseDirectory, "fixtures", "RuneCLR.TestMaps.dll"),
        "RuneCLR.TestMaps." + type);

    static void Expect<T>(Action action) where T : Exception
    {
        try
        {
            action();
        }
        catch (T)
        {
            return;
        }

        throw new InvalidOperationException("Expected " + typeof(T).Name + ".");
    }

    static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
