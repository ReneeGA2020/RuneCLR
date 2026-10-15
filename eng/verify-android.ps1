param(
    [string]$AndroidRoot = 'D:/RuneCLR-Android',
    [string]$RuntimeRepo = 'E:/runtime',
    [string]$TemplateRun = 'D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351',
    [string]$RuntimePackDirectory,
    [string]$DotnetExecutable = 'dotnet',
    [string]$OperatorDotnetExecutable = 'dotnet',
    [string]$EvidenceDirectory,
    [switch]$BuildOnly,
    [switch]$ControlledPackages
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sdk = Join-Path $AndroidRoot 'sdk'
$ndk = Join-Path $sdk 'ndk/27.2.12479018'
$java = Join-Path $AndroidRoot 'android-studio/jbr'
$adb = Join-Path $sdk 'platform-tools/adb.exe'
$emulator = Join-Path $sdk 'emulator/emulator.exe'
$ninja = 'C:/Program Files/Microsoft Visual Studio/2022/Professional/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja'
$packageRoot = if ($RuntimePackDirectory) { [IO.Path]::GetFullPath($RuntimePackDirectory) } else { Join-Path $TemplateRun 'package/extracted' }
$dotnet = (Get-Command $DotnetExecutable -ErrorAction Stop).Source
$operatorDotnet = if ($ControlledPackages) { (Get-Command $OperatorDotnetExecutable -ErrorAction Stop).Source } else { $dotnet }
$serial = 'emulator-5556'; $avdName = 'RuneCLR_API_35_x64'
# Each private build has its own debug signing key; a unique package preserves
# older fixtures and avoids updating an APK signed with a different debug key.
$projectName = 'RuneCLR_Lifecycle_' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$appId = 'net.dot.' + $projectName
foreach ($required in "$ndk/source.properties", "$java/bin/javac.exe", $adb, $emulator,
    "$TemplateRun/builder/builder.csproj", "$packageRoot/Microsoft.NETCore.App.Runtime.android-x64.nuspec",
    "$sdk/platforms/android-36/android.jar", "$sdk/build-tools/35.0.1/aapt.exe") {
    if (!(Test-Path -LiteralPath $required)) { throw ('Missing Android build input: ' + $required) }
}
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $root ('artifacts/android/lifecycle-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N')) }
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory)
if (Test-Path -LiteralPath $evidence) { throw 'Use a fresh evidence directory; historical APKs and outputs must be preserved.' }
New-Item -ItemType Directory -Path $evidence | Out-Null
function Invoke-Logged([string]$File, [string[]]$Arguments, [string]$Log) {
    & $File @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $Log -Tail 35; throw ('Command failed with exit code ' + $LASTEXITCODE + ': ' + $File) }
}
function Hash-Tree([string]$Directory) {
    @(Get-ChildItem -LiteralPath $Directory -Recurse -File | Where-Object { $_.FullName -notmatch '[/\\](bin|obj)[/\\]' } | ForEach-Object {
        [pscustomobject]@{ path = [IO.Path]::GetRelativePath($Directory, $_.FullName); sha256 = (Get-FileHash -LiteralPath $_.FullName).Hash }
    })
}
function Adb([string[]]$Arguments) {
    $output = & $adb -s $serial @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('ADB failed: ' + ($Arguments -join ' ') + ' ' + ($output -join [Environment]::NewLine)) }
    ($output -join [Environment]::NewLine).Trim()
}
$oldPath = $env:PATH; $oldJava = $env:JAVA_HOME
$oldSdk = $env:ANDROID_SDK_ROOT; $oldAndroidHome = $env:ANDROID_HOME; $oldAvd = $env:ANDROID_AVD_HOME
$startedEmulator = $false
$app = Join-Path $evidence 'app'; $builder = Join-Path $evidence 'builder'; $generated = Join-Path $evidence 'host'
New-Item -ItemType Directory -Path $app, $builder, $generated, "$evidence/headers/hosts", "$evidence/headers/native/corehost" | Out-Null
Get-ChildItem -LiteralPath "$TemplateRun/builder" -Force | Where-Object Name -notin 'bin', 'obj' | Copy-Item -Destination $builder -Recurse
Copy-Item "$RuntimeRepo/src/coreclr/hosts/inc/*" "$evidence/headers/hosts"
Copy-Item "$RuntimeRepo/src/native/corehost/host_runtime_contract.h" "$evidence/headers/native/corehost"
Copy-Item "$root/global.json" "$evidence/global.json"
# The upstream build-task snapshot has its own project settings; do not inherit
# RuneCLR's implicit usings and warnings policy through the artifacts directory.
'<Project />' | Set-Content "$evidence/Directory.Build.props"
@'
<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><AssemblyName>RuneCLR.AndroidLifecycleHost</AssemblyName></PropertyGroup></Project>
'@ | Set-Content "$generated/host.csproj"
if ($ControlledPackages) {
    $runtimeReference = [Security.SecurityElement]::Escape("$app/RuneCLR.Runtime.dll")
    $packagesReference = [Security.SecurityElement]::Escape("$app/RuneCLR.Packages.dll")
    (Get-Content "$generated/host.csproj" -Raw).Replace('</Project>', "<ItemGroup><Reference Include='RuneCLR.Runtime'><HintPath>$runtimeReference</HintPath></Reference><Reference Include='RuneCLR.Packages'><HintPath>$packagesReference</HintPath></Reference></ItemGroup></Project>") | Set-Content "$generated/host.csproj"
}
@'
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
var originalOut = Console.Out;
var originalError = Console.Error;
var root = AppContext.BaseDirectory;
var logPath = Path.Combine(root, "lifecycle-output.log");
var resultPath = Path.Combine(root, "lifecycle-result.json");
var lateManifest = Path.Combine(root, "late", "map.json");
int code = 1;
int controlledPassed = 0;
using (var writer = new StreamWriter(logPath) { AutoFlush = true })
{
    Console.SetOut(writer); Console.SetError(writer);
    try
    {
        Console.WriteLine("ANDROID_LIFECYCLE framework=" + RuntimeInformation.FrameworkDescription + "; arch=" + RuntimeInformation.ProcessArchitecture);
        Console.WriteLine("ANDROID_LIFECYCLE CoreLib=" + typeof(object).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion);
        var harness = Assembly.LoadFrom(Path.Combine(root, "RuneCLR.Runtime.Tests.dll"));
        string[] harnessArgs = File.Exists(lateManifest) ? ["--late-map", lateManifest] : [];
        object? outcome = harness.EntryPoint!.Invoke(null, [harnessArgs]);
        code = outcome is Task<int> task ? task.GetAwaiter().GetResult() : (int)outcome!;
        if (File.Exists(Path.Combine(root, "controlled", "source", "package.json")))
            controlledPassed = ControlledAcceptance.Run(root);
    }
    catch (Exception exception) { code = 1; Console.WriteLine(exception.ToString()); }
    finally { Console.SetOut(originalOut); Console.SetError(originalError); }
}
File.WriteAllText(resultPath, JsonSerializer.Serialize(new { returnCode = code, controlledPassed, lateMap = File.Exists(lateManifest), framework = RuntimeInformation.FrameworkDescription, arch = RuntimeInformation.ProcessArchitecture.ToString(), scope = "Real RuneCLR lifecycle harness; stock Android CoreCLR JIT, not interpreter proof" }));
Console.WriteLine(File.ReadAllText(logPath));
Console.WriteLine("ANDROID_LIFECYCLE return-code=" + code);
return code;
'@ | Set-Content "$generated/Program.cs"
if (!$ControlledPackages) {
    (Get-Content "$generated/Program.cs" -Raw).Replace('            controlledPassed = ControlledAcceptance.Run(root);', '            throw new InvalidOperationException("Controlled acceptance was not enabled.");') | Set-Content "$generated/Program.cs"
}
if ($ControlledPackages) {
@'
using RuneCLR.Packages;
using RuneCLR.Runtime;
internal static class ControlledAcceptance
{
    internal static int Run(string root)
    {
        var passed = 0;
        void Case(string name, Action action) { action(); passed++; Console.WriteLine("PASS controlled " + name); }
        string Manifest(string name) => Path.Combine(root, "controlled", name, "package.json");
        void Valid(string name)
        {
            var result = new MapRunner().Run(MapPackage.FromManifest(Manifest(name)));
            Assert(result.Report.Outcome == MapRunOutcome.Completed, result.Report.Error ?? "Unexpected author failure.");
            Assert(result.Report.Logs.SequenceEqual(new[] { "starts=1", "stopped" }), "Static state or stop callback mismatch.");
            Clean(result);
        }
        Case("source fresh session", () => Valid("source"));
        Case("imported IL fresh session", () => Valid("import"));
        Case("source reused with fresh static state", () => Valid("source"));
        Case("author failure cleanup and unload", () =>
        {
            var result = new MapRunner().Run(MapPackage.FromManifest(Manifest("failure")));
            Assert(result.Report.Outcome == MapRunOutcome.Failed && result.Report.Error?.Contains("after-spawn") == true, "Expected ordinary author failure.");
            Assert(result.Report.Logs.SequenceEqual(new[] { "starts=1", "stopped" }), "Failure skipped stop callback.");
            Clean(result);
        });
        Case("valid recovery after failure", () => Valid("source"));
        Case("tampered package rejected before execution", () => Rejected(Manifest("tampered"), false));
        Case("rehashed forbidden API rejected before execution", () => Rejected(Manifest("forbidden"), true));
        Case("valid recovery after rejected packages", () => Valid("source"));
        Console.WriteLine(passed + "/8 controlled package tests passed");
        return passed;
    }
    private static void Rejected(string manifest, bool policy)
    {
        try { MapPackage.FromManifest(manifest); }
        catch (InvalidDataException error)
        {
            Assert(!policy || error.Message.Contains(GameplayCapabilityPolicy.Profile), "Rehashed package was not rejected by capability policy.");
            return;
        }
        throw new InvalidOperationException("Unsafe package reached loading.");
    }
    private static void Clean(MapRunResult result)
    {
        Assert(result.Report.CreatedEntities == 1 && result.Report.ReleasedEntities == 1 && result.Report.RemainingEntities == 0, "Entity cleanup failed.");
        for (var attempt = 0; attempt < 10 && !result.Unload.IsCollected; attempt++)
        { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); Thread.Sleep(10); }
        Assert(result.Unload.IsCollected, "Collectible context stayed alive.");
    }
    private static void Assert(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
}
'@ | Set-Content "$generated/ControlledAcceptance.cs"
    $operator = Join-Path $evidence 'operator'
    New-Item -ItemType Directory -Path $operator | Out-Null
    $compilerProject = [Security.SecurityElement]::Escape("$root/src/RuneCLR.Compiler/RuneCLR.Compiler.csproj")
    @"
<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><ProjectReference Include="$compilerProject" /></ItemGroup></Project>
"@ | Set-Content "$operator/operator.csproj"
@'
using RuneCLR.Compiler;
using RuneCLR.Packages;
using System.Security.Cryptography;
var output = args[0]; var refs = args[1]; var contract = args[2];
Directory.CreateDirectory(output);
var profile = new ReferenceProfile(refs, contract);
const string source = """
using RuneCLR;
public sealed class GameScript : IMapScript
{
    private static int starts; private IMapContext? context;
    public void OnStart(IMapContext value) { context = value; context.Log("starts=" + (++starts)); context.SpawnEntity("controlled"); }
    public void OnTick(MapTick tick) { }
    public void OnStop() { context!.Log("stopped"); }
}
""";
void Build(string name, string text)
{
    File.WriteAllText(Path.Combine(output, name + ".cs"), text);
    var result = PackageBuilder.Compile("ControlledGame", "GameScript", [new("GameScript.cs", text)], profile, Path.Combine(output, name));
    if (!result.Succeeded) throw new InvalidOperationException(string.Join(";", result.Diagnostics.Select(item => item.Message)));
}
Build("source", source);
var imported = PackageBuilder.Import("ImportedGame", "GameScript", Path.Combine(output, "source", "ControlledGame.dll"), profile, Path.Combine(output, "import"));
if (!imported.Succeeded) throw new InvalidOperationException("IL import failed.");
Build("failure", source.Replace("context.SpawnEntity(\"controlled\");", "context.SpawnEntity(\"controlled\"); throw new System.InvalidOperationException(\"after-spawn\");"));
void Clone(string name)
{
    Directory.CreateDirectory(Path.Combine(output, name));
    foreach (var path in Directory.EnumerateFiles(Path.Combine(output, "source"))) File.Copy(path, Path.Combine(output, name, Path.GetFileName(path)));
}
Clone("tampered"); File.AppendAllText(Path.Combine(output, "tampered", "ControlledGame.dll"), "changed");
Clone("forbidden");
var deniedSource = source.Replace("context.SpawnEntity(\"controlled\");", "context.SpawnEntity(\"controlled\"); System.GC.Collect();");
File.WriteAllText(Path.Combine(output, "forbidden.cs"), deniedSource);
var denied = SourceCompiler.Compile("ControlledGame", [new("GameScript.cs", deniedSource)], ReferenceProfile.FrameworkNames.Select(name => Path.Combine(refs, name + ".dll")).Append(contract).ToArray());
if (!denied.Succeeded) throw new InvalidOperationException("Forbidden raw fixture failed compilation.");
var manifestPath = Path.Combine(output, "forbidden", "package.json");
var manifest = PackageManifestIO.Read(manifestPath);
var hash = Convert.ToHexString(SHA256.HashData(denied.Assembly!)).ToLowerInvariant();
File.WriteAllBytes(Path.Combine(output, "forbidden", manifest.EntryAssembly), denied.Assembly!);
manifest = manifest with { EntrySha256 = hash, Files = manifest.Files.Select(file => file with { Sha256 = hash }).ToArray() };
manifest = manifest with { ContentSha256 = PackageManifestIO.ComputeContentSha256(manifest) };
PackageManifestIO.Write(manifestPath, manifest);
Console.WriteLine("Controlled packages produced: source, import, failure, tampered, rehashed-forbidden; profile=" + PackageFormat.InputProfile);
'@ | Set-Content "$operator/Program.cs"
}
@'
<Project>
 <UsingTask TaskName="AndroidAppBuilderTask" AssemblyFile="$(MSBuildThisFileDirectory)builder/bin/Release/net11.0/AndroidSmokeBuilder.dll" />
 <ItemGroup><Env Include="DOTNET_ReadyToRun"><Value>0</Value></Env><Env Include="DOTNET_TieredCompilation"><Value>0</Value></Env></ItemGroup>
 <Target Name="Build">
  <AndroidAppBuilderTask AppDir="$(MSBuildThisFileDirectory)app" MainLibraryFileName="RuneCLR.AndroidLifecycleHost.dll" RuntimeIdentifier="android-x64" RuntimeFlavor="CoreCLR" ProjectName="$(AndroidProjectName)" OutputDir="$(MSBuildThisFileDirectory)apk" AndroidSdk="$(AndroidSdk)" AndroidNdk="$(AndroidNdk)" RuntimeHeaders="$(MSBuildThisFileDirectory)headers/hosts;$(MSBuildThisFileDirectory)headers/native" BuildApiLevel="36" BuildToolsVersion="35.0.1" TargetApiLevel="35" MinApiLevel="24" StaticLinkedRuntime="false" ForceInterpreter="false" ForceAOT="false" StripDebugSymbols="false" EnvironmentVariables="@(Env)" />
 </Target>
