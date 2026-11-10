#!/usr/bin/env python3
"""Wave 28: the /var persistence verdict. Compares the session-1 WRITE
package against the session-2 READ package:

  1. root marker content  (/var/wave28-marker-S1.txt)
  2. jb marker utc        (/var/jb/wave28-marker-S1.txt, vs the root utc)
  3. blob integrity       (sha256 of the 64 KiB blob bytes, both sessions)
  4. ssh host keys        (exact .pub contents across the boot cycle)

PERSIST  = all four hold (content-identical across a full boot cycle)
REGRESSED = any of them differs or is missing (the failing rows say which)

The judgment is written to wave28-scripts/verdict28-var.txt regardless.

usage: python verdict-var-v28.py --write-run ID --read-run ID
"""
import hashlib
import os
import re
import sys
import time

W28 = os.path.dirname(os.path.abspath(__file__))


def arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


WRUN = arg("--write-run")
RRUN = arg("--read-run")
if not WRUN or not RRUN:
    print("usage: verdict-var-v28.py --write-run ID --read-run ID")
    sys.exit(2)


def read(path):
    p = os.path.join(W28, path)
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def section(text, start, stops):
    """The bytes between the start marker line and the next stop marker."""
    m = re.search(start.encode(), text)
    if not m:
        return None
    rest = text[m.end():]
    ends = [rest.find(s.encode()) for s in stops]
    ends = [e for e in ends if e >= 0]
    return rest[:min(ends)] if ends else rest


# ---- session 1 (write) ------------------------------------------------------
w_recon = read("mark1-%s-S1-recon.out" % WRUN) or b""
w_blob = read("mark1-%s-S1-blob.out" % WRUN) or b""
w_keys = read("mark1-%s-S1-hostkeys.out" % WRUN) or b""

w_marker = section(w_recon, r"--marker--\r?\n", [])
w_utc = re.search(rb"written_utc=([0-9T:\-Z]+)", w_marker or b"")

# ---- session 2 (read) -------------------------------------------------------
r_recon = read("mark1-%s-S2-recon2.out" % RRUN) or b""
r_blob = read("mark1-%s-S2-blob.out" % RRUN) or b""

r_marker = section(r_recon, r"==MARKER-ROOT==\r?\n",
                   [ "==MARKER-JB==", "==HOSTKEYS==", "==INVENTORY==" ])
r_jb = section(r_recon, r"==MARKER-JB==\r?\n",
               [ "==HOSTKEYS==", "==INVENTORY==" ])
r_utc_jb = re.search(rb"written_utc=([0-9T:\-Z]+)", r_jb or b"")
r_keys = section(r_recon, r"==HOSTKEYS==\r?\n", [ "==INVENTORY==" ])

# ---- host key maps ----------------------------------------------------------

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

# ---- the four checks --------------------------------------------------------
rows = []


def row(name, ok, detail):
    rows.append((name, ok, detail))


m_ok = bool(w_marker) and bool(r_marker) and w_marker.strip() == r_marker.strip()
row("root marker", m_ok,
    "write %d B / read %d B %s" % (len(w_marker or b""), len(r_marker or b""),
                                   "MATCH" if m_ok else "DIFFER/MISSING"))

jb_ok = bool(w_utc) and bool(r_utc_jb) and w_utc.group(1) == r_utc_jb.group(1)
row("jb marker utc", jb_ok,
    "write %s / read %s" % (w_utc.group(1).decode() if w_utc else "MISSING",
                            r_utc_jb.group(1).decode() if r_utc_jb else "MISSING"))

wb_sha = hashlib.sha256(w_blob).hexdigest() if len(w_blob) == 65536 else None
rb_sha = hashlib.sha256(r_blob).hexdigest() if len(r_blob) == 65536 else None
b_ok = bool(wb_sha) and bool(rb_sha) and wb_sha == rb_sha
row("blob sha256 (64 KiB)", b_ok,
    "write %s / read %s" % (wb_sha or "MISSING/BAD-SIZE(%d)" % len(w_blob),
                            rb_sha or "MISSING/BAD-SIZE(%d)" % len(r_blob)))

k_ok = bool(wk) and wk == rk
row("ssh host keys", k_ok,
    "write %d key(s) / read %d key(s) %s" % (
        len(wk), len(rk),
        "IDENTICAL" if k_ok else ("DIFFER: %s" % sorted(
            set(wk.items()) ^ set(rk.items()))[:2] if (wk or rk) else "MISSING")))

persist = all(ok for _, ok, _ in rows)

# ---- the verdict file -------------------------------------------------------
out = os.path.join(W28, "verdict28-var.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write("WAVE28-VAR-%s\n" % ("PERSIST" if persist else "REGRESSED"))
    f.write("write-run: %s\nread-run: %s\n" % (WRUN, RRUN))
    f.write("when: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    f.write("boot cycle: session1 exec -> 1800s cap -> return -> save window -> "
            "re-arm/march -> session2 exec (both sessions on boot_b = v23 graft "
            "9e0609fb, var_hfs=ufs_darwin_data)\n")
    f.write("tool: wave28-scripts/mark-var-v28.py + hunt-var-v28.py + this script\n")
    for name, ok, detail in rows:
        f.write("\n[%s] %s\n  %s\n" % (name, "PASS" if ok else "FAIL", detail))
    f.write("\nverdict: %s\n" % ("PERSIST -- /var content survived the boot cycle"
                                 if persist else
                                 "REGRESSED -- /var content did NOT survive"))
print(open(out, encoding="utf-8").read())
sys.exit(0 if persist else 1)
