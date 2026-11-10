#!/usr/bin/env python3
"""Wave 26 Phase A -- the 8 targeted regressions (in-memory packets, no device).

Drive the REAL fixed code (wave21's Link/Tunnel via wave25's own module
bindings, wave25's Pipe25, wave26's timed-ssh verdict discipline) with
constructed bytes and scripted USB answers:

  1. ARP request -> a reply with the four fields RFC 826 requires (swapped)
  2. ARP reply    -> learned (the old opcode check dropped every reply)
  3. valid SYN-ACK -> the final ACK carries seq=ISN+1 and ack=their seq+1
  4. a SYN-ACK that does not acknowledge our SYN establishes nothing
  5. cross-port SYN-ACK / cross-port RST leave the connection alone
  6. cumulative / partial / duplicate ACKs move retransmit state exactly
  7. DATA with a short/missing/late terminal OKAY is identified and healed
  8. a stale verdict file from an old run does not pass a new failing run

usage: python regression-phase-a.py     (exit 0 = all green)
"""
import importlib.util
import os
import struct
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the module layout tunnel25w itself assumes: wave13's loader_talk occupies the
# "loader_talk" name; wave21's Link/Tunnel come along as tunnel25w's lt21
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
sys.path.insert(0, os.path.join(REPO, "wave26-scripts"))
import loader_talk as lt13  # noqa: E402  -- wave13's plumbing, as tunnel25w sees it

import tunnel25w_stub  # noqa: F402,E402  (imports tunnel25w; restores sys.stdout)
t25w = tunnel25w_stub.t25w
LT21 = t25w.lt21                        # wave21's Link/Tunnel (the fixed code)
HOST_IP = "10.0.0.1"
PEER_IP = "10.0.0.2"
EN0_MAC = LT21.EN0_MAC
HOST_MAC = LT21.HOST_MAC

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  PASS %-58s %s" % (name, detail))
    else:
        FAIL.append(name)
        print("  FAIL %-58s %s" % (name, detail))


# ---------------------------------------------------------------- helpers

def eth(dst, src, ethertype, payload):
    return dst + src + struct.pack(">H", ethertype) + payload


def arp_pkt(oper, sender_mac, sender_ip, target_mac, target_ip):
    return struct.pack(">HHBBH", 1, 0x0800, 6, 4, oper) + \
        sender_mac + bytes(int(x) for x in sender_ip.split(".")) + \
        target_mac + bytes(int(x) for x in target_ip.split("."))


def tcp_seg(src_port, dst_port, seq, ack, flags, payload=b"", window=16384,
            src_ip=PEER_IP, dst_ip=HOST_IP):
    """A peer->host TCP segment inside an IPv4 frame, checksummed for real."""
    hdr = struct.pack(">HHIIBBHHH", src_port, dst_port, seq, ack, 0x50, flags,
                      window, 0, 0)
    pseudo = LT21.ip4(src_ip) + LT21.ip4(dst_ip) + struct.pack(">BBH", 0, 6, len(hdr) + len(payload))
    c = LT21.checksum(pseudo + hdr + payload)
    hdr = hdr[:16] + struct.pack(">H", c) + hdr[18:]
    return LT21.ipv4_packet(src_ip, dst_ip, 6, hdr + payload)


def last_ipv4_out(link):
    """Parse the last IPv4 frame the link queued (host->peer)."""
    frame = link.out[-1]
    assert struct.unpack_from(">H", frame, 12)[0] == 0x0800
    pkt = frame[14:]
    off = (pkt[20 + 12] >> 4) * 4
    sport, dport, seq, ack, _x, flags, window, _c, _e = struct.unpack_from(">HHIIBBHHH", pkt[20:40])
    return {"sport": sport, "dport": dport, "seq": seq, "ack": ack, "flags": flags,
            "payload": pkt[20 + off:]}


