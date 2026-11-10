/*
 * The touch screen of the OnePlus Ace 2 (PHK110): a Synaptics S3910 speaking TouchComm over
 * SPI ("TCM"), as a source of touches for /dev/hakios-touch (sys/hakios.input.h). Only with
 * boot-arg touchscreen=1: every address below belongs to this phone.
 *
 * There is no clock, pin, regulator, SPI or touch framework in this kernel, so the driver does
 * all of it itself, in the order the phone's own Linux drivers do (the OnePlus GPL tree,
 * OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475, branch oneplus/sm8475_v_15.0.0_ace_2:
 *   vendor/oplus/kernel/touchpanel/synaptics_hbp/  -- the TouchCom driver that binds the node
 *       synaptics_tcm_hbp@0 (compatible "synaptics,tcm-spi-hbp", status okay in the live FDT),
 *   vendor/oplus/kernel/touchpanel/oplus_touchscreen_v2/Synaptics/Syna_tcm_S3910/ -- the Oplus
 *       variant of the same protocol; both were read for this file):
 *   power    the analog supply (L3C of the PM8350C, "ldoc3" in RPMh) and the I/O supply (L4H of
 *            the pm8450-family chip, "ldoh4"), written through RPMh like the reference phone's
 *            driver writes its supply; the analog rail also has a load switch, TLMM GPIO 97
 *   clocks   the serial engine's clocks, by vote in the global clock controller
 *   pins     the four SPI pins (GPIO 16-19, function "qup4"), reset (GPIO 20, active low) and the
 *            interrupt line (GPIO 21, active low: the level the firmware raises a report at)
 *   SPI      the serial engine ("GENI") in FIFO mode, polled
 *   chip     TouchComm: the firmware has booted itself when the phone arrives (the flash holds it;
 *            this driver never flashes the chip), so bring-up is only reading who it is and then
 *            asking for touch reports
 *
 * The protocol. TouchComm has two wire formats and the firmware speaks one of them; both are
 * implemented here and the version comes out of the first exchange:
 *   v1  a message is [0xA5 marker, code, length LSB, length MSB, payload..., 0x5A padding], no
 *       checksum; a command is written as [command, length LSB, length MSB, payload...]; this is
 *       the format the Oplus S3910 driver speaks
 *   v2  a message is [code, length LSB, length MSB, byte3] with byte3's top six bits a CRC-6 of
 *       the header, and a payload of more than nothing ends in a CRC-16/CCITT of the whole packet
 *       (its remainder must be 0); a command packet carries the same header; the host asks for a
 *       report with CMD_TCM2_GET_REPORT and lets a message continue with CMD_TCM2_ACK; this is the
 *       format the TouchCom v2 core of the HBP driver speaks
 * The identification packet (REPORT_IDENTIFY after a reset, or the answer to CMD_IDENTIFY) says
 * which format the firmware uses ("version" = 1 or 2) and, either way, who the chip is: part
 * number, build id and the largest packet it accepts -- the lines this driver prints first.
 *
 * No interrupt is used: a thread looks at the interrupt line 125 times a second (boot-arg
 * touch_poll_us=N: every N microseconds instead of 8000), and asks for the report waiting behind
 * it. The order of the registers: Linux drivers/spi/spi-geni-qcom.c, drivers/soc/qcom/{qcom-geni-se,
 * rpmh-rsc,cmd-db}.c, drivers/clk/qcom/gcc-sm8450.c, drivers/pinctrl/qcom/pinctrl-sm8450.c, and the
 * phone's own device tree (live FDT: spi@990000, synaptics_tcm_hbp@0, pinctrl@f000000, rsc@17a00000).
 */
#include <kern/clock.h>
#include <kern/locks.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern vm_offset_t ml_io_map_wcomb(vm_offset_t phys_addr, vm_size_t size);
extern kern_return_t thread_terminate(thread_t thread);

/* RPMh's sequencer (TCS 0 of the RSC): the audio DSP's and the modem's drivers write the same slots, so every request goes through this lock */
extern lck_mtx_t hakios_rsc_lock;

static vm_offset_t tlmm, gcc, se, rsc, cmd_db;

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
sleep_us(uint32_t us)
{
	delay_for_interval(us, NSEC_PER_USEC);
}

static void
sleep_ms(uint32_t ms)
{
	delay_for_interval(ms, NSEC_PER_MSEC);
}

/* ---- pins (TLMM) ------------------------------------------------------------------------------- */

#define TLMM_PHYS               0x0f100000UL
#define TLMM_SIZE               0x100000UL
#define GPIO_CFG(n)             (tlmm + 0x1000UL * (n))         /* [1:0] pull, [5:2] function, [8:6] drive, [9] output */
#define GPIO_IO(n)              (tlmm + 0x1000UL * (n) + 4)     /* bit 0 in, bit 1 out */
#define PULL_NONE               0
#define PULL_UP                 3

#define PIN_MISO                16
#define PIN_MOSI                17
#define PIN_CLK                 18
#define PIN_CS                  19
#define PIN_INT                 21      /* low = the chip has a report (the tree's 0x2008: level low) */
#define PIN_RESET               20      /* low = in reset */
#define PIN_VDD                 97      /* high = the analog supply's load switch on */
#define PIN_FUNCTION_SPI        1       /* "qup4" */

static void
gpio_configure(unsigned pin, unsigned function, unsigned pull, unsigned ma, bool output)
{
	wr(GPIO_CFG(pin), pull | function << 2 | (ma / 2 - 1) << 6 | (output ? 1u << 9 : 0));
}

static void
gpio_set(unsigned pin, bool high)
{
	wr(GPIO_IO(pin), high ? 2 : 0);
}

static bool
gpio_get(unsigned pin)
{
	return rd(GPIO_IO(pin)) & 1;
}

static void
gpio_output(unsigned pin, bool high, unsigned pull, unsigned ma)
{
	gpio_set(pin, high);            /* the level first, so that the pin never drives the wrong one */
	gpio_configure(pin, 0, pull, ma, true);
}

/* ---- the supplies (RPMh) ------------------------------------------------------------------------- */

#define CMD_DB_PHYS             0x80860000UL
#define CMD_DB_SIZE             0x20000UL
#define RSC_PHYS                0x17a20000UL    /* apps_rsc, the application processor's "DRV 2" (the tree's qcom,drv-id=2) */
#define RSC_SIZE                0x10000UL
#define TCS(reg)                (rsc + 0xd00 + (reg))           /* command slot set 0, an "active" one (qcom,tcs-offset=0xd00) */
#define TCS_IRQ_ENABLE          0x00
#define TCS_IRQ_STATUS          0x04
#define TCS_IRQ_CLEAR           0x08
#define TCS_WAIT_FOR_COMPLETION 0x10
#define TCS_CONTROL             0x14
#define TCS_CONTROL_ENABLE      (1u << 16)
#define TCS_CONTROL_TRIGGER     (1u << 24)
#define TCS_STATUS              0x18            /* 0 while busy */
#define TCS_CMD_ENABLE          0x1c
#define TCS_CMD_MSGID(n)        (0x30 + 20 * (n))
#define TCS_CMD_ADDR(n)         (0x34 + 20 * (n))
#define TCS_CMD_DATA(n)         (0x38 + 20 * (n))
#define MSGID_WRITE_4_BYTES     0x10008
#define MSGID_RESPONSE          0x100

#define VRM_VOLTAGE             0               /* a regulator's registers, from its address: millivolts */
#define VRM_ENABLE              4
#define VRM_MODE                8
#define VRM_MODE_LDO_HPM        7

struct cmd_db_slave {
	uint16_t id, header_offset, data_offset, count, version, reserved[3];
};
struct cmd_db_header {
	uint32_t version;
	uint8_t magic[4];
	struct cmd_db_slave slave[8];
	uint32_t checksum, reserved;
	uint8_t data[];
};
struct cmd_db_entry {
	char id[8];
	uint32_t priority[2];
	uint32_t address;
	uint16_t length, offset;
};

/* The RPMh address of a resource by its name in the command database the boot loader left; 0 = none. */
static uint32_t
rpmh_address(const char *name)
{
	const struct cmd_db_header *db = (const struct cmd_db_header *)cmd_db;
	char id[8] = { 0 };

	if (db->magic[0] != 0xdb || db->magic[1] != 0x30 || db->magic[2] != 0x03 || db->magic[3] != 0x0c) {
		printf("s3910: no command database (magic %02x %02x %02x %02x)\n", db->magic[0], db->magic[1], db->magic[2],
		    db->magic[3]);
		return 0;
	}
	strlcpy(id, name, sizeof(id));
	for (unsigned s = 0; s < 8; s++) {
		const struct cmd_db_slave *slave = &db->slave[s];
		const struct cmd_db_entry *entry = (const struct cmd_db_entry *)(db->data + slave->header_offset);

		if (slave->id == 0 || slave->header_offset >= CMD_DB_SIZE - 0x1000 || slave->count > 512) {
			continue;
		}
		for (unsigned i = 0; i < slave->count; i++) {
			if (memcmp(entry[i].id, id, sizeof(id)) == 0) {
				return entry[i].address;
			}
		}
	}
	return 0;
}

