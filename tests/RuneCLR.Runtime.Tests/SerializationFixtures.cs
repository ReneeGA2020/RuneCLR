// Loaded from the test image into two ordinary collectible contexts. Never used
// as a compile-time DTO contract by the host; each context owns a distinct Type.
namespace RuneCLR.SerializationFixtures;

public sealed class Record
{
    [System.Text.Json.Serialization.JsonInclude] public int Value;
    [System.Text.Json.Serialization.JsonInclude] public string Label = "";
    [System.Text.Json.Serialization.JsonInclude] public object? Peer;
    public int Number => Value;
    public object? Link => Peer;
}

public sealed class ThrowingRecord
{
    [System.Text.Json.Serialization.JsonInclude] public int Value;
    [System.Text.Json.Serialization.JsonInclude] public string Label = "";
    [System.Text.Json.Serialization.JsonInclude] public object? Peer;
    public int Reading => throw new InvalidOperationException("synthetic serialization getter failure");
}

// The host closes these Default-context definitions over types from two other
// contexts: the constructed Type is collectible while its defining Assembly is not.
public sealed class Pair<TLeft, TRight>
{
    [System.Text.Json.Serialization.JsonInclude] public TLeft Left = default!;
    [System.Text.Json.Serialization.JsonInclude] public TRight Right = default!;
}

public sealed class Nest<T>
{
    [System.Text.Json.Serialization.JsonInclude] public T Value = default!;
}

public sealed class StableRecord
{
    public int Value { get; set; }
}
