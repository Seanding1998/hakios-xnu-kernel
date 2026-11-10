#!/usr/bin/env python3
"""Wave 25: the OpenSSH ProxyCommand: ssh's transport over the loader's net ring.

Host-side realities this wrapper exists for (all established on the device in this
wave):

  1. Win32-OpenSSH "exec"s the ProxyCommand string: a .cmd file dies instantly, a
     direct exe with spaceless paths works.
  2. loader_talk's diagnostic prints share sys.stdout with the ssh transport bytes;
     inside the proxy they corrupt the stream. Diagnostics go to stderr here.
  3. Windows keeps STALE devnodes of past loader generations: the open tries every
     18d1:d00d and keeps the first that answers.
  4. THE BIG ONE: the loader's DATA replies are TWO separate IN transfers (DATA
     header, then a standalone OKAY), each awaited with usb_wait. A reader that
     stops at the DATA frame leaves the OKAY pending and the loader blocks forever
     (wave21's Pipe had never met the real loader; every attempt died at the first
     `upload` and the loader went dark until a drain revived it). Pipe25 below is a
     protocol-exact reimplementation on wave13's primitives: every DATA reply is
     followed by an OKAY drain, downloads never exist without their payload (the
     loader waits 20 s for it otherwise), and `oem netmode on` is known to discard
     whatever the stage held. The userspace half (ARP/ICMP/TCP) stays wave21's own
     Link/Tunnel classes untouched.
"""
import ctypes
import importlib.util
import os
import struct
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W13 = os.path.join(REPO, "wave13-scripts")
W21 = os.path.join(REPO, "wave21-scripts")
sys.path.insert(0, W13)

_real_stdout = sys.stdout


class SplitOut(object):
    """print() writes here -> stderr; sys.stdout.buffer -> the real stdout."""

    def __init__(self, transport, diag):
        self._transport = transport.buffer if hasattr(transport, "buffer") else transport
        self._diag = diag

    @property
    def buffer(self):
        return self._transport

    def write(self, s):
        self._diag.write(s)
        return len(s)

    def writelines(self, lines):
        self._diag.writelines(lines)

    def flush(self):
        self._diag.flush()

    def isatty(self):
        return False


sys.stdout = SplitOut(_real_stdout, sys.stderr)

import loader_talk as lt13  # noqa: E402  -- wave13's plumbing occupies sys.modules

_spec = importlib.util.spec_from_file_location("loader_talk_wave21",
                                               os.path.join(W21, "loader_talk.py"))
lt21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lt21)          # its `import loader_talk` hits wave13's


def _segment25(self, flags, payload=b"", seq=None, ack=None):
    """wave21's Tunnel._segment packed the data-offset/flags word into a 'B'
    (>255 -> struct.error: the TCP layer had never run before this wave). The
    correct header: offset 5 words (0x50), flags, no options (only the SYN
    carries the MSS option, built by hand in run_tunnel)."""
    if seq is None:
        seq = self.seq
    if ack is None:
        ack = self.ack_of_peer
    hdr = struct.pack(">HHIIBBHHH", self.src_port, self.dst_port, seq, ack,
                      0x50, flags & 0xff, self.my_window, 0, 0)
    pseudo = lt21.ip4(HOST_IP) + lt21.ip4(self.dst_ip) + struct.pack(">BBH", 0, 6, len(hdr) + len(payload))
    c = lt21.checksum(pseudo + hdr + payload)
    tcp = hdr[:16] + struct.pack(">H", c) + hdr[18:] + payload
    return lt21.ipv4_packet(HOST_IP, self.dst_ip, 6, tcp)


lt21.Tunnel._segment = _segment25

# wave27 MSS ladder (probe-mss-v27, live session): the phone's TCP ACKed a
# 160 B data segment and silently dropped every 170 B+ one -- the loader's
# host->kernel ring path caps frames near 160 B of TCP payload. Wave21's
# netmode ping validated 100 B frames only (--size default 100); MSS=1400
# was never exercised until the first real KEXINIT, whose 1400 B segments
# vanished into the ring forever (SND.UNA frozen, endless retransmits).
lt21.MSS = 160

HOST_IP = "10.0.0.1"
PEER_IP = "10.0.0.2"
PEER_PORT = 22
RING_FRAME_MAX = 1600


def diag(msg):
    sys.stderr.write("tunnel25w: %s\n" % msg)
    sys.stderr.flush()


