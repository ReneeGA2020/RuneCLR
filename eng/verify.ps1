$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & dotnet build RuneCLR.slnx -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    & dotnet build tests/RuneCLR.LateMap -c Release -t:Rebuild -p:BuildProjectReferences=false
    if ($LASTEXITCODE -ne 0) { throw 'Late map build failed.' }
    & dotnet run --project tests/RuneCLR.Runtime.Tests -c Release --no-build -- --late-map tests/RuneCLR.LateMap/bin/Release/net11.0/map.json
    if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed.' }
    & dotnet run --project tests/RuneCLR.Packaging.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Packaging tests failed.' }
    $fixtures = Join-Path 'artifacts/packages' ('acceptance-' + [guid]::NewGuid().ToString('N'))
    & dotnet run --project tools/RuneCLR.PackageFixtures -c Release --no-build -- --framework-refs tools/RuneCLR.PackageFixtures/bin/Release/net11.0/refs --contract src/RuneCLR.Abstractions/bin/Release/net11.0/RuneCLR.Abstractions.dll --output $fixtures --include-pumped
    if ($LASTEXITCODE -ne 0) { throw 'Controlled fixture generation failed.' }
    & dotnet run --project tests/RuneCLR.PackageExecution.Tests -c Release --no-build -- --packages $fixtures
    if ($LASTEXITCODE -ne 0) { throw 'Player package execution tests failed.' }
    & dotnet run --project tests/RuneCLR.PackageExecution.Tests -c Release --no-build -- --packages $fixtures --pump
    if ($LASTEXITCODE -ne 0) { throw 'Host-pumped package execution tests failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
    if ($LASTEXITCODE -ne 0) { throw 'Sample failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --pump --collect
    if ($LASTEXITCODE -ne 0) { throw 'Host-pumped sample failed.' }
}
finally {
    Pop-Location
}
