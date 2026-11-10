#!/usr/bin/env python3
"""Wave 25: the tunnel-vs-raw bisect. The real tunnel dies at its first `upload`
("no answer", 4 s, nothing on IN) minutes into a session, while a raw probe's
upload seconds earlier answers DATA0+OKAY instantly. This script replays the
tunnel's exact opening (claim, getvar:product, netmode on) then:

  upload via lt13.transact (the tunnel's exact call)     -> answer or not
  ...immediately raw bulk-IN reads for 4 s more          -> late bytes?
  getvar:version                                          -> is the loader alive?
  upload via lt13.transact AGAIN                          -> retry behavior
  getvar:version + netmode off                            -> recovery
"""
import ctypes
import sys
import time

REPO = r"<host>\.zcode\workspace\9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7\hakios-phk110"
sys.path.insert(0, REPO + r"\wave13-scripts")
import loader_talk as lt13  # noqa: E402


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
    lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
    iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
    r = lib.dll.libusb_claim_interface(h, iface)
    assert r == 0, lib.errname(r)
    sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out, "ep_in": ep_in,
            "maxpkt": ifd.endpoint[0].wMaxPacketSize}
    t0 = time.time()

    def stamp():
        return "[t+%.2f]" % (time.time() - t0,)

    def ask(label, cmd, timeout_ms=4000):
        try:
            resp = lt13.transact(lib, sess, cmd, timeout_ms, quiet=True)
        except lt13.DeviceError as e:
            resp = "EXC:" + str(e)
        if isinstance(resp, lt13.Response):
            print("%s %-26s -> %s %r" % (stamp(), label, resp.status, resp.payload), flush=True)
        else:
            print("%s %-26s -> %r" % (stamp(), label, resp), flush=True)
        return resp

    def raw_reads(seconds):
        end = time.time() + seconds
        total = 0
        while time.time() < end:
            data, nread, err = lt13.bulk_in(lib, sess, 500)
            if nread > 0:
                total += nread
                print("%s   raw +(%d) %r" % (stamp(), nread, data[:64]), flush=True)
            elif err and "TIMEOUT" in str(err):
                continue
            else:
                print("%s   raw err %s" % (stamp(), err), flush=True)
                break
        print("%s   raw total %d B" % (stamp(), total), flush=True)

    ask("1 getvar:product (arbiter)", "getvar:product")
    ask("2 oem netmode on", "oem netmode on")
    ask("3 upload (tunnel's call)", "upload", 4000)
    print("%s 4 late reads after the failed upload:" % stamp(), flush=True)
    raw_reads(4.0)
    ask("5 getvar:version (alive?)", "getvar:version")
    ask("6 upload retry", "upload", 4000)
    raw_reads(2.0)
    ask("7 getvar:version", "getvar:version")
    ask("8 oem netmode off", "oem netmode off")
    ask("9 getvar:version", "getvar:version")
    try:
        lt13.disconnect(lib, sess)
    except Exception:
        pass
    lib.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
