namespace OrbitBridge;

/// <summary>Host callback object offered to one author call.</summary>
public interface IHost
{
    int Position { get; }

    int Move(int delta);
}

/// <summary>Author module entry. The host only knows this shared interface.</summary>
public interface IRules
{
    int Step(IHost host);
}
