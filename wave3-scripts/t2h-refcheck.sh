#!/bin/bash
cd /home/HOST-REDACTED/hakios/kernel/Mu-Silicium
python3 - << 'PY'
import re, glob, os
PP = ["Platforms/OnePlus","Common/Mu","Common/Mu_OEM_Sample","Mu_Basecore","Silicon/Qualcomm","Silicon/Silicium","Silicium-ACPI","Silicium-ACPI/Platforms/Xiaomi","Silicium-ACPI/Silicon/Qualcomm","."]
refs = set()
for inc in glob.glob('Platforms/OnePlus/phk110Pkg/Include/*.inc'):
    for line in open(inc, errors='ignore'):
        for m in re.finditer(r'([A-Za-z0-9_/\.\-]+\.(?:inf|fdx|fd|bin|aml|bmp|mbn|elf))', line, re.I):
            refs.add(m.group(1))
def find(r):
    for p in PP:
        if os.path.isfile(os.path.join(p, r)):
            return True
    return False
missing = sorted(r for r in refs if not find(r))
infs = sorted(r for r in refs if r.lower().endswith('.inf'))
print(f'total refs: {len(refs)}  INFs: {len(infs)}  missing: {len(missing)}')
for r in missing:
    print('MISSING:', r)
PY
