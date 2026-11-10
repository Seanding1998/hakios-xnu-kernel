#!/bin/bash
# Wave 18 v13: the real-init userland build (wave19-prep Q2 step 2).
# FLASHBOOT=1 CRYPTEXES=flash: flashboot.apfs (boot volume alone, md0 resident)
# + root.apfs (md1) + system.apfs (the Darwin root volume for the darwin front).
# RC_JOBS=rc.jobs.ssh wired per the wake-up order (sshd itself stays absent until
# the Procursus /jb lands in a later wave: no ../jb in the tree, the 155 MB prefix
# does not fit the payload's 64 MB window).
set -e
cd ~/hakios/kernel/userland
RC_JOBS=rc.jobs.ssh FLASHBOOT=1 CRYPTEXES=flash bash build.sh 2>&1
echo "=== artifacts ==="
ls -la root.apfs flashboot.apfs system.apfs 2>/dev/null || true
