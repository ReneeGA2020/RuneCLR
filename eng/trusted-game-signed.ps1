param(
    [string]$OutputRoot,
    [ValidateSet('Release', 'Debug')]
    [string]$Configuration = 'Release'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$sampleOnWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $OutputRoot = Join-Path $repo ('artifacts/trusted-game-signed/' + $stamp + '-' + [guid]::NewGuid().ToString('n'))
}
$dotnet = (Get-Command dotnet -ErrorAction Stop).Source
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLowerInvariant()
if ($architecture -eq 'amd64') {
    $architecture = 'x64'
}
if ($architecture -notin @('x64', 'x86', 'arm64', 'arm')) {
    $architecture = 'unknown'
}
$powerShellExe = if ($PSVersionTable.PSEdition -eq 'Core') {
    Join-Path $PSHOME $(if ($sampleOnWindows) { 'pwsh.exe' } else { 'pwsh' })
} else {
    Join-Path $PSHOME 'powershell.exe'
}
if (-not (Test-Path -LiteralPath $powerShellExe)) {
    $powerShellExe = (Get-Process -Id $PID).Path
}
if ([string]::IsNullOrWhiteSpace($powerShellExe)) {
    throw 'Cannot locate a current PowerShell executable for the local regression.'
}

$hostProject = Join-Path $repo 'samples/TrustedGame.Host/TrustedGame.Host.csproj'
$publisherProject = Join-Path $repo 'samples/TrustedGame.Publisher/TrustedGame.Publisher.csproj'
$updateProject = Join-Path $repo 'samples/TrustedGame.Update/TrustedGame.Update.csproj'
$updateV2Project = Join-Path $repo 'samples/TrustedGame.UpdateV2/TrustedGame.UpdateV2.csproj'
$output = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $output) {
    throw "OutputRoot must be a new path: $output"
}
Write-Host "trusted-game-signed: output=$output"
$logs = Join-Path $output 'logs'
$buildRoot = Join-Path $output 'build'
$publisherRoot = Join-Path $output 'publisher'
$sourceA = Join-Path $publisherRoot 'source-a'
$sourceInvalid = Join-Path $publisherRoot 'source-invalid'
$sourceB = Join-Path $publisherRoot 'source-b'
$keyDir = Join-Path $publisherRoot 'keys'
$privateKey = Join-Path $keyDir 'demo-private.pem'
$spki = Join-Path $keyDir 'host.spki'
$signedA = Join-Path $publisherRoot 'A.signed.json'
$signedInvalid = Join-Path $publisherRoot 'InvalidEntry.signed.json'
$signedB = Join-Path $publisherRoot 'B.signed.json'
$tamperedA = Join-Path $publisherRoot 'A.tampered.signed.json'
$tamperedB = Join-Path $publisherRoot 'B.tampered.signed.json'
$releases = Join-Path $output 'releases'
$state = Join-Path $output 'state'
$receipt = Join-Path $state 'receipt.json'

New-Item -ItemType Directory -Force -Path $logs, $buildRoot, $publisherRoot, $sourceA, $sourceInvalid, $sourceB, $keyDir, $releases, $state | Out-Null

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $stdout = Join-Path $logs ($Name + '.stdout')
    $stderr = Join-Path $logs ($Name + '.stderr')
    & $Exe @Arguments > $stdout 2> $stderr
    $code = $LASTEXITCODE
    Write-Host "$Name exit=$code"
    if (Test-Path -LiteralPath $stdout) {
        Get-Content -LiteralPath $stdout | ForEach-Object { Write-Host $_ }
    }
    if (Test-Path -LiteralPath $stderr) {
        Get-Content -LiteralPath $stderr | ForEach-Object { Write-Host $_ }
    }
    return $code
}

function Invoke-Logged {
    param([Parameter(Mandatory = $true)][string]$Name,
          [Parameter(Mandatory = $true)][string[]]$Arguments)
    return Invoke-LoggedCommand -Name $Name -Exe $dotnet -Arguments $Arguments
}

