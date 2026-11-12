#!/bin/bash
# Wave 42: keep the xnuloader gadget owned by Windows libusb while the hunts run.
# The persisted usbipd GUIDs auto-attach the device to WSL on every re-enumeration,
# which makes the tunnel's Windows-libusb opens fail with LIBUSB_ERROR_NOT_SUPPORTED.
# Red-line discipline: detach ONLY (never wsl --shutdown, no config changes).
while true; do
    LINE=$(usbipd.exe list 2>/dev/null | grep "2-2" | head -1)
    if printf '%s' "$LINE" | grep -qE "18d1:d00d.*Attached"; then
        echo "[$(date +%H:%M:%S)] detaching stale WSL attach on the xnuloader gadget"
        usbipd.exe detach --busid 2-2 2>&1 | tail -1
    fi
    sleep 2
done
