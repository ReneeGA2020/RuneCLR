#!/usr/bin/env python3
"""Generate one non-collectible iOS-device R2R owner from pinned source, after a signed install.

Fixes M1/M2/M3/M6/M7 of REVIEW-IMPL:
  M1 compiles Update/Private/IlOnlyHelper from source with a fresh nonce+version stamp
  M2 emits a closed deployable manifest including the crossgen-rewritten component
  M3 pins the shared Contract identity and refuses any other bytes
  M6 validates a real install receipt (device, host digest, timestamps, archive)
  M7 requires an external section-defined _RTR_HEADER
"""
import argparse, hashlib, json, shutil, struct, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIN_OS = '15.3'
SOURCE_FILES = ('Business.cs', 'Update.cs', 'PrivateLogic.cs', 'IlOnlyHelper.cs')
VERSION_FILE = {'A': 'PrivateVersion.cs', 'B': 'PrivateVersionB.cs'}


def utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def app_digest(app):
    app = Path(app)
    entries = [{'path': str(p.relative_to(app)), 'sha256': sha(p), 'size': p.stat().st_size}
               for p in sorted(app.rglob('*')) if p.is_file()]
    return hashlib.sha256(''.join(e['path'] + chr(0) + e['sha256'] + chr(0) + str(e['size']) + chr(10)
                                  for e in entries).encode()).hexdigest(), entries


def run(argv, log):
    with open(log, 'wb') as stream:
        process = subprocess.run([str(a) for a in argv], stdout=stream, stderr=subprocess.STDOUT)
    return process.returncode


