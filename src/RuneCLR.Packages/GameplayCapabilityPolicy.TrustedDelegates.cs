using System.Collections.Immutable;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using static RuneCLR.Packages.TrustedDelegateProvider;

namespace RuneCLR.Packages;

public static partial class GameplayCapabilityPolicy
{
    /// <summary>Opt-in author intake with standard BCL delegates and selected actual definitions from
    /// host-controlled trusted framework bytes. The host must bind each provider's recorded hash and
    /// full identity to its real shared assembly; metadata itself does not authenticate a provider.
    /// Strict and standard-only entry points do not enable this optional capability.</summary>
    public static void ValidateWithTrustedManagedDelegates(ReadOnlyMemory<byte> image,
        IReadOnlyCollection<string> privateAssemblyIdentities, string contractAssemblyIdentity, IApiAccessPolicy apiPolicy,
        IReadOnlyCollection<TrustedDelegateProvider> trustedProviders,
        bool allowReflectionTypeTokens = false, bool allowSessionAssemblyNames = false)
    {
        ArgumentNullException.ThrowIfNull(privateAssemblyIdentities);
        ArgumentNullException.ThrowIfNull(apiPolicy);
        ArgumentNullException.ThrowIfNull(trustedProviders);
        if (trustedProviders.Count > 64) throw new ArgumentException("At most 64 trusted delegate providers are supported.", nameof(trustedProviders));
        var providers = ImmutableDictionary.CreateBuilder<string, TrustedDelegateProvider>(StringComparer.OrdinalIgnoreCase);
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var provider in trustedProviders)
        {
            if (provider is null || !names.Add(new System.Reflection.AssemblyName(provider.AssemblyIdentity).Name!))
                throw new ArgumentException("Null, duplicate or conflicting trusted delegate provider.", nameof(trustedProviders));
            providers.Add(provider.AssemblyIdentity, provider);
        }
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw Invalid("Provide a nonempty assembly within the managed-IL image limit.");
        var snapshot = image.ToArray();
        _ = ManagedAssemblyInspector.Inspect(snapshot);
        ValidateCore(snapshot, privateAssemblyIdentities, contractAssemblyIdentity, null, null, apiPolicy,
            allowReflectionTypeTokens, allowSessionAssemblyNames, allowManagedDelegateConstruction: true,
            trustedDelegateProviders: providers.ToImmutable());
    }

    private sealed partial class Inspection
    {
        private readonly ImmutableDictionary<string, TrustedDelegateProvider>? trustedDelegateProviders;
        private readonly Dictionary<int, MethodShape> trustedConstructors = new();
        private Decoder EvidenceDecoder => new(metadata, ownIdentity);

        private bool TrustedDefinition(EntityHandle parent, out Definition definition, out ImmutableArray<Node> arguments)
        {
            definition = null!;
            arguments = [];
            if (trustedDelegateProviders is null || parent.Kind is not (HandleKind.TypeReference or HandleKind.TypeSpecification)) return false;
            var type = EvidenceDecoder.Type(parent);
            var root = type.Kind == NodeKind.Generic ? type.Children[0] : type;
            if (!trustedDelegateProviders.TryGetValue(root.Assembly, out var provider) ||
                !provider.Definitions.TryGetValue(root.Name, out definition!)) return false;
            if (type.Kind == NodeKind.Generic) arguments = type.Children.RemoveAt(0);
            if (arguments.Length != definition.Arity) throw Invalid("Trusted delegate generic arity does not match its definition.");
            foreach (var argument in arguments) DemandEvidenceType(argument);
            return true;
        }

        private bool CollectTrustedDelegateConstructor(MemberReferenceHandle handle, MemberReference member)
        {
            if (!TrustedDefinition(member.Parent, out var definition, out var arguments)) return false;
            var actual = EvidenceDecoder.Method(member.Signature);
            if (!definition.Methods[".ctor"].Same(actual)) throw Invalid("Trusted delegate constructor signature does not match its provider definition.");
            var invoke = definition.Methods["Invoke"].Substitute(arguments);
            foreach (var part in invoke.Types) DemandEvidenceType(part);
            trustedConstructors.Add(MetadataTokens.GetToken(handle), invoke);
            return true;
        }

        private void ValidateTrustedMember(MemberReference member, string name)
        {
            if (!TrustedDefinition(member.Parent, out var definition, out var arguments)) return;
            if (!definition.Methods.TryGetValue(name, out var method) || member.GetKind() != MemberReferenceKind.Method ||
                !method.Same(EvidenceDecoder.Method(member.Signature)))
                throw Invalid("Trusted delegate member signature does not match its provider definition.");
            if (name != ".ctor")
                foreach (var part in method.Substitute(arguments).Types) DemandEvidenceType(part);
        }

        private void DemandEvidenceType(Node node)
        {
            node.CheckSafe(int.MaxValue);
            if (node.Kind == NodeKind.Named)
            {
                ValidateAssembly(node.Assembly);
                Demand(new(node.Assembly, ApiTargetKind.Type, node.Name));
            }
            foreach (var child in node.Children) DemandEvidenceType(child);
        }

        private MethodShape Handler(EntityHandle handle, ImmutableArray<Node> methodArguments = default)
        {
            var decoder = EvidenceDecoder;
            if (handle.Kind == HandleKind.MethodSpecification)
            {
                var spec = metadata.GetMethodSpecification((MethodSpecificationHandle)handle);
                var args = spec.DecodeSignature(decoder, null);
                foreach (var arg in args) DemandEvidenceType(arg);
                return Handler(spec.Method, args);
            }
            MethodShape shape;
            Node declaring;
            string name;
            ImmutableArray<Node> typeArguments = default;
            if (handle.Kind == HandleKind.MethodDefinition)
            {
                var method = metadata.GetMethodDefinition((MethodDefinitionHandle)handle);
                declaring = decoder.Type(method.GetDeclaringType());
                name = metadata.GetString(method.Name);
                shape = decoder.Method(method.Signature);
            }
            else if (handle.Kind == HandleKind.MemberReference)
            {
                var member = metadata.GetMemberReference((MemberReferenceHandle)handle);
                if (member.GetKind() != MemberReferenceKind.Method) throw Invalid("A delegate target must be a managed method.");
                declaring = decoder.Type(member.Parent);
                name = metadata.GetString(member.Name);
                shape = decoder.Method(member.Signature);
                if (declaring.Kind == NodeKind.Generic) { typeArguments = declaring.Children.RemoveAt(0); declaring = declaring.Children[0]; }
            }
            else throw Invalid("Unsupported trusted delegate handler token.");
            if (name is ".ctor" or ".cctor") throw Invalid("A delegate handler cannot be a constructor.");
            DemandEvidenceType(declaring);
            Demand(new(declaring.Assembly, ApiTargetKind.Method, declaring.Name, name,
                new(shape.Return.Display, shape.Parameters.Select(n => n.Display).ToImmutableArray(), shape.Arity, (shape.Header & 0x20) != 0)));
            if (shape.Arity != (methodArguments.IsDefault ? 0 : methodArguments.Length))
                throw Invalid("Trusted delegate handler generic method arguments do not match.");
            var resolved = shape.Substitute(typeArguments, methodArguments);
            foreach (var part in resolved.Types) DemandEvidenceType(part);
            return resolved with { Header = 0x20, Arity = 0 };
        }

        private void ValidateTrustedHandler(EntityHandle handle, MethodShape invoke)
        {
            if (!invoke.Same(Handler(handle)))
                throw Invalid("Trusted delegate handler signature does not match the substituted Invoke definition (exact signatures required).");
        }
    }
}
