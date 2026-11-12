#!/usr/bin/env python3
"""Wave 36: apply the a6xx(642L) -> gen7(730) parameter layer to drivers/gpu/hakios.adreno.c.

Wave 35's patch skeletons (scratch/wave35/patches/0001..0005) said what to change and left
[TODO-DEV] marks. This applier lands the values: every replacement must match exactly once
(asserts), the original is kept beside the file, and a combined unified diff is written to
the patches/ directory next to this script for the record.

Evidence marks (as in wave 35): [DTB] our device tree, [VENDOR] the phone's own vendor gen7
kgsl driver (refs/kernel_oneplus_sm8475, GPL, source-reference only), [UP] mainline msm,
[PONG] the pong/zizhan bring-up notes, [W36] this wave's own forensic (the pulled firmware
files, the ELF program headers of a730_zap.mdt).

usage (in WSL): python3 wave36-scripts/apply-adreno-v25.py
"""
import difflib
import io
import os
import sys

DRIVER = os.path.expanduser("~/hakios/kernel/drivers/gpu/hakios.adreno.c")
HERE = os.path.dirname(os.path.abspath(__file__))

R = []  # (tag, old, new)


def rep(tag, old, new, count=1):
    R.append((tag, old, new, count))


# ---- 0002: address map -----------------------------------------------------

rep("0002-gmu-block",
"""/*
 * dt: qcom,gmu "kgsl_gmu_reg" at 0x3d6a000, 0x34000 long. Offsets in a6xx_gmu.xml are in words.
 */
static struct block gmu = { "gmu", 0x03d6a000, 0x34000 };""",
"""/*
 * dt: qcom,gmu@3d69000 reg[0] "gmu" at 0x3d68000, 0x37000 long (phk110.dts:20301; the node's
 * unit address is 3d69000, the window begins one page earlier: the vendor numbering). Words
 * again -- and the vendor gen7 map (refs/kernel_oneplus_sm8475 drivers/gpu/msm gen7_reg.h)
 * carries every register of the a6xx layout 0x800 words further into this window; more than
 * twenty of its word addresses check out as a6xx + 0x800 (CM3 0x50xx->0x58xx, HFI 0x518x->
 * 0x598x, GENERAL 0x51cc->0x59cc, AO/RSCC-ctrl 0x93xx->0x9bxx, ICACHE 0x4c00->0x5400), which
 * is how the offsets below were moved.
 */
static struct block gmu = { "gmu", 0x03d68000, 0x37000 };""")

