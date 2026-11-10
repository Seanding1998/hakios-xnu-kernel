#!/usr/bin/env python3
"""Wave 26: the loader revival probe (the H4 discipline): a loader wedged on an
unread reply resumes the moment one raw bulk-IN drains it. Drain a few reads,
then getvar:product as the liveness arbiter. Single owner, run by hand.
"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402


def main():
    lib = lt13.Libusb()
    sess = None
    plist, n = lib.device_list()
    import ctypes
    for i in range(n):
        d = lib.device_desc(plist[i])
        if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
            h = ctypes.c_void_p()
            r = lib.dll.libusb_open(plist[i], ctypes.byref(h))
            if r != 0:
                print("open failed: %s" % lib.errname(r))
                continue
            lib.dll.libusb_set_configuration(h, 1)
            lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
            cfg = ctypes.POINTER(lt13.ConfigDescriptor)()
            lib.dll.libusb_get_active_config_descriptor(plist[i], ctypes.byref(cfg))
            iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
            if iface is None:
                lib.dll.libusb_close(h)
                continue
            assert lib.dll.libusb_claim_interface(h, iface) == 0
            sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out, "ep_in": ep_in,
                    "maxpkt": ifd.endpoint[0].wMaxPacketSize}
            break
    if sess is None:
        print("no openable d00d")
        return 1
    total = 0
    for r in range(6):
        try:
            data, nread, err = lt13.bulk_in(lib, sess, 2000)
            if nread:
                total += nread
                print("drain %d: %d bytes: %r" % (r, nread, bytes(data[:nread])[:60]))
            else:
                print("drain %d: nothing (%s)" % (r, err))
        except Exception as e:
            print("drain %d: %s" % (r, e))
    # if nothing drained, the loader's bulk loop is deaf: a hot bus reset makes
    # its controller raise the disconnect event, which retires the standing
    # receive and re-arms on the next enumeration (the wave25 port-event cure,
    # without touching the cable)
    if total == 0:
        try:
            rv = lib.dll.libusb_reset_device(sess["handle"])
            print("hot reset: %s (%s)" % (rv, "device re-enumerating" if rv == 0 else "refused"))
            time.sleep(6)
        except Exception as e:
            print("hot reset failed: %s" % e)
    try:
        resp = lt13.transact(lib, sess, "getvar:product", 4000, quiet=True)
        print("getvar:product -> %r" % ((resp.raw or b"") if resp else None))
    except Exception as e:
        print("getvar after drain: %s" % e)
    lt13.disconnect(lib, sess)
    print("drained %d bytes total" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
