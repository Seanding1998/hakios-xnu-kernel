# 阶段 3 · 2026-11-02 · 调研：高通手机用 fastboot boot 引导自制 UEFI 的外部案例

- 研究日期：2026-11-02
- 研究方法：WebSearch + GitHub 源码/文档直读（WebFetch / GitHub API / raw.githubusercontent），全部 URL 均已逐一访问验证（HTTP 200），未编造。
- 标注约定：**[确证]** = 有可复查的外部一手证据；**[推测]** = 基于外部证据的推断，尚无直接案例证明；**[未找到]** = 公开检索未命中。

---

## 0. 一句话结论

PHK110 上存在一个**已公开验证能跑通 Mu-Silicium UEFI 的完整外部项目**（takasugl/uefi-udon + UniXNU-udon，FD 就放在 **0xA7100000**），但其路径是 **flash 进 boot_b + 嫁接原厂 OEM vbmeta/AVB footer**，而不是裸 `fastboot boot`；同一项目对 `fastboot boot` 的多次尝试均复现了与本项目完全相同的"静默冻结、无显示无 USB"症状。因此"0xA7100000 被 OPPO ABL 占用"这一假设被外部证据**削弱**，"PHK110 ABL 对非原厂格式 boot 镜像的 fastboot boot 路径不可靠（需 OEM vbmeta/footer graft 或直接 flash）"成为最强解释。

---

## 1. 六个研究问题的发现与 URL 证据

### Q1：Renegade Project / Mu-Silicium / edk2-msm 在 OPPO/一加 taro（sm8450/sm8475）世代机型上的 boot 案例；一加 ABL 怪癖

**[确证] Mu-Silicium 官方没有任何一加/OPPO 的 taro（sm8450/sm8475）机型平台包。**
- `Platforms/OnePlus/` 下仅有：astonPkg（Ace 3/12R, SM8550, KailuaPkg）、salamiPkg（一加 11, SM8550, KailuaPkg）、dodgePkg（一加 13, SM8750, PakalaPkg）、giuliaPkg（13R/Ace 5）、macanPkg（15R）、paganiPkg（13s）、infinitiPkg（一加 15, KaanapaliPkg）、kebabPkg（8T, SM8250）、lemonadePkg（9, SM8350）、cheeseburgerPkg（5）、enchiladaPkg（6）。
  - https://github.com/Project-Silicium/Mu-Silicium （repo）
  - https://github.com/Project-Silicium/Mu-Silicium/tree/main/Platforms/OnePlus （目录列表）
  - 各 DSC 头可证 SoC 归属，如 aston.dsc 含 `KailuaPkg`（SM8550）、dodge.dsc 含 `PakalaPkg`（SM8750）：https://github.com/Project-Silicium/Mu-Silicium/blob/main/Platforms/OnePlus/astonPkg/aston.dsc
- Status.md 中一加 11（salami）为 Inactive；一加 13（dodge）为 Inactive（但社区实测可跑）：https://github.com/Project-Silicium/Mu-Silicium/blob/main/Status.md

**[确证] PHK110 上唯一公开验证过的自定义 UEFI 项目 = takasugl/uefi-udon（Mu-Silicium 衍生），从 SM8475 "senna_bc" 平台（Realme GT Neo5 / 一加 Ace Pro 家族，senna = SM8475）衍生。**
- uefi-udon README："UEFI, UniXNU, DarwinBoot and the target XNU kernel run on the OnePlus Ace 2 / 11R (PHK110, Udon, SM8475)"、"4 MiB DEBUG FD at 0xA7100000"、"Booted through the boot_b AVB/OEM-footer graft path"、"The stock PHK110 ABL requires the boot image's OEM vbmeta/footer graft"：
  - https://github.com/takasugl/uefi-udon （README）
- UniXNU-udon（配套设备仓库，"OnePlus Ace 2 / PHK110 (Udon) UniXNU device port"）：https://github.com/takasugl/UniXNU-udon
- udon 链路："ABL -> boot_b (Mu-Silicium UEFI + UniXNU + DarwinBoot) -> FAT payload in super -> XNU"：https://github.com/takasugl/uefi-udon/blob/main/docs/STATUS.md

**[确证] 一加 ABL 怪癖（外部一手记录，PHK110 专有）**：
- "Historical PHK110 tests require grafting the stock boot image's OEM vbmeta blob plus a 192 MiB footer before ABL will execute a replacement boot image."（UniXNU-udon bring-up 日志）：https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md
- 无 graft 的镜像经 `fastboot boot` 发送后**不被执行**（设备回到原 boot_b 里的 XNU），带 graft 的镜像过 ABL 后设备**卡死在 Fastboot mode 画面、USB 消失**——与本项目症状同型（同文档 12:52/12:55/13:01 三节）。
- SM8475 上 SMMU 编程会 external abort，udon 固件刻意跳过（BRINGUP 日志 "SMMU programming is deliberately skipped on SM8475 because it caused an external abort"）。

