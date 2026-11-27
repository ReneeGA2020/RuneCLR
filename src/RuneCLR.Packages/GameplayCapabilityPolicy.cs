using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

namespace RuneCLR.Packages;

/// <summary>Rejects metadata outside the initial synchronous gameplay API profile without loading author code.
/// This is a static compatibility gate, not semantic IL verification, execution metering or a security sandbox.</summary>
public static partial class GameplayCapabilityPolicy
{
    public const string Profile = "managed-il-gameplay-v1";

    public static void Validate(ReadOnlyMemory<byte> image, IReadOnlyCollection<string> privateAssemblyIdentities,
        string contractAssemblyIdentity,
        string? hostInterface = null, IReadOnlyCollection<string>? allowedMethods = null)
        => ValidateCore(image, privateAssemblyIdentities, contractAssemblyIdentity, hostInterface, allowedMethods, null);

    /// <summary>Validates the managed-IL envelope with a trusted caller's target policy.
    /// Versioned packages still use the fixed gameplay profile; this does not select a new loader profile.</summary>
    public static void ValidateWithApiPolicy(ReadOnlyMemory<byte> image, IReadOnlyCollection<string> privateAssemblyIdentities,
        string contractAssemblyIdentity, IApiAccessPolicy apiPolicy,
        string? hostInterface = null, IReadOnlyCollection<string>? allowedMethods = null, bool allowReflectionTypeTokens = false,
        bool allowSessionAssemblyNames = false)
    {
        ArgumentNullException.ThrowIfNull(apiPolicy);
        ValidateCore(image, privateAssemblyIdentities, contractAssemblyIdentity, hostInterface, allowedMethods, apiPolicy,
            allowReflectionTypeTokens, allowSessionAssemblyNames);
    }

    /// <summary>Grouped-host admission: same ValidateCore as ValidateWithApiPolicy, plus the
    /// metadata-proven managed delegate constructor exception, with the group's type-token/name options.
    /// External loaders opt in separately through ValidateWithStandardManagedDelegates;
    /// Validate and ValidateWithApiPolicy keep their legacy strict behavior.</summary>
    internal static void ValidateGroupedHostWithApiPolicy(ReadOnlyMemory<byte> image,
        IReadOnlyCollection<string> privateAssemblyIdentities, string contractAssemblyIdentity, IApiAccessPolicy apiPolicy)
    {
        ArgumentNullException.ThrowIfNull(apiPolicy);
        ValidateCore(image, privateAssemblyIdentities, contractAssemblyIdentity, null, null, apiPolicy,
            allowReflectionTypeTokens: true, allowSessionAssemblyNames: true, allowManagedDelegateConstruction: true);
    }

    private static void ValidateCore(ReadOnlyMemory<byte> image, IReadOnlyCollection<string> privateAssemblyIdentities,
        string contractAssemblyIdentity, string? hostInterface, IReadOnlyCollection<string>? allowedMethods, IApiAccessPolicy? apiPolicy,
        bool allowReflectionTypeTokens = false, bool allowSessionAssemblyNames = false,
        bool allowManagedDelegateConstruction = false,
        ImmutableDictionary<string, TrustedDelegateProvider>? trustedDelegateProviders = null)
    {
        ArgumentNullException.ThrowIfNull(privateAssemblyIdentities);
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw Invalid("Provide a nonempty assembly within the managed-IL image limit.");
        try
        {
            using var pe = new PEReader(ImmutableArray.CreateRange(image.ToArray()));
            var reader = pe.GetMetadataReader(MetadataReaderOptions.None);
            new Inspection(reader, pe, privateAssemblyIdentities, contractAssemblyIdentity, hostInterface, allowedMethods, apiPolicy,
                allowReflectionTypeTokens, allowSessionAssemblyNames, allowManagedDelegateConstruction, trustedDelegateProviders).Validate();
        }
        catch (Exception error) when (error is BadImageFormatException or ArgumentException or
            InvalidOperationException or IndexOutOfRangeException or OverflowException)
        {
            throw Invalid($"Malformed capability metadata or IL: {error.Message}", error);
        }
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null)
    {
        var prefix = $"Capability profile '{Profile}': ";
        const int maximumCharacters = 2_048;
        var remaining = maximumCharacters - prefix.Length;
        return new(prefix + (message.Length > remaining ? message[..(remaining - 3)] + "..." : message), inner);
    }

    // Names are enumerated per type. Signatures are checked independently, including unused helpers and attributes.
    // Accepted framework calls can still allocate heavily or execute for a long time; there is no cost bound here.
    private static readonly Dictionary<string, HashSet<string>> Framework = CreateFrameworkSurface();
    private static readonly Dictionary<string, HashSet<string>> Contract = new(StringComparer.Ordinal)
    {
        ["RuneCLR.IMapScript"] = Members("OnStart OnTick OnStop"),
        // Signal, RaiseSignal, the tick schedule, Repeat, host-completed work, resource registration, and host-posted events are intentionally absent.
        // Delegate callbacks stay denied, and this profile has no timer or async surface.
        ["RuneCLR.IMapContext"] = Members("get_MapId SpawnEntity DestroyEntity Log Charge"),
        ["RuneCLR.EntityId"] = Members(".ctor get_Value set_Value Equals GetHashCode ToString Deconstruct op_Equality op_Inequality"),
        ["RuneCLR.MapTick"] = Members(".ctor get_Index set_Index get_Delta set_Delta Equals GetHashCode ToString Deconstruct op_Equality op_Inequality")
    };

