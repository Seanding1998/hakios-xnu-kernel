# Wave 5 — HakiOS payload grafted into the udonPkg UEFI base (`udon-hakios-grafted.img`)

Date: 2026-11-02. Agent: Wave 5 (no device access; flashing is done by the main agent).
Goal: make the hardware-proven takasugl/uefi-udon (udonPkg, Wave 4) UEFI launch the
HakiOS XNUP payload (loader.efi + hakios-kernel + hello) instead of sitting at its
no-payload state.

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-grafted.img` | 201,326,592 B (192 MiB) | `7b97f1e3e74275d3d6f808b55dffe057d0ed79da1461a1f7e9eb86530722f971` |
| Raw UEFI FD (wave 5 build) | `udon-hakios-SILICIUM_UEFI.fd` | 4,194,304 B | `de4df6ac27279303672fc4f422524e01781a74eaaac9318cd732ba70ce2eb067` |
| BootShim.bin (PAYLOAD_BASE=0xF4000000, 240 B) | `udon-hakios-BootShim.bin` | 240 B | `108ce972adb82cc9c23967a1d380a27a67ef73a7c131f117561e38e261fa58ba` |
| XNUP payload container | `udon-hakios-payload.bin` | 14,924,392 B | `a3a7e26897f711002b60d499e2520d520aa1929cb13f4ae7b5a86782d342afb3` |
| loader.efi (stage 1, PAYLOAD_BASE=0xF4000000) | `udon-hakios-loader.efi` | 66,048 B | `7eff1605f5c455ffedcb3bc9d60cf180590879dbc7df420bf70d74d346612af4` |
| Packaging/verification report | `udon-hakios-grafted.report.json` | — | — |

Intermediate (WSL `/tmp/wave5/`): gzip(BootShim+FD+XNUP) = 6,762,817 B
(`173be84b250e8157684fee857501baab9fe26c793260c3b3b3d7ac9e78073bf6`),
pre-graft unsigned v4 container = 6,770,688 B, decompressed FvMain sha256
`5dc409e1bb96dde5c81b49178a344cd1b3425a2f086a3c537bc4ae667b16056e`.

## 1. Fusion plan (what was merged where)

The two trees share the Silicium lineage, so the HakiOS overlay
(`hakios.patch` against Mu-Silicium BASE e51cd87) maps almost 1:1 onto uefi-udon:

| hakios.patch hunk | uefi-udon counterpart | Action |
| --- | --- | --- |
| `BootShim/BootShim.S` XNUP copy block (`#ifdef PAYLOAD_BASE`) | `BootShim/BootShim.S` (same structure, same insert point after `_CopyLoop`) | **verbatim port** of the block, `#ifdef`-guarded → udon default (no payload copy) preserved |
| `BootManagerLib/BootManager.c` `XnuLoaderMain ();` at top of `PlatformBootManagerUnableToBoot` | same file exists at `Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/` (not overridden by udon.dsc/Palima/Qcom) | **same 2-line hook** |
| `BootManagerLib/BootManagerLib.inf` +XnuLoader.c +BaseLib/BaseMemoryLib +BlockIo/PartitionInfo protocols | same INF (FILE_GUID identical DF8F3324-…) | **same additions** |
| `files/…/XnuLoader.c/h` (stage-0 diagnostics + `StartPayloadLoader`) | new files in the same dir | **ported**, `XNU_PAYLOAD_BASE` `#ifndef`-guarded, default **0xF4000000** |
| Sec.c banner + `PcdFirmwareVendor|L"HakiOS"` | udon has its own branding (`BUILDID_STRING=udon-research`, Realme SMBIOS strings) | **not applied** (kept udon identity; cosmetic) |
| — | `Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c` (udon-specific, no hakios counterpart) | **+1 row**: `{"XNU Payload", 0xF4000000, 0x04000000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN}` |

### Payload base = 0xF4000000 (design decision 1, implemented)

udon's verified map: `TZApps Reserved 0xEA000000+0x07400000` ends at **0xF1400000**;
`DXE Heap` starts at **0xF8000000** → 104 MB gap. 0xF4000000..0xF7FFFFFF sits exactly
inside it (ends flush with the heap). The MemoryMapLib row marks it reserved +
WRITE_BACK_XN so UEFI (a) never allocates over the payload and (b) maps it cacheable,
which makes the shim's MMU-off writes coherent for the later UEFI-stage reads.

