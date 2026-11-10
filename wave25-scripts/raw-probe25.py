#!/usr/bin/env python3
"""Wave 25: the in-session RAW upload probe (single owner, run by hand).

The service-window probe proved upload answers DATA0+OKAY there (and that an
unread OKAY wedges the loader until drained). In the KERNEL SESSION the tunnel's
upload still says "no answer" -- so this probe bypasses every parser and prints
RAW bulk-IN bytes with timestamps, to decide whether the in-session IN reply is
sent-and-missed or never sent at all:

  getvar:version          liveness
  oem netstat             en0 alive? (tx 1 = the kernel's startup frame drained)
  oem netmode on          ACK
  getvar:version          serving under netmode in-session?
  upload RAW              the write, then raw reads for 5 s, every chunk printed
  getvar:version          post-upload liveness
  oem netmode off         recovery + liveness
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
            print("%s %-20s -> %s %r" % (stamp(), label, resp.status, resp.payload), flush=True)
        else:
            print("%s %-20s -> %r" % (stamp(), label, resp), flush=True)

    def raw_write(cmd):
        wire = lt13.LoaderProto.encode_command(cmd)
        buf = (ctypes.c_ubyte * len(wire)).from_buffer_copy(wire)
        moved = ctypes.c_int(0)
        r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_out"], buf, len(wire),
                                         ctypes.byref(moved), 3000)
        print("%s raw write %r -> r=%s moved=%d" % (stamp(), cmd, lib.errname(r) if r else "OK",
                                                    moved.value), flush=True)

    def raw_reads(seconds):
        end = time.time() + seconds
        got = 0
        while time.time() < end:
            data, nread, err = lt13.bulk_in(lib, sess, 800)
            if nread > 0:
                got += nread
                print("%s raw read +%d B: %r" % (stamp(), nread, data[:80]), flush=True)
            elif err and "TIMEOUT" in str(err):
                continue
            else:
                print("%s raw read err: %s" % (stamp(), err), flush=True)
                break
        print("%s raw reads done: %d B total" % (stamp(), got), flush=True)

    ask("getvar:version", "getvar:version")
    ask("oem recording (phase oracle)", "oem recording")   # FAIL text tells the phase
    ask("oem netstat", "oem netstat")
    ask("oem netmode on", "oem netmode on")
    ask("getvar:version", "getvar:version")
    raw_write("upload")
    raw_reads(5.0)
    ask("getvar:version", "getvar:version")
    ask("oem netmode off", "oem netmode off")
    ask("getvar:version", "getvar:version")
    try:
        lt13.disconnect(lib, sess)
    except Exception:
        pass
    lib.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
