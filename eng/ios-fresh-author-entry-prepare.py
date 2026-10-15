#!/usr/bin/env python3
"""Prepare a fresh-author simulator sampler contract offline; never launch or attach."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import platform
import re
import struct
import subprocess
import uuid

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
STATE_SHA = 'dad906720793ac28271f3c81f3ae5532100005bb3a9842dfc2987fb81dad09af'
ACCEPTANCE_SHA = '4d19ef8a8cff9b1c30b64b8b7ba640123a1c87534b177117997921a84fb01922'
NATIVE_SHA = 'b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae'
PROOF_SHA = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
SCENE_SHA = 'c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a'
TRUSTED = {
    'System.Private.CoreLib.dll': ('60bcb3e62ca1b1ba2504b7b00c8d57723b426eb66ea425e9082afb9255607c81',
                                  '4da263b143b4364fd382fc8482d77291a0380357970ae8fe0655748d2308550e'),
    'SessionBridge.dll': ('e97b5ef13fa5029251dec29d171a640c1d1c342c658ba2859bc2fe015aa8de29',
                         'b79d4398d4fbc810c7f36b4a5bad36263eada3da46024c8611444f28796fc724'),
}
AUTHORS = {
    'HostBudgetProbe.Payload.dll': ('37483ac26d596c463406ee5feefd0d8866078ce28485b029764e98dc38ada1c2',
                                  'a5a85fe5-30aa-44b7-840f-848c02a24dac'),
    'HostBudgetProbe.Private.dll': ('2d70da9c913bc900b920891d0b77ccf47073d372739785998a413fc6892da2a2',
                                  '3a81270a-c338-474a-84aa-f49eb8a9e489'),
}
FIELDS = {
    'RuneCLRInstructionMeter': ('m_terminalPrototype', 'm_phaseAcquireLoad', 'm_derivedLedger',
                               'm_remaining', 'm_executed', 'm_phase', 'm_batchInterval'),
    'InterpMethodContextFrame': ('startIp',),
    'InterpMethod': ('methodHnd', 'codeSize'),
    'MethodDesc': ('m_chunkIndex', 'm_wFlags3AndTokenRemainder', 'm_interpreterCode'),
    'MethodDescChunk': ('m_methodTable', 'm_flagsAndTokenRange'),
    'MethodTable': ('m_dwFlags', 'm_pModule'),
    'Module': ('m_pSimpleName', 'm_path', 'm_baseAddress', 'm_pAssembly', 'm_pPEAssembly'),
}
EXPECTED_LAYOUTS = {
    'RuneCLRInstructionMeter': {'size': 72, 'fields': {'m_terminalPrototype': 1, 'm_phaseAcquireLoad': 2,
        'm_derivedLedger': 3, 'm_remaining': 8, 'm_executed': 16, 'm_phase': 40, 'm_batchInterval': 64}},
    'InterpMethodContextFrame': {'size': 48, 'fields': {'startIp': 8}},
    'InterpMethod': {'size': 56, 'fields': {'methodHnd': 0, 'codeSize': 36}},
    'MethodDesc': {'size': 24, 'fields': {'m_chunkIndex': 2, 'm_wFlags3AndTokenRemainder': 0, 'm_interpreterCode': 16}},
    'MethodDescChunk': {'size': 24, 'fields': {'m_methodTable': 0, 'm_flagsAndTokenRange': 18}},
    'MethodTable': {'size': 64, 'fields': {'m_dwFlags': 0, 'm_pModule': 24}},
    'Module': {'size': 976, 'fields': {'m_pSimpleName': 224, 'm_path': 232, 'm_baseAddress': 256,
                                     'm_pAssembly': 272, 'm_pPEAssembly': 248}},
}
HELPERS = {
    'ios-r2r-release-verify.py': ('29a782a093ee3a6dca355562c08d79b87c9afe96046218190df9507b1422fa7e', ('plugin_methods',)),
    'ios-budget-increment-entry.py': ('1991b6c0906d807b3b69dad69ea151f9ffbb8369c5aad7ceef1010a7fecd4dc1', ('pe_mvid',)),
    'ios-batch-boundary-entry-prepare.py': ('5956effd1046633755e6db7f70915ed8d4f1725cfa579fc7a0b740a1f76d99a8',
                                        ('il_layout', 'native', 'dwarf_layout')),
}
SYMBOL = '__Z16InterpExecMethodP16InterpreterFrameP24InterpMethodContextFrameP19InterpThreadContextP19ExceptionClauseArgs'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def readers():
    scope = {'struct': struct, 'uuid': uuid, 're': re, 'hashlib': hashlib,
             'need': need, 'sha': sha, 'FIELDS': FIELDS}
    for name, (expected, functions) in HELPERS.items():
        path = Path(__file__).with_name(name)
        need(sha(path) == expected, 'Frozen offline reader differs: ' + name)
        nodes = [n for n in ast.parse(path.read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in functions]
        need(len(nodes) == len(functions), 'Offline reader function missing or duplicate')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return scope


def command(argv, out, name):
    argv = [str(x) for x in argv]
    write(out / (name + '.request.json'), {'argv': argv, 'offlineOnly': True, 'timeoutSeconds': 45})
    result = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    (out / (name + '.stdout')).write_text(result.stdout, encoding='utf-8')
    (out / (name + '.stderr')).write_text(result.stderr, encoding='utf-8')
    write(out / (name + '.result.json'), {'exitCode': result.returncode})
    need(result.returncode == 0, 'Offline Apple reader failed: ' + name)
    return result.stdout


def validate_contract(value):
    need(value['platform'] == 'iossimulator.arm64' and value['sourceCommit'] == COMMIT
         and value['sourceTree'] == TREE, 'Simulator source identity differs')
    need(value['sourceNative']['sha256'] == NATIVE_SHA and value['sourceNative']['platform'] == 7
         and value['signedNative']['platform'] == 7, 'Simulator native bytes/platform differs')
    need({k: v for k, v in value['sourceNative'].items() if k != 'sha256'} ==
         {k: v for k, v in value['signedNative'].items() if k != 'sha256'},
         'Signing changed native sections or UUID')
    need(value['dwarfUuid'].replace('-', '').lower() == value['sourceNative']['uuid'],
         'Current simulator DWARF UUID differs')
    need(value['gate'] == {'terminalPrototype': 1, 'phaseAcquireLoad': 1, 'derivedLedger': 1,
                           'batchInterval': 0, 'phase': 0}, 'Fresh author budget gate differs')
    need(value['abi'] == {'contextFrame': 'x1', 'exceptionArgs': 'x3'}, 'Entry ABI differs')
    need(value['layouts'] == EXPECTED_LAYOUTS, 'Current simulator DWARF field layout differs')
    need(value['sceneMainSha256'] == SCENE_SHA, 'Accepted scene wrapper changed')
    for name, (raw, r2r) in TRUSTED.items():
        image = value['trustedImages'][name]
        need(image['rawSha256'] == raw and image['r2rSha256'] == r2r
             and image['layout']['managedNativeRva'] != 0, 'Trusted raw/R2R image changed')
    need(set(value['modules']) == set(AUTHORS) and len(value['requiredMethods']) == 9,
         'Fresh author module or method coverage differs')
    for name, (expected, mvid) in AUTHORS.items():
        module = value['modules'][name]
        need(module['sha256'] == expected and module['moduleMvid'] == mvid
             and module['layout'] == {'ilOnly': True, 'managedNativeRva': 0},
             'Fresh author hash/MVID/IL layout differs')
    need(value['nativeEntryProof'] is False and value['liveRegisterContentsVerified'] is False
         and value['targetProcessCreated'] is False and value['physicalDeviceExecuted'] is False,
         'Offline preparation was promoted to live proof')


def controls(value):
    edits = {
        'device-platform': lambda x: x['sourceNative'].update(platform=2),
        'wrong-dwarf-uuid': lambda x: x.update(dwarfUuid='0' * 32),
        'wrong-native-hash': lambda x: x['sourceNative'].update(sha256='0' * 64),
        'disabled-derived-ledger': lambda x: x['gate'].update(derivedLedger=0),
        'enabled-batching': lambda x: x['gate'].update(batchInterval=1000),
        'old-author-mvid': lambda x: x['modules']['HostBudgetProbe.Payload.dll'].update(moduleMvid='0' * 32),
        'wrong-private-hash': lambda x: x['modules']['HostBudgetProbe.Private.dll'].update(sha256='0' * 64),
        'missing-method': lambda x: x['requiredMethods'].pop(),
        'wrong-frame-layout': lambda x: x['layouts']['InterpMethodContextFrame']['fields'].update(startIp=16),
        'wrong-trusted-bridge': lambda x: x['trustedImages']['SessionBridge.dll'].update(r2rSha256='0' * 64),
        'wrong-corelib': lambda x: x['trustedImages']['System.Private.CoreLib.dll'].update(rawSha256='0' * 64),
        'old-scene-wrapper': lambda x: x.update(sceneMainSha256='0' * 64),
        'promoted-live-proof': lambda x: x.update(nativeEntryProof=True),
    }
    rows = []
    for name, change in edits.items():
        altered = copy.deepcopy(value); change(altered)
        try:
            validate_contract(altered)
        except RuntimeError:
            rows.append({'name': name, 'rejected': True, 'inMemoryOnly': True})
        else:
            raise RuntimeError('Altered sampler contract accepted: ' + name)
    return rows


def prepare(args, out):
    app_root = args.application.resolve(); runtime = args.runtime.resolve(); pe = readers()
    state = read(app_root / 'state.json'); accepted = read(app_root / 'run-all/results.json')
    need(sha(app_root / 'state.json') == STATE_SHA
         and sha(app_root / 'run-all/results.json') == ACCEPTANCE_SHA
         and accepted['passed'] and accepted['cases'] == 15 and accepted['contexts'] == 73
         and accepted['debugger'] is False and accepted['authorCompiledAfterInstallation']
         and accepted['nativeEntryProof'] is False, 'Frozen normal acceptance differs')
    bundle = app_root / 'app/Session.app'
    need({p.relative_to(bundle).as_posix(): sha(p) for p in sorted(bundle.rglob('*')) if p.is_file()}
         == state['bundleHashes'], 'Accepted signed bundle changed')
    need(read(app_root / 'run-all/installed-before.json') == read(app_root / 'run-all/installed-after.json')
         and read(app_root / 'cleanup/results.json')['deleted'], 'Normal identity/retirement receipt differs')
    need(command(['git', '-C', runtime, 'rev-parse', 'HEAD'], out, 'source-commit').strip() == COMMIT
         and command(['git', '-C', runtime, 'rev-parse', 'HEAD^{tree}'], out, 'source-tree').strip() == TREE
         and not command(['git', '-C', runtime, 'status', '--porcelain', '--untracked-files=no'],
                         out, 'source-status').strip(), 'Matching source checkout changed')
    need(sha(app_root / 'source-proof.json') == PROOF_SHA, 'Frozen source proof differs')
    proof = read(app_root / 'source-proof.json')
    for name, expected in proof['sourceHashes'].items():
        need(sha(runtime / name) == expected == sha(app_root / 'source' / name), 'Source-proof file differs')
    native = runtime / 'artifacts/bin/coreclr/iossimulator.arm64.Release/libcoreclr.dylib'
    dwarf = native.with_name(native.name + '.dwarf')
    unsigned, signed = pe['native'](native), pe['native'](bundle / native.name)
    uuids = re.findall(r'UUID: ([0-9A-Fa-f-]+)', command(['xcrun', 'dwarfdump', '--uuid', dwarf], out, 'dwarf-uuid'))
    need(len(uuids) == 1, 'Current simulator DWARF UUID not unique')
    symbols = command(['xcrun', 'nm', '-nm', native], out, 'native-symbols')
    found = re.findall(r'^([0-9a-f]+) \(__TEXT,__text\).* ' + re.escape(SYMBOL) + r'$', symbols, re.M)
    need(len(found) == 1, 'Interpreter entry symbol not unique')
    address = int(found[0], 16)
    command(['xcrun', 'llvm-objdump', '--disassemble', '--start-address=' + hex(address),
             '--stop-address=' + hex(address + 128), native], out, 'entry-instructions')
    layouts = {}
    for name in FIELDS:
        text = command(['xcrun', 'dwarfdump', '--name=' + name, '--show-children', '--recurse-depth=1', dwarf], out, name)
        layouts[name] = pe['dwarf_layout'](text, name)
    modules, required = {}, []
    for name in AUTHORS:
        path = app_root / 'run-all/author-compilation/plugin' / name
        methods = pe['plugin_methods'](path, required=(), qualified=True)
        selected = ('HostBudgetUGC.Base..ctor', 'HostBudgetUGC.Base.OnStart', 'HostBudgetUGC.Base.OnStop',
                    'HostBudgetUGC.Normal..ctor', 'HostBudgetUGC.Normal.OnStart', 'HostBudgetUGC.Normal.OnTick',
                    'HostBudgetUGC.FiniteCleanup.OnTick') if name.endswith('Payload.dll') else (
                    'HostBudgetUGC.Private.Helper.Finite', '<>c__DisplayClass0_0.<Finite>b__0')
        need(set(selected) <= set(methods), 'Required author method absent')
        modules[name] = {'sha256': sha(path), 'layout': pe['il_layout'](path),
                         'methods': {n: methods[n] for n in selected}, **pe['pe_mvid'](path)}
        required.extend(name + ':' + n for n in selected)
    identity = {'platform': 'iossimulator.arm64', 'sourceCommit': COMMIT, 'sourceTree': TREE,
        'sourceNative': unsigned, 'signedNative': signed, 'dwarfUuid': uuids[0], 'dwarfSha256': sha(dwarf),
        'layouts': layouts, 'symbol': {'name': SYMBOL, 'filePc': address},
        'modules': modules, 'requiredMethods': required,
        'gate': {'terminalPrototype': 1, 'phaseAcquireLoad': 1, 'derivedLedger': 1, 'batchInterval': 0, 'phase': 0},
        'abi': {'contextFrame': 'x1', 'exceptionArgs': 'x3'},
        'trustedImages': {n: {'rawSha256': sha(app_root / 'input' / n), 'r2rSha256': sha(bundle / n),
                            'layout': pe['il_layout'](bundle / n)}
                          for n in ('System.Private.CoreLib.dll', 'SessionBridge.dll')},
        'sceneMainSha256': sha(app_root / 'main.m'), 'normalAcceptanceSha256': ACCEPTANCE_SHA,
        'nativeEntryProof': False, 'liveRegisterContentsVerified': False,
        'targetProcessCreated': False, 'physicalDeviceExecuted': False}
    validate_contract(identity); write(out / 'identity.json', identity); write(out / 'controls.json', controls(identity))
    write(out / 'observer-plan.json', {'draftOnly': True, 'reuseAcceptedSignedApp': True,
        'requiresSeparateOwnedSimulatorAndDebugLaunch': True, 'newAuthorCompilationRequiredForNewInstallClaim': True,
        'bindPerSample': ['actual loaded native UUID/slide/PC', 'current context frame/startIp',
                         'MethodDesc MethodDef token', 'loaded PE module MVID/path/hash', 'meter owner and gate',
                         'actual PID/nonce and caller stack'], 'requiredMethods': required,
        'hitCap': 100000, 'timeoutSeconds': 180, 'disableAfterCoverage': True,
        'scope': 'Nine author method groups; does not prove every invocation, first opcode, or performance.',
        'pending': ['Implement and independently review live decoder/observer.',
                    'Create a new owned simulator, install, transfer late IL and make a separate diagnostic launch.',
                    'Verify samples, complete raw managed recovery suite and clean up owned resources.']})
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('application', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); need(platform.system() == 'Darwin', 'Offline Apple readers require the configured Mac')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    result = {'passed': False, 'offlineOnly': True, 'draftOnly': True, 'nativeEntryProof': False,
              'targetProcessCreated': False, 'physicalDeviceExecuted': False, 'driverSha256': sha(__file__)}
    try:
        identity = prepare(args, out)
        result.update(passed=True, requiredMethods=len(identity['requiredMethods']), controls=13)
    except Exception as error:
        result['error'] = str(error); raise
    finally:
        write(out / 'results.json', result); print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
