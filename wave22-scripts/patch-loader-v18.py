#!/usr/bin/env python3
"""Wave 22 (v0.4 final battle three: host visibility) loader.c delta on the v17b tree.

Wave 21.5's verdict: the fix mechanism ran perfectly (18 probes, two re-throws, the
calibrated discriminator) but the host never enumerated once across two rounds -- ep0 did
not answer the host's descriptor requests. This round's disassembly of the vendor pair
(WSL ~/f12, UsbfnDwc3Dxe/UsbDeviceDxe) found the structural cause, and it is neither
pumping alone nor descriptors -- it is WHO raises the pull-up and WHEN:

  - The vendor connect (fcn.000161e0: wait, config via fcn.00013868, then
    DCTL.RUN_STOP |= bit31 at 0x1632c-0x1635c) is only driven by the platform's
    bring-up callback (fcn.0001609c) -- which fires in the pumpless settle window,
    before the loader has even located the USB protocol.
  - Our start_ex's own ConfigureEnableEndpointsEx (the [+0x90] slot, fcn.00012580)
    OPENS by disconnecting a prior connect (fcn.0001609c -> fcn.000161e0(dev, 0) at
    0x125e0: the vendor StopController, RUN_STOP cleared at 0x14dbc) and NEVER
    re-presents: its tail (fcn.00016080) only resets state fields.
  - So every boot showed the host a device exactly in the window nothing pumped, and
    kept the bus silent (RUN_STOP=0) through every window the loader does pump: the
    probe stage, the run, the service loop. Forty minutes of 0000:0002 across two
    rounds, explained -- the host never once saw an attach with pumping alive.

v18 answers with the wave's two moves, both at the loader level:
  1. Pump-forward: every wait past the first successful start_ex now runs at a tick's
     cadence (twenty milliseconds), each wake pumping handle_event (the probe beats'
     five-second gaps and the re-throws' twenty-five-second quiets alike). Pumping
     stays confined to post-config states: before a start_ex has configured the
     vendor's event buffer the ring pointer is the platform's business, not ours.
  2. Self-presentation (the forced re-enumeration linkage): after every successful
     start_ex -- our descriptor set walked, ep0 armed, the control state machine
     active -- the loader raises the pull-up itself: the same single-bit write the
     vendor's connect ends with (DCTL bit 31), now in a pumped window. Each re-throw's
     start_ex drops it again (a real detach), so every generation is a clean
     detach->attach pair; and the pull-up stays up for the whole session, so the host
     can enumerate at any point of the run or service phases (the run/service loops
     already pump at millisecond cadence -- v15's shape).

usage: patch-loader-v18.py LOADER_C   (applies on top of the v17b-patched file)
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

# ---- hunk 1: the two Wave 22 helpers, after usb_dwc3_wake (needs USB, BS, wdt_pet, the
#      event types -- all defined above this point) ------------------------------------------------
sub("""	usb_dwc3_susphy_off();                        /* reset restored defaults: un-gate again */
	print("usb: dwc3 woken (phy suspend off + core soft reset)\\n");
}

/* One bring-up attempt:""",
"""	usb_dwc3_susphy_off();                        /* reset restored defaults: un-gate again */
	print("usb: dwc3 woken (phy suspend off + core soft reset)\\n");
}

/* Wave 22's pump-forward. The vendor's ep0 machinery -- the descriptor answers that make
 * the host's enumeration, and the SET_CONFIG walk that arms the bulk pair -- advances only
 * under handle_event's dispatch, and the host's control timeout is on the order of five
 * seconds: the waits Wave 21.5 inherited (five-second beats, twenty-five-second quiets)
 * left every host request that landed inside them sitting un-dispatched past that timeout.
 * So every wait past a successful start_ex now runs at a tick's cadence (twenty
 * milliseconds), each wake pumping the queue; the periodic timer is kept because its
 * slices still drive the firmware's own event queue and watchdog (the settle-window
 * lesson), and the loader's watchdog gets its pet. Pumping begins only once a start_ex
 * has configured the vendor's event buffer: before that the ring pointer belongs to the
 * platform, and calling in would read a ring nobody built. */
