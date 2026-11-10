import io

p = "wave26-scripts/runbook-phone-return.sh"
lines = open(p, encoding="utf-8").read().splitlines()

dd_i = next(i for i, l in enumerate(lines) if "dd if=/dev/block/by-name/boot_b of=" in l)
rm_i = next(i for i, l in enumerate(lines) if "rm -f /data/local/tmp/boot_b.read." in l)
print("replacing lines", dd_i + 1, "to", rm_i + 1)

new_lines = [
    '    # Windows adb.exe `shell` mangles CRLF (wave16c lesson): stream binary via',
    '    # exec-out straight into the scratch file -- no on-device temp, no pull.',
    '    adb exec-out "su -c \'dd if=/dev/block/by-name/boot_b bs=4096 count=49152\'" > "$READ_FILE" 2>/dev/null \\',
    '        || DIE "exec-out dd of boot_b failed"',
    '    RSIZE=$(stat -c %s "$READ_FILE" 2>/dev/null)',
    '    [ "$RSIZE" = "201326592" ] || DIE "boot_b read size wrong: $RSIZE (want 201326592)"',
    "    READ_SHA=$(sha256sum \"$READ_FILE\" 2>/dev/null | cut -d' ' -f1)",
    '    rm -f "$READ_FILE"',
    '    LOG "boot_b read sha256: $READ_SHA"',
]
lines[dd_i : rm_i + 1] = new_lines
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("patched")
