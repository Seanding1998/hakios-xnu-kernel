#!/usr/bin/env python3
"""Wave 12b fix B (the one-liner from wave12a report section 4): hakios.s3910.c
L787, v1_read's first read, calls geni_transfer directly instead of going
through the spi_xfer pointer -- so the bitbang fallback never answered the
v1 probe window (every round burned ~1.47 s of engine timeout on the
FIFO-disabled engine, 50 rounds > 60 s session, no verdict line).

Root cause of how this survived v10's own fix: fix5-v10.py step 3 tried to
replace 'return geni_transfer(NULL, buf, V1_MIN_READ);' but the source reads
'if (!geni_transfer(NULL, buf, V1_MIN_READ)) {' -- str.replace mismatches
silently. This script asserts counts, so a mismatch fails loudly.

After the fix v1_read goes v1_read -> spi_xfer -> bitbang_transfer ->
TLMM GPIO 16-19 whenever the engine path is refused (PHK110: FIFO interface
disabled by the SE firmware), which is the whole point of the fallback.

usage: fix1-spi-xfer.py SOURCE_FILE
"""
import sys

p = sys.argv[1]
s = open(p).read()

old = '''	if (!geni_transfer(NULL, buf, V1_MIN_READ)) {
		return false;
	}'''
new = '''	if (!spi_xfer(NULL, buf, V1_MIN_READ)) {
		return false;
	}'''

assert s.count(old) == 1, f'pre: the bad line appears {s.count(old)} times, not 1'
assert s.count(new) == 0, 'post candidate already present?'
s = s.replace(old, new, 1)
open(p, 'w').write(s)

# the only geni_transfer references left must be its definition and the
# engine-path assignment in bring_up
left = [i + 1 for i, line in enumerate(s.splitlines()) if 'geni_transfer' in line]
assert left == [542, 1439], f'unexpected geni_transfer references at lines {left}'
print(f'{p}: L787 geni_transfer -> spi_xfer written; geni_transfer now only at {left}')
