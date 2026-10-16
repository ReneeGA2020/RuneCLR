using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
using RuneCLR.Experiments;
using TrustedComposition.Contract;

namespace TrustedComposition;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            string root = Path.GetFullPath(Value(args, "--updates"));
            bool observe = args.Contains("--observe");
            bool interpreted = args.Contains("--expect-interpreted");
            bool hostInterpreted = args.Contains("--expect-host-interpreted");
            bool jit = args.Contains("--jit-control");
            bool collectible = !args.Contains("--noncollectible");
            Check(!(interpreted && jit), "Conflicting execution expectations.");
            var host = new HostObject();
            var sessions = new List<SessionReport>();
            long[] timing = new long[3];
            var residentReuse = new List<int>();
            var residentModules = new List<IUpdateModule>();
            int? reactivation = null;
            int? reactivationPrivateValue = null;
            string? reactivationPrivateVersion = null;
            foreach (var spec in new[] { ("A", false), ("B", false), ("A", false), ("A", true), ("A", false) })
            {
                SessionResult completed = RunSession(root, spec.Item1, spec.Item2, host, observe, interpreted, hostInterpreted, jit, collectible, timing, residentReuse, residentModules);
                long boundaryStart = Stopwatch.GetTimestamp();
                bool collected = false;
                if (collectible)
                    collected = Collect(completed.Context);
                timing[2] += Stopwatch.GetTimestamp() - boundaryStart;
                Check(!collectible || collected, "Retired context did not collect: " + spec.Item1);
                sessions.Add(completed.Report with { Collected = collected });
                if (!collectible && sessions.Count == 2)
                {
                    UpdateOutcome returned = residentModules[0].Execute(host, false);
                    Check(returned.StaticCount == 4 && returned.PrivateCount == 4
                        && returned.PrivateValue == 101 && returned.PrivateVersion == "1.0.0.0",
                        "Returning to the already loaded version did not keep its A private binding.");
                    reactivation = returned.StaticCount;
                    reactivationPrivateValue = returned.PrivateValue;
                    reactivationPrivateVersion = returned.PrivateVersion;
                }
            }
            int extraCalls = residentReuse.Count + (reactivation is null ? 0 : 1);
            Check(host.Touches == 9 + extraCalls && host.InterfaceCalls == 9 + extraCalls && host.DelegateCalls == 9 + extraCalls && host.GenericCalls == 18 + extraCalls * 2,
                "Host call totals differ.");
            long managedBytes = GC.GetTotalMemory(false);
            long workingSetBytes = Environment.WorkingSet;
            Emit(args, new
            {
                Passed = true, Runtime = RuntimeInformation.FrameworkDescription,
                Architecture = RuntimeInformation.ProcessArchitecture.ToString(),
                Observation = observe, ExpectedUpdateInterpreter = interpreted, ExpectedHostInterpreter = hostInterpreted,
                JitControl = jit, Collectible = collectible,
                HostTouches = host.Touches, InterfaceCalls = host.InterfaceCalls,
                DelegateCalls = host.DelegateCalls, GenericCalls = host.GenericCalls, Sessions = sessions,
                TimingStartupUs = timing[0] * 1_000_000L / Stopwatch.Frequency,
                TimingCallbackUs = timing[1] * 1_000_000L / Stopwatch.Frequency,
                TimingBoundaryUs = timing[2] * 1_000_000L / Stopwatch.Frequency,
                ResidentReuseStaticCounts = residentReuse,
                ResidentReactivationStaticCount = reactivation,
                ResidentReactivationPrivateValue = reactivationPrivateValue,
                ResidentReactivationPrivateVersion = reactivationPrivateVersion,
                ManagedBytes = managedBytes,
                WorkingSetBytes = workingSetBytes,
                Witnesses = ExecutionWitness.Drain()
            });
            return 0;
        }
        catch (Exception error)
        {
            Emit(args, new { Passed = false, Error = error.ToString() });
            return 1;
        }
    }

    private static void Emit(string[] args, object result)
    {
        string json = JsonSerializer.Serialize(result);
        if (args.Contains("--report")) File.WriteAllText(Path.GetFullPath(Value(args, "--report")), json + Environment.NewLine);
        Console.WriteLine(json);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static SessionResult RunSession(string root, string version, bool fail, HostObject host,
        bool observe, bool interpreted, bool hostInterpreted, bool jit, bool collectible, long[] timing, List<int> residentReuse, List<IUpdateModule> residentModules)
    {
        string directory = Path.Combine(root, ".sessions", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        // R2R physical images can have one owning ALC. Independent copies keep
        // repeated noncollectible control sessions from reusing another owner.
        foreach (string file in Directory.EnumerateFiles(Path.Combine(root, version), "*.dll"))
            File.Copy(file, Path.Combine(directory, Path.GetFileName(file)));
        var context = new UpdateContext(directory, version, collectible);
        var weak = new WeakReference(context);
        var calls = new List<CallReport>();
        var entries = new List<LocatedEntry>();
        string? errorType = null;
        string? errorMessage = null;
        try
        {
            var startup = Stopwatch.StartNew();
            Assembly assembly = context.LoadFromAssemblyPath(Path.Combine(directory,
                $"TrustedComposition.Update.{version}.dll"));
            var module = (IUpdateModule)Activator.CreateInstance(assembly.GetType("TrustedComposition.UpdateModule", true)!)!;
            startup.Stop();
            timing[0] += startup.ElapsedTicks;
            var callback = Stopwatch.StartNew();
            try
            {
            for (int i = 1; i <= (fail ? 1 : 2); i++)
            {
                try
                {
                    UpdateOutcome actual = module.Execute(host, fail);
                    Check(!fail, "Failure case unexpectedly returned.");
                    int expected = version == "A" ? 101 : 202;
                    string privateVersion = version == "A" ? "1.0.0.0" : "2.0.0.0";
                    bool identity = ReferenceEquals(host, actual.ReturnedHost) && ReferenceEquals(host, actual.GenericHost);
                    Check(identity, "Shared host reference identity differs.");
                    Check(actual.StaticCount == i && actual.PrivateCount == i, "Module/private static state did not reset.");
                    Check(actual.PrivateValue == expected && actual.PrivateVersion == privateVersion, "Private binding differs.");
                    Check(actual.HelperValue == expected * 3 + 7 && actual.TouchValue == expected + 11, "Host/helper arithmetic differs.");
                    Check(actual.InterfaceValue == i + 19 && actual.DelegateValue == i + 19 &&
                        actual.GenericValue == actual.HelperValue, "Callback/delegate/generic result differs.");
                    calls.Add(new(i, actual.StaticCount, actual.PrivateCount, actual.PrivateValue,
                        actual.PrivateVersion, actual.HelperValue, actual.TouchValue, actual.InterfaceValue,
                        actual.DelegateValue, actual.GenericValue, identity));
                }
                catch (Exception error) when (fail && error.GetType().FullName == "TrustedComposition.UpdateFailureException")
                {
                    errorType = error.GetType().FullName;
                    errorMessage = error.Message;
                }
            }
            }
            finally
            {
                callback.Stop();
                timing[1] += callback.ElapsedTicks;
            }
            Check(!fail || errorType is not null, "Expected private failure was not copied.");
            if (observe)
            {
                string evidence = fail ? "Execute threw expected private exception after callbacks" : "Execute returned twice with checked results";
                entries.Add(Capture(typeof(HostObject).GetMethod(nameof(HostObject.Touch))!,
                    hostInterpreted, evidence + "; cumulative host Touch count=" + host.Touches));
                entries.Add(Capture(module.GetType().GetMethod("Execute")!, interpreted, evidence));
                Assembly dependency = context.Assemblies.Single(a => a.GetName().Name == "TrustedComposition.Private");
                entries.Add(Capture(dependency.GetType("TrustedComposition.PrivateLogic")!.GetMethod("Read")!,
                    interpreted, evidence + "; dependency arithmetic checked"));
                Assembly helper = context.Assemblies.Single(a => a.GetName().Name == "TrustedComposition.IlOnlyHelper");
                entries.Add(Capture(helper.GetType("TrustedComposition.IlOnlyHelper")!.GetMethod("Compute")!,
                    !jit, evidence + "; helper arithmetic checked"));
            }
            if (!collectible && !fail)
            {
                var again = (IUpdateModule)Activator.CreateInstance(module.GetType())!;
                UpdateOutcome reused = again.Execute(host, false);
                int expectedPrivate = version == "A" ? 101 : 202;
                string expectedPrivateVersion = version == "A" ? "1.0.0.0" : "2.0.0.0";
                Check(reused.StaticCount == 3 && reused.PrivateCount == 3
                    && reused.PrivateValue == expectedPrivate && reused.PrivateVersion == expectedPrivateVersion,
                    "Resident module statics did not continue for a second instance.");
                residentReuse.Add(reused.StaticCount);
                if (residentModules.Count == 0)
                    residentModules.Add(module);
            }
        }
        finally
        {
            if (collectible) context.Unload();
        }
        return new(weak, new(version, directory, collectible, fail, calls, errorType, errorMessage, false, entries));
    }

    private static LocatedEntry Capture(MethodBase method, bool interpreted, string evidence) =>
        new(method.Module.Assembly.Location, WindowsEntryObservation.Capture(method, interpreted, evidence));

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static bool Collect(WeakReference context)
    {
        for (int i = 0; context.IsAlive && i < 20; i++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }
        return !context.IsAlive;
    }

    private static string Value(string[] args, string name)
    {
        int index = Array.IndexOf(args, name);
        if (index < 0 || index + 1 == args.Length) throw new ArgumentException("Missing " + name);
        return args[index + 1];
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}

internal sealed class HostObject : IHostObject
{
    internal int Touches, InterfaceCalls, DelegateCalls, GenericCalls;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Touch(int value)
    {
        ExecutionWitness.Capture("host");
        Touches++;
        return value + 11;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Invoke(IUpdateCallback callback, int value) { InterfaceCalls++; return callback.Apply(value); }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public int InvokeDelegate(Func<int, int> callback, int value) { DelegateCalls++; return callback(value); }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public T Echo<T>(T value) { GenericCalls++; return value; }
}

internal sealed class UpdateContext(string directory, string version, bool collectible) : AssemblyLoadContext("trusted-" + version, isCollectible: collectible)
{
    protected override Assembly? Load(AssemblyName name)
    {
        Assembly contract = typeof(IUpdateModule).Assembly;
        if (name.Name == contract.GetName().Name)
        {
            if (name.FullName != contract.GetName().FullName) throw new FileLoadException("Contract identity differs.");
            return contract;
        }
        if (name.Name is "TrustedComposition.Private" or "TrustedComposition.IlOnlyHelper")
        {
            string path = Path.Combine(directory, name.Name + ".dll");
            if (AssemblyName.GetAssemblyName(path).FullName != name.FullName)
                throw new FileLoadException("Private assembly identity differs: " + name);
            return LoadFromAssemblyPath(path);
        }
        if (name.Name?.StartsWith("TrustedComposition.", StringComparison.Ordinal) == true)
            throw new FileNotFoundException("Unknown fixture dependency: " + name);
        return null;
    }
}

internal sealed record CallReport(int Invocation, int StaticCount, int PrivateCount, int PrivateValue,
    string PrivateVersion, int HelperValue, int TouchValue, int InterfaceValue, int DelegateValue, int GenericValue, bool HostIdentity);
internal sealed record SessionReport(string Version, string Directory, bool Collectible, bool ExpectedFailure, List<CallReport> Calls,
    string? ErrorType, string? ErrorMessage, bool Collected, List<LocatedEntry> Entries);
internal sealed record SessionResult(WeakReference Context, SessionReport Report);
internal sealed record LocatedEntry(string ImagePath, EntryObservation Entry);
