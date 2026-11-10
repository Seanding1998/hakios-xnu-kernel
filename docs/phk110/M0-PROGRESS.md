# HakiOS → PHK110（一加 Ace 2 / SM8475 "Cape"）移植项目 — M0 进度存档

> ⚠️ **当前状态请读 [`STATUS.md`](STATUS.md)**（权威快照，2026-11-03 起）；本文件保留为编年体全记录，用于细节查找。文档索引见 [`README.md`](README.md)。

> 更新：2026-11-02 15:30 · 状态：M0 情报采集基本完成，可行性已确认，尚未做任何改动手机的操作
> 续接入口：先读本文件 → `docs/port-pkg110.md`（上游移植实录，金矿）→ `docs/porting/index.md`（官方 5 步移植法）

## 使命

用户目标：在一加 Ace 2 (PHK110) 上跑 HakiOS（XNU on Android 手机）。用户已授权 AI 主导开发（"你来主导开发！tokens不是问题！"）。
手机是用户主力机：**任何 fastboot boot / 重启操作必须先获得用户明确同意**；绝不 flash 任何分区。

## 已确认的设备事实（全部实测）

| 项 | 值 | 来源 |
|---|---|---|
| SoC | **SM8475**（骁龙 8+ Gen 1），高通代号 **Cape**，平台 `taro` | getprop + cmdline |
| 板级 DT | `qcom,cape-mtp qcom,cape qcom,mtp`，model "Cape MTP, **Udon**"，prjname=22803，board-id=0x01000800 | /proc/device-tree |
| **BL 真实状态** | **`oplusboot.verifiedbootstate=orange` = 已解锁**（getprop 的 green/locked 是 Magisk 系伪装）| /proc/cmdline（resetprop 伪造不了）|
| 面板 | `mdss_dsi_oplus22803_nt37705_1240_2772_dsc_cmd`（NT37705 DDIC）| cmdline msm_drm.dsi_display0 |
| 触摸 | **Synaptics S3910** | cmdline oplus_bsp_tp_custom |
| 内存 | 12GB+：32 位区 0x808f4000~0xffffffff + 64 位区 0x800000000~0x8382fffff、0x840000000~0xb7fffffff | /proc/iomem |
| FDT | ✅ 已提取：`intel/phk110-fdt.dtb`（1200263 字节，含 __symbols__）| /sys/firmware/fdt |
| 分区 | 标准 QC taro A/B：abl/hyp/devcfg/xbl 全套，boot_a/b，dtbo_a/b，logdump 等 | /dev/block/by-name |
| 串口 | cmdline 有 `console=ttyMSM0` 但 `msm_geni_serial.con_enabled=0`；有 EUD 调试子系统 | cmdline + iomem |
| Magisk | 30.7，`su -c` 免弹窗；BL 解锁推导依据与上游 pkg110 实录一致（同类 root 必须解锁 BL，伪装靠 tricky_store/resetprop）| handoff + pkg110 文档 |

## 仓库与架构（Explore agent 已完成内核分析，结论存档）

工作区 `hakios-phk110/upstream/`：已克隆 hakios-xnu-kernel、hakios-uefi、hakios-sm7325、hakios-metal（均 depth 1）。

- 分层：**common**（内核补丁+通用驱动+xnuloader）/ **SoC 层**（soc.conf+configs+soc.args）/ **device 层**（device.conf+UEFI Pkg+pull 脚本）/ UEFI（Mu-Silicium + hakios.patch + 设备 files/）
- 内核编译为**通用 ARM64 板**（BCM2837 board config + PAN），无 per-SoC 代码；**SoC 差异全走 boot-args `soc_*`**（`tools/soc-args.py` 从手机 FDT 生成）
- 启动链：`fastboot boot` → Android bootimg（gzip(BootShim + MuSilicium UEFI FD + XNUP payload) + 手机 DTB）→ UEFI → xnuloader（扮演 iBoot，构造 Apple 格式 DTB + 原生 boot_args）→ XNU Mach-O
- 大小核已支持（loader DT `small-core` 属性 + boot-arg `small_cores=N`）；Qualcomm hypervisor 下 EL1 + HVC PSCI 是显式设计；PAC/MTE 未启用（无需）
- ARMv8.2 PAN 要求 Cortex-X2/A710/A510 全部满足 ✅
- 产物：payload 为 XNUP 容器；手机镜像用 `mkxnuimg.py` 打 bootimg，`fastboot boot` 进 RAM，不碰分区

## UEFI 层关键事实

