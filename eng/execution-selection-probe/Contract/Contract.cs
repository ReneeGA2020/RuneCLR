namespace SelectionProbe.Contract;

public interface IProbe { ProbeResult Run(); }
public interface IBoxProbe { int Read(); int Starts { get; } int Instances { get; } }
public interface IStaticProbe { static abstract int ReadInline(int value); }

public readonly record struct ProbeResult(int PayloadStatic, int PayloadConstructor, int Property,
    int Inlined, int GenericStatic, int GenericMethod, int Delegate, int Virtual, int DefaultInterface,
    int Filter, int PrivateStatic, int PrivateConstructor, int PrivateProperty, int PrivateInline,
    int PrivateGenericStatic, int PrivateGenericMethod, int PrivateDelegate);
