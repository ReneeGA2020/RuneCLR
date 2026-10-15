param(
    [Parameter(Mandatory)][string] $RuntimeRepo,
    [string] $CoreRoot,
    [string] $EvidenceDirectory,
    [string] $ProbeSourceDirectory,
    [switch] $ProbeOnly,
    [ValidateSet(0, 1)][int] $CachedDispatch = 0,
    [ValidateRange(2, 100)][int] $ProbeTicks = 2
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$expectedBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
$base = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $base -ne $expectedBase) { throw "Expected runtime base $expectedBase; found $base" }
if (& git -C $RuntimeRepo status --porcelain --untracked-files=no) { throw 'Runtime tracked source must be clean for the baseline experiment.' }
if (!$CoreRoot) { $CoreRoot = Join-Path $RuntimeRepo 'artifacts/tests/coreclr/windows.x64.Checked/Tests/Core_Root' }
$CoreRoot = (Resolve-Path $CoreRoot).Path
$identity = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll', 'corerun.exe') {
    $file = Join-Path $CoreRoot $name
    $product = Join-Path $RuntimeRepo "artifacts/bin/coreclr/windows.x64.Checked/$name"
    if (!(Test-Path $file) -or !(Test-Path $product)) { throw "Missing matching Checked artifact: $name" }
    $identity[$name] = (Get-FileHash $file -Algorithm SHA256).Hash
    if ($identity[$name] -ne (Get-FileHash $product -Algorithm SHA256).Hash) { throw "Core_Root differs from Checked product: $name" }
}
$stamp = (Get-Item (Join-Path $CoreRoot 'coreclr.dll')).VersionInfo.ProductVersion
if (!$stamp.Contains($base)) { throw "CoreCLR source stamp does not match the selected base: $stamp" }
if (!$EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $repo ("artifacts/cid-upstream/{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N'))
}
if (Test-Path $EvidenceDirectory) { throw 'EvidenceDirectory must be new; preserve earlier runs.' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
$output = Join-Path $EvidenceDirectory 'upstream'
$testBin = Join-Path $output 'windows.x64.Checked'
$common = @('-p:BuildAsStandalone=true', "-p:BaseOutputPath=$output", "-p:__TestBinDir=$testBin", '-p:CLRTestPriorityToBuild=1')
$tests = @(
    @{ name = 'GenericVirtualMethod'; folder = 'Loader/CollectibleAssemblies/GenericVirtualMethod'; project = 'GenericVirtualMethod' },
    @{ name = 'CollectibleStatics'; folder = 'Loader/CollectibleAssemblies/Statics'; project = 'CollectibleStatics' },
    @{ name = 'ResolvedFromDifferentContext'; folder = 'Loader/CollectibleAssemblies/ResolvedFromDifferentContext'; project = 'ResolvedFromDifferentContext' },
    @{ name = 'ByRefLocals'; folder = 'Loader/CollectibleAssemblies/ByRefLocals'; project = 'ByRefLocals' }
)
if ($ProbeOnly) {
    if (!$ProbeSourceDirectory) { throw 'ProbeOnly requires ProbeSourceDirectory.' }
    $tests = @()
}
$settings = [ordered]@{
    CORE_ROOT = $CoreRoot
    DOTNET_ReadyToRun = '0'
    DOTNET_TieredCompilation = '0'
    DOTNET_InterpMode = '0'
    DOTNET_InterpList = '1'
    DOTNET_InterpDump = 'DerivedMachine:* Machine:* *:TestEntryPoint StaticTest:*'
    DOTNET_Interpreter = $null
    DOTNET_InterpreterName = $null
    DOTNET_InterpreterPath = $null
    DOTNET_JitDisasmSummary = '1'
    DOTNET_JitNoInline = '1'
    DOTNET_GCStress = '0'
    DOTNET_UseCachedInterfaceDispatch = "$CachedDispatch"
}
$saved = @{}
$results = [Collections.Generic.List[object]]::new()
$request = [ordered]@{
    startedUtc = [DateTime]::UtcNow.ToString('o')
    runtimeBase = $base
    runtimeRepo = $RuntimeRepo
    coreRoot = $CoreRoot
    sourceStamp = $stamp
    runtimeHashes = $identity
    buildArguments = $common
    tests = $tests
    settings = $settings
    officialInstructions = 'docs/workflow/testing/coreclr/windows-test-instructions.md'
    probeSourceDirectory = $ProbeSourceDirectory
    probeTicks = $ProbeTicks
}
$request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $EvidenceDirectory 'driver.ps1')

function Get-ManagedLayout([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    $reader = [System.Reflection.PortableExecutable.PEReader]::new($stream)
    try {
        $header = $reader.PEHeaders.CorHeader
        if (!$header) { throw "Missing managed header: $Path" }
        return [ordered]@{
            ilOnly = [bool]($header.Flags -band [System.Reflection.PortableExecutable.CorFlags]::ILOnly)
            managedNativeRva = $header.ManagedNativeHeaderDirectory.RelativeVirtualAddress
            managedNativeSize = $header.ManagedNativeHeaderDirectory.Size
            sha256 = (Get-FileHash $Path -Algorithm SHA256).Hash
        }
    } finally { $reader.Dispose(); $stream.Dispose() }
}

function Invoke-Build([string[]] $Arguments, [string] $Log) {
    # Test diagnostics must not leak into the SDK or compiler processes.
    foreach ($key in $saved.Keys) {
        $value = if ($null -eq $saved[$key]) { [NullString]::Value } else { $saved[$key] }
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
    & (Join-Path $RuntimeRepo 'dotnet.cmd') @Arguments > $Log 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Official test build failed ($LASTEXITCODE); see $Log" }
}

Push-Location $RuntimeRepo
try {
    foreach ($key in $settings.Keys) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        if ($key.StartsWith('DOTNET_')) {
            $legacy = $key -replace '^DOTNET_', 'COMPlus_'
            $saved[$legacy] = [Environment]::GetEnvironmentVariable($legacy, 'Process')
            [Environment]::SetEnvironmentVariable($legacy, [NullString]::Value, 'Process')
        }
    }
    # The upstream targets share dependency assets outside individual restores.
    if ($tests.Count -gt 0) {
        Invoke-Build (@('restore', 'src/tests/Common/test_dependencies/test_dependencies.csproj') + $common) (Join-Path $EvidenceDirectory 'restore-dependencies.log')
    }
    foreach ($test in $tests) {
        $project = "src/tests/$($test.folder)/$($test.project).csproj"
        Invoke-Build (@('build', $project, '-c', 'Checked') + $common) (Join-Path $EvidenceDirectory "$($test.name)-build.log")
        $folder = Join-Path $testBin "$($test.folder)/$($test.project)"
        $wrapper = Join-Path $folder "$($test.project).cmd"
        $assembly = Join-Path $folder "$($test.project).dll"
        if (!(Test-Path $wrapper) -or !(Test-Path $assembly)) { throw "Missing generated upstream runner: $wrapper" }
        foreach ($mode in 0, 1) {
            foreach ($key in $settings.Keys) {
                $value = if ($null -eq $settings[$key]) { [NullString]::Value } else { $settings[$key] }
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
            [Environment]::SetEnvironmentVariable('DOTNET_InterpMode', "$mode", 'Process')
            $log = Join-Path $EvidenceDirectory "$($test.name)-mode$mode.log"
            & $wrapper > $log 2>&1
            $exit = $LASTEXITCODE
            $text = Get-Content $log -Raw
            $dumps = ([regex]::Matches($text, 'Compiled method:')).Count
            $pass = $exit -eq 0 -and $text.Contains('Expected: 100') -and $text.Contains('Actual: 100') -and $text.Contains('END EXECUTION - PASSED')
            if ($mode -eq 1) { $pass = $pass -and $dumps -gt 0 }
            $results.Add([ordered]@{
                test = $test.name; mode = $mode; cachedDispatch = $CachedDispatch; exitCode = $exit; passed = $pass; successfulInterpreterDumps = $dumps
                generatedRunner = $wrapper; runnerSha256 = (Get-FileHash $wrapper -Algorithm SHA256).Hash
                assemblySha256 = (Get-FileHash $assembly -Algorithm SHA256).Hash; log = $log
            })
            [ordered]@{ completedUtc = [DateTime]::UtcNow.ToString('o'); runs = $results.ToArray() } |
                ConvertTo-Json -Depth 6 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
            if (!$pass) { throw "Upstream test failed or lacked execution evidence: $($test.name), mode $mode. See $log" }
            Write-Output "PASS $($test.name) mode=${mode}: official runner Expected/Actual=100; successful interpreter dumps=$dumps"
        }
    }
    if ($ProbeSourceDirectory) {
        $source = (Resolve-Path $ProbeSourceDirectory).Path
        $probe = Join-Path $EvidenceDirectory 'probe'
        $inputDirectory = Join-Path $probe 'input'
        $sourceCopy = Join-Path $probe 'source'
        New-Item -ItemType Directory -Path $inputDirectory, $sourceCopy | Out-Null
        $hostSource = Get-Content (Join-Path $source 'ProbeHost.cs') -Raw
        $beforeMarker = if ($hostSource.Contains('TICK_BEFORE index=')) { 'TICK_BEFORE index=' } else { 'CALL_TICK index=' }
        $afterMarker = if ($hostSource.Contains('TICK_AFTER index=')) { 'TICK_AFTER index=' } else { 'CALL_TICK_RETURNED index=' }
        $sdk = Join-Path $RuntimeRepo '.dotnet/dotnet.exe'
        foreach ($key in $saved.Keys) {
            $value = if ($null -eq $saved[$key]) { [NullString]::Value } else { $saved[$key] }
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
        $version = (& $sdk --version).Trim()
        $csc = Join-Path $RuntimeRepo ".dotnet/sdk/$version/Roslyn/bincore/csc.dll"
        $refs = @((@(Get-ChildItem $CoreRoot -Filter 'System.*.dll') + @(Get-Item (Join-Path $CoreRoot 'Microsoft.CSharp.dll'))) |
            Where-Object {
                try { [Reflection.AssemblyName]::GetAssemblyName($_.FullName) | Out-Null; $true }
                catch [BadImageFormatException] { $false }
            })
        $references = @($refs | ForEach-Object { '-r:' + $_.FullName })
        foreach ($name in 'ProbeContract', 'ProbePlugin', 'ProbeHost', 'ProbeEntry') {
            $original = Join-Path $source "$name.cs"
            $copy = Join-Path $sourceCopy "$name.cs"
            Copy-Item -LiteralPath $original -Destination $copy
            $target = if ($name -eq 'ProbeEntry') { 'exe' } else { 'library' }
            [string[]] $extra = if ($name -in 'ProbePlugin', 'ProbeHost') { @('-r:' + (Join-Path $inputDirectory 'ProbeContract.dll')) }
                elseif ($name -eq 'ProbeEntry') { @('-r:' + (Join-Path $inputDirectory 'ProbeHost.dll')) } else { @() }
            & $sdk $csc -nologo -noconfig -nostdlib+ -optimize+ "-target:$target" "-out:$inputDirectory/$name.dll" @references @extra $copy > (Join-Path $probe "$name-compile.log") 2>&1
            if ($LASTEXITCODE -ne 0) { throw "Probe compilation failed: $name" }
        }
        $crossgen = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Checked/crossgen2/crossgen2.dll'
        $privateCorerun = Join-Path $CoreRoot 'corerun.exe'
        $crossgenHash = (Get-FileHash $crossgen -Algorithm SHA256).Hash
        foreach ($variant in 'r2r', 'il') {
            $lane = Join-Path $probe $variant
            New-Item -ItemType Directory -Path (Join-Path $lane 'plugin') | Out-Null
            Copy-Item (Join-Path $inputDirectory 'ProbePlugin.dll') (Join-Path $lane 'plugin/ProbePlugin.dll')
            $inputs = @('ProbeContract', 'ProbeEntry')
            if ($variant -eq 'r2r') { $inputs += 'ProbeHost' } else { Copy-Item (Join-Path $inputDirectory 'ProbeHost.dll') $lane }
            $arguments = @($crossgen, '--targetos:windows', '--targetarch:x64', '--composite', '--inputbubble', '--resilient', '--optimize', '--parallelism:2', "--out:$lane/probe.dll") +
                $references + @('-r:' + (Join-Path $inputDirectory 'ProbeHost.dll')) + @($inputs | ForEach-Object { Join-Path $inputDirectory "$_.dll" })
            & $sdk @arguments > (Join-Path $lane 'crossgen.log') 2>&1
            if ($LASTEXITCODE -ne 0) { throw "Probe crossgen failed: $variant" }
            $layout = [ordered]@{
                host = Get-ManagedLayout (Join-Path $lane 'ProbeHost.dll')
                plugin = Get-ManagedLayout (Join-Path $lane 'plugin/ProbePlugin.dll')
            }
            if (!$layout.plugin.ilOnly -or $layout.plugin.managedNativeRva -ne 0 -or
                $layout.plugin.sha256 -ne (Get-FileHash (Join-Path $inputDirectory 'ProbePlugin.dll') -Algorithm SHA256).Hash) {
                throw 'Plugin must remain unchanged IL outside the host composite.'
            }
            if ($variant -eq 'r2r' -and $layout.host.managedNativeRva -eq 0) { throw 'R2R host has no managed native header.' }
            if ($variant -eq 'il' -and (!$layout.host.ilOnly -or $layout.host.managedNativeRva -ne 0 -or
                $layout.host.sha256 -ne (Get-FileHash (Join-Path $inputDirectory 'ProbeHost.dll') -Algorithm SHA256).Hash)) {
                throw 'IL host must retain original input bytes.'
            }
            $sourceHashes = [ordered]@{}
            foreach ($file in Get-ChildItem $sourceCopy -Filter '*.cs') { $sourceHashes[$file.Name] = (Get-FileHash $file.FullName -Algorithm SHA256).Hash }
            [ordered]@{ sourceSdk = $version; sourceHashes = $sourceHashes; layouts = $layout; probeTicks = $ProbeTicks;
                crossgenSha256 = $crossgenHash; arguments = $arguments } |
                ConvertTo-Json -Depth 8 | Set-Content (Join-Path $lane 'identity.json')
            foreach ($dispatch in 0, 1) {
                foreach ($key in $settings.Keys) {
                    $value = if ($null -eq $settings[$key]) { [NullString]::Value } else { $settings[$key] }
                    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
                }
                $extraSettings = @{ DOTNET_InterpMode = '1'; DOTNET_ReadyToRun = '1'; DOTNET_UseCachedInterfaceDispatch = "$dispatch";
                    DOTNET_InterpDump = 'Plugin:* Driver:CallSite'; DOTNET_ReadyToRunLogFile = (Join-Path $lane "dispatch$dispatch-r2r.log");
                    PROBE_MODE = 'collect'; PROBE_CYCLES = '20'; PROBE_TICKS = "$ProbeTicks" }
                foreach ($key in $extraSettings.Keys) {
                    if (!$saved.ContainsKey($key)) { $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
                    if ($key.StartsWith('DOTNET_')) {
                        $legacy = $key -replace '^DOTNET_', 'COMPlus_'
                        if (!$saved.ContainsKey($legacy)) { $saved[$legacy] = [Environment]::GetEnvironmentVariable($legacy, 'Process') }
                        [Environment]::SetEnvironmentVariable($legacy, [NullString]::Value, 'Process')
                    }
                    [Environment]::SetEnvironmentVariable($key, $extraSettings[$key], 'Process')
                }
                $log = Join-Path $lane "dispatch$dispatch.log"
                & $privateCorerun (Join-Path $lane 'ProbeEntry.dll') > $log 2>&1
                $exit = $LASTEXITCODE
                $text = Get-Content $log -Raw
                $tickResults = @(for ($index = 0; $index -lt $ProbeTicks; $index++) {
                    $expected = "PLUGIN_TICK counter=$($index + 1) index=$index ticks=160000"
                    [ordered]@{
                        index = $index
                        before = ([regex]::Matches($text, [regex]::Escape($beforeMarker + $index) + '(?![0-9])')).Count
                        after = ([regex]::Matches($text, [regex]::Escape($afterMarker + $index) + '(?![0-9])')).Count
                        plugin = ([regex]::Matches($text, [regex]::Escape($expected))).Count
                    }
                })
                $ticks = $tickResults[-1].plugin
                $collections = ([regex]::Matches($text, 'CYCLE=[0-9]+ COLLECTED=True')).Count
                $dumps = ([regex]::Matches($text, 'Compiled method: .Plugin:Tick')).Count
                $native = !$text.Contains('Interpreter compile method Driver:CallSite') -and !$text.Contains('JIT compiled Driver:CallSite')
                $hostDumps = ([regex]::Matches($text, 'Compiled method: .Driver:CallSite')).Count
                $pass = $exit -eq 0 -and $text.Contains('PROBE_PASS cycles=20') -and $ticks -eq 20 -and $dumps -eq 20 -and $collections -eq 20
                foreach ($tick in $tickResults) { $pass = $pass -and $tick.before -eq 20 -and $tick.after -eq 20 -and $tick.plugin -eq 20 }
                if ($variant -eq 'r2r') { $pass = $pass -and $native }
                else { $pass = $pass -and $hostDumps -gt 0 }
                $testName = if ($ProbeTicks -eq 2) { 'twoTick' } else { "${ProbeTicks}Tick" }
                $results.Add([ordered]@{ test = $testName; variant = $variant; cachedDispatch = $dispatch; passed = $pass; exitCode = $exit;
                    probeTicks = $ProbeTicks; tickResults = $tickResults; lastTickCount = $ticks; secondTickCount = $tickResults[1].plugin; collections = $collections;
                    interpretedPluginTickDumps = $dumps; hostCallsiteNative = $native; hostCallsiteDumps = $hostDumps; settings = $extraSettings;
                    crossgenSha256 = $crossgenHash; log = $log })
                [ordered]@{ completedUtc = [DateTime]::UtcNow.ToString('o'); runs = $results.ToArray() } |
                    ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
                if (!$pass) { throw "Probe failed: $variant cached dispatch $dispatch. See $log" }
                Write-Output "PASS $testName variant=$variant cachedDispatch=$dispatch; lastTickCount=$ticks; interpretedPluginTickDumps=$dumps; collections=$collections"
            }
            foreach ($key in $saved.Keys) {
                $value = if ($null -eq $saved[$key]) { [NullString]::Value } else { $saved[$key] }
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
    foreach ($name in $identity.Keys) {
        if ($identity[$name] -ne (Get-FileHash (Join-Path $CoreRoot $name) -Algorithm SHA256).Hash) { throw "Core_Root changed during tests: $name" }
    }
    Write-Output "PASS $($results.Count)/$($results.Count) Checked-runtime runs; unchanged Core_Root. Evidence: $EvidenceDirectory"
} finally {
    foreach ($key in $saved.Keys) {
        $value = if ($null -eq $saved[$key]) { [NullString]::Value } else { $saved[$key] }
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
    Pop-Location
}
