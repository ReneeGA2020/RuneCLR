using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.PortableExecutable;
using System.Reflection.Emit;
using System.Security.Cryptography;
using RuneCLR.Packages;
using RuneCLR.Runtime;

internal static class HostContractSessionTests
{
    internal static IEnumerable<(string Name, Action Run)> Cases()
    {
        yield return ("Host contract OnStart receives the host instance and the context unloads", EchoAndUnload);
        yield return ("Host contract rejects an OnStart parameter that is not the host interface", RejectWrongParameter);
        yield return ("Host contract rejects an OnStart call that is not a host contract member", RejectForeignCall);
        yield return ("Host contract rejects an interface method that is not allowed", RejectUnlistedInterfaceMethod);
        yield return ("Host contract Invoke runs a later callback on the same session", InvokeLaterCallback);
        yield return ("Host contract Invoke rejects an unlisted later call before it runs", InvokeRejectsUnlisted);
        yield return ("Host contract Invoke passes the host interface into a later callback", InvokePassesTheHostAgain);
        yield return ("Host contract Invoke rejects a reentrant callback", InvokeRejectsReentry);
        yield return ("Host contract Invoke reports callback failure as text and continues", InvokeFailureIsText);
        yield return ("Host contract OnStart failure is text and does not return the session", OnStartFailureIsText);
        yield return ("Host contract Open uses the manifest allow list", OpenUsesManifest);
        yield return ("Host contract Open rejects a call outside the manifest allow list", OpenRejectsUnlisted);
        yield return ("Host contract Open rejects a different host interface", OpenRejectsInterface);
        yield return ("Host contract Open rejects a changed entry file", OpenRejectsEntryTamper);
        yield return ("Host contract Open rejects a manifest whose content hash does not match", OpenRejectsContentTamper);
        yield return ("Host contract Open rejects an entry path that escapes the package", OpenRejectsEscapingPath);
        yield return ("Host contract Open rejects an entry that is not a DLL", OpenRejectsNonDll);
        yield return ("Host contract Open rejects an entry missing from the file list", OpenRejectsUnlistedEntry);
        yield return ("Host contract Open rejects an entry hash that disagrees with the file list", OpenRejectsMismatchedFileHash);
        yield return ("Host contract Open rejects a dependency path that escapes the package", OpenRejectsEscapingDependency);
        yield return ("Host contract Open rejects a file that is not the entry or a dependency", OpenRejectsExtraFile);
        yield return ("Host contract Open accepts a dependency whose bytes match", OpenAcceptsDependency);
        yield return ("Host contract Open rejects a missing dependency file", OpenRejectsMissingDependency);
        yield return ("Host contract Open rejects a changed dependency file", OpenRejectsChangedDependency);
        yield return ("Host contract Open rejects a dependency that is not a managed assembly", OpenRejectsOpaqueDependency);
        yield return ("Host contract Open rejects a dependency that spoofs a framework name", OpenRejectsSpoofedDependency);
        yield return ("Host contract rejects a type initializer before the author runs", RejectTypeInitializer);
        yield return ("Host contract rejects a constructor call other than Object..ctor", RejectConstructorCall);
        yield return ("Host contract rejects an assembly that is not IL-only", RejectNativeImage);
        yield return ("Host contract rejects an assembly name that spoofs the framework", RejectSpoofedAssemblyName);
        yield return ("Host contract rejects a reference outside the contract assembly", RejectUnapprovedReference);
        yield return ("Host contract rejects unsafe IL before the author runs", RejectUnsafeIl);
        yield return ("Host contract rejects a static field load before the author runs", RejectStaticFieldLoad);
        yield return ("Host contract rejects boxing an author value type", RejectAuthorBox);
        yield return ("Host contract rejects an author array type before the author runs", RejectAuthorArray);
        yield return ("Host contract rejects a cast to an author type", RejectAuthorCast);
    }

