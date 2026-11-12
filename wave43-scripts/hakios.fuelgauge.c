/*
 * The fuel gauge of the OnePlus Ace 2 (phk110): the state of the battery, read from the two
 * buses that reach it without the audio DSP (whose battery manager the phone's Android asks;
 * ours is not brought up), and fed to the battery pipeline the system already has
 * (drivers/power/hakios.battery.c: hakios_battery_report(), which lights the sysctls
 * kern.hakios.battery_* and HakiosBattery, the IOPMPowerSource powerd reads the charge from,
 * and with it the status bar's battery, the lock screen's "Charging", Settings > Battery).
 * Nothing in the pipeline is changed here; this driver is only where its values come from.
 *
 * THIS DRIVER ONLY READS. Nothing is written to the gauge (whose authentication and
 * calibration registers Oplus' own driver writes, and this one never touches), to the PMIC,
 * or to any pin beyond the two the I2C by hand borrows for a transaction and gives back as
 * they were found. Charging itself stays the ADSP firmware's work (the tree gives it
 * qcom,pmic_glink/qcom,battery_charger); this kernel does not run that firmware, so whatever
 * the charger does while we watch it, it does of its own. The way to the PMIC's registers is
 * the same one the buttons take (docs/research/f17-battery-display.md).
 *
 * The hardware, the live device tree being the authority (intel/wave1b-scripts/fdt-full.txt):
 *   gauge    TI bq27541 -- the tree's node is bq27541-battery@55 with compatible
 *            "oplus,bq27541-battery" and qcom,batt_bq28z610 (the bq28z610 register table,
 *            which shares every address this driver reads with the bq27541's) -- on the
 *            serial engine 0 I2C at 0x980000, 100 kHz, address 0x55, its pins GPIO 26 (data)
 *            and 27 (clock), function qup0, with pull-ups. As for the amplifiers and the
 *            vibration motor of the reference phone, the two pins are taken for each
 *            transaction by hand and given back as they were found.
 *   charger  PM8350B, SPMI slave 3: the SMB5 family's blocks, CHGR at 0x1000, BATIF at
 *            0x1200, USBIN at 0x1300, TYPEC at 0x1500 -- in the arbiter's table, slave 3 with
 *            peripherals 0x10, 0x12, 0x13 and 0x15. Their real-time status tells a USB plug
 *            (USBIN 0x10, bit 4), a Type-C attachment (TYPEC 0x0b, bit 0) and the charger's
 *            own state machine (CHGR 0x06, its low three bits: inhibited, trickle, pre,
 *            full-on, taper, terminated, paused, disabled). The blocks are the ADSP's to
 *            drive; the arbiter's observer channel may read any peripheral whoever owns it --
 *            the buttons driver has read such registers 30,006 times on this phone with 2
 *            failures (docs/waves/wave12-touch-buttons.md).
 *
 * Register maps [VENDOR refs/kernel_oneplus_sm8475, branch oneplus/sm8475_b_16.0.0_ace_2]:
 * the gauge's from drivers/power/supply/bq27xxx_battery.c (bq27541_regs; a word's bytes are
 * little-endian, as that driver's i2c_smbus_read_word_data reads them), the charger's from
 * drivers/power/supply/qcom/smb5-reg.h and smb5-lib.c -- whose get_prop_usb_present and
 * get_prop_batt_status the reading and the state synthesis below follow.
 *
 * Two modes, on the fuelgauge= boot argument:
 *   fuelgauge=1  a static battery, no bus touched: present, at fuelgauge_static_soc= percent
 *                (100), not on a charger, discharging. This is the iPhone port ios-sweet's
 *                "SweetBattery" (its patch 0062), which showed that a battery service alone
 *                -- any battery service -- is what turns the status bar's empty red battery
 *                into a battery icon ("Battery icon OK (static 100%)"). It lies about one
 *                number, on purpose, and says "static" in every line of its log.
 *                Why a static value rather than a clock's estimate of the drain (percent
 *                falling with the time powered on): an estimate needs to be told the
 *                capacity and the drain and the hour it started from, and it compounds its
 *                error from there; a battery that "reaches" zero while the phone still runs
 *                lies worse than one that says full and keeps saying it -- and the pipeline's
 *                guard (hakios.battguard.c, battery_stop=) would hand the run back at the
 *                estimate's zero with the battery still good. The truth is mode 2's to tell;
 *                the static mode is only to keep the icon human until the buses answer, and
 *                it never speaks without the word "static".
 *   fuelgauge=2  the real readings: the PM8350B's plug and charge state over the SPMI
 *                arbiter's observer, the gauge's registers by hand over GPIO 26 and 27. The
 *                charger's blocks and the gauge do not need each other: when the arbiter
 *                refuses a charger block, the gauge alone still feeds the percentage (with
 *                the plug bit reading "nothing on the port"), and the other way round. Until
 *                the gauge has answered once with a state of charge that passes the sanity
 *                windows, nothing is fed to the pipeline at all: the pipeline's percentage
 *                clamps to 0..100, so an "unknown" cannot ride it, and a battery icon at
 *                0 percent would be a worse lie than no battery icon. After that, what fails
 *                fails alone: a charger register that refuses to be read degrades the plug
 *                bit (its last good word is kept), a gauge register that refuses degrades
 *                its field (its last good value is kept, and the minute line says how stale
 *                it is). The percentage is the gauge's own raw word -- ColorOS smooths and
 *                calibrates it before it shows its own, so the two may differ a little; the
 *                acceptance is against Android's raw value
 *                (/sys/class/power_supply/battery/capacity), not against ColorOS'.
 *
 * The bring-up is made in steps, each said in the log before it is made. Boot-arg
 * fuelgauge_steps=N stops after the first N (mode 2 only):
 *   1  map the PMIC arbiter and read its version
 *   2  look through its table for the channels of the four charger peripherals
 *   3  ask each peripheral what it is (registers 0x04/0x05). No table of the SMB5 types and
 *      subtypes is authoritative in the GPL tree (smb5-lib.c checks only an SDAM's), so what
 *      they say is recorded in the log, not judged: the peripheral numbers themselves come
 *      from the tree's layout of the PM8350B, and this step's lines are the first archive of
 *      what each block calls itself on this phone.
 *   4  map the TLMM, take the I2C bus if it is at rest, and ask the gauge for its four main
 *      registers (state of charge, voltage, current, temperature); every value must pass its
 *      sanity window before it is believed at all (a pin that is not what the tree says it
 *      is must not become a battery at 0 percent, as a key must not become a volume key
 *      held down).
 *   5  feed the pipeline, every fuelgauge_poll_us= microseconds (5 s), and say a line a
 *      minute (the default, and what fuelgauge_steps stops in)
 *
 * Boot arguments: fuelgauge= (1 static, 2 the buses), fuelgauge_steps=, fuelgauge_poll_us=,
 * fuelgauge_static_soc=, and the arbiter's three windows fuelgauge_core=, fuelgauge_cnfg=,
 * fuelgauge_obs= (hexadecimal, as buttons_core= and its brothers take them) -- the defaults
 * are this phone's own (the tree's qcom,spmi@c42d000, as the buttons driver found and used
 * them: core 0xc400000, cnfg 0xc42d000, observer 0xc440000).
 */