- Mu-Silicium 真身：**github.com/Project-Silicium/Mu-Silicium**（WOA-Project 是错的，404）。默认分支 main，活跃（2026-11-01 有推送）
- hakios-uefi/BASE 钉住 commit `e51cd877e31c8fbb322032dc4cb6715e83d25ad3`；`apply.sh` clone→checkout→submodule→patch→拷设备 files/
- Qualcomm silicon 包清单（API 已核验）：KodiakPkg（=SC7280，redwood 用的）、**WaipioPkg（=SM8450，taro 家族，SM8475 的最近亲）**、LahainaPkg、KailuaPkg、NapaliPkg、PalawanPkg、Cape 专属包**不存在**
- → phk110Pkg 应建模自 **WaipioPkg**（SM8475 在 BSP/主线生态里大量复用 waipio/taro 平台驱动）
- 设备 UEFI 需要厂商 Binaries（display/touch 等预编译驱动，从 OEM 的 abl/UEFI 提取，root 手机可拉）——参考 sm7325 `uefi/files/Binaries/redwood/README.md` 的补丁记录（ButtonsDxe/DALSYSDxe/TzDxeLA/UsbConfigDxe 等，社区已知修法）

## 已知硬骨头（按风险排序）

1. **NT37705 面板** UEFI 驱动（需从 OnePlus abl 提取 Binaries + 可能打补丁）
2. **Adreno 730（a7xx）**：redwood 是 a6xx/a660，GPU 驱动 + Mesa freedreno 侧都要动；第一阶段可先 UEFI framebuffer 显示、GPU 延后
3. **Synaptics S3910 触摸**：新驱动（参照 `drivers/*/hakios.*` 模式，Goodix 是范本）
4. **IPA v5**（SM8475）vs IPA 4.11（SC7280）：蜂窝网大移植，redwood 上蜂窝也只是 partial，可最后做
5. cpufreq EPSS：taro 寄存器兼容，频率表要换
6. Darwin 用户空间：用户需自备 IPSW（Darwin 16.5），unpack 流程 pkg110 实录已验证

## 环境盘点（本机）

- **WSL Fedora 44**：gcc 16.2.1 ✅、Python 3.14.8 ✅、git/make ✅、磁盘 953G 空闲 ✅；**缺 clang/llvm/lld（XNU 构建必需）** → `dnf install clang lld llvm ldid?`（ldid 也没有）；EDK2 构建在 Linux 用 GCC 亦可
- Windows Git Bash：git ✅、fastboot 37.0.1 ✅、adb ✅；**python3 是 Store 空壳**（用 WSL 跑 python，或 `python`）；flock 无 → 用仓库自带 `tools/win-bin/flock` shim
- pkg110 实录指路：构建放 WSL ext4（~/hakios），别放 /mnt/d（APFS 解包文件名含 `:` NTFS 不允许 + drvfs 慢）；成品拷回 Windows 侧给 `xl` 用
- ⚠️ D: 盘和 WSL ~/hakios 目前都是空的——pkg110 实录是上游维护者机器上做的，本机要从零建（但工具链脚本已全在仓库里）

## UEFI Binaries 现状（M1.6 关键发现，2026-11-02）

- **xbl_a 已加密**（OPPO sec-boot）：3 个链式 ELF，主体 5.7MB 段 phnum=0/熵 7.0，无明文 FV。**xbl_config_a 同样加密**
- **abl_a 未加密**：ARM ELF，含 1 个 EFI_FV（LZMA 压缩）；UEFIReader 提取结果 = 仅 LinuxLoader.efi（ABL 本体），**无平台 DXE 驱动**
- redwoodPkg 需要的厂商 Binaries（Binaries/redwood/QcomPkg/Drivers/）：EnvDxe、ShmBridgeDxeLA、ScmDxeLA、TzDxeLA、ChipInfoDxe、PlatformInfoDxe、ProjectInfoDxe、DALSYSDxe、HALIOMMUDxe、HWIODxe、ClockDxe、DisplayDxe、UsbConfigDxe…（全部来自 XBL 的 DXEFV）
- **绕行策略（按优先级）**：
  1. 查 Mu-Silicium 是否有这些 DXE 的开源重实现（克隆进行中）
  2. 小米 SM8450/8475 机型（cupid 等）公开 fastboot 固件的 xbl.img **不加密** → SoC 级通用 DXE 可提取（显示驱动除外，面板不通用）
  3. Moto edge 30 Ultra/X30 Pro（SM8475 精确同硅）固件 dump 作候选
  4. DisplayDxe（NT37705 面板专属）是真正的难点；第一里程碑可盲启（无显示）+ 依赖 logfs/logdump 分区回读日志（UEFI 常驻 logfs 服务，手机分区表里有 logfs/logdump ✓）
