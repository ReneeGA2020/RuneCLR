// Loaded from the test image into two ordinary collectible contexts. Never used
// as a compile-time DTO contract by the host; each context owns a distinct Type.
namespace RuneCLR.SerializationFixtures;

public sealed class Record
{
    public int Value;
    public string Label = "";
    public object? Peer;
    public int Number => Value;
    public object? Link => Peer;
}

public sealed class ThrowingRecord
{
    public int Value;
    public string Label = "";
    public object? Peer;
    public int Reading => throw new InvalidOperationException("synthetic serialization getter failure");
}
