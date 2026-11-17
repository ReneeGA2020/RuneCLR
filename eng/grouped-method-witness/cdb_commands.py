"""CDB command text and transcript parsers for grouped method witnesses.

This module is the shared helper used by the grouped method witness runner. It only
builds debugger command text and parses CDB transcript text that has already been
captured: it never launches a debugger or a debuggee, never installs anything beyond
the command list it returns, and never invents a value it did not observe. Every
parser raises ValueError when an observation is missing, ambiguous, duplicated or
inconsistent.

Radix rule
    CDB evaluates MASM expressions in radix 16 by default, so decimal text is unsafe.
    Every numeric literal emitted here is written 0x... . Bare hex digits are accepted
    only while parsing debugger output, which CDB already prints in radix 16, and are
    never used to fill in a value that this module did not read back.

Source-audited facts behind the interpreter route (REVIEW-INTERP-FRAME-WITNESS.md)
    InterpExecMethod(InterpreterFrame* rcx, InterpMethodContextFrame* rdx,
                     InterpThreadContext* r8, ExceptionClauseArgs* r9).
    r9 != 0 means exception-clause resume, not a method entry, and is rejected.
    pFrame->startIp->Method->methodHnd is the MethodDesc of the frame.
    InterpMethod::codeSize counts int32 IR slots, so IR bytes = slots * 4.
    InterpByteCodeStart begins with InterpMethod* Method and GetByteCodes() returns the
    int32 slots immediately after that header, so the IR start offset is
    sizeof(InterpByteCodeStart), read at run time and never assumed.
    MethodDesc::m_interpreterCode must equal pFrame->startIp for a first entry.

Layout input contract
    parse_layout() consumes captured text per type: dt coreclr!Type for the fields, plus
    one explicit size observation for InterpByteCodeStart from the printf probe that
    layout_probe_commands() returns. That probe prints a labelled 0x value, for example
    SIZEOF-InterpByteCodeStart 0x8, so the size can never be read as a decimal string.
    Size and offset observations must be 0x-prefixed and the size label must name the same
    type; a bare unattributed decimal size is rejected instead of being guessed.

Transcript contract
    CDB prints its prompt before a command's output, and a stdin pipe does not echo the
    command, so a real transcript line looks like "0:000> SIZEOF-InterpByteCodeStart 0x8"
    or "0:000>    +0x000 Method : Ptr64 InterpMethod". The prompt is therefore a separator,
    not a discard marker: it is stripped and only the remainder is judged. A remainder
    that is debugger input (.echo/.printf and other directives, !SOS commands, r, dt, u,
    bp/bc, g/gc, ?/??, poi/dwo and similar) is an echoed command and is dropped; every
    other remainder is runtime output and is kept. A marker is only accepted as output, so
    ".echo WITNESS-..." never satisfies it. Duplicate stop markers mean several stops were
    captured in one text; split them before parsing.

Stop kind vocabulary (consumed by the verifier)
    author    -> interp-first-entry (InterpExecMethod entry with matching frame MethodDesc)
    framework -> jit-native, or jit-native-partial when the observed instruction span is
                 not contiguous from RIP. native_code_start/size describe that observed span
                 only; they are not the method body size and are null when it is partial.

Layout input shapes
    parse_layout accepts either one block per type name, or a single block holding the whole
    layout transcript; in that case the segments are split on the echoed probe commands.
"""
from __future__ import annotations

import re

__all__ = [
    "LAYOUT_TYPES",
    "bootstrap_commands",
    "layout_probe_commands",
    "parse_layout",
    "framework_breakpoint_commands",
    "capture_jit_commands",
    "parse_jit_capture",
    "interp_breakpoint_command",
    "capture_interp_commands",
    "parse_interp_capture",
    "code_probe_commands",
    "parse_code_probe",
    "framework_compile_breakpoint_commands",
    "capture_compile_commands",
    "parse_compile_stop",
    "code_address_inspection_commands",
    "hardware_execute_breakpoint_commands",
    "cleanup_commands",
]

BT = chr(96)

LAYOUT_TYPES = (
    "InterpMethodContextFrame",
    "InterpByteCodeStart",
    "InterpMethod",
    "MethodDesc",
)

_LAYOUT_KEYS = (
    "start_ip_off",
    "method_off",
    "method_hnd_off",
    "codesize_off",
    "m_interp_code_off",
    "bytecode_start_size",
)

