#!/usr/bin/env python3
"""Bind actual simulator functional evidence; configured switches are not live witnesses."""
import argparse, copy, hashlib, json, re, struct, subprocess
from pathlib import Path

COMMIT = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
PROOF_SHA = 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97'
BUILD_SHA = 'a80501359effdf25bedf7f30bc6f07ab700a68f0efb0fd59f6b80c9c4ac8b7d0'
PARENT_SHA = '6627c434c9919e205a9c38e5dcb1306b391afe31035e9f31c807fc4202d20ef7'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def write(p, v): p.write_text(json.dumps(v, indent=2) + chr(10))
def check(v, m):
    if not v: raise AssertionError(m)

def sections(p):
    data = Path(p).read_bytes()
    check(struct.unpack_from('<I', data)[0] == 0xfeedfacf, 'expected Mach-O64')
    offset, count, image_uuid, digest = 32, 0, None, hashlib.sha256()
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x1b: image_uuid = data[offset + 8:offset + 24].hex()
        if cmd == 0x19:
            for i in range(struct.unpack_from('<I', data, offset + 64)[0]):
                at = offset + 72 + 80 * i
                length, start = struct.unpack_from('<Q', data, at + 40)[0], struct.unpack_from('<I', data, at + 48)[0]
                if start and length:
                    digest.update(data[at:at + 32]); digest.update(data[start:start + length]); count += 1
        offset += size
    return {'uuid': image_uuid, 'fileBackedSections': count, 'sectionsSha256': digest.hexdigest()}