static bool
rpmh_wait(uint32_t reg, uint32_t mask, uint32_t value, const char *what)
{
	for (int i = 0; i < 2000; i++) {
		if ((rd(TCS(reg)) & mask) == value) {
			return true;
		}
		sleep_us(100);
	}
	printf("s3910: RPMh: timeout waiting for %s (register %#x = %#x)\n", what, reg, rd(TCS(reg)));
	return false;
}

/* Send up to three register writes to RPMh and wait until they are done. */
static bool
rpmh_write(const uint32_t *address, const uint32_t *data, unsigned count)
{
	uint32_t irq_enable;
	bool done;

	/* the other drivers that write this slot set take the same lock, so that two requests never mix their address and data words */
	lck_mtx_lock(&hakios_rsc_lock);
	irq_enable = rd(TCS(TCS_IRQ_ENABLE));
	/* the slot set must be idle, and switched off the way the hardware wants it: trigger, then enable */
	for (int i = 0; rd(TCS(TCS_STATUS)) == 0; i++) {
		if (i > 2000) {
			printf("s3910: RPMh: the command slots stay busy\n");
			lck_mtx_unlock(&hakios_rsc_lock);
			return false;
		}
		sleep_us(100);
	}
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_TRIGGER);
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_ENABLE);
	wr(TCS(TCS_IRQ_CLEAR), 1);
	for (unsigned i = 0; i < count; i++) {
		wr(TCS(TCS_CMD_MSGID(i)), MSGID_WRITE_4_BYTES | MSGID_RESPONSE);
		wr(TCS(TCS_CMD_ADDR(i)), address[i]);
		wr(TCS(TCS_CMD_DATA(i)), data[i]);
	}
	wr(TCS(TCS_WAIT_FOR_COMPLETION), (1u << count) - 1);
	wr(TCS(TCS_CMD_ENABLE), (1u << count) - 1);
	wr(TCS(TCS_IRQ_ENABLE), irq_enable | 1);        /* the status bit follows the enable; the interrupt itself stays masked */
	wr(TCS(TCS_CONTROL), TCS_CONTROL_ENABLE);
	wr(TCS(TCS_CONTROL), TCS_CONTROL_ENABLE | TCS_CONTROL_TRIGGER);

	done = rpmh_wait(TCS_IRQ_STATUS, 1, 1, "the request");   /* rpmh_wait applies TCS itself */
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_TRIGGER);
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_ENABLE);
	wr(TCS(TCS_CMD_ENABLE), 0);
	wr(TCS(TCS_WAIT_FOR_COMPLETION), 0);
	wr(TCS(TCS_IRQ_CLEAR), 1);
	wr(TCS(TCS_IRQ_ENABLE), irq_enable);
	lck_mtx_unlock(&hakios_rsc_lock);
	return done;
}

/* One rail: its address from the command database, then voltage, enable and mode written. */
static bool
rail_on(const char *name, uint32_t millivolts, const char *what)
{
	uint32_t base = rpmh_address(name);
	uint32_t address[3] = { base + VRM_VOLTAGE, base + VRM_ENABLE, base + VRM_MODE };
	uint32_t data[3] = { millivolts, 1, VRM_MODE_LDO_HPM };

	/* addresses of regulators ("VRM") have 4 in bits 19:16; anything else is not what we are looking for */
	if (base == 0 || (base >> 16 & 0xf) != 4) {
		printf("s3910: RPMh: no regulator \"%s\" for %s (address %#x); carrying on: the rail may already be on\n", name,
		    what, base);
		return false;
	}
	if (!rpmh_write(address, data, 3)) {
		return false;
	}
	printf("s3910: %s on (%s at %u mV)\n", what, name, millivolts);
	return true;
}

/* ---- clocks (GCC) -------------------------------------------------------------------------------- */

#define GCC_PHYS                0x00100000UL
#define GCC_SIZE                0x1f4200UL      /* the tree's own size; sm8450's vote register is at 0x62008 */
#define GCC_VOTE                (gcc + 0x62008)         /* the application processor's votes (sm8450) */
#define VOTE_QUP1_CORE_2X       (1u << 18)
#define VOTE_QUP1_CORE          (1u << 19)
#define VOTE_QUP1_M_AHB         (1u << 20)
#define VOTE_QUP1_S_AHB         (1u << 21)
#define VOTE_QUP1_SE4           (1u << 26)             /* serial engine 4 of the second group (wrap1_s4) */
#define GCC_QUP1_M_AHB_CBCR     (gcc + 0x28004)         /* bit 31: the clock is off */
#define GCC_QUP1_S_AHB_CBCR     (gcc + 0x28008)
#define GCC_QUP1_SE4_CBCR       (gcc + 0x284dc)
#define GCC_QUP1_SE4_CMD        (gcc + 0x284e4)         /* bit 0: take the new configuration */
#define GCC_QUP1_SE4_CFG        (gcc + 0x284e8)         /* [4:0] 2*divider-1, [10:8] source, [13:12] mode */
#define GCC_QUP1_SE4_DFSR       (gcc + 0x284f8)         /* bit 0: the engine chooses among preset rates itself */
#define GCC_QUP1_SE4_PERF_CFG(l) (gcc + 0x28500 + 4 * (l))
#define GCC_QUP1_SE4_PERF_M(l)  (gcc + 0x28540 + 4 * (l))
#define GCC_QUP1_SE4_PERF_N(l)  (gcc + 0x28580 + 4 * (l))
#define CLOCK_OFF               (1u << 31)
#define XO_HZ                   19200000

static uint32_t se_source_hz, se_clock_select;

static uint32_t
rcg_rate(uint32_t cfg, uint32_t m, uint32_t not_n_minus_m)
{
	static const uint32_t parent[8] = { XO_HZ, 600000000, 300000000, 0, 0, 0, 0, 0 };
	uint64_t hz = parent[cfg >> 8 & 7];
	uint32_t divider = cfg & 0x1f, mode = cfg >> 12 & 3;

	if (divider) {
		hz = hz * 2 / (divider + 1);
	}
	if (mode) {
		uint32_t n = (~not_n_minus_m & 0xffff) + (m & 0xffff);

		if (n) {
			hz = hz * (m & 0xffff) / n;
		}
	}
	return (uint32_t)hz;
}

static bool
clocks_on(void)
{
	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_CORE_2X | VOTE_QUP1_CORE | VOTE_QUP1_M_AHB | VOTE_QUP1_S_AHB);
	if (rd(GCC_QUP1_SE4_DFSR) & 1) {
		/* preset rates: the lowest that is at least 4 MHz */
		for (uint32_t level = 0; level < 8; level++) {
			uint32_t hz = rcg_rate(rd(GCC_QUP1_SE4_PERF_CFG(level)), rd(GCC_QUP1_SE4_PERF_M(level)),
			    rd(GCC_QUP1_SE4_PERF_N(level)));

			if (hz >= 4000000 && (se_source_hz == 0 || hz < se_source_hz)) {
				se_source_hz = hz;
				se_clock_select = level;
			}
		}
		if (se_source_hz == 0) {
			printf("s3910: no usable preset clock rate\n");
			return false;
		}
	} else {
		/* the crystal, undivided: nothing else has to be running */
		wr(GCC_QUP1_SE4_CFG, (rd(GCC_QUP1_SE4_CFG) & ~0x371fu) | 1);
		wr(GCC_QUP1_SE4_CMD, rd(GCC_QUP1_SE4_CMD) | 1);
		for (int i = 0; i < 500 && (rd(GCC_QUP1_SE4_CMD) & 1); i++) {
			sleep_us(10);
		}
		if (rd(GCC_QUP1_SE4_CMD) & 1) {
			printf("s3910: the serial engine's clock does not take its configuration (%#x)\n", rd(GCC_QUP1_SE4_CMD));
			return false;
		}
		se_source_hz = XO_HZ;
		se_clock_select = 0;
	}
	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_SE4);
	for (int i = 0; i < 1000; i++) {
		if (!((rd(GCC_QUP1_M_AHB_CBCR) | rd(GCC_QUP1_SE4_CBCR)) & CLOCK_OFF)) {
			/*
			 * Boot #16: this gcc is cape's -- the tree's m/s_ahb clock indices (134/135) are not
			 * the sm8450 table's (118/119) -- and the branch at 0x28008 read 0x80000002 (halted)
			 * through the vote while the engine's own branch un-halted fine. It is not believed:
			 * warn and let the engine's firmware revision say whether it is alive.
			 */
			if (rd(GCC_QUP1_S_AHB_CBCR) & CLOCK_OFF) {
				printf("s3910: the wrapper's s_ahb clock still reads halted (%#x); trying the engine anyway\n",
				    rd(GCC_QUP1_S_AHB_CBCR));
			}
			return true;
		}
		sleep_us(10);
	}
	printf("s3910: clocks stay off: %#x %#x %#x\n", rd(GCC_QUP1_M_AHB_CBCR), rd(GCC_QUP1_S_AHB_CBCR),
	    rd(GCC_QUP1_SE4_CBCR));
	return false;
}

