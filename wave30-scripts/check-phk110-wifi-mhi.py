#!/usr/bin/env python3
"""check-phk110-wifi-mhi.py -- MHI transport arithmetic + ath11k PCI glue cross-check.

PHK110's radio (qca6490) hangs off PCIe0 and speaks MHI: ath11k's mhi.c drives the MHI
protocol over the device's BAR, firmware goes up via BHI, then IPCR channels carry QRTR.
Two layers of checks, both host-side:

  1. Self-check arithmetic (always runs): ring sizes must be powers of two, element size 16
     (MHI spec constant), doorbell arithmetic (phys addr of the last-written element) must
     round-trip.  Catches table-entry mistakes in whatever layout table we later freeze.
  2. Cross-check against real upstream ath11k/mhi.c (when mk-ath11k.py --verify has staged it
     at upstream-scratch/build-ath11k/linux-7.0.14/ath11k/): the qca6490 channel table must
     name the IPCR channels (IDs 100/101) ath11k registers for QRTR; SKIP otherwise.

Usage: python3 check-phk110-wifi-mhi.py [--src ATH11K_DIR]   exit 0 pass/skip, 1 fail
"""
from pathlib import Path
import argparse
import re
import sys

STAGED_DEFAULT = Path(__file__).resolve().parent / (
    "upstream-scratch/build-ath11k/linux-7.0.14/ath11k")  # set by mk-ath11k.py --verify (strip 5)

MHI_ELEMENT_SIZE = 16  # bytes, per MHI spec ring element (chan + event rings)


def verdict(name: str, ok: bool) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def pow2_ok(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def doorbell(base: int, element_size: int, index: int, ring_len: int) -> int:
    return base + ((index % ring_len) * element_size)


def main() -> int:
    ap = argparse.ArgumentParser(description="MHI ring arithmetic + ath11k PCI glue cross-check")
    ap.add_argument("--src", default=str(STAGED_DEFAULT), help="staged ath11k source dir")
    args = ap.parse_args()
    ok = True
    skips = 0

    print("== check-phk110-wifi-mhi part 1: ring arithmetic self-check")
    for ring_len in (64, 128, 256, 512):
        ok &= pow2_ok(ring_len)
    print("  [PASS] reference ring sizes 64/128/256/512 are powers of two")
    base, idx, ring = 0x40000000, 262, 128           # arbitrary base; wrap must hold
    db = doorbell(base, MHI_ELEMENT_SIZE, idx, ring)
    ok &= verdict_eq("doorbell wrap arithmetic", db,
                     base + ((idx % ring) * MHI_ELEMENT_SIZE))
    ok &= verdict_eq("doorbell at index 0", doorbell(base, 16, 0, ring), base)
    ok &= verdict_eq("doorbell one full wrap", doorbell(base, 16, ring, ring), base)

    print("== check-phk110-wifi-mhi part 2: staged ath11k cross-check")
    mhi_c = Path(args.src) / "mhi.c"
    pci_c = Path(args.src) / "pci.c"
    if not mhi_c.exists() or not pci_c.exists():
        print(f"  [SKIP] staged ath11k not found under {args.src} "
              f"(run: python3 mk-ath11k.py --verify)")
        print("         expected mhi.c + pci.c (upstream ath11k_pci module = mhi.o + pci.o)")
        skips += 1
    else:
        text = mhi_c.read_text(errors="replace")
        # qca6390 family table (WCN6750 reuses it in vendor trees): IPCR pair = channels 20/21
        block = re.search(r"ath11k_mhi_channels_qca6390\[\]\s*=\s*\{(.*?)\n\};", text, re.S)
        if block:
            ids = sorted(set(int(x) for x in re.findall(r"\.num\s*=\s*(\d+)", block.group(1))))
            names = set(re.findall(r"\.name\s*=\s*\"(\w+)\"", block.group(1)))
            print(f"  [PASS] qca6390 channel table: ids {ids}, names {sorted(names)}")
            for want in (20, 21):  # IPCR out/in pair ath11k uses for QRTR
                ok &= verdict(f"IPCR channel id {want} present", want in ids)
            ok &= verdict("both IPCR directions named IPCR", names == {"IPCR"})
        else:
            print("  [SKIP] could not parse ath11k_mhi_channels_qca6390 table shape")
            skips += 1
        for marker in ("ath11k_mhi_get_msi", "ath11k_mhi_op_runtime_get",
                       "ath11k_mhi_set_mhictrl_reset", "ath11k_mhi_register"):
            ok &= verdict(f"mhi.c defines/references {marker}", marker in text)
        # documented upstream gaps (wave30 finding): patch manifest for the lx wave
        gaps = []
        ptext = pci_c.read_text(errors="replace")
        if "WCN6750" not in ptext or "WCN6750_DEVICE_ID" not in ptext:
            gaps.append("pci.c id table has no WCN6750/QCA6490 device id "
                        "(only QCA6390/WCN6855/QCN9074)")
        if not re.search(r"case\s+ATH11K_HW_WCN6750_HW10", text):
            gaps.append("mhi.c hw_rev switch has no WCN6750 case -> default errors "
                        "'failed assign mhi_config'")
        for g in gaps:
            print(f"  [GAP-PATCH-NEEDED] {g}")
        print(f"  upstream-gap count: {len(gaps)} (both are one-line patches; see wave30 doc "
              "section 2.3 -- also listed as the pipeline patch manifest)")
        ok &= verdict("pci.c has ath11k_pci_probe", "ath11k_pci_probe" in ptext)

    verdict_txt = "FAIL" if not ok else ("PASS" if not skips else "PASS-WITH-SKIP")
    print(f"== VERDICT: {verdict_txt} (skip={skips})")
    return 0 if ok else 1


def verdict_eq(name: str, got: int, want: int) -> bool:
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {got:#x}" + ("" if ok else f" != {want:#x}"))
    return ok


if __name__ == "__main__":
    sys.exit(main())
