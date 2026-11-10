# 阶段 4 · 2026-11-02 · uefi-udon（udonPkg）完整重建与 boot 镜像封装

Date: 2026-11-02. Agent: 阶段 4 (no device access; flashing is done by the main agent).
Goal: rebuild the proven takasugl/uefi-udon SM8475 platform package end-to-end in WSL and
produce a flashable `boot_b` image (`udon-uefi-grafted.img`) for the OnePlus Ace 2 (PHK110).

## Result summary

| Artifact | Path (Windows) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `device-layer/udon-uefi-grafted.img` | 201,326,592 B (192 MiB) | `3eee4e1d4ce9986c4b367399cfd88c1da7b832894f09cb107ac15a6c4d08f346` |
| Raw UEFI FD | `device-layer/udon-SILICIUM_UEFI.fd` | 4,194,304 B (0x400000) | `86c9ead0c766fecc709e1b0d8fcc3a56ba6a86e12101783c2264ab528522b38c` |
| Packaging/verification report | `device-layer/udon-uefi-grafted.report.json` | — | — |
| BootShim.bin (FD_BASE=0xA7100000, FD_SIZE=0x400000, kernel header) | WSL `~/hakios/uefi-udon/BootShim/BootShim.bin` | 192 B | `701786eaa31d908757da5f2d6a719a16acebed8de92715cb804bd592eec6017d` |
| gzip(BootShim+FD) ("kernel") | inside container | 1,270,378 B | `027fc77c5e3e289ae09194c2f73031b4e199315505e5c6b286de0957984d7f22` |
| Pre-graft v4 container (unsigned) | WSL `/tmp/wave4/udon-uefi-unsigned.img` | 1,277,952 B | `51807e814d6fe2dea7df1468a7796dc6e74314914ce48112c2d65ab16df358b8` |
| Stock OEM vbmeta (byte-copied) | from `device-layer/stock-boot-a.img` @ 0x2F49000 | 2,432 B | `25314ab1cd5d69cd52fc3aef2fe3793e1c153da34c7653c773b67e29e3e81f17` |

Upstream FD reference: REPRODUCE.md documents `08e52705…` for the author's own build with
their private `Binaries/udon`; "Different compilers or submodule revisions can change the
hash" — our hash differs for exactly that reason (see Binaries provenance below).

## 1. Repository bootstrap (WSL FedoraLinux-44)

```sh
git clone --depth 1 https://github.com/takasugl/uefi-udon ~/hakios/uefi-udon
cd ~/hakios/uefi-udon
git submodule update --init --depth 1            # Binaries, Common/Mu, Mu_OEM_Sample,
                                                 # Mu_Basecore, Silicium-ACPI, openssl
git -C Mu_Basecore submodule update --init --depth 1   # nested: mipisyst, brotli x2,
                                                 # libfdt, oniguruma, libspdm, cmocka,
                                                 # googletest, subhook  (build fails
                                                 # without mipisyst/brotli)
```

- uefi-udon HEAD `475f9de` ("docs: link the companion device repository"),
  Binaries submodule @ `a1501e0c2e642d6ac0d8f52c85af2a67b75a7799`.
- `python3 scripts/check-udon-platform.py` → "Udon UEFI check passed" (run before and
  after the build).

## 2. UniXNU dependency (needed by udon.dsc: UniXNUPkg + DarwinBootPkg)

```sh
git clone --depth 1 https://github.com/takasugl/UniXNU-udon ~/hakios/unixnu-udon
git clone https://github.com/UniXNU/UniXNU.git ~/hakios/unixnu-core
cd ~/hakios/unixnu-udon && ./scripts/bootstrap-core.sh ~/hakios/unixnu-core
# pins UniXNU @ 0597c81b4d571f4706f7bbcf03ca51fe5b6e868b, NativeUfs @ 04b748e6…,
# applies UniXNU-core-changes.patch + NativeUfs.patch
cd ~/hakios/unixnu-core && git submodule update --init --depth 1 drivers/DarwinBoot
# DarwinBoot @ 12bc9e23fb5f9a7d2715a9e30c021a883db0a310 (only submodule the UEFI build needs)
```

