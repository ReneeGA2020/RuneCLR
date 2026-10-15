#!/usr/bin/env python3
"""Build Android framework inputs after an accepted matching session-policy core build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback

BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
COMMIT = '1724cdec553a7aff7a373a271a4be612651c7625'
TREE = '71c1ab3ba9a4efd354d71611f081c0bcfd30cdf2'
SANITIZE = ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
            'LIBRARY_PATH', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET',
            'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + chr(10))


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def below(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def capture(command):
    return subprocess.check_output([str(arg) for arg in command], text=True).strip()


def source_identity(source, hashes):
    require(capture(['git', '-C', source, 'rev-parse', 'HEAD']) == COMMIT and
            capture(['git', '-C', source, 'rev-parse', 'HEAD^{tree}']) == TREE,
            'Source HEAD/tree differs from accepted combined source')
    require(not capture(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']),
            'Runtime tracked source is dirty')
    changed = capture(['git', '-C', source, 'diff', '--name-only', BASE, COMMIT]).splitlines()
    require(len(changed) == 27 and set(changed) == set(hashes), 'Expected exact source27')
    require(all(sha(source / name) == hashes[name] for name in changed), 'Source hash mismatch')


def inventory(paths):
    return [{'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size}
            for path in sorted({Path(p).resolve() for p in paths}) if path.is_file()]


def android_tools(directory):
    require(directory is not None, '--android-tools receipt is required before a library run')
    directory = directory.resolve()
    receipt_path = directory / 'results.json'
    tools = read(receipt_path)
    require(tools['schema'] == 'runeclr.android.framework-toolchain.v1' and tools['success'] and
            tools['host'] == 'darwin-arm64' and tools['jdkMajor'] == 17 and
            tools['globalEnvironmentChanged'] is False, 'Unsupported SDK/JDK receipt')
    require(sha(directory / 'request.json') == tools['requestSha256'], 'SDK/JDK request receipt changed')
    sdk, java_home = Path(tools['androidSdkRoot']).resolve(), Path(tools['javaHome']).resolve()
    require(below(sdk, directory) and below(java_home, directory) and sdk.is_dir() and java_home.is_dir(),
            'SDK/JDK must be the accepted private directories')
    files = tools['criticalFiles']
    require(files and len({row['path'] for row in files}) == len(files), 'Invalid tools critical inventory')
    for row in files:
        path = Path(row['path']).resolve()
        require(below(path, directory) and path.is_file() and sha(path) == row['sha256'] and
                path.stat().st_size == row['size'], 'SDK/JDK critical file changed: ' + str(path))
    recorded = {Path(row['path']).resolve() for row in files}
    for name in ('java', 'javac', 'jar'):
        path = Path(tools[name + 'Executable']).resolve()
        require(path == java_home / 'bin' / name and path in recorded and os.access(path, os.X_OK),
                'Unverified JDK executable: ' + name)
    api_dirs = [int(p.name[8:]) for p in (sdk / 'platforms').iterdir()
                if p.is_dir() and re.fullmatch(r'android-[0-9]+', p.name)]
    versions = [tuple(int(part) for part in p.name.split('.')) for p in (sdk / 'build-tools').iterdir()
                if p.is_dir() and re.fullmatch(r'[0-9]+(?:[.][0-9]+)+', p.name)]
    api, version = str(tools['platformApi']), tools['buildToolsVersion']
    require(api_dirs and max(api_dirs) == int(api) and versions and
            max(versions) == tuple(int(part) for part in version.split('.')),
            'AndroidSdkHelper would select a different SDK platform/build-tools version')
    build_tools = sdk / 'build-tools' / version
    d8 = Path(tools['d8Executable']).resolve()
    required = {sdk / 'platforms' / ('android-' + api) / 'android.jar',
                sdk / 'platforms' / ('android-' + api) / 'source.properties',
                build_tools / 'source.properties', build_tools / 'lib/d8.jar', build_tools / 'd8'}
    require(required <= recorded and d8 == build_tools / 'd8' and os.access(d8, os.X_OK),
            'Unverified Android SDK compile/dex inputs')
    require(tools['probes'] and all(p['exitCode'] == 0 for p in tools['probes']),
            'SDK/JDK bootstrap executable probes did not pass')
    for probe in tools['probes']:
        log = Path(probe['log'])
        log = (directory / log if not log.is_absolute() else log).resolve()
        require(below(log, directory) and sha(log) == probe['logSha256'], 'SDK/JDK probe log changed')
    return tools, receipt_path


def critical_inputs(source, build, completed, accepted):
    product = source / ('artifacts/bin/coreclr/android.x64.' + completed['configuration'])
    compiler = Path(completed['crossgen2'])
    paths = {name: Path(completed[name]) for name in
             ('native', 'corelib', 'crossgen2', 'interpreter', 'targetJit')}
    paths.update(jitinterface=compiler.parent / 'libjitinterface_arm64.dylib',
                 crossarchJit=compiler.parent / 'libclrjit_unix_x64_arm64.dylib')
    require(set(paths) == set(accepted['criticalHashes']), 'Assessment critical inventory differs')
    rows = []
    artifacts = read(build / 'artifacts.json')
    for name, path in paths.items():
        expected = accepted['criticalHashes'][name]
        require(below(path, product) and sha(path) == expected, 'Accepted product changed: ' + name)
        copies = [Path(row['path']) for row in artifacts if row['sha256'] == expected]
        require(copies, 'Missing original artifact record: ' + name)
        for item in inventory([path, *copies]):
            require(below(item['path'], product) and item['sha256'] == expected,
                    'Accepted component copy changed: ' + name)
            rows.append(dict(item, component=name))
    return rows


def check_critical(rows):
    after = []
    for row in rows:
        path = Path(row['path'])
        after.append(dict(row, exists=path.is_file(),
                          sha256=sha(path) if path.is_file() else None,
                          size=path.stat().st_size if path.is_file() else None))
    return after, all(a['sha256'] == b['sha256'] and a['size'] == b['size']
                      for a, b in zip(after, rows))


def msbuild_json(text):
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character != '{':
            continue
        try:
            result, _ = decoder.raw_decode(text[offset:])
        except ValueError:
            continue
        if isinstance(result, dict) and 'Items' in result and 'Properties' in result:
            return result
    raise RuntimeError('MSBuild did not return actual evaluated properties/items JSON')


def run_stage(out, source, env, name, command, collect=False):
    command = [str(arg) for arg in command]
    write(out / (name + '.request.json'), {'command': command, 'cwd': str(source), 'startedUtc': utc()})
    if collect:
        with (out / (name + '.stdout.txt')).open('w') as stdout, \
             (out / (name + '.stderr.txt')).open('w') as stderr:
            process = subprocess.run(command, cwd=source, env=env, stdout=stdout, stderr=stderr)
        text = (out / (name + '.stdout.txt')).read_text()
    else:
        with (out / (name + '.log')).open('w') as log:
            process = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        text = None
    (out / (name + '.exit')).write_text(str(process.returncode) + chr(10))
    write(out / (name + '.results.json'), {'success': process.returncode == 0,
          'exit': process.returncode, 'endedUtc': utc(), 'executionVerified': False})
    require(process.returncode == 0, name + ' failed; original output preserved')
    return text


def build_framework(args):
    configuration = args.configuration
    build, assessment, toolchain, out = [p.resolve() for p in
        (args.build, args.assessment, args.toolchain, args.output)]
    source = build / 'runtime'
    require(not below(out, source) and out != build and out != assessment and out != toolchain,
            'Fresh output must be separate from input directories and runtime worktree')
    out.mkdir(parents=True, exist_ok=False)
    result = {'success': False, 'base': BASE, 'commit': COMMIT, 'tree': TREE,
              'target': 'android.x64', 'configuration': configuration, 'frameworkConfiguration': 'Release',
              'source': str(source), 'executionVerified': False, 'frameworkInputsAvailable': False,
              'depsGenerated': False, 'frameworkComplete': False,
              'scope': 'Same-source Android library inputs and actual runtime-pack deps; no APK/execution'}
    before = []
    hashes = None
    try:
        completed, provenance, original_request = [read(build / name) for name in
            ('results.json', 'source.json', 'request.json')]
        accepted, ndk_receipt = read(assessment / 'results.json'), read(toolchain / 'results.json')
        require(completed['success'] and completed['buildExit'] == 0 and
                (build / 'build.exit').read_text().strip() == '0', 'Core build must succeed first')
        require(accepted['success'] and accepted['candidateCommit'] == COMMIT and
                accepted['metadataPassed'] and accepted['nativeConfigurationPassed'] and
                accepted['nativeGuidPassed'], 'Actual Android assessment must succeed first')
        for row in (completed, provenance, original_request):
            require(row['base'] == BASE and row['commit'] == COMMIT and row['tree'] == TREE,
                    'Build/source/request identity mismatch')
        require(completed['target'] == 'android.x64' and completed['configuration'] == configuration and
                completed['frameworkConfiguration'] == 'Release', 'Unexpected core target/configuration')
        hashes = provenance['sourceHashes']
        source_identity(source, hashes)
        require(ndk_receipt['success'] and ndk_receipt['clangExecutableVerified'], 'NDK not accepted')
        ndk = Path(ndk_receipt['ndk']).resolve()
        require(sha(ndk / 'build/cmake/android.toolchain.cmake') == ndk_receipt['toolchainSha256'] and
                str(ndk) == original_request['ndk'] and
                sha(toolchain / 'results.json') == original_request['toolchainReceiptSha256'],
                'Toolchain differs from matching core build')
        sdk = source / '.dotnet/dotnet'
        require(capture([sdk, '--version']) == original_request['sdkVersion'], 'Pinned SDK changed')
        metadata = assessment / 'metadata-assessment.json'
        require(metadata.is_file(), 'Accepted CoreLib metadata receipt missing')
        before = critical_inputs(source, build, completed, accepted)
        write(out / 'core-critical-before.json', before)
        tools, tools_receipt = android_tools(args.android_tools)
        env = dict(os.environ)
        removed = {name: env.pop(name) for name in SANITIZE if name in env}
        env.update({'PATH': tools['javaHome'] + '/bin:' + str(build.parent / 'tools/bin') +
                           ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                    'ANDROID_NDK_ROOT': str(ndk), 'ANDROID_NDK_HOME': str(ndk),
                    'ANDROID_SDK_ROOT': tools['androidSdkRoot'], 'JAVA_HOME': tools['javaHome'],
                    'DOTNET_CLI_HOME': str(out / 'dotnet-home'), 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                    'MSBUILDDISABLENODEREUSE': '1', 'DOTNET_CLI_USE_MSBUILD_SERVER': '0',
                    'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
        libraries = ['./build.sh', 'libs.native+libs.sfx', '-os', 'android', '-arch', 'x64', '-cross',
                     '-c', 'Release', '-rc', configuration, '-lc', 'Release', '-clrinterpreter', '-ninja',
                     '/m:1', '/p:RuntimeFlavor=CoreCLR', '/p:FeatureInterpreter=true',
                     '/p:FeatureDynamicCodeCompiled=true']
        properties = {'TargetOS': 'android', 'TargetArchitecture': 'x64', 'BuildArchitecture': 'arm64',
                      'Configuration': 'Release', 'RuntimeConfiguration': configuration,
                      'LibrariesConfiguration': 'Release', 'RuntimeFlavor': 'CoreCLR',
                      'FeatureInterpreter': 'true', 'FeatureDynamicCodeCompiled': 'true',
                      'CrossBuild': 'true', 'PublishReadyToRun': 'false'}
        if args.no_shared_compilation:
            libraries.append('/p:UseSharedCompilation=false')
            properties['UseSharedCompilation'] = 'false'
        queried = ('LibrariesSharedFrameworkBinArtifactsPath', 'LibrariesNativeArtifactsPath',
                   'CoreCLRArtifactsPath', 'IntermediateOutputPath', 'RuntimeIdentifier',
                   'NetCoreAppCurrent', 'RuntimeFlavor', 'PublishReadyToRun', 'CoreCLRConfiguration')
        project = 'src/installer/pkg/sfx/Microsoft.NETCore.App/Microsoft.NETCore.App.Runtime.CoreCLR.sfxproj'
        deps_command = [sdk, 'msbuild', project, '-restore', '-t:_GenerateSharedFrameworkDepsFile',
                        '-getItem:_SharedFrameworkDepsFile,FilesToPackage',
                        '-getProperty:' + ','.join(queried), '-v:quiet', '-nodeReuse:false', '-m:1']
        deps_command.extend('-p:' + name + '=' + value for name, value in properties.items())
        write(out / 'request.json', dict(result, build=str(build), assessment=str(assessment),
              toolchain=str(toolchain), ndk=str(ndk), sdkVersion=original_request['sdkVersion'],
              commands=[libraries, [str(p) for p in deps_command]], driverSha256=sha(__file__),
              sourceHashes=hashes, buildReceiptSha256=sha(build / 'results.json'),
              assessmentReceiptSha256=sha(assessment / 'results.json'),
              androidToolsReceipt=str(tools_receipt), androidToolsReceiptSha256=sha(tools_receipt),
              androidSdkRoot=tools['androidSdkRoot'], javaHome=tools['javaHome'],
              androidPlatformApi=tools['platformApi'], androidBuildToolsVersion=tools['buildToolsVersion'],
              metadataAssessmentSha256=sha(metadata), toolchainReceiptSha256=sha(toolchain / 'results.json'),
              removedCrossCompilationEnvironment=removed, globalEnvironmentChanged=False, startedUtc=utc()))
        request_path = out / 'request.json'
        actual_request = read(request_path)
        actual_request['sharedCompilationDisabled'] = args.no_shared_compilation
        write(request_path, actual_request)
        run_stage(out, source, env, 'libraries', libraries)
        after, same = check_critical(before)
        write(out / 'core-critical-after-libraries.json', after)
        require(same, 'Libraries stage changed accepted core inputs; stop before deps')
        source_identity(source, hashes)
        evaluated = msbuild_json(run_stage(out, source, env, 'deps', deps_command, collect=True))
        write(out / 'deps-evaluated.json', evaluated)
        props, items = evaluated['Properties'], evaluated['Items']
        require(props['RuntimeIdentifier'] == 'android-x64' and props['RuntimeFlavor'] == 'CoreCLR' and
                props['PublishReadyToRun'].lower() == 'false' and props['CoreCLRConfiguration'] == configuration,
                'Runtime-pack deps target evaluated wrong configuration')
        def actual_path(value):
            path = Path(value)
            path = (source / path if not path.is_absolute() else path).resolve()
            require(below(path, source / 'artifacts'), 'Evaluated output outside same-source artifacts')
            return path
        deps_items = items['_SharedFrameworkDepsFile']
        require(len(deps_items) == 1, 'Expected exactly one actual generated deps item')
        deps = actual_path(deps_items[0]['Identity'])
        manifest = read(deps)
        require(manifest.get('targets') and 'android-x64' in manifest['runtimeTarget']['name'],
                'Generated deps has no Android x64 target')
        framework = actual_path(props['LibrariesSharedFrameworkBinArtifactsPath'])
        native = actual_path(props['LibrariesNativeArtifactsPath'])
        core_native = actual_path(props['CoreCLRArtifactsPath']) / 'sharedFramework'
        require(framework.is_dir() and native.is_dir(), 'Library output directories missing')
        groups = {'framework': inventory(framework.glob('*.dll')),
                  'native': inventory([*native.glob('*.so'), *native.glob('*.a'),
                                       *core_native.glob('*.so'), *core_native.glob('*.a'),
                                       *native.glob('*.jar'), *native.glob('*.dex')]),
                  'headers': inventory([*native.rglob('*.h'), *core_native.rglob('*.h')]),
                  'deps': inventory([deps])}
        require({'System.Runtime.dll', 'System.Console.dll'} <=
                {Path(row['path']).name for row in groups['framework']}, 'Framework incomplete')
        require('libSystem.Security.Cryptography.Native.Android.so' in
                {Path(row['path']).name for row in groups['native']}, 'Android crypto shim missing')
        require({'libSystem.Security.Cryptography.Native.Android.jar',
                 'libSystem.Security.Cryptography.Native.Android.dex'} <=
                {Path(row['path']).name for row in groups['native']}, 'Actual Android crypto Java/dex output missing')
        assets = {Path(name).name for target in manifest['targets'].values() for library in target.values()
                  for category in ('runtime', 'native', 'runtimeTargets') for name in library.get(category, {})}
        require({'System.Private.CoreLib.dll', 'System.Runtime.dll', 'libcoreclr.so',
                 'libclrinterpreter.so', 'libclrjit.so'} <= assets, 'Actual deps lacks required matching assets')
        write(out / 'input-inventory.json', dict(base=BASE, commit=COMMIT, tree=TREE,
              target='android.x64', configuration=configuration, frameworkConfiguration='Release',
              source=str(source), groups=groups, sourceHashes=hashes,
              sourceCommit=COMMIT, frameworkDirectory=str(framework), nativeDirectory=str(native),
              coreNativeDirectory=str(core_native), depsFile=str(deps), depsSha256=sha(deps)))
        result.update(frameworkInputsAvailable=True, depsGenerated=True, depsFile=str(deps),
                      depsSha256=sha(deps), frameworkDirectory=str(framework), nativeDirectory=str(native),
                      coreNativeDirectory=str(core_native), frameworkFiles=len(groups['framework']),
                      nativeFiles=len(groups['native']), inputInventorySha256=sha(out / 'input-inventory.json'),
                      metadataAssessment=str(metadata), metadataAssessmentSha256=sha(metadata),
                      androidToolsReceipt=str(tools_receipt), androidToolsReceiptSha256=sha(tools_receipt),
                      assessmentReceiptSha256=sha(assessment / 'results.json'))
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if before:
            after, same = check_critical(before)
            write(out / 'core-critical-after.json', after)
            result['coreCriticalUnchanged'] = same
        try:
            if hashes:
                source_identity(source, hashes)
                result['sourceTrackedClean'] = True
        except Exception:
            result['sourceTrackedClean'] = False
            result['sourceVerificationError'] = traceback.format_exc()
        result['success'] = bool(result['frameworkInputsAvailable'] and result['depsGenerated'] and
                                 result.get('coreCriticalUnchanged') and result.get('sourceTrackedClean') and
                                 not result.get('error'))
        result['endedUtc'] = utc()
        write(out / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'assessment', 'toolchain', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--android-tools', type=Path,
                        help='Accepted private SDK/JDK receipt directory; required before library execution')
    parser.add_argument('--configuration', choices=('Checked', 'Release'), default='Checked')
    parser.add_argument('--no-shared-compilation', action='store_true',
                        help='Use separate C# compiler processes; retain original failed shared-server receipts')
    return build_framework(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
