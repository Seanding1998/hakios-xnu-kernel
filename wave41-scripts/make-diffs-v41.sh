#!/bin/bash
# Wave 41: record the patch diffs into wave41-scripts/diffs/.
set -e
R="/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave41-scripts"
mkdir -p "$R/diffs"
diff -u /home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c.v41-orig /home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c > "$R/diffs/hakios.adreno.c.v41.diff" || true
diff -u /home/cyrux/hakios/kernel/userland/src/gl_test.c.v41-orig /home/cyrux/hakios/kernel/userland/src/gl_test.c > "$R/diffs/gl_test.c.v41.diff" || true
wc -l "$R/diffs/"*.diff
sha256sum /home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c /home/cyrux/hakios/kernel/userland/src/gl_test.c
