using TrustedComposition.Contract;

namespace TrustedComposition;

public sealed class UpdateModule : IUpdateModule
{
    public UpdateOutcome Execute(IHostObject host, bool fail)
    {
        var seen = DeliveryAppDep.Marker.Touch();
        return new UpdateOutcome(host, host, 0, 0, seen == "loaded" ? 1 : 0, 0, 0, 0, 0, 0, "0.0.0.0");
    }
}