- 提取工具链已就绪：UEFIReader（.NET，DOTNET_ROLL_FORWARD=LatestMajor 跑在 .NET 10 上）已构建成功并验证可用

## M1 完成（2026-11-02 15:55，全链路验收通过 ✅）

```
make qemu-open: XNULOADER v3 → XNU 22.5.0 (DEVELOPMENT_ARM64_BCM2837) → 25 drivers → hello 用户态 → 正常 reset
hakios-kernel = 15.7MB Mach-O；构建中踩坑：libuuid-devel（host 工具）、xnu-deps stage2 顺序、QEMU 10 需要 64MB pflash（Fedora edk2 3MB → truncate+dd 填充 EFI64.fd/vars64.fd，QEMU_EFI/QEMU_VARS 需绝对路径）
```
- WSL 构建树：`~/hakios/kernel`（工作树）；产物已同步到工作区 `device-layer/`（hakios-kernel、payload.bin、phk110/ 设备层、qemu-open.log）
- **M1.5 已完成**：`devices/phk110/` 骨架生成（device.conf + configs/phk110_defconfig + configs/phk110.config + soc/{soc.conf,configs/sm8475.config} + soc.args + README）；FDT 识别 "Cape MTP, Udon"；21 个手机驱动按渐进法暂缓
- sm8475 SoC 层待填充：CONFIG_BOOTCPU=7（已定）、3银+4金+1超大拓扑；4 个缺失 soc_*（soc_cmd_db/soc_mpss_mem/modem_ipa_fw_at/soc_pas_mpss）要从 FDT reserved-memory 手工解析（soc-args 对 Cape FDT 的节点名不识别）

## M1.6 结论：SM8475 UEFI 驱动源已解决 ✅

- **xbl_a/xbl_config_a 已加密**（OPPO sec-boot，ELF#2 phnum=0 熵 7.0，无明文 FV）；abl_a 未加密但只有 LinuxLoader.efi（ABL 本体）
- **破局点**：Mu-Silicium 的 `Binaries` 子模块（github.com/Project-Silicium/Device-Binaries.git，78 台设备）里有 **bitra（Realme GT Neo 3 = SM8475 精确同硅）**全套：`Binaries/bitra/QcomPkg/Drivers/` 50 个厂商 DXE（ChipInfoDxe/UFSDxe/DALSYSDxe/TzDxe/ScmDxeLA/RpmhDxe/PmicDxeLa/CmdDbDxe/DisplayDxe/UsbConfigDxe/ButtonsDxe/...含 OplusProject.inf —— Realme 与一加同属 Oplus 系）
- **平台包模板**：`Platforms/Realme/bitraPkg/`（bitra.dec/.dsc/.fdf/DeviceBuild.py + Include/APRIORI|DXE|RAW.inc + Library/）→ phk110Pkg 照此改造
- 遗留难点：DisplayDxe 面板库是 bitra 的（非 NT37705）→ 首阶段可盲启（logfs/logdump 分区回读日志，UEFI 常驻 logfs 服务，本机分区表有 logfs+logdump ✓）；NT37705 面板序列后续从一加同系固件/逆向获取
- UEFIReader 已构建可用（.NET 10 + DOTNET_ROLL_FORWARD=LatestMajor）
- Mu-Silicium 已克隆：~/hakios/Mu-Silicium（294MB；子模块 Binaries 已 init；构建还需 init Common/Mu、Mu_Basecore 等其余子模块）

工具链明细：WSL Fedora 44（.wslconfig 已加 `networkingMode=mirrored`，修复 WSL 直连）；clang 22.1.8 / LLD / DTC 1.8.1 / QEMU 10.2.2 / nasm / libuuid-devel；theos 865MB（本体 + iPhoneOS16.5.sdk sparse + toolchain/linux/iphone 117 个 cctools 二进制）

## PHK110 实测 soc.args（tools/soc-args.py 对本机 FDT 的输出，2026-11-02）

