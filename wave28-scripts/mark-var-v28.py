#!/usr/bin/env python3
"""Wave 28: the /var persistence marker package, over one SSH attempt each.

Two modes, both zero-flash, both through the wave27-fixed protocol stack
(tunnel25w ProxyCommand + the wave21 key + Windows OpenSSH):

  --mode write   recon /var, write timestamped markers (/var + /var/jb),
                 seed a 64 KiB urandom blob, read the blob BACK and sha256 it
                 on the host, fingerprint the ssh host public keys locally
  --mode read    read the markers + blob + host keys again (the session-2
                 comparison set)

Every step is a separate ssh connection with its own .out/.err pair
(wave27 file discipline); one attempt at a time -- single owner. Tree kill
only as the frozen-proxy backstop (the tunnel self-exits cleanly).

usage: python mark-var-v28.py --mode write --tag S1 [--run-id ID]
"""
import hashlib
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W21 = os.path.join(REPO, "wave21-scripts")
W27 = os.path.join(REPO, "wave27-scripts")
W28 = os.path.join(REPO, "wave28-scripts")

KEY = os.path.join(W21, "id_ed25519_phk110")
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
SSH_KEYGEN = r"C:\Windows\System32\OpenSSH\ssh-keygen.exe"
PYEXE = r"<host>\AppData\Local\Programs\Python\Python313\python.exe"
PROXY = "%s %s" % (PYEXE, os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))

RUN_ID = time.strftime("%Y%m%d-%H%M%S")
if "--run-id" in sys.argv:
    RUN_ID = sys.argv[sys.argv.index("--run-id") + 1]
MODE = sys.argv[sys.argv.index("--mode") + 1]
TAG = sys.argv[sys.argv.index("--tag") + 1]

LOG = os.path.join(W28, "mark1-%s-%s.log" % (RUN_ID, TAG))
SUMMARY = os.path.join(W28, "mark1-%s-%s.txt" % (RUN_ID, TAG))

CT = 170          # proxy self-exits at 150s SYN / 45s no-progress; this is the outer
KILL = 200        # tree-kill backstop for a FROZEN proxy only
CT_BLOB = 320     # 64 KiB over the ~5-20 KiB/s ring
KILL_BLOB = 420


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def ssh_step(name, remote_cmd, timeout=CT, kill_after=KILL):
    out_path = os.path.join(W28, "mark1-%s-%s-%s.out" % (RUN_ID, TAG, name))
    err_path = os.path.join(W28, "mark1-%s-%s-%s.err" % (RUN_ID, TAG, name))
    cmd = [SSH, "-i", KEY,
           "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=NUL",
           "-o", "ConnectTimeout=%d" % timeout,
           "-o", "ProxyCommand=" + PROXY,
           "-o", "LogLevel=INFO",
           "root@10.0.0.2",
           remote_cmd]
    log("step %s: firing (%d B cmd)" % (name, len(remote_cmd)))
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = p.communicate(timeout=kill_after)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       capture_output=True)
        try:
            out, err = p.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        rc = "TIMEOUT-TREEKILLED"
    out = out or b""
    err = err or b""
    with open(out_path, "wb") as f:
        f.write(out)
    with open(err_path, "wb") as f:
        f.write(err)
    text = out.decode("utf-8", "replace")
    dur = time.time() - t0
    log("step %s -> rc=%s in %.1fs (%d B stdout)" % (name, rc, dur, len(out)))
    return rc, text, err.decode("utf-8", "replace")


def fingerprint(pubs):
    lines = []
    for name, content in sorted(pubs.items()):
        tmp = os.path.join(W28, "tmp-hostkey.pub")
        with open(tmp, "w") as f:
            f.write(content.strip() + "\n")
        r = subprocess.run([SSH_KEYGEN, "-lf", tmp], capture_output=True)
        fp = (r.stdout or b"").decode("utf-8", "replace").strip()
        lines.append("%s | %s" % (name, fp or "FINGERPRINT-FAIL: %s"
                                  % (r.stderr or b"").decode("utf-8", "replace").strip()))
    os.remove(tmp)
    return lines


WRITE_CMD = (
    "echo ==RECON==; uname -a; date; "
    "ls -ld /jb /var/jb 2>/dev/null; echo --var--; ls /var/ 2>/dev/null | head -40; "
    "echo --hostkeys--; find /var /etc -maxdepth 4 -name 'ssh_host_*key.pub' 2>/dev/null; "
    "echo ==WRITE==; "
    "U=$(date -u '+%Y-%m-%dT%H:%M:%SZ'); "
    "printf 'wave28 marker S1 root\\nwritten_utc=%s\\n%s\\n' \"$U\" \"$(uname -a)\" "
    "> /var/wave28-marker-S1.txt; RC1=$?; "
    "if [ -d /var/jb ]; then printf 'wave28 marker S1 jb\\nwritten_utc=%s\\n' \"$U\" "
    "> /var/jb/wave28-marker-S1.txt; RC2=$?; else RC2=SKIP-nojb; fi; "
    "dd if=/dev/urandom of=/var/wave28-blob-S1.bin bs=1024 count=64 2>/dev/null; RC3=$?; "
    "sync; echo \"RC1=$RC1 RC2=$RC2 RC3=$RC3\"; "
    "echo ==VERIFY==; ls -la /var/wave28-marker-S1.txt /var/wave28-blob-S1.bin "
    "/var/jb/wave28-marker-S1.txt 2>/dev/null; "
    "echo --marker--; cat /var/wave28-marker-S1.txt"
)

