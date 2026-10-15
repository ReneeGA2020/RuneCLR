param(
    [string] $RuntimeRepo = 'E:/runtime-selection-20261013',
    [Parameter(Mandatory)][string] $RuntimeLayout,
    [Parameter(Mandatory)][string] $CandidateCommit,
    [string] $BuiltProduct,
    [string] $BaselineRuntimeRepo = 'E:/runtime',
    [string] $SdkDotnet,
    [string] $EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$RuntimeRepo = (Resolve-Path $RuntimeRepo).Path
$RuntimeLayout = (Resolve-Path $RuntimeLayout).Path
$BaselineRuntimeRepo = (Resolve-Path $BaselineRuntimeRepo).Path
if (!$BuiltProduct) { $BuiltProduct = Join-Path $RuntimeRepo 'artifacts/bin/coreclr/windows.x64.Checked' }
$BuiltProduct = (Resolve-Path $BuiltProduct).Path
if (!$SdkDotnet) { $SdkDotnet = Join-Path $RuntimeRepo '.dotnet/dotnet.exe' }
$SdkDotnet = (Resolve-Path $SdkDotnet).Path
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
$head = (& git -C $RuntimeRepo rev-parse HEAD).Trim()
if ($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Explicit committed, tracked-clean candidate required.' }
if ((& git -C $BaselineRuntimeRepo rev-parse HEAD).Trim() -ne $base -or (& git -C $BaselineRuntimeRepo status --porcelain --untracked-files=no)) { throw 'Read-only baseline must match the pinned clean source.' }
& git -C $RuntimeRepo merge-base --is-ancestor $base $head
if ($LASTEXITCODE -ne 0) { throw 'Candidate must descend from the pinned baseline.' }
$framework = Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0'
$privateDotnet = Join-Path $RuntimeLayout 'dotnet.exe'
$runtimeHashes = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll', 'System.Private.CoreLib.dll') {
    $runtimeHashes[$name] = (Get-FileHash (Join-Path $framework $name)).Hash
    if ($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash) { throw "Candidate build/layout mismatch: $name" }
}
$stamp = (Get-Item (Join-Path $framework 'coreclr.dll')).VersionInfo.ProductVersion
if (!$stamp.Contains($head)) { throw "Candidate source stamp mismatch: $stamp" }
$nativeStamps = [ordered]@{}
foreach ($name in 'coreclr.dll', 'clrinterpreter.dll', 'clrjit.dll') {
    $nativeStamps[$name] = (Get-Item (Join-Path $framework $name)).VersionInfo.ProductVersion
    if (!$nativeStamps[$name].Contains($head)) { throw "Native source stamp mismatch: $name" }
}
$identityPaths = [ordered]@{}
foreach ($name in $runtimeHashes.Keys) { $identityPaths[$name] = Join-Path $framework $name }
$identityPaths['dotnet.exe'] = $privateDotnet
$identityPaths['hostfxr.dll'] = Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll'
$identityPaths['hostpolicy.dll'] = Join-Path $framework 'hostpolicy.dll'
foreach ($name in $identityPaths.Keys) { $runtimeHashes[$name] = (Get-FileHash $identityPaths[$name]).Hash }
if (!$EvidenceDirectory) { $EvidenceDirectory = Join-Path $repo ("artifacts/execution-selection/upstream-{0}-{1}" -f (Get-Date -Format yyyyMMdd-HHmmss), [guid]::NewGuid().ToString('N')) }
if (Test-Path $EvidenceDirectory) { throw 'Use a new evidence directory; preserve failed runs.' }
New-Item -ItemType Directory $EvidenceDirectory | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$tests = @(
    @{ name='GenericVirtualMethod'; folder='GenericVirtualMethod'; host='GenericVirtualMethodUnloading:CallGenericVirtualMethodAcrossUnloads' },
    @{ name='CollectibleStatics'; folder='Statics'; host='Program:TestEntryPoint' },
    @{ name='ResolvedFromDifferentContext'; folder='ResolvedFromDifferentContext'; host='Test:TestEntryPoint' },
    @{ name='ByRefLocals'; folder='ByRefLocals'; host='Program:TestEntryPoint' }
)
$sourceHashes = [ordered]@{}
foreach ($test in $tests) {
    $relativeRoot = 'src/tests/Loader/CollectibleAssemblies/' + $test.folder
    $sourceRoot = Join-Path $RuntimeRepo $relativeRoot
    foreach ($file in Get-ChildItem $sourceRoot -File | Where-Object Extension -in '.cs','.csproj') {
        $relative = $relativeRoot + '/' + $file.Name
        $digest = (Get-FileHash $file.FullName).Hash
        if ($digest -ne (Get-FileHash (Join-Path $BaselineRuntimeRepo $relative)).Hash) { throw "Official test source differs from baseline: $relative" }
        $sourceHashes[$relative] = $digest
        $dest = Join-Path $EvidenceDirectory "source/$relative"
        New-Item -ItemType Directory (Split-Path $dest) -Force | Out-Null
        Copy-Item $file.FullName $dest
    }
}
function Invoke-Process([string] $Executable, [string[]] $Arguments, [hashtable] $Settings, [string] $WorkingDirectory, [string] $Log, [int] $TimeoutSeconds=180) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.WorkingDirectory = $WorkingDirectory
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($key in @($info.Environment.Keys)) {
        if ($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_')) { $info.Environment.Remove($key) | Out-Null }
    }
    $info.Environment.Remove('Platform') | Out-Null
    foreach ($key in $Settings.Keys) { $info.Environment[$key] = $Settings[$key] }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timedOut = !$process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) { $process.Kill($true); $process.WaitForExit() }
    $outText = $stdout.GetAwaiter().GetResult()
    $errText = $stderr.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($Log + '.stdout', $outText)
    [IO.File]::WriteAllText($Log + '.stderr', $errText)
    [IO.File]::WriteAllText($Log, $outText + $errText)
    return @{ stdout=$outText; stderr=$errText; exitCode=$process.ExitCode; timedOut=$timedOut; command=@($Executable)+$Arguments;
        stdoutSha256=(Get-FileHash ($Log+'.stdout')).Hash; stderrSha256=(Get-FileHash ($Log+'.stderr')).Hash; logSha256=(Get-FileHash $Log).Hash }
}
$output = Join-Path $EvidenceDirectory 'official-output'
$testBin = Join-Path $output 'windows.x64.Checked'
$targetingPack = Join-Path $EvidenceDirectory 'targeting-pack'
Copy-Item (Join-Path $BaselineRuntimeRepo 'artifacts/TargetingPack') $targetingPack -Recurse
$packHashes = [ordered]@{}
foreach ($f in Get-ChildItem $targetingPack -Recurse -File) { $packHashes[$f.FullName.Substring($targetingPack.Length+1)] = (Get-FileHash $f.FullName).Hash }
$referencePack = Join-Path $EvidenceDirectory 'reference-pack'
Copy-Item (Join-Path $BaselineRuntimeRepo 'artifacts/bin/microsoft.netcore.app.ref') $referencePack -Recurse
$referenceHashes = [ordered]@{}
foreach ($f in Get-ChildItem $referencePack -Recurse -File) { $referenceHashes[$f.FullName.Substring($referencePack.Length+1)] = (Get-FileHash $f.FullName).Hash }
$allReferences = Join-Path $EvidenceDirectory 'all-reference-pack'
Copy-Item (Join-Path $BaselineRuntimeRepo 'artifacts/bin/ref/net11.0') $allReferences -Recurse
$allReferenceHashes = [ordered]@{}
foreach ($f in Get-ChildItem $allReferences -Recurse -File) { $allReferenceHashes[$f.FullName.Substring($allReferences.Length+1)] = (Get-FileHash $f.FullName).Hash }
$common = @('-p:BuildAsStandalone=true', "-p:BaseOutputPath=$output", "-p:__TestBinDir=$testBin", '-p:CLRTestPriorityToBuild=1',
    '-p:TargetOS=windows', '-p:TargetArchitecture=x64', '-p:RuntimeFlavor=coreclr', '-p:EmitCompilerGeneratedFiles=true',
    "-p:TargetingPackPath=$targetingPack/", "-p:MicrosoftNetCoreAppRefPackDir=$referencePack/", "-p:LibrariesAllRefArtifactsPath=$allReferences/", '-p:BuildTestsOnHelix=false')
