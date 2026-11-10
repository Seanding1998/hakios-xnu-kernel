#!/usr/bin/env python3
"""One-shot generator: adapt verify-udon-hakios-v17b.py into verify-udon-hakios-v18.py."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PREV = os.path.join(os.path.dirname(HERE), "wave21-scripts")
src = open(os.path.join(PREV, "verify-udon-hakios-v17b.py"), encoding="utf-8").read()

src = src.replace('''"""Wave 21.5 round-2 verification of udon-hakios-grafted-v17b.img (field-corrected probe).

Shape identical to wave21-scripts/verify-udon-hakios-v17.py, with Boot #34's field
corrections (logdump-v17.bin):
  - the loader CHANGES: any nonzero probe answer = not armed (the field form is
    UsbDeviceSend's EFI_DEVICE_ERROR wrap -- 7-shaped -- not the raw 0x8000000C), so the
    stage keeps beating to the window's end and every code lands on the record; the
    re-throw no longer calls USB->stop() explicitly (start_ex opens with the vendor's own
    StopController -- proven every boot since v15); the final verdict keeps the server up
    (v16c's proven wall state) (d368c8aa);''',
'''"""Wave 22 verification of udon-hakios-grafted-v18.img (host visibility round).

Shape identical to wave21-scripts/verify-udon-hakios-v17b.py, with the v17b mechanism kept
whole (the 18-probe stage, the calibrated any-nonzero-is-un-armed discriminator, the two
re-throws over start_ex's own StopController) and Wave 22's two moves added on top:
  - the pump-forward: every wait past a successful start_ex (the probe beats' gaps and the
    re-throws' quiets) runs at a twenty-millisecond tick cadence, each wake pumping
    handle_event -- the host's ep0 requests are now answered inside any window;
  - the self-presentation: after every successful start_ex the loader raises the pull-up
    itself (DCTL bit 31, the vendor connect's own final write) -- the host gets a fresh
    attach in a pumped window, and the pull-up stays up for the whole session (553289a4);''')

src = src.replace("IMG, STOCK, SHIM, FD, PAYLOAD_V17B, PAYLOAD_V16, CMDLINE_V17, KFILE = sys.argv[1:9]",
                  "IMG, STOCK, SHIM, FD, PAYLOAD_V18, PAYLOAD_V16, CMDLINE_V17, KFILE = sys.argv[1:9]")
src = src.replace('payload = open(PAYLOAD_V17B, "rb").read()', 'payload = open(PAYLOAD_V18, "rb").read()')
src = src.replace('e17b = payload_entries(payload)', 'e18 = payload_entries(payload)')
src = src.replace('e17b["cmdline"] == e16["cmdline"]', 'e18["cmdline"] == e16["cmdline"]')
src = src.replace("e17b[\"kernel\"] == kfile == e16[\"kernel\"], f\"sha256 {sha(e17b['kernel'])[:16]}\"",
                  "e18[\"kernel\"] == kfile == e16[\"kernel\"], f\"sha256 {sha(e18['kernel'])[:16]}\"")
src = src.replace('b"en0_addr" in e17b["kernel"]', 'b"en0_addr" in e18["kernel"]')
src = src.replace('b"10.0.0.2/30" in e17b["kernel"]', 'b"10.0.0.2/30" in e18["kernel"]')
src = src.replace('all(s in e17b["kernel"] for s in', 'all(s in e18["kernel"] for s in')
src = src.replace('b"TouchComm v" in e17b["kernel"]', 'b"TouchComm v" in e18["kernel"]')
src = src.replace('''check("loader.efi is the v17b field-corrected build (correct PAYLOAD_BASE), not v17 or older",
      sha(e17b["loader.efi"]).startswith("d368c8aa") and e17b["loader.efi"] != e16["loader.efi"],
      sha(e17b["loader.efi"])[:16])''',
'''check("loader.efi is the v18 host-visibility build (correct PAYLOAD_BASE), not v17b or older",
      sha(e18["loader.efi"]).startswith("553289a4") and e18["loader.efi"] != e16["loader.efi"],
      sha(e18["loader.efi"])[:16])''')
src = src.replace('''check("loader.efi carries the v17b probe forensics prints",
      all(s in e17b["loader.efi"] for s in (b"usb: bulk probe gen %d beat %d: %x",
                                            b"usb: the bulk pair answered: armed at generation %d, beat %d",
                                            b"the pair never armed across 3 generations",
                                            b"the pair is un-armed after generation %d (last %x)",
                                            b"twenty-five quiet seconds before the re-throw's try",
                                            b"the re-throw did not come back")))
check("v17's retired discriminator print is gone",
      b"a non-wall probe answer stopped the stage" not in e17b["loader.efi"])
check("the v17 final-verdict line (explicit stop path) is gone",
      b"the server comes down, the run goes on without it" not in e17b["loader.efi"])''',
'''check("loader.efi carries the v17b probe forensics prints (mechanism kept whole)",
      all(s in e18["loader.efi"] for s in (b"usb: bulk probe gen %d beat %d: %x",
                                           b"usb: the bulk pair answered: armed at generation %d, beat %d",
                                           b"the pair never armed across 3 generations",
                                           b"the pair is un-armed after generation %d (last %x)",
                                           b"twenty-five quiet seconds before the re-throw's try",
                                           b"the re-throw did not come back")))
check("loader.efi carries Wave 22's self-presentation print",
      b"the gadget is presented to the host (the pull-up is ours)" in e18["loader.efi"])
check("v17's retired discriminator print is gone",
      b"a non-wall probe answer stopped the stage" not in e18["loader.efi"])
check("the v17 final-verdict line (explicit stop path) is gone",
      b"the server comes down, the run goes on without it" not in e18["loader.efi"])''')
src = src.replace('b"usb: dwc3 woken (phy suspend off + core soft reset)" in e17b["loader.efi"])',
                  'b"usb: dwc3 woken (phy suspend off + core soft reset)" in e18["loader.efi"])')
src = src.replace('all(s in e17b["loader.efi"] for s in', 'all(s in e18["loader.efi"] for s in')
src = src.replace('b"started late" not in e17b["loader.efi"]', 'b"started late" not in e18["loader.efi"]')
src = src.replace('all(s in e17b["loader.efi"] for s in (b"D22AP", b"iPhone10,3")))',
                  'all(s in e18["loader.efi"] for s in (b"D22AP", b"iPhone10,3")))')
src = src.replace('ldr = e17b["loader.efi"]', 'ldr = e18["loader.efi"]')
src = src.replace('e17b["kernel.ver"] == e16["kernel.ver"]', 'e18["kernel.ver"] == e16["kernel.ver"]')
src = src.replace('sha(e17b["kernel.ver"])[:16])', 'sha(e18["kernel.ver"])[:16])')
src = src.replace('sha(e17b["kernel.ver"]).startswith("afd473f5")', 'sha(e18["kernel.ver"]).startswith("afd473f5")')
src = src.replace("e17b[\"resident\"] == e16[\"resident\"], f\"{len(e17b['resident'])} B\")",
                  "e18[\"resident\"] == e16[\"resident\"], f\"{len(e18['resident'])} B\")")
src = src.replace("e17b[\"ramdisk\"] == e16[\"ramdisk\"], f\"{len(e17b['ramdisk'])} B\")",
                  "e18[\"ramdisk\"] == e16[\"ramdisk\"], f\"{len(e18['ramdisk'])} B\")")
src = src.replace('e17b["usb"] == b"1\\0", repr(e17b["usb"]))', 'e18["usb"] == b"1\\0", repr(e18["usb"]))')
src = src.replace('b"RAMDisk1" in e17b["loader.efi"] and b"may be written this run" in e17b["loader.efi"])',
                  'b"RAMDisk1" in e18["loader.efi"] and b"may be written this run" in e18["loader.efi"])')
src = src.replace('e17b["resident"][32:36] == b"NXSB")', 'e18["resident"][32:36] == b"NXSB")')
src = src.replace('e17b["ramdisk"][32:36] == b"NXSB")', 'e18["ramdisk"][32:36] == b"NXSB")')
src = src.replace('verify-udon-hakios-v17b.py IMG STOCK SHIM FD PAYLOAD_V17B PAYLOAD_V16 CMDLINE_V17 KERNEL_FILE',
                  'verify-udon-hakios-v18.py IMG STOCK SHIM FD PAYLOAD_V18 PAYLOAD_V16 CMDLINE_V17 KERNEL_FILE')

leftover = [l for l in src.splitlines() if "e17b[" in l]
assert not leftover, f"unconverted v17b pins remain: {leftover[:3]}"

out = os.path.join(HERE, "verify-udon-hakios-v18.py")
open(out, "w", encoding="utf-8", newline="").write(src)
print("written", out)
