#!/bin/bash
# Wave 18 phase 2 recon: v13 (real-init chain) decision inputs.
K=~/hakios/kernel
echo "===== 1. mkpayload.py entry names ====="
sed -n '1,80p' $K/xnuloader/mkpayload.py
echo "===== 2. loader.c ramdisk/resident entry handling (2670-2710) ====="
sed -n '2670,2710p' $K/xnuloader/loader.c
echo "===== 3. loader.c DT RAMDisk writing (3330-3370) ====="
sed -n '3330,3375p' $K/xnuloader/loader.c
echo "===== 4. loader.c resident/rd1 setup (2960-3060) ====="
sed -n '2960,3060p' $K/xnuloader/loader.c
