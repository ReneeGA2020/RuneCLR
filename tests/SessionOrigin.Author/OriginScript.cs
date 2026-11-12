using System.Reflection;
using RuneCLR;
using SessionOrigin.Compiled;

namespace SessionOrigin.Author;

public class OriginScript : IMapScript
{
    public OriginScript() { }
    public virtual void OnStart(IMapContext context) { }
    public virtual void OnTick(MapTick tick) { }
    public virtual void OnStop() { }

    protected static void Run(bool suppressFlow, bool useTask, bool hiddenFrame = false, bool inlinedFrame = false)
    {
        OriginHooks.RunChild(Probe(nameof(ChildProbe)), suppressFlow, useTask,
            hiddenFrame: hiddenFrame, inlinedFrame: inlinedFrame);
    }

    protected static MethodInfo Probe(string name) => typeof(OriginScript).GetMethod(name,
        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!;

    public static void ChildProbe() => ProbeBody();

    public static void OverflowProbe() => OriginHooks.RunOverflowChain();

    /// <summary>Parks inside the author frame so the host can retire the session underneath it.</summary>
    public static void BlockingProbe()
    {
        OriginHooks.ParkUntilReleased(15000);
        ProbeBody();
    }

    private static void ProbeBody()
    {
        try
        {
            var effect = typeof(OriginHooks).GetMethod(nameof(OriginHooks.ForbiddenEffect))!;
            effect.Invoke(null, null);
        }
        catch (TargetInvocationException error) when (error.InnerException is InvalidOperationException)
        {
            OriginHooks.RecordReflectionDenied();
        }
        catch (InvalidOperationException)
        {
            OriginHooks.RecordReflectionDenied();
        }

        try
        {
            Assembly.Load(OriginHooks.DeniedAssemblyBytes!);
            OriginHooks.RecordLoadSucceeded();
        }
        catch (Exception error) when (error is InvalidOperationException or InvalidDataException or BadImageFormatException)
        {
            OriginHooks.RecordLoadDenied();
        }
    }
}

public sealed class NormalThreadScript : OriginScript
{
    public override void OnStart(IMapContext context) { base.OnStart(context); Run(false, false); }
}

public sealed class SuppressedThreadScript : OriginScript
{
    public override void OnStart(IMapContext context) { base.OnStart(context); Run(true, false); }
}

public sealed class SuppressedTaskScript : OriginScript
{
    public override void OnStart(IMapContext context) { base.OnStart(context); Run(true, true); }
}

public sealed class CompiledHelperScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        OriginHooks.ReflectForbiddenCompiledHelper();
    }
}

public sealed class RetirementScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        OriginHooks.SetRetainedProbe(typeof(OriginScript).GetMethod(nameof(ChildProbe),
            BindingFlags.Public | BindingFlags.Static)!);
    }
}

public sealed class HiddenHelperScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        Run(true, false, hiddenFrame: true);
    }
}

public sealed class InlinedHelperScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        Run(true, false, inlinedFrame: true);
    }
}

public sealed class ConflictingOwnerScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        OriginHooks.InvokeOther();
    }
}

public sealed class OverflowScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        OriginHooks.SetRetainedProbe(Probe(nameof(ChildProbe)));
        OriginHooks.RunChild(Probe(nameof(OverflowProbe)), suppressFlow: true, useTask: false);
    }
}

public sealed class DisposalScript : OriginScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        OriginHooks.StartBlockingChild(Probe(nameof(BlockingProbe)));
    }
}
