# F16 调研报告：红米 K60（mondrian / SM8475）项目普查 + 同机型（PHK110 / udon）公开活动普查

日期：2026-11-10 ｜ 执行：F16 调研（纯调研：零手机、零刷写、零构建）｜ 方法先例 = F15（fork 网络普查）
工具链：GitHub REST/raw + git shallow clone（Mu-Silicium / edk2-msm / UniXNU-mondrian / uefi-mondrian / MiCode mondrian-s-oss，全部代理 127.0.0.1:7897）+ unixnu.com 设备目录 + WebSearch ×2；含追加任务"同机型普查"（追加任务）
产出：本报告（git commit，message 前缀 "F16 research:"）+ `f16-scripts/progress.log`

> 证据分级沿用 F14/F15：**[实证]** = 文件/commit/页面可复现来源；**[实测转述]** = 作者文档/控制台自述的真机结果（我们未复现）；**[推断]** = 类比/待核。

---

## 0. 摘要（判定先行，七条）

1. **硬件口径 = 证实，但只对 K60 标准版成立**：**K60 = mondrian = SM8475（骁龙 8+ Gen 1，cape 家族）= 与 PHK110（udon）同 SoC** [实证]：MiCode 厂方内核分支 `mondrian-s-oss`（5.10 GKI，`MSM_ARCH=mondrian`）的 `modules.list.msm.mondrian` 同列 `pinctrl-cape.ko`/`phy-qcom-ufs-qmp-v4-cape.ko` 与 waipio 底座模块（cape = SM8475，waipio=SM8450 的衍生）；LOS wiki mondrian 页 = "Redmi K60 + POCO F5 Pro 双变体共板"。**K60 Pro = socrates = SM8550**（MiCode 分支 `socrates-t-oss` + LOS wiki "SM8550 Snapdragon 8 Gen2"）；**K60E = rembrandt = MediaTek mt6895-common 树（MTK）**——任务书猜测的 "coriander" 在 MiCode 分支、LOS wiki、GitHub 设备树三处均不成立（K60E 设备树三仓一致写 rembrandt）。用户"K60 和我们一样的 CPU"说法**正确**。
2. **"GitHub 上有项目" = 证实且超预期**：K60（mondrian）至少有 **三条独立移植线 + 4 个 fork**：① **Emilelu/UniXNU-mondrian**（最深：**2026-11-07 已把 iOS 16.6.1（20G81）跑到用户态首帧**——XNU→launchd→SpringBoard/backboardd 链活着，1440×3200 出画、MiniIOMobileFramebuffer 60 fps、屏幕可见 iOS 启动进度条，发布 3 个 boot 镜像；唯一阻塞 = launchd pid1 SIGSEGV 循环复位）[实测转述，证据密度高]；② **XTOM0706/ios-sweet-k60**（HackiOS/ios-sweet 线）；③ **Amor1120iy/hakios-mondrian**（oosexgang 式设备仓，全实测口径，驱动层"partial/missing 为主"）。
3. **Mu-Silicium 上游全扫（90 设备包逐目录过）零 mondrian 命中**（Xiaomi 目录 36 包亦无；顺带复核无 raphaelPkg、nuwaPkg=小米 13 Pro/SM8550 与 F15 勘误一致）。但 **SM8475 硅包 = PalimaPkg 在上游**（SOC_TYPE 0=8475@3.0G、1=8475@3.2G、2=SM7475-AB；SMBIOS PartNumber="SM8475"），上游挂三台 SM8475 真机：**pongPkg（Nothing Phone 2：Windows Boot ✅ + Linux Boot ✅，Inactive）、senna_bcPkg（Realme GT Neo5 150W：UEFI 显示/存储/按键 ✅，Win/Linux ❌，Active）、b4qPkg（Galaxy Z Flip4：Windows Boot ✅，需 BIT-10，Inactive）**；SM7475 侧 senna_a/marble 均仅 UEFI。**K60 的 UEFI 包在 Emilelu fork**：`Emilelu/uefi-mondrian` = Mu-Silicium 衍生树 + `Platforms/Xiaomi/mondrianPkg`（UEFI 启动链/显示/按键 ✅，vendor DXE 有意剔除，2026-10-27 状态）。
4. **Renegade 系（edk2-porting）有 SM8475 但休眠且无 K60**：edk2-msm 有 `Silicon/Qualcomm/sm8475` + 唯一设备 `Platform/Xiaomi/sm8475/yudi`（小米 Pad 6 Max 14），提交全部落在 **2023-08-20～09-02**（"soc:sm8475 test (8plus gen1)"起），骨架级（内存图/PEI/PrePi/SMBIOS，无面板/USB 驱动证据），此后三年零提交。无 mondrian、无 OnePlus sm8475、无 Windows 启动证据。
5. **SM8475 已成"移动黑果"主力 SoC**：unixnu.com 社区设备表在案 **9 条 SM8475/SM7475 条目**（diting、liuqin、**mondrian×5 源**、rmx3551、thor、udon（我们）、unicorn×2、zizhan、pong 双列；marble=SM7475×3）；散装搜索另见 6+ 独立仓：**qiumochen/UniXNU-zizhan**（MIX Fold 2，iPadOS 18.7.10 内屏+触摸+**Adreno 730 渲染**，derived from UniXNU-pong）、**Yu-DaTouX/hakios-thor**（12S Ultra，"iOS 16.5 home screen and touch"，RAM-only）、**SFZ97/UniXNU-thor**、zhouzhoublm 三仓（12S Pro unicorn：hakios+UniXNU+uefi）、cotunjr/hakios-mayfly（12S）、1696108518/iPadOS-liuqin（fork 自 **dipa-studio/ios-sweet**，1344 星基座）。
6. **同机型（PHK110/udon）普查 = 一个休眠先驱 + 我们独苗**：**boomoodxf/UniXNU-ace2**（2026-10-26 单日 push，此后零推送）= 唯一他人在 PHK110 上的公开移植：Mu-Silicium 系 `uefi-ace2` overlay，达成 UEFI 启动→UniXNU 菜单→DarwinBoot 校验→**4.75 GiB 高内存窗**→XNU entry（绿条、不回 Android），但 **XNU console 未捕获、UFS/launchd/UI 全 ❌**；谱系 = 设备层复制 UniXNU-liuqin、内存用 sheng 的 BootMemoryDxe（`ShengBootMemoryDxe` 发高 bank 0x840000000+5GiB）。unixnu.com 的 udon 条目**只有 takasugl/UniXNU-udon（我们）**；Mu-Silicium/Renegade/hackios fork 网络均无 udon；中文平台无 Ace 2 具体出圈（smzdm 只把 **Ace 2 Pro** 列入"求适配"讨论）。**判定：我们是 PHK110 上唯一活跃在案移植；boomoodxf 是休眠先驱，值得挂监控而非对标**。相邻活动（非 iOS 线）：cooolxuuun/ace2-kernel-build(-v2)（Android 内核 DroidSpaces 构建，10-25/10-30）、Forenche/android_kernel_oneplus_sm8475（2024 WIP 旧）、lizj55785578/PHK110-PPS（充电，无关）。
7. **时间线判定**：SM8475 生态的爆发集中在 **2026-10-23～11-09**（dipa-studio/ios-sweet 10-23、boomoodxf 10-26、Emilelu 仓群 10-28～11-09、Amor 11-08、qiumochen/zhouzhoublm 11-05~09）——与 F14/F15 发现的"官方 org 沉默 ≠ 生态沉默"同构：这波在 **UniXNU/ios-sweet 两条非 oosexgang 系谱**上发生，我们此前监控面（oosexgang org + takasugl + unixnu 设备页按条目）对"unixnu.com 社区表的行数增长"没有锚点，F16 起建议把"unixnu.com /devices 表 SM8475 行数"纳入双周扫。

