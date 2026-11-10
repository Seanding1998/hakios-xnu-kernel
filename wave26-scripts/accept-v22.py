#!/usr/bin/env python3
"""Wave 26: the v22 acceptance sampler (single owner).

The vnode fix's verdict: a session whose poll heartbeat ("en0 <n>") keeps
climbing past kernel age ~300 s (where every v20/v21 session was wedged), with
held/lost quiet. One generation, sampled from the loader phase through the
kernel session; every sample also drains one upload so the pipe stays clean.

usage: python accept-v22.py [SAMPLE_SECONDS]
"""
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave25-scripts"))
import importlib.util
_spec = importlib.util.spec_from_file_location("t25w", os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))
t25w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t25w)

import loader_talk as lt13  # noqa: E402

RUN_SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 660.0
LOG = os.path.join(REPO, "wave26-scripts", "accept-v22.log")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main():
    lib = lt13.Libusb()
    log("acceptance: watching generations for %.0f s (the v21 wedge was at ~220 s)" % RUN_SECONDS)
    deadline = time.time() + RUN_SECONDS + 600.0
    while time.time() < deadline:
        sess = t25w.open_fresh_session(lib)
        if sess is None:
            time.sleep(5)
            continue
        pipe = t25w.Pipe25(lib, sess)
        try:
            probe = pipe.command("oem recording", 2500)
            raw = (probe.raw or b"") + (probe.payload or b"")
            if b"kernel is running" not in raw:
                log("loader phase (%r); exiting without a teardown (the disconnect path "
                    "faults when the loader reboots under it -- wave25's 0xC0000 ruling); "
                    "the relauncher owns the loop" % raw[:40])
                return 5
            log("kernel session live; sampling the heartbeat")
            t0 = time.time()
            beats = []
            samples = 0
            last_log_lines = []
            while time.time() - t0 < RUN_SECONDS:
                try:
                    ns_text = pipe.command("oem netstat", 2500).raw.decode("utf-8", "replace")
                    f = ns_text.split()
                    tx, rx, held, en0 = int(f[1]), int(f[5]), (int(f[9]), int(f[10])), int(f[12])
                    samples += 1
                    beats.append(en0)
                    frozen = len(beats) >= 2 and beats[-1] == beats[-2] and (held[1] or f[7] != "0")
                    log("age %5.0fs: tx %d rx %d held %s en0 %d %s"
                        % (time.time() - t0, tx, rx, held, en0, "FROZEN" if frozen else ""))
                    if frozen:
                        log("VERDICT: the heartbeat froze at age %.0f s -- the vnode fix did not hold" % (time.time() - t0))
                        return 4
                    if samples % 2 == 0:
                        # the kernel's own log (the loader composes it live): the state
                        # of the kernel at THIS moment, not a guess from the USB layer
                        try:
                            pipe.command("oem log", 8000)
                            up = pipe.command("upload", 15000)
                            if up.status == "DATA" and up.payload:
                                text = up.payload.decode("utf-8", "replace")
                                klines = [l for l in text.strip().splitlines()
                                          if re.match(r"^\[\s*\d+\.\d+\]:", l)]
                                last_log_lines = klines[-3:]
                                log("  kernel log tail: %s" % " || ".join(
                                    l[:80] for l in last_log_lines))
                        except lt13.DeviceError as e:
                            log("  log pull failed: %s" % e)
                    time.sleep(25)
                except lt13.DeviceError as e:
                    log("device error at age %.0fs: %s" % (time.time() - t0, e))
                    break
            log("VERDICT: the heartbeat lived %d samples to age %.0f s (last en0 %d) -- past the wedge point"
                % (samples, time.time() - t0, beats[-1] if beats else -1))
            return 0
        except lt13.DeviceError as e:
            log("probe error: %s" % e)
            time.sleep(10)
        finally:
            try:
                lt13.disconnect(lib, sess)
            except Exception:
                pass
    log("no kernel session within the deadline")
    return 5


if __name__ == "__main__":
    sys.exit(main())
