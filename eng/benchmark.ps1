param(
    [Parameter(Mandatory)][string]$RuntimeRepo,
    [string]$FrameworkLayout,
    [ValidateRange(3, 30)][int]$Samples = 7,
    [ValidateRange(1, 10)][int]$Rounds = 3
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
if ((git -C $RuntimeRepo rev-parse HEAD) -ne $base) { throw 'Benchmark proof is specific to the pinned runtime base.' }
if (git -C $RuntimeRepo status --porcelain --untracked-files=no) { throw 'Runtime has tracked changes; record a new experiment before using this benchmark.' }
if (![Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows) -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'The execution probe and Lua build currently require Windows x64.' }
$native = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Release'
$cache = Join-Path $RuntimeRepo 'artifacts/obj/coreclr/windows.x64.Release/CMakeCache.txt'
if (!(Select-String -Path $cache -Pattern '^CMAKE_BUILD_TYPE:STRING=Release$') -or
    !(Select-String -Path $cache -Pattern '^FEATURE_INTERPRETER:[^=]+=1$')) { throw 'Build Release CoreCLR with /p:FeatureInterpreter=true first.' }
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    if (!(Test-Path (Join-Path $native $name))) { throw ('Missing Release runtime file: ' + $name) }
}
$stamp = (Get-Item (Join-Path $native 'coreclr.dll')).VersionInfo.ProductVersion
if ($stamp -notlike ('*' + $base + '*')) { throw 'Release native product stamp does not match source base.' }
if (!$FrameworkLayout) { $FrameworkLayout = Join-Path $RuntimeRepo 'artifacts/bin/testhost/net11.0-windows-Release-x64' }
$FrameworkLayout = (Resolve-Path $FrameworkLayout).Path
$scratch = Join-Path $root 'artifacts/performance'
$toolsDir = Join-Path $scratch 'tools'
New-Item -ItemType Directory -Force $toolsDir | Out-Null
$evidence = Join-Path $scratch ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $evidence | Out-Null

function Invoke-Logged([string]$File, [string[]]$Arguments, [string]$Log) {
    & $File @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) { throw ('Command failed (' + $LASTEXITCODE + '): ' + $File + '. Log: ' + $Log) }
}

# Build official Lua in private scratch space; do not install or change PATH.
$luaVersion = '5.4.9'
$luaSha = '2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6'
$archive = Join-Path $toolsDir ('lua-' + $luaVersion + '.tar.gz')
if (!(Test-Path $archive)) { Invoke-WebRequest ('https://www.lua.org/ftp/lua-' + $luaVersion + '.tar.gz') -OutFile $archive }
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $luaSha) { throw 'Lua source archive checksum mismatch.' }
Invoke-Logged 'tar' @('-xzf', $archive, '-C', $toolsDir) (Join-Path $evidence 'lua-extract.log')
$luaSource = Join-Path $toolsDir ('lua-' + $luaVersion + '/src')
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw 'Visual Studio x64 C compiler not found.' }
$sources = @(Get-ChildItem $luaSource -Filter '*.c' | Where-Object { $_.Name -notin 'lua.c', 'luac.c' } | ForEach-Object { '"' + $_.FullName + '"' })
$luaExe = Join-Path $toolsDir 'lua54-bench.exe'
$buildCmd = Join-Path $toolsDir 'build-lua.cmd'
$command = @('@echo off', ('call "' + (Join-Path $vs 'Common7/Tools/VsDevCmd.bat') + '" -arch=x64 -host_arch=x64'),
    'if errorlevel 1 exit /b %errorlevel%',
    ('cl /nologo /O2 /DNDEBUG /MD /DLUA_USE_WINDOWS /I"' + $luaSource + '" /Fe:"' + $luaExe + '" ' +
    ($sources -join ' ') + ' "' + (Join-Path $root 'benchmarks/scripts/lua-runner.c') + '"'), 'exit /b %errorlevel%')
$command | Set-Content $buildCmd -Encoding ascii
Push-Location $toolsDir
try { Invoke-Logged $buildCmd @() (Join-Path $evidence 'lua-build.log') } finally { Pop-Location }
Invoke-Logged 'dotnet' @('build', (Join-Path $root 'benchmarks/RuneCLR.PerformanceHost'), '-c', 'Release') (Join-Path $evidence 'host-build.log')

