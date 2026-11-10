#!/usr/bin/env python3
"""mk-ath11k.py -- PHK110 (SM8475 / WCN6750-qca6490 via PCIe+MHI) fixed-source driver pipeline.

Modeled on the proven pipeline of the raphael fork (HeliumStudio-Dev/hackios-xnu-kernel,
raphael-bringup branch): tools/mk-ath10k.py (SHA256-locked sources -> host-side .o -> XNU link)
and tools/mk-ath11k.sh (upstream's earlier ath11k shell pipeline, staged bring-up with
auto-generated stubs).  Wave 30 scope: pipeline READY (fetch / verify / plan); the compile step
is gated until the kernel-side lx layer (bsd/sys/hakios.lx.h equivalent) exists in our tree.

Sources locked by SHA256 (same archives as the fork's two pipelines, evidence:
fork tools/mk-ath10k.py SOURCES{} and tools/mk-ath11k.sh VERSION=/SHA256=):
  linux-7.0.14.tar.xz        cdn.kernel.org      ath11k lives in drivers/net/wireless/ath/ath11k
  freebsd-15.1-src.txz       download.freebsd.org LinuxKPI headers the driver compiles against
  wpa_supplicant-2.11.tar.gz w1.fi               SAE host regression (later wave, not this one)
  mbedtls-3.6.7.tar.bz2      github Mbed-TLS     SAE crypto backend (later wave, not this one)

Usage:
  python3 mk-ath11k.py                # = --dry-run: plan everything, touch nothing, exit 0
  python3 mk-ath11k.py --fetch        # download + SHA256-verify archives into cache
  python3 mk-ath11k.py --verify       # fetch-if-needed + extract + per-file licence gate + emit commands
  python3 mk-ath11k.py --build        # refused in wave 30: needs our kernel's hakios.lx.h (see --build)

Exit codes: 0 = PASS (or SKIP-only), 1 = FAIL.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRATCH = HERE / "upstream-scratch"
CACHE = SCRATCH / "cache"
BUILD = SCRATCH / "build-ath11k"

# ---------------------------------------------------------------- locked sources
SOURCES = {
    "linux": (
        "linux-7.0.14.tar.xz",
        "https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.0.14.tar.xz",
        "de9999b784d2293f00d39c62d8f92a08ab8a54bc4e80ffd250a0c09cb07a0f98",
    ),
    "freebsd": (
        "freebsd-15.1-src.txz",
        "https://download.freebsd.org/releases/amd64/15.1-RELEASE/src.txz",
        "cf5762da53fd52e1eaf0f9ceee9bf58cbe314c821031d0d9ffa76823185a89e1",
    ),
    "hostap": (
        "wpa_supplicant-2.11.tar.gz",
        "https://w1.fi/releases/wpa_supplicant-2.11.tar.gz",
        "912ea06f74e30a8e36fbb68064d6cdff218d8d591db0fc5d75dee6c81ac7fc0a",
    ),
    "mbedtls": (
        "mbedtls-3.6.7.tar.bz2",
        "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2",
        "a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6",
    ),
}
# hostap/mbedtls are only needed by the later SAE wave; fetch on demand.
FETCH_DEFAULT = ("linux", "freebsd")

# ---------------------------------------------------------------- ath11k file set
# Upstream Makefile (torvalds/linux master, drivers/net/wireless/ath/ath11k/Makefile,
# fetched 2026-11-10): core module 20 files + separate ath11k_pci module = mhi.o + pci.o.
# The fork's redwood pipeline (tools/mk-ath11k.sh DRIVER list) builds 19 files and omits
# pcic/mhi/pci/debug -- its bus is replaced by wifi/lx/src/lx_bus.c (AHB-like WCN6750 on
# SM7325).  PHK110 is qca6490 on PCIe0 -> we need the PCI trio + the core 19.
ATH11K_CORE = [
    "core", "hal", "hal_tx", "hal_rx", "wmi", "mac", "reg", "htc", "qmi",
    "dp", "dp_tx", "dp_rx", "debug", "ce", "peer", "dbring", "hw", "pcic",
    "fw", "p2p",
]
ATH11K_PCI_MODULE = ["mhi", "pci"]          # ath11k_pci.o on upstream
ATH11K_EXTRA_HEADERS = ["spectral_common.h"]  # ath/ level headers ath11k includes
# Fork's list, for the record (diff vs ours = +debug, +pcic, +mhi, +pci):
FORK_DRIVER_LIST = [
    "core", "hal", "qmi", "ce", "hw", "fw", "htc", "wmi", "mac", "reg",
    "peer", "dp", "dp_rx", "dp_tx", "hal_rx", "hal_tx", "dbring", "p2p",
]
# Later-wave optional files (debugfs/testmode/trace/thermal/spectral/wow/coredump/cfr):
ATH11K_LATER = ["debugfs", "testmode", "trace", "thermal", "spectral", "wow", "coredump", "cfr"]

# Licence gate, copied from fork tools/mk-ath11k.sh: every extracted ath11k file must carry
# BSD-3-Clause-Clear SPDX or the ISC permission text; anything else fails the build.
LICENCE_OK_MARKERS = (
    "SPDX-License-Identifier: BSD-3-Clause-Clear",
    "Permission to use, copy, modify, and/or distribute this software",  # ISC, spelled out
)
# Known GPL boundary: drivers/bus/mhi (the MHI host stack ath11k/mhi.c drives) is GPL-2.0-only.
# It is NOT extracted by default.  See wave30 design doc section 2.3.
MHI_GPL_NOTE = (
    "drivers/bus/mhi/host/*.c are GPL-2.0-only -- excluded from extraction by licence gate. "
    "MHI protocol must be re-implemented inside wifi/lx (like the fork's lx_bus.c did for "
    "WCN6750 AH B probe) or the licence gate must be consciously relaxed by a future wave."
)

# FreeBSD source parts LinuxKPI compiles against (fork tools/mk-ath10k.py parts list, verbatim).
FREEBSD_PARTS = (
    "compat/linuxkpi sys arm64/include net net80211 netinet netinet6 vm kern tools libkern ddb "
    "security fs/pseudofs crypto opencrypto geom bsm isa cam rpc xdr x86/include ofed/include "
    "dev/pci dev/ofw dev/fdt dev/acpica dev/usb dev/iicbus dev/backlight "
    "contrib/ck/include contrib/dev/acpica/include contrib/libnv"
).split()

# Kernel-side contract (checked at --build time, not this wave):
KERNEL_LX_HEADER = "bsd/sys/hakios.lx.h"     # the one ABI both sides compile against
KERNEL_TREE_ENV = "HAKIOS_KERNEL_SRC"        # env var; our WSL tree default below
KERNEL_TREE_DEFAULT = "~/hakios/kernel"

# Exported entry points into XNU (fork out/exported.txt, verbatim).
EXPORTED_SYMBOLS = ["_lx_prepare", "_lx_start", "_lx_stop", "_lx_transmit"]
# libc names XNU provides under the same name (fork KERNEL list, verbatim).
XNU_LIBC = [
    "memcmp", "memcpy", "memmove", "memset", "strcmp", "strncmp", "strlen", "strchr",
    "strrchr", "strlcpy", "strlcat", "bzero", "snprintf", "vsnprintf",
    "__stack_chk_fail", "__stack_chk_guard",
]

# Compile flags: fork tools/mk-ath10k.py flags with CONFIG_ATH11K_PCI swapped in
# (fork used CONFIG_ATH11K_AHB for redwood's WCN6750 path).
def compile_flags(kernel_src: str) -> list:
    return [
        "-target", "arm64-apple-ios16.5", "-mkernel", "-mgeneral-regs-only",
        "-fno-builtin", "-fno-common", "-ffreestanding", "-fno-strict-aliasing",
        "-funsigned-char", "-nostdinc", "-std=gnu17", "-O2", "-g", "-w",
        "-D__FreeBSD__=15", "-D_KERNEL", "-DKLD_MODULE", "-DHAVE_KERNEL_OPTION_HEADERS",
        "-DLINUXKPI_VERSION=70000",
        "-DCONFIG_ATH11K_PCI", "-DCONFIG_ATH11K_DEBUG",
        f"-DLX_HAKIOS_LX_H=\"{kernel_src}/{KERNEL_LX_HEADER}\"",
        '-DKBUILD_MODNAME="ath11k"',
    ]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(name: str) -> Path:
    filename, url, sha = SOURCES[name]
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / filename
    if dest.exists() and sha256_of(dest) == sha:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".partial")
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "hakios-phk110-wave30"})
    print(f"  fetch {url}")
    with opener.open(req, timeout=180) as r, tmp.open("wb") as out:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    got = sha256_of(tmp)
    if got != sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {filename}: want {sha} got {got}")
    tmp.replace(dest)
    return dest


def archive_state(name: str) -> str:
    filename, _url, sha = SOURCES[name]
    p = CACHE / filename
    if not p.exists():
        return "ABSENT"
    return "OK" if sha256_of(p) == sha else "BAD-SHA"


def tool_available(tool: str) -> bool:
    from shutil import which
    return which(tool) is not None


# ---------------------------------------------------------------- plan / verdict
def plan(kernel_src: str | None) -> dict:
    files = ATH11K_CORE + ATH11K_PCI_MODULE
    return {
        "phases": [
            {"id": "fetch", "desc": "download archives to cache, enforce SHA256",
             "archives": {n: SOURCES[n][0] for n in FETCH_DEFAULT}},
            {"id": "extract-linux", "desc": "extract ath11k/ from linux tarball (strip 5), per-file licence gate",
             "note": "strip 5 as fork tools/mk-ath10k.py does"},
            {"id": "extract-freebsd", "desc": "extract LinuxKPI-relevant sys trees (strip 2)"},
            {"id": "gen-headers", "desc": "makeobjops.awk x10 + vnode_if.awk hpq + empty opt_*.h + opt_global/opt_inet"},
            {"id": "compile", "desc": "clang arm64-apple-ios16.5 kernel objects, MMD depfiles, per-object .err capture",
             "files": files, "count": len(files),
             "skipped_this_wave": "needs kernel-side bsd/sys/hakios.lx.h + wifi/lx port (v0.6 waves)"},
            {"id": "link", "desc": "ld64 -r -> all.o; undefined-symbol gate; auto-stub ath11k_* ; exported_symbols_list -> ath11k.o"},
        ],
        "ath11k_files": files,
        "ath11k_fork_diff": sorted(set(files) - set(FORK_DRIVER_LIST)),
        "ath11k_later": ATH11K_LATER,
        "mhi_gpl": MHI_GPL_NOTE,
        "exported": EXPORTED_SYMBOLS,
        "kernel_tree": kernel_src or "(unset -- compile phase will refuse)",
        "cache": str(CACHE),
    }


def cmd_dry_run(args) -> int:
    kernel_src = os.environ.get(KERNEL_TREE_ENV) or (Path(os.path.expanduser(KERNEL_TREE_DEFAULT)) if Path(os.path.expanduser(KERNEL_TREE_DEFAULT)).exists() else None)
    p = plan(kernel_src)
    print("== mk-ath11k dry-run (plan only, nothing fetched, nothing built) ==")
    print(f"cache dir   : {CACHE}")
    for n in FETCH_DEFAULT:
        print(f"archive {n:8s}: {archive_state(n):8s} {SOURCES[n][0]}")
    tools = ["curl", "tar", "patch", "awk", "clang", "llvm-nm", "ld64"]
    print("host tools  : " + " ".join(f"{t}={'yes' if tool_available(t) else 'no'}" for t in tools))
    print(f"ath11k files: {len(p['ath11k_files'])} core+pci "
          f"(fork diff: +{','.join(p['ath11k_fork_diff'])})")
    print(f"kernel tree : {p['kernel_tree']}")
    print("MHI/GPL     : " + MHI_GPL_NOTE[:80] + "...")
    print("VERDICT: PASS (dry-run plan emitted; see design doc section 2)")
    return 0


def cmd_fetch(args) -> int:
    ok = True
    for n in (FETCH_DEFAULT if not args.all else SOURCES.keys()):
        try:
            p = download(n)
            print(f"PASS {n}: {p} ({p.stat().st_size} bytes)")
        except Exception as e:  # noqa: BLE001 -- report and continue
            print(f"FAIL {n}: {e}")
            ok = False
    return 0 if ok else 1


def cmd_verify(args) -> int:
    """Fetch (if needed) + extract ath11k subset + licence gate + emit compile plan."""
    errors = []
    for n in FETCH_DEFAULT:
        try:
            download(n)
        except Exception as e:  # noqa: BLE001
            errors.append(f"fetch {n}: {e}")
            continue
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        return 1

    linux_tar = CACHE / SOURCES["linux"][0]
    want = [f"drivers/net/wireless/ath/ath11k/{f}.c" for f in ATH11K_CORE + ATH11K_PCI_MODULE]
    want += [f"drivers/net/wireless/ath/ath11k/{f}.h" for f in ATH11K_CORE + ATH11K_PCI_MODULE]
    want += [f"drivers/net/wireless/ath/{h}" for h in ATH11K_EXTRA_HEADERS]

    # NOTE: extraction below runs from scratch dir; scratch is gitignored, never committed.
    out = BUILD / "linux-7.0.14"
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["tar", "-xf", str(linux_tar), "-C", str(out), "--strip-components=5"] + \
          [f"linux-7.0.14/{w}" for w in want]
    print(f"extract -> {out}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(f"FAIL tar: {r.stderr[:400]}")
        return 1

    bad_licence = []
    for c in sorted(out.rglob("ath11k/*.c")) + sorted(out.rglob("ath11k/*.h")):
        head = "\n".join(c.read_text(errors="replace").splitlines()[:6])
        if not any(m in head for m in LICENCE_OK_MARKERS):
            bad_licence.append(str(c))
    if bad_licence:
        print("FAIL licence gate (fork mk-ath11k.sh rule):")
        for f in bad_licence:
            print(f"  {f}")
        return 1
    print(f"PASS licence gate: {len(ATH11K_CORE + ATH11K_PCI_MODULE)} files carry "
          f"BSD-3-Clause-Clear/ISC")

    flags = compile_flags(kernel_src_placeholder())
    cmds = {
        "extract_freebsd": ["tar", "-xf", str(CACHE / SOURCES["freebsd"][0]), "-C", "<freebsd-out>",
                            "--strip-components=2", "usr/src/COPYRIGHT",
                            *[f"usr/src/sys/{p}" for p in FREEBSD_PARTS]],
        "compile_each": ["clang", *flags, "-MMD", "-MF", "<obj>.d", "-c", "<src>", "-o", "<obj>"],
        "link": ["<root>/xnu-deps/host/bin/ld64", "-r", "-arch", "arm64", "<objs...>",
                 "-o", "out/all.o"],
        "export": EXPORTED_SYMBOLS,
    }
    (BUILD / "compile-plan.json").write_text(json.dumps(cmds, indent=2))
    print(f"PASS compile plan emitted -> {BUILD / 'compile-plan.json'}")
    print("VERDICT: PASS (pipeline ready; compile gated on kernel hakios.lx.h, wave 30 scope ends here)")
    return 0


def kernel_src_placeholder() -> str:
    env = os.environ.get(KERNEL_TREE_ENV)
    return env if env else str(Path(os.path.expanduser(KERNEL_TREE_DEFAULT)))


def cmd_build(args) -> int:
    print("REFUSED: wave 30 scope is pipeline-ready only (task brief).")
    print("The compile+link step needs, and will refuse until present:")
    print(f"  1. our kernel tree with {KERNEL_LX_HEADER} (env {KERNEL_TREE_ENV}, "
          f"default {KERNEL_TREE_DEFAULT})")
    print("  2. wifi/lx port with the lx_os_* implementation (fork: wifi/lx/src/*.c + "
          "xnu/files/bsd/dev/hakios.lx.c)")
    print("  3. xnu-deps/host/bin/ld64 + nm host tools")
    print("Run --verify to bring the source side to ready state.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="PHK110 ath11k (qca6490 PCIe+MHI) fixed-source pipeline -- wave 30 skeleton")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="print plan only (default)")
    g.add_argument("--fetch", action="store_true", help="download + SHA256-verify archives")
    g.add_argument("--all", action="store_true", help="with --fetch: also hostap/mbedtls (SAE wave)")
    g.add_argument("--verify", action="store_true",
                   help="fetch + extract + licence gate + emit compile-plan.json")
    g.add_argument("--build", action="store_true", help="compile+link (refused this wave)")
    args = ap.parse_args()
    if args.fetch:
        return cmd_fetch(args)
    if args.verify:
        return cmd_verify(args)
    if args.build:
        return cmd_build(args)
    return cmd_dry_run(args)


if __name__ == "__main__":
    sys.exit(main())
