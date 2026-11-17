"""Synthetic unit tests for cdb_commands.py.

Command text and parser correctness only. No debugger or debuggee is launched, and no
fixture here proves a live method witness. Every fixture is a hand written CDB transcript
fragment that keeps the prompt echoes, so the echo filter and the marker rules are
exercised instead of being assumed.
"""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("cdb_commands_under_test", HERE / "cdb_commands.py")
M = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M)

BT = chr(96)
BS = chr(92)


def a64(hi, lo):
    return hi + BT + lo


def eval_u64(expression):
    return '.printf "%016I64x' + BS + 'n", ' + expression


def eval_u32(expression):
    return '.printf "%08x' + BS + 'n", ' + expression


def sizeof_probe(type_name):
    return (
        '.printf "SIZEOF-' + type_name + ' 0x%I64x' + BS + 'n", @@c++(sizeof(coreclr!' + type_name + '))'
    )


RIP_FW = a64("00007ff8", "b96e85a8")
RIP_INTERP = a64("00007ff8", "b96c1000")
FRAME = a64("000001f8", "39f50000")
START_IP = a64("00000208", "1a670010")
IR_START = a64("00000208", "1a670018")
INTERP_METHOD = a64("00000208", "1a670040")
MD_VALUE = 0x1f839f50000
MD_TEXT = a64("000001f8", "39f50000")
MODULE = a64("000001f8", "39f4d010")
OTHER_MD_TEXT = a64("000001f8", "39f50008")


def prompt(command):
    return "0:000> " + command


def transcript(rows):
    return "\n".join(rows) + "\n"


def layout_outputs():
    return {
        "InterpMethodContextFrame": transcript([
            prompt("dt coreclr!InterpMethodContextFrame"),
            "   +0x000 pParent                : Ptr64 InterpMethodContextFrame",
            "   +0x008 startIp                : Ptr64 InterpByteCodeStart",
            "   +0x010 pStack                 : Ptr64 Int1B",
            "   +0x018 pRetVal                : Ptr64 Int1B",
            "   +0x020 ip                     : Ptr64 Int4B",
            "   +0x028 pNext                  : Ptr64 InterpMethodContextFrame",
            "   +0x030 runeclrCallbackDeadline : Ptr64 RuneCLRDeadline",
        ]),
        "InterpByteCodeStart": transcript([
            prompt("dt coreclr!InterpByteCodeStart"),
            "   +0x000 Method                 : Ptr64 InterpMethod",
            prompt(sizeof_probe("InterpByteCodeStart")),
            "SIZEOF-InterpByteCodeStart 0x8",
        ]),
        "InterpMethod": transcript([
            prompt("dt coreclr!InterpMethod"),
            "   +0x000 self                   : Ptr64 InterpMethod",
            "   +0x008 methodHnd              : Ptr64 MethodDesc",
            "   +0x010 argsSize               : Int4B",
            "   +0x014 allocaSize             : Int4B",
            "   +0x018 pDataItems             : Ptr64 Ptr64 Void",
            "   +0x020 pCallStub              : Ptr64 CallStubHeader",
            "   +0x028 initLocals             : UChar",
            "   +0x029 unmanagedCallersOnly   : UChar",
            "   +0x02a publishSecretStubParam : UChar",
            "   +0x02c codeSize               : Int4B",
        ]),
        "MethodDesc": transcript([
            prompt("dt coreclr!MethodDesc"),
            "   +0x000 m_wFlags3AndTokenRemainder : Uint2B",
            "   +0x068 m_interpreterCode      : Ptr64 InterpByteCodeStart",
        ]),
    }


def interp_transcript(**overrides):
    r9 = overrides.get("r9", "0000000000000000")
    start_ip = overrides.get("start_ip", START_IP)
    method = overrides.get("method", INTERP_METHOD)
    method_hnd = overrides.get("method_hnd", MD_TEXT)
    slots = overrides.get("slots", "0000001c")
    interp_code = overrides.get("interp_code", START_IP)
    ir_start = overrides.get("ir_start", IR_START)
    token = overrides.get("token", "0600000b")
    module = overrides.get("module", MODULE)
    dump_md = overrides.get("dump_md", MD_TEXT)
    md_line = overrides.get("md_line", True)
    method_name = overrides.get("method_name", True)
    hit_marker = overrides.get("hit_marker", True)

    rows = []
    if hit_marker:
        rows.extend([prompt(".echo " + M.MARKER_INTERP_HIT), M.MARKER_INTERP_HIT])
    rows.extend([
        prompt(".echo " + M.MARKER_INTERP_FRAME), M.MARKER_INTERP_FRAME,
        prompt("r rdx"), "rdx=" + FRAME,
        prompt("r r9"), "r9=" + r9,
        prompt("r rip"), "rip=" + RIP_INTERP,
        prompt(".echo " + M.MARKER_INTERP_STARTIP), M.MARKER_INTERP_STARTIP,
        prompt(eval_u64("poi(@rdx+0x8)")), start_ip,
        prompt(".echo " + M.MARKER_INTERP_METHOD), M.MARKER_INTERP_METHOD,
        prompt(eval_u64("poi(poi(@rdx+0x8)+0x0)")), method,
        prompt(".echo " + M.MARKER_INTERP_METHODHND), M.MARKER_INTERP_METHODHND,
        prompt(eval_u64("poi(poi(poi(@rdx+0x8)+0x0)+0x8)")), method_hnd,
        prompt(".echo " + M.MARKER_INTERP_CODESIZE), M.MARKER_INTERP_CODESIZE,
        prompt(eval_u32("dwo(poi(poi(@rdx+0x8)+0x0)+0x2c)")), slots,
        prompt(".echo " + M.MARKER_INTERP_INTERPCODE), M.MARKER_INTERP_INTERPCODE,
        prompt(eval_u64("poi(poi(poi(poi(@rdx+0x8)+0x0)+0x8)+0x68)")), interp_code,
        prompt(".echo " + M.MARKER_INTERP_DUMPMD), M.MARKER_INTERP_DUMPMD,
    ])
    if md_line:
        rows.append("MethodDesc:          " + dump_md)
    if method_name:
        rows.append("Method Name:         AuthorEntry.Run(IGroupedHostContract, Int32)")
    rows.extend([
        "Class:               " + a64("000001f8", "39f4e0a0"),
        "MethodTable:         " + a64("000001f8", "39f4e1f0"),
        "mdToken:             " + token,
        "Module:              " + module,
        "IsJitted:            no",
        prompt(".echo " + M.MARKER_INTERP_IRSTART), M.MARKER_INTERP_IRSTART,
        prompt(eval_u64("poi(@rdx+0x8)+0x8")), ir_start,
        prompt(".echo " + M.MARKER_INTERP_END), M.MARKER_INTERP_END,
    ])
    return transcript(rows)


def jit_instructions():
    return [
        (RIP_FW, "48895c2420", "mov     qword ptr [rsp+20h],rbx"),
        (a64("00007ff8", "b96e85ad"), "55", "push    rbp"),
        (a64("00007ff8", "b96e85ae"), "57", "push    rdi"),
    ]


