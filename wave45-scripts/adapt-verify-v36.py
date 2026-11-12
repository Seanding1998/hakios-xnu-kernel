#!/usr/bin/env python3
"""One-shot: turn wave42's verify-udon-hakios-v35.py into wave45's verify-udon-hakios-v36.py."""
import io, os, sys

REPO = r"C:\Users\<host>\.zcode\workspace\9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7\hakios-phk110"
SRC = os.path.join(REPO, "wave42-scripts", "verify-udon-hakios-v35.py")
DST = os.path.join(REPO, "wave45-scripts", "verify-udon-hakios-v36.py")

s = io.open(SRC, encoding="utf-8").read()

subs = []

subs.append(('"""Wave 42 (v35) verification of udon-hakios-grafted-v35.img.',
             '"""Wave 45 (v36) verification of udon-hakios-grafted-v36.img.'))

subs.append((
"""  - the payload = the v33 bytes except loader.efi (the v35 build, sha pinned
    as-built: 5de055ea...) and ramdisk (the wave39 GL=test carrier c2780842):
    kernel = the wave37 GPU-first-light build (55a8d40f), cmdline = the v26/v33
    bytes (gpu=1), resident/kernel.ver/usb carried from v33 byte for byte;""",
"""  - the payload = the v35 bytes except kernel (the wave43 build 5b77b418 =
    the wave41 GPU fixes + the fuelgauge driver), ramdisk (the wave41 GL=test
    carrier 51a030c3 with the gl_test judge inside) and cmdline (the v35 text
    with ' fuelgauge=2' appended, 489 chars + NUL); loader.efi (the frozen
    5de055ea build), resident/kernel.ver/usb carried from v35 byte for byte;"""))

subs.append(("usage: verify-udon-hakios-v35.py IMG STOCK SHIM FD PAYLOAD_V35 PAYLOAD_V33 PAYLOAD_V26 ROOT_APFS",
              "usage: verify-udon-hakios-v36.py IMG STOCK SHIM FD PAYLOAD_V36 PAYLOAD_V35 PAYLOAD_V26 ROOT_APFS_C51A030C3"))
subs.append(("IMG, STOCK, SHIM, FD, PAYLOAD_V35, PAYLOAD_V33, PAYLOAD_V26, ROOT_APFS = sys.argv[1:9]",
              "IMG, STOCK, SHIM, FD, PAYLOAD_V36, PAYLOAD_V35, PAYLOAD_V26, ROOT_APFS = sys.argv[1:9]"))
subs.append(('payload = open(PAYLOAD_V35, "rb").read()', 'payload = open(PAYLOAD_V36, "rb").read()'))
subs.append(('payload_v33_bytes = payload_entries(payload_v33)\ne33b = payload_entries(payload_v33)',
              'payload_v33_bytes = payload_entries(payload_v26)\ne35b = payload_entries(payload_v35)'))
subs.append(('e35 = payload_entries(payload)\ne26 = payload_v26_bytes',
              'e36 = payload_entries(payload)\ne26 = payload_v26_bytes'))

subs.append((
'''check("kernel == the wave 37 GPU-first-light build (55a8d40f), byte-equal to the v33 payload entry",
      e35["kernel"] == e33b["kernel"] and sha(e35["kernel"]).startswith("55a8d40f"),
      f"sha256 {sha(e35['kernel'])[:16]}")''',
'''check("kernel == the wave 43 build (5b77b418: wave41 GPU fixes + the fuelgauge driver), != the v35 payload entry",
      e36["kernel"] != e35b["kernel"] and sha(e36["kernel"]).startswith("5b77b418"),
      f"sha256 {sha(e36['kernel'])[:16]}")'''))

subs.append(('''check("kernel carries the gen7 parameter layer (the a730 names, the chip id, the log lines)",
      all(s in e35["kernel"] for s in''',
             '''check("kernel carries the gen7 parameter layer (the a730 names, the chip id, the log lines)",
      all(s in e36["kernel"] for s in'''))
