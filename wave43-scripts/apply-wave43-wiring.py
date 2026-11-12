#!/usr/bin/env python3
"""Wave 43: wire the fuel gauge into the kernel.

F17 (docs/research/f17-battery-display.md) found two independent reasons the desktop shows
an empty red battery instead of a charge: the pipeline that would tell Darwin about the
battery (drivers/power/hakios.battery.c/.cpp) is not built for this phone at all
(CONFIG_HAKIOS_BATTERY not set in devices/phk110/configs/phk110.config), and nothing in the
kernel produces a state to feed it with. This script wires both halves:

  - the pipeline is built in (phk110.config: CONFIG_HAKIOS_BATTERY=y);
  - the phone's own fuel gauge driver lands at
    devices/phk110/drivers/power/hakios.fuelgauge.c (M1's static feed and M2's real readings
    are its fuelgauge=1 / fuelgauge=2 modes; the canonical copy lives in wave43-scripts/ of
    the project repository, which tracks what the kernel tree's git does not);
  - a driver block in drivers/power/conf (FUELGAUGE, default n, requires BATTERY) so the
    configuration machinery sees it, with stub, prototype and the one call after
    hakios_battery_init() in hakios.input.c;
  - common_defconfig and the QEMU defconfig name the new symbol ("is not set"), as a
    defconfig names every symbol.

Every anchor must appear exactly once; every file must be its wave 43 baseline. Never run
twice: a second run dies on the backups it made the first time.
"""
import hashlib
import os
import shutil
import sys

ROOT = "/home/cyrux/hakios/kernel"
DRIVER_SOURCE = "/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave43-scripts/hakios.fuelgauge.c"

# path -> baseline sha256 (the wave 43 opening state of the kernel tree)
BASELINES = {
    "drivers/power/conf":
        "7935332f74cbc6bb559010a36e701da9b7bc3681b66938a690b9828eeb309fb6",
    "drivers/core/hakios.stubs.c":
        "77619eb5362d6118e48398a9646721b1c01525bd535e5e0c46a2e3e8851b9ebc",
    "drivers/input/hakios.input.c":
        "805bfb777c28367fe64333eeba77eb272c8fb661876eb762187b266e0f68c93a",
    "xnu/files/bsd/sys/hakios.input.h":
        "e4d240135b656be364a91298d30a2375ef8581e9ac80420a8493a46280127478",
    "devices/phk110/configs/phk110.config":
        "cf2c51d2e03281455508c94f3781c22bf5b3a88f2ec360645bf37dc7ad947d3e",
    "configs/common_defconfig":
        "38ce95e66291adc17419a96baa9ee4b445a8ad7c22d2cbcbb322179d35bd2916",
    "devices/qemu/configs/qemu_defconfig":
        "ddc9ed56d22029715f4ac8c262832c2b6888021b7553af37dec349290a7770e1",
}

TREE_HEADER = os.path.join(ROOT, "xnu-src/xnu-8796.121.2/bsd/sys/hakios.input.h")

sha = lambda b: hashlib.sha256(b.encode("utf-8")).hexdigest()
edits = {}          # path -> (old text, new text)

# --- W1: the phone's own power-drivers conf (the device repository's, as the S3910's is) ----------
# A device-repo driver's block lives in its repository's conf (devices/phk110/drivers/power/conf),
# not in the common drivers/power/conf: that is what keeps drivers/map (the common files' list)
# out of it, as with the S3910. The conf is created whole; if it is there, it must be exactly this.
DEVICE_CONF = """# devices/phk110/drivers/power/conf: this phone's own power drivers, on top of the common repository's.
# The format is the same as drivers/power/conf (docs/drivers-config.md); xnu/sync-drivers.sh copies the
# files, tools/hakios-config.py makes the tree's lines from what the .config chooses.

driver FUELGAUGE
\tfile    bsd/dev/hakios.fuelgauge.c
\trequires BATTERY
\tdefault n
\thelp    the fuel gauge: TI bq27541 at I2C 0x55 by hand (GPIO 26 data, 27 clock) and the
\thelp    PM8350B's charger blocks over the SPMI observer (fuelgauge=1 a static battery,
\thelp    fuelgauge=2 the readings), feeding what they say to hakios_battery_report()
"""
device_conf_path = os.path.join(ROOT, "devices/phk110/drivers/power/conf")
if os.path.exists(device_conf_path):
    if open(device_conf_path, encoding="utf-8").read() != DEVICE_CONF:
        sys.exit("devices/phk110/drivers/power/conf is there and is not what this script makes")