</Project>
'@ | Set-Content "$evidence/package.proj"
try {
    $env:PATH = "$java/bin;$ninja;" + $oldPath
    $env:JAVA_HOME = $java; $env:ANDROID_SDK_ROOT = $sdk; $env:ANDROID_HOME = $sdk
    $env:ANDROID_AVD_HOME = Join-Path $AndroidRoot 'avd'
    Push-Location $root
    try { Invoke-Logged $dotnet @('build', 'RuneCLR.slnx', '-c', 'Release') "$evidence/host-build.log" } finally { Pop-Location }
    Copy-Item "$root/tests/RuneCLR.Runtime.Tests/bin/Release/net11.0/*" $app -Recurse
    if (Test-Path "$app/late") { throw 'Late map must not be packaged in the APK.' }
    Push-Location $evidence
    try {
        Invoke-Logged $dotnet @('build', 'builder/builder.csproj', '-c', 'Release') "$evidence/builder-build.log"
        Invoke-Logged $dotnet @('build', 'host/host.csproj', '-c', 'Release', '-o', $app) "$evidence/wrapper-build.log"
        if ($ControlledPackages) {
            Invoke-Logged $operatorDotnet @('build', "$operator/operator.csproj", '-c', 'Release') "$evidence/operator-build.log"
        }
        Get-ChildItem "$packageRoot/runtimes/android-x64/lib/net11.0" -File | Copy-Item -Destination $app
        Get-ChildItem "$packageRoot/runtimes/android-x64/native" -File | Copy-Item -Destination $app
        [IO.File]::WriteAllBytes("$app/runtimeconfig.bin", [byte[]]@(0))
        Invoke-Logged $dotnet @('msbuild', 'package.proj', '/t:Build', ('/p:AndroidSdk=' + $sdk), ('/p:AndroidNdk=' + $ndk), ('/p:AndroidProjectName=' + $projectName), '/v:minimal') "$evidence/apk-build.log"
    } finally { Pop-Location }
    $apk = Join-Path $evidence ('apk/bin/' + $projectName + '.apk')
    if (!(Test-Path $apk)) { throw 'APK missing after build.' }
    $apkHash = (Get-FileHash $apk).Hash
    $hostHash = (Get-FileHash "$app/RuneCLR.AndroidLifecycleHost.dll").Hash
    $harnessHash = (Get-FileHash "$app/RuneCLR.Runtime.Tests.dll").Hash
    # Inspect nested assets.zip rather than inferring its contents from staging.
    $zip = [IO.Compression.ZipFile]::OpenRead($apk)
    try {
        $asset = $zip.GetEntry('assets/assets.zip')
        if (!$asset) { throw 'APK has no managed assets.zip.' }
        $stream = $asset.Open(); $assets = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Read)
        try {
            $names = @($assets.Entries.FullName)
            if (@($names | Where-Object { $_ -like 'late/*' -or $_ -like '*RuneCLR.LateMap.dll' }).Count) { throw 'Late IL unexpectedly present in APK.' }
            if (@($names | Where-Object { $_ -like 'controlled/*' -or $_ -like '*ControlledGame.dll' -or $_ -like '*ImportedGame.dll' }).Count) { throw 'Post-install controlled IL unexpectedly present in APK.' }
            if (@($names | Where-Object { $_ -like '*Microsoft.CodeAnalysis*' -or $_ -like '*RuneCLR.Compiler*' -or $_ -like '*RuneCLR.PackageTool*' }).Count) { throw 'Operator compiler tooling must not enter Android player assets.' }
            foreach ($fixture in 'RuneCLR.Runtime.Tests.dll', 'RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll', 'Microsoft.NETCore.App.deps.json', 'fixtures/RuneCLR.TestMaps.dll', 'dependency-a/RuneCLR.PrivateDependency.dll', 'dependency-b/RuneCLR.PrivateDependency.dll') {
                if ($fixture -notin $names) { throw ('Required fixture absent from APK: ' + $fixture) }
            }
            if (@($names | Where-Object { $_ -in 'RuneCLR.TestMaps.dll', 'RuneCLR.PrivateDependency.dll', 'RuneCLR.DependencyMap.dll' }).Count) { throw 'Map-owned assembly was staged in default-root assets.' }
            $names | Set-Content "$evidence/apk-assets.txt"
        } finally { $assets.Dispose(); $stream.Dispose() }
    } finally { $zip.Dispose() }
    [xml]$nuspec = Get-Content "$packageRoot/Microsoft.NETCore.App.Runtime.android-x64.nuspec" -Raw
    $request = [ordered]@{
        startedUtc = [DateTime]::UtcNow.ToString('o'); hostCommit = (git -C $root rev-parse HEAD); hostWorkingTree = @(git -C $root status --short)
        wrapperSourceBase = (git -C $RuntimeRepo rev-parse HEAD); wrapperSources = (Hash-Tree $builder); wrapperHeaders = (Hash-Tree "$evidence/headers")
        hostSources = @((Hash-Tree "$root/src") + (Hash-Tree "$root/tests")); generatedHostSources = (Hash-Tree $generated)
        runtimePackageVersion = $nuspec.package.metadata.version; runtimePackageCommit = $nuspec.package.metadata.repository.commit
        runtimeFiles = @(Get-ChildItem "$packageRoot/runtimes/android-x64" -Recurse -File | ForEach-Object { @{ path = [IO.Path]::GetRelativePath($packageRoot, $_.FullName); sha256 = (Get-FileHash $_.FullName).Hash } })
        apk = $apk; apkSha256 = $apkHash; hostSha256 = $hostHash; harnessSha256 = $harnessHash
        stagedFiles = @(Get-ChildItem $app -Recurse -File | ForEach-Object { @{ path = [IO.Path]::GetRelativePath($app, $_.FullName); sha256 = (Get-FileHash $_.FullName).Hash } })
        sdk = (& $dotnet --version); dotnetExecutable = $dotnet; runtimePackDirectory = $packageRoot
        controlledPackages = [bool]$ControlledPackages; operatorSdk = (& $operatorDotnet --version); operatorDotnetExecutable = $operatorDotnet
        ndk = (Get-Content "$ndk/source.properties" -Raw); avd = $avdName; serial = $serial; packageId = $appId
        scope = 'Complete RuneCLR lifecycle harness on stock Android x64 CoreCLR JIT; not interpreted execution or physical-device proof'
    }
    $request | ConvertTo-Json -Depth 12 | Set-Content "$evidence/request.json"
    if ($BuildOnly) { Write-Host ('APK prepared: ' + $apk); return }
    $connected = & $adb devices
    if ($connected -match ($serial + '\s+device')) {
        $existing = Adb @('emu', 'avd', 'name')
        if ($existing -notmatch [regex]::Escape($avdName)) { throw 'Refusing to operate a different AVD on the dedicated port.' }
    } else {
        Start-Process -FilePath $emulator -ArgumentList @('-avd', $avdName, '-port', '5556', '-gpu', 'software', '-no-snapshot', '-no-metrics', '-no-window', '-no-audio') -WindowStyle Hidden
        $startedEmulator = $true
    }
    $deadline = [DateTime]::UtcNow.AddMinutes(4)
    do {
        $boot = & $adb -s $serial shell getprop sys.boot_completed 2>$null
        if ($boot -eq '1') { break }
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Dedicated AVD boot timed out.' }
        Start-Sleep -Seconds 2
    } while ($true)
    $existing = Adb @('emu', 'avd', 'name')
    if ($existing -notmatch [regex]::Escape($avdName)) { throw 'Booted AVD identity does not match.' }
    Invoke-Logged $adb @('-s', $serial, 'install', '-r', $apk) "$evidence/install.log"
    $installedUtc = [DateTime]::UtcNow
    function Run-Harness([string]$Label, [bool]$Late) {
        Invoke-Logged $adb @('-s', $serial, 'shell', 'am', 'force-stop', $appId) "$evidence/$Label-stop.log"
        Invoke-Logged $adb @('-s', $serial, 'shell', 'am', 'instrument', '-w', ($appId + '/net.dot.MonoRunner')) "$evidence/$Label-instrumentation.log"
        $log = Adb @('shell', 'run-as', $appId, 'cat', 'files/lifecycle-output.log')
        $log | Set-Content "$evidence/$Label-tests.log"
        $resultJson = Adb @('shell', 'run-as', $appId, 'cat', 'files/lifecycle-result.json')
        $resultJson | Set-Content "$evidence/$Label-result.json"
        $result = $resultJson | ConvertFrom-Json
        $counts = [regex]::Match($log, '(\d+)/(\d+) tests passed')
        if ($result.returnCode -ne 0 -or $result.lateMap -ne $Late -or !$counts.Success -or $counts.Groups[1].Value -ne $counts.Groups[2].Value -or $log -match '(?m)^FAIL ') {
            throw ('Android lifecycle harness failed; see ' + "$evidence/$Label-tests.log")
        }
        [pscustomobject]@{ result = $result; passed = [int]$counts.Groups[1].Value; total = [int]$counts.Groups[2].Value }
    }
    # This private APK's data only: ensure earlier late IL cannot affect baseline.
    $null = Adb @('shell', 'pm', 'clear', $appId)
    $baseline = Run-Harness 'baseline' $false
    $late = Join-Path $evidence 'late-output'
    $lateStartedUtc = [DateTime]::UtcNow
    if ($lateStartedUtc -le $installedUtc) { throw 'Late compilation must begin after APK installation.' }
    # Compile the real fixture source in isolated obj/output directories, avoiding
    # contention with concurrent desktop validation and any host project rebuild.
    $lateSource = Join-Path $evidence 'late-source'
    New-Item -ItemType Directory -Path $lateSource | Out-Null
    Copy-Item "$root/tests/RuneCLR.LateMap/*.cs" $lateSource
    Copy-Item "$root/tests/RuneCLR.LateMap/map.json" $lateSource
    $contractPath = [Security.SecurityElement]::Escape("$app/RuneCLR.Abstractions.dll")
    @"