```
soc_ipa_base=0x3e40000   soc_gsi_base=0x3e04000   soc_ipcc=0xed18000
soc_aoss=0xc300000       soc_rsc=0x17a20000       soc_apps_smmu=0x15000000
soc_smem=0x80900000      soc_imem=0x14600000      soc_ipa_stream=0x5c0
soc_ipa_stream_uc=0x5c2  soc_pas_ipa=0xf          soc_ipa_fw=ipa_fws
```
与 redwood 参考值的关键差异：IPA 基址 0x1e4→0x3e4 万段、IPCC 0x408000→0xed18000、RSC 0x18220000→0x17a20000、IPA stream 0x480→0x5c0、固件名 yupik_ipa_fws→ipa_fws（确认 IPA v5 家族）。
**缺失项（Cape FDT 节点名不同，M2 需手工补）**：soc_mpss_mem、modem_ipa_fw_at、soc_pas_mpss、soc_cmd_db。

## PHK110 CPU 拓扑（FDT /cpus 实测，2026-11-02）

| 频率域 | CPU | MPIDR | capacity-dmips-mhz | 核心 |
|---|---|---|---|---|
| 0 | cpu0/1/2 | 0x0/0x100/0x200 | 1024 | 银核 A510 ×3 |
| 1 | cpu3/4/5/6 | 0x300–0x600 | 2253 | 金核 A710 ×4 |
| 2 | **cpu7** | 0x700 | **2386** | **超大核 X2 → CONFIG_BOOTCPU=7**（与 redwood 相同）|

compatible 全部为 qcom,kryo（通用名），cache 子节点为 arm,arch-cache。
解析脚本：`intel/dump_cpus.py`（FDT 属性 walker，已修对齐 bug，可复用于其他 DT 节点分析）。

## 手机当前状态（本阶段全程只读）

- 无线 ADB `192.168.43.29:42621` 在线（端口会漂移，`adb mdns services` 重发现；配对已永久，无需重配）
- 已做：getprop / cmdline / iomem 读取；fdt、xbl_a、xbl_config_a、abl_a **只读拷贝**到 /data/local/tmp 并拉回本地（intel/）；无重启、无写入、无 fastboot
- opencli 浏览器会话 `main`（profile z9xxjp2g）保持 bind

## 上机战役实录（2026-11-02 晚，Boot #1-6 全记录）

| # | 镜像 | 通道 | 结果 | 学到 |
|---|---|---|---|---|
| 1 | xnu-phk110.img（HakiOS 全链） | fastboot boot | 静默挂死，USB 僵尸 D00D | 死在 USB 重枚举之前 |
| 2 | Mu-ingres.img（上游官方） | fastboot boot | 同上 | **不是我们包的问题，是公共层** |
| 3 | stock boot_a（原厂对照） | fastboot boot | ✅ 秒回安卓 | **ABL 通道完全正常** |
| 4 | Mu-phk110-grafted | fastboot boot | ABL 验收过了！执行后弹回异常 fastboot（USB 全消失）| **footer 是第一道门** |
| 5 | 同 #4 但 flash boot_b + set_active b | flash 路线 | 仍死 | FD 本体（ingres 衍生）不适配本机 |
| 6 | **udon-uefi-grafted.img**（udonPkg 重建） | **flash boot_b + set_active b** | ✅✅ **UEFI 活了！用户确认"进去了"** | 外部验证路线复现成功 |

### 三层根因链（全部闭环）
1. **OPPO ABL 拒绝无 AVB footer 的镜像** → 解法：UniXNU-udon 的 `graft-boot-footer.py`（原厂 vbmeta blob 原样搬运 + footer 重写，非伪造签名）
2. **graft 后裸 `fastboot boot` 仍不可靠**（udon 同款中间态）→ 唯一验证路径 = **flash boot_b + graft + set_active b**
3. **ingres(Poco F4 GT) 衍生的平台包不适配 PHK110** → udonPkg（takasugl/uefi-udon，同机已验证、公开源码）才是正确底座；Binaries 用公共 senna_bc（OnePlus Ace Pro 同硅同族）

### 本机环境专项修复（都已完成）
- WSL 网络：.wslconfig `networkingMode=mirrored`
- Windows libusb/fastboot 全盲（Zadig WinUSB/oem63 绑定、管理员、非沙箱、37/34 双版本均无效；火绒退出也无效）→ **绕行：usbipd-win 已装，手机 USB attach 到 WSL 用 Linux fastboot（root）** —— 这是本机唯一可用的 fastboot 通道
- 驱动安装参考：intel/usb-driver/（Zadig 2.9 + Google USB Driver + libusb 1.0.27）
- adb 现在走 USB（serial SERIAL_REDACTED），WiFi ADB 备用

