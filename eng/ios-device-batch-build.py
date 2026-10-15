#!/usr/bin/env python3
"""Build the frozen batch source for an unsigned iOS device runtime, without device operations."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import types

WORKFLOW_SHA = '218150b10355f96fbd6d6f4442ef3cbb2f9ec83f944f1b1f271ddf46f411f771'
PARENT_SHA = '3ed2bae44ba4d9f8e021b554d0702671a7b2671a6157a39b18521dd9453aa613'
BATCH_SHA = 'de0b4215f210a44023c3a3a021563b502c46fd2dc7e0dec7e06ea109a64615da'
TARGET = 'ios.arm64.Release'
TRANSFORMS = []


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapt(path, expected_sha, functions, replacements, expected_counts, replace_parent=False):
    need(sha(path) == expected_sha, 'Frozen build helper changed: ' + str(path))
    tree = ast.parse(Path(path).read_text())
    counts = {key: 0 for key in replacements}
    calls = []

    class Target(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                for old, new in replacements.items():
                    if old in node.value:
                        counts[old] += node.value.count(old)
                        node.value = node.value.replace(old, new)
            return node

        def visit_Attribute(self, node):
            if replace_parent and isinstance(node.value, ast.Name) and node.value.id == 'parent' and node.attr == 'assess_product':
                calls.append(1)
                return ast.copy_location(ast.Name(id='_device_assess_product', ctx=node.ctx), node)
            return self.generic_visit(node)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            Target().visit(node)
    need(counts == expected_counts, 'Pinned function-level target adaptation differs: ' + repr(counts))
    need(len(calls) == int(replace_parent), 'Pinned product assessment call adaptation differs')
    namespace = {'__name__': 'frozen_device_' + Path(path).stem, '__file__': str(Path(__file__).resolve())}
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), namespace)
    module = types.SimpleNamespace(**namespace)
    TRANSFORMS.append({'helperSha256': expected_sha, 'functions': sorted(functions),
                       'replacements': replacements, 'counts': counts, 'productCallReplacements': len(calls)})
    return module


def macho_device(path):
    data = Path(path).read_bytes()
    need(len(data) >= 32 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c),
         'Actual device runtime is not thin ARM64 Mach-O')
    commands, size = struct.unpack_from('<II', data, 16)
    limit = 32 + size
    need(limit <= len(data), 'Mach-O command table exceeds actual bytes')
    cursor, versions = 32, []
    for _ in range(commands):
        need(cursor + 8 <= limit, 'Mach-O command header truncated')
        command, length = struct.unpack_from('<II', data, cursor)
        need(length >= 8 and cursor + length <= limit, 'Mach-O command length differs')
        if command == 0x32:
            need(length >= 24, 'Mach-O build-version command truncated')
            platform, minimum, sdk, tools = struct.unpack_from('<IIII', data, cursor + 8)
            need(length == 24 + tools * 8, 'Mach-O build tools table differs')
            versions.append({'platform': platform, 'minimum': minimum, 'sdk': sdk, 'tools': tools})
        cursor += length
    need(cursor == limit and len(versions) == 1, 'Expected exactly one actual LC_BUILD_VERSION')
    version = versions[0]
    need(version['platform'] == 2 and version['minimum'] == (15 << 16 | 3 << 8),
         'Actual Mach-O must target iOS device platform2/minimum15.3')
    return dict(version, architecture='arm64', platformName='ios-device', sha256=sha(path))


def helpers(args):
    parent = adapt(args.parent_driver, PARENT_SHA, {'assess_product'},
                   {'iossimulator.arm64.Release': TARGET, 'iphonesimulator': 'iphoneos',
                    '-mios-simulator-version-min=15.3': '-miphoneos-version-min=15.3',
                    'iPhoneSimulator': 'iPhoneOS'},
                   {'iossimulator.arm64.Release': 2, 'iphonesimulator': 1,
                    '-mios-simulator-version-min=15.3': 1, 'iPhoneSimulator': 1})
    workflow = adapt(args.workflow, WORKFLOW_SHA, {'build', 'assess_batch', 'environment'},
                     {'iossimulator.arm64.Release': TARGET, 'iossimulator.arm64': 'ios.arm64',
                      'iossimulator': 'ios', 'iphonesimulator': 'iphoneos'},
                     {'iossimulator.arm64.Release': 3, 'iossimulator.arm64': 2,
                      'iossimulator': 1, 'iphonesimulator': 2}, replace_parent=True)

    def device_assess(source, product, out, inner_args, commit):
        platform = macho_device(product / 'libcoreclr.dylib')
        result = parent.assess_product(source, product, out, inner_args, commit)
        workflow.write(out / 'device-platform-assessment.json', {'passed': True, 'native': platform,
                       'adaptations': TRANSFORMS, 'runtimeExecuted': False, 'physicalDeviceExecuted': False})
        return dict(result, deviceMachO=platform, deviceBuildOnly=True, physicalDeviceExecuted=False)

    workflow.build.__globals__['_device_assess_product'] = device_assess
    original_preserved = workflow.preserved

    def preserved(root):
        result = original_preserved(root)
        for child, target, native in [('ios-batch-interval-release-20261015-attempt1', 'iossimulator.arm64.Release', 'libcoreclr.dylib'),
                                      ('android-batch-interval-release-20261015-attempt1', 'android.x64.Release', 'libcoreclr.so')]:
            source = root / child / 'runtime'
            need(workflow.clean(source), 'Current matching simulator/Android source became dirty')
            product = source / 'artifacts/bin/coreclr' / target
            for relative in [native, 'IL/System.Private.CoreLib.dll', 'arm64/crossgen2/crossgen2']:
                path = product / relative
                result[str(path)] = workflow.sha(path)
        app = root / 'ios-timing-application-20261015-attempt1/app/Session.app'
        result.update({str(app / relative): digest for relative, digest in workflow.inventory(app).items()})
        return result

    workflow.build.__globals__['preserved'] = preserved
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['preflight', 'build'])
    for name in ['root', 'output', 'patches', 'source-proof', 'source-bundle', 'parent-driver',
                 'metadata-tool', 'batch-assessor', 'workflow']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--build-slot-granted', action='store_true')
    args = parser.parse_args()
    args.batch_assessor_sha256 = BATCH_SHA
    args.prepare_only = False
    need(sys.platform == 'darwin', 'Configured Mac required for actual device build preflight')
    need(shutil.disk_usage(args.root).free > 60 * 1024**3, 'Device private build requires at least60GiB free')
    workflow = helpers(args)
    proof = workflow.frozen_proof(args)
    source = args.root / 'ios-batch-interval-release-20261015-attempt1/runtime'
    source_hashes = workflow.source_identity(source, proof)
    original = args.root / 'runtime'
    need(workflow.capture(['git', '-C', original, 'rev-parse', 'HEAD']) == workflow.BASE and workflow.clean(original),
         'Official baseline source changed')
    need(not args.output.exists(), 'Preserve prior device build attempts; output must be fresh')
    environment = workflow.environment(args.root)
    need(workflow.capture([original / '.dotnet/dotnet', '--version']) == workflow.SDK_VERSION, 'Private SDK differs')
    if args.phase == 'preflight':
        print(json.dumps({'passed': True, 'sourceCommit': workflow.COMMIT, 'sourceTree': workflow.TREE,
                          'sourceFilesVerified': len(source_hashes), 'target': TARGET, 'adaptations': TRANSFORMS,
                          'environment': environment, 'sourceBuildExecuted': False,
                          'signingChanged': False, 'deviceExecuted': False}, indent=2))
        return 0
    try:
        return workflow.build(args)
    except Exception as error:
        if getattr(args, 'created_output', False):
            import traceback
            workflow.write(args.output / 'results.json', {'success': False, 'target': TARGET, 'executionVerified': False,
                           'physicalDeviceExecuted': False, 'error': str(error)})
            (args.output / 'driver-failure.txt').write_text(traceback.format_exc())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