rep("0002-gmu-defines",
"""#define GMU_DTCM                GMU_WORD(0x1c00)        /* the processor's 16K of data memory (its code: 0x0c00) */
#define GMU_DTCM_VERSIONS       GMU_WORD(0x1c00 + 0xff8) /* five words where loaded firmware carries its versions */
#define GMU_CM3_SYSRESET        GMU_WORD(0x5000)        /* 1: the processor is held in reset */
#define GMU_CM3_BOOT_CONFIG     GMU_WORD(0x5001)
#define GMU_CM3_FW_INIT_RESULT  GMU_WORD(0x501c)        /* 0xbabeface once firmware has started */
#define GMU_CM3_CFG             GMU_WORD(0x502d)
#define GMU_ALWAYS_ON_COUNTER_L GMU_WORD(0x5088)        /* counts the 19.2 MHz crystal */
#define GMU_ALWAYS_ON_COUNTER_H GMU_WORD(0x5089)
#define GMU_SPTPRAC_PWR_CLK_STATUS GMU_WORD(0x50d0)     /* bit 6: the 3D core has no power, bit 7: no clock */
#define GMU_RPMH_POWER_STATE    GMU_WORD(0x50ec)
#define GMU_HFI_CTRL_STATUS     GMU_WORD(0x5180)
#define GMU_HFI_VERSION_INFO    GMU_WORD(0x5181)
#define GMU_GENERAL_7           GMU_WORD(0x51cc)
#define GMU_AO_HOST_INTERRUPT_STATUS GMU_WORD(0x9305)
#define GMU_RSCC_CONTROL_ACK    GMU_WORD(0x9308)
#define GMU_AO_GPU_CX_BUSY_STATUS GMU_WORD(0x930c)
#define GMU_AHB_FENCE_STATUS    GMU_WORD(0x9313)""",
"""#define GMU_DTCM                GMU_WORD(0x2400)        /* the processor's 16K of data memory (its code: 0x1400) */
#define GMU_DTCM_VERSIONS       GMU_WORD(0x2400 + 0xff8) /* five words where loaded firmware carries its versions */
#define GMU_CM3_SYSRESET        GMU_WORD(0x5800)        /* 1: the processor is held in reset */
#define GMU_CM3_BOOT_CONFIG     GMU_WORD(0x5801)
#define GMU_CM3_FW_INIT_RESULT  GMU_WORD(0x581c)        /* 0xbabeface once firmware has started */
#define GMU_CM3_CFG             GMU_WORD(0x582d)
#define GMU_ALWAYS_ON_COUNTER_L GMU_WORD(0x5888)        /* counts the 19.2 MHz crystal */
#define GMU_ALWAYS_ON_COUNTER_H GMU_WORD(0x5889)
#define GMU_SPTPRAC_PWR_CLK_STATUS GMU_WORD(0x58d0)     /* bit 6: the 3D core has no power, bit 7: no clock */
#define GMU_RPMH_POWER_STATE    GMU_WORD(0x58ec)
#define GMU_HFI_CTRL_STATUS     GMU_WORD(0x5980)
#define GMU_HFI_VERSION_INFO    GMU_WORD(0x5981)
#define GMU_GENERAL_7           GMU_WORD(0x59cc)
#define GMU_GENERAL_8           GMU_WORD(0x59cd)        /* at start: where the GMU's log is, its pages - 1 */
#define GMU_GENERAL_9           GMU_WORD(0x59ce)        /* how far the log had been written before (the wptr retention) */
#define GMU_GENERAL_10          GMU_WORD(0x59cf)        /* at start: which GPU this is (the chip id) */
#define GMU_AO_HOST_INTERRUPT_STATUS GMU_WORD(0x9b05)
#define GMU_RSCC_CONTROL_ACK    GMU_WORD(0x9b08)
#define GMU_AO_GPU_CX_BUSY_STATUS GMU_WORD(0x9b0c)
#define GMU_AHB_FENCE_STATUS    GMU_WORD(0x9b13)""")

rep("0002-cx-misc",
"""static struct block cx_misc = { "cx_misc", 0x03d9e000, 0x1000 };
#define CX_MISC_SYSTEM_CACHE_CNTL_0 (4 * 1)
#define CX_MISC_SYSTEM_CACHE_CNTL_1 (4 * 2)""",
"""static struct block cx_misc = { "cx_misc", 0x03d9e000, 0x1000 };
#define CX_MISC_SYSTEM_CACHE_CNTL_0 (4 * 1)
#define CX_MISC_SYSTEM_CACHE_CNTL_1 (4 * 2)
#define CX_MISC_TCM_RET_CNTL    (4 * 0x39)      /* gen7 keeps the TCMs on through the CX manager (a6xx voted GENERAL_7) [VENDOR] */""")

rep("0002-gmu-announce",
'announce("read registers of the GMU (0x3d6a000): the first words from the GPU block itself");',
'announce("read registers of the GMU (0x3d68000): the first words from the GPU block itself");')

rep("0002-rscc",
"""/*
 * dt: qcom,kgsl-3d0 "rscc" at 0x3de0000: the same kind of command slots through which this
 * kernel asks RPMh for the touch screen's supply, but the GMU's own; through them its firmware
 * raises the 3D core's rail. Offsets in words: a6xx_gmu.xml, domain A6XX_RSCC.
 */
static struct block rscc = { "rscc", 0x03de0000, 0x2000 };""",
"""/*
 * dt: kgsl reg[2] "rscc" at 0x3d50000, 0x10000 long (phk110.dts:20055; redwood said 0x3de0000):
 * the same kind of command slots through which this kernel asks RPMh for the touch screen's
 * supply, but the GMU's own; through them its firmware raises the 3D core's rail. Offsets in
 * words, unchanged from a6xx: every RSCC offset the vendor gen7_reg.h lists (PDC slave id 0xb,
 * seq busy 0x101, seq memory 0x180, TCS status 0x346) is the a6xx number. So is the program
 * the GMU's side loads (gen7_load_rsc_ucode: the same five words, the same PDC start/match
 * 0x4520/0x4510/0x4514, slave id 1) -- the only difference found is hidden_tcs_cmd2_data
 * 0x80000000 where a650-and-later wrote 0x80000021 (step 16).
 */
static struct block rscc = { "rscc", 0x03d50000, 0x10000 };""")

