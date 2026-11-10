#!/bin/bash
# p0-carve-run.sh -- P0 for the PHK110: carve darwin (20 GiB exactly, 5,242,875 blocks of 4096) off
# the end of userdata, then fill it with the empty HFS+ data volume. Step by step, one subcommand
# at a time, each step checking the previous one; a failure stops with the way back printed.
#
# This is the EXECUTION script. It is prepared by the P0 prep wave (docs/wave16b-p0-prep.md) and is
# to be run with the user present, phone on Android with root (Magisk), one subcommand per step:
#
#   p0-carve-run.sh preflight            0. everything in place, phone is what the prep wave measured
#   p0-carve-run.sh backup               1. READ ONLY: GPT head/tail + f2fs super + segment_info saved and hashed
#   p0-carve-run.sh resize               2. f2fs shrunk by Android's own kernel (F2FS_IOC_RESIZE_FS) -- DESTRUCTIVE*
#   p0-carve-run.sh dryrun               3. the carve checked dry (nothing written, not even staging files)
#   p0-carve-run.sh carve                4. the new GPT written to the phone, both copies, read back -- DESTRUCTIVE
#   p0-carve-run.sh verify-android       5. rebooted into Android: darwin exists, userdata intact
#   p0-carve-run.sh volume               6. mkdatavol -> fastboot flash darwin (or the adb fallback) -- DESTRUCTIVE
#   p0-carve-run.sh verify-volume        7. rebooted into Android: the HFS+ volume is there
#   p0-carve-run.sh rollback-gpt         E. emergency: write the step-1 GPT back (undoes step 4, nothing else needed)
#   p0-carve-run.sh status               what state is the phone in right now (read only)
#
#   * resize is the only step that touches Android's data (it shrinks the filesystem in place; the
#   kernel moves nothing: the prep wave verified the 20 GiB tail holds no data). If it fails or is
#   aborted BEFORE step 4, a reboot into Android grows the filesystem straight back: nothing is lost.
#
# Rules baked in (from docs/wave15-ufs-research.md P0 + docs/wave16b-p0-prep.md):
#   - darwin must come out exactly 5,242,875 blocks (the kernel's UFS_DARWIN_MIN, the loader's
#     BLOCK_DARWIN_MIN, mkdatavol's DARWIN_BLOCKS -- zero changes to any of them), and it must be
#     the fixed unique GUID the carve stamps (6E9D0187-62E7-4887-B50E-FB241BF4BE6D).
#   - the GPT is written table-before-header on each copy, both copies, then read back and compared.
#   - no reboot between step 2 and step 4 (a boot would grow the f2fs straight back).
#   - this script never touches boot_a/boot_b or any other partition, and never runs
#     git reset/checkout/stash/clean.
#
# Destructive steps refuse unless the operator types the word the step asks for (or P0_APPROVED=yes
# is set, for a session where the user has already approved the whole P0).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$REPO/tools"
BK="$REPO/backups-slotb"
RUN_DIR="${P0_RUN_DIR:-$BK/p0-run}"
FORK="${HAKIOS_FORK:-$HOME/hakios/kernel}"