#include <kern/clock.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern kern_return_t thread_terminate(thread_t thread);

/*
 * Every line goes to the loader's log directly as well: without -v the kernel's own messages
 * reach that log only at the end of a run (with the kernel's message buffer), and "xl log"
 * during a run is to show a reading when it happens.
 */
extern void loader_log_putc(char c);

static int say(const char *format, ...) __printflike(1, 2);

static int
say(const char *format, ...)
{
	char line[400];
	va_list list;

	va_start(list, format);
	vsnprintf(line, sizeof(line), format, list);
	va_end(list);
	for (const char *c = line; *c != 0; c++) {
		loader_log_putc(*c);
	}
	return printf("%s", line);
}
#define printf say

static inline uint32_t
rd(vm_offset_t address)
{
	return *(volatile uint32_t *)address;
}

static inline void
wr(vm_offset_t address, uint32_t value)
{
	*(volatile uint32_t *)address = value;
}

static void
spin_us(uint32_t us)
{
	uint64_t until;

	nanoseconds_to_absolutetime((uint64_t)us * NSEC_PER_USEC, &until);
	until += mach_absolute_time();
	while (mach_absolute_time() < until) {
	}
}

/* ---- the PMIC arbiter (as drivers/input/hakios.buttons.c has it, narrowed to what this driver reads) ---- */

#define ARB_CORE_PHYS           0x0c400000UL    /* this phone's tree: qcom,spmi@c400000 ("core": version, tables) */
#define ARB_CORE_SIZE           0x3000UL        /* version 7 keeps its APID->PPID table at 0x2000 */
#define ARB_CNFG_PHYS           0x0c42d000UL    /* "cnfg": which system owns each channel */
#define ARB_CNFG_SIZE           0x1000UL
#define ARB_OBSERVER_PHYS       0x0c440000UL    /* "obsrvr": 0x8000 per system, 0x20 per channel in it, version 7 */
#define ARB_OBSERVER_SIZE       0x10000UL
#define ARB_SYSTEM              0               /* who we are to the arbiter: the tree's "qcom,ee" */

#define ARB_VERSION             0x000
#define ARB_VERSION_5           0x50000000u
#define ARB_VERSION_7           0x70000000u
#define ARB_VERSION_8           0x80000000u
#define ARB_FEATURES            0x004           /* [10:0] the number of channels */
#define ARB_CHANNEL(n)          (arb_apid_map + 4 * (n))        /* [19:8] slave and peripheral, [24] interrupts */
#define ARB_CHANNEL_INTERRUPTS  (1u << 24)
#define ARB_OWNER(n)            (arb_owner_base + 4 * (n))      /* [2:0] the system that may write through channel n */
#define ARB_MAX_CHANNELS        1024            /* version 7 answers 768 on this phone (Boot #14) */

/* version 7's tables (Linux drivers/spmi/spmi-pmic-arb.c's v7 ops), which this phone's arbiter speaks;
 * a version 5 arbiter moves them back, as the buttons driver found on the reference phone */
static uint32_t arb_apid_map = 0x2000, arb_owner_base = 0;
static uint32_t arb_obs_system = 0x8000, arb_obs_stride = 0x20;

