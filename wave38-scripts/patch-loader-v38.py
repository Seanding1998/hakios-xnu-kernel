#!/usr/bin/env python3
"""Wave 38 patch: the USB pair's self-heal (wave34 §5's design items ①+③ implemented,
②'s loader-side minimal equivalent) -- no-consumer-no-queue + stale-TRB drain + gated
prints + the service window's whole-pair rebuild.

The settled mechanism (wave31 x2, wave36 round 3, user photos, wave34 §5, f12): during
the Darwin session / service window a reply is queued on the bulk-IN pair (phys[3]) with
nobody reading -- the TRB ring fills, every later submit answers the vendor's own debug
lines (0x8000000B, straight onto the framebuffer through FrameBufferSerialPortLib), and
at the conversion-point teardown the pair's state bytes land at zero (0x8000000C) --
bulk pair dead, ep0 alive alone: the zombie. This patch names the loader's own two feeds
of that wall and closes both:

  1. The reply side (usb_tx): a wait that gives up left the transfer standing (the 3 s
     session bound returned -1 without touching the controller) -- every later reply
     queued one more TRB into a ring nobody drains. Now: one IN transfer stands at a
     time; a given-up wait takes the transfer back out (abort_xfer = the pair's own
     END_TRANSFER, the stale TRB retires); from three unread replies the IN gate holds
     reply submits through a doubling backoff (cap 30 s), one probe per beat -- no
     submit, no vendor print. The gate lifts when the host reads a reply again or at the
     next enumeration.
  2. The receive side in the service window (usb_rx via usb_command_loop): the loop's
     own submits were ungated -- with the pair refused the loop spun per pass, and every
     refused submit answered the vendor's four debug lines (the flood's second face; the
     window-expiry exit in usb_wait was unreachable because the submit failed before the
     wait -- the wall printed forever). Now: the receive's submits go through the same
     wall gate the arm path beats, and the loop takes a quiet pumped second between
     passes. The window can now expire; the phone carries on.
  3. The service window's whole-pair rebuild (usb_pair_rebuild): when both halves agree
     the pair is dead (the reply gate up AND the receive at the wall), the pair's own
     END_TRANSFERs go out (abort_xfer on both endpoints) and the whole bring-up is thrown
     again the start_ex way (the vendor's start_ex stops the controller itself; the next
     enumeration's SET_CONFIG walk re-arms the bulk pair) -- the loader-side minimal
     equivalent of wave34 §5's item ②. Twice at most, a minute apart, never during a
     session (a start_ex resets the DWC3 -- the tunnel would die).
  4. usb_wait's reply side never waits past ten seconds anywhere (an unread reply used
     to sit the whole 240 s service window out).

usage: patch-loader-v38.py LOADER_C
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

# ---- hunk 1: the reply side's ledger (declarations) -----------------------------------------
sub(
"""static uint64_t usb_tx_done, usb_tx_err;
static uint64_t usb_t0;          /* the session's monotonic timeline (CNTVCT at usb_start) */
""",
"""static uint64_t usb_tx_done, usb_tx_err;
/* Wave 38: the reply side's ledger. The user-facing wall (0xB first, 0xC after the
 * teardown -- wave31 x2 + wave36 round 3) is fed by our own submits: a reply queued on
 * the IN pair with nobody reading stays armed forever, the TRB ring fills, and every
 * later submit answers the vendor's own debug lines (0x8000000B -- the ring's URB nodes
 * are gone), painted straight onto the framebuffer. The ledger: usb_in_expect -- one IN
 * transfer stands; completions for transfers nothing waits on are the abandoned ones'
 * tails and are swallowed (usb_in_stray). usb_in_stale counts the replies we took back
 * out unread; from USB_IN_STALE_GATE the gate holds reply submits off through a doubling
 * backoff (cap 30 s) with one probe per beat: no submit, no vendor print -- the flood
 * stops at the source. */