    private static HashSet<string> Members(string names) => new(names.Split(' ', StringSplitOptions.RemoveEmptyEntries), StringComparer.Ordinal);

    private static Dictionary<string, HashSet<string>> CreateFrameworkSurface()
    {
        var result = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
        void Add(string type, string names) => result.Add(type, Members(names));
        Add("System.Object", ".ctor Equals ReferenceEquals GetHashCode ToString");
        Add("System.ValueType", "Equals GetHashCode ToString");
        Add("System.Enum", "Equals GetHashCode ToString HasFlag");
        foreach (var scalar in new[] { "Boolean", "Byte", "SByte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Single", "Double", "Char" })
            Add("System." + scalar, "CompareTo Equals GetHashCode ToString Parse TryParse IsNaN IsInfinity IsFinite IsNegativeInfinity IsPositiveInfinity IsAscii IsAsciiDigit IsDigit IsLetter IsLetterOrDigit IsLower IsUpper IsWhiteSpace ToLowerInvariant ToUpperInvariant");
        Add("System.Decimal", ".ctor Compare CompareTo Equals GetHashCode ToString Parse TryParse Abs Ceiling Floor Round Truncate Add Subtract Multiply Divide Remainder Negate ToInt32 ToInt64 ToDouble ToSingle op_Implicit op_Explicit op_Addition op_Subtraction op_Multiply op_Division op_Modulus op_UnaryNegation op_Increment op_Decrement op_Equality op_Inequality op_LessThan op_LessThanOrEqual op_GreaterThan op_GreaterThanOrEqual");
        Add("System.String", ".ctor get_Length get_Chars Concat Equals Compare CompareOrdinal CompareTo GetHashCode ToString IsNullOrEmpty IsNullOrWhiteSpace Contains StartsWith EndsWith IndexOf LastIndexOf Substring Remove Replace Split Trim TrimStart TrimEnd ToLowerInvariant ToUpperInvariant ToCharArray Join op_Equality op_Inequality");
        Add("System.StringComparison", "");
        Add("System.MidpointRounding", "");
        const string math = "Abs Acos Acosh Asin Asinh Atan Atan2 Atanh BitDecrement BitIncrement Cbrt Ceiling Clamp CopySign Cos Cosh Exp Floor FusedMultiplyAdd IEEERemainder Log Log2 Log10 Max Min Pow Round Sign Sin Sinh Sqrt Tan Tanh Truncate DivRem BigMul ScaleB";
        Add("System.Math", math);
        Add("System.MathF", math);
        Add("System.TimeSpan", ".ctor get_Ticks get_Days get_Hours get_Minutes get_Seconds get_Milliseconds get_TotalDays get_TotalHours get_TotalMinutes get_TotalSeconds get_TotalMilliseconds FromTicks FromDays FromHours FromMinutes FromSeconds FromMilliseconds Add Subtract Duration Negate Compare CompareTo Equals GetHashCode ToString op_Addition op_Subtraction op_UnaryNegation op_UnaryPlus op_Equality op_Inequality op_LessThan op_LessThanOrEqual op_GreaterThan op_GreaterThanOrEqual");
        Add("System.Array", "get_Length get_LongLength get_Rank GetLength GetLongLength GetLowerBound GetUpperBound Clear Copy Resize Empty IndexOf LastIndexOf Reverse Sort");
        Add("System.IDisposable", "Dispose");
        Add("System.IComparable", "CompareTo");
        Add("System.IComparable`1", "CompareTo");
        Add("System.IEquatable`1", "Equals");
        Add("System.Collections.IEnumerable", "GetEnumerator");
        Add("System.Collections.IEnumerator", "get_Current MoveNext Reset");
        Add("System.Collections.Generic.IEnumerable`1", "GetEnumerator");
        Add("System.Collections.Generic.IEnumerator`1", "get_Current");
        Add("System.Collections.Generic.ICollection`1", "get_Count get_IsReadOnly Add Clear Contains CopyTo Remove");
        Add("System.Collections.Generic.IList`1", "get_Item set_Item IndexOf Insert RemoveAt");
        Add("System.Collections.Generic.IReadOnlyCollection`1", "get_Count");
        Add("System.Collections.Generic.IReadOnlyList`1", "get_Item");
        Add("System.Collections.Generic.IDictionary`2", "get_Item set_Item get_Keys get_Values Add ContainsKey Remove TryGetValue");
        Add("System.Collections.Generic.IReadOnlyDictionary`2", "get_Item get_Keys get_Values ContainsKey TryGetValue");
        Add("System.Collections.Generic.IEqualityComparer`1", "Equals GetHashCode");
        Add("System.Collections.Generic.EqualityComparer`1", "get_Default Equals GetHashCode");
        Add("System.Collections.Generic.List`1", ".ctor get_Count get_Capacity set_Capacity get_Item set_Item Add AddRange Clear Contains CopyTo GetEnumerator IndexOf Insert InsertRange Remove RemoveAt RemoveRange Reverse Sort ToArray TrimExcess");
        Add("System.Collections.Generic.List`1+Enumerator", "get_Current MoveNext Dispose");
        Add("System.Collections.Generic.Dictionary`2", ".ctor get_Count get_Item set_Item get_Keys get_Values Add Clear ContainsKey ContainsValue GetEnumerator Remove TryAdd TryGetValue EnsureCapacity TrimExcess");
        Add("System.Collections.Generic.Dictionary`2+Enumerator", "get_Current MoveNext Dispose");
        Add("System.Collections.Generic.Dictionary`2+KeyCollection", "get_Count Contains CopyTo GetEnumerator");
        Add("System.Collections.Generic.Dictionary`2+ValueCollection", "get_Count Contains CopyTo GetEnumerator");
        Add("System.Collections.Generic.Dictionary`2+KeyCollection+Enumerator", "get_Current MoveNext Dispose");
        Add("System.Collections.Generic.Dictionary`2+ValueCollection+Enumerator", "get_Current MoveNext Dispose");
        Add("System.Collections.Generic.KeyValuePair`2", ".ctor get_Key get_Value Deconstruct ToString");
        foreach (var exception in new[] { "Exception", "SystemException", "ArgumentException", "ArgumentNullException", "ArgumentOutOfRangeException", "InvalidOperationException", "ArithmeticException", "DivideByZeroException", "OverflowException", "IndexOutOfRangeException", "NullReferenceException", "NotSupportedException" })
            Add("System." + exception, ".ctor get_Message");
        foreach (var attribute in new[] { "CompilationRelaxationsAttribute", "NullableAttribute", "NullableContextAttribute", "RefSafetyRulesAttribute", "CompilerGeneratedAttribute", "IsReadOnlyAttribute", "IsExternalInit", "ParamCollectionAttribute" })
            Add("System.Runtime.CompilerServices." + attribute, ".ctor");
        Add("System.Runtime.CompilerServices.RuntimeCompatibilityAttribute", ".ctor set_WrapNonExceptionThrows");
        // This single known ref-struct is supported for ordinary C# interpolation; Span and author ref-structs are not.
        Add("System.Runtime.CompilerServices.DefaultInterpolatedStringHandler", ".ctor AppendLiteral AppendFormatted ToStringAndClear");
        Add("System.Diagnostics.DebuggableAttribute", ".ctor");
        Add("System.Diagnostics.DebuggableAttribute+DebuggingModes", "");
        Add("System.Runtime.Versioning.TargetFrameworkAttribute", ".ctor set_FrameworkDisplayName");
        foreach (var attribute in new[] { "AssemblyCompanyAttribute", "AssemblyConfigurationAttribute", "AssemblyCopyrightAttribute", "AssemblyDescriptionAttribute", "AssemblyFileVersionAttribute", "AssemblyInformationalVersionAttribute", "AssemblyProductAttribute", "AssemblyTitleAttribute", "AssemblyVersionAttribute", "AssemblyMetadataAttribute" })
            Add("System.Reflection." + attribute, ".ctor");
        return result;
    }

