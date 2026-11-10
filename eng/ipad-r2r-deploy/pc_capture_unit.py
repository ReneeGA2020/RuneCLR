#!/usr/bin/env python3
"""Offline unit fixtures for the portable PC capture arithmetic and gates.

The fixture region exposes only methods that the real LLDB SBMemoryRegionInfo
provides (IsMapped, IsReadable, IsExecutable, GetRegionBase, GetRegionEnd), so a
regression back to the nonexistent IsValid() fails here instead of only on a device.
"""
import sys
import types
from pathlib import Path

sys.modules.setdefault("lldb", types.SimpleNamespace())
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pc_capture as pc

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, condition, detail))
    print(("PASS " if condition else "FAIL ") + name + ((" " + detail) if not condition else ""))


class Region:
    """Mirror of the actual LLDB SBMemoryRegionInfo surface; no IsValid()."""

    def __init__(self, base=0x1000, end=0x2000, mapped=True, readable=True,
                 executable=True):
        self.base = base
        self.end = end
        self.mapped = mapped
        self.readable = readable
        self.executable = executable

    def IsMapped(self):
        return self.mapped

    def IsReadable(self):
        return self.readable

    def IsExecutable(self):
        return self.executable

    def GetRegionBase(self):
        return self.base

    def GetRegionEnd(self):
        return self.end


class DefaultRegion:
    """Shape of a fresh lldb.SBMemoryRegionInfo(): nothing mapped, empty range."""

    def IsMapped(self):
        return False

    def IsReadable(self):
        return False

    def IsExecutable(self):
        return False

    def GetRegionBase(self):
        return 0

    def GetRegionEnd(self):
        return 0


OWNER = "TrustedUpdate.A.r2r.dylib"
OWNER_UUID = "5537271B-CF18-361C-A722-357B01AC114B"

check("fixture-has-no-invented-isvalid", not hasattr(Region(), "IsValid"))

zero = pc.compute_expected_pc(0x1000, 0, 0x4050)
check("arithmetic-zero-text-vmaddr", zero == 0x5050, hex(zero))
nonzero = pc.compute_expected_pc(0x200000000, 0x100000000, 0x100004050)
check("arithmetic-nonzero-text-vmaddr", nonzero == 0x200004050, hex(nonzero))

check("owner-exact-basename", pc.owner_matches(
    "/private/var/containers/.../" + OWNER, "5537271bcf18361ca722357b01ac114b",
    OWNER, OWNER_UUID))
check("owner-reject-substring", not pc.owner_matches(
    "/tmp/prefix-" + OWNER + ".bak", "5537271bcf18361ca722357b01ac114b",
    OWNER, OWNER_UUID))
check("owner-reject-wrong-uuid", not pc.owner_matches(
    "/tmp/" + OWNER, "00000000000000000000000000000000", OWNER, OWNER_UUID))

check("region-inside-nonzero-addr", pc.region_ok(Region(0x100000000, 0x100001000), 0x100000abc))
check("region-inclusive-base", pc.region_ok(Region(0x1000, 0x2000), 0x1000))
check("region-exclusive-end", not pc.region_ok(Region(0x1000, 0x2000), 0x2000))
check("region-outside-range-exec", not pc.region_ok(Region(0x1000, 0x2000), 0x3000))
check("region-empty-range", not pc.region_ok(Region(0x1000, 0x1000), 0x1000))
check("region-not-readable", not pc.region_ok(Region(readable=False), 0x1800))
check("region-not-executable", not pc.region_ok(Region(executable=False), 0x1800))
check("region-unmapped", not pc.region_ok(Region(mapped=False), 0x1800))
check("region-fresh-lldb-object", not pc.region_ok(DefaultRegion(), 0x1800))
check("region-none", not pc.region_ok(None, 0x1800))

checks = pc.pc_checks(0x1000, 0x1000, "/tmp/" + OWNER, OWNER_UUID, OWNER, OWNER_UUID,
                      Region(0x1000, 0x2000))
check("checks-all-pass", all(checks.values()), repr(checks))
bad_module = pc.pc_checks(0x1000, 0x1000, "/tmp/Other.dylib", OWNER_UUID, OWNER,
                          OWNER_UUID, Region(0x1000, 0x2000))
check("checks-wrong-module", not bad_module["frame_module_exact"], repr(bad_module))
bad_range = pc.pc_checks(0x1000, 0x3000, "/tmp/" + OWNER, OWNER_UUID, OWNER,
                         OWNER_UUID, Region(0x1000, 0x2000))
check("checks-pc-outside-region", not bad_range["pc_in_executable_region"], repr(bad_range))
bad_region = pc.pc_checks(0x1000, 0x1000, "/tmp/" + OWNER, OWNER_UUID, OWNER,
                          OWNER_UUID, Region(0x1000, 0x2000, executable=False))
check("checks-nonexec-region", not bad_region["pc_in_executable_region"], repr(bad_region))
check("checks-missing-region", not pc.region_ok(None, 0x1000))

failed = [name for name, ok, _detail in RESULTS if not ok]
print("PC_CAPTURE_UNIT", "PASS" if not failed else "FAIL",
      "passed=" + str(sum(1 for _n, ok, _d in RESULTS if ok)),
      "total=" + str(len(RESULTS)), "failures=" + str(len(failed)))
raise SystemExit(0 if not failed else 1)
