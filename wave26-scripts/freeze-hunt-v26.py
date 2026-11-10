#!/usr/bin/env python3
"""Wave 26: the freeze hunt (single Windows-libusb owner, run by hand).

The v21 kernel's poll heartbeat ("en0 <n>" in `oem netstat`) froze mid-session
under the wave25 load pattern, with the RX ring full and `lost` climbing -- the
same K1 signature as v20. This tool drives one kernel session alone:

  1. open a live kernel session (tunnel25w's stale-devnode opener)
  2. `oem netmode on`, then push the wave25 load shape (ARP requests + TCP SYN
     retries) while sampling `oem netstat` every few seconds
  3. the poll heartbeat (en0 <n>) tells live vs frozen: frozen twice in a row
     = the hunt is over
  4. whatever the moment's state: `oem netmode off`, then `oem log` + `upload`
     = the kernel's own log (the loader composes it live), saved to a file
  5. every frame the kernel sent is histogrammed by ethertype (the wave25
     mystery: 140 frames up, arp_in 0 -- what ARE the kernel's replies?)

usage: python freeze-hunt-v26.py LOG_OUT [SECONDS]
"""
import collections
import os
import struct
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave25-scripts"))
import importlib.util
_spec = importlib.util.spec_from_file_location("t25w", os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))
t25w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t25w)

import loader_talk as lt13  # noqa: E402
lt21 = t25w.lt21

HOST_IP, PEER_IP = "10.0.0.1", "10.0.0.2"
LOG_OUT = sys.argv[1]
HUNT_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 180.0


def arp_request():
    pkt = struct.pack(">HHBBH", 1, lt21.ETHERTYPE_IPV4, 6, 4, 1) + \
        lt21.HOST_MAC + lt21.ip4(HOST_IP) + b"\0" * 6 + lt21.ip4(PEER_IP)
    return b"\xff" * 6 + lt21.HOST_MAC + struct.pack(">H", lt21.ETHERTYPE_ARP) + pkt


def syn():
    src, dst, seq = 26427, 22, 0x1000
    opt = struct.pack(">BBH", 2, 4, lt21.MSS)
    hdr = struct.pack(">HHIIBBHHH", src, dst, seq, 0, 0x60, lt21.SYN, 65535, 0, 0) + opt
    pseudo = lt21.ip4(HOST_IP) + lt21.ip4(PEER_IP) + struct.pack(">BBH", 0, 6, len(hdr))
    c = lt21.checksum(pseudo + hdr)
    hdr = hdr[:16] + struct.pack(">H", c) + hdr[18:]
    return lt21.EN0_MAC + lt21.HOST_MAC + struct.pack(">H", 0x0800) + lt21.ipv4_packet(HOST_IP, PEER_IP, 6, hdr)


def netstat_parse(text):
    # "tx 12 lost 0 rx 34 lost 0 held 2 0 en0 1"
    try:
        f = text.split()
        return {"tx": int(f[1]), "txlost": int(f[3]), "rx": int(f[5]), "rxlost": int(f[7]),
                "held": (int(f[9]), int(f[10])), "en0": int(f[12])}
    except Exception:
        return None


def main():
    lib = lt13.Libusb()
    sess = t25w.open_fresh_session(lib)
    if sess is None:
        print("no live session on the bus")
        return 1
    pipe = t25w.Pipe25(lib, sess)
    try:
        probe = pipe.command("oem recording", 2500)
        raw = (probe.raw or b"") + (probe.payload or b"")
        print("phase probe: %r" % raw[:60])
        if b"kernel is running" not in raw:
            print("not a kernel session; exiting for a later window")
            return 5
        pipe.command("oem netmode on", 2500)
        print("netmode on; hunting the freeze for %.0f s" % HUNT_SECONDS)
        t0 = time.time()
        types = collections.Counter()
        got = 0
        beats = []
        frozen = False
        sample_no = 0
        while time.time() - t0 < HUNT_SECONDS:
            batch = [arp_request() for _ in range(5)] + [syn()]
            try:
                pipe.push(batch)
                time.sleep(0.5)
                for fr in pipe.fetch():
                    got += 1
                    types[struct.unpack(">H", fr[12:14])[0] if len(fr) >= 14 else -1] += 1
                ns = netstat_parse(pipe.command("oem netstat", 2500).raw.decode("utf-8", "replace"))
                if ns:
                    sample_no += 1
                    beats.append(ns["en0"])
                    frozen = len(beats) >= 2 and beats[-1] == beats[-2] and (ns["rxlost"] or ns["held"][1])
                    print("[%5.1fs] sample %2d: tx %d (lost %d) rx %d (lost %d) held %s en0 %d | "
                          "pushed %d fetched %d err %d | types %s"
                          % (time.time() - t0, sample_no, ns["tx"], ns["txlost"], ns["rx"], ns["rxlost"],
                             ns["held"], ns["en0"], pipe.pushed, pipe.uploaded, pipe.errors, dict(types)))
                    if frozen:
                        print("HEARTBEAT FROZEN: en0 %d twice with the ring backing up -- K1 reproduced" % ns["en0"])
                        break
            except lt13.DeviceError as e:
                print("device error at %.1fs: %s" % (time.time() - t0, e))
                break
        try:
            pipe.command("oem netmode off", 2500)
        except Exception:
            pass
        # the kernel's log (the loader composes it live while the kernel runs)
        try:
            pipe.command("oem log", 8000)
            up = pipe.command("upload", 15000)
            if up.status == "DATA" and up.payload:
                with open(LOG_OUT, "wb") as f:
                    f.write(up.payload)
                print("kernel log: %d bytes -> %s" % (len(up.payload), LOG_OUT))
                text = up.payload.decode("utf-8", "replace")
                print("--- kernel log tail (last 40 lines) ---")
                for line in text.strip().splitlines()[-40:]:
                    print("  |%s" % line)
        except Exception as e:
            print("log pull failed: %s" % e)
        print("hunt over: frozen=%s samples=%d beats=%s" % (frozen, sample_no, beats[-6:]))
        return 0
    finally:
        try:
            lt13.disconnect(lib, sess)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
