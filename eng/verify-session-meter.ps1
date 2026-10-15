param(
    [string] $RuntimeRepo = 'E:/runtime-budget-20261013',
    [string] $RuntimeLayout,
    [string] $CandidateCommit,
    [string] $BuiltProduct,
    [string] $SdkDotnet,
    [string] $EvidenceDirectory,
    [switch] $StockSmoke,
    [switch] $Concurrent
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$SdkDotnet) { $SdkDotnet = Join-Path $repo 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe' }
$SdkDotnet = (Resolve-Path $SdkDotnet).Path
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $repo ('artifacts/session-budget/meter-{0}-{1}' -f (Get-Date -Format yyyyMMdd-HHmmss), [guid]::NewGuid().ToString('N')) }
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be fresh; previous failures must remain intact.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot = Join-Path $PSScriptRoot 'session-meter-probe'
$sourceHashes = [ordered]@{}
foreach ($source in Get-ChildItem $sourceRoot -Recurse -File | Where-Object { $_.Extension -in '.cs', '.csproj' -and $_.FullName -notmatch '[\/]obj[\/]|[\/]bin[\/]' }) {
    $relative = $source.FullName.Substring($sourceRoot.Length + 1)
    $destination = Join-Path $EvidenceDirectory "source/$relative"
    New-Item -ItemType Directory (Split-Path $destination) -Force | Out-Null
    Copy-Item $source.FullName $destination
    $sourceHashes[$relative] = (Get-FileHash $source.FullName).Hash
}
function Invoke-Child([string] $Executable, [string[]] $Arguments, [hashtable] $Settings, [string] $Log) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true; $info.WorkingDirectory = $repo
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($key in @($info.Environment.Keys)) {
        if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_') -or $key.StartsWith('RUNECLR_')) { $info.Environment.Remove($key) | Out-Null }
    }
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
    $timedOut = !$process.WaitForExit(180000)
    if ($timedOut) { $process.Kill($true); $process.WaitForExit(10000) | Out-Null }
    $outText = if ($stdout.Wait(10000)) { $stdout.GetAwaiter().GetResult() } else { '[capture incomplete after bounded termination]' }
    $errText = if ($stderr.Wait(10000)) { $stderr.GetAwaiter().GetResult() } else { '[capture incomplete after bounded termination]' }
    [IO.File]::WriteAllText($Log + '.stdout', $outText); [IO.File]::WriteAllText($Log + '.stderr', $errText)
    [ordered]@{ executable = $Executable; arguments = $Arguments; settings = $Settings; processId = $process.Id; timedOut = $timedOut;
        terminated = $process.HasExited; exitCode = if ($process.HasExited) { $process.ExitCode } else { $null };
        stdoutSha256 = (Get-FileHash ($Log + '.stdout')).Hash; stderrSha256 = (Get-FileHash ($Log + '.stderr')).Hash
    } | ConvertTo-Json -Depth 6 | Set-Content ($Log + '.process.json')
    if ($timedOut) { throw "Child timed out180s; owned tree killed; raw streams retained: $Log" }
    if ($process.ExitCode -ne 0) { throw "Child failed exit=$($process.ExitCode); raw streams retained: $Log" }
    $jit = if ($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)) { [IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile) } else { '' }
    return @{ stdout = $outText; stderr = $errText; jit = $jit }
}
$request = [ordered]@{ startedUtc = [DateTime]::UtcNow.ToString('o'); platform = 'windows.x64'; sdk = $SdkDotnet;
    sdkSha256 = (Get-FileHash $SdkDotnet).Hash; stockSmoke = [bool]$StockSmoke; concurrent = [bool]$Concurrent; sourceHashes = $sourceHashes;
    scope = 'trusted diagnostic fixture; opcode accounting only; no terminal quota/sandbox/device claim' }
