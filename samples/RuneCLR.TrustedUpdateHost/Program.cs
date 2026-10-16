using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using RuneCLR.TrustedUpdate;

var timingStartup = System.Diagnostics.Stopwatch.StartNew();
const string HostRuntime = "net11.0";
var hostTarget = new TrustedUpdateTarget(HostRuntime, HostArchitecture());

if (args is ["--self-test"])
    return SelfTest();
if (args is ["--timings"])
    return TimeOneTick(hostTarget, timingStartup);
if (args is ["--host-loaded", var hostMode, var hostDirectory, var hostStore])
    return HostLoaded(hostMode, hostDirectory, hostStore, hostTarget);
if (args is ["--tick", var tickDirectory, var tickStore])
    return TickSample(tickDirectory, tickStore, hostTarget);
if (args is ["--work", var workDirectory, var workStore])
    return WorkSample(workDirectory, workStore, hostTarget);
if (args is ["--work-order", var workOrderDirectory, var workOrderStore])
    return WorkOrderSample(workOrderDirectory, workOrderStore, hostTarget);
if (args is ["--null-callback", var nullCallbackDirectory, var nullCallbackStore])
    return NullCallbackSample(nullCallbackDirectory, nullCallbackStore, hostTarget);
if (args is ["--signal", var signalDirectory, var signalStore])
    return SignalSample(signalDirectory, signalStore, hostTarget);
if (args is ["--generic", var genericDirectory, var genericStore])
    return GenericSample(genericDirectory, genericStore, hostTarget);

if (args is ["--start", var startDirectory, var startStore])
    return Start(startDirectory, startStore, hostTarget);
if (args is ["--restore", var rootedStore, var restoreRoot])
    return Restore(rootedStore, hostTarget, restoreRoot);
if (args is ["--restore", var restoreStore])
    return Restore(restoreStore, hostTarget);
if (args is not [var candidateDirectory, var lastKnownGood])
{
    Console.WriteLine("REJECTED InvalidCandidate");
    return 1;
}

return Select(candidateDirectory, lastKnownGood, hostTarget);


static int Restore(string lastKnownGood, TrustedUpdateTarget hostTarget, string? contentRoot = null)
{
    try
    {
        TrustedUpdateApproval? approval = null;
        using (var document = JsonDocument.Parse(File.ReadAllText(lastKnownGood)))
        {
            var rootElement = document.RootElement;
            string? assemblyPath = null;
            if (rootElement.TryGetProperty("AssemblyPath", out var pathProperty))
                assemblyPath = pathProperty.GetString();
            else if (rootElement.TryGetProperty("assemblyPath", out pathProperty))
                assemblyPath = pathProperty.GetString();
            var directory = string.IsNullOrWhiteSpace(assemblyPath) ? null : Path.GetDirectoryName(assemblyPath);
            if (!string.IsNullOrWhiteSpace(directory))
                TryReadApproval(directory, out approval);
        }
        var result = string.IsNullOrWhiteSpace(contentRoot)
            ? new TrustedUpdateProcess().TrySelectLastKnownGood(hostTarget, lastKnownGood, approval)
            : new TrustedUpdateProcess().TrySelectLastKnownGood(hostTarget, lastKnownGood, approval, contentRoot);
        if (result.Succeeded)
        {
            Console.WriteLine("SELECTED " + result.SelectedVersionName);
            return 0;
        }
        Console.WriteLine("REJECTED " + result.Failure);
        return 1;
    }
    catch (Exception)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
}

static int Start(string candidateDirectory, string lastKnownGood, TrustedUpdateTarget hostTarget)
{
    try
    {
        if (!TryReadCandidate(candidateDirectory, out var candidate))
        {
            Console.WriteLine("REJECTED InvalidCandidate");
            return 1;
        }

        if (!TryReadApproval(candidateDirectory, out var approval))
            approval = null;
        TrustedUpdateApproval? fallbackApproval = null;
        string? fallbackRoot = null;
        if (File.Exists(lastKnownGood))
        {
            using var document = JsonDocument.Parse(File.ReadAllText(lastKnownGood));
            var rootElement = document.RootElement;
            string? assemblyPath = null;
            if (rootElement.TryGetProperty("AssemblyPath", out var pathProperty))
                assemblyPath = pathProperty.GetString();
            else if (rootElement.TryGetProperty("assemblyPath", out pathProperty))
                assemblyPath = pathProperty.GetString();
            var directory = string.IsNullOrWhiteSpace(assemblyPath) ? null : Path.GetDirectoryName(assemblyPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                fallbackRoot = directory;
                if (!TryReadApproval(directory, out fallbackApproval))
                    fallbackApproval = null;
            }
        }

        var result = new TrustedUpdateProcess().TryStart(
            candidate, hostTarget, lastKnownGood, approval, candidateDirectory, fallbackApproval, fallbackRoot);
        if (!result.Succeeded)
        {
            Console.WriteLine("REJECTED " + result.Failure);
            return 1;
        }

        if (result.Source == TrustedUpdateStartSource.LastKnownGood)
            Console.WriteLine("FALLBACK " + result.SelectedVersionName + " " + result.CandidateFailure);
        else
            Console.WriteLine("SELECTED " + result.SelectedVersionName);
        return 0;
    }
    catch (Exception)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
}

static int Select(string candidateDirectory, string lastKnownGood, TrustedUpdateTarget hostTarget)
{
    try
    {
        if (!TryReadCandidate(candidateDirectory, out var candidate))
        {
            Console.WriteLine("REJECTED InvalidCandidate");
            return 1;
        }

        if (!TryReadApproval(candidateDirectory, out var approval))
            approval = null;
        var process = new TrustedUpdateProcess();
        var planned = process.TryPlanCandidate(candidate, hostTarget, approval, candidateDirectory);
        if (!planned.Succeeded)
        {
            Console.WriteLine("REJECTED " + planned.Failure);
            return 1;
        }

        var result = process.TrySelectCandidate(candidate, hostTarget, lastKnownGood, approval, candidateDirectory);
        if (result.Succeeded)
        {
            Console.WriteLine("SELECTED " + result.SelectedVersionName);
            return 0;
        }

        Console.WriteLine("REJECTED " + result.Failure);
        return 1;
    }
    catch (Exception)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
}


static bool TryReadApproval(string directory, out TrustedUpdateApproval? approval)
{
    approval = null;
    var path = Path.Combine(directory, "trusted-update-approval.json");
    if (!File.Exists(path))
        return false;
    HostApprovalFile? file;
    try
    {
        file = JsonSerializer.Deserialize<HostApprovalFile>(File.ReadAllText(path));
    }
    catch (JsonException)
    {
        return false;
    }
    if (file is null
        || string.IsNullOrWhiteSpace(file.VersionName)
        || string.IsNullOrWhiteSpace(file.ContentSha256)
        || string.IsNullOrWhiteSpace(file.ApprovalId))
        return false;
    approval = new TrustedUpdateApproval(file.VersionName, file.ContentSha256, file.ApprovalId);
    return true;
}

