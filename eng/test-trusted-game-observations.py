#!/usr/bin/env python3
"""Offline tests for eng/verify-trusted-game-observations.py.

The default run builds a self-contained synthetic run root (including minimal
PE images, maps, logs, observations, signed documents and receipts) and never
touches machine-specific artifacts. Pass --run-root to also replay one
retained run root; the retained root is read only and never written.
"""

from copy import deepcopy
import base64
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
ENG = REPO / 'eng'
sys.path.insert(0, str(ENG))

from trusted_game_observations import builder, observations, pe, replay  # noqa: E402
from trusted_game_observations.common import (canonical_json, load_json,  # noqa: E402
                                              sha256_bytes, sha256_file)


CLI = ENG / 'verify-trusted-game-observations.py'


def _align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def _put(fmt, data, offset, *values):
    struct.pack_into(fmt, data, offset, *values)


def make_pe(path, guid, pdata=(), marker=b'', text_size=0x10000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text_rva = 0x1000
    text_raw = 0x400
    pdata_rva = text_rva + text_size
    pdata_size = 12 * len(pdata) + 4
    pdata_raw = _align(text_raw + text_size, 0x200)
    pdata_raw_size = _align(pdata_size, 0x200)
    image_size = _align(pdata_rva + pdata_size, 0x1000)
    cli_rva = text_rva + 0x5F00
    metadata_rva = text_rva + 0x6000
    metadata_size = 0x200
    data = bytearray(pdata_raw + pdata_raw_size)
    data[0:2] = b'MZ'
    _put('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    _put('<HHIIIHH', data, 0x84, 0x8664, 2, 0, 0, 0, 0xF0, 0x22)
    opt = 0x98
    _put('<H', data, opt, 0x20b)
    _put('<BB', data, opt + 2, 14, 0)
    _put('<I', data, opt + 4, text_size)
    _put('<I', data, opt + 8, pdata_raw_size)
    _put('<I', data, opt + 12, 0)
    _put('<I', data, opt + 16, 0)
    _put('<I', data, opt + 20, text_rva)
    _put('<Q', data, opt + 24, 0x140000000)
    _put('<I', data, opt + 32, 0x1000)
    _put('<I', data, opt + 36, 0x200)
    _put('<HH', data, opt + 40, 6, 0)
    _put('<HH', data, opt + 44, 0, 0)
    _put('<HH', data, opt + 48, 6, 0)
    _put('<I', data, opt + 52, 0)
    _put('<I', data, opt + 56, image_size)
    _put('<I', data, opt + 60, 0x400)
    _put('<I', data, opt + 64, 0)
    _put('<H', data, opt + 68, 3)
    _put('<H', data, opt + 70, 0)
    _put('<Q', data, opt + 72, 0x100000)
    _put('<Q', data, opt + 80, 0x1000)
    _put('<Q', data, opt + 88, 0x100000)
    _put('<Q', data, opt + 96, 0x1000)
    _put('<I', data, opt + 104, 0)
    _put('<I', data, opt + 108, 16)
    _put('<II', data, opt + 112 + 3 * 8, pdata_rva, pdata_size)
    _put('<II', data, opt + 112 + 14 * 8, cli_rva, 72)
    section = opt + 0xF0
    data[section:section + 8] = b'.text\0\0\0'
    _put('<IIIIIIHHI', data, section + 8, text_size, text_rva, text_size,
         text_raw, 0, 0, 0, 0, 0x60000020)
    section2 = section + 40
    data[section2:section2 + 8] = b'.pdata\0\0'
    _put('<IIIIIIHHI', data, section2 + 8, pdata_size, pdata_rva,
         pdata_raw_size, pdata_raw, 0, 0, 0, 0, 0x40000040)
    data[text_raw + 0x10:text_raw + 0x10 + len(marker)] = marker
    for index, (begin, end, unwind) in enumerate(pdata):
        _put('<III', data, pdata_raw + index * 12, begin, end, unwind)
    cli = text_raw + (cli_rva - text_rva)
    _put('<I', data, cli, 72)
    _put('<HH', data, cli + 4, 2, 5)
    _put('<I', data, cli + 8, metadata_rva)
    _put('<I', data, cli + 12, metadata_size)
    _put('<I', data, cli + 16, 1)
    metadata = bytearray(metadata_size)
    _put('<IHHII', metadata, 0, 0x424A5342, 1, 1, 0, 12)
    metadata[16:28] = b'v4.0.30319\0\0'
    _put('<HH', metadata, 28, 0, 3)
    at = 32
    for name, offset, size in (('#~', 0x50, 0x30), ('#GUID', 0x80, 0x10),
                               ('#Strings', 0x90, 0x10)):
        _put('<II', metadata, at, offset, size)
        at += 8
        raw = name.encode('ascii') + b'\0'
        metadata[at:at + len(raw)] = raw
        at = _align(at + len(raw), 4)
    _put('<IBBBBQQI', metadata, 0x50, 0, 2, 0, 0, 0, 1, 0, 1)
    _put('<HHHHH', metadata, 0x6C, 0, 1, 1, 0, 0)
    metadata[0x80:0x90] = uuid.UUID(guid).bytes_le
    metadata[0x90:0x99] = b'\0Fixture\0'
    metadata_at = text_raw + (metadata_rva - text_rva)
    data[metadata_at:metadata_at + metadata_size] = metadata
    path.write_bytes(bytes(data))


def write_map(path, rva, length, symbol):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ('Rva,Length,Relocs,Section,Symbol,Node Type\n'
            '0x%08X,%d,0,.text,%s,MethodWithGCInfo\n' % (rva, length, symbol))
    path.write_text(text, encoding='utf-8-sig')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1), encoding='utf-8')


def signed_document(manifest):
    payload = json.dumps(manifest, separators=(',', ':')).encode('utf-8')
    return (b'RTRSIG1\n' + base64.b64encode(b'fixture-signature') +
            b'\n' + payload + b'\n')


