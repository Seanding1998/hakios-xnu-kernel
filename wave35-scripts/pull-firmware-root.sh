#!/bin/bash
# pull-firmware-root.sh -- PHK110 (OnePlus Ace 2, SM8475/cape) firmware extraction.
#
# Why the root variant is the main path here: F14 (docs/research/f14-sd778g-zendot-survey.md
# 4.1-B) found the upstream reference script needed root on one ROM because /vendor/firmware_mnt
# is a vfat mount owned by system with fmask=0337 and /vendor/firmware is not readable by the
# adb shell user either -- plain `adb pull` returns nothing although every file is present.
# ColorOS on PHK110 is expected to sit behind the same wall, so this script copies the
# firmware, under root (Magisk), into a world-readable staging directory in /data/local/tmp,
# pulls the staging directory over adb, and removes it again. Nothing on the phone is
# changed; every write is inside /data/local/tmp and removed at the end.
#
# Wave 35 status: written without a phone (Wave 34 holds the device while building v24).
#   --dry-run   prints the manifest and the exact staging/pull plan, touches nothing,
#               never calls adb -- safe to run anywhere; already self-tested on this host
#   (no flag)   the real pull; needs: phone in Android, adb authorized (wave16c WSL recipe:
#               ADB_SERVER_SOCKET=tcp:127.0.0.1:5037), Magisk root answering `su -c`
#
# Manifest (v0.5 scope: GPU + WiFi + audio; modem stays v0.7, haptic has no firmware here):
#   fw-gpu    <- /vendor/firmware/{a730_sqe.fw,gmu_gen70000.bin,a730_zap.*}
#              Names are the SM8475 set (vendor gpulist "qcom,adreno-gpu-gen7-4-0":
#              sqefw_name a730_sqe.fw, gmufw_name gmu_gen70000.bin, zap_name a730_zap;
#              same files confirmed on MIX Fold 2 / MIUI V14.0.15.0.TLRCNXM). ColorOS may
#              name them differently -- the phone-side step lists /vendor/firmware first
#              and reports what matched instead of failing silently.
#   fw-wifi   <- /vendor/firmware/wlan/ (whole directory; WCN6750 over PCIe/MHI, NOT wpss.*
#              -- this phone has no WPSS node, F14 2.3). The ath11k staging gate
#              (wave30-scripts/check-phk110-wifi-fw.py) wants WCN6750/hw1.0/{amss.bin,
#              m3.bin,board-2.bin}; the Android-side files are the qca6490-family vendor
#              set (BDF bdwlan.elf.<variant> candidates) and the mapping/renaming happens
#              host-side after the pull. The generic-default refusal clause stays: a
#              generic bdwlan.bin alone FAILS that gate; the device variant is mandatory.
#              MAC address: probe /vendor/persist/wlan/ (read-only) for the radio's
#              address file; the exact path is unverified until the first run [TODO-DEV].
#   fw-audio  <- /vendor/firmware_mnt/image/adsp.* (MDT + segments, TZ PAS image 1)
#
# Migration: the long-term home is devices/phk110/pull-firmware.sh in the WSL build tree
# (its current placeholder says exactly this: "write this script after the reference
# device's (devices/redwood/pull-firmware.sh)"). Copy this file there when the tree is
# writable; keep the fw-*/ output layout identical so userland/build.sh GPU=1 ADSP=1 picks
# the directories up unchanged.
set -eu

DRY_RUN=0
for a in "$@"; do
	case "$a" in
	--dry-run) DRY_RUN=1 ;;
	*) echo "pull-firmware-root.sh: unknown argument $a (only --dry-run)" >&2; exit 2 ;;
	esac
done

# Output layout lives next to this script unless told otherwise.
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${WAVE35_FW_OUT:-$HERE/fw-stage}"
STAGE=/data/local/tmp/fw-phk110

GPU_FILES="/vendor/firmware/a730_sqe.fw /vendor/firmware/gmu_gen70000.bin /vendor/firmware/a730_zap.mdt /vendor/firmware/a730_zap.b01 /vendor/firmware/a730_zap.b02"
GPU_GLOB="/vendor/firmware/a730_zap.*"
WIFI_DIRS="/vendor/firmware/wlan"
AUDIO_GLOB="/vendor/firmware_mnt/image/adsp.*"
MAC_PROBE="/vendor/persist/wlan/mac.bin /vendor/persist/wlan/mac.addr /vendor/persist/wlan_bd/mac.bin"

