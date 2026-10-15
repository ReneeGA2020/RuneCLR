using System.Reflection;
using System.Runtime.InteropServices;

namespace RuneCLR.Experiments;

internal sealed record EntryObservation(string DefiningType, string Method, string Assembly, string ModuleMvid,
    string MethodDefToken, bool Collectible, bool Interpreted, int PrecodeType, string EntryAddress,
    string CodeAddress, string Bytes, string InvocationEvidence, string Scope);

internal static class WindowsEntryObservation
{
    internal static bool Enabled => Environment.GetEnvironmentVariable("RUNECLR_POST_EXECUTION_PRECODE") == "1";

    internal static EntryObservation Capture(MethodBase method, bool expectedInterpreted, string invocationEvidence)
    {
        if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
            throw new PlatformNotSupportedException("Pinned observer requires Windows x64.");
        // The caller supplies a completed invocation/counter before inspecting its precode.
        // GetFunctionPointer alone is preparation and supplies no invocation evidence.
        nint entry = method.MethodHandle.GetFunctionPointer(), code = entry;
        if (Marshal.ReadByte(entry) == 0xff && Marshal.ReadByte(entry, 1) == 0x25)
            code = Marshal.ReadIntPtr(entry + 6 + Marshal.ReadInt32(entry, 2));
        bool stub = Marshal.ReadByte(code) == 0x4c && Marshal.ReadByte(code, 1) == 0x8b &&
            Marshal.ReadByte(code, 2) == 0x15 && Marshal.ReadByte(code, 7) == 0xff &&
            Marshal.ReadByte(code, 8) == 0x25;
        int kind = stub ? Marshal.ReadByte(code + 7 + Marshal.ReadInt32(code, 3) + 16) : -1;
        bool interpreted = stub && kind == 6;
        if (interpreted != expectedInterpreted)
            throw new InvalidOperationException("Post-invocation interpreter precode differs: " + method);
        var bytes = new byte[16];
        Marshal.Copy(code, bytes, 0, bytes.Length);
        return new(method.DeclaringType!.FullName!, method.Name, method.Module.Assembly.GetName().Name!,
            method.Module.ModuleVersionId.ToString(), $"0x{method.MetadataToken:x8}", method.Module.Assembly.IsCollectible,
            interpreted, kind, $"0x{entry:x}", $"0x{code:x}", Convert.ToHexString(bytes), invocationEvidence,
            "Post-invocation selected entry; no complete invocation or child-dispatch coverage");
    }
}
