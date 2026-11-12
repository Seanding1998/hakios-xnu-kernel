#!/usr/bin/env python3
"""Wave 38/42 (domain-external execution for wave 39, per the main agent's addendum;
runner criteria upgraded per wave41-gpu-fix.md s6 -- that upgrade is this file's
wave-42 delta): run the GL first-frame attempt inside a live SSH session and capture
the evidence.

Execution + capture ONLY; the six-branch verdict table belongs to wave39
(docs/waves/wave39-mesa-userland.md s4.4). Session order per wave39 s4.5:
  1. the kernel-log tail via SSH (the GPU keep=1 no-change observation for wave38's gates)
  2. gl_test 8 <W> <H>   -- the first-frame attempt (the kHakiosShow puts it on the panel)
  3. gl_test fill        -- the frame-cost profile (only if there is session time)
  4. u2f_test            -- the uint->float path
Single Windows-libusb owner while running (tunnel25w children only).

Wave 42 runner criteria (wave41 s6):
  - the remote shell stores the real rc then echoes it: `gl_test ...; echo GL_RC=$?`;
    the runner PARSES GL_RC=(\\d+) numerically (substring existence is not a verdict);
  - hardware DONE = GL_RC==0 AND 'RENDER_PASS backend=hw' AND 'READBACK_PASS samples'
    AND 'PRESENT_CALL_OK' AND no _FAIL line anywhere in the output;
  - the token 'gl_test:' NEVER constitutes completion ('no OpenGL ES context' is
    gl_test's own failure branch C output);
  - 'RENDER backend=sw' / renderer != FD725 / PRESENT_CALL_FAIL (rc=3) are recorded
    as their own states -- a software comparison is evidence, never hardware DONE;
  - every attempt gets unique stdout/stderr files (RUN_ID+tag+sequence), no overwrite;
  - on the v35 carrier (c2780842) gl_test predates the structured verifier lines, so
    a run there is DIAGNOSTIC ONLY (machine facts: hung or not, klog lines, panel
    frame) -- 'first-frame success' is not claimable on it (review P1-b).

usage: python gltest-run-v38.py [--deadline-minutes 60] [--run-id ID] [--size WxH]
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
W27 = os.path.join(REPO, "wave27-scripts")
sys.path.insert(0, W13)

KEY = os.path.join(W21, "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"C:\Users\<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(W25, "tunnel25w.py"))
OUTDIR = os.path.join(REPO, "wave38-scripts")

CT = 20          # connect timeout per attempt
KILL = 240       # gl_test 8 draws + shows for 8 s; give it minutes
KILL_FILL = 420  # the fill profile runs 160 frames
SILENCE = 260.0  # the loader-silence cadence between failed attempts (>= 260 s)

def arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default

RUN_ID = arg("--run-id", time.strftime("%Y%m%d-%H%M%S"))
SIZE = arg("--size", "")          # "1080x2400" style; empty = the binary's default
DEADLINE = time.time() + 60 * float(arg("--deadline-minutes", "60"))
LOGP = os.path.join(OUTDIR, "gltest-run-v38-%s.log" % RUN_ID)

_started = time.time()
_attempt_seq = {}

def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOGP, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)

def ssh_attempt(tag, remote_cmd, kill_after):
    seq = _attempt_seq.get(tag, 0) + 1
    _attempt_seq[tag] = seq
    out_path = os.path.join(OUTDIR, "gltest-%s-%s-%02d.out" % (RUN_ID, tag, seq))
    err_path = os.path.join(OUTDIR, "gltest-%s-%s-%02d.err" % (RUN_ID, tag, seq))
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=%d" % CT,
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "root@10.0.0.2",
           remote_cmd]
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(timeout=kill_after)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        rc = -9
    dur = time.time() - t0
    open(out_path, "wb").write(out or b"")
    open(err_path, "wb").write(err or b"")
    log("attempt %s#%d -> rc=%s in %.1fs (out %d B -> %s)" %
        (tag, seq, rc, dur, len(out or b""), os.path.basename(out_path)))
    return rc, (out or b"").decode("utf-8", "replace"), dur

def classify(out, rc):
    """The wave41-s6 verdict classifier. Returns (state, detail)."""
    m = re.search(r"GL_RC=(\d+)", out)
    gl_rc = int(m.group(1)) if m else None
    has_hw = "RENDER_PASS backend=hw" in out
    has_readback = "READBACK_PASS samples" in out
    has_present = "PRESENT_CALL_OK" in out
    has_fail = "_FAIL" in out
    sw = ("backend=sw" in out) or ("softpipe" in out.lower()) or ("llvmpipe" in out.lower())
    if rc != 0 and gl_rc is None and not out.strip():
        return "no-session", "no remote output (connect/session phase failed; ssh rc=%s)" % rc
    if "no OpenGL ES context" in out:
        return "branch-C", "context creation failed (dyld/SDK layer); gl_rc=%s" % gl_rc
    if "PRESENT_CALL_FAIL" in out or gl_rc == 3:
        return "present-fail", "the panel call failed (no GPU service path); gl_rc=%s" % gl_rc
    if sw and gl_rc == 0 and "_FAIL" not in out:
        return "software-comparison", "a software renderer drew it -- evidence, never hardware DONE"
    if gl_rc == 0 and has_hw and has_readback and has_present and not has_fail:
        return "hardware-DONE", "RENDER_PASS backend=hw + READBACK_PASS + PRESENT_CALL_OK, no _FAIL"
    if gl_rc == 0:
        return "unstructured-rc0", "rc=0 but the structured verifier lines are absent (the v35 " \
               "carrier's gl_test predates them): DIAGNOSTIC ONLY -- machine facts only, no " \
               "first-frame claim (review P1-b)"
    if gl_rc is not None:
        detail = "gl_test exited %s" % gl_rc
        if gl_rc == 1:
            detail += " (context or program failure)"
        elif gl_rc == 2:
            detail += " (pixel/readback failure -- branch E territory)"
        elif gl_rc == 4:
            detail += " (GL error)"
        return "remote-fail", detail
    return "no-session", "session ended without a GL_RC echo (remote command phase; ssh rc=%s)" % rc

def main():
    if not os.path.isfile(SSH):
        log("FATAL: ssh.exe not at %s" % SSH)
        return 2
    size_arg = ""
    if SIZE:
        m = re.match(r"^(\d+)x(\d+)$", SIZE)
        if not m:
            log("FATAL: --size wants WxH")
            return 2
        size_arg = " " + m.group(1) + " " + m.group(2)

    # wave42: the w42gl1 field round proved the session shell cannot find gl_test on
    # its PATH (zsh command not found, GL_RC=127) -- every step self-locates the binary
    _FIND = ("G=$(command -v %s || find /bin /usr/bin /usr/local/bin /var/jb /Applications "
             "-maxdepth 4 -name %s 2>/dev/null | head -1); echo GLBIN=$G; ")
    GFILL = (_FIND % ("gl_test", "gl_test")) + '[ -n "$G" ] && $G'
    GU2F = (_FIND % ("u2f_test", "u2f_test")) + '[ -n "$G" ] && $G'

    steps = [
        ("klog", "tail -c 131072 /dev/logdump 2>/dev/null | tail -40; "
                 "echo PATH=$PATH; echo ==WHICH==; command -v gl_test u2f_test; "
                 "echo ==BIN==; ls -la /bin 2>/dev/null | head -40; "
                 "echo ==DISCOVERY-END==", 60),
        ("gl", "G=$(command -v gl_test || find /bin /usr/bin /usr/local/bin /var/jb /Applications "
               "-maxdepth 4 -name gl_test 2>/dev/null | head -1); echo GLBIN=$G; "
               "[ -n \"$G\" ] && $G 8" + size_arg + " 2>&1; echo GL_RC=$?", KILL),
    ]
    log("gltest runner armed (run-id %s, deadline %.0f min, size %r; wave41-s6 criteria)" %
        (RUN_ID, (DEADLINE - time.time()) / 60.0, SIZE or "default"))

    done_gl = False
    while time.time() < DEADLINE:
        if not done_gl:
            rc, out, _ = ssh_attempt("klog", steps[0][1], steps[0][2])
            if rc == 0 and out.strip():
                log("klog tail captured (%d B): the GPU lines are in the .out file" % len(out))
            rc, out, dur = ssh_attempt("gl", steps[1][1], steps[1][2])
            state, detail = classify(out, rc)
            log("gl attempt state=%s: %s" % (state, detail))
            for line in out.splitlines():
                if ("gl_test:" in line or "GL_RC" in line or "RENDER_PASS" in line
                        or "READBACK_PASS" in line or "PRESENT_CALL" in line
                        or "_FAIL" in line or "renderer" in line.lower()):
                    log("  | %s" % line)
            if state in ("hardware-DONE", "software-comparison", "branch-C",
                         "present-fail", "remote-fail", "unstructured-rc0"):
                # a real answer (any branch) -- capture the extras while the session lives
                rc2, out2, _ = ssh_attempt("fill", GFILL + " fill 1080 2400 2>&1; echo FILL_RC=$?", KILL_FILL)
                log("fill profile rc=%s (%d B captured)" % (rc2, len(out2 or "")))
                rc3, out3, _ = ssh_attempt("u2f", GU2F + " 2>&1; echo U2F_RC=$?", 120)
                log("u2f_test rc=%s (%d B captured)" % (rc3, len(out3 or "")))
                log("DONE (state=%s): the GL evidence set is in wave38-scripts/gltest-%s-*.{{out,err}}"
                    % (state, RUN_ID))
                return 0
            # wave42: phase-adaptive cadence (the fixed 260 s sleep kept landing on
            # session-end boundaries -- w42gl2 hit two dying sessions back to back).
            # The attempt's own tunnel stderr names the phase; honor it the way the
            # wave27 machine does.
            err_file = os.path.join(OUTDIR, "gltest-%s-gl-%02d.err"
                                    % (RUN_ID, _attempt_seq.get("gl", 1)))
            terr = ""
            if os.path.isfile(err_file):
                terr = open(err_file, encoding="utf-8", errors="replace").read()
            if "loader phase" in terr or "FAILno recording" in terr:
                wait = SILENCE          # the loader answered: true silence (exec clock)
                why = "loader answered -- true silence so the exec happens"
            elif "kernel session is live" in terr or "established" in terr:
                wait = 5.0              # a live session: knock continuously
                why = "kernel session live but the step failed -- immediate retry"
            else:
                wait = 15.0             # dead pair / no device: keep the arming pressure
                why = "dead pair or no device -- short-cycle arming pressure"
            log("no verdict yet (%s); %d s -- %s (the wave27 LOADER_SILENCE lesson: the "
                "loader phase must go silent or the exec clock never fires)"
                % (state, int(wait), why))
            time.sleep(wait)
    log("deadline reached without a completed gl_test run")
    return 1

if __name__ == "__main__":
    sys.exit(main())