MARKER_BOOT_BEGIN = "WITNESS-BOOT-BEGIN"
MARKER_BOOT_AT_LOAD = "WITNESS-BOOT-AT-LOAD"
MARKER_BOOT_AT_EXECMAIN = "WITNESS-BOOT-AT-EXECMAIN"
MARKER_JIT_HIT = "WITNESS-JIT-HIT"
MARKER_JIT_END = "WITNESS-JIT-END"
MARKER_INTERP_HIT = "WITNESS-INTERP-HIT"
MARKER_INTERP_FRAME = "WITNESS-INTERP-FRAME"
MARKER_INTERP_STARTIP = "WITNESS-INTERP-STARTIP"
MARKER_INTERP_METHOD = "WITNESS-INTERP-METHOD"
MARKER_INTERP_METHODHND = "WITNESS-INTERP-METHODHND"
MARKER_INTERP_CODESIZE = "WITNESS-INTERP-CODESIZE"
MARKER_INTERP_INTERPCODE = "WITNESS-INTERP-INTERPCODE"
MARKER_INTERP_DUMPMD = "WITNESS-INTERP-DUMPMD"
MARKER_INTERP_IRSTART = "WITNESS-INTERP-IRSTART"
MARKER_INTERP_END = "WITNESS-INTERP-END"
MARKER_CODE_PROBE_BEGIN = "WITNESS-CODE-PROBE-BEGIN"
MARKER_CODE_PROBE_INTERPCODE = "WITNESS-CODE-PROBE-INTERPCODE"
MARKER_CODE_PROBE_MODULE = "WITNESS-CODE-PROBE-MODULE"
MARKER_CODE_PROBE_END = "WITNESS-CODE-PROBE-END"
MARKER_CODE_INSPECT_BEGIN = "WITNESS-CODE-INSPECT-BEGIN"
MARKER_CODE_INSPECT_ADDRESS = "WITNESS-CODE-INSPECT-ADDRESS"
MARKER_CODE_INSPECT_VPROT = "WITNESS-CODE-INSPECT-VPROT"
MARKER_CODE_INSPECT_DISASM = "WITNESS-CODE-INSPECT-DISASM"
MARKER_CODE_INSPECT_END = "WITNESS-CODE-INSPECT-END"
MARKER_COMPILE_READY = "WITNESS-COMPILE-READY"
MARKER_COMPILE_BEGIN = "WITNESS-COMPILE-BEGIN"
MARKER_COMPILE_END = "WITNESS-COMPILE-END"
MARKER_HW_ARM = "WITNESS-HW-ARM"
MARKER_HW_ARMED = "WITNESS-HW-ARMED"

MARKER_CLEANUP = "WITNESS-CLEANUP"
MARKER_CLEANUP_DONE = "WITNESS-CLEANUP-DONE"

_MAX_CODE_SLOTS = 0x400000

_HEX_TOKEN = re.compile(r"^(?:0x)?([0-9a-fA-F]+)$")
_PROMPT = re.compile(r"^\s*\d+:[0-9a-fA-F]{3}(?::[0-9A-Za-z_.-]+)?>\s?")

_COMMAND_ECHO = re.compile(
    r"^(?:"
    r"\."
    r"|!"
    r"|x(?:\s|$)"
    r"|(?:bp|bc|bd|be|bl|bm|ba|bu|br)(?:\s|$)"
    r"|dt(?:\s|$)"
    r"|(?:poi|dwo)(?=\s|\()"
    r"|(?:d|e)[abcdqwsuf](?:\s|$)"
    r"|u(?:\s|$)"
    r"|ln(?:\s|$)"
    r"|r(?:\s|$)"
    r"|(?:g|gc|gh|gn|gu|p|pc|t|ta|q|qd|qq)(?:\s|$)"
    r"|s(?:xe|xd|xi|xn)(?:\s|$)"
    r"|(?:k|kb|kv|kp|kn)(?:\s|$)"
    r"|[?]{1,2}(?:\s|$)"
    r"|(?:lm|ld|lu)(?:\s|$)"
    r"|(?:ver|version)(?:\s|$)"
    r")"
)
_FIELD = re.compile(r"^\s*\+\s*0x([0-9a-fA-F]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::.*)?$")
_VALUE = re.compile(r"^([0-9a-fA-F" + BT + r"]+)(?:\s+\S+)?$")
_MD_LINE = re.compile(r"^MethodDesc:\s*([0-9a-fA-F" + BT + r"]+)(.*)$")
_TOKEN_LINE = re.compile(r"^(?:md)?token:\s*(?:0x)?([0-9a-fA-F]{16}|[0-9a-fA-F]{8})\b", re.IGNORECASE)
_MODULE_LINE = re.compile(r"^Module:\s*([0-9a-fA-F" + BT + r"]+)(?:\s+.*)?$")
_METHOD_NAME = re.compile(r"^Method Name:\s*\S", re.IGNORECASE)
_CODE_ADDR = re.compile(r"^(?:Current\s+)?CodeAddr:\s*([0-9a-fA-F" + BT + r"]+)(?:\s+.*)?$", re.IGNORECASE)
_VERSION_HISTORY = re.compile(r"^Version History:", re.IGNORECASE)
_COMPILE_SYMBOL = re.compile(r"^coreclr!DACNotifyCompilationFinished(?:\+0x0)?:?$")
_DISASM = re.compile(r"^\s*([0-9a-fA-F" + BT + r"]+)\s+([0-9a-fA-F]{2,})\s+\S")

_PROBE_ECHO = re.compile(
    r'^\s*\d+:[0-9a-fA-F]{3}(?::[0-9A-Za-z_.-]+)?>\s*(?:dt\s+coreclr!([A-Za-z_][A-Za-z0-9_]*)|[?]{2}\s*sizeof\(\s*(?:coreclr!)?([A-Za-z_][A-Za-z0-9_]*)\s*\)|\.printf\s+"SIZEOF-([A-Za-z_][A-Za-z0-9_]*)\s)',
    re.MULTILINE,
)

_SIZE_LABELED = re.compile(r"^SIZEOF-([A-Za-z_][A-Za-z0-9_]*)\s+0x([0-9a-fA-F]+)$")

_SIZE_PATTERNS = (
    re.compile(r"^\s*sizeof\s*\([^)]*\)\s*(?:=|:)\s*(0x[0-9a-fA-F]+)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:struct\s+)?size\s*(?:=|:)\s*(0x[0-9a-fA-F]+)\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(?:unsigned\s+)?(?:int64|__int64|int32|int|long|size_t|ulonglong)\s+(0x[0-9a-fA-F]+)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(0x[0-9a-fA-F]+)\s+(?:unsigned\s+)?(?:int64|__int64|int32|int|long|size_t|ulonglong)\s*$",
        re.IGNORECASE,
    ),
)


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def _require_text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(what + " must be a non-empty string")
    if "\n" in value or "\r" in value:
        raise ValueError(what + " must be a single line")
    return value


