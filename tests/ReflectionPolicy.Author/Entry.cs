using ReflectionPolicy.CompiledLibrary;

namespace ReflectionPolicy.Author;

public static class Entry
{
    public static int Own() => (int)typeof(Payload).GetMethod(nameof(Payload.ABC))!.Invoke(null, [40])!;
    public static bool Framework() => (bool)typeof(string).GetMethod(nameof(string.StartsWith), [typeof(string)])!
        .Invoke("player", ["play"])!;
    public static int ThroughLibrary() => (int)ReflectionLibrary.Call(typeof(Payload).GetMethod(nameof(Payload.ABC))!, null, [40])!;
    public static void LibraryTouch() => ReflectionLibrary.Call(typeof(NeverTarget).GetMethod(nameof(NeverTarget.Touch))!, null, []);
    public static void FileWrite(string path) => typeof(File).GetMethod(nameof(File.WriteAllText), [typeof(string), typeof(string)])!
        .Invoke(null, [path, "must-not-be-written"]);
    public static void Touch() => typeof(NeverTarget).GetMethod(nameof(NeverTarget.Touch))!.Invoke(null, null);
    public static int CatchDenied()
    {
        int caught = 0;
        for (int i = 0; i < 2; i++)
        {
            try { Touch(); }
            catch (InvalidOperationException) { caught++; }
        }
        return caught;
    }
    public static int Generic() => (int)typeof(Payload).GetMethod(nameof(Payload.Echo))!.MakeGenericMethod(typeof(int)).Invoke(null, [41])!;
    public static void ForbiddenGeneric() => typeof(Payload).GetMethod(nameof(Payload.Echo))!.MakeGenericMethod(typeof(FileInfo)).Invoke(null, [null]);
    public static int BaseVirtual() => (int)typeof(Parent).GetMethod(nameof(Parent.Read))!.Invoke(new Child(), null)!;
    public static int ConcreteVirtual() => (int)typeof(Child).GetMethod(nameof(Child.Read))!.Invoke(new Child(), null)!;
    public static void Throwing() => typeof(Payload).GetMethod(nameof(Payload.Fail))!.Invoke(null, null);
}

public static class Counters
{
    public static int StaticRuns;
    public static int BodyRuns;
    public static int GenericRuns;
    public static int VirtualRuns;
    public static int ConstructorStaticRuns;
    public static int ConstructorBodyRuns;
    public static int FieldStaticRuns;
    public static int PropertyReads;
    public static int PropertyWrites;
    public static int IndexReads;
    public static int IndexWrites;
    public static int BoxRuns;
}

public static class Payload
{
    public static int ABC(int value) => value + 1;
    public static T Echo<T>(T value) { Counters.GenericRuns++; return value; }
    public static void Fail() => throw new InvalidOperationException("author-failure");
}

public static class NeverTarget
{
    static NeverTarget() { Counters.StaticRuns++; }
    public static void Touch() { Counters.BodyRuns++; }
}

public class Parent { public virtual int Read() => 1; }
public sealed class Child : Parent
{
    public override int Read() { Counters.VirtualRuns++; return 2; }
}
