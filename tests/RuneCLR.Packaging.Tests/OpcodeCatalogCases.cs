using System.Collections;
using System.Reflection;
using System.Reflection.Emit;
using RuneCLR.Packages;

/// <summary>
/// Bounded equivalence check between the checked-in group-only opcode catalog and the runtime
/// <see cref="OpCodes"/> table. The production validator stays reflection-free; the reflection lives
/// here, in the stock test process, and never inside a policy scope.
/// </summary>
internal static class OpcodeCatalogCases
{
    private const int ExpectedOpcodeCount = 226;

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Grouped opcode catalog matches runtime OpCodes key/name/operand for all 226 entries", CatalogMatchesRuntime);
        yield return ("Grouped opcode catalog is complete, duplicate-free and prefix-consistent", CatalogShape);
    }

    private readonly record struct CatalogEntry(string Name, OperandType Operand);

    private static void CatalogMatchesRuntime()
    {
        var catalog = ReadCatalog();
        var runtime = RuntimeOpcodeTable();
        Check.Assert(runtime.Count == ExpectedOpcodeCount,
            "The runtime exposes " + runtime.Count + " opcodes; the checked-in table was generated from a different SDK (expected " + ExpectedOpcodeCount + ").");
        Check.Assert(catalog.Count == runtime.Count,
            "The checked-in catalog has " + catalog.Count + " entries; the runtime exposes " + runtime.Count + ".");
        foreach (var (value, expected) in runtime)
        {
            Check.Assert(catalog.TryGetValue(value, out var actual),
                "The checked-in catalog is missing opcode 0x" + value.ToString("X4") + " (" + expected.Name + ").");
            Check.Assert(actual.Name == expected.Name,
                "Opcode 0x" + value.ToString("X4") + " name mismatch: catalog '" + actual.Name + "', runtime '" + expected.Name + "'.");
            Check.Assert(actual.Operand == expected.Operand,
                "Opcode 0x" + value.ToString("X4") + " (" + expected.Name + ") operand mismatch: catalog " + actual.Operand + ", runtime " + expected.Operand + ".");
        }
        foreach (var (value, entry) in catalog)
            Check.Assert(runtime.ContainsKey(value),
                "The checked-in catalog contains an opcode the runtime does not expose: 0x" + value.ToString("X4") + " (" + entry.Name + ").");
    }

    private static void CatalogShape()
    {
        var catalog = ReadCatalog();
        Check.Assert(catalog.Count == ExpectedOpcodeCount, "Catalog count " + catalog.Count + " is not " + ExpectedOpcodeCount + ".");
        foreach (var (value, entry) in catalog)
        {
            Check.Assert(entry.Name.Length is > 0 and <= 16, "Opcode 0x" + value.ToString("X4") + " has an implausible name '" + entry.Name + "'.");
            Check.Assert(value < 0xFE00 || value <= 0xFEFF, "Opcode 0x" + value.ToString("X4") + " is outside the two-byte opcode range.");
        }
        Check.Assert(catalog.TryGetValue(0xFE06, out var ldftn) && ldftn.Name == "ldftn", "ldftn (0xFE06) is missing from the catalog.");
        Check.Assert(catalog.TryGetValue(0xFE07, out var ldvirtftn) && ldvirtftn.Name == "ldvirtftn", "ldvirtftn (0xFE07) is missing from the catalog.");
        Check.Assert(catalog.TryGetValue(0x0073, out var newobj) && newobj.Name == "newobj", "newobj (0x0073) is missing from the catalog.");
        Check.Assert(catalog.TryGetValue(0x0029, out var calli) && calli.Name == "calli", "calli (0x0029) is missing from the catalog.");
    }

    private static Dictionary<ushort, CatalogEntry> ReadCatalog()
    {
        var assembly = typeof(GameplayCapabilityPolicy).Assembly;
        var type = assembly.GetType("RuneCLR.Packages.GameplayCapabilityOpcodes", throwOnError: false)
            ?? throw new InvalidOperationException("RuneCLR.Packages.GameplayCapabilityOpcodes is missing; the checked-in opcode catalog is not available.");
        var field = type.GetField("ByValue", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("GameplayCapabilityOpcodes.ByValue is missing; the test binds the internal catalog by name.");
        if (field.GetValue(null) is not IEnumerable items)
            throw new InvalidOperationException("GameplayCapabilityOpcodes.ByValue is not enumerable.");
        var result = new Dictionary<ushort, CatalogEntry>();
        foreach (var item in items)
        {
            if (item is null) throw new InvalidOperationException("'ByValue' yielded a null entry.");
            var itemType = item.GetType();
            var keyValue = itemType.GetProperty("Key")?.GetValue(item)
                ?? throw new InvalidOperationException("'ByValue' entries have no Key.");
            var tuple = itemType.GetProperty("Value")?.GetValue(item)
                ?? throw new InvalidOperationException("'ByValue' entries have no Value tuple.");
            var tupleType = tuple.GetType();
            var name = tupleType.GetField("Item1")?.GetValue(tuple) as string
                ?? throw new InvalidOperationException("The catalog value tuple has no name item.");
            var operandValue = tupleType.GetField("Item2")?.GetValue(tuple)
                ?? throw new InvalidOperationException("The catalog value tuple has no operand item.");
            var key = (ushort)keyValue;
            if (!result.TryAdd(key, new CatalogEntry(name, (OperandType)operandValue)))
                throw new InvalidOperationException("The checked-in catalog contains duplicate key 0x" + key.ToString("X4") + ".");
        }
        return result;
    }

    internal static Dictionary<ushort, (string Name, OperandType Operand)> RuntimeOpcodeTable() =>
        typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(field => field.FieldType == typeof(OpCode))
            .Select(field => (OpCode)field.GetValue(null)!)
            .ToDictionary(opcode => unchecked((ushort)opcode.Value),
                opcode => (Name: opcode.Name!, Operand: opcode.OperandType));
}
