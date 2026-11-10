#!/usr/bin/env python3
"""One-shot generator: adapt verify-udon-hakios-v17.py into verify-udon-hakios-v17b.py."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "verify-udon-hakios-v17.py"), encoding="utf-8").read()

src = src.replace('''"""Wave 21.5 verification of udon-hakios-grafted-v17.img (the bulk arm probe + wall re-throw).

Shape identical to wave21-scripts/verify-udon-hakios-v16b.py, with:
  - the loader CHANGES: after the boot window's start chain succeeds, the loader probes the
    bulk OUT pair with a zero-length submit on a five-second beat (each beat pumps
    handle_event -- the ep0 state machine that processes the host's SET_CONFIG, the only
    arming path of the bulk pair, advances only under that dispatch). A generation still
    answering the F12 wall code (0x8000000C, DwcPrepareURB's un-armed state byte) past its
    six-beat window is stopped and thrown again -- stop, init event re-signaled, the
    twenty-five-second quiet, and the boot window's own chain again; two re-throws, then
    the server comes down and the run proceeds without it (47acf7b0);''',
'''"""Wave 21.5 round-2 verification of udon-hakios-grafted-v17b.img (field-corrected probe).

Shape identical to wave21-scripts/verify-udon-hakios-v17.py, with Boot #34's field
corrections (logdump-v17.bin):
  - the loader CHANGES: any nonzero probe answer = not armed (the field form is
    UsbDeviceSend's EFI_DEVICE_ERROR wrap -- 7-shaped -- not the raw 0x8000000C), so the
    stage keeps beating to the window's end and every code lands on the record; the
    re-throw no longer calls USB->stop() explicitly (start_ex opens with the vendor's own
    StopController -- proven every boot since v15); the final verdict keeps the server up
    (v16c's proven wall state) (d368c8aa);''')

src = src.replace("IMG, STOCK, SHIM, FD, PAYLOAD, PAYLOAD_V16, CMDLINE_V17, KFILE = sys.argv[1:9]",
                  "IMG, STOCK, SHIM, FD, PAYLOAD_V17B, PAYLOAD_V16, CMDLINE_V17, KFILE = sys.argv[1:9]")
src = src.replace('payload = open(PAYLOAD, "rb").read()', 'payload = open(PAYLOAD_V17B, "rb").read()')
src = src.replace('e17 = payload_entries(payload)', 'e17b = payload_entries(payload)')
src = src.replace('e17["cmdline"] == e16["cmdline"]', 'e17b["cmdline"] == e16["cmdline"]')
src = src.replace("e17[\"kernel\"] == kfile == e16[\"kernel\"], f\"sha256 {sha(e17['kernel'])[:16]}\"",
                  "e17b[\"kernel\"] == kfile == e16[\"kernel\"], f\"sha256 {sha(e17b['kernel'])[:16]}\"")
src = src.replace('b"en0_addr" in e17["kernel"]', 'b"en0_addr" in e17b["kernel"]')
src = src.replace('b"10.0.0.2/30" in e17["kernel"]', 'b"10.0.0.2/30" in e17b["kernel"]')
src = src.replace('all(s in e17["kernel"] for s in', 'all(s in e17b["kernel"] for s in')
src = src.replace('b"TouchComm v" in e17["kernel"]', 'b"TouchComm v" in e17b["kernel"]')
src = src.replace('''check("loader.efi is the v17 arm-probe build (correct PAYLOAD_BASE), not v16/v16b'/v16c",
      sha(e17["loader.efi"]).startswith("47acf7b0") and e17["loader.efi"] != e16["loader.efi"],
      sha(e17["loader.efi"])[:16])''',
'''check("loader.efi is the v17b field-corrected build (correct PAYLOAD_BASE), not v17 or older",
      sha(e17b["loader.efi"]).startswith("d368c8aa") and e17b["loader.efi"] != e16["loader.efi"],
      sha(e17b["loader.efi"])[:16])''')
src = src.replace('''check("loader.efi carries the arm-probe forensics prints",
      all(s in e17["loader.efi"] for s in (b"usb: bulk probe gen %d beat %d: %x",
                                           b"usb: the bulk pair answered: armed at generation %d, beat %d",
                                           b"a non-wall probe answer stopped the stage",
                                           b"the wall stands after 3 generations",
                                           b"twenty-five quiet seconds before the re-throw's try",
                                           b"the re-throw did not come back")))''',
'''check("loader.efi carries the v17b probe forensics prints",
      all(s in e17b["loader.efi"] for s in (b"usb: bulk probe gen %d beat %d: %x",
                                            b"usb: the bulk pair answered: armed at generation %d, beat %d",
                                            b"the pair never armed across 3 generations",
                                            b"the pair is un-armed after generation %d (last %x)",
                                            b"twenty-five quiet seconds before the re-throw's try",
                                            b"the re-throw did not come back")))
check("v17's retired discriminator print is gone",
      b"a non-wall probe answer stopped the stage" not in e17b["loader.efi"])
check("the v17 final-verdict line (explicit stop path) is gone",
      b"the server comes down, the run goes on without it" not in e17b["loader.efi"])''')
src = src.replace('b"usb: dwc3 woken (phy suspend off + core soft reset)" in e17["loader.efi"])',
                  'b"usb: dwc3 woken (phy suspend off + core soft reset)" in e17b["loader.efi"])')
src = src.replace('all(s in e17["loader.efi"] for s in', 'all(s in e17b["loader.efi"] for s in')
src = src.replace('b"started late" not in e17["loader.efi"]', 'b"started late" not in e17b["loader.efi"]')
src = src.replace('all(s in e17["loader.efi"] for s in (b"D22AP", b"iPhone10,3")))',
                  'all(s in e17b["loader.efi"] for s in (b"D22AP", b"iPhone10,3")))')
src = src.replace('ldr = e17["loader.efi"]', 'ldr = e17b["loader.efi"]')
src = src.replace('e17["kernel.ver"] == e16["kernel.ver"]', 'e17b["kernel.ver"] == e16["kernel.ver"]')
src = src.replace('sha(e17["kernel.ver"])[:16])', 'sha(e17b["kernel.ver"])[:16])')
src = src.replace('sha(e17["kernel.ver"]).startswith("afd473f5")', 'sha(e17b["kernel.ver"]).startswith("afd473f5")')
src = src.replace("e17[\"resident\"] == e16[\"resident\"], f\"{len(e17['resident'])} B\")",
                  "e17b[\"resident\"] == e16[\"resident\"], f\"{len(e17b['resident'])} B\")")
src = src.replace("e17[\"ramdisk\"] == e16[\"ramdisk\"], f\"{len(e17['ramdisk'])} B\")",
                  "e17b[\"ramdisk\"] == e16[\"ramdisk\"], f\"{len(e17b['ramdisk'])} B\")")
src = src.replace('e17["usb"] == b"1\\0", repr(e17["usb"]))', 'e17b["usb"] == b"1\\0", repr(e17b["usb"]))')
src = src.replace('b"RAMDisk1" in e17["loader.efi"] and b"may be written this run" in e17["loader.efi"])',
                  'b"RAMDisk1" in e17b["loader.efi"] and b"may be written this run" in e17b["loader.efi"])')
src = src.replace('e17["resident"][32:36] == b"NXSB")', 'e17b["resident"][32:36] == b"NXSB")')
src = src.replace('e17["ramdisk"][32:36] == b"NXSB")', 'e17b["ramdisk"][32:36] == b"NXSB")')
src = src.replace('verify-udon-hakios-v17.py IMG STOCK SHIM FD PAYLOAD_V17 PAYLOAD_V16 CMDLINE_V17 KERNEL_FILE',
                  'verify-udon-hakios-v17b.py IMG STOCK SHIM FD PAYLOAD_V17B PAYLOAD_V16 CMDLINE_V17 KERNEL_FILE')

leftover = [l for l in src.splitlines() if "e17[" in l]
assert not leftover, f"unconverted v17 pins remain: {leftover[:3]}"

out = os.path.join(HERE, "verify-udon-hakios-v17b.py")
open(out, "w", encoding="utf-8", newline="").write(src)
print("written", out)