static bool TryReadCandidate(string directory, out TrustedUpdateCandidate candidate)
{
    candidate = new TrustedUpdateCandidate("", "", "", "", "", new TrustedUpdateTarget("", ""));
    if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
        return false;
    var manifestPath = Path.Combine(directory, "trusted-update.json");
    if (!File.Exists(manifestPath))
        return false;

    HostCandidateFile? file;
    try
    {
        file = JsonSerializer.Deserialize<HostCandidateFile>(File.ReadAllText(manifestPath));
    }
    catch (JsonException)
    {
        return false;
    }

    if (file is null
        || string.IsNullOrWhiteSpace(file.VersionName)
        || string.IsNullOrWhiteSpace(file.ContentSha256)
        || string.IsNullOrWhiteSpace(file.AssemblyFile)
        || string.IsNullOrWhiteSpace(file.EntryTypeName)
        || string.IsNullOrWhiteSpace(file.EntryMethodName)
        || string.IsNullOrWhiteSpace(file.Runtime)
        || string.IsNullOrWhiteSpace(file.Architecture)
        || file.AssemblyFile.IndexOfAny(['/', '\\']) >= 0
        || !TryReadAdditional(directory, file.AdditionalFiles, out var additional))
        return false;

    candidate = new TrustedUpdateCandidate(
        file.VersionName,
        file.ContentSha256,
        Path.Combine(directory, file.AssemblyFile),
        file.EntryTypeName,
        file.EntryMethodName,
        new TrustedUpdateTarget(file.Runtime, file.Architecture),
        additional);
    return true;
}

static bool TryReadAdditional(string directory, IReadOnlyList<HostContentFile>? files, out IReadOnlyList<TrustedUpdateContentFile>? additional)
{
    additional = null;
    if (files is null)
        return true;
    var list = new List<TrustedUpdateContentFile>();
    foreach (var item in files)
    {
        if (item is null
            || string.IsNullOrWhiteSpace(item.FileName)
            || string.IsNullOrWhiteSpace(item.ContentSha256)
            || item.FileName is "." or ".."
            || item.FileName.IndexOfAny(['/', '\\']) >= 0)
            return false;
        list.Add(new TrustedUpdateContentFile(Path.Combine(directory, item.FileName), item.ContentSha256));
    }
    additional = list;
    return true;
}

