using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using RuneCLR.Compiler;
using RuneCLR.Packages;
using RuneCLR.Runtime;

/// <summary>
/// Contract tests for the composable include/exclude API rules (docs/api-access-rules.md).
/// Expectations come from the documented selectors, precedence tuple and structural-reference rule;
/// the matcher is not re-implemented here. Compiled-IL and reflection cases reuse one policy shape so
/// static admission and ReflectionAccessProbe must agree.
/// </summary>
internal static class ApiRuleCases
{
    private const string ApiAssembly = "GameApi";
    private const string GameApi = "GameApi, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
    private const string Other = "Other, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
    private const string SystemRuntime = "System.Runtime, Version=1.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a";

    private static readonly ApiMethodSignature IntToInt = new("System.Int32", ["System.Int32"], 0, false);
    private static readonly ApiMethodSignature StringToString = new("System.String", ["System.String"], 0, false);
    private static readonly ApiMethodSignature ReadInfo = new("Game.Api.Info", ["Game.Api.Info"], 0, false);
    private static readonly ApiMethodSignature EchoSlot = new("!!0", ["!!0"], 1, false);

    public static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Default allow and default deny apply when no rule matches", Defaults);
        yield return ("Assembly selectors match a simple name or one complete identity", AssemblySelectors);
        yield return ("Namespace selectors honor exact boundaries and optional subtrees", NamespaceSelectors);
        yield return ("Nested type names are compared to the declaring type, not the namespace", NestedTypes);
        yield return ("Type include with member exclude closes only the named member", TypeIncludeMemberExclude);
        yield return ("Broad exclude with a narrow include reopens exactly one member", NarrowIncludeUnderBroadExclude);
        yield return ("Equal specificity excludes and rule order does not change decisions", EqualRankAndPermutation);
        yield return ("Signature rules select one overload and honor static and generic slots", SignatureSelectors);
        yield return ("Property accessors are matched as their accessor methods", PropertyAccessors);
        yield return ("Session-owned targets are allowed by the flag only, never by assembly name", SessionOwnership);
        yield return ("Malformed rules and invalid target shapes fail closed", MalformedConfiguration);
        yield return ("Rule collections are snapshotted at construction", ImmutableInputs);
        yield return ("Denial reasons name the winner and stay bounded", Diagnostics);
        yield return ("Structural references never become invocation, construction or metadata rights", StructuralReferences);
        yield return ("Structural references come only from a strict descendant include", StructuralReachabilityIsStrictDescendantOnly);
        yield return ("A matching namespace/type conjunction keeps the type and its container reachable", MatchingNamespaceTypeConjunctionStaysAllowed);
        yield return ("An included member cannot use an excluded signature type", ExcludedSignatureTypeStaysDenied);
        yield return ("Malformed and incomplete identities fail closed", MalformedIdentityFormsFailClosed);
        yield return ("Signature snapshots deep-copy parameter strings", SignatureSnapshotDeepCopiesParameters);
        yield return ("Malformed target signatures fail closed under default allow", MalformedTargetSignaturesFailClosed);
        yield return ("A redundant namespace qualifier does not weaken an equal-type exclude", RedundantNamespaceDoesNotWeakenExclude);
        yield return ("Compiled IL admits one included method and rejects siblings, construction and fields", CompiledIlAdmission);
        yield return ("Compiled IL requires reference permission for signature types", SignatureTypePermission);
        yield return ("Reflection probe shares rule decisions and refuses before side effects", ReflectionProbe);
        yield return ("Default allow does not bypass intake, signature or delegate envelopes", HardEnvelope);
        yield return ("Long-lived rule policies do not retain a retired author context", PolicyRetirement);
        yield return ("Exact full-identity matching is stage-specific for IL and runtime targets", FullIdentityMatchingIsStageSpecific);
        yield return ("Constructed generic declaring targets and signatures agree between IL and reflection", GenericDeclaringTargetMatchesAcrossStages);
        yield return ("Selector validation rejects wildcards, empty segments and blank names but keeps declaration names", SelectorValidationRejectsMalformedNames);
        yield return ("Default deny needs explicit BCL and contract references for a custom policy", DefaultDenyRequiresExplicitBclAndContractReferences);
    }

    // The API assembly is compiled once. It is the external surface the author IL/reflection calls into.
    private const string ApiSource = """
        namespace Game.Api
        {
            public sealed class Info
            {
                public int Value;
                public int Number { get; set; }
                public Info() { }
            }
            public sealed class Marker
            {
                public static int Constructions;
                public Marker() { Constructions++; }
            }
            public static class Score
            {
                public static int Field;
                public static int ReadCalls;
                public static int SiblingCalls;
                public static Info Read(Info value) { ReadCalls++; return value; }
                public static Info Sibling(Info value) { SiblingCalls++; return value; }
                public static int Add(int left, int right) => left + right;
                public static string Add(string left, string right) => left + right;
                public static T Echo<T>(T value) => value;
            }

            public sealed class Box<T>
            {
                public static int Field;
                public T Value;
                public T Get() => Value;
                public void Set(T value) { Value = value; }
                public T Echo(T value) => value;
            }
            public sealed class Outer
            {
                public sealed class Inner { public static int Value; }
            }
        }
        namespace Game.ApiOther
        {
            public sealed class Other { public static int Read(int value) => value; }
        }
        """;

    private static readonly TempDirectory ApiFolder = new();
    private static readonly Lazy<byte[]> ApiImage = new(() =>
    {
        var compiled = SourceCompiler.Compile(ApiAssembly, [new("Api.cs", ApiSource)], CompilerFixture.ApprovedReferences());
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        return compiled.Assembly!;
    });
    private static readonly Lazy<string> ApiReference = new(() =>
    {
        var path = Path.Combine(ApiFolder.Path, ApiAssembly + ".dll");
        File.WriteAllBytes(path, ApiImage.Value);
        return path;
    });
    private static readonly Lazy<Assembly> ApiRuntime = new(() =>
        AssemblyLoadContext.Default.LoadFromStream(new MemoryStream(ApiImage.Value, writable: false)));

    private static RuleBasedApiAccessPolicy Policy(ApiPolicyDefault defaultDecision = ApiPolicyDefault.Deny,
        params ApiRule[] rules) => new(defaultDecision, rules);

    private static ApiTarget AssemblyTarget(string identity = GameApi) => new(identity, ApiTargetKind.Assembly);
    private static ApiTarget TypeTarget(string identity, string typeName, bool session = false) =>
        new(identity, ApiTargetKind.Type, typeName) { IsSessionCode = session };
    private static ApiTarget MethodTarget(string identity, string typeName, string member,
        ApiMethodSignature? signature = null, bool session = false) =>
        new(identity, ApiTargetKind.Method, typeName, member, signature) { IsSessionCode = session };
    private static ApiTarget FieldTarget(string identity, string typeName, string member, bool session = false) =>
        new(identity, ApiTargetKind.Field, typeName, member) { IsSessionCode = session };

    private static bool Allowed(IApiAccessPolicy policy, ApiTarget target, ApiOperation operation = ApiOperation.Reference) =>
        policy.Evaluate(target, operation).Allowed;

    private static void Rejects(Action action)
    {
        try { action(); }
        catch (Exception) { return; }
        throw new InvalidOperationException("Expected the configuration to be rejected.");
    }

    private static string Contract => typeof(RuneCLR.IMapScript).Assembly.FullName!;

    private static byte[] CompileAuthor(string assemblyName, string source)
    {
        var references = CompilerFixture.ApprovedReferences().Append(ApiReference.Value).ToArray();
        var compiled = SourceCompiler.Compile(assemblyName, [new("Author.cs", source)], references);
        Check.Assert(compiled.Succeeded, string.Join("; ", compiled.Diagnostics.Select(item => item.Message)));
        return compiled.Assembly!;
    }

    private static void Validate(byte[] image, IApiAccessPolicy policy)
    {
        var identity = ManagedAssemblyInspector.Inspect(image).AssemblyName;
        GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [identity], Contract, policy);
    }

    // Default deny, framework plumbing allowed, the API type excluded, one method reopened, and the
    // signature type optional so the signature-dependency case can omit it.
    private static RuleBasedApiAccessPolicy CompiledPolicy(bool includeSignatureType = true)
    {
        var rules = new List<ApiRule>
        {
            new("sys-runtime", ApiRuleEffect.Include, AssemblyName: "System.Runtime"),
            new("api-score-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new("api-read-include", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read", Signature: ReadInfo)
        };
        if (includeSignatureType)
            rules.Add(new("api-info-include", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Info"));
        return new(ApiPolicyDefault.Deny, rules);
    }

    private const string AllowedSource = """
        namespace Author;
        public static class Entry
        {
            public static Game.Api.Info Run(Game.Api.Info info) => Game.Api.Score.Read(info);
        }
        """;
    private const string SiblingSource = """
        namespace Author;
        public static class Entry
        {
            public static Game.Api.Info Run(Game.Api.Info info) => Game.Api.Score.Sibling(info);
        }
        """;
    private const string ConstructSource = """
        namespace Author;
        public static class Entry
        {
            public static object Run() => new Game.Api.Marker();
        }
        """;
    private const string FieldReadSource = """
        namespace Author;
        public static class Entry
        {
            public static int Run() => Game.Api.Score.Field;
        }
        """;
    private const string FieldWriteSource = """
        namespace Author;
        public static class Entry
        {
            public static void Run() => Game.Api.Score.Field = 1;
        }
        """;
    private const string OverloadSource = """
        namespace Author;
        public static class Entry
        {
            public static int Run(int value) => Game.Api.Score.Add(value, value);
        }
        """;

    private static void Defaults()
    {
        var allow = Policy(ApiPolicyDefault.Allow);
        var deny = Policy(ApiPolicyDefault.Deny);
        Check.Assert(Allowed(allow, TypeTarget(GameApi, "Game.Api.Score")), "Default allow must permit an unlisted target.");
        var denied = deny.Evaluate(TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Reference);
        Check.Assert(!denied.Allowed, "Default deny must refuse an unlisted target.");
        Check.Assert(!string.IsNullOrWhiteSpace(denied.Reason), "A default denial needs a reason.");
    }

    private static void AssemblySelectors()
    {
        var simple = Policy(ApiPolicyDefault.Allow, new ApiRule("asm-simple", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly));
        Check.Assert(!Allowed(simple, TypeTarget(GameApi, "Game.Api.Score")), "A simple name must match the complete identity.");
        Check.Assert(Allowed(simple, TypeTarget(Other, "Other.Api.Type")), "A simple name must not match another assembly.");
        Check.Assert(Allowed(simple, TypeTarget("GameApi2, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", "Game.Api.Score")),
            "A simple name is an exact simple name, not a prefix.");
        var full = Policy(ApiPolicyDefault.Allow, new ApiRule("asm-full", ApiRuleEffect.Exclude, AssemblyName: GameApi));
        Check.Assert(!Allowed(full, TypeTarget(GameApi, "Game.Api.Score")), "A complete identity must match itself.");
        Check.Assert(Allowed(full, TypeTarget("GameApi, Version=2.0.0.0, Culture=neutral, PublicKeyToken=null", "Game.Api.Score")),
            "A complete identity must not match another version.");
        var include = Policy(ApiPolicyDefault.Deny, new ApiRule("asm-include", ApiRuleEffect.Include, AssemblyName: "Other"));
        Check.Assert(Allowed(include, TypeTarget(Other, "Other.Api.Type")), "An assembly include must cover its descendants.");
        Check.Assert(Allowed(include, AssemblyTarget(Other)), "An assembly include must cover the assembly reference.");
        Check.Assert(!Allowed(include, TypeTarget(GameApi, "Game.Api.Score")), "An assembly include must not cover another assembly.");
    }

    private static void NamespaceSelectors()
    {
        var subtree = Policy(ApiPolicyDefault.Deny, new ApiRule("ns", ApiRuleEffect.Include, Namespace: "Game.Api"));
        Check.Assert(Allowed(subtree, TypeTarget(GameApi, "Game.Api.Score")), "A type in the exact namespace must match.");
        Check.Assert(Allowed(subtree, TypeTarget(GameApi, "Game.Api.Child.Score")), "Child namespaces must match by default.");
        Check.Assert(!Allowed(subtree, TypeTarget(GameApi, "Game.ApiOther.Other")), "A sibling namespace must not match.");
        Check.Assert(!Allowed(subtree, TypeTarget(GameApi, "Game.Apiary.Score")), "A mere prefix must not cross the namespace boundary.");
        var exact = Policy(ApiPolicyDefault.Deny,
            new ApiRule("ns-exact", ApiRuleEffect.Include, Namespace: "Game.Api", IncludeChildNamespaces: false));
        Check.Assert(Allowed(exact, TypeTarget(GameApi, "Game.Api.Score")), "The exact namespace must match when descendants are off.");
        Check.Assert(!Allowed(exact, TypeTarget(GameApi, "Game.Api.Child.Score")), "Descendants must not match when disabled.");
    }

    private static void NestedTypes()
    {
        var nested = Policy(ApiPolicyDefault.Deny,
            new ApiRule("nested", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Outer+Inner"));
        Check.Assert(Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer+Inner")), "The ordinal nested name must match.");
        Check.Assert(Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer")),
            "A nested include makes its outer container reference reachable.");
        Check.Assert(!Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer"), ApiOperation.Construct),
            "The outer container keeps its other operations denied.");
        Check.Assert(!Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer.Inner")), "A dotted nested name is not the ordinal form.");
        var byNamespace = Policy(ApiPolicyDefault.Deny,
            new ApiRule("outer-ns", ApiRuleEffect.Include, Namespace: "Game.Api.Outer"));
        Check.Assert(!Allowed(byNamespace, TypeTarget(GameApi, "Game.Api.Outer+Inner")),
            "A nested type belongs to the enclosing namespace, not a namespace named after its declaring type.");
        Check.Assert(Allowed(byNamespace, TypeTarget(GameApi, "Game.Api.Outer.Value")), "A normal child namespace must still match.");
    }

    private static void TypeIncludeMemberExclude()
    {
        var policy = Policy(ApiPolicyDefault.Deny,
            new ApiRule("score", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new ApiRule("delete", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Delete"));
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Read"), ApiOperation.Invoke), "The type include must keep Read.");
        Check.Assert(!Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Delete"), ApiOperation.Invoke), "The member exclude must close Delete.");
        Check.Assert(Allowed(policy, FieldTarget(GameApi, "Game.Api.Score", "Field"), ApiOperation.ReadField), "The type include must keep fields.");
        Check.Assert(Allowed(policy, TypeTarget(GameApi, "Game.Api.Score")), "The type include must allow the type reference.");
    }

    private static void NarrowIncludeUnderBroadExclude()
    {
        var policy = Policy(ApiPolicyDefault.Deny,
            new ApiRule("score-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new ApiRule("read-include", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read"));
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Read"), ApiOperation.Invoke), "The narrow include must reopen Read.");
        Check.Assert(!Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Sibling"), ApiOperation.Invoke), "The narrow include must not reopen siblings.");
        Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Construct), "The narrow include must not grant construction.");
        Check.Assert(Allowed(policy, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Reference), "Read's declaring type stays structurally reachable.");
        Check.Assert(!Allowed(policy, FieldTarget(GameApi, "Game.Api.Score", "Field"), ApiOperation.ReadField), "Fields stay closed.");
    }

    private static void EqualRankAndPermutation()
    {
        var include = new ApiRule("inc", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
            MemberKind: ApiTargetKind.Method, MemberName: "Read");
        var exclude = new ApiRule("dec", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
            MemberKind: ApiTargetKind.Method, MemberName: "Read");
        foreach (var order in new[] { new[] { include, exclude }, new[] { exclude, include } })
        {
            var equal = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, order);
            Check.Assert(!Allowed(equal, MethodTarget(GameApi, "Game.Api.Score", "Read"), ApiOperation.Invoke),
                "At equal specificity, exclude must win regardless of rule order.");
        }
        var rules = new List<ApiRule>
        {
            new("sys", ApiRuleEffect.Include, AssemblyName: "System.Runtime"),
            new("score", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new("read-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read"),
            new("add-int", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Add", Signature: IntToInt),
            new("info", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Info")
        };
        var forward = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, rules);
        var reverse = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, rules.AsEnumerable().Reverse().ToArray());
        var matrix = new (ApiTarget Target, ApiOperation Operation)[]
        {
            (MethodTarget(GameApi, "Game.Api.Score", "Read", ReadInfo), ApiOperation.Invoke),
            (MethodTarget(GameApi, "Game.Api.Score", "Add", IntToInt), ApiOperation.Invoke),
            (MethodTarget(GameApi, "Game.Api.Score", "Add", StringToString), ApiOperation.Invoke),
            (MethodTarget(GameApi, "Game.Api.Score", "Sibling", ReadInfo), ApiOperation.Invoke),
            (FieldTarget(GameApi, "Game.Api.Score", "Field"), ApiOperation.ReadField),
            (TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Construct),
            (TypeTarget(GameApi, "Game.Api.Info"), ApiOperation.Reference),
            (TypeTarget(Other, "Other.Api.Type"), ApiOperation.Reference)
        };
        foreach (var (target, operation) in matrix)
            Check.Assert(forward.Evaluate(target, operation).Allowed == reverse.Evaluate(target, operation).Allowed,
                "Rule enumeration order changed a decision for " + target.Kind + " " + target.TypeName + "/" + target.MemberName + ".");
    }

    private static void SignatureSelectors()
    {
        var addInt = Policy(ApiPolicyDefault.Deny, new ApiRule("add-int", ApiRuleEffect.Include, AssemblyName: ApiAssembly,
            TypeName: "Game.Api.Score", MemberKind: ApiTargetKind.Method, MemberName: "Add", Signature: IntToInt));
        Check.Assert(Allowed(addInt, MethodTarget(GameApi, "Game.Api.Score", "Add", IntToInt), ApiOperation.Invoke), "The exact overload must be allowed.");
        Check.Assert(!Allowed(addInt, MethodTarget(GameApi, "Game.Api.Score", "Add", StringToString), ApiOperation.Invoke), "A sibling overload must stay closed.");
        Check.Assert(!Allowed(addInt, MethodTarget(GameApi, "Game.Api.Score", "Add"), ApiOperation.Invoke), "A signature rule must not match a target without a signature.");
        var echo = Policy(ApiPolicyDefault.Deny, new ApiRule("echo", ApiRuleEffect.Include, AssemblyName: ApiAssembly,
            TypeName: "Game.Api.Score", MemberKind: ApiTargetKind.Method, MemberName: "Echo", Signature: EchoSlot));
        Check.Assert(Allowed(echo, MethodTarget(GameApi, "Game.Api.Score", "Echo", EchoSlot), ApiOperation.Invoke), "The !!0 generic slot must match.");
        Check.Assert(!Allowed(echo, MethodTarget(GameApi, "Game.Api.Score", "Echo", new ApiMethodSignature("!!0", ["!!0"], 0, false)), ApiOperation.Invoke),
            "Generic arity must be part of the match.");
        var instance = new ApiMethodSignature("System.Int32", [], 0, true);
        var instanceRule = Policy(ApiPolicyDefault.Deny, new ApiRule("instance", ApiRuleEffect.Include, AssemblyName: ApiAssembly,
            TypeName: "Game.Api.Score", MemberKind: ApiTargetKind.Method, MemberName: "Get", Signature: instance));
        Check.Assert(Allowed(instanceRule, MethodTarget(GameApi, "Game.Api.Score", "Get", instance), ApiOperation.Invoke), "An instance shape must match an instance target.");
        Check.Assert(!Allowed(instanceRule, MethodTarget(GameApi, "Game.Api.Score", "Get", new ApiMethodSignature("System.Int32", [], 0, false)), ApiOperation.Invoke),
            "Static and instance shapes must not be interchangeable.");
    }

    private static void PropertyAccessors()
    {
        var policy = Policy(ApiPolicyDefault.Deny, new ApiRule("getter", ApiRuleEffect.Include, AssemblyName: ApiAssembly,
            TypeName: "Game.Api.Info", MemberKind: ApiTargetKind.Method, MemberName: "get_Number"));
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Info", "get_Number"), ApiOperation.Invoke), "The getter accessor must match.");
        Check.Assert(!Allowed(policy, MethodTarget(GameApi, "Game.Api.Info", "set_Number"), ApiOperation.Invoke), "The setter must stay closed.");
        Check.Assert(!Allowed(policy, FieldTarget(GameApi, "Game.Api.Info", "Number"), ApiOperation.ReadField), "The property target is not a field target.");
    }

    private static void SessionOwnership()
    {
        var deny = Policy(ApiPolicyDefault.Deny);
        Check.Assert(Allowed(deny, TypeTarget(GameApi, "Game.Api.Score", session: true)), "Session-owned targets need no rule.");
        Check.Assert(!Allowed(deny, TypeTarget(GameApi, "Game.Api.Score", session: false)), "Unmarked targets use the default.");
        Check.Assert(!Allowed(deny, TypeTarget(SystemRuntime, "System.String", session: false)), "A framework-looking name is not ownership.");
        var excluded = Policy(ApiPolicyDefault.Deny, new ApiRule("frame-exclude", ApiRuleEffect.Exclude, AssemblyName: "System.Runtime"));
        Check.Assert(!Allowed(excluded, TypeTarget(SystemRuntime, "System.String", session: true)), "Explicit rules must run before session ownership.");
        Check.Assert(Allowed(excluded, TypeTarget(Other, "Other.Api.Type", session: true)), "A session-owned target outside the rule stays allowed.");
    }

    private static void MalformedConfiguration()
    {
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, null!));
        Rejects(() => _ = new RuleBasedApiAccessPolicy((ApiPolicyDefault)99, []));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("", ApiRuleEffect.Include, AssemblyName: "A")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("dup", ApiRuleEffect.Include, AssemblyName: "A"),
             new ApiRule("dup", ApiRuleEffect.Exclude, AssemblyName: "B")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("empty", ApiRuleEffect.Include)]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("member", ApiRuleEffect.Include, MemberName: "Read")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("kind", ApiRuleEffect.Include, TypeName: "T", MemberKind: ApiTargetKind.Method)]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("sig", ApiRuleEffect.Include, TypeName: "T", Signature: IntToInt)]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("fieldsig", ApiRuleEffect.Include, TypeName: "T", MemberKind: ApiTargetKind.Field, MemberName: "F", Signature: IntToInt)]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("asmkind", ApiRuleEffect.Include, TypeName: "T", MemberKind: ApiTargetKind.Assembly, MemberName: "M")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("typekind", ApiRuleEffect.Include, TypeName: "T", MemberKind: ApiTargetKind.Type, MemberName: "M")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("badeffect", (ApiRuleEffect)99, AssemblyName: "A")]));
        var allow = Policy(ApiPolicyDefault.Allow);
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Method, "Game.Api.Score", null), ApiOperation.Invoke),
            "A method target without a member name must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Field, "Game.Api.Score", "Field", IntToInt), ApiOperation.ReadField),
            "A field target with a method signature must fail closed.");
        Check.Assert(!Allowed(allow, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.ReadField),
            "A type target with a field operation must fail closed.");
        Check.Assert(!Allowed(allow, AssemblyTarget(), ApiOperation.Invoke),
            "An assembly target with an invocation operation must fail closed.");
        Check.Assert(!Allowed(allow, TypeTarget(GameApi, "Game.Api.Score"), (ApiOperation)999),
            "An unknown operation must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, (ApiTargetKind)99, "Game.Api.Score"), ApiOperation.Reference),
            "An unknown target kind must fail closed.");
    }

    private static void ImmutableInputs()
    {
        var rules = new List<ApiRule> { new("api", ApiRuleEffect.Include, AssemblyName: ApiAssembly) };
        var policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, rules);
        Check.Assert(Allowed(policy, TypeTarget(GameApi, "Game.Api.Score")), "The initial snapshot must allow the API assembly.");
        rules.Clear();
        rules.Add(new ApiRule("api-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly));
        Check.Assert(Allowed(policy, TypeTarget(GameApi, "Game.Api.Score")), "Mutating the input list must not change decisions.");
        Check.Assert(!Allowed(policy, TypeTarget(Other, "Other.Api.Type")), "Mutating the input list must not add a rule.");
    }

    private static void Diagnostics()
    {
        var rule = Policy(ApiPolicyDefault.Deny, new ApiRule("deny-score", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"));
        var denied = rule.Evaluate(TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Reference);
        Check.Assert(!denied.Allowed, "The rule must deny.");
        Check.Assert(denied.Reason is not null && denied.Reason.Contains("deny-score", StringComparison.Ordinal),
            "A rule denial must name the winning rule.");
        Check.Assert(denied.Reason!.Length <= 1_024, "The denial reason must stay bounded.");
        var byDefault = Policy(ApiPolicyDefault.Deny).Evaluate(TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Reference);
        Check.Assert(!byDefault.Allowed, "The default must deny.");
        Check.Assert(byDefault.Reason is not null && byDefault.Reason.Contains("default", StringComparison.OrdinalIgnoreCase),
            "A default denial must name the default decision.");
        Check.Assert(byDefault.Reason!.Length <= 1_024, "The default reason must stay bounded.");
    }

    private static void StructuralReferences()
    {
        var policy = Policy(ApiPolicyDefault.Deny,
            new ApiRule("read", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read"));
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Read"), ApiOperation.Invoke), "The included member must match directly.");
        Check.Assert(Allowed(policy, TypeTarget(GameApi, "Game.Api.Score")), "The member's declaring type stays structurally reachable.");
        Check.Assert(Allowed(policy, AssemblyTarget(GameApi)), "The member's assembly stays structurally reachable.");
        Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.ReadMetadata), "ReadMetadata must not be granted.");
        Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Construct), "Construction must not be granted.");
        Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Marker")), "An unrelated type must not become reachable.");
        Check.Assert(!Allowed(policy, AssemblyTarget(GameApi), ApiOperation.Invoke), "A non-reference operation on the container must stay denied.");
        Check.Assert(!Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Sibling"), ApiOperation.Invoke), "Sibling members must stay denied.");
    }

    private static void StructuralReachabilityIsStrictDescendantOnly()
    {
        var assemblyOnly = Policy(ApiPolicyDefault.Deny,
            new ApiRule("asm", ApiRuleEffect.Include, AssemblyName: ApiAssembly),
            new ApiRule("type", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"));
        Check.Assert(Allowed(assemblyOnly, AssemblyTarget(GameApi)), "The directly included assembly is allowed.");
        Check.Assert(!Allowed(assemblyOnly, TypeTarget(GameApi, "Game.Api.Score")),
            "An assembly-only include must not erase a winning type exclude for the type reference.");
        var namespaceAncestor = Policy(ApiPolicyDefault.Deny,
            new ApiRule("ns", ApiRuleEffect.Include, Namespace: "Game.Api"),
            new ApiRule("type", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"));
        Check.Assert(!Allowed(namespaceAncestor, TypeTarget(GameApi, "Game.Api.Score")),
            "A broader namespace include must not erase a winning type exclude.");
        Check.Assert(Allowed(namespaceAncestor, TypeTarget(GameApi, "Game.Api.Other")), "The namespace include still matches other types.");
        var tied = new ApiRule("tie", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score");
        var excluded = new ApiRule("tie-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score");
        foreach (var order in new[] { new[] { tied, excluded }, new[] { excluded, tied } })
        {
            var equalType = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, order);
            Check.Assert(!Allowed(equalType, TypeTarget(GameApi, "Game.Api.Score")),
                "An equal-type include must not erase an equal-type exclude, regardless of order.");
        }
        var descendant = Policy(ApiPolicyDefault.Deny,
            new ApiRule("type-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new ApiRule("member", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read"));
        Check.Assert(Allowed(descendant, TypeTarget(GameApi, "Game.Api.Score")),
            "A member include on the exact type is a strict descendant and must keep the type reference reachable.");
        Check.Assert(Allowed(descendant, AssemblyTarget(GameApi)), "The member include must keep the assembly reference reachable.");
        Check.Assert(!Allowed(descendant, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.ReadMetadata), "ReadMetadata stays denied.");
        Check.Assert(!Allowed(descendant, TypeTarget(GameApi, "Game.Api.Score"), ApiOperation.Construct), "Construct stays denied.");
        Check.Assert(!Allowed(descendant, MethodTarget(GameApi, "Game.Api.Score", "Sibling"), ApiOperation.Invoke), "Sibling members stay denied.");
        var nested = Policy(ApiPolicyDefault.Deny,
            new ApiRule("outer-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Outer"),
            new ApiRule("inner", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Outer+Inner"));
        Check.Assert(Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer+Inner")), "The nested include matches directly.");
        Check.Assert(Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer")),
            "A truly nested include is a strict descendant of the outer container and must keep the outer type reference reachable.");
        Check.Assert(!Allowed(nested, TypeTarget(GameApi, "Game.Api.Outer"), ApiOperation.Construct), "The outer container's other operations stay denied.");
        var impossible = Policy(ApiPolicyDefault.Deny,
            new ApiRule("impossible", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Other", TypeName: "Game.Api.Score"));
        Check.Assert(!Allowed(impossible, TypeTarget(GameApi, "Game.Api.Score")),
            "A namespace/type AND that cannot match must not create a structural reference.");
        Check.Assert(!Allowed(impossible, AssemblyTarget(GameApi)),
            "An impossible namespace/type AND must not make the assembly reachable either.");
    }

    private static void ExcludedSignatureTypeStaysDenied()
    {
        var rules = new List<ApiRule>
        {
            new("sys", ApiRuleEffect.Include, AssemblyName: "System.Runtime"),
            new("score-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score"),
            new("read", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read", Signature: ReadInfo),
            new("info-exclude", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Info")
        };
        var policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, rules);
        Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Info")), "The excluded signature type stays denied.");
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorExcludedSignature", AllowedSource), policy));
        var assembly = ApiRuntime.Value;
        var score = assembly.GetType("Game.Api.Score")!;
        var info = assembly.GetType("Game.Api.Info")!;
        var probe = new ReflectionAccessProbe(policy);
        var value = Activator.CreateInstance(info)!;
        Check.Throws<InvalidOperationException>(() => probe.Invoke(score.GetMethod("Read")!, null, value));
    }

    private static void MalformedIdentityFormsFailClosed()
    {
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("version-only", ApiRuleEffect.Include, AssemblyName: "GameApi, Version=1.0.0.0")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("no-token", ApiRuleEffect.Include, AssemblyName: "GameApi, Version=1.0.0.0, Culture=neutral")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("token-only", ApiRuleEffect.Include, AssemblyName: "GameApi, PublicKeyToken=null")]));
        var allow = Policy(ApiPolicyDefault.Allow);
        Check.Assert(!Allowed(allow, TypeTarget("GameApi, Version=1.0.0.0", "Game.Api.Score")),
            "A partial target identity must fail closed even under default allow.");
        Check.Assert(!Allowed(allow, TypeTarget("GameApi, Version=1.0.0.0, Culture=neutral", "Game.Api.Score")),
            "A target without an explicit token must fail closed.");
        Check.Assert(!Allowed(allow, AssemblyTarget("GameApi")), "A simple target identity must fail closed.");
        Check.Assert(Allowed(allow, TypeTarget(GameApi, "Game.Api.Score")), "A complete target identity must be accepted.");
        var simple = Policy(ApiPolicyDefault.Deny, new ApiRule("simple", ApiRuleEffect.Include, AssemblyName: "GameApi"));
        Check.Assert(Allowed(simple, TypeTarget(GameApi, "Game.Api.Score")), "A simple-name selector must still match a complete target identity.");
    }

    private static void SignatureSnapshotDeepCopiesParameters()
    {
        var backing = new string[] { "System.Int32" };
        var captured = new ApiMethodSignature("System.Int32",
            System.Runtime.InteropServices.ImmutableCollectionsMarshal.AsImmutableArray(backing), 0, false);
        var policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("add", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Add", Signature: captured)]);
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Add", IntToInt), ApiOperation.Invoke),
            "The captured signature must match before mutation.");
        backing[0] = "System.String";
        Check.Assert(Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Add", IntToInt), ApiOperation.Invoke),
            "Mutating the backing array must not change the captured signature.");
        Check.Assert(!Allowed(policy, MethodTarget(GameApi, "Game.Api.Score", "Add", StringToString), ApiOperation.Invoke),
            "The snapshot must not adopt the mutated parameter type.");
    }

    private static void MalformedTargetSignaturesFailClosed()
    {
        var allow = Policy(ApiPolicyDefault.Allow);
        Check.Assert(!Allowed(allow, MethodTarget(GameApi, "Game.Api.Score", "Read",
            new ApiMethodSignature("Game.Api.Info", default, 0, false)), ApiOperation.Invoke),
            "A default ParameterTypes array must fail closed.");
        Check.Assert(!Allowed(allow, MethodTarget(GameApi, "Game.Api.Score", "Read",
            new ApiMethodSignature("Game.Api.Info", [], -1, false)), ApiOperation.Invoke),
            "A negative generic arity must fail closed.");
        Check.Assert(!Allowed(allow, MethodTarget(GameApi, "Game.Api.Score", "Read",
            new ApiMethodSignature("", ["Game.Api.Info"], 0, false)), ApiOperation.Invoke),
            "An empty return type must fail closed.");
        Check.Assert(!Allowed(allow, MethodTarget(GameApi, "Game.Api.Score", "Read",
            new ApiMethodSignature("Game.Api.Info", [""], 0, false)), ApiOperation.Invoke),
            "An empty parameter type must fail closed.");
        Check.Assert(!Allowed(allow, MethodTarget(GameApi, "Game.Api.Score", "Read",
            new ApiMethodSignature("Game.Api.Info", [null!], 0, false)), ApiOperation.Invoke),
            "A null parameter type must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Field, "Game.Api.Score", "Field", IntToInt), ApiOperation.ReadField),
            "A field with a signature must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Type, "Game.Api.Score", "Read"), ApiOperation.Reference),
            "A type target with a member name must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Method, null, "Read"), ApiOperation.Invoke),
            "A member target without a type name must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Method, "Game.Api.Score", "Read", IntToInt), ApiOperation.ReadField),
            "A method target with a field operation must fail closed.");
        Check.Assert(!Allowed(allow, new ApiTarget(GameApi, ApiTargetKind.Field, "Game.Api.Score", "Field"), ApiOperation.Invoke),
            "A field target with an invocation operation must fail closed.");
    }

    private static void RedundantNamespaceDoesNotWeakenExclude()
    {
        var include = new ApiRule("inc", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Game.Api", TypeName: "Game.Api.Score");
        var exclude = new ApiRule("dec", ApiRuleEffect.Exclude, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score");
        foreach (var order in new[] { new[] { include, exclude }, new[] { exclude, include } })
        {
            var policy = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny, order);
            Check.Assert(!Allowed(policy, TypeTarget(GameApi, "Game.Api.Score")),
                "A redundant namespace qualifier must not make an equal-type include win.");
        }
        var mismatched = Policy(ApiPolicyDefault.Deny,
            new ApiRule("inc", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Other", TypeName: "Game.Api.Score"));
        Check.Assert(!Allowed(mismatched, TypeTarget(GameApi, "Game.Api.Score")),
            "A non-matching namespace constraint must keep the rule from matching.");
    }

    private static void CompiledIlAdmission()
    {
        var policy = CompiledPolicy();
        Validate(CompileAuthor("AuthorAllowed", AllowedSource), policy);
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorSibling", SiblingSource), policy));
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorConstruct", ConstructSource), policy));
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorFieldRead", FieldReadSource), policy));
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorFieldWrite", FieldWriteSource), policy));
        Check.Throws<InvalidDataException>(() => Validate(CompileAuthor("AuthorOverload", OverloadSource), policy));
    }

    private static void SignatureTypePermission()
    {
        var image = CompileAuthor("AuthorSignatureType", AllowedSource);
        Validate(image, CompiledPolicy(includeSignatureType: true));
        Check.Throws<InvalidDataException>(() => Validate(image, CompiledPolicy(includeSignatureType: false)));
    }

    private static void ReflectionProbe()
    {
        var assembly = ApiRuntime.Value;
        var score = assembly.GetType("Game.Api.Score")!;
        var info = assembly.GetType("Game.Api.Info")!;
        var marker = assembly.GetType("Game.Api.Marker")!;
        var probe = new ReflectionAccessProbe(CompiledPolicy());
        var value = Activator.CreateInstance(info)!;
        var read = score.GetMethod("Read")!;
        Check.Assert(ReferenceEquals(probe.Invoke(read, null, value), value), "The included method must run.");
        Check.Assert((int)score.GetField("ReadCalls")!.GetValue(null)! == 1, "The included method must have run once.");
        Check.Throws<InvalidOperationException>(() => probe.Invoke(score.GetMethod("Sibling")!, null, value));
        Check.Assert((int)score.GetField("SiblingCalls")!.GetValue(null)! == 0, "A denied sibling must not run.");
        Check.Throws<InvalidOperationException>(() => probe.Construct(marker.GetConstructor(Type.EmptyTypes)!));
        Check.Assert((int)marker.GetField("Constructions")!.GetValue(null)! == 0, "A denied constructor must not run.");
        var field = score.GetField("Field")!;
        Check.Throws<InvalidOperationException>(() => probe.Read(field, null));
        Check.Throws<InvalidOperationException>(() => probe.Write(field, null, 7));
        Check.Assert((int)field.GetValue(null)! == 0, "A denied write must not change the field.");
        Check.Assert(probe.Inspect(read).MemberName == "Read", "The included member's ReadMetadata must succeed.");
        Check.Throws<InvalidOperationException>(() => probe.Inspect(score));
    }

    private static void HardEnvelope()
    {
        var allow = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Allow, []);
        var pinvoke = CompileAuthor("AuthorPInvoke", """
            using System.Runtime.CompilerServices;
            namespace Author;
            public static class Entry
            {
                [MethodImpl(MethodImplOptions.InternalCall)] public static extern int Native();
                public static int Run() => Native();
            }
            """);
        Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.Inspect(pinvoke));
        var coreLib = Path.Combine(Path.GetDirectoryName(typeof(object).Assembly.Location)!, "System.Private.CoreLib.dll");
        var dllImport = SourceCompiler.Compile("AuthorDllImport", [new("Author.cs", """
            using System.Runtime.InteropServices;
            namespace Author;
            public static class Entry
            {
                [DllImport("kernel32.dll")] public static extern int GetTickCount();
                public static int Run() => GetTickCount();
            }
            """)], [coreLib, ApiReference.Value]);
        Check.Assert(dllImport.Succeeded, string.Join("; ", dllImport.Diagnostics.Select(item => item.Message)));
        Check.Throws<InvalidDataException>(() => ManagedAssemblyInspector.Inspect(dllImport.Assembly!));
        var native = CompileAuthor("AuthorNativeSignature", """
            namespace Author;
            public static class Entry
            {
                public static System.IntPtr Run(System.IntPtr value) => value;
            }
            """);
        Check.Throws<InvalidDataException>(() => Validate(native, allow));
        var delegated = CompileAuthor("AuthorDelegate", """
            namespace Author;
            public static class Entry
            {
                public static void Add(int value) { }
                public static int Run() { System.Action<int> action = Add; return 0; }
            }
            """);
        Check.Throws<InvalidDataException>(() => Validate(delegated, allow));
    }

    private static void PolicyRetirement()
    {
        var (context, policy) = Retire();
        for (var attempt = 0; attempt < 10 && context.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }
        Check.Assert(!context.IsAlive, "A long-lived rule policy retained the retired author context.");
        GC.KeepAlive(policy);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static (WeakReference Context, IApiAccessPolicy Policy) Retire()
    {
        var context = new AssemblyLoadContext("api-rule-retirement", isCollectible: true);
        using var stream = new MemoryStream(ApiImage.Value, writable: false);
        var assembly = context.LoadFromStream(stream);
        var policy = CompiledPolicy();
        var probe = new ReflectionAccessProbe(policy);
        var score = assembly.GetType("Game.Api.Score")!;
        var info = assembly.GetType("Game.Api.Info")!;
        var value = Activator.CreateInstance(info)!;
        _ = probe.Invoke(score.GetMethod("Read")!, null, value);
        var weak = new WeakReference(context);
        context.Unload();
        return (weak, policy);
    }

    private static void FullIdentityMatchingIsStageSpecific()
    {
        // An exact full identity is compared against the identity string of the stage that supplies
        // the target: the IL AssemblyRef identity for admission, the runtime assembly identity for the
        // probe. The two can differ (version/forwarder), so full-identity rules are stage-specific.
        var runtimeIdentity = ApiRuntime.Value.GetName().FullName!;
        var ilReference = ManagedAssemblyInspector.Inspect(CompileAuthor("AuthorStageIdentity", AllowedSource))
            .References.Single(reference => reference.StartsWith("GameApi,", StringComparison.Ordinal));
        var runtimeRule = Policy(ApiPolicyDefault.Allow,
            new ApiRule("exact-runtime", ApiRuleEffect.Exclude, AssemblyName: runtimeIdentity));
        var ilRule = Policy(ApiPolicyDefault.Allow,
            new ApiRule("exact-il", ApiRuleEffect.Exclude, AssemblyName: ilReference));
        Check.Assert(!Allowed(runtimeRule, TypeTarget(runtimeIdentity, "Game.Api.Score")), "The exact runtime identity must match the runtime target.");
        Check.Assert(!Allowed(ilRule, TypeTarget(ilReference, "Game.Api.Score")), "The exact IL identity must match the IL target.");
        if (!string.Equals(runtimeIdentity, ilReference, StringComparison.Ordinal))
        {
            Check.Assert(Allowed(runtimeRule, TypeTarget(ilReference, "Game.Api.Score")),
                "A full-identity rule must not match the other stage's identity.");
            Check.Assert(Allowed(ilRule, TypeTarget(runtimeIdentity, "Game.Api.Score")),
                "A full-identity rule must not match the other stage's identity.");
        }
        var shifted = "GameApi, Version=9.9.9.9, Culture=neutral, PublicKeyToken=null";
        Check.Assert(Allowed(runtimeRule, TypeTarget(shifted, "Game.Api.Score")),
            "A full-identity rule must not match a different version string.");
        var simple = Policy(ApiPolicyDefault.Allow, new ApiRule("simple", ApiRuleEffect.Exclude, AssemblyName: "GameApi"));
        Check.Assert(!Allowed(simple, TypeTarget(runtimeIdentity, "Game.Api.Score"))
            && !Allowed(simple, TypeTarget(ilReference, "Game.Api.Score")),
            "A simple-name rule must match both stage identities.");
        var byNamespace = Policy(ApiPolicyDefault.Allow, new ApiRule("ns", ApiRuleEffect.Exclude, Namespace: "Game.Api"));
        Check.Assert(!Allowed(byNamespace, TypeTarget(runtimeIdentity, "Game.Api.Score"))
            && !Allowed(byNamespace, TypeTarget(ilReference, "Game.Api.Score")),
            "A namespace rule must match both stage identities.");
    }

    private static void GenericDeclaringTargetMatchesAcrossStages()
    {
        var assembly = ApiRuntime.Value;
        var box = assembly.GetTypes().Single(type => type.Name.StartsWith("Box", StringComparison.Ordinal) && type.IsGenericTypeDefinition);
        var constructed = box.MakeGenericType(typeof(int));
        var probe = new ReflectionAccessProbe(Policy(ApiPolicyDefault.Allow));
        var reflectedMethod = probe.Inspect(constructed.GetMethod("Get")!);
        Check.Assert(reflectedMethod.TypeName == box.FullName, "The reflection target must use the generic definition type name.");
        Check.Assert(reflectedMethod.Signature is not null
            && reflectedMethod.Signature.ReturnType == "!0"
            && reflectedMethod.Signature.ParameterTypes.Length == 0
            && reflectedMethod.Signature.GenericArity == 0
            && reflectedMethod.Signature.IsInstance,
            "The reflection signature must keep the definition generic slot and instance shape.");
        var reflectedField = probe.Inspect(constructed.GetField("Value")!);
        Check.Assert(reflectedField.TypeName == box.FullName && reflectedField.Signature is null,
            "A field target must use the generic definition type name and carry no signature.");
        var recorder = new RecordingPolicy(Policy(ApiPolicyDefault.Allow));
        var image = CompileAuthor("AuthorGenericDeclaring", """
            namespace Author;
            public static class Entry
            {
                public static int Run(Game.Api.Box<int> box) => box.Get();
                public static int Read(Game.Api.Box<int> box) => box.Value;
            }
            """);
        GameplayCapabilityPolicy.ValidateWithApiPolicy(image, [ManagedAssemblyInspector.Inspect(image).AssemblyName], Contract, recorder);
        var ilMethod = recorder.Targets.Single(target => target.TypeName == box.FullName && target.MemberName == "Get");
        Check.Assert(ilMethod.Signature is not null
            && ilMethod.Signature.ReturnType == reflectedMethod.Signature!.ReturnType
            && ilMethod.Signature.ParameterTypes.SequenceEqual(reflectedMethod.Signature.ParameterTypes)
            && ilMethod.Signature.GenericArity == reflectedMethod.Signature.GenericArity
            && ilMethod.Signature.IsInstance == reflectedMethod.Signature.IsInstance,
            "IL and reflection must agree on the constructed generic declaring target and signature.");
        var ilField = recorder.Targets.Single(target => target.TypeName == box.FullName && target.MemberName == "Value");
        Check.Assert(ilField.Signature is null, "The IL field target must carry no signature, matching the probe.");
    }

    private static void SelectorValidationRejectsMalformedNames()
    {
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("wildcard-asm", ApiRuleEffect.Include, AssemblyName: "Game*")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("wildcard-type", ApiRuleEffect.Include, TypeName: "Game.Api.*")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("wildcard-member", ApiRuleEffect.Include, TypeName: "Game.Api.Score", MemberName: "Read*")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("empty-segment", ApiRuleEffect.Include, TypeName: "Game..Score")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("leading-dot", ApiRuleEffect.Include, TypeName: ".Game.Api.Score")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("trailing-dot", ApiRuleEffect.Include, TypeName: "Game.Api.Score.")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("blank-namespace", ApiRuleEffect.Include, Namespace: "   ")]));
        Rejects(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("blank-type", ApiRuleEffect.Include, TypeName: "  ")]));
        var valid = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
        [
            new ApiRule("ctor", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: ".ctor"),
            new ApiRule("accessor", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Info",
                MemberKind: ApiTargetKind.Method, MemberName: "get_Number"),
            new ApiRule("explicit", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Game.IApi.Ping"),
            new ApiRule("nested", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Outer+Inner")
        ]);
        Check.Assert(Allowed(valid, MethodTarget(GameApi, "Game.Api.Score", ".ctor"), ApiOperation.Construct), "Constructor names must stay valid.");
        Check.Assert(Allowed(valid, MethodTarget(GameApi, "Game.Api.Info", "get_Number"), ApiOperation.Invoke), "Accessor names must stay valid.");
        Check.Assert(Allowed(valid, MethodTarget(GameApi, "Game.Api.Score", "Game.IApi.Ping"), ApiOperation.Invoke), "Explicit interface member names must stay valid.");
        Check.Assert(Allowed(valid, TypeTarget(GameApi, "Game.Api.Outer+Inner")), "Nested type names must stay valid.");
        Check.Throws<ArgumentException>(() => _ = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
            [new ApiRule("padded", ApiRuleEffect.Include, AssemblyName: " GameApi ")]));
    }

    private static void DefaultDenyRequiresExplicitBclAndContractReferences()
    {
        var withBcl = CompiledPolicy();
        var withoutBcl = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
        [
            new ApiRule("api-read", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Score",
                MemberKind: ApiTargetKind.Method, MemberName: "Read", Signature: ReadInfo),
            new ApiRule("api-info", ApiRuleEffect.Include, AssemblyName: ApiAssembly, TypeName: "Game.Api.Info")
        ]);
        var apiImage = CompileAuthor("AuthorBclReferences", AllowedSource);
        Validate(apiImage, withBcl);
        Check.Throws<InvalidDataException>(() => Validate(apiImage, withoutBcl));
        var contractImage = CompileAuthor("AuthorContractReference", """
            namespace Author;
            public sealed class Entry : RuneCLR.IMapScript
            {
                public void OnStart(RuneCLR.IMapContext context) { }
                public void OnTick(RuneCLR.MapTick tick) { }
                public void OnStop() { }
            }
            """);
        Check.Throws<InvalidDataException>(() => Validate(contractImage, withBcl));
        var contractAllowed = new RuleBasedApiAccessPolicy(ApiPolicyDefault.Deny,
        [
            new ApiRule("sys", ApiRuleEffect.Include, AssemblyName: "System.Runtime"),
            new ApiRule("contract", ApiRuleEffect.Include, AssemblyName: "RuneCLR.Abstractions")
        ]);
        Validate(contractImage, contractAllowed);
    }

    private sealed class RecordingPolicy(IApiAccessPolicy inner) : IApiAccessPolicy
    {
        public List<ApiTarget> Targets { get; } = [];
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation)
        {
            Targets.Add(target);
            return inner.Evaluate(target, operation);
        }
    }

    private static void MatchingNamespaceTypeConjunctionStaysAllowed()
    {
        var exact = Policy(ApiPolicyDefault.Deny,
            new ApiRule("conjunction", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Game.Api", TypeName: "Game.Api.Score"));
        Check.Assert(Allowed(exact, TypeTarget(GameApi, "Game.Api.Score")), "A matching namespace/type conjunction must match the type.");
        Check.Assert(Allowed(exact, AssemblyTarget(GameApi)), "A matching conjunction must make the assembly container reachable.");
        Check.Assert(!Allowed(exact, TypeTarget(GameApi, "Game.Api.Other")), "The conjunction must not match another type.");
        var exactNamespace = Policy(ApiPolicyDefault.Deny,
            new ApiRule("exact-ns", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Game.Api",
                IncludeChildNamespaces: false, TypeName: "Game.Api.Score"));
        Check.Assert(Allowed(exactNamespace, TypeTarget(GameApi, "Game.Api.Score")), "The exact namespace conjunction must match.");
        var childMismatch = Policy(ApiPolicyDefault.Deny,
            new ApiRule("exact-ns-child", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Game.Api",
                IncludeChildNamespaces: false, TypeName: "Game.Api.Child.Score"));
        Check.Assert(!Allowed(childMismatch, TypeTarget(GameApi, "Game.Api.Child.Score")),
            "With descendants disabled, a child namespace must not satisfy the namespace constraint.");
        Check.Assert(!Allowed(childMismatch, AssemblyTarget(GameApi)),
            "A non-matching conjunction must not make the assembly reachable.");
        var subtree = Policy(ApiPolicyDefault.Deny,
            new ApiRule("subtree", ApiRuleEffect.Include, AssemblyName: ApiAssembly, Namespace: "Game.Api",
                TypeName: "Game.Api.Child.Score"));
        Check.Assert(Allowed(subtree, TypeTarget(GameApi, "Game.Api.Child.Score")), "A descendant namespace must satisfy the constraint by default.");
        Check.Assert(Allowed(subtree, AssemblyTarget(GameApi)), "A matching subtree conjunction must make the assembly reachable.");
    }
}