Note: the UniXNU *payload/kernel/XNU* side (IPSW, userdata image) was NOT built — it is
not required to produce the UEFI firmware; `UniXNU.efi`/`UniXNUDxe` in the FD are the
launcher/driver and read their payload from the FAT volume in `super` at runtime.

## 3. Binaries/udon — extraction attempt and decision (the important part)

Task assumed `intel/phk110-abl-a.bin` contains an extractable vendor DXE module set.
**It does not.** Verified thoroughly:

- abl_a FV @ 0x1000: single FVMAIN_COMPACT file (`9E21FD93-…`), LZMA GUIDED section
  (`EE4E5898-…`, data 0x2DBD0 B → 0xC80C8 B decompressed).
- Inner FV (0xC80C0 B) contains exactly ONE file: `LinuxLoader`
  (APPLICATION, `F536D559-459F-48FA-8BBC-43B554ECAE8D`, PE32 0xC8000 B) — this is the
  Qualcomm ABL application itself. No other FFS files, no embedded FVs, no LZMA/gzip
  blobs inside the PE, and no `.dll` build-path strings / driver names
  (UFSDxe/ClockDxe/PmicDxe/OplusProject/OGaugeAuth/nt37705 … all NOT FOUND).
- `phk110-xbl-a.bin` (6 MB) / `phk110-xblcfg-a.bin`: no `_FVH`, no readable module
  strings → OPPO sec-boot encrypted (matches wave-2 finding).
- UEFIReader (`<host>/AppData/Local/Temp/UEFIReader/.../UEFIReader.exe`,
  `DOTNET_ROLL_FORWARD=LatestMajor`) reproduces this: original run and a manual run on
  the decompressed inner FV both yield only LinuxLoader (the latter via
  BadImageFormatException on an unsupported FFS type — a robustness limitation, not
  missing data; our own FV walker confirms the volume is exhausted).
