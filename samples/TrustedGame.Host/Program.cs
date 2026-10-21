using System.Runtime.InteropServices;
using RuneCLR.TrustedUpdate;
using TrustedGame.Contracts;

const string VersionName = "game-rules-1";
const string EntryTypeName = "TrustedGame.Update.GameRules";
const string EntryMethodName = "Entry";
const string LocalApprovalId = "local-trusted-build";
const string HostRuntime = "net11.0";

return Dispatch(args);

static int Dispatch(string[] args)
{
    if (args.Length == 0)
        return Usage();
    if (string.Equals(args[0], "--module", StringComparison.Ordinal))
        return RunLocal(args);
    if (string.Equals(args[0], "--stage-signed", StringComparison.Ordinal))
        return RunSignedStage(args);
    if (string.Equals(args[0], "--recover-signed", StringComparison.Ordinal))
        return RunSignedRecover(args);
    return Usage();
}

static int RunLocal(string[] args)
{
    if (args.Length != 6
        || !string.Equals(args[0], "--module", StringComparison.Ordinal)
        || !string.Equals(args[2], "--sha256", StringComparison.Ordinal)
        || !string.Equals(args[4], "--approval", StringComparison.Ordinal))
        return Usage();

    string modulePath;
    try
    {
        modulePath = Path.GetFullPath(args[1]);
    }
    catch (Exception)
    {
        Console.Error.WriteLine("TRUSTED-GAME START FAILED invalid-module-path");
        return 2;
    }

    var expectedSha256 = args[3];
    if (!File.Exists(modulePath))
    {
        Console.Error.WriteLine("TRUSTED-GAME START FAILED module-missing");
        return 2;
    }
    if (!IsSha256(expectedSha256))
    {
        Console.Error.WriteLine("TRUSTED-GAME START FAILED invalid-sha256");
        return 2;
    }
    if (!string.Equals(args[5], LocalApprovalId, StringComparison.Ordinal))
    {
        Console.Error.WriteLine("TRUSTED-GAME START FAILED approval-not-local-build-pipeline");
        return 2;
    }

    var activation = new SampleActivation(allowLastKnownGood: false);
    var hostTarget = HostTarget();
    var candidate = new TrustedUpdateCandidate(
        VersionName, expectedSha256, modulePath, EntryTypeName, EntryMethodName, hostTarget);
    var approval = new TrustedUpdateApproval(VersionName, expectedSha256, LocalApprovalId);
    var contentRoot = Path.GetDirectoryName(modulePath)!;
    try
    {
        var started = new TrustedUpdateProcess().TryStartHostLoaded(
            candidate,
            hostTarget,
            lastKnownGoodPath: null,
            approval,
            contentRoot,
            fallbackApproval: null,
            fallbackContentRoot: null,
            requiredVersion: VersionName,
            activation.Activate);

        if (!started.Succeeded || activation.Session is null || activation.RulesType is null)
        {
            Console.Error.WriteLine($"TRUSTED-GAME START FAILED {started.Failure} candidate={started.CandidateFailure}");
            activation.Session?.Dispose();
            return 3;
        }
        if (started.Source != TrustedUpdateStartSource.Candidate || started.CandidateFailure != TrustedUpdateFailure.None)
        {
            Console.Error.WriteLine($"TRUSTED-GAME START FAILED source={started.Source} candidate={started.CandidateFailure}");
            activation.Session.Dispose();
            return 3;
        }
        return RunGameplay(activation, expectedScoreMultiplier: 1);
    }
    catch (Exception error)
    {
        activation.Session?.Dispose();
        Console.Error.WriteLine("TRUSTED-GAME FAILED " + error.GetType().Name + ": " + error.Message);
        return 1;
    }
}

