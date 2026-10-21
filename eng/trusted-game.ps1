param(
    [ValidateSet('Release', 'Debug')]
    [string]$Configuration = 'Release'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$dotnet = (Get-Command dotnet -ErrorAction Stop).Source
$hostProject = Join-Path $repo 'samples/TrustedGame.Host/TrustedGame.Host.csproj'
$updateProject = Join-Path $repo 'samples/TrustedGame.Update/TrustedGame.Update.csproj'
$hostOut = Join-Path $repo "samples/TrustedGame.Host/bin/$Configuration/net11.0"
$hostDll = Join-Path $hostOut 'TrustedGame.Host.dll'
$updateOut = Join-Path $repo "samples/TrustedGame.Update/bin/$Configuration/net11.0"
$updateDll = Join-Path $updateOut 'TrustedGame.Update.dll'
$hostCopyOfUpdate = Join-Path $hostOut 'TrustedGame.Update.dll'


Write-Host "trusted-game: build host and Contracts/TrustedUpdate dependencies"
& $dotnet build $hostProject -c $Configuration --nologo
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $hostDll)) {
    throw "Host output was not produced: $hostDll"
}
if (Test-Path -LiteralPath $hostCopyOfUpdate) {
    throw "Host output unexpectedly contains TrustedGame.Update.dll; the host must not reference the module."
}

$hostShaBefore = (Get-FileHash -LiteralPath $hostDll -Algorithm SHA256).Hash
$hostWriteBefore = (Get-Item -LiteralPath $hostDll).LastWriteTimeUtc

Write-Host "trusted-game: build module after host; BuildProjectReferences=false"
& $dotnet build $updateProject -c $Configuration --nologo -p:BuildProjectReferences=false
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $updateDll)) {
    throw "Update output was not produced: $updateDll"
}

$hostShaAfter = (Get-FileHash -LiteralPath $hostDll -Algorithm SHA256).Hash
$hostWriteAfter = (Get-Item -LiteralPath $hostDll).LastWriteTimeUtc
if ($hostShaBefore -ne $hostShaAfter -or $hostWriteBefore -ne $hostWriteAfter) {
    throw "Host DLL changed while the module was built; the host must not be rebuilt in step two."
}

$moduleSha256 = (Get-FileHash -LiteralPath $updateDll -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "trusted-game: host-sha=$hostShaAfter module-sha=$moduleSha256"
Write-Host "trusted-game: launch host; approval is a local build-pipeline gate, not a signature"

& $dotnet $hostDll --module $updateDll --sha256 $moduleSha256 --approval local-trusted-build
exit $LASTEXITCODE