**[确证] 对照案例：一加 13（OPPO ABL/OxygenOS 16，CPH2653）上官方 Mu-dodge.img 可以裸 `fastboot boot` 直接过 ABL 显示 UEFI**——说明 OPPO ABL 并非一律拒绝 fastboot boot UEFI，前提是镜像按该设备官方支持包的格式构建：
- XDA 帖 "My attempts to boot linux"（Attempt 2/3：`fastboot boot Mu-dodge.img` 成功显示 UEFI；Attempt 1：recovery.img 被 ABL 拒绝并回显 `Failed to load/authenticate boot image: Bad Buffer Size`；Attempt 5/6：自打包的任意内核/自制 boot.img → 卡死在 Fastboot mode 画面，需 `fastboot reboot` 救回）：https://xdaforums.com/t/my-attempts-to-boot-linux.4767261

**[确证] Renegade 项目（一代目）对"如何让 ABL 接受自定义镜像"的定性描述**："make our UEFI Firmware look like a Linux kernel ... adding a piece of magic header on top of the image, and also appending device tree to it. In this way, abl will be happy with the provided image"；内存映射参考 xbl 内的 `uefiplat.cfg`；显示复用 XBL 已初始化的 framebuffer（SimpleFbDxe）：
- https://renegade-doc.readthedocs.io/en/latest/edk2/Overview.html
- sdm845 新机型移植流程（DTB 取自 `/sys/firmware/fdt` 或 boot.img-dtb，`fastboot boot boot-CodeName.img` 验证）：https://forum.renegade-project.tech/t/edk2-sdm845-new-device-porting-guide/417
- edk2-msm（Renegade 系）：https://github.com/edk2-porting/edk2-msm
- Project-Aloha mu_aloha_platforms（SM8450 WaipioPkg 的来源，ingres 官方支持的血缘）：https://github.com/Project-Aloha/mu_aloha_platforms

**[未找到]** 任何 OPPO/一加 sm8450/sm8475 机型上"裸 fastboot boot 成功引导自定义 UEFI"的公开案例（一加 13 是 sm8750，且依赖官方 dodge 支持包）。

---

### Q2：Mu-Silicium 官方 OnePlus 平台包的 FD base；BootShim 如何处理加载地址不确定性

**[确证] 全部官方配置（`Resources/Configs/<codename>.toml`）FD base 实测值：**

| 设备 | 机型/SoC | FD base | FD size | boot header | 其他 |
|---|---|---|---|---|---|
| ingres | Poco F4 GT / SM8450(taro, 与 PHK110 同代) | **0xA7100000** | 0x300000 | v4 | gzip + append_dtb |
| kebab | 一加 8T / SM8250 | 0x9FC00000 | 0x300000 | v1 | 同上 |
| cheeseburger | 一加 5 / MSM8998 | 0x9FC00000 | 0x300000 | v1 | 同上 |
| lemonade | 一加 9 / SM8350 | 0x9FD00000 | 0x200000 | v3 | 同上 |
| salami | 一加 11 / SM8550 | **0xA7100000** | 0x300000 | v4 | gzip + append_dtb |
| aston | Ace 3 / 12R / SM8550 | **0xA7100000** | 0x300000 | v4 | 同上 |
| dodge | 一加 13 / SM8750 | **0xA7100000** | 0x300000 | v4 | 同上 |
| giulia | 13R/Ace 5 | **0xA7100000** | — | v4 | 同上 |
| macan | 一加 15R | **0xA7100000** | — | v4 | 同上 |
| pagani | 一加 13s | **0xA7100000** | — | v4 | 同上（Status.md 注明此机要求 ARB Version 1） |
| infiniti | 一加 15 | 0xC6900000 | — | v4 | 同上 |

- URL（raw，逐一验证）：
  - https://github.com/Project-Silicium/Mu-Silicium/blob/main/Resources/Configs/ingres.toml
  - https://github.com/Project-Silicium/Mu-Silicium/blob/main/Resources/Configs/kebab.toml 、`lemonade.toml`、`cheeseburger.toml`、`salami.toml`、`aston.toml`、`dodge.toml`、`giulia.toml`、`macan.toml`、`pagani.toml`、`infiniti.toml`（同目录）
- 全部配置统一为：`boot_shim.requires_kernel_header = true`、`kernel_compression = "gzip"`、`append_dtb = true`（DTB 直接拼接在 FD/gzip 镜像尾部放进 boot.img 的 kernel 槽，而非 mkbootimg --dtb 槽）。构建逻辑见 build_uefi.py（`append_dtb` → `android_kernel.write_bytes(uefi_fd + device_dtb)`）：https://github.com/Project-Silicium/Mu-Silicium/blob/main/build_uefi.py

