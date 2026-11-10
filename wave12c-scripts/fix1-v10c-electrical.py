#!/usr/bin/env python3
"""Wave 12c fix: the S3910 electrical-layer experiments from the wave12b fix
list (docs/wave12b-probe-verdict.md section 4), all six items:

 1  raw-byte forensics: the v1 window prints the 9 bytes it clocked in on
    rounds 1, 2, 3 and every tenth; v2 prints every header it reads (up to 8
    per probe, counted from zero again for each sweep phase).
 2  MISO bias experiment: boot-arg touch_miso_pull=0..3 (0 none = v10b), and
    sweep phase 1 probes once with the pull-up engaged.
 3  reset polarity experiment: boot-arg touch_reset_active_high=1, and sweep
    phase 4 runs the whole power sequence with the line inverted.
 4  bitbang pacing: boot-arg touch_bitbang_us=N (CLK half period, us), and
    sweep phases 2/3 probe at 5 us.
 5  pad/polarity re-check: done against the live FDT and the phone's own
    driver source (no code) -- qup4 = gpio16..19 func 1 confirmed; reset is
    active low (DT flags + reset-on-state 0); GPIO 97 power switch is driven
    raw-high by the phone's own driver. Only the switch level stays an
    experiment: sweep phase 5 drives it low once (touch_vdd_active_high=0).
 6  GENI DMA/GSI path: not in v10c (the wave12b report keeps it remote-backup).

Plus the loopback probe: with the reset asserted and again with it released,
clock a known pattern and log what MISO returns -- a MOSI echo (short/loop),
a flat 00/ff (clamp), or a difference between the two reads (chip alive).

Without boot-args the baseline probe is v10b's exactly; the sweep only runs
after it has already found nobody. usage:
  fix1-v10c-electrical.py SOURCE_V10B OUT_V10C
Every replacement asserts its own count, so a mismatch fails loudly (the
wave12 lesson: str.replace skips silently).
"""
import sys

SRC, DST = sys.argv[1:3]
s = open(SRC).read()


