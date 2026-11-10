#!/usr/bin/env python3
"""Reverse the first v16c application (to re-apply the updated hunks)."""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"reverse hunk not unique (found {n}x)"
    src = src.replace(old, new)

# reverse hunk 1: remove the wake helper (from its comment to the boot-time comment start)
i = src.find("/* Wave 21.2's endpoint wall (v16b' on device):")
j = src.find("/* The boot-time bring-up. Wave 21.1: the first start_ex has been losing a race to the")
assert i >= 0 and j > i, "v16c block boundaries not found"
src = src[:i] + src[j:]

# reverse hunk 2: remove the wake call
sub(
"""	usb_dwc3_wake();          /* warm-boot DWC3: SUSPHY off + core soft reset before the bring-up */
	/* the settle window:""",
"""	/* the settle window:""")

# reverse hunk 3: remove the post-success SUSPHY clear (tolerate absence)
orphan = """		usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */\n"""
if orphan in src:
    src = src.replace(orphan, "")
    print("orphaned hunk-3 line removed")

assert "usb_dwc3_wake" not in src
assert "usb_dwc3_susphy_off" not in src
open(path, "w", encoding="utf-8", newline="").write(src)
print("reversed v16c hunks in", path)
