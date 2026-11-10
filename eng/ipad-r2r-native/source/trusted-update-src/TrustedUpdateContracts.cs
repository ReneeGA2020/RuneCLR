using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;

namespace RuneCLR.TrustedUpdate;

/// <summary>
/// One business version offered at process startup. The content hash is the
/// file identity; it is not an approval or signature.
/// </summary>
public sealed record TrustedUpdateCandidate(
    string VersionName,
    string ContentSha256,
    string AssemblyPath,
    string EntryTypeName,
    string EntryMethodName,
    TrustedUpdateTarget Target,
    IReadOnlyList<TrustedUpdateContentFile>? AdditionalContent = null);

/// <summary>
/// One extra file that must match its hash before the entry assembly loads.
/// This is file identity, not an approval or signature, and the selector does not load it.
/// </summary>
public sealed record TrustedUpdateContentFile(string Path, string ContentSha256);

/// <summary>
/// Host and candidate runtime/architecture pair. Comparison is exact and ordinal.
/// </summary>
public readonly record struct TrustedUpdateTarget(string Runtime, string Architecture);

/// <summary>
/// Host decision that a version's content hash may be activated.
/// This is an approval record, not a signature, and it is not checked with cryptography.
/// </summary>
public sealed record TrustedUpdateApproval(
    string VersionName,
    string ContentSha256,
    string ApprovalId);

/// <summary>
/// Host object offered to the selected update for one Tick call.
/// The process does not store it, and calls fail after that Tick returns.
/// </summary>
public interface ITrustedUpdateHost
{
    int Echo(int value);
}

/// <summary>
/// Event source offered to one update call. Subscribers are dropped when that
/// call returns. A later add, remove, or raise throws and does not attach a
/// handler. This object is not stored by the selector.
/// </summary>
public interface ITrustedUpdateSignals
{
    event Action<int> Signal;

    void Raise(int value);
}

/// <summary>
/// Primitive work offered to one update call. The process keeps ids and ints,
/// not delegates or exceptions. Request and take fail after that call returns,
/// including during a later call.
/// </summary>
public interface ITrustedUpdateWork
{
    long Request(string name);

    bool TryTake(out long id, out int value, out bool succeeded);
}

public readonly record struct TrustedUpdateWorkInfo(long Id, string Name);

public enum TrustedUpdateFailure
{
    None = 0,
    InvalidCandidate,
    MissingContent,
    ContentHashMismatch,
    IncompatibleTarget,
    NotApproved,
    ActivationFailed,
    ProcessSelectionLocked,
    NoLastKnownGood,
    LastKnownGoodUnusable,
    SessionNotOpen,
    OutsideContentRoot,
}

public enum TrustedUpdateStartSource
{
    None = 0,
    Candidate,
    LastKnownGood,
}

/// <summary>
/// One process start. CandidateFailure is the update that was not used.
/// Failure is None only when a version was selected. Activation failure does
/// not fall back in the same process.
/// </summary>
public readonly record struct TrustedUpdateStartup(
    TrustedUpdateFailure Failure,
    TrustedUpdateFailure CandidateFailure,
    string? SelectedVersionName,
    TrustedUpdateStartSource Source)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

/// <summary>
/// Host-owned activation of a candidate the selector has already planned.
/// The selector does not load the assembly or retain the exception.
/// </summary>
public readonly record struct TrustedUpdateActivation(TrustedUpdateFailure Failure, int Value)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

public delegate TrustedUpdateActivation TrustedUpdateActivator(
    TrustedUpdateCandidate candidate,
    TrustedUpdateStartSource source,
    TrustedUpdateFailure candidateFailure);

/// <summary>
/// One host-loaded start. Value comes from the activator and is meaningful
/// only when Failure is None. Calling the activator occupies the process.
/// If it fails or throws, the process stays occupied, the last known good
/// record is not replaced, and this process does not fall back.
/// </summary>
public readonly record struct TrustedUpdateHostStart(
    TrustedUpdateFailure Failure,
    TrustedUpdateFailure CandidateFailure,
    string? SelectedVersionName,
    TrustedUpdateStartSource Source,
    int Value)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

/// <summary>
/// Host-owned selection result. It never carries an update exception, assembly,
/// or other update object.
/// </summary>
public readonly record struct TrustedUpdateResult(TrustedUpdateFailure Failure, string? SelectedVersionName)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

/// <summary>
/// Process-lifetime fact for a selected trusted update. Native code stays
/// resident until the process exits. This host does not unload it or switch
/// versions in-process.
/// </summary>

/// <summary>
/// Host-owned call result. Value is meaningful only when Failure is None.
/// The update exception is not retained.
/// </summary>
public readonly record struct TrustedUpdateCallResult(TrustedUpdateFailure Failure, int Value)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

/// <summary>
/// Whether one host object came back as the same reference. The result does not
/// retain the object or any update instance.
/// </summary>
public readonly record struct TrustedUpdateIdentityResult(TrustedUpdateFailure Failure, bool SameReference)
{
    public bool Succeeded => Failure == TrustedUpdateFailure.None;
}

public readonly record struct TrustedUpdateResidency(
    string VersionName,
    bool ResidentUntilProcessExit,
    bool UnloadSupported,
    bool SameProcessSwitchSupported);

/// <summary>
/// A host-owned session for the selected update. Closing it releases only the
/// session. The selected module remains resident until the process exits.
/// </summary>
public sealed class TrustedUpdateSession
{
    internal TrustedUpdateSession(string versionName) => VersionName = versionName;

    public string VersionName { get; }

    public bool Closed { get; private set; }

    public void Close()
    {
        Closed = true;
    }
}


public sealed class TrustedUpdateMutableBox
{
    public int Value { get; set; }
}