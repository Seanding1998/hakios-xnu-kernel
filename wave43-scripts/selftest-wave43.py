#!/usr/bin/env python3
"""Wave 43's isolated self-test (zero device): the fuel gauge driver's numbers are judged on
two fronts, the way wave 41's were.

1. Every register constant the driver carries is checked against the vendor sources it cites,
   parsed mechanically from refs/kernel_oneplus_sm8475 (and the live FDT dump for the I2C
   bus), not from this script's memory of them: the gauge's addresses from bq27xxx_battery.c's
   bq27541_regs table, the charger's from smb5-reg.h, the state and usb-type numbers from
   include/linux/power_supply.h, the SPMI arbiter's version-7 tables from the buttons driver
   that ran them on this phone, the bus and the address from intel/wave1b-scripts/fdt-full.txt.

2. The driver's own code -- power_status, the sanity windows, gauge_look, charger_look, feed,
   feed_static, extracted verbatim from the installed file -- runs in a C judge (gcc -O0)
   against mock buses, and the struct each scenario hands to hakios_battery_report() is
   checked field by field, including the size check the pipeline itself makes first
   (drivers/power/hakios.battery.cpp's twin-struct guard).

Run on the WSL side: python3 selftest-wave43.py (from anywhere: the paths below are absolute).
"""
import hashlib
import os
import re
import subprocess
import sys

REPO = "/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110"
KERNEL = "/home/cyrux/hakios/kernel"
DRIVER = os.path.join(KERNEL, "devices/phk110/drivers/power/hakios.fuelgauge.c")
CANONICAL = os.path.join(REPO, "wave43-scripts/hakios.fuelgauge.c")
VENDOR = "/home/cyrux/hakios/refs/kernel_oneplus_sm8475"
FDT = os.path.join(REPO, "intel/wave1b-scripts/fdt-full.txt")
JUDGE_C = "/tmp/wave43-selftest.c"
JUDGE = "/tmp/wave43-selftest"

results = []


def check(ok, name, detail=""):
    results.append((bool(ok), name, detail))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail and not ok else ""))
    return bool(ok)


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---- the driver, installed and canonical ------------------------------------------------------------
installed = open(DRIVER, encoding="utf-8").read()
canonical = open(CANONICAL, encoding="utf-8").read()
check(installed == canonical, "the installed driver is the canonical copy (wave43-scripts)",
      "%s vs %s" % (sha256_file(DRIVER)[:16], sha256_file(CANONICAL)[:16]))


def extract(text, start, end, what):
    n0 = text.count(start)
    n1 = text.count(end)
    check(n0 == 1 and n1 == 1, "extraction anchors of the %s appear once" % what,
          "%r x%d, %r x%d" % (start[:40], n0, end[:40], n1))
    if n0 != 1 or n1 == 0:
        return ""
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def constant(src, name):
    m = re.search(r"^#define\s+%s\s+(.+?)\s*(?:/\*.*)?$" % re.escape(name), src, re.M)
    return m.group(1) if m else None


drv_reg = {}
for m in re.finditer(r"^#define\s+GAUGE_(\w+)\s+(0x[0-9a-fA-F]+)", installed, re.M):
    drv_reg[m.group(1)] = int(m.group(2), 16)

# ---- 1a. the gauge's registers, against the vendor's bq27541 table ----------------------------------
bq = open(os.path.join(VENDOR, "drivers/power/supply/bq27xxx_battery.c"), encoding="utf-8").read()
i = bq.index("bq27541_regs[BQ27XXX_REG_MAX] = {")
j = bq.index("\n\t},", i)          # a table ends with "\t},"; "};", the next one, is tables away
table = bq[i:j]
vend_reg = {name: int(val, 16) for name, val in
            re.findall(r"\[BQ27XXX_REG_(\w+)\] = (0x[0-9a-fA-F]+)", table)}