---

## ① 硬件口径核实（厂商/设备树为权威，逐项）

| 机型 | 厂内代号 | SoC | 证据 | 判定 |
|---|---|---|---|---|
| **红米 K60** | **mondrian** | **SM8475（骁龙 8+ Gen 1，cape）** | ① MiCode/Xiaomi_Kernel_OpenSource 分支 `mondrian-s-oss`（tip 989b27a，2023-05-06 "Kernel: Xiaomi kernel changes for Redmi K60 Android S"，5.10，`build.config.msm.mondrian`: `MSM_ARCH=mondrian`、BOOT_IMAGE_HEADER_VERSION=3）② `modules.list.msm.mondrian` 含 `pinctrl-cape.ko`、`phy-qcom-ufs-qmp-v4-cape.ko`（cape=SM8475 专有）+ `gcc-waipio.ko`/`dispcc-waipio.ko`/`pinctrl-waipio.ko`/`qnoc-waipio.ko`（waipio=SM8450 底座复用，cape 为其衍生）③ LOS wiki `/devices/mondrian/` = 变体页 "POCO F5 Pro + Redmi K60 共用同一 LOS 构建"；搜索摘要引 LOS 变体页配置 "骁龙 8+ Gen 1 (SM8475)" [实测转述] ④ Amor1120iy/hakios-mondrian README："`mondrian`, SM8475 'cape'/'cape-v2', 1×X2+3×A710+4×A510, Adreno 730, 1440×3200, UFS" | **与 PHK110 同 SoC 成立** |
| 红米 K60 Pro | socrates | SM8550（骁龙 8 Gen 2，kailua） | ① MiCode 分支 `socrates-t-oss` ② LOS wiki socrates 页 = "SM8550 Snapdragon 8 Gen2" | **不同 SoC**（但属 Mu-Silicium KailuaPkg 系，与 nuwa/salami 同族） |
| 红米 K60E | **rembrandt**（**不是 coriander**） | MediaTek mt6895-common（Dimensity 8200 族） | ① MiCode 分支表无 coriander、无 rembrandt（MTK 不入 MiCode）② LOS wiki coriander = 404 ③ GitHub 设备树三仓一致："Redmi K60E (rembrandt)"（mominqimiang TWRP 树、AviumUI-Devices rubens 共享树、ProjectRembrandt 树 lineage-23.0），其 `device.mk` 头行 "**Inherit from mt6895-common**" | **完全出圈**（非高通），本轮不再深挖；"coriander" 口径在全部权威源缺席，判定任务书猜测有误 |

