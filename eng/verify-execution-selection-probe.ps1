param(
    [string] $RuntimeRepo = 'E:/runtime',
    [string] $SdkDotnet,
    [string] $EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$SdkDotnet) { $SdkDotnet = Join-Path $repo 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe' }
$SdkDotnet = (Resolve-Path $SdkDotnet).Path
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$expectedBase = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
$base = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
if ($base -ne $expectedBase -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) {
    throw 'Probe baseline requires the pinned tracked-clean runtime checkout.'
}
$layout = Join-Path $RuntimeRepo 'artifacts/bin/testhost/net11.0-windows-Release-x64'
$framework = Join-Path $layout 'shared/Microsoft.NETCore.App/12.0.0'
$privateDotnet = Join-Path $layout 'dotnet.exe'
$hashes = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'System.Private.CoreLib.dll') {
    $deployed = Join-Path $framework $name
    $built = Join-Path $RuntimeRepo "artifacts/bin/coreclr/windows.x64.Checked/$name"
    $hashes[$name] = (Get-FileHash $deployed).Hash
    if ($hashes[$name] -ne (Get-FileHash $built).Hash) { throw "Checked build/layout mismatch: $name" }
}
$stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$stamp.Contains($base)) { throw 'Source stamp mismatch.' }
if (!$EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $repo ("artifacts/execution-selection/{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N'))
}
if (Test-Path $EvidenceDirectory) { throw 'Evidence directory must be new; preserve earlier failures.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item (Join-Path $PSScriptRoot 'execution-selection-probe') (Join-Path $EvidenceDirectory 'source') -Recurse
Get-ChildItem (Join-Path $EvidenceDirectory 'source') -Directory -Recurse | Where-Object { $_.Name -in 'bin', 'obj' } | ForEach-Object {
    # Snapshot only source inputs; keep all earlier evidence/build outputs.
    $target = [IO.Path]::GetFullPath($_.FullName)
    if (!$target.StartsWith((Join-Path $EvidenceDirectory 'source') + [IO.Path]::DirectorySeparatorChar)) { throw 'Unexpected snapshot path.' }
    Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')

function Invoke-Child([string] $Executable, [string[]] $Arguments, [hashtable] $Settings, [string] $Log) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.WorkingDirectory = $repo
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    # Clear inherited runtime test switches only in this child's environment.
    foreach ($key in @($info.Environment.Keys)) {
        if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_')) { $info.Environment.Remove($key) | Out-Null }
    }
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $outText = $stdout.GetAwaiter().GetResult()
    $errText = $stderr.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($Log + '.stdout', $outText)
    [IO.File]::WriteAllText($Log + '.stderr', $errText)
    $text = $outText + $errText
    [IO.File]::WriteAllText($Log, $text)
    if ($process.ExitCode -ne 0) { throw "Child failed exit=$($process.ExitCode); retained log $Log" }
    return $text
}

$hostDirectory = Join-Path $EvidenceDirectory 'host'
$payloadDirectory = Join-Path $EvidenceDirectory 'payload'
foreach ($project in 'Host', 'Payload') {
    $output = if ($project -eq 'Host') { $hostDirectory } else { $payloadDirectory }
    Invoke-Child $SdkDotnet @('build', (Join-Path $PSScriptRoot "execution-selection-probe/$project/$project.csproj"),
        '-c', 'Release', '--output', $output) @{} (Join-Path $EvidenceDirectory "build-$project.log") | Out-Null
}
$probeHost = Join-Path $hostDirectory 'SelectionProbe.Host.dll'
$settings = @{ DOTNET_InterpMode = '1'; DOTNET_ReadyToRun = '0'; DOTNET_TieredCompilation = '0';
    DOTNET_InterpList = '1'; DOTNET_InterpDump = '*:*'; DOTNET_JitDisasmSummary = '1';
    DOTNET_JitNoInline = '0'; DOTNET_MULTILEVEL_LOOKUP = '0' }
[ordered]@{ runtimeBase = $base; runtimePatch = 'none'; runtimeLayout = $layout;
    runtimeSourceStamp = $stamp; runtimeHashes = $hashes; settings = $settings;
    sdk = $SdkDotnet; startedUtc = [DateTime]::UtcNow.ToString('o');
    fixtureScope = 'trusted experimental IL; not production managed-il-gameplay-v1';
    coverageLimit = 'compiled bytecode plus functional invocation; no per-method native entry trace'
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'request.json')

$controlSettings = @{ DOTNET_JitDisasmSummary = '1'; DOTNET_TieredCompilation = '0'; DOTNET_JitNoInline = '0' }
$control = Invoke-Child $SdkDotnet @($probeHost, $payloadDirectory, (Join-Path $EvidenceDirectory 'control')) $controlSettings (Join-Path $EvidenceDirectory 'control.log')
$interpreted = Invoke-Child $privateDotnet @('exec', '--fx-version', '12.0.0', $probeHost, $payloadDirectory,
    (Join-Path $EvidenceDirectory 'mode1')) $settings (Join-Path $EvidenceDirectory 'mode1.log')
foreach ($text in $control, $interpreted) {
    if ($text -notmatch '20/20 execution-selection sessions passed; 20/20 contexts collected') { throw 'Functional or collection result missing.' }
}
if ($interpreted -match 'JIT compiled[^\r\n]*SelectionUGC') { throw 'Reported UGC JIT fallback detected.' }
if ($control -notmatch 'JIT compiled[^\r\n]*SelectionUGC.Payload.Entry:Run') { throw 'JIT control observation channel not established.' }
# Evidence requirements are kept beside the inventory, allowing future native
# entry tracing to bind exact MethodDef tokens and constructed generic methods.
$requirements = @(
    'SelectionUGC.Payload.Entry:.ctor', 'SelectionUGC.Payload.Entry:.cctor',
    'SelectionUGC.Payload.Entry:Run', 'SelectionUGC.Payload.Entry:get_Value',
    'SelectionUGC.Payload.VirtualBase:.ctor', 'SelectionUGC.Payload.Entry\+[^\r\n]*:.ctor',
    'SelectionUGC.Payload.Entry:InlineAdd', 'SelectionUGC.Payload.Entry:VirtualRead',
    'SelectionUGC.Payload.Entry:Accept', 'SelectionUGC.Payload.IDefaultProbe:DefaultRead',
    'SelectionUGC.Payload.GenericState[^\r\n]*:.cctor', 'SelectionUGC.Payload.GenericState[^\r\n]*:Next',
    'SelectionUGC.Payload.GenericState[^\r\n]*:Identity', 'SelectionUGC.Payload.Entry[^\r\n]*:<Run>',
    'SelectionUGC.Private.PrivateState:.ctor', 'SelectionUGC.Private.PrivateState:.cctor',
    'SelectionUGC.Private.PrivateState:get_Value', 'SelectionUGC.Private.PrivateState:InlineAdd',
    'SelectionUGC.Private.PrivateState:get_Starts', 'SelectionUGC.Private.PrivateState:get_Instances',
    'SelectionUGC.Private.PrivateState\+[^\r\n]*:.ctor',
    'SelectionUGC.Private.PrivateState:MakeDelegate', 'SelectionUGC.Private.PrivateState[^\r\n]*:<MakeDelegate>',
    'SelectionUGC.Private.PrivateGeneric[^\r\n]*:.cctor', 'SelectionUGC.Private.PrivateGeneric[^\r\n]*:Next',
    'SelectionUGC.Private.PrivateGeneric[^\r\n]*:Identity'
)
foreach ($requirement in $requirements) {
    $count = [regex]::Matches($interpreted, 'Compiled method: [^\r\n]*' + $requirement).Count
    if ($count -ne 20) {
        throw "Successful interpreter bytecode dumps incomplete: $requirement; count=$count expected=20"
    }
}
$fixtureHashes = [ordered]@{}
foreach ($file in Get-ChildItem $hostDirectory, $payloadDirectory -File) {
    $fixtureHashes[$file.FullName.Substring($EvidenceDirectory.Length + 1)] = (Get-FileHash $file.FullName).Hash
}
[ordered]@{ passed = $true; controlSessions = 20; mode1Sessions = 20; collectedEachLane = 20;
    successfulBytecodeRequirements = $requirements.Count; reportedUGCJitFallback = $false;
    successfulBytecodeDumps = $requirements.Count * 20; jitControlObserved = $true;
    blanketNoInlineDisabled = $true; methodEntryProof = 'not collected'; fixtureHashes = $fixtureHashes;
    runtimeHashes = $hashes; finishedUtc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
Write-Host "PASS control20/20; mode1 20/20; contexts20/20 each; bytecode$($requirements.Count)/$($requirements.Count); reportedUGCJIT=0"
Write-Host "Evidence: $EvidenceDirectory"
