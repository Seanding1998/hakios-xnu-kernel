#!/usr/bin/env python3
"""One-shot adapter: verify-udon-hakios-v34.py = the wave38 verify re-anchored on the v33
payload entries (the re-baseline merge). Run once; refuses a second run (assertions MISS)."""
p = "/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave38-scripts/verify-udon-hakios-v34.py"
s = open(p, encoding="utf-8").read()

def sub(old, new):
    global s
    n = s.count(old)
    assert n == 1, f"not unique ({n}x): {old[:80]!r}"
    s = s.replace(old, new)

sub('''"""Wave 38 (wave38- prefix; the version number is confirmed with the main agent before any
flash) verification of udon-hakios-grafted-wave38.img.

Shape identical to the v27 verifies, with:
  - the payload = the v27 bytes except loader.efi (the wave38 USB-pair self-heal build,
    sha pinned as-built: 3f595c52...) and the cmdline (re-sourced from v26: 478 B, gpu=1
    carried, wave37's adreno_only=1 probe diagnostic NOT carried);
  - kernel / ramdisk / resident / kernel.ver / usb byte-equal to BOTH the v26 and the v27
    payload entries (no external kernel file needed);''',
'''"""Wave 38 (v34; the version number assigned by the main agent, v27-v33 are wave37's)
verification of udon-hakios-grafted-v34.img -- the re-baselined merge.

Shape identical to the wave38 verifies, with:
  - the payload = the v33 bytes except loader.efi (the wave38 USB-pair self-heal build,
    sha pinned as-built: 3f595c52...): kernel = the wave37 GPU-first-light build
    (55a8d40f), cmdline = the v26/v33 bytes (gpu=1), ramdisk/resident/kernel.ver/usb
    carried from v33 byte for byte;''')

sub("usage: verify-udon-hakios-wave38.py IMG STOCK SHIM FD PAYLOAD_W38 PAYLOAD_V27 PAYLOAD_V26 ROOT_APFS",
    "usage: verify-udon-hakios-v34.py IMG STOCK SHIM FD PAYLOAD_V34 PAYLOAD_V33 PAYLOAD_V26 ROOT_APFS")

sub("IMG, STOCK, SHIM, FD, PAYLOAD_W38, PAYLOAD_V27, PAYLOAD_V26, ROOT_APFS = sys.argv[1:9]",
    "IMG, STOCK, SHIM, FD, PAYLOAD_V34, PAYLOAD_V33, PAYLOAD_V26, ROOT_APFS = sys.argv[1:9]")

sub('payload = open(PAYLOAD_W38, "rb").read()\npayload_v27 = open(PAYLOAD_V27, "rb").read()',
    'payload = open(PAYLOAD_V34, "rb").read()\npayload_v33 = open(PAYLOAD_V33, "rb").read()')

sub('e27 = payload_entries(payload_v27)', 'e33b = payload_entries(payload_v33)')

sub('e38 = payload_entries(payload)\ne26 = payload_v26_bytes',
    'e34 = payload_entries(payload)\ne26 = payload_v26_bytes')

sub('''check("kernel == the wave 36 build, byte-equal to BOTH the v26 and the v27 payload entries",
      e38["kernel"] == e27["kernel"] == e26["kernel"],
      f"sha256 {sha(e38['kernel'])[:16]}")''',
'''check("kernel == the wave 37 GPU-first-light build (55a8d40f), byte-equal to the v33 payload entry",
      e34["kernel"] == e33b["kernel"] and sha(e34["kernel"]).startswith("55a8d40f"),
      f"sha256 {sha(e34['kernel'])[:16]}")''')

s = s.replace("e38[", "e34[")

sub('''check("kernel.ver byte-equal to the v26/v27 entries", e34["kernel.ver"] == e27["kernel.ver"] == e26["kernel.ver"], f"{len(e34['kernel.ver'])} B")
check("resident entry byte-equal to the v26/v27 entries", e34["resident"] == e27["resident"] == e26["resident"], f"{len(e34['resident'])} B")
check("cmdline entry == the v26 entry (re-sourced)", e34["cmdline"] == e26["cmdline"], f"{len(e34['cmdline'])} B")
check("usb entry byte-equal to the v26/v27 entries", e34["usb"] == e27["usb"] == e26["usb"], repr(e34["usb"]))
check("usb entry says 1", e34["usb"] == b"1\\0", repr(e34["usb"]))
check("ramdisk byte-equal to the v26/v27 entries (unchanged)",
      e34["ramdisk"] == root_apfs == e27["ramdisk"] == e26["ramdisk"],
      f"sha256 {sha(e34['ramdisk'])[:16]}")''',
'''check("kernel.ver byte-equal to the v33 entry", e34["kernel.ver"] == e33b["kernel.ver"], f"{len(e34['kernel.ver'])} B")
check("resident entry byte-equal to the v33 entry", e34["resident"] == e33b["resident"], f"{len(e34['resident'])} B")
check("cmdline entry == the v33 entry (== the v26 bytes: gpu=1 alone)",
      e34["cmdline"] == e33b["cmdline"] == e26["cmdline"], f"{len(e34['cmdline'])} B")
check("usb entry byte-equal to the v33 entry", e34["usb"] == e33b["usb"], repr(e34["usb"]))
check("usb entry says 1", e34["usb"] == b"1\\0", repr(e34["usb"]))
check("ramdisk byte-equal to the v33 entry (unchanged)",
      e34["ramdisk"] == root_apfs == e33b["ramdisk"],
      f"sha256 {sha(e34['ramdisk'])[:16]}")''')

sub('check("loader.efi is the wave38 self-heal build (as-built sha pin; != the v27 carry)",\n      e34["loader.efi"] != e27["loader.efi"] and sha(e34["loader.efi"]).startswith("3f595c52"),',
    'check("loader.efi is the wave38 self-heal build (as-built sha pin; != the v33 carry)",\n      e34["loader.efi"] != e33b["loader.efi"] and sha(e34["loader.efi"]).startswith("3f595c52"),')

sub('print("[loader (the Wave 38 self-heal build)]")',
    'print("[loader (the Wave 38 self-heal build, on the v34 re-baseline)]")')

sub('''check("cmdline == the v26 payload's cmdline entry byte for byte (gpu=1 carried, no probe args)",
      g[cmd_off:cmd_off + cmd_sz] == payload_v26_bytes["cmdline"])''',
'''check("cmdline == the v26 AND the v33 payload's cmdline entry byte for byte (gpu=1 carried, no probe args)",
      g[cmd_off:cmd_off + cmd_sz] == payload_v26_bytes["cmdline"] == payload_v33_bytes["cmdline"])''')

sub('payload_v26_bytes = payload_entries(payload_v26)',
    'payload_v26_bytes = payload_entries(payload_v26)\npayload_v33_bytes = payload_entries(payload_v33)')

open(p, "w", encoding="utf-8", newline="").write(s)
print("adapted; residual e27 refs:", s.count("e27"), "; residual PAYLOAD_V27 refs:", s.count("PAYLOAD_V27"),
      "; residual e38 refs:", s.count("e38"))
