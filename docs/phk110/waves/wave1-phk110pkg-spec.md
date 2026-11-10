# 阶段 1 · 2026-11-02 · UEFI 平台包（phk110Pkg）逐文件适配方案

> 调查代理 C · 2026-11-02 · 只读调查产物，供 阶段 2 实现代理机械执行。
> 调查环境：Mu-Silicium 为 WSL Fedora-44 `~/hakios/Mu-Silicium/`（HEAD=6b3d90b "Version 4.1"）；
> 已用 `git fetch origin e51cd87` + diff 验证：**BASE(e51cd87, HakiOS 钉住) 与 HEAD 在本规格涉及的全部路径上无差异**
>（全仓库仅 2 处差异：ErrataPatchesLib.c 一条 DEBUG 字符串、build_uefi.py 的 MuPatches 列表少一项 `AsmMacroLib.patch`）。
> 本文档所有行号/结构对 BASE 有效。

---

## 0. 结论速览（先读这里）

1. **模板改判**：`bitraPkg` 不是 SM8475 平台包。bitra = **Realme GT Neo 2，SM8250-AC（Kona，骁龙 870）**，
   其 dsc `!include KonaPkg/KonaPkg.dsc.inc`、SOC_TYPE 注释 0/1/2=SM8250/-AB/-AC、SMBIOS 串 "GT NEO 2"、
   Mu-Silicium Status.md 明写 "Realme GT NEO 2 / Codename: bitra / State: Inactive"。
   原 PLAN.md 中 "bitra（Realme GT Neo 3，SM8475 同硅）" 的前提**错误**（GT Neo 3 也是联发科，从无 SM8475 版）。
2. **正确硅层 = WaipioPkg**：Mu-Silicium 里所有 SM8475 设备（Xiaomi `ingresPkg`=Poco F4 GT、
   Samsung `r0qPkg`=Z Flip4、`gts8pPkg`=Tab S8）的 dsc 都是 `!include WaipioPkg/WaipioPkg.dsc.inc`。
   PHK110（SM8475 Cape，DT model "Cape MTP, Udon"）走 Waipio 层。**本规格模板 = `Platforms/Xiaomi/ingresPkg`**
   （同为 SM8475 手机、状态最完整：Display/存储/按钮/MassStorage/Windows Boot 全 ✅）。
3. **驱动二进制源**：PHK110 自身 XBL/ABL 已确认加密（intel/phk110-xbl-a.bin、phk110-abl-a.bin 无可读 UEFI 字符串，
   与 M0-PROGRESS "xbl 加密（OPPO sec-boot）" 一致）→ 无法自提取。采用公共仓库
   `Binaries/ingres/`（Poco F4 GT，SM8475，9.3MB，73 个驱动目录）复制为本地 `Binaries/phk110/`。
   bitra 的 50 个 DXE 是 Kona 时代产物，寄存器/协议版本与 Cape 不匹配，**不要用**。
4. **显示**：首版 `USE_CUSTOM_DISPLAY_DRIVER = 0` → 用开源 `SiliciumPkg/Drivers/SimpleFbDxe` 接管 XBL 遗留
   framebuffer（bitra 包正是这么做的且 Display ✅），绕开"拿不到 PHK110 panel XML"的死结。
5. **HakiOS 关键差异**：redwood 先例证明设备包适配 = 纯改名 + 数据文件替换；但 MemoryMapLib 必须新增
   `{"XNU Payload", 0xF0000000, 0x04000000, ...}`（64MB，BootShim/XnuLoader 的 XNUP 容器落点）。
   **PHK110 主 RAM 在 0x800000000–0xb7fffffff，0xF0000000 落在 RAM 之外** → redwood 的 0xF0000000 不可照抄，
   XnuLoader.h 的 `XNU_PAYLOAD_BASE`（hakios-uefi 全局 overlay）也要用设备 overlay 覆盖（apply.sh 设备目录最后拷贝，
   可覆盖全局文件）。地址等 wave1-socargs.md 给出（见 §6.10、§8）。
6. 构建前置：WSL Fedora 已缺 `nasm`、`gcc-aarch64-linux-gnu`（另有 mono/nuget/gnupg，见 §7）；
   Mu-Silicium 6 个子模块需 `--init`（当前只初始化了 Binaries）；venv 装 `pip-requirements.txt`；
   系统 Python 3.14.8 过新，venv pip 可能无轮子（§7 有降级预案）。

---

## 1. build_uefi.py 的设备解析：全部硬编码约定（读源码确认）

源：`build_uefi.py`（523 行）。`-d <device>` 之后发生的事，每一条都是 阶段 2 必须满足的约定：

| # | 约定 | 代码位置 | phk110 需要的文件 |
|---|------|----------|-------------------|
| 1 | 平台包目录：`Platforms/*/<device>Pkg` 或 `Platforms/*/*/<device>Pkg`（两级 glob，取第一个命中） | `get_device_package_path` | `Platforms/OnePlus/phk110Pkg/`（`Platforms/OnePlus/` 已存在，OnePlus 10 Pro aston 等在用） |
| 2 | 设备 TOML：`Resources/Configs/<device>.toml`（缺则退出） | `parse_device_config` | `Resources/Configs/phk110.toml` |
| 3 | TOML 必含 `[uefi_fd]` 的 `base`、`size`（缺则退出）；`blocks = size // 4096` | `main` | 同上 |
| 4 | TOML 若含 `[status] model_count`：输出名带 `-<model>` 后缀且 `-m` 超界即退出；**没有 `[status]` 则不检查**，输出 `Mu-phk110.img` | `main`/`create_output_image` | phk110 单机型，**不加** `[status]` |
| 5 | 平台包内必须有 `DeviceBuild.py`（stuart 入口） | `main` | §6.4 |
| 6 | TOML 含 `[boot_shim]` 才编 BootShim（make 传 `FD_BASE/FD_SIZE/REQUIRES_KERNEL_HEADER`） | `compile_boot_shim` | 必须含：HakiOS 启动链靠 BootShim 搬运 XNUP 容器 |
| 7 | `prepare_uefi_environment`：若 `Build/` 不存在或 `-u`，调 `DeviceBuild.py --setup` 和 `--update -t <mode>`（触发 stuart_setup/update：装子模块、装 extdep） | `prepare_uefi_environment` | DeviceBuild.py 的 `GetRequiredSubmodules` 列出全部 6 个子模块 |
| 8 | Mu_Basecore 打 4 个补丁：`Resources/MuPatches/{Auth-Service,Boot-Manager,Timer,Usb-Bus}.patch`（BASE 上是这 4 个；HEAD 多了 AsmMacroLib.patch） | `main` | 无需动作，仓库自带 |
| 9 | 编译 UEFI：`DeviceBuild.py TARGET=<mode> ENABLE_SECUREBOOT=.. FD_BASE=0x.. FD_SIZE=0x.. FD_BLOCKS=0x.. DEVICE_MODEL=0` | `compile_uefi` | FD_BASE/FD_SIZE 来自 TOML |
| 10 | 产物 FV 路径：`Build/<device>Pkg/<TARGET>_CLANGPDB/FV/SILICIUM_UEFI.fd`（FD 名由 FDF `[FD.SILICIUM_UEFI]` 固定） | `create_android_boot_img` | FDF 不改这段 |
| 11 | `boot_image_kernel.kernel_compression` ∈ {gzip, none}；`append_dtb=true` 时要求 `Resources/DTBs/<device>.dtb` 存在（缺则报错退出），kernel = gzip(FD 或 FD+BootShim) + DTB | `create_android_boot_img` | `Resources/DTBs/phk110.dtb` |
| 12 | mkbootimg：`Resources/Scripts/mkbootimg.py`，参数白名单 base/cmdline/dtb/dtb_offset/header_version/kernel_offset/...（TOML `[boot_image]` 给多少传多少）；ramdisk 用占位文件 `Resources/ramdisk`（5 字节，仓库自带） | 同上 | TOML `[boot_image] header_version` |
| 13 | payload 型输出（`[payload] type=raw`）与 bootimg 型（`[boot_image]`）二选一；都没有则只留 .fd 并警告跳过 | `create_output_image` | 用 `[boot_image]`（与 redwood 相同），便于单独 fastboot boot 测 UEFI |

