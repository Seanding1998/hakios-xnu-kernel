#!/bin/bash
set -e
S=~/hakios/kernel/sysimage
# the wave14 scripts already live here; my hardlink copy landed as $S/sysimage — merge one level up
for d in rootfs cryptex cryptex-app "20F66__iPhone10,3_6"; do
  [ -e "$S/$d" ] && { echo "SKIP $d (already there)"; continue; }
  mv "$S/sysimage/$d" "$S/"
done
for f in system.files system.manifest var.skel .done-rootfs .done-cryptex .done-cryptex-app; do
  [ -e "$S/$f" ] && { echo "SKIP $f"; continue; }
  mv "$S/sysimage/$f" "$S/"
done
for f in rootfs.dmg rootfs.slt cryptex-os.dmg cryptex-app.dmg; do
  [ -e "$S/$f" ] || mv "$S/sysimage/$f" "$S/"
done
rmdir "$S/sysimage" && echo "nested dir removed"
echo "--- now:"
ls "$S"
[ -f "$S/20F66__iPhone10,3_6/dyld_shared_cache_arm64" ] && echo CACHE-OK
[ -f "$S/system.manifest" ] && echo MANIFEST-OK
[ -d "$S/rootfs" ] && echo ROOTFS-OK
