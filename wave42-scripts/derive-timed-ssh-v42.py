#!/usr/bin/env python3
"""Wave 42: derive timed-ssh-v42.py from wave27's timed-ssh-v27.py.

Deltas (per the wave38 handoff s3.2 and the review-3 revised acceptance):
  1. BIDIRECTIONAL CONTENT SHA (the 'length != content' lesson): after the wc -c
     transfer, one connection streams a fresh 512 KiB blob into the phone's
     /tmp/w42blob.bin and reads back the device's sha256sum + wc -c; the next
     connection cats the file back and the HOST hashes the received bytes and
     compares both hash and length -- both directions carry megabyte-scale
     content, verified by content, not by length.
  2. the verdict's boot line stops being hardcoded to v23 (it names the v35
     graft actually flashed).
  3. artifacts (log + verdict + per-attempt out/err) land in wave42-scripts.

usage: python timed-ssh-v42.py [--deadline-minutes 480] [--run-id ID]
"""
import re

SRC = "wave27-scripts/timed-ssh-v27.py"
DST = "wave42-scripts/timed-ssh-v42.py"
src = open(SRC, encoding="utf-8").read()
orig = src


def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"anchor not unique ({n}x): {old[:80]!r}"
    src = src.replace(old, new)


# ---- paths: log + report + per-attempt artifacts go to wave42-scripts -------------
sub('W27 = os.path.join(REPO, "wave27-scripts")',
    'W27 = os.path.join(REPO, "wave27-scripts")\nW42 = os.path.join(REPO, "wave42-scripts")')
sub('LOG = os.path.join(W27, "hunt-phaseB-v27-%s.log" % RUN_ID)',
    'LOG = os.path.join(W42, "hunt-ssh-v42-%s.log" % RUN_ID)')
sub('REPORT = os.path.join(W27, "wave27-report.md")',
    'REPORT = os.path.join(W42, "wave42-report.md")')
# per-attempt .out/.err files (ssh_attempt writes them via its own path code)
src = sub_head = src  # (the attempt-file paths are handled below)

# find the per-attempt artifact paths inside ssh_attempt and re-root them at W42
assert src.count('W27, "tssh27-%s') == 2, "expected the two per-attempt path anchors"
src = src.replace('W27, "tssh27-%s', 'W42, "tssh42-%s')

# ---- the bidirectional content SHA, spliced after the wc -c transfer --------------
SHA_BLOCK = '''    maybe_revive(err)
    # ---- wave42: the BIDIRECTIONAL CONTENT SHA round trip ----------------------
    # host -> device: a fresh 512 KiB blob, hashed BY THE DEVICE on arrival;
    # device -> host: the same file cat'ed back, hashed BY THE HOST on arrival.
    # The verdict compares content hashes and lengths -- never length alone.
    blob42 = os.urandom(524288)
    rc42a, out42a, err42a, k42a, dur42a = ssh_attempt(
        "sha-in", "T=/tmp/w42blob.bin; cat > $T; sha256sum $T; wc -c $T; sync",
        CT_ACCEPT, KILL_TRANSFER, stdin_bytes=blob42)
    dev_hash, dev_len = "", ""
    for line in out42a.splitlines():
        p = line.split()
        if len(p) == 2 and len(p[0]) == 64 and all(c in "0123456789abcdef" for c in p[0].lower()):
            dev_hash = p[0].lower()
            dev_len = "".join(ch for ch in p[1] if ch.isdigit())
    host_hash_sent = __import__("hashlib").sha256(blob42).hexdigest()
    sha_in_ok = (rc42a == 0 and dev_hash == host_hash_sent and dev_len == str(len(blob42)))
    results.append(("sha host->device %d B" % len(blob42),
                    "cat > /tmp/w42blob.bin; sha256sum",
                    "dev=%s host=%s len=%s/%d" % (dev_hash or "?", host_hash_sent,
                                                  dev_len or "?", len(blob42)),
                    err42a, rc42a))
    log("sha host->device -> rc=%s, device hash %s, %s in %.1fs"
        % (rc42a, dev_hash[:16] + ".." if dev_hash else "MISSING",
           "MATCH" if dev_hash == host_hash_sent else "MISMATCH", dur42a))
    maybe_revive(err42a)
    rc42b, out42b, err42b, k42b, dur42b = ssh_attempt(
        "sha-out", "cat /tmp/w42blob.bin; rm -f /tmp/w42blob.bin",
        CT_ACCEPT, KILL_TRANSFER)
    host_hash_got = __import__("hashlib").sha256(out42b.encode("utf-8", "surrogateescape")).hexdigest()
    got_len = len(out42b.encode("utf-8", "surrogateescape"))
    sha_out_ok = (rc42b == 0 and host_hash_got == host_hash_sent and got_len == len(blob42))
    results.append(("sha device->host %d B" % len(blob42),
                    "cat /tmp/w42blob.bin",
                    "host-got=%s want=%s len=%s/%d" % (host_hash_got[:16] + "..",
                                                       host_hash_sent[:16] + "..",
                                                       got_len, len(blob42)),
                    err42b, rc42b))
    log("sha device->host -> rc=%s, %s in %.1fs (%d B round trip)"
        % (rc42b, "MATCH" if sha_out_ok else "MISMATCH", dur42b, got_len))
    maybe_revive(err42b)
    sha_both_ok = sha_in_ok and sha_out_ok
    # ---- end of the wave42 content block ---------------------------------------
'''
anchor = '''    log("acceptance transfer -> rc=%s, phone counted %s of %d bytes in %.1fs"
        % (rc, got or "?", TRANSFER_BYTES, dur))
    maybe_revive(err)
'''
assert src.count(anchor) == 1
src = src.replace(anchor, anchor + SHA_BLOCK)

