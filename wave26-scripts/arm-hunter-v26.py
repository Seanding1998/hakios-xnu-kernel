#!/usr/bin/env python3
"""Wave 26 Phase B -- the arming hunter.

The loader's bulk pair arms only while its 3-generation arming loop is running
(loader boot +0..~4 min): every host SET_CONFIG + bulk-OUT write in that window
completes the standing receive and arms the pair ("armed at generation %d, beat
%d"). After the loop gives up, the boot is ep0-only -- everything bulk is dead
no matter what the host does.

This hunter: watches the bus for a fresh xnuloader appearance and hammers
SET_CONFIG + a real bulk command every ~2 s for the whole window. The moment a
write completes, the pair is armed: it logs ARMED and exits 0 (the campaign
then runs on the live pair).

usage: python arm-hunter-v26.py [WINDOW_SECONDS]
"""
import ctypes
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402

WINDOW = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
LOG = os.path.join(REPO, "wave26-scripts", "arm-hunter.log")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


LIB = lt13.Libusb()   # one context for the whole hunt (a fresh Libusb per
                      # attempt leaks a dll directory each time -- the env
                      # block overflowed at attempt ~600)


def open_and_write_once():
    """One open + SET_CONFIG + a real bulk command. Returns 'ARMED' when the
    write completes, 'DEAD' when it times out, None when the device is not
    openable right now."""
    import ctypes as c
    lib = LIB
    sess = None
    try:
        plist, n = lib.device_list()
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                h = c.c_void_p()
                r = lib.dll.libusb_open(plist[i], c.byref(h))
                if r != 0:
                    continue
                lib.dll.libusb_set_configuration(h, 1)   # the arm trigger's first half
                lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
                cfg = c.POINTER(lt13.ConfigDescriptor)()
                if lib.dll.libusb_get_active_config_descriptor(plist[i], c.byref(cfg)) != 0:
                    lib.dll.libusb_close(h)
                    continue
                iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
                if iface is None:
                    lib.dll.libusb_free_config_descriptor(cfg)
                    lib.dll.libusb_close(h)
                    continue
                if lib.dll.libusb_claim_interface(h, iface) != 0:
                    lib.dll.libusb_free_config_descriptor(cfg)
                    lib.dll.libusb_close(h)
                    continue
                sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out,
                        "ep_in": ep_in, "maxpkt": ifd.endpoint[0].wMaxPacketSize}
                break
        if sess is None:
            return None
        # the arm trigger: a real command over the bulk pair
        resp = lt13.transact(lib, sess, "getvar:version", 2500, quiet=True)
        if resp is not None and resp.status in ("OKAY", "DATA"):
            lt13.disconnect(lib, sess)
            return "ARMED"
        lt13.disconnect(lib, sess)
        return "DEAD"
    except Exception as e:
        # the LIB context is shared across attempts: never close it here
        return "ERR:%s" % str(e)[:50]


def main():
    log("arming hunter armed (%.0f s window): fresh xnuloader -> SET_CONFIG + bulk write every ~2 s"
        % WINDOW)
    t0 = time.time()
    armed_at = None
    attempts = 0
    while time.time() - t0 < WINDOW:
        r = open_and_write_once()
        attempts += 1
        if r == "ARMED":
            armed_at = time.time()
            log("ARMED after %d attempts (%.0f s into the window) -- the pair is live, run the campaign"
                % (attempts, armed_at - t0))
            return 0
        if attempts % 5 == 0 or r is None:
            log("attempt %d: %s" % (attempts, r if r is not None else "device not openable"))
        time.sleep(1.5)
    log("the window closed without an arming (%d attempts)" % attempts)
    return 5


if __name__ == "__main__":
    sys.exit(main())
