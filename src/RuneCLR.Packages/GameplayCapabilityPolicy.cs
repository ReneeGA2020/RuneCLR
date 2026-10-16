using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

namespace RuneCLR.Packages;

/// <summary>Rejects metadata outside the initial synchronous gameplay API profile without loading author code.
/// This is a static compatibility gate, not semantic IL verification, execution metering or a security sandbox.</summary>
public static class GameplayCapabilityPolicy
{
    public const string Profile = "managed-il-gameplay-v1";

    public static void Validate(ReadOnlyMemory<byte> image, IReadOnlyCollection<string> privateAssemblyIdentities,
        string contractAssemblyIdentity)
    {
        ArgumentNullException.ThrowIfNull(privateAssemblyIdentities);
        if (image.IsEmpty || image.Length > ManagedAssemblyInspector.MaximumImageBytes)
            throw Invalid("Provide a nonempty assembly within the managed-IL image limit.");
        try
        {
            using var pe = new PEReader(ImmutableArray.CreateRange(image.ToArray()));
            var reader = pe.GetMetadataReader(MetadataReaderOptions.None);
            new Inspection(reader, pe, privateAssemblyIdentities, contractAssemblyIdentity).Validate();
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
        // Signal, RaiseSignal, the tick schedule, host-completed work, and resource registration are intentionally absent.
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

    private sealed record Shape(string Name, string Assembly, bool Private);

    private sealed class Inspection : ISignatureTypeProvider<Shape, object?>
    {
        private readonly MetadataReader metadata;
        private readonly PEReader pe;
        private readonly HashSet<string> privateIdentities = new(StringComparer.Ordinal);
        private readonly string contractIdentity;
        private int depth;
        private int activeSpecificationBytes;

        internal Inspection(MetadataReader metadata, PEReader pe, IReadOnlyCollection<string> identities, string contract)
        {
            this.metadata = metadata;
            this.pe = pe;
            contractIdentity = FullIdentity(contract);
            if (new AssemblyName(contractIdentity).Name != "RuneCLR.Abstractions")
                throw Invalid("The approved contract must be RuneCLR.Abstractions.");
            foreach (var identity in identities)
            {
                var full = FullIdentity(identity);
                if (Reserved(new AssemblyName(full).Name!))
                    throw Invalid($"Private assembly '{full}' spoofs a framework or host assembly name.");
                privateIdentities.Add(full);
            }
        }

        internal void Validate()
        {
            var definition = metadata.GetAssemblyDefinition();
            var ownName = metadata.GetString(definition.Name);
            if (Reserved(ownName)) throw Invalid($"Author assembly '{ownName}' spoofs a framework or host assembly name.");
            foreach (var handle in metadata.AssemblyReferences) ValidateAssembly(ReferenceIdentity(handle));
            foreach (var handle in metadata.TypeReferences) _ = GetTypeFromReference(metadata, handle, 0);
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
                if (metadata.GetString(method.Name) == "Finalize") throw Invalid("Author finalizers are unsupported.");
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
                CheckInstructions(body.GetILBytes()!);
            }
            foreach (var handle in metadata.MemberReferences)
            {
                var member = metadata.GetMemberReference(handle);
                CheckBlob(member.Signature);
                var declaring = Type(member.Parent);
                var name = Identifier(member.Name);
                if (!declaring.Private)
                {
                    var surface = declaring.Assembly == contractIdentity ? Contract : Framework;
                    if (!surface.TryGetValue(declaring.Name, out var members) || !members.Contains(name))
                        throw Invalid($"Member '{declaring.Name}.{name}' is not approved.");
                    // No framework/contract fields are exposed, including attributes' backing storage.
                    if (member.GetKind() != MemberReferenceKind.Method)
                        throw Invalid($"Field '{declaring.Name}.{name}' is not approved.");
                }
                if (member.GetKind() == MemberReferenceKind.Method) CheckSignature(member.DecodeMethodSignature(this, null));
                else _ = member.DecodeFieldSignature(this, null);
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

        private static bool Reserved(string name) => new[] { "mscorlib", "netstandard", "System", "Microsoft", "RuneCLR" }.Contains(name, StringComparer.OrdinalIgnoreCase) ||
            name.StartsWith("System.", StringComparison.OrdinalIgnoreCase) ||
            name.StartsWith("Microsoft.", StringComparison.OrdinalIgnoreCase) ||
            name.StartsWith("RuneCLR.", StringComparison.OrdinalIgnoreCase);

        private static string FullIdentity(string identity)
        {
            var name = new AssemblyName(identity);
            if (name.Version is null || string.IsNullOrEmpty(name.Name) || !identity.Contains("PublicKeyToken=", StringComparison.OrdinalIgnoreCase) ||
                !identity.Contains("Culture=", StringComparison.OrdinalIgnoreCase))
                throw Invalid("Assembly identities must include version, culture and public-key token.");
            return name.FullName!;
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
            if (full == contractIdentity || privateIdentities.Contains(full)) return;
            var name = new AssemblyName(full);
            var token = Convert.ToHexString(name.GetPublicKeyToken() ?? []).ToLowerInvariant();
            var allowed = name.Name is "System.Runtime" or "System.Collections" or "System.Linq" or "System.ObjectModel" or "System.Runtime.Extensions";
            if (((allowed && token == "b03f5f7f11d50a3a") ||
                 (name.Name == "System.Private.CoreLib" && token == "7cec85d7bea7798e")) &&
                string.IsNullOrEmpty(name.CultureName) && name.ContentType == AssemblyContentType.Default &&
                (name.Flags & AssemblyNameFlags.Retargetable) == 0) return;
            throw Invalid($"Assembly '{full}' is not approved.");
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
                if (privateIdentities.Contains(identity)) return new(name, identity, true);
                var surface = identity == contractIdentity ? Contract : Framework;
                if (!surface.ContainsKey(name)) throw Invalid($"Type '{name}' is not approved.");
                return new(name, identity, false);
            }
            finally { depth--; }
        }

        public Shape GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind)
        {
            var type = reader.GetTypeDefinition(handle);
            return new(Identifier(type.Name), "self", true);
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
            PrimitiveTypeCode.IntPtr or PrimitiveTypeCode.UIntPtr or PrimitiveTypeCode.TypedReference =>
                throw Invalid($"Unsafe/native signature type '{code}' is unsupported."),
            _ => new(code.ToString(), "primitive", false)
        };
        public Shape GetArrayType(Shape elementType, ArrayShape shape) => elementType;
        public Shape GetSZArrayType(Shape elementType) => elementType;
        public Shape GetByReferenceType(Shape elementType) => elementType;
        public Shape GetPointerType(Shape elementType) => throw Invalid("Pointer signatures are unsupported.");
        public Shape GetFunctionPointerType(MethodSignature<Shape> signature) => throw Invalid("Function-pointer signatures are unsupported.");
        public Shape GetGenericInstantiation(Shape genericType, ImmutableArray<Shape> typeArguments) => genericType;
        public Shape GetGenericMethodParameter(object? genericContext, int index) => new("!!" + index, "self", true);
        public Shape GetGenericTypeParameter(object? genericContext, int index) => new("!" + index, "self", true);
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

        private static readonly Dictionary<ushort, OpCode> Opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(field => field.FieldType == typeof(OpCode)).Select(field => (OpCode)field.GetValue(null)!)
            .ToDictionary(opcode => unchecked((ushort)opcode.Value));

        private static void CheckInstructions(byte[] bytes)
        {
            var offset = 0;
            while (offset < bytes.Length)
            {
                ushort value = bytes[offset++];
                if (value == 0xfe)
                {
                    if (offset == bytes.Length) throw Invalid("Truncated IL opcode.");
                    value = (ushort)(0xfe00 | bytes[offset++]);
                }
                if (!Opcodes.TryGetValue(value, out var opcode)) throw Invalid("Unknown IL opcode.");
                if (opcode == OpCodes.Calli || opcode == OpCodes.Localloc || opcode == OpCodes.Jmp ||
                    opcode == OpCodes.Ldtoken || opcode == OpCodes.Mkrefany || opcode == OpCodes.Refanytype || opcode == OpCodes.Refanyval ||
                    opcode == OpCodes.Cpblk || opcode == OpCodes.Initblk)
                    throw Invalid($"IL opcode '{opcode.Name}' is unsupported.");
                var size = opcode.OperandType switch
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
                if (size > bytes.Length - offset) throw Invalid("Truncated IL operand.");
                offset += size;
            }
        }

        private static int SwitchSize(byte[] bytes, int offset)
        {
            if (bytes.Length - offset < 4) throw Invalid("Truncated IL switch.");
            var count = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset, 4));
            if (count < 0 || count > (bytes.Length - offset - 4) / 4) throw Invalid("Invalid IL switch target count.");
            return checked(4 + count * 4);
        }
    }
}