def validate(v):
    check(v['commit'] == COMMIT and v['tree'] == TREE, 'exact derived candidate')
    check(v['proofSha256'] == PROOF_SHA and v['buildSha256'] == BUILD_SHA, 'frozen source/build')
    check(v['layoutSize'] == 64 and v['layoutAlignment'] == 8 and v['phaseOffset'] == 2 and v['derivedOffset'] == 3, 'meter layout')
    check(v['defaultsOff'] is True and v['switchesIndependent'] is True, 'source switch contract')
    check(v['sourceHashesAfter'] == v['sourceHashesProof'] and len(v['sourceHashesProof']) == 37, 'live source hashes')
    check(v['nativeInputSha256'] == v['buildNativeSha256'], 'current native input')
    check(v['nativeSourceSections'] == v['nativeInstalledSections'] and v['nativeSourceSections']['fileBackedSections'] > 0, 'installed native sections')
    check(v['installedNativeSha256'] == v['installedBeforeNativeSha256'] == v['installedAfterNativeSha256'], 'installed native before/after')
    check(v['phaseAcquireLoadConfigured'] == 1 and v['derivedLedgerConfigured'] == 1 and v['nativeSettingsHeaders'] == 1, 'native configuration header')
    check(v['wrapperSettingsBound'] is True and v['launchSettingsBound'] is True, 'wrapper/launch settings')
    check(v['trustedR2R'] is True and v['frameworkInputs'] == 186, 'current framework/trusted bridge')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('player', 'functional', 'inputs', 'runtime', 'native', 'source-proof', 'output'): p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args(); out = a.output.resolve(); out.mkdir(exist_ok=False)
    result = {'passed': False, 'nativeEntryProof': False, 'liveDerivedPathVerified': False, 'physicalDeviceVerified': False}
    try:
        parent = Path(__file__).with_name('mobile-budget-increment-audit.py')
        check(sha(parent) == PARENT_SHA, 'frozen row assessor')
        c = ['/usr/bin/python3', str(parent), '--inputs', str(a.inputs), '--mobile-run', str(a.functional / 'transport-receipt.json'), '--adapter-evidence', str(a.functional / 'adapter-evidence'), '--output', str(out / 'rows'), '--negative-controls']
        with (out / 'row-assessor.log').open('w') as f: q = subprocess.run(c, stdout=f, stderr=subprocess.STDOUT)
        check(q.returncode == 0, 'strict row assessor exit')
        rows = load(out / 'rows/results.json'); check(rows['passed'] and rows['mobileVerified'] and rows['pending'] == [], '15/73 mobile gate')
        state = load(a.player / 'state.json'); run = load(a.functional / 'results.json'); transport = load(a.functional / 'transport-receipt.json')
        bound = load(a.player / 'derived-bindings.json'); proof = load(a.source_proof); build = load(a.player / 'matching-build.json')
        check(sha(a.player / 'derived-bindings.json') == state['derivedBindingsSha256'] == sha(a.functional / 'derived-bindings.json'), 'app binding hash')
        check(sha(a.player / 'state.json') == sha(a.functional / 'original-state.json') == load(a.functional / 'request.json')['stateSha256'], 'frozen app state hash')
        check(bound['runtimeCommit'] == state['runtimeCommit'] == transport['runtimeCommit'] == build['commit'] == COMMIT, 'commit across app/run')
        check(bound['runtimeTree'] == state['runtimeTree'] == transport['runtimeTree'] == build['tree'] == TREE, 'tree across app/run')
        check(bound['sourceProofSha256'] == sha(a.source_proof) == PROOF_SHA and bound['buildReceiptSha256'] == sha(a.player / 'matching-build.json') == BUILD_SHA, 'actual frozen hashes')
        check(subprocess.check_output(['git', '-C', str(a.runtime), 'status', '--porcelain', '--untracked-files=no'], text=True) == '', 'source clean')
        source_hashes = {n: sha(a.runtime / n) for n in proof['sourceHashes']}
        installed = Path(state['installedApp']); before = load(a.functional / 'installed-before.json'); after = load(a.functional / 'installed-after.json')
        nonce, pid = run['nonce'], run['appPid']; text = (a.functional / 'launch.log').read_text()
        marker = f'DERIVED_LEDGER_NATIVE pid={pid} nonce={nonce} PhaseAcquireLoad=1 DerivedLedger=1'
        wrapper = (a.player / 'runtime.m').read_text(); settings = load(a.functional / 'launch-request.json')['environment']
        trusted = ('System.Private.CoreLib.dll', 'SessionBridge.dll', 'MobileHostBudgetProbe.dll', 'RuneCLR.Runtime.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Abstractions.dll')
        v = {'commit': COMMIT, 'tree': TREE, 'proofSha256': sha(a.source_proof), 'buildSha256': sha(a.player / 'matching-build.json'),
             'layoutSize': build['nativeMeterSize'], 'layoutAlignment': build['nativeMeterAlignment'], 'phaseOffset': proof['phaseFlagOffset'], 'derivedOffset': proof['derivedFlagOffset'],
             'defaultsOff': proof['phaseAcquireLoadDefaultOff'] and proof['terminalDerivedLedgerDefaultOff'], 'switchesIndependent': proof['phaseAndDerivedSwitchesIndependent'],
             'sourceHashesAfter': source_hashes, 'sourceHashesProof': proof['sourceHashes'],
             'nativeInputSha256': sha(a.native), 'buildNativeSha256': build['nativeSha256'], 'nativeSourceSections': sections(a.native), 'nativeInstalledSections': sections(installed / 'libcoreclr.dylib'),
             'installedNativeSha256': sha(installed / 'libcoreclr.dylib'), 'installedBeforeNativeSha256': before['bundle']['libcoreclr.dylib'], 'installedAfterNativeSha256': after['bundle']['libcoreclr.dylib'],
             'phaseAcquireLoadConfigured': state['phaseAcquireLoad'], 'derivedLedgerConfigured': state['derivedLedger'], 'nativeSettingsHeaders': len(re.findall(re.escape(marker) + '$', text, re.M)),
             'wrapperSettingsBound': sha(a.player / 'runtime.m') == state['wrapperSourceSha256'] and all(wrapper.count('setenv("DOTNET_' + n + '", "1", 1);') == 1 for n in ('RuneCLRPhaseAcquireLoad', 'RuneCLRDerivedLedger')),
             'launchSettingsBound': all(settings.get('SIMCTL_CHILD_DOTNET_' + n) == '1' for n in ('RuneCLRPhaseAcquireLoad', 'RuneCLRDerivedLedger')),
             'trustedR2R': all(state['layouts'][n]['managedNativeRva'] > 0 for n in trusted), 'frameworkInputs': len(load(a.player / 'framework-reuse.json')['compositeInputs'])}
        validate(v); write(out / 'candidate-bindings.json', v)
        negative = []
        for name, key, value in [('old-tree', 'tree', '91673a7980bda79006259e525741fecb04324444'), ('wrong-native-input', 'nativeInputSha256', '0' * 64), ('old-layout', 'layoutSize', 48), ('phase-off', 'phaseAcquireLoadConfigured', 0), ('derived-off', 'derivedLedgerConfigured', 0), ('missing-native-setting', 'nativeSettingsHeaders', 0), ('unbound-wrapper', 'wrapperSettingsBound', False), ('wrong-signed-native', 'installedNativeSha256', '0' * 64)]:
            mutated = copy.deepcopy(v); mutated[key] = value
            try: validate(mutated)
            except AssertionError: negative.append({'name': name, 'rejected': True, 'inMemoryOnly': True})
            else: raise AssertionError('corrupted binding accepted: ' + name)
        result.update(passed=True, mobileVerified=True, platform='iossimulator.arm64', processId=pid, nonce=nonce, contexts=73, cases=15, debugger=False,
                      rowAuditSha256=sha(out / 'rows/results.json'), candidateBindingsSha256=sha(out / 'candidate-bindings.json'), strictRowNegativeControls=len(rows['negativeControls']), candidateNegativeControls=negative, metrics=rows['metrics'],
                      sourceCommit=COMMIT, sourceTree=TREE, installedNativeSections=v['nativeInstalledSections'], scope='Actual simulator functional semantics and source/build/app/native section bindings; configuredON only, no live meter flags, branch witness, method-entry, performance or physical-device acceptance.')
    except Exception as e: result['error'] = str(e); raise
    finally: result['assessorSha256'] = sha(__file__); write(out / 'results.json', result); print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
