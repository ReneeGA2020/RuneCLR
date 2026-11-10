#!/usr/bin/env python3
"""Maintained LLDB PC capture adapter for a downloaded R2R owner.

Run inside LLDB from the deploy directory:
  PC_PID=<device pid> PC_HOST=<signed host executable> PC_OWNER=<owner basename>
  PC_METADATA=<owner-symbol.json> PC_DEVICE=<CoreDevice UUID> PC_OUT=<witness.json>
  lldb --batch -o 'script exec(compile(open("pc_capture.py").read(),
                                        "pc_capture.py", "exec"),
                               {"__name__": "__main__"})'

The symbol and VM address come from offline resolve_owner_symbol.py metadata, or from
the loaded owner module's LLDB symbol table. No universal 0x4050 constant is used.
"""
import json
import os
import time
import lldb


def lldb_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def normalized_uuid(value):
    return str(value or "").replace("-", "").lower()


def owner_matches(path, actual_uuid, owner, expected_uuid):
    if os.path.basename(str(path)) != os.path.basename(str(owner)):
        return False
    if expected_uuid and normalized_uuid(actual_uuid) != normalized_uuid(expected_uuid):
        return False
    return True


def compute_expected_pc(header_load, text_vmaddr, symbol_vmaddr):
    return int(header_load) - int(text_vmaddr or 0) + int(symbol_vmaddr)


def region_ok(region, pc):
    if region is None:
        return False
    try:
        if not (region.IsMapped() and region.IsReadable() and region.IsExecutable()):
            return False
        return int(region.GetRegionBase()) <= int(pc) < int(region.GetRegionEnd())
    except Exception:
        return False


def pc_checks(expected, actual, frame_path, frame_uuid, owner, owner_uuid, region):
    return {
        "pc_matches_expected": int(actual) == int(expected),
        "frame_module_exact": os.path.basename(str(frame_path))
                              == os.path.basename(str(owner)),
        "frame_uuid_matches": (not owner_uuid
                               or normalized_uuid(frame_uuid) == normalized_uuid(owner_uuid)),
        "pc_in_executable_region": region_ok(region, actual),
    }


