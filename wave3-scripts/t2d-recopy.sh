#!/bin/bash
set -e
SRC=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/upstream
K=/home/HOST-REDACTED/hakios/kernel
rm -rf "$K/uefi"
mkdir -p "$K/uefi"
git -C "$SRC/hakios-uefi" archive HEAD | tar -C "$K/uefi" -xf -
cd "$K/uefi"
chmod +x apply.sh export.sh branding/banner.py 2>/dev/null || true
echo "--- patch line endings (should be a mix or LF as stored in git):"
file hakios.patch
head -c 200 hakios.patch | od -c | grep -c '\r' || true
python3 - << 'PY'
data = open('/home/HOST-REDACTED/hakios/kernel/uefi/hakios.patch','rb').read()
crlf = data.count(b'\r\n')
lf = data.count(b'\n') - crlf
print(f'CRLF lines: {crlf}, LF-only lines: {lf}')
PY
echo "--- BASE:"; cat BASE
ls -la