rep("0002-smmu",
""" * the vendor's driver leaves its stream table as it finds it. Its streams (dt: qcom,kgsl-iommu
 * and qcom,gmu, "iommus"): 0 the GPU, 1 its low-priority twin, 2 secure content, 5 the GMU.
 * The global registers here are the ones the hypervisor imitates; offsets: arm-smmu.h.
 */
static struct block smmu = { "smmu", 0x03da0000, 0x20000 };""",
""" * the vendor's driver leaves its stream table as it finds it. Its streams (dt: qcom,kgsl-iommu
 * and qcom,gmu, "iommus"): 0 the GPU, 1 its low-priority twin (gen7's LPAC), 2 secure content,
 * 5 the GMU. The window is 0x40000 on this phone (phk110.dts kgsl-smmu; redwood said 0x20000).
 * The global registers here are the ones the hypervisor imitates; offsets: arm-smmu.h.
 */
static struct block smmu = { "smmu", 0x03da0000, 0x40000 };""")

rep("0002-smmu-check",
"""	if (2 * smmu_pages * smmu_page != smmu.size) {
		printf("adreno: %u: that makes %#x of registers, the device tree says %#x: not reading further\\n", step,
		    2 * smmu_pages * smmu_page, smmu.size);
		return false;
	}""",
"""	if (2 * smmu_pages * smmu_page > smmu.size) {
		printf("adreno: %u: that makes %#x of registers, more than the device tree's %#x window: not reading further\\n", step,
		    2 * smmu_pages * smmu_page, smmu.size);
		return false;
	}""")

rep("0002-itcm",
"#define GMU_ITCM                GMU_WORD(0x0c00)",
"#define GMU_ITCM                GMU_WORD(0x1400)")

rep("0002-zap-window",
"""#define ZAP_MEMORY              0x8b71a000ull
#define ZAP_MEMORY_SIZE         0x2000u""",
"""#define ZAP_MEMORY              0x8b91a000ull   /* dt reserved-memory gpu_microcode (phk110.dts:150; redwood: 0x8b71a000) */
#define ZAP_MEMORY_SIZE         0x2000u""")

# ---- 0001: identity --------------------------------------------------------

rep("0001-chipid",
'#define GPU_CHIP_ID             0x06030500ull   /* dt: qcom,chipid */',
"""/* PHK110: dt qcom,chipid = <0x7030002> (phk110.dts:20063); Mesa's freedreno table names it
 * FD725 / "Adreno730v3" (mesa 25.0.7 freedreno_devices.py:1047) */
#define GPU_CHIP_ID             0x07030002ull   /* dt: qcom,chipid */""")

rep("0001-model",
"""	/* dt: qcom,gpu-models: 0xac and 0xbe are sold as Adreno 643, anything else is the 642L */
	printf("adreno: %u: speed bin %u: an Adreno %s; gaming bin %u\\n", step, bin, bin == 0xac || bin == 0xbe ? "643" : "642L",
	    gaming);""",
"""	/* the cell of cape's QFPROM that holds the GPU speed bin is not the reference's [TODO-DEV]:
	 * both reads stay (they print what the fuses say), nothing is gated on the bin (the
	 * reference gates nothing either), and the chip id's own name is what the log shows */
	printf("adreno: %u: speed bin %u: an Adreno 730v3 (chip id %#llx); gaming bin %u\\n", step, bin, GPU_CHIP_ID,
	    gaming);""")

