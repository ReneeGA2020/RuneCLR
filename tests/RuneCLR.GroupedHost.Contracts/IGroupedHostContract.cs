namespace RuneCLR.GroupedHost.Fixtures;

/// <summary>
/// Host-provided surface used by the grouped-host fixtures. The harness keeps this contract
/// assembly in the default load context; framework and author fixtures only reference this
/// interface (never RuneCLR.Runtime).
/// </summary>
public interface IGroupedHostContract
{
    /// <summary>Host mode string. "normal" keeps fixture behaviour plain.</summary>
    string Mode { get; }

    /// <summary>Records one fixture message on the host side.</summary>
    void Record(string message);

    /// <summary>Registers a host-held external callback root.</summary>
    void Subscribe(Action callback);

    /// <summary>Removes a previously registered host-held callback root.</summary>
    void Unsubscribe(Action callback);

    /// <summary>
    /// Optional managed image bytes the host wants the author to load dynamically into its own
    /// collectible context. Empty by default; the host fills it before Open so the author never reads
    /// files itself.
    /// </summary>
    byte[] DynamicImage { get; }
}
