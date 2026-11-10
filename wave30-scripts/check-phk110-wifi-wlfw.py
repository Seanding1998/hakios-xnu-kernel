#!/usr/bin/env python3
"""check-phk110-wifi-wlfw.py -- QMI WLFW service contract check (ath11k qmi.c side).

For qca6490/WCN6750 on PCIe the control plane is: MHI channels -> QRTR -> QMI service
ATH11K_QMI_WLFW_SERVICE_ID_V01.  This check pins the pieces the host must reproduce when the
kernel-side QMI/WLFW shim gets written (fork keeps QMI "as it is" through its lx layer; the
kernel tree's redwood lineage already has QRTR + QMI + a WLFW stand-in per F14).

Layers checked:
  1. staged ath11k/qmi.c (from mk-ath11k.py --verify): the QMI message table must reference
     the standard WLFW indications (REQUEST_MEM / FW_MEM_READY / FW_READY / COLD_BOOT_CAL_DONE
     / FW_INIT_DONE) and the service lookup with WCN6750 instance id -- SKIP if not staged.
  2. The QMI message ID *values* live in a not-staged generated header (upstream kernel
     include/linux/soc/qcom or qmi_wlfw_v01 generated code); the script reports them as
     TODO-SOURCE rather than inventing numbers (no fabrication rule).

Usage: python3 check-phk110-wifi-wlfw.py [--src ATH11K_DIR]   exit 0 pass/skip, 1 fail
"""
from pathlib import Path
import argparse
import re
import sys

STAGED_DEFAULT = Path(__file__).resolve().parent / (
    "upstream-scratch/build-ath11k/linux-7.0.14/ath11k")

REQUIRED_INDICATIONS = [
    "QMI_WLFW_REQUEST_MEM_IND_V01",
    "QMI_WLFW_FW_MEM_READY_IND_V01",
    "QMI_WLFW_FW_READY_IND_V01",
    "QMI_WLFW_COLD_BOOT_CAL_DONE_IND_V01",
    "QMI_WLFW_FW_INIT_DONE_IND_V01",
]


def verdict(name: str, ok: bool) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="QMI WLFW contract check (host-side)")
    ap.add_argument("--src", default=str(STAGED_DEFAULT), help="staged ath11k source dir")
    args = ap.parse_args()
    ok = True
    skips = 0

    print("== check-phk110-wifi-wlfw: staged ath11k qmi.c")
    qmi_c = Path(args.src) / "qmi.c"
    if not qmi_c.exists():
        print(f"  [SKIP] {qmi_c} not staged (run: python3 mk-ath11k.py --verify)")
        skips += 1
    else:
        text = qmi_c.read_text(errors="replace")
        for ind in REQUIRED_INDICATIONS:
            ok &= verdict(f"indication table has {ind}", ind in text)
        ok &= verdict("service lookup ATH11K_QMI_WLFW_SERVICE_ID_V01",
                      "ATH11K_QMI_WLFW_SERVICE_ID_V01" in text)
        ok &= verdict("WCN6750 instance id referenced",
                      "WCN6750" in text or "wcn6750" in text.lower())

    print("== check-phk110-wifi-wlfw: QMI message ID values")
    # Where do the numbers live?  Not in ath11k/*.c -- in the kernel's generated QMI header.
    # Honest handling: point at the TODO-SOURCE, do not invent values.
    id_sources = [
        "linux include/linux/soc/qcom/ (generated qmi_wlfw_v01 or hand-written ids)",
        "fork lineage: xnu-deps/build/ath10k/gen had qmi_wlfw_v01.c generated per pipeline",
    ]
    print("  [TODO-SOURCE] message-id values not staged by the wave-30 extraction "
          "(ath11k/*.c only reference the symbols)")
    for s in id_sources:
        print(f"         -> {s}")
    print("         wave-31+ action: extract the id header into the pipeline SOURCES list "
          "before freezing the WLFW shim table")

    verdict_txt = "FAIL" if not ok else ("PASS" if not skips else "PASS-WITH-SKIP")
    print(f"== VERDICT: {verdict_txt} (skip={skips})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
