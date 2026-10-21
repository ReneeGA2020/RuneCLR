$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $refs = 'tools/RuneCLR.PackageFixtures/bin/Release/net11.0/refs'
    $contract = 'samples/ScoreGame.Contracts/bin/Release/net11.0/ScoreGame.Contracts.dll'
    $root = Join-Path 'artifacts/score-game' ([guid]::NewGuid().ToString('N'))
    function Publish-Score([string] $name, [string] $source, [string] $id) {
        $output = Join-Path $root $name
        & dotnet run --project tools/RuneCLR.PackageTool -c Release --no-build -- compile --source $source --id $id --entry-type Script --framework-refs $refs --contract $contract --output $output --host-interface ScoreGame.IScoreRules --allowed-method Add --allowed-method Total | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Score package compile failed: $name" }
        $manifest = Join-Path $output 'package.json'
        & dotnet run --project tools/RuneCLR.PackageTool -c Release --no-build -- validate --manifest $manifest | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Score package validate failed: $name" }
        return $manifest
    }

    $a = Publish-Score 'a' 'samples/ScoreGame.Source/A' 'score-a'
    $b = Publish-Score 'b' 'samples/ScoreGame.Source/B' 'score-b'
    $fail = Publish-Score 'fail' 'samples/ScoreGame.Source/Fail' 'score-fail'
    & dotnet run --project samples/ScoreGame.Host -c Release --no-build -- $a $b $fail
    if ($LASTEXITCODE -ne 0) { throw 'Score game host failed.' }
}
finally {
    Pop-Location
}
