#!/usr/bin/env python3
"""Wave 23 recording extractor v2: the Windows-side libusb sampler, protocol-corrected.

Review fixes (docs/review/gpt-review-report-2026-11-09.md §六-2/§六-3, applied 01:3x):
  - the stage command ("oem recording"/"oem log"/"oem screenshot") only STAGES a buffer and
    replies OKAY (loader.c:4678/4726/4673); the bytes move only after a follow-up "upload"
    (loader.c:4643: fb_reply_data(len) -> 1 MiB chunks -> fb_reply("OKAY","")). v1 read DATA
    straight after the stage OKAY and would have timed out even on a healthy pipe.
  - fb_reply puts the text straight after the 4-byte code with NO colon (loader.c:4465-4475:
    fb_reply("FAIL", text) sends "FAIL"+text); v1 looked for "FAIL:" and mis-filed every
    real FAIL as PARTIAL.
  - the upload's trailing OKAY (sent after the last payload chunk) is consumed, not left to
    masquerade as the next reply's header.
  - every episode starts with a read-only "getvar:version" liveness check: a write that
    lands and is answered proves the bulk pair is armed and the application protocol is
    live; a swallowed write proves the opposite without touching anything.

Phase map (all logged):
  getvar swallowed            -> un-armed session or dead node: quiet backoff
  getvar OKAY "0.5"           -> protocol live; "oem recording" next
  "oem recording" -> FAIL (no recording)                -> loader phase before a run
  "oem recording" -> FAIL (a kernel is running / still arming) -> the session is live;
                   the recording arms at the return -- keep polling at a low cadence
  "oem recording" -> OKAY  -> "upload" -> DATA<len> + bytes + OKAY -> saved
After the recording: "oem log" + upload (the loader+kernel log), "oem screenshot" + upload
(one still of the last screen), then sampling continues for further cycles.

Single-owner note: this sampler is Windows-libusb only; it never attaches/detaches usbipd
(the review's standing rule for the diagnostic period).

usage: fetch-recording-23.py [--once] [--deadline-minutes N]
"""
import ctypes
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt  # noqa: E402

OUT_DIR = os.path.join(REPO, "wave23-scripts")
LOG = os.path.join(OUT_DIR, "fetch23.log")
REC_OUT = os.path.join(OUT_DIR, "udon-recording-v19b.bin")
LOG_OUT = os.path.join(OUT_DIR, "udon-oemlog-v19b.txt")
SHOT_OUT = os.path.join(OUT_DIR, "udon-screenshot-v19b.raw")

def log(msg):
    line = "[fetch23 %s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)

def find_gadget(lib):
    plist, n = lib.device_list()
    try:
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                return plist[i], plist, n
    except Exception:
        pass
    return None, plist, n

def bulk_read(lib, sess, timeout_ms, size):
    buf = (ctypes.c_ubyte * size)()
    transferred = ctypes.c_int(0)
    r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_in"], buf, size,
                                     ctypes.byref(transferred), timeout_ms)
    data = bytes(buf[:transferred.value]) if transferred.value > 0 else b""
    return data, transferred.value, (None if r == 0 else lib.errname(r))

def read_frame(lib, sess, timeout_s, out=None, progress=None):
    """One reply frame. The wire (loader.c fb_reply/fb_reply_data, NO colon):
        OKAY[<text>]                       -> ("OKAY", text)
        FAIL<text>                         -> ("FAIL", text)
        DATA<8hex><payload...>[OKAY]       -> ("DATA", bytes_read); a trailing OKAY is
                                              consumed and reported via out_when ("okay").
    A DATA payload streams into `out` (a file object). Returns one of
        ("OKAY"|"FAIL", bytes) | ("DATA", n) | ("UNDERRUN", n) | ("PARTIAL", buf) | (None, None)
    """
    deadline = time.time() + timeout_s
    buf = b""
    want = None
    got = 0
    marked = 0
    while True:
        remain = deadline - time.time()
        if remain <= 0:
            if want is not None:
                return ("UNDERRUN", got)
            return ("PARTIAL", buf) if buf else (None, None)
        data, n, err = bulk_read(lib, sess, min(int(remain * 1000), 8000), 1 << 20)
        if n > 0:
            if want is None:
                buf += data
                if buf.startswith(b"OKAY"):
                    return ("OKAY", buf[4:])
                if buf.startswith(b"FAIL"):
                    return ("FAIL", buf[4:])
                if buf.startswith(b"DATA"):
                    if len(buf) < 12:
                        continue
                    want = int(buf[4:12], 16)
                    rest = buf[12:]
                    got = len(rest)
                    if out is not None:
                        out.write(rest)
                    if got >= want:
                        break            # payload done; the trailing OKAY comes next
                    buf = b""
                    continue
                for cand in (b"OKAY", b"FAIL", b"DATA"):
                    if cand.startswith(buf):
                        break
                else:
                    return ("PARTIAL", buf)
            else:
                got += n
                if out is not None:
                    out.write(data)
                if progress and got - marked >= (16 << 20):
                    marked = got
                    progress(got, want)
                if got >= want:
                    break
            continue
        if err and "TIMEOUT" in err:
            continue
        if err:
            raise lt.DeviceError("bulk-IN failed: %s" % err)
        if want is not None and got >= want:
            break
        return (None, None)
    # payload complete: consume the upload's trailing OKAY (loader.c:4661 fb_reply("OKAY",""))
    tail_data, tail_n, tail_err = bulk_read(lib, sess, 5000, 4096)
    if tail_n > 0:
        t = bytes(tail_data)
        return ("DATA", got) if t.startswith(b"OKAY") else ("DATA+JUNK", (got, t[:32]))
    return ("DATA", got)