def open_fresh_session(lib):
    """Try every d00d on the bus; the arbiter of life is claim+getvar (dead nodes
    and nodes held elsewhere both fail it). Returns the wave13 session, or None."""
    for round_no in range(6):
        plist, n = lib.device_list()
        matches = []
        try:
            for i in range(n):
                d = lib.device_desc(plist[i])
                if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                    matches.append((plist[i], lib.dll.libusb_get_device_address(plist[i])))
            if not matches:
                diag("no d00d on the bus (round %d)" % round_no)
                continue
            diag("round %d: d00d nodes at addr %s" % (round_no, [m[1] for m in matches]))
            for dev, addr in matches:
                h = ctypes.c_void_p()
                r = lib.dll.libusb_open(dev, ctypes.byref(h))
                if r != lt13.LIBUSB_SUCCESS:
                    diag("addr %d: open failed (%s)" % (addr, lib.errname(r)))
                    continue
                r = lib.dll.libusb_set_configuration(h, 1)
                if r != 0:
                    diag("addr %d: set_configuration(1): %s" % (addr, lib.errname(r)))
                lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
                cfg = ctypes.POINTER(lt13.ConfigDescriptor)()
                r = lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
                if r != lt13.LIBUSB_SUCCESS:
                    diag("addr %d: active config failed: %s" % (addr, lib.errname(r)))
                    lib.dll.libusb_close(h)
                    continue
                iface, ep_out, ep_in, ifd = lt13.pick_iface_eps(cfg.contents)
                if iface is None:
                    diag("addr %d: no bulk pair" % addr)
                    lib.dll.libusb_free_config_descriptor(cfg)
                    lib.dll.libusb_close(h)
                    continue
                r = lib.dll.libusb_claim_interface(h, iface)
                if r != lt13.LIBUSB_SUCCESS:
                    diag("addr %d: claim(if%d) failed: %s" % (addr, iface, lib.errname(r)))
                    lib.dll.libusb_free_config_descriptor(cfg)
                    lib.dll.libusb_close(h)
                    continue
                sess = {"handle": h, "cfg": cfg, "iface": iface, "ep_out": ep_out,
                        "ep_in": ep_in,
                        "maxpkt": (ifd.endpoint[0].wMaxPacketSize
                                   if ifd and ifd.bNumEndpoints else 512)}
                # wave27: flush the ring before the identity arbiter -- a queue
                # may hold the last tunnel's kernel frames (acc2's failure mode:
                # a raw getvar read one as a DATA reply and the dance cascaded).
                # One proper upload consumes them as DATA+terminal-OKAY; an
                # empty stage answers just as cleanly. Best effort either way.
                try:
                    fl = lt13.transact(lib, sess, "upload", 1500, quiet=True)
                    if fl is not None and fl.status == "DATA":
                        lt13.bulk_in(lib, sess, 800)   # the standalone OKAY
                except lt13.DeviceError:
                    pass
                try:
                    resp = lt13.transact(lib, sess, "getvar:product", 2000, quiet=True)
                except lt13.DeviceError as e:
                    diag("addr %d: claim ok but the pair is dead (%s)" % (addr, e))
                    lt13.disconnect(lib, sess)
                    continue
                if resp is None or resp.status != "OKAY":
                    diag("addr %d: claim ok but getvar -> %s" % (addr, resp))
                    lt13.disconnect(lib, sess)
                    continue
                diag("addr %d: LIVE (product %r); this is our loader" % (addr, resp.payload))
                return sess
        finally:
            lib.free_list(plist, n)
        time.sleep(1.5)
    return None


