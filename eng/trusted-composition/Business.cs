using System.Runtime.CompilerServices;
using TrustedComposition.Contract;

namespace TrustedComposition;

public sealed class UpdateModule : IUpdateModule, IUpdateCallback
{
    private static int count;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public UpdateOutcome Execute(IHostObject host, bool fail)
    {
        ExecutionWitness.Capture("update");
        int current = ++count;
        int value = PrivateLogic.Read();
        int helper = IlOnlyHelper.Compute(value);
        int touched = host.Touch(value);
        int callback = host.Invoke(this, current);
        int delegated = host.InvokeDelegate(Apply, current);
        object genericHost = host.Echo<object>(host);
        int genericValue = host.Echo(helper);
        if (fail)
            throw new UpdateFailureException("ordinary update failure after shared-object callbacks");
        return new(host, genericHost, current, PrivateLogic.Count, value, helper, touched,
            callback, delegated, genericValue, typeof(PrivateLogic).Assembly.GetName().Version!.ToString());
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public int Apply(int value) => value + 19;
}

public sealed class UpdateFailureException(string message) : Exception(message);
