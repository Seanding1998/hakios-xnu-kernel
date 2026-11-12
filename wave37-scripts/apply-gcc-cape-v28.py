#!/usr/bin/env python3
"""Wave 37 (v28): kodiak-ize the gcc block of hakios.adreno.c.

Evidence (wave37-scripts/logdump-v26-wave37-w37gen1.bin, sha 96bcfc4b):
the v27 probe hung inside the FIRST gcc read -- last line "about to read gcc pll votes
at 0x152000", no value line, zero panic. The driver carried sc7280 ("yupik") offsets;
this phone's gcc is cape ("qcom,cape-gcc", phk110.dts:786), whose driver is gcc-waipio.c
with gcc_cape_fixup (the K60 census corroborates cape machines shipping gcc-waipio.ko).

Every replacement is vendor-anchored (refs/kernel_oneplus_sm8475/drivers/clk/qcom/):
  gcc-waipio.c     gcc_gpu_gpll0_clk_src/div enable_reg 0x62000 BIT(15)/BIT(16)
                   gcc_gpu_cfg_ahb_clk 0x81004, gcc_gpu_memnoc_gfx_clk 0x81010,
                   gcc_gpu_snoc_dvm_gfx_clk 0x81018, gcc_ddrss_gpu_axi_clk 0x81154
                   (gcc_cape_fixup touches PLLs/sdcc/ufs only -- GPU offsets untouched)
  debugcc-waipio.c gcc_debug_mux debug_offset 0x72000, post_div_offset 0x72004,
                   cbcr_offset 0x72008; measure_clk_data xo_div4_cbcr 0x7200C,
                   ctl_reg 0x72038, status_reg 0x7203C; gcc_debug_mux_sels gpu_cc = 0x16E
                   (post_div register value stays div-1 == 1: cape val 2, clk-debug.c writes
                   post_div_val - 1 -- the driver's existing "divider - 1" semantics already
                   match, so only offsets move)
  phk110.dts:787   clock-controller@100000 reg = <0x100000 0x1f4200> -- the mapping grows
                   from 0x80000 (which could not even cover cape's 0x81xxx registers) to
                   the DTB's own size.
GCC_DISP_AHB_CBCR (0x27004, display_probe=1 only, not in the payload cmdline) is left as
is with a TODO note -- no cape value was established this wave.

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

REPL = [
    # the comment block: cape, not yupik; the vendor source named correctly
    (
        """ * dt: clock-controller@100000 (qcom,yupik-gcc). The GPU's clocks there, by the names the GPU's
 * nodes give them: gcc_gpu_memnoc_gfx and gcc_gpu_snoc_dvm_gfx (its two bus connections),
 * "axi_clk" = gcc_ddrss_gpu_axi (memory), gcc_gpu_cfg_ahb (the registers of its clock controller);
 * and the two taps of the 600 MHz PLL that its clock controller takes as inputs. None of them is
 * among that node's protected-clocks, the ones the hypervisor keeps to itself. Offsets:
 * gcc-sc7280.c. The touch screen driver uses this controller too.
 */""",
        """ * dt: clock-controller@100000 (qcom,cape-gcc; this phone's own device tree). The GPU's clocks
 * there, by the names the GPU's nodes give them: gcc_gpu_memnoc_gfx and gcc_gpu_snoc_dvm_gfx
 * (its two bus connections), "axi_clk" = gcc_ddrss_gpu_axi (memory), gcc_gpu_cfg_ahb (the
 * registers of its clock controller); and the two taps of the PLL that its clock controller
 * takes as inputs. None of them is among that node's protected-clocks, the ones the hypervisor
 * keeps to itself. Offsets: gcc-waipio.c, whose gcc_cape_fixup is what binds to "qcom,cape-gcc"
 * (it leaves every GPU clock's address alone). The wave 37 probe hung reading the sc7280 pll
 * votes at 0x152000; this phone's bus names the cape registers, a register-class apart.
 */""",
    ),
    (
        """static struct block gcc = { "gcc", 0x00100000, 0x80000 };""",
        """static struct block gcc = { "gcc", 0x00100000, 0x1f4200 };    /* the DTB's own reg size */""",
    ),
    (
        """#define GCC_PLL_VOTE            0x52000         /* bit 15: gcc_gpu_gpll0_clk_src (600 MHz), bit 16: ..._div_clk_src (300 MHz) */
#define GCC_PLL_VOTE_GPU_DIV    (1u << 16)
#define GCC_GPU_CFG_AHB_CBCR    0x71004
#define GCC_GPU_MEMNOC_GFX_CBCR 0x7100c
#define GCC_GPU_SNOC_DVM_GFX_CBCR 0x71018
#define GCC_DDRSS_GPU_AXI_CBCR  0x71154""",
        """#define GCC_PLL_VOTE            0x62000         /* bit 15: gcc_gpu_gpll0_clk_src, bit 16: ..._div_clk_src */
#define GCC_PLL_VOTE_GPU_DIV    (1u << 16)
#define GCC_GPU_CFG_AHB_CBCR    0x81004
#define GCC_GPU_MEMNOC_GFX_CBCR 0x81010
#define GCC_GPU_SNOC_DVM_GFX_CBCR 0x81018
#define GCC_DDRSS_GPU_AXI_CBCR  0x81154""",
    ),
    (
        """ * result as "clk_measure"; registers, selections and procedure are its debugcc-yupik.c and
 * clk-debug.c (mainline Linux has no counterpart).""",
        """ * result as "clk_measure"; registers, selections and procedure are its debugcc-waipio.c and
 * clk-debug.c (mainline Linux has no counterpart); this phone's selections are cape's.
 """,
    ),
    (
        """#define GCC_DEBUG_MUX           0x62000         /* [9:0] which clock goes to the counter */
#define GCC_DEBUG_MUX_GPUCC     0x146           /* ... the debug output of the GPU's clock controller */
#define GCC_DEBUG_DIV           0x62004         /* [3:0] divider - 1; both controllers divide by 2 */
#define GCC_DEBUG_CBCR          0x62008
#define GCC_XO_DIV4_CBCR        0x6200c         /* the counter's time base: the crystal / 4, 4.8 MHz */
#define GCC_MEASURE_CTL         0x62038         /* [19:0] how many ticks of the time base to count for */""",
        """#define GCC_DEBUG_MUX           0x72000         /* [9:0] which clock goes to the counter */
#define GCC_DEBUG_MUX_GPUCC     0x16e           /* ... the debug output of the GPU's clock controller */
#define GCC_DEBUG_DIV           0x72004         /* [3:0] divider - 1; both controllers divide by 2 */
#define GCC_DEBUG_CBCR          0x72008
#define GCC_XO_DIV4_CBCR        0x7200c         /* the counter's time base: the crystal / 4, 4.8 MHz */
#define GCC_MEASURE_CTL         0x72038         /* [19:0] how many ticks of the time base to count for */""",
    ),
    (
        """#define GCC_MEASURE_STATUS      0x6203c         /* [24:0] the count */""",
        """#define GCC_MEASURE_STATUS      0x7203c         /* [24:0] the count */""",
    ),
    (
        """#define GCC_DISP_AHB_CBCR       0x27004""",
        """#define GCC_DISP_AHB_CBCR       0x27004         /* [TODO-DEV: cape value unknown; display_probe=1 only] */""",
    ),
]

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:60]!r}...")
    src = src.replace(old, new)

# no sc7280 gpu offsets may survive in the gcc defines
# (0x62000 is exempt: it is the CAPE pll-vote offset the fix itself introduces)
for leftover in ("0x52000", "0x71004", "0x7100c", "0x71018", "0x71154",
                 "0x146 ", "0x62004 ", "0x62008\n", "0x6200c ", "0x62038 ", "0x6203c "):
    if leftover in src:
        sys.exit(f"leftover sc7280 offset in the tree: {leftover!r}")

open(PATH, "w").write(src)
print("applied: 5 replacements, 0 leftovers; gcc block is cape now")
