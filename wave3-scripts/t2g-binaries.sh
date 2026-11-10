#!/bin/bash
set -e
MU=/home/HOST-REDACTED/hakios/kernel/Mu-Silicium
F=/home/HOST-REDACTED/hakios/Mu-Silicium
echo "== F tree Binaries/phk110:"
ls "$F/Binaries/phk110" | wc -l
du -sh "$F/Binaries/phk110"
cp -r "$F/Binaries/phk110/." "$MU/Binaries/phk110/"
echo "== new tree Binaries/phk110:"
ls "$MU/Binaries/phk110" | wc -l
du -sh "$MU/Binaries/phk110"
ls "$MU/Binaries/phk110" | head -8
echo "== INF/RAW existence check (cwd = MU root):"
cd "$MU"
python3 - << 'PY'
import re, glob, os
refs = set()
for inc in glob.glob('Platforms/OnePlus/phk110Pkg/Include/*.inc'):
    for line in open(inc, errors='ignore'):
        for m in re.finditer(r'([A-Za-z0-9_/\.\-]+\.inf)', line):
            refs.add(m.group(1))
        for m in re.finditer(r'([A-Za-z0-9_/\.\-]+\.(?:fdx|fd|bin|aml|bmp|mbn|elf))', line, re.I):
            refs.add(m.group(1))
missing = [r for r in sorted(refs) if not (os.path.isfile(r))]
infs = [r for r in sorted(refs) if r.endswith('.inf')]
others = [r for r in sorted(refs) if not r.endswith('.inf')]
print(f'unique INFs referenced: {len(infs)}; missing: {sum(1 for r in infs if not os.path.isfile(r))}')
print(f'other blobs referenced: {len(others)}; missing: {sum(1 for r in others if not os.path.isfile(r))}')
for r in sorted(refs):
    if not os.path.isfile(r):
        print('MISSING:', r)
PY