class Pipe25(object):
    """The loader's wire, protocol-exact (wave 25's reading of loader.c):

      * every DATA reply = DATA<header> [+ payload transfers] + a standalone OKAY,
        and the loader usb_wait()s each: consume the OKAY or the loader wedges;
      * `upload` in net mode = net_poll + DATA<stage> [+ stage bytes] + OKAY;
      * `download:<hex>` = DATA<total> ack, then the loader usb_rx's the payload
        with a 20 s timeout, then OKAY / FAIL short download: never queue a
        download without sending the payload right behind it;
      * `oem netmode on` resets the stage (whatever it held is gone).
    """

    def __init__(self, lib, sess):
        self.lib = lib
        self.sess = sess
        self.uploaded = 0
        self.pushed = 0
        self.errors = 0
        self.pending_okay = False       # a DATA whose terminal OKAY is still owed
        self.drain_seconds = 5.0        # how long a terminal OKAY may take to arrive

    def _drain_okay(self, seconds=None):
        """Read until the loader's terminal OKAY is actually in hand (never a
        single timed read: an OKAY that has not hit the wire yet left pending
        wedges the loader's next reply into garbage -- the PARTIAL and
        `OKAYxnuloaderxnuloader` family). Stray bytes are consumed and shown."""
        seconds = seconds if seconds is not None else self.drain_seconds
        end = time.time() + seconds
        while time.time() < end:
            try:
                data, n, err = lt13.bulk_in(self.lib, self.sess,
                                            int(max(0.05, end - time.time()) * 1000))
            except Exception:
                continue
            if n:
                chunk = bytes(data[:n])
                if chunk.startswith(b"OKAY"):
                    self.pending_okay = False
                    return chunk
                diag("drain: %d stray bytes %r" % (n, chunk[:40]))
        self.errors += 1
        return b""

    def command(self, text, timeout_ms=4000):
        # a transaction that has not reached its terminal OKAY must not be
        # followed by another command: finish it (or account for it) first
        if self.pending_okay:
            diag("completing the previous transaction's OKAY first")
            if not self._drain_okay():
                raise lt13.DeviceError("the previous transaction never completed (no OKAY)")
        attempt = 0
        while True:
            attempt += 1
            resp = lt13.transact(self.lib, self.sess, text, timeout_ms, quiet=True)
            if resp is None:
                self.errors += 1
                raise lt13.DeviceError("no answer to %r" % text)
            if resp.status == "PARTIAL":
                # desynchronized bytes: the answer was not one whole reply --
                # drain hard until the loader's own OKAY surfaces, then retry once
                diag("partial reply to %r (raw %r); draining to the OKAY" % (text, (resp.raw or b"")[:40]))
                if not self._drain_okay():
                    self.errors += 1
                    raise lt13.DeviceError("desync after a partial reply to %r" % text)
                if attempt == 1:
                    continue
                self.errors += 1
                raise lt13.DeviceError("partial reply to %r twice in a row" % text)
            if resp.status == "DATA":
                self.pending_okay = True
                self._drain_okay()
            return resp

    def fetch(self):
        """One `upload`: the frames the kernel sent since the last poll."""
        resp = self.command("upload", 4000)
        if resp.status != "DATA" or resp.payload is None:
            return []
        blob = resp.payload
        frames = []
        off = 0
        while off + 8 <= len(blob):
            (length,) = struct.unpack_from("<I", blob, off)
            if off + 8 + length > len(blob) or length > RING_FRAME_MAX:
                break
            frames.append(blob[off + 8:off + 8 + length])
            off += 8 + length
        self.uploaded += len(frames)
        return frames

    def push(self, frames):
        """One `download:` carrying every frame given; the payload leaves
        immediately behind the ack (the loader's 20 s payload trap)."""
        if not frames:
            return True
        blob = b"".join(struct.pack("<I", len(f)) + f for f in frames)
        import ctypes as C
        wire = b"download:%08x" % len(blob)
        buf = (C.c_ubyte * len(wire)).from_buffer_copy(wire)
        moved = C.c_int(0)
        r = self.lib.dll.libusb_bulk_transfer(self.sess["handle"], self.sess["ep_out"],
                                              buf, len(wire), C.byref(moved), 4000)
        if r != 0 or moved.value != len(wire):
            self.errors += 1
            raise lt13.DeviceError("bulk-OUT failed: %s (%d/%d)"
                                   % (self.lib.errname(r), moved.value, len(wire)))
        end = time.time() + 4.0
        ack = None
        while time.time() < end and ack is None:
            remain = int((end - time.time()) * 1000)
            if remain <= 0:
                break
            data, n, err = lt13.bulk_in(self.lib, self.sess, remain)
            if n > 0:
                ack = bytes(data[:n])
        if ack is None or not ack.startswith(b"DATA"):
            self.errors += 1
            raise lt13.DeviceError("no download ack (%r)" % (ack,))
        for off in range(0, len(blob), 16384):
            chunk = blob[off:off + 16384]
            buf = (C.c_ubyte * len(chunk)).from_buffer_copy(chunk)
            moved = C.c_int(0)
            r = self.lib.dll.libusb_bulk_transfer(self.sess["handle"], self.sess["ep_out"],
                                                  buf, len(chunk), C.byref(moved), 4000)
            if r != 0 or moved.value != len(chunk):
                self.errors += 1
                raise lt13.DeviceError("payload bulk-OUT failed: %s (%d/%d)"
                                       % (self.lib.errname(r), moved.value, len(chunk)))
        end = time.time() + 4.0
        fin = None
        while time.time() < end and fin is None:
            remain = int((end - time.time()) * 1000)
            if remain <= 0:
                break
            data, n, err = lt13.bulk_in(self.lib, self.sess, remain)
            if n > 0:
                fin = bytes(data[:n])
        if fin is None or not fin.startswith(b"OKAY"):
            self.errors += 1
            raise lt13.DeviceError("no download OKAY (%r)" % (fin,))
        self.pushed += len(frames)
        return True


