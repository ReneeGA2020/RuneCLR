#!/usr/bin/env python3
"""Independently review the phase-aware three-path iOS sampler source.

This reviewer is deliberately offline: it never creates, installs, launches, or
attaches to a target.  A later run review may consume the sampler's JSON receipt.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = ROOT / 'eng' / 'ios-fresh-author-entry-capture-v2.py'
EXPECTED_PRIVATE = {
    'HostBudgetProbe.Private.dll:HostBudgetUGC.Private.Helper.Finite',
    'HostBudgetProbe.Private.dll:<>c__DisplayClass0_0.<Finite>b__0',
}
EXPECTED_PATHS = ('function-entry', 'ordinary-child-dispatch', 'delegate-child-dispatch')
EXPECTED_PCS = {'function-entry': 2662540, 'ordinary-child-dispatch': 3046156,
                'delegate-child-dispatch': 3042808}


def need(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_checks(text):
    checks = {}
    checks['capture_stays_gated'] = 'CAPTURE_READY = False' in text
    checks['three_path_names'] = all(repr(p) in text for p in EXPECTED_PATHS)
    checks['private_phase1_set'] = all(x in text for x in EXPECTED_PRIVATE)
    checks['method_phase_map_is_definition_owned'] = (
        "config['methodPhases'][group]" in text and
        "expected_gate = dict(config['gate'], phase=config['methodPhases'][group])" in text)
    checks['entry_rejects_eh_reentry'] = "item = decode(lambda a,n:memory(process,a,n), frame.FindRegister('x1').GetValueAsUnsigned()" in text and "frame.FindRegister('x3').GetValueAsUnsigned()" in text
    checks['child_paths_dispatch_separately'] = "if kind == 'function-entry':" in text and "else:\n            item = decode_child" in text
    checks['cleanup_owner_is_read_from_thread'] = "runeclrCleanupOwner" in text and "cleanupOwner=owner" in text
    checks['phase1_owner_matches_meter'] = "expected = item['instructionMeter'] if phase == 1 else 0" in text
    checks['raw_and_derived_thread_slots_are_checked'] = (
        "rawSpillOffset" in text and "stackPointerAddressSpillOffset" in text and
        "stack_slot != thread_context + config['layouts']['InterpThreadContext']['fields']['pStackPointer']" in text)
    checks['child_opcode_is_frame_relative'] = "opcode != item['bytecodeStart'] + 8" in text
    checks['bounded_capture'] = "HITS > CONFIG['hitCap']" in text and "hitCap" in text
    checks['owned_process_and_native_identity'] = "process.GetProcessID() != CONFIG['pid']" in text and "nativeUuid" in text
    checks['three_exact_breakpoints'] = "len(BREAKPOINTS)!=3" in text and "len(slides)!=1" in text
    checks['owned_cleanup_on_setup_failure'] = "process.Kill()" in text and "safe_setup" in text
    return checks


def ast_checks(text):
    tree = ast.parse(text)
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {
        'python_parses': True,
        'decoder_and_entry_verifier_exist': {'decoder_source', 'verify_entries'} <= names,
        'observer_source_is_generated': 'observer_source' in names,
    }


def mutation_controls(text):
    """Controls model accidental removal of each safety gate without running LLDB."""
    needles = {
        'remove_phase_gate': "expected_gate = dict(config['gate'], phase=config['methodPhases'][group])",
        'remove_cleanup_owner_check': "owner != expected",
        'remove_raw_thread_context_check': "threadStackPointerAddress",
        'remove_opcode_frame_check': "opcode != item['bytecodeStart'] + 8",
        'remove_eh_prefilter': "frame.FindRegister('x3').GetValueAsUnsigned()",
        'remove_pid_check': "process.GetProcessID() != CONFIG['pid']",
        'remove_uuid_check': "nativeUuid",
        'remove_hit_cap': "HITS > CONFIG['hitCap']",
        'remove_three_path_count': "len(BREAKPOINTS)!=3",
        'remove_slide_check': "len(slides)!=1",
    }
    return {name: needle in text for name, needle in needles.items()}


def config_checks(config):
    """Validate the prepared ABI contract when a capture config is available."""
    need(isinstance(config, dict), 'Capture config must be an object')
    paths = config.get('paths', {})
    checks = {
        'config_has_exact_paths': tuple(paths) == EXPECTED_PATHS,
        'config_has_nine_methods': len(config.get('requiredMethods', [])) == 9,
        'config_thread_context_layout': config.get('layouts', {}).get('InterpThreadContext') == {
            'size': 88, 'fields': {'pStackPointer': 16, 'runeclrCleanupOwner': 80}},
        'config_raw_thread_spills': config.get('threadContract') == {
            'rawSpillOffset': 136, 'stackPointerAddressSpillOffset': 80},
        'config_phase1_private_only': config.get('methodPhases') == {
            name: int(name in EXPECTED_PRIVATE) for name in config.get('requiredMethods', [])},
    }
    for kind, pc in EXPECTED_PCS.items():
        checks['config_' + kind + '_pc'] = paths.get(kind, {}).get('filePc') == pc
    ordinary = paths.get('ordinary-child-dispatch', {})
    delegate = paths.get('delegate-child-dispatch', {})
    checks['config_ordinary_contract'] = (ordinary.get('line') == 3784 and
        ordinary.get('frameRegister') == 'x19' and ordinary.get('frameSpillOffset') == 152 and
        ordinary.get('opcodePointerRegister') == 'x9' and ordinary.get('opcodeAddressAdvance') == 8)
    checks['config_delegate_contract'] = (delegate.get('line') == 3667 and
        delegate.get('frameRegister') == 'x19' and delegate.get('frameSpillOffset') == 152 and
        delegate.get('opcodePointerRegister') == 'x26' and delegate.get('opcodeAddressAdvance') == 8)
    for kind in EXPECTED_PATHS:
        checks['config_' + kind + '_native_prefix'] = (
            isinstance(paths.get(kind, {}).get('prefixHex'), str) and
            len(paths[kind]['prefixHex']) >= 8 and len(paths[kind]['prefixHex']) % 2 == 0)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=CAPTURE)
    parser.add_argument('--config', type=Path, help='Optional prepared capture-config.json; still offline')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = args.capture.resolve()
    text = path.read_text(encoding='utf-8')
    checks = source_checks(text)
    checks.update(ast_checks(text))
    if args.config:
        checks.update(config_checks(json.loads(args.config.read_text(encoding='utf-8-sig'))))
    controls = mutation_controls(text)
    all_passed = all(checks.values()) and all(controls.values())
    result = {
        'reviewer': 'review-ios-fresh-author-entry-v2',
        'capturePath': str(path),
        'captureSha256': sha(path),
        'offlineOnly': True,
        'targetProcessCreated': False,
        'targetInstalled': False,
        'targetLaunched': False,
        'targetAttached': False,
        'paths': list(EXPECTED_PATHS),
        'privatePhase1': sorted(EXPECTED_PRIVATE),
        'configPath': str(args.config.resolve()) if args.config else None,
        'checks': checks,
        'mutationControls': controls,
        'passed': all_passed,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if all_passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