    private static void EchoAndUnload()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "echo.dll");
            WriteScript(path, "HostContract.EchoScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
            var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.EchoScript.Script", ["Echo"]);
            var reference = session.ContextReference;
            session.Dispose();
            Check(host.Seen == 41, "The host did not observe Echo(41).");
            for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }

            Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
        }
        finally
        {
            directory.Dispose();
        }
    }

    private static void RejectWrongParameter()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "wrong.dll");
            WriteScript(path, "HostContract.WrongScript", typeof(object), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 7, cast: true);
            var error = CheckThrows<InvalidOperationException>(() =>
                new HostContractSession(typeof(IHostEcho), host, path, "HostContract.WrongScript.Script", ["Echo"]));
            Check(error.Message.Contains("host contract interface", StringComparison.Ordinal), error.Message);
            Check(host.Seen is null, "The author method was called.");
        }
        finally
        {
            directory.Dispose();
        }
    }


    private static void RejectForeignCall()
    {
        var host = new RecordingEcho();
        var directory = new TemporaryDirectory();
        try
        {
            var path = Path.Combine(directory.Path, "foreign.dll");
            WriteEchoAndForeignCall(path);
            var error = CheckThrows<InvalidOperationException>(() =>
                new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ForeignScript.Script", ["Echo"]));
            Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
            Check(host.Seen is null, "The author method was called.");
        }
        finally
        {
            directory.Dispose();
        }
    }


    private static void InvokeLaterCallback()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "later.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndLater(path, "HostContract.LaterScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.LaterScript.Script", ["Echo"]);
        Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
        session.Invoke("OnTick");
        Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not call Echo(2) after Echo(1).");
        var reference = session.ContextReference;
        session.Dispose();
        var disposed = CheckThrows<ObjectDisposedException>(() => session.Invoke("OnTick"));
        Check(disposed.ObjectName == nameof(HostContractSession), disposed.Message);
        for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
    }

    private static void InvokeRejectsUnlisted()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "later-other.dll");
        var other = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Other))!;
        WriteStartAndLater(path, "HostContract.LaterOtherScript", other, 1, 5);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.LaterOtherScript.Script", ["Echo"]);
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1]) && host.OtherSeen is null, "The unlisted callback ran.");
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void InvokePassesTheHostAgain()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "host-again.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndHostParameter(path, "HostContract.HostAgainScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.HostAgainScript.Script", ["Echo"]);
        try
        {
            Check(host.Calls.SequenceEqual([1]), "OnStart did not call Echo(1).");
            session.Invoke("OnTick");
            Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not receive the host instance.");
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void InvokeRejectsReentry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "reentry.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartAndHostParameter(path, "HostContract.ReentryScript", echo, 1, 2);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ReentryScript.Script", ["Echo"]);
        host.Nested = session;
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.InnerException is null, "The callback exception was retained.");
            Check(error.Message.Contains("already running", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1, 2]), "The nested callback ran.");
        }
        finally
        {
            host.Nested = null;
            session.Dispose();
        }
    }

    private static void InvokeFailureIsText()
    {
        var host = new RecordingEcho { ThrowOn = 2 };
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "failure.dll");
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        WriteStartTickStop(path, "HostContract.FailureScript", echo);
        var session = new HostContractSession(typeof(IHostEcho), host, path, "HostContract.FailureScript.Script", ["Echo"]);
        try
        {
            var error = CheckThrows<InvalidOperationException>(() => session.Invoke("OnTick"));
            Check(error.InnerException is null, "The callback exception was retained.");
            Check(error.Message.Contains("System.InvalidOperationException: host-failed", StringComparison.Ordinal), error.Message);
            Check(host.Calls.SequenceEqual([1, 2]), "OnTick did not reach the host.");
            session.Invoke("OnStop");
            Check(host.Calls.SequenceEqual([1, 2, 3]), "The session did not continue after the failure.");
            var reference = session.ContextReference;
            session.Dispose();
            for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }

            Check(!reference.IsAlive, error.Message);
        }
        finally
        {
            session.Dispose();
        }
    }

    private static void OnStartFailureIsText()
    {
        var host = new RecordingEcho { ThrowOn = 9 };
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "start-failure.dll");
        WriteScript(path, "HostContract.StartFailureScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 9, cast: false);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.StartFailureScript.Script", ["Echo"]));
        Check(error.InnerException is null, "The OnStart exception was retained.");
        Check(error.Message.Contains("System.InvalidOperationException: host-failed", StringComparison.Ordinal), error.Message);
        Check(host.Calls.SequenceEqual([9]), "OnStart did not reach the host.");
        GC.KeepAlive(error);
    }

    private static void OpenUsesManifest()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        var reference = session.ContextReference;
        session.Dispose();
        Check(host.Seen == 41, "The manifest allow list did not reach Echo.");
        for (var attempt = 0; attempt < 10 && reference.IsAlive; attempt++)
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();
        }

        Check(!reference.IsAlive, "The collectible context was still alive after Dispose.");
    }

    private static void OpenRejectsUnlisted()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenRejectScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenRejectScript.Script", typeof(IHostEcho).FullName!, ["Other"]);
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unlisted manifest call ran.");
    }

    private static void OpenRejectsInterface()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenInterfaceScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenInterfaceScript.Script", "Other.Contract", ["Echo"]);
        var error = CheckThrows<InvalidOperationException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("does not match", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The mismatched interface ran.");
    }

    private static void OpenRejectsEntryTamper()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenEntryScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenEntryScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var bytes = File.ReadAllBytes(path);
        bytes[^1] ^= 0xFF;
        File.WriteAllBytes(path, bytes);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The tampered entry ran.");
    }

    private static void OpenRejectsContentTamper()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "echo.dll");
        WriteScript(path, "HostContract.OpenContentScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteManifest(directory.Path, "echo.dll", "HostContract.OpenContentScript.Script", typeof(IHostEcho).FullName!, ["Echo"]);
        var json = File.ReadAllText(manifest).Replace(typeof(IHostEcho).FullName!, nameof(IHostEcho) + "0", StringComparison.Ordinal);
        File.WriteAllText(manifest, json);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("content identity", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The tampered manifest ran.");
    }

    private static void OpenRejectsEscapingPath()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteManifestUnchecked(directory.Path, "../echo.dll");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The escaping entry ran.");
    }

    private static void OpenRejectsNonDll()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteManifestUnchecked(directory.Path, "echo.txt");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The non-DLL entry ran.");
    }

    private static void OpenRejectsUnlistedEntry()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteListedManifest(directory.Path, "echo.dll", new string('a', 64), "other.dll", new string('b', 64));
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The unlisted entry ran.");
    }

    private static void OpenRejectsMismatchedFileHash()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteListedManifest(directory.Path, "echo.dll", new string('a', 64), "echo.dll", new string('b', 64));
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The mismatched entry ran.");
    }

    private static void OpenRejectsEscapingDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteDependencyManifest(directory.Path, "../lib.dll", false);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("canonical relative DLL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The escaping dependency ran.");
    }

    private static void OpenRejectsExtraFile()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var manifest = WriteDependencyManifest(directory.Path, "lib.dll", true);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("exactly match the entry", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra file ran.");
    }

    private static void OpenAcceptsDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenDependencyScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 41, cast: false);
        WriteScript(library, "HostContract.Library", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenDependencyScript.Script");
        var session = HostContractSession.Open(manifest, typeof(IHostEcho), host);
        session.Dispose();
        Check(host.Seen == 41, "A matching dependency blocked the host call.");
    }

    private static void OpenRejectsMissingDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        WriteScript(entry, "HostContract.OpenMissingScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, null, "HostContract.OpenMissingScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("lib.dll", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The missing dependency ran.");
    }

    private static void OpenRejectsChangedDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenChangedScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        File.WriteAllBytes(library, [1, 2, 3, 4]);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenChangedScript.Script");
        File.WriteAllBytes(library, [1, 2, 3, 5]);
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("hash mismatch", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The changed dependency ran.");
    }

    private static void OpenRejectsOpaqueDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenOpaqueScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        File.WriteAllBytes(library, [1, 2, 3, 4]);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenOpaqueScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("PE", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The opaque dependency ran.");
    }

    private static void OpenRejectsSpoofedDependency()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var entry = Path.Combine(directory.Path, "echo.dll");
        var library = Path.Combine(directory.Path, "lib.dll");
        WriteScript(entry, "HostContract.OpenSpoofDepScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 5, cast: false);
        WriteScript(library, "System.IO", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var manifest = WriteHashedDependency(directory.Path, entry, library, "HostContract.OpenSpoofDepScript.Script");
        var error = CheckThrows<InvalidDataException>(() => HostContractSession.Open(manifest, typeof(IHostEcho), host));
        Check(error.Message.Contains("spoofs", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The spoofed dependency ran.");
    }

    private static string WriteHashedDependency(string directory, string entryPath, string? libraryPath, string entryType)
    {
        var entryHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(entryPath)));
        var dependencyHash = libraryPath is null ? new string('b', 64) : Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(libraryPath)));
        var empty = new string('c', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity("echo.dll", entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", "echo.dll", entryType, entryHash,
            [new PackageDependency("lib.dll", "Lib, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", dependencyHash)],
            [new PackageFile("echo.dll", entryHash), new PackageFile("lib.dll", dependencyHash)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteDependencyManifest(string directory, string dependencyPath, bool extraFile)
    {
        var entryHash = new string('a', 64);
        var dependencyHash = new string('b', 64);
        var empty = new string('c', 64);
        var files = extraFile
            ? new[] { new PackageFile("echo.dll", entryHash), new PackageFile("extra.dll", dependencyHash) }
            : new[] { new PackageFile("echo.dll", entryHash), new PackageFile(dependencyPath, dependencyHash) };
        var dependencies = extraFile ? Array.Empty<PackageDependency>() : new[] { new PackageDependency(dependencyPath, "Lib, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null", dependencyHash) };
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity("echo.dll", entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", "echo.dll", "HostContract.OpenDependencyScript.Script", entryHash, dependencies, files, producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteListedManifest(string directory, string entryPath, string entryHash, string filePath, string fileHash)
    {
        var empty = new string('c', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(entryPath, entryHash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", entryPath, "HostContract.OpenListScript.Script", entryHash, [], [new PackageFile(filePath, fileHash)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteManifestUnchecked(string directory, string entryPath)
    {
        var empty = new string('a', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(entryPath, empty)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", entryPath, "HostContract.OpenPathScript.Script", empty, [], [new PackageFile(entryPath, empty)], producer, "",
            typeof(IHostEcho).FullName, ["Echo"]);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static string WriteManifest(string directory, string assemblyFile, string entryType, string hostInterface, string[] methods)
    {
        var hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(directory, assemblyFile))));
        var empty = new string('0', 64);
        var producer = new PackageProducer("RuneCLR.PackageTool", "0.1.0", "il", [],
            [new InputIdentity("references.dll", empty)], [new InputIdentity(assemblyFile, hash)]);
        var manifest = new PackageManifest(PackageFormat.CurrentVersion, PackageFormat.CurrentApiVersion, PackageFormat.InputProfile,
            "host-open", assemblyFile, entryType, hash, [], [new PackageFile(assemblyFile, hash)], producer, "",
            hostInterface, methods);
        manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
        var path = Path.Combine(directory, PackageFormat.ManifestFileName);
        PackageManifestIO.Write(path, manifest);
        return path;
    }

    private static void RejectTypeInitializer()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "initializer.dll");
        WriteInitializer(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.InitializerScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initializer", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The type initializer ran.");
    }

    private static void RejectConstructorCall()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "constructor.dll");
        WriteExtraConstructorCall(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ConstructorScript.Script", ["Echo"]));
        Check(error.Message.Contains("Object..ctor", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra constructor call ran.");
    }

    private static void WriteInitializer(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.InitializerScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.InitializerScript");
        var type = module.DefineType("HostContract.InitializerScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var initializer = type.DefineConstructor(MethodAttributes.Private | MethodAttributes.Static, CallingConventions.Standard, Type.EmptyTypes);
        var initializerIl = initializer.GetILGenerator();
        initializerIl.Emit(OpCodes.Ldstr, "initializer-ran");
        initializerIl.Emit(OpCodes.Newobj, typeof(InvalidOperationException).GetConstructor(new[] { typeof(string) })!);
        initializerIl.Emit(OpCodes.Throw);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteExtraConstructorCall(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ConstructorScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ConstructorScript");
        var type = module.DefineType("HostContract.ConstructorScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Callvirt, typeof(object).GetMethod(nameof(object.ToString), Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Pop);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectNativeImage()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "native.dll");
        WriteScript(path, "HostContract.NativeScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        ClearIlOnly(path);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.NativeScript.Script", ["Echo"]));
        Check(error.Message.Contains("IL-only", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The native image ran.");
    }

    private static void ClearIlOnly(string path)
    {
        var bytes = File.ReadAllBytes(path);
        using var stream = new MemoryStream(bytes, writable: false);
        using var pe = new PEReader(stream, PEStreamOptions.LeaveOpen);
        var flags = (uint)(pe.PEHeaders.CorHeader!.Flags & ~CorFlags.ILOnly);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(pe.PEHeaders.CorHeaderStartOffset + 16), flags);
        File.WriteAllBytes(path, bytes);
    }

    private static void RejectSpoofedAssemblyName()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "spoof.dll");
        WriteScript(path, "System.IO", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!, 1, cast: false);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "System.IO.Script", ["Echo"]));
        Check(error.Message.Contains("spoofs", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("System.IO", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The spoofed assembly ran.");
    }

    private static void RejectUnapprovedReference()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "reference.dll");
        WriteExtraReference(path);
        var error = CheckThrows<InvalidDataException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ReferenceScript.Script", ["Echo"]));
        Check(error.Message.Contains("not approved", StringComparison.Ordinal), error.Message);
        Check(error.Message.Contains("RuneCLR.Packages", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The extra reference ran.");
    }

    private static void WriteExtraReference(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ReferenceScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ReferenceScript");
        var type = module.DefineType("HostContract.ReferenceScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        type.DefineField("extra", typeof(PackageManifest), FieldAttributes.Private);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectUnsafeIl()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "unsafe.dll");
        WriteUnsafeOnStart(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.UnsafeScript.Script", ["Echo"]));
        Check(error.Message.Contains("Unsafe IL", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "Unsafe IL ran.");
    }

    private static void WriteUnsafeOnStart(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.UnsafeScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.UnsafeScript");
        var type = module.DefineType("HostContract.UnsafeScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_4);
        il.Emit(OpCodes.Localloc);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectStaticFieldLoad()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "static.dll");
        WriteStaticFieldLoad(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.StaticScript.Script", ["Echo"]));
        Check(error.Message.Contains("Static field", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The static field load ran.");
    }

    private static void WriteStaticFieldLoad(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.StaticScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.StaticScript");
        var type = module.DefineType("HostContract.StaticScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldsfld, typeof(string).GetField(nameof(string.Empty))!);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorBox()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "box.dll");
        WriteAuthorBox(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.BoxScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author box ran.");
    }

    private static void WriteAuthorBox(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.BoxScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.BoxScript");
        var bomb = module.DefineType("HostContract.BoxScript.Bomb",
            TypeAttributes.Public | TypeAttributes.Sealed | TypeAttributes.SequentialLayout | TypeAttributes.BeforeFieldInit, typeof(ValueType));
        bomb.DefineField("value", typeof(int), FieldAttributes.Public);
        var type = module.DefineType("HostContract.BoxScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_0);
        il.Emit(OpCodes.Box, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorArray()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "array.dll");
        WriteAuthorArray(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.ArrayScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author array ran.");
    }

    private static void WriteAuthorArray(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ArrayScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ArrayScript");
        var bomb = module.DefineType("HostContract.ArrayScript.Bomb", TypeAttributes.Public | TypeAttributes.Class);
        var type = module.DefineType("HostContract.ArrayScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Newarr, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectAuthorCast()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "cast.dll");
        WriteAuthorCast(path);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.CastScript.Script", ["Echo"]));
        Check(error.Message.Contains("type initialization", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null, "The author cast ran.");
    }

    private static void WriteAuthorCast(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.CastScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.CastScript");
        var bomb = module.DefineType("HostContract.CastScript.Bomb", TypeAttributes.Public | TypeAttributes.Class);
        var type = module.DefineType("HostContract.CastScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldnull);
        il.Emit(OpCodes.Castclass, bomb);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 1);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        bomb.CreateType();
        type.CreateType();
        builder.Save(path);
    }

    private static void RejectUnlistedInterfaceMethod()
    {
        var host = new RecordingEcho();
        using var directory = new TemporaryDirectory();
        var path = Path.Combine(directory.Path, "other.dll");
        WriteScript(path, "HostContract.OtherScript", typeof(IHostEcho), typeof(IHostEcho).GetMethod(nameof(IHostEcho.Other))!, 5, cast: false);
        var error = CheckThrows<InvalidOperationException>(() =>
            new HostContractSession(typeof(IHostEcho), host, path, "HostContract.OtherScript.Script", ["Echo"]));
        Check(error.Message.Contains("host contract member", StringComparison.Ordinal), error.Message);
        Check(host.Seen is null && host.OtherSeen is null, "The author method was called.");
    }
    private static void WriteStartTickStop(string path, string assemblyName, MethodInfo echo)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        void EmitCall(string name, int value)
        {
            var method = type.DefineMethod(name, MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
            var il = method.GetILGenerator();
            il.Emit(OpCodes.Ldarg_1);
            il.Emit(OpCodes.Ldc_I4, value);
            il.Emit(OpCodes.Callvirt, echo);
            il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Ret);
        }

        EmitCall("OnStart", 1);
        EmitCall("OnTick", 2);
        EmitCall("OnStop", 3);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndHostParameter(string path, string assemblyName, MethodInfo later, int startValue, int laterValue)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Ldc_I4, startValue);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_1);
        tickIl.Emit(OpCodes.Ldc_I4, laterValue);
        tickIl.Emit(OpCodes.Callvirt, later);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteStartAndLater(string path, string assemblyName, MethodInfo later, int startValue, int laterValue)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var field = type.DefineField("host", typeof(IHostEcho), FieldAttributes.Private);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var startIl = start.GetILGenerator();
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldarg_1);
        startIl.Emit(OpCodes.Stfld, field);
        startIl.Emit(OpCodes.Ldarg_0);
        startIl.Emit(OpCodes.Ldfld, field);
        startIl.Emit(OpCodes.Ldc_I4, startValue);
        startIl.Emit(OpCodes.Callvirt, echo);
        startIl.Emit(OpCodes.Pop);
        startIl.Emit(OpCodes.Ret);
        var tick = type.DefineMethod("OnTick", MethodAttributes.Public, typeof(void), Type.EmptyTypes);
        var tickIl = tick.GetILGenerator();
        tickIl.Emit(OpCodes.Ldarg_0);
        tickIl.Emit(OpCodes.Ldfld, field);
        tickIl.Emit(OpCodes.Ldc_I4, laterValue);
        tickIl.Emit(OpCodes.Callvirt, later);
        tickIl.Emit(OpCodes.Pop);
        tickIl.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteEchoAndForeignCall(string path)
    {
        var echo = typeof(IHostEcho).GetMethod(nameof(IHostEcho.Echo))!;
        var toString = typeof(object).GetMethod(nameof(object.ToString), Type.EmptyTypes)!;
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName("HostContract.ForeignScript") { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule("HostContract.ForeignScript");
        var type = module.DefineType("HostContract.ForeignScript.Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [typeof(IHostEcho)]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Ldc_I4, 41);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ldarg_1);
        il.Emit(OpCodes.Callvirt, toString);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void WriteScript(string path, string assemblyName, Type parameterType, MethodInfo echo, int value, bool cast)
    {
        var builder = new PersistedAssemblyBuilder(
            new AssemblyName(assemblyName) { Version = new Version(1, 0, 0, 0) },
            typeof(object).Assembly);
        var module = builder.DefineDynamicModule(assemblyName);
        var type = module.DefineType(assemblyName + ".Script", TypeAttributes.Public | TypeAttributes.Class);
        var constructor = type.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, Type.EmptyTypes);
        var constructorIl = constructor.GetILGenerator();
        constructorIl.Emit(OpCodes.Ldarg_0);
        constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
        constructorIl.Emit(OpCodes.Ret);
        var start = type.DefineMethod("OnStart", MethodAttributes.Public, typeof(void), [parameterType]);
        var il = start.GetILGenerator();
        il.Emit(OpCodes.Ldarg_1);
        if (cast) il.Emit(OpCodes.Castclass, typeof(IHostEcho));
        il.Emit(OpCodes.Ldc_I4, value);
        il.Emit(OpCodes.Callvirt, echo);
        il.Emit(OpCodes.Pop);
        il.Emit(OpCodes.Ret);
        type.CreateType();
        builder.Save(path);
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private static T CheckThrows<T>(Action action) where T : Exception
    {
        try
        {
            action();
        }
        catch (T exception)
        {
            return exception;
        }

        throw new InvalidOperationException("Expected " + typeof(T).Name + ".");
    }

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "runeclr-host-contract-" + Guid.NewGuid().ToString("n"));
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}

public interface IHostEcho
{
    int Echo(int value);
    int Other(int value);
}

sealed class RecordingEcho : IHostEcho
{
    public int? Seen { get; private set; }

    public int? OtherSeen { get; private set; }

    public List<int> Calls { get; } = [];

    public HostContractSession? Nested { get; set; }

    public int? ThrowOn { get; set; }

    public int Echo(int value)
    {
        Seen = value;
        Calls.Add(value);
        if (value == 2 && Nested is not null)
            Nested.Invoke("OnTick");
        if (ThrowOn == value) throw new InvalidOperationException("host-failed");
        return value;
    }

    public int Other(int value)
    {
        OtherSeen = value;
        return value;
    }
}
