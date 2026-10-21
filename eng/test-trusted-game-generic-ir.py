#!/usr/bin/env python3
"""Synthetic/source-shaped tests for the constructed-generic IR text reader.

These tests use only synthetic text. They contain no retained machine paths,
no product invocation and no process launch. Process-launch entrypoints are
patched to raise for the duration of the direct test run.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trusted_game_observations import generic_ir

_ORIGINAL_CALLABLES = {}


def _raise_process_launch(*args, **kwargs):
    raise AssertionError('process launch attempted by portable parser test')


def _patch_process_launches():
    for module, names in (
        (subprocess, ('Popen', 'run', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput')),
        (os, ('system', 'popen', 'spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 'spawnv', 'spawnve', 'spawnvp', 'spawnvpe', 'posix_spawn', 'posix_spawnp')),
    ):
        for name in names:
            if hasattr(module, name):
                _ORIGINAL_CALLABLES[(module, name)] = getattr(module, name)
                setattr(module, name, _raise_process_launch)


def _restore_process_launches():
    for (module, name), value in _ORIGINAL_CALLABLES.items():
        setattr(module, name, value)
    _ORIGINAL_CALLABLES.clear()


def _block(identity, opcodes=('NOP',), end=True):
    lines = ['Compiled method: .' + identity, 'Locals size 1']
    for index, opcode in enumerate(opcodes):
        lines.append('%04x: IR_%04x: %s' % (index, index, opcode))
    if end:
        offset = len(opcodes)
        lines.append('End of method: %04x: IR_%04x' % (offset, offset))
    return '\n'.join(lines)


def _raw_block(identity, code_lines, end=True):
    lines = ['Compiled method: .' + identity, 'Locals size 1'] + list(code_lines)
    if end:
        lines.append('End of method: 0000: IR_0000')
    return '\n'.join(lines)


class GenericIrTests(unittest.TestCase):
    """Synthetic parser contract tests; not product or execution evidence."""

    def test_two_constructed_instantiations_are_separate(self):
        first = 'Factory:Create[System.Int32](System.Int32)'
        second = 'Factory:Create[System.String](System.String)'
        text = _block(first) + '\n\n' + _block(second)
        result = generic_ir.parse_ir_dump(text, [first, '.' + second])
        self.assertEqual([item.normalized_target for item in result.targets], [first, second])
        self.assertNotEqual(result.targets[0].block.normalized_identity,
                            result.targets[1].block.normalized_identity)
        self.assertEqual([item.block.instruction_count for item in result.targets], [1, 1])

    def test_two_same_name_overloads_are_separate(self):
        first = 'Overloads:Run(System.Int32)'
        second = 'Overloads:Run(System.String)'
        result = generic_ir.parse_ir_dump(_block(first) + '\n' + _block(second), [first, second])
        self.assertEqual(len(result.targets), 2)
        self.assertEqual(result.targets[0].normalized_target, first)
        self.assertEqual(result.targets[1].normalized_target, second)

    def test_nested_generic_and_array_arguments_are_exact(self):
        identity = ('Container[System.Collections.Generic.List[System.Int32]]:'
                    'Store[System.Int32[]](System.Int32[][], System.String)')
        result = generic_ir.parse_ir_dump(_block(identity, ('NOP', 'LDC_I4 1')), ['  .' + identity + '  '])
        target = result.targets[0]
        self.assertEqual(target.normalized_target, identity)
        self.assertEqual(target.block.raw_identity, '.' + identity)
        self.assertEqual(target.block.normalized_identity, identity)
        self.assertEqual(target.block.instruction_count, 2)

    def test_outer_whitespace_and_one_leading_dot(self):
        identity = 'Sample:Run(System.Int32)'
        target = '   .' + identity + '  '
        result = generic_ir.parse_ir_dump(_block(identity), [target])
        self.assertEqual(result.targets[0].raw_target, target)
        self.assertEqual(result.targets[0].normalized_target, identity)
        self.assertEqual(result.targets[0].block.raw_identity, '.' + identity)

    def test_positions_and_instruction_count_ignore_other_lines(self):
        text = (
            'Compiled method: .Sample:Run(System.Int32)\n'
            'Locals size 2\n'
            '\n'
            '0000: IR_0000: NOP\n'
            'BB0:\n'
            '0004: IR_0004: LDC_I4 1\n'
            '0008: IR_0008: RET\n'
            'End of method: 000c: IR_000c\n'
        )
        block = generic_ir.parse_ir_dump(text, ['Sample:Run(System.Int32)']).targets[0].block
        self.assertEqual(block.instruction_count, 3)
        self.assertEqual(block.instruction_line_numbers, (4, 6, 7))
        self.assertEqual(block.header_line, 1)
        self.assertEqual(block.end_line, 8)
        self.assertEqual(block.char_start, 0)
        self.assertEqual(block.char_end, len(text))
        self.assertTrue(block.raw_text.startswith('Compiled method: .Sample:Run'))
        self.assertTrue(block.raw_text.endswith('End of method: 000c: IR_000c\n'))

    def test_post_end_synthetic_text_not_counted(self):
        identity = 'Sample:Run(System.Int32)'
        text = _block(identity, ('NOP',)) + '\n0001: IR_0001: NOP\n'
        block = generic_ir.parse_ir_dump(text, [identity]).targets[0].block
        self.assertEqual(block.instruction_count, 1)
        self.assertNotIn('0001: IR_0001: NOP', block.raw_text)
        self.assertEqual(len(generic_ir.parse_ir_dump(text, [identity]).blocks), 1)

    def test_wrong_signature_not_matched(self):
        text = _block('Sample:Run(System.Int32)')
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(text, ['Sample:Run(System.String)'])

    def test_substring_like_prefix_not_matched(self):
        text = _block('Sample:Run(System.Int32, System.Int32)')
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(text, ['Sample:Run(System.Int32)'])

    def test_multiple_signature_block_rejected(self):
        text = _block('Sample:Run(System.Int32)(System.String)')
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(text, ['Sample:Run(System.Int32)'])

    def test_substring_suffix_not_matched(self):
        text = _block('Namespace.Sample:Run(System.Int32)')
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(text, ['Sample:Run(System.Int32)'])

    def test_canonical_aliases_are_not_equated(self):
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(_block('Sample:Run(int)'), ['Sample:Run(System.Int32)'])
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(_block('Factory:Create[System.Int32](System.Int32)'),
                                     ['Factory:Create[int](int)'])

    def test_argument_alias_is_preserved_exactly(self):
        identity = 'Alias:Run(int)'
        result = generic_ir.parse_ir_dump(_block(identity), [identity])
        self.assertEqual(result.targets[0].block.normalized_identity, identity)
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump(_block(identity), ['Alias:Run(System.Int32)'])

    def test_duplicate_targets_rejected(self):
        identity = 'Sample:Run(System.Int32)'
        with self.assertRaises(generic_ir.DuplicateTargetError):
            generic_ir.parse_ir_dump(_block(identity), [identity, '  .' + identity + '  '])

    def test_duplicate_selected_blocks_rejected(self):
        identity = 'Sample:Run(System.Int32)'
        text = _block(identity) + '\n\n' + _block(identity)
        with self.assertRaises(generic_ir.DuplicateBlockError):
            generic_ir.parse_ir_dump(text, [identity])

    def test_missing_end_rejected(self):
        identity = 'Sample:Run(System.Int32)'
        with self.assertRaises(generic_ir.TruncatedBlockError):
            generic_ir.parse_ir_dump(_block(identity, end=False), [identity])

    def test_empty_block_rejected(self):
        identity = 'Empty:Run()'
        with self.assertRaises(generic_ir.EmptyBlockError):
            generic_ir.parse_ir_dump(_block(identity, opcodes=()), [identity])

    def test_synthetic_only_opcode_rows_rejected(self):
        identity = 'Synthetic:Run()'
        text = _raw_block(identity, ['IL_0000: NOP', '0000: IR_0000:', 'BB0:'])
        with self.assertRaises(generic_ir.EmptyBlockError):
            generic_ir.parse_ir_dump(text, [identity])

    def test_nested_header_rejected(self):
        text = _raw_block(
            'Outer:Run(System.Int32)',
            ['0000: IR_0000: NOP', 'Compiled method: .Inner:Run(System.Int32)'],
            end=True,
        )
        with self.assertRaises(generic_ir.NestedBlockError):
            generic_ir.parse_ir_dump(text, ['Outer:Run(System.Int32)'])

    def test_incomplete_targets_rejected(self):
        text = _block('Sample:Run(System.Int32)')
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, [])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, ['Sample:Run'])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, ['   .   '])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, ['(System.Int32)'])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, ['Sample:()'])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, [':Sample:Run(System.Int32)'])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(text, ['Method(System.Int32)'])

    def test_incomplete_block_identity_rejected(self):
        text = (
            'Compiled method: .Sample:Run\n'
            'Locals size 1\n'
            '0000: IR_0000: NOP\n'
            'End of method: 0001: IR_0001\n'
        )
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(text, ['Sample:Run(System.Int32)'])
        empty_method = (
            'Compiled method: .Sample:()\n'
            'Locals size 1\n'
            '0000: IR_0000: NOP\n'
            'End of method: 0001: IR_0001\n'
        )
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(empty_method, ['Sample:Run(System.Int32)'])
        no_class = (
            'Compiled method: .Method(System.Int32)\n'
            'Locals size 1\n'
            '0000: IR_0000: NOP\n'
            'End of method: 0001: IR_0001\n'
        )
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(no_class, ['Sample:Run(System.Int32)'])

    def test_no_blocks_rejected(self):
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump('', ['Sample:Run(System.Int32)'])
        with self.assertRaises(generic_ir.MissingBlockError):
            generic_ir.parse_ir_dump('unrelated text\n', ['Sample:Run(System.Int32)'])

    def test_unbalanced_generic_brackets_rejected(self):
        valid = _block('Fixture:Run(ScorePair)')
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(valid, ['Fixture:Run[ScorePair(ScorePair)'])
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(valid, ['Fixture:Run]ScorePair[(ScorePair)'])
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(_block('Fixture:Run[ScorePair(ScorePair)'),
                                     ['Fixture:Run(ScorePair)'])

    def test_whitespace_only_method_name_rejected(self):
        with self.assertRaises(generic_ir.TargetSpecError):
            generic_ir.parse_ir_dump(_block('Fixture:Run(int)'), ['Fixture: (int)'])
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(_block('Fixture: (int)'), ['Fixture:Run(int)'])

    def test_malformed_reserved_header_rejected(self):
        valid = 'Fixture:Run[ScorePair](ScorePair)'
        text = (
            'Compiled method: .' + valid + '\n'
            '0000: IR_0000: NOP\n'
            'Compiled method:.Other:Run[int](int)\n'
            '0001: IR_0001: RET\n'
            'End of method: 0002: IR_0002\n'
        )
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(text, [valid])

    def test_malformed_reserved_end_rejected(self):
        valid = 'Fixture:Run[ScorePair](ScorePair)'
        text = (
            'Compiled method: .' + valid + '\n'
            '0000: IR_0000: NOP\n'
            'End of method: invalid\n'
            '0001: IR_0001: RET\n'
            'End of method: 0002: IR_0002\n'
        )
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(text, [valid])

    def test_empty_parameter_slots_rejected(self):
        text = _block('Fixture:Run(System.Int32)')
        for target in (
            'Fixture:Run(,System.Int32)',
            'Fixture:Run(System.Int32,)',
            'Fixture:Run(System.Int32,,System.String)',
            'Fixture:Run( )',
        ):
            with self.assertRaises(generic_ir.TargetSpecError):
                generic_ir.parse_ir_dump(text, [target])
        with self.assertRaises(generic_ir.BlockParseError):
            generic_ir.parse_ir_dump(_block('Fixture:Run(,System.Int32)'),
                                     ['Fixture:Run(System.Int32)'])

    def test_nested_generic_and_array_rank_commas_preserved(self):
        identity = ('Fixture:Run(System.Collections.Generic.Dictionary[System.Int32, System.String], '
                    'System.Int32[,])')
        result = generic_ir.parse_ir_dump(_block(identity), [identity])
        self.assertEqual(result.targets[0].normalized_target, identity)
        self.assertEqual(result.targets[0].block.instruction_count, 1)
    def test_result_declares_text_only_no_identity_attribution(self):
        result = generic_ir.parse_ir_dump(_block('Meta:Run(System.Int32)'), ['Meta:Run(System.Int32)'])
        self.assertTrue(result.text_only)
        self.assertFalse(result.identity_attribution)
        self.assertIsNone(result.execution_mode)
        self.assertEqual(result.product_calls, 0)
        self.assertIn('text-only', result.api_scope)
        self.assertIn('no assembly/token/MVID', result.api_scope)
        self.assertEqual(result.mixed_managed_native_framing, 'outside-reader')


def main():
    _patch_process_launches()
    try:
        print('SYNTHETIC/SOURCE-SHAPED PARSER TESTS ONLY; no retained machine paths; productCalls=0')
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print('SUMMARY tests=%d failures=%d errors=%d productCalls=0' % (
            result.testsRun, len(result.failures), len(result.errors)))
        return 0 if result.wasSuccessful() else 1
    finally:
        _restore_process_launches()


if __name__ == '__main__':
    raise SystemExit(main())