#!/usr/bin/env python3
"""Wave 37 (v33): step 20 stops writing the a6xx address-mode register list.

Evidence (wave37-scripts/logdump-v26-wave37-w37v32gen1.bin, sha 971b3ebe): step 19 went GREEN
(TrustZone authenticated and started the zap shader -- the wave 36 handoff's step-12-class
acceptance, reached at 19 instead); step 20 then announced and died inside its register program:
the log's last line of this generation is the SIXTH of twelve "address mode: 64 bits" writes
(word 0xbe05 -> byte offset 0x3d2f814), the next put()'s print never landed, and the phone reset
(it was back in Android before the session's 600 s cap). A punished write.

That twelve-register list is the a6xx idiom (mainline a6xx_gpu.c writes exactly {0x842, 0xc01,
0x8601, 0x8e05, 0x9e01, 0xbe05, 0xa601, 0x9601, 0x0e00, 0xae01, 0xb601, 0xf810} x4 for 64-bit
addressing). The vendor gen7 driver -- this phone's own GPL source -- writes NONE of them:
gen7_start() (adreno_gen7.c:422) has no address-mode programming at all; gen7 is 64-bit native
and this table does not exist in gen7_reg.h. Wave 36's honest boundary (§9-1: steps 18-21's
a6xx-era hw_init tables were not re-derived for a730) is exactly this spot.

The machine-proven fix: the loop goes. Nothing replaces it -- the vendor writes nothing there.
Everything else in step 20 keeps its place for the next generation's localization (one
evidence-backed change per generation); for the record, the qsb_side writes were CHECKED against
the vendor and are gen7-legal (gen7_0_0_gbif_regs carries GBIF_QSB_SIDE0-3 = 0x71620, the very
values written; adreno-gpulist.h:1809).

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

REPL = [
    (
        """	static const uint32_t address_modes[] = { 0x0842, 0x0c01, 0x8601, 0x8e05, 0x9e01, 0xbe05, 0xa601, 0x9601, 0x0e00, 0xae01,
		                                  0xb601, 0xf810 };
	uint32_t blind = 0;""",
        """	uint32_t blind = 0;""",
    ),
    (
        """	for (unsigned i = 0; i < sizeof(address_modes) / sizeof(address_modes[0]); i++) {
		put(&gpu, "address mode: 64 bits", GPU_WORD(address_modes[i]), 1);
	}
	for (unsigned i = 0; i < 4; i++) {""",
        """	/* the a6xx twelve-register "address mode" list ends here: gen7 is 64-bit native, its own
	 * driver writes no such registers (gen7_start has none), and the sixth of them (word 0xbe05)
	 * reset this phone (the wave 37 v32 walk died at exactly that write). gen7_start instead
	 * configures UCHE_CMDQ_CONFIG and the NC_MODE bank encodings -- those come with their own
	 * evidence when the walk's later generations reach for them. */
	for (unsigned i = 0; i < 4; i++) {""",
    ),
]

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:60]!r}...")
    src = src.replace(old, new)

if "address_modes" in src:
    sys.exit("address_modes still referenced somewhere")

open(PATH, "w").write(src)
print("applied: the a6xx address-mode list is out of step 20 (gen7-native)")
