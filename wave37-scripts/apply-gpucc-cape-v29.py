#!/usr/bin/env python3
"""Wave 37 (v29): kodiak-ize the gpucc block of hakios.adreno.c (the same error class as the
gcc fix the v28 generation proved: the driver carried sc7280 ("yupik") offsets; this phone's
clock controllers are cape, "qcom,cape-gpucc" (phk110.dts:838, reg 0x3d90000+0xa000), whose
vendor driver is gpucc-waipio.c bound by gpu_cc_cape_fixup, with the debug side in
debugcc-waipio.c ("qcom,waipio-debugcc" per the phone's own DTB) and the GDSC/syscon addresses
in the phone's own DTB.

Every replacement is vendor- or DTB-anchored (refs/kernel_oneplus_sm8475/drivers/clk/qcom/
and Mu-Silicium/Resources/DTBs/phk110.dts):
  block size        0x9000 -> 0xa000            DTB reg
  PLL1_MODE         0x0100 -> 0x1000            gpucc-waipio.c gpu_cc_pll1 .offset = 0x1000
                    (PLL0 .offset = 0x0 -- unchanged)
  CXO_AON_CBCR      0x1004 -> 0x9004            gpucc-waipio.c enable_reg
  GX_SW_RESET       0x1008 -> 0x9058            DTB syscon@3d99058
  GX_GDSCR          0x100c -> 0x905c            DTB gdsc@3d9905c
  GX_GMU_CBCR       0x1064 -> 0x90bc            gpucc-waipio.c enable_reg
  CX_GDSCR          0x106c -> 0x9108            DTB gdsc@3d99108
  AHB_CBCR          0x1078 -> 0x911c            gpucc-waipio.c enable_reg
  CX_GMU_CBCR       0x1098 -> 0x913c            gpucc-waipio.c enable_reg
  CXO_CBCR          0x109c -> 0x9144            gpucc-waipio.c enable_reg
  GMU_RCGR          0x1120 -> 0x9318            gpucc-waipio.c gpu_cc_gmu_clk_src .cmd_rcgr
  HUB_AON_CBCR      0x1178 -> 0x93e8            gpucc-waipio.c enable_reg
  HUB_RCGR          0x117c -> 0x93ec            gpucc-waipio.c gpu_cc_hub_clk_src .cmd_rcgr
  HUB_CX_INT_CBCR   0x1204 -> 0x9148            gpucc-waipio.c enable_reg
  CX_HW_CTRL        0x1540 -> 0x953c            DTB syscon@3d9953c
  GX_DOMAIN_MISC    0x158c -> 0x9504            DTB syscon@3d99504
  SMMU_VOTE_CBCR    0x5000 -> 0x7000            gpucc-waipio.c hlos1_vote_gpu_smmu enable_reg
  DEBUG_DIV         0x10fc -> 0x9270            debugcc-waipio.c gpu_cc_debug_mux .post_div_offset
  DEBUG_CBCR        0x1100 -> 0x9274            debugcc-waipio.c .cbcr_offset
  DEBUG_MUX         0x1568 -> 0x9564            debugcc-waipio.c .debug_offset
  DEBUG_GX_GFX3D    0x0d  -> 0x25               cape sels: measure_only_gpu_cc_cx_gfx3d_clk (cape has
                                                no plain gx_gfx3d debug view; mnd1x_0_gfx3d = 0x29 is
                                                the MND-divided monitor)
  DEBUG_GX_GMU      0x11  -> 0x12               cape sels gpu_cc_gx_gmu_clk
  DEBUG_AHB         0x12  -> 0x16               cape sels gpu_cc_ahb_clk
  DEBUG_CX_GMU      0x1a  -> 0x1e               cape sels gpu_cc_cx_gmu_clk
  DEBUG_CXO         0x1b  -> 0x1f               cape sels gpu_cc_cxo_clk
  DEBUG_HUB_CX_INT  0x1c  -> 0x20               cape sels gpu_cc_hub_cx_int_clk
  DEBUG_HUB_AON     0x27  -> 0x2f               cape sels gpu_cc_hub_aon_clk
  DEBUG_CXO_AON     0x0b  (unchanged; cape sels gpu_cc_cxo_aon_clk = 0xB)
Left alone, annotated: GPUCC_CB_CBCR (cape has no cb clock at all -- gpucc-waipio.c carries none;
the sc7280 offset stays with a TODO note: the step-3 READ of it decodes inside the map and is
harmless, the step-5 WRITE (clock_on) is unresolved until the walk reaches step 5) and
GPUCC_DEBUG_CB (same story for the debug selection list).

Each anchor must appear exactly once. Never run twice.
"""
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
src = open(PATH, "r").read()

