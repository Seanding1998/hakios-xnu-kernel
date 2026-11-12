#!/usr/bin/env python3
"""Wave 38 fix generation 3: P0-1 + P1-2 (review report 3) -- the request lifecycle.

P0-1 (the IN request): a boolean "someone waits" cannot attribute completions. The
request management becomes a real per-endpoint state machine

    IDLE -> SUBMITTED -> (CANCELLING -> IDLE | IDLE)

with these rules, each of which answers one of the review's counterexamples:
  - a new submit is legal only from IDLE (the late-Cancelled/late-OK races die: B cannot
    start until A's retirement evidence has been consumed);
  - a completion seen while SUBMITTED belongs to the standing request (nothing else is
    outstanding on that endpoint -- attribution by exclusivity, the only honest kind
    without a protocol cookie);
  - a completion seen while CANCELLING is the retired request's tail: consumed as
    retirement evidence (the state returns to IDLE);
  - a completion seen while IDLE is a stray: counted, swallowed;
  - abort results are checked; the tail is drained by a bounded pump loop and its
    timeout is a bounded fault (the endpoint refuses new submits until a Connected or a
    pair rebuild clears it -- never an unbounded spin, never an assumption);
  - a Connected event is NOT "everything retired": it flips standing requests to
    CANCELLING and bumps a reset counter the waiters bail on;
  - a reply shorter than its submitted length is a failed reply (usb_tx drains it and
    says so), never silently credited.

P1-2 (the OUT request): the same ownership for the receive side --
  - a bound exit (3 s session / window / 10 s IN) that did not abort keeps the transfer
    standing: the standing-receive identity is RESTORED so the next consumer takes over
    the standing transfer instead of queueing a second one into the same DMA buffer
    (the vendor contract violation the review flagged);
  - the data-timeout abort flips CANCELLING and drains before the caller proceeds;
  - usb_poll_command serves the completed command BEFORE re-arming (the hardware must
    not be invited to overwrite the buffer while the previous command is being read).

usb_in_expect is retired; the pump's stray swallow keys off the IN state itself.

usage: patch-loader-v38e-p01.py LOADER_C
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

# ---- hunk 1: the lifecycle state (extends the P0-2 ledger block) -------------------------------
sub(
"""static uint64_t usb_in_send_fail;    /* consecutive direct-submit refusals (an episode) */
static uint32_t usb_in_send_code;    /* the episode's last refusal code (kept on the record) */
static uint64_t usb_in_send_fail_total; /* the cumulative refusals (never reset) */
static uint64_t usb_in_sf_next, usb_in_sf_backoff;
""",
"""static uint64_t usb_in_send_fail;    /* consecutive direct-submit refusals (an episode) */
static uint32_t usb_in_send_code;    /* the episode's last refusal code (kept on the record) */
static uint64_t usb_in_send_fail_total; /* the cumulative refusals (never reset) */
static uint64_t usb_in_sf_next, usb_in_sf_backoff;
/* P0-1 (review report 3): the request lifecycle. One request stands per endpoint; a
 * completion is attributed by that exclusivity (there is no protocol cookie to match
 * with). CANCELLING means abort was asked: no new submit and no buffer reuse until the
 * vendor's own completion arrives for the retired request (the bounded drain), and a
 * drain timeout is a fault the endpoint stays in until a Connected clears it. */
#define USB_REQ_IDLE 0
#define USB_REQ_SUBMITTED 1
#define USB_REQ_CANCELLING 2
static int usb_in_state, usb_out_state;
static uint64_t usb_bus_resets;      /* Connected events: the waiters' cue to bail */
static uint64_t usb_out_stray;       /* OUT completions with no standing request */
static int usb_in_fault;             /* the bounded drain timed out: the endpoint refuses */
""")

# ---- hunk 2: the pump -- Connected retires standing requests instead of clearing flags --------
sub(
"""				/* Wave 38: a fresh enumeration is a fresh reader: the reply gates lift and
				 * the episode ledgers close (the bus reset retired whatever stood). The
				 * backoffs start from 1 s again at the next episode (the review's
				 * inherited-backoff note); the cumulative totals stay cumulative. */
				usb_in_expect = 0;
				usb_in_stale = 0;
				usb_in_gate_next = 0;
				usb_in_gate_backoff = 0;
				usb_in_send_fail = 0;
				usb_in_send_code = 0;
				usb_in_sf_next = 0;
				usb_in_sf_backoff = 0;
