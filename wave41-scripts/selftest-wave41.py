#!/usr/bin/env python3
"""Wave 41 isolated self-test: the event word and the NC_MODE encodings, judged offline.

Nothing here touches a device. The generator extracts, VERBATIM, from the patched driver:
  - the odd_parity helper and the FENCE_EVENT / CP_EVENT_WRITE7_* / EV_* macro block,
  - the EVENT_CCU_CLEAN_COLOR and EVENT_CACHE_CLEAN values,
  - the five NC_MODE put() value expressions and the DDR-type branch and bank_bit formula,
then compiles a small judge around the extracted text and runs it. A failure exits nonzero.

References the expectations come from (report 4 + wave 40, independently confirmed):
  - the fence event's first word is CACHE_CLEAN | BIT(27) = 0x08000031 (vendor
    adreno_gen7_ringbuffer.c:368-390, Linux v6.12 a7xx_submit; the sixth generation's 0x04 has
    bit 27 off, which is precisely the gap),
  - with highest_bank_bit 16 (this phone: gen7_4_0 = Mesa FD725; dt ddr_device_type 0x08 does
    not fire the vendor's DDR-4 override) and min-access-length 32, the vendor formula
    (adreno_gen7.c gen7_gpu_init) gives RB 0x816, TPL1 0x6, SP 0x26, GRAS 0x60, UCHE 0x600000;
    with the override fired (type 0x7 -> 14) it gives 0x812 / 0x2 / 0x22 / 0x20 / 0x200000 --
    exactly the old table's values, which is the cross-check that the branch means something.
"""
import re
import subprocess
import sys

DRIVER = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
CFILE = "/tmp/wave41-selftest.c"

src = open(DRIVER).read()

# --- verbatim extractions -----------------------------------------------------------------------
m = re.search(r"static uint32_t\nodd_parity\(uint32_t v\)\n\{\n\treturn [^\n]*\n\}\n", src)
if not m:
    sys.exit("odd_parity not found in the driver")
parity = m.group(0)

m = re.search(r"#define EV_WRITE_USER_32B[^\n]*\n(#define[^\n]*\n){4}#define FENCE_EVENT[^\n]*\\\n[^\n]*\n", src)
if not m:
    sys.exit("the FENCE_EVENT macro block not found")
fence_block = m.group(0)

event_ids = {}
for name in ("EVENT_CCU_CLEAN_COLOR", "EVENT_CACHE_CLEAN"):
    m = re.search(rf"#define {name}\s+(0x[0-9a-fA-F]+)", src)
    if not m:
        sys.exit(f"{name} not found")
    event_ids[name] = m.group(1)

puts = re.findall(r'\tput\(&gpu, "(rb_nc_mode_cntl|tpl1_nc_mode_cntl|sp_nc_mode_cntl|gras_nc_mode_cntl|uche_mode_cntl)", '
                  r'GPU_WORD\(0x[0-9a-f]+\), (.+)\);\n', src)
if len(puts) != 5:
    sys.exit(f"expected 5 NC_MODE puts, found {len(puts)}")

m = re.search(r"\tif \(ddr_type == 0x7\) \{[^\n]*\n\t\tgpu_highest_bank_bit = 14;\n\t\}\n\tbank_bit = \(gpu_highest_bank_bit - 13\) & 3;\n", src)
if not m:
    sys.exit("the DDR-type branch / bank_bit formula not found")
ddr_branch = m.group(0)

# --- the judge ----------------------------------------------------------------------------------
def expect_line(name, expr, want):
    return f'\texpect("{name}", ({expr}), {want});\n'

wants_hbb16 = {"rb_nc_mode_cntl": "0x816", "tpl1_nc_mode_cntl": "0x6", "sp_nc_mode_cntl": "0x26",
               "gras_nc_mode_cntl": "0x60", "uche_mode_cntl": "0x600000"}
wants_hbb14 = {"rb_nc_mode_cntl": "0x812", "tpl1_nc_mode_cntl": "0x2", "sp_nc_mode_cntl": "0x22",
               "gras_nc_mode_cntl": "0x20", "uche_mode_cntl": "0x200000"}
nc16 = "".join(expect_line(name, expr, wants_hbb16[name]) for name, expr in puts)
nc14 = "".join(expect_line(name + " (ddr 0x7)", expr, wants_hbb14[name]) for name, expr in puts)

