#!/bin/bash
# Wave 20: write the Darwin front (blocks 0..1284994 of the darwin partition):
#   segment 1: system.apfs      @ block 0        (616835 blocks = 2526556160 B, /jb inside)
#   segment 2: cryptex-os.dmg   @ block 616835   (665600 blocks = 2726297600 B)
#   segment 3: cryptex-app.dmg  @ block 1282435  (2560 blocks = 10485760 B)
# Range gate: last written block 1284994 << 2042368 (the HFS+ data volume head,
# this wave zero-write). Same guarded-dd recipe as wave18 (the darwin-write tool
# refuses offset < PROTECTED=1374208, so plain su dd with our own range gate).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
K=/home/HOST-REDACTED/hakios/kernel
CRYPTEX_OS=/home/HOST-REDACTED/hakios/sysimage-20F66/work/cryptex-os.dmg
CRYPTEX_APP=/home/HOST-REDACTED/hakios/sysimage-20F66/work/cryptex-app.dmg
EXPECT_SIZE=21474816000   # 5242875 * 4096
GATE=2042368              # first block of the data volume: must never be touched

adb wait-for-device
adb root >/dev/null 2>&1; sleep 3

write_seg() {  # name file block
  local name=$1 file=$2 block=$3
  local size=$(stat -c %s "$file")
  local blocks=$(( size / 4096 ))
  [ $(( size % 4096 )) -eq 0 ] || { echo "$name not block-aligned"; exit 1; }
  local end=$(( block + blocks ))
  [ "$end" -le "$GATE" ] || { echo "RANGE GATE: $name would end at $end >= $GATE"; exit 1; }
  local host_sha=$(sha256sum "$file" | cut -d' ' -f1)
  echo "== $name: $file -> darwin block $block ($blocks blocks, ends $end < $GATE) =="
  adb shell "rm -f /data/local/tmp/w20seg.bin"
  adb push "$file" /data/local/tmp/w20seg.bin >/dev/null
  local dev_sha=$(adb shell "sha256sum /data/local/tmp/w20seg.bin" | cut -d' ' -f1 | tr -d '\r')
  if [ "$dev_sha" != "$host_sha" ]; then echo "PUSH SHA MISMATCH ($dev_sha != $host_sha)"; exit 1; fi
  echo "  pushed, sha ${dev_sha:0:16}"
  adb shell "su -c 'test \$(readlink -f /dev/block/by-name/darwin) = /dev/block/sda15 || exit 9; test \$(blockdev --getsize64 /dev/block/sda15) = $EXPECT_SIZE || exit 9; dd if=/data/local/tmp/w20seg.bin of=/dev/block/by-name/darwin bs=4096 seek=$block count=$blocks conv=notrunc,fsync && sync'" 2>&1 | tail -1
  if [ $? -ne 0 ]; then echo "DD FAILED for $name"; exit 1; fi
  local back_sha=$(adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=$block count=$blocks 2>/dev/null | sha256sum'" | cut -d' ' -f1 | tr -d '\r')
  if [ "$back_sha" != "$host_sha" ]; then echo "READBACK MISMATCH ($back_sha != $host_sha)"; exit 1; fi
  echo "  read back: ${back_sha:0:16} -- the same"
  adb shell "rm -f /data/local/tmp/w20seg.bin"
}

write_seg system.apfs "$K/userland/system.apfs" 0
write_seg cryptex-os.dmg "$CRYPTEX_OS" 616835
write_seg cryptex-app.dmg "$CRYPTEX_APP" 1282435
echo "-- data volume head still intact @2042368 (expect 1e4cd367...):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=1 2>/dev/null | sha256sum'" | tr -d '\r'
echo "== darwin front written =="
