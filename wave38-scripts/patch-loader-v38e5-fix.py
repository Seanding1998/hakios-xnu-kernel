#!/usr/bin/env python3
"""Gen 3 fixes: (1) the failed-reply path lost its `usb_in_stale++` in the state-machine
rewrite -- the reader-death ledger never incremented and the gate never engaged; (2) a
Connected clears a lingering CANCELLING: after the bus reset the retired request's tail
is not coming -- waiting for it is pointless, and any late tail is swallowed as a stray."""
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()

old1 = """	/* the wait failed, or the reply came back short: count an unread/undelivered reply */
	if (usb_in_stale >= USB_IN_STALE_GATE) {"""
new1 = """	/* the wait failed, or the reply came back short: count an unread/undelivered reply */
	usb_in_stale++;
	if (usb_in_stale >= USB_IN_STALE_GATE) {"""
assert src.count(old1) == 1
src = src.replace(old1, new1)

old2 = """				usb_stale_wipe();
				if (usb_in_state == USB_REQ_SUBMITTED) {
					usb_in_state = USB_REQ_CANCELLING;
				}
				if (usb_out_state == USB_REQ_SUBMITTED) {
					usb_out_state = USB_REQ_CANCELLING;
				}
				usb_bus_resets++;
				usb_in_fault = 0;     /* a fresh bus: the faulted endpoint may try again */"""
new2 = """				usb_stale_wipe();
				if (usb_in_state == USB_REQ_SUBMITTED) {
					usb_in_state = USB_REQ_CANCELLING;    /* the reset retires it */
				} else if (usb_in_state == USB_REQ_CANCELLING) {
					usb_in_state = USB_REQ_IDLE;          /* after the reset the tail is not
					                                         coming: the waiters are gone, any
					                                         late tail lands as a stray */
				}
				if (usb_out_state == USB_REQ_SUBMITTED) {
					usb_out_state = USB_REQ_CANCELLING;
				} else if (usb_out_state == USB_REQ_CANCELLING) {
					usb_out_state = USB_REQ_IDLE;
				}
				usb_bus_resets++;
				usb_in_fault = 0;     /* a fresh bus: the faulted endpoint may try again */"""
assert src.count(old2) == 1
src = src.replace(old2, new2)
open(path, "w", encoding="utf-8", newline="").write(src)
print("gen-3 fixes applied (stale increment restored; Connected clears lingering CANCELLING)")
