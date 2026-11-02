using ReflectionPolicy.CompiledLibrary;
using RuneCLR;

namespace ReflectionPolicy.Author;

public class SessionScript : IMapScript
{
    protected IMapContext Context = null!;
    public SessionScript()
    {
        if (Read() != 41) throw new InvalidOperationException();
        SessionHooks.Capture();
    }
    public virtual void OnStart(IMapContext context)
    {
        Context = context;
        Context.Log("start:" + Read());
        SessionHooks.Capture();
    }
    public virtual void OnTick(MapTick tick)
    {
        Context.Log("tick:" + Read());
        SessionHooks.Capture();
    }
    public virtual void OnStop() { Context.Log("stop:" + Read()); SessionHooks.Capture(); }
    private static int Read() => (int)typeof(SessionHooks).GetMethod(nameof(SessionHooks.Read))!.Invoke(null, null)!;
}

public sealed class DeniedConstructorScript : SessionScript
{
    public DeniedConstructorScript() => SessionHooks.ReflectEffect();
}
public sealed class DeniedStartScript : SessionScript
{
    public override void OnStart(IMapContext context) { base.OnStart(context); SessionHooks.ReflectEffect(); }
}
public sealed class DeniedTickScript : SessionScript
{
    public override void OnTick(MapTick tick) { base.OnTick(tick); SessionHooks.ReflectEffect(); }
}
public sealed class DeniedStopScript : SessionScript
{
    public override void OnStop() { base.OnStop(); SessionHooks.ReflectEffect(); }
}

public sealed class LoadingScript : SessionScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        if (!SessionHooks.LoadTarget(typeof(LoadingScript).Assembly)) throw new InvalidOperationException();
        context.Log("loaded:41");
    }
}

// Runs the review-finding probes from admitted author callbacks. Factory and
// stream probes run at OnStart; resolver-depth probes run from an explicit
// host-driven Tick so the harness can set the trusted-resolution simulation
// without changing session startup.
public sealed class ReviewProbeScript : SessionScript
{
    public override void OnStart(IMapContext context)
    {
        base.OnStart(context);
        SessionHooks.ProbeFactories();
        SessionHooks.ProbeStreams();
        SessionHooks.OversizedSymbolsResult = SessionHooks.ProbeOversizedSymbols();
        context.Log("symbols:" + SessionHooks.OversizedSymbolsResult);
        context.Log("factory:" + SessionHooks.DynamicFactoryResult);
        context.Log("stub:" + SessionHooks.StubFactoryResult);
        context.Log("seekable:" + SessionHooks.SeekableStreamResult);
        context.Log("nonseekable:" + SessionHooks.NonseekableStreamResult);
    }

    public override void OnTick(MapTick tick)
    {
        base.OnTick(tick);
        SessionHooks.ProbeResolverEvent();
        SessionHooks.ProbeCrossSession();
        Context.Log("resolver:" + SessionHooks.ResolverEventResult);
        Context.Log("cross:" + SessionHooks.CrossSessionResult);
    }
}
