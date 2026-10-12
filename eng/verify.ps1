$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & dotnet build RuneCLR.slnx -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    & dotnet build tests/RuneCLR.LateMap -c Release -t:Rebuild -p:BuildProjectReferences=false
    if ($LASTEXITCODE -ne 0) { throw 'Late map build failed.' }
    & dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --late-map tests/RuneCLR.LateMap/bin/Release/net11.0/map.json
    if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
    if ($LASTEXITCODE -ne 0) { throw 'Sample failed.' }
}
finally {
    Pop-Location
}