# Copy matching framework libraries into a new private layout, replacing only that
# copy's runtime with Release outputs. The issue #1 Checked layout is preserved.
$layout = Join-Path $evidence 'runtime'
Copy-Item $FrameworkLayout $layout -Recurse
$framework = Join-Path $layout 'shared/Microsoft.NETCore.App/12.0.0'
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll', 'mscordaccore.dll', 'mscordbi.dll') {
    Copy-Item (Join-Path $native $name) (Join-Path $framework $name) -Force
}
$privateDotnet = Join-Path $layout 'dotnet.exe'
$benchmarkDll = Join-Path $root 'benchmarks/RuneCLR.PerformanceHost/bin/Release/net11.0/RuneCLR.PerformanceHost.dll'
$benchmarkBinaryHashes = @{}
foreach ($name in 'RuneCLR.PerformanceHost.dll', 'RuneCLR.Performance.Kernels.dll') {
    $benchmarkBinaryHashes[$name] = (Get-FileHash (Join-Path (Split-Path $benchmarkDll -Parent) $name) -Algorithm SHA256).Hash
}
$buildInputHashes = @{}
foreach ($path in 'Directory.Build.props', 'global.json', 'eng/benchmark.ps1', 'eng/write-benchmark-report.ps1') {
    $buildInputHashes[$path] = (Get-FileHash (Join-Path $root $path) -Algorithm SHA256).Hash
}
$sourcesHashes = @{}
Get-ChildItem (Join-Path $root 'benchmarks') -File -Recurse | Where-Object { $_.FullName -notmatch '[\/](bin|obj)[\/]' } |
    ForEach-Object { $sourcesHashes[$_.FullName.Substring($root.Length + 1)] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
$node = (Get-Command node).Source
$engineDefinitions = @(
    @{ Name = 'coreclr-interpreter'; File = $privateDotnet; Args = @('exec', '--fx-version', '12.0.0', $benchmarkDll, "$Samples"); Interp = $true },
    @{ Name = 'coreclr-jit'; File = $privateDotnet; Args = @('exec', '--fx-version', '12.0.0', $benchmarkDll, "$Samples"); Interp = $false },
    @{ Name = 'lua-5.4'; File = $luaExe; Args = @((Join-Path $root 'benchmarks/scripts/workloads.lua'), "$Samples") },
    @{ Name = 'javascript-jit'; File = $node; Args = @((Join-Path $root 'benchmarks/scripts/workloads.js'), "$Samples") },
    @{ Name = 'javascript-jitless'; File = $node; Args = @('--jitless', (Join-Path $root 'benchmarks/scripts/workloads.js'), "$Samples") }
)
$saved = @{}
$settings = @('InterpMode', 'Interpreter', 'InterpreterName', 'InterpreterPath', 'ReadyToRun', 'TieredCompilation',
    'InterpPGO', 'InterpList', 'InterpDump', 'JitDisasm', 'JitDisasmSummary', 'JitDump', 'JitNoInline',
    'JitStress', 'GCStress', 'EnableHWIntrinsic', 'MULTILEVEL_LOOKUP')
foreach ($prefix in 'DOTNET_', 'COMPlus_') { foreach ($key in $settings) {
    $envKey = $prefix + $key; $saved[$envKey] = [Environment]::GetEnvironmentVariable($envKey);
    [Environment]::SetEnvironmentVariable($envKey, $null)
} }
$saved['NODE_OPTIONS'] = [Environment]::GetEnvironmentVariable('NODE_OPTIONS')
[Environment]::SetEnvironmentVariable('NODE_OPTIONS', $null)
$raw = [Collections.Generic.List[object]]::new()
$orders = [Collections.Generic.List[object]]::new()
$random = [Random]::new(20261012)
try {
    $env:DOTNET_InterpMode = '0'; $env:DOTNET_ReadyToRun = '0'; $env:DOTNET_TieredCompilation = '0'; $env:DOTNET_MULTILEVEL_LOOKUP = '0'
    for ($round = 1; $round -le $Rounds; $round++) {
        $engines = @($engineDefinitions | Sort-Object { $random.Next() })
        $orders.Add(@{ round = $round; engines = @($engines.Name) })
        foreach ($engine in $engines) {
            $env:DOTNET_Interpreter = if ($engine.Interp) { 'RuneCLR.Performance.Workloads:*' } else { $null }
            $log = Join-Path $evidence ($engine.Name + '-' + $round + '.log')
            Write-Host ('Round ' + $round + ': ' + $engine.Name)
            Invoke-Logged $engine.File $engine.Args $log
            $records = @(Get-Content $log | Where-Object { $_ -match '^{' } | ForEach-Object { $_ | ConvertFrom-Json })
            $results = @($records | Where-Object kind -eq 'result')
            if ($results.Count -ne 4) { throw ('Expected four cases: ' + $log) }
            if ($engine.Name -like 'coreclr-*') {
                $proof = @($records | Where-Object kind -eq 'execution')
                if ($proof.Count -ne 4 -or @($proof | Where-Object { $_.interpreted -ne [bool]$engine.Interp }).Count) {
                    throw ('Execution backend probe failed: ' + $log)
                }
            }
            foreach ($result in $results) {
                if (@($result.times).Count -ne $Samples -or @($result.times | Where-Object { $_ -le 0 }).Count) { throw 'Invalid timing samples.' }
                $raw.Add(@{ engine = $engine.Name; round = $round; name = $result.name; checksum = $result.checksum; times = $result.times })
            }
        }
    }
} finally { foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) } }