static int SelfTest()
{
    var root = Path.Combine(Path.GetTempPath(), "runeclr-trusted-update-host-" + Guid.NewGuid().ToString("n"));
    try
    {
        var goodDirectory = Path.Combine(root, "good");
        var badDirectory = Path.Combine(root, "bad");
        Directory.CreateDirectory(goodDirectory);
        Directory.CreateDirectory(badDirectory);
        const string assemblyFile = "TrustedUpdate.SampleCandidate.dll";
        var goodAssembly = Path.Combine(goodDirectory, assemblyFile);
        WriteCandidateAssembly(goodAssembly);
        File.Copy(goodAssembly, Path.Combine(badDirectory, assemblyFile));
        var goodHash = Hash(goodAssembly);
        WriteManifest(goodDirectory, "good", goodHash);
        WriteApproval(goodDirectory, "good", goodHash);
        WriteManifest(badDirectory, "bad", new string('b', 64));
        var unapprovedDirectory = Path.Combine(root, "unapproved");
        Directory.CreateDirectory(unapprovedDirectory);
        File.Copy(goodAssembly, Path.Combine(unapprovedDirectory, assemblyFile));
        WriteManifest(unapprovedDirectory, "good", goodHash);
        var store = Path.Combine(root, "last-known-good.json");

        var first = RunChild(goodDirectory, store);
        Console.Write(first.Output);
        if (first.ExitCode != 0 || first.Output.Trim() != "SELECTED good" || !File.Exists(store))
            return 1;
        var stored = File.ReadAllBytes(store);

        var second = RunChild(badDirectory, store);
        Console.Write(second.Output);
        if (second.Output.Trim() != "REJECTED ContentHashMismatch")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var started = RunStart(badDirectory, store);
        Console.Write(started.Output);
        if (started.ExitCode != 0 || started.Output.Trim() != "FALLBACK good ContentHashMismatch")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var throwingDirectory = Path.Combine(root, "throwing");
        Directory.CreateDirectory(throwingDirectory);
        var throwingAssembly = Path.Combine(throwingDirectory, assemblyFile);
        WriteThrowingAssembly(throwingAssembly);
        var throwingHash = Hash(throwingAssembly);
        WriteManifest(throwingDirectory, "throwing", throwingHash);
        WriteApproval(throwingDirectory, "throwing", throwingHash);
        var beforeThrow = File.ReadAllBytes(store);
        var thrown = RunStart(throwingDirectory, store);
        Console.Write(thrown.Output);
        if (thrown.Output.Trim() != "REJECTED ActivationFailed"
            || thrown.Output.Contains("update-private-failure-9f3c", StringComparison.Ordinal))
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(beforeThrow))
            return 1;
        var third = RunChild(unapprovedDirectory, store);
        Console.Write(third.Output);
        if (third.Output.Trim() != "REJECTED NotApproved")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var extraDirectory = Path.Combine(root, "extra-bad");
        Directory.CreateDirectory(extraDirectory);
        File.Copy(goodAssembly, Path.Combine(extraDirectory, assemblyFile));
        File.WriteAllText(Path.Combine(extraDirectory, "TrustedUpdate.Private.dll"), "private-v1");
        WriteManifest(extraDirectory, "good", goodHash);
        WriteApproval(extraDirectory, "good", goodHash);
        WriteAdditional(extraDirectory, "TrustedUpdate.Private.dll", new string('0', 64));
        var extraRejected = RunChild(extraDirectory, store);
        Console.Write(extraRejected.Output);
        if (extraRejected.Output.Trim() != "REJECTED ContentHashMismatch")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var escapeDirectory = Path.Combine(root, "escape-name");
        Directory.CreateDirectory(escapeDirectory);
        File.Copy(goodAssembly, Path.Combine(escapeDirectory, assemblyFile));
        WriteManifest(escapeDirectory, "good", goodHash);
        WriteApproval(escapeDirectory, "good", goodHash);
        WriteAdditional(escapeDirectory, "..", goodHash);
        var escapeRejected = RunChild(escapeDirectory, store);
        Console.Write(escapeRejected.Output);
        if (escapeRejected.Output.Trim() != "REJECTED InvalidCandidate")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var extraGood = Path.Combine(root, "extra-good");
        Directory.CreateDirectory(extraGood);
        File.Copy(goodAssembly, Path.Combine(extraGood, assemblyFile));
        var privatePath = Path.Combine(extraGood, "TrustedUpdate.Private.dll");
        File.WriteAllText(privatePath, "private-v1");
        var privateHash = Hash(privatePath);
        WriteManifest(extraGood, "good", goodHash);
        WriteApproval(extraGood, "good", goodHash);
        WriteAdditional(extraGood, "TrustedUpdate.Private.dll", privateHash);
        var extraStore = Path.Combine(root, "extra-store.json");
        var extraSelected = RunChild(extraGood, extraStore);
        Console.Write(extraSelected.Output);
        if (extraSelected.ExitCode != 0 || extraSelected.Output.Trim() != "SELECTED good")
            return 1;
        var extraStored = File.ReadAllText(extraStore);
        if (!extraStored.Contains(privateHash, StringComparison.Ordinal))
            return 1;
        File.WriteAllText(privatePath, "private-v2");
        var extraTampered = RunRestore(extraStore, extraGood);
        Console.Write(extraTampered.Output);
        if (extraTampered.Output.Trim() != "REJECTED ContentHashMismatch")
            return 1;
        if (File.ReadAllText(extraStore) != extraStored)
            return 1;
        File.WriteAllText(privatePath, "private-v1");
        var extraRestored = RunRestore(extraStore, extraGood);
        Console.Write(extraRestored.Output);
        if (extraRestored.ExitCode != 0 || extraRestored.Output.Trim() != "SELECTED good")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var outsideDirectory = Path.Combine(root, "outside");
        Directory.CreateDirectory(outsideDirectory);
        File.Copy(goodAssembly, Path.Combine(outsideDirectory, assemblyFile));
        var outsideStore = Path.Combine(root, "outside-store.json");
        var tampered = JsonNode.Parse(File.ReadAllText(store))!.AsObject();
        tampered["AssemblyPath"] = Path.Combine(outsideDirectory, assemblyFile);
        File.WriteAllText(outsideStore, tampered.ToJsonString());
        var outsideRejected = RunRestore(outsideStore, goodDirectory);
        Console.Write(outsideRejected.Output);
        if (outsideRejected.Output.Trim() != "REJECTED OutsideContentRoot")
            return 1;
        if (!File.ReadAllBytes(store).AsSpan().SequenceEqual(stored))
            return 1;
        var restored = RunRestore(store, goodDirectory);
        Console.Write(restored.Output);
        if (restored.ExitCode != 0 || restored.Output.Trim() != "SELECTED good")
            return 1;
        var after = File.ReadAllText(store);
        if (!after.Contains("good", StringComparison.Ordinal) || !after.Contains(goodHash, StringComparison.Ordinal))
            return 1;
        var hostMissing = Path.Combine(root, "host-missing.json");
        var hostRejected = RunHostLoaded("ok", unapprovedDirectory, hostMissing);
        Console.Write(hostRejected.Output);
        if (hostRejected.ExitCode != 0
            || !hostRejected.Output.Contains("HOST-LOADED CALLS 0", StringComparison.Ordinal)
            || !hostRejected.Output.Contains("HOST-LOADED RESULT NotApproved", StringComparison.Ordinal)
            || !hostRejected.Output.Contains("HOST-LOADED NO-CONTEXT", StringComparison.Ordinal)
            || hostRejected.Output.Contains("HOST-LOADED RAN", StringComparison.Ordinal)
            || File.Exists(hostMissing))
            return 1;
        var returnDirectory = Path.Combine(root, "returning");
        Directory.CreateDirectory(returnDirectory);
        var returnAssembly = Path.Combine(returnDirectory, assemblyFile);
        WriteReturningAssembly(returnAssembly);
        var returnHash = Hash(returnAssembly);
        WriteManifest(returnDirectory, "returning", returnHash);
        WriteApproval(returnDirectory, "returning", returnHash);
        var hostStore = Path.Combine(root, "host-store.json");
        var hostOk = RunHostLoaded("ok", returnDirectory, hostStore);
        Console.Write(hostOk.Output);
        if (hostOk.ExitCode != 0
            || !hostOk.Output.Contains("HOST-LOADED CALLS 1 Candidate returning", StringComparison.Ordinal)
            || !hostOk.Output.Contains("HOST-LOADED RESULT None Candidate 11 None", StringComparison.Ordinal)
            || !hostOk.Output.Contains("HOST-LOADED NO-CONTEXT", StringComparison.Ordinal)
            || !hostOk.Output.Contains("HOST-LOADED RAN returning", StringComparison.Ordinal)
            || !File.Exists(hostStore))
            return 1;
        var hostBytes = File.ReadAllBytes(hostStore);
        var hostFailStore = Path.Combine(root, "host-fail.json");
        var hostFail = RunHostLoaded("activate-fail", goodDirectory, hostFailStore);
        Console.Write(hostFail.Output);
        if (hostFail.ExitCode != 0
            || !hostFail.Output.Contains("HOST-LOADED RESULT ActivationFailed", StringComparison.Ordinal)
            || !hostFail.Output.Contains("HOST-LOADED CALLS 1 Candidate good", StringComparison.Ordinal)
            || hostFail.Output.Contains("HOST-LOADED RAN", StringComparison.Ordinal)
            || File.Exists(hostFailStore))
            return 1;
        var hostFallback = RunHostLoaded("ok", unapprovedDirectory, hostStore);
        Console.Write(hostFallback.Output);
        if (hostFallback.ExitCode != 0
            || !hostFallback.Output.Contains("HOST-LOADED CALLS 1 LastKnownGood returning", StringComparison.Ordinal)
            || !hostFallback.Output.Contains("HOST-LOADED RESULT None LastKnownGood 11 NotApproved", StringComparison.Ordinal)
            || !hostFallback.Output.Contains("HOST-LOADED NO-CONTEXT", StringComparison.Ordinal)
            || !hostFallback.Output.Contains("HOST-LOADED RAN returning", StringComparison.Ordinal)
            || !File.ReadAllBytes(hostStore).AsSpan().SequenceEqual(hostBytes))
            return 1;
        var hostThrowStore = Path.Combine(root, "host-throw.json");
        var hostThrow = RunHostLoaded("ok", throwingDirectory, hostThrowStore);
        Console.Write(hostThrow.Output);
        if (hostThrow.ExitCode != 0
            || !hostThrow.Output.Contains("HOST-LOADED CALLS 1 Candidate throwing", StringComparison.Ordinal)
            || !hostThrow.Output.Contains("HOST-LOADED RESULT ActivationFailed", StringComparison.Ordinal)
            || hostThrow.Output.Contains("HOST-LOADED RAN", StringComparison.Ordinal)
            || hostThrow.Output.Contains("Exception", StringComparison.Ordinal)
            || hostThrow.Output.Contains("update-private-failure-9f3c", StringComparison.Ordinal)
            || hostThrow.Output.Contains("LastKnownGood", StringComparison.Ordinal)
            || File.Exists(hostThrowStore))
            return 1;
        var hostNoFallback = RunHostLoaded("ok", throwingDirectory, hostStore);
        Console.Write(hostNoFallback.Output);
        if (hostNoFallback.ExitCode != 0
            || !hostNoFallback.Output.Contains("HOST-LOADED RESULT ActivationFailed", StringComparison.Ordinal)
            || hostNoFallback.Output.Contains("LastKnownGood", StringComparison.Ordinal)
            || hostNoFallback.Output.Contains("HOST-LOADED RAN", StringComparison.Ordinal)
            || hostNoFallback.Output.Contains("Exception", StringComparison.Ordinal)
            || hostNoFallback.Output.Contains("update-private-failure-9f3c", StringComparison.Ordinal)
            || !File.ReadAllBytes(hostStore).AsSpan().SequenceEqual(hostBytes))
            return 1;
        var tickDirectory = Path.Combine(root, "tick");
        Directory.CreateDirectory(tickDirectory);
        var tickAssembly = Path.Combine(tickDirectory, assemblyFile);
        WriteTickAssembly(tickAssembly);
        var tickHash = Hash(tickAssembly);
        WriteManifest(tickDirectory, "tick", tickHash);
        WriteApproval(tickDirectory, "tick", tickHash);
        var ticked = RunTick(tickDirectory, Path.Combine(root, "tick-store.json"));
        Console.Write(ticked.Output);
        if (ticked.ExitCode != 0
            || !ticked.Output.Contains("TICK 5", StringComparison.Ordinal)
            || !ticked.Output.Contains("LATE-CLOSED", StringComparison.Ordinal))
            return 1;
        var signalDirectory = Path.Combine(root, "signal");
        Directory.CreateDirectory(signalDirectory);
        var signalAssembly = Path.Combine(signalDirectory, assemblyFile);
        WriteSignalAssembly(signalAssembly);
        var signalHash = Hash(signalAssembly);
        WriteManifest(signalDirectory, "signal", signalHash);
        WriteApproval(signalDirectory, "signal", signalHash);
        var signaled = RunSignal(signalDirectory, Path.Combine(root, "signal-store.json"));
        Console.Write(signaled.Output);
        if (signaled.ExitCode != 0
            || !signaled.Output.Contains("LISTEN 10", StringComparison.Ordinal)
            || !signaled.Output.Contains("SEEN 10", StringComparison.Ordinal)
            || !signaled.Output.Contains("SUBSCRIBE-CLOSED", StringComparison.Ordinal)
            || signaled.Output.Contains("SUBSCRIBE-OPEN", StringComparison.Ordinal))
            return 1;
        var genericDirectory = Path.Combine(root, "generic");
        Directory.CreateDirectory(genericDirectory);
        var genericAssembly = Path.Combine(genericDirectory, assemblyFile);
        WriteGenericAssembly(genericAssembly);
        var genericHash = Hash(genericAssembly);
        WriteManifest(genericDirectory, "generic", genericHash);
        WriteApproval(genericDirectory, "generic", genericHash);
        var generic = RunGeneric(genericDirectory, Path.Combine(root, "generic-store.json"));
        Console.Write(generic.Output);
        if (generic.ExitCode != 0
            || !generic.Output.Contains("VALUE-REJECTED", StringComparison.Ordinal)
            || generic.Output.Contains("VALUE-CALLED", StringComparison.Ordinal)
            || !generic.Output.Contains("CALLS-BEFORE 0", StringComparison.Ordinal)
            || !generic.Output.Contains("OBJECT-SAME", StringComparison.Ordinal)
            || !generic.Output.Contains("STRING-SAME", StringComparison.Ordinal)
            || generic.Output.Contains("STRING-DIFFERENT", StringComparison.Ordinal)
            || !generic.Output.Contains("INT 11", StringComparison.Ordinal)
            || !generic.Output.Contains("CALLS 3", StringComparison.Ordinal)
            || !generic.Output.Contains("MUTATE-SAME", StringComparison.Ordinal)
            || !generic.Output.Contains("BOX-SAME", StringComparison.Ordinal))
            return 1;
        var orderDirectory = Path.Combine(root, "work-order");
        Directory.CreateDirectory(orderDirectory);
        var orderAssembly = Path.Combine(orderDirectory, assemblyFile);
        WriteWorkOrderAssembly(orderAssembly);
        var orderHash = Hash(orderAssembly);
        WriteManifest(orderDirectory, "work-order", orderHash);
        WriteApproval(orderDirectory, "work-order", orderHash);
        var ordered = RunWorkOrder(orderDirectory, Path.Combine(root, "work-order-store.json"));
        Console.Write(ordered.Output);
        if (ordered.ExitCode != 0
            || !ordered.Output.Contains("NAMES bad,good", StringComparison.Ordinal)
            || !ordered.Output.Contains("TAKE 7", StringComparison.Ordinal)
            || !ordered.Output.Contains("TAKE 4", StringComparison.Ordinal)
            || ordered.Output.Contains("TAKE -1", StringComparison.Ordinal))
            return 1;
        var nullCallbackDirectory = Path.Combine(root, "null-callback");
        Directory.CreateDirectory(nullCallbackDirectory);
        var nullCallbackAssembly = Path.Combine(nullCallbackDirectory, assemblyFile);
        WriteNullCallbackAssembly(nullCallbackAssembly);
        var nullCallbackHash = Hash(nullCallbackAssembly);
        WriteManifest(nullCallbackDirectory, "null-callback", nullCallbackHash);
        WriteApproval(nullCallbackDirectory, "null-callback", nullCallbackHash);
        var nullCallback = RunNullCallback(nullCallbackDirectory, Path.Combine(root, "null-callback-store.json"));
        Console.Write(nullCallback.Output);
        if (nullCallback.ExitCode != 0
            || !nullCallback.Output.Contains("NULL-CALLBACK", StringComparison.Ordinal)
            || nullCallback.Output.Contains("NULL-OPEN", StringComparison.Ordinal)
            || !nullCallback.Output.Contains("TICK ActivationFailed", StringComparison.Ordinal)
            || !nullCallback.Output.Contains("CALLS-BEFORE 0", StringComparison.Ordinal)
            || !nullCallback.Output.Contains("TICK 2", StringComparison.Ordinal)
            || !nullCallback.Output.Contains("CALLS 1", StringComparison.Ordinal)
            || nullCallback.Output.Contains("CALLS 2", StringComparison.Ordinal))
            return 1;
        var workDirectory = Path.Combine(root, "work");


        Directory.CreateDirectory(workDirectory);
        var workAssembly = Path.Combine(workDirectory, assemblyFile);
        WriteWorkAssembly(workAssembly);
        var workHash = Hash(workAssembly);
        WriteManifest(workDirectory, "work", workHash);
        WriteApproval(workDirectory, "work", workHash);
        var worked = RunWork(workDirectory, Path.Combine(root, "work-store.json"));
        Console.Write(worked.Output);
        return worked.ExitCode == 0
            && worked.Output.Contains("WORK 0", StringComparison.Ordinal)
            && worked.Output.Contains("WORK ActivationFailed", StringComparison.Ordinal)
            && worked.Output.Contains("OPEN load", StringComparison.Ordinal)
            && worked.Output.Contains("TAKE 4", StringComparison.Ordinal)
            && worked.Output.Contains("CLOSED", StringComparison.Ordinal)
            && !worked.Output.Contains("update-private-failure-9f3c", StringComparison.Ordinal) ? 0 : 1;
    }
    finally
    {
        try
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
        catch (Exception)
        {
        }
    }
}