**[确证] BootShim 对加载地址不确定性的处理**：运行时用 `adr x1, _Payload` 取自身实际落点，与编译期 `FD_BASE` 比较；不等则把 `FD_SIZE` 字节整块搬到 FD_BASE 再跳过去（`_CopyLoop` + `_Entry: br x5`）；ARM64 kernel header 的 Text Offset=FD_BASE、Image Size=FD_SIZE（`REQUIRES_KERNEL_HEADER=1` 时写入）：
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/BootShim/BootShim.S
- 编译参数 `-DFD_BASE=$(FD_BASE) -DFD_SIZE=$(FD_SIZE)`：https://github.com/Project-Silicium/Mu-Silicium/blob/main/BootShim/Makefile
- FD_BASE 最终来源是设备 toml（`uefi_fd.base/size`），经 build_uefi.py 传给 DeviceBuild.py：`BLD_*_FD_BASE`（ingres DeviceBuild.py L160-161）。

**[确证] FD base 的官方选取方法**：移植指南明确"`<FD Base/Size Value>` is the UEFI FD Value in the MemoryMap (uefiplat.cfg)"——即从 XBL 自带的 uefiplat.cfg 内存映射里取 XBL UEFI 自己的 FD 窗口；DTB 取自设备 `/sys/firmware/fdt` 或用 AIK 从 stock boot.img 抽 `boot.img-dtb`：
- https://github.com/Project-Silicium/Guides/blob/main/Silicium/Porting/Snapdragon/Device/README.md

**[确证] PHK110 专用平台包同样使用 FD 0xA7100000**（udon.toml：base=0xA7100000, size=0x400000, v4, gzip, append_dtb, requires_kernel_header=true）：
- https://github.com/takasugl/uefi-udon/blob/main/Resources/Configs/udon.toml
- https://github.com/takasugl/uefi-udon/blob/main/docs/REPRODUCE.md （`FD_BASE=0xA7100000 FD_SIZE=0x400000 FD_BLOCKS=0x400`）

**[确证] marble（SM7475，小米系同代机）侧的 BootShim 教训**：stock BootShim 的 kernel header 只描述了 shim 自己，bootimg 拒收；修复是 header 的 Image Size 改为 `FD_SIZE + _Payload - _Head`（覆盖整个 shim+payload）：
- https://unixnu.com/zh/devices/marble-milacy

---

### Q3：kvm-arm.mode=protected（QHEE/pKVM）对 fastboot boot 自定义 UEFI/内核的影响；小米 vs OPPO 在 waipio/taro 上的 hyp 状态差异

**[确证] `kvm-arm.mode` 的来源与语义**：这是 2021 年加入的内核参数，用于在 none/nvhe/protected（pKVM）间选择，前提是**内核自己拥有 EL2**：
- https://lists.infradead.org/pipermail/linux-arm-kernel/2021-September/681596.html

**[确证] 平台 hypervisor 模型**：在 Qualcomm 平台上 EL2 的主人是平台厂 hypervisor（QHEE/Gunyah），OS 侧内核通过驱动桥接；Android 13 的 AVF 并不强制 pKVM/内核进 EL2。换句话说，cmdline 里的 `kvm-arm.mode=protected` 在 HLOS 于 EL1 运行时并不代表内核控制 EL2（这与本项目中"HLOS 在 EL1"的实测一致）：
- https://threedots.ovh/blog/2023/01/virtualisation-when-you-dont-own-the-hypervisor-android-tales

**[确证] 平台 hyp 会在后期阶段拦截特定操作（小米 marble/SM7475 实例）**：marble 在 Gunyah 下 EL1 写 `CNTP_CTL_EL0` 被 trap 成 UNDEF，需改用 CNTV 的 patch 才能继续——说明平台 hyp 的"存在感"体现在 UEFI/Linux 已跑起来之后的特定 MMIO/寄存器拦截，而不是入口即死：
- https://unixnu.com/zh/devices/marble-milacy

**[确证] PHK110 也有 hyp 区且不妨碍 UEFI**：udon 的 PHK110 内存映射里赫然有 `HYP 0x80000000, 6 MiB` 与 `HYP Reserved 0x830000000, 256 MiB`，而其 UEFI（flashed 路径）照常运行——说明"设备带 QHEE"本身并不杀死自定义 UEFI：
- https://github.com/takasugl/uefi-udon/blob/main/Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c

**[确证] Mu-Silicium/udon 的 SEC 不做 EL 迁移**：WaipioPkg PlatformSecLib 仅做 GIC 唤醒 + MDP SMMU detach，`PlatformHelper.S` 是空实现——该固件不主动退 hyp/切 EL，运行在 ABL 交出的任何状态：
- https://github.com/takasugl/uefi-udon/blob/main/Silicon/Qualcomm/WaipioPkg/Library/PlatformSecLib/PlatformSec.c
- https://github.com/takasugl/uefi-udon/blob/main/Silicon/Qualcomm/WaipioPkg/Library/PlatformSecLib/AArch64/PlatformHelper.S
- （Renegade 定位即"boot any fuOS at EL1"：https://renegade-doc.readthedocs.io/en/latest/edk2/Overview.html ）

