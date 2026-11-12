#!/usr/bin/env python3
"""Wave 37 (v32): zap_header() understands cape's three-segment a730_zap.mdt.

Evidence (wave37-scripts/logdump-v26-wave37-w37v31a.bin, sha a99956a2): the v31 production walk
reached step 19 with steps 14-18 green (GMU fw 4.0.7 loaded and running, queues up, the 3D core
powered and answering at 283 MHz, SQE loaded, SMMU context set), then:
    an ELF header of 3 segments, 148 bytes with its table, then 3416 bytes; by the table, 2236 of hashes
    the file is not the header followed by the hashes alone: not what TrustZone takes
cape's a730_zap.mdt (pulled in wave 36, sha 9df98f79) has THREE segments: 0 = the ELF header and
table themselves (148 bytes), 1 = the code (a730_zap.b01, 2236 bytes -- a separate file, loaded to
its address in step 19's later calls), 2 = THE HASHES (0xd58 = 3416 bytes). The file on disk is the
header and the table followed by the hashes alone: 148 + 3416 = 3564 = the actual file size. The
check only failed because it read the hash size from segment 1 -- sc7280's two-segment layout, in
which the hashes were the second segment -- and so compared 2236 against the trailing 3416.

The fix generalizes the accounting: the hash segment is whichever segment's p_filesz makes
header + table + p_filesz == the file size. sc7280's layout still satisfies it (its segment 1 does).

Also refreshed: the step-5 announce line's example offsets (they still named the sc7280 debug
registers; the accesses themselves were already cape's, as the v30/v31 logs show).

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

REPL = [
    (
        """	memcpy(&hashes, header + 52 + 32 + 16, sizeof(hashes));
	printf("adreno: %u: an ELF header of %u segments, %u bytes with its table, then %llu bytes; by the table, %u of hashes\\n",
	    step, segments, 52 + 32 * segments, size - (52 + 32 * segments), hashes);
	if (52 + 32 * segments + (uint64_t)hashes != size) {
		printf("adreno: %u: the file is not the header followed by the hashes alone: not what TrustZone takes\\n", step);
		return false;
	}""",
        """	/* the hashes are whichever segment's file size completes the file: cape's a730_zap.mdt has
	 * three segments (0 = the header itself, 1 = the code in a730_zap.b01, 2 = the hashes) and its
	 * file is the header and the table followed by segment 2 alone; sc7280's two-segment layout had
	 * them in segment 1, which this same accounting still finds */
	hashes = 0;
	for (uint32_t i = 0; i < segments; i++) {
		uint32_t filesz;
		memcpy(&filesz, header + 52 + 32 * i + 16, sizeof(filesz));
		if (52 + 32 * segments + (uint64_t)filesz == size) {
			hashes = filesz;
			break;
		}
	}
	printf("adreno: %u: an ELF header of %u segments, %u bytes with its table, then %llu bytes; by the table, %u of hashes\\n",
	    step, segments, 52 + 32 * segments, size - (52 + 32 * segments), hashes);
	if (52 + 32 * segments + (uint64_t)hashes != size) {
		printf("adreno: %u: no segment's size completes the file: not the header followed by the hashes alone, not what TrustZone takes\\n", step);
		return false;
	}""",
    ),
    (
        """	announce("measure the GPU block's clocks with the SoC's frequency counter (debug registers at gcc 0x162000.., "
	    "gpucc 0x3d910fc, 0x3d91100, 0x3d91568)");""",
        """	announce("measure the GPU block's clocks with the SoC's frequency counter (debug registers at gcc 0x172000.., "
	    "gpucc 0x3d99270, 0x3d99274, 0x3d99564)");""",
    ),
]

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:60]!r}...")
    src = src.replace(old, new)

if "hashes = 0;" not in src or "uint32_t i = 0; i < segments" not in src:
    sys.exit("the generalized hash accounting did not land")

open(PATH, "w").write(src)
print("applied: zap_header reads cape's 3-segment layout; step-5 announce refreshed")
