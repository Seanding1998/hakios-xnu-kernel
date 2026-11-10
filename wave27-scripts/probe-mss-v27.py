#!/usr/bin/env python3
"""Wave 27: the MSS size-ladder probe (run by hand while the hunt is paused).

A live session where the phone ACKed our 33 B banner but never ACKs our
1400 B KEXINIT. This probe establishes one tunnel (the fixed push-first
flow), then sends PSH|ACK data segments of rising size and reports exactly
which sizes the phone's TCP acknowledges. The threshold = the MSS the en0
path really accepts; timed-ssh's next patch takes it."""
import importlib.util
import os
import struct
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt13  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "t25w", os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))
t25w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t25w)

lt21 = t25w.lt21
SIZES = [160, 170, 180, 190, 200]


def diag(msg):
    sys.stderr.write("mssprobe: %s\n" % msg)
    sys.stderr.flush()


def main():
    lib = lt13.Libusb()
    sess = t25w.open_fresh_session(lib)
    if sess is None:
        print("no live loader")
        return 1
    try:
        resp = lt13.transact(lib, sess, "oem recording", 2500, quiet=True)
        raw = (resp.raw or b"") + (resp.payload or b"") if resp else b""
        if b"kernel is running" not in raw:
            print("loader phase (%r) -- need a live session" % raw[:40])
            return 2
        pipe = t25w.Pipe25(lib, sess)
        link = lt21.Link()
        tun = lt21.Tunnel(link, t25w.PEER_IP, t25w.PEER_PORT)
        link.ipv4_handlers.append(tun.on_ipv4)

        def pump():
            if link.out:
                out, link.out = link.out[:32], link.out[32:]
                pipe.push(out)
            for frame in pipe.fetch():
                link.on_frame(frame)

        pipe.command("oem netmode on", 4000)
        end = time.time() + 4.0
        while time.time() < end:
            link.arp_request(t25w.PEER_IP)
            pump()
            if lt21.ip4(t25w.PEER_IP) in [lt21.ip4(k) for k in link.arp]:
                break
            time.sleep(0.03)
        diag("arp: %s" % sorted(link.arp))

        tun.open_syn()
        end = time.time() + 20.0
        retry_at = 0.0
        while time.time() < end and tun.state != "ESTABLISHED":
            if time.time() > retry_at:
                tun.resyn()
                retry_at = time.time() + 2.0
            pump()
            time.sleep(0.01)
        if tun.state != "ESTABLISHED":
            print("no established (state %s)" % tun.state)
            return 3
        diag("established; banner sent")

        results = []
        for size in SIZES:
            payload = bytes((i * 7) & 0xff for i in range(size))
            tun._emit(lt21.PSH | lt21.ACK, payload)
            acked = False
            end = time.time() + 3.0
            while time.time() < end and not acked:
                pump()
                if tun.unacked:
                    pass
                else:
                    acked = True
                time.sleep(0.01)
            results.append((size, acked))
            diag("size %4d -> %s" % (size, "ACKED" if acked else "not acked in 3s"))
            if not acked:
                # purge the stuck segment so the next size starts clean
                tun.unacked = []
                tun.acked = tun.seq = (tun.seq + size) & 0xffffffff
            time.sleep(0.2)
        print("LADDER: " + " ".join("%d=%s" % (s, "ok" if a else "DROP") for s, a in results))
        try:
            pipe.command("oem netmode off", 3000)
        except lt13.DeviceError:
            pass
        return 0
    finally:
        try:
            lt13.disconnect(lib, sess)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
