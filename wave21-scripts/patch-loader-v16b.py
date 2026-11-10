#!/usr/bin/env python3
"""Wave 21.2 patch: the USB bring-up belongs to the boot window alone (v16b).

v16's verdict (docs/waves/wave21_1-ssh-verdict.md): the online criterion is met -- with a
settle before the first try, the last two independent logdumps show `usb: started` first-try,
zero failed tries on those boots. What still blocked N1-N3 was host-side: F8 (a failed
start_ex leaves the DWC3 half-started: ep0 enumerable, bulk endpoints never armed -- "visible
is not usable") and F9 (usbipd's auto-attach binding to a dead export instance). The half-
started state's factory was the runtime retry: usb_lazy_start called start_ex every twenty
seconds of a live session, and every call resets the DWC3 -- zero successes in every round
observed, and each failed call could tear an enumeration out from under a host already
talking to the loader.

Four changes, each asserted unique (construction order wave21_1 §6 item 2):
  1. usb_lazy_start() is retired: the body no longer touches the controller. Boot-time only
     tries now; nothing resets the DWC3 while the kernel runs. A boot whose tries all failed
     runs without the USB server this session -- which is v15.3's safe behavior -- and the
     next boot's tries are the recovery.
  2. The settle window widens 5 s -> 25 s (the platform gets a quieter quarter minute to
     finish its UsbConfigDxe bring-up before the first start_ex).
  3. The boot window keeps three tries, twenty-five seconds apart (25/50/75 s), then gives
     up -- each try a clean generational attempt, no churn cascade (the v16 window was 30 s
     at a 20 s tempo; the widened budget is the "one more clean try" of §6 item 2c).
  4. The give-up line says what the next recovery is ("usb: warm-boot start failed after %d
     tries; the next cold boot is the clean try") -- the cold-boot criterion card of §6 item
     1 reads exactly this line from the screen/logdump.

usage: patch-loader-v16b.py LOADER_C
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

# ---- hunk 1: the lazy retry is retired (F8's factory closes) --------------------------------
sub(
"""/* The watch loop's every pass: if the boot-time bring-up did not make it, keep trying, a
 * quarter second at a time, for the whole run. */
static void
usb_lazy_start(void)
{
\tstatic uint64_t last;

\tif (usb_ready || USB == NULL) {
\t\treturn;
\t}
\tif (READ_SYSREG(CNTVCT_EL0) - last < 20 * READ_SYSREG(CNTFRQ_EL0)) {
\t\treturn;      /* twenty seconds between tries: every start_ex resets the DWC3, and a
\t\t                try every quarter second kept the gadget in a churn the host could
\t\t                never enumerate through (session v15.2 -- the lesson) */
\t}
\tlast = READ_SYSREG(CNTVCT_EL0);
\tif (usb_start_attempt() > 0) {
\t\tprint("usb: started late (the run goes on; the commands are served from here)\\n");
\t}
}
""",
"""/* The watch loop's every pass. Wave 21.2 retired the runtime retries: a start_ex resets the
 * DWC3 even when it fails, so a try while the kernel runs could tear the enumeration out from
 * under a host that was already talking to the loader (the half-started state, F8) -- and
 * every runtime retry ever observed (v15.3's 20 s backoff, v16's 20 s tempo) succeeded zero
 * times. The bring-up belongs to the boot window alone now: three tries before the kernel is
 * up, and a boot whose three tries all failed runs without the USB server (the safe v15.3
 * behavior) -- the next boot tries again on silicon nothing has touched since its reset. */