static void WriteApproval(string directory, string version, string hash)
{
    var file = new HostApprovalFile
    {
        VersionName = version,
        ContentSha256 = hash,
        ApprovalId = "console-host",
    };
    File.WriteAllText(Path.Combine(directory, "trusted-update-approval.json"), JsonSerializer.Serialize(file));
}

static void WriteAdditional(string directory, string fileName, string hash)
{
    var manifestPath = Path.Combine(directory, "trusted-update.json");
    var manifest = JsonNode.Parse(File.ReadAllText(manifestPath))!.AsObject();
    manifest["AdditionalFiles"] = new JsonArray
    {
        new JsonObject
        {
            ["FileName"] = fileName,
            ["ContentSha256"] = hash,
        },
    };
    File.WriteAllText(manifestPath, manifest.ToJsonString());
}

static void WriteManifest(string directory, string version, string hash)
{
    var file = new HostCandidateFile
    {
        VersionName = version,
        ContentSha256 = hash,
        AssemblyFile = "TrustedUpdate.SampleCandidate.dll",
        EntryTypeName = "TrustedUpdate.SampleCandidate.Entry",
        EntryMethodName = "Activate",
        Runtime = HostRuntime,
        Architecture = HostArchitecture(),
    };
    File.WriteAllText(Path.Combine(directory, "trusted-update.json"), JsonSerializer.Serialize(file));
}

