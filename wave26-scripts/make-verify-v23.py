#!/usr/bin/env python3
"""Generate verify-udon-hakios-v23.py from verify-udon-hakios-v22.py."""
import re

src = open(r"wave26-scripts/verify-udon-hakios-v22.py", encoding="utf-8").read()

src = src.replace("Wave 26 Round 2 (v22, the maxvnodes loader) verification of udon-hakios-grafted-v22.img.",
                  "Wave 26 Round 3 (v23, the long-session cmdline) verification of udon-hakios-grafted-v23.img.")
src = src.replace("IMG, STOCK, SHIM, FD, PAYLOAD_V22, PAYLOAD_V21, CMDLINE_FILE, KFILE = sys.argv[1:9]",
                  "IMG, STOCK, SHIM, FD, PAYLOAD_V23, PAYLOAD_V22, CMDLINE_FILE, KFILE = sys.argv[1:9]")
src = src.replace("payload = open(PAYLOAD_V22, \"rb\").read()\npayload_v21 = open(PAYLOAD_V21, \"rb\").read()",
                  "payload = open(PAYLOAD_V23, \"rb\").read()\npayload_v21 = open(PAYLOAD_V22, \"rb\").read()")
src = src.replace("e22 = payload_entries(payload)\ne21 = payload_entries(payload_v21)",
                  "e23 = payload_entries(payload)\ne21 = payload_entries(payload_v21)")
src = src.replace('check("cmdline = the v18 bytes exactly (the vnode fix moves no boot-arg)",\n      g[cmd_off:cmd_off + cmd_sz] == cmdline_file)',
                  'check("cmdline = the v18 bytes with only loader_return_after 180->1800",\n      g[cmd_off:cmd_off + cmd_sz] == cmdline_file)')
src = src.replace('check("cmdline carries loader_return_after=180 and en0_addr=10.0.0.2",\n      cmd.count("loader_return_after=180") == 1 and cmd.count("en0_addr=10.0.0.2") == 1)',
                  'check("cmdline carries loader_return_after=1800 and en0_addr=10.0.0.2",\n      cmd.count("loader_return_after=1800") == 1 and cmd.count("en0_addr=10.0.0.2") == 1\n      and "loader_return_after=180 " not in cmd)')
src = src.replace('check("cmdline is 471 chars (the v18 budget, 471+110=581/607)", len(cmd) == 471)',
                  'check("cmdline is 472 chars (the v18 budget 471+110=581/607, +1 for 1800)", len(cmd) == 472)')
src = src.replace('e22["', 'e23["').replace('e22[', 'e23[')
src = src.replace('check("loader.efi is the Wave 26 maxvnodes build (0ade78b5), not the v21 carry",\n      e23["loader.efi"] != e21["loader.efi"] and sha(e23["loader.efi"]).startswith("0ade78b5"),',
                  'check("loader.efi == the v22 carry (0ade78b5, the maxvnodes build) byte for byte",\n      e23["loader.efi"] == e21["loader.efi"] and sha(e23["loader.efi"]).startswith("0ade78b5"),')
src = src.replace('check("kernel == the v21 kernel carried byte for byte (the passed kernel file)",\n      e23["kernel"] == kfile == e21["kernel"], f"sha256 {sha(e23[\'kernel\'])[:16]}")',
                  'check("kernel == the v21/v22 kernel carried byte for byte (the passed kernel file)",\n      e23["kernel"] == kfile == e21["kernel"], f"sha256 {sha(e23[\'kernel\'])[:16]}")')

open(r"wave26-scripts/verify-udon-hakios-v23.py", "w", encoding="utf-8", newline="\n").write(src)
print("written; remaining v22-isms:", len(re.findall(r"v22", src)))