### Why the boot reaches the loader (BDS fall-through, verified)

udon's `MsBootOptionsLib` registers "Internal Storage"/"USB Storage" only when an FV
file carries the `gMsBootPolicyFileGuid` section, plus hidden FFU/Mass-Storage options.
Verified in the built FvMain: **0** occurrences of the MsBootPolicy GUID section, no
SsdApp/UsbApp → **zero active boot options** → after the volume-up countdown BdsEntry
falls into `PlatformBootManagerUnableToBoot` → `XnuLoaderMain()`. (`BootManagerMenuApp`
and `UFPLoader` are present but only reachable via volume-up / hidden options.)
udonPkg's `LinuxBootDxe` (boots a PE from the `logdump` partition) only fires on the
ReadyToBoot event, which is never signaled when no option boots — and ASCII loader logs
in `logdump` are not PE images — so it stays dormant.

## 2. File-level changes (all in WSL `~/hakios/uefi-udon`, base 475f9de)

`git diff --stat`: 4 files changed, 31 insertions(+); plus new `XnuLoader.c` (305 lines)
and `XnuLoader.h` (39 lines) from `upstream/hakios-uefi/files/…` (CRLF→LF, base
parameterized). Applied by `wave5-scripts/apply-wave5-fusion.py` (idempotent,
anchor-checked, EOL-preserving; an earlier anchor bug — `ldr x5, =FD_BASE` appears
twice in the udon shim — was caught and fixed before any bad edit was saved).

1. `BootShim/BootShim.S` — +21 lines, byte-identical to hakios.patch hunk 1:
   after the FD copy loop, if the word at `x4` (just past the FD) is "XNUP", copy
   `Size` (rounded up to 16, +header) to `PAYLOAD_BASE`; `#ifdef PAYLOAD_BASE`.
2. `Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/BootManager.c` —
   `#include "XnuLoader.h"` + `XnuLoaderMain ();` as the first statement of
   `PlatformBootManagerUnableToBoot` (exact hakios.patch wording).
3. `…/BootManagerLib.inf` — +XnuLoader.c source, +BaseLib/+BaseMemoryLib,
   +`gEfiBlockIoProtocolGuid`/`gEfiPartitionInfoProtocolGuid`.
4. `…/XnuLoader.h` (new) — `#ifndef XNU_PAYLOAD_BASE` → `0xF4000000ULL`,
   `XNU_PAYLOAD_MAX_SIZE 0x04000000ULL`, magic/entry structs, `XnuLoaderMain()`.
5. `…/XnuLoader.c` (new) — verbatim HakiOS stage-0 (collects cpu/display/memmap/payload
   diagnostics → `logdump`; `StartPayloadLoader()` LoadImage+StartImage's the
   `"loader.efi"` entry from the container; cold-reset fallback).
6. `Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c` — +1 row
   (see §1), inserted in address order between TZApps Reserved and DXE Heap.

Revert = `git checkout -- . && rm XnuLoader.c XnuLoader.h` in that tree (original
udon behavior, e.g. the wave-4 no-payload image, rebuilds unchanged).

## 3. Build steps and outputs

