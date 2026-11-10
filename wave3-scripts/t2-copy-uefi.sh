#!/bin/bash
set -e
SRC=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/upstream
K=/home/HOST-REDACTED/hakios/kernel
cd "$K"
[ -e uefi ] && { echo "uefi already exists"; exit 1; }
tar --exclude=.git -C "$SRC" -cf - hakios-uefi | tar -C "$K" -xf -
mv "$K/hakios-uefi" "$K/uefi"
ls -la "$K/uefi"
[ -x "$K/uefi/apply.sh" ] && echo "apply.sh executable"
cat "$K/uefi/BASE"
find "$K/uefi/files" -type f
echo OK