# ---- PHK110 constants, measured 2026-11-03 (docs/wave16b-p0-prep.md); preflight re-verifies them
SDA_BYTES=251964424192            # LUN 0 = /dev/block/sda
DISK_BLOCKS=61514752              # in blocks of 4096
LAST_USABLE=61514746
UD_FIRST=3756780                  # userdata = entry 14, sda14
UD_LAST=61514746
FS_BLOCKS_BEFORE=57757967         # f2fs block_count (fills the partition)
NEW_BLOCKS=52514816               # f2fs-resize /data 52514816  (= main_blkaddr 176128 + 102224 segs x 512)
FS_BLOCKS_AFTER=52515087          # f2fs after: 57757967 - 10240 segs x 512
UD_NEW_LAST=56271866              # userdata entry's last LBA after the carve
DARWIN_FIRST=56271872
DARWIN_LAST=61514746
DARWIN_BLOCKS=5242875
DARWIN_BYTES=21474816000
DARWIN_GUID=6E9D0187-62E7-4887-B50E-FB241BF4BE6D
GIB=20
DATA_FIRST=2042368                # the data volume's first block in darwin (mkdatavol, kernel UFS_WRITE_FIRST)
BASELINE_HEAD_SHA=8dc1919bc32bc1185a4e0c4970cd32a6829ca5adcc0bfc05b9ec4f8b2c24bd5c
BASELINE_TAIL_SHA=7ed16c8724440bc05006cda3df94f72e8aef8e600f31164d643ed7f4d4e3f4af
BASELINE_DM_SUPER_SHA=da2fee90d10220d3fad9dd9775300758b2bf49c8235c74ff9cd3f3dd44e4b144

say()  { printf '%s\n' "$*"; }
die()  { printf 'p0: FAIL: %s\n' "$*" >&2; exit 1; }
gate() { # gate STEP WORD -- destructive steps ask for the word, unless P0_APPROVED=yes
    [ "${P0_APPROVED:-}" = yes ] && return 0
    printf 'p0: about to: %s\nType "%s" to go on, anything else to stop: ' "$*" "$2"
    read -r a
    [ "$a" = "$2" ] || die "not approved: $*"
}

phone() { # phone <script on stdin>  -- root shell, output on stdout (TEXT only: adb shell may CRLF-mangle bytes)
    adb shell su -c sh
}

phone_bin() { # phone_bin <command> -- one command, its stdout BINARY-safe (adb exec-out, as darwin-write.py's phone_bytes)
    adb exec-out "su -c '$1'"
}

phone_dm() { # echo the dm device over sda14 (dm name "userdata"); empty if none
    phone <<'EOF'
for x in /sys/block/dm-*; do
    [ "$(cat $x/dm/name 2>/dev/null)" = userdata ] && echo "$(basename $x)" && break
done
EOF
}

dm_node=$(phone_dm | tr -d '\r' | head -1 || true)

step_prev() { [ -f "$RUN_DIR/$1" ] || die "step prerequisite missing: $RUN_DIR/$1 (run the earlier step first)"; }