line_no = bq[:i].count("\n") + 1
for dname in ("TEMP", "VOLT", "AI", "RC", "FCC", "CYCT", "SOC", "DCAP"):
    ok = drv_reg.get(dname) == vend_reg.get(dname)
    check(ok, "GAUGE_%s = %#x matches bq27541_regs[BQ27XXX_REG_%s] (bq27xxx_battery.c:%d)"
          % (dname, drv_reg.get(dname, 0), dname, line_no),
          "driver %#x, vendor %#x" % (drv_reg.get(dname, 0), vend_reg.get(dname, 0)))

# ---- 1b. the charger's registers, against smb5-reg.h -------------------------------------------------
smb = open(os.path.join(VENDOR, "drivers/power/supply/qcom/smb5-reg.h"), encoding="utf-8").read()
bases = {name: int(v, 16) for name, v in
         re.findall(r"^#define\s+(\w+_BASE)\s+0[xX]([0-9A-Fa-f]+)", smb, re.M)}
offsets = {}
for name, base, lit in re.findall(r"^#define\s+(\w+)\s+\((\w+)_BASE \+ (0[xX][0-9A-Fa-f]+)\)", smb, re.M):
    offsets[name] = (base, int(lit, 16))
plain = {}
for name, lit in re.findall(r"^#define\s+(\w+)\s+(0[xX][0-9A-Fa-f]+)\s*(?:/\*.*)?$", smb, re.M):
    plain[name] = int(lit, 16)
bits = {name: 1 << int(b) for name, b in re.findall(r"^#define\s+(\w+)\s+BIT\((\d+)\)", smb, re.M)}
genmasks = {name: ((1 << (int(hi) + 1)) - 1) & ~((1 << int(lo)) - 1)
            for name, hi, lo in re.findall(r"^#define\s+(\w+)\s+GENMASK\((\d+),\s*(\d+)\)", smb, re.M)}
smb_line = {}
for n, line in enumerate(smb.splitlines(), 1):
    m = re.match(r"#define\s+(\w+)\s", line)
    if m and m.group(1) not in smb_line:
        smb_line[m.group(1)] = n

check(bases.get("CHGR_BASE") == 0x1000 and bases.get("USBIN_BASE") == 0x1300 and
      bases.get("BATIF_BASE") == 0x1200 and bases.get("TYPEC_BASE") == 0x1500,
      "smb5-reg.h block bases: CHGR 0x1000, DCDC 0x1100, BATIF 0x1200, USBIN 0x1300, TYPEC 0x1500")
check(offsets.get("BATTERY_CHARGER_STATUS_1_REG") == ("CHGR", 0x06),
      "BATTERY_CHARGER_STATUS_1_REG = CHGR_BASE + 0x06 (smb5-reg.h:%d)"
      % smb_line.get("BATTERY_CHARGER_STATUS_1_REG", 0))
check(genmasks.get("BATTERY_CHARGER_STATUS_MASK") == 7,
      "BATTERY_CHARGER_STATUS_MASK = GENMASK(2,0) = 7")
check(plain.get("INT_RT_STS_OFFSET") == 0x10,
      "INT_RT_STS_OFFSET = 0x10 (smb5-reg.h:%d)" % smb_line.get("INT_RT_STS_OFFSET", 0))
check(bits.get("USBIN_PLUGIN_RT_STS_BIT") == 1 << 4,
      "USBIN_PLUGIN_RT_STS_BIT = BIT(4) (smb5-reg.h:%d)" % smb_line.get("USBIN_PLUGIN_RT_STS_BIT", 0))
check(offsets.get("TYPE_C_MISC_STATUS_REG") == ("TYPEC", 0x0B),
      "TYPE_C_MISC_STATUS_REG = TYPEC_BASE + 0x0B (smb5-reg.h:%d)"
      % smb_line.get("TYPE_C_MISC_STATUS_REG", 0))
check(bits.get("CC_ATTACHED_BIT") == 1 << 0,
      "CC_ATTACHED_BIT = BIT(0) (smb5-reg.h:%d)" % smb_line.get("CC_ATTACHED_BIT", 0))
