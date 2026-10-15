#!/usr/bin/env python3
"""Recheck archived simulator capture without launching a target or debugger."""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path


def review(root):
    tools = root / 'source-freeze/eng'
    driver = tools / 'ios-fresh-author-entry-capture-v2-live.py'
    spec = importlib.util.spec_from_file_location('archived_live_capture', driver)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    candidates = [p for p in root.iterdir() if (p / 'run-results.json').is_file()]
    m.need(len(candidates) == 1, 'Exactly one archived live run required')
    capture = candidates[0]
    run = m.read(capture / 'run-results.json')
    request = m.read(capture / 'request.json')
    planned = m.read(capture / 'live-results.json')
    config = m.read(capture / 'diagnostic/capture-config.json')
    diagnostic = m.read(capture / 'diagnostic/results.json')
    install = m.read(capture / 'installation/results.json')
    compiled = m.read(capture / 'author-compilation-after-install/results.json')
    delivered = m.read(capture / 'author-readback.json')
    bindings = root / 'bindings'
    identity = m.read(bindings / 'identity.json')
    state = m.read(bindings / 'state.json')
    native = m.read(bindings / 'native-bind-receipt.json')
    m.need(run['passed'] is True and run['cleanupSucceeded'] is True
           and run['physicalDeviceExecuted'] is False and run['debugObserver'] is False,
           'Successful non-debug-observer simulator run required')
    m.need(all(run.get(key) == value for key, value in diagnostic.items())
           and run['pid'] == config['pid'] and run['nonce'] == config['nonce']
           and run['methodGroups'] == 9 and run['contexts'] == 73 and run['cases'] == 15
           and run['debuggerTargetExitStatus'] == 0 and run['actualTargetExitObservedByDebugger'] is True,
           'Diagnostic/final summary owner or completion differs')
    m.need(run['driverSha256'] == request['liveDriverSha256'] == m.sha(driver)
           and planned['requestSha256'] == m.sha(capture / 'request.json')
           and request['requestContract'] == m.LIVE_CONTRACT, 'Archived driver/plan differs')
    for name, field in (('identity.json', 'prepareIdentitySha256'), ('state.json', 'stateSha256'),
                        ('native-bind-receipt.json', 'nativeBindReceiptSha256'),
                        ('native-review.json', 'nativeBindReviewSha256')):
        m.need(m.sha(bindings / name) == request[field], 'Archived binding differs: ' + name)
    m.need(native['passed'] and native['nativeUuid'] == config['nativeUuid']
           == identity['sourceNative']['uuid'], 'Native image identity differs')
    m.need(config['paths'] == request['paths']
           and config['threadContract'] == request['threadContract']
           and config['hitCap'] == request['hitCap']
           and config['requiredMethods'] == identity['requiredMethods']
           and config['methodPhases'] == request['methodPhases']
           and config['gate'] == identity['gate'], 'Actual configuration differs from plan')
    m.need(config['layouts'] == dict(identity['layouts'], **request['layouts'], **m.old().OWNER_LAYOUTS),
           'Actual layout differs from bound identity')
    for kind, (prefix, pc) in native['paths'].items():
        m.need(config['paths'][kind]['prefixHex'] == prefix and config['paths'][kind]['filePc'] == pc,
               'Actual native path differs: ' + kind)
    m.need(config['paths']['ordinary-child-dispatch']['opcodeAddressAdvance'] == 0
           and config['paths']['delegate-child-dispatch']['opcodeAddressAdvance'] == 8,
           'Versioned opcode pointer contract differs')
    dest = capture / 'diagnostic'
    observer = dest / 'fresh_author_entry_v2_lldb.py'
    m.need(m.sha(observer) == run['observerSha256'] == request['observerSha256'], 'Actual observer differs')
    hits = m.read(dest / 'capture-hits.json')
    m.need(hits['allRequiredCovered'] and hits['disabledAfterCoverage'] and hits['entries'] == 9
           and hits['errors'] == 0 and 9 <= hits['hits'] <= config['hitCap']
           and not (dest / 'capture-errors.json').exists(), 'Actual capture incomplete')
    m.verify_capture(dest, config, m.read(dest / 'breakpoints.json'))
    host = m.old().helper('ios-fresh-author-simulator-continuation.py', m.old().CONTINUATION_SHA)
    m.validate_completion(dest, config, host)
    before, after = m.read(dest / 'installed-before.json'), m.read(dest / 'installed-after.json')
    m.need(before == after and before['bundle'] == state['bundleHashes']
           and before['author'] == compiled['authorHashes'] == delivered['authorHashes'],
           'Archived installed input inventories differ')
    m.need(install['passed'] and install['authorDirectoryAbsent'] and install['appLaunched'] is False
           and install['stateSha256'] == request['stateSha256']
           and delivered['installReceiptSha256'] == m.sha(capture / 'installation/results.json')
           and delivered['compilerResultSha256'] == m.sha(capture / 'author-compilation-after-install/results.json')
           and datetime.fromisoformat(compiled['startedAfterHostBindingUtc']) > datetime.fromisoformat(install['readbackUtc']),
           'Compilation/delivery must follow diagnostic installation')
    pe = m.old().helper('ios-fresh-author-entry-prepare.py', m.old().PREPARE_SHA).readers()
    for name, author in config['authors'].items():
        path = capture / 'author-compilation-after-install/plugin' / name
        methods = pe['plugin_methods'](path, required=tuple(author['methods']), qualified=True)
        m.need(m.sha(path) == author['sha256'] == compiled['authorHashes'][name]
               and author['path'] == delivered['plugin'] + '/' + name
               and pe['il_layout'](path) == {'ilOnly': True, 'managedNativeRva': 0}
               and pe['pe_mvid'](path)['moduleMvid'] == author['moduleMvid']
               and author['moduleMvid'] != identity['modules'][name]['moduleMvid']
               and {name: methods[name] for name in author['methods']} == author['methods'],
               'Preserved fresh author metadata differs: ' + name)
    cleanup = m.read(capture / 'cleanup/results.json')
    devices = m.read(capture / 'cleanup/devices-after.json')
    m.need(cleanup['passed'] and cleanup['deleted'] and cleanup['simulator'] == install['simulator']
           and not any(x['udid'] == install['simulator'] for rows in devices['devices'].values() for x in rows),
           'Owned simulator retirement differs')
    audit = m.module('archived_budget_audit', tools / 'mobile-host-budget-audit.py', m.BUDGET_AUDIT_SHA)
    aggregate, receipts, _, _ = audit.adapter(dest / 'adapter-evidence', config['nonce'], config['pid'])
    controls = audit.negative_controls(aggregate, receipts, config['nonce'], config['pid'])
    observed = sorted({x['kind'] for x in m.read(dest / 'interpreter-entries.json')})
    m.need(observed == run['observedEntryPaths'], 'Observed path summary differs')
    return {'passed': True, 'methodGroups': 9, 'observedEntryPaths': observed, 'cases': 15,
            'contexts': 73, 'semanticCorruptionControls': len(controls), 'targetExit': 0,
            'cleanupSucceeded': True, 'physicalDeviceExecuted': False,
            'offlineReview': True, 'targetProcessCreatedByReview': False,
            'driverSha256': m.sha(driver), 'runResultSha256': m.sha(capture / 'run-results.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = review(args.archive_root.resolve())
    if args.output:
        with args.output.open('x', encoding='ascii') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