static int RunSignedStage(string[] args)
{
    if (args.Length is not (10 or 12)
        || !string.Equals(args[0], "--stage-signed", StringComparison.Ordinal)
        || !string.Equals(args[2], "--signed", StringComparison.Ordinal)
        || !string.Equals(args[4], "--spki", StringComparison.Ordinal)
        || !string.Equals(args[6], "--releases-root", StringComparison.Ordinal)
        || !string.Equals(args[8], "--receipt", StringComparison.Ordinal))
        return Usage();
    var expectedScoreMultiplier = 1;
    if (args.Length == 12
        && (!string.Equals(args[10], "--expected-score-multiplier", StringComparison.Ordinal)
            || !TryScoreMultiplier(args[11], out expectedScoreMultiplier)))
        return Usage();

    try
    {
        var sourceRoot = Path.GetFullPath(args[1]);
        if (!Directory.Exists(sourceRoot))
        {
            Console.Error.WriteLine("SIGNED-STAGE REJECTED source-missing");
            return 2;
        }
        if (!TryReadBounded(args[3], TrustedRelease.MaxDocumentBytes, out var signed, out var signedDetail))
        {
            Console.Error.WriteLine("SIGNED-STAGE REJECTED signed-" + signedDetail);
            return 2;
        }
        if (!TryReadExact(args[5], TrustedRelease.SpkiBytes, out var spki, out var spkiDetail))
        {
            Console.Error.WriteLine("SIGNED-STAGE REJECTED spki-" + spkiDetail);
            return 2;
        }

        var releasesRoot = Path.GetFullPath(args[7]);
        var receiptPath = Path.GetFullPath(args[9]);
        Directory.CreateDirectory(releasesRoot);
        var receiptDirectory = Path.GetDirectoryName(receiptPath);
        if (string.IsNullOrEmpty(receiptDirectory))
        {
            Console.Error.WriteLine("SIGNED-STAGE REJECTED receipt-path");
            return 2;
        }
        Directory.CreateDirectory(receiptDirectory);

        var activation = new SampleActivation(allowLastKnownGood: true);
        var verified = TrustedRelease.Verify(sourceRoot, signed, spki);
        TrustedReleaseRecoveryStart start;
        string stageStatus;
        string stageDetail;
        if (!verified.Succeeded || verified.Candidate is null || verified.Approval is null)
        {
            stageStatus = "VerificationFailed";
            stageDetail = verified.Failure + "/" + verified.Detail;
            start = Recover(null, spki, releasesRoot, receiptPath, activation);
        }
        else
        {
            try
            {
                var sources = BuildSources(sourceRoot, verified.Candidate);
                var finalDirectory = Path.Combine(releasesRoot,
                    verified.Candidate.VersionName + "-" + Guid.NewGuid().ToString("n"));
                var staged = TrustedReleaseStaging.PublishAsync(finalDirectory, signed, spki, sources)
                    .GetAwaiter().GetResult();
                if (!staged.Succeeded || staged.FinalDirectory is null)
                {
                    stageStatus = staged.Failure.ToString();
                    stageDetail = staged.Detail;
                    start = Recover(null, spki, releasesRoot, receiptPath, activation);
                }
                else
                {
                    stageStatus = "OK";
                    stageDetail = "";
                    start = Recover(new TrustedReleaseOffer(staged.FinalDirectory, signed),
                        spki, releasesRoot, receiptPath, activation);
                }
            }
            catch (Exception error)
            {
                stageStatus = "StageException";
                stageDetail = error.GetType().Name;
                start = Recover(null, spki, releasesRoot, receiptPath, activation);
            }
        }

        return Report("stage", stageStatus, stageDetail, start, activation, expectedScoreMultiplier);
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("SIGNED-STAGE FAILED " + error.GetType().Name + ": " + error.Message);
        return 1;
    }
}

static int RunSignedRecover(string[] args)
{
    if (args.Length is not (7 or 9)
        || !string.Equals(args[0], "--recover-signed", StringComparison.Ordinal)
        || !string.Equals(args[1], "--spki", StringComparison.Ordinal)
        || !string.Equals(args[3], "--releases-root", StringComparison.Ordinal)
        || !string.Equals(args[5], "--receipt", StringComparison.Ordinal))
        return Usage();
    var expectedScoreMultiplier = 1;
    if (args.Length == 9
        && (!string.Equals(args[7], "--expected-score-multiplier", StringComparison.Ordinal)
            || !TryScoreMultiplier(args[8], out expectedScoreMultiplier)))
        return Usage();

    try
    {
        if (!TryReadExact(args[2], TrustedRelease.SpkiBytes, out var spki, out var spkiDetail))
        {
            Console.Error.WriteLine("SIGNED-RECOVER REJECTED spki-" + spkiDetail);
            return 2;
        }
        var releasesRoot = Path.GetFullPath(args[4]);
        var receiptPath = Path.GetFullPath(args[6]);
        Directory.CreateDirectory(releasesRoot);
        var receiptDirectory = Path.GetDirectoryName(receiptPath);
        if (string.IsNullOrEmpty(receiptDirectory))
        {
            Console.Error.WriteLine("SIGNED-RECOVER REJECTED receipt-path");
            return 2;
        }
        Directory.CreateDirectory(receiptDirectory);

        var activation = new SampleActivation(allowLastKnownGood: true);
        var start = Recover(null, spki, releasesRoot, receiptPath, activation);
        return Report("recover", "NA", "", start, activation, expectedScoreMultiplier);
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("SIGNED-RECOVER FAILED " + error.GetType().Name + ": " + error.Message);
        return 1;
    }
}

static TrustedReleaseRecoveryStart Recover(TrustedReleaseOffer? offer, byte[] spki, string releasesRoot,
    string receiptPath, SampleActivation activation) =>
    TrustedReleaseRecovery.TryStart(offer, spki, HostTarget(), releasesRoot, receiptPath, activation.Activate);

