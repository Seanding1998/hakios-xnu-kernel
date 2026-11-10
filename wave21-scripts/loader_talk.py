#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""loader_talk.py - Wave 21: the host's side of en0's link over the xnuloader USB byte pipes.

The loader (v15, BLOCK_VERSION 4) ends its shared page with a ring of Ethernet frames: the
kernel's en0 fills the send ring, and frames the host drops into `download:` reach en0. The
loader's "oem netmode" points the `upload`/`download:` pipes at that ring; "oem netstat" tells
how it is going. This tool drives both pipes and speaks the protocols of a small host end:

  inherited from Wave 13 (same arguments, unchanged):
    list | probe | cmd <ascii> | log | dllinfo | selftest
  new:
    netmode [--loopback] [--frames N] [--seconds S] [--stats-every N]
                            N1: turn net mode on, push test frames, watch the ring answer
                              (the kernel's en0 itself answers a 0x88b5/"W21" frame back).
    ping <ip> [--count N] [--size S] [--interval S]
                            N2: ICMP echo over the bridge (the frame path, built here; the
                              phone's own inet stack answers).
    tunnel <ip> <port>      N3: a small TCP for OpenSSH's ProxyCommand -- ssh carries its
                              transport over this tool's stdin/stdout while this tool carries
                              the TCP packets over the ring:
                                ssh -i key -o ProxyCommand="python loader_talk.py tunnel 10.0.0.2 22" root@10.0.0.2
    tun --adapter NAME --addr 10.0.0.1
                            wintun's frame relay instead of the two above (needs an elevated
                            prompt: WintunCreateAdapter refuses a plain one, ERROR_ACCESS_DENIED
                            on this machine 2026-11-08; the netmode/ping/tunnel trio is the
                            unattended path).

Wave 21.2's pipe guardian: every device-opening mode first self-checks the usbipd/WSL pipe
(the F9 dead-export disease is cured by one detach->attach surgery per device generation; a
generation that stays visible but never answers gets the same single cure only after the
loader's boot-time tries are spent; every surgery is followed by a random 4-9 s pause). Set
LOADER_TALK_NO_GUARD=1 to turn the guardian off.

Frame format over both pipes: a little-endian u32 length, then that many bytes of one Ethernet
frame; batches of them, one `download:` per batch, one `upload` per poll.

The host's identity on the link: MAC 02:68:61:6b:69:01, IP 10.0.0.1 (en0 is 10.0.0.2/30, the
loader's channel between them). ARP is answered here (the kernel ARPs for its peer before it
sends to it), ICMP echo is answered by the phone's own stack, and TCP belongs to ssh and sshd --
this tool only carries the packets, and keeps the small book TCP asks of a sender (sequence,
window, retransmit, enough of the closing hand to end a connection cleanly).

Exit codes: 0 ok, 1 device/protocol failure, 2 usage, 3 selftest failure (Wave 13's), 4 tunnel
or ping failed.
"""

import argparse
import ctypes.util
import faulthandler
import os
import random
import shutil
import struct
import subprocess
import sys
import threading
import time

faulthandler.enable(all_threads=True)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt          # noqa: E402  (Wave 13's plumbing: Libusb, connect, transact...)

# The tool is Windows-born (Wave 13: libusb-1.0.dll by ctypes), and Wave 21 runs it in WSL as
# well -- the whole session's USB (fastboot flash, then the loader's pipes) stays on the WSL side
# of usbipd, which is also what keeps the Windows-side WinUSB binding out of the VBoxUSB trap
# (docs/STATUS: the persisted xnuloader share). On Linux the loader is the system one.
if os.name == "nt":
    DEFAULT_LOADER_DLL = lt.DEFAULT_DLL
else:
    DEFAULT_LOADER_DLL = None
    for _candidate in (ctypes.util.find_library("usb-1.0"), "libusb-1.0.so.0"):
        if not _candidate:
            continue
        for _dir in ("/usr/lib64", "/lib64", "/usr/lib", "/lib", "/usr/lib/x86_64-linux-gnu"):
            _path = os.path.join(_dir, _candidate)
            if os.path.isfile(_path):
                DEFAULT_LOADER_DLL = _path
                break
        if DEFAULT_LOADER_DLL:
            break
    DEFAULT_LOADER_DLL = DEFAULT_LOADER_DLL or "/usr/lib64/libusb-1.0.so.0"

# the host end of the channel
HOST_MAC = bytes.fromhex("0268616b6901")     # 02:68:61:6b:69:01
EN0_MAC = bytes.fromhex("0268616b6902")      # what en0 answers ARP with its side
HOST_IP = "10.0.0.1"
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_ARP = 0x0806
MSS = 1400                                   # TCP payload per segment (a frame of 1454 bytes)
RING_FRAME_MAX = 1600


def ip4(text):
    """'10.0.0.2' -> the four bytes on the wire."""
    return bytes(int(x) for x in text.split("."))


def connect(lib, args):
    """Wave 13's connect, with the one re-ordering Linux demands: libusb_free_device_list unrefs
    the devices, and after it every pointer taken from the list is dead -- device speed, the
    strings, the active config, and the claim itself all belong while the list is alive (the
    Windows build happened to survive the stale pointers; Linux segfaults, which is how the
    order was found -- Wave 21, the first real-device session of this tool)."""
    import ctypes
    vid = int(args.vid, 16) if args.vid else lt.TARGET_VID
    pid = int(args.pid, 16) if args.pid else lt.TARGET_PID
    plist, n = lib.device_list()
    h = cfg = None
    sess = None
    try:
        dev = desc = None
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == vid and d.idProduct == pid:
                dev, desc = plist[i], d
                break
        if dev is None:
            raise lt.DeviceError("device %04x:%04x not found on this bus (the loader's gadget "
                                 "enumerates only while the loader image runs)" % (vid, pid))
        # everything about the device, while the list is alive
        speed = lib.dll.libusb_get_device_speed(dev)
        loc = "bus %d port %s addr %d speed=%s" % (
            lib.dll.libusb_get_bus_number(dev), lib.port_path(dev),
            lib.dll.libusb_get_device_address(dev), lt.SPEED_NAMES.get(speed, speed))
        strs = lib.strings(dev, desc)
        print("device %04x:%04x @ %s" % (vid, pid, loc))
        for k in ("manufacturer", "product", "serial"):
            if strs.get(k):
                print("  %s: %r" % (k, strs[k]))
        if "error" in strs:
            print("  (string read: %s)" % strs["error"])
        print("  bcdUSB=%04x bDeviceClass=%s bMaxPacketSize0=%d configs=%d" % (
            desc.bcdUSB, lt.class_name(desc.bDeviceClass), desc.bMaxPacketSize0, desc.bNumConfigurations))
        h = ctypes.c_void_p()
        r = lib.dll.libusb_open(dev, ctypes.byref(h))
        if r != lt.LIBUSB_SUCCESS:
            raise lt.DeviceError("libusb_open failed: %s" % lib.errname(r))
        ensure_configured(lib, h)
        cfg = ctypes.POINTER(lt.ConfigDescriptor)()
        r = lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
        if r != lt.LIBUSB_SUCCESS:
            raise lt.DeviceError("libusb_get_active_config_descriptor failed: %s" % lib.errname(r))
        iface, ep_out, ep_in, ifd = lt.pick_iface_eps(cfg.contents)
        if iface is None:
            print(lt.describe_config(cfg.contents))
            raise lt.DeviceError("no interface with a bulk OUT+IN pair found")
        r = lib.dll.libusb_claim_interface(h, iface)
        if r != lt.LIBUSB_SUCCESS:
            print(lt.describe_config(cfg.contents))
            raise lt.DeviceError("libusb_claim_interface(if%d) failed: %s" % (iface, lib.errname(r)))
        print("  OPEN+CLAIM OK (interface %d, class=%s)" % (
            iface, lt.class_name(ifd.bInterfaceClass) if ifd else "?"))
        print(lt.describe_config(cfg.contents))
        sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out, "ep_in": ep_in,
                "maxpkt": (ifd.endpoint[0].wMaxPacketSize if ifd and ifd.bNumEndpoints else 512)}
        return sess
    finally:
        lib.free_list(plist, n)
        if sess is None:
            if cfg is not None:
                lib.dll.libusb_free_config_descriptor(cfg)
            if h is not None and h.value:
                lib.dll.libusb_close(h)


def ensure_configured(lib, handle):
    """Explicit SET_CONFIGURATION(1) before claiming (Wave 21.2's endpoint wall, host side).

    The on-device evidence (Boot #33+ screen): UsbDeviceSend -> DwcPrepareURB:Trb ->
    "physical endpoint[2] not configured" -> PrepareUrb Failed 0x8000000C, one loop per
    loader tick. The vendor state machine only arms the bulk endpoints once the device
    reaches CONFIGURED -- i.e. once the HOST sends SET_CONFIGURATION(1). An enumeration that
    died half-way (the F9 surgery's fresh pipe, a stalled host stack) leaves the device in
    ADDRESS, and then every armed submit the loader makes bounces for the whole session.
    libusb's SET_CONFIGURATION goes out on ep0 (which works: the descriptors were read); if
    the device accepts it, the endpoints arm and the wall stops. Best effort either way:
    the answer to `getvar` decides serving, not this call."""
    import ctypes
    r = lib.dll.libusb_set_configuration(handle, 1)
    if r != 0:
        print("  set_configuration(1): %s" % lib.errname(r), file=sys.stderr)
    else:
        print("  set_configuration(1): ok", file=sys.stderr)
    lib.dll.libusb_set_auto_detach_kernel_driver(handle, 1)


def checksum(data):
    """The internet checksum of the bytes (counted as big-endian words, padded once)."""
    if len(data) % 2:
        data += b"\0"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def ipv4_packet(src, dst, protocol, payload):
    hdr = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), 0x1234, 0x4000, 64, protocol, 0, ip4(src), ip4(dst))
    c = checksum(hdr)
    hdr = hdr[:10] + struct.pack(">H", c) + hdr[12:]
    return hdr + payload


# ---------------------------------------------------------------- the pipes

class Pipe:
    """`upload` and `download:` in net mode, as frames. The log's staging returns with
    `oem netmode off` (the loader's own rule; the ring keeps working underneath)."""

    def __init__(self, lib, sess):
        self.lib = lib
        self.sess = sess
        self.uploaded = 0
        self.pushed = 0
        self.errors = 0

    def _raw_send(self, wire):
        import ctypes
        buf = (ctypes.c_ubyte * len(wire)).from_buffer_copy(wire)
        moved = ctypes.c_int(0)
        r = self.lib.dll.libusb_bulk_transfer(self.sess["handle"], self.sess["ep_out"], buf,
                                              len(wire), ctypes.byref(moved), 4000)
        if r != 0 or moved.value != len(wire):
            raise lt.DeviceError("bulk-OUT failed: %s (%d/%d)" %
                                 (self.lib.errname(r), moved.value, len(wire)))

    def _reply(self, deadline_ms=4000):
        """The DATA/status frame after a command, whole."""
        parser = lt.LoaderProto()
        end = time.time() + deadline_ms / 1000.0
        while True:
            remain = int((end - time.time()) * 1000)
            if remain <= 0:
                return None
            data, n, err = lt.bulk_in(self.lib, self.sess, remain)
            if n > 0:
                resp = parser.feed(data)
                if resp is not None:
                    return resp
                continue
            if err and "TIMEOUT" in str(err):
                continue
            if err:
                raise lt.DeviceError("bulk-IN failed: %s" % err)
            return None

    def command(self, text, timeout_ms=4000):
        resp = lt.transact(self.lib, self.sess, text, timeout_ms, quiet=True)
        if resp is None:
            raise lt.DeviceError("no answer to %r" % text)
        return resp

    def fetch(self):
        """One `upload`: what en0 sent since the last poll. A list of frames."""
        resp = self.command("upload")
        if resp.status == "FAIL":
            self.errors += 1
            return []
        if resp.status != "DATA" or resp.payload is None:
            return []
        blob = resp.payload
        frames = []
        off = 0
        while off + 8 <= len(blob):
            (length,) = struct.unpack_from("<I", blob, off)
            if off + 8 + length > len(blob) or length > RING_FRAME_MAX:
                break                       # a torn batch: the rest is skipped, counted elsewhere
            frames.append(blob[off + 8:off + 8 + length])
            off += 8 + length
        self.uploaded += len(frames)
        return frames

    def push(self, frames):
        """One `download:` carrying every frame given, in length-prefixed pieces."""
        if not frames:
            return True
        blob = b"".join(struct.pack("<I", len(f)) + f for f in frames)
        self._raw_send(b"download:%08x" % len(blob))
        resp = self._reply()
        if resp is None or resp.status != "DATA":
            self.errors += 1
            return False
        for off in range(0, len(blob), 16384):
            self._raw_send(blob[off:off + 16384])
        resp = self._reply()
        if resp is None or resp.status != "OKAY":
            self.errors += 1
            return False
        self.pushed += len(frames)
        return True


# ---------------------------------------------------------------- the little host

class Link:
    """What the host end of the channel knows: ARP for its address, ICMP echo, and one TCP
    (enough for ssh: it is the only thing asked of this link)."""

    def __init__(self, host_ip=HOST_IP):
        self.host_ip = host_ip
        self.arp = {}                            # ip -> mac, learned from asks and traffic
        self.ipv4_handlers = []                  # f(ip_packet) for the protocols that want them
        self.out = []                            # frames to hand to the pipe
        self.counts = {"arp_in": 0, "arp_out": 0, "icmp_in": 0, "icmp_out": 0,
                       "tcp_in": 0, "tcp_out": 0, "dropped": 0}

    def send(self, payload, ethertype):
        self.out.append(EN0_MAC + HOST_MAC + struct.pack(">H", ethertype) + payload)

    def on_frame(self, frame):
        """One frame from the phone (dst, src, type, ...)."""
        if len(frame) < 14:
            self.counts["dropped"] += 1
            return
        ethertype = struct.unpack_from(">H", frame, 12)[0]
        if ethertype == ETHERTYPE_ARP:
            self._on_arp(frame[14:])
        elif ethertype == ETHERTYPE_IPV4:
            self._on_ipv4(frame[14:])

    def _on_arp(self, pkt):
        """RFC 826: requests and replies are different beasts. A request is
        answered (its sender learned first); a reply is pure learning -- the
        reply's sender fields ARE the answer. The old code dropped every reply
        with an opcode check (and built replies with the fields unreversed),
        which is why "arp learned" never saw 10.0.0.2 (Phase A's finding)."""
        if len(pkt) < 28:
            self.counts["dropped"] += 1
            return
        oper = struct.unpack_from(">H", pkt, 6)[0]
        sender_mac = pkt[8:14]
        sender_ip = pkt[14:18]
        target_ip = pkt[24:28]
        if oper == 1:
            self.arp[ip4str(sender_ip)] = sender_mac
            if target_ip == ip4(self.host_ip):
                # the reply swaps the fields: the sender is us, the target the asker
                reply = struct.pack(">HHBBH", 1, ETHERTYPE_IPV4, 6, 4, 2) + \
                    HOST_MAC + ip4(self.host_ip) + sender_mac + sender_ip
                self.send(reply, ETHERTYPE_ARP)
                self.counts["arp_in"] += 1
                self.counts["arp_out"] += 1
        elif oper == 2:
            self.arp[ip4str(sender_ip)] = sender_mac
            self.counts["arp_in"] += 1
        else:
            self.counts["dropped"] += 1

    def _on_ipv4(self, pkt):
        if len(pkt) < 20:
            self.counts["dropped"] += 1
            return
        protocol = pkt[9]
        self.counts["tcp_in" if protocol == 6 else "icmp_in" if protocol == 1 else "dropped"] += 1
        for handler in self.ipv4_handlers:
            handler(pkt)

    def arp_request(self, ip_text):
        pkt = struct.pack(">HHBBH", 1, ETHERTYPE_IPV4, 6, 4, 1) + \
            HOST_MAC + ip4(self.host_ip) + b"\0" * 6 + ip4(ip_text)
        # an Ethernet broadcast, for the case the ring's other end does not have us yet
        self.out.append(b"\xff" * 6 + HOST_MAC + struct.pack(">H", ETHERTYPE_ARP) + pkt)


def ip4str(b):
    return ".".join(str(x) for x in b)


# ---------------------------------------------------------------- TCP (the tunnel's half)

FIN, SYN, RST, PSH, ACK = 0x01, 0x02, 0x04, 0x08, 0x10


class Tunnel:
    """One TCP connection, carried over the ring. OpenSSH's ProxyCommand gives this its stdin
    and stdout; sshd on the phone gives the other half. What is kept: sequence numbers and the
    peer's window, a retransmit of the oldest unacknowledged segment, an ACK for what arrives in
    order (a duplicate ACK for what does not), and the closing hands."""

    def __init__(self, link, dst_ip, dst_port):
        self.link = link
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.src_port = 0x4000 + (int(time.time() * 1000) & 0x3fff)
        self.state = "CLOSED"
        self.initial_seq = 0x10000000            # the ISN this connection was born with
        self.seq = self.initial_seq              # this end's next byte to send
        self.acked = self.seq                    # what the peer has acknowledged
        self.ack_of_peer = 0                     # what we owe an acknowledgment for
        self.peer_window = 16384
        self.my_window = 16384
        self.unacked = []                        # (seq, payload, first-sent time)
        self.in_order = b""                      # data for the reader (stdout)
        self.closed_by_peer = False
        self.fin_sent = False
        self.failed = None
        self.opened = threading.Event()

    # -- packets ---------------------------------------------------------

    def _segment(self, flags, payload=b"", seq=None, ack=None):
        if seq is None:
            seq = self.seq
        if ack is None:
            ack = self.ack_of_peer
        off_flags = (5 << 12) | flags
        hdr = struct.pack(">HHIIBBHHH", self.src_port, self.dst_port, seq, ack, 0x50, off_flags,
                          self.my_window, 0, 0)
        pseudo = ip4(self.link.host_ip) + ip4(self.dst_ip) + struct.pack(">BBH", 0, 6, len(hdr) + len(payload))
        c = checksum(pseudo + hdr + payload)
        tcp = hdr[:16] + struct.pack(">H", c) + hdr[18:] + payload
        return ipv4_packet(self.link.host_ip, self.dst_ip, 6, tcp)

    def _emit(self, flags, payload=b"", seq=None, ack=None, record=True):
        if seq is None:
            seq = self.seq
        self.link.send(self._segment(flags, payload, seq, ack), ETHERTYPE_IPV4)
        self.link.counts["tcp_out"] += 1
        if payload and record:
            self.unacked.append((seq, payload, time.time()))
            self.seq = (seq + len(payload)) & 0xffffffff

    # -- the connection --------------------------------------------------

    def open_syn(self):
        """The handshake's open, owned by the state machine: the SYN goes out
        (with the MSS option) and this end's sequence number consumes it
        immediately (SND.NXT = ISN+1) -- so the handshake's final ACK and every
        data segment carry the right sequence number from the start (Phase A:
        the old code emitted the final ACK with the un-consumed ISN, off by
        one, and patched the advance afterwards in the wrapper; it also packed
        the offset/flags word into a 'B' each, which is the crash wave25's H5
        wrapper patch had been papering over)."""
        self.state = "SYN_SENT"
        # the data-offset (6 words: the MSS option) and the flags each take
        # their own byte -- never a shifted word in a 'B' slot
        hdr = struct.pack(">HHIIBBHHH", self.src_port, self.dst_port, self.initial_seq, 0,
                          6, SYN, self.my_window, 0, 0) + \
            struct.pack(">BBH", 2, 4, MSS)
        pseudo = ip4(self.link.host_ip) + ip4(self.dst_ip) + struct.pack(">BBH", 0, 6, len(hdr))
        c = checksum(pseudo + hdr)
        hdr = hdr[:16] + struct.pack(">H", c) + hdr[18:]
        self.link.send(ipv4_packet(self.link.host_ip, self.dst_ip, 6, hdr), ETHERTYPE_IPV4)
        self.link.counts["tcp_out"] += 1
        self.seq = (self.initial_seq + 1) & 0xffffffff

    def resyn(self):
        """A re-SYN inside SYN_SENT: the original ISN again (never the consumed
        sequence number), for the wrapper's retry loop."""
        if self.state == "SYN_SENT":
            self._emit(SYN, seq=self.initial_seq, record=False)

    def connect(self, timeout=8.0):
        self.open_syn()
        if not self.opened.wait(timeout):
            self.failed = self.failed or "no SYN-ACK in %ds (is en0 up? is sshd?)" % int(timeout)
            return False
        return True

    def send(self, data):
        """stdin's bytes, as segments while the peer's window allows."""
        if self.state != "ESTABLISHED":
            return False
        while data:
            self._retransmit_if_due()
            while self.unacked and self.seq - self.acked > min(self.peer_window, 8192):
                time.sleep(0.002)
                self._retransmit_if_due()
            take = data[:MSS]
            self._emit(PSH | ACK, take)
            data = data[len(take):]
        return True

    def _retransmit_if_due(self):
        if self.unacked and time.time() - self.unacked[0][2] > 1.5:
            seq0, payload0, _ = self.unacked[0]
            self._emit(PSH | ACK, payload0, seq=seq0, record=False)
            self.unacked[0] = (seq0, payload0, time.time())

    def on_ipv4(self, pkt):
        if self.state == "CLOSED" or len(pkt) < 20 or pkt[9] != 6:
            return
        if ip4str(pkt[12:16]) != self.dst_ip:
            return
        off = (pkt[20 + 12] >> 4) * 4            # the TCP header's own length
        if len(pkt) < 20 + off:
            return
        (sport, dport, seq, ack, _x, flags, window, _c, _e) = struct.unpack_from(">HHIIBBHHH", pkt[20:40])
        payload = pkt[20 + off:]
        # the connection's demux (Phase A): only this 4-tuple's peer is ours to
        # hear -- a segment for any other port (another connection's RST, say)
        # is dropped here, before it can touch the state machine
        if sport != self.dst_port or dport != self.src_port:
            self.link.counts["dropped"] += 1
            return
        self.peer_window = window
        if flags & RST:
            # an RST is believed only when its sequence plausibly belongs to
            # this conversation (inside a bounded distance of what we owe an
            # acknowledgment for); the evidence travels with the verdict
            rcv_nxt = self.ack_of_peer
            ahead = (seq - rcv_nxt) & 0xffffffff
            behind = (rcv_nxt - seq) & 0xffffffff
            if ahead < 0x20000000 or behind < 0x20000000:
                self.failed = ("reset by peer (raddr %s:%u -> %s:%u seq=%u rcv_nxt=%u)"
                               % (ip4str(pkt[12:16]), sport, ip4str(pkt[16:20]), dport, seq, rcv_nxt))
                self.state = "CLOSED"
                self.opened.set()
            else:
                self.link.counts["dropped"] += 1
            return
        if self.state == "SYN_SENT":
            # the handshake's one true answer: SYN|ACK with our ISN acknowledged
            if flags & SYN and flags & ACK and \
                    ack == (self.initial_seq + 1) & 0xffffffff:
                self.ack_of_peer = (seq + 1) & 0xffffffff
                self.acked = self.seq            # the peer acknowledged our SYN byte
                self._emit(ACK)                  # the final ACK, seq already ISN+1
                self.state = "ESTABLISHED"
                self.opened.set()
                self._absorb(seq, payload, flags)
            else:
                # an answer that does not acknowledge this SYN is not one
                self.link.counts["dropped"] += 1
            return
        if not (flags & ACK):
            return
        # the peer's acknowledgment: drop the segments it covers
        while self.unacked and (self.unacked[0][0] + len(self.unacked[0][1])) <= (ack & 0xffffffff):
            self.acked = (self.unacked[0][0] + len(self.unacked[0][1])) & 0xffffffff
            self.unacked.pop(0)
        self._absorb(seq, payload, flags)
        if flags & FIN:
            self.ack_of_peer = (seq + len(payload) + 1) & 0xffffffff
            self._emit(ACK)
            self.closed_by_peer = True

    def _absorb(self, seq, payload, flags):
        seq &= 0xffffffff
        if payload:
            if seq == self.ack_of_peer:
                self.in_order += payload
                self.ack_of_peer = (seq + len(payload)) & 0xffffffff
                self._emit(ACK)
            elif seq < self.ack_of_peer and seq + len(payload) > self.ack_of_peer:
                # the tail of an old segment: the part we have not got is ours to keep
                keep = self.ack_of_peer - seq
                self.in_order += payload[keep:]
                self.ack_of_peer = (seq + len(payload)) & 0xffffffff
                self._emit(ACK)
            else:
                self._emit(ACK, seq=self.seq, ack=self.ack_of_peer)   # a duplicate ACK

    def drain(self, size=1 << 20):
        out = self.in_order[:size]
        self.in_order = self.in_order[len(out):]
        return out

    def half_close(self):
        """stdin is done: the FIN, once. (ssh sends nothing more; sshd may still be writing.)"""
        if self.state == "ESTABLISHED" and not self.fin_sent:
            self.fin_sent = True
            self._emit(FIN | ACK)

    def close(self, linger=3.0):
        if self.state != "ESTABLISHED" and not self.unacked:
            return
        self.half_close()
        end = time.time() + linger
        while time.time() < end and self.unacked:
            self._retransmit_if_due()
            time.sleep(0.005)


# ---------------------------------------------------------------- the pump

class Pump:
    """Move frames both ways, until told to stop: `upload` each tick (en0's send ring), and one
    `download:` with whatever the link has for en0."""

    def __init__(self, lib, sess, link, tick=0.005):
        self.pipe = Pipe(lib, sess)
        self.link = link
        self.tick = tick
        self.stop = False

    def once(self):
        for frame in self.pipe.fetch():
            self.link.on_frame(frame)
        if self.link.out:
            out, self.link.out = self.link.out[:32], self.link.out[32:]
            self.pipe.push(out)

    def run(self, seconds=None):
        end = time.time() + seconds if seconds else None
        while not self.stop and (end is None or time.time() < end):
            try:
                self.once()
            except lt.DeviceError as e:
                print("loader_talk: pipe error: %s" % e, file=sys.stderr)
                return False
            time.sleep(self.tick)
        return True


# ---------------------------------------------------------------- modes

def do_netmode(lib, args):
    """N1: the ring's round trip. The kernel's en0 answers a 0x88b5 "W21..." frame by sending
    it straight back out; `oem netstat` keeps the counts of the loader's drains and pushes."""
    sess = connect(lib, args)
    try:
        pipe = Pipe(lib, sess)
        print("netstat before :", pipe.command("oem netstat").payload.decode("ascii", "replace"))
        print("netmode on     :", pipe.command("oem netmode on").payload.decode("ascii", "replace"))
        test = (b"\xff" * 6 + HOST_MAC + struct.pack(">H", 0x88b5) + b"W21" +
                bytes(range(14, 14 + (args.size - 17))))
        got = 0
        sent = 0
        t0 = time.time()
        while time.time() - t0 < args.seconds and got < args.frames:
            if sent < args.frames:
                pipe.push([test])
                sent += 1
            for frame in pipe.fetch():
                if frame[12:14] == b"\x88\xb5" and frame[14:16] == b"W21" and frame[14:] == test[14:]:
                    got += 1
                    print("loopback frame %d answered (%d bytes, %d bytes test)" %
                          (got, len(frame), len(test)))
            time.sleep(args.interval)
        print("netstat after  :", pipe.command("oem netstat").payload.decode("ascii", "replace"))
        print("netmode off    :", pipe.command("oem netmode off").payload.decode("ascii", "replace"))
        verdict = "PASS" if got == args.frames and sent == args.frames else "FAIL"
        print("N1 verdict: %s (%d sent, %d echoed)" % (verdict, sent, got))
        return 0 if verdict == "PASS" else 4
    finally:
        lt.disconnect(lib, sess)


def do_ping(lib, args):
    """N2: ICMP echo over the bridge. The request is built here; the reply comes from the
    phone's own inet stack, which is the point: the datagram path of en0 works."""
    sess = lt.connect(lib, args)
    ensure_configured(lib, sess["handle"])
    try:
        link = Link()
        pipe = Pipe(lib, sess)
        pipe.command("oem netmode on")
        pump = Pump(lib, sess, link)
        sent_at = {}
        received = []

        def icmp_watch(pkt):
            if pkt[9] == 1 and len(pkt) >= 24:
                itype, _code, _c, iid, iseq = struct.unpack_from(">BBHHH", pkt, 20)
                if itype == 0 and iid == args.ident and iseq in sent_at:
                    received.append((iseq, (time.time() - sent_at[iseq]) * 1000.0))
        args.ident = os.getpid() & 0xffff
        link.ipv4_handlers.append(icmp_watch)
        print("PING %s (%d bytes of payload) over the loader's channel" % (args.ip, args.size))
        t0 = time.time()
        for seq in range(1, args.count + 1):
            while time.time() - t0 < (seq - 1) * args.interval:
                pump.once()
                time.sleep(0.005)
            body = struct.pack(">BBHHH", 8, 0, 0, args.ident, seq) + \
                bytes((seq * 7 + i) & 0xff for i in range(args.size))
            body = body[:2] + struct.pack(">H", checksum(body)) + body[4:]
            link.send(ipv4_packet(HOST_IP, args.ip, 1, body), ETHERTYPE_IPV4)
            link.arp_request(args.ip)
            sent_at[seq] = time.time()
            deadline = time.time() + args.interval * 2
            while time.time() < deadline:
                pump.once()
                if received and received[-1][0] == seq:
                    break
                time.sleep(0.005)
            if received and received[-1][0] == seq:
                print("reply from %s: icmp_seq=%d bytes=%d time=%.1f ms" %
                      (args.ip, seq, args.size, received[-1][1]))
            else:
                print("no reply to icmp_seq=%d" % seq)
        print("netstat:", pipe.command("oem netstat").payload.decode("ascii", "replace"))
        pipe.command("oem netmode off")
        verdict = "PASS" if len(received) == args.count else "PARTIAL" if received else "FAIL"
        print("N2 verdict: %s (%d of %d replies)" % (verdict, len(received), args.count))
        return 0 if len(received) == args.count else 4
    finally:
        lt.disconnect(lib, sess)


def do_tunnel(lib, args):
    """N3: OpenSSH's ProxyCommand transport. sshd's transport bytes come in on stdin and go
    out as TCP over the ring; what TCP brings back goes to stdout. usage:
      ssh -i key -o ProxyCommand="python loader_talk.py tunnel 10.0.0.2 22" root@10.0.0.2"""
    sess = lt.connect(lib, args)
    ensure_configured(lib, sess["handle"])

    def stdin_reader(tun):
        while True:
            try:
                data = sys.stdin.buffer.read(4096)
            except Exception:
                return
            if not data:
                tun.half_close()
                return
            if not tun.send(data):
                return

    try:
        link = Link()
        pipe = Pipe(lib, sess)
        pipe.command("oem netmode on")
        tun = Tunnel(link, args.host, args.port)
        link.ipv4_handlers.append(tun.on_ipv4)
        pump = Pump(lib, sess, link)
        # the ring's other end must know where our packets go: ask it (the pump is not
        # running yet, so the list is ours alone here)
        for _ in range(60):
            link.arp_request(args.host)
            pump.once()
            if ip4(args.host) in [ip4(k) for k in link.arp]:
                break
            time.sleep(0.05)
        sys.stderr.write("loader_talk: tunnel to %s:%d over the ring (ARP learned: %s)\n" %
                         (args.host, args.port, sorted(link.arp)))
        pump_thread = threading.Thread(target=pump.run, daemon=True)
        pump_thread.start()
        if not tun.connect():
            sys.stderr.write("loader_talk: %s\n" % tun.failed)
            pump.stop = True
            pump_thread.join(2)
            try:
                pipe.command("oem netmode off")
            except lt.DeviceError:
                pass
            return 4
        sys.stderr.write("loader_talk: established (%s:%d -> %s:%d)\n" %
                         (link.host_ip, tun.src_port, args.host, args.port))
        reader = threading.Thread(target=stdin_reader, args=(tun,), daemon=True)
        reader.start()
        while tun.state == "ESTABLISHED" and not tun.closed_by_peer and not tun.failed:
            out = tun.drain()
            if out:
                sys.stdout.buffer.write(out)
                sys.stdout.buffer.flush()
            tun._retransmit_if_due()
            time.sleep(0.002)
        # what the closing hand brought
        end = time.time() + 1.0
        while time.time() < end:
            out = tun.drain()
            if not out:
                break
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()
            time.sleep(0.002)
        pump.stop = True
        pump_thread.join(2)
        try:
            pipe.command("oem netmode off")
        except lt.DeviceError:
            pass
        if tun.failed:
            sys.stderr.write("loader_talk: %s\n" % tun.failed)
            return 4
        return 0
    finally:
        lt.disconnect(lib, sess)


def do_tun(lib, args):
    """wintun's frame relay (needs an elevated prompt): the adapter carries the Windows side,
    this loop carries the frames between it and the ring. ARP is answered by Windows itself."""
    import ctypes
    dll_path = os.path.join(REPO, "wave21-scripts", "wintun.dll")
    dll = ctypes.CDLL(dll_path, use_last_error=True)
    P = ctypes.c_void_p
    dll.WintunCreateAdapter.restype = P
    dll.WintunCreateAdapter.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, P, ctypes.POINTER(ctypes.c_int)]
    dll.WintunCloseAdapter.argtypes = [P]
    dll.WintunStartSession.restype = P
    dll.WintunStartSession.argtypes = [P, ctypes.c_uint32]
    dll.WintunEndSession.argtypes = [P]
    dll.WintunGetReadWaitEvent.restype = P
    dll.WintunGetReadWaitEvent.argtypes = [P]
    dll.WintunReceivePacket.restype = ctypes.POINTER(ctypes.c_ubyte)
    dll.WintunReceivePacket.argtypes = [P, ctypes.POINTER(ctypes.c_uint32)]
    dll.WintunReleaseReceivePacket.argtypes = [P, P]
    dll.WintunAllocateSendPacket.restype = ctypes.POINTER(ctypes.c_ubyte)
    dll.WintunAllocateSendPacket.argtypes = [P, ctypes.c_uint32]
    dll.WintunSendPacket.argtypes = [P, P]
    rb = ctypes.c_int(0)
    adapter = dll.WintunCreateAdapter(args.adapter, "HakiOS", None, ctypes.byref(rb))
    if not adapter:
        print("wintun: the adapter did not come (error %d) -- an elevated prompt is wanted" % ctypes.get_last_error())
        return 1
    session = dll.WintunStartSession(adapter, 0x400000)
    subprocess.run(["netsh", "interface", "ip", "set", "address", "name=" + args.adapter,
                    "source=static", "addr=" + args.addr, "mask=255.255.255.252"], check=False)
    print("wintun: %s up at %s/30; relaying (Ctrl+C ends)" % (args.adapter, args.addr))
    sess = connect(lib, args)
    try:
        pipe = Pipe(lib, sess)
        pipe.command("oem netmode on")
        wait_event = dll.WintunGetReadWaitEvent(session)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        relayed = 0
        while True:
            for frame in pipe.fetch():
                if len(frame) >= 14 and struct.unpack_from(">H", frame, 12)[0] == ETHERTYPE_IPV4:
                    pkt = frame[14:]
                    buf = dll.WintunAllocateSendPacket(session, len(pkt))
                    if buf:
                        ctypes.memmove(buf, pkt, len(pkt))
                        dll.WintunSendPacket(session, buf)
                        relayed += 1
            # what Windows sent, in one go, as one download
            out = []
            while True:
                size = ctypes.c_uint32(0)
                pkt = dll.WintunReceivePacket(session, ctypes.byref(size))
                if not pkt:
                    break
                data = bytes(ctypes.cast(pkt, ctypes.POINTER(ctypes.c_ubyte * size.value)).contents)
                dll.WintunReleaseReceivePacket(session, pkt)
                if len(data) <= RING_FRAME_MAX - 14:
                    out.append(EN0_MAC + HOST_MAC + struct.pack(">H", ETHERTYPE_IPV4) + data)
                if len(out) >= 32:
                    break
            if out:
                pipe.push(out)
            if k32.WaitForSingleObject(wait_event, 2) == 0xFFFFFFFF:
                pass                    # (a wait of 2 ms is the tick here)
        return 0
    finally:
        lt.disconnect(lib, sess)
        if session:
            dll.WintunEndSession(session)
        dll.WintunCloseAdapter(adapter)


# ---------------------------------------------------------------- the pipe guardian (Wave 21.2)

# Wave 21.1's verdict: the loader's USB server comes up (settle + delayed first try), but the
# host's catch was blocked by two pipe diseases.  F9: usbipd's attach binds to a dead export
# instance -- Windows says Attached while WSL's lsusb sees nothing, and every transfer dies.
# F8: a loader whose start_ex failed keeps the DWC3 half-started -- ep0 enumerates (the device
# is ON THE WIRE) but the bulk endpoints were never armed, so "visible" is not "usable". The
# only cure for F9 is the detach->attach surgery -- but the surgery is also the enumeration
# killer when it lands inside the loader's start_ex window, and a surgery per probe miss (hunt
# v4) poisoned start_ex for real. Hunt v5's proven house rules, now the DEFAULT behavior of
# this tool:
#   * at most one cure per device generation for each disease (a generation = one dark->
#     visible stretch of the gadget on the wire), never one per miss;
#   * the surgery is evidence-gated: the F9 signature (Windows Attached, WSL blind) is cured
#     as soon as it is seen; a generation that stays visible but never answers is left alone
#     until the loader's boot-time tries are all spent (~52 s after the generation began --
#     v16b's tries sit at 25/50/75 s of its boot), so a cure can never cut short a try that
#     was about to succeed;
#   * after every surgery a random 4-9 s pause, so successive generations' surgeries do not
#     sync into a boot phase;
#   * every device-opening mode self-checks the pipe before it opens (this guardian), and a
#     failed operation leaves a miss on the generation's record.
GUARD_STATE = os.environ.get("LOADER_TALK_GUARD_STATE", "/tmp/loader_talk_guardian.state")
GUARD_DARK, GUARD_WATCHING, GUARD_OPERATED = "dark", "watching", "operated"


def _log(tag):
    return lambda msg: print("%s: %s" % (tag, msg), file=sys.stderr, flush=True)


def _usbipd_exe():
    """usbipd.exe's path: sudo's secure_path drops the Windows interop dirs, so the well-known
    install location is the fallback (this tool always runs under sudo on the WSL side)."""
    for cand in (shutil.which("usbipd.exe"), "/mnt/c/Program Files/usbipd-win/usbipd.exe"):
        if cand and os.path.isfile(cand):
            return cand
    return "usbipd.exe"


def _usbipd(*argv, timeout=30):
    try:
        return subprocess.run([_usbipd_exe(), *argv], capture_output=True, text=True,
                              timeout=timeout).stdout
    except Exception as e:
        _log("guardian")("usbipd %s failed: %s" % (" ".join(argv), e))
        return ""


def _wsl_sees_gadget():
    try:
        out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=15).stdout
        return "d00d" in out
    except Exception:
        return False


def _guard_read():
    """(generation, phase, gen-start epoch, misses, last-surgery epoch) -- zero-ish defaults
    when nothing is on file (a wiped /tmp is safe: the next look reads as a new generation)."""
    try:
        gen, phase, began, misses, surg = open(GUARD_STATE).read().split()
        return int(gen), phase, float(began), int(misses), float(surg)
    except Exception:
        return 0, GUARD_DARK, 0.0, 0, 0.0


def _guard_write(gen, phase, began, misses, surg):
    try:
        with open(GUARD_STATE, "w") as f:
            f.write("%d %s %f %d %f" % (gen, phase, began, misses, surg))
    except Exception:
        pass


def _guard_busid():
    for line in _usbipd("list").splitlines():
        if "18d1:d00d" in line:
            return line.split()[0]
    return None


def _guard_surgery(busid, gen, began, note, surg):
    """The detach->attach cure, then a random pause clear of the loader's boot phase."""
    log = _log("guardian")
    log("surgery (%s): detach %s -> attach --wsl" % (note, busid))
    _usbipd("detach", "--busid", busid)
    time.sleep(2)
    _usbipd("attach", "--wsl", "--busid", busid)
    pause = random.uniform(4.0, 9.0)
    log("surgery done; %.1f s pause so the reset lands clear of the loader's start window" % pause)
    time.sleep(pause)
    now = time.time()
    _guard_write(gen, GUARD_OPERATED, began, 0, now)
    return now


def guardian():
    """The pipe's self-check, run before every device-opening mode. The outcomes of previous
    operations (guard_miss/guard_hit) are already on the generation's record: a generation
    that stays dark to every probe gets its one surgery only after the loader's own tries are
    spent."""
    if os.name == "nt" or os.environ.get("LOADER_TALK_NO_GUARD"):
        return                       # the guardian lives where usbipd lives (the WSL side)
    log = _log("guardian")
    gen, phase, began, misses, surg = _guard_read()
    wsl_seen = _wsl_sees_gadget()
    busid = None
    for line in _usbipd("list").splitlines():
        if "18d1:d00d" in line:
            busid = line.split()[0]
            break

    if busid is None:
        if phase != GUARD_DARK:
            log("dark: the gadget left the wire (generation %d over)" % gen)
        _guard_write(gen, GUARD_DARK, 0.0, 0, surg)
        return

    if not wsl_seen:
        # The F9 signature (or a plain never-attached): the pipe is the dead thing, and the
        # loader cannot be reached without it. One cure per generation -- the second look is
        # allowed only half a minute after the first, and only while the pipe stays dead.
        if phase == GUARD_OPERATED and time.time() - surg < 30.0:
            return
        now = time.time()
        if phase == GUARD_DARK:
            gen += 1
            began = now
        _guard_surgery(busid, gen, began, "Windows shows the device, WSL cannot see it", surg)
        return

    if phase != GUARD_WATCHING and phase != GUARD_OPERATED:
        gen += 1
        began = time.time()
        _guard_write(gen, GUARD_WATCHING, began, 0, surg)
        log("generation %d on the wire (%s)" % (gen, busid))

    if phase == GUARD_WATCHING and misses >= 2 and time.time() - began >= 52.0:
        # The generation has been visible and unanswered through two probes, and the loader's
        # boot-time tries (25/50/75 s of its boot, ~52 s past the generation's first sight)
        # are spent: the half-started/dead-pipe state is what remains, and one surgery is what
        # it gets -- none more until the next generation.
        _guard_surgery(busid, gen, began, "visible but unanswered (%d misses)" % misses, surg)


def guard_miss():
    """One unanswered operation on the current generation's record."""
    if os.name == "nt" or os.environ.get("LOADER_TALK_NO_GUARD"):
        return
    gen, phase, began, misses, surg = _guard_read()
    if phase in (GUARD_WATCHING, GUARD_OPERATED):
        _guard_write(gen, phase, began, misses + 1, surg)


def guard_hit():
    """The pipe answered: the generation's miss record clears."""
    if os.name == "nt" or os.environ.get("LOADER_TALK_NO_GUARD"):
        return
    gen, phase, began, _misses, surg = _guard_read()
    _guard_write(gen, phase, began, 0, surg)


# ---------------------------------------------------------------- CLI

def main(argv):
    ap = argparse.ArgumentParser(description="Wave 21: en0's frames over the xnuloader pipes")
    ap.add_argument("--dll", default=os.environ.get("LOADER_TALK_LIBUSB", DEFAULT_LOADER_DLL))
    ap.add_argument("--vid")
    ap.add_argument("--pid")
    ap.add_argument("--iface", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=2000)
    ap.add_argument("--libusb-debug", type=int, default=0)
    sub = ap.add_subparsers(dest="mode")

    sub.add_parser("list", help="enumerate USB devices (Wave 13)")
    sub.add_parser("probe", help="find+open+claim 18d1:d00d (Wave 13)")
    sp = sub.add_parser("cmd", help="send one ASCII command (Wave 13)")
    sp.add_argument("command")
    sp.add_argument("--nl", action="store_true")
    sp = sub.add_parser("log", help="fetch 'oem log' payload to file (Wave 13)")
    sp.add_argument("--out", help="output file (default oem-log.out in this directory)")
    sub.add_parser("dllinfo", help="print libusb runtime info (Wave 13)")
    sub.add_parser("selftest", help="parser tests + safe DLL checks (Wave 13)")

    sp = sub.add_parser("netmode", help="N1: the ring's round trip")
    sp.add_argument("--frames", type=int, default=4, help="test frames to echo")
    sp.add_argument("--size", type=int, default=100, help="test frame's size in bytes")
    sp.add_argument("--seconds", type=float, default=20, help="how long to wait for them")
    sp.add_argument("--interval", type=float, default=0.01)

    sp = sub.add_parser("ping", help="N2: ICMP echo over the bridge")
    sp.add_argument("ip")
    sp.add_argument("--count", type=int, default=4)
    sp.add_argument("--size", type=int, default=64)
    sp.add_argument("--interval", type=float, default=1.0)

    sp = sub.add_parser("tunnel", help="N3: OpenSSH ProxyCommand transport")
    sp.add_argument("host")
    sp.add_argument("port", type=int)

    sp = sub.add_parser("tun", help="wintun's frame relay (elevated prompt)")
    sp.add_argument("--adapter", default="HakiOS")
    sp.add_argument("--addr", default=HOST_IP)

    args = ap.parse_args(argv)
    if args.mode is None:
        ap.print_help()
        return 2
    if args.mode == "selftest":
        ok, fail = lt.selftest(args.dll)
        return 3 if fail else 0

    if args.mode in ("probe", "cmd", "log", "netmode", "ping", "tunnel", "tun"):
        guardian()                   # the pipe's self-check (Wave 21.2; LOADER_TALK_NO_GUARD skips)

    lib = lt.Libusb(args.dll, debug=args.libusb_debug)
    rc = 2
    try:
        if args.mode == "list":
            rc = lt.do_list(lib, args)
        elif args.mode == "probe":
            sess = connect(lib, args)
            print("probe verdict: the gadget opens and claims its interface")
            lt.disconnect(lib, sess)
            rc = 0
        elif args.mode == "cmd":
            sess = connect(lib, args)
            try:
                resp = lt.transact(lib, sess, args.command, args.timeout,
                                   newline=args.nl, quiet=True)
                if resp is None:
                    print("NO RESPONSE (bulk-IN timeout after %d ms)" % args.timeout)
                    rc = 1
                else:
                    print("status : %s" % resp.status)
                    if resp.payload is not None:
                        if len(resp.payload) <= 256:
                            print("payload: %r" % resp.payload)
                        else:
                            print("payload: %d bytes, first 256: %r" % (
                                len(resp.payload), resp.payload[:256]))
                    rc = 0 if resp.status in ("OKAY", "DATA") else 1
            finally:
                lt.disconnect(lib, sess)
        elif args.mode == "log":
            sess = connect(lib, args)
            try:
                resp = lt.transact(lib, sess, "oem log", args.timeout * 3)
                if resp is None or resp.status != "DATA":
                    print("NO RESPONSE to 'oem log'")
                    rc = 1
                else:
                    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "oem-log.out")
                    with open(out, "wb") as f:
                        f.write(resp.payload)
                    print("saved %d bytes -> %s" % (len(resp.payload), out))
                    print(resp.payload[:400].decode("utf-8", "replace"))
                    rc = 0
            finally:
                lt.disconnect(lib, sess)
        elif args.mode == "dllinfo":
            rc = lt.do_dllinfo(lib, args)
        elif args.mode == "netmode":
            rc = do_netmode(lib, args)
        elif args.mode == "ping":
            rc = do_ping(lib, args)
        elif args.mode == "tunnel":
            rc = do_tunnel(lib, args)
        elif args.mode == "tun":
            rc = do_tun(lib, args)
    except lt.DeviceError as e:
        print("DEVICE ERROR: %s" % e)
        rc = 1
    finally:
        lib.close()
    # the generation's record: only a transport-level failure (rc 1) is a miss -- a FAIL/DATA
    # answer or a completed netmode/ping proves the pipe itself is alive.
    if rc == 1:
        guard_miss()
    else:
        guard_hit()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
