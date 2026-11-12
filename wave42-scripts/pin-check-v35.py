#!/usr/bin/env python3
"""Wave 42: check every verify-v34 loader string pin against the current loader.c
(GEN-1..4 reworded several prints -- the v35 verify pin table must match the
shipped source). Also print the gen-4 pins' presence."""
src = open("/home/cyrux/hakios/kernel/xnuloader/loader.c", "rb").read()

PINS = [
    ("IN gate: engagement", b"the IN gate is up: x%d unread replies"),
    ("IN gate: beat", b"one probe per beat (1 s doubling to 30 s, counts silent)"),
    ("IN gate: wall refusal", b"the reply side is refused at the wall too (%x)"),
    ("IN gate: lift", b"the host reads replies again: the gate lifts"),
    ("drain: unread reply", b"a reply came back unread: the host's reader is gone"),
    ("drain: third unread", b"from the third unread the replies are gated"),
    ("OLD rebuild: dead both ways", b"the bulk pair reads dead both ways"),
    ("OLD rebuild: cap line", b"rebuild %d of 2 -- the pair's END_TRANSFERs"),
    ("OLD rebuild: presented", b"the pair's rebuild is in: the gadget is presented"),
    ("OLD rebuild: no come-back", b"the rebuild's bring-up did not come back"),
    ("NEW gen4: reads dead this gen", b"the pair reads dead in this generation"),
    ("NEW gen4: bounded recovery", b"bounded recovery %d of 2"),
    ("NEW gen4: bring-up back", b"the recovery's bring-up is back"),
    ("NEW gen4: bring-up dead", b"the recovery's bring-up did not come back"),
    ("NEW gen4: IN abort refused", b"the recovery's IN abort was refused"),
    ("NEW gen4: OUT abort refused", b"the recovery's OUT abort was refused"),
    ("NEW gen4: stopped for window", b"USB is stopped for this window"),
    ("GEN2: mirror sticky", b"the vendor said '%s': the line is sticky now"),
    ("GEN2: console mirror", b"the console mirror: vendor door %s, console door %s"),
    ("mirror leads", b"DEPSTARTCFG Fails"),
    ("mirror leads 2", b"Failed to set config for ep"),
    ("mirror leads 3", b"DwcConfigureEP failed"),
    ("mirror leads 4", b"Unknown USB Speed"),
    ("consumer: checkpoint-3", b"checkpoint-3: the standing receive finished"),
    ("consumer: retired", b"the host left: the standing receive (gen %d) is retired"),
    ("standing recv: checkpoint-1", b"checkpoint-1: the standing receive is in"),
    ("standing recv: first refusal", b"the first refusal is on the record"),
    ("standing recv: refused again", b"refused %x again (x%d since the first)"),
    ("sampler: regs", b"sample %s: GCTL %x DCTL %x DSTS %x DALEPENA %x"),
    ("sampler: vendor", b"sample %s (vendor): speed %d (%s) phys[2] state %d maxpkt %d phys[3] state %d"),
    ("sampler: no usbf below", b"carries no 'usbf' below"),
    ("timeline", b"the bring-up begins (the Wave 24 timeline runs from here)"),
    ("GCTL cleared", b"soft reset was still set after the wait: cleared by hand"),
    ("raw look moved", b"the raw UsbFn look (gen %d, a second submit by design)"),
    ("NEG raw through UsbFn (must be ABSENT)", b"through UsbFn (raw)"),
    ("buffer split", b"the receive buffer alone (%x)"),
    ("buffer split 2", b"the send buffer (%x); the receive buffer goes back"),
    ("NEG zero-length probe (must be ABSENT)", b"USB->send(USB_EP_OUT, 0,"),
    ("presented", b"the gadget is presented to the host (the pull-up is ours)"),
    ("bulk pair answered", b"usb: the bulk pair answered: armed at generation %d, beat %d"),
    ("never armed", b"the pair never armed across 3 generations"),
    ("re-throw dead", b"the re-throw did not come back"),
    ("kept host", b"kept its host: no re-throw"),
    ("dwc3 woken", b"usb: dwc3 woken (phy suspend off + core soft reset)"),
    ("oem recording", b"oem recording"),
    ("no recording", b"no recording"),
    ("D22AP", b"D22AP"),
    ("iPhone10,3", b"iPhone10,3"),
    ("RAMDisk1", b"RAMDisk1"),
    ("may be written this run", b"may be written this run"),
    ("kern.maxvnodes", b"kern.maxvnodes"),
    ("SerialPort Lib", b"SerialPort Lib"),
]

print(f"source bytes: {len(src)}")
for label, s in PINS:
    neg = label.startswith("NEG")
    c = src.count(s)
    verdict = "PASS" if ((c > 0) != neg) else "STALE" if not neg and c == 0 else "VIOLATION"
    print(f"  [{verdict:9s}] {c}x {label}")
