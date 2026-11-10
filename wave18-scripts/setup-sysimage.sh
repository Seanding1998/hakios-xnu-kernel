#!/bin/bash
# Wave 18 v13: set up ~/hakios/sysimage (the layout build.sh expects, DARWIN=../sysimage)
# as hardlink copies of the wave14 extraction (sysimage-20F66/work). Never edits the original.
set -e
SRC=~/hakios/sysimage-20F66/work
DST=~/hakios/sysimage
[ -e "$DST" ] && { echo "sysimage already exists:"; ls "$DST"; exit 0; }
mkdir -p "$DST"
# directories: hardlink copies (build.sh renames/unlinks inside the copy only)
for d in rootfs cryptex cryptex-app "20F66__iPhone10,3_6"; do
  cp -al "$SRC/$d" "$DST/"
done
# files: real copies (small)
for f in system.files system.manifest var.skel .done-rootfs .done-cryptex .done-cryptex-app; do
  cp -a "$SRC/$f" "$DST/"
done
# big dmg artifacts: symlinks (build.sh does not read cryptex-os.dmg; it is our flash input)
for f in rootfs.dmg rootfs.slt cryptex-os.dmg cryptex-app.dmg; do
  ln -s "$SRC/$f" "$DST/"
done
echo "--- sysimage ready:"
ls -la "$DST"
echo "--- cache check:"
ls "$DST/20F66__iPhone10,3_6/" | head -5
