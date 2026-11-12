#!/usr/bin/env python3
"""Wave 41: the kernel's GPU fence events speak the seventh generation, and the NC_MODE bank
encoding matches the HBB the driver declares.

Report 4 (docs/review/gpt-review-report-4-2026-11-11-gpu.md) P0-1 and P1-1, independently
confirmed by wave 40 (docs/waves/wave40-gpu-verify.md sections 1 and 2):

  P0 -- the submission tail's completion event went out with the sixth generation's word
  (EVENT_CACHE_FLUSH = 0x04, WRITE_ENABLED bit 27 off): the core was asked to run the event and
  told nothing about writing the submission number back. The only writer of the word
  hakios_gpu_done waits on (GPU_FENCE_AT in the scratch page) is that one event, so a wait
  cannot end. The vendor's completion event (adreno_gen7_ringbuffer.c:368-390) and Linux's
  a7xx_submit both build CACHE_CLEAN | BIT(27); Mesa's CP_EVENT_WRITE7 fields name the parts.
  The fix builds the word from the named fields (no magic numbers), for the submission tail and
  for step_frame's two twin events alike (wave 40 section 6.2's "same knife").

  P1-a -- the five NC_MODE registers were programmed with the bank encoding of
  highest_bank_bit 14 (what a DDR-4 machine gets) while the driver's own parameter table, the
  device tree and Mesa's FD725 all say 16; GRAS_NC_MODE_CNTL was not written at all. The fix
  computes all five the vendor's way (adreno_gen7.c gen7_gpu_init) from a highest_bank_bit that
  carries the vendor's DDR-type override branch (gen7_init: type 0x7 -> 14; this phone's tree
  says ddr_device_type = <0x08>, which does not fire -- the branch stays, overridable by the
  adreno_ddr_type boot argument), and the parameter table hands Mesa the same number.

  Wave 40 section 6.2's hard precondition: the vendor's own CP start turns concurrent binning
  off first (gen7_cp_init_cmds), and this kernel's BV/BR + CP_WAIT_TIMESTAMP ordering does not
  exist -- so CP_THREAD_CONTROL with CONCURRENT_BIN_DISABLE goes out before CP_ME_INIT, behind
  a CONCURRENT_BINNING switch that fails the build if anyone flips it before those pieces exist.

Each anchor must appear exactly once; the file must be the wave 33..40 baseline (b4795014...).
Never run twice.
"""
import hashlib
import re
import sys

PATH = "/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c"
BASE_SHA = "b479501498cb6ba8e71080f829a0735b945bfef9914f7dc790c761b76cc07eea"

src = open(PATH, "rb").read().decode("utf-8")
if hashlib.sha256(src.encode()).hexdigest() != BASE_SHA:
    sys.exit("hakios.adreno.c is not the v33..v40 baseline (b4795014...); the patch anchors are void")

REPL = []

# --- K1: the seventh generation's event-word fields, by name, after the CP opcodes --------------
K1_ANCHOR = "\n#define CP_SET_MARKER           0x65\n#define CP_SET_SECURE_MODE      0x66\n"
K1_NEW = (
    "\n#define CP_SET_MARKER           0x65\n#define CP_SET_SECURE_MODE      0x66\n"
    "#define CP_THREAD_CONTROL       0x17    /* [VENDOR adreno_pm4types.h] */\n"
    "#define CP_THREAD_CONTROL_CONCURRENT_BIN_DISABLE (1u << 27)     /* Mesa's CONCURRENT_BIN_DISABLE */\n"
    "\n"
    "/*\n"
    " * The seventh generation says, in the word after a type-7 header, what a completion event\n"
    " * writes and where (Mesa's CP_EVENT_WRITE7, adreno_pm4.xml: the event id in bits 0-7,\n"
    " * WRITE_SRC in 20-22, WRITE_DST in 24, WRITE_ENABLED in bit 27, IRQ in 31). The vendor's\n"
    " * fence event is CACHE_CLEAN with WRITE_ENABLED (adreno_gen7_ringbuffer.c: CACHE_CLEAN |\n"
    " * BIT(27); BIT(31) more is the interrupting kind, which this polling wait does not ask\n"
    " * for), and Linux's a7xx_submit builds the same. WRITE_SRC 0 is the payload word after the\n"
    " * 64-bit address (EV_WRITE_USER_32B), WRITE_DST 0 is memory (EV_DST_RAM): with the bit off\n"
    " * the core writes nothing anywhere, and the submission number a waiter reads in the scratch\n"
    " * page never arrives -- the sixth generation's event word (0x04) asked for the event alone\n"
    " * and put the number in a scratch register instead.\n"
    " */\n"
    "#define EV_WRITE_USER_32B       0\n"
    "#define EV_DST_RAM              0\n"
    "#define CP_EVENT_WRITE7_SRC(src)        ((uint32_t)(src) << 20)\n"
    "#define CP_EVENT_WRITE7_DST(dst)        ((uint32_t)(dst) << 24)\n"
    "#define CP_EVENT_WRITE7_WRITE_ENABLED   (1u << 27)\n"
    "#define FENCE_EVENT(event)      ((event) | CP_EVENT_WRITE7_SRC(EV_WRITE_USER_32B) | CP_EVENT_WRITE7_DST(EV_DST_RAM) \\\n"
    "\t    | CP_EVENT_WRITE7_WRITE_ENABLED)\n"
)
REPL.append((K1_ANCHOR, K1_NEW))