def _require_int(value, what):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(what + " must be an integer, got %r" % (value,))
    if value < 0:
        raise ValueError(what + " must be non-negative")
    return value


def _hex(value, what):
    return "0x%x" % _require_int(value, what)


def _require_md(value, what):
    md = _require_int(value, what)
    if md == 0:
        raise ValueError(what + " must not be null")
    if md >= 1 << 64:
        raise ValueError(what + " does not fit in 64 bits")
    if md % 8 != 0:
        raise ValueError(what + " is not pointer aligned")
    return md


def _require_code_addr(value, what):
    """Validate a natural code address: non-null, not the poison sentinel, 64-bit, plausible."""
    addr = _require_int(value, what)
    if addr == 0 or addr == 1:
        raise ValueError(what + " is null or the poison sentinel, not a code address")
    if addr < 0x10000:
        raise ValueError(what + " 0x%x is below the smallest plausible image address" % addr)
    if addr >= 1 << 64:
        raise ValueError(what + " does not fit in 64 bits")
    return addr


def _printf_u64(expression):
    """Query a 64-bit value as plain 16-digit hex.

    A bare poi(...) line is parsed by CDB as the p (step) command, so every expression
    query must be the argument of a genuine command instead.
    """
    return '.printf "%016I64x\\n", ' + expression


def _printf_u32(expression):
    """Query a 32-bit value (for example dwo) as plain 8-digit hex."""
    return '.printf "%08x\\n", ' + expression

def _path_arg(path, what):
    text = _require_text(path, what)
    if text != text.strip():
        raise ValueError(what + " has leading or trailing whitespace")
    for ch in ('"', ";", "\t"):
        if ch in text:
            raise ValueError(what + " contains a character unsafe for a debugger path: %r" % text)
    if " " in text:
        return '"' + text + '"'
    return text


def _parse_hex(token, what):
    if not isinstance(token, str):
        raise ValueError(what + " is not text")
    text = token.strip().replace(BT, "")
    match = _HEX_TOKEN.match(text)
    if match is None:
        raise ValueError(what + " is not a hex value: %r" % (token,))
    return int(match.group(1), 16)


def _fmt_set(values):
    return ", ".join("0x%x" % value for value in sorted(values)) if values else "(none)"


def _output_lines(text):
    if not isinstance(text, str):
        raise ValueError("transcript text must be a string")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in normalized.split("\n"):
        prompt = _PROMPT.match(raw)
        if prompt is None:
            line = raw.rstrip()
        else:
            remainder = raw[prompt.end():]
            if not remainder.strip():
                continue
            if _COMMAND_ECHO.match(remainder.lstrip()):
                continue
            line = remainder.rstrip()
        if not line.strip():
            continue
        lines.append(line)
    return lines


def _require_marker(lines, marker):
    hits = [index for index, line in enumerate(lines) if line.strip() == marker]
    if not hits:
        raise ValueError("missing marker line " + marker + " (an echoed command does not count)")
    if len(hits) > 1:
        raise ValueError("duplicate marker line " + marker + ": several stops in one transcript")
    return hits[0]


def _section(lines, start_marker, end_marker):
    begin = _require_marker(lines, start_marker)
    end = _require_marker(lines, end_marker)
    if end <= begin:
        raise ValueError("end marker " + end_marker + " appears before " + start_marker)
    return lines[begin + 1:end]


def _single_value(lines, pattern, what):
    found = []
    for line in lines:
        match = pattern.match(line)
        if match is not None:
            found.append(match.group(1))
    if not found:
        raise ValueError("missing " + what)
    if len(found) > 1:
        raise ValueError("ambiguous " + what + ": %d observations" % len(found))
    return _parse_hex(found[0], what)


def _unique_value(lines, pattern, what):
    values = set()
    for line in lines:
        match = pattern.match(line)
        if match is not None:
            values.add(_parse_hex(match.group(1), what))
    if not values:
        raise ValueError("missing " + what)
    if len(values) > 1:
        raise ValueError("conflicting " + what + " observations: " + _fmt_set(values))
    return values.pop()


def _register(lines, name):
    pattern = re.compile(r"^" + re.escape(name) + r"=([0-9a-fA-F" + BT + r"]+)(?:\s+\S+)?$")
    return _single_value(lines, pattern, "register " + name)




_DEBUGGER_FAILURES = (
    (re.compile(r"pass count must be pre", re.IGNORECASE),
     "the debugger rejected the expression query as a step command, so no value was observed"),
    (re.compile(r"Numeric expression missing", re.IGNORECASE),
     "the debugger could not evaluate the breakpoint condition (MASM grammar), so no method hit was observed"),
    (re.compile(r"^error in '", re.IGNORECASE),
     "the debugger rejected the command text, so no value was observed"),
    (re.compile(r"^Unable to insert breakpoint\b", re.IGNORECASE),
     "breakpoint could not be inserted, so the method was never hit"),
    (re.compile(r"^bp[0-9a-fA-F]* at .*\bfailed$", re.IGNORECASE),
     "breakpoint could not be inserted, so the method was never hit"),
    (re.compile(r"^WaitForEvent failed\b", re.IGNORECASE),
     "debugger WaitForEvent failed, so no method hit was observed"),
    (re.compile(r"^Failed to request MethodData\b", re.IGNORECASE),
     "!ip2md has no MethodData for this stop, so it is not a method hit"),
)


def _reject_debugger_failure(lines):
    """Surface the real debugger failure instead of reporting a method hit."""
    for line in lines:
        text = line.strip()
        for pattern, reason in _DEBUGGER_FAILURES:
            if pattern.search(text):
                raise ValueError(reason + ": " + text[:240])


