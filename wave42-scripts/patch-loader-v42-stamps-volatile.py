#!/usr/bin/env python3
"""Wave 42: the LLVM 22.1.8 -O1 elimination of usb_pair_rebuild, fixed at the root.

Forensics (probe1-7, this wave): the frontend IR is complete and correct; the killer
is IPSCCP. It treats the four GEN-4 timestamp globals (usb_pair_last_progress /
usb_pair_born_at / usb_wall_last_at / usb_last_connected_at) as compile-time
constants 0 -- their only non-zero stores sit in code IPSCCP refuses to mark
executable (the recovery's own body, gutted in the same solve; with the volatile
fn-pointer the call site is an unknown callee and grants no executable edge), so
every detector guard folds into the "no recent refusal -> early return" path and
the whole body below the guards is deleted (the shipped stub: mrs CNTFRQ; mrs
CNTVCT; ret). optnone does NOT shield a function from this global-constant fold
(verified), and the volatile fn-pointer indirection does NOT either (verified).

The fix is semantic, not a fight with the pass manager: these stamps are
cross-context state -- usb_last_connected_at is written inside the pump's
Connected path (an EFI event-callback context) and all four are read from the
service-window loop -- and the file's own convention for such flags is volatile
(other_cpu_stage/other_cpu_done, the net_tx/net_rx prod/cons pairs). Declaring
them volatile says what was always true: they are machine-observed timestamps,
not solver-tracked constants. It also, mechanically, starves IPSCCP's fold.

With the root fixed, the v38g/v38h hardening is dead weight and is reverted:
- optnone on the ten hot-path USB functions (usb_rx/usb_tx/usb_wait/usb_pump ...)
  disabled optimization where the loader spends its life; it saved nothing.
- the volatile fn-pointer indirection obfuscated the call graph; saved nothing.
usb_pair_rebuild keeps noinline so the recovery stays a real, symbol-verifiable
function (outlined also keeps it out of the hot loop's icache).

usage: patch-loader-v42-stamps-volatile.py LOADER_C
"""
import re
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src


def sub(old, new, expect=1):
    n = src.count(old)
    assert n == expect, f"hunk not unique (found {n}x, want {expect}):\n{old[:200]}"
    return src.replace(old, new)


# ---- hunk A: the four stamp globals become volatile ----------------------------------------------
for name in ("usb_pair_last_progress", "usb_pair_born_at", "usb_wall_last_at",
             "usb_last_connected_at"):
    old = f"static uint64_t {name};"
    new = (f"/* Wave 42: volatile -- a cross-context stamp (the pump's Connected path and the\n"
           f" * service-window loop are different execution contexts; the file's convention for\n"
           f" * such flags is volatile). This is also what keeps LLVM 22.1.8's IPSCCP from\n"
           f" * folding the stamps to their 0 initializers and deleting the whole recovery\n"
           f" * (the -O1 elimination forensics: wave42-scripts/probe1-7). */\n"
           f"static volatile uint64_t {name};")
    src = sub(old, new)

# ---- hunk B: revert the v38h volatile fn-pointer --------------------------------------------------
src = sub(
"""/* P1-1 hardening: the recovery is called through a volatile function pointer. LLVM
 * 22.1.8 at -O1 pruned usb_pair_rebuild's single call site (inside usb_command_loop,
 * after that function was inlined into efi_main) and then the whole optnone function
 * with it -- the shipped binary carried no recovery at all. A volatile read of the
 * pointer forces an opaque, unprunable indirect call. */
static void (*volatile usb_pair_rebuild_fn)(void) = usb_pair_rebuild;

""", "")

# ---- hunk C: the direct call comes back -----------------------------------------------------------
src = sub(
"""			usb_pair_rebuild_fn();  /* Wave 38: the bounded-recovery check, through the
			                           volatile pointer (the optimizer pruned the direct call
			                           after inlining usb_command_loop into efi_main) */""",
"""			usb_pair_rebuild();     /* Wave 38: the bounded-recovery check (the -O1
			                           elimination was root-fixed at the stamp globals'
			                           volatility, wave42; the call stays direct) */""")

# ---- hunk D: the ten hot-path functions lose optnone; the recovery keeps noinline ------------------
n_attr = src.count("__attribute__((optnone, noinline)) ")
assert n_attr == 11, f"expected 11 optnone sites, found {n_attr}"
src = src.replace("__attribute__((optnone, noinline)) static void\nusb_pair_rebuild(void)",
                  "__attribute__((noinline)) static void\nusb_pair_rebuild(void)")
src = src.replace("__attribute__((optnone, noinline)) ", "")
assert "__attribute__((optnone" not in src, "optnone survived"
assert src.count("__attribute__((noinline))") == 1

assert src != orig, "nothing changed"
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"patched {path}: stamp globals volatile (4), fn-ptr reverted, direct call restored, "
      f"optnone lifted from 10 hot-path functions (rebuild keeps noinline)")