**附**：任务书"先核现代号"一项的 mondrian/socrates 两枚均被 MiCode 分支名直接证实；F15 §5.3 的 nuwaPkg 误报勘误（nuwa=小米 13 Pro/SM8550）在本轮 unixnu.com 表（nuwa SM8550）与 Mu-Silicium KailuaPkg 系归属再次复核一致。

---

## ② Mu-Silicium（Project-Silicium）全量扫

本地浅克隆 @73daadd（2026-11-09 push，#2184）grep 全树。

- **全景**：`Platforms/` 12 个 OEM 目录共 **90 个设备包**（Asus 1 / LG 2 / Lenovo 2 / Motorola 2 / Nintendo 1 / Nothing 2 / OnePlus 11 / Qualcomm 1 / Realme 4 / Samsung 22 / **Xiaomi 36** / ZTE 1）；`Silicon/Qualcomm/` 26 个硅包（Blackbolt…Waipio）。全树 grep `sm8475|mondrian|redmi k60` 命中面 = pong/senna_a/senna_bc/b4q/marble/PalimaPkg **六处，无任何 mondrian/K60 条目**；Xiaomi 36 包清单复核：无 mondrianPkg、无 raphaelPkg（F15 结论复核通过）、nuwaPkg 在列（=SM8550 系）。
- **PalimaPkg（SM8475/SM7475 硅包）**：`Silicon/Qualcomm/PalimaPkg/PalimaPkg.dsc.inc` —— SOC_TYPE **0 = SM8475 @3.00 GHz**、**1 = SM8475 @3.20 GHz（OC）**（SMBIOS `PcdSmbiosProcessorPartNumber|"SM8475"`）、**2 = SM7475-AB（骁龙 7+ Gen 2 @2.91 GHz）**；ACPI OEM revision 0x8475 / 0x7475；GICD 0x17100000 / GICR 0x17180000（与我们 udon 的口 径同值）。
- **上游 SM8475 设备三台**（Status.md 逐行）：

| 设备 | 包 | 状态 | UEFI 关键项 |
|---|---|---|---|
| Nothing Phone (2) (pong) | pongPkg | **Inactive**；**Windows Boot ✅、Linux Boot ✅** | Display/UFS/按键/USB device/Mass Storage ✅；USB host/PD ❌。Windows 侧仅存储/CPU/USB host/显示 ✅（触摸/WLAN/GPU/音频/相机 ❌）；Linux（sm8450-mainline "tyalie" 树）侧触摸/电池/GPU/充电/NFC/手电 ✅ |
| Realme GT Neo5 150W/240W/GT3 (senna_bc) | senna_bcPkg | **Active** | Display/UFS/按键/USB device/Mass Storage ✅；**Windows Boot ❌、Linux Boot ❌** |
| Galaxy Z Flip 4 (b4q) | b4qPkg | Inactive；**Windows Boot ✅**（要求 BIT-10 版本；UFS 接管需特殊安装流程） | Display/UFS/按键 ✅、USB device 需启动后重插 |
| （SM7475 侧：GT Neo5 SE senna_a、Poco F5 marble） | senna_aPkg / marblePkg | Active / Inactive | 仅 UEFI 基础五项 ✅，Win/Linux 均 ❌ |

- **OnePlus 目录 11 包**（aston/cheeseburger/dodge/enchilada/giulia/infiniti/kebab/lemonade/macan/pagani/salami）**无 udon**（我们的 PHK110 不在上游）。
- **K60 UEFI 包的真实位置 = Emilelu fork**：`Emilelu/uefi-mondrian`（@1a7afe7，2026-11-07 push）自述 "Derived from Project-Silicium / Mu-Silicium; the platform package is `Platforms/Xiaomi/mondrianPkg`"。其 Status（2026-10-27）：UEFI 启动链 ✅（ABL→`fastboot boot`→BootShim→SEC/PEI/DXE/BDS→UniXNU 菜单）、显示 ✅（ABL splash fb + SimpleFbDxe GOP，**无 GPU 驱动**）、按键 ✅（官方 KeypadDeviceDxe + `K60KeypadDeviceLib`，SPMI PON/GPIO）、AdvLog ✅、60 s 无按键自动回 fastboot；**SMEM/时钟/PMIC/UFS/充电等 vendor DXE 全部有意剔除**（最小 DXE 路线）。XNU payload 当时 TODO——其后由 UniXNU 装载器路线补上（见 §④）。

---

## ③ Renegade / Renegade-project 系

`Renegade-Project` org 仍在（login renegade-project，id 89634282）；现役主仓 = `edk2-porting/edk2-msm`（@e195262，最后 push 2026-03-07，Merge PR #440 nabu）。

- **SM8475 命中两处**：`Silicon/Qualcomm/sm8475/`（仅 14 文件：DeviceConfigurationMap.h、MsPlatformDevicesLib、PlatformMemoryMapLib、PlatformPeiLib、PlatformPrePiLib、SOCSmbiosInfoLib、sm8475.dec）+ `Platform/Qualcomm/sm8475/sm8475.dsc/.fdf` + 唯一设备 `Platform/Xiaomi/sm8475/yudi.dsc`（`PcdDeviceProduct|"Pad 6 Max 14"`、`PcdDeviceCodeName|"yudi"`）。
- **时间线**：commit 全集 = 2023-08-20 "soc:sm8475 test (8plus gen1)"、"Initial Xiaomi pad 6 max (yudi) supports"、"yudi:fix errors"，至 2023-09-02 "fix dtb file" 止——**三年零跟进，骨架级，无面板/USB/存储驱动证据，无任何启动证据**。
- **无 mondrian/K60**、无 OnePlus sm8475（Platform/Oneplus 止步 sm8250）。**判定：Renegade 线对本任务无增量**。

