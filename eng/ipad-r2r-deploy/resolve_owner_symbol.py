#!/usr/bin/env python3
"""Resolve a managed method symbol and its file address from an actual signed Mach-O owner.

This is the offline source of truth for the maintained PC capture adapter. It does not
hardcode 0x4050: it parses LC_UUID, __TEXT, __TEXT,__managedcode and LC_SYMTAB from the
actual signed owner, then optionally confirms the LLDB-visible symbol/address.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def lldb_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_macho(path):
    data = Path(path).read_bytes()
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        raise SystemExit("owner is not a 64-bit Mach-O")
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    uuid = None
    text = None
    managed = None
    symbols = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x1B and size >= 24:
            uuid = data[off + 8:off + 24].hex()
        elif cmd == 0x19 and size >= 72:
            segname = data[off + 8:off + 24].split(b"\x00")[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            if segname == "__TEXT":
                text = {"vmaddr": vmaddr, "vmsize": vmsize, "fileoff": fileoff,
                        "filesize": filesize}
                nsects = struct.unpack_from("<I", data, off + 64)[0]
                sec_off = off + 72
                for _index in range(nsects):
                    sectname = data[sec_off:sec_off + 16].split(b"\x00")[0].decode(
                        "ascii", "replace")
                    if sectname == "__managedcode":
                        addr, sec_size, offset = struct.unpack_from(
                            "<QQI", data, sec_off + 32)
                        managed = {"name": sectname, "addr": addr, "size": sec_size,
                                   "offset": offset}
                    sec_off += 80
        elif cmd == 0x2 and size >= 24:
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", data, off + 8)
            for index in range(nsyms):
                n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from(
                    "<IBBhQ", data, symoff + index * 16)
                end = data.index(b"\x00", stroff + n_strx)
                name = data[stroff + n_strx:end].decode("ascii", "replace")
                symbols.append({"name": name, "value": n_value,
                                "section_index": n_sect, "type": n_type,
                                "external": bool(n_type & 1)})
        off += size
    if not uuid:
        raise SystemExit("LC_UUID missing")
    if not text:
        raise SystemExit("__TEXT segment missing")
    if not managed:
        raise SystemExit("__TEXT,__managedcode section missing")
    return data, uuid, text, managed, symbols


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("owner")
    parser.add_argument("--pattern", default=r"Business.*Execute")
    parser.add_argument("--symbol")
    parser.add_argument("--lldb-confirm", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    owner = Path(args.owner).resolve()
    data, uuid, text, managed, symbols = parse_macho(owner)
    regex = re.compile(args.pattern)
    candidates = [item for item in symbols
                  if regex.search(item["name"].lstrip("_"))
                  and managed["addr"] <= item["value"] < managed["addr"] + managed["size"]]
    if args.symbol:
        candidates = [item for item in candidates
                      if item["name"].lstrip("_") == args.symbol.lstrip("_")]
    if len(candidates) != 1:
        raise SystemExit("expected exactly one matching symbol, got: "
                         + repr([item["name"] for item in candidates]))
    item = candidates[0]
    if not (managed["addr"] <= item["value"] < managed["addr"] + managed["size"]):
        raise SystemExit("matched symbol is outside __managedcode")
    record = {
        "schema": "runeclr.ipados.r2r.owner-symbol.v1",
        "owner": str(owner),
        "sha256": sha256(owner),
        "uuid": uuid,
        "macho_symbol": item["name"],
        "symbol": item["name"].lstrip("_"),
        "file_address": item["value"],
        "managedcode": managed,
        "text": text,
        "arch": "arm64",
    }
    if args.lldb_confirm:
        command = ["lldb", "--batch",
                   "-o", "target create " + lldb_quote(owner),
                   "-o", "image lookup -rn " + lldb_quote(args.pattern)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        text_out = result.stdout + result.stderr
        matches = re.findall(r"Address: .*?\[0x([0-9a-fA-F]+)\]", text_out)
        quote = chr(96)
        summary = []
        for line in text_out.splitlines():
            line = line.strip()
            if line.startswith("Summary:"):
                parts = line.split(quote)
                if len(parts) >= 2:
                    summary = [parts[1]]
                break
        if not matches:
            raise SystemExit("LLDB did not resolve the owner symbol")
        record["lldb_confirmed"] = True
        record["lldb_address"] = int(matches[0], 16)
        record["lldb_symbol"] = summary[0] if summary else None
        if record["lldb_address"] != record["file_address"]:
            raise SystemExit("LLDB address does not match Mach-O file address")
        if record["lldb_symbol"] and record["lldb_symbol"].lstrip("_") != record["symbol"]:
            raise SystemExit("LLDB symbol spelling does not match")
    output = json.dumps(record, indent=2) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