def connect_in_thread(tun, timeout=3.0):
    """connect() blocks on the handshake event; drive it from a thread so the
    test can feed the SYN-ACK in between."""
    th = threading.Thread(target=tun.connect, kwargs={"timeout": timeout}, daemon=True)
    th.start()
    time.sleep(0.15)
    return th


# ---------------------------------------------------------------- 1+2: ARP

def test_arp():
    print("[1] ARP request -> RFC 826 reply (four fields)")
    link = LT21.Link()
    # the phone's ARP request: who has 10.0.0.1? from en0's MAC/IP, broadcast
    link.on_frame(b"\xff" * 6 + HOST_MAC + struct.pack(">H", 0x0806) +
                  arp_pkt(1, EN0_MAC, PEER_IP, b"\0" * 6, HOST_IP))
    ok_len = len(link.out) == 1
    rep = link.out[-1][14:] if link.out else b""
    ok_eth = bool(link.out) and link.out[-1][:6] == EN0_MAC and link.out[-1][6:12] == HOST_MAC
    oper = struct.unpack_from(">H", rep, 6)[0] if len(rep) >= 8 else 0
    s_mac, s_ip, t_mac, t_ip = rep[8:14], rep[14:18], rep[18:24], rep[24:28]
    check("ARP reply fields (oper=2, sender=us, target=asker)",
          ok_len and ok_eth and oper == 2 and s_mac == HOST_MAC
          and s_ip == LT21.ip4(HOST_IP) and t_mac == EN0_MAC and t_ip == LT21.ip4(PEER_IP),
          "oper=%d sender_ip=%s target_ip=%s" % (oper, LT21.ip4str(s_ip), LT21.ip4str(t_ip)))

    print("[2] ARP reply -> learned (the old opcode gate dropped it)")
    link2 = LT21.Link()
    link2.on_frame(eth(HOST_MAC, EN0_MAC, 0x0806,
                       arp_pkt(2, EN0_MAC, PEER_IP, HOST_MAC, HOST_IP)))
    check("ARP reply learned 10.0.0.2 -> en0's MAC",
          link2.arp.get(PEER_IP) == EN0_MAC and link2.counts["arp_in"] == 1
          and link2.counts["arp_out"] == 0,
          "arp=%s" % link2.arp)


# ---------------------------------------------------------------- 3+4+5: TCP handshake / demux

def establish(link, tun):
    th = connect_in_thread(tun)
    link.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                      tcp_seg(22, tun.src_port, 0x900, tun.initial_seq + 1, LT21.SYN | LT21.ACK)))
    th.join(3.0)