static void
usb_lazy_start(void)
{
\t/* retired (Wave 21.2): no controller access while the kernel runs */
}
""")

# ---- hunk 2: the watch-loop declaration's comment keeps the truth ---------------------------
sub(
"""static void usb_lazy_start(void);   /* the watch loop keeps the USB bring-up trying (Wave 21) */""",
"""static void usb_lazy_start(void);   /* retired in 21.2: the boot window is the only bring-up */""")

# ---- hunk 3: usb_init_kick's comment (the settle it feeds is twenty-five seconds now) -------
sub(
"""/* The platform's bring-up event: created once, signaled before the first start_ex (the settle
 * window in usb_start gives its callback five quiet seconds) and re-signaled after every
 * failed try. Returns -1 if the event cannot even be created. */""",
"""/* The platform's bring-up event: created once, signaled before the first start_ex (the settle
 * window in usb_start gives its callback twenty-five quiet seconds) and re-signaled after
 * every failed try. Returns -1 if the event cannot even be created. */""")

# ---- hunk 3b: usb_start_attempt's comment (only the boot window calls it now) ----------------
sub(
"""/* One bring-up attempt: the init event's callback, then start_ex, then the buffers. The
 * vendor callback restarts safely (every failed try re-signals it), so the watch loop keeps
 * trying these while the kernel runs (usb_lazy_start). Returns 1 started, 0 try again, -1
 * there is no controller protocol here at all. */""",
"""/* One bring-up attempt: the init event's callback, then start_ex, then the buffers. The
 * vendor callback restarts safely (every failed try re-signals it). Only the boot window
 * calls this now (usb_start's three tries). Returns 1 started, 0 try again, -1 there is no
 * controller protocol here at all. */""")

# ---- hunk 4: the boot window: settle 25 s, three tries at a 25 s tempo, honest give-up ------
sub(
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
{""",
"""/* The boot-time bring-up. Wave 21.1: the first start_ex has been losing a race to the
 * platform's own USB bring-up (Boot #9, and ~9/10 of the v15 boots; the one boot that won --
 * logdump-v16-base.bin -- started first try, right after the phone had sat still for the best
 * part of an hour, i.e. with the platform fully settled). So the init event is signaled and
 * the platform gets twenty-five quiet seconds (Wave 21.2 widened the settle from five) to run
 * its UsbConfigDxe callback (and the RPM/DAL clocks behind it) before the first start_ex
 * touches the controller; the wait is a timer event, which also pumps the firmware's queue
 * and its watchdog. A failed try is retried twenty-five seconds later, three tries in all
 * (25/50/75 s) -- every start_ex resets the DWC3 (v15.2's churn lesson), so the tempo stays
 * at one try per twenty-five seconds and each try is a clean generational attempt. If all
 * three fail, the run starts without a USB server: nothing touches the controller while the
 * kernel runs (the lazy retry that used to take over here was the half-started state's
 * factory -- F8 -- and never once succeeded), and the give-up line names the recovery, a
 * cold boot's fresh tries. */
static int
usb_start(void)
{""")

