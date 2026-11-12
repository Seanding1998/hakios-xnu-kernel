#!/usr/bin/env python3
"""Wave 42 patch: replace timed-ssh-v42.py's two-connection sha round trip with a
single-connection one. The w42ssh3 field run proved the device-side half works
(512 KiB, device sha256sum == host hash, 68.4 s) but /tmp does NOT persist across
rc-ssh connections (the sha-out cat returned 0 B) -- so the round trip now rides
ONE connection: write /var/w42blob.bin, device-hashes it, cats it back in the same
session; the host byte-compares the returned payload and both hashes. Also re-roots
the verdict file at wave42-scripts (the derivation had kept W27)."""
path = "wave42-scripts/timed-ssh-v42.py"
src = open(path, encoding="utf-8").read()
orig = src

start = src.index("    # ---- wave42: the BIDIRECTIONAL CONTENT SHA round trip")
end = src.index("    # ---- end of the wave42 content block")
newblock = '''    # ---- wave42: the BIDIRECTIONAL CONTENT SHA round trip ----------------------
    # ONE connection rides both directions: the host streams a fresh 512 KiB blob
    # into /var/w42blob.bin, the DEVICE hashes what it received (sha256sum + wc -c),
    # then cats the same file back on the same session and removes it. The host
    # byte-compares the returned payload against the sent blob and checks both
    # hashes -- content, never length alone. (w42ssh3's field run: the device-side
    # half verified 512 KiB in 68.4 s; /tmp does not persist across rc-ssh
    # connections, hence the single connection and the /var path.)
    blob42 = os.urandom(524288)
    host_hash_sent = __import__("hashlib").sha256(blob42).hexdigest()
    _cmd42 = ("T=/var/w42blob.bin; cat > $T; sha256sum $T; wc -c < $T; cat $T; rm -f $T")

    def _sha_rt_parse(o):
        b = o.encode("utf-8", "surrogateescape")
        i = b.find(b"\\n")
        if i < 0:
            return "", "", b""
        j = b.find(b"\\n", i + 1)
        if j < 0:
            return "", "", b""
        _hl = b[:i].decode("utf-8", "replace").strip().split()
        dev_hash = _hl[0].lower() if _hl else ""
        count = "".join(ch for ch in b[i + 1:j].decode("utf-8", "replace") if ch.isdigit())
        return dev_hash, count, b[j + 1:]

    def _sha_rt_ok(r, o):
        if r != 0:
            return False
        _h, _c, _p = _sha_rt_parse(o)
        return _h == host_hash_sent and _p == blob42 and _c == str(len(blob42))

    rc42, out42, err42, k42, dur42 = retried(
        "sha-rt", _cmd42, KILL_TRANSFER, stdin_bytes=blob42, ok_check=_sha_rt_ok)
    dev_hash, dev_len, payload42 = _sha_rt_parse(out42)
    host_hash_got = __import__("hashlib").sha256(payload42).hexdigest()
    got_len = len(payload42)
    sha_in_ok = (rc42 == 0 and dev_hash == host_hash_sent)
    sha_out_ok = (rc42 == 0 and payload42 == blob42)
    sha_both_ok = sha_in_ok and sha_out_ok
    results.append(("content sha round trip %d B (one connection, both directions)" % len(blob42),
                    _cmd42,
                    "dev=%s host=%s payload=%s bytes=%s/%d"
                    % (dev_hash[:16] + ".." if dev_hash else "MISSING",
                       host_hash_sent[:16] + "..", host_hash_got[:16] + "..",
                       got_len, len(blob42)),
                    err42, rc42))
    log("content sha round trip -> rc=%s in %.1fs: device hash %s, returned payload %s "
        "(%d/%d B) -- %s" % (rc42, dur42,
                             "MATCH" if sha_in_ok else "MISMATCH",
                             "MATCH" if sha_out_ok else "MISMATCH",
                             got_len, len(blob42),
                             "PASS" if sha_both_ok else "FAIL"))
    maybe_revive(err42)
'''
src = src[:start] + newblock + src[end:]
n = src.count('verdict = os.path.join(W27, "verdict27-%s.txt" % RUN_ID)')
assert n == 1, f"verdict path anchor x{n}"
src = src.replace('verdict = os.path.join(W27, "verdict27-%s.txt" % RUN_ID)',
                  'verdict = os.path.join(W42, "verdict42-%s.txt" % RUN_ID)')
src = src.replace('log("verdict written: %s (transfer %s, sha %s, mgmt %s)"',
                  'log("verdict written: %s (transfer %s, sha %s, mgmt %s)"')
assert '"sha-in"' not in src and '"sha-out"' not in src, "old steps still referenced"
assert src != orig
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path} ({len(src)} B): single-connection sha round trip via /var, verdict re-rooted at wave42-scripts")
