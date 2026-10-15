#!/usr/bin/env python3
"""Independently audit retained Windows Release budget experiments, without reruns."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '099dacd07d8d890822f7422f895337733457ab3c'
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
EXPERIMENTS = {
    'terminal': 'windows-terminal-20261013-attempt2',
    'finalizer': 'windows-finalizer-20261013-attempt2',
    'host': 'windows-host-budget-20261013-attempt1',
}
SIGNALS = ('Enter Catch Post FilterEntered FilterReturned Finally Helper Delegate '
           'OuterFinally InnerFinally ThrowingFinally ConstructorBefore ConstructorAfter '
           'StaticBefore StaticAfter TrustedEntered TrustedCaught ReentryAttempt '
           'ReentrySucceeded Starts Good FilterCatch').split()


def require(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def match_hash(path, expected):
    require(digest(path) == expected.lower(), 'Byte identity differs: ' + str(path))


def exact_line(raw, line):
    require(raw.splitlines().count(line) == 1, 'Owned raw marker missing/duplicated: ' + line)


def ledger(value, limit, terminated=None):
    require(value is not None, 'Native ledger missing')
    require(value['Remaining'] >= 0 and value['Executed'] >= 0 and
            value['Remaining'] + value['Executed'] == limit, 'Execution arithmetic differs')
    require(value['CleanupRemaining'] >= 0 and value['CleanupExecuted'] >= 0 and
            value['CleanupRemaining'] + value['CleanupExecuted'] == 4096, 'Cleanup arithmetic differs')
    if terminated is not None:
        require(value['IsTerminated'] is terminated and value['Reason'] == int(terminated), 'Sticky latch differs')
        if terminated:
            require(value['Remaining'] == 0 and value['Executed'] == limit and value['Exhausted'], 'Exact exhaustion differs')
        else:
            require(value['Remaining'] > 0 and not value['Exhausted'] and value['Phase'] == 0 and
                    value['CleanupExecuted'] == 0, 'Active ledger used terminal reserve')


def metadata_method(metadata, assembly, mvid, token, owner, method):
    candidates = [item for item in metadata if item['assembly'] == assembly and item['moduleMvid'] == mvid]
    require(len(candidates) == 1, 'PE assembly/MVID ambiguous or missing')
    matches = [m for m in candidates[0]['methods'] if m['token'] == token and m['owner'] == owner and m['name'] == method]
    require(len(matches) == 1 and matches[0]['ilBytes'] > 0, 'PE definition/IL binding differs')


def entry(value, interpreted, metadata, owner=None, method=None, collectible=None):
    require(value is not None and not value.get('skipped'), 'Selected post-invocation entry absent')
    require(value['Interpreted'] is interpreted and (value['PrecodeType'] == 6) is interpreted, 'Precode type differs')
    require(value['InvocationEvidence'] and value['Scope'] ==
            'Post-invocation selected entry; no complete invocation or child-dispatch coverage', 'Entry scope/evidence differs')
    if owner is not None:
        require(value['DefiningType'] == owner and value['Method'] == method, 'Definition selection differs')
    if collectible is not None:
        require(value['Collectible'] is collectible, 'Definition ownership differs')
    require(int(value['EntryAddress'], 16) > 0 and int(value['CodeAddress'], 16) > 0, 'Native address absent')
    raw = bytes.fromhex(value['Bytes'])
    require(len(raw) == 16, 'Native code byte span differs')
    if interpreted:
        require(raw[:3] == bytes.fromhex('4c8b15') and raw[7:9] == bytes.fromhex('ff25'), 'Pinned x64 precode shape differs')
    metadata_method(metadata, value['Assembly'], value['ModuleMvid'], value['MethodDefToken'],
                    value['DefiningType'], value['Method'])


def terminal_row(row, scenario, mode, metadata):
    counts = row['Counts']
    require(len(counts) == len(SIGNALS) and all(type(v) is int and v >= 0 for v in counts), 'Terminal counters differ')
    c = dict(zip(SIGNALS, counts))
    selected = '.cctor' if scenario == 'StaticConstructor' else '.ctor' if scenario == 'Constructor' else 'Run'
    signal = 'StaticBefore' if scenario == 'StaticConstructor' else 'ConstructorBefore' if scenario == 'Constructor' else 'Enter'
    entry(row['Entry'], mode != 'ordinary', metadata, 'TerminalUGC.Payload.Entry', selected, True)
    require(row['Entry']['InvocationEvidence'] ==
            f'counter={signal};value={c[signal]};callback frame returned or host caught actual failure' and c[signal] > 0,
            'Entry does not follow actual selected invocation counter')
    if scenario == 'Good':
        require(row['Returned'] and row['Value'] == 73 and c['Starts'] == 1 and c['Good'] == 1, 'Good session/static reset differs')
        if mode == 'terminal':
            ledger(row['Snapshot'], 1000000, False)
        return
    if mode != 'terminal':
        if scenario == 'ThrowingFinally':
            require(not row['Returned'] and row['ExceptionType'] == 'System.InvalidOperationException', 'Ordinary finally failure differs')
        else:
            require(row['Returned'] and row['Value'] == (99 if scenario == 'CatchReturn' else 17), 'Finite control value differs')
        if scenario in ('TypedCatch', 'BroadCatch', 'CatchReturn'):
            require(c['Catch'] == 1, 'Ordinary catch not entered')
        if scenario in ('Filter', 'SignalFilter'):
            require(all(c[k] == 1 for k in ('FilterEntered', 'FilterReturned', 'FilterCatch')), 'Ordinary filter not entered')
        if scenario in ('FiniteFinally', 'NestedFinally'):
            require(c['Helper'] > 0 and c['Delegate'] > 0, 'Ordinary private cleanup absent')
        if scenario == 'TrustedReenter':
            require(c['TrustedCaught'] == c['ReentrySucceeded'] == c['Good'] == 1, 'Ordinary trusted reentry absent')
        if mode == 'diagnostic':
            s = row['Snapshot']
            require(s['Remaining'] == 0 and s['Executed'] > 2048 and s['Exhausted'] and not s['IsTerminated'],
                    'Diagnostic accounting did not permit continuation')
        else:
            require(row['Snapshot'] is None, 'Ordinary context fabricated ledger')
        return
    ledger(row['Snapshot'], 2048, True)
    require(not row['Returned'] and row['ExceptionType'] and c['Catch'] == c['Post'] == c['FilterCatch'] == 0,
            'Author terminal catch/continuation escaped')
    s = row['Snapshot']
    expected = {
        'Filter': {'FilterEntered': 1, 'FilterReturned': 0},
        'SignalFilter': {'FilterEntered': 0, 'FilterReturned': 0},
        'FiniteFinally': {'Finally': 1, 'Helper': 1, 'Delegate': 1},
        'NestedFinally': {'InnerFinally': 1, 'OuterFinally': 1, 'Helper': 2, 'Delegate': 2},
        'InfiniteFinally': {'InnerFinally': 1, 'OuterFinally': 0},
        'ThrowingFinally': {'ThrowingFinally': 1, 'OuterFinally': 1},
        'Constructor': {'ConstructorBefore': 1, 'ConstructorAfter': 0, 'Enter': 0},
        'StaticConstructor': {'StaticBefore': 1, 'StaticAfter': 0, 'Enter': 0},
        'TrustedReenter': {'TrustedEntered': 1, 'TrustedCaught': 1, 'ReentryAttempt': 1, 'ReentrySucceeded': 0, 'Good': 0},
    }
    require(all(c[k] == v for k, v in expected.get(scenario, {}).items()), 'Scenario cleanup/constructor/reentry differs')
    if scenario == 'InfiniteFinally':
        require(s['Phase'] == 2 and s['CleanupExecuted'] == 4096 and s['CleanupRemaining'] == 0, 'Infinite cleanup unbounded')
    elif scenario in ('FiniteFinally', 'NestedFinally', 'ThrowingFinally'):
        require(s['Phase'] == 1 and s['CleanupExecuted'] > 0, 'Finite cleanup reserve missing')
    if row['Ownership']:
        o = row['Ownership']
        require(o['goodBefore'] == o['goodAfterBad'] and o['badAfterBad'] == o['badAfterGood'], 'Cross-session owner isolation differs')
        require(o['badAfterBad'] == s, 'Bad-row ownership ledger differs')
        ledger(o['badBefore'], 2048, False)
        ledger(o['goodBefore'], 1000000, False)
        ledger(o['goodAfterGood'], 1000000, False)


def finalizer_positive(receipt, owner, observed, metadata, raw):
    case = receipt['scenario']
    require(receipt['targetCollected'] and receipt['contextCollected'] and receipt['queueSentinels'] == 2, 'Finalizer queue/collection differs')
    counts = receipt['counts']
    require(len(counts) == 10 and counts[0] == 1 and counts[7] == 2, 'Finalizer constructor/sentinels differ')
    require(owner['targetCollectible'] and owner['targetAssembly'] == 'FinalizerProbe.Payload', 'Finalizer target ownership differs')
    expected_owner = {'InheritedTrustedBase': 'FinalizerProbe.Contract.TrustedBase',
                      'AuthorOverrideFinite': 'FinalizerUGC.Payload.OverrideFiniteTarget',
                      'AuthorOverrideInfinite': 'FinalizerUGC.Payload.OverrideInfiniteTarget'}.get(case, 'FinalizerUGC.Payload.Target')
    require(owner['definingType'] == expected_owner and owner['definingCollectible'] is (case != 'InheritedTrustedBase'),
            'Finalizer definition ownership differs')
    metadata_method(metadata, owner['definingAssembly'], owner['module'], owner['token'], owner['definingType'], 'Finalize')
    for pass_number in (1, 2):
        exact_line(raw, f"FINALIZER QUEUE nonce={receipt['nonce']} pass={pass_number} sentinel=true")
    require(raw.splitlines().count('FINALIZER RETIRED rejected=8 exception=System.InvalidOperationException') == 2, 'Retired query guards differ')
    good = receipt['nextGood']
    require(good['value'] == 73 and good['collected'] and good['counts'][8:] == [1, 1], 'Finalizer next-good recovery differs')
    ledger(good['snapshot'], 1000000, False)
    ledger(receipt['before'], 2048)
    if case in ('AlreadyTerminated', 'InheritedTrustedBase'):
        ledger(receipt['before'], 2048, True)
        require(receipt['after'] == receipt['before'] and counts[1] == 0, 'Suppressed/inherited finalizer charged author ledger')
        require(counts[6] == (1 if case == 'InheritedTrustedBase' else 0), 'Inherited trusted base progress differs')
    elif case == 'GoodFiniteControl':
        require(counts[1:3] == [1, 1], 'Finite finalizer did not complete')
        ledger(receipt['after'], 2048, False)
    else:
        require(counts[1:3] == [1, 0], 'Active finalizer continued after terminal boundary')
        require(not receipt['before']['IsTerminated'] and receipt['before']['Executed'] > 0, 'Active finalizer setup already terminal')
        if case == 'UnloadBeforeFinalization':
            require(receipt['retiredBeforeFinalization'] and receipt['after'] is None, 'Retired binder snapshot fabricated')
            exact_line(raw, 'FINALIZER ROOT held-through-unload=true retiredQueriesRejected=true targetReleased=false')
        else:
            ledger(receipt['after'], 2048, True)
            s = receipt['after']
            infinite = case in ('ActiveLoopInfiniteFinally', 'AuthorOverrideInfinite')
            require(s['Phase'] == (2 if infinite else 1), 'Finalizer cleanup phase differs')
            if infinite:
                require(s['CleanupExecuted'] == 4096 and s['CleanupRemaining'] == 0, 'Finalizer infinite cleanup unbounded')
        if case in ('ActiveLoopFinally', 'UnloadBeforeFinalization', 'AuthorOverrideFinite'):
            require(counts[3:6] == [1, 1, 1], 'Finalizer private cleanup/delegate absent')
        if case in ('ActiveLoopInfiniteFinally', 'AuthorOverrideInfinite'):
            require(counts[3] == 1, 'Infinite finalizer cleanup not entered')
        if case.startswith('AuthorOverride'):
            require(counts[6] == (1 if case == 'AuthorOverrideFinite' else 0), 'Implicit base chain boundary differs')
    if case == 'AlreadyTerminated':
        require(observed.get('skipped') and counts[1] == 0 and 'no execution evidence' in observed['reason'],
                'Suppressed finalizer falsely supplies entry evidence')
    else:
        trusted = case == 'InheritedTrustedBase'
        entry(observed, not trusted, metadata, expected_owner, 'Finalize', not trusted)
        signal, count = ('BaseEntered', counts[6]) if trusted else ('AuthorEntered', counts[1])
        require(observed['InvocationEvidence'] == f'counter={signal};value={count};actual finalization drain returned',
                'Finalizer entry lacks actual drain counter')


def host_row(row, case):
    report = row['report']
    require(row['collected'] and report['ExecutionPolicy'] == report['ExecutionPolicyVersion'] == 1, 'Host policy/collection differs')
    constructed = case not in ('ConstructorLoop', 'StaticConstructorLoop')
    require(report['CreatedEntities'] == report['ReleasedEntities'] == int(constructed) and report['RemainingEntities'] == 0,
            'Host-owned resources not released')
    logs = report['Logs']
    if case == 'Normal':
        require(report['Outcome'] == 0 and report['CompletedTicks'] == 3 and report['Error'] is None and
                logs == ['start', 'static=1', 'tick=0', 'tick=1', 'tick=2', 'stop'], 'Normal lifecycle/static state differs')
    else:
        require(report['Outcome'] == 1 and report['Error'] and report['CompletedTicks'] == (3 if case == 'StopLoop' else 0),
                'Host failure/ticks differs')
        blocked = {'catch', 'broad-catch', 'resume', 'signal-filter', 'filter-catch', 'fallback-catch', 'filter-after',
                   'tick-after', 'stop-after', 'start-after', 'unexpected-tick'}
        require(not blocked.intersection(logs), 'Authored continuation escaped host budget')
        required = {'FiniteCleanup': ['finally', 'private-finally', 'private-delegate'],
                    'InfiniteCleanup': ['private-infinite-finally'], 'FilterExhaustion': ['filter-before'],
                    'StopLoop': ['stop-before']}
        require(all(v in logs for v in required.get(case, [])), 'Host scenario entry/cleanup absent')
        require(('stop' in logs) is (case in ('MaliciousMessage', 'ExplicitCanceled')), 'Host OnStop terminal boundary differs')
    s = report['PrototypeBudget']
    normalized = {k: s[v] for k, v in {'Remaining': 'ExecutionRemaining', 'Executed': 'ExecutionExecuted',
                  'Exhausted': 'ExecutionExhausted'}.items()}
    normalized.update({k: s[k] for k in ('IsTerminated', 'Reason', 'Phase', 'CleanupRemaining', 'CleanupExecuted')})
    terminated = case not in ('Normal', 'MaliciousMessage', 'ExplicitCanceled')
    ledger(normalized, 1000000 if case == 'Normal' else 8192, terminated)
    if terminated:
        require('The native prototype instruction budget terminated author execution.' in report['Error'], 'Quota error attribution differs')
    if case == 'FiniteCleanup':
        require(s['Phase'] == 1 and s['CleanupExecuted'] > 0, 'Host finite cleanup reserve absent')
    if case == 'InfiniteCleanup':
        require(s['Phase'] == 2 and s['CleanupExecuted'] == 4096 and s['CleanupRemaining'] == 0, 'Host cleanup unbounded')
    if case in ('MaliciousMessage', 'ExplicitCanceled'):
        require(('HostBudgetUGC.BadMessage' if case == 'MaliciousMessage' else 'System.OperationCanceledException')
                in report['Error'], 'Ordinary author exception misattributed to quota')


def provenance(directory, request, candidate=COMMIT):
    require(request['runtimeConfiguration'] == 'Release' and request['candidateCommit'] == candidate and
            ('runtimeBase' not in request or request['runtimeBase'] == BASE),
            'Release source base/configuration differs')
    record = directory / 'runtime-provenance.json'
    match_hash(record, request['runtimeProvenanceSha256'])
    p = load(record)
    binding = p['binding']
    require(p['passed'] and p['configuration'] == binding['configuration'] == 'Release' and
            binding['actualSourceCommit'] == candidate, 'Frozen runtime identity differs')
    require(binding['cmakeFeatures'] == {'CLR_CMAKE_TARGET_ARCH': 'x64', 'CLR_CMAKE_TARGET_OS': 'windows',
            'CMAKE_BUILD_TYPE': 'Release', 'FEATURE_INTERPRETER': '1', 'FEATURE_DYNAMIC_CODE_COMPILED': '1'},
            'Actual CMake feature configuration differs')
    for relative, expected in binding['metadataHashes'].items():
        match_hash(directory / relative, expected)
    for path, expected in p['frozenInputHashes'].items():
        match_hash(path, expected)
    build_request = load(directory / 'provenance/build-request.json')
    build_result = load(directory / 'provenance/build-result.json')
    layout = load(directory / 'provenance/layout-receipt.json')
    if candidate != COMMIT or 'candidateValidation' in binding:
        validation = binding['candidateValidation']
        require(validation['candidateCommit'] == candidate and validation['baselineCommit'] == COMMIT and
                validation['upstreamBase'] == BASE and validation['trackedClean'] and
                validation['kind'] == ('baseline' if candidate == COMMIT else 'terminal-increment-child'),
                'Bound strict candidate validation differs')
        require(p['candidateValidation'] == validation and p['candidateCommit'] == candidate,
                'Functional candidate validation differs')
        match_hash(directory / 'provenance/budget-runtime-candidate.py', binding['candidateCheckerSha256'])
        if candidate != COMMIT or 'candidateValidation' in build_request:
            for item in (build_request, build_result, layout):
                require(item['candidateValidation'] == validation and item['candidateCheckerSha256'] == binding['candidateCheckerSha256'],
                        'Build/source-checker candidate validation differs')
            match_hash(directory / 'provenance/build-candidate-checker.py', binding['candidateCheckerSha256'])
    require(build_result['exitCode'] == 0 and build_result['configuration'] == layout['configuration'] == 'Release' and
            build_result['candidateCommit'] == layout['candidateCommit'] == candidate and layout['passed'], 'Successful build/layout absent')
    arguments = build_request['arguments']
    require(arguments[arguments.index('-configuration') + 1] == 'Release' and '-clrinterpreter' in arguments, 'Build command differs')
    match_hash(directory / 'provenance/build-request.json', build_result['requestSha256'])
    match_hash(directory / 'provenance/build-result.json', layout['buildResultSha256'])
    match_hash(directory / 'provenance/build.stdout', build_result['stdoutSha256'])
    match_hash(directory / 'provenance/build.stderr', build_result['stderrSha256'])
    match_hash(directory / 'provenance/CMakeCache.txt', build_result['cmakeCacheSha256'])
    require(layout['upstreamBase'] == BASE and all(candidate in item['stamp'] for item in layout['nativeStamps']) and
            ('runtimeSourceStamp' not in request or candidate in request['runtimeSourceStamp']), 'Native source stamp/base differs')
    require(layout['criticalHashes'] == binding['criticalProductHashes'] if 'criticalHashes' in layout else
            build_result['criticalProductHashes'] == binding['criticalProductHashes'], 'Compiler/native/CoreLib binding differs')
    for relative, expected in build_request['sourceHashes'].items():
        match_hash(directory / 'provenance/runtime-source' / relative, expected)
    for name, expected in request['runtimeHashes'].items():
        paths = list(Path(request['runtimeLayout']).rglob(name))
        require(paths and any(digest(path) == expected.lower() for path in paths), 'Runtime layout member differs: ' + name)
    for path, expected in load(directory / 'managed-identity.json').items():
        match_hash(path, expected)
    for relative, expected in request['sourceHashes'].items():
        match_hash(directory / 'source' / relative, expected)
    match_hash(directory / 'WindowsEntryObservation.cs', request['entryObserverSourceSha256'])
    match_hash(request['sdk'], request['sdkSha256'])
    return {'candidateCommit': candidate, 'upstreamBase': BASE, 'configuration': 'Release',
            'nativeHashes': request['runtimeHashes'], 'frozenRuntimeSourceFiles': len(build_request['sourceHashes']),
            'managedFiles': len(load(directory / 'managed-identity.json'))}


def process_record(directory, name, lane, request):
    p = load(directory / (name + '.log.process.json'))
    process_binding(p, name, lane, request)
    for stream in ('stdout', 'stderr'):
        match_hash(directory / (name + '.log.' + stream), p[stream + 'Sha256'])
    return p, (directory / (name + '.log.stderr')).read_text(encoding='utf-8-sig')


def process_binding(p, name, lane, request):
    require(type(p['processId']) is int and p['processId'] > 0 and p['terminated'] and not p['timedOut'], 'Fresh process/watchdog binding differs')
    require(p['arguments'] == lane['arguments'] and p['settings'] == lane['settings'] and
            Path(p['executable']).resolve() == (Path(request['runtimeLayout']) / 'dotnet.exe').resolve(), 'Launcher binding differs')
    require(p['arguments'][-3:] == [lane['case'], lane['nonce'], lane['mode']] and
            name == f"{lane['mode']}-{lane['case']}-{lane['nonce']}", 'Owned nonce/case/argument binding differs')
    settings = p['settings']
    require(settings['DOTNET_InterpMode'] == '0' and settings['DOTNET_ReadyToRun'] == '1' and
            settings['DOTNET_RuneCLRInterpretCollectible'] == '0' and settings['RUNECLR_POST_EXECUTION_PRECODE'] == '1',
            'Interpretation configuration differs')


def precode_source_binding(runtime, output, candidate=COMMIT):
    files = ('src/coreclr/vm/precode.h', 'src/coreclr/vm/amd64/thunktemplates.asm',
             'src/coreclr/vm/amd64/asmconstants.h')
    require(subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip() == candidate,
            'Precode source checkout differs')
    result = {}
    for relative in files:
        blob = subprocess.check_output(['git', '-C', str(runtime), 'show', candidate + ':' + relative])
        require((runtime / relative).read_bytes().replace(b'\r\n', b'\n') == blob, 'Precode source differs from pinned Git blob')
        frozen = output / 'precode-source' / relative
        frozen.parent.mkdir(parents=True, exist_ok=True); frozen.write_bytes(blob)
        result[relative] = {'sha256': digest(frozen), 'gitBlob': subprocess.check_output(
            ['git', '-C', str(runtime), 'rev-parse', candidate + ':' + relative], text=True).strip()}
    header = (output / 'precode-source' / files[0]).read_text()
    require(re.search(r'struct InterpreterPrecodeData\s*\{\s*TADDR ByteCodeAddr;\s*PCODE Target;\s*BYTE Type;', header) and
            'static const int Type = 0x06;' in header, 'Pinned interpreter precode data/type layout differs')
    asm = (output / 'precode-source' / files[1]).read_text()
    require('mov    r10, QWORD PTR [DATA_SLOT(StubPrecode, SecretParam)]' in asm and
            'jmp    QWORD PTR [DATA_SLOT(StubPrecode, Target)]' in asm, 'Pinned x64 thunk shape differs')
    return result


def candidate_change_binding(runtime, candidate):
    require(not subprocess.check_output(['git', '-C', str(runtime), 'status', '--porcelain', '--untracked-files=no']),
            'Candidate tracked source is dirty')
    if candidate == COMMIT:
        return {'kind': 'baseline', 'candidateCommit': candidate}
    meter = 'src/coreclr/vm/runeclrinstructionmeter.h'
    parents = subprocess.check_output(['git', '-C', str(runtime), 'rev-list', '--parents', '-n', '1', candidate], text=True).split()
    changes = subprocess.check_output(['git', '-C', str(runtime), 'diff', '--name-status', COMMIT, candidate], text=True).splitlines()
    require(parents == [candidate, COMMIT] and changes == ['M\t' + meter], 'Candidate is not an exact direct single-file child')
    original = subprocess.check_output(['git', '-C', str(runtime), 'show', COMMIT + ':' + meter])
    actual = subprocess.check_output(['git', '-C', str(runtime), 'show', candidate + ':' + meter])
    old = b'''                previous = InterlockedCompareExchange64(&executed, 0, 0);
                while (true)
                {
                    observed = InterlockedCompareExchange64(&executed, previous + 1, previous);
                    if (observed == previous)
                        return true;
                    previous = observed;
                }'''
    new = b'''                InterlockedIncrement64(&executed);
                return true;'''
    require(original.count(old) == 1 and actual == original.replace(old, new, 1), 'Candidate contains changes beyond atomic-increment replacement')
    require((runtime / meter).read_bytes().replace(b'\r\n', b'\n') == actual, 'Working meter differs from candidate Git blob')
    for revision in (COMMIT, candidate):
        mode = subprocess.check_output(['git', '-C', str(runtime), 'ls-tree', revision, '--', meter]).split()[0]
        require(mode == b'100644', 'Candidate meter file mode differs')
    return {'kind': 'terminal-increment-child', 'candidateCommit': candidate, 'parentCommit': COMMIT,
            'meterPath': meter, 'baselineSourceSha256': hashlib.sha256(original).hexdigest(),
            'candidateSourceSha256': hashlib.sha256(actual).hexdigest(), 'onlyAtomicExecutedIncrementChanged': True}


def audit_experiment(kind, directory, metadata, candidate=COMMIT):
    request, result = load(directory / 'request.json'), load(directory / 'results.json')
    require(result['passed'] and result['releaseProvenanceUnchanged'] and result['nativeEntryProof'] is False,
            'Retained driver state differs')
    identity_fields = (('sourceUnchanged', 'managedUnchanged', 'runtimeUnchanged') if kind == 'host' else
                       ('runtimeBytesAndSourceUnchanged', 'managedBytesUnchanged'))
    require(all(result[field] for field in identity_fields), 'Retained driver identities differ')
    identity = provenance(directory, request, candidate)
    count, interpreted, native, fatal, skipped, rows = 0, 0, 0, 0, 0, 0
    samples = []
    cases = set()
    for name, lane in result['lanes'].items():
        process, raw = process_record(directory, name, lane, request)
        case, mode, nonce = lane['case'], lane['mode'], lane['nonce']
        cases.add(case)
        prefix = 'TERMINAL' if kind == 'terminal' else 'FINALIZER' if kind == 'finalizer' else 'HOST BUDGET'
        require(any(line.startswith(f'{prefix} RUN nonce={nonce} case={case} mode={mode} runtime=.NET 12.0.0') for line in raw.splitlines()),
                'Actual runtime/nonce run marker absent')
        lane_path = directory / name
        if lane.get('expectedFatal'):
            exception = 'System.OperationCanceledException' if 'Canceled' in case else 'System.InvalidOperationException'
            require(kind == 'finalizer' and process['exitCode'] != 0 and process['expectedFatal'], 'Expected fatal status absent')
            exact_line(raw, f'FINALIZER FATAL ARMED nonce={nonce} case={case} mode={mode} exception={exception} nativeLatchBefore=false')
            require(re.search(r'^Unhandled exception\. ' + re.escape(exception) + r'(?:[:\r\n]|$)', raw, re.M) and
                    'Finalize()' in raw and 'at System.GC.RunFinalizers()' in raw, 'Original unhandled finalizer exception absent')
            require(not (lane_path / 'result.json').exists() and not (lane_path / 'post-finalizer-entry.json').exists(),
                    'Fatal lane unexpectedly has positive outcome/entry proof')
            owner = load(lane_path / 'finalizer-owner.json')
            trusted = case.startswith('FatalTrusted')
            require(owner['targetCollectible'] is (not trusted) and owner['definingCollectible'] is (not trusted), 'Fatal definition owner differs')
            metadata_method(metadata, owner['definingAssembly'], owner['module'], owner['token'], owner['definingType'], 'Finalize')
            fatal += 1
            samples.append({'name': name, 'processId': process['processId'], 'nonce': nonce, 'expectedFatal': True})
            continue
        require(process['exitCode'] == 0 and lane['passed'], 'Positive process outcome differs')
        receipt = load(lane_path / 'result.json')
        match_hash(lane_path / 'result.json', lane['scalarReceiptSha256'])
        require(receipt['passed'] and receipt['nonce'] == nonce and receipt['scenario'] == case and receipt['mode'] == mode, 'Scalar nonce binding differs')
        if kind == 'terminal':
            expected = 40 if case == 'Recovery' else 2 if case == 'TwoContexts' else 1
            require(len(receipt['rows']) == expected, 'Terminal row count differs')
            exact_line(raw, f'TERMINAL COMPLETE nonce={nonce} case={case} mode={mode} rows={expected} prototypeOnly=true')
            for index, row in enumerate(receipt['rows']):
                scenario = ('Good' if row['Role'] == 'good' else 'BroadCatch') if case in ('Recovery', 'TwoContexts') else case
                require(row['Session'] == (index // 2 + 1 if case == 'Recovery' else 1) and
                        row['Role'] == ('good' if index % 2 else 'bad') if case in ('Recovery', 'TwoContexts') else
                        row['Session'] == 1 and row['Role'] == 'case', 'Terminal row order differs')
                terminal_row(row, scenario, mode, metadata)
                interpreted += int(row['Entry']['Interpreted']); native += int(not row['Entry']['Interpreted'])
            if case == 'Recovery':
                for session in range(1, 21):
                    exact_line(raw, f'PASS terminal-recovery session={session} badCollected=true goodCollected=true goodValue=73 starts=1')
            elif case == 'TwoContexts':
                exact_line(raw, 'PASS terminal-two-contexts ownerIsolated=true badCollected=true goodCollected=true')
                require(receipt['rows'][0]['Ownership'] is not None, 'Two-context isolation record missing')
            else:
                require(any(line.startswith(f'PASS terminal-case={case} collected=true counts=') for line in raw.splitlines()), 'Terminal collection marker absent')
            rows += expected
        elif kind == 'finalizer':
            owner, observed = load(lane_path / 'finalizer-owner.json'), load(lane_path / 'post-finalizer-entry.json')
            finalizer_positive(receipt, owner, observed, metadata, raw)
            exact_line(raw, f'FINALIZER COMPLETE nonce={nonce} case={case} mode={mode} targetCollected=true contextCollected=true sentinels=2 nextGood=73 nextCollected=true')
            skipped += int(observed.get('skipped', False))
            interpreted += int(observed.get('Interpreted', False))
            native += int(not observed.get('Interpreted', False) and not observed.get('skipped', False))
        else:
            expected = 40 if case == 'Recovery' else 20 if case == 'Normal' else 1
            require(len(receipt['rows']) == expected, 'Host row count differs')
            exact_line(raw, f'HOST BUDGET COMPLETE nonce={nonce} case={case} mode={mode} rows={expected} prototypeOnly=true')
            for index, row in enumerate(receipt['rows']):
                require(row['session'] == (index // 2 + 1 if case == 'Recovery' else index + 1), 'Host session order differs')
                expected_role = ('good' if index % 2 else 'bad') if case == 'Recovery' else 'case'
                require(row['role'] == expected_role, 'Host recovery role differs')
                actual_case = ('Normal' if row['role'] == 'good' else 'CatchResume') if case == 'Recovery' else case
                host_row(row, actual_case)
            trusted = load(lane_path / 'trusted-entry.json')
            entry(trusted, False, metadata, 'RuneCLR.Runtime.MapRunner', 'Run', False)
            require(trusted['InvocationEvidence'] == 'MapRunner.Run returned validated host report and collected ticket', 'Trusted host invocation absent')
            native += 1; rows += expected
        count += 1
        samples.append({'name': name, 'processId': process['processId'], 'nonce': nonce, 'expectedFatal': False})
    require(cases == set(request['cases']), 'Requested cases incomplete')
    expected_counts = {'terminal': (44, 84, 70, 14, 0, 0), 'finalizer': (9, 0, 7, 1, 6, 1), 'host': (15, 73, 0, 15, 0, 0)}
    require((count, rows, interpreted, native, fatal, skipped) == expected_counts[kind], 'Measured scope/count differs')
    return {'passed': True, 'identity': identity, 'positiveLanes': count, 'rows': rows, 'interpreterPostInvocationEntries': interpreted,
            'nativePostInvocationEntries': native, 'originalExceptionFatalControls': fatal, 'suppressedNoEntryClaims': skipped,
            'requestSha256': digest(directory / 'request.json'), 'resultsSha256': digest(directory / 'results.json'), 'processBindings': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'artifacts/release-budget-functional')
    parser.add_argument('--candidate-commit', default=COMMIT)
    parser.add_argument('--terminal-evidence', type=Path)
    parser.add_argument('--finalizer-evidence', type=Path)
    parser.add_argument('--host-evidence', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--metadata-reader', type=Path, default=ROOT / 'eng/managed-entry-metadata/bin/Release/net11.0/RuneCLR.ManagedEntryMetadata.dll')
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f]{40}', args.candidate_commit), 'Explicit full lowercase candidate SHA required')
    experiments = {kind: getattr(args, kind + '_evidence') or args.evidence / name for kind, name in EXPERIMENTS.items()}
    require(not args.output.exists(), 'Fresh audit directory required')
    args.output.mkdir(parents=True)
    shutil.copy2(__file__, args.output / Path(__file__).name)
    request = load(experiments['terminal'] / 'request.json')
    precode_sources = precode_source_binding(Path(request['runtimeRepo']), args.output, args.candidate_commit)
    candidate_change = candidate_change_binding(Path(request['runtimeRepo']), args.candidate_commit)
    paths = []
    for directory in experiments.values():
        paths.extend(path for folder in ('host', 'payload') for path in (directory / folder).glob('*.dll'))
    # PEReader reads author bytes without loading or invoking author code.
    metadata_run = subprocess.run([str(ROOT / 'artifacts/toolchains/dotnet-11-rc1/dotnet.exe'), str(args.metadata_reader),
                                  *map(str, paths)], capture_output=True)
    (args.output / 'metadata.stdout').write_bytes(metadata_run.stdout)
    (args.output / 'metadata.stderr').write_bytes(metadata_run.stderr)
    require(metadata_run.returncode == 0, 'PE-only metadata reader failed')
    metadata = json.loads(metadata_run.stdout)
    # Copies of Contract in host/payload are identical; de-duplicate only exact identity.
    unique = {}
    for item in metadata:
        match_hash(item['path'], item['sha256'])
        if Path(item['path']).parent.name == 'payload':
            require(item['managedNativeRva'] == 0, 'Author fixture unexpectedly contains managed native code')
        unique[(item['assembly'], item['moduleMvid'], item['sha256'])] = item
    metadata = list(unique.values())
    outcomes = {kind: audit_experiment(kind, directory, metadata, args.candidate_commit) for kind, directory in experiments.items()}
    negatives = []
    terminal, finalizer, host = (experiments[kind] for kind in ('terminal', 'finalizer', 'host'))
    tr = next(load(path / 'result.json')['rows'][0] for path in terminal.glob('terminal-TightLoop-*') if path.is_dir())
    fr_path = next(path for path in finalizer.glob('terminal-ActiveLoop-*') if path.is_dir())
    fr, owner, observed = (load(fr_path / name) for name in ('result.json', 'finalizer-owner.json', 'post-finalizer-entry.json'))
    fr_raw = (finalizer / (fr_path.name + '.log.stderr')).read_text()
    hr = next(load(path / 'result.json')['rows'][0] for path in host.glob('budget-EndlessTick-*') if path.is_dir())
    def negative(name, value, mutate, verify):
        edited = copy.deepcopy(value); mutate(edited)
        try:
            verify(edited)
        except (ValueError, KeyError) as error:
            negatives.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('Corruption was accepted: ' + name)
    tv = lambda v: terminal_row(v, 'TightLoop', 'terminal', metadata)
    negative('terminal-author-catch', tr, lambda v: v['Counts'].__setitem__(1, 1), tv)
    negative('terminal-latch-reset', tr, lambda v: v['Snapshot'].__setitem__('IsTerminated', False), tv)
    negative('terminal-execution-drift', tr, lambda v: v['Snapshot'].__setitem__('Executed', 2049), tv)
    negative('terminal-native-fallback', tr, lambda v: v['Entry'].__setitem__('PrecodeType', -1), tv)
    negative('terminal-mvid-substitution', tr, lambda v: v['Entry'].__setitem__('ModuleMvid', '00000000-0000-0000-0000-000000000000'), tv)
    negative('terminal-definition-substitution', tr, lambda v: v['Entry'].__setitem__('MethodDefToken', '0x06000001'), tv)
    fv = lambda v: finalizer_positive(v, owner, observed, metadata, fr_raw)
    negative('finalizer-queue-stalled', fr, lambda v: v.__setitem__('queueSentinels', 1), fv)
    negative('finalizer-context-retained', fr, lambda v: v.__setitem__('contextCollected', False), fv)
    negative('finalizer-next-session-corrupted', fr, lambda v: v['nextGood'].__setitem__('value', 74), fv)
    negative('finalizer-cleanup-overrun', fr, lambda v: v['after'].__setitem__('CleanupExecuted', 4097), fv)
    negative('finalizer-owner-substitution', owner, lambda v: v.__setitem__('definingCollectible', False),
             lambda v: finalizer_positive(fr, v, observed, metadata, fr_raw))
    hv = lambda v: host_row(v, 'EndlessTick')
    negative('host-context-retained', hr, lambda v: v.__setitem__('collected', False), hv)
    negative('host-resource-leak', hr, lambda v: v['report'].__setitem__('RemainingEntities', 1), hv)
    negative('host-author-resume', hr, lambda v: v['report']['Logs'].append('resume'), hv)
    negative('host-budget-reset', hr, lambda v: v['report']['PrototypeBudget'].__setitem__('ExecutionExecuted', 8191), hv)
    name, lane = next(iter(load(terminal / 'results.json')['lanes'].items()))
    process = load(terminal / (name + '.log.process.json'))
    pv = lambda v: process_binding(v, name, lane, request)
    negative('launcher-watchdog-timeout', process, lambda v: v.__setitem__('timedOut', True), pv)
    negative('launcher-missing-pid', process, lambda v: v.__setitem__('processId', 0), pv)
    negative('launcher-nonce-substitution', process, lambda v: v['arguments'].__setitem__(-2, '0' * 32), pv)
    negative('launcher-interpretation-switch-substitution', process, lambda v: v['settings'].__setitem__('DOTNET_InterpMode', '1'), pv)
    negative('owned-raw-marker-substitution', fr_raw, lambda v: None,
             lambda v: exact_line(v.replace(fr['nonce'], '0' * 32), f"FINALIZER QUEUE nonce={fr['nonce']} pass=1 sentinel=true"))
    isolated = next(load(path / 'result.json')['rows'][0] for path in terminal.glob('terminal-TwoContexts-*') if path.is_dir())
    negative('cross-session-owner-ledger-substitution', isolated,
             lambda v: v['Ownership']['goodAfterBad'].__setitem__('Executed', 1),
             lambda v: terminal_row(v, 'BroadCatch', 'terminal', metadata))
    result = {'passed': True, 'candidateCommit': args.candidate_commit, 'experimentPaths': {kind: str(path.resolve()) for kind, path in experiments.items()},
              'experiments': outcomes, 'negativeControls': negatives, 'metadataFiles': len(metadata),
              'metadataReaderSha256': digest(args.metadata_reader), 'auditSourceSha256': digest(__file__), 'precodeSources': precode_sources,
              'independentCandidateChange': candidate_change,
              'scope': 'Offline frozen-byte/source/raw-stream/process-record/PE-definition/ledger audit; post-invocation selected entries only',
              'limits': ['Launcher-recorded PIDs bound to raw nonce/arguments; no independent managed PID field',
                         'No complete invocation trace or child-dispatch coverage', 'No fatal per-method entry samples',
                         'Host budget author methods are not individually sampled', 'Private prototype; no real-device or production finalizer acceptance']}
    save(args.output / 'results.json', result)
    print(f'PASS Release audit: terminal 44 lanes/84 rows/70 interpreted+14 native entries; finalizer 9 recovery+6 original fatal controls/7 interpreted+1 trusted native/1 suppressed; host 15 cases/73 collected contexts; {len(negatives)} semantic corruption controls rejected')


if __name__ == '__main__':
    main()
