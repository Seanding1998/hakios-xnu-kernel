#!/usr/bin/env python3
"""Wave 38 fix generation 3, part 2: the state machine lands in usb_rx / usb_tx /
usb_poll_command / usb_arm_rx, the pump's Disconnected book, and the rebuild/rethrow
paths. usb_in_expect is retired -- the IN state drives everything now.

usage: patch-loader-v38e2-p12.py LOADER_C
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

# ---- hunk A: usb_in_expect's declaration is retired ---------------------------------------------
sub(
"""static int usb_in_expect;        /* an IN transfer stands with the controller */
static uint64_t usb_in_stray;    /* completions for transfers nobody waits on any more */""",
"""static uint64_t usb_in_stray;    /* completions for transfers nobody waits on any more */
static uint64_t usb_in_short;    /* replies the host read short (a failed reply) */
static uint64_t usb_in_short_total;""")

# ---- hunk B: usb_arm_rx flips the OUT state ------------------------------------------------------
sub(
"""	usb_arm_ok++;
	usb_cp1++;
	usb_rx_queued = 1;
	usb_gate_reset();""",
"""	usb_arm_ok++;
	usb_cp1++;
	usb_rx_queued = 1;
	usb_out_state = USB_REQ_SUBMITTED;
	usb_gate_reset();""")

# ---- hunk C: the pump's Disconnected flips the OUT state too --------------------------------------
sub(
"""				usb_state_gone++;
				usb_connected = 0;
				usb_disconnects++;
				if (usb_rx_queued) {
					usb_rx_queued = 0;    /* P2-4: the receive's life follows the bus's */
					print("usb: the host left: the standing receive (gen %d) is retired\\n", usb_rx_gen);
				}
			}""",
"""				usb_state_gone++;
				usb_connected = 0;
				usb_disconnects++;
				if (usb_rx_queued) {
					usb_rx_queued = 0;    /* P2-4: the receive's life follows the bus's */
					print("usb: the host left: the standing receive (gen %d) is retired\\n", usb_rx_gen);
				}
				if (usb_out_state == USB_REQ_SUBMITTED) {
					usb_out_state = USB_REQ_CANCELLING;   /* P0-1: the vendor retires it; the cleanup drains */
				}
			}""")

# ---- hunk D: usb_rx takes the standing receive's ownership and restores it on bound exits --------
sub(
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
""",
"""static int64_t
usb_rx(uint8_t *buf, uint64_t len)
{
	int64_t r;

	if (usb_out_state == USB_REQ_CANCELLING) {
		/* P0-1: the previous receive is being retired -- drain its tail first; the
		 * buffer is not reused until the vendor's own completion lands. */
		if (usb_retire_drain(&usb_out_state) != 0) {
			return -1;      /* bounded fault: this pass declines; the window's reset still comes */
		}
	}
	if (usb_rx_queued) {
		usb_rx_queued = 0;      /* (every command is received the same way, into the same buffer) */
		usb_out_state = USB_REQ_SUBMITTED;   /* the standing receive IS this receive */
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
		usb_out_state = USB_REQ_SUBMITTED;
	}
	r = usb_wait(USB_EP_OUT);
	if (r < 0 && usb_out_state == USB_REQ_SUBMITTED) {
		/* a bound exit with the transfer still standing: it IS the standing receive
		 * now -- the identity is restored so the next consumer takes over the same
		 * transfer instead of queueing a second one into the same buffer (P1-2) */
		usb_rx_queued = 1;
	}
	if (usb_out_state == USB_REQ_CANCELLING) {
		usb_retire_drain(&usb_out_state);   /* the data timeout's abort: drain the tail */
	}
	return r;
}
""")