---

## ④ UniXNU 系 + hackios fork 网络

### 4.1 unixnu.com 社区设备表（SM8475 全行）

`unixnu.com/devices/`（VitePress 静态表）：**diting SM8475×1、liuqin SM8475×1、mondrian SM8475×5、rmx3551 SM8475×1、thor SM8475×1、udon SM8475×1（= takasugl/UniXNU-udon，我们）、unicorn SM8475×2、zizhan SM8475×1、pong SM8250+SM8475**；marble=SM7475×3；对照 SM8550×12、SM8450×2。模型页 `unixnu.com/devices/models/mondrian` 列出五仓：**Emilelu（Record pending）、mzyxsl、wohusaixing、XTOM0706、ZxbMsl160918（四仓 "Porting record" 在站）**。

### 4.2 Emilelu/UniXNU-mondrian（K60 主线，最深）@f048a92（2026-11-07）

- **口径**："Redmi K60（mondrian，SM8475）的 UniXNU 设备支持仓"，schema_version=2 四层合并（ARM64→SoC→OS→设备），输出 `out/mondrian/ipados-16.6.1-20G81/`。
- **当前状态（README 2026-11-07）[实测转述]**：
  - **"iOS 16.6.1（20G81）已启动到用户态首帧"**：启动链 XNU→`launchd`→SpringBoard/backboardd/containermanagerd/mediaserverd 全活；显示 `K60 DISPLAY: first frame presented (swap 1, 1440x3200 canvas on 1440x3200 panel)`，之后 MiniIOMobileFramebuffer 稳定 60 fps，屏幕可见 iOS 启动进度条。
  - **唯一阻塞**：launchd（pid 1）SIGSEGV（`KX! 50 1 launchd ... sig=11 code=0xb`）→ XNU 按设计 "pid 1 exited" panic 复位循环；崩溃地址尚未抓到。
  - 发布镜像三枚：`boot-0408/0409/0410-20261107.img`（首帧+SpringBoard 存活口径）。
- **porting.toml（权威设备记录）要点**：
  - **CPU device-verified**：8 核、Android 设备树 MPIDR 平铺 0x000..0x700 经 PSCI 全核启动；board dts 曾覆盖 cpu 节点致固件 target 表/复位向量失配——修法 = 删覆盖继承 SoC dtsi；启动路径换 **Darwin 24 first-boot**（`pong_cpu_first_boot*`，取自 pong）后绕过 `cpu_common.c:586` 断言。
  - **内存 implemented**：实机读出 6 条 RAM bank、**4..32 GiB 有 28 GiB 洞**；12 GiB 单窗不可达（DarwinWindowSizeValid 上限 8 GiB）；实测 4.75 GiB 高窗 pin（commit 5e97e9d "pin measured 4.75 GiB high memory window"）、8.625 GiB arena + 7 GiB 窗可过（HANDOFF EXIT RETURN 0）。
  - **GPU/Metal planned**（"GPU submissions complete… Metal client presents it" 为完成判据，未达成）；另有 host-verified / planned 若干区。
  - **诊断探针族**（0347/0348/0354/0362）：`K60PANICFMT`（panic 串+caller）、`K60KEXC`（pid/pc/lr/esr/far）、`K60KFRAME`（帧指针回溯六帧）、`K60NULLENTRY`（无 ExpansionData 的 IORegistryEntry）——"把静默复位变成每次可定位故障"。
  - **fork 协作工程化**：`scripts/audit-forks.py` 枚举公开 fork 与全部分支、钉比较 SHA、报告候选但不执行合并；已吸收 mzyxsl 76552b88 的"源代码-only 离线路径/证据检查器"；`docs/FORK-REVIEW.md` / `docs/BOOT-STALL-2026-10-31.md` 在案。
- **四层仓**：框架 `Emilelu/UniXNU`（"Run iOS and macOS on non-Apple ARM64 hardware through UEFI"，Python，pushed 11-07）、SoC `Emilelu/UniXNU-sm8475-common`（soc.toml / configs/sm8475.config / dts/sm8475.dtsi）、设备本仓（`patches/xnu/series` **182 项 16.6.1 补丁**、userland、`porting.toml`）、UEFI `Emilelu/uefi-mondrian`（§②）。
- **pong 资产复用**：`chore(lock): add PongUfs source pin c959284`、`feat(xnu-0232): pong adreno ramoops bridge`、`pong-unixnu.patch`/`pong-payload.patch` 入仓；另有 `Emilelu/PongUfs`（10-29）。
- **约束两条（README 明文）**：payload boot-arg **≤600 字符**（预编译 loader 超限即 `Bad Buffer Size` 零启动）；payload FAT 用已验证基座组装+读回校验。

### 4.3 另两条 K60 线

