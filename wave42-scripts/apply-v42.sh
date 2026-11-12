#!/bin/bash
# Wave 42: apply the root fix to the real tree, with backup, then a -O1 pre-flight
# check BEFORE the real build.sh run (which overwrites loader.efi/loader.obj).
set -e
cd ~/hakios/kernel/xnuloader
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110

echo "== backup: the gen-4+hardening terminal state joins the chain =="
[ -f loader.c.v38-gen4hard ] || cp -p loader.c loader.c.v38-gen4hard
md5sum loader.c loader.c.v38-gen4hard

echo "== apply the v42 patch =="
python3 "$R/wave42-scripts/patch-loader-v42-stamps-volatile.py" loader.c
md5sum loader.c

echo "== pre-flight: -O1 compile to /tmp, string + symbol check =="
mkdir -p /tmp/w42
clang --target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector \
  -fshort-wchar -mgeneral-regs-only -O1 -Wall -Wextra -Wno-unused-parameter \
  -DPAYLOAD_BASE=0xF4000000ULL -c loader.c -o /tmp/w42/v42preflight.obj
python3 - <<'EOF'
data = open('/tmp/w42/v42preflight.obj', 'rb').read()
import hashlib
print('preflight obj sha', hashlib.sha256(data).hexdigest()[:8], len(data), 'B')
needles = [
    b'the pair reads dead in this generation',
    b'bounded recovery %d of 2',
    b"the recovery's bring-up is back",
    b"the recovery's bring-up did not come back",
    b'the IN gate is up',
    b'the service window is over',
]
ok = True
for s in needles:
    c = data.count(s)
    ok = ok and c >= 1
    print(f'  {c}x {s[:48]!r}')
assert ok, 'gen-4 strings missing at -O1: the fix did not hold'
print('PRE-FLIGHT PASS: all gen-4 strings present at -O1')
EOF
