#!/usr/bin/env bash
# Wave 44 - third-party cross-check against Linux (official tags, fetched through the proxy).
# Only grep excerpts are archived (wave44-scripts/evidence/linux-crosscheck.txt); the GPL source files
# stay in a scratch directory under /tmp and are never copied into this repository or into kernel/.
set -u
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
D=/tmp/wave44-linux   # tmpfs: gone when the WSL distro is recycled, so every run fetches again
mkdir -p "$D"
for tag in v6.12 master; do
  f="$D/a6xx_gpu.$tag.c"
  [ -s "$f" ] || curl -fsSL "https://raw.githubusercontent.com/torvalds/linux/$tag/drivers/gpu/drm/msm/adreno/a6xx_gpu.c" -o "$f"
  echo "##### $tag: $(wc -l < "$f") lines, sha256 $(sha256sum "$f" | cut -c1-16)"
  echo "--- a7xx_cp_init"
  n=$(grep -n '^static int a7xx_cp_init' "$f" | cut -d: -f1)
  sed -n "${n},$((n+62))p" "$f" | grep -n -E 'CP_THREAD_CONTROL|CP_ME_INIT|mask|OUT_RING|pwrup' | sed "s/^/  +/"
  echo "--- a6xx_cp_init (the sixth generation's, for contrast)"
  n=$(grep -n '^static int a6xx_cp_init' "$f" | cut -d: -f1)
  sed -n "${n},$((n+26))p" "$f" | grep -n -E 'CP_ME_INIT|OUT_RING' | sed "s/^/  +/"
  echo "--- GRAS_NC_MODE_CNTL / aperture in a6xx_set_ubwc_config"
  grep -n 'GRAS_NC_MODE_CNTL\|CP_APERTURE_CNTL_HOST\|PIPE_BV\|PIPE_BR' "$f" | head -20
  echo "--- a7xx_submit fence words"
  grep -n 'CACHE_CLEAN\|CP_WAIT_TIMESTAMP\|CP_SET_THREAD_\|IFPC\|CCU_INVALIDATE' "$f" | head -40
  echo "--- hang check: BV registers read by a6xx_progress?"
  grep -n 'a6xx_progress\|CP_BV_\|REG_A7XX_CP_BV' "$f" | head -20
done
# UBWC platform data: which swizzle / bank bit / macrotile mainline gives the SM8450 family (SM8475 is its
# refresh) and SM8550, and that the encoder version is a field of its own.
u="$D/ubwc_config.master.c"
[ -s "$u" ] || curl -fsSL "https://raw.githubusercontent.com/torvalds/linux/master/drivers/soc/qcom/ubwc_config.c" -o "$u"
echo "##### ubwc_config.c master: $(wc -l < "$u") lines, sha256 $(sha256sum "$u" | cut -c1-16)"
echo "--- the structure the SM8450 family and SM8550 share, and who points at it"
grep -n -A7 'ubwc_4_0_hbb16 = {' "$u"
grep -n -E '"qcom,sm84[0-9]+"|"qcom,sm85[0-9]+"' "$u"
echo "--- every other field name the file knows (one line each)"
grep -n -o -E '\.(ubwc_[a-z_]+|highest_bank_bit|macrotile_mode)' "$u" | sed 's/^[0-9]*://' | sort | uniq -c
# How swizzle and macrotile follow from the encoder version alone is in include/linux/soc/qcom/ubwc.h:
# see 04-ubwc-helpers.sh (fetched through gh api; the raw host rate-limits repeated fetches with 429).
