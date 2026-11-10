#!/usr/bin/env python3
"""Wave 23 Round 2 (v19b) loader.c delta on the v18 tree.

Coordinator-updated four items (2026-11-09, fetch23 00:59-01:02 data):
  1. Softened re-throw: a generation that saw device-state events keeps its host -- no
     detach on it (the wave22 report's first suspect: the re-throw's own detach kills the
     just-built enumeration). The first window is stretched to ~120 s (24 beats); the
     re-throw only fires after a window that saw no host at all.
  2. Service phase early: the odd probe beats go through usb_poll_command instead of the
     zero-length probe -- the receive a host command needs IS this beat's probe (the same
     DwcPrepareURB gate: taken = armed, refused = the same wall), and a command that lands
     is served on the spot. fb_command sees usb_stage_serving, so a run command in the
     stage is refused, not re-entered.
  3. Raw code passthrough: the wrapped probe print (UsbDeviceSend folds everything into
     EFI_DEVICE_ERROR -- the 7 shape) is joined by the vendor's own UsbFn layer
     (EFI_USBFN_IO_PROTOCOL, gEfiUsbfnIoProtocolGuid 32d2963a-fe5d-4f30-b633-6e5dc55803cc,
     Mu-Silicium EFIUsbfnIo.h; Transfer at +0x50, the layout cross-checked by wave22's
     [+0x90] = ConfigureEnableEndpointsEx finding). Asked once per generation, only after
     the wrapped probe already answered nonzero -- on an un-armed pair the submit is
     refused before any hardware transfer is queued, so the raw look cannot touch the
     armed path.
  4. Settle 25 s -> 5 s: the whole first settle is a structural poison window (the vendor
     callback presents the gadget in it and nothing pumps it -- every boot hands the host
     one doomed enumeration; wave22 §1). Five seconds of the same poison is five times
     less; v16's five-second settle has the "first try succeeded" precedent. The lost-race
     risk (the reason 21.2 widened it) stays covered by the 3-try + re-throw machinery.

usage: patch-loader-v19.py LOADER_C   (applies on top of the v18-patched file)
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:300]}"
    src = src.replace(old, new)

# ---- hunk 1: the stage-serving flag, beside the receive flag --------------------------------
sub("""static int usb_rx_queued;    /* the receive the loader leaves with the controller (defined below) */""",
"""static int usb_rx_queued;    /* the receive the loader leaves with the controller (defined below) */
static int usb_stage_serving;    /* Wave 23: the probe stage serves commands (usb_poll_command from
                                  * the odd beats); while it does, fb_command must refuse a run
                                  * command rather than re-enter run_kernel inside usb_start */""")

# ---- hunk 2: fb_command sees the stage -------------------------------------------------------
sub("""	int busy = run_active;""",
"""	int busy = run_active || usb_stage_serving;   /* Wave 23: the probe stage serves too */""")
sub("""			fb_reply("FAIL", "a kernel is running (oem stop ends it)");""",
"""			fb_reply("FAIL", run_active ? "a kernel is running (oem stop ends it)"
			    : "the bring-up is still arming (the run is next)");""")

# ---- hunk 3: the raw-code helper, after usb_present ------------------------------------------
sub("""	print("usb: the gadget is presented to the host (the pull-up is ours)\\n");
}

/* One bring-up attempt:""",
"""	print("usb: the gadget is presented to the host (the pull-up is ours)\\n");
}

/* Wave 23: the wall's raw code. UsbDeviceSend folds whatever the submit path returned into
 * EFI_DEVICE_ERROR (the 7 shape of Boot #34), so the probe's printed code cannot say WHICH
 * layer refused. The vendor's own UsbFn layer under it -- the EFI_USBFN_IO_PROTOCOL
 * (gEfiUsbfnIoProtocolGuid 32d2963a-fe5d-4f30-b633-6e5dc55803cc, Mu-Silicium's
 * EFIUsbfnIo.h) -- exposes the same submit unwrapped: Transfer() at protocol offset 0x50,
 * the 11th member of the struct (the layout cross-checks against wave22's disassembly: the
 * [+0x90] slot there is ConfigureEnableEndpointsEx, the 19th member). The raw look is only
 * asked after the wrapped probe has already answered nonzero: on an un-armed pair the
 * submit is refused before any hardware transfer is queued, so it cannot touch the armed
 * path; when the pair is armed the wrapped probe answers zero and the raw look never runs. */
static void
usb_probe_raw_code(uint64_t gen, uint64_t beat, uint64_t wrapped)
{
	static void *usb_fn;          /* NULL = not looked up yet, -1 = absent, else the protocol */
	typedef efi_status (EFIAPI *usbfn_transfer_t)(void *, uint8_t, uint32_t, uint64_t *, void *);

	if (usb_fn == NULL) {
		static const efi_guid usbfn_guid = { 0x32d2963a, 0xfe5d, 0x4f30, { 0xb6, 0x33, 0x6e, 0x5d, 0xc5, 0x58, 0x03, 0xcc } };

		if (EFI_ERROR(BS->locate_protocol(&usbfn_guid, NULL, (void **)&usb_fn))) {
			usb_fn = (void *)-1;
			print("usb: the vendor's UsbFn layer is not here: the wall's raw code stays unknown\\n");
		}
	}
	if (usb_fn != (void *)-1) {
		usbfn_transfer_t raw = *(usbfn_transfer_t *)((uint8_t *)usb_fn + 0x50);
		uint64_t size = 0;
		uint64_t code = (uint64_t)(uint32_t)raw(usb_fn, 1 /* the bulk OUT pair */, 0 /* the host's direction */,
		    &size, usb_rx_buf);

		print("usb: bulk probe gen %d beat %d: %x (wrapped); the same submit through UsbFn (raw): %x\\n",
		    gen, beat, wrapped, code);
	}
}

