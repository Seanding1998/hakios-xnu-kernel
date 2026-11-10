#!/usr/bin/env python3
"""Wave 25: the upload-in-netmode定性 probe (single owner, run by hand).

The E2E attempts die at pump.once's first `upload` after `oem netmode on` ("no
answer"), while netmode's own OKAY answers instantly. This probe walks the exact
step sequence with per-step timing, in whatever phase the loader is in:

  1 getvar:version        liveness
  2 oem netmode on        the ACK
  3 getvar:version        serving under netmode?
  4 upload                THE TEST (empty ring answers DATA0+OKAY by design)
  5 getvar:version        did the upload kill the IN channel?
  6 oem netstat           the ring's counters
  7 oem netmode off       recovery
  8 getvar:version        final liveness
"""
import ctypes
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402

_spec = importlib.util.spec_from_file_location("lt21w", os.path.join(REPO, "wave21-scripts", "loader_talk.py"))
lt21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lt21)


def main():
    lib = lt13.Libusb()
    plist, n = lib.device_list()
    dev = None
    for i in range(n):
        d = lib.device_desc(plist[i])
        if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
            dev = plist[i]
            break
    if dev is None:
        print("no d00d on the bus")
        return 1
    h = ctypes.c_void_p()
    r = lib.dll.libusb_open(dev, ctypes.byref(h))
    assert r == 0, lib.errname(r)
    lib.dll.libusb_set_configuration(h, 1)
    lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
    cfg = ctypes.POINTER(lt13.ConfigDescriptor)()
    r = lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
    iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
    r = lib.dll.libusb_claim_interface(h, iface)
    assert r == 0, lib.errname(r)
    sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out, "ep_in": ep_in,
            "maxpkt": ifd.endpoint[0].wMaxPacketSize}

    def step(label, cmd, timeout_ms=4000):
        t0 = time.time()
        try:
            resp = lt13.transact(lib, sess, cmd, timeout_ms, quiet=True)
        except lt13.DeviceError as e:
            resp = "EXC:" + str(e)
        dt = time.time() - t0
        if isinstance(resp, lt13.Response):
            print("%-22s -> %s %r (%.2fs)" % (label, resp.status, resp.payload, dt), flush=True)
        else:
            print("%-22s -> %r (%.2fs)" % (label, resp, dt), flush=True)
        return resp

    step("1 getvar:version", "getvar:version")
    step("2 oem netmode on", "oem netmode on")
    step("3 getvar:version", "getvar:version")
    step("4 upload (THE TEST)", "upload", 6000)
    step("5 getvar:version", "getvar:version")
    step("6 oem netstat", "oem netstat")
    step("7 oem netmode off", "oem netmode off")
    step("8 getvar:version", "getvar:version")
    lt13.disconnect(lib, sess)
    lib.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