def send(lib, sess, command, timeout_ms=3000):
    wire = lt.LoaderProto.encode_command(command)
    transferred = ctypes.c_int(0)
    outbuf = (ctypes.c_ubyte * len(wire)).from_buffer_copy(wire)
    r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_out"], outbuf,
                                     len(wire), ctypes.byref(transferred), timeout_ms)
    if r != 0 or transferred.value != len(wire):
        raise lt.DeviceError("bulk-OUT failed: %s (%d/%d)"
                             % (lib.errname(r), transferred.value, len(wire)))

def ask(lib, sess, command, reply_timeout_s):
    """Send a command, return (status, tail). The write exception propagates.
    NOT for DATA-bearing replies (inline payload bytes would be lost) -- use
    upload_staged for those."""
    send(lib, sess, command)
    return read_frame(lib, sess, reply_timeout_s)

def upload_staged(lib, sess, timeout_s, out_path, label):
    """'upload' -> DATA<len> + payload + OKAY, streamed to out_path. The payload may start
    inline in the header's bulk transfer, so the whole frame is read with out= from the
    start (nothing is lost to a late stream hand-off)."""
    send(lib, sess, "upload")
    tmp = out_path + ".part"
    with open(tmp, "wb") as out:
        def prog(g, w):
            log("%s: %d of %d MiB" % (label, g >> 20, w >> 20))
        st, tail = read_frame(lib, sess, timeout_s, out=out, progress=prog)
    if st in ("DATA", "DATA+JUNK"):
        os.replace(tmp, out_path)
        size = os.path.getsize(out_path)
        with open(out_path, "rb") as f:
            headb = f.read(64)
        log("%s: saved %d bytes -> %s (head %r)" % (label, size, out_path, headb))
        if st == "DATA+JUNK":
            log("%s: trailing bytes after the payload: %r" % (label, tail[1]))
        return ("DATA", size)
    try:
        os.remove(tmp)
    except OSError:
        pass
    if st == "UNDERRUN":
        log("%s: UNDERRUN after %d bytes" % (label, tail))
    return (st, tail)

def fetch_staged(lib, sess, stage_cmd, upload_timeout_s, out_path, label):
    """Stage one buffer, then upload it. Returns (status, detail)."""
    st, tail = ask(lib, sess, stage_cmd, 8.0)
    if st == "FAIL":
        return ("FAIL", bytes(tail).decode("utf-8", "replace") if tail else "")
    if st == "PARTIAL":
        return ("PARTIAL", bytes(tail))
    if st != "OKAY":
        return (st or "NONE", b"")
    return upload_staged(lib, sess, upload_timeout_s, out_path, label)

