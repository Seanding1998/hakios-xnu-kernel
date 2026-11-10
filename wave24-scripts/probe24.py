#!/usr/bin/env python3
"""Wave 24 diagnostic sampler (Windows-libusb, single owner).

Protocol layer = fetch-recording-23.py v2.1 verbatim (the review-fixed one: stage then
"upload", FAIL without the colon, the trailing OKAY consumed, getvar liveness first).
This round's mission is the FOUR-CHECKPOINT acceptance channel, recorded apart:

  CP1 (real OUT submit taken)        device side  -> logdump ("checkpoint-1: ...")
  CP2 (the host's write completed)   HERE         -> every send() success line (bytes on wire)
  CP3 (the completion reached the device's loader) device side -> logdump ("checkpoint-3: ...")
  CP4 (the IN reply went out)        HERE (reply) + device side (usb_tx_done sampler line)

Per episode (a gadget appearance on the Windows bus):
  1. getvar:version                liveness; a swallowed write is "un-armed", logged as such
  2. getvar:max-download-size, getvar:screen   read-only protocol depth
  3. oem log + upload              THE length+content-checked bidirectional exchange
                                   (DATA<len> must match byte count; the content must be the
                                   loader log -- the mirror's lines are the diagnosis)
  4. oem recording + upload        only after a run has returned (the v19b carry-over)
Every session also logs: libusb version, bus/port path, device speed, active config,
endpoint max packet sizes -- the review's "distinguish device generations from real data".

usage: probe24.py [--once] [--deadline-minutes N]
"""
import ctypes
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt  # noqa: E402

OUT_DIR = os.path.join(REPO, "wave24-scripts")
LOG = os.path.join(OUT_DIR, "probe24.log")
LOG_OUT = os.path.join(OUT_DIR, "udon-oemlog-v20.txt")
REC_OUT = os.path.join(OUT_DIR, "udon-recording-v20.bin")

def log(msg):
    line = "[probe24 %s] %s" % (time.strftime("%H:%M:%S"), msg)
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
    """One reply frame, the v2.1 wire (no colon after FAIL; DATA streams; trailing OKAY)."""
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
                        break
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
    tail_data, tail_n, tail_err = bulk_read(lib, sess, 5000, 4096)
    if tail_n > 0:
        t = bytes(tail_data)
        return ("DATA", got) if t.startswith(b"OKAY") else ("DATA+JUNK", (got, t[:32]))
    return ("DATA", got)

def send(lib, sess, command, timeout_ms=3000):
    """CP2 lives here: a send() that returns with the full byte count on the wire."""
    wire = lt.LoaderProto.encode_command(command)
    transferred = ctypes.c_int(0)
    outbuf = (ctypes.c_ubyte * len(wire)).from_buffer_copy(wire)
    r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_out"], outbuf,
                                     len(wire), ctypes.byref(transferred), timeout_ms)
    if r != 0 or transferred.value != len(wire):
        raise lt.DeviceError("bulk-OUT failed: %s (%d/%d)"
                             % (lib.errname(r), transferred.value, len(wire)))
    log("CP2-host: wrote %d bytes on ep 0x%02x (%s): the host's write completed"
        % (transferred.value, sess["ep_out"], command.split("\n")[0]))

def ask(lib, sess, command, reply_timeout_s):
    send(lib, sess, command)
    st, tail = read_frame(lib, sess, reply_timeout_s)
    if st in ("OKAY", "FAIL"):
        log("CP4-host: reply %s %r" % (st, bytes(tail)[:80] if isinstance(tail, (bytes, bytearray)) else tail))
    return st, tail

def upload_staged(lib, sess, timeout_s, out_path, label):
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
            headb = f.read(96)
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

def fetch_staged(lib, sess, stage_cmd, upload_timeout_s, out_path, label, content_markers=()):
    st, tail = ask(lib, sess, stage_cmd, 8.0)
    if st == "FAIL":
        return ("FAIL", bytes(tail).decode("utf-8", "replace") if tail else "")
    if st == "PARTIAL":
        return ("PARTIAL", bytes(tail))
    if st != "OKAY":
        return (st or "NONE", b"")
    st, tail = upload_staged(lib, sess, upload_timeout_s, out_path, label)
    if st == "DATA" and content_markers:
        data = open(out_path, "rb").read()
        hits = [m for m in content_markers if m in data]
        log("content check on %s (%d bytes): %d/%d markers %s"
            % (label, len(data), len(hits), len(content_markers),
               "OK " + repr([h[:40] for h in hits[:4]]) if hits else "NONE of %r" % content_markers))
    return (st, tail)

def describe(lib, dev, sess, cfg, iface, ifd):
    try:
        speed = {0: "unknown", 1: "low", 2: "full", 3: "high", 4: "super", 5: "super+"}.get(
            lib.dll.libusb_get_device_speed(dev), "?")
    except Exception:
        speed = "?"
    try:
        eps = ",".join("0x%02x/%dB" % (ifd.endpoint[i].bEndpointAddress,
                                       ifd.endpoint[i].wMaxPacketSize)
                       for i in range(ifd.bNumEndpoints)) if ifd else "?"
    except Exception:
        eps = "?"
    log("session: libusb %s, bus %d path %s, speed %s, config %d, iface %d, eps %s"
        % (lib.version(), lib.dll.libusb_get_bus_number(dev) if hasattr(lib.dll, "libusb_get_bus_number") else -1,
           lib.port_path(dev), speed, cfg.contents.bConfigurationValue if cfg else -1, iface, eps))