$settings = @{ DOTNET_InterpMode='0'; DOTNET_RuneCLRInterpretCollectible='1'; DOTNET_ReadyToRun='1'; DOTNET_TieredCompilation='0';
    DOTNET_InterpList='1'; DOTNET_InterpDump='*:*'; DOTNET_JitDisasmSummary='1'; DOTNET_JitNoInline='0'; DOTNET_GCStress='0' }
$sdkIdentity = Invoke-Process $SdkDotnet @('--version') @{} $RuntimeRepo (Join-Path $EvidenceDirectory 'sdk-version.log')
if ($sdkIdentity.exitCode -ne 0 -or $sdkIdentity.timedOut) { throw 'Private SDK identity failed.' }
$request = [ordered]@{ runtimeBase=$base; candidateCommit=$head; runtimeRepo=$RuntimeRepo; runtimeLayout=$RuntimeLayout; builtProduct=$BuiltProduct;
    sourceStamp=$stamp; nativeSourceStamps=$nativeStamps; runtimeHashes=$runtimeHashes; officialSourceBase=$base; sourceHashes=$sourceHashes; baselineRuntimeRepo=$BaselineRuntimeRepo;
    sdk=$SdkDotnet; sdkVersion=$sdkIdentity.stdout.Trim(); sdkSha256=(Get-FileHash $SdkDotnet).Hash; targetingPackHashes=$packHashes; referencePackHashes=$referenceHashes; allReferencePackHashes=$allReferenceHashes; buildProperties=$common; settings=$settings; tests=$tests; startedUtc=[DateTime]::UtcNow.ToString('o');
    scope='Four official standalone generated Main entrypoints, native trusted callers plus required collectible IL; no complete upstream suite/native entry sampling' }