function Require {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Read-Text {
    param([string]$Path)
    return [IO.File]::ReadAllText($Path)
}

function Find-One {
    param([string]$Root, [string]$Name)
    $bin = Join-Path $Root 'bin'
    $hits = @(Get-ChildItem -LiteralPath $bin -Recurse -File -Filter $Name)
    Require ($hits.Count -eq 1) "Expected one $Name under $Root, got $($hits.Count)"
    return $hits[0].FullName
}

function Find-ProjectDll {
    param([string]$Root, [string]$Project, [string]$Name)
    $bin = Join-Path (Join-Path $Root 'bin') $Project
    $hits = @(Get-ChildItem -LiteralPath $bin -Recurse -File -Filter $Name)
    Require ($hits.Count -eq 1) "Expected one $Name under $bin, got $($hits.Count)"
    return $hits[0].FullName
}

try {
    $hostCode = Invoke-Logged 'build-host' @('build', $hostProject, '-c', $Configuration, '--artifacts-path', $buildRoot, '--nologo')
    Require ($hostCode -eq 0) 'Host build failed'
    $hostDll = Find-One $buildRoot 'TrustedGame.Host.dll'
    $hostDirectory = Split-Path -Parent $hostDll
    $residentNames = @('TrustedGame.Host.dll', 'TrustedGame.Contracts.dll', 'RuneCLR.TrustedUpdate.dll')
    $residentBefore = @{}
    foreach ($name in $residentNames) {
        $path = Join-Path $hostDirectory $name
        Require (Test-Path -LiteralPath $path) ('Resident missing: ' + $name)
        $residentBefore[$name] = [ordered]@{
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            timestamp = (Get-Item -LiteralPath $path).LastWriteTimeUtc
        }
    }
    $hostDeps = Join-Path $hostDirectory 'TrustedGame.Host.deps.json'
    Require (Test-Path -LiteralPath $hostDeps) 'Host deps missing'
    Require (-not (Read-Text $hostDeps).Contains('TrustedGame.Update')) 'Host deps contains Update'

    $publisherCode = Invoke-Logged 'build-publisher' @('build', $publisherProject, '-c', $Configuration, '--artifacts-path', $buildRoot, '--nologo', '-p:BuildProjectReferences=false')
    Require ($publisherCode -eq 0) 'Publisher build failed'
    $publisherDll = Find-One $buildRoot 'TrustedGame.Publisher.dll'

    $updateCode = Invoke-Logged 'build-update-a' @('build', $updateProject, '-c', $Configuration, '--artifacts-path', $buildRoot, '--nologo', '-p:BuildProjectReferences=false')
    Require ($updateCode -eq 0) 'Update A build failed'
    $updateDll = Find-ProjectDll $buildRoot 'TrustedGame.Update' 'TrustedGame.Update.dll'

    $updateV2Code = Invoke-Logged 'build-update-b' @('build', $updateV2Project, '-c', $Configuration, '--artifacts-path', $buildRoot, '--nologo', '-p:BuildProjectReferences=false')
    Require ($updateV2Code -eq 0) 'Update B build failed'
    $updateV2Dll = Find-ProjectDll $buildRoot 'TrustedGame.UpdateV2' 'TrustedGame.Update.dll'

    $residentAfter = @{}
    foreach ($name in $residentNames) {
        $path = Join-Path $hostDirectory $name
        $residentAfter[$name] = [ordered]@{
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            timestamp = (Get-Item -LiteralPath $path).LastWriteTimeUtc
        }
    }
    foreach ($name in $residentNames) {
        Require ($residentBefore[$name].sha256 -eq $residentAfter[$name].sha256) ('Resident hash changed: ' + $name)
        Require ($residentBefore[$name].timestamp -eq $residentAfter[$name].timestamp) ('Resident timestamp changed: ' + $name)
    }
    Require (-not (Test-Path -LiteralPath (Join-Path $hostDirectory 'TrustedGame.Update.dll'))) 'Host output contains Update'

    $updateAHash = (Get-FileHash -LiteralPath $updateDll -Algorithm SHA256).Hash
    $updateBHash = (Get-FileHash -LiteralPath $updateV2Dll -Algorithm SHA256).Hash
    Require ($updateAHash -ne $updateBHash) 'A and B module hashes are identical'
    $assemblyA = [Reflection.AssemblyName]::GetAssemblyName($updateDll).FullName
    $assemblyB = [Reflection.AssemblyName]::GetAssemblyName($updateV2Dll).FullName
    Require ($assemblyA -eq $assemblyB) 'A and B assembly full identities differ'
    Write-Host "trusted-game-signed: assembly=$assemblyA updateA=$updateAHash updateB=$updateBHash"

    Copy-Item -LiteralPath $updateDll -Destination (Join-Path $sourceA 'TrustedGame.Update.dll') -Force
    Copy-Item -LiteralPath $updateDll -Destination (Join-Path $sourceInvalid 'TrustedGame.Update.dll') -Force
    Copy-Item -LiteralPath $updateV2Dll -Destination (Join-Path $sourceB 'TrustedGame.Update.dll') -Force

    $publishA = Invoke-Logged 'publish-a' @($publisherDll, '--module', (Join-Path $sourceA 'TrustedGame.Update.dll'), '--version', 'game-rules-a', '--entry-type', 'TrustedGame.Update.GameRules', '--entry-method', 'Entry', '--runtime', 'net11.0', '--architecture', $architecture, '--signed', $signedA, '--spki', $spki, '--private-key', $privateKey)
    Require ($publishA -eq 0) 'Signed A publication failed'
    $publishInvalid = Invoke-Logged 'publish-invalid-entry' @($publisherDll, '--module', (Join-Path $sourceInvalid 'TrustedGame.Update.dll'), '--version', 'game-rules-invalid', '--entry-type', 'TrustedGame.Update.MissingRules', '--entry-method', 'Entry', '--runtime', 'net11.0', '--architecture', $architecture, '--signed', $signedInvalid, '--spki', $spki, '--private-key', $privateKey)
    Require ($publishInvalid -eq 0) 'Signed invalid-entry publication failed'
    $publishB = Invoke-Logged 'publish-b' @($publisherDll, '--module', (Join-Path $sourceB 'TrustedGame.Update.dll'), '--version', 'game-rules-b', '--entry-type', 'TrustedGame.Update.GameRules', '--entry-method', 'Entry', '--runtime', 'net11.0', '--architecture', $architecture, '--signed', $signedB, '--spki', $spki, '--private-key', $privateKey)
    Require ($publishB -eq 0) 'Signed B publication failed'
    Require (Test-Path -LiteralPath $spki) 'Host SPKI missing'

    $stageA = Invoke-Logged 'stage-a' @($hostDll, '--stage-signed', $sourceA, '--signed', $signedA, '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt)
    Require ($stageA -eq 0) 'Signed A stage failed'
    $stageAText = Read-Text (Join-Path $logs 'stage-a.stdout')
    foreach ($needle in @('stage=OK', 'activated=True', 'source=Candidate', 'version=game-rules-a', 'expectedScoreMultiplier=1', 'results=1,3,6 score=6 ticks=3 multiplier=1', 'persistence=None', 'activatorCalls=1', 'TRUSTED-GAME OK')) {
        Require ($stageAText.Contains($needle)) ('Signed A output missing ' + $needle)
    }
    Require (Test-Path -LiteralPath $receipt) 'Receipt not written by A stage'
    $receiptAHash = (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash

    $recoverA = Invoke-Logged 'recover-a' @($hostDll, '--recover-signed', '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt)
    Require ($recoverA -eq 0) 'A recovery failed'
    $recoverAText = Read-Text (Join-Path $logs 'recover-a.stdout')
    foreach ($needle in @('activated=True', 'source=LastKnownGood', 'version=game-rules-a', 'results=1,3,6 score=6 ticks=3 multiplier=1', 'persistence=None', 'TRUSTED-GAME OK')) {
        Require ($recoverAText.Contains($needle)) ('A recovery output missing ' + $needle)
    }
    Require ($receiptAHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed during A recovery'

    $signedAText = Read-Text $signedA
    $tamperedAText = $signedAText.Replace('"version":"game-rules-a"', '"version":"game-rules-x"')
    Require ($tamperedAText -ne $signedAText) 'Could not tamper signed A payload'
    [IO.File]::WriteAllText($tamperedA, $tamperedAText, [Text.UTF8Encoding]::new($false))
    $stageTamperedA = Invoke-Logged 'stage-tampered-a' @($hostDll, '--stage-signed', $sourceA, '--signed', $tamperedA, '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt)
    Require ($stageTamperedA -eq 0) 'Tampered A did not fall back to authenticated A'
    $tamperedATextOut = Read-Text (Join-Path $logs 'stage-tampered-a.stdout')
    foreach ($needle in @('stage=VerificationFailed', 'activated=True', 'source=LastKnownGood', 'version=game-rules-a', 'results=1,3,6 score=6 ticks=3 multiplier=1', 'persistence=None', 'TRUSTED-GAME OK')) {
        Require ($tamperedATextOut.Contains($needle)) ('Tampered A fallback output missing ' + $needle)
    }
    Require ($receiptAHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed during tampered A fallback'

    $stageInvalid = Invoke-Logged 'stage-invalid-entry' @($hostDll, '--stage-signed', $sourceInvalid, '--signed', $signedInvalid, '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt)
    Require ($stageInvalid -eq 3) 'Invalid entry did not fail activation'
    $stageInvalidText = Read-Text (Join-Path $logs 'stage-invalid-entry.stdout')
    foreach ($needle in @('stage=OK', 'activated=False', 'candidateActivation=ActivationFailed', 'activatorCalls=1')) {
        Require ($stageInvalidText.Contains($needle)) ('Invalid entry output missing ' + $needle)
    }
    Require (-not $stageInvalidText.Contains('source=LastKnownGood')) 'Invalid entry fell back in the same process'
    Require ($receiptAHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed after invalid entry'

    $recoverAAfterInvalid = Invoke-Logged 'recover-a-after-invalid' @($hostDll, '--recover-signed', '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt)
    Require ($recoverAAfterInvalid -eq 0) 'A recovery after invalid entry failed'
    $recoverAAfterInvalidText = Read-Text (Join-Path $logs 'recover-a-after-invalid.stdout')
    foreach ($needle in @('activated=True', 'source=LastKnownGood', 'version=game-rules-a', 'results=1,3,6 score=6 ticks=3 multiplier=1', 'TRUSTED-GAME OK')) {
        Require ($recoverAAfterInvalidText.Contains($needle)) ('A after invalid output missing ' + $needle)
    }
    Require ($receiptAHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed after A recovery following invalid entry'

    $stageB = Invoke-Logged 'stage-b' @($hostDll, '--stage-signed', $sourceB, '--signed', $signedB, '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt, '--expected-score-multiplier', '2')
    Require ($stageB -eq 0) 'Signed B stage failed'
    $stageBText = Read-Text (Join-Path $logs 'stage-b.stdout')
    foreach ($needle in @('stage=OK', 'activated=True', 'source=Candidate', 'version=game-rules-b', 'expectedScoreMultiplier=2', 'results=2,6,12 score=12 ticks=3 multiplier=2', 'persistence=None', 'TRUSTED-GAME OK')) {
        Require ($stageBText.Contains($needle)) ('Signed B output missing ' + $needle)
    }
    $receiptBHash = (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
    Require ($receiptBHash -ne $receiptAHash) 'B stage did not change the persisted receipt'

    $recoverB = Invoke-Logged 'recover-b' @($hostDll, '--recover-signed', '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt, '--expected-score-multiplier', '2')
    Require ($recoverB -eq 0) 'B recovery failed'
    $recoverBText = Read-Text (Join-Path $logs 'recover-b.stdout')
    foreach ($needle in @('activated=True', 'source=LastKnownGood', 'version=game-rules-b', 'results=2,6,12 score=12 ticks=3 multiplier=2', 'persistence=None', 'TRUSTED-GAME OK')) {
        Require ($recoverBText.Contains($needle)) ('B recovery output missing ' + $needle)
    }
    Require ($receiptBHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed during B recovery'

    $signedBText = Read-Text $signedB
    $tamperedBText = $signedBText.Replace('"version":"game-rules-b"', '"version":"game-rules-y"')
    Require ($tamperedBText -ne $signedBText) 'Could not tamper signed B payload'
    [IO.File]::WriteAllText($tamperedB, $tamperedBText, [Text.UTF8Encoding]::new($false))
    $stageTamperedB = Invoke-Logged 'stage-tampered-b' @($hostDll, '--stage-signed', $sourceB, '--signed', $tamperedB, '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt, '--expected-score-multiplier', '2')
    Require ($stageTamperedB -eq 0) 'Tampered B did not fall back to authenticated B'
    $tamperedBOut = Read-Text (Join-Path $logs 'stage-tampered-b.stdout')
    foreach ($needle in @('stage=VerificationFailed', 'activated=True', 'source=LastKnownGood', 'version=game-rules-b', 'results=2,6,12 score=12 ticks=3 multiplier=2', 'persistence=None', 'TRUSTED-GAME OK')) {
        Require ($tamperedBOut.Contains($needle)) ('Tampered B fallback output missing ' + $needle)
    }
    Require ($receiptBHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed during tampered B fallback'

    $wrongMultiplier = Invoke-Logged 'recover-b-wrong-multiplier' @($hostDll, '--recover-signed', '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt, '--expected-score-multiplier', '1')
    Require ($wrongMultiplier -eq 1) 'Wrong multiplier did not fail gameplay'
    $wrongMultiplierText = (Read-Text (Join-Path $logs 'recover-b-wrong-multiplier.stdout')) + (Read-Text (Join-Path $logs 'recover-b-wrong-multiplier.stderr'))
    foreach ($needle in @('activated=True', 'version=game-rules-b', 'expectedScoreMultiplier=1', 'TRUSTED-GAME FAILED')) {
        Require ($wrongMultiplierText.Contains($needle)) ('Wrong multiplier output missing ' + $needle)
    }
    Require (-not $wrongMultiplierText.Contains('TRUSTED-GAME OK')) 'Wrong multiplier reported success'
    Require ($receiptBHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed after wrong multiplier control'

    $recoverBCorrect = Invoke-Logged 'recover-b-correct' @($hostDll, '--recover-signed', '--spki', $spki, '--releases-root', $releases, '--receipt', $receipt, '--expected-score-multiplier', '2')
    Require ($recoverBCorrect -eq 0) 'Correct B recovery after wrong multiplier failed'
    $recoverBCorrectText = Read-Text (Join-Path $logs 'recover-b-correct.stdout')
    foreach ($needle in @('activated=True', 'source=LastKnownGood', 'version=game-rules-b', 'results=2,6,12 score=12 ticks=3 multiplier=2', 'TRUSTED-GAME OK')) {
        Require ($recoverBCorrectText.Contains($needle)) ('Correct B recovery output missing ' + $needle)
    }
    Require ($receiptBHash -eq (Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash) 'Receipt changed after correct B recovery'

    $localScript = Join-Path $repo 'eng/trusted-game.ps1'
    $localArguments = @('-NoProfile')
    if ($sampleOnWindows) {
        $localArguments += @('-ExecutionPolicy', 'Bypass')
    }
    $localArguments += @('-File', $localScript, '-Configuration', $Configuration)
    $localCode = Invoke-LoggedCommand -Name 'local-regression' -Exe $powerShellExe -Arguments $localArguments
    Require ($localCode -eq 0) 'Original local trusted-game regression failed'
    $localText = Read-Text (Join-Path $logs 'local-regression.stdout')
    Require ($localText.Contains('TRUSTED-GAME OK')) 'Original local regression did not print TRUSTED-GAME OK'

    Write-Host "TRUSTED-GAME-SIGNED OK receipt-a=$receiptAHash receipt-b=$receiptBHash assembly=$assemblyA update-a=$updateAHash update-b=$updateBHash"
    exit 0
}
catch {
    Write-Host ("TRUSTED-GAME-SIGNED FAILED " + $_.Exception.Message)
    exit 1
}
