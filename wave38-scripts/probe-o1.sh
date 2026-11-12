#!/bin/bash
# Wave 38 gen-4 -O1 elimination probe: rebuilds the non-static rebuild variant, then
# probes which strings survive into the object (calibrated against known-live strings).
set -u
mkdir -p /tmp/w38test
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
perl -0777 -pe 's/static void\nusb_pair_rebuild\(void\)/void\nusb_pair_rebuild(void)/' \
  /home/cyrux/hakios/kernel/xnuloader/loader.c > /tmp/w38test/loader-ns.c
cd /home/cyrux/hakios/kernel/xnuloader
clang --target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector \
  -fshort-wchar -mgeneral-regs-only -O1 -DPAYLOAD_BASE=0xF4000000ULL -I. \
  -c /tmp/w38test/loader-ns.c -o /tmp/w38test/o1ns.obj 2>/tmp/w38test/cc.err
echo "compile rc=$? size=$(stat -c%s /tmp/w38test/o1ns.obj 2>/dev/null)"
head -3 /tmp/w38test/cc.err
for s in 'the pair reads dead' 'the platform is asked up again' 'checkpoint-3' \
         'warm-boot start failed' 'the wall' 'the IN gate is up' \
         'the service window is over' 'reads dead both ways'; do
  printf '%-38s -> %s\n' "$s" "$(strings -a /tmp/w38test/o1ns.obj | grep -cF -- "$s")"
done
