#!/usr/bin/env python3
"""Wave 21.1 patch: the delayed first try for the loader's USB bring-up (v16).

Forensics (logdump-v16-base.bin, Boot #26 chain): the one execution whose USB came up won on
the FIRST try -- immediately, right after the phone had sat still for the best part of an hour
(platform fully settled) -- and then served four kernel sessions straight. Every FAILED boot's
logdump was overwritten by that success, so no `start failed %x` code survives anywhere on the
device (checked all 18 logdumps: zero occurrences). The evidence therefore points at the race,
not at a specific status: start_ex loses to the platform's own bring-up when it fires in the
first seconds after the init event (Boot #9's finding), and it wins first-try when the platform
has settled. Wave 21 §6 candidate ① (init event -> settle -> first try) is the matched fix.

Three changes, each asserted unique:
  1. usb_init_kick(): the platform's bring-up event (create once + signal) pulled out of
     usb_start_attempt so usb_start() can signal it and then give the vendor callback five
     quiet seconds before the first start_ex.
  2. usb_start_attempt(): the failed try's EFI status goes to the log ("usb: try failed:
     start_ex %x") -- if v16 still fails on device, the code lands in logdump this time.
  3. usb_start(): settle window (5 s, via an EVT_TIMER relative wait -- pumps the firmware's
     queue and its watchdog), then first try; retries now twenty seconds apart (the safe tempo
     v15.2's churn lesson bought) inside a 30 s boot window, then the run's watch loop keeps
     the 20 s tempo (usb_lazy_start, unchanged).

usage: patch-loader-v16.py LOADER_C
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

# ---- hunk 1: pull the init event out of the attempt into usb_init_kick --------------------
sub(
"""static void usb_lazy_start(void);

/* One bring-up attempt: the init event's callback, then start_ex, then the buffers. The
 * vendor callback restarts safely (the boot-time loop has always re-signaled it), so the
 * watch loop keeps trying these while the kernel runs (usb_lazy_start). Returns 1 started,
 * 0 try again, -1 there is no controller protocol here at all. */
static int
usb_start_attempt(void)
{
\tstatic const efi_guid usb_guid = QCOM_USB_DEVICE_GUID;
\tstatic const efi_guid init_guid = QCOM_USB_INIT_EVENT_GUID;

\tif (usb_init_event == NULL) {
\t\tif (!EFI_ERROR(BS->create_event_ex(0x200 /* EVT_NOTIFY_SIGNAL */, 8 /* TPL_CALLBACK */, usb_dummy_notify,
\t\t    NULL, &init_guid, &usb_init_event))) {
\t\t\tBS->signal_event(usb_init_event);
\t\t} else {
\t\t\treturn -1;
\t\t}
\t}
""",
"""static void usb_lazy_start(void);

/* The platform's bring-up event: created once, signaled before the first start_ex (the settle
 * window in usb_start gives its callback five quiet seconds) and re-signaled after every
 * failed try. Returns -1 if the event cannot even be created. */
static int
usb_init_kick(void)
{
\tstatic const efi_guid init_guid = QCOM_USB_INIT_EVENT_GUID;

\tif (usb_init_event == NULL &&
\t    EFI_ERROR(BS->create_event_ex(0x200 /* EVT_NOTIFY_SIGNAL */, 8 /* TPL_CALLBACK */, usb_dummy_notify,
\t        NULL, &init_guid, &usb_init_event))) {
\t\treturn -1;
\t}
\tBS->signal_event(usb_init_event);
\treturn 0;
}

/* One bring-up attempt: the init event's callback, then start_ex, then the buffers. The
 * vendor callback restarts safely (every failed try re-signals it), so the watch loop keeps
 * trying these while the kernel runs (usb_lazy_start). Returns 1 started, 0 try again, -1
 * there is no controller protocol here at all. */
static int
usb_start_attempt(void)
{
\tstatic const efi_guid usb_guid = QCOM_USB_DEVICE_GUID;

\tif (usb_init_event == NULL && usb_init_kick() != 0) {
\t\treturn -1;
\t}
""")

# ---- hunk 2: the failed try's status code goes to the log ---------------------------------
sub(
"""	if (!EFI_ERROR(USB->start_ex(&usb_set)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf))) {
		usb_ready = 1;
		return 1;
	}
	BS->signal_event(usb_init_event);        /* kick the firmware's start callback again */
	return 0;
}
""",
"""	efi_status s = USB->start_ex(&usb_set);
	if (!EFI_ERROR(s) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf))) {
		usb_ready = 1;
		return 1;
	}
	print("usb: try failed: start_ex %x\\n", s);   /* the code is the next forensics round's input */
	BS->signal_event(usb_init_event);        /* kick the firmware's start callback again */
	return 0;
}
""")

# ---- hunk 3: usb_start(): settle window, 20 s retry tempo, 30 s boot window ---------------
sub(
"""/* The boot-time bring-up: as many attempts as fit in ten seconds (the platform init behind the
 * first one is still in flight then -- Boot #9's finding), then the run takes over (the watch
 * loop's usb_lazy_start) and this core serves whenever it comes up. */