$request | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $EvidenceDirectory 'request.json')
$builds = [Collections.Generic.List[object]]::new()
$results = [Collections.Generic.List[object]]::new()
$stage = 'build'
try {
    $commands = @(@{ name='restore-dependencies'; args=@('restore','src/tests/Common/test_dependencies/test_dependencies.csproj')+$common })
    foreach ($test in $tests) { $commands += @{ name=$test.name; args=@('build',"src/tests/Loader/CollectibleAssemblies/$($test.folder)/$($test.name).csproj",'-c','Checked','-t:Rebuild')+$common } }
    foreach ($command in $commands) {
        $build = Invoke-Process $SdkDotnet $command.args @{} $RuntimeRepo (Join-Path $EvidenceDirectory "$($command.name)-build.log") 600
        $builds.Add(@{ name=$command.name; exitCode=$build.exitCode; timedOut=$build.timedOut; command=$build.command; logSha256=$build.logSha256 })
        $builds.ToArray() | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $EvidenceDirectory 'build-results.json')
        if ($build.exitCode -ne 0 -or $build.timedOut) { throw "Official project build failed: $($command.name)" }
        Write-Output "BUILT official $($command.name)"
    }
    $runtimeConfig = Join-Path $EvidenceDirectory 'official.runtimeconfig.json'
    @{ runtimeOptions=@{ tfm='net12.0'; framework=@{ name='Microsoft.NETCore.App'; version='12.0.0' }; rollForward='Disable' } } |
        ConvertTo-Json -Depth 5 | Set-Content $runtimeConfig
    $guards = [ordered]@{}
    $managedHashes = [ordered]@{}
    foreach ($test in $tests) {
        $folder = Join-Path $testBin "Loader/CollectibleAssemblies/$($test.folder)/$($test.name)"
        foreach ($dependency in Get-ChildItem $targetingPack -Filter '*.dll' | Where-Object { $_.Name.StartsWith('xunit.') -or $_.Name -eq 'Microsoft.DotNet.XUnitExtensions.dll' }) {
            $destination = Join-Path $folder $dependency.Name
            if (Test-Path $destination) {
                if ((Get-FileHash $destination).Hash -ne (Get-FileHash $dependency.FullName).Hash) { throw "Trusted test dependency mismatch: $destination" }
            } else { Copy-Item $dependency.FullName $destination }
        }
        $runners = @(Get-ChildItem $output -Recurse -Filter SimpleRunner.g.cs | Where-Object { $_.FullName -match ('[\\/]'+[regex]::Escape($test.folder)+'[\\/]'+[regex]::Escape($test.name)+'[\\/]') })
        if ($runners.Count -ne 1) { throw "Expected one freshly emitted official Main: $($test.name); found $($runners.Count)" }
        $runnerText = Get-Content $runners[0].FullName -Raw
        $hostMethod = $test.host.Split(':')[-1]
        $guardPass = $runnerText.Contains($hostMethod) -and $runnerText -notmatch '&&\s*\(false\)|if\s*\(\s*false\s*\)'
        if ($test.name -in 'GenericVirtualMethod','ResolvedFromDifferentContext') { $guardPass = $guardPass -and $runnerText.Contains('IsGCStress') }
        $dest = Join-Path $EvidenceDirectory "generated/$($test.name).cs"
        New-Item -ItemType Directory (Split-Path $dest) -Force | Out-Null
        Copy-Item $runners[0].FullName $dest
        $guards[$test.name] = @{ passed=$guardPass; source=$runners[0].FullName; sha256=(Get-FileHash $dest).Hash; hostMethod=$test.host }
        foreach ($f in Get-ChildItem $folder -File -Recurse) { $managedHashes[$f.FullName] = (Get-FileHash $f.FullName).Hash }
        if (!$guardPass) { throw "Official generated condition/body call invalid: $($test.name)" }
        foreach ($f in Get-ChildItem $folder -Filter '*.dll' -File -Recurse) {
            $stream = [IO.File]::OpenRead($f.FullName)
            $reader = [System.Reflection.PortableExecutable.PEReader]::new($stream)
            try {
                if (!$reader.PEHeaders.CorHeader -or $reader.PEHeaders.CorHeader.ManagedNativeHeaderDirectory.RelativeVirtualAddress -ne 0) { throw "Official managed input is not plain IL: $($f.FullName)" }
            } finally { $reader.Dispose(); $stream.Dispose() }
        }
    }
    $guards | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'generated-guards.json')
    $managedHashes | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $EvidenceDirectory 'managed-input-hashes.json')
    $stage = 'run'
    foreach ($test in $tests) {
        $folder = Join-Path $testBin "Loader/CollectibleAssemblies/$($test.folder)/$($test.name)"
        $assembly = Join-Path $folder "$($test.name).dll"
        $log = Join-Path $EvidenceDirectory "$($test.name)-required.log"
        $run = Invoke-Process $privateDotnet @('exec','--runtimeconfig',$runtimeConfig,'--fx-version','12.0.0',$assembly) $settings $folder $log
        $text = $run.stdout + $run.stderr
        $methods = @([regex]::Matches($text,'(?m)^Compiled method: (.+)\r?$') | ForEach-Object { $_.Groups[1].Value.TrimEnd([char]13) })
        $hostPattern = [regex]::Escape($test.host)
        $hostJit = $text -match ('JIT compiled[^\r\n]*'+$hostPattern)
        $hostInterpreted = $text -match ('(?m)^Compiled method: [^\r\n]*'+$hostPattern)
        $body = [ordered]@{}
        $forbidden = ''
        switch ($test.name) {
            'GenericVirtualMethod' {
                $body.genericBodies = @($methods | Where-Object { $_ -eq '.DerivedMachine:Construct[System.__Canon]()' }).Count
                $body.passed = $body.genericBodies -eq 10
                $forbidden = 'DerivedMachine:|Machine:'
            }
            'CollectibleStatics' {
                foreach ($method in 'SetStatic','GetStatic','SetStaticObject','GetStaticObject') {
                    $body[$method] = @($methods | Where-Object { $_.StartsWith('.StaticTest:'+ $method +'(') }).Count
                }
                $body.passed = $body.SetStatic -eq 1 -and $body.GetStatic -eq 1 -and $body.SetStaticObject -eq 1 -and $body.GetStaticObject -eq 1
                $forbidden = 'StaticTest:'
            }
            'ResolvedFromDifferentContext' {
                $body.positiveBodies = @($methods | Where-Object { $_ -eq '.TestClass.Class:MainTest()' }).Count
                $body.scenarioCount = ([regex]::Matches($text,'(?m)^Running test case (ResolvingEvent|LoadOverride|ResolvingEventInNonCollectible|LoadOverrideInNonCollectible)\r?$')).Count
                $body.passed = $body.positiveBodies -eq 2 -and $body.scenarioCount -eq 4
                $forbidden = 'TestClass.Class:|TestInterface.Class:'
            }
            'ByRefLocals' {
                $body.metadataGetSpan = @($methods | Where-Object { $_ -eq '.SpanAccessor:GetSpan()' }).Count
                $body.dynamicGetSpan = @($methods | Where-Object { $_ -eq '.GetSpanType:GetSpan()' }).Count
                $body.loopOutputs = ([regex]::Matches($text,'(?m)^1\r?$')).Count
                $body.passed = $body.metadataGetSpan -eq 1 -and $body.dynamicGetSpan -eq 1 -and $body.loopOutputs -eq 20
                $forbidden = 'SpanAccessor:|GetSpanType:'
            }
        }
        $payloadJit = $text -match ('JIT compiled[^\r\n]*('+ $forbidden +')')
        $passed = $run.exitCode -eq 100 -and !$run.timedOut -and $body.passed -and $hostJit -and !$hostInterpreted -and !$payloadJit -and $text -notmatch 'Assert failure|Fatal error|Unhandled exception'
        $results.Add([ordered]@{ test=$test.name; passed=$passed; exitCode=$run.exitCode; timedOut=$run.timedOut; generatedGuard=$guards[$test.name]; body=$body;
            hostJitPositive=$hostJit; hostInterpreted=$hostInterpreted; payloadJit=$payloadJit; command=$run.command;
            stdoutSha256=$run.stdoutSha256; stderrSha256=$run.stderrSha256; logSha256=$run.logSha256; log=$log })
        @{ success=$false; complete=$false; stage=$stage; runs=$results.ToArray() } |
            ConvertTo-Json -Depth 7 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
        if (!$passed) { throw "Official required-interpreter execution failed or evidence incomplete: $($test.name). See $log" }
        Write-Output "PASS official $($test.name): native trusted caller, required collectible bytecode, original assertions; exit100"
    }
    foreach ($f in $managedHashes.Keys) { if ((Get-FileHash $f).Hash -ne $managedHashes[$f]) { throw "Managed input changed: $f" } }
    foreach ($name in $identityPaths.Keys) { if ((Get-FileHash $identityPaths[$name]).Hash -ne $runtimeHashes[$name]) { throw "Runtime input changed: $name" } }
    if ((& git -C $RuntimeRepo rev-parse HEAD).Trim() -ne $head -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)) { throw 'Candidate source changed during execution.' }
    @{ success=$true; complete=$true; runs=$results.ToArray(); managedInputsUnchanged=$true; runtimeInputsUnchanged=$true; candidateCommit=$head; completedUtc=[DateTime]::UtcNow.ToString('o') } |
        ConvertTo-Json -Depth 7 | Set-Content (Join-Path $EvidenceDirectory 'results.json')
    Write-Output "PASS 4/4 official Windows Checked loader tests under mode0 + RuneCLRInterpretCollectible=1. Evidence: $EvidenceDirectory"
} catch {
    @{ success=$false; stage=$stage; error=$_.ToString(); runs=$results.ToArray(); failedUtc=[DateTime]::UtcNow.ToString('o') } |
        ConvertTo-Json -Depth 7 | Set-Content (Join-Path $EvidenceDirectory 'failure.json')
    throw
}
