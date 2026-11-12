#!/bin/bash
# Wave 39: build the Mesa userspace for the phone (WSL tree), the wave35 s5 #6 construction
# order item made real. Wraps the tree's own tools/mk-mesa.sh with the environment this WSL
# needs (found by wave39 the hard way; see docs/waves/wave39-mesa-userland.md s2):
#   - meson and ninja are not on this WSL: pip --user installs them into ~/.local/bin
#   - patch is not installed: dnf needs it before mk-mesa.sh can apply tools/mesa/*.patch
#   - (do not) nohup background: a wsl.exe session reaps its children; run this in the
#     foreground of one wsl.exe call
# Then verifies the artifacts and prints their sha256 for the ledger (the tree is not in
# this git repository; big files stay in the WSL tree, only the hashes are recorded).
#
#   wave39-scripts/build-mesa.sh            build the library (drivers softpipe,freedreno)
#   wave39-scripts/build-mesa.sh AIR=1      ... and air_run (Metal-translated-drawing test)
#   wave39-scripts/build-mesa.sh IMAGE=1    ... and the GL=test root.apfs that carries
#                                           bin/gl_test + lib/libOSMesa.8.dylib + fw/ to the
#                                           phone (the v25 recipe + GL=test, RC_JOBS=rc.jobs.ssh)
set -e
R=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
K=/home/cyrux/hakios/kernel
say() { echo "[wave39] $*"; }

command -v patch >/dev/null || { say "patch missing: sudo dnf install -y patch"; exit 1; }
[ -x "$HOME/.local/bin/meson" ] || python3 -m pip install --quiet --user meson ninja
export PATH="$HOME/.local/bin:$PATH"

if [ ! -f "$K/tools/mk-mesa.sh" ]; then say "no WSL tree at $K"; exit 1; fi

say "building Mesa (tools/mk-mesa.sh, pin 25.0.7)..."
( cd "$K/tools" && env ${AIR:+AIR=1} bash ./mk-mesa.sh )

M=$K/xnu-deps/build/mesa/out
say "-- ledger:"
sha256sum "$K/xnu-deps/build/mesa/mesa-25.0.7.tar.xz" "$M"/libOSMesa.8.dylib "$M"/exported-gl.txt "$M"/gl.xml "$M"/built-from
[ -f "$M/air_run" ] && sha256sum "$M/air_run"
file "$M/libOSMesa.8.dylib"
say "freedreno device identity present in the library: $(strings -a "$M/libOSMesa.8.dylib" | grep -c '^FD725$') x 'FD725'"

if [ -n "$IMAGE" ]; then
    say "building the GL=test root.apfs (v25 recipe FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh, delta GL=test)..."
    ( cd "$K/userland" && GL=test FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh ./build.sh >/dev/null )
    say "-- ledger (image):"
    sha256sum "$K/userland/root.apfs" "$K/userland/obj/libOSMesa.8.dylib" "$K/userland/obj/gl_test"
    say "root.bin/gl_test and root.lib/libOSMesa.8.dylib staged; fw/ = $(ls "$K/userland/root/fw" | wc -l) files"
fi
say "done"
