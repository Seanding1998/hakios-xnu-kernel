#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
echo "== reset tracked tree to BASE, then apply in apply.sh order"
git -C Mu-Silicium checkout -- .
git -C Mu-Silicium apply --whitespace=nowarn /home/HOST-REDACTED/hakios/kernel/uefi/hakios.patch && echo "hakios.patch APPLIED"
cp -r uefi/files/. Mu-Silicium/
python3 uefi/branding/banner.py Mu-Silicium/Silicon/Silicium/SiliciumPkg/Include/Resources
cp -r devices/phk110/uefi/files/. Mu-Silicium/
echo "uefi/apply.sh: the platform of phk110"
echo "== BootManager.c has XnuLoaderMain:"
grep -n "XnuLoaderMain" Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManager.c
echo "== BootManagerLib.inf has XnuLoader.c:"
grep -n "XnuLoader" Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManagerLib.inf
echo "== XnuLoader.c present:"
ls -la Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/
echo "== Sec.c banner:"
grep -n "HakiOS UEFI" Mu-Silicium/Silicon/Silicium/SiliciumPkg/Sec/Sec.c
echo "== dsc.inc vendor:"
grep -n "PcdFirmwareVendor" Mu-Silicium/Silicon/Silicium/SiliciumPkg/SiliciumPkg.dsc.inc
echo "== BootShim.S final (device version on top of patched):"
grep -n "PAYLOAD_BASE\|XNUP" Mu-Silicium/BootShim/BootShim.S | head -8
echo "== git status summary:"
git -C Mu-Silicium status --porcelain | awk '{print $1}' | sort | uniq -c
echo "== V-3 again:"
diff -q Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h devices/phk110/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h && echo "V-3 PASS"