check(plain.get("PERPH_TYPE_OFFSET") == 0x04 and plain.get("PERPH_SUBTYPE_OFFSET") == 0x05,
      "PERPH_TYPE_OFFSET 0x04 / PERPH_SUBTYPE_OFFSET 0x05")
check(constant(installed, "USBIN_INT_RT_STS") == "0x10", "driver USBIN_INT_RT_STS = 0x10")
check(constant(installed, "USBIN_PLUGIN_BIT") == "(1u << 4)", "driver USBIN_PLUGIN_BIT = BIT(4)")
check(constant(installed, "TYPE_C_MISC_STATUS") == "0x0b", "driver TYPE_C_MISC_STATUS = 0x0b")
check(constant(installed, "TYPE_C_CC_ATTACHED_BIT") == "(1u << 0)",
      "driver TYPE_C_CC_ATTACHED_BIT = BIT(0)")
check(constant(installed, "CHGR_STATUS_1") == "0x06", "driver CHGR_STATUS_1 = 0x06")
check(constant(installed, "CHGR_STATUS_MASK") == "7u", "driver CHGR_STATUS_MASK = 7")
check(constant(installed, "REG_TYPE") == "0x04", "driver REG_TYPE = 0x04")
check(constant(installed, "REG_SUBTYPE") == "0x05", "driver REG_SUBTYPE = 0x05")

# the peripheral numbers: the SMB5 bases divided by 0x100, on slave 3
for name, base, pid in (("chgr", 0x1000, 0x310), ("batif", 0x1200, 0x312),
                        ("usbin", 0x1300, 0x313), ("typec", 0x1500, 0x315)):
    ok = ".id = 0x%03x" % pid in installed and bases.get(name.upper() + "_BASE") == base
    check(ok, "peripheral %s id 0x%03x = slave 3 | %s_BASE 0x%04x / 0x100" % (name, pid, name.upper(), base))

# the charger's state machine, against the vendor's enum of BATTERY_CHARGER_STATUS_1
# (INHIBIT_CHARGE carries an explicit "= 0"; tokens after the "enum {", in order, are the values)
i = smb.index("BATTERY_CHARGER_STATUS_MASK")
j = smb.index("};", i)
vend_block = smb[i:j].split("enum {", 1)[1]
vend_states = {}
for value, name in enumerate(re.findall(r"[A-Z][A-Z_]*", vend_block)):
    vend_states[name] = value
# the driver's enum is written on one line: INHIBIT = 0, TRICKLE, PRE_CHARGE, ...
i2 = installed.index("enum charger_state {")
j2 = installed.index("};", i2)
drv_enum = {}
for value, name in enumerate(re.findall(r"[A-Z][A-Z_]*", installed[i2:j2])):
    drv_enum[name] = value
for d, v in (("INHIBIT", "INHIBIT_CHARGE"), ("TRICKLE", "TRICKLE_CHARGE"),
             ("PRE_CHARGE", "PRE_CHARGE"), ("FULLON", "FULLON_CHARGE"),
             ("TAPER", "TAPER_CHARGE"), ("TERMINATE", "TERMINATE_CHARGE"),
             ("PAUSE", "PAUSE_CHARGE"), ("DISABLED", "DISABLE_CHARGE")):
    check(drv_enum.get(d) == vend_states.get(v) == {
        "INHIBIT_CHARGE": 0, "TRICKLE_CHARGE": 1, "PRE_CHARGE": 2, "FULLON_CHARGE": 3,
        "TAPER_CHARGE": 4, "TERMINATE_CHARGE": 5, "PAUSE_CHARGE": 6, "DISABLE_CHARGE": 7}.get(v),
        "charger state %s = %d (vendor %s)" % (d, drv_enum.get(d, -1), v))

# ---- 1c. the state and usb-type numbers, against the vendor's power_supply.h -------------------------
ps = open(os.path.join(VENDOR, "include/linux/power_supply.h"), encoding="utf-8").read()


