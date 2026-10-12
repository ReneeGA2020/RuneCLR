$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & dotnet build RuneCLR.slnx -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    & dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
    if ($LASTEXITCODE -ne 0) { throw 'Sample failed.' }
}
finally {
    Pop-Location
}