static int TickSample(string directory, string store, TrustedUpdateTarget hostTarget, System.Diagnostics.Stopwatch? timingStartup = null)
{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }
    process.OpenSession();
    var calls = 0;
    timingStartup?.Stop();
    var timingCallback = timingStartup is null ? null : System.Diagnostics.Stopwatch.StartNew();
    var tick = process.TryTick(1, new SampleEcho(value =>
    {
        calls++;
        return value + 1;
    }));
    timingCallback?.Stop();
    var timingBoundary = timingStartup is null ? null : System.Diagnostics.Stopwatch.StartNew();
    Console.WriteLine(tick.Succeeded ? "TICK " + tick.Value : "TICK " + tick.Failure);
    var closed = false;
    try
    {
        var assembly = AssemblyLoadContext.All.SelectMany(context => context.Assemblies)
            .First(item => item.GetName().Name == "TrustedUpdate.SampleCandidate");
        var kept = assembly.GetType("TrustedUpdate.SampleCandidate.Entry")!
            .GetField("Kept", BindingFlags.Public | BindingFlags.Static)!
            .GetValue(null) as ITrustedUpdateHost;
        kept!.Echo(9);
    }
    catch (InvalidOperationException exception) when (exception.Message == "host callback closed")
    {
        closed = true;
    }
    Console.WriteLine(closed && calls == 1 ? "LATE-CLOSED" : "LATE-OPEN");
    if (timingStartup is not null && timingCallback is not null && timingBoundary is not null)
    {
        Console.Out.Flush();
        timingBoundary.Stop();
        Console.WriteLine("TIMING_STARTUP_MS " + timingStartup.ElapsedMilliseconds);
        Console.WriteLine("TIMING_CALLBACK_MS " + timingCallback.ElapsedMilliseconds);
        Console.WriteLine("TIMING_BOUNDARY_MS " + timingBoundary.ElapsedMilliseconds);
        Console.WriteLine("scope=one-desktop-self-test-sample");
    }
    return tick.Value == 5 && closed && calls == 1 ? 0 : 1;
}