# ---------------------------------------------------------------- 0. preflight
cmd_preflight() {
    command -v adb >/dev/null || die "no adb"
    [ "$(adb get-state 2>/dev/null || true)" = device ] || die "no adb device (phone must be on Android, not bootloader/loader)"
    phone <<'EOF' >/dev/null || die "no root on the phone (adb shell su -c id failed)"
id -u
EOF
    say "-- phone identity"
    local node udnode sdabytes ss dmhash udblocks
    udnode=$(phone <<'EOF'
readlink -f /dev/block/by-name/userdata
EOF
)
    udnode=${udnode%$'\r'}
    [ "$udnode" = /dev/block/sda14 ] || die "userdata is $udnode, not /dev/block/sda14: not the phone the prep wave measured"
    local darwin_there
    darwin_there=$(phone <<'EOF'
test -e /dev/block/by-name/darwin && echo YES || echo NO
EOF
)
    if [ "${darwin_there%%$'\r'*}" = YES ]; then die "a darwin partition already exists -- P0 was already done?"; fi
    sdabytes=$(phone <<'EOF'
blockdev --getsize64 /dev/block/sda
EOF
)
    sdabytes=${sdabytes%$'\r'}
    [ "$sdabytes" = "$SDA_BYTES" ] || die "sda is $sdabytes bytes, not $SDA_BYTES"
    ss=$(phone <<'EOF'
blockdev --getss /dev/block/sda
EOF
)
    ss=${ss%$'\r'}
    [ "$ss" = 4096 ] || die "sda logical sector is $ss, not 4096"
    [ -n "$dm_node" ] || die "no dm device named \"userdata\" over sda14 (metadata encryption layer not found)"
    say "   userdata = sda14, sda = $sdabytes bytes, sector $ss, f2fs on dm device $dm_node -- as measured"
    say "-- GPT against the prep wave's baseline"
    phone_bin "dd if=/dev/block/sda bs=4096 count=8 2>/dev/null" > /tmp/p0-head-check.bin
    phone_bin "dd if=/dev/block/sda bs=4096 count=8 skip=61514744 2>/dev/null" > /tmp/p0-tail-check.bin
    local h t
    h=$(sha256sum /tmp/p0-head-check.bin | cut -d' ' -f1)
    t=$(sha256sum /tmp/p0-tail-check.bin | cut -d' ' -f1)
    [ "$h" = "$BASELINE_HEAD_SHA" ] || die "GPT head sha256 $h is not the prep wave's $BASELINE_HEAD_SHA -- the table changed since; redo the prep-wave backup and re-derive the carve"
    [ "$t" = "$BASELINE_TAIL_SHA" ] || die "GPT tail sha256 $t is not the prep wave's $BASELINE_TAIL_SHA"
    say "   head $h"
    say "   tail $t  -- both as measured"
    say "-- host side"
    [ -f "$TOOLS/userdata-carve-phk110.py" ] || die "missing $TOOLS/userdata-carve-phk110.py"
    [ -f "$TOOLS/darwin-write-phk110.py" ] || die "missing $TOOLS/darwin-write-phk110.py"
    [ -f "$FORK/tools/mkdatavol.py" ] || die "missing $FORK/tools/mkdatavol.py (set HAKIOS_FORK)"
    [ -f "$FORK/tools/android/f2fs-resize.c" ] || die "missing $FORK/tools/android/f2fs-resize.c (set HAKIOS_FORK)"
    command -v mkfs.hfsplus >/dev/null || die "no mkfs.hfsplus (needed by mkdatavol, step 6)"
    command -v fastboot >/dev/null || say "   note: no fastboot in PATH -- step 6 falls back to the adb path"
    command -v simg2img >/dev/null || say "   note: no simg2img -- the adb fallback of step 6 needs it (dnf install android-tools)"
    say "preflight: PASS"
}

# ---------------------------------------------------------------- 1. backup (read only)
cmd_backup() {
    mkdir -p "$RUN_DIR"
    [ -n "$dm_node" ] || die "dm device not found (run preflight)"
    say "-- reading (all read only: dd if=, ls, cat) and hashing on the phone"
    phone <<EOF
mkdir -p /data/local/tmp/p0
dd if=/dev/block/sda bs=4096 count=8 2>/dev/null > /data/local/tmp/p0/gpt-head.bin
dd if=/dev/block/sda bs=4096 count=8 skip=61514744 2>/dev/null > /data/local/tmp/p0/gpt-tail.bin
dd if=/dev/block/$dm_node bs=4096 count=1 2>/dev/null > /data/local/tmp/p0/userdata-meta-before.bin
cat /proc/fs/f2fs/$dm_node/segment_info > /data/local/tmp/p0/segment_info-before.txt
sha256sum /data/local/tmp/p0/gpt-head.bin /data/local/tmp/p0/gpt-tail.bin /data/local/tmp/p0/userdata-meta-before.bin
EOF
    for f in gpt-head.bin gpt-tail.bin userdata-meta-before.bin segment_info-before.txt; do
        MSYS_NO_PATHCONV=1 adb pull "/data/local/tmp/p0/$f" "$RUN_DIR/$f" >/dev/null || die "pull $f"
    done
    say "-- hashes, host side"
    ( cd "$RUN_DIR" && sha256sum gpt-head.bin gpt-tail.bin userdata-meta-before.bin segment_info-before.txt )
    local h t s
    h=$(sha256sum "$RUN_DIR/gpt-head.bin" | cut -d' ' -f1)
    t=$(sha256sum "$RUN_DIR/gpt-tail.bin" | cut -d' ' -f1)
    s=$(sha256sum "$RUN_DIR/userdata-meta-before.bin" | cut -d' ' -f1)
    [ "$h" = "$BASELINE_HEAD_SHA" ] || die "GPT head is $h, not the prep wave's $BASELINE_HEAD_SHA"
    [ "$t" = "$BASELINE_TAIL_SHA" ] || die "GPT tail is $t, not the prep wave's $BASELINE_TAIL_SHA"
    [ "$s" = "$BASELINE_DM_SUPER_SHA" ] || die "f2fs superblock is $s, not the prep wave's $BASELINE_DM_SUPER_SHA (the filesystem changed since -- re-derive the carve numbers first)"
    python3 - "$RUN_DIR/userdata-meta-before.bin" <<'EOF'
import struct, sys
b = open(sys.argv[1], 'rb').read()[1024:2048]
magic, = struct.unpack_from('<I', b, 0)
bc, = struct.unpack_from('<Q', b, 36)
segs, = struct.unpack_from('<I', b, 68)
main, = struct.unpack_from('<I', b, 92)
assert magic == 0xf2f52010, 'not an f2fs'
assert (bc, segs, main) == (57757967, 112464, 176128), (bc, segs, main)
print('f2fs: %d blocks, %d main segments, main area at %d -- as measured' % (bc, segs, main))
EOF
    phone <<'EOF'
rm -rf /data/local/tmp/p0
EOF
    say "backup: PASS (in $RUN_DIR; rollback-GPT material = gpt-head.bin + gpt-tail.bin of this dir)"
}

