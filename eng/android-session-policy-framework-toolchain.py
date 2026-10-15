#!/usr/bin/env python3
"""Prepare a private Darwin SDK36/build-tools35.0.1 and pinned Temurin17 JDK.

No SDK manager, system installer, licence marker, global environment or device
operation is used. Downloads, metadata, checksums and real executable probes
are retained in a fresh explicitly named output directory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile
import time
import traceback
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

GOOGLE_MANIFEST = 'https://dl.google.com/android/repository/repository2-3.xml'
GOOGLE_SHA256 = '13dd16e8984cc6f3202a72c8eb269bd7ad03be4247b41b4412b315c5b8bf6d4b'
GOOGLE_PACKAGES = {
    'platforms;android-36': ('platform-36_r02.zip', 65878410, '2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576'),
    'build-tools;35.0.1': ('build-tools_r35.0.1_macosx.zip', 76857925, 'f4dda6855ddf1ea1a51ee3ab6587104bd0c1d727'),
}
JDK_VERSION = '17.0.20.1+1'
JDK_RELEASE = 'jdk-' + JDK_VERSION
JDK_NAME = 'OpenJDK17U-jdk_aarch64_mac_hotspot_17.0.20.1_1.tar.gz'
JDK_SIZE = 185851019
JDK_SHA256 = '196d13ba5f10414bef7f6a05a9b3f00edacb18ebacef2b99485db9e2ee18f0e8'
JDK_METADATA_URL = ('https://api.adoptium.net/v3/assets/version/' + quote(JDK_VERSION, safe='') +
                    '?architecture=aarch64&image_type=jdk&os=mac&vendor=eclipse&jvm_impl=hotspot&release_type=ga')
JDK_BINARY_URL = ('https://api.adoptium.net/v3/binary/version/' + quote(JDK_RELEASE, safe='') +
                  '/mac/aarch64/jdk/hotspot/normal/eclipse')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path, algorithm='sha256'):
    digest = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def run(command, log, env=None):
    with Path(log).open('w') as stream:
        status = subprocess.run([str(item) for item in command], env=env,
                                stdout=stream, stderr=subprocess.STDOUT).returncode
    Path(str(log) + '.exit').write_text(str(status) + '\n')
    require(status == 0, 'Command failed, retained log: ' + str(log))
    return {'command': [str(item) for item in command], 'exitCode': status,
            'log': str(log), 'logSha256': sha(log)}


def download(url, path, log, timeout=1200):
    return run(['curl', '--fail', '--location', '--connect-timeout', '30', '--max-time', str(timeout),
                '--dump-header', str(path) + '.headers', '--write-out',
                '\nRUNECLR_DOWNLOAD_EFFECTIVE_URL=%{url_effective}\nRUNECLR_DOWNLOAD_HTTP_CODE=%{http_code}\n',
                url, '--output', path], log)


def google_records(manifest):
    require(sha(manifest) == GOOGLE_SHA256, 'Official Google manifest differs from reviewed snapshot')
    root = ET.parse(manifest).getroot()
    result = []
    for package, pin in GOOGLE_PACKAGES.items():
        nodes = [node for node in root if node.attrib.get('path') == package]
        require(len(nodes) == 1, 'Google package metadata missing/ambiguous: ' + package)
        node = nodes[0]
        require(node.find('channelRef').attrib['ref'] == 'channel-0', 'Non-stable Google package')
        archives = [item for item in node.find('archives') if item.findtext('host-os') in (None, 'macosx')]
        require(len(archives) == 1, 'Darwin archive missing/ambiguous: ' + package)
        complete = archives[0].find('complete')
        filename = complete.findtext('url')
        size = int(complete.findtext('size'))
        checksum = complete.find('checksum')
        require(checksum.attrib['type'] == 'sha1' and (filename, size, checksum.text) == pin,
                'Google archive changed from reviewed version: ' + package)
        result.append({'package': package, 'filename': filename, 'size': size,
                       'checksumAlgorithm': 'sha1', 'checksum': checksum.text,
                       'url': 'https://dl.google.com/android/repository/' + filename,
                       'licenseReference': node.find('uses-license').attrib['ref']})
    return result


def jdk_record(metadata):
    assets = json.loads(Path(metadata).read_text())
    candidates = []
    for asset in assets:
        if asset.get('release_name') != JDK_RELEASE or asset.get('release_type') != 'ga' or asset.get('vendor') != 'eclipse':
            continue
        require(asset['version_data']['major'] == 17, 'Wrong JDK major')
        for binary in asset['binaries']:
            if all(binary.get(key) == value for key, value in {'architecture': 'aarch64', 'image_type': 'jdk',
                    'os': 'mac', 'jvm_impl': 'hotspot', 'heap_size': 'normal'}.items()):
                candidates.append(binary['package'])
    require(len(candidates) == 1, 'Pinned stable Temurin17 Darwin ARM64 archive missing/ambiguous')
    package = candidates[0]
    require((package['name'], package['size'], package['checksum']) == (JDK_NAME, JDK_SIZE, JDK_SHA256),
            'Adoptium primary metadata no longer matches reviewed archive')
    require(package['link'].startswith('https://github.com/adoptium/temurin17-binaries/releases/download/'),
            'Unexpected Adoptium release owner')
    return {'release': JDK_RELEASE, 'filename': JDK_NAME, 'size': JDK_SIZE,
            'checksumAlgorithm': 'sha256', 'checksum': JDK_SHA256, 'url': JDK_BINARY_URL,
            'primaryMetadataUrl': JDK_METADATA_URL, 'metadataPackageUrl': package['link'],
            'metadataChecksumUrl': package['checksum_link']}


def safe_zip(path):
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            require(not name.is_absolute() and '..' not in name.parts and '\\' not in item.filename,
                    'ZIP member escapes output: ' + item.filename)
            # SDK archives do not need symlink extraction; reject it rather than following an unexpected target.
            require((item.external_attr >> 16) & 0o170000 != 0o120000, 'Unexpected SDK ZIP symlink')


def safe_tar(path):
    with tarfile.open(path, 'r:gz') as archive:
        roots = set()
        for item in archive.getmembers():
            name = PurePosixPath(item.name)
            require(name.parts and not name.is_absolute() and '..' not in name.parts,
                    'TAR member escapes output: ' + item.name)
            roots.add(name.parts[0])
            require(not item.isdev() and not item.isfifo(), 'Unexpected special TAR member')
            if item.issym() or item.islnk():
                target = PurePosixPath(item.linkname)
                require(not target.is_absolute(), 'Absolute TAR link')
                combined = list(name.parent.parts) if item.issym() else []
                for part in target.parts:
                    if part == '..':
                        require(combined, 'TAR link escapes output')
                        combined.pop()
                    elif part != '.':
                        combined.append(part)
                require(combined and combined[0] == name.parts[0], 'TAR link escapes JDK bundle')
        require(len(roots) == 1, 'Ambiguous JDK bundle archive')


def prepare(args):
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    try:
        require(platform.system() == 'Darwin' and platform.machine() in ('arm64', 'aarch64'),
                'Executable probes require actual Darwin ARM64 host')
        manifest = out / 'repository2-3.xml'
        shutil.copy2(args.manifest, manifest)
        google = google_records(manifest)
        metadata = out / 'adoptium17-assets.json'
        metadata_fetch = download(JDK_METADATA_URL, metadata, out / 'adoptium-metadata-download.log', 120)
        jdk = jdk_record(metadata)
        request = {'schema': 'runeclr.android.framework-toolchain.request.v1', 'startedUtc': utc(),
                   'output': str(out), 'host': 'darwin-arm64', 'platformApi': 36, 'buildToolsVersion': '35.0.1',
                   'googleManifestUrl': GOOGLE_MANIFEST, 'googleManifestSha256': sha(manifest),
                   'adoptiumMetadataUrl': JDK_METADATA_URL, 'adoptiumMetadataSha256': sha(metadata),
                   'googlePackages': google, 'jdk': jdk, 'metadataFetch': metadata_fetch,
                   'driverSha256': sha(Path(__file__)), 'globalEnvironmentChanged': False,
                   'licenseAcceptanceWritten': False, 'sdkManagerUsed': False, 'systemInstallerUsed': False,
                   'deviceOperation': False}
        write(out / 'request.json', request)
        records = google + [jdk]

        def obtain(record):
            archive = out / record['filename']
            command = download(record['url'], archive, out / (record['filename'] + '.download.log'))
            require(archive.stat().st_size == record['size'], 'Downloaded archive size mismatch: ' + record['filename'])
            require(sha(archive, record['checksumAlgorithm']) == record['checksum'],
                    'Downloaded archive checksum mismatch: ' + record['filename'])
            return dict(record, path=str(archive), actualSha256=sha(archive), verified=True, download=command)

        with ThreadPoolExecutor(max_workers=3) as executor:
            obtained = list(executor.map(obtain, records))
        write(out / 'archives.json', obtained)
        sdk = out / 'sdk'
        extractions = []
        for record in google:
            archive = out / record['filename']
            safe_zip(archive)
            unpacked = out / ('unpacked-' + record['package'].replace(';', '-'))
            unpacked.mkdir()
            extractions.append(run(['ditto', '-x', '-k', archive, unpacked], out / (record['filename'] + '.extract.log')))
            marker = 'android.jar' if record['package'].startswith('platforms') else 'd8'
            sources = [path.parent for path in unpacked.rglob('source.properties') if (path.parent / marker).is_file()]
            require(len(sources) == 1, 'SDK archive package root missing/ambiguous')
            destination = sdk / ('platforms/android-36' if marker == 'android.jar' else 'build-tools/35.0.1')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(sources[0], destination)
            properties = (destination / 'source.properties').read_text()
            require(('AndroidVersion.ApiLevel=36' in properties.replace(' ', '') if marker == 'android.jar'
                     else 'Pkg.Revision=35.0.1' in properties.replace(' ', '')), 'SDK package revision/API mismatch')
        jdk_archive = out / JDK_NAME
        safe_tar(jdk_archive)
        jdk_root = out / 'jdk'
        jdk_root.mkdir()
        extractions.append(run(['tar', '-xzf', jdk_archive, '-C', jdk_root], out / 'jdk-extract.log'))
        homes = [path.parent for path in jdk_root.glob('*/Contents/Home/release')]
        require(len(homes) == 1, 'JDK Contents/Home missing/ambiguous')
        java_home = homes[0]
        release = (java_home / 'release').read_text()
        require('JAVA_VERSION="17.0.20.1"' in release and 'OS_ARCH="aarch64"' in release,
                'Extracted JDK release/architecture mismatch')
        env = dict(os.environ)
        env.update({'JAVA_HOME': str(java_home), 'ANDROID_SDK_ROOT': str(sdk),
                    'PATH': str(java_home / 'bin') + ':' + env.get('PATH', '/usr/bin:/bin')})
        tools = {'java': java_home / 'bin/java', 'javac': java_home / 'bin/javac',
                 'jar': java_home / 'bin/jar', 'd8': sdk / 'build-tools/35.0.1/d8'}
        probes = []
        for name, executable in tools.items():
            require(executable.is_file() and os.access(executable, os.X_OK), 'Tool is not executable: ' + str(executable))
            probe = run([executable, '-version' if name in ('java', 'javac') else '--version'],
                        out / (name + '-version.log'), env)
            probes.append(dict(probe, tool=name))
        properties_probe = run([tools['java'], '-XshowSettings:properties', '-version'], out / 'java-properties.log', env)
        require('os.arch = aarch64' in (out / 'java-properties.log').read_text(), 'Actual Java process is not ARM64')
        probes.append(dict(properties_probe, tool='java-properties'))
        probes.append(dict(run(['file', tools['java']], out / 'java-file.log'), tool='java-file'))
        critical = [*tools.values(), sdk / 'build-tools/35.0.1/lib/d8.jar', sdk / 'platforms/android-36/android.jar',
                    sdk / 'build-tools/35.0.1/source.properties', sdk / 'platforms/android-36/source.properties',
                    java_home / 'release', java_home / 'lib/modules', java_home / 'lib/server/libjvm.dylib']
        critical_files = [{'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size} for path in critical]
        result = {'schema': 'runeclr.android.framework-toolchain.v1', 'success': True,
                  'host': 'darwin-arm64', 'androidSdkRoot': str(sdk), 'javaHome': str(java_home),
                  'javaExecutable': str(tools['java']), 'javacExecutable': str(tools['javac']),
                  'jarExecutable': str(tools['jar']), 'd8Executable': str(tools['d8']),
                  'platformApi': 36, 'buildToolsVersion': '35.0.1', 'jdkMajor': 17, 'jdkRelease': JDK_RELEASE,
                  'criticalFiles': critical_files, 'probes': probes, 'extractions': extractions,
                  'requestSha256': sha(out / 'request.json'), 'archivesReceiptSha256': sha(out / 'archives.json'),
                  'metadataHashes': {'google': sha(manifest), 'adoptium': sha(metadata)},
                  'driverSha256': sha(Path(__file__)), 'globalEnvironmentChanged': False,
                  'licenseAcceptanceWritten': False, 'sdkManagerUsed': False, 'systemInstallerUsed': False,
                  'deviceOperation': False, 'frameworkBuildVerified': False, 'endedUtc': utc()}
        write(out / 'results.json', result)
        print(json.dumps(result, indent=2), flush=True)
        return 0
    except Exception:
        write(out / 'results.json', {'schema': 'runeclr.android.framework-toolchain.v1', 'success': False,
              'error': traceback.format_exc(), 'endedUtc': utc(), 'globalEnvironmentChanged': False,
              'deviceOperation': False, 'frameworkBuildVerified': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return prepare(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
