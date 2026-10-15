using System.Reflection;
using System.Runtime.Loader;

namespace RuneCLR.Runtime;

// Only the trusted CoreLib type and these exact private signatures are inspected.
// Delegates are local to a run; never put a session context/resolver in a static root.
internal sealed class RequiredInterpreterBridge
{
    private readonly Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> _create;
    private readonly Func<AssemblyLoadContext, int> _getPolicy;

    private RequiredInterpreterBridge(
        Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext> create,
        Func<AssemblyLoadContext, int> getPolicy)
    {
        _create = create;
        _getPolicy = getPolicy;
    }

    public static RequiredInterpreterBridge Bind()
    {
        try
        {
            var type = typeof(AssemblyLoadContext);
            var factory = Method(type, "RuneCLR_CreateInterpreterRequired", isStatic: true,
                typeof(AssemblyLoadContext), typeof(string), typeof(Func<AssemblyLoadContext, AssemblyName, Assembly?>));
            var version = Method(type, "RuneCLR_GetExecutionPolicyVersion", isStatic: true, typeof(int));
            var getPolicy = Method(type, "RuneCLR_GetExecutionPolicy", isStatic: false, typeof(int));
            if (version.CreateDelegate<Func<int>>()() != 1)
                throw Unsupported("The CoreLib execution-policy version is not 1.");
            return new RequiredInterpreterBridge(
                factory.CreateDelegate<Func<string, Func<AssemblyLoadContext, AssemblyName, Assembly?>, AssemblyLoadContext>>(),
                getPolicy.CreateDelegate<Func<AssemblyLoadContext, int>>());
        }
        catch (PlatformNotSupportedException) { throw; }
        catch (Exception error) { throw Unsupported("The trusted CoreLib execution-policy bridge cannot be bound.", error); }
    }

    public AssemblyLoadContext Create(string name, Func<AssemblyLoadContext, AssemblyName, Assembly?> resolver)
    {
        AssemblyLoadContext? context = null;
        try
        {
            context = _create(name, resolver);
            Acknowledge(context);
            return context!;
        }
        catch
        {
            if (context?.IsCollectible == true) context.Unload();
            throw;
        }
    }

    internal void Acknowledge(AssemblyLoadContext? context)
    {
        if (context is null || !context.IsCollectible || _getPolicy(context) != 1)
            throw Unsupported("The new collectible context did not acknowledge native required-interpreter policy.");
    }

    internal static MethodInfo Method(Type type, string name, bool isStatic, Type result, params Type[] parameters)
    {
        var flags = BindingFlags.NonPublic | BindingFlags.DeclaredOnly |
            (isStatic ? BindingFlags.Static : BindingFlags.Instance);
        var method = type.GetMethod(name, flags, binder: null, types: parameters, modifiers: null);
        if (method is null || !method.IsPrivate || method.IsStatic != isStatic ||
            method.ReturnType != result || method.IsGenericMethod)
            throw Unsupported($"The trusted CoreLib lacks the fixed {name} signature.");
        return method;
    }

    private static PlatformNotSupportedException Unsupported(string message, Exception? inner = null) =>
        new("RequireInterpreter needs RuneCLR CoreLib/native execution-policy support. " + message, inner);
}
