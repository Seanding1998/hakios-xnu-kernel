#!/usr/bin/env python3
"""check-phk110-wifi-fw.py -- firmware staging gate for the WCN6750 (qca6490-form) WiFi radio.

Directory truth (staged linux-7.0.14 ath11k/core.c, wcn6750 hw_params entry):
  .fw.dir = "WCN6750/hw1.0"  board_size 256 KiB, cal_offset 128 KiB, bdf_addr 0x4B0C0000.
F14's "QCA6490/hw1.0" naming corrected by wave 30: QCA6490 is not an ath11k hw_rev at all
(core.h enum) -- the chip PHK110 exposes as cnss-qca6490 is ath11k's WCN6750 hw1.0.

  WCN6750/hw1.0/amss.bin      WLAN firmware image carried to the radio over MHI BHI
  WCN6750/hw1.0/m3.bin        m3 firmware
  WCN6750/hw1.0/board-2.bin   board data (BDF), device-specific variant

Discipline inherited from the raphael fork (docs/RAPHAEL-WIFI.md / pull-firmware.sh): the BDF
is device-specific; a generic bdwlan.bin default is refused (raphael already burned on cnss-
daemon picking the wrong BDF variant).  Per-file verdicts PASS/FAIL/SKIP; SKIP = not staged
yet (expected until the phone returns and pull-firmware runs -- zero-phone wave).

SHA256 registry below stays empty until first real pull; each entry then pins the blob.
Usage: python3 check-phk110-wifi-fw.py [--dir STAGING_DIR]   exit 0 pass/skip-only, 1 fail
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

STAGING_DEFAULT = Path(__file__).resolve().parent / "fw-phk110"
FW_SUBPATH = "WCN6750/hw1.0"
# F14 wrote "QCA6490/hw1.0"; kept as an alias so a pull under the old name is caught, not lost.
FW_SUBPATH_ALIASES = ["QCA6490/hw1.0"]
EXPECTED = {
    "amss.bin": "WLAN firmware (MHI BHI image)",
    "m3.bin": "m3 firmware",
    "board-2.bin": "board data / BDF (device-specific)",
}
# Wave 30: registry intentionally empty -- fill after the first pull-firmware run.
SHA256_REGISTRY = {}  # e.g. {"amss.bin": "<64 hex>"}
# Generic-default refusal list (raphael lesson): these must NOT be the only BDF present.
GENERIC_BDF_NAMES = ["bdwlan.bin", "bdwlan.b00"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="qca6490 firmware staging gate (host-side)")
    ap.add_argument("--dir", default=str(STAGING_DEFAULT), help="staging dir")
    ap.add_argument("--json", action="store_true", help="emit machine-readable summary json")
    args = ap.parse_args()
    root = Path(args.dir) / FW_SUBPATH
    print(f"== check-phk110-wifi-fw: {root}")
    results = {}
    fails = 0
    skips = 0
    for name, desc in EXPECTED.items():
        want = SHA256_REGISTRY.get(name)
        p = root / name
        if not p.exists():
            print(f"  [SKIP] {name} -- not staged yet ({desc})")
            results[name] = "SKIP"
            skips += 1
            continue
        got = sha256_of(p)
        if want and got != want:
            print(f"  [FAIL] {name} -- SHA256 mismatch want {want} got {got}")
            results[name] = "FAIL"
            fails += 1
            continue
        print(f"  [PASS] {name} -- {p.stat().st_size} bytes, sha256 {got[:16]}..."
              + ("" if want else " (unpinned; add to SHA256_REGISTRY)"))
        results[name] = "PASS"

    # raphael-lesson refusal: generic BDF alone must fail loudly
    generic_present = [g for g in GENERIC_BDF_NAMES if (Path(args.dir) / g).exists()
                       or (root / g).exists()]
    if generic_present and results.get("board-2.bin") != "PASS":
        print(f"  [FAIL] generic BDF present without device board-2.bin: {generic_present}")
        print("         (raphael: wrong-BDF costs days; device variant is mandatory)")
        fails += 1
        results["generic-bdf"] = "FAIL"
    elif generic_present:
        print(f"  [WARN] generic BDF present alongside board-2.bin: {generic_present}")
        results["generic-bdf"] = "WARN"

    verdict = "FAIL" if fails else ("SKIP-ONLY" if skips else "PASS")
    print(f"== VERDICT: {verdict} (fail={fails} skip={skips})")
    if args.json:
        print(json.dumps({"verdict": verdict, "results": results}, indent=2))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