def test_handshake():
    print("[3] valid SYN-ACK -> final ACK with seq=ISN+1, ack=their seq+1")
    link = LT21.Link()
    tun = LT21.Tunnel(link, PEER_IP, 22)
    link.ipv4_handlers.append(tun.on_ipv4)   # the tunnel25w wiring
    th = connect_in_thread(tun, timeout=3.0)
    time.sleep(0.05)
    # capture the SYN's presence: exactly one outbound frame before our answer
    n_syn_at_open = len(link.out)
    link.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                      tcp_seg(22, tun.src_port, 0x900, tun.initial_seq + 1, LT21.SYN | LT21.ACK)))
    th.join(3.0)
    ok_est = tun.state == "ESTABLISHED"
    ackf = last_ipv4_out(link)
    check("handshake final ACK seq/ack/flags",
          ok_est and n_syn_at_open == 1
          and ackf["seq"] == (tun.initial_seq + 1) & 0xffffffff
          and ackf["ack"] == 0x901 and ackf["flags"] == LT21.ACK
          and tun.acked == tun.seq == (tun.initial_seq + 1) & 0xffffffff,
          "out=%d seq=%#x ack=%#x flags=%#x state=%s"
          % (n_syn_at_open, ackf["seq"], ackf["ack"], ackf["flags"], tun.state))

    print("[4] a SYN-ACK that does not acknowledge our SYN establishes nothing")
    link4 = LT21.Link()
    tun4 = LT21.Tunnel(link4, PEER_IP, 22)
    link4.ipv4_handlers.append(tun4.on_ipv4)
    th4 = connect_in_thread(tun4)
    link4.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                       tcp_seg(22, tun4.src_port, 0x900, tun4.initial_seq + 2, LT21.SYN | LT21.ACK)))
    th4.join(1.5)
    check("wrong-ack SYN-ACK ignored (state SYN_SENT, no ACK emitted)",
          tun4.state == "SYN_SENT" and tun4.failed is None and len(link4.out) == 1,
          "state=%s out=%d" % (tun4.state, len(link4.out)))

    print("[5] cross-port SYN-ACK / cross-port RST leave the connection alone")
    link5 = LT21.Link()
    tun5 = LT21.Tunnel(link5, PEER_IP, 22)
    link5.ipv4_handlers.append(tun5.on_ipv4)
    th5 = connect_in_thread(tun5)
    link5.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                       tcp_seg(2323, tun5.src_port, 0x900, tun5.initial_seq + 1, LT21.SYN | LT21.ACK)))
    link5.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                       tcp_seg(2323, tun5.src_port, 0x900, 0, LT21.RST)))
    th5.join(1.0)
    check("cross-port SYN-ACK and RST dropped (still SYN_SENT, not failed)",
          tun5.state == "SYN_SENT" and tun5.failed is None and link5.counts["dropped"] >= 2,
          "state=%s failed=%r dropped=%d" % (tun5.state, tun5.failed, link5.counts["dropped"]))
    # and after the connection IS established, a cross-port RST must not kill it
    establish(link5, tun5)
    was = tun5.state == "ESTABLISHED"
    link5.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                       tcp_seg(2323, tun5.src_port, 0x1234, 0, LT21.RST)))
    check("cross-port RST after establishment does not close",
          was and tun5.state == "ESTABLISHED" and tun5.failed is None,
          "state=%s failed=%r" % (tun5.state, tun5.failed))
    # while a cross-port-PLAUSIBLE RST from the true peer does close, with evidence
    link5.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                   tcp_seg(22, tun5.src_port, tun5.ack_of_peer, 0, LT21.RST)))
    check("same-4-tuple RST closes, the verdict carries the tuple",
          tun5.state == "CLOSED" and tun5.failed is not None
          and "10.0.0.2:22" in tun5.failed and "seq=" in tun5.failed,
          "failed=%r" % tun5.failed)


# ---------------------------------------------------------------- 6: ACK bookkeeping

def test_ack_bookkeeping():
    print("[6] cumulative / partial / duplicate ACK vs the retransmit sequence")
    link = LT21.Link()
    tun = LT21.Tunnel(link, PEER_IP, 22)
    link.ipv4_handlers.append(tun.on_ipv4)
    establish(link, tun)
    data_seq = tun.seq
    tun.send(b"0123456789abcdef")            # one 16-byte segment
    seg = tun.unacked[0]
    ok_seg = seg[0] == data_seq and seg[1] == b"0123456789abcdef"
    # a PARTIAL ack (5 bytes): the segment stays whole, nothing over-advances
    link.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                      tcp_seg(22, tun.src_port, 0x900, data_seq + 5, LT21.ACK)))
    kept = bool(tun.unacked) and tun.unacked[0][0] == data_seq and tun.unacked[0][1] == seg[1]
    # a cumulative ack (everything): the segment drops, acked lands exactly
    link.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                      tcp_seg(22, tun.src_port, 0x900, data_seq + 16, LT21.ACK)))
    drained = tun.unacked == [] and tun.acked == (data_seq + 16) & 0xffffffff
    # a duplicate ack (the same number again): nothing left to move
    link.on_frame(eth(EN0_MAC, HOST_MAC, 0x0800,
                      tcp_seg(22, tun.src_port, 0x900, data_seq + 16, LT21.ACK)))
    still = tun.unacked == [] and tun.acked == (data_seq + 16) & 0xffffffff
    # the retransmit re-emits the SAME sequence number, and the timer drives it
    tun.send(b"XYZ")
    tun.unacked[0] = (tun.unacked[0][0], tun.unacked[0][1], time.time() - 3.0)
    tun._retransmit_if_due()
    rex = last_ipv4_out(link)
    check("ack bookkeeping (partial keeps, cumulative drops, dup inert, retransmit same seq)",
          ok_seg and kept and drained and still
          and rex["seq"] == (data_seq + 16) & 0xffffffff and rex["payload"] == b"XYZ",
          "retransmit seq=%#x payload=%r" % (rex["seq"], rex["payload"]))


