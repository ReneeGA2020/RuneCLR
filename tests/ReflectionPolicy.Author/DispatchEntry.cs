using ReflectionPolicy.CompiledLibrary;

namespace ReflectionPolicy.Author;

public static class DispatchEntry
{
    public static int Runs;
    public static int Virtual() => (int)typeof(DispatchBase).GetMethod(nameof(DispatchBase.Read))!.Invoke(new DispatchChild(), null)!;
    public static int LibraryVirtual() => (int)ReflectionLibrary.Call(typeof(DispatchBase).GetMethod(nameof(DispatchBase.Read))!, new DispatchChild(), [])!;
    public static int Inherited() => (int)typeof(DispatchBase).GetMethod(nameof(DispatchBase.Read))!.Invoke(new DispatchInherited(), null)!;
    public static int Hidden() => (int)typeof(DispatchBase).GetMethod(nameof(DispatchBase.Read))!.Invoke(new DispatchHidden(), null)!;
    public static int Abstract() => (int)typeof(DispatchAbstract).GetMethod(nameof(DispatchAbstract.Value))!.Invoke(new DispatchConcrete(), null)!;
    public static int Interface() => (int)typeof(IDispatch).GetMethod(nameof(IDispatch.Value))!.Invoke(new ExplicitDispatch(), null)!;
    public static int DefaultInterface() => (int)typeof(IDefaultDispatch).GetMethod(nameof(IDefaultDispatch.Value))!.Invoke(new DefaultDispatch(), null)!;
    public static int StructInterface() => (int)typeof(IDispatch).GetMethod(nameof(IDispatch.Value))!.Invoke(new StructDispatch(), null)!;
    public static int Generic() => (int)typeof(DispatchBase).GetMethod(nameof(DispatchBase.Echo))!.MakeGenericMethod(typeof(int)).Invoke(new DispatchChild(), [43])!;
    public static string GenericType() => (string)typeof(GenericDispatchBase<string>).GetMethod("Echo")!.Invoke(new GenericDispatchChild(), ["dispatch"])!;
    public static string VariantInterface() => (string)typeof(IVariantDispatch<object>).GetMethod("Read")!.Invoke(new VariantDispatch(), null)!;
    public static object Covariant() => typeof(CovariantBase).GetMethod("Read")!.Invoke(new CovariantChild(), null)!;
    public static int Property() => (int)typeof(DispatchBase).GetProperty("Number")!.GetValue(new DispatchChild())!;
    public static void SetProperty() => typeof(DispatchBase).GetProperty("Number")!.SetValue(new DispatchChild(), 9);
    public static void Event() => typeof(DispatchBase).GetEvent("Changed")!.AddEventHandler(new DispatchChild(), (DispatchHandler)(() => { }));
}
public delegate void DispatchHandler();

public class DispatchBase
{
    public virtual int Read() { DispatchEntry.Runs++; return 1; }
    public virtual T Echo<T>(T value) { DispatchEntry.Runs++; return value; }
    public virtual int Number { get { DispatchEntry.Runs++; return 1; } set { DispatchEntry.Runs++; } }
    public virtual event DispatchHandler Changed { add { DispatchEntry.Runs++; } remove { DispatchEntry.Runs++; } }
}
public sealed class DispatchChild : DispatchBase
{
    public override int Read() { DispatchEntry.Runs++; return 2; }
    public override T Echo<T>(T value) { DispatchEntry.Runs++; return value; }
    public override int Number { get { DispatchEntry.Runs++; return 2; } set { DispatchEntry.Runs += value; } }
    public override event DispatchHandler Changed { add { DispatchEntry.Runs += 2; } remove { DispatchEntry.Runs += 2; } }
}
public sealed class DispatchInherited : DispatchBase { }
public sealed class DispatchHidden : DispatchBase { public new int Read() { DispatchEntry.Runs += 100; return 99; } }
public abstract class DispatchAbstract { public abstract int Value(); }
public sealed class DispatchConcrete : DispatchAbstract { public override int Value() { DispatchEntry.Runs++; return 3; } }
public interface IDispatch { int Value(); }
public sealed class ExplicitDispatch : IDispatch { int IDispatch.Value() { DispatchEntry.Runs++; return 4; } }
public struct StructDispatch : IDispatch { public int Value() { DispatchEntry.Runs++; return 5; } }
public interface IDefaultDispatch { int Value() { DispatchEntry.Runs++; return 6; } }
public sealed class DefaultDispatch : IDefaultDispatch { }
public class GenericDispatchBase<T> { public virtual T Echo(T value) { DispatchEntry.Runs++; return value; } }
public sealed class GenericDispatchChild : GenericDispatchBase<string> { public override string Echo(string value) { DispatchEntry.Runs++; return value; } }
public interface IVariantDispatch<out T> { T Read(); }
public sealed class VariantDispatch : IVariantDispatch<string> { public string Read() { DispatchEntry.Runs++; return "variant"; } }
public class CovariantBase { public virtual object Read() { DispatchEntry.Runs++; return new object(); } }
public sealed class CovariantChild : CovariantBase { public override string Read() { DispatchEntry.Runs++; return "covariant"; } }