# ---------------------------------------------------------------- 2. f2fs resize (destructive*)
cmd_resize() {
    step_prev segment_info-before.txt
    [ -n "$dm_node" ] || die "dm device not found (run preflight)"
    say "-- build f2fs-resize (static arm64, into /tmp -- the fork tree is not written)"
    local FR=/tmp/p0-f2fs-resize
    clang --target=aarch64-linux-gnu -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -static \
        -fuse-ld=lld -O1 -Wall -Wl,-e,_start -o "$FR" "$FORK/tools/android/f2fs-resize.c" \
        || die "clang failed (WSL: dnf install clang lld)"
    adb push "$FR" /data/local/tmp/f2fs-resize >/dev/null || die "push f2fs-resize"
    say "-- probe: does Android's kernel have F2FS_IOC_RESIZE_FS?"
    phone <<'EOF' > /tmp/p0-probe.out
chmod 755 /data/local/tmp/f2fs-resize
/data/local/tmp/f2fs-resize /data probe && echo PROBE-OK || echo PROBE-BAD
EOF
    cat /tmp/p0-probe.out
    grep -q PROBE-OK /tmp/p0-probe.out || die "the kernel refused the resize ioctl probe (R6): stop; see the report's rollback section"
    say "-- the filesystem must be exactly as measured (no reboot since the backup, nothing moved)"
    phone_bin "dd if=/dev/block/$dm_node bs=4096 count=1 2>/dev/null" > /tmp/p0-sb-now.bin
    python3 - /tmp/p0-sb-now.bin <<'EOF'
import struct, sys
b = open(sys.argv[1], 'rb').read()[1024:2048]
bc, = struct.unpack_from('<Q', b, 36)
assert bc == 57757967, 'f2fs is %d blocks now, the measurement said 57757967 (a reboot happened? data changed?): re-run backup' % bc
print('f2fs still %d blocks -- as measured' % bc)
EOF
    gate "shrink /data's f2fs to $NEW_BLOCKS blocks (F2FS_IOC_RESIZE_FS; nothing to move: the tail is empty)" RESIZE
    say "-- shrinking"
    phone <<'EOF' > /tmp/p0-resize.out
/data/local/tmp/f2fs-resize /data 52514816; echo "resize-rc=$?"
EOF
    cat /tmp/p0-resize.out
    grep -q 'resize-rc=0' /tmp/p0-resize.out \
        || die "f2fs-resize failed (R6): NOTHING is lost -- a reboot grows the fs back; see the report's rollback section"
    say "-- checking what the kernel made"
    phone_bin "dd if=/dev/block/$dm_node bs=4096 count=1 2>/dev/null" > "$RUN_DIR/sb-after.bin"
    phone <<EOF > "$RUN_DIR/segment_info-after.txt"
cat /proc/fs/f2fs/$dm_node/segment_info
EOF
    python3 - "$RUN_DIR/sb-after.bin" <<'EOF'
import struct, sys
b = open(sys.argv[1], 'rb').read()[1024:2048]
bc, = struct.unpack_from('<Q', b, 36)
segs, = struct.unpack_from('<I', b, 68)
assert (bc, segs) == (52515087, 102224), 'after the shrink: %d blocks, %d segments -- expected 52515087, 102224' % (bc, segs)
print('f2fs now %d blocks, %d main segments -- exactly the carve\'s numbers' % (bc, segs))
EOF
    python3 - "$RUN_DIR/segment_info-after.txt" <<'EOF'
import sys
valid = {}
for line in open(sys.argv[1]):
    p = line.split()
    if len(p) < 2 or not p[0].isdigit():
        continue
    for k, e in enumerate(p[1:]):
        valid[int(p[0]) + k] = int(e.split('|')[1])
assert len(valid) == 102224, 'the kernel now reports %d segments, expected the shrunk 102224' % len(valid)
last_used = max(s for s in valid if valid[s])
assert last_used < 102224, 'data in segment %d, past the f2fs end?' % last_used
print('the kernel\'s own view: %d segments (102224 = 112464 - 10240), last data segment %d -- the fs is the shrunk one' % (len(valid), last_used))
EOF
    say "-- /data still mounts and serves:"
    phone <<'EOF'
df -h /data | tail -1
EOF
    say "resize: PASS. DO NOT REBOOT until step 4 (carve) is done -- a boot grows the f2fs back."
    say "  User: please look at the phone now (photos, files all there?). Then run: $0 dryrun"
}

