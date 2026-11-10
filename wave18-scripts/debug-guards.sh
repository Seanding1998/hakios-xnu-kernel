#!/bin/bash
cd ~/hakios/kernel/userland || exit 1
source ../xnu-env.sh
DARWIN=../sysimage
CACHE=$DARWIN/20F66__iPhone10,3_6
echo "CACHE=$CACHE -> $(readlink -f "$CACHE")"
[ -f "$CACHE/dyld_shared_cache_arm64" ] && echo "guard CACHE: OK" || echo "guard CACHE: FAIL"
[ -f "$DARWIN/system.manifest" ] && echo "guard manifest: OK" || echo "guard manifest: FAIL"
# replay build.sh's own environment the way my runner invoked it
env RC_JOBS=rc.jobs.ssh FLASHBOOT=1 CRYPTEXES=flash bash -c 'echo "inside bash: FLASHBOOT=[$FLASHBOOT] CRYPTEXES=[$CRYPTEXES] RC_JOBS=[$RC_JOBS]"'
# and the two full guards as build.sh writes them
if [ -n "$FLASHBOOT" ] && [ -f $CACHE/dyld_shared_cache_arm64 ]; then echo "flashboot guard: would RUN"; else echo "flashboot guard: skip"; fi
if [ -f $DARWIN/system.manifest ] && [ -f $CACHE/dyld_shared_cache_arm64 ]; then echo "system guard first half: OK"; else echo "system guard first half: FAIL"; fi
ls -la system.apfs flashboot.apfs root.apfs 2>&1