def _methoddef_token(token, what):
    """Accept a 32-bit MethodDef token, including zero-extended 16-digit printouts."""
    if token > 0xFFFFFFFF:
        raise ValueError(
            "%s 0x%x carries non-zero upper bits and is not a 32-bit MethodDef token"
            % (what, token)
        )
    if (token >> 24) != 0x06:
        raise ValueError("%s 0x%08x is not a MethodDef token" % (what, token))
    if (token & 0x00FFFFFF) == 0:
        raise ValueError("%s 0x%08x has a zero row id" % (what, token))
    return token


def _active_code_addr(lines):
    """Read the active native code address and never a per-version history entry."""
    header = []
    for line in lines:
        if _VERSION_HISTORY.match(line.strip()):
            break
        header.append(line)
    values = set()
    for line in header:
        match = _CODE_ADDR.match(line)
        if match is not None:
            values.add(_parse_hex(match.group(1), "CodeAddr"))
    if len(values) > 1:
        raise ValueError("conflicting active CodeAddr observations: " + _fmt_set(values))
    return values.pop() if values else None

def _methoddesc_values(lines):
    values = set()
    for line in lines:
        match = _MD_LINE.match(line)
        if match is None:
            continue
        if "(stub" in match.group(2):
            raise ValueError("!ip2md resolved to a stub, not a method body")
        values.add(_parse_hex(match.group(1), "MethodDesc"))
    return values


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------

def bootstrap_commands(runtime_root, sos):
    """Proven initialized-runtime bootstrap: loader stop, local PDB, native stop, SOS."""
    root = _path_arg(runtime_root, "runtime_root")
    sos_arg = _path_arg(sos, "sos")
    return [
        ".echo " + MARKER_BOOT_BEGIN,
        "sxe ld:coreclr.dll",
        "g",
        ".echo " + MARKER_BOOT_AT_LOAD,
        ".sympath+ " + root,
        ".reload /f coreclr.dll",
        "x coreclr!Assembly::ExecuteMainMethod",
        "bp coreclr!Assembly::ExecuteMainMethod",
        "g",
        ".echo " + MARKER_BOOT_AT_EXECMAIN,
        ".load " + sos_arg,
        "!sosstatus",
        "!dumpdomain",
    ]


def layout_probe_commands():
    """Commands whose captured text feeds parse_layout(), grouped by type name."""
    commands = []
    for type_name in LAYOUT_TYPES:
        commands.append("dt coreclr!" + type_name)
        if type_name == "InterpByteCodeStart":
            commands.append(
                '.printf "SIZEOF-%s 0x%%I64x\\n", @@c++(sizeof(coreclr!%s))' % (type_name, type_name)
            )
    return commands


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

def _field_offset(lines, field, type_name, alignment, limit):
    offsets = []
    for line in lines:
        match = _FIELD.match(line)
        if match is None:
            continue
        if match.group(2) != field:
            continue
        offsets.append(int(match.group(1), 16))
    if not offsets:
        raise ValueError(type_name + " has no " + field + " field")
    if len(offsets) > 1:
        raise ValueError(type_name + " lists " + field + " %d times" % len(offsets))
    offset = offsets[0]
    if offset % alignment != 0:
        raise ValueError(
            "%s.%s offset 0x%x is not %d-byte aligned" % (type_name, field, offset, alignment)
        )
    if offset >= limit:
        raise ValueError(
            "%s.%s offset 0x%x is outside the expected range (< 0x%x)"
            % (type_name, field, offset, limit)
        )
    return offset


def _type_size(lines, type_name):
    sizes = set()
    for line in lines:
        if _FIELD.match(line) is not None:
            continue
        labeled = _SIZE_LABELED.match(line.strip())
        if labeled is not None:
            if labeled.group(1) != type_name:
                raise ValueError(
                    "size observation is labelled for %s, not %s" % (labeled.group(1), type_name)
                )
            sizes.add(_parse_hex(labeled.group(2), type_name + " size"))
            continue
        for pattern in _SIZE_PATTERNS:
            match = pattern.match(line.strip())
            if match is not None:
                sizes.add(_parse_hex(match.group(1), type_name + " size"))
                break
    if not sizes:
        raise ValueError(
            type_name
            + " has no 0x-prefixed size observation; capture ?? sizeof(coreclr!"
            + type_name
            + ")"
        )
    if len(sizes) > 1:
        raise ValueError("conflicting " + type_name + " size observations: " + _fmt_set(sizes))
    return sizes.pop()


def _split_probe_transcript(text):
    segments = {}
    current = None
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = _PROBE_ECHO.match(line)
        if match is not None:
            current = match.group(1) or match.group(2) or match.group(3)
            segments.setdefault(current, [])
        if current is not None:
            segments[current].append(line)
    return {name: "\n".join(lines) for name, lines in segments.items()}


