#!/usr/bin/env python3
"""Wave 21.2 v16c patch: wake the DWC3 before the USB bring-up (the endpoint wall).

v16b' on device: the loader boots (the PAYLOAD_BASE fix held), the USB server starts, the
gadget enumerates -- and the vendor state machine refuses every bulk submit
("usbDevSsm/DwcPrepareURB:Trb: physical endpoint[2] not configured" / 0x8000000C). The
device SSM never reaches Configured on warm boots -- the Qualcomm SM8450 DWC3 warm-resume
disease: with the PHY suspend clock gated (SUSPHY), writes into the clock-gated register
domain drop silently, so the SSM cannot advance. The Qualcomm-blessed cure, in the loader:

  1. clear GUSB3PIPECTL(0).SUSPHY and GUSB2PHYCFG(0).SUSPHY (bit 6 -- the
     dis_u3_susphy/dis_u2_susphy of the Qualcomm fix; un-gate the register domain);
  2. stop the controller and soft disconnect (DCTL.RUN_STOP bit 31 + CS bit 18: the host
     sees a real detach);
  3. GCTL.CSFTRST core soft reset (bit 11, self-clearing, bounded wait);
  4. re-clear the SUSPHY bits (reset restores power-on defaults);
  5. NEW (v16c-re): the vendor's own init re-sets SUSPHY=1 (the snps power-saving default)
     inside start_ex -- which re-gates the domain and the DEPCFG writes at SET_CONFIG time
     drop again. So usb_start_attempt clears the SUSPHY bits once more AFTER a successful
     start_ex, before the host's SET_CONFIGURATION arrives.

Linux dwc3_core_soft_reset's shape, MMIO by hand (DWC3 at 0x0A600000: GCTL 0xC110,
GUSB3PIPECTL(0) 0xC2C0, GUSB2PHYCFG(0) 0xC200, DCTL 0xC704). The init event re-signals the
vendor's bring-up callback on the freshly reset controller. Only on platform_phk110.

usage: patch-loader-v16c.py LOADER_C
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, "hunk not unique (found %dx):\n%s" % (n, old[:200])
    src = src.replace(old, new)

# ---- hunk 1: the wake helpers, inserted before usb_start_attempt (its first caller) ----------
OLD_A = "/* One bring-up attempt: the init event's callback, then start_ex, then the buffers. The"
NEW_A = (
"/* Wave 21.2's endpoint wall (v16b' on device): on warm boots the DWC3's PHY-suspend clock\n"
" * gates its register domain, writes drop silently (the Qualcomm SM8450 warm-resume disease),\n"
" * the device state machine never reaches Configured, and every bulk submit answers\n"
' * "Physical endpoint not configured" (0x8000000C -- the same DevSm mismatch family as 0xB).\n'
" * The Qualcomm-blessed wake, in the loader now (Linux dwc3_core_soft_reset's shape, MMIO by\n"
" * hand): un-gate both PHY suspend clocks (SUSPHY, bit 6 of GUSB3PIPECTL/GUSB2PHYCFG -- the\n"
" * dis_u3_susphy/dis_u2_susphy of the Qualcomm fix), stop the controller and soft disconnect\n"
" * (DCTL.RUN_STOP bit 31 + CS bit 18: the host sees a real detach), then GCTL CSFTRST (bit 11,\n"
" * self-clearing, bounded wait), and un-gate again once more (the reset restores power-on\n"
" * defaults). The vendor's bring-up callback re-programs the controller fresh after it\n"
" * (usb_init_kick re-signals it). Only on platform_phk110 (DWC3 at 0x0A600000). */\n"
"static void\n"
"usb_dwc3_susphy_off(void)\n"
"{\n"
"\tvolatile uint32_t *gusb3pipectl = (volatile uint32_t *)(uintptr_t)0x0A60C2C0ULL; /* GUSB3PIPECTL(0) */\n"
"\tvolatile uint32_t *gusb2phycfg = (volatile uint32_t *)(uintptr_t)0x0A60C200ULL;  /* GUSB2PHYCFG(0) */\n"
"\n"
"\t*gusb3pipectl = *gusb3pipectl & ~(1u << 6);   /* SUSPHY off: the register domain must stay clocked */\n"
"\t*gusb2phycfg = *gusb2phycfg & ~(1u << 6);\n"
"}\n"
"\n"
"static void\n"
"usb_dwc3_wake(void)\n"
"{\n"
"\tvolatile uint32_t *dctl = (volatile uint32_t *)(uintptr_t)0x0A60C704ULL;        /* DCTL */\n"
"\tvolatile uint32_t *gctl = (volatile uint32_t *)(uintptr_t)0x0A60C110ULL;         /* GCTL */\n"
"\tuint64_t freq = READ_SYSREG(CNTFRQ_EL0), began = READ_SYSREG(CNTVCT_EL0);\n"
"\n"
"\tif (PLAT != &platform_phk110) {\n"
"\t\treturn;\n"
"\t}\n"
"\tusb_dwc3_susphy_off();\n"
"\t*dctl = *dctl & ~((1u << 31) | (1u << 18));   /* RUN_STOP off + soft disconnect: real detach */\n"
"\t*gctl = *gctl | (1u << 11);                   /* CSFTRST */\n"
"\twhile (*gctl & (1u << 11)) {\n"
'\t\tif (READ_SYSREG(CNTVCT_EL0) - began > freq) {\n'
'\t\t\tprint("usb: dwc3 soft reset did not settle in one second\\n");\n'
"\t\t\tbreak;\n"
"\t\t}\n"
"\t}\n"
"\tusb_dwc3_susphy_off();                        /* reset restored defaults: un-gate again */\n"
'\tprint("usb: dwc3 woken (phy suspend off + core soft reset)\\n");\n'
"}\n"
"\n"
+ OLD_A)
sub(OLD_A, NEW_A)

# ---- hunk 2: call the wake before the bring-up ------------------------------------------------
sub(
"""	if (EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL, &tick))) {
		tick = NULL;
	}
	/* the settle window: the init event's callback runs behind it, and the timer event pumps""",
"""	if (EFI_ERROR(create_event(0x80000000 /* EVT_TIMER */, 8 /* TPL_CALLBACK */, NULL, NULL, &tick))) {
		tick = NULL;
	}
	usb_dwc3_wake();          /* warm-boot DWC3: SUSPHY off + core soft reset before the bring-up */
	/* the settle window: the init event's callback runs behind it, and the timer event pumps""")

# ---- hunk 3: re-clear SUSPHY after every successful start_ex ----------------------------------
sub(
"""	efi_status s = USB->start_ex(&usb_set);
	if (!EFI_ERROR(s) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf))) {
		usb_ready = 1;
		return 1;
	}""",
"""	efi_status s = USB->start_ex(&usb_set);
	if (!EFI_ERROR(s) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_rx_buf)) &&
	    !EFI_ERROR(USB->allocate_transfer_buffer(USB_CHUNK, (void **)&usb_tx_buf))) {
		usb_dwc3_susphy_off();   /* the vendor init re-set SUSPHY=1: un-gate before SET_CONFIG comes */
		usb_ready = 1;
		return 1;
	}""")

# ---- sanity of the patched text ---------------------------------------------------------------
for token in (b"usb_dwc3_wake", b"usb_dwc3_susphy_off",
              b"usb: dwc3 woken (phy suspend off + core soft reset)",
              b"0x0A60C2C0ULL", b"0x0A60C110ULL", b"0x0A60C704ULL"):
    assert token in src.encode(), "missing after patch: %s" % token
assert src.count("usb_dwc3_wake") == 2, src.count("usb_dwc3_wake")          # def + call site
assert src.count("usb_dwc3_susphy_off") == 4, src.count("usb_dwc3_susphy_off")  # def + wake(2) + post-start_ex

if src == orig:
    sys.exit("nothing changed")
open(path, "w", encoding="utf-8", newline="").write(src)
print("patched %s: 3 hunks applied" % path)
print("  1. usb_dwc3_susphy_off() + usb_dwc3_wake() inserted before usb_start_attempt")
print("  2. usb_start calls the wake before the init kick + settle")
print("  3. usb_start_attempt clears SUSPHY again after a successful start_ex")