#define OBSERVER_COMMAND        0x00
#define OBSERVER_STATUS         0x08
#define OBSERVER_DATA0          0x18            /* the bytes read, the first in the lowest byte */
#define OBSERVER_DATA1          0x1c
#define STATUS_DONE             0x1
#define STATUS_FAILURE          0x2
#define STATUS_DENIED           0x4
#define STATUS_DROPPED          0x8
#define COMMAND_READ            (1u << 27)      /* "extended register read long"; [11:4] register, [2:0] bytes - 1 */
#define READ_TIMEOUT_US         2000            /* a read takes some tens of microseconds */

/* boot-arg fuelgauge_core=/fuelgauge_cnfg=/fuelgauge_obs= (hexadecimal) move the three windows */
static vm_offset_t arb_core, arb_cnfg, arb_observer;
static uint64_t arb_core_phys = ARB_CORE_PHYS, arb_cnfg_phys = ARB_CNFG_PHYS, arb_obs_phys = ARB_OBSERVER_PHYS;

/* one transfer at a time through the arbiter: hakios_spmi_lock() (sys/hakios.input.h) */

struct peripheral {
	const char *    name;
	uint16_t        id;             /* slave << 8 | peripheral: the arbiter table's [19:8] */
	uint16_t        channel;
	bool            found;
	bool            usable;         /* it has answered at least once */
};

/*
 * The PM8350B's charger blocks (SPMI slave 3): the peripheral numbers are the SMB5 register
 * bases divided by 0x100, the layout the vendor's smb5-reg.h names (CHGR_BASE 0x1000,
 * BATIF_BASE 0x1200, USBIN_BASE 0x1300, TYPEC_BASE 0x1500). Which of them this arbiter's
 * table shows, and what each calls itself, step 2 and step 3 find and record.
 */
static struct peripheral chgr  = { .name = "the PM8350B's charger block",     .id = 0x310 };
static struct peripheral batif = { .name = "the PM8350B's battery interface", .id = 0x312 };
static struct peripheral usbin = { .name = "the PM8350B's USB input block",   .id = 0x313 };
static struct peripheral typec = { .name = "the PM8350B's Type-C block",      .id = 0x315 };

/* How the reads have gone: said once a minute. */
static struct {
	uint64_t spmi_reads, spmi_failed, i2c_reads, i2c_failed;
} bus;

static const char *
spmi_read(const struct peripheral *p, uint8_t reg, uint8_t *bytes, uint32_t count)
{
	vm_offset_t channel = arb_observer + (uint32_t)arb_obs_system * ARB_SYSTEM +
	    (uint32_t)arb_obs_stride * p->channel;
	uint64_t start = mach_absolute_time(), now = start, interval;
	uint32_t status = 0, data[2];
	const char *problem = NULL;

	nanoseconds_to_absolutetime(READ_TIMEOUT_US * (uint64_t)NSEC_PER_USEC, &interval);
	hakios_spmi_lock();
	wr(channel + OBSERVER_COMMAND, COMMAND_READ | (uint32_t)reg << 4 | (count - 1));
	do {
		status = rd(channel + OBSERVER_STATUS);
		now = mach_absolute_time();
	} while (!(status & STATUS_DONE) && now - start < interval);
	data[0] = rd(channel + OBSERVER_DATA0);
	data[1] = count > 4 ? rd(channel + OBSERVER_DATA1) : 0;
	hakios_spmi_unlock();

	if (!(status & STATUS_DONE)) {
		problem = "no answer from the arbiter";
	} else if (status & STATUS_DENIED) {
		problem = "the arbiter refuses";
	} else if (status & STATUS_FAILURE) {
		problem = "the transfer failed (nobody at that address?)";
	} else if (status & STATUS_DROPPED) {
		problem = "the transfer was dropped";
	} else {
		for (uint32_t i = 0; i < count; i++) {
			bytes[i] = (uint8_t)(data[i / 4] >> (8 * (i % 4)));
		}
	}
	bus.spmi_reads++;
	if (problem != NULL) {
		bus.spmi_failed++;
	}
	return problem;
}

/*
 * Which channel is that peripheral's. Several can be: one per system that may write to it.
 * As Linux chooses: the first, unless a later one is ours to write through.
 */
static void
find_channel(struct peripheral *p, uint32_t channels)
{
	for (uint32_t n = 0; n < channels; n++) {
		uint32_t map = rd(arb_core + ARB_CHANNEL(n)), owner;

		if (map == 0 || ((map >> 8) & 0xfff) != p->id) {
			continue;
		}
		owner = rd(arb_cnfg + ARB_OWNER(n)) & 7;
		printf("fuelgauge: channel %u is %s (%#x); written by system %u%s\n", n, p->name, map, owner,
		    (map & ARB_CHANNEL_INTERRUPTS) ? ", which also gets its interrupts" : "");
		if (!p->found || owner == ARB_SYSTEM) {
			p->found = true;
			p->channel = (uint16_t)n;
		}
	}
	if (!p->found) {
		printf("fuelgauge: no channel of the arbiter is %s (slave %u, peripheral %#x)\n", p->name,
		    p->id >> 8, p->id & 0xff);
	}
}

/* ---- the charger's registers [VENDOR drivers/power/supply/qcom/smb5-reg.h] ------------------------- */

#define REG_TYPE                0x04    /* PERPH_TYPE_OFFSET */
#define REG_SUBTYPE             0x05    /* PERPH_SUBTYPE_OFFSET */

