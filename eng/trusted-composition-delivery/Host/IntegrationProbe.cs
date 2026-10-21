using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using RuneCLR.TrustedUpdate;
using TrustedComposition.Contract;

static class IntegrationProbe
{
    const string Entry = "TrustedComposition.Update.A.dll";
    const string PrivateName = "TrustedComposition.Private.dll";
    const string HelperName = "TrustedComposition.IlOnlyHelper.dll";

    public static int Run()
    {
        var failures = 0;
        var root = Path.Combine(Path.GetTempPath(), "typed-delivery-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(root);
        try
        {
            using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var spki = key.ExportSubjectPublicKeyInfo();
            var calls = Prepare(root, "calls", key, spki);
            var callsRun = RunChild(calls, "calls");
            var callsReceipt = callsRun.Ok ? File.ReadAllBytes(calls.Receipt) : null;
            failures += Check("same signed session calls twice", callsRun.Ok);
            failures += Check("second call interface delegate generic", callsRun.Stdout.Contains("SECOND static=2 privateCount=2 interface=21 delegate=21 generic=310", StringComparison.Ordinal));
            failures += Check("receipt unchanged after second call and close",
                callsRun.Stdout.Contains("RECEIPT_AFTER_SECOND same=True", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("RECEIPT_AFTER_CLOSE same=True", StringComparison.Ordinal));
            failures += Check("normal close keeps the process locked",
                callsRun.Stdout.Contains("LOCKED None/ProcessSelectionLocked/None/locked", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("LOCK_CALLS 0", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("ACTIVATIONS 1", StringComparison.Ordinal));
            failures += Check("close during call executes the borrowed module",
                callsRun.Stdout.Contains("DURING static=3 privateCount=3 interface=22 delegate=22 generic=310 private=101 helper=310 touch=112 identity=True", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("NESTED entered=False", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("LATER entered=False failure=closed", StringComparison.Ordinal));
            failures += Check("session owner releases the host root",
                callsRun.Stdout.Contains("HOST_COLLECTED True", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("SESSION_RETAINED True", StringComparison.Ordinal)
                && callsRun.Stdout.Contains("HOST_ROOT null", StringComparison.Ordinal));
            var restored = RunChild(calls, "recover");
            failures += Check("new process restores A after session close",
                callsReceipt is not null && restored.Ok && Same(calls.Receipt, callsReceipt)
                && restored.Stdout.Contains("RECOVER_SOURCE LastKnownGood", StringComparison.Ordinal)
                && restored.Stdout.Contains("RECOVER_PATHS True", StringComparison.Ordinal));
            var fail = Prepare(root, "fail", key, spki);
            var failRun = RunChild(fail, "fail");
            var failReceipt = failRun.Ok ? File.ReadAllBytes(fail.Receipt) : null;
            failures += Check("author failure closes only the session", failRun.Ok);
            failures += Check("author failure clears the host root",
                failRun.Stdout.Contains("HOST_COLLECTED True", StringComparison.Ordinal)
                && failRun.Stdout.Contains("HOST_ROOT null", StringComparison.Ordinal)
                && failRun.Stdout.Contains("SESSION_RETAINED True", StringComparison.Ordinal));
            var restoredAfterFailure = RunChild(fail, "recover");
            failures += Check("new process restores A after author failure",
                failReceipt is not null && restoredAfterFailure.Ok && Same(fail.Receipt, failReceipt)
                && restoredAfterFailure.Stdout.Contains("RECOVER_SOURCE LastKnownGood", StringComparison.Ordinal)
                && restoredAfterFailure.Stdout.Contains("RECOVER_PATHS True", StringComparison.Ordinal));
        }
        finally
        {
            try { Directory.Delete(root, true); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }

        Console.WriteLine(failures == 0 ? "INTEGRATION PASS" : "INTEGRATION FAIL " + failures);
        return failures == 0 ? 0 : 1;
    }

    public static int Child(string[] args)
    {
        var mode = args[1];
        var request = File.ReadAllLines(args[2]).Select(line => line.Split('=', 2)).ToDictionary(pair => pair[0], pair => pair[1]);
        var files = request["files"].Split('|', StringSplitOptions.RemoveEmptyEntries).Select(pair =>
        {
            var split = pair.IndexOf('=');
            return (pair[..split], pair[(split + 1)..]);
        }).ToArray();
        if (mode == "recover")
            return RecoverChild(request);

        var staged = DeliverySession.StageAsync(request["releases"], request["final"], request["document"], request["spki"], request["receipt"], files, false).GetAwaiter().GetResult();
        var session = DeliverySession.LogicalSession;
        if (session is null || !staged.Activated || staged.StaticCount != 1 || staged.PrivateValue != 101 || staged.HelperValue != 310 || !staged.Identity || staged.Calls != 1 || DeliverySession.LogicalHost is null)
        {
            Console.WriteLine("BAD " + mode + " stage");
            return 1;
        }

        if (mode == "calls")
        {
            var afterStage = File.ReadAllBytes(request["receipt"]);
            var weak = ExerciseCalls(session, afterStage, request, out var ok);
            var collected = weak is not null && HostCollected(weak);
            var retained = SessionRetained(session);
            Console.WriteLine("HOST_COLLECTED " + collected);
            Console.WriteLine("SESSION_RETAINED " + retained);
            Console.WriteLine("HOST_ROOT " + (DeliverySession.LogicalHost is null ? "null" : "live"));
            Console.WriteLine(ok && collected && retained ? "OK calls" : "BAD calls");
            return ok && collected && retained ? 0 : 1;
        }

        var before = File.ReadAllBytes(request["receipt"]);
        var failWeak = ExerciseFail(session, before, request, out var okFail);
        var failCollected = failWeak is not null && HostCollected(failWeak);
        var failRetained = SessionRetained(session);
        Console.WriteLine("HOST_COLLECTED " + failCollected);
        Console.WriteLine("SESSION_RETAINED " + failRetained);
        Console.WriteLine("HOST_ROOT " + (DeliverySession.LogicalHost is null ? "null" : "live"));
        Console.WriteLine(okFail && failCollected && failRetained ? "OK fail" : "BAD fail");
        return okFail && failCollected && failRetained ? 0 : 1;
    }

    static int RecoverChild(Dictionary<string, string> request)
    {
        var facts = DeliverySession.RecoverOnly(request["releases"], request["spki"], request["receipt"], false);
        var entry = Path.Combine(request["final"], Entry);
        var privatePath = Path.Combine(request["final"], PrivateName);
        var helper = Path.Combine(request["final"], HelperName);
        var finalDir = request["final"];
        var paths = SameSignedFile(facts.LoadedEntry, finalDir, Entry)
            && SameFile(facts.Entry, entry)
            && SameSignedFile(facts.LoadedPrivate, finalDir, PrivateName)
            && SameFile(facts.ListedPrivate, privatePath)
            && SameSignedFile(facts.LoadedHelper, finalDir, HelperName)
            && SameFile(facts.ListedHelper, helper);
        var ok = facts.Activated && facts.Version == "A" && facts.Source == "LastKnownGood"
            && facts.PrivateValue == 101 && facts.HelperValue == 310 && facts.TouchValue == 112
            && facts.InterfaceValue == 20 && facts.DelegateValue == 20 && facts.GenericValue == 310
            && facts.Identity && facts.StaticCount == 1 && facts.PrivateCount == 1
            && facts.Calls == 1 && facts.Detail == "executed" && paths;
        Console.WriteLine("RECOVER_SOURCE " + facts.Source);
        Console.WriteLine("RECOVER_LOADED_ENTRY " + facts.LoadedEntry);
        Console.WriteLine("RECOVER_LOADED_PRIVATE " + facts.LoadedPrivate);
        Console.WriteLine("RECOVER_LOADED_HELPER " + facts.LoadedHelper);
        Console.WriteLine("RECOVER_FINAL_ENTRY " + entry);
        Console.WriteLine("RECOVER_PATHS " + paths);
        Console.WriteLine(ok ? "OK recover" : "BAD recover");
        return ok ? 0 : 1;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference<DeliveryHostObject>? ExerciseCalls(TypedSession<IUpdateModule> session, byte[] stageReceipt, Dictionary<string, string> request, out bool ok)
    {
        var host = DeliverySession.LogicalHost;
        if (host is null)
        {
            ok = false;
            return null;
        }

        var weak = new WeakReference<DeliveryHostObject>(host);
        var secondOk = SecondCall(session, host);
        var sameSecond = stageReceipt.AsSpan().SequenceEqual(File.ReadAllBytes(request["receipt"]));
        Console.WriteLine("RECEIPT_AFTER_SECOND same=" + sameSecond);
        var reentryOk = Reentry(session);
        var duringOk = CloseDuringCall(session, host);
        var sameClose = stageReceipt.AsSpan().SequenceEqual(File.ReadAllBytes(request["receipt"]));
        Console.WriteLine("RECEIPT_AFTER_CLOSE same=" + sameClose);
        var locked = DeliverySession.RecoverOnly(request["releases"], request["spki"], request["receipt"], false);
        Console.WriteLine("LOCKED " + locked.Recovery);
        Console.WriteLine("LOCK_CALLS " + locked.Calls);
        Console.WriteLine("ACTIVATIONS " + DeliverySession.TotalActivations);
        ok = secondOk && sameSecond && reentryOk && duringOk && sameClose
            && !locked.Activated
            && locked.Recovery == "None/ProcessSelectionLocked/None/locked"
            && locked.Calls == 0
            && DeliverySession.TotalActivations == 1
            && DeliverySession.LogicalHost is null
            && session.IsClosed;
        return weak;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference<DeliveryHostObject>? ExerciseFail(TypedSession<IUpdateModule> session, byte[] before, Dictionary<string, string> request, out bool ok)
    {
        var host = DeliverySession.LogicalHost;
        if (host is null)
        {
            ok = false;
            return null;
        }

        var weak = new WeakReference<DeliveryHostObject>(host);
        var entered = false;
        var failed = DeliverySession.InvokeLogical(candidate =>
        {
            entered = true;
            candidate.Execute(host, true);
            return 0;
        });
        var again = false;
        var later = session.Invoke(candidate =>
        {
            again = true;
            return candidate.Execute(host, false).PrivateValue;
        });
        session.Close();
        session.Close();
        var closed = session.Invoke(candidate =>
        {
            again = true;
            return 1;
        });
        var locked = DeliverySession.RecoverOnly(request["releases"], request["spki"], request["receipt"], false);
        var after = File.ReadAllBytes(request["receipt"]);
        Console.WriteLine("FAIL_CODE " + failed.Failure);
        Console.WriteLine("LOCKED " + locked.Recovery);
        Console.WriteLine("ACTIVATIONS " + DeliverySession.TotalActivations);
        ok = entered
            && !failed.Completed
            && failed.Failure == "author-failed"
            && failed.Value == 0
            && session.IsClosed
            && !again
            && later.Failure == "closed"
            && closed.Failure == "closed"
            && DeliverySession.TotalActivations == 1
            && DeliverySession.LogicalHost is null
            && !locked.Activated
            && locked.Recovery == "None/ProcessSelectionLocked/None/locked"
            && locked.Calls == 0
            && before.AsSpan().SequenceEqual(after);
        return weak;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static bool HostCollected(WeakReference<DeliveryHostObject> weak)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        return !weak.TryGetTarget(out _);
    }

    static bool SessionRetained(TypedSession<IUpdateModule> session) =>
        ReferenceEquals(session, DeliverySession.LogicalSession) && session.IsClosed;

    static bool SecondCall(TypedSession<IUpdateModule> session, DeliveryHostObject host)
    {
        var identity = false;
        var staticCount = 0;
        var privateCount = 0;
        var helper = 0;
        var touch = 0;
        var iface = 0;
        var delegated = 0;
        var generic = 0;
        var version = "";
        var second = DeliverySession.InvokeLogical(candidate =>
        {
            var outcome = candidate.Execute(host, false);
            staticCount = outcome.StaticCount;
            privateCount = outcome.PrivateCount;
            helper = outcome.HelperValue;
            touch = outcome.TouchValue;
            iface = outcome.InterfaceValue;
            delegated = outcome.DelegateValue;
            generic = outcome.GenericValue;
            version = outcome.PrivateVersion;
            identity = ReferenceEquals(host, outcome.ReturnedHost) && ReferenceEquals(host, outcome.GenericHost);
            return outcome.PrivateValue;
        });
        Console.WriteLine("SECOND static=" + staticCount + " privateCount=" + privateCount + " interface=" + iface + " delegate=" + delegated + " generic=" + generic + " helper=" + helper + " touch=" + touch + " version=" + version + " identity=" + identity);
        return ReferenceEquals(DeliverySession.LogicalHost, host) && second.Completed && second.Value == 101 && second.Failure.Length == 0
            && staticCount == 2 && privateCount == 2 && iface == 21 && delegated == 21 && generic == 310
            && helper == 310 && touch == 112 && version == "1.0.0.0" && identity;
    }

    static bool Reentry(TypedSession<IUpdateModule> session)
    {
        var nested = false;
        var originalHost = DeliverySession.LogicalHost;
        var outer = DeliverySession.InvokeLogical(_ =>
        {
            var inner = DeliverySession.InvokeLogical(candidate =>
            {
                nested = true;
                return candidate.Execute(new DeliveryHostObject(), false).PrivateValue;
            });
            return inner.Failure == "reentered" && ReferenceEquals(DeliverySession.LogicalHost, originalHost) ? 5 : -1;
        });
        return originalHost is not null && ReferenceEquals(DeliverySession.LogicalHost, originalHost) && outer.Completed && outer.Value == 5 && outer.Failure.Length == 0 && !nested && !session.IsClosed;
    }

    static bool CloseDuringCall(TypedSession<IUpdateModule> session, DeliveryHostObject host)
    {
        var nestedEntered = false;
        var staticCount = 0;
        var privateCount = 0;
        var iface = 0;
        var delegated = 0;
        var generic = 0;
        var privateValue = 0;
        var helper = 0;
        var touch = 0;
        var identity = false;
        var active = session.Invoke(candidate =>
        {
            DeliverySession.CloseLogical();
            var inner = session.Invoke(innerCandidate =>
            {
                nestedEntered = true;
                return innerCandidate.Execute(host, false).PrivateValue;
            });
            if (nestedEntered || inner.Failure != "closed")
                return -1;
            var outcome = candidate.Execute(host, false);
            staticCount = outcome.StaticCount;
            privateCount = outcome.PrivateCount;
            iface = outcome.InterfaceValue;
            delegated = outcome.DelegateValue;
            generic = outcome.GenericValue;
            privateValue = outcome.PrivateValue;
            helper = outcome.HelperValue;
            touch = outcome.TouchValue;
            identity = ReferenceEquals(host, outcome.ReturnedHost) && ReferenceEquals(host, outcome.GenericHost);
            return outcome.PrivateValue;
        });
        var laterEntered = false;
        var later = session.Invoke(candidate =>
        {
            laterEntered = true;
            return candidate.Execute(host, false).PrivateValue;
        });
        Console.WriteLine("DURING static=" + staticCount + " privateCount=" + privateCount + " interface=" + iface + " delegate=" + delegated + " generic=" + generic + " private=" + privateValue + " helper=" + helper + " touch=" + touch + " identity=" + identity);
        Console.WriteLine("NESTED entered=" + nestedEntered);
        Console.WriteLine("LATER entered=" + laterEntered + " failure=" + later.Failure);
        return active.Completed && active.Value == 101 && active.Failure.Length == 0
            && staticCount == 3 && privateCount == 3 && iface == 22 && delegated == 22 && generic == 310
            && privateValue == 101 && helper == 310 && touch == 112 && identity
            && !nestedEntered && !laterEntered && later.Failure == "closed" && session.IsClosed
            && DeliverySession.LogicalHost is null;
    }

    static ChildRun RunChild(World world, string mode)
    {
        var request = Path.Combine(world.Root, mode + ".request");
        File.WriteAllLines(request, new[]
        {
            "releases=" + world.Releases,
            "final=" + world.Final,
            "document=" + world.Document,
            "spki=" + world.Spki,
            "receipt=" + world.Receipt,
            "files=" + string.Join('|', world.Files.Select(file => file.Relative + "=" + file.Absolute)),
        });
        var start = new ProcessStartInfo(Environment.ProcessPath!)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = AppContext.BaseDirectory,
        };
        start.ArgumentList.Add("--integration-child");
        start.ArgumentList.Add(mode);
        start.ArgumentList.Add(request);
        using var child = Process.Start(start) ?? throw new InvalidOperationException("child");
        var stdoutTask = child.StandardOutput.ReadToEndAsync();
        var stderrTask = child.StandardError.ReadToEndAsync();
        Task.WaitAll(stdoutTask, stderrTask);
        child.WaitForExit();
        var stdout = stdoutTask.GetAwaiter().GetResult();
        var stderr = stderrTask.GetAwaiter().GetResult();
        Console.WriteLine(stdout);
        Console.Error.WriteLine("STDERR_BYTES " + stderr.Length);
        if (stderr.Length > 0)
            Console.Error.WriteLine(stderr);
        return new ChildRun(child.ExitCode == 0 && stdout.Contains("OK " + mode, StringComparison.Ordinal), stdout, stderr);
    }

    static World Prepare(string root, string name, ECDsa key, byte[] spki)
    {
        var worldRoot = Path.Combine(root, name);
        var releases = Path.Combine(worldRoot, "releases");
        var source = Path.Combine(releases, "src");
        Directory.CreateDirectory(source);
        Directory.CreateDirectory(Path.Combine(worldRoot, "state"));
        var built = Locate();
        File.Copy(built.Entry, Path.Combine(source, Entry));
        File.Copy(built.Private, Path.Combine(source, PrivateName));
        File.Copy(built.Helper, Path.Combine(source, HelperName));
        var signed = TrustedRelease.Sign(source, new TrustedReleaseIdentity("A", "net11.0", DeliverySession.Target.Architecture, "TrustedComposition.UpdateModule", "Execute", Entry), new[] { Entry, PrivateName, HelperName }, key);
        if (!signed.Succeeded || signed.Document is null)
            throw new InvalidOperationException("sign " + signed.Failure + " " + signed.Detail);
        var document = Path.Combine(worldRoot, "package.bin");
        var spkiPath = Path.Combine(worldRoot, "host.spki");
        File.WriteAllBytes(document, signed.Document);
        File.WriteAllBytes(spkiPath, spki);
        var files = new List<(string Relative, string Absolute)>
        {
            (Entry, Path.Combine(source, Entry)),
            (PrivateName, Path.Combine(source, PrivateName)),
            (HelperName, Path.Combine(source, HelperName)),
        };
        return new World(worldRoot, releases, Path.Combine(releases, "published"), document, spkiPath, Path.Combine(worldRoot, "state", "current.json"), files);
    }

    static (string Entry, string Private, string Helper) Locate()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var root = Path.Combine(dir.FullName, "eng", "trusted-composition");
            if (Directory.Exists(Path.Combine(root, "Update.A")))
            {
                var config = AppContext.BaseDirectory.Contains(Path.DirectorySeparatorChar + "Release" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ? "Release" : "Debug";
                return (
                    Path.Combine(root, "Update.A", "bin", config, "net11.0", Entry),
                    Path.Combine(root, "Private.A", "bin", config, "net11.0", PrivateName),
                    Path.Combine(root, "IlOnlyHelper", "bin", config, "net11.0", HelperName));
            }
            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("fixture");
    }

    static int Check(string name, bool passed)
    {
        Console.WriteLine((passed ? "PASS " : "FAIL ") + name);
        return passed ? 0 : 1;
    }

    static bool Same(string path, byte[] bytes) => File.ReadAllBytes(path).AsSpan().SequenceEqual(bytes);

    static bool SameSignedFile(string loaded, string finalDirectory, string fileName) =>
        SameFile(loaded, Path.Combine(finalDirectory, fileName)) && InsideDirectory(finalDirectory, loaded);

    static bool SameFile(string left, string right) =>
        TryCanonicalize(left, out var leftPath) && TryCanonicalize(right, out var rightPath) && SameCanonical(leftPath, rightPath);

    static bool InsideDirectory(string root, string candidate) =>
        TryCanonicalize(root, out var rootPath) && TryCanonicalize(candidate, out var candidatePath) && IsStrictChild(rootPath, candidatePath);

    const int MaxPathHops = 32;

    static bool SameCanonical(string left, string right)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return string.Equals(TrimPath(left), TrimPath(right), comparison);
    }

    static bool IsStrictChild(string root, string candidate)
    {
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var prefix = TrimPath(root) + Path.DirectorySeparatorChar;
        var full = TrimPath(candidate);
        return full.StartsWith(prefix, comparison);
    }

    static string TrimPath(string path)
    {
        var root = Path.GetPathRoot(path) ?? "";
        var trimmed = path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return trimmed.Length < root.Length ? root : trimmed;
    }

    static bool TryCanonicalize(string path, out string canonical)
    {
        canonical = "";
        if (string.IsNullOrWhiteSpace(path))
            return false;
        string full;
        try
        {
            full = Path.GetFullPath(path);
        }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or IOException)
        {
            return false;
        }

        var root = Path.GetPathRoot(full);
        if (string.IsNullOrEmpty(root))
            return false;
        var pending = Segments(full).ToList();
        var done = new List<string>();
        var hops = 0;
        var index = 0;
        while (index < pending.Count)
        {
            var next = Combine(root, done.Append(pending[index]));
            if (!TryInspect(next, out var reparse, out var missing))
                return false;
            if (missing)
            {
                done.AddRange(pending.Skip(index));
                break;
            }

            if (reparse)
            {
                if (++hops > MaxPathHops)
                    return false;
                FileSystemInfo? target;
                try
                {
                    target = File.ResolveLinkTarget(next, returnFinalTarget: false);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
                {
                    return false;
                }

                if (target is null)
                    return false;
                string targetFull;
                try
                {
                    targetFull = Path.GetFullPath(target.FullName);
                }
                catch (Exception ex) when (ex is ArgumentException or NotSupportedException or IOException)
                {
                    return false;
                }

                var targetRoot = Path.GetPathRoot(targetFull);
                if (string.IsNullOrEmpty(targetRoot))
                    return false;
                pending = Segments(targetFull).Concat(pending.Skip(index + 1)).ToList();
                root = targetRoot;
                done.Clear();
                index = 0;
                continue;
            }

            done.Add(pending[index]);
            index++;
        }

        canonical = Combine(root, done);
        return canonical.Length > 0;
    }

    static bool TryInspect(string path, out bool reparse, out bool missing)
    {
        reparse = false;
        missing = false;
        try
        {
            reparse = (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
            return true;
        }
        catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException)
        {
            missing = true;
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }

    static IEnumerable<string> Segments(string fullPath)
    {
        var root = Path.GetPathRoot(fullPath) ?? "";
        return fullPath.Length > root.Length
            ? fullPath[root.Length..].Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }, StringSplitOptions.RemoveEmptyEntries)
            : Array.Empty<string>();
    }

    static string Combine(string root, IEnumerable<string> segments)
    {
        var path = root;
        foreach (var segment in segments)
            path = Path.Combine(path, segment);
        return path;
    }


    sealed record World(string Root, string Releases, string Final, string Document, string Spki, string Receipt, List<(string Relative, string Absolute)> Files);

    readonly record struct ChildRun(bool Ok, string Stdout, string Stderr);
}