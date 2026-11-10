#!/usr/bin/env python3
"""Retry-connect and poll getvar continuously for up to 25 minutes; a serving window is caught."""
import sys, time, argparse, importlib.util, subprocess

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

W = "<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts"
lt = load("w13talk", W + "/../wave13-scripts/loader_talk.py")
w21 = load("w21talk", W + "/loader_talk.py")

lib = lt.Libusb("/usr/lib64/libusb-1.0.so.0")
ns = argparse.Namespace(vid=None, pid=None, iface=None)
print("polling for a serving window, up to 25 min", flush=True)
end = time.time() + 1500
n = answered = 0
while time.time() < end:
    try:
        sess = w21.connect(lib, ns)
    except lt.DeviceError:
        subprocess.run(["usbipd", "attach", "--wsl", "--busid", "2-2"],
                       capture_output=True)
        time.sleep(10)
        continue
    print("connected at %s" % time.strftime("%H:%M:%S"), flush=True)
    stop = time.time() + 120
    while time.time() < stop and time.time() < end:
        try:
            resp = lt.transact(lib, sess, "getvar:result", 2500, quiet=True)
        except lt.DeviceError as e:
            print("device error at %s: %s" % (time.strftime("%H:%M:%S"), e), flush=True)
            break
        n += 1
        if resp is not None and resp.status == "OKAY":
            answered += 1
            print("SERVING: %r (poll %d at %s)" % (resp.payload, n, time.strftime("%H:%M:%S")), flush=True)
            if resp.payload and b"idle" in resp.payload:
                # a serving idle loader: start a session now and keep serving it
                print("idle: oem run", flush=True)
                lt.transact(lib, sess, "oem run", 30000, quiet=True)
                print("session started; serving it (getvar every 2 s)", flush=True)
        if n % 15 == 0:
            print("poll %d, answered %d" % (n, answered), flush=True)
        time.sleep(1.2)
    try:
        lt.disconnect(lib, sess)
    except Exception:
        pass
print("done: polls %d, answered %d" % (n, answered), flush=True)
