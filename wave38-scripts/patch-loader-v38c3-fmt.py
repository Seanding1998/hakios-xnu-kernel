#!/usr/bin/env python3
"""Wave 38 generation 2, fix round 2: wall_fmt_agg's copy loops incremented the source
pointer twice (loop body + for-increment), dropping every other byte -- the aggregate
lines were garbled. The isolation harness caught it (the displayed aggregate did not
contain the family name).

usage: patch-loader-v38c3-fmt.py LOADER_C
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src
bad = "out[n++] = *p++;"
n_bad = src.count(bad)
assert n_bad == 5, f"expected the 5 formatter loops, found {n_bad}"
src = src.replace("for (p = pre; *p != 0 && n < cap - 1; p++) {\n\t\tout[n++] = *p++;\n\t}",
                  "for (p = pre; *p != 0 && n < cap - 1; p++) {\n\t\tout[n++] = *p;\n\t}")
src = src.replace("for (p = wall_family_name[family]; *p != 0 && n < cap - 1; p++) {\n\t\tout[n++] = *p++;\n\t}",
                  "for (p = wall_family_name[family]; *p != 0 && n < cap - 1; p++) {\n\t\tout[n++] = *p;\n\t}")
for mid in (': x', ' suppressed here, x', ' since the family\'s first\\n'):
    old = f'for (p = "{mid}"; *p != 0 && n < cap - 1; p++) {{\n\t\tout[n++] = *p++;\n\t}}'
    new = f'for (p = "{mid}"; *p != 0 && n < cap - 1; p++) {{\n\t\tout[n++] = *p;\n\t}}'
    assert src.count(old) == 1, f"formatter loop not found: {mid!r}"
    src = src.replace(old, new)
assert src != orig and src.count(bad) == 0
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: the formatter's double increment removed (5 loops)")
