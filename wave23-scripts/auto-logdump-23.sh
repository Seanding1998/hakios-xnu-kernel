#!/bin/bash
# Wave 23: wait for the ABL fallback (Android on the bus), then pull the logdump and
# extract the v19 boot's key lines: the recording chain (the kernel left a screen
# recording), the Mini display stack (swap/created-surface/frames-drawn lines), the
# three-window process evidence (SpringBoard/backboardd execs, crash/exit lines),
# plus the carry-over markers and the freshness discriminator (loader.efi size 0x12e00).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[ld23 $(date +%H:%M:%S)] $*"; }

for i in $(seq 1 120); do
  ST=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$ST" | grep -q "22d9"; then LOG "android on the bus ($i)"; break; fi
  if [ $((i % 6)) -eq 0 ]; then LOG "still cycling ($i): ${ST:0:40}"; fi
  sleep 30
done

adb wait-for-device 2>/dev/null || true
sleep 10
LOG "boot_completed: $(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
adb root >/dev/null 2>&1; sleep 3
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w23-ld19.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w23-ld19.bin "$R/logdump-v19.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w23-ld19.bin'"
LOG "sha: $(sha256sum "$R/logdump-v19.bin" | cut -c1-16)"
python3 -I - "$R/logdump-v19.bin" <<'PYEOF'
import sys, re
d = open(sys.argv[1], "rb").read()
out = sys.argv[1] + ".keylines.txt"
lines = []
for token in (b"the kernel left a screen recording", b"recording %u s", b"recording finished",
              b"recording a frame took", b"recording begins",
              b"swap %u layer", b"created surface", b"selector 4", b"selector 5",
              b"frames drawn again filtered", b"asks for a surface",
              b"not implemented",
              b"exec of SpringBoard", b"exec of backboardd", b"SpringBoard", b"backboardd",
              b"CRASH", b"exit reason", b"panic(", b"vnode table is full",
              b"bulk probe gen", b"presented to the host", b"armed at generation",
              b"asked up again", b"dwc3 woken", b"try failed: start_ex",
              b"usb: started", b"payload entry 'loader.efi' size",
              b"cmdline:", b"loader_return_after expired", b"END OF LOG"):
    i = 0
    n = 0
    while True:
        i = d.find(token, i)
        if i < 0:
            break
        s = max(0, i - 80)
        seg = d[s:i + len(token) + 110].replace(b"\n", b" | ")
        lines.append("%s @%d: %s" % (token.decode(), i, seg.decode("utf-8", "replace")))
        n += 1
        i += len(token)
        if n >= 20:
            break
    if n == 0:
        lines.append(token.decode() + " -> 0 hits")
# session freshness: count the v19 loader's own session heads (loader.efi size 0x12e00)
heads = [m.start() for m in re.finditer(rb"payload entry 'loader\.efi' size 12e00", d)]
lines.append("v18/v19 loader session heads (size 0x12e00): %d at %s" % (len(heads), heads[:12]))
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines[:40]))
PYEOF
LOG "done"