    private sealed record Shape(string Name, string Assembly, bool Private, string? EncodedName = null)
    {
        internal string SignatureName => EncodedName ?? Name;
    }

    private sealed partial class Inspection : ISignatureTypeProvider<Shape, object?>
    {
        private readonly MetadataReader metadata;
        private readonly PEReader pe;
        private readonly HashSet<string> privateIdentities = new(StringComparer.OrdinalIgnoreCase);
        private readonly string ownIdentity;
        private readonly IApiAccessPolicy apiPolicy;
        private readonly bool allowReflectionTypeTokens;
        private readonly bool allowSessionAssemblyNames;
        private readonly bool allowManagedDelegateConstruction;
        private bool decodingDelegateConstructor;
        private int depth;
        private int activeSpecificationBytes;

        internal Inspection(MetadataReader metadata, PEReader pe, IReadOnlyCollection<string> identities, string contract,
            string? hostInterface = null, IReadOnlyCollection<string>? allowedMethods = null, IApiAccessPolicy? apiPolicy = null,
            bool allowReflectionTypeTokens = false, bool allowSessionAssemblyNames = false,
            bool allowManagedDelegateConstruction = false,
            ImmutableDictionary<string, TrustedDelegateProvider>? trustedDelegateProviders = null)
        {
            this.metadata = metadata;
            this.pe = pe;
            var definition = metadata.GetAssemblyDefinition();
            var ownName = new AssemblyName
            {
                Name = metadata.GetString(definition.Name), Version = definition.Version,
                CultureName = metadata.GetString(definition.Culture)
            };
            var publicKey = metadata.GetBlobBytes(definition.PublicKey);
            if (publicKey.Length > 0) ownName.SetPublicKey(publicKey);
            else ownName.SetPublicKeyToken([]);
            ownIdentity = ownName.FullName!;
            this.trustedDelegateProviders = trustedDelegateProviders;
            if (trustedDelegateProviders is not null)
            {
                var sessionNames = identities.Append(ownIdentity).Select(i => new AssemblyName(i).Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
                if (trustedDelegateProviders.Values.Any(p => sessionNames.Contains(new AssemblyName(p.AssemblyIdentity).Name)))
                    throw Invalid("Trusted delegate providers cannot also be author/private assemblies.");
            }
            this.apiPolicy = apiPolicy ?? CreateApiPolicy(identities.Append(ownIdentity).ToArray(), contract, hostInterface, allowedMethods);
            this.allowReflectionTypeTokens = allowReflectionTypeTokens;
            this.allowSessionAssemblyNames = allowSessionAssemblyNames;
            this.allowManagedDelegateConstruction = allowManagedDelegateConstruction;
            foreach (var identity in identities)
            {
                var full = FullIdentity(identity);
                if (!allowSessionAssemblyNames && Reserved(new AssemblyName(full).Name!))
                    throw Invalid($"Private assembly '{full}' spoofs a framework or host assembly name.");
                privateIdentities.Add(full);
            }
        }

        internal void Validate()
        {
            var definition = metadata.GetAssemblyDefinition();
            var ownName = metadata.GetString(definition.Name);
            if (!allowSessionAssemblyNames && Reserved(ownName)) throw Invalid($"Author assembly '{ownName}' spoofs a framework or host assembly name.");
            foreach (var handle in metadata.AssemblyReferences) ValidateAssembly(ReferenceIdentity(handle));
            foreach (var handle in metadata.TypeReferences) _ = GetTypeFromReference(metadata, handle, 0);
            ValidateFinalizerSlots();
            for (var row = 1; row <= metadata.GetTableRowCount(TableIndex.TypeSpec); row++)
                _ = GetTypeFromSpecification(metadata, null, MetadataTokens.TypeSpecificationHandle(row), 0);
            foreach (var handle in metadata.TypeDefinitions)
            {
                var type = metadata.GetTypeDefinition(handle);
                _ = Identifier(type.Name);
                _ = Identifier(type.Namespace);
                if (!type.BaseType.IsNil) _ = Type(type.BaseType);
                foreach (var implementation in type.GetInterfaceImplementations())
                    _ = Type(metadata.GetInterfaceImplementation(implementation).Interface);
                foreach (var attribute in type.GetCustomAttributes())
                {
                    var constructor = metadata.GetCustomAttribute(attribute).Constructor;
                    if (constructor.Kind == HandleKind.MemberReference &&
                        Type(metadata.GetMemberReference((MemberReferenceHandle)constructor).Parent).Name == "System.Runtime.CompilerServices.IsByRefLikeAttribute")
                        throw Invalid("Author byref-like types are unsupported.");
                }
            }
            // Opt-in routes: identify metadata-proven managed delegate constructors before any body scan.
            var delegateConstructorTokens = allowManagedDelegateConstruction
                ? CollectManagedDelegateConstructors()
                : new HashSet<int>();

            foreach (var handle in metadata.FieldDefinitions)
            {
                var field = metadata.GetFieldDefinition(handle);
                CheckBlob(field.Signature);
                _ = field.DecodeSignature(this, null);
            }
            foreach (var handle in metadata.MethodDefinitions)
            {
                var method = metadata.GetMethodDefinition(handle);
                CheckBlob(method.Signature);
                CheckSignature(method.DecodeSignature(this, null));
                if (metadata.GetString(metadata.GetTypeDefinition(method.GetDeclaringType()).Name) == "<Module>")
                    throw Invalid("Module initializers and global module methods are unsupported.");
                if (method.RelativeVirtualAddress == 0) continue;
                var body = pe.GetMethodBody(method.RelativeVirtualAddress);
                if (!body.LocalSignature.IsNil)
                {
                    var locals = metadata.GetStandaloneSignature(body.LocalSignature);
                    CheckBlob(locals.Signature);
                    _ = locals.DecodeLocalSignature(this, null);
                }
                foreach (var region in body.ExceptionRegions)
                    if (region.Kind == ExceptionRegionKind.Catch) _ = Type(region.CatchType);
                CheckInstructions(body.GetILBytes()!, delegateConstructorTokens, body.ExceptionRegions);
            }
            foreach (var handle in metadata.MemberReferences)
            {
                var member = metadata.GetMemberReference(handle);
                CheckBlob(member.Signature);
                var declaring = Type(member.Parent);
                var name = Identifier(member.Name);
                ValidateTrustedMember(member, name);
                ApiMethodSignature? methodShape = null;
                if (member.GetKind() == MemberReferenceKind.Method)
                {
                    decodingDelegateConstructor = delegateConstructorTokens.Contains(MetadataTokens.GetToken(handle));
                    MethodSignature<Shape> signature;
                    try { signature = member.DecodeMethodSignature(this, null); }
                    finally { decodingDelegateConstructor = false; }
                    CheckSignature(signature);
                    methodShape = new(signature.ReturnType.SignatureName,
                        signature.ParameterTypes.Select(type => type.SignatureName).ToImmutableArray(),
                        signature.GenericParameterCount, signature.Header.IsInstance);
                }
                else _ = member.DecodeFieldSignature(this, null);
                Demand(new(declaring.Assembly, member.GetKind() == MemberReferenceKind.Method ? ApiTargetKind.Method : ApiTargetKind.Field,
                    declaring.Name, name, methodShape));
            }
            for (var row = 1; row <= metadata.GetTableRowCount(TableIndex.MethodSpec); row++)
            {
                var method = metadata.GetMethodSpecification(MetadataTokens.MethodSpecificationHandle(row));
                CheckBlob(method.Signature);
                _ = method.DecodeSignature(this, null);
            }
            for (var row = 1; row <= metadata.GetTableRowCount(TableIndex.StandAloneSig); row++)
            {
                var signature = metadata.GetStandaloneSignature(MetadataTokens.StandaloneSignatureHandle(row));
                CheckBlob(signature.Signature);
                if (signature.GetKind() == StandaloneSignatureKind.LocalVariables)
                    _ = signature.DecodeLocalSignature(this, null);
                else CheckSignature(signature.DecodeMethodSignature(this, null));
            }
            for (var row = 1; row <= metadata.GetTableRowCount(TableIndex.GenericParamConstraint); row++)
                _ = Type(metadata.GetGenericParameterConstraint(MetadataTokens.GenericParameterConstraintHandle(row)).Type);
            foreach (var handle in metadata.PropertyDefinitions)
            {
                var property = metadata.GetPropertyDefinition(handle);
                CheckBlob(property.Signature);
                CheckSignature(property.DecodeSignature(this, null), property: true);
            }
            foreach (var handle in metadata.EventDefinitions) _ = Type(metadata.GetEventDefinition(handle).Type);
            if (metadata.GetTableRowCount(TableIndex.ExportedType) != 0 || metadata.GetTableRowCount(TableIndex.File) != 0)
                throw Invalid("Exported types and linked assembly modules are unsupported.");
        }

        private string ReferenceIdentity(AssemblyReferenceHandle handle)
        {
            var reference = metadata.GetAssemblyReference(handle);
            var identity = new AssemblyName
            {
                Name = metadata.GetString(reference.Name), Version = reference.Version, CultureName = metadata.GetString(reference.Culture),
                Flags = (AssemblyNameFlags)(reference.Flags & AssemblyFlags.Retargetable),
                ContentType = (reference.Flags & AssemblyFlags.WindowsRuntime) != 0 ? AssemblyContentType.WindowsRuntime : AssemblyContentType.Default
            };
            var key = metadata.GetBlobBytes(reference.PublicKeyOrToken);
            if ((reference.Flags & AssemblyFlags.PublicKey) != 0) identity.SetPublicKey(key);
            else identity.SetPublicKeyToken(key);
            return identity.FullName!;
        }

        private void ValidateAssembly(string full)
        {
            Demand(new(full, ApiTargetKind.Assembly));
        }

        private void Demand(ApiTarget target)
        {
            if (target.AssemblyIdentity == ownIdentity || privateIdentities.Contains(target.AssemblyIdentity))
                target = target with { IsSessionCode = true };
            var decision = apiPolicy.Evaluate(target, ApiOperation.Reference);
            if (!decision.Allowed) throw Invalid(decision.Reason!);
        }

        private Shape Type(EntityHandle handle) => handle.Kind switch
        {
            HandleKind.TypeReference => GetTypeFromReference(metadata, (TypeReferenceHandle)handle, 0),
            HandleKind.TypeDefinition => GetTypeFromDefinition(metadata, (TypeDefinitionHandle)handle, 0),
            HandleKind.TypeSpecification => GetTypeFromSpecification(metadata, null, (TypeSpecificationHandle)handle, 0),
            _ => throw Invalid("Unsupported type/member declaring scope.")
        };

        private string Identifier(StringHandle handle)
        {
            var name = metadata.GetString(handle);
            if (name.Length > 512) throw Invalid("Metadata type/member names and namespaces cannot exceed 512 characters.");
            return name;
        }

        public Shape GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
        {
            if (++depth > 64) throw Invalid("Type nesting exceeds the profile limit.");
            try
            {
                var type = reader.GetTypeReference(handle);
                var name = Identifier(type.Name);
                string identity;
                if (type.ResolutionScope.Kind == HandleKind.TypeReference)
                {
                    var outer = GetTypeFromReference(reader, (TypeReferenceHandle)type.ResolutionScope, 0);
                    if (outer.Name.Length + name.Length + 1 > 1_024)
                        throw Invalid("Qualified type names cannot exceed 1024 characters.");
                    name = outer.Name + "+" + name;
                    identity = outer.Assembly;
                }
                else if (type.ResolutionScope.Kind == HandleKind.AssemblyReference)
                {
                    identity = ReferenceIdentity((AssemblyReferenceHandle)type.ResolutionScope);
                    var ns = Identifier(type.Namespace);
                    if (ns.Length + name.Length + 1 > 1_024)
                        throw Invalid("Qualified type names cannot exceed 1024 characters.");
                    name = ns.Length == 0 ? name : ns + "." + name;
                }
                else throw Invalid("Type references must have explicit assembly or nested-type scope.");
                ValidateAssembly(identity);
                Demand(new(identity, ApiTargetKind.Type, name));
                return new(name, identity, privateIdentities.Contains(identity));
            }
            finally { depth--; }
        }

        public Shape GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind)
        {
            var name = DefinitionTypeName(handle, 0);
            Demand(new(ownIdentity, ApiTargetKind.Type, name));
            return new(name, ownIdentity, true);
        }