# --- K2: ring_fence_event, the one builder both twin and fence use ------------------------------
K2_ANCHOR = (
    "ring_register(uint32_t number, uint32_t value)\n"
    "{\n"
    "\tring(4u << 28 | 1 | odd_parity(1) << 7 | number << 8 | odd_parity(number) << 27);\n"
    "\tring(value);\n"
    "}\n"
    "\n"
)
K2_NEW = K2_ANCHOR + (
    "/* A completion event of the seventh generation, with its write-back: the event id, where the\n"
    " * word goes, and the word itself (a type-7 header and four words, FENCE_EVENT first). */\n"
    "static void\n"
    "ring_fence_event(uint32_t event, uint64_t address, uint32_t word)\n"
    "{\n"
    "\tring_command(CP_EVENT_WRITE, 4);\n"
    "\tring(FENCE_EVENT(event));\n"
    "\tring((uint32_t)address);\n"
    "\tring((uint32_t)(address >> 32));\n"
    "\tring(word);\n"
    "}\n"
    "\n"
)
REPL.append((K2_ANCHOR, K2_NEW))

# --- K3: the event ids the generation itself uses ----------------------------------------------
K3_ANCHOR = "#define EVENT_FLUSH_COLOR       0x1d\n#define EVENT_CACHE_FLUSH       0x04\n"
K3_NEW = (
    "#define EVENT_CCU_CLEAN_COLOR   0x20    /* the seventh generation's clean of the colour caches (Mesa's\n"
    "                                         * fd_gpu_events: FD_CCU_CLEAN_COLOR = CCU_CLEAN_COLOR); the sixth's\n"
    "                                         * 0x1d flush is, on a seventh, its clean-and-invalidate kind */\n"
    "#define EVENT_CACHE_CLEAN       0x31    /* [VENDOR adreno_pm4types.h CACHE_CLEAN] the event the seventh generation's\n"
    "                                         * fences write their word back with */\n"
)
REPL.append((K3_ANCHOR, K3_NEW))

# --- K4: step_frame's twin events, same knife ---------------------------------------------------
K4_ANCHOR = (
    "\t/*\n"
    "\t * What it has drawn out of its caches into memory. Each of the two events is followed by an\n"
    "\t * address and a word that the core writes there when it is done (Linux's a6xx_submit; Mesa's\n"
    "\t * tu6_emit_event_write: the events named ..._TS): the core takes those three words whether\n"
    "\t * they are there or not.\n"
    "\t */\n"
    "\tring_command(CP_EVENT_WRITE, 4);\n"
    "\tring(EVENT_FLUSH_COLOR);\n"
    "\tring(CORE_SCRATCH_ADDRESS + 32);\n"
    "\tring(0);\n"
    "\tring(0x0c0c0c0c);\n"
    "\tring_command(CP_EVENT_WRITE, 4);\n"
    "\tring(EVENT_CACHE_FLUSH);\n"
    "\tring(CORE_SCRATCH_ADDRESS + 16);\n"
    "\tring(0);\n"
    "\tring(0x0d0e0d0e);\n"
)
K4_NEW = (
    "\t/*\n"
    "\t * What it has drawn out of its caches into memory. Each event says, in the seventh\n"
    "\t * generation's own fields, to write its word into memory when the clean is done (the sixth\n"
    "\t * generation asked for the event alone and never had the word after the address written;\n"
    "\t * wave 41 gives these the same write-back the submission fences have).\n"
    "\t */\n"
    "\tring_fence_event(EVENT_CCU_CLEAN_COLOR, CORE_SCRATCH_ADDRESS + 32, 0x0c0c0c0c);\n"
    "\tring_fence_event(EVENT_CACHE_CLEAN, CORE_SCRATCH_ADDRESS + 16, 0x0d0e0d0e);\n"
)
REPL.append((K4_ANCHOR, K4_NEW))

