#!/usr/bin/env python3
"""Wave 38 fix generation 2: P0-4 + P1-5 (review report 3).

P0-4 -- the vendor log hook's write ABI was written with three parameters; the real
EFI_SIO_WRITE (EFISerialPort.h:27-32, ShimLoader.c:28-37, FrameBufferSerialPortLib.c:298)
takes TWO (Buffer, NumberOfBytes) and returns UINTN. The blobs' dispatch restores
x0=Buffer, x1=Length before the tail-call (UsbFn 0x1f288, UsbDevice 0x19040). Fixes:
  - shim_write_t and mirror_shim_write become two-parameter;
  - the self-check probe passes a real text buffer + length (the old call handed the
    interface table as the Buffer and the string's address as the NumberOfBytes);
  - the HOB walk: the generic header is 8 bytes (legal short HOBs exist); the 0x18
    length applies only to reading a GUID extension's GUID, 0x20 before its pointer;
    the PHIT's EfiEndOfHobList (+0x30 on the type-1 handoff HOB) bounds the walk.

P1-5 -- the display budget, in the (now correct) loader write hook, FD bytes untouched:
  - cross-call bounded line assembly (DebugPrint writes are reassembled into whole
    lines across calls, 256 B cap; newline or full = a complete line);
  - the three USB wall families are classified (SETUP_PENDING / ring-full 0xB /
    not-configured 0xC), most specific first;
  - a SHARED budget: each family's first line passes verbatim (the first cause stays
    on the record -- three lines at most), later wall lines count per family, and at
    most ONE aggregated summary (family + suppressed counts) is emitted per two
    seconds across all families;
  - no sleeps, no recursion (the aggregate is formatted by hand and written straight
    to the original writer; print() is never called from inside the filter), and the
    wrapper always returns the consumed count so the caller never retries a suppressed
    write.

usage: patch-loader-v38c-p04.py LOADER_C
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

# ---- hunk 1: the budget's state, the classifier, the formatter, the per-line filter ----
# inserted right after mirror_take's definition, before the ConOut door: the filter needs
# mirror_take and shim_write_orig (declared here) in scope.
sub(
"""typedef efi_status (EFIAPI *sto_string_t)(struct efi_text_output *self, const char16 *str);
static sto_string_t con_out_orig;
""",
"""/* ---- P1-5 (review report 3): the wall's display budget, inside the shim write hook ---- */
/* The three USB wall families share ONE display budget: the first line of each family
 * passes verbatim (the first cause stays on the record -- three lines at most), later
 * wall lines are counted per family, and at most one aggregated summary (naming the
 * family and the suppressed counts) is shown per two seconds across all families. The
 * filter never sleeps and never recurses: the aggregate is formatted by hand (no
 * print() -- print paints through the console doors and would re-enter this filter)
 * and written straight to the original writer. Every wrapper path reports every byte
 * consumed, so the vendor's caller never retries a suppressed write. */
typedef uint64_t (EFIAPI *shim_write_t)(const char *buf, uint64_t len);
static shim_write_t shim_write_orig;

#define WALL_LINE_CAP 256
#define WALL_FAMILIES 3
#define WALL_BUDGET_BEAT (2ULL * READ_SYSREG(CNTFRQ_EL0))   /* two seconds, in ticks */

static const char *const wall_family_name[WALL_FAMILIES] = {
    "SETUP_PENDING", "ring-full (0xB)", "not-configured (0xC)"
};
static char wall_line[WALL_LINE_CAP];     /* the cross-call line assembler's buffer */
static uint64_t wall_line_len;
static uint64_t wall_family_count[WALL_FAMILIES];   /* suppressed since the last shown */
static uint64_t wall_family_total[WALL_FAMILIES];   /* never reset */
static uint64_t wall_family_first[WALL_FAMILIES];   /* each family's first cause shown */
static uint64_t wall_last_shown;          /* the shared budget's clock */
static uint64_t wall_budget_suppressed;   /* lines swallowed under the shared budget */
static uint64_t wall_budget_shown;        /* aggregates that made it to the screen */

/* the families, most specific first: SETUP_PENDING is its own beast (the ep0
 * fast-forward), then the two bulk submit families by their exact codes, then their
 * signature strings */