        private string DefinitionTypeName(TypeDefinitionHandle handle, int nesting)
        {
            if (nesting > 64) throw Invalid("Type nesting exceeds the profile limit.");
            var type = metadata.GetTypeDefinition(handle);
            var name = Identifier(type.Name);
            var parent = type.GetDeclaringType();
            if (!parent.IsNil) name = DefinitionTypeName(parent, nesting + 1) + "+" + name;
            else
            {
                var ns = Identifier(type.Namespace);
                if (ns.Length > 0) name = ns + "." + name;
            }
            if (name.Length > 1024) throw Invalid("Qualified type names cannot exceed 1024 characters.");
            return name;
        }

        public Shape GetTypeFromSpecification(MetadataReader reader, object? genericContext, TypeSpecificationHandle handle, byte rawTypeKind)
        {
            if (++depth > 64) throw Invalid("Type nesting exceeds the profile limit.");
            var size = 0;
            try
            {
                var type = reader.GetTypeSpecification(handle);
                CheckBlob(type.Signature);
                size = reader.GetBlobReader(type.Signature).Length;
                activeSpecificationBytes += size;
                if (activeSpecificationBytes > 1_024) throw Invalid("Nested type specifications exceed the profile limit.");
                return type.DecodeSignature(this, genericContext);
            }
            finally { activeSpecificationBytes -= size; depth--; }
        }