```
# loader.efi (WSL ~/hakios/kernel/xnuloader, build.sh env passthrough from wave 3)
PAYLOAD_BASE=0xF4000000 ./build.sh            # 66,048 B
#   verified: disasm diff vs previous binary — movz w8,#0xf400,lsl#16 (0xF4000000)
#   replaces #0xf000 (0xF0000000); rest = linker jitter only

# XNUP container (WSL ~/hakios/kernel)
python3 xnuloader/mkpayload.py -o /tmp/wave5/xnup-payload.bin \
    loader.efi=/tmp/wave5/loader.efi kernel=hakios-kernel ramdisk=userland/hello \
    --cmdline "serial=0 loader_return_after=20 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 \
     soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 \
     soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws"
#   14,924,392 B; entries loader.efi/kernel/ramdisk/cmdline(231 B)/kernel.ver
#   (wave-3 minimal cmdline set; loader auto-adds debug=0x8 cpus=1 rd=md0)

# UEFI FD (WSL ~/hakios/uefi-udon)
export UNIXNU_ROOT=$HOME/hakios/unixnu-core
JOBS=$(nproc) ./scripts/build-udon-firmware.sh     # 29 s incremental
#   Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd  (4 MiB)
#   XnuLoader.obj compiled from the new source; strings "loader.efi",
#   "XNULOADER LOG v1" present in the linked BdsDxe.efi (module that consumes
#   PlatformBootManagerLib). FvMain = 8,060,936 B, 108 FFS files (same count as wave 4),
#   contains SimpleFbDxe/DarwinBoot/UniXNU + "XNU Payload" MemoryMapLib string.

# BootShim (WSL ~/hakios/uefi-udon/BootShim)
rm -f BootShim.elf BootShim.bin
make REQUIRES_KERNEL_HEADER=1 FD_BASE=0xA7100000 FD_SIZE=0x400000 \
     'CFLAGS=--target=aarch64-linux-gnu -DPAYLOAD_BASE=0xF4000000'
#   240 B (wave 4: 192 B + 48 B XNUP block); disasm: mov x5,#0xf4000000 (d2be8005),
#   header text_offset=0xA7100000, image_size=0x4000F0 (=240+0x400000, shim+FD only
#   by design — the payload tail is described by the XNUP header, not image_size)

# packaging (extended wave-4 script)
python3 wave4-scripts/package-udon-boot.py --fd … --shim … --payload /tmp/wave5/xnup-payload.bin \
    --stock device-layer/stock-boot-a.img --out device-layer/udon-hakios-grafted.img \
    --unsigned-out /tmp/wave5/udon-hakios-unsigned.img --report device-layer/udon-hakios-grafted.report.json
```

`wave4-scripts/package-udon-boot.py` was extended (payload optional, wave-4 invocation
still valid): `--payload XNUP` asserts magic 0x50554E58 / Size==len-8 / ≤ 0x3FFF000,
appends shim+FD+payload and pads the blob to 16 bytes (mkxnuimg.py semantics), verifies
payload magic at offset shim+FD and the zero padding on readback, and reports
payload/combined hashes. Post-build `scripts/check-udon-platform.py` → "Udon UEFI check
passed".

## 4. Independent verification (wave5-scripts/verify-udon-hakios.py — 21/21 PASS)

- header diff vs stock = bytes 8..14 only (kernel_size 6,762,817 / ramdisk_size 0);
  kernel zero-padded to pages; content end = 6,770,688 = footer orig_size = vbmeta_offset.
- gzip round-trip == shim+FD+XNUP(+8 B pad) = 19,118,944 B; shim header
  (0xA7100000, 0x4000F0, "ARMd"@0x38); `_FVH` at decompressed[shim+0x28].
- XNUP magic/Size at decompressed[shim+FD], container byte-equal to the source file,
  entries {loader.efi 66,048 / kernel 14,841,368 / ramdisk 16,528 / cmdline 231 /
  kernel.ver 48}, cmdline carries serial=0 + loader_return_after=20.
- Stock OEM vbmeta (2,432 B, sha 25314ab1…) byte-identical at the graft offset;
  fresh AVBf v1.0 footer; everything after vbmeta zero; final size 192 MiB.
- Shim `mov x5, #0xf4000000` in BootShim.bin disassembly; loader.efi
  `movz w8,#0xf400,lsl#16`; FD `_FVH` present.

## 5. Flashing instructions for the main agent

```sh
# device in fastboot/bootloader mode (BL unlocked), stock vendor_boot_b must remain installed
fastboot flash boot_b device-layer/udon-hakios-grafted.img
fastboot set_active b
fastboot reboot
```

- Same graft pattern as the hardware-proven wave-4 image (stock OEM vbmeta + fresh
  footer, full 192 MiB). Do NOT touch vbmeta/vendor_boot/dtbo.
- Restore any time: `fastboot flash boot_b backups-slotb/backup-boot_b.img`
  (wave-4 image is also still on disk as `device-layer/udon-uefi-grafted.img`).

