using System.Security.Cryptography;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.Loader;
using ReflectionPolicy.CompiledLibrary;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static partial class ReflectionPolicyTests
{
    private static void ExerciseHostPolicy()
    {
        SessionHooks.HostProbe = null;
        SessionHooks.HostDeniedReflectionDenied = false;
        SessionHooks.HostEffectDenied = false;
        SessionHooks.Flow = null;
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeApiPolicy = new HostPolicy(),
            PrototypeSharedAssemblies = [typeof(RuneCLR.IMapScript).Assembly]
        };
        string directory = Path.Combine(Path.GetTempPath(), "runeclr-host-policy-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            string entryPath = Path.Combine(directory, "host-policy.dll");
            string entryType = WriteHostPolicyEntry(entryPath, "PolicyScript", directDenied: false, fail: false);
            var host = new PolicyHost();
            var session = new HostContractSession(typeof(IHostProbe), host, entryPath, entryType, ["Echo"], options);
            var context = session.ContextReference;
            Assert(host.EchoCalls == 3, "Host ctor/OnStart reflection did not follow the expected calls: " + host.EchoCalls);
            Assert(SessionHooks.HostDeniedReflectionDenied && SessionHooks.HostEffectDenied && host.DeniedCalls == 0,
                "Denied host/shared reflection target executed.");
            Pass("host contract options share the real contract and run ctor/OnStart reflection under required interpretation");

            session.Invoke("OnLater");
            Assert(host.EchoCalls == 5, "Later host callback reflection did not run: " + host.EchoCalls);
            session.Invoke("OnTick", 7);
            Assert(host.EchoCalls == 6, "Host int callback reflection did not run: " + host.EchoCalls);
            Assert(session.InvokeInt("OnReturn", 8) == 9, "Host int-return callback reflection failed.");
            Assert(host.EchoCalls == 7, "Host int-return callback did not reach the host: " + host.EchoCalls);
            Pass("host contract later/int callbacks keep approved direct and reflected host calls working");

            int outside = host.Echo(20);
            Assert(outside == 20 && host.EchoCalls == 8, "Host callback policy leaked outside the session.");
            var flow = SessionHooks.Flow!;
            Expect<InvalidOperationException>(() => ExecutionContext.Run(flow, _ => SessionHooks.ReflectEffect(), null));
            Pass("host calls outside callbacks remain unrestricted and returned contexts refuse reflection");

            SessionHooks.Flow = null;
            session.Dispose();
            for (int i = 0; i < 15 && context.IsAlive; i++)
            {
                GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            }
            Assert(!context.IsAlive, "Host contract policy context was retained after Dispose.");
            Pass("host contract Dispose clears the policy and unloads the collectible context");

            string deniedPath = Path.Combine(directory, "host-denied.dll");
            string deniedType = WriteHostPolicyEntry(deniedPath, "DeniedScript", directDenied: true, fail: false);
            var deniedHost = new PolicyHost();
            var deniedError = Capture(() =>
                new HostContractSession(typeof(IHostProbe), deniedHost, deniedPath, deniedType, ["Echo"], options));
            Assert(deniedHost.DeniedCalls == 0 && deniedHost.EchoCalls == 0, "An unlisted direct host call ran.");
            Assert(deniedError.Message.Contains("host contract", StringComparison.OrdinalIgnoreCase) ||
                deniedError.Message.Contains("allowedMethods", StringComparison.OrdinalIgnoreCase) ||
                deniedError.Message.Contains("Denied", StringComparison.OrdinalIgnoreCase), deniedError.Message);
            Pass("host contract allowedMethods still rejects a direct unlisted host call before OnStart");

            string failPath = Path.Combine(directory, "host-fail.dll");
            string failType = WriteHostPolicyEntry(failPath, "FailScript", directDenied: false, fail: true);
            var failHost = new PolicyHost();
            SessionHooks.HostMessageRead = false;
            int contextsBefore = HostContractContextCount();
            var failure = Expect<InvalidOperationException>(() =>
                new HostContractSession(typeof(IHostProbe), failHost, failPath, failType, ["Echo"], options));
            Assert(!SessionHooks.HostMessageRead, "Host failure reporting ran the author virtual Message property.");
            Assert(failure.Message.Contains("HostMessageException", StringComparison.Ordinal) &&
                !failure.Message.Contains("author-failed", StringComparison.Ordinal) && failHost.EchoCalls == 0,
                "Host callback failure was not bounded type-only text: " + failure.Message);
            Pass("host contract callback failure is bounded text without a virtual Message side effect");
            for (int i = 0; i < 15 && HostContractContextCount() > contextsBefore; i++)
            {
                GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            }
            Assert(HostContractContextCount() <= contextsBefore, "Host contract policy OnStart failure kept its context alive.");
            Pass("host contract policy OnStart failure unloads its collectible context");

            string dependencyDirectory = Path.Combine(directory, "dependency-package");
            Directory.CreateDirectory(dependencyDirectory);
            string dependencyPath = Path.Combine(dependencyDirectory, "host-dep.dll");
            WriteHostDependency(dependencyPath);
            string dependencyEntryPath = Path.Combine(dependencyDirectory, "host-dependency.dll");
            string dependencyEntryType = WriteHostPolicyEntry(dependencyEntryPath, "DependencyScript",
                directDenied: false, fail: false, dependencyPath: dependencyPath);
            string dependencyManifest = WriteHostManifest(dependencyDirectory, "host-dependency.dll",
                dependencyEntryType, ["Echo"], "host-dep.dll");
            var dependencyHost = new PolicyHost();
            using (var dependencySession = HostContractSession.Open(dependencyManifest,
                typeof(IHostProbe), dependencyHost, options))
            {
                Assert(dependencyHost.EchoCalls == 4,
                    "Host contract private dependency was not executed: " + dependencyHost.EchoCalls);
            }
            Pass("host contract private dependency executes through the policy load hooks");

            string openDirectory = Path.Combine(directory, "open-package");
            Directory.CreateDirectory(openDirectory);
            string openEntryPath = Path.Combine(openDirectory, "host-policy.dll");
            string openEntryType = WriteHostPolicyEntry(openEntryPath, "PolicyScript", directDenied: false, fail: false);
            string manifest = WriteHostManifest(openDirectory, "host-policy.dll", openEntryType, ["Echo"]);
            var openHost = new PolicyHost();
            using (var opened = HostContractSession.Open(manifest, typeof(IHostProbe), openHost, options))
            {
                Assert(openHost.EchoCalls == 3, "Host contract Open options did not run OnStart: " + openHost.EchoCalls);
            }
            Pass("host contract Open accepts options after the existing manifest checks");

            string rejectedManifest = WriteHostManifest(openDirectory, "host-policy.dll", openEntryType, ["Other"]);
            var rejectedHost = new PolicyHost();
            var rejectedError = Capture(() =>
                HostContractSession.Open(rejectedManifest, typeof(IHostProbe), rejectedHost, options));
            Assert(rejectedHost.EchoCalls == 0 && rejectedHost.DeniedCalls == 0, "Rejected manifest ran a host call.");
            Assert(rejectedError.Message.Contains("host contract", StringComparison.OrdinalIgnoreCase) ||
                rejectedError.Message.Contains("allowedMethods", StringComparison.OrdinalIgnoreCase) ||
                rejectedError.Message.Contains("Echo", StringComparison.OrdinalIgnoreCase), rejectedError.Message);
            Pass("host contract Open keeps the legacy allow-list check with options");
        }
        finally
        {
            SessionHooks.HostProbe = null;
            SessionHooks.HostDeniedReflectionDenied = false;
            SessionHooks.HostEffectDenied = false;
            Directory.Delete(directory, recursive: true);
        }
    }

    private static void ExerciseHostAllowedMethods()
    {
        string directory = Path.Combine(Path.GetTempPath(), "runeclr-host-allowall-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeApiPolicy = new AllowAllPolicy(),
            PrototypeSharedAssemblies = [typeof(RuneCLR.IMapScript).Assembly]
        };
        try
        {
            ResetHostProbeFlags();
            string reflectPath = Path.Combine(directory, "host-reflect.dll");
            string reflectType = WriteHostPolicyEntry(reflectPath, "ReflectScript", false, false, probeMode: "reflect");
            var reflectHost = new PolicyHost();
            using (var session = new HostContractSession(typeof(IHostProbe), reflectHost, reflectPath,
                reflectType, ["Echo"], options))
            {
                Assert(reflectHost.HiddenCalls == 0 && reflectHost.EchoCalls == 2 &&
                    SessionHooks.HostHiddenReflectionDenied,
                    "Allow-all reflected unlisted host call was not refused: " + reflectHost.HiddenCalls + "/" + reflectHost.EchoCalls);
                Assert(reflectHost.Hidden(70) == 70, "Host outside-callback call was restricted.");
            }
            Pass("allow-all policy still enforces allowedMethods for reflected contract targets");

            ResetHostProbeFlags();
            string wrapperPath = Path.Combine(directory, "host-wrapper.dll");
            string wrapperType = WriteHostPolicyEntry(wrapperPath, "WrapperScript", false, false, probeMode: "wrapper");
            var wrapperHost = new PolicyHost();
            var wrapperError = Capture(() =>
            {
                using var session = new HostContractSession(typeof(IHostProbe), wrapperHost, wrapperPath,
                    wrapperType, ["Echo"], options);
                Assert(wrapperHost.HiddenCalls == 0 && wrapperHost.EchoCalls == 1 &&
                    SessionHooks.HostPrivateWrapperDenied,
                    "Allow-all private author wrapper reached an unlisted host call.");
            });
            if (wrapperError is not null)
                Assert(wrapperHost.HiddenCalls == 0 && wrapperHost.EchoCalls == 0,
                    "Rejected wrapper entry still ran a host call.");
            Pass("allow-all policy enforces allowedMethods for a reflectively invoked private author wrapper");

            ResetHostProbeFlags();
            string dynamicPath = Path.Combine(directory, "host-dynamic.dll");
            SessionHooks.DynamicAuthorBytes = BuildDynamicAuthor(directory);
            string dynamicType = WriteHostPolicyEntry(dynamicPath, "DynamicScript", false, false, probeMode: "dynamic");
            var dynamicHost = new PolicyHost();
            using (var session = new HostContractSession(typeof(IHostProbe), dynamicHost, dynamicPath,
                dynamicType, ["Echo"], options))
            {
                Assert(dynamicHost.HiddenCalls == 0 && dynamicHost.EchoCalls == 1 &&
                    SessionHooks.HostDynamicAuthorDenied,
                    "Allow-all dynamically loaded author helper reached an unlisted host call.");
            }
            Pass("allow-all policy enforces allowedMethods for a dynamically loaded author helper");

            ResetHostProbeFlags();
            string aliasPath = Path.Combine(directory, "host-alias.dll");
            string aliasType = WriteHostPolicyEntry(aliasPath, "AliasScript", false, false, probeMode: "alias");
            var aliasHost = new PolicyHost();
            using (var session = new HostContractSession(typeof(IHostProbe), aliasHost, aliasPath,
                aliasType, ["Echo"], options))
            {
                Assert(aliasHost.HiddenCalls == 0 && aliasHost.EchoCalls == 1 &&
                    SessionHooks.HostBaseAliasDenied && SessionHooks.HostImplementationAliasDenied,
                    "Allow-all base/implementation alias reached an unlisted host call.");
            }
            Pass("allow-all policy enforces allowedMethods for base-interface and host-implementation aliases");

            string dependencyDirectory = Path.Combine(directory, "session-dependency");
            Directory.CreateDirectory(dependencyDirectory);
            string dependencyPath = Path.Combine(dependencyDirectory, "host-dep.dll");
            WriteHostDependency(dependencyPath);
            string dependencyEntryPath = Path.Combine(dependencyDirectory, "host-sessiondep.dll");
            string dependencyEntryType = WriteHostPolicyEntry(dependencyEntryPath, "SessionDependencyScript",
                false, false, dependencyPath: dependencyPath, probeMode: "sessiondep");
            string dependencyManifest = WriteHostManifest(dependencyDirectory, "host-sessiondep.dll",
                dependencyEntryType, ["Echo"], "host-dep.dll");
            var dependencyHost = new PolicyHost();
            var dependencyError = Capture(() => HostContractSession.Open(dependencyManifest,
                typeof(IHostProbe), dependencyHost, new HostContractSessionOptions
                {
                    ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
                    PrototypeApiPolicy = new SessionCodePolicy()
                }));
            Assert(dependencyHost.EchoCalls == 0, "Session-code dependency denial ran a host effect.");
            Assert(dependencyError.Message.Contains("SessionOnly", StringComparison.OrdinalIgnoreCase) ||
                dependencyError.Message.Contains("den", StringComparison.OrdinalIgnoreCase), dependencyError.Message);
            Pass("declared dependency identity is session code during entry admission");

            string shadowDirectory = Path.Combine(directory, "framework-shadow");
            Directory.CreateDirectory(shadowDirectory);
            string shadowDependencyPath = Path.Combine(shadowDirectory, "framework-dep.dll");
            WriteHostDependency(shadowDependencyPath, "System.Runtime", "System.Runtime.Call");
            string shadowEntryPath = Path.Combine(shadowDirectory, "host-shadow.dll");
            string shadowEntryType = WriteHostPolicyEntry(shadowEntryPath, "ShadowScript", false, false, probeMode: "simple");
            string shadowManifest = WriteHostManifest(shadowDirectory, "host-shadow.dll",
                shadowEntryType, ["Echo"], "framework-dep.dll");
            var shadowHost = new PolicyHost();
            var shadowError = Capture(() => HostContractSession.Open(shadowManifest,
                typeof(IHostProbe), shadowHost, options));
            Assert(shadowHost.EchoCalls == 0, "Framework-shadow dependency ran a host effect.");
            Assert(shadowError.Message.Contains("framework", StringComparison.OrdinalIgnoreCase) ||
                shadowError.Message.Contains("reserved", StringComparison.OrdinalIgnoreCase) ||
                shadowError.Message.Contains("System.Runtime", StringComparison.OrdinalIgnoreCase), shadowError.Message);
            Pass("framework identity shadow sources are rejected while System.Custom dependencies keep working");

            string simplePath = Path.Combine(directory, "host-simple.dll");
            string simpleType = WriteHostPolicyEntry(simplePath, "SimpleScript", false, false, probeMode: "simple");
            var simpleHost = new PolicyHost();
            var simpleError = Capture(() =>
            {
                using var session = new HostContractSession(typeof(IHostProbe), simpleHost, simplePath,
                    simpleType, ["Echo"], new HostContractSessionOptions
                    {
                        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter
                    });
            });
            Assert(simpleHost.EchoCalls == 0, "Rejected RequireInterpreter options ran an author callback.");
            Assert(simpleError.Message.Contains("RequireInterpreter", StringComparison.OrdinalIgnoreCase) ||
                simpleError.Message.Contains("policy", StringComparison.OrdinalIgnoreCase), simpleError.Message);
            Pass("RequireInterpreter without a policy is rejected before author code");
        }
        finally
        {
            SessionHooks.DynamicAuthorBytes = null;
            ResetHostProbeFlags();
            Directory.Delete(directory, recursive: true);
        }
    }

    private static void ResetHostProbeFlags()
    {
        SessionHooks.HostDeniedReflectionDenied = false;
        SessionHooks.HostEffectDenied = false;
        SessionHooks.HostHiddenReflectionDenied = false;
        SessionHooks.HostPrivateWrapperDenied = false;
        SessionHooks.HostDynamicAuthorDenied = false;
        SessionHooks.HostBaseAliasDenied = false;
        SessionHooks.HostImplementationAliasDenied = false;
        SessionHooks.HostMessageRead = false;
        SessionHooks.GenericHiddenReflectionDenied = false;
        SessionHooks.GenericBaseReflectionDenied = false;
        SessionHooks.GenericBaseAliasDenied = false;
        SessionHooks.GenericBaseObjectControlSucceeded = false;
        SessionHooks.GenericBaseObjectContractDenied = false;
        SessionHooks.GenericBaseAliasMethod = null;
        SessionHooks.GenericBaseObjectMethod = null;
    }

    private static byte[] BuildDynamicAuthor(string directory)
    {
        string path = Path.Combine(directory, "dynamic-author.bin");
        var identity = new AssemblyName("System.Custom.DynamicAuthor") { Version = new Version(1, 0, 0, 0) };
        var builder = new PersistedAssemblyBuilder(identity, typeof(object).Assembly);
        var module = builder.DefineDynamicModule(identity.Name!);
        var type = module.DefineType("System.Custom.DynamicAuthor.Call",
            TypeAttributes.Public | TypeAttributes.Class | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var hidden = type.DefineMethod("Hidden", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), [typeof(IHostProbe)]);
        var il = hidden.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Ldc_I4, 66);
        il.Emit(OpCodes.Callvirt, typeof(IHostProbeBase).GetMethod(nameof(IHostProbeBase.Hidden))!);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
        byte[] bytes = File.ReadAllBytes(path);
        File.Delete(path);
        return bytes;
    }

    private static int HostContractContextCount() =>
        AssemblyLoadContext.All.Count(context => context != AssemblyLoadContext.Default);

    private static Exception Capture(Action action)
    {
        try { action(); }
        catch (Exception error) { return error; }
        throw new InvalidOperationException("Expected a host contract policy failure.");
    }

    private static void ExerciseGenericHostContract()
    {
        string directory = Path.Combine(Path.GetTempPath(), "runeclr-host-generic-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var options = new HostContractSessionOptions
        {
            ExecutionPolicy = MapExecutionPolicy.RequireInterpreter,
            PrototypeApiPolicy = new AllowAllPolicy(),
            PrototypeSharedAssemblies = [typeof(RuneCLR.IMapScript).Assembly]
        };
        try
        {
            ResetHostProbeFlags();
            string allowedPath = Path.Combine(directory, "generic-allowed.dll");
            string allowedType = WriteGenericHostEntry(allowedPath, "Allowed", "allowed");
            var allowedHost = new GenericPolicyHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), allowedHost, allowedPath,
                allowedType, ["Echo"], options))
            {
                Assert(allowedHost.EchoCalls == 1 && allowedHost.HiddenCalls == 0,
                    "Allowed constructed generic host target failed.");
            }
            Pass("constructed generic contract allows the listed host method");

            string deniedPath = Path.Combine(directory, "generic-denied.dll");
            string deniedType = WriteGenericHostEntry(deniedPath, "Denied", "denied");
            var deniedHost = new GenericPolicyHost();
            var deniedError = Capture(() =>
                new HostContractSession(typeof(IGenericProbe<int>), deniedHost, deniedPath,
                    deniedType, ["Echo"], options));
            Assert(deniedHost.EchoCalls == 0 && deniedHost.HiddenCalls == 0,
                "Unlisted constructed generic direct call ran a host effect.");
            Assert(deniedError.Message.Contains("Hidden", StringComparison.OrdinalIgnoreCase) ||
                deniedError.Message.Contains("allowedMethods", StringComparison.OrdinalIgnoreCase), deniedError.Message);
            Pass("constructed generic contract rejects an unlisted direct host call");

            ResetHostProbeFlags();
            string reflectPath = Path.Combine(directory, "generic-reflect.dll");
            string reflectType = WriteGenericHostEntry(reflectPath, "Reflect", "reflect");
            var reflectHost = new GenericPolicyHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), reflectHost, reflectPath,
                reflectType, ["Echo"], options))
            {
                Assert(reflectHost.EchoCalls == 2 && reflectHost.HiddenCalls == 0 &&
                    SessionHooks.GenericHiddenReflectionDenied,
                    "Constructed generic reflection bypassed allowedMethods.");
            }
            Pass("constructed generic contract rejects unlisted reflected host targets");

            ResetHostProbeFlags();
            string basePath = Path.Combine(directory, "generic-base.dll");
            string baseType = WriteGenericHostEntry(basePath, "Base", "base");
            var baseHost = new GenericPolicyHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), baseHost, basePath,
                baseType, ["Echo"], options))
            {
                Assert(baseHost.EchoCalls == 1 && baseHost.HiddenCalls == 0 &&
                    SessionHooks.GenericBaseReflectionDenied,
                    "Inherited generic interface bypassed allowedMethods.");
            }
            Pass("inherited generic interface rejects unlisted base targets");

            ResetHostProbeFlags();
            string explicitPath = Path.Combine(directory, "generic-explicit.dll");
            string explicitType = WriteGenericHostEntry(explicitPath, "Explicit", "reflect");
            var explicitHost = new ExplicitGenericPolicyHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), explicitHost, explicitPath,
                explicitType, ["Echo"], options))
            {
                Assert(explicitHost.EchoCalls == 2 && explicitHost.HiddenCalls == 0 &&
                    SessionHooks.GenericHiddenReflectionDenied,
                    "Explicit generic implementation name bypassed allowedMethods.");
            }
            Pass("explicit distinct CLR-name generic implementation stays denied");

            ResetHostProbeFlags();
            string overridePath = Path.Combine(directory, "generic-override.dll");
            string overrideType = WriteGenericHostEntry(overridePath, "Override", "base");
            var overrideHost = new DerivedGenericHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), overrideHost, overridePath,
                overrideType, ["Echo"], options))
            {
                Assert(overrideHost.EchoCalls == 1 && overrideHost.HiddenCalls == 0 &&
                    SessionHooks.GenericBaseReflectionDenied,
                    "Overridden generic base implementation bypassed allowedMethods.");
            }
            Pass("supplied instance override of a generic base implementation stays denied");

            ResetHostProbeFlags();
            SessionHooks.GenericBaseAliasMethod = typeof(NonVirtualBaseHostBase)
                .GetMethod(nameof(NonVirtualBaseHostBase.Hidden), BindingFlags.Public | BindingFlags.Instance,
                    null, [typeof(int)], null);
            Assert(SessionHooks.GenericBaseAliasMethod is not null, "Exact base alias method was not found.");
            string aliasBasePath = Path.Combine(directory, "generic-basealias.dll");
            string aliasBaseType = WriteGenericHostEntry(aliasBasePath, "BaseAlias", "basealias");
            var aliasBaseHost = new NonVirtualBaseHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), aliasBaseHost, aliasBasePath,
                aliasBaseType, ["Echo"], options))
            {
                Assert(aliasBaseHost.EchoCalls == 1 && aliasBaseHost.BaseHiddenCalls == 0 &&
                    aliasBaseHost.DerivedHiddenCalls == 0 && SessionHooks.GenericBaseAliasDenied,
                    "Exact-parameter nonvirtual base alias was not denied.");
            }
            Pass("direct reflected nonvirtual base alias with exact parameters stays denied");

            ResetHostProbeFlags();
            SessionHooks.GenericBaseObjectMethod = typeof(ObjectBaseHostBase)
                .GetMethod(nameof(ObjectBaseHostBase.Hidden), BindingFlags.Public | BindingFlags.Instance,
                    null, [typeof(object)], null);
            Assert(SessionHooks.GenericBaseObjectMethod is not null, "Base object overload was not found.");
            string objectBasePath = Path.Combine(directory, "generic-objectbase.dll");
            string objectBaseType = WriteGenericHostEntry(objectBasePath, "ObjectBase", "objectcontrol");
            var objectBaseHost = new ObjectBaseHost();
            using (var session = new HostContractSession(typeof(IGenericProbe<int>), objectBaseHost, objectBasePath,
                objectBaseType, ["Echo"], options))
            {
                Assert(objectBaseHost.EchoCalls == 1 && objectBaseHost.ObjectHiddenCalls == 1 &&
                    objectBaseHost.IntHiddenCalls == 0 && SessionHooks.GenericBaseObjectControlSucceeded &&
                    SessionHooks.GenericBaseObjectContractDenied,
                    "Base Hidden(object) control or contract Hidden(int) denial failed.");
            }
            Pass("base Hidden(object) remains callable while contract Hidden(int) stays denied");
        }
        finally
        {
            ResetHostProbeFlags();
            Directory.Delete(directory, recursive: true);
        }
    }

    private static string WriteGenericHostEntry(string path, string name, string mode)
    {
        var identity = new AssemblyName("HostContract.Generic" + name + "Assembly") { Version = new Version(1, 0, 0, 0) };
        var builder = new PersistedAssemblyBuilder(identity, typeof(object).Assembly);
        var module = builder.DefineDynamicModule(identity.Name!);
        string entryName = "HostContract.Generic" + name + ".Entry";
        var type = module.DefineType(entryName, TypeAttributes.Public | TypeAttributes.Class | TypeAttributes.Sealed);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);

        var contract = typeof(IGenericProbe<int>);
        var echo = contract.GetMethod(nameof(IGenericProbe<int>.Echo))!;
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [contract]);
        var il = start.GetILGenerator();
        if (mode is "allowed" or "reflect" or "base" or "basealias" or "objectcontrol")
        {
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Ldc_I4_1);
            il.Emit(OpCodes.Callvirt, echo);
            il.Emit(OpCodes.Pop);
        }
        if (mode == "denied")
        {
            var hidden = typeof(IGenericProbeBase<int>).GetMethod(nameof(IGenericProbeBase<int>.Hidden))!;
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Ldc_I4_2);
            il.Emit(OpCodes.Callvirt, hidden);
            il.Emit(OpCodes.Pop);
        }
        else if (mode == "reflect")
        {
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostGenericReflectProbe))!);
        }
        else if (mode == "base")
        {
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostGenericBaseReflectProbe))!);
        }
        else if (mode == "basealias")
        {
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostGenericBaseAliasProbe))!);
        }
        else if (mode == "objectcontrol")
        {
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostGenericBaseObjectControlProbe))!);
        }
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
        return entryName;
    }

    private static string WriteHostPolicyEntry(string path, string name, bool directDenied, bool fail, string? dependencyPath = null, string? probeMode = null)
    {
        var assemblyName = new AssemblyName("HostContract." + name + "Assembly") { Version = new Version(1, 0, 0, 0) };
        var builder = new PersistedAssemblyBuilder(assemblyName, typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName.Name!);
        string entryName = "HostContract." + name + ".Entry";
        var type = module.DefineType(entryName, TypeAttributes.Public | TypeAttributes.Class | TypeAttributes.Sealed);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostCtorProbe))!);
        constructorIl.Emit(OpCodes.Ret);

        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostProbe)]);
        var startIl = start.GetILGenerator();
        if (fail)
        {
            startIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostThrow))!);
        }
        else
        {
            startIl.Emit(OpCodes.Ldarg_1);
            startIl.Emit(OpCodes.Ldc_I4, directDenied ? 9 : 1);
            startIl.Emit(OpCodes.Callvirt, typeof(IHostProbe).GetMethod(directDenied ? nameof(IHostProbe.Denied) : nameof(IHostProbe.Echo))!);
            startIl.Emit(OpCodes.Pop);
            if (dependencyPath is not null)
            {
                var dependency = Assembly.Load(File.ReadAllBytes(dependencyPath));
                var call = dependency.GetType("System.Custom.UgcDependency.Call", throwOnError: true)!
                    .GetMethod(probeMode == "sessiondep" ? "SessionOnly" : "Echo", BindingFlags.Public | BindingFlags.Static)!;
                if (call.GetParameters().Length == 0)
                {
                    startIl.Emit(OpCodes.Call, call);
                }
                else
                {
                    startIl.Emit(OpCodes.Ldarg_1);
                    startIl.Emit(OpCodes.Call, call);
                }
                startIl.Emit(OpCodes.Pop);
            }
            if (probeMode is "reflect" or "wrapper" or "dynamic" or "alias")
            {
                if (probeMode == "wrapper")
                {
                    startIl.Emit(OpCodes.Ldarg_1);
                    startIl.Emit(OpCodes.Ldtoken, type);
                    startIl.Emit(OpCodes.Call, typeof(Type).GetMethod(nameof(Type.GetTypeFromHandle))!);
                    startIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostPrivateWrapperProbe))!);
                }
                else
                {
                    startIl.Emit(OpCodes.Ldarg_1);
                    var helper = probeMode switch
                    {
                        "reflect" => nameof(SessionHooks.HostReflectHiddenProbe),
                        "dynamic" => nameof(SessionHooks.HostDynamicAuthorProbe),
                        _ => nameof(SessionHooks.HostAliasProbe)
                    };
                    startIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(helper)!);
                }
            }
            else if (probeMode is null)
            {
                startIl.Emit(OpCodes.Ldarg_1);
                startIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostStartProbe))!);
            }
        }
        startIl.Emit(OpCodes.Ret);

        var later = type.DefineMethod("OnLater", MethodAttributes.Public, typeof(void), [typeof(IHostProbe)]);
        var laterIl = later.GetILGenerator();
        laterIl.Emit(OpCodes.Ldarg_1);
        laterIl.Emit(OpCodes.Ldc_I4, 5);
        laterIl.Emit(OpCodes.Callvirt, typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!);
        laterIl.Emit(OpCodes.Pop);
        laterIl.Emit(OpCodes.Ldarg_1);
        laterIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostLaterProbe))!);
        laterIl.Emit(OpCodes.Ret);

        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), [typeof(int)]);
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostTickProbe))!);
        tickIl.Emit(OpCodes.Ret);

        if (probeMode == "wrapper")
        {
            var wrapper = type.DefineMethod("Wrapper", MethodAttributes.Private | MethodAttributes.Static,
                typeof(void), [typeof(IHostProbe)]);
            var wrapperIl = wrapper.GetILGenerator();
            wrapperIl.Emit(OpCodes.Ldarg_0);
            wrapperIl.Emit(OpCodes.Ldc_I4, 65);
            wrapperIl.Emit(OpCodes.Callvirt, typeof(IHostProbeBase).GetMethod(nameof(IHostProbeBase.Hidden))!);
            wrapperIl.Emit(OpCodes.Pop);
            wrapperIl.Emit(OpCodes.Ret);
        }

        var ret = type.DefineMethod("OnReturn", MethodAttributes.Public, typeof(int), [typeof(int)]);
        var retIl = ret.GetILGenerator();
        retIl.Emit(OpCodes.Ldarg_1);
        retIl.Emit(OpCodes.Call, typeof(SessionHooks).GetMethod(nameof(SessionHooks.HostReturnProbe))!);
        retIl.Emit(OpCodes.Ret);

        type.CreateType();
        builder.Save(path);
        return entryName;
    }

    private static void WriteHostDependency(string path, string assemblyName = "System.Custom.UgcDependency",
        string typeName = "System.Custom.UgcDependency.Call")
    {
        var identity = new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) };
        var builder = new PersistedAssemblyBuilder(identity, typeof(object).Assembly);
        var module = builder.DefineDynamicModule(identity.Name!);
        var type = module.DefineType(typeName,
            TypeAttributes.Public | TypeAttributes.Class | TypeAttributes.Abstract | TypeAttributes.Sealed);
        var echo = type.DefineMethod("Echo", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), [typeof(IHostProbe)]);
        var il = echo.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Ldc_I4, 11);
        il.Emit(OpCodes.Callvirt, typeof(IHostProbe).GetMethod(nameof(IHostProbe.Echo))!);
        il.Emit(OpCodes.Ret);

        var sessionOnly = type.DefineMethod("SessionOnly", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), Type.EmptyTypes);
        var sessionIl = sessionOnly.GetILGenerator();
        sessionIl.Emit(OpCodes.Ldc_I4, 0);
        sessionIl.Emit(OpCodes.Ret);

        type.CreateType();
        builder.Save(path);
    }

    private static string WriteHostManifest(string directory, string entryFile, string entryType, string[] methods, string? dependencyFile = null)
    {
        string entryPath = Path.Combine(directory, entryFile);
        string hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(entryPath)));
        string empty = new string('0', 64);
        var contract = new InputIdentity("host-contract.dll", new string('d', 64),
            typeof(IHostProbe).Assembly.GetName().FullName);
        var files = new List<PackageFile> { new(entryFile, hash) };
        var dependencies = new List<PackageDependency>();
        var inputs = new List<InputIdentity> { new(entryFile, hash) };
        if (dependencyFile is not null)
        {
            string dependencyPath = Path.Combine(directory, dependencyFile);
            byte[] dependencyBytes = File.ReadAllBytes(dependencyPath);
            string dependencyHash = Convert.ToHexString(SHA256.HashData(dependencyBytes));
            files.Add(new PackageFile(dependencyFile, dependencyHash));
            dependencies.Add(new PackageDependency(dependencyFile,
                ManagedAssemblyInspector.Inspect(dependencyBytes).AssemblyName, dependencyHash));
            inputs.Add(new InputIdentity(dependencyFile, dependencyHash));
        }
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty), contract], inputs.ToArray());
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion,
            PackageFormat.InputProfile, "host-policy", entryFile, entryType, hash, dependencies.ToArray(), files.ToArray(),
            producer, "", typeof(IHostProbe).FullName, methods);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        string path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private sealed class HostPolicy : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) =>
            operation == ApiOperation.Invoke && target.MemberName is "Denied" or "Effect"
                ? ApiDecision.Deny("Host policy denies this target.")
                : ApiDecision.Allow;
    }

    private sealed class AllowAllPolicy : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) => ApiDecision.Allow;
    }

    private sealed class SessionCodePolicy : IApiAccessPolicy
    {
        public ApiDecision Evaluate(ApiTarget target, ApiOperation operation) =>
            target.IsSessionCode && target.MemberName == "SessionOnly"
                ? ApiDecision.Deny("Session dependency target is denied.")
                : ApiDecision.Allow;
    }

    private class GenericPolicyHost : IGenericProbe<int>
    {
        public int EchoCalls { get; protected set; }
        public int HiddenCalls { get; protected set; }
        public virtual int Echo(int value) { EchoCalls++; return value; }
        public virtual int Hidden(int value) { HiddenCalls++; return value; }
    }

    private class NonVirtualBaseHostBase
    {
        public int BaseHiddenCalls { get; private set; }
        public int Hidden(int value) { BaseHiddenCalls++; return value; }
    }

    private sealed class NonVirtualBaseHost : NonVirtualBaseHostBase, IGenericProbe<int>
    {
        public int EchoCalls { get; private set; }
        public int DerivedHiddenCalls { get; private set; }
        public int Echo(int value) { EchoCalls++; return value; }
        public new int Hidden(int value) { DerivedHiddenCalls++; return value; }
    }

    private class ObjectBaseHostBase
    {
        public int ObjectHiddenCalls { get; private set; }
        public int Hidden(object value) { ObjectHiddenCalls++; return (int)value; }
    }

    private sealed class ObjectBaseHost : ObjectBaseHostBase, IGenericProbe<int>
    {
        public int EchoCalls { get; private set; }
        public int IntHiddenCalls { get; private set; }
        public int Echo(int value) { EchoCalls++; return value; }
        public int Hidden(int value) { IntHiddenCalls++; return value; }
    }

    private sealed class ExplicitGenericPolicyHost : IGenericProbe<int>
    {
        public int EchoCalls { get; private set; }
        public int HiddenCalls { get; private set; }
        int IGenericProbe<int>.Echo(int value) { EchoCalls++; return value; }
        int IGenericProbeBase<int>.Hidden(int value) { HiddenCalls++; return value; }
    }

    private sealed class DerivedGenericHost : GenericPolicyHost
    {
        public override int Hidden(int value)
        {
            HiddenCalls++;
            return value;
        }
    }

    private sealed class PolicyHost : IHostProbe
    {
        public int EchoCalls { get; private set; }
        public int DeniedCalls { get; private set; }
        public int HiddenCalls { get; private set; }
        public int Echo(int value) { EchoCalls++; return value; }
        public int Denied(int value) { DeniedCalls++; return value; }
        public int Hidden(int value) { HiddenCalls++; return value; }
    }
}