static int
usb_start(void)
{
	/* create_event/set_timer/wait_for_event are unused elsewhere, so efi.h leaves them untyped */
	typedef efi_status (EFIAPI *create_event_t)(uint32_t type, uint64_t tpl, void (EFIAPI *notify)(void *, void *),
	    void *ctx, void **event);
	typedef efi_status (EFIAPI *set_timer_t)(void *event, uint32_t kind, uint64_t time);
	typedef efi_status (EFIAPI *wait_for_event_t)(uint64_t count, void **events, uint64_t *index);
	create_event_t create_event = (create_event_t)BS->create_event;
	set_timer_t set_timer = (set_timer_t)BS->set_timer;
	wait_for_event_t wait_for_event = (wait_for_event_t)BS->wait_for_event;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r;

	for (;;) {
		r = usb_start_attempt();
		tries++;
		if (r != 0) {
			if (r < 0) {
				print("usb: device protocol not found\\n");
			}
			break;
		}
		if (READ_SYSREG(CNTVCT_EL0) - began > 10 * freq) {
			print("usb: start failed after %d tries: the run goes on and this core keeps trying\\n", (uint64_t)tries);
			break;
		}
		if (tries == 1) {
			print("usb: start failed, retrying\\n");
		}
		if (tick == NULL && EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL,
		    &tick))) {
			tick = NULL;
		}
		if (tick == NULL) {
			BS->stall(250000);               /* no timer events here: a plain quarter second */
			continue;
		}
		set_timer(tick, 1 /* TimerPeriodic */, 10000000 /* one second, in 100 ns */);
		if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
			BS->stall(1000000);
		}
	}
""",
"""/* The boot-time bring-up. Wave 21.1: the first start_ex has been losing a race to the
 * platform's own USB bring-up (Boot #9, and ~9/10 of the v15 boots; the one boot that won --
 * logdump-v16-base.bin -- started first try, right after the phone had sat still for the best
 * part of an hour, i.e. with the platform fully settled). So the init event is signaled and
 * the platform gets five quiet seconds to run its UsbConfigDxe callback (and the RPM/DAL
 * clocks behind it) before the first start_ex touches the controller; the wait is a timer
 * event, which also pumps the firmware's queue and its watchdog. A failed try is retried
 * twenty seconds later (every start_ex resets the DWC3 -- v15.2's churn lesson -- so the safe
 * tempo is one try per twenty seconds) within a thirty-second boot window, then the run takes
 * over (the watch loop's usb_lazy_start, same twenty-second tempo). */
static int
usb_start(void)
{
	/* create_event/set_timer/wait_for_event are unused elsewhere, so efi.h leaves them untyped */
	typedef efi_status (EFIAPI *create_event_t)(uint32_t type, uint64_t tpl, void (EFIAPI *notify)(void *, void *),
	    void *ctx, void **event);
	typedef efi_status (EFIAPI *set_timer_t)(void *event, uint32_t kind, uint64_t time);
	typedef efi_status (EFIAPI *wait_for_event_t)(uint64_t count, void **events, uint64_t *index);
	create_event_t create_event = (create_event_t)BS->create_event;
	set_timer_t set_timer = (set_timer_t)BS->set_timer;
	wait_for_event_t wait_for_event = (wait_for_event_t)BS->wait_for_event;
	uint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0), index;
	void *tick = NULL;
	int tries = 0, r, stalled;

	if (EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL, &tick))) {
		tick = NULL;
	}
	/* the settle window: the init event's callback runs behind it, and the timer event pumps
	 * the firmware's queue (its watchdog with it) while the platform finishes its bring-up.
	 * A kick that would not even take falls through: the first attempt reports it. */
	if (usb_init_kick() == 0) {
		print("usb: the platform is asked up; five quiet seconds before the first try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 50000000 /* five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (r = 0; r < 5; r++) {
				BS->stall(1000000);
			}
		}
	}
	for (;;) {
		r = usb_start_attempt();
		tries++;
		if (r != 0) {
			if (r < 0) {
				print("usb: device protocol not found\\n");
			}
			break;
		}
		if (READ_SYSREG(CNTVCT_EL0) - began > 30 * freq) {
			print("usb: start failed after %d tries: the run goes on and this core keeps trying\\n", (uint64_t)tries);
			break;
		}
		if (tick == NULL) {
			for (stalled = 0; stalled < 20; stalled++) {
				BS->stall(1000000);      /* no timer events here: plain seconds */
			}
			continue;
		}
		set_timer(tick, 1 /* TimerPeriodic */, 200000000 /* twenty seconds, in 100 ns */);
		if (EFI_ERROR(wait_for_event(1, &tick, &index))) {
			BS->stall(1000000);
		}
	}
""")

# ---- sanity of the patched text ------------------------------------------------------------
for token in (b"usb_init_kick", b"five quiet seconds", b"200000000 /* twenty seconds",
              b"usb: try failed: start_ex %x"):
    assert token in src.encode(), f"missing after patch: {token}"
assert src.count("usb_init_kick") == 3, src.count("usb_init_kick")   # def + attempt call + start call
assert src.count("TimerPeriodic") == 1
assert "10000000 /* one second" not in src

if src == orig:
    sys.exit("nothing changed")
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: 3 hunks applied")
print("  1. usb_init_kick() helper (init event pulled out of the attempt)")
print("  2. failed tries print their start_ex status (forensics land in logdump)")
print("  3. usb_start(): 5 s settle before the first try, 20 s retry tempo, 30 s boot window")