#define USBIN_INT_RT_STS        0x10    /* INT_RT_STS_OFFSET, in the USBIN block */
#define USBIN_PLUGIN_BIT        (1u << 4)       /* USBIN_PLUGIN_RT_STS_BIT: a USB cable is in */

#define TYPE_C_MISC_STATUS      0x0b    /* TYPE_C_MISC_STATUS_REG */
#define TYPE_C_CC_ATTACHED_BIT  (1u << 0)       /* CC_ATTACHED_BIT: a Type-C connection is made */

#define CHGR_STATUS_1           0x06    /* BATTERY_CHARGER_STATUS_1_REG */
#define CHGR_STATUS_MASK        7u      /* BATTERY_CHARGER_STATUS_MASK, its low three bits */

/*
 * The charger's own state machine, as the vendor's smb5-reg.h numbers the statuses of
 * BATTERY_CHARGER_STATUS_1 (smb5-lib.c's get_prop_batt_status turns them into Linux's
 * POWER_SUPPLY_STATUS_*, the same numbers the battery pipeline takes in its `status`).
 */
enum charger_state {
	INHIBIT = 0, TRICKLE, PRE_CHARGE, FULLON, TAPER, TERMINATE, PAUSE, DISABLED
};

#define POWER_SUPPLY_STATUS_CHARGING     1
#define POWER_SUPPLY_STATUS_DISCHARGING  2
#define POWER_SUPPLY_STATUS_NOT_CHARGING 3
#define POWER_SUPPLY_STATUS_FULL         4

static bool charge_word_said;           /* the current-vs-state-machine word has been said once */

/*
 * The state of the battery, as the vendor's smblib_get_prop_batt_status puts it together,
 * with a direct-current input there is none of: nothing on the USB port reads terminated or
 * inhibited as full and everything else as discharging; something on the port reads trickle,
 * pre, full-on and taper as charging, terminated and inhibited as full, paused and disabled
 * as not charging. One refinement of this driver's own, from the repair list's risk table
 * (F17 section 4.5): the charger can say "charging" for a state machine that the firmware of
 * an absent DSP has left somewhere -- so a charging status is believed only while the
 * gauge's current says the battery is really taking charge (no more than 50 mA out of it;
 * its sign is positive into the battery). Against that word the status says "not charging",
 * once remarked in the log.
 */
static int
power_status(bool external, uint32_t state, int ma)
{
	if (!external) {
		return (state == TERMINATE || state == INHIBIT) ? POWER_SUPPLY_STATUS_FULL :
		    POWER_SUPPLY_STATUS_DISCHARGING;
	}
	switch (state) {
	case TRICKLE:
	case PRE_CHARGE:
	case FULLON:
	case TAPER:
		if (ma <= -50 && !charge_word_said) {
			charge_word_said = true;
			printf("fuelgauge: the charger says state %u but the gauge's current is %d mA: "
			    "\"not charging\" while the two disagree\n", state, ma);
		}
		return ma <= -50 ? POWER_SUPPLY_STATUS_NOT_CHARGING : POWER_SUPPLY_STATUS_CHARGING;
	case TERMINATE:
	case INHIBIT:
		return POWER_SUPPLY_STATUS_FULL;
	default:                        /* PAUSE, DISABLED */
		return POWER_SUPPLY_STATUS_NOT_CHARGING;
	}
}

/*
 * Linux's POWER_SUPPLY_USB_TYPE_* for "a Type-C port" (the vendor tree's
 * include/linux/power_supply.h: 5), which is what an attached CC says and no more: the
 * port's volts and amperes, and with them whether power delivery was negotiated, live behind
 * the charger's own ADC (smb5-lib.c get_prop_usb_voltage_now), whose dance of channel
 * registers this driver does not do; the adapter's dictionary goes out with zeros there.
 */
#define POWER_SUPPLY_USB_TYPE_C 5

/* ---- the I2C by hand, to the gauge (as drivers/haptic/hakios.haptic.c has it) ---------------------- */

#define TLMM_PHYS               0x0f100000UL    /* the same pin controller the reference phone's drivers map */
#define TLMM_SIZE               0x100000UL
#define GPIO_CFG(n)             (tlmm + 0x1000UL * (n))         /* [1:0] pull, [5:2] function, [8:6] drive, [9] output */
#define GPIO_IO(n)              (tlmm + 0x1000UL * (n) + 4)     /* bit 0 in, bit 1 out */
#define CFG_PULL_UP             3
#define CFG_OUTPUT              (1u << 9)

#define PIN_SDA                 26      /* the tree's qupv3_se0_i2c: the engine's first pin is the data line... */
#define PIN_SCL                 27      /* ...and its second the clock (function qup0, with pull-ups) */

#define GAUGE_ADDRESS           0x55    /* the tree's bq27541-battery@55 */

static vm_offset_t tlmm;

static void
half_bit(void)
{
	spin_us(5);                     /* the tree's qcom,clk-freq-out=0x186a0 asks for 100 kHz at most */
}

static void
line(unsigned pin, bool high)
{
	wr(GPIO_IO(pin), 0);
	wr(GPIO_CFG(pin), CFG_PULL_UP | (high ? 0 : CFG_OUTPUT));
}

static bool
level_of(unsigned pin)
{
	return rd(GPIO_IO(pin)) & 1;
}

static void
i2c_start(void)
{
	line(PIN_SDA, true);
	line(PIN_SCL, true);
	half_bit();
	line(PIN_SDA, false);
	half_bit();
	line(PIN_SCL, false);
	half_bit();
}

