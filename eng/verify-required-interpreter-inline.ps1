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
if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Explicit committed clean candidate required.' }
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
& git -C $RuntimeRepo merge-base --is-ancestor $base $head
if ($LASTEXITCODE) { throw 'Candidate source ancestry mismatch.' }
$framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'
$privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
$runtimeHashes = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
    if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Build/layout mismatch: $name" }
}
$stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$stamp.Contains($head)) { throw 'Candidate native source stamp mismatch.' }
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $repo ("artifacts/execution-selection/inline-{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N')) }
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be new.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot = Join-Path $PSScriptRoot 'execution-selection-probe'
foreach ($source in Get-ChildItem $sourceRoot -File -Recurse | Where-Object { $_.Extension -in '.cs', '.csproj' -and $_.FullName -notmatch '[\/]obj[\/]|[\/]bin[\/]' }) {
    $destination = Join-Path $EvidenceDirectory ('source/' + $source.FullName.Substring($sourceRoot.Length + 1))
    New-Item -ItemType Directory (Split-Path $destination) -Force | Out-Null
    Copy-Item $source.FullName $destination
}
function Invoke-Child([string] $Executable, [string[]] $Arguments, [hashtable] $Settings, [string] $Log) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true; $info.WorkingDirectory = $repo
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($key in @($info.Environment.Keys)) { if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_')) { $info.Environment.Remove($key) | Out-Null } }
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $outText = $stdout.GetAwaiter().GetResult(); $errText = $stderr.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($Log + '.stdout', $outText); [IO.File]::WriteAllText($Log + '.stderr', $errText)
    if ($process.ExitCode) { throw "Child failed exit=$($process.ExitCode); retained streams $Log" }
    $jitText = if ($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)) { [IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile) } else { '' }
    return @{ stdout = $outText; stderr = $errText; jit = $jitText }
}
$outputs = @{}
foreach ($project in 'Host', 'Inline') {
    $outputs[$project] = Join-Path $EvidenceDirectory $project.ToLowerInvariant()
    Invoke-Child $SdkDotnet @('build', (Join-Path $sourceRoot "$project/$project.csproj"), '-c', 'Release', '--output', $outputs[$project]) @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
}
$managed = [ordered]@{}
foreach ($directory in $outputs.Values) { foreach ($file in Get-ChildItem $directory -File) { $managed[$file.FullName] = (Get-FileHash $file.FullName).Hash } }
$settings = @{ DOTNET_InterpMode = '0'; DOTNET_ReadyToRun = '1'; DOTNET_TieredCompilation = '0';
    DOTNET_JitNoInline = '0'; DOTNET_JitDisasmSummary = '1'; DOTNET_InterpDump = '*:*'; DOTNET_InterpList = '1';
    DOTNET_JitDump = 'TrustedInlineCaller:NativeInlineCall'; DOTNET_JitPrintInlinedMethods = 'TrustedInlineCaller:NativeInlineCall';
    DOTNET_RuneCLRInterpretCollectible = '0'; DOTNET_MULTILEVEL_LOOKUP = '0' }
[ordered]@{ candidateCommit = $head; runtimeBase = $base; runtimeLayout = $RuntimeLayout; runtimeHashes = $runtimeHashes;
    sourceStamp = $stamp; settings = $settings; observation = 'native generic trusted definition with concrete collectible struct argument';
    limitation = 'JIT inline diagnostics, functional values and bytecode preparation; not native interpreter entry tracing'
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
$laneResults = [ordered]@{}
foreach ($lane in 'switch-off', 'required') {
    $laneSettings = $settings.Clone()
    $laneSettings.DOTNET_JitStdOutFile = Join-Path $EvidenceDirectory "$lane.log.jit"
    if ($lane -eq 'required') { $laneSettings.DOTNET_RuneCLRInterpretCollectible = '1' }
    $arguments = @('exec', '--fx-version', '12.0.0', (Join-Path $outputs.Host 'SelectionProbe.Host.dll'),
        $outputs.Inline, (Join-Path $EvidenceDirectory $lane), '--inline', $outputs.Inline)
    $result = Invoke-Child $privateDotnet $arguments $laneSettings (Join-Path $EvidenceDirectory "$lane.log")
    if ($result.stderr -notmatch '20/20 native generic caller sessions passed; 20/20 contexts collected' -or
        ([regex]::Matches($result.stderr, '(?m)^PASS inline-session=[0-9]+ ')).Count -ne 20) { throw "Inline values/collection missing: $lane" }
    if ($result.jit -notmatch 'JIT compiled\s+TrustedInlineCaller:NativeInlineCall\[SelectionUGC.Inline.Entry\]') { throw "Trusted concrete generic caller native JIT missing: $lane" }
    $successes = @($result.jit -split '\r?\n' | Where-Object { $_ -match "INLINER:.*result 'SUCCESS'.*for 'TrustedInlineCaller:NativeInlineCall.*calling 'SelectionUGC.Inline.Entry:ReadInline" })
    if ($lane -eq 'switch-off') {
        if ($successes.Count -ne 20) { throw "Actual JIT inline positive incomplete: $($successes.Count) expected20" }
        if ($result.stdout -match 'Compiled method: [^\r\n]*SelectionUGC.Inline.Entry:ReadInline') { throw 'Switch-off body unexpectedly interpreted.' }
    } else {
        # Signature arguments may name SelectionUGC even for a trusted owner.
        # Classify definition owner, not arbitrary text anywhere in the line.
        if ($result.jit -match 'JIT compiled\s+\.?SelectionUGC\.' -or $successes.Count) { throw 'Required body compiled natively or entered successful native inline.' }
        $dumps = [regex]::Matches($result.stdout, 'Compiled method: [^\r\n]*SelectionUGC.Inline.Entry:ReadInline').Count
        if ($dumps -ne 20) { throw "Required inlinee bytecode count=$dumps expected20" }
        $rejections = @($result.jit -split '\r?\n' | Where-Object { $_ -match "INLINER:.*result 'failed this callee' reason 'noinline per IL/cached result'.*for 'TrustedInlineCaller:NativeInlineCall.*calling 'SelectionUGC.Inline.Entry:ReadInline" })
        if ($rejections.Count -lt 20) { throw 'Required concrete inlinee rejection diagnostic incomplete.' }
    }
    $laneResults[$lane] = @{ sessions = 20; collected = 20; inlineSuccesses = $successes.Count; settings = $laneSettings }
}
foreach ($file in $managed.Keys) { if ((Get-FileHash $file).Hash -ne $managed[$file]) { throw "Managed bytes changed: $file" } }
if ((Get-FileHash (Join-Path $EvidenceDirectory 'switch-off/method-inventory.json')).Hash -ne
    (Get-FileHash (Join-Path $EvidenceDirectory 'required/method-inventory.json')).Hash) { throw 'Inline metadata identity mismatch between lanes.' }
[ordered]@{ passed = $true; candidateCommit = $head; lanes = $laneResults; matchingManagedHashes = $managed; runtimeHashes = $runtimeHashes;
    interpretationEvidence = '20 required bytecode dumps and functional values; no native-entry trace';
    inlineEvidence = '20 actual off-lane SUCCESS decisions versus required rejection diagnostics; trusted definition remains native'
} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
Write-Host 'PASS native generic caller20/20 each; actual inline20positive switch-off; required20bytecode with inline rejection; contexts20/20 each'
Write-Host "Evidence: $EvidenceDirectory"
