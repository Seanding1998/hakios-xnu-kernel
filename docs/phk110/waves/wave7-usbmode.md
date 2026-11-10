# Wave 7 — USB-mode grafted boot image (XnuLoaderMain graft + usb-mode payload)

Date: 2026-11-03. Scope: rebuild udon FD with the Wave-7 `BootManager.c` patch
(`XnuLoaderMain()` inserted at the tail of `PlatformBootManagerAfterConsole`,
before `DeviceBootManagerAfterConsole ()`, with PHK110 comment), package it with
the 66 KB usb-mode XNUP payload, verify, deliver. No phone touched.

## 1. Build environment fix (venv)

- Symptom (main agent): `~/hakios/uefi-udon/venv/bin/python3` does not exist —
  no venv was ever created inside `uefi-udon`.
- Resolution: reuse the **Wave-4-era venv** at `~/hakios/Mu-Silicium/venv`
  (python 3.14, `edk2-pytool` verified importable), passed as `PYTHON_COMMAND`.
- The upstream-generic `build_uefi.py` entry point was **not** used: it drives
  `Platforms/OnePlus/udonPkg/DeviceBuild.py` (Stuart) and does not know about the
  UniXNU package paths that the udon build needs. The Wave-4-proven wrapper
  `scripts/build-udon-firmware.sh` was used instead — it sets
  `WORKSPACE/PACKAGES_PATH` (incl. `unixnu-core/package`, DarwinBoot drivers,
  Mu_Basecore, Silicium, ACPI), copies BaseTools Conf templates and invokes the
  exact equivalent of `build -p Platforms/OnePlus/udonPkg/udon.dsc -a AARCH64
  -b DEBUG -t CLANGPDB -D FD_BASE=0xA7100000 -D FD_SIZE=0x400000
  -D FD_BLOCKS=0x400 -D DEVICE_MODEL=0 -D ENABLE_SECUREBOOT=0
  -D MEMORY_PROTECTION=TRUE …`.

Build command (WSL):

```sh
cd ~/hakios/uefi-udon
export UNIXNU_ROOT=$HOME/hakios/unixnu-core
export CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-
export PYTHON_COMMAND=$HOME/hakios/Mu-Silicium/venv/bin/python3
JOBS=$(nproc) ./scripts/build-udon-firmware.sh
```

## 2. Build output

- Build total time **00:00:34** (2026-11-03 14:11:14 → 14:11:48), no errors;
  only the pre-existing warnings from Wave 4 (SiliciumPkg.dsc.inc(211) library
  class, BaseTools VFR grammar).
- FV geometry: `FVMAIN 99% full 0x7b0000 total, 0x7af0a0 used` (Wave 4 was
  0x7AF008 — +0x98 from the graft call), `FVMAIN_COMPACT 31% full 0x400000`.
- Product: `~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`
  (4,194,304 B, `_FVH` @ 0x28).
  sha256 `8924cb67e349f7c188c258bde08fe90155d81a9d27ef5d0a965399ffb7a7180f`
  (Wave-5 FD was `de4df6ac…` → build is genuinely new).

### Patch-compiled-in proof

The outer FD is FVMAIN_COMPACT (LZMA-compressed inner FV), so plaintext greps
of the FD are meaningless; verification done on the build artifacts:

- `BootManager.c` mtime 14:07 (patch) < object mtimes 14:11 (this build):
  `BootManagerLib/OUTPUT/BootManager.obj`, `XnuLoader.obj`, `BootManagerLib.lib`
  all rebuilt.
- Symbol grep: `BootManager.obj` references `XnuLoaderMain` (1 hit),
  `XnuLoader.obj` defines it (2 hits), `BootManagerLib.lib` carries 5 hits.
- `PlatformBootManagerLib|SiliciumPkg/Library/BootManagerLib/BootManagerLib.inf`
  (`SiliciumPkg.dsc.inc:238`) links into **BdsDxe**; `BdsDxe.pdb` (rebuilt
  14:11) contains 3 `XnuLoaderMain` symbol hits → the graft call is linked into
  the dispatch path that runs before `DeviceBootManagerAfterConsole`.

## 3. Packaging

`wave4-scripts/package-udon-boot.py` (Wave-5 `--payload` extension) run in WSL:

```sh
cd <host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
python3 wave4-scripts/package-udon-boot.py \
  --fd       ~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --shim     device-layer/udon-hakios-BootShim.bin \
  --stock    device-layer/stock-boot-a.img \
  --payload  /tmp/wave7-payload-usb.bin \
  --out      device-layer/udon-hakios-usbmode-grafted.img \
  --unsigned-out /tmp/wave7-usbmode-unsigned.img \
  --report   /tmp/wave7-usbmode-grafted.report.json
```

