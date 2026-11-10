#!/usr/bin/env python3
"""Wave 21.5 round-2 delta (v17b): the field-corrected discriminator + no explicit stop.

Boot #34's logdump (logdump-v17.bin, pulled 20:45 off the returned Android) rewrote the
round-1 picture: the loader never froze -- it ran clean sessions in a slot-b boot loop for
~1 h (start_ex first-try, the probe fired once, en0 up kernel-side, 1 frame out, a clean
END OF LOG, recycle; Android finally took the slot). Two field facts correct v17:

  1. The probe's answer on an un-armed pair is NOT the raw DwcPrepareURB wall code
     (0x8000000C): the loader sees 0x8000000000000007 -- UsbDeviceSend wraps the UsbFn
     failure into EFI_DEVICE_ERROR before it reaches us. v17's stage compared against the
     raw literal, read 7 as "another layer answered", and stopped -- the re-throw (the
     actual fix) never ran. v17b: ANY nonzero probe answer means the submit was rejected,
     i.e. the pair is not armed (a successful submit queues and answers zero) -- keep
     beating to the window's end, log every code on the record, and let the generation's
     verdict drive the re-throw.
  2. The explicit USB->stop() (loader-first-ever vendor call) stays out: start_ex opens
     with the vendor's own StopController (F12 §3.1 T1, proven every boot since v15), so
     the re-throw is "re-signal the init event, the quiet, start_ex again" -- all proven
     paths. The final wall verdict leaves the server up (v16c's proven wall state: the
     session runs, the recycle chain takes the phone home).

usage: patch-loader-v17b.py LOADER_C   (applies on top of the v17-patched file)
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:200]}"
    src = src.replace(old, new)

# ---- the probe beat: any nonzero answer is "not armed" (the field's form: EFI_DEVICE_ERROR
# wrapped by UsbDeviceSend; the raw 0x8000000C never reaches the loader) ------------------------
sub(
"""			probe = USB->send(USB_EP_OUT, 0, usb_rx_buf);   /* the zero-length probe: the submit
			                                                   path reads the state byte and
			                                                   answers the wall code from it */
			if (probe == 0) {
				USB->abort_xfer(USB_EP_OUT);    /* the probe was queued: take it back out --
			                                       its Cancelled completion is dropped
			                                       harmlessly by the serve paths */
				verdict = 1;
				break;
			}
			print("usb: bulk probe gen %d beat %d: %x\\n", (uint64_t)gen, (uint64_t)beat, probe);
			if ((probe & 0xffffffffULL) != 0x8000000CULL) {
				verdict = 2;
				break;
			}
		}
		if (verdict == 1) {
			print("usb: the bulk pair answered: armed at generation %d, beat %d\\n",
			    (uint64_t)gen, (uint64_t)beat);
			break;
		}
		if (verdict == 2) {
			print("usb: a non-wall probe answer stopped the stage; the session goes on as it stands\\n");
			break;
		}
		if (gen == 2) {
			print("usb: the wall stands after 3 generations (%x): the server comes down, the run goes on without it\\n",
			    probe);
			USB->stop();
			usb_ready = 0;
			usb_rx_queued = 0;
			break;
		}
		print("usb: the wall stands after generation %d: the bring-up is stopped and thrown again\\n",
		    (uint64_t)(gen + 1));
		USB->stop();
		usb_ready = 0;
		usb_rx_queued = 0;
		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (stalled = 0; stalled < 25; stalled++) {
				BS->stall(1000000);
			}
		}
		if (usb_start_attempt() <= 0) {
			print("usb: the re-throw did not come back; the run goes on without the USB server\\n");
			break;
		}
	}""",
"""			probe = USB->send(USB_EP_OUT, 0, usb_rx_buf);   /* the zero-length probe: the submit
			                                                   path reads the state byte; an
			                                                   un-armed pair answers an error
			                                                   (Boot #34's field form:
			                                                   UsbDeviceSend wraps the wall in
			                                                   EFI_DEVICE_ERROR -- 7-shaped,
			                                                   not the raw 0x8000000C) */
			if (probe == 0) {
				USB->abort_xfer(USB_EP_OUT);    /* the probe was queued: take it back out --
			                                       its Cancelled completion is dropped
			                                       harmlessly by the serve paths */
				verdict = 1;
				break;
			}
			print("usb: bulk probe gen %d beat %d: %x\\n", (uint64_t)gen, (uint64_t)beat, probe);
			/* any nonzero answer = the submit was rejected = the pair is not armed: the next
			 * beat gives the host's SET_CONFIG walk another five seconds (the codes stay on
			 * the record -- they are the next attribution round's input) */
		}
		if (verdict == 1) {
			print("usb: the bulk pair answered: armed at generation %d, beat %d\\n",
			    (uint64_t)gen, (uint64_t)beat);
			break;
		}
		if (gen == 2) {
			print("usb: the pair never armed across 3 generations (last %x): the session goes on over ep0 alone (v16c's proven state)\\n",
			    probe);
			break;
		}
		print("usb: the pair is un-armed after generation %d (last %x): the bring-up is thrown again (the next start_ex stops the controller itself)\\n",
		    (uint64_t)(gen + 1), probe);
		usb_rx_queued = 0;
		usb_init_kick();     /* the platform's bring-up callback again, behind the quiet window */
		print("usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try\\n");
		if (tick != NULL) {
			set_timer(tick, 2 /* TimerRelative */, 250000000 /* twenty-five seconds, in 100 ns */);
			wait_for_event(1, &tick, &index);
		} else {
			for (stalled = 0; stalled < 25; stalled++) {
				BS->stall(1000000);
			}
		}
		if (usb_start_attempt() <= 0) {
			print("usb: the re-throw did not come back; the run goes on without the USB server\\n");
			usb_ready = 0;
			break;
		}
	}""")

assert src != orig, "the v17b delta changed nothing"
open(path, "w", encoding="utf-8", newline="").write(src)

for needle in (b"the pair never armed across 3 generations",
               b"the pair is un-armed after generation %d (last %x)",
               b"UsbDeviceSend wraps the wall in",
               b"the re-throw did not come back"):
    assert needle in src.encode(), f"pin string missing after patch: {needle}"
assert src.count("USB->stop()") == 0, "an explicit stop survived"
assert "a non-wall probe answer stopped the stage" not in src, "the old discriminator print survived"
print("patched", path)
print("v17b: any-nonzero probe = not armed (keep beating); explicit USB->stop() gone; final verdict keeps the server up")
