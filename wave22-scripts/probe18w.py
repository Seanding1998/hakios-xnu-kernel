#!/usr/bin/env python3
"""Wave 22 probe W: the Windows-side libusb sampler.

The device now ENUMERATES on the Windows bus (the xnuloader WinUSB binding -- v18's
present+pump work), which is exactly what the old "Windows libusb is blind" verdict was
missing: that verdict was taken on a device that never enumerated. This sampler ignores
usbipd/WSL entirely: it polls Windows libusb for the gadget; when it appears it tries
open+claim straight away, and on an un-configured device it does set_configuration(1)
first (the T2 trigger from the host's side), then one getvar write. Every step is logged
with its exact libusb error name.
"""
import ctypes
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt  # noqa: E402

OUT = os.path.join(REPO, "wave22-scripts", "probe18w.log")

def log(msg):
    line = "[probe18w %s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)

def find_gadget(lib):
    plist, n = lib.device_list()
    try:
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                return plist[i], plist, n
    finally:
        pass
    return None, plist, n

def attempt(lib, dev):
    desc = lib.device_desc(dev)
    sess = None
    try:
        h, cfg, iface, ep_out, ep_in, ifd = lt.open_and_claim(lib, dev, desc)
        sess = {"handle": h, "ep_out": ep_out, "ep_in": ep_in}
        log("open+claim ok (iface %d, ep 0x%02x/0x%02x) -- device already CONFIGURED"
            % (iface, ep_out, ep_in))
    except lt.DeviceError as e:
        msg = str(e)
        log("open+claim failed: %s" % msg)
        if "get_active_config" in msg:
            log("the device is UN-CONFIGURED: issuing set_configuration(1) (the T2 trigger)")
            h = ctypes.c_void_p()
            r = lib.dll.libusb_open(dev, ctypes.byref(h))
            if r != 0:
                log("libusb_open: %s" % lib.errname(r))
                return
            r = lib.dll.libusb_set_configuration(h, 1)
            log("set_configuration(1): %s" % (lib.errname(r) if r else "ok  <== the host's T2 shot"))
            lib.dll.libusb_close(h)
            return
        return
    if sess:
        try:
            resp = lt.transact(lib, sess, "getvar:result", 8000)
            if resp is None:
                log("getvar:result -> NO RESPONSE (the write landed, nothing came back)")
            else:
                log("getvar:result -> %s payload=%r"
                    % (resp.status, (resp.payload or b"")[:120]))
        except lt.DeviceError as e:
            log("transact failed: %s" % e)
        finally:
            lib.dll.libusb_release_interface(sess["handle"], sess.get("iface", 0)) if False else None
            lib.dll.libusb_close(sess["handle"])

def main():
    lib = lt.Libusb()
    deadline = time.time() + 60 * 45
    n = 0
    shots = 0
    while time.time() < deadline:
        n += 1
        dev, plist, cnt = find_gadget(lib)
        if dev is None:
            if n % 30 == 1:
                log("no gadget on the Windows bus (pass %d)" % n)
            time.sleep(2)
            continue
        log("gadget visible on the WINDOWS bus (pass %d)" % n)
        try:
            attempt(lib, dev)
            shots += 1
        finally:
            lib.free_list(plist, cnt)
        if shots >= 6:
            log("six shots taken; keep sampling until the deadline")
        time.sleep(3)

if __name__ == "__main__":
    main()