### 外部参考项目（金矿级）
- **takasugl/uefi-udon**：PHK110 专用 Mu-Silicium 平台包（udonPkg，公开源码，MemoryMapLib 含已验证的 MTE Reserved 0xC0000000/512MB、Kernel 0xA8000000/256MB）
- **takasugl/UniXNU-udon**：同机跑通 XNU 的完整实现；`docs/BRINGUP-2026-10-25.md` = 方法论金矿；`package/linux-log/graft-boot-footer.py` = footer graft 工具
- 一加 GPL 内核源码：OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475（面板 dtsi + S3910 触摸源码副本已在 intel/wave1b-scripts/）

### 当前手机状态（本节末尾）
- **slot b 活动**，boot_b = udon-uefi-grafted.img（UEFI 能启动但无 payload 会挂引导）；boot_a = 原厂安卓未动
- **回安卓**：强关 → 按住电源+音量下 → fastboot → `fastboot set_active a` → reboot
- 手机目前在 fastboot 待命（用户手动进入）

### Wave 5 ✅（Boot #7，2026-11-02 深夜）
`udon-hakios-grafted.img`（payload@0xF4000000）刷写结果：**UniXNU 菜单出画**（显示/USB PHY/菜单全工作）→ 选 Return to firmware → **XnuLoader 触发 → 内核日志上屏滚动** → CPU exception（EDK2 CpuExceptionHandlerLib.c:438）冻结。USB gadget 只收中断不对外枚举。logdump 全零（冻结早于落盘）。
报错定位：`ConvertPages a1000000-a196aff` = EDK2 Page.c:688（良性）；`usb start failed` = loader.c:3676（良性）；**exception 根因 = loader 平台表无 SM8475 → 回落 qemu-virt 几何 → 内核在真机访问错误地址**。

### Wave 6 刷写 = Boot #8 ✅（2026-11-03，重大突破）
`udon-hakios-grafted-v2.img` flash boot_b + set_active b：**全链贯通**——UniXNU 菜单出画（显示/USB PHY/菜单全工作，用户拍照实证）→ 选 Return to firmware → **XnuLoader 触发 → 内核日志上屏滚动 → 干净返回**（无异常！）。logdump 首次落盘成功，全日志回读：
```
platform phk110 ✓  CurrentEL=1 ✓  MIDR=410fd463(boot核心=A510)
core 700: the firmware answers 0（PSCI 唤醒 X2 成功）✓
jumping to 8434194a8 → kernel returned: log 717B（走 loader_return 正常路径）
```
已知残留：①内核日志未随 logdump 落盘（loader 只写自己的 4096 块）②loader USB gadget start failed（良性）③每轮复位后 ABL fallback 回安卓（~3 轮后）。

### Wave 7（进行中，后台子代理）
**免刷写迭代基建**：① XnuLoaderMain 挂点从 UnableToBoot 前移到 AfterConsole 尾部（跳过 UniXNU 菜单，全自动进加载器）② payload 加 `--usb` 驻留标志 → loader 进入 USB fastboot 命令服务器稳定驻留 → 之后内核迭代全走 `fastboot stage payload.bin` + `oem run` + `get_staged log.txt`，**零刷写零手动**。主代理职责收敛为：分析/记录/编排。
`platform_phk110` 平台表 +22 行（FB key 0xB8000000 从 SimpleFb.c 源码确认、GIC 0x17A00000/17A60000、core_shift=8 由 FDT cpu@700 决定性证实、cmdline 追加 cpus=8 bootcpu=7）；**发现并修正拓扑认知**：三组证据（EPSS freq-domain、idle-states、SM8475 官方规格）指向 **4 小核(cpu0-3)+3 大核+1 prime**，与早前 capacity 值读出的 3+4+1 矛盾 → small_cores=0x0f 暂定，标待真机 MIDR 验证。产物 `device-layer/udon-hakios-grafted-v2.img`（sha256 6fb33fc1…，21/21 自检，commit 574fa69）。**刷写等用户**；预期 banner `platform phk110` + `display 1240x2772 at b8000000` + `core 700: the firmware answers`。回退：重刷 backups-slotb/backup-boot_b.img。

- 无线 ADB `192.168.43.29:42621` 在线（端口会漂移，`adb mdns services` 重发现；配对已永久，无需重配）
- 本次会话对手机**只做过读取**（getprop/cat/ddt 拷贝到 /data/local/tmp 的 fdt 副本），无任何重启/写入
- opencli 浏览器会话 `main`（profile z9xxjp2g）保持 bind 在 github.com/oosexgang