# ---- the verdict block: boot line + sha verdicts -----------------------------------
sub('f.write("boot: boot_b = v23 graft 9e0609fb (loader_return_after=1800, maxvnodes=8192)\\n")',
    'f.write("boot: boot_b = v35 graft 6558d303ac792e6e0536b0b80deb3efcaa8195abaa4f398254ae869d7705f0a0 '
    '(kernel 55a8d40f + loader 5de055ea the wave42 root-fixed GEN-1..4 build + ramdisk c2780842 the '
    'GL=test carrier; loader_return_after=600, maxvnodes=8192)\\n")')
sub('f.write("tool: wave27-scripts/timed-ssh-v27.py (fixed-protocol first full live run)\\n")',
    'f.write("tool: wave42-scripts/timed-ssh-v42.py (v27 protocol + the wave42 bidirectional '
    'content-SHA round trip)\\n")')
sub('        f.write("\\ntransfer verdict: %s\\n" % ("PASS" if xfer_ok else "FAIL"))',
    '        f.write("\\ntransfer verdict: %s\\n" % ("PASS" if xfer_ok else "FAIL"))\n'
    '        f.write("content sha host->device: %s\\n" % ("MATCH" if sha_in_ok else "FAIL"))\n'
    '        f.write("content sha device->host: %s\\n" % ("MATCH" if sha_out_ok else "FAIL"))\n'
    '        f.write("content sha verdict: %s\\n" % ("PASS" if sha_both_ok else "FAIL"))')
sub('    report("HIT + acceptance: conn2/conn3 + transfer(%s) + mgmt(%s); verdict %s"\n'
    '           % ("PASS" if xfer_ok else "FAIL", "OKAY" if mgmt_ok else "UNVERIFIED",\n'
    '              os.path.basename(verdict)))',
    '    report("HIT + acceptance: conn2/conn3 + transfer(%s) + sha(%s) + mgmt(%s); verdict %s"\n'
    '           % ("PASS" if xfer_ok else "FAIL", "PASS" if sha_both_ok else "FAIL",\n'
    '              "OKAY" if mgmt_ok else "UNVERIFIED", os.path.basename(verdict)))')
sub('    log("verdict written: %s (transfer %s, mgmt %s)"\n'
    '        % (verdict, "PASS" if xfer_ok else "FAIL", "OKAY" if mgmt_ok else "UNVERIFIED"))',
    '    log("verdict written: %s (transfer %s, sha %s, mgmt %s)"\n'
    '        % (verdict, "PASS" if xfer_ok else "FAIL",\n'
    '           "PASS" if sha_both_ok else "FAIL", "OKAY" if mgmt_ok else "UNVERIFIED"))')

assert src != orig
open(DST, "w", encoding="utf-8", newline="").write(src)
print(f"written {DST} ({len(src)} B)")