def enum_values(text, header):
    i = text.index(header)
    j = text.index("};", i)
    out = {}
    value = 0
    for line in text[i:j].splitlines():
        mm = re.match(r"\s+(\w+)(?:\s*=\s*(\d+))?,?\s*(?:/\*.*)?$", line)
        if mm:
            if mm.group(2) is not None:
                value = int(mm.group(2))
            out[mm.group(1)] = value
            value += 1
    return out


status = enum_values(ps, "enum {\n\tPOWER_SUPPLY_STATUS_UNKNOWN = 0,")
usb_types = enum_values(ps, "enum power_supply_usb_type {")
for name, want in (("POWER_SUPPLY_STATUS_CHARGING", 1), ("POWER_SUPPLY_STATUS_DISCHARGING", 2),
                   ("POWER_SUPPLY_STATUS_NOT_CHARGING", 3), ("POWER_SUPPLY_STATUS_FULL", 4)):
    m = re.search(r"#define\s+%s\s+(\d+)" % name, installed)
    check(status.get(name) == want and m is not None and int(m.group(1)) == want,
          "%s = %d (power_supply.h, driver)" % (name, want))
check(usb_types.get("POWER_SUPPLY_USB_TYPE_C") == 5 and
      constant(installed, "POWER_SUPPLY_USB_TYPE_C") == "5",
      "POWER_SUPPLY_USB_TYPE_C = 5 (power_supply.h, driver)")

# ---- 1d. the arbiter's tables, against the driver that ran them on this phone ------------------------
buttons = open(os.path.join(KERNEL, "drivers/input/hakios.buttons.c"), encoding="utf-8").read()
check("arb_apid_map = 0x2000" in installed and "arb_apid_map = 0x2000" in buttons.replace(" ", " "),
      "v7 APID->PPID table at core+0x2000 (buttons.c, Linux spmi-pmic-arb v7 ops)")
check("arb_owner_base = 0;" in installed and "arb_owner_base = 0x700;" in buttons,
      "v7 owner table at cnfg+0 / v5's at +0x700 (buttons.c)")
check("arb_obs_system = 0x8000" in installed and "arb_obs_stride = 0x20" in installed,
      "v7 observer channels at obsrvr+0x8000*system+0x20*apid (buttons.c)")
check("ARB_CORE_PHYS           0x0c400000UL" in installed and
      "ARB_CNFG_PHYS           0x0c42d000UL" in installed and
      "ARB_OBSERVER_PHYS       0x0c440000UL" in installed,
      "the arbiter's three windows are this phone's (buttons' boot-arg values, Boot #14-16)")

# ---- 1e. the bus and the address, against the live FDT -----------------------------------------------
fdt = open(FDT, encoding="utf-8", errors="replace").read()
i = fdt.index("NODE //soc/i2c@980000")
j = fdt.index("NODE //soc/spi@980000", i)
node = fdt[i:j]
check("bq27541-battery@55" in node and "compatible = 'oplus,bq27541-battery'" in node and
      "status = 'okay'" in node, "the live FDT: bq27541-battery@55, oplus compatible, okay")
check("reg = [1 words: #55]" in node, "the gauge's I2C address is 0x55 (fdt-full.txt)")
check("GAUGE_ADDRESS           0x55" in installed, "driver GAUGE_ADDRESS = 0x55")
check("PIN_SDA                 26" in installed and "PIN_SCL                 27" in installed,
      "driver pins: GPIO 26 data, 27 clock (fdt qupv3_se0_i2c)")
check("qcom,clk-freq-out = [1 words: #186a0]" in fdt, "the bus's clock is 100 kHz (fdt-full.txt)")

# ---- 2. the C judge ----------------------------------------------------------------------------------
# the twin struct is not copied here: it is extracted from the header itself, as the pipeline
# keeps its own copy in hakios.battery.cpp and the size guard between the two is what refuses
# a state that disagrees
header = open(os.path.join(KERNEL, "xnu/files/bsd/sys/hakios.input.h"), encoding="utf-8").read()
i = header.index("struct hakios_battery_state {")
j = header.index("};", i)
twin = header[i:j + 2]
n_lines = len(re.findall(r"^\t", twin, re.M))
n_fields = sum(len(re.findall(r"\b(u?int\d+_t)\s+([\w, ]+);", line)) and
               len(re.split(r",\s*", re.search(r"\b(?:u)?int\d+_t\s+([\w, ]+);", line).group(1)))
               for line in twin.splitlines() if re.match(r"\t(u|u?int)", line))
