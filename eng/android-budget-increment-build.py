#!/usr/bin/env python3
"""Prepare, then explicitly run a fresh matching Android x64 Release budget build.

No framework/APK/device stage or application execution is performed. The Mac
heavy-build slot must be granted by the experiment owner before the run phase.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import time
import traceback

SDK_VERSION = '11.0.100-rc.1.26420.103'
PARENT_DRIVER_SHA256 = '8ee55cd98d12af718c0f866c0a9859ee2aa9e6d99b154b9981cf0c7693347135'
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS_COMMIT = '20405f7ae23e183e038703aa5e356b3310fef427'
TREE = '91673a7980bda79006259e525741fecb04324444'
PROOF_SHA = '6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48'
COMMAND = ['./build.sh', 'clr.runtime+clr.native+clr.corelib+clr.tools+clr.crossarchtools',
           '-os', 'android', '-arch', 'x64', '-cross', '-c', 'Release',
           '-rc', 'Release', '-lc', 'Release', '-clrinterpreter', '-ninja', '/m:1']
REMOVED_ENV = ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
               'LIBRARY_PATH', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CMAKE_PREFIX_PATH',
               'PKG_CONFIG_PATH', 'EXTRA_CFLAGS', 'EXTRA_CXXFLAGS', 'EXTRA_LDFLAGS')


def require(condition, message):
    if not condition:
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
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def capture(command):
    return subprocess.check_output([str(v) for v in command], text=True).strip()


def git(source, *args):
    return capture(['git', '-C', source, *args])


def clean(source):
    return not git(source, 'status', '--porcelain', '--untracked-files=no')


def inside(path, parent):
    Path(path).resolve().relative_to(Path(parent).resolve())


def verify_proof(path):
    require(sha(path) == PROOF_SHA, 'Root source-proof receipt SHA differs')
    proof = read(path)
    require(proof['base'] == BASE and proof['windowsCommit'] == WINDOWS_COMMIT and
            proof['tree'] == TREE and proof['privateIndexCompositionVerified'] and
            proof['windowsDeltaOnlyCID'], 'Combined source proof identity differs')
    require(len(proof['sourceHashes']) == 37 and len(proof['patches']) == 7,
            'Expected exact source37 / seven reviewed patches')
    require(proof['exactIncrementVerified'] and proof['oldMobileDeltaOnlyMeter'],
            'Exact minimal increment proof required')
    for name, value in proof['sourceHashes'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                re.fullmatch('[0-9a-f]{64}', value), 'Invalid source hash mapping')
    return proof


def verify_source(source, commit, proof):
    require(git(source, 'rev-parse', 'HEAD') == commit and
            git(source, 'rev-parse', 'HEAD^{tree}') == TREE and clean(source),
            'Live worktree commit/tree/clean mismatch')
    changed = git(source, 'diff', '--name-only', BASE, commit).splitlines()
    require(set(changed) == set(proof['sourceHashes']) and len(changed) == 37,
            'Changed source set is not the exact reviewed source37')
    hashes = {name: sha(source / name) for name in changed}
    require(hashes == proof['sourceHashes'], 'Worktree LF bytes differ from root Git blob hashes')
    return hashes


def verify_ndk(receipt_path):
    receipt = read(receipt_path)
    require(receipt['success'] and receipt['clangExecutableVerified'] and
            receipt['package'] == 'ndk;27.2.12479018', 'Unverified NDK r27c receipt')
    ndk = Path(receipt['ndk']).resolve()
    clang = ndk / 'toolchains/llvm/prebuilt/darwin-x86_64/bin/clang'
    checks = {str(clang): receipt['clangSha256'],
              str(ndk / 'build/cmake/android.toolchain.cmake'): receipt['toolchainSha256'],
              str(ndk / 'source.properties'): receipt['sourcePropertiesSha256']}
    require(all(sha(name) == value for name, value in checks.items()), 'NDK critical bytes changed')
    return ndk, checks


def process_environment(root, output, ndk):
    env = dict(os.environ)
    removed = sorted(name for name in REMOVED_ENV if name in env)
    for name in REMOVED_ENV:
        env.pop(name, None)
    env.update(PATH=str(root / 'tools/bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               ANDROID_NDK_ROOT=str(ndk), ANDROID_NDK_HOME=str(ndk),
               DOTNET_CLI_HOME=str(output / 'dotnet-home'), DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
               MSBUILDDISABLENODEREUSE='1', DOTNET_CLI_USE_MSBUILD_SERVER='0',
               CMAKE_BUILD_PARALLEL_LEVEL='2')
    return env, removed


def preserve_hashes(root, extra):
    paths = [root / 'runtime/artifacts/bin/coreclr/iossimulator.arm64.Debug/libcoreclr.dylib']
    paths += [Path(value).resolve() for value in extra]
    return {str(path): sha(path) for path in paths}


def prepare(args):
    require(sys.platform == 'darwin', 'Preparation requires the private Darwin build host')
    root, output, repository = args.root.resolve(), args.output.resolve(), args.repository.resolve()
    inside(output, root)
    require(output.parent == root and not output.exists(), 'Output must be a fresh direct child of the experiment root')
    proof = verify_proof(args.source_proof)
    require(re.fullmatch('[0-9a-f]{40}', args.commit), 'Expected exact Mac combined commit')
    verify_source(repository, args.commit, proof)
    baseline = root / 'runtime'
    require(git(baseline, 'rev-parse', 'HEAD') == BASE and clean(baseline), 'Original baseline changed')
    ndk, ndk_hashes = verify_ndk(args.toolchain / 'results.json')
    require(capture([baseline / '.dotnet/dotnet', '--version']) == SDK_VERSION, 'Unexpected source SDK')
    preserved = preserve_hashes(root, args.preserve_file)
    output.mkdir()
    args.failure_dir_ready = True
    # Snapshots and failure records are local to this new output, never old evidence.
    (output / 'source-proof.json').write_bytes(args.source_proof.read_bytes())
    (output / 'ndk-receipt.json').write_bytes((args.toolchain / 'results.json').read_bytes())
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    source = output / 'runtime'
    with (output / 'source-setup.log').open('w') as log:
        subprocess.run(['git', '-C', str(repository), 'worktree', 'add', '--detach', str(source),
                        args.commit], stdout=log, stderr=subprocess.STDOUT, check=True)
    require(not (source / 'artifacts').exists() and not (source / '.dotnet').exists(),
            'Fresh worktree already contains build objects or SDK')
    hashes = verify_source(source, args.commit, proof)
    subprocess.run(['cp', '-cR', str(baseline / '.dotnet'), str(source / '.dotnet')], check=True)
    require(capture([source / '.dotnet/dotnet', '--version']) == SDK_VERSION and
            not (source / 'artifacts').exists(), 'SDK clone identity or no-object invariant failed')
    env, removed = process_environment(root, output, ndk)
    source_result = dict(base=BASE, commit=args.commit, windowsCommit=WINDOWS_COMMIT, tree=TREE,
                         sourceHashes=hashes, trackedClean=True, sourceTrackedClean=True,
                         configuration='android.x64.Release', patches=proof['patches'],
                         sourceProofSha256=PROOF_SHA, branch='detached', repository=str(repository))
    write(output / 'source.json', source_result)
    request = dict(schema='runeclr.android.session-budget.build.v1', base=BASE,
                   commit=args.commit, windowsCommit=WINDOWS_COMMIT, tree=TREE,
                   root=str(root), output=str(output), source=str(source), target='android.x64',
                   configuration='Release', frameworkConfiguration='Release', command=COMMAND,
                   sdkVersion=SDK_VERSION, sdkExecutableSha256=sha(source / '.dotnet/dotnet'),
                   ndk=str(ndk), ndkCriticalHashes=ndk_hashes,
                   toolchainReceiptSha256=sha(output / 'ndk-receipt.json'),
                   driverSha256=sha(output / 'driver.py'), parentDriverSha256=PARENT_DRIVER_SHA256, sourceProofSha256=PROOF_SHA,
                   preservedFiles=preserved, baselineCommit=BASE,
                   sourceReceiptSha256=sha(output / 'source.json'),
                   removedCrossCompilationEnvironment=removed,
                   processEnvironment={name: env[name] for name in ('PATH', 'ANDROID_NDK_ROOT',
                       'ANDROID_NDK_HOME', 'DOTNET_CLI_HOME', 'CMAKE_BUILD_PARALLEL_LEVEL')},
                   globalEnvironmentChanged=False, cleanBuildObjects=True,
                   reuse='SDK APFS clone only; no native/obj/CoreLib/framework products',
                   preparedUtc=utc(), executionVerified=False, buildStarted=False)
    require(all(sha(path) == value for path, value in preserved.items()) and clean(baseline),
            'Preserved baseline bytes changed during preparation')
    write(output / 'request.json', request)
    write(output / 'prepared.json', dict(success=True, state='prepared-only', buildStarted=False,
          requestSha256=sha(output / 'request.json'), sourceTrackedClean=True,
          executionVerified=False, completeBudgetCapability=False, preparedUtc=utc()))
    print(json.dumps(read(output / 'prepared.json'), indent=2))
    return 0


def compile_flags(entry):
    tokens = entry.get('arguments') or shlex.split(entry['command'])
    defines = {}
    for token in tokens:
        if token.startswith('-D'):
            key, _, value = token[2:].partition('=')
            defines[key] = value or '1'
    return tokens, defines


def preprocess_command(tokens):
    result, index = [], 0
    while index < len(tokens):
        if tokens[index:index + 2] == ['-Xclang', '-include-pch']:
            require(index + 3 < len(tokens) and tokens[index + 2] == '-Xclang', 'Unexpected PCH argument')
            index += 4
        elif tokens[index] == '-o':
            index += 2
        elif tokens[index] == '-c':
            index += 1
        else:
            result.append(tokens[index])
            index += 1
    # Textual -include cmake_pch.hxx remains, preserving actual definitions.
    return result + ['-E', '-dD']


def compiled_assessment(output, source, env, ndk):
    directory = source / 'artifacts/obj/coreclr/android.x64.Release'
    database = directory / 'compile_commands.json'
    entries = read(database)
    cache = (directory / 'CMakeCache.txt').read_text()
    for key, expected in [('ANDROID_ABI', 'x86_64'), ('FEATURE_INTERPRETER', '1'),
                          ('FEATURE_DYNAMIC_CODE_COMPILED', '1')]:
        match = re.search('^' + key + ':[^=]+=(.*)$', cache, re.M)
        require(match and match[1] == expected, 'Native cache feature mismatch: ' + key)
    matches = []
    for name in ('interpexec.cpp', 'exceptionhandling.cpp', 'eetwain.cpp', 'comutilnative.cpp',
                 'assemblynative.cpp', 'jitinterface.cpp'):
        selected = [entry for entry in entries if entry['file'].endswith('/vm/' + name) and
                    'cee_wks_core.dir' in entry.get('output', '')]
        require(len(selected) == 1, 'Expected one native budget compile owner: ' + name)
        entry = selected[0]
        inside(entry['file'], source)
        require(Path(entry['directory']).resolve() == directory, 'Compile output owner differs')
        tokens, defines = compile_flags(entry)
        required = {'TARGET_AMD64', 'HOST_AMD64', 'HOST_ANDROID', 'FEATURE_INTERPRETER',
                    'FEATURE_DYNAMIC_CODE_COMPILED', 'FEATURE_READYTORUN', 'FEATURE_VIRTUAL_STUB_DISPATCH', 'NDEBUG'}
        forbidden = {'DEBUG', '_DEBUG', '_DBG', 'BUILDENV_CHECKED', 'BUILDENV_DEBUG', 'FEATURE_CACHED_INTERFACE_DISPATCH'}
        require(required <= defines.keys() and not forbidden & defines.keys() and
                defines.get('URTBLDENV_FRIENDLY') == 'Retail' and '-O2' in tokens and
                any('x86_64' in value and 'linux-android24' in value for value in tokens),
                'Actual Android Release compile flags differ: ' + name)
        obj = directory / entry['output']
        matches.append(dict(file=name, entry=entry, object=str(obj), objectSha256=sha(obj), defines=defines))
    interp = next(row for row in matches if row['file'] == 'interpexec.cpp')
    tokens, _ = compile_flags(interp['entry'])
    command = preprocess_command(tokens)
    with (output / 'interpexec.preprocessed.cpp').open('w') as stream, (output / 'preprocess.log').open('w') as log:
        status = subprocess.run(command, cwd=directory, env=env, stdout=stream, stderr=log).returncode
    require(status == 0, 'Actual native dispatcher preprocessing failed')
    text = (output / 'interpexec.preprocessed.cpp').read_text()
    computed = re.search(r'^#define INTOP_DISPATCH\(op\)[^\r\n]*$', text, re.M)
    require('#define USE_COMPUTED_GOTO 1' in text and computed and
            'RUNECLR_CHARGE_DISPATCH()' in computed[0] and
            'goto *s_dispatchTable[opcode]' in computed[0] and
            'RuneCLRChargeCurrentInstruction(pFrame, pThreadContext)' in text and
            'goto RUNECLR_ABANDON_CLEANUP' in text, 'Compiled computed-goto budget path not present')
    nm = ndk / 'toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-nm'
    product = source / 'artifacts/bin/coreclr/android.x64.Release'
    symbols_path = product / 'libcoreclr.so.dbg'
    symbols = capture([nm, '--demangle', symbols_path])
    names = ('AssemblyNative_InitializeTerminalPrototypeLoadContext',
             'AssemblyNative_RuneCLRGetTerminalPrototypeVersion',
             'GCInterface_RuneCLRGetTerminalFinalizerBoundaryVersion',
             'GCInterface_RuneCLRIsTerminatedFinalizerOwner', 'RuneCLRIsTerminatedFrameOwner')
    kept = [line for line in symbols.splitlines() if line.split() and line.split()[-1] in names]
    require({line.split()[-1] for line in kept} == set(names), 'Native terminal/finalizer entry symbol missing')
    (output / 'native-budget-symbols.txt').write_text('\n'.join(kept) + '\n')
    result = dict(success=True, compileOwners=matches, compileDatabaseSha256=sha(database),
                  nativeCacheSha256=sha(directory / 'CMakeCache.txt'),
                  preprocessingCommand=command, preprocessingExit=0,
                  preprocessingSha256=sha(output / 'interpexec.preprocessed.cpp'),
                  computedGotoBudgetPathCompiled=True, featureInterpreter=True,
                  featureDynamicCodeCompiled=True, cachedInterfaceDispatch=False,
                  nativeSymbols=kept, symbolImage=str(symbols_path), symbolImageSha256=sha(symbols_path),
                  executionVerified=False, metadataVerified=False,
                  scope='Actual Release compile flags/preprocessed dispatcher/native symbols; PE ABI assessment remains separate')
    write(output / 'compile-assessment.json', result)
    return result


def product_files(source):
    product = source / 'artifacts/bin/coreclr/android.x64.Release'
    compilers = [path for path in product.glob('**/crossgen2') if path.is_file()]
    require(len(compilers) == 1, 'Expected unique matching Mac-host crossgen2')
    compiler = compilers[0]
    critical = {'native': product / 'libcoreclr.so', 'interpreter': product / 'libclrinterpreter.so',
                'targetJit': product / 'libclrjit.so', 'corelib': product / 'IL/System.Private.CoreLib.dll',
                'crossgen2': compiler, 'jitinterface': compiler.parent / 'libjitinterface_arm64.dylib',
                'crossarchJit': compiler.parent / 'libclrjit_unix_x64_arm64.dylib'}
    for name, path in critical.items():
        inside(path, product)
        require(path.is_file(), 'Missing matching product: ' + name)
    for name in ('native', 'interpreter', 'targetJit'):
        with critical[name].open('rb') as stream:
            header = stream.read(20)
        require(header[:7] == b'\x7fELF\x02\x01\x01' and
                struct.unpack_from('<HH', header, 16) == (3, 62), 'Expected Android x64 shared ELF: ' + name)
    return critical


def run(args):
    require(sys.platform == 'darwin', 'Build requires the private Darwin host')
    require(args.build_slot_granted, 'Owner must release the exclusive heavy-build slot before run')
    output = args.output.resolve()
    request, prepared = read(output / 'request.json'), read(output / 'prepared.json')
    require(prepared['success'] and sha(output / 'request.json') == prepared['requestSha256'], 'Prepared receipt changed')
    require(sha(__file__) == request['driverSha256'] == sha(output / 'driver.py'), 'Frozen driver differs')
    require(not (output / 'run-started.json').exists(), 'Build is one-shot; failures need a fresh attempt')
    args.failure_dir_ready = True
    source, root = Path(request['source']), Path(request['root'])
    require(source == output / 'runtime' and root == output.parent and request['command'] == COMMAND,
            'Prepared source/output/command identity changed')
    proof = verify_proof(output / 'source-proof.json')
    verify_source(source, request['commit'], proof)
    require(sha(output / 'source.json') == request['sourceReceiptSha256'], 'Source receipt changed')
    require(not (source / 'artifacts').exists(), 'Build artifacts already exist before first invocation')
    require(sha(source / '.dotnet/dotnet') == request['sdkExecutableSha256'] and
            capture([source / '.dotnet/dotnet', '--version']) == SDK_VERSION, 'Source SDK changed')
    require(sha(output / 'ndk-receipt.json') == request['toolchainReceiptSha256'], 'NDK receipt changed')
    ndk, hashes = verify_ndk(output / 'ndk-receipt.json')
    require(hashes == request['ndkCriticalHashes'], 'NDK bytes changed after prepare')
    require(all(sha(path) == value for path, value in request['preservedFiles'].items()), 'Original products changed')
    env, removed = process_environment(root, output, ndk)
    write(output / 'run-started.json', dict(pid=os.getpid(), startedUtc=utc(), requestSha256=sha(output / 'request.json'),
          heavyBuildSlotGranted=True, removedCrossCompilationEnvironment=removed, executionVerified=False))
    with (output / 'build.log').open('w') as log:
        status = subprocess.run(COMMAND, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    (output / 'build.exit').write_text(str(status) + '\n')
    result = dict(success=False, buildExit=status, base=BASE, commit=request['commit'], tree=TREE,
                  windowsCommit=WINDOWS_COMMIT, target='android.x64', configuration='Release',
                  frameworkConfiguration='Release', executionVerified=False, frameworkComplete=False,
                  metadataVerified=False, completeBudgetCapability=False, endedUtc=utc())
    try:
        require(status == 0, 'Official build failed: see original build.log')
        verify_source(source, request['commit'], proof)
        critical = product_files(source)
        identities = {name: sha(path) for name, path in critical.items()}
        write(output / 'artifacts.json', [dict(role=name, path=str(path), sha256=identities[name],
              size=path.stat().st_size) for name, path in critical.items()])
        assessment = compiled_assessment(output, source, env, ndk)
        unchanged = all(sha(path) == value for path, value in request['preservedFiles'].items())
        require(unchanged and clean(root / 'runtime'), 'Original baseline/product changed during build')
        require(all(sha(path) == identities[name] for name, path in critical.items()), 'Products changed during assessment')
        result.update(success=True, sourceTrackedClean=True, baselineNativeUnchanged=unchanged,
                      preservedProductsUnchanged=unchanged, criticalHashes=identities,
                      computedGotoBudgetPathCompiled=assessment['computedGotoBudgetPathCompiled'],
                      featureInterpreter=True, featureDynamicCodeCompiled=True,
                      requestSha256=sha(output / 'request.json'), sourceProofSha256=PROOF_SHA)
        for name, path in critical.items():
            result[name] = str(path)
            result[name + 'Sha256'] = identities[name]
    except Exception:
        result['error'] = traceback.format_exc()
    write(output / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else status or 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='phase', required=True)
    prep = sub.add_parser('prepare', help='Create fresh source and SDK only; no build')
    for name in ('root', 'output', 'repository', 'source-proof', 'toolchain'):
        prep.add_argument('--' + name, type=Path, required=True)
    prep.add_argument('--commit', required=True)
    prep.add_argument('--preserve-file', action='append', default=[], type=Path)
    build = sub.add_parser('run', help='Consume the frozen preparation after exclusive build-slot grant')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--build-slot-granted', action='store_true')
    args = parser.parse_args()
    try:
        return prepare(args) if args.phase == 'prepare' else run(args)
    except Exception:
        if getattr(args, 'failure_dir_ready', False):
            # Preserve the first failure instead of overwriting previous evidence.
            write(args.output / ('driver-failure-' + str(time.time_ns()) + '.json'),
                  dict(error=traceback.format_exc(), phase=args.phase, executionVerified=False))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