rep("0001-gmu-chip",
'#define GMU_CHIP                0x06035000      /* dt qcom,chipid 0x06030500 the way the firmware wants it */',
"""/* gen7 packs the chip id minor and patch into the low nibbles: 0x07030002 -> 0x07030200
 * (mainline a6xx_gmu.c's gen7 formula; the pong bring-up reached the same number) [UP][PONG] */
#define GMU_CHIP                0x07030200      /* dt qcom,chipid 0x07030002 the way the firmware wants it */""")

# ---- 0003: firmware names --------------------------------------------------

rep("0003-zap-header-line",
'	header = image_file("fw", "a660_zap.mdt", &size);',
'	header = image_file("fw", "a730_zap.mdt", &size);')

rep("0003-gmu-fw",
"""	announce("find the GMU's firmware, fw/a660_gmu.bin, in the small image, and make the memory it asks for");
	gmu_firmware = image_file("fw", "a660_gmu.bin", &gmu_firmware_size);""",
"""	announce("find the GMU's firmware, fw/gmu_gen70000.bin, in the small image, and make the memory it asks for");
	gmu_firmware = image_file("fw", "gmu_gen70000.bin", &gmu_firmware_size);""")

rep("0003-sqe",
'	microcode = image_file("fw", "a660_sqe.fw", &size);',
'	microcode = image_file("fw", "a730_sqe.fw", &size);')

rep("0003-zap-seg",
'	segment = image_file("fw", "a660_zap.b02", &size);',
"""	/* gen7: the code segment is a730_zap.b01 -- the pulled .mdt's own ELF says so: seg1
	 * PT_LOAD rwx, 0x8bc bytes (b01: 2236), while seg0/b00 and seg2/b02 are PT_NULL metadata
	 * [W36 forensic on the ColorOS files; the vendor loader picks b01 the same way] */
	segment = image_file("fw", "a730_zap.b01", &size);""")

rep("0003-files",
'	static const char *const files[] = { "a660_gmu.bin", "a660_sqe.fw", "a660_zap.mdt", "a660_zap.b02" };',
'	static const char *const files[] = { "gmu_gen70000.bin", "a730_sqe.fw", "a730_zap.mdt", "a730_zap.b01" };')

# ---- 0004: GMU start/queues ------------------------------------------------

rep("0004-step15-defines",
"""#define GMU_ICACHE_CONFIG       GMU_WORD(0x4c00)
#define GMU_DCACHE_CONFIG       GMU_WORD(0x4c01)
#define GMU_SYS_BUS_CONFIG      GMU_WORD(0x4c0f)
#define GMU_PWR_COL_INTER_FRAME_CTRL GMU_WORD(0x50c0)
#define GMU_RPMH_CTRL           GMU_WORD(0x50e8)
#define GMU_RPMH_CTRL_ALL       0xf11           /* the RPMh interface, and every vote the firmware may cast */
#define GMU_CX_FAL_INTF         GMU_WORD(0x50f0)
#define GMU_CX_FALNEXT_INTF     GMU_WORD(0x50f1)
#define GMU_PWR_COL_CP_MSG      GMU_WORD(0x5100)        /* at start: where the log is, and its pages - 1 */
#define GMU_PWR_COL_CP_RESP     GMU_WORD(0x5101)        /* ... and how far it was written before */
#define GMU_HFI_SFR_ADDR        GMU_WORD(0x5182)        /* at start: which GPU this is */
#define GMU_HFI_QTBL_INFO       GMU_WORD(0x5184)
#define GMU_HFI_QTBL_ADDR       GMU_WORD(0x5185)
#define GMU_HFI_CTRL_INIT       GMU_WORD(0x5186)
#define GMU_GMU2HOST_INTR_CLR   GMU_WORD(0x5191)
#define GMU_GMU2HOST_INTR_INFO  GMU_WORD(0x5192)        /* bit 0: a message for us; bit 31: the 3D core is ours */
#define GMU_HOST2GMU_INTR_SET   GMU_WORD(0x5194)        /* bit 0: a message for the GMU; bit 30, 31: see step 17 */
#define GMU_RSCC_CONTROL_REQ    GMU_WORD(0x9307)
#define GMU_AO_AHB_FENCE_CTRL   GMU_WORD(0x9310)
#define GMU_AHB_FENCE_RANGE_0   GMU_WORD(0x9311)""",
"""/* gen7: the a6xx words + 0x800 (see the GMU block's comment). The log and the chip id moved
 * off the PWR_COL/HFI_SFR names onto GENERAL_8/9/10 (vendor gen7_gmu_register_config). */
#define GMU_ICACHE_CONFIG       GMU_WORD(0x5400)
#define GMU_DCACHE_CONFIG       GMU_WORD(0x5401)
#define GMU_SYS_BUS_CONFIG      GMU_WORD(0x540f)
#define GMU_PWR_COL_INTER_FRAME_CTRL GMU_WORD(0x58c0)
#define GMU_RPMH_CTRL           GMU_WORD(0x58e8)
#define GMU_RPMH_CTRL_ALL       0xf11           /* the RPMh interface, and every vote the firmware may cast */
#define GMU_CX_FAL_INTF         GMU_WORD(0x58f0)
#define GMU_CX_FALNEXT_INTF     GMU_WORD(0x58f1)
#define GMU_HFI_QTBL_INFO       GMU_WORD(0x5984)
#define GMU_HFI_QTBL_ADDR       GMU_WORD(0x5985)
#define GMU_HFI_CTRL_INIT       GMU_WORD(0x5986)
#define GMU_GMU2HOST_INTR_CLR   GMU_WORD(0x5991)
#define GMU_GMU2HOST_INTR_INFO  GMU_WORD(0x5992)        /* bit 0: a message for us; bit 31: the 3D core is ours */
#define GMU_HOST2GMU_INTR_SET   GMU_WORD(0x5994)        /* bit 0: a message for the GMU; bit 30, 31: see step 17 */
#define GMU_RSCC_CONTROL_REQ    GMU_WORD(0x9b07)
#define GMU_AO_AHB_FENCE_CTRL   GMU_WORD(0x9b10)
#define GMU_AHB_FENCE_RANGE_0   GMU_WORD(0x9b11)""")

