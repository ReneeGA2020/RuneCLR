param(
    [string] $RuntimeRepo = 'E:/runtime-selection-20261013',
    [Parameter(Mandatory)][string] $RuntimeLayout,
    [Parameter(Mandatory)][string] $CandidateCommit,
    [string] $BuiltProduct,
    [string] $SdkDotnet,
    [string] $EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$SdkDotnet) { $SdkDotnet = Join-Path $repo 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe' }
$SdkDotnet = (Resolve-Path $SdkDotnet).Path
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
if (!$BuiltProduct) { $BuiltProduct = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Checked' }
$BuiltProduct = (Resolve-Path $BuiltProduct).Path
$head = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) {
    throw 'Session-policy acceptance needs the explicit committed tracked-clean candidate.'
}
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
& git -C $RuntimeRepo merge-base --is-ancestor $base $head
if ($LASTEXITCODE -ne 0) { throw 'Candidate does not descend from the pinned base.' }
$framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'
$privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
$runtimeHashes = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
    if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) {
        throw "Candidate build/layout mismatch: $name"
    }
}
$stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$stamp.Contains($head)) { throw "Candidate source stamp mismatch: $stamp" }
$runtimeHashes['dotnet.exe'] = (Get-FileHash $privateDotnet).Hash
$runtimeHashes['hostfxr.dll'] = (Get-FileHash (Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll')).Hash
$runtimeHashes['hostpolicy.dll'] = (Get-FileHash (Join-Path $framework 'hostpolicy.dll')).Hash
if (!$EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $repo ("artifacts/session-policy/session-{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N'))
}
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be new; preserve failed experiments.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot = Join-Path $PSScriptRoot 'execution-selection-probe'
foreach ($source in Get-ChildItem $sourceRoot -Recurse -File | Where-Object { $_.Extension -in '.cs', '.csproj' -and $_.FullName -notmatch '[\/]obj[\/]|[\/]bin[\/]' }) {
    $relative = $source.FullName.Substring($sourceRoot.Length + 1)
    $destination = Join-Path $EvidenceDirectory "source/$relative"
    New-Item -ItemType Directory (Split-Path $destination) -Force | Out-Null
    Copy-Item $source.FullName $destination
}

function Invoke-Child([string] $Executable, [string[]] $Arguments, [hashtable] $Settings, [string] $Log) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.WorkingDirectory = $repo
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($key in @($info.Environment.Keys)) {
        if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_')) { $info.Environment.Remove($key) | Out-Null }
    }
    $info.Environment.Remove('RUNECLR_PROBE_FACTORY') | Out-Null
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timedOut = !$process.WaitForExit(180000)
    if ($timedOut) { $process.Kill($true); $process.WaitForExit(10000) | Out-Null }
    $outText = if ($stdout.Wait(10000)) { $stdout.GetAwaiter().GetResult() } else { '[capture incomplete after bounded termination]' }
    $errText = if ($stderr.Wait(10000)) { $stderr.GetAwaiter().GetResult() } else { '[capture incomplete after bounded termination]' }
    [IO.File]::WriteAllText($Log + '.stdout', $outText)
    [IO.File]::WriteAllText($Log + '.stderr', $errText)
    [IO.File]::WriteAllText($Log, $outText + $errText)
    if ($timedOut) {
        @{ timedOut = $true; processId = $process.Id; timeoutSeconds = 180; terminated = $process.HasExited;
            executable = $Executable; arguments = $Arguments; settings = $Settings } | ConvertTo-Json -Depth 5 | Set-Content ($Log + '.timeout.json')
        throw "Child timed out after180s; owned process tree terminated; retained streams: $Log"
    }
    if ($process.ExitCode -ne 0) { throw "Child failed exit=$($process.ExitCode); retained streams: $Log" }
    $jitText = if ($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)) { [IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile) } else { '' }
    return @{ stdout = $outText; stderr = $errText; jit = $jitText; exitCode = $process.ExitCode }
}

$outputs = @{}
foreach ($project in 'Host', 'Payload', 'Refusal', 'Boxed') {
    $outputs[$project] = Join-Path $EvidenceDirectory $project.ToLowerInvariant()
    Invoke-Child $SdkDotnet @('build', (Join-Path $sourceRoot "$project/$project.csproj"), '-c', 'Release',
        '--output', $outputs[$project]) @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
}
$probeHost = Join-Path $outputs.Host 'SelectionProbe.Host.dll'
$managedBefore = [ordered]@{}
foreach ($directory in $outputs.Values) {
    foreach ($file in Get-ChildItem $directory -File) { $managedBefore[$file.FullName] = (Get-FileHash $file.FullName).Hash }
}
$common = @{ DOTNET_InterpMode = '0'; DOTNET_ReadyToRun = '1'; DOTNET_TieredCompilation = '1';
    DOTNET_InterpList = '1'; DOTNET_InterpDump = '*:*'; DOTNET_JitDisasmSummary = '1'; DOTNET_JitNoInline = '0';
    DOTNET_MULTILEVEL_LOOKUP = '0'; DOTNET_RuneCLRInterpretCollectible = '0' }
$refuseMethods = 'SelectionUGC.Refusal.Entry:Reject'
[ordered]@{ runtimeBase = $base; candidateCommit = $head; runtimeRepo = $RuntimeRepo;
    runtimeLayout = $RuntimeLayout; builtProduct = $BuiltProduct; runtimeSourceStamp = $stamp;
    runtimeHashes = $runtimeHashes; normalSettings = $common; refusalMethodset = $refuseMethods;
    sdk = $SdkDotnet; startedUtc = [DateTime]::UtcNow.ToString('o');
    limitation = 'collectible metadata IL fixture; no submitted R2R payload/native method-entry trace'
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'request.json')

$lanes = [ordered]@{}
foreach ($lane in 'required', 'ordinary', 'required-refusal', 'unmarked-fallback', 'required-boxed') {
    $settings = $common.Clone()
    $settings.RUNECLR_PROBE_FACTORY = if ($lane -in 'ordinary', 'unmarked-fallback') { 'ordinary' } else { 'required' }
    $settings.DOTNET_JitStdOutFile = Join-Path $EvidenceDirectory "$lane.log.jit"
    if ($lane -eq 'ordinary') { $settings.DOTNET_RuneCLRInterpretCollectible = '0' }
    if ($lane -in 'required-refusal', 'unmarked-fallback') { $settings.DOTNET_RuneCLRInterpreterRefuseMethods = $refuseMethods }
    if ($lane -eq 'unmarked-fallback') { $settings.DOTNET_InterpMode = '1' }
    $arguments = @('exec', '--fx-version', '12.0.0', $probeHost, $outputs.Payload, (Join-Path $EvidenceDirectory $lane))
    if ($lane -eq 'required-refusal') { $arguments += @('--refusal-required', $outputs.Refusal) }
    if ($lane -eq 'unmarked-fallback') { $arguments += @('--refusal-fallback', $outputs.Refusal) }
    if ($lane -eq 'required-boxed') { $arguments += @('--bridges', $outputs.Boxed) }
    $lanes[$lane] = @{ settings = $settings; arguments = $arguments }
    $lanes | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'lanes.json')
    $result = Invoke-Child $privateDotnet $arguments $settings (Join-Path $EvidenceDirectory "$lane.log")
    if ($result.stderr -notmatch 'POLICY API version=1' -or $result.stderr -notmatch 'immutable-api=true') { throw "Session policy API acknowledgement missing: $lane" }
    $expectedRetired = if ($lane -eq 'unmarked-fallback') { 0 } elseif ($lane -eq 'required-refusal') { 21 } else { 20 }
    if (([regex]::Matches($result.stderr, '(?m)^RETIRED query=System.InvalidOperationException protected=true')).Count -ne $expectedRetired) {
        throw "Post-unload policy query guard incomplete: $lane"
    }
    if ($lane -in 'required-refusal', 'unmarked-fallback') {
        if ($result.stdout -notmatch 'RuneCLRInterpreterRefusal: SelectionUGC.Refusal.Entry:Reject CORJIT_SKIPPED') {
            throw "Scoped actual compiler-skip diagnostic missing: $lane"
        }
    }
    if ($lane -eq 'unmarked-fallback') {
        if ($result.stderr -notmatch 'PASS unmarked-refusal value=73 module=.* token=0x06000001' -or
            $result.jit -notmatch 'JIT compiled[^\r\n]*SelectionUGC.Refusal.Entry:Reject') { throw 'Unmarked actual fallback/value evidence missing.' }
        continue
    }
    if ($lane -eq 'required-boxed') {
        if ($result.stderr -notmatch '20/20 boxed bridge sessions passed; 20/20 contexts collected' -or
            ([regex]::Matches($result.stderr, '(?m)^PASS bridge-session=[0-9]+ ')).Count -ne 20 -or
            $result.jit -notmatch 'JIT compiled[^\r\n]*Program:[^\r\n]*BoxedFrame' -or
            $result.jit -match 'JIT compiled[^\r\n]*SelectionUGC') { throw 'Boxed body/native host/collection evidence incomplete.' }
        $boxedGroups = @($result.stdout -split '\r?\n' | Where-Object { $_.StartsWith('Compiled method: ') -and $_.Contains('SelectionUGC.Boxed.Entry:') } | Group-Object)
        if ($boxedGroups.Count -ne 5 -or @($boxedGroups | Where-Object Count -ne 20).Count -ne 0) { throw 'Boxed method-body bytecode groups differ from5x20.' }
        continue
    }
    if ($result.stderr -notmatch '20/20 execution-selection sessions passed; 20/20 contexts collected' -or
        ([regex]::Matches($result.stderr, '(?m)^PASS session=[0-9]+ ')).Count -ne 20 -or
        ([regex]::Matches($result.stderr, '(?m)^LATE private=absent ')).Count -ne 20 -or
        ([regex]::Matches($result.stderr, '(?m)^LATE private=loaded ')).Count -ne 20) { throw "Functional/collection result incomplete: $lane" }
    if ($lane -eq 'ordinary') {
        if ($result.jit -notmatch 'JIT compiled[^\r\n]*SelectionUGC.Payload.Entry:Run' -or
            $result.stdout -match 'Compiled method: [^\r\n]*SelectionUGC') { throw 'Switch-off UGC native control incomplete.' }
        continue
    }
    if ($result.jit -match 'JIT compiled[^\r\n]*SelectionUGC' -or
        $result.jit -notmatch 'JIT compiled[^\r\n]*Program:[^\r\n]*RunFrame') { throw "Required UGC fallback or missing native host evidence: $lane" }
    $groups = @($result.stdout -split '\r?\n' | Where-Object { $_.StartsWith('Compiled method: ') -and $_.Contains('SelectionUGC.') } | Group-Object)
    if ($groups.Count -ne 26 -or @($groups | Where-Object Count -ne 20).Count -ne 0) { throw "Required bytecode groups differ from26x20: $lane" }
    if ($lane -eq 'required-refusal' -and $result.stderr -notmatch 'PASS required-refusal exception=System.NotSupportedException collected=true') {
        throw 'Required refusal/recovery evidence incomplete.'
    }
}
foreach ($file in $managedBefore.Keys) { if ((Get-FileHash $file).Hash -ne $managedBefore[$file]) { throw "Managed bytes changed between lanes: $file" } }
$inventoryHash = (Get-FileHash (Join-Path $EvidenceDirectory 'required/method-inventory.json')).Hash
foreach ($lane in 'ordinary', 'required-refusal') {
    if ((Get-FileHash (Join-Path $EvidenceDirectory "$lane/method-inventory.json")).Hash -ne $inventoryHash) { throw "Metadata inventory changed: $lane" }
}
[ordered]@{ passed = $true; candidateCommit = $head; requiredSessions = 20; requiredContextsCollected = 20;
    policyVersion = 1; diagnosticCollectibleSwitch = 0; immutableFactoryPolicy = $true;
    unloadedQueryGuard = 'InvalidOperationException;20pernormal/boxedlane,21refusal+recovery,0defaultload';
    successfulBytecodeGroups = 26; successfulBytecodeDumpsEachRequiredLane = 520; hostJitPositive = $true;
    ordinaryUgcJitPositive = $true; refusal = 'NotSupportedException, context collected, next20normalcontexts pass';
    unmarkedFallback = 'same refusal DLL returns73 and Reject native JIT observed';
    boxedBridge = '20contexts; cold/warm interface plus closed delegate on boxed struct;5bodygroupsx20';
    managedBytesUnchanged = $true; matchingInventoryHash = $inventoryHash; managedHashes = $managedBefore;
    runtimeHashes = $runtimeHashes; methodNativeEntryProof = 'not collected'; finishedUtc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
Write-Host 'PASS required20/20; bytecode26x20; hostJITpositive; ordinaryUGCJITpositive; required-refusal/collection/recovery PASS; unmarked fallback73/JIT PASS'
Write-Host "Evidence: $EvidenceDirectory"