class Fixture:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runtime = self.root / 'runtime'
        self.framework = self.runtime / 'shared' / 'Microsoft.NETCore.App' / '12.0.0'
        self.coreclr = self.framework / 'coreclr.dll'
        self.dotnet = self.runtime / 'dotnet.exe'
        self.sdk_dotnet = self.root / 'tools' / 'dotnet.exe'
        self.publisher = self.root / 'publisher' / 'TrustedGame.Publisher.dll'
        self.leaf = self.root / 'leaf' / 'caller_leaf.dll'
        self.signing = self.root / 'signing'
        self.private_key = self.signing / 'demo.private.pem'
        self.spki = self.signing / 'demo.spki'
        self.a_signed = self.signing / 'A.signed.json'
        self.b_signed = self.signing / 'B.signed.json'
        self.guids = {
            'Host': '11111111-1111-4111-8111-111111111111',
            'Contracts': '22222222-2222-4222-8222-222222222222',
            'TrustedUpdate': '33333333-3333-4333-8333-333333333333',
            'A': '44444444-4444-4444-8444-444444444444',
            'B': '55555555-5555-4555-8555-555555555555',
        }
        self.create()

    def create(self):
        for directory in (self.runtime, self.framework, self.root / 'tools',
                          self.root / 'publisher', self.root / 'leaf',
                          self.signing, self.root / 'logs',
                          self.root / 'observations'):
            directory.mkdir(parents=True, exist_ok=True)
        self.dotnet.write_bytes(b'fixture-private-dotnet')
        self.sdk_dotnet.write_bytes(b'fixture-sdk-dotnet')
        self.publisher.write_bytes(b'fixture-publisher')
        self.leaf.write_bytes(b'fixture-caller-leaf')
        self.private_key.write_bytes(b'NOT A REAL PRIVATE KEY')
        self.spki.write_bytes(b'fixture-spki')
        make_pe(self.coreclr, '99999999-9999-4999-8999-999999999999',
                pdata=((0x2000, 0x2100, 0),), marker=b'coreclr')
        self.r2r = {}
        self.il = {}
        specs = {
            'Host': (0x4C30, 726, 'TrustedGame_Host_Gameplay__InvokeObserved'),
            'Contracts': (0x2000, 0x100, 'TrustedGame_Contracts_Fixture'),
            'TrustedUpdate': (0x2000, 0x100, 'RuneCLR_TrustedUpdate_Fixture'),
            'A': (0x1680, 259, 'TrustedGame_Update_TrustedGame_Update_GameRules__Tick'),
            'B': (0x1680, 259, 'TrustedGame_Update_TrustedGame_Update_GameRules__Tick'),
        }
        self.specs = specs
        for key, (rva, length, symbol) in specs.items():
            group = 'host' if key in ('Host', 'Contracts', 'TrustedUpdate') else key.lower()
            name = ('TrustedGame.Host.dll' if key == 'Host' else
                    'TrustedGame.Contracts.dll' if key == 'Contracts' else
                    'RuneCLR.TrustedUpdate.dll' if key == 'TrustedUpdate' else
                    'TrustedGame.Update.dll')
            r2r = self.root / 'r2r' / group / name
            il = self.root / 'il' / group / name
            pdata = ((rva, rva + length, 0x1000),)
            make_pe(r2r, self.guids[key], pdata=pdata,
                    marker=('R2R-' + key).encode('ascii'))
            make_pe(il, self.guids[key], pdata=pdata,
                    marker=('IL-' + key).encode('ascii'))
            self.r2r[key] = r2r
            self.il[key] = il
        self.maps = {}
        for key in ('Host', 'A', 'B'):
            rva, length, symbol = specs[key]
            path = self.r2r[key].with_suffix('.map.csv')
            write_map(path, rva, length, symbol)
            self.maps[key] = path
        self.images = {}
        for key in self.guids:
            self.images[key] = {
                'ilPath': str(self.il[key]), 'r2rPath': str(self.r2r[key]),
                'ilSha': sha256_file(self.il[key]),
                'r2rSha': sha256_file(self.r2r[key]),
                'ilMvid': self.guids[key], 'r2rMvid': self.guids[key],
                'ilR2R': False, 'r2r': True,
            }
        self.bindings = {}
        for key in ('Host', 'A', 'B'):
            rva, length, symbol = specs[key]
            self.bindings[key] = {
                'path': str(self.r2r[key]),
                'sha256': self.images[key]['r2rSha'],
                'method': {
                    'symbol': symbol, 'rva': rva, 'length': length,
                    'section': '.text', 'mapPath': str(self.maps[key]),
                    'mapSha': sha256_file(self.maps[key]),
                },
                'executableSections': pe.executable_sections(self.r2r[key]),
                'runtimeFunctions': pe.pdata(self.r2r[key]),
            }
        self.preflight = {
            'framework': str(self.framework),
            'layout': str(self.runtime),
            'runtimeSeal': {
                'layoutDotnet': {'path': str(self.dotnet),
                                 'sha256': sha256_file(self.dotnet)},
                'files': {'coreclr.dll': {
                    'framework': str(self.coreclr),
                    'frameworkSha': sha256_file(self.coreclr),
                    'checked': str(self.coreclr),
                    'checkedSha': sha256_file(self.coreclr),
                    'expected': sha256_file(self.coreclr),
                }},
            },
        }
        self.manifest_a = self.manifest('game-rules-a', self.images['A']['r2rSha'])
        self.manifest_b = self.manifest('game-rules-b', self.images['B']['r2rSha'])
        self.a_bytes = signed_document(self.manifest_a)
        self.b_bytes = signed_document(self.manifest_b)
        self.a_signed.write_bytes(self.a_bytes)
        self.b_signed.write_bytes(self.b_bytes)
        self.commands = []
        self.raw_logs = {}
        self.lanes = []
        pids = {
            ('r2r1', 'stageA'): 1101, ('r2r1', 'stageB'): 1102,
            ('r2r1', 'recoverB'): 1103, ('r2r0', 'stageA'): 1201,
            ('r2r0', 'stageB'): 1202, ('r2r0', 'recoverB'): 1203,
        }
        self.commands.append(self.make_command(
            'assembly-identities', self.assembly_argv(), {}, 3001, b'[]\r\n'))
        self.commands.append(self.make_command(
            'publish-A', self.publish_argv('A', 'game-rules-a', self.a_signed),
            {}, 3002, b'published A\r\n'))
        self.commands.append(self.make_command(
            'publish-B', self.publish_argv('B', 'game-rules-b', self.b_signed),
            {}, 3003, b'published B\r\n'))
        for lane_name in ('r2r1', 'r2r0'):
            self.lanes.append(self.make_lane(lane_name, pids))
        self.raw_logs = {}
        for command in self.commands:
            self.raw_logs[str(Path(command['stdout']))] = sha256_file(command['stdout'])
            self.raw_logs[str(Path(command['stderr']))] = sha256_file(command['stderr'])
        self.write_inputs()

    def manifest(self, version, module_sha):
        return {
            'formatVersion': 1, 'version': version, 'runtime': 'net11.0',
            'architecture': 'x64', 'entryType': 'TrustedGame.Update.GameRules',
            'entryMethod': 'Entry', 'entryPath': 'TrustedGame.Update.dll',
            'files': [{'path': 'TrustedGame.Update.dll', 'sha256': module_sha}],
        }

    def assembly_argv(self):
        paths = [str(self.r2r[key]) for key in
                 ('Host', 'Contracts', 'TrustedUpdate', 'A', 'B')]
        paths += [str(self.il[key]) for key in ('A', 'B')]
        script = '$p=@(' + ','.join("'" + path + "'" for path in paths) + ');$p'
        return [str(self.root / 'tools' / 'pwsh.exe'), '-NoProfile', '-Command', script]

    def publish_argv(self, key, version, signed):
        module = str(self.r2r[key])
        return [
            str(self.sdk_dotnet), str(self.publisher), '--module', module,
            '--version', version, '--entry-type', 'TrustedGame.Update.GameRules',
            '--entry-method', 'Entry', '--signed', str(signed),
            '--spki', str(self.spki), '--private-key', str(self.private_key),
            '--content-root', str(Path(module).parent), '--runtime', 'net11.0',
            '--architecture', 'x64',
        ]

    def make_command(self, name, argv, settings, pid, stdout, stderr=b''):
        stdout_path = self.root / 'logs' / (name + '.stdout')
        stderr_path = self.root / 'logs' / (name + '.stderr')
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        now = '2026-10-21T00:00:00+08:00'
        return {
            'name': name, 'argv': argv, 'cwd': str(self.root),
            'settings': settings, 'startStatus': 'started', 'startedUtc': now,
            'stdout': str(stdout_path), 'stderr': str(stderr_path),
            'pid': pid, 'timedOut': False, 'exitCode': 0,
            'endedStatus': 'exited', 'endedUtc': now,
            'stdoutBytes': len(stdout), 'stderrBytes': len(stderr),
        }

    def settings(self, lane_name):
        return {
            'DOTNET_ROOT': str(self.runtime),
            'DOTNET_ReadyToRun': '1' if lane_name == 'r2r1' else '0',
            'DOTNET_InterpMode': '1', 'DOTNET_TieredCompilation': '0',
            'DOTNET_TC_QuickJit': '0', 'DOTNET_TC_OnStackReplacement': '0',
            'DOTNET_MULTILEVEL_LOOKUP': '0', 'DOTNET_ROLL_FORWARD': 'Disable',
            'TRUSTED_GAME_OBSERVE': '1',
            'RUNECLR_CALLER_LEAF': str(self.leaf),
        }

    def make_lane(self, lane_name, pids):
        ready = lane_name == 'r2r1'
        receipt_a = sha256_bytes(('A-receipt-' + lane_name).encode('utf-8'))
        content_a = 'game-rules-a-' + sha256_bytes(('A-' + lane_name).encode('utf-8'))[:32]
        content_b = 'game-rules-b-' + sha256_bytes(('B-' + lane_name).encode('utf-8'))[:32]
        releases = self.root / 'lanes' / lane_name / 'releases'
        staged_a = releases / content_a / 'TrustedGame.Update.dll'
        staged_b = releases / content_b / 'TrustedGame.Update.dll'
        staged_a.parent.mkdir(parents=True, exist_ok=True)
        staged_b.parent.mkdir(parents=True, exist_ok=True)
        staged_a.write_bytes(self.r2r['A'].read_bytes())
        staged_b.write_bytes(self.r2r['B'].read_bytes())
        receipt_path = self.root / 'lanes' / lane_name / 'receipt.json'
        receipt = {'v': 1, 'contentRoot': content_b,
                   'document': base64.b64encode(self.b_bytes).decode('ascii')}
        receipt_path.write_text(json.dumps(receipt, separators=(',', ':')),
                                encoding='utf-8')
        receipt_b = sha256_file(receipt_path)
        lane = {
            'lane': lane_name, 'readyToRun': ready, 'settings': self.settings(lane_name),
            'receiptA': receipt_a, 'receiptB': receipt_b, 'receiptRecover': receipt_b,
        }
        for scenario, staged_key, version, method_key, signed_name, suffix in (
            ('stageA', 'stagedA', 'game-rules-a', 'A', 'A.signed.json', 'stage-A'),
            ('stageB', 'stagedB', 'game-rules-b', 'B', 'B.signed.json', 'stage-B'),
            ('recoverB', 'stagedRecover', 'game-rules-b', 'B', 'B.signed.json', 'recover-B'),
        ):
            mode = 'recover' if scenario == 'recoverB' else 'stage'
            multiplier = 2 if version == 'game-rules-b' else 1
            pid = pids[(lane_name, scenario)]
            command = self.make_command(
                lane_name + '-' + suffix,
                self.scenario_argv(lane_name, version, method_key, signed_name, mode,
                                   multiplier),
                self.settings(lane_name), pid,
                self.scenario_text(mode, version, multiplier).replace('\n', '\r\n').encode('utf-8'))
            self.commands.append(command)
            records = self.observation_records(lane_name, ready, pid, version,
                                               scenario, staged_a, staged_b, method_key)
            obs_path = self.root / 'observations' / (lane_name + '-' + suffix + '.jsonl')
            obs_path.write_text('\n'.join(json.dumps(record, separators=(',', ':'))
                                          for record in records) + '\n', encoding='utf-8')
            lane[scenario] = {
                'name': command['name'], 'record': deepcopy(command),
                'text': self.scenario_text(mode, version, multiplier),
                'fields': observations.expected_facts(
                    mode, version, multiplier,
                    'LastKnownGood' if mode == 'recover' else 'Candidate'),
                'obsPath': str(obs_path), 'observations': records,
            }
            staged_path = staged_a if staged_key == 'stagedA' else staged_b
            manifest = self.manifest_a if version == 'game-rules-a' else self.manifest_b
            staged = {
                'receiptSha': receipt_a if staged_key == 'stagedA' else receipt_b,
                'contentRoot': content_a if staged_key == 'stagedA' else content_b,
                'entryPath': 'TrustedGame.Update.dll',
                'stagedPath': str(staged_path),
                'stagedSha': sha256_file(staged_path),
                'manifest': deepcopy(manifest),
            }
            lane[staged_key] = staged
        return lane

    def scenario_argv(self, lane_name, version, method_key, signed_name, mode, multiplier):
        host = str(self.r2r['Host'])
        module_dir = str(self.r2r[method_key].parent)
        signed = str(self.signing / signed_name)
        releases = str(self.root / 'lanes' / lane_name / 'releases')
        receipt = str(self.root / 'lanes' / lane_name / 'receipt.json')
        common = [str(self.dotnet), 'exec', '--fx-version', '12.0.0', host]
        if mode == 'stage':
            return common + ['--stage-signed', module_dir, '--signed', signed,
                             '--spki', str(self.spki), '--releases-root', releases,
                             '--receipt', receipt, '--expected-score-multiplier',
                             str(multiplier)]
        return common + ['--recover-signed', '--spki', str(self.spki),
                         '--releases-root', releases, '--receipt', receipt,
                         '--expected-score-multiplier', str(multiplier)]

    def scenario_text(self, mode, version, multiplier):
        facts = observations.expected_facts(
            mode, version, multiplier,
            'LastKnownGood' if mode == 'recover' else 'Candidate')
        values = (1, 3, 6) if multiplier == 1 else (2, 6, 12)
        lines = [
            'CALLERDLL path=' + str(self.leaf) + ' hash=' + sha256_file(self.leaf) +
            ' module=TrustedGame.Update',
            'SIGNED-FACTS ' + ' '.join(key + '=' + value for key, value in facts.items()),
            'TRUSTED-GAME normal results=' + ','.join(map(str, values)) +
            ' score=' + str(values[2]) + ' ticks=3 multiplier=' + str(multiplier),
            'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0',
            'TRUSTED-GAME OK',
        ]
        return '\n'.join(lines) + '\n'

    def observation_records(self, lane_name, ready, pid, version, scenario,
                            staged_a, staged_b, method_key):
        records = []
        base = 0x100000000 + pid * 0x100000
        staged = staged_a if version == 'game-rules-a' else staged_b
        for ordinal in (1, 2, 3):
            for role in ('Host', 'Tick'):
                if ready:
                    if role == 'Host':
                        path = str(self.r2r['Host'])
                        image_sha = self.images['Host']['r2rSha']
                        start = self.specs['Host'][0]
                    else:
                        path = str(staged)
                        image_sha = self.images[method_key]['r2rSha']
                        start = self.specs[method_key][0]
                    offset = start + 16
                else:
                    path = str(self.coreclr)
                    image_sha = sha256_file(self.coreclr)
                    offset = 0x2050
                pc = base + offset
                query_base = pc - 0x100
                records.append({
                    'recordType': 'CallerObservation', 'pid': pid,
                    'callId': str(pid) + ':' + version + ':' + str(ordinal) + ':' + role,
                    'role': role, 'version': version, 'ordinal': ordinal,
                    'pc': hex(pc), 'vqStatus': 'ok', 'vqError': 0,
                    'queryBase': hex(query_base), 'queryRegionSize': '0x1000',
                    'inQueryRegion': True, 'allocBase': hex(base),
                    'regionSize': '0x1000', 'state': '0x1000', 'protect': '0x20',
                    'type': '0x1000000', 'mapStatus': 'ok', 'mapLength': 128,
                    'mapError': 0, 'pathStatus': 'ok',
                    'device': '\\Device\\HarddiskVolume1',
                    'volume': 'C:=\\Device\\HarddiskVolume1',
                    'canonical': path, 'hashStatus': 'ok', 'fileHash': image_sha,
                    'headerStatus': 'ok', 'headerMachine': '0x8664',
                    'headerError': 0, 'exception': 'none', 'hresult': 0,
                })
        return records

    def write_inputs(self):
        write_json(self.root / 'images.json', self.images)
        write_json(self.root / 'bindings.json', self.bindings)
        write_json(self.root / 'preflight.json', self.preflight)
        write_json(self.root / 'commands.json', self.commands)
        write_json(self.root / 'lanes.json', self.lanes)
        write_json(self.root / 'raw-log-hashes.json', self.raw_logs)
        write_json(self.root / 'checker-full.json',
                   {'passed': False, 'error': 'disabled-type 0x1000000'})
        write_json(self.root / 'failure.json',
                   {'passed': False, 'error': "KeyError: 'stagedA'",
                    'at': '2026-10-20T00:00:00+00:00'})
        (self.root / 'parent.exit.txt').write_text('1\n', encoding='ascii')

    def load(self):
        return {
            'lanes': load_json(self.root / 'lanes.json'),
            'bindings': load_json(self.root / 'bindings.json'),
            'images': load_json(self.root / 'images.json'),
            'commands': load_json(self.root / 'commands.json'),
            'preflight': load_json(self.root / 'preflight.json'),
            'raw_logs': load_json(self.root / 'raw-log-hashes.json'),
        }