rep("0004-queue-slots",
"""#define HFI_QUEUES              3               /* 0: ours to the GMU; 1: its answers; 2: its debugging messages */
#define HFI_QUEUE_WORDS         1024""",
"""#define HFI_QUEUE_SLOTS         17              /* header slots reserved in the table (gen7; 3 carry queues) */
#define HFI_QUEUES              3               /* 0: ours to the GMU; 1: its answers; 2: its debugging messages */
#define HFI_QUEUE_WORDS         1024""")

rep("0004-hfi-init",
"""	hfi->words = sizeof(struct hfi_table) / 4;
	hfi->first_queue = 6;
	hfi->queue_words = sizeof(struct hfi_queue) / 4;
	hfi->queues = hfi->active_queues = HFI_QUEUES;""",
"""	hfi->version = 0;
	hfi->words = sizeof(struct hfi_table) / 4;      /* 210: the head 6 + 17 headers of 12 */
	hfi->first_queue = 6;
	hfi->queue_words = sizeof(struct hfi_queue) / 4;
	hfi->queues = hfi->active_queues = HFI_QUEUE_SLOTS;     /* gen7 counts all 17 slots (vendor init_queues) */""")

rep("0004-tcm-ret",
"""	put(&gmu, "cx_fal_intf", GMU_CX_FAL_INTF, 1);
	put(&gmu, "general_7", GMU_GENERAL_7, 1);""",
"""	put(&gmu, "cx_fal_intf", GMU_CX_FAL_INTF, 1);
	put(&cx_misc, "tcm_ret_cntl", CX_MISC_TCM_RET_CNTL, 1);         /* gen7's TCM retention (a6xx voted GENERAL_7) */""")

rep("0004-log-and-chip",
"""	put(&gmu, "pwr_col_cp_resp", GMU_PWR_COL_CP_RESP, 0);
	put(&gmu, "hfi_sfr_addr", GMU_HFI_SFR_ADDR, GMU_CHIP);
	put(&gmu, "pwr_col_cp_msg", GMU_PWR_COL_CP_MSG, GMU_LOG_ADDRESS | (GMU_LOG_SIZE / 4096 - 1));""",
"""	put(&gmu, "general_9", GMU_GENERAL_9, 0);       /* the log's wptr retention (gen7 moved it here) */
	put(&gmu, "general_10", GMU_GENERAL_10, GMU_CHIP);      /* which GPU this is: before the processor runs */
	put(&gmu, "general_8", GMU_GENERAL_8, GMU_LOG_ADDRESS | (GMU_LOG_SIZE / 4096 - 1));""")