subs.append(('''check("kernel still carries the Wave 26 feeder (carried, not under test)",
      all(s in e35["kernel"] for s in''',
             '''check("kernel still carries the Wave 26 feeder (carried, not under test)",
      all(s in e36["kernel"] for s in'''))
subs.append(('''check("kernel carries the Mini display + surface drivers (carried, not under test)",
      all(s in e35["kernel"] for s in''',
             '''check("kernel carries the Mini display + surface drivers (carried, not under test)",
      all(s in e36["kernel"] for s in'''))

subs.append((
'''                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u"))''',
'''                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u"))
check("kernel carries the wave41 GPU fixes and the wave43 fuelgauge (same tree, one build)",
      all(s in e36["kernel"] for s in (b"the gauge answers", b"the PMIC arbiter is version",
                                       b"adreno_ddr_type", b"gras_nc_mode_cntl",
                                       b"fuelgauge_poll_us")))'''))

subs.append((
'''check("loader.efi is the v35 build (as-built sha pin; != the v33 carry)",
      e35["loader.efi"] != e33b["loader.efi"] and sha(e35["loader.efi"]).startswith("5de055ea"),
      f"{len(e35['loader.efi'])} B, sha {sha(e35['loader.efi'])[:16]}")''',
'''check("loader.efi is the frozen v35 build (as-built sha pin; byte-equal to the v35 payload entry)",
      e36["loader.efi"] == e35b["loader.efi"] and sha(e36["loader.efi"]).startswith("5de055ea")
      and len(e36["loader.efi"]) == 90112,
      f"{len(e36['loader.efi'])} B, sha {sha(e36['loader.efi'])[:16]}")'''))

subs.append(('''check("loader carries the kern.maxvnodes DT injection (the vnode cap's bypass)",
      b"kern.maxvnodes" in e35["loader.efi"])''',
             '''check("loader carries the kern.maxvnodes DT injection (the vnode cap's bypass)",
      b"kern.maxvnodes" in e36["loader.efi"])'''))
subs.append(('check("kernel.ver byte-equal to the v33 entry", e35["kernel.ver"] == e33b["kernel.ver"], f"{len(e35[\'kernel.ver\'])} B")',
             'check("kernel.ver byte-equal to the v35 entry", e36["kernel.ver"] == e35b["kernel.ver"], f"{len(e36[\'kernel.ver\'])} B")'))
subs.append(('check("resident entry byte-equal to the v33 entry", e35["resident"] == e33b["resident"], f"{len(e35[\'resident\'])} B")',
             'check("resident entry byte-equal to the v35 entry", e36["resident"] == e35b["resident"], f"{len(e36[\'resident\'])} B")'))
subs.append(('check("cmdline entry == the v33 entry (== the v26 bytes: gpu=1 alone)",\n      e35["cmdline"] == e33b["cmdline"] == e26["cmdline"], f"{len(e35[\'cmdline\'])} B")',
             'check("cmdline entry == the v35 payload\'s entry with \' fuelgauge=2\' appended before its NUL",\n      e36["cmdline"][:-1] == e35b["cmdline"][:-1] + b" fuelgauge=2" and e36["cmdline"].endswith(b"\\0"), f"{len(e36[\'cmdline\'])} B")'))
subs.append(('check("usb entry byte-equal to the v33 entry", e35["usb"] == e33b["usb"], repr(e35["usb"]))',
             'check("usb entry byte-equal to the v35 entry", e36["usb"] == e35b["usb"], repr(e36["usb"]))'))
subs.append(('check("usb entry says 1", e35["usb"] == b"1\\0", repr(e35["usb"]))',
             'check("usb entry says 1", e36["usb"] == b"1\\0", repr(e36["usb"]))'))