def expect_reject(label, fn):
    try:
        fn()
    except Exception as error:
        print('PASS reject ' + label + ' :: ' + type(error).__name__ + ': ' + str(error))
        return
    raise AssertionError('accepted ' + label)


def run_cli(run_root, output, extra=()):
    return subprocess.run(
        [sys.executable, '-B', str(CLI), '--run-root', str(run_root),
         '--output', str(output)] + list(extra),
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace')


def load_records(root):
    records = []
    for path in sorted((Path(root) / 'observations').glob('*.jsonl')):
        records.extend(observations.parse_observations(
            path.read_text(encoding='utf-8')))
    return records


def build(data, root, **overrides):
    values = {key: deepcopy(data[key]) for key in
              ('lanes', 'bindings', 'images', 'commands', 'preflight', 'raw_logs')}
    values.update(overrides)
    return builder.build_expected(
        values['lanes'], values['bindings'], values['images'],
        values['commands'], values['preflight'], values['raw_logs'], root)


def test_builder_and_replay(temp, fixture, data):
    assert ' ' in str(fixture.root), 'fixture root must contain a space'
    expected = build(data, fixture.root)
    assert len(expected['calls']) == 36
    assert sum(1 for call in expected['calls'] if call['image'] is True) == 18
    assert sum(1 for call in expected['calls'] if call['image'] is False) == 18
    for call in expected['calls']:
        want = 'Host' if call['role'] == 'Host' else (
            'A' if call['version'] == 'game-rules-a' else 'B')
        assert call['methodKey'] == want, call
    print('PASS derived 36 calls from commands/images/maps/PE/receipts/logs')

    records = load_records(fixture.root)
    assert len(records) == 36
    result = replay.replay(records, expected, data['bindings'],
                           str(fixture.coreclr), sha256_file(fixture.coreclr))
    assert result['targetImageBindings'] == 18
    assert result['runtimeImageObservations'] == 18
    assert result['interpreterIdentityProven'] is False
    assert result['targetMethodBodyProven'] is False
    assert result['overallAcceptance'] is False
    print('PASS replay target18/runtime18 with false interpreter/method/overall')

    for lane in data['lanes']:
        for scenario, mode, version, multiplier, source in (
            ('stageA', 'stage', 'game-rules-a', 1, 'Candidate'),
            ('stageB', 'stage', 'game-rules-b', 2, 'Candidate'),
            ('recoverB', 'recover', 'game-rules-b', 2, 'LastKnownGood'),
        ):
            text = lane[scenario]['text']
            fields = observations.parse_signed_facts(text)
            observations.check_facts(fields, mode, version, multiplier, source)
            observations.check_gameplay(text, multiplier)
            observations.check_caller_line(text, fixture.leaf, sha256_file(fixture.leaf))
    print('PASS strict SIGNED-FACTS/gameplay/CALLERDLL for six scenarios')
    return expected, records


def test_cli_positive(temp, fixture, expected):
    output = Path(temp) / 'report'
    completed = run_cli(fixture.root, output)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    report_path = output / 'report.json'
    sha_path = output / 'report.sha256'
    assert report_path.is_file() and sha_path.is_file()
    digest = sha256_file(report_path)
    assert sha_path.read_text(encoding='ascii').strip() == digest + '  report.json'
    report = load_json(report_path)
    assert report['expected']['callCount'] == 36
    assert report['observations']['targetImageBindings'] == 18
    assert report['observations']['runtimeImageObservations'] == 18
    assert report['checks']['observationChecksPassed'] is True
    assert report['checks']['derivedExpectedFromRunRoot'] is True
    assert report['acceptance']['overallAcceptance'] is False
    assert report['acceptance']['interpreterIdentityProven'] is False
    assert report['acceptance']['targetMethodBodyProven'] is False
    assert report['acceptance']['originalPolicyPassed'] is False
    assert report['acceptance']['originalPolicyRecomputed'] is False
    assert report['originalPolicy']['historical'] is True
    assert report['originalPolicy']['error'] == 'disabled-type 0x1000000'
    assert report['historicalParent']['error'] == "KeyError: 'stagedA'"
    assert report['historicalParent']['exitCode'] == 1
    assert report['pins']['allUnchanged'] is True
    assert report['pins']['inputs'] and report['pins']['raw']
    assert not [path for path in
                list(report['pins']['inputs']) + list(report['pins']['raw'])
                if 'private' in path.lower()]
    assert sha256_file(fixture.private_key) == sha256_bytes(b'NOT A REAL PRIVATE KEY')
    assert report['expected']['sha256'] == sha256_bytes(
        canonical_json(expected).encode('utf-8'))
    print('PASS maintained CLI wrote report.json/report.sha256; pins unchanged; no key pin')
    second = Path(temp) / 'report-2'
    completed = run_cli(fixture.root, second)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert (second / 'report.json').read_bytes() == report_path.read_bytes()
    print('PASS report bytes are deterministic for the same run root')
    return output, report


def test_output_refusals(temp, fixture):
    existing = Path(temp) / 'existing-output'
    existing.mkdir()
    sentinel = existing / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')
    completed = run_cli(fixture.root, existing)
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    assert sentinel.read_text(encoding='utf-8') == 'keep'
    assert not (existing / 'report.json').exists()
    print('PASS existing output refused before writes (sentinel untouched)')

    inside = fixture.root / 'output-inside'
    completed = run_cli(fixture.root, inside)
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    assert not inside.exists()
    print('PASS output inside run root refused before writes')


def test_validation_failure_no_report(temp, fixture):
    tampered = Path(temp) / 'tampered-run'
    shutil.copytree(fixture.root, tampered)
    log = tampered / 'logs' / 'r2r0-stage-A.stdout'
    log.write_bytes(log.read_bytes() + b'X')
    output = Path(temp) / 'tampered-report'
    completed = run_cli(tampered, output)
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert not output.exists()
    print('PASS validation failure returned 2 and created no output')


def test_no_external_expected(temp, fixture):
    output = Path(temp) / 'no-expected-input'
    completed = run_cli(fixture.root, output, ['--expected', 'anything.json'])
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert not output.exists()
    assert 'unrecognized arguments' in completed.stderr
    print('PASS CLI has no trusted --expected input')


def test_builder_negatives(fixture, data, expected):
    root = fixture.root

    duplicate = deepcopy(next(item for item in data['commands']
                              if item['name'] == 'r2r1-stage-A'))
    expect_reject('duplicate-command-name',
                  lambda: build(data, root,
                                commands=data['commands'] + [duplicate]))

    def mutate_lane(fn, label):
        lanes = deepcopy(data['lanes'])
        fn(lanes)
        expect_reject(label, lambda: build(data, root, lanes=lanes))

    def mutate_record_and_command(fn, label):
        lanes = deepcopy(data['lanes'])
        commands = deepcopy(data['commands'])
        record = lanes[0]['stageA']['record']
        command = next(item for item in commands if item['name'] == record['name'])
        fn(record)
        fn(command)
        expect_reject(label, lambda: build(data, root, lanes=lanes,
                                           commands=commands))

    mutate_record_and_command(
        lambda item: item.update({'exitCode': False}), 'record-exit-bool-false')
    mutate_record_and_command(
        lambda item: item.update({'exitCode': 0.0}), 'record-exit-float-zero')
    mutate_record_and_command(
        lambda item: item.update({'exitCode': 1}), 'record-exit-one')
    mutate_record_and_command(
        lambda item: item.update({'startStatus': 'failed'}), 'record-start-status')
    mutate_record_and_command(
        lambda item: item.update({'endedStatus': 'killed'}), 'record-ended-status')
    mutate_record_and_command(
        lambda item: item.update({'stdoutBytes': 1}), 'record-stdout-bytes')
    mutate_record_and_command(
        lambda item: item.update({'stderrBytes': 1}), 'record-stderr-bytes')
    mutate_record_and_command(
        lambda item: item.update({'timedOut': True}), 'record-timeout')
    mutate_record_and_command(
        lambda item: item.update(
            {'stdout': str(root / 'logs' / 'does-not-exist.stdout')}),
        'record-stdout-missing')
    mutate_record_and_command(
        lambda item: item.update(
            {'stdout': data['lanes'][1]['stageA']['record']['stdout']}),
        'record-stdout-swapped')
    mutate_record_and_command(
        lambda item: item['settings'].update({'DOTNET_InterpMode': '0'}),
        'record-interpmode')
    mutate_record_and_command(
        lambda item: item['argv'].__setitem__(
            item['argv'].index('--signed') + 1, str(fixture.b_signed)),
        'record-signed-lineage')
    mutate_record_and_command(
        lambda item: item['argv'].__setitem__(
            item['argv'].index('--expected-score-multiplier') + 1, '2'),
        'record-multiplier-lineage')
    mutate_record_and_command(
        lambda item: item['argv'].__setitem__(4, str(root / 'wrong-Host.dll')),
        'record-host-lineage')

    commands = deepcopy(data['commands'])
    next(item for item in commands if item['name'] == 'publish-A')['exitCode'] = False
    expect_reject('command-exit-bool-false',
                  lambda: build(data, root, commands=commands))
    commands = deepcopy(data['commands'])
    next(item for item in commands if item['name'] == 'publish-B')['exitCode'] = 0.0
    expect_reject('command-exit-float-zero',
                  lambda: build(data, root, commands=commands))
    commands = deepcopy(data['commands'])
    next(item for item in commands if item['name'] == 'assembly-identities')[
        'exitCode'] = True
    expect_reject('command-exit-bool-true',
                  lambda: build(data, root, commands=commands))

    mutate_lane(lambda lanes: lanes[0]['stagedA'].update(
        {'stagedPath': str(root / 'lanes.json')}), 'module-path')
    mutate_lane(lambda lanes: lanes[0]['stagedA']['manifest'].update(
        {'version': 'game-rules-b'}), 'staged-version')
    mutate_lane(lambda lanes: lanes[0]['stagedA'].update(
        {'receiptSha': lanes[0]['receiptB']}), 'staged-a-superseded-receipt')
    mutate_lane(lambda lanes: lanes[0]['stagedB'].update(
        {'receiptSha': '0' * 64}), 'staged-b-receipt')
    mutate_lane(lambda lanes: lanes[0].update(
        {'receiptRecover': '0' * 64}), 'receipt-recover')
    mutate_lane(lambda lanes: lanes[0]['stageA']['fields'].update(
        {'version': 'game-rules-b'}), 'scenario-version-lineage')

    images = deepcopy(data['images'])
    images['A']['r2rMvid'] = '00000000-0000-0000-0000-000000000001'
    expect_reject('image-mvid-forged', lambda: build(data, root, images=images))
    images = deepcopy(data['images'])
    images['A']['r2rSha'] = '0' * 64
    expect_reject('image-r2r-sha', lambda: build(data, root, images=images))
    images = deepcopy(data['images'])
    images['A']['ilSha'] = '0' * 64
    expect_reject('image-il-sha', lambda: build(data, root, images=images))
    images = deepcopy(data['images'])
    images['A']['r2rPath'] = images['B']['r2rPath']
    expect_reject('image-a-path-swapped', lambda: build(data, root, images=images))

    bindings = deepcopy(data['bindings'])
    bindings['A']['method']['rva'] = 5800
    expect_reject('binding-rva-inside-pc',
                  lambda: build(data, root, bindings=bindings))
    bindings = deepcopy(data['bindings'])
    bindings['A']['runtimeFunctions'] = [{'begin': 0, 'end': 65536, 'unwind': 0}]
    expect_reject('runtime-function-forged',
                  lambda: build(data, root, bindings=bindings))
    bindings = deepcopy(data['bindings'])
    bindings['A']['sha256'] = '0' * 64
    expect_reject('binding-sha', lambda: build(data, root, bindings=bindings))
    bindings = deepcopy(data['bindings'])
    bindings['A']['executableSections'] = []
    expect_reject('binding-sections',
                  lambda: build(data, root, bindings=bindings))

    with tempfile.TemporaryDirectory() as receipt_temp:
        receipt = load_json(root / 'lanes' / 'r2r0' / 'receipt.json')
        receipt['document'] = receipt['document'][:-8] + 'AAAAAAA='
        bad_receipt = Path(receipt_temp) / 'receipt.json'
        bad_receipt.write_text(json.dumps(receipt), encoding='utf-8')
        r2r0 = next(lane for lane in data['lanes'] if lane['lane'] == 'r2r0')
        expect_reject('receipt-document-forged', lambda: builder.validate_receipt(
            bad_receipt, fixture.b_bytes, fixture.manifest_b,
            r2r0['stagedB']['contentRoot']))

    broken = data['lanes'][0]['stageA']['text'] + (
        'TRUSTED-GAME normal results=999 score=999 ticks=3 multiplier=1\n')
    expect_reject('extra-normal-999',
                  lambda: observations.check_gameplay(broken, 1))
    expect_reject('duplicate-normal', lambda: observations.check_gameplay(
        data['lanes'][0]['stageA']['text'] +
        'TRUSTED-GAME normal results=1,3,6 score=6 ticks=3 multiplier=1\n', 1))
    expect_reject('unknown-gameplay-row', lambda: observations.check_gameplay(
        data['lanes'][0]['stageA']['text'] + 'TRUSTED-GAME unexpected\n', 1))
    expect_reject('out-of-order-gameplay', lambda: observations.check_gameplay(
        'TRUSTED-GAME OK\n' + data['lanes'][0]['stageA']['text'], 1))
    print('PASS builder/record/command/image/map/receipt/facts negatives')


def test_observation_negatives(fixture, data, expected):
    records = load_records(fixture.root)
    runtime_sha = sha256_file(fixture.coreclr)

    def replay_records(items, exp=None):
        return replay.replay(items, exp or expected, data['bindings'],
                             str(fixture.coreclr), runtime_sha)

    target_index = next(index for index, record in enumerate(records)
                        if record['fileHash'] != runtime_sha)
    runtime_index = next(index for index, record in enumerate(records)
                         if record['fileHash'] == runtime_sha)
    target = records[target_index]
    runtime = records[runtime_index]

    def rec(index, key, value):
        bad = deepcopy(records)
        bad[index][key] = value
        return bad

    expect_reject('duplicate-observation',
                  lambda: replay_records(records + [deepcopy(records[0])]))
    expect_reject('missing-observation',
                  lambda: replay_records(records[:-1]))
    expect_reject('cross-call-id', lambda: replay_records(
        rec(target_index, 'callId', 'wrong:call:id:Host')))
    expect_reject('cross-role', lambda: replay_records(
        rec(target_index, 'role', 'Tick')))
    expect_reject('target-path', lambda: replay_records(
        rec(target_index, 'canonical', str(fixture.root / 'copy.dll'))))
    expect_reject('target-sha', lambda: replay_records(
        rec(target_index, 'fileHash', '0' * 64)))
    expect_reject('target-query', lambda: replay_records(
        rec(target_index, 'vqStatus', 'error')))
    interval = rec(target_index, 'pc',
                   hex(int(target['allocBase'], 16) + 0x9000))
    interval[target_index].update({
        'queryBase': target['allocBase'], 'queryRegionSize': '0x10000',
        'inQueryRegion': True})
    expect_reject('target-interval', lambda: replay_records(interval))
    expect_reject('target-type', lambda: replay_records(
        rec(target_index, 'type', '0x40000')))
    expect_reject('runtime-path', lambda: replay_records(
        rec(runtime_index, 'canonical', target['canonical'])))
    expect_reject('runtime-sha', lambda: replay_records(
        rec(runtime_index, 'fileHash', target['fileHash'])))
    expect_reject('runtime-query', lambda: replay_records(
        rec(runtime_index, 'vqError', 5)))
    bad_section = deepcopy(records)
    bad_section[runtime_index].update({
        'pc': hex(int(runtime['allocBase'], 16) + 0x100),
        'queryBase': runtime['allocBase'], 'queryRegionSize': '0x1000',
        'inQueryRegion': True})
    expect_reject('runtime-section', lambda: replay_records(bad_section))
    expect_reject('runtime-target-masquerade', lambda: replay_records(
        rec(runtime_index, 'canonical', target['canonical'])))

    bad_expected = deepcopy(expected)
    tick = next(call for call in bad_expected['calls']
                if call['role'] == 'Tick' and call['version'] == 'game-rules-a')
    tick['methodKey'] = 'B'
    expect_reject('forged-method-key-lineage',
                  lambda: replay_records(records, bad_expected))
    print('PASS observation/path/sha/query/interval/lineage negatives')


def test_query_protect(fixture):
    records = load_records(fixture.root)
    base = next(record for record in records
                if record.get('inQueryRegion') is True)
    for value in ('0x10', '0x20', '0x40', '0x80'):
        record = deepcopy(base)
        record['protect'] = value
        replay.check_query(record, ('protect-valid', value))
    for value, label in (('0x30', 'read-execute-combination'),
                         ('0x60', 'read-write-execute-combination'),
                         ('0x04', 'non-executable'),
                         ('0x120', 'guard-with-execute')):
        record = deepcopy(base)
        record['protect'] = value
        expect_reject('protect-' + label,
                      lambda record=record: replay.check_query(
                          record, ('protect-invalid', value)))
    print('PASS protect exact exec bits; reject 0x30/0x60/guard/nonexec')


def test_caller_line(fixture):
    leaf = fixture.leaf
    digest = sha256_file(leaf)
    valid = ('CALLERDLL path=' + str(leaf) + ' hash=' + digest +
             ' module=TrustedGame.Update')
    observations.check_caller_line(valid, leaf, digest)
    synthetic = 'C:/synthetic path/caller_leaf.dll'
    synthetic_digest = '0123456789abcdef' * 4
    observations.check_caller_line(
        'CALLERDLL path=' + synthetic + ' hash=' + synthetic_digest +
        ' module=TrustedGame.Update', synthetic, synthetic_digest)
    print('PASS CALLERDLL accepts unquoted path with spaces')
    prefix = 'CALLERDLL path=' + str(leaf)
    cases = (
        ('duplicate-path', prefix + ' path=' + str(leaf) + ' hash=' + digest +
         ' module=TrustedGame.Update'),
        ('duplicate-hash', prefix + ' hash=' + digest + ' hash=' + digest +
         ' module=TrustedGame.Update'),
        ('duplicate-module', prefix + ' hash=' + digest +
         ' module=TrustedGame.Update module=TrustedGame.Update'),
        ('malformed-hash', prefix + ' hash=' + digest[:-1] +
         ' module=TrustedGame.Update'),
        ('missing-module', prefix + ' hash=' + digest),
        ('extra-field', prefix + ' hash=' + digest +
         ' extra=1 module=TrustedGame.Update'),
        ('wrong-module', prefix + ' hash=' + digest + ' module=Other'),
    )
    for label, text in cases:
        expect_reject('caller-line-' + label,
                      lambda text=text: observations.check_caller_line(
                          text, leaf, digest))
    print('PASS CALLERDLL duplicate/malformed-field rejection retained')


def test_forged_interval(fixture, data, temp):
    forged_map = Path(temp) / 'forged-interval.map.csv'
    bindings = deepcopy(data['bindings'])
    method = bindings['A']['method']
    write_map(forged_map, 5790, 210, method['symbol'])
    method['mapPath'] = str(forged_map)
    method['rva'] = 5790
    method['length'] = 210
    method['mapSha'] = sha256_file(forged_map)
    forged_expected = build(data, fixture.root, bindings=bindings)
    forged_records = load_records(fixture.root)
    expect_reject('forged-map-interval-derived-then-observation-rejected',
                  lambda: replay.replay(
                      forged_records, forged_expected, bindings,
                      str(fixture.coreclr), sha256_file(fixture.coreclr)))
    print('PASS forged map interval is rebuilt from actual map and fails replay')


def test_parsers(fixture, data):
    records = load_records(fixture.root)
    spaced = deepcopy(records[0])
    spaced['canonical'] = r'C:\method proof\run 2\TrustedGame.Host.dll'
    assert observations.parse_observations(
        json.dumps(spaced))[0]['canonical'] == spaced['canonical']
    print('PASS path-with-space JSONL round trip')
    expect_reject('duplicate-json-key', lambda: observations.parse_observations(
        '{"recordType":"CallerObservation","role":"Host","role":"Tick"}'))
    expect_reject('malformed-json-line',
                  lambda: observations.parse_observations('not-json\n'))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path,
                        help='optional retained run root for an actual read-only replay')
    args = parser.parse_args()

    temp = tempfile.TemporaryDirectory(prefix='runeclr-observations-')
    temp_path = Path(temp.name)
    try:
        fixture = Fixture(temp_path / 'run with spaces')
        data = fixture.load()
        expected, _ = test_builder_and_replay(temp_path, fixture, data)
        test_cli_positive(temp_path, fixture, expected)
        test_output_refusals(temp_path, fixture)
        test_validation_failure_no_report(temp_path, fixture)
        test_no_external_expected(temp_path, fixture)
        test_builder_negatives(fixture, data, expected)
        test_observation_negatives(fixture, data, expected)
        test_query_protect(fixture)
        test_caller_line(fixture)
        test_forged_interval(fixture, data, temp_path)
        test_parsers(fixture, data)
    finally:
        temp.cleanup()
    assert not temp_path.exists(), 'temporary directory was not cleaned'
    print('PASS system temporary directory cleaned')

    if args.run_root:
        actual_temp = tempfile.TemporaryDirectory(prefix='runeclr-actual-')
        try:
            output = Path(actual_temp.name) / 'report'
            completed = run_cli(args.run_root, output)
            assert completed.returncode == 0, (completed.stdout, completed.stderr)
            report = load_json(output / 'report.json')
            assert report['observations']['targetImageBindings'] == 18
            assert report['observations']['runtimeImageObservations'] == 18
            assert report['acceptance']['overallAcceptance'] is False
            assert report['acceptance']['interpreterIdentityProven'] is False
            assert report['checks']['observationChecksPassed'] is True
            assert report['pins']['allUnchanged'] is True
            assert report['originalPolicy']['historical'] is True
            assert report['originalPolicy']['recomputed'] is False
            assert report['originalPolicy']['passed'] is False
            assert report['historicalParent']['historical'] is True
            assert report['historicalParent']['recomputed'] is False
            if 'error' in report['historicalParent']:
                assert isinstance(report['historicalParent']['error'], str)
                assert report['historicalParent']['error']
            if 'exitCode' in report['historicalParent']:
                assert type(report['historicalParent']['exitCode']) is int
            assert not [path for path in
                        list(report['pins']['inputs']) + list(report['pins']['raw'])
                        if 'private' in path.lower()]
            print('PASS actual retained run: target18/runtime18, overall false, '
                  'pins unchanged, no key pin')
        finally:
            actual_temp.cleanup()
    else:
        print('SKIP actual retained-data check (pass --run-root to enable)')
    print('TRUSTED_GAME_OBSERVATIONS_TESTS PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
