#!/usr/bin/env python3
"""Independently reconcile an Android five-lane batching run with its raw inputs."""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import zipfile

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
BUILD_SHA = 'e4f0451abf6dcc47671b1ae400a98bf3316b0bf27478c468d1022cab0dd37769'
INPUT_SHA = '82ea9368e8fe6e7070b6d181e09c2294aed0aacb3d2008399ae92a15ae88d3fb'
REVIEW_SHA = '9aab8cae277ad138b6635b9db61bf30bcfa942ce14aa54c56df71e6bb683ccd2'
LANES = ((1, 1), (1, 100), (1, 1000), (100, 100), (1000, 1000))


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def owned(root, relative):
    target = (root / relative).resolve()
    need(target.is_relative_to(root.resolve()), 'Receipt path escapes run directory')
    return target


def unique_line(text, expected):
    need(text.splitlines().count(expected) == 1, 'Missing or repeated exact line: ' + expected)


def elf_x64(path):
    header = Path(path).read_bytes()[:64]
    need(len(header) == 64 and header[:6] == b'\x7fELF\x02\x01'
         and struct.unpack_from('<H', header, 18)[0] == 62, 'Actual native file is not ELF64 x86_64')


def r2r_x64(path):
    data = Path(path).read_bytes()
    need(data[:2] == b'MZ', 'Actual component is not managed PE')
    pe = struct.unpack_from('<I', data, 60)[0]
    need(data[pe:pe + 4] == b'PE\0\0' and struct.unpack_from('<H', data, pe + 4)[0] == 0xfd1d,
         'Actual R2R component is not Linux x64')
    count = struct.unpack_from('<H', data, pe + 6)[0]
    size = struct.unpack_from('<H', data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    need(magic in (0x10b, 0x20b), 'Unsupported actual PE optional header')
    sections = [struct.unpack_from('<IIII', data, opt + size + i * 40 + 8) for i in range(count)]
    def offset(rva, length):
        owners = [raw + rva - va for _, va, rs, raw in sections if va <= rva and rva + length <= va + rs]
        need(len(owners) == 1 and owners[0] + length <= len(data), 'Actual PE range has no unique file owner')
        return owners[0]
    cli_rva = struct.unpack_from('<I', data, opt + (112 if magic == 0x20b else 96) + 14 * 8)[0]
    cli = offset(cli_rva, 72)
    rva, length = struct.unpack_from('<II', data, cli + 64)
    need(rva > 0 and length >= 16 and data[offset(rva, 16):offset(rva, 16) + 4] == b'RTR\0',
         'Actual component lacks ReadyToRun signature')


def reviewer():
    path = Path(__file__).with_name('assess-mobile-batch-boundary.py')
    need(sha(path) == REVIEW_SHA, 'Frozen semantic reviewer changed')
    spec = importlib.util.spec_from_file_location('mobile_boundary_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.review_lane


def assess(root):
    root = root.resolve()
    state = read(root / 'state.json')
    summary = read(root / 'matrix-results.json')
    layout = read(root / 'layout.json')
    inputs = read(root / 'input-manifest.json')
    build = read(root / 'matching-build-review.json')
    need(state['success'] and state['installed'] and state['runtimeCommit'] == COMMIT
         and state['runtimeTree'] == TREE, 'Installed source identity differs')
    need(sha(root / 'driver.py') == state['driverSha256'] == summary['driverSha256'], 'Controller bytes differ')
    need(sha(root / 'layout.json') == state['layoutSha256'] == summary['layoutSha256'], 'Layout binding differs')
    need(sha(root / 'matching-build-review.json') == BUILD_SHA == state['buildReviewSha256']
         and build['commit'] == COMMIT and build['tree'] == TREE and build['success']
         and build['target'] == 'android.x64' and build['configuration'] == 'Release', 'Actual native build differs')
    need(sha(root / 'input-manifest.json') == INPUT_SHA == state['inputManifestSha256']
         == summary['inputManifestSha256'] and inputs['files'] == state['inputFiles'], 'Frozen input binding differs')
    need(layout['schema'] == 'runeclr.android-batch-boundary.layout.v1' and layout['success']
         and layout['compositeInputCount'] == 184 and layout['compositeFileCount'] == 185
         and layout['nativeMeterSize'] == 72 and layout['nativeBatchIntervalOffset'] == 64
         and layout['executableAssembly'] == 'AndroidBatchBoundaryBridge.dll', 'Matching batch layout differs')
    staged = state['appHashes']
    need(not any('BatchBoundary.Author' in name for name in staged), 'Author was packaged into trusted host')
    need({p.name: sha(p) for p in (root / 'app').iterdir() if p.is_file()} == staged, 'Staged application bytes changed')
    for row in layout['files']:
        if row['path'].startswith(('managed/', 'native/', 'java/')):
            need(staged.get(Path(row['path']).name) == row['sha256'], 'Layout/staged component hash differs')
    actual_components = [root / 'app' / Path(row['path']).name for row in layout['files']
                         if row['path'].startswith('managed/') and row['path'].endswith('.dll')]
    need(len(actual_components) == 185, 'Fresh component count differs')
    for path in actual_components:
        r2r_x64(path)
    for key, name in (('native', 'libcoreclr.so'), ('interpreter', 'libclrinterpreter.so'), ('targetJit', 'libclrjit.so')):
        need(staged[name] == build['criticalHashes'][key], 'APK does not use matching critical native product')
        elf_x64(root / 'app' / name)
    apk = Path(state['apk'])
    need(sha(apk) == state['apkSha256'] == summary['apkSha256'], 'Actual APK hash differs')
    package_bytes = {}
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        need(len(set(names)) == len(names), 'Duplicate APK members')
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/assets.zip'))) as assets:
            members = [name for name in assets.namelist() if not name.endswith('/')]
            need(len(set(members)) == len(members) and all('/' not in name for name in members), 'Ambiguous nested assets')
            package_bytes.update({name: hashlib.sha256(assets.read(name)).hexdigest() for name in members})
        natives = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names
                   if name.startswith('lib/') and name.endswith('.so')}
        need(natives == state['apkNativeHashes'] and all(name.startswith('lib/x86_64/') for name in natives),
             'Actual APK native membership differs')
        package_bytes.update({Path(name).name: digest for name, digest in natives.items()})
        dexes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names
                 if re.fullmatch(r'classes([2-9]|[1-9][0-9]+)\.dex', name)}
        need(dexes == state['apkDexHashes'], 'Actual APK crypto Java bytes differ')
        for name, digest in staged.items():
            if name.endswith('.dex'):
                need(list(dexes.values()).count(digest) == 1, 'Staged DEX is not uniquely packaged')
            else:
                need(package_bytes.get(name) == digest, 'Staged bytes differ from actual APK')
        need(not any('BatchBoundary.Author' in name for name in package_bytes), 'Author present in actual APK')
    author = state['authorHashes']['author/BatchBoundary.Author.dll']
    for name, digest in state['authorHashes'].items():
        need(sha(root / 'postinstall-author' / Path(name).name) == digest == inputs['files'][name], 'Late author bytes changed')
    transfer = read(root / 'postinstall-author.json')
    need(transfer['installedUtc'] == state['installedUtc'] <= transfer['transferStartedUtc'] <= transfer['completedUtc']
         and transfer['files'] == state['authorHashes'], 'Post-install transfer ownership differs')
    need(summary['success'] and summary['platform'] == 'Android.x64' and summary['totalContexts'] == 168
         and summary['collections'] == 168 and summary['physicalDeviceTouched'] is False
         and summary['nativeEntryProof'] is False and summary['liveBatchPathVerified'] is False
         and summary['performanceMeasured'] is False, 'Run summary scope differs')
    need([(lane['configured'], lane['matrix']) for lane in summary['lanes']] == list(LANES), 'Five-lane order differs')
    expected_inventory = dict(staged, **state['authorHashes'])
    expected_inventory['apk/base.apk'] = state['apkSha256']
    validate = reviewer()
    all_rows, controls, owners = {}, [], []
    for lane in summary['lanes']:
        directory = owned(root, lane['receipt']).parent
        result = read(directory / 'mobile-run.json')
        need(sha(directory / 'mobile-run.json') == lane['receiptSha256'], 'Lane summary hash differs')
        for name, digest in result['rawHashes'].items():
            need(sha(owned(directory, name)) == digest, 'Raw lane file changed: ' + name)
        for name in ('matching-build-review.json', 'layout.json', 'postinstall-author.json', 'input-manifest.json'):
            need(sha(directory / name) == sha(root / name), 'Per-lane original input binding differs')
        configured, matrix = lane['configured'], lane['matrix']
        pid, nonce = lane['pid'], lane['nonce']
        owners.append((pid, nonce))
        need(result['success'] and result['appPid'] == pid and result['nonce'] == nonce
             and result['configuredInterval'] == configured and result['matrixInterval'] == matrix
             and result['instrumentationExit'] == 0 and result['timedOut'] is False
             and result['debugger'] is False and result['nativeEntryProof'] is False
             and result['liveBatchPathVerified'] is False
             and result['performanceMeasured'] is False, 'Actual lane ownership/completion/scope differs')
        request = read(directory / 'request.json')
        argv = request['command']
        def argument(name):
            positions = [i for i, value in enumerate(argv) if value == name]
            need(len(positions) == 1, 'Ambiguous actual lane argument')
            return argv[positions[0] + 1]
        need(argument('-s') == 'emulator-5556' and argument('env:RUNECLR_BATCH_NONCE') == nonce
             and argument('env:RUNECLR_BATCH_MATRIX') == str(matrix)
             and argument('env:RUNECLR_BATCH_HEX') == format(configured, 'x')
             and argv[-1] == state['package'] + '/net.dot.MonoRunner', 'Raw instrumentation arguments differ')
        process = read(directory / 'instrumentation.log.process.json')
        need(process['command'] == argv and process['exitCode'] == 0 and process['timedOut'] is False
             and process['logSha256'] == sha(directory / 'instrumentation.log'), 'Actual instrumentation process differs')
        unique_line((directory / 'instrumentation.log').read_text(), 'INSTRUMENTATION_RESULT: return-code=0')
        native = (directory / 'native.log').read_text()
        unique_line(native, f'ANDROID_BATCH_NATIVE pid={pid} nonce={nonce} matrix={matrix} interval={configured:x} PhaseAcquireLoad=1 DerivedLedger=0 InterpMode=0 ReadyToRun=1')
        for marker in ('CORECLR_INITIALIZE_HRESULT=0x0', 'CORECLR_EXECUTE_HRESULT=0x0;RUNECLR_EXIT=0', 'CORECLR_SHUTDOWN_HRESULT=0x0'):
            unique_line(native, marker)
        unique_line((directory / 'pid-query.txt').read_text(), 'android.os.Process.myPid=' + str(pid))
        managed = read(directory / 'managed-result.json')
        need(managed['appPid'] == pid and managed['nonce'] == nonce and managed['matrix'] == str(matrix)
             and managed['interval'] == format(configured, 'x') and managed['exitCode'] == 0
             and all(managed[key] == 1 for key in ('policy', 'meter', 'terminal', 'gc'))
             and managed['defaultPolicy'] == 0, 'Managed native-ack/PID/configuration differs')
        receipt = read(directory / 'boundary.json')
        rows = validate(receipt, configured, matrix, 'Android.x64', author, pid, nonce)
        marker = f'BATCH_BOUNDARY_COMPLETE nonce={nonce} pid={pid} N={matrix} rows={len(rows)}'
        unique_line(native, marker)
        unique_line((directory / 'managed.log').read_text(), marker)
        need(lane['rows'] == result['rows'] == len(rows)
             and lane['collections'] == result['collections'] == sum(row['Collected'] is True for row in rows), 'Actual row/collection count differs')
        for label in ('installed-before', 'installed-after'):
            need(read(directory / (label + '.json')) == expected_inventory, 'Complete installed inventory differs')
            raw = (directory / (label + '.sha256sum.log')).read_text().splitlines()
            need(len(raw) == len(expected_inventory) and all(len(line.split()) == 2 for line in raw), 'Raw installed inventory incomplete')
            observations = {line.split()[1]: line.split()[0] for line in raw}
            need(len(observations) == len(raw), 'Duplicate installed paths')
            for name, digest in expected_inventory.items():
                if name == 'apk/base.apk':
                    matches = [value for path, value in observations.items() if path.endswith('/base.apk')]
                    need(matches == [digest], 'Raw installed APK digest differs')
                else:
                    actual = (result['actualNativeRuntimeDirectory'] + '/' + name
                              if name.endswith('.so') else 'files/' + name)
                    need(observations.get(actual) == digest, 'Raw installed file digest differs: ' + name)
        maps = (directory / 'maps.log').read_text()
        for name in ('libcoreclr.so', 'libclrinterpreter.so', 'libclrjit.so'):
            paths = set(re.findall(r'(?m)(/[^\s]+/' + re.escape(name) + r')$', maps))
            need(paths == {result['actualNativeRuntimeDirectory'] + '/' + name}, 'Actual mapped native image differs')
        # Alter real receipts: these controls exercise recovery and scope claims.
        mutations = [
            ('wrong-pid', lambda value: value.__setitem__('processId', pid + 1)),
            ('wrong-author', lambda value: value.__setitem__('authorHash', '0' * 64)),
            ('promoted-cadence', lambda value: value.__setitem__('liveBatchPathVerified', True)),
            ('retained-context', lambda value: value['rows'][0].__setitem__('Collected', False)),
            ('recovery-checksum', lambda value: next(row for row in value['rows'] if row['Role'] == 'recovery')['Observations'].__setitem__('Value', -1)),
            ('over-bound', lambda value: next(row for row in value['rows'] if row['Observations'] and row['Observations']['Snapshot']['IsTerminated'])['Observations']['Snapshot'].__setitem__('Executed', 1000000000)),
        ]
        for name, mutate in mutations:
            altered = copy.deepcopy(receipt)
            mutate(altered)
            try:
                validate(altered, configured, matrix, 'Android.x64', author, pid, nonce)
            except RuntimeError as error:
                controls.append({'lane': [configured, matrix], 'mutation': name, 'rejected': True, 'reason': str(error)})
            else:
                raise RuntimeError('Altered actual receipt accepted: ' + name)
        all_rows[(configured, matrix)] = rows
    need(len(set(pid for pid, _ in owners)) == len(set(nonce for _, nonce in owners)) == 5, 'Fresh process/nonce reused')
    need(sum(len(rows) for rows in all_rows.values()) == 169
         and sum(row['Collected'] is True for rows in all_rows.values() for row in rows) == 168, '169 observations /168 collections expected')
    calibration = []
    for interval in (100, 1000):
        before, after = all_rows[(1, interval)], all_rows[(interval, interval)]
        for baseline, candidate in zip(before, after):
            if candidate['Role'] != 'calibration':
                continue
            need(baseline['Observations']['Snapshot']['Executed'] == candidate['Observations']['Snapshot']['Executed'],
                 'Completed partial settlement differs from same-platform exact control')
            calibration.append({'interval': interval, 'method': candidate['Method'],
                                'executed': candidate['Observations']['Snapshot']['Executed']})
    cleanup = read(root / 'cleanup.json')
    need(cleanup['success'] and cleanup['package'] == state['package'] and cleanup['appUninstalled']
         and cleanup['physicalDeviceTouched'] is False, 'Owned application cleanup incomplete')
    return {'passed': True, 'platform': 'Android.x64', 'functionalEmulatorVerified': True, 'processes': 5,
            'observations': 169, 'collections': 168, 'r2rComponents': len(actual_components),
            'installedFilesPerObservation': len(expected_inventory), 'negativeControls': controls,
            'partialSettlements': calibration, 'sameProcessRecovery': True, 'nativeEntryProof': False,
            'liveBatchPathVerified': False, 'performanceMeasured': False, 'physicalDeviceVerified': False,
            'apkSha256': state['apkSha256'], 'layoutSha256': state['layoutSha256'],
            'sourceCommit': COMMIT, 'sourceTree': TREE, 'assessorSha256': sha(__file__),
            'scope': 'Actual APK/raw five-lane emulator outcomes, installed bytes, late author transfer and recovery; entry/cadence and timing remain separate.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.run)
    with args.output.open('x', encoding='ascii') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(f"PASS: five Android processes,169 observations,168 collections;{len(result['negativeControls'])} altered receipts rejected")


if __name__ == '__main__':
    main()
