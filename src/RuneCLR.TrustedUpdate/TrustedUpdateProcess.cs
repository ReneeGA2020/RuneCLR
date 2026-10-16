using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;

namespace RuneCLR.TrustedUpdate;

/// <summary>
/// Selects one trusted update for a process lifetime.
/// A failed hash, missing file, or incompatible target is rejected before any
/// candidate assembly is loaded. The selected assembly then stays loaded: this
/// type has no unload operation and will not switch versions in-process.
/// Another instance in a later process can select the last known good version.
/// </summary>
public sealed class TrustedUpdateProcess
{
    const string ContextPrefix = "RuneCLR.TrustedUpdate:";
    static int ProcessGate;

    AssemblyLoadContext? residentContext;
    string? selectedVersionName;
    TrustedUpdateSession? openSession;
    Type? entryType;
    readonly Dictionary<long, string> openWork = [];
    readonly Queue<FinishedUpdateWork> finishedWork = [];
    readonly HashSet<long> finishedWorkIds = [];
    long nextWork;
    bool workOpen;

    public bool HasSelectedVersion => selectedVersionName is not null;

    public string? SelectedVersionName => selectedVersionName;



    public TrustedUpdateResidency? DescribeResidency()
    {
        if (selectedVersionName is null)
            return null;
        return new TrustedUpdateResidency(selectedVersionName, true, false, false);
    }


    public TrustedUpdateSession? OpenSession()
    {
        if (selectedVersionName is null)
            return null;
        if (openSession is { Closed: false })
            return openSession;
        openSession = new TrustedUpdateSession(selectedVersionName);
        return openSession;
    }

    public void CloseSession()
    {
        openSession?.Close();
        openSession = null;
        CancelUpdateWork();
    }

    public TrustedUpdateCallResult TryWork()
    {
        if (!SessionIsOpen())
            return new TrustedUpdateCallResult(TrustedUpdateFailure.SessionNotOpen, 0);
        var method = entryType!.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "Work"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(int)
                && ParametersMatch(item, new[] { typeof(ITrustedUpdateWork) }));
        if (method is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        var gate = new WorkGate(this);
        var requestedBefore = nextWork;
        workOpen = true;
        try
        {
            var returned = method.Invoke(null, new object[] { gate });
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, (int)returned!);
        }
        catch (Exception)
        {
            DropWorkRequestedAfter(requestedBefore);
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
        finally
        {
            gate.Close();
            workOpen = false;
        }
    }

    public TrustedUpdateWorkInfo[] CopyPendingWork()
    {
        if (!SessionIsOpen())
            throw new InvalidOperationException("The session is not open.");
        var copy = new TrustedUpdateWorkInfo[openWork.Count];
        var index = 0;
        foreach (var (id, name) in openWork)
            copy[index++] = new TrustedUpdateWorkInfo(id, name);
        return copy;
    }

    public void CompleteWork(long id, int value) => FinishUpdateWork(id, value, succeeded: true);

    public void FailWork(long id, int reason) => FinishUpdateWork(id, reason, succeeded: false);


    public TrustedUpdateCallResult TryTick(int value) => InvokeTick(value, null);

    // The callback is valid only until this call returns, and this object does not store it.
    public TrustedUpdateCallResult TryTick(int value, Func<int, int> hostCall)
    {
        ArgumentNullException.ThrowIfNull(hostCall);
        return InvokeTick(value, hostCall);
    }

    // The host object is valid only until this call returns, and this object does not store it.
    public TrustedUpdateCallResult TryTick(int value, ITrustedUpdateHost host)
    {
        ArgumentNullException.ThrowIfNull(host);
        return InvokeHostTick(value, host);
    }

