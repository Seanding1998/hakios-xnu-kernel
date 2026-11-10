#!/usr/bin/env python3
"""Wave 28: the /var persistence watcher. The wave27 phase-aware duty cycle,
re-pointed: on a live-session hit it does NOT run the ssh acceptance pack --
it runs the /var marker package (wave28-scripts/mark-var-v28.py) for the
mode given on the command line, then exits. Everything else (loader-phase
silence, dead-pair arming pressure, six-branch classification, tree kill
discipline, single Windows-libusb owner) is the wave27 machine verbatim.

  --marker-mode write  session 1: write markers + blob + fingerprint host keys
  --marker-mode read   session 2: read them all back (the judgment inputs)

usage: python hunt-var-v28.py --marker-mode write [--deadline-minutes 200]
                              [--run-id ID] [--tag S1]
"""
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W13 = os.path.join(REPO, "wave13-scripts")
W21 = os.path.join(REPO, "wave21-scripts")
W25 = os.path.join(REPO, "wave25-scripts")
W26 = os.path.join(REPO, "wave26-scripts")
W27 = os.path.join(REPO, "wave27-scripts")
W28 = os.path.join(REPO, "wave28-scripts")
sys.path.insert(0, W13)

KEY = os.path.join(W21, "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(W25, "tunnel25w.py"))

POLL_S = 3.0
LOADER_SILENCE = 250.0
ENTRY_GUARD = 75.0
CT_FAST = 12
KILL_FAST = 16
KNOCK_GAP = 2.5
CT_KNOCK = 170
KILL_KNOCK = 190
MARKER_TIMEOUT = 1400   # the marker pack: up to 4 ssh steps at up to ~200-420 s

TALKED = re.compile(r"LIVE \(product|netmode on ->|pipe error|pump during|"
                    r"partial reply|download|established|netmode off|reset by peer")

_started = time.time()


def arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


RUN_ID = arg("--run-id", time.strftime("%Y%m%d-%H%M%S"))
MODE = arg("--marker-mode", "write")
TAG = arg("--tag", "S1" if MODE == "write" else "S2")
LOG = os.path.join(W28, "hunt-var-v28-%s.log" % RUN_ID)
DEADLINE = time.time() + 60 * float(arg("--deadline-minutes", 200))


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


_lib = None


def bus_d00d():
    global _lib
    try:
        if _lib is None:
            import loader_talk as lt13
            _lib = lt13.Libusb()
        plist, n = _lib.device_list()
        addrs = []
        try:
            for i in range(n):
                d = _lib.device_desc(plist[i])
                if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                    addrs.append(_lib.dll.libusb_get_device_address(plist[i]))
        finally:
            _lib.free_list(plist, n)
        return addrs
    except Exception as e:
        return ["ERR:%s" % e.__class__.__name__]


def ssh_attempt(tag, remote_cmd, connect_timeout, kill_after):
    out_path = os.path.join(W28, "hunt28-%s-%s.out" % (RUN_ID, tag))
    err_path = os.path.join(W28, "hunt28-%s-%s.err" % (RUN_ID, tag))
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=%d" % connect_timeout,
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "root@10.0.0.2",
           remote_cmd]
    t0 = time.time()
    killed = False
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = p.communicate(timeout=kill_after)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True)
            out, err = b"", b""
            try:
                out, err = p.communicate(timeout=5)
            except Exception:
                pass
            rc, killed = "TIMEOUT-TREEKILLED", True
    except Exception as e:
        out, err, rc = b"", repr(e).encode(), "SPAWN-FAIL"
    out = out or b""
    err = err or b""
    with open(out_path, "wb") as f:
        f.write(out)
    with open(err_path, "wb") as f:
        f.write(err)
    text = out.decode("utf-8", "replace")
    err_text = err.decode("utf-8", "replace")
    dur = time.time() - t0
    log("attempt %s -> rc=%s in %.1fs%s" % (tag, rc, dur, " (tree-killed)" if killed else ""))
    return rc, text, err_text, killed, dur


def classify(rc, text, err_text):
    if rc == 0 and "W28-PROBE" in text:
        return "HIT"
    kind = None
    for line in err_text.splitlines():
        if "the kernel session is live" in line:
            kind = "KNOCK-LIVE"
        elif "established (" in line:
            kind = "ESTABLISHED"
        elif "no SYN-ACK in time" in line or "RSTs ridden" in line \
                or "reset by peer" in line:
            kind = "NOLISTEN"
        elif "pair is dead" in line or "claim ok but" in line:
            kind = "DEAD-PAIR"
        elif "loader phase" in line:
            kind = "LOADER-PHASE"
        elif ("pipe error" in line or "pump during" in line
              or "partial reply" in line or "bulk-OUT failed" in line
              or "no download" in line):
            kind = "USB-DESYNC"
        elif "no d00d on the bus" in line:
            kind = "NO-DEVICE"
    if ("Permission denied" in err_text or "Remote protocol version" in err_text
            or "kex_exchange" in err_text or "PTY allocation" in err_text
            or "Server refused" in err_text or "Welcome to" in err_text
            or "Darwin" in text):
        kind = "SSH-REACHED"
    elif rc == 255 and "banner exchange" in err_text:
        if kind == "ESTABLISHED":
            kind = "STALL-EST"
        elif kind in (None, "KNOCK-LIVE"):
            kind = "STALL-NOTUNNEL"
    elif rc == 0 and text and "W28-PROBE" not in text:
        kind = "SSH-REACHED"
    return kind or "OTHER"


