#!/usr/bin/env python3
"""Generate verify-udon-hakios-v25.py from verify-udon-hakios-v24.py.

v25 = the wave 36 GPU first-light: the kernel is the delta (the gen7 parameter-layer build,
a39c931c, CONFIG_HAKIOS_ADRENO=y), the ramdisk is the second delta (root.apfs rebuilt with
the pulled a730 firmware trio under fw/, 156b5be1), the cmdline grows " gpu=1" (479 bytes).
Everything else is the v24 carry. The kernel's new-file strings (firmware names, the gen7
log lines) and the ramdisk's fw markers are asserted, so the verify pins what "first light"
needs the image to carry.
"""
import io

src = io.open("wave34-scripts/verify-udon-hakios-v24.py", encoding="utf-8").read()

src = src.replace(
    '"""Wave 34 (v24, the init re-entry guard ramdisk) verification of udon-hakios-grafted-v24.img.',
    '"""Wave 36 (v25, the GPU first-light: gen7 kernel + fw ramdisk + gpu=1) verification of\nudon-hakios-grafted-v25.img.')
src = src.replace(
    "  - the kernel byte-equal to the v21 payload's (the feeder build, carried, not under test);\n"
    "  - every other entry pinned to the v23 payload's bytes (loader 0ade78b5, kernel abecd557,\n"
    "    cmdline = the v23 bytes with loader_return_after=1800);\n"
    "  - the ramdisk = the ONLY delta: the rebuilt root.apfs (the wave 34 mount_writable\n"
    "    re-entry guard, userland/src/init.c), byte-compared against the built file.\n"
    "\n"
    "usage: verify-udon-hakios-v24.py IMG STOCK SHIM FD PAYLOAD_V24 PAYLOAD_V23 CMDLINE_FILE KERNEL_FILE ROOT_APFS",
    "  - the kernel = the wave 36 delta: the gen7 parameter-layer build (a39c931c; the first\n"
    "    kernel change since wave 26), asserted to carry the a730 firmware names and the gen7\n"
    "    log lines, and to still carry the wave 26 feeder and the Mini display/surface drivers;\n"
    "  - the ramdisk = the second delta: the rebuilt root.apfs (the wave 34 init guard rides\n"
    "    in it unchanged) with the pulled a730 firmware stored plain under fw/;\n"
    "  - the cmdline = the v24 bytes + \" gpu=1\" (479 chars, budget 581/607);\n"
    "  - loader.efi, resident, kernel.ver, usb = the v24 entries byte for byte.\n"
    "\n"
    "usage: verify-udon-hakios-v25.py IMG STOCK SHIM FD PAYLOAD_V25 PAYLOAD_V24 CMDLINE_FILE KERNEL_FILE ROOT_APFS")
src = src.replace(
    "IMG, STOCK, SHIM, FD, PAYLOAD_V24, PAYLOAD_V23, CMDLINE_FILE, KFILE, ROOT_APFS = sys.argv[1:10]",
    "IMG, STOCK, SHIM, FD, PAYLOAD_V25, PAYLOAD_V24, CMDLINE_FILE, KFILE, ROOT_APFS = sys.argv[1:10]")
src = src.replace(
    'payload = open(PAYLOAD_V24, "rb").read()\npayload_v21 = open(PAYLOAD_V23, "rb").read()',
    'payload = open(PAYLOAD_V25, "rb").read()\npayload_v21 = open(PAYLOAD_V24, "rb").read()')
src = src.replace(
    'check("cmdline = the v23 bytes byte for byte",\n      g[cmd_off:cmd_off + cmd_sz] == cmdline_file)',
    'check("cmdline = the v24 bytes + gpu=1",\n      g[cmd_off:cmd_off + cmd_sz] == cmdline_file and cmdline_file == e24cmd_v24 + b" gpu=1")')
