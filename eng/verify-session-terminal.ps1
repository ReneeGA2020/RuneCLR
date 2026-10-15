param(
    [string] $RuntimeRepo = 'E:/runtime-terminal-20261013',
    [string] $RuntimeLayout,
    [string] $CandidateCommit,
    [string] $BuiltProduct,
    [ValidateSet('Checked','Release')] [string] $RuntimeConfiguration = 'Checked',
    [string] $BuildEvidence,
    [string] $SdkDotnet,
    [string] $EvidenceDirectory,
    [string[]] $Cases,
    [switch] $StockSmoke
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$SdkDotnet) { $SdkDotnet = Join-Path $repo 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe' }
$SdkDotnet = (Resolve-Path $SdkDotnet).Path
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $repo ('artifacts/session-budget/terminal-{0}-{1}' -f (Get-Date -Format yyyyMMdd-HHmmss), [guid]::NewGuid().ToString('N')) }
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be fresh; retain previous failed attempts.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot = Join-Path $PSScriptRoot 'session-terminal-probe'
$entryObserverSource = Join-Path $PSScriptRoot 'windows-entry-observation/WindowsEntryObservation.cs'
$entryObserverSourceSha256 = (Get-FileHash $entryObserverSource).Hash
Copy-Item $entryObserverSource (Join-Path $EvidenceDirectory 'WindowsEntryObservation.cs')
$sourceHashes = [ordered]@{}
foreach ($source in Get-ChildItem $sourceRoot -Recurse -File | Where-Object { $_.Extension -in '.cs', '.csproj' -and $_.FullName.Replace([IO.Path]::DirectorySeparatorChar,[char]'/') -notmatch '/(obj|bin)/' }) {
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
    if ($timedOut) { throw "Child exceeded180s; killed owned process tree; termination is FAIL, raw retained: $Log" }
    if ($process.ExitCode -ne 0) { throw "Child failed exit=$($process.ExitCode); raw retained: $Log" }
    $jit = if ($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)) { [IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile) } else { '' }
    return @{ stdout = $outText; stderr = $errText; jit = $jit }
}
$normalCases = @('TightLoop','TypedCatch','BroadCatch','CatchReturn','Filter','SignalFilter','FiniteFinally','NestedFinally','InfiniteFinally','ThrowingFinally','Constructor','StaticConstructor','TrustedReenter','Good')
if (!$Cases) { $Cases = if ($StockSmoke) { $normalCases } else { $normalCases + @('TwoContexts','Recovery') } }
foreach ($case in $Cases) { if ($case -notin ($normalCases + @('TwoContexts','Recovery'))) { throw "Unknown case: $case" } }
$request = [ordered]@{ startedUtc = [DateTime]::UtcNow.ToString('o'); platform = 'windows.x64'; sdk = $SdkDotnet; sdkSha256 = (Get-FileHash $SdkDotnet).Hash;
    sourceHashes = $sourceHashes; stockSmoke = [bool]$StockSmoke; cases = $Cases; executionLimit = 2048; cleanupLimit = 4096;
    prototypeOnly = $true; finalizersIntegrated = $false; nativeEntryProof = $false }