# ---- hunk E: usb_tx -- the state machine end to end ------------------------------------------------
sub(
"""	if (usb_in_expect) {
		usb_in_refused++;    /* the invariant: one IN transfer stands; never queue a second */
		return -1;
	}
	if (gated && usb_in_gate_next != 0 && now < usb_in_gate_next) {""",
"""	if (usb_in_state != USB_REQ_IDLE || usb_in_fault) {
		/* P0-1: a request stands or is being retired (or a drain timed out) -- no
		 * second submit and no buffer reuse; the fault lifts at the next enumeration */
		usb_in_refused++;
		return -1;
	}
	if (gated && usb_in_gate_next != 0 && now < usb_in_gate_next) {""")

sub(
"""	s = USB->send(USB_EP_IN, len, usb_tx_buf);
	if (EFI_ERROR(s)) {""",
"""	if (usb_in_state != USB_REQ_IDLE) {
		usb_in_refused++;    /* a state flip raced the gates (a reset mid-check): decline */
		return -1;
	}
	s = USB->send(USB_EP_IN, len, usb_tx_buf);
	if (EFI_ERROR(s)) {""")

sub(
"""	/* a submission went in: both episodes are over */
	usb_in_send_fail = 0;
	usb_in_sf_next = 0;
	usb_in_sf_backoff = 0;
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
		usb_in_gate_backoff = 0;
		return r;
	}
	/* the wait gave up with the transfer still standing: take it back out (the drain --
	 * its Cancelled tail is swallowed by the pump) and count an unread reply */
	USB->abort_xfer(USB_EP_IN);
	usb_in_stale++;""",
"""	/* a submission went in: both episodes are over */
	usb_in_send_fail = 0;
	usb_in_sf_next = 0;
	usb_in_sf_backoff = 0;
	usb_in_state = USB_REQ_SUBMITTED;
	r = usb_wait(USB_EP_IN);
	if (usb_in_state == USB_REQ_SUBMITTED) {
		/* the wait gave up on a bound with the transfer still standing: take it back
		 * out -- P0-1's drain, the vendor's own completion is the retirement evidence */
		efi_status ar = USB->abort_xfer(USB_EP_IN);

		usb_in_state = USB_REQ_CANCELLING;
		if (EFI_ERROR(ar)) {
			print("usb: the reply's abort was refused (%x): the drain proceeds anyway\\n",
			    (uint64_t)(uint32_t)ar);
		}
	}
	if (usb_in_state == USB_REQ_CANCELLING) {
		if (usb_retire_drain(&usb_in_state) != 0) {
			usb_in_fault = 1;
			print("usb: the retired reply's tail never arrived: the reply side refuses until the next enumeration\\n");
		}
	}
	if (r >= 0 && usb_in_state == USB_REQ_IDLE) {
		if (r != (int64_t)len) {
			/* P0-1: a short reply is a failed reply -- never silently credited */
			usb_in_short++;
			usb_in_short_total++;
			if (usb_in_short == 1) {
				print("usb: [t+%d.%d] a reply came back short (%d of %d bytes): it is treated as undelivered\\n",
				    usb_age() / 10, usb_age() % 10, (uint64_t)r, len);
			}
			return -1;
		}
		if (gated) {
			print("usb: [t+%d.%d] the host reads replies again: the gate lifts (x%d unread, x%d turned away while it was up)\\n",
			    usb_age() / 10, usb_age() % 10, usb_in_stale, usb_in_refused);
		}
		usb_in_ok++;
		usb_in_stale = 0;
		usb_in_gate_next = 0;
		usb_in_gate_backoff = 0;
		return r;
	}
	/* the wait failed, or the reply came back short: count an unread/undelivered reply */""")

# ---- hunk F: usb_poll_command serves before it re-arms (P1-2) --------------------------------------
sub(
"""	usb_pump();
	if (!usb_rx_queued) {
		usb_arm_rx();
	}
	if (!d->live) {
		return;
	}
	d->live = 0;
	if (d->status != UsbDeviceTransferStatusCompleteOK || d->bytes == 0) {
		return;
	}
	n = d->bytes < sizeof(cmd) - 1 ? d->bytes : sizeof(cmd) - 1;
	memcpy(cmd, usb_rx_buf, (size_t)n);
	cmd[n] = 0;
	fb_command(cmd);
}""",
"""	usb_pump();
	if (d->live) {
		/* P1-2: serve the completed command FIRST -- the re-arm below must not invite
		 * the hardware to overwrite the buffer while the previous command is read */
		d->live = 0;
		usb_out_state = USB_REQ_IDLE;
		if (d->status == UsbDeviceTransferStatusCompleteOK && d->bytes != 0) {
			n = d->bytes < sizeof(cmd) - 1 ? d->bytes : sizeof(cmd) - 1;
			memcpy(cmd, usb_rx_buf, (size_t)n);
			cmd[n] = 0;
			fb_command(cmd);
			return;
		}
	}
	if (!usb_rx_queued) {
		usb_arm_rx();
	}
}""")

