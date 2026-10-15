param(
    [Parameter(Mandatory)][string] $RuntimeRepo,
    [string] $RuntimeLayout,
    [ValidateSet(0, 1, 2, 3)][int] $Mode = 1,
    [string] $RequiredCandidateCommit,
    [switch] $SessionPolicy,
    [string] $EvidenceDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$expectedBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
$required = ![string]::IsNullOrEmpty($RequiredCandidateCommit)
if ($SessionPolicy -and !$required) { throw 'SessionPolicy requires an explicitly identified matching runtime candidate.' }
if ($required) {
    if ($Mode -ne 0 -or !$RuntimeLayout) { throw 'Required candidate needs Mode 0 and an explicit matching RuntimeLayout.' }
    $expectedBase = $RequiredCandidateCommit
} elseif ($Mode -eq 0) { throw 'Mode 0 needs an explicitly identified required-interpreter candidate.' }
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
if ($required) {
    & git -C $RuntimeRepo merge-base --is-ancestor '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de' $base
    if ($LASTEXITCODE -ne 0) { throw 'Required candidate is not descended from the pinned source base.' }
}
$sourceStamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$sourceStamp.Contains($base)) {
    throw "Private CoreCLR is not stamped with the selected source commit: $sourceStamp"
}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
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
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $EvidenceDirectory 'driver.ps1')

function Invoke-Logged([string] $Program, [string[]] $Arguments, [string] $Log) {
    if ($required -and $Program -eq $privateDotnet) {
        [Environment]::SetEnvironmentVariable('DOTNET_JitStdOutFile', $Log + '.jit', 'Process')
    }
    & $Program @Arguments > $Log 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE). See $Log" }
}

