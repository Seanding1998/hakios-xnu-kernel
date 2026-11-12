#!/usr/bin/env python3
"""Wave 43 wiring correction: the FUELGAUGE driver block belongs in the DEVICE repository's
drivers/power/conf (devices/phk110/drivers/power/conf, the S3910's precedent), not in the
common repository's drivers/power/conf -- drivers-check.py said so ("which drivers/map does
not list": a common-repo conf block builds a drivers/map file, and a device-repo driver's
file is of no map). This script restores the common conf to its wave 43 baseline (its
.v43-orig, whose sha must equal the baseline the wiring patcher pinned) and creates the
device conf with the block. The wiring patcher itself now makes the right shape; this script
moves the already-wired tree over to it.
"""
import hashlib
import os
import shutil
import sys

ROOT = "/home/cyrux/hakios/kernel"
COMMON_CONF = os.path.join(ROOT, "drivers/power/conf")
BASELINE = "7935332f74cbc6bb559010a36e701da9b7bc3681b66938a690b9828eeb309fb6"
DEVICE_CONF = os.path.join(ROOT, "devices/phk110/drivers/power/conf")
DEVICE_CONF_TEXT = """# devices/phk110/drivers/power/conf: this phone's own power drivers, on top of the common repository's.
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

sha = lambda b: hashlib.sha256(b.encode("utf-8")).hexdigest()

current = open(COMMON_CONF, encoding="utf-8").read()
if sha(current) == BASELINE:
    print("drivers/power/conf: already at its baseline, nothing to restore")
else:
    backup = COMMON_CONF + ".v43-orig"
    if not os.path.exists(backup):
        sys.exit("no .v43-orig backup of drivers/power/conf to restore from")
    if sha(open(backup, encoding="utf-8").read()) != BASELINE:
        sys.exit("the .v43-orig of drivers/power/conf is not the wave 43 baseline")
    shutil.copy2(backup, COMMON_CONF)
    print("drivers/power/conf: restored to its wave 43 baseline")

if os.path.exists(DEVICE_CONF):
    if open(DEVICE_CONF, encoding="utf-8").read() != DEVICE_CONF_TEXT:
        sys.exit("devices/phk110/drivers/power/conf is there and is not what this script makes")
    print("devices/phk110/drivers/power/conf: already right")
else:
    os.makedirs(os.path.dirname(DEVICE_CONF), exist_ok=True)
    open(DEVICE_CONF, "w", encoding="utf-8", newline="\n").write(DEVICE_CONF_TEXT)
    print("devices/phk110/drivers/power/conf: created with the FUELGAUGE block")

text = open(COMMON_CONF, encoding="utf-8").read()
if "FUELGAUGE" in text:
    sys.exit("the common conf still mentions FUELGAUGE")
print("done: the block is the device repository's; the common conf is its baseline again")
