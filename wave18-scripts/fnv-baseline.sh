#!/bin/bash
# Wave 18: R1 FNV baseline puller.
# Pulls the 8 reference partitions (both slots) off the phone over adb
# (rooted Android, the third trusted path -- Linux kernel reads, no UFSDxe)
# so the kernel-side FNV from the b23 log has something to be compared with.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
OUT=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/intel/fnv-baseline
mkdir -p "$OUT"
cd "$OUT" || exit 1
adb wait-for-device
adb root >/dev/null 2>&1; sleep 3
for p in bluetooth abl aop xbl tz hyp dsp modem; do
  for s in a b; do
    if adb shell "su -c 'test -e /dev/block/by-name/${p}_${s}'" >/dev/null 2>&1; then
      echo "pulling ${p}_${s}..."
      adb shell "su -c 'dd if=/dev/block/by-name/${p}_${s} of=/data/local/tmp/w18.img bs=4096'" >/dev/null 2>&1
      adb pull /data/local/tmp/w18.img "${p}_${s}.bin" >/dev/null 2>&1 && echo "  pulled ${p}_${s}.bin $(stat -c %s ${p}_${s}.bin) bytes"
      adb shell "su -c 'rm -f /data/local/tmp/w18.img'" >/dev/null 2>&1
    else
      echo "  ${p}_${s} absent"
    fi
  done
done
ls -la
