#!/usr/bin/env python3
"""Bind the frozen Android APK driver to the accepted counter increment."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess

PARENT_SHA = '6d0a6b9714060e942f603181bf695e988f23e1efa838bc6503caa6a7a1ff4419'
COMMIT = '112e97408de1ae1c2a6cbd2967dcd250cd2d491c'
TREE = '91673a7980bda79006259e525741fecb04324444'
PROOF_SHA = '6dea87eae1bbbb3142319707c2af4f5cca142a5bc1e4fe8ef665d8a93a2e4d48'
INPUT_SHA = 'ccf1ece09ef7d8f33a4da685234222526426f4712af1b1a5b2308de0dc97d685'
METADATA_TOOL_SHA = '57934b53bc3665d3ad1b7f2def5acd084cdb0bf1d089f1f23a774d90d58aaaa6'
CRITICAL = {
    'native': 'd2e2b148216d14bd7f05175a4c61c413673def17a3781e723a83ca940ba859d6',
    'interpreter': '045f426c2091b0445fd976324d93901a14e734413bd3812b78b234674c97bbfa',
    'targetJit': '355886d55ab849b618059f83e317710ef5af4251f5cd4f27ce1e98e811ca1735',
    'corelib': '54ff907b0499cff7999449c6b93739e2a7703f9822f273fffcb1c725c32e2424',
    'crossgen2': '1c9caeb18a56fd1c2cfc678a6fc2dee378ea0156cde919c3d8789d91d8144b68',
    'jitinterface': 'a02512cf8c225015ef94a3f6591fd99e82033b96e8c36dce9d2b6f421103578e',
    'crossarchJit': 'b3f99520968c0763c38a4d353f2ac248f93e59d81e2d613a62514c73d8128469',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


PARENT = Path(__file__).with_name('android-session-budget-apk.py')
require(sha(PARENT) == PARENT_SHA, 'Frozen parent APK driver changed')
spec = importlib.util.spec_from_file_location('frozen_android_budget_apk', PARENT)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.COMMIT, base.TREE = COMMIT, TREE
# Parent phases freeze the actual entry driver, with the parent saved alongside.
base.__file__ = __file__


def validate_inputs(root):
    root = Path(root).resolve()
    require(sha(root / 'input-manifest.json') == INPUT_SHA, 'Frozen mobile input manifest changed')
    manifest = base.load(root / 'input-manifest.json')
    require(len(manifest['files']) == 6 and len(manifest['sourceHashes']) == 30
            and manifest['expectedContexts'] == 73, 'Frozen mobile input topology changed')
    for name, value in manifest['files'].items():
        require(sha(root / name) == value, 'Frozen author/trusted DLL changed: ' + name)
    for name, value in manifest['sourceHashes'].items():
        require(sha(root / 'source' / name) == value, 'Frozen input source changed: ' + name)


def validate_layout(root):
    root = Path(root).resolve()
    layout = base.load(root / 'layout.json')
    require(layout['success'] and layout['base'] == base.BASE and layout['commit'] == COMMIT
            and layout['tree'] == TREE, 'Minimal increment layout source differs')
    proof_path = root / 'receipts/source-proof.json'
    require(sha(proof_path) == PROOF_SHA, 'Exact increment proof bytes differ')
    proof = base.load(proof_path)
    require(proof['exactIncrementVerified'] and proof['oldMobileDeltaOnlyMeter']
            and proof['tree'] == TREE and len(proof['sourceHashes']) == 37, 'Increment composition differs')
    review_path = root / 'receipts/native-build-review.json'
    review = base.load(review_path)
    require(review['success'] and review['buildExit'] == 0 and review['commit'] == COMMIT
            and review['tree'] == TREE and review['sourceTrackedClean'], 'Matching native build differs')
    require(review['criticalHashes'] == layout['critical7'] == CRITICAL, 'Exact new core products differ')
    require(layout['buildReviewSha256'] == sha(review_path), 'Native review receipt stamp differs')
    metadata_path = root / 'receipts/corelib-metadata.json'
    require(layout['metadataReviewSha256'] == sha(metadata_path), 'CoreLib metadata receipt stamp differs')
    metadata = base.load(metadata_path)
    require(metadata['success'] and metadata['commit'] == COMMIT and metadata['tree'] == TREE,
            'CoreLib metadata source differs')
    require(layout['corelibComponentMetadataUnchanged'] and layout['coreCriticalUnchanged']
            and layout['allElfDependenciesResolved'], 'Matching framework ABI/native gates missing')
    require(layout['inputManifestSha256'] == INPUT_SHA, 'Framework mobile input stamp differs')


def validate_state(output):
    output = Path(output)
    state = base.load(output / 'state.json')
    require(state['runtimeCommit'] == COMMIT and state['runtimeTree'] == TREE
            and state['inputManifestSha256'] == INPUT_SHA, 'Owned new APK source differs')
    require(state['driverSha256'] == sha(__file__) and state['parentDriverSha256'] == PARENT_SHA
            and state['sourceProofSha256'] == PROOF_SHA, 'Owned frozen driver/proof differs')
    require(sha(output / PARENT.name) == PARENT_SHA, 'Owned frozen parent driver differs')
    for name, key in [('libcoreclr.so', 'native'), ('libclrinterpreter.so', 'interpreter'), ('libclrjit.so', 'targetJit')]:
        require(state['appHashes'][name] == CRITICAL[key], 'Owned APK native source differs')


original_bridge, original_apk = base.bridge, base.apk
original_install, original_run = base.install, base.run


def bridge(args):
    validate_inputs(args.inputs)
    validate_layout(args.layout)
    require(sha(args.metadata_inspector) == METADATA_TOOL_SHA, 'Frozen metadata inspector changed')
    layout = base.load(args.layout / 'layout.json')
    rows = [row for row in layout['files'] if row.get('inputSha256') is not None]
    expected = {Path(row['path']).name: row['inputSha256'] for row in rows}
    inputs = args.layout.parent / 'input'
    require(len(expected) == len(rows) == layout['compositeInputCount']
            and {p.name for p in inputs.glob('*.dll')} == set(expected), 'Actual composite input set differs')
    for name, value in expected.items():
        require(sha(inputs / name) == value, 'Actual composite IL input changed: ' + name)
    source = args.runtime.resolve()
    for revision, expected in [('HEAD', COMMIT), ('HEAD^{tree}', TREE)]:
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', revision], text=True).strip()
        require(actual == expected, 'Live bridge runtime source differs')
    require(not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain',
                                        '--untracked-files=no'], text=True).strip(), 'Live source is dirty')
    original_bridge(args)
    shutil.copy2(PARENT, args.output / PARENT.name)


def apk(args):
    validate_inputs(args.inputs)
    validate_layout(args.layout)
    original_apk(args)
    shutil.copy2(PARENT, args.output / PARENT.name)
    state_path = args.output / 'state.json'
    state = base.load(state_path)
    state.update(parentDriverSha256=PARENT_SHA, sourceProofSha256=PROOF_SHA)
    base.write(state_path, state)


def install(args):
    validate_state(args.output)
    validate_inputs(args.inputs)
    original_install(args)


def run(args):
    validate_state(args.output)
    original_run(args)


base.bridge, base.apk, base.install, base.run = bridge, apk, install, run

if __name__ == '__main__':
    base.main()