注意：**HakiOS 日常 XNU 启动链不用这个 bootimg**（用内核仓 `mkxnuimg.py`，`--header_version 1` 写死），
build_uefi.py 的 bootimg 只是 UEFI 单体调试通道；TOML 仍按 redwood 惯例配全。

---

## 2. HakiOS 侧 overlay 流程（apply.sh/export.sh，读源码确认）

`hakios-uefi/apply.sh`（"默认对每个有 `devices/<name>/uefi/files/` 的设备执行"）：

```
git clone Mu-Silicium → checkout BASE(e51cd87) → submodule update --init --recursive
→ git apply hakios.patch                       # BootShim.S(XNUP→0xF0000000) + BootManagerLib→XnuLoader + Sec.c 首行日志 + PcdFirmwareVendor=HakiOS
→ cp -r files/.        $MU/                    # 全局新文件：XnuLoader.[ch]
→ python3 branding/banner.py SiliciumPkg/Include/Resources   # HakiOS 三张图
→ for d: cp -r devices/$d/uefi/files/. $MU/    # ★ 设备层最后拷 → 设备文件可覆盖全局/补丁产物
```

`export.sh` 是逆操作（`git diff -- BootShim Silicon` → hakios.patch；XnuLoader.[ch] → files/；每设备 `uefi/export.sh`）。

因此 **phk110 的设备树内可以有 `devices/phk110/uefi/files/` 之外的覆盖文件**（如 BootShim.S、XnuLoader.h），
放同一 `uefi/files/` 树里按 Mu-Silicium 根相对路径摆放即可，拷贝顺序保证生效。

`devices/manifest.conf`（hakios-xnu-kernel）：登记制。本地开发**不需要**登记；将来开源设备仓后再加块
（`device phk110 / repository <git URL> / revision <sha>`）。

---

## 3. redwoodPkg 先例：HakiOS 设备包相对上游差多少（实测 diff）

HakiOS `hakios-sm7325/uefi/files/Platforms/Xiaomi/redwoodPkg/`（13 文件）与上游 `Platforms/Xiaomi/lisaPkg/`
逐文件 diff 的结果——这就是 phk110 适配的"配方模板"：