All packager asserts passed (FD size 0x400000 + `_FVH`, shim header
`(0xA7100000, shim+fd)`, XNUP magic `0x50554E58` and `Size == len-8`,
gzip round-trip, footer/graft geometry, readback). Container: stock-aligned
Android boot v4, header page byte-copied from stock (only kernel_size
1,302,378 / ramdisk_size 0 rewritten), payload = gzip(shim 240 B + FD 4 MiB +
XNUP 66,216 B + pad), stock OEM vbmeta grafted + fresh AVBf footer, 192 MiB.

## 4. Verification

`wave5-scripts/verify-udon-hakios.py <img> <stock> <shim> <fd> <payload>` —
**14 PASS then expected stop** at the container-entry hard assertion. The
script asserts the Wave-5 kernel-container entry set
`{"loader.efi","kernel","ramdisk","cmdline","kernel.ver"}`; the Wave-7 usb-mode
container by design carries `{"loader.efi","usb","kernel.ver"}` and no
`cmdline` entry (loader v2 has built-in usb-mode defaults). Equivalent manual
checks were substituted for the remaining assertions.

| Check | Result |
|---|---|
| ANDROID! magic | PASS |
| header diff vs stock = kernel_size/ramdisk_size only (bytes 8–14) | PASS |
| kernel zero-padded to page | PASS |
| gunzip == shim+fd+payload(+pad), 4,260,768 B | PASS |
| shim text_offset 0xA7100000 / image_size 0x4000F0 / ARMd @0x38 | PASS |
| `_FVH` at shim+0x28; FD bytes equal source | PASS |
| XNUP magic / Size==len-8 / container byte-equal to source | PASS |
| entries == {loader.efi, usb, kernel.ver} (usb-mode form) | PASS (manual) |
| usb entry == `"1"` | PASS (manual) |
| loader.efi entry byte-equal `device-layer/udon-hakios-loader-v2.efi` | PASS (manual) |
| cmdline entry absent (v2 built-in defaults) | PASS (manual) |
| footer AVBf v1.0; orig==voff==content_end (1,306,624) | PASS |
| vbmeta size 2432 == stock bytes @stock footer offset | PASS |
| zero fill vbmeta→footer; final 192 MiB | PASS |

Total: 14 script + 10 manual = 24 checks, 0 unexpected failures.

## 5. Artifacts

| File | Bytes | sha256 |
|---|---|---|
| `device-layer/udon-hakios-usbmode-grafted.img` | 201,326,592 | `0fdd243724c4566390fc7bc3a35f6f67429a36d57f80f82fd909e3ab8d5123f6` |
| FD `SILICIUM_UEFI.fd` (build tree, not copied to device-layer) | 4,194,304 | `8924cb67e349f7c188c258bde08fe90155d81a9d27ef5d0a965399ffb7a7180f` |
| payload `/tmp/wave7-payload-usb.bin` | 66,216 | `859be7211a446a9654ff9a5f1416f4ef64f213f11f70ad30fc500dda39e2bfde` |
| shim `udon-hakios-BootShim.bin` (reused, Wave 5) | 240 | `108ce972adb82cc9c23967a1d380a27a67ef73a7c131f117561e38e261fa58ba` |
| loader `udon-hakios-loader-v2.efi` (embedded in payload) | 66,048 | `63e51e0770286711c3d56e0d9bf79f2f50dbbd07c084b6c74a7fd6cc960e5b51` |

New files on Windows device-layer: only `udon-hakios-usbmode-grafted.img`.
Note: `/tmp/wave7-payload-usb.bin` lives in WSL tmp — re-create it with
`mkpayload.py -o /tmp/wave7-payload-usb.bin --usb loader.efi=…/udon-hakios-loader-v2.efi`
if the machine reboots before flashing.

## 6. Flash instructions

```sh
fastboot flash boot_b device-layer/udon-hakios-usbmode-grafted.img
fastboot set_active b
fastboot reboot
```

Expected boot chain:

1. ABL splash (stock vbmeta grafted, AVB green/red as in Wave 5).
2. UEFI starts, console up, `PlatformBootManagerAfterConsole` runs →
   **no Boot Manager menu**: the graft calls `XnuLoaderMain()` directly and
   never reaches `DeviceBootManagerAfterConsole ()`.
3. XNULOADER banner on serial/screen, loader v2 sees `usb=1` in its XNUP
   container → **USB command server, resident** (no kernel load, no reset
   loop as in earlier waves).
4. Host side: `usbipd` should enumerate the loader USB gadget — attach from
   Windows and drive the command protocol.
