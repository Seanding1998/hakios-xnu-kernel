#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel/uefi
echo "--- before:"
file apply.sh branding/* files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/* 2>/dev/null | head
find . -type f \( -name "*.sh" -o -name "*.py" -o -name "*.c" -o -name "*.h" -o -name "BASE" -o -name "hakios.patch" -o -name "*.md" \) -print0 | xargs -0 -I{} sh -c 'tr -d "\r" < "{}" > "{}.lf" && mv "{}.lf" "{}"'
echo "--- after:"
file apply.sh branding/* BASE hakios.patch | head
tail -c 60 BASE | od -c | head -3
echo done
