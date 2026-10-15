#!/usr/bin/env python3
"""Prepare an isolated Darwin NDK from the official Google package manifest."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile

MANIFEST_URL = 'https://dl.google.com/android/repository/repository2-3.xml'
PACKAGE = 'ndk;27.2.12479018'


def checksum(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + chr(10))


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def logged(command, path):
    with path.open('w') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    try:
        manifest = out / 'repository2-3.xml'
        shutil.copy2(args.manifest, manifest)
        item = next(node for node in ET.parse(manifest).getroot() if node.attrib.get('path') == PACKAGE)
        archive = next(node for node in item.find('archives') if node.findtext('host-os') == 'macosx')
        complete = archive.find('complete')
        filename, size = complete.findtext('url'), int(complete.findtext('size'))
        expected, algorithm = complete.findtext('checksum'), complete.find('checksum').attrib['type']
        assert filename == 'android-ndk-r27c-darwin.zip' and algorithm == 'sha1'
        url = 'https://dl.google.com/android/repository/' + filename
        request = {'manifestUrl': MANIFEST_URL, 'manifestSha256': checksum(manifest),
                   'package': PACKAGE, 'host': 'macosx', 'url': url, 'sizeBytes': size,
                   'officialChecksumAlgorithm': algorithm, 'officialChecksum': expected,
                   'licenseReference': item.find('uses-license').attrib['ref'],
                   'driverSha256': checksum(Path(__file__)), 'startedUtc': utc(),
                   'installationScope': str(out), 'globalEnvironmentChanged': False}
        write(out / 'request.json', request)
        downloaded = out / filename
        logged(['curl', '--fail', '--location', '--connect-timeout', '20', '--max-time', '1200',
                url, '--output', str(downloaded)], out / 'download.log')
        assert downloaded.stat().st_size == size and checksum(downloaded, algorithm) == expected
        with zipfile.ZipFile(downloaded) as package:
            for name in package.namelist():
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts
                assert path.parts[0] == 'android-ndk-r27c'
        logged(['ditto', '-x', '-k', str(downloaded), str(out)], out / 'extract.log')
        ndk = out / 'android-ndk-r27c'
        properties = (ndk / 'source.properties').read_text()
        assert 'Pkg.Revision = 27.2.12479018' in properties
        clang = ndk / 'toolchains/llvm/prebuilt/darwin-x86_64/bin/clang'
        logged([str(clang), '--version'], out / 'clang-version.log')
        logged(['file', str(clang.resolve())], out / 'clang-file.log')
        result = {'success': True, 'package': PACKAGE, 'ndk': str(ndk),
                  'archiveSha256': checksum(downloaded), 'archiveSha1': expected, 'sizeBytes': size,
                  'clangSha256': checksum(clang.resolve()),
                  'toolchainSha256': checksum(ndk / 'build/cmake/android.toolchain.cmake'),
                  'sourcePropertiesSha256': checksum(ndk / 'source.properties'),
                  'clangExecutableVerified': True, 'globalEnvironmentChanged': False,
                  'endedUtc': utc()}
        write(out / 'results.json', result)
        print(json.dumps(result, indent=2), flush=True)
        return 0
    except Exception:
        write(out / 'results.json', {'success': False, 'error': traceback.format_exc(), 'endedUtc': utc()})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
