using System.Reflection;

namespace ReflectionPolicy.CompiledLibrary;

public static class ReflectionLibrary
{
    public static object? Call(MethodInfo target, object? receiver, object?[] arguments) => target.Invoke(receiver, arguments);
    public static object Construct(ConstructorInfo target, object?[] arguments) => target.Invoke(arguments);
    public static object? ReadField(FieldInfo target, object? receiver) => target.GetValue(receiver);
    public static void WriteField(FieldInfo target, object? receiver, object? value) => target.SetValue(receiver, value);
    public static object? ReadProperty(PropertyInfo target, object? receiver) => target.GetValue(receiver);
    public static void WriteProperty(PropertyInfo target, object? receiver, object? value) => target.SetValue(receiver, value);
    public static object? FastCall(MethodInvoker invoker, object? receiver, object?[] arguments) => arguments.Length switch
    {
        0 => invoker.Invoke(receiver),
        1 => invoker.Invoke(receiver, arguments[0]),
        2 => invoker.Invoke(receiver, arguments[0], arguments[1]),
        3 => invoker.Invoke(receiver, arguments[0], arguments[1], arguments[2]),
        4 => invoker.Invoke(receiver, arguments[0], arguments[1], arguments[2], arguments[3]),
        _ => invoker.Invoke(receiver, arguments.AsSpan()),
    };
    public static object FastConstruct(ConstructorInvoker invoker, object?[] arguments) => arguments.Length switch
    {
        0 => invoker.Invoke(),
        1 => invoker.Invoke(arguments[0]),
        2 => invoker.Invoke(arguments[0], arguments[1]),
        3 => invoker.Invoke(arguments[0], arguments[1], arguments[2]),
        4 => invoker.Invoke(arguments[0], arguments[1], arguments[2], arguments[3]),
        _ => invoker.Invoke(arguments.AsSpan()),
    };
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    public static T Activate<T>() where T : new() => Activator.CreateInstance<T>();
}
