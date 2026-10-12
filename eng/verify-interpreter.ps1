param(
    [Parameter(Mandatory)][string] $RuntimeRepo,
    [string] $RuntimeLayout,
    [ValidateSet(1, 2, 3)][int] $Mode = 1,
    [string] $EvidenceDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$expectedBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
if (!$RuntimeLayout) {
    $RuntimeLayout = Join-Path $RuntimeRepo 'artifacts/bin/testhost/net11.0-windows-Release-x64'
}
$RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
$framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'
$privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
if (!(Test-Path $privateDotnet)) { throw "Missing private host: $privateDotnet" }
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll', 'hostpolicy.dll') {
    if (!(Test-Path (Join-Path $framework $name))) { throw "Missing private runtime file: $name" }
}
$base = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $base -ne $expectedBase) {
    throw "This experiment requires runtime base $expectedBase; found $base."
}
if (& git -C $RuntimeRepo status --porcelain --untracked-files=no) {
    throw 'Runtime has tracked changes; record and validate a new experiment before using this launcher.'
}
$sourceStamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$sourceStamp.Contains($base)) {
    throw "Private CoreCLR is not stamped with the selected source commit: $sourceStamp"
}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll') {
    $builtFile = Join-Path $RuntimeRepo "artifacts/bin/coreclr/windows.x64.Checked/$name"
    if (!(Test-Path $builtFile) -or
        (Get-FileHash $builtFile).Hash -ne (Get-FileHash (Join-Path $framework $name)).Hash) {
        throw "Private layout does not match the Checked build output: $name"
    }
}
if (!$EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $repo ("artifacts/interpreter/{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N'))
}
if ((Test-Path $EvidenceDirectory) -and (Get-ChildItem $EvidenceDirectory -Force | Select-Object -First 1)) {
    throw 'EvidenceDirectory must be empty so failed runs cannot inherit old success evidence.'
}
New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path

function Invoke-Logged([string] $Program, [string[]] $Arguments, [string] $Log) {
    & $Program @Arguments > $Log 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE). See $Log" }
}