static void
i2c_stop(void)
{
	line(PIN_SDA, false);
	half_bit();
	line(PIN_SCL, true);
	half_bit();
	line(PIN_SDA, true);
	half_bit();
}

static bool
i2c_bit(bool out)
{
	bool in;

	line(PIN_SDA, out);
	half_bit();
	line(PIN_SCL, true);
	for (unsigned stretched = 0; !level_of(PIN_SCL) && stretched < 100; stretched++) {
		half_bit();
	}
	half_bit();
	in = level_of(PIN_SDA);
	line(PIN_SCL, false);
	return in;
}

static bool
i2c_write(uint8_t byte)
{
	for (int bit = 7; bit >= 0; bit--) {
		i2c_bit((byte >> bit) & 1);
	}
	return !i2c_bit(true);
}

static uint8_t
i2c_read(bool more)
{
	uint8_t byte = 0;

	for (int bit = 7; bit >= 0; bit--) {
		byte = (uint8_t)(byte << 1 | i2c_bit(true));
	}
	i2c_bit(!more);
	return byte;
}

static uint32_t taken_cfg[2], taken_io[2];

static bool
bus_take(void)
{
	taken_cfg[0] = rd(GPIO_CFG(PIN_SDA));
	taken_cfg[1] = rd(GPIO_CFG(PIN_SCL));
	taken_io[0] = rd(GPIO_IO(PIN_SDA));
	taken_io[1] = rd(GPIO_IO(PIN_SCL));
	line(PIN_SDA, true);
	line(PIN_SCL, true);
	half_bit();
	if (!level_of(PIN_SDA) || !level_of(PIN_SCL)) {
		wr(GPIO_IO(PIN_SDA), taken_io[0] & 2);
		wr(GPIO_IO(PIN_SCL), taken_io[1] & 2);
		wr(GPIO_CFG(PIN_SDA), taken_cfg[0]);
		wr(GPIO_CFG(PIN_SCL), taken_cfg[1]);
		printf("fuelgauge: the I2C bus is not at rest (gpio%u reads %u, gpio%u reads %u): not touched\n",
		    PIN_SDA, level_of(PIN_SDA), PIN_SCL, level_of(PIN_SCL));
		return false;
	}
	return true;
}

static void
bus_give_back(void)
{
	wr(GPIO_IO(PIN_SDA), taken_io[0] & 2);
	wr(GPIO_IO(PIN_SCL), taken_io[1] & 2);
	wr(GPIO_CFG(PIN_SDA), taken_cfg[0]);
	wr(GPIO_CFG(PIN_SCL), taken_cfg[1]);
}

/*
 * The gauge's registers, as the vendor's bq27xxx_battery.c numbers them for the bq27541
 * (bq27541_regs, drivers/power/supply/bq27xxx_battery.c:385-404). TEMP is tenths of a kelvin
 * (that driver's own conversion takes 2731 from the word for tenths of a degree Celsius);
 * VOLT is millivolts of the battery as the gauge sees it -- the tree says the battery is two
 * cells in series (qcom,vbatt_num=<2>), so whether this one word is the pair's or a single
 * cell's voltage is for the first comparison against Android to say (F17 section 6.4);
 * AI is signed milliamperes, positive into the battery; RC, FCC and DCAP are
 * milliampere-hours; SOC is a percent; CYCT is a count.
 */
#define GAUGE_TEMP              0x06
#define GAUGE_VOLT              0x08
#define GAUGE_RC                0x10
#define GAUGE_FCC               0x12
#define GAUGE_AI                0x14
#define GAUGE_CYCT              0x2a
#define GAUGE_SOC               0x2c
#define GAUGE_DCAP              0x3c

/*
 * Read one word of the gauge: the command register's address written, then a repeated start
 * and two bytes read, low first -- SMBus read word, as the vendor driver's
 * i2c_smbus_read_word_data has it.
 */
static bool
gauge_read_word(uint8_t reg, uint16_t *word)
{
	bool answered;

	bus.i2c_reads++;
	if (!bus_take()) {
		bus.i2c_failed++;
		return false;
	}
	i2c_start();
	answered = i2c_write(GAUGE_ADDRESS << 1) && i2c_write(reg);
	if (answered) {
		i2c_start();
		answered = i2c_write(GAUGE_ADDRESS << 1 | 1);
	}
	if (answered) {
		uint8_t low = i2c_read(true), high = i2c_read(false);

		*word = (uint16_t)(low | high << 8);
	}
	i2c_stop();
	bus_give_back();
	if (!answered) {
		bus.i2c_failed++;
	}
	return answered;
}

/*
 * The sanity windows: a value outside one is not believed (the pin may not be what the tree
 * says it is, or the chip may answer nonsense out of a state we do not know). As wide as the
 * repair list dares: any state of charge; 2.5 V to 9.5 V, so that a pair of cells in series
 * (up to about 8.9 V) and a single cell of it (up to about 4.5 V) both pass, whichever way
 * the voltage's question lands; up to 10 A of current, for a charger that can give 5 A or
 * more; -60 to 90 degrees Celsius, in hundredths.
 */