**[推测] 若 OPPO ABL 的 fastboot boot 交入状态与 flash boot 交入状态不同（如不同 EL/不同 MMU/sidestate），可以造成"flash 能进 UEFI、fastboot boot 秒死"。目前没有任何外部文档直接描述该差异**——检索 "kvm-arm.mode=protected" 与 "fastboot boot 自定义 UEFI 秒死" 的关联案例：**[未找到]**，无公开案例把 QHEE/kvm-arm.mode 与 fastboot boot UEFI 即死直接挂钩。

**[推测] 小米 vs OPPO hyp 差异**：marble（小米，Gunyah）与 PHK110（OPPO，QHEE + pKVM cmdline）都带平台 hyp；公开证据只能说明两者 hyp 都存在且都能让 UEFI 跑（marble 走 fastboot boot，PHK110 走 flash），差异点更可能落在 ABL 对 fastboot boot 镜像的校验/格式要求（见 Q4），而非 hyp 本身。

---

### Q4：OPPO ABL 已知怪癖（内核加载地址、DTB 来源、oplusboot.*）

**[确证] 内核/镜像加载地址（PHK110 内存地图，来自 udonPkg 官方 memory map）**：
- `Kernel 0xA8000000, size 0x10000000`（与本项目实测 ABL 内核加载地址 0xA8000000 完全一致）
- `DBI Dump 0xA6000000 (0xF00000)`、`FD Reserved 0xA7000000`、`UEFI FD 0xA7100000`、`UEFI FD Reserved 0xA7400000`、`Info Blk/MMU/Log/Stack 0xA7601000-0xA764C000`、`Display Reserved 0xB8000000`、`OEM VM 0xBB000000`、`MTE 0xC0000000`、`TZApps 0xEA000000` 等：
  - https://github.com/takasugl/uefi-udon/blob/main/Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c
- marble 侧低于 4 GiB 的保留区（PIL 0x1C200000@0x85200000、display/Demura 0x2B00000、kernel 0x10000000@0xA8000000、OEM VM、MTE）与 udon 布局一致，可交叉印证 taro 代系布局：https://unixnu.com/zh/devices/marble-milacy

**[确证] PHK110 ABL 对替换 boot 镜像要求 OEM vbmeta + AVB footer graft（192 MiB footer）**，否则不执行；graft 工具 `graft-boot-footer.py` 公开可复用（输入自定义镜像 + stock boot_b，输出带 `AVBf` footer 的镜像）：
- https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md
- https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/graft-boot-footer.py

**[确证] DTB 来源与 dtbo/msm-id 机制（PHK110/cape）**：udon 的自定义 vendor_boot 候选镜像带 `model "OnePlus Ace 2 / 11R", compatible qcom,cape-v2, msm-id <0x21c 0x10000>`（cape = Ace 2 的高通 DTS 名）；其主线内核 reader 经 ABL 拿到的是 **vendor_boot 里的 DTB**（stock vendor DTB 路径"起内核但 console 前挂"的假设后被自证排除——换 custom vendor_boot 仍冻结）。对 UEFI 镜像本身，官方 Mu-Silicium 的做法是 DTB 直接 append 进 kernel 槽（append_dtb=true），不依赖 ABL 传 DTB：
- https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md （"Next physical test" 与 "13:01 custom-vendor reader attempt" 两节）
- append_dtb：https://github.com/Project-Silicium/Mu-Silicium/blob/main/build_uefi.py
- 一加官方 SM8475 内核/DTB 源参考：https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475

**[确证] oplusboot.* 参数（公开 cmdline 样例）**：`oplusboot.mode=reboot`、`oplusboot.prjname=22825`、`oplusboot.serialno=...`（termux 项目的 OPPO 设备 cmdline 转储）；`oplusboot.mode=normal`、`oplusboot.avbkeysha256=...`（CSDN 文档）。语义：Oplus ABL 注入的启动模式/项目号/序列号/AVB key 指纹标记。除 cmdline 转储外无文档级说明：
- https://github.com/termux/termux-packages/issues/19194
- https://wenku.csdn.net/answer/3g8h0mh8jj

**[未找到]** OPPO ABL 源码级文档（oplus ABL 非开源；检索不到 kernel load address 策略的官方说明）。ABL 行为结论全部来自上面的一手逆向/实验记录。

---

### Q5：postmarketOS / 主线 Linux 在一加 Ace 2 / SM8475 / 一加 11 系上的移植与 boot 方案

