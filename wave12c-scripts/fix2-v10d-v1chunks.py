#!/usr/bin/env python3
"""Wave 12c fix 2 (v10d): v1_read threw away every TouchComm v1 message
longer than five payload bytes -- and Boot #19's raw-byte forensics show the
chip has been answering correctly all along (round 1: a5 10 1c 00 01 01 53
33 39 = REPORT_IDENTIFY, 28-byte payload, version 1, application mode, part
number "S391..."; rounds 2-3: a5 03 continuation chunks; later: the a5 00
00 00 5a idle line).

Two wire facts from the b19 evidence:
  - this chip answers exactly NINE bytes per CS frame: a continuation frame
    reads back [a5 03][seven payload bytes]; the rest of a longer frame is
    idle-high filler (ff);
  - the old code clocked ONE long frame (rest+2 bytes) and then checked the
    padding at buf[4+len] -- but the padding it had read landed at
    buf[V1_MIN_READ+rest+1], two positions further, so the check bit stale
    payload and v1_read returned false for every such message. The identify
    was never accepted, protocol fell through to v2, and the probe said "no
    answer" while the answer sat on the wire.

v10d: harvest the payload and the trailing padding byte from nine-byte
continuation frames ([a5 03][7 bytes] each). Works for generous chips too
(the frames just come back full). Every harvested frame's raw bytes go to
the log (first 12), so Boot #20 either shows the handshake or shows exactly
why not.

usage: fix2-v10d-v1chunks.py SOURCE_V10C OUT_V10D
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


# the chunk-print counter, next to v2_headers_shown
swap('''static unsigned sweep_on = 1;
static unsigned v2_headers_shown;
''',
'''static unsigned sweep_on = 1;
static unsigned v2_headers_shown;
static unsigned v1_chunks_shown;
''', 'v1 chunk forensics counter')

# the continuation branch: one long frame -> nine-byte frames, harvested
swap('''	if (total > V1_MIN_READ) {
		uint32_t rest = total - V1_MIN_READ;

		if (!spi_xfer(NULL, buf + V1_MIN_READ, rest + 2)) {
			return false;
		}
		if (buf[V1_MIN_READ] != V1_MARKER || buf[V1_MIN_READ + 1] != STATUS_CONTINUED_READ) {
			return false;
		}
		memmove(buf + MESSAGE_HEADER_SIZE + *payload_length - (rest - 1), buf + V1_MIN_READ + 2, rest - 1);
	} else if (buf[total - 1] != V1_PADDING) {
		return false;
	}''',
'''	if (total > V1_MIN_READ) {
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
		}
	} else if (buf[total - 1] != V1_PADDING) {
		return false;
	}''', 'v1 continuation: nine-byte chunk harvest')

open(DST, 'w').write(s)

# post-conditions
assert s.count('memmove(buf + MESSAGE_HEADER_SIZE + *payload_length - (rest - 1)') == 0, 'the old memmove survived'
assert s.count('v1 chunk %u:') == 1
assert s.count('v1_chunks_shown') == 4        # declaration + print guard + increment + printf arg
assert s.count('geni_transfer') == 2          # untouched by this fix
lines = s.splitlines()
marks = {name: i + 1 for i, line in enumerate(lines)
         for name in ('v1_read(uint8_t', 'bitbang_init(void)', 'bring_up(void)')
         if line.startswith(name)}
print('landmarks:', marks)
print(f'{DST}: 2 patches applied, all assertions green; {len(lines)} lines (v10c was 1711)')