static bool
soc_sane(unsigned pct)                  { return pct <= 100; }
static bool
volt_sane(int mv)                       { return mv >= 2500 && mv <= 9500; }
static bool
current_sane(int ma)                    { return ma >= -10000 && ma <= 10000; }
static bool
temp_sane(int hundredths_c)            { return hundredths_c > -6000 && hundredths_c < 9000; }

/* ---- the state this driver keeps and feeds --------------------------------------------------------- */

/*
 * The last good reading of every gauge field (what a failed read leaves in place) and the
 * poll it was read at: the minute line marks a field that has been stale for over a minute.
 * Until the state of charge has passed its window once, nothing goes to the pipeline at all.
 */
static struct {
	bool soc_ok, volt_ok, current_ok, temp_ok, capacity_ok;
	unsigned soc;                   /* percent */
	int mv, ma, hundredths_c;      /* millivolts, milliamperes, hundredths of a degree Celsius */
	unsigned rc_mah, fcc_mah, dcap_mah, cycles;
	uint64_t soc_at, volt_at, current_at, temp_at;
} gauge;

static bool external, typec_attached, external_ok, charger_ok, typec_ok;
static uint32_t charger_state = DISABLED;

static uint32_t poll_us = 5000000, static_soc = 100, steps = 5, running_mode;
static uint64_t polls;

/* the pipeline's "not known" for the temperature (drivers/power/hakios.battery.c starts its
 * own at -273 C), rounded so that hakios_battery_report's rounding says -273 again */
#define TEMP_NOT_KNOWN  (-27350)

static void
gauge_look(void)
{
	uint16_t word;
	static const struct {
		uint8_t reg;
		unsigned *into;
		const char *name;
	} rest[] = {
		{ GAUGE_RC,   &gauge.rc_mah,  "remaining capacity" },
		{ GAUGE_FCC,  &gauge.fcc_mah, "full-charge capacity" },
		{ GAUGE_DCAP, &gauge.dcap_mah, "design capacity" },
		{ GAUGE_CYCT, &gauge.cycles,  "cycle count" },
	};

	if (gauge_read_word(GAUGE_SOC, &word) && soc_sane(word)) {
		gauge.soc = word;
		gauge.soc_ok = true;
		gauge.soc_at = polls;
	} else if (polls % 12 == 0) {
		printf("fuelgauge: the state of charge is not answering sensibly%s\n",
		    gauge.soc_ok ? " (the last one is kept)" : "");
	}
	if (gauge_read_word(GAUGE_VOLT, &word) && volt_sane((int)word)) {
		gauge.mv = word;
		gauge.volt_ok = true;
		gauge.volt_at = polls;
	}
	if (gauge_read_word(GAUGE_AI, &word)) {
		int ma = (int)(int16_t)word;    /* signed, positive into the battery */

		if (current_sane(ma)) {
			gauge.ma = ma;
			gauge.current_ok = true;
			gauge.current_at = polls;
		}
	}
	if (gauge_read_word(GAUGE_TEMP, &word)) {
		int hundredths = ((int)word - 2731) * 10;      /* tenths of a kelvin in, hundredths of a degree Celsius out */

		if (temp_sane(hundredths)) {
			gauge.hundredths_c = hundredths;
			gauge.temp_ok = true;
			gauge.temp_at = polls;
		}
	}
	/* the capacities and the cycle count once a minute: they change the slowest */
	if (polls % 12 == 0 || !gauge.capacity_ok) {
		for (unsigned i = 0; i < sizeof(rest) / sizeof(rest[0]); i++) {
			if (gauge_read_word(rest[i].reg, &word)) {
				*rest[i].into = word;
				if (rest[i].reg != GAUGE_CYCT) {
					gauge.capacity_ok = true;
				}
			}
		}
	}
}

static void
charger_look(void)
{
	uint8_t byte;

	if (usbin.found) {
		if (spmi_read(&usbin, USBIN_INT_RT_STS, &byte, 1) == NULL) {
			external = (byte & USBIN_PLUGIN_BIT) != 0;
			external_ok = true;
			usbin.usable = true;
		}
	}
	if (typec.found) {
		if (spmi_read(&typec, TYPE_C_MISC_STATUS, &byte, 1) == NULL) {
			typec_attached = (byte & TYPE_C_CC_ATTACHED_BIT) != 0;
			typec_ok = true;
			typec.usable = true;
		}
	}
	if (chgr.found) {
		if (spmi_read(&chgr, CHGR_STATUS_1, &byte, 1) == NULL) {
			charger_state = byte & CHGR_STATUS_MASK;
			charger_ok = true;
			chgr.usable = true;
		}
	}
}

/* What goes to the pipeline, put together out of what the buses said last. */
static void
feed(void)
{
	struct hakios_battery_state b;

	memset(&b, 0, sizeof(b));
	b.size = sizeof(b);
	b.present = 1;
	b.percent_hundredths = (int)gauge.soc * 100;
	b.voltage_uv = gauge.mv * 1000;
	b.current_ua = gauge.ma * 1000;
	b.temperature_hundredths = gauge.temp_ok ? gauge.hundredths_c : TEMP_NOT_KNOWN;
	b.external = external ? 1 : 0;
	b.status = power_status(external, charger_state, gauge.current_ok ? gauge.ma : 0);
	if (gauge.capacity_ok) {
		b.charge_uah = (int)gauge.rc_mah * 1000;
		b.full_uah = (int)gauge.fcc_mah * 1000;
		b.design_uah = (int)gauge.dcap_mah * 1000;
	}
	b.cycles = (int)gauge.cycles;
	b.usb_type = typec_attached ? POWER_SUPPLY_USB_TYPE_C : 0;
	hakios_battery_report(&b);
}

