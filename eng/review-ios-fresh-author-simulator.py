#!/usr/bin/env python3
"""Independently bind fresh author IL to a matching simulator application run."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct

ROOT = Path(__file__).resolve().parent.parent
COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
BUILD_SHA = 'c071b2c67103b5646f37cffdc8a442a8e711105585df9740635459ef1bb86745'
AUTHOR_REVIEW_SHA = 'ed128f2b0085347172c0ad12e1e76202e053db5b3168fead68eb595e213967cb'
MANAGED_REVIEW_SHA = 'fda1c5747b3998195ea7584918c0a5b918164c6cdc929865b92892b8ef092148'
ROWS_SHA = '4ecc6e1751d59d9402eeeaf4e5b155c1a44fb2617ec56aadd183d8ca59ba34d4'
FRAMEWORK_SHA = '8a4f83d62d07a4bc75d270951989be6b9c46e7974c34abb636666556a03495cf'
BUILDER_SHA = '2d99895d3d327d484da78ddafbdaaa841e17555af2743bace59ef087221e694b'
CONTINUATION_SHA = '53105c1f8f8321fbb7b4ae309e125f0fb30221abc62fd6eed598850afcbbda5e'
REPAIR_SHA = '5ad5a082100dc0eb7f3c810970111069dba7ed91b50a3d8e3c2815142e24e608'
SCENE_MAIN_SHA = 'c49f3cd9050f5d6fcbf73b92996e8b3a1c291a7ec0fc7e3d44b4be722f3c670a'
WRAPPER_HELPER_SHA = 'c86af795e75cc810ac949a3ff31269465cd7f34665f798f5c1c168a866c5c15d'
BRIDGE_SHA = 'e97b5ef13fa5029251dec29d171a640c1d1c342c658ba2859bc2fe015aa8de29'
PROFILE = {'InterpMode': '0', 'RuneCLRInterpretCollectible': '0', 'ReadyToRun': '1',
           'TieredCompilation': '0', 'SYSTEM_GLOBALIZATION_INVARIANT': '1', 'InterpList': '0',
           'RuneCLRPhaseAcquireLoad': '1', 'RuneCLRDerivedLedger': '1', 'RuneCLRBatchInterval': '0'}
PREVIOUS_AUTHOR = {
    'HostBudgetProbe.Private.dll': ('3427628f9ab003aa92bc62670c4470b8b55db868464e37d2637a5fd692636dde',
                                  '08897279-36fe-4a3e-b555-e2c75ad22db6'),
    'HostBudgetProbe.Payload.dll': ('f722ee94f8f6e03c7a8c4a820d4b8d89994e27616484de61386f89ee807b4aa7',
                                  'f3b655ec-5458-45b1-aeb4-2bc9f73bff7a')}
PRODUCTS = {'nativeSha256': 'b0670a7604bd8857409f1ea9ac543f293c99047286f6f762d0eb720ca6f877ae',
            'corelibSha256': '60bcb3e62ca1b1ba2504b7b00c8d57723b426eb66ea425e9082afb9255607c81',
            'crossgen2Sha256': '1b5da2959311a58ff8ed09c8f695be6869d143ab36f65974bb478b89cc0ab8b7'}
METADATA_KEYS = ('identity', 'mvid', 'metadataRootHeaderSha256', 'canonicalStreams',
                 'tableCounts', 'methods', 'initializedFields')


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def helper(name, filename, expected):
    path = ROOT / 'eng' / filename
    need(sha(path) == expected, 'Independent frozen helper differs: ' + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.utcoffset() is not None, 'Actual ordering requires timezone-qualified timestamps')
    return parsed


def native_image(path):
    image = Path(path).read_bytes()
    need(len(image) >= 32 and struct.unpack_from('<II', image) == (0xfeedfacf, 0x100000c),
         'Actual native image must be thin ARM64 Mach-O')
    kind, count, size = struct.unpack_from('<III', image, 12)
    need(kind in (2, 6), 'Actual native image must be executable or dylib')
    cursor, limit = 32, 32 + size
    need(limit <= len(image), 'Truncated native load-command table')
    versions, sections, uuids, signatures, dependencies, symbols, segments = [], {}, [], [], [], None, []
    for _ in range(count):
        need(cursor + 8 <= limit, 'Truncated native command')
        command, length = struct.unpack_from('<II', image, cursor)
        need(length >= 8 and cursor + length <= limit, 'Invalid native command bounds')
        payload = image[cursor:cursor + length]
        if command == 0x32:
            platform, minimum, sdk, tools = struct.unpack_from('<IIII', payload, 8)
            need(length == 24 + tools * 8, 'Native platform tool table differs')
            versions.append({'platform': platform, 'minimum': minimum, 'sdk': sdk})
        elif command == 0x1b:
            need(length == 24, 'Native UUID command differs')
            uuids.append(payload[8:].hex())
        elif command == 0x1d:
            start, extent = struct.unpack_from('<II', payload, 8)
            need(start + extent <= len(image), 'Native signature exceeds file')
            signatures.append({'offset': start, 'size': extent})
        elif command == 0x19:
            segment = payload[8:24].split(b'\0')[0].decode('ascii')
            nsects = struct.unpack_from('<I', payload, 64)[0]
            need(length == 72 + 80 * nsects, 'Native section table differs')
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', payload, 24)
            segments.append((vmaddr, vmsize, fileoff, filesize))
            for index in range(nsects):
                at = 72 + 80 * index
                section = payload[at:at + 16].split(b'\0')[0].decode('ascii')
                address, extent, offset = struct.unpack_from('<QQI', payload, at + 32)
                flags = struct.unpack_from('<I', payload, at + 64)[0]
                key = segment + '/' + section
                need(key not in sections, 'Duplicate native section')
                zerofill = flags & 0xff in (1, 0xc, 0x12)
                need(zerofill or offset + extent <= len(image), 'Native section exceeds file')
                sections[key] = {'address': address, 'size': extent, 'flags': flags,
                                 'sha256': None if zerofill else digest(image[offset:offset + extent])}
        elif command in (0xc, 0x80000018, 0x8000001f, 0x80000023):
            at = struct.unpack_from('<I', payload, 8)[0]
            dependencies.append(payload[at:payload.index(0, at)].decode('ascii'))
        elif command == 2:
            symbols = struct.unpack_from('<IIII', payload, 8)
        cursor += length
    need(cursor == limit and len(versions) == 1 and versions[0]['platform'] == 7
         and versions[0]['minimum'] <= 0x000f0300, 'Native platform7 simulator/minimum15.3 required')
    rtr = None
    if symbols:
        start, count, strings, size = symbols
        need(start + count * 16 <= len(image) and strings + size <= len(image), 'Native symbols exceed file')
        for i in range(count):
            name, flags, section, _, value = struct.unpack_from('<IBBHQ', image, start + 16 * i)
            need(name < size, 'Native symbol string exceeds table')
            end = image.index(0, strings + name, strings + size)
            if image[strings + name:end] == b'_RTR_HEADER':
                need(flags & 0xf == 0xf and section > 0 and rtr is None, 'Composite export differs')
                position = next(offset + value - address for address, _, offset, extent in segments
                                if address <= value and value + 16 <= address + extent)
                signature, major, minor, flags, section_count = struct.unpack_from('<IHHII', image, position)
                need(signature == 0x00525452, 'Native composite RTR signature differs')
                rtr = {'major': major, 'minor': minor, 'flags': flags, 'sectionCount': section_count}
    return {'sha256': sha(path), 'kind': kind, 'buildVersion': versions[0], 'uuids': uuids,
            'sections': sections, 'codeSignatures': signatures, 'dependencies': dependencies, 'rtrHeader': rtr}


def source_native_binding(source, signed):
    for key in ('kind', 'buildVersion', 'uuids', 'sections', 'dependencies', 'rtrHeader'):
        need(source[key] == signed[key], 'Signed/source native executable-section binding differs: ' + key)
    need(len(signed['codeSignatures']) == 1, 'Actual simulator native image must retain one ad-hoc signature')


def author_il_only(path):
    image = Path(path).read_bytes()
    pe = struct.unpack_from('<I', image, 60)[0]
    optional = pe + 24
    directory = optional + (112 if struct.unpack_from('<H', image, optional)[0] == 0x20b else 96)
    cli = struct.unpack_from('<I', image, directory + 14 * 8)[0]
    sections = optional + struct.unpack_from('<H', image, pe + 20)[0]
    for index in range(struct.unpack_from('<H', image, pe + 6)[0]):
        size, address, raw_size, offset = struct.unpack_from('<IIII', image, sections + 40 * index + 8)
        if address <= cli and cli + 72 <= address + raw_size:
            need(struct.unpack_from('<I', image, offset + cli - address + 16)[0] & 1, 'Original author PE must have ILONLY flag')
            return
    raise ValueError('Original author PE CLI header missing')


def author_binding(authors, author_review, expected_review_sha, installed_utc, managed):
    need(sha(author_review) == expected_review_sha, 'New after-simulator-install author review digest differs')
    binding = read(author_review)
    request, result = read(authors / 'request.json'), read(authors / 'results.json')
    previous_dir = Path('D:/RuneCLR-Android/device-build/post-device-app-author-20261015-attempt1')
    previous_request = read(previous_dir / 'request.json')
    previous_review = Path('D:/RuneCLR-Android/device-build/post-device-app-author-review-20261015-attempt1/review.json')
    need(sha(previous_review) == AUTHOR_REVIEW_SHA, 'Preserved original post-device-build author review changed')
    previous_binding = read(previous_review)
    need(sha(previous_dir / 'request.json') == previous_binding['authorRequestSha256']
         and sha(previous_dir / 'results.json') == previous_binding['authorResultsSha256'],
         'Preserved original source/compiler/device-host request changed')
    for name, (expected, _) in PREVIOUS_AUTHOR.items():
        need(sha(previous_dir / 'plugin' / name) == expected, 'Preserved original author pair changed')
    need(binding['passed'] and binding['deviceHostBytesBound'] and binding['postDeviceHostBuildCompiled']
         and not binding['physicalDeviceExecuted'] and not binding['interpreterEntryProven']
         and binding['authorRequestSha256'] == sha(authors / 'request.json')
         and binding['authorResultsSha256'] == sha(authors / 'results.json'), 'Actual fresh compiler receipt bindings differ')
    need(instant(binding['buildEndedUtc']) < instant(request['boundUtc'])
         and instant(request['boundUtc']) >= instant(installed_utc)
         and set(result['authorHashes']) == set(PREVIOUS_AUTHOR)
         and request['nonce'] != previous_request['nonce']
         and result['nonce'] == request['nonce'] and re.fullmatch('[0-9a-f]{32}', request['nonce']),
         'Fresh author installation/build ordering or nonce differs')
    for key in ('hostBundleHashes', 'inputManifestSha256', 'sourceHashes', 'sdkHostSha256',
                'compilerSha256', 'referenceHashes', 'app', 'phase'):
        need(request[key] == previous_request[key], 'New compile changed accepted device host/source/compiler/refs: ' + key)
    need(inventory(Path(request['app'])) == request['hostBundleHashes'], 'Accepted unsigned DEVICE bundle changed')
    refs_root = ROOT / 'artifacts/toolchains/dotnet-11-rc1/packs/Microsoft.NETCore.App.Ref/11.0.0-rc.1.26425.128/ref/net11.0'
    references = sorted(refs_root.glob('*.dll'))
    need({p.name: sha(p) for p in references} == request['referenceHashes'], 'New compiler actual fixed references changed')
    contract = ROOT / 'artifacts/host-budget/mobile-inputs-20261013-attempt1/trusted/RuneCLR.Abstractions.dll'
    need(sha(contract) == read(ROOT / 'artifacts/host-budget/mobile-inputs-20261013-attempt1/input-manifest.json')['files']['trusted/RuneCLR.Abstractions.dll'],
         'New compiler actual shared contract changed')
    globals_path, attribute = authors / 'source/GlobalUsings.cs', authors / 'source/AfterHostBuild.cs'
    need(globals_path.read_text() == 'global using System;' + chr(10)
         and attribute.read_text() == '[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]' + chr(10) +
         '[assembly: System.Reflection.AssemblyMetadata("RuneCLR.DeviceAuthor.AfterHost", "' + request['nonce'] + '")]' + chr(10),
         'Fresh nonce source or implicit using differs from fixed compiler input')
    last = instant(request['boundUtc'])
    identities = {}
    for role, name in zip(('Private', 'Payload'), PREVIOUS_AUTHOR):
        process = read(authors / (role + '.process.json'))
        need(process['exitCode'] == 0 and last <= instant(process['startedUtc']) <= instant(process['endedUtc'])
             and instant(process['startedUtc']) >= instant(installed_utc), 'Real author compiler predates simulator installation')
        last = instant(process['endedUtc'])
        need(process in binding['compilerProcesses'], 'New author compiler process not in independent binding review')
        for suffix in ('stdout', 'stderr'):
            need(sha(authors / (role + '.' + suffix)) == process[suffix + 'Sha256'], 'Actual compiler raw stream changed')
        response = authors / (role + '.rsp')
        need(sha(response) == process['responseSha256'], 'Actual compiler response changed')
        old_process = read(previous_dir / (role + '.process.json'))
        need(process['argv'][:3] == old_process['argv'][:3]
             and process['argv'][3:] == ['@' + str(response.resolve())]
             and sha(Path(process['argv'][0])) == request['sdkHostSha256']
             and sha(Path(process['argv'][1])) == request['compilerSha256'], 'Actual explicit compiler executable changed')
        need(sha(authors / 'source' / (role + '.cs')) == request['sourceHashes'][role], 'New author fixed source changed')
        selected = references + [contract] + ([authors / 'plugin/HostBudgetProbe.Private.dll'] if role == 'Payload' else [])
        expected_response = ['-target:library', '-nostdlib+', '-deterministic+', '-optimize+', '-debug-',
                             '-nullable:enable', '-langversion:preview', '-warnaserror+',
                             '-out:"' + str((authors / 'plugin' / name).resolve()) + '"']
        expected_response += ['-reference:"' + str(p.resolve()) + '"' for p in selected]
        expected_response += ['"' + str(p.resolve()) + '"' for p in
                              (authors / 'source' / (role + '.cs'), globals_path, attribute)]
        need(response.read_text().splitlines() == expected_response, 'Actual author compilation arguments differ from independent fixed derivation')
        image = managed.managed(authors / 'plugin' / name)
        author_il_only(authors / 'plugin' / name)
        expected, mvid = result['authorHashes'][name], binding['authors'][name]['moduleVersionId']
        need(image['sha256'] == expected and image['mvid'] == mvid
             and image['managedNativeRva'] == image['managedNativeSize'] == 0
             and binding['authors'][name]['sha256'] == expected
             and image['sha256'] != PREVIOUS_AUTHOR[name][0] and image['mvid'] != PREVIOUS_AUTHOR[name][1]
             and request['nonce'].encode('ascii') in (authors / 'plugin' / name).read_bytes(),
             'Actual NEW author PE hash/MVID/nonce differs or replays preserved old pair: ' + name)
        identities[name] = {'sha256': expected, 'mvid': mvid, 'methodCount': len(image['methods'])}
    return {'binding': binding, 'identities': identities, 'compiledAfterSimulatorInstall': True,
            'lastCompilerEndedUtc': binding['compilerProcesses'][-1]['endedUtc']}


def stage_binding(root, label, expected_argv):
    request = read(root / (label + '.request.json'))
    process = read(root / (label + '.process.json'))
    result = read(root / (label + '.result.json'))
    need(request['argv'] == process['argv'] == expected_argv and
         result['pid'] == process['pid'] > 0 and result['exitCode'] == 0 and not result['timedOut'] and
         request['startedUtc'] == result['startedUtc'] and
         instant(request['startedUtc']) <= instant(process['startedUtc']) <= instant(result['endedUtc']),
         'Actual stage process/arguments/completion/ordering differs: ' + label)
    for suffix in ('stdout', 'stderr'):
        need(sha(root / (label + '.' + suffix)) == result[suffix + 'Sha256'], 'Actual stage raw stream differs: ' + label)
    return result


def build_identity(request, build):
    need(request['schema'] == 'runeclr.ios-fresh-author.simulator-build.v1' and
         request['driverSha256'] == BUILDER_SHA and request['sourceCommit'] == build['commit'] == COMMIT and
         request['sourceTree'] == build['tree'] == TREE and build['base'] == BASE and
         request['buildReceiptSha256'] == BUILD_SHA and request['wrapperHelperSha256'] == WRAPPER_HELPER_SHA and
         request['configuration'] == PROFILE and not request['physicalDeviceExecuted'] and
         not request['runtimeRebuilt'] and not request['trustedHostRecompiled'] and
         build['configuration'] == 'Release' and build['target'] == 'iossimulator.arm64' and
         build['success'] and build['buildExit'] == 0 and build['assessment']['staticInterpreter'] and
         not build['assessment']['dynamicJitEnabled'] and
         all(build[key] == value for key, value in PRODUCTS.items()), 'Independent fixed simulator build/profile identity differs')


def ordering(install, compilation, transfer, launch):
    need(instant(install['installEndedUtc']) <= instant(install['readbackUtc']) <=
         instant(compilation['authorBoundUtc']) <= instant(compilation['compilerProcesses'][0]['startedUtc']) <=
         instant(compilation['compilerProcesses'][0]['endedUtc']) <= instant(compilation['compilerProcesses'][1]['startedUtc']) <=
         instant(compilation['compilerProcesses'][1]['endedUtc']) <= instant(transfer['startedUtc']) <=
         instant(transfer['endedUtc']) <= instant(launch['startedUtc']) <= instant(launch['endedUtc']),
         'Actual install/readback/new-compile/delivery/launch ordering differs')


def transported_author(transfer, before, after, identities):
    expected = {name: row['sha256'] for name, row in identities.items()}
    need(transfer['authorHashes'] == before['author'] == after['author'] == expected and
         before['bundle'] == after['bundle'], 'Actual NEW compiler-output hashes differ from delivered/readback author identities')


def launch_identity(request, owned, state, builder_sha=BUILDER_SHA):
    need(request['configuration'] == PROFILE and request['simulator'] == owned['id'] and
         request['bundleId'] == owned['bundleId'] == state['bundleId'] and
         request['environment'] == {'SIMCTL_CHILD_RUNECLR_BUDGET_NONCE': request['nonce']} and
         request['driverSha256'] == CONTINUATION_SHA and request['buildDriverSha256'] == builder_sha and
         re.fullmatch('[0-9a-f]{32}', request['nonce']) and request['debugger'] is False and
         request['physicalDeviceExecuted'] is False and request['launchCount'] == 1,
         'Actual launch nonce/owned-simulator/profile/environment/scope differs')


def markers(text, nonce, pid, bundle_id):
    prefix = r'(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3,6} Session\[' + str(pid) + r':\d+\] )?'
    for marker in (
        'FRESH_AUTHOR_SIM_NATIVE pid=' + str(pid) + ' nonce=' + nonce + ' PhaseAcquireLoad=1 DerivedLedger=1 BatchInterval=0 InterpMode=0 InterpretCollectible=0 ReadyToRun=1',
        'FRESH_AUTHOR_SIM_INITIALIZE pid=' + str(pid) + ' nonce=' + nonce + ' hr=0',
        'FRESH_AUTHOR_SIM_CREATE_DELEGATE pid=' + str(pid) + ' nonce=' + nonce + ' hr=0',
        'FRESH_AUTHOR_SIM_INVOKE pid=' + str(pid) + ' nonce=' + nonce + ' managedExit=0',
        'FRESH_AUTHOR_SIM_SHUTDOWN pid=' + str(pid) + ' nonce=' + nonce + ' attempted=false reason=template-exit-path',
        'FRESH_AUTHOR_SIM_EXIT pid=' + str(pid) + ' nonce=' + nonce + ' managedExit=0 actualExit=0'):
        need(len(re.findall('^' + prefix + re.escape(marker) + '$', text, re.M)) == 1, 'Actual native PID/nonce/configuration/exit marker differs')
    marker = 'MOBILE_HOST_BUDGET_COMPLETE nonce=' + nonce + ' scenario=all pid=' + str(pid) + ' cases=15 contexts=73 passed=true'
    need(len(re.findall('^' + prefix + re.escape(marker) + '$', text, re.M)) == 1, 'Actual managed completion marker differs')
    need(text.splitlines().count(bundle_id + ': ' + str(pid)) == 1, 'Actual simctl launched bundle/application PID marker differs')


def application_binding(root, managed):
    request, build, state = read(root / 'request.json'), read(root / 'matching-build.json'), read(root / 'state.json')
    build_identity(request, build)
    need(sha(root / 'matching-build.json') == BUILD_SHA and sha(root / 'driver.py') == BUILDER_SHA
         and sha(root / 'continuation.py') == CONTINUATION_SHA and sha(root / 'wrapper-helper.py') == WRAPPER_HELPER_SHA
         and sha(root / 'framework-reuse.json') == FRAMEWORK_SHA, 'Frozen application/build/framework/continuation receipt bytes differ')
    need(sha(root / 'critical-native/crossgen2') == PRODUCTS['crossgen2Sha256'], 'Actual frozen crossgen2 executable differs from fixed simulator build')
    framework = read(root / 'framework-reuse.json')
    expected_inputs = dict(framework['inputHashes'])
    need(len(expected_inputs) == 180 and 'System.Private.CoreLib.dll' not in expected_inputs, 'Exactly180 fixed framework-only inputs required')
    expected_inputs.update(managed.TRUSTED)
    expected_inputs.update({'SessionBridge.dll': BRIDGE_SHA, 'System.Private.CoreLib.dll': PRODUCTS['corelibSha256']})
    need(inventory(root / 'input') == request['rawInputHashes'] == state['rawInputHashes'] == expected_inputs,
         'Raw framework/trusted/CoreLib input hashes differ from independent fixed identities')
    proof = read(root / 'source-proof.json')
    need(sha(root / 'source-proof.json') == build['sourceProofSha256'] == request['sourceProofSha256']
         and len(proof['sourceHashes']) == 38, 'Fixed simulator38-source proof binding differs')
    for name, expected in proof['sourceHashes'].items():
        need(sha(root / 'source' / name) == expected, 'Archived actual runtime source differs: ' + name)
    helper_module = helper('frozen_wrapper', 'ios-device-application-build.py', WRAPPER_HELPER_SHA)
    for name, expected in helper_module.WRAPPERS.items():
        need(sha(root / 'wrapper-inputs' / name) == expected, 'Actual official wrapper template differs')
    need((root / 'main.m').read_text() == helper_module.MAIN and
         (root / 'runtime.m').read_text() == helper_module.wrapper(root / 'wrapper-inputs/src/tasks/AppleAppBuilder/Templates/runtime-coreclr.m').replace(
             'ios-arm64', 'iossimulator-arm64').replace('DEVICE_APP_', 'FRESH_AUTHOR_SIM_'),
         'Actual wrapper source differs from independent fixed source derivation')
    for name in ('util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h'):
        relative = next(r for r in helper_module.WRAPPERS if PurePosixPath(r).name == name)
        need(sha(root / name) == helper_module.WRAPPERS[relative], 'Actual native wrapper include changed')
    app = root / 'app/Session.app'
    current = inventory(app)
    need(current == state['bundleHashes'] and state['configuration'] == PROFILE and
         state['sourceCommit'] == COMMIT and state['sourceTree'] == TREE and
         not state['physicalDeviceExecuted'] and not state['nativeEntryProof'], 'Actual signed simulator bundle/state differs')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    need(info['CFBundleExecutable'] == 'Session' and info['CFBundleIdentifier'] == state['bundleId']
         and info['CFBundleSupportedPlatforms'] == ['iPhoneSimulator'] and info['MinimumOSVersion'] == '15.3'
         and state['bundleId'].startswith('org.runeclr.freshauthor.'), 'Actual simulator plist platform/entry/minimum differs')
    need({n for n in current if n.endswith('.dll')} == set(expected_inputs)
         and not any(PurePosixPath(n).name in PREVIOUS_AUTHOR for n in current), 'Author isolation or exact trusted component inventory differs')
    native_rows, components = {}, {}
    for name in ['Session'] + sorted(n for n in current if n.endswith('.dylib')):
        actual, source = native_image(app / name), native_image(root / 'unsigned-native' / name)
        need(actual['kind'] == (2 if name == 'Session' else 6), 'Actual native role differs')
        source_native_binding(source, actual)
        need(state['nativeOutputs'][name]['sha256'] == actual['sha256'], 'Recorded signed native hash differs')
        if name == 'libcoreclr.dylib':
            need(source['sha256'] == PRODUCTS['nativeSha256'], 'Actual unsigned native runtime differs from matching3126bbc build')
        elif name not in ('Session', 'framework.dylib'):
            need(source['sha256'] == request['baselineBeforeHashes'][name], 'Native support source differs from retained baseline')
        if name == 'framework.dylib':
            need(actual['rtrHeader'] is not None and actual['rtrHeader']['major'] == 31, 'Actual signed composite exported R2R31 header missing')
        for dependency in actual['dependencies']:
            need(dependency.startswith(('/usr/lib/', '/System/Library/')) or
                 dependency.startswith(('@rpath/', '@loader_path/', '@executable_path/')) and PurePosixPath(dependency).name in current,
                 'Native dependency is not resolved to system or current application')
        native_rows[name] = actual
    need(len(native_rows) == 11 and len(state['nativeOutputs']) == 11, 'Exactly11 simulator native files required')
    remote = PurePosixPath(state['app']).parent.parent
    expected_rsp = ['--targetos:iossimulator', '--targetarch:arm64', '--obj-format:macho', '--composite',
                    '--inputbubble', '--parallelism:2', '--resilient', '--optimize',
                    '--out:' + str(remote / 'app/Session.app/framework.dylib')]
    expected_rsp += [str(remote / 'input' / name) for name in sorted(expected_inputs)]
    need((root / 'crossgen.rsp').read_text().splitlines() == expected_rsp, 'Actual crossgen args differ from independent fixed derivation')
    stage_binding(root, 'crossgen', [build['crossgen2'], '@' + str(remote / 'crossgen.rsp')])
    stage_binding(root, 'composite-link', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target',
        'arm64-apple-ios15.3-simulator', '-dynamiclib', str(remote / 'framework.o'),
        '-Wl,-install_name,@rpath/framework.dylib', '-o', str(remote / 'app/Session.app/framework.dylib')])
    stage_binding(root, 'wrapper', ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target',
        'arm64-apple-ios15.3-simulator', '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(remote),
        str(remote / 'main.m'), str(remote / 'runtime.m'), str(remote / 'util.m'), '-L' + str(remote / 'app/Session.app'),
        '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path',
        '-o', str(remote / 'app/Session.app/Session')])
    for name in sorted(n for n in current if n.endswith('.dylib')):
        stage_binding(root, 'sign-' + PurePosixPath(name).stem, ['codesign', '--force', '--sign', '-', str(remote / 'app/Session.app' / name)])
    stage_binding(root, 'sign-app', ['codesign', '--force', '--sign', '-', str(remote / 'app/Session.app')])
    stage_binding(root, 'sign-verify', ['codesign', '--verify', '--strict', str(remote / 'app/Session.app')])
    for name in sorted(expected_inputs):
        raw, component = managed.managed(root / 'input' / name), managed.managed(app / name)
        need(raw['managedNativeRva'] == 0 and component['managedNativeRva'] > 0
             and component['readyToRun']['flags'] & 0x120 == 0x120
             and component['readyToRun']['ownerComposite'] == 'framework.dylib', 'Actual R2R component role/owner differs')
        for key in METADATA_KEYS:
            need(raw[key] == component[key], 'Actual whole metadata/IL/EH/initialized-field comparison differs: ' + name + '/' + key)
        components[name] = {'rawSha256': raw['sha256'], 'componentSha256': component['sha256'],
                            'mvid': raw['mvid'], 'methodCount': len(raw['methods']),
                            'initializedFields': len(raw['initializedFields'])}
    need(set(state['components']) == set(components), 'Recorded component inventory differs')
    built = read(root / 'build-results.json')
    need(built['passed'] and built['applicationBuilt'] and built['managedComponents'] == 186
         and not built['authorBundled'] and not built['physicalDeviceExecuted'] and not built['nativeEntryProof'],
         'Actual simulator application completion/scope differs')
    return {'native': native_rows, 'components': components, 'appFiles': len(current), 'profile': PROFILE,
            'runtimeSourceFiles': 38, 'officialWrapperInputs': len(helper_module.WRAPPERS),
            'crossgenOriginalIdentityValidatedByFrozenBuilder': True, 'independentCrossgenImageRehashed': True,
            'builderSha256': BUILDER_SHA, 'continuationSha256': CONTINUATION_SHA}


def scene_contract(main_bytes, info):
    need(digest(main_bytes) == SCENE_MAIN_SHA, 'Actual scene main differs from fixed accepted lifecycle template')
    need(info.get('UIApplicationSceneManifest') == {'UIApplicationSupportsMultipleScenes': False},
         'Actual new UIKit scene lifecycle manifest is absent or differs')


def scene_bundle_diff(previous, current):
    need(set(previous) == set(current), 'Scene-only repair added/removed bundle files')
    changed = [name for name in previous if previous[name] != current[name]]
    need(all(name in ('Session', 'Info.plist') or name.startswith('_CodeSignature/') for name in changed),
         'Scene-only repair changed trusted/native/composite bundle bytes')
    need('Session' in changed and 'Info.plist' in changed, 'Scene-only repair must replace scene entry and plist')
    return changed


def scene_scope_identity(request, state):
    need(request['schema'] == 'runeclr.ios-fresh-author.simulator-scene-repair.v1'
         and request['driverSha256'] == REPAIR_SHA and request['continuationSha256'] == CONTINUATION_SHA
         and request['previousBuildDriverSha256'] == BUILDER_SHA
         and request['sourceCommit'] == COMMIT and request['sourceTree'] == TREE
         and request['configuration'] == state['configuration'] == PROFILE
         and state['wrapperOnlyRepair'] and not state['r2rRebuilt']
         and state['sceneMainSha256'] == request['sceneMainSourceSha256'] == SCENE_MAIN_SHA
         and not state['physicalDeviceExecuted'] and not state['nativeEntryProof']
         and not any(request[key] for key in ('runtimeRebuilt', 'trustedHostRecompiled', 'r2rRebuilt',
                                             'deviceAppRepaired', 'physicalDeviceExecuted')),
         'Actual fixed scene-only source/profile/repair scope differs')


def scene_application_binding(root, previous, base_review):
    request, state = read(root / 'request.json'), read(root / 'state.json')
    previous_request, previous_state = read(previous / 'request.json'), read(previous / 'state.json')
    scene_scope_identity(request, state)
    need(request['schema'] == 'runeclr.ios-fresh-author.simulator-scene-repair.v1' and
         request['driverSha256'] == REPAIR_SHA and sha(root / 'driver.py') == REPAIR_SHA and
         sha(root / 'continuation.py') == CONTINUATION_SHA == request['continuationSha256'] and
         request['previousBuildDriverSha256'] == BUILDER_SHA and
         request['previousBuildRequestSha256'] == sha(previous / 'request.json') == sha(root / 'previous-build-request.json') and
         request['previousStateSha256'] == sha(previous / 'state.json') == sha(root / 'previous-state.json') and
         sha(previous / 'build-results.json') == sha(root / 'previous-build-results.json') and
         request['sourceCommit'] == COMMIT and request['sourceTree'] == TREE and
         request['configuration'] == state['configuration'] == PROFILE and
         not any(request[key] for key in ('runtimeRebuilt', 'trustedHostRecompiled', 'r2rRebuilt', 'deviceAppRepaired', 'physicalDeviceExecuted')),
         'Actual separately frozen scene-repair origin/source/profile/scope differs')
    for folder in ('input', 'source', 'wrapper-inputs', 'critical-native'):
        need(inventory(root / folder) == inventory(previous / folder), 'Scene repair changed original raw/source/native compiler snapshot: ' + folder)
    need(sha(root / 'matching-build.json') == BUILD_SHA and
         sha(root / 'framework-reuse.json') == FRAMEWORK_SHA and
         request['rawInputHashes'] == state['rawInputHashes'] == previous_state['rawInputHashes'] and
         state['components'] == previous_state['components'], 'Scene repair changed186 component/raw/build identity')
    for name in ('runtime.m', 'util.m', 'util.h', 'runtime.h', 'coreclrhost.h', 'host_runtime_contract.h', 'wrapper-helper.py'):
        need(sha(root / name) == sha(previous / name), 'Scene repair changed immutable native wrapper source: ' + name)
    app = root / 'app/Session.app'
    current, old = inventory(app), inventory(previous / 'app/Session.app')
    changed = scene_bundle_diff(old, current)
    need(current == state['bundleHashes'] and state['wrapperOnlyRepair'] and not state['r2rRebuilt']
         and state['previousStateSha256'] == sha(previous / 'state.json') and
         state['sceneMainSha256'] == request['sceneMainSourceSha256'] == SCENE_MAIN_SHA
         and not state['physicalDeviceExecuted'] and not state['nativeEntryProof'], 'Actual scene state/bundle differs')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    scene_contract((root / 'main.m').read_bytes(), info)
    need(sha(root / 'scene-template-main.m') == SCENE_MAIN_SHA and
         info['CFBundleIdentifier'] == state['bundleId'] and state['bundleId'].startswith('org.runeclr.freshauthorscene.') and
         info['CFBundleExecutable'] == 'Session' and info['CFBundleSupportedPlatforms'] == ['iPhoneSimulator'] and
         info['MinimumOSVersion'] == '15.3', 'Scene plist/template actual identity differs')
    remote = PurePosixPath(state['app']).parent.parent
    argv = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', 'arm64-apple-ios15.3-simulator',
            '-fobjc-arc', '-DINVARIANT_GLOBALIZATION=1', '-I' + str(remote), str(remote / 'main.m'),
            str(remote / 'runtime.m'), str(remote / 'util.m'), '-L' + str(remote / 'app/Session.app'),
            '-lcoreclr', '-framework', 'UIKit', '-framework', 'Foundation', '-Wl,-rpath,@executable_path',
            '-o', str(remote / 'app/Session.app/Session')]
    need(request['wrapperCommand'] == argv, 'Scene wrapper compiler argv differs from independent derivation')
    stage_binding(root, 'wrapper', argv)
    stage_binding(root, 'sign-app', ['codesign', '--force', '--sign', '-', str(remote / 'app/Session.app')])
    stage_binding(root, 'sign-verify', ['codesign', '--verify', '--strict', str(remote / 'app/Session.app')])
    source, signed = native_image(root / 'unsigned-native/Session'), native_image(app / 'Session')
    source_native_binding(source, signed)
    native_rows = dict(base_review['native']); native_rows['Session'] = signed
    for name in native_rows:
        need(state['nativeOutputs'][name]['sha256'] == sha(app / name), 'Actual repaired signed native state differs')
        if name != 'Session':
            need(sha(root / 'unsigned-native' / name) == sha(previous / 'unsigned-native' / name),
                 'Scene repair changed immutable unsigned native/composite snapshot')
    result = read(root / 'build-results.json')
    need(result['passed'] and result['applicationBuilt'] and result['managedComponents'] == 186
         and result['preservedNonWrapperFiles'] == len(old) - len([n for n in old if n in ('Session', 'Info.plist') or n.startswith('_CodeSignature/')])
         and not any(result[key] for key in ('runtimeRebuilt', 'trustedHostRecompiled', 'r2rRebuilt', 'physicalDeviceExecuted', 'deviceAppRepaired', 'authorBundled')),
         'Actual scene-only application completion/scope differs')
    return dict(base_review, native=native_rows, appFiles=len(current), sceneOnlyRepair=True,
                sceneChangedBundleFiles=changed, sceneMainSha256=SCENE_MAIN_SHA, builderSha256=REPAIR_SHA,
                originalBuilderSha256=BUILDER_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('authors', 'author-review'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--author-review-sha256')
    parser.add_argument('--phase', choices=('application', 'run'), default='run')
    parser.add_argument('--previous-experiment', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh independent-review output required')
    args.output.mkdir(parents=True)
    result = {'schema': 'runeclr.ios-fresh-author.simulator-independent-review.v1', 'passed': False,
              'phase': args.phase, 'lifecycleRowsVerified': False, 'postSimulatorInstallCompiled': False,
              'reviewerSha256': sha(__file__), 'physicalDeviceExecuted': False, 'physicalDeviceInstalled': False,
              'nativeEntryProof': False, 'timingPerformed': False}
    try:
        managed = helper('independent_managed', 'ios-device-application-review.py', MANAGED_REVIEW_SHA)
        rows = helper('fixed_rows', 'mobile-host-budget-audit.py', ROWS_SHA)
        active_builder = BUILDER_SHA
        if args.previous_experiment is not None:
            base_review = application_binding(args.previous_experiment, managed)
            app_review = scene_application_binding(args.experiment, args.previous_experiment, base_review)
            active_builder = REPAIR_SHA
        else:
            app_review = application_binding(args.experiment, managed)
        if args.phase == 'application':
            result.update(passed=True, platform='iossimulator.arm64', applicationReview=app_review,
                          scope='Matching simulator source/images and actual186-component trusted application composition only; no launch/lifecycle/author-execution claim.')
            return save_result(args.output, result)
        need(args.authors is not None and args.author_review is not None and args.author_review_sha256 is not None,
             'Actual NEW authors and fixed independent binding review required for run phase')
        root, run = args.experiment, args.experiment / 'run-all'
        state, owned = read(root / 'state.json'), read(root / 'owned-simulator.json')
        install = read(root / 'installation/results.json')
        install_process = stage_binding(root / 'installation', 'install',
            ['xcrun', 'simctl', 'install', owned['id'], state['app']])
        need(install['schema'] == 'runeclr.ios-fresh-author.simulator-install.v1' and install['passed']
             and install['driverSha256'] == CONTINUATION_SHA and install['buildDriverSha256'] == active_builder
             and install['simulator'] == owned['id'] and install['bundleId'] == state['bundleId']
             and install['installEndedUtc'] == install_process['endedUtc']
             and install['installResultSha256'] == sha(root / 'installation/install.result.json')
             and install['installRequestSha256'] == sha(root / 'installation/install.request.json')
             and install['stateSha256'] == sha(root / 'state.json')
             and not install['physicalDeviceInstalled'], 'Actual owned simulator installation binding differs')
        absent = read(root / 'installation/installed-before-copy.json')
        need(sha(root / 'installation/installed-before-copy.json') == install['readbackSha256']
             and absent['bundle'] == state['bundleHashes'] and absent['authorFiles'] == {}
             and absent['authorDirectoryExists'] is False and absent['appPath'] == install['installedApp']
             and absent['dataPath'] == install['dataContainer']
             and instant(install['installEndedUtc']) <= instant(absent['observedUtc']) <= instant(install['readbackUtc'])
             and '/Devices/' + owned['id'] + '/' in absent['dataPath']
             and '/Devices/' + owned['id'] + '/' in absent['appPath'], 'Installed-before-copy app/author absence/readback differs')
        author_review = author_binding(args.authors, args.author_review, args.author_review_sha256, install['readbackUtc'], managed)
        expected_author_snapshot = inventory(args.authors)
        expected_author_snapshot['author-binding-review.json'] = args.author_review_sha256
        need(inventory(run / 'author-compilation') == expected_author_snapshot,
             'Copied actual compiler receipts/IL/source differ from original NEW compilation and exactly bound review')
        transfer = read(run / 'transfer.json')
        before, after = read(run / 'installed-before.json'), read(run / 'installed-after.json')
        transported_author(transfer, before, after, author_review['identities'])
        need(before['bundle'] == state['bundleHashes'] and transfer['compiledResultSha256'] == sha(args.authors / 'results.json')
             and transfer['installReceiptSha256'] == sha(root / 'installation/results.json')
             and transfer['destination'] == str(PurePosixPath(install['dataContainer']) / 'Documents/budget-plugin'),
             'Actual transfer source/result/installed destination differs')
        request = read(run / 'request.json')
        launch_identity(request, owned, state, active_builder)
        launch = stage_binding(run, 'launch', ['xcrun', 'simctl', 'launch', '--console', owned['id'], state['bundleId']])
        need(instant(transfer['endedUtc']) <= instant(request['startedUtc']) <= instant(launch['startedUtc']),
             'Actual transfer/run-request/launch ordering differs')
        ordering(install, author_review['binding'], transfer, launch)
        aggregate = read(run / 'adapter-evidence/result.json')
        pid, nonce = aggregate['processId'], request['nonce']
        aggregate, receipts, metrics, hashes = rows.adapter(run / 'adapter-evidence', nonce, pid)
        text = (run / 'launch.stdout').read_text() + (run / 'launch.stderr').read_text()
        markers(text, nonce, pid, state['bundleId'])
        actual = read(run / 'results.json')
        need(actual['passed'] and actual['platform'] == 'iossimulator.arm64' and actual['processId'] == pid
             and actual['driverSha256'] == CONTINUATION_SHA
             and actual['nonce'] == nonce and actual['cases'] == 15 and actual['contexts'] == 73
             and actual['installedUnchanged'] and actual['authorCompiledAfterInstallation']
             and actual['debugger'] is False and actual['launchCount'] == 1
             and not actual['nativeEntryProof'] and not actual['physicalDeviceExecuted'],
             'Actual completed simulator run owner/scope differs')
        deleted = stage_binding(root / 'cleanup', 'delete', ['xcrun', 'simctl', 'delete', owned['id']])
        cleanup, devices = read(root / 'cleanup/results.json'), read(root / 'cleanup/devices-after.json')
        need(cleanup['passed'] and cleanup['deleted'] and cleanup['simulator'] == owned['id']
             and not cleanup['physicalDeviceChanged'] and instant(launch['endedUtc']) <= instant(deleted['startedUtc'])
             and not any(item['udid'] == owned['id'] for group in devices['devices'].values() for item in group),
             'Actual owned-simulator deletion/final inventory differs')
        controls = rows.negative_controls(aggregate, receipts, nonce, pid) if args.selftest else []
        result.update(passed=True, platform='iossimulator.arm64', applicationReview=app_review,
                      lifecycleRowsVerified=True,
                      authorIdentities=author_review['identities'], processId=pid, nonce=nonce, cases=15, contexts=73,
                      lifecycleMetrics=metrics, lifecycleReceiptHashes=hashes, lifecycleControls=controls,
                      independentNewAuthorIdentityBound=True, installedAuthorAbsentBeforeCompile=True,
                      postSimulatorInstallCompiled=True, deliveryReadbackBound=True, installedInputsUnchanged=True,
                      ownedSimulatorDeleted=True, authorReviewSha256=args.author_review_sha256,
                      authorReviewPath=str(args.author_review.resolve()), originalAuthorDirectory=str(args.authors.resolve()),
                      activeBuildDriverSha256=active_builder, previousExperiment=str(args.previous_experiment) if args.previous_experiment else None,
                      actualRawReceiptHashes={name: sha(root / name) for name in
                          ('request.json', 'state.json', 'matching-build.json', 'framework-reuse.json', 'source-proof.json',
                           'installation/results.json', 'installation/installed-before-copy.json', 'run-all/transfer.json',
                           'run-all/request.json', 'run-all/launch.request.json', 'run-all/launch.process.json',
                           'run-all/launch.result.json', 'run-all/launch.stdout', 'run-all/launch.stderr',
                           'run-all/results.json', 'run-all/installed-before.json', 'run-all/installed-after.json',
                           'cleanup/results.json', 'cleanup/devices-after.json')},
                      scope='Actual simulator install followed by NEW fixed-source author compilation/delivery/readback and fixed15-case/73-context normal execution; no physical-device or native interpreter-method-entry claim.')
    except Exception as error:
        result['error'] = str(error)
    return save_result(args.output, result)


def save_result(output, result):
    (output / 'results.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({k: v for k, v in result.items() if k not in
        ('applicationReview', 'lifecycleMetrics', 'lifecycleReceiptHashes', 'actualRawReceiptHashes', 'lifecycleControls')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