def attempt(lib, dev, state):
    desc = lib.device_desc(dev)
    try:
        h, cfg, iface, ep_out, ep_in, ifd = lt.open_and_claim(lib, dev, desc)
    except lt.DeviceError as e:
        msg = str(e)
        log("open+claim failed: %s" % msg)
        if "NOT_SUPPORTED" in msg or "ACCESS" in msg:
            if state.get("phase") != "owned-elsewhere":
                state["phase"] = "owned-elsewhere"
                log("the device is owned by another driver (usbipd attach?): standing down to 20 s cadence")
            time.sleep(20)
        return
    sess = {"handle": h, "ep_out": ep_out, "ep_in": ep_in, "iface": iface,
            "maxpkt": (ifd.endpoint[0].wMaxPacketSize if ifd and ifd.bNumEndpoints else 512)}
    state["eps"] += 1
    log("gadget episode #%d: open+claim ok (iface %d, ep 0x%02x/0x%02x)"
        % (state["eps"], iface, ep_out, ep_in))
    describe(lib, dev, sess, cfg, iface, ifd)
    try:
        # -- 1. liveness (read-only): the write is either swallowed (un-armed) or answered
        st, tail = ask(lib, sess, "getvar:version", 5.0)
        if st != "OKAY":
            ph = "dark:" + str(st)
            if state.get("phase") != ph:
                log("getvar:version -> %s %r: writes are not being answered (un-armed pair): backing off"
                    % (st, tail if isinstance(tail, bytes) else b""))
            state["phase"] = ph
            return
        if state.get("phase") != "live":
            log("getvar:version -> OKAY %r: the bulk pair is ARMED and the protocol is live" % (tail,))
        state["phase"] = "live"
        # -- 2. read-only depth
        for var in ("max-download-size", "screen", "product", "result"):
            try:
                st, tail = ask(lib, sess, "getvar:" + var, 5.0)
                if st != "OKAY":
                    break
            except lt.DeviceError as e:
                log("getvar %s failed: %s" % (var, e))
                break
        # -- 3. the length+content-checked bidirectional exchange (the loader+kernel log;
        #       the mirror's vendor lines ride in it -- the round's primary evidence)
        markers = (b"== XNULOADER", b"checkpoint-1", b"sample ", b"the console mirror",
                   b"== KERNEL LOG", b"END OF LOG")
        stamp = time.strftime("%H%M%S")
        log_out = LOG_OUT.replace(".txt", "-" + stamp + ".txt")
        st, tail = fetch_staged(lib, sess, "oem log", 120, log_out, "oem log", markers)
        if st == "DATA":
            state["got_log"] = True
            log("=== OEM LOG CAPTURED (%s bytes): the four-checkpoint channel has its content check ===" % tail)
        elif st == "FAIL":
            log("oem log FAIL: %r" % tail)
        # -- 4. the recording (only after a kernel run has returned; FAIL otherwise)
        rec_out = REC_OUT.replace(".bin", "-" + stamp + ".bin")
        st, tail = fetch_staged(lib, sess, "oem recording", 900, rec_out, "recording")
        if st == "FAIL":
            reason = tail
            if "kernel is running" in reason or "still arming" in reason:
                state["busy"] += 1
                if state["busy"] == 1 or state["busy"] % 10 == 0:
                    log("the session is live (%d probes): the recording arms at the return" % state["busy"])
            elif "no recording" in reason:
                state["noRec"] += 1
                if state["noRec"] == 1 or state["noRec"] % 10 == 0:
                    log("loader phase, no recording staged yet (%d probes)" % state["noRec"])
            else:
                log("oem recording FAIL: %r" % reason)
        elif st == "DATA":
            state["got_rec"] = True
            log("=== RECORDING CAPTURED (%s bytes) ===" % tail)
        log("episode closed")
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
    state = {"busy": 0, "noRec": 0, "got_rec": False, "got_log": False, "eps": 0,
             "phase": None}
    n = 0
    log("sampler v1 armed (deadline %d min); Windows-libusb single owner" % minutes)
    log("libusb %s" % lib.version())
    while time.time() < deadline:
        n += 1
        try:
            dev, plist, cnt = find_gadget(lib)
        except Exception as e:
            log("device list failed: %r" % (e,))
            time.sleep(2)
            continue
        if dev is None:
            if state.get("phase") is not None or state["eps"]:
                if state.get("phase") == "live":
                    log("the gadget left the bus (a live episode ended)")
                state["phase"] = None
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
        if (state["got_log"] or state["got_rec"]) and once:
            log("evidence in hand (--once): done")
            return
        time.sleep(2)
    log("deadline reached; log captured: %s, recording captured: %s" % (state["got_log"], state["got_rec"]))

if __name__ == "__main__":
    main()
