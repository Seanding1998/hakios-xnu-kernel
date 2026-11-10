#!/usr/bin/env python3
"""Wave 27: the one-shot phase probe (run by hand, before the hunt owns the
device). Asks `oem recording` of every openable d00d and prints the phase:
loader (pre-exec / post-session) or a live kernel session. One command, then
off the wire -- the caller decides what the answer means."""
import ctypes
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402


def main():
    lib = lt13.Libusb()
    plist, n = lib.device_list()
    found = 0
    try:
        for i in range(n):
            d = lib.device_desc(plist[i])
            if not (d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D):
                continue
            found += 1
            addr = lib.dll.libusb_get_device_address(plist[i])
            h = ctypes.c_void_p()
            r = lib.dll.libusb_open(plist[i], ctypes.byref(h))
            if r != 0:
                print("addr %d: open failed (%s)" % (addr, lib.errname(r)))
                continue
            lib.dll.libusb_set_configuration(h, 1)
            lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
            cfg = ctypes.POINTER(lt13.ConfigDescriptor)()
            lib.dll.libusb_get_active_config_descriptor(plist[i], ctypes.byref(cfg))
            iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
            if iface is None:
                lib.dll.libusb_close(h)
                print("addr %d: no bulk pair" % addr)
                continue
            if lib.dll.libusb_claim_interface(h, iface) != 0:
                print("addr %d: claim failed" % addr)
                lib.dll.libusb_close(h)
                continue
            sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out,
                    "ep_in": ep_in, "maxpkt": ifd.endpoint[0].wMaxPacketSize}
            try:
                resp = lt13.transact(lib, sess, "oem recording", 3000, quiet=True)
            except lt13.DeviceError as e:
                print("addr %d: probe failed: %s" % (addr, e))
                resp = None
            if resp is None:
                print("addr %d: no answer" % addr)
            else:
                raw = (resp.raw or b"") + (resp.payload or b"")
                phase = ("KERNEL-LIVE" if b"kernel is running" in raw else "LOADER-PHASE")
                print("addr %d: %s (raw %r)" % (addr, phase, raw[:60]))
            lt13.disconnect(lib, sess)
    finally:
        lib.free_list(plist, n)
        lib.close()
    if not found:
        print("no d00d on the bus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
