using System.Collections.Immutable;
using System.Reflection;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

/// <summary>A trusted-boundary experiment, not automatic interception of author reflection.
/// The shipped gameplay profile still denies general reflection; runtime entry coverage is separate.</summary>
public sealed class ReflectionAccessProbe(IApiAccessPolicy policy)
{
    private readonly IApiAccessPolicy policy = policy ?? throw new ArgumentNullException(nameof(policy));
    private readonly Func<Assembly, bool>? sessionOwns;

    internal ReflectionAccessProbe(IApiAccessPolicy policy, Func<Assembly, bool> sessionOwns) : this(policy)
        => this.sessionOwns = sessionOwns;

    public object? Invoke(MethodInfo method, object? instance, params object?[]? arguments)
    {
        DemandInvocation(method, instance, arguments);
        return method.Invoke(instance, arguments);
    }

    internal void DemandInvocation(MethodInfo method, object? instance, object?[]? arguments,
        bool runtimeDispatch = false, bool declaration = false)
    {
        ArgumentNullException.ThrowIfNull(method);
        DemandMethod(method, ApiOperation.Invoke, instance, runtimeDispatch, declaration);
        DemandArguments(arguments);
    }

    public object Construct(ConstructorInfo constructor, params object?[]? arguments)
    {
        DemandConstruction(constructor, null, arguments);
        return constructor.Invoke(arguments);
    }

    internal void DemandConstruction(ConstructorInfo constructor, object? instance, object?[]? arguments)
    {
        ArgumentNullException.ThrowIfNull(constructor);
        DemandMethod(constructor, ApiOperation.Construct, null);
        if (instance is not null)
        {
            if (!constructor.DeclaringType!.IsInstanceOfType(instance))
                throw Refuse("The constructor requires a compatible existing receiver.");
            DemandType(instance.GetType());
        }
        DemandArguments(arguments);
    }

    internal void DemandDefaultConstruction(Type type)
    {
        if (!type.IsValueType || type.ContainsGenericParameters)
            throw Refuse("An implicit default construction requires a closed value type.");
        DemandType(type);
        Demand(Describe(type), ApiOperation.Construct);
    }

    public object? Read(FieldInfo field, object? instance)
    {
        DemandField(field, ApiOperation.ReadField, instance);
        return field.GetValue(instance);
    }

    public void Write(FieldInfo field, object? instance, object? value)
    {
        DemandFieldWrite(field, instance, value);
        field.SetValue(instance, value);
    }

    internal void DemandFieldRead(FieldInfo field, object? instance) => DemandField(field, ApiOperation.ReadField, instance);

    internal void DemandFieldWrite(FieldInfo field, object? instance, object? value)
    {
        DemandField(field, ApiOperation.WriteField, instance);
        if (field.IsInitOnly || field.IsLiteral) throw Refuse("Writing readonly or literal fields is unsupported by this probe.");
        if (value is not null) DemandType(value.GetType());
    }

    public object? Read(PropertyInfo property, object? instance)
    {
        ArgumentNullException.ThrowIfNull(property);
        return Invoke(property.GetGetMethod(true) ?? throw Refuse("The property has no getter."), instance);
    }

    public void Write(PropertyInfo property, object? instance, object? value)
    {
        ArgumentNullException.ThrowIfNull(property);
        _ = Invoke(property.GetSetMethod(true) ?? throw Refuse("The property has no setter."), instance, value);
    }

    public ApiTarget Inspect(MemberInfo member)
    {
        ArgumentNullException.ThrowIfNull(member);
        var target = Describe(member);
        Demand(target, ApiOperation.ReadMetadata);
        switch (member)
        {
            case Type type: DemandType(type); break;
            case MethodBase method: DemandSignature(method); break;
            case FieldInfo field: DemandType(field.DeclaringType!); DemandType(field.FieldType); break;
        }
        return target;
    }

    public Delegate CreateDelegate(MethodInfo method, Type delegateType, object? instance = null)
    {
        ArgumentNullException.ThrowIfNull(method);
        ArgumentNullException.ThrowIfNull(delegateType);
        Demand(Describe(method), ApiOperation.CreateDelegate);
        // Delegate lifetime/dispatch enforcement is not established by the initial probe.
        throw Refuse("Delegate creation is unsupported by this probe.");
    }

    private void DemandMethod(MethodBase method, ApiOperation operation, object? instance,
        bool runtimeDispatch = false, bool declaration = false)
    {
        var target = Describe(method);
        Demand(target, operation);
        if (method.ContainsGenericParameters || method.IsAbstract && !declaration || method.IsStatic && method is ConstructorInfo)
            throw Refuse("Open, abstract or static-constructor invocation is unsupported by this probe.");
        DemandSignature(method);
        if (!method.IsStatic && method is not ConstructorInfo)
        {
            if (instance is null || !method.DeclaringType!.IsInstanceOfType(instance))
                throw Refuse("The invocation requires a compatible receiver.");
            DemandType(instance.GetType());
            // A runtime bridge must resolve actual dispatch. Do not check a base method then execute an unchecked override.
            if (!runtimeDispatch && method.IsVirtual && !method.IsFinal && instance.GetType() != method.DeclaringType)
                throw Refuse("Polymorphic reflection dispatch is unsupported by this probe.");
        }
    }