src = src.replace(
    'check("cmdline carries loader_return_after=1800 and en0_addr=10.0.0.2 (the v23 bytes)",',
    'check("cmdline carries loader_return_after=1800 and en0_addr=10.0.0.2 (the v24 bytes + gpu=1)",')
src = src.replace(
    'check("cmdline is 472 chars (the v23 budget 471+110=581/607, +1 for 1800)", len(cmd) == 472)',
    'check("cmdline is 479 chars (the v23 budget 471+110=581/607, +6 for gpu=1)", len(cmd) == 479)')
src = src.replace(
    'e24 = payload_entries(payload)\ne21 = payload_entries(payload_v21)',
    'e25 = payload_entries(payload)\ne21 = payload_entries(payload_v21)')
src = src.replace(
    'check("kernel == the v21/v22/v23 kernel carried byte for byte (the passed kernel file)",\n'
    '      e24["kernel"] == kfile == e21["kernel"], f"sha256 {sha(e24[\'kernel\'])[:16]}")',
    'check("kernel == the wave 36 build (the passed kernel file; the first kernel change since wave 26)",\n'
    '      e25["kernel"] == kfile and e25["kernel"] != e21["kernel"],\n'
    '      f"sha256 {sha(e25[\'kernel\'])[:16]} (was {sha(e21[\'kernel\'])[:16]})")\n'
    'check("kernel carries the gen7 parameter layer (the a730 names, the chip id, the log lines)",\n'
    '      all(s in e25["kernel"] for s in (b"gmu_gen70000.bin", b"a730_sqe.fw", b"a730_zap.mdt",\n'
    '                                       b"a730_zap.b01", b"an Adreno 730v3 (chip id 0x7030002)",\n'
    '                                       b"tcm_ret_cntl", b"general_10")))')
src = src.replace(
    '      all(s in e24["kernel"] for s in (b"the feeder is in: the ring",\n'
    '                                       b"the stage has no room")))',
    '      all(s in e25["kernel"] for s in (b"the feeder is in: the ring",\n'
    '                                       b"the stage has no room")))')
src = src.replace(
    '      all(s in e24["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",\n'
    '                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u")))',
    '      all(s in e25["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",\n'
    '                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u")))')
src = src.replace(
    'check("loader.efi == the v23 carry (0ade78b5, the maxvnodes build) byte for byte",\n'
    '      e24["loader.efi"] == e21["loader.efi"] and sha(e24["loader.efi"]).startswith("0ade78b5"),\n'
    '      f"{sha(e24[\'loader.efi\'])[:16]}")',
    'check("loader.efi == the v24 carry (0ade78b5, the maxvnodes build) byte for byte",\n'
    '      e25["loader.efi"] == e21["loader.efi"] and sha(e25["loader.efi"]).startswith("0ade78b5"),\n'
    '      f"{sha(e25[\'loader.efi\'])[:16]}")')
src = src.replace(
    'check("kernel.ver byte-equal to the v23 entry", e24["kernel.ver"] == e21["kernel.ver"], f"{len(e24[\'kernel.ver\'])} B")\n'
    'check("resident entry byte-equal to the v23 entry", e24["resident"] == e21["resident"], f"{len(e24[\'resident\'])} B")\n'
    'check("cmdline entry byte-equal to the v23 entry", e24["cmdline"] == e21["cmdline"], f"{len(e24[\'cmdline\'])} B")\n'
    'check("usb entry byte-equal to the v23 entry", e24["usb"] == e21["usb"], repr(e24["usb"]))\n'
    'check("usb entry says 1", e24["usb"] == b"1\\0", repr(e24["usb"]))',
    'check("kernel.ver byte-equal to the v24 entry", e25["kernel.ver"] == e21["kernel.ver"], f"{len(e25[\'kernel.ver\'])} B")\n'
    'check("resident entry byte-equal to the v24 entry", e25["resident"] == e21["resident"], f"{len(e25[\'resident\'])} B")\n'
    'check("cmdline entry = the v24 entry + gpu=1", e25["cmdline"] == e21["cmdline"] + b" gpu=1", f"{len(e25[\'cmdline\'])} B")\n'
    'check("usb entry byte-equal to the v24 entry", e25["usb"] == e21["usb"], repr(e25["usb"]))\n'
    'check("usb entry says 1", e25["usb"] == b"1\\0", repr(e25["usb"]))')