- **[未找到] Ace 2 / PHK110（udon）没有 postmarketOS 设备页**（pmOS wiki 检索无此机型；"The big list" 类页面亦无 oneplus-udon 条目）。唯一的 Ace 2 主线类项目就是 takasugl/UniXNU-udon（走 UEFI→XNU，不是 Linux/pmOS）：https://github.com/takasugl/UniXNU-udon
- **[确证] 同代/近代一加机型在 pmOS/主线的落点**：
  - OnePlus 13（oneplus-dodge, SM8750）：pmOS wiki 页存在（重定向到 wiki.nura.eco），链接 sm8750-mainline 内核与 UEFI 引导器：https://wiki.postmarketos.org/wiki/OnePlus_13_(oneplus-dodge) 、内核 https://github.com/sm8750-mainline/linux
  - OnePlus 15（oneplus-infiniti）：pmOS wiki 页存在：https://wiki.postmarketos.org/wiki/OnePlus_15_(oneplus-infiniti)
  - OnePlus Ace 3 / 12R（aston, SM8550）：pmOS 列表中标 "in testing"（经 Mu-Silicium aston 条目跳转确认）；第三方主线工程 https://github.com/jiganomegsdfdf/aston-mainline
  - 一加 11（salami）：**无** pmOS 主线移植（仅 Android ROM 开发生态）：https://xdaforums.com/t/rom-unofficial-lineageos-20-for-oneplus-11.4609069 、https://github.com/OnePlus-11-Development/android_device_oneplus_salami
- **[确证] "一加 ABL 直启主线内核（无 UEFI）"的正面案例**：OnePlus 7T Pro（hotdog）项目直接从一加 ABL 启 header-v2 主线 Linux 进 postmarketOS（USB 网络、SSH、A/B slot 成功标记全自动）。重要怪癖：**需要先刷一次 LineageOS 再回 OxygenOS，某持久化改动是启动成功的必要条件**（原因未明，作者在查）：
  - https://github.com/Sr-0w/hotdog-linux-bringup
- **[确证] 一加系"boot.img 里带 DTB + fastboot boot"的主线启动说明书**（OnePlus Pad Pro/caihong, SM8650 的 LKML cover letter 含 mainline-boot.img + dtbo + fastboot 步骤，可作 taro 世代参照）：https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2505.3/00889.html
- **[确证] lemonadep（一加 9 Pro）pmOS 主线 boot 失败的归因讨论**（v3/v4 头 boot/vendor_boot 分割、deviceinfo 缺失）：https://gitlab.postmarketos.org/postmarketOS/pmaports/-/work_items/4498

---

### Q6：「自定义镜像 fastboot boot 静默秒死、原厂正常」的社区通用排查法

汇总外部社区反复出现的可复用手法（均有 URL）：

1. **让镜像"看起来像内核"**：Renegade 的根基做法——UEFI 前加 ARM64 kernel header（Text Offset/Image Size）、尾部 append DTB，让 ABL 按 Linux kernel 路径接收：https://renegade-doc.readthedocs.io/en/latest/edk2/Overview.html
2. **bootimg header 版本与地址字段**：marble 实测 **v4 镜像 ramdisk 加载不可靠，工作版本是 Android v0：kernel 0x80008000、160 MiB payload 放 0xA8000000-0xB2000000、DTB 放 boot.img**；并且 kernel header 的 Image Size 必须覆盖 shim+payload 全长，否则 bootimg/ABL 处理不全：https://unixnu.com/zh/devices/marble-milacy
   - udon 的 reader 构建脚本同时支持 v0 与 v3/v4（v0 时保留输入的 kernel_addr/tags/page 字段）：https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/build-linux-log-boot.py
3. **AVB/vbmeta**：常见法是 `fastboot flash vbmeta vbmeta.img --disable-verity --disable-verification`；PHK110 特化法是 **OEM vbmeta blob + 192 MiB footer 嫁接**（udon graft-boot-footer.py，见 Q4）：https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/graft-boot-footer.py
4. **换路径验证**：同一镜像"fastboot boot 不行就 flash 到当前 slot 试"——udon 正是靠 flash boot_b + graft 拿到唯一成功路径：https://github.com/takasugl/uefi-udon/blob/main/docs/STATUS.md
5. **ABL 错误串监听**：一加 13 上 ABL 会回显 `Failed to load/authenticate boot image: Bad Buffer Size`；镜像过 ABL 但卡死时屏幕停在 "Fastboot mode" 静态画面（此时 fastboot 已死，USB 消失），需 `fastboot reboot`/强拆电池重启：https://xdaforums.com/t/my-attempts-to-boot-linux.4767261
6. **拿早期日志**：pstore/last_kmsg 回退（ABL 回落 fastboot 时可 `fastboot oem` 拉 pstore）与 XBL/ABL ULog 显示驱动（Daniel-Abrecht 给 Mu-Silicium 写的 ULogDxe 把 XBL 日志直接画屏，调试利器）：https://xdaforums.com/t/phone-always-boot-to-fastboot-after-flashing-custom-kernel-from-twrp.3902470 、https://github.com/Daniel-Abrecht/Mu-Silicium/tree/ULogDxe
7. **内存映射对齐**：FD base/大小必须与 xbl uefiplat.cfg 的 MemoryMap 对齐（官方移植指南）；自定义 MemoryMap 参考同 SoC 已验证平台：https://github.com/Project-Silicium/Guides/blob/main/Silicium/Porting/Snapdragon/Device/README.md
8. **fdisk/分区类事故规避**（marble 教训：勿 `fastboot flash userdata` 硬塞大镜像）：https://unixnu.com/zh/devices/marble-milacy

---

## 2. 最可能解释本项目现象的外部案例 TOP3