# ---------------------------------------------------------------- 7: transactions

class ScriptedUsb(object):
    """Feeds Pipe25 through monkeypatched lt13.transact/bulk_in: a queue of
    answers per call, in order."""

    def __init__(self, transact_script, bulkin_script):
        self.t = list(transact_script)
        self.b = list(bulkin_script)
        self.calls_t = 0
        self.calls_b = 0

    def transact(self, lib, sess, text, timeout_ms, quiet=True):
        self.calls_t += 1
        return self.t.pop(0) if self.t else None

    def bulk_in(self, lib, sess, ms):
        self.calls_b += 1
        item = self.b.pop(0) if self.b else (None, 0, "LIBUSB_ERROR_TIMEOUT")
        if item[1] == 0:
            time.sleep(0.05)             # a timed-out read costs real wall time
        return item


def resp(status, raw=None, payload=None):
    return lt13.Response(status, payload, raw=raw if raw is not None else status.encode())


def test_transactions():
    print("[7] DATA with a short/missing/late terminal OKAY")
    stage = lambda frame: struct.pack("<I", len(frame)) + b"\0\0\0\0" + frame
    # (a) DATA then the OKAY arrives LATE (the first raw read sees nothing):
    #     the command still completes, and the pending flag clears
    usb = ScriptedUsb([resp("DATA", payload=stage(b"Z" * 16))],
                      [(None, 0, "TIMEOUT"), (b"OKAY", 4, None)])
    lt13.bulk_in = usb.bulk_in
    lt13.transact = usb.transact
    pipe = t25w.Pipe25(object(), object())
    frames = pipe.fetch()
    check("DATA + late OKAY completed in one command",
          pipe.pending_okay is False and usb.calls_b >= 2 and frames == [b"Z" * 16],
          "frames=%r pending=%s reads=%d" % (frames, pipe.pending_okay, usb.calls_b))

    # (b) an OKAY that never comes: the command returns but the debt is on the
    #     books, and the NEXT command completes the debt before it goes out
    usb2 = ScriptedUsb([resp("DATA", payload=stage(b"Y" * 16)),
                        resp("OKAY", raw=b"OKAY")],
                       [(None, 0, "TIMEOUT"), (None, 0, "TIMEOUT"),
                        (b"OKAY", 4, None)])
    lt13.bulk_in = usb2.bulk_in
    lt13.transact = usb2.transact
    pipe2 = t25w.Pipe25(object(), object())
    pipe2.drain_seconds = 0.08             # the OKAY never arrives inside this budget
    pipe2.fetch()
    debt = pipe2.pending_okay is True
    ok2 = pipe2.command("oem netstat")
    check("missing OKAY: debt carried, next command completes it first",
          debt and pipe2.pending_okay is False and usb2.calls_b == 3 and ok2.status == "OKAY",
          "debt=%s pending=%s raw reads=%d" % (debt, pipe2.pending_okay, usb2.calls_b))

    # (c) a PARTIAL (desynced) reply: drain to the OKAY, retry the command once
    usb3 = ScriptedUsb([resp("PARTIAL", raw=b"OKAYxnuloaderxnuloader"),
                        resp("DATA", payload=stage(b"W" * 8)),
                        resp("OKAY", raw=b"OKAY")],
                       [(b"OKAY", 4, None), (b"OKAY", 4, None)])
    lt13.bulk_in = usb3.bulk_in
    lt13.transact = usb3.transact
    pipe3 = t25w.Pipe25(object(), object())
    pipe3.drain_seconds = 0.15
    r3 = pipe3.command("getvar:version")
    check("PARTIAL reply drained to OKAY and the command retried once",
          r3.status == "DATA" and usb3.calls_t == 2 and pipe3.pending_okay is False,
          "transacts=%d status=%s" % (usb3.calls_t, r3.status))

    # (d) a PARTIAL twice in a row is a named error, not a silent desync
    usb4 = ScriptedUsb([resp("PARTIAL", raw=b"garbage"), resp("PARTIAL", raw=b"garbage")],
                       [(b"OKAY", 4, None), (b"OKAY", 4, None)])
    lt13.bulk_in = usb4.bulk_in
    lt13.transact = usb4.transact
    pipe4 = t25w.Pipe25(object(), object())
    try:
        pipe4.command("getvar:version")
        named = False
    except lt13.DeviceError as e:
        named = "partial" in str(e).lower()
    check("PARTIAL twice raises the named desync error", named)


