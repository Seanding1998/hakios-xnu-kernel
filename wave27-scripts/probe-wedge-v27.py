#!/usr/bin/env python3
"""Wave 27: the wedged-pair diagnostic (run by hand while the hunt is paused).

A loader that accepts bulk-OUT but answers nothing -- which command set, if
any, does it still serve? Writes one candidate command at a time, reads 4 s,
drains strays, and reports each answer verbatim. Zero state changes beyond the
commands themselves (netmode off is deliberate: if the wedge is a persisted
net mode, this is the key that unlocks it)."""
import ctypes
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402

CMDS = ["oem recording", "oem netstat", "oem netmode off", "getvar:product"]


def main():
    lib = lt13.Libusb()
    plist, n = lib.device_list()
    sess = None
    addr = None
    try:
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                addr = lib.dll.libusb_get_device_address(plist[i])
                h = ctypes.c_void_p()
                if lib.dll.libusb_open(plist[i], ctypes.byref(h)) != 0:
                    print("addr %s: open failed" % addr)
                    continue
                lib.dll.libusb_set_configuration(h, 1)
                lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
                cfg = ctypes.POINTER(lt13.ConfigDescriptor)()
                lib.dll.libusb_get_active_config_descriptor(plist[i], ctypes.byref(cfg))
                iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
                if iface is None or lib.dll.libusb_claim_interface(h, iface) != 0:
                    lib.dll.libusb_close(h)
                    print("addr %s: claim failed" % addr)
                    continue
                sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out,
                        "ep_in": ep_in, "maxpkt": ifd.endpoint[0].wMaxPacketSize}
                break
        if sess is None:
            print("no openable d00d")
            return 1
        # drain whatever is pending first
        got = 0
        for _ in range(3):
            data, nread, err = lt13.bulk_in(lib, sess, 1500)
            if nread:
                got += nread
                print("pre-drain: %d B %r" % (nread, bytes(data[:nread])[:80]))
        print("pre-drain total: %d B" % got)
        for cmd in CMDS:
            try:
                resp = lt13.transact(lib, sess, cmd, 4000, quiet=True)
            except lt13.DeviceError as e:
                resp = None
                print("%-16s -> DeviceError: %s" % (cmd, e))
                continue
            if resp is None:
                print("%-16s -> no answer" % cmd)
            else:
                print("%-16s -> %s raw=%r payload=%r" % (
                    cmd, resp.status, (resp.raw or b"")[:60], (resp.payload or b"")[:60]))
            # drain strays between commands
            for _ in range(2):
                data, nread, err = lt13.bulk_in(lib, sess, 800)
                if nread:
                    print("  stray: %d B %r" % (nread, bytes(data[:nread])[:60]))
        lt13.disconnect(lib, sess)
    finally:
        lib.free_list(plist, n)
        lib.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