# --- K5: the submission tail's fence event ------------------------------------------------------
K5_ANCHOR = (
    "\tring_register(CP_SCRATCH_REG2, gpu_fence);\n"
    "\tring_command(CP_EVENT_WRITE, 4);\n"
    "\tring(EVENT_CACHE_FLUSH);\n"
    "\tring(CORE_SCRATCH_ADDRESS + GPU_FENCE_AT);\n"
    "\tring(0);\n"
    "\tring(gpu_fence);\n"
    "\tring_send();\n"
)
K5_NEW = (
    "\tring_register(CP_SCRATCH_REG2, gpu_fence);\n"
    "\tring_fence_event(EVENT_CACHE_CLEAN, CORE_SCRATCH_ADDRESS + GPU_FENCE_AT, gpu_fence);\n"
    "\tring_send();\n"
)
REPL.append((K5_ANCHOR, K5_NEW))

# --- K6: the highest_bank_bit the registers and the parameter table share -----------------------
K6_ANCHOR = (
    "/* ---- step 20: the 3D core's registers, its command processor started, its first command ------------------- */\n"
    "\n"
    "static bool\n"
)
K6_NEW = (
    "/*\n"
    " * How the five NC_MODE registers encode the memory's banks: highest_bank_bit, 16 for this\n"
    " * chip (gen7_4_0 in the vendor's list, Mesa's FD725), which the vendor's own start takes down\n"
    " * to 14 when the memory is DDR type 0x7 (\"If the memory type is DDR 4\", adreno_gen7.c\n"
    " * gen7_init). This phone's device tree declares ddr_device_type = <0x08> (phk110.dts:22), so\n"
    " * the override does not fire -- but the branch is kept below, and the adreno_ddr_type boot\n"
    " * argument corrects a tree that lies without a rebuild. Mesa is told the same number\n"
    " * (hakios_gpu_parameter).\n"
    " */\n"
    "static uint32_t gpu_highest_bank_bit = 16;\n"
    "\n"
) + K6_ANCHOR
REPL.append((K6_ANCHOR, K6_NEW))

# --- K7: the five NC_MODE registers, computed the vendor's way, GRAS among them ------------------
K7_ANCHOR = (
    "\t/*\n"
    "\t * How textures in the GPU's own tiled and compressed layouts are laid out in memory (Linux's\n"
    "\t * a6xx_calc_ubwc_config, a6xx_set_ubwc_config for this GPU: highest bank bit 14, and the\n"
    "\t * rest as below); Mesa is told the same (hakios_gpu_parameter()).\n"
    "\t */\n"
    "\tput(&gpu, \"rb_nc_mode_cntl\", GPU_WORD(0x8e08), 1u << 11 | 1u << 4 | 1u << 1);\n"
    "\tput(&gpu, \"tpl1_nc_mode_cntl\", GPU_WORD(0xb604), 1u << 1);\n"
    "\tput(&gpu, \"sp_nc_mode_cntl\", GPU_WORD(0xae02), 2u << 4 | 1u << 1);\n"
    "\tput(&gpu, \"uche_mode_cntl\", GPU_WORD(0x0e01), 1u << 21);\n"
    "\tput(&gpu, \"rbbm_nc_mode_cntl\", GPU_WORD(0x0534), 1);\n"
)
K7_NEW = (
    "\t/*\n"
    "\t * How textures in the GPU's own tiled and compressed layouts are laid out in memory: the\n"
    "\t * vendor's gen7_gpu_init computes these five from highest_bank_bit and the device tree's\n"
    "\t * qcom,min-access-length (adreno_gen7.c: bank_bit = (highest_bank_bit - 13) & 3, each\n"
    "\t * register takes bank_bit in its own field, a 64-byte access length would add its bit, and\n"
    "\t * this phone's tree says <0x20>, 32, so none). The values this table had were bank_bit 1's\n"
    "\t * -- highest_bank_bit 14, what a DDR-4 machine gets -- while the chip, its tree and Mesa\n"
    "\t * all say 16: bank_bit 3. GRAS_NC_MODE_CNTL (word 0x8602, gen7_reg.h:726) is the vendor's\n"
    "\t * fifth register, which the sixth generation has no counterpart of and the old table forgot.\n"
    "\t */\n"
    "\tuint32_t ddr_type = 0x8, bank_bit;      /* dt: ddr_device_type (phk110.dts:22) */\n"
    "\n"
    "\tPE_parse_boot_argn(\"adreno_ddr_type\", &ddr_type, sizeof(ddr_type));\n"
    "\tif (ddr_type == 0x7) {                 /* [VENDOR adreno_gen7.c gen7_init] DDR 4: highest_bank_bit 14 */\n"
    "\t\tgpu_highest_bank_bit = 14;\n"
    "\t}\n"
    "\tbank_bit = (gpu_highest_bank_bit - 13) & 3;\n"
    "\tput(&gpu, \"rb_nc_mode_cntl\", GPU_WORD(0x8e08), 1u << 11 | 1u << 4 | bank_bit << 1);\n"
    "\tput(&gpu, \"tpl1_nc_mode_cntl\", GPU_WORD(0xb604), bank_bit << 1);\n"
    "\tput(&gpu, \"sp_nc_mode_cntl\", GPU_WORD(0xae02), 2u << 4 | bank_bit << 1);\n"
    "\tput(&gpu, \"gras_nc_mode_cntl\", GPU_WORD(0x8602), bank_bit << 5);\n"
    "\tput(&gpu, \"uche_mode_cntl\", GPU_WORD(0x0e01), bank_bit << 21);\n"
    "\tput(&gpu, \"rbbm_nc_mode_cntl\", GPU_WORD(0x0534), 1);\n"
)
REPL.append((K7_ANCHOR, K7_NEW))

