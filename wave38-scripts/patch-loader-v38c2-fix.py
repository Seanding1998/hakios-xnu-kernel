#!/usr/bin/env python3
"""Wave 38 generation 2, fix round: three defects the isolation harness caught in the
P0-4+P1-5 code as first written.

  1. wall_line_take's non-wall path recorded the line but never passed it to the
     original writer -- the display passthrough was lost (T1).
  2. the budget's `wall_last_shown != 0` guard disabled the beat whenever the clock
     read zero, so every repeat showed its own aggregate at boot time (T3).
  3. the 0xB family's signature list missed the real vendor line "Failed to submit
     data transfer" (UsbDeviceSend's wrapping line, f12 §1) -- only UsbfnDwcTransfer's
     own "Failed to submit transfer" was listed (T2).

usage: patch-loader-v38c2-fix.py LOADER_C
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:200]}"
    src = src.replace(old, new)

# ---- fix 1 + the classifier's fourth slot ------------------------------------------------
sub(
"""	static const char *const sigs[WALL_FAMILIES][3] = {
		{ "SETUP_PENDING", "", "" },
		{ "0x8000000B", "no free URB nodes", "Failed to submit transfer" },
		{ "0x8000000C", "not configured", "" },
	};
	uint64_t f, k, m, scan;

	for (f = 0; f < WALL_FAMILIES; f++) {
		for (k = 0; k < 3 && sigs[f][k][0] != 0; k++) {""",
"""	static const char *const sigs[WALL_FAMILIES][4] = {
		{ "SETUP_PENDING", "", "", "" },
		{ "0x8000000B", "no free URB nodes", "Failed to submit data transfer", "Failed to submit transfer" },
		{ "0x8000000C", "not configured", "", "" },
	};
	uint64_t f, k, m, scan;

	for (f = 0; f < WALL_FAMILIES; f++) {
		for (k = 0; k < 4 && sigs[f][k][0] != 0; k++) {""")

# ---- fix 2: the beat guard must not vanish at a zero clock --------------------------------
sub(
"""	wall_family_count[family]++;
	now = READ_SYSREG(CNTVCT_EL0);
	if (wall_last_shown != 0 && now - wall_last_shown < WALL_BUDGET_BEAT) {
		wall_budget_suppressed++;   /* inside the shared beat: counted, not shown */
		return;
	}""",
"""	wall_family_count[family]++;
	now = READ_SYSREG(CNTVCT_EL0);
	if (now - wall_last_shown < WALL_BUDGET_BEAT) {
		wall_budget_suppressed++;   /* inside the shared beat: counted, not shown */
		return;
	}""")

# ---- fix 3: the non-wall passthrough keeps its display ------------------------------------
sub(
"""	if (family < 0) {
		mirror_take(line, n);     /* a vendor line, but not a wall line: record as before */
		return;
	}""",
"""	if (family < 0) {
		/* a vendor line, but not a wall line: record AND display as before */
		mirror_take(line, n);
		if (shim_write_orig != NULL) {
			shim_write_orig(line, n);
		}
		return;
	}""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: the three harness-caught defects fixed")