/* ---- SPI through the serial engine (GENI) ---------------------------------------------------------- */

#define SE_PHYS                 0x00990000UL
#define SE_SIZE                 0x4000UL
#define GENI_FORCE_DEFAULT      (se + 0x020)
#define GENI_OUTPUT_CTRL        (se + 0x024)
#define GENI_CGC_CTRL           (se + 0x028)
#define GENI_STATUS             (se + 0x040)    /* bit 0: a command is running */
#define GENI_SER_M_CLK_CFG      (se + 0x048)    /* bit 0 enable, [15:4] divider */
#define GENI_IF_DISABLE_RO      (se + 0x064)    /* bit 0: no FIFO interface */
#define GENI_FW_REVISION_RO     (se + 0x068)    /* [15:8] protocol: 1 = SPI */
#define GENI_CLK_SEL            (se + 0x07c)
#define SPI_CPHA                (se + 0x224)
#define SPI_LOOPBACK            (se + 0x22c)
#define SPI_CPOL                (se + 0x230)
#define SPI_DEMUX_OUTPUT_INV    (se + 0x24c)
#define SPI_DEMUX_SEL           (se + 0x250)
#define GENI_BYTE_GRAN          (se + 0x254)
#define GENI_DMA_MODE_EN        (se + 0x258)
#define SPI_TRANS_CFG           (se + 0x25c)
#define GENI_TX_PACKING_CFG0    (se + 0x260)
#define GENI_TX_PACKING_CFG1    (se + 0x264)
#define SPI_WORD_LEN            (se + 0x268)
#define SPI_TX_TRANS_LEN        (se + 0x26c)
#define SPI_RX_TRANS_LEN        (se + 0x270)
#define SPI_DELAY_COUNTERS      (se + 0x278)
#define GENI_RX_PACKING_CFG0    (se + 0x284)
#define GENI_RX_PACKING_CFG1    (se + 0x288)
#define GENI_M_CMD0             (se + 0x600)    /* [31:27] operation */
#define GENI_M_CMD_CTRL         (se + 0x604)    /* bit 2 cancel, bit 1 abort */
#define GENI_M_IRQ_STATUS       (se + 0x610)
#define GENI_M_IRQ_EN           (se + 0x614)
#define GENI_M_IRQ_CLEAR        (se + 0x618)
#define GENI_S_IRQ_CLEAR        (se + 0x648)
#define GENI_TX_FIFO            (se + 0x700)
#define GENI_RX_FIFO            (se + 0x780)
#define GENI_TX_FIFO_STATUS     (se + 0x800)    /* [27:0] words */
#define GENI_RX_FIFO_STATUS     (se + 0x804)    /* bit 31 last, [30:28] bytes of the last word, [24:0] words */
#define GENI_TX_WATERMARK       (se + 0x80c)
#define GENI_RX_WATERMARK       (se + 0x810)
#define GENI_RX_RFR_WATERMARK   (se + 0x814)
#define SE_DMA_TX_IRQ_CLR       (se + 0xc44)
#define SE_DMA_RX_IRQ_CLR       (se + 0xd44)
#define SE_GSI_EVENT_EN         (se + 0xe18)
#define SE_IRQ_EN               (se + 0xe1c)
#define SE_HW_PARAM_0           (se + 0xe24)    /* [21:16] FIFO depth in words */
#define SE_DMA_GENERAL_CFG      (se + 0xe30)

#define M_CMD_DONE              (1u << 0)
#define M_CMD_CANCEL            (1u << 4)
#define M_CMD_ABORT             (1u << 5)
#define M_ERRORS                ((1u << 1) | (1u << 2) | (1u << 3) | (1u << 24) | (1u << 25) | (1u << 28) | (1u << 29))
#define SPI_FULL_DUPLEX         (3u << 27)

static uint32_t fifo_depth;

/* The bus underneath the TouchComm framing: the serial engine, or the same pins driven by hand. */
static bool (*spi_xfer)(const uint8_t *tx, uint8_t *rx, uint32_t length);

/* The electrical experiments (wave 12c), every knob reachable by boot-arg:
 *   touch_miso_pull=0..3       the MISO bias: 0 none (the tree's own), 1 up, 2 down, 3 keeper
 *   touch_reset_active_high=1  hold the chip in reset by driving the line high instead of low
 *   touch_vdd_active_high=0    drive the load switch low instead of high to power the chip
 *   touch_bitbang_us=N         sleep N us in every CLK half period (0: as fast as the writes go)
 *   touch_sweep=0              only the one, baseline probe (the v10b behavior), no sweep
 * With no boot-args at all the first probe is v10b's; when it finds nobody, probe_sweep runs the
 * experiments in sequence, one probe each, and the reads print their raw bytes into the log. */
static unsigned miso_pull;
static unsigned reset_active_high;
static unsigned vdd_active_high = 1;
static uint32_t bitbang_us;
static unsigned sweep_on = 1;
static unsigned v2_headers_shown;
static unsigned v1_chunks_shown;
static unsigned v1_dirty_shown;

/* 0 = ready; otherwise why the engine cannot be used */
static const char *
geni_spi_init(uint32_t hz)
{
	uint32_t divider;

	if ((rd(GENI_FW_REVISION_RO) >> 8 & 0xff) != 1) {
		return "the serial engine has no SPI firmware";
	}
	if (rd(GENI_IF_DISABLE_RO) & 1) {
		return "the serial engine's FIFO interface is disabled";
	}
	fifo_depth = rd(SE_HW_PARAM_0) >> 16 & 0x3f;
	if (fifo_depth < 4) {
		return "the serial engine reports no FIFO";
	}
	wr(SE_GSI_EVENT_EN, 0);
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
	wr(GENI_S_IRQ_CLEAR, 0xffffffff);
	wr(SE_DMA_TX_IRQ_CLR, 0xffffffff);
	wr(SE_DMA_RX_IRQ_CLR, 0xffffffff);
	wr(GENI_CGC_CTRL, rd(GENI_CGC_CTRL) | 0x7f);
	wr(SE_DMA_GENERAL_CFG, rd(SE_DMA_GENERAL_CFG) | 0xf);
	wr(GENI_OUTPUT_CTRL, 0x7f);
	wr(GENI_FORCE_DEFAULT, 1);
	wr(GENI_DMA_MODE_EN, rd(GENI_DMA_MODE_EN) & ~1u);
	wr(GENI_RX_WATERMARK, fifo_depth - 3);
	wr(GENI_RX_RFR_WATERMARK, fifo_depth - 2);
	wr(GENI_TX_WATERMARK, 0);
	/* the status bits we poll follow these enables; the interrupt itself stays masked at the GIC */
	wr(SE_IRQ_EN, rd(SE_IRQ_EN) | 0xf);
	wr(GENI_M_IRQ_EN, rd(GENI_M_IRQ_EN) | 0x7fc0007f);

	/* mode 0, chip select 0, 8 bits, most significant first, four bytes in a FIFO word */
	wr(SPI_LOOPBACK, 0);
	wr(SPI_DEMUX_SEL, 0);
	wr(SPI_CPHA, 0);
	wr(SPI_CPOL, 0);
	wr(SPI_DEMUX_OUTPUT_INV, 0);
	wr(SPI_TRANS_CFG, rd(SPI_TRANS_CFG) & ~2u);
	wr(SPI_DELAY_COUNTERS, 0);
	wr(GENI_TX_PACKING_CFG0, 0x0007f8fe);
	wr(GENI_TX_PACKING_CFG1, 0x000ffefe);
	wr(GENI_RX_PACKING_CFG0, 0x0007f8fe);
	wr(GENI_RX_PACKING_CFG1, 0x000ffefe);
	wr(GENI_BYTE_GRAN, 0);
	wr(SPI_WORD_LEN, 8 - 4);

	divider = (se_source_hz + hz - 1) / hz;
	if (divider < 2) {
		divider = 2;            /* never faster than the chip is sold for, whatever the source rate really is */
	}
	wr(GENI_CLK_SEL, se_clock_select & 7);
	wr(GENI_SER_M_CLK_CFG, divider << 4 | 1);
	return NULL;
}

static void
geni_drain(uint8_t *rx, uint32_t length, uint32_t *received)
{
	uint32_t status = rd(GENI_RX_FIFO_STATUS), words = status & 0x01ffffff, bytes = words * 4;

	if (status & 0x80000000u) {
		uint32_t valid = status >> 28 & 7;

		if (valid && valid < 4) {
			bytes -= 4 - valid;
		}
	}
	for (uint32_t i = 0; i < words; i++) {
		uint32_t word = rd(GENI_RX_FIFO);

		for (int j = 0; j < 4 && bytes; j++, bytes--) {
			if (*received < length) {
				if (rx) {
					rx[*received] = (uint8_t)(word >> (8 * j));
				}
				(*received)++;
			}
		}
	}
}

