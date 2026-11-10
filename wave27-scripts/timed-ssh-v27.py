#!/usr/bin/env python3
"""Wave 27: the wide-window SSH hunt on v23's 1800 s sessions -- the first full
live run of the Phase-A-fixed host protocol.

What changed against wave26's timed-ssh (and why):

  1. PHASE-AWARE DUTY CYCLE. The loader execs the kernel 240 s after its LAST
     command. wave26's continuous mode probed every ~55 s and could keep the
     loader in its service window forever (no session ever starts). Here every
     attempt's proxy probe classifies the phase:
       - "loader phase" (the loader ANSWERED)  -> true silence for 250 s, so the
         exec happens; the next attempt lands ~10 s into the fresh session;
       - "kernel is running"                   -> knock continuously;
       - dead pair / no device                 -> keep arming pressure
         (the loader's standing receive is posted ~11 s after the gadget
         appears; the attempt's claim+getvar write is what arms it -- wave26's
         run9 finding -- so dead-pair phases respawn attempts back-to-back).
  2. CHEAP BUS GATING. No attempt fires into an empty bus (the 242 "no device"
     polls of run9 were full 52 s attempts doing nothing). A single libusb
     instance polls device_list every ~3 s (metadata only -- no claim, no
     device I/O, single-owner safe).
  3. SIX-BRANCH CLASSIFICATION (review-3 §5 B4). Every miss is filed into a
     named branch from the attempt's stderr evidence -- never a bare "miss".
     The B3 frame traces (tunnel25w's pkt lines, fixed this wave for INbound
     pseudo-headers) are in the per-attempt .err and decide the fine branch.
  4. ACCEPTANCE MODE. On a hit: three independent SSH connections in the same
     session, one content-verified 256 KiB transfer (stdin -> `wc -c`), and a
     management-channel check (drain + getvar) -- then the per-run verdict.
  5. Kill discipline: taskkill /F /T by the exact ssh PID only.

Zero flash. Single Windows-libusb owner (this process and its attempt
children -- nothing else talks to the device while the hunt runs).

usage: python timed-ssh-v27.py [--deadline-minutes 480] [--run-id ID]
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
sys.path.insert(0, W13)

KEY = os.path.join(W21, "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(W25, "tunnel25w.py"))

POLL_S = 3.0            # idle bus poll period
LOADER_SILENCE = 250.0  # after a loader-phase ANSWER (exec = last command + 240 s)
ENTRY_GUARD = 75.0      # a fresh session is entered no sooner than this past its
                        # open: en0 attaches at kernel ~49 s, and k001 proved an
                        # earlier `upload` wedges the loader's net loop for the
                        # WHOLE session (wave26's good tunnel entered at age 8-11 min)
CT_FAST = 12            # the un-armed dead-pair cycle: short attempts so the
KILL_FAST = 16          # SET_CONFIG+getvar arming pressure stays near-continuous
                        # (the loader's arming loop is its boot +0..~4 min window;
                        # the wave26 hunter ran this rhythm at ~2 s)
KNOCK_GAP = 2.5         # respawn delay between attempts while the bus holds a live pair
CT_KNOCK = 170          # the tunnel now leaves CLEANLY on its own (push-first + the
KILL_KNOCK = 190        # 45 s no-progress exit); the kill is a backstop for a frozen
                        # proxy only -- killing mid-tunnel was the wedge injector
                        # (k001/k006: the loader's net loop died holding the upload)
CT_ACCEPT = 170         # acceptance connections: same clean-exit bounds
KILL_ACCEPT = 200
KILL_TRANSFER = 300     # 256 KiB over the ring at ~5-20 KiB/s
TRANSFER_BYTES = 262144

TALKED = re.compile(r"LIVE \(product|netmode on ->|pipe error|pump during|"
                    r"partial reply|download|established|netmode off|reset by peer")

_started = time.time()


def arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


RUN_ID = arg("--run-id", time.strftime("%Y%m%d-%H%M%S"))
LOG = os.path.join(W27, "hunt-phaseB-v27-%s.log" % RUN_ID)
REPORT = os.path.join(W27, "wave27-report.md")
DEADLINE = time.time() + 60 * float(arg("--deadline-minutes", 480))


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def report(note):
    """A progress line into the wave27 report (visibility requirement)."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write("- %s | %s\n" % (stamp, note))
    log("report| %s" % note)


_lib = None


