#!/usr/bin/env python3
"""Wave 24 (Exp-1 diagnostic) loader.c delta on the v19b tree (v18 + Wave 23 Round 2).

The wall is confirmed at the instruction level: DwcPrepareURB refuses because the
vendor's SOFTWARE endpoint state phys[2] is zero (0x8000000C). What nobody has yet seen
is the step that leaves it at zero. This round buys that answer with four moves, all in
the loader, no vendor bytes touched:

  1. Console mirror: the desk check (UsbfnDwc3Dxe disassembly, fcn.0001c044 ->
     fcn.0001f258 -> shim HOB gEfiShimLibraryHobGuid -> device "SerialPort Lib" ->
     [dev+0x10]) shows the vendor's DebugPrint sinking through the platform shim's
     SerialPort console, NOT through ConOut. The loader walks that same chain and wraps
     the device's write member, so every vendor debug byte -- the four-line wall AND the
     leading errors (DEPSTARTCFG Fails / Failed to set config for ep / DwcConfigureEP
     failed / Unknown USB Speed) -- lands in the log ring and rides the logdump out.
     The leading strings are additionally sticky-printed by the loader (one line each,
     first occurrence). ConOut is wrapped too (the shim writer may paint through it);
     both doors share one in-flight flag, and put_char flags its own writes so nothing
     is logged twice. A mirror that finds no door says so once and hurts nothing.

  2. One event consumer (F1): usb_pump() is the only handle_event call site. Bounded
     drain (8) with the backlog shape recorded; state events update the host book
     (Connected sets usb_host_seen and samples once; Disconnected retires the standing
     receive and never counts as a host); transfer completions land in a per-endpoint
     pending store for the caller to serve. usb_wait_pumped also loses its 200 ms
     fallback slices (stall(200000) is 200 ms, ten times the 20 ms slice).

  3. One standing receive: a real 511-byte OUT request stays with the controller (the
     receive a command needs IS the wall's gate; the zero-length probe is retired -- no
     contention, one request identity stamped with the bring-up generation). The
     refused submit is rate limited at the SOURCE (each refusal costs the vendor's own
     four-line wall: the submit waits out 1 s -> 30 s backoff, the pump never stops),
     the first refusal prints in full, the repeats count and print at the backoff's
     beat only.

  4. The samples the judgment table turns on, at three moments (present / first host
     progress / failure window's end): GCTL DCTL DSTS DALEPENA read back, plus the
     vendor's own UsbFn instance -- derivable because the vendor's Transfer walks
     usb_fn-8 and checks the 'usbf' signature (fcn.000130bc): speed at instance+0x184,
     the physical endpoint table at instance+0, 0x20 stride (state +0x18, maxpacket
     +0x30; phys[2] = EP1-OUT, phys[3] = EP1-IN). NOTHING is read before the signature
     check passes (H2's zero-column trap is only real through a verified layout).
     GCTL bit11 is cleared by hand if the soft reset never settles (P1-1; Linux clears
     CORESOFTRESET explicitly). The raw UsbFn look moves from beat 0 to the failure
     window's END, once per generation, with abort cleanup (v19b asked it at the one
     beat whose normal answer is "not yet configured"). The buffer allocations are
     split and freed apart (P2-5). The timeline is one monotonic clock from usb_start.

usage: patch-loader-v24.py LOADER_C   (applies on top of the v19b-patched file)
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:400]}"
    src = src.replace(old, new)

# ---- hunk 1: put_char flags its own console writes (the mirror must not double-log) ----------
sub("""static void
put_char(char c)
{""",
"""static int in_own_print;         /* put_char's own console writes: the mirror must not log them twice */

static void
put_char(char c)
{""")
sub("""		ST->con_out->output_string(ST->con_out, w);
	}
}""",
"""		in_own_print = 1;
		ST->con_out->output_string(ST->con_out, w);
		in_own_print = 0;
	}
}""")

# ---- hunk 2: the console mirror, after clean_dcache ------------------------------------------
sub("""static void
clean_dcache(uint64_t start, uint64_t end)
{
	uint64_t line = 4ULL << ((READ_SYSREG(CTR_EL0) >> 16) & 0xF);
	for (uint64_t p = start & ~(line - 1); p < end; p += line) {
		__asm__ volatile ("dc cvac, %0" : : "r" (p));
	}
	__asm__ volatile ("dsb sy");
}

/* ------------------------------------------------------------------------ */
/* Log persistence: raw write to a GPT partition (phone only)               */""",
"""static void
clean_dcache(uint64_t start, uint64_t end)
{
	uint64_t line = 4ULL << ((READ_SYSREG(CTR_EL0) >> 16) & 0xF);
	for (uint64_t p = start & ~(line - 1); p < end; p += line) {
		__asm__ volatile ("dc cvac, %0" : : "r" (p));
	}
	__asm__ volatile ("dsb sy");
}

