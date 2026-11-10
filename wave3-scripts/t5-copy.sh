#!/bin/bash
set -e
MU=/home/HOST-REDACTED/hakios/kernel/Mu-Silicium
echo "== build report FIXED_ADDRESS rows (V-6):"
ls "$MU"/Build/phk110Pkg/RELEASE_CLANGPDB/*.txt 2>/dev/null | head -3
grep -n "0xA7100000\|0xA760D000\|RamManager\|UEFI FD\|PlatformPei" "$MU"/Build/phk110Pkg/RELEASE_CLANGPDB/*.txt 2>/dev/null | head -12
echo "== copy artifacts to Windows device-layer:"
DST=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer
cp /home/HOST-REDACTED/hakios/kernel/xnu-phk110.img "$DST/"
cp "$MU/Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd" "$DST/SILICIUM_UEFI.fd"
cp /home/HOST-REDACTED/hakios/kernel/run-payload.bin "$DST/xnu-phk110-payload.bin"
ls -la "$DST/"
echo "== sha256 (final):"
sha256sum "$DST/xnu-phk110.img" "$DST/SILICIUM_UEFI.fd" "$DST/xnu-phk110-payload.bin"