rep("0004-fence",
'	put(&gmu, "ahb_fence_range_0", GMU_AHB_FENCE_RANGE_0, 1u << 31 | (0xa << 2) << 18 | 0x8a0);',
'	put(&gmu, "ahb_fence_range_0", GMU_AHB_FENCE_RANGE_0, 1u << 31 | 0x32 << 18 | 0x8a0);   /* gen7 fence range [VENDOR][UP] */')

rep("0004-hidden-tcs",
'	put(&rscc, "hidden_tcs_cmd2_data", RSCC_HIDDEN_TCS_CMD0_DATA + 4 * 4, 0x80000021);    /* a650 and later */',
'	put(&rscc, "hidden_tcs_cmd2_data", RSCC_HIDDEN_TCS_CMD0_DATA + 4 * 4, 0x80000000);    /* gen7 [VENDOR]; a650 and later wrote 0x80000021 */')

rep("0004-hidden-tcs-check",
"	    get(&rscc, \"hidden_tcs_cmd2_data\", RSCC_HIDDEN_TCS_CMD0_DATA + 4 * 4) == 0x80000021) {",
"	    get(&rscc, \"hidden_tcs_cmd2_data\", RSCC_HIDDEN_TCS_CMD0_DATA + 4 * 4) == 0x80000000) {")

rep("0004-rscc-announce",
'	announce("give the GMU\'s RPMh channel its sleep and wake program (rscc, 0x3de0000), unless it has it");',
'	announce("give the GMU\'s RPMh channel its sleep and wake program (rscc, 0x3d50000), unless it has it");')

rep("0004-post-mortem",
'	uint32_t next = rd(gmu.base + GMU_PWR_COL_CP_RESP) & 0xffff, entries = GMU_LOG_SIZE / 16;',
'	uint32_t next = rd(gmu.base + GMU_GENERAL_9) & 0xffff, entries = GMU_LOG_SIZE / 16;')

rep("0004-gmu-state-comment",
"#define GMU_STATE_ADDRESS       0x108454",
"#define GMU_STATE_ADDRESS       0x108454        /* [TODO-DEV] the a6xx firmware's data; on gen7 it may read 0xdeadbeef */")

# ---- 0005: tables, parameters, CP -----------------------------------------

rep("0005-cx-hlvl",
"""/* dt: kgsl_3d0_reg_memory: the 3D core's registers; a6xx.xml counts in words */""",
"""/* gen7's to_cx_hlvl: the place in the cx rail of the first level at or above `level`;
 * 0xffffffff: none (the vendor returns the same to say "no cx vote"). */
static uint32_t
cx_hlvl(uint32_t level, const uint16_t *cx, unsigned cx_levels)
{
	for (unsigned i = 0; i < cx_levels; i++) {
		if (cx[i] >= level) {
			return i;
		}
	}
	return 0xffffffff;
}

/* dt: kgsl_3d0_reg_memory: the 3D core's registers; a6xx.xml counts in words */""")

rep("0005-speeds",
"""	static const struct {
		uint32_t khz, level;
	} speeds[] = { { 0, 0 }, { 315000, 64 }, { 450000, 128 }, { 550000, 192 } };""",
"""	/* the cape table: dt qcom,gpu-pwrlevels, 13 levels (phk110.dts:20081-20230); `level` is
	 * qcom,level (the 3D rail's vote), `cx` the qcom,cx-level floor beside it. Index 0 stays
	 * "off". dt qcom,initial-pwrlevel = <0x0b> (283 MHz) is the level to ask for first. */
	static const struct {
		uint32_t khz, level, cx;
	} speeds[] = {
		{ 0, 0, 0 },
		{ 900000, 0x1a0, 0x1a0 }, { 860000, 0x180, 0x180 }, { 810000, 0x140, 0x140 },
		{ 760000, 0x100, 0x100 }, { 710000, 0xe0, 0x100 }, { 645000, 0xc0, 0xc0 },
		{ 580000, 0x90, 0xc0 }, { 510000, 0x80, 0x80 }, { 440000, 0x60, 0x80 },
		{ 370000, 0x50, 0x80 }, { 325000, 0x40, 0x40 }, { 283000, 0x38, 0x40 },
		{ 220000, 0x30, 0x40 },
	};""")

