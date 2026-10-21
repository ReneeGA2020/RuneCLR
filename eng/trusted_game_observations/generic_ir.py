"""Text-only matcher for constructed-generic interpreter IR text blocks.

This module is deliberately small and side-effect-free. It consumes an
already-extracted IR text stream and an explicit list of complete emitted
method identities. It does not read files, launch processes, inspect native
images, derive assembly/token/MVID values, or claim whole-method, interpreter,
native or execution-mode evidence.

The emitted identity shape supported here is the runtime's
Class[classArgs]:Method[methodArgs](parameterTypes) text after the
Compiled method: prefix. Matching is exact after only outer-whitespace and one
leading-dot normalization. Type aliases are never canonicalized. Mixed
managed/native framing is outside this reader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

API_SCOPE = (
    'text-only constructed-generic IR block matching; no assembly/token/MVID attribution, '
    'no whole-method/native/interpreter evidence and no execution-mode claim'
)
IDENTITY_ATTRIBUTION = False
EXECUTION_MODE = None
MIXED_MANAGED_NATIVE_FRAMING = 'outside-reader'

_HEADER_RE = re.compile(r'^Compiled method: (.*)$')
_END_RE = re.compile(r'^End of method: ([0-9A-Fa-f]{4,}): IR_([0-9A-Fa-f]{4,})\s*$')
_OPCODE_RE = re.compile(r'^([0-9A-Fa-f]{4,}): IR_([0-9A-Fa-f]{4,}): (\S.*)$')


class GenericIrError(ValueError):
    """Base class for text-reader failures."""


class TargetSpecError(GenericIrError):
    """A requested target is missing, malformed or incomplete."""


class DuplicateTargetError(TargetSpecError):
    """Two requested targets normalize to the same identity."""


class BlockParseError(GenericIrError):
    """The supplied IR text stream is malformed for this reader."""


class MissingBlockError(BlockParseError):
    """No block matches a requested target."""


class DuplicateBlockError(BlockParseError):
    """More than one block matches a requested target."""


class TruncatedBlockError(BlockParseError):
    """A block started but did not end with End of method."""


class EmptyBlockError(BlockParseError):
    """A block contains no source-shaped opcode rows."""


class NestedBlockError(BlockParseError):
    """A new Compiled method header appeared before the current block ended."""


@dataclass(frozen=True)
class OpcodeRow:
    line_number: int
    char_start: int
    char_end: int
    il_offset: str
    ir_offset: str
    opcode: str
    text: str


@dataclass(frozen=True)
class ParsedBlock:
    raw_identity: str
    normalized_identity: str
    header_line: int
    end_line: int
    char_start: int
    char_end: int
    raw_text: str
    opcode_rows: Tuple[OpcodeRow, ...]

    @property
    def instruction_count(self) -> int:
        return len(self.opcode_rows)

    @property
    def instruction_line_numbers(self) -> Tuple[int, ...]:
        return tuple(row.line_number for row in self.opcode_rows)


@dataclass(frozen=True)
class TargetResult:
    raw_target: str
    normalized_target: str
    block: ParsedBlock


@dataclass(frozen=True)
class SelectionResult:
    targets: Tuple[TargetResult, ...]
    blocks: Tuple[ParsedBlock, ...]
    api_scope: str = API_SCOPE
    text_only: bool = True
    identity_attribution: bool = False
    execution_mode: Optional[str] = EXECUTION_MODE
    mixed_managed_native_framing: str = MIXED_MANAGED_NATIVE_FRAMING
    product_calls: int = 0


def normalize_identity(value: str) -> str:
    """Strip outer whitespace and at most one leading emitted dot."""

    if not isinstance(value, str):
        raise GenericIrError('method identity must be a string')
    normalized = value.strip()
    if normalized.startswith('.'):
        normalized = normalized[1:]
    return normalized


def _require_balanced_brackets(value, label, error_type):
    depth = 0
    for character in value:
        if character == '[':
            depth += 1
        elif character == ']':
            depth -= 1
            if depth < 0:
                raise error_type(label + ' has unbalanced generic/array brackets: ' + repr(value))
    if depth != 0:
        raise error_type(label + ' has unbalanced generic/array brackets: ' + repr(value))


def _require_parameter_slots(value, first_parenthesis, label, error_type):
    signature = value[first_parenthesis + 1:-1]
    if signature == '':
        return
    if not signature.strip():
        raise error_type(label + ' has an empty parameter slot: ' + repr(value))
    depth = 0
    start = 0
    for index, character in enumerate(signature):
        if character == '[':
            depth += 1
        elif character == ']':
            depth -= 1
        elif character == ',' and depth == 0:
            if not signature[start:index].strip():
                raise error_type(label + ' has an empty parameter slot: ' + repr(value))
            start = index + 1
    if not signature[start:].strip():
        raise error_type(label + ' has an empty parameter slot: ' + repr(value))

def _require_complete_identity(value: str, label: str, error_type) -> None:
    if not value:
        raise error_type(label + ' is empty')
    if any(character in value for character in '\r\n'):
        raise error_type(label + ' contains a line break')
    _require_balanced_brackets(value, label, error_type)
    first_parenthesis = value.find('(')
    if first_parenthesis <= 0 or not value.endswith(')'):
        raise error_type(label + ' lacks a complete parameter signature: ' + repr(value))
    if value.count('(') != 1 or value.count(')') != 1:
        raise error_type(label + ' must contain exactly one complete parameter signature: ' + repr(value))
    prefix = value[:first_parenthesis]
    if prefix.count(':') != 1:
        raise error_type(label + ' must contain exactly one class/method separator: ' + repr(value))
    class_name, method_name = prefix.split(':', 1)
    if not class_name.strip():
        raise error_type(label + ' has an empty class name: ' + repr(value))
    if not method_name.strip():
        raise error_type(label + ' has an empty method name: ' + repr(value))
    _require_parameter_slots(value, first_parenthesis, label, error_type)


def _parse_targets(targets: Iterable[str]) -> Tuple[Tuple[str, str], ...]:
    if targets is None or isinstance(targets, (str, bytes)):
        raise TargetSpecError('targets must be an iterable of complete method identities')
    requested = tuple(targets)
    if not requested:
        raise TargetSpecError('at least one complete target is required')
    parsed = []
    seen = set()
    for raw in requested:
        if not isinstance(raw, str):
            raise TargetSpecError('target identity must be a string')
        normalized = normalize_identity(raw)
        _require_complete_identity(normalized, 'target identity', TargetSpecError)
        if normalized in seen:
            raise DuplicateTargetError('duplicate target after normalization: ' + normalized)
        seen.add(normalized)
        parsed.append((raw, normalized))
    return tuple(parsed)


def _parse_blocks(text: str) -> Tuple[ParsedBlock, ...]:
    if not isinstance(text, str):
        raise GenericIrError('IR text must be a string')

    lines = text.splitlines(keepends=True)
    blocks = []
    current = None
    char_offset = 0

    for line_number, raw_line in enumerate(lines, 1):
        line_start = char_offset
        char_offset += len(raw_line)
        line = raw_line.rstrip('\r\n')

        header = _HEADER_RE.match(line)
        if header is not None:
            if current is not None:
                raise NestedBlockError(
                    'nested Compiled method header at line ' + str(line_number)
                    + ' before End of method for ' + current['normalized_identity']
                )
            raw_identity = header.group(1)
            normalized = normalize_identity(raw_identity)
            _require_complete_identity(normalized, 'emitted block identity', BlockParseError)
            current = {
                'raw_identity': raw_identity,
                'normalized_identity': normalized,
                'header_line': line_number,
                'char_start': line_start,
                'opcode_rows': [],
            }
            continue

        if line.lstrip().startswith('Compiled method:'):
            raise BlockParseError('malformed Compiled method header at line ' + str(line_number))

        if line.lstrip().startswith('End of method:') and _END_RE.match(line) is None:
            raise BlockParseError('malformed End of method line at line ' + str(line_number))

        if current is None:
            continue

        end = _END_RE.match(line)
        if end is not None:
            if not current['opcode_rows']:
                raise EmptyBlockError(
                    'block has no source-shaped opcode rows: ' + current['normalized_identity']
                )
            current['end_line'] = line_number
            current['end_char'] = line_start + len(raw_line)
            blocks.append(
                ParsedBlock(
                    raw_identity=current['raw_identity'],
                    normalized_identity=current['normalized_identity'],
                    header_line=current['header_line'],
                    end_line=current['end_line'],
                    char_start=current['char_start'],
                    char_end=current['end_char'],
                    raw_text=text[current['char_start']:current['end_char']],
                    opcode_rows=tuple(current['opcode_rows']),
                )
            )
            current = None
            continue

        opcode = _OPCODE_RE.match(line)
        if opcode is not None:
            current['opcode_rows'].append(
                OpcodeRow(
                    line_number=line_number,
                    char_start=line_start,
                    char_end=line_start + len(raw_line),
                    il_offset=opcode.group(1),
                    ir_offset=opcode.group(2),
                    opcode=opcode.group(3),
                    text=line,
                )
            )

    if current is not None:
        raise TruncatedBlockError(
            'block at line ' + str(current['header_line'])
            + ' has no End of method: ' + current['normalized_identity']
        )
    return tuple(blocks)


def parse_ir_dump(text: str, targets: Iterable[str]) -> SelectionResult:
    """Match explicit complete targets against an extracted IR text stream.

    The result contains exactly one block for each unique normalized target.
    All parsed blocks are retained in blocks for position/instruction-count
    inspection. No identities are inferred from the dump and no product,
    runtime, assembly, token, MVID or execution-mode data is produced.
    """

    requested = _parse_targets(targets)
    blocks = _parse_blocks(text)
    by_identity = {}
    for block in blocks:
        by_identity.setdefault(block.normalized_identity, []).append(block)

    selected = []
    for raw_target, normalized_target in requested:
        matches = by_identity.get(normalized_target, ())
        if not matches:
            raise MissingBlockError('no IR block for target: ' + normalized_target)
        if len(matches) > 1:
            raise DuplicateBlockError('multiple IR blocks for target: ' + normalized_target)
        selected.append(TargetResult(raw_target, normalized_target, matches[0]))

    return SelectionResult(targets=tuple(selected), blocks=blocks)