def run_tunnel(lib, sess):
    """ssh's transport over the ring: wave21's userspace Link/Tunnel, wave 25's pipe.

    SINGLE-THREAD USB: every libusb call happens in THIS thread (the pump); ssh's
    stdin arrives through a python-only reader thread and a queue (a second thread
    inside libusb's sync API crashed with an access violation -- the one time the
    mixed design ran)."""
    import queue
    in_q = queue.Queue()

    def stdin_reader():
        # os.read, NOT sys.stdin.buffer.read(4096): the buffered read blocks until
        # the FULL 4096 bytes (or EOF) -- ssh's banner (34 B) and KEX_INIT (2-4 KB)
        # would sit in the pipe forever and the handshake would starve (r3#1's
        # counters: acked frozen at 0x1, the client banner never emitted).
        fd = sys.stdin.fileno()
        while True:
            try:
                data = os.read(fd, 4096)
            except Exception:
                data = b""
            if not data:
                in_q.put(None)
                return
            in_q.put(data)

    pipe = Pipe25(lib, sess)
    link = lt21.Link()
    tun = lt21.Tunnel(link, PEER_IP, PEER_PORT)
    link.ipv4_handlers.append(tun.on_ipv4)

    resp = pipe.command("oem netmode on")
    diag("netmode on -> %s %r" % (resp.status, resp.payload))
    # (the caller has already verified the phase: `oem recording` said "a kernel is
    # running" moments ago. Note the loader's window is EXTENDED by every command:
    # a waiting loop must go silent -- device released -- or the kernel session it
    # waits for never starts.)

    FLAGS_TXT = {1: "FIN", 2: "SYN", 4: "RST", 8: "PSH", 16: "ACK"}

    def flags_txt(flags):
        return "|".join(txt for bit, txt in sorted(FLAGS_TXT.items()) if flags & bit) or "none"

    def trace_frame(frame, direction):
        """B3's full-field log line: time, direction, 4-tuple, flags, seq, ack,
        window, payload length, and the checksum verdict on the TCP header."""
        if len(frame) < 14 or struct.unpack_from(">H", frame, 12)[0] != 0x0800:
            diag("pkt %s %d B non-IPv4" % (direction, len(frame)))
            return
        pkt = frame[14:]
        if len(pkt) < 20 or pkt[9] != 6:
            diag("pkt %s %d B ip proto %d %s->%s" % (direction, len(pkt), pkt[9],
                 ".".join(str(b) for b in pkt[12:16]), ".".join(str(b) for b in pkt[16:20])))
            return
        off = (pkt[20 + 12] >> 4) * 4
        sport, dport, seq, ack, _x, flags, window, cksum, _e = struct.unpack_from(">HHIIBBHHH", pkt[20:40])
        payload = pkt[20 + off:]
        # the pseudo-header takes the packet's OWN addresses (wave27 fix: the old
        # line pinned HOST_IP as the source, which marked every INBOUND segment
        # BAD and would have poisoned the B3 branch evidence)
        pseudo = pkt[12:16] + pkt[16:20] + struct.pack(">BBH", 0, 6, off + len(payload))
        want = lt21.checksum(pseudo + pkt[20:20 + off] + payload)
        good = "ok" if want == 0 or (want ^ 0xffff) == 0 else "BAD(%#x)" % cksum
        diag("pkt %s %s:%u -> %s:%u flags=%s seq=%u ack=%u win=%u len=%u cksum=%s "
             "| SND.UNA=%u SND.NXT=%u RCV.NXT=%u state=%s"
             % (direction, ".".join(str(b) for b in pkt[12:16]), sport,
                ".".join(str(b) for b in pkt[16:20]), dport, flags_txt(flags), seq, ack,
                window, len(payload), good, tun.acked & 0xffffffff, tun.seq & 0xffffffff,
                tun.ack_of_peer & 0xffffffff, tun.state))

    def pump_once():
        # PUSH FIRST (wave27 fix): both wave27 sessions wedged the loader's
        # net loop on the very first `upload` -- with the ring empty, the
        # upload has nothing to return, and in the old fetch-first order our
        # ARP request sat in link.out FOREVER while the upload waited for the
        # kernel to speak. The kernel speaks only after OUR ARP reaches it.
        # Drain link.out before the fetch; the kernel's answer then gives the
        # upload its payload.
        if link.out:
            out, link.out = link.out[:32], link.out[32:]
            for frame in out:
                trace_frame(frame, "OUT")
            try:
                pipe.push(out)
            except lt13.DeviceError as e:
                # the net loop needs a beat to switch modes after netmode on:
                # k022's first push lost its terminal OKAY and the frames with
                # it. One grace retry before letting the error travel.
                diag("push failed once (%s); grace retry after a beat" % str(e)[:44])
                time.sleep(0.5)
                pipe.push(out)
        for frame in pipe.fetch():
            trace_frame(frame, "IN ")
            link.on_frame(frame)

    # the ring's other end should know where our packets go
    deadline = time.time() + 4.0
    while time.time() < deadline:
        link.arp_request(PEER_IP)
        try:
            pump_once()
        except lt13.DeviceError as e:
            diag("pump during arp: %s" % e)
            break
        if lt21.ip4(PEER_IP) in [lt21.ip4(k) for k in link.arp]:
            break
        time.sleep(0.03)
    diag("arp learned: %s" % sorted(link.arp))

    reader = threading.Thread(target=stdin_reader, daemon=True)
    reader.start()

    # the handshake is the state machine's now (Phase A): open_syn sends the SYN
    # with the MSS option and consumes the SYN's sequence number in the same
    # breath, so the final ACK and every data segment carry the right sequence;
    # the re-SYNs go through resyn() with the original ISN
    tun.open_syn()
    end = time.time() + 150.0
    retry = 0.0
    err = None
    rst_waits = 0
    while time.time() < end and tun.state != "ESTABLISHED":
        if tun.state == "CLOSED" and tun.failed:
            # an RST just means "nobody on :22 yet" -- sshd comes up at launchd's
            # own pace: reset and keep SYN-ing for the rest of the window
            rst_waits += 1
            tun.failed = None
            tun.state = "SYN_SENT"
        if time.time() > retry:
            tun.resyn()                                       # re-SYN every ~2 s
            retry = time.time() + 2.0
        try:
            pump_once()
        except lt13.DeviceError as e:
            err = str(e)
            diag("pump during syn: %s" % e)
            break
        time.sleep(0.01)
    if rst_waits:
        diag("%d RSTs ridden out while SYN-ing" % rst_waits)
    if tun.state != "ESTABLISHED":
        diag("no SYN-ACK in time (state %s%s)" % (tun.state, ": " + tun.failed if tun.failed else ""))
        try:
            pipe.command("oem netmode off")
        except lt13.DeviceError:
            pass
        return 4
    # (the SYN's sequence number was consumed by open_syn at the very start --
    # the state machine's final ACK and the data segments were born right)
    diag("established (%s:%d -> %s:%d)" % (HOST_IP, tun.src_port, PEER_IP, PEER_PORT))

    pending = b""
    stdin_eof = False
    last_counts = 0.0
    last_progress = time.time()
    progress_sig = None
    while tun.state == "ESTABLISHED" and not tun.closed_by_peer and not tun.failed and err is None:
        # the no-progress self-deadline (wave27 fix): a tree kill mid-tunnel is
        # the wedge injector -- the loader's net loop dies holding the pending
        # upload for the REST of the session. When nothing moves for 45 s
        # (ssh gone, sshd mute, link stuck), leave CLEANLY: netmode off, the
        # pair lives, the next attempt re-enters.
        sig = (len(tun.in_order), tun.acked, pipe.uploaded, len(pending))
        if sig != progress_sig:
            progress_sig = sig
            last_progress = time.time()
        elif time.time() - last_progress > 45.0:
            diag("no progress for 45 s: leaving cleanly (netmode off)")
            break
        if time.time() - last_counts > 5.0:
            last_counts = time.time()
            try:
                ns = pipe.command("oem netstat", 1500)
                nstext = ns.payload.decode("ascii", "replace").strip() if ns.payload else "?"
            except lt13.DeviceError as e:
                nstext = "ERR:" + str(e)[:40]
            diag("counts %s | up=%d pushed=%d err=%d | pending=%d unacked=%d acked=%s | netstat %s"
                 % (link.counts, pipe.uploaded, pipe.pushed, pipe.errors,
                    len(pending), len(tun.unacked),
                    hex((tun.seq - tun.acked) & 0xffffffff), nstext))
        # ssh's stdin -> the pending buffer (NEVER block here: tun.send's window
        # wait would freeze the pump and the first data segment would never leave)
        try:
            while True:
                data = in_q.get_nowait()
                if data is None:
                    stdin_eof = True
                else:
                    pending += data
        except queue.Empty:
            pass
        # feed what the peer's window allows: _emit only queues into link.out,
        # pump_once below is what actually moves frames over the ring
        while pending and (not tun.unacked or
                           ((tun.seq - tun.acked) & 0xffffffff) <= min(tun.peer_window, 8192) - lt21.MSS):
            take = pending[:lt21.MSS]
            pending = pending[len(take):]
            tun._emit(lt21.PSH | lt21.ACK, take)
        if stdin_eof and not pending and tun.state == "ESTABLISHED":
            tun.half_close()
        try:
            pump_once()
        except lt13.DeviceError as e:
            err = str(e)
            diag("pipe error: %s" % e)
            break
        out = tun.drain()
        if out:
            _real_stdout.buffer.write(out)
            _real_stdout.buffer.flush()
        tun._retransmit_if_due()
        time.sleep(0.002)
    end = time.time() + 1.0
    while time.time() < end:
        out = tun.drain()
        if not out:
            break
        _real_stdout.buffer.write(out)
        _real_stdout.buffer.flush()
        time.sleep(0.002)
    try:
        pipe.command("oem netmode off")
    except lt13.DeviceError:
        pass
    if tun.failed:
        diag("%s" % tun.failed)
        return 4
    if err is not None:
        return 4
    return 0


