namespace TrustedComposition.Contract;

public interface IHostObject
{
    int Touch(int value);
    int Invoke(IUpdateCallback callback, int value);
    int InvokeDelegate(Func<int, int> callback, int value);
    T Echo<T>(T value);
}

public interface IUpdateCallback
{
    int Apply(int value);
}

public interface IUpdateModule
{
    UpdateOutcome Execute(IHostObject host, bool fail);
}

public sealed record UpdateOutcome(
    IHostObject ReturnedHost, object GenericHost, int StaticCount, int PrivateCount,
    int PrivateValue, int HelperValue, int TouchValue, int InterfaceValue,
    int DelegateValue, int GenericValue, string PrivateVersion);
