#!/usr/bin/env python3
"""Wave 45: the v36 gates hunt. The wave27/42 SSH machinery (phase-aware duty
cycle, six-branch classification, revive discipline, raw-byte pipes) with the
wave45 gates ladder in the hit's session:

  gate A (first):  pull /dev/logdump -- the step machine's own lines are the
                   regression verdict (steps to 21, 0x600dc0de, THE GPU STAYS
                   ON). No USB needed; the probe lines fall where they fall.
  gate D (cheap):  kern.hakios.battery_* sysctls (twice, spaced) + the
                   fuelgauge lines out of the pulled klog; also whether /sys
                   exists on this darwin at all (recorded honestly).
  gate B:          transfer wave45's fence_probe (stdin -> /var, chmod +x,
                   sha256 pinned), then run it. Two nonce CP_MEM_WRITEs through
                   the real submit->fence path; the wave44 WPTR-rewrite branch
                   is inside the probe (resubmits). The kernel's >=1 s no-answer
                   report (GMU_AHB_FENCE_STATUS, RPTR, WPTR) lands in the klog,
                   which gate A already pulled -- a second pull is taken after
                   the probe so the report lines are on record either way.
  gate C (last):   /bin/gl_test 8 -- the wave41 judge with RENDER/READBACK/
                   GL_ERROR/PRESENT lines; classified by the wave41-s6 rules.
                   fill + u2f_test ride along when there is session time.

Every gate's verdict file lands in wave45-scripts/ (verdict45-gate{a,b,c,d}.txt);
raw per-attempt stdout/stderr stay beside them (w45-<run>-<tag>-<nn>.out/.err).
Gates already holding a PASS verdict are not re-run (later generations only
fill holes). The hunt ends when all four gates hold verdicts or the deadline
passes -- whichever first. Zero flash; single Windows-libusb owner while
running.

usage: python gates-run-v45.py [--deadline-minutes 300] [--run-id ID]
"""
import hashlib
import json
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
PROBE_LOCAL = os.path.join(W45, "fence_probe")

POLL_S = 3.0
LOADER_SILENCE = 250.0
ENTRY_GUARD = 75.0
CT_KNOCK = 170
KILL_KNOCK = 190
CT_GATE = 170
KILL_GATE = 200
KILL_KLOG = 300       # 512 KiB of logdump over the ring at ~5-20 KiB/s
KILL_TRANSFER = 300
KILL_GL = 240         # gl_test 8 draws + holds the panel for 8 s
KILL_FILL = 420       # the fill profile runs 160 frames
KLOG_BYTES = 524288

TALKED = re.compile(r"LIVE \(product|netmode on ->|pipe error|pump during|"
                    r"partial reply|download|established|netmode off|reset by peer")

_started = time.time()


class MarchStop(Exception):
    """gate A (the march regression) did not reproduce: the mission's stop-loss
    says the remaining gates are not run."""


def arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