subs.append((
'''check("ramdisk is the wave39 GL=test carrier (c2780842), byte-equal to the passed root.apfs; != the v33 ramdisk",
      e35["ramdisk"] == root_apfs and sha(e35["ramdisk"]).startswith("c2780842") and e35["ramdisk"] != e33b["ramdisk"],
      f"sha256 {sha(e35['ramdisk'])[:16]}, {len(e35['ramdisk'])} B")''',
'''check("ramdisk is the wave41 GL=test carrier (51a030c3), byte-equal to the passed root.apfs; != the v35 ramdisk",
      e36["ramdisk"] == root_apfs and sha(e36["ramdisk"]).startswith("51a030c3") and e36["ramdisk"] != e35b["ramdisk"],
      f"sha256 {sha(e36['ramdisk'])[:16]}, {len(e36['ramdisk'])} B")'''))

subs.append(('b"gmu_gen70000.bin" in e35["ramdisk"] and b"a730_zap.mdt" in e35["ramdisk"])',
             'b"gmu_gen70000.bin" in e36["ramdisk"] and b"a730_zap.mdt" in e36["ramdisk"])'))
subs.append((
'''check("ramdisk carries the GL first-frame kit (gl_test + u2f_test + libOSMesa, the wave39 carrier's content)",
      all(s in e35["ramdisk"] for s in (b"gl_test", b"u2f_test", b"libOSMesa")))
check("ramdisk is an 8,089,600 B APFS container (NXSB @+32)",
      len(e35["ramdisk"]) == 8089600 and e35["ramdisk"][32:36] == b"NXSB")
check("resident is an APFS container (NXSB @+32)", e35["resident"][32:36] == b"NXSB")''',
'''check("ramdisk carries the GL first-frame kit (gl_test + u2f_test + libOSMesa, the wave41 carrier's content)",
      all(s in e36["ramdisk"] for s in (b"gl_test", b"u2f_test", b"libOSMesa")))
check("ramdisk carries the wave41 judge lines (the real gl_test verifier strings)",
      all(s in e36["ramdisk"] for s in (b"READBACK_PASS", b"PRESENT_CALL_OK", b"GL_ERROR_FAIL")))
check("ramdisk is an 8,089,600 B APFS container (NXSB @+32)",
      len(e36["ramdisk"]) == 8089600 and e36["ramdisk"][32:36] == b"NXSB")
check("resident is an APFS container (NXSB @+32)", e36["resident"][32:36] == b"NXSB")'''))

subs.append((
'''check("cmdline == the v26 AND the v33 payload's cmdline entry byte for byte (gpu=1 carried, no probe args)",
      g[cmd_off:cmd_off + cmd_sz] == payload_v26_bytes["cmdline"] == payload_v33_bytes["cmdline"])''',
'''check("cmdline = the v35 text byte for byte with ' fuelgauge=2' appended before the NUL",
      g[cmd_off:cmd_off + cmd_sz] == e35b["cmdline"] and
      g[cmd_off:cmd_off + cmd_sz - 1] == e35b["cmdline"][:-1] + b" fuelgauge=2")'''))

subs.append((
'''check("cmdline is 477 chars (combined budget 110+477=587/607: no truncation)", len(cmd) == 477)''',
'''check("cmdline is 489 chars (combined budget 110+489=599/607: no truncation)", len(cmd) == 489)
check("cmdline carries fuelgauge=2 exactly once, right after gpu=1",
      cmd.count("fuelgauge=2") == 1 and cmd.index("fuelgauge=2") == cmd.index("gpu=1") + len("gpu=1") + 1)'''))

subs.append(('ldr = e35["loader.efi"]', 'ldr = e36["loader.efi"]'))
subs.append(('[loader (the GEN-1..4 fix chain on the wave42 root fix, v35 re-baseline)]',
             '[loader (the GEN-1..4 fix chain on the wave42 root fix; the frozen v35 build, unchanged)]'))

for old, new in subs:
    if old not in s:
        sys.exit("MISSING ANCHOR: %r" % old[:90])
    if s.count(old) != 1:
        sys.exit("ANCHOR NOT UNIQUE (%d): %r" % (s.count(old), old[:90]))
    s = s.replace(old, new)

io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print("verify-udon-hakios-v36.py written with %d substitutions" % len(subs))
