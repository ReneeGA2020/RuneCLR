using System.Reflection;
using RuneCLR.Packages;

namespace RuneCLR.Runtime;

// Enforces the manifest allow-list against the actual contract surface while
// leaving trust decisions to the host evaluator. It maps both interface methods
// and the supplied instance's concrete implementations/aliases.
internal sealed class HostContractAllowedMethodsPolicy : IApiAccessPolicy
{
    private readonly IApiAccessPolicy _inner;
    private readonly Dictionary<MemberKey, bool> _members = new(MemberKeyComparer.Instance);

    internal HostContractAllowedMethodsPolicy(IApiAccessPolicy inner, Type contract, object instance,
        IReadOnlyCollection<string> allowedMethods)
    {
        ArgumentNullException.ThrowIfNull(inner);
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(instance);
        ArgumentNullException.ThrowIfNull(allowedMethods);
        _inner = inner;
        var allowed = new HashSet<string>(allowedMethods, StringComparer.Ordinal);
        var interfaces = new List<Type> { contract };
        interfaces.AddRange(contract.GetInterfaces());
        foreach (var iface in interfaces)
        {
            foreach (var method in iface.GetMethods(BindingFlags.Public | BindingFlags.Instance |
                                                    BindingFlags.Static | BindingFlags.DeclaredOnly))
                Add(method, allowed.Contains(method.Name));
        }

        var implementation = instance.GetType();
        foreach (var iface in interfaces)
        {
            InterfaceMapping map;
            try { map = implementation.GetInterfaceMap(iface); }
            catch (ArgumentException error)
            {
                throw new InvalidOperationException(
                    "The supplied host instance cannot be mapped to the host contract.", error);
            }
            for (int i = 0; i < map.InterfaceMethods.Length; i++)
            {
                MethodInfo? target = map.TargetMethods[i];
                if (target is not null)
                    Add(target, allowed.Contains(map.InterfaceMethods[i].Name));
            }
        }
    }

    public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
    {
        if (target.Kind == ApiTargetKind.Method && target.TypeName is not null &&
            target.MemberName is not null &&
            _members.TryGetValue(new MemberKey(target.AssemblyIdentity, target.TypeName, target.MemberName),
                out bool allowed) && !allowed)
            return ApiDecision.Deny("Host contract method '" + target.TypeName + "." + target.MemberName +
                                    "' is not listed in allowedMethods.");
        return _inner.Evaluate(target, operation);
    }

    private void Add(MethodInfo method, bool allowed)
    {
        AddKey(method, allowed);

        MethodInfo? baseDefinition = method.GetBaseDefinition();
        if (baseDefinition is not null && baseDefinition != method)
            AddKey(baseDefinition, allowed);

        ParameterInfo[] parameters = method.GetParameters();
        Type[] parameterTypes = parameters.Select(parameter => parameter.ParameterType).ToArray();
        const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic |
                                   BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.ExactBinding;
        for (Type? type = method.DeclaringType?.BaseType; type is not null; type = type.BaseType)
        {
            MethodInfo? candidate;
            try { candidate = type.GetMethod(method.Name, flags, binder: null, types: parameterTypes, modifiers: null); }
            catch (AmbiguousMatchException) { candidate = null; }
            if (candidate is not null)
                AddKey(candidate, allowed);
        }
    }

    private void AddKey(MethodInfo method, bool allowed)
    {
        Type? type = method.DeclaringType;
        if (type is null) return;
        // ApiTarget and ReflectionAccessProbe both describe the declaring generic
        // definition, so constructed generic interface/implementation methods must
        // use the same key space here.
        if (type.IsConstructedGenericType) type = type.GetGenericTypeDefinition();
        if (type.FullName is not string typeName) return;
        var key = new MemberKey(type.Assembly.GetName().FullName!, typeName, method.Name);
        if (!_members.TryGetValue(key, out bool previous) || (previous && !allowed))
            _members[key] = allowed;
    }

    private readonly record struct MemberKey(string Assembly, string Type, string Member);

    private sealed class MemberKeyComparer : IEqualityComparer<MemberKey>
    {
        internal static readonly MemberKeyComparer Instance = new();

        public bool Equals(MemberKey x, MemberKey y) =>
            string.Equals(x.Assembly, y.Assembly, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(x.Type, y.Type, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(x.Member, y.Member, StringComparison.OrdinalIgnoreCase);

        public int GetHashCode(MemberKey key) => HashCode.Combine(
            StringComparer.OrdinalIgnoreCase.GetHashCode(key.Assembly),
            StringComparer.OrdinalIgnoreCase.GetHashCode(key.Type),
            StringComparer.OrdinalIgnoreCase.GetHashCode(key.Member));
    }
}
