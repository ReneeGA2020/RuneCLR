"""Read-only four-PE budget ABI assessment after the fresh Android Release build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback
import re
import uuid

INSPECTOR_SHA = '57934b53bc3665d3ad1b7f2def5acd084cdb0bf1d089f1f23a774d90d58aaaa6'
TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
COMMIT = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
BUILD_SHA = '8831f2f0a7b094fffb0203b21a00c7a2533f23d7f57df3b480ab65dee625aa51'
PROOF_SHA = 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97'
TYPED_SHA = '4605f5d3a34676e5fb6c8da856c1c7478620a2c29622b5fe73724d6a51c68cfe'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def check(stages, rows, typed_rows, descriptor):
    required = {'RuneCLR_CreateInterpreterRequired', 'RuneCLR_GetExecutionPolicyVersion', 'RuneCLR_GetExecutionPolicy',
                'RuneCLR_GetExecutionPolicyVersionNative', 'RuneCLR_GetExecutionPolicyNative'}
    meter = {'RuneCLR_CreateInstructionMetered', 'RuneCLR_GetInstructionMeterVersion', 'RuneCLR_GetInstructionMeterRemaining',
             'RuneCLR_GetInstructionMeterExecuted', 'RuneCLR_GetInstructionMeterExhausted', 'RuneCLR_GetInstructionMeterVersionNative',
             'RuneCLR_GetInstructionMeterRemainingNative', 'RuneCLR_GetInstructionMeterExecutedNative'}
    terminal = {'RuneCLR_CreateTerminalPrototype', 'RuneCLR_GetTerminalPrototypeVersion', 'RuneCLR_GetTerminalPrototypeIsTerminated',
                'RuneCLR_GetTerminalPrototypeReason', 'RuneCLR_GetTerminalPrototypePhase', 'RuneCLR_GetTerminalPrototypeCleanupRemaining',
                'RuneCLR_GetTerminalPrototypeCleanupExecuted', 'RuneCLR_GetTerminalPrototypeVersionNative',
                'RuneCLR_GetTerminalPrototypeReasonNative', 'RuneCLR_GetTerminalPrototypePhaseNative',
                'RuneCLR_GetTerminalPrototypeCleanupRemainingNative', 'RuneCLR_GetTerminalPrototypeCleanupExecutedNative'}
    gc = {'RuneCLR_GetTerminalFinalizerBoundaryVersion', 'RuneCLR_GetTerminalFinalizerBoundaryVersionNative', 'RuneCLR_IsTerminatedFinalizerOwner'}
    signatures = {'GCInterface_RuneCLRGetTerminalFinalizerBoundaryVersion': '000008',
                  'AssemblyNative_InitializeInterpreterRequiredLoadContext': '000218180F18',
                  'AssemblyNative_InitializeInstructionMeteredLoadContext': '000318180A0F18',
                  'AssemblyNative_InitializeTerminalPrototypeLoadContext': '000418180A0A0F18'}
    require(len(rows) == len(stages) == 4 and len(typed_rows) == 3, 'Expected three CoreLib stages plus managed compiler flag mirror')
    for path, row, typed in zip(stages[:3], rows[:3], typed_rows):
        require(row['sha256'] == typed['sha256'] == sha(path), 'Actual inspector PE identity differs')
        methods = row['methods']
        outer = [m for m in methods if m['owner'] == 'System.Runtime.Loader.AssemblyLoadContext' and m['name'].startswith('RuneCLR_')]
        gc_methods = [m for m in methods if m['owner'] == 'System.GC' and m['name'].startswith('RuneCLR_')]
        require(len(outer) == 25 and {m['name'] for m in outer} == required | meter | terminal and
                len(gc_methods) == 3 and {m['name'] for m in gc_methods} == gc, 'Exact private bridge family differs')
        require(all('Private' in m['attributes'] for m in outer + gc_methods), 'Private API visibility differs')
        nested = [m for m in methods if m['owner'].endswith('+RuneCLRInterpreterLoadContext')]
        require(len(nested) == 5 and {m['name'] for m in nested} == {'.ctor', 'Load', 'LoadUnmanagedDll'} and
                sorted(int(m['signatureHex'][2:4], 16) for m in nested if m['name'] == '.ctor') == [2, 3, 4], 'Nested factory context ABI differs')
        for entry, signature in signatures.items():
            require([m['signatureHex'] for m in methods if m['nativeEntry'] == entry] == [signature], 'Factory/GC QCall ABI differs: ' + entry)
        for entry, prefix in [('GCInterface_RuneCLRIsTerminatedFinalizerOwner', '00010511'), ('RuneCLRIsTerminatedFrameOwner', '0001050F11')]:
            found = [m for m in methods if m['nativeEntry'] == entry]
            require(len(found) == 1 and found[0]['signatureHex'].startswith(prefix), 'NoGC owner-query ABI differs')
        queries = typed['queries']
        require(len(queries) == 2, 'Missing resolved typed owner queries')
        for entry, type_name, pointer in [('GCInterface_RuneCLRIsTerminatedFinalizerOwner', 'System.Runtime.CompilerServices.ObjectHandleOnStack', False),
                                          ('RuneCLRIsTerminatedFrameOwner', 'System.Runtime.StackFrameIterator', True)]:
            found = [q for q in queries if q['entry'] == entry]
            require(len(found) == 1 and found[0]['nativeReturnType'] == 'Byte' and found[0]['parameterType'] == type_name and
                    found[0]['pointer'] == pointer and found[0]['count'] == 1 and found[0]['hiddenErrorStatus'] is False,
                    'Resolved finalizer/EH query type or hidden-error ABI differs')
    require(rows[1]['sha256'] == rows[2]['sha256'], 'PostTrim/ProductIL bytes differ')
    require(rows[3]['sha256'] == sha(stages[3]) and
            any(f['name'] == 'CORJIT_FLAG_INTERPRET_REQUIRED' and f['value'] == 33 for f in rows[3]['fields']),
            'Actual managed compiler bit33 mirror missing')
    roots = {name for name in required | meter | terminal if not name.endswith('Native')} | {'RuneCLR_GetTerminalFinalizerBoundaryVersion'}
    text = descriptor.read_text()
    require(all('name="' + name + '"' in text for name in roots), 'Actual generated ILLink root descriptor missing API')
    return dict(policyFamily=5, meterFamily=8, terminalFamily=12, gcFamily=3, nestedConstructorArities=[2, 3, 4],
                hiddenErrorFactoryArities=[2, 3, 4], nativeOwnerQueryReturn='Byte', objectHandleOnStackResolved=True,
                stackFrameIteratorResolved=True, ownerQueriesNoHiddenErrorStatus=True,
                postTrimProductIdentical=True, managedCompilerBit33=True, generatedRootsPresent=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'inspector', 'typed-inspector', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--typed-inspector-sha256', required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    result = dict(success=False, executionVerified=False, completeBudgetCapability=False)
    try:
        require(sha(args.build / 'results.json') == BUILD_SHA and sha(args.build / 'source-proof.json') == PROOF_SHA, 'Exact new build/source proof binding differs')
        proof = json.loads((args.build / 'source-proof.json').read_text())
        require(proof['schema'] == 'runeclr.mobile-derived-ledger.source-proof.v1' and proof['sourceCommit'] == COMMIT and proof['tree'] == TREE and proof['exactDerivedLedgerVerified'] and proof['phaseAcquireLoadDefaultOff'] and proof['terminalDerivedLedgerDefaultOff'] and proof['phaseAndDerivedSwitchesIndependent'] and proof['layoutSize'] == 64 and proof['layoutAlignment'] == 8, 'Exact default-OFF derived source proof missing')
        original = json.loads((args.build / 'results.json').read_text())
        completed = original
        require(completed['success'] and completed['tree'] == TREE and completed['target'] == 'android.x64' and completed['configuration'] == 'Release', 'Matching Android Release build incomplete')
        require(original['success'] and original['commit'] == COMMIT and original['buildExit'] == 0 and
                (args.build / 'build.exit').read_text().strip() == '0', 'Matching successful official build absent')
        require({row['role']:row['sha256'] for row in json.loads((args.build / 'artifacts.json').read_text())} == completed['criticalHashes'],
                'Independent review products do not equal the original seven artifact hashes')
        require(sha(args.inspector) == INSPECTOR_SHA and sha(args.typed_inspector) == args.typed_inspector_sha256 == TYPED_SHA, 'Trusted PE inspector hash differs')
        source = args.build / 'runtime'
        coreobj = source / 'artifacts/obj/coreclr/System.Private.CoreLib/android.x64.Release'
        mirrors = list((source / 'artifacts/obj/coreclr/ILCompiler.Compiler').glob('android.x64.*/ILCompiler.Compiler.dll'))
        require(len(mirrors) == 1, 'Expected exactly one actual managed compiler flag mirror')
        stages = [coreobj / 'PreTrim/System.Private.CoreLib.dll', coreobj / 'System.Private.CoreLib.dll',
                  Path(completed['corelib']), mirrors[0]]
        original_hashes = {str(path): sha(path) for path in stages}
        source_hashes = json.loads((args.build / 'source.json').read_text())['sourceHashes']
        require(all(sha(source / path) == value for path, value in source_hashes.items()), 'Actual source37 bytes changed')
        require(source_hashes == proof['sourceHashes'], 'Source receipt differs from reviewed exact37 proof')
        require(len(source_hashes) == 37 and subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() == COMMIT and subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip() == TREE and not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip(), 'Live exact source identity differs')
        commands = []
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DOTNET_', 'COMPlus_'))}
        for prefix, tool in [('metadata', args.inspector), ('typed-query', args.typed_inspector)]:
            inspected = stages if prefix == 'metadata' else stages[:3]
            command = [str(source / '.dotnet/dotnet'), 'exec', '--fx-version', '11.0.0-rc.1.26420.103', str(tool), *map(str, inspected)]
            with (args.output / (prefix + '.json')).open('w') as stdout, (args.output / (prefix + '.stderr.log')).open('w') as stderr:
                done = subprocess.run(command, env=env, stdout=stdout, stderr=stderr)
            require(done.returncode == 0, 'Trusted metadata-only tool failed; streams retained')
            commands.append(dict(command=command, exitCode=done.returncode, toolSha256=sha(tool)))
        rows = json.loads((args.output / 'metadata.json').read_text())
        typed = json.loads((args.output / 'typed-query.json').read_text())
        descriptor = coreobj / 'ILLink.Descriptors.xml'
        verified = check(stages, rows, typed, descriptor)
        guid_text = (source / 'src/coreclr/inc/jiteeversionguid.h').read_text()
        guid = re.search(r'^constexpr GUID JITEEVersionIdentifier = \{ /\* ([0-9a-f-]+) \*/', guid_text, re.M).group(1)
        guid_bytes = uuid.UUID(guid).bytes_le
        guid_counts = {role: Path(completed[role]).read_bytes().count(guid_bytes)
                       for role in ('native', 'interpreter', 'targetJit', 'crossgen2', 'jitinterface', 'crossarchJit')}
        # Crossgen's managed GUID is initialized as fields, not a contiguous native GUID.
        require(all(guid_counts[role] > 0 for role in ('native', 'interpreter', 'targetJit', 'crossarchJit')),
                'Native compiler/runtime GUID bytes differ')
        native = json.loads((args.build / 'compile-assessment.json').read_text())
        symbol_image = Path(native['symbolImage'])
        require(sha(symbol_image) == native['symbolImageSha256'], 'Native symbols image changed')
        request = json.loads((args.build / 'request.json').read_text())
        nm = Path(request['ndk']) / 'toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-nm'
        symbols = subprocess.check_output([str(nm), '--demangle', str(symbol_image)], text=True)
        require(all(line in symbols.splitlines() for line in native['nativeSymbols']), 'Live terminal/finalizer entry symbols differ')
        (args.output / 'native-budget-symbols.txt').write_text('\n'.join(native['nativeSymbols']) + '\n')
        require(all(sha(path) == value for path, value in original_hashes.items()) and
                all(sha(completed[role]) == value for role,value in completed['criticalHashes'].items()), 'Products changed during read-only PE assessment')
        result.update(success=True, base=completed['base'], commit=completed['commit'], tree=TREE,
                      target='android.x64', configuration='Release', nativeMeterSize=64, nativeMeterAlignment=8, phaseAcquireLoadDefaultOff=True, derivedLedgerDefaultOff=True, corelibStages=3, managedCompilerMirrorStages=1, peStages=4, checks=verified,
                      actualPeHashes=original_hashes, descriptorSha256=sha(descriptor), commands=commands,
                      originalBuildReceiptSha256=sha(args.build / 'results.json'),
                      nativeBuildReceiptSha256=sha(args.build / 'results.json'),
                      sourceReceiptSha256=sha(args.build / 'source.json'), helperSha256=sha(__file__),
                      sourceProofSha256=sha(args.build / 'source-proof.json'), nativeSymbols=native['nativeSymbols'],
                      symbolImageSha256=sha(symbol_image), compilerGuid=guid, criticalGuidByteCounts=guid_counts,
                      rawHashes={p.name:sha(p) for p in args.output.iterdir() if p.is_file()},
                      scope='Exact derived-ledger retained PE private APIs, native import ABI and compiler GUID; trusted SDK metadata reading only; no Android target execution')
    except Exception:
        result['error'] = traceback.format_exc()
    write(args.output / 'results.json', result)
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
