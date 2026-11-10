#!/bin/bash
K=~/hakios/kernel
echo "===== init.c base resolution ====="
grep -n "base" $K/userland/src/init.c | grep -v "^\s*\*" | head -20
echo "===== build.sh flashboot section (511-596) ====="
sed -n '511,596p' $K/userland/build.sh
echo "===== build.sh root/ dir: sbin, private/var, launchd ====="
grep -n "root/sbin\|sbin/launchd\|sbin/init\|mkdir -p root\|root/private" $K/userland/build.sh | head -25
