"""Recheck actual derived metadata and reject five altered observer results."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('driver', 'metadata', 'build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Preserve previous control result')
    spec = importlib.util.spec_from_file_location('derived_metadata', args.driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = json.loads((args.metadata / 'results.json').read_text())
    if not result['success'] or result['helperSha256'] != sha(args.driver):
        raise RuntimeError('Actual metadata result/helper binding differs')
    stages = [Path(value) for value in result['commands'][0]['command'][5:]]
    rows = json.loads((args.metadata / 'metadata.json').read_text())
    typed = json.loads((args.metadata / 'typed-query.json').read_text())
    descriptor = args.build / 'runtime/artifacts/obj/coreclr/System.Private.CoreLib/android.x64.Release/ILLink.Descriptors.xml'
    positive = module.check(stages, rows, typed, descriptor)
    if positive != result['checks']:
        raise RuntimeError('Actual positive recheck differs')
    controls = []
    for name in ('private-family-missing', 'visibility', 'factory-signature',
                 'typed-owner-hidden-error', 'compiler-bit33'):
        changed_rows, changed_typed = copy.deepcopy(rows), copy.deepcopy(typed)
        if name == 'private-family-missing':
            changed_rows[0]['methods'] = [method for method in changed_rows[0]['methods']
                    if method['name'] != 'RuneCLR_CreateTerminalPrototype']
        elif name == 'visibility':
            method = next(method for method in changed_rows[0]['methods']
                          if method['name'] == 'RuneCLR_CreateTerminalPrototype')
            method['attributes'] = 'Public'
        elif name == 'factory-signature':
            method = next(method for method in changed_rows[0]['methods']
                          if method['nativeEntry'] == 'AssemblyNative_InitializeTerminalPrototypeLoadContext')
            method['signatureHex'] = '000318180A0F18'
        elif name == 'typed-owner-hidden-error':
            changed_typed[0]['queries'][0]['hiddenErrorStatus'] = True
        else:
            field = next(field for field in changed_rows[3]['fields']
                         if field['name'] == 'CORJIT_FLAG_INTERPRET_REQUIRED')
            field['value'] = 32
        try:
            module.check(stages, changed_rows, changed_typed, descriptor)
        except RuntimeError as error:
            controls.append(dict(name=name, rejected=True, reason=str(error)))
        else:
            raise RuntimeError('Altered result accepted: ' + name)
    receipt = dict(success=True, positivePassed=True, controls=controls,
                   metadataReceiptSha256=sha(args.metadata / 'results.json'),
                   driverSha256=sha(args.driver), helperSha256=sha(__file__),
                   executionVerified=False,
                   scope='Actual positive PE observer recheck plus altered observer results; no target execution')
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
