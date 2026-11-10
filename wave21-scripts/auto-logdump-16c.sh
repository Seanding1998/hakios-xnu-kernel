#!/bin/bash
# Wait for the ABL fallback (Android on the bus), then pull the logdump automatically and
# extract the v16c boot's key lines (the DWC3 wake trace + the try-failed codes).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[ld $(date +%H:%M:%S)] $*"; }

for i in $(seq 1 90); do
  ST=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$ST" | grep -q "22d9"; then LOG "android on the bus ($i)"; break; fi
  if [ $((i % 6)) -eq 0 ]; then LOG "still cycling ($i): ${ST:0:40}"; fi
  sleep 30
done

adb wait-for-device 2>/dev/null || true
sleep 10
LOG "boot_completed: $(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
adb root >/dev/null 2>&1; sleep 3
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w21c-ld.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w21c-ld.bin "$R/logdump-v16c.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w21c-ld.bin'"
LOG "sha: $(sha256sum "$R/logdump-v16c.bin" | cut -c1-16)"
python3 -I - "$R/logdump-v16c.bin" <<'PYEOF'
import sys
d = open(sys.argv[1], "rb").read()
out = sys.argv[1] + ".keylines.txt"
lines = []
for token in (b"dwc3 woken", b"soft reset did not settle", b"twenty-five quiet seconds",
              b"try failed: start_ex", b"warm-boot start failed", b"usb: started",
              b"no payload at", b"UEFI EXCEPTION"):
    i = 0
    n = 0
    while True:
        i = d.find(token, i)
        if i < 0:
            break
        s = max(0, i - 60)
        seg = d[s:i + len(token) + 80].replace(b"\n", b" | ")
        lines.append(token.decode() + " @%d: %s" % (i, seg.decode("utf-8", "replace")))
        n += 1
        i += len(token)
        if n >= 8:
            break
    if n == 0:
        lines.append(token.decode() + " -> 0 hits")
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
PYEOF
LOG "done"