sub(
"""	if (usb_init_kick() == 0) {
\t\tprint("usb: the platform is asked up; five quiet seconds before the first try\\n");
\t\tif (tick != NULL) {
\t\t\tset_timer(tick, 2 /* TimerRelative */, 50000000 /* five seconds, in 100 ns */);
\t\t\twait_for_event(1, &tick, &index);
\t\t} else {
\t\t\tfor (r = 0; r < 5; r++) {
\t\t\t\tBS->stall(1000000);
\t\t\t}
\t\t}
\t}
\tfor (;;) {
\t\tr = usb_start_attempt();
\t\ttries++;
\t\tif (r != 0) {
\t\t\tif (r < 0) {
\t\t\t\tprint("usb: device protocol not found\\n");
\t\t\t}
\t\t\tbreak;
\t\t}
\t\tif (READ_SYSREG(CNTVCT_EL0) - began > 30 * freq) {
\t\t\tprint("usb: start failed after %d tries: the run goes on and this core keeps trying\\n", (uint64_t)tries);
\t\t\tbreak;
\t\t}
\t\tif (tick == NULL) {
\t\t\tfor (stalled = 0; stalled < 20; stalled++) {
\t\t\t\tBS->stall(1000000);      /* no timer events here: plain seconds */
\t\t\t}
\t\t\tcontinue;
\t\t}
\t\tset_timer(tick, 1 /* TimerPeriodic */, 200000000 /* twenty seconds, in 100 ns */);
""",
"""	if (usb_init_kick() == 0) {
\t\tprint("usb: the platform is asked up; twenty-five quiet seconds before the first try\\n");
\t\tif (tick != NULL) {
\t\t\tset_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
\t\t\twait_for_event(1, &tick, &index);
\t\t} else {
\t\t\tfor (r = 0; r < 25; r++) {
\t\t\t\tBS->stall(1000000);
\t\t\t}
\t\t}
\t}
\tfor (;;) {
\t\tr = usb_start_attempt();
\t\ttries++;
\t\tif (r != 0) {
\t\t\tif (r < 0) {
\t\t\t\tprint("usb: device protocol not found\\n");
\t\t\t}
\t\t\tbreak;
\t\t}
\t\tif (tries >= 3 || READ_SYSREG(CNTVCT_EL0) - began > 90 * freq) {
\t\t\tprint("usb: warm-boot start failed after %d tries; the next cold boot is the clean try\\n", (uint64_t)tries);
\t\t\tbreak;
\t\t}
\t\tif (tick == NULL) {
\t\t\tfor (stalled = 0; stalled < 25; stalled++) {
\t\t\t\tBS->stall(1000000);      /* no timer events here: plain seconds */
\t\t\t}
\t\t\tcontinue;
\t\t}
\t\tset_timer(tick, 1 /* TimerPeriodic */, 250000000 /* twenty-five seconds, in 100 ns */);
""")

# ---- hunk 5: main()'s comment tells the new truth -------------------------------------------
sub(
"""		/* Wave 21: the run first -- this core watches it and its USB server carries en0's
		 * frames (block_poll, net_poll, usb_lazy_start, usb_poll_command) -- and then the
		 * commands, with a service window: a host that stops talking for good leaves the
		 * phone free again. The bring-up is retried all along the run (usb_lazy_start), so
		 * a start_ex that lost the race to the platform's own init costs seconds, not the
		 * session. */""",
"""		/* Wave 21: the run first -- this core watches it and its USB server carries en0's
		 * frames (block_poll, net_poll, usb_poll_command; the lazy retry retired in 21.2) --
		 * and then the commands, with a service window: a host that stops talking for good
		 * leaves the phone free again. The bring-up belongs to the boot window (usb_start's
		 * three tries); a start_ex that lost the race costs this session's usb server, and
		 * the next boot's tries are the recovery. */""")

# ---- sanity of the patched text ------------------------------------------------------------
for token in (b"twenty-five quiet seconds", b"250000000 /* twenty-five seconds",
              b"usb: warm-boot start failed after %d tries", b"retired (Wave 21.2)"):
    assert token in src.encode(), f"missing after patch: {token}"
for gone in (b"asked up; five quiet seconds", b"gives its callback five quiet seconds",
             b"gets five quiet seconds", b"50000000 /* five seconds",
             b"200000000 /* twenty seconds"):
    assert gone not in src.encode(), f"still present after patch: {gone}"
assert b"started late" not in src.encode()
assert b"this core keeps trying" not in src.encode()
assert src.count("usb_lazy_start") == 4, src.count("usb_lazy_start")   # 2 decls + watch call + def
assert src.count("usb_start_attempt() > 0") == 0                       # no runtime retries left
assert src.count("250000000") == 2                                     # settle + retry tempo

if src == orig:
    sys.exit("nothing changed")
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: 6 hunks applied")
print("  1. usb_lazy_start retired (no controller access while the kernel runs; F8's factory closes)")
print("  2. watch-loop declaration's comment updated")
print("  3. usb_init_kick + usb_start_attempt comments updated (25 s settle; boot window only)")
print("  4. settle window 5 s -> 25 s; three tries at a 25 s tempo (25/50/75 s), 90 s bound")
print("  5. give-up names the recovery: the next cold boot is the clean try")
print("  6. main()'s bring-up comment updated (no all-run retries)")