$request.runtimeConfiguration = $RuntimeConfiguration
$request.entryObserverSourceSha256 = $entryObserverSourceSha256
$request.executionEvidenceScope = if ($RuntimeConfiguration -eq 'Release') { 'Actual native ledgers/business outcomes/ownership/collection; per-method interpreter entry proof pending' } else { 'Checked positive bytecode and native compilation diagnostics plus scalar behavior' }
$results = [ordered]@{ passed = $false; prototypeOnly = $true; finalizersIntegrated = $false; nativeEntryProof = $false; completeTerminalBudget = $false; lanes = [ordered]@{} }
try {
    if (!$StockSmoke) {
        if (!$RuntimeLayout -or !$CandidateCommit) { throw 'Candidate requires explicit RuntimeLayout and CandidateCommit.' }
        $RuntimeRepo = (Resolve-Path $RuntimeRepo).Path; $RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
        $head = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
        if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Candidate must be exact committed tracked-clean source.' }
        & git -C $RuntimeRepo merge-base --is-ancestor b8e5b0b4b7db30385265f935c00a39a3ba507aea $head
        if ($LASTEXITCODE -ne 0) { throw 'Terminal candidate does not descend from verified instruction meter.' }
        if (!$BuiltProduct) { $BuiltProduct = Join-Path $RuntimeRepo ('artifacts/bin/coreclr/windows.x64.' + $RuntimeConfiguration) }
        $BuiltProduct = (Resolve-Path $BuiltProduct).Path
        $framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'; $privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
        $runtimeHashes = [ordered]@{}
        foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
            $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
            if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Matching product/layout hash mismatch: $name" }
        }
        $stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
        if (!$stamp.Contains($head)) { throw 'CoreCLR source stamp mismatch.' }
        $runtimeHashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash
        $runtimeHashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
        $runtimeHashes['hostpolicy.dll'] = (Get-FileHash (Join-Path $framework 'hostpolicy.dll')).Hash
        $request.candidateCommit = $head; $request.runtimeBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'; $request.meterParent = 'b8e5b0b4b7db30385265f935c00a39a3ba507aea'
        $request.runtimeRepo = $RuntimeRepo; $request.runtimeLayout = $RuntimeLayout; $request.builtProduct = $BuiltProduct; $request.runtimeHashes = $runtimeHashes; $request.runtimeSourceStamp = $stamp
    }
    if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') {
        if (!$BuildEvidence) { throw 'Release requires explicit matching BuildEvidence; a configuration label is not provenance.' }
        & py -3 -B (Join-Path $PSScriptRoot 'windows-runtime-validation.py') freeze --candidate-commit $CandidateCommit --runtime $RuntimeRepo --layout $RuntimeLayout --build-evidence $BuildEvidence --output $EvidenceDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Exact Release build/layout provenance validation failed; raw retained.' }
        $request.runtimeProvenanceSha256 = (Get-FileHash (Join-Path $EvidenceDirectory 'runtime-provenance.json')).Hash
    }
    $request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $outputs = @{}
    foreach ($project in 'Host','Payload') {
        $outputs[$project] = Join-Path $EvidenceDirectory $project.ToLowerInvariant()
        Invoke-Child $SdkDotnet @('build',(Join-Path $sourceRoot "$project/$project.csproj"),'-c','Release','--output',$outputs[$project],'-nodeReuse:false') @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
    }
    $managedBefore = [ordered]@{}
    foreach ($directory in $outputs.Values) { foreach ($file in Get-ChildItem $directory -File) { $managedBefore[$file.FullName] = (Get-FileHash $file.FullName).Hash } }
    $managedBefore | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'managed-identity.json')
    $hostPath = Join-Path $outputs.Host 'TerminalProbe.Host.dll'
    $common = @{ DOTNET_InterpMode = '0'; DOTNET_RuneCLRInterpretCollectible = '0'; DOTNET_ReadyToRun = '1'; DOTNET_TieredCompilation = '1';
        DOTNET_InterpList = '1'; DOTNET_InterpDump = '*:*'; DOTNET_JitDisasmSummary = '1'; DOTNET_MULTILEVEL_LOOKUP = '0' }
    if ($RuntimeConfiguration -eq 'Release') { foreach ($key in 'DOTNET_InterpList','DOTNET_InterpDump','DOTNET_JitDisasmSummary') { $common.Remove($key) } }
    $modes = if ($StockSmoke) { @('stock') } else { @('ordinary','diagnostic','terminal') }
    foreach ($mode in $modes) {
        foreach ($case in $Cases) {
            if ($case -in 'TwoContexts','Recovery' -and $mode -ne 'terminal') { continue }
            $nonce = [guid]::NewGuid().ToString('N'); $name = "$mode-$case-$nonce"; $laneDirectory = Join-Path $EvidenceDirectory $name
            $settings = if ($StockSmoke) { @{} } else { $common.Clone() }
            if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') { $settings.RUNECLR_POST_EXECUTION_PRECODE='1' }
            if (!$StockSmoke) { $settings.DOTNET_JitStdOutFile = Join-Path $EvidenceDirectory "$name.log.jit" }
            $arguments = if ($StockSmoke) { @($hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode) } else { @('exec','--fx-version','12.0.0',$hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode) }
            $results.lanes[$name] = @{ passed = $false; mode = $mode; case = $case; nonce = $nonce; settings = $settings; arguments = $arguments }
            $results | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
            $result = Invoke-Child $(if ($StockSmoke) { $SdkDotnet } else { $privateDotnet }) $arguments $settings (Join-Path $EvidenceDirectory "$name.log")
            $receipt = Get-Content (Join-Path $laneDirectory 'result.json') -Raw | ConvertFrom-Json
            if (!$receipt.passed -or $receipt.nonce -ne $nonce -or $receipt.scenario -ne $case -or $receipt.mode -ne $mode -or $receipt.finalizersIntegrated) { throw "Owned scalar outcome/nonce binding mismatch: $name" }
            if ($result.stderr -notmatch ('(?m)^TERMINAL COMPLETE nonce=' + $nonce + ' case=' + $case + ' mode=' + $mode + ' rows=[0-9]+ prototypeOnly=true\r?$')) { throw "Exact owned completion marker missing: $name" }
            $expectedRows = if ($case -eq 'Recovery') { 40 } elseif ($case -eq 'TwoContexts') { 2 } else { 1 }
            if (@($receipt.rows).Count -ne $expectedRows) { throw "Scalar outcome count differs: $name" }
            if (!$StockSmoke) {
                if ($result.stderr -notmatch '(?m)^TERMINAL API version=1 private-api=true prototypeOnly=true finalizersIntegrated=false\r?$' -or
                    ([regex]::Matches($result.stderr,'(?m)^TERMINAL RETIRED rejected=8 exception=System[.]InvalidOperationException\r?$')).Count -ne $expectedRows) { throw "API/retired scalar-query guards incomplete: $name" }
                if ($RuntimeConfiguration -eq 'Checked') {
                if ($result.jit -notmatch 'JIT compiled\s+[.]?TerminalProbe[.]Host[.]Program:(RunFrame|TwoFrames)') { throw "Trusted native execution evidence missing: $name" }
                if ($mode -in 'terminal','diagnostic') {
                    if ($result.jit -match 'JIT compiled\s+[.]?TerminalUGC[.]') { throw "Reported native author-definition compilation: $name" }
                    if ($result.stdout -notmatch '(?m)^Compiled method: [.]?TerminalUGC[.]Payload[.]Entry:') { throw "Actual successful author bytecode evidence missing: $name" }
                } elseif ($result.jit -notmatch 'JIT compiled\s+[.]?TerminalUGC[.]Payload[.]Entry:') { throw "Ordinary author native control missing: $name" }
                }
                if ($mode -in 'ordinary','diagnostic' -and $result.stderr -notmatch '(?m)^TERMINAL UNBUDGETED rejected=5 exception=System[.]InvalidOperationException\r?$') { throw "Nonterminal context terminal-query rejection missing: $name" }
                if ($case -eq 'Recovery' -and ([regex]::Matches($result.stderr,'(?m)^PASS terminal-recovery session=[0-9]+ badCollected=true goodCollected=true goodValue=73 starts=1\r?$')).Count -ne 20) { throw 'Twenty bad/good recovery pairs incomplete.' }
            }
            $results.lanes[$name].passed = $true
            $results.lanes[$name].scalarReceiptSha256 = (Get-FileHash (Join-Path $laneDirectory 'result.json')).Hash
        }
    }
    foreach ($path in $managedBefore.Keys) { if ($managedBefore[$path] -ne (Get-FileHash $path).Hash) { throw "Fixture bytes changed during execution: $path" } }
    if (!$StockSmoke) {
        foreach ($name in $runtimeHashes.Keys) {
            $path = if ($name -eq 'dotnet.exe') { $privateDotnet } elseif ($name -eq 'hostfxr.dll') { Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll' } else { Join-Path $framework $name }
            if ($runtimeHashes[$name] -ne (Get-FileHash $path).Hash) { throw "Matching runtime bytes changed during execution: $name" }
            if ($name -in 'coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll' -and $runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Candidate product changed during execution: $name" }
        }
        if ((& git -C $RuntimeRepo rev-parse HEAD).Trim() -ne $head -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Candidate source changed during execution.' }
        $results.runtimeBytesAndSourceUnchanged = $true
    }
    if ((Get-FileHash $entryObserverSource).Hash -ne $entryObserverSourceSha256) { throw 'Post-execution observer source changed during probes.' }
    if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') {
        & py -3 -B (Join-Path $PSScriptRoot 'windows-runtime-validation.py') check --candidate-commit $CandidateCommit --output $EvidenceDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Frozen Release inputs changed during probes.' }
        $results.releaseProvenanceUnchanged = $true
    }
    $results.managedBytesUnchanged = $true; $results.passed = $true
    Write-Output "SESSION TERMINAL PROBE PASS stock=$([bool]$StockSmoke) prototypeOnly=true finalizersIntegrated=false evidence=$EvidenceDirectory"
} catch { $results.error = $_.Exception.Message; throw }
finally {
    $request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $results | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
}
