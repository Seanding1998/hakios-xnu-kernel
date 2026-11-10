#!/bin/bash
# Wave 18: write the Darwin root volume + the two cryptexes into the darwin
# partition's front (blocks 0..2042367, read-only to the kernel: the write
# window starts at 2042368 where the P0 HFS+ data volume sits, untouched).
#   segment 1: system.apfs   @ block 0        (604420 blocks = 2475704320 B)
#   segment 2: cryptex-os.dmg @ block 604420  (665600 blocks = 2726297600 B)
#   segment 3: cryptex-app.dmg @ block 1270020 (2560 blocks = 10485760 B)
# Every segment: push -> phone-side sha check -> guarded dd -> read-back sha.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
SYSTEM=$R/../../hakios-kernel-none 2>/dev/null
SYSTEM=/home/HOST-REDACTED/hakios/kernel/userland/system.apfs
CRYPTEX_OS=/home/HOST-REDACTED/hakios/sysimage-20F66/work/cryptex-os.dmg
CRYPTEX_APP=/home/HOST-REDACTED/hakios/sysimage-20F66/work/cryptex-app.dmg
EXPECT_SIZE=21474816000   # 5242875 * 4096

adb wait-for-device
adb root >/dev/null 2>&1; sleep 3

write_seg() {  # name file block
  local name=$1 file=$2 block=$3
  local size=$(stat -c %s "$file")
  local blocks=$(( size / 4096 ))
  [ $(( size % 4096 )) -eq 0 ] || { echo "$name not block-aligned"; exit 1; }
  local host_sha=$(sha256sum "$file" | cut -d' ' -f1)
  echo "== $name: $file -> darwin block $block ($blocks blocks) =="
  adb shell "rm -f /data/local/tmp/w18seg.bin"
  adb push "$file" /data/local/tmp/w18seg.bin >/dev/null
  local dev_sha=$(adb shell "sha256sum /data/local/tmp/w18seg.bin" | cut -d' ' -f1 | tr -d '\r')
  if [ "$dev_sha" != "$host_sha" ]; then echo "PUSH SHA MISMATCH ($dev_sha != $host_sha)"; exit 1; fi
  echo "  pushed, sha $dev_sha"
  adb shell "su -c 'test \$(readlink -f /dev/block/by-name/darwin) = /dev/block/sda15 || exit 9; test \$(blockdev --getsize64 /dev/block/sda15) = $EXPECT_SIZE || exit 9; dd if=/data/local/tmp/w18seg.bin of=/dev/block/by-name/darwin bs=4096 seek=$block count=$blocks conv=notrunc,fsync && sync'" 2>&1 | tail -1
  if [ $? -ne 0 ]; then echo "DD FAILED for $name"; exit 1; fi
  local back_sha=$(adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=$block count=$blocks 2>/dev/null | sha256sum'" | cut -d' ' -f1 | tr -d '\r')
  if [ "$back_sha" != "$host_sha" ]; then echo "READBACK MISMATCH ($back_sha != $host_sha)"; exit 1; fi
  echo "  read back: $back_sha -- the same"
  adb shell "rm -f /data/local/tmp/w18seg.bin"
}

write_seg system.apfs "$SYSTEM" 0
write_seg cryptex-os.dmg "$CRYPTEX_OS" 604420
write_seg cryptex-app.dmg "$CRYPTEX_APP" 1270020
echo "== darwin front written =="