check(n_lines == 11 and n_fields == 15, "the pipeline's twin struct: 11 lines of 15 fields",
      "%d lines, %d fields" % (n_lines, n_fields))
check("sizeof(struct hakios_battery_state)" in twin, "the twin struct's first field is the size")

blocks = {}
blocks["periphs"] = extract(installed, "struct peripheral {", "/* How the reads have gone", "peripherals")
blocks["charger"] = extract(installed, "/* ---- the charger's registers", "/* ---- the I2C by hand", "charger")
blocks["sanity"] = extract(installed, "/*\n * The sanity windows", "/* ---- the state this driver keeps", "sanity")
blocks["state"] = extract(installed, "/* ---- the state this driver keeps", "static void\ngauge_look", "state")
blocks["gauge_look"] = extract(installed, "static void\ngauge_look(void)", "\nstatic void\ncharger_look", "gauge_look")
blocks["charger_look"] = extract(installed, "static void\ncharger_look(void)",
                                 "/* What goes to the pipeline", "charger_look")
blocks["feed"] = extract(installed, "/* What goes to the pipeline", "static void\nsay_summary", "feed")
if not all(blocks.values()):
    sys.exit("an extraction failed; the judge is not built")

JUDGE_HEAD_A = """/* Generated by wave43-scripts/selftest-wave43.py -- do not edit; see the generator's docstring. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <stdlib.h>

static int passed, failed;
#define CHECK(cond, name) do { if (cond) { passed++; printf("PASS %s\\n", name); } \\
    else { failed++; printf("FAIL %s\\n", name); } } while (0)

/* the pipeline's twin of the struct, verbatim from xnu/files/bsd/sys/hakios.input.h
 * (drivers/power/hakios.battery.cpp keeps its own copy and refuses a state whose size
 * disagrees: that check is replayed here) */
"""

JUDGE_HEAD_B = """

static struct hakios_battery_state captured[32];
static int captured_n, refused;

static void hakios_battery_report(const struct hakios_battery_state *b)
{
	if (b->size != sizeof(struct hakios_battery_state)) {
		refused++;
		return;                 /* the pipeline's twin-struct guard */
	}
	captured[captured_n++] = *b;
}

/* one SPMI lock and unlock per transfer in the driver; here they do nothing */
void hakios_spmi_lock(void) {}
void hakios_spmi_unlock(void) {}

/* the mock buses: a register file for the gauge, three status bytes for the charger's blocks */
static uint16_t gauge_regs[256];
static bool gauge_answers[256];
static uint8_t charger_bytes[3];        /* 0 usbin rt-sts, 1 typec misc, 2 chgr status-1 */
static bool charger_present[3];
"""

JUDGE_HEAD = JUDGE_HEAD_A + twin + JUDGE_HEAD_B

JUDGE_MOCKS = r"""
static bool
gauge_read_word(uint8_t reg, uint16_t *word)
{
	if (!gauge_answers[reg]) {
		return false;
	}
	*word = gauge_regs[reg];
	return true;
}

static const char *
spmi_read(const struct peripheral *p, uint8_t reg, uint8_t *bytes, uint32_t count)
{
	int which = p == &usbin ? 0 : p == &typec ? 1 : p == &chgr ? 2 : -1;

	if (which < 0 || !charger_present[which]) {
		return "the mock has no answer here";
	}
	*bytes = charger_bytes[which];
	(void)reg;
	(void)count;
	return NULL;
}
"""