else:
    os.makedirs(os.path.dirname(device_conf_path), exist_ok=True)
    open(device_conf_path, "w", encoding="utf-8", newline="\n").write(DEVICE_CONF)

# --- W2: the stub of a kernel without the driver --------------------------------------------------
path = "drivers/core/hakios.stubs.c"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
W2_ANCHOR = (
    "#ifndef HAKIOS_BATTERY\n"
    "void hakios_battery_init(void) {}\n"
    "int hakios_battery_temperature(void) { return -273; }      /* \"not known\", as the driver says before its first reading */\n"
    "void hakios_battery_report(__unused const struct hakios_battery_state *state) {}\n"
    "#endif\n"
)
W2_NEW = W2_ANCHOR + (
    "\n"
    "#ifndef HAKIOS_FUELGAUGE\n"
    "void hakios_fuelgauge_init(void) {}\n"
    "#endif\n"
)
edits[path] = (src, src.replace(W2_ANCHOR, W2_NEW, 1))

# --- W3: the call, right after the battery pipeline's own ------------------------------------------
path = "drivers/input/hakios.input.c"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
W3_ANCHOR = "\thakios_battery_init();\n"
W3_NEW = W3_ANCHOR + "\thakios_fuelgauge_init();      /* the pipeline's source on this phone: the fuel gauge */\n"
edits[path] = (src, src.replace(W3_ANCHOR, W3_NEW, 1))

# --- W4: the prototype, and the tree's copy of this header brought along ----------------------------
path = "xnu/files/bsd/sys/hakios.input.h"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
if sha(open(TREE_HEADER, encoding="utf-8").read()) != BASELINES[path]:
    sys.exit("the kernel tree's copy of bsd/sys/hakios.input.h has drifted from the repository's")
W4_ANCHOR = "void hakios_battery_init(void);        /* boot-arg battery=1: Qualcomm UEFI charger state shared by xnuloader */\n"
W4_NEW = W4_ANCHOR + (
    "void hakios_fuelgauge_init(void);      /* boot-arg fuelgauge=1 static, 2 the buses: the fuel gauge feeds the pipeline */\n"
)
edits[path] = (src, src.replace(W4_ANCHOR, W4_NEW, 1))

# --- W5: the phone's configuration turns both halves on ----------------------------------------------
path = "devices/phk110/configs/phk110.config"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
W5_ANCHOR = "# CONFIG_HAKIOS_BATTERY is not set\n"
W5_NEW = (
    "# the battery pipeline (hakios.battery.c/.cpp): kern.hakios.battery_* and HakiosBattery, the\n"
    "# IOPMPowerSource powerd reads. Was off: with it off the desktop had no battery service at all\n"
    "# (the first of the two reasons F17 gives for the empty red battery)\n"
    "CONFIG_HAKIOS_BATTERY=y\n"
    "# the fuel gauge, this phone's own driver of the device repository\n"
    "# (devices/phk110/drivers/power/): TI bq27541 at I2C 0x55 by hand and the PM8350B's charger\n"
    "# blocks over the SPMI observer, feeding the pipeline (fuelgauge=1 static, fuelgauge=2 the readings)\n"
    "CONFIG_HAKIOS_FUELGAUGE=y\n"
)
edits[path] = (src, src.replace(W5_ANCHOR, W5_NEW, 1))

# --- W6: the common defconfig names the new symbol (it names every symbol) ---------------------------
path = "configs/common_defconfig"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
W6_ANCHOR = "CONFIG_HAKIOS_BATTERY=y\n"
W6_NEW = W6_ANCHOR + (
    "\n"
    "# the fuel gauge of a phone with a bq27541 behind a GENI I2C (this phone's own driver, devices/phk110/drivers/power/)\n"
    "# CONFIG_HAKIOS_FUELGAUGE is not set\n"
)
edits[path] = (src, src.replace(W6_ANCHOR, W6_NEW, 1))