/* ------------------------------------------------------------------------ */
/* Wave 24: the console mirror.                                             */
/*                                                                          */
/* The vendor's debug lines -- the four-line wall AND the leading errors the */
/* judgment table turns on (DEPSTARTCFG Fails / Failed to set config for ep */
/* / DwcConfigureEP failed / Unknown USB Speed) -- never reached the loader  */
/* log: the desk check (UsbfnDwc3Dxe disassembly) shows Qualcomm's DebugPrint */
/* (fcn.0001c044) sinking its formatted bytes through the platform shim's    */
/* console device named "SerialPort Lib" (gEfiShimLibraryHobGuid HOB ->      */
/* [shim+0x10]("SerialPort Lib", 0, &dev) -> [dev+0x10](buf, len)), not      */
/* through ConOut. The loader walks the same chain and wraps the device's    */
/* write member, so every vendor debug byte lands in the log ring beside our */
/* own lines and rides the logdump out. The ConOut door is wrapped too (the  */
/* shim's writer may itself paint through the console): the two doors share  */
/* one in-flight flag, so a chain of doors mirrors once, and put_char flags  */
/* its own writes so nothing is logged twice. A mirror that finds no door    */
/* says so once and hurts nothing: the copy is bounded writes into the ring */
/* and the original call is made no matter what.                            */

static int mirror_busy;
static uint64_t mirror_bytes, mirror_drops;
static uint64_t mirror_lead_hits[4];

static void
mirror_take(const char *data, uint64_t len)
{
	static const char *const leads[4] = {
		"DEPSTARTCFG Fails", "Failed to set config for ep", "DwcConfigureEP failed", "Unknown USB Speed"
	};
	uint64_t i, k;
	uint64_t room = sizeof(log_buf) - 6144;   /* the vendor never takes the tail our lines need */

	for (i = 0; i < len && data[i] != 0; i++) {
		char c = data[i];

		if (c == '\\r') {
			continue;
		}
		if (log_len >= room) {
			if (mirror_drops == 0) {
				print("usb: the mirror hit its budget after %d bytes: the vendor lines drop from here (the loader's lines keep their room)\\n",
				    mirror_bytes);
			}
			mirror_drops++;
			return;
		}
		log_buf[log_len++] = c;
		mirror_bytes++;
	}
	for (k = 0; k < 4; k++) {
		const char *l = leads[k];
		uint64_t n = str_len(l), scan, m;

		if (mirror_lead_hits[k] != 0 || len < n) {
			continue;
		}
		for (scan = 0; scan + n <= len; scan++) {
			for (m = 0; m < n && data[scan + m] == l[m]; m++) {
			}
			if (m == n) {
				mirror_lead_hits[k] = 1;
				print("usb: the vendor said '%s': the line is sticky now (the mirror keeps the full text)\\n", l);
				break;
			}
		}
	}
}

typedef efi_status (EFIAPI *sto_string_t)(struct efi_text_output *self, const char16 *str);
static sto_string_t con_out_orig;

static efi_status EFIAPI
mirror_con_string(struct efi_text_output *self, const char16 *str)
{
	if (!mirror_busy && !in_own_print && str != NULL) {
		char buf[128];
		uint64_t n = 0;
		const char16 *p;

		for (p = str; *p != 0 && n < sizeof(buf); p++) {
			char c = (char)(*p & 0xff);

			buf[n++] = (c < 32 && c != '\\n' && c != '\\t') ? '.' : c;
		}
		if (n != 0) {
			mirror_busy = 1;
			mirror_take(buf, n);
			mirror_busy = 0;
		}
	}
	return con_out_orig(self, str);
}

typedef long (EFIAPI *shim_write_t)(void *dev, const char *buf, uint64_t len);
static shim_write_t shim_write_orig;

static long EFIAPI
mirror_shim_write(void *dev, const char *buf, uint64_t len)
{
	if (!mirror_busy && buf != NULL && len != 0 && len < 4096) {
		mirror_busy = 1;
		mirror_take(buf, len);
		mirror_busy = 0;
	}
	return shim_write_orig != NULL ? shim_write_orig(dev, buf, len) : 0;
}

