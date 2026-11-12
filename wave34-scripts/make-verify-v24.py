#!/usr/bin/env python3
"""Generate verify-udon-hakios-v24.py from verify-udon-hakios-v23.py.

v24 = the wave 34 init re-entry guard: the ONLY payload delta is the ramdisk
entry (root.apfs rebuilt with userland/src/init.c guarded). Everything else is
the v23 carry. The verify takes one extra argument: the built root.apfs file,
byte-compared against the payload's ramdisk entry."""
import re

src = open(r"wave26-scripts/verify-udon-hakios-v23.py", encoding="utf-8").read()

src = src.replace(
    "Wave 26 Round 3 (v23, the long-session cmdline) verification of udon-hakios-grafted-v23.img.",
    "Wave 34 (v24, the init re-entry guard ramdisk) verification of udon-hakios-grafted-v24.img.")
src = src.replace(
    "  - every other entry pinned to the v21 payload's bytes;\n"
    "  - the cmdline asserted as the v18 bytes (loader_return_after=180, en0_addr in, rec_* out).\n"
    "\n"
    "usage: verify-udon-hakios-v22.py IMG STOCK SHIM FD PAYLOAD_V22 PAYLOAD_V21 CMDLINE_FILE KERNEL_FILE",
    "  - every other entry pinned to the v23 payload's bytes (loader 0ade78b5, kernel abecd557,\n"
    "    cmdline = the v23 bytes with loader_return_after=1800);\n"
    "  - the ramdisk = the ONLY delta: the rebuilt root.apfs (the wave 34 mount_writable\n"
    "    re-entry guard, userland/src/init.c), byte-compared against the built file.\n"
    "\n"
    "usage: verify-udon-hakios-v24.py IMG STOCK SHIM FD PAYLOAD_V24 PAYLOAD_V23 CMDLINE_FILE KERNEL_FILE ROOT_APFS")
src = src.replace(
    'IMG, STOCK, SHIM, FD, PAYLOAD_V23, PAYLOAD_V22, CMDLINE_FILE, KFILE = sys.argv[1:9]',
    'IMG, STOCK, SHIM, FD, PAYLOAD_V24, PAYLOAD_V23, CMDLINE_FILE, KFILE, ROOT_APFS = sys.argv[1:10]')
src = src.replace(
    'payload = open(PAYLOAD_V23, "rb").read()\npayload_v21 = open(PAYLOAD_V22, "rb").read()',
    'payload = open(PAYLOAD_V24, "rb").read()\npayload_v21 = open(PAYLOAD_V23, "rb").read()\nroot_apfs = open(ROOT_APFS, "rb").read()')
src = src.replace(
    'cmdline_file = open(CMDLINE_FILE, "rb").read()',
    'cmdline_file = open(CMDLINE_FILE, "rb").read()')
src = src.replace(
    'check("cmdline = the v18 bytes with only loader_return_after 180->1800",',
    'check("cmdline = the v23 bytes byte for byte",')
src = src.replace(
    'check("cmdline carries loader_return_after=1800 and en0_addr=10.0.0.2",',
    'check("cmdline carries loader_return_after=1800 and en0_addr=10.0.0.2 (the v23 bytes)",')
src = src.replace(
    'check("cmdline is 472 chars (the v18 budget 471+110=581/607, +1 for 1800)", len(cmd) == 472)',
    'check("cmdline is 472 chars (the v23 budget 471+110=581/607, +1 for 1800)", len(cmd) == 472)')
src = src.replace(
    'e23 = payload_entries(payload)\ne21 = payload_entries(payload_v21)',
    'e24 = payload_entries(payload)\ne21 = payload_entries(payload_v21)')
src = src.replace(
    'check("kernel == the v21/v22 kernel carried byte for byte (the passed kernel file)",\n      e23["kernel"] == kfile == e21["kernel"], f"sha256 {sha(e23[\'kernel\'])[:16]}")',
    'check("kernel == the v21/v22/v23 kernel carried byte for byte (the passed kernel file)",\n      e24["kernel"] == kfile == e21["kernel"], f"sha256 {sha(e24[\'kernel\'])[:16]}")')
src = src.replace(
    '      all(s in e23["kernel"] for s in (b"the feeder is in: the ring",\n                                       b"the stage has no room")))',
    '      all(s in e24["kernel"] for s in (b"the feeder is in: the ring",\n                                       b"the stage has no room")))')
src = src.replace(
    '      all(s in e23["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",\n                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u")))',
    '      all(s in e24["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",\n                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u")))')
src = src.replace(
    'check("loader.efi == the v22 carry (0ade78b5, the maxvnodes build) byte for byte",\n      e23["loader.efi"] == e21["loader.efi"] and sha(e23["loader.efi"]).startswith("0ade78b5"),\n      f"{sha(e23[\'loader.efi\'])[:16]}")',
    'check("loader.efi == the v23 carry (0ade78b5, the maxvnodes build) byte for byte",\n      e24["loader.efi"] == e21["loader.efi"] and sha(e24["loader.efi"]).startswith("0ade78b5"),\n      f"{sha(e24[\'loader.efi\'])[:16]}")')
src = src.replace(
    'check("kernel.ver byte-equal to the v21 entry", e23["kernel.ver"] == e21["kernel.ver"], f"{len(e23[\'kernel.ver\'])} B")\n'
    'check("resident entry byte-equal to the v21 entry", e23["resident"] == e21["resident"], f"{len(e23[\'resident\'])} B")\n'
    'check("ramdisk entry byte-equal to the v21 entry", e23["ramdisk"] == e21["ramdisk"], f"{len(e23[\'ramdisk\'])} B")\n'
    'check("usb entry says 1", e23["usb"] == b"1\\0", repr(e23["usb"]))\n'
    'check("resident/ramdisk are APFS containers (NXSB @+32)",\n      e23["resident"][32:36] == b"NXSB" and e23["ramdisk"][32:36] == b"NXSB")',
    'check("kernel.ver byte-equal to the v23 entry", e24["kernel.ver"] == e21["kernel.ver"], f"{len(e24[\'kernel.ver\'])} B")\n'
    'check("resident entry byte-equal to the v23 entry", e24["resident"] == e21["resident"], f"{len(e24[\'resident\'])} B")\n'
    'check("cmdline entry byte-equal to the v23 entry", e24["cmdline"] == e21["cmdline"], f"{len(e24[\'cmdline\'])} B")\n'
    'check("usb entry byte-equal to the v23 entry", e24["usb"] == e21["usb"], repr(e24["usb"]))\n'
    'check("usb entry says 1", e24["usb"] == b"1\\0", repr(e24["usb"]))\n'
    'check("ramdisk == the wave 34 DELTA (the rebuilt root.apfs with the init guard)",\n      e24["ramdisk"] == root_apfs and e24["ramdisk"] != e21["ramdisk"],\n      f"sha256 {sha(e24[\'ramdisk\'])[:16]} (was {sha(e21[\'ramdisk\'])[:16]})")\n'
    'check("ramdisk is a 4 MB APFS container (NXSB @+32)",\n      len(e24["ramdisk"]) == 4194304 and e24["ramdisk"][32:36] == b"NXSB")\n'
    'check("resident is an APFS container (NXSB @+32)", e24["resident"][32:36] == b"NXSB")')
src = src.replace('e23["loader.efi"]', 'e24["loader.efi"]')  # the [loader] section's ldr

open(r"wave34-scripts/verify-udon-hakios-v24.py", "w", encoding="utf-8", newline="\n").write(src)
left = len(re.findall(r"e23\[", src))
print("written; remaining e23 references:", left)
