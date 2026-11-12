#!/bin/bash
# Wave 45 (busid-generic edition): keep the xnuloader gadget owned by Windows
# libusb while the hunts run. The persisted usbipd GUIDs auto-attach the device
# on every re-enumeration, which makes the tunnel's Windows-libusb opens fail.
# Scans every busid (the device moved 2-2 -> 1-1 after the user's power cycle)
# and detaches ONLY a stale WSL attach of the xnuloader gadget itself -- never
# the ABL fastboot gadget, whose USB name is not xnuloader.
# Red-line discipline: detach ONLY (never wsl --shutdown, no config changes).
while true; do
    BUS=$(usbipd.exe list 2>/dev/null | grep "xnuloader" | grep "Attached" | awk '{print $1}' | head -1)
    if [ -n "$BUS" ]; then
        echo "[$(date +%H:%M:%S)] detaching stale WSL attach on the xnuloader gadget at $BUS"
        usbipd.exe detach --busid "$BUS" 2>&1 | tail -1
    fi
    sleep 2
done