static void
geni_recover(void)
{
	wr(GENI_M_CMD_CTRL, 1u << 2);
	for (int i = 0; i < 2000 && !(rd(GENI_M_IRQ_STATUS) & M_CMD_CANCEL); i++) {
		sleep_us(100);
	}
	if (!(rd(GENI_M_IRQ_STATUS) & M_CMD_CANCEL)) {
		wr(GENI_M_CMD_CTRL, 1u << 1);
		for (int i = 0; i < 2000 && !(rd(GENI_M_IRQ_STATUS) & M_CMD_ABORT); i++) {
			sleep_us(100);
		}
	}
	for (int i = 0; i < 64 && (rd(GENI_RX_FIFO_STATUS) & 0x01ffffff); i++) {
		(void)rd(GENI_RX_FIFO);
	}
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
}

/* One transfer with the chip selected throughout: `length` bytes out (zeros without tx) and as many in. */
static bool
geni_transfer(const uint8_t *tx, uint8_t *rx, uint32_t length)
{
	static unsigned complaints;
	uint32_t sent = 0, received = 0, status = 0;
	uint64_t deadline;

	for (int i = 0; rd(GENI_STATUS) & 1; i++) {
		if (i > 2000) {
			geni_recover();
			break;
		}
		sleep_us(100);
	}
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
	wr(SPI_TX_TRANS_LEN, length);
	wr(SPI_RX_TRANS_LEN, length);
	wr(GENI_M_CMD0, SPI_FULL_DUPLEX);
	clock_interval_to_deadline(200, NSEC_PER_MSEC, &deadline);
	while (mach_absolute_time() < deadline) {
		while (sent < length && (rd(GENI_TX_FIFO_STATUS) & 0x0fffffff) + 1 < fifo_depth) {
			uint32_t word = 0;

			for (int j = 0; j < 4 && sent < length; j++, sent++) {
				word |= (uint32_t)(tx ? tx[sent] : 0) << (8 * j);
			}
			wr(GENI_TX_FIFO, word);
		}
		status = rd(GENI_M_IRQ_STATUS);
		geni_drain(rx, length, &received);
		if (status & M_ERRORS) {
			break;
		}
		if (status & M_CMD_DONE) {
			geni_drain(rx, length, &received);
			wr(GENI_M_IRQ_CLEAR, status);
			if (received == length) {
				return true;
			}
			break;
		}
	}
	if (complaints++ < 8) {
		printf("s3910: SPI transfer of %u bytes failed: status %#x, sent %u, received %u\n", length, status, sent,
		    received);
	}
	geni_recover();
	return false;
}

/* ---- SPI by hand, on the same pins (the reference driver's fallback; no engine clocks involved) ----- */

static void
bitbang_init(void)
{
	static const unsigned pull_of[4] = { 0, 3, 1, 2 };      /* the TLMM pull: 0 none, 1 down, 2 keeper, 3 up */
	unsigned pull = pull_of[miso_pull & 3];

	gpio_output(PIN_CS, true, PULL_NONE, 6);
	gpio_output(PIN_CLK, false, PULL_NONE, 6);
	gpio_output(PIN_MOSI, false, PULL_NONE, 6);
	gpio_configure(PIN_MISO, 0, pull, 2, false);
	if (pull != PULL_NONE) {
		printf("s3910: the MISO bias is a pull %s\n", pull == PULL_UP ? "up" : pull == 2 ? "down" : "keeper");
	}
}

static bool
bitbang_transfer(const uint8_t *tx, uint8_t *rx, uint32_t length)
{
	gpio_set(PIN_CS, false);
	for (uint32_t i = 0; i < length; i++) {
		uint8_t out = tx ? tx[i] : 0, in = 0;

		for (int bit = 7; bit >= 0; bit--) {
			gpio_set(PIN_MOSI, out >> bit & 1);
			if (bitbang_us) {
				sleep_us(bitbang_us);
			}
			gpio_set(PIN_CLK, true);
			in = (uint8_t)(in << 1 | gpio_get(PIN_MISO));
			if (bitbang_us) {
				sleep_us(bitbang_us);
			}
			gpio_set(PIN_CLK, false);
		}
		if (rx) {
			rx[i] = in;
		}
	}
	gpio_set(PIN_CS, true);
	return true;
}

/* ---- TouchComm: the two formats' shared parts ------------------------------------------------------- */

#define MESSAGE_HEADER_SIZE     4

/* commands */
#define CMD_CONTINUE_WRITE      0x01
#define CMD_IDENTIFY            0x02
#define CMD_RESET               0x04
#define CMD_ENABLE_REPORT       0x05
#define CMD_TCM2_ACK            0x07
#define CMD_TCM2_RETRY          0x08
#define CMD_TCM2_SET_MAX_READ_LENGTH 0x09
#define CMD_TCM2_GET_REPORT     0x0a
#define CMD_RUN_APPLICATION_FIRMWARE 0x14
#define CMD_GET_APPLICATION_INFO 0x20
#define CMD_GET_TOUCH_REPORT_CONFIG 0x25

/* status codes and report codes a message's code byte can hold */
#define STATUS_IDLE             0x00
#define STATUS_OK               0x01
#define STATUS_CONTINUED_READ   0x03
#define STATUS_NO_REPORT_AVAILABLE 0x04
#define STATUS_ACK              0x07
#define STATUS_RETRY_REQUESTED  0x08
#define STATUS_CMD_FAILED       0x09
#define STATUS_NOT_IMPLEMENTED  0x0e
#define STATUS_ERROR            0x0f
#define STATUS_PACKET_CORRUPTED 0xfe
#define STATUS_INVALID          0xff
#define REPORT_IDENTIFY         0x10
#define REPORT_TOUCH            0x11

/* firmware modes (the identification packet's "mode") */
#define MODE_APPLICATION_FIRMWARE 0x01
#define MODE_ROMBOOTLOADER      0x04
#define MODE_BOOTLOADER         0x0b

/* the identification packet: 24 bytes in v1, 32 in v2 (max_read_size and padding more) */
struct tcm_identify {
	uint8_t version, mode;
	uint8_t part_number[16];
	uint8_t build_id[4];
	uint8_t max_write_size[2];
	uint8_t max_read_size[2];       /* v2 */
};
/* the application information packet (the answer to CMD_GET_APPLICATION_INFO) */
struct tcm_app_info {
	uint8_t version[2], status[2];
	uint8_t static_config_size[2], dynamic_config_size[2];
	uint8_t app_config_start_write_block[2], app_config_size[2];
	uint8_t max_touch_report_config_size[2], max_touch_report_payload_size[2];
	uint8_t customer_config_id[16];
	uint8_t max_x[2], max_y[2], max_objects[2], num_of_buttons[2];
	uint8_t num_of_image_rows[2], num_of_image_cols[2], has_hybrid_data[2], num_of_force_elecs[2];
};

#define APP_STATUS_OK           0x00
#define APP_STATUS_BOOTING      0x01
#define APP_STATUS_UPDATING     0x02

static uint16_t
le16(const uint8_t *p)
{
	return (uint16_t)(p[0] | p[1] << 8);
}

static uint32_t
le32(const uint8_t *p)
{
	return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}

/* The TouchComm checksums (Synaptics TouchCom reference: a CRC-6 over the v2 header and a CRC-16/CCITT over the packet). */
static uint8_t
tcm_crc6(const uint8_t *p, unsigned bits)
{
	static const uint16_t table[16] = {
		0, 268, 536, 788, 1072, 1340, 1576, 1828,
		2144, 2412, 2680, 2932, 3152, 3420, 3656, 3908
	};
	uint16_t r = 0x003f << 2, x;

	for (; bits > 8; bits -= 8) {
		r ^= *p++;
		r = (uint16_t)(r << 4 ^ table[r >> 4]);
		r = (uint16_t)(r << 4 ^ table[r >> 4]);
	}
	if (bits > 0) {
		x = *p;
		while (bits--) {
			if (x & 0x80) {
				r ^= 0x80;
			}
			x <<= 1;
			r <<= 1;
			if (r & 0x100) {
				r ^= 0x03 << 2;
			}
		}
	}
	return (uint8_t)(r >> 2 & 0x3f);
}

static uint16_t
tcm_crc16(const uint8_t *p, unsigned len, uint16_t val)
{
	static const uint16_t table[256] = {
		0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
		0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
		0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
		0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
		0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
		0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
		0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
		0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
		0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
		0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
		0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
		0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
		0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
		0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
		0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
		0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
		0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
		0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
		0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
		0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
		0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
		0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
		0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
		0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
		0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
		0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
		0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
		0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
		0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
		0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
		0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
		0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0
	};

	while (len--) {
		val = (uint16_t)(val << 8 ^ table[val >> 8 ^ *p++]);
	}
	return val;
}

/* which format the chip speaks (1 or 2), v2's packet sequence bit, and the packet sizes it accepts */
static int protocol;
static uint8_t seq;
static uint32_t max_rd = 0, max_wr = 0;

/* ---- TouchComm v1: [A5 code len_lo len_hi payload... 5A] ------------------------------------------- */

#define V1_MARKER               0xa5
#define V1_PADDING              0x5a
#define V1_MIN_READ             9       /* the header, four payload bytes and the padding */