function Median($Values) {
    $sorted = @($Values | Sort-Object); $middle = [int][Math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { return [double]$sorted[$middle] }
    return ([double]$sorted[$middle - 1] + [double]$sorted[$middle]) / 2
}
$summary = @()
foreach ($case in 'numeric', 'entities-soa', 'entities-objects', 'skills') {
    $caseRows = @($raw | Where-Object name -eq $case)
    if (@($caseRows.checksum | Sort-Object -Unique).Count -ne 1) { throw ('Cross-engine checksum mismatch: ' + $case) }
    $luaTimes = @($caseRows | Where-Object engine -eq 'lua-5.4' | ForEach-Object { $_.times })
    $luaMedian = Median $luaTimes
    foreach ($engine in $engineDefinitions.Name) {
        $rows = @($caseRows | Where-Object engine -eq $engine)
        $times = @($rows | ForEach-Object { $_.times })
        $median = Median $times
        $summary += [pscustomobject]@{ case = $case; engine = $engine; checksum = $rows[0].checksum;
            medianMs = $median; minMs = ($times | Measure-Object -Minimum).Minimum; maxMs = ($times | Measure-Object -Maximum).Maximum;
            timeRelativeToLua = $median / $luaMedian; roundMedians = @($rows | ForEach-Object { Median $_.times }) }
    }
}
$hashes = @{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    $hashes[$name] = (Get-FileHash (Join-Path $framework $name) -Algorithm SHA256).Hash
}
# Reject a result if measured assemblies or recorded inputs changed while running.
foreach ($name in $benchmarkBinaryHashes.Keys) {
    if ((Get-FileHash (Join-Path (Split-Path $benchmarkDll -Parent) $name) -Algorithm SHA256).Hash -ne $benchmarkBinaryHashes[$name]) {
        throw ('Benchmark assembly changed during measurement: ' + $name)
    }
}
foreach ($inputs in $buildInputHashes, $sourcesHashes) { foreach ($path in $inputs.Keys) {
    if ((Get-FileHash (Join-Path $root $path) -Algorithm SHA256).Hash -ne $inputs[$path]) {
        throw ('Benchmark input changed during measurement: ' + $path)
    }
} }
$report = @{ date = (Get-Date).ToString('o'); runtimeBase = $base; runtimeBranch = (git -C $RuntimeRepo branch --show-current);
    runtimeProductStamp = $stamp; runtimeConfiguration = 'Release, FEATURE_INTERPRETER=1'; runtimeHashes = $hashes;
    hostCommit = (git -C $root rev-parse HEAD); hostWorkingTree = @(git -C $root status --short); kernelHashes = $sourcesHashes;
    benchmarkBinaryHashes = $benchmarkBinaryHashes; buildInputHashes = $buildInputHashes;
    os = [Runtime.InteropServices.RuntimeInformation]::OSDescription; arch = 'x64'; cpu = (Get-CimInstance Win32_Processor).Name;
    sdk = (dotnet --version); node = (& $node --version); v8 = (& $node -p 'process.versions.v8');
    lua = (& $luaExe); luaArchiveSha256 = $luaSha; luaCompiler = 'MSVC /O2 /DNDEBUG /MD, standard Lua 5.4.9 VM';
    executables = @{ node = (Get-FileHash $node).Hash; lua = (Get-FileHash $luaExe).Hash };
    timer = 'wall-clock high-resolution timer: Stopwatch, hrtime, QueryPerformanceCounter';
    scope = 'Warmed kernels; setup excluded, checksum included; default V8 tiering may optimize during measurement; no allocation-heavy or native host binding tests.';
    settings = @{ InterpMode = 0; Interpreter = 'RuneCLR.Performance.Workloads:* (interpreter runs only)'; ReadyToRun = 0; TieredCompilation = 0; InterpPGO = 0 };
    count = 4096; ticks = 256; numericIterations = 1000000; warmups = 3; samples = $Samples; rounds = $Rounds;
    processOrders = $orders; commands = $engineDefinitions; summary = $summary; raw = $raw; evidenceDirectory = $evidence }
$report | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $evidence 'results.json') -Encoding utf8
$summary | Export-Csv (Join-Path $evidence 'summary.csv') -NoTypeInformation -Encoding utf8
& (Join-Path $PSScriptRoot 'write-benchmark-report.ps1') -Results (Join-Path $evidence 'results.json')
$summary | Format-Table case, engine, medianMs, timeRelativeToLua -AutoSize
Write-Host ('Evidence: ' + $evidence)