# --- W7: QEMU's defconfig too ------------------------------------------------------------------------
path = "devices/qemu/configs/qemu_defconfig"
src = open(os.path.join(ROOT, path), encoding="utf-8").read()
if sha(src) != BASELINES[path]:
    sys.exit(path + " is not its wave 43 baseline; the anchors are void")
W7_ANCHOR = "# CONFIG_HAKIOS_BATTERY is not set\n"
W7_NEW = W7_ANCHOR + "# CONFIG_HAKIOS_FUELGAUGE is not set\n"
edits[path] = (src, src.replace(W7_ANCHOR, W7_NEW, 1))

# --- apply, with a backup of each edited file ---------------------------------------------------------
for path, (old, new) in edits.items():
    if old == new:
        sys.exit(path + ": the anchor did not change anything")
    full = os.path.join(ROOT, path)
    backup = full + ".v43-orig"
    if os.path.exists(backup):
        sys.exit(path + ": a .v43-orig backup is already there (this script has run before)")
    shutil.copy2(full, backup)
    open(full, "w").write(new)

# --- the driver itself, from the project repository's canonical copy ----------------------------------
driver_path = os.path.join(ROOT, "devices/phk110/drivers/power/hakios.fuelgauge.c")
if os.path.exists(driver_path):
    sys.exit("devices/phk110/drivers/power/hakios.fuelgauge.c is already there (this script has run before)")
os.makedirs(os.path.dirname(driver_path), exist_ok=True)
shutil.copy2(DRIVER_SOURCE, driver_path)

# and the tree's copy of the header follows the repository's
shutil.copy2(os.path.join(ROOT, "xnu/files/bsd/sys/hakios.input.h"), TREE_HEADER)

# --- never-run-twice and completeness markers ---------------------------------------------------------
counts = {
    "devices/phk110/drivers/power/conf": ("driver FUELGAUGE", 1),
    "drivers/core/hakios.stubs.c": ("HAKIOS_FUELGAUGE", 1),       # the ifndef line alone
    "drivers/input/hakios.input.c": ("hakios_fuelgauge_init();", 1),
    "xnu/files/bsd/sys/hakios.input.h": ("hakios_fuelgauge_init(void);", 1),
    "devices/phk110/configs/phk110.config": ("CONFIG_HAKIOS_FUELGAUGE=y", 1),
    "configs/common_defconfig": ("CONFIG_HAKIOS_FUELGAUGE is not set", 1),
    "devices/qemu/configs/qemu_defconfig": ("CONFIG_HAKIOS_FUELGAUGE is not set", 1),
}
for path, (marker, expected) in counts.items():
    text = open(os.path.join(ROOT, path), encoding="utf-8").read()
    n = text.count(marker)
    if n != expected:
        sys.exit("%s: %r appears %d times, expected %d" % (path, marker, n, expected))
driver_text = open(driver_path, encoding="utf-8").read()
for marker in ("fuelgauge=1", "fuelgauge=2", "GAUGE_SOC               0x2c", "USBIN_PLUGIN_BIT",
               "power_status", "hakios_battery_report(&b)"):
    if marker not in driver_text:
        sys.exit("the driver is missing " + marker)
if hashlib.sha256(open(driver_path, "rb").read()).hexdigest() != \
        hashlib.sha256(open(DRIVER_SOURCE, "rb").read()).hexdigest():
    sys.exit("the installed driver differs from the canonical copy")

print("applied: the fuel gauge wired in -- pipeline on (CONFIG_HAKIOS_BATTERY=y), driver installed,")
print("         the device conf/stub/prototype/call in place, common and QEMU defconfigs name the symbol,")
print("         the kernel tree's header copy follows; backups are <file>.v43-orig")
for path in list(counts) + ["devices/phk110/drivers/power/hakios.fuelgauge.c",
                            "xnu-src/xnu-8796.121.2/bsd/sys/hakios.input.h"]:
    print("  %-56s %s" % (path, sha(open(os.path.join(ROOT, path), "rb").read().decode("utf-8"))[:16] + "..."))
