#!/usr/bin/env python3
"""check-phk110-wifi-dtb.py -- host-side regression: PHK110 DTB vs the WiFi route we committed to.

Pattern borrowed from the raphael fork's tools/check-wifi-*.py family: check real artifacts on
the host, assert hard facts, PASS/FAIL verdicts, exit code carries the verdict (0 pass, 1 fail).

Facts under test (all present in device-layer/phk110/uefi/files/Resources/DTBs/phk110.dts):
  - wlan node qcom,cnss-qca6490@b0000000 (CNSS platform device; NO WPSS remoteproc anywhere --
    the upstream redwood WPSS-PIL chain does not apply, F14 verdict)
  - wlan-en GPIO = <0x3c 0x50 0x00> (tlmm phandle 0x3c, pin 0x50 = 80), bt-en 81, sw-ctrl 82
  - six regulator supplies: aon / dig / io / rfa1 / rfa2 / ant-switch (+ config cells each)
  - qcom,wlan-rc-num = 0 -> radio sits on PCIe controller 0
  - pcie0: qcom,pcie@1c00000 with reg-names parf/phy/dm_core/elbi/iatu/conf and an msi-map
    (GIC ITS phandle 0x235, vectors 0x5980-0x5981) -> MHI doorbells ride MSI, not level SPI
Usage: python3 check-phk110-wifi-dtb.py [--dts PATH]      exit 0 PASS, 1 FAIL
"""
from pathlib import Path
import argparse
import re
import sys

DEFAULT_DTS = Path(__file__).resolve().parent.parent / (
    "device-layer/phk110/uefi/files/Resources/DTBs/phk110.dts")

EXPECTED_VREGS = ["aon", "dig", "io", "rfa1", "rfa2"]
# ant-switch breaks the vdd-wlan-* naming pattern in the actual DTB:
#   wlan-ant-switch-supply / qcom,wlan-ant-switch-config (no vdd- prefix)
ANT_SWITCH_SUPPLY = "wlan-ant-switch-supply"
ANT_SWITCH_CONFIG = "qcom,wlan-ant-switch-config"


def verdict(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="PHK110 DTB WiFi-node regression (host-side, no phone)")
    ap.add_argument("--dts", default=str(DEFAULT_DTS), help="path to phk110.dts")
    args = ap.parse_args()
    path = Path(args.dts)
    print(f"== check-phk110-wifi-dtb: {path}")
    if not path.exists():
        print(f"FAIL: dts not found: {path}")
        return 1
    text = path.read_text(errors="replace")

    ok = True
    # node presence + compatible
    m = re.search(r"wlan:\s*qcom,cnss-qca6490@b0000000\s*\{", text)
    ok &= verdict("wlan node qcom,cnss-qca6490@b0000000 exists", bool(m))
    if m:
        end = text.index("\n\t\t};", m.end())
        node = text[m.start():end]
        ok &= verdict("compatible = qcom,cnss-qca6490",
                      'compatible = "qcom,cnss-qca6490"' in node)
        # GPIOs: <phandle pin flags>; 0x3c = tlmm, 0x50 = 80
        ok &= verdict("wlan-en-gpio pin 80 (0x50)",
                      "wlan-en-gpio = <0x3c 0x50 0x00>" in node)
        ok &= verdict("bt-en-gpio pin 81 / sw-ctrl-gpio pin 82",
                      "qcom,bt-en-gpio = <0x3c 0x51 0x00>" in node
                      and "qcom,sw-ctrl-gpio = <0x3c 0x52 0x00>" in node)
        for v in EXPECTED_VREGS:
            ok &= verdict(f"regulator vdd-wlan-{v}-supply", f"vdd-wlan-{v}-supply" in node)
            ok &= verdict(f"regulator config qcom,vdd-wlan-{v}-config",
                          f"qcom,vdd-wlan-{v}-config" in node)
        ok &= verdict("regulator wlan-ant-switch-supply", ANT_SWITCH_SUPPLY in node)
        ok &= verdict("regulator config qcom,wlan-ant-switch-config", ANT_SWITCH_CONFIG in node)
        ok &= verdict("qcom,wlan-rc-num = 0 (PCIe controller 0)",
                      "qcom,wlan-rc-num = <0x00>" in node)
        ok &= verdict("no WPSS dependency in wlan node", "wpss" not in node.lower())
    else:
        ok = False

    # PCIe controller 0
    ok &= verdict("pcie0 node qcom,pcie@1c00000", "pcie0: qcom,pcie@1c00000 {" in text)
    m2 = re.search(r"pcie0: qcom,pcie@1c00000\s*\{(.*?)\n\t\t\};", text, re.S)
    if m2:
        pcie = m2.group(1)
        ok &= verdict("pcie0 reg-names parf/phy/dm_core/elbi/iatu/conf",
                      all(n in pcie for n in
                          ["parf", "phy", "dm_core", "elbi", "iatu", "conf"]))
        ok &= verdict("pcie0 msi-map present (ITS-backed MSI for MHI)",
                      "msi-map" in pcie)
    else:
        ok = False

    print(f"== VERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