    public TrustedUpdateIdentityResult TryEchoObject(object value)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (selectedVersionName is null || openSession is not { Closed: false } || entryType is null)
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.SessionNotOpen, false);
        var method = entryType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "EchoObject"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(object)
                && ParametersMatch(item, new[] { typeof(object) }));
        if (method is null)
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.ActivationFailed, false);
        try
        {
            var returned = method.Invoke(null, new object[] { value });
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.None, ReferenceEquals(returned, value));
        }
        catch (Exception)
        {
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.ActivationFailed, false);
        }
    }

    public TrustedUpdateCallResult TryListen()
    {
        if (!SessionIsOpen())
            return new TrustedUpdateCallResult(TrustedUpdateFailure.SessionNotOpen, 0);
        var method = entryType!.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "Listen"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(int)
                && ParametersMatch(item, new[] { typeof(ITrustedUpdateSignals) }));
        if (method is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        var gate = new SignalGate();
        try
        {
            var returned = method.Invoke(null, new object[] { gate });
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, (int)returned!);
        }
        catch (Exception)
        {
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
        finally
        {
            gate.Close();
        }
    }

    public TrustedUpdateIdentityResult TryEchoGenericObject(object value)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (value.GetType().IsValueType)
            throw new ArgumentException("Generic object echo requires a reference type.", nameof(value));
        var method = FindGenericEcho();
        if (method is null)
            return new TrustedUpdateIdentityResult(method is null && !SessionIsOpen() ? TrustedUpdateFailure.SessionNotOpen : TrustedUpdateFailure.ActivationFailed, false);
        try
        {
            var returned = method.MakeGenericMethod(value.GetType()).Invoke(null, new object[] { value });
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.None, ReferenceEquals(returned, value));
        }
        catch (Exception)
        {
            return new TrustedUpdateIdentityResult(TrustedUpdateFailure.ActivationFailed, false);
        }
    }

    public TrustedUpdateCallResult TryEchoGenericInt(int value)
    {
        var method = FindGenericEcho();
        if (method is null)
            return new TrustedUpdateCallResult(SessionIsOpen() ? TrustedUpdateFailure.ActivationFailed : TrustedUpdateFailure.SessionNotOpen, 0);
        try
        {
            var returned = method.MakeGenericMethod(typeof(int)).Invoke(null, new object[] { value });
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, (int)returned!);
        }
        catch (Exception)
        {
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    bool SessionIsOpen() => selectedVersionName is not null && openSession is { Closed: false } && entryType is not null;

    MethodInfo? FindGenericEcho()
    {
        if (!SessionIsOpen() || entryType is null)
            return null;
        foreach (var item in entryType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly))
        {
            if (IsTypeArgumentEcho(item))
                return item;
        }
        return null;
    }

    static bool IsTypeArgumentEcho(MethodInfo item)
    {
        try
        {
            if (!item.IsGenericMethodDefinition || item.Name != "EchoGeneric")
                return false;
            var arguments = item.GetGenericArguments();
            if (arguments.Length != 1)
                return false;
            var parameters = item.GetParameters();
            return parameters.Length == 1
                && item.ReturnType == arguments[0]
                && parameters[0].ParameterType == arguments[0];
        }
        catch (Exception)
        {
            return false;
        }
    }

    public TrustedUpdateCallResult TryReleaseHeldObjects()
    {
        if (selectedVersionName is null || openSession is not { Closed: false } || entryType is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.SessionNotOpen, 0);
        var method = entryType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "ReleaseHeldObjects"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(void)
                && item.GetParameters().Length == 0);
        if (method is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        try
        {
            method.Invoke(null, null);
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, 0);
        }
        catch (Exception)
        {
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
    }

    TrustedUpdateCallResult InvokeTick(int value, Func<int, int>? hostCall)
    {
        if (selectedVersionName is null || openSession is not { Closed: false } || entryType is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.SessionNotOpen, 0);
        var parameters = hostCall is null
            ? new[] { typeof(int) }
            : new[] { typeof(int), typeof(Func<int, int>) };
        var method = entryType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "Tick"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(int)
                && ParametersMatch(item, parameters));
        if (method is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        HostCallGate? gate = null;
        if (hostCall is not null)
            gate = new HostCallGate(hostCall);
        try
        {
            var args = gate is null ? new object[] { value } : new object[] { value, new Func<int, int>(gate.Invoke) };
            var result = method.Invoke(null, args);
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, (int)result!);
        }
        catch (Exception)
        {
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
        finally
        {
            gate?.Close();
        }
    }

    TrustedUpdateCallResult InvokeHostTick(int value, ITrustedUpdateHost host)
    {
        if (selectedVersionName is null || openSession is not { Closed: false } || entryType is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.SessionNotOpen, 0);
        var parameters = new[] { typeof(int), typeof(ITrustedUpdateHost) };
        var method = entryType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .FirstOrDefault(item => item.Name == "Tick"
                && !item.IsGenericMethodDefinition
                && item.ReturnType == typeof(int)
                && ParametersMatch(item, parameters));
        if (method is null)
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        var gate = new HostApiGate(host);
        try
        {
            var result = method.Invoke(null, new object[] { value, gate });
            return new TrustedUpdateCallResult(TrustedUpdateFailure.None, (int)result!);
        }
        catch (Exception)
        {
            return new TrustedUpdateCallResult(TrustedUpdateFailure.ActivationFailed, 0);
        }
        finally
        {
            gate.Close();
        }
    }

    static bool ParametersMatch(MethodInfo method, Type[] expected)
    {
        var actual = method.GetParameters();
        if (actual.Length != expected.Length)
            return false;
        for (var index = 0; index < expected.Length; index++)
        {
            if (actual[index].ParameterType != expected[index])
                return false;
        }
        return true;
    }

    public TrustedUpdateResult TryPlanCandidate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        TrustedUpdateApproval? approval) =>
        Plan(candidate, hostTarget, approval, null);

    public TrustedUpdateResult TryPlanCandidate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        TrustedUpdateApproval? approval,
        string contentRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(contentRoot);
        return Plan(candidate, hostTarget, approval, contentRoot);
    }

    TrustedUpdateResult Plan(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        TrustedUpdateApproval? approval,
        string? contentRoot)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        if (contentRoot is not null)
        {
            if (ExistsOutside(contentRoot, candidate.AssemblyPath))
                return Reject(TrustedUpdateFailure.OutsideContentRoot);
            if (candidate.AdditionalContent is not null)
            {
                foreach (var item in candidate.AdditionalContent)
                {
                    if (item is not null && ExistsOutside(contentRoot, item.Path))
                        return Reject(TrustedUpdateFailure.OutsideContentRoot);
                }
            }
        }
        if (IsLocked)
            return Reject(TrustedUpdateFailure.ProcessSelectionLocked);
        var invalid = Validate(candidate, hostTarget);
        if (invalid != TrustedUpdateFailure.None)
            return Reject(invalid);
        var additional = ValidateAdditional(candidate.AdditionalContent);
        if (additional != TrustedUpdateFailure.None)
            return Reject(additional);
        if (!IsApproved(candidate, approval))
            return Reject(TrustedUpdateFailure.NotApproved);
        return new TrustedUpdateResult(TrustedUpdateFailure.None, candidate.VersionName);
    }

    public TrustedUpdateResult TryStorePlannedCandidate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        TrustedUpdateApproval? approval,
        string lastKnownGoodPath,
        string contentRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        var planned = TryPlanCandidate(candidate, hostTarget, approval, contentRoot);
        if (!planned.Succeeded)
            return planned;
        WriteLastKnownGood(lastKnownGoodPath, candidate);
        return planned;
    }

    public TrustedUpdateHostStart TryStartHostLoaded(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        string? lastKnownGoodPath,
        TrustedUpdateApproval? approval,
        string contentRoot,
        TrustedUpdateApproval? fallbackApproval,
        string? fallbackContentRoot,
        string? requiredVersion,
        TrustedUpdateActivator activate)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        ArgumentNullException.ThrowIfNull(activate);
        ArgumentException.ThrowIfNullOrWhiteSpace(contentRoot);
        if (IsLocked)
            return new TrustedUpdateHostStart(TrustedUpdateFailure.ProcessSelectionLocked, TrustedUpdateFailure.None, null, TrustedUpdateStartSource.None, 0);
        var planned = TryPlanCandidate(candidate, hostTarget, approval, contentRoot);
        if (planned.Succeeded)
        {
            if (requiredVersion is not null
                && !string.Equals(planned.SelectedVersionName, requiredVersion, StringComparison.Ordinal))
                return new TrustedUpdateHostStart(TrustedUpdateFailure.InvalidCandidate, TrustedUpdateFailure.None, null, TrustedUpdateStartSource.None, 0);
            var activation = activate(candidate, TrustedUpdateStartSource.Candidate, TrustedUpdateFailure.None);
            if (!activation.Succeeded)
                return new TrustedUpdateHostStart(activation.Failure, TrustedUpdateFailure.None, null, TrustedUpdateStartSource.None, 0);
            if (!string.IsNullOrWhiteSpace(lastKnownGoodPath))
                WriteLastKnownGood(lastKnownGoodPath, candidate);
            Interlocked.Exchange(ref ProcessGate, 1);
            return new TrustedUpdateHostStart(TrustedUpdateFailure.None, TrustedUpdateFailure.None, candidate.VersionName, TrustedUpdateStartSource.Candidate, activation.Value);
        }

        if (string.IsNullOrWhiteSpace(lastKnownGoodPath) || fallbackApproval is null || string.IsNullOrWhiteSpace(fallbackContentRoot))
            return new TrustedUpdateHostStart(planned.Failure, planned.Failure, null, TrustedUpdateStartSource.None, 0);
        var restored = TryPlanLastKnownGood(hostTarget, lastKnownGoodPath, fallbackApproval, fallbackContentRoot, out var stored);
        if (!restored.Succeeded || stored is null)
            return new TrustedUpdateHostStart(planned.Failure, planned.Failure, null, TrustedUpdateStartSource.None, 0);
        var fallbackActivation = activate(stored, TrustedUpdateStartSource.LastKnownGood, planned.Failure);
        if (!fallbackActivation.Succeeded)
            return new TrustedUpdateHostStart(fallbackActivation.Failure, planned.Failure, null, TrustedUpdateStartSource.None, 0);
        Interlocked.Exchange(ref ProcessGate, 1);
        return new TrustedUpdateHostStart(TrustedUpdateFailure.None, planned.Failure, stored.VersionName, TrustedUpdateStartSource.LastKnownGood, fallbackActivation.Value);
    }

    public TrustedUpdateResult TryPlanLastKnownGood(
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval,
        string contentRoot,
        out TrustedUpdateCandidate? candidate)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(contentRoot);
        candidate = null;
        if (!TryReadStoredCandidate(lastKnownGoodPath, out var stored, out var failure))
            return Reject(failure);
        if (File.Exists(stored.AssemblyPath) && !IsUnderContentRoot(contentRoot, stored.AssemblyPath))
            return Reject(TrustedUpdateFailure.OutsideContentRoot);
        var planned = TryPlanCandidate(stored, hostTarget, approval, contentRoot);
        if (!planned.Succeeded)
            return planned;
        candidate = stored;
        return planned;
    }

    public TrustedUpdateResult TrySelectCandidate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval,
        string contentRoot)
    {
        var planned = TryPlanCandidate(candidate, hostTarget, approval, contentRoot);
        if (!planned.Succeeded)
            return planned;
        return TrySelectCandidate(candidate, hostTarget, lastKnownGoodPath, approval);
    }

    public TrustedUpdateResult TrySelectCandidate(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        var planned = TryPlanCandidate(candidate, hostTarget, approval);
        if (!planned.Succeeded)
            return planned;

        var context = new AssemblyLoadContext(ContextPrefix + candidate.VersionName, isCollectible: false);
        Assembly assembly;
        try
        {
            assembly = context.LoadFromAssemblyPath(Path.GetFullPath(candidate.AssemblyPath));
        }
        catch (Exception)
        {
            return Reject(TrustedUpdateFailure.ActivationFailed);
        }

        Type? type = null;
        try
        {
            type = assembly.GetType(candidate.EntryTypeName, throwOnError: false, ignoreCase: false);
            if (type is null || type.ContainsGenericParameters)
                return Reject(TrustedUpdateFailure.ActivationFailed);
            var method = type.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
                .FirstOrDefault(item => item.Name == candidate.EntryMethodName
                    && !item.IsGenericMethodDefinition
                    && item.ReturnType == typeof(void)
                    && item.GetParameters().Length == 0);
            if (method is null)
                return Reject(TrustedUpdateFailure.ActivationFailed);
            method.Invoke(null, null);
        }
        catch (Exception)
        {
            return Reject(TrustedUpdateFailure.ActivationFailed);
        }

        residentContext = context;
        entryType = type;
        Interlocked.Exchange(ref ProcessGate, 1);
        WriteLastKnownGood(lastKnownGoodPath, candidate);
        selectedVersionName = candidate.VersionName;
        return new TrustedUpdateResult(TrustedUpdateFailure.None, candidate.VersionName);
    }

    public TrustedUpdateStartup TryStart(
        TrustedUpdateCandidate candidate,
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval,
        string? contentRoot,
        TrustedUpdateApproval? fallbackApproval = null,
        string? fallbackContentRoot = null)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        var planned = string.IsNullOrWhiteSpace(contentRoot)
            ? TryPlanCandidate(candidate, hostTarget, approval)
            : TryPlanCandidate(candidate, hostTarget, approval, contentRoot);
        if (planned.Succeeded)
        {
            var selected = string.IsNullOrWhiteSpace(contentRoot)
                ? TrySelectCandidate(candidate, hostTarget, lastKnownGoodPath, approval)
                : TrySelectCandidate(candidate, hostTarget, lastKnownGoodPath, approval, contentRoot);
            return new TrustedUpdateStartup(
                selected.Failure,
                TrustedUpdateFailure.None,
                selected.SelectedVersionName,
                selected.Succeeded ? TrustedUpdateStartSource.Candidate : TrustedUpdateStartSource.None);
        }

        var restoreApproval = fallbackApproval ?? approval;
        var restoreRoot = fallbackContentRoot ?? contentRoot;
        var restored = string.IsNullOrWhiteSpace(restoreRoot)
            ? TrySelectLastKnownGood(hostTarget, lastKnownGoodPath, restoreApproval)
            : TrySelectLastKnownGood(hostTarget, lastKnownGoodPath, restoreApproval, restoreRoot);
        if (!restored.Succeeded)
            return new TrustedUpdateStartup(restored.Failure, planned.Failure, null, TrustedUpdateStartSource.None);
        return new TrustedUpdateStartup(
            TrustedUpdateFailure.None,
            planned.Failure,
            restored.SelectedVersionName,
            TrustedUpdateStartSource.LastKnownGood);
    }

    public TrustedUpdateResult TrySelectLastKnownGood(
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        if (IsLocked)
            return Reject(TrustedUpdateFailure.ProcessSelectionLocked);
        if (!TryReadStoredCandidate(lastKnownGoodPath, out var candidate, out var failure))
            return Reject(failure);
        return TrySelectCandidate(candidate, hostTarget, lastKnownGoodPath, approval);
    }

    public TrustedUpdateResult TrySelectLastKnownGood(
        TrustedUpdateTarget hostTarget,
        string lastKnownGoodPath,
        TrustedUpdateApproval? approval,
        string contentRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(lastKnownGoodPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(contentRoot);
        if (IsLocked)
            return Reject(TrustedUpdateFailure.ProcessSelectionLocked);
        if (!TryReadStoredCandidate(lastKnownGoodPath, out var candidate, out var failure))
            return Reject(failure);
        if (File.Exists(candidate.AssemblyPath) && !IsUnderContentRoot(contentRoot, candidate.AssemblyPath))
            return Reject(TrustedUpdateFailure.OutsideContentRoot);
        return TrySelectCandidate(candidate, hostTarget, lastKnownGoodPath, approval, contentRoot);
    }

    static bool TryReadStoredCandidate(
        string lastKnownGoodPath,
        out TrustedUpdateCandidate candidate,
        out TrustedUpdateFailure failure)
    {
        candidate = new TrustedUpdateCandidate("", "", "", "", "", new TrustedUpdateTarget("", ""));
        if (!File.Exists(lastKnownGoodPath))
        {
            failure = TrustedUpdateFailure.NoLastKnownGood;
            return false;
        }

        StoredVersion? stored;
        try
        {
            stored = JsonSerializer.Deserialize<StoredVersion>(File.ReadAllText(lastKnownGoodPath));
        }
        catch (Exception)
        {
            failure = TrustedUpdateFailure.LastKnownGoodUnusable;
            return false;
        }
        var versionName = stored?.VersionName;
        var contentSha256 = stored?.ContentSha256;
        var assemblyPath = stored?.AssemblyPath;
        var entryTypeName = stored?.EntryTypeName;
        var entryMethodName = stored?.EntryMethodName;
        var runtime = stored?.Runtime;
        var architecture = stored?.Architecture;
        if (stored is null
            || string.IsNullOrWhiteSpace(versionName)
            || string.IsNullOrWhiteSpace(contentSha256)
            || string.IsNullOrWhiteSpace(assemblyPath)
            || string.IsNullOrWhiteSpace(entryTypeName)
            || string.IsNullOrWhiteSpace(entryMethodName)
            || string.IsNullOrWhiteSpace(runtime)
            || string.IsNullOrWhiteSpace(architecture))
        {
            failure = TrustedUpdateFailure.LastKnownGoodUnusable;
            return false;
        }

        IReadOnlyList<TrustedUpdateContentFile>? additional = null;
        if (stored.AdditionalContent is not null)
        {
            var files = new List<TrustedUpdateContentFile>();
            foreach (var item in stored.AdditionalContent)
            {
                if (item is null
                    || string.IsNullOrWhiteSpace(item.Path)
                    || string.IsNullOrWhiteSpace(item.ContentSha256))
                {
                    failure = TrustedUpdateFailure.LastKnownGoodUnusable;
                    return false;
                }
                files.Add(new TrustedUpdateContentFile(item.Path, item.ContentSha256));
            }
            additional = files;
        }

        candidate = new TrustedUpdateCandidate(
            versionName,
            contentSha256,
            assemblyPath,
            entryTypeName,
            entryMethodName,
            new TrustedUpdateTarget(runtime, architecture),
            additional);
        failure = TrustedUpdateFailure.None;
        return true;
    }

    bool IsLocked => residentContext is not null || selectedVersionName is not null || Volatile.Read(ref ProcessGate) != 0;

    static TrustedUpdateFailure Validate(TrustedUpdateCandidate candidate, TrustedUpdateTarget hostTarget)
    {
        if (string.IsNullOrWhiteSpace(candidate.VersionName)
            || string.IsNullOrWhiteSpace(candidate.ContentSha256)
            || string.IsNullOrWhiteSpace(candidate.EntryTypeName)
            || string.IsNullOrWhiteSpace(candidate.EntryMethodName)
            || string.IsNullOrWhiteSpace(hostTarget.Runtime)
            || string.IsNullOrWhiteSpace(hostTarget.Architecture)
            || string.IsNullOrWhiteSpace(candidate.Target.Runtime)
            || string.IsNullOrWhiteSpace(candidate.Target.Architecture))
            return TrustedUpdateFailure.InvalidCandidate;
        if (string.IsNullOrWhiteSpace(candidate.AssemblyPath) || !File.Exists(candidate.AssemblyPath))
            return TrustedUpdateFailure.MissingContent;
        if (!string.Equals(candidate.Target.Runtime, hostTarget.Runtime, StringComparison.Ordinal)
            || !string.Equals(candidate.Target.Architecture, hostTarget.Architecture, StringComparison.Ordinal))
            return TrustedUpdateFailure.IncompatibleTarget;
        var actual = HashFile(candidate.AssemblyPath);
        if (!string.Equals(actual, candidate.ContentSha256, StringComparison.OrdinalIgnoreCase))
            return TrustedUpdateFailure.ContentHashMismatch;
        return TrustedUpdateFailure.None;
    }

    static bool IsUnderContentRoot(string contentRoot, string assemblyPath)
    {
        var root = Path.GetFullPath(contentRoot);
        var full = Path.GetFullPath(assemblyPath);
        var relative = Path.GetRelativePath(root, full);
        return relative != "."
            && relative != ".."
            && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            && !relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal)
            && !Path.IsPathRooted(relative);
    }

    static bool ExistsOutside(string contentRoot, string? path) =>
        !string.IsNullOrWhiteSpace(path)
        && File.Exists(path)
        && !IsUnderContentRoot(contentRoot, path);

    static TrustedUpdateFailure ValidateAdditional(IReadOnlyList<TrustedUpdateContentFile>? files)
    {
        if (files is null)
            return TrustedUpdateFailure.None;
        foreach (var item in files)
        {
            if (item is null
                || string.IsNullOrWhiteSpace(item.Path)
                || string.IsNullOrWhiteSpace(item.ContentSha256))
                return TrustedUpdateFailure.InvalidCandidate;
            if (!File.Exists(item.Path))
                return TrustedUpdateFailure.MissingContent;
            var actual = HashFile(item.Path);
            if (!string.Equals(actual, item.ContentSha256, StringComparison.OrdinalIgnoreCase))
                return TrustedUpdateFailure.ContentHashMismatch;
        }
        return TrustedUpdateFailure.None;
    }

    static bool IsApproved(TrustedUpdateCandidate candidate, TrustedUpdateApproval? approval) =>
        approval is not null
        && !string.IsNullOrWhiteSpace(approval.ApprovalId)
        && !string.IsNullOrWhiteSpace(approval.VersionName)
        && !string.IsNullOrWhiteSpace(approval.ContentSha256)
        && string.Equals(approval.VersionName, candidate.VersionName, StringComparison.Ordinal)
        && string.Equals(approval.ContentSha256, candidate.ContentSha256, StringComparison.OrdinalIgnoreCase);

    static string HashFile(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    static void WriteLastKnownGood(string path, TrustedUpdateCandidate candidate)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory))
            Directory.CreateDirectory(directory);
        List<StoredContent>? additional = null;
        if (candidate.AdditionalContent is not null)
        {
            additional = new List<StoredContent>();
            foreach (var item in candidate.AdditionalContent)
            {
                additional.Add(new StoredContent
                {
                    Path = Path.GetFullPath(item.Path),
                    ContentSha256 = item.ContentSha256.ToLowerInvariant(),
                });
            }
        }
        var stored = new StoredVersion
        {
            VersionName = candidate.VersionName,
            ContentSha256 = candidate.ContentSha256.ToLowerInvariant(),
            AssemblyPath = Path.GetFullPath(candidate.AssemblyPath),
            EntryTypeName = candidate.EntryTypeName,
            EntryMethodName = candidate.EntryMethodName,
            Runtime = candidate.Target.Runtime,
            Architecture = candidate.Target.Architecture,
            AdditionalContent = additional,
        };
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(stored));
        File.Move(temporary, path, overwrite: true);
    }

    static TrustedUpdateResult Reject(TrustedUpdateFailure failure) => new(failure, null);

    sealed class HostCallGate
    {
        readonly Func<int, int> hostCall;
        bool accepting;

        public HostCallGate(Func<int, int> hostCall)
        {
            this.hostCall = hostCall;
            accepting = true;
        }

        public void Close() => accepting = false;

        public int Invoke(int value)
        {
            if (!accepting)
                throw new InvalidOperationException("host callback closed");
            return hostCall(value);
        }
    }

    long RequestUpdateWork(string name)
    {
        if (!workOpen)
            throw new InvalidOperationException("The update work is closed.");
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        var id = ++nextWork;
        openWork.Add(id, name);
        return id;
    }

    bool TryTakeUpdateWork(out long id, out int value, out bool succeeded)
    {
        if (!workOpen)
            throw new InvalidOperationException("The update work is closed.");
        if (finishedWork.Count == 0)
        {
            id = 0;
            value = 0;
            succeeded = false;
            return false;
        }

        var finished = finishedWork.Dequeue();
        finishedWorkIds.Remove(finished.Id);
        id = finished.Id;
        value = finished.Value;
        succeeded = finished.Succeeded;
        return true;
    }

    void FinishUpdateWork(long id, int value, bool succeeded)
    {
        if (!SessionIsOpen())
            throw new InvalidOperationException("The session is not open.");
        if (finishedWorkIds.Contains(id))
            throw new InvalidOperationException("The work is already complete.");
        if (!openWork.Remove(id))
            throw new ArgumentException("The work does not belong to this session.", nameof(id));
        finishedWorkIds.Add(id);
        finishedWork.Enqueue(new FinishedUpdateWork(id, value, succeeded));
    }

    void CancelUpdateWork()
    {
        openWork.Clear();
        finishedWork.Clear();
        finishedWorkIds.Clear();
    }

    void DropWorkRequestedAfter(long before)
    {
        var added = new long[openWork.Count];
        var count = 0;
        foreach (var id in openWork.Keys)
        {
            if (id > before)
                added[count++] = id;
        }

        for (var index = 0; index < count; index++)
            openWork.Remove(added[index]);
    }

    sealed class WorkGate : ITrustedUpdateWork
    {
        readonly TrustedUpdateProcess owner;
        bool accepting = true;

        public WorkGate(TrustedUpdateProcess owner) => this.owner = owner;

        public void Close() => accepting = false;

        public long Request(string name)
        {
            if (!accepting)
                throw new InvalidOperationException("The update work is closed.");
            return owner.RequestUpdateWork(name);
        }

        public bool TryTake(out long id, out int value, out bool succeeded)
        {
            if (!accepting)
                throw new InvalidOperationException("The update work is closed.");
            return owner.TryTakeUpdateWork(out id, out value, out succeeded);
        }
    }

    readonly record struct FinishedUpdateWork(long Id, int Value, bool Succeeded);

    sealed class SignalGate : ITrustedUpdateSignals
    {
        bool accepting = true;
        Action<int>? signal;

        public event Action<int>? Signal
        {
            add
            {
                if (!accepting)
                    throw new InvalidOperationException("host callback closed");
                signal += value;
            }
            remove
            {
                if (!accepting)
                    throw new InvalidOperationException("host callback closed");
                signal -= value;
            }
        }

        public void Raise(int value)
        {
            if (!accepting)
                throw new InvalidOperationException("host callback closed");
            signal?.Invoke(value);
        }

        public void Close()
        {
            accepting = false;
            signal = null;
        }
    }

    sealed class HostApiGate : ITrustedUpdateHost
    {
        readonly ITrustedUpdateHost host;
        bool accepting;

        public HostApiGate(ITrustedUpdateHost host)
        {
            this.host = host;
            accepting = true;
        }

        public void Close() => accepting = false;

        public int Echo(int value)
        {
            if (!accepting)
                throw new InvalidOperationException("host callback closed");
            return host.Echo(value);
        }
    }

    sealed class StoredVersion
    {
        public string? VersionName { get; set; }
        public string? ContentSha256 { get; set; }
        public string? AssemblyPath { get; set; }
        public string? EntryTypeName { get; set; }
        public string? EntryMethodName { get; set; }
        public string? Runtime { get; set; }
        public string? Architecture { get; set; }
        public List<StoredContent>? AdditionalContent { get; set; }
    }

    sealed class StoredContent
    {
        public string? Path { get; set; }
        public string? ContentSha256 { get; set; }
    }
}
