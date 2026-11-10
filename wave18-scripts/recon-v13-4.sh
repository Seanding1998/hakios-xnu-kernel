#!/bin/bash
K=~/hakios/kernel
echo "===== init.c flash_root body (180-275) ====="
sed -n '180,275p' $K/userland/src/init.c
echo "===== build.sh system.apfs + jb embed (640-700) ====="
sed -n '640,700p' $K/userland/build.sh
echo "===== upstream darwin-write.py (write plan) ====="
sed -n '1,80p' $K/tools/darwin-write.py
echo "===== work dir contents ====="
ls -la ~/hakios/sysimage-20F66/work/ | head -20
echo "===== CONFIG_ROOT_APFS / VAR_HFS gates ====="
grep -rn "CONFIG_ROOT_APFS\|CONFIG_VAR_HFS" $K/userland/src/init.c $K/configs/common_defconfig | head -8
echo "===== on-machine loader: resident/RAMDisk1 strings ====="
grep -ac "resident" HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-payload-v11.bin
grep -ac "RAMDisk1" HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-payload-v11.bin
grep -ac "payload entry 'resident'" HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-payload-v11.bin
