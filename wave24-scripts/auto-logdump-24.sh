#!/bin/bash
# Wave 24: wait for Android (22d9 on the bus), then pull the logdump and extract the
# v20 boot's key lines: the Wave 24 diagnosis (the mirror's install/probe lines, the
# checkpoint lines, the sample lines with the vendor fields, the gate lines, the leading
# vendor errors the mirror carries), plus the freshness discriminator (the Wave 24
# loader's own size in the payload-entry line).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[ld24 $(date +%H:%M:%S)] $*"; }

for i in $(seq 1 360); do
  ST=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$ST" | grep -q "22d9"; then LOG "android on the bus ($i)"; break; fi
  if [ $((i % 6)) -eq 0 ]; then LOG "still cycling ($i): ${ST:0:40}"; fi
  sleep 30
done

adb wait-for-device 2>/dev/null || true
sleep 10
LOG "boot_completed: $(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
adb root >/dev/null 2>&1; sleep 3
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w24-ld20.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w24-ld20.bin "$R/logdump-v20.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w24-ld20.bin'"
LOG "sha: $(sha256sum "$R/logdump-v20.bin" | cut -c1-16)"
python3 -I - "$R/logdump-v20.bin" <<'PYEOF'
import sys, re
d = open(sys.argv[1], "rb").read()
out = sys.argv[1] + ".keylines.txt"
lines = []
for token in (b"the console mirror", b"the vendor debug door echoes",
              b"checkpoint-1", b"checkpoint-3", b"CP3", b"refused %x again",
              b"the first refusal is on the record",
              b"the vendor said", b"DEPSTARTCFG Fails", b"Failed to set config for ep",
              b"DwcConfigureEP failed", b"Unknown USB Speed",
              b"sample ", b"GCTL", b"phys[2]", b"phys[3]",
              b"the bring-up begins", b"presented to the host",
              b"armed at generation", b"kept its host", b"un-armed after generation",
              b"never armed across 3 generations", b"the raw UsbFn look",
              b"cleared by hand", b"start_ex is in", b"try failed",
              b"the receive buffer alone", b"dwc3 woken", b"usb: started",
              b"bulk probe gen", b"oem log", b"en0 @", b"loader_return_after expired",
              b"END OF LOG", b"payload entry 'loader.efi' size"):
    i = 0
    n = 0
    while True:
        i = d.find(token, i)
        if i < 0:
            break
        s = max(0, i - 100)
        seg = d[s:i + len(token) + 160].replace(b"\n", b" | ")
        lines.append("%s @%d: %s" % (token.decode(), i, seg.decode("utf-8", "replace")))
        n += 1
        i += len(token)
        if n >= 12:
            break
    if n == 0:
        lines.append(token.decode() + " -> 0 hits")
heads = [m.start() for m in re.finditer(rb"payload entry 'loader\.efi' size ([0-9a-f]+)", d)]
sizes = {}
for m in re.finditer(rb"payload entry 'loader\.efi' size ([0-9a-f]+)", d):
    sizes[m.group(1).decode()] = sizes.get(m.group(1).decode(), 0) + 1
lines.append("loader.efi session heads by size: %r (0x14600 = 83456 = the Wave 24 build)" % (sizes,))
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines[:45]))
PYEOF
LOG "done"
