#!/usr/bin/env python3
"""Wave 7b unit evidence: simulate loader.c write_logs/compose_logs/reboot's flush
against a fake logdump, OLD (pre-fix) vs NEW (post-fix) flow.

Timeline mirrors Boot #8 on PHK110: banner prints -> pre-run flush -> 20 s kernel
run (its log in a mailbox, loader prints nothing to the partition) -> clean return
-> "kernel returned: log at ..., 717 bytes" -> write_logs(klog, 717) -> efi_main
falls into reboot() -> hc_take_back + flush_log() -> cold reset. What must be in
logdump afterwards is the loader log FOLLOWED BY the kernel log (compose_logs'
own contract: "the kernel log of the last run").
"""
SEP, END = b"\n== KERNEL LOG ==\n", b"\n== END OF LOG ==\n"


class Loader:
    def __init__(self, fixed):
        self.log_buf = b""          # loader's own log (print appends here)
        self.logdump = bytearray(512 * 1024 * 1024 // 8)  # partition (shrunk: only LBA region used)
        self.run_klog = None        # NEW-flow only: last run's kernel log, kept
        self.run_klog_len = 0
        self.fixed = fixed

    def print(self, s): self.log_buf += s.encode()

    def compose(self, klog, klog_len):
        out = bytearray(self.log_buf)
        if klog is not None:                      # C adds the section even for klog_len == 0
            out += SEP + klog[:klog_len] + END
        n = len(out)
        return bytes(out), n

    def write_logs(self, klog, klog_len):        # bio != NULL (phone); hc guard passes
        if self.fixed:
            if klog is not None and klog_len != 0:
                self.run_klog, self.run_klog_len = klog, klog_len
            elif klog is None and self.run_klog is not None:
                klog, klog_len = self.run_klog, self.run_klog_len
        out, n = self.compose(klog, klog_len)
        ln = (n + 1 + 4095) // 4096 * 4096
        # compose_logs memset()s the whole out_buf first: the write overwrites [0, ln) with zeros past n
        self.logdump[:ln] = out.ljust(ln, b"\0")

    def reboot(self):
        self.write_logs(None, 0)                  # reboot(): flush_log() then cold reset


def run(fixed):
    l = Loader(fixed)
    l.print("== XNULOADER v3 ==\nplatform phk110\njumping to 8434194a8\n")
    l.write_logs(None, 0)                         # pre-run flush_log() (loader-only)
    klog = b"xnu on phk110: MIDR=410fd463 ... 717 bytes of kernel log ...\n"
    l.print("kernel returned: log at 843ae89c0, 717 bytes\n")
    l.write_logs(klog, len(klog))                 # run_kernel's post-return write
    l.reboot()                                    # efi_main -> reboot() -> flush_log()
    return bytes(l.logdump)


old, new = run(False), run(True)
assert b"== KERNEL LOG ==" not in old, "old flow unexpectedly kept klog"
assert new == run(True), "new flow nondeterministic"
assert new.startswith(old.rstrip(b"\0")), "loader log not at the front of the new block"
assert new[len(old.rstrip(b"\0")):].startswith(SEP + b"xnu on phk110"), "klog not appended after loader log"
print("OLD flow logdump (Boot #8):  kernel log section present:", b"== KERNEL LOG ==" in old)
print("NEW flow logdump:            kernel log section present:", b"== KERNEL LOG ==" in new)
i = new.index(b"== KERNEL LOG ==")
print("NEW block: loader log %d B | %r | klog %d B | %r" % (
    new.index(SEP), new[new.index(SEP) - 20:new.index(SEP)],
    new.index(END) - i - len(SEP), new[new.index(END):new.index(END) + len(END)]))
# zero-klog / no-run regressions: identical to the old flow
z = Loader(True); z.print("banner\n"); z.write_logs(None, 0); z.reboot()
o = Loader(False); o.print("banner\n"); o.write_logs(None, 0); o.reboot()
assert z.logdump == o.logdump, "no-run flush changed"
print("no-run flush: new flow byte-identical to old flow:", z.logdump == o.logdump)
z2 = Loader(True); z2.print("banner\n"); z2.write_logs(b"k", 0); z2.reboot()
o2 = Loader(False); o2.print("banner\n"); o2.write_logs(b"k", 0); o2.reboot()
assert z2.logdump == o2.logdump, "zero-length klog flush changed"
print("zero-length klog: new flow byte-identical to old flow:", z2.logdump == o2.logdump)
print("SIMULATION PASS")