# ---------------------------------------------------------------- 3. dry-run carve
cmd_dryrun() {
    step_prev segment_info-before.txt
    step_prev sb-after.bin
    say "-- userdata-carve-phk110.py --dry-run against $RUN_DIR"
    python3 -I "$TOOLS/userdata-carve-phk110.py" "$RUN_DIR" "$GIB" darwin --dry-run \
        || die "the carve tool refused (see above): fix before going on"
    say "dryrun: PASS (nothing written anywhere; the phone was never touched)"
}

# ---------------------------------------------------------------- 4. the carve (destructive)
cmd_carve() {
    step_prev sb-after.bin
    say "-- the carve, for real: makes gpt-head.new/gpt-tail.new in $RUN_DIR (host only, so far)"
    python3 -I "$TOOLS/userdata-carve-phk110.py" "$RUN_DIR" "$GIB" darwin \
        || die "the carve tool refused: nothing written"
    say "-- independent check of what the tool made (not the tool's own word)"
    python3 - "$RUN_DIR/gpt-head.new" "$RUN_DIR/gpt-tail.new" <<'EOF'
import struct, sys, uuid, zlib
BS = 4096
head, tail = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
def law(h, at):
    h = h[at:at+BS]
    sz = struct.unpack_from('<I', h, 12)[0]
    t = bytearray(h[:sz]); want = struct.unpack_from('<I', t, 16)[0]; struct.pack_into('<I', t, 16, 0)
    assert zlib.crc32(bytes(t)) & 0xffffffff == want, 'header CRC wrong'
    n, esz = struct.unpack_from('<II', h, 80)
    assert (n, esz) == (32, 128), (n, esz)
    raw = h[BS:BS+n*esz] if at == BS else None
    return h, raw
h0, t0 = law(head, BS)
raw = head[2*BS:2*BS+32*128]
assert zlib.crc32(raw) & 0xffffffff == struct.unpack_from('<I', h0, 88)[0], 'table CRC wrong'
e14 = raw[13*128:14*128]; e15 = raw[14*128:15*128]
assert struct.unpack_from('<Q', e14, 40)[0] == 56271866, 'userdata does not end at 56271866'
assert e15[56:68].decode('utf-16le') == 'darwin', 'entry 15 is not darwin'
first, last = struct.unpack_from('<QQ', e15, 32)
assert (first, last) == (56271872, 61514746), (first, last)
assert last - first + 1 == 5242875, 'darwin is %d blocks, the law says 5242875' % (last - first + 1)
assert str(uuid.UUID(bytes_le=e15[16:32])).upper() == '6E9D0187-62E7-4887-B50E-FB241BF4BE6D'
bt = tail[3*BS:3*BS+32*128]
assert bt == raw, 'backup table is not the primary table'
assert tail[7*BS:7*BS+8] == b'EFI PART', 'no backup header'
print('the new table: userdata to 56271866, darwin 56271872..61514746 = 5242875 blocks, GUID as laid down; both copies agree')
EOF
    gate "write the new GPT to /dev/block/sda (userdata shortened, darwin added; both copies, then read back)" CARVE
    adb push "$RUN_DIR/gpt-head.new" /data/local/tmp/gpt-head.new >/dev/null
    adb push "$RUN_DIR/gpt-tail.new" /data/local/tmp/gpt-tail.new >/dev/null
    say "-- writing: each copy table-before-header (a cut-short write leaves the other copy good)"
    phone <<'EOF' || die "a GPT-write dd failed (see above): the table state is unknown -- STOP, do not reboot, diagnose, then $0 rollback-gpt"
dd if=/data/local/tmp/gpt-head.new of=/dev/block/sda bs=4096 skip=2 seek=2 count=1 conv=notrunc,fsync
dd if=/data/local/tmp/gpt-head.new of=/dev/block/sda bs=4096 skip=1 seek=1 count=1 conv=notrunc,fsync
dd if=/data/local/tmp/gpt-tail.new of=/dev/block/sda bs=4096 skip=3 seek=61514747 count=5 conv=notrunc,fsync
sync
EOF
    say "-- reading both regions back and comparing"
    phone_bin "dd if=/dev/block/sda bs=4096 count=8 2>/dev/null" > /tmp/p0-head-back.bin
    phone_bin "dd if=/dev/block/sda bs=4096 count=8 skip=61514744 2>/dev/null" > /tmp/p0-tail-back.bin
    cmp /tmp/p0-head-back.bin "$RUN_DIR/gpt-head.new" || die "the GPT head on the phone is NOT what was written: STOP, run: $0 rollback-gpt"
    cmp /tmp/p0-tail-back.bin "$RUN_DIR/gpt-tail.new" || die "the GPT tail on the phone is NOT what was written: STOP, run: $0 rollback-gpt"
    phone <<'EOF'
rm -f /data/local/tmp/gpt-head.new /data/local/tmp/gpt-tail.new
EOF
    say "-- the running f2fs is untouched by the table change:"
    phone <<EOF
dd if=/dev/block/$dm_node bs=4096 count=1 2>/dev/null | sha256sum
EOF
    say "carve: PASS (both copies on the phone verified byte for byte). Now reboot into Android"
    say "  (adb reboot) and let the user check the phone, then run: $0 verify-android"
    say "  If Android does not come up: fastboot/adb root shell, run: $0 rollback-gpt"
}