        private void CheckBlob(BlobHandle handle)
        {
            if (metadata.GetBlobReader(handle).Length > 512)
                throw Invalid("Signature exceeds the 512-byte profile limit.");
        }

        public Shape GetPrimitiveType(PrimitiveTypeCode code) => code switch
        {
            PrimitiveTypeCode.IntPtr when decodingDelegateConstructor =>
                new("IntPtr", "primitive", false, "System.IntPtr"),
            PrimitiveTypeCode.IntPtr or PrimitiveTypeCode.UIntPtr or PrimitiveTypeCode.TypedReference =>
                throw Invalid($"Unsafe/native signature type '{code}' is unsupported."),
            _ => new(code.ToString(), "primitive", false, "System." + code)
        };
        public Shape GetArrayType(Shape elementType, ArrayShape shape) => shape.Rank is >= 1 and <= 32
            ? elementType with { EncodedName = elementType.SignatureName + "[" + new string(',', shape.Rank - 1) + "]" }
            : throw Invalid("Array rank exceeds the managed array limit.");
        public Shape GetSZArrayType(Shape elementType) => elementType with { EncodedName = elementType.SignatureName + "[]" };
        public Shape GetByReferenceType(Shape elementType) => elementType with { EncodedName = elementType.SignatureName + "&" };
        public Shape GetPointerType(Shape elementType) => throw Invalid("Pointer signatures are unsupported.");
        public Shape GetFunctionPointerType(MethodSignature<Shape> signature) => throw Invalid("Function-pointer signatures are unsupported.");
        public Shape GetGenericInstantiation(Shape genericType, ImmutableArray<Shape> typeArguments) =>
            genericType with { EncodedName = genericType.SignatureName + "<" + string.Join(",", typeArguments.Select(type => type.SignatureName)) + ">" };
        public Shape GetGenericMethodParameter(object? genericContext, int index) => new("!!" + index, ownIdentity, true);
        public Shape GetGenericTypeParameter(object? genericContext, int index) => new("!" + index, ownIdentity, true);
        public Shape GetModifiedType(Shape modifier, Shape unmodifiedType, bool isRequired) => unmodifiedType;
        public Shape GetPinnedType(Shape elementType) => throw Invalid("Pinned locals are unsupported.");