/* Clock in the whole message: the header first, then the rest with the two header bytes of the continuation. */
static bool
v1_read(uint8_t *buf, uint32_t buf_size, uint32_t *payload_length, uint8_t *code)
{
	uint32_t total;

	if (!spi_xfer(NULL, buf, V1_MIN_READ)) {
		return false;
	}
	for (unsigned tries = 0; buf[0] != V1_MARKER && tries < 5; tries++) {
		/* a frame clocked sooner than the chip's ~20 ms re-arm tick reads back misaligned
		 * filler (Boot #20's "30 ff ff...") and consumes nothing, so pacing and retrying is
		 * free */
		sleep_ms(10);
		if (!spi_xfer(NULL, buf, V1_MIN_READ)) {
			return false;
		}
	}
	if (buf[0] != V1_MARKER) {
		return false;
	}
	*code = buf[1];
	*payload_length = le16(buf + 2);
	if (*code <= STATUS_ERROR && *code != STATUS_OK) {
		*payload_length = 0;
		return true;            /* a status line: nothing behind it */
	}
	total = MESSAGE_HEADER_SIZE + *payload_length + 1;
	if (total > buf_size) {
		return false;
	}
	if (total > V1_MIN_READ) {
		/*
		 * Boot #19's forensics: this chip answers exactly nine bytes a CS frame -- a
		 * continuation reads back [a5 03][seven payload bytes] and the rest of a longer frame
		 * is idle-high filler (ff). The old code clocked one long frame and then looked for the
		 * padding two positions ahead of where it landed, so every message longer than five
		 * payload bytes was thrown away -- the identify sat on the wire, unread. Harvest the
		 * payload and the trailing padding byte from nine-byte frames instead.
		 */
		uint32_t got = V1_MIN_READ - MESSAGE_HEADER_SIZE;       /* the payload bytes the header frame brought */
		uint8_t chunk[V1_MIN_READ];

		while (got < *payload_length + 1) {                     /* the payload, then its padding byte */
			unsigned tries = 0;

			for (;;) {
				sleep_ms(20);                   /* the chunk re-arm tick the two boots measured */
				if (!spi_xfer(NULL, chunk, V1_MIN_READ)) {
					return false;
				}
				if (chunk[0] == V1_MARKER &&
				    (chunk[1] == STATUS_CONTINUED_READ ||
				     (chunk[1] == STATUS_IDLE && got == *payload_length))) {
					break;
				}
				if (v1_dirty_shown < 6) {
					v1_dirty_shown++;
					printf("s3910: v1 chunk misaligned (payload %u of %u in hand):"
					    " %02x %02x %02x %02x %02x %02x %02x %02x %02x\n", got, *payload_length, chunk[0],
					    chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7], chunk[8]);
				}
				if (++tries > 14) {
					return false;
				}
			}
			if (v1_chunks_shown < 12) {
				v1_chunks_shown++;
				printf("s3910: v1 chunk %u: %02x %02x %02x %02x %02x %02x %02x %02x %02x\n", v1_chunks_shown,
				    chunk[0], chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7], chunk[8]);
			}
			for (uint32_t i = 2; i < V1_MIN_READ && got < *payload_length + 1; i++) {
				if (chunk[1] == STATUS_IDLE && chunk[i] != V1_PADDING) {
					continue;           /* the idle line: keep its 5a, skip the zeros around it */
				}
				buf[MESSAGE_HEADER_SIZE + got] = chunk[i];
				got++;
			}
		}
	} else if (buf[total - 1] != V1_PADDING) {
		return false;
	}
	if (buf[MESSAGE_HEADER_SIZE + *payload_length] != V1_PADDING) {
		return false;
	}
	return true;
}

/* One command of at most 255 bytes of payload: the phone's commands are all smaller. */
static bool
v1_write(uint8_t command, const uint8_t *payload, uint32_t length)
{
	uint8_t out[3 + 255];

	if (length > 255) {
		return false;
	}
	out[0] = command;
	out[1] = (uint8_t)length;
	out[2] = (uint8_t)(length >> 8);
	if (length) {
		memcpy(out + 3, payload, length);
	}
	return spi_xfer(out, NULL, 3 + length);
}

/* ---- TouchComm v2: a header with a CRC-6, packets with a CRC-16 ------------------------------------ */

static bool
v2_write(uint8_t command, const uint8_t *payload, uint32_t length, bool resend)
{
	uint8_t out[MESSAGE_HEADER_SIZE + 255 + 2];

	if (length > 255) {
		return false;
	}
	if (resend) {
		seq -= 1;
	}
	out[0] = command;
	out[1] = (uint8_t)length;
	out[2] = (uint8_t)(length >> 8);
	out[3] = 1u << 7 | (seq++ & 1) << 6;            /* host primary, the sequence toggling, room for the CRC-6 */
	out[3] |= tcm_crc6(out, 26);
	if (length) {
		memcpy(out + MESSAGE_HEADER_SIZE, payload, length);
		uint16_t crc = tcm_crc16(out, MESSAGE_HEADER_SIZE + length, 0xffff);

		out[MESSAGE_HEADER_SIZE + length] = (uint8_t)(crc >> 8);
		out[MESSAGE_HEADER_SIZE + length + 1] = (uint8_t)crc;
	}
	return spi_xfer(out, NULL, MESSAGE_HEADER_SIZE + length + (length ? 2 : 0));
}

/* Read a header and, when there is a payload, the payload behind its CRC. 0 = fine; *code and *payload_length say what came. */
static bool
v2_read(uint8_t *buf, uint32_t buf_size, uint32_t *payload_length, uint8_t *code, uint32_t *max_rd)
{
	uint32_t xfer, got;

	if (!spi_xfer(NULL, buf, MESSAGE_HEADER_SIZE)) {
		return false;
	}
	if (v2_headers_shown < 8) {
		v2_headers_shown++;
		printf("s3910: v2 header %u raw: %02x %02x %02x %02x (crc6 remainder %u)\n", v2_headers_shown, buf[0],
		    buf[1], buf[2], buf[3], tcm_crc6(buf, 32));
	}
	if (tcm_crc6(buf, 32) != 0) {
		*code = STATUS_PACKET_CORRUPTED;
		*payload_length = 0;
		return true;
	}
	*code = buf[0];
	*payload_length = le16(buf + 2);
	if (*payload_length == 0) {
		return true;
	}
	if (MESSAGE_HEADER_SIZE + *payload_length > buf_size) {
		return false;
	}
	xfer = *payload_length;
	if (*max_rd != 0 && *max_rd < xfer) {
		xfer = *max_rd;         /* the rest is fetched in pieces by the caller's continued read */
	}
	if (!spi_xfer(NULL, buf + MESSAGE_HEADER_SIZE, xfer + 2)) {
		return false;
	}
	if (tcm_crc16(buf, MESSAGE_HEADER_SIZE + xfer + 2, 0xffff) != 0) {
		*code = STATUS_PACKET_CORRUPTED;
		return true;
	}
	got = xfer;
	while (got < *payload_length) {
		/* a continuation: ask for the rest, one packet at a time */
		uint32_t chunk = *payload_length - got;

		if (!v2_write(CMD_TCM2_ACK, NULL, 0, false)) {
			return false;
		}
		if (*max_rd != 0 && *max_rd < chunk) {
			chunk = *max_rd;
		}
		if (!spi_xfer(NULL, buf + MESSAGE_HEADER_SIZE + got, chunk + 2 + MESSAGE_HEADER_SIZE)) {
			return false;
		}
		uint8_t *piece = buf + MESSAGE_HEADER_SIZE + got;

		if (tcm_crc6(piece, 32) != 0 || tcm_crc16(piece, chunk + 2 + MESSAGE_HEADER_SIZE, 0xffff) != 0 ||
		    (piece[0] != STATUS_CONTINUED_READ && piece[0] != *code)) {
			*code = STATUS_PACKET_CORRUPTED;
			return true;
		}
		memmove(piece, piece + MESSAGE_HEADER_SIZE, chunk);
		got += chunk;
	}
	*payload_length = got;
	return true;
}

/* ---- the chip, through either format ------------------------------------------------------------------ */

/*
 * Both formats answer the same commands with the same payloads; what differs is the framing. This
 * part is written once against the format the chip turned out to speak.
 */

