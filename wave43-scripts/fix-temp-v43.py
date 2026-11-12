#!/usr/bin/env python3
# one-shot fixer for wave43-scripts/hakios.fuelgauge.c: the temperature field is hundredths of a
# degree Celsius, but the first draft named it and printed it as thousandths, and the sanity
# window was scaled wrong with it. Run from the wave43-scripts directory (python3 fix-temp-v43.py).
# The verify-print block is replaced first: its operand pair also appears in the summary line, so
# only with it gone does the summary's block match exactly once.
import hashlib
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hakios.fuelgauge.c")
src = io.open(p, encoding="utf-8").read()

n = src.count("thousandths_c")
src = src.replace("thousandths_c", "hundredths_c")

# the local that holds the converted value is hundredths too, now
old_local = "\t\tint thousandths = ((int)word - 2731) * 10;      /* tenths of a kelvin in, thousandths of a degree out */"
new_local = "\t\tint hundredths = ((int)word - 2731) * 10;      /* tenths of a kelvin in, hundredths of a degree Celsius out */"
assert src.count(old_local) == 1, "gauge_look local not found"
src = src.replace(old_local, new_local)
assert src.count("\t\tif (temp_sane(thousandths)) {") == 1
src = src.replace("\t\tif (temp_sane(thousandths)) {", "\t\tif (temp_sane(hundredths)) {")
assert src.count("\t\t\tgauge.hundredths_c = thousandths;") == 1
src = src.replace("\t\t\tgauge.hundredths_c = thousandths;", "\t\t\tgauge.hundredths_c = hundredths;")

# the sanity window in hundredths: -60 C is -6000, 90 C is 9000
old = "temp_sane(int hundredths_c)            { return hundredths_c > -60000 && hundredths_c < 90000; }"
new = "temp_sane(int hundredths_c)            { return hundredths_c > -6000 && hundredths_c < 9000; }"
assert src.count(old) == 1, "sanity window line not found"
src = src.replace(old, new)

# the verify line first (its operand pair also sits in the summary line)
old_ver = (
    '\tprintf("fuelgauge: the gauge answers: SOC %u, %d mV, %d mA, %d.%d C (%d thousandths)\\n", gauge.soc,\n'
    "\t    gauge.mv, gauge.ma, gauge.hundredths_c / 1000,\n"
    "\t    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 1000 / 100,\n"
    "\t    gauge.hundredths_c);"
)
new_ver = (
    '\tprintf("fuelgauge: the gauge answers: SOC %u, %d mV, %d mA, %d.%02d C (%d hundredths)\\n", gauge.soc,\n'
    "\t    gauge.mv, gauge.ma, gauge.hundredths_c / 100,\n"
    "\t    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 100,\n"
    "\t    gauge.hundredths_c);"
)
assert src.count(old_ver) == 1, "verify print not found"
src = src.replace(old_ver, new_ver)

# now the summary's operand pair is the only one left
old_sum = (
    "gauge.hundredths_c / 1000,\n"
    "\t    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 1000 / 100,"
)
new_sum = (
    "gauge.hundredths_c / 100,\n"
    "\t    (gauge.hundredths_c < 0 ? -gauge.hundredths_c : gauge.hundredths_c) % 100,"
)
assert src.count(old_sum) == 1, "summary print operands not found"
src = src.replace(old_sum, new_sum)

old_fmt = '"fuelgauge: %s%u%% %d mV %d mA %d.%d C ext=%d cc=%d chg=%u (%llu polls; %llu SPMI reads, "'
new_fmt = '"fuelgauge: %s%u%% %d mV %d mA %d.%02d C ext=%d cc=%d chg=%u (%llu polls; %llu SPMI reads, "'
assert src.count(old_fmt) == 1, "summary format string not found"
src = src.replace(old_fmt, new_fmt)

src = src.replace("-60 to 90 degrees Celsius.", "-60 to 90 degrees Celsius, in hundredths.")
old_cmt = "\tint mv, ma, hundredths_c;      /* millivolts, milliamperes, thousandths of a degree Celsius */"
new_cmt = "\tint mv, ma, hundredths_c;      /* millivolts, milliamperes, hundredths of a degree Celsius */"
assert src.count(old_cmt) == 1, "the gauge struct's temperature comment not found"
src = src.replace(old_cmt, new_cmt)
assert "thousandths" not in src, "a 'thousandths' is still in the file"

io.open(p, "w", encoding="utf-8", newline="\n").write(src)
print("renamed %d occurrences of thousandths_c" % n)
print("sha256[:16]:", hashlib.sha256(src.encode()).hexdigest()[:16])