static int TimeOneTick(TrustedUpdateTarget hostTarget, System.Diagnostics.Stopwatch timingStartup)
{
    var root = Path.Combine(Path.GetTempPath(), "runeclr-timings-" + Guid.NewGuid().ToString("n"));
    Directory.CreateDirectory(root);
    try
    {
        var tickDirectory = Path.Combine(root, "tick");
        Directory.CreateDirectory(tickDirectory);
        var tickAssembly = Path.Combine(tickDirectory, "TrustedUpdate.SampleCandidate.dll");
        WriteTickAssembly(tickAssembly);
        var tickHash = Hash(tickAssembly);
        WriteManifest(tickDirectory, "tick", tickHash);
        WriteApproval(tickDirectory, "tick", tickHash);
        return TickSample(tickDirectory, Path.Combine(root, "tick-store.json"), hostTarget, timingStartup);
    }
    finally
    {
        try
        {
            Directory.Delete(root, true);
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}

static int GenericSample(string directory, string store, TrustedUpdateTarget hostTarget)
{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }
    process.OpenSession();
    var rejected = false;
    try
    {
        process.TryEchoGenericObject(4);
    }
    catch (ArgumentException exception) when (exception.Message.StartsWith("Generic object echo requires a reference type.", StringComparison.Ordinal))
    {
        rejected = true;
    }
    var assembly = AssemblyLoadContext.All.SelectMany(context => context.Assemblies)
        .First(item => item.GetName().Name == "TrustedUpdate.SampleCandidate");
    var entry = assembly.GetType("TrustedUpdate.SampleCandidate.Entry")!;
    var before = (int)entry.GetField("Calls")!.GetValue(null)!;
    Console.WriteLine(rejected && before == 0 ? "VALUE-REJECTED" : "VALUE-CALLED");
    Console.WriteLine("CALLS-BEFORE " + before);
    var token = new object();
    var echoed = process.TryEchoGenericObject(token);
    Console.WriteLine(echoed.Succeeded && echoed.SameReference ? "OBJECT-SAME" : "OBJECT-DIFFERENT");
    var text = "rune-generic";
    var textEcho = process.TryEchoGenericObject(text);
    Console.WriteLine(textEcho.Succeeded && textEcho.SameReference ? "STRING-SAME" : "STRING-DIFFERENT");
    var number = process.TryEchoGenericInt(11);
    Console.WriteLine(number.Succeeded ? "INT " + number.Value : "INT " + number.Failure);
    var calls = (int)entry.GetField("Calls")!.GetValue(null)!;
    Console.WriteLine("CALLS " + calls);
    var data = new int[1];
    var mutated = process.TryMutateFirst(data);
    Console.WriteLine(mutated ? "MUTATE-SAME" : "MUTATE-DIFFERENT");
    var box = new TrustedUpdateMutableBox();
    var boxMutated = process.TryMutateBox(box);
    Console.WriteLine(boxMutated ? "BOX-SAME" : "BOX-DIFFERENT");
    return rejected && before == 0 && echoed.SameReference && textEcho.SameReference && number.Value == 11 && calls == 3 && mutated && boxMutated ? 0 : 1;
}

static void WriteGenericAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var calls = type.DefineField("Calls", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var echo = type.DefineMethod("EchoGeneric", MethodAttributes.Public | MethodAttributes.Static);
    var typeParameter = echo.DefineGenericParameters("T")[0];
    echo.SetReturnType(typeParameter);
    echo.SetParameters(typeParameter);
    var il = echo.GetILGenerator();
    il.Emit(OpCodes.Ldsfld, calls);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Add);
    il.Emit(OpCodes.Stsfld, calls);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ret);
    var mutate = type.DefineMethod("MutateFirst", MethodAttributes.Public | MethodAttributes.Static, typeof(int[]), new[] { typeof(int[]) });
    var mutateIl = mutate.GetILGenerator();
    mutateIl.Emit(OpCodes.Ldarg_0);
    mutateIl.Emit(OpCodes.Ldc_I4_0);
    mutateIl.Emit(OpCodes.Ldc_I4_7);
    mutateIl.Emit(OpCodes.Stelem_I4);
    mutateIl.Emit(OpCodes.Ldarg_0);
    mutateIl.Emit(OpCodes.Ret);
    var boxType = typeof(TrustedUpdateMutableBox);
    var mutateBox = type.DefineMethod("MutateBox", MethodAttributes.Public | MethodAttributes.Static, boxType, new[] { boxType });
    var boxIl = mutateBox.GetILGenerator();
    boxIl.Emit(OpCodes.Ldarg_0);
    boxIl.Emit(OpCodes.Ldc_I4_7);
    boxIl.Emit(OpCodes.Callvirt, boxType.GetProperty("Value")!.SetMethod!);
    boxIl.Emit(OpCodes.Ldarg_0);
    boxIl.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunGeneric(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--generic");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}
static int SignalSample(string directory, string store, TrustedUpdateTarget hostTarget)

{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }
    process.OpenSession();
    var listened = process.TryListen();
    Console.WriteLine(listened.Succeeded ? "LISTEN " + listened.Value : "LISTEN " + listened.Failure);
    var assembly = AssemblyLoadContext.All.SelectMany(context => context.Assemblies)
        .First(item => item.GetName().Name == "TrustedUpdate.SampleCandidate");
    var entry = assembly.GetType("TrustedUpdate.SampleCandidate.Entry")!;
    var seen = (int)entry.GetField("Seen")!.GetValue(null)!;
    Console.WriteLine("SEEN " + seen);
    var kept = entry.GetField("Kept")!.GetValue(null) as ITrustedUpdateSignals;
    var added = 0;
    var closed = false;
    try
    {
        kept!.Signal += value => added += value;
    }
    catch (InvalidOperationException exception) when (exception.Message == "host callback closed")
    {
        closed = true;
    }
    var stored = kept?.GetType().GetField("signal", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(kept);
    Console.WriteLine(closed && added == 0 && stored is null ? "SUBSCRIBE-CLOSED" : "SUBSCRIBE-OPEN");
    return listened.Value == 10 && seen == 10 && closed && added == 0 && stored is null ? 0 : 1;
}

static void WriteSignalAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var seen = type.DefineField("Seen", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
    var kept = type.DefineField("Kept", typeof(ITrustedUpdateSignals), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var onA = type.DefineMethod("OnA", MethodAttributes.Private | MethodAttributes.Static, typeof(void), new[] { typeof(int) });
    var onAIl = onA.GetILGenerator();
    onAIl.Emit(OpCodes.Ldsfld, seen);
    onAIl.Emit(OpCodes.Ldc_I4_1);
    onAIl.Emit(OpCodes.Add);
    onAIl.Emit(OpCodes.Stsfld, seen);
    onAIl.Emit(OpCodes.Ret);
    var onB = type.DefineMethod("OnB", MethodAttributes.Private | MethodAttributes.Static, typeof(void), new[] { typeof(int) });
    var onBIl = onB.GetILGenerator();
    onBIl.Emit(OpCodes.Ldsfld, seen);
    onBIl.Emit(OpCodes.Ldc_I4, 10);
    onBIl.Emit(OpCodes.Add);
    onBIl.Emit(OpCodes.Stsfld, seen);
    onBIl.Emit(OpCodes.Ret);
    var listen = type.DefineMethod("Listen", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(ITrustedUpdateSignals) });
    var il = listen.GetILGenerator();
    var handlerA = il.DeclareLocal(typeof(Action<int>));
    var handlerB = il.DeclareLocal(typeof(Action<int>));
    var ctor = typeof(Action<int>).GetConstructor(new[] { typeof(object), typeof(IntPtr) })!;
    var add = typeof(ITrustedUpdateSignals).GetEvent("Signal")!.GetAddMethod()!;
    var remove = typeof(ITrustedUpdateSignals).GetEvent("Signal")!.GetRemoveMethod()!;
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Stsfld, kept);
    il.Emit(OpCodes.Ldnull);
    il.Emit(OpCodes.Ldftn, onA);
    il.Emit(OpCodes.Newobj, ctor);
    il.Emit(OpCodes.Stloc, handlerA);
    il.Emit(OpCodes.Ldnull);
    il.Emit(OpCodes.Ldftn, onB);
    il.Emit(OpCodes.Newobj, ctor);
    il.Emit(OpCodes.Stloc, handlerB);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloc, handlerA);
    il.Emit(OpCodes.Callvirt, add);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloc, handlerB);
    il.Emit(OpCodes.Callvirt, add);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloc, handlerA);
    il.Emit(OpCodes.Callvirt, remove);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldc_I4_4);
    il.Emit(OpCodes.Callvirt, typeof(ITrustedUpdateSignals).GetMethod("Raise")!);
    il.Emit(OpCodes.Ldsfld, seen);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunSignal(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--signal");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}
static int NullCallbackSample(string directory, string store, TrustedUpdateTarget hostTarget)
{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }
    process.OpenSession();
    var rejected = false;
    try
    {
        process.TryTick(1, (Func<int, int>)null!);
    }
    catch (ArgumentNullException exception) when (exception.ParamName == "hostCall")
    {
        rejected = true;
    }
    Console.WriteLine(rejected ? "NULL-CALLBACK" : "NULL-OPEN");
    var plain = process.TryTick(1);
    Console.WriteLine(plain.Succeeded ? "TICK " + plain.Value : "TICK " + plain.Failure);
    var assembly = AssemblyLoadContext.All.SelectMany(context => context.Assemblies)
        .First(item => item.GetName().Name == "TrustedUpdate.SampleCandidate");
    var entry = assembly.GetType("TrustedUpdate.SampleCandidate.Entry")!;
    var before = (int)entry.GetField("Calls")!.GetValue(null)!;
    Console.WriteLine("CALLS-BEFORE " + before);
    var calls = 0;
    var tick = process.TryTick(1, value =>
    {
        calls++;
        return value + 1;
    });
    Console.WriteLine(tick.Succeeded ? "TICK " + tick.Value : "TICK " + tick.Failure);
    var after = (int)entry.GetField("Calls")!.GetValue(null)!;
    Console.WriteLine("CALLS " + after);
    return rejected && plain.Failure == TrustedUpdateFailure.ActivationFailed && before == 0 && tick.Value == 2 && calls == 1 && after == 1 ? 0 : 1;
}

static void WriteNullCallbackAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var calls = type.DefineField("Calls", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var tick = type.DefineMethod("Tick", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int), typeof(Func<int, int>) });
    var il = tick.GetILGenerator();
    il.Emit(OpCodes.Ldsfld, calls);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Add);
    il.Emit(OpCodes.Stsfld, calls);
    il.Emit(OpCodes.Ldarg_1);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Callvirt, typeof(Func<int, int>).GetMethod("Invoke")!);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunNullCallback(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--null-callback");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}
static int WorkOrderSample(string directory, string store, TrustedUpdateTarget hostTarget)
{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }
    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }
    process.OpenSession();
    var first = process.TryWork();
    Console.WriteLine(first.Succeeded ? "WORK " + first.Value : "WORK " + first.Failure);
    var pending = process.CopyPendingWork();
    Console.WriteLine("NAMES " + string.Join(",", pending.Select(item => item.Name)));
    if (pending.Length != 2 || pending[0].Name != "bad" || pending[1].Name != "good" || pending[0].Id == pending[1].Id)
        return 1;
    process.FailWork(pending[0].Id, 7);
    process.CompleteWork(pending[1].Id, 4);
    var failed = process.TryWork();
    Console.WriteLine(failed.Succeeded ? "TAKE " + failed.Value : "TAKE " + failed.Failure);
    var succeeded = process.TryWork();
    Console.WriteLine(succeeded.Succeeded ? "TAKE " + succeeded.Value : "TAKE " + succeeded.Failure);
    return first.Value == 0 && failed.Value == 7 && succeeded.Value == 4 ? 0 : 1;
}