static void
mirror_install(void)
{
	static const efi_guid hob_list_guid = { 0x7739f24c, 0x93d7, 0x11d4, { 0x9a, 0x3a, 0x00, 0x90, 0x27, 0x3f, 0xc1, 0x4d } };
	static const efi_guid shim_hob_guid = { 0xbedaeabc, 0x5e70, 0x4d66, { 0x97, 0x33, 0x21, 0x3d, 0x07, 0x2b, 0x9d, 0x04 } };
	typedef long (EFIAPI *shim_locator_t)(const char *name, uint64_t flags, void **out);
	uint64_t i;
	uint8_t *hob, *shim = NULL;
	void *dev = NULL;
	shim_locator_t locator;
	int vendor_door = 0;

	if (ST == NULL || ST->tables == NULL) {
		return;
	}
	for (i = 0; i < ST->nr_tables; i++) {
		if (memcmp(&ST->tables[i].guid, &hob_list_guid, sizeof(efi_guid)) == 0) {
			break;                    /* DxeCore parks the HOB list in the configuration table */
		}
	}
	if (i < ST->nr_tables && ST->tables[i].table != NULL) {
		for (hob = (uint8_t *)ST->tables[i].table;;) {
			uint16_t type = (uint16_t)(hob[0] | (hob[1] << 8));
			uint16_t hlen = (uint16_t)(hob[2] | (hob[3] << 8));

			if (type == 0xffff || hlen < 0x18) {
				break;                /* the list's end (or a broken header): no shim block */
			}
			if (type == 4 /* EFI_HOB_TYPE_GUID_EXTENSION */ &&
			    memcmp(hob + 8, &shim_hob_guid, sizeof(efi_guid)) == 0) {
				shim = *(uint8_t **)(hob + 0x18);
				break;
			}
			hob += hlen;
		}
	}
	if (shim != NULL) {
		locator = *(shim_locator_t *)(shim + 0x10);
		/* (the locator's return convention is the vendor's own; the device pointer in OUR
		 * slot is the only contract the lazy-init path relies on, so that is what we check) */
		if (locator != NULL) {
			locator("SerialPort Lib", 0, &dev);
		}
		if (dev != NULL) {
			shim_write_orig = *(shim_write_t *)((uint8_t *)dev + 0x10);
			if (shim_write_orig != NULL) {
				*(shim_write_t *)((uint8_t *)dev + 0x10) = mirror_shim_write;
				vendor_door = 1;
				/* the probe, out through the wrapped member: the mirror captures its own
				 * echo, and that one line in the ring is the end-to-end proof */
				(*(shim_write_t *)((uint8_t *)dev + 0x10))(dev,
				    "usb: the vendor debug door echoes: the mirror is in\\n",
				    str_len("usb: the vendor debug door echoes: the mirror is in\\n"));
			}
		}
	}
	if (ST->con_out != NULL && ST->con_out->output_string != NULL) {
		con_out_orig = ST->con_out->output_string;
		ST->con_out->output_string = mirror_con_string;
	}
	print("usb: the console mirror: vendor door %s, console door %s\\n",
	    vendor_door ? "hooked (the shim's SerialPort Lib)" : "NOT FOUND (vendor lines stay off the log)",
	    con_out_orig != NULL ? "hooked" : "absent");
}

/* ------------------------------------------------------------------------ */
/* Log persistence: raw write to a GPT partition (phone only)               */""")

# ---- hunk 3: efi_main installs the mirror ----------------------------------------------------
sub("""	BS->set_watchdog_timer(0, 0, 0, NULL);
	/* no payload in memory (nobody put one there): the volume this loader came from may have one, as a UEFI boot loader's does */""",
"""	BS->set_watchdog_timer(0, 0, 0, NULL);
	mirror_install();             /* Wave 24: the vendor's debug door, before anything talks */
	/* no payload in memory (nobody put one there): the volume this loader came from may have one, as a UEFI boot loader's does */""")

# ---- hunk 4: GCTL bit11 cleared by hand if the soft reset never settles (P1-1) ----------------
sub("""	*gctl = *gctl | (1u << 11);                   /* CSFTRST */
	while (*gctl & (1u << 11)) {
		if (READ_SYSREG(CNTVCT_EL0) - began > freq) {
			print("usb: dwc3 soft reset did not settle in one second\\n");
			break;
		}
	}""",
"""	*gctl = *gctl | (1u << 11);                   /* CSFTRST */
	while (*gctl & (1u << 11)) {
		if (READ_SYSREG(CNTVCT_EL0) - began > freq) {
			print("usb: dwc3 soft reset did not settle in one second\\n");
			break;
		}
	}
	if (*gctl & (1u << 11)) {
		*gctl &= ~(1u << 11);         /* P1-1: Linux clears CORESOFTRESET by hand; a reset
		                                 left asserted holds the register domain down */
		print("usb: dwc3 core soft reset was still set after the wait: cleared by hand (GCTL now %x)\\n",
		    (uint64_t)*gctl);
	}""")

# ---- hunk 5: the diagnosis rig replaces the two Wave 23 statics -------------------------------
sub("""static int usb_rx_queued;    /* the receive the loader leaves with the controller (defined below) */
static int usb_stage_serving;    /* Wave 23: the probe stage serves commands (usb_poll_command from
                                  * the odd beats); while it does, fb_command must refuse a run
                                  * command rather than re-enter run_kernel inside usb_start */""",
"""/* ------------------------------------------------------------------------ */
/* Wave 24: the diagnosis rig. One event consumer, one standing receive, one */
/* failure gate, one state sampler -- and the four checkpoints recorded      */
/* apart: (1) the standing receive's submit succeeds (usb_arm_rx),           */
/* (2) the host's write completes (the host side's own record), (3) the      */
/* completion event routed through the pump (usb_pump -> usb_done_out),      */
/* (4) the IN reply's completions (counted in the sampler). The judgment     */
/* table needs the layer that LEFT the endpoint state at zero, so the        */
/* samples take the vendor's own UsbFn instance apart: the vendor's Transfer */
/* walks usb_fn-8 and checks the 'usbf' signature (fcn.000130bc), which      */
/* makes the instance address derivable -- speed at instance+0x184, the      */
/* physical endpoint table at instance+0 with 0x20 stride (state +0x18,      */
/* maxpacket +0x30 per entry; phys[2] = EP1-OUT = USB_EP_OUT, phys[3] =      */
/* EP1-IN). Nothing is read before that signature says the layout is the     */
/* one the disassembly showed.                                               */

