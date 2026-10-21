namespace OrbitGame.Contracts;

public interface IOrbitHost
{
    int Move(int delta);
    int Position { get; }
}

public interface IOrbitRules
{
    int Start(IOrbitHost host);
    int Step(IOrbitHost host);
}