static void WriteWorkOrderAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var phase = type.DefineField("Phase", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var request = typeof(ITrustedUpdateWork).GetMethod("Request")!;
    var tryTake = typeof(ITrustedUpdateWork).GetMethod("TryTake")!;
    var work = type.DefineMethod("Work", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(ITrustedUpdateWork) });
    var il = work.GetILGenerator();
    var take = il.DefineLabel();
    var second = il.DefineLabel();
    var bad = il.DefineLabel();
    var id = il.DeclareLocal(typeof(long));
    var value = il.DeclareLocal(typeof(int));
    var ok = il.DeclareLocal(typeof(bool));
    var succeeded = il.DeclareLocal(typeof(bool));
    il.Emit(OpCodes.Ldsfld, phase);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Beq, take);
    il.Emit(OpCodes.Ldsfld, phase);
    il.Emit(OpCodes.Ldc_I4_2);
    il.Emit(OpCodes.Beq, second);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Stsfld, phase);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldstr, "bad");
    il.Emit(OpCodes.Callvirt, request);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldstr, "good");
    il.Emit(OpCodes.Callvirt, request);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldc_I4_0);
    il.Emit(OpCodes.Ret);
    il.MarkLabel(take);
    il.Emit(OpCodes.Ldc_I4_2);
    il.Emit(OpCodes.Stsfld, phase);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloca, id);
    il.Emit(OpCodes.Ldloca, value);
    il.Emit(OpCodes.Ldloca, succeeded);
    il.Emit(OpCodes.Callvirt, tryTake);
    il.Emit(OpCodes.Stloc, ok);
    il.Emit(OpCodes.Ldloc, ok);
    il.Emit(OpCodes.Brfalse, bad);
    il.Emit(OpCodes.Ldloc, succeeded);
    il.Emit(OpCodes.Brtrue, bad);
    il.Emit(OpCodes.Ldloc, value);
    il.Emit(OpCodes.Ldc_I4, 7);
    il.Emit(OpCodes.Bne_Un, bad);
    il.Emit(OpCodes.Ldc_I4, 7);
    il.Emit(OpCodes.Ret);
    il.MarkLabel(second);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloca, id);
    il.Emit(OpCodes.Ldloca, value);
    il.Emit(OpCodes.Ldloca, succeeded);
    il.Emit(OpCodes.Callvirt, tryTake);
    il.Emit(OpCodes.Stloc, ok);
    il.Emit(OpCodes.Ldloc, ok);
    il.Emit(OpCodes.Brfalse, bad);
    il.Emit(OpCodes.Ldloc, succeeded);
    il.Emit(OpCodes.Brfalse, bad);
    il.Emit(OpCodes.Ldloc, value);
    il.Emit(OpCodes.Ldc_I4_4);
    il.Emit(OpCodes.Bne_Un, bad);
    il.Emit(OpCodes.Ldc_I4_4);
    il.Emit(OpCodes.Ret);
    il.MarkLabel(bad);
    il.Emit(OpCodes.Ldc_I4_M1);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunWorkOrder(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--work-order");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}
static int WorkSample(string directory, string store, TrustedUpdateTarget hostTarget)
{
    if (!TryReadCandidate(directory, out var candidate) || !TryReadApproval(directory, out var approval) || approval is null)
    {
        Console.WriteLine("REJECTED InvalidCandidate");
        return 1;
    }

    var process = new TrustedUpdateProcess();
    var selected = process.TrySelectCandidate(candidate, hostTarget, store, approval, directory);
    if (!selected.Succeeded)
    {
        Console.WriteLine("REJECTED " + selected.Failure);
        return 1;
    }

    process.OpenSession();
    var first = process.TryWork();
    Console.WriteLine(first.Succeeded ? "WORK " + first.Value : "WORK " + first.Failure);
    var failed = process.TryWork();
    Console.WriteLine(failed.Succeeded ? "WORK " + failed.Value : "WORK " + failed.Failure);
    var pending = process.CopyPendingWork();
    Console.WriteLine(pending.Length == 1 && pending[0].Name == "load" ? "OPEN load" : "OPEN " + pending.Length);
    if (pending.Length != 1)
        return 1;
    process.CompleteWork(pending[0].Id, 4);
    var taken = process.TryWork();
    Console.WriteLine(taken.Succeeded ? "TAKE " + taken.Value : "TAKE " + taken.Failure);
    var later = process.CopyPendingWork();
    process.CloseSession();
    var closed = false;
    try
    {
        if (later.Length == 1)
            process.CompleteWork(later[0].Id, 1);
    }
    catch (InvalidOperationException exception) when (exception.Message == "The session is not open.")
    {
        closed = true;
    }

    Console.WriteLine(closed && later.Length == 1 && later[0].Name == "later" ? "CLOSED" : "OPEN");
    return first.Value == 0 && failed.Failure == TrustedUpdateFailure.ActivationFailed && taken.Value == 4 && closed ? 0 : 1;
}

static void WriteWorkAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var phase = type.DefineField("Phase", typeof(int), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var request = typeof(ITrustedUpdateWork).GetMethod("Request")!;
    var tryTake = typeof(ITrustedUpdateWork).GetMethod("TryTake")!;
    var work = type.DefineMethod("Work", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(ITrustedUpdateWork) });
    var il = work.GetILGenerator();
    var fault = il.DefineLabel();
    var take = il.DefineLabel();
    var mismatch = il.DefineLabel();
    var id = il.DeclareLocal(typeof(long));
    var value = il.DeclareLocal(typeof(int));
    var ok = il.DeclareLocal(typeof(bool));
    il.Emit(OpCodes.Ldsfld, phase);
    il.Emit(OpCodes.Brtrue, fault);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldstr, "load");
    il.Emit(OpCodes.Callvirt, request);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Stsfld, phase);
    il.Emit(OpCodes.Ldc_I4_0);
    il.Emit(OpCodes.Ret);
    il.MarkLabel(fault);
    il.Emit(OpCodes.Ldsfld, phase);
    il.Emit(OpCodes.Ldc_I4_1);
    il.Emit(OpCodes.Bne_Un, take);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldstr, "bad");
    il.Emit(OpCodes.Callvirt, request);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldc_I4_2);
    il.Emit(OpCodes.Stsfld, phase);
    il.Emit(OpCodes.Ldstr, "update-private-failure-9f3c");
    il.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
    il.Emit(OpCodes.Throw);
    il.MarkLabel(take);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldloca, id);
    il.Emit(OpCodes.Ldloca, value);
    il.Emit(OpCodes.Ldloca, ok);
    il.Emit(OpCodes.Callvirt, tryTake);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Ldstr, "later");
    il.Emit(OpCodes.Callvirt, request);
    il.Emit(OpCodes.Pop);
    il.Emit(OpCodes.Ldloc, ok);
    il.Emit(OpCodes.Brfalse, mismatch);
    il.Emit(OpCodes.Ldloc, value);
    il.Emit(OpCodes.Ldc_I4_4);
    il.Emit(OpCodes.Bne_Un, mismatch);
    il.Emit(OpCodes.Ldc_I4_4);
    il.Emit(OpCodes.Ret);
    il.MarkLabel(mismatch);
    il.Emit(OpCodes.Ldc_I4_M1);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunWork(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--work");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}

static void WriteTickAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var kept = type.DefineField("Kept", typeof(ITrustedUpdateHost), FieldAttributes.Public | FieldAttributes.Static);
    var activate = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    activate.GetILGenerator().Emit(OpCodes.Ret);
    var tick = type.DefineMethod("Tick", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int), typeof(ITrustedUpdateHost) });
    var il = tick.GetILGenerator();
    il.Emit(OpCodes.Ldarg_1);
    il.Emit(OpCodes.Stsfld, kept);
    il.Emit(OpCodes.Ldarg_1);
    il.Emit(OpCodes.Ldarg_0);
    il.Emit(OpCodes.Callvirt, typeof(ITrustedUpdateHost).GetMethod("Echo")!);
    il.Emit(OpCodes.Ldc_I4_3);
    il.Emit(OpCodes.Add);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunTick(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--tick");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout);
}