| 文件 | lisa→redwood 实际差异 |
|------|----------------------|
| `<dev>.dec` | 0 字节空文件（所有设备都这样；dec 在这里只是 EDK2 包存在性占位） |
| `<dev>.dsc` | 仅 6 处：PLATFORM_NAME/PLATFORM_GUID/OUTPUT_DIRECTORY/FLASH_DEFINITION 改名 + 5 条 SMBIOS 字符串 + MemoryMapLib/ConfigurationMapLib 路径改名。**[Components] 直接复用上游 `lisa/AcpiTables.inf`**（redwood 没有自己的 ACPI 表！） |
| `<dev>.fdf` | 纯改名（FV 结构完全一致） |
| DeviceBuild.py | 纯改名（PackagesSupported/Scopes/PackagesPath/GetPlatformDscAndConfig/GetName/PRODUCT_NAME/ACTIVE_PLATFORM） |
| Include/APRIORI.inc, DXE.inc, RAW.inc | **仅把 `Binaries/lisa/` → `Binaries/redwood/`**（redwood 的 RAW.inc 面板清单按自提取的驱动重排过，但那是"有自己二进制"才需要的事） |
| Library/MemoryMapLib.c | 3 处数据修改（TZApps 大小、ADSP RPC）+ **新增一行 `{"XNU Payload", 0xF0000000, 0x04000000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN}`** ← HakiOS 唯一真正的新增语义 |
| Library/ConfigurationMapLib.c | 逐字节相同（纯复制） |
| Library/*.inf | 纯复制 |
| Resources/Configs/redwood.toml | uefi_fd base=0x9FD00000 size=0x200000（=MemoryMapLib 的 "UEFI FD" 行）；gzip；append_dtb=true；header_version=1 |
| Resources/DTBs/redwood.dtb | 设备 FDT 二进制，进 git（provenance `pending`） |
| Binaries/redwood/README.md | 记录固件版本（OS1.0.3.0.UMSMIXM / BOOT.MXF.1.0-00852-LAHAINA-2.12801.8）+ 5 个二进制补丁（ButtonsDxe 按键码→Enter、DALSYSDxe UFS cache coherence、TzDxeLA 全局 applet 变量=TRUE、UsbConfigDxe 去 ExitBootServices USB 反初始化、UsbMsdDxe 可移动位清除）及其作者。**二进制本体不进 git** |

---

## 4. 模板平台包逐文件剖析（bitraPkg & ingresPkg，结构完全同构）

目录（两包一致，13 文件）：

```
Platforms/<Vendor>/<dev>Pkg/
  <dev>.dec                                  # 0 字节
  <dev>.dsc                                  # 平台 DSC，!include 硅层 dsc.inc
  <dev>.fdf                                  # FD/FV 骨架
  DeviceBuild.py                             # stuart 入口（build_uefi.py 的 8 号约定）
  Include/APRIORI.inc                        # DXE 调度顺序（APRIORI FFS）
  Include/DXE.inc                            # FvMain 的 INF 清单主体
  Include/RAW.inc                            # FvMain 的 RAW/FREEFORM 文件（panel XML、cfg）
  Library/MemoryMapLib/{MemoryMapLib.c,.inf} # 设备内存映射描述
  Library/ConfigurationMapLib/{ConfigurationMapLib.c,.inf}  # QCOM UEFI 配置键值表
```

### 4.1 bitraPkg（原计划模板，仅作对照存档）

- `bitra.dec`：0 字节。
- `bitra.dsc`（85 行）：`PLATFORM_NAME=bitra`，GUID `4F4872E2-A454-4FFA-9145-8C6F473A5D9E`，
  `FLASH_DEFINITION=bitraPkg/bitra.fdf`，`USE_CUSTOM_DISPLAY_DRIVER=0`，`SOC_TYPE=2`（注释：0=SM8250,1=SM8250-AB,2=SM8250-AC），
  `!include KonaPkg/KonaPkg.dsc.inc`；PCD：`PcdSystemMemoryBase|0x80000000`、
  `PcdCPUCoresStackBase|0x9FF90000`、`PcdCPUCorePrimaryStackSize|0x40000`、5 条 SMBIOS（"Realme"/"GT NEO 2"/"bitra"...）、
  FB 1080x2400x32、`gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"`；
  LibraryClasses：MemoryMapLib/ConfigurationMapLib 指向包内；[Components]：`bitra/AcpiTables.inf`
  （经 PackagesPath `Silicium-ACPI/Platforms/Realme` 解析到 Silicium-ACPI 子模块）。
- `bitra.fdf`（133 行）：`[FD.SILICIUM_UEFI]` 用 `$(FD_BASE)/$(FD_SIZE)/$(FD_BLOCKS)`（build_uefi.py 传入），
  单 region 0x00000000|$(FD_SIZE) → `FV = FVMAIN_COMPACT`；`[FV.FvMain]`（FvNameGuid CD8D4C84-...，固定 GUID 全设备复用）
  依序 `!include Include/APRIORI.inc / DXE.inc / RAW.inc` + RamManagerDxe + SmbiosDxe/SmBiosTableDxe +
  AcpiTableDxe/AcpiPlatformDxe + `RuleOverride=ACPITABLE bitra/AcpiTables.inf` + （注释掉的 DTB FV 段）+
  `!include QcomPkg/Extra.fdf.inc`；`[FV.FVMAIN_COMPACT]` = `SiliciumPkg/Sec/Sec.inf` + GUIDED 压缩 FVMAIN +
  `!include SiliciumPkg/Common.fdf.inc`。**无 flash 大小/RAW 硬编码，唯一设备相关项就是 AcpiTables 文件名。**
- `Include/APRIORI.inc`（109 行）+ `DXE.inc`（103 行）：41 个 `Binaries/bitra/QcomPkg/Drivers/...` 厂商 INF +
  EDK2 通用 INF；`!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1` 时挂厂商 DisplayDxe 与 CPRDxe，否则挂
  `SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf`；Oplus 特色：`OcdtDxe/OplusProject.inf`（=OplusProject 伪 inf）、
  `OGaugeAuthDxe/OGaugeAuth.inf`。**引用的 INF 必须真实存在，缺一个 build 即失败**（这是 Binaries 目录名与设备名
  实际上强耦合的地方——耦合点是文本路径，不是机制）。
- `Include/RAW.inc`（241 行）：44 个 FILE FREEFORM（GUID + SECTION UI 名 + SECTION RAW 路径）。
  41 个 panel XML 在 `!if USE_CUSTOM_DISPLAY_DRIVER == 1` 内（仅厂商 DisplayDxe 运行时读取）；
  恒定 4 个：`SecParti.cfg`(A1E235DE-...)、`uefipil.cfg`(21E9BDD9-...)、`QcomChargerCfg.cfg`(45FE4B7C-...)、
  `BATTERY.PROVISION`(F780C779-...)。bitra RawFiles 里另有 uefiplat.cfg/BDS_Menu.cfg/logo1.bmp/verifyboot.bmp
  未被 RAW.inc 引用（XBL 全量提取的剩余物）。
- `Library/MemoryMapLib/MemoryMapLib.c`（64 行）：`EFI_MEMORY_REGION_DESCRIPTOR gMemoryDescriptor[]`，8 元组
  `{Name, Address, Length, HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttribute}`。
  Kona 布局：HYP 0x80000000/0x600000、SMEM 0x80900000/0x200000、TZApps 0x82400000/0xB400000、
  PIL 0x8DA00000/0xAD00000、DXE Heap 0x98900000、FV Region 0x9F800000、**UEFI FD 0x9FC00000/0x300000**（=TOML base）、
  SEC Heap→Info Blk 收尾于 0x9FFFF000、MMIO 尾条 `APSS_HM 0x17800000/0xd981000`。
- `Library/ConfigurationMapLib/ConfigurationMapLib.c`（49 行）：`EFI_CONFIGURATION_ENTRY_DESCRIPTOR` 键值对
  `{CHAR8* Name, UINT64 Value}`，34 项（NumCpus 8、SharedIMEMBaseAddr 0x146BF000、DloadCookieAddr 0x01FD3000、
  ShmBridgememSize 0xA00000、EnableDisplayImageFv 0 等）。Kona 专有值。
- `DeviceBuild.py`（204 行）：stuart 五件套（Update/Setup/PrEval/Parse/Build SettingsManager + UefiBuilder）。
  设备相关仅 8 处字符串：`PackagesSupported=("bitraPkg")`、`Scopes=('bitra','gcc_aarch64_linux','edk2-build')`、
  `WorkspaceRoot`=上溯 4 级、`PackagesPath=("Platforms/Realme","Common/Mu","Common/Mu_OEM_Sample","Mu_Basecore",
  "Silicon/Qualcomm","Silicon/Silicium","Silicium-ACPI","Silicium-ACPI/Platforms/Realme","Silicium-ACPI/Silicon/Qualcomm")`、
  `GetPlatformDscAndConfig=("bitraPkg/bitra.dsc",{})`、`GetName()="bitra"`、`PRODUCT_NAME`、`ACTIVE_PLATFORM`。
  `GetRequiredSubmodules`：Binaries、Common/Mu、Common/Mu_OEM_Sample、Mu_Basecore、Silicium-ACPI、
  Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl（共 6）。`SetPlatformEnv` 透传 FD_BASE/FD_SIZE/FD_BLOCKS/
  ENABLE_SECUREBOOT 为 BLD_*_*。

### 4.2 ingresPkg（本规格实际模板）与 bitraPkg 的全部差异

| 项 | ingresPkg 值 |
|----|--------------|
| dsc `!include` | `WaipioPkg/WaipioPkg.dsc.inc`（**无 SOC_TYPE**，Waipio 层不分型） |
| dsc `USE_CUSTOM_DISPLAY_DRIVER` | **1**（挂厂商 DisplayDxe+CPRDxe+44 panel RAW）→ phk110 要改成 0 |
| dsc 栈 | `PcdCPUCoresStackBase|0xA760D000`（与它的 MemoryMapLib "UEFI Stack" 行一致） |
| [Components] | `ingres/AcpiTables.inf`（Silicium-ACPI/Platforms/Xiaomi/ingres/ 实存：AcpiTables.inf+SSDT.asl+SSDT.aml，已在线验证） |
| fdf 额外 | FvMain 里多一行 `INF QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf`（Waipio 的 IORT DT 修复驱动，WaipioPkg.dsc.inc [Components] 也编它） |
| RAW.inc | 44 RAW = SecParti.cfg + uefipil.cfg + QcomChargerCfg.cfg + 41 panel（Poco F4 GT 的 r66451 系等）；**无 BATTERY.PROVISION** |
| MemoryMapLib | Waipio 布局：HYP 0x80000000/0x600000、DT BLOB 0x80600000、XBL RAMDUMP 0x80640000、AOP 0x80800000、SMEM 0x80900000/0x200000、PIL 0x85200000/0x1DC00000、DBI Dump 0xA6000000、**FD Reserved 0xA7000000/0x100000 + UEFI FD 0xA7100000/0x300000 + UEFI FD Reserved 0xA7400000/0x200000**、Info Blk 0xA7601000 → UEFI Stack 0xA760D000 → … → FV Region 0xA7AD9000 → UEFI RESV 0xA7ED9000、Kernel 0xA8000000/0x10000000、Display Reserved 0xB8000000/0x2B00000、OEM VM 0xBB000000/0x5000000、MTE Reserved 0xC0000000/0x20000000、VM PIL 0xE0000000/0x5700000、TZApps 0xEA000000/0x7400000、DXE Heap 0xF8000000/0x7C00000、HYP Reserved 0x830000000/0x10000000；IMEM 0x14680000/0x2A000 + Cookie 0x146AA000/0x16000；MMIO：QUP 0x00800000/0x300000、PRNG 0x010C0000、CRYPTO 0x01DC0000、TCSR 0x01FC0000、PERIPH_SS 0x08800000/0x100000、USB 0x0A600000/0x200000、AOSS 0x0B000000/0x4000000、TLMM 0x0F000000/0x1000000、SMMU 0x15000000/0x200000、APSS_HM 0x17000000/0x2000000 |
| ConfigurationMapLib | 45 项，Waipio 值（SecPagePoolCount 0x800、SharedIMEMBaseAddr 0x146AA000、UefiMemUseThreshold 0x1900、EnableUfsIOC 1、EarlyInitCoreCnt 2、EnableDisplayImageFv 1、PilSubsysDbgCookie 0x146AA6DC/0x53444247、EnableMultiCoreFvDecompression 1、EnableACPIFallback 0 等） |
| Binaries/ingres | 9.3MB、73 个 QcomPkg/Drivers 目录；DXE.inc+APRIORI.inc 实际引用 41 个 INF（清单见 §6.7）+ RawFiles（45 文件） |

### 4.3 WaipioPkg.dsc.inc（硅层，phk110 无需复制，引用即可）

KEP errata：ACTLR_EL1/AMCNTENSET0/GIC-V3-IRM=1、PSCI-MEMPROTECT=0；`-march=armv9-a+crypto+rcpc`；
`PcdAcpiDefaultOemId|"QCOM  "`、OemTableId 0x20204F4950494157（"WAIPIO"）、OemRevision 0x8450；
`PcdCoreCount|8`、`PcdClusterCount|3`；**GICD 0x17100000、GICR 0x17180000**；SMBIOS CPU 串 "SM8450"
（可被设备 dsc 覆盖）；`PlatformSecLib`/`AcpiTableUpdateLib` ← WaipioPkg/Library。链路：
`phk110.dsc → WaipioPkg.dsc.inc → QcomPkg.dsc.inc → SiliciumPkg.dsc.inc`（QcomPkg 层提供 PlatformPeiLib、
RamManagerLib、PlatformBootManagerLib【HakiOS hakios.patch 改的就是 Silicium 层的 BootManagerLib，链路兼容】、
SmBiosTableLib、DisplayReEnablerDxe、MassStorage 等）。

---

## 5. Binaries 策略决策（任务 4）

**决策：方案②变体 —— 设备树内建 `devices/phk110/uefi/files/Binaries/phk110/`（git 只进 README.md；
二进制本体在本地用 `Binaries/ingres/` 填充，不 commit）。**

| 备选 | 判定 |
|------|------|
| ① phk110Pkg 的 inc 直接引用 `Binaries/bitra` | 否。bitra=Kona/SM8250-AC 二进制，XBL 代差 2 年（BOOT.XF.4.x vs Cape 的 BOOT.XF.5.x），ClockDxe/RpmhDxe/UFSDxe/DisplayDxe 的寄存器表和协议版本与 SM8475 不匹配，几乎必然连 UEFI shell 都到不了。且"语义混用"确实会误导后续维护者 |
| ② 复制 `Binaries/bitra` → `Binaries/phk110` | 源本身错了（同上）。目录拷贝机制本身没问题 |
| ③（本规格）复制 `Binaries/ingres` → 本地 `Binaries/phk110` | 同硅 SM8475、同代 XBL、73 驱动目录覆盖 DXE.inc 所需全部 41 个 INF + RawFiles。du：**Binaries/bitra=9.0MB、Binaries/ingres=9.3MB**，拷贝代价可忽略 |

build_uefi.py/EDK2 对 Binaries 目录名**没有机制性强约束**——约束只是 DXE.inc/APRIORI.inc/RAW.inc 里的文本路径
`Binaries/<名字>/...`（名字可任意，路径必须存在）。选 `Binaries/phk110`（而非直接引用 Binaries/ingres）的理由：
1. HakiOS 惯例是设备树携带 `Binaries/<device>/README.md` 记录固件版本与二进制补丁（redwood 先例）；
   将来若拿到可解密的 XBL 或 Oplus 同硅固件，只替换目录内容、平台包零改动。
2. `Binaries/` 在 Mu-Silicium 里是 git 子模块（Device-Binaries 仓库）。在子模块工作树里加未跟踪文件
   虽然能 build，但会被子模块 git status 污染，且 HakiOS overlay 语义是"设备文件铺在 Mu-Silicium 根"，
   不该依赖别人仓库的子模块路径内容。
3. provenance-check（hakios-xnu-kernel/tools/provenance-check.py）：**只扫 git 跟踪的文件**
   （`git ls-files`）。本地不 commit → 完全不受影响。若将来推设备仓：`Binaries/phk110/*` 属 `vendor`
   语义（check 会 fail 直到移出），正确姿势与 redwood 相同——git 里只留 README.md，DTB 单独一条
   `pending`（redwood 的 allow 表里两条先例：`pending devices/redwood/uefi/files/Resources/DTBs/redwood.dtb`、
   `vendor devices/redwood/uefi/files/Binaries/redwood/*`）。阶段 2 需在 kernel 仓
   `tools/provenance.allow` 照抄两行换成 phk110 路径（§6.11）。

ingres 驱动的预期问题（写进 README 风险栏）：Poco F4 GT 无 side keys 之外的按键差异不大，但 PMIC/GLink
电池/充电链路是 Xiaomi 私有 GLink 对接，PHK110 是 Oplus 私有协议 → 充电/电量类 DXE（QcomChargerDxe、
ChargerExDxe、PmicGlinkDxe、GLinkDxe、OGaugeAuth 等）首次跑可能挂或无功能；显示靠 SimpleFb 回退
（见 §6.2 的 USE_CUSTOM_DISPLAY_DRIVER=0）。这些不影响"UEFI 起来 + SimpleFb 出画面 + USB/logfs 通路"的 v1 目标。

---

## 6. 逐文件适配规格（阶段 2 机械执行单）

目标树根：`~/hakios/kernel/devices/phk110/uefi/files/`（apply.sh 会把它整体拷进 Mu-Silicium 根）。
13 个平台包文件全部来自模板复制 + 定点修改；`<...>` 占位符汇总见 §6.12。

```
devices/phk110/uefi/files/
├── Platforms/OnePlus/phk110Pkg/
│   ├── phk110.dec
│   ├── phk110.dsc
│   ├── phk110.fdf
│   ├── DeviceBuild.py
│   ├── Include/{APRIORI.inc, DXE.inc, RAW.inc}
│   └── Library/{MemoryMapLib,ConfigurationMapLib}/{*.c,*.inf}
├── Resources/Configs/phk110.toml
├── Resources/DTBs/phk110.dtb            （可选 phk110.dts）
├── Binaries/phk110/README.md            （git 可见；其余内容本地填充，不 commit）
└── （条件覆盖，见 §6.10）Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h
```

### 6.1 `Platforms/OnePlus/phk110Pkg/phk110.dec`
- 源：`Platforms/Xiaomi/ingresPkg/ingres.dec`（0 字节）。
- 修改：无。创建 0 字节文件。

### 6.2 `Platforms/OnePlus/phk110Pkg/phk110.dsc`
- 源：`Platforms/Xiaomi/ingresPkg/ingres.dsc`（全文 95 行）。
- 修改点（7 处）：
  1. `PLATFORM_NAME = phk110`
  2. `PLATFORM_GUID = <新生成>`（uuidgen；不得复用 ingres 的 E4EA93C9-...）
  3. `OUTPUT_DIRECTORY = Build/phk110Pkg`
  4. `FLASH_DEFINITION = phk110Pkg/phk110.fdf`
  5. `USE_CUSTOM_DISPLAY_DRIVER = 1` → **改 `0`**（v1 用 SimpleFbDxe；等拿到 PHK110 panel XML 再翻回 1 并补 RAW.inc panel 段）
  6. SMBIOS 5 条：`PcdSmbiosSystemManufacturer|"OnePlus"`、`...SystemModel|"Ace 2"`、
     `...SystemRetailModel|"phk110"`、`...SystemRetailSku|"PHK110"`、`...SystemBoardModel|"Ace 2"`
  7. `PcdFrameBufferWidth|1080` / `Height|2400` → **`1240` / `2772`**（Ace 2 = 6.74" 1.5K 2772×1240；
     SimpleFbDxe 用 FixedPcdGet 暴露 GOP 模式，纵屏竖排与 bitra/salami 的 1080x24xx 同构）【待验证 V-1】
- **保持不变**（关键）：
  - `!include WaipioPkg/WaipioPkg.dsc.inc`（照抄，不改 KonaPkg）；
  - `PcdSystemMemoryBase|0x80000000`；
  - `PcdCPUCoresStackBase|<STACK>`（占位符：ingres 值 0xA760D000，**必须**与 MemoryMapLib "UEFI Stack" 行地址一致，
    阶段 2 生成 MemoryMapLib 后回填）+ `PcdCPUCorePrimaryStackSize|0x40000`；
  - `gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"`；
  - LibraryClasses 两行 → `phk110Pkg/Library/...`；
  - `[Components] ingres/AcpiTables.inf` **原文保留**（同硅复用 ACPI，redwood 复用 lisa 的同款先例；
    由 DeviceBuild.py PackagesPath `Silicium-ACPI/Platforms/Xiaomi` 解析，见 §6.4）。
- 板型 ID 说明（任务里问的 PlatformInfoDxe/ProjectInfoDxe/ChipInfoDxe）：这三个都是厂商二进制 DXE，
  从 XBL devinfo/共享内存自读板型，**上游不存在给它们的 PCD**，redwood/lisa/ingres/bitra 都没有覆盖，phk110 同样不设。
  平台身份的唯一可控 PCD 就是上面 SMBIOS 5 条 + PcdPlatformType。

### 6.3 `Platforms/OnePlus/phk110Pkg/phk110.fdf`
- 源：`Platforms/Xiaomi/ingresPkg/ingres.fdf`。
- 修改点：仅 1 处 —— `INF RuleOverride = ACPITABLE ingres/AcpiTables.inf` **原样保留**（同 §6.2，ACPI 复用）。
  其余（FD.SILICIUM_UEFI 的 $(FD_*) 变量、FvNameGuid CD8D4C84-...、三个 `!include Include/*.inc`、
  RamManagerDxe/Smbios/Acpi 栈、IortDtDxe、`QcomPkg/Extra.fdf.inc`、FVMAIN_COMPACT/Sec/Common.fdf.inc）全部照抄。
- 说明：fdf **没有** flash 大小/RAW 段硬编码；panel RAW 在 RAW.inc（当前 flag=0 不参与）；无 DTB FV 段
  （注释掉的模板块保留不动）。

### 6.4 `Platforms/OnePlus/phk110Pkg/DeviceBuild.py`
- 源：`Platforms/Xiaomi/ingresPkg/DeviceBuild.py`。
- 修改点（8 处字符串，diff bitra↔ingres 同构）：
  1. `PackagesSupported = ("phk110Pkg")`
  2. `Scopes = ('phk110', 'gcc_aarch64_linux', 'edk2-build')`（scope 是自由名，无中央注册表——上游每设备独立）
  3. `PackagesPath`：`"Platforms/Xiaomi"` → **`"Platforms/OnePlus"`**；`"Silicium-ACPI/Platforms/Xiaomi"` **保留**
     （因为 [Components] 复用 `ingres/AcpiTables.inf`；将来自制 phk110 ACPI 时改成
     `"Silicium-ACPI/Platforms/OnePlus"` 并同步挪 [Components]）；其余 7 项不动
  4. `GetPlatformDscAndConfig` → `("phk110Pkg/phk110.dsc", {})`
  5. `GetName` → `"phk110"`
  6. `PRODUCT_NAME` → `"phk110"`
  7. `ACTIVE_PLATFORM` → `"phk110Pkg/phk110.dsc"`
  8. （函数 `GetName` 有两处：SettingsManager 返回 `"phk110"`、PlatformBuilder 返回 `"phk110Pkg"`，分别改）
- `GetRequiredSubmodules`（6 项）不动。

### 6.5 `Platforms/OnePlus/phk110Pkg/Library/MemoryMapLib/MemoryMapLib.inf` 与 `ConfigurationMapLib/*.inf`
- 源：ingresPkg 对应 .inf。修改：无（BASE_NAME/LIBRARY_CLASS 与文件名解耦，纯复制）。

### 6.6 `Platforms/OnePlus/phk110Pkg/Library/ConfigurationMapLib/ConfigurationMapLib.c`
- 源：ingresPkg 版（45 项 Waipio 值）。修改：**v1 原样复制**。
- 后续调优（非 v1 阻塞）：这些值源自设备 XBL 的 uefiplat.cfg；PHK110 XBL 加密拿不到，故长期沿用 ingres 值，
  出问题再对PHK110 abl log/内核 DT 推导逐项调（SharedIMEMBaseAddr 0x146AA000、DloadCookieAddr、
  SecPagePoolCount 优先核查——见 §8 V-4）。

### 6.7 `Platforms/OnePlus/phk110Pkg/Include/APRIORI.inc`、`Include/DXE.inc`、`Include/RAW.inc`
- 源：ingresPkg 三件。修改：**只做机械替换 `Binaries/ingres/` → `Binaries/phk110/`**（APRIORI+DXE 共 41 个唯一 INF
  路径、RAW.inc 44 个 RAW 路径），**不增删任何 INF**。
- 替换后自检（必做）：
  ```bash
  grep -ho 'Binaries/phk110/[^ ]*\.inf' Include/APRIORI.inc Include/DXE.inc | sort -u | while read p; do
    [ -f "$p" ] || echo "MISSING: $p"; done   # 在 Mu-Silicium 根执行
  grep -ho 'Binaries/phk110/RawFiles/[^ ]*' Include/RAW.inc | sort -u | while read p; do
    [ -f "$p" ] || echo "MISSING: $p"; done
  ```
- DXE.inc 引用的 41 个厂商 INF（=Binaries/phk110 必须含的最小集，全部在 Binaries/ingres 里实存）：
  `ButtonsDxe, ChargerExDxe, ChipInfoDxe, ClockDxe, CmdDbDxe, CPRDxe, DALSYSDxe, DDRInfoDxe, DisplayDxe,
  EnvDxe, FeatureEnablerDxe, GLinkDxe, GpiDxe, HALIOMMUDxe, HWIODxe, I2CDxe, ICBDxe, IPCCDxe, NpaDxe,
  PILDxe, PILProxyDxe, PlatformInfoDxe, PmicDxe(PmicDxeLa.inf), PmicGlinkDxe, ProjectInfoDxe, PwrUtilsDxe,
  QcomChargerDxe(QcomChargerDxeLA.inf), RNGDxe(RngDxe.inf), RpmhDxe, SdccDxe, ShmBridgeDxe(ShmBridgeDxeLA.inf),
  SmemDxe, SPIDxe, SPMIDxe, SPSSDxe, TLMMDxe, TsensDxe, TzDxe(ScmDxeLA.inf), TzDxe(TzDxeLA.inf), UCDxe,
  UFSDxe, ULogDxe, UsbConfigDxe, UsbDeviceDxe, UsbfnDwc3Dxe, UsbInitDxe, UsbMsdDxe, UsbPwrCtrlDxe, VcsDxe,
  XhciDxe, XhciPciEmulationDxe`。
- USE_CUSTOM_DISPLAY_DRIVER=0 时：DXE/APRIORI 的 `!if` 分支自动挂 SimpleFbDxe、跳过 DisplayDxe/CPRDxe；
  RAW.inc 的 41 个 panel 段整体被 `!if` 跳过，恒定 3 个 RAW（SecParti.cfg/uefipil.cfg/QcomChargerCfg.cfg）仍编入。
- 二进制补丁提示（阶段 2 后续，非 v1 阻塞）：redwood README 记录的 5 个补丁中 4 个可平移到 ingres 二进制
  （ButtonsDxe 键码、DALSYSDxe cache coherence、TzDxeLA applet=TRUE、UsbConfigDxe 去 deinit、UsbMsdDxe 不可移动位），
  做法 = 二进制 hexpatch + README 记录（ButtonsDxe 在 Binaries/bitra 里有 `.patched.efi` 先例可参照手法）。

### 6.8 `Platforms/OnePlus/phk110Pkg/Library/MemoryMapLib/MemoryMapLib.c`
- 源：ingresPkg 版为骨架。**本文件是最大的真工作量**，规则：
  1. **保留不变的结构**：HYP/DT BLOB/XBL RAMDUMP/AOP/SMEM 高位描述符形态、IMEM 两条、全部 MMIO 行
     （Waipio 外设基址对 Cape 通用；PHK110 的 soc.args 实证 AOSS=0xc300000、APPS_SMMU=0x15000000、
     SMEM=0x80900000、IMEM=0x14600000 —— 其中 AOSS/MMIO 行里 ingres 是 0x0B000000/0x4000000（覆盖到 0xF000000）
     而 Cape AOSS 在 0xC300000，见占位符 P-7）。
  2. **必须按 PHK110 DT 重算的行**（等 wave1-socargs.md，先放占位符）：
     - `HYP`（PHK110 的 hyp 载入地址）
     - `SMEM`（soc.args 实证 0x80900000/0x200000，大概率不用改）
     - `PIL Reserved`、`VM PIL`、`MTE Reserved`、`HYP Reserved`、`OEM VM`（非安全侧载区，按 DT reserved-memory）
     - `TZApps Reserved`（xbl 布局）
     - `Display Reserved`（PHK110 DT `non_secure_display_region` size=0xA400000，ingres 行只有 0x2B00000 → 必改，
        地址取 wave1）
     - `IMEM Base`/`IMEM Cookie Base`（PHK110 soc_imem=0x14600000 ≠ ingres 0x14680000 → 必改，cookie 地址 wave1）
  3. **UEFI 自用簇**（FD Reserved/UEFI FD/UEFI FD Reserved/Info Blk/MMU PageTables/Log Buffer/UEFI Stack/
     SEC Heap/Sched Heap/FV Region/UEFI RESV/DXE Heap）：作为一整块搬迁到一个 PHK110 低 4G 空闲窗口内，
     保持 ingres 的相互偏移布局不变（相邻排布），首地址 = `<FD_BASE>` 占位符；"UEFI FD" 行地址必须 ==
     phk110.toml 的 `uefi_fd.base`，"UEFI Stack" 行 == dsc 的 PcdCPUCoresStackBase，"DXE Heap" 大小 ≥0x7C00000。
  4. **HakiOS 必加行**（照抄 redwood 语法）：`{"XNU Payload", <XNU_PAYLOAD_BASE>, 0x04000000, AddMem, SYS_MEM,
     SYS_MEM_CAP, Reserv, WRITE_BACK_XN}` —— 地址必须与 §6.10 的 XNU_PAYLOAD_BASE 一致且为真实 RAM；
     PHK110 **不能用 redwood 的 0xF0000000**（主 RAM 从 0x800000000 起）。
  5. `Kernel` 行（0xA8000000/0x10000000）：保留语义（XNU 载入区预留），地址归入第 3 条整块搬迁。
- 完成后一致性自检：所有 AddMem/Reserv 行两两不重叠、且落在 wave1 的 System RAM 区间内（写个 10 行 python 对拍）。

### 6.9 `Resources/Configs/phk110.toml`（新文件，全文如下，占位符 2 个）

```toml
#
# Boot Shim Configs
#
[boot_shim]
requires_kernel_header = true

#
# UEFI FD Configs
#
[uefi_fd]
base = <FD_BASE>          # 占位 P-1：必须 == MemoryMapLib "UEFI FD" 行地址（如 ingres 0xA7100000 的同角色值）
size = 0x300000

#
# Android Boot Image Kernel Configs
#
[boot_image_kernel]
kernel_compression = "gzip"
append_dtb         = true

#
# Android Boot Image Configs
#
[boot_image]
header_version = 1        # 与内核仓 mkxnuimg.py 的 --header_version 1 对齐（redwood 同值）
```

### 6.10 `Resources/DTBs/phk110.dtb`（+可选 `phk110.dts`）
- 源：`hakios-phk110/intel/phk110-fdt.dtb`（1,200,263 字节，=live-fdt.dtb 同尺寸）。
- 动作：拷贝并改名 `phk110.dtb`；建议同时存 `phk110.dts` 反汇编（上游 DTBs 目录惯例是 .dtb+.dts 成对，
  用 `dtc -I dtb -O dts` 生成）。
- 用途：build_uefi.py append_dtb=true 时拼进 Mu-phk110.img；HakiOS 正式链用内核仓的 FDT，此处副本保证
  UEFI 单体调试包自洽。

### 6.11 `Binaries/phk110/README.md`（git 唯一可见文件；本体本地填充）
- 撰写要点（仿 `hakios-sm7325/uefi/files/Binaries/redwood/README.md`）：
  - Firmware Infos：**Device: OnePlus Ace 2 (PHK110)**；说明"PHK110 XBL/ABL 经 OPPO sec-boot 加密，无法本地
    UEFIReader 提取；本目录内容系 **Xiaomi Poco F4 GT (ingres) 同硅 SM8475 驱动集**，复制自
    Project-Silicium/Device-Binaries 子模块 `Binaries/ingres`（Binaries @ 9f4dbfd）"；
  - 已知差异/风险（面板 NT37705 不在 panel 集、Oplus 充电协议 vs Qualcomm GLink、side-key 布局）；
  - Patches/Fixes 栏（§6.7 的 4 个平移补丁做了再记，含 patcher 名）。
- 本体填充命令（阶段 2 执行，在 apply.sh 之后的 Mu-Silicium 树里做，或直接拷进设备树）：
  ```bash
  cp -r "$MU/Binaries/ingres/." devices/phk110/uefi/files/Binaries/phk110/   # QcomPkg/ + RawFiles/
  rm  devices/phk110/uefi/files/Binaries/phk110/QcomPkg/XBLCore 2>/dev/null  # XBLCore 无引用，可留可删
  ```
  （注意：拷进 Mu-Silicium 的 `Binaries/phk110/` 位于子模块内未跟踪，不影响主仓；拷进设备树的这份是"正本"。）

### 6.12 条件覆盖：`Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h`（+可能 BootShim 覆盖）
- 事实：全局 overlay `hakios-uefi/files/.../XnuLoader.h` 写死 `XNU_PAYLOAD_BASE 0xF0000000ULL`、
  `XNU_PAYLOAD_MAX_SIZE 0x04000000ULL`；hakios.patch 的 BootShim.S 同样把 XNUP 容器搬到 0xF0000000。
  redwood 的 RAM 顶到 0xC 区域内含 0xF0000000 以下低窗，PHK110 主 RAM 起于 0x800000000 → **0xF0000000 无 RAM**。
- 方案：设备树放同路径 `XnuLoader.h` 副本，改 `XNU_PAYLOAD_BASE` 为 `<XNU_PAYLOAD_BASE>`（占位 P-2，
  = MemoryMapLib "XNU Payload" 行地址；候选：PHK110 低 4G 内 64MB 对齐空闲窗，与 UEFI 自用簇同窗规划；
  apply.sh 拷贝顺序保证设备副本覆盖全局副本）。
- BootShim.S：若 P-2 落点 ≠ 0xF0000000，还需要 `files/BootShim/BootShim.S` 的设备副本
  （用 hakios.patch 版全文 + 改搬移目标常数）。**此项牵动全局启动链，阶段 2 前先和 orchestrator 确认**：
  若 阶段 1-socargs 给出 PHK110 低 4G 确有 ≥64MB 空闲窗（XBL 大多在低 4G 留有大块 frpwst/审计区），只在
  设备树覆盖两个文件即可，零上游改动。
- [待验证 V-3] 见 §8。

### 6.13 kernel 仓配套（2 行 + 0~1 行）
- `tools/provenance.allow` 追加（照 redwood 两行改路径）：
  ```
  pending  devices/phk110/uefi/files/Resources/DTBs/phk110.dtb   the phone's device tree, ... (同 redwood 措辞)
  vendor   devices/phk110/uefi/files/Binaries/phk110/*           UEFI drivers, ingres (SM8475) set from Device-Binaries, ... (措辞注明来源非本机)
  ```
- `devices/manifest.conf`：本地开发不加；开源后补 `device phk110` 块（repository+revision）。

### 6.14 占位符汇总（阶段 1 socargs 产出后回填）

| 占位符 | 所在文件 | 来源 |
|--------|----------|------|
| P-1 `<FD_BASE>`（UEFI 自用簇首址） | phk110.toml `uefi_fd.base` + MemoryMapLib FD 簇 + dsc Stack | wave1-socargs.md：PHK110 低 4G System RAM 空闲 ≥14MB 连续窗（FD 3MB+FD Reserved 2MB+FD Reserved2MB+其余簇 ~7MB）|
| P-2 `<XNU_PAYLOAD_BASE>` | MemoryMapLib "XNU Payload" + XnuLoader.h(设备副本) + (条件)BootShim.S | 同上：64MB 对齐窗；PHK110 主 RAM 0x800000000+，redwood 的 0xF0000000 无效 |
| P-3 `<STACK>` | dsc PcdCPUCoresStackBase | = FD 簇内按 ingres 偏移推出的值（机械推导） |
| P-4 reserved-memory 各行 | MemoryMapLib | wave1-socargs.md 的 reserved-memory 表（hyp/pil/mte/vm/tzapps/demura/qseecom…） |
| P-5 Display Reserved | MemoryMapLib | DT non_secure_display_region（size=0xA400000 已知；地址 wave1） |
| P-6 IMEM/Cookie | MemoryMapLib + ConfigurationMapLib SharedIMEMBaseAddr | soc.args: soc_imem=0x14600000；cookie=wave1 |
| P-7 AOSS 等 MMIO 微调 | MemoryMapLib | PHK110 AOSS=0xc300000（soc.args 实证）；核对 QUP/USB/TLMM/SMMU/APSS_HM 与 wave1 的 soc 外设表 |

---

## 7. 构建链前置清单（跑通 apply.sh phk110 + build_uefi.py -d phk110）

### 7.1 WSL Fedora 44 包（实测 rpm -q）
已有：git 2.56、gcc 16、make、clang 22、llvm 22、lld 22、python3 3.14.8、python3-pip 26、gettext、curl、
gnupg2、libuuid-devel。
**缺（setup_env.sh dnf 清单对照）**：
```bash
sudo dnf install -y nasm gcc-aarch64-linux-gnu
# 可选（mu_nasm 走 NuGet 才需要；用 §7.3 的 nasm 垫片则不必装）：
sudo dnf install -y mono-devel nuget
```
说明：setup_env.sh 的 dnf 行是 `git mono-devel nuget nasm make lld gcc automake gcc-aarch64-linux-gnu
python3 python3-pip gettext gnupg ca-certificates clang llvm curl`；Fedora 上 `gnupg` 包名实为 gnupg2（已有），
uuid 库（Ubuntu uuid-dev）对应 libuuid-devel（已有）。

### 7.2 Mu-Silicium 子模块（6 个，当前只有 Binaries 已初始化）
apply.sh 会 `git submodule update --init --recursive`，覆盖：
`Binaries`（9f4dbfd）、`Common/Mu`（mu_plus release/202608）、`Common/Mu_OEM_Sample`、`Mu_Basecore`
（release/202608）、`Silicium-ACPI`（f50bc115）、`Silicon/Silicium/OpensslPkg/.../openssl`（67b5686b）。
国内网络需给 git 配代理（WSL mirrored 网络已具备）。首次 stuart_setup 还会经 NuGet 拉
`mu_nasm_extdep` 等 extdep（见 §7.3）。磁盘 ~3GB（README 估计）。

### 7.3 Python venv 与 mu_nasm 垫片（ hakios-uefi/README.md 既定流程）
```bash
cd ~/hakios/kernel            # 或存放 Mu-Silicium/ 的父目录
python3 -m venv venv
venv/bin/pip install -r Mu-Silicium/pip-requirements.txt   # edk2-pytool-library 0.23.x / -extensions 0.31.x / antlr4 4.13.2 / regex / pefile / coloredlogs
source venv/bin/activate
```
【风险 V-5】系统 python3=3.14.8 过新，`edk2-pytool-library~=0.23.17` 可能无 3.14 轮子；预案：
`sudo dnf install python3.13`（Fedora 44 提供）→ `python3.13 -m venv venv`。
mu_nasm 垫片（无 Mono 时，README 原方案）：
```bash
D=Mu-Silicium/Mu_Basecore/BaseTools/Bin/mu_nasm_extdep
mkdir -p $D/Linux-x86-64
echo 'version: 20016.1.1' > $D/extdep_state.yaml
ln -s /usr/bin/nasm /usr/bin/ndisasm $D/Linux-x86-64/
```

### 7.4 首跑命令序列
```bash
hakios-uefi/apply.sh phk110                    # 需先有 devices/phk110/uefi/files/（本规格产物）与 hakios-uefi 全局层
cd Mu-Silicium && source ../venv/bin/activate
python3 build_uefi.py -d phk110 -r RELEASE      # 产物 Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd (+ Mu-phk110.img)
```
（正式 XNU 链随后用内核仓 `mkxnuimg.py`/`./xl enter`，吃 Mu-Silicium/ 的 .fd。）

---

## 8. 待验证清单（V-*，每项带验证方法）

| # | 事项 | 验证方法 |
|---|------|----------|
| V-1 | 帧缓冲 PCD 1240×2772×32 | 首次盲启后 XnuLoader stage0 的 logfs/logdump 回读里有 GOP mode 行；或对 phk110-fdt.dtb `strings | grep -i 'dsi\|panel\|2772\|1240'` 交叉确认面板逻辑分辨率 |
| V-2 | PHK110 低 4G 是否存在 ≥64MB 连续可用窗（决定 XNU_PAYLOAD_BASE 与 FD 簇落点） | wave1-socargs.md 的 32-bit 小块清单 + phk110-fdt.dtb `reserved-memory`/`memory` 节点；不行则采用高 RAM 落点方案并改 BootShim.S（PhysAddr 64 位在 BootShim 阶段可用，需确认 ABL 传入的 x0/DT 载入模型） |
| V-3 | 设备副本能否覆盖全局 XnuLoader.h/BootShim.S | apply.sh 拷贝顺序已是"设备最后"（源码确认）；再实测一次 apply 后 `diff devices/phk110/uefi/files/Silicon/.../XnuLoader.h Mu-Silicium/Silicon/.../XnuLoader.h` 应相同 |
| V-4 | ConfigurationMapLib 的 ingres 值在 PHK110 上是否成立（SharedIMEMBaseAddr/DloadCookie/SecPagePoolCount） | 首跑 logfs 回读的 UEFI 日志（SharedIMEM cookie 校验失败会显式打印）；对照内核 soc.args 的 imem=0x14600000 |
| V-5 | venv 在 python 3.14.8 下可装 | 直接装一次；失败按 §7.3 换 python3.13 |
| V-6 | ingres 的 MemoryMapLib FD 簇整体搬迁后 RamManagerDxe/PlatformPeiLib 不再报冲突 | 看 build report（BUILDREPORT_TYPES 含 PCID/FIXED_ADDRESS）+ 首跑日志 |
| V-7 | UsbConfigDxe 未打"去 deinit"补丁时 fastboot 会话后 USB 失联 | 首跑直接以 logfs 回读为验收通道（盲启流程既定），必要时按 §6.7 打补丁 |
| V-8 | Silicium-ACPI 子模块在 BASE f50bc115 处确有 Platforms/Xiaomi/ingres（main 分支在线已确认存在） | apply.sh 后 `ls Mu-Silicium/Silicium-ACPI/Platforms/Xiaomi/ingres/` 应有 AcpiTables.inf/SSDT.asl/SSDT.aml |

---

## 9. 阶段 2 执行顺序建议

1. 等 wave1-socargs.md → 回填 P-1/P-2/P-3~P-7，定稿 MemoryMapLib + toml + XnuLoader.h 设备副本（§6.8/6.9/6.12）。
2. 生成 13 个平台包文件（§6.1–6.7，纯复制+改名，半天量级）+ phk110.dtb（§6.10）+ Binaries/phk110 README 与本地填充（§6.11）。
3. dnf 补装（§7.1）→ apply.sh phk110 → venv（§7.3）→ build_uefi.py -d phk110（§7.4）。
4. build 过后跑 §6.7 自检 + §8 的 V-6/V-8；通过后进入首跑/盲启验收（logfs 回读）。
5. 追加 provenance.allow 两行（§6.13）；manifest.conf 留待开源。

## 附：调查中核实过的关键路径（Windows/WSL）
- WSL：`~/hakios/Mu-Silicium/{build_uefi.py, Platforms/Realme/bitraPkg/*, Platforms/Xiaomi/ingresPkg/*,
  Platforms/OnePlus/salamiPkg/*, Silicon/Qualcomm/{WaipioPkg,QcomPkg,KonaPkg,KailuaPkg}, Binaries/{bitra,ingres},
  Resources/{Configs,DTBs,MuPatches,Scripts,ramdisk}, Silicium-ACPI(未 init), .gitmodules}`
- Windows：`upstream/hakios-uefi/{apply.sh,export.sh,hakios.patch,BASE,README.md,files/...XnuLoader.[ch],branding/banner.py}`、
  `upstream/hakios-sm7325/uefi/files/{Platforms/Xiaomi/redwoodPkg/**, Resources/Configs/redwood.toml,
  Resources/DTBs/redwood.dtb, Binaries/redwood/README.md}`、`upstream/hakios-xnu-kernel/{tools/provenance-check.py,
  tools/provenance.allow, devices/manifest.conf, mkxnuimg.py}`、`intel/{phk110-fdt.dtb, phk110-xbl-a.bin,
  phk110-abl-a.bin, wave1b-scripts/fdt-full.txt}`、`~/hakios/kernel/devices/phk110/{device.conf, soc.args, README.md}`