static int usb_stage_serving;    /* Wave 23: the probe stage serves commands (usb_poll_command
                                  * from the beats); while it does, fb_command must refuse a run
                                  * command rather than re-enter run_kernel inside usb_start */

static int usb_rx_queued;        /* the standing receive: submitted, not yet completed */
static uint64_t usb_rx_gen;      /* its identity: bumped at every start_ex and re-throw */
static uint32_t usb_arm_code;    /* the last refused submit's code (the wall's shape) */
static uint64_t usb_arm_ok, usb_wall_count, usb_cp1, usb_cp3_ok, usb_cp3_bad;
static int usb_host_seen;        /* a Connected event this bring-up (Disconnected never sets it) */
static uint64_t usb_disconnects; /* the latch usb_wait watches for a mid-transfer detach */
static uint64_t usb_state_conn, usb_state_gone;
static uint64_t usb_tx_done, usb_tx_err;
static uint64_t usb_t0;          /* the session's monotonic timeline (CNTVCT at usb_start) */
static uint64_t usb_pump_calls, usb_pump_events, usb_pump_max, usb_pump_gap, usb_pump_last;
static void *usb_fn;             /* NULL not looked up, (void *)-1 absent, else the UsbFn protocol */

struct usb_done { int live; uint32_t status; uint64_t bytes; };
static struct usb_done usb_done_out, usb_done_in;

static uint64_t
usb_age(void)
{
	return usb_t0 == 0 ? 0 : (READ_SYSREG(CNTVCT_EL0) - usb_t0) * 10 / READ_SYSREG(CNTFRQ_EL0);
}

static int
usb_fn_locate(void)
{
	static const efi_guid usbfn_guid = { 0x32d2963a, 0xfe5d, 0x4f30, { 0xb6, 0x33, 0x6e, 0x5d, 0xc5, 0x58, 0x03, 0xcc } };

	if (usb_fn == (void *)-1) {
		return 0;
	}
	if (usb_fn == NULL) {
		if (EFI_ERROR(BS->locate_protocol(&usbfn_guid, NULL, (void **)&usb_fn))) {
			usb_fn = (void *)-1;
			print("usb: the vendor's UsbFn layer is not here: the wall's raw code stays unknown\\n");
			return 0;
		}
	}
	return 1;
}

/* The failure gate. The submit itself is rate limited (each refusal costs the vendor's
 * own four-line debug wall -- the flood's source was our own submit-per-pass): after a
 * refusal the next submit waits out the backoff, one second doubling to thirty. The
 * first refusal prints in full; the repeats print only at the backoff's beat, with the
 * running count. The pump never stops. */
static uint64_t gate_next, gate_backoff;

static int
usb_wall_gate(uint32_t code)
{
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), now = READ_SYSREG(CNTVCT_EL0);
	uint64_t a = usb_age();

	usb_wall_count++;
	usb_arm_code = code;
	if (usb_wall_count == 1) {
		print("usb: [t+%d.%d] the bulk receive is refused: %x (the first refusal is on the record; the repeats are counted and backed off)\\n",
		    a / 10, a % 10, (uint64_t)code);
		gate_backoff = freq;
		gate_next = now + gate_backoff;
		return 1;
	}
	gate_backoff *= 2;
	if (gate_backoff > 30 * freq) {
		gate_backoff = 30 * freq;
	}
	gate_next = now + gate_backoff;
	print("usb: [t+%d.%d] refused %x again (x%d since the first; quiet for %d s now)\\n",
	    a / 10, a % 10, (uint64_t)code, usb_wall_count, gate_backoff / freq);
	return 1;
}

static void
usb_gate_reset(void)
{
	gate_next = 0;
	gate_backoff = 0;
	/* (usb_wall_count and usb_arm_code survive: they are the window's totals) */
}

/* The state sampler: the registers, then the vendor's own fields behind the signature
 * check. This is the three-moment evidence the judgment table reads (present / first
 * host progress / failure window's end). */
static void
usb_sample_state(const char *when)
{
	static const char *const speed_name[8] = { "unknown(0)", "LS", "FS", "HS", "SS", "SSP", "?", "?" };
	volatile uint32_t *gctl = (volatile uint32_t *)(uintptr_t)0x0A60C110ULL;
	volatile uint32_t *dctl = (volatile uint32_t *)(uintptr_t)0x0A60C704ULL;
	volatile uint32_t *dsts = (volatile uint32_t *)(uintptr_t)0x0A60C708ULL;
	volatile uint32_t *alepena = (volatile uint32_t *)(uintptr_t)0x0A60C720ULL;
	uint64_t a = usb_age();

	if (PLAT != &platform_phk110) {
		return;
	}
	print("usb: [t+%d.%d] sample %s: GCTL %x DCTL %x DSTS %x DALEPENA %x\\n",
	    a / 10, a % 10, when, (uint64_t)*gctl, (uint64_t)*dctl, (uint64_t)*dsts, (uint64_t)*alepena);
	if (!usb_fn_locate()) {
		return;
	}
	{
		uint8_t *inst = (uint8_t *)usb_fn - 8;    /* the vendor's own walk: Transfer checks the
		                                             'usbf' signature one pointer below */
		uint64_t sig = *(volatile uint64_t *)inst & 0xffffffffULL;

		if (sig != 0x66627573ULL /* 'usbf' */) {
			print("usb: [t+%d.%d] sample %s: the UsbFn pointer carries no 'usbf' below (%x): the vendor fields stay unread\\n",
			    a / 10, a % 10, when, sig);
			return;
		}
		print("usb: [t+%d.%d] sample %s (vendor): speed %d (%s) phys[2] state %d maxpkt %d phys[3] state %d; pump %d calls %d events (max drain %d, max gap %d s), rx gen %d queued %d\\n",
		    a / 10, a % 10, when,
		    (uint64_t)*(volatile uint32_t *)(inst + 0x184),
		    (uint64_t)speed_name[*(volatile uint32_t *)(inst + 0x184) & 7],
		    (uint64_t)*(volatile uint32_t *)(inst + 0x58),
		    (uint64_t)*(volatile uint32_t *)(inst + 0x70),
		    (uint64_t)*(volatile uint32_t *)(inst + 0x78),
		    usb_pump_calls, usb_pump_events, usb_pump_max,
		    usb_pump_gap / READ_SYSREG(CNTFRQ_EL0), usb_rx_gen, usb_rx_queued);
	}
}

