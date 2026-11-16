using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.ExceptionServices;
using RuneCLR.Compiler;
using RuneCLR.Packages;

/// <summary>
/// Group-only managed-delegate capability regressions. The stock test compiler produces the images;
/// the legacy public profile must keep rejecting them while the internal grouped route admits only
/// metadata-proven delegate construction whose native-int argument comes from ldftn/ldvirtftn.
/// Patched images are inspected only; nothing here loads or executes them.
/// </summary>
internal static class GroupedDelegateCapabilityCases
{
    private static readonly string Contract = typeof(RuneCLR.IMapScript).Assembly.FullName!;

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Grouped route admits static and instance Action construction; legacy route rejects the same bytes", ActionConstruction);
        yield return ("Grouped route admits Action<T> and Func<T> constructions; legacy route rejects the same bytes", GenericDelegateConstruction);
        yield return ("Grouped route rejects IntPtr field and return signatures", NativeIntSignatures);
        yield return ("Grouped route rejects an Action-like constructor that does not derive MulticastDelegate", FakeDelegateConstructor);
        yield return ("Grouped route rejects a delegate constructor token used by call instead of newobj", ConstructorTokenOutsideNewobj);
        yield return ("Grouped route rejects conv.i in place of the ldftn delegate target", ConvIProducer);
        yield return ("Grouped route rejects delegate construction reached by a short branch", BranchTargetAtDelegateConstruction);
        yield return ("Grouped route rejects delegate construction reached by a switch target", SwitchTargetAtDelegateConstruction);
        yield return ("Grouped route rejects delegate construction on an exception-region boundary", ExceptionBoundaryAtDelegateConstruction);
        yield return ("Author P/Invoke is rejected by structural intake before the delegate route", PInvokeLayering);
        yield return ("Grouped route denies a delegate to a BCL method outside the supplied policy", DeniedDelegateTarget);
    }

    // --- fixtures (raw Roslyn output, never routed through the legacy capability gate) ---

    private const string StaticAction = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Action Make() => new System.Action(Target);
            private static void Target() { }
        }
        """;

    private const string InstanceAction = """
        namespace Fixture;
        public sealed class Probe
        {
            public System.Action Make() => new System.Action(Run);
            public void Run() { }
        }
        """;

    private const string BranchAction = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Action Make(bool flag) => flag ? new System.Action(Target) : null;
            private static void Target() { }
        }
        """;

    private const string SwitchAction = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Action Make(int value)
            {
                switch (value)
                {
                    case 0: return new System.Action(Target);
                    case 1: return new System.Action(Target);
                    case 2: return new System.Action(Target);
                    case 3: return new System.Action(Target);
                    case 4: return new System.Action(Target);
                    case 5: return new System.Action(Target);
                    default: return null;
                }
            }
            private static void Target() { }
        }
        """;

    private const string ExceptionAction = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Action Make()
            {
                try { return new System.Action(Target); }
                catch (System.Exception) { return null; }
            }
            private static void Target() { }
        }
        """;

    private const string GenericActionStatic = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Action<int> Make() => new System.Action<int>(Target);
            private static void Target(int value) { }
        }
        """;

    private const string GenericActionInstance = """
        namespace Fixture;
        public sealed class Probe
        {
            public System.Action<int> Make() => new System.Action<int>(Run);
            public void Run(int value) { }
        }
        """;

    private const string GenericFuncStatic = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Func<int, int> Make() => new System.Func<int, int>(Square);
            private static int Square(int value) => value;
        }
        """;

    private const string GenericFuncInstance = """
        namespace Fixture;
        public sealed class Probe
        {
            public System.Func<int> Make() => new System.Func<int>(Get);
            public int Get() => 1;
        }
        """;

    private const string NativeIntSource = """
        namespace Fixture;
        public static class Probe
        {
            public static System.IntPtr Value;
            public static System.IntPtr Echo(System.IntPtr input) => input;
        }
        """;

    private const string FakeDelegateSource = """
        namespace Fixture;
        public sealed class FakeAction
        {
            public FakeAction(object target, System.IntPtr pointer) { }
        }
        """;

    private const string PInvokeSource = """
        namespace Fixture;
        public static class Probe
        {
            [System.Runtime.InteropServices.DllImport("kernel32.dll")]
            private static extern int GetCurrentThreadId();
            public static int Call() => GetCurrentThreadId();
        }
        """;

    private const string DeniedTargetSource = """
        namespace Fixture;
        public static class Probe
        {
            public static System.Func<string> Factory = new System.Func<string>(System.IO.Path.GetTempPath);
        }
        """;

    // --- cases ---

    private static void ActionConstruction()
    {
        foreach (var source in new[] { StaticAction, InstanceAction })
            AssertAdmittedButLegacyRejected(Compile("AuthorActionProbe", source));
    }

    private static void GenericDelegateConstruction()
    {
        foreach (var source in new[] { GenericActionStatic, GenericActionInstance, GenericFuncStatic, GenericFuncInstance })
            AssertAdmittedButLegacyRejected(Compile("AuthorGenericDelegateProbe", source));
    }

    private static void AssertAdmittedButLegacyRejected(byte[] image)
    {
        var identity = IdentityOf(image);
        ValidateGrouped(image, identity);
        var legacy = Check.Throws<InvalidDataException>(() => ValidateLegacy(image, identity));
        Check.Assert(legacy.Message.Contains("IntPtr", StringComparison.Ordinal) ||
            legacy.Message.Contains("native signature", StringComparison.OrdinalIgnoreCase),
            "The legacy profile must keep rejecting the delegate constructor's native int: " + legacy.Message);
    }

    private static void NativeIntSignatures()
    {
        var image = Compile("AuthorNativeIntProbe", NativeIntSource);
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(image, IdentityOf(image)));
        Check.Assert(error.Message.Contains("IntPtr", StringComparison.Ordinal),
            "IntPtr outside a delegate constructor must stay rejected: " + error.Message);
    }

    private static void FakeDelegateConstructor()
    {
        var image = Compile("AuthorFakeDelegateProbe", FakeDelegateSource);
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(image, IdentityOf(image)));
        Check.Assert(error.Message.Contains("IntPtr", StringComparison.Ordinal),
            "An Action-like constructor that does not derive MulticastDelegate must stay rejected: " + error.Message);
    }

    private static void ConstructorTokenOutsideNewobj()
    {
        var image = Compile("AuthorCallTokenProbe", StaticAction);
        ValidateGrouped(image, IdentityOf(image));
        var site = LocateDelegateSite(image);
        Check.Assert(site.Newobj.Size == 5, "The fixture newobj is not a five-byte instruction.");
        var patched = PatchIl(image, site, (il, instructions) =>
        {
            var newobj = instructions[site.NewobjIndex];
            il[newobj.Offset] = 0x28; // call <delegate ctor token>
        });
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(patched, IdentityOf(patched)));
        Check.Assert(error.Message.Contains("only newobj is allowed", StringComparison.Ordinal),
            "A delegate constructor token used outside newobj must be rejected by the delegate guard: " + error.Message);
    }

    private static void ConvIProducer()
    {
        var image = Compile("AuthorConvIProbe", StaticAction);
        var site = LocateDelegateSite(image);
        Check.Assert(site.Ldftn.Size == 6, "The fixture ldftn is not a six-byte instruction.");
        var patched = PatchIl(image, site, (il, instructions) =>
        {
            var ldftn = instructions[site.LdftnIndex];
            il[ldftn.Offset] = 0x1F; il[ldftn.Offset + 1] = 0x01; // ldc.i4.s 1
            il[ldftn.Offset + 2] = 0x00; il[ldftn.Offset + 3] = 0x00; il[ldftn.Offset + 4] = 0x00; // nop x3
            il[ldftn.Offset + 5] = 0xD3; // conv.i
        });
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(patched, IdentityOf(patched)));
        Check.Assert(error.Message.Contains("not directly preceded by ldftn/ldvirtftn", StringComparison.Ordinal),
            "A conv.i producer must not stand in for the delegate target: " + error.Message);
    }

    private static void BranchTargetAtDelegateConstruction()
    {
        var image = Compile("AuthorBranchProbe", BranchAction);
        ValidateGrouped(image, IdentityOf(image));
        var site = LocateDelegateSite(image);
        Check.Assert(site.LdftnIndex + 1 == site.NewobjIndex && site.Ldftn.End == site.NewobjOffset,
            "The untouched fixture must keep ldftn directly before newobj.");
        Check.Assert(!BranchTargets(site.Il, site.Instructions).Contains(site.NewobjOffset),
            "The untouched branch fixture must not already target newobj.");

        Instruction? branch = null;
        foreach (var instruction in site.Instructions)
        {
            if (instruction.Offset >= site.LdftnOffset) break;
            if (instruction.Value is >= 0x2B and <= 0x37 && instruction.Size == 2) { branch = instruction; break; }
        }
        if (branch is not Instruction chosen)
            throw new InvalidOperationException("The branch fixture has no short branch before ldftn.");
        var patched = PatchIl(image, site, (il, _) =>
        {
            var delta = site.NewobjOffset - chosen.End;
            Check.Assert(delta is >= sbyte.MinValue and <= sbyte.MaxValue, "The short-branch delta does not fit.");
            il[chosen.Offset + 1] = (byte)(sbyte)delta;
        });
        var patchedSite = LocateDelegateSite(patched);
        Check.Assert(patchedSite.LdftnIndex + 1 == patchedSite.NewobjIndex && patchedSite.Ldftn.End == patchedSite.NewobjOffset,
            "The patched image must keep ldftn directly before newobj.");
        Check.Assert(BranchTargets(patchedSite.Il, patchedSite.Instructions).Contains(patchedSite.NewobjOffset),
            "The patch must make newobj an actual branch target.");
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(patched, IdentityOf(patched)));
        Check.Assert(error.Message.Contains("branch/switch target", StringComparison.Ordinal),
            "A branch into a delegate newobj must be rejected by the branch-target rule: " + error.Message);
        Check.Assert(!error.Message.Contains("not directly preceded", StringComparison.Ordinal),
            "The branch rejection must not be attributed to producer adjacency: " + error.Message);
    }

    private static void SwitchTargetAtDelegateConstruction()
    {
        var image = Compile("AuthorSwitchProbe", SwitchAction);
        ValidateGrouped(image, IdentityOf(image));
        var site = LocateDelegateSite(image);
        Instruction? switchInstruction = null;
        foreach (var instruction in site.Instructions)
            if (instruction.Value == 0x45) { switchInstruction = instruction; break; }
        if (switchInstruction is not Instruction chosen)
            throw new InvalidOperationException("The switch fixture has no switch opcode.");
        Check.Assert(!BranchTargets(site.Il, site.Instructions).Contains(site.NewobjOffset),
            "The untouched switch fixture must not already target newobj.");

        var patched = PatchIl(image, site, (il, _) =>
        {
            var delta = site.NewobjOffset - chosen.End;
            BinaryPrimitives.WriteInt32LittleEndian(il.AsSpan(chosen.OperandOffset + 4, 4), delta);
        });
        var patchedSite = LocateDelegateSite(patched);
        Check.Assert(BranchTargets(patchedSite.Il, patchedSite.Instructions).Contains(patchedSite.NewobjOffset),
            "The patch must make newobj an actual switch target.");
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(patched, IdentityOf(patched)));
        Check.Assert(error.Message.Contains("branch/switch target", StringComparison.Ordinal),
            "A switch into a delegate newobj must be rejected by the branch/switch rule: " + error.Message);
    }

    private static void ExceptionBoundaryAtDelegateConstruction()
    {
        var image = Compile("AuthorExceptionProbe", ExceptionAction);
        ValidateGrouped(image, IdentityOf(image));
        var patched = PatchCatchClauseToNewobj(image);
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(patched, IdentityOf(patched)));
        Check.Assert(error.Message.Contains("exception-region boundary", StringComparison.Ordinal),
            "A delegate newobj on an exception-region boundary must be rejected by the EH rule: " + error.Message);
    }

    private static void PInvokeLayering()
    {
        // Structural intake is the P/Invoke gate: mutate a managed method to PinvokeImpl and
        // assert that ManagedAssemblyInspector rejects it. The delegate capability route is not
        // reached and is not credited with this decision.
        var image = Compile("AuthorPInvokeProbe", StaticAction);
        var mutated = MutateMethod(image, (bytes, offset, method) =>
            BinaryPrimitives.WriteUInt16LittleEndian(bytes.AsSpan(offset + 6, 2),
                (ushort)(method.Attributes | MethodAttributes.PinvokeImpl)));
        var intake = Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.Inspect(mutated));
        Check.Assert(intake.Message.Contains("P/Invoke", StringComparison.Ordinal),
            "Author P/Invoke must be rejected by structural intake itself: " + intake.Message);
    }

    private static void DeniedDelegateTarget()
    {
        var image = Compile("AuthorDeniedTargetProbe", DeniedTargetSource);
        var error = Check.Throws<InvalidDataException>(() => ValidateGrouped(image, IdentityOf(image)));
        Check.Assert(error.Message.Contains("System.IO.Path", StringComparison.Ordinal),
            "A delegate to a BCL method outside the policy must be denied through the member reference: " + error.Message);
    }

    // --- helpers ---

    private static byte[] Compile(string name, string source, params string[] extraReferences)
    {
        var references = CompilerFixture.ApprovedReferences().Concat(extraReferences).ToArray();
        var compiled = SourceCompiler.Compile(name, [new SourceFile("Probe.cs", source)], references);
        Check.Assert(compiled.Succeeded, name + ": " + string.Join("; ", compiled.Diagnostics.Select(diagnostic => diagnostic.Message)));
        return compiled.Assembly!;
    }

    private static byte[] MutateMethod(byte[] image, Action<byte[], int, MethodDefinition> edit)
    {
        using var stream = new MemoryStream(image, writable: false);
        using var pe = new PEReader(stream);
        var metadata = pe.GetMetadataReader();
        var handle = metadata.MethodDefinitions.First(candidate =>
            metadata.GetMethodDefinition(candidate).RelativeVirtualAddress != 0);
        var offset = pe.PEHeaders.MetadataStartOffset + metadata.GetTableMetadataOffset(TableIndex.MethodDef) +
            (MetadataTokens.GetRowNumber(handle) - 1) * metadata.GetTableRowSize(TableIndex.MethodDef);
        var copy = (byte[])image.Clone();
        edit(copy, offset, metadata.GetMethodDefinition(handle));
        return copy;
    }

    private static string IdentityOf(byte[] image) => ManagedAssemblyInspector.Inspect(image).AssemblyName;

    private static IApiAccessPolicy Policy(string identity) =>
        new DelegateFixturePolicy(GameplayCapabilityPolicy.CreateApiPolicy([identity], Contract));

    private static void ValidateGrouped(byte[] image, string identity) => GroupedRoute.Value.Invoke(image, identity, Policy(identity));

    private static void ValidateLegacy(byte[] image, string identity) =>
        GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [identity], Contract, Policy(identity));

    private static readonly Lazy<GroupedRouteBinder> GroupedRoute = new(() => new GroupedRouteBinder());

    private sealed class GroupedRouteBinder
    {
        private readonly MethodInfo _method = typeof(GameplayCapabilityPolicy).GetMethod(
                "ValidateGroupedHostWithApiPolicy",
                BindingFlags.NonPublic | BindingFlags.Static,
                binder: null,
                types: [typeof(ReadOnlyMemory<byte>), typeof(IReadOnlyCollection<string>), typeof(string), typeof(IApiAccessPolicy)],
                modifiers: null)
            ?? throw new InvalidOperationException(
                "GameplayCapabilityPolicy.ValidateGroupedHostWithApiPolicy(ReadOnlyMemory<byte>, IReadOnlyCollection<string>, string, IApiAccessPolicy) is missing; the grouped delegate route is not available.");

        public void Invoke(byte[] image, string identity, IApiAccessPolicy policy)
        {
            try
            {
                _method.Invoke(null, [new ReadOnlyMemory<byte>(image), new[] { identity }, Contract, policy]);
            }
            catch (TargetInvocationException error) when (error.InnerException is not null)
            {
                ExceptionDispatchInfo.Capture(error.InnerException).Throw();
            }
        }
    }

    private sealed class DelegateFixturePolicy(IApiAccessPolicy baseline) : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            if (target.Kind == ApiTargetKind.Type && IsTrustedDelegateTypeName(target.TypeName) &&
                operation is ApiOperation.Reference or ApiOperation.ReadMetadata)
                return ApiDecision.Allow;
            if (target.Kind == ApiTargetKind.Method && IsTrustedDelegateTypeName(target.TypeName) &&
                (target.MemberName == ".ctor" || target.MemberName == "Invoke") &&
                operation is ApiOperation.Reference or ApiOperation.ReadMetadata or ApiOperation.Construct or ApiOperation.Invoke)
                return ApiDecision.Allow;
            return baseline.Evaluate(target, operation);
        }

        private static bool IsTrustedDelegateTypeName(string? typeName) =>
            typeName is "System.Action" or "System.Predicate`1" or "System.Comparison`1" or "System.Converter`2"
                or "System.EventHandler" or "System.EventHandler`1" ||
            typeName is not null &&
            (typeName.StartsWith("System.Action`", StringComparison.Ordinal) || typeName.StartsWith("System.Func`", StringComparison.Ordinal));
    }

    // --- bounded IL inspection/rewrite helpers (patched images are never loaded) ---

    private readonly record struct Instruction(int Offset, ushort Value, string Name, int Size, int OperandOffset)
    {
        public int End => Offset + Size;
    }

    private sealed record DelegateSite(int BodyFileOffset, byte[] Il, List<Instruction> Instructions, int LdftnIndex, int NewobjIndex)
    {
        public Instruction Ldftn => Instructions[LdftnIndex];
        public Instruction Newobj => Instructions[NewobjIndex];
        public int LdftnOffset => Ldftn.Offset;
        public int NewobjOffset => Newobj.Offset;
    }

    private static List<Instruction> Decode(byte[] il)
    {
        var table = OpcodeCatalogCases.RuntimeOpcodeTable();
        var result = new List<Instruction>();
        var offset = 0;
        while (offset < il.Length)
        {
            var start = offset;
            ushort value = il[offset++];
            if (value == 0xFE && offset < il.Length) value = (ushort)(0xFE00 | il[offset++]);
            if (!table.TryGetValue(value, out var opcode))
                throw new InvalidOperationException("Unknown opcode 0x" + value.ToString("X4") + " at IL offset " + start + ".");
            var size = opcode.Operand switch
            {
                OperandType.InlineNone => 0,
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2,
                OperandType.InlineI8 or OperandType.InlineR => 8,
                OperandType.InlineSwitch => checked(4 + BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(offset, 4)) * 4),
                OperandType.InlineBrTarget or OperandType.InlineField or OperandType.InlineI or OperandType.InlineMethod or
                    OperandType.InlineSig or OperandType.InlineString or OperandType.InlineTok or OperandType.InlineType or
                    OperandType.ShortInlineR => 4,
                _ => throw new InvalidOperationException("Unsupported operand type " + opcode.Operand + " at IL offset " + start + ".")
            };
            if (size > il.Length - offset)
                throw new InvalidOperationException("Truncated operand at IL offset " + start + ".");
            result.Add(new Instruction(start, value, opcode.Name, offset - start + size, offset));
            offset += size;
        }
        return result;
    }

    private static HashSet<int> BranchTargets(byte[] il, List<Instruction> instructions)
    {
        var targets = new HashSet<int>();
        foreach (var instruction in instructions)
        {
            if (instruction.Value is >= 0x2B and <= 0x37)
                targets.Add(instruction.End + (sbyte)il[instruction.OperandOffset]);
            else if (instruction.Value is >= 0x38 and <= 0x44 || instruction.Value is 0xDD or 0xDE)
                targets.Add(instruction.End + BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(instruction.OperandOffset, 4)));
            else if (instruction.Value == 0x45)
            {
                var count = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(instruction.OperandOffset, 4));
                for (var index = 0; index < count; index++)
                    targets.Add(instruction.End + BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(instruction.OperandOffset + 4 + index * 4, 4)));
            }
        }
        return targets;
    }

    private static DelegateSite LocateDelegateSite(byte[] image)
    {
        using var stream = new MemoryStream(image, writable: false);
        using var pe = new PEReader(stream);
        var metadata = pe.GetMetadataReader();
        foreach (var handle in metadata.MethodDefinitions)
        {
            var method = metadata.GetMethodDefinition(handle);
            if (method.RelativeVirtualAddress == 0) continue;
            var body = pe.GetMethodBody(method.RelativeVirtualAddress);
            var il = body.GetILBytes();
            if (il is null || il.Length == 0) continue;
            List<Instruction> instructions;
            try { instructions = Decode(il); } catch { continue; }
            var newobjIndex = FindDelegateNewobj(instructions);
            if (newobjIndex < 0) continue;
            var bodyStart = RvaToFileOffset(pe, method.RelativeVirtualAddress + MethodBodyHeaderSize(pe, method.RelativeVirtualAddress));
            return new DelegateSite(bodyStart, il, instructions, newobjIndex - 1, newobjIndex);
        }
        throw new InvalidOperationException("The fixture image contains no newobj directly preceded by ldftn/ldvirtftn.");
    }

    private static int FindDelegateNewobj(List<Instruction> instructions)
    {
        for (var index = 1; index < instructions.Count; index++)
        {
            var current = instructions[index];
            if (current.Value != 0x0073) continue;
            var previous = instructions[index - 1];
            if (previous.Value is not (0xFE06 or 0xFE07)) continue;
            if (previous.End != current.Offset) continue;
            return index;
        }
        return -1;
    }

    private static byte[] PatchIl(byte[] image, DelegateSite site, Action<byte[], List<Instruction>> rewrite)
    {
        var il = (byte[])site.Il.Clone();
        var instructions = Decode(il);
        rewrite(il, instructions);
        var patched = (byte[])image.Clone();
        Buffer.BlockCopy(il, 0, patched, site.BodyFileOffset, il.Length);
        return patched;
    }

    private static byte[] PatchCatchClauseToNewobj(byte[] image)
    {
        using var stream = new MemoryStream(image, writable: false);
        using var pe = new PEReader(stream);
        var metadata = pe.GetMetadataReader();
        foreach (var handle in metadata.MethodDefinitions)
        {
            var method = metadata.GetMethodDefinition(handle);
            if (method.RelativeVirtualAddress == 0) continue;
            var body = pe.GetMethodBody(method.RelativeVirtualAddress);
            if (body.ExceptionRegions.IsDefaultOrEmpty) continue;
            var il = body.GetILBytes();
            if (il is null || il.Length == 0) continue;
            List<Instruction> instructions;
            try { instructions = Decode(il); } catch { continue; }
            var newobjIndex = FindDelegateNewobj(instructions);
            if (newobjIndex < 0) continue;
            var newobjOffset = instructions[newobjIndex].Offset;
            ExceptionRegion? catchRegion = null;
            foreach (var region in body.ExceptionRegions)
                if (region.Kind == ExceptionRegionKind.Catch) { catchRegion = region; break; }
            if (catchRegion is null)
                throw new InvalidOperationException("EH-boundary test unsupported: the fixture has no catch clause.");

            var headerSize = MethodBodyHeaderSize(pe, method.RelativeVirtualAddress);
            var section = FindSection(pe, method.RelativeVirtualAddress);
            var relative = method.RelativeVirtualAddress + headerSize + il.Length - section.VirtualAddress;
            var extraStart = section.PointerToRawData + ((relative + 3) & ~3);
            var tryLength = il.Length - newobjOffset;
            if (tryLength <= 0)
                throw new InvalidOperationException("EH-boundary test unsupported: the delegate newobj is outside the method body.");
            var patched = (byte[])image.Clone();
            var kind = image[extraStart];
            if (kind == 0x01)
            {
                Check.Assert(tryLength <= byte.MaxValue, "EH-boundary test unsupported: the patched try region length does not fit the small clause format.");
                var clause = extraStart + 4; // kind(1) + compressed data size(1) + reserved(2)
                BinaryPrimitives.WriteUInt16LittleEndian(patched.AsSpan(clause + 2), (ushort)newobjOffset);
                patched[clause + 4] = (byte)tryLength;
            }
            else if (kind == 0x41)
            {
                var clause = extraStart + 4;
                BinaryPrimitives.WriteInt32LittleEndian(patched.AsSpan(clause + 4), newobjOffset);
                BinaryPrimitives.WriteInt32LittleEndian(patched.AsSpan(clause + 8), tryLength);
            }
            else
            {
                throw new InvalidOperationException("EH-boundary test unsupported: unknown method-data kind 0x" + kind.ToString("X2") + ".");
            }

            if (!TryReadCatchOffsets(patched, method.RelativeVirtualAddress, out var patchedTryOffset, out var patchedTryLength) ||
                patchedTryOffset != newobjOffset || patchedTryLength != tryLength)
                throw new InvalidOperationException("EH-boundary test unsupported: the patched catch clause could not be verified.");
            return patched;
        }
        throw new InvalidOperationException("EH-boundary test unsupported: no method with a catch clause around a delegate construction.");
    }

    private static SectionHeader FindSection(PEReader pe, int rva)
    {
        foreach (var section in pe.PEHeaders.SectionHeaders)
            if (rva >= section.VirtualAddress && rva < (long)section.VirtualAddress + section.SizeOfRawData)
                return section;
        throw new InvalidOperationException("RVA 0x" + rva.ToString("X8") + " is not mapped by any PE section.");
    }

    private static bool TryReadCatchOffsets(byte[] image, int rva, out int tryOffset, out int tryLength)
    {
        tryOffset = -1;
        tryLength = -1;
        try
        {
            using var stream = new MemoryStream(image, writable: false);
            using var pe = new PEReader(stream);
            var body = pe.GetMethodBody(rva);
            foreach (var region in body.ExceptionRegions)
            {
                if (region.Kind != ExceptionRegionKind.Catch) continue;
                tryOffset = region.TryOffset;
                tryLength = region.TryLength;
                return true;
            }
        }
        catch { return false; }
        return false;
    }
    private static int MethodBodyHeaderSize(PEReader pe, int rva)
    {
        var first = pe.GetSectionData(rva).GetReader().ReadByte();
        return (first & 0x3) == 0x2 ? 1 : 12;
    }

    private static int RvaToFileOffset(PEReader pe, int rva)
    {
        foreach (var section in pe.PEHeaders.SectionHeaders)
        {
            var size = Math.Max(section.VirtualSize, section.SizeOfRawData);
            if (rva >= section.VirtualAddress && rva < section.VirtualAddress + size)
                return section.PointerToRawData + (rva - section.VirtualAddress);
        }
        throw new InvalidOperationException("RVA 0x" + rva.ToString("X8") + " is not mapped by any PE section.");
    }
}
