#!/usr/bin/env python3
"""Wave 21.5 patch: the bulk pair's arm probe + the wall re-throw (v17).

Wave 21.4's instruction-level verdict (docs/research/f12-ep2-not-configured.md): the boot
photo's "physical endpoint[2] not configured" is DwcPrepareURB reading the endpoint-table
state byte (ctx + phys_idx*32 + 0x18) and answering 0x8000000C while it is zero. The state
byte's only setter is DwcConfigureEP, and the bulk pair's only arming path is the host's
SET_CONFIG: UsbfnDwc's ep0 state machine case 9 -> UsbfnDwcSetConfigIfc (DEPSTARTCFG) ->
the descriptor walk -> the per-endpoint configure. start_ex arms the ep0 pair alone (the
vendor's ConfigureEnableEndpointsEx is ep0-only), so on the wall boots -- where the host
enumerates and SET_CONFIGs and the walk still never lands -- every bulk submit dies and the
session's command channel (and en0 with it) is dead on arrival.

The fix (F12 §6 first choice, the loader verifies its own arm instead of finding out at the
first command):
  1. After the boot window's start chain succeeds, probe the bulk OUT pair with a
     zero-length submit on a five-second beat. DwcPrepareURB reads the state byte and
     answers the wall code (0x8000000C) while the pair is un-armed; the submit is queued
     (and immediately aborted) once it is armed. The ep0 state machine only advances under
     handle_event's dispatch, so every beat pumps it -- without the pump a SET_CONFIG that
     arrives during the stage would sit unprocessed and the probe would lie.
  2. The probe's answer doubles as the root-cause discriminator: a steady 0x8000000C across
     generations says the arm chain is dead (H1/H2 territory); any other code says another
     layer answered and stops the stage -- a re-throw would be a guess.
  3. A generation that still answers the wall past its window (six beats) is stopped and
     thrown again: USB->stop(), the init event re-signaled, the twenty-five-second quiet
     (the churn lesson keeps one controller reset per twenty-five seconds), and the boot
     window's own start chain again. The restart replays the whole enumeration for the
     host -- a fresh SET_CONFIG chance. Two re-throws; then the server comes down and the
     run proceeds without it (the safe headless session; the next boot tries again).

usage: patch-loader-v17.py LOADER_C
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

# ---- hunk 0: the receive-queue flag's forward declaration (the stage resets it on every
# stop; its definition lives with the receive path, below the whole bring-up) -------------------
sub(
"""static void usb_lazy_start(void);
""",
"""static void usb_lazy_start(void);
static int usb_rx_queued;    /* the receive the loader leaves with the controller (defined below) */
""")

# ---- hunk 1: the stage's locals --------------------------------------------------------------
sub(
"""	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r, stalled;
""",
"""	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r, stalled, gen, beat, verdict;
	efi_status probe;
