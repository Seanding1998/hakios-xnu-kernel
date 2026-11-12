#!/usr/bin/env python3
"""Wave 38 fix generation 1: P0-2 (review report 3) -- the IN reply's DIRECT submit
failure gets its own fault-episode gate.

The reviewed hole: `usb_tx`'s send-error branch only printed when the reader-death gate
(`usb_in_stale >= USB_IN_STALE_GATE`) was already up; a submit refused outright (the ring
already full, the IN pair unconfigured) never touched `usb_in_stale`, so the gate never
engaged and every command's reply kept hitting the vendor's print point (the isolation
counterexample: 1000 direct rejections -> 1000 real sends, stale=0, gate_next=0).

The fix (per the report's correction requirements):
  - direct submit failures get their OWN consecutive-failure counter and backoff beat
    (1 s doubling to 30 s, one probe per beat), with the error code kept;
  - an episode ends at the first successful submit (counters and backoff reset);
  - the reader-death ledger (`usb_in_stale`, "a reader stopped reading") is NOT touched
    by this path -- enqueue-failure and unread-reply stay distinct diagnoses;
  - backoff hygiene from the report's hunk-6 verdict note: the stale gate's backoff is
    reset on success and on Connected (episodes start from 1 s again; the cumulative
    totals stay cumulative).

usage: patch-loader-v38b-p02.py LOADER_C
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

# ---- hunk 1: the send-failure episode's ledger ----------------------------------------------
sub(
"""static uint64_t usb_in_gate_next, usb_in_gate_backoff;
#define USB_IN_STALE_GATE 3      /* unread replies before the gate comes up */
""",
"""static uint64_t usb_in_gate_next, usb_in_gate_backoff;
#define USB_IN_STALE_GATE 3      /* unread replies before the gate comes up */
/* P0-2 (review report 3): a reply whose SUBMIT is refused outright (the ring already
 * full, the IN pair unconfigured) is its own fault episode -- it never touched the
 * reader-death ledger above, so the gate never engaged and every command's reply kept
 * hitting the vendor's print point. Its own consecutive-failure count, its own beat. */
static uint64_t usb_in_send_fail;    /* consecutive direct-submit refusals (an episode) */
static uint32_t usb_in_send_code;    /* the episode's last refusal code (kept on the record) */
static uint64_t usb_in_send_fail_total; /* the cumulative refusals (never reset) */
static uint64_t usb_in_sf_next, usb_in_sf_backoff;
""")

# ---- hunk 2: the pump's Connected branch resets the send-failure episode and the stale backoff
sub(
"""				/* Wave 38: a fresh enumeration is a fresh reader: the reply gate lifts and
				 * the stale ledger closes (the bus reset retired whatever stood). */
				usb_in_expect = 0;
				usb_in_stale = 0;
				usb_in_gate_next = 0;
""",
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
""")

# ---- hunk 3: usb_tx's entry gate covers the send-failure beat too -----------------------------
sub(
"""	if (usb_in_expect) {
		usb_in_refused++;    /* the invariant: one IN transfer stands; never queue a second */
		return -1;
	}
	if (gated && usb_in_gate_next != 0 && now < usb_in_gate_next) {
		usb_in_refused++;    /* inside the backoff: no submit, so no vendor wall either */
		return -1;
	}
""",
"""	if (usb_in_expect) {
		usb_in_refused++;    /* the invariant: one IN transfer stands; never queue a second */
		return -1;
	}
	if (gated && usb_in_gate_next != 0 && now < usb_in_gate_next) {
		usb_in_refused++;    /* inside the reader-death backoff: no submit, no vendor wall */
		return -1;
	}
	if (usb_in_send_fail != 0 && now < usb_in_sf_next) {
		usb_in_refused++;    /* P0-2: inside the send-failure beat -- the probes go one per beat */
		return -1;
	}
""")

# ---- hunk 4: usb_tx's send-error branch becomes its own gated episode --------------------------
sub(
"""	s = USB->send(USB_EP_IN, len, usb_tx_buf);
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
""",
"""	s = USB->send(USB_EP_IN, len, usb_tx_buf);
	if (EFI_ERROR(s)) {
		if (gated) {
			/* the reader-death gate's own beat: the probe was refused too */
			usb_in_gate_backoff *= 2;
			if (usb_in_gate_backoff > 30 * freq) {
				usb_in_gate_backoff = 30 * freq;
			}
			usb_in_gate_next = READ_SYSREG(CNTVCT_EL0) + usb_in_gate_backoff;
			print("usb: [t+%d.%d] the reply side is refused at the wall too (%x): x%d unread, x%d turned away -- the next probe in %d s\\n",
			    usb_age() / 10, usb_age() % 10, (uint64_t)(uint32_t)s, usb_in_stale, usb_in_refused,
			    usb_in_gate_backoff / freq);
			return -1;
		}
		/* P0-2: the episode of direct refusals. First one announces with the code; each
		 * later probe that is refused again prints at its own beat (1 s doubling to
		 * 30 s). The reader-death ledger is NOT touched here: nothing was queued, so
		 * no reader missed anything. */
		usb_in_send_code = (uint32_t)s;
		usb_in_send_fail++;
		usb_in_send_fail_total++;
		usb_in_sf_backoff = usb_in_send_fail == 1 ? freq : usb_in_sf_backoff * 2;
		if (usb_in_sf_backoff > 30 * freq) {
			usb_in_sf_backoff = 30 * freq;
		}
		usb_in_sf_next = READ_SYSREG(CNTVCT_EL0) + usb_in_sf_backoff;
		print("usb: [t+%d.%d] the reply's submit itself is refused: %x (x%d this episode, x%d ever) -- submits hold off, one probe per beat\\n",
		    usb_age() / 10, usb_age() % 10, (uint64_t)usb_in_send_code, usb_in_send_fail,
		    usb_in_send_fail_total);
		return -1;
	}
	/* a submission went in: both episodes are over */
	usb_in_send_fail = 0;
	usb_in_sf_next = 0;
	usb_in_sf_backoff = 0;
	usb_in_expect = 1;
""")

# ---- hunk 5: the success path resets the stale gate's backoff (episodes start from 1 s) --------
sub(
"""		usb_in_ok++;
		usb_in_stale = 0;
		usb_in_gate_next = 0;
		return r;
""",
"""		usb_in_ok++;
		usb_in_stale = 0;
		usb_in_gate_next = 0;
		usb_in_gate_backoff = 0;
		return r;
""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-2 applied (5 hunks)")