/* One bring-up attempt:""")

# ---- hunk 4: the settle, twenty-five -> five seconds -----------------------------------------
sub(""" * part of an hour, i.e. with the platform fully settled). So the init event is signaled and
 * the platform gets twenty-five quiet seconds (Wave 21.2 widened the settle from five) to run
 * its UsbConfigDxe callback (and the RPM/DAL clocks behind it) before the first start_ex
 * touches the controller; the wait is a timer event, which also pumps the firmware's queue
 * and its watchdog. A failed try is retried twenty-five seconds later, three tries in all""",
""" * part of an hour, i.e. with the platform fully settled). So the init event is signaled and
 * the platform gets five quiet seconds (Wave 23 narrowed Wave 21.2's twenty-five: the whole
 * settle is a poison window -- the callback presents the gadget inside it and nothing pumps
 * it, so every boot hands the host one doomed enumeration) to run its UsbConfigDxe callback
 * (and the RPM/DAL clocks behind it) before the first start_ex touches the controller; the
 * wait is a timer event, which also pumps the firmware's queue and its watchdog. A failed
 * try is retried twenty-five seconds later, three tries in all""")
sub("""		print("usb: the platform is asked up; twenty-five quiet seconds before the first try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (r = 0; r < 25; r++) {
				BS->stall(1000000);
			}
		}""",
"""		print("usb: the platform is asked up; five quiet seconds before the first try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 50000000 /* five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (r = 0; r < 5; r++) {
				BS->stall(1000000);
			}
		}""")

# ---- hunk 5: the stage itself -- host_seen, the stretched first window, the serving beats,
#      the raw code, the softened re-throw -----------------------------------------------------
sub("""	void *tick = NULL;
	int tries = 0, r, stalled, gen, beat, verdict;""",
"""	void *tick = NULL;
	int tries = 0, r, stalled, gen, beat, verdict, host_seen;""")

sub("""	for (gen = 0; usb_ready && gen < 3; gen++) {
		verdict = 0;         /* 0 the wall through every beat, 1 armed, 2 a non-wall answer */
		for (beat = 0; beat < 6; beat++) {""",
"""	for (gen = 0; usb_ready && gen < 3; gen++) {
		verdict = 0;         /* 0 the wall through every beat, 1 armed, 2 a non-wall answer */
		host_seen = 0;       /* Wave 23: a device state event in this generation = a host out there */
		for (beat = 0; beat < (gen == 0 ? 24 : 6); beat++) {   /* Wave 23: the first window is
		                                  stretched to ~two minutes -- a host that needs the
		                                  longer grace gets it before any detach is thrown */""")

sub("""			USB->handle_event(&msg, &size, &data);
			if (msg == UsbDeviceEventDeviceStateChange) {
				usb_connected = (data.device_state == UsbDeviceStateConnected);
			}
			probe = USB->send(USB_EP_OUT, 0, usb_rx_buf);""",
"""			USB->handle_event(&msg, &size, &data);
			if (msg == UsbDeviceEventDeviceStateChange) {
				usb_connected = (data.device_state == UsbDeviceStateConnected);
				if (!host_seen) {
					print("usb: a host is out there (a device state change at gen %d beat %d): the re-throw is softened\\n",
					    (uint64_t)gen, (uint64_t)beat);
				}
				host_seen = 1;
			}
			if (usb_rx_queued) {
				verdict = 1;     /* a receive stands with the controller: DwcPrepareURB took it,
				                    which only an armed pair does */
				break;
			}
			if ((beat & 1) != 0) {
				/* Wave 23: the odd beats serve AND probe in one submit: the receive a host
				 * command needs goes through the same gate as the zero-length probe -- taken
				 * = the pair is armed (and a command that landed is served on the spot;
				 * fb_command sees usb_stage_serving, so a run command here is refused, not
				 * re-entered); refused = the same wall, the even beats keep printing its code. */
				usb_stage_serving = 1;
				usb_poll_command();
				usb_stage_serving = 0;
				continue;
			}
			probe = USB->send(USB_EP_OUT, 0, usb_rx_buf);""")

sub("""			print("usb: bulk probe gen %d beat %d: %x\\n", (uint64_t)gen, (uint64_t)beat, probe);
			/* any nonzero answer = the submit was rejected = the pair is not armed: the next
			 * beat gives the host's SET_CONFIG walk another five seconds (the codes stay on
			 * the record -- they are the next attribution round's input) */
		}""",
"""			print("usb: bulk probe gen %d beat %d: %x\\n", (uint64_t)gen, (uint64_t)beat, probe);
			if (beat == 0) {
				usb_probe_raw_code((uint64_t)gen, (uint64_t)beat, (uint64_t)(uint32_t)probe);
			}
			/* any nonzero answer = the submit was rejected = the pair is not armed: the next
			 * beat gives the host's SET_CONFIG walk another five seconds (the codes stay on
			 * the record -- they are the next attribution round's input) */
		}""")

sub("""		print("usb: the pair is un-armed after generation %d (last %x): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), probe);
		usb_rx_queued = 0;""",
"""		if (host_seen) {
			/* Wave 23: a host was seen in this generation -- a re-throw's detach would kill
			 * the enumeration it just built (wave22's first suspect for the dead cycles).
			 * The present stays, the pumping continues, and the next generation's window
			 * opens without touching the controller: the SET_CONFIG walk keeps its chances. */
			print("usb: generation %d kept its host: no re-throw, the present stays and the stage keeps beating\\n",
			    (uint64_t)gen);
			continue;
		}
		print("usb: the pair is un-armed after generation %d (last %x): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), probe);
		usb_rx_queued = 0;""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: 8 hunks applied, {len(orig)} -> {len(src)} bytes")
