using RuneCLR.TrustedUpdate;
using TrustedComposition.Contract;

readonly struct SessionCall
{
    public SessionCall(bool completed, int value, string failure)
    {
        Completed = completed;
        Value = value;
        Failure = failure;
    }

    public bool Completed { get; }
    public int Value { get; }
    public string Failure { get; }
}

sealed class TypedSession<TModule> where TModule : class
{
    readonly TrustedModuleSession<TModule> session;

    public TypedSession(TModule module)
    {
        ArgumentNullException.ThrowIfNull(module);
        session = new TrustedModuleSession<TModule>(module);
    }

    public bool IsClosed => session.IsClosed;

    public SessionCall Invoke(Func<TModule, int> call)
    {
        if (call is null)
            return new SessionCall(false, 0, "invalid");

        var result = session.Invoke(call);
        var failure = result.Failure switch
        {
            TrustedModuleCallFailure.None => "",
            TrustedModuleCallFailure.Closed => "closed",
            TrustedModuleCallFailure.ReentrantCall => "reentered",
            TrustedModuleCallFailure.CallbackFailed => "author-failed",
            _ => "author-failed",
        };
        return new SessionCall(result.Succeeded, result.Value, failure);
    }

    public void Close() => session.Close();
}