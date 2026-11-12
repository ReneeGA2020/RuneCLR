#!/usr/bin/env python3
"""Offline self-test for the iPad device R2R native host package.

Runs only synthetic/local checks: C path normalization tests, the managed RunEntry
result-contract fixtures, generator install-receipt validation and the crossgen
component-header parser. No device, no signing, no product build, no runtime.

Usage:
    python3 -B eng/ipad-r2r-native/host/tools/selftest.py [--dotnet PATH] [--clang PATH] [--keep]
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
SRC = PACKAGE / 'host/src'
TEST = PACKAGE / 'host/test'
TOOLS = PACKAGE / 'host/tools'
NONCE = '0123456789abcdef0123456789abcdef'
failures = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + ((' ' + detail) if detail else ''))
    if not ok:
        failures.append(name)


def run(cmd, cwd=None, env=None, log=None):
    process = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                             capture_output=True, text=True)
    if log:
        Path(log).write_text(process.stdout + process.stderr, encoding='utf-8')
    return process


def c_tests(work, clang):
    binary = work / 'rn_test'
    build = run([clang, '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', binary,
                 SRC / 'path_norm.c', SRC / 'rn_test.c'])
    check('path-tests-build', build.returncode == 0, build.stderr.strip()[:160])
    if build.returncode != 0:
        return
    result = run([binary], log=work / 'path-tests.log')
    passed = result.returncode == 0 and 'RESULT PASS' in result.stdout
    count = result.stdout.count('PASS ')
    check('path-tests-cases', passed and count >= 26, 'cases=' + str(count))


def build_fixtures(work, dotnet):
    env = dict(**__import__('os').environ)
    env.setdefault('DOTNET_CLI_TELEMETRY_OPTOUT', '1')
    env.setdefault('DOTNET_NOLOGO', '1')
    ok = True
    builds = (('Stamp', 'Stamp-A', ['-p:StampVersion=A']),
              ('Stamp', 'Stamp-B', ['-p:StampVersion=B']),
              ('Contract', 'Contract', []),
              ('Harness', 'Harness', []))
    for name, tag, props in builds:
        result = run([dotnet, 'build', TEST / name / (name + '.csproj'), '-c', 'Release', '-v', 'q',
                      '-p:BaseOutputPath=' + str(work / 'bin' / tag) + '/',
                      '-p:BaseIntermediateOutputPath=' + str(work / 'obj' / tag) + '/'] + props,
                     cwd=work, env=env, log=work / ('build-' + tag + '.log'))
        ok = ok and result.returncode == 0
    check('managed-fixtures-build', ok)
    if not ok:
        return None, None
    harness = work / 'bin/Harness/Release/net11.0/ProbeHarness.dll'
    stamp_a = work / 'bin/Stamp-A/Release/net11.0/TrustedUpdate.Update.dll'
    stamp_b = work / 'bin/Stamp-B/Release/net11.0/TrustedUpdate.Update.dll'
    contract = work / 'bin/Contract/Release/net11.0/TrustedUpdate.Contract.dll'
    if not harness.is_file() or not stamp_a.is_file() or not stamp_b.is_file():
        check('managed-fixtures-present', False)
        return None, None
    if contract.is_file():
        shutil.copyfile(contract, harness.parent / 'TrustedUpdate.Contract.dll')
    check('managed-fixtures-present', True)
    return harness, (stamp_a, stamp_b)


def entry_case(dotnet, harness, work, name, extra, expect_exit, expect_ok, expect_error=None, expect_result=None, stamp=None):
    env = {k: v for k, v in __import__('os').environ.items() if not k.startswith(('RUNECLR_', 'TEST_'))}
    env.update({'RUNECLR_EXPECTED_VERSION': 'A', 'RUNECLR_PROBE_NONCE': NONCE,
                'RUNECLR_GOLDEN_RESULT': '216', 'RUNECLR_GOLDEN_PRIVATE': '100',
                'RUNECLR_GOLDEN_HELPER': '307', 'TEST_LOAD_STAMP': '1',
                'TEST_MODE': 'ok', 'TEST_PRIVATE': '100', 'TEST_HELPER': '307',
                'RUNECLR_RESULT_PATH': str(work / (name + '.json')),
                'TEST_STAMP_PATH': str(stamp) if stamp else ''})
    env.update(extra)
    process = run([dotnet, harness], cwd=work, env=env, log=work / (name + '.log'))
    lines = [line for line in process.stdout.splitlines() if line.startswith('RUNE_IPAD_RESULT ')]
    payload = json.loads(lines[-1][len('RUNE_IPAD_RESULT '):]) if lines else {}
    ok = process.returncode == expect_exit and payload.get('ok') is expect_ok
    if expect_error:
        ok = ok and expect_error in (payload.get('error') or '')
    if expect_result:
        ok = ok and payload.get('observedResult') == expect_result
    check('entry-' + name, ok, 'exit=' + str(process.returncode) + ' ok=' + str(payload.get('ok')) +
          ' err=' + str(payload.get('error')) + ' result=' + str(payload.get('observedResult')))


def run_entry_tests(work, dotnet, harness, stamps):
    stamp_a, stamp_b = stamps
    cases = {
        'final-216': ({'TEST_STAMP_PATH': str(stamp_a)}, 0, True, None, '216'),
        'final-216-B': ({'RUNECLR_EXPECTED_VERSION': 'B', 'TEST_STAMP_PATH': str(stamp_b),
                         'TEST_STAMP_VERSION': 'B', 'RUNECLR_GOLDEN_PRIVATE': '200',
                         'TEST_PRIVATE': '200', 'RUNECLR_GOLDEN_HELPER': '607', 'TEST_HELPER': '607'},
                        0, True, None, '216'),
        'no-final-success': ({'TEST_MODE': 'no-success'}, 1, False, 'driver-success-marker-missing', None),
        'ambiguous-success': ({'TEST_MODE': 'ambiguous'}, 1, False, 'final-success-ambiguous', None),
        'golden-215-mismatch': ({'RUNECLR_GOLDEN_RESULT': '215'}, 1, False, 'golden-mismatch', '216'),
        'wrong-nonce': ({'RUNECLR_PROBE_NONCE': 'ffeeddccbbaa99887766554433221100'}, 1, False,
                        'nonce-mismatch', None),
        'wrong-version': ({'RUNECLR_EXPECTED_VERSION': 'B'}, 1, False, 'version-mismatch', None),
        'driver-failure': ({'TEST_MODE': 'fail'}, 1, False, 'driver-success-marker-missing', None),
        'result-path-missing': ({'RUNECLR_RESULT_PATH': ''}, 1, False, 'result-path-missing', None),
    }
    blocked = work / 'blocked.json'
    blocked.mkdir(exist_ok=True)
    cases['result-write-failure'] = ({'RUNECLR_RESULT_PATH': str(blocked)}, 1, False,
                                     'result-write-failed', None)
    for name, (extra, expect_exit, expect_ok, expect_error, expect_result) in cases.items():
        entry_case(dotnet, harness, work, name, extra, expect_exit, expect_ok, expect_error,
                   expect_result, stamp_a)


def load_generator():
    spec = importlib.util.spec_from_file_location('ipad_generate_update', TOOLS / 'generate_update_v2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_digest(app):
    entries = [{'path': str(p.relative_to(app)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                'size': p.stat().st_size} for p in sorted(Path(app).rglob('*')) if p.is_file()]
    return hashlib.sha256(''.join(e['path'] + chr(0) + e['sha256'] + chr(0) + str(e['size']) + chr(10)
                                  for e in entries).encode()).hexdigest()


def mvid_tests(generator):
    raw = '24716ef334ba1e4c9843fc900fd2de39'
    check('canonical-mvid-guid-d',
          generator.canonical_mvid(raw) == 'f36e7124-ba34-4c1e-9843-fc900fd2de39',
          generator.canonical_mvid(raw))
    check('canonical-mvid-not-raw-order',
          generator.canonical_mvid(raw) != '24716ef3-34ba-1e4c-9843-fc900fd2de39')


def receipt_tests(work, generator):
    app = work / 'fake-host.app'
    app.mkdir(exist_ok=True)
    (app / 'TrustedUpdate.Contract.dll').write_bytes(b'contract-stub')
    (app / 'TrustedUpdate.Host.dll').write_bytes(b'host-stub')
    digest = app_digest(app)
    raw = work / 'raw-receipt.json'
    raw.write_text(json.dumps({'success': True, 'bundleId': 'org.example.probe',
                               'deviceUdid': 'UDID-0001'}))
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    base = {'status': 'installed', 'installed': True, 'signed': True,
            'bundleId': 'org.example.probe', 'deviceUdid': 'UDID-0001', 'platform': 2,
            'installedUtc': '2026-01-01T00:00:00Z', 'appDigestSha256': digest,
            'rawReceiptPath': str(raw), 'rawReceiptSha256': raw_sha,
            'archive': {'path': '/tmp/archive.zip', 'sha256': '0' * 64}}
    started = '2026-01-02T00:00:00Z'

    def validate(receipt):
        path = work / 'receipt-case.json'
        path.write_text(json.dumps(receipt))
        try:
            generator.validate_receipt(path, app, started, 'org.example.probe', 'UDID-0001')
            return True
        except SystemExit:
            return False

    check('receipt-valid', validate(dict(base)))
    check('receipt-wrong-bundle', not validate(dict(base, bundleId='org.example.other')))
    check('receipt-wrong-device', not validate(dict(base, deviceUdid='UDID-0002')))
    check('receipt-unsigned', not validate(dict(base, signed=False)))
    check('receipt-future-install', not validate(dict(base, installedUtc='2027-01-01T00:00:00Z')))
    check('receipt-wrong-digest', not validate(dict(base, appDigestSha256='1' * 64)))
    check('receipt-raw-hash-wrong', not validate(dict(base, rawReceiptSha256='2' * 64)))


def synthetic_component(component_bit=True, owner='TrustedUpdate.A.r2r.dylib',
                        flags_extra=0x0, decoy=None):
    """Minimal PE with a CLI header and a real-layout ReadyToRun header.

    READYTORUN_HEADER: signature +0, major/minor +4/+6, flags +8,
    numberOfSections +12, entrySize +14, sections +16. One section of type 116
    (OwnerCompositeExecutable) points at the owner file name.
    """
    data = bytearray(0x600)
    struct.pack_into('<I', data, 0x3C, 0x80)
    data[0x80:0x84] = b'PE' + bytes([0, 0])
    struct.pack_into('<HHIIIHH', data, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x22)
    opt = 0x98
    struct.pack_into('<H', data, opt, 0x20B)
    struct.pack_into('<I', data, opt + 16, 0x2000)
    struct.pack_into('<I', data, opt + 20, 0x200)
    struct.pack_into('<I', data, opt + 32, 0x2000)
    struct.pack_into('<H', data, opt + 56, 0x2000)
    struct.pack_into('<H', data, opt + 60, 0x200)
    struct.pack_into('<I', data, opt + 108, 16)
    struct.pack_into('<II', data, opt + 112 + 14 * 8, 0x2000, 0x40)  # CLI header
    sect = opt + 0xF0
    data[sect:sect + 8] = b'.text'.ljust(8, bytes([0]))
    struct.pack_into('<IIII', data, sect + 8, 0x400, 0x2000, 0x400, 0x200)
    cor = 0x200
    struct.pack_into('<I', data, cor, 72)
    struct.pack_into('<II', data, cor + 64, 0x2100, 0x40)  # ManagedNativeHeader -> file 0x300
    native_off = 0x300
    struct.pack_into('<I', data, native_off, 0x00525452)
    struct.pack_into('<HH', data, native_off + 4, 1, 0)
    flags = (0x20 if component_bit else 0) | flags_extra
    struct.pack_into('<I', data, native_off + 8, flags)
    struct.pack_into('<H', data, native_off + 12, 1)
    struct.pack_into('<H', data, native_off + 14, 12)
    owner_bytes = owner.encode() + bytes([0])
    struct.pack_into('<III', data, native_off + 16, 116, 0x2200, len(owner_bytes))
    data[0x400:0x400 + len(owner_bytes)] = owner_bytes
    if decoy:
        data[0x500:0x500 + len(decoy)] = decoy.encode()
    return bytes(data)


def component_tests(work, generator, sample=None):
    good = work / 'component-good.dll'
    bad = work / 'component-bad.dll'
    wrong_owner = work / 'component-wrong-owner.dll'
    good.write_bytes(synthetic_component(True))
    bad.write_bytes(synthetic_component(False))
    wrong_owner.write_bytes(synthetic_component(True, owner='Other.r2r.dylib',
                                                decoy='TrustedUpdate.A.r2r.dylib'))
    positive = generator.component_header(good, 'TrustedUpdate.A.r2r.dylib')
    negative = generator.component_header(bad, 'TrustedUpdate.A.r2r.dylib')
    wrong = generator.component_header(wrong_owner, 'TrustedUpdate.A.r2r.dylib')
    check('component-header-positive', positive['componentBit'] and (positive['flags'] & 0x20) == 0x20,
          'flags=0x%x owner=%s' % (positive['flags'] or 0, positive['ownerComposite']))
    check('component-header-owner',
          positive['ownerComposite'] == 'TrustedUpdate.A.r2r.dylib', str(positive['ownerComposite']))
    check('component-header-negative', not negative['componentBit'],
          'flags=0x%x' % (negative['flags'] or 0))
    check('component-header-wrong-owner',
          wrong['componentBit'] and wrong['ownerComposite'] == 'Other.r2r.dylib',
          str(wrong['ownerComposite']))
    if sample:
        real = generator.component_header(Path(sample), Path(sample).name)
        check('component-header-real-host', real['componentBit'] and bool(real['ownerComposite']),
              'owner=' + str(real['ownerComposite']))


def build_host_source_fixture():
    src = (TOOLS / "build_host.py").read_text(encoding="utf-8")
    directives = ["global using System;", "global using System.Collections.Generic;",
                  "global using System.IO;", "global using System.Linq;",
                  "global using System.Net.Http;", "global using System.Net.Http.Json;",
                  "global using System.Threading;", "global using System.Threading.Tasks;"]
    check("build-host-implicit-usings-file",
          "global-usings.g.cs" in src and all(d in src for d in directives))
    check("build-host-nullable-managed-only", src.count("-nullable:enable") == 3)
    contract = [l for l in src.splitlines() if chr(39) + "Contract.cs" + chr(39) in l]
    check("build-host-contract-compile-unchanged",
          bool(contract) and "global_usings" not in contract[0] and "-nullable" not in contract[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet', help='dotnet 11+ host')
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--keep', action='store_true', help='keep the temporary work directory')
    parser.add_argument('--component-sample', default=None,
                        help='optional real host component DLL for the header parser check')
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix='ipad-r2r-selftest-'))
    try:
        c_tests(work, args.clang)
        harness, stamps = build_fixtures(work, args.dotnet)
        if harness and stamps:
            run_entry_tests(work, args.dotnet, harness, stamps)
        generator = load_generator()
        mvid_tests(generator)
        receipt_tests(work, generator)
        component_tests(work, generator, args.component_sample)
        build_host_source_fixture()
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print('WORKDIR ' + str(work))
    total = len(failures)
    print('IPAD_R2R_NATIVE_SELFTEST ' + ('PASS' if total == 0 else 'FAIL') + ' failures=' + str(total))
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