static void
usb_wait_pumped(void *tick, uint64_t slices)
{
	/* create_event/set_timer/wait_for_event are unused elsewhere, so efi.h leaves them untyped */
	typedef efi_status (EFIAPI *set_timer_t)(void *event, uint32_t kind, uint64_t time);
	typedef efi_status (EFIAPI *wait_for_event_t)(uint64_t count, void **events, uint64_t *index);
	set_timer_t set_timer = (set_timer_t)BS->set_timer;
	wait_for_event_t wait_for_event = (wait_for_event_t)BS->wait_for_event;
	uint64_t index;

	if (tick != NULL) {
		set_timer(tick, 1 /* TimerPeriodic */, 200000 /* twenty milliseconds, in 100 ns */);
	}
	while (slices-- != 0) {
		uint32_t msg = UsbDeviceEventNoEvent;
		uint64_t size = 0;
		usb_device_event_data data;

		if (tick != NULL) {
			if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
				BS->stall(200000);       /* the timer refused: a plain slice of the same length */
			}
		} else {
			BS->stall(200000);           /* no timer here: plain slices */
		}
		USB->handle_event(&msg, &size, &data);
		if (msg == UsbDeviceEventDeviceStateChange) {
			usb_connected = (data.device_state == UsbDeviceStateConnected);
		}
		if ((slices & 63) == 62) {
			wdt_pet();                   /* about once a second across a long wait */
		}
	}
	if (tick != NULL) {
		set_timer(tick, 0 /* TimerCancel */, 0);
	}
}

/* Wave 22: present the gadget to the host ourselves. The vendor's own connect -- the
 * platform bring-up callback's path (fcn.000161e0: wait, configure, then
 * DCTL.RUN_STOP |= bit31, 0x1632c-0x1635c) -- fires in the pumpless settle window, and our
 * start_ex's own ConfigureEnableEndpointsEx (the [+0x90] slot, fcn.00012580) opens by
 * disconnecting a prior connect (fcn.0001609c -> fcn.000161e0(dev, 0): the vendor
 * StopController clears the same bit, 0x14dbc) and never re-presents. The net since v15:
 * the host saw the device only in the window nothing pumped, and the bus stayed silent
 * through every pumped one (wave21_5: forty minutes of 0000:0002 across two rounds). So
 * after every successful start_ex -- our descriptor set walked, ep0 armed, the control
 * state machine active -- the loader raises the pull-up itself: the same single-bit write
 * the vendor's connect ends with, now in a window the loader pumps at a tick's cadence.
 * Each re-throw's start_ex drops it again (a real detach for the host), so every
 * generation is a clean detach->attach pair; left up for the whole session, the host can
 * enumerate at any point of the run or service phases. The register shape is the wake's
 * precedent (DCTL at 0x0A600000+0xC704, platform_phk110 only). */
static void
usb_present(void)
{
	volatile uint32_t *dctl = (volatile uint32_t *)(uintptr_t)0x0A60C704ULL;        /* DCTL */

	if (PLAT != &platform_phk110) {
		return;
	}
	BS->stall(50000);             /* five milliseconds of bus silence before the pull-up */
	*dctl |= 1u << 31;            /* RUN/Stop: the pull-up, the vendor connect's own tail */
	print("usb: the gadget is presented to the host (the pull-up is ours)\\n");
}

/* One bring-up attempt:""")

# ---- hunk 2: present after every successful start_ex (boot tries AND re-throws) -----------------
sub("""		usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
		usb_ready = 1;
		return 1;""",
"""		usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
		usb_ready = 1;
		usb_present();           /* Wave 22: the pull-up -- a fresh attach in a pumped window */
		return 1;""")

# ---- hunk 3: the probe beat gap pumps continuously instead of one pump per gap ------------------
sub("""			if (beat != 0) { /* five seconds between probes; the timer event keeps the
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
			}""",
"""			if (beat != 0) {
				usb_wait_pumped(tick, 250);   /* Wave 22: the whole beat gap at the tick's
				                                 cadence, each wake pumping -- a host SETUP
				                                 landing in it is answered in one slice */
			}""")

# ---- hunk 4: the re-throw quiet pumps too (the platform callback's connect lands there) ---------
sub("""		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (stalled = 0; stalled < 25; stalled++) {
				BS->stall(1000000);
			}
		}""",
"""		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		usb_wait_pumped(tick, 1250);   /* Wave 22: the quiet pumps too -- the callback's connect
		                                  lands here (it is what asserts the pull-up in this
		                                  window), and a host arriving in it is answered */""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: 4 hunks applied, {len(orig)} -> {len(src)} bytes")