### TOP 1：PHK110 ABL 的 fastboot boot 路径对非原厂格式镜像不可靠（需 OEM vbmeta/footer graft；最稳路径是 flash boot_b）——udon/UniXNU-udon 全套案例
- **证据**：udon 项目在 PHK110 上 UEFI 跑通的唯一路径是 `ABL -> boot_b（flash + AVB/OEM-footer graft）`；同一团队多次 `fastboot boot`（无 graft：镜像不被执行、静默回退；有 graft：ABL 放行后设备冻结在 Fastboot 画面、无显示无 USB）——**与本项目"原厂 boot_a 秒回安卓、自定义 UEFI 秒死且死在一切输出之前"的表型完全同构**。
- **对本项目假设的影响**：这是目前唯一针对 PHK110 的一手实验记录，直接把嫌疑从"FD 地址"挪到"ABL 接收路径/镜像格式"。
- URL：https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md 、https://github.com/takasugl/uefi-udon

### TOP 2：镜像格式细节（header 版本、Image Size 完整性、gzip+append_dtb、DTB 归属）——marble + 一加 13 + Mu-Silicium 官方配置三角印证
- **证据**：marble 证明 v4 的 ramdisk 路径不可靠、v0+kernel 0x80008000 才稳，且 BootShim header 必须声明完整长度；一加 13 证明 OPPO ABL 会给"格式不符"的镜像回 `Bad Buffer Size` 或直接静默冻结；Mu-Silicium 全部一加配置统一 v4+gzip+append_dtb+requires_kernel_header（即 header 声明 FD_BASE/FD_SIZE）。任何一处与 ABL 期望不符 → ABL 传完即死，无任何输出。
- URL：https://unixnu.com/zh/devices/marble-milacy 、https://xdaforums.com/t/my-attempts-to-boot-linux.4767261 、https://github.com/Project-Silicium/Mu-Silicium/blob/main/Resources/Configs/ingres.toml

### TOP 3： ingres（同硅 Poco F4 GT）官方 UEFI 的"可 fastboot boot"属性绑定在**小米 ABL**上——换到 OPPO ABL 的 PHK110 上即失效；OPPO ABL 的接收要求由 udon 的 graft 记录给出
- **证据**：ingres 官方 toml FD=0xA7100000/v4 与 PHK110 完全同参，但小米 ABL 的 fastboot boot 校验路径宽松（marble 同为小米系，v0 镜像可 fastboot boot）；OPPO 系（PHK110）由 udon 记录了 graft 要求与 fastboot boot 冻结史。一加 13 则证明"OPPO ABL + 官方支持包格式的 Mu-Silicium"可以 fastboot boot——所以变量既不是 SoC 也不是 hyp，而是**每台设备 ABL 对镜像的验收逻辑 + 是否存在该设备的官方支持包**。PHK110 无官方包，一切格式的 fastboot boot 都无先例可循。
- URL：https://github.com/Project-Silicium/Mu-Silicium/blob/main/Resources/Configs/ingres.toml 、https://github.com/takasugl/uefi-udon/blob/main/docs/STATUS.md 、https://xdaforums.com/t/my-attempts-to-boot-linux.4767261

**被削弱的原假设**："`0xA7100000` 被 OPPO ABL 占用/保护，BootShim 覆盖它即死" —— **[推测，证据反方]**：uefi-udon 的 PHK110 UEFI FD 就放在 0xA7100000 且跑通（flash 路径）；其 MemoryMapLib 显式把 0xA7000000-0xA7FFFFFF 规划为 FD/FD Reserved（BsData），0xA8000000 才是 Kernel 区。0xA7100000 在 PHK110 上被 ABL 实际占用/保护的直接证据**未找到**。但注意：该结论只覆盖 flash 路径；若 OPPO ABL 在 fastboot boot 路径把 0xA7100000 用作暂存/重叠区，仍可解释差异——此为**推测**，无外部证据。

---

## 3. 行动建议（按性价比排序）

1. **[最高性价比] 复刻 udon 已验证路径：放弃裸 `fastboot boot`，改走"graft + flash boot_b"**
   - 用 udon 公开的 `graft-boot-footer.py` 把本项目 BootShim+FD boot.img 与 stock boot_b 备份做 OEM vbmeta + 192 MiB footer 嫁接，先试 `fastboot boot <grafted.img>`（udon 证明 graft 后 ABL 会放行到执行阶段）；若仍冻结，直接 `fastboot flash boot_b <grafted.img>`（已备份原 boot_a/b，可恢复）。这是外部唯一在 PHK110 上被证明能进 UEFI 的路径。
   - URL：https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/graft-boot-footer.py 、https://github.com/takasugl/uefi-udon
2. **[廉价] 对齐官方镜像格式四件套**：boot header v4（PHK110 原厂即 v4）+ kernel gzip + append_dtb（PHK110 cape DTB 拼 FD 尾）+ BootShim `REQUIRES_KERNEL_HEADER=1` 且 header 的 Image Size = 完整 shim+payload（marble 教训）。逐项 diff 本项目镜像与官方 Mu-Silicium 产物。
   - URL：https://unixnu.com/zh/devices/marble-milacy 、https://github.com/Project-Silicium/Mu-Silicium/blob/main/build_uefi.py