/* A command and its answer. Returns 0, or the TouchComm status code that went wrong. */
static uint32_t
tcm_command(uint8_t command, const uint8_t *payload, uint32_t length, uint8_t *resp, uint32_t resp_max,
    uint32_t *resp_length)
{
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t payload_length;
	uint8_t code;

	for (int attempt = 0; attempt < 6; attempt++) {
		if (protocol == 2) {
			if (!v2_write(command, payload, length, attempt > 0)) {
				return STATUS_INVALID;
			}
			sleep_us(150);          /* the bus turnaround the reference driver takes */
			if (!v2_read(buf, sizeof(buf), &payload_length, &code, &max_rd)) {
				return STATUS_INVALID;
			}
			if (code == STATUS_PACKET_CORRUPTED || code == STATUS_RETRY_REQUESTED) {
				sleep_ms(2);
				continue;
			}
			if (code == STATUS_ACK) {
				/* the write was taken; the answer itself comes as a report: ask for it */
				if (!v2_write(CMD_TCM2_GET_REPORT, NULL, 0, false) ||
				    !v2_read(buf, sizeof(buf), &payload_length, &code, &max_rd)) {
					return STATUS_INVALID;
				}
			}
		} else {
			if (!v1_write(command, payload, length)) {
				return STATUS_INVALID;
			}
			/* the answer is polled: some tens of microseconds away, a few milliseconds at worst */
			bool heard = false;

			for (int look = 0; look < 100; look++) {
				if (!v1_read(buf, sizeof(buf), &payload_length, &code)) {
					return STATUS_INVALID;
				}
				if (code == STATUS_IDLE || code == STATUS_CONTINUED_READ) {
					sleep_ms(10);
					continue;
				}
				heard = true;
				break;
			}
			if (!heard) {
				return STATUS_INVALID;
			}
		}
		if (code == STATUS_OK || code >= REPORT_IDENTIFY || code == STATUS_NO_REPORT_AVAILABLE) {
			if (resp != NULL && resp_length != NULL) {
				uint32_t given = payload_length < resp_max ? payload_length : resp_max;

				memmove(resp, buf + MESSAGE_HEADER_SIZE, given);
				*resp_length = given;
			}
			return 0;
		}
		if (code == STATUS_CMD_FAILED || code == STATUS_NOT_IMPLEMENTED || code == STATUS_ERROR) {
			printf("s3910: command %#x failed: status %#x\n", command, code);
			return code;
		}
		sleep_ms(5);
	}
	printf("s3910: command %#x: no usable answer after six tries (last status %#x)\n", command, code);
	return code;
}

/* Read whatever report is waiting (v1: it is pushed; v2: asked with CMD_TCM2_GET_REPORT). */
static bool
tcm_get_report(uint8_t *buf, uint32_t buf_size, uint32_t *payload_length, uint8_t *code)
{
	if (protocol == 2) {
		uint32_t got;

		return tcm_command(CMD_TCM2_GET_REPORT, NULL, 0, buf + MESSAGE_HEADER_SIZE, buf_size - MESSAGE_HEADER_SIZE,
		    &got) == 0 && (*payload_length = got, true);
	}
	return v1_read(buf, buf_size, payload_length, code);
}

static void
identify_print(const struct tcm_identify *id)
{
	printf("s3910: TouchComm v%u firmware: mode %#x (%s), part number \"%.16s\", build id %02x%02x%02x%02x, "
	    "max write %u, max read %u\n", id->version, id->mode,
	    id->mode == MODE_APPLICATION_FIRMWARE ? "application" : id->mode == MODE_BOOTLOADER ? "bootloader" :
	    id->mode == MODE_ROMBOOTLOADER ? "ROM bootloader" : "other", (const char *)id->part_number,
	    id->build_id[3], id->build_id[2], id->build_id[1], id->build_id[0], le16(id->max_write_size),
	    id->version >= 2 ? le16(id->max_read_size) : 0);
}

/* Who the chip is: the identification packet after a reset, or the answer to CMD_IDENTIFY. */
static bool
chip_identify(struct tcm_identify *id)
{
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t payload_length = 0;
	uint8_t code = 0;

	/*
	 * The format is not known yet. Reading is passive on v1 (the firmware pushes the packet once
	 * it has booted, some tens of milliseconds after the reset), so v1 is given a second to say
	 * itself before anything is written: a v2-framed command could desync a v1 chip.
	 */
	if (protocol == 0) {
		for (int look = 0; look < 50; look++) {
			bool identified = v1_read(buf, sizeof(buf), &payload_length, &code);

			/* the raw bytes on the wire, for the log: the first three rounds and every tenth tell
			 * 00 (clamped low) from ff (pulled high) from noise (floating) from a real frame */
			if (look < 3 || (look + 1) % 10 == 0) {
				printf("s3910: v1 window, read %u raw: %02x %02x %02x %02x %02x %02x %02x %02x %02x\n",
				    look + 1, buf[0], buf[1], buf[2], buf[3], buf[4], buf[5], buf[6], buf[7], buf[8]);
			}
			if (identified && code == REPORT_IDENTIFY && payload_length >= 24 &&
			    buf[MESSAGE_HEADER_SIZE] == 1) {
				protocol = 1;
				memcpy((uint8_t *)id, buf + MESSAGE_HEADER_SIZE,
				    payload_length < sizeof(*id) ? payload_length : sizeof(*id));
				identify_print(id);
				max_wr = le16(id->max_write_size);
				return true;
			}
			sleep_ms(20);
		}
		protocol = 2;           /* nothing arrived in v1's format: try the checksummed one */
	}
	if (protocol == 2) {
		uint32_t got;

		if (tcm_command(CMD_IDENTIFY, NULL, 0, buf + MESSAGE_HEADER_SIZE, sizeof(buf) - MESSAGE_HEADER_SIZE,
		    &got) != 0 || got < 24) {
			return false;
		}
		payload_length = got;
	} else {
		/* v1: ask the chip to say who it is (the answer comes polled) */
		if (tcm_command(CMD_IDENTIFY, NULL, 0, buf + MESSAGE_HEADER_SIZE, sizeof(buf) - MESSAGE_HEADER_SIZE,
		    &payload_length) != 0 || payload_length < 24) {
			return false;
		}
	}
	memcpy((uint8_t *)id, buf + MESSAGE_HEADER_SIZE, payload_length < sizeof(*id) ? payload_length : sizeof(*id));
	identify_print(id);
	max_wr = le16(id->max_write_size);
	if (id->version >= 2) {
		max_rd = le16(id->max_read_size);
	}
	return true;
}

static struct tcm_app_info app_info;

static bool
chip_app_info(void)
{
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t got;

	for (int attempt = 0; attempt < 10; attempt++) {
		if (tcm_command(CMD_GET_APPLICATION_INFO, NULL, 0, buf + MESSAGE_HEADER_SIZE,
		    sizeof(buf) - MESSAGE_HEADER_SIZE, &got) != 0 || got < 8) {
			return false;
		}
		memcpy(&app_info, buf + MESSAGE_HEADER_SIZE, got < sizeof(app_info) ? got : sizeof(app_info));
		uint16_t status = le16(app_info.status);

		if (status == APP_STATUS_OK) {
			printf("s3910: application: max x %u, max y %u, %u objects, %u buttons, touch report config up to %u bytes\n",
			    le16(app_info.max_x), le16(app_info.max_y), le16(app_info.max_objects), le16(app_info.num_of_buttons),
			    le16(app_info.max_touch_report_config_size));
			return true;
		}
		if (status != APP_STATUS_BOOTING && status != APP_STATUS_UPDATING) {
			printf("s3910: the application firmware is not well (status %#x)\n", status);
			return false;
		}
		sleep_ms(100);          /* still booting (or being updated): the reference driver waits like this */
	}
	printf("s3910: the application firmware did not finish booting\n");
	return false;
}

static bool
chip_run_application(void)
{
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t got;

	printf("s3910: not in application mode: asking for it\n");
	if (tcm_command(CMD_RUN_APPLICATION_FIRMWARE, NULL, 0, buf + MESSAGE_HEADER_SIZE,
	    sizeof(buf) - MESSAGE_HEADER_SIZE, &got) != 0) {
		return false;
	}
	sleep_ms(200);
	return chip_identify(&(struct tcm_identify){0});
}

/* ---- touch reports ---------------------------------------------------------------------------------- */

/* The items of the touch report configuration (Synaptics TouchCom's standard codes). */
#define CFG_END                 0x00
#define CFG_FOREACH_ACTIVE      0x01
#define CFG_FOREACH_OBJECT      0x02
#define CFG_FOREACH_END         0x03
#define CFG_PAD                 0x04
#define CFG_TIMESTAMP           0x05
#define CFG_OBJECT_INDEX        0x06
#define CFG_OBJECT_CLASSIFICATION 0x07
#define CFG_OBJECT_X            0x08
#define CFG_OBJECT_Y            0x09
#define CFG_OBJECT_Z            0x0a
#define CFG_OBJECT_X_WIDTH      0x0b
#define CFG_OBJECT_Y_WIDTH      0x0c
#define CFG_NUM_ACTIVE_OBJECTS  0x18

#define MAX_OBJECTS             10

static uint8_t touch_config[128];
static uint32_t touch_config_size;
static uint32_t max_x = 1, max_y = 1;
static uint32_t flip;           /* boot-arg touch_flip: 1 = mirror left-right, 2 = mirror top-bottom */

/* bits of the report from bit `offset`, little-endian bit order, the way the reference driver reads them */
static uint32_t
report_bits(const uint8_t *report, uint32_t report_size, uint32_t offset, uint32_t bits)
{
	uint32_t out = 0;

	if (bits == 0 || bits > 32 || (offset + bits + 7) / 8 > report_size) {
		return 0;
	}
	for (uint32_t taken = 0; taken < bits; taken++) {
		uint32_t bit = offset + taken;

		out |= (report[bit / 8] >> bit % 8 & 1) << taken;
	}
	return out;
}