JUDGE_TAIL = r"""
/* the thread's inner step, as the driver's loop has it: nothing feeds until the gauge's SOC
 * has passed its window once */
static void
poll_once(void)
{
	charger_look();
	gauge_look();
	if (gauge.soc_ok) {
		feed();
	}
	polls++;
}

static void
reset_gauge(void)
{
	memset(&gauge, 0, sizeof(gauge));
	external = typec_attached = external_ok = charger_ok = typec_ok = false;
	charger_state = DISABLED;
	charge_word_said = false;
	captured_n = 0;
}

static void
set_gauge(unsigned soc, unsigned mv, int ma, unsigned temp, unsigned rc, unsigned fcc,
          unsigned dcap, unsigned cyct)
{
	memset(gauge_answers, 0, sizeof(gauge_answers));
	gauge_regs[GAUGE_SOC] = (uint16_t)soc; gauge_answers[GAUGE_SOC] = true;
	gauge_regs[GAUGE_VOLT] = (uint16_t)mv; gauge_answers[GAUGE_VOLT] = true;
	gauge_regs[GAUGE_AI] = (uint16_t)(int16_t)ma; gauge_answers[GAUGE_AI] = true;
	gauge_regs[GAUGE_TEMP] = (uint16_t)temp; gauge_answers[GAUGE_TEMP] = true;
	gauge_regs[GAUGE_RC] = (uint16_t)rc; gauge_answers[GAUGE_RC] = true;
	gauge_regs[GAUGE_FCC] = (uint16_t)fcc; gauge_answers[GAUGE_FCC] = true;
	gauge_regs[GAUGE_DCAP] = (uint16_t)dcap; gauge_answers[GAUGE_DCAP] = true;
	gauge_regs[GAUGE_CYCT] = (uint16_t)cyct; gauge_answers[GAUGE_CYCT] = true;
}

static void
set_charger(int usbin_present, uint8_t usbin_sts, int typec_present, uint8_t typec_sts,
            int chgr_present, uint8_t chgr_sts)
{
	charger_present[0] = usbin_present; charger_bytes[0] = usbin_sts;
	charger_present[1] = typec_present; charger_bytes[1] = typec_sts;
	charger_present[2] = chgr_present; charger_bytes[2] = chgr_sts;
	usbin.found = typec.found = chgr.found = batif.found = true;
}

int
main(void)
{
	/* the numbers the pipeline takes, as its header names them */
	CHECK(POWER_SUPPLY_STATUS_CHARGING == 1, "status charging is 1");
	CHECK(POWER_SUPPLY_STATUS_DISCHARGING == 2, "status discharging is 2");
	CHECK(POWER_SUPPLY_STATUS_NOT_CHARGING == 3, "status not-charging is 3");
	CHECK(POWER_SUPPLY_STATUS_FULL == 4, "status full is 4");
	CHECK(POWER_SUPPLY_USB_TYPE_C == 5, "usb type C is 5");

	/* S1: discharging on the battery, nothing on the port */
	reset_gauge();
	set_gauge(63, 7871, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0x00, 1, 0x00, 1, DISABLED);
	poll_once();
	CHECK(captured_n == 1 && refused == 0, "S1: one report, and the size guard passes");
	if (captured_n == 1) {
		struct hakios_battery_state *b = &captured[0];
		CHECK(b->present == 1, "S1: present");
		CHECK(b->percent_hundredths == 6300, "S1: 63 percent as hundredths");
		CHECK(b->voltage_uv == 7871000, "S1: 7871 mV");
		CHECK(b->current_ua == -412000, "S1: -412 mA (out of the battery)");
		CHECK(b->temperature_hundredths == 2800, "S1: 28.00 C from 3011 tenths of a kelvin");
		CHECK(b->external == 0, "S1: nothing on the port");
		CHECK(b->status == POWER_SUPPLY_STATUS_DISCHARGING, "S1: discharging (the vendor's table)");
		CHECK(b->charge_uah == 1500000 && b->full_uah == 4800000 && b->design_uah == 5000000,
		    "S1: the capacities in uAh");
		CHECK(b->cycles == 123, "S1: cycle count");
		CHECK(b->usb_type == 0, "S1: no type with no attachment");
	}

	/* S2: on the charger, charging, a Type-C attachment */
	reset_gauge();
	set_gauge(40, 8600, 1900, 3035, 1900, 4800, 5000, 123);
	set_charger(1, USBIN_PLUGIN_BIT, 1, TYPE_C_CC_ATTACHED_BIT, 1, FULLON);
	poll_once();
	CHECK(captured_n == 1, "S2: one report");
	if (captured_n == 1) {
		CHECK(captured[0].external == 1, "S2: the plug bit");
		CHECK(captured[0].status == POWER_SUPPLY_STATUS_CHARGING, "S2: charging (the vendor's table)");
		CHECK(captured[0].usb_type == POWER_SUPPLY_USB_TYPE_C, "S2: a Type-C attachment says C");
		CHECK(captured[0].current_ua == 1900000, "S2: +1.9 A into the battery");
	}

	/* S3: the charger says terminated: full */
	reset_gauge();
	set_gauge(100, 8850, 5, 3010, 4800, 4800, 5000, 123);
	set_charger(1, USBIN_PLUGIN_BIT, 1, 0, 1, TERMINATE);
	poll_once();
	CHECK(captured_n == 1 && captured[0].status == POWER_SUPPLY_STATUS_FULL,
	    "S3: terminated reads full");

	/* S4: paused and disabled read not charging */
	reset_gauge();
	set_gauge(80, 8100, 0, 3000, 3800, 4800, 5000, 123);
	set_charger(1, USBIN_PLUGIN_BIT, 1, 0, 1, PAUSE);
	poll_once();
	CHECK(captured_n == 1 && captured[0].status == POWER_SUPPLY_STATUS_NOT_CHARGING, "S4a: paused");
	reset_gauge();
	set_gauge(80, 8100, 0, 3000, 3800, 4800, 5000, 123);
	set_charger(1, USBIN_PLUGIN_BIT, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured_n == 1 && captured[0].status == POWER_SUPPLY_STATUS_NOT_CHARGING, "S4b: disabled");

	/* S5: the vendor's own branch -- terminated with nothing on the port is full there too */
	reset_gauge();
	set_gauge(55, 7900, -300, 3000, 2600, 4800, 5000, 123);
	set_charger(1, 0x00, 1, 0, 1, TERMINATE);
	poll_once();
	CHECK(captured_n == 1 && captured[0].status == POWER_SUPPLY_STATUS_FULL &&
	    captured[0].external == 0, "S5: terminated with no plug is full, external stays 0");

	/* S6: the F17 risk-table refinement -- a charging state machine against an outward current */
	reset_gauge();
	set_gauge(70, 8000, -500, 3000, 3300, 4800, 5000, 123);
	set_charger(1, USBIN_PLUGIN_BIT, 1, 0, 1, FULLON);
	poll_once();
	CHECK(captured_n == 1 && captured[0].status == POWER_SUPPLY_STATUS_NOT_CHARGING,
	    "S6: full-on with -500 mA reads not charging");
	charge_word_said = false;
	poll_once();
	CHECK(charge_word_said, "S6: the remark is made while the two disagree");

	/* S7: a state of charge outside the window is not believed, and nothing is fed */
	reset_gauge();
	set_gauge(65535, 7871, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	captured_n = 0;
	poll_once();
	CHECK(captured_n == 0, "S7: a nonsense SOC feeds nothing");

	/* S8: a register that stops answering leaves the last good value in place */
	reset_gauge();
	set_gauge(63, 7871, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	gauge_answers[GAUGE_SOC] = false;
	poll_once();
	CHECK(captured_n == 2 && captured[1].percent_hundredths == 6300, "S8: the stale SOC is kept");

	/* S9: a temperature that never answers goes out as the pipeline's not-known */
	reset_gauge();
	set_gauge(63, 7871, -412, 3011, 1500, 4800, 5000, 123);
	gauge_answers[GAUGE_TEMP] = false;
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured_n == 1 && captured[0].temperature_hundredths == TEMP_NOT_KNOWN,
	    "S9: no temperature is the pipeline's not-known");
	CHECK((TEMP_NOT_KNOWN + 50) / 100 == -273, "S9: the not-known rounds to -273 C");

	/* S10: the sanity windows hold each field alone */
	reset_gauge();
	set_gauge(50, 2400, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured[0].voltage_uv == 0, "S10a: 2.4 V is below the window, not believed");
	reset_gauge();
	set_gauge(50, 9600, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured[0].voltage_uv == 0, "S10b: 9.6 V is above the window, not believed");
	reset_gauge();
	set_gauge(50, 4400, 0, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured[0].voltage_uv == 4400000, "S10c: a single cell's 4.4 V passes the wide window");
	reset_gauge();
	set_gauge(50, 7871, -32768, 3011, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured[0].current_ua == 0, "S10d: -32.768 A is outside the window, not believed");
	reset_gauge();
	set_gauge(50, 7871, -412, 25000, 1500, 4800, 5000, 123);
	set_charger(1, 0, 1, 0, 1, DISABLED);
	poll_once();
	CHECK(captured[0].temperature_hundredths == TEMP_NOT_KNOWN,
	    "S10e: an absurd temperature is outside the window, not believed");

	/* S11: the static mode feeds exactly what the SweetBattery precedent does */
	reset_gauge();
	running_mode = 1;
	static_soc = 100;
	feed_static();
	CHECK(captured_n == 1 && captured[0].percent_hundredths == 10000 && captured[0].present == 1 &&
	    captured[0].external == 0 && captured[0].status == POWER_SUPPLY_STATUS_DISCHARGING,
	    "S11a: static 100 percent, no charger, discharging");
	CHECK(captured[0].voltage_uv == 0 && captured[0].current_ua == 0 &&
	    captured[0].charge_uah == 0 && captured[0].usb_type == 0,
	    "S11a: every detail field at zero");
	reset_gauge();
	running_mode = 1;
	static_soc = 77;
	feed_static();
	CHECK(captured_n == 1 && captured[0].percent_hundredths == 7700, "S11b: the static value is settable");

	/* S12: charger blocks nobody answers degrade only the plug bit */
	reset_gauge();
	set_gauge(63, 7871, -412, 3011, 1500, 4800, 5000, 123);
	set_charger(0, 0, 0, 0, 0, 0);
	poll_once();
	CHECK(captured_n == 1 && captured[0].external == 0 &&
	    captured[0].status == POWER_SUPPLY_STATUS_DISCHARGING,
	    "S12: no charger registers, the plug reads nothing-on-the-port");

	printf("%d passed, %d failed\n", passed, failed);
	return failed ? 1 : 0;
}
"""

