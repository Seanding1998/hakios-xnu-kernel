#!/usr/bin/env bash
# Wave 44 - clone the UniXNU GPU repos into the reference directory (WSL side).
# Read-only reference material: nothing here is built, executed or copied into kernel/.
# Each repo gets its own new directory under /home/cyrux/hakios/refs/. No submodule recursion.
set -u
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
REFS=/home/cyrux/hakios/refs
# GPU driver + its kits + the Metal userland + the framework, then the board and SoC kit that hold hw_init and the GMU cold start
REPOS="Adreno740 AdrenoPM4 AdrenoFirmware AirNir AdrenoMetal UniXNU UniXNU-sheng UniXNU-sm8550-common"
for r in $REPOS; do
  d="$REFS/UniXNU-$r"
  if [ -e "$d" ]; then echo "SKIP $d (exists)"; continue; fi
  git clone --no-recurse-submodules "https://github.com/UniXNU/$r.git" "$d" 2>&1 | tail -2
  chown -R cyrux:cyrux "$d"
done
echo "=== clone ledger ==="
for r in $REPOS; do
  d="$REFS/UniXNU-$r"
  # The directories are owned by cyrux (same as the sibling refs). git runs as the owner, so
  # no safe.directory entry has to be added to anybody's git config.
  g() { runuser -u cyrux -- git -C "$d" "$@"; }
  printf '%s\t%s\t%s\t%s\n' "$r" "$(g rev-parse HEAD)" "$(g log -1 --format=%cI)" "$(g rev-list --count HEAD) commits"
done
