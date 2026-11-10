internal static class RunStamp {
#if STAMP_B
    internal const string Version = "B";
#else
    internal const string Version = "A";
#endif
    internal const string Nonce = "0123456789abcdef0123456789abcdef";
}