<Project Sdk="Microsoft.NET.Sdk">
 <PropertyGroup><TargetFramework>net11.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><AssemblyName>RuneCLR.LateMap</AssemblyName><Deterministic>false</Deterministic><EnableDynamicLoading>true</EnableDynamicLoading></PropertyGroup>
 <ItemGroup><Reference Include="RuneCLR.Abstractions"><HintPath>$contractPath</HintPath></Reference><None Update="map.json" CopyToOutputDirectory="PreserveNewest" /></ItemGroup>
</Project>
"@ | Set-Content "$lateSource/late.csproj"
    Invoke-Logged $dotnet @('build', "$lateSource/late.csproj", '-c', 'Release', '-o', $late) "$evidence/late-build.log"
    if ((Get-FileHash $apk).Hash -ne $apkHash -or (Get-FileHash "$app/RuneCLR.AndroidLifecycleHost.dll").Hash -ne $hostHash -or (Get-FileHash "$app/RuneCLR.Runtime.Tests.dll").Hash -ne $harnessHash) { throw 'APK or host changed during late compilation.' }
    $null = Adb @('shell', 'run-as', $appId, 'mkdir', '-p', 'files/late')
    foreach ($name in 'RuneCLR.LateMap.dll', 'map.json') {
        $staged = '/data/local/tmp/runeclr-lifecycle-' + [Guid]::NewGuid().ToString('N') + '-' + $name
        $null = Adb @('push', (Join-Path $late $name), $staged)
        $null = Adb @('shell', 'run-as', $appId, 'cp', $staged, ('files/late/' + $name))
        $null = Adb @('shell', 'rm', $staged)
    }
    $withLate = Run-Harness 'post-install' $true
    if ($withLate.total -ne $baseline.total + 1) { throw 'Late map did not add exactly one integration case.' }
    $controlledEvidence = $null
    if ($ControlledPackages) {
        $controlledStartedUtc = [DateTime]::UtcNow
        if ($controlledStartedUtc -le $installedUtc) { throw 'Controlled source and IL production must start after APK installation.' }
        $payloads = Join-Path $evidence 'controlled-output'
        Invoke-Logged $operatorDotnet @("$operator/bin/Release/net11.0/operator.dll", $payloads, "$root/tests/RuneCLR.Packaging.Tests/bin/Release/net11.0/refs", "$app/RuneCLR.Abstractions.dll") "$evidence/controlled-build.log"
        foreach ($name in 'source', 'import', 'failure', 'tampered', 'forbidden') {
            $null = Adb @('shell', 'run-as', $appId, 'mkdir', '-p', ('files/controlled/' + $name))
            foreach ($file in Get-ChildItem -LiteralPath (Join-Path $payloads $name) -File) {
                $staged = '/data/local/tmp/runeclr-controlled-' + [Guid]::NewGuid().ToString('N')
                $null = Adb @('push', $file.FullName, $staged)
                $null = Adb @('shell', 'run-as', $appId, 'cp', $staged, ('files/controlled/' + $name + '/' + $file.Name))
                $null = Adb @('shell', 'rm', $staged)
                $deviceHash = Adb @('shell', 'run-as', $appId, 'sha256sum', ('files/controlled/' + $name + '/' + $file.Name))
                if (!$deviceHash.StartsWith((Get-FileHash $file.FullName).Hash, [StringComparison]::OrdinalIgnoreCase)) { throw 'Controlled payload device hash mismatch.' }
                $deviceHash | Add-Content "$evidence/controlled-device-hashes.txt"
            }
        }
        $controlledRun = Run-Harness 'controlled' $true
        if ($controlledRun.result.controlledPassed -ne 8 -or $controlledRun.total -ne $withLate.total) { throw 'Controlled Android acceptance did not pass all eight cases.' }
        $deviceLibraries = @{}
        foreach ($name in 'RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Abstractions.dll') {
            $deviceHash = Adb @('shell', 'run-as', $appId, 'sha256sum', ('files/' + $name))
            if (!$deviceHash.StartsWith((Get-FileHash (Join-Path $app $name)).Hash, [StringComparison]::OrdinalIgnoreCase)) { throw 'Controlled execution changed a host library.' }
            $deviceLibraries[$name] = $deviceHash
        }
        $controlledEvidence = [ordered]@{ productionStartedUtc = $controlledStartedUtc.ToString('o'); run = $controlledRun; payloads = (Hash-Tree $payloads); operatorSources = (Hash-Tree $operator); hostLibraryDeviceHashes = $deviceLibraries; playerCompilerAbsent = $true; scope = 'Versioned managed-il-gameplay-v1 packages; Android x64 stock RC1 CoreCLR permits JIT; no interpreter or physical-device proof' }
    }
    $deviceHost = Adb @('shell', 'run-as', $appId, 'sha256sum', 'files/RuneCLR.AndroidLifecycleHost.dll')
    $deviceHarness = Adb @('shell', 'run-as', $appId, 'sha256sum', 'files/RuneCLR.Runtime.Tests.dll')
    $deviceLate = Adb @('shell', 'run-as', $appId, 'sha256sum', 'files/late/RuneCLR.LateMap.dll')
    $devicePackagePath = (Adb @('shell', 'pm', 'path', $appId)) -replace '^package:', ''
    $deviceApk = Adb @('shell', 'sha256sum', $devicePackagePath)
    $lateHash = (Get-FileHash "$late/RuneCLR.LateMap.dll").Hash
    foreach ($pair in @(@($deviceHost, $hostHash), @($deviceHarness, $harnessHash), @($deviceLate, $lateHash), @($deviceApk, $apkHash))) {
        if (!$pair[0].StartsWith($pair[1], [StringComparison]::OrdinalIgnoreCase)) { throw 'Device-side SHA256 does not match local build.' }
    }
    [ordered]@{
        completedUtc = [DateTime]::UtcNow.ToString('o'); baseline = $baseline; postInstall = $withLate
        installedUtc = $installedUtc.ToString('o'); lateCompilationStartedUtc = $lateStartedUtc.ToString('o'); lateSha256 = $lateHash
        lateSources = (Hash-Tree $lateSource)
        controlledPackages = $controlledEvidence
        apkAndHostUnchanged = $true; deviceHashes = @{ host = $deviceHost; harness = $deviceHarness; late = $deviceLate; apk = $deviceApk }
        device = @{ kernelArchitecture = (Adb @('shell', 'uname', '-m')); api = (Adb @('shell', 'getprop', 'ro.build.version.sdk')); pageSize = (Adb @('shell', 'getconf', 'PAGESIZE')) }
        scope = $request.scope
    } | ConvertTo-Json -Depth 12 | Set-Content "$evidence/evidence.json"
    Write-Host ('Android lifecycle verified: ' + $baseline.passed + '/' + $baseline.total + '; post-install IL ' + $withLate.passed + '/' + $withLate.total)
    if ($ControlledPackages) { Write-Host 'Android controlled packages verified: 8/8; compiler absent from APK; source/import/source and failure/rejection recovery collected.' }
    Write-Host ('Evidence: ' + $evidence)
} finally {
    if ($startedEmulator) { & $adb -s $serial emu kill *> "$evidence/emulator-shutdown.log" }
    $env:PATH = $oldPath; $env:JAVA_HOME = $oldJava
    $env:ANDROID_SDK_ROOT = $oldSdk; $env:ANDROID_HOME = $oldAndroidHome; $env:ANDROID_AVD_HOME = $oldAvd
}