if [ "$DRY_RUN" = 1 ]; then
	echo "== pull-firmware-root.sh --dry-run (no adb, no phone, nothing written)"
	echo "output dir      : $OUT (real run leaves fw-gpu/ fw-wifi/ fw-audio/ under it;"
	echo "staging on phone: $STAGE (created under root, removed after pull)"
	echo
	echo "manifest:"
	echo "  fw-gpu   fixed files : $GPU_FILES"
	echo "  fw-gpu   glob        : $GPU_GLOB"
	echo "  fw-wifi  directories : $WIFI_DIRS (copied whole; BDF variant discipline"
	echo "                          enforced later by check-phk110-wifi-fw.py -- a generic"
	echo "                          bdwlan.bin alone is refused there)"
	echo "  fw-wifi  mac probe   : $MAC_PROBE [TODO-DEV: real path unverified]"
	echo "  fw-audio  glob       : $AUDIO_GLOB"
	echo "  (not pulled: modem.* + image/ -> v0.7; haptic -> PM8350B has no firmware file;"
	echo "   camera -> v1.0+; vendor DTB -> already on disk from Wave 1)"
	echo
	echo "real-run sequence:"
	echo "  1. adb get-state                      (phone in Android, adb authorized)"
	echo "  2. su -c: list /vendor/firmware       (report actual a730*/gmu* names first;"
	echo "     ColorOS naming may differ from the SM8475 set above [TODO-DEV])"
	echo "  3. su -c: rm -rf $STAGE; mkdir -p \$STAGE/{gpu,wifi,audio};"
	echo "     cp the files above into it; chmod -R a+rX \$STAGE"
	echo "  4. adb pull $STAGE -> \$OUT/fw-stage (then unpacked into fw-gpu/ fw-wifi/ fw-audio/)"
	echo "  5. mv into fw-gpu/ fw-wifi/ fw-audio/; su -c: rm -rf $STAGE"
	echo "  6. per-directory file-count report (upstream acceptance format)"
	echo
	echo "host-side follow-ups after a real pull:"
	echo "  - sha256sum every file; register fw-wifi BDF + gpu blobs in the check gates"
	echo "  - run wave30-scripts/check-phk110-wifi-fw.py against the staged WCN6750/hw1.0 set"
	echo "  - fw-gpu/ goes into the payload small image (userland/build.sh GPU=1);"
	echo "    fw-audio/ into ADSP=1 or the system volume /fw later"
	exit 0
fi

# ---- real run (needs phone + adb + root) ------------------------------------------------
cd "$HERE"
adb get-state >/dev/null

# Step 2: report what the phone actually has before copying anything.
echo "pull-firmware-root.sh: /vendor/firmware GPU candidates on the phone:"
adb shell "su -c 'ls /vendor/firmware'" | grep -i "a730\|a7xx\|gmu\|zap\|sqe" || \
	echo "  (none matched a730/gmu/zap/sqe -- report above decides the GPU list)" >&2
echo "pull-firmware-root.sh: /vendor/firmware/wlan:"
adb shell "su -c 'ls /vendor/firmware/wlan'" || echo "  (no /vendor/firmware/wlan)" >&2

# Step 3: root-side staging. (Wave 36 fix: the original nested su -c sh -c quoting
# died on the phone with "/system/bin/sh: no closing quote"; a flat one-liner with
# host-side expansion only has no quote nesting and ran clean.)
adb shell "su -c 'rm -rf /data/local/tmp/fw-phk110; mkdir -p /data/local/tmp/fw-phk110/gpu /data/local/tmp/fw-phk110/wifi /data/local/tmp/fw-phk110/audio; cp /vendor/firmware/a730_sqe.fw /vendor/firmware/gmu_gen70000.bin /data/local/tmp/fw-phk110/gpu/ 2>/dev/null; cp /vendor/firmware/a730_zap.* /data/local/tmp/fw-phk110/gpu/ 2>/dev/null; cp -r /vendor/firmware/wlan /data/local/tmp/fw-phk110/wifi/ 2>/dev/null; cp /vendor/firmware_mnt/image/adsp.* /data/local/tmp/fw-phk110/audio/ 2>/dev/null; chmod -R a+rX /data/local/tmp/fw-phk110'"

# Step 4: pull, unpack, clean both sides.
rm -rf "$OUT"
mkdir -p "$OUT"
( cd "$OUT" && MSYS_NO_PATHCONV=1 adb pull "$STAGE" fw-stage >/dev/null )
MSYS_NO_PATHCONV=1 adb shell "su -c 'rm -rf $STAGE'"

rm -rf "$OUT/fw-gpu" "$OUT/fw-wifi" "$OUT/fw-audio"
mv "$OUT/fw-stage/gpu"   "$OUT/fw-gpu"
mv "$OUT/fw-stage/wifi"  "$OUT/fw-wifi"
mv "$OUT/fw-stage/audio" "$OUT/fw-audio"
rm -rf "$OUT/fw-stage"

# Step 6: acceptance report, upstream format.
for d in fw-gpu fw-wifi fw-wifi/wlan fw-audio; do
	[ -d "$OUT/$d" ] && echo "pull-firmware-root.sh: $d: $(ls -1 "$OUT/$d" | wc -l | tr -d ' ') files"
done
echo "pull-firmware-root.sh: done. Next: sha256sum everything; run"
echo "  python3 ../../wave30-scripts/check-phk110-wifi-fw.py --dir $OUT/fw-phk110"
echo "(rename/re-map the wlan files into WCN6750/hw1.0/ first; the gate refuses a generic"
echo " bdwlan.bin without the device board-2.bin)."