def jit_transcript(**overrides):
    ip2md_md = overrides.get("ip2md_md", MD_TEXT)
    stub = overrides.get("stub", False)
    code_addr = overrides.get("code_addr", RIP_FW)
    instructions = overrides.get("instructions", jit_instructions())
    method_name = overrides.get("method_name", True)
    token = overrides.get("token", "06000001")

    rows = [
        prompt(".echo " + M.MARKER_JIT_HIT), M.MARKER_JIT_HIT,
        prompt("r rip"), "rip=" + RIP_FW,
        prompt("!ip2md @rip"),
        "MethodDesc:          " + ip2md_md + (" (stub)" if stub else ""),
    ]
    if method_name:
        rows.append("Method Name:         FrameworkEntry.Initialize(IGroupedHostContract)")
    rows.extend([
        "Class:               " + a64("000001f8", "39f4e0a0"),
        "MethodTable:         " + a64("000001f8", "39f4e1f0"),
        "Module:              " + MODULE,
        prompt("!dumpmd 0x1f839f50000"),
        "Class:               " + a64("000001f8", "39f4e0a0"),
        "MethodTable:         " + a64("000001f8", "39f4e1f0"),
        "mdToken:             " + token,
        "Module:              " + MODULE,
        "IsJitted:            yes",
        "CodeAddr:            " + code_addr,
        prompt("u @rip L0x40"),
        "coreclr!FrameworkEntry.Initialize:",
    ])
    for address, code, mnemonic in instructions:
        rows.append(address + " " + code + "      " + mnemonic)
    rows.extend([prompt(".echo " + M.MARKER_JIT_END), M.MARKER_JIT_END])
    return transcript(rows)


class TestBootstrap(unittest.TestCase):
    ROOT = "D:/example/runtime/layout/net12.0-windows-Release-x64"
    SOS = "C:/tools/sos/sos.dll"

    def test_sequence_is_the_proven_route(self):
        commands = M.bootstrap_commands(self.ROOT, self.SOS)
        self.assertEqual(commands, [
            ".echo " + M.MARKER_BOOT_BEGIN,
            "sxe ld:coreclr.dll",
            "g",
            ".echo " + M.MARKER_BOOT_AT_LOAD,
            ".sympath+ " + self.ROOT,
            ".reload /f coreclr.dll",
            "x coreclr!Assembly::ExecuteMainMethod",
            "bp coreclr!Assembly::ExecuteMainMethod",
            "g",
            ".echo " + M.MARKER_BOOT_AT_EXECMAIN,
            ".load " + self.SOS,
            "!sosstatus",
            "!dumpdomain",
        ])

    def test_stops_at_loader_then_execute_main_method(self):
        commands = M.bootstrap_commands(self.ROOT, self.SOS)
        self.assertEqual(commands[1], "sxe ld:coreclr.dll")
        self.assertIn(".reload /f coreclr.dll", commands)
        self.assertIn(".load " + self.SOS, commands)
        self.assertLess(commands.index("!sosstatus"), commands.index("!dumpdomain"))

    def test_no_unsupported_sos_commands(self):
        joined = " ".join(M.bootstrap_commands(self.ROOT, self.SOS)).lower()
        for forbidden in ("dacinfo", "!dumpmodule", "!eeheap", "!modules", " modules"):
            self.assertNotIn(forbidden, joined)

    def test_quotes_path_with_spaces(self):
        commands = M.bootstrap_commands("C:/Program Files/runtime x", "C:/sos dir/sos.dll")
        self.assertIn('.sympath+ "C:/Program Files/runtime x"', commands)
        self.assertIn('.load "C:/sos dir/sos.dll"', commands)

    def test_rejects_unusable_paths(self):
        for root in ("", "   ", "C:/a\n.reload", "C:/a\rg", "C:/a;b", 'C:/a"b'):
            with self.assertRaises(ValueError):
                M.bootstrap_commands(root, self.SOS)
        with self.assertRaises(ValueError):
            M.bootstrap_commands(self.ROOT, "")


