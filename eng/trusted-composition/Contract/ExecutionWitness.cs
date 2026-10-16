using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;

namespace TrustedComposition.Contract;

public sealed record NativeWitness(string Label, string Pc, string Image, string AllocationBase, uint Rva, bool Executable);

public static class ExecutionWitness
{
    private static readonly List<NativeWitness> witnesses = [];

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Capture(string label)
    {
        if (Environment.GetEnvironmentVariable("TRUSTED_COMPOSITION_WITNESS") != "1") return;
        if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
            throw new PlatformNotSupportedException("Native witnesses require Windows x64.");
        var frames = new nint[64];
        int count = RtlCaptureStackBackTrace(0, (uint)frames.Length, frames, out _);
        for (int i = 0; i < count; i++)
        {
            nint pc = frames[i];
            if (VirtualQuery(pc, out var memory, (nuint)Marshal.SizeOf<MemoryInformation>()) == 0) continue;
            var name = new StringBuilder(2048);
            if (GetModuleFileNameW(memory.AllocationBase, name, name.Capacity) == 0) continue;
            string image = name.ToString();
            if (!Path.GetFileName(image).StartsWith("TrustedComposition.", StringComparison.Ordinal)) continue;
            long offset = pc - memory.AllocationBase;
            if (offset < 0 || offset > uint.MaxValue) continue;
            // Return PCs inside mapped executable image pages witness active native frames.
            bool executable = (memory.Protect & 0xf0) != 0;
            witnesses.Add(new(label, $"0x{pc:x}", image, $"0x{memory.AllocationBase:x}", (uint)offset, executable));
        }
    }

    public static NativeWitness[] Drain()
    {
        var result = witnesses.ToArray();
        witnesses.Clear();
        return result;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryInformation
    {
        public nint BaseAddress, AllocationBase;
        public uint AllocationProtect;
        public ushort PartitionId;
        public nuint RegionSize;
        public uint State, Protect, Type;
    }

    [DllImport("kernel32.dll")]
    private static extern ushort RtlCaptureStackBackTrace(uint skip, uint capture, [Out] nint[] frames, out uint hash);
    [DllImport("kernel32.dll")]
    private static extern nuint VirtualQuery(nint address, out MemoryInformation information, nuint length);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern uint GetModuleFileNameW(nint module, StringBuilder name, int size);
}