READ_CMD = (
    "echo ==RECON2==; uname -a; date; "
    "echo --markers--; ls -la /var/wave28-marker-S1.txt /var/wave28-blob-S1.bin "
    "/var/jb/wave28-marker-S1.txt 2>/dev/null; "
    "echo ==MARKER-ROOT==; cat /var/wave28-marker-S1.txt 2>/dev/null; echo \"rc=$?\"; "
    "echo ==MARKER-JB==; cat /var/jb/wave28-marker-S1.txt 2>/dev/null; echo \"rc=$?\"; "
    "echo ==HOSTKEYS==; "
    "for f in $(find /var /etc -maxdepth 4 -name 'ssh_host_*key.pub' 2>/dev/null); do "
    "echo \"-- $f\"; cat \"$f\"; done; "
    "echo ==INVENTORY==; ls /var/ 2>/dev/null | head -40"
)


def main():
    log("mark-var-v28 mode=%s tag=%s run=%s" % (MODE, TAG, RUN_ID))
    sections = []
    blob = None

    rc, text, errt = ssh_step("recon" if MODE == "write" else "recon2",
                              WRITE_CMD if MODE == "write" else READ_CMD)
    sections.append(("[recon/%s]" % MODE, rc, text))
    if rc != 0:
        log("FATAL: recon failed -- the session is probably not live")
        return 4

    if MODE == "write":
        # blob read-back + host sha256
        rc, blob, errt = ssh_step("blob", "cat /var/wave28-blob-S1.bin",
                                  CT_BLOB, KILL_BLOB)
        if rc == 0 and len(blob) == 65536:
            sha = hashlib.sha256(blob).hexdigest()
            log("blob read back: 65536 B sha256=%s" % sha)
            sections.append(("[blob readback]", rc,
                             "bytes=%d sha256=%s" % (len(blob), sha)))
        else:
            log("WARN: blob readback rc=%s len=%s" % (rc, len(blob) if blob else 0))
            sections.append(("[blob readback]", rc, "bytes=%s FAILED" % len(blob)))
        # host key contents (the write-mode recon only listed paths)
        rc, hktext, errt = ssh_step(
            "hostkeys",
            "for f in $(find /var /etc -maxdepth 4 -name 'ssh_host_*key.pub' "
            "2>/dev/null); do echo \"-- $f\"; cat \"$f\"; done")
        sections.append(("[hostkey files]", rc, hktext))
        text = hktext
    else:
        # read mode: the session-2 blob (sha256 compared on the host)
        rc, blob, errt = ssh_step("blob", "cat /var/wave28-blob-S1.bin",
                                  CT_BLOB, KILL_BLOB)
        if rc == 0 and blob:
            sha = hashlib.sha256(blob).hexdigest()
            log("blob read: %d B sha256=%s" % (len(blob), sha))
            sections.append(("[blob read]", rc,
                             "bytes=%d sha256=%s" % (len(blob), sha)))
        else:
            log("WARN: blob read rc=%s len=%s" % (rc, len(blob) if blob else 0))
            sections.append(("[blob read]", rc, "bytes=%s FAILED/MISSING"
                             % len(blob)))

    # host keys -> local fingerprints
    pubs = {}
    cur = None
    for line in text.split("==HOSTKEYS==")[-1].splitlines():
        line = line.rstrip("\r")
        if line.startswith("-- "):
            cur = line[3:].strip()
            pubs[cur] = ""
        elif cur is not None and line.strip():
            pubs[cur] += line + "\n"
    fps = fingerprint({k: v for k, v in pubs.items() if v.strip()})
    sections.append(("[hostkey fingerprints]", 0, "\n".join(fps) or "NONE FOUND"))

    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write("wave28 /var marker package\n")
        f.write("mode: %s\ntag: %s\nrun-id: %s\nwhen: %s\n"
                % (MODE, TAG, RUN_ID, time.strftime("%Y-%m-%d %H:%M:%S")))
        if MODE == "write" and blob:
            f.write("blob sha256: %s\n" % hashlib.sha256(blob).hexdigest())
        for head, rcx, textx in sections:
            f.write("\n%s rc=%s\n%s\n" % (head, rcx, textx.strip()[:4000]))
    log("summary written: %s" % SUMMARY)
    print(open(SUMMARY, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