- **XTOM0706/ios-sweet-k60**（独立仓，非 GitHub fork，C，pushed 2026-11-01）："HackiOS / ios-sweet port bring-up for Redmi K60 (mondrian, SM8475) — patched shim, hardware map, cape board prep"。XTOM0706 同时维护 UniXNU / UniXNU-mondrian / UniXNU-sm8475-common 副本（fork 自 Emilelu 线）。"ios-sweet" 基座 = **dipa-studio/ios-sweet**（"iOS 16 userland + XNU on Redmi Note 10 Pro (sweet, SM7150)"，**1344 stars**，pushed 10-23）——与 oosexgang/hakios 平行的另一支大系谱 [谱系细节未深挖，见 §⑦]。
- **Amor1120iy/hakios-mondrian**（pushed 2026-11-08）："HakiOS device repository for the Redmi K60 (mondrian, SM8475 / cape)"。oosexgang 式设备仓（device.conf / soc.args / metal.args / uefi/ / prebuilt/ / pull-firmware.sh / FLASHING.md）。**全部数字从手机实测**（固件 `mondrian_images_OS3.0.8.0.VMNCNXM` 的 vendor_boot dtb/dtbo/boot header + root 后实机 thermal_zone/kgsl/vendor 固件目录）。`device.conf` 逐行状态：display partial（UEFI fb 1440×3200，无 panel/backlight/DSI）、touch **missing（Goodix m11a @QUP4，gpio16-19 irq21 reset20 avdd71——"驱动的引脚是 POCO X5 Pro 的"）**、cpu partial（8 核；EPSS @0x17d91000，MC3/SH5 内存投票，未运行）、gpu missing（Adreno 730；"hakios-metal 只认识 0x06030500，hakios.adreno.c 只认识 642L"）、storage partial（UFS @0x1d84000，"与参考机同 phy"，未见读出）、audio missing（AW882XX 功放）、haptic missing（PM8350B hv-haptics）、torch missing（PM8350C）、**wifi missing（WCN6856；参考机是 WCN6750——ath11k 但固件/BDF 不同）**、cellular missing（modem @0x8bc00000、IPA @0x3e00000，地址在驱动未上）、**thermal works（tsens @0xc263000/0xc265000 与参考机同址；32 通道 SM8475 map，`thermal_map=sm8475`）、其余 missing**。FLASHING.md 含分区 SHA-256 级实测表。

### 4.4 hackios fork 网络

`oosexgang/hakios-xnu-kernel /forks?sort=newest` 前 40：**无 mondrian/k60/udon/phk110 命名 fork**（设备名 fork 在场者：bramble=Pixel 4a 5G、a52sxq、garnet、thyme 等）。oosexgang org 本体 7 仓（main=redwood/sm7325、mtk 线、uefi、metal、web、userland）无 SM8475 条目。

---

## ⑤ 散装项目与 SM8475 生态全景（GitHub 搜索 API + WebSearch）

| 仓 | 设备/SoC | 状态口径 | 最后活动 |
|---|---|---|---|
| Emilelu/UniXNU-mondrian（+4 fork） | K60 / SM8475 | iOS 16.6.1 用户态首帧 | 11-09 |
| XTOM0706/ios-sweet-k60 | K60 / SM8475 | HackiOS/ios-sweet bring-up | 11-01 |
| Amor1120iy/hakios-mondrian | K60 / SM8475 | 设备层+实测表，多数 missing | 11-08 |
| qiumochen/UniXNU-zizhan | MIX Fold 2 / SM8475 | **iPadOS 18.7.10 内屏+触摸+Adreno 730 渲染**（derived from UniXNU-pong） | 11-09 |
| Yu-DaTouX/hakios-thor | 12S Ultra / SM8475 | "iOS 16.5 home screen and touch, RAM-only" | 11-03 |
| SFZ97/UniXNU-thor | 12S Ultra / SM8475 | iPadOS 18.7.10 | 11-05 |
| zhouzhoublm/hakios-xnu-kernel + UniXNU-unicorn + uefi-unicorn | 12S Pro / SM8475 | 双线三仓 | 11-05~06 |
| cotunjr/hakios-mayfly | 小米 12S / SM8475 | drivers/UEFI/findings/logs | 11-01 |
| 1696108518/iPadOS-liuqin | Pad 6 Pro / SM8475 | fork 自 dipa-studio/ios-sweet | 11-08 |
| dipa-studio/ios-sweet | Note 10 Pro / SM7150 | **1344 星基座**：iOS 16 userland+XNU | 10-23 |
| edk2-porting/edk2-msm（yudi） | Pad 6 Max / SM8475 | 休眠骨架（2023） | 2023-09 |
| boomoodxf/UniXNU-ace2 | **PHK110 我们机型** | 见 §同机型 | 10-26 |

**中文社区面（WebSearch）**：UniXNU 被中文圈描述为"UEFI 引导的移动黑果，思路同 OpenCore"（X 帖 huozhemeta）；HakiOS 于 2026-10 开源出圈（linux.do t/3058807、知乎/CSDN 解析、smzdm 报道）；smzdm 讨论区被点名的"想刷机型" = 小米 6、红米 K70、OPPO Find X9U、**一加 Ace 2 Pro**——**未見 K60 或 Ace 2（标准版）的具体视频/帖子命中**；另有"红米 K90 Pro Max 跑 iOS 17"博主传闻 [实测转述，超本轮范围]。F15 教训（视频先于代码）适用：中文平台深查列为后续事件驱动项。

