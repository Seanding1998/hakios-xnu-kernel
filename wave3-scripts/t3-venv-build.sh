#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
echo "== venv start $(date -Is)"
if [ ! -x venv/bin/python3 ]; then
  python3 -m venv venv
fi
venv/bin/python3 -m pip install -q -r Mu-Silicium/pip-requirements.txt 2>&1 | tail -5
venv/bin/python3 -c "import edk2toolext, edk2toollib; print('stuart deps OK')"
echo "== build start $(date -Is)"
cd Mu-Silicium
CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu- ../venv/bin/python3 build_uefi.py -d phk110 -r RELEASE > /tmp/build_phk110.log 2>&1
rc=$?
echo "build exit=$rc"
tail -20 /tmp/build_phk110.log
ls -la Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd
echo "== done $(date -Is)"