Push-Location $repo
try {
    Invoke-Logged 'dotnet' @('build', 'RuneCLR.slnx', '-c', 'Release') (Join-Path $EvidenceDirectory 'host-build.log')
    $hostDll = Join-Path $repo 'samples/RuneCLR.SampleHost/bin/Release/net11.0/RuneCLR.SampleHost.dll'
    $testsDll = Join-Path $repo 'tests/RuneCLR.Runtime.Tests/bin/Release/net11.0/RuneCLR.Runtime.Tests.dll'
    $playerDll = Join-Path $repo 'tests/RuneCLR.PackageExecution.Tests/bin/Release/net11.0/RuneCLR.PackageExecution.Tests.dll'
    $hostFiles = @(Get-ChildItem (Split-Path $hostDll) -File) + @(Get-ChildItem (Split-Path $testsDll) -File) +
        @(Get-ChildItem (Split-Path $playerDll) -File)
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
    # Operator tooling runs on the selected SDK runtime; only its generated IL
    # packages enter the private interpreter host. Roslyn stays out of the player.
    $packageTool = Join-Path $repo 'tools/RuneCLR.PackageTool/bin/Release/net11.0/RuneCLR.PackageTool.dll'
    $approvedReferences = Join-Path $repo 'tests/RuneCLR.Packaging.Tests/bin/Release/net11.0/refs'
    $approvedContract = Join-Path $repo 'src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll'
    $packageDirectory = Join-Path $EvidenceDirectory 'controlled-source'
    Invoke-Logged 'dotnet' @($packageTool, 'compile', '--source', (Join-Path $repo 'samples/Source'),
        '--id', 'ControlledGameplay', '--entry-type', 'Gameplay', '--framework-refs', $approvedReferences,
        '--contract', $approvedContract, '--output', $packageDirectory) (Join-Path $EvidenceDirectory 'package-build.log')
    $controlledManifest = Join-Path $packageDirectory 'package.json'
    Invoke-Logged 'dotnet' @($packageTool, 'validate', '--manifest', $controlledManifest) (Join-Path $EvidenceDirectory 'package-validate.log')
    $importDirectory = Join-Path $EvidenceDirectory 'controlled-import'
    Invoke-Logged 'dotnet' @($packageTool, 'import', '--assembly', (Join-Path $packageDirectory 'ControlledGameplay.dll'),
        '--id', 'ControlledImported', '--entry-type', 'Gameplay', '--framework-refs', $approvedReferences,
        '--contract', $approvedContract, '--output', $importDirectory) (Join-Path $EvidenceDirectory 'package-import.log')
    $importedManifest = Join-Path $importDirectory 'package.json'
    $fixtureDirectory = Join-Path $EvidenceDirectory 'package-fixtures'
    $fixtureTool = Join-Path $repo 'tools/RuneCLR.PackageFixtures/bin/Release/net11.0/RuneCLR.PackageFixtures.dll'
    Invoke-Logged 'dotnet' @($fixtureTool, '--framework-refs', $approvedReferences, '--contract', $approvedContract,
        '--output', $fixtureDirectory) (Join-Path $EvidenceDirectory 'fixture-build.log')
    foreach ($file in $hostFiles) {
        if ((Get-FileHash $file.FullName).Hash -ne $before[$file.FullName].hash -or
            (Get-Item $file.FullName).LastWriteTimeUtc.Ticks -ne $before[$file.FullName].ticks) {
            throw "Host file changed while compiling the late map: $($file.FullName)"
        }
    }

    $settings = @{
        DOTNET_InterpMode = "$Mode"
        DOTNET_RuneCLRInterpretCollectible = $(if ($required -and !$SessionPolicy) { '1' } else { '0' })
        DOTNET_RuneCLRInterpreterRefuseMethods = $null
        DOTNET_Interpreter = $null
        DOTNET_InterpreterName = $null
        DOTNET_InterpreterPath = $null
        DOTNET_ReadyToRun = '0'
        DOTNET_TieredCompilation = '0'
        DOTNET_InterpList = '1'
        DOTNET_InterpDump = '*:OnStart *:OnTick *:OnStop *:Start *:Identity *:Read *:Next'
        DOTNET_JitDisasmSummary = '1'
        DOTNET_JitStdOutFile = $null
        DOTNET_JitNoInline = '1'
        DOTNET_MULTILEVEL_LOOKUP = '0'
    }
    if ($required) {
        $settings.DOTNET_ReadyToRun = '1'
        $settings.DOTNET_TieredCompilation = '1'
        $settings.DOTNET_JitNoInline = '0'
    }
    $saved = @{}
    [ordered]@{
        startedUtc = [DateTime]::UtcNow.ToString('o')
        runtimeBase = $base
        upstreamBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
        runtimeLayout = $RuntimeLayout
        runtimeSourceStamp = $sourceStamp
        sessionPolicy = [bool]$SessionPolicy
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
        $controlledLog = Join-Path $EvidenceDirectory 'controlled-sample.log'
        $playerLog = Join-Path $EvidenceDirectory 'package-execution.log'
        $policyArgs = @()
        if ($SessionPolicy) { $policyArgs = @('--require-interpreter') }
        Invoke-Logged $privateDotnet (@('exec', '--fx-version', '12.0.0', $testsDll, '--late-map', $lateManifest) + $policyArgs) $testsLog
        Invoke-Logged $privateDotnet (@('exec', '--fx-version', '12.0.0', $hostDll, '--collect') + $policyArgs) $sampleLog
        Invoke-Logged $privateDotnet (@('exec', '--fx-version', '12.0.0', $hostDll, '--collect', $lateManifest) + $policyArgs) $lateLog
        Invoke-Logged $privateDotnet (@('exec', '--fx-version', '12.0.0', $hostDll, '--collect',
            $controlledManifest, $importedManifest, $controlledManifest) + $policyArgs) $controlledLog
        Invoke-Logged $privateDotnet (@('exec', '--fx-version', '12.0.0', $playerDll, '--packages', $fixtureDirectory) + $policyArgs) $playerLog

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
        if ($testText -notmatch '24/24 tests passed' -or
            ([regex]::Matches($sampleText, 'unload: collected')).Count -ne 3) {
            throw 'Lifecycle results are incomplete; inspect the saved logs.'
        }
        $controlledText = Get-Content $controlledLog -Raw
        foreach ($callback in 'OnStart', 'OnTick', 'OnStop') {
            if ($controlledText -notmatch ("Compiled method: [^\r\n]*Gameplay[^\r\n]*:{0}" -f $callback)) {
                throw "Missing controlled-package interpreter dump for $callback. See $controlledLog"
            }
        }
        if (([regex]::Matches($controlledText, 'unload: collected')).Count -ne 3 -or
            ([regex]::Matches($controlledText, 'starts=1')).Count -ne 3) {
            throw 'Controlled source/import/source sessions did not reset static state and collect.'
        }
        $playerText = Get-Content $playerLog -Raw
        if ($SessionPolicy) {
            foreach ($policyLog in $testsLog, $sampleLog, $lateLog, $controlledLog, $playerLog) {
                if ((Get-Content $policyLog -Raw) -notmatch 'SESSION_EXECUTION_POLICY required-interpreter version=1') {
                    throw "Missing native policy acknowledgement in $policyLog"
                }
            }
        }
        if ($playerText -notmatch '15/15 package execution tests passed') {
            throw 'Player package execution results are incomplete.'
        }
        foreach ($pattern in 'GameScript[^\r\n]*:OnStart', 'GameScript[^\r\n]*:OnTick',
            'GameScript[^\r\n]*:OnStop', 'SharedHelper[^\r\n]*:Read', 'GenericCounter[^\r\n]*:Next') {
            if ($playerText -notmatch ('Compiled method: [^\r\n]*' + $pattern)) {
                throw "Missing player package interpreter dump: $pattern. See $playerLog"
            }
        }
        foreach ($log in $testsLog, $sampleLog, $lateLog, $controlledLog, $playerLog) {
            $nativeLog = $(if ($required) { $log + '.jit' } else { $log })
            $mapEvents = @(Select-String -Path $nativeLog -Pattern 'JIT compiled.*(RuneCLR\.(TestMaps|DependencyMap|PrivateDependency|LateMap)|Maps\.(Hello|Arena)|ControlledGameplay|GameScript|SharedHelper|GenericCounter)')
            if ($required -and $log -eq $testsLog) {
                # This existing test deliberately seeds the same dependency in
                # the trusted default ALC, before testing private isolation.
                $seedPattern = 'JIT compiled RuneCLR.PrivateDependency.PrivateState`1\[int\]:Start\(int\):System.String '
                $seedEvents = @($mapEvents | Where-Object { $_.Line -match $seedPattern })
                if ($seedEvents.Count -ne 1 -or $testText -notmatch 'DEFAULT_DEPENDENCY_SEED collectible=false module=[0-9a-f-]+ token=0x[0-9a-f]+') {
                    throw 'Default-context collision control lacks its single native seed and explicit ownership marker.'
                }
                $mapEvents = @($mapEvents | Where-Object { $_.Line -notmatch $seedPattern })
            }
            if ($mapEvents.Count -ne 0) {
                throw "Map JIT fallback detected in $log"
            }
        }
        if ($required -and (Get-Content ($testsLog + '.jit') -Raw) -notmatch 'JIT compiled[^\r\n]*RuneCLR.Runtime.MapRunner:') {
            throw 'Required lane has no positive native compilation evidence for the trusted MapRunner.'
        }
    }
    finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }

    $hashes = @{}
    $hashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash
    $hashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
    foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll', 'hostpolicy.dll') {
        $hashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
    }
    $evidence = [ordered]@{
        runtimeBase = $base
        upstreamBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
        runtimePatch = $(if ($required) { $RequiredCandidateCommit } else { 'none' })
        runtimeBranch = (& git -C $RuntimeRepo branch --show-current).Trim()
        runtimeConfiguration = 'windows.x64.Checked; libraries Release'
        runtimeLayout = $RuntimeLayout
        runtimeHashes = $hashes
        runtimeProductVersion = $sourceStamp
        runtimeBuildCommands = @($(if ($required) {
            './build.cmd -subset clr.runtime+clr.jit+clr.hosts+clr.corelib+clr.tools+clr.nativecorelib -configuration Checked -arch x64 -clrinterpreter; unchanged same-base Release framework libraries'
        } else { './build.cmd -subset clr+libs -configuration Checked -librariesConfiguration Release -arch x64' }))
        hostBase = (& git rev-parse HEAD).Trim()
        hostWorkingTree = @(& git status --porcelain)
        os = [Environment]::OSVersion.ToString()
        architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        sdk = (& dotnet --version).Trim()
        settings = $settings
        sessionPolicy = [bool]$SessionPolicy
        nativeDiagnosticStreams = $(if ($required) { 'Each private process uses its own <log>.jit; interpreter/result log stays separate.' } else { 'Original merged stream' })
        defaultContextControl = $(if ($required) { 'One native PrivateState<int>.Start seed, explicit non-collectible default ownership marker; collectible copies have successful bytecode and independent static reset. Names alone do not provide per-MethodDesc native-entry attribution.' } else { 'Mode selection applies to the original default collision control as before.' })
        lateMapBuiltUtc = $lateDll.LastWriteTimeUtc.ToString('o')
        hostFilesUnchanged = $true
        hostHash = (Get-FileHash $hostDll).Hash
        harnessHash = (Get-FileHash $testsDll).Hash
        lateMapHash = (Get-FileHash $lateDll.FullName).Hash
        controlledSourceManifest = Get-Content $controlledManifest -Raw | ConvertFrom-Json
        controlledImportManifest = Get-Content $importedManifest -Raw | ConvertFrom-Json
        controlledLifecycle = 'source/import/source 3/3 collected, starts=1 each; direct callback interpreter dumps'
        playerHarnessHash = (Get-FileHash $playerDll).Hash
        packageFixtures = Get-Content (Join-Path $fixtureDirectory 'fixtures.json') -Raw | ConvertFrom-Json
        playerPackageExecution = '15/15 passed; private version/generic reset, failure cleanup, invalid entry/dependency rejection, recovery and collection; direct callback/helper interpreter dumps'
        lifecycle = '24/24 passed; sample 3/3 contexts collected; late sample collected'
    }
    $evidence | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'evidence.json')
    Write-Host "Interpreter lifecycle verified. Evidence: $EvidenceDirectory"
}
finally { Pop-Location }