""")

# ---- hunk 2: the arm-probe stage between the start chain and the tick's close -----------------
sub(
"""		set_timer(tick, 1 /* TimerPeriodic */, 250000000 /* twenty-five seconds, in 100 ns */);
		if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
			BS->stall(1000000);
		}
	}
	if (tick != NULL) {
""",
"""		set_timer(tick, 1 /* TimerPeriodic */, 250000000 /* twenty-five seconds, in 100 ns */);
		if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
			BS->stall(1000000);
		}
	}
	/* Wave 21.5: the bulk pair's arm probe. start_ex arms ep0 alone (the vendor's
	 * ConfigureEnableEndpointsEx walks the ep0 pair only); the bulk pair arms when the
	 * host's SET_CONFIG walks the interface -- DwcConfigureEP sets the endpoint-table
	 * state byte that every submit reads ("physical endpoint[%d] not configured",
	 * 0x8000000C, the F12 wall). On the wall boots the host enumerates and SET_CONFIGs
	 * and the walk still never lands -- so the loader verifies the arm itself instead of
	 * finding out at the first command: a zero-length submit on the bulk OUT pair answers
	 * the wall code while the state byte is zero, and nothing once it is armed (the
	 * probe's answer doubles as the root-cause discriminator: a steady 0x8000000C across
	 * generations says the arm chain is dead; any other code says another layer answered
	 * and stops the stage -- a re-throw would be a guess). The ep0 state machine only
	 * advances under handle_event's dispatch, so every beat pumps it: without the pump a
	 * SET_CONFIG that arrives during the stage would sit unprocessed and the probe would
	 * lie. A generation that still answers the wall past its window (six beats, five
	 * seconds apart) is stopped and thrown again -- the restart replays the enumeration
	 * for the host, a fresh SET_CONFIG chance, with the twenty-five-second quiet between
	 * controller resets kept (the churn lesson). Two re-throws; then the server comes
	 * down and the run proceeds without it (the safe headless session -- the next boot
	 * tries again). */
	for (gen = 0; usb_ready && gen < 3; gen++) {
		verdict = 0;         /* 0 the wall through every beat, 1 armed, 2 a non-wall answer */
		for (beat = 0; beat < 6; beat++) {
			uint32_t msg = UsbDeviceEventNoEvent;
			uint64_t size = 0;
			usb_device_event_data data;

			if (beat != 0) { /* five seconds between probes; the timer event keeps the
			                    firmware's queue (and its watchdog) moving through it */
				if (tick != NULL) {
					set_timer(tick, 1 /* TimerPeriodic */, 5000000 /* five seconds, in 100 ns */);
					if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
						BS->stall(1000000);
					}
				} else {
					for (stalled = 0; stalled < 5; stalled++) {
						BS->stall(1000000);
					}
				}
			}
			USB->handle_event(&msg, &size, &data);
			if (msg == UsbDeviceEventDeviceStateChange) {
				usb_connected = (data.device_state == UsbDeviceStateConnected);
			}
			probe = USB->send(USB_EP_OUT, 0, usb_rx_buf);   /* the zero-length probe: the submit
			                                                   path reads the state byte and
			                                                   answers the wall code from it */
			if (probe == 0) {
				USB->abort_xfer(USB_EP_OUT);    /* the probe was queued: take it back out --
			                                       its Cancelled completion is dropped
			                                       harmlessly by the serve paths */
				verdict = 1;
				break;
			}
			print("usb: bulk probe gen %d beat %d: %x\\n", (uint64_t)gen, (uint64_t)beat, probe);
			if ((probe & 0xffffffffULL) != 0x8000000CULL) {
				verdict = 2;
				break;
			}
		}
		if (verdict == 1) {
			print("usb: the bulk pair answered: armed at generation %d, beat %d\\n",
			    (uint64_t)gen, (uint64_t)beat);
			break;
		}
		if (verdict == 2) {
			print("usb: a non-wall probe answer stopped the stage; the session goes on as it stands\\n");
			break;
		}
		if (gen == 2) {
			print("usb: the wall stands after 3 generations (%x): the server comes down, the run goes on without it\\n",
			    probe);
			USB->stop();
			usb_ready = 0;
			usb_rx_queued = 0;
			break;
		}
		print("usb: the wall stands after generation %d: the bring-up is stopped and thrown again\\n",
		    (uint64_t)(gen + 1));
		USB->stop();
		usb_ready = 0;
		usb_rx_queued = 0;
		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (stalled = 0; stalled < 25; stalled++) {
				BS->stall(1000000);
			}
		}
		if (usb_start_attempt() <= 0) {
			print("usb: the re-throw did not come back; the run goes on without the USB server\\n");
			break;
		}
	}
	if (tick != NULL) {
""")

assert src != orig, "the patch changed nothing"
open(path, "w", encoding="utf-8", newline="").write(src)

# the strings the payload/verify pins read back out of the built loader.efi
for needle in (b"usb: bulk probe gen %d beat %d: %x",
               b"usb: the bulk pair answered: armed at generation %d, beat %d",
               b"a non-wall probe answer stopped the stage",
               b"the wall stands after 3 generations",
               b"twenty-five quiet seconds before the re-throw's try",
               b"the re-throw did not come back"):
    assert needle in src.encode(), f"pin string missing after patch: {needle}"
print("patched", path)
print("hunks: 3 (forward decl + stage locals + the arm-probe/re-throw stage)")