static void WriteCandidateAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var method = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    method.GetILGenerator().Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static void WriteReturningAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var method = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(int), Type.EmptyTypes);
    var il = method.GetILGenerator();
    il.Emit(OpCodes.Ldc_I4, 11);
    il.Emit(OpCodes.Ret);
    type.CreateType();
    builder.Save(path);
}

static (int ExitCode, string Output) RunRestore(string store, string? contentRoot = null)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--restore");
    start.ArgumentList.Add(store);
    if (!string.IsNullOrWhiteSpace(contentRoot))
        start.ArgumentList.Add(contentRoot);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout);
}

static (int ExitCode, string Output) RunStart(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--start");
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}

static void WriteThrowingAssembly(string path)
{
    var builder = new PersistedAssemblyBuilder(
        new AssemblyName("TrustedUpdate.SampleCandidate") { Version = new Version(1, 0, 0, 0) },
        typeof(object).Assembly);
    var module = builder.DefineDynamicModule("TrustedUpdate.SampleCandidate");
    var type = module.DefineType(
        "TrustedUpdate.SampleCandidate.Entry",
        TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
    var method = type.DefineMethod("Activate", MethodAttributes.Public | MethodAttributes.Static, typeof(void), Type.EmptyTypes);
    var il = method.GetILGenerator();
    il.Emit(OpCodes.Ldstr, "update-private-failure-9f3c");
    il.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
    il.Emit(OpCodes.Throw);
    type.CreateType();
    builder.Save(path);
}

static int HostLoaded(string mode, string directory, string store, TrustedUpdateTarget hostTarget)
{
    if (!TryReadCandidate(directory, out var candidate))
    {
        Console.WriteLine("HOST-LOADED RESULT InvalidCandidate None 0 None");
        return 1;
    }
    if (!TryReadApproval(directory, out var approval))
        approval = null;
    TrustedUpdateApproval? fallbackApproval = null;
    string? fallbackRoot = null;
    if (File.Exists(store))
    {
        using var document = JsonDocument.Parse(File.ReadAllText(store));
        var rootElement = document.RootElement;
        string? assemblyPath = null;
        if (rootElement.TryGetProperty("AssemblyPath", out var pathProperty))
            assemblyPath = pathProperty.GetString();
        var storedDirectory = string.IsNullOrWhiteSpace(assemblyPath) ? null : Path.GetDirectoryName(assemblyPath);
        if (!string.IsNullOrWhiteSpace(storedDirectory))
        {
            fallbackRoot = storedDirectory;
            if (!TryReadApproval(storedDirectory, out fallbackApproval))
                fallbackApproval = null;
        }
    }
    var calls = 0;
    var seen = "";
    var started = new TrustedUpdateProcess().TryStartHostLoaded(
        candidate,
        hostTarget,
        store,
        approval,
        directory,
        fallbackApproval,
        fallbackRoot,
        null,
        (chosen, source, _) =>
        {
            calls++;
            seen = source + " " + chosen.VersionName;
            if (mode == "activate-fail" && source == TrustedUpdateStartSource.Candidate)
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            try
            {
                var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(chosen.AssemblyPath));
                var type = assembly.GetType(chosen.EntryTypeName, throwOnError: true, ignoreCase: false);
                var method = type?.GetMethod(chosen.EntryMethodName, BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
                if (method is null || method.GetParameters().Length != 0)
                    return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
                var returned = method.Invoke(null, null);
                if (method.ReturnType == typeof(int))
                {
                    Console.WriteLine("HOST-LOADED RAN " + chosen.VersionName);
                    return new TrustedUpdateActivation(TrustedUpdateFailure.None, (int)returned!);
                }
                if (method.ReturnType != typeof(void))
                    return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            }
            catch (Exception)
            {
                return new TrustedUpdateActivation(TrustedUpdateFailure.ActivationFailed, 0);
            }
            Console.WriteLine("HOST-LOADED RAN " + chosen.VersionName);
            return new TrustedUpdateActivation(TrustedUpdateFailure.None, 0);
        });
    var loaded = AssemblyLoadContext.All.Any(context =>
        context.Name != null && context.Name.StartsWith("RuneCLR.TrustedUpdate:", StringComparison.Ordinal));
    Console.WriteLine("HOST-LOADED CALLS " + calls + " " + seen);
    Console.WriteLine("HOST-LOADED RESULT " + started.Failure + " " + started.Source + " " + started.Value + " " + started.CandidateFailure);
    Console.WriteLine(loaded ? "HOST-LOADED CONTEXT" : "HOST-LOADED NO-CONTEXT");
    return loaded ? 1 : 0;
}

static (int ExitCode, string Output) RunHostLoaded(string mode, string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add("--host-loaded");
    start.ArgumentList.Add(mode);
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    var stderr = child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout + stderr);
}

static (int ExitCode, string Output) RunChild(string directory, string store)
{
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!)
    {
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    start.ArgumentList.Add(directory);
    start.ArgumentList.Add(store);
    using var child = System.Diagnostics.Process.Start(start) ?? throw new InvalidOperationException();
    var stdout = child.StandardOutput.ReadToEnd();
    child.StandardError.ReadToEnd();
    child.WaitForExit();
    return (child.ExitCode, stdout);
}

static string Hash(string path)
{
    using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
    return Convert.ToHexStringLower(SHA256.HashData(stream));
}

static string HostArchitecture() => RuntimeInformation.ProcessArchitecture switch
{
    Architecture.X64 => "x64",
    Architecture.X86 => "x86",
    Architecture.Arm64 => "arm64",
    Architecture.Arm => "arm",
    _ => "unknown",
};

sealed class SampleEcho : ITrustedUpdateHost
{
    readonly Func<int, int> echo;

    public SampleEcho(Func<int, int> echo) => this.echo = echo;

    public int Echo(int value) => echo(value);
}

sealed class HostApprovalFile
{
    public string? VersionName { get; set; }
    public string? ContentSha256 { get; set; }
    public string? ApprovalId { get; set; }
}

sealed class HostCandidateFile
{
    public string? VersionName { get; set; }
    public string? ContentSha256 { get; set; }
    public string? AssemblyFile { get; set; }
    public string? EntryTypeName { get; set; }
    public string? EntryMethodName { get; set; }
    public string? Runtime { get; set; }
    public string? Architecture { get; set; }
    public List<HostContentFile>? AdditionalFiles { get; set; }
}

sealed class HostContentFile
{
    public string? FileName { get; set; }
    public string? ContentSha256 { get; set; }
}