/* What the static mode feeds: the pipeline's minimum, marked "static" in every line of the log. */
static void
feed_static(void)
{
	struct hakios_battery_state b;

	memset(&b, 0, sizeof(b));
	b.size = sizeof(b);
	b.present = 1;
	b.percent_hundredths = (int)static_soc * 100;
	b.temperature_hundredths = TEMP_NOT_KNOWN;
	b.status = POWER_SUPPLY_STATUS_DISCHARGING;
	hakios_battery_report(&b);
}

static void
say_summary(void)
{
	if (running_mode == 1) {
		printf("fuelgauge: static %u%%, not on a charger (%llu feeds of the pipeline)\n", static_soc, polls);
		return;
	}
	printf("fuelgauge: %s%u%% %d mV %d mA %d.%02d C ext=%d cc=%d chg=%u (%llu polls; %llu SPMI reads, "
	    "%llu failed; %llu gauge reads, %llu failed)%s%s%s%s%s\n",
	    gauge.soc_ok ? "" : "no ", gauge.soc, gauge.mv, gauge.ma, gauge.hundredths_c / 100,
	    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 100,
	    external ? 1 : 0, typec_attached ? 1 : 0, charger_state, polls, bus.spmi_reads,
	    bus.spmi_failed, bus.i2c_reads, bus.i2c_failed,
	    gauge.soc_ok && polls - gauge.soc_at > 12 ? " (soc stale)" : "",
	    gauge.volt_ok && polls - gauge.volt_at > 12 ? " (volt stale)" : "",
	    gauge.current_ok && polls - gauge.current_at > 12 ? " (current stale)" : "",
	    gauge.temp_ok && polls - gauge.temp_at > 12 ? " (temp stale)" : "",
	    external_ok && charger_ok && typec_ok ? "" : " (a charger register unread)");
}

/* ---- the steps ------------------------------------------------------------------------------------- */

static bool
arbiter_map(void)
{
	uint32_t version, channels;

	printf("fuelgauge: step 1: map the PMIC arbiter (%#llx, %#llx, %#llx) and read its version\n",
	    arb_core_phys, arb_cnfg_phys, arb_obs_phys);
	arb_core = ml_io_map((vm_offset_t)arb_core_phys, ARB_CORE_SIZE);
	arb_cnfg = ml_io_map((vm_offset_t)arb_cnfg_phys, ARB_CNFG_SIZE);
	arb_observer = ml_io_map((vm_offset_t)arb_obs_phys, ARB_OBSERVER_SIZE);
	version = rd(arb_core + ARB_VERSION);
	channels = rd(arb_core + ARB_FEATURES) & 0x7ff;
	printf("fuelgauge: the PMIC arbiter is version %#x, %u channels\n", version, channels);
	if (version < ARB_VERSION_5 || version >= ARB_VERSION_8) {
		printf("fuelgauge: this driver knows versions 5 and 7 of the arbiter only: no charger readings "
		    "(the gauge does not need the arbiter, and is tried regardless)\n");
		return false;
	}
	if (version < ARB_VERSION_7) {
		/* (version 7's tables are the defaults; version 5's, the reference phone's, move back) */
		arb_apid_map = 0x900;
		arb_owner_base = 0x700;
		arb_obs_system = 0x10000;
		arb_obs_stride = 0x80;
		printf("fuelgauge: version 5: APID->PPID table at core+0x900, owner table at cnfg+0x700, "
		    "observer channels at obsrvr+0x10000*system+0x80*apid\n");
	}
	if (channels == 0 || channels > ARB_MAX_CHANNELS) {
		channels = ARB_MAX_CHANNELS;
	}
	return true;
}

static bool
find_channels(void)
{
	struct peripheral *all[] = { &chgr, &batif, &usbin, &typec };
	bool any = false;

	printf("fuelgauge: step 2: look through the arbiter's table for the channels of the charger's four blocks\n");
	for (unsigned i = 0; i < sizeof(all) / sizeof(all[0]); i++) {
		find_channel(all[i], rd(arb_core + ARB_FEATURES) & 0x7ff);
		any |= all[i]->found;
	}
	if (!any) {
		printf("fuelgauge: none of the charger's blocks is in the arbiter's table: no charger readings "
		    "(the gauge does not need the arbiter, and is tried regardless)\n");
	}
	return any;
}

static void
identify_all(void)
{
	struct peripheral *all[] = { &chgr, &batif, &usbin, &typec };
	uint8_t is[2];

	printf("fuelgauge: step 3: ask each block what it is (registers 0x04 and 0x05). No table of the SMB5 "
	    "types and subtypes is authoritative in the GPL tree, so what they say is recorded, not judged\n");
	for (unsigned i = 0; i < sizeof(all) / sizeof(all[0]); i++) {
		const char *problem;

		if (!all[i]->found) {
			continue;
		}
		problem = spmi_read(all[i], REG_TYPE, is, 2);
		if (problem != NULL) {
			printf("fuelgauge: %s: %s\n", all[i]->name, problem);
			continue;
		}
		all[i]->usable = true;
		printf("fuelgauge: peripheral %#x (%s) says type %#x, subtype %#x\n", all[i]->id, all[i]->name,
		    is[0], is[1]);
	}
}

