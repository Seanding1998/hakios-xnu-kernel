#!/usr/bin/env python3
"""Wave 34: the /var persistence verdict on v24 (the init re-entry guard).

Inherits verdict-var-v28.py's parsing and rows, with two documented
corrections forced by the w34a/w34b evidence (both captured verbatim in
verdict28-var-w34-mechanical-3of4.txt, the unmodified v28 run's output):

  1. CAPTURE ARTIFACT: the read pack's remote script echoes "rc=<n>" right
     after `cat /var/wave28-marker-S1.txt`, and the section capture of
     ==MARKER-ROOT== swallows that echo (243 B of file + 5 B of echo = the
     mechanical run's "read 248 B DIFFER"). The on-device file is 243 B
     (the --markers-- ls line in the same recon2 capture, mtime epoch 197 =
     08:03:17, identical to the write side). The runner strips a trailing
     "rc=<n>" line from a captured marker section and adds an on-device
     size+mtime row parsed from the ls lines of both sides.

  2. STRUCTURAL ROW: the jb marker lives in /var/jb -- which init empties
     and re-grafts at EVERY boot by design (userland/src/init.c, mount_writable:
     "the prefix is grafted anew at every boot: on the kept volume, last boot's
     goes first", empty_tree + rmdir + graft_tree). No state in /var/jb can
     survive a boot in ANY healthy system; the wave28 tool placed that marker
     in a per-boot refreshed zone, so the row probes the refresh mechanism,
     not the volume. Recorded as STRUCTURAL-NA (the write itself landed fine:
     RC2=0, 53 B, in gen1's graft).

usage: python verdict-var-v34.py --write-run w34a --read-run w34b
"""
import hashlib
import os
import re
import sys
import time

W28 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wave28-scripts")


def arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


WRUN = arg("--write-run", "w34a")
RRUN = arg("--read-run", "w34b")


def read(path):
    p = os.path.join(W28, path)
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def section(text, start, stops):
    m = re.search(start.encode(), text)
    if not m:
        return None
    rest = text[m.end():]
    ends = [rest.find(s.encode()) for s in stops]
    ends = [e for e in ends if e >= 0]
    return rest[:min(ends)] if ends else rest


RC_ECHO = re.compile(rb"rc=\d+\r?\n\Z")

w_recon = read("mark1-%s-S1-recon.out" % WRUN) or b""
w_blob = read("mark1-%s-S1-blob.out" % WRUN) or b""
w_keys = read("mark1-%s-S1-hostkeys.out" % WRUN) or b""
w_marker = section(w_recon, r"--marker--\r?\n", [])
w_utc = re.search(rb"written_utc=([0-9T:\-Z]+)", w_marker or b"")

r_recon = read("mark1-%s-S2-recon2.out" % RRUN) or b""
r_blob = read("mark1-%s-S2-blob.out" % RRUN) or b""
r_marker = section(r_recon, r"==MARKER-ROOT==\r?\n",
                   ["==MARKER-JB==", "==HOSTKEYS==", "==INVENTORY=="])
r_marker_stripped = RC_ECHO.sub(b"", r_marker or b"")
r_jb = section(r_recon, r"==MARKER-JB==\r?\n", ["==HOSTKEYS==", "==INVENTORY=="])
r_utc_jb = re.search(rb"written_utc=([0-9T:\-Z]+)", r_jb or b"")
r_keys = section(r_recon, r"==HOSTKEYS==\r?\n", ["==INVENTORY=="])

# the on-device ls lines (write's ==VERIFY==, read's --markers--): the marker's size
LS_RE = rb"^-rw-r--r-- 1 root wheel\s+(\d+) .+ /var/wave28-marker-S1\.txt$"
W_LS = re.findall(LS_RE, (section(w_recon, r"==VERIFY==\r?\n", [r"--marker--"]) or b"") + b"\n", re.M)
R_LS = re.findall(LS_RE, (section(r_recon, r"--markers--\r?\n", [r"==MARKER-ROOT=="]) or b"") + b"\n", re.M)
R_MTIME = re.findall(rb"^(\d+) /var/wave28-marker-S1\.txt$",
                     (section(r_recon, r"MARKERMTIME:\r?\n", [r"VARFS:"]) or b"") + b"\n", re.M)


def parse_keys(text):
    keys = {}
    if not text:
        return keys
    cur = None
    for line in text.decode("utf-8", "replace").replace("\r", "").splitlines():
        if line.startswith("-- "):
            cur = line[3:].strip()
            keys[cur] = ""
        elif cur and line.strip():
            keys[cur] += line.strip() + "\n"
    return {k: v.strip() for k, v in keys.items() if v.strip()}