def maybe_revive(err_text):
    if not TALKED.search(err_text):
        return None
    try:
        r = subprocess.run([PYEXE, os.path.join(W26, "revive-v26.py")],
                           capture_output=True, timeout=45)
        text = (r.stdout or b"").decode("utf-8", "replace")
        tail = " | ".join(text.strip().splitlines()[-2:])
        log("revive -> %s %s" % (r.returncode, tail[-160:]))
        return tail
    except Exception as e:
        log("revive failed: %r" % (e,))
        return None


KNOCK_CMD = "uname -a && echo W28-PROBE %s" % RUN_ID


def marker_pack(first_out, first_err):
    """The hit's payload: the /var marker package for this wave's mode."""
    log("=== LIVE SESSION (%s mode): firing the marker package ===" % MODE)
    for line in first_err.strip().splitlines()[-6:]:
        log("  hit-err| %s" % line[:200])
    rc = subprocess.run([PYEXE, "-I", os.path.join(W28, "mark-var-v28.py"),
                         "--mode", MODE, "--tag", TAG, "--run-id", RUN_ID],
                        cwd=W28, timeout=MARKER_TIMEOUT)
    log("marker pack -> rc=%s" % rc.returncode)
    return rc.returncode


def main():
    log("wave28 /var watcher armed (run-id %s, mode %s tag %s, deadline %.0f min)"
        % (RUN_ID, MODE, TAG, (DEADLINE - time.time()) / 60.0))
    log("knock cmd: %r" % KNOCK_CMD)
    if not os.path.isfile(SSH):
        log("FATAL: ssh.exe not at %s" % SSH)
        return 2
    silence_until = 0.0
    last_addrs = None
    n = 0
    while time.time() < DEADLINE:
        addrs = bus_d00d()
        if addrs != last_addrs:
            log("bus: d00d addrs %s (was %s)" % (addrs, last_addrs))
            last_addrs = addrs
        clean = bool(addrs) and not any(str(a).startswith("ERR:") for a in addrs)
        if not clean:
            silence_until = 0.0
            time.sleep(POLL_S)
            continue
        if time.time() < silence_until + (ENTRY_GUARD if silence_until else 0.0):
            time.sleep(POLL_S)
            continue
        n += 1
        tag = "k%03d" % n
        rc, out, err, killed, dur = ssh_attempt(tag, KNOCK_CMD, CT_KNOCK, KILL_KNOCK)
        kind = classify(rc, out, err)
        log("branch: %s" % kind)
        for line in err.strip().splitlines()[-4:]:
            log("  err| %s" % line[:200])
        if kind == "HIT":
            mrc = marker_pack(out, err)
            log("=== marker pack done (rc=%s); watcher exits ===" % mrc)
            return 0 if mrc == 0 else 6
        if kind == "LOADER-PHASE":
            silence_until = time.time() + LOADER_SILENCE
            log("loader answered: silence until +%.0f s (the exec clock)" % LOADER_SILENCE)
            time.sleep(POLL_S)
            continue
        if kind == "DEAD-PAIR":
            # short arming attempts keep the SET_CONFIG+getvar pressure on
            rc2, out2, err2, _, _ = ssh_attempt(tag + "f", KNOCK_CMD, CT_FAST, KILL_FAST)
            kind2 = classify(rc2, out2, err2)
            if kind2 == "HIT":
                mrc = marker_pack(out2, err2)
                log("=== marker pack done (rc=%s); watcher exits ===" % mrc)
                return 0 if mrc == 0 else 6
            if kind2 == "LOADER-PHASE":
                silence_until = time.time() + LOADER_SILENCE
                log("loader answered (fast): silence until +%.0f s" % LOADER_SILENCE)
            time.sleep(KNOCK_GAP)
            continue
        if kind == "NO-DEVICE":
            time.sleep(POLL_S)
            continue
        maybe_revive(err)
        time.sleep(KNOCK_GAP)
    log("deadline reached without a live session (%d attempts)" % n)
    return 5


if __name__ == "__main__":
    sys.exit(main())