def main():
    pid = int(os.environ["PC_PID"])
    host = os.environ["PC_HOST"]
    owner = os.environ["PC_OWNER"]
    device = os.environ.get("PC_DEVICE")
    if not device:
        raise SystemExit("PC_DEVICE is required")
    out = os.environ.get("PC_OUT", "pc-witness.json")
    metadata_path = os.environ.get("PC_METADATA")
    metadata = json.load(open(metadata_path)) if metadata_path else {}
    owner_uuid = normalized_uuid(metadata.get("uuid") or os.environ.get("PC_UUID", ""))
    symbol_name = metadata.get("symbol") or os.environ.get("PC_SYMBOL")
    symbol_vm = metadata.get("file_address")
    text_vmaddr = (metadata.get("text") or {}).get("vmaddr", 0)

    debugger = lldb.debugger
    debugger.SetAsync(False)
    debugger.HandleCommand("target create " + lldb_quote(host))
    debugger.HandleCommand("device select " + device)
    debugger.HandleCommand("device process attach -p %d" % pid)
    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    for _ in range(30):
        if process.GetState() == lldb.eStateStopped:
            break
        process.Stop()
        time.sleep(1)
    if process.GetState() != lldb.eStateStopped:
        raise SystemExit("target did not reach stopped state")

    debugger.HandleCommand("settings set target.process.stop-on-sharedlibrary-events true")
    module = None
    for _ in range(3000):
        process.Continue()
        state = process.GetState()
        if state != lldb.eStateStopped:
            if state in (lldb.eStateExited, lldb.eStateDetached):
                raise SystemExit("process ended before owner mapping")
            continue
        for item in target.module_iter():
            path = str(item.GetFileSpec().fullpath)
            if owner_matches(path, item.GetUUIDString(), owner, owner_uuid):
                module = item
                break
        if module is not None:
            break
    if module is None:
        raise SystemExit("owner module was not mapped")

    header_load = module.GetObjectFileHeaderAddress().GetLoadAddress(target)
    if header_load == lldb.LLDB_INVALID_ADDRESS:
        raise SystemExit("owner module load address unavailable")
    if symbol_vm is None:
        if not symbol_name:
            raise SystemExit("no symbol metadata and no PC_SYMBOL")
        symbol = module.FindSymbol(symbol_name)
        if not symbol.IsValid():
            symbol = module.FindSymbol("_" + symbol_name)
        if not symbol.IsValid():
            raise SystemExit("owner symbol not found in loaded module")
        symbol_name = symbol.GetName()
        symbol_vm = symbol.GetStartAddress().GetFileAddress()
    expected_pc = compute_expected_pc(header_load, text_vmaddr, symbol_vm)

    symbol = module.FindSymbol(symbol_name) if symbol_name else None
    if symbol is not None and symbol.IsValid():
        symbol_load = symbol.GetStartAddress().GetLoadAddress(target)
        if symbol_load != lldb.LLDB_INVALID_ADDRESS:
            expected_pc = symbol_load

    breakpoint = target.BreakpointCreateByAddress(expected_pc)
    process.Continue()
    if process.GetState() != lldb.eStateStopped:
        raise SystemExit("address breakpoint did not stop the process")
    thread = process.GetSelectedThread()
    if thread.GetNumFrames() == 0:
        raise SystemExit("no stopped frame")
    frame = thread.GetFrameAtIndex(0)
    frame_module = frame.GetModule()
    if not frame_module.IsValid():
        raise SystemExit("stopped frame has no module")
    frame_path = str(frame_module.GetFileSpec().fullpath)
    frame_uuid = frame_module.GetUUIDString()
    actual_pc = frame.GetPC()
    region = lldb.SBMemoryRegionInfo()
    region_error = process.GetMemoryRegionInfo(actual_pc, region)
    region_error_text = None
    region_value = None
    if region_error.Success():
        try:
            region_value = {
                "base": region.GetRegionBase(),
                "end": region.GetRegionEnd(),
                "mapped": region.IsMapped(),
                "readable": region.IsReadable(),
                "executable": region.IsExecutable(),
            }
        except Exception as error:
            region_error_text = repr(error)
    else:
        region_error_text = "GetMemoryRegionInfo failed for pc 0x%x" % int(actual_pc)
    checks = pc_checks(expected_pc, actual_pc, frame_path, frame_uuid,
                       owner, owner_uuid, region)
    stop_reason = thread.GetStopReason()
    try:
        stop_description = thread.GetStopDescription(256)
    except Exception:
        stop_description = ""
    witness = {
        "schema": "runeclr.ipados.r2r.pc-witness.v1",
        "pid": pid,
        "owner": str(module.GetFileSpec().fullpath),
        "owner_uuid": module.GetUUIDString(),
        "owner_base": header_load,
        "text_vmaddr": int(text_vmaddr or 0),
        "symbol_vmaddr": int(symbol_vm),
        "symbol": symbol_name,
        "expected_pc": expected_pc,
        "actual_pc": actual_pc,
        "frame_module": frame_path,
        "frame_module_uuid": frame_uuid,
        "stop_reason": stop_reason,
        "stop_description": stop_description,
        "executable_region": region_value,
        "region_error": region_error_text,
        "checks": checks,
        "ok": all(checks.values()),
        "text": metadata.get("text"),
        "managedcode": metadata.get("managedcode"),
        "frames": [
            {"pc": thread.GetFrameAtIndex(i).GetPC(),
             "symbol": thread.GetFrameAtIndex(i).GetFunctionName(),
             "module": (thread.GetFrameAtIndex(i).GetModule().GetFileSpec().fullpath
                        if thread.GetFrameAtIndex(i).GetModule().IsValid() else None)}
            for i in range(min(12, thread.GetNumFrames()))
        ],
    }
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(witness, stream, indent=2)
        stream.write("\n")
    print(json.dumps(witness, indent=2), flush=True)
    if not witness["ok"]:
        raise SystemExit("PC witness checks failed")

    breakpoint.SetEnabled(False)
    process.Continue()
    for _ in range(30):
        if process.GetState() in (lldb.eStateExited, lldb.eStateDetached):
            break
        time.sleep(1)
    witness["process_state"] = process.GetState()
    witness["process_exit_status"] = process.GetExitStatus()
    if process.GetExitStatus() != 0:
        witness["ok"] = False
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(witness, stream, indent=2)
        stream.write("\n")
    print("FINAL_PROCESS_STATE", process.GetState(), "EXIT", process.GetExitStatus(), flush=True)
    if not witness["ok"]:
        raise SystemExit("process did not exit 0 after PC capture")


if __name__ == "__main__":
    main()