---

## §同机型普查（追加任务：PHK110 / Ace 2 / udon 上有没有别人在做）

**判定：一个休眠先驱（boomoodxf），零活跃公开竞品，unixnu.com 在案的 udon 只有我们。**

### boomoodxf/UniXNU-ace2（唯一命中）

- 身份：独立仓（非 GitHub fork），created **2026-10-26**，同日 push 后**再无任何推送**（今天 11-10）；0 star、无 fork 跟随者。
- 自述："OnePlus Ace 2 / PHK110 UniXNU bring-up: UEFI overlay, device repo and working memory configuration"；"**bring-up backup, not a ready-to-use OS**……只 `fastboot boot`，从不写分区"。
- 状态表（2026-10-26）[实测转述]：UEFI（`uefi-ace2`，**Project Silicium** 系）✅ → UniXNU 菜单+payload（`ace2 (PHK110)` + xnu）✅ → DarwinBoot 内核/ADT 校验 ✅（Exiting boot services）→ **4.75 GiB DarwinBoot 窗 ✅**（无 NO WINDOW，绿条）→ XNU entry ✅（绿条，停在交接屏不复位）→ **XNU console/其后 ❓ 未捕获** → UFS root/launchd/UI ❌。
- 里程碑内存战法：低 4 GiB 仅 ~51 MiB 连续空闲 → 4.75 GiB 窗分配失败 → **`ShengBootMemoryDxe`**（取自 sheng=小米 Pad 6S Pro 官方 UniXNU 设备）发同 SoC 高 bank `0x840000000 + 5 GiB` → 窗分配成功并交接。
- 谱系：`device/` = **UniXNU-liuqin 设备仓的拷贝**（liuqin = Pad 6 Pro，SM8475 同 SoC）；结构 = core-patches/device/docs/scripts/**uefi-overlay**（Mu-Silicium overlay 手术而非完整 fork）。
- 硬件事实表（对我们可直接互证的实测值）：Panel **1240×2772，stride 4960**；**Framebuffer 0xb8000000**；GIC GICD 0x17100000 / GICR 0x17180000（stride 0x40000，与 PalimaPkg 常量同值）；**UFS controller 0x1d84000 / PHY 0x1d80000**；DRAM 12 GiB：低 bank <4 GiB、高 bank @0x840000000；SoC ID 530；UEFI FD 0xA7100000/0x400000。工作镜像本地保存未入库（含 vendor 固件；boot img SHA256 8f7dd504…、kernel Mach-O SHA256 aceb48ac…）。

### 与我们（takasugl 线，upstream-manifest：UniXNU-udon@ad550a9、uefi-udon@475f9de；项目侧 wave 系）的差异

| 维度 | boomoodxf（10-26 定格） | 我们（wave27~31 活跃） |
|---|---|---|
| UEFI 基座 | Mu-Silicium overlay（Project Silicium 口径） | takasugl/uefi-udon（11-08 仍活跃推送） |
| XNU 进度 | entry 达成、console 未捕获、RAM-only | logdump 已至 v23 / wave27（内核 console/驱动战线持续推进中） |
| 存储链 | ❌ 未开始 | v0.4 口径 UFS S0–S8 已全通（F14 记录） |
| 内存窗 | 4.75 GiB 窗已实证（ShengBootMemoryDxe 法） | 同一 4.75 GiB/高 bank 课题我们独立在推——其 "working memory configuration" 可作第二证据源互证 |
| 生态位 | UniXNU-liuqin 谱系 + sheng 内存 DXE | UniXNU-udon 主线 |

### 其余命中（非 iOS 线的相邻活动）

- **cooolxuuun/ace2-kernel-build（10-25）与 ace2-kernel-build-v2（10-30）**："OnePlus Ace 2 (PHK110) kernel build (v19) with DroidSpaces support"——Android 内核/DroidSpaces 构建，**非 HakiOS/XNU**；同机活跃度信号，记录在案。
- Forenche/android_kernel_oneplus_sm8475（2024-08，"[WIP] Custom kernel for OnePlus 11r (Udon)"，旧）；lizj55785578/PHK110-PPS（PPS 充电，无关）；Gokulgethu/hardware_dolby（udon/CPH 音效包，无关）。
- Mu-Silicium 上游无 udonPkg（§②）；Renegade Platform/Oneplus 无 sm8475（§③）；hackios fork 网络无 udon/phk110 命名 fork（§4.4）。
- **中文平台**：无 Ace 2（标准版/PHK110）具体移植帖；smzdm 圈把 **Ace 2 Pro**（SM8550）当"求适配目标"讨论——**注意别把 Ace 2 Pro 的进展误记到我们头上**（它不是同 SoC）。

**含义**：我们的 upstream-manifest 生态位（PHK110 = takasugl 独苗）成立；boomoodxf 是唯一先行者，其仓 = "第二份 PHK110 实测数据源"（内存窗/fb/UFS 地址与我们互证），建议挂双周监控（repo pushed + 作者主页），暂无合作通道迹象（无 issue/README 联系点 [未深查]）。

---

## ⑥ 迁移评估：K60 线对 PHK110 可搬什么

### 6.1 SoC 级通用（直接参考/互证，同 cape 板间的"免费"增量）

1. **内存窗三定律**（Emilelu K60 实测 + boomoodxf Ace 2 实测同值）：12 GiB 机型高 bank @0x840000000、4.75 GiB 实测窗 pin、DarwinWindowSizeValid 8 GiB 上限、**payload boot-arg ≤600 字符硬限**（loader 预编译缓冲）——后者直接影响我们 boot.img 组装参数。
2. **CPU 拓扑结论**（Emilelu porting.toml device-verified）：cape 八核 MPIDR 平铺 0x000..0x700、PSCI 全核可达；**board dts 不得覆盖 cpu 节点**（会破坏固件 target 表/复位向量匹配）——我们 dts/mondrian 课题同款雷区预排。
3. **SoC 常量互证**：GIC 0x17100000/0x17180000（PalimaPkg=boomoodxf 实测一致）、UFS 0x1d84000/PHY 0x1d80000（boomoodxf=Amor "与参考机同 phy"）、EPSS @0x17d91000 + MC3/SH5（Amor，与我们 wave1 sm8475.config 的 SC7280 族口径对照）、tsens @0xc263000/0xc265000 + `thermal_map=sm8475` 32 通道表（Amor）。
4. **pong 系现成件**：PongUfs（pin c959284）、pong adreno ramoops bridge、`pong_cpu_first_boot*`（Darwin 24 首启路径）——Emilelu 已示范"同 SoC 直接搬 pong 件"，我们与 pong 同 SoC，可搬度更高。
5. **诊断探针族**（K60PANICFMT/K60KEXC/K60KFRAME/K60NULLENTRY + audit-forks.py 工程化 fork 协作）：零成本改造成 `phk110` 前缀探针 + 我们的 fork 审计脚本。
6. **UEFI 第二基座锚点**（落实 F15 §5.4 遗愿，但换正确的锚）：上游入口 = **PalimaPkg + pongPkg/senna_bcPkg**（有维护、有 Status 页、senna_bc Active）；设备化先例 = `Emilelu/uefi-mondrian` 的 `mondrianPkg`（fork @1a7afe7）——若 takasugl/uefi-udon 路线受阻，Mu-Silicium 系是现成第二路。

### 6.2 板级差异（必须自己做——与我们现有战线一一对应）

| 域 | K60（mondrian） | 我们 PHK110 | 备注 |
|---|---|---|---|
| 面板 | 1440×3200（2K） | 1240×2772、stride 4960、fb 0xb8000000 | Emilelu 的"canvas on panel"措辞 = 面板原生分辨率直挂；我们 1.5K 尺寸不同，DSI/面板参数板级 |
| 触摸 | Goodix m11a @QUP4 | 我们设备层自有（wave 早期已侦察） | Amor 教训：驱动机化（其驱动"说的是 redwood 的引脚语言"） |
| WiFi | **WCN6856**（ath11k，固件/BDF 不同） | WCN6750/qca6490-PCI（F14/F15 口径） | 同为 ath11k 族但固件/BDF 不可互换——K60 线的 WiFi 未见有人打通（全线 ❌） |
| 音频 | AW882XX 功放 | 我们自有配置 | ADSP 链 SoC 级、功放板级 |
| haptic | PM8350B hv | 我们自有 | 板级 |
| UEFI vendor DXE | mondrianPkg 走"最小 DXE、vendor 全剔"路线 | 我们走 udon 手术 patch 路线 | 两条哲学，无对错；Emilelu 用最小 DXE+外部装载器也走到了用户态 |

### 6.3 对 K60 Pro/K60E 的明确划界

- K60 Pro（socrates/SM8550/kailua）：非同 SoC，但其 UniXNU/黑果生态（nuwa、salami、aston、sheng 官方线）**是 SM8475 装机的"上游补给站"**（boomoodxf 的内存 DXE 即抄 sheng）。
- K60E（rembrandt/MTK）：零参考价值，从此从本项目的"K60"讨论中排除。

---

## ⑦ 诚实边界 / 未找到清单

1. 所有"首帧/60fps/桌面/触摸"声明均为**作者文档/控制台自述 [实测转述]**，我们未复现；Emilelu 线证据密度高（控制台原文、镜像清单、device-verified 记录带 revision/command），Yu-DaTouX thor 的"iOS 16.5 home screen"为单行自述、证据密度低。
2. Emilelu 仓的 182 项补丁 series、userland、UEFI FDF 未逐行读（时间盒）；四个 fork（mzyxsl/wohusaixing/XTOM0706/ZxbMsl160918）内容未读（unixnu.com 站标"Porting record"，未逐个打开）。
3. Amor1120iy 仓多数状态 missing/partial——它是"设备层+实测档案"，**不是可运行系统**；其"not seen on phone yet"的自我标注如实采信。
4. Renegade sm8475 仅文件层证据（无启动记录可查）；edk2-msm 的 README 无设备状态表。
5. boomoodxf 10-26 后零推送的原因（放弃/转私/等待）未知；其 README 无联系方式/路线图更新。
6. dipa-studio/ios-sweet（1344 星）与 oosexgang/hackios 的关系、以及 Emilelu/UniXNU 框架与 takasugl/UniXNU 框架的谱系关系未核——"UniXNU"同名字空间分属两个 org（我们上游锚 takasugl），**值得独立 F-task 摸清 ios-sweet 系谱**（它同时是 liuqin/K60/12S 系的公共基座）。
7. 中文平台仅 WebSearch 两页深度：酷安/贴吧/B站/抖音未直查；F15 的"视频先于代码"监测源仍未落地（无抖音/B站关键词监控）。
8. K60E=rembrandt 判定依据三仓设备树一致；"Dimensity 8200"精确型号名未从权威源字面证实（以 mt6895-common 命名为准）。
9. los wiki "SM8475" 字样引自搜索摘要的变体页口径 [实测转述]；未直读 variant2 页 HTML。
10. F15 勘误已复核：nuwaPkg=小米 13 Pro/SM8550，本轮证据（unixnu 表 nuwa SM8550 + KailuaPkg 系）一致，无推翻。

## 附录 A：本轮取证来源清单

**GitHub API/HTML（代理 7897）**
- orgs/Renegade-Project（login 确认）、orgs/edk2-porting/repos（22 仓全列）、repos/edk2-porting/edk2-msm/commits?path={Platform/Xiaomi/sm8475,Silicon/Qualcomm/sm8475}（2023-08~09 五条）
- repos/MiCode/Xiaomi_Kernel_OpenSource/branches（页 1-5，grep mondrian/socrates/coriander）；git shallow `--filter=blob:none --no-checkout -b mondrian-s-oss`（68,531 文件树清单：`build.config.msm.mondrian`、`modules.list.msm.mondrian`、`arch/arm64/configs/vendor/mondrian_*.config`；raw 取 build.config/modules.list）
- 浅克隆（均记录 HEAD）：Project-Silicium/Mu-Silicium @73daadd（2026-11-09）；edk2-porting/edk2-msm @e195262；Emilelu/UniXNU-mondrian @f048a92（depth 30，git log 30 条全录）；Emilelu/uefi-mondrian @1a7afe7
- repos API ×15：Emilelu/{UniXNU, UniXNU-sm8475-common, uefi-mondrian, ios-sweet-k60, PongUfs}、users/Emilelu/repos、XTOM0706 repos、{Emilelu,XTOM0706,ZxbMsl160918,mzyxsl,wohusaixing}/UniXNU-mondrian、Amor1120iy/hakios-mondrian（+contents/raw README/device.conf/FLASHING.md）、dipa-studio/ios-sweet、cotunjr/hakios-mayfly、Yu-DaTouX/hakios-thor、boomoodxf/UniXNU-ace2（+contents/raw README）、SFZ97/UniXNU-thor、zhouzhoublm/hakios-xnu-kernel、qiumochen/UniXNU-zizhan、ProjectRembrandt/android_device_xiaomi_rembrandt（+raw device.mk）
- search API ×7：sm8475+uefi、mondrian+uefi、sm8475+xnu、redmi+k60+ios、sm8475、PHK110、udon+sm8475、oneplus+ace2+uniXNU、udon+uefi、coriander+k60e、redmi+k60e
- repos/oosexgang/hakios-xnu-kernel/forks?sort=newest（40 条 name/desc/日期）、orgs/oosexgang/repos（7 仓）

**Web**
- unixnu.com：/devices/（全表 HTML 解析）、/devices/models/mondrian、/devices/models/udon
- wiki.lineageos.org：/devices/mondrian/（200，变体页）、/devices/socrates/（200，SM8550）、/devices/coriander/（404）
- WebSearch ×2："红米 K60 iOS UniXNU mondrian 黑果"（LOS variant2 口径、X huozhemeta 帖、OFRP 仓）；"一加 Ace 2 HakiOS iOS 黑果 移植"（linux.do 开源帖、知乎/CSDN/smzdm/AirMore、Ace 2 Pro 求适配讨论）
- xiaomifirmwareupdater.com（域名已停放，弃用）

**本地**
- `docs/research/f15-raphael-k20pro-survey.md`（格式模板、附录 A 工具链、nuwaPkg 勘误基线）
- `upstream-manifest.txt`（我们 udon 线锚点：UniXNU-udon@ad550a9、uefi-udon@475f9de）
- `f16-scripts/progress.log`（六阶段记录）

## 补记：本轮三条对我们最值钱的"免费情报"

1. **boomoodxf 的 PHK110 实测表**（fb 0xb8000000 / UFS 0x1d84000+0x1d80000 / stride 4960 / 高 bank 0x840000000）= 第二个人在我们板上量出来的数，与我们 wave 数据互证即可刷新置信度。
2. **Emilelu 的"静默复位→可定位故障"探针族 + ≤600 字符 boot-arg 硬限**：前者是我们任一阶段都能当天抄走的工作流；后者请检查我们 boot.img 组装是否踩线。
3. **cape 生态的上游正门是 PalimaPkg+pongPkg（有 Windows Boot 先例），不是任何 K60 包**——F15 §5.3 的"Mu-Silicium 同 SoC UEFI 备胎"愿望本轮落到了正确的锚上（上游 pong/b4q 有 Windows Boot 实绩；K60 的 mondrianPkg 只活在 Emilelu fork）。
