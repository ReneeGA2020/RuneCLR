$ErrorActionPreference = 'Stop'
function Resolve-Python3 {
    $candidates = @(
        @{ Name = 'python3'; Prefix = @() },
        @{ Name = 'python'; Prefix = @() },
        @{ Name = 'py'; Prefix = @('-3') }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) { continue }
        try {
            $prefix = @($candidate.Prefix)
            $versionOutput = & $command.Source @prefix --version 2>&1
            $versionCode = $LASTEXITCODE
            $version = ($versionOutput | Out-String).Trim()
            if ($versionCode -eq 0 -and $version -match '^Python 3\.') {
                return @{ Command = $command.Source; Prefix = $prefix; Version = $version }
            }
        } catch {
            continue
        }
    }
    throw 'Python 3 was not found (tried python3, python, py -3).'
}

$Python = Resolve-Python3
Write-Host ("Python: " + $Python.Command + " " + $Python.Version)
$PythonCommand = $Python.Command
$PythonPrefix = @($Python.Prefix)

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
    & dotnet run --project tests/RuneCLR.TrustedUpdate.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Trusted update selector tests failed.' }
    & dotnet run --project tests/RuneCLR.TrustedModuleSession.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Trusted module session tests failed.' }
    & dotnet run --project tests/RuneCLR.TrustedRelease.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Trusted release signature tests failed.' }
    & dotnet run --project tests/RuneCLR.TrustedReleaseStaging.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Trusted release staging tests failed.' }
    & dotnet run --project tests/RuneCLR.TrustedReleaseRecovery.Tests -c Release --no-build
    if ($LASTEXITCODE -ne 0) { throw 'Trusted release recovery tests failed.' }
    & $PythonCommand @PythonPrefix eng/verify-trusted-update-plan.py
    if ($LASTEXITCODE -ne 0) { throw 'Trusted update plan parity failed.' }
    & $PythonCommand @PythonPrefix -B eng/test-trusted-game-builds.py
    if ($LASTEXITCODE -ne 0) { throw 'Trusted game build runner diagnostics failed.' }
    & $PythonCommand @PythonPrefix -B eng/test-trusted-game-observations.py
    if ($LASTEXITCODE -ne 0) { throw 'Trusted game observation selftest failed.' }
    & $PythonCommand @PythonPrefix -B eng/trusted-game-generic-size/test-offline-replay.py
    if ($LASTEXITCODE -ne 0) { throw 'Generic-size offline replay selftest failed.' }
    & $PythonCommand @PythonPrefix -B eng/test-trusted-game-generics.py --self-test-portability
    if ($LASTEXITCODE -ne 0) { throw 'Generic-interaction portability selftest failed.' }
    & $PythonCommand @PythonPrefix -B eng/test-trusted-game-generic-ir.py
    if ($LASTEXITCODE -ne 0) { throw 'Generic IR reader selftest failed.' }
    & $PythonCommand @PythonPrefix eng/verify-ios-host-callback.py
    if ($LASTEXITCODE -ne 0) { throw 'iOS host callback closure failed.' }
    & dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release --no-build -- --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Trusted update host self-test failed.' }
    & dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release --no-build -- --signed-self-test
    if ($LASTEXITCODE -ne 0) { throw 'Signed trusted update startup self-test failed.' }
    & dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release --no-build -- --staged-self-test
    if ($LASTEXITCODE -ne 0) { throw 'Staged trusted update startup self-test failed.' }
    & dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release --no-build -- --recovery-self-test
    if ($LASTEXITCODE -ne 0) { throw 'Recoverable trusted update startup self-test failed.' }
    & dotnet run --project samples/RuneCLR.TrustedUpdateHost -c Release --no-build -- --staged-recovery-self-test
    if ($LASTEXITCODE -ne 0) { throw 'Staged recoverable startup self-test failed.' }
    & dotnet run --project eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --no-build -- --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Signed delivery host self-test failed.' }
    & dotnet run --project eng/trusted-composition-delivery/Host/TrustedComposition.DeliveryHost.csproj -c Release --no-build -- --integration
    if ($LASTEXITCODE -ne 0) { throw 'Signed delivery host integration failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --collect
    if ($LASTEXITCODE -ne 0) { throw 'Sample failed.' }
    & dotnet run --project samples/RuneCLR.SampleHost -c Release --no-build -- --pump --collect
    if ($LASTEXITCODE -ne 0) { throw 'Host-pumped sample failed.' }
    & ./eng/score-game.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Score game sample failed.' }
    & ./eng/trusted-game.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Trusted game late-module sample failed.' }
    & ./eng/trusted-game-signed.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Trusted game signed staging and recovery sample failed.' }
}
finally {
    Pop-Location
}