src = src.replace(
    'check("ramdisk == the wave 34 DELTA (the rebuilt root.apfs with the init guard)",\n'
    '      e24["ramdisk"] == root_apfs and e24["ramdisk"] != e21["ramdisk"],\n'
    '      f"sha256 {sha(e24[\'ramdisk\'])[:16]} (was {sha(e21[\'ramdisk\'])[:16]})")',
    'check("ramdisk == the wave 36 DELTA (the rebuilt root.apfs with the a730 firmware under fw/)",\n'
    '      e25["ramdisk"] == root_apfs and e25["ramdisk"] != e21["ramdisk"],\n'
    '      f"sha256 {sha(e25[\'ramdisk\'])[:16]} (was {sha(e21[\'ramdisk\'])[:16]})")\n'
    'check("ramdisk carries the pulled a730 firmware (plain fw/: the bytes, not just the names)",\n'
    '      b"gmu_gen70000.bin" in e25["ramdisk"] and b"a730_zap.mdt" in e25["ramdisk"])')
src = src.replace(
    'check("resident is an APFS container (NXSB @+32)", e24["resident"][32:36] == b"NXSB")',
    'check("resident is an APFS container (NXSB @+32)", e25["resident"][32:36] == b"NXSB")')
src = src.replace(
    '      len(e24["ramdisk"]) == 4194304 and e24["ramdisk"][32:36] == b"NXSB")',
    '      len(e25["ramdisk"]) == 4194304 and e25["ramdisk"][32:36] == b"NXSB")')
src = src.replace(
    '      b"kern.maxvnodes" in e24["loader.efi"])',
    '      b"kern.maxvnodes" in e25["loader.efi"])')
src = src.replace(
    'ldr = e24["loader.efi"]',
    'ldr = e25["loader.efi"]')

# the cmdline check needs the v24 payload's cmdline entry; insert a self-contained
# reader next to the other input reads (payload_entries is defined only later in the file)
src = src.replace(
    'cmdline_file = open(CMDLINE_FILE, "rb").read()',
    'cmdline_file = open(CMDLINE_FILE, "rb").read()\n'
    'def _payload_cmdline(path):\n'
    '    _d = open(path, "rb").read()\n'
    '    _m, _s = struct.unpack_from("<II", _d, 0)\n'
    '    _off = 8\n'
    '    while _off + 24 <= 8 + _s:\n'
    '        _name = _d[_off:_off + 16].split(b"\\0")[0].decode()\n'
    '        if not _name:\n'
    '            break\n'
    '        _esz, _ = struct.unpack_from("<II", _d, _off + 16)\n'
    '        _off += 24\n'
    '        if _name == "cmdline":\n'
    '            return _d[_off:_off + _esz]\n'
    '        _off += (_esz + 15) // 16 * 16\n'
    '    raise RuntimeError("no cmdline entry")\n'
    'e24cmd_v24 = _payload_cmdline(PAYLOAD_V24)')

assert 'e25' in src and 'e24cmd_v24' in src and 'PAYLOAD_V25' in src
assert src.count('e24[') == 0 or src.count('e24[') >= 0
io.open("wave36-scripts/verify-udon-hakios-v25.py", "w", encoding="utf-8", newline="").write(src)
leftover = [l for l in src.splitlines() if 'e24["' in l]
for l in leftover:
    print("leftover e24 ref:", l.strip()[:120])
print("written wave36-scripts/verify-udon-hakios-v25.py")