### Expected on screen (timeline)

1. ABL splash → Silicium/udon UEFI boots (SimpleFb picture, as wave 4), "[Volume Up]
   Boot Manager" countdown at the bottom (~3 s, ignorable).
2. No bootable option → `XnuLoaderMain()` → payload found at 0xF4000000 →
   `loader.efi` banner: `== XNULOADER v3 ==`, `kernel.ver=…`, `payload base=F4000000
   magic=50554e58` (screen console; `display 1240 x 2772` line is the V-1 check).
3. Kernel verbose log scrolls on screen (`debug=0x8`), then `userland/hello` under the
   mockfs root.
4. After **20 s** (`loader_return_after=20`) the kernel returns to loader.efi, the
   loader writes its log to the `logdump` partition (`log: N bytes written to
   logdump`, else `NOT WRITTEN` on screen), and resets.

### IMPORTANT deviation from the task's "20s 后自动回 fastboot" expectation

The loader has no reboot-to-fastboot mechanism (no OPPO reboot-reason write), and after
a cold reset the active slot is still **b** → the device re-runs this same image:
**the demo cycles** (splash → banner → kernel 20 s → reset → …). It never returns to
Android on its own and never sits in fastboot. The cycle is harmless (only `logdump`
gets written), but recovery requires the main agent to put the device back in fastboot
(hold Vol- / power-cycle into bootloader) and reflash `backups-slotb/backup-boot_b.img`
(or re-flash `udon-uefi-grafted.img`). If a one-shot run is preferred, keep slot A
active and `fastboot boot` from RAM is not possible for this image size — so flash
slot_b, observe one cycle, then restore.

### Log readback

```sh
adb shell su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/logdump.bin'
adb pull /data/local/tmp/logdump.bin
# look for: payload base=0xF4000000 magic=50554e58; memmap window 0xF4000000 reserved;
# "log: N bytes written to logdump"; kernel log tail after the 20 s return
```

## 6. Residual risks / open items

1. **First hardware run of this exact chain**: the shim XNUP copy and the
   UnableToBoot→XnuLoaderMain hook follow the wave-3 design but were never executed on
   PHK110 hardware before this image; wave 4 proved only the shim→FD part. All
   constants re-verified statically (§4).
2. **loader platform table still lacks SM8475** (wave-3 risk 1, unchanged): PLAT falls
   to qemu-virt — banner/log-on-screen still works via the framebuffer path, but SoC
   drivers (cpufreq/thermal/socinfo/pmic) will not attach, and `cpus=8 bootcpu=7` is
   intentionally absent (loader defaults `cpus=1`, single core, PSCI geometry of the
   wrong platform). Fix belongs to the kernel repo (add platform_phk110 + select by
   SCREEN.base==0xB8000000), then re-run only §3 loader+payload+package steps.
3. `logdump` gets overwritten by loader logs (OPPO log partition; same as wave-3 plan).
4. DEBUG build retained (wave-4 convention); FD fits its 4 MiB region with the added
   XnuLoader (~3 KB text).
5. UniXNU menu/payload path is dormant (no ESP/payload FAT in `super` needed anymore);
   the udon tree's UniXNU modules remain in the FD untouched for revertibility.
6. Wave-4's `udon-uefi-grafted.img` (no payload) and `udon-hakios-grafted.img` now
   differ only by: FD BootManagerLib/MemoryMapLib changes, shim 240 B with payload
   copy, and the 14.9 MB XNUP tail in the gzip.

## 7. Reproducing from scratch

```sh
wsl -d FedoraLinux-44
python3 /mnt/c/…/hakios-phk110/wave5-scripts/apply-wave5-fusion.py ~/hakios/uefi-udon \
        /mnt/c/…/hakios-phk110/upstream/hakios-uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib
# then the §3 command block (build loader → payload → FD → shim → package → verify)
python3 /mnt/c/…/hakios-phk110/wave5-scripts/verify-udon-hakios.py device-layer/udon-hakios-grafted.img \
        device-layer/stock-boot-a.img /tmp/wave5/BootShim.bin \
        ~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd /tmp/wave5/xnup-payload.bin
```
