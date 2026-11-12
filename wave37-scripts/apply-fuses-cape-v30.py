#!/usr/bin/env python3
"""Wave 37 (v30): step 2 goes cape-native -- no fuse access at all.

Evidence:
  1. v29's logdump (wave37-scripts/logdump-v26-wave37-w37v29gen1.bin, sha 36bf2e03): the machine hung
     at step 2's first access -- the line set ends at the step-2 announce; get8's per-access prints
     are silent for step 2 (newest_step=3), so the hang is inside the first qfprom read at
     0x780000+0x4000+0x1e9 = 0x7841e9. Zero panic.
  2. Ground truth from the phone itself: /sys/firmware/fdt (the LIVE device tree, 1,200,263 B) has
     ZERO occurrences of "qfprom", "speed_bin", "efuse" -- this platform does not expose the fuses to
     the applications processor at all.
  3. The vendor's own driver agrees: drivers/gpu/msm/adreno.c adreno_read_speed_bin() returns 0 when
     nvmem_cell_get("speed_bin") comes back -ENOENT, and the phone's kgsl node carries the chip id
     directly (qcom,chipid = <0x7030002>). The vendor kernel never touches fuse hardware here.

So step 2 on cape = announce the finding, take the speed bin as 0 (exactly what the vendor does),
read nothing. The sc7280-style reads (0x7841e9/0x7841f5/0x7801e9) hang this phone's bus and are
retired. get8() loses its only caller -> marked unused. The qfprom block/defines stay in the file
(inert, documented) so the sc7280 numbers survive for sibling boards.

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

REPL = [
    (
        """/*
 * dt: qfprom@780000 with gpu_speed_bin@1e9 (two bytes, 8 bits from bit 5) and gpu_gaming_bin@1f5
 * (bit 5). Linux has the same cell 0x4000 further on, in the error-corrected copy of the fuses
 * (sc7280.dtsi: efuse@784000), and that is the copy it reads under this hypervisor on sibling
 * boards; so that one first.
 */
static struct block qfprom = { "qfprom", 0x00780000, 0x7000 };""",
        """/*
 * The fuses, as sc7280 has them (dt: qfprom@780000 with gpu_speed_bin@1e9, two bytes, 8 bits from
 * bit 5, and gpu_gaming_bin@1f5, bit 5; the error-corrected copy at 0x784000). CAPE HAS NONE OF
 * THIS: the phone's own live device tree (/sys/firmware/fdt) carries no qfprom, no speed_bin, no
 * efuse -- the platform does not expose the fuses to the applications processor, and the vendor's
 * own driver takes that as its answer (adreno_read_speed_bin returns 0 when the nvmem cell is
 * absent). The wave 37 probe hung inside the first read (0x7841e9): an address this phone's bus
 * does not decode. The block and the offsets stay here only as the sc7280 record; nothing reads
 * them on this phone.
 */
static struct block qfprom __attribute__((unused)) = { "qfprom", 0x00780000, 0x7000 };""",
    ),
    (
        """static uint32_t
get8(struct block *b, const char *name, uint32_t offset)""",
        """static uint32_t __attribute__((unused))
get8(struct block *b, const char *name, uint32_t offset)""",
    ),
    (
        """static bool
step_fuses(void)
{
	uint32_t bin, gaming;

	announce("read the GPU's fuses in the error-corrected copy (0x784000), which Linux reads");
	bin = get8(&qfprom, "speed bin, low", QFPROM_CORRECTED + QFPROM_GPU_SPEED_BIN);
	bin |= get8(&qfprom, "speed bin, high", QFPROM_CORRECTED + QFPROM_GPU_SPEED_BIN + 1) << 8;
	bin = bin >> 5 & 0xff;
	speed_bin = bin;
	gaming = get8(&qfprom, "gaming bin", QFPROM_CORRECTED + QFPROM_GPU_GAMING_BIN) >> 5 & 1;
	/* the cell of cape's QFPROM that holds the GPU speed bin is not the reference's [TODO-DEV]:
	 * both reads stay (they print what the fuses say), nothing is gated on the bin (the
	 * reference gates nothing either), and the chip id's own name is what the log shows */
	printf("adreno: %u: speed bin %u: an Adreno 730v3 (chip id 0x7030002); gaming bin %u\\n", step, bin,
	    gaming);

	announce("read the same fuses where the phone's device tree has them (0x780000)");
	bin = get8(&qfprom, "raw speed bin, low", QFPROM_GPU_SPEED_BIN);
	bin |= get8(&qfprom, "raw speed bin, high", QFPROM_GPU_SPEED_BIN + 1) << 8;
	printf("adreno: %u: raw speed bin %u\\n", step, bin >> 5 & 0xff);
	return true;
}""",
        """static bool
step_fuses(void)
{
	/* The fuse is not the applications processor's business on this platform: the phone's own
	 * live device tree has no qfprom at all, and the vendor's own driver reads no fuse either
	 * (its nvmem cell is absent, which it takes as speed bin 0). Reading the sc7280 addresses
	 * instead hangs the bus (the wave 37 probe: the machine stopped inside the first read,
	 * 0x7841e9, no panic). The chip id is not lost with the fuse: this phone's device tree
	 * declares it directly (qcom,chipid = 0x7030002), and nothing is gated on the bin. */
	announce("this platform exposes no fuses to the applications processor (the vendor's own driver skips them: the chip id comes from the device tree)");
	speed_bin = 0;
	printf("adreno: %u: speed bin 0 (not read): an Adreno 730v3 (chip id 0x7030002), as the device tree declares\\n", step);
	return true;
}""",
    ),
]

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:60]!r}...")
    src = src.replace(old, new)

# the retired reads must be gone from the step
for leftover in ("QFPROM_CORRECTED + QFPROM_GPU_SPEED_BIN", "get8(&qfprom"):
    if leftover in src:
        sys.exit(f"leftover fuse read in the tree: {leftover!r}")

open(PATH, "w").write(src)
print("applied: 3 replacements, 0 fuse reads left; step 2 is cape-native")