def attempt(lib, dev, state):
    desc = lib.device_desc(dev)
    try:
        h, cfg, iface, ep_out, ep_in, ifd = lt.open_and_claim(lib, dev, desc)
    except lt.DeviceError as e:
        msg = str(e)
        log("open+claim failed: %s" % msg)
        if "NOT_SUPPORTED" in msg or "ACCESS" in msg:
            # the device is owned elsewhere (usbipd attach): single-owner discipline --
            # never fight it, wait for the ownership to come back
            if state.get("phase") != "owned-elsewhere":
                state["phase"] = "owned-elsewhere"
                log("the device is owned by another driver (usbipd attach?): standing down to 20 s cadence")
            time.sleep(20)
        return
    sess = {"handle": h, "ep_out": ep_out, "ep_in": ep_in, "iface": iface,
            "maxpkt": (ifd.endpoint[0].wMaxPacketSize if ifd and ifd.bNumEndpoints else 512)}
    state["eps"] += 1
    if not state.get("in_ep"):
        log("gadget episode #%d: open+claim ok (iface %d, ep 0x%02x/0x%02x)"
            % (state["eps"], iface, ep_out, ep_in))
    state["in_ep"] = True
    try:
        # -- liveness: a read-only getvar. A swallowed write means un-armed/dead; an OKAY
        #    means the bulk pair is armed and the application protocol is answering.
        st, tail = ask(lib, sess, "getvar:version", 5.0)
        if st != "OKAY":
            if state.get("phase") != "dark:" + str(st):
                state["phase"] = "dark:" + str(st)
                log("getvar:version -> %s %r: writes are not being answered (un-armed pair): backing off"
                    % (st, tail if isinstance(tail, bytes) else b""))
            state["phase"] = "dark:" + str(st)
            return
        if state.get("phase") not in ("live", None) or not state.get("said_live"):
            log("getvar:version -> OKAY %r: the bulk pair is ARMED and the protocol is live" % (tail,))
            state["said_live"] = True
        state["phase"] = "live"
        # -- the recording: staged only after a kernel run has returned
        st, tail = fetch_staged(lib, sess, "oem recording", 900, REC_OUT, "recording")
        if st == "FAIL":
            reason = tail
            if "kernel is running" in reason or "still arming" in reason:
                state["busy"] += 1
                state["phase"] = "session"
                if state["busy"] == 1 or state["busy"] % 10 == 0:
                    log("the session is live (%d probes): the recording arms at the return" % state["busy"])
            elif "no recording" in reason:
                state["noRec"] += 1
                state["phase"] = "loader"
                if state["noRec"] == 1 or state["noRec"] % 10 == 0:
                    log("loader phase, no recording staged yet (%d probes)" % state["noRec"])
            else:
                log("oem recording FAIL: %r" % reason)
            return
        if st != "DATA":
            log("oem recording did not stage: %s %r" % (st, tail if not isinstance(tail, bytes) else tail[:64]))
            return
        state["got_rec"] = True
        log("=== RECORDING CAPTURED (%s bytes) ===" % tail)
        # -- the loader+kernel log of the finished run
        st, tail = fetch_staged(lib, sess, "oem log", 120, LOG_OUT, "oem log")
        log("oem log: %s %r" % (st, tail))
        # -- one still frame of the last screen (the panel memory as left)
        st, tail = fetch_staged(lib, sess, "oem screenshot", 120, SHOT_OUT, "screenshot")
        log("screenshot: %s %r" % (st, tail))
        try:
            st, tail = ask(lib, sess, "getvar:screen", 5.0)
            log("getvar screen: %s %r" % (st, tail))
        except lt.DeviceError as e:
            log("getvar screen failed: %s" % e)
        log("=== evidence set complete; sampling continues for further cycles ===")
    finally:
        try:
            lib.dll.libusb_release_interface(sess["handle"], sess["iface"])
        except Exception:
            pass
        lib.dll.libusb_close(sess["handle"])

def main():
    once = "--once" in sys.argv
    minutes = 150
    for i, a in enumerate(sys.argv):
        if a == "--deadline-minutes":
            minutes = int(sys.argv[i + 1])
    lib = lt.Libusb()
    deadline = time.time() + 60 * minutes
    state = {"busy": 0, "noRec": 0, "got_rec": False, "eps": 0,
             "in_ep": False, "phase": None, "said_live": False}
    n = 0
    log("sampler v2 armed (deadline %d min); Windows-libusb single owner" % minutes)
    while time.time() < deadline:
        n += 1
        try:
            dev, plist, cnt = find_gadget(lib)
        except Exception as e:
            log("device list failed: %r" % (e,))
            time.sleep(2)
            continue
        if dev is None:
            if state.get("in_ep"):
                log("the gadget left the bus (episode closed)")
            state["in_ep"] = False
            state["phase"] = None
            state["said_live"] = False
            state["busy"] = 0
            state["noRec"] = 0
            lib.free_list(plist, cnt)
            time.sleep(2)
            continue
        try:
            attempt(lib, dev, state)
        except lt.DeviceError as e:
            if "bulk-OUT failed" in str(e):
                if state.get("phase") != "dark:write":
                    state["phase"] = "dark:write"
                    log("writes are being swallowed (un-armed session): backing off to 20 s cadence")
                time.sleep(20)
            else:
                log("attempt failed: %s" % e)
                time.sleep(4)
        except Exception as e:
            log("attempt crashed: %r" % (e,))
            time.sleep(4)
        finally:
            lib.free_list(plist, cnt)
        if state["got_rec"] and once:
            log("evidence in hand (--once): done")
            return
        time.sleep(2)
    log("deadline reached; recording captured: %s" % state["got_rec"])

if __name__ == "__main__":
    main()
