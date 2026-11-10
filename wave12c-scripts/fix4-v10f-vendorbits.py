#!/usr/bin/env python3
"""Wave 12c fix 4 (v10f): the vendor-practice deltas from the wave 12c
research report (docs/research-tcm-miso.md), on top of v10e's paced harvest:

 1  read transactions clock 0xFF on MOSI, not 0x00 -- the OPPO v1 driver, the
    OPPO common layer and the Syna HBP platform all memset(0xff) their read
    buffers (a 0x00 run is an "invalid command" bit pattern; the chip can
    abort its push mid-stream, which matches Boot #20's lone byte then
    filler). Boot-arg touch_read_fill=0 puts 0x00 back for an A/B.
 2  CS setup/hold: the Syna platform configures cs_setuptime=5000 ns and
    cs_holdtime=3000 ns; we drove CS and clocked immediately. CS low now
    waits 5 us before the first clock, the last bit waits 3 us before CS
    high again.
 3  the ATTN line (GPIO 21) goes into the loopback-probe log lines, so "the
    chip did not start" separates from "the read is wrong" on paper.

usage: fix4-v10f-vendorbits.py SOURCE_V10E OUT_V10F
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


swap('''static unsigned sweep_on = 1;
static unsigned v2_headers_shown;
''',
'''static unsigned sweep_on = 1;
static unsigned read_fill = 0xff;       /* boot-arg touch_read_fill: the MOSI byte of reads (the vendors clock 0xff) */
static unsigned v2_headers_shown;
''', 'read-fill knob')

swap('''	gpio_set(PIN_CS, false);
	for (uint32_t i = 0; i < length; i++) {
		uint8_t out = tx ? tx[i] : 0, in = 0;
''',
'''	gpio_set(PIN_CS, false);
	sleep_us(5);                            /* the Syna platform's cs_setuptime = 5000 ns */
	for (uint32_t i = 0; i < length; i++) {
		uint8_t out = tx ? tx[i] : (uint8_t)read_fill, in = 0;
''', 'CS setup time + 0xFF read fill')

swap('''			gpio_set(PIN_CLK, false);
		}
		if (rx) {
			rx[i] = in;
		}
	}
	gpio_set(PIN_CS, true);
	return true;
}''',
'''			gpio_set(PIN_CLK, false);
		}
		if (rx) {
			rx[i] = in;
		}
	}
	sleep_us(3);                            /* the Syna platform's cs_holdtime = 3000 ns */
	gpio_set(PIN_CS, true);
	return true;
}''', 'CS hold time')

swap('''	reset_assert();
	sleep_ms(20);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset asserted, rx:");
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\\n");
	reset_release();
	sleep_ms(80);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset released, rx:");
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\\n");''',
'''	reset_assert();
	sleep_ms(20);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset asserted, attn %u, rx:", gpio_get(PIN_INT));
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\\n");
	reset_release();
	sleep_ms(80);
	bitbang_transfer(pattern, echo, 9);
	printf("s3910: loopback probe, reset released, attn %u, rx:", gpio_get(PIN_INT));
	for (i = 0; i < 9; i++) {
		printf(" %02x", echo[i]);
	}
	printf("\\n");''', 'ATTN level in the loopback lines')

swap('''	PE_parse_boot_argn("touch_sweep", &sweep_on, sizeof(sweep_on));''',
'''	PE_parse_boot_argn("touch_sweep", &sweep_on, sizeof(sweep_on));
	PE_parse_boot_argn("touch_read_fill", &read_fill, sizeof(read_fill));''', 'touch_read_fill boot-arg')

open(DST, 'w').write(s)

# post-conditions
assert s.count('read_fill') == 5          # declaration + bitbang use + boot-arg parse + (0xff init + comment on same line)
assert s.count('sleep_us(5)') == 1
assert s.count('sleep_us(3)') == 1
assert s.count('attn %u') == 2
assert s.count('geni_transfer') == 2
lines = s.splitlines()
print('landmarks:', {name: i + 1 for i, line in enumerate(lines)
                     for name in ('v1_read(uint8_t', 'bitbang_transfer(const', 'bring_up(void)')
                     if line.startswith(name)})
print(f'{DST}: 5 patches applied, all assertions green; {len(lines)} lines (v10e was 1760)')
