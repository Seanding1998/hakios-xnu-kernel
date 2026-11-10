#!/usr/bin/env python3
"""Wave 26: pull `oem log` through tunnel25w's fresh-session opener (the H3
stale-devnode discipline: try every 18d1:d00d node, keep the live one).

usage: python pull-log-v26.py OUT_FILE
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "wave25-scripts"))
import importlib.util
spec = importlib.util.spec_from_file_location("t25w", os.path.join(REPO, "wave25-scripts", "tunnel25w.py"))
t25w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t25w)

import loader_talk as lt13  # noqa: E402


def main():
    out = sys.argv[1]
    lib = lt13.Libusb()
    sess = t25w.open_fresh_session(lib)
    if sess is None:
        print("no live d00d session on the bus")
        return 1
    pipe = t25w.Pipe25(lib, sess)
    try:
        # Pipe25's discipline: every DATA reply is followed by a standalone OKAY
        # that must be drained, or the loader wedges on its next send.
        pipe.command("oem log", 8000)
        up = pipe.command("upload", 15000)
        if up.status != "DATA" or up.payload is None:
            print("unexpected upload reply: %r raw=%r" % (up.status if up else None,
                                                          (up.raw or b"")[:120] if up else b""))
            return 2
        with open(out, "wb") as f:
            f.write(up.payload)
        print("saved %d bytes -> %s" % (len(up.payload), out))
        return 0
    finally:
        try:
            lt13.disconnect(lib, sess)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