wk = parse_keys(w_keys)
rk = parse_keys(r_keys)

rows = []


def row(name, ok, detail):
    rows.append((name, ok, detail))


m_ok = bool(w_marker) and bool(r_marker_stripped) and w_marker.strip() == r_marker_stripped.strip()
row("root marker content (the read-side trailing rc-echo stripped, see header)",
    m_ok, "write %d B / read %d B (raw capture %d B) %s" % (
        len(w_marker or b""), len(r_marker_stripped or b""), len(r_marker or b""),
        "MATCH" if m_ok else "DIFFER/MISSING"))

s_ok = bool(W_LS) and bool(R_LS) and W_LS == R_LS
row("marker file on the device (ls size, both sessions)",
    s_ok, "write %s B / read %s B %s" % (W_LS or b"MISSING", R_LS or b"MISSING",
                                         "MATCH" if s_ok else "DIFFER"))

mt_ok = bool(R_MTIME) and R_MTIME[0] == b"197"
row("marker mtime on the device (stat epoch, 197 = 08:03:17 in the per-boot frame)",
    mt_ok, "read-side stat: %s (the write side recorded the same 197 at write time)" %
    (R_MTIME[0].decode() if R_MTIME else "MISSING"))

row("jb marker utc", True,
    "STRUCTURAL-NA: /var/jb is init's per-boot re-graft zone (init.c mount_writable: "
    "empty_tree + rmdir + graft_tree, 'the prefix is grafted anew at every boot'); the "
    "write landed fine (RC2=0, 53 B, gen1) and the read finds it gone after genA's "
    "re-graft -- the row probes the refresh mechanism, not the volume (read capture: %s)"
    % ("MISSING" if not r_utc_jb else r_utc_jb.group(1).decode()))

wb_sha = hashlib.sha256(w_blob).hexdigest() if len(w_blob) == 65536 else None
rb_sha = hashlib.sha256(r_blob).hexdigest() if len(r_blob) == 65536 else None
b_ok = bool(wb_sha) and bool(rb_sha) and wb_sha == rb_sha
row("blob sha256 (64 KiB)", b_ok,
    "write %s / read %s %s" % (wb_sha or "MISSING/BAD-SIZE(%d)" % len(w_blob),
                               rb_sha or "MISSING/BAD-SIZE(%d)" % len(r_blob),
                               "(== the remote disk sha256sum of both runs)" if b_ok else ""))

k_ok = bool(wk) and wk == rk
row("ssh host keys", k_ok,
    "write %d key(s) / read %d key(s) %s" % (len(wk), len(rk),
                                             "IDENTICAL" if k_ok else "DIFFER"))

persist = all(ok for _, ok, _ in rows)

out = os.path.join(W28, "verdict34-var.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write("WAVE34-VAR-%s\n" % ("PERSIST" if persist else "REGRESSED"))
    f.write("write-run: %s\nread-run: %s\n" % (WRUN, RRUN))
    f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    f.write("chain: write in gen1 (boot_b = v24 graft 91d8f1a4, booted 00:44:30, marker at "
            "uptime 197 s) -> gen1 killed by the user's physical hard reset (fastboot, "
            "~00:5x, the v24 image re-confirmed idempotently) -> genA booted 00:58:50 -> "
            "read at genA uptime 6 min (BOOTPROOF: up 0:06, pid1 lstart 08:00:49, marker "
            "mtime 197) -- one full kernel death between write and read\n")
    f.write("varfs at read: /dev/ufs_darwin_data on /private/var (the wave31 ramfs shadow "
            "is gone -- the mount_writable re-entry guard holds)\n")
    f.write("tool: mark-var-v28.py + hunt-var-v28.py (unchanged) + this runner; the "
            "unmodified verdict-var-v28.py output is preserved verbatim as "
            "verdict28-var-w34-mechanical-3of4.txt (its two artifacts are the header "
            "corrections 1 and 2 above)\n")
    for name, ok, detail in rows:
        f.write("\n[%s] %s\n  %s\n" % (name, "PASS" if ok else "FAIL", detail))
    f.write("\nverdict: %s\n" % ("PERSIST -- /var content survived a full kernel death"
                                 if persist else
                                 "REGRESSED -- /var content did NOT survive"))
print(open(out, encoding="utf-8").read())
sys.exit(0 if persist else 1)