        private static void CheckSignature(MethodSignature<Shape> signature, bool property = false)
        {
            if (signature.Header.CallingConvention != SignatureCallingConvention.Default || signature.Header.HasExplicitThis ||
                signature.RequiredParameterCount != signature.ParameterTypes.Length)
                throw Invalid("Vararg, explicit-this and unmanaged calling conventions are unsupported.");
            if (signature.Header.Kind != (property ? SignatureKind.Property : SignatureKind.Method))
                throw Invalid("Unexpected method/property signature kind.");
        }


        private static readonly HashSet<string> TrustedDelegateNames = new(StringComparer.Ordinal)
        {
            "System.Action", "System.Predicate`1", "System.Comparison`1", "System.Converter`2",
            "System.EventHandler", "System.EventHandler`1",
            "System.Action`1", "System.Action`2", "System.Action`3", "System.Action`4", "System.Action`5",
            "System.Action`6", "System.Action`7", "System.Action`8", "System.Action`9", "System.Action`10",
            "System.Action`11", "System.Action`12", "System.Action`13", "System.Action`14", "System.Action`15",
            "System.Action`16",
            "System.Func`1", "System.Func`2", "System.Func`3", "System.Func`4", "System.Func`5",
            "System.Func`6", "System.Func`7", "System.Func`8", "System.Func`9", "System.Func`10",
            "System.Func`11", "System.Func`12", "System.Func`13", "System.Func`14", "System.Func`15",
            "System.Func`16", "System.Func`17"
        };