- Consequence: on PHK110 the Qualcomm UEFI DXE drivers live in the encrypted XBL, so a
  "real PHK110 module extraction" from user-accessible partitions is impossible — the
  same situation the upstream author documented ("The source tree is complete, but the
  PHK110 vendor modules are external inputs", docs/REPRODUCE.md).

Decision (recorded per task instruction (c) "same-silicon modules may be substituted"):

> **`Binaries/udon` = verbatim copy of `Binaries/senna_bc`** from the public
> Device-Binaries submodule @ a1501e0c (Realme GT Neo 5, **SM8475**, same silicon,
> same Oplus/BBK family: includes `OcdtDxe/OplusProject` and `OGaugeAuthDxe/OGaugeAuth`
> that udonPkg's DXE.inc requires, plus the standard community bring-up patches
> ButtonsDxe/ClockDxe/PmicDxe/TzDxeLA/UFSDxe/UsbConfigDxe/UsbMsdDxe — INFs reference
> the `.patched.efi` variants). Rationale: udonPkg is a port of the SM8475 senna_bc
> template; the senna_bc set contains **all 53 modules** udonPkg references
> (checked INF+EFI for each) plus `RawFiles/{SecParti.cfg,uefipil.cfg,QcomChargerCfg.cfg}`;
> the panel XML RAW files are not needed because `USE_CUSTOM_DISPLAY_DRIVER=0` keeps
> vendor DisplayDxe/CPRDxe out and SimpleFbDxe drives the ABL splash buffer.
> This also mirrors what the upstream project did (their udonPkg is "derived from the
> SM8475 senna_bc platform", docs/STATUS.md).

Also relevant: wave-3's `~/hakios/kernel/Mu-Silicium/Binaries/phk110` is a copy of
**ingres** (Xiaomi Poco F4 GT) binaries — Xiaomi, not Oplus — one more reason the old
phk110Pkg graft path died. Provenance README + per-file sha256 manifest written to
`Binaries/udon/README.md` / `Binaries/udon/manifest.sha256` (337 files, 9.4 MB).

Extraction workproducts kept for the record:
- `intel/wave4-abl-extract/` — UEFIReader run dir, `abl-fvmain-inner.fv` (decompressed),
  `fvextract.py` (our robust FFS/section walker), `udon-readme.md` (copy source).

## 4. Build

```sh
export UNIXNU_ROOT=$HOME/hakios/unixnu-core
cd ~/hakios/uefi-udon && JOBS=$(nproc) ./scripts/build-udon-firmware.sh
# → BaseTools C build (first run needed the brotli/mipisyst submodules above)
# → build -p Platforms/OnePlus/udonPkg/udon.dsc -a AARCH64 -b DEBUG -t CLANGPDB \
#     -D FD_BASE=0xA7100000 -D FD_SIZE=0x400000 -D FD_BLOCKS=0x400 \
#     -D DEVICE_MODEL=0 -D ENABLE_SECUREBOOT=0 -D MEMORY_PROTECTION=TRUE ...
```

Build time ~35 s on this machine (most DXEs are prebuilt binaries). Warnings: one
pre-existing `SiliciumPkg.dsc.inc(211)` library-class warning; VFR grammar warnings in
BaseTools; no errors.

Output: `Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` (0x400000, `_FVH` @ 0x28).
FVMAIN_COMPACT decompresses to a 0x7AF008-byte FvMain with **108 files**; UI names
confirm the required content is embedded: all Binaries/udon drivers, `SimpleFbDxe`,
`DarwinBoot`, `ShengBootMemoryDxe`, `UniXNU`, `UniXNUDxe`, `SmBiosTableDxe`,
`DtPlatformDxe` + `DeviceTreeBlob` (udon-test.dtb), `LinuxBootDxe`, `IortDtDxe`, RAW
files `SecParti.cfg`/`uefipil.cfg`/`QcomChargerCfg.cfg`, plus Silicium common extras
(UFPLoader, BootManagerMenuApp, …). `MemoryMapLib` carries the proven
`Kernel 0xA8000000/0x10000000` and `MTE Reserved 0xC0000000/0x20000000` reservations.

## 5. BootShim

```sh
cd ~/hakios/uefi-udon/BootShim
make REQUIRES_KERNEL_HEADER=1 FD_BASE=0xA7100000 FD_SIZE=0x400000   # clang+llvm-objcopy
```

192 B binary; header convention verified: `decompressed[8:24] == (0xA7100000, 192+0x400000)`
(arm64 Image header: text_offset=FD base, image_size=shim+FD), `ARMd` magic at 0x38 —
matches `BootShim.S` and the udon.toml `requires_kernel_header = true` convention.

## 6. Packaging + AVB graft

New durable script: **`wave4-scripts/package-udon-boot.py`** (modelled on UniXNU-udon
`scripts/package-sheng-boot-v4.py` + `package/linux-log/graft-boot-footer.py`).

```sh
python3 wave4-scripts/package-udon-boot.py \
  --fd  ~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --shim ~/hakios/uefi-udon/BootShim/BootShim.bin \
  --stock device-layer/stock-boot-a.img \
  --out  device-layer/udon-uefi-grafted.img \
  --unsigned-out /tmp/wave4/udon-uefi-unsigned.img \
  --report device-layer/udon-uefi-grafted.report.json
```

Container shape (the proven UniXNU-udon boot_v4 form):
- Header = stock `stock-boot-a.img` header page byte-for-byte (v4, page 4096,
  header_size 1584, os_version 0x180001a8, reserved, cmdline, boot-signature words),
  **only `kernel_size` (offset 8) and `ramdisk_size` (offset 12) rewritten** —
  `kernel_size` = 1,270,378 (gzip), `ramdisk_size` = 0.
  *Documented deviation from the task text* ("只改 kernel_size"): stock ramdisk_size
  is 1,455,342 but we ship no ramdisk pages, so a verbatim copy would describe a
  ramdisk that does not exist in the container; zeroing it keeps the image
  self-consistent for ABL's page-walking. Same spirit as the upstream v4 packager
  (which kept stock values only because sheng's stock ramdisk_size was already 0).
- kernel = gzip(BootShim + FD) at page 1, zero-padded to 4096 → payload end 1,277,952.
- **No DTB** — ABL applies its runtime memory fixups to the vendor_boot DTB (stock
  `vendor_boot_b` must remain installed; backups exist in `backups-slotb/`).
- Graft: stock OEM vbmeta (2,432 B, byte-identical, sha 25314ab1…) copied at
  offset 1,277,952; fresh 64-byte AVBf footer at the end of a full 192 MiB buffer:
  `orig_size = vbmeta_offset = 1,277,952`, `vbmeta_size = 2,432` (identical pattern to
  the hardware-proven `udon-linux-log-graft.img` in BRINGUP-2026-10-25.md, which also
  used vbmeta size 2,432).

## 7. Verification (independent readback, separate from the packager asserts)

- `ANDROID!` magic; header diff vs stock = bytes [8..14] only (kernel_size/ramdisk_size).
- kernel pages = 311; payload end (1,277,952) == footer vbmeta_offset == orig_size.
- gzip round-trip == BootShim+FD; shim header `(0xA7100000, 4194496)` ✓; FD `_FVH` at
  gunzip offset 0xE8 (= shim 192 + 0x28) ✓.
- Final vbmeta bytes identical to stock bytes @ 0x2F49000 (sha 25314ab1…) ✓.
- Everything between payload end and vbmeta, and after the footer, zero-filled ✓.
- `avbtool`-style sanity: footer version 1.0; stock footer parse (orig 49,582,080 =
  header+kernel+ramdisk+signature pages) consistent.
- `scripts/check-udon-platform.py` passed post-build.

## 8. Flashing instructions for the main agent

```sh
# device must be in fastboot (bootloader) mode; BL is already unlocked/orange
fastboot flash boot_b device-layer/udon-uefi-grafted.img
fastboot set_active b
fastboot reboot
```

- The image fills the whole 192 MiB boot_b partition (same as stock), includes the
  stock OEM vbmeta graft — this is the only path proven to pass PHK110 ABL acceptance.
- Do NOT also reflash vbmeta/vendor_boot (stock vendor_boot_b with its DTB must stay;
  `backups-slotb/` holds `backup-boot_b.img`, `backup-vendor_boot_b.img`,
  `backup-vbmeta_b.img`, `backup-dtbo_b.img` for restore: `fastboot flash boot_b backups-slotb/backup-boot_b.img` etc.).
- Expected on success: ABL hands off to the shim, which copies the 4 MiB FD to
  0xA7100000 and boots Mu-Silicium udonPkg UEFI (UniXNU menu on the 1240x2772 splash
  framebuffer). Serial/logging expectations inherit from the upstream bring-up docs.

## 9. Reproducing from scratch (one-liners)

```sh
wsl -d FedoraLinux-44
export UNIXNU_ROOT=$HOME/hakios/unixnu-core
cd ~/hakios/uefi-udon && JOBS=$(nproc) ./scripts/build-udon-firmware.sh
cd BootShim && make REQUIRES_KERNEL_HEADER=1 FD_BASE=0xA7100000 FD_SIZE=0x400000 && cd ..
python3 /mnt/c/.../hakios-phk110/wave4-scripts/package-udon-boot.py ...   # see §6
```

## 10. Open issues / residual risks

1. **Binaries provenance**: modules are the SM8475 senna_bc (realme GT Neo 5) set, not
   PHK110's own (unobtainable: XBL encrypted, abl carries only the ABL app). This is
   the same substitution class upstream projects use for same-silicon bring-up, and
   udonPkg was written against this exact set — but a real-PHK110 module set could
   still differ (e.g. PMIC, charger, UFS pacing). First-boot log review should watch
   PmicDxe/QcomChargerDxe/OplusProject/OGaugeAuth warnings.
2. **DEBUG build**: built `-b DEBUG` per the upstream build script (their REPRODUCE.md
   also uses `AARCH64 DEBUG CLANGPDB`); DEBUG serial logging is larger but the FD fits
   its 4 MiB region.
3. **ramdisk_size=0 deviation** (see §6) — intentional; flagging in case the main agent
   wants an alternate variant with the stock value for A/B comparison.
4. The UniXNU payload (XNU kernel etc.) is not part of this image; UEFI will boot to the
   UniXNU menu and look for the payload FAT volume in `super` (out of 阶段 4 scope).
5. `intel/wave4-abl-extract/abl-fvmain-inner.fv` (819 KB) is kept as evidence of the
   abl_a contents for future waves.