REPL = [
    (
        """/*
 * dt: clock-controller@3d90000 (qcom,yupik-gpucc), 0x9000 long; offsets: gpucc-sc7280.c. Its
 * registers answer only while gcc_gpu_cfg_ahb runs, which Linux turns on for good when it
 * starts (gcc-sc7280.c, the end of the probe function).
 */
static struct block gpucc = { "gpucc", 0x03d90000, 0x9000 };""",
        """/*
 * dt: clock-controller@3d90000 (qcom,cape-gpucc), 0xa000 long; offsets: gpucc-waipio.c, whose
 * gpu_cc_cape_fixup binds to this phone's compatible (the GDSC and syscon addresses are the
 * phone's own device tree's, the debug side debugcc-waipio.c, the mux selections cape's).
 * Its registers answer only while gcc_gpu_cfg_ahb runs, which Linux turns on for good when it
 * starts (gcc-waipio.c, the end of the probe function).
 */
static struct block gpucc = { "gpucc", 0x03d90000, 0xa000 };""",
    ),
    (
        """#define GPUCC_PLL0_MODE         0x0000          /* the 3D core's PLL: bit 31 locked, bit 0 output on; +4: times 19.2 MHz */
#define GPUCC_PLL1_MODE         0x0100          /* a 500 MHz PLL, an alternative source for the GMU's clock */
#define GPUCC_CXO_AON_CBCR      0x1004
#define GPUCC_GX_SW_RESET       0x1008          /* dt: gpu_gx_sw_reset */
#define GPUCC_GX_GDSCR          0x100c          /* dt: gpu_gx_gdsc, the 3D core's power switch: the GMU's to operate */
#define GPUCC_GX_GMU_CBCR       0x1064
#define GPUCC_CX_GDSCR          0x106c          /* dt: gpu_cx_gdsc */
#define GPUCC_AHB_CBCR          0x1078          /* gpu_cc_ahb_clk: the register bus inside the GPU block */
#define GPUCC_CX_GMU_CBCR       0x1098          /* gpu_cc_cx_gmu_clk: the GMU */
#define GPUCC_CXO_CBCR          0x109c          /* gpu_cc_cxo_clk: the crystal, for the GMU's timers */
#define GPUCC_GMU_RCGR          0x1120          /* gpu_cc_gmu_clk_src: +0 command, +4 source and divider */
#define GPUCC_CB_CBCR           0x1170          /* gpu_cc_cb_clk: Linux keeps it on always */
#define GPUCC_HUB_AON_CBCR      0x1178          /* gpu_cc_hub_aon_clk */
#define GPUCC_HUB_RCGR          0x117c          /* gpu_cc_hub_clk_src */
#define GPUCC_HUB_CX_INT_CBCR   0x1204          /* gpu_cc_hub_cx_int_clk */
#define GPUCC_CX_HW_CTRL        0x1540          /* dt: gpu_cx_hw_ctrl: bit 31 is where the vendor's driver sees CX come on */
#define GPUCC_GX_DOMAIN_MISC    0x158c          /* dt: gpu_gx_domain_addr */
#define GPUCC_SMMU_VOTE_CBCR    0x5000          /* gpu_cc_hlos1_vote_gpu_smmu_clk: our vote for the SMMU's clock */""",
        """#define GPUCC_PLL0_MODE         0x0000          /* the 3D core's PLL: bit 31 locked, bit 0 output on; +4: times 19.2 MHz */
#define GPUCC_PLL1_MODE         0x1000          /* a 500 MHz PLL, an alternative source for the GMU's clock */
#define GPUCC_CXO_AON_CBCR      0x9004
#define GPUCC_GX_SW_RESET       0x9058          /* dt: syscon@3d99058 */
#define GPUCC_GX_GDSCR          0x905c          /* dt: gdsc@3d9905c, the 3D core's power switch: the GMU's to operate */
#define GPUCC_GX_GMU_CBCR       0x90bc
#define GPUCC_CX_GDSCR          0x9108          /* dt: gdsc@3d99108 */
#define GPUCC_AHB_CBCR          0x911c          /* gpu_cc_ahb_clk: the register bus inside the GPU block */
#define GPUCC_CX_GMU_CBCR       0x913c          /* gpu_cc_cx_gmu_clk: the GMU */
#define GPUCC_CXO_CBCR          0x9144          /* gpu_cc_cxo_clk: the crystal, for the GMU's timers */
#define GPUCC_GMU_RCGR          0x9318          /* gpu_cc_gmu_clk_src: +0 command, +4 source and divider */
#define GPUCC_CB_CBCR           0x1170          /* gpu_cc_cb_clk: Linux keeps it on always [TODO-DEV: cape has no cb clock -- gpucc-waipio.c carries none; the read here decodes, the step-5 write is unresolved] */
#define GPUCC_HUB_AON_CBCR      0x93e8          /* gpu_cc_hub_aon_clk */
#define GPUCC_HUB_RCGR          0x93ec          /* gpu_cc_hub_clk_src */
#define GPUCC_HUB_CX_INT_CBCR   0x9148          /* gpu_cc_hub_cx_int_clk */
#define GPUCC_CX_HW_CTRL        0x953c          /* dt: syscon@3d9953c: bit 31 is where the vendor's driver sees CX come on */
#define GPUCC_GX_DOMAIN_MISC    0x9504          /* dt: syscon@3d99504 */
#define GPUCC_SMMU_VOTE_CBCR    0x7000          /* gpu_cc_hlos1_vote_gpu_smmu_clk: our vote for the SMMU's clock */""",
    ),
    (
        """#define GPUCC_DEBUG_DIV         0x10fc
#define GPUCC_DEBUG_CBCR        0x1100
#define GPUCC_DEBUG_MUX         0x1568          /* [7:0] which of the GPU's clocks */
#define GPUCC_DEBUG_CXO_AON     0x0b
#define GPUCC_DEBUG_GX_GFX3D    0x0d            /* the 3D core's own clock */
#define GPUCC_DEBUG_GX_GMU      0x11
#define GPUCC_DEBUG_AHB         0x12
#define GPUCC_DEBUG_CX_GMU      0x1a
#define GPUCC_DEBUG_CXO         0x1b
#define GPUCC_DEBUG_HUB_CX_INT  0x1c
#define GPUCC_DEBUG_CB          0x26
#define GPUCC_DEBUG_HUB_AON     0x27""",
        """#define GPUCC_DEBUG_DIV         0x9270
#define GPUCC_DEBUG_CBCR        0x9274
#define GPUCC_DEBUG_MUX         0x9564          /* [7:0] which of the GPU's clocks */
#define GPUCC_DEBUG_CXO_AON     0x0b
#define GPUCC_DEBUG_GX_GFX3D    0x25            /* the 3D core's own clock (cape: measure_only cx_gfx3d) */
#define GPUCC_DEBUG_GX_GMU      0x12
#define GPUCC_DEBUG_AHB         0x16
#define GPUCC_DEBUG_CX_GMU      0x1e
#define GPUCC_DEBUG_CXO         0x1f
#define GPUCC_DEBUG_HUB_CX_INT  0x20
#define GPUCC_DEBUG_CB          0x26            /* [TODO-DEV: cape has no cb clock; 0x26 = the cx_gfx3d slave measure view] */
#define GPUCC_DEBUG_HUB_AON     0x2f""",
    ),
]

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:60]!r}...")
    src = src.replace(old, new)

# no sc7280 gpucc offsets may survive in the gpucc defines
for leftover in ("0x1004\n", "0x1008 ", "0x100c ", "0x1064\n", "0x106c ", "0x1078 ", "0x1098 ",
                 "0x109c ", "0x1120 ", "0x1178 ", "0x117c ", "0x1204 ", "0x1540 ", "0x158c ",
                 "0x10fc", "0x1568 ", "0x5000 "):
    if leftover in src:
        sys.exit(f"leftover sc7280 gpucc offset in the tree: {leftover!r}")

open(PATH, "w").write(src)
print("applied: 3 replacement blocks (all gpucc defines), 0 leftovers; gpucc block is cape now")