class TestLayout(unittest.TestCase):
    def test_parses_dynamic_offsets_and_size(self):
        layout = M.parse_layout(layout_outputs())
        self.assertEqual(sorted(layout.keys()), sorted([
            "start_ip_off", "method_off", "method_hnd_off",
            "codesize_off", "m_interp_code_off", "bytecode_start_size",
        ]))
        self.assertEqual(layout["start_ip_off"], 0x8)
        self.assertEqual(layout["method_off"], 0x0)
        self.assertEqual(layout["method_hnd_off"], 0x8)
        self.assertEqual(layout["codesize_off"], 0x2c)
        self.assertEqual(layout["m_interp_code_off"], 0x68)
        self.assertEqual(layout["bytecode_start_size"], 0x8)

    def test_accepts_one_combined_probe_transcript(self):
        outputs = layout_outputs()
        combined = transcript([prompt("dt coreclr!InterpMethodContextFrame")])
        combined += outputs["InterpMethodContextFrame"].split("\n", 1)[1] + "\n"
        combined += transcript([prompt("dt coreclr!InterpByteCodeStart")])
        combined += outputs["InterpByteCodeStart"].split("\n", 1)[1] + "\n"
        combined += transcript([prompt(sizeof_probe("InterpByteCodeStart")), "SIZEOF-InterpByteCodeStart 0x8"])
        combined += transcript([prompt("dt coreclr!InterpMethod")])
        combined += outputs["InterpMethod"].split("\n", 1)[1] + "\n"
        combined += transcript([prompt("dt coreclr!MethodDesc")])
        combined += outputs["MethodDesc"].split("\n", 1)[1] + "\n"
        self.assertEqual(M.parse_layout({"dt": combined}), M.parse_layout(outputs))

    def test_accepts_coreclr_prefixed_keys(self):
        outputs = {"coreclr!" + key: value for key, value in layout_outputs().items()}
        self.assertEqual(M.parse_layout(outputs), M.parse_layout(layout_outputs()))

    def test_requires_every_type(self):
        for missing in M.LAYOUT_TYPES:
            outputs = layout_outputs()
            del outputs[missing]
            with self.assertRaises(ValueError):
                M.parse_layout(outputs)

    def test_rejects_non_mapping(self):
        with self.assertRaises(ValueError):
            M.parse_layout({})
        with self.assertRaises(ValueError):
            M.parse_layout(None)

    def test_rejects_missing_field(self):
        outputs = layout_outputs()
        outputs["InterpMethodContextFrame"] = transcript([
            prompt("dt coreclr!InterpMethodContextFrame"),
            "   +0x000 pParent : Ptr64 InterpMethodContextFrame",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_duplicate_field(self):
        outputs = layout_outputs()
        outputs["InterpMethodContextFrame"] = transcript([
            "   +0x008 startIp : Ptr64 InterpByteCodeStart",
            "   +0x010 startIp : Ptr64 InterpByteCodeStart",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_misaligned_pointer_field(self):
        outputs = layout_outputs()
        outputs["InterpMethodContextFrame"] = transcript([
            "   +0x006 startIp : Ptr64 InterpByteCodeStart",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_probe_uses_labelled_printf_hex(self):
        commands = M.layout_probe_commands()
        self.assertIn(sizeof_probe("InterpByteCodeStart"), commands)
        self.assertIn("0x%I64x", sizeof_probe("InterpByteCodeStart"))
        for command in commands:
            self.assertNotIn("?? sizeof", command)

    def test_accepts_typed_size_with_0x_prefix(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            "   +0x000 Method : Ptr64 InterpMethod",
            "unsigned int64 0x8",
        ])
        self.assertEqual(M.parse_layout(outputs)["bytecode_start_size"], 0x8)

    def test_rejects_bare_typed_decimal_size(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            "   +0x000 Method : Ptr64 InterpMethod",
            "unsigned int64 8",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_size_labelled_for_another_type(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            "   +0x000 Method : Ptr64 InterpMethod",
            "SIZEOF-InterpMethod 0x8",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_absent_size(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            prompt("dt coreclr!InterpByteCodeStart"),
            "   +0x000 Method : Ptr64 InterpMethod",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_decimal_size(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            "   +0x000 Method : Ptr64 InterpMethod",
            "size: 8",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_rejects_conflicting_sizes(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            "   +0x000 Method : Ptr64 InterpMethod",
            "unsigned int64 0x8",
            "unsigned int64 0x10",
        ])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)

    def test_echo_only_block_is_empty(self):
        outputs = layout_outputs()
        outputs["MethodDesc"] = transcript([prompt("dt coreclr!MethodDesc")])
        with self.assertRaises(ValueError):
            M.parse_layout(outputs)


class TestCommandText(unittest.TestCase):
    def setUp(self):
        self.layout = M.parse_layout(layout_outputs())

    def test_framework_breakpoint_uses_hex_md(self):
        self.assertEqual(M.framework_breakpoint_commands(MD_VALUE), ["!bpmd -md 0x1f839f50000"])

    def test_jit_capture_sequence(self):
        commands = M.capture_jit_commands(MD_VALUE)
        self.assertEqual(commands, [
            ".echo " + M.MARKER_JIT_HIT,
            "r rip",
            "!ip2md @rip",
            "!dumpmd 0x1f839f50000",
            "u @rip L0x40",
            ".echo " + M.MARKER_JIT_END,
        ])

    def test_interp_breakpoint_is_conditional_on_r9_and_md(self):
        command = M.interp_breakpoint_command(MD_VALUE, self.layout)
        self.assertTrue(command.startswith('bp coreclr!InterpExecMethod "'))
        self.assertTrue(command.endswith('"'))
        self.assertIn("@r9==0", command)
        self.assertIn("@rdx!=0", command)
        self.assertIn("poi(poi(poi(@rdx+0x8)+0x0)+0x8)==0x1f839f50000", command)
        self.assertIn("WITNESS-INTERP-HIT", command)
        self.assertIn(".else { gc }", command)

    def test_interp_breakpoint_uses_nested_if_blocks_without_logical_and(self):
        command = M.interp_breakpoint_command(MD_VALUE, self.layout)
        self.assertNotIn("&&", command)
        self.assertNotIn("||", command)
        self.assertEqual(command.count(".else { gc }"), 3)
        self.assertEqual(command.count("{"), command.count("}"))
        i_r9 = command.index("@r9==0")
        i_rdx = command.index("@rdx!=0")
        i_deref = command.index("poi(")
        i_chain = command.index("poi(poi(poi(@rdx+0x8)+0x0)+0x8)==0x1f839f50000")
        i_hit = command.index("WITNESS-INTERP-HIT")
        self.assertLess(i_r9, i_rdx)
        self.assertLess(i_rdx, i_deref)
        self.assertEqual(i_deref, i_chain)
        self.assertLess(i_chain, i_hit)
        self.assertTrue(command.startswith('bp coreclr!InterpExecMethod ".if (@r9==0) { .if (@rdx!=0) { .if ('))
        self.assertTrue(command.endswith(" } .else { gc } } .else { gc } } .else { gc }\""))

    def test_interp_capture_uses_dwo_for_codesize(self):
        commands = M.capture_interp_commands(self.layout)
        self.assertIn(eval_u32("dwo(poi(poi(@rdx+0x8)+0x0)+0x2c)"), commands)
        for command in commands:
            self.assertNotIn("codeSize", command)
            if "0x2c" in command:
                self.assertTrue(command.startswith(".printf "), command)

    def test_interp_capture_follows_layout_offsets(self):
        layout = dict(self.layout)
        layout["codesize_off"] = 0x40
        layout["m_interp_code_off"] = 0x120
        commands = M.capture_interp_commands(layout)
        self.assertIn(eval_u32("dwo(poi(poi(@rdx+0x8)+0x0)+0x40)"), commands)
        self.assertIn(eval_u64("poi(poi(poi(poi(@rdx+0x8)+0x0)+0x8)+0x120)"), commands)

    def test_interp_capture_accepts_known_md_for_dumpmd(self):
        commands = M.capture_interp_commands(self.layout, md=MD_VALUE)
        self.assertIn("!dumpmd 0x1f839f50000", commands)
        for command in commands:
            self.assertNotIn("!dumpmd poi(", command)

    def test_interp_capture_reads_interp_start_from_bytecode_header_size(self):
        layout = dict(self.layout)
        layout["bytecode_start_size"] = 0x10
        commands = M.capture_interp_commands(layout)
        self.assertIn(eval_u64("poi(@rdx+0x8)+0x10"), commands)

    def test_cleanup_clears_and_installs_nothing(self):
        commands = M.cleanup_commands()
        self.assertIn("bc *", commands)
        self.assertIn("!bpmd -clearall", commands)
        for command in commands:
            self.assertFalse(command.startswith("!bpmd -md"), command)
            self.assertFalse(command.startswith("bp "), command)
            self.assertNotIn("InterpExecMethod", command)
            self.assertNotIn("Assembly::ExecuteMainMethod", command)

    def test_every_command_is_single_line_hex_only(self):
        generators = [
            M.bootstrap_commands("D:/rt", "C:/sos/sos.dll"),
            M.layout_probe_commands(),
            M.framework_breakpoint_commands(MD_VALUE),
            M.capture_jit_commands(MD_VALUE),
            [M.interp_breakpoint_command(MD_VALUE, self.layout)],
            M.capture_interp_commands(self.layout),
            M.cleanup_commands(),
        ]
        for commands in generators:
            for command in commands:
                self.assertTrue(command)
                self.assertNotIn("\n", command)
                self.assertNotIn("\r", command)

    def test_md_is_never_emitted_as_decimal(self):
        decimal_text = str(MD_VALUE)
        self.assertNotIn(decimal_text, "".join(M.framework_breakpoint_commands(MD_VALUE)))
        self.assertNotIn(decimal_text, "".join(M.capture_jit_commands(MD_VALUE)))
        self.assertNotIn(decimal_text, M.interp_breakpoint_command(MD_VALUE, self.layout))

    def test_rejects_invalid_md(self):
        for bad in (-1, True, "4096", 1.5, 1 << 70):
            with self.assertRaises(ValueError):
                M.framework_breakpoint_commands(bad)
            with self.assertRaises(ValueError):
                M.capture_jit_commands(bad)
            with self.assertRaises(ValueError):
                M.interp_breakpoint_command(bad, self.layout)

    def test_rejects_incomplete_layout(self):
        for key in ("start_ip_off", "method_off", "method_hnd_off",
                    "codesize_off", "m_interp_code_off", "bytecode_start_size"):
            layout = dict(self.layout)
            del layout[key]
            with self.assertRaises(ValueError):
                M.interp_breakpoint_command(MD_VALUE, layout)
            with self.assertRaises(ValueError):
                M.capture_interp_commands(layout)


class TestInterpParse(unittest.TestCase):
    def setUp(self):
        self.layout = M.parse_layout(layout_outputs())

    def test_happy_path(self):
        event = M.parse_interp_capture(interp_transcript(), self.layout, MD_VALUE)
        self.assertEqual(event["target"], "author")
        self.assertEqual(event["stop_kind"], "interp-first-entry")
        self.assertEqual(event["entry_kind"], "first-entry")
        self.assertEqual(event["md_value"], MD_VALUE)
        self.assertEqual(event["method_hnd"], MD_VALUE)
        self.assertEqual(event["exception_clause_args"], 0)
        self.assertEqual(event["frame"], int(FRAME.replace(BT, ""), 16))
        self.assertEqual(event["start_ip"], int(START_IP.replace(BT, ""), 16))
        self.assertEqual(event["start_ip"] + self.layout["bytecode_start_size"], event["ir_code_start"])
        self.assertEqual(event["bytecode_start_size"], 0x8)
        self.assertEqual(event["ir_size_bytes"], 0x1c * 4)
        self.assertEqual(event["actual_native_pc"], event["pc"])
        self.assertEqual(event["ir_code_size"], 0x1c * 4)
        self.assertEqual(event["ir_code_end"], event["ir_code_start"] + 0x1c * 4)
        self.assertEqual(event["methoddesc_interpreter_code"], event["start_ip"])
        self.assertEqual(event["dac_token"], 0x0600000b)
        self.assertEqual(event["dac_module"], int(MODULE.replace(BT, ""), 16))
        self.assertIsNone(event["diagnostic_error"])
        self.assertNotIn("AuthorEntry", repr(event))

    def test_rejects_exception_clause_resume(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(r9="0000000000000001"), self.layout, MD_VALUE)

    def test_rejects_wrong_md(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(method_hnd=OTHER_MD_TEXT), self.layout, MD_VALUE)
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(), self.layout, MD_VALUE + 8)

    def test_rejects_interpreter_code_mismatch(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(
                interp_transcript(interp_code=a64("00000208", "1a670020")), self.layout, MD_VALUE
            )

    def test_rejects_zero_codesize(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(slots="00000000"), self.layout, MD_VALUE)

    def test_rejects_implausible_codesize(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(slots="7fffffff"), self.layout, MD_VALUE)

    def test_rejects_ir_start_disagreeing_with_header_size(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(
                interp_transcript(ir_start=a64("00000208", "1a670020")), self.layout, MD_VALUE
            )

    def test_rejects_missing_token(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(token=""), self.layout, MD_VALUE)

    def test_rejects_non_methoddef_token(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(token="0200000b"), self.layout, MD_VALUE)

    def test_rejects_missing_method_name(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(method_name=False), self.layout, MD_VALUE)

    def test_rejects_wrong_dumpmd_md_when_reported(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(dump_md=OTHER_MD_TEXT), self.layout, MD_VALUE)

    def test_dumpmd_md_line_is_optional(self):
        event = M.parse_interp_capture(interp_transcript(md_line=False), self.layout, MD_VALUE)
        self.assertEqual(event["method_hnd"], MD_VALUE)

    def test_rejects_missing_hit_marker(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(interp_transcript(hit_marker=False), self.layout, MD_VALUE)

    def test_rejects_missing_end_marker(self):
        text = interp_transcript().replace(M.MARKER_INTERP_END, "")
        with self.assertRaises(ValueError):
            M.parse_interp_capture(text, self.layout, MD_VALUE)

    def test_rejects_command_echo_only(self):
        text = transcript([
            prompt(".echo " + M.MARKER_INTERP_HIT),
            prompt("r r9"),
            prompt(eval_u64("poi(poi(poi(@rdx+0x8)+0x0)+0x8)")),
        ])
        with self.assertRaises(ValueError):
            M.parse_interp_capture(text, self.layout, MD_VALUE)

    def test_tolerates_trailing_annotations_on_token_and_module(self):
        text = interp_transcript()
        text = text.replace("mdToken:             0600000b", "mdToken:             0600000b (MethodDef)")
        text = text.replace("Module:              " + MODULE, "Module:              " + MODULE + " Example.Assembly.dll")
        event = M.parse_interp_capture(text, self.layout, MD_VALUE)
        self.assertEqual(event["dac_token"], 0x0600000b)
        self.assertEqual(event["dac_module"], int(MODULE.replace(BT, ""), 16))

    def test_rejects_null_frame(self):
        text = interp_transcript().replace("rdx=" + FRAME, "rdx=0000000000000000")
        with self.assertRaises(ValueError):
            M.parse_interp_capture(text, self.layout, MD_VALUE)


class TestJitParse(unittest.TestCase):
    def test_happy_path_records_observed_span(self):
        event = M.parse_jit_capture(jit_transcript(), MD_VALUE)
        self.assertEqual(event["target"], "framework")
        self.assertEqual(event["stop_kind"], "jit-native")
        self.assertTrue(event["range_complete"])
        self.assertEqual(event["md_value"], MD_VALUE)
        self.assertEqual(event["pc"], int(RIP_FW.replace(BT, ""), 16))
        self.assertEqual(event["native_code_start"], event["pc"])
        self.assertEqual(event["native_code_size"], 5 + 1 + 1)
        self.assertEqual(event["native_instruction_count"], 3)
        self.assertEqual(event["ip2md_md"], MD_VALUE)
        self.assertEqual(event["actual_native_pc"], event["pc"])
        self.assertEqual(event["dac_native_code_addr"], event["pc"])
        self.assertTrue(event["native_body_bound_to_dac"])
        self.assertEqual(event["range_kind"], "observed-instructions-from-rip")
        self.assertEqual(event["observed_span_start"], event["pc"])
        self.assertEqual(event["observed_span_size"], 5 + 1 + 1)
        self.assertEqual(event["observed_span_instructions"], 3)
        self.assertEqual(event["native_code_range_kind"], "observed-instructions-from-rip")
        self.assertEqual(event["dac_token"], 0x06000001)
        self.assertEqual(event["dac_module"], int(MODULE.replace(BT, ""), 16))
        self.assertIsNone(event["diagnostic_error"])

    def test_non_contiguous_disassembly_is_partial(self):
        instructions = [
            (RIP_FW, "48895c2420", "mov     qword ptr [rsp+20h],rbx"),
            (a64("00007ff8", "b96e85b0"), "55", "push    rbp"),
        ]
        event = M.parse_jit_capture(jit_transcript(instructions=instructions), MD_VALUE)
        self.assertFalse(event["range_complete"])
        self.assertEqual(event["stop_kind"], "jit-native-partial")
        self.assertIsNone(event["native_code_start"])
        self.assertIsNone(event["native_code_size"])
        self.assertTrue(event["diagnostic_error"])

    def test_partial_still_reports_ip2md_md(self):
        event = M.parse_jit_capture(jit_transcript(instructions=[]), MD_VALUE)
        self.assertEqual(event["ip2md_md"], MD_VALUE)
        self.assertEqual(event["actual_native_pc"], event["pc"])
        self.assertEqual(event["range_kind"], "observed-instructions-from-rip")
        self.assertIsNone(event["observed_span_start"])

    def test_missing_disassembly_is_partial(self):
        event = M.parse_jit_capture(jit_transcript(instructions=[]), MD_VALUE)
        self.assertFalse(event["range_complete"])
        self.assertIsNone(event["native_code_start"])
        self.assertIsNone(event["native_code_size"])

    def test_rejects_wrong_md(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(ip2md_md=OTHER_MD_TEXT), MD_VALUE)
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(), MD_VALUE + 8)

    def test_rejects_stub(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(stub=True), MD_VALUE)

    def test_missing_code_addr_never_grants_full_success(self):
        text = jit_transcript()
        lines = [line for line in text.split("\n") if not line.startswith("CodeAddr:")]
        event = M.parse_jit_capture("\n".join(lines), MD_VALUE)
        self.assertEqual(event["stop_kind"], "jit-native-partial")
        self.assertFalse(event["range_complete"])
        self.assertFalse(event["native_body_bound_to_dac"])
        self.assertIsNone(event["dac_native_code_addr"])
        self.assertIsNone(event["native_code_start"])
        self.assertIsNone(event["native_code_size"])
        self.assertEqual(event["observed_span_start"], event["pc"])
        self.assertEqual(event["observed_span_size"], 5 + 1 + 1)
        self.assertTrue(event["diagnostic_error"])

    def test_rejects_code_addr_mismatch(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(code_addr=a64("00007ff8", "b96e85b0")), MD_VALUE)

    def test_rejects_non_methoddef_token(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(token="02000001"), MD_VALUE)

    def test_rejects_missing_method_name(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(jit_transcript(method_name=False), MD_VALUE)

    def test_rejects_command_echo_only(self):
        text = transcript([
            prompt(".echo " + M.MARKER_JIT_HIT),
            prompt("r rip"),
            prompt("!ip2md @rip"),
            prompt("u @rip L0x40"),
        ])
        with self.assertRaises(ValueError):
            M.parse_jit_capture(text, MD_VALUE)

    def test_rejects_duplicate_markers_from_two_stops(self):
        text = jit_transcript() + jit_transcript()
        with self.assertRaises(ValueError):
            M.parse_jit_capture(text, MD_VALUE)



class TestInlinePromptFormat(unittest.TestCase):
    """Real CDB pipe format: no command echo, prompt glued to the first output line."""

    def setUp(self):
        self.layout = M.parse_layout(layout_outputs())

    def test_layout_keeps_prompted_field_and_size(self):
        outputs = layout_outputs()
        outputs["InterpByteCodeStart"] = transcript([
            prompt("dt coreclr!InterpByteCodeStart"),
            prompt("   +0x000 Method           : Ptr64 InterpMethod"),
            prompt("SIZEOF-InterpByteCodeStart 0x8"),
        ])
        layout = M.parse_layout(outputs)
        self.assertEqual(layout["method_off"], 0x0)
        self.assertEqual(layout["bytecode_start_size"], 0x8)

    def test_layout_prompted_first_field_then_plain_lines(self):
        outputs = layout_outputs()
        outputs["InterpMethodContextFrame"] = transcript([
            prompt("dt coreclr!InterpMethodContextFrame"),
            prompt("   +0x000 pParent          : Ptr64 InterpMethodContextFrame"),
            "   +0x008 startIp          : Ptr64 InterpByteCodeStart",
            "   +0x030 runeclrCallbackDeadline : Ptr64 RuneCLRDeadline",
        ])
        self.assertEqual(M.parse_layout(outputs)["start_ip_off"], 0x8)

    def test_prompted_dt_command_is_dropped_not_parsed(self):
        text = transcript([
            prompt("dt coreclr!InterpMethodContextFrame"),
            prompt("   +0x000 pParent          : Ptr64 InterpMethodContextFrame"),
            prompt("   +0x008 startIp          : Ptr64 InterpByteCodeStart"),
        ])
        lines = M._output_lines(text)
        self.assertFalse(any("dt coreclr!" in line for line in lines))
        self.assertTrue(any("startIp" in line for line in lines))

    def test_prompt_does_not_discard_runtime_output(self):
        text = transcript([
            prompt("SIZEOF-InterpByteCodeStart 0x8"),
            prompt(M.MARKER_INTERP_HIT),
            prompt("rdx=" + FRAME),
            prompt("rip=" + RIP_INTERP),
            prompt("   +0x000 Method           : Ptr64 InterpMethod"),
            prompt("MethodDesc:          " + MD_TEXT),
            prompt("Module:              " + MODULE),
            prompt("mdToken:             0600000b"),
            prompt("quit:"),
        ])
        lines = M._output_lines(text)
        for expected in ("SIZEOF-InterpByteCodeStart 0x8", M.MARKER_INTERP_HIT,
                         "rdx=" + FRAME, "rip=" + RIP_INTERP,
                         "MethodDesc:          " + MD_TEXT,
                         "Module:              " + MODULE,
                         "mdToken:             0600000b",
                         "quit:"):
            self.assertIn(expected, lines)
        self.assertTrue(any("+0x000 Method" in line for line in lines))

    def test_prompted_commands_are_dropped(self):
        for command in (".echo " + M.MARKER_JIT_HIT,
                        ".printf \"x 0x%I64x\\n\", 0",
                        "r r9", "!ip2md @rip", "dt coreclr!InterpMethod",
                        "bp coreclr!InterpExecMethod", "bc *", "u @rip L0x40",
                        "g", "gc", "? 0x10", "?? 0x10",
                        "poi(@rdx+0x8)", "dwo(0x10)", "x coreclr!InterpExecMethod"):
            self.assertEqual(M._output_lines("0:000> " + command), [], command)
        self.assertEqual(M._output_lines("0:000> "), [])
        self.assertEqual(M._output_lines("0:000>"), [])

    def test_prompted_command_echo_only_is_not_proof(self):
        text = transcript([
            prompt(".echo " + M.MARKER_JIT_HIT),
            prompt("r rip"),
            prompt("!ip2md @rip"),
            prompt("u @rip L0x40"),
        ])
        self.assertEqual(M._output_lines(text), [])
        with self.assertRaises(ValueError):
            M.parse_jit_capture(text, MD_VALUE)
        text2 = transcript([
            prompt(".echo " + M.MARKER_INTERP_HIT),
            prompt(eval_u64("poi(poi(poi(@rdx+0x8)+0x0)+0x8)")),
            prompt("r r9"),
        ])
        with self.assertRaises(ValueError):
            M.parse_interp_capture(text2, self.layout, MD_VALUE)

    def test_interp_capture_inline_prompt(self):
        rows = [
            prompt(M.MARKER_INTERP_HIT),
            prompt(M.MARKER_INTERP_FRAME),
            prompt("rdx=" + FRAME),
            "r9=0000000000000000",
            prompt("rip=" + RIP_INTERP),
            prompt(M.MARKER_INTERP_STARTIP),
            prompt(START_IP),
            prompt(M.MARKER_INTERP_METHOD),
            prompt(INTERP_METHOD),
            prompt(M.MARKER_INTERP_METHODHND),
            prompt(MD_TEXT),
            prompt(M.MARKER_INTERP_CODESIZE),
            prompt("0000001c"),
            prompt(M.MARKER_INTERP_INTERPCODE),
            prompt(START_IP),
            prompt(M.MARKER_INTERP_DUMPMD),
            prompt("Method Name:         AuthorEntry.Run(IGroupedHostContract, Int32)"),
            prompt("mdToken:             0600000b"),
            "Module:              " + MODULE,
            prompt(M.MARKER_INTERP_IRSTART),
            prompt(IR_START),
            prompt(M.MARKER_INTERP_END),
        ]
        event = M.parse_interp_capture(transcript(rows), self.layout, MD_VALUE)
        self.assertEqual(event["stop_kind"], "interp-first-entry")
        self.assertEqual(event["pc"], int(RIP_INTERP.replace(BT, ""), 16))
        self.assertEqual(event["ir_code_start"], int(IR_START.replace(BT, ""), 16))
        self.assertNotEqual(event["pc"], event["ir_code_start"])
        self.assertEqual(event["ir_size_bytes"], 0x1c * 4)

    def test_jit_capture_inline_prompt(self):
        rows = [
            prompt(M.MARKER_JIT_HIT),
            prompt("rip=" + RIP_FW),
            prompt("MethodDesc:          " + MD_TEXT),
            "Method Name:         FrameworkEntry.Initialize(IGroupedHostContract)",
            prompt("Module:              " + MODULE),
            "mdToken:             06000001",
            prompt("CodeAddr:            " + RIP_FW),
            prompt(RIP_FW + " 48895c2420      mov     qword ptr [rsp+20h],rbx"),
            a64("00007ff8", "b96e85ad") + " 55              push    rbp",
            prompt(M.MARKER_JIT_END),
        ]
        event = M.parse_jit_capture(transcript(rows), MD_VALUE)
        self.assertEqual(event["stop_kind"], "jit-native")
        self.assertTrue(event["native_body_bound_to_dac"])
        self.assertEqual(event["native_code_start"], int(RIP_FW.replace(BT, ""), 16))
        self.assertEqual(event["native_code_size"], 5 + 1)



def sos9_dumpmd_rows(token="0000000006000003", current_addr=True, history=True):
    """dumpmd field layout as SOS9 prints it: zero-extended token, Current CodeAddr, history."""
    rows = [
        "Method Name:         FrameworkEntry.Initialize(IGroupedHostContract)",
        "Class:               " + a64("000001f8", "39f4e0a0"),
        "MethodTable:         " + a64("000001f8", "39f4e1f0"),
        "mdToken:             " + token,
        "Module:              " + MODULE,
        "IsJitted:            yes",
    ]
    if current_addr:
        rows.append("Current CodeAddr:     " + RIP_FW)
    if history:
        rows.extend([
            "Version History:",
            "  ILCodeVersion:      0000000000000000",
            "  ReJIT ID:           0",
            "  IL Addr:            0000000000000000",
            "     CodeAddr:           " + RIP_FW + "  (Unknown Tier)",
            "     NativeCodeVersion:  0000000000000000",
        ])
    return rows


class TestSos9Format(unittest.TestCase):
    """Real SOS9 print shapes: 16-digit token, Current CodeAddr, history, failed stops."""

    def _jit(self, dumpmd_rows, ip2md_md=MD_TEXT, failure_lines=(), instructions=None):
        rows = [prompt(M.MARKER_JIT_HIT), prompt("rip=" + RIP_FW)]
        if ip2md_md is not None:
            rows.append(prompt("MethodDesc:          " + ip2md_md))
            rows.append("Method Name:         FrameworkEntry.Initialize(IGroupedHostContract)")
        rows.extend(failure_lines)
        rows.extend(dumpmd_rows)
        rows.append(prompt("u @rip L0x40"))
        for address, code, mnemonic in (jit_instructions() if instructions is None else instructions):
            rows.append(address + " " + code + "      " + mnemonic)
        rows.append(prompt(M.MARKER_JIT_END))
        return transcript(rows)

    def _interp(self, token="000000000600000b", failure_lines=()):
        rows = [
            prompt(M.MARKER_INTERP_HIT),
            prompt(M.MARKER_INTERP_FRAME),
            prompt("rdx=" + FRAME),
            "r9=0000000000000000",
            prompt("rip=" + RIP_INTERP),
            prompt(M.MARKER_INTERP_STARTIP),
            prompt(START_IP),
            prompt(M.MARKER_INTERP_METHOD),
            prompt(INTERP_METHOD),
            prompt(M.MARKER_INTERP_METHODHND),
            prompt(MD_TEXT),
            prompt(M.MARKER_INTERP_CODESIZE),
            prompt("0000001c"),
            prompt(M.MARKER_INTERP_INTERPCODE),
            prompt(START_IP),
            prompt(M.MARKER_INTERP_DUMPMD),
        ]
        rows.extend(failure_lines)
        rows.extend([
            prompt("Method Name:         AuthorEntry.Run(IGroupedHostContract, Int32)"),
            prompt("mdToken:             " + token),
            "Module:              " + MODULE,
            prompt(M.MARKER_INTERP_IRSTART),
            prompt(IR_START),
            prompt(M.MARKER_INTERP_END),
        ])
        return transcript(rows)

    def test_zero_extended_token_and_current_code_addr(self):
        event = M.parse_jit_capture(self._jit(sos9_dumpmd_rows()), MD_VALUE)
        self.assertEqual(event["dac_token"], 0x06000003)
        self.assertEqual(event["stop_kind"], "jit-native")
        self.assertEqual(event["dac_native_code_addr"], event["pc"])
        self.assertTrue(event["native_body_bound_to_dac"])
        self.assertEqual(event["native_code_size"], 5 + 1 + 1)
        self.assertIsNone(event["diagnostic_error"])

    def test_version_history_code_addr_never_binds(self):
        event = M.parse_jit_capture(self._jit(sos9_dumpmd_rows(current_addr=False)), MD_VALUE)
        self.assertIsNone(event["dac_native_code_addr"])
        self.assertEqual(event["stop_kind"], "jit-native-partial")
        self.assertFalse(event["native_body_bound_to_dac"])
        self.assertIsNone(event["native_code_start"])
        self.assertEqual(event["observed_span_start"], event["pc"])

    def test_token_with_nonzero_upper_bits_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_jit_capture(self._jit(sos9_dumpmd_rows(token="0000000106000003")), MD_VALUE)
        self.assertIn("upper bits", str(ctx.exception))

    def test_token_outside_methoddef_table_is_rejected(self):
        with self.assertRaises(ValueError):
            M.parse_jit_capture(self._jit(sos9_dumpmd_rows(token="0000000002000003")), MD_VALUE)

    def test_missing_ip2md_methoddesc_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_jit_capture(self._jit(sos9_dumpmd_rows(), ip2md_md=None), MD_VALUE)
        self.assertIn("ip2md", str(ctx.exception))

    def test_unable_insert_breakpoint_reported_precisely(self):
        failure = [
            "Unable to insert breakpoint 0 at " + RIP_FW + ", Win32 error 0n998",
            "bp0 at " + RIP_FW + " failed",
            "WaitForEvent failed, Win32 error 0n998",
        ]
        with self.assertRaises(ValueError) as ctx:
            M.parse_jit_capture(self._jit(sos9_dumpmd_rows(), failure_lines=failure), MD_VALUE)
        message = str(ctx.exception)
        self.assertIn("breakpoint could not be inserted", message)
        self.assertIn("Win32 error 0n998", message)

    def test_waitforevent_failure_reported(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_jit_capture(
                self._jit(sos9_dumpmd_rows(), failure_lines=["WaitForEvent failed, Win32 error 0n998"]),
                MD_VALUE,
            )
        self.assertIn("WaitForEvent", str(ctx.exception))

    def test_failed_ip2md_reported_precisely(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_jit_capture(
                self._jit(sos9_dumpmd_rows(), ip2md_md=None,
                          failure_lines=["Failed to request MethodData, not in JIT code range"]),
                MD_VALUE,
            )
        self.assertIn("MethodData", str(ctx.exception))

    def test_interp_accepts_zero_extended_token(self):
        event = M.parse_interp_capture(self._interp(), M.parse_layout(layout_outputs()), MD_VALUE)
        self.assertEqual(event["dac_token"], 0x0600000b)
        self.assertEqual(event["stop_kind"], "interp-first-entry")

    def test_interp_rejects_token_upper_bits(self):
        with self.assertRaises(ValueError):
            M.parse_interp_capture(
                self._interp(token="000000010600000b"), M.parse_layout(layout_outputs()), MD_VALUE
            )

    def test_interp_failed_stop_never_reports_entry(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_interp_capture(
                self._interp(failure_lines=["WaitForEvent failed, Win32 error 0n998"]),
                M.parse_layout(layout_outputs()),
                MD_VALUE,
            )
        self.assertIn("WaitForEvent", str(ctx.exception))



class TestCodeProbe(unittest.TestCase):
    """Natural-code probe and hardware-arm helpers: observation only, never an event."""

    CODE = int(RIP_FW.replace(BT, ""), 16)

    def setUp(self):
        self.layout = M.parse_layout(layout_outputs())

    def _probe(self, token="0000000006000003", current=RIP_FW, history=True,
               interp_code="0000000000000000", module_lines=(), end=True):
        rows = [
            prompt(M.MARKER_CODE_PROBE_BEGIN),
            prompt("!dumpmd 0x1f839f50000"),
            "Method Name:         FrameworkEntry.Initialize(IGroupedHostContract)",
            "Class:               " + a64("000001f8", "39f4e0a0"),
            "MethodTable:         " + a64("000001f8", "39f4e1f0"),
            "mdToken:             " + token,
            "Module:              " + MODULE,
            "IsJitted:            yes",
        ]
        if current is not None:
            rows.append("Current CodeAddr:     " + current)
        if history:
            rows.extend([
                "Version History:",
                "  ILCodeVersion:      0000000000000000",
                "     CodeAddr:           " + RIP_FW + "  (Unknown Tier)",
                "     NativeCodeVersion:  0000000000000000",
            ])
        rows.extend([
            prompt(M.MARKER_CODE_PROBE_INTERPCODE),
            prompt(interp_code),
            prompt(M.MARKER_CODE_PROBE_MODULE),
        ])
        rows.extend(module_lines)
        if end:
            rows.append(prompt(M.MARKER_CODE_PROBE_END))
        return transcript(rows)

    def test_probe_commands_use_the_dynamic_interpreter_code_offset(self):
        commands = M.code_probe_commands(MD_VALUE, self.layout)
        self.assertIn("!dumpmd 0x1f839f50000", commands)
        self.assertIn(eval_u64("poi(0x1f839f50000+0x68)"), commands)
        self.assertIn("lm m clrinterpreter", commands)
        self.assertIn(".echo " + M.MARKER_CODE_PROBE_BEGIN, commands)
        self.assertIn(".echo " + M.MARKER_CODE_PROBE_END, commands)

    def test_probe_commands_follow_a_changed_layout(self):
        layout = dict(self.layout)
        layout["m_interp_code_off"] = 0x120
        self.assertIn(eval_u64("poi(0x1f839f50000+0x120)"), M.code_probe_commands(MD_VALUE, layout))

    def test_probe_commands_reject_bad_input(self):
        with self.assertRaises(ValueError):
            M.code_probe_commands(-1, self.layout)
        broken = dict(self.layout)
        del broken["m_interp_code_off"]
        with self.assertRaises(ValueError):
            M.code_probe_commands(MD_VALUE, broken)

    def test_probe_reports_current_code_addr_token_and_module(self):
        event = M.parse_code_probe(self._probe(), self.layout, MD_VALUE)
        self.assertEqual(event["probe_kind"], "code-probe")
        self.assertFalse(event["execution_evidence"])
        self.assertNotIn("stop_kind", event)
        self.assertEqual(event["md_value"], MD_VALUE)
        self.assertEqual(event["dac_token"], 0x06000003)
        self.assertEqual(event["dac_module"], int(MODULE.replace(BT, ""), 16))
        self.assertEqual(event["current_code_addr"], self.CODE)
        self.assertEqual(event["interpreter_code_state"], "null")
        self.assertIsNone(event["interpreter_code_addr"])

    def test_probe_never_uses_the_version_history_code_addr(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_code_probe(self._probe(current=None), self.layout, MD_VALUE)
        self.assertIn("Current CodeAddr", str(ctx.exception))

    def test_probe_rejects_null_and_poison_code_addr(self):
        for current in ("0000000000000000", "0000000000000001"):
            with self.assertRaises(ValueError):
                M.parse_code_probe(self._probe(current=current), self.layout, MD_VALUE)

    def test_probe_reports_interpreter_code_states(self):
        poison = M.parse_code_probe(self._probe(interp_code="0000000000000001"), self.layout, MD_VALUE)
        self.assertEqual(poison["interpreter_code_state"], "poison")
        self.assertIsNone(poison["interpreter_code_addr"])
        real = M.parse_code_probe(self._probe(interp_code=START_IP), self.layout, MD_VALUE)
        self.assertEqual(real["interpreter_code_state"], "set")
        self.assertEqual(real["interpreter_code_addr"], int(START_IP.replace(BT, ""), 16))

    def test_probe_rejects_unparsable_interpreter_code(self):
        with self.assertRaises(ValueError):
            M.parse_code_probe(self._probe(interp_code=""), self.layout, MD_VALUE)

    def test_probe_rejects_non_methoddef_token(self):
        with self.assertRaises(ValueError):
            M.parse_code_probe(self._probe(token="0000000002000003"), self.layout, MD_VALUE)

    def test_probe_requires_every_marker(self):
        with self.assertRaises(ValueError):
            M.parse_code_probe(self._probe(end=False), self.layout, MD_VALUE)

    def test_probe_keeps_interpreter_module_report(self):
        listing = a64("00007ff8", "12340000") + " " + a64("00007ff8", "12350000") + "   interpreter (deferred)"
        event = M.parse_code_probe(self._probe(module_lines=[listing]), self.layout, MD_VALUE)
        self.assertTrue(any("interpreter" in line for line in event["interpreter_module_lines"]))

    def test_inspection_commands_are_read_only(self):
        addr = "0x%x" % self.CODE
        commands = M.code_address_inspection_commands(self.CODE)
        self.assertIn("!ip2md " + addr, commands)
        self.assertIn("!address " + addr, commands)
        self.assertIn("!vprot " + addr, commands)
        self.assertIn("u " + addr + " L0x40", commands)
        for command in commands:
            head = command.split()[0]
            self.assertNotIn(head, ("bp", "ba", "bc", "bu", "e", "ed", "eq", "eb"))

    def test_hardware_arm_is_execute_only(self):
        addr = "0x%x" % self.CODE
        commands = M.hardware_execute_breakpoint_commands(self.CODE)
        self.assertEqual(commands, [
            ".echo " + M.MARKER_HW_ARM,
            "ba e 1 " + addr,
            ".echo " + M.MARKER_HW_ARMED,
        ])
        for command in commands:
            self.assertNotIn(command.split()[0], ("bp", "e", "ed", "eq", "eb", "f"))
        self.assertNotIn("0x0", " ".join(commands))

    def test_hardware_arm_rejects_bad_address(self):
        for bad in (0, 1, -1, True, "0x1000", 1 << 70, 0x800):
            with self.assertRaises(ValueError):
                M.hardware_execute_breakpoint_commands(bad)
            with self.assertRaises(ValueError):
                M.code_address_inspection_commands(bad)

    def test_interp_capture_queries_are_all_printf(self):
        commands = M.capture_interp_commands(self.layout)
        printf_lines = [c for c in commands if c.startswith(".printf ")]
        self.assertEqual(len(printf_lines), 6)
        self.assertEqual(sum(1 for c in printf_lines if '"%08x' in c), 1)
        self.assertEqual(sum(1 for c in printf_lines if '"%016I64x' in c), 5)

    def test_printf_queries_keep_a_literal_backslash_n(self):
        commands = (
            M.capture_interp_commands(self.layout)
            + M.code_probe_commands(MD_VALUE, self.layout)
            + M.layout_probe_commands()
        )
        printf_lines = [c for c in commands if c.startswith(".printf ")]
        self.assertEqual(len(printf_lines), 8)
        for command in printf_lines:
            self.assertIn(BS + 'n"', command)
            self.assertNotIn("\n", command)
            self.assertNotIn("\r", command)

    def test_no_generated_command_starts_with_a_bare_expression(self):
        layout = self.layout
        code = int(RIP_FW.replace(BT, ""), 16)
        commands = (
            M.bootstrap_commands("D:/example/runtime/layout", "C:/tools/sos/sos.dll")
            + M.layout_probe_commands()
            + M.framework_breakpoint_commands(MD_VALUE)
            + M.capture_jit_commands(MD_VALUE)
            + [M.interp_breakpoint_command(MD_VALUE, layout)]
            + M.capture_interp_commands(layout)
            + M.capture_interp_commands(layout, md=MD_VALUE)
            + M.code_probe_commands(MD_VALUE, layout)
            + M.code_address_inspection_commands(code)
            + M.hardware_execute_breakpoint_commands(code)
            + M.capture_compile_commands()
            + M.framework_compile_breakpoint_commands(MD_VALUE)
            + M.cleanup_commands()
        )
        for command in commands:
            head = command.split()[0]
            self.assertFalse(head.startswith("poi"), command)
            self.assertFalse(head.startswith("dwo"), command)
            self.assertNotIn(head, ("p", "pc", "pa", "pe", "t", "ta"), command)
            if "poi(" in command or "dwo(" in command:
                self.assertTrue(
                    head.startswith(".printf") or head.startswith("!") or head == "bp",
                    command,
                )

    def test_debugger_grammar_error_is_reported_precisely(self):
        error = "       ^ pass count must be preceeded by whitespace error in 'poi(0x1f839f50000+0x10)'"
        text = self._probe().replace(prompt("0000000000000000"), prompt(error))
        with self.assertRaises(ValueError) as ctx:
            M.parse_code_probe(text, self.layout, MD_VALUE)
        message = str(ctx.exception)
        self.assertIn("pass count", message)
        self.assertIn("step command", message)

    def test_interp_rejects_step_command_grammar_error(self):
        error = "       ^ pass count must be preceeded by whitespace error in 'poi(0x1f839f50000+0x10)'"
        text = interp_transcript().replace(START_IP, error, 1)
        with self.assertRaises(ValueError) as ctx:
            M.parse_interp_capture(text, self.layout, MD_VALUE)
        self.assertIn("pass count", str(ctx.exception))

    def test_new_commands_avoid_forbidden_forms(self):
        commands = (
            M.code_probe_commands(MD_VALUE, self.layout)
            + M.code_address_inspection_commands(self.CODE)
            + M.hardware_execute_breakpoint_commands(self.CODE)
        )
        joined = " ".join(commands)
        for forbidden in (".call", "PrepareMethod", "clr!", "*!", "sxe", "!name2ee", "!dumpdomain", "gc"):
            self.assertNotIn(forbidden, joined)
        for command in commands:
            self.assertTrue(command)
            self.assertNotIn("\n", command)
            self.assertNotIn("\r", command)



def compile_stop_transcript(rcx=MD_TEXT, rdx=RIP_FW, marker=True, symbol=True):
    """Natural compilation stop: notification symbol, ready marker, then the register capture."""
    rows = []
    if symbol:
        rows.extend([
            "Breakpoint 1 hit",
            "coreclr!DACNotifyCompilationFinished:",
            RIP_FW + " 48895c2420      mov     qword ptr [rsp+20h],rbx",
        ])
    if marker:
        rows.append(prompt(M.MARKER_COMPILE_READY))
    rows.extend([
        prompt(M.MARKER_COMPILE_BEGIN),
        prompt("r rcx"),
        "rcx=" + rcx,
        prompt("r rdx"),
        "rdx=" + rdx,
        prompt(M.MARKER_COMPILE_END),
    ])
    return transcript(rows)


class TestCompileStop(unittest.TestCase):
    """Natural-compilation notification helpers: observation only, never execution evidence."""

    def test_compile_breakpoint_targets_the_notification_site(self):
        commands = M.framework_compile_breakpoint_commands(MD_VALUE)
        self.assertEqual(commands, [
            'bp coreclr!DACNotifyCompilationFinished '
            '".if (@rcx==0x1f839f50000) { .echo WITNESS-COMPILE-READY } .else { gc }"'
        ])
        self.assertNotIn("&&", commands[0])
        self.assertNotIn("InterpExecMethod", commands[0])
        self.assertNotIn("!bpmd", commands[0])

    def test_compile_breakpoint_rejects_bad_md(self):
        for bad in (-1, True, "4096", 1 << 70, 0):
            with self.assertRaises(ValueError):
                M.framework_compile_breakpoint_commands(bad)

    def test_capture_compile_commands_shape(self):
        self.assertEqual(M.capture_compile_commands(), [
            ".echo " + M.MARKER_COMPILE_BEGIN,
            "r rcx",
            "r rdx",
            ".echo " + M.MARKER_COMPILE_END,
        ])

    def test_parse_compile_stop_returns_observed_values_only(self):
        event = M.parse_compile_stop(compile_stop_transcript(), MD_VALUE)
        self.assertEqual(event["probe_kind"], "compile-stop")
        self.assertFalse(event["execution_evidence"])
        self.assertNotIn("stop_kind", event)
        self.assertEqual(event["md_value"], MD_VALUE)
        self.assertEqual(event["compiled_md"], MD_VALUE)
        self.assertEqual(event["compiled_code"], int(RIP_FW.replace(BT, ""), 16))
        self.assertEqual(event["stop_symbol"], "coreclr!DACNotifyCompilationFinished")

    def test_parse_compile_stop_rejects_wrong_rcx(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_compile_stop(compile_stop_transcript(rcx=OTHER_MD_TEXT), MD_VALUE)
        self.assertIn("rcx", str(ctx.exception))

    def test_parse_compile_stop_rejects_null_or_poison_code(self):
        for rdx in ("0000000000000000", "0000000000000001"):
            with self.assertRaises(ValueError):
                M.parse_compile_stop(compile_stop_transcript(rdx=rdx), MD_VALUE)

    def test_parse_compile_stop_rejects_missing_symbol(self):
        with self.assertRaises(ValueError) as ctx:
            M.parse_compile_stop(compile_stop_transcript(symbol=False), MD_VALUE)
        self.assertIn("DACNotifyCompilationFinished", str(ctx.exception))

    def test_parse_compile_stop_rejects_missing_marker(self):
        with self.assertRaises(ValueError):
            M.parse_compile_stop(compile_stop_transcript(marker=False), MD_VALUE)

    def test_parse_compile_stop_rejects_echo_only(self):
        text = transcript([
            prompt('bp coreclr!DACNotifyCompilationFinished ".if (@rcx==0x1f839f50000) { .echo WITNESS-COMPILE-READY } .else { gc }"'),
            prompt(M.MARKER_COMPILE_BEGIN),
            prompt("r rcx"),
            "rcx=" + MD_TEXT,
            prompt("r rdx"),
            "rdx=" + RIP_FW,
            prompt(M.MARKER_COMPILE_END),
        ])
        with self.assertRaises(ValueError):
            M.parse_compile_stop(text, MD_VALUE)

    def test_numeric_expression_missing_is_reported_precisely(self):
        error = ("Numeric expression missing from '& @rdx!=0 && poi(poi(poi(@rdx+0x8)+0x0)+0x8)==0x1f839f50000) "
                 "{ .echo WITNESS-INTERP-HIT } .else { gc }'")
        text = interp_transcript().replace(START_IP, error, 1)
        layout = M.parse_layout(layout_outputs())
        with self.assertRaises(ValueError) as ctx:
            M.parse_interp_capture(text, layout, MD_VALUE)
        self.assertIn("MASM grammar", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