rep("0005-perf-fill",
"""	perf.gpu_levels = sizeof(speeds) / sizeof(speeds[0]);
	for (unsigned i = 0; i < perf.gpu_levels; i++) {
		perf.gpu[i].khz = speeds[i].khz;
		perf.gpu[i].acd = 0xffffffff;           /* no adaptive clocking */
		if (!rail_vote(speeds[i].level, gfx, gfx_levels, mx, mx_levels, &perf.gpu[i].vote)) {
			printf("adreno: %u: RPMh has no level %u for the 3D core's rail\\n", step, speeds[i].level);
			return false;
		}
	}
	perf.gmu_levels = 2;
	perf.gmu[1].khz = 200000;
	if (!rail_vote(0, cx, cx_levels, mx, mx_levels, &perf.gmu[0].vote) ||
	    !rail_vote(48, cx, cx_levels, mx, mx_levels, &perf.gmu[1].vote)) {  /* "minimum SVS", the vendor's choice */
		return false;
	}""",
"""	perf.gpu_levels = sizeof(speeds) / sizeof(speeds[0]);
	for (unsigned i = 0; i < perf.gpu_levels; i++) {
		perf.gpu[i].khz = speeds[i].khz;
		if (!rail_vote(speeds[i].level, gfx, gfx_levels, mx, mx_levels, &perf.gpu[i].vote)) {
			printf("adreno: %u: RPMh has no level %u for the 3D core's rail\\n", step, speeds[i].level);
			return false;
		}
		/* gen7 reads this table's second word of a GPU level as the CX level the speed stands
		 * on (the vendor repurposed the a6xx "acd" field; to_cx_hlvl gives the place) */
		perf.gpu[i].acd = cx_hlvl(speeds[i].cx, cx, cx_levels);
	}
	perf.gmu_levels = 3;    /* gen7: off, the crystal, 200 MHz (vendor setup_cx_arc_votes) */
	perf.gmu[1].khz = 19200;        /* the crystal */
	perf.gmu[2].khz = 200000;
	if (!rail_vote(0, cx, cx_levels, mx, mx_levels, &perf.gmu[0].vote) ||
	    !rail_vote(0x40, cx, cx_levels, mx, mx_levels, &perf.gmu[1].vote) ||
	    !rail_vote(0xc0, cx, cx_levels, mx, mx_levels, &perf.gmu[2].vote)) {
		return false;
	}""")

rep("0005-default-speed",
'	uint32_t core_start[2] = { 0, 0 }, start[1] = { 0 }, vote[4] = { 0, 1, 3, HFI_NO_INDEX }, granted = 0, speed = 0;',
"""	uint32_t core_start[2] = { 0, 0 }, start[1] = { 0 }, vote[4] = { 0, 1, 12, HFI_NO_INDEX }, granted = 0, speed = 0;
	/* (12: dt qcom,initial-pwrlevel <0x0b>, 283 MHz, at this table's +1 for the "off" level) */""")

rep("0005-gmem",
"""	case 0x02:                              /* GMEM_SIZE */
		*value = 512 * 1024;
		return true;""",
"""	case 0x02:                              /* GMEM_SIZE */
		*value = 2 * 1024 * 1024;       /* 2 MiB [VENDOR gpulist gmem_size][UP a730 gmem] */
		return true;""")

rep("0005-hbb",
"""	case 0x10:                              /* HIGHEST_BANK_BIT */
		*value = 14;
		return true;""",
"""	case 0x10:                              /* HIGHEST_BANK_BIT */
		*value = 16;                    /* [VENDOR highest_bank_bit] = Mesa's FD725 (16) */
		return true;""")