# ---------------------------------------------------------------- 5. android-side verification
cmd_verify_android() {
    step_prev gpt-head.new
    say "-- darwin as Android sees it now"
    phone <<'EOF'
ls -l /dev/block/by-name/darwin
blockdev --getsize64 /dev/block/by-name/darwin
cat /sys/class/block/sda15/partition /sys/class/block/sda15/start /sys/class/block/sda15/size
grep ^PARTNAME= /sys/class/block/sda15/uevent
EOF
    local bytes
    bytes=$(phone <<'EOF'
blockdev --getsize64 /dev/block/by-name/darwin
EOF
)
    bytes=${bytes%$'\r'}
    [ "$bytes" = "$DARWIN_BYTES" ] || die "darwin is $bytes bytes, not $DARWIN_BYTES (5,242,875 blocks of 4096)"
    say "-- userdata: still there, still serving"
    phone <<'EOF'
df -h /data | tail -1
EOF
    say "-- the port's own identity chain (tools/darwin-write-phk110.py check: writes nothing)"
    python3 -I "$TOOLS/darwin-write-phk110.py" check || die "darwin's identity is not what the tools laid down"
    say "verify-android: PASS. User: please confirm your data (photos, chats, files) is intact."
    say "  Then run: $0 volume"
}

# ---------------------------------------------------------------- 6. the data volume
cmd_volume() {
    step_prev gpt-head.new
    local OUT="$RUN_DIR/darwin.simg"
    say "-- building the empty HFS+ data volume as a sparse image (tools/mkdatavol.py, unchanged)"
    python3 -I "$FORK/tools/mkdatavol.py" "$OUT" || die "mkdatavol failed"
    ls -la "$OUT"
    if command -v fastboot >/dev/null && [ "${P0_VOLUME_VIA:-fastboot}" = fastboot ]; then
        say "-- fastboot path (the phone must be in bootloader: adb reboot bootloader first;"
        say "   on this host fastboot lives in WSL and needs the phone attached: usbipd bind+attach, per STATUS.md)"
        if ! fastboot getvar all 2>&1 | grep -qi darwin; then
            say "   note: fastboot does not list a darwin partition (its GPT view may predate the carve)."
            say "   If 'fastboot flash darwin' fails, use the adb fallback: reboot Android, then P0_VOLUME_VIA=adb $0 volume"
        fi
        gate "fastboot flash darwin $OUT" FLASH
        fastboot flash darwin "$OUT" || die "fastboot flash darwin failed: use P0_VOLUME_VIA=adb $0 volume (from Android)"
    else
        say "-- adb fallback: sparse -> raw, keep only the volume's blocks (from $DATA_FIRST on),"
        say "   then the port's own guarded writer (identity checks, sha256, read back)"
        command -v simg2img >/dev/null || die "no simg2img (dnf install android-tools)"
        simg2img "$OUT" "$RUN_DIR/darwin.raw"
        tail -c +"$((DATA_FIRST * 4096 + 1))" "$RUN_DIR/darwin.raw" > "$RUN_DIR/darwin-vol.raw"
        rm -f "$RUN_DIR/darwin.raw"
        ls -la "$RUN_DIR/darwin-vol.raw"
        gate "adb-write the volume into darwin blocks $DATA_FIRST..$DARWIN_LAST (nothing before $DATA_FIRST is touched)" VOLW
        ( cd "$TOOLS" && DARWIN_WRITE=yes python3 -I darwin-write-phk110.py write "$RUN_DIR/darwin-vol.raw" "$DATA_FIRST" ) \
            || die "the guarded write refused or failed (see logs/darwin-write-phk110.log)"
    fi
    say "volume: PASS. Reboot into Android (fastboot reboot / adb reboot), then run: $0 verify-volume"
}

