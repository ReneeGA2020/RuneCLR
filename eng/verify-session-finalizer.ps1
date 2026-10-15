param(
    [string] $RuntimeRepo = 'E:/runtime-finalizer-20261013',
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
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $repo ('artifacts/session-finalizer/probe-{0}-{1}' -f (Get-Date -Format yyyyMMdd-HHmmss),[guid]::NewGuid().ToString('N')) }
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be new; preserve prior failed runs.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot = Join-Path $PSScriptRoot 'session-finalizer-probe'
$entryObserverSource = Join-Path $PSScriptRoot 'windows-entry-observation/WindowsEntryObservation.cs'
$entryObserverSourceSha256 = (Get-FileHash $entryObserverSource).Hash
Copy-Item $entryObserverSource (Join-Path $EvidenceDirectory 'WindowsEntryObservation.cs')
$sourceHashes = [ordered]@{}
foreach ($source in Get-ChildItem $sourceRoot -Recurse -File | Where-Object { $_.Extension -in '.cs','.csproj' -and $_.FullName.Replace([IO.Path]::DirectorySeparatorChar,[char]'/') -notmatch '/(obj|bin)/' }) {
    $relative = $source.FullName.Substring($sourceRoot.Length + 1); $destination = Join-Path $EvidenceDirectory "source/$relative"
    New-Item -ItemType Directory (Split-Path $destination) -Force | Out-Null
    Copy-Item $source.FullName $destination; $sourceHashes[$relative] = (Get-FileHash $source.FullName).Hash
}
$buildConfigHashes = [ordered]@{}
foreach ($name in 'Directory.Build.props','Directory.Build.targets','global.json','NuGet.Config') { if (Test-Path (Join-Path $repo $name)) { $buildConfigHashes[$name] = (Get-FileHash (Join-Path $repo $name)).Hash; Copy-Item (Join-Path $repo $name) (Join-Path $EvidenceDirectory $name) } }
function Assert-FrozenSources {
    foreach ($relative in $sourceHashes.Keys) { if ($sourceHashes[$relative] -ne (Get-FileHash (Join-Path $sourceRoot $relative)).Hash) { throw "Fixture source changed after freezing: $relative" } }
    foreach ($name in $buildConfigHashes.Keys) { if ($buildConfigHashes[$name] -ne (Get-FileHash (Join-Path $repo $name)).Hash) { throw "Fixture build configuration changed after freezing: $name" } }
}
function Invoke-Child([string] $Executable,[string[]] $Arguments,[hashtable] $Settings,[string] $Log,[bool] $ExpectedFatal = $false) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true; $info.WorkingDirectory = $repo
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($key in @($info.Environment.Keys)) { if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_') -or $key.StartsWith('RUNECLR_')) { $info.Environment.Remove($key) | Out-Null } }
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info); $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
    $timedOut = !$process.WaitForExit(180000)
    if ($timedOut) { $process.Kill($true); $process.WaitForExit(10000) | Out-Null }
    $outText = if ($stdout.Wait(10000)) { $stdout.GetAwaiter().GetResult() } else { '[capture incomplete after owned timeout termination]' }
    $errText = if ($stderr.Wait(10000)) { $stderr.GetAwaiter().GetResult() } else { '[capture incomplete after owned timeout termination]' }
    [IO.File]::WriteAllText($Log+'.stdout',$outText); [IO.File]::WriteAllText($Log+'.stderr',$errText)
    [ordered]@{ executable = $Executable; arguments = $Arguments; settings = $Settings; processId = $process.Id;
        timedOut = $timedOut; terminated = $process.HasExited; expectedFatal = $ExpectedFatal; exitCode = if ($process.HasExited) { $process.ExitCode } else { $null };
        stdoutSha256 = (Get-FileHash ($Log+'.stdout')).Hash; stderrSha256 = (Get-FileHash ($Log+'.stderr')).Hash
    } | ConvertTo-Json -Depth 6 | Set-Content ($Log+'.process.json')
    if ($timedOut) { throw "Finalizer child exceeded180s; owned tree killed; watchdog never counts as fatal/positive success: $Log" }
    if (!$ExpectedFatal -and $process.ExitCode -ne 0) { throw "Finalizer positive failed exit=$($process.ExitCode); retained raw: $Log" }
    if ($ExpectedFatal -and $process.ExitCode -eq 0) { throw "Expected unhandled finalizer exception unexpectedly survived: $Log" }
    $jit = if ($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)) { [IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile) } else { '' }
    return @{ stdout = $outText; stderr = $errText; jit = $jit; exitCode = $process.ExitCode }
}
$positive = @('ActiveLoop','ActiveLoopFinally','ActiveLoopInfiniteFinally','AlreadyTerminated','UnloadBeforeFinalization','InheritedTrustedBase','AuthorOverrideFinite','AuthorOverrideInfinite','GoodFiniteControl')
$fatal = @('FatalTrustedCanceled','FatalTrustedInvalid','FatalAuthorCanceled','FatalAuthorInvalid','FatalPrototypeCanceled','FatalRequiredCanceled')
if (!$Cases) { $Cases = if ($StockSmoke) { $positive + @('FatalTrustedCanceled','FatalTrustedInvalid','FatalAuthorCanceled','FatalAuthorInvalid') } else { $positive + $fatal } }
foreach ($case in $Cases) { if ($case -notin ($positive+$fatal)) { throw "Unknown finalizer case: $case" } }
$request = [ordered]@{ startedUtc = [DateTime]::UtcNow.ToString('o'); platform = 'windows.x64'; sdk = $SdkDotnet; sdkSha256 = (Get-FileHash $SdkDotnet).Hash;
    sourceHashes = $sourceHashes; buildConfigHashes = $buildConfigHashes; stockSmoke = [bool]$StockSmoke; cases = $Cases; executionLimit = 2048; cleanupLimit = 4096;
    prototypeOnly = $true; authorFinalizersProductionSupported = $false; nativeEntryProof = $false }
