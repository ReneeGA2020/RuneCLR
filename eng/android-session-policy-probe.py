#!/usr/bin/env python3
"""Prepare Android probe lanes or assess owned raw logs without executing an app.

Android acceptance requires the independent APK/build/ownership receipts.
Parser compatibility with Windows archives is explicitly not Android evidence.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
LANES = ('required', 'ordinary', 'required-refusal', 'unmarked-fallback',
         'required-boxed', 'required-inline', 'ordinary-inline')
VALUES = dict(zip(('PayloadStatic', 'PayloadConstructor', 'Property', 'Inlined', 'GenericStatic',
                  'GenericMethod', 'Delegate', 'Virtual', 'DefaultInterface', 'Filter',
                  'PrivateStatic', 'PrivateConstructor', 'PrivateProperty', 'PrivateInline',
                  'PrivateGenericStatic', 'PrivateGenericMethod', 'PrivateDelegate'),
                 (1, 1, 7, 12, 1, 19, 11, 13, 17, 1, 1, 1, 30, 38, 1, 41, 42)))
REFUSE = 'SelectionUGC.Refusal.Entry:Reject'
SKIPPED = 'RuneCLRInterpreterRefusal: ' + REFUSE + ' CORJIT_SKIPPED'


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return Path(path).read_text(encoding='utf-8-sig')


def document(path):
    return json.loads(read(path))


def lane_plan(lane, payload, evidence, jit):
    check(lane in LANES, 'Unknown semantic probe lane')
    settings = {'DOTNET_InterpMode': '1' if lane == 'unmarked-fallback' else '0',
                'DOTNET_RuneCLRInterpretCollectible': '0', 'DOTNET_ReadyToRun': '1',
                'DOTNET_TieredCompilation': '0' if lane.endswith('inline') else '1',
                'DOTNET_JitNoInline': '0', 'DOTNET_InterpList': '1', 'DOTNET_InterpDump': '*:*',
                'DOTNET_JitDisasmSummary': '1', 'DOTNET_JitStdOutFile': jit,
                'RUNECLR_PROBE_FACTORY': 'ordinary' if lane in ('ordinary', 'ordinary-inline', 'unmarked-fallback') else 'required'}
    arguments = [payload, evidence]
    if lane in ('required-refusal', 'unmarked-fallback'):
        settings['DOTNET_RuneCLRInterpreterRefuseMethods'] = REFUSE
        arguments += ['--refusal-required' if lane == 'required-refusal' else '--refusal-fallback', str(PurePosixPath(payload) / 'Refusal')]
    if lane == 'required-boxed':
        arguments += ['--bridges', str(PurePosixPath(payload) / 'Boxed')]
    if lane.endswith('inline'):
        arguments += ['--inline', str(PurePosixPath(payload) / 'Inline')]
        settings.update(DOTNET_JitDump='TrustedInlineCaller:NativeInlineCall',
                        DOTNET_JitPrintInlinedMethods='TrustedInlineCaller:NativeInlineCall')
    return {'probeLane': lane, 'managedEntry': 'SelectionProbe.Host', 'arguments': arguments,
            'settings': settings, 'runRequired': True, 'platformAcceptance': 'not performed',
            'nativeLogRequirement': 'Owned PID/runId; untruncated stdout/stderr before coreclr_initialize',
            'managedWriterRequirement': 'SetOut and SetError to the same owned writer; Host selects Console.Error'}


def decode_log(text, pid, framing='plain'):
    """Strip framing, preserving raw bytecode/JIT lines and ignoring foreign PIDs."""
    if framing == 'plain':
        return text
    records = []
    if framing == 'jsonl':
        for line in text.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            check(isinstance(event.get('pid'), int) and isinstance(event.get('message'), str), 'Malformed JSON log ownership framing')
            if event['pid'] == pid:
                records.append(event['message'])
    elif framing == 'logcat-threadtime':
        for line in text.splitlines():
            if not line or line.startswith('--------- beginning of '):
                continue
            match = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(\d+)\s+\d+\s+[VDIWEF]\s+[^:]+:\s?(.*)$', line)
            check(match is not None, 'Unrecognized logcat framing; raw source must be retained')
            if int(match[1]) == pid:
                records.append(match[2])
    else:
        raise ValueError('Unknown framing')
    return '\n'.join(records) + '\n'


def installed_identity(hash_text, maps_text, runtime_hashes, managed_hashes, apk_hash):
    """Compare independent original device reads, not only transport summary maps."""
    records = {}
    for line in hash_text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+[* ]?(.+)', line)
        check(match is not None, 'Malformed original device sha256sum line')
        digest, path = match[1].lower(), match[2]
        check(path not in records or records[path] == digest, 'Conflicting original device hash reads')
        records[path] = digest
    coreclr = set(re.findall(r'(/[^\s]+/libcoreclr\.so)\r?$', maps_text, re.M))
    check(len(coreclr) == 1, 'One actual mapped CoreCLR file required')
    native_dir = str(PurePosixPath(next(iter(coreclr))).parent)
    for name, expected in runtime_hashes.items():
        check(PurePosixPath(name).name == name, 'Runtime manifest expects native basenames')
        path = 'files/' + name if name == 'System.Private.CoreLib.dll' else native_dir + '/' + name
        check(records.get(path) == expected.lower(), 'Original installed runtime hash differs: ' + name)
    for relative, expected in managed_hashes.items():
        check(not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts,
              'Managed producer relative path escapes app files')
        check(records.get('files/' + relative) == expected.lower(), 'Original installed managed hash differs: ' + relative)
    check(isinstance(apk_hash, str) and re.fullmatch(r'[0-9a-f]{64}', apk_hash), 'Frozen APK identity missing')
    apks = {path: digest for path, digest in records.items() if path.startswith('/data/app/') and path.endswith('.apk')}
    check(len(apks) == 1 and set(apks.values()) == {apk_hash}, 'Original installed APK hash differs')
    return {'nativeDirectory': native_dir, 'deviceHashReadCount': len(records), 'apkSha256': apk_hash}


def observations(lane, native, jit, managed):
    """Execution assertions only; caller must establish platform/artifact/PID provenance."""
    required = lane not in ('ordinary', 'ordinary-inline', 'unmarked-fallback')
    inline = lane.endswith('inline')
    boxed = lane == 'required-boxed'
    expected_policy = 1 if required else 0
    api = 'POLICY API version=1 factory=' + ('required' if required else 'ordinary') + ' default=0 immutable-api=true'
    check(api in managed.splitlines(), 'Actual native policy/API acknowledgement missing')
    query = re.findall(r'^POLICY context=.* phase=(\S+) value=([01]) collectible=true$', managed, re.M)
    check(all(int(value) == expected_policy for phase, value in query), 'Observed context policy changed')
    phases = Counter(phase for phase, value in query)
    retired = len(re.findall(r'^RETIRED query=System.InvalidOperationException protected=true$', managed, re.M))
    expected_retired = 0 if lane == 'unmarked-fallback' else 21 if lane == 'required-refusal' else 20
    check(retired == expected_retired, 'Post-Unload native query guard count mismatch')
    owner_jit = re.findall(r'JIT compiled\s+\.?SelectionUGC\.[^\r\n]*', jit)
    # A trusted generic definition may name collectible T in its signature;
    # classify the owner immediately following "JIT compiled", not any UGC text.
    if required:
        check(not owner_jit, 'Required author definition compiled natively')
    groups = Counter(line for line in native.splitlines() if line.startswith('Compiled method: ') and 'SelectionUGC.' in line)
    bodies = re.findall(r'^(Compiled method: [^\r\n]*SelectionUGC\.[^\r\n]*)\r?\nLocals size \d+\r?\n[0-9a-fA-F]+: IR_[0-9a-fA-F]+:', native, re.M)
    check(Counter(bodies) == groups, 'Successful author compilation must retain actual bytecode body dump')
    skips = native.count(SKIPPED)
    sessions = 0
    if lane == 'unmarked-fallback':
        check(skips == 1 and re.search(r'^PASS unmarked-refusal value=73 module=.* token=0x06000001$', managed, re.M), 'Actual unmarked SKIPPED/value73 missing')
        check(any('SelectionUGC.Refusal.Entry:Reject' in line for line in owner_jit), 'Unmarked native fallback body not observed')
        check(not groups, 'Skipped unmarked body unexpectedly produced UGC bytecode')
    elif inline:
        passes = re.findall(r'^PASS inline-session=(\d+) first=53 warm=38 trusted-definition=true collectible-argument=true collected=true$', managed, re.M)
        check([int(value) for value in passes] == list(range(1, 21)), 'Concrete generic values/collection incomplete')
        check('20/20 native generic caller sessions passed; 20/20 contexts collected' in managed.splitlines(), 'Native generic aggregate missing')
        callers = re.findall(r'JIT compiled\s+TrustedInlineCaller:NativeInlineCall\[SelectionUGC.Inline.Entry\]', jit)
        check(len(callers) == 20, 'Trusted generic definition native positive count mismatch')
        successful_inline = re.findall(r"^.*INLINER:.*result 'success'.*for 'TrustedInlineCaller:NativeInlineCall.*calling 'SelectionUGC.Inline.Entry:ReadInline.*$", jit, re.M | re.I)
        rejected_inline = re.findall(r"^.*INLINER:.*result 'failed this callee' reason 'noinline per IL/cached result'.*for 'TrustedInlineCaller:NativeInlineCall.*calling 'SelectionUGC.Inline.Entry:ReadInline.*$", jit, re.M)
        check(len(successful_inline) == (0 if required else 20), 'Actual inline positive/negative decision count mismatch')
        if required:
            check(len(rejected_inline) == 20, 'Required concrete inlinee actual rejection count mismatch')
        sessions = 20
    elif boxed:
        passes = re.findall(r'^PASS bridge-session=(\d+) interface=17 warm-interface=17 closed-delegate=17 starts=1 instances=1 collected=true$', managed, re.M)
        check([int(value) for value in passes] == list(range(1, 21)), 'Boxed interface/delegate values/collection incomplete')
        check('20/20 boxed bridge sessions passed; 20/20 contexts collected' in managed.splitlines(), 'Boxed aggregate missing')
        check(re.search(r'JIT compiled\s+Program:[^\r\n]*BoxedFrame', jit), 'Trusted boxed frame native positive missing')
        sessions = 20
    else:
        passes = re.findall(r'^PASS session=(\d+) values=(\{[^\r\n]*\}) collected=true$', managed, re.M)
        check([int(number) for number, value in passes] == list(range(1, 21)), '20 independent sessions/collection markers missing')
        check(all(json.loads(value) == VALUES for number, value in passes), 'Business values/static resets differ from expected actual fixture result')
        check('20/20 execution-selection sessions passed; 20/20 contexts collected' in managed.splitlines(), 'Independent session aggregate missing')
        check(len(re.findall(r'^LATE private=absent policy=' + str(expected_policy) + '$', managed, re.M)) == 20, 'Late dependency pre-boundary incomplete')
        check(len(re.findall(r'^LATE private=loaded policy=' + str(expected_policy) + '$', managed, re.M)) == 20, 'Late dependency inherited policy incomplete')
        check(len(re.findall(r'^DEPENDENCY resolved-private=SelectionProbe.Private owning-context=true$', managed, re.M)) == 20, 'Private dependency escaped session owner')
        if required:
            check(re.search(r'JIT compiled\s+Program:[^\r\n]*RunFrame', jit), 'Trusted frame native JIT positive missing')
        else:
            check(any('SelectionUGC.Payload.Entry:Run' in line for line in owner_jit), 'Ordinary same-IL UGC native JIT positive missing')
        if lane == 'required-refusal':
            check(skips == 1 and 'PASS required-refusal exception=System.NotSupportedException collected=true' in managed.splitlines(), 'Real interpreter decline/refused-context retirement missing')
        sessions = 20
    if lane != 'unmarked-fallback':
        explicit = 20 if inline or boxed else 40
        extra = int(lane == 'required-refusal')
        expected_phases = {'before-load': 20 + extra, 'before-explicit-load': explicit + extra,
                           'after-explicit-load': explicit + extra, 'before-unload': 20 + extra}
        if not inline and not boxed:
            expected_phases.update({'before-run': 20, 'resolver-after-private': 20, 'after-run': 20})
        check(all(phases[name] == count for name, count in expected_phases.items()), 'Immutable native policy load/run/retirement phase counts differ')
        check(phases['resolver-before'] >= 20, 'Owning resolver native-query acknowledgement missing')
    if required:
        expected_groups = 1 if inline else 5 if boxed else 26
        check(len(groups) == expected_groups and set(groups.values()) == {20}, 'Actual bytecode preparation groups differ from required 20-context matrix')
    else:
        check(not groups, 'Ordinary mode0 control unexpectedly interpreted author bodies')
    check(not re.search(r'^(FAIL |Unhandled exception)', managed, re.M), 'Managed fixture failure retained')
    check(not any(marker in native + jit + managed for marker in ('Assert failure', 'Assertion failed', 'Got a SIGSEGV')), 'Native assertion/crash retained')
    result = {'probeLane': lane, 'functionalSessions': sessions, 'contextsCollected': sessions,
              'policyVersion': 1, 'policy': expected_policy, 'nativeQueryCount': len(query), 'policyPhaseCounts': dict(phases),
              'retiredQueryGuards': retired, 'bytecodeGroups': len(groups), 'bytecodeDumps': sum(groups.values()),
              'ugcOwnerNativeJitCount': len(owner_jit), 'actualSkippedCount': skips,
              'methodNativeEntryProof': 'not collected; bytecode preparation plus values and native-JIT diagnostics'}
    if inline:
        result.update(actualInlineSuccesses=len(successful_inline), actualInlineRejections=len(rejected_inline), trustedNativeCallerCount=len(callers))
    return result


def assess(args):
    directory = args.run.resolve()
    request = document(directory / 'request.json')
    transport = document(directory / 'results.json')
    lane = args.lane
    check(request.get('platform') == 'android' and request.get('abi') == 'x86_64', 'Actual Android x64 platform/ABI request required')
    check(request.get('probeLane') == lane, 'Semantic probe lane receipt mismatch')
    check(transport.get('platform') == 'android' and transport.get('abi') == request['abi'], 'Transport platform provenance mismatch')
    pid, run_id = transport.get('appPid'), request.get('runId')
    check(isinstance(pid, int) and pid > 0 and isinstance(run_id, str) and len(run_id) >= 16, 'Actual owned PID/nonempty run nonce required')
    check(transport.get('runId') == run_id, 'Native/managed run ownership mismatch')
    check(transport.get('lane') == lane and request.get('lane') == lane, 'Transport semantic lane mismatch')
    check(request.get('appRerun') is False and transport.get('appRerun') is False, 'Original single application run required')
    check(transport.get('pidQueryObservedPid') == pid and transport.get('pidQueryCommand'), 'Independent owned-process query receipt missing')
    raw_hashes = transport.get('rawHashes', {})
    for name in ('native.log', 'jit.log', 'managed.log', 'managed-result.json', 'instrumentation.log', 'hash-reads.log', 'pid-query.txt', 'maps.log'):
        check(name in raw_hashes and sha(directory / name).lower() == raw_hashes[name].lower(), 'Original raw file missing/changed: ' + name)
    check(transport.get('normalExitCode') == 0 and transport.get('nativeManagedExitZero') is True, 'Actual instrumentation/native/managed exit not zero')
    check(re.search(r'\breturn-code=0\b', read(directory / 'instrumentation.log')), 'Original instrumentation completion marker missing')
    check(transport.get('bundleUnchanged') is True and transport.get('payloadUnchanged') is True, 'APK/trusted/payload bytes changed')
    check(not transport.get('stdoutTruncated') and not transport.get('logsTruncated'), 'Raw output truncation cannot pass')
    product = document(args.product)
    check(product.get('platform') == 'android' and product.get('abi') == 'x86_64' and product.get('configuration') == 'Checked', 'Matching private Checked Android product required')
    check(product.get('base') == BASE and product.get('featureInterpreter') is True and product.get('featureDynamicCodeCompiled') is True, 'Pinned source and actual native feature receipts required')
    check(product.get('sourceTrackedClean') is True and product.get('commit') == transport.get('candidateCommit'), 'Source/product commit ownership mismatch')
    check(request.get('candidateCommit') == product['commit'], 'Requested candidate differs from actual product')
    check(sha(args.product) == transport.get('productManifestSha256'), 'Immutable matching product manifest changed')
    check(request.get('productManifestSha256') == transport['productManifestSha256'], 'Request/product manifest binding differs')
    check(product.get('artifactHashes') == transport.get('installedRuntimeHashes') and product.get('artifactHashes'), 'Installed matching CoreCLR/interpreter/JIT/CoreLib identities differ')
    managed_identity = document(args.managed_identity)
    check(sha(args.managed_identity) == transport.get('managedIdentitySha256'), 'Managed fixture producer identity changed')
    check(request.get('managedIdentitySha256') == transport['managedIdentitySha256'], 'Request/producer manifest binding differs')
    check(managed_identity.get('files') == transport.get('installedManagedHashes') and managed_identity.get('files'), 'Installed host/payload hashes differ from producer')
    query = re.fullmatch(r'android\.os\.Process\.myPid=(\d+)\s*', read(directory / 'pid-query.txt'))
    check(query is not None and int(query[1]) == pid, 'Original pre-initialization Java PID query differs')
    installed = installed_identity(read(directory / 'hash-reads.log'), read(directory / 'maps.log'),
                                   product['artifactHashes'], managed_identity['files'], request.get('apkSha256'))
    check({'libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so', 'System.Private.CoreLib.dll'} <= set(product['artifactHashes']),
          'Matching native/runtime manifest omits mandatory artifacts')
    if lane not in ('ordinary', 'ordinary-inline', 'unmarked-fallback'):
        check(re.search(r'/libclrinterpreter\.so\r?$', read(directory / 'maps.log'), re.M), 'Actual required interpreter module mapping missing')
    logs = {}
    for name in ('native', 'jit', 'managed'):
        logs[name] = decode_log(read(directory / (name + '.log')), pid, request.get('logFraming', {}).get(name, 'plain'))
    headers = re.findall(r'^ANDROID_SESSION_NATIVE pid=(\d+) runId=(\S+) InterpMode=([0-9]+) RuneCLRInterpretCollectible=([0-9]+)\s*$', logs['native'], re.M)
    expected_mode = '1' if lane == 'unmarked-fallback' else '0'
    check(headers == [(str(pid), run_id, expected_mode, '0')], 'Native pre-initialization PID/runId/mode0/diagnostic0 marker mismatch')
    managed_headers = re.findall(r'^ANDROID_SESSION_MANAGED pid=(\d+) runId=(\S+) lane=(\S+) framework=[^\r\n]+ arch=(\S+)\s*$', logs['managed'], re.M)
    check(managed_headers == [(str(pid), run_id, lane, 'X64')], 'Original managed PID/runId/lane/architecture ownership marker mismatch')
    original_settings = request.get('settings', {})
    settings = dict(original_settings)
    for short, exact in {'interpMode': 'DOTNET_InterpMode', 'diagnostic': 'DOTNET_RuneCLRInterpretCollectible',
                         'readyToRun': 'DOTNET_ReadyToRun', 'tiered': 'DOTNET_TieredCompilation',
                         'jitStdOutFile': 'DOTNET_JitStdOutFile',
                         'refuseMethods': 'DOTNET_RuneCLRInterpreterRefuseMethods',
                         'jitDisasmSummary': 'DOTNET_JitDisasmSummary', 'interpList': 'DOTNET_InterpList',
                         'interpDump': 'DOTNET_InterpDump'}.items():
        if short in original_settings:
            value = str(original_settings[short])
            check(exact not in settings or str(settings[exact]) == value, 'Contradictory abbreviated/native config settings')
            settings[exact] = value
    check(settings.get('DOTNET_InterpMode') == expected_mode and settings.get('DOTNET_RuneCLRInterpretCollectible') == '0', 'Requested global diagnostic/mode differs from actual lane')
    check(settings.get('DOTNET_ReadyToRun') == '1' and settings.get('DOTNET_TieredCompilation') == ('0' if lane.endswith('inline') else '1'), 'Required R2R/tiering main-lane settings differ')
    check(settings.get('DOTNET_JitStdOutFile'), 'Separate owned native-JIT raw file required')
    check(settings.get('DOTNET_JitDisasmSummary') == '1' and settings.get('DOTNET_InterpList') == '1'
          and settings.get('DOTNET_InterpDump') == '*:*', 'Full native-JIT/bytecode diagnostic coverage must be explicitly requested')
    check('CORECLR_INITIALIZE_HRESULT=0x0' in logs['native'] and 'CORECLR_EXECUTE_HRESULT=0x0' in logs['native'] and 'RUNECLR_EXIT=0' in logs['native'], 'Native runtime initialization/managed exit markers missing')
    if lane in ('required-refusal', 'unmarked-fallback'):
        check(settings.get('DOTNET_RuneCLRInterpreterRefuseMethods') == REFUSE, 'Exact real compiler-skip injection settings missing')
    observed = observations(lane, logs['native'], logs['jit'], logs['managed'])
    managed_result = document(directory / 'managed-result.json')
    check(managed_result.get('runId') == run_id and managed_result.get('exitCode') == 0
          and managed_result.get('appPid') == pid and managed_result.get('lane') == lane,
          'Managed wrapper run/PID/lane/exit result mismatch')
    check(managed_result.get('policyVersion') == 1 and managed_result.get('defaultPolicy') == 0
          and managed_result.get('ordinaryPolicy') == 0 and managed_result.get('requiredPolicy') == 1,
          'Wrapper fixed-factory native acknowledgement incomplete')
    result = {'passed': True, 'appRerun': False, 'platform': 'android', 'abi': 'x86_64', 'appPid': pid, 'runId': run_id,
              'candidateCommit': product['commit'], 'productManifestSha256': sha(args.product),
              'managedIdentitySha256': sha(args.managed_identity), 'rawHashes': raw_hashes, 'observations': observed,
              'installedIdentity': installed,
              'scope': 'Owned Checked Android raw logs; not per-method native-entry trace, mobile ARM64/device proof or security sandbox'}
    check(not args.output.exists(), 'Preserve previous assessment; choose a new output file')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


def matrix(args):
    assessments = [document(path) for path in args.assessment]
    by_lane = {item.get('observations', {}).get('probeLane'): item for item in assessments}
    expected = set(LANES) if args.include_inline else set(LANES[:5])
    check(len(by_lane) == len(assessments) and set(by_lane) == expected, 'Every matrix lane must have one independent assessment')
    check(all(item.get('passed') is True and item.get('platform') == 'android' and item.get('abi') == 'x86_64' and item.get('appRerun') is False for item in assessments), 'Non-Android/incomplete result cannot form an Android matrix')
    check(len({item['candidateCommit'] for item in assessments}) == 1 and len({item['productManifestSha256'] for item in assessments}) == 1, 'Matrix runtime inputs differ')
    check(len({item['managedIdentitySha256'] for item in assessments}) == 1, 'Same IL/host identity controls differ between lanes')
    check(len({(item['appPid'], item['runId']) for item in assessments}) == len(assessments), 'Separate process/run ownership records reused')
    check(not args.output.exists(), 'Preserve previous matrix assessment')
    result = {'passed': True, 'appRerun': False, 'platform': 'android', 'abi': 'x86_64',
              'candidateCommit': assessments[0]['candidateCommit'], 'sameRuntimeAndManagedInputs': True,
              'lanes': {lane: item['observations'] for lane, item in by_lane.items()},
              'assessmentHashes': {str(path): sha(path) for path in args.assessment},
              'scope': 'Checked bytecode/JIT/refusal controls; native method-entry and Release/device parity remain separate'}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


def windows_compatibility(args):
    """Inspect actual old Windows files; never emit an Android pass receipt."""
    directory = args.evidence
    check(document(directory / 'results.json').get('passed') is True, 'Existing Windows evidence did not pass')
    for lane in ('required', 'ordinary', 'required-refusal', 'unmarked-fallback', 'required-boxed'):
        result = observations(lane, read(directory / (lane + '.log.stdout')), read(directory / (lane + '.log.jit')), read(directory / (lane + '.log.stderr')))
        print('WINDOWS HISTORICAL PARSER COMPATIBILITY', lane, json.dumps(result))
    if args.inline_evidence:
        for lane, filename in [('ordinary-inline', 'ordinary'), ('required-inline', 'required')]:
            result = observations(lane, read(args.inline_evidence / (filename + '.log.stdout')), read(args.inline_evidence / (filename + '.log.jit')), read(args.inline_evidence / (filename + '.log.stderr')))
            print('WINDOWS HISTORICAL PARSER COMPATIBILITY', lane, json.dumps(result))
    print('No Android runtime or app executed; no Android pass receipt produced.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Emit APK integration lane settings/arguments; no execution')
    plan.add_argument('--lane', choices=LANES, required=True)
    for name in ('payload', 'evidence', 'jit'):
        plan.add_argument('--' + name, required=True)
    plan.set_defaults(action=lambda args: print(json.dumps(lane_plan(args.lane, args.payload, args.evidence, args.jit), indent=2)))
    audit = sub.add_parser('assess', help='Read actual owned Android raw artifacts; no app/assessor rerun')
    audit.add_argument('--lane', choices=LANES, required=True)
    for name in ('run', 'product', 'managed-identity', 'output'):
        audit.add_argument('--' + name, type=Path, required=True)
    audit.set_defaults(action=assess)
    combined = sub.add_parser('matrix', help='Compare actual assessed Android lanes with identical host/payload/runtime inputs')
    combined.add_argument('--assessment', type=Path, action='append', required=True)
    combined.add_argument('--include-inline', action='store_true')
    combined.add_argument('--output', type=Path, required=True)
    combined.set_defaults(action=matrix)
    compatibility = sub.add_parser('check-windows-parser', help='Actual historical Windows parser compatibility, explicitly not Android proof')
    compatibility.add_argument('--evidence', type=Path, required=True)
    compatibility.add_argument('--inline-evidence', type=Path)
    compatibility.set_defaults(action=windows_compatibility)
    args = parser.parse_args()
    args.action(args)


if __name__ == '__main__':
    main()