# ---- hunk G: the rebuild / rethrow / probe paths' state flips --------------------------------------
sub(
"""	USB->abort_xfer(USB_EP_IN);      /* the pair's own END_TRANSFERs: the stale TRBs retire */
	USB->abort_xfer(USB_EP_OUT);
	usb_rx_queued = 0;
	usb_in_expect = 0;
	usb_gate_reset();""",
"""	USB->abort_xfer(USB_EP_IN);      /* the pair's own END_TRANSFERs: the stale TRBs retire */
	USB->abort_xfer(USB_EP_OUT);
	usb_rx_queued = 0;
	usb_in_state = USB_REQ_CANCELLING;    /* P0-1: both tails are owed; the drain follows */
	usb_out_state = USB_REQ_CANCELLING;
	usb_retire_drain(&usb_in_state);
	usb_retire_drain(&usb_out_state);
	usb_gate_reset();""")

sub(
"""	if (!EFI_ERROR(code)) {
		USB->abort_xfer(USB_EP_OUT);
		usb_rx_queued = 0;
	}
}""",
"""	if (!EFI_ERROR(code)) {
		USB->abort_xfer(USB_EP_OUT);
		usb_rx_queued = 0;
		usb_out_state = USB_REQ_CANCELLING;   /* P0-1: the probe's tail is drained lazily */
	}
}""")

sub(
"""	usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
	usb_ready = 1;
	usb_rx_gen++;            /* Wave 24: this generation's requests carry a new identity */
	usb_host_seen = 0;       /* a real detach happened; the next Connected is the next host */""",
"""	usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
	usb_ready = 1;
	usb_rx_gen++;            /* Wave 24: this generation's requests carry a new identity */
	usb_host_seen = 0;       /* a real detach happened; the next Connected is the next host */
	usb_in_state = USB_REQ_IDLE;    /* a fresh controller: both endpoints start clean */
	usb_out_state = USB_REQ_IDLE;
	usb_in_fault = 0;""")

# ---- hunk H: usb_start's re-throw clear -------------------------------------------------------------
sub(
"""		print("usb: the pair is un-armed after generation %d (last refuse %x, refused %d times): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), (uint64_t)usb_arm_code, usb_wall_count);
		usb_rx_queued = 0;""",
"""		print("usb: the pair is un-armed after generation %d (last refuse %x, refused %d times): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), (uint64_t)usb_arm_code, usb_wall_count);
		usb_rx_queued = 0;
		usb_in_state = USB_REQ_IDLE;
		usb_out_state = USB_REQ_IDLE;""")

# ---- hunk I: the rebuild's detector reads the states, not just the queues ---------------------------
sub(
"""	if (usb_in_stale < USB_IN_STALE_GATE || usb_rx_queued || usb_arm_code == 0) {
		return;         /* one disagreement is enough: either half alive = not the zombie */
	}""",
"""	if (usb_in_state != USB_REQ_IDLE || usb_out_state != USB_REQ_IDLE) {
		return;         /* P0-1: a request still stands or a tail is owed: not the zombie */
	}
	if (usb_in_stale < USB_IN_STALE_GATE || usb_rx_queued || usb_arm_code == 0) {
		return;         /* one disagreement is enough: either half alive = not the zombie */
	}""")

assert src != orig, "nothing changed (part 2)"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-1/P1-2 part 2 applied (9 hunks)")