/* What has been seen so far: said once a minute, so that the end of the log always tells. */
static struct {
	uint32_t polls, reports, touches, bad, last_x, last_y;
} seen;

static struct {
	bool down;
	uint32_t x, y;
} contact[MAX_OBJECTS];

static void
touch_report(const uint8_t *report, uint32_t report_size)
{
	static unsigned shown;
	uint32_t offset = 0, objects = 0, active = 0, obj = 0, next = 0, cfg = 0;
	bool active_only = false, have_count = false;
	struct {
		uint32_t index, classification, x, y, seen;
	} object[MAX_OBJECTS];

	memset(object, 0, sizeof(object));
	while (cfg < touch_config_size) {
		uint8_t item = touch_config[cfg++];
		uint32_t bits;

		switch (item) {
		case CFG_END:
			goto walk_done;
		case CFG_FOREACH_ACTIVE:
			obj = 0;
			next = cfg;
			active_only = true;
			continue;
		case CFG_FOREACH_OBJECT:
			obj = 0;
			next = cfg;
			active_only = false;
			continue;
		case CFG_FOREACH_END:
			if (active_only) {
				if (have_count) {
					objects++;
					obj++;
					if (objects < active) {
						cfg = next;
					}
				} else if (offset < report_size * 8) {
					obj++;
					cfg = next;
				}
			} else {
				obj++;
				if (obj < MAX_OBJECTS) {
					cfg = next;
				}
			}
			continue;
		case CFG_PAD:
			offset = (offset + 7) / 8 * 8;
			continue;
		case CFG_TIMESTAMP:
		case CFG_OBJECT_INDEX:
		case CFG_OBJECT_CLASSIFICATION:
		case CFG_OBJECT_X:
		case CFG_OBJECT_Y:
		case CFG_OBJECT_Z:
		case CFG_OBJECT_X_WIDTH:
		case CFG_OBJECT_Y_WIDTH:
		case CFG_NUM_ACTIVE_OBJECTS:
		default:
			break;
		}
		if (cfg >= touch_config_size) {
			break;
		}
		bits = touch_config[cfg++];
		uint32_t data = report_bits(report, report_size, offset, bits);

		offset += bits;
		switch (item) {
		case CFG_NUM_ACTIVE_OBJECTS:
			active = data;
			have_count = true;
			break;
		case CFG_OBJECT_INDEX:
			obj = data < MAX_OBJECTS ? data : 0;
			break;
		case CFG_OBJECT_CLASSIFICATION:
			object[obj].classification = data;
			object[obj].seen = 1;
			break;
		case CFG_OBJECT_X:
			object[obj].x = data;
			break;
		case CFG_OBJECT_Y:
			object[obj].y = data;
			break;
		default:
			break;          /* everything else is read only to stay in step */
		}
	}
walk_done:
	if (!have_count) {
		active = objects;
	}
	(void)active;
	for (uint32_t i = 0; i < MAX_OBJECTS; i++) {
		bool now_down = object[i].seen && object[i].classification != 0;

		if (contact[i].down && !now_down) {
			/* a finger that is no longer in the report (or says LIFT) has lifted */
			contact[i].down = false;
			hakios_touch_post(HAKIOS_TOUCH_UP, i, contact[i].x, contact[i].y);
			continue;
		}
		if (!now_down) {
			continue;
		}
		uint32_t x = object[i].x, y = object[i].y;

		if (max_x > 1) {
			x = x >= max_x ? 65535 : x * 65535 / (max_x - 1);
		}
		if (max_y > 1) {
			y = y >= max_y ? 65535 : y * 65535 / (max_y - 1);
		}
		if (flip & 1) {
			x = 65535 - x;
		}
		if (flip & 2) {
			y = 65535 - y;
		}
		seen.touches++;
		seen.last_x = x;
		seen.last_y = y;
		if (shown < 40) {
			shown++;
			printf("s3910: finger %u at %u, %u (of %u x %u)\n", i, x, y, max_x, max_y);
		}
		if (!contact[i].down) {
			hakios_touch_post(HAKIOS_TOUCH_DOWN, i, x, y);
		} else if (contact[i].x != x || contact[i].y != y) {
			hakios_touch_post(HAKIOS_TOUCH_MOVE, i, x, y);
		}
		contact[i].down = true;
		contact[i].x = x;
		contact[i].y = y;
	}
}

static bool
chip_report_config(void)
{
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t got;

	if (tcm_command(CMD_GET_TOUCH_REPORT_CONFIG, NULL, 0, buf + MESSAGE_HEADER_SIZE,
	    sizeof(buf) - MESSAGE_HEADER_SIZE, &got) != 0) {
		return false;
	}
	touch_config_size = got < sizeof(touch_config) ? got : sizeof(touch_config);
	memcpy(touch_config, buf + MESSAGE_HEADER_SIZE, touch_config_size);
	printf("s3910: touch report config: %u bytes:", touch_config_size);
	for (uint32_t i = 0; i < touch_config_size && i < 16; i++) {
		printf(" %02x", touch_config[i]);
	}
	printf("%s\n", touch_config_size > 16 ? " ..." : "");
	return touch_config_size != 0;
}

/* Is the chip there and running its firmware? */
static bool
chip_probe(void)
{
	struct tcm_identify id;

	if (!chip_identify(&id)) {
		return false;
	}
	if (id.mode != MODE_APPLICATION_FIRMWARE) {
		if (!chip_run_application()) {
			return false;
		}
	}
	if (!chip_app_info()) {
		return false;
	}
	uint32_t x = le16(app_info.max_x), y = le16(app_info.max_y);

	if (x > 1 && y > 1) {
		max_x = x;
		max_y = y;
	}
	chip_report_config();
	{
		uint8_t which = REPORT_TOUCH;
		uint8_t buf[MESSAGE_HEADER_SIZE + 512];
		uint32_t got;

		if (tcm_command(CMD_ENABLE_REPORT, &which, 1, buf + MESSAGE_HEADER_SIZE,
		    sizeof(buf) - MESSAGE_HEADER_SIZE, &got) != 0) {
			printf("s3910: touch reports not enabled (status of the command above)\n");
		}
	}
	return true;
}

/* ---- all of it together ---------------------------------------------------------------------------- */

static void
show_state(const char *when)
{
	printf("s3910: %s: votes %#x, clocks %#x %#x %#x, rate cfg %#x dfs %#x; pins cs/clk/mosi/miso cfg %#x %#x %#x %#x,"
	    " reset %#x/%u, int %#x/%u, vdd %#x/%u\n", when, rd(GCC_VOTE), rd(GCC_QUP1_M_AHB_CBCR),
	    rd(GCC_QUP1_S_AHB_CBCR), rd(GCC_QUP1_SE4_CBCR), rd(GCC_QUP1_SE4_CFG), rd(GCC_QUP1_SE4_DFSR), rd(GPIO_CFG(PIN_CS)),
	    rd(GPIO_CFG(PIN_CLK)), rd(GPIO_CFG(PIN_MOSI)), rd(GPIO_CFG(PIN_MISO)), rd(GPIO_CFG(PIN_RESET)),
	    rd(GPIO_IO(PIN_RESET)), rd(GPIO_CFG(PIN_INT)), rd(GPIO_IO(PIN_INT)), rd(GPIO_CFG(PIN_VDD)), rd(GPIO_IO(PIN_VDD)));
}

/* The reset line in whatever polarity the experiment has chosen: assert = hold the chip in reset. */
static void
reset_assert(void)
{
	gpio_output(PIN_RESET, reset_active_high != 0, PULL_UP, 8);
}

static void
reset_release(void)
{
	gpio_set(PIN_RESET, reset_active_high == 0);
}

/* A fresh boot in the current polarity: the tree's 10 ms held, then the tree's 80 ms wait. */
static void
reset_pulse(void)
{
	reset_assert();
	sleep_ms(10);
	reset_release();
	sleep_ms(80);
}

/* Power the chip up from nothing, in the reference driver's order: rails, then reset. The load
 * switch's level is an experiment too (the live FDT flags GPIO 97 active low, but the phone's own
 * driver drives the raw line: its power-on state 1 = high). */
static bool
power_on(void)
{
	reset_assert();                                 /* in reset */
	gpio_configure(PIN_INT, 0, PULL_NONE, 2, false);
	gpio_output(PIN_VDD, vdd_active_high != 0, PULL_NONE, 2);
	rail_on("ldoc3", 3008, "the analog supply");    /* the tree's vdd_2v8_volt */
	rail_on("ldoh4", 1800, "the I/O supply");
	sleep_ms(200);                                  /* the tree's synaptics,power-delay-ms */
	reset_release();
	sleep_ms(100);                                  /* reset low 10 ms is the tree's reset-active-ms; the wait after is 80 */
	return true;
}