static List<TrustedReleaseStageSource> BuildSources(string sourceRoot, TrustedUpdateCandidate candidate)
{
    var result = new List<TrustedReleaseStageSource>();
    Add(candidate.AssemblyPath);
    if (candidate.AdditionalContent is not null)
    {
        foreach (var file in candidate.AdditionalContent)
            Add(file.Path);
    }
    return result;

    void Add(string fullPath)
    {
        var relative = Path.GetRelativePath(sourceRoot, fullPath).Replace('\\', '/');
        if (relative == ".." || relative.StartsWith("../", StringComparison.Ordinal) || Path.IsPathRooted(relative))
            throw new InvalidOperationException("signed source path is outside its content root");
        var full = Path.GetFullPath(fullPath);
        result.Add(new TrustedReleaseStageSource(relative,
            _ => new ValueTask<Stream>(File.OpenRead(full))));
    }
}

static int Report(string mode, string stage, string stageDetail, TrustedReleaseRecoveryStart start,
    SampleActivation activation, int expectedScoreMultiplier)
{
    Console.WriteLine("SIGNED-FACTS mode=" + mode
        + " stage=" + stage
        + " stageDetail=" + stageDetail
        + " expectedScoreMultiplier=" + expectedScoreMultiplier
        + " candidateVerification=" + start.Candidate.Verification
        + " candidatePlan=" + start.Candidate.Plan
        + " candidateActivation=" + start.Candidate.Activation
        + " recoveryVerification=" + start.Recovery.Verification
        + " recoveryPlan=" + start.Recovery.Plan
        + " recoveryActivation=" + start.Recovery.Activation
        + " persistence=" + start.Persistence
        + " persistenceDetail=" + start.PersistenceDetail
        + " activated=" + start.Activated
        + " source=" + start.Source
        + " version=" + (start.SelectedVersion ?? "-")
        + " activatorCalls=" + activation.ActivatorCalls);

    if (!start.Activated)
        return 3;
    var gameplay = RunGameplay(activation, expectedScoreMultiplier);
    if (gameplay != 0)
        return 1;
    return start.Persistence == TrustedReleasePersistenceFailure.None ? 0 : 5;
}

static int RunGameplay(SampleActivation activation, int expectedScoreMultiplier)
{
    try
    {
        Gameplay.Run(activation.Session!, activation.RulesType!, expectedScoreMultiplier);
        Console.WriteLine("TRUSTED-GAME OK");
        return 0;
    }
    catch (Exception error)
    {
        Console.Error.WriteLine("TRUSTED-GAME FAILED " + error.GetType().Name + ": " + error.Message);
        return 1;
    }
}

static bool TryReadBounded(string path, int limit, out byte[] bytes, out string detail)
{
    bytes = Array.Empty<byte>();
    try
    {
        var info = new FileInfo(path);
        if (!info.Exists)
        {
            detail = "missing";
            return false;
        }
        if (info.Length > limit)
        {
            detail = "size";
            return false;
        }
        bytes = File.ReadAllBytes(path);
        detail = "";
        return true;
    }
    catch (Exception)
    {
        detail = "io";
        return false;
    }
}

static bool TryReadExact(string path, int length, out byte[] bytes, out string detail)
{
    bytes = Array.Empty<byte>();
    try
    {
        var info = new FileInfo(path);
        if (!info.Exists)
        {
            detail = "missing";
            return false;
        }
        if (info.Length != length)
        {
            detail = "size";
            return false;
        }
        bytes = File.ReadAllBytes(path);
        detail = "";
        return true;
    }
    catch (Exception)
    {
        detail = "io";
        return false;
    }
}

static TrustedUpdateTarget HostTarget() => new(HostRuntime, HostArchitecture());

static string HostArchitecture() => RuntimeInformation.ProcessArchitecture switch
{
    Architecture.X64 => "x64",
    Architecture.X86 => "x86",
    Architecture.Arm64 => "arm64",
    Architecture.Arm => "arm",
    _ => "unknown",
};

static bool TryScoreMultiplier(string text, out int value)
{
    if (string.Equals(text, "1", StringComparison.Ordinal))
    {
        value = 1;
        return true;
    }
    if (string.Equals(text, "2", StringComparison.Ordinal))
    {
        value = 2;
        return true;
    }
    value = 1;
    return false;
}

static bool IsSha256(string value)
{
    if (value.Length != 64)
        return false;
    foreach (var item in value)
    {
        if (!Uri.IsHexDigit(item))
            return false;
    }
    return true;
}

static int Usage()
{
    Console.Error.WriteLine("usage: TrustedGame.Host --module <module.dll> --sha256 <64-hex> --approval local-trusted-build");
    Console.Error.WriteLine("   or: TrustedGame.Host --stage-signed <source-dir> --signed <release.signed.json> --spki <host.spki> --releases-root <dir> --receipt <receipt.json>");
    Console.Error.WriteLine("   or: TrustedGame.Host --recover-signed --spki <host.spki> --releases-root <dir> --receipt <receipt.json>");
    return 2;
}
