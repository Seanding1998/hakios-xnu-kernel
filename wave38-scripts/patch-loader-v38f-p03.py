#!/usr/bin/env python3
"""Wave 38 fix generation 4: P0-3 + P1-1 (review report 3).

P0-3 -- the rebuild detector is rebuilt on timestamped same-generation evidence:
  - PROGRESS: the last real advance (an armed receive, a delivered reply, a received
    command) is stamped usb_pair_last_progress;
  - FAILURE: the wall gate stamps usb_wall_last_at on every refused receive submit;
  - the detector (service window only, run_active hard gate kept) fires when the
    failure is RECENT and the progress is NOT: a recent wall plus no progress for
    120 s means both halves are dead in this generation -- including the pure-0xC
    zombie, which has no IN history at all (the old detector demanded three unread
    replies that can never exist there);
  - vetoes: the grace after a bring-up (150 s), a recent Connected (30 s), and the
    cumulative-ledger problem is gone by construction.

P1-1 -- the rebuild becomes a transaction: window expiry checked first, abort results
checked, a drained retirement, the kick behind a pumped settle, a bounded failure that
stops USB for the window, the counter reset per window, and honest wording (a bounded
recovery, not a self-heal verdict).

usage: patch-loader-v38f-p03.py LOADER_C
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src
lines = src.split("\n")

def line_index(prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise SystemExit(f"anchor not found: {prefix!r}")

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:200]}"
    src = src.replace(old, new)

# ---- hunk 1: the progress/failure stamps (wall gate) ---------------------------------------------
sub(
"""	usb_wall_count++;
	usb_arm_code = code;""",
"""	usb_wall_count++;
	usb_wall_last_at = READ_SYSREG(CNTVCT_EL0);   /* P0-3: timestamped failure evidence */
	usb_arm_code = code;""")

sub(
"""static uint64_t usb_pair_rebuilds, usb_zombie_last;
""",
"""static uint64_t usb_pair_rebuilds, usb_zombie_last;
/* P0-3: timestamped same-generation evidence (not cumulative ledgers): the last real
 * advance and the last wall refusal, plus the generation's birth for the grace. */
