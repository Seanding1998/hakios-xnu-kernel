#!/bin/bash
K=/home/HOST-REDACTED/hakios/kernel
S=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave3-scripts
python3 -m py_compile "$K/mkxnuimg.py" && echo "py_compile OK"
cp "$S/mkxnuimg-orig.py" "$K/mkxnuimg-orig.py"
cd "$K"
echo "--- ORIG (no MU tree, no prebuilt):"
python3 mkxnuimg-orig.py; echo "orig exit=$?"
echo "--- NEW default (same inputs):"
python3 mkxnuimg.py; echo "new-default exit=$?"
echo "--- NEW --device phk110 (no MU tree):"
python3 mkxnuimg.py --device phk110 --fd-base 0xA7100000 --fd-size 0x300000 --payload-base 0xC0000000; echo "new-phk110 exit=$?"
echo "--- NEW --help (first lines):"
python3 mkxnuimg.py --help | head -6
rm -f "$K/mkxnuimg-orig.py" "$K/mkxnuimg-orig.pyc" 2>/dev/null
find "$K/__pycache__" -delete 2>/dev/null
echo done
