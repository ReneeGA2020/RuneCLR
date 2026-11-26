using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;

namespace RuneCLR.Packages;

/// <summary>Host-owned definition evidence for selected delegates in one trusted framework image.
/// Creation reads metadata only. The host must bind the recorded hash/identity to its actual provider;
/// this object neither authenticates the bytes nor loads them. It stores no reflection objects.</summary>
public sealed class TrustedDelegateProvider
{
    public string AssemblyIdentity { get; }
    public string ImageSha256 { get; }
    public ImmutableArray<string> DelegateTypeNames { get; }
    internal ImmutableDictionary<string, Definition> Definitions { get; }

    private TrustedDelegateProvider(string identity, string hash, ImmutableDictionary<string, Definition> definitions)
    {
        AssemblyIdentity = identity;
        ImageSha256 = hash;
        Definitions = definitions;
        DelegateTypeNames = definitions.Keys.Order(StringComparer.Ordinal).ToImmutableArray();
    }

    /// <summary>Selects actual delegate TypeDefs from trusted provider bytes, not from author claims.
    /// Provider native methods are not subjected to author intake. Selected delegates must themselves
    /// have ordinary managed runtime constructor/Invoke definitions and supported signatures.</summary>
    public static TrustedDelegateProvider Create(ReadOnlyMemory<byte> providerImage, params string[] delegateTypeNames)
    {
        ArgumentNullException.ThrowIfNull(delegateTypeNames);
        if (providerImage.IsEmpty || providerImage.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw new InvalidDataException("A trusted delegate provider must be a bounded managed image.");
        if (delegateTypeNames.Length is < 1 or > 256)
            throw new ArgumentException("Select between 1 and 256 delegate definitions.", nameof(delegateTypeNames));
        var names = delegateTypeNames.ToArray();
        if (names.Any(n => string.IsNullOrWhiteSpace(n) || n.Length > 1024) ||
            names.Distinct(StringComparer.Ordinal).Count() != names.Length)
            throw new ArgumentException("Delegate definition names must be nonempty, bounded and unique.", nameof(delegateTypeNames));
        var snapshot = providerImage.ToArray();
        try
        {
            using var pe = new PEReader(ImmutableArray.CreateRange(snapshot));
            if (!pe.HasMetadata) throw Error("Provider has no managed metadata.");
            var reader = pe.GetMetadataReader(MetadataReaderOptions.None);
            if (!reader.IsAssembly) throw Error("Provider must be an assembly.");
            var identity = Identity(reader);
            var decoder = new Decoder(reader, identity);
            var definitions = ImmutableDictionary.CreateBuilder<string, Definition>(StringComparer.Ordinal);
            var selected = names.ToHashSet(StringComparer.Ordinal);
            foreach (var handle in reader.TypeDefinitions)
            {
                var node = decoder.Type(handle);
                if (!selected.Contains(node.Name)) continue;
                var type = reader.GetTypeDefinition(handle);
                var parent = decoder.Type(type.BaseType);
                if (parent.Kind != NodeKind.Named || parent.Name != "System.MulticastDelegate" || !IsBcl(parent.Assembly) ||
                    (type.Attributes & TypeAttributes.Sealed) == 0 || type.GetFields().Count != 0 ||
                    type.GetInterfaceImplementations().Count != 0)
                    throw Error("Selected type is not a sealed standard-shaped managed delegate: " + node.Name);
                var arity = type.GetGenericParameters().Count;
                var parameters = type.GetGenericParameters().Select(reader.GetGenericParameter).ToArray();
                if (!parameters.Select(p => p.Index).Order().SequenceEqual(Enumerable.Range(0, arity)))
                    throw Error("Inconsistent delegate generic parameters.");
                var methods = ImmutableDictionary.CreateBuilder<string, MethodShape>(StringComparer.Ordinal);
                foreach (var methodHandle in type.GetMethods())
                {
                    var method = reader.GetMethodDefinition(methodHandle);
                    var name = reader.GetString(method.Name);
                    if (name is not (".ctor" or "Invoke" or "BeginInvoke" or "EndInvoke") || methods.ContainsKey(name) ||
                        (method.Attributes & (MethodAttributes.Static | MethodAttributes.PinvokeImpl | MethodAttributes.Abstract)) != 0 ||
                        (method.Attributes & MethodAttributes.MemberAccessMask) != MethodAttributes.Public ||
                        method.ImplAttributes != MethodImplAttributes.Runtime || method.RelativeVirtualAddress != 0)
                        throw Error("Unsupported managed delegate method definition: " + node.Name + "." + name);
                    var shape = decoder.Method(method.Signature);
                    if (shape.Header != 0x20 || shape.Arity != 0 ||
                        name != ".ctor" && (method.Attributes & (MethodAttributes.Virtual | MethodAttributes.NewSlot)) !=
                            (MethodAttributes.Virtual | MethodAttributes.NewSlot))
                        throw Error("Delegate methods require ordinary instance runtime signatures.");
                    if (name == ".ctor")
                    {
                        if (!shape.CanonicalConstructor ||
                            (method.Attributes & (MethodAttributes.SpecialName | MethodAttributes.RTSpecialName)) !=
                                (MethodAttributes.SpecialName | MethodAttributes.RTSpecialName))
                            throw Error("Delegate constructor requires instance void(object, native int) and constructor flags.");
                    }
                    else foreach (var part in shape.Types) part.CheckSafe(arity);
                    methods.Add(name, shape);
                }
                if (!methods.ContainsKey(".ctor") || !methods.ContainsKey("Invoke"))
                    throw Error("Delegate constructor or Invoke definition is missing.");
                definitions.Add(node.Name, new(arity, methods.ToImmutable()));
            }
            if (definitions.Count != selected.Count) throw Error("A selected delegate definition was not found in the provider.");
            return new(identity, Convert.ToHexString(SHA256.HashData(snapshot)).ToLowerInvariant(), definitions.ToImmutable());
        }
        catch (Exception e) when (e is BadImageFormatException or ArgumentException or InvalidOperationException or
            IndexOutOfRangeException or OverflowException)
        { throw Error("Malformed trusted delegate metadata: " + e.GetType().Name); }
    }

    internal sealed record Definition(int Arity, ImmutableDictionary<string, MethodShape> Methods);
    internal enum NodeKind { Primitive, Named, TypeParameter, MethodParameter, Generic, SzArray, Array, ByRef }
    internal sealed record Node(NodeKind Kind, string Name, string Assembly, ImmutableArray<Node> Children)
    {
        internal string Display => Kind switch
        {
            NodeKind.TypeParameter => "!" + Name, NodeKind.MethodParameter => "!!" + Name,
            NodeKind.Generic => Children[0].Display + "<" + string.Join(",", Children.Skip(1).Select(n => n.Display)) + ">",
            NodeKind.SzArray => Children[0].Display + "[]", NodeKind.Array => Children[0].Display + Name,
            NodeKind.ByRef => Children[0].Display + "&", _ => Name
        };
        internal bool Same(Node other) => Kind == other.Kind && Name == other.Name &&
            StringComparer.OrdinalIgnoreCase.Equals(Assembly, other.Assembly) && Children.Length == other.Children.Length &&
            Children.Zip(other.Children).All(p => p.First.Same(p.Second));
        internal Node Substitute(ImmutableArray<Node> types, ImmutableArray<Node> methods = default)
        {
            if (Kind == NodeKind.TypeParameter || Kind == NodeKind.MethodParameter)
            {
                var args = Kind == NodeKind.TypeParameter ? types : methods;
                var index = int.Parse(Name, System.Globalization.CultureInfo.InvariantCulture);
                if (args.IsDefault) return this;
                if (index < 0 || index >= args.Length) throw Error("Generic signature argument is out of range.");
                return args[index];
            }
            return this with { Children = Children.Select(n => n.Substitute(types, methods)).ToImmutableArray() };
        }
        internal void CheckSafe(int typeArity)
        {
            if (Name is "System.IntPtr" or "System.UIntPtr" or "System.TypedReference" ||
                Kind == NodeKind.MethodParameter || Kind == NodeKind.TypeParameter &&
                (!int.TryParse(Name, out var index) || index < 0 || index >= typeArity))
                throw Error("Unsafe or out-of-range trusted delegate signature type.");
            foreach (var child in Children) child.CheckSafe(typeArity);
        }
    }
    internal sealed record MethodShape(byte Header, int Arity, Node Return, ImmutableArray<Node> Parameters)
    {
        internal IEnumerable<Node> Types => Parameters.Prepend(Return);
        internal bool CanonicalConstructor => Header == 0x20 && Arity == 0 && Return.Kind == NodeKind.Primitive &&
            Return.Name == "System.Void" && Parameters.Length == 2 && Parameters[0].Kind == NodeKind.Primitive &&
            Parameters[0].Name == "System.Object" && Parameters[1].Kind == NodeKind.Primitive && Parameters[1].Name == "System.IntPtr";
        internal bool Same(MethodShape other) => Header == other.Header && Arity == other.Arity && Return.Same(other.Return) &&
            Parameters.Length == other.Parameters.Length && Parameters.Zip(other.Parameters).All(p => p.First.Same(p.Second));
        internal MethodShape Substitute(ImmutableArray<Node> types, ImmutableArray<Node> methods = default) =>
            this with { Return = Return.Substitute(types, methods), Parameters = Parameters.Select(n => n.Substitute(types, methods)).ToImmutableArray() };
    }

    internal static InvalidDataException Error(string message) => new("Trusted delegate metadata: " + message);
    internal static bool IsBcl(string identity)
    {
        var name = new AssemblyName(identity);
        var token = Convert.ToHexString(name.GetPublicKeyToken() ?? []).ToLowerInvariant();
        return name.Name == "System.Runtime" && token == "b03f5f7f11d50a3a" ||
            name.Name == "System.Private.CoreLib" && token == "7cec85d7bea7798e";
    }
    internal static string Identity(MetadataReader reader)
    {
        var d = reader.GetAssemblyDefinition();
        var name = new AssemblyName { Name = reader.GetString(d.Name), Version = d.Version, CultureName = reader.GetString(d.Culture),
            Flags = (AssemblyNameFlags)(d.Flags & AssemblyFlags.Retargetable),
            ContentType = (d.Flags & AssemblyFlags.WindowsRuntime) != 0 ? AssemblyContentType.WindowsRuntime : AssemblyContentType.Default };
        var key = reader.GetBlobBytes(d.PublicKey);
        if (key.Length == 0) name.SetPublicKeyToken([]); else name.SetPublicKey(key);
        return name.FullName!;
    }
    internal static string Reference(MetadataReader reader, AssemblyReferenceHandle handle)
    {
        var d = reader.GetAssemblyReference(handle);
        var name = new AssemblyName { Name = reader.GetString(d.Name), Version = d.Version, CultureName = reader.GetString(d.Culture),
            Flags = (AssemblyNameFlags)(d.Flags & AssemblyFlags.Retargetable),
            ContentType = (d.Flags & AssemblyFlags.WindowsRuntime) != 0 ? AssemblyContentType.WindowsRuntime : AssemblyContentType.Default };
        var key = reader.GetBlobBytes(d.PublicKeyOrToken);
        if ((d.Flags & AssemblyFlags.PublicKey) != 0) name.SetPublicKey(key); else name.SetPublicKeyToken(key);
        return name.FullName!;
    }

    internal sealed class Decoder(MetadataReader reader, string identity) : ISignatureTypeProvider<Node, object?>
    {
        private int depth;
        private static Node Leaf(NodeKind kind, string name, string assembly = "") => new(kind, name, assembly, []);
        internal Node Type(EntityHandle handle)
        {
            if (++depth > 64) throw Error("Type nesting exceeds 64.");
            try
            {
                var node = handle.Kind switch
                {
                    HandleKind.TypeDefinition => GetTypeFromDefinition(reader, (TypeDefinitionHandle)handle, 0),
                    HandleKind.TypeReference => GetTypeFromReference(reader, (TypeReferenceHandle)handle, 0),
                    HandleKind.TypeSpecification => GetTypeFromSpecification(reader, null, (TypeSpecificationHandle)handle, 0),
                    _ => throw Error("Unsupported type scope.")
                };
                if (node.Display.Length > 4096) throw Error("Signature type is oversized.");
                return node;
            }
            finally { depth--; }
        }
        internal MethodShape Method(BlobHandle blob)
        {
            Bound(blob);
            var signature = new SignatureDecoder<Node, object?>(this, reader, null);
            var bytes = reader.GetBlobReader(blob);
            var method = signature.DecodeMethodSignature(ref bytes);
            if (bytes.RemainingBytes != 0 || method.RequiredParameterCount != method.ParameterTypes.Length ||
                method.Header.CallingConvention != SignatureCallingConvention.Default || method.Header.HasExplicitThis)
                throw Error("Unsupported or trailing method signature data.");
            return new(method.Header.RawValue, method.GenericParameterCount, method.ReturnType, method.ParameterTypes);
        }
        private void Bound(BlobHandle blob) { if (reader.GetBlobReader(blob).Length > 512) throw Error("Signature exceeds 512 bytes."); }
        public Node GetPrimitiveType(PrimitiveTypeCode code) => Leaf(NodeKind.Primitive, "System." + code);
        public Node GetTypeFromDefinition(MetadataReader r, TypeDefinitionHandle h, byte kind)
        {
            var t = r.GetTypeDefinition(h);
            var outer = t.GetDeclaringType();
            var name = r.GetString(t.Name);
            if (!outer.IsNil) name = Type(outer).Name + "+" + name;
            else if (r.GetString(t.Namespace) is { Length: > 0 } ns) name = ns + "." + name;
            return Leaf(NodeKind.Named, name, identity);
        }
        public Node GetTypeFromReference(MetadataReader r, TypeReferenceHandle h, byte kind)
        {
            var t = r.GetTypeReference(h);
            var name = r.GetString(t.Name);
            if (t.ResolutionScope.Kind == HandleKind.TypeReference)
            {
                var outer = Type(t.ResolutionScope);
                return Leaf(NodeKind.Named, outer.Name + "+" + name, outer.Assembly);
            }
            if (t.ResolutionScope.Kind != HandleKind.AssemblyReference) throw Error("Type reference requires assembly scope.");
            if (r.GetString(t.Namespace) is { Length: > 0 } ns) name = ns + "." + name;
            return Leaf(NodeKind.Named, name, Reference(r, (AssemblyReferenceHandle)t.ResolutionScope));
        }
        public Node GetTypeFromSpecification(MetadataReader r, object? context, TypeSpecificationHandle h, byte kind)
        {
            if (++depth > 64) throw Error("Type specification nesting exceeds 64.");
            try
            {
                var blob = r.GetTypeSpecification(h).Signature;
                Bound(blob);
                // The depth guard also bounds cyclic TypeSpec rows.
                var bytes = r.GetBlobReader(blob);
                var result = new SignatureDecoder<Node, object?>(this, r, null).DecodeType(ref bytes);
                if (bytes.RemainingBytes != 0) throw Error("Trailing type signature data.");
                return result;
            }
            finally { depth--; }
        }
        public Node GetGenericInstantiation(Node type, ImmutableArray<Node> args) => new(NodeKind.Generic, "", "", args.Insert(0, type));
        public Node GetGenericTypeParameter(object? c, int index) => Leaf(NodeKind.TypeParameter, index.ToString(System.Globalization.CultureInfo.InvariantCulture));
        public Node GetGenericMethodParameter(object? c, int index) => Leaf(NodeKind.MethodParameter, index.ToString(System.Globalization.CultureInfo.InvariantCulture));
        public Node GetSZArrayType(Node t) => new(NodeKind.SzArray, "", "", [t]);
        public Node GetArrayType(Node t, ArrayShape s) => s.Rank is >= 1 and <= 32 && s.LowerBounds.IsEmpty && s.Sizes.IsEmpty
            ? new(NodeKind.Array, "[" + new string(',', s.Rank - 1) + "]", "", [t]) : throw Error("Unsupported array bounds.");
        public Node GetByReferenceType(Node t) => new(NodeKind.ByRef, "", "", [t]);
        public Node GetModifiedType(Node m, Node t, bool required) => throw Error("Modified delegate signature types are unsupported.");
        public Node GetPinnedType(Node t) => throw Error("Pinned delegate signatures are unsupported.");
        public Node GetPointerType(Node t) => throw Error("Pointer delegate signatures are unsupported.");
        public Node GetFunctionPointerType(MethodSignature<Node> s) => throw Error("Function-pointer delegate signatures are unsupported.");
    }
}