def pe_mvid(path):
    import struct
    data = Path(path).read_bytes()
    e = struct.unpack_from('<I', data, 0x3C)[0]
    coff = e + 4
    sections = struct.unpack_from('<H', data, coff + 2)[0]
    opt_size = struct.unpack_from('<H', data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from('<H', data, opt)[0]
    directory = opt + (112 if magic == 0x20B else 96)
    clr_rva = struct.unpack_from('<I', data, directory + 14 * 8)[0]
    table = opt + opt_size
    def off(rva):
        for i in range(sections):
            b = table + i * 40
            vs, va = struct.unpack_from('<II', data, b + 8)
            rs, rp = struct.unpack_from('<II', data, b + 16)
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        raise SystemExit('rva unmapped')
    cor = off(clr_rva)
    meta = off(struct.unpack_from('<I', data, cor + 8)[0])
    vlen = struct.unpack_from('<I', data, meta + 12)[0]
    cur = meta + 16 + vlen + 2
    count = struct.unpack_from('<H', data, cur)[0]
    cur += 2
    for _ in range(count):
        offset, size = struct.unpack_from('<II', data, cur)
        cur += 8
        end = data.index(b'\x00', cur)
        name = data[cur:end].decode('ascii', 'replace')
        cur = (end + 4) & ~3
        if name == '#GUID':
            return data[meta + offset:meta + offset + 16].hex()
    return ''


def run_logged(argv, out, name):
    import datetime, json as _json
    from datetime import timezone
    started = datetime.datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    request = {'argv': [str(a) for a in argv], 'startedUtc': started}
    (out / (name + '.request.json')).write_text(_json.dumps(request, indent=2) + chr(10), encoding='ascii')
    with open(out / (name + '.stdout'), 'wb') as stream:
        process = subprocess.Popen([str(a) for a in argv], stdout=stream, stderr=subprocess.STDOUT)
        pid = process.pid
        exit_code = process.wait()
    receipt = dict(request, pid=pid, exitCode=exit_code,
                   endedUtc=datetime.datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    (out / (name + '.process.json')).write_text(_json.dumps(receipt, indent=2) + chr(10), encoding='ascii')
    return exit_code


def canonical_mvid(raw):
    """Canonical Guid "D" text from the 16 raw metadata #GUID bytes.

    The bytes are stored in metadata-heap order (the first three fields are little-endian);
    formatting them as-is is a different Guid, so decode first. Raw comparisons elsewhere keep
    using the raw bytes; this helper only produces the host-facing text form.
    """
    if isinstance(raw, str):
        raw = bytes.fromhex(raw)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != 16:
        raise ValueError('raw MVID must be 16 bytes')
    a = int.from_bytes(raw[0:4], 'little')
    b = int.from_bytes(raw[4:6], 'little')
    c = int.from_bytes(raw[6:8], 'little')
    return '%08x-%04x-%04x-%s-%s' % (a, b, c, raw[8:10].hex(), raw[10:16].hex())


def compile_logged(out, name, sources, refs, target_path, sdk, csc):
    argv = [sdk, csc, '-nologo', '-noconfig', '-nostdlib+', '-optimize+', '-deterministic+',
            '-target:library', '-out:' + str(target_path)]
    argv += ['-r:' + str(r) for r in refs] + [str(s) for s in sources]
    return run_logged(argv, out, name)


def component_header(path, owner_name=None):
    """Parse the real ReadyToRun header of a composite component.

    READYTORUN_HEADER: signature +0, major +4, minor +6, flags +8,
    numberOfSections +12, entrySize +14, sections +16. Section type 116 is
    OwnerCompositeExecutable and its RVA points at the owner file name.
    """
    import struct
    data = Path(path).read_bytes()
    e = struct.unpack_from('<I', data, 0x3C)[0]
    coff = e + 4
    nsect = struct.unpack_from('<H', data, coff + 2)[0]
    opt_size = struct.unpack_from('<H', data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from('<H', data, opt)[0]
    directory = opt + (112 if magic == 0x20B else 96)
    clr_rva = struct.unpack_from('<I', data, directory + 14 * 8)[0]
    table = opt + opt_size

    def off(rva):
        for index in range(nsect):
            b = table + index * 40
            vs, va = struct.unpack_from('<II', data, b + 8)
            rs, rp = struct.unpack_from('<II', data, b + 16)
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        return None

    empty = {'componentBit': False, 'flags': None, 'ownerComposite': None,
             'sections': 0, 'entrySize': 0}
    cor = off(clr_rva)
    if cor is None:
        return empty
    native_rva = struct.unpack_from('<I', data, cor + 64)[0]
    if native_rva == 0:
        return empty
    native_off = off(native_rva)
    if native_off is None:
        return empty
    if struct.unpack_from('<I', data, native_off)[0] != 0x00525452:
        return empty
    flags = struct.unpack_from('<I', data, native_off + 8)[0]
    count = struct.unpack_from('<H', data, native_off + 12)[0]
    entry_size = struct.unpack_from('<H', data, native_off + 14)[0] or 12
    owner = None
    for index in range(count):
        base = native_off + 16 + index * entry_size
        if entry_size == 0 or base + 12 > len(data):
            break
        stype, srva, ssize = struct.unpack_from('<III', data, base)
        if stype != 116:
            continue
        section_off = off(srva)
        if section_off is None:
            continue
        raw = data[section_off:section_off + ssize] if ssize else data[section_off:]
        end = raw.find(bytes([0]))
        if end >= 0:
            raw = raw[:end]
        owner = raw.decode('utf-8', 'replace')
        break
    return {'componentBit': bool(flags & 0x20), 'flags': flags, 'ownerComposite': owner,
            'sections': count, 'entrySize': entry_size}


def macho_fields(path):
    data = Path(path).read_bytes()
    ncmds = struct.unpack_from('<I', data, 16)[0]
    off = 32
    platform = None
    uuid = None
    text = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 0x32:
            platform = struct.unpack_from('<III', data, off + 8)[0]
        if cmd == 0x1B:
            uuid = data[off + 8:off + 24].hex()
        if cmd == 0x19:
            segname = data[off + 8:off + 24].split(b'\x00')[0].decode('ascii', 'replace')
            if segname == '__TEXT':
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, off + 24)
                text = {'vmaddr': vmaddr, 'vmsize': vmsize, 'fileoff': fileoff, 'filesize': filesize}
        off += size
    return {'platform': platform, 'uuid': uuid, 'text': text}


def exported_rtr_header(path):
    data = Path(path).read_bytes()
    ncmds = struct.unpack_from('<I', data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == 0x2:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, off + 8)
            for index in range(nsyms):
                n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from('<IBBhQ', data, symoff + index * 16)
                end = data.index(b'\x00', stroff + n_strx)
                if data[stroff + n_strx:end] == b'_RTR_HEADER':
                    external = bool(n_type & 0x01)
                    defined = (n_type & 0x0E) == 0x0E and n_sect != 0
                    if not external or not defined or n_value == 0:
                        raise SystemExit('_RTR_HEADER is not an external section symbol')
                    return {'symbol': '_RTR_HEADER', 'value': n_value, 'section': n_sect}
        off += size
    raise SystemExit('owner has no exported _RTR_HEADER')


def validate_receipt(receipt_path, host_app, started, bundle_id, device_udid):
    receipt = json.loads(Path(receipt_path).read_text())
    errors = []
    if receipt.get('status') != 'installed' or receipt.get('installed') is not True or receipt.get('signed') is not True:
        errors.append('receipt is not a signed install success')
    if receipt.get('bundleId') != bundle_id:
        errors.append('receipt bundle id differs')
    if receipt.get('deviceUdid') != device_udid:
        errors.append('receipt device differs')
    if receipt.get('platform') != 2:
        errors.append('receipt platform is not iOS device (2)')
    installed = receipt.get('installedUtc') or ''
    if not installed or installed >= started:
        errors.append('install timestamp is missing or not before generation')
    digest, _entries = app_digest(host_app)
    if receipt.get('appDigestSha256') != digest:
        errors.append('receipt app digest does not match the signed host app')
    raw_path = receipt.get('rawReceiptPath') or ''
    raw_sha = receipt.get('rawReceiptSha256') or ''
    if not raw_path or not raw_sha:
        errors.append('raw CoreDevice receipt path/hash missing')
    elif not Path(raw_path).is_file():
        errors.append('raw CoreDevice receipt file missing')
    elif sha(raw_path) != raw_sha:
        errors.append('raw CoreDevice receipt hash mismatch')
    else:
        try:
            raw = json.loads(Path(raw_path).read_text())
            info = raw.get('info') or {}
            result = raw.get('result') or {}
            succeeded = raw.get('success') is True or info.get('outcome') == 'success'
            installed = result.get('installedApplications') or []
            raw_bundle = raw.get('bundleId') or (installed[0].get('bundleID') if installed else None)
            arguments = info.get('arguments') or []
            raw_device = raw.get('deviceUdid')
            if not raw_device and '--device' in arguments:
                raw_device = arguments[arguments.index('--device') + 1]
            if not succeeded or raw_bundle != bundle_id:
                errors.append('raw CoreDevice receipt success/bundle mismatch')
            if raw_device != device_udid:
                errors.append('raw CoreDevice receipt device mismatch')
        except Exception:
            errors.append('raw CoreDevice receipt is not valid JSON')
    archive = receipt.get('archive') or {}
    if not archive.get('path') or not archive.get('sha256'):
        errors.append('receipt archive path/hash missing')
    if errors:
        raise SystemExit('install receipt rejected: ' + '; '.join(errors))
    return receipt, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework-root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--crossgen2', type=Path, default=None)
    parser.add_argument('--dotnet', type=Path, default=None)
    parser.add_argument('--csc', type=Path, default=None)
    parser.add_argument('--udid', required=True, help='target device UDID')
    parser.add_argument('--bundle-id', required=True)
    parser.add_argument('--min-os', default=DEFAULT_MIN_OS)
    parser.add_argument('--version', choices=('A', 'B'), required=True)
    parser.add_argument('--sources', type=Path, default=PACKAGE_ROOT / 'source/update-src')
    parser.add_argument('--host-app', type=Path, required=True)
    parser.add_argument('--install-receipt', type=Path, required=True)
    parser.add_argument('--nonce', default=None, help='32 hex; generated when omitted')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    started = utc()
    framework = args.framework_root.resolve()
    runtime = args.runtime_root.resolve()
    crossgen2 = (args.crossgen2 or (runtime / 'artifacts/bin/coreclr/ios.arm64.Release/arm64/crossgen2/crossgen2')).resolve()
    sdk = (args.dotnet or (runtime / '.dotnet/dotnet')).resolve()
    csc = (args.csc or (runtime / '.dotnet/sdk/11.0.100-rc.1.26420.103/Roslyn/bincore/csc.dll')).resolve()
    min_os = args.min_os
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('fresh output required')
    out.mkdir(parents=True)
    nonce = args.nonce or hashlib.sha256((started + args.version).encode()).hexdigest()[:32]
    if len(nonce) != 32 or any(c not in '0123456789abcdefABCDEF' for c in nonce):
        raise SystemExit('nonce must be 32 hex characters')

    receipt, host_digest = validate_receipt(args.install_receipt, args.host_app, started, args.bundle_id, args.udid)
    host_app = args.host_app.resolve()
    contract = host_app / 'TrustedUpdate.Contract.dll'
    contract_mvid = pe_mvid(contract)
    if not contract_mvid:
        raise SystemExit('installed host Contract has no MVID')
    if not (host_app / 'TrustedUpdate.Host.dll').is_file():
        raise SystemExit('installed host lacks the host assembly')

    inventory = json.loads((framework / 'input-inventory.json').read_text())
    refs = [framework / 'input' / name for name in sorted(inventory['compositeInputs'])]
    refs += [contract, host_app / 'RuneCLR.TrustedUpdate.dll']

    source_hashes = {name: sha(args.sources / name) for name in SOURCE_FILES + (VERSION_FILE[args.version],)}
    sdk_version = subprocess.run([str(sdk), '--version'], capture_output=True, text=True).stdout.strip()
    toolchain = {
        'dotnet': str(sdk), 'dotnetSha256': sha(sdk) if sdk.is_file() else None,
        'sdkVersion': sdk_version,
        'csc': str(csc), 'cscSha256': sha(csc) if csc.is_file() else None,
        'crossgen2': str(crossgen2), 'crossgen2Sha256': sha(crossgen2) if crossgen2.is_file() else None,
        'capturedUtc': utc(),
    }
    stamp = out / 'RunStamp.cs'
    stamp.write_text(
        'internal static class RunStamp {\n'
        '    internal const string Version = "' + args.version + '";\n'
        '    internal const string Nonce = "' + nonce + '";\n'
        '}\n', encoding='ascii')

    update = out / 'TrustedUpdate.Update.dll'
    private = out / 'TrustedUpdate.Private.dll'
    helper = out / 'TrustedUpdate.IlOnlyHelper.dll'
    version_code = run_logged([sdk, '--version'], out, 'sdk-version')
    (out / 'compiler.txt').write_text(str(csc) + chr(10) + sha(csc) + chr(10) + str(version_code), encoding='ascii')
    if compile_logged(out, 'update-compile', [args.sources / n for n in ('Business.cs', 'Update.cs', VERSION_FILE[args.version])] + [stamp], refs, update, sdk, csc) != 0:
        raise SystemExit('update compile failed')
    if compile_logged(out, 'private-compile', [args.sources / 'PrivateLogic.cs', args.sources / VERSION_FILE[args.version]], refs, private, sdk, csc) != 0:
        raise SystemExit('private compile failed')
    if compile_logged(out, 'helper-compile', [args.sources / 'IlOnlyHelper.cs'], refs, helper, sdk, csc) != 0:
        raise SystemExit('helper compile failed')

    crossgen_dir = out / 'crossgen-out'
    crossgen_dir.mkdir()
    obj = crossgen_dir / ('TrustedUpdate.' + args.version + '.r2r.obj')
    owner = crossgen_dir / ('TrustedUpdate.' + args.version + '.r2r.dylib')
    rsp = out / 'crossgen.rsp'
    options = ['--targetos:ios', '--targetarch:arm64', '--obj-format:macho', '--composite',
               '--inputbubble', '--parallelism:2', '--resilient', '--optimize', '--out:' + str(obj)]
    rsp.write_text(chr(10).join(options + [str(update)] + ['-r:' + str(r) for r in refs]) + chr(10), encoding='ascii')
    before_crossgen = {p.name: sha(p) for p in (update, private, helper)}
    if run_logged([crossgen2, '@' + str(rsp)], out, 'owner-crossgen') != 0:
        raise SystemExit('owner crossgen failed')
    if {p.name: sha(p) for p in (update, private, helper)} != before_crossgen:
        raise SystemExit('crossgen changed an input assembly')

    if run_logged(['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios' + min_os, '-dynamiclib',
                   str(obj), '-Wl,-install_name,@rpath/' + owner.name, '-o', str(owner)], out, 'owner-link') != 0:
        raise SystemExit('owner link failed')

    fields = macho_fields(owner)
    if fields['platform'] != 2:
        raise SystemExit('owner is not platform 2')
    header = exported_rtr_header(owner)
    rewritten_update = crossgen_dir / 'TrustedUpdate.Update.dll'
    if not rewritten_update.is_file():
        raise SystemExit('crossgen did not write the component copy')
    component = component_header(rewritten_update, owner.name)
    if not component['componentBit']:
        raise SystemExit('rewritten component lacks the READYTORUN COMPONENT flag')
    if component['ownerComposite'] != owner.name:
        raise SystemExit('component owner section does not name the owner: ' + str(component['ownerComposite']))
    if pe_mvid(rewritten_update) != pe_mvid(update):
        raise SystemExit('rewritten component MVID differs from the compile input')

    deploy = out / 'deploy'
    deploy.mkdir()
    files = {rewritten_update.name: rewritten_update, private.name: private, helper.name: helper,
             owner.name: owner}
    manifest = {}
    for name, path in files.items():
        shutil.copyfile(path, deploy / name)
        manifest[name] = {'sha256': sha(deploy / name), 'bytes': (deploy / name).stat().st_size}
    payload_list = deploy / 'payload-files.txt'
    payload_list.write_text(chr(10).join(name + ' ' + manifest[name]['sha256'] for name in sorted(manifest)) + chr(10),
                            encoding='ascii')

    owner_json = {
        'schema': 'runeclr.ipados.r2r.owner.v2', 'capturedUtc': utc(), 'generatedAtUtc': started,
        'version': args.version, 'nonce': nonce, 'collectible': False,
        'contract': {'name': contract.name,
                     'componentSha256': sha(contract),
                     'rawIlSha256': None,
                     'mvid': contract_mvid,
                     'mvidCanonical': canonical_mvid(contract_mvid),
                     'mvidSource': 'raw-metadata-heap-bytes',
                     'source': 'installed host Default ALC'},
        'sources': source_hashes, 'compiler': str(csc), 'compilerSha256': sha(csc),
        'toolchain': toolchain,
        'crossgenArgs': options,
        'owner': {'name': owner.name, 'rawSha256': manifest[owner.name]['sha256'],
                  'bytes': manifest[owner.name]['bytes'], 'uuid': fields['uuid'],
                  'platform': fields['platform'], 'text': fields['text'], 'rtrHeader': header,
                  'signedSha256': None,
                  'signedSha256Note': 'Fill after normal development signing; UUID and code range must not change.'},
        'components': {name: manifest[name] for name in manifest if name.endswith('.dll')},
        'payload': manifest, 'payloadFilesSha256': sha(payload_list),
        'deployable': sorted(manifest) + [payload_list.name],
        'installReceipt': {'path': str(args.install_receipt.resolve()), 'sha256': sha(args.install_receipt),
                           'appDigestSha256': host_digest, 'installedUtc': receipt.get('installedUtc'),
                           'deviceUdid': receipt.get('deviceUdid'), 'archive': receipt.get('archive')},
    }
    (out / 'owner.json').write_text(json.dumps(owner_json, indent=2) + chr(10), encoding='ascii')
    print(json.dumps({'status': 'PASS', 'version': args.version, 'owner': str(deploy / owner.name),
                      'rawSha256': owner_json['owner']['rawSha256'], 'uuid': fields['uuid'],
                      'nonce': nonce, 'deployable': owner_json['deployable']}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
