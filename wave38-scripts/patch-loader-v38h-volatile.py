#!/usr/bin/env python3
"""Wave 38 fix generation 4, hardening 2: LLVM 22.1.8 at -O1 (with usb_command_loop
inlined into efi_main) pruned the single call site of usb_pair_rebuild and then the
whole (optnone!) function with it -- the shipped binary had no recovery at all, while
every other fix string survived. The bulletproof shape: the service window's loop
calls the recovery through a volatile function pointer -- LLVM must load the pointer
and call whatever it names; the target (its address taken, reached through a volatile
read) can be neither pruned nor folded.

usage: patch-loader-v38h-volatile.py LOADER_C
"""
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

def sub(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"hunk not unique (found {n}x):\n{old[:200]}"
    src = src.replace(old, new)

# ---- hunk 1: the volatile pointer, defined right after the recovery's definition -------------
sub(
"""	print("usb: the recovery's bring-up is back: the gadget is presented again -- the pair still needs the host's SET_CONFIG before any of this is called recovered\\n");
}
""",
"""	print("usb: the recovery's bring-up is back: the gadget is presented again -- the pair still needs the host's SET_CONFIG before any of this is called recovered\\n");
}

/* P1-1 hardening: the recovery is called through a volatile function pointer. LLVM
 * 22.1.8 at -O1 pruned usb_pair_rebuild's single call site (inside usb_command_loop,
 * after that function was inlined into efi_main) and then the whole optnone function
 * with it -- the shipped binary carried no recovery at all. A volatile read of the
 * pointer forces an opaque, unprunable indirect call. */
static void (*volatile usb_pair_rebuild_fn)(void) = usb_pair_rebuild;
""")

# ---- hunk 2: the loop calls through the pointer ------------------------------------------------
sub(
"""			usb_pair_rebuild();     /* Wave 38: the bounded-recovery check */
			usb_wait_pumped(NULL, 50);   /* a quiet, pumped second before the next pass --""",
"""			usb_pair_rebuild_fn();  /* Wave 38: the bounded-recovery check, through the
			                           volatile pointer (the optimizer pruned the direct call
			                           after inlining usb_command_loop into efi_main) */
			usb_wait_pumped(NULL, 50);   /* a quiet, pumped second before the next pass --""")

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: volatile-pointer indirection applied (2 hunks)")