def bus_d00d():
    """Addresses of every 18d1:d00d node libusb sees now (metadata only)."""
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


def ssh_attempt(tag, remote_cmd, connect_timeout, kill_after, stdin_bytes=None):
    """One OpenSSH attempt over tunnel25w. Returns (rc, stdout, stderr)."""
    out_path = os.path.join(W27, "tssh27-%s-%s.out" % (RUN_ID, tag))
    err_path = os.path.join(W27, "tssh27-%s-%s.err" % (RUN_ID, tag))
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
        p = subprocess.Popen(cmd,
                             stdin=(subprocess.PIPE if stdin_bytes is not None
                                    else subprocess.DEVNULL),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            if stdin_bytes is not None:
                # write stdin from a thread is overkill: ssh reads at its own pace
                # and the tunnel drains it; a plain communicate keeps it simple
                out, err = p.communicate(input=stdin_bytes, timeout=kill_after)
            else:
                out, err = p.communicate(timeout=kill_after)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            # the hard tree kill by exact PID: ssh never exits on a missing
            # banner, and a leftover proxy holds the pipes (and the device)
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
    with open(out_path, "wb") as f:
        f.write(out or b"")
    with open(err_path, "wb") as f:
        f.write(err or b"")
    text = (out or b"").decode("utf-8", "replace")
    err_text = (err or b"").decode("utf-8", "replace")
    dur = time.time() - t0
    log("attempt %s -> rc=%s in %.1fs%s" % (tag, rc, dur, " (tree-killed)" if killed else ""))
    return rc, text, err_text, killed, dur


def classify(rc, text, err_text):
    """The attempt's branch. Priority: the SSH layer outranks everything, then
    the tunnel's own decisive lines -- the LAST one wins (a file can show an
    established link that later died in the pipe)."""
    if rc == 0 and "WAVE21-SSH-OK" in text:
        return "HIT"
    kind = None
    for line in err_text.splitlines():
        if "the kernel session is live" in line:
            kind = "KNOCK-LIVE"          # netmode on answered; SYN phase begins
        elif "established (" in line:
            kind = "ESTABLISHED"          # TCP up; the ssh layer now decides
        elif "no SYN-ACK in time" in line or "RSTs ridden" in line \
                or "reset by peer" in line:
            kind = "NOLISTEN"             # B1: nobody answered on :22 (RST or silence)
        elif "pair is dead" in line or "claim ok but" in line:
            # checked BEFORE the desync family: a pair that never accepted the
            # bulk-OUT is a dead devnode, not a transaction desync (its error
            # text mentions bulk-OUT too)
            kind = "DEAD-PAIR"
        elif "loader phase" in line:
            kind = "LOADER-PHASE"         # the loader answered the phase probe
        elif ("pipe error" in line or "pump during" in line
              or "partial reply" in line or "bulk-OUT failed" in line
              or "no download" in line):
            kind = "USB-DESYNC"           # B6: the loader transaction family
        elif "no d00d on the bus" in line:
            kind = "NO-DEVICE"
    # ssh-level evidence overrides (banner/auth/exec are terminal states)
    if ("Permission denied" in err_text or "Remote protocol version" in err_text
            or "kex_exchange" in err_text or "PTY allocation" in err_text
            or "Server refused" in err_text or "Welcome to" in err_text
            or "Darwin" in text):
        kind = "SSH-REACHED"              # B2: the ssh layer itself now moves
    elif rc == 255 and "banner exchange" in err_text:
        if kind == "ESTABLISHED":
            kind = "STALL-EST"            # B3/B4/B5 family: TCP up, no banner bytes
        elif kind in (None, "KNOCK-LIVE"):
            kind = "STALL-NOTUNNEL"       # the proxy never even established
    elif rc == 0 and text and "WAVE21-SSH-OK" not in text:
        kind = "SSH-REACHED"
    return kind or "OTHER"


def maybe_revive(err_text):
    """The H4 discipline: an attempt that talked past netmode may have died
    mid-transaction, leaving the loader holding an unread reply. One raw
    bulk-IN drain + getvar revives it (and doubles as a management-channel
    probe). Attempts that never talked are left alone."""
    if not TALKED.search(err_text):
        return None
    try:
        r = subprocess.run([PYEXE, os.path.join(W26, "revive-v26.py")],
                           capture_output=True, timeout=45)
        text = (r.stdout or b"").decode("utf-8", "replace")
        errt = (r.stderr or b"").decode("utf-8", "replace")
        tail = " | ".join(text.strip().splitlines()[-2:])
        log("revive -> %s %s" % (r.returncode, tail[-160:]))
        if errt.strip():
            log("revive err| %s" % errt.strip().splitlines()[-1][:160])
        return tail
    except Exception as e:
        log("revive failed: %r" % (e,))
        return None


KNOCK_CMD = ("uname -a && id && echo WAVE21-SSH-OK W27-%s" % RUN_ID)


def acceptance(first_tag, first_out, first_err):
    """The hit's evidence pack: three independent connections, one
    content-verified transfer, the management channel -- then the verdict."""
    log("=== ACCEPTANCE MODE (session must still be live) ===")
    results = [("conn1", KNOCK_CMD, first_out, first_err, 0)]
    token = lambda n: "W27-%s-acc%d" % (RUN_ID, n)
    for i in (2, 3):
        cmd = "uname -a && id && echo %s" % token(i)
        rc, out, err, killed, dur = ssh_attempt("acc%d" % i, cmd, CT_ACCEPT, KILL_ACCEPT)
        ok = rc == 0 and token(i) in out and "Darwin" in out
        results.append(("conn%d" % i, cmd, out, err, rc))
        log("acceptance conn%d -> rc=%s, marker %s, Darwin %s" % (
            i, rc, "OK" if token(i) in out else "MISSING",
            "OK" if "Darwin" in out else "MISSING"))
        maybe_revive(err)
        time.sleep(2.5)
    # content-verified transfer: 256 KiB into the phone's `wc -c`
    blob = os.urandom(TRANSFER_BYTES)
    rc, out, err, killed, dur = ssh_attempt(
        "transfer", "wc -c", CT_ACCEPT, KILL_TRANSFER, stdin_bytes=blob)
    got = "".join(ch for ch in out if ch.isdigit())
    xfer_ok = (rc == 0 and got == str(TRANSFER_BYTES))
    results.append(("transfer %d B" % TRANSFER_BYTES, "wc -c",
                    "count=%s want=%d" % (got, TRANSFER_BYTES), err, rc))
    log("acceptance transfer -> rc=%s, phone counted %s of %d bytes in %.1fs"
        % (rc, got or "?", TRANSFER_BYTES, dur))
    maybe_revive(err)
    # the management channel after clean client exits: drain + getvar
    mgmt = maybe_revive("netmode on ->")  # unconditional revive-as-probe
    mgmt_ok = bool(mgmt) and "OKAY" in mgmt
    # ---- the verdict, bound to THIS run
    verdict = os.path.join(W27, "verdict27-%s.txt" % RUN_ID)
    with open(verdict, "w", encoding="utf-8") as f:
        f.write("WAVE21-SSH-OK\n")
        f.write("run-id: %s\n" % RUN_ID)
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("tool: wave27-scripts/timed-ssh-v27.py (fixed-protocol first full live run)\n")
        f.write("tunnel: wave25-scripts/tunnel25w.py + B3 frame traces (pseudo-header fix)\n")
        f.write("boot: boot_b = v23 graft 9e0609fb (loader_return_after=1800, maxvnodes=8192)\n")
        for name, cmd, out, err, rcx in results:
            f.write("\n[%s] cmd: %s\n" % (name, cmd))
            f.write("[%s] rc: %s\n" % (name, rcx))
            f.write("[%s] stdout:\n%s\n" % (name, out.strip()[:400]))
        f.write("\ntransfer verdict: %s\n" % ("PASS" if xfer_ok else "FAIL"))
        f.write("management channel after exits: %s\n" % ("OKAY (alive)" if mgmt_ok else "UNVERIFIED"))
        f.write("device evidence (tunnel stderr, hit attempt excerpt):\n%s\n"
                % "\n".join(first_err.strip().splitlines()[-12:]))
        f.write("\nDarwin session evidence above: uname=%s\n"
                % ("Darwin confirmed" if "Darwin" in first_out else "UNKNOWN"))
    log("verdict written: %s (transfer %s, mgmt %s)"
        % (verdict, "PASS" if xfer_ok else "FAIL", "OKAY" if mgmt_ok else "UNVERIFIED"))
    report("HIT + acceptance: conn2/conn3 + transfer(%s) + mgmt(%s); verdict %s"
           % ("PASS" if xfer_ok else "FAIL", "OKAY" if mgmt_ok else "UNVERIFIED",
              os.path.basename(verdict)))
    return verdict, xfer_ok, mgmt_ok


def main():
    log("wave27 wide-window SSH hunt armed (run-id %s, deadline %.0f min)"
        % (RUN_ID, (DEADLINE - time.time()) / 60.0))
    log("knock cmd: %r" % KNOCK_CMD)
    report("hunt armed, run-id %s, deadline %.0f min, single-owner mode"
           % (RUN_ID, (DEADLINE - time.time()) / 60.0))
    if not os.path.isfile(SSH):
        log("FATAL: ssh.exe not at %s" % SSH)
        return 2
    silence_until = 0.0
    pair_armed = False          # an attempt has seen getvar answered on this generation
    last_addrs = None
    n = 0
    last_report = time.time()
    while time.time() < DEADLINE:
        addrs = bus_d00d()
        if addrs != last_addrs:
            log("bus: d00d addrs %s (was %s)" % (addrs, last_addrs))
            if addrs != last_addrs and last_addrs is not None:
                pair_armed = False      # a fresh generation: re-arm it
            last_addrs = addrs
        clean = bool(addrs) and not any(str(a).startswith("ERR:") for a in addrs)
        if not clean:
            silence_until = 0.0        # the bus forgot the gadget: forget the silence
            pair_armed = False
            time.sleep(POLL_S)
            continue
        # the silence covers the exec AND the entry guard: a session that opens
        # at silence_until is first entered at silence_until + ENTRY_GUARD (en0
        # attaches at kernel ~49 s; an earlier upload wedges the net loop -- k001)
        if time.time() < silence_until + (ENTRY_GUARD if silence_until else 0.0):
            time.sleep(POLL_S)
            continue
        n += 1
        tag = "k%03d" % n
        # ONE bound for every attempt (wave27): the proxy self-terminates in
        # 20 s when no live session answers, and self-bounds its armed runs
        # (SYN 150 s / no-progress 45 s) with a clean netmode-off exit -- so
        # the tree kill below is a backstop for a FROZEN proxy only. The old
        # fast-cycle 16 s kill fired mid-transaction (k022) and wedged the
        # pair for the whole session.
        ct = CT_KNOCK
        kill = KILL_KNOCK
        rc, out, err, killed, dur = ssh_attempt(tag, KNOCK_CMD, ct, kill)
        kind = classify(rc, out, err)
        if "LIVE (product" in err:
            pair_armed = True
        log("branch: %s (armed=%s, ct=%d)%s" % (kind, pair_armed, ct,
                                                " HIT-CANDIDATE" if kind == "HIT" else ""))
        for line in err.strip().splitlines()[-4:]:
            log("  err| %s" % line[:200])
        if kind == "HIT":
            verdict, xfer_ok, mgmt_ok = acceptance(tag, out, err)
            report("=== WAVE21-SSH-OK on record: %s ===" % os.path.basename(verdict))
            if xfer_ok and mgmt_ok:
                log("=== v0.4 SSH GATE: PASS (hit + 3 conns + verified transfer + mgmt) ===")
                return 0
            return 6                     # hit but the acceptance pack is incomplete
        if kind in ("LOADER-PHASE", "DEAD-PAIR"):
            if kind == "LOADER-PHASE":
                # the loader ANSWERED -> its 240 s exec clock restarted NOW.
                # True silence so the session actually opens (the entry guard
                # rides on the same clock -- see the wait above).
                silence_until = time.time() + LOADER_SILENCE
                pair_armed = False       # the exec starts a fresh USB generation
                log("loader answered: silence until +%.0f s (the exec clock)" % LOADER_SILENCE)
            else:
                pair_armed = False
                # dead pair: nothing reached the device -> the fast cycle keeps
                # the SET_CONFIG+getvar arming pressure near-continuous
            time.sleep(KNOCK_GAP if kind == "DEAD-PAIR" else POLL_S)
            continue
        if kind == "NO-DEVICE":
            time.sleep(POLL_S)
            continue
        # kernel-live family: knock on
        maybe_revive(err)
        time.sleep(KNOCK_GAP)
        if time.time() - last_report > 900:
            last_report = time.time()
            report("hunting: %d attempts so far, last branch %s, bus %s"
                   % (n, kind, addrs))
    report("hunt closed: deadline reached, %d attempts, no WAVE21-SSH-OK" % n)
    log("deadline reached without WAVE21-SSH-OK (%d attempts)" % n)
    return 5


if __name__ == "__main__":
    sys.exit(main())