# ---------------------------------------------------------------- 8: verdict freshness

def test_verdict_freshness():
    print("[8] an old verdict file does not pass a new failing run")
    run_id = "REG8"
    stale = os.path.join(REPO, "wave26-scripts", "verdict26-%s.txt" % run_id)
    if os.path.exists(stale):
        os.remove(stale)
    with open(stale, "w", encoding="utf-8") as f:
        f.write("WAVE21-SSH-OK\nwhen: STALE from an old run\n")

    spec = importlib.util.spec_from_file_location(
        "timed_ssh_v26_reg8", os.path.join(REPO, "wave26-scripts", "timed-ssh-v26.py"))
    mod = importlib.util.module_from_spec(spec)

    class FakePopen(object):
        """miss: communicate returns no marker and a non-zero rc"""
        pid = 424242

        def __init__(self, cmd, stdout=None, stderr=None):
            self.cmd = cmd

        def communicate(self, timeout=None):
            return b"", b"Connection timed out during banner exchange"

        @property
        def returncode(self):
            return 255

    class FakeTaskkill(object):
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            class R(object):
                returncode = 0
            return R()

    real_run = sp_run_holder["run"]

    def fake_run(*a, **k):                   # the tree-kill call: record only
        real_run(["true"], capture_output=True)
        class R(object):
            returncode = 0
        return R()

    sp_run_holder["run"] = fake_run
    spec.loader.exec_module(mod)
    # after exec, mod.subprocess is the real module; replace its Popen/run for
    # the duration of the run
    real_popen = mod.subprocess.Popen
    mod.subprocess.Popen = FakePopen
    mod.subprocess.run = fake_run
    old_argv = sys.argv
    sys.argv = ["timed-ssh-v26.py", "--continuous", "--deadline-minutes", "0.1",
                "--run-id", run_id]
    rc = mod.main()
    sys.argv = old_argv
    mod.subprocess.Popen = real_popen
    mod.subprocess.run = real_run
    # the failing run must not have written any verdict of its own: the stale
    # file's content stands untouched (and the runbook rotates verdicts per run)
    untouched = os.path.exists(stale) and "STALE from an old run" in open(stale, encoding="utf-8").read()
    check("a failing run writes no verdict, even with a stale one on file",
          rc == 5 and untouched,
          "rc=%s stale-untouched=%s" % (rc, untouched))
    if os.path.exists(stale):
        os.remove(stale)


sp_run_holder = {"run": None}

if __name__ == "__main__":
    import subprocess as sp_run_mod
    sp_run_holder["run"] = sp_run_mod.run
    print("Wave 26 Phase A regressions (the fixed code under test)")
    print("under test: %s" % LT21.__file__)
    test_arp()
    test_handshake()
    test_ack_bookkeeping()
    test_transactions()
    test_verdict_freshness()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        sys.exit(1)
    sys.exit(0)