    private void DemandSignature(MethodBase method)
    {
        DemandType(method.DeclaringType!);
        if (method.CallingConvention.HasFlag(CallingConventions.VarArgs))
            throw Refuse("Vararg invocation is unsupported by this probe.");
        if (method is MethodInfo info)
        {
            DemandType(info.ReturnType);
            if (info.IsGenericMethod)
                foreach (var type in info.GetGenericArguments()) DemandType(type);
        }
        foreach (var parameter in method.GetParameters()) DemandType(parameter.ParameterType);
    }

    private void DemandField(FieldInfo field, ApiOperation operation, object? instance)
    {
        ArgumentNullException.ThrowIfNull(field);
        Demand(Describe(field), operation);
        DemandType(field.DeclaringType!);
        DemandType(field.FieldType);
        if (!field.IsStatic)
        {
            if (instance is null || !field.DeclaringType!.IsInstanceOfType(instance))
                throw Refuse("The field requires a compatible receiver.");
            DemandType(instance.GetType());
        }
    }

    private void DemandArguments(object?[]? arguments)
    {
        if (arguments is null) return;
        foreach (var value in arguments)
            if (value is not null) DemandType(value.GetType());
    }

    private void DemandType(Type type)
    {
        if (type == typeof(void)) return;
        if (type.IsGenericParameter) return;
        if (type.IsByRef || type.IsPointer || type.IsFunctionPointer || type.IsByRefLike ||
            type == typeof(IntPtr) || type == typeof(UIntPtr) || type == typeof(TypedReference))
            throw Refuse("Byref, native and byref-like types are unsupported by this probe.");
        if (type.IsArray)
        {
            DemandType(type.GetElementType()!);
            return;
        }
        Demand(Describe(type), ApiOperation.Reference);
        if (type.IsGenericType)
            foreach (var argument in type.GetGenericArguments()) DemandType(argument);
    }

    private ApiTarget Describe(MemberInfo member)
    {
        if (member.GetType().Assembly != typeof(object).Assembly || member is TypeDelegator)
            throw Refuse("Only runtime reflection metadata is supported by this probe.");
        var type = member as Type ?? member.DeclaringType ?? throw Refuse("Global members are unsupported by this probe.");
        if (type.IsConstructedGenericType) type = type.GetGenericTypeDefinition();
        var identity = type.Assembly.GetName().FullName!;
        var name = type.FullName ?? throw Refuse("A concrete declaring type name is required.");
        ApiTarget target = member switch
        {
            Type => new(identity, ApiTargetKind.Type, name),
            MethodBase method => new(identity, ApiTargetKind.Method, name, member.Name, Signature(method)),
            FieldInfo => new(identity, ApiTargetKind.Field, name, member.Name),
            _ => throw Refuse("This metadata target is unsupported by the initial probe.")
        };
        return sessionOwns?.Invoke(type.Assembly) == true ? target with { IsSessionCode = true } : target;
    }

    private static ApiMethodSignature Signature(MethodBase method)
    {
        if (method.DeclaringType!.IsConstructedGenericType)
        {
            var definition = method.DeclaringType.GetGenericTypeDefinition();
            const BindingFlags flags = BindingFlags.DeclaredOnly | BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
            method = definition.GetMembers(flags).OfType<MethodBase>()
                .Single(candidate => candidate.Module == method.Module && candidate.MetadataToken == method.MetadataToken);
        }
        if (method is MethodInfo generic && generic.IsGenericMethod) method = generic.GetGenericMethodDefinition();
        return new(method is MethodInfo info ? TypeSignature(info.ReturnType) : "System.Void",
            method.GetParameters().Select(parameter => TypeSignature(parameter.ParameterType)).ToImmutableArray(),
            method.IsGenericMethod ? method.GetGenericArguments().Length : 0, !method.IsStatic);
    }

    private static string TypeSignature(Type type)
    {
        if (type.IsGenericParameter) return (type.DeclaringMethod is null ? "!" : "!!") + type.GenericParameterPosition;
        if (type.IsByRef || type.IsPointer) return TypeSignature(type.GetElementType()!) + (type.IsByRef ? "&" : "*");
        if (type.IsArray) return TypeSignature(type.GetElementType()!) + "[" + new string(',', type.GetArrayRank() - 1) + "]";
        if (type.IsGenericType)
            return type.GetGenericTypeDefinition().FullName + "<" + string.Join(",", type.GetGenericArguments().Select(TypeSignature)) + ">";
        return type.FullName ?? type.Name;
    }

    private void Demand(ApiTarget target, ApiOperation operation)
    {
        var decision = policy.Evaluate(target, operation);
        if (!decision.Allowed) throw Refuse(decision.Reason ?? "The target is not approved.");
    }

    private static InvalidOperationException Refuse(string message) => new("Reflection access: " + message);
}
