#!/bin/bash
cd /home/HOST-REDACTED/hakios/kernel
git stash push -q tools/provenance.allow
python3 tools/provenance-check.py 2>&1 | tail -3
git stash pop -q
echo "--- restored:"; grep -c phk110 tools/provenance.allow