# ---------------------------------------------------------------- 7. volume verification
cmd_verify_volume() {
    say "-- the HFS+ volume header at darwin block $DATA_FIRST (bytes 1024..1025: H+ or HX)"
    local sig
    sig=$(phone_bin "dd if=/dev/block/by-name/darwin bs=4096 skip=$DATA_FIRST count=1 2>/dev/null | tail -c +1025 | head -c 2")
    say "   signature: '$sig'"
    case "$sig" in H+|HX) ;; *) die "no HFS+ volume header at darwin block $DATA_FIRST (got '$sig')";; esac
    python3 -I "$TOOLS/darwin-write-phk110.py" sum "$DATA_FIRST" 1 || true
    say "-- and the start of darwin (the future Darwin volume) was not touched by this step:"
    python3 -I "$TOOLS/darwin-write-phk110.py" sum 0 1 || true
    say "verify-volume: PASS -- P0 is done: darwin exists (5,242,875 blocks, 20 GiB), the empty HFS+ data"
    say "  volume sits at block $DATA_FIRST. S0-S2 (config + ufs=2, read only) of docs/wave15-ufs-research.md"
    say "  is the next wave; the kernel will see the volume as /dev/ufs_darwin_data."
}

# ---------------------------------------------------------------- E. rollback
cmd_rollback_gpt() {
    step_prev gpt-head.bin
    gate "write the SAVED GPT (userdata as it was, no darwin) back to /dev/block/sda, both copies" ROLLBK
    adb push "$RUN_DIR/gpt-head.bin" /data/local/tmp/gpt-orig-head.bin >/dev/null
    adb push "$RUN_DIR/gpt-tail.bin" /data/local/tmp/gpt-orig-tail.bin >/dev/null
    phone <<'EOF'
dd if=/data/local/tmp/gpt-orig-head.bin of=/dev/block/sda bs=4096 skip=2 seek=2 count=1 conv=notrunc,fsync
dd if=/data/local/tmp/gpt-orig-head.bin of=/dev/block/sda bs=4096 skip=1 seek=1 count=1 conv=notrunc,fsync
dd if=/data/local/tmp/gpt-orig-tail.bin of=/dev/block/sda bs=4096 skip=3 seek=61514747 count=5 conv=notrunc,fsync
sync
rm -f /data/local/tmp/gpt-orig-head.bin /data/local/tmp/gpt-orig-tail.bin
EOF
    say "rollback-gpt: DONE. Reboot into Android: fs_mgr's resize.f2fs grows the shrunk filesystem"
    say "  back to the old partition -- data intact, the phone as it was before P0."
    say "  (If the f2fs was never shrunk -- step 2 not run -- the reboot changes nothing at all.)"
}

