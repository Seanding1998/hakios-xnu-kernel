#!/usr/bin/env python3
"""Wave 12c fix 3 (v10e): pace the v1 continuation harvest.

Boot #20 proved the last piece: the chip serves one nine-byte chunk per CS
frame ([a5 03][seven payload bytes]) but only re-arms a chunk on a ~20 ms
tick, and a frame clocked sooner reads back misaligned filler ("30 ff ff...")
-- which consumes nothing: the next well-timed frame gets the same chunk.
v10d's continuation frames fired immediately after the header frame, so every
one landed in the misaligned window and the identify failed exactly as
before. v10e:

  - paces EVERY v1 frame: the header frame retries (10 ms steps) until it
    opens with the 0xa5 marker, and every continuation frame waits 20 ms
    first, retrying up to 15 times;
  - harvests payload AND the trailing padding byte from the chunks' seven
    byte slots (a short tail chunk -- [a5 03][payload][5a][filler] -- fills
    exactly to the end, the filler is never taken);
  - tolerates the idle line arriving while only the padding is missing (the
    idle line itself carries 5a bytes);
  - logs the first 12 clean chunks and the first 6 misaligned ones.

usage: fix3-v10e-v1pacing.py SOURCE_V10D OUT_V10E
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


swap('''static unsigned v1_chunks_shown;
''',
'''static unsigned v1_chunks_shown;
static unsigned v1_dirty_shown;
''', 'dirty-chunk forensics counter')

swap('''	if (!spi_xfer(NULL, buf, V1_MIN_READ)) {
		return false;
	}
	if (buf[0] != V1_MARKER) {
		return false;
	}''',
'''	if (!spi_xfer(NULL, buf, V1_MIN_READ)) {
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
	}''', 'header frame retry pacing')

swap('''		while (got < *payload_length + 1) {                     /* the payload, then its padding byte */
			if (!spi_xfer(NULL, chunk, V1_MIN_READ)) {
				return false;
			}
			if (v1_chunks_shown < 12) {
				v1_chunks_shown++;
				printf("s3910: v1 chunk %u: %02x %02x %02x %02x %02x %02x %02x %02x %02x\\n", v1_chunks_shown,
				    chunk[0], chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7], chunk[8]);
			}
			if (chunk[0] != V1_MARKER || chunk[1] != STATUS_CONTINUED_READ) {
				return false;
			}
			for (uint32_t i = 2; i < V1_MIN_READ && got < *payload_length + 1; i++) {
				buf[MESSAGE_HEADER_SIZE + got] = chunk[i];
				got++;
			}
		}''',
'''		while (got < *payload_length + 1) {                     /* the payload, then its padding byte */
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
					    " %02x %02x %02x %02x %02x %02x %02x %02x %02x\\n", got, *payload_length, chunk[0],
					    chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7], chunk[8]);
				}
				if (++tries > 14) {
					return false;
				}
			}
			if (v1_chunks_shown < 12) {
				v1_chunks_shown++;
				printf("s3910: v1 chunk %u: %02x %02x %02x %02x %02x %02x %02x %02x %02x\\n", v1_chunks_shown,
				    chunk[0], chunk[1], chunk[2], chunk[3], chunk[4], chunk[5], chunk[6], chunk[7], chunk[8]);
			}
			for (uint32_t i = 2; i < V1_MIN_READ && got < *payload_length + 1; i++) {
				if (chunk[1] == STATUS_IDLE && chunk[i] != V1_PADDING) {
					continue;           /* the idle line: keep its 5a, skip the zeros around it */
				}
				buf[MESSAGE_HEADER_SIZE + got] = chunk[i];
				got++;
			}
		}''', 'paced continuation harvest')

open(DST, 'w').write(s)

# post-conditions
assert s.count('v1 chunk misaligned') == 1
assert s.count('v1 chunk %u:') == 1
assert s.count('v1_dirty_shown') == 3        # declaration + guard + increment
assert s.count('v1_chunks_shown') == 4
assert s.count('sleep_ms(20)') == 3          # chip_identify round + electrical_probe + the chunk pacing
assert s.count('memmove(buf + MESSAGE_HEADER_SIZE + *payload_length') == 0
assert s.count('geni_transfer') == 2
lines = s.splitlines()
print('landmarks:', {name: i + 1 for i, line in enumerate(lines)
                     for name in ('v1_read(uint8_t', 'bitbang_init(void)', 'bring_up(void)')
                     if line.startswith(name)})
print(f'{DST}: 3 patches applied, all assertions green; {len(lines)} lines (v10d was 1731)')