static void
use_engine_pins(void)
{
	gpio_configure(PIN_MISO, PIN_FUNCTION_SPI, PULL_NONE, 6, false);
	gpio_configure(PIN_MOSI, PIN_FUNCTION_SPI, PULL_NONE, 6, false);
	gpio_configure(PIN_CLK, PIN_FUNCTION_SPI, PULL_NONE, 6, false);
	gpio_configure(PIN_CS, PIN_FUNCTION_SPI, PULL_NONE, 6, false);
}

/*
 * The pins, interrogated: with the reset asserted (the chip should be silent) and again with it
 * released, clock a known pattern and print what MISO gives back. An echo of the pattern means the
 * pins are shorted together or the pad loops back; a flat 00/ff names the clamp; a difference
 * between the two reads says the chip's output stage is alive on this line.
 */
static void
electrical_probe(void)
{
	static const uint8_t pattern[9] = { 0xa5, 0x5a, 0x00, 0xff, 0x55, 0xaa, 0x01, 0x80, 0x77 };
	uint8_t echo[9];
	int i;

	reset_assert();
	sleep_ms(20);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset asserted, rx:");
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\n");
	reset_release();
	sleep_ms(80);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset released, rx:");
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\n");
}

/* The sweep (the wave12b fix list): one experiment per probe, each printing its own raw bytes, so
 * one boot separates bias from pacing from polarity. Every phase ends with its own pin state. */
static bool
probe_sweep(void)
{
	static const struct {
		const char *name;
		unsigned pull, reset_high, vdd_high, full_power;
		uint32_t pace_us;
	} phase[5] = {
		{ "the MISO bias pulled up", 1, 0, 1, 0, 0 },
		{ "the clock paced at 5 us a half period", 0, 0, 1, 0, 5 },
		{ "the MISO pulled up and the clock paced", 1, 0, 1, 0, 5 },
		{ "the reset polarity inverted", 0, 1, 1, 1, 0 },
		{ "the load switch driven low for power", 0, 0, 0, 1, 0 },
	};
	const unsigned pull_arg = miso_pull, reset_arg = reset_active_high, vdd_arg = vdd_active_high;
	const uint32_t pace_arg = bitbang_us;
	bool answered = false;

	for (unsigned p = 0; p < 5; p++) {
		printf("s3910: experiment %u of 5: %s\n", p + 1, phase[p].name);
		miso_pull = phase[p].pull;
		reset_active_high = phase[p].reset_high;
		vdd_active_high = phase[p].vdd_high;
		bitbang_us = phase[p].pace_us ? phase[p].pace_us : pace_arg;
		bitbang_init();
		if (phase[p].full_power) {
			power_on();
		} else {
			reset_pulse();
		}
		protocol = 0;
		v2_headers_shown = 0;
		if (chip_probe()) {
			printf("s3910: the chip answered while %s\n", phase[p].name);
			answered = true;
			break;
		}
		show_state(phase[p].name);
	}
	if (!answered) {
		/* the final word on the pins is the boot-arg configuration, not the last experiment */
		miso_pull = pull_arg;
		reset_active_high = reset_arg;
		vdd_active_high = vdd_arg;
		bitbang_us = pace_arg;
		bitbang_init();
	}
	return answered;
}

static bool
bring_up(void)
{
	const char *problem = "its clocks cannot be turned on";

	show_state("as found");
	if (!power_on()) {
		printf("s3910: the supplies are not on; the chip is left alone\n");
		return false;
	}
	if (clocks_on()) {
		printf("s3910: serial engine: firmware %#x, interface %#x, parameters %#x, source clock %u Hz (select %u)\n",
		    rd(GENI_FW_REVISION_RO), rd(GENI_IF_DISABLE_RO), rd(SE_HW_PARAM_0), se_source_hz, se_clock_select);
		uint32_t spi_hz = 10000000;

		/* boot-arg touch_spi_hz=N: the bus at N Hz (the tree gives the chip 12 or 15 MHz) */
		PE_parse_boot_argn("touch_spi_hz", &spi_hz, sizeof(spi_hz));
		if (spi_hz < 100000 || spi_hz > 15000000) {
			spi_hz = 10000000;
		}
		printf("s3910: the bus at %u Hz\n", spi_hz);
		problem = geni_spi_init(spi_hz);
	}
	if (problem == NULL) {
		use_engine_pins();
		spi_xfer = geni_transfer;
		show_state("powered, on the serial engine");
		if (chip_probe()) {
			return true;
		}
		printf("s3910: the chip did not answer through the serial engine; trying the pins by hand\n");
	} else {
		printf("s3910: %s; driving the pins by hand\n", problem);
	}
	/* by hand; mode 0, the same pins as plain gpio -- nothing but the TLMM is needed */
	spi_xfer = bitbang_transfer;
	bitbang_init();
	electrical_probe();
	if (chip_probe()) {
		printf("s3910: the chip answers on pins driven by hand\n");
		return true;
	}
	if (sweep_on && probe_sweep()) {
		return true;
	}
	show_state("no answer");
	return false;
}

static uint64_t
micros_now(void)
{
	uint64_t ns;

	absolutetime_to_nanoseconds(mach_absolute_time(), &ns);
	return ns / 1000;
}

static void
s3910_thread(__unused void *parameter, __unused wait_result_t result)
{
	unsigned idle = 0, idle_looks;
	uint32_t poll_us = 8000;
	uint8_t buf[MESSAGE_HEADER_SIZE + 512];
	uint32_t payload_length;
	uint8_t code;

	PE_parse_boot_argn("touch_poll_us", &poll_us, sizeof(poll_us));
	if (poll_us < 250 || poll_us > 100000) {
		poll_us = 8000;
	}
	idle_looks = 80000 / poll_us;   /* a report read every 80 ms even with the line high, in case it is missed */
	PE_parse_boot_argn("touch_miso_pull", &miso_pull, sizeof(miso_pull));
	if (miso_pull > 3) {
		miso_pull = 0;
	}
	PE_parse_boot_argn("touch_reset_active_high", &reset_active_high, sizeof(reset_active_high));
	PE_parse_boot_argn("touch_vdd_active_high", &vdd_active_high, sizeof(vdd_active_high));
	PE_parse_boot_argn("touch_bitbang_us", &bitbang_us, sizeof(bitbang_us));
	if (bitbang_us > 100) {
		bitbang_us = 0;
	}
	PE_parse_boot_argn("touch_sweep", &sweep_on, sizeof(sweep_on));

	tlmm = ml_io_map(TLMM_PHYS, TLMM_SIZE);
	gcc = ml_io_map(GCC_PHYS, GCC_SIZE);
	se = ml_io_map(SE_PHYS, SE_SIZE);
	rsc = ml_io_map(RSC_PHYS, RSC_SIZE);
	cmd_db = ml_io_map_wcomb(CMD_DB_PHYS, CMD_DB_SIZE);      /* memory, not registers: no alignment rules */

	if (!bring_up()) {
		printf("s3910: no touch screen\n");
		thread_terminate(current_thread());
		return;
	}
	printf("s3910: touch screen ready (TouchComm v%u); the interrupt line is looked at every %u us\n", protocol,
	    poll_us);
	for (unsigned tick = 1;; tick++) {
		bool look = false;

		/* the interrupt line is low while a report waits; look anyway every 80 ms in case it is missed */
		if (!gpio_get(PIN_INT)) {
			idle = 0;
			look = true;
		} else if (++idle >= idle_looks) {
			idle = 0;
			look = true;
		}
		if (look) {
			seen.polls++;
			code = 0;
			if (!tcm_get_report(buf, sizeof(buf), &payload_length, &code)) {
				seen.bad++;
				sleep_us(poll_us);
				continue;
			}
			seen.reports++;
			if (code == REPORT_TOUCH && payload_length != 0) {
				touch_report(buf + MESSAGE_HEADER_SIZE, payload_length);
			} else if (code == REPORT_IDENTIFY && payload_length >= 24) {
				/* the chip says who it is again (it reset itself, or switched modes) */
				struct tcm_identify id;

				memcpy(&id, buf + MESSAGE_HEADER_SIZE, payload_length < sizeof(id) ? payload_length : sizeof(id));
				identify_print(&id);
			}
		}
		if (tick % (60 * (1000000 / poll_us)) == 0) {
			printf("s3910: so far %u reports in %u looks (%u bad), %u finger positions, the last at %u, %u; "
			    "interrupt line %s; the line looked at every %u us\n", seen.reports, seen.polls, seen.bad,
			    seen.touches, seen.last_x, seen.last_y, gpio_get(PIN_INT) ? "high" : "low", poll_us);
		}
		sleep_us(poll_us);
	}
}

void
hakios_s3910_init(void)
{
	uint32_t enabled = 0;
	thread_t thread;

	if (!PE_parse_boot_argn("touchscreen", &enabled, sizeof(enabled)) || !enabled) {
		return;
	}
	PE_parse_boot_argn("touch_flip", &flip, sizeof(flip));
	if (kernel_thread_start(s3910_thread, NULL, &thread) == KERN_SUCCESS) {
		thread_deallocate(thread);
	}
}