""",
"""				/* Wave 38: a fresh enumeration is a fresh reader: the reply gates lift and
				 * the episode ledgers close. The backoffs start from 1 s again at the
				 * next episode (the review's inherited-backoff note); the cumulative
				 * totals stay cumulative. P0-1: a Connected event is NOT "everything
				 * retired" -- standing requests flip to CANCELLING and the waiters bail
				 * on the reset counter; their cleanup drains the tails. */
				usb_stale_wipe();
				if (usb_in_state == USB_REQ_SUBMITTED) {
					usb_in_state = USB_REQ_CANCELLING;
				}
				if (usb_out_state == USB_REQ_SUBMITTED) {
					usb_out_state = USB_REQ_CANCELLING;
				}
				usb_bus_resets++;
				usb_in_fault = 0;     /* a fresh bus: the faulted endpoint may try again */
""")

# ---- hunk 3: the pump's completion branches attribute by state ---------------------------------
sub(
"""			if (ep == USB_EP_OUT) {
				usb_done_out.live = 1;
				usb_done_out.status = data.transfer.status;
				usb_done_out.bytes = data.transfer.bytes_completed;
				if (usb_rx_queued) {
					usb_rx_queued = 0;
					if (ok) {
						usb_cp3_ok++;
						/* checkpoint 3: the host's write came off the wire and its
						 * completion reached the loader */
						if (usb_cp3_ok <= 3 || usb_cp3_ok % 16 == 0) {
							print("usb: [t+%d.%d] checkpoint-3: the standing receive finished (%d bytes, gen %d); the command is served next\\n",
							    usb_age() / 10, usb_age() % 10, data.transfer.bytes_completed, usb_rx_gen);
						}
					} else {
						usb_cp3_bad++;
						print("usb: [t+%d.%d] checkpoint-3 FAILED: the standing receive finished bad (status %d, gen %d)\\n",
						    usb_age() / 10, usb_age() % 10, (uint64_t)data.transfer.status, usb_rx_gen);
					}
				}
			} else if (!usb_in_expect) {
				/* Wave 38: a completion for a transfer nothing waits on -- the tail of a
				 * reply we took back out. Swallowed: it must never answer a later wait. */
				usb_in_stray++;
			} else {
""",
"""			if (ep == USB_EP_OUT) {
				/* P0-1: a completion while SUBMITTED belongs to the standing receive
				 * (nothing else is outstanding on this endpoint); while CANCELLING it is
				 * the retired request's tail -- the retirement evidence; while IDLE it is
				 * a stray. */
				if (usb_out_state == USB_REQ_CANCELLING) {
					usb_out_state = USB_REQ_IDLE;    /* the tail: retired clean */
				} else if (usb_out_state == USB_REQ_IDLE) {
					usb_out_stray++;
				} else {
					usb_done_out.live = 1;
					usb_done_out.status = data.transfer.status;
					usb_done_out.bytes = data.transfer.bytes_completed;
					if (usb_rx_queued) {
						usb_rx_queued = 0;
						if (ok) {
							usb_cp3_ok++;
							/* checkpoint 3: the host's write came off the wire and its
							 * completion reached the loader */
							if (usb_cp3_ok <= 3 || usb_cp3_ok % 16 == 0) {
								print("usb: [t+%d.%d] checkpoint-3: the standing receive finished (%d bytes, gen %d); the command is served next\\n",
								    usb_age() / 10, usb_age() % 10, data.transfer.bytes_completed, usb_rx_gen);
							}
						} else {
							usb_cp3_bad++;
							print("usb: [t+%d.%d] checkpoint-3 FAILED: the standing receive finished bad (status %d, gen %d)\\n",
							    usb_age() / 10, usb_age() % 10, (uint64_t)data.transfer.status, usb_rx_gen);
						}
					}
				}
			} else if (usb_in_state != USB_REQ_SUBMITTED) {
				/* P0-1: while CANCELLING this is the retired reply's tail -- the retirement
				 * evidence; while IDLE it is a stray. Either way it is swallowed: it must
				 * never answer a later wait. */
				if (usb_in_state == USB_REQ_CANCELLING) {
					usb_in_state = USB_REQ_IDLE;
				} else {
					usb_in_stray++;
				}
			} else {
""")

# ---- hunk 4: usb_stale_wipe + the bounded drain (before usb_wait) ------------------------------
sub(
"""/*
 * Pump controller events until a transfer on `endpoint` finishes.
 * Returns the byte count, or -1 if the transfer was cancelled or the cable
 * state changed. Keeps the watchdog fed while idle.
 */
""",
"""/* Wave 38: the episode ledgers' shared wipe (the pump's Connected book calls it; the
 * service window's rebuild resets it too). */
static void
usb_stale_wipe(void)
{
	usb_in_stale = 0;
	usb_in_gate_next = 0;
	usb_in_gate_backoff = 0;
	usb_in_send_fail = 0;
	usb_in_send_code = 0;
	usb_in_sf_next = 0;
	usb_in_sf_backoff = 0;
}

/* P0-1: a bounded drain. CANCELLING means the vendor owes us the retired request's own
 * completion; pump until it arrives or the bound passes. Returns 0 retired clean, -1
 * the tail never came (a bounded fault: the caller leaves the endpoint refusing). */
static int
usb_retire_drain(int *state)
{
	int b;

	for (b = 0; b < 50 && *state == USB_REQ_CANCELLING; b++) {
		usb_pump();
	}
	return *state == USB_REQ_IDLE ? 0 : -1;
}

/*
 * Pump controller events until a transfer on `endpoint` finishes.
 * Returns the byte count, or -1 if the transfer was cancelled or the cable
 * state changed. Keeps the watchdog fed while idle.
 */
""")

# ---- hunk 5: usb_wait -- bus-reset bail + state-aware completion consumption --------------------
sub(
"""	for (;;) {
		usb_pump();     /* Wave 24: the one consumer; completions land in the pending store */
		if (usb_disconnects != parts_at) {
			return -1;      /* the cable changed under the transfer (the caller's cue to bail) */
		}
		if (d->live) {
			d->live = 0;
			if (d->status == UsbDeviceTransferStatusCompleteOK) {
				return (int64_t)d->bytes;
			}
			return -1;
		}
""",
"""	for (;;) {
		usb_pump();     /* Wave 24: the one consumer; completions land in the pending store */
		if (usb_disconnects != parts_at) {
			return -1;      /* the cable changed under the transfer (the caller's cue to bail) */
		}
		if (bus_resets_at != usb_bus_resets) {
			return -1;      /* P0-1: the bus reset mid-transfer -- bail, the cleanup drains */
		}
		if (d->live) {
			d->live = 0;
			if (endpoint == USB_EP_IN) {
				usb_in_state = USB_REQ_IDLE;    /* the completion: this request is retired */
			} else {
				usb_out_state = USB_REQ_IDLE;
			}
			if (d->status == UsbDeviceTransferStatusCompleteOK) {
				return (int64_t)d->bytes;
			}
			return -1;
		}
""")

# ---- hunk 6: usb_wait's locals (the bus-reset latch) --------------------------------------------
sub(
"""	static uint64_t last_pet;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0);
	struct usb_done *d = (endpoint == USB_EP_OUT) ? &usb_done_out : &usb_done_in;
	uint64_t parts_at = usb_disconnects;
""",
"""	static uint64_t last_pet;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0);
	struct usb_done *d = (endpoint == USB_EP_OUT) ? &usb_done_out : &usb_done_in;
	uint64_t parts_at = usb_disconnects;
	uint64_t bus_resets_at = usb_bus_resets;
""")

# ---- hunk 7: usb_wait's data-timeout abort flips CANCELLING -------------------------------------
sub(
"""		if (usb_data_timeout != 0 && READ_SYSREG(CNTVCT_EL0) - began > usb_data_timeout * freq) {
			USB->abort_xfer(endpoint);
			return -1;
		}
""",
"""		if (usb_data_timeout != 0 && READ_SYSREG(CNTVCT_EL0) - began > usb_data_timeout * freq) {
			efi_status ar = USB->abort_xfer(endpoint);

			if (endpoint == USB_EP_IN) {
				usb_in_state = USB_REQ_CANCELLING;   /* P0-1: the tail must be drained */
			} else {
				usb_out_state = USB_REQ_CANCELLING;
			}
			if (EFI_ERROR(ar)) {
				print("usb: the data timeout's abort was refused (%x): the endpoint's cleanup proceeds anyway\\n",
				    (uint64_t)(uint32_t)ar);
			}
			return -1;
		}
""")

assert src != orig, "nothing changed (part 1)"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-1/P1-2 part 1 applied (7 hunks)")
