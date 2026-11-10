#!/bin/bash
K=~/hakios/kernel
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
echo "===== loader.c resident placement (2965-3060) ====="
sed -n '2965,3060p' $K/xnuloader/loader.c
echo "===== on-machine loader strings ====="
for s in "resident" "RAMDisk1" "it is the root (md0)"; do
  printf "%-30s %s\n" "$s" "$(grep -ac "$s" $R/device-layer/udon-hakios-payload-v11.bin)"
done
echo "===== CONFIG_ROOT_APFS/VAR_HFS kernel gates ====="
grep -rn "CONFIG_ROOT_APFS\|CONFIG_VAR_HFS" $K/configs/common_defconfig
grep -rln "CONFIG_ROOT_APFS" $K/xnu $K/drivers $K/userland 2>/dev/null | head -5
echo "===== work dir contents ====="
ls -la ~/hakios/sysimage-20F66/work/
echo "===== CACHE + DARWIN defs in build.sh ====="
grep -n "^CACHE=\|^DARWIN=\|^RC=\|^RC_JOBS=" $K/userland/build.sh | head
