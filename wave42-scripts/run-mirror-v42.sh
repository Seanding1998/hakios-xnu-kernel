#!/bin/bash
# Wave 42: mirror-harness (22 cases) on the final source.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
rm -rf /tmp/w42m && mkdir -p /tmp/w42m
cd ~/hakios/kernel/xnuloader
python3 "$R/wave38-scripts/mirror-harness.py" loader.c /tmp/w42m/mirror-test.c
gcc -O0 -o /tmp/w42m/mirror-test /tmp/w42m/mirror-test.c
/tmp/w42m/mirror-test | tee "$R/wave42-scripts/mirror-suite-results-v42.txt" | tail -8
