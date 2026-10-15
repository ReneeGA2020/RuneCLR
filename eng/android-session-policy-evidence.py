#!/usr/bin/env python3
"""Archive completed Android build evidence; never build or execute an app."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'build', 'assessment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--failure', type=Path, action='append', default=[])
    parser.add_argument('--include-pe', action='store_true')
    args = parser.parse_args()
    root, build, assessment, output = [getattr(args, n).resolve() for n in
                                      ('root', 'build', 'assessment', 'output')]
    output.relative_to(root)
    result, source = read(build / 'results.json'), read(build / 'source.json')
    assessed = read(assessment / 'results.json')
    assert result['success'] and assessed['success']
    assert result['commit'] == source['commit'] == assessed['candidateCommit']
    assert result['executionVerified'] is False and assessed['executionVerified'] is False
    files = {}

    def add(path, expected=None):
        path = path.resolve()
        name = path.relative_to(root).as_posix()
        assert path.is_file() and '\n' not in name and '\r' not in name
        checksum = sha(path)
        if expected is not None:
            assert checksum == expected, name
        files[name] = {'path': name, 'sha256': checksum, 'sizeBytes': path.stat().st_size}

    for directory in [build, assessment, *args.failure]:
        for path in sorted(directory.glob('*')):
            if path.is_file():
                add(path)
    runtime = build / 'runtime'
    for name, checksum in source['sourceHashes'].items():
        add(runtime / name, checksum)
    compilation = read(assessment / 'compile-assessment.json')
    for row in compilation['roles'].values():
        add(Path(row['database']), row['databaseSha256'])
    obj = runtime / 'artifacts/obj/coreclr/android.x64.Checked'
    for directory, expected in [(obj, compilation['nativeCacheSha256']),
                                (obj / 'arm64', compilation['hostCacheSha256'])]:
        add(directory / 'CMakeCache.txt', expected)
    native = read(assessment / 'native-binary-assessment.json')
    add(Path(native['publicationProps']), native['publicationPropsSha256'])
    metadata = read(assessment / 'metadata-assessment.json')
    add(runtime / 'artifacts/obj/coreclr/System.Private.CoreLib/android.x64.Checked/ILLink.Descriptors.xml',
        metadata['descriptorSha256'])
    if args.include_pe:
        for row in metadata['stages']:
            add(Path(row['path']), row['sha256'])
    add(Path(__file__))
    output.mkdir(exist_ok=False)
    rows = [files[name] for name in sorted(files)]
    ledger = output / 'member-manifest.json'
    ledger.write_text(json.dumps({'files': rows}, indent=2) + chr(10))
    target = output / 'evidence.tar.gz'
    with tarfile.open(target, 'w:gz') as package:
        for path in [ledger, *[root / row['path'] for row in rows]]:
            package.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    with tarfile.open(target) as package:
        names = package.getnames()
        assert len(names) == len(set(names)) == len(rows) + 1
        for row in rows:
            assert hashlib.sha256(package.extractfile(row['path']).read()).hexdigest() == row['sha256']
    receipt = {'passed': True, 'candidateCommit': result['commit'], 'executionVerified': False,
               'archivePath': str(target), 'sha256': sha(target), 'sizeBytes': target.stat().st_size,
               'fileCount': len(rows) + 1, 'includeManagedPE': args.include_pe,
               'scope': 'Original configuration/logs/source/assessment; native binaries remain in the private build'}
    (output / 'results.json').write_text(json.dumps(receipt, indent=2) + chr(10))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
