#!/usr/bin/env python3
"""Gen 3 fix: the pump's Disconnected branch flipped only the OUT state; the IN request
must flip to CANCELLING too (the vendor retires it with the bus)."""
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
old = """				if (usb_out_state == USB_REQ_SUBMITTED) {
					usb_out_state = USB_REQ_CANCELLING;   /* P0-1: the vendor retires it; the cleanup drains */
				}"""
assert src.count(old) == 1
src = src.replace(old, old + """
				if (usb_in_state == USB_REQ_SUBMITTED) {
					usb_in_state = USB_REQ_CANCELLING;    /* P0-1: the reply's tail is owed too */
				}""")
open(path, "w", encoding="utf-8", newline="").write(src)
print("Disconnected IN flip added")