/* Step 4: the gauge, and its first four readings. */
static bool
gauge_verify(void)
{
	printf("fuelgauge: step 4: map the pin controller and ask the gauge at 0x55 (GPIO %u data, %u clock) "
	    "for its four main registers\n", PIN_SDA, PIN_SCL);
	tlmm = ml_io_map(TLMM_PHYS, TLMM_SIZE);
	if (tlmm == 0) {
		printf("fuelgauge: could not map the pin controller: no gauge\n");
		return false;
	}
	polls = 1;
	gauge_look();
	if (!gauge.soc_ok) {
		printf("fuelgauge: the gauge does not answer, or answers nonsense: nothing is fed to the battery "
		    "(the status bar keeps whatever it shows without a battery)\n");
		return false;
	}
	printf("fuelgauge: the gauge answers: SOC %u, %d mV, %d mA, %d.%02d C (%d hundredths)\n", gauge.soc,
	    gauge.mv, gauge.ma, gauge.hundredths_c / 100,
	    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 100,
	    gauge.hundredths_c);
	return true;
}

/* ---- the thread ------------------------------------------------------------------------------------ */

static void
fuelgauge_thread(void *parameter, __unused wait_result_t result)
{
	bool feeding = false;
	bool arbiter_ok;

	if (running_mode == 1) {
		printf("fuelgauge: step 5: feeding a static battery of %u percent, every %u.%u s: an ios-sweet "
		    "\"SweetBattery\", no bus touched\n", static_soc, poll_us / 1000000, poll_us / 100000 % 10);
		goto watch;
	}
	arbiter_ok = arbiter_map();
	if (steps < 2) {
		goto out;
	}
	if (arbiter_ok) {
		find_channels();
	}
	if (steps < 3) {
		goto out;
	}
	if (arbiter_ok) {
		identify_all();
	}
	if (steps < 4) {
		goto out;
	}
	if (!gauge_verify()) {
		goto out;
	}
	printf("fuelgauge: step 5: watching the gauge and the charger, every %u.%u s\n",
	    poll_us / 1000000, poll_us / 100000 % 10);
watch:
	for (;; polls++) {
		if (running_mode == 1) {
			feed_static();
		} else {
			charger_look();
			gauge_look();
			if (gauge.soc_ok) {
				if (!feeding) {
					feeding = true;
					printf("fuelgauge: the battery's readings are believed from here on\n");
				}
				feed();
			} else if (polls % 12 == 0) {
				printf("fuelgauge: nothing fed yet: the gauge has not given a state of charge that "
				    "passes its window\n");
			}
		}
		if (polls % 12 == 0) {
			say_summary();
		}
		delay_for_interval(poll_us / 1000, NSEC_PER_MSEC);
	}
out:
	printf("fuelgauge: stopping here (fuelgauge_steps=%u)\n", steps);
	thread_terminate(current_thread());
}

/* ---- the start ------------------------------------------------------------------------------------- */

void
hakios_fuelgauge_init(void)
{
	uint32_t mode = 0;
	thread_t thread;

	if (!PE_parse_boot_argn("fuelgauge", &mode, sizeof(mode)) || (mode != 1 && mode != 2)) {
		return;
	}
	PE_parse_boot_argn("fuelgauge_poll_us", &poll_us, sizeof(poll_us));
	if (poll_us < 100000 || poll_us > 60000000) {
		poll_us = 5000000;              /* a value nobody could have meant: the default again */
	}
	PE_parse_boot_argn("fuelgauge_static_soc", &static_soc, sizeof(static_soc));
	if (static_soc > 100) {
		static_soc = 100;
	}
	PE_parse_boot_argn("fuelgauge_steps", &steps, sizeof(steps));
	PE_parse_boot_argn("fuelgauge_core", &arb_core_phys, sizeof(arb_core_phys));
	PE_parse_boot_argn("fuelgauge_cnfg", &arb_cnfg_phys, sizeof(arb_cnfg_phys));
	PE_parse_boot_argn("fuelgauge_obs", &arb_obs_phys, sizeof(arb_obs_phys));
	running_mode = mode;
	printf("fuelgauge: the fuel gauge of the battery, mode %u (%s)\n", mode,
	    mode == 1 ? "static: a battery service without the buses, as ios-sweet's SweetBattery" :
	    "the readings of the gauge and of the charger");
	if (mode == 2 && steps == 0) {
		return;
	}
	/* (mode 2's steps run on its thread as well, so that the I2C by hand is never spun on the
	 * boot path: a transaction takes its milliseconds of pin spinning) */
	if (kernel_thread_start(fuelgauge_thread, NULL, &thread) != KERN_SUCCESS) {
		printf("fuelgauge: could not start its thread\n");
	}
	thread_deallocate(thread);
}

/*
 * What interrupts would take, instead of looking twelve times a minute: the same as the
 * buttons driver's list at the end of its file -- the arbiter's one line for the PMICs'
 * peripherals (this kernel drives no hardware interrupt but the timer's yet), per channel an
 * enable and a status and a clear, and in each block the interrupt enables that would have
 * to be written into the PMIC. A battery changes slowly; looking costs a handful of reads of
 * some tens of microseconds each every five seconds, which is nothing.
 */