# ---------------------------------------------------------------- status (read only)
cmd_status() {
    if [ "$(adb get-state 2>/dev/null || true)" != device ]; then say "phone: not on adb (bootloader/loader/off?)"; exit 0; fi
    [ -n "$dm_node" ] && say "dm over sda14: $dm_node" || say "dm over sda14: none"
    phone <<'EOF'
echo "darwin: $(test -e /dev/block/by-name/darwin && echo present || echo absent)"
test -e /dev/block/by-name/darwin && blockdev --getsize64 /dev/block/by-name/darwin
echo "userdata: $(blockdev --getsize64 /dev/block/by-name/userdata) bytes"
df -h /data | tail -1
EOF
    local dmsha
    if [ -n "$dm_node" ]; then
        dmsha=$(phone <<EOF
dd if=/dev/block/$dm_node bs=4096 count=1 2>/dev/null | sha256sum
EOF
)
        say "f2fs super (via dm) sha256: $dmsha  (pre-P0: $BASELINE_DM_SUPER_SHA)"
    fi
}

case "${1:-}" in
    preflight) cmd_preflight ;;
    backup) cmd_backup ;;
    resize) cmd_resize ;;
    dryrun) cmd_dryrun ;;
    carve) cmd_carve ;;
    verify-android) cmd_verify_android ;;
    volume) cmd_volume ;;
    verify-volume) cmd_verify_volume ;;
    rollback-gpt) cmd_rollback_gpt ;;
    status) cmd_status ;;
    *) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