3. **[廉价] 建 A/B 变体矩阵**：同固件分别打 v4 与 v0（kernel 0x80008000、payload 0xA8000000 窗口）两个 boot.img，都试 fastboot boot——marble 证明 v4 ramdisk 路径不可靠时 v0 能救。
   - URL：https://unixnu.com/zh/devices/marble-milacy
4. **[中等] 打通更早的观测通道再盲试**：把 XBL/ABL 的 ULog 画屏（Daniel-Abrecht 的 ULogDxe 思路）或 SEC 阶段直接写 ABL splash framebuffer（udon/官方 Mu-Silicium 均复用 splash buffer 出 GOP）做进固件首指令；目标是区分"ABL 未放行"还是"SEC 即死"。
   - URL：https://github.com/Daniel-Abrecht/Mu-Silicium/tree/ULogDxe 、https://github.com/takasugl/uefi-udon/blob/main/docs/STATUS.md
5. **[中等] 直接采纳 uefi-udon 的 udonPkg 资产**：其 PHK110 memory map、ConfigurationMap、vendor 模块清单（Binaries/udon：UFS/USB/显示/PMIC/TLMM/SPMI/GLink/clock，来源必须是 PHK110 自己的 ABL dump）与 FD 配置完全公开；本项目自适配固件可与其逐文件 diff，重点比对 MemoryMapLib 与 SEC/APRIORI。
   - URL：https://github.com/takasugl/uefi-udon/blob/main/docs/REPRODUCE.md 、https://github.com/takasugl/uefi-udon/blob/main/Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c
6. **[中等] DTB 策略**：boot.img 自带 DTB（append_dtb）为第一优先；如仍死，再临时 flash custom vendor_boot（cape-v2, msm-id 0x21c 0x10000，udon 的 vboot_e1_custom 模板）做隔离测试——但注意 udon 已证 stock vendor DTB 不是唯一死因，测试后立即还原 stock vendor_boot_b。
   - URL：https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md
7. **[低/长期] 联系 takasugl / UniXNU 社区**（Telegram @unixnu）：对方持有 PHK110 的完整 vendor 模块与 graft 经验，是唯一复现过"PHK110 ABL 放行替换镜像"的活跃方。
   - URL：https://github.com/takasugl/UniXNU-udon
8. **[不推荐先做] QHEE/hyp 侧攻关**：无任何外部案例支持"kvm-arm.mode=protected 是直接死因"；PHK110 带 hyp 且 UEFI 可跑（udon）。除非 1-6 全部排除，不值得投入。

---

## 4. 确证 / 推测 分项标注

**确证（有可复查一手证据）：**
- Mu-Silicium 官方一加/小米全机型 FD base、header 版本、gzip/append_dtb/requires_kernel_header 配置（toml 一手源码）。
- BootShim 的自搬移逻辑与 ARM64 header 语义（BootShim.S/Makefile 一手源码）。
- PHK110 存在已跑通的 Mu-Silicium UEFI（uefi-udon），FD=0xA7100000/0x400000，显示 1240×2772，走 flash boot_b + AVB/OEM-footer graft。
- PHK110 ABL 对替换镜像的 OEM vbmeta + 192 MiB footer graft 要求；无 graft 的 fastboot boot 镜像不被执行；graft 后 fastboot boot 过 ABL 但冻结（无 USB/无 console）。
- PHK110 内存布局：Kernel=0xA8000000(256 MiB)、FD=0xA7100000、HYP=0x80000000、DBI Dump=0xA6000000（MemoryMapLib.c）。
- SM8475 上 SMMU 编程会 external abort，udon 刻意跳过。
- 一加 13（OPPO ABL）：官方 Mu-dodge.img 可裸 fastboot boot 进 UEFI；任意自制 boot.img / raw kernel fastboot boot → 冻结在 Fastboot 画面；recovery.img → ABL 回显 Bad Buffer Size。
- marble（小米 SM7475）：v4 镜像 ramdisk 不可靠、v0+0x80008000 工作布局成立；BootShim header 长度修复；Gunyah trap CNTP。
- FD base 官方选取法 = xbl uefiplat.cfg 的 UEFI FD 窗口；DTB 取 /sys/firmware/fdt 或 boot.img-dtb。
- oplusboot.* 参数公开样例（mode/prjname/serialno/avbkeysha256）。
- pmOS：无 Ace 2/PHK110 页面；有 OnePlus 13/15 页面；一加 11 无主线移植；hotdog 一加 ABL 直启主线需先刷 LineageOS 的持久化怪癖。
- FD base=0xA7100000 亦为小米 ingres/同代 marble 官方与 UniXNU 移植采用值。

