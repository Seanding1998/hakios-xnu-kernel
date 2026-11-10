#!/usr/bin/env python3
"""check-phk110-wifi-e2e.py -- on-kernel WiFi verdict, read through the wave27 channels.

This is the future acceptance gate once the ath11k object is linked into our kernel.  It talks
ONLY through the established host<->phone channels (zero-flash, read-only):
  - loader command channel (wave13/wave21 loader_talk.py): text commands over USB bulk pair,
    "getvar:<name>" reads, "oem netstat"/"oem netmode on|off" for the en0 frame ring
  - en0 data channel: "upload" / "download:" frame pipes (wave21 netmode), SSH over en0
    (wave27 timed-ssh-v27.py: phase-aware ENTRY_GUARD, MSS=160, 45s clean exit)
  - kernel state: sysctl read over SSH once sshd is up (wave22 host-visibility conventions)

Proposed (not yet existing on the kernel side) state names, registered here so the loader/
kernel waves can adopt the same names:
  getvar:wifi-state      loader-side: "absent"/"fw-loading"/"fw-ready"/"ifup" per the fork's
                         wifi_step ladder (raphael: wifi_step=15 == registered+joined)
  getvar:wifi-fw         firmware files the kernel asked lx_os_firmware() for + verdicts
  sysctl kern.hakios.wifi.scan_done / .link / .ssid     post-join state for the e2e gate

Verdict ladder mirrors the fork's step discipline: driver-attached -> firmware-ready ->
scan-heard -> joined -> frames passed.  Without a phone the script returns SKIP/NO-DEVICE
(exit 0) -- this wave is zero-phone; the contract below is the deliverable.

Usage: python3 check-phk110-wifi-e2e.py [--dry-run] [--timeout SECONDS]   exit 0 pass/skip, 1 fail
"""
from pathlib import Path
import argparse
import sys

# wave21 loader_talk.py is the canonical channel implementation (bulk pair, getvar/upload).
LOADER_TALK = Path(__file__).resolve().parent.parent / "wave21-scripts" / "loader_talk.py"

GETVARS = [
    ("wifi-state", "loader-side driver step label (absent/fw-loading/fw-ready/ifup)"),
    ("wifi-fw", "firmware files requested via lx_os_firmware() + load verdicts"),
    ("wifi-irq", "MSI vector attach/enable counts (fork: wifi_irq=1)"),
]
SYSCTLS = [
    "kern.hakios.wifi.scan_done",
    "kern.hakios.wifi.link",
    "kern.hakios.wifi.ssid",
]
# Acceptance ladder: each rung names the signal that closes it (fork RAPHAEL-WIFI order).
RUNGS = [
    ("rung1 driver-attached", "getvar wifi-state in {fw-loading,fw-ready,ifup}"),
    ("rung2 firmware-ready", "getvar wifi-state in {fw-ready,ifup} and wifi-fw all ok"),
    ("rung3 scan-heard", "sysctl kern.hakios.wifi.scan_done == 1 and ssid list non-empty"),
    ("rung4 joined", "sysctl kern.hakios.wifi.link == 1"),
    ("rung5 frames", "SSH banner exchanged over en0 while wifi link up (wave27 gate re-used)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="on-kernel WiFi verdict via wave27 channels (read-only)")
    ap.add_argument("--dry-run", action="store_true", help="print the gate contract, touch no device")
    ap.add_argument("--timeout", type=int, default=600, help="overall seconds to hold the gate open")
    args = ap.parse_args()

    print("== check-phk110-wifi-e2e contract")
    print(f"loader_talk module : {LOADER_TALK} ({'found' if LOADER_TALK.exists() else 'MISSING'})")
    for var, desc in GETVARS:
        print(f"getvar:{var:10s} -> {desc}")
    for s in SYSCTLS:
        print(f"sysctl {s:28s} (over SSH, wave22 conventions)")
    for rung, signal in RUNGS:
        print(f"{rung:22s} <= {signal}")
    print("red-line: getvar/upload reads only; no download writes, no fastboot, no adb writes")

    if args.dry_run:
        print("== VERDICT: SKIP (dry-run contract printed; no device touched)")
        return 0

    try:
        import loader_talk  # type: ignore -- wave21 module
    except Exception as e:  # noqa: BLE001
        print(f"== VERDICT: SKIP (NO-DEVICE/NO-MODULE: loader_talk import failed: {e})")
        return 0

    # Phone-path skeleton (will be exercised in the wifi bring-up wave, not wave 30):
    #   lib, sess = loader_talk.connect(libusb, args)  -> getvar:wifi-state ladder
    #   phase-aware duty cycle per wave27: loader answers -> 250s silence -> 75s ENTRY_GUARD
    #   on ifup: timed-ssh-v27 conventions for rung5 (MSS=160, clean 45s exit)
    print("== VERDICT: SKIP (phone-path skeleton; live ladder lands with the wifi bring-up wave)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
