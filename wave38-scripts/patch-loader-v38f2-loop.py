#!/usr/bin/env python3
"""Wave 38 fix generation 4, part 2: the service window's loop ordering (P1-1):
the window's own expiry is checked FIRST (a window about to end never starts a
recovery), the usb_ready check exists inside the loop (a failed recovery stops USB
for the window and falls to the window's own reset), and the recovery counter resets
per service window. The caller in efi_main resets it at the loop's start.

usage: patch-loader-v38f2-loop.py LOADER_C
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

sub(
"""static void
usb_command_loop(void)
{
	screen_quiet = 1;
	for (;;) {
		char cmd[128];
		int64_t n;

		/* (no gate on usb_connected here either: see usb_poll_command -- the host is there
		 * when it writes; a receive armed while it does not costs nothing) */
		n = usb_rx(usb_rx_buf, 511);
		if (n <= 0) {
			/* usb_wait has said -1 on the service window's end (and on a cable's change) */
			usb_pair_rebuild();     /* Wave 38: the zombie check -- before the window's own
			                           exit, so a dead pair gets its two rebuild chances */
			if (usb_service_secs != 0 && READ_SYSREG(CNTVCT_EL0) - usb_service_mark > usb_service_secs * READ_SYSREG(CNTFRQ_EL0)) {
				print("usb: the service window is over: reset\\n");
				reboot();
			}
			usb_wait_pumped(NULL, 50);   /* Wave 38: a quiet, pumped second before the next
			                                pass -- a refused receive must not spin this loop
			                                hot (each refused submit cost the vendor's wall
			                                lines; the spin was the flood's second face) */
			continue;
		}""",
"""static void
usb_command_loop(void)
{
	screen_quiet = 1;
	usb_pair_rebuilds = 0;              /* P1-1: the recovery budget is per service window */
	for (;;) {
		char cmd[128];
		int64_t n;

		/* P1-1: the window's own expiry is checked FIRST -- a window about to end
		 * never starts a recovery; and a failed recovery (usb_ready == 0) stops USB
		 * for this window, falling back to the window's own reset. */
		if (usb_service_secs != 0 && READ_SYSREG(CNTVCT_EL0) - usb_service_mark > usb_service_secs * READ_SYSREG(CNTFRQ_EL0)) {
			print("usb: the service window is over: reset\\n");
			reboot();
		}
		if (!usb_ready) {
			usb_wait_pumped(NULL, 50);   /* USB is down after a failed recovery: keep the
			                                window's clock and the watchdog running, touch
			                                nothing else, and let the window expire */
			continue;
		}
		/* (no gate on usb_connected here either: see usb_poll_command -- the host is there
		 * when it writes; a receive armed while it does not costs nothing) */
		n = usb_rx(usb_rx_buf, 511);
		if (n <= 0) {
			/* usb_wait has said -1 on a cable's change, on a refused receive, or on an
			 * abandoned reply -- not necessarily on the window's end (that check is at
			 * the loop's top now) */
			usb_pair_rebuild();     /* Wave 38: the bounded-recovery check */
			usb_wait_pumped(NULL, 50);   /* a quiet, pumped second before the next pass --
			                                a refused receive must not spin this loop hot
			                                (each refused submit cost the vendor's wall
			                                lines; the spin was the flood's second face) */
			continue;
		}""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-3/P1-1 part 2 applied (loop ordering)")
