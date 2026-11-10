#!/usr/bin/env python3
"""Wave 26: the timed ssh play.

The logdump verdict (logdump-v21-wave26-1.bin): sshd listens on :22 at session
age ~181 s (kernel 165.8 s) and the whole kernel collapses at ~238 s (kernel
222.6 s) under SpringBoard's post-boot XPC retry storm (commcenter.xpc lookups
at 3400-3900/s + chronod + sleepd; launchd's flush interval decays 56 ms ->
1000 ms, then everything stops). The en0 poll freeze is collateral of that
collapse -- "K1" was never an en0 driver bug.

So the ssh verdict has a window: T0+181 .. T0+237 (T0 = the gadget's first
appearance on the bus). This tool: watch for the generation, hold SILENT
(every loader command extends the window but says nothing to the kernel), then
from T0+178 run the wave25 ssh attempt back to back until T0+242. An attempt
that lands in the window meets a listening sshd on a living kernel.

usage: python timed-ssh-v26.py [--deadline-minutes 90]
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave13-scripts"))
import loader_talk as lt  # noqa: E402

HERE = os.path.join(REPO, "wave25-scripts")
W26 = os.path.join(REPO, "wave26-scripts")
LOG = os.path.join(W26, "timed-ssh-v26.log")
KEY = os.path.join(REPO, "wave21-scripts", "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
PYEXE = r"<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(HERE, "tunnel25w.py"))


def arg(name, default):
    for i, a in enumerate(sys.argv):
        if a == name:
            return sys.argv[i + 1]
    return default


RUN_ID = arg("--run-id", time.strftime("%H%M%S"))
VERDICT = os.path.join(W26, "verdict26-%s.txt" % RUN_ID)

FIRST_SEEN_GRACE = 178.0     # sshd listens ~181; start knocking just before
WINDOW_END = 600.0           # v22 (maxvnodes): no collapse expected -- knock for minutes

_started = time.time()


def log(msg):
    line = "[%s t+%06.1fs] %s" % (time.strftime("%H:%M:%S"), time.time() - _started, msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def gadget_age():
    """Seconds since the gadget first appeared (0.0 if it is not on the bus now)."""
    import ctypes
    lib = lt.Libusb()
    try:
        plist, n = lib.device_list()
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == 0x18D1 and d.idProduct == 0xD00D:
                return True
        return False
    except Exception:
        return False
    finally:
        lib.close()


def write_verdict(rc, text, err_excerpt, attempt_tag, elapsed_note):
    """The verdict, bound to THIS run: the run id, the rc, the command's output
    and the tunnel's own device evidence (the stderr carries `product
    b'xnuloader'` -- the device identity the attempt actually spoke to). A
    verdict file from another run never passes for this one (the name is the
    run's, and the content carries its id)."""
    with open(VERDICT, "w", encoding="utf-8") as f:
        f.write("WAVE21-SSH-OK\n")
        f.write("run-id: %s\n" % RUN_ID)
        f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("attempt: %s (%s)\n" % (attempt_tag, elapsed_note))
        f.write("ssh rc: %s\n" % rc)
        f.write("device evidence (tunnel stderr excerpt): %s\n" % err_excerpt[:200])
        f.write("\n%s\n" % text)
    return VERDICT


def ssh_attempt(tag):
    out_path = os.path.join(W26, "tssh-%s.out" % tag)
    err_path = os.path.join(W26, "tssh-%s.err" % tag)
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=30",
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "root@10.0.0.2",
           "uname -a && id && echo WAVE21-SSH-OK"]
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = p.communicate(timeout=52)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            # the hard tree kill: ssh never exits on a missing banner, and a
            # leftover tunnel proxy holds the pipes (and the device) forever --
            # taskkill /T ends the whole tree by PID. The bound keeps each
            # attempt inside the sshd window instead of eating it all.
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True)
            out, err, rc = b"", b"", "TIMEOUT-TREEKILLED"
    except Exception as e:
        out, err, rc = b"", repr(e).encode(), "SPAWN-FAIL"
    with open(out_path, "wb") as f:
        f.write(out)
    with open(err_path, "wb") as f:
        f.write(err)
    text = out.decode("utf-8", "replace")
    err_text = err.decode("utf-8", "replace")
    ok = "WAVE21-SSH-OK" in text and rc == 0
    log("attempt %s -> rc=%s in %.1fs: %s" % (tag, rc, time.time() - t0, "HIT" if ok else "miss"))
    for line in err_text.strip().splitlines()[-5:]:
        log("  err| %s" % line)
    for line in text.strip().splitlines()[:6]:
        log("  out| %s" % line)
    return ok, rc, text, err_text


def main():
    minutes = 90.0
    if "--deadline-minutes" in sys.argv:
        minutes = float(sys.argv[sys.argv.index("--deadline-minutes") + 1])
    deadline = time.time() + 60 * minutes
    continuous = "--continuous" in sys.argv
    if continuous:
        log("timed-ssh CONTINUOUS hunt armed (deadline %.0f min): back-to-back "
            "attempts (drain-revive between), no generation-boundary wait" % minutes)
    else:
        log("timed-ssh armed (deadline %.0f min): silent until T0+%.0f, attempts until T0+%.0f"
            % (minutes, FIRST_SEEN_GRACE, WINDOW_END))
    if continuous:
        n = 0
        while time.time() < deadline:
            n += 1
            # the arming window (Phase B finding): the loader's standing receive
            # is posted ~11 s after the gadget appears, and if no host writes to
            # the bulk pair inside that window the loader gives up -- the pair
            # stays dead for the whole generation. So the FIRST attempt fires
            # seconds after the gadget's appearance (its open+getvar write is
            # what arms the pair), and every failed attempt leaves the loader
            # holding an unread reply (the H4 wedge): one raw bulk-IN drain
            # revives it before the next attempt's probe reads stale bytes.
            if n > 1:
                try:
                    subprocess.run([PYEXE, os.path.join(W26, "revive-v26.py")],
                                   capture_output=True, timeout=25)
                except Exception:
                    pass
            ok, rc, text, err_text = ssh_attempt("c-%03d" % n)
            if ok:
                v = write_verdict(rc, text, err_text, "c-%03d" % n, "continuous attempt %d" % n)
                log("=== WAVE21-SSH-OK (continuous hunt, attempt %d) ===" % n)
                log("verdict written: %s" % v)
                return 0
            time.sleep(3)
        log("deadline reached without WAVE21-SSH-OK (continuous)")
        return 5
    # ---- non-continuous: the generation-boundary timed play (wave27 repair:
    # the block below was the intended control flow, left after the early
    # return with a stray `break` -- the file would not even parse)
    while time.time() < deadline:
        # find a generation: the gadget must be ABSENT first (so T0 = a fresh appearance)
        log("waiting for the bus to be empty of d00d (a generation boundary)...")
        while time.time() < deadline:
            if not gadget_age():
                break
            time.sleep(5)
        if time.time() >= deadline:
            break
        while time.time() < deadline and not gadget_age():
            time.sleep(2)
        t0 = time.time()
        log("T0: gadget appeared; holding silent until T0+%.0f" % FIRST_SEEN_GRACE)
        wait = FIRST_SEEN_GRACE - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
        n = 0
        while time.time() - t0 < WINDOW_END:
            n += 1
            if n > 1:
                # every attempt that died mid-command leaves the loader holding an
                # unread reply (the H4 wedge): one raw bulk-IN drain revives it
                # before the next attempt's probe reads stale bytes as its answer
                try:
                    subprocess.run([PYEXE, os.path.join(W26, "revive-v26.py")],
                                   capture_output=True, timeout=25)
                except Exception:
                    pass
            ok, rc, text, err_text = ssh_attempt("g0-%02d" % n)
            if ok:
                v = write_verdict(rc, text, err_text, "g0-%02d" % n, "T0+%.0f s" % (time.time() - t0))
                log("=== WAVE21-SSH-OK (timed play, T0+%.0f s) ===" % (time.time() - t0))
                log("verdict written: %s" % v)
                return 0
            time.sleep(2)
        log("window closed without a hit (T0+%.0f); next generation" % WINDOW_END)
    log("deadline reached without WAVE21-SSH-OK")
    return 5


if __name__ == "__main__":
    sys.exit(main())