def _normalized_blocks(outputs_by_type):
    if not isinstance(outputs_by_type, dict):
        raise ValueError("outputs_by_type must be a mapping of type name to captured text")
    blocks = {}
    if len(outputs_by_type) == 1:
        only_key = next(iter(outputs_by_type))
        only_text = outputs_by_type[only_key]
        only_name = only_key.strip() if isinstance(only_key, str) else ""
        if only_name.startswith("coreclr!"):
            only_name = only_name[len("coreclr!"):]
        if only_name not in LAYOUT_TYPES and isinstance(only_text, str) and _PROBE_ECHO.search(only_text):
            outputs_by_type = _split_probe_transcript(only_text)
    blocks = {}
    for raw_key, text in outputs_by_type.items():
        if not isinstance(raw_key, str):
            raise ValueError("layout output keys must be type names, got %r" % (raw_key,))
        key = raw_key.strip()
        if key.startswith("coreclr!"):
            key = key[len("coreclr!"):]
        if key in blocks:
            raise ValueError("duplicate layout output for type " + key)
        if not isinstance(text, str):
            raise ValueError("layout output for " + key + " must be text")
        blocks[key] = _output_lines(text)
    for type_name in LAYOUT_TYPES:
        if type_name not in blocks:
            raise ValueError("missing layout output for type " + type_name)
        if not blocks[type_name]:
            raise ValueError("layout output for " + type_name + " is empty")
    return blocks


def parse_layout(outputs_by_type):
    """Read the six dynamic layout values from captured dt/sizeof text."""
    blocks = _normalized_blocks(outputs_by_type)
    frame = blocks["InterpMethodContextFrame"]
    bytecode = blocks["InterpByteCodeStart"]
    interp_method = blocks["InterpMethod"]
    method_desc = blocks["MethodDesc"]

    bytecode_start_size = _type_size(bytecode, "InterpByteCodeStart")
    if bytecode_start_size <= 0 or bytecode_start_size % 4 != 0:
        raise ValueError(
            "InterpByteCodeStart size 0x%x is not a positive multiple of 4"
            % bytecode_start_size
        )

    start_ip_off = _field_offset(frame, "startIp", "InterpMethodContextFrame", 8, 0x10000)
    method_off = _field_offset(bytecode, "Method", "InterpByteCodeStart", 8, bytecode_start_size)
    method_hnd_off = _field_offset(interp_method, "methodHnd", "InterpMethod", 8, 0x10000)
    codesize_off = _field_offset(interp_method, "codeSize", "InterpMethod", 4, 0x10000)
    m_interp_code_off = _field_offset(method_desc, "m_interpreterCode", "MethodDesc", 8, 0x100000)

    if method_off + 8 > bytecode_start_size:
        raise ValueError(
            "InterpByteCodeStart.Method at 0x%x does not fit in size 0x%x"
            % (method_off, bytecode_start_size)
        )

    return {
        "start_ip_off": start_ip_off,
        "method_off": method_off,
        "method_hnd_off": method_hnd_off,
        "codesize_off": codesize_off,
        "m_interp_code_off": m_interp_code_off,
        "bytecode_start_size": bytecode_start_size,
    }


