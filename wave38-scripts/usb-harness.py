#!/usr/bin/env python3
"""Wave 38 fix-generation isolation harness (the review report 3's method, kept):
extract the REAL code from the WSL loader.c -- the whole USB section (endpoint defines,
descriptor set, all the USB globals and ledger, the wall gate, the sampler) plus the
functions under test -- compile against a fake clock and a stub USB/Boot-Services
environment, run the counterexample cases, and assert.

Line-anchored spans + a line-based function extractor (no greedy regex), so the tests
always run the code as it actually is in the tree -- no reimplementation, no drift.

usage: python usb-harness.py LOADER_C OUT_C   (writes the standalone test program)
"""
import sys

src = open(sys.argv[1], encoding="utf-8").read()
lines = src.split("\n")

def line_index(prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise SystemExit(f"anchor not found: {prefix!r}")

def extract_fn(fn):
    """Extract a function definition (with its return-type line and the contiguous
    preceding /* */ comment block) from the loader's own layout:
        [comment block]\nstatic <type>\n<name>(<args>)\n{\n...\n}\n"""
    sig = None
    for i, ln in enumerate(lines):
        if ln.startswith(fn + "("):
            sig = i
            break
    if sig is None:
        raise SystemExit(f"function not found: {fn}")
    first = sig                                  # the signature line (name(...)
    if "{" not in lines[first]:
        first -= 1                               # the "static <type>" line above it
    begin = first
    # the contiguous comment block above (walk back over */-terminated comment lines)
    j = begin - 1
    if j >= 0 and lines[j].rstrip().endswith("*/"):
        end_of_comment = j
        while j >= 0:
            if lines[j].lstrip().startswith("/*") or lines[j].lstrip().startswith("*") or lines[j].rstrip().endswith("*/"):
                j -= 1
            else:
                break
        begin = j + 1
    # brace-match the body
    depth, k = 0, first
    body_start = None
    while k < len(lines):
        for ch in lines[k]:
            if ch == "{":
                depth += 1
                body_start = True
            elif ch == "}":
                depth -= 1
        if body_start is not None and depth == 0:
            return "\n".join(lines[begin:k + 1]) + "\n"
        k += 1
    raise SystemExit(f"unbalanced braces in {fn}")

si_end = line_index("#define USB_PUMP_BUDGET 8")
# include the usb_stale_wipe forward declaration if it sits within a few lines after
# the pump budget (a blank line may separate them)
for _look in (si_end + 1, si_end + 2, si_end + 3):
    if _look < len(lines) and lines[_look].lstrip().startswith("static void usb_stale_wipe"):
        si_end = _look
        break
usb_section = "\n".join(lines[line_index("#define USB_EP_OUT"):si_end + 1]) + "\n"
FUNCS = ["usb_pump", "usb_stale_wipe", "usb_arm_rx", "usb_retire_drain", "usb_init_kick",
         "usb_dwc3_susphy_off", "usb_dwc3_wake", "usb_wait_pumped", "usb_present",
         "usb_start_attempt", "usb_wait", "usb_rx", "usb_tx", "usb_poll_command"]
body = "\n".join(extract_fn(f) for f in FUNCS)

# the generation-4 recovery block (the statics + usb_pair_rebuild), extracted verbatim:
# from its statics line through the function's brace-matched close
ri = line_index("static uint64_t usb_pair_rebuilds, usb_zombie_last;")
sig = line_index("usb_pair_rebuild(void)", ri)
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
rebuild_section = "\n".join(lines[ri:k + 1]) + "\n"

PRELUDE = r"""
/* ---- fake environment (the harness; not the loader) ---- */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

typedef int64_t efi_status;
#define EFIAPI
#define EFI_ERROR(s) ((s) < 0)
/* the vendor's statuses arrive as 32-bit EFI_ERROR values sign-extended into the 64-bit
 * efi_status (the loader prints them as (uint32_t)s) -- the harness mirrors that ABI */
#define ECODE(x) ((efi_status)(0xFFFFFFFF00000000ULL | (x)))

static uint64_t g_now;            /* the fake counter/tick (CNTVCT_EL0) */
static const uint64_t g_freq = 10000000ULL;   /* 10 MHz */
enum { CNTVCT_EL0 = 1, CNTFRQ_EL0 = 2 };
#define READ_SYSREG(x) ((x) == CNTVCT_EL0 ? g_now : g_freq)

static char g_printbuf[1 << 20];
static size_t g_printlen;
static int g_printlines;
static void print(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(g_printbuf + g_printlen, sizeof(g_printbuf) - g_printlen - 1, fmt, ap);
    va_end(ap);
    if (n > 0) {
        g_printlen += (size_t)n;
        g_printbuf[g_printlen] = 0;
        for (const char *p = g_printbuf + g_printlen - n; p < g_printbuf + g_printlen; p++)
            if (*p == '\n')
                g_printlines++;
    }
}
static void print_reset(void) { g_printlen = 0; g_printbuf[0] = 0; g_printlines = 0; }
static int print_has(const char *s) { return strstr(g_printbuf, s) != NULL; }

/* the platform objects the sampler compares against (the real struct stays in loader.c) */
struct platform { const char *name; };
static const struct platform *PLAT;
static const struct platform platform_phk110 = { "phk110-fake" };

/* the vendor event/transfer enums (mirror of efi.h) */
enum { UsbDeviceEventNoEvent, UsbDeviceEventDeviceStateChange, UsbDeviceEventTransferNotification, UsbDeviceEventOemEvent };
enum { UsbDeviceTransferStatusActive, UsbDeviceTransferStatusCompleteOK, UsbDeviceTransferStatusCancelled,
       UsbDeviceTransferStatusCompleteError };
enum { UsbDeviceStateConnected, UsbDeviceStateDisconnected };
typedef union {
    uint32_t device_state;
    struct { uint32_t status; uint8_t endpoint_index; uint64_t bytes_completed; void *data_buffer; } transfer;
    uint64_t raw[8];
} usb_device_event_data;

typedef struct { uint32_t a; uint16_t b, c; uint8_t d[8]; } efi_guid;
/* the loader's GUID macros (the values are never compared inside the harness) */
#define QCOM_USB_DEVICE_GUID { 0xd9d9ce48, 0x44b8, 0x4f49, { 0x8e, 0x3e, 0x2a, 0x3b, 0x92, 0x7d, 0xc6, 0xc1 } }
#define QCOM_USB_INIT_EVENT_GUID { 0x1c0cffce, 0xfc8d, 0x4e44, { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 } }
typedef struct { const void *device_descriptor; const void **descriptors; const void *ss_device_descriptor;
    const void **ss_descriptors; const void *device_qualifier; const void *bos; uint8_t string_count;
    const void **strings; } usb_device_descriptor_set;
typedef void efi_system_table;
typedef void efi_handle;
typedef struct bs_s {
    efi_status (EFIAPI *locate_protocol)(const efi_guid *, void *, void **);
    void (EFIAPI *stall)(uint64_t us);
    efi_status (EFIAPI *create_event)(uint32_t, uint64_t, void *, void *, void **);
    efi_status (EFIAPI *set_timer)(void *, uint32_t, uint64_t);
    efi_status (EFIAPI *wait_for_event)(uint64_t, void **, uint64_t *);
    efi_status (EFIAPI *signal_event)(void *);
    efi_status (EFIAPI *create_event_ex)(uint32_t, uint64_t, void *, void *, const void *, void **);
} efi_boot_services;
static efi_boot_services *BS;           /* the loader's own global (declared outside the span there) */
static efi_status EFIAPI fake_locate(const efi_guid *g, void *r, void **out);
static int run_active;                  /* loader globals outside the span */
static uint64_t usb_data_timeout;
static uint64_t usb_service_secs, usb_service_mark;
static void wdt_pet(void) {}
#include <sys/mman.h>
static void fake_stall(uint64_t us) { g_now += us * (g_freq / 1000000ULL); }
static void fb_command(char *cmd);    /* the loader's real one is not under test: the glue fakes it */

typedef struct {
    uint64_t revision;
    void *start;
    efi_status (*send)(uint8_t endpoint, uint64_t size, void *buffer);
    efi_status (EFIAPI *handle_event)(uint32_t *event, uint64_t *size, usb_device_event_data *data);
    efi_status (EFIAPI *allocate_transfer_buffer)(uint64_t size, void **buffer);
    efi_status (EFIAPI *free_transfer_buffer)(void *buffer);
    efi_status (*stop)(void);
    efi_status (*abort_xfer)(uint8_t endpoint);
    efi_status (EFIAPI *set_endpoint_stall_state)(uint8_t endpoint, uint8_t state);
    efi_status (*start_ex)(void *set);
} usb_device_protocol;

/* ---- the fake USB script (what the stub protocol does per call) ---- */
static long g_send_calls;                 /* real USB->send attempts (either ep) */
static long g_send_in_ok;                 /* IN submits that succeeded */
static long g_abort_calls;
static efi_status g_send_in_result = 0;   /* 0 = success; else the refusal code */
static efi_status g_send_out_result = 0;
struct fake_event { uint32_t msg; uint32_t status; uint8_t ep; uint64_t bytes; };
static struct fake_event g_events[64];
static int g_event_n, g_event_i;

static efi_status fake_send(uint8_t ep, uint64_t size, void *buffer)
{
    (void)size; (void)buffer;
    g_send_calls++;
    if (ep == 0x81 /* USB_EP_IN, defined by the loader section below */) {
        if (EFI_ERROR(g_send_in_result)) return g_send_in_result;
        g_send_in_ok++;
        return 0;
    }
    return g_send_out_result;
}
static efi_status EFIAPI fake_handle_event(uint32_t *event, uint64_t *size, usb_device_event_data *data)
{
    (void)size;
    g_now += g_freq / 2;   /* every pump pass costs half a second: the clock advances
                              inside usb_wait's loop the way a real clock would */
    if (g_event_i >= g_event_n) { *event = UsbDeviceEventNoEvent; return 0; }
    struct fake_event *e = &g_events[g_event_i++];
    *event = e->msg;
    memset(data, 0, sizeof(*data));
    if (e->msg == UsbDeviceEventDeviceStateChange)
        data->device_state = e->status;
    else if (e->msg == UsbDeviceEventTransferNotification) {
        data->transfer.status = e->status;
        data->transfer.endpoint_index = e->ep;
        data->transfer.bytes_completed = e->bytes;
        data->transfer.data_buffer = NULL;
    }
    return 0;
}
static efi_status fake_abort(uint8_t ep) { (void)ep; g_abort_calls++; return 0; }

static usb_device_protocol g_usb;
static efi_boot_services g_bs_storage;

/* ---- the loader's own USB section follows (verbatim) ---- */
"""

MAIN = r"""
/* ---- the tests ---- */
static int g_pass, g_fail;
#define CHECK(name, cond) do { if (cond) { g_pass++; printf("  PASS %s\n", name); } \
    else { g_fail++; printf("  FAIL %s\n", name); } } while (0)

static uint8_t g_buf_rx[4096], g_buf_tx[65536];   /* real memcpy targets (usb_tx copies into them) */

static void reset_all(void)
{
    fake_usb_reset();
    memset(&g_printbuf, 0, sizeof(g_printbuf)); g_printlen = g_printlines = 0;
    usb_ready = 1; USB = &g_usb;
    usb_rx_buf = g_buf_rx; usb_tx_buf = g_buf_tx;
    usb_connected = 0; usb_rx_queued = 0; usb_rx_gen = 1;
    usb_arm_code = 0; usb_arm_ok = 0; usb_wall_count = 0;
    usb_cp1 = usb_cp3_ok = usb_cp3_bad = 0;
    usb_host_seen = 0; usb_disconnects = 0; usb_state_conn = usb_state_gone = 0;
    usb_tx_done = usb_tx_err = 0; usb_t0 = g_now = 0;
    usb_pump_calls = usb_pump_events = usb_pump_max = usb_pump_gap = usb_pump_last = 0;
    usb_fn = (void *)0;
    usb_done_out.live = 0; usb_done_in.live = 0;
    gate_next = 0; gate_backoff = 0;
    usb_in_stray = 0; usb_in_stale = 0; usb_in_ok = 0; usb_in_refused = 0;
    usb_in_gate_next = 0; usb_in_gate_backoff = 0;
    usb_in_send_fail = 0; usb_in_send_code = 0; usb_in_send_fail_total = 0;
    usb_in_sf_next = 0; usb_in_sf_backoff = 0;
    usb_in_state = 0 /* IDLE */; usb_out_state = 0;
    usb_bus_resets = 0; usb_out_stray = 0; usb_in_fault = 0;
    usb_in_short = 0; usb_in_short_total = 0;
    usb_pair_last_progress = 0; usb_pair_born_at = 0;
    usb_wall_last_at = 0; usb_last_connected_at = 0;
    usb_pair_rebuilds = 0; usb_zombie_last = 0;
    usb_init_event = (void *)1;        /* the kick exists; signal_event is a no-op fake */
    g_start_ex_result = 0; g_start_ex_calls = 0; g_alloc_n = 0;
    served_reset();
    run_active = 0; usb_service_secs = 0; usb_service_mark = 0; usb_data_timeout = 0;
}

/* T1: the P0-2 counterexample -- 1000 calls with IN submits refused outright */
static void t_direct_refusals(void)
{
    reset_all();
    g_send_in_result = ECODE(0x8000000B);
    for (int i = 0; i < 1000; i++) {
        usb_tx((const uint8_t *)"OKAY", 4);
        g_now += g_freq / 2;               /* half a second per command */
    }
    CHECK("P0-2 sends stopped by the gate (21 beats over 500 s, not 1000)",
          g_send_calls <= 25);
    printf("    [dbg T1] send_calls=%ld send_fail=%lu total=%lu code=%x stale=%lu expect=%d refused=%lu lines=%d\\n",
        g_send_calls, usb_in_send_fail, usb_in_send_fail_total, usb_in_send_code,
        usb_in_stale, usb_in_state, usb_in_refused, g_printlines);
    CHECK("P0-2 the episode counter holds first+beats", usb_in_send_fail_total >= 2);
    CHECK("P0-2 the refusal code is kept", usb_in_send_code == 0x8000000B);
    CHECK("P0-2 the reader-death ledger stays clean (not lumped in)",
          usb_in_stale == 0 && usb_in_state == 0);
    CHECK("P0-2 the refusal print exists and is bounded",
          print_has("the reply's submit itself is refused") && g_printlines <= 40);
}

/* T2: a successful submit ends the episode; a fresh failure starts from beat 1 */
static void t_episode_ends_on_success(void)
{
    reset_all();
    g_send_in_result = ECODE(0x8000000B);
    usb_tx((const uint8_t *)"OKAY", 4);          /* refused: the episode starts */
    g_now += 2 * g_freq;                          /* past the first beat */
    g_send_in_result = 0;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 4);
    int64_t r = usb_tx((const uint8_t *)"OKAY", 4);
    CHECK("P0-2 success ends the episode (r == 4)", r == 4);
    CHECK("P0-2 the episode counters reset on success",
          usb_in_send_fail == 0 && usb_in_sf_next == 0);
    g_send_in_result = ECODE(0x8000000C);
    print_reset();
    usb_tx((const uint8_t *)"OKAY", 4);
    CHECK("P0-2 a fresh episode announces as the first (x1)",
          strstr(g_printbuf, "(x1 this episode") != NULL);
}

/* T3: the stale gate works end to end and its backoff resets on success. Each bound
 * exit's retired tail (a Cancelled) is queued so the state machine retires cleanly. */
static void t_stale_gate_episode(void)
{
    reset_all();
    run_active = 1;                               /* the session-phase 3 s bound */
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCancelled, USB_EP_IN, 0);
    usb_tx((const uint8_t *)"OKAY", 4);           /* the wait takes the tail: unread */
    printf("    [dbg T3] stale=%lu aborts=%ld state=%d\n", usb_in_stale, g_abort_calls, usb_in_state);
    CHECK("stale: the unread reply is counted (the wait consumed the queued tail)", usb_in_stale == 1 && usb_in_state == 0);
    CHECK("stale: the state machine is back to idle after the tail",
          usb_in_state == 0 /* IDLE */);
    for (int i = 0; i < 2; i++) {
        g_now += 4 * g_freq;
        push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCancelled, USB_EP_IN, 0);
        usb_tx((const uint8_t *)"OKAY", 4);
    }
    CHECK("stale: the gate engages by the third unread", usb_in_stale >= 3 && usb_in_gate_next != 0);
    /* the reader comes back: the beat probe goes through and the gate lifts */
    g_now += 2 * g_freq;
    g_event_n = 0; g_event_i = 0;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 4);
    print_reset();
    int64_t r = usb_tx((const uint8_t *)"OKAY", 4);
    CHECK("stale: the gate lifts with a clean backoff on success",
          r == 4 && usb_in_stale == 0 && usb_in_gate_next == 0 && usb_in_gate_backoff == 0);
}

/* T4 (review counterexample 9's gate): the OUT wall gate still beats per its own tempo */
static void t_out_gate_still_beats(void)
{
    reset_all();
    g_send_out_result = ECODE(0x8000000C);
    usb_arm_rx();                                  /* refused: the wall gate engages */
    CHECK("wall gate: the first refusal is announced", usb_wall_count == 1 && gate_next != 0);
    g_now += g_freq / 2;
    usb_arm_rx();                                  /* inside the beat: refused quietly */
    CHECK("wall gate: the beat holds the submit", g_send_calls == 1 && usb_wall_count == 1);
    g_now += 2 * g_freq;
    usb_arm_rx();                                  /* the beat passed: probe again */
    CHECK("wall gate: the probe goes per beat", g_send_calls == 2);
}

/* ---- generation 3: the review's four counterexamples + P1-2 ---- */

/* TC1 (review counterexample): A's Cancelled completes AFTER B's submit. With the
 * lifecycle, B is refused while A is CANCELLING, the fault holds until a Connected,
 * and B then submits cleanly. */
static void tc1_late_cancel(void)
{
    reset_all();
    run_active = 1;
    usb_tx((const uint8_t *)"AAAAAAA", 7);         /* A: no tail queued -> the drain faults */
    CHECK("TC1 A's cleanup left the endpoint faulted (bounded, not assumed)",
          usb_in_fault == 1 && usb_in_state == 2 /* CANCELLING */);
    long sends_before = g_send_calls;
    int64_t r = usb_tx((const uint8_t *)"B", 1);   /* B: refused while faulted/cancelling */
    CHECK("TC1 B cannot submit while A is retiring", r == -1 && g_send_calls == sends_before);
    /* a fresh enumeration clears the fault (the Connected the pump delivers) */
    g_event_n = 0; g_event_i = 0;
    push_event(UsbDeviceEventDeviceStateChange, UsbDeviceStateConnected, 0, 0);
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCancelled, USB_EP_IN, 0);
    usb_pump();
    CHECK("TC1 the Connected lifted the fault and retired the tail",
          usb_in_fault == 0 && usb_in_state == 0);
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 1);
    r = usb_tx((const uint8_t *)"B", 1);
    CHECK("TC1 B then submits cleanly and gets its own length", r == 1);
}

/* TC2 (review counterexample): A's old OK completes after B's submit -- B must receive
 * its OWN reply length, never A's bytes. */
static void tc2_late_ok(void)
{
    reset_all();
    run_active = 1;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 17);
    usb_tx((const uint8_t *)"AAAAAAA", 7);         /* A: the wait takes A's own OK (17 B) --
                                                      a short reply is a failed reply */
    CHECK("TC2 A's short reply is not credited", usb_in_short_total == 1);
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 17);
    int64_t r = usb_tx((const uint8_t *)"BBBBBBBBBBBBBBBBB", 17);
    CHECK("TC2 B's own 17-byte reply is credited in full", r == 17);
}

/* TC3 (review counterexample): Connected and the current OK land in one pump batch
 * while a reply is live: the reset fails the wait, the OK is the retirement tail (never
 * credited as the reply), and the next reply works in full. */
static void tc3_connected_same_batch(void)
{
    reset_all();
    run_active = 1;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCancelled, USB_EP_IN, 0);
    usb_tx((const uint8_t *)"OKAY", 4);            /* A retires clean on its queued tail */
    CHECK("TC3 A retired clean before the batch", usb_in_state == 0 && usb_in_fault == 0);
    /* the batch that will meet B's live wait: Connected + an unrelated OK */
    push_event(UsbDeviceEventDeviceStateChange, UsbDeviceStateConnected, 0, 0);
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 17);
    int64_t r = usb_tx((const uint8_t *)"BBBB", 4);   /* B: the batch lands mid-wait */
    CHECK("TC3 the bus reset fails the wait (A's bytes NOT credited as B's reply)", r == -1);
    printf("    [dbg TC3] r=%ld state=%d fault=%d resets=%lu\n", r, usb_in_state, usb_in_fault, usb_bus_resets);
    CHECK("TC3 the cleanup drained the state back to idle", usb_in_state == 0);
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 4);
    r = usb_tx((const uint8_t *)"CCCC", 4);
    CHECK("TC3 the next reply after the reset works in full", r == 4);
}

/* TC4 (review counterexample): the current OK and a Disconnected in one batch -- no
 * stale completion reuse on the next request. */
static void tc4_ok_then_disconnect(void)
{
    reset_all();
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 17);
    push_event(UsbDeviceEventDeviceStateChange, UsbDeviceStateDisconnected, 0, 0);
    run_active = 1;
    int64_t r = usb_tx((const uint8_t *)"AAAAAAA", 7);   /* its own OK lands, then the bus leaves */
    CHECK("TC4 the wait reports the disconnect", r == -1);
    /* the next reply must not see the consumed slot: a fresh enumeration clears whatever
     * the disconnect left (the fault if A's tail never came), then it gets its own completion */
    g_event_n = 0; g_event_i = 0;
    run_active = 0;
    push_event(UsbDeviceEventDeviceStateChange, UsbDeviceStateConnected, 0, 0);
    usb_pump();
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_IN, 4);
    r = usb_tx((const uint8_t *)"BBBB", 4);
    printf("    [dbg TC4] r=%ld state=%d stale=%lu fault=%d\n", r, usb_in_state, usb_in_stale, usb_in_fault);
    CHECK("TC4 the next request is answered by its own completion only", r == 4);
    CHECK("TC4 no stray OUT noise was invented", usb_out_stray == 0);
}

/* TC5 (P1-2): a bound exit restores the standing receive; the next consumer takes over
 * the same transfer (no second submit into the same buffer). */
static void tc5_out_standing_restore(void)
{
    reset_all();
    run_active = 1;
    long sends0 = g_send_calls;
    int64_t r = usb_rx(g_buf_rx, 511);             /* times out at the 3 s bound */
    CHECK("TC5 the timed-out receive keeps its identity", r == -1 && usb_rx_queued == 1);
    g_event_n = 0; g_event_i = 0;
    run_active = 0;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_OUT, 9);
    r = usb_rx(g_buf_rx, 511);                     /* takes over the SAME standing transfer */
    CHECK("TC5 the standing transfer completed for the new consumer (no second submit)",
          r == 9 && g_send_calls == sends0 + 1);
}

/* TC6 (P1-2): usb_poll_command serves the completed command before any re-arm. The
 * command receive is armed first (the standing receive), its completion arrives, and
 * the poll must serve it before inviting the hardware to overwrite the buffer. */
static void tc6_serve_before_arm(void)
{
    reset_all();
    usb_service_secs = 600; usb_service_mark = g_now;
    usb_arm_rx();                                  /* the standing receive (state SUBMITTED) */
    long out_sends = g_send_calls;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_OUT, 14);
    usb_pump();                                    /* the command lands in the done slot */
    CHECK("TC6 the done slot holds the standing receive's completion", usb_done_out.live == 1);
    memcpy(g_buf_rx, "getvar:product", 14);
    usb_poll_command();                            /* serves it (the reply goes out on IN) */
    CHECK("TC6 the serve ran the fastboot handler", g_served_n == 1 &&
          strstr(g_served_cmd, "getvar:product") != NULL);
    CHECK("TC6 the serve submitted the IN reply", g_send_in_ok >= 1);
    CHECK("TC6 no OUT re-arm happened before the serve (the old order's race is gone)",
          g_send_calls - out_sends == 1);          /* only the IN reply's submit */
}

/* TC7: the data timeout abort flips CANCELLING and drains before the caller proceeds;
 * a fresh enumeration clears the fault; the next receive then works in full. */
static void tc7_data_timeout_drain(void)
{
    reset_all();
    usb_data_timeout = 2;
    usb_rx(g_buf_rx, 511);                         /* the timeout aborts; the drain runs */
    CHECK("TC7 the state machine drained to idle (or faulted honestly)",
          usb_out_state == 0 || usb_out_state == 2);
    usb_data_timeout = 0;
    /* a fresh enumeration clears the fault and any lingering CANCELLING (the tail of a
     * reset endpoint never comes -- the Connected book retires it), then the next
     * receive runs under a session bound with its completion queued */
    g_event_n = 0; g_event_i = 0;
    push_event(UsbDeviceEventDeviceStateChange, UsbDeviceStateConnected, 0, 0);
    usb_pump();
    CHECK("TC7 the Connected retired the lingering cancel", usb_out_state == 0);
    run_active = 1;
    push_event(UsbDeviceEventTransferNotification, UsbDeviceTransferStatusCompleteOK, USB_EP_OUT, 5);
    int64_t r = usb_rx(g_buf_rx, 511);
    CHECK("TC7 the next receive works after the timeout's cleanup", r == 5);
}

/* ---- generation 4: the detector + the transactional recovery ---- */

/* helper: a generation that has been up for 10 minutes with a recent wall refusal and
 * no progress -- the pure-0xC zombie's shape (no IN history at all) */
static void zombify(void)
{
    reset_all();
    usb_ready = 1;
    run_active = 0;
    g_now = 200 * g_freq;                /* the generation has been up for ten minutes */
    usb_service_secs = 240; usb_service_mark = g_now - 100 * g_freq;
    usb_pair_born_at = g_now - 190 * g_freq;          /* born ten minutes ago: past the grace */
    usb_pair_last_progress = g_now - 190 * g_freq;    /* the arm was the last progress */
    usb_wall_last_at = g_now - 10 * g_freq;           /* ...and the wall refused right before now */
    usb_arm_code = ECODE(0x8000000C);    /* the last refuse, for the record */
    usb_rx_queued = 0;
}

/* TD1 (THE P0-3 proof): the pure-0xC zombie -- zero IN history, a recent wall
 * refusal, no progress -- now reaches the bounded recovery. */
static void td1_pure_0xc_reachable(void)
{
    long aborts0;
    zombify();
    printf("    [dbg TD1] zombified: wall_last=%lu last_progress=%lu born=%lu now=%lu\n",
        usb_wall_last_at, usb_pair_last_progress, usb_pair_born_at, g_now);
    aborts0 = g_abort_calls;
    usb_pair_rebuild();
    printf("    [dbg TD1] rebuild returned: rebuilds=%lu fault=%d ready=%d start_ex=%ld\n",
        usb_pair_rebuilds, usb_in_fault, usb_ready, g_start_ex_calls);
    CHECK("TD1 the pure-0xC zombie (stale=0) FIRES the bounded recovery",
          usb_pair_rebuilds == 1);
    CHECK("TD1 the recovery retired both endpoints through the drains (aborts issued)",
          g_abort_calls >= aborts0 + 2);
    CHECK("TD1 the recovery re-threw the bring-up (start_ex called)",
          g_start_ex_calls == 1);
    CHECK("TD1 the recovery's success line says SET_CONFIG is still owed",
          print_has("the pair still needs the host's SET_CONFIG"));
}

/* TD2: recent progress vetoes the recovery (some half is alive). */
static void td2_progress_veto(void)
{
    zombify();
    usb_pair_last_progress = g_now - 30 * g_freq;   /* progress 30 s ago: recent */
    usb_pair_rebuild();
    CHECK("TD2 recent progress vetoes the recovery", usb_pair_rebuilds == 0);
}

/* TD3: the bring-up's grace (150 s) vetoes a recovery while the generation is young. */
static void td3_grace_veto(void)
{
    zombify();
    usb_pair_last_progress = 0;                  /* no progress stamp at all */
    usb_pair_born_at = g_now - 100 * g_freq;     /* the generation is only 100 s old */
    usb_pair_rebuild();
    CHECK("TD3 the bring-up's 150 s grace vetoes a young generation", usb_pair_rebuilds == 0);
}

/* TD4: a recent Connected (a host mid-setup) vetoes the recovery. */
static void td4_connected_veto(void)
{
    zombify();
    usb_pair_last_progress = 0;
    usb_pair_born_at = g_now - 300 * g_freq;     /* old enough */
    usb_last_connected_at = g_now - 10 * g_freq; /* enumerated 10 s ago */
    usb_pair_rebuild();
    CHECK("TD4 a recent enumeration vetoes the recovery", usb_pair_rebuilds == 0);
}

/* TD5: without a recent wall refusal there is no failure evidence at all. */
static void td5_no_wall_no_recovery(void)
{
    zombify();
    usb_pair_last_progress = 0;
    usb_pair_born_at = g_now - 300 * g_freq;
    usb_wall_last_at = g_now - 400 * g_freq;     /* the wall refusal is ancient */
    usb_pair_rebuild();
    CHECK("TD5 an ancient wall refusal is not failure evidence now", usb_pair_rebuilds == 0);
}

/* TD6: the cap (2) holds and the counter resets per service window. */
static void td6_cap_and_reset(void)
{
    zombify();
    usb_pair_rebuild();                          /* fires; its start_attempt re-stamps born_at */
    CHECK("TD6 the first recovery fired", usb_pair_rebuilds == 1);
    usb_pair_rebuilds = 2;
    usb_zombie_last = 0;
    usb_pair_rebuild();
    CHECK("TD6 the cap of two holds", usb_pair_rebuilds == 2);
    usb_pair_rebuilds = 0;                       /* the loop resets it per service window */
    g_now += 200 * g_freq;                       /* the new generation ages past its grace */
    usb_pair_born_at = g_now - 190 * g_freq;
    usb_pair_last_progress = g_now - 190 * g_freq;
    usb_wall_last_at = g_now - 10 * g_freq;
    usb_arm_code = ECODE(0x8000000C);
    usb_pair_rebuild();
    CHECK("TD6 the per-window reset lets a fresh window recover again", usb_pair_rebuilds == 1);
}

/* TD7: the run_active hard gate -- the session is never disturbed. */
static void td7_run_active_gate(void)
{
    zombify();
    run_active = 1;
    usb_pair_rebuild();
    CHECK("TD7 the session's hard gate blocks any recovery", usb_pair_rebuilds == 0);
    run_active = 0;
}

int main(void)
{
    /* map the DWC3 register page: the loader's MMIO writes in the wake/present paths
     * touch it for real, and the harness honours that (the same addresses, a fake page) */
    if (mmap((void *)0x0A600000ULL, 0x10000, PROT_READ | PROT_WRITE,
             MAP_ANONYMOUS | MAP_PRIVATE | MAP_FIXED, -1, 0) == MAP_FAILED) {
        printf("FATAL: the DWC3 fake page did not map\n");
        return 2;
    }
    printf("== wave38 isolation harness (P0-2 + P0-1/P1-2 + P0-3/P1-1 generations) ==\n");
    t_direct_refusals();
    t_episode_ends_on_success();
    t_stale_gate_episode();
    t_out_gate_still_beats();
    tc1_late_cancel();
    tc2_late_ok();
    tc3_connected_same_batch();
    tc4_ok_then_disconnect();
    tc5_out_standing_restore();
    tc6_serve_before_arm();
    tc7_data_timeout_drain();
    td1_pure_0xc_reachable();
    td2_progress_veto();
    td3_grace_veto();
    td4_connected_veto();
    td5_no_wall_no_recovery();
    td6_cap_and_reset();
    td7_run_active_gate();
    printf("== %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail != 0;
}
"""

GLUE = r"""
/* ---- the harness glue (needs the loader section's BS and endpoint defines) ---- */
static efi_status EFIAPI fake_locate(const efi_guid *g, void *r, void **out)
{ (void)g; (void)r; (void)out; return ECODE(0x80000008); }
static long g_start_ex_calls;                    /* the bring-up attempts */
static efi_status g_start_ex_result;
static efi_status fake_start_ex(void *set)       /* scripted: 0 = the bring-up is back */
{ (void)set; g_start_ex_calls++; return g_start_ex_result; }
static long g_alloc_n;
static efi_status EFIAPI fake_alloc(uint64_t size, void **buffer)
{
    static uint8_t pool[2][USB_CHUNK];
    *buffer = (g_alloc_n++ % 2) ? pool[1] : pool[0];
    (void)size;
    return 0;
}
static efi_status fake_free(void *buffer) { (void)buffer; return 0; }
static efi_status EFIAPI fake_signal_event(void *ev) { (void)ev; return 0; }
static char g_served_cmd[128];        /* the fake fb_command records what was served */
static int g_served_n;
static int64_t usb_tx(const uint8_t *data, uint64_t len);   /* under test: the fake replies through it */
static void fb_command(char *cmd)
{
    size_t n = strlen(cmd);
    if (n >= sizeof(g_served_cmd)) n = sizeof(g_served_cmd) - 1;
    memcpy(g_served_cmd, cmd, n);
    g_served_cmd[n] = 0;
    g_served_n++;
    usb_tx((const uint8_t *)"OKAYxnuloader", 13);   /* a reply, the way the real one would */
}
static void served_reset(void) { g_served_cmd[0] = 0; g_served_n = 0; }
static void fake_usb_reset(void)
{
    memset(&g_usb, 0, sizeof(g_usb));
    g_usb.send = fake_send;
    g_usb.handle_event = fake_handle_event;
    g_usb.abort_xfer = fake_abort;
    g_usb.start_ex = fake_start_ex;
    g_usb.allocate_transfer_buffer = fake_alloc;
    g_usb.free_transfer_buffer = fake_free;
    g_bs_storage.locate_protocol = fake_locate;
    g_bs_storage.stall = fake_stall;
    g_bs_storage.signal_event = fake_signal_event;
    BS = &g_bs_storage;
    g_send_calls = g_send_in_ok = g_abort_calls = 0;
    g_send_in_result = g_send_out_result = 0;
    g_event_n = g_event_i = 0;
    memset(g_events, 0, sizeof(g_events));
}
static void push_event(uint32_t msg, uint32_t status, uint8_t ep, uint64_t bytes)
{
    g_events[g_event_n].msg = msg; g_events[g_event_n].status = status;
    g_events[g_event_n].ep = ep; g_events[g_event_n].bytes = bytes;
    g_event_n++;
}
"""

out = PRELUDE + usb_section + "\n" + GLUE + "\n" + body + "\n" + rebuild_section + "\n" + MAIN
open(sys.argv[2], "w", encoding="utf-8", newline="").write(out)
print(f"harness written: {sys.argv[2]} ({len(out)} B; section {len(usb_section)} B; functions: {', '.join(FUNCS)})")
