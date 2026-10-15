param(
    [Parameter(Mandatory)][string]$RuntimeRepo,
    [Parameter(Mandatory)][string]$PrivateLayout,
    [ValidateRange(3, 30)][int]$Samples = 7,
    [ValidateRange(1, 10)][int]$Rounds = 3
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$PrivateLayout = (Resolve-Path $PrivateLayout).Path
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
if (![Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows) -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'The pinned entry probe requires Windows x64.' }
if ((git -C $RuntimeRepo rev-parse HEAD) -ne $base -or
    (git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Expected the pinned, tracked-clean runtime checkout.' }
$native = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Release'
$cache = Join-Path $RuntimeRepo 'artifacts/obj/coreclr/windows.x64.Release/CMakeCache.txt'
if (!(Select-String -Path $cache -Pattern '^CMAKE_BUILD_TYPE:STRING=Release$') -or
    !(Select-String -Path $cache -Pattern '^FEATURE_INTERPRETER:[^=]+=1$')) { throw 'Expected Release CoreCLR with FeatureInterpreter=true.' }
$framework = Join-Path $PrivateLayout 'shared/Microsoft.NETCore.App/12.0.0'
$runtimeHashes = @{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    $hash = (Get-FileHash (Join-Path $framework $name)).Hash
    if ($hash -ne (Get-FileHash (Join-Path $native $name)).Hash) { throw ('Private layout differs from Release output: ' + $name) }
    $runtimeHashes[$name] = $hash
}
$stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if ($stamp -notlike ('*' + $base + '*')) { throw 'Native product stamp differs from the source base.' }
$privateDotnet = Join-Path $PrivateLayout 'dotnet.exe'
$evidence = Join-Path $root ('artifacts/performance/sessions-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
function Invoke-Logged([string]$File, [string[]]$Arguments, [string]$Log) {
    & $File @Arguments *> $Log
    if ($LASTEXITCODE -ne 0) { throw ('Command failed (' + $LASTEXITCODE + '): ' + $File + '; log: ' + $Log) }
}
function Invoke-Cold([string]$Log) {
    # Direct process timing avoids PowerShell's external-command/redirection overhead.
    # Stream capture runs concurrently; writing the evidence file is after timing.
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $privateDotnet
    $startInfo.Arguments = 'exec --fx-version 12.0.0 "' + $sessionDll + '" --cold'
    $startInfo.UseShellExecute = $false; $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true; $startInfo.RedirectStandardError = $true
    $start = [Diagnostics.Stopwatch]::GetTimestamp()
    $process = [Diagnostics.Process]::Start($startInfo)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $elapsed = ([Diagnostics.Stopwatch]::GetTimestamp() - $start) * 1000.0 / [Diagnostics.Stopwatch]::Frequency
        ($stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()) | Set-Content $Log -Encoding utf8
        if ($process.ExitCode -ne 0) { throw ('Cold process failed (' + $process.ExitCode + '); log: ' + $Log) }
        return $elapsed
    } finally { $process.Dispose() }
}
foreach ($project in 'RuneCLR.PerformanceHost', 'RuneCLR.SessionBenchmarks') {
    Invoke-Logged 'dotnet' @('build', (Join-Path $root ('benchmarks/' + $project)), '-c', 'Release') (Join-Path $evidence ($project + '-build.log'))
}
$performanceDll = Join-Path $root 'benchmarks/RuneCLR.PerformanceHost/bin/Release/net11.0/RuneCLR.PerformanceHost.dll'
$sessionDll = Join-Path $root 'benchmarks/RuneCLR.SessionBenchmarks/bin/Release/net11.0/RuneCLR.SessionBenchmarks.dll'

# Capture actual executed DLLs as well as source/configuration before measurement.
$inputFiles = @(Get-ChildItem (Join-Path $root 'benchmarks') -File -Recurse | Where-Object { $_.FullName -notmatch '[\/](bin|obj)[\/]' } | ForEach-Object FullName)
$inputFiles += @(Get-ChildItem (Join-Path $root 'src') -File -Recurse | Where-Object { $_.FullName -notmatch '[\/](bin|obj)[\/]' } | ForEach-Object FullName)
$inputFiles += @('Directory.Build.props', 'global.json', 'eng/benchmark-sessions.ps1' | ForEach-Object { Join-Path $root $_ })
foreach ($directory in (Split-Path $performanceDll), (Split-Path $sessionDll)) {
    $inputFiles += @(Get-ChildItem $directory -Recurse -File | Where-Object { $_.Extension -in '.dll', '.json' } | ForEach-Object FullName)
}
$inputHashes = @{}
foreach ($file in ($inputFiles | Sort-Object -Unique)) { $inputHashes[$file.Substring($root.Length + 1)] = (Get-FileHash $file).Hash }
$settings = @('InterpMode', 'Interpreter', 'InterpreterName', 'InterpreterPath', 'ReadyToRun', 'TieredCompilation',
    'InterpPGO', 'InterpList', 'InterpDump', 'JitDisasm', 'JitDisasmSummary', 'JitDump', 'JitNoInline',
    'JitStress', 'GCStress', 'EnableHWIntrinsic', 'MULTILEVEL_LOOKUP')
$saved = @{}
foreach ($prefix in 'DOTNET_', 'COMPlus_') { foreach ($key in $settings) {
    $envKey = $prefix + $key; $saved[$envKey] = [Environment]::GetEnvironmentVariable($envKey)
    [Environment]::SetEnvironmentVariable($envKey, $null)
} }
$raw = [Collections.Generic.List[object]]::new()
$orders = [Collections.Generic.List[object]]::new()
$random = [Random]::new(20261012)
try {
    $env:DOTNET_InterpMode = '0'; $env:DOTNET_ReadyToRun = '0'; $env:DOTNET_TieredCompilation = '0'; $env:DOTNET_MULTILEVEL_LOOKUP = '0'
    for ($round = 1; $round -le $Rounds; $round++) {
        $engines = @('coreclr-jit', 'coreclr-interpreter' | Sort-Object { $random.Next() })
        $orders.Add(@{ round = $round; engines = $engines })
        foreach ($engine in $engines) {
            $interp = $engine -eq 'coreclr-interpreter'
            Write-Host ('Round ' + $round + ': ' + $engine)
            $env:DOTNET_Interpreter = if ($interp) { 'RuneCLR.Performance.Workloads:*' } else { $null }
            $log = Join-Path $evidence ($engine + '-' + $round + '-extended.log')
            Invoke-Logged $privateDotnet @('exec', '--fx-version', '12.0.0', $performanceDll, "$Samples", '--extended-only') $log
            $records = @(Get-Content $log | Where-Object { $_ -match '^{' } | ForEach-Object { $_ | ConvertFrom-Json })
            $results = @($records | Where-Object kind -eq 'result')
            $proof = @($records | Where-Object kind -eq 'execution')
            $hostProof = @($records | Where-Object kind -eq 'host-execution')
            if ($results.Count -ne 2 -or $proof.Count -ne 3 -or $hostProof.Count -ne 4 -or
                @($proof | Where-Object { $_.interpreted -ne $interp }).Count -or
                @($hostProof | Where-Object interpreted).Count) { throw ('Extended backend proof failed: ' + $log) }
            foreach ($result in $results) {
                $expected = if ($result.name -eq 'host-api') { 8590000128L } elseif ($result.name -eq 'allocations-generics') { 16514272L } else { throw 'Unknown kernel.' }
                if ($result.checksum -ne $expected) { throw 'Kernel checksum failed.' }
                $raw.Add(@{ engine = $engine; round = $round; record = $result })
            }
            $env:DOTNET_Interpreter = if ($interp) { 'RuneCLR.SessionMap.*:*' } else { $null }
            $log = Join-Path $evidence ($engine + '-' + $round + '-sessions.log')
            Invoke-Logged $privateDotnet @('exec', '--fx-version', '12.0.0', $sessionDll, "$Samples") $log
            $records = @(Get-Content $log | Where-Object { $_ -match '^{' } | ForEach-Object { $_ | ConvertFrom-Json })
            $proof = @($records | Where-Object kind -eq 'execution')
            $hostProof = @($records | Where-Object kind -eq 'host-execution')
            $sessions = @($records | Where-Object kind -eq 'session')
            $retention = @($records | Where-Object kind -eq 'retention')
            if ($proof.Count -ne 8 -or $hostProof.Count -ne 2 -or $sessions.Count -ne 3 -or $retention.Count -ne 1 -or
                @($proof | Where-Object { $_.interpreted -ne $interp }).Count -or
                @($hostProof | Where-Object interpreted).Count -or $retention[0].collectedAfter -ne 40) { throw ('Session backend/retention proof failed: ' + $log) }
            foreach ($record in @($sessions) + @($retention)) { $raw.Add(@{ engine = $engine; round = $round; record = $record }) }
            for ($sample = 1; $sample -le $Samples; $sample++) {
                $log = Join-Path $evidence ($engine + '-' + $round + '-cold-' + $sample + '.log')
                $elapsed = Invoke-Cold $log
                $cold = @(Get-Content $log | Where-Object { $_ -match '^{' } | ForEach-Object { $_ | ConvertFrom-Json })
                if ($cold.Count -ne 1 -or $cold[0].kind -ne 'cold' -or $cold[0].ms -le 0) { throw ('Invalid cold record: ' + $log) }
                $raw.Add(@{ engine = $engine; round = $round; record = $cold[0]; processMs = $elapsed })
            }
        }
    }
} finally { foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) } }
foreach ($relative in $inputHashes.Keys) {
    if ((Get-FileHash (Join-Path $root $relative)).Hash -ne $inputHashes[$relative]) { throw ('Measurement input changed: ' + $relative) }
}
function Median($Values) {
    $sorted = @($Values | Sort-Object); $middle = [int][Math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { return [double]$sorted[$middle] }
    return ([double]$sorted[$middle - 1] + [double]$sorted[$middle]) / 2
}
$summary = [Collections.Generic.List[object]]::new()
foreach ($name in 'host-api', 'allocations-generics', 'empty-session', 'gameplay-start', 'gameplay-128-ticks') {
    foreach ($engine in 'coreclr-interpreter', 'coreclr-jit') {
        $rows = @($raw | Where-Object { $_.engine -eq $engine -and $_.record.name -eq $name })
        foreach ($row in $rows) {
            if (@($row.record.times).Count -ne $Samples -or @($row.record.allocatedBytes).Count -ne $Samples -or
                @($row.record.gcCounts).Count -ne $Samples -or @($row.record.times | Where-Object { $_ -le 0 }).Count) { throw ('Invalid samples: ' + $name) }
        }
        $times = @($rows | ForEach-Object { $_.record.times })
        $allocations = @($rows | ForEach-Object { $_.record.allocatedBytes })
        $summary.Add([pscustomobject]@{ name = $name; engine = $engine; samples = $times.Count; medianMs = (Median $times);
            minMs = ($times | Measure-Object -Minimum).Minimum; maxMs = ($times | Measure-Object -Maximum).Maximum;
            medianAllocatedBytes = (Median $allocations); roundMedians = @($rows | ForEach-Object { Median $_.record.times }) })
    }
}
foreach ($engine in 'coreclr-interpreter', 'coreclr-jit') {
    $rows = @($raw | Where-Object { $_.engine -eq $engine -and $_.record.kind -eq 'cold' })
    $summary.Add([pscustomobject]@{ name = 'cold-process-to-exit'; engine = $engine; samples = $rows.Count;
        medianMs = (Median $rows.processMs); minMs = ($rows.processMs | Measure-Object -Minimum).Minimum;
        maxMs = ($rows.processMs | Measure-Object -Maximum).Maximum; medianFirstMapMs = (Median $rows.record.ms) })
}
$report = @{ date = (Get-Date).ToString('o'); runtimeBase = $base; runtimeProductStamp = $stamp; runtimeHashes = $runtimeHashes;
    runtimeConfiguration = 'Release, FEATURE_INTERPRETER=1'; runtimeBranch = (git -C $RuntimeRepo branch --show-current);
    hostCommit = (git -C $root rev-parse HEAD); hostWorkingTree = @(git -C $root status --short); inputHashes = $inputHashes;
    os = [Runtime.InteropServices.RuntimeInformation]::OSDescription; arch = 'x64'; cpu = (Get-CimInstance Win32_Processor).Name;
    sdk = (dotnet --version); privateLayout = $PrivateLayout; samples = $Samples; rounds = $Rounds; processOrders = $orders;
    settings = @{ InterpMode = 0; ReadyToRun = 0; TieredCompilation = 0;
        kernelInterpreter = 'RuneCLR.Performance.Workloads:*'; sessionInterpreter = 'RuneCLR.SessionMap.*:*';
        rule = 'selective interpretation of UGC assembly; trusted host/framework remain native' };
    commands = @{ executable = $privateDotnet; prefix = @('exec', '--fx-version', '12.0.0');
        extended = @($performanceDll, "$Samples", '--extended-only'); sessions = @($sessionDll, "$Samples"); cold = @($sessionDll, '--cold') };
    allocationScope = 'current thread only; process-wide GC counters';
    coldScope = 'direct Process.Start through exit, includes host startup, manifest reads, first map and JSON output/stream capture; log file write excluded; OS file caches not flushed';
    evidenceDirectory = $evidence; summary = $summary; raw = $raw }
$report | ConvertTo-Json -Depth 15 | Set-Content (Join-Path $evidence 'results.json') -Encoding utf8
$summary | Export-Csv (Join-Path $evidence 'summary.csv') -NoTypeInformation -Encoding utf8
$summary | Format-Table name, engine, medianMs, medianAllocatedBytes -AutoSize
Write-Host ('Evidence: ' + $evidence)
