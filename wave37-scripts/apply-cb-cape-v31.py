#!/usr/bin/env python3
"""Wave 37 (v31): step 5 stops writing the cb clock -- cape has none.

Evidence: gpucc-waipio.c (the vendor driver bound to this phone's "qcom,cape-gpucc") carries NO
gpu_cc_cb_clk branch -- grep over its whole clock list finds none; the cape debug mux selection
table has no cb clock either. The sc7280 reference kept gpu_cc_cb_clk "on always" at gpucc+0x1170,
but on this phone 0x3d91170 belongs to no known clock (the cape branches all live in the 0x90xx/
0x93xx/0x7000 range), so clock_on() would set a bit of an unidentified register. Everything else
step 5 touches is cape-anchored (verified by the v28/v30 generations' reads).

The step-3 READ of the same offset stays (it decodes inside the map and its value is information:
v30 read "gpucc cb (0x3d91170) = 0"). Only the WRITE is removed.

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

OLD = """	if (!clock_on(&gpucc, "cb", GPUCC_CB_CBCR, false) ||
	    !clock_on(&gpucc, "cxo", GPUCC_CXO_CBCR, true) ||"""
NEW = """	/* cape has no cb clock: gpucc-waipio.c (the vendor driver of this phone's controller) carries
	 * no such branch, so gpucc+0x1170 names no known clock here and the write stays out; the
	 * sc7280 reference merely kept that clock always on */
	if (!clock_on(&gpucc, "cxo", GPUCC_CXO_CBCR, true) ||"""

n = src.count(OLD)
if n != 1:
    sys.exit(f"anchor not exactly once ({n})")
src = src.replace(OLD, NEW)
open(PATH, "w").write(src)
print("applied: the cb write is out of step 5 (cape-native)")
