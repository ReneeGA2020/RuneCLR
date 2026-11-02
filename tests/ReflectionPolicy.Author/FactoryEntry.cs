using System.Reflection;
using ReflectionPolicy.CompiledLibrary;

namespace ReflectionPolicy.Author;

public static class FactoryEntry
{
    public static int Runs;
    public static int StaticRuns;
    private static MethodInvoker[] methods = [];
    private static ConstructorInvoker[] constructors = [];
    private static MethodInvoker? virtualMethod;
    public static void Prepare()
    {
        methods = Enumerable.Range(0, 6).Select(i => MethodInvoker.Create(typeof(FastTarget).GetMethod("M" + i)!)).ToArray();
        constructors = Enumerable.Range(0, 6).Select(i => ConstructorInvoker.Create(typeof(FastTarget).GetConstructor(Enumerable.Repeat(typeof(int), i).ToArray())!)).ToArray();
        virtualMethod = MethodInvoker.Create(typeof(DispatchBase).GetMethod("Read")!);
    }
    public static int FastMethod(int count) => (int)ReflectionLibrary.FastCall(methods[count], null, Enumerable.Repeat<object?>(1, count).ToArray())!;
    public static void FastConstructor(int count) => ReflectionLibrary.FastConstruct(constructors[count], Enumerable.Repeat<object?>(1, count).ToArray());
    public static int FastVirtual() => (int)ReflectionLibrary.FastCall(virtualMethod!, new DispatchChild(), [])!;
    public static void Default() => Activator.CreateInstance(typeof(ActivationTarget));
    public static void Generic() => Activator.CreateInstance<ActivationTarget>();
    public static void LibraryGeneric() => ReflectionLibrary.Activate<ActivationTarget>();
    public static void DefaultStruct() => Activator.CreateInstance(typeof(ImplicitValue));
    public static void GenericStruct() => ReflectionLibrary.Activate<ImplicitValue>();
    public static void ExplicitStruct() => ReflectionLibrary.Activate<ExplicitValue>();
    public static void Parameterized() => Activator.CreateInstance(typeof(FastTarget), [1, 2]);
    public static void TypeInvoke() => typeof(FastTarget).InvokeMember("M1", BindingFlags.InvokeMethod | BindingFlags.Public | BindingFlags.Static, null, null, [1]);
}

public class FastTarget
{
    public FastTarget() { FactoryEntry.Runs++; }
    public FastTarget(int a) { FactoryEntry.Runs++; }
    public FastTarget(int a, int b) { FactoryEntry.Runs++; }
    public FastTarget(int a, int b, int c) { FactoryEntry.Runs++; }
    public FastTarget(int a, int b, int c, int d) { FactoryEntry.Runs++; }
    public FastTarget(int a, int b, int c, int d, int e) { FactoryEntry.Runs++; }
    public static int M0() { FactoryEntry.Runs++; return 0; }
    public static int M1(int a) { FactoryEntry.Runs++; return 1; }
    public static int M2(int a, int b) { FactoryEntry.Runs++; return 2; }
    public static int M3(int a, int b, int c) { FactoryEntry.Runs++; return 3; }
    public static int M4(int a, int b, int c, int d) { FactoryEntry.Runs++; return 4; }
    public static int M5(int a, int b, int c, int d, int e) { FactoryEntry.Runs++; return 5; }
}
public class ActivationTarget
{
    static ActivationTarget() { FactoryEntry.StaticRuns++; }
    public ActivationTarget() { FactoryEntry.Runs++; }
}
public struct ImplicitValue { public int Value; }
public struct ExplicitValue { public ExplicitValue() { FactoryEntry.Runs++; } }
