// Synthetic harness stub. RunEntry.cs references TrustedUpdate.DeliveryHost.Run(), and the
// unit fixture compiles RunEntry.cs without the production host. The real DeliveryHost needs
// the portable bridge, the pinned key and the network, so it is deliberately NOT compiled into
// this fixture. This stub only keeps the fixture compiling and returns a fixed failure code.
namespace TrustedUpdate
{
    public static class DeliveryHost
    {
        public const int StubExitCode = 90;

        public static int Run() => StubExitCode;
    }
}