/* THE event consumer (F1's fix). Every handle_event in the loader runs here: the
 * waiting helper, the stage, the command service. One call drains at most eight events
 * (the backlog shape is recorded, not guessed); state events update the host book
 * (Connected sets usb_host_seen and samples once; Disconnected retires the standing
 * receive and never counts as a host); transfer completions land in the per-endpoint
 * pending store for the caller to serve. */
#define USB_PUMP_BUDGET 8

static void
usb_pump(void)
{
	uint64_t now = READ_SYSREG(CNTVCT_EL0);
	int drained;

	if (usb_pump_last != 0 && now - usb_pump_last > usb_pump_gap) {
		usb_pump_gap = now - usb_pump_last;
	}
	usb_pump_last = now;
	for (drained = 0; drained < USB_PUMP_BUDGET; drained++) {
		uint32_t msg = UsbDeviceEventNoEvent;
		uint64_t size = 0;
		usb_device_event_data data;

		USB->handle_event(&msg, &size, &data);
		usb_pump_calls++;
		if (msg == UsbDeviceEventNoEvent) {
			break;
		}
		usb_pump_events++;
		if ((uint64_t)(drained + 1) > usb_pump_max) {
			usb_pump_max = drained + 1;
		}
		if (msg == UsbDeviceEventDeviceStateChange) {
			if (data.device_state == UsbDeviceStateConnected) {
				usb_state_conn++;
				usb_connected = 1;
				if (!usb_host_seen) {
					usb_host_seen = 1;
					usb_sample_state("first-host");   /* the timeline's ConnectDone moment */
				}
			} else {
				usb_state_gone++;
				usb_connected = 0;
				usb_disconnects++;
				if (usb_rx_queued) {
					usb_rx_queued = 0;    /* P2-4: the receive's life follows the bus's */
					print("usb: the host left: the standing receive (gen %d) is retired\\n", usb_rx_gen);
				}
			}
		} else if (msg == UsbDeviceEventTransferNotification) {
			uint8_t ep = data.transfer.endpoint_index;
			int ok = data.transfer.status == UsbDeviceTransferStatusCompleteOK;

			if (ep == USB_EP_OUT) {
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
		}
	}
}

/* The standing receive: one non-zero-length OUT request kept with the controller for
 * the whole session -- the receive a host command needs IS the wall's gate now (the
 * zero-length probe is retired: two submits on one pair contended, and the wall's
 * flood was the probe path's). The submit's return code is checkpoint 1; the completion
 * through the pump is checkpoint 3. */
static void
usb_arm_rx(void)
{
	efi_status s;

	if (usb_rx_queued) {
		return;
	}
	if (gate_next != 0 && READ_SYSREG(CNTVCT_EL0) < gate_next) {
		return;         /* the wall is up: the submit waits out the backoff */
	}
	s = USB->send(USB_EP_OUT, 511, usb_rx_buf);
	if (EFI_ERROR(s)) {
		usb_wall_gate((uint32_t)s);
		return;
	}
	usb_arm_ok++;
	usb_cp1++;
	usb_rx_queued = 1;
	usb_gate_reset();
	if (usb_cp1 == 1) {
		print("usb: [t+%d.%d] checkpoint-1: the standing receive is in (gen %d, 511 bytes, submit %x): the pair took a real receive\\n",
		    usb_age() / 10, usb_age() % 10, usb_rx_gen, (uint64_t)(uint32_t)s);
		usb_sample_state("armed");    /* the walk's evidence: did the state bytes turn nonzero */
	}
}""")

# ---- hunk 6: usb_wait_pumped runs on the one consumer; the fallback slices lose a zero --------
sub("""	if (tick != NULL) {
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
	}""",
"""	if (tick != NULL) {
		set_timer(tick, 1 /* TimerPeriodic */, 200000 /* twenty milliseconds, in 100 ns */);
	}
	while (slices-- != 0) {
		if (tick != NULL) {
			if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
				BS->stall(20000);        /* the timer refused: a plain slice -- twenty MILLISECONDS
				                            (the old 200000 stalled ten times the slice's length) */
			}
		} else {
			BS->stall(20000);            /* no timer here: plain slices */
		}
		usb_pump();                      /* Wave 24: the one event consumer -- state events and
		                                    transfer completions alike are routed, not dropped */
		if ((slices & 63) == 62) {
			wdt_pet();                   /* about once a second across a long wait */
		}
	}""")

# ---- hunk 7: usb_present -- the pre-pull-up readback + the unit comment ------------------------
sub("""	BS->stall(50000);             /* five milliseconds of bus silence before the pull-up */
	*dctl |= 1u << 31;            /* RUN/Stop: the pull-up, the vendor connect's own tail */""",
"""	usb_sample_state("present");  /* Wave 24: the registers read back before the pull-up
	                                 (the P1-1 question: is the reset released?) */
	BS->stall(50000);             /* fifty milliseconds of bus silence before the pull-up
	                                 (the old comment said five; stall's unit is the microsecond) */
	*dctl |= 1u << 31;            /* RUN/Stop: the pull-up, the vendor connect's own tail */""")

# ---- hunk 8: the raw look moves to the failure window's end (and aborts if it queued) ----------
sub("""/* Wave 23: the wall's raw code. UsbDeviceSend folds whatever the submit path returned into
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
}""",
"""/* Wave 24: the wall's raw code, once per failed window's END (v19b asked it at beat 0,
 * the one point whose normal answer is "not yet configured"). It is a SECOND submit by
 * design -- the wrapped submit's own return code is folded by UsbDeviceSend, and the
 * sampler's state reads are the primary evidence now; the raw look only names the
 * refusing layer when the wrapped submit was refused. It is called only while no receive
 * stands (the wall held through the window), so on an armed pair it never runs; if the
 * raw look itself is queued, it is aborted straight back out (the old probe's own
 * precedent: the Cancelled completion is dropped harmlessly by the serve paths). */
