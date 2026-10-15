#!/usr/bin/env python3
"""Check benchmark provenance guards without launching CLR or timing workloads."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    adapter = ROOT / 'eng/benchmark-derived-ledger-overhead.py'
    spec = importlib.util.spec_from_file_location('derived_benchmark_guard', adapter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    legacy = module.legacy_module()
    binding, inputs = legacy.freeze_build_binding(module.RUNTIME, module.BUILD / 'layout',
                                                  'Release', module.BUILD, output, module.COMMIT)
    module.validate_build_binding(binding, binding['candidateValidation'])
    controls = []
    def reject(name, value, edit, verify):
        changed = copy.deepcopy(value)
        edit(changed)
        try:
            verify(changed)
        except RuntimeError as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise RuntimeError('Corrupted binding accepted: ' + name)
    edits = {
        'critical-product': lambda x: x['criticalProductHashes'].__setitem__('coreclr.dll', '0' * 64),
        'build-feature': lambda x: x['cmakeFeatures'].__setitem__('FEATURE_INTERPRETER', '0'),
        'metadata-hash': lambda x: x['metadataHashes'].__setitem__('provenance/build-result.json', '0' * 64),
        'metadata-omitted': lambda x: x['metadataHashes'].pop('provenance/build-result.json'),
        'metadata-extra': lambda x: x['metadataHashes'].__setitem__('provenance/extra', '0' * 64),
        'configuration': lambda x: x.__setitem__('configuration', 'Checked'),
        'evidence-path': lambda x: x.__setitem__('buildEvidencePath', str(ROOT)),
        'checker': lambda x: x.__setitem__('candidateCheckerSha256', '0' * 64),
        'candidate': lambda x: x.__setitem__('actualSourceCommit', module.BASELINE),
        'version': lambda x: x.__setitem__('version', 1),
    }
    for name, edit in edits.items():
        reject(name, binding, edit, lambda x: module.validate_build_binding(x, binding['candidateValidation']))
    framework = module.BUILD / 'layout/shared/Microsoft.NETCore.App/12.0.0'
    core = str((framework / 'coreclr.dll').resolve())
    pdb = str((framework / 'coreclr.pdb').resolve())
    witness = {'candidateCommit': module.COMMIT,
               'buildResultSha256': sha(module.BUILD / 'build-result.json'),
               'layoutReceiptSha256': sha(module.BUILD / 'layout-receipt.json'),
               'boundFiles': {str((framework / name).resolve()): sha(framework / name)
                              for name in ('coreclr.dll', 'coreclr.pdb', 'clrinterpreter.dll',
                                           'clrjit.dll', 'System.Private.CoreLib.dll')}}
    module.validate_live_build(witness)
    for name, edit in {
        'witness-candidate': lambda x: x.__setitem__('candidateCommit', module.BASELINE),
        'witness-build': lambda x: x.__setitem__('buildResultSha256', '0' * 64),
        'witness-layout': lambda x: x.__setitem__('layoutReceiptSha256', '0' * 64),
        'witness-native-hash': lambda x: x['boundFiles'].__setitem__(core, '0' * 64),
        'witness-native-missing': lambda x: x['boundFiles'].pop(core),
        'witness-symbol-hash': lambda x: x['boundFiles'].__setitem__(pdb, '0' * 64),
    }.items():
        reject(name, witness, edit, module.validate_live_build)
    paths = (adapter, ROOT / 'eng/audit-derived-ledger-overhead.py',
             ROOT / 'eng/compare-derived-ledger-overhead.py', Path(__file__).resolve())
    for path in paths:
        ast.parse(path.read_text())
        (output / path.name).write_bytes(path.read_bytes())
    report = {'passed': True, 'preparedOnly': True, 'runtimeExecuted': False,
              'benchmarkExecuted': False, 'liveWitnessGenerated': False,
              'adapterHashes': {str(p.relative_to(ROOT)): sha(p) for p in paths},
              'actualBuildBinding': binding, 'corruptionControls': controls,
              'scope': 'Actual build and synthetic native cross-binding guard checks only; no live witness or timing.'}
    (output / 'results.json').write_text(json.dumps(report, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({'passed': True, 'buildBindingControlsRejected': 10,
                      'nativeCrossBindingControlsRejected': 6, 'benchmarkExecuted': False}, indent=2))

if __name__ == '__main__':
    main()