RUN_ID = arg("--run-id", time.strftime("%H%M%S"))
LOGP = os.path.join(W45, "gates-run-v45-%s.log" % RUN_ID)
DEADLINE = time.time() + 60 * float(arg("--deadline-minutes", "300"))


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOGP, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def plog(msg):
    with open(os.path.join(W45, "progress.log"), "a", encoding="utf-8") as f:
        f.write("%s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def verdict_path(gate):
    return os.path.join(W45, "verdict45-gate%s.txt" % gate)


def gate_verdict(gate):
    p = verdict_path(gate)
    if not os.path.isfile(p):
        return None
    head = open(p, encoding="utf-8", errors="replace").read(400)
    for line in head.splitlines():
        if line.startswith("verdict:"):
            return line.split(":", 1)[1].strip()
    return "UNKNOWN"


_attempt_seq = {}


def ssh_attempt(tag, remote_cmd, connect_timeout, kill_after, stdin_bytes=None):
    seq = _attempt_seq.get(tag, 0) + 1
    _attempt_seq[tag] = seq
    out_path = os.path.join(W45, "w45-%s-%s-%02d.out" % (RUN_ID, tag, seq))
    err_path = os.path.join(W45, "w45-%s-%s-%02d.err" % (RUN_ID, tag, seq))
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
    killed = False
    try:
        p = subprocess.Popen(cmd,
                             stdin=(subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = p.communicate(input=stdin_bytes, timeout=kill_after)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
            out, err = b"", b""
            try:
                out, err = p.communicate(timeout=5)
            except Exception:
                pass
            rc, killed = "TIMEOUT-TREEKILLED", True
    except Exception as e:
        out, err, rc = b"", repr(e).encode(), "SPAWN-FAIL"
    with open(out_path, "wb") as f:
        f.write(out or b"")
    with open(err_path, "wb") as f:
        f.write(err or b"")
    raw = out or b""
    text = raw.decode("utf-8", "replace")
    err_text = (err or b"").decode("utf-8", "replace")
    dur = time.time() - t0
    log("attempt %s -> rc=%s in %.1fs%s (out %d B)" % (tag, rc, dur, " (tree-killed)" if killed else "", len(raw)))
    return rc, text, err_text, killed, dur, raw, out_path, err_path


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
            or "kex_exchange" in err_text or "PTY allocation" in err_text
            or "Server refused" in err_text or "Welcome to" in err_text
            or "Darwin" in text):
        kind = "SSH-REACHED"
    elif rc == 255 and "banner exchange" in err_text:
        if kind == "ESTABLISHED":
            kind = "STALL-EST"
        elif kind in (None, "KNOCK-LIVE"):
            kind = "STALL-NOTUNNEL"
    elif rc == 0 and text and "WAVE21-SSH-OK" not in text:
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


def retried(tag, cmd, kill_after, stdin_bytes=None, tries=3, ok_check=None):
    rc = out = err = killed = dur = raw = opath = epath = None
    for t in range(tries):
        rc, out, err, killed, dur, raw, opath, epath = ssh_attempt(tag, cmd, CT_GATE, kill_after, stdin_bytes=stdin_bytes)
        if ok_check is None or ok_check(rc, out, raw, err):
            return rc, out, err, killed, dur, raw, opath, epath
        log("step %s try%d unsatisfied (rc=%s) -- retrying after the attach race (8 s)" % (tag, t + 1, rc))
        time.sleep(8)
    return rc, out, err, killed, dur, raw, opath, epath


# ---------------------------------------------------------------- gate A ----
def gate_a(raw, out_text, source=""):
    """Judge the march from an adreno-line extraction (zsh-safe quoted markers;
    the remote command greps the log outlets and pulls only the matching lines)."""
    text = raw.decode("utf-8", "replace")
    lines = [l.rstrip() for l in text.splitlines() if l.lstrip().startswith("adreno:")]
    steps = {}
    for l in lines:
        m = re.match(r"adreno: (?:step )?(\d+): (done|FAILED)", l)
        if m:
            steps[int(m.group(1))] = "done" if m.group(2) == "done" else "FAILED"
    keep_on = any("THE GPU STAYS ON" in l for l in lines)
    takes = any("THE 3D CORE TAKES COMMANDS" in l for l in lines)
    magic = [l for l in lines if "0x600dc0de" in l]
    magic_ok = any("THE 3D CORE WRITES OUR MEMORY ON COMMAND" in l for l in magic)
    ok = magic_ok and keep_on and steps.get(21) == "done"
    if not lines:
        verdict = "NO-LOG"          # the outlets answered nothing: honest non-verdict, gate stays open
    else:
        verdict = "PASS" if ok else "REGRESSED"
    with open(verdict_path("a"), "w", encoding="utf-8") as f:
        f.write("wave45 gate A -- the GPU march regression (kernel 5b77b418, gpu=1)\n")
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        if source:
            f.write("source: %s\n" % source)
        f.write("verdict: %s\n" % verdict)
        if verdict == "NO-LOG":
            f.write("the extraction returned no adreno lines: the outlets read empty -- recorded, not judged\n")
        f.write("steps seen: %s\n" % (" ".join("%d=%s" % (n, s) for n, s in sorted(steps.items())) or "NONE"))
        f.write("step 20 THE 3D CORE TAKES COMMANDS: %s\n" % takes)
        f.write("step 21 0x600dc0de written: %s\n" % magic_ok)
        f.write("THE GPU STAYS ON: %s\n" % keep_on)
        f.write("\nadreno lines:\n")
        for l in lines:
            f.write("  %s\n" % l)
        f.write("\n(the raw pull is the w45-%s-klog-*.out file beside this verdict)\n" % RUN_ID)
    log("gate A -> %s (steps %s, magic %s, stays-on %s)" % (verdict, len(steps), magic_ok, keep_on))
    plog("gate A %s (steps=%d magic=%s stays=%s)" % (verdict, len(steps), magic_ok, keep_on))
    return verdict


# ---------------------------------------------------------------- gate B ----
def gate_b():
    """Transfer the probe, pin its sha on the device, run it, read it back."""
    blob = open(PROBE_LOCAL, "rb").read()
    host_sha = hashlib.sha256(blob).hexdigest()
    cmd = ("cat > /var/fence_probe; chmod +x /var/fence_probe; "
           "sha256sum /var/fence_probe; wc -c < /var/fence_probe")

    def ok(r, o, raw, e):
        lines = (o or "").strip().splitlines()
        return (r == 0 and any(l.startswith(host_sha) for l in lines)
                and any(l.strip() == str(len(blob)) for l in lines))

    rc, out, err, killed, dur, raw, opath, epath = retried(
        "probe-xfer", cmd, KILL_TRANSFER, stdin_bytes=blob, tries=4, ok_check=ok)
    lines = (out or "").strip().splitlines()
    dev_sha = next((l.split()[0].lower() for l in lines if l and l[0] in "0123456789abcdef" and len(l.split()[0]) == 64), "")
    dev_len = next((l.strip() for l in lines if l.strip().isdigit()), "")
    if not (rc == 0 and dev_sha == host_sha and dev_len == str(len(blob))):
        log("gate B: transfer failed (host %s/%d, device %s/%s, rc=%s)" % (host_sha[:12], len(blob), dev_sha[:12] or "?", dev_len or "?", rc))
        return "TRANSFER-FAILED"
    log("gate B: probe staged (%d B, sha %s) in %.1fs" % (len(blob), host_sha[:12], dur))

    rc, out, err, killed, dur, raw, opath, epath = retried(
        "probe-run", "/var/fence_probe 2>&1; echo PROBE_RC=$?", 240, tries=4,
        ok_check=lambda r, o, _raw, e: r == 0 and "FENCE_PROBE:" in o)
    text = out or ""
    if "FENCE_PROBE: PASS" in text:
        verdict = "PASS"
    elif "FENCE_PROBE:" in text:
        verdict = "FAIL"
    else:
        log("gate B: the probe produced no verdict line (rc=%s)" % rc)
        return "NO-OUTPUT"
    with open(verdict_path("b"), "w", encoding="utf-8") as f:
        f.write("wave45 gate B -- the fence nonce probe (P0 device-level first test)\n")
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("tool: wave45-scripts/fence_probe (sha256 %s), two nonce CP_MEM_WRITEs through gem new -> map -> info -> submit -> wait fence\n" % host_sha)
        f.write("wave44 branch: a not-answered submit is resubmitted (WPTR rewrite), <=8 rounds per nonce\n\n")
        f.write("verdict: %s\n\n" % verdict)
        f.write(text.strip())
        f.write("\n\nprobe rc: %s\n" % rc)
    log("gate B -> %s" % verdict)
    plog("gate B %s" % verdict)
    return verdict


# ---------------------------------------------------------------- gate D ----
SYSCTLS = ("kern.hakios.battery_soc kern.hakios.battery_voltage_mv kern.hakios.battery_current_ma "
           "kern.hakios.battery_temperature_c kern.hakios.battery_present "
           "kern.hakios.battery_charger_present kern.hakios.battery_charging "
           "kern.hakios.battery_soc_estimated kern.hakios.battery_charger_action "
           "kern.hakios.battery_full_uah")

def gate_d(klog_raw):
    """The battery gate. The carrier has no /usr/sbin/sysctl (the discovery
    round's command not found), so the oids are read through battery_probe
    (sysctlbyname, the same interface the missing tool used), transferred and
    sha-pinned like the fence probe, run twice spaced for the series."""
    blob = open(os.path.join(W45, "battery_probe"), "rb").read()
    host_sha = hashlib.sha256(blob).hexdigest()
    xfer = ("cat > /var/battery_probe; chmod +x /var/battery_probe; "
            "sha256sum /var/battery_probe; wc -c < /var/battery_probe")

    def xfer_ok(r, o, raw, e):
        lines = (o or "").strip().splitlines()
        return (r == 0 and any(l.startswith(host_sha) for l in lines)
                and any(l.strip() == str(len(blob)) for l in lines))

    rc, out, err, killed, dur, raw, opath, epath = retried(
        "batt-xfer", xfer, KILL_TRANSFER, stdin_bytes=blob, tries=4, ok_check=xfer_ok)
    lines = (out or "").strip().splitlines()
    dev_sha = next((l.split()[0].lower() for l in lines if l and l[0] in "0123456789abcdef" and len(l.split()[0]) == 64), "")
    dev_len = next((l.strip() for l in lines if l.strip().isdigit()), "")
    if not (rc == 0 and dev_sha == host_sha and dev_len == str(len(blob))):
        log("gate D: transfer failed (rc=%s)" % rc)
        return "TRANSFER-FAILED"
    log("gate D: battery_probe staged (%d B, sha %s)" % (len(blob), host_sha[:12]))

    # zsh discipline: every echo marker quoted ('=' words abort the zsh line)
    run = ("echo '==SYSCTL-1=='; /var/battery_probe 2>&1; sleep 6; "
           "echo '==SYSCTL-2=='; /var/battery_probe 2>&1; "
           "echo '==SYSEXIST=='; ls /sys/class/power_supply 2>&1 | head -3; "
           "echo '==D==DONE'")
    rc, out, err, killed, dur, raw, opath, epath = retried(
        "battery", run, 200, tries=3,
        ok_check=lambda r, o, _raw, e: r == 0 and "==D==DONE" in o)
    text = out or ""
    if "==SYSCTL-1==" not in text:
        log("gate D: no probe output (rc=%s)" % rc)
        return "NO-OUTPUT"
    n_soc = text.count("kern.hakios.battery_soc =")
    verdict = "PASS" if n_soc >= 2 else "FAIL"
    # the fuelgauge's own lines, from whatever log text the ladder pulled
    ktext = klog_raw.decode("utf-8", "replace")
    fuel = [l.rstrip() for l in ktext.splitlines() if "fuelgauge" in l or "HakiosBattery" in l]
    with open(verdict_path("d"), "w", encoding="utf-8") as f:
        f.write("wave45 gate D -- the battery (wave43 S1-S3 device side)\n")
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("tool: /var/battery_probe (sha256 %s), sysctlbyname of the wave43 oids, two samples spaced 6 s\n" % host_sha)
        f.write("verdict: %s (two readable battery_soc samples required)\n\n" % verdict)
        f.write(text.strip())
        f.write("\n\nfuelgauge / HakiosBattery lines from the pulled log text:\n")
        for l in fuel:
            f.write("  %s\n" % l)
        if not fuel:
            f.write("  (none in the pulled window)\n")
        f.write("\nnote: /sys/class/power_supply is the ANDROID-side path; on Hakios the readout\n")
        f.write("is the kern.hakios.battery_* sysctls above (wave43 s7), read here through\n")
        f.write("sysctlbyname because the carrier ships no /usr/sbin/sysctl. The same-instant\n")
        f.write("Android pairing stays with the user.\n")
    log("gate D -> %s (fuelgauge lines %d)" % (verdict, len(fuel)))
    plog("gate D %s (fuel lines %d)" % (verdict, len(fuel)))
    return verdict


# ---------------------------------------------------------------- gate C ----
def classify_gl(out, rc):
    m = re.search(r"GL_RC=(\d+)", out)
    gl_rc = int(m.group(1)) if m else None
    has_hw = "RENDER_PASS backend=hw" in out
    has_readback = "READBACK_PASS samples" in out
    has_present = "PRESENT_CALL_OK" in out
    has_fail = "_FAIL" in out
    sw = ("backend=sw" in out) or ("softpipe" in out.lower()) or ("llvmpipe" in out.lower())
    if rc != 0 and gl_rc is None and not out.strip():
        return "no-session", "no remote output (connect/session phase failed; ssh rc=%s)" % rc, gl_rc
    if ("command not found" in out) or (("GLBIN=" in out) and ("not found" in out)):
        return "path-unreachable", "the binary was not found even at the absolute path (the v35 GL_RC=127 lesson)", gl_rc
    if "no OpenGL ES context" in out:
        return "branch-C", "context creation failed (dyld/SDK layer); gl_rc=%s" % gl_rc, gl_rc
    if "PRESENT_CALL_FAIL" in out or gl_rc == 3:
        return "present-fail", "the panel call failed (no GPU service path); gl_rc=%s" % gl_rc, gl_rc
    if sw and gl_rc == 0 and "_FAIL" not in out:
        return "software-comparison", "a software renderer drew it -- evidence, never hardware DONE", gl_rc
    if gl_rc == 0 and has_hw and has_readback and has_present and not has_fail:
        return "hardware-DONE", "GL_RC=0 + RENDER_PASS backend=hw + READBACK_PASS + PRESENT_CALL_OK, no _FAIL", gl_rc
    if gl_rc == 0:
        return "unstructured-rc0", "rc=0 but the structured verifier lines are absent", gl_rc
    if gl_rc is not None:
        return "remote-fail", "gl_test exited %s" % gl_rc, gl_rc
    return "no-session", "session ended without a GL_RC echo (ssh rc=%s)" % rc, gl_rc


def gate_c():
    cmd = ("G=/bin/gl_test; [ -x $G ] || G=/redwood/bin/gl_test; [ -x $G ] || "
           "G=$(command -v gl_test || find /bin /usr/bin /usr/local/bin /var/jb /Applications "
           "-maxdepth 4 -name gl_test 2>/dev/null | head -1); echo GLBIN=$G; "
           "[ -n \"$G\" ] && $G 8 2>&1; echo GL_RC=$?")
    rc, out, err, killed, dur, raw, opath, epath = retried(
        "gl", cmd, KILL_GL, tries=4,
        ok_check=lambda r, o, _raw, e: "GL_RC=" in o and "GLBIN=" in o)
    text = out or ""
    state, detail, gl_rc = classify_gl(text, rc)
    with open(verdict_path("c"), "w", encoding="utf-8") as f:
        f.write("wave45 gate C -- gl_test, the wave41 judge, first-frame round (six-branch)\n")
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("carrier: 51a030c3 (/bin/gl_test = the 802522ff judge binary, proven at verify)\n")
        f.write("criteria: wave41 s6 -- GL_RC==0 AND RENDER_PASS backend=hw AND READBACK_PASS AND PRESENT_CALL_OK AND no _FAIL\n\n")
        f.write("verdict: %s\n" % state)
        f.write("detail: %s\n" % detail)
        f.write("gl_rc: %s\n\n" % gl_rc)
        f.write(text.strip())
    log("gate C -> %s (%s)" % (state, detail))
    plog("gate C %s (gl_rc=%s)" % (state, gl_rc))
    if state in ("hardware-DONE", "software-comparison", "branch-C", "present-fail", "remote-fail"):
        # a real answer: the fill profile and u2f ride along while the session lives
        cmd_fill = ("G=/bin/gl_test; [ -x $G ] || G=/redwood/bin/gl_test; "
                    "$G fill 1080 2400 2>&1; echo FILL_RC=$?")
        rc2, out2, _e2, _k2, _d2, _r2, _o2, _e2p = retried(
            "fill", cmd_fill, KILL_FILL, tries=2,
            ok_check=lambda r, o, _raw, e: "FILL_RC=" in o)
        log("fill profile rc=%s (%d B)" % (rc2, len(out2 or "")))
        cmd_u2f = ("G=/bin/u2f_test; [ -x $G ] || G=/redwood/bin/u2f_test; "
                   "$G 2>&1; echo U2F_RC=$?")
        rc3, out3, _e3, _k3, _d3, _r3, _o3, _e3p = retried(
            "u2f", cmd_u2f, 120, tries=2, ok_check=lambda r, o, _raw, e: "U2F_RC=" in o)
        log("u2f_test rc=%s (%d B)" % (rc3, len(out3 or "")))
    return state


def run_gates():
    """The gates ladder in one live session."""
    # 1. the march log, both outlets in one zsh-safe pull:
    #    /dev/logdump (if the carrier exposes it) and /dev/ufs_logdump (the
    #    logdump PARTITION as a ufs block node: the loader composes the last
    #    generation's loader block + kernel log into it at every reset, and
    #    every generation boots the same v36 the same way, so its adreno
    #    lines are this build's march evidence). The partition is 512 MB but
    #    the kernel log sits at its head (the v23-era compose measured the
    #    ASCII extent at ~1.4 MB): head 4 MB captures the march, tail 1 MB
    #    captures the battery minute lines. Only the matching lines travel.
    rc, out, err, killed, dur, raw, opath, epath = retried(
        "klog",
        "echo '==KLOG-DEV=='; ls -la /dev/logdump /dev/ufs_logdump /dev/rufs_logdump 2>&1 | head -4; "
        "head -c 4194304 /dev/logdump 2>/dev/null | grep -a 'adreno:' | head -80; "
        "echo '==KLOG-END=='; "
        "head -c 4194304 /dev/ufs_logdump 2>/dev/null | grep -a 'adreno:' | head -700; "
        "echo '==UFS-LOG-END=='; "
        "head -c 8388608 /dev/ufs_logdump 2>/dev/null | grep -a -E 'fuelgauge|HakiosBattery' | tail -80; "
        "echo '==TAIL-END=='; "
        "head -c 4194304 /dev/ufs_logdump 2>/dev/null | grep -a -c 'adreno:'; "
        "wc -c < /dev/ufs_logdump 2>/dev/null; echo '==KLOG-DONE=='",
        KILL_KLOG, tries=3,
        ok_check=lambda r, o, _raw, e: r == 0 and b"==KLOG-DONE==" in (_raw or b""))
    klog_raw = b""
    if b"==KLOG-DONE==" not in (raw or b""):
        log("klog pull failed (rc=%s); continuing with the rest of the ladder" % rc)
    else:
        klog_raw = raw[:raw.find(b"==KLOG-DONE==")]
        log("klog pull: %d B in %.1fs" % (len(klog_raw), dur))
        if gate_verdict("a") != "PASS":
            source = ("log outlets via one SSH session (quoted-marker pull): /dev/logdump + "
                      "/dev/ufs_logdump (the logdump partition holds the last generation's "
                      "loader block + kernel log; every generation boots the same v36 the same way)")
            va = gate_a(klog_raw, out, source=source)
            if va != "PASS" and va != "NO-LOG":
                raise MarchStop("gate A = %s: the mission's stop-loss stops the ladder here" % va)
    # 2. battery (cheap, do it while the session lives)
    if gate_verdict("d") != "PASS":
        gate_d(klog_raw)
    # 3. the fence probe, then a klog TAIL pull: the kernel's no-answer report
    #    (GMU_AHB_FENCE_STATUS, RPTR, WPTR) if the probe tripped it, plus the
    #    fuelgauge minute lines for gate D
    tail_raw = b""
    if gate_verdict("b") != "PASS":
        bv = gate_b()
        rc, out, err, killed, dur, raw2, opath, epath = retried(
            "klog2", "tail -c %d /dev/logdump 2>/dev/null; echo '==KLOG2-END=='" % KLOG_BYTES,
            KILL_KLOG, tries=2,
            ok_check=lambda r, o, _raw, e: r == 0 and b"==KLOG2-END==" in (_raw or b""))
        if b"==KLOG2-END==" in (raw2 or b""):
            tail_raw = raw2[:raw2.find(b"==KLOG2-END==")]
            with open(os.path.join(W45, "klog2-%s.bin" % RUN_ID), "wb") as f:
                f.write(tail_raw)
            log("klog tail: %d B (archived)" % len(tail_raw))
    # 4. gl_test (the heavy judge)
    if gate_verdict("c") not in ("hardware-DONE", "software-comparison", "branch-C",
                                 "present-fail", "remote-fail", "unstructured-rc0"):
        gate_c()
    # 5. gate D again with head+tail if it never got a PASS (the minute lines)
    if gate_verdict("d") != "PASS" and tail_raw:
        gate_d(klog_raw + tail_raw)


def main():
    log("wave45 gates hunt armed (run-id %s, deadline %.0f min)" % (RUN_ID, (DEADLINE - time.time()) / 60.0))
    log("gates on record: A=%s B=%s C=%s D=%s" % (gate_verdict("a"), gate_verdict("b"),
                                                  gate_verdict("c"), gate_verdict("d")))
    plog("gates hunt armed run=%s (A=%s B=%s C=%s D=%s)" % (RUN_ID, gate_verdict("a"),
                                                           gate_verdict("b"), gate_verdict("c"), gate_verdict("d")))
    if not os.path.isfile(SSH):
        log("FATAL: ssh.exe not at %s" % SSH)
        return 2
    silence_until = 0.0
    last_addrs = None
    n = 0
    while time.time() < DEADLINE:
        open_gates = [g for g, good in (("a", "PASS"), ("b", "PASS"), ("d", "PASS")) if gate_verdict(g) != good]
        if gate_verdict("c") not in ("hardware-DONE", "software-comparison", "branch-C",
                                     "present-fail", "remote-fail", "unstructured-rc0"):
            open_gates.append("c")
        if not open_gates:
            log("=== ALL FOUR GATES HOLD VERDICTS; the hunt is done ===")
            plog("all four gates hold verdicts; hunt done")
            return 0
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
        knock = "uname -a && id && echo WAVE21-SSH-OK W45-%s" % RUN_ID
        rc, out, err, killed, dur, raw, opath, epath = ssh_attempt(tag, knock, CT_KNOCK, KILL_KNOCK)
        kind = classify(rc, out, err)
        log("branch: %s" % kind)
        if kind == "HIT":
            log("=== HIT: entering the gates ladder (open: %s) ===" % (",".join(open_gates) or "none"))
            plog("HIT; gates ladder entered (open: %s)" % (",".join(open_gates) or "none"))
            try:
                run_gates()
            except MarchStop as e:
                with open(os.path.join(W45, "verdict45-overall.txt"), "w", encoding="utf-8") as f:
                    f.write("wave45 v36 overall verdict\n")
                    f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                    f.write("verdict: BLOCKED at march (gate A failed: %s)\n" % e)
                    f.write("per the mission's stop-loss the remaining gates are not run\n")
                log("MARCH STOP: %s -- the ladder is abandoned (verdict45-overall.txt written)" % e)
                plog("MARCH STOP: %s" % e)
                return 7
            except Exception as e:
                log("gates ladder raised %r -- continuing the hunt" % (e,))
        if kind in ("LOADER-PHASE", "DEAD-PAIR"):
            if kind == "LOADER-PHASE":
                silence_until = time.time() + LOADER_SILENCE
                log("loader answered: silence until +%.0f s (the exec clock)" % LOADER_SILENCE)
            time.sleep(2.5 if kind == "DEAD-PAIR" else POLL_S)
            continue
        if kind == "NO-DEVICE":
            time.sleep(POLL_S)
            continue
        maybe_revive(err)
        time.sleep(2.5)
    plog("gates hunt closed at deadline: A=%s B=%s C=%s D=%s" % (gate_verdict("a"), gate_verdict("b"),
                                                                 gate_verdict("c"), gate_verdict("d")))
    log("deadline reached. verdicts: A=%s B=%s C=%s D=%s" % (gate_verdict("a"), gate_verdict("b"),
                                                             gate_verdict("c"), gate_verdict("d")))
    return 5


if __name__ == "__main__":
    sys.exit(main())
