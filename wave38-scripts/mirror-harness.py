#!/usr/bin/env python3
"""Wave 38 generation-2 (P0-4 + P1-5) isolation harness: the mirror section extracted
verbatim from the WSL loader.c, compiled against a fake console table, a fake HOB list
and a recording shim writer. Tests:

  T1 passthrough + record: a non-wall line reaches the original writer and the log ring
  T2 first cause + suppression: each wall family's first line passes verbatim, repeats count
  T3 the shared budget: exactly one aggregate per 2 s across families
  T4 SETUP_PENDING classified as its own family under the same budget
  T5 split-line assembly: a wall line split across two writer calls classifies once
  T6 return value: every path reports every byte consumed (no caller retries)
  T7 the HOB walk: legal short HOBs do not stop it; the GUID gates hold; the PHIT bounds it

usage: python mirror-harness.py LOADER_C OUT_C
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
    sig = None
    for i, ln in enumerate(lines):
        if ln.startswith(fn + "("):
            sig = i
            break
    if sig is None:
        raise SystemExit(f"function not found: {fn}")
    first = sig
    if "{" not in lines[first]:
        first -= 1
    begin = first
    j = first - 1
    if j >= 0 and lines[j].rstrip().endswith("*/"):
        while j >= 0:
            ls = lines[j].lstrip()
            if ls.startswith("/*") or ls.startswith("*") or lines[j].rstrip().endswith("*/"):
                j -= 1
            else:
                break
        begin = j + 1
    depth, k, started = 0, first, False
    while k < len(lines):
        for ch in lines[k]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        if started and depth == 0:
            return "\n".join(lines[begin:k + 1]) + "\n"
        k += 1
    raise SystemExit(f"unbalanced braces in {fn}")

ia = line_index("static int mirror_busy;")
si = line_index("mirror_shim_write(const char *buf, uint64_t len)")
depth, j, started = 0, si, False
while j < len(lines):
    for ch in lines[j]:
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
    if started and depth == 0:
        break
    j += 1
mirror_section = "\n".join(lines[ia:j + 1]) + "\n"
mirror_install = extract_fn("mirror_install")

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

static uint64_t g_now;
static const uint64_t g_freq = 10000000ULL;
enum { CNTVCT_EL0 = 1, CNTFRQ_EL0 = 2 };
#define READ_SYSREG(x) ((x) == CNTVCT_EL0 ? g_now : g_freq)

typedef uint16_t char16;
typedef struct { uint32_t a; uint16_t b, c; uint8_t d[8]; } efi_guid;
struct efi_text_output {
    uint64_t pad[4];
    efi_status (EFIAPI *output_string)(struct efi_text_output *self, const char16 *str);
};
struct efi_config_table { efi_guid guid; void *table; };
struct efi_system_table {
    uint64_t pad[4];
    struct efi_config_table *tables;
    uint64_t nr_tables;
    struct efi_text_output *con_out;
};
static struct efi_system_table *ST;

static char g_printbuf[1 << 18];
static size_t g_printlen;
static void print(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(g_printbuf + g_printlen, sizeof(g_printbuf) - g_printlen - 1, fmt, ap);
    va_end(ap);
    if (n > 0) {
        g_printlen += (size_t)n;
        g_printbuf[g_printlen] = 0;
    }
}
static void print_reset(void) { g_printlen = 0; g_printbuf[0] = 0; }
static int print_has(const char *s) { return strstr(g_printbuf, s) != NULL; }

static int in_own_print;
static char log_buf[1 << 16];
static uint64_t log_len;

static uint64_t str_len(const char *s) { return strlen(s); }

/* the recording original writer (stands in for SerialPortWrite): everything it is
 * handed lands in orig_seen; the tests install it as shim_write_orig */
static char orig_seen[64][320];
static uint64_t orig_seen_n, orig_seen_bytes;
static uint64_t rec_writer(const char *buf, uint64_t len)
{
    uint64_t i;

    for (i = 0; i < len && i < sizeof(orig_seen[0]) - 1; i++) {
        orig_seen[orig_seen_n][i] = buf[i];
    }
    orig_seen[orig_seen_n][i] = 0;
    orig_seen_n++;
    orig_seen_bytes += len;
    return len;
}
static uint64_t EFIAPI sentinel_writer(const char *buf, uint64_t len)
{ (void)buf; (void)len; return len; }
static void orig_reset(void) { orig_seen_n = 0; orig_seen_bytes = 0; }
static int orig_has(const char *s)
{
    for (uint64_t i = 0; i < orig_seen_n; i++) {
        if (strstr(orig_seen[i], s)) return 1;
    }
    return 0;
}
static int orig_line_contains(uint64_t idx, const char *s)
{
    return idx < orig_seen_n && strstr(orig_seen[idx], s) != NULL;
}

/* ---- the loader's mirror section follows (verbatim) ---- */
"""