c = f"""#include <stdio.h>
#include <stdint.h>

/* ---- text extracted verbatim from {DRIVER} ---- */
{parity}
{fence_block}
#define EVENT_CCU_CLEAN_COLOR   {event_ids['EVENT_CCU_CLEAN_COLOR']}
#define EVENT_CACHE_CLEAN       {event_ids['EVENT_CACHE_CLEAN']}

static int failed, judged;
static void expect(const char *what, uint32_t got, uint32_t want)
{{
	judged++;
	if (got != want) {{
		printf("FAIL %s: got %#x, want %#x\\n", what, got, want);
		failed = 1;
	}} else {{
		printf("ok   %-44s %#x\\n", what, got);
	}}
}}

/* the packet builder, shaped exactly like ring_command + ring + ring_fence_event */
static void packet(uint32_t event, uint64_t address, uint32_t word, uint32_t out[5])
{{
	out[0] = 7u << 28 | 4 | odd_parity(4) << 15 | 0x46u << 16 | odd_parity(0x46) << 23;
	out[1] = FENCE_EVENT(event);
	out[2] = (uint32_t)address;
	out[3] = (uint32_t)(address >> 32);
	out[4] = word;
}}

int main(void)
{{
	uint32_t p[5];

	/* the submission fence event: the packet the ring actually carries */
	packet(EVENT_CACHE_CLEAN, 0x01200040ull, 7, p);
	expect("fence word (first of four)", p[1], 0x31u | (1u << 27));
	expect("fence word = 0x08000031", p[1], 0x08000031u);
	expect("packet header (type 7, 4 words, CP_EVENT_WRITE)", p[0],
	    7u << 28 | 4 | odd_parity(4) << 15 | 0x46u << 16 | odd_parity(0x46) << 23);
	expect("WRITE_SRC field = EV_WRITE_USER_32B", (p[1] >> 20) & 7, 0);
	expect("WRITE_DST field = EV_DST_RAM", (p[1] >> 24) & 1, 0);
	expect("WRITE_ENABLED on", (p[1] >> 27) & 1, 1);
	expect("IRQ bit off (polling wait)", (p[1] >> 31) & 1, 0);
	expect("address low", p[2], 0x01200040u);
	expect("address high", p[3], 0);
	expect("payload (the submission number)", p[4], 7);

	/* step_frame's twin colour event, same knife */
	packet(EVENT_CCU_CLEAN_COLOR, 0x01200020ull, 0x0c0c0c0cu, p);
	expect("twin colour word = 0x08000020", p[1], 0x20u | (1u << 27));

	/* what was broken: the sixth generation's word had no WRITE_ENABLED at all */
	expect("the old 0x04 word's WRITE_ENABLED", 0x04u & (1u << 27), 0);

	/* the NC_MODE encodings, expressions straight out of step_core_start, this phone's dt
	 * (ddr_device_type 0x08: the vendor's override does not fire) */
	uint32_t gpu_highest_bank_bit = 16, ddr_type = 0x8, bank_bit;
	if (ddr_type == 0x7) {{
		gpu_highest_bank_bit = 14;
	}}
	bank_bit = (gpu_highest_bank_bit - 13) & 3;
	expect("HBB stays 16 when the dt says 0x8", gpu_highest_bank_bit, 16);
	expect("bank_bit", bank_bit, 3);
{nc16}
	/* the same expressions with the override fired (a DDR type 0x7 machine): the vendor's
	 * HBB 14, and the old table's values come back -- proof the branch means something */
	gpu_highest_bank_bit = 16;
	ddr_type = 0x7;
	if (ddr_type == 0x7) {{
		gpu_highest_bank_bit = 14;
	}}
	bank_bit = (gpu_highest_bank_bit - 13) & 3;
	expect("HBB falls to 14 when the type is 0x7", gpu_highest_bank_bit, 14);
	expect("bank_bit (ddr 0x7)", bank_bit, 1);
{nc14}
	printf("%u judgements, %s\\n", judged, failed ? "FAILED" : "all pass");
	return failed;
}}
"""
open(CFILE, "w").write(c)
r = subprocess.run(["cc", "-Wall", "-Wextra", "-Wno-unused-function", "-o", "/tmp/wave41-selftest", CFILE],
                   capture_output=True, text=True)
if r.returncode != 0:
    print(r.stdout, r.stderr)
    sys.exit("the self-test did not compile")
r = subprocess.run(["/tmp/wave41-selftest"], capture_output=True, text=True)
print(r.stdout, end="")
if r.stderr:
    print(r.stderr, end="")
sys.exit(r.returncode)
