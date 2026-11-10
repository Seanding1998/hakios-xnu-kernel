#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
echo "== resume apply steps $(date -Is)"
git -C Mu-Silicium apply --whitespace=nowarn uefi/hakios.patch && echo "hakios.patch applied"
cp -r uefi/files/. Mu-Silicium/
python3 uefi/branding/banner.py Mu-Silicium/Silicon/Silicium/SiliciumPkg/Include/Resources
cp -r devices/phk110/uefi/files/. Mu-Silicium/
echo "uefi/apply.sh: the platform of phk110"
git -C Mu-Silicium rev-parse HEAD
echo "== V-3 device override check:"
diff -q Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h devices/phk110/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h && echo "V-3 PASS: XnuLoader.h = device version (0xC0000000)"
echo "== V-8 ACPI check:"
ls Mu-Silicium/Silicium-ACPI/Platforms/Xiaomi/ingres/
echo "== BootShim.S in tree (device default):"
grep -n "PAYLOAD_BASE" Mu-Silicium/BootShim/BootShim.S | head -5
echo "== phk110 tree files:"
ls Mu-Silicium/Platforms/OnePlus/phk110Pkg/
ls -la Mu-Silicium/Resources/DTBs/phk110.dtb Mu-Silicium/Resources/Configs/phk110.toml
echo "== Binaries/phk110 (only README expected before blob copy):"
ls Mu-Silicium/Binaries/phk110/ | head
echo "== git status summary:"
git -C Mu-Silicium status --porcelain | awk '{print $1}' | sort | uniq -c