# the gauge's register addresses (checked above against the vendor's table) go into the judge
# as defines: they live in the driver's I2C section, which is not extracted
gauge_defines = "".join("#define GAUGE_%s 0x%x\n" % (name, addr) for name, addr in sorted(drv_reg.items()))

judge = (JUDGE_HEAD + gauge_defines + blocks["periphs"] + blocks["charger"] + blocks["sanity"] +
         blocks["state"] + JUDGE_MOCKS + blocks["gauge_look"] + blocks["charger_look"] +
         blocks["feed"] + JUDGE_TAIL)
open(JUDGE_C, "w", encoding="utf-8").write(judge)

build = subprocess.run(["gcc", "-std=gnu11", "-O0", "-Wall", "-o", JUDGE, JUDGE_C],
                       capture_output=True, text=True)
check(build.returncode == 0, "the judge compiles (gcc -O0)", build.stderr[-800:])
if build.returncode != 0:
    sys.exit(1)

run = subprocess.run([JUDGE], capture_output=True, text=True)
print(run.stdout, end="")
check(run.returncode == 0, "the judge's verdict is green", run.stdout[-400:])

bad = [name for ok, name, _ in results if not ok]
print("\nwave43 selftest: %d checks, %d failed%s" % (len(results), len(bad),
      ("; failed: " + "; ".join(bad)) if bad else ""))
sys.exit(1 if bad else 0)