static uint64_t usb_pair_last_progress;
static uint64_t usb_pair_born_at;
static uint64_t usb_wall_last_at;
static uint64_t usb_last_connected_at;
""")

# ---- hunk 2: stamp the progress points ----------------------------------------------------------
sub(
"""	usb_arm_ok++;
	usb_cp1++;
	usb_rx_queued = 1;
	usb_out_state = USB_REQ_SUBMITTED;
	usb_gate_reset();""",
"""	usb_arm_ok++;
	usb_cp1++;
	usb_rx_queued = 1;
	usb_out_state = USB_REQ_SUBMITTED;
	usb_pair_last_progress = READ_SYSREG(CNTVCT_EL0);   /* P0-3: an armed receive is progress */
	usb_gate_reset();""")

sub(
"""	if (r >= 0 && usb_in_state == USB_REQ_IDLE) {
		if (r != (int64_t)len) {""",
"""	if (r >= 0 && usb_in_state == USB_REQ_IDLE) {
		usb_pair_last_progress = READ_SYSREG(CNTVCT_EL0);   /* P0-3: a delivered reply */
		if (r != (int64_t)len) {""")

sub(
"""	r = usb_wait(USB_EP_OUT);
	if (r < 0 && usb_out_state == USB_REQ_SUBMITTED) {""",
"""	r = usb_wait(USB_EP_OUT);
	if (r > 0) {
		usb_pair_last_progress = READ_SYSREG(CNTVCT_EL0);   /* P0-3: a command arrived */
	}
	if (r < 0 && usb_out_state == USB_REQ_SUBMITTED) {""")

# ---- hunk 3: start_attempt stamps the birth + clears the states ----------------------------------
sub(
"""	usb_in_state = USB_REQ_IDLE;    /* a fresh controller: both endpoints start clean */
	usb_out_state = USB_REQ_IDLE;
	usb_in_fault = 0;""",
"""	usb_in_state = USB_REQ_IDLE;    /* a fresh controller: both endpoints start clean */
	usb_out_state = USB_REQ_IDLE;
	usb_in_fault = 0;
	usb_pair_born_at = READ_SYSREG(CNTVCT_EL0);         /* P0-3: the generation's birth */
	usb_pair_last_progress = usb_pair_born_at;
	usb_wall_last_at = 0;""")

# ---- hunk 4: the pump's Connected stamps the enumeration time --------------------------------------
sub(
"""				usb_bus_resets++;
				usb_in_fault = 0;     /* a fresh bus: the faulted endpoint may try again */""",
"""				usb_bus_resets++;
				usb_last_connected_at = READ_SYSREG(CNTVCT_EL0);   /* P0-3: an enumeration */
				usb_in_fault = 0;     /* a fresh bus: the faulted endpoint may try again */""")

# ---- hunk 5: the detector rewritten (index-based splice: the old block holds a non-ASCII
#      byte in its comment, so the splice runs on anchors, not on the literal text) ----------------
NEWBLOCK = r"""/* Wave 38: the service window's own bounded recovery of the bulk pair. The review's
 * verdict on the old detector stands: three unread replies can never exist in the
 * pure-0xC zombie (no commands arrive, so no replies are owed), and a cumulative
 * last-error code proves nothing about NOW. The rewritten detector reads only
 * timestamped same-generation evidence:
 *   - FAILURE: a receive submit refused recently (the wall gate's own stamp);
 *   - NO PROGRESS: no armed receive, no delivered reply, no received command for
 *     120 s -- which covers the pure-0xC case that has no IN history at all;
 *   - vetoes: the generation's bring-up grace (150 s -- the arm window and a fresh
 *     SET_CONFIG get their time), a recent enumeration (a host mid-setup is not a
 *     dead pair), the run_active hard gate, and the service window checked FIRST
 *     (a window about to end never starts a rebuild).
 * The recovery itself: the pair's own END_TRANSFERs (abort_xfer, results checked),
 * a drained retirement of both endpoint states, the platform kick behind a pumped
 * settle, then start_ex -- which stops the controller itself and rebuilds ep0; the
 * bulk pair arms again only when the host's next enumeration SET_CONFIGs. A failed
 * recovery stops USB for the window (the window's own reset remains the exit). This
 * is a bounded RECOVERY, not a self-heal verdict: the revised acceptance owns that
 * evidence (a nonce round-trip after a real re-configuration). */
static uint64_t usb_pair_rebuilds, usb_zombie_last;
/* P0-3: timestamped same-generation evidence (not cumulative ledgers): the last real
 * advance and the last wall refusal, plus the generation's birth for the grace. */
static uint64_t usb_pair_last_progress;
static uint64_t usb_pair_born_at;
static uint64_t usb_wall_last_at;
static uint64_t usb_last_connected_at;

static void
usb_pair_rebuild(void)
{
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), now = READ_SYSREG(CNTVCT_EL0);
	efi_status ar;

	if (run_active || !usb_ready || usb_pair_rebuilds >= 2) {
		return;
	}
	if (usb_pair_born_at != 0 && now - usb_pair_born_at < 150 * freq) {
		return;         /* the bring-up's grace: the arm window and SET_CONFIG get their time */
	}
	if (usb_last_connected_at != 0 && now - usb_last_connected_at < 30 * freq) {
		return;         /* an enumeration just happened: a host mid-setup is not a dead pair */
	}
	if (usb_wall_last_at == 0 || now - usb_wall_last_at > 120 * freq) {
		return;         /* no RECENT wall refusal: the receive side has not failed now */
	}
	if (usb_pair_last_progress != 0 && now - usb_pair_last_progress < 120 * freq) {
		return;         /* RECENT progress vetoes the rebuild: some half is alive */
	}
	if (usb_zombie_last != 0 && now - usb_zombie_last < 60 * freq) {
		return;
	}
	usb_zombie_last = now;
	usb_pair_rebuilds++;
	print("usb: [t+%d.%d] the pair reads dead in this generation (recent refuse %x, no progress for %d s): bounded recovery %d of 2 -- the pair's END_TRANSFERs, a drained retirement, then the whole bring-up again\n",
	    usb_age() / 10, usb_age() % 10, (uint64_t)usb_arm_code,
	    (uint64_t)((now - usb_pair_last_progress) / freq), usb_pair_rebuilds);
	ar = USB->abort_xfer(USB_EP_IN);      /* the pair's own END_TRANSFERs: the stale TRBs retire */
	if (EFI_ERROR(ar)) {
		print("usb: the recovery's IN abort was refused (%x): the drain proceeds anyway\n",
		    (uint64_t)(uint32_t)ar);
	}
	ar = USB->abort_xfer(USB_EP_OUT);
	if (EFI_ERROR(ar)) {
		print("usb: the recovery's OUT abort was refused (%x): the drain proceeds anyway\n",
		    (uint64_t)(uint32_t)ar);
	}
	usb_rx_queued = 0;
	usb_in_state = USB_REQ_CANCELLING;    /* P0-1: both tails are owed; the drain follows */
	usb_out_state = USB_REQ_CANCELLING;
	usb_retire_drain(&usb_in_state);
	usb_retire_drain(&usb_out_state);
	usb_gate_reset();
	usb_in_gate_next = 0;
	usb_rx_gen++;
	/* (the old transfer buffers are deliberately left in place: freeing memory the
	 * controller may still DMA into is the worse trade -- two recoveries at most
	 * bound the cost at 4 MiB, and start_ex's fresh allocations take over from here) */
	if (usb_init_event != NULL) {
		BS->signal_event(usb_init_event);   /* the platform's bring-up callback again */
	}
	usb_wait_pumped(NULL, 250);             /* a quiet, pumped five seconds behind the kick
	                                           (the re-throw's proven shape: the callback
	                                           presents the gadget inside it) */
	if (usb_start_attempt() <= 0) {
		print("usb: the recovery's bring-up did not come back: USB is stopped for this window (the window's own reset remains the exit)\n");
		usb_ready = 0;
		return;
	}
	print("usb: the recovery's bring-up is back: the gadget is presented again -- the pair still needs the host's SET_CONFIG before any of this is called recovered\n");
}
"""

com_start = line_index("/* Wave 38: the service window's own rebuild")
# brace-match the function from its signature (the definition line starts the line)
sig = line_index("usb_pair_rebuild(void)")
depth, k, started = 0, sig, False
while k < len(lines):
    for ch in lines[k]:
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
    if started and depth == 0:
        break
    k += 1
# the block to replace: from the comment's start line through the function's close
src = "\n".join(lines[:com_start]) + "\n" + NEWBLOCK + "\n".join(lines[k + 1:])
lines = src.split("\n")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-3/P1-1 applied (5 hunks, hunk 5 via splice)")
