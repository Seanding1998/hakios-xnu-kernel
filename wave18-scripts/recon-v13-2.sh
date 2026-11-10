#!/bin/bash
K=~/hakios/kernel
echo "===== init.c main flow (1530-1620) ====="
sed -n '1530,1620p' $K/userland/src/init.c
echo "===== init.c flash_root (100,180) ====="
sed -n '100,180p' $K/userland/src/init.c
echo "===== init.c mount_cryptex (136,177) ====="
sed -n '136,177p' $K/userland/src/init.c
echo "===== init.c handoff (1300,1350) ====="
sed -n '1300,1350p' $K/userland/src/init.c
