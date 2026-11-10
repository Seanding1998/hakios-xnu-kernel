#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
echo "== apply.sh phk110 start $(date -Is)"
./uefi/apply.sh phk110 2>&1
echo "== apply.sh done $(date -Is)"
git -C Mu-Silicium rev-parse HEAD
ls Mu-Silicium/Platforms/OnePlus/phk110Pkg/ 2>/dev/null || ls Mu-Silicium/Platforms/
ls -la Mu-Silicium/Resources/DTBs/phk110.dtb Mu-Silicium/Resources/Configs/phk110.toml Mu-Silicium/BootShim/BootShim.S
diff -q Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h devices/phk110/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h && echo "XnuLoader.h device override in place (V-3)"
ls Mu-Silicium/Silicium-ACPI/Platforms/Xiaomi/ingres/ 2>/dev/null && echo "V-8: ingres AcpiTables present" || ls Mu-Silicium/Silicium-ACPI/
