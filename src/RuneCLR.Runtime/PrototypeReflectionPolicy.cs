using System.Reflection;
using System.Runtime.Loader;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

/// <summary>Installs a trusted host's policy for the private reflection experiment.
/// This does not enable reflection in versioned gameplay packages or cover every reflection route.</summary>
public static class PrototypeReflectionPolicy
{
    // Only the fixed CoreLib entry is cached, never a policy, session or author metadata.
    private static readonly Lazy<Func<Action<MemberInfo, object?, object?[]?, int>, IDisposable>> Entry = new(Bind);
    private delegate IDisposable CreateSession(Action<MemberInfo, object?, object?[]?, int> check,
        AssemblyLoadContext context, Action<byte[], string?> admit, out Func<IDisposable> activate);
    private static readonly Lazy<CreateSession> SessionEntry = new(BindSession);

    public static IDisposable Enter(IApiAccessPolicy policy)
    {
        ArgumentNullException.ThrowIfNull(policy);
        var enter = Entry.Value;
        return enter(Checker(policy));
    }

    internal static void Prepare()
    {
        if (!AppContext.TryGetSwitch("RuneCLR.EnableReflectionPolicy", out bool enabled) || !enabled)
            throw new PlatformNotSupportedException("The RuneCLR reflection-policy experiment is disabled.");
        _ = SessionEntry.Value;
    }

    internal static ReflectionPolicySession Create(IApiAccessPolicy policy, AssemblyLoadContext context, Action<byte[], string?> admit)
    {
        ArgumentNullException.ThrowIfNull(policy);
        var session = SessionEntry.Value(Checker(policy, context), context, admit, out var activate);
        return new ReflectionPolicySession(session, activate);
    }

    private static Action<MemberInfo, object?, object?[]?, int> Checker(IApiAccessPolicy policy, AssemblyLoadContext? context = null)
    {
        var probe = context is null ? new ReflectionAccessProbe(policy) :
            new ReflectionAccessProbe(policy, assembly => AssemblyLoadContext.GetLoadContext(assembly) == context);
        return (member, receiver, arguments, operation) =>
        {
            // Wire IDs are independent of the public ApiOperation enum's ordinal values.
            switch (operation, member)
            {
                case (0, MethodInfo method): probe.DemandInvocation(method, receiver, arguments, runtimeDispatch: true); break;
                case (4, MethodInfo method) when method.IsVirtual && !method.IsStatic:
                    probe.DemandInvocation(method, receiver, arguments, runtimeDispatch: true, declaration: true); break;
                case (1, ConstructorInfo constructor): probe.DemandConstruction(constructor, receiver, arguments); break;
                case (2, FieldInfo field) when arguments is null: probe.DemandFieldRead(field, receiver); break;
                case (3, FieldInfo field) when arguments is { Length: 1 }: probe.DemandFieldWrite(field, receiver, arguments[0]); break;
                case (5, Type type) when receiver is null && arguments is null: probe.DemandDefaultConstruction(type); break;
                default: throw new InvalidOperationException("Unsupported reflection-policy operation or metadata shape.");
            }
        };
    }

    private static Func<Action<MemberInfo, object?, object?[]?, int>, IDisposable> Bind()
    {
        Func<Action<MemberInfo, object?, object?[]?, int>, IDisposable> enter;
        try
        {
            _ = RequiredInterpreterBridge.Bind();
            var type = typeof(MethodInfo).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", throwOnError: true)!;
            var version = RequiredInterpreterBridge.Method(type, "RuneCLR_GetReflectionPolicyVersion", true, typeof(int))
                .CreateDelegate<Func<int>>();
            if (version() != 4) throw new PlatformNotSupportedException("Reflection-policy version 4 is required.");
            enter = RequiredInterpreterBridge.Method(type, "RuneCLR_EnterReflectionPolicy", true, typeof(IDisposable),
                typeof(Action<MemberInfo, object?, object?[]?, int>))
                .CreateDelegate<Func<Action<MemberInfo, object?, object?[]?, int>, IDisposable>>();
        }
        catch (PlatformNotSupportedException) { throw; }
        catch (Exception error)
        {
            throw new PlatformNotSupportedException("The reflection-policy experiment needs matching private CoreLib/runtime support.", error);
        }

        return enter;
    }

    private static CreateSession BindSession()
    {
        _ = Entry.Value;
        return RequiredInterpreterBridge.Method(typeof(MethodInfo).Assembly.GetType("System.Reflection.RuneCLRReflectionPolicy", true)!,
            "RuneCLR_CreateReflectionPolicySession", true, typeof(IDisposable),
            typeof(Action<MemberInfo, object?, object?[]?, int>), typeof(AssemblyLoadContext), typeof(Action<byte[], string?>),
            typeof(Func<IDisposable>).MakeByRefType()).CreateDelegate<CreateSession>();
    }
}

internal sealed class ReflectionPolicySession(IDisposable owner, Func<IDisposable> activate) : IDisposable
{
    private IDisposable? _owner = owner;
    private Func<IDisposable>? _activate = activate;
    internal IDisposable Activate() => (_activate ?? throw new ObjectDisposedException(nameof(ReflectionPolicySession)))();
    public void Dispose()
    {
        _activate = null;
        Interlocked.Exchange(ref _owner, null)?.Dispose();
    }
}