# --- K8: the parameter table hands Mesa the same number -----------------------------------------
K8_ANCHOR = (
    "\tcase 0x10:                              /* HIGHEST_BANK_BIT */\n"
    "\t\t*value = 16;                    /* [VENDOR highest_bank_bit] = Mesa's FD725 (16) */\n"
    "\t\treturn true;\n"
)
K8_NEW = (
    "\tcase 0x10:                              /* HIGHEST_BANK_BIT */\n"
    "\t\t*value = gpu_highest_bank_bit;  /* what the NC_MODE registers were computed from (16; 14 if the memory is DDR type 0x7) */\n"
    "\t\treturn true;\n"
)
REPL.append((K8_ANCHOR, K8_NEW))

# --- K9: concurrent binning off at the source, behind a switch that argues back ------------------
K9_ANCHOR = (
    "\tannounce(\"give the 3D core its first command, \\\"initialize\\\"\");\n"
    "\tring_command(CP_ME_INIT, 8);            /* a6xx_cp_init; gen7 turns DMS off with bit 11 [PONG] */\n"
)
K9_NEW = (
    "\tannounce(\"give the 3D core its first command, \\\"initialize\\\"\");\n"
    "\t/*\n"
    "\t * The vendor's own command-processor start turns concurrent binning off first\n"
    "\t * (gen7_cp_init_cmds: \"Disable concurrent binning before sending CP init\"), and Mesa's\n"
    "\t * seventh-generation restores do the same (fd6_emit.cc: CP_THREAD_CONTROL with\n"
    "\t * CONCURRENT_BIN_DISABLE). This kernel drives one direct command stream: binning beside\n"
    "\t * rendering needs the binning stream's own completion event and the CP_WAIT_TIMESTAMP that\n"
    "\t * orders it against the render stream before the draws that read it (the three-part fence\n"
    "\t * of adreno_gen7_ringbuffer.c) -- none of which exist here. CONCURRENT_BINNING below is\n"
    "\t * the single switch, and a hard precondition, not a TODO: flipped before those exist, it\n"
    "\t * fails right here.\n"
    "\t */\n"
    "#define CONCURRENT_BINNING 0\n"
    "#if CONCURRENT_BINNING\n"
    '#error "concurrent binning needs the BV and BR completion events and CP_WAIT_TIMESTAMP first (see the comment above)"\n'
    "#endif\n"
    "\tring_command(CP_THREAD_CONTROL, 1);\n"
    "\tring(CP_THREAD_CONTROL_CONCURRENT_BIN_DISABLE);\n"
    "\tring_command(CP_ME_INIT, 8);            /* a6xx_cp_init; gen7 turns DMS off with bit 11 [PONG] */\n"
)
REPL.append((K9_ANCHOR, K9_NEW))

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:72]!r}...")
    src = src.replace(old, new)

# never-run-twice and completeness markers
n_def = src.count("ring_fence_event(uint32_t event")
n_calls = src.count("\tring_fence_event(")
if (n_def, n_calls) != (1, 3):                  # one builder; step_frame's twins + the submission tail
    sys.exit(f"ring_fence_event definition/calls wrong: {n_def}/{n_calls}")
if "EVENT_CACHE_FLUSH" in src or "EVENT_FLUSH_COLOR" in src:
    sys.exit("a sixth-generation event id is still referenced")
if src.count("gpu_highest_bank_bit") != 4:      # definition, the DDR branch's assignment, the formula, the parameter
    sys.exit(f"gpu_highest_bank_bit used {src.count('gpu_highest_bank_bit')} times, expected 4")
if "gras_nc_mode_cntl" not in src:
    sys.exit("GRAS_NC_MODE_CNTL did not land")
if "#define CONCURRENT_BINNING 0" not in src:
    sys.exit("the CONCURRENT_BINNING switch did not land")

open(PATH, "w").write(src)
print("applied: fence events fielded (0x31|BIT(27)), NC_MODE = vendor formula with the DDR branch, GRAS added, concurrent binning gated off")
print("new sha256:", hashlib.sha256(open(PATH, "rb").read()).hexdigest())
