#!/usr/bin/env python3
"""Wave 5 fusion: graft the HakiOS payload-boot path into the uefi-udon tree.

Edits (run inside WSL against ~/hakios/uefi-udon):
  1. BootShim/BootShim.S            - XNUP payload copy block (#ifdef PAYLOAD_BASE, hakios.patch hunk 1 verbatim)
  2. Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManager.c
                                    - XnuLoaderMain() at the top of PlatformBootManagerUnableToBoot (hakios.patch)
  3. Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManagerLib.inf
                                    - XnuLoader.c source + BaseLib/BaseMemoryLib + BlockIo/PartitionInfo protocols
  4. Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.{c,h}
                                    - ported from HakiOS (files/), PAYLOAD_BASE default 0xF4000000 (#ifndef-guarded)
  5. Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c
                                    - "XNU Payload" 0xF4000000/0x04000000 reserved region

All insertions are idempotent (skipped when the marker is already present) and
every edit aborts the run if its anchor text is not found exactly once.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "hakios/uefi-udon")
UPSTREAM = Path(sys.argv[2])  # .../upstream/hakios-uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib
PAYLOAD_BASE = "0xF4000000"

def load(p: Path) -> str:
    return p.read_text(newline="")  # keep exact line endings (mixed: EDK2 files CRLF, shim LF)

def eol_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"

def save(p: Path, s: str) -> None:
    p.write_text(s, newline="")

def insert_once(text: str, marker: str, addition: str, what: str) -> str:
    if addition.strip() in text:
        print(f"  = {what}: already present, skipped")
        return text
    n = text.count(marker)
    if n != 1:
        sys.exit(f"FAIL {what}: anchor found {n} times (expected 1)")
    print(f"  + {what}")
    return text.replace(marker, addition)

# ---------------------------------------------------------------- 1. BootShim.S
p = ROOT / "BootShim/BootShim.S"
s = load(p)
block = (
    "\n"
    "#ifdef PAYLOAD_BASE\n"
    "  /* x4 now points just past the FD: an optional \"XNUP\" payload may follow */\n"
    "  ldr   w2, [x4]\n"
    "  movz  w3, #0x4E58\n"
    "  movk  w3, #0x5055, lsl #16\n"
    "  cmp   w2, w3\n"
    "  b.ne  _NoPayload\n"
    "  ldr   w6, [x4, #4]    /* Payload Size */\n"
    "  add   x6, x6, #23     /* Header + Round Up to 16 */\n"
    "  and   x6, x6, #~15\n"
    "  movz  x5, #(PAYLOAD_BASE >> 16), lsl #16\n"
    "\n"
    "_PayloadLoop:\n"
    "  ldp   x2, x3, [x4], #16\n"
    "  stp   x2, x3, [x5], #16\n"
    "  subs  x6, x6, #16\n"
    "  b.ne  _PayloadLoop\n"
    "\n"
    "_NoPayload:\n"
    "#endif\n"
)
s = insert_once(s, "  b.ne  _CopyLoop\n", "  b.ne  _CopyLoop\n" + block,
                "BootShim.S XNUP copy block")
save(p, s)

# ------------------------------------------------- 2. BootManager.c (CRLF file)
p = ROOT / "Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManager.c"
s = load(p)
EOL = eol_of(s)
s = insert_once(
    s,
    f'#include "BootManager.h"{EOL}',
    f'#include "BootManager.h"{EOL}#include "XnuLoader.h"{EOL}',
    "BootManager.c XnuLoader.h include",
)
hook = (
    f"  // Nothing else to boot: hand over to the XNU loader (does not return){EOL}"
    f"  XnuLoaderMain ();{EOL}{EOL}"
)
s = insert_once(
    s,
    f"  // Execute Secondary Unable To Boot{EOL}",
    hook + f"  // Execute Secondary Unable To Boot{EOL}",
    "BootManager.c XnuLoaderMain() hook in PlatformBootManagerUnableToBoot",
)
save(p, s)

# ------------------------------------------------- 3. BootManagerLib.inf (CRLF file)
p = ROOT / "Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManagerLib.inf"
s = load(p)
EOL = eol_of(s)
s = insert_once(
    s, f"[Sources]{EOL}  BootManager.c{EOL}", f"[Sources]{EOL}  BootManager.c{EOL}  XnuLoader.c{EOL}",
    "BootManagerLib.inf XnuLoader.c source",
)
s = insert_once(
    s, f"  DevicePathLib{EOL}  PrintLib{EOL}",
    f"  DevicePathLib{EOL}  PrintLib{EOL}  BaseLib{EOL}  BaseMemoryLib{EOL}",
    "BootManagerLib.inf BaseLib/BaseMemoryLib",
)
s = insert_once(
    s,
    f"  gEfiSimpleTextInputExProtocolGuid{EOL}",
    f"  gEfiSimpleTextInputExProtocolGuid{EOL}  gEfiBlockIoProtocolGuid{EOL}  gEfiPartitionInfoProtocolGuid{EOL}",
    "BootManagerLib.inf BlockIo/PartitionInfo protocols",
)
save(p, s)

# ------------------------------------------------- 4. XnuLoader.c / XnuLoader.h
bm = ROOT / "Silicon/Silicium/SiliciumPkg/Library/BootManagerLib"
c_src = (UPSTREAM / "XnuLoader.c").read_text(newline="")
h_src = (UPSTREAM / "XnuLoader.h").read_text(newline="")
# normalize to LF for tree consistency
c_src = c_src.replace("\r\n", "\n")
h_src = h_src.replace("\r\n", "\n")
# parameterize the payload base (udon window: 0xF4000000, inside the 0xF1400000-0xF8000000 gap)
old_h = (
    "// The boot shim copies everything appended after the UEFI FD to this address.\n"
    "// The region is marked reserved in the device memory map.\n"
    "//\n"
    "#define XNU_PAYLOAD_BASE      0xF0000000ULL\n"
    "#define XNU_PAYLOAD_MAX_SIZE  0x04000000ULL\n"
)
new_h = (
    "// The boot shim copies everything appended after the UEFI FD to this address\n"
    "// (wave 5: udon window 0xF4000000..0xF7FFFFFF, inside the verified\n"
    "// 0xF1400000-0xF8000000 gap of udonPkg's memory map). The region is marked\n"
    "// reserved in the device memory map (MemoryMapLib \"XNU Payload\").\n"
    "//\n"
    "#ifndef XNU_PAYLOAD_BASE\n"
    f"#define XNU_PAYLOAD_BASE      {PAYLOAD_BASE}ULL\n"
    "#endif\n"
    "#define XNU_PAYLOAD_MAX_SIZE  0x04000000ULL\n"
)
if old_h not in h_src:
    if new_h in h_src:
        print("  = XnuLoader.h payload base: already patched, skipped")
    else:
        sys.exit("FAIL XnuLoader.h: PAYLOAD_BASE block anchor not found")
else:
    h_src = h_src.replace(old_h, new_h)
    print("  + XnuLoader.h payload base -> " + PAYLOAD_BASE)
(bm / "XnuLoader.c").write_text(c_src, newline="")
(bm / "XnuLoader.h").write_text(h_src, newline="")
print("  + XnuLoader.c / XnuLoader.h written")

# ------------------------------------------------- 5. MemoryMapLib.c
p = ROOT / "Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c"
s = load(p)
EOL = eol_of(s)
row = f'  {{"XNU Payload",         0xF4000000, 0x04000000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN}},{EOL}'
tz = '  {"TZApps Reserved",     0xEA000000, 0x07400000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},'
s = insert_once(s, tz + EOL, tz + EOL + row, "MemoryMapLib.c XNU Payload region")
save(p, s)

print("wave5 fusion edits applied OK")