static int
wall_family_of(const char *line, uint64_t n)
{
	static const char *const sigs[WALL_FAMILIES][3] = {
		{ "SETUP_PENDING", "", "" },
		{ "0x8000000B", "no free URB nodes", "Failed to submit transfer" },
		{ "0x8000000C", "not configured", "" },
	};
	uint64_t f, k, m, scan;

	for (f = 0; f < WALL_FAMILIES; f++) {
		for (k = 0; k < 3 && sigs[f][k][0] != 0; k++) {
			const char *l = sigs[f][k];
			uint64_t nl = 0;
			while (l[nl] != 0) {
				nl++;
			}
			if (n < nl) {
				continue;
			}
			for (scan = 0; scan + nl <= n; scan++) {
				for (m = 0; m < nl && line[scan + m] == l[m]; m++) {
				}
				if (m == nl) {
					return (int)f;
				}
			}
		}
	}
	return -1;                    /* not a wall line: passthrough as before */
}

/* append one decimal, hand-rolled (print() is off limits inside the filter) */
static uint64_t
wall_put_u64(char *out, uint64_t cap, uint64_t n, uint64_t v)
{
	char tmp[24];
	uint64_t t = 0;

	if (v == 0) {
		v = 1;                    /* the triggering line counts as one */
	}
	while (v != 0 && t < sizeof(tmp)) {
		tmp[t++] = (char)('0' + (v % 10));
		v /= 10;
	}
	while (t != 0 && n < cap - 1) {
		out[n++] = tmp[--t];
	}
	return n;
}

/* the aggregate summary line: family name + suppressed-since-last + family total */
static uint64_t
wall_fmt_agg(char *out, uint64_t cap, int family)
{
	const char *pre = "usb: [the wall's display budget, one line per 2 s across all families] ";
	const char *p;
	uint64_t n = 0;

	for (p = pre; *p != 0 && n < cap - 1; p++) {
		out[n++] = *p++;
	}
	for (p = wall_family_name[family]; *p != 0 && n < cap - 1; p++) {
		out[n++] = *p++;
	}
	for (p = ": x"; *p != 0 && n < cap - 1; p++) {
		out[n++] = *p++;
	}
	n = wall_put_u64(out, cap, n, wall_family_count[family]);
	for (p = " suppressed here, x"; *p != 0 && n < cap - 1; p++) {
		out[n++] = *p++;
	}
	n = wall_put_u64(out, cap, n, wall_family_total[family]);
	for (p = " since the family's first\\n"; *p != 0 && n < cap - 1; p++) {
		out[n++] = *p++;
	}
	out[n] = 0;
	return n;
}

/* one complete line through the filter: classify, first cause, budget, display/record */
static void
wall_line_take(const char *line, uint64_t n)
{
	int family = wall_family_of(line, n);
	char agg[320];
	uint64_t alen, now;

	if (family < 0) {
		mirror_take(line, n);     /* a vendor line, but not a wall line: record as before */
		return;
	}
	wall_family_total[family]++;
	if (wall_family_first[family] == 0) {
		/* the family's first cause: show it verbatim once and keep it in the log */
		wall_family_first[family] = 1;
		mirror_take(line, n);
		if (shim_write_orig != NULL) {
			shim_write_orig(line, n);
		}
		wall_last_shown = READ_SYSREG(CNTVCT_EL0);
		return;
	}
	wall_family_count[family]++;
	now = READ_SYSREG(CNTVCT_EL0);
	if (wall_last_shown != 0 && now - wall_last_shown < WALL_BUDGET_BEAT) {
		wall_budget_suppressed++;   /* inside the shared beat: counted, not shown */
		return;
	}
	alen = wall_fmt_agg(agg, sizeof(agg), family);
	wall_budget_shown++;
	wall_last_shown = now;
	wall_family_count[family] = 0;
	mirror_take(agg, alen);
	if (shim_write_orig != NULL) {
		shim_write_orig(agg, alen);
	}
}

typedef efi_status (EFIAPI *sto_string_t)(struct efi_text_output *self, const char16 *str);
static sto_string_t con_out_orig;
""")

# ---- hunk 2: the two-parameter wrapper (the old typedef/wrapper replaced) ----------------------
sub(
"""typedef long (EFIAPI *shim_write_t)(void *dev, const char *buf, uint64_t len);
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
""",
"""/* P0-4 (review report 3): the REAL two-parameter EFI_SIO_WRITE. The old
 * three-parameter wrapper misread its arguments whenever the hook fired, and its
 * self-check handed the interface table as the Buffer. This filter reassembles
 * DebugPrint's writes into whole lines across calls and runs the wall's budget (P1-5);
 * every path returns the consumed count. */
