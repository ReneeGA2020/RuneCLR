#!/usr/bin/env python3
"""Prepare an unsigned device application plan locally; never build, sign or run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
TRUSTED = ('RuneCLR.Abstractions.dll', 'RuneCLR.Packages.dll', 'RuneCLR.Runtime.dll', 'MobileHostBudgetProbe.dll')
AUTHOR = ('HostBudgetProbe.Payload.dll', 'HostBudgetProbe.Private.dll')
CASES = ('Normal', 'EndlessTick', 'StartLoop', 'CatchResume', 'BroadCatchResume', 'SignalFilter',
         'FilterExhaustion', 'ConstructorLoop', 'StaticConstructorLoop', 'FiniteCleanup',
         'InfiniteCleanup', 'StopLoop', 'MaliciousMessage', 'ExplicitCanceled', 'Recovery')
PRODUCTS = {'libcoreclr.dylib': '34c27daf3d6ef73a1558c21733d9f101bea4dcc839b9380d182d68cea2e2b93b',
            'IL/System.Private.CoreLib.dll': '9ce8a9f4028c66521b6211f7ca58df060b980208d449dfddbec0c1fd4451c0b0',
            'arm64/crossgen2/crossgen2': 'a518c15912febb36f48bce3c13b5d1e6fd85f45780c7a9d00860c71cb2d6c337'}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def source_anchors(root):
    checks = {
        'src/tasks/AppleAppBuilder/Xcode.cs': (
            'if (devTeamProvisioning == "-")', 'CODE_SIGN_IDENTITY=\\"\\"',
            'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGNING_ALLOWED=NO',
            'case TargetNames.iOS:', 'sdk = "iphoneos";'),
        'src/mono/msbuild/apple/build/AppleBuild.targets': (
            "'$(TargetOS)' == 'ios'", "'$(DevTeamProvisioning)' == ''", "'-' to skip signing all together"),
        'src/mono/msbuild/apple/build/AppleBuild.InTree.targets': ('>-</DevTeamProvisioning>',),
        'docs/workflow/building/coreclr/ios.md': ('/p:TargetArchitecture=arm64 /p:UseMonoRuntime=false', 'iOS Device')}
    evidence = {}
    for relative, anchors in checks.items():
        path = root / relative
        text = path.read_text(encoding='utf-8-sig')
        rows = []
        for anchor in anchors:
            need(anchor in text, 'Missing official source anchor: ' + relative + ' ' + anchor)
            rows.append({'anchor': anchor, 'line': text[:text.index(anchor)].count('\n') + 1})
        evidence[relative] = {'sha256': sha(path),
            'lfSha256': hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
            'anchors': rows}
    return evidence


def device_platform(path):
    data = Path(path).read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c),
         'Device input must be thin ARM64 Mach-O')
    count, size = struct.unpack_from('<II', data, 16)
    cursor, limit, versions = 32, 32 + size, []
    need(limit <= len(data), 'Truncated Mach-O load-command table')
    for _ in range(count):
        need(cursor + 8 <= limit, 'Truncated Mach-O command header')
        command, length = struct.unpack_from('<II', data, cursor)
        need(length >= 8 and cursor + length <= limit, 'Invalid Mach-O command length')
        if command == 0x32:
            need(length >= 24, 'Truncated LC_BUILD_VERSION')
            platform, minimum, sdk, tools = struct.unpack_from('<IIII', data, cursor + 8)
            need(length == 24 + tools * 8, 'Invalid Mach-O tool table')
            versions.append({'platform': platform, 'minimum': minimum, 'sdk': sdk})
        cursor += length
    need(cursor == limit and len(versions) == 1, 'Expected one LC_BUILD_VERSION')
    need(versions[0]['platform'] == 2 and versions[0]['minimum'] == 983808,
         'iOS device platform2/minimum15.3 required; simulator platform7 rejected')
    return dict(versions[0], architecture='arm64', sha256=sha(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-source', type=Path, required=True)
    parser.add_argument('--native-build', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    need(not args.output.exists(), 'Fresh output required; preserve prior attempts')
    source_commit = subprocess.check_output(['git', '-C', str(args.runtime_source), 'rev-parse', 'HEAD'], text=True).strip()
    need(source_commit in (BASE, COMMIT), 'Unexpected source revision')
    need(not subprocess.check_output(['git', '-C', str(args.runtime_source), 'status', '--porcelain', '--untracked-files=no'], text=True).strip(), 'Tracked runtime source modifications')
    anchors = source_anchors(args.runtime_source)
    receipt = read(args.native_build / 'results.json')
    need(receipt['success'] and receipt['commit'] == COMMIT and receipt['tree'] == TREE
         and receipt['base'] == BASE and receipt['target'] == 'ios.arm64'
         and receipt['configuration'] == 'Release' and receipt['sourceTrackedClean'], 'Matching device-native receipt required')
    product = args.native_build / 'runtime/artifacts/bin/coreclr/ios.arm64.Release'
    for relative, expected in PRODUCTS.items():
        need(sha(product / relative) == expected, 'Device product changed: ' + relative)
    platform = device_platform(product / 'libcoreclr.dylib')
    harness = root / 'eng/mobile-host-budget-probe/Entry.cs'
    need(sha(harness) == 'b21874d855338441b128eeb9885d681a7f1b39d19f809622fc4b55b39785a1f7',
         'Frozen production harness source changed')
    text = harness.read_text()
    declaration = re.search(r'Cases\s*=\s*\[(.*?)\];', text, re.S)
    need(declaration and tuple(re.findall(r'"([^"]+)"', declaration.group(1))) == CASES, 'Production cases changed')
    need('name == "Normal" ? 20 : name == "Recovery" ? 40 : 1' in text, 'Production context counts changed')
    manifest_path = args.inputs / 'input-manifest.json'
    need(sha(manifest_path) == 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685', 'Frozen production manifest changed')
    manifest, trusted = read(manifest_path), {}
    for name in TRUSTED:
        expected = manifest['files']['trusted/' + name]
        need(sha(args.inputs / 'trusted' / name) == expected, 'Trusted input changed: ' + name)
        trusted[name] = expected
    for name in AUTHOR:
        need(not list((args.inputs / 'trusted').rglob(name)), 'Author IL in trusted directory')
    plan = {'target': 'ios.arm64.Release', 'sdk': 'iphoneos', 'minimumDeployment': '15.3',
        'bundleId': 'org.runeclr.deviceprobe', 'unsignedProperty': 'DevTeamProvisioning=-',
        'xcodeSigningArguments': ['CODE_SIGN_IDENTITY=""', 'CODE_SIGNING_REQUIRED=NO', 'CODE_SIGNING_ALLOWED=NO'],
        'officialSampleReference': ['./dotnet.sh', 'build', 'src/mono/sample/iOS/Program.csproj', '-c', 'Release',
            '/p:TargetOS=ios', '/p:TargetArchitecture=arm64', '/p:UseMonoRuntime=false', '/p:DevTeamProvisioning=-'],
        'appRequirements': {'freshEmptyBundle': True, 'reuseSimulatorNativeOrComposite': False,
            'rawFrameworkIL': 'new matching device framework input inventory', 'trustedInputHashes': trusted,
            'trustedBridge': 'SessionBridge.Main -> MobileHostBudgetProbe.Entry.Run',
            'authorAssembliesForbiddenInBundle': list(AUTHOR), 'appContainsCompiler': False,
            'compositeArguments': ['--targetos:ios', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble', '--resilient', '--optimize'],
            'wrapperClangTarget': 'arm64-apple-ios15.3',
            'nativeDependencies': 'matching device deps inventory, each linked Mach-O must have platform2',
            'InfoPlist': {'CFBundleSupportedPlatforms': ['iPhoneOS'], 'MinimumOSVersion': '15.3', 'UIDeviceFamily': [1, 2]},
            'finalChecks': ['actual executable/dylib platform2 and absent LC_CODE_SIGNATURE',
                'verify actual linker does not insert an ad-hoc signature',
                'final component hash/MVID/R2R identities', 'author IL absent', 'native dependencies resolved']},
        'productionAcceptance': {'cases': list(CASES), 'contexts': 73, 'sameProcessRecovery': True,
            'freshILTool': 'eng/prepare-ios-device-author.py',
            'timeline': ['host build completed < author compilation started', 'author compilation completed < delivery completed', 'installation completed < delivery started'],
            'evidence': ['nonce/source/IL identity', 'delivered and loaded author hashes', 'actual interpreter method entries', '15 cases/73 collectible contexts', 'same-process recovery'],
            'authorFinalizersProductionSupported': False},
        'pending': ['device framework complete and independently checked', 'matching-source Apple generator anchor confirmation',
            'unsigned app assembled and inspected', 'reachable device and suitable profile before installation',
            'real-device transport established before delivery', 'physical device execution']}
    result = {'schema': 'runeclr.ios-device.application-source-preflight.v1', 'passed': True,
        'createdUtc': datetime.now(timezone.utc).isoformat(), 'sourceAnchorCommit': source_commit,
        'sourceAnchorScope': 'matching patched source' if source_commit == COMMIT else 'upstream base only',
        'runtimeCommit': COMMIT, 'runtimeTree': TREE, 'sourceAnchors': anchors,
        'nativeBuildReceiptSha256': sha(args.native_build / 'results.json'), 'actualProductHashes': PRODUCTS,
        'actualDevicePlatform': platform, 'productionHarnessSha256': sha(harness),
        'inputManifestSha256': sha(manifest_path), 'trustedInputHashes': trusted, 'unsignedSourceRouteVerified': True,
        'matchingFrameworkReady': False, 'applicationBuilt': False, 'physicalDeviceExecuted': False,
        'nativeEntryProof': False, 'signingOrDeviceSettingsChanged': False, 'remoteOperations': False}
    args.output.mkdir(parents=True)
    write(args.output / 'plan.json', plan)
    result.update(planSha256=sha(args.output / 'plan.json'), driverSha256=sha(__file__))
    write(args.output / 'results.json', result)
    print(json.dumps({'passed': True, 'unsignedSourceRouteVerified': True, 'actualDevicePlatform': platform['platform'],
        'productionCases': len(CASES), 'productionContexts': 73, 'applicationBuilt': False,
        'physicalDeviceExecuted': False, 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
