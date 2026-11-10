#!/usr/bin/env python3
"""Wave 25: host `ssh` into the Darwin userspace shell = the v0.4 announcement attempt.

The phone boots slot b (v20, zero-flash: set_active b only). The loader's gadget
(18d1:d00d "xnuloader") enumerates on the Windows bus; per the Wave 24 serving
discipline this orchestrator is the SINGLE Windows-libusb owner (no usbipd in the
serving phase). The loop, per generation (one gadget presence stretch):

  1. watch the bus for the gadget
  2. poll getvar:version until the bulk pair answers (armed ~t+11s into a boot;
     the v20 wall is gone: gen 0 beat 1, every boot)
  3. confirm getvar:product == xnuloader (not the ABL's fastboot d00d)
  4. evidence: oem netstat (the ring's counters, before), then one oem recording
     probe (v20 cmdline has no rec_*: the side quest's verdict, on the record once)
  5. release the device and attempt the E2E:
       ssh -i wave21-scripts/id_ed25519_phk110 -o ProxyCommand=tunnel25.cmd
           root@10.0.0.2  "uname -a; id; echo WAVE21-SSH-OK"
     tunnel25.cmd = python wave21-scripts/loader_talk.py tunnel 10.0.0.2 22 --
     the net ring's little TCP (netmode on, ARP, SYN to sshd, ssh's transport).
  6. WAVE21-SSH-OK in the output = the verdict; netstat after = the ring's share.
  7. across generations (the phone's own cycle), keep watching until the deadline.

usage: python e2e25.py [--deadline-minutes 60] [--attempts-per-generation 9] [--pause 5]
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt  # noqa: E402

HERE = os.path.join(REPO, "wave25-scripts")
LOG = os.path.join(HERE, "e2e25.log")
KEY = os.path.join(REPO, "wave21-scripts", "id_ed25519_phk110")
VERDICT = os.path.join(HERE, "verdict25.txt")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"<host>\AppData\Local\Programs\Python\Python313\python.exe"
# Win32-OpenSSH "exec"s the ProxyCommand string: a .cmd file dies instantly there
# (first session's finding), a direct exe with spaceless paths works. The wrapper
# (tunnel25w.py) splits the streams: loader_talk's diagnostic prints must never
# ride into ssh's transport (second session's finding: its banner on stdout
# corrupted the proxy stream the same way).
PROXY = "%s %s" % (PYEXE, os.path.join(HERE, "tunnel25w.py"))

_started = time.time()
RUN_STAMP = time.strftime("%H%M%S")


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def open_claim(lib):
    """Locate+open+config+claim the gadget (the wave21 ordering, harmless on Windows).
    Returns a session dict, or None when no gadget is on the bus. USB errors raise."""
    import ctypes
    plist, n = lib.device_list()
    h = cfg = None
    sess = None
    try:
        dev = None
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                dev = plist[i]
                break
        if dev is None:
            return None
        h = ctypes.c_void_p()
        r = lib.dll.libusb_open(dev, ctypes.byref(h))
        if r != lt.LIBUSB_SUCCESS:
            raise lt.DeviceError("libusb_open failed: %s" % lib.errname(r))
        r = lib.dll.libusb_set_configuration(h, 1)
        if r != 0:
            log("set_configuration(1): %s" % lib.errname(r))
        lib.dll.libusb_set_auto_detach_kernel_driver(h, 1)
        cfg = ctypes.POINTER(lt.ConfigDescriptor)()
        r = lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
        if r != lt.LIBUSB_SUCCESS:
            raise lt.DeviceError("active config failed: %s" % lib.errname(r))
        iface, ep_out, ep_in, ifd = lt.pick_iface_eps(cfg.contents)
        if iface is None:
            raise lt.DeviceError("no interface with a bulk OUT+IN pair")
        r = lib.dll.libusb_claim_interface(h, iface)
        if r != lt.LIBUSB_SUCCESS:
            raise lt.DeviceError("claim(if%d) failed: %s" % (iface, lib.errname(r)))
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


def release(lib, sess):
    try:
        lt.disconnect(lib, sess)
    except Exception as e:
        log("release: %r" % (e,))


def ask(lib, sess, cmd, timeout_ms=2500):
    try:
        return lt.transact(lib, sess, cmd, timeout_ms, quiet=True)
    except lt.DeviceError as e:
        log("ask(%r) transport: %s" % (cmd, e))
        return None


def resp_text(resp):
    if resp is None:
        return None
    if resp.status == "OKAY" and resp.payload is not None:
        return resp.payload.decode("ascii", "replace").strip()
    return "%s %r" % (resp.status, resp.payload)


def netstat(lib):
    sess = None
    try:
        sess = open_claim(lib)
        if sess is None:
            return None
        return resp_text(ask(lib, sess, "oem netstat", 2500))
    finally:
        if sess is not None:
            release(lib, sess)


def ssh_attempt(n, gen):
    stamp = RUN_STAMP
    out_path = os.path.join(HERE, "ssh-attempt-r%s-g%d-%d.out" % (stamp, gen, n))
    err_path = os.path.join(HERE, "ssh-attempt-r%s-g%d-%d.err" % (stamp, gen, n))
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=30",
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "root@10.0.0.2",
           "uname -a; id; echo WAVE21-SSH-OK"]
    t0 = time.time()
    out = err = b""
    rc = "?"
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=110)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout or b""
        err = e.stderr or b""
        rc = "TIMEOUT"
    except Exception as e:
        err = repr(e).encode()
        rc = "SPAWN-FAIL"
    with open(out_path, "wb") as f:
        f.write(out)
    with open(err_path, "wb") as f:
        f.write(err)
    text = out.decode("utf-8", "replace")
    ok = "WAVE21-SSH-OK" in text
    log("ssh attempt g%d#%d -> rc=%s in %.1fs (stdout %d B, stderr %d B): %s"
        % (gen, n, rc, time.time() - t0, len(out), len(err), "HIT" if ok else "miss"))
    for line in err.decode("utf-8", "replace").strip().splitlines()[-6:]:
        log("  err| %s" % line)
    for line in text.strip().splitlines()[:8]:
        log("  out| %s" % line)
    return ok, text


def arg(name, default):
    for i, a in enumerate(sys.argv):
        if a == name:
            return sys.argv[i + 1]
    return default


def main():
    minutes = float(arg("--deadline-minutes", 60))
    per_gen = int(arg("--attempts-per-generation", 9))
    pause = float(arg("--pause", 5))
    lib = lt.Libusb()
    deadline = time.time() + 60 * minutes
    log("e2e25 orchestrator armed (deadline %.0f min, %d attempts/generation, pause %.0f s); "
        "Windows-libusb single owner" % (minutes, per_gen, pause))
    log("libusb %s" % lib.version())
    gen = 0
    state = "watch"          # watch | dark | armed
    darks = 0
    attempts = 0
    gen_started = 0.0
    armed_at = 0.0
    recording_probed = False
    rc = 1
    try:
        while time.time() < deadline:
            plist, n = lib.device_list()
            dev = None
            try:
                for i in range(n):
                    d = lib.device_desc(plist[i])
                    if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                        dev = plist[i]
                        break
            except Exception:
                pass
            lib.free_list(plist, n)
            if dev is None:
                if state != "watch":
                    log("generation %d left the bus (state %s, %d attempts, %d darks)"
                        % (gen, state, attempts, darks))
                state, darks, attempts = "watch", 0, 0
                time.sleep(2)
                continue
            if state == "watch":
                gen += 1
                state = "dark"
                darks = 0
                gen_started = time.time()
                log("generation %d: gadget on the wire" % gen)
            # armed?
            try:
                sess = open_claim(lib)
            except lt.DeviceError as e:
                if "ACCESS" in str(e) or "NOT_SUPPORTED" in str(e):
                    if darks == 0:
                        log("open blocked (another driver owns the device?): %s" % e)
                    time.sleep(15)
                    continue
                if "NO_DEVICE" in str(e):
                    time.sleep(2)          # a stale devnode or a generation boundary
                    continue
                raise
            if sess is None:
                time.sleep(2)
                continue
            resp = ask(lib, sess, "getvar:version", 2000)
            if resp is None:
                darks += 1
                if darks == 1 or darks % 10 == 0:
                    log("dark (%d): the bulk pair is not answering yet" % darks)
                release(lib, sess)
                if darks % 12 == 0:
                    # libusb (Windows, no hotplug thread) keeps phantom cached
                    # devices after the gadget left the wire: writes into the
                    # void time out exactly like a dark loader. Re-anchor the
                    # bus view so "gone" reads as gone.
                    log("re-anchoring the bus view (fresh libusb context)")
                    try:
                        lib.close()
                    except Exception:
                        pass
                    lib = lt.Libusb()
                time.sleep(2.5)
                continue
            ptext = resp_text(ask(lib, sess, "getvar:product", 2000)) or "?"
            if "xnuloader" not in ptext:
                log("d00d answers but product=%r (not our loader); standing down" % ptext)
                release(lib, sess)
                time.sleep(8)
                continue
            if state != "armed":
                state = "armed"
                armed_at = time.time()
                attempts = 0
                ns = resp_text(ask(lib, sess, "oem netstat", 2500))
                log("generation %d ARMED (generation age %.1f s, %d darks); netstat(before) = %s"
                    % (gen, armed_at - gen_started, darks, ns))
                if not recording_probed:
                    recording_probed = True
                    rec = ask(lib, sess, "oem recording", 2500)
                    log("side-quest probe: oem recording -> %s" % resp_text(rec))
            release(lib, sess)
            attempts += 1
            ok, text = ssh_attempt(attempts, gen)
            if ok:
                log("=== WAVE21-SSH-OK: the host reached the Darwin shell over the loader's ring ===")
                after = netstat(lib)
                log("netstat(after) = %s" % after)
                with open(VERDICT, "w", encoding="utf-8") as f:
                    f.write("WAVE21-SSH-OK\nwhen: %s\ngeneration: %d\nattempt: %d\n"
                            "netstat after: %s\n\n%s\n" %
                            (time.strftime("%Y-%m-%d %H:%M:%S"), gen, attempts, after, text))
                log("verdict written: %s" % VERDICT)
                rc = 0
                break
            after = netstat(lib)
            if after:
                log("netstat after attempt g%d#%d: %s" % (gen, attempts, after))
            if attempts >= per_gen:
                log("generation %d: %d attempts spent; standing down until the next generation"
                    % (gen, attempts))
                time.sleep(20)
            else:
                time.sleep(pause)
        if rc != 0:
            log("deadline reached without WAVE21-SSH-OK (generations seen: %d)" % gen)
        return rc
    finally:
        lib.close()


if __name__ == "__main__":
    sys.exit(main())
