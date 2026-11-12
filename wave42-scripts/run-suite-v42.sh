#!/bin/bash
# Wave 42: re-run the full GEN test chain on the FINAL (v42-fixed) loader source.
# usb-harness: 49 USB cases (TD1-TD7 + all prior-generation regressions, incl. the
# review's nine counterexamples). mirror-harness: 22 mirror-segment cases.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
OUT=$R/wave42-scripts
rm -rf /tmp/w42suite && mkdir -p /tmp/w42suite
cd ~/hakios/kernel/xnuloader

echo "== md5 of the source under test =="
md5sum loader.c

echo "== usb-harness: generate =="
python3 "$R/wave38-scripts/usb-harness.py" loader.c /tmp/w42suite/usb-test.c
echo "== usb-harness: build (gcc -O0) =="
gcc -O0 -o /tmp/w42suite/usb-test /tmp/w42suite/usb-test.c
echo "== usb-harness: run =="
/tmp/w42suite/usb-test | tee "$OUT/usb-suite-results-v42.txt"
