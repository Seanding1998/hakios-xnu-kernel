#!/usr/bin/env python3
"""Wave 42: offline stub test of the upgraded gltest runner's classifier (wave41 s6).
No device, no ssh -- pure classify() checks against synthetic gl_test outputs."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "gltest_run_v38", os.path.join(HERE, "..", "wave38-scripts", "gltest-run-v38.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CASES = [
    # (name, out, rc, expected-state)
    ("hw-DONE", "gl_test: renderer=FD725\nRENDER_PASS backend=hw\nREADBACK_PASS samples 5/5 coverage 26%\nPRESENT_CALL_OK\nGL_RC=0", 0,
     "hardware-DONE"),
    ("rc=0 but softpipe -> software-comparison, NOT done", "gl_test: renderer=softpipe\nRENDER_PASS backend=sw\nREADBACK_PASS samples 5/5 coverage 26%\nPRESENT_CALL_OK\nGL_RC=0", 0,
     "software-comparison"),
    ("branch C: no context is NOT a pass", "gl_test: no OpenGL ES context\nGL_RC=1", 1, "branch-C"),
    ("present fail rc=3", "gl_test: context ok, drawn\nPRESENT_CALL_FAIL\nGL_RC=3", 3, "present-fail"),
    ("no-context token 'gl_test:' alone never completes", "gl_test: drew nothing\nGL_RC=2", 2, "remote-fail"),
    ("pixel fail on hw context -> branch E territory", "RENDER_PASS backend=hw\nREADBACK_FAIL samples 1/5 coverage 3%\nPRESENT_CALL_OK\nGL_RC=2", 2, "remote-fail"),
    ("v35 old carrier: rc=0, printf-only output -> diagnostic only", "gl_test: drew the triangle in 0.4s\nGL_RC=0", 0, "unstructured-rc0"),
    ("connect phase: nothing at all", "", 255, "no-session"),
    ("remote cmd killed mid-draw (branch D territory)", "gl_test: context ok\npartial", -9, "no-session"),
]

fails = 0
for name, out, rc, want in CASES:
    state, detail = mod.classify(out, rc)
    ok = state == want
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'} {name} -> {state} ({detail[:60]})")
print(f"== {len(CASES) - fails} passed, {fails} failed ==")
sys.exit(1 if fails else 0)
