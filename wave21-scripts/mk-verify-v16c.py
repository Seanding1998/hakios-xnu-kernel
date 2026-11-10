#!/usr/bin/env python3
"""One-shot generator: adapt verify-udon-hakios-v16b.py into verify-udon-hakios-v16c.py."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "verify-udon-hakios-v16b.py"), encoding="utf-8").read()

src = src.replace("v16b.img (the boot-window-only bring-up)", "v16c.img (the boot-window-only bring-up + DWC3 wake)")
src = src.replace("PAYLOAD_V16B", "PAYLOAD_V16C")
src = src.replace("payload_v16b", "payload_v16c")
src = src.replace("e16b", "e16c")
src = src.replace("v16b file bytes", "v16c file bytes")
src = src.replace("udon-hakios-grafted-v16b.img", "udon-hakios-grafted-v16c.img")
src = src.replace('sha(e16c["loader.efi"]).startswith("6c7fdb62") and e16c["loader.efi"] != e16["loader.efi"],',
                  'sha(e16c["loader.efi"]).startswith("ee8204e8") and e16c["loader.efi"] != e16["loader.efi"],')
src = src.replace("the v16b boot-window-only build (correct PAYLOAD_BASE), not v16/broken-v16b",
                  "the v16c DWC3-wake build, not v16b/broken-v16b/v16")

old_pin = '''ldr = e16c["loader.efi"]
_off = struct.unpack_from("<I", ldr, 0x3C)[0]
_epi = struct.unpack_from("<I", ldr, _off + 24 + 16)[0]
check("loader entry at RVA 0x2140", _epi == 0x2140, hex(_epi))
_sect = _off + 24 + struct.unpack_from("<H", ldr, _off + 20)[0]
_nsec = struct.unpack_from("<H", ldr, _off + 6)[0]
_tva = _tpraw = None
for _i in range(_nsec):
    _s = ldr[_sect + 40*_i: _sect + 40*_i + 40]
    if _s[:5] == b".text":
        _tvs, _tva, _trs, _tpraw = struct.unpack_from("<IIII", _s[8:24])
        break
check(".text section found", _tva is not None)
check("loader carries PAYLOAD_BASE=0xF4000000 at the entry parse "
      "(movz 0x52BE8008 @0x2198 after movk 0x72AA0AB3 @0x2190)",
      struct.unpack_from("<I", ldr, 0x2198 - _tva + _tpraw)[0] == 0x52BE8008 and
      struct.unpack_from("<I", ldr, 0x2190 - _tva + _tpraw)[0] == 0x72AA0AB3)'''
new_pin = '''ldr = e16c["loader.efi"]
check("loader carries the DWC3 wake print",
      b"usb: dwc3 woken (phy suspend off + core soft reset)" in ldr)
# F10 pin (layout-robust): the XNUP movk (0x72AA0AB3) must be followed 8 bytes later by
# movz w8, #0xF4000000 (0x52BE8008) -- the bare-build redwood default fails this.
_m = ldr.find(struct.pack("<I", 0x72AA0AB3))
check("loader entry parse carries PAYLOAD_BASE=0xF4000000 (XNUP movk + movz pin)",
      _m >= 0 and struct.unpack_from("<I", ldr, _m + 8)[0] == 0x52BE8008)'''
assert old_pin in src, "old pin block not found"
src = src.replace(old_pin, new_pin)
src = src.replace("usage: verify-udon-hakios-v16b.py", "usage: verify-udon-hakios-v16c.py")
src = src.replace('"""Wave 21.2 verification of udon-hakios-grafted-v16b.img',
                  '"""Wave 21.2 v16c verification of udon-hakios-grafted-v16c.img')
src = src.replace(" - the boot-window-only bring-up.\n", " - the boot-window-only bring-up + the DWC3 wake.\n")
src = src.replace("  - the loader CHANGES: the lazy retry retired",
                  "  - v16b' plus the DWC3 wake (SUSPHY off + GCTL.CSFTRST before the bring-up);\n  - the v16b' changes: the lazy retry retired")

out = os.path.join(HERE, "verify-udon-hakios-v16c.py")
open(out, "w", encoding="utf-8", newline="").write(src)
print("written", out)