static void
usb_probe_raw_code(uint64_t gen)
{
	typedef efi_status (EFIAPI *usbfn_transfer_t)(void *, uint8_t, uint32_t, uint64_t *, void *);
	usbfn_transfer_t raw;
	uint64_t size = 0, code, a;

	if (!usb_fn_locate()) {
		return;
	}
	raw = *(usbfn_transfer_t *)((uint8_t *)usb_fn + 0x50);
	code = (uint64_t)(uint32_t)raw(usb_fn, 1 /* the bulk OUT pair */, 0 /* host -> device */,
	    &size, usb_rx_buf);
	a = usb_age();
	print("usb: [t+%d.%d] the raw UsbFn look (gen %d, a second submit by design): %x%s\\n",
	    a / 10, a % 10, gen, code, EFI_ERROR(code) ? "" : " (it queued: taken back out)");
	if (!EFI_ERROR(code)) {
		USB->abort_xfer(USB_EP_OUT);
		usb_rx_queued = 0;
	}
}""")

# ---- hunk 9: usb_start_attempt -- the allocations split, the failures named, the buffers freed -
sub("""	efi_status s = USB->start_ex(&usb_set);
	if (!EFI_ERROR(s) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf))) {
		usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
		usb_ready = 1;
		usb_present();           /* Wave 22: the pull-up -- a fresh attach in a pumped window */
		return 1;
	}
	print("usb: try failed: start_ex %x\\n", s);   /* the code is the next forensics round's input */
	BS->signal_event(usb_init_event);        /* kick the firmware's start callback again */
	return 0;""",
"""	efi_status s = USB->start_ex(&usb_set);
	if (EFI_ERROR(s)) {
		print("usb: try failed: start_ex %x\\n", s);   /* the code is the next forensics round's input */
		BS->signal_event(usb_init_event);        /* kick the firmware's start callback again */
		return 0;
	}
	print("usb: start_ex is in (t+%d.%d)\\n", usb_age() / 10, usb_age() % 10);
	s = USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf);
	if (EFI_ERROR(s)) {
		print("usb: try failed: the receive buffer alone (%x) -- the allocations are told apart now (P2-5)\\n",
		    (uint64_t)(uint32_t)s);
		BS->signal_event(usb_init_event);
		return 0;
	}
	s = USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf);
	if (EFI_ERROR(s)) {
		print("usb: try failed: the send buffer (%x); the receive buffer goes back\\n", (uint64_t)(uint32_t)s);
		USB->free_transfer_buffer(usb_rx_buf);
		usb_rx_buf = NULL;
		BS->signal_event(usb_init_event);
		return 0;
	}
	usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
	usb_ready = 1;
	usb_rx_gen++;            /* Wave 24: this generation's requests carry a new identity */
	usb_host_seen = 0;       /* a real detach happened; the next Connected is the next host */
	usb_present();           /* Wave 22: the pull-up -- a fresh attach in a pumped window */
	return 1;""")

# ---- hunk 10: usb_start's head -- the monotonic timeline starts here ---------------------------
sub("""	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r, stalled, gen, beat, verdict, host_seen;
	efi_status probe;

	if (EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL, &tick))) {
		tick = NULL;
	}
	usb_dwc3_wake();          /* warm-boot DWC3: SUSPHY off + core soft reset before the bring-up */""",
"""	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r, stalled, gen, beat, verdict;

	usb_t0 = READ_SYSREG(CNTVCT_EL0);   /* Wave 24: one monotonic timeline for the session */
	print("usb: the bring-up begins (the Wave 24 timeline runs from here)\\n");
	if (EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL, &tick))) {
		tick = NULL;
	}
	usb_dwc3_wake();          /* warm-boot DWC3: SUSPHY off + core soft reset before the bring-up */
	usb_sample_state("wake"); /* the reset's readback: was bit11 released before anything ran? */""")

# ---- hunk 11: the stage itself -- standing RX, one consumer, no zero-length probe --------------
# (anchor-based: the v19b loop body's comment alignment is exact in the tree; the whole
#  region between the gen-loop head and the tick teardown is replaced)
_i = src.index("\tfor (gen = 0; usb_ready && gen < 3; gen++) {")
_j = src.index("\tif (tick != NULL) {\n\t\tset_timer(tick, 0 /* TimerCancel */, 0);", _i)
_region = src[_i:_j]
for _must in ("host_seen = 0;", "zero-length probe", "usb_probe_raw_code((uint64_t)gen, (uint64_t)beat",
              "kept its host", "twenty-five quiet seconds before the re-throw"):
    assert _must in _region, f"stage region marker missing: {_must}"
src = src[:_i] + """	for (gen = 0; usb_ready && gen < 3; gen++) {
		verdict = 0;         /* 0 the wall through every beat, 1 armed */
		usb_gate_reset();    /* each generation's wall counts from its own first refusal */
		usb_rx_gen++;        /* the generation stamps this window's standing receive */
		for (beat = 0; beat < (gen == 0 ? 24 : 6); beat++) {   /* Wave 23: the first window is
			                                  stretched to ~two minutes -- a host that needs the
			                                  longer grace gets it before any detach is thrown */
			if (beat != 0) {
				usb_wait_pumped(tick, 250);   /* Wave 22: the whole beat gap at the tick's
				                                 cadence, each wake pumping -- a host SETUP
				                                 landing in it is answered in one slice */
			}
			usb_stage_serving = 1;
			usb_poll_command();   /* Wave 24: pump + serve + arm in one call. The standing
			                         511-byte receive IS the probe now -- the zero-length
			                         probe is retired (one request, one identity, no
			                         contention); the submit's return code is checkpoint 1,
			                         and the wall's submit rate is the gate's business. */
			usb_stage_serving = 0;
			if (usb_rx_queued) {
				verdict = 1;     /* a receive stands with the controller: DwcPrepareURB took it,
				                    which only an armed pair does */
				break;
			}
		}
		if (verdict == 1) {
			print("usb: the bulk pair answered: armed at generation %d, beat %d (checkpoint-1 stood %d times before it)\\n",
			    (uint64_t)gen, (uint64_t)beat, usb_cp1);
			break;
		}
		if (gen == 2) {
			usb_sample_state("give-up");
			usb_probe_raw_code((uint64_t)gen);    /* the raw look, once, at the failure's end */
			print("usb: the pair never armed across 3 generations (last refuse %x, refused %d times): the session goes on over ep0 alone (v16c's proven state)\\n",
			    (uint64_t)usb_arm_code, usb_wall_count);
			break;
		}
		if (usb_host_seen) {
			/* Wave 23: a host was seen -- a re-throw's detach would kill the enumeration it
			 * just built (wave22's first suspect for the dead cycles). The present stays,
			 * the pumping continues, and the next generation's window opens without touching
			 * the controller. usb_host_seen is the pump's Connected book now: a Disconnected
			 * never sets it, and it is not cleared between generations (the review's "no
			 * blind clear") -- only a real re-throw's start_ex resets it. */
			print("usb: generation %d kept its host: no re-throw, the present stays and the stage keeps beating\\n",
			    (uint64_t)gen);
			continue;
		}
		usb_sample_state("throw");
		usb_probe_raw_code((uint64_t)gen);        /* the raw look, once, at the failure's end */
		print("usb: the pair is un-armed after generation %d (last refuse %x, refused %d times): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), (uint64_t)usb_arm_code, usb_wall_count);
		usb_rx_queued = 0;
		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		usb_wait_pumped(tick, 1250);   /* Wave 22: the quiet pumps too -- the callback's connect
		                                  lands here (it is what asserts the pull-up in this
		                                  window), and a host arriving in it is answered */
		if (usb_start_attempt() <= 0) {
			print("usb: the re-throw did not come back; the run goes on without the USB server\\n");
			usb_ready = 0;
			break;
		}
	}
""" + src[_j:]

# ---- hunk 12: usb_wait waits on the pending store through the one consumer ---------------------
sub("""static int64_t
usb_wait(uint8_t endpoint)
{
	/* static: a long transfer is many short waits, and the watchdog must be fed across them */
	static uint64_t last_pet;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0);

	for (;;) {
		uint32_t msg = UsbDeviceEventNoEvent;
		uint64_t size = 0;
		usb_device_event_data data;

		USB->handle_event(&msg, &size, &data);
		if (msg == UsbDeviceEventDeviceStateChange) {
			usb_connected = (data.device_state == UsbDeviceStateConnected);
			return -1;
		}
		/* with a kernel running, a host that went away must not keep this core from watching it */
		if (run_active && READ_SYSREG(CNTVCT_EL0) - began > 3 * freq) {
			return -1;
		}
		/* after a run, the service window (a host gone for good: reset and let the phone carry on) */
		if (!run_active && usb_service_secs != 0 && READ_SYSREG(CNTVCT_EL0) - usb_service_mark > usb_service_secs * freq) {
			return -1;
		}
		if (usb_data_timeout != 0 && READ_SYSREG(CNTVCT_EL0) - began > usb_data_timeout * freq) {
			USB->abort_xfer(endpoint);
			return -1;
		}
		if (msg == UsbDeviceEventTransferNotification && data.transfer.endpoint_index == endpoint) {
			return data.transfer.status == UsbDeviceTransferStatusCompleteOK ? (int64_t)data.transfer.bytes_completed : -1;
		}
		if (READ_SYSREG(CNTVCT_EL0) - last_pet > freq) {
			last_pet = READ_SYSREG(CNTVCT_EL0);
			wdt_pet();
		}
	}
}""",
"""static int64_t
usb_wait(uint8_t endpoint)
{
	/* static: a long transfer is many short waits, and the watchdog must be fed across them */
	static uint64_t last_pet;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0);
	struct usb_done *d = (endpoint == USB_EP_OUT) ? &usb_done_out : &usb_done_in;
	uint64_t parts_at = usb_disconnects;

	for (;;) {
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
		/* with a kernel running, a host that went away must not keep this core from watching it */
		if (run_active && READ_SYSREG(CNTVCT_EL0) - began > 3 * freq) {
			return -1;
		}
		/* after a run, the service window (a host gone for good: reset and let the phone carry on) */
		if (!run_active && usb_service_secs != 0 && READ_SYSREG(CNTVCT_EL0) - usb_service_mark > usb_service_secs * freq) {
			return -1;
		}
		if (usb_data_timeout != 0 && READ_SYSREG(CNTVCT_EL0) - began > usb_data_timeout * freq) {
			USB->abort_xfer(endpoint);
			return -1;
		}
		if (READ_SYSREG(CNTVCT_EL0) - last_pet > freq) {
			last_pet = READ_SYSREG(CNTVCT_EL0);
			wdt_pet();
		}
	}
}""")

# ---- hunk 13: the duplicate tentative definition of usb_rx_queued goes away --------------------
sub("""static int usb_rx_queued;       /* usb_poll_command() has left the receive for the next command with the controller */

