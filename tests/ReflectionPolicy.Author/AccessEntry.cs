using System.Reflection;
using ReflectionPolicy.CompiledLibrary;

namespace ReflectionPolicy.Author;

public static class AccessEntry
{
    private static readonly Dto data = new(10);
    public static int Snapshot() => data.Value;
    public static int NumberSnapshot() => data.NumberStorage;
    public static int ReadonlySnapshot() => data.Readonly;
    public static object? ObjectSnapshot() => data.Any;
    public static int RoundTrip()
    {
        var dto = (Dto)typeof(Dto).GetConstructor([typeof(int)])!.Invoke([10]);
        var field = typeof(Dto).GetField(nameof(Dto.Value))!;
        field.SetValue(dto, 41);
        var property = typeof(Dto).GetProperty(nameof(Dto.Number))!;
        property.SetValue(dto, (int)field.GetValue(dto)! + 1);
        var indexer = typeof(Dto).GetProperty("Item")!;
        indexer.SetValue(dto, 43, [0]);
        return (int)property.GetValue(dto)! + (int)indexer.GetValue(dto, [0])!;
    }

    public static int LibraryRoundTrip()
    {
        var dto = ReflectionLibrary.Construct(typeof(Dto).GetConstructor([typeof(int)])!, [10]);
        var field = typeof(Dto).GetField(nameof(Dto.Value))!;
        ReflectionLibrary.WriteField(field, dto, 41);
        var property = typeof(Dto).GetProperty(nameof(Dto.Number))!;
        ReflectionLibrary.WriteProperty(property, dto, (int)ReflectionLibrary.ReadField(field, dto)! + 1);
        return (int)ReflectionLibrary.ReadProperty(property, dto)!;
    }

    public static void ConstructDenied() => typeof(DeniedConstruction).GetConstructor(Type.EmptyTypes)!.Invoke(null);
    public static void LibraryConstructDenied() => ReflectionLibrary.Construct(typeof(DeniedConstruction).GetConstructor(Type.EmptyTypes)!, []);
    public static void ConstructExisting() => typeof(Dto).GetConstructor([typeof(int)])!.Invoke(data, [99]);
    public static void ConstructThrowing() => typeof(ThrowingConstruction).GetConstructor(Type.EmptyTypes)!.Invoke(null);
    public static int ReadField() => (int)typeof(Dto).GetField(nameof(Dto.Value))!.GetValue(data)!;
    public static void WriteField() => typeof(Dto).GetField(nameof(Dto.Value))!.SetValue(data, data.Value + 1);
    public static int LibraryReadField() => (int)ReflectionLibrary.ReadField(typeof(Dto).GetField(nameof(Dto.Value))!, data)!;
    public static void LibraryWriteField() => ReflectionLibrary.WriteField(typeof(Dto).GetField(nameof(Dto.Value))!, data, data.Value + 1);
    public static int ReadProperty() => (int)typeof(Dto).GetProperty(nameof(Dto.Number))!.GetValue(data)!;
    public static void WriteProperty() => typeof(Dto).GetProperty(nameof(Dto.Number))!.SetValue(data, 99);
    public static int LibraryReadProperty() => (int)ReflectionLibrary.ReadProperty(typeof(Dto).GetProperty(nameof(Dto.Number))!, data)!;
    public static void LibraryWriteProperty() => ReflectionLibrary.WriteProperty(typeof(Dto).GetProperty(nameof(Dto.Number))!, data, 99);
    public static int ReadIndex() => (int)typeof(Dto).GetProperty("Item")!.GetValue(data, [0])!;
    public static void WriteIndex() => typeof(Dto).GetProperty("Item")!.SetValue(data, 99, [0]);
    public static int ReadStatic() => (int)typeof(StaticFieldTarget).GetField(nameof(StaticFieldTarget.Value))!.GetValue(null)!;
    public static void WriteStatic() => typeof(StaticFieldTarget).GetField(nameof(StaticFieldTarget.Value))!.SetValue(null, 99);
    public static int ReadConstant() => (int)typeof(Dto).GetField(nameof(Dto.Constant))!.GetValue(null)!;
    public static int ReadRawConstant() => (int)typeof(Dto).GetField(nameof(Dto.Constant))!.GetRawConstantValue()!;
    public static void WriteReadonly() => typeof(Dto).GetField(nameof(Dto.Readonly))!.SetValue(data, 99);
    public static void WriteForbiddenValue() => typeof(Dto).GetField(nameof(Dto.Any))!.SetValue(data, new FileInfo("forbidden-value"));
    public static int GenericFields()
    {
        var box = typeof(Box<int>).GetConstructor([typeof(int)])!.Invoke([41]);
        var field = typeof(Box<int>).GetField(nameof(Box<int>.Value))!;
        field.SetValue(box, 42);
        return (int)field.GetValue(box)!;
    }
    public static void ForbiddenGenericConstructor() => typeof(Box<FileInfo>).GetConstructor([typeof(FileInfo)])!.Invoke([null]);
    public static void ConstructWithBinder(Binder binder) => typeof(Dto).GetConstructor([typeof(int)])!.Invoke(BindingFlags.Default, binder, ["99"], null);
    public static void FieldWithBinder(Binder binder) => typeof(Dto).GetField(nameof(Dto.Value))!.SetValue(data, "99", BindingFlags.Default, binder, null);
    public static void PropertyWithBinder(Binder binder) => typeof(Dto).GetProperty(nameof(Dto.Number))!.SetValue(data, "99", BindingFlags.Default, binder, null, null);
}

public sealed class Dto(int value)
{
    public const int Constant = 23;
    public readonly int Readonly = 10;
    public int Value = value;
    public object? Any;
    public int NumberStorage = value;
    public int Number
    {
        get { Counters.PropertyReads++; return NumberStorage; }
        set { Counters.PropertyWrites++; NumberStorage = value; }
    }
    public int this[int index]
    {
        get { Counters.IndexReads++; return Value + index; }
        set { Counters.IndexWrites++; Value = value - index; }
    }
}

public sealed class DeniedConstruction
{
    static DeniedConstruction() { Counters.ConstructorStaticRuns++; }
    public DeniedConstruction() { Counters.ConstructorBodyRuns++; }
}

public sealed class ThrowingConstruction
{
    public ThrowingConstruction() => throw new InvalidOperationException("constructor-failure");
}

public static class StaticFieldTarget
{
    static StaticFieldTarget() { Counters.FieldStaticRuns++; Value = 77; }
    public static int Value;
}

public sealed class Box<T>
{
    public Box(T value) { Counters.BoxRuns++; Value = value; }
    public T Value;
}