MAIN = r"""
/* ---- the tests ---- */
static int g_pass, g_fail;
#define CHECK(name, cond) do { if (cond) { g_pass++; printf("  PASS %s\n", name); } \
    else { g_fail++; printf("  FAIL %s\n", name); } } while (0)

static uint8_t g_hobs[4096];
static uint64_t g_shim_slot[4];                      /* the fake shim: locator at +0x10 */
static uint64_t g_dev_slot[4];                       /* the fake device: writer at +0x10 */

static long EFIAPI fake_locator(const char *name, uint64_t flags, void **out)
{
    (void)name; (void)flags;
    *out = g_dev_slot;
    return 0;
}

static void reset_all(void)
{
    mirror_busy = 0;
    mirror_bytes = mirror_drops = 0;
    memset(mirror_lead_hits, 0, sizeof(mirror_lead_hits));
    wall_line_len = 0;
    memset(wall_family_count, 0, sizeof(wall_family_count));
    memset(wall_family_total, 0, sizeof(wall_family_total));
    memset(wall_family_first, 0, sizeof(wall_family_first));
    wall_last_shown = 0; wall_budget_suppressed = 0; wall_budget_shown = 0;
    log_len = 0; log_buf[0] = 0;
    g_now = 0;
    print_reset();
    orig_reset();
    shim_write_orig = rec_writer;
}

/* T1: a non-wall line passes through and lands in the log ring */
static void t1_passthrough(void)
{
    reset_all();
    const char *line = "usb: the vendor debug door echoes: the mirror is in\n";
    uint64_t r = mirror_shim_write(line, str_len(line));
    CHECK("T1 the whole write is reported consumed", r == str_len(line));
    CHECK("T1 the original writer saw the line", orig_has("the vendor debug door echoes"));
    CHECK("T1 the log ring recorded it", strstr(log_buf, "the vendor debug door echoes") != NULL);
}

/* T2: each wall family's first line passes verbatim; the repeats are counted */
static void t2_first_cause(void)
{
    reset_all();
    const char *l1 = "UsbDeviceSend: Failed to submit data transfer: Device Error\n";
    const char *l2 = "DwcPrepareURB:Trb: physical endpoint[2] not configured\n";

    mirror_shim_write(l1, str_len(l1));              /* the 0xB family's first cause */
    mirror_shim_write(l2, str_len(l2));              /* the 0xC family's first cause */
    for (int i = 0; i < 40; i++) {
        mirror_shim_write(l1, str_len(l1));          /* repeats, all inside the beat */
    }
    CHECK("T2 both first causes shown verbatim and nothing else", orig_seen_n == 2);
    CHECK("T2 the first causes are in the log ring", strstr(log_buf, "Failed to submit data transfer") != NULL &&
          strstr(log_buf, "physical endpoint[2] not configured") != NULL);
    CHECK("T2 the repeats were counted per family", wall_family_total[1] >= 40);
    CHECK("T2 the repeats are suppressed, not shown (the flood stopped)",
          wall_budget_suppressed >= 39);
}

/* T3: the shared budget -- all repeats inside the beat suppress; past it exactly one aggregate */
static void t3_shared_budget(void)
{
    reset_all();
    const char *b = "UsbfnDwcTransfer: Failed to submit transfer\n";
    mirror_shim_write(b, str_len(b));                /* the 0xB first cause at t=0 */
    for (int i = 0; i < 20; i++) {
        mirror_shim_write(b, str_len(b));            /* repeats at t=0: inside the beat */
    }
    CHECK("T3 20 in-beat repeats produced no display", orig_seen_n == 1);
    g_now += 2 * g_freq;                             /* past the beat */
    mirror_shim_write(b, str_len(b));                /* exactly one aggregate */
    CHECK("T3 past the beat exactly one aggregate crossed the budget", orig_seen_n == 2);
    CHECK("T3 the aggregate names the family and the counts",
          orig_has("the wall's display budget") && orig_has("ring-full (0xB)"));
    CHECK("T3 the aggregate is in the log ring", strstr(log_buf, "display budget") != NULL);
    CHECK("T3 the storm was fully consumed (22 of this family: first + 20 in-beat + the aggregate trigger)", wall_family_total[1] == 22);
}

/* T4: SETUP_PENDING is its own family under the same budget */
static void t4_setup_pending(void)
{
    reset_all();
    const char *s = "DwcGetNextEvent: DWC_TRB_STS_SETUP_PENDING fast-forward\n";
    mirror_shim_write(s, str_len(s));                /* first cause: family 0 */
    CHECK("T4 the first SETUP_PENDING passed verbatim", orig_seen_n == 1);
    for (int i = 0; i < 10; i++) {
        g_now += g_freq / 4;
        mirror_shim_write(s, str_len(s));
    }
    CHECK("T4 the family total counts them all", wall_family_total[0] >= 10);
    CHECK("T4 the family classifier names SETUP_PENDING", wall_family_of("x SETUP_PENDING y", 17) == 0);
}

/* T5: a wall line split across two writer calls classifies once */
static void t5_split_line(void)
{
    reset_all();
    const char *a = "DwcPrepareURB:Trb: physical endpoint[2] not";
    const char *b = " configured\n";
    mirror_shim_write(a, str_len(a));                /* no newline yet: held in the assembler */
    CHECK("T5 nothing classified while the line is open", orig_seen_n == 0);
    mirror_shim_write(b, str_len(b));                /* the newline completes it */
    CHECK("T5 the completed line showed once (the 0xC first cause)", orig_seen_n == 1);
    CHECK("T5 the assembled line is what the original saw",
          orig_line_contains(0, "physical endpoint[2] not configured"));
}

/* T6: every path reports every byte consumed */
static void t6_return_values(void)
{
    reset_all();
    const char *wall = "UsbDeviceSend: Failed to submit data transfer: Device Error\n";
    const char *plain = "usb: informational line\n";
    uint64_t r1 = mirror_shim_write(wall, str_len(wall));       /* the first cause */
    uint64_t r2 = mirror_shim_write(wall, str_len(wall));       /* suppressed (inside the beat) */
    uint64_t r3 = mirror_shim_write(plain, str_len(plain));     /* passthrough */
    CHECK("T6 shown, suppressed and passthrough all report the full length",
          r1 == str_len(wall) && r2 == str_len(wall) && r3 == str_len(plain));
}

/* T7: the HOB walk -- short generic HOBs do not stop it; the GUID gates hold; the PHIT bounds it */
static struct efi_config_table g_ct[2];
static struct efi_system_table g_st;

static void put_hob(uint64_t off, uint16_t type, uint16_t len)
{
    g_hobs[off] = (char)(type & 0xff);
    g_hobs[off + 1] = (char)(type >> 8);
    g_hobs[off + 2] = (char)(len & 0xff);
    g_hobs[off + 3] = (char)(len >> 8);
    memset(g_hobs + off + 4, 0, 4);
}
static void put_guid_hob(uint64_t off, uint16_t len, uint8_t *shim_ptr)
{
    static const efi_guid shim_hob_guid = { 0xbedaeabc, 0x5e70, 0x4d66, { 0x97, 0x33, 0x21, 0x3d, 0x07, 0x2b, 0x9d, 0x04 } };

    put_hob(off, 4, len);
    memcpy(g_hobs + off + 8, &shim_hob_guid, 16);
    memcpy(g_hobs + off + 0x18, &shim_ptr, 8);
}

static void t7_hob_walk(void)
{
    reset_all();
    memset(g_hobs, 0, sizeof(g_hobs));
    /* a PHIT whose EfiEndOfHobList lies before the shim HOB: the walk must stop there */
    put_hob(0, 1, 0x38);
    {
        uint64_t bound = (uint64_t)(uintptr_t)(g_hobs + 0x40);
        memcpy(g_hobs + 0x30, &bound, 8);            /* EfiEndOfHobList = g_hobs+0x40 */
    }
    put_guid_hob(0x40, 0x20, (uint8_t *)g_shim_slot);/* the shim HOB sits PAST the bound */
    put_hob(0x60, 0xffff, 8);
    g_ct[0].guid = (efi_guid){ 0x7739f24c, 0x93d7, 0x11d4, { 0x9a, 0x3a, 0x00, 0x90, 0x27, 0x3f, 0xc1, 0x4d } };
    g_ct[0].table = g_hobs;
    g_st.tables = g_ct;
    g_st.nr_tables = 1;
    g_st.con_out = NULL;
    ST = &g_st;
    g_dev_slot[2] = (uint64_t)(uintptr_t)sentinel_writer;
    shim_write_orig = sentinel_writer;
    mirror_install();
    CHECK("T7 the PHIT bound stops the walk: the shim past it is NOT hooked",
          g_dev_slot[2] == (uint64_t)(uintptr_t)sentinel_writer);
    /* a walkable list: a legal short generic HOB (8 B) first, then the shim HOB */
    reset_all();
    memset(g_hobs, 0, sizeof(g_hobs));
    put_hob(0, 3, 8);                                /* the legal short generic HOB */
    put_guid_hob(8, 0x20, (uint8_t *)g_shim_slot);
    put_hob(0x28, 0xffff, 8);
    g_ct[0].table = g_hobs;
    g_shim_slot[2] = (uint64_t)(uintptr_t)fake_locator;
    g_dev_slot[2] = (uint64_t)(uintptr_t)sentinel_writer;
    shim_write_orig = sentinel_writer;
    mirror_install();
    CHECK("T7 the short HOB did not stop the walk; the writer member is now the filter",
          g_dev_slot[2] == (uint64_t)(uintptr_t)mirror_shim_write);
    CHECK("T7 the install kept the original writer (the filter's fallback)",
          shim_write_orig == sentinel_writer);
    ST = NULL;                                       /* the other tests stay out of install */
}

int main(void)
{
    printf("== wave38 isolation harness (P0-4 + P1-5 generation) ==\n");
    t1_passthrough();
    t2_first_cause();
    t3_shared_budget();
    t4_setup_pending();
    t5_split_line();
    t6_return_values();
    t7_hob_walk();
    printf("== %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail != 0;
}
"""

out = PRELUDE + mirror_section + "\n" + mirror_install + "\n" + MAIN
open(sys.argv[2], "w", encoding="utf-8", newline="").write(out)
print(f"mirror harness written: {sys.argv[2]} ({len(out)} B)")