        /// <summary>Trusted BCL identity by exact simple name plus the .NET public key token.</summary>
        private static bool IsTrustedBclAssembly(string identity)
        {
            try
            {
                var name = new AssemblyName(identity);
                var token = name.GetPublicKeyToken();
                if (token is null || token.Length != 8) return false;
                var hex = Convert.ToHexString(token).ToLowerInvariant();
                return name.Name switch
                {
                    "System.Private.CoreLib" => hex == "7cec85d7bea7798e",
                    "System.Runtime" => hex == "b03f5f7f11d50a3a",
                    _ => false
                };
            }
            catch (Exception) { return false; }
        }

        private HashSet<int> CollectManagedDelegateConstructors()
        {
            var tokens = new HashSet<int>();
            foreach (var handle in metadata.MemberReferences)
            {
                var member = metadata.GetMemberReference(handle);
                if (member.GetKind() != MemberReferenceKind.Method || Identifier(member.Name) != ".ctor") continue;
                if (!IsTrustedStandardDelegate(member.Parent) && !CollectTrustedDelegateConstructor(handle, member)) continue;
                decodingDelegateConstructor = true;
                MethodSignature<Shape> signature;
                try { signature = member.DecodeMethodSignature(this, null); }
                finally { decodingDelegateConstructor = false; }
                CheckSignature(signature);
                // A known BCL delegate constructor has exactly this ordinary instance signature.
                // Reject malformed lookalikes even if their signature omits the native-int slot.
                if (signature.Header.RawValue != 0x20 || signature.GenericParameterCount != 0 ||
                    signature.ReturnType.SignatureName != "System.Void" || signature.ParameterTypes.Length != 2 ||
                    signature.ParameterTypes[0].SignatureName != "System.Object" ||
                    signature.ParameterTypes[1].SignatureName != "System.IntPtr")
                    throw Invalid("Standard managed delegate constructors require instance void(object, native int).");
                tokens.Add(MetadataTokens.GetToken(handle));
            }
            return tokens;
        }

        /// <summary>Supported scope: trusted standard BCL delegate types only. Author-defined delegates
        /// stay on the strict path (their IntPtr constructor signature is rejected), which is deliberate
        /// for this slice rather than an unproven custom-type acceptance.</summary>
        private bool IsTrustedStandardDelegate(EntityHandle parent)
        {
            if (parent.Kind is not (HandleKind.TypeReference or HandleKind.TypeSpecification)) return false;
            // Type() decodes a specification strictly (the scoped IntPtr flag is off here), so generic
            // arguments never receive the delegate-constructor exception.
            var shape = Type(parent);
            if (shape.Private) return false;
            // A generic instantiation renders as "Ns.Name<args>"; compare the generic definition name.
            var name = shape.Name;
            var generic = name.IndexOf('<');
            if (generic >= 0) name = name[..generic];
            return IsTrustedBclAssembly(shape.Assembly) && TrustedDelegateNames.Contains(name);
        }

        private bool TryInstructionSize(ushort value, byte[] bytes, int operandOffset, out int size)
        {
            size = 0;
            if (!GameplayCapabilityOpcodes.ByValue.TryGetValue(value, out var opcode)) return false;
            size = opcode.Operand switch
            {
                OperandType.InlineNone => 0,
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2,
                OperandType.InlineI8 or OperandType.InlineR => 8,
                OperandType.InlineSwitch => SwitchSize(bytes, operandOffset),
                OperandType.InlineBrTarget or OperandType.InlineField or OperandType.InlineI or OperandType.InlineMethod or
                    OperandType.InlineSig or OperandType.InlineString or OperandType.InlineTok or OperandType.InlineType or OperandType.ShortInlineR => 4,
                _ => -1
            };
            return size >= 0;
        }

