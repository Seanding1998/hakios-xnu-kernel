p = '/home/<host>/hakios/kernel/devices/phk110/drivers/input/hakios.s3910.c'
s = open(p).read()

def rep(old, new, what):
    global s
    assert s.count(old) == 1, (what, s.count(old))
    s = s.replace(old, new, 1)
    print(what, 'patched')

# 1. Boot #16: the wrapper's s_ahb branch read 0x80000002 (halted) through the vote while the
#    engine's own branch (0x284dc) un-halted fine; this gcc is cape's (the FDT's clock indices
#    134/135 for m/s_ahb are not the sm8450 table's 118/119), so the branch we read may not be
#    ours at all. The engine answers or not: demote s_ahb to a warning and let geni_spi_init say.
rep('''	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_SE4);
	for (int i = 0; i < 1000; i++) {
		if (!((rd(GCC_QUP1_M_AHB_CBCR) | rd(GCC_QUP1_S_AHB_CBCR) | rd(GCC_QUP1_SE4_CBCR)) & CLOCK_OFF)) {
			return true;
		}
		sleep_us(10);
	}
	printf("s3910: clocks stay off: %#x %#x %#x\\n", rd(GCC_QUP1_M_AHB_CBCR), rd(GCC_QUP1_S_AHB_CBCR),
	    rd(GCC_QUP1_SE4_CBCR));
	return false;
}''',
'''	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_SE4);
	for (int i = 0; i < 1000; i++) {
		if (!((rd(GCC_QUP1_M_AHB_CBCR) | rd(GCC_QUP1_SE4_CBCR)) & CLOCK_OFF)) {
			/*
			 * Boot #16: this gcc is cape's -- the tree's m/s_ahb clock indices (134/135) are not
			 * the sm8450 table's (118/119) -- and the branch at 0x28008 read 0x80000002 (halted)
			 * through the vote while the engine's own branch un-halted fine. It is not believed:
			 * warn and let the engine's firmware revision say whether it is alive.
			 */
			if (rd(GCC_QUP1_S_AHB_CBCR) & CLOCK_OFF) {
				printf("s3910: the wrapper's s_ahb clock still reads halted (%#x); trying the engine anyway\\n",
				    rd(GCC_QUP1_S_AHB_CBCR));
			}
			return true;
		}
		sleep_us(10);
	}
	printf("s3910: clocks stay off: %#x %#x %#x\\n", rd(GCC_QUP1_M_AHB_CBCR), rd(GCC_QUP1_S_AHB_CBCR),
	    rd(GCC_QUP1_SE4_CBCR));
	return false;
}''', '1 clocks_on s_ahb demoted')

# 2. a transfer function pointer, so the pins-by-hand path can take over when the engine is dead
rep('''static uint32_t fifo_depth;

/* 0 = ready; otherwise why the engine cannot be used */
static const char *
geni_spi_init(uint32_t hz)
{''',
'''static uint32_t fifo_depth;

/* The bus underneath the TouchComm framing: the serial engine, or the same pins driven by hand. */
static bool (*spi_xfer)(const uint8_t *tx, uint8_t *rx, uint32_t length);

/* 0 = ready; otherwise why the engine cannot be used */
static const char *
geni_spi_init(uint32_t hz)
{''', '2 transfer pointer declared')

# 3. route the TouchComm transfers through the pointer
s = s.replace('return geni_transfer(NULL, buf, V1_MIN_READ);', 'return spi_xfer(NULL, buf, V1_MIN_READ);')
s = s.replace('if (!geni_transfer(NULL, buf + V1_MIN_READ, rest + 2)) {', 'if (!spi_xfer(NULL, buf + V1_MIN_READ, rest + 2)) {')
s = s.replace('return geni_transfer(out, NULL, 3 + length);', 'return spi_xfer(out, NULL, 3 + length);')
s = s.replace('return geni_transfer(out, NULL, MESSAGE_HEADER_SIZE + length + (length ? 2 : 0));',
    'return spi_xfer(out, NULL, MESSAGE_HEADER_SIZE + length + (length ? 2 : 0));')
s = s.replace('if (!geni_transfer(NULL, buf, MESSAGE_HEADER_SIZE)) {', 'if (!spi_xfer(NULL, buf, MESSAGE_HEADER_SIZE)) {')
s = s.replace('if (!geni_transfer(NULL, buf + MESSAGE_HEADER_SIZE, xfer + 2)) {', 'if (!spi_xfer(NULL, buf + MESSAGE_HEADER_SIZE, xfer + 2)) {')
s = s.replace('if (!geni_transfer(NULL, buf + MESSAGE_HEADER_SIZE + got, chunk + 2 + MESSAGE_HEADER_SIZE)) {',
    'if (!spi_xfer(NULL, buf + MESSAGE_HEADER_SIZE + got, chunk + 2 + MESSAGE_HEADER_SIZE)) {')
print('3 transfers routed')

# 4. the pins by hand (the goodix driver's fallback, the same TLMM): CS 19, CLK 18, MOSI 17, MISO 16
rep('''/* ---- TouchComm: the two formats' shared parts ------------------------------------------------------- */''',
'''/* ---- SPI by hand, on the same pins (the reference driver's fallback; no engine clocks involved) ----- */

static void
bitbang_init(void)
{
	gpio_output(PIN_CS, true, PULL_NONE, 6);
	gpio_output(PIN_CLK, false, PULL_NONE, 6);
	gpio_output(PIN_MOSI, false, PULL_NONE, 6);
	gpio_configure(PIN_MISO, 0, PULL_NONE, 2, false);
}

static bool
bitbang_transfer(const uint8_t *tx, uint8_t *rx, uint32_t length)
{
	gpio_set(PIN_CS, false);
	for (uint32_t i = 0; i < length; i++) {
		uint8_t out = tx ? tx[i] : 0, in = 0;

		for (int bit = 7; bit >= 0; bit--) {
			gpio_set(PIN_MOSI, out >> bit & 1);
			gpio_set(PIN_CLK, true);
			in = (uint8_t)(in << 1 | gpio_get(PIN_MISO));
			gpio_set(PIN_CLK, false);
		}
		if (rx) {
			rx[i] = in;
		}
	}
	gpio_set(PIN_CS, true);
	return true;
}

/* ---- TouchComm: the two formats' shared parts ------------------------------------------------------- */''', '4 bitbang added')

# 5. bring_up: fall back to the pins by hand when the engine cannot be used or does not answer
rep('''	if (problem != NULL) {
		printf("s3910: %s; no SPI\\n", problem);
		return false;
	}
	use_engine_pins();
	show_state("powered, on the serial engine");
	if (!chip_probe()) {
		show_state("no answer");
		return false;
	}
	return true;
}''',
'''	if (problem == NULL) {
		use_engine_pins();
		spi_xfer = geni_transfer;
		show_state("powered, on the serial engine");
		if (chip_probe()) {
			return true;
		}
		printf("s3910: the chip did not answer through the serial engine; trying the pins by hand\\n");
	} else {
		printf("s3910: %s; driving the pins by hand\\n", problem);
	}
	/* by hand; mode 0, the same pins as plain gpio -- nothing but the TLMM is needed */
	spi_xfer = bitbang_transfer;
	bitbang_init();
	if (chip_probe()) {
		printf("s3910: the chip answers on pins driven by hand\\n");
		return true;
	}
	show_state("no answer");
	return false;
}''', '5 bring_up fallback')

open(p, 'w').write(s)
print('s3910.c v10 changes written')