**推测（基于外部证据推断，未直接证明）：**
- PHK110 ABL fastboot boot 与 flash boot 两条路径在 EL/内存状态/校验逻辑上存在差异，是本项目"flash 可行、fastboot boot 秒死"差异化的机制（无外部直接描述，但 udon 行为高度暗示）。
- OPPO ABL 可能在 fastboot boot 时把 0xA7100000 附近区域作他用（原假设的残存版本；flash 路径已证明该地址可用，此说法仅剩 fastboot 路径的可能性空间）。
- `kvm-arm.mode=protected`/QHEE 直接导致 UEFI 入口即死——**无任何外部案例支持**，且 udon（同机、同 hyp 环境）flash 路径可跑，优先级应排最低。
- "Bad Buffer Size" 类 ABL 拒收逻辑在 PHK110 上同样存在（一加 13 观察外推）。

**未找到（明说）：**
- OPPO/一加 taro 世代机型上"裸 fastboot boot 成功引导自定义 UEFI"的公开案例（一加 13 为 SM8750 且靠官方支持包）。
- OPPO ABL 内核加载地址策略的官方/源码级文档（只有 udon memory map 与本项目实测可对照）。
- 把 `kvm-arm.mode=protected` 与 fastboot boot 自定义镜像死亡直接关联的任何公开案例。
- PHK110/udon 的 postmarketOS 页面或主线 Linux（pmOS）移植。

---

## 附：本次研究全部一手 URL 清单

**Mu-Silicium 官方**
- https://github.com/Project-Silicium/Mu-Silicium
- https://github.com/Project-Silicium/Mu-Silicium/tree/main/Platforms/OnePlus
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/BootShim/BootShim.S
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/BootShim/Makefile
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/build_uefi.py
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/Resources/Configs/ingres.toml （kebab/lemonade/cheeseburger/salami/aston/dodge/giulia/macan/pagani/infiniti.toml 同目录）
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/Status.md
- https://github.com/Project-Silicium/Mu-Silicium/blob/main/Platforms/OnePlus/astonPkg/aston.dsc
- https://github.com/Project-Silicium/Guides/blob/main/Silicium/Porting/Snapdragon/Device/README.md

**PHK110 一手案例（udon）**
- https://github.com/takasugl/uefi-udon
- https://github.com/takasugl/uefi-udon/blob/main/docs/STATUS.md
- https://github.com/takasugl/uefi-udon/blob/main/docs/REPRODUCE.md
- https://github.com/takasugl/uefi-udon/blob/main/Resources/Configs/udon.toml
- https://github.com/takasugl/uefi-udon/blob/main/Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c
- https://github.com/takasugl/uefi-udon/blob/main/Silicon/Qualcomm/WaipioPkg/Library/PlatformSecLib/PlatformSec.c
- https://github.com/takasugl/UniXNU-udon
- https://github.com/takasugl/UniXNU-udon/blob/main/docs/BRINGUP-2026-10-25.md
- https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/graft-boot-footer.py
- https://github.com/takasugl/UniXNU-udon/blob/main/package/linux-log/build-linux-log-boot.py

**对照设备案例**
- https://unixnu.com/zh/devices/marble-milacy （marble/SM7475，小米，FD 0xA7100000 + v0 fastboot boot 工作布局 + Gunyah trap）
- https://xdaforums.com/t/my-attempts-to-boot-linux.4767261 （一加 13/SM8750，OPPO ABL fastboot boot 全记录）
- https://github.com/Sr-0w/hotdog-linux-bringup （一加 7T Pro，ABL 直启主线 + LineageOS 持久化怪癖）
- https://github.com/jiganomegsdfdf/aston-mainline （Ace 3/12R 主线）

**Renegade / 项目生态**
- https://renegade-doc.readthedocs.io/en/latest/edk2/Overview.html
- https://forum.renegade-project.tech/t/edk2-sdm845-new-device-porting-guide/417
- https://github.com/edk2-porting/edk2-msm
- https://github.com/Project-Aloha/mu_aloha_platforms
- https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475

**hyp / pKVM**
- https://threedots.ovh/blog/2023/01/virtualisation-when-you-dont-own-the-hypervisor-android-tales
- https://lists.infradead.org/pipermail/linux-arm-kernel/2021-September/681596.html

**oplusboot.* 与 misc**
- https://github.com/termux/termux-packages/issues/19194
- https://wenku.csdn.net/answer/3g8h0mh8jj
- https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2505.3/00889.html
- https://gitlab.postmarketos.org/postmarketOS/pmaports/-/work_items/4498
- https://wiki.postmarketos.org/wiki/OnePlus_13_(oneplus-dodge) （重定向 wiki.nura.eco）
- https://wiki.postmarketos.org/wiki/OnePlus_15_(oneplus-infiniti) （重定向 wiki.nura.eco）
- https://github.com/Daniel-Abrecht/Mu-Silicium/tree/ULogDxe
- https://github.com/sm8750-mainline/linux
- https://xdaforums.com/t/phone-always-boot-to-fastboot-after-flashing-custom-kernel-from-twrp.3902470 （pstore 排查）