rep("0005-ubwc",
"""	case 0x12:                              /* UBWC_SWIZZLE */
		*value = 6;
		return true;""",
"""	case 0x12:                              /* UBWC_SWIZZLE */
		*value = 6;                     /* [TODO-DEV] the reference's 6; this phone's dt says ubwc-mode <0x04> */
		return true;""")

rep("0005-cp-me-init",
"""	ring_command(CP_ME_INIT, 8);            /* a6xx_cp_init */
	ring(0x0000002f);""",
"""	ring_command(CP_ME_INIT, 8);            /* a6xx_cp_init; gen7 turns DMS off with bit 11 [PONG] */
	ring(0x0000082f);""")

# ---- header comment: the firmware names the file itself advertises ----------

rep("0003-header-comment",
" *              small image (fw/a660_zap.mdt) into memory of ours that TrustZone is pointed at",
" *              small image (fw/a730_zap.mdt) into memory of ours that TrustZone is pointed at")
rep("0003-header-comment-2",
" *  14  writes  the GMU's firmware (fw/a660_gmu.bin) into its own memory and into that memory",
" *  14  writes  the GMU's firmware (fw/gmu_gen70000.bin) into its own memory and into that memory")
rep("0003-header-comment-3",
" *              (fw/a660_sqe.fw) in it",
" *              (fw/a730_sqe.fw) in it")
rep("0003-zap-header-comment",
" * the ELF header and the block of hashes and certificates, which is all of the file a660_zap.mdt",
" * the ELF header and the block of hashes and certificates, which is all of the file a730_zap.mdt")
rep("0003-zap-announce",
'	announce("find the zap shader\'s header, fw/a660_zap.mdt, in the small image that came with the kernel");',
'	announce("find the zap shader\'s header, fw/a730_zap.mdt, in the small image that came with the kernel");')
rep("0003-sqe-comment",
' * ("SQE", with microcode of its own: a660_sqe.fw) reads up to where a register says we have',
' * ("SQE", with microcode of its own: a730_sqe.fw) reads up to where a register says we have')
rep("0003-sqe-announce",
'	announce("make the 3D core\'s memory: its ring, its microcode (fw/a660_sqe.fw), a page to try writing to");',
'	announce("make the 3D core\'s memory: its ring, its microcode (fw/a730_sqe.fw), a page to try writing to");')
rep("0003-zap-seg-comment",
" * one segment (the file a660_zap.b02, relocatable: at the start of that memory) is put there,",
" * one segment (gen7: the file a730_zap.b01, relocatable: at the start of that memory) is put there,")


def main():
    text = io.open(DRIVER, encoding="utf-8", newline="").read()
    original = text
    for tag, old, new, count in R:
        found = text.count(old)
        if found != count:
            print(f"FAIL {tag}: {found} match(es) for anchor (want {count}):")
            print("  " + old.splitlines()[0][:120])
            sys.exit(1)
        text = text.replace(old, new)
        print(f"ok   {tag}")
    leftovers = [ln for ln in text.splitlines() if "a660" in ln or "0x03d6a000" in ln or "0x03de0000" in ln or "GMU_PWR_COL_CP" in ln or "GMU_HFI_SFR_ADDR" in ln]
    if leftovers:
        print("FAIL leftover a6xx names:")
        for ln in leftovers:
            print("  " + ln[:140])
        sys.exit(1)
    io.open(DRIVER, "w", encoding="utf-8", newline="").write(text)
    io.open(DRIVER + ".v24-orig", "w", encoding="utf-8", newline="").write(original)
    diff = difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True),
                                "a/drivers/gpu/hakios.adreno.c", "b/drivers/gpu/hakios.adreno.c")
    out = os.path.join(HERE, "patches", "wave36-adreno-a730-parameter-layer.diff")
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        f.writelines(diff)
    print(f"\napplied {len(R)} replacements; diff -> {out}")
    import hashlib
    print("new driver sha256:", hashlib.sha256(text.encode("utf-8")).hexdigest()[:16])
    print("old driver sha256:", hashlib.sha256(original.encode("utf-8")).hexdigest()[:16])


main()