static int usb_in_expect;        /* an IN transfer stands with the controller */
static uint64_t usb_in_stray;    /* completions for transfers nobody waits on any more */
static uint64_t usb_in_stale;    /* replies taken back out unread (the reader was gone) */
static uint64_t usb_in_ok;       /* replies the host actually took */
static uint64_t usb_in_refused;  /* submits the IN gate itself turned away */
static uint64_t usb_in_gate_next, usb_in_gate_backoff;
#define USB_IN_STALE_GATE 3      /* unread replies before the gate comes up */
static uint64_t usb_t0;          /* the session's monotonic timeline (CNTVCT at usb_start) */
""")

# ---- hunk 2: a fresh enumeration lifts the gate ---------------------------------------------
sub(
"""			if (data.device_state == UsbDeviceStateConnected) {
				usb_state_conn++;
				usb_connected = 1;
				if (!usb_host_seen) {
""",
"""			if (data.device_state == UsbDeviceStateConnected) {
				usb_state_conn++;
				usb_connected = 1;
				/* Wave 38: a fresh enumeration is a fresh reader: the reply gate lifts and
				 * the stale ledger closes (the bus reset retired whatever stood). */
				usb_in_expect = 0;
				usb_in_stale = 0;
				usb_in_gate_next = 0;
				if (!usb_host_seen) {
""")

# ---- hunk 3: the pump swallows an abandoned reply's completion -------------------------------
sub(
"""			} else {
				usb_done_in.live = 1;
				usb_done_in.status = data.transfer.status;
				usb_done_in.bytes = data.transfer.bytes_completed;
				if (ok) {
					usb_tx_done++;
				} else {
					usb_tx_err++;
				}
			}
""",
"""			} else if (!usb_in_expect) {
				/* Wave 38: a completion for a transfer nothing waits on -- the tail of a
				 * reply we took back out. Swallowed: it must never answer a later wait. */
				usb_in_stray++;
			} else {
				usb_done_in.live = 1;
				usb_done_in.status = data.transfer.status;
				usb_done_in.bytes = data.transfer.bytes_completed;
				if (ok) {
					usb_tx_done++;
				} else {
					usb_tx_err++;
				}
			}
""")

# ---- hunk 4: usb_wait -- the reply side never waits past ten seconds ------------------------
sub(
"""		/* with a kernel running, a host that went away must not keep this core from watching it */
		if (run_active && READ_SYSREG(CNTVCT_EL0) - began > 3 * freq) {
			return -1;
		}
""",
"""		/* with a kernel running, a host that went away must not keep this core from watching it */
		if (run_active && READ_SYSREG(CNTVCT_EL0) - began > 3 * freq) {
			return -1;
		}
		/* Wave 38: the reply side never waits past ten seconds anywhere -- a reply the host
		 * has not taken in ten is not coming (the reader is gone); the wait gives up and
		 * usb_tx takes the transfer back out. Without this an unread reply sat the whole
		 * service window out (240 s of a deaf loop), the deaf-window shape of wave31/36. */
		if (endpoint == USB_EP_IN && READ_SYSREG(CNTVCT_EL0) - began > 10 * freq) {
			return -1;
		}
""")

# ---- hunk 5: usb_rx -- the receive's own submits go through the wall gate --------------------
sub(
"""static int64_t
usb_rx(uint8_t *buf, uint64_t len)
{
	if (usb_rx_queued) {
		usb_rx_queued = 0;      /* (every command is received the same way, into the same buffer) */
	} else if (EFI_ERROR(USB->send(USB_EP_OUT, len, buf))) {
		return -1;
	}
	return usb_wait(USB_EP_OUT);
}
""",
"""static int64_t
usb_rx(uint8_t *buf, uint64_t len)
{
	if (usb_rx_queued) {
		usb_rx_queued = 0;      /* (every command is received the same way, into the same buffer) */
	} else if (gate_next != 0 && READ_SYSREG(CNTVCT_EL0) < gate_next) {
		return -1;      /* Wave 38: the wall gate covers the receive's own submits too -- the
		                   service window's loop used to re-submit per pass, and every refused
		                   submit answered the vendor's debug lines (the flood's second face;
		                   usb_arm_rx's path was already gated, this one was not) */
	} else {
		efi_status s = USB->send(USB_EP_OUT, len, buf);

		if (EFI_ERROR(s)) {
			usb_wall_gate((uint32_t)s);   /* the same gate the arm path beats: refuse, count, back off */
			return -1;
		}
	}
	return usb_wait(USB_EP_OUT);
}
""")

# ---- hunk 6: usb_tx -- one IN transfer at a time, the drain, the gate ------------------------
sub(
"""static int64_t
usb_tx(const uint8_t *data, uint64_t len)
{
	if (data != usb_tx_buf) {
		memcpy(usb_tx_buf, data, len);
	}
	if (EFI_ERROR(USB->send(USB_EP_IN, len, usb_tx_buf))) {
		return -1;
	}
	return usb_wait(USB_EP_IN);
}
""",
"""/* Wave 38: the reply's submit, behind the IN gate. One IN transfer stands at a time; a
 * wait that gives up takes the transfer back out (abort_xfer retires the stale TRB -- the
 * ring keeps its room) and counts an unread reply; from USB_IN_STALE_GATE the gate holds
 * further submits through a doubling backoff (cap 30 s), one probe submit per beat: a
 * reply nobody reads is not worth a submit, and every submit the full ring refuses costs
 * the vendor's own wall line on the framebuffer. The gate lifts when the host takes a
 * reply again, or at the next enumeration (the pump's Connected book). */
static int64_t
usb_tx(const uint8_t *data, uint64_t len)
{
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), now = READ_SYSREG(CNTVCT_EL0);
	int gated = usb_in_stale >= USB_IN_STALE_GATE;
	efi_status s;
	int64_t r;

	if (usb_in_expect) {
		usb_in_refused++;    /* the invariant: one IN transfer stands; never queue a second */
		return -1;
	}
	if (gated && usb_in_gate_next != 0 && now < usb_in_gate_next) {
		usb_in_refused++;    /* inside the backoff: no submit, so no vendor wall either */
		return -1;
	}
	if (data != usb_tx_buf) {
		memcpy(usb_tx_buf, data, len);
	}
	s = USB->send(USB_EP_IN, len, usb_tx_buf);
	if (EFI_ERROR(s)) {
		if (gated) {
			/* the gate's own beat: the probe was refused too; the count goes on quietly */
			usb_in_gate_backoff *= 2;
			if (usb_in_gate_backoff > 30 * freq) {
				usb_in_gate_backoff = 30 * freq;
			}
			usb_in_gate_next = READ_SYSREG(CNTVCT_EL0) + usb_in_gate_backoff;
			print("usb: [t+%d.%d] the reply side is refused at the wall too (%x): x%d unread, x%d turned away -- the next probe in %d s\\n",
			    usb_age() / 10, usb_age() % 10, (uint64_t)(uint32_t)s, usb_in_stale, usb_in_refused,
			    usb_in_gate_backoff / freq);
		}
		return -1;
	}
	usb_in_expect = 1;
	r = usb_wait(USB_EP_IN);
	usb_in_expect = 0;
	if (r >= 0) {
		if (gated) {
			print("usb: [t+%d.%d] the host reads replies again: the gate lifts (x%d unread, x%d turned away while it was up)\\n",
			    usb_age() / 10, usb_age() % 10, usb_in_stale, usb_in_refused);
		}
		usb_in_ok++;
		usb_in_stale = 0;
		usb_in_gate_next = 0;
		return r;
	}
	/* the wait gave up with the transfer still standing: take it back out (the drain --
	 * its Cancelled tail is swallowed by the pump) and count an unread reply */
	USB->abort_xfer(USB_EP_IN);
	usb_in_stale++;
	if (usb_in_stale >= USB_IN_STALE_GATE) {
		if (usb_in_gate_backoff == 0) {
			usb_in_gate_backoff = freq;
		} else {
			usb_in_gate_backoff *= 2;
			if (usb_in_gate_backoff > 30 * freq) {
				usb_in_gate_backoff = 30 * freq;
			}
		}
		usb_in_gate_next = READ_SYSREG(CNTVCT_EL0) + usb_in_gate_backoff;
		if (usb_in_stale == USB_IN_STALE_GATE) {
			print("usb: [t+%d.%d] the IN gate is up: x%d unread replies -- reply submits hold off, one probe per beat (1 s doubling to 30 s, counts silent)\\n",
			    usb_age() / 10, usb_age() % 10, usb_in_stale);
		}
	} else if (usb_in_stale == 1) {
		print("usb: [t+%d.%d] a reply came back unread: the host's reader is gone (the stale TRB is taken out; from the third unread the replies are gated)\\n",
		    usb_age() / 10, usb_age() % 10);
	}
	return -1;
}
""")

# ---- hunk 7: the service window's whole-pair rebuild + the loop's calm -----------------------
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
			if (usb_service_secs != 0 && READ_SYSREG(CNTVCT_EL0) - usb_service_mark > usb_service_secs * READ_SYSREG(CNTFRQ_EL0)) {
				print("usb: the service window is over: reset\\n");
				reboot();
			}
			continue;
		}
""",
"""/* Wave 38: the service window's own rebuild of the bulk pair -- the loader-side minimal
 * equivalent of the whole-pair END_TRANSFER + reconfigure (wave34 §5's design item 2; the
 * FD layer's own UsbFnDwc surgery stays a design there -- an FD rebuild breaks the
 * 8924cb67 byte anchor every graft since wave 21 is pinned to). The zombie of wave31 (x2)
 * and wave36 round 3: the vendor's conversion-point teardown leaves the pair's state
 * bytes at zero (0x8000000C) with ep0 alive alone. The loader cannot walk the vendor's
 * DwcConfigureEP, but the pair's own END_TRANSFERs are reachable (abort_xfer) and the
 * full reconfiguration is reachable the start_ex way: the vendor's start_ex stops the
 * controller itself, rebuilds ep0 and the descriptor set, and the next enumeration's
 * SET_CONFIG walk re-arms the bulk pair (the same replay the bring-up's re-throw uses).
 * Never during a session (a start_ex resets the DWC3 -- the tunnel would die; wave21.2's
 * lesson). Service window only, twice at most, a minute apart, and only when both halves
 * agree the pair is dead: the reply gate is up (three unread replies) AND the receive
 * side sits at the wall (a refusal remembered, nothing standing). */
static uint64_t usb_pair_rebuilds, usb_zombie_last;

static void
usb_pair_rebuild(void)
{
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), now = READ_SYSREG(CNTVCT_EL0);

	if (run_active || !usb_ready || usb_pair_rebuilds >= 2) {
		return;
	}
	if (usb_in_stale < USB_IN_STALE_GATE || usb_rx_queued || usb_arm_code == 0) {
		return;         /* one disagreement is enough: either half alive = not the zombie */
	}
	if (usb_zombie_last != 0 && now - usb_zombie_last < 60 * freq) {
		return;
	}
	usb_zombie_last = now;
	usb_pair_rebuilds++;
	print("usb: [t+%d.%d] the bulk pair reads dead both ways (x%d unread replies, last refuse %x): rebuild %d of 2 -- the pair's END_TRANSFERs, then the whole bring-up again\\n",
	    usb_age() / 10, usb_age() % 10, usb_in_stale, (uint64_t)usb_arm_code, usb_pair_rebuilds);
	USB->abort_xfer(USB_EP_IN);      /* the pair's own END_TRANSFERs: the stale TRBs retire */
	USB->abort_xfer(USB_EP_OUT);
	usb_rx_queued = 0;
	usb_in_expect = 0;
	usb_gate_reset();
	usb_in_gate_next = 0;
	usb_rx_gen++;
	if (usb_init_event != NULL) {
		BS->signal_event(usb_init_event);   /* the platform's bring-up callback again, as the re-throw does */
	}
	if (usb_start_attempt() <= 0) {
		print("usb: the rebuild's bring-up did not come back: the window's reset is the next stop\\n");
		usb_ready = 0;
		return;
	}
	print("usb: the pair's rebuild is in: the gadget is presented, a fresh enumeration may arm the pair\\n");
}

static void
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
		}
""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: 7 hunks applied")
