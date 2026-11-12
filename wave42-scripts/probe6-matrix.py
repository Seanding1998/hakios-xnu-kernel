#!/usr/bin/env python3
"""Wave 42 probe 6: the fix experiment matrix at -O1.
V1 = current minus hardening (direct call, no optnone) -- the 95f1f555 shape.
V2 = current + volatile on the four GEN-4 stamp globals (keeps fn-ptr + optnone).
V3 = V2 + direct call (drop the fn-pointer indirection), no optnone.
Each variant compiles at -O1 with the ship flags; report obj sha, string survival,
and the usb_pair_rebuild symbol table entry."""
import hashlib
import re
import subprocess
import sys

SRC = "/home/cyrux/hakios/kernel/xnuloader/loader.c"
OUT = "/tmp/w42"
FLAGS = ["clang", "--target=aarch64-unknown-windows", "-ffreestanding", "-fno-builtin",
         "-fno-stack-protector", "-fshort-wchar", "-mgeneral-regs-only", "-O1", "-w",
         "-DPAYLOAD_BASE=0xF4000000ULL", "-I/home/cyrux/hakios/kernel/xnuloader", "-c"]

NEEDLES = [
    b"the pair reads dead in this generation",
    b"bounded recovery %d of 2",
    b"the recovery's bring-up is back",
    b"the recovery's bring-up did not come back",
    b"the IN gate is up",
    b"the service window is over",
]


def strip_hardening(src):
    # -g: remove the optnone/noinline attributes
    src = src.replace("__attribute__((optnone, noinline)) ", "")
    # -h: call directly and remove the volatile fn-pointer definition block
    src = src.replace("usb_pair_rebuild_fn();", "usb_pair_rebuild();")
    src = re.sub(
        r"/\* P1-1 hardening: the recovery is called through a volatile function pointer.*?"
        r"static void \(\*volatile usb_pair_rebuild_fn\)\(void\) = usb_pair_rebuild;\n",
        "", src, flags=re.S)
    assert "usb_pair_rebuild_fn" not in src, "fn-ptr still referenced"
    assert "__attribute__((optnone" not in src
    return src


def add_volatile_stamps(src):
    pairs = [
        ("static uint64_t usb_pair_last_progress;", "static volatile uint64_t usb_pair_last_progress;"),
        ("static uint64_t usb_pair_born_at;", "static volatile uint64_t usb_pair_born_at;"),
        ("static uint64_t usb_wall_last_at;", "static volatile uint64_t usb_wall_last_at;"),
        ("static uint64_t usb_last_connected_at;", "static volatile uint64_t usb_last_connected_at;"),
    ]
    for old, new in pairs:
        n = src.count(old)
        assert n >= 1, f"decl not found: {old}"
        src = src.replace(old, new)
        print(f"    volatile'd: {old} ({n} site(s))")
    return src


def build(tag, src):
    cpath = f"{OUT}/{tag}.c"
    opath = f"{OUT}/{tag}.obj"
    open(cpath, "w", encoding="utf-8", newline="").write(src)
    r = subprocess.run(FLAGS + [cpath, "-o", opath], capture_output=True, text=True)
    print(f"== {tag}: rc={r.returncode} stderr={len(r.stderr)}B")
    if r.returncode != 0:
        print(r.stderr[:1500])
        return False
    data = open(opath, "rb").read()
    print("   obj sha " + hashlib.sha256(data).hexdigest()[:8], len(data), "B")
    for s in NEEDLES:
        print(f"   {data.count(s)}x  {s[:46]!r}")
    st = subprocess.run(["llvm-objdump", "-t", opath], capture_output=True, text=True).stdout
    for ln in st.splitlines():
        if "usb_pair_rebuild" in ln and "fn" not in ln:
            print("   SYM:", ln.strip())
    return True


base = open(SRC, encoding="utf-8").read()
n_stamps = len(re.findall(r"static uint64_t usb_pair_last_progress;", base))
print(f"base source: stamp-global decls found {n_stamps}x")

v1 = strip_hardening(base)
print("V1 = -optnone -volatile-fnptr (direct call):")
build("v1", v1)

v2 = add_volatile_stamps(base)
print("V2 = +volatile stamp globals (keeps fn-ptr + optnone):")
build("v2", v2)

v3 = add_volatile_stamps(strip_hardening(base))
print("V3 = volatile stamps + direct call, no optnone:")
build("v3", v3)