        private void CheckInstructions(byte[] bytes, HashSet<int> delegateConstructors, ImmutableArray<ExceptionRegion> regions)
        {
            // Pass 1: collect branch/switch targets so a newobj can never be reached by a jump.
            var branchTargets = new HashSet<int>();
            var instructionStarts = new HashSet<int>();
            {
                var scan = 0;
                while (scan < bytes.Length)
                {
                    var at = scan;
                    instructionStarts.Add(at);
                    ushort value = bytes[scan++];
                    if (value == 0xfe)
                    {
                        if (scan >= bytes.Length) throw Invalid($"Truncated IL opcode at IL offset {at}.");
                        value = (ushort)(0xfe00 | bytes[scan++]);
                    }
                    if (!GameplayCapabilityOpcodes.ByValue.ContainsKey(value))
                        throw Invalid($"Unknown IL opcode 0x{value:X4} at IL offset {at}.");
                    if (!TryInstructionSize(value, bytes, scan, out var step) || step < 0)
                        throw Invalid($"Unsupported IL operand encoding at IL offset {at}.");
                    if (step > bytes.Length - scan)
                        throw Invalid($"Truncated IL operand at IL offset {scan}.");
                    if (value == 0x45) // switch: int32 count followed by count int32 targets
                    {
                        var count = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(scan, 4));

                        for (var i = 0; i < count; i++)
                            branchTargets.Add(scan + step + System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(scan + 4 + i * 4, 4)));
                    }
                    else if (value is >= 0x2B and <= 0x37 || value is >= 0x38 and <= 0x44 || value is 0xDD or 0xDE)
                    {
                        var delta = step == 1 ? (sbyte)bytes[scan] : System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(scan, 4));
                        branchTargets.Add(scan + step + delta);
                    }
                    scan += step;
                }
                foreach (var target in branchTargets)
                {
                    if (target < 0 || target >= bytes.Length || !instructionStarts.Contains(target))
                        throw Invalid($"Branch/switch target {target} is not a valid instruction start.");
                }
            }
            var offset = 0;
            ushort previousValue = 0;
            var previousEnd = -1;
            while (offset < bytes.Length)
            {
                var start = offset;
                ushort value = bytes[offset++];
                if (value == 0xfe)
                {
                    if (offset == bytes.Length) throw Invalid($"Truncated IL opcode at IL offset {start}.");
                    value = (ushort)(0xfe00 | bytes[offset++]);
                }
                if (!GameplayCapabilityOpcodes.ByValue.TryGetValue(value, out var opcode)) throw Invalid($"Unknown IL opcode at IL offset {start}.");
                // Values checked against the checked-in catalog; no reflection at runtime.
                if (value == 0x0029 /* calli */ || value == 0xFE0F /* localloc */ || value == 0x0027 /* jmp */ ||
                    value == 0x00D0 /* ldtoken */ && !allowReflectionTypeTokens || value == 0x00C6 /* mkrefany */ ||
                    value == 0xFE1D /* refanytype */ || value == 0x00C2 /* refanyval */ ||
                    value == 0xFE17 /* cpblk */ || value == 0xFE18 /* initblk */)
                    throw Invalid($"IL opcode '{opcode.Name}' is unsupported at IL offset {start}.");
                var size = opcode.Operand switch
                {
                    OperandType.InlineNone => 0,
                    OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                    OperandType.InlineVar => 2,
                    OperandType.InlineI8 or OperandType.InlineR => 8,
                    OperandType.InlineSwitch => SwitchSize(bytes, offset),
                    OperandType.InlineBrTarget or OperandType.InlineField or OperandType.InlineI or OperandType.InlineMethod or
                        OperandType.InlineSig or OperandType.InlineString or OperandType.InlineTok or OperandType.InlineType or OperandType.ShortInlineR => 4,
                    _ => throw Invalid("Unsupported IL operand encoding.")
                };
                if (size > bytes.Length - offset) throw Invalid($"Truncated IL operand at IL offset {offset}.");
                if (value == 0x00D0 /* ldtoken */)
                {
                    int token = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset, 4));
                    var handle = MetadataTokens.EntityHandle(token);
                    if (handle.Kind is not (HandleKind.TypeDefinition or HandleKind.TypeReference or HandleKind.TypeSpecification))
                        throw Invalid("Only type metadata tokens are supported by the reflection-policy input profile.");
                    _ = Type(handle);
                }
                // Any instruction carrying a method/token operand is checked against the admitted set.
                if (delegateConstructors.Count != 0 && size == 4 &&
                    GameplayCapabilityOpcodes.ByValue.TryGetValue(value, out var guarded) &&
                    guarded.Operand is OperandType.InlineMethod or OperandType.InlineTok)
                {
                    var token = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset, 4));
                    if (delegateConstructors.Contains(token))
                    {
                        if (value != 0x0073)
                            throw Invalid($"Admitted delegate constructor token used by opcode 0x{value:X4} at IL offset {start}; only newobj is allowed.");
                        if (!(previousValue == 0xFE06 || previousValue == 0xFE07) || previousEnd != start)
                            throw Invalid($"Delegate construction at IL offset {start} is not directly preceded by ldftn/ldvirtftn.");
                        if (branchTargets.Contains(start))
                            throw Invalid($"Delegate construction at IL offset {start} is a branch/switch target.");
                        if (trustedConstructors.TryGetValue(token, out var trustedConstructor))
                            ValidateTrustedHandler(MetadataTokens.EntityHandle(System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(
                                bytes.AsSpan(start - 4, 4))), trustedConstructor);
                        foreach (var region in regions)
                        {
                            if (region.TryOffset < 0 || region.TryLength < 0 || region.HandlerOffset < 0 || region.HandlerLength < 0 ||
                                (long)region.TryOffset + region.TryLength > bytes.Length ||
                                (long)region.HandlerOffset + region.HandlerLength > bytes.Length)
                                throw Invalid("Exception region ranges are outside the method body.");
                            if (start == region.TryOffset || start == region.TryOffset + region.TryLength ||
                                start == region.HandlerOffset || start == region.HandlerOffset + region.HandlerLength ||
                                (region.Kind == ExceptionRegionKind.Filter && start == region.FilterOffset))
                                throw Invalid($"Delegate construction at IL offset {start} is an exception-region boundary.");
                        }
                    }
                }
                previousEnd = offset + size;
                previousValue = value;
                offset += size;
            }
        }

        private static int SwitchSize(byte[] bytes, int offset)
        {
            if (bytes.Length - offset < 4) throw Invalid($"Truncated IL switch at IL offset {offset}.");
            var count = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset, 4));
            if (count < 0 || count > (bytes.Length - offset - 4) / 4) throw Invalid($"Invalid IL switch target count at IL offset {offset}.");
            return checked(4 + count * 4);
        }
    }
}
