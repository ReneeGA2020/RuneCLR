#!/usr/bin/env python3
"""Compare the iOS startup plan with TryPlanCandidate. This does not start a simulator."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def load_driver():
    spec = importlib.util.spec_from_file_location(
        'ios_trusted_update_driver', Path(__file__).with_name('ios-trusted-update.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def additional_spec(additional):
    if not additional:
        return '-'
    return '|'.join(str(item['path']) + chr(9) + str(item['contentSha256']) for item in additional)


def csharp_plan(path, version, manifest, approval, host_target, candidate_target, content_root=None, additional=None):
    spec = '-'
    if approval is not None:
        spec = chr(9).join((str(approval['versionName']), str(approval['contentSha256']), str(approval['approvalId'])))
    repo = Path(__file__).resolve().parents[1]
    dll = repo / 'tests' / 'RuneCLR.TrustedUpdate.Tests' / 'bin' / 'Release' / 'net11.0' / 'RuneCLR.TrustedUpdate.Tests.dll'
    command = [
        'dotnet', 'exec', str(dll),
        '--plan', str(path), str(version), str(manifest),
        str(candidate_target[0]), str(candidate_target[1]),
        str(host_target[0]), str(host_target[1]), spec, '-' if content_root is None else str(content_root),
        additional_spec(additional),
    ]
    completed = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    line = next((item.strip() for item in (completed.stdout or '').splitlines() if item.startswith('PLAN ')), '')
    if completed.returncode != 0 or not line.startswith('PLAN '):
        detail = (completed.stdout or '') + (completed.stderr or '')
        return 'probe-failed: ' + detail[-400:]
    return line.split(' ', 1)[1]


def main():
    driver = load_driver()
    root = Path(tempfile.mkdtemp(prefix='runeclr-plan-parity-'))
    errors = []
    try:
        payload = root / 'TrustedUpdate.Update.dll'
        payload.write_bytes(b'runeclr-plan-parity')
        digest = driver.sha(payload)
        approval = {'approvalId': 'parity', 'versionName': 'B', 'contentSha256': digest}
        host = ('net11.0', 'arm64')
        candidate = ('net11.0', 'arm64')
        cases = [
            ('match', payload, 'B', digest, approval, host, candidate, None, 'None'),
            ('missing', root / 'missing.dll', 'B', digest, approval, host, candidate, None, 'MissingContent'),
            ('hash', payload, 'B', '0' * 64, approval, host, candidate, None, 'ContentHashMismatch'),
            ('unapproved', payload, 'B', digest, None, host, candidate, None, 'NotApproved'),
            ('wrong-approval-hash', payload, 'B', digest, {**approval, 'contentSha256': '0' * 64}, host, candidate, None, 'NotApproved'),
            ('target', payload, 'B', digest, approval, host, ('net11.0', 'x64'), None, 'IncompatibleTarget'),
            ('blank-target', payload, 'B', digest, approval, ('', 'arm64'), candidate, None, 'InvalidCandidate'),
            ('blank-version', payload, '  ', digest, approval, host, candidate, None, 'InvalidCandidate'),
            ('inside-root', payload, 'B', digest, approval, host, candidate, payload.parent, 'None'),
            ('outside-root', payload, 'B', digest, approval, host, candidate, root / 'other', 'OutsideContentRoot'),
            ('dotdot-inside', (root / 'inside' / 'nested' / '..' / payload.name), 'B', digest, approval, host, candidate, root / 'inside', 'None'),
            ('dotdot-outside', (root / 'inside' / '..' / 'other' / payload.name), 'B', digest, approval, host, candidate, root / 'inside', None, 'OutsideContentRoot'),
        ]
        (root / 'other').mkdir()
        inside = root / 'inside'
        inside.mkdir()
        (inside / 'nested').mkdir()
        (inside / payload.name).write_bytes(payload.read_bytes())
        (root / 'other' / payload.name).write_bytes(payload.read_bytes())
        extra = inside / 'TrustedUpdate.Private.dll'
        extra.write_bytes(b'private-v1')
        (root / 'other' / extra.name).write_bytes(b'private-v1')
        extra_digest = driver.sha(extra)
        inside_payload = inside / payload.name
        matched = [{'path': extra, 'contentSha256': extra_digest}]
        folded = [{'path': inside / 'nested' / '..' / extra.name, 'contentSha256': extra_digest}]
        escaped = [{'path': inside / '..' / 'other' / extra.name, 'contentSha256': extra_digest}]
        cases.extend([
            ('additional-match', inside_payload, 'B', digest, approval, host, candidate, inside, matched, 'None'),
            ('additional-missing', inside_payload, 'B', digest, approval, host, candidate, inside, [{'path': inside / 'absent.dll', 'contentSha256': extra_digest}], 'MissingContent'),
            ('additional-hash', inside_payload, 'B', digest, approval, host, candidate, inside, [{'path': extra, 'contentSha256': '0' * 64}], 'ContentHashMismatch'),
            ('additional-dotdot-inside', inside_payload, 'B', digest, approval, host, candidate, inside, folded, 'None'),
            ('additional-dotdot-outside', inside_payload, 'B', digest, approval, host, candidate, inside, escaped, 'OutsideContentRoot'),
            ('additional-before-approval', inside_payload, 'B', digest, None, host, candidate, inside, [{'path': extra, 'contentSha256': '0' * 64}], 'ContentHashMismatch'),
        ])
        normalized = []
        for row in cases:
            if len(row) == 9:
                row = row[:8] + (None,) + row[8:]
            normalized.append(row)
        for name, path, version, manifest, item_approval, host_target, candidate_target, content_root, additional, expected in normalized:
            python_plan = driver.plan_update_candidate(
                path, version, manifest, item_approval, host_target, candidate_target, content_root, additional)
            dotnet_plan = csharp_plan(path, version, manifest, item_approval, host_target, candidate_target, content_root, additional)
            if python_plan['failure'] != expected or dotnet_plan != expected or python_plan['processStarted'] is not False:
                errors.append('%s expected %s, python %s, dotnet %s' % (name, expected, python_plan['failure'], dotnet_plan))
            if python_plan['assemblyLoadContextCreated'] is not False:
                errors.append('%s python plan loaded an assembly' % name)
        payload_dir = root / "payload"
        payload_dir.mkdir()
        private = payload_dir / "TrustedUpdate.Private.dll"
        helper = payload_dir / "TrustedUpdate.IlOnlyHelper.dll"
        private.write_bytes(b"private-v1")
        helper.write_bytes(b"helper-v1")
        payload_manifest = {"files": {
            private.name: driver.sha(private),
            helper.name: driver.sha(helper),
        }}
        matched = driver.payload_file_failure(payload_manifest, payload_dir)
        if matched is not None:
            errors.append("payload match returned %s" % matched)
        if driver.payload_file_failure(None, payload_dir) is not None or driver.payload_file_failure({}, payload_dir) is not None:
            errors.append("payload check failed without a files map")
        mismatch = driver.payload_file_failure({"files": {private.name: "0" * 64, helper.name: driver.sha(helper)}}, payload_dir)
        if not mismatch or mismatch.get("failure") != "ContentHashMismatch" or mismatch.get("processStarted") is not False:
            errors.append("payload mismatch %s" % mismatch)
        (root / "empty-payload").mkdir()
        missing = driver.payload_file_failure(payload_manifest, root / "empty-payload")
        if not missing or missing.get("failure") != "MissingContent" or missing.get("processStarted") is not False:
            errors.append("payload missing %s" % missing)
        blank = driver.payload_file_failure({"files": {private.name: "  "}}, payload_dir)
        if not blank or blank.get("failure") != "InvalidCandidate" or blank.get("processStarted") is not False:
            errors.append("payload blank %s" % blank)
        lane = root / "rewrite-lane"
        rewritten = lane / "crossgen-out"
        rewritten.mkdir(parents=True)
        (lane / "TrustedUpdate.Update.dll").write_bytes(b"input-update")
        (lane / "TrustedUpdate.Contract.dll").write_bytes(b"input-contract")
        (lane / "TrustedUpdate.AnchorHost.dll").write_bytes(b"input-anchor-host")
        (lane / "TrustedUpdate.AnchorEntry.dll").write_bytes(b"input-anchor-entry")
        (lane / "TrustedUpdate.Private.dll").write_bytes(b"private-v1")
        (lane / "TrustedUpdate.IlOnlyHelper.dll").write_bytes(b"helper-v1")
        (rewritten / "TrustedUpdate.Update.dll").write_bytes(b"rewritten-update")
        (rewritten / "TrustedUpdate.Contract.dll").write_bytes(b"rewritten-contract")
        (rewritten / "TrustedUpdate.AnchorHost.dll").write_bytes(b"rewritten-anchor-host")
        (rewritten / "TrustedUpdate.AnchorEntry.dll").write_bytes(b"rewritten-anchor-entry")
        (rewritten / "TrustedUpdate.A.r2r.dylib").write_bytes(b"owner-dylib")
        staged = root / "staged-payload"
        driver.stage_downloaded_payload(lane, rewritten, staged)
        staged_manifest = {"files": driver.payload_manifest_files(rewritten, lane / "TrustedUpdate.Private.dll", lane / "TrustedUpdate.IlOnlyHelper.dll", rewritten / "TrustedUpdate.A.r2r.dylib")}
        staged_result = driver.payload_file_failure(staged_manifest, staged)
        if staged_result is not None:
            errors.append("rewritten payload %s" % staged_result)
        if (staged / "TrustedUpdate.Update.dll").read_bytes() == b"input-update":
            errors.append("staged update kept the input dll")
        if "TrustedUpdate.Contract.dll" not in staged_manifest["files"] or "TrustedUpdate.AnchorHost.dll" not in staged_manifest["files"] or "TrustedUpdate.AnchorEntry.dll" not in staged_manifest["files"]:
            errors.append("rewritten components missing from payload manifest")
        sentinel = root / "escape-sentinel"
        sentinel.write_bytes(b"sentinel")
        escape_dest = root / "escape-dest"
        escape_dest.mkdir()
        escaped = driver.payload_file_failure({"files": {"../escape-sentinel": driver.sha(sentinel)}}, escape_dest)
        if not escaped or escaped.get("failure") != "InvalidCandidate" or escaped.get("processStarted") is not False:
            errors.append("payload escape %s" % escaped)
        good_dir = root / "startup-good"
        good_dir.mkdir()
        (good_dir / "TrustedUpdate.Private.dll").write_bytes(b"private-v1")
        good_manifest = {"files": {"TrustedUpdate.Private.dll": driver.sha(good_dir / "TrustedUpdate.Private.dll")}}
        bad_dir = root / "startup-bad"
        bad_dir.mkdir()
        (bad_dir / "TrustedUpdate.Private.dll").write_bytes(b"private-v2")
        bad_manifest = {"files": {"TrustedUpdate.Private.dll": driver.sha(good_dir / "TrustedUpdate.Private.dll")}}
        chosen = driver.choose_startup_payload(good_manifest, good_dir, bad_manifest, bad_dir)
        if chosen.get("selected") != "candidate" or chosen.get("processStarted") is not False:
            errors.append("startup candidate %s" % chosen)
        fallback = driver.choose_startup_payload(bad_manifest, bad_dir, good_manifest, good_dir)
        if fallback.get("selected") != "last-known-good" or fallback.get("candidateFailure") != "ContentHashMismatch" or fallback.get("processStarted") is not False or Path(fallback.get("directory")) != good_dir:
            errors.append("startup fallback %s" % fallback)
        neither = driver.choose_startup_payload(bad_manifest, bad_dir, bad_manifest, bad_dir)
        if neither.get("selected") is not None or neither.get("processStarted") is not False:
            errors.append("startup neither %s" % neither)
        escaped_choice = driver.choose_startup_payload({"files": {"../escape-sentinel": driver.sha(sentinel)}}, escape_dest, good_manifest, good_dir)
        if escaped_choice.get("selected") != "last-known-good" or escaped_choice.get("candidateFailure") != "InvalidCandidate":
            errors.append("startup escape %s" % escaped_choice)
        fallback_src = root / "fallback-src"
        fallback_src.mkdir()
        (fallback_src / "TrustedUpdate.Private.dll").write_bytes(b"private-v1")
        (fallback_src / "TrustedUpdate.A.r2r.dylib").write_bytes(b"owner-a")
        (fallback_src / "nested").mkdir()
        (fallback_src / "nested" / "skip.dll").write_bytes(b"nope")
        fallback_dest = root / "fallback-staged"
        staged_payload = driver.stage_plain_payload(fallback_src, fallback_dest)
        if staged_payload.get("processStarted") is not False or "TrustedUpdate.Private.dll" not in staged_payload.get("copied") or "skip.dll" in staged_payload.get("copied") or (fallback_dest / "skip.dll").exists():
            errors.append("stage plain %s" % staged_payload)
        if (fallback_dest / "TrustedUpdate.Private.dll").read_bytes() != b"private-v1":
            errors.append("staged payload did not keep the last known good bytes")
        staged_manifest = {"files": {"TrustedUpdate.Private.dll": driver.sha(fallback_src / "TrustedUpdate.Private.dll"), "TrustedUpdate.A.r2r.dylib": driver.sha(fallback_src / "TrustedUpdate.A.r2r.dylib")}}
        if driver.payload_file_failure(staged_manifest, fallback_dest) is not None:
            errors.append("staged last known good did not match")
        rejected = root / "trusted-update-B"
        kept = root / "trusted-update-last-known-good"
        rejected.mkdir()
        kept.mkdir()
        (rejected / "TrustedUpdate.Private.dll").write_bytes(b"tampered-private")
        (kept / "TrustedUpdate.Private.dll").write_bytes(b"private-v1")
        same = driver.retire_rejected_payload(kept, kept)
        if same.get("retired") is not False or not kept.is_dir():
            errors.append("retire removed the selected payload %s" % same)
        other = root / "not-a-trusted-update"
        other.mkdir()
        (other / "TrustedUpdate.Private.dll").write_bytes(b"keep-me")
        skipped = driver.retire_rejected_payload(other, kept)
        if skipped.get("retired") is not False or not (other / "TrustedUpdate.Private.dll").is_file():
            errors.append("retire removed an unrelated directory %s" % skipped)
        retired = driver.retire_rejected_payload(rejected, kept)
        if retired.get("retired") is not True or retired.get("processStarted") is not False or rejected.exists() or (kept / "TrustedUpdate.Private.dll").read_bytes() != b"private-v1":
            errors.append("retire rejected %s" % retired)
    finally:
        shutil.rmtree(root)
    receipt = {
        'passed': not errors,
        'errors': errors,
        'simulatorReceipt': False,
        'nativeExecutionProven': False,
        'scope': 'local startup-plan agreement and copied payload file hashes; not an iOS simulator receipt',
    }
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