def main():
    lib = lt13.Libusb()
    # wave27: the no-session deadline is 20 s, not 600 -- a dead-pair attempt
    # must SELF-TERMINATE so the seeder's tree kill (the wedge injector when
    # it fires mid-transaction, k022) never has a reason to run. Armed runs
    # self-bound through the SYN phase (150 s) and the no-progress exit (45 s).
    deadline = time.time() + 20.0
    try:
        while time.time() < deadline:
            sess = open_fresh_session(lib)
            if sess is None:
                time.sleep(5)
                continue
            try:
                resp = lt13.transact(lib, sess, "oem recording", 2500, quiet=True)
            except lt13.DeviceError as e:
                diag("phase probe: %s" % e)
                resp = None
            raw = b""
            if resp is not None:
                raw = (resp.raw or b"") + (resp.payload or b"")
            if b"kernel is running" in raw:
                diag("phase: the kernel session is live -- tunneling")
                return run_tunnel(lib, sess)
            # loader phase: the service window is 240 s past the LAST command and is
            # extended by every command -- release the device and go SILENT so the
            # window closes, the loader returns, and the next session opens
            # (~250 s later, a live kernel session with sshd in it).
            try:
                lt13.disconnect(lib, sess)
            except Exception:
                pass
            diag("loader phase (raw %r); exiting fast -- the CALLER owns the duty "
                 "cycle: probing extends the loader's 240 s window forever, so the "
                 "campaign must alternate active windows with true silence (the "
                 "reset is what opens the next kernel session)" % raw[:40])
            # deliberately NO disconnect here: a loader that reboots between the
            # probe and the teardown makes libusb's free/close fault (0xC0000005,
            # uncatchable). The process exits anyway and the OS reclaims everything.
            return 5
        diag("no live kernel session within 600 s")
        return 5
    finally:
        lib.close()


if __name__ == "__main__":
    sys.exit(main())