$results = [ordered]@{ passed = $false; executionVerified = $false; diagnosticOnly = $true; terminalEnforcement = $false }
try {
    if (!$StockSmoke) {
        if (!$RuntimeLayout -or !$CandidateCommit) { throw 'Candidate requires explicit RuntimeLayout and CandidateCommit.' }
        $RuntimeRepo = (Resolve-Path $RuntimeRepo).Path; $RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
        $head = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
        if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Candidate commit must be exact and tracked-clean.' }
        $base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
        & git -C $RuntimeRepo merge-base --is-ancestor $base $head
        if ($LASTEXITCODE -ne 0) { throw 'Candidate does not descend from pinned upstream base.' }
        if (!$BuiltProduct) { $BuiltProduct = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Checked' }
        $BuiltProduct = (Resolve-Path $BuiltProduct).Path
        $framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'
        $privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
        $runtimeHashes = [ordered]@{}
        foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
            $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
            if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Matching product/layout hash mismatch: $name" }
        }
        $stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
        if (!$stamp.Contains($head)) { throw 'CoreCLR source stamp is not exact candidate.' }
        $runtimeHashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash
        $runtimeHashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
        $runtimeHashes['hostpolicy.dll'] = (Get-FileHash (Join-Path $framework 'hostpolicy.dll')).Hash
        $request.runtimeBase = $base; $request.candidateCommit = $head; $request.runtimeRepo = $RuntimeRepo; $request.runtimeLayout = $RuntimeLayout
        $request.builtProduct = $BuiltProduct; $request.runtimeSourceStamp = $stamp; $request.runtimeHashes = $runtimeHashes
    }
    $request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $outputs = @{}
    foreach ($project in 'Host', 'Payload') {
        $outputs[$project] = Join-Path $EvidenceDirectory $project.ToLowerInvariant()
        Invoke-Child $SdkDotnet @('build', (Join-Path $sourceRoot "$project/$project.csproj"), '-c', 'Release', '--output', $outputs[$project], '-nodeReuse:false') @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
    }
    $managedBefore = [ordered]@{}
    foreach ($directory in $outputs.Values) { foreach ($file in Get-ChildItem $directory -File) { $managedBefore[$file.FullName] = (Get-FileHash $file.FullName).Hash } }
    $managedBefore | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'managed-identity.json')
    $hostPath = Join-Path $outputs.Host 'MeterProbe.Host.dll'
    if ($StockSmoke) {
        $lane = Invoke-Child $SdkDotnet @($hostPath, $outputs.Payload, (Join-Path $EvidenceDirectory 'stock'), '--stock-smoke') @{} (Join-Path $EvidenceDirectory 'stock.log')
        if (([regex]::Matches($lane.stderr, '(?m)^PASS meter-session=[0-9]+ collected=true ')).Count -ne 20 -or $lane.stderr -notmatch 'METER COMPLETE sessions=20 collected=20 stock=true') { throw 'Stock values/collection smoke incomplete.' }
        $results.stockValuesAndCollection = $true
    } else {
        $common = @{ DOTNET_InterpMode = '0'; DOTNET_RuneCLRInterpretCollectible = '0'; DOTNET_ReadyToRun = '1'; DOTNET_TieredCompilation = '1';
            DOTNET_InterpList = '1'; DOTNET_InterpDump = '*:*'; DOTNET_JitDisasmSummary = '1'; DOTNET_MULTILEVEL_LOOKUP = '0' }
        $lanes = if ($Concurrent) { @('metered', 'compatibility', 'concurrent') } else { @('metered', 'compatibility') }
        foreach ($name in $lanes) {
            $settings = $common.Clone(); $settings.DOTNET_JitStdOutFile = Join-Path $EvidenceDirectory "$name.log.jit"
            $mode = switch ($name) { 'metered' { '--metered-only' } 'compatibility' { '--compatibility' } 'concurrent' { '--concurrent' } }
            $argsForChild = @('exec', '--fx-version', '12.0.0', $hostPath, $outputs.Payload, (Join-Path $EvidenceDirectory $name), $mode)
            $lane = Invoke-Child $privateDotnet $argsForChild $settings (Join-Path $EvidenceDirectory "$name.log")
            if ($lane.stderr -notmatch '(?m)^METER API version=1 private-api=true no-setter=true diagnostic-only=true\r?$') { throw "Missing exact meter API ack: $name" }
            if ($lane.jit -notmatch 'JIT compiled\s+MeterProbe[.]Host[.]Program:RunFrame') { throw "Trusted native host compilation missing: $name" }
            if ($name -eq 'compatibility') {
                if (([regex]::Matches($lane.stderr, '(?m)^PASS unmetered kind=(Ordinary|RequiredUnmetered) values-correct=true getters=System[.]InvalidOperationException collected=true\r?$')).Count -ne 2 -or
                    ([regex]::Matches($lane.stderr, '(?m)^METER QUERY retired=false rejected=3 ')).Count -ne 2 -or
                    ([regex]::Matches($lane.stderr, '(?m)^METER QUERY retired=true rejected=3 ')).Count -ne 2 -or
                    $lane.jit -notmatch 'JIT compiled\s+MeterUGC[.]Payload[.]Entry:Loop' -or $lane.stdout -notmatch 'Compiled method: [.]?MeterUGC[.]Payload[.]Entry:Loop') { throw 'Ordinary native and unmetered-required bytecode/value/query controls incomplete.' }
            } else {
                if (([regex]::Matches($lane.stderr, '(?m)^PASS meter-session=[0-9]+ collected=true ')).Count -ne 20 -or
                    $lane.stderr -notmatch 'PASS boundary-one finite-return=true counting-after-zero=true collected=true' -or
                    $lane.stderr -notmatch 'PASS boundary-max collected=true' -or
                    $lane.stderr -notmatch 'PASS interleaved owner-isolation=true returned-owner=true collected=2' -or
                    ([regex]::Matches($lane.stderr, '(?m)^PASS invalid-limit=(0|-1) exception=System[.]ArgumentOutOfRangeException\r?$')).Count -ne 2) { throw "Meter/owner/boundary values incomplete: $name" }
                $expectedRetired = if ($name -eq 'concurrent') { 25 } else { 24 }
                if (([regex]::Matches($lane.stderr, '(?m)^METER QUERY retired=true rejected=3 ')).Count -ne $expectedRetired) { throw "Meter retirement guard count differs: $name" }
                if ($lane.jit -match 'JIT compiled\s+[.]?MeterUGC[.]') { throw "Reported author native compilation: $name" }
                foreach ($target in @('MeterUGC.Payload.Entry:.cctor', 'MeterUGC.Payload.Entry:.ctor', 'MeterUGC.Payload.Entry:Empty',
                    'MeterUGC.Payload.Entry:Loop', 'MeterUGC.Payload.Entry:Helper', 'MeterUGC.Payload.Entry:Paths', 'MeterUGC.Payload.Entry:ReadVirtual',
                    'MeterUGC.Payload.Entry:Direct', 'MeterUGC.Payload.Entry:Exceptions', 'MeterUGC.Payload.Entry:Filter', 'MeterUGC.Payload.Entry:AfterZero',
                    'MeterUGC.Payload.Entry:ReadStatic', 'MeterUGC.Private.Helper:.cctor', 'MeterUGC.Private.Helper:.ctor', 'MeterUGC.Private.Helper:Read', 'MeterUGC.Private.Helper:Identity')) {
                    if (([regex]::Matches($lane.stdout, '(?m)^Compiled method: [.]?' + [regex]::Escape($target) + '(?:\(|\[|<)')).Count -lt 20) { throw "Missing actual successful bytecode groups >=20 for $target in $name" }
                }
                if (([regex]::Matches($lane.stdout, '(?m)^Compiled method: [.]?MeterUGC[.]Private[.]Generic' + [char]96 + '1\[[^\r\n]*\]:[.]cctor\(')).Count -lt 20) { throw "Private generic cctor bytecode groups incomplete: $name" }
                if ($name -eq 'concurrent' -and $lane.stderr -notmatch 'PASS concurrent trusted-tasks=4 joined-before-snapshot=true value=1998000') { throw 'Concurrent exact joined totals incomplete.' }
            }
            $results[$name] = @{ passed = $true; settings = $settings; arguments = $argsForChild; bytecodeCompilationNotNativeEntryProof = $true }
        }
        $results.executionVerified = $true
    }
    foreach ($path in $managedBefore.Keys) { if ($managedBefore[$path] -ne (Get-FileHash $path).Hash) { throw "Fixture bytes changed during execution: $path" } }
    $results.managedBytesUnchanged = $true; $results.passed = $true
    Write-Output "SESSION METER PASS stock=$([bool]$StockSmoke) terminalEnforcement=false evidence=$EvidenceDirectory"
} catch {
    $results.error = $_.Exception.Message
    throw
} finally {
    $request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $results | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
}