$request.runtimeConfiguration = $RuntimeConfiguration
$request.entryObserverSourceSha256 = $entryObserverSourceSha256
$request.executionEvidenceScope = if ($RuntimeConfiguration -eq 'Release') { 'Actual native ledgers/business outcomes/ownership/collection; per-method interpreter entry proof pending' } else { 'Checked positive bytecode and native compilation diagnostics plus scalar behavior' }
$results = [ordered]@{ passed = $false; prototypeOnly = $true; authorFinalizersProductionSupported = $false; nativeEntryProof = $false; lanes = [ordered]@{} }
try {
    if (!$StockSmoke) {
        if (!$RuntimeLayout -or !$CandidateCommit) { throw 'Explicit matching RuntimeLayout and CandidateCommit required.' }
        $RuntimeRepo = (Resolve-Path $RuntimeRepo).Path; $RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
        $head = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
        if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Exact committed tracked-clean runtime candidate required.' }
        & git -C $RuntimeRepo merge-base --is-ancestor 7660f3069b3751b648f038bf7f3e9cfc6f96ff09 $head
        if ($LASTEXITCODE -ne 0) { throw 'Finalizer candidate does not descend from verified terminal prototype.' }
        if (!$BuiltProduct) { $BuiltProduct = Join-Path $RuntimeRepo ('artifacts/bin/coreclr/windows.x64.' + $RuntimeConfiguration) }
        $BuiltProduct = (Resolve-Path $BuiltProduct).Path; $framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'; $privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
        $runtimeHashes = [ordered]@{}
        foreach ($name in 'coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll') {
            $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
            if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Matching layout/product bytes differ: $name" }
        }
        $stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
        if (!$stamp.Contains($head)) { throw 'Actual CoreCLR source stamp differs.' }
        $runtimeHashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash; $runtimeHashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
        $runtimeHashes['hostpolicy.dll'] = (Get-FileHash (Join-Path $framework 'hostpolicy.dll')).Hash
        $request.candidateCommit = $head; $request.terminalParent = '7660f3069b3751b648f038bf7f3e9cfc6f96ff09'; $request.runtimeBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
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
        Assert-FrozenSources
        $outputs[$project] = Join-Path $EvidenceDirectory $project.ToLowerInvariant()
        Invoke-Child $SdkDotnet @('build',(Join-Path $sourceRoot "$project/$project.csproj"),'-c','Release','--output',$outputs[$project],'-nodeReuse:false') @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
        Assert-FrozenSources
    }
    $managedBefore = [ordered]@{}
    foreach ($directory in $outputs.Values) { foreach ($file in Get-ChildItem $directory -File) { $managedBefore[$file.FullName] = (Get-FileHash $file.FullName).Hash } }
    $managedBefore | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'managed-identity.json')
    $hostPath = Join-Path $outputs.Host 'FinalizerProbe.Host.dll'
    $common = @{ DOTNET_InterpMode = '0'; DOTNET_RuneCLRInterpretCollectible = '0'; DOTNET_ReadyToRun = '1'; DOTNET_TieredCompilation = '1'; DOTNET_InterpList = '1'; DOTNET_InterpDump = '*:*'; DOTNET_JitDisasmSummary = '1'; DOTNET_MULTILEVEL_LOOKUP = '0' }
    if ($RuntimeConfiguration -eq 'Release') { foreach ($key in 'DOTNET_InterpList','DOTNET_InterpDump','DOTNET_JitDisasmSummary') { $common.Remove($key) } }
    foreach ($case in $Cases) {
        $isFatal = $case -in $fatal
        $mode = if ($case.StartsWith('FatalTrusted')) { 'default' } elseif ($StockSmoke) { 'stock' } elseif ($case -eq 'FatalRequiredCanceled') { 'required' } elseif ($case -in 'FatalAuthorCanceled','FatalAuthorInvalid') { 'ordinary' } else { 'terminal' }
        $nonce = [guid]::NewGuid().ToString('N'); $name = "$mode-$case-$nonce"; $laneDirectory = Join-Path $EvidenceDirectory $name
        $settings = if ($StockSmoke) { @{} } else { $common.Clone() }
        if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') { $settings.RUNECLR_POST_EXECUTION_PRECODE='1' }
            if (!$StockSmoke) { $settings.DOTNET_JitStdOutFile = Join-Path $EvidenceDirectory "$name.log.jit" }
        $arguments = if ($StockSmoke) { @($hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode) } else { @('exec','--fx-version','12.0.0',$hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode) }
        $results.lanes[$name] = @{ passed = $false; case = $case; mode = $mode; nonce = $nonce; expectedFatal = $isFatal; settings = $settings; arguments = $arguments }
        $results | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
        $result = Invoke-Child $(if ($StockSmoke) { $SdkDotnet } else { $privateDotnet }) $arguments $settings (Join-Path $EvidenceDirectory "$name.log") $isFatal
        if ($isFatal) {
            $exception = if ($case.Contains('Canceled')) { 'System.OperationCanceledException' } else { 'System.InvalidOperationException' }
            $marker = "FINALIZER FATAL ARMED nonce=$nonce case=$case mode=$mode exception=$exception nativeLatchBefore=false"
            if ($result.stderr.Split([char]10).Trim() -notcontains $marker -or $result.stderr -notmatch ('(?m)^Unhandled exception[.] ' + [regex]::Escape($exception) + '(?:[:\r\n]|$)') -or $result.stderr -notmatch '[:.]Finalize\(') { throw "Expected original unhandled finalizer exception/owned marker not established: $name" }
            if (Test-Path (Join-Path $laneDirectory 'result.json')) { throw "Fatal child unexpectedly created positive outcome: $name" }
            $results.lanes[$name].actualAbnormalExit = $result.exitCode; $results.lanes[$name].expectedUnhandledType = $exception
        } else {
            $receipt = Get-Content (Join-Path $laneDirectory 'result.json') -Raw | ConvertFrom-Json
            if (!$receipt.passed -or $receipt.nonce -ne $nonce -or $receipt.scenario -ne $case -or $receipt.mode -ne $mode -or !$receipt.targetCollected -or !$receipt.contextCollected -or $receipt.queueSentinels -ne 2 -or $receipt.nextGood.value -ne 73 -or !$receipt.nextGood.collected) { throw "Owned finalizer scalar/collection/next-session receipt differs: $name" }
            if ($result.stderr -notmatch ('(?m)^FINALIZER COMPLETE nonce=' + $nonce + ' case=' + $case + ' mode=' + $mode + ' targetCollected=true contextCollected=true sentinels=2 nextGood=73 nextCollected=true\r?$') -or
                ([regex]::Matches($result.stderr,'(?m)^FINALIZER QUEUE nonce=' + $nonce + ' pass=1 sentinel=true\r?$')).Count -ne 1 -or
                ([regex]::Matches($result.stderr,'(?m)^FINALIZER QUEUE nonce=' + $nonce + ' pass=2 sentinel=true\r?$')).Count -ne 1) { throw "Two actual trusted queue drains or owned completion missing: $name" }
            $results.lanes[$name].scalarReceiptSha256 = (Get-FileHash (Join-Path $laneDirectory 'result.json')).Hash
        }
        if (!$StockSmoke) {
            if ($mode -ne 'default' -and $result.stderr -notmatch '(?m)^FINALIZER API boundaryVersion=1 terminalVersion=1 private-api=true\r?$') { throw "Actual finalizer capability acknowledgement missing: $name" }
            if ($RuntimeConfiguration -eq 'Checked') {
            if ($result.jit -notmatch 'JIT compiled\s+[.]?FinalizerProbe[.]Host[.]Program:(RunFrame|PrepareRetired|FatalFrame)') { throw "Trusted native finalizer-fixture execution positive missing: $name" }
            if ($mode -in 'terminal','required') {
                if ($result.jit -match 'JIT compiled\s+[.]?FinalizerUGC[.]') { throw "Reported native author-definition compilation: $name" }
                if ($result.stdout -notmatch '(?m)^Compiled method: [.]?FinalizerUGC[.]Payload[.]Entry:') { throw "Author successful bytecode evidence missing: $name" }
            }
            }
            if (!$isFatal) {
                $owner = Get-Content (Join-Path $laneDirectory 'finalizer-owner.json') -Raw | ConvertFrom-Json
                $expectedOwner = if ($case -eq 'InheritedTrustedBase') { 'FinalizerProbe.Contract.TrustedBase' } elseif ($case -eq 'AuthorOverrideFinite') { 'FinalizerUGC.Payload.OverrideFiniteTarget' } elseif ($case -eq 'AuthorOverrideInfinite') { 'FinalizerUGC.Payload.OverrideInfiniteTarget' } else { 'FinalizerUGC.Payload.Target' }
                if ($owner.definingType -ne $expectedOwner -or !$owner.targetCollectible -or $owner.token -notmatch '^0x060[0-9a-f]{5}$') { throw "Resolved actual finalizer definition owner differs: $name" }
                if ($case -eq 'InheritedTrustedBase') {
                    if ($owner.definingCollectible -or $owner.definingAssembly -ne 'FinalizerProbe.Contract' -or ($RuntimeConfiguration -eq 'Checked' -and $result.jit -notmatch 'JIT compiled\s+[.]?FinalizerProbe[.]Contract[.]TrustedBase:Finalize')) { throw 'Inherited trusted finalizer definition/native execution evidence missing.' }
                } elseif (!$owner.definingCollectible -or $owner.definingAssembly -ne 'FinalizerProbe.Payload') { throw "Authored finalizer definition escaped collectible payload: $name" }
                if ($RuntimeConfiguration -eq 'Checked') {
                if ($case -notin 'AlreadyTerminated','InheritedTrustedBase' -and $result.stdout -notmatch ('(?m)^Compiled method: [.]?' + [regex]::Escape($expectedOwner) + ':Finalize\(')) { throw "Actual authored finalizer successful bytecode body missing: $name" }
                if ($case -in 'ActiveLoopFinally','UnloadBeforeFinalization','AuthorOverrideFinite' -and $result.stdout -notmatch '(?m)^Compiled method: [.]?FinalizerUGC[.]Private[.]Helper:Cleanup\(') { throw "Actual finalizer-private cleanup body bytecode missing: $name" }
                }
            }
            if (!$isFatal -and ([regex]::Matches($result.stderr,'(?m)^FINALIZER RETIRED rejected=8 exception=System[.]InvalidOperationException\r?$')).Count -ne 2) { throw "Retired primary/next-good context queries not guarded: $name" }
        }
        $results.lanes[$name].passed = $true
    }
    foreach ($path in $managedBefore.Keys) { if ($managedBefore[$path] -ne (Get-FileHash $path).Hash) { throw "Fixture bytes changed during finalizer run: $path" } }
    Assert-FrozenSources
    $results.sourceAndBuildConfigUnchanged = $true
    if (!$StockSmoke) {
        foreach ($name in $runtimeHashes.Keys) {
            $path = if ($name -eq 'dotnet.exe') { $privateDotnet } elseif ($name -eq 'hostfxr.dll') { Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll' } else { Join-Path $framework $name }
            if ($runtimeHashes[$name] -ne (Get-FileHash $path).Hash) { throw "Matching runtime changed during finalizer execution: $name" }
            if ($name -in 'coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll' -and $runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Native product changed during finalizer execution: $name" }
        }
        if ((& git -C $RuntimeRepo rev-parse HEAD).Trim() -ne $head -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Candidate source changed during finalizer execution.' }
        $results.runtimeBytesAndSourceUnchanged = $true
    }
    if ((Get-FileHash $entryObserverSource).Hash -ne $entryObserverSourceSha256) { throw 'Post-execution observer source changed during probes.' }
    if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') {
        & py -3 -B (Join-Path $PSScriptRoot 'windows-runtime-validation.py') check --candidate-commit $CandidateCommit --output $EvidenceDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Frozen Release inputs changed during probes.' }
        $results.releaseProvenanceUnchanged = $true
    }
    $results.managedBytesUnchanged = $true; $results.passed = $true
    Write-Output "SESSION FINALIZER PROBE PASS stock=$([bool]$StockSmoke) authorFinalizersProductionSupported=false evidence=$EvidenceDirectory"
} catch { $results.error = $_.Exception.Message; throw }
finally { $request | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'request.json'); $results | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDirectory 'results.json') }