def swap(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, f'{what}: appears {n} times, not 1'
    assert s.count(new) == 0, f'{what}: the new text is already present'
    s = s.replace(old, new, 1)
    print(f'  patched: {what}')


# ---- the experiment knobs, next to the spi_xfer pointer ----------------------
swap('''/* The bus underneath the TouchComm framing: the serial engine, or the same pins driven by hand. */
static bool (*spi_xfer)(const uint8_t *tx, uint8_t *rx, uint32_t length);
''',
'''/* The bus underneath the TouchComm framing: the serial engine, or the same pins driven by hand. */
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
''', 'experiment knobs (globals)')

# ---- 2: the MISO bias in bitbang_init ----------------------------------------
swap('''static void
bitbang_init(void)
{
\tgpio_output(PIN_CS, true, PULL_NONE, 6);
\tgpio_output(PIN_CLK, false, PULL_NONE, 6);
\tgpio_output(PIN_MOSI, false, PULL_NONE, 6);
\tgpio_configure(PIN_MISO, 0, PULL_NONE, 2, false);
}''',
'''static void
bitbang_init(void)
{
\tstatic const unsigned pull_of[4] = { 0, 3, 1, 2 };      /* the TLMM pull: 0 none, 1 down, 2 keeper, 3 up */
\tunsigned pull = pull_of[miso_pull & 3];

\tgpio_output(PIN_CS, true, PULL_NONE, 6);
\tgpio_output(PIN_CLK, false, PULL_NONE, 6);
\tgpio_output(PIN_MOSI, false, PULL_NONE, 6);
\tgpio_configure(PIN_MISO, 0, pull, 2, false);
\tif (pull != PULL_NONE) {
\t\tprintf("s3910: the MISO bias is a pull %s\\n", pull == PULL_UP ? "up" : pull == 2 ? "down" : "keeper");
\t}
}''', 'MISO bias in bitbang_init')

# ---- 4: the bitbang pacing ----------------------------------------------------
swap('''\t\tfor (int bit = 7; bit >= 0; bit--) {
\t\t\tgpio_set(PIN_MOSI, out >> bit & 1);
\t\t\tgpio_set(PIN_CLK, true);
\t\t\tin = (uint8_t)(in << 1 | gpio_get(PIN_MISO));
\t\t\tgpio_set(PIN_CLK, false);
\t\t}''',
'''\t\tfor (int bit = 7; bit >= 0; bit--) {
\t\t\tgpio_set(PIN_MOSI, out >> bit & 1);
\t\t\tif (bitbang_us) {
\t\t\t\tsleep_us(bitbang_us);
\t\t\t}
\t\t\tgpio_set(PIN_CLK, true);
\t\t\tin = (uint8_t)(in << 1 | gpio_get(PIN_MISO));
\t\t\tif (bitbang_us) {
\t\t\t\tsleep_us(bitbang_us);
\t\t\t}
\t\t\tgpio_set(PIN_CLK, false);
\t\t}''', 'bitbang CLK pacing')

# ---- 1: the v2 header forensics ------------------------------------------------
swap('''\tif (!spi_xfer(NULL, buf, MESSAGE_HEADER_SIZE)) {
\t\treturn false;
\t}
\tif (tcm_crc6(buf, 32) != 0) {
\t\t*code = STATUS_PACKET_CORRUPTED;
\t\t*payload_length = 0;
\t\treturn true;
\t}''',
'''\tif (!spi_xfer(NULL, buf, MESSAGE_HEADER_SIZE)) {
\t\treturn false;
\t}
\tif (v2_headers_shown < 8) {
\t\tv2_headers_shown++;
\t\tprintf("s3910: v2 header %u raw: %02x %02x %02x %02x (crc6 remainder %u)\\n", v2_headers_shown, buf[0],
\t\t    buf[1], buf[2], buf[3], tcm_crc6(buf, 32));
\t}
\tif (tcm_crc6(buf, 32) != 0) {
\t\t*code = STATUS_PACKET_CORRUPTED;
\t\t*payload_length = 0;
\t\treturn true;
\t}''', 'v2 header raw-byte forensics')

# ---- 1: the v1 window forensics -------------------------------------------------
swap('''\tif (protocol == 0) {
\t\tfor (int look = 0; look < 50; look++) {
\t\t\tif (v1_read(buf, sizeof(buf), &payload_length, &code) && code == REPORT_IDENTIFY &&
\t\t\t    payload_length >= 24 && buf[MESSAGE_HEADER_SIZE] == 1) {
\t\t\t\tprotocol = 1;
\t\t\t\tmemcpy((uint8_t *)id, buf + MESSAGE_HEADER_SIZE,
\t\t\t\t    payload_length < sizeof(*id) ? payload_length : sizeof(*id));
\t\t\t\tidentify_print(id);
\t\t\t\tmax_wr = le16(id->max_write_size);
\t\t\t\treturn true;
\t\t\t}
\t\t\tsleep_ms(20);
\t\t}
\t\tprotocol = 2;           /* nothing arrived in v1's format: try the checksummed one */
\t}''',
'''\tif (protocol == 0) {
\t\tfor (int look = 0; look < 50; look++) {
\t\t\tbool identified = v1_read(buf, sizeof(buf), &payload_length, &code);

\t\t\t/* the raw bytes on the wire, for the log: the first three rounds and every tenth tell
\t\t\t * 00 (clamped low) from ff (pulled high) from noise (floating) from a real frame */
\t\t\tif (look < 3 || (look + 1) % 10 == 0) {
\t\t\t\tprintf("s3910: v1 window, read %u raw: %02x %02x %02x %02x %02x %02x %02x %02x %02x\\n",
\t\t\t\t    look + 1, buf[0], buf[1], buf[2], buf[3], buf[4], buf[5], buf[6], buf[7], buf[8]);
\t\t\t}
\t\t\tif (identified && code == REPORT_IDENTIFY && payload_length >= 24 &&
\t\t\t    buf[MESSAGE_HEADER_SIZE] == 1) {
\t\t\t\tprotocol = 1;
\t\t\t\tmemcpy((uint8_t *)id, buf + MESSAGE_HEADER_SIZE,
\t\t\t\t    payload_length < sizeof(*id) ? payload_length : sizeof(*id));
\t\t\t\tidentify_print(id);
\t\t\t\tmax_wr = le16(id->max_write_size);
\t\t\t\treturn true;
\t\t\t}
\t\t\tsleep_ms(20);
\t\t}
\t\tprotocol = 2;           /* nothing arrived in v1's format: try the checksummed one */
\t}''', 'v1 window raw-byte forensics')

# ---- 3: the reset polarity helpers + power_on ------------------------------------
swap('''/* Power the chip up from nothing, in the reference driver's order: rails, then reset. */
static bool
power_on(void)
{
\tgpio_output(PIN_RESET, false, PULL_UP, 8);      /* in reset */
\tgpio_configure(PIN_INT, 0, PULL_NONE, 2, false);
\tgpio_output(PIN_VDD, true, PULL_NONE, 2);
\trail_on("ldoc3", 3008, "the analog supply");    /* the tree's vdd_2v8_volt */
\trail_on("ldoh4", 1800, "the I/O supply");
\tsleep_ms(200);                                  /* the tree's synaptics,power-delay-ms */
\tgpio_set(PIN_RESET, true);
\tsleep_ms(100);                                  /* reset low 10 ms is the tree's reset-active-ms; the wait after is 80 */
\treturn true;
}''',
'''/* The reset line in whatever polarity the experiment has chosen: assert = hold the chip in reset. */
static void
reset_assert(void)
{
\tgpio_output(PIN_RESET, reset_active_high != 0, PULL_UP, 8);
}

static void
reset_release(void)
{
\tgpio_set(PIN_RESET, reset_active_high == 0);
}

/* A fresh boot in the current polarity: the tree's 10 ms held, then the tree's 80 ms wait. */
static void
reset_pulse(void)
{
\treset_assert();
\tsleep_ms(10);
\treset_release();
\tsleep_ms(80);
}

/* Power the chip up from nothing, in the reference driver's order: rails, then reset. The load
 * switch's level is an experiment too (the live FDT flags GPIO 97 active low, but the phone's own
 * driver drives the raw line: its power-on state 1 = high). */
static bool
power_on(void)
{
\treset_assert();                                 /* in reset */
\tgpio_configure(PIN_INT, 0, PULL_NONE, 2, false);
\tgpio_output(PIN_VDD, vdd_active_high != 0, PULL_NONE, 2);
\trail_on("ldoc3", 3008, "the analog supply");    /* the tree's vdd_2v8_volt */
\trail_on("ldoh4", 1800, "the I/O supply");
\tsleep_ms(200);                                  /* the tree's synaptics,power-delay-ms */
\treset_release();
\tsleep_ms(100);                                  /* reset low 10 ms is the tree's reset-active-ms; the wait after is 80 */
\treturn true;
}''', 'reset polarity helpers + power_on')

# ---- 5/6-side: the loopback probe and the sweep, then bring_up's tail --------------
swap('''static bool
bring_up(void)
{
\tconst char *problem = "its clocks cannot be turned on";
''',
'''/*
 * The pins, interrogated: with the reset asserted (the chip should be silent) and again with it
 * released, clock a known pattern and print what MISO gives back. An echo of the pattern means the
 * pins are shorted together or the pad loops back; a flat 00/ff names the clamp; a difference
 * between the two reads says the chip's output stage is alive on this line.
 */
static void
electrical_probe(void)
{
\tstatic const uint8_t pattern[9] = { 0xa5, 0x5a, 0x00, 0xff, 0x55, 0xaa, 0x01, 0x80, 0x77 };
\tuint8_t echo[9];
\tint i;

\treset_assert();
\tsleep_ms(20);
\tbitbang_transfer(pattern, echo, 9);
\tprintf("s3910: loopback probe, reset asserted, rx:");
\tfor (i = 0; i < 9; i++) {
\t\tprintf(" %02x", echo[i]);
\t}
\tprintf("\\n");
\treset_release();
\tsleep_ms(80);
\tbitbang_transfer(pattern, echo, 9);
\tprintf("s3910: loopback probe, reset released, rx:");
\tfor (i = 0; i < 9; i++) {
\t\tprintf(" %02x", echo[i]);
\t}
\tprintf("\\n");
}

/* The sweep (the wave12b fix list): one experiment per probe, each printing its own raw bytes, so
 * one boot separates bias from pacing from polarity. Every phase ends with its own pin state. */
static bool
probe_sweep(void)
{
\tstatic const struct {
\t\tconst char *name;
\t\tunsigned pull, reset_high, vdd_high, full_power;
\t\tuint32_t pace_us;
\t} phase[5] = {
\t\t{ "the MISO bias pulled up", 1, 0, 1, 0, 0 },
\t\t{ "the clock paced at 5 us a half period", 0, 0, 1, 0, 5 },
\t\t{ "the MISO pulled up and the clock paced", 1, 0, 1, 0, 5 },
\t\t{ "the reset polarity inverted", 0, 1, 1, 1, 0 },
\t\t{ "the load switch driven low for power", 0, 0, 0, 1, 0 },
\t};
\tconst unsigned pull_arg = miso_pull, reset_arg = reset_active_high, vdd_arg = vdd_active_high;
\tconst uint32_t pace_arg = bitbang_us;
\tbool answered = false;

\tfor (unsigned p = 0; p < 5; p++) {
\t\tprintf("s3910: experiment %u of 5: %s\\n", p + 1, phase[p].name);
\t\tmiso_pull = phase[p].pull;
\t\treset_active_high = phase[p].reset_high;
\t\tvdd_active_high = phase[p].vdd_high;
\t\tbitbang_us = phase[p].pace_us ? phase[p].pace_us : pace_arg;
\t\tbitbang_init();
\t\tif (phase[p].full_power) {
\t\t\tpower_on();
\t\t} else {
\t\t\treset_pulse();
\t\t}
\t\tprotocol = 0;
\t\tv2_headers_shown = 0;
\t\tif (chip_probe()) {
\t\t\tprintf("s3910: the chip answered while %s\\n", phase[p].name);
\t\t\tanswered = true;
\t\t\tbreak;
\t\t}
\t\tshow_state(phase[p].name);
\t}
\tif (!answered) {
\t\t/* the final word on the pins is the boot-arg configuration, not the last experiment */
\t\tmiso_pull = pull_arg;
\t\treset_active_high = reset_arg;
\t\tvdd_active_high = vdd_arg;
\t\tbitbang_us = pace_arg;
\t\tbitbang_init();
\t}
\treturn answered;
}

static bool
bring_up(void)
{
\tconst char *problem = "its clocks cannot be turned on";
''', 'electrical_probe + probe_sweep before bring_up')

swap('''\t/* by hand; mode 0, the same pins as plain gpio -- nothing but the TLMM is needed */
\tspi_xfer = bitbang_transfer;
\tbitbang_init();
\tif (chip_probe()) {
\t\tprintf("s3910: the chip answers on pins driven by hand\\n");
\t\treturn true;
\t}
\tshow_state("no answer");
\treturn false;
}''',
'''\t/* by hand; mode 0, the same pins as plain gpio -- nothing but the TLMM is needed */
\tspi_xfer = bitbang_transfer;
\tbitbang_init();
\telectrical_probe();
\tif (chip_probe()) {
\t\tprintf("s3910: the chip answers on pins driven by hand\\n");
\t\treturn true;
\t}
\tif (sweep_on && probe_sweep()) {
\t\treturn true;
\t}
\tshow_state("no answer");
\treturn false;
}''', 'bring_up tail: loopback + sweep wiring')

# ---- the boot-args -----------------------------------------------------------------
swap('''\tPE_parse_boot_argn("touch_poll_us", &poll_us, sizeof(poll_us));
\tif (poll_us < 250 || poll_us > 100000) {
\t\tpoll_us = 8000;
\t}
\tidle_looks = 80000 / poll_us;   /* a report read every 80 ms even with the line high, in case it is missed */
''',
'''\tPE_parse_boot_argn("touch_poll_us", &poll_us, sizeof(poll_us));
\tif (poll_us < 250 || poll_us > 100000) {
\t\tpoll_us = 8000;
\t}
\tidle_looks = 80000 / poll_us;   /* a report read every 80 ms even with the line high, in case it is missed */
\tPE_parse_boot_argn("touch_miso_pull", &miso_pull, sizeof(miso_pull));
\tif (miso_pull > 3) {
\t\tmiso_pull = 0;
\t}
\tPE_parse_boot_argn("touch_reset_active_high", &reset_active_high, sizeof(reset_active_high));
\tPE_parse_boot_argn("touch_vdd_active_high", &vdd_active_high, sizeof(vdd_active_high));
\tPE_parse_boot_argn("touch_bitbang_us", &bitbang_us, sizeof(bitbang_us));
\tif (bitbang_us > 100) {
\t\tbitbang_us = 0;
\t}
\tPE_parse_boot_argn("touch_sweep", &sweep_on, sizeof(sweep_on));
''', 'boot-arg parsing')

open(DST, 'w').write(s)

# ---- post-conditions ------------------------------------------------------------
assert s.count('geni_transfer') == 2, f'geni_transfer refs: {s.count("geni_transfer")}'
assert s.count('v1 window, read %u raw') == 1
assert s.count('v2 header %u raw') == 1
assert s.count('loopback probe') == 2
assert s.count('probe_sweep') == 3          # comment + definition + call
assert s.count('electrical_probe') == 2     # definition + call
assert s.count('reset_assert') == 4         # definition + reset_pulse + power_on + electrical_probe
assert s.count('reset_release') == 4        # definition + reset_pulse + power_on + electrical_probe
assert s.count('PULL_NONE') >= 6
lines = s.splitlines()
marks = {name: i + 1 for i, line in enumerate(lines)
         for name in ('bitbang_init(void)', 'bitbang_transfer(const', 'power_on(void)', 'electrical_probe(void)',
                      'probe_sweep(void)', 'bring_up(void)', 'chip_identify(struct', 'v2_read(uint8_t')
         if line.startswith(name)}
print('landmarks:', marks)
for a, b in zip(list(marks), list(marks)[1:]):
    pass
order = ['bitbang_init(void)', 'bitbang_transfer(const', 'v2_read(uint8_t', 'chip_identify(struct',
         'power_on(void)', 'electrical_probe(void)', 'probe_sweep(void)', 'bring_up(void)']
seen = [marks[k] for k in order]
assert seen == sorted(seen), f'function order broken: {marks}'
print(f'{DST}: all patches applied, all assertions green; {len(lines)} lines (v10b was 1549)')
