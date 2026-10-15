#!/usr/bin/env python3
"""Build matching device libraries, deps and an unsigned framework composite in private outputs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

COMMIT = '3126bbc9a8851a09ac6435b18a12882bad48f3ee'
TREE = '710936ae1729a5689ab0e0896f3cf722ddd3d31c'
PROOF = '29d83ae68ca57ec2067261d15a901e81f8422981609f1fe6aaad5cb37879de5e'
DEVICE_DRIVER = '24fe654ead15f3fe170ab02cdae191270d72080d409337a805701a31c5c3ea8b'
METADATA = '57934b53bc3665d3ad1b7f2def5acd084cdb0bf1d089f1f23a774d90d58aaaa6'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def cap(argv):
    return subprocess.check_output(list(map(str, argv)), text=True).strip()


def identity(build):
    source = build / 'runtime'
    proof, receipt = read(build / 'source-proof.json'), read(build / 'results.json')
    need(sha(build / 'source-proof.json') == PROOF and receipt['success'] and receipt['buildExit'] == 0,
         'Accepted device source/build receipt required')
    need(receipt['commit'] == COMMIT and receipt['tree'] == TREE and receipt['target'] == 'ios.arm64'
         and receipt['configuration'] == 'Release' and receipt['assessment']['deviceMachO']['platform'] == 2,
         'Accepted device build identity differs')
    need(cap(['git', '-C', source, 'rev-parse', 'HEAD']) == COMMIT
         and cap(['git', '-C', source, 'rev-parse', 'HEAD^{tree}']) == TREE
         and not cap(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']), 'Device source changed')
    need(len(proof['sourceHashes']) == 38 and all(sha(source / n) == v for n, v in proof['sourceHashes'].items()),
         'Actual 38 frozen LF sources changed')
    critical = {row['path']: row['sha256'] for row in read(build / 'artifacts.json')}
    for name in ['native', 'corelib', 'crossgen2']:
        need(sha(receipt[name]) == receipt[name + 'Sha256'], 'Critical device product differs')
    need(all(sha(n) == v for n, v in critical.items()), 'Original critical artifact changed')
    return source, receipt, critical


def module(path):
    need(sha(path) == DEVICE_DRIVER, 'Frozen device build/platform helper changed')
    spec = importlib.util.spec_from_file_location('accepted_device_platform', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def stage(out, source, env, label, argv):
    argv = list(map(str, argv))
    write(out / (label + '.request.json'), {'argv': argv, 'cwd': str(source), 'startedUtc': utc()})
    with (out / (label + '.stdout')).open('x') as stdout, (out / (label + '.stderr')).open('x') as stderr:
        child = subprocess.Popen(argv, cwd=source, env=env, stdout=stdout, stderr=stderr)
        write(out / (label + '.process.json'), {'pid': child.pid, 'driverPid': os.getpid(), 'argv': argv})
        code = child.wait()
    write(out / (label + '.result.json'), {'exitCode': code, 'stdoutSha256': sha(out / (label + '.stdout')),
          'stderrSha256': sha(out / (label + '.stderr')), 'endedUtc': utc()})
    need(code == 0, label + ' failed; original attempt and streams preserved')
    return (out / (label + '.stdout')).read_text()


def evaluated(text):
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                result, _ = decoder.raw_decode(text[i:])
                if isinstance(result, dict) and 'Items' in result and 'Properties' in result:
                    return result
            except ValueError:
                pass
    raise RuntimeError('Actual MSBuild evaluated properties/items JSON missing')


def inventory(directory):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['preflight', 'build'])
    for name in ['root', 'build', 'output', 'device-driver', 'metadata-tool']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--build-slot-granted', action='store_true')
    parser.add_argument('--reuse-framework', type=Path)
    args = parser.parse_args()
    need(sys.platform == 'darwin', 'Configured Mac required')
    root, build, out = args.root.resolve(), args.build.resolve(), args.output.resolve()
    need(out.parent == root and not out.exists(), 'Fresh private experiment directory required')
    need(shutil.disk_usage(root).free > 60 * 1024**3, 'At least60GiB free private-build space required')
    source, receipt, critical = identity(build)
    device = module(args.device_driver)
    need(device.macho_device(receipt['native'])['sha256'] == receipt['nativeSha256'], 'Actual device Mach-O differs')
    need(sha(args.metadata_tool) == METADATA, 'Original metadata inspector differs')
    sdk = source / '.dotnet/dotnet'
    sdk_version = cap([sdk, '--version'])
    need(sdk_version == '11.0.100-rc.1.26420.103', 'Private source-build SDK differs')
    libraries = ['./build.sh', 'libs.native+libs.sfx', '-os', 'ios', '-arch', 'arm64', '-cross',
                 '-c', 'Release', '-rc', 'Release', '-lc', 'Release', '-clrinterpreter', '-ninja', '/m:1',
                 '/p:RuntimeFlavor=CoreCLR', '/p:FeatureInterpreter=true', '/p:FeatureDynamicCodeCompiled=false',
                 '/p:UseSharedCompilation=false']
    props = {'TargetOS': 'ios', 'TargetArchitecture': 'arm64', 'BuildArchitecture': 'arm64',
             'Configuration': 'Release', 'RuntimeConfiguration': 'Release', 'LibrariesConfiguration': 'Release',
             'RuntimeFlavor': 'CoreCLR', 'FeatureInterpreter': 'true', 'FeatureDynamicCodeCompiled': 'false',
             'CrossBuild': 'true', 'PublishReadyToRun': 'false', 'UseSharedCompilation': 'false'}
    queried = ['LibrariesSharedFrameworkBinArtifactsPath', 'LibrariesNativeArtifactsPath', 'CoreCLRArtifactsPath',
               'RuntimeIdentifier', 'NetCoreAppCurrent', 'RuntimeFlavor', 'PublishReadyToRun', 'CoreCLRConfiguration',
               'FeatureInterpreter', 'FeatureDynamicCodeCompiled']
    project = 'src/installer/pkg/sfx/Microsoft.NETCore.App/Microsoft.NETCore.App.Runtime.CoreCLR.sfxproj'
    deps = [sdk, 'msbuild', project, '-restore', '-t:_GenerateSharedFrameworkDepsFile',
            '-getItem:_SharedFrameworkDepsFile,FilesToPackage', '-getProperty:' + ','.join(queried),
            '-v:quiet', '-nodeReuse:false', '-m:1'] + ['-p:' + n + '=' + v for n, v in props.items()]
    reused = None
    if args.reuse_framework:
        previous = args.reuse_framework.resolve()
        need(previous.parent == root and previous != out, 'Reuse must name a different private experiment')
        previous_request, previous_result = read(previous / 'request.json'), read(previous / 'results.json')
        need(previous_request['criticalBefore'] == critical and previous_request['sourceProofSha256'] == PROOF
             and previous_result['criticalUnchanged'] and previous_result['sourceTrackedClean']
             and previous_result['frameworkBuilt'] and not previous_result['compositeBuilt'],
             'Successful libraries and unchanged accepted runtime required for continuation')
        for label in ['libraries', 'deps']:
            stage_result = read(previous / (label + '.result.json'))
            need(stage_result['exitCode'] == 0 and all(sha(previous / (label + '.' + stream)) ==
                 stage_result[stream + 'Sha256'] for stream in ['stdout', 'stderr']), 'Reused stage streams changed')
        reused = evaluated((previous / 'deps.stdout').read_text())
        need(reused == read(previous / 'deps-evaluated.json'), 'Reused evaluated deps differ from original stream')
    if args.phase == 'preflight':
        print(json.dumps({'passed': True, 'sourceCommit': COMMIT, 'sourceTree': TREE, 'target': 'ios.arm64',
                          'commands': [libraries, list(map(str, deps))], 'criticalFiles': len(critical),
                          'nativeBuildRequested': False, 'sourceFilesVerified': 38, 'buildExecuted': False}))
        return 0
    need(args.build_slot_granted, 'Exclusive Mac heavy-build slot required')
    out.mkdir()
    shutil.copyfile(__file__, out / 'driver.py')
    result = {'schema': 'runeclr.ios-device-batch.framework.v1', 'success': False, 'target': 'ios.arm64',
              'configuration': 'Release', 'sourceCommit': COMMIT, 'sourceTree': TREE,
              'frameworkBuilt': False, 'depsGenerated': False, 'compositeBuilt': False,
              'physicalDeviceExecuted': False, 'signingChanged': False, 'executionVerified': False}
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_', 'RUNECLR_', 'DYLD_', 'LD_'))
           and k not in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH',
                        'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH',
                        'EXTRA_CFLAGS', 'EXTRA_CXXFLAGS', 'EXTRA_LDFLAGS')}
    env.update({'PATH': str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'CMAKE_PREFIX_PATH': str(root / 'tools/icu'), 'PKG_CONFIG_PATH': str(root / 'tools/icu/lib/pkgconfig'),
                'DOTNET_CLI_HOME': str(out / 'dotnet-home'), 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                'MSBUILDDISABLENODEREUSE': '1', 'DOTNET_CLI_USE_MSBUILD_SERVER': '0', 'CMAKE_BUILD_PARALLEL_LEVEL': '2'})
    write(out / 'request.json', dict(result, source=str(source), build=str(build), sdkVersion=sdk_version,
          commands=[libraries, list(map(str, deps))], driverSha256=sha(__file__),
          nativeBuildReceiptSha256=sha(build / 'results.json'), criticalBefore=critical,
          sourceProofSha256=PROOF, metadataToolSha256=METADATA, startedUtc=utc()))
    try:
        if reused is None:
            stage(out, source, env, 'libraries', libraries)
        else:
            write(out / 'reused-stages.json', {'previousDirectory': str(previous),
                  'previousRequestSha256': sha(previous / 'request.json'),
                  'previousResultSha256': sha(previous / 'results.json'),
                  'librariesResultSha256': sha(previous / 'libraries.result.json'),
                  'depsResultSha256': sha(previous / 'deps.result.json'), 'librariesOrDepsRerun': False})
        need(identity(build)[2] == critical, 'Libraries changed accepted runtime-critical products')
        result['frameworkBuilt'] = True
        data = reused if reused is not None else evaluated(stage(out, source, env, 'deps', deps))
        write(out / 'deps-evaluated.json', data)
        properties, items = data['Properties'], data['Items']
        need(properties['RuntimeIdentifier'] == 'ios-arm64' and properties['RuntimeFlavor'] == 'CoreCLR'
             and properties['PublishReadyToRun'] == 'false' and properties['CoreCLRConfiguration'] == 'Release'
             and properties['FeatureInterpreter'] == 'true' and properties['FeatureDynamicCodeCompiled'] == 'false',
             'Actual framework evaluation chose another runtime/target')

        def artifact(value):
            path = Path(value)
            path = (source / path if not path.is_absolute() else path).resolve()
            need(path.is_relative_to(source / 'artifacts'), 'Actual evaluated output outside private source artifacts')
            return path

        framework = artifact(properties['LibrariesSharedFrameworkBinArtifactsPath'])
        native = artifact(properties['LibrariesNativeArtifactsPath'])
        need(len(items['_SharedFrameworkDepsFile']) == 1, 'Expected one actual deps file')
        deps_file = artifact(items['_SharedFrameworkDepsFile'][0]['Identity'])
        manifest = read(deps_file)
        need('ios-arm64' in manifest['runtimeTarget']['name'], 'Generated deps target differs')
        input_dir, layout = out / 'input', out / 'layout'
        input_dir.mkdir(); layout.mkdir()
        originals = {str(p): sha(p) for p in framework.glob('*.dll')}
        need(len(originals) >= 150 and {'System.Runtime.dll', 'System.Console.dll', 'System.Runtime.Loader.dll'}
             <= {Path(p).name for p in originals}, 'Actual framework inputs incomplete')
        for name, digest in originals.items():
            path = Path(name)
            if path.name != 'System.Private.CoreLib.dll':
                shutil.copy2(path, input_dir / path.name)
        shutil.copy2(receipt['corelib'], input_dir / 'System.Private.CoreLib.dll')
        need(sha(input_dir / 'System.Private.CoreLib.dll') == receipt['corelibSha256'], 'Current private CoreLib raw bytes differ')
        native_inputs = {str(p): sha(p) for directory in [native, Path(receipt['native']).parent / 'sharedFramework']
                         for pattern in ['*.dylib', '*.a'] for p in directory.glob(pattern)}
        need(any(Path(p).name.startswith('libSystem.Native') for p in native_inputs)
             and any('Security.Cryptography.Native.Apple' in Path(p).name for p in native_inputs), 'Actual Apple native shims missing')
        # Bind each packaged native asset to the actual runtime-pack item source.
        packaged = {}
        for item in items['FilesToPackage']:
            if Path(item['Identity']).suffix not in ['.dylib', '.a']:
                continue
            path = artifact(item['Identity'])
            need(str(path) in native_inputs, 'Packaged native source outside device native products')
            need(path.name not in packaged, 'Actual native package contains duplicate basenames')
            packaged[path.name] = str(path)
        deps_native = {Path(n).name for target in manifest['targets'].values()
                       for library in target.values() for n in library.get('native', {})}
        need(set(packaged) == deps_native, 'Actual deps native assets differ from evaluated package items')
        selected = dict(packaged)
        for name in sorted(native_inputs):
            path = Path(name)
            if path.parent == native and path.name not in selected:
                selected[path.name] = str(path)
        native_raw = out / 'native-raw'
        for label, directory in [('libraries', native), ('coreclr', Path(receipt['native']).parent / 'sharedFramework')]:
            (native_raw / label).mkdir(parents=True)
            for name in native_inputs:
                path = Path(name)
                if path.parent == directory:
                    shutil.copy2(path, native_raw / label / path.name)
        write(out / 'native-selection.json', {'rule': 'Actual deps native assets bind FilesToPackage identity; unlisted libraries-native products supplement only absent basenames',
              'packaged': packaged, 'selected': selected, 'rawSources': native_inputs,
              'excludedHostCompilerInputs': True})
        for name in selected.values():
            shutil.copy2(name, layout / Path(name).name)
        shutil.copy2(receipt['native'], layout / 'libcoreclr.dylib')
        shutil.copy2(deps_file, layout / 'Microsoft.NETCore.App.deps.json')
        result['depsGenerated'] = True
        inputs = inventory(input_dir)
        rsp = out / 'crossgen.rsp'
        options = ['--targetos:ios', '--targetarch:arm64', '--obj-format:macho', '--composite', '--inputbubble',
                   '--parallelism:2', '--resilient', '--optimize', '--out:' + str(layout / 'framework.dylib')]
        rsp.write_text(chr(10).join(options + [str(input_dir / p) for p in sorted(inputs)]) + chr(10))
        stage(out, source, env, 'crossgen', [receipt['crossgen2'], '@' + str(rsp)])
        shutil.copy2(layout / 'framework.dylib', out / 'framework.o')
        stage(out, source, env, 'composite-link', ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios15.3',
              '-dynamiclib', out / 'framework.o', '-Wl,-install_name,@rpath/framework.dylib', '-o', layout / 'framework.dylib'])
        platform = device.macho_device(layout / 'framework.dylib')
        need(all((layout / p).is_file() for p in inputs), 'Composite components incomplete')
        host_version = [line.split()[1] for line in cap([sdk, '--list-runtimes']).splitlines()
                        if line.startswith('Microsoft.NETCore.App ')][-1]
        metadata = json.loads(stage(out, source, env, 'metadata', [sdk, 'exec', '--fx-version', host_version,
                                   args.metadata_tool, input_dir / 'System.Private.CoreLib.dll', layout / 'System.Private.CoreLib.dll']))
        need(len(metadata) == 2 and metadata[0]['sha256'] == receipt['corelibSha256']
             and metadata[0]['methods'] == metadata[1]['methods'], 'Private CoreLib method metadata changed in composite')
        write(out / 'input-inventory.json', {'originalFramework': originals, 'originalNative': native_inputs,
              'compositeInputs': inputs, 'layout': inventory(layout), 'corelibRawSha256': receipt['corelibSha256'],
              'depsFile': str(deps_file), 'depsSha256': sha(deps_file), 'frameworkPlatform': platform,
              'sourceCommit': COMMIT, 'sourceTree': TREE, 'authorBundled': False})
        need(inputs == inventory(input_dir) and all(sha(p) == h for p, h in originals.items())
             and all(sha(p) == h for p, h in native_inputs.items()), 'Library/composite input bytes changed')
        result.update(compositeBuilt=True, frameworkFiles=len(inputs), nativeFiles=len(native_inputs),
                      layoutDirectory=str(layout), frameworkPlatform=platform, inputInventorySha256=sha(out / 'input-inventory.json'))
    except Exception as error:
        result['error'] = str(error)
        (out / 'driver-failure.txt').write_text(traceback.format_exc())
    finally:
        try:
            _, _, after = identity(build)
            result.update(criticalUnchanged=after == critical, sourceTrackedClean=True)
        except Exception as error:
            result.update(criticalUnchanged=False, sourceTrackedClean=False, preservationError=str(error))
        result['success'] = all(result.get(n) for n in ['frameworkBuilt', 'depsGenerated', 'compositeBuilt',
                                                      'criticalUnchanged', 'sourceTrackedClean']) and 'error' not in result
        result['endedUtc'] = utc()
        write(out / 'results.json', result)
        print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
