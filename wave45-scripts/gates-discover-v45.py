#!/usr/bin/env python3
"""Wave 45 follow-up: one discovery session over the live v36 SSH channel.
Purpose: find the real outlets for gate A (the kernel march log) and gate D
(the battery sysctls) on the 51a030c3/flash-boot carrier, with zsh-safe
commands (no word may start with '=': zsh expands =word as the path of the
command 'word' and aborts the whole line when it does not exist -- the
original ==MARKER== echoes were what made klog/battery die in 0.3 s).

usage: python gates-discover-v45.py [--deadline-minutes 45]
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
W45 = os.path.join(REPO, "wave45-scripts")
sys.path.insert(0, W13)

KEY = os.path.join(W21, "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"C:\Users\<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(W25, "tunnel25w.py"))

POLL_S = 3.0
LOADER_SILENCE = 250.0
ENTRY_GUARD = 75.0
CT_KNOCK = 170
KILL_KNOCK = 190
CT_GATE = 170
KILL_GATE = 200

TALKED = re.compile(r"LIVE \(product|netmode on ->|pipe error|pump during|"
                    r"partial reply|download|established|netmode off|reset by peer")

_started = time.time()
RUN_ID = arg = sys.argv[sys.argv.index("--run-id") + 1] if "--run-id" in sys.argv else time.strftime("%H%M%S")
LOGP = os.path.join(W45, "gates-discover-v45-%s.log" % RUN_ID)
DEADLINE = time.time() + 60 * float(os.environ.get("DISC_MIN", "45"))


def arg_of(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOGP, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


_attempt_seq = {}


def ssh_attempt(tag, remote_cmd, connect_timeout, kill_after, stdin_bytes=None):
    seq = _attempt_seq.get(tag, 0) + 1
    _attempt_seq[tag] = seq
    out_path = os.path.join(W45, "w45-disc-%s-%s-%02d.out" % (RUN_ID, tag, seq))
    err_path = os.path.join(W45, "w45-disc-%s-%s-%02d.err" % (RUN_ID, tag, seq))
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=%d" % connect_timeout,
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "-T",
           "root@10.0.0.2",
           remote_cmd]
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd,
                             stdin=(subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(timeout=kill_after)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        out, err = b"", b""
        try:
            out, err = p.communicate(timeout=5)
        except Exception:
            pass
        rc = "TIMEOUT-TREEKILLED"
    except Exception as e:
        out, err, rc = b"", repr(e).encode(), "SPAWN-FAIL"
    with open(out_path, "wb") as f:
        f.write(out or b"")
    with open(err_path, "wb") as f:
        f.write(err or b"")
    raw = out or b""
    text = raw.decode("utf-8", "replace")
    err_text = (err or b"").decode("utf-8", "replace")
    log("attempt %s -> rc=%s in %.1fs (out %d B)" % (tag, rc, time.time() - t0, len(raw)))
    return rc, text, err_text, raw


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


def classify(rc, text, err_text):
    if rc == 0 and "WAVE21-SSH-OK" in text:
        return "HIT"
    kind = None
    for line in err_text.splitlines():
        if "the kernel session is live" in line:
            kind = "KNOCK-LIVE"
        elif "established (" in line:
            kind = "ESTABLISHED"
        elif "no SYN-ACK in time" in line or "RSTs ridden" in line or "reset by peer" in line:
            kind = "NOLISTEN"
        elif "pair is dead" in line or "claim ok but" in line:
            kind = "DEAD-PAIR"
        elif "loader phase" in line:
            kind = "LOADER-PHASE"
        elif ("pipe error" in line or "pump during" in line or "partial reply" in line
              or "bulk-OUT failed" in line or "no download" in line):
            kind = "USB-DESYNC"
        elif "no d00d on the bus" in line:
            kind = "NO-DEVICE"
    if ("Permission denied" in err_text or "Remote protocol version" in err_text
            or "kex_exchange" in err_text or "Darwin" in text):
        kind = "SSH-REACHED"
    elif rc == 255 and "banner exchange" in err_text:
        kind = "STALL"
    return kind or "OTHER"


def maybe_revive(err_text):
    if not TALKED.search(err_text):
        return None
    try:
        r = subprocess.run([PYEXE, os.path.join(W26, "revive-v26.py")],
                           capture_output=True, timeout=45)
        text = (r.stdout or b"").decode("utf-8", "replace")
        log("revive -> %s %s" % (r.returncode, " | ".join(text.strip().splitlines()[-2:])[-150:]))
        return text
    except Exception as e:
        log("revive failed: %r" % (e,))
        return None


DISCOVERY_CMD = (
    "echo MARK-DEV-UFS; ls -la /dev/ufs_logdump /dev/rufs_logdump 2>&1; "
    "echo MARK-UFS-LIST; ls /dev 2>/dev/null | grep -i ufs | head -12; "
    "echo MARK-DEV-LOG; ls -la /dev/logdump /dev/klog /dev/console 2>&1; "
    "echo MARK-SYSCTL-BIN; command -v sysctl; sysctl -n kern.hakios.battery_soc 2>&1; "
    "echo MARK-SYSCTL-FAMILY; sysctl kern.hakios 2>&1 | head -24; "
    "echo MARK-VAR; ls /var 2>/dev/null | head -16; "
    "echo MARK-DMESG; command -v dmesg; dmesg 2>&1 | head -3; "
    "echo MARK-PATH; echo PATH-$PATH; "
    "echo MARK-DISCOVERY-DONE"
)


def main():
    log("wave45 discovery armed (run-id %s, deadline %.0f min)" % (RUN_ID, (DEADLINE - time.time()) / 60.0))
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
        rc, text, err_text, raw = ssh_attempt("k%03d" % n,
                                              "uname -a && id && echo WAVE21-SSH-OK W45D-%s" % RUN_ID,
                                              CT_KNOCK, KILL_KNOCK)
        kind = classify(rc, text, err_text)
        log("branch: %s" % kind)
        if kind == "HIT":
            log("=== HIT: running the discovery command ===")
            rc, text, err_text, raw = ssh_attempt("disc", DISCOVERY_CMD, CT_GATE, KILL_GATE)
            with open(os.path.join(W45, "w45-discovery-%s.txt" % RUN_ID), "w", encoding="utf-8") as f:
                f.write("wave45 discovery (run-id %s, %s)\n\n" % (RUN_ID, time.strftime("%Y-%m-%d %H:%M:%S")))
                f.write(text)
            log("discovery captured (%d B) -> w45-discovery-%s.txt" % (len(raw), RUN_ID))
            maybe_revive(err_text)
            return 0
        if kind in ("LOADER-PHASE", "DEAD-PAIR"):
            if kind == "LOADER-PHASE":
                silence_until = time.time() + LOADER_SILENCE
                log("loader answered: silence until +%.0f s" % LOADER_SILENCE)
            time.sleep(2.5 if kind == "DEAD-PAIR" else POLL_S)
            continue
        if kind == "NO-DEVICE":
            time.sleep(POLL_S)
            continue
        maybe_revive(err_text)
        time.sleep(2.5)
    log("deadline reached without a discovery session")
    return 5


if __name__ == "__main__":
    sys.exit(main())