def _layout_offsets(layout):
    if not isinstance(layout, dict):
        raise ValueError("layout must be the dict returned by parse_layout")
    offsets = {}
    for key in _LAYOUT_KEYS:
        if key not in layout:
            raise ValueError("layout is missing " + key)
        value = layout[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("layout " + key + " must be a non-negative integer")
        offsets[key] = value
    size = offsets["bytecode_start_size"]
    if size <= 0 or size % 4 != 0:
        raise ValueError("layout bytecode_start_size must be a positive multiple of 4")
    return offsets


# ---------------------------------------------------------------------------
# framework (JIT) route
# ---------------------------------------------------------------------------

def framework_breakpoint_commands(md):
    """SOS managed breakpoint on the ordinary framework method body."""
    md_hex = _hex(_require_md(md, "method descriptor"), "method descriptor")
    return ["!bpmd -md " + md_hex]


def capture_jit_commands(md):
    """Capture native RIP, MethodDesc/token/module and the observed instruction span."""
    md_hex = _hex(_require_md(md, "method descriptor"), "method descriptor")
    return [
        ".echo " + MARKER_JIT_HIT,
        "r rip",
        "!ip2md @rip",
        "!dumpmd " + md_hex,
        "u @rip L0x40",
        ".echo " + MARKER_JIT_END,
    ]


def _disassembly_range(lines, start_pc):
    entries = []
    for line in lines:
        match = _DISASM.match(line)
        if match is None:
            continue
        address = _parse_hex(match.group(1), "disassembly address")
        code = match.group(2)
        if len(code) % 2 != 0:
            return None
        entries.append((address, len(code) // 2))
    if not entries:
        return None
    expected = start_pc
    total = 0
    for address, size in entries:
        if address != expected or size <= 0:
            return None
        expected += size
        total += size
    return start_pc, total, len(entries)


def parse_jit_capture(text, expected_md):
    """Parse one framework stop; the returned span is observed, not the method size."""
    want = _require_md(expected_md, "expected method descriptor")
    lines = _output_lines(text)
    _reject_debugger_failure(lines)
    body = _section(lines, MARKER_JIT_HIT, MARKER_JIT_END)

    pc = _register(body, "rip")
    if pc == 0:
        raise ValueError("stop RIP is null")

    observed = _methoddesc_values(body)
    if observed != {want}:
        raise ValueError(
            "!ip2md must independently report the expected MethodDesc; observed %s, expected %s"
            % (_fmt_set(observed), _hex(want, "expected MethodDesc"))
        )

    token = _methoddef_token(_unique_value(body, _TOKEN_LINE, "mdToken"), "mdToken")
    module = _unique_value(body, _MODULE_LINE, "Module")
    if module == 0:
        raise ValueError("Module observation is null")
    if not any(_METHOD_NAME.match(line) for line in body):
        raise ValueError("!dumpmd output has no Method Name line")

    dac_native_code_addr = _active_code_addr(body)
    if dac_native_code_addr is not None and dac_native_code_addr != pc:
        raise ValueError(
            "!dumpmd active CodeAddr %s is not the stop RIP %s"
            % (_hex(dac_native_code_addr, "CodeAddr"), _hex(pc, "rip"))
        )

    span = _disassembly_range(body, pc)
    if span is None:
        observed_start = None
        observed_size = None
        observed_count = None
    else:
        observed_start, observed_size, observed_count = span

    bound = dac_native_code_addr is not None and dac_native_code_addr == pc
    complete = bool(bound and span is not None)
    if complete:
        stop_kind = "jit-native"
        diagnostic = None
    else:
        stop_kind = "jit-native-partial"
        if span is None:
            diagnostic = "u @rip did not yield a contiguous instruction stream at RIP"
        else:
            diagnostic = (
                "DAC CodeAddr missing; the observed instruction span is not bound to the native body"
            )

    return {
        "target": "framework",
        "md_value": want,
        "stop_kind": stop_kind,
        "pc": pc,
        "actual_native_pc": pc,
        "ip2md_md": want,
        "dac_native_code_addr": dac_native_code_addr,
        "native_body_bound_to_dac": bound,
        "native_code_start": observed_start if complete else None,
        "native_code_size": observed_size if complete else None,
        "native_instruction_count": observed_count if complete else None,
        "observed_span_start": observed_start,
        "observed_span_size": observed_size,
        "observed_span_instructions": observed_count,
        "observed_span_complete": span is not None,
        "range_complete": complete,
        "range_kind": "observed-instructions-from-rip",
        "native_code_range_kind": "observed-instructions-from-rip",
        "dac_token": token,
        "dac_module": module,
        "diagnostic_error": diagnostic,
    }


# ---------------------------------------------------------------------------
# author (interpreter) route
# ---------------------------------------------------------------------------

def interp_breakpoint_command(md, layout):
    """Conditional InterpExecMethod breakpoint: r9==0 and frame MD equal to target."""
    md_hex = _hex(_require_md(md, "method descriptor"), "method descriptor")
    offsets = _layout_offsets(layout)
    chain = "poi(poi(poi(@rdx+0x%x)+0x%x)+0x%x)" % (
        offsets["start_ip_off"],
        offsets["method_off"],
        offsets["method_hnd_off"],
    )
    inner = (
        ".if ("
        + chain
        + "=="
        + md_hex
        + ") { .echo "
        + MARKER_INTERP_HIT
        + " } .else { gc }"
    )
    middle = ".if (@rdx!=0) { " + inner + " } .else { gc }"
    outer = ".if (@r9==0) { " + middle + " } .else { gc }"
    return 'bp coreclr!InterpExecMethod "' + outer + '"'


def capture_interp_commands(layout, md=None):
    """Read the frame, startIp, method chain, codeSize (dwo), interpreter code and dumpmd.

    md is optional; when the caller already knows the MethodDesc from the host record it is
    emitted as the !dumpmd argument instead of the frame-derived expression, which avoids any
    SOS expression parsing of nested poi terms. Without md the frame chain is used.
    """
    offsets = _layout_offsets(layout)
    sip = "0x%x" % offsets["start_ip_off"]
    method_off = "0x%x" % offsets["method_off"]
    hnd = "0x%x" % offsets["method_hnd_off"]
    codesize = "0x%x" % offsets["codesize_off"]
    interp_code = "0x%x" % offsets["m_interp_code_off"]
    start_size = "0x%x" % offsets["bytecode_start_size"]

    method_ptr = "poi(poi(@rdx+" + sip + ")+" + method_off + ")"
    hnd_ptr = "poi(" + method_ptr + "+" + hnd + ")"

    if md is None:
        dump_md_arg = hnd_ptr
    else:
        dump_md_arg = _hex(_require_md(md, "method descriptor"), "method descriptor")

    start_ip_expr = "poi(@rdx+" + sip + ")"
    return [
        ".echo " + MARKER_INTERP_FRAME,
        "r rdx",
        "r r9",
        "r rip",
        ".echo " + MARKER_INTERP_STARTIP,
        _printf_u64(start_ip_expr),
        ".echo " + MARKER_INTERP_METHOD,
        _printf_u64(method_ptr),
        ".echo " + MARKER_INTERP_METHODHND,
        _printf_u64(hnd_ptr),
        ".echo " + MARKER_INTERP_CODESIZE,
        _printf_u32("dwo(" + method_ptr + "+" + codesize + ")"),
        ".echo " + MARKER_INTERP_INTERPCODE,
        _printf_u64("poi(" + hnd_ptr + "+" + interp_code + ")"),
        ".echo " + MARKER_INTERP_DUMPMD,
        "!dumpmd " + dump_md_arg,
        ".echo " + MARKER_INTERP_IRSTART,
        _printf_u64(start_ip_expr + "+" + start_size),
        ".echo " + MARKER_INTERP_END,
    ]


def parse_interp_capture(text, layout, expected_md):
    """Parse one interpreter entry stop; rejects resume frames and any inconsistency.

    pc is the native InterpExecMethod stop address, never an IR address. The IR body is
    reported separately as ir_code_start = startIp + bytecode_start_size, with
    ir_size_bytes = codeSize slots * 4.
    """
    want = _require_md(expected_md, "expected method descriptor")
    offsets = _layout_offsets(layout)
    lines = _output_lines(text)
    _reject_debugger_failure(lines)
    _require_marker(lines, MARKER_INTERP_HIT)

    frame_part = _section(lines, MARKER_INTERP_FRAME, MARKER_INTERP_STARTIP)
    startip_part = _section(lines, MARKER_INTERP_STARTIP, MARKER_INTERP_METHOD)
    method_part = _section(lines, MARKER_INTERP_METHOD, MARKER_INTERP_METHODHND)
    hnd_part = _section(lines, MARKER_INTERP_METHODHND, MARKER_INTERP_CODESIZE)
    codesize_part = _section(lines, MARKER_INTERP_CODESIZE, MARKER_INTERP_INTERPCODE)
    interpcode_part = _section(lines, MARKER_INTERP_INTERPCODE, MARKER_INTERP_DUMPMD)
    dumpmd_part = _section(lines, MARKER_INTERP_DUMPMD, MARKER_INTERP_IRSTART)
    irstart_part = _section(lines, MARKER_INTERP_IRSTART, MARKER_INTERP_END)

    frame = _register(frame_part, "rdx")
    r9 = _register(frame_part, "r9")
    pc = _register(frame_part, "rip")
    if frame == 0:
        raise ValueError("frame pointer rdx is null")
    if pc == 0:
        raise ValueError("stop RIP is null")
    if r9 != 0:
        raise ValueError(
            "exception-clause resume (r9=0x%x != 0); this is not a method entry" % r9
        )

    start_ip = _single_value(startip_part, _VALUE, "startIp")
    method = _single_value(method_part, _VALUE, "InterpMethod pointer")
    method_hnd = _single_value(hnd_part, _VALUE, "methodHnd")
    slots = _single_value(codesize_part, _VALUE, "codeSize slots")
    interp_code = _single_value(interpcode_part, _VALUE, "m_interpreterCode")
    ir_start_observed = _single_value(irstart_part, _VALUE, "IR start expression")

    if method == 0:
        raise ValueError("InterpMethod pointer is null")
    if start_ip == 0 or start_ip % 4 != 0:
        raise ValueError("startIp 0x%x is null or not int32-aligned" % start_ip)
    if method_hnd != want:
        raise ValueError(
            "frame methodHnd 0x%x does not match expected MethodDesc 0x%x"
            % (method_hnd, want)
        )
    if slots <= 0:
        raise ValueError("codeSize is %d int32 slots; a method body must be non-empty" % slots)
    if slots > _MAX_CODE_SLOTS:
        raise ValueError("codeSize %d slots is implausible; refusing to use it" % slots)
    if interp_code != start_ip:
        raise ValueError(
            "MethodDesc.m_interpreterCode 0x%x does not equal frame startIp 0x%x"
            % (interp_code, start_ip)
        )

    ir_start = start_ip + offsets["bytecode_start_size"]
    if ir_start_observed != ir_start:
        raise ValueError(
            "observed IR start 0x%x != startIp+sizeof(InterpByteCodeStart) 0x%x"
            % (ir_start_observed, ir_start)
        )
    ir_size = slots * 4

    observed = _methoddesc_values(dumpmd_part)
    if observed and observed != {want}:
        raise ValueError(
            "!dumpmd MethodDesc observations %s do not match expected %s"
            % (_fmt_set(observed), _hex(want, "expected MethodDesc"))
        )
    token = _methoddef_token(_unique_value(dumpmd_part, _TOKEN_LINE, "mdToken"), "mdToken")
    module = _unique_value(dumpmd_part, _MODULE_LINE, "Module")
    if module == 0:
        raise ValueError("!dumpmd Module observation is null")
    if not any(_METHOD_NAME.match(line) for line in dumpmd_part):
        raise ValueError("!dumpmd output has no Method Name line")

    return {
        "target": "author",
        "md_value": want,
        "stop_kind": "interp-first-entry",
        "entry_kind": "first-entry",
        "pc": pc,
        "actual_native_pc": pc,
        "frame": frame,
        "start_ip": start_ip,
        "method_pointer": method,
        "method_hnd": method_hnd,
        "exception_clause_args": r9,
        "code_size_slots": slots,
        "bytecode_start_size": offsets["bytecode_start_size"],
        "ir_code_start": ir_start,
        "ir_code_size": ir_size,
        "ir_size_bytes": ir_size,
        "ir_code_end": ir_start + ir_size,
        "methoddesc_interpreter_code": interp_code,
        "dac_token": token,
        "dac_module": module,
        "diagnostic_error": None,
    }


# ---------------------------------------------------------------------------
# natural-code probes (observation only, never execution evidence)
# ---------------------------------------------------------------------------

def code_probe_commands(md, layout):
    """Observe the natural code state of md: dumpmd header, m_interpreterCode, interpreter module.

    Nothing here is an execution observation. The outputs only say which code address DAC
    reports and whether the MethodDesc carries interpreter code; they must never be turned
    into a stop event.
    """
    md_hex = _hex(_require_md(md, "method descriptor"), "method descriptor")
    offsets = _layout_offsets(layout)
    return [
        ".echo " + MARKER_CODE_PROBE_BEGIN,
        "!dumpmd " + md_hex,
        ".echo " + MARKER_CODE_PROBE_INTERPCODE,
        _printf_u64("poi(" + md_hex + "+0x%x)" % offsets["m_interp_code_off"]),
        ".echo " + MARKER_CODE_PROBE_MODULE,
        "lm m clrinterpreter",
        ".echo " + MARKER_CODE_PROBE_END,
    ]


def parse_code_probe(text, layout, expected_md):
    """Read a code probe; the result is explicitly not an execution event."""
    want = _require_md(expected_md, "expected method descriptor")
    _layout_offsets(layout)
    lines = _output_lines(text)
    _reject_debugger_failure(lines)
    _require_marker(lines, MARKER_CODE_PROBE_BEGIN)
    dump = _section(lines, MARKER_CODE_PROBE_BEGIN, MARKER_CODE_PROBE_INTERPCODE)
    interp = _section(lines, MARKER_CODE_PROBE_INTERPCODE, MARKER_CODE_PROBE_MODULE)
    module_part = _section(lines, MARKER_CODE_PROBE_MODULE, MARKER_CODE_PROBE_END)

    observed = _methoddesc_values(dump)
    if observed and observed != {want}:
        raise ValueError(
            "!dumpmd MethodDesc observations %s do not match expected %s"
            % (_fmt_set(observed), _hex(want, "expected MethodDesc"))
        )
    token = _methoddef_token(_unique_value(dump, _TOKEN_LINE, "mdToken"), "mdToken")
    module = _unique_value(dump, _MODULE_LINE, "Module")
    if module == 0:
        raise ValueError("!dumpmd Module observation is null")
    if not any(_METHOD_NAME.match(line) for line in dump):
        raise ValueError("!dumpmd output has no Method Name line")

    current = _active_code_addr(dump)
    if current is None:
        raise ValueError(
            "!dumpmd reported no active Current CodeAddr; a per-version history entry is not a code address"
        )
    current = _require_code_addr(current, "observed Current CodeAddr")

    raw_interp = _single_value(interp, _VALUE, "m_interpreterCode")
    if raw_interp == 0:
        state = "null"
        interp_addr = None
    elif raw_interp == 1:
        state = "poison"
        interp_addr = None
    else:
        if raw_interp % 4 != 0:
            raise ValueError("m_interpreterCode 0x%x is not int32 aligned" % raw_interp)
        state = "set"
        interp_addr = raw_interp

    module_lines = [line.strip()[:200] for line in module_part if line.strip()]
    return {
        "probe_kind": "code-probe",
        "execution_evidence": False,
        "md_value": want,
        "dac_token": token,
        "dac_module": module,
        "current_code_addr": current,
        "methoddesc_interpreter_code": raw_interp,
        "interpreter_code_state": state,
        "interpreter_code_addr": interp_addr,
        "interpreter_module_lines": module_lines[:10],
    }


def framework_compile_breakpoint_commands(md):
    """Break on the natural compilation notification for md.

    coreclr!DACNotifyCompilationFinished(MethodDesc *methodDesc, PCODE pCode) is called
    unconditionally after PrepareCode finishes, with methodDesc in rcx and pCode in rdx on
    x64. This is a notification site, not a method body breakpoint, and it is never
    execution evidence.
    """
    md_hex = _hex(_require_md(md, "method descriptor"), "method descriptor")
    inner = ".if (@rcx==" + md_hex + ") { .echo " + MARKER_COMPILE_READY + " } .else { gc }"
    return ['bp coreclr!DACNotifyCompilationFinished "' + inner + '"']


def capture_compile_commands():
    """Read the notification registers; the stop is a compilation event, never a method hit."""
    return [
        ".echo " + MARKER_COMPILE_BEGIN,
        "r rcx",
        "r rdx",
        ".echo " + MARKER_COMPILE_END,
    ]


def parse_compile_stop(text, expected_md):
    """Parse a natural-compilation stop; returns the observed MethodDesc and code pointer."""
    want = _require_md(expected_md, "expected method descriptor")
    lines = _output_lines(text)
    _reject_debugger_failure(lines)
    _require_marker(lines, MARKER_COMPILE_READY)
    begin = _require_marker(lines, MARKER_COMPILE_BEGIN)
    if not any(_COMPILE_SYMBOL.match(line) for line in lines[:begin]):
        raise ValueError(
            "no real coreclr!DACNotifyCompilationFinished stop precedes the capture section"
        )
    body = _section(lines, MARKER_COMPILE_BEGIN, MARKER_COMPILE_END)

    rcx = _register(body, "rcx")
    rdx = _register(body, "rdx")
    if rcx != want:
        raise ValueError(
            "DACNotifyCompilationFinished rcx 0x%x is not the expected MethodDesc 0x%x"
            % (rcx, want)
        )
    if rdx in (0, 1):
        raise ValueError(
            "DACNotifyCompilationFinished rdx is 0x%x; there is no compiled code pointer" % rdx
        )
    if rdx >= 1 << 64:
        raise ValueError("observed compiled code pointer does not fit in 64 bits")

    return {
        "probe_kind": "compile-stop",
        "execution_evidence": False,
        "md_value": want,
        "compiled_md": rcx,
        "compiled_code": rdx,
        "stop_symbol": "coreclr!DACNotifyCompilationFinished",
    }

def code_address_inspection_commands(code_addr):
    """Read-only inspection of a natural code address: ip2md, region info, protection, disassembly."""
    addr = _hex(_require_code_addr(code_addr, "code address"), "code address")
    return [
        ".echo " + MARKER_CODE_INSPECT_BEGIN,
        "!ip2md " + addr,
        ".echo " + MARKER_CODE_INSPECT_ADDRESS,
        "!address " + addr,
        ".echo " + MARKER_CODE_INSPECT_VPROT,
        "!vprot " + addr,
        ".echo " + MARKER_CODE_INSPECT_DISASM,
        "u " + addr + " L0x40",
        ".echo " + MARKER_CODE_INSPECT_END,
    ]


def hardware_execute_breakpoint_commands(code_addr):
    """Arm an execute-only hardware breakpoint; no software bp and no target memory write."""
    addr = _hex(_require_code_addr(code_addr, "code address"), "code address")
    return [
        ".echo " + MARKER_HW_ARM,
        "ba e 1 " + addr,
        ".echo " + MARKER_HW_ARMED,
    ]

# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cleanup_commands():
    """Remove native and pending SOS breakpoints; install nothing new."""
    return [
        ".echo " + MARKER_CLEANUP,
        "bc *",
        "!bpmd -clearall",
        ".echo " + MARKER_CLEANUP_DONE,
    ]
