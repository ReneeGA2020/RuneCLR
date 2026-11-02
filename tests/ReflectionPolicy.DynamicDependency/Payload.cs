using ReflectionPolicy.CompiledLibrary;

namespace DynamicDependency;

public static class Payload
{
    static Payload() => SessionHooks.MarkLoaded();
    public static int ABC() => 41;
}
