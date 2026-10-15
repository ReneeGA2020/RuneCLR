[CmdletBinding()]
param(
    [ValidateSet('Validate','Build','Install','Produce','Transfer','Run','Archive','SelfTest')][string]$Phase = 'Validate',
    [string]$SourceLayoutDirectory,
    [string]$LayoutReceiptPath,
    [string]$HostInputReceipt,
    [ValidateSet('Checked','Release')][string]$NativeConfiguration = 'Checked',
    [string]$BuilderDirectory = 'D:/RuneCLR-Android/coreclr-smoke/run-20261012-172351/builder',
    [string]$BuilderSourceCommit = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de',
    [string]$EvidenceDirectory,
    [string]$AndroidRoot = 'D:/RuneCLR-Android',
    [string]$DeviceSerial,
    [string]$ExpectedAvdName = 'RuneCLR_API_35_x64',
    [string]$DotnetExecutable = 'dotnet',
    [string]$OperatorDotnetExecutable = 'dotnet',
    [string]$FixtureGenerator,
    [string]$FrameworkReferences,
    [string]$LateSourceDirectory,
    [string]$PayloadDirectory,
    [ValidateSet('all','sample','packages','lifecycle','required','ordinary','required-refusal','unmarked-fallback','required-boxed','required-inline','ordinary-inline')][string]$Lane = 'all',
    [string]$ProbeAssessorPath,
    [string]$PythonExecutable = 'py',
    [switch]$Offline
)
# Private source layout only. Never starts an emulator or builds production/runtime binaries.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$base = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
$candidate = '1724cdec553a7aff7a373a271a4be612651c7625'
$tree = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
$utf8 = [Text.UTF8Encoding]::new($false)
trap {
    if($EvidenceDirectory -and (Test-Path -LiteralPath $EvidenceDirectory -PathType Container)) {
        $failurePath=Join-Path $EvidenceDirectory ('phase-failure-'+$Phase+'-'+[Guid]::NewGuid().ToString('N')+'.json')
        Write-Json $failurePath @{phase=$Phase;failed=$true;error=$_.Exception.ToString();utc=[DateTime]::UtcNow.ToString('o');executionVerified=$false;scope='Preserved failed phase; no automatic retry'}
    }
    throw
}
function Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Json([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Write-Json([string]$Path, $Value) { [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 30) + [Environment]::NewLine, $utf8) }
function Require([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
function Inside([string]$Root, [string]$Relative) {
    Require (![IO.Path]::IsPathRooted($Relative) -and $Relative -notmatch '(^|[/\\])\.\.([/\\]|$)' -and $Relative -notmatch '[\x00-\x1f:]') ('Invalid relative path: ' + $Relative)
    $absolute = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('/','\') + [IO.Path]::DirectorySeparatorChar
    Require ($absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) 'Path escapes owned directory'
    $absolute
}
function File-Identity([string]$Root) {
    $values = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -File) { $values[[IO.Path]::GetRelativePath($Root, $file.FullName).Replace('\','/')] = Sha $file.FullName }
    $values
}
function Invoke-Logged([string]$Exe, [string[]]$Arguments, [string]$Log) {
    & $Exe @Arguments *> $Log
    $exit = $LASTEXITCODE
    [IO.File]::WriteAllText($Log + '.exit', [string]$exit, $utf8)
    Require ($exit -eq 0) ('Command failed; retained ' + $Log + ', exit=' + $exit)
}
function Check-Elf([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try { $bytes = [byte[]]::new(20); Require ($stream.Read($bytes,0,20) -eq 20) 'Truncated ELF' } finally { $stream.Dispose() }
    Require ($bytes[0] -eq 127 -and $bytes[1] -eq 69 -and $bytes[2] -eq 76 -and $bytes[3] -eq 70 -and $bytes[4] -eq 2 -and $bytes[5] -eq 1 -and $bytes[18] -eq 62 -and $bytes[19] -eq 0) ('Not target ELF64 x86_64: ' + $Path)
}
function Validate-Layout {
    Require ([bool]$SourceLayoutDirectory -and [bool]$LayoutReceiptPath) 'Supply explicit -SourceLayoutDirectory and -LayoutReceiptPath; shipping NuGet layouts are not accepted'
    $layout = Read-Json $LayoutReceiptPath
    Require ($layout.schema -eq 'runeclr.android.session-policy.layout.v1' -and $layout.success -eq $true) 'Incomplete/wrong private layout receipt'
    Require ($layout.base -eq $base -and $layout.commit -eq $candidate -and $layout.tree -eq $tree -and $layout.sourceTrackedClean -eq $true) 'Matching clean combined source identity required'
    Require ($layout.target -eq 'android.x64' -and $layout.nativeConfiguration -eq $NativeConfiguration -and $layout.frameworkConfiguration -eq 'Release') 'Explicit matching Android x64 native configuration / Release framework required'
    Require ($layout.features.interpreter -eq $true -and $layout.features.dynamicCodeCompiled -eq $true) 'Actual interpreter and dynamic-JIT feature evidence required'
    $seen = @{}; $roles = @{}
    foreach ($item in $layout.files) {
        Require ($item.role -in 'runtime','interpreter','jit','corelib','framework','os-native','ndk-native','android-java','header') ('Unexpected layout role: '+$item.role)
        Require (!$seen.ContainsKey($item.path)) ('Duplicate layout path ' + $item.path)
        $seen[$item.path] = $true
        $path = Inside $SourceLayoutDirectory $item.path
        Require ((Sha $path) -eq $item.sha256.ToLowerInvariant()) ('Layout hash mismatch: ' + $item.path)
        if ($item.role -eq 'ndk-native') { Require ([bool]$item.toolchainReceiptSha256) 'NDK dependency lacks toolchain receipt binding' }
        else { Require ($item.sourceCommit -eq $candidate) ('Wrong source owner: ' + $item.path) }
        if ($item.path -like 'native/*.so') { Check-Elf $path }
        if (!$roles.ContainsKey($item.role)) { $roles[$item.role] = @() }; $roles[$item.role] += $item.path
        Require ($item.path -match '^(managed/[^/]+\.(dll|json)|native/[^/]+\.so|java/[^/]+\.dex|headers/.+)$') ('Unexpected player input: ' + $item.path)
        if ($item.path -like 'java/*') { Require ($item.role -eq 'android-java') 'Java companion has wrong source role' }
    }
    foreach ($pair in @(@('runtime','native/libcoreclr.so'),@('interpreter','native/libclrinterpreter.so'),@('jit','native/libclrjit.so'),@('corelib','managed/System.Private.CoreLib.dll'))) {
        Require ($pair[1] -in $roles[$pair[0]]) ('Required role/file absent: ' + ($pair -join ':'))
    }
    Require ($seen.ContainsKey('managed/Microsoft.NETCore.App.deps.json') -and $seen.ContainsKey('managed/System.Runtime.dll') -and $seen.ContainsKey('native/libSystem.Native.so')) 'Complete Android framework / OS-native inventory required'
    Require ($seen.ContainsKey('headers/hosts/coreclrhost.h') -and $seen.ContainsKey('headers/native/corehost/host_runtime_contract.h')) 'Matching runtime host headers absent'
    Require ($seen.ContainsKey('java/libSystem.Security.Cryptography.Native.Android.dex')) 'Matching Android crypto Java companion absent'
    foreach ($kind in 'native-build','framework-build','source','features','trim-api','elf-needed') {
        $receipts = @($layout.receipts | Where-Object kind -eq $kind)
        Require ($receipts.Count -eq 1) ('One immutable evidence receipt required: ' + $kind)
        Require ((Sha (Inside $SourceLayoutDirectory $receipts[0].path)) -eq $receipts[0].sha256.ToLowerInvariant()) ('Receipt changed: ' + $kind)
    }
    $nativeBuild = Read-Json (Inside $SourceLayoutDirectory (@($layout.receipts | Where-Object kind -eq 'native-build')[0].path))
    Require ($nativeBuild.success -eq $true -and $nativeBuild.commit -eq $candidate -and $nativeBuild.tree -eq $tree -and $nativeBuild.target -eq 'android.x64') 'Native build did not succeed at matching source'
    $frameworkBuild = Read-Json (Inside $SourceLayoutDirectory (@($layout.receipts | Where-Object kind -eq 'framework-build')[0].path))
    Require ($frameworkBuild.success -eq $true -and $frameworkBuild.commit -eq $candidate -and $frameworkBuild.target -eq 'android.x64') 'Matching Android framework build did not succeed'
    $feature = Read-Json (Inside $SourceLayoutDirectory (@($layout.receipts | Where-Object kind -eq 'features')[0].path))
    Require ($feature.featureInterpreter -eq $true -and $feature.featureDynamicCodeCompiled -eq $true -and $feature.compileEvidenceVerified -eq $true) 'Compile evidence not verified'
    $trim = Read-Json (Inside $SourceLayoutDirectory (@($layout.receipts | Where-Object kind -eq 'trim-api')[0].path))
    Require ($trim.corelibSha256 -eq (Sha (Inside $SourceLayoutDirectory 'managed/System.Private.CoreLib.dll')) -and $trim.fixedBridgeSignaturesVerified -eq $true -and $trim.privateApiCount -eq 3) 'Trimmed CoreLib fixed bridge signatures not verified'
    $needed = Read-Json (Inside $SourceLayoutDirectory (@($layout.receipts | Where-Object kind -eq 'elf-needed')[0].path))
    Require ($needed.allDependenciesResolved -eq $true -and $needed.abi -eq 'x86_64') 'Actual ELF DT_NEEDED dependency closure missing'
    $layout
}
function Validate-Hosts {
    Require ([bool]$HostInputReceipt) 'Supply immutable frozen current-host input receipt'
    $receipt = Read-Json $HostInputReceipt
    Require ([bool]$receipt.files -and [bool]$receipt.rootsAtSnapshot) 'Expected files hash map and rootsAtSnapshot'
    foreach ($property in $receipt.files.psobject.Properties) {
        $parts = $property.Name.Replace('\','/').Split('/',2)
        $inputRoot = $receipt.rootsAtSnapshot.($parts[0])
        Require ([bool]$inputRoot) ('Unknown host root ' + $parts[0])
        $expected = if ($property.Value -is [string]) { $property.Value } else { $property.Value.sha256 }
        Require ((Sha (Inside $inputRoot $parts[1])) -eq $expected.ToLowerInvariant()) ('Frozen host changed: ' + $property.Name)
    }
    foreach ($key in 'player/RuneCLR.Runtime.dll','player/RuneCLR.Packages.dll','player/RuneCLR.Abstractions.dll','player/RuneCLR.PackageExecution.Tests.dll','lifecycle/RuneCLR.Runtime.Tests.dll','sample/RuneCLR.SampleHost.dll') { Require ([bool]$receipt.files.$key) ('Required current host absent: ' + $key) }
    $receipt
}
function Test-Functional([string]$Name, [string]$Text, $Managed) {
    Require ($Managed.exitCode -eq 0 -and $Managed.policyVersion -eq 1 -and $Managed.requiredPolicy -eq 1 -and $Managed.ordinaryPolicy -eq 0 -and $Managed.defaultPolicy -eq 0) 'Managed exit / native policy acknowledgement failed'
    if ($Name -in 'all','lifecycle') { Require ($Text -match '(?m)^24/24 tests passed\r?$' -and $Text -notmatch '(?m)^FAIL ') 'Current 24/24 lifecycle including late IL required' }
    if ($Name -in 'all','packages') { Require ($Text -match '(?m)^15/15 package execution tests passed\.\r?$' -and $Text -notmatch '(?m)^FAIL ') 'Current package 15/15 required' }
    if ($Name -in 'all','sample') { Require (@([regex]::Matches($Text,'(?m)^  unload: collected\r?$')).Count -eq 3 -and $Text -notmatch 'Cannot run map:') 'Three sample contexts must collect' }
    if ($Name -in 'all','sample','packages','lifecycle') { Require ($Text.Contains('SESSION_EXECUTION_POLICY required-interpreter version=1')) 'Host acknowledged policy marker absent' }
}
if ($Phase -eq 'SelfTest') {
    $managed = [pscustomobject]@{exitCode=0;policyVersion=1;requiredPolicy=1;ordinaryPolicy=0;defaultPolicy=0}
    $text = @'
24/24 tests passed
15/15 package execution tests passed.
SESSION_EXECUTION_POLICY required-interpreter version=1
  unload: collected
  unload: collected
  unload: collected
'@
    Test-Functional 'all' $text $managed
    foreach ($bad in @($text.Replace('24/24','23/24'),$text.Replace('15/15','14/15'),$text.Replace('version=1','version=0'),$text.Replace('  unload: collected','  unload: pending'))) {
        $rejected = $false; try { Test-Functional 'all' $bad $managed } catch { $rejected = $true }; Require $rejected 'Offline negative parser test accepted incomplete results'
    }
    $escaped = $false; try { $null = Inside $repo '../outside' } catch { $escaped = $true }; Require $escaped 'Path containment failed'
    if($HostInputReceipt){$null=Validate-Hosts;Write-Host 'Frozen current-host input SHA validation PASS (read-only).'}
    if(Test-Path -LiteralPath "$BuilderDirectory/Templates/monodroid-coreclr.c") {
        $nativeTemplate=Get-Content -LiteralPath "$BuilderDirectory/Templates/monodroid-coreclr.c" -Raw
        foreach($anchor in @('    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);','    coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);','    LOG_INFO ("coreclr_initialize returned 0x%x", rv);')){Require ($nativeTemplate.Contains($anchor)) 'Offline JNI native template anchor changed'}
        $javaTemplate=Get-Content -LiteralPath "$BuilderDirectory/Templates/MonoRunner.java" -Raw
        Require ($javaTemplate.Contains('        int rv = initRuntime(filesDir, entryPointLibName, localDateTimeOffset);')) 'Offline Java PID-query template anchor changed'
        Write-Host 'Existing builder JNI/Java transformation anchors PASS (read-only).'
    }
    Write-Host 'Offline parser/path self-test PASS; no Android product execution.'; return
}
if ($Phase -in 'Validate','Build') {
    $layout = Validate-Layout; $hosts = Validate-Hosts
    if ($Phase -eq 'Validate') { Write-Host 'Private layout and frozen-host hash validation PASS; execution unmeasured.'; return }
}
Require ([bool]$EvidenceDirectory) 'Supply -EvidenceDirectory for an isolated build or an existing phase state'
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory)
$statePath = Join-Path $evidence 'state.json'
$sdk = Join-Path $AndroidRoot 'sdk'; $ndk = Join-Path $sdk 'ndk/27.2.12479018'; $java = Join-Path $AndroidRoot 'android-studio/jbr'
$adb = Join-Path $sdk 'platform-tools/adb.exe'
function Adb([string[]]$Arguments) {
    Require ([bool]$DeviceSerial) 'Explicit already-running -DeviceSerial required; no emulator startup is provided'
    $output = & $adb -s $DeviceSerial @Arguments 2>&1; $status = $LASTEXITCODE
    Require ($status -eq 0) ('ADB failed: ' + ($Arguments -join ' ') + ' ' + ($output -join [Environment]::NewLine))
    ($output -join [Environment]::NewLine).Trim()
}
function Check-Device {
    Require (!$Offline) 'Offline mode forbids device operations'
    Require ((Adb @('get-state')) -eq 'device') 'Requested device not connected'
    Require ((Adb @('shell','uname','-m')) -eq 'x86_64') 'This driver targets actual x86_64 kernel only'
    if ($ExpectedAvdName) { Require ((Adb @('emu','avd','name')) -match [regex]::Escape($ExpectedAvdName)) 'Wrong owned AVD' }
}
function Pull-Owned([string]$Relative, [string]$Output, [switch]$Optional) {
    Require ($Relative -match '^files/[A-Za-z0-9_./-]+$' -and $Relative -notmatch '\.\.') 'Invalid owned app file'
    $info = [Diagnostics.ProcessStartInfo]::new($adb)
    foreach ($arg in @('-s',$DeviceSerial,'exec-out','run-as',$state.package,'cat',$Relative)) { $info.ArgumentList.Add($arg) }
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $process = [Diagnostics.Process]::Start($info); $errorTask = $process.StandardError.ReadToEndAsync()
    $stream = [IO.File]::Create($Output)
    try { $process.StandardOutput.BaseStream.CopyTo($stream) } finally { $stream.Dispose() }
    $process.WaitForExit(); $errorText = $errorTask.GetAwaiter().GetResult()
    if (!$Optional) { Require ($process.ExitCode -eq 0) ('Owned log read failed: ' + $Relative + ': ' + $errorText) }
    elseif ($process.ExitCode -ne 0) { Remove-Item -LiteralPath $Output }
}
function Check-Installed([string]$Log) {
    $records = [ordered]@{}; $lines = [Collections.Generic.List[string]]::new()
    foreach ($property in $state.appHashes.psobject.Properties) {
        if ($property.Name -like '*.so') { continue }
        $line = Adb @('shell','run-as',$state.package,'sha256sum',('files/' + $property.Name))
        Require ($line.StartsWith($property.Value,[StringComparison]::OrdinalIgnoreCase)) ('Installed trusted input changed: ' + $property.Name)
        $records[$property.Name] = $property.Value; $lines.Add($line)
    }
    $apkPath = (Adb @('shell','pm','path',$state.package)) -replace '^package:',''
    Require ($apkPath -notmatch '[\r\n]') 'Unexpected split APK layout'
    $line = Adb @('shell','sha256sum',$apkPath)
    Require ($line.StartsWith($state.apkSha256,[StringComparison]::OrdinalIgnoreCase)) 'Installed APK changed'
    $lines.Add($line)
    foreach ($property in $state.payloadHashes.psobject.Properties) {
        $line = Adb @('shell','run-as',$state.package,'sha256sum',('files/' + $property.Name))
        Require ($line.StartsWith($property.Value,[StringComparison]::OrdinalIgnoreCase)) ('Installed author input changed: ' + $property.Name)
        $records[$property.Name] = $property.Value; $lines.Add($line)
    }
    [IO.File]::WriteAllLines($Log,$lines,$utf8); $records
}
if ($Phase -eq 'Build') {
    Require (!(Test-Path -LiteralPath $evidence)) 'Build requires a fresh evidence directory; preserve previous attempts'
    New-Item -ItemType Directory -Path $evidence | Out-Null
    $app = Join-Path $evidence 'app'; $builder = Join-Path $evidence 'builder'; $wrapperRoot = Join-Path $evidence 'wrapper'
    New-Item -ItemType Directory -Path $app,$builder,$wrapperRoot | Out-Null
    Write-Json "$evidence/layout-receipt.json" $layout
    Copy-Item -LiteralPath $LayoutReceiptPath -Destination "$evidence/original-layout.json"
    Copy-Item -LiteralPath $HostInputReceipt -Destination "$evidence/host-inputs.json"
    Copy-Item -LiteralPath $PSCommandPath -Destination "$evidence/driver.ps1"
    foreach($receipt in @($layout.receipts)+@($layout.evidenceFiles)) {
        if(!$receipt){continue}
        $source=Inside $SourceLayoutDirectory $receipt.path;Require ((Sha $source) -eq $receipt.sha256.ToLowerInvariant()) ('Provenance file changed: '+$receipt.path)
        $target=Inside "$evidence/provenance" $receipt.path;New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null;Copy-Item -LiteralPath $source -Destination $target
    }
    foreach ($item in $layout.files) {
        $source = Inside $SourceLayoutDirectory $item.path
        if ($item.path -match '^(managed|native|java)/') { $destination = Join-Path $app ([IO.Path]::GetFileName($item.path)) }
        else { $destination = Inside $evidence $item.path; New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null }
        Require (!(Test-Path -LiteralPath $destination)) ('Input basename collision: ' + $item.path)
        Copy-Item -LiteralPath $source -Destination $destination
    }
    $hostHashes = [ordered]@{}
    foreach ($property in $hosts.files.psobject.Properties) {
        $key = $property.Name.Replace('\','/'); $parts = $key.Split('/',2)
        $rootPath = $hosts.rootsAtSnapshot.($parts[0]); $relative = $parts[1]
        $trusted = ($parts[0] -in 'player','lifecycle','sample' -and $relative -notmatch '/' -and $relative -like '*.dll') -or $key -like 'selection/trusted/*.dll'
        if (!$trusted) { continue }
        $source = Inside $rootPath $relative; $name = [IO.Path]::GetFileName($relative); $hash = Sha $source
        if (Test-Path -LiteralPath "$app/$name") { Require ((Sha "$app/$name") -eq $hash) ('Trusted duplicate differs: ' + $name) }
        else { Copy-Item -LiteralPath $source -Destination "$app/$name" }
        $hostHashes[$name] = $hash
    }
    foreach ($name in 'RuneCLR.Runtime.dll','RuneCLR.Packages.dll','RuneCLR.Abstractions.dll','RuneCLR.Runtime.Tests.dll','RuneCLR.PackageExecution.Tests.dll','RuneCLR.SampleHost.dll') { Require ($hostHashes.Contains($name)) ('Trusted input absent ' + $name) }
    $builderHashes = File-Identity $BuilderDirectory
    Get-ChildItem -LiteralPath $BuilderDirectory -Force | Where-Object Name -notin 'bin','obj' | Copy-Item -Destination $builder -Recurse
    # Modify a private resource copy, retaining both original and generated hashes.
    $templatePath = "$builder/Templates/monodroid-coreclr.c"
    $template = Get-Content -LiteralPath $templatePath -Raw
    $nativeSetup = @'
    const char* run_id = getenv("RUNECLR_SESSION_RUN_ID");
    const char* mode = getenv("RUNECLR_SESSION_MODE");
    const char* lane = getenv("RUNECLR_SESSION_LANE");
    if (run_id == NULL || strlen(run_id) != 32 || strspn(run_id, "0123456789abcdef") != 32 || mode == NULL || (strcmp(mode,"0") && strcmp(mode,"1"))) return -1;
    char native_path[2048], jit_path[2048];
    snprintf(native_path, sizeof(native_path), "%s/session-%s.native.log", g_bundle_path, run_id);
    snprintf(jit_path, sizeof(jit_path), "%s/session-%s.jit.log", g_bundle_path, run_id);
    if (freopen(native_path,"w",stdout) == NULL || dup2(fileno(stdout),fileno(stderr)) < 0) return -1;
    setvbuf(stdout,NULL,_IONBF,0); setvbuf(stderr,NULL,_IONBF,0);
    setenv("DOTNET_InterpMode",mode,1);
    setenv("DOTNET_RuneCLRInterpretCollectible","0",1);
    setenv("DOTNET_ReadyToRun","1",1);
    setenv("DOTNET_TieredCompilation",lane && strstr(lane,"inline") ? "0" : "1",1);
    setenv("DOTNET_InterpList","1",1);
    setenv("DOTNET_InterpDump","*:*",1);
    setenv("DOTNET_JitDisasmSummary","1",1);
    setenv("DOTNET_JitStdOutFile",jit_path,1);
    if (lane && (!strcmp(lane,"required-refusal") || !strcmp(lane,"unmarked-fallback")))
        setenv("DOTNET_RuneCLRInterpreterRefuseMethods","SelectionUGC.Refusal.Entry:Reject",1);
    else unsetenv("DOTNET_RuneCLRInterpreterRefuseMethods");
    setenv("DOTNET_JitNoInline","0",1);
    if (lane && strstr(lane,"inline")) {
        setenv("DOTNET_JitDump","TrustedInlineCaller:NativeInlineCall",1);
        setenv("DOTNET_JitPrintInlinedMethods","TrustedInlineCaller:NativeInlineCall",1);
    } else { unsetenv("DOTNET_JitDump"); unsetenv("DOTNET_JitPrintInlinedMethods"); }
    printf("ANDROID_SESSION_NATIVE pid=%d runId=%s InterpMode=%s RuneCLRInterpretCollectible=0\n",getpid(),run_id,mode);
'@
    $anchor = '    setenv ("DOTNET_CrashReportBeforeSignalChaining", "1", true);'
    Require ($template.Contains($anchor)) 'JNI initialization anchor changed; review upstream builder'
    $template = $template.Replace($anchor, $anchor + [Environment]::NewLine + $nativeSetup)
    $execute = '    coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);'
    Require ($template.Contains($execute)) 'JNI execution anchor changed'
    $template = $template.Replace('    unsigned int rv;', '    unsigned int rv = 255;').Replace($execute, '    int execute_hr = coreclr_execute_assembly (coreclr_handle, coreclr_domainId, managed_argc, managed_argv, executable_path, &rv);' + [Environment]::NewLine + '    printf("CORECLR_EXECUTE_HRESULT=0x%x;RUNECLR_EXIT=%u\n",execute_hr,rv);' + [Environment]::NewLine + '    if (execute_hr != 0) return 255;')
    $initialize = '    LOG_INFO ("coreclr_initialize returned 0x%x", rv);'
    Require ($template.Contains($initialize)) 'JNI CoreCLR initialization marker changed'
    $template = $template.Replace($initialize, $initialize + [Environment]::NewLine + '    printf("CORECLR_INITIALIZE_HRESULT=0x%x\n",rv);')
    $shutdown='        coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);'
    Require ($template.Contains($shutdown)) 'JNI shutdown anchor changed'
    $template=$template.Replace($shutdown,'        int shutdown_hr = coreclr_shutdown (g_coreclr_handle, g_coreclr_domainId);'+[Environment]::NewLine+'        printf("CORECLR_SHUTDOWN_HRESULT=0x%x\n",shutdown_hr);')
    [IO.File]::WriteAllText($templatePath,$template,$utf8)
    # Independent PID query before runtime initialization; do not derive it from managed output.
    $javaPath = "$builder/Templates/MonoRunner.java"
    $javaSource = Get-Content -LiteralPath $javaPath -Raw
    $javaAnchor = '        int rv = initRuntime(filesDir, entryPointLibName, localDateTimeOffset);'
    Require ($javaSource.Contains($javaAnchor)) 'JNI Java initialization anchor changed'
    $pidQuery = @'
        try {
            String runId = android.system.Os.getenv("RUNECLR_SESSION_RUN_ID");
            if (runId == null || !runId.matches("[0-9a-f]{32}")) throw new RuntimeException("Missing owned run id");
            java.io.File pidFile = new java.io.File(filesDir,"session-"+runId+".pid-query.txt");
            java.io.FileOutputStream pidStream = new java.io.FileOutputStream(pidFile);
            pidStream.write(("android.os.Process.myPid="+android.os.Process.myPid()+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8));
            pidStream.close();
        } catch (java.io.IOException error) { throw new RuntimeException(error); }
'@
    [IO.File]::WriteAllText($javaPath,$javaSource.Replace($javaAnchor,$pidQuery + [Environment]::NewLine + $javaAnchor),$utf8)
    '<Project />' | Set-Content -LiteralPath "$evidence/Directory.Build.props"
    Copy-Item -LiteralPath "$repo/global.json" -Destination "$evidence/global.json"
    @'
<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><AssemblyName>RuneCLR.AndroidSessionHost</AssemblyName></PropertyGroup></Project>
'@ | Set-Content -LiteralPath "$wrapperRoot/host.csproj"
    @'
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text.Json;
var root = AppContext.BaseDirectory;
var runId = Environment.GetEnvironmentVariable("RUNECLR_SESSION_RUN_ID") ?? throw new InvalidOperationException("No owned run id");
var lane = Environment.GetEnvironmentVariable("RUNECLR_SESSION_LANE") ?? throw new InvalidOperationException("No lane");
var prefix = Path.Combine(root,"session-"+runId);
var originalOut = Console.Out; var originalError = Console.Error;
int exitCode = 1, policyVersion = -1, defaultPolicy = -1, ordinaryPolicy = -1, requiredPolicy = -1;
using (var writer = new StreamWriter(prefix+".managed.log") { AutoFlush = true }) {
    // SelectionProbe explicitly SetOut(Console.Error); both streams must use the same owned writer.
    Console.SetOut(writer); Console.SetError(writer);
    try {
        var flags = BindingFlags.NonPublic | BindingFlags.Static;
        var versionMethod = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicyVersion",flags,null,Type.EmptyTypes,null);
        var factoryMethod = typeof(AssemblyLoadContext).GetMethod("RuneCLR_CreateInterpreterRequired",flags,null,[typeof(string),typeof(Func<AssemblyLoadContext,AssemblyName,Assembly>)],null);
        var queryMethod = typeof(AssemblyLoadContext).GetMethod("RuneCLR_GetExecutionPolicy",BindingFlags.NonPublic|BindingFlags.Instance,null,Type.EmptyTypes,null);
        if (versionMethod?.ReturnType != typeof(int) || factoryMethod?.ReturnType != typeof(AssemblyLoadContext) || queryMethod?.ReturnType != typeof(int)) throw new PlatformNotSupportedException("Fixed trusted CoreLib bridge unavailable");
        var version = versionMethod.CreateDelegate<Func<int>>();
        var factory = factoryMethod.CreateDelegate<Func<string,Func<AssemblyLoadContext,AssemblyName,Assembly?>,AssemblyLoadContext>>();
        var query = queryMethod.CreateDelegate<Func<AssemblyLoadContext,int>>();
        policyVersion = version(); defaultPolicy = query(AssemblyLoadContext.Default);
        var ordinary = new AssemblyLoadContext("android-preflight-ordinary",true);
        AssemblyLoadContext? required = null;
        try {
            ordinaryPolicy = query(ordinary);
            required = factory("android-preflight-required", (_,_)=>null);
            requiredPolicy = query(required);
            if (policyVersion != 1 || defaultPolicy != 0 || ordinaryPolicy != 0 || requiredPolicy != 1 || !required.IsCollectible || required.GetType().Assembly != typeof(object).Assembly) throw new PlatformNotSupportedException("Native policy acknowledgement invalid");
        } finally { required?.Unload(); ordinary.Unload(); }
        Console.WriteLine($"ANDROID_SESSION_POLICY version={policyVersion} default={defaultPolicy} ordinary={ordinaryPolicy} required={requiredPolicy}");
        Console.WriteLine($"ANDROID_SESSION_MANAGED pid={Environment.ProcessId} runId={runId} lane={lane} framework={RuntimeInformation.FrameworkDescription} arch={RuntimeInformation.ProcessArchitecture}");
        int Invoke(string dll, string[] args) {
            var entry = Assembly.LoadFrom(Path.Combine(root,dll)).EntryPoint ?? throw new InvalidOperationException("Trusted entrypoint missing");
            var result = entry.Invoke(null,entry.GetParameters().Length==0 ? null : [args]);
            return result is Task<int> task ? task.GetAwaiter().GetResult() : result is int code ? code : 0;
        }
        exitCode = 0;
        if (lane is "all" or "lifecycle") {
            var late = Path.Combine(root,"late","map.json");
            if (!File.Exists(late)) throw new InvalidOperationException("Post-install late IL required for current 24-case lane");
            exitCode |= Invoke("RuneCLR.Runtime.Tests.dll",["--late-map",late,"--require-interpreter"]);
        }
        if (lane is "all" or "packages") exitCode |= Invoke("RuneCLR.PackageExecution.Tests.dll",["--packages",Path.Combine(root,"controlled"),"--require-interpreter"]);
        if (lane is "all" or "sample") exitCode |= Invoke("RuneCLR.SampleHost.dll",["--collect","--require-interpreter"]);
        if (lane is not ("all" or "lifecycle" or "packages" or "sample")) {
            var directory = Path.Combine(root,"plugin"); var evidence = Path.Combine(root,"probe-evidence-"+runId);
            Environment.SetEnvironmentVariable("RUNECLR_PROBE_FACTORY",lane is "ordinary" or "unmarked-fallback" or "ordinary-inline" ? "ordinary" : "required");
            string[] probeArgs = lane switch {
                "required-refusal" => [directory,evidence,"--refusal-required",Path.Combine(directory,"Refusal")],
                "unmarked-fallback" => [directory,evidence,"--refusal-fallback",Path.Combine(directory,"Refusal")],
                "required-boxed" => [directory,evidence,"--bridges",Path.Combine(directory,"Boxed")],
                "required-inline" or "ordinary-inline" => [directory,evidence,"--inline",Path.Combine(directory,"Inline")],
                _ => [directory,evidence] };
            exitCode |= Invoke("SelectionProbe.Host.dll",probeArgs);
        }
    } catch(Exception error) { exitCode=1; Console.Error.WriteLine((error is TargetInvocationException {InnerException:not null} invocation ? invocation.InnerException! : error).ToString()); }
    finally { Console.SetOut(originalOut); Console.SetError(originalError); }
}
File.WriteAllText(prefix+".maps.log",File.Exists("/proc/self/maps") ? File.ReadAllText("/proc/self/maps") : "unavailable on this platform");
File.WriteAllText(prefix+".managed-result.json",JsonSerializer.Serialize(new {runId,lane,exitCode,appPid=Environment.ProcessId,policyVersion,defaultPolicy,ordinaryPolicy,requiredPolicy}));
return exitCode;
'@ | Set-Content -LiteralPath "$wrapperRoot/Program.cs"
    @'
<Project>
 <UsingTask TaskName="AndroidAppBuilderTask" AssemblyFile="$(MSBuildThisFileDirectory)builder/bin/Release/net11.0/AndroidSmokeBuilder.dll" />
 <Target Name="Build">
  <AndroidAppBuilderTask AppDir="$(MSBuildThisFileDirectory)app" MainLibraryFileName="RuneCLR.AndroidSessionHost.dll" RuntimeIdentifier="android-x64" RuntimeFlavor="CoreCLR" ProjectName="$(AndroidProjectName)" OutputDir="$(MSBuildThisFileDirectory)apk" AndroidSdk="$(AndroidSdk)" AndroidNdk="$(AndroidNdk)" RuntimeHeaders="$(MSBuildThisFileDirectory)headers/hosts;$(MSBuildThisFileDirectory)headers/native" BuildApiLevel="36" BuildToolsVersion="35.0.1" TargetApiLevel="35" MinApiLevel="24" StaticLinkedRuntime="false" ForceInterpreter="false" ForceAOT="false" StripDebugSymbols="false" />
 </Target>
</Project>
'@ | Set-Content -LiteralPath "$evidence/package.proj"
    $name = 'RuneCLR_Session_' + [Guid]::NewGuid().ToString('N').Substring(0,12)
    $dotnet = (Get-Command $DotnetExecutable).Source
    $saved = @{PATH=$env:PATH;JAVA_HOME=$env:JAVA_HOME;ANDROID_SDK_ROOT=$env:ANDROID_SDK_ROOT;ANDROID_HOME=$env:ANDROID_HOME;CPATH=$env:CPATH;C_INCLUDE_PATH=$env:C_INCLUDE_PATH;CPLUS_INCLUDE_PATH=$env:CPLUS_INCLUDE_PATH;LIBRARY_PATH=$env:LIBRARY_PATH;SDKROOT=$env:SDKROOT;MACOSX_DEPLOYMENT_TARGET=$env:MACOSX_DEPLOYMENT_TARGET}
    try {
        foreach($key in 'CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','SDKROOT','MACOSX_DEPLOYMENT_TARGET'){Remove-Item -LiteralPath ('Env:'+$key) -ErrorAction SilentlyContinue}
        $env:PATH = "$java/bin;C:/Program Files/Microsoft Visual Studio/2022/Professional/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja;" + $env:PATH
        $env:JAVA_HOME = $java; $env:ANDROID_SDK_ROOT=$sdk; $env:ANDROID_HOME=$sdk
        Push-Location $evidence
        try {
            Invoke-Logged $dotnet @('build','builder/builder.csproj','-c','Release') "$evidence/builder-build.log"
            Invoke-Logged $dotnet @('build','wrapper/host.csproj','-c','Release','-o',"$evidence/wrapper-output") "$evidence/wrapper-build.log"
            Copy-Item -LiteralPath "$evidence/wrapper-output/RuneCLR.AndroidSessionHost.dll" -Destination $app
            [IO.File]::WriteAllBytes("$app/runtimeconfig.bin",[byte[]]@(0))
            Invoke-Logged $dotnet @('msbuild','package.proj','/t:Build',('/p:AndroidSdk='+$sdk),('/p:AndroidNdk='+$ndk),('/p:AndroidProjectName='+$name),'/v:minimal') "$evidence/apk-build.log"
        } finally { Pop-Location }
    } finally { foreach ($key in $saved.Keys) { Set-Item -LiteralPath ('Env:'+$key) -Value $saved[$key] } }
    $apk = "$evidence/apk/bin/$name.apk"; Require (Test-Path -LiteralPath $apk) 'APK missing'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($apk); $packaged = [ordered]@{};$apkNativeHashes=[ordered]@{}
    try {
        foreach($entry in $zip.Entries |Where-Object FullName -like 'lib/*/*.so') {
            Require ($entry.FullName -like 'lib/x86_64/*.so') 'Unexpected APK native ABI'
            $entryStream=$entry.Open();try{$memory=[IO.MemoryStream]::new();$entryStream.CopyTo($memory);$bytes=$memory.ToArray();Require ($bytes.Length -gt 20 -and $bytes[0] -eq 127 -and $bytes[1] -eq 69 -and $bytes[2] -eq 76 -and $bytes[3] -eq 70 -and $bytes[4] -eq 2 -and $bytes[5] -eq 1 -and $bytes[18] -eq 62 -and $bytes[19] -eq 0) 'APK includes non-target native executable';$apkNativeHashes[$entry.FullName]=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant();$memory.Dispose()}finally{$entryStream.Dispose()}
        }
        $assetsEntry = $zip.GetEntry('assets/assets.zip'); Require ([bool]$assetsEntry) 'Actual APK nested assets missing'
        $stream = $assetsEntry.Open(); $assets = [IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Read)
        try {
            foreach ($entry in $assets.Entries) {
                if ($entry.FullName.EndsWith('/')) { continue }
                Require ($entry.FullName -notmatch '(^|/)(fixtures|dependency-a|dependency-b|maps|plugin|controlled|late)/|Microsoft.CodeAnalysis|RuneCLR.Compiler|RuneCLR.PackageTool|RuneCLR.PackageFixtures') ('Untrusted/operator material inside APK: '+$entry.FullName)
                $entryStream=$entry.Open(); try { $hash=[Security.Cryptography.SHA256]::Create(); $digest=$hash.ComputeHash($entryStream); $packaged[$entry.FullName]=[Convert]::ToHexString($digest).ToLowerInvariant(); $hash.Dispose() } finally {$entryStream.Dispose()}
            }
        } finally { $assets.Dispose(); $stream.Dispose() }
        foreach ($file in Get-ChildItem -LiteralPath $app -File) {
            if ($file.Name -like '*.so') { $entry=$zip.GetEntry('lib/x86_64/'+$file.Name); Require ([bool]$entry) ('Target native absent in APK: '+$file.Name); $entryStream=$entry.Open(); try {$hash=[Security.Cryptography.SHA256]::Create();$digest=$hash.ComputeHash($entryStream);$packaged[$file.Name]=[Convert]::ToHexString($digest).ToLowerInvariant();$hash.Dispose()}finally{$entryStream.Dispose()} }
            if ($file.Name -like '*.dex') {
                $dexMatchedEntries = @()
                foreach ($entry in $zip.Entries | Where-Object FullName -match '^classes([2-9]|[1-9][0-9]+)\.dex$') {
                    $entryStream=$entry.Open()
                    try {$hash=[Security.Cryptography.SHA256]::Create();$digest=[Convert]::ToHexString($hash.ComputeHash($entryStream)).ToLowerInvariant();$hash.Dispose()} finally {$entryStream.Dispose()}
                    if ($digest -eq (Sha $file.FullName)) { $dexMatchedEntries += $entry.FullName }
                }
                Require ($dexMatchedEntries.Count -eq 1) ('Matching Java companion must appear once as APK classesN.dex: '+$file.Name)
                $packaged[$file.Name] = Sha $file.FullName
            }
            Require ($packaged[$file.Name] -eq (Sha $file.FullName)) ('APK changed staged input: '+$file.Name)
        }
    } finally { $zip.Dispose() }
    $artifactHashes=[ordered]@{}; foreach($file in $layout.files | Where-Object {$_.role -in 'runtime','interpreter','jit','corelib','os-native','ndk-native'}) {$artifactHashes[[IO.Path]::GetFileName($file.path)]=$file.sha256.ToLowerInvariant()}
    Write-Json "$evidence/product-manifest.json" @{platform='android';abi='x86_64';configuration=$layout.nativeConfiguration;base=$base;commit=$candidate;tree=$tree;sourceTrackedClean=$true;featureInterpreter=$true;featureDynamicCodeCompiled=$true;artifactHashes=$artifactHashes;layoutReceiptSha256=(Sha "$evidence/original-layout.json");evidenceReceipts=$layout.receipts;scope='Private matching source layout, not shipping NuGet'}
    $state=[ordered]@{schema='runeclr.android.session-policy.state.v1';prepared=$true;executionVerified=$false;createdUtc=[DateTime]::UtcNow.ToString('o');package=('net.dot.'+$name);apk=$apk;apkSha256=(Sha $apk);candidateCommit=$candidate;tree=$tree;layoutReceiptSha256=(Sha "$evidence/original-layout.json");productManifestSha256=(Sha "$evidence/product-manifest.json");hostReceiptSha256=(Sha "$evidence/host-inputs.json");currentHostHashes=$hostHashes;appHashes=(File-Identity $app);packagedHashes=$packaged;apkNativeHashes=$apkNativeHashes;payloadHashes=@{};builderSourceCommit=$BuilderSourceCommit;builderOriginalHashes=$builderHashes;builderGeneratedHashes=(File-Identity $builder);wrapperSourceHashes=(File-Identity $wrapperRoot);driverSha256=(Sha $PSCommandPath);sdk=(& $dotnet --version);tools=@{dotnetPath=$dotnet;dotnetSha256=(Sha $dotnet);ndkProperties=(Get-Content -LiteralPath "$ndk/source.properties" -Raw);ndkPropertiesSha256=(Sha "$ndk/source.properties");clangSha256=(Sha "$ndk/toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe");javaSha256=(Sha "$java/bin/javac.exe");adbSha256=(Sha $adb)};scope='Prepared APK only; Android interpretation/policy not yet measured'}
    Write-Json $statePath $state; Write-Host ('Prepared private-source APK: '+$apk); return
}
$state=Read-Json $statePath
Require ($state.schema -eq 'runeclr.android.session-policy.state.v1' -and $state.candidateCommit -eq $candidate) 'Wrong phase state'
Require ((Sha $state.apk) -eq $state.apkSha256 -and (Sha "$evidence/product-manifest.json") -eq $state.productManifestSha256 -and (Sha "$evidence/host-inputs.json") -eq $state.hostReceiptSha256) 'Frozen APK/product/host receipt changed'
Require ((Sha "$evidence/original-layout.json") -eq $state.layoutReceiptSha256) 'Frozen layout receipt changed'
$frozenLayout = Read-Json "$evidence/original-layout.json"
foreach ($receipt in @($frozenLayout.receipts) + @($frozenLayout.evidenceFiles)) {
    if ($receipt) { Require ((Sha (Inside "$evidence/provenance" $receipt.path)) -eq $receipt.sha256.ToLowerInvariant()) ('Frozen provenance receipt changed: ' + $receipt.path) }
}
foreach($property in $state.appHashes.psobject.Properties) {Require ((Sha (Inside "$evidence/app" $property.Name)) -eq $property.Value) ('Frozen host/product input changed '+$property.Name)}
function Push-Owned([string]$Source,[string]$Relative,[string]$Log) {
    $null=Inside "$evidence/device-path-check" $Relative
    Require ($Relative -match '^[A-Za-z0-9_./-]+$') 'Device path contains unsupported characters'
    $stage='/data/local/tmp/runeclr-session-'+[Guid]::NewGuid().ToString('N')
    $null=Adb @('push',$Source,$stage)
    try {
        $parent=($Relative -replace '/[^/]+$',''); if($parent -eq $Relative){$parent=''}
        $null=Adb @('shell','run-as',$state.package,'mkdir','-p',('files/'+$parent))
        $null=Adb @('shell','run-as',$state.package,'cp',$stage,('files/'+$Relative))
        $hash=Sha $Source; $line=Adb @('shell','run-as',$state.package,'sha256sum',('files/'+$Relative))
        Require ($line.StartsWith($hash,[StringComparison]::OrdinalIgnoreCase)) ('Transferred file mismatch '+$Relative)
        Add-Content -LiteralPath $Log -Value $line
    } finally { $null=Adb @('shell','rm',$stage) }
}
if($Phase -eq 'Install') {
    Check-Device
    Require (!$state.installedUtc) 'Already installed; preserve state and do not replace APK'
    $installed=Adb @('shell','pm','list','packages',$state.package)
    Require (!$installed.Contains('package:'+$state.package)) 'Unique app ID unexpectedly exists; use fresh Build output'
    Invoke-Logged $adb @('-s',$DeviceSerial,'install',$state.apk) "$evidence/install.log"
    $null=Adb @('shell','run-as',$state.package,'mkdir','-p','files')
    # Exact validated APK assets are materialized before first app startup for pre-run device hash reads.
    foreach($property in $state.appHashes.psobject.Properties) {if($property.Name -notlike '*.so'){Push-Owned (Inside "$evidence/app" $property.Name) $property.Name "$evidence/install-hash-reads.log"}}
    $state | Add-Member -NotePropertyName installedUtc -NotePropertyValue ([DateTime]::UtcNow.ToString('o'))
    $state | Add-Member -NotePropertyName deviceSerial -NotePropertyValue $DeviceSerial
    $state | Add-Member -NotePropertyName device -NotePropertyValue @{kernelArchitecture=(Adb @('shell','uname','-m'));api=(Adb @('shell','getprop','ro.build.version.sdk'));pageSize=(Adb @('shell','getconf','PAGESIZE'));avd=$ExpectedAvdName}
    $null=Check-Installed "$evidence/installed-identity.log"
    Write-Json $statePath $state; Write-Host ('Installed new owned app '+$state.package+'; no app execution.'); return
}
if($Phase -eq 'Produce') {
    Require ([bool]$state.installedUtc) 'Operator generation must follow recorded APK installation'
    Require ([bool]$FixtureGenerator -and [bool]$FrameworkReferences) 'Provide prebuilt operator FixtureGenerator and fixed FrameworkReferences'
    $operator=(Get-Command $OperatorDotnetExecutable).Source
    $started=[DateTime]::UtcNow; Require ($started -gt [DateTime]::Parse($state.installedUtc)) 'Operator start is not after install'
    $output="$evidence/payloads-"+[Guid]::NewGuid().ToString('N'); New-Item -ItemType Directory -Path $output | Out-Null
    $frozen=Read-Json "$evidence/host-inputs.json"
    foreach($property in $frozen.files.psobject.Properties) {
        $parts=$property.Name.Replace('\','/').Split('/',2);$relative=$parts[1]
        $destination=if($parts[0] -eq 'lifecycle' -and $relative -match '^(fixtures|dependency-a|dependency-b)/'){$relative}elseif($parts[0] -eq 'sample' -and $relative -like 'maps/*'){$relative}elseif($parts[0] -eq 'selection' -and $relative -like 'plugin/*'){$relative}else{$null}
        if(!$destination){continue}
        $source=Inside $frozen.rootsAtSnapshot.($parts[0]) $relative
        $expected=if($property.Value -is [string]){$property.Value}else{$property.Value.sha256}
        Require ((Sha $source) -eq $expected) ('Frozen author fixture changed '+$property.Name)
        $target=Inside $output $destination;New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null;Copy-Item -LiteralPath $source -Destination $target
    }
    Invoke-Logged $operator @($FixtureGenerator,'--framework-refs',$FrameworkReferences,'--contract',"$evidence/app/RuneCLR.Abstractions.dll",'--output',"$output/controlled") "$output/operator-generation.log"
    if(!$LateSourceDirectory){$LateSourceDirectory="$repo/tests/RuneCLR.LateMap"}
    $lateProject="$output/late-source";New-Item -ItemType Directory -Path $lateProject|Out-Null
    Get-ChildItem -LiteralPath $LateSourceDirectory -File |Where-Object Extension -eq '.cs'|Copy-Item -Destination $lateProject
    $contract=[Security.SecurityElement]::Escape("$evidence/app/RuneCLR.Abstractions.dll")
    [IO.File]::WriteAllText("$lateProject/late.csproj",('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><AssemblyName>RuneCLR.LateMap</AssemblyName><Deterministic>false</Deterministic></PropertyGroup><ItemGroup><Reference Include="RuneCLR.Abstractions"><HintPath>'+ $contract +'</HintPath></Reference></ItemGroup></Project>'),$utf8)
    Invoke-Logged $operator @('build',"$lateProject/late.csproj",'-c','Release','-o',"$output/late-build") "$output/late-build.log"
    New-Item -ItemType Directory -Path "$output/late"|Out-Null
    Copy-Item -LiteralPath "$output/late-build/RuneCLR.LateMap.dll" -Destination "$output/late"
    Copy-Item -LiteralPath "$LateSourceDirectory/map.json" -Destination "$output/late"
    $files=[ordered]@{};foreach($directory in 'fixtures','dependency-a','dependency-b','maps','plugin','controlled','late') {
        if(Test-Path -LiteralPath "$output/$directory"){foreach($entry in (File-Identity "$output/$directory").GetEnumerator()){$files[$directory+'/'+$entry.Key]=$entry.Value}}
    }
    Write-Json "$output/producer.json" @{schema='runeclr.android.session-policy.payloads.v1';apkSha256=$state.apkSha256;installedUtc=$state.installedUtc;productionStartedUtc=$started.ToString('o');completedUtc=[DateTime]::UtcNow.ToString('o');operatorDotnet=$operator;operatorSdk=(& $operator --version);fixtureGeneratorSha256=(Sha $FixtureGenerator);frameworkReferenceHashes=(File-Identity $FrameworkReferences);approvedContractSha256=(Sha "$evidence/app/RuneCLR.Abstractions.dll");lateSourceHashes=(File-Identity $lateProject);files=$files;appRerun=$false;scope='Operator-produced late IL and controlled package fixtures after installation; unchanged current host'}
    Write-Host ('Post-install fixtures prepared: '+$output);return
}
function Check-ManagedIL([string]$Path) {
    $bytes=[IO.File]::ReadAllBytes($Path)
    Require ($bytes.Length -ge 256 -and $bytes[0] -eq 77 -and $bytes[1] -eq 90) ('Not PE managed IL '+$Path)
    $pe=[BitConverter]::ToInt32($bytes,60);Require ($pe -gt 0 -and $pe+256 -lt $bytes.Length) 'Invalid PE offset'
    $sections=[BitConverter]::ToUInt16($bytes,$pe+6);$optionalSize=[BitConverter]::ToUInt16($bytes,$pe+20);$optional=$pe+24
    $magic=[BitConverter]::ToUInt16($bytes,$optional);Require ($magic -in 267,523) 'Unknown PE optional header'
    $directory=$optional+$(if($magic -eq 523){112}else{96})
    $clrRva=[BitConverter]::ToUInt32($bytes,$directory+112);Require ($clrRva -gt 0) 'Missing CLR header'
    $offset=-1
    for($index=0;$index -lt $sections;$index++) {
        $section=$optional+$optionalSize+40*$index;$rva=[BitConverter]::ToUInt32($bytes,$section+12);$size=[BitConverter]::ToUInt32($bytes,$section+16);$raw=[BitConverter]::ToUInt32($bytes,$section+20)
        if($clrRva -ge $rva -and $clrRva -lt $rva+$size){$offset=[int]($raw+$clrRva-$rva);break}
    }
    Require ($offset -ge 0 -and $offset+72 -le $bytes.Length) 'Invalid CLR mapping'
    Require (([BitConverter]::ToUInt32($bytes,$offset+16) -band 1) -eq 1 -and [BitConverter]::ToUInt32($bytes,$offset+64) -eq 0 -and [BitConverter]::ToUInt32($bytes,$offset+68) -eq 0) ('Author fixture is not pure IL: '+$Path)
}
if($Phase -eq 'Transfer') {
    Check-Device;Require ($DeviceSerial -eq $state.deviceSerial -and [bool]$state.installedUtc) 'Wrong installed owned device'
    Require ([bool]$PayloadDirectory) 'Supply -PayloadDirectory from post-install Produce phase'
    $producer=Read-Json "$PayloadDirectory/producer.json"
    Require ($producer.schema -eq 'runeclr.android.session-policy.payloads.v1' -and $producer.apkSha256 -eq $state.apkSha256 -and [DateTime]::Parse($producer.productionStartedUtc) -gt [DateTime]::Parse($state.installedUtc)) 'Producer does not bind post-install APK'
    Require (!$state.payloadReceiptSha256) 'Payloads already frozen; use new APK/evidence for a different fixture identity'
    $payloadHashes=[ordered]@{}
    foreach($property in $producer.files.psobject.Properties) {
        Require ($property.Name -match '^(fixtures|dependency-a|dependency-b|maps|plugin|controlled|late)/') 'Payload may not replace trusted APK files'
        $source=Inside $PayloadDirectory $property.Name;Require ((Sha $source) -eq $property.Value) ('Operator payload changed '+$property.Name)
        if($source -like '*.dll'){Check-ManagedIL $source}
        Push-Owned $source $property.Name "$evidence/transfer-hash-reads.log";$payloadHashes[$property.Name]=$property.Value
    }
    Require ($payloadHashes.Contains('late/RuneCLR.LateMap.dll') -and $payloadHashes.Contains('controlled/source/package.json')) 'Late IL / current controlled packages missing'
    Copy-Item -LiteralPath "$PayloadDirectory/producer.json" -Destination "$evidence/payload-producer.json"
    $state.payloadHashes=[pscustomobject]$payloadHashes
    $state|Add-Member -NotePropertyName payloadReceiptSha256 -NotePropertyValue (Sha "$evidence/payload-producer.json")
    $managedIdentity=[ordered]@{};foreach($property in $state.currentHostHashes.psobject.Properties){$managedIdentity[$property.Name]=$property.Value};foreach($entry in $payloadHashes.GetEnumerator()){$managedIdentity[$entry.Key]=$entry.Value}
    Write-Json "$evidence/managed-identity.json" @{schema='runeclr.android.session-policy.managed.v1';files=$managedIdentity;hostReceiptSha256=$state.hostReceiptSha256;producerReceiptSha256=$state.payloadReceiptSha256;scope='Actual device sha256sum checked against frozen producer files'}
    $state|Add-Member -NotePropertyName managedIdentitySha256 -NotePropertyValue (Sha "$evidence/managed-identity.json")
    Write-Json $statePath $state;Write-Host 'Transferred and froze author IL; trusted APK unchanged.';return
}
if($Phase -eq 'Run') {
    Check-Device;Require ($DeviceSerial -eq $state.deviceSerial -and [bool]$state.payloadReceiptSha256) 'Installed owned app and frozen transferred payloads required'
    Require ((Sha "$evidence/payload-producer.json") -eq $state.payloadReceiptSha256 -and (Sha "$evidence/managed-identity.json") -eq $state.managedIdentitySha256) 'Fixture receipts changed'
    if($Lane -notin 'all','sample','packages','lifecycle') {Require ([bool]$state.currentHostHashes.'SelectionProbe.Host.dll' -and [bool]$state.payloadHashes.'plugin/SelectionProbe.Payload.dll') 'Selection fixture absent from this frozen APK/payload'}
    if($Lane.EndsWith('inline')) {Require ([bool]$state.payloadHashes.'plugin/Inline/SelectionProbe.Inline.dll') 'Inline fixture was not produced/bound; old iOS selection ZIP is insufficient'}
    $runId=[Guid]::NewGuid().ToString('N');$run="$evidence/run-$Lane-$runId";New-Item -ItemType Directory -Path $run|Out-Null
    $mode=if($Lane -eq 'unmarked-fallback'){'1'}else{'0'};$tiered=if($Lane.EndsWith('inline')){'0'}else{'1'}
    $jitPath='/data/user/0/'+$state.package+'/files/session-'+$runId+'.jit.log'
    $settings=[ordered]@{interpMode=$mode;diagnostic='0';readyToRun='1';tiered=$tiered;jitStdOutFile=$jitPath;jitDisasmSummary='1';interpList='1';interpDump='*:*';DOTNET_JitNoInline='0'}
    if($Lane -in 'required-refusal','unmarked-fallback'){$settings.refuseMethods='SelectionUGC.Refusal.Entry:Reject'}
    if($Lane.EndsWith('inline')){$settings.DOTNET_JitDump='TrustedInlineCaller:NativeInlineCall';$settings.DOTNET_JitPrintInlinedMethods='TrustedInlineCaller:NativeInlineCall'}
    $arguments=@('-s',$DeviceSerial,'shell','am','instrument','-w','-e','env:RUNECLR_SESSION_RUN_ID',$runId,'-e','env:RUNECLR_SESSION_LANE',$Lane,'-e','env:RUNECLR_SESSION_MODE',$mode,($state.package+'/net.dot.MonoRunner'))
    $request=[ordered]@{platform='android';abi='x86_64';lane=$Lane;probeLane=$Lane;package=$state.package;deviceSerial=$DeviceSerial;runId=$runId;settings=$settings;candidateCommit=$candidate;productManifestSha256=$state.productManifestSha256;managedIdentitySha256=$state.managedIdentitySha256;currentHostHashes=$state.currentHostHashes;apkSha256=$state.apkSha256;startedUtc=[DateTime]::UtcNow.ToString('o');command=@($adb)+$arguments;pidQueryCommand='android.os.Process.myPid() in MonoRunner.initializeRuntime before CoreCLR initialization';logFraming=@{native='plain';jit='plain';managed='plain'};appRerun=$false}
    Write-Json "$run/request.json" $request
    $result=[ordered]@{platform='android';abi='x86_64';lane=$Lane;runId=$runId;candidateCommit=$candidate;productManifestSha256=$state.productManifestSha256;managedIdentitySha256=$state.managedIdentitySha256;currentHostHashes=$state.currentHostHashes;functionalPassed=$false;executionEvidencePassed=$false;platformAccepted=$false;nativeManagedExitZero=$false;bundleUnchanged=$false;payloadUnchanged=$false;stdoutTruncated=$false;logsTruncated=$false;rawHashes=@{};appRerun=$false}
    try {
        $null=Check-Installed "$run/hash-reads-before.log"
        $null=Adb @('shell','am','force-stop',$state.package)
        & $adb @arguments *> "$run/instrumentation.log";$instrumentExit=$LASTEXITCODE
        [IO.File]::WriteAllText("$run/instrumentation.log.exit",[string]$instrumentExit,$utf8)
        $result.normalExitCode=$instrumentExit
        foreach($pair in @(@('native.log','native.log'),@('jit.log','jit.log'),@('managed.log','managed.log'),@('managed-result.json','managed-result.json'),@('pid-query.txt','pid-query.txt'),@('maps.log','maps.log'))) {Pull-Owned ('files/session-'+$runId+'.'+$pair[0]) ("$run/"+$pair[1])}
        $native=Get-Content -LiteralPath "$run/native.log" -Raw;$managed=Read-Json "$run/managed-result.json";$managedText=Get-Content -LiteralPath "$run/managed.log" -Raw;$jit=Get-Content -LiteralPath "$run/jit.log" -Raw
        $header=[regex]::Matches($native,'(?m)^ANDROID_SESSION_NATIVE pid=([0-9]+) runId=([0-9a-f]+) InterpMode=([01]) RuneCLRInterpretCollectible=0\r?$')
        Require ($header.Count -eq 1) 'Unique native pre-initialization config header required'
        $ownedPid=[int]$header[0].Groups[1].Value;$result.appPid=$ownedPid
        Require ($header[0].Groups[2].Value -eq $runId -and $header[0].Groups[3].Value -eq $mode -and $managed.appPid -eq $ownedPid -and $managed.runId -eq $runId -and $managed.lane -eq $Lane) 'Actual native/managed ownership mismatch'
        $pidQuery=[regex]::Match((Get-Content -LiteralPath "$run/pid-query.txt" -Raw),'^android.os.Process.myPid=([0-9]+)\r?\n?$')
        Require ($pidQuery.Success -and [int]$pidQuery.Groups[1].Value -eq $ownedPid) 'Independent Java owned PID query mismatch'
        $result.pidQueryObservedPid=[int]$pidQuery.Groups[1].Value;$result.pidQueryCommand=$request.pidQueryCommand
        Require ($instrumentExit -eq 0 -and (Get-Content -LiteralPath "$run/instrumentation.log" -Raw) -match 'return-code=0' -and $native -match '(?m)^CORECLR_INITIALIZE_HRESULT=0x0\r?$' -and $native -match '(?m)^CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0\r?$' -and $managed.exitCode -eq 0) 'Instrumentation/native/managed completion failed'
        $result.nativeManagedExitZero=$true
        $observed=Check-Installed "$run/hash-reads.log"
        $product=Read-Json "$evidence/product-manifest.json";$runtimeHashes=[ordered]@{}
        $maps=Get-Content -LiteralPath "$run/maps.log" -Raw
        $coreclrPath=[regex]::Match($maps,'(?m)(/[^\s]+/libcoreclr\.so)\r?$');Require $coreclrPath.Success 'Actual mapped target CoreCLR library absent'
        $nativeDir=($coreclrPath.Groups[1].Value -replace '/libcoreclr\.so$','')
        foreach($property in $product.artifactHashes.psobject.Properties) {
            $devicePath=if($property.Name -eq 'System.Private.CoreLib.dll'){'files/'+$property.Name}else{$nativeDir+'/'+$property.Name}
            $line=Adb @('shell','run-as',$state.package,'sha256sum',$devicePath)
            Require ($line.StartsWith($property.Value,[StringComparison]::OrdinalIgnoreCase)) ('Actual installed runtime hash differs: '+$property.Name)
            Add-Content -LiteralPath "$run/hash-reads.log" -Value $line;$runtimeHashes[$property.Name]=$property.Value
        }
        if($Lane -notin 'ordinary','ordinary-inline','unmarked-fallback'){Require ($maps -match '/libclrinterpreter\.so(?:\r?\n|$)') 'Required execution did not map dynamic interpreter library'}
        $result.installedRuntimeHashes=$runtimeHashes
        $identity=Read-Json "$evidence/managed-identity.json";$managedHashes=[ordered]@{}
        foreach($property in $identity.files.psobject.Properties) {Require ($observed[$property.Name] -eq $property.Value) ('Installed fixture binding absent '+$property.Name);$managedHashes[$property.Name]=$observed[$property.Name]}
        $result.installedManagedHashes=$managedHashes;$result.bundleUnchanged=$true;$result.payloadUnchanged=$true
        # Copy actual managed probe evidence without substituting inventories for execution counts.
        if($Lane -notin 'all','sample','packages','lifecycle') {
            New-Item -ItemType Directory -Path "$run/probe-evidence"|Out-Null
            $listing=Adb @('shell','run-as',$state.package,'find',('files/probe-evidence-'+$runId),'-type','f')
            foreach($path in $listing.Split([char]10) |Where-Object {$_}) { $relative=$path.Trim();Require ($relative -match ('^files/probe-evidence-'+$runId+'/[A-Za-z0-9_./-]+$')) 'Unexpected probe evidence path';$target=Inside "$run/probe-evidence" ($relative -replace ('^files/probe-evidence-'+$runId+'/'),'');New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null;Pull-Owned $relative $target }
            Require ([bool]$ProbeAssessorPath) 'Selection lanes require explicit Checked-bytecode/JIT assessor; transport success alone is insufficient'
        } else {
            Test-Functional $Lane $managedText $managed
            $result.functionalPassed=$true
            Require ($jit -match 'JIT compiled\s+RuneCLR\.Runtime\.MapRunner:' -and $native -match '(?m)^Compiled method: [^\r\n]*(RuneCLR\.TestMaps|GameScript|Maps\.Hello|Maps\.Arena)[^\r\n]*\r?\nLocals size [0-9]+\r?\n[0-9a-fA-F]+: IR_[0-9a-fA-F]+:') 'Trusted native caller plus same-method actual author bytecode-body evidence missing'
            Require ($jit -notmatch 'JIT compiled\s+\.?(RuneCLR\.TestMaps\.|GameScript:|Maps\.Hello\.|Maps\.Arena\.)') 'Required author definition compiled natively'
            $result.executionEvidencePassed=$true
            $result.scope='Current production functional counts and native host / author bytecode evidence; complete selection/refusal/inline matrix is a separate gate'
        }
        $result.completedUtc=[DateTime]::UtcNow.ToString('o')
        $result.rawHashes=File-Identity $run;Write-Json "$run/results.json" $result
        if($Lane -notin 'all','sample','packages','lifecycle') {
            [string[]]$pythonArgs=@()
            if([IO.Path]::GetFileNameWithoutExtension($PythonExecutable) -eq 'py'){$pythonArgs=@('-3')}
            Invoke-Logged $PythonExecutable ($pythonArgs+@($ProbeAssessorPath,'assess','--lane',$Lane,'--run',$run,'--product',"$evidence/product-manifest.json",'--managed-identity',"$evidence/managed-identity.json",'--output',"$run/method-assessment.json")) "$run/assessment.log"
            $assessment=Read-Json "$run/method-assessment.json";Require ($assessment.passed -eq $true) 'Method assessment did not pass'
            $result.functionalPassed=$true;$result.executionEvidencePassed=$true;$result.methodAssessmentSha256=Sha "$run/method-assessment.json";$result.scope=$assessment.scope
            # Keep the transport receipt immutable: assessment references its original hash.
            Write-Json "$run/final-assessment.json" @{functionalPassed=$true;executionEvidencePassed=$true;platformAccepted=$false;transportResultsSha256=(Sha "$run/results.json");methodAssessmentSha256=$result.methodAssessmentSha256;reason='Complete Android matrix / fresh Release native entry / physical ARM64 device remain separate milestones';appRerun=$false}
        }
        Write-Host ('Completed owned Android lane: '+$run+'; platform matrix acceptance remains separate.')
    } catch {
        $result.error=$_.Exception.ToString();$result.completedUtc=[DateTime]::UtcNow.ToString('o');$result.rawHashes=File-Identity $run
        if(!(Test-Path -LiteralPath "$run/results.json")){Write-Json "$run/results.json" $result}else{Write-Json "$run/failure-assessment.json" $result}
        throw
    }
    return
}
if($Phase -eq 'Archive') {
    $archive=$evidence.TrimEnd('/','\')+'-'+[Guid]::NewGuid().ToString('N')+'.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($evidence,$archive,[IO.Compression.CompressionLevel]::Optimal,$false)
    Write-Json ($archive+'.sha256.json') @{path=$archive;sha256=(Sha $archive);bytes=(Get-Item -LiteralPath $archive).Length;executionVerified=$false;scope='Archive of actual prepared/build/run records; acceptance is determined by contained receipts'}
    Write-Host $archive;Write-Host (Sha $archive);return
}
throw ('Unhandled phase '+$Phase)