static uint64_t EFIAPI
mirror_shim_write(const char *buf, uint64_t len)
{
	if (shim_write_orig == NULL) {
		return len;
	}
	if (mirror_busy || buf == NULL || len == 0) {
		return shim_write_orig(buf, len);
	}
	if (len < WALL_LINE_CAP) {
		uint64_t i;

		mirror_busy = 1;
		for (i = 0; i < len; i++) {
			char c = buf[i];

			if (c == '\\r') {
				continue;
			}
			if (c == '\\n') {
				wall_line_take(wall_line, wall_line_len);
				wall_line_len = 0;
				continue;
			}
			if (wall_line_len + 1 >= WALL_LINE_CAP) {
				wall_line_take(wall_line, wall_line_len);   /* full without a newline */
				wall_line_len = 0;
			}
			wall_line[wall_line_len++] = c;
		}
		mirror_busy = 0;
		return len;
	}
	/* a write bigger than a line: not DebugPrint's style -- passthrough unfiltered */
	mirror_busy = 1;
	mirror_take(buf, len);
	mirror_busy = 0;
	shim_write_orig(buf, len);
	return len;
}
""")

# ---- hunk 3: the probe becomes a two-parameter call with a real buffer ------------------------
sub(
"""			if (shim_write_orig != NULL) {
				*(shim_write_t *)((uint8_t *)dev + 0x10) = mirror_shim_write;
				vendor_door = 1;
				/* the probe, out through the wrapped member: the mirror captures its own
				 * echo, and that one line in the ring is the end-to-end proof */
				(*(shim_write_t *)((uint8_t *)dev + 0x10))(dev,
				    "usb: the vendor debug door echoes: the mirror is in\\n",
				    str_len("usb: the vendor debug door echoes: the mirror is in\\n"));
			}
""",
"""			if (shim_write_orig != NULL) {
				*(shim_write_t *)((uint8_t *)dev + 0x10) = mirror_shim_write;
				vendor_door = 1;
				/* P0-4: the probe is a real two-parameter write of a real text buffer
				 * (the old call handed the interface table as the Buffer and the string's
				 * address as the NumberOfBytes -- an unbounded paint if it ever fired).
				 * Out through the wrapped member: the filter reassembles it, classifies
				 * it as a non-wall line, records it, and passes it to the original. */
				(*(shim_write_t *)((uint8_t *)dev + 0x10))(
				    "usb: the vendor debug door echoes: the mirror is in\\n",
				    str_len("usb: the vendor debug door echoes: the mirror is in\\n"));
			}
""")

# ---- hunk 4: the HOB walk -- the generic header is 8 bytes, the 0x18/0x20 gates are GUID-only,
#      and the PHIT's EfiEndOfHobList bounds the walk ------------------------------------------
sub(
"""		for (hob = (uint8_t *)ST->tables[i].table;;) {
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
""",
"""		for (hob = (uint8_t *)ST->tables[i].table;;) {
			/* P0-4: the generic HOB header is 8 bytes and legal short HOBs exist; the
			 * 0x18 length applies only when reading a GUID extension's GUID (8-byte
			 * header + 16-byte GUID), 0x20 before reading its pointer. The type-1
			 * handoff table (PHIT) carries EfiEndOfHobList at +0x30: the walk's bound. */
			uint16_t type = (uint16_t)(hob[0] | (hob[1] << 8));
			uint16_t hlen = (uint16_t)(hob[2] | (hob[3] << 8));

			if (type == 0xffff || hlen < 8) {
				break;                /* the list's end (or a broken header): no shim block */
			}
			if (phit_end == 0 && type == 1 /* EFI_HOB_TYPE_HANDOFF */ && hlen >= 0x38) {
				phit_end = *(uint64_t *)(hob + 0x30);   /* EfiEndOfHobList */
			}
			if (phit_end != 0 && (uint64_t)(uintptr_t)hob >= phit_end) {
				break;                /* walked past the handoff table's own end */
			}
			if (type == 4 /* EFI_HOB_TYPE_GUID_EXTENSION */) {
				if (hlen < 0x18 || memcmp(hob + 8, &shim_hob_guid, sizeof(efi_guid)) != 0) {
					hob += hlen;
					continue;
				}
				if (hlen >= 0x20) {
					shim = *(uint8_t **)(hob + 0x18);
				}
				break;
			}
			hob += hlen;
		}
""")

# ---- hunk 5: the walker's local (phit_end) declaration -----------------------------------------
sub(
"""	uint64_t i;
	uint8_t *hob, *shim = NULL;
	void *dev = NULL;
	shim_locator_t locator;
	int vendor_door = 0;
""",
"""	uint64_t i;
	uint8_t *hob, *shim = NULL;
	void *dev = NULL;
	shim_locator_t locator;
	int vendor_door = 0;
	uint64_t phit_end = 0;
""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: P0-4 + P1-5 applied (5 hunks)")
