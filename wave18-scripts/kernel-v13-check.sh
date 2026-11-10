#!/bin/bash
set -e
cd ~/hakios/kernel
echo "--- kernel rebuild after config (+ROOT_APFS/VAR_HFS):"
timeout 570 make kernel > /tmp/kernel-v13.log 2>&1 || true
tail -2 /tmp/kernel-v13.log
sha256sum hakios-kernel
echo "--- v11 kernel on Windows:"
sha256sum HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/hakios-kernel-v11.bin
