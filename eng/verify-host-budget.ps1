param(
    [string] $RuntimeRepo = 'E:/runtime-finalizer-20261013',
    [string] $RuntimeLayout,
    [string] $CandidateCommit,
    [string] $BuiltProduct,
    [ValidateSet('Checked','Release')] [string] $RuntimeConfiguration = 'Checked',
    [string] $BuildEvidence,
    [string] $SdkDotnet,
    [string] $EvidenceDirectory,
    [string[]] $Cases,
    [switch] $StockSmoke,
    [switch] $CapabilityRefusal,
    [switch] $Pumped
)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
if(!$SdkDotnet){$SdkDotnet=Join-Path $repo 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'}
$SdkDotnet=(Resolve-Path $SdkDotnet).Path
if(!$EvidenceDirectory){$EvidenceDirectory=Join-Path $repo ('artifacts/host-budget/probe-'+[guid]::NewGuid().ToString('N'))}
if(Test-Path $EvidenceDirectory){throw 'New evidence directory required; never replace a failed run.'}
New-Item -ItemType Directory $EvidenceDirectory|Out-Null
$EvidenceDirectory=(Resolve-Path $EvidenceDirectory).Path
Copy-Item $PSCommandPath (Join-Path $EvidenceDirectory 'driver.ps1')
$sourceRoot=Join-Path $PSScriptRoot 'host-budget-probe'
$entryObserverSource = Join-Path $PSScriptRoot 'windows-entry-observation/WindowsEntryObservation.cs'
$entryObserverSourceSha256 = (Get-FileHash $entryObserverSource).Hash
Copy-Item $entryObserverSource (Join-Path $EvidenceDirectory 'WindowsEntryObservation.cs')
$sourceHashes=[ordered]@{}
foreach($root in @($sourceRoot,(Join-Path $repo 'src/RuneCLR.Runtime'),(Join-Path $repo 'src/RuneCLR.Abstractions'),(Join-Path $repo 'src/RuneCLR.Packages'))){
    foreach($file in Get-ChildItem $root -Recurse -File|Where-Object{$_.Extension -in '.cs','.csproj' -and $_.FullName.Replace([IO.Path]::DirectorySeparatorChar,[char]'/') -notmatch '/(obj|bin)/'}){
        $relative=[IO.Path]::GetRelativePath($repo,$file.FullName);$dest=Join-Path $EvidenceDirectory ('source/'+$relative)
        New-Item -ItemType Directory (Split-Path $dest) -Force|Out-Null
        Copy-Item $file.FullName $dest;$sourceHashes[$relative]=(Get-FileHash $file.FullName).Hash
    }
}
foreach($name in 'Directory.Build.props','Directory.Build.targets','global.json','NuGet.Config'){
    if(Test-Path (Join-Path $repo $name)){$sourceHashes[$name]=(Get-FileHash (Join-Path $repo $name)).Hash;New-Item -ItemType Directory (Join-Path $EvidenceDirectory 'source') -Force|Out-Null;Copy-Item (Join-Path $repo $name) (Join-Path $EvidenceDirectory ('source/'+$name))}
}
function Assert-Sources{foreach($relative in $sourceHashes.Keys){if($sourceHashes[$relative] -ne (Get-FileHash (Join-Path $repo $relative)).Hash){throw "Source changed after evidence freeze: $relative"}}}
function Invoke-Child([string]$Executable,[string[]]$Arguments,[hashtable]$Settings,[string]$Log){
    $info=[Diagnostics.ProcessStartInfo]::new($Executable);$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.WorkingDirectory=$repo
    foreach($argument in $Arguments){$info.ArgumentList.Add($argument)}
    foreach($key in @($info.Environment.Keys)){if($key.StartsWith('DOTNET_') -or $key.StartsWith('COMPlus_') -or $key.StartsWith('RUNECLR_')){$info.Environment.Remove($key)|Out-Null}}
    foreach($key in $Settings.Keys){$info.Environment[$key]=$Settings[$key]}
    $process=[Diagnostics.Process]::Start($info);$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    $timedOut=!$process.WaitForExit(180000)
    if($timedOut){$process.Kill($true);$process.WaitForExit(10000)|Out-Null}
    $outText=if($stdout.Wait(10000)){$stdout.GetAwaiter().GetResult()}else{'[stdout incomplete after owned watchdog]'}
    $errText=if($stderr.Wait(10000)){$stderr.GetAwaiter().GetResult()}else{'[stderr incomplete after owned watchdog]'}
    [IO.File]::WriteAllText($Log+'.stdout',$outText);[IO.File]::WriteAllText($Log+'.stderr',$errText)
    [ordered]@{executable=$Executable;arguments=$Arguments;settings=$Settings;processId=$process.Id;timedOut=$timedOut;terminated=$process.HasExited;exitCode=if($process.HasExited){$process.ExitCode}else{$null};stdoutSha256=(Get-FileHash ($Log+'.stdout')).Hash;stderrSha256=(Get-FileHash ($Log+'.stderr')).Hash}|ConvertTo-Json -Depth 6|Set-Content ($Log+'.process.json')
    if($timedOut){throw "Owned child exceeded 180s and was killed; watchdog means FAIL: $Log"}
    if($process.ExitCode -ne 0){throw "Host budget child failed exit=$($process.ExitCode); raw logs preserved: $Log"}
    $jit=if($Settings.ContainsKey('DOTNET_JitStdOutFile') -and (Test-Path $Settings.DOTNET_JitStdOutFile)){[IO.File]::ReadAllText($Settings.DOTNET_JitStdOutFile)}else{''}
    return @{stdout=$outText;stderr=$errText;jit=$jit;exitCode=$process.ExitCode}
}
$all=@('Normal','EndlessTick','StartLoop','CatchResume','BroadCatchResume','SignalFilter','FilterExhaustion','ConstructorLoop','StaticConstructorLoop','FiniteCleanup','InfiniteCleanup','StopLoop','MaliciousMessage','ExplicitCanceled','Recovery')
if($Pumped){$all+=@('TickWork')}
if($StockSmoke -and $CapabilityRefusal){throw 'StockSmoke and CapabilityRefusal are separate controls.'}
if(!$Cases){$Cases=if($StockSmoke){@('Normal','MissingCapability')}elseif($CapabilityRefusal){@('MissingCapability')}else{$all}}
foreach($case in $Cases){if($case -notin ($all+@('MissingCapability'))){throw "Unknown case: $case"};if($StockSmoke -and $case -notin 'Normal','MissingCapability'){throw 'Stock smoke only finite and missing-capability cases.'};if($CapabilityRefusal -and $case -ne 'MissingCapability'){throw 'Older layout only capability refusal.'}}
$request=[ordered]@{platform='windows.x64';startedUtc=[DateTime]::UtcNow.ToString('o');sdk=$SdkDotnet;sdkSha256=(Get-FileHash $SdkDotnet).Hash;sourceHashes=$sourceHashes;cases=$Cases;stockSmoke=[bool]$StockSmoke;capabilityRefusal=[bool]$CapabilityRefusal;executionLimit=8192;normalExecutionLimit=1000000;cleanupLimit=4096;prototypeOnly=$true;nativeEntryProof=$false}
$request.runtimeConfiguration = $RuntimeConfiguration
if($Pumped){$request.hostPumped=$true}
$request.entryObserverSourceSha256 = $entryObserverSourceSha256
$request.executionEvidenceScope = if ($RuntimeConfiguration -eq 'Release') { 'Actual native ledgers/business outcomes/ownership/collection; per-method interpreter entry proof pending' } else { 'Checked positive bytecode and native compilation diagnostics plus scalar behavior' }
$results=[ordered]@{passed=$false;prototypeOnly=$true;nativeEntryProof=$false;lanes=[ordered]@{}}
try{
    if(!$StockSmoke){
        if(!$RuntimeLayout -or !$CandidateCommit){throw 'Explicit layout and candidate source commit required.'}
        $RuntimeRepo=(Resolve-Path $RuntimeRepo).Path;$RuntimeLayout=(Resolve-Path $RuntimeLayout).Path
        $head=(& git -C $RuntimeRepo rev-parse HEAD).Trim()
        if($head -ne $CandidateCommit -or (& git -C $RuntimeRepo status --porcelain --untracked-files=no)){throw 'Exact committed tracked-clean runtime source required.'}
        $requiredParent=if($CapabilityRefusal){'7660f3069b3751b648f038bf7f3e9cfc6f96ff09'}else{'099dacd07d8d890822f7422f895337733457ab3c'}
        & git -C $RuntimeRepo merge-base --is-ancestor $requiredParent $head
        if($LASTEXITCODE -ne 0){throw 'Runtime ancestry does not contain required boundary candidate.'}
        if(!$BuiltProduct){$BuiltProduct=Join-Path $RuntimeRepo ('artifacts/bin/coreclr/windows.x64.' + $RuntimeConfiguration)}
        $BuiltProduct=(Resolve-Path $BuiltProduct).Path;$framework=Join-Path $RuntimeLayout 'shared/Microsoft.NETCore.App/12.0.0';$privateDotnet=Join-Path $RuntimeLayout 'dotnet.exe'
        $runtimePaths=[ordered]@{};$runtimeHashes=[ordered]@{}
        foreach($name in 'coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll'){
            $runtimePaths[$name]=Join-Path $framework $name;$runtimeHashes[$name]=(Get-FileHash $runtimePaths[$name]).Hash
            if($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash){throw "Layout/product mismatch: $name"}
        }
        foreach($name in 'coreclr.dll','clrinterpreter.dll','clrjit.dll'){
            if(!(Get-Item $runtimePaths[$name]).VersionInfo.ProductVersion.Contains($head)){throw "Source stamp mismatch: $name"}
        }
        $runtimePaths['dotnet.exe']=$privateDotnet;$runtimePaths['hostpolicy.dll']=Join-Path $framework 'hostpolicy.dll';$runtimePaths['hostfxr.dll']=Join-Path $RuntimeLayout 'host/fxr/12.0.0/hostfxr.dll'
        foreach($name in $runtimePaths.Keys){$runtimeHashes[$name]=(Get-FileHash $runtimePaths[$name]).Hash}
        $request.candidateCommit=$head;$request.runtimeRepo=$RuntimeRepo;$request.runtimeLayout=$RuntimeLayout;$request.builtProduct=$BuiltProduct;$request.runtimeHashes=$runtimeHashes;$request.runtimePaths=$runtimePaths
    }
    if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') {
        if (!$BuildEvidence) { throw 'Release requires explicit matching BuildEvidence; a configuration label is not provenance.' }
        & py -3 -B (Join-Path $PSScriptRoot 'windows-runtime-validation.py') freeze --candidate-commit $CandidateCommit --runtime $RuntimeRepo --layout $RuntimeLayout --build-evidence $BuildEvidence --output $EvidenceDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Exact Release build/layout provenance validation failed; raw retained.' }
        $request.runtimeProvenanceSha256 = (Get-FileHash (Join-Path $EvidenceDirectory 'runtime-provenance.json')).Hash
    }
    $request|ConvertTo-Json -Depth 8|Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $outputs=@{}
    foreach($project in 'Host','Payload'){
        Assert-Sources;$outputs[$project]=Join-Path $EvidenceDirectory $project.ToLowerInvariant()
        Invoke-Child $SdkDotnet @('build',(Join-Path $sourceRoot "$project/$project.csproj"),'-c','Release','--output',$outputs[$project],'-nodeReuse:false') @{} (Join-Path $EvidenceDirectory "build-$project.log")|Out-Null
        Assert-Sources
    }
    $managedHashes=[ordered]@{}
    foreach($directory in $outputs.Values){foreach($file in Get-ChildItem $directory -File){$managedHashes[$file.FullName]=(Get-FileHash $file.FullName).Hash}}
    $managedHashes|ConvertTo-Json -Depth 5|Set-Content (Join-Path $EvidenceDirectory 'managed-identity.json')
    $hostPath=Join-Path $outputs.Host 'HostBudgetProbe.Host.dll'
    foreach($case in $Cases){
        Assert-Sources;$mode=if($case -eq 'MissingCapability'){'missing-capability'}elseif($StockSmoke){'stock'}else{'budget'}
        $nonce=[guid]::NewGuid().ToString('N');$name="$mode-$case-$nonce";$laneDirectory=Join-Path $EvidenceDirectory $name
        $settings=if($StockSmoke){@{}}else{@{DOTNET_InterpMode='0';DOTNET_RuneCLRInterpretCollectible='0';DOTNET_ReadyToRun='1';DOTNET_TieredCompilation='1';DOTNET_InterpList='1';DOTNET_InterpDump='*:*';DOTNET_JitDisasmSummary='1';DOTNET_MULTILEVEL_LOOKUP='0';DOTNET_JitStdOutFile=(Join-Path $EvidenceDirectory "$name.log.jit")}}
        if ($RuntimeConfiguration -eq 'Release') { foreach ($key in 'DOTNET_InterpList','DOTNET_InterpDump','DOTNET_JitDisasmSummary') { $settings.Remove($key) }; $settings.RUNECLR_POST_EXECUTION_PRECODE='1' }
        $arguments=if($StockSmoke){@($hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode)}else{@('exec','--fx-version','12.0.0',$hostPath,$outputs.Payload,$laneDirectory,$case,$nonce,$mode)}
        if($Pumped){$arguments+=@('--pumped')}
        $results.lanes[$name]=@{passed=$false;case=$case;mode=$mode;nonce=$nonce;arguments=$arguments;settings=$settings}
        $results|ConvertTo-Json -Depth 8|Set-Content (Join-Path $EvidenceDirectory 'results.json')
        $raw=Invoke-Child $(if($StockSmoke){$SdkDotnet}else{$privateDotnet}) $arguments $settings (Join-Path $EvidenceDirectory "$name.log")
        $receipt=Get-Content (Join-Path $laneDirectory 'result.json') -Raw|ConvertFrom-Json
        if(!$receipt.passed -or $receipt.nonce -ne $nonce -or $receipt.scenario -ne $case -or $receipt.mode -ne $mode){throw "Owned scalar receipt mismatch: $name"}
        if($case -eq 'MissingCapability'){
            if(!$receipt.beforeAuthorFile -or $receipt.exception -ne 'System.PlatformNotSupportedException' -or $raw.stderr -notmatch ('(?m)^HOST BUDGET REFUSAL nonce='+$nonce+' exception=System[.]PlatformNotSupportedException beforeAuthorFile=true\r?$')){throw 'Capability refusal was not established before missing author file.'}
        }else{
            $rowCount=if($case -eq 'Normal'){20}elseif($case -eq 'Recovery'){40}else{1}
            if(@($receipt.rows).Count -ne $rowCount -or @($receipt.rows|Where-Object{!$_.collected}).Count -ne 0 -or $raw.stderr -notmatch ('(?m)^HOST BUDGET COMPLETE nonce='+$nonce+' case='+$case+' mode='+$mode+' rows='+$rowCount+' prototypeOnly=true\r?$')){throw "Owned result/collection count mismatch: $name"}
            if($Pumped){
                foreach($row in $receipt.rows){
                    if(!$row.pumped -or !$row.retainedStoppedSessionCollected -or $row.successfulHostReturns -ne $row.report.CompletedTicks){throw "Host-pumped return/retained-session receipt mismatch: $name"}
                    if($case -eq 'TickWork' -and ($row.successfulHostReturns -lt 2 -or $row.successfulHostReturns -ge 64 -or !$row.report.PrototypeBudget.IsTerminated -or $row.report.PrototypeBudget.ExecutionExecuted -ne 8192)){throw 'Finite callbacks did not share the native session allowance across host returns.'}
                }
            }
            if(!$StockSmoke -and $RuntimeConfiguration -eq 'Checked'){
                $trusted=if($Pumped){'Start'}else{'Run'}
                if($raw.jit -notmatch ('JIT compiled\s+[.]?RuneCLR[.]Runtime[.]MapRunner:'+$trusted+'\(')){throw "Actual trusted native MapRunner execution missing: $name"}
                if($raw.jit -match 'JIT compiled\s+[.]?HostBudgetUGC[.]'){throw "Reported author native definition compilation: $name"}
                $method=if($case -eq 'Recovery'){'HostBudgetUGC.Base:Spin'}elseif($case -eq 'ConstructorLoop'){'HostBudgetUGC.ConstructorLoop:.ctor'}elseif($case -eq 'StaticConstructorLoop'){'HostBudgetUGC.StaticConstructorLoop:.cctor'}elseif($case -eq 'StartLoop'){'HostBudgetUGC.StartLoop:OnStart'}else{'HostBudgetUGC.'+$case+':OnTick'}
                if($raw.stdout -notmatch ('(?m)^Compiled method: [.]?'+[regex]::Escape($method)+'\(')){throw "Actual author bytecode missing: $method"}
                if($case -eq 'StopLoop' -and $raw.stdout -notmatch '(?m)^Compiled method: [.]?HostBudgetUGC[.]StopLoop:OnStop\('){throw 'StopLoop author body bytecode missing.'}
                if($case -in 'FiniteCleanup','InfiniteCleanup'){
                    $helper=if($case -eq 'FiniteCleanup'){'Finite'}else{'Infinite'}
                    if($raw.stdout -notmatch ('(?m)^Compiled method: [.]?HostBudgetUGC[.]Private[.]Helper:'+$helper+'\(')){throw 'Actual private cleanup body bytecode missing.'}
                }
                if($case -eq 'MaliciousMessage' -and $raw.stdout -match '(?m)^Compiled method: [.]?HostBudgetUGC[.]BadMessage:get_Message\('){throw 'Host error reporting executed malicious author Message getter.'}
            }
        }
        $results.lanes[$name].scalarReceiptSha256=(Get-FileHash (Join-Path $laneDirectory 'result.json')).Hash;$results.lanes[$name].passed=$true
        Write-Host "PASS host-budget case=$case mode=$mode"
    }
    Assert-Sources
    foreach($path in $managedHashes.Keys){if($managedHashes[$path] -ne (Get-FileHash $path).Hash){throw "Managed bytes changed during run: $path"}}
    if(!$StockSmoke){foreach($name in $runtimeHashes.Keys){if($runtimeHashes[$name] -ne (Get-FileHash $runtimePaths[$name]).Hash){throw "Runtime bytes changed during run: $name"}};foreach($name in 'coreclr.dll','clrinterpreter.dll','clrjit.dll','System.Private.CoreLib.dll'){if($runtimeHashes[$name] -ne (Get-FileHash (Join-Path $BuiltProduct $name)).Hash){throw "Product changed during run: $name"}}}
    if ((Get-FileHash $entryObserverSource).Hash -ne $entryObserverSourceSha256) { throw 'Post-execution observer source changed during probes.' }
    if (!$StockSmoke -and $RuntimeConfiguration -eq 'Release') {
        & py -3 -B (Join-Path $PSScriptRoot 'windows-runtime-validation.py') check --candidate-commit $CandidateCommit --output $EvidenceDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Frozen Release inputs changed during probes.' }
        $results.releaseProvenanceUnchanged = $true
    }
    $results.passed=$true;$results.sourceUnchanged=$true;$results.managedUnchanged=$true;$results.runtimeUnchanged=!$StockSmoke
}catch{$results.error=$_.Exception.Message;throw}finally{
    $request|ConvertTo-Json -Depth 8|Set-Content (Join-Path $EvidenceDirectory 'request.json')
    $results|ConvertTo-Json -Depth 8|Set-Content (Join-Path $EvidenceDirectory 'results.json')
}
