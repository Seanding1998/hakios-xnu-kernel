#!/usr/bin/env python3
"""Gen 3 fix: usb_stale_wipe is defined below its first caller (the pump); a forward
declaration goes above usb_pump."""
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
old = "#define USB_PUMP_BUDGET 8"
assert src.count(old) == 1
src = src.replace(old, "#define USB_PUMP_BUDGET 8\n\nstatic void usb_stale_wipe(void);   /* the episode ledgers' shared wipe (defined below) */")
open(path, "w", encoding="utf-8", newline="").write(src)
print("forward declaration added")
