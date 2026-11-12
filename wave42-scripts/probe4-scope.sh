#!/bin/bash
# Wave 42 probe 4: measure IPSCCP's effect per function (pre/post dump sizes) +
# which strings survive in the current -O1 obj + the file's existing volatile usage.
set -u
mkdir -p /tmp/w42
cd ~/hakios/kernel/xnuloader
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave42-scripts
FLAGS="--target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mgeneral-regs-only -O1 -w -DPAYLOAD_BASE=0xF4000000ULL -I."

clang $FLAGS -c loader.c -o /tmp/w42/p4.obj \
  -mllvm -print-after-all \
  -mllvm "-filter-print-funcs=usb_pair_rebuild,usb_command_loop,usb_start_attempt,usb_rx,usb_wait" 2>"$R/afterall4.log" >/dev/null
echo "log bytes: $(stat -c%s "$R/afterall4.log")"
python3 - "$R/afterall4.log" <<'EOF'
import re, sys
txt = open(sys.argv[1], encoding='utf-8', errors='replace').read()
# split into (header, body) chunks
chunks = re.split(r'; \*\*\* IR Dump After (.*?) \*\*\*', txt)
# chunks[0] preamble, then pairs (passname, body)
passes = list(zip(chunks[1::2], chunks[2::2]))
for name, body in passes:
    m = re.search(r'define\s+(?:internal\s+)?\S+\s+@([\w.$]+)\(', body)
    if m:
        lines = body.count('\n')
        print(f'{name[:55]:57s} func={m.group(1):24s} lines={lines}')
EOF
echo "== string battery on the -O1 obj =="
for s in 'the pair reads dead in this generation' 'the service window is over' 'the wall' 'the IN gate is up' 'xnuloader' 'bounded recovery'; do
  printf '  %-45s -> %s\n' "$s" "$(strings -a /tmp/w42/p4.obj | grep -cF -- "$s")"
done
echo "== volatile usage on state globals in loader.c =="
grep -nE 'static volatile|volatile uint|volatile int|volatile u32|volatile u64' loader.c | head -20