static int64_t
usb_rx(uint8_t *buf, uint64_t len)""",
"""static int64_t
usb_rx(uint8_t *buf, uint64_t len)""")

# ---- hunk 14: usb_poll_command -- the one consumer + the standing receive ----------------------
sub("""static void
usb_poll_command(void)
{
	uint32_t msg = UsbDeviceEventNoEvent;
	uint64_t size = 0, n;
	usb_device_event_data data;
	char cmd[128];

	if (!usb_ready) {
		return;         /* not started over USB, or the bring-up has not made it (yet) */
	}
	/* (the cable's state does not gate the receive: over a USBIP host the Connected event of
	 * the vendor stack never arrives, and the write of a host is all the "connected" there is;
	 * an endpoint armed while no one writes costs nothing) -- Wave 21, session 4's lesson */
	if (!usb_rx_queued && !EFI_ERROR(USB->send(USB_EP_OUT, 511, usb_rx_buf))) {
		usb_rx_queued = 1;
	}
	USB->handle_event(&msg, &size, &data);
	if (msg == UsbDeviceEventDeviceStateChange) {
		usb_connected = (data.device_state == UsbDeviceStateConnected);
		usb_rx_queued = 0;
		return;
	}
	if (msg != UsbDeviceEventTransferNotification || data.transfer.endpoint_index != USB_EP_OUT) {
		return;
	}
	usb_rx_queued = 0;
	if (data.transfer.status != UsbDeviceTransferStatusCompleteOK || data.transfer.bytes_completed == 0) {
		return;
	}
	n = data.transfer.bytes_completed < sizeof(cmd) - 1 ? data.transfer.bytes_completed : sizeof(cmd) - 1;
	memcpy(cmd, usb_rx_buf, (size_t)n);
	cmd[n] = 0;
	fb_command(cmd);
}""",
"""static void
usb_poll_command(void)
{
	char cmd[128];
	uint64_t n;
	struct usb_done *d = &usb_done_out;

	if (!usb_ready) {
		return;         /* not started over USB, or the bring-up has not made it (yet) */
	}
	/* (the cable's state does not gate the receive: over a USBIP host the Connected event of
	 * the vendor stack never arrives, and the write of a host is all the "connected" there is;
	 * an endpoint armed while no one writes costs nothing) -- Wave 21, session 4's lesson.
	 * Wave 24: one consumer pumps the queue; the standing receive (rate limited at the
	 * source by the gate -- the wall's flood was our own submit-per-pass) carries the
	 * command; its completion lands in usb_done_out and is served here. */
	usb_pump();
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
}""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: hunks applied, {len(orig)} -> {len(src)} bytes")