Push-Location $repo
try {
    Invoke-Logged 'dotnet' @('build', 'RuneCLR.slnx', '-c', 'Release') (Join-Path $EvidenceDirectory 'host-build.log')
    $hostDll = Join-Path $repo 'samples/RuneCLR.SampleHost/bin/Release/net11.0/RuneCLR.SampleHost.dll'
    $testsDll = Join-Path $repo 'tests/RuneCLR.Runtime.Tests/bin/Release/net11.0/RuneCLR.Runtime.Tests.dll'
    $hostFiles = @(Get-ChildItem (Split-Path $hostDll) -File) + @(Get-ChildItem (Split-Path $testsDll) -File)
    $before = @{}
    foreach ($file in $hostFiles) {
        $before[$file.FullName] = @{ hash = (Get-FileHash $file.FullName).Hash; ticks = $file.LastWriteTimeUtc.Ticks }
    }
    $lateBuildStarted = [DateTime]::UtcNow
    # Recompile IL after the host, without traversing its dependency project graph.
    Invoke-Logged 'dotnet' @('build', 'tests/RuneCLR.LateMap', '-c', 'Release', '-t:Rebuild',
        '-p:BuildProjectReferences=false') (Join-Path $EvidenceDirectory 'late-build.log')
    $lateDirectory = Join-Path $repo 'tests/RuneCLR.LateMap/bin/Release/net11.0'
    $lateDll = Get-Item (Join-Path $lateDirectory 'RuneCLR.LateMap.dll')
    if ($lateDll.LastWriteTimeUtc -lt $lateBuildStarted) { throw 'Late map was not recompiled after the host build.' }
    $lateManifest = Join-Path $lateDirectory 'map.json'
    foreach ($file in $hostFiles) {
        if ((Get-FileHash $file.FullName).Hash -ne $before[$file.FullName].hash -or
            (Get-Item $file.FullName).LastWriteTimeUtc.Ticks -ne $before[$file.FullName].ticks) {
            throw "Host file changed while compiling the late map: $($file.FullName)"
        }
    }

    $settings = @{
        DOTNET_InterpMode = "$Mode"
        DOTNET_Interpreter = $null
        DOTNET_InterpreterName = $null
        DOTNET_InterpreterPath = $null
        DOTNET_ReadyToRun = '0'
        DOTNET_TieredCompilation = '0'
        DOTNET_InterpList = '1'
        DOTNET_InterpDump = '*:OnStart *:OnTick *:OnStop *:Start *:Identity *:Read'
        DOTNET_JitDisasmSummary = '1'
        DOTNET_JitNoInline = '1'
        DOTNET_MULTILEVEL_LOOKUP = '0'
    }
    $saved = @{}
    [ordered]@{
        startedUtc = [DateTime]::UtcNow.ToString('o')
        runtimeBase = $base
        runtimeLayout = $RuntimeLayout
        runtimeSourceStamp = $sourceStamp
        hostBase = (& git rev-parse HEAD).Trim()
        settings = $settings
    } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
    try {
        foreach ($key in @($settings.Keys)) {
            $legacy = $key -replace '^DOTNET_', 'COMPlus_'
            $saved[$legacy] = [Environment]::GetEnvironmentVariable($legacy, 'Process')
            [Environment]::SetEnvironmentVariable($legacy, $null, 'Process')
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
        }
        $testsLog = Join-Path $EvidenceDirectory 'tests.log'
        $sampleLog = Join-Path $EvidenceDirectory 'sample.log'
        $lateLog = Join-Path $EvidenceDirectory 'late-sample.log'
        Invoke-Logged $privateDotnet @('exec', '--fx-version', '12.0.0', $testsDll, '--late-map', $lateManifest) $testsLog
        Invoke-Logged $privateDotnet @('exec', '--fx-version', '12.0.0', $hostDll, '--collect') $sampleLog
        Invoke-Logged $privateDotnet @('exec', '--fx-version', '12.0.0', $hostDll, '--collect', $lateManifest) $lateLog

        # Successful bytecode dumps, alongside callback results, establish more than switch acceptance.
        $testText = Get-Content $testsLog -Raw
        $sampleText = Get-Content $sampleLog -Raw
        foreach ($name in 'CounterMap', 'ThrowingMap', 'DependencyMap', 'GenericMap', 'LateMap') {
            if ($testText -notmatch ("Compiled method: [^\r\n]*{0}[^\r\n]*:OnStart" -f $name)) {
                throw "Missing successful interpreter bytecode dump for $name. See $testsLog"
            }
        }
        foreach ($name in 'HelloMap', 'ArenaMap') {
            if ($sampleText -notmatch ("Compiled method: [^\r\n]*{0}[^\r\n]*:OnTick" -f $name)) {
                throw "Missing successful interpreter bytecode dump for $name. See $sampleLog"
            }
        }
        foreach ($pattern in 'PrivateState[^\r\n]*:Start', 'GenericMap[^\r\n]*:Identity', 'GenericMap[^\r\n]*:Read') {
            if ($testText -notmatch ("Compiled method: [^\r\n]*" + $pattern)) {
                throw "Missing successful generic helper bytecode dump: $pattern. See $testsLog"
            }
        }
        if ($testText -notmatch '12/12 tests passed' -or
            ([regex]::Matches($sampleText, 'unload: collected')).Count -ne 3) {
            throw 'Lifecycle results are incomplete; inspect the saved logs.'
        }
        foreach ($log in $testsLog, $sampleLog, $lateLog) {
            if (Select-String -Path $log -Pattern 'JIT compiled.*(RuneCLR\.(TestMaps|DependencyMap|PrivateDependency|LateMap)|Maps\.(Hello|Arena))' -Quiet) {
                throw "Map JIT fallback detected in $log"
            }
        }
    }
    finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }

    $hashes = @{}
    $hashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash
    $hashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
    foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll', 'hostpolicy.dll') {
        $hashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
    }
    $evidence = [ordered]@{
        runtimeBase = $base
        runtimePatch = 'none'
        runtimeBranch = (& git -C $RuntimeRepo branch --show-current).Trim()
        runtimeConfiguration = 'windows.x64.Checked; libraries Release'
        runtimeLayout = $RuntimeLayout
        runtimeHashes = $hashes
        runtimeProductVersion = $sourceStamp
        runtimeBuildCommands = @(
            './build.cmd -subset clr+libs -configuration Checked -librariesConfiguration Release -arch x64'
        )
        hostBase = (& git rev-parse HEAD).Trim()
        hostWorkingTree = @(& git status --porcelain)
        os = [Environment]::OSVersion.ToString()
        architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        sdk = (& dotnet --version).Trim()
        settings = $settings
        lateMapBuiltUtc = $lateDll.LastWriteTimeUtc.ToString('o')
        hostFilesUnchanged = $true
        hostHash = (Get-FileHash $hostDll).Hash
        harnessHash = (Get-FileHash $testsDll).Hash
        lateMapHash = (Get-FileHash $lateDll.FullName).Hash
        lifecycle = '12/12 passed; sample 3/3 contexts collected; late sample collected'
    }
    $evidence | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'evidence.json')
    Write-Host "Interpreter lifecycle verified. Evidence: $EvidenceDirectory"
}
finally { Pop-Location }
