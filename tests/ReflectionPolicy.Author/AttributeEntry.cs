namespace ReflectionPolicy.Author;

public static class AttributeEntry
{
    public static int StaticRuns;
    public static int Constructors;
    public static int Setters;
    public static int Defaults;
    public static object? Last;
    public static void Read() => Last = typeof(Decorated).GetCustomAttributes(false)[0];
    public static void ReadDefault() => _ = typeof(DefaultDecorated).GetCustomAttributes(false);
    public static int Snapshot() => Last is GateAttribute value ? value.Number + value.Field : 0;
}

[Gate(7, Number = 8, Field = 9)]
public sealed class Decorated { }
[DefaultGate]
public sealed class DefaultDecorated { }

public sealed class GateAttribute : Attribute
{
    static GateAttribute() { AttributeEntry.StaticRuns++; }
    public GateAttribute(int number) { AttributeEntry.Constructors++; }
    public int Field;
    private int number;
    public int Number { get => number; set { AttributeEntry.Setters++; number = value; } }
}
public sealed class DefaultGateAttribute : Attribute
{
    public DefaultGateAttribute() { AttributeEntry.Defaults++; }
}
