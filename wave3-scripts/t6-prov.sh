#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
python3 - << 'PY'
path = 'tools/provenance.allow'
text = open(path).read()
anchor = 'pending  devices/redwood/uefi/files/Resources/DTBs/redwood.dtb   the same device tree, for the UEFI build\n'
add_pending = anchor + 'pending  devices/phk110/uefi/files/Resources/DTBs/phk110.dtb            the phone\'s device tree (OnePlus Ace 2, cape/SM8475), taken from the phone like the reference\'s; the same confirming to do\n'
anchor2 = 'vendor   devices/redwood/uefi/files/Binaries/redwood/*       UEFI drivers extracted from the vendor\'s xbl firmware (QcomPkg, MiPkg, RawFiles and the EDK2 modules as the vendor built them)\n'
add_vendor = anchor2 + 'vendor   devices/phk110/uefi/files/Binaries/phk110/*          UEFI drivers from the vendor\'s xbl firmware of an ingres (SM8475) phone, standing in for this phone\'s own until they are extracted from it (Binaries/phk110/README.md)\n'
assert anchor in text and anchor2 in text, 'anchors not found'
text = text.replace(anchor, add_pending).replace(anchor2, add_vendor)
open(path, 'w').write(text)
print('provenance.allow: 2 lines added')
PY
grep -n "phk110" tools/provenance.allow
python3 tools/provenance-check.py 2>&1 | tail -5
