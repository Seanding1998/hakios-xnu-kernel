# SM7325 驱动全景与外部文章考古（含物料清单预研）

> ⚠ **勘误（2026-11-10，阶段 30 实证，`docs/waves/wave30-ath11k-tooling-prep.md`）**：本报告"WiFi = PCIe+CNSS（qca6490 形态）"一节的芯片口径需修正——**主线 ath11k 没有 QCA6490 这个 hw_rev**；PHK110 的芯片在 ath11k 世界 = **WCN6750 hw1.0**（固件目录 `WCN6750/hw1.0/`，IPCR 通道 20/21 复用 qca6390 表）。ath11k_pci 补 WCN6750 = 2 个一行级补丁（pci.c 设备 ID 表 + mhi.c hw_rev case）。

日期：2026-11-09 ｜ 执行：F14 调研 ｜ 纯调研：零手机、零刷写、零构建、零 clone
方法：webReader + GitHub REST/raw（代理 127.0.0.1:7897）+ 本仓文档只读 + WSL `~/hakios/kernel`（v2.1.13 树）+ `devices/phk110/uefi/files/Resources/DTBs/phk110.dts`（手机自己设备树的文本形式，2.4 MB，本地在盘）只读取证
产出：本报告（git add 不 commit）

> 证据分级：**[实证]** = 文件/行号/字节/可复现来源；**[实测转述]** = 上游文档自述的真机结果（我们未复现）；**[推断]** = 类比/待核；**[待核]** = 明确标注需要真机验证或源码对照的。
> 引用缩写：`[ART]` = zendot 文章；`[UP-K]` = github.com/oosexgang/hakios-xnu-kernel（HEAD，2026-11-08 push，v2.3.4）；`[UP-D]` = github.com/oosexgang/hakios-sm7325（redwood 设备仓，HEAD，2026-11-04 push）；`[TREE]` = WSL `~/hakios/kernel`（本地 v2.1.13 + PHK110 移植改动）；`[DTB]` = `[TREE] devices/phk110/uefi/files/Resources/DTBs/phk110.dts`；`[W1]` = 本仓 `docs/waves/wave1-hwmap.md`。

---

## 0. 摘要（先读这八条）

1. **文章定性**：zendot 文章（2026-10-22，中英双版同文）是一篇**导读型短评**（"它是什么/亮点/上手/适合谁"四节），信息源 = 上游官方 README/CHANGELOG 的浓缩；无新技术事实，唯一外链 = 仓库（旧名 `hackios-xnu-kernel`，已 301 → `hakios-xnu-kernel`）。它的价值是**独立第三方时间戳**：把 10-22 时点的"778G 真机可跑锁屏/主屏/设置/Safari/相机、Wi-Fi 55–90 Mbit/s、扬声器麦克风出声、HEIC 照片、数据跨重启"钉为公开可见事实 [实测转述]。
2. **文章坐标 vs 我们的现状**：文章时点 = 上游 v2.1.x 时代（Metal 应用不可用至今仍真，但 **2.3.4（11-05）已让窗口服务器经 Metal 出画：滑动 100-104 fps**——文章未提，因为它发稿在此之后）。我们与上游的能力差距没有因文章改变，但上游仓库考古给出了**精确的版本落差清单**（见 §3.3）。
3. **上游驱动获取工作流全部破译**（本报告最高价值产出之一）：上游"从自家安卓拉驱动" = **三个脚本**：`pull-firmware.sh`（adb 拉 5 类固件 blob 进 `fw-*/`，永不入 git）+ `pull-firmware-root.sh`（权限墙 root 变体：`fmask=0337` 的 vfat 挂载使 adb shell 拉不到，经 `su` 在 `/data/local/tmp` 暂存）+ `pull-soc.sh`（拉 `/sys/firmware/fdt` → `tools/soc-args.py` 生成 `soc_*` boot-args）。拉的全是 **firmware blob（.mdt+.bNN 签名分段与裸 .bin）**，**没有 Linux .ko**——XNU 不能加载 Linux 模块；Linux 驱动（ath11k）是**源码级移植**经 `wifi/lx/` 兼容层进内核。
4. **redwood（778G）拉固件的实测清单**（PKG110 文档，实测转述）：fw-modem 273 MB（modem.mdt+28 段+370 个 TFTP 文件）、fw-audio 21 MB（adsp.mdt+b00–b36）、fw-wifi 7.3 MB（wpss.mdt+b00–b07）、fw-gpu 137 KB（a660_gmu.bin/a660_sqe.fw/a660_zap.*，7 文件）、fw-haptic 7.5 KB（aw8697_haptic.bin）；合计 837 文件 313 MB 10.7 s。**注意 GPU 固件名 = a660 族**（642L 用 a660 族固件）——同族低配 GPU 用高配固件文件名是我们的直接先例。
5. **IPA 版本重大修正**：`[W1]` 声称 PHK110 = IPA 4.5（"主线 ipa_data-v4.5.c 可参照"）。**主线证据推翻**：SM8450 IPA 支持系列（2026-09 patchew v2，未合 net-next）明确新增 `ipa_data-v5.1.c`，且作者声明 **"Verified on SM7475, SM8450, and SM8475 with the modem working"**；`[DTB]` `qcom,ipa-hw-ver=<0x16>`（=22，vendor 枚举待解码）与 4.5/4.11 均不符。**PHK110 蜂窝 = IPA v5.1**，上游 `hakios.ipa.c` 是 4.11 硬编码 → 按 upstream 自己的定义"a different IPA version is a larger port"。v0.7 物料 = 主线 ipa_data-v5.1.c + OnePlusOSS sm8475 techpack/ipa（GPL）。
6. **PHK110 WiFi 一手证据确认**：`[DTB]` `wlan: qcom,cnss-qca6490@b0000000`，**无 WPSS remoteproc 节点**——上游 redwood 的 WPSS-PIL bring-up 整条不适用，PHK110 = CNSS 供电序列（6 路调光器+wlan-en GPIO80）+ PCIe0/MHI + ath11k **QCA6490/hw1.0** 固件族（amss.bin/m3.bin/board-2.bin）。
7. **内核级驱动文件：上游有我们没有的 ≈ 零**（意外结论）：`[TREE]` drivers/ 全 12 子系统与 `[UP-K]` HEAD 逐文件对大小，绝大多数字节级一致；本地独有 = `loader_net.c`（阶段 21 en0）+ `s3910.c`（设备仓）+ 8 个文件的 PHK110 改动（buttons/stubs/ufs 等）；上游略新 = `gpu.cpp`(+4 KB)、`input.c`(+2 KB)、`goodix.c`(+1 KB)。**真正的缺口在设备仓与工具层**（§3.4）：`pull-firmware*.sh` 真实现（我们的是 exit 1 占位）、`pull-soc.sh`、`cellular_probe.py`、`modem_firmware.py`、porting/driver-review 文档族、`drivers-check.py` CI 范式。
8. **对最近路程的直击**：① `pull-firmware-root.sh` 模板化 → 我们 v0.5 前置的 GPU 固件拉取（30–60 行，且 Magisk root + wave16c WSL adb 配方条件齐备）；② 2.3.3 修了 `fb_beam/fb_measure` 在非 sc7280 SoC 上读 SM7325 显示接口地址的坑——**与我们 23.x 虚拟显示出画链直接相关**；③ `UsbConfigDxe` 在 ExitBootServices 反初始化的 vendor DXE patch（上游必须打）与我们 阶段 21–24 的 USB 工作互证——上游 Binaries README 的 5 个 vendor DXE patch 清单是 udon UEFI 的现成对照表。

---

## ① zendot 文章全文要点提取（逐节）

**元数据**：`https://www.zendot.org/posts/oosexgang-hackios-xnu-kernel`（zh-CN）+ `/en/posts/...`（en），published 2026-10-22T17:23:43Z；四节结构；全文外链仅一条（仓库）。以下逐节提取，中英文版内容一致（双版互校）。

### §"它是什么"（What it is）
| # | 事实 | 等级 | 我们的交叉验证 |
|---|---|---|---|
| A1 | HackiOS = OOSEX GANG 独立研究项目：xnu-8796.121.2（iOS 16.5 所用内核）启动在安卓手机硬件，其上跑**未修改** iOS 16.5 用户空间（launchd/backboardd/SpringBoard/应用全链原装） | 实证（与我们树 VERSION/CHANGELOG 一致） | `[TREE] VERSION` XNU=xnu-8796.121.2 ✓ |
| A2 | 技术构成 = 自研 EFI 加载器 + 苹果闭源驱动替代品 + 一份 UEFI 移植 + **经兼容层直接复用 Linux 的 Wi-Fi 驱动** | 实证 | `[UP-K] drivers/wifi/` + `wifi/lx/`（6 个 Linux 头 patch + lx_base/bus/80211/wpa 共 155 KB）✓ |
| A3 | "自研 EFI 加载器"与"一份 UEFI 移植"并存 = BootShim/Mu-Silicium 路线 + 自研 xnuloader | 实证 | `[UP-D] prebuilt/BootShim.bin` + `[UP-K] xnuloader/` ✓ |

### §"亮点在哪"（What stands out）
| # | 事实 | 等级 | 备注 |
|---|---|---|---|
| A4 | POCO X5 Pro 5G（骁龙 778G）`fastboot boot` 内存启动，不刷机不落盘，重启回安卓 | 实证（与我们同款流程） | 我们 Boot #1–39 同链 |
| A5 | 真机已能跑：锁屏、主屏、系统手势、Settings、Safari、相机；**Wi-Fi 实测 55–90 Mbit/s**；扬声器+麦克风出声；前后摄可拍 HEIC；**数据跨重启保存** | 实测转述（第三方转发上游 README） | 与 10-22 时点上游 CHANGELOG 相容；数值级数据（Mbit/s）为上游自测 |
| A6 | **不含任何苹果文件**：系统镜像自苹果 CDN 拉取；许可证自定义 Other；声明与苹果无关联未获授权 | 实证 | `[UP-K] LICENSE/LEGAL.md` |
| A7 | 工具链完整：C 项目（当时 297★）带 QEMU 脚本、预编译内核/loader/UEFI、构建脚本；**配套 userland 仓**（注入库、launchd 任务、APFS 镜像构建） | 实证 | org 里 `hackios-xnu-userland`（410★，push 10-25）✓ |
| A8 | 坦诚清单：**蜂窝、蓝牙、Metal 应用、Apple ID 登录不行**；研究台非 ROM；每次会话限时；结束时内核把日志交回加载器 | 实证 | 与 redwood device.conf 状态表（§2.1）逐项吻合 |

### §"上手"（Getting started）
| # | 事实 | 等级 |
|---|---|---|
| A9 | QEMU 路线：Linux x86-64 + ~12 GB 盘 + 4 GB 内存；`common/setup.sh` → `ios165/fetch.sh`（7.4 GB 苹果 CDN）→ `common/build.sh qemu-virt` → `common/run.sh`；2–3 分钟出锁屏；单会话 20 分钟 | 实证（脚本在库） |
| A10 | 真机要求：解锁 BL 的 POCO X5 Pro 5G；**GPU、Wi-Fi、音频固件要用 adb 从这台手机自己的安卓里拉出来** | 实证（= pull-firmware.sh，§4.1 全解） |

### §"适合谁"（Who it's for）
| # | 事实 | 等级 |
|---|---|---|
| A11 | 受众定位研究者/系统程序员；**真机目前只支持 redwood 一款机型**；明确"不是日常备机" | 实证（2.3.4 时点仍真：org 设备仓只有 sm7325/mt6768/qemu） |

### 文章外链跟访结果
- 仓库链接（旧名）→ 301 → `oosexgang/hakios-xnu-kernel`（id 1429328794，2665★，push 2026-11-08）——已在 §3 深挖。
- 文章无 issues/其他文章外链。zendot 站同页无相关文章推荐区（HTML 已存 `/tmp` 核对）。

**文章的增量价值判定**：对已通读上游 CHANGELOG 的我们，文章自身新技术增量 ≈ 0；增量在于（a）**第三方独立转载的时间戳锚**（10-22 时的能力清单与数字）；（b）**它把"驱动从自家安卓拉"写进面向读者的标准步骤**（A10）——这正是本文确定的新重心，见 §4。

---

## ② 778G（SM7325）驱动族谱与 SM8475 对照

### 2.1 上游 redwood（778G）自述状态表（v2.3.4 时点，`[UP-D] device.conf` + `[UP-K] docs/devices/redwood.md`）[实测转述]

| 部分 | 状态 | 上游实现要点（boot-arg） |
|---|---|---|
| display | works | UEFI framebuffer；GPU 画帧（gpu=1） |
| touch | works | **Goodix GT9916 / FocalTech FT3680** SPI 多点（CONFIG_HAKIOS_GOODIX，touchscreen=1） |
| buttons | works | PMIC 电源/音量（CONFIG_HAKIOS_BUTTONS） |
| cpu | works | 8 核全起，大核 2.4 GHz（cpus=8 bootcpu=7 cpufreq=1） |
| gpu | works | **Adreno 642L，OpenGL ES 经 Mesa（gpu=1）；Metal：窗口服务器经它出画（metal=1），滑动 100-104 fps（非 120）** |
| storage | works | UFS 经 loader 读；/private/var 持久（var_store=1 ufs_write=1） |
| audio | works | 扬声器+麦克风经音频 DSP（adsp=1 sound=4 mic=4） |
| battery | partial | 电量经音频 DSP（battmgr）进 UI；本内核下不充电 |
| haptic | works | **Awinic AW86927**（haptic=5） |
| camera | works | Camera.app（cam=5） |
| torch | partial | PM8350C flash LED（torch=N） |
| wifi | works | **WCN6750 + Linux 的 ath11k**：radio/驱动/入网（wifi=1） |
| bluetooth | missing | 只做了第一步只读侦察（bt=1） |
| cellular | partial | modem 起、见网、SIM 绑定、IPA+en1 就位；**尚未注册入网** |
| thermal | partial | 27/27 传感器读（thermal=1）；停机阈值未见触发 |

> 注意：上游 v1.0 的"全功能"也只到上表——蜂窝未注册、蓝牙缺、充电缺。我们 v1.0 的目标定义（STATUS.md）与上表逐项对齐是合理的。

### 2.2 SoC 层族谱

- **上游把 778G 归为 SC7280 族**：`[UP-D] soc/soc.conf` = "Qualcomm SC7280 family (SM7325 'Snapdragon 778G', QCM6490; 'yupik', 'kodiak'); 8 核，最大核 = core 7；Adreno 642L"。
- **我们把 SM8475 建为独立 SoC 层**：`[TREE] devices/phk110/soc/configs/sm8475.config` = "SM8475 family（'cape','taro'）；8 核最大 = core 7（3×A510+4×A710+1×X2）；EPSS@0x17d91000 同 SC7280 族地址；TSENS v2 @0xc222000/0xc223000 同基址（16 传感器×2，读法同、计数 27→32 待真机确认）；SMEM item 137 同；SPMI arbiter@0xc42d000 同布局"。
- 两个 SoC 层的 **config 骨架逐行同构**（CONFIG_SOC/CPUS/BOOTCPU/CPUFREQ/SOCINFO/THERMAL/HAKIOS_CPUFREQ/SOCINFO/THERMAL/PMIC 完全一致）——上游的"SoC 层"抽象直接可复用，我们已复用。

### 2.3 逐驱动对照大表（778G → SM8475）

判定档：**同**（平台无关可直接用）/ **换参**（同 IP 同架构，换寄存器/表/数量）/ **新写**（IP 版本或架构不同）/ **已有**（我们 v0.x 已真机达成）。

| 驱动 | redwood（778G）实现 | PHK110（SM8475）事实（来源） | 判定 | 我们现状 |
|---|---|---|---|---|
| 显示 | UEFI framebuffer，内核无 DSI 驱动 | 同（NT37705 1240×2772 面板经 ABL/UEFI fb） | 同 | **已有**（v0.2 + 23.x MiniIOMFB 出画链） |
| 触摸 | Goodix GT9916 / FT3680 SPI（`hakios.goodix.c` 53 KB） | Synaptics S3910 TouchComm v1，SPI SE4 bitbang | 新写 | **已有**（S3910 v10e probe PASS，Boot #21；设备仓 `drivers/input/hakios.s3910.c` 62 KB） |
| 按键 | PMIC SPMI（taro 上游只认 v5 仲裁器） | taro SPMI **v7** 仲裁器 | 换参 | **已有**（阶段 12 v8/v9 真机按键事件） |
| CPU/cpufreq | EPSS，8 核，bootcpu=7 | EPSS@0x17d91000 同址，3 频域 | 换参（表） | **已有**（8/8 核 Boot #13 起） |
| 存储 UFS | `hakios.ufs.c/ufshc.c` 经 loader mailbox 页 | 同架构同地址（ufshc@1d84000） | 同 | **已有**（v0.4 S0–S8 全通，Boot #22–24） |
| GPU | **`hakios.adreno.c` 167 KB，22 步法**；Adreno 642L，chipid 0x06030500（DT），无芯片 ID 寄存器，只靠 fuse；固件 a660_{gmu.bin,sqe.fw,zap.mdt/b00–b02} | **Adreno730v3**（gen7），chipid 0x7030002，kgsl@0x3d00000、gen7-gmu@3d69000、adreno-smmu@3da0000、zap-shader 节点在（`[DTB]`） | **新写参数层**（方法论同，全套数字+固件族换 a730/gen7） | 未启动（v0.5） |
| WiFi | WCN6750 **WPSS-PIL（AHB）**：`hakios.wifi.c` 16 步法，wpss.mdt+b02–b07，SMEM/SMP2P/IPCC/AOP/GLINK/QRTR/WLFW（ath11k stand-in）+ lx 兼容层 | **同一芯片族但 PCIe**：`qcom,cnss-qca6490@b0000000`，无 WPSS 节点；CNSS 供电 6 路+wlan-en GPIO80；MHI+QRTR | **新写**（WPSS 链全废，改 CNSS+MHI+ath11k_pci） | 未启动（v0.6） |
| 蓝牙 | `hakios.bt.c` 仅 GPIO 84/85/86 只读侦察 | 同芯片族 GPIO 81/82 起（`[W1]`） | 新写（同为侦察级） | 未排期 |
| 蜂窝 modem | `hakios.mpss.c` 250 KB：PIL（modem.mdt+b00–b29，85 MB→246 MB 区）+TZ image 4+QMI WDA/NAS+QMAP | `qcom,cape-modem-pas` @04080000 同址同流程；固件同布局（`/vendor/firmware_mnt/image`） | 换参 | 未启动（v0.7） |
| 蜂窝 IPA | **IPA 4.11 + GSI 2.11**（`hakios.ipa.c` 硬编码 4.11 寄存器布局/端点表） | **IPA v5.1**（主线 sm8450 系列实测 SM8475；`[DTB]` hw-ver=0x16=22 待 vendor 枚举解码；`soc_ipa_base=0x3e40000/cfg-offset 0x140000/stream 0x5c0`） | **新写（IP 版本不同="larger port"）** | 未启动；`[W1]`"IPA 4.5"结论需修正 |
| 音频 | ADSP PIL（adsp.mdt+b02–b36，20 MB；TZ image 1；APR）+ speaker/mic | `qcom,cape-adsp-pas` @03000000 同族；codec wcd938x+lpass-cdc+swr（`[DTB]`）；TFA9874 功放（`[W1]`） | 换参（PIL 同）+ 功放新写 | 未启动 |
| 电池 | 电量经 ADSP battmgr（GLINK） | 同协议族（`[W1]`：GLINK/battmgr 直接对 redwood 协议） | 换参 | 未启动 |
| 触感 | Awinic AW86927 I2C + 固件 bin | **PM8350B HV-haptics（SPMI）+ SoundWire（swr_haptics）**（`[DTB]`） | 新写（架构不同，低优先） | 未排期 |
| 相机 | `hakios.camera.c` 165 KB + torch；sensormodule/tuned bin 从 `/vendor/lib64/camera/` 拉 | 4×cam-sensor + OIS + eeprom（型号在运行时 bin 才知） | 新写（v1.0 后） | 未排期 |
| 热 | TSENS 直读 27 传感器 @0xc222000/0xc223000 | 同基址 v2，16×2=32 传感器 | 换参（计数/热区表） | 部分已有（sm8475.config 记录） |
| 平台核 | GIC-600（GICR stride 0x20000） | GICR stride **0x40000**（Boot #12 真机定位根因） | 换参 | **已有** |
| 平台核 | SPMI v5 仲裁器 | SPMI **v7** 仲裁器（阶段 12 v8 适配） | 换参 | **已有** |
| 平台核 | GENI 引擎（FIFO） | GENI 同 IP（我们 SE4 FIFO 被固件禁用 → bitbang 路径，阶段 12a/b） | 换参 | **已有** |
| 网络 | `hakios.net.c`（enN）+ virtio_net | 同 + 我们自有 `hakios.loader_net.c`（en0 loader 桥） | 同+自有 | **已有**（阶段 21 en0 数据面） |

### 2.4 soc_* boot-args 全 16 项对照（`[UP-D] soc.args` vs `[TREE] devices/phk110/soc.args`）

| 参数 | redwood（yupik） | phk110（cape） | 备注 |
|---|---|---|---|
| soc_ipa_base | 0x1e40000 | **0x3e40000** | cape IPA@3e00000+0x40000 |
| soc_gsi_base | 0x1e04000 | **0x3e04000** | |
| soc_ipcc | 0x408000 | **0xed18000** | 巨差：taro IPCC 独立地址 |
| soc_aoss | 0xc300000 | 0xc300000 | 同（SoC 定死） |
| soc_rsc | 0x18220000 | **0x17a20000** | |
| soc_apps_smmu | 0x15000000 | 0x15000000 | 同 |
| soc_cmd_db | 0x80860000 | 0x80860000 | 同 |
| soc_mpss_mem | 0x8b800000 | **0x8bc00000**（306 MB） | 不换则驱动默认指到 modem 保留区外 |
| modem_ipa_fw_at | 0x8b710000 | **0x8b910000** | cape PIL 装 gsi 区非 ipa_fw 区 |
| soc_smem | 0x80900000 | 0x80900000 | 同 |
| soc_imem | 0x14600000 | 0x14600000 | 同 |
| soc_ipa_stream / _uc | 0x480 / 0x482 | **0x5c0 / 0x5c2** | SMMU 流 ID 不同 |
| soc_pas_mpss / _ipa | 4 / 0xf | 4 / 0xf | 同（cape DT 无 pas-id，沿用默认，[待核]） |
| soc_ipa_fw | yupik_ipa_fws | **ipa_fws** | 固件名不同 |

> 16 项中 6 同 10 异——印证上游架构判断："同 SoC 层内每台手机只带 device 层差异；soc_* 由 pull-soc.sh 生成"。我们的 soc.args 已是 wave1 的合格产物。

---

## ③ 上游仓库驱动清单对照

### 3.1 org 仓库地图（2026-11-09 实测）

| 仓库 | ★ | push | 内容 |
|---|---|---|---|
| hakios-xnu-kernel | 2665 | 11-08 | 内核+驱动+loader+UEFI 通用层+hakios-metal（已并入）+tools+docs+sysimage+userland 副本 |
| hackios-xnu-userland | 410 | 10-25 | 注入库/launchd 任务/APFS 镜像构建（landscape 已普查） |
| **hakios-sm7325** | 7 | 11-04 | **redwood 设备仓**：device.conf/configs/soc(sc7280)/uefi(redwoodPkg)/prebuilt/pull-*.sh/tools(蜂窝) |
| hakios-uefi | 11 | 10-31 | Mu-Silicium 改动 + U-Boot v2026.07 |
| hakios-metal | 41 | 11-05 | "Moved into the kernel"（2.3.3 起在主仓 `hakios-metal/`） |
| hakios-mt6768 | 9 | 11-08 | Infinix Hot 20（MTK Helio G85，实验性第二 SoC 族） |
| hackios-web | 59 | 11-05 | 官网 |

**设备仓 sync 机制**：`devices/manifest.conf` 登记 `device redwood → repository hakios-sm7325 @ af52dfba`；`tools/hakios-device.py sync` 克隆进 `devices/redwood/`。**我们 phk110 的等价做法 = 直接住进 devices/phk110/（path 型，无独立仓）**——机制兼容，无需建仓。

### 3.2 内核驱动文件清单（`[UP-K] drivers/` HEAD vs `[TREE] drivers/`）

上游 12 子系统 48 个 hakios.* 文件（+drivers/map 索引 + 各 conf）。本地对照结果：

- **字节级一致（同版本同内容）**：audio 全 7、bluetooth、camera 全 2、core/platform+socinfo、gpu/adreno.c、haptic、input/focaltech_fw.h+virtio_input、modem 全 5、power 全 6、storage 除 ufs.c 外全 5、wifi 全 6、net/virtio_net——共 ~38 文件。
- **上游略新（版本落差）**：`gpu/hakios.gpu.cpp` 47089 vs 本地 43055（**+4.0 KB**，2.2.x–2.3.x 的 HakiosGPU 演进：0x7d 客户端页 buffer、Turnip 对接）；`input/hakios.input.c` 8940 vs 6894（+2.0 KB）；`input/hakios.goodix.c` 52907 vs 51892（+1.0 KB）。
- **本地独有/已改**：`net/hakios.loader_net.c`（+15.8 KB，仅我们）；`input/hakios.buttons.c` 27154 vs 24694（**本地大 2.4 KB** = taro SPMI v7 适配）；`core/hakios.stubs.c`（+208 B）、`core/hakios.version.c`（+1 B）、`storage/hakios.ufs.c`（+598 B）、`net/hakios.net.c`（+27 B）。
- **上游独有而本地无的驱动文件：无**。`wifi/lx/`（Linux 兼容层 26 文件）本地全在。

> 结论：**"上游有我们没有的驱动文件"这一项 = 空**。本地树就是上游 v2.1.13 的完整拷贝 + PHK110 增量。缺口在下面两处。

### 3.3 版本落差：2.1.13 → 2.3.4（CHANGELOG 全差，标注行动价值）

| 上游条目（日期） | 内容 | 对我们 |
|---|---|---|
| 2.3.4（11-05） | Metal 运行期 pipeline 邻近变体匹配修复（壁纸红顶/状态栏白带根因）；触摸 lift ≤5–6 ms（原 88–169）；**Metal 基准 109.6 fps / 1.3% 超 16.7 ms**；`devices/<name>/metal.args` 机制（非 redwood 设备不再吃 redwood 参数） | **高**（v0.5 性能锚 + metal.args 范式直接抄） |
| 2.3.3（11-05） | hakios-metal 并入主仓；**`fb_beam/fb_measure` 只在 sc7280 或 fb_intf= 时读显示接口寄存器（此前在任何 SoC 上读 SM7325 的地址）**；chip id 不符的 GPU 拒绝服务；触摸每 look 必读报告；慢帧即时过滤 | **高**（fb 接口寄存器坑正是跨 SoC 移植会踩的；23.x 出画链相关） |
| 11-04 | Metal 120 未达的量化归因（SpringBoard 主线程 + home 键帧耗）；`wallpaper_freeze=1`（壁纸定帧：home 键 28→92 fps）；`fb_beam=1`（按面板扫描线错峰写行，去横带零帧损）；`fbsubtype=N`（换 iPhone 机型屏幕等级） | **高**（23.y 进程稳定/帧率调优的现成旋钮） |
| 11-03 | **Metal on Vulkan（Turnip+AdrenoMetal+metal2vulkan）全链真机验证**：vk_test/m2v_test 过；metal_m2v=1 窗口服务器 50–57 fps；HakiosGPU 0x7d 客户端页 buffer（`VK_EXT_external_memory_host`） | **高**（v0.5 第二路线的验收级细节） |
| 11-02 | Metal shader 缓存 `/var/db/hakios-metal-cache` + 镜像种子；`tools/metal-run.sh`（Git Bash 一条命令实测跑 Metal） | 中 |
| 10-29/30 | U-Boot 双系统全家桶；Wi-Fi 控制器寻址修复（ios-sapphire port 发现）；Darwin 化更名 | 已在 landscape 覆盖 |

> **给 v0.5 的直接推论**：上游 GPU 战已在 778G 上双路线（直编 hakios-metal ~110 fps + m2v/Turnip 50–57 fps）都到了可用态，且暴露了帧率墙 = SpringBoard 主线程 100–300 ms 卡顿 + home 键路径，**不是 GPU 吞吐**。我们 PHK110（Adreno 730 > 642L）的预期上限至少不差于此；8 核 X2 大核对 SpringBoard 主线程只会更好。

### 3.4 设备仓级：上游有、我们没有（重点发现）

| 上游 sm7325 资产 | 我们的对应 | 差距与行动 |
|---|---|---|
| `pull-firmware.sh`（真实现，1601 B） | `devices/phk110/pull-firmware.sh` = **exit 1 占位**（881 B） | §4.1/§4.4：按模板写 PHK110 版（v0.5 前置） |
| `pull-firmware-root.sh`（2137 B，root 变体 + 权限墙文档） | 无 | 同上，**PHK110 的 ColorOS 大概率同墙（vfat fmask）**，root 变体应为主路径 |
| `pull-soc.sh` + `tools/soc-args.py` 工作流 | soc.args 已手工有（wave1 产物，质量好）；`tools/soc-args.py` 树内已有 | 差距小；可跑一次 soc-args.py 对拍我们 soc.args（零手机成本，fdt 在盘） |
| `tools/cellular_probe.py` + `tools/modem_firmware.py`（DTB 校验 modem 分段） | 无 | v0.7 前抄（PKG110 文档示范其价值：28 段校到字节） |
| `prebuilt/device-tree.dtb`（405 KB，vendor_boot 的 DT 入库）+ `mkbootimg.py` | 我们的等价物 = `phk110.dtb/dts`（1.2/2.4 MB）+ 自有 mkpayload 流 | 无缺口（形态不同） |
| `uefi/files/Binaries/redwood/README.md`（**vendor DXE patch 清单范式**） | 无对应文档（我们的 udonPkg 改动散在各 wave 报告） | §5-Top3#3：把我们的 vendor DXE 差异也收成单一清单 |
| `docs/porting/{index,drivers,repositories}.md` + `drivers-check.py` CI + `tools/boot-args.py --check` | 无（我们的纪律在各 wave SOP） | 中期可选：driver-review 审计文档族值得 v0.5 前读（gpu-display.md 30 KB / wifi-bringup 33 KB / wifi-stack 36 KB） |
| `docs/port-pkg110.md`（9.5 KB） | 无 | **同族第二台点亮的方法论模板**（§5-Top3#2），含 Windows Git Bash 跑通全链的坑位表（flock shim、7z 的 `:` 文件名 NTFS 限制、modem 必须 system 镜像 /fw 等——最后这条与我们的 wave18 经验完全同构） |

### 3.5 wifi/lx 兼容层结构（v0.6 的关键基础设施）[实证]

`[UP-K] wifi/lx/` = Linux 驱动进 XNU 的桥：
- `include/linux/{irq,of,of_irq,of_reserved_mem,remoteproc,rhashtable}.h` + `soc/qcom/qmi.h`：Linux 头的 XNU 假身；
- `patches/`：对 **Linux 内核头**（device.h/etherdevice.h/io.h/socket.h/cfg80211.h/mac80211.h）的 6 个适配 patch——意味着 ath11k/mac80211 源码树被外部拉入编译（拉取脚本在 `[UP-K] tools/` 族，本报告未逐个打开，见 §6 缺口）；
- `src/`：`lx_80211.c` 81 KB + `lx_base.c` 31 KB + `lx_bus.c` 30 KB + `lx_wpa.c` 17 KB——cfg80211/mac80211 核心的移植层；
- `[TREE] drivers/wifi/hakios.lx.c`（15.5 KB）= 内核侧接驳，`hakios.wlfw.c` = ath11k 的 wlfw 服务 stand-in。

**对我们的含义**：PHK110 走 ath11k **PCI**（qca6490）时，**同一 lx 层大概率可复用**（差异在 bus 后端：AHB/WPSS ↔ PCI/MHI，cfg80211/mac80211 上半全同）[推断，待读 wifi-stack.md 确认 bus 抽象程度]。

---

## ④ 驱动提取工作流与 PHK110 物料清单（本文重点）

### 4.1 上游工作流全解（三个脚本逐条）

**A. `pull-firmware.sh`（手机在安卓 + adb）** —— 拉取即"驱动获取"，产物 5 个 `fw-*/` 目录（永不入 git）：

| 目录 | 手机侧来源 | 文件 | 大小（PKG110 实测） |
|---|---|---|---|
| fw-gpu | `/vendor/firmware/` | a660_gmu.bin、a660_sqe.fw、a660_zap.mdt/.b00/.b01/.b02 | 137 KB |
| fw-wifi | `/vendor/firmware_mnt/image/` | wpss.mdt + b02–b07 | 7.3 MB |
| fw-audio | `/vendor/firmware_mnt/image/` | adsp.mdt + b00–b36 | 21 MB |
| fw-haptic | `/vendor/firmware/` | aw8697_haptic.bin | 7.5 KB |
| fw-modem | `/vendor/firmware_mnt/image/` | modem.mdt + b00–b28 + 整个 `image/`（370 个 TFTP 文件） | 273 MB |
| fw-camera | `/vendor/lib64/camera/` | `com.qti.sensormodule.hakios_*.bin` + `com.qti.tuned.hakios_*.bin`（上游曾把首台命名改写为 hakios_ 前缀） | 未量（root 版不拉） |

另有两项**手工文件**（脚本末尾提醒）：`fw-wifi/mac`（radio MAC 地址）与 `fw-wifi/network`（网络名+密码）。
合计 837 文件 313 MB 10.7 s [实测转述，PKG110 文档]。

**B. `pull-firmware-root.sh`（权限墙变体）**——上游在真机上遇到的墙与解法（对我们的 ColorOS 直接适用）：
- 墙：某台 redwood ROM 的 `/vendor/firmware_mnt` 是 vfat 挂载、属主 system、`fmask=0337`，且 `/vendor/firmware` 对 adb shell 也不可读 → **裸 `adb pull` 每个文件都拿不到**（但文件都在）。
- 解法：`su -c` 把固件拷进 `/data/local/tmp/fw` 暂存目录 → `chmod -R a+rX` → `adb pull` → 删暂存。手机零改动。支持 Magisk/KernelSU。
- **我们的条件已齐备**：PHK110 = Magisk 真解锁 + wave16c 的 WSL Linux adb + `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037` 配方（Windows adb.exe CRLF 教训在案）。

**C. `pull-soc.sh`（SoC 参数生成）**——`adb pull /sys/firmware/fdt`（不可读时同 root 暂存法）→ `tools/soc-args.py` 读 `qcom,ipa`/`qcom,ipcc`/AOSS mailbox/`qcom,rpmh-rsc`/`apps-smmu` 节点 → 生成 16 项 `soc_*`（全表见 §2.4）；保留内存类（smem/cmd_db/mpss/imem）需手工补。**redwood 上生成值=内核默认（零 override）；cape 上 10 项不同——正是我们 wave1 已做的工作**。

**D. 固件怎么进镜像（接入路径）**：
- **小镜像 `fw/`**：`userland/build.sh` 以 `GPU=1 ADSP=1 ...` 把 fw-gpu/fw-wifi/fw-haptic/fw-audio 打进 payload 小镜像（GPU 137 KB 级别才放得下）；
- **`system.apfs /fw`**：MODEM=1 SYSTEM=1 时把 fw-modem（273 MB）灌进系统卷 `/fw`，内核运行期从根读（`hakios.mpss.c:1045-1110`）——**PKG110 文档实证：没有 ramdisk/system 镜像时内核在 modem 线程启动前就 panic（root mount fail），modem 链必须配完整 Darwin 镜像**（与我们 阶段 18 的 system.apfs 换根结论同构）；
- 内核驱动以"step 法"消费固件：先 `is it whole, does it fit the reserved memory` 校验，再 TZ 认证加载（zap/wifi/adsp/modem 各有 TZ image 号：GPU zap=12 步、WPSS=image 6、ADSP=image 1、MPSS=image 4）。

### 4.2 "拉出来之后接在哪"（接入形态分类）

| 形态 | 上游实例 | 说明 |
|---|---|---|
| **firmware blob**（.mdt+.bNN 签名分段 / 裸 .bin） | GPU zap/GMU/SQE、WPSS、ADSP、MPSS、IPA fw、触感 bin | 唯一从手机拉的形态；**没有 .ko**——XNU 不能加载 Linux 内核模块 |
| **Linux 驱动源码级移植** | ath11k（`hakios.wlfw.c` = 其 wlfw 服务的 stand-in；`wifi/lx/` = cfg80211/mac80211 兼容层 + 6 个 Linux 头 patch） | "复用 Linux Wi-Fi 驱动"的真实含义 = 源码编译进 XNU，不是二进制复用 |
| **vendor UEFI DXE 二进制**（另一条拉取线，从 UEFI 镜像非从 Android） | `[UP-D] uefi/files/Binaries/redwood/`（不入 git）：ButtonsDxe（键码 0x102→Enter，Gustave Monce）/ **DALSYSDxe（UFS cache coherence）**/ TzDxeLA（TZ applet 变量→TRUE）/ **UsbConfigDxe（移除 ExitBootServices 时的 USB 反初始化）** / UsbMsdDxe（Removable→Non-Removable） | 与我们 阶段 18 R1（DALSYSDxe 清白免patch）与 阶段 21–24（UsbConfigDxe start_ex/端点墙）**互证**：vendor DXE 的这两处坑上游同样要手术 |
| **用户态物料**（不从手机拉） | Mesa 25.0.7（freedreno+Turnip）、hakios-metal、AdrenoMetal+metal2vulkan、Procursus 类 | IPSW 自备 + 工具链自建 |

### 4.3 PHK110（SM8475/ColorOS）物料清单预研

前置事实：root 可用（Magisk）+ adb 通道已验证（wave16c 配方）→ **"拉"这个动作零障碍；关键是拉什么、接在哪**。下表置信度分级：A = DTB/在盘证据直接支持；B = 上游同族先例+主线证据；C = 待真机验证/待解包核对。

| 物料 | ColorOS 预期位置 | 预期形态/文件名 | 接入点（v0.x） | 置信 |
|---|---|---|---|---|
| **GPU 固件（a730）** | `/vendor/firmware/` | zap：**a730_zap.mdt/.bNN**（主线 linux-firmware 有 `qcom/a730_zap.mbn` 同族；主线 sm8450.dtsi GPU=`qcom,adreno-730.0`）；GMU/SQE 文件名 **[待核]**（`[DTB]` 只给 `qcom,gen7-gmu`@3d69000，无固件名字串——vendor kgsl 从芯片族推名；候选 a730_gmu.bin/a730_sqe.fw） | v0.5：`hakios.adreno.c` 的 22 步法换 cape 全套数字 + gen7 固件族；用户态 Mesa TU730 主线已实证支持 | B/C |
| **WiFi 固件（qca6490 PCIe）** | `/vendor/firmware/wlan/`（`[W1]` 声称 qca_cld 族 **[待核]**）或 firmware_mnt | ath11k 族对应 **QCA6490/hw1.0/{amss.bin, m3.bin, board-2.bin}**；Android 侧 BDF 常见 `bdwlan.elf.<variant>`（例：Motorola dubai 的 `bdwlan.elf.dubai.ipa` 从 vendor 分区提取入 ath11k-firmware） | v0.6：CNSS 供电序列（aon/io/dig/rfa1/rfa2/ant-switch 6 路 + wlan-en GPIO80）→ PCIe0 上电 → MHI → QRTR → ath11k_pci（lx 层） | A（节点/供电）+B（文件名） |
| **BT 固件** | `/vendor/firmware/` | qca 族 `msbtfw11.mbn` + `msnv11.bin`（WCN6750 类） | 远期（上游也只有侦察级） | B |
| **ADSP 固件** | `/vendor/firmware_mnt/image/` | `adsp.mdt + adsp.b00–bNN`（cape 的分段数待拉时确认；redwood=38 文件 21 MB） | 音频战（v0.x 后段）：cape-adsp-pas@03000000，TZ image 1，APR/GLINK/QRTR 全同族 | A+B |
| **MODEM 固件** | `/vendor/firmware_mnt/image/` | `modem.mdt + modem.bNN` + `image/` TFTP 目录（370 文件级）+ `ipa_fws`（`[DTB]` qcom,ipa_fws pas-id 0xf；`modem_ipa_fw_at=0x8b910000` 已在 soc.args） | v0.7：PIL 流程同 redwood；**IPA 部分换 v5.1**（§2.3） | A+B |
| **CDSP / SLPI / SPSS** | 同上 image/ | cape 有 `cape-cdsp-pas`@32300000、slpi@02400000、spss@1880000 节点（`[DTB]`）；上游 redwood 未用 | 观察项：非必拉；v0.5 GPU 不经 CDSP | A |
| **触感** | 无固件 | PM8350B HV-haptics = 寄存器直驱族（SPMI+SoundWire） | 不拉；低优先新写 | A |
| **相机 blob** | `/vendor/lib64/camera/` | `com.qti.sensormodule.*.bin` + `com.qti.tuned.*.bin`（4 摄，型号在 bin 内） | v1.0 后 | B |
| **vendor DTB** | `/sys/firmware/fdt`（运行时）或 vendor_boot | **已在盘**（phk110.dtb/dts，wave1 产物） | 不用再拉 | A |

**PHK110 `pull-firmware.sh` v1 施工要点**（给下一波，本报告零执行）：
1. 以 `pull-firmware-root.sh` 为模板（ColorOS 大概率同权限墙；`su -c` 暂存法主路径，Magisk 在位）；
2. 清单差异 vs redwood：fw-gpu 换 **a730_\*（先 `adb shell su -c 'ls /vendor/firmware/'` 取真名再写死清单）**；fw-wifi 改拉 **PCIe 族**（/vendor/firmware/wlan 的 amss/m3/bdwlan 族 + MAC 地址文件）而**不是 wpss.\***；fw-haptic **删**（架构不同）；fw-audio/fw-modem/fw-camera 同上游；
3. 管道用 wave16c 配方（WSL adb + mirrored USB + ADB_SERVER_SOCKET）；脚本 exit 0 且逐目录报文件数（上游范式）；
4. 产物走向：fw-gpu 进小镜像 `fw/`；fw-modem 进 system.apfs `/fw`（MODEM=1）；fw-audio 双路（ADSP=1 小镜像或 /fw）。

---

## ⑤ 行动价值排序

### Top 3（立即可用）

**#1 `pull-firmware-root.sh` 模板化 → 实现 `devices/phk110/pull-firmware.sh`**（v0.5 前置，估 30–60 行脚本 + 一次真机验证 ls/拉取）
- 价值：上游已把"从 ColorOS 拉固件"的权限墙、暂存法、逐目录验收全部趟平；我们 root+adb 双通道在位。v0.5 GPU 战的第一物料（a730 固件）就靠它。
- 佐证：PKG110 文档 = 第二台同族点亮用同款脚本一次拉齐 313 MB；`[TREE]` 我们的占位脚本已写明"写这个脚本时参照 devices/redwood/pull-firmware.sh"。
- 验收：5 个 fw-*/ 目录文件数行；a730 三件（zap/gmu/sqe）真名落档进本报告附录或 wave 报告。

**#2 版本落差选择性同步（gpu.cpp + fb 门控 + metal.args 范式）**（v0.5 战前 0.5 天评估）
- `drivers/gpu/hakios.gpu.cpp`（+4 KB：HakiosGPU 0x7d `VK_EXT_external_memory_host` 等）与 `input.c/goodix.c` 的 2.2.x–2.3.x 演进 diff 一看即懂，直接择优合入我们树；
- **2.3.3 的 `fb_beam/fb_measure` sc7280 门控**：我们的 23.x 出画链（MiniIOMFB→panel memcpy）若曾借用上游 fb 帧路径，检查是否踩"非 sc7280 上读 SM7325 显示接口寄存器"；23.y 帧率调优直接可用 `fb_beam=1`/`wallpaper_freeze=1`/`fbsubtype=N` 旋钮（均已在树，若我们树是 2.1.13 则随同步获得）；
- `devices/<name>/metal.args` + `tools/metal-run.sh` 的"设备参数文件"范式 → 给 phk110 建 metal.args（分辨率 1240×2772、fbscale 等）。

**#3 IPA v5.1 修正单 + 主线参考收档**（v0.7 物料，零手机成本）
- 修正 `[W1]` §2.11/§"v0.6/v0.7 排期修正"中的"IPA 4.5"结论为 **IPA v5.1**（证据：patchew SM8450 IPA v2 系列自述 "Verified on SM7475, SM8450, and SM8475 with the modem working"；新增 `drivers/net/ipa/data/ipa_data-v5.1.c` ~476 行；[DTB] hw-ver=0x16 与 4.5/4.11 均不符）；
- 把该系列（或合入后的主线版）收进 `intel/` 作为 v0.7 参考：上游 `hakios.ipa.c` 是 4.11 硬编码（寄存器布局 reg/gsi_reg-v4.11 + 端点/通道表 ipa_data-v4.11），cape = "a different IPA version is a larger port"（上游原话）——v0.7 排期预期按"寄存器族重对表"设定，不按"换参数"。
- 遗留解码项：`qcom,ipa-hw-ver=0x16` 的 vendor 枚举精确名——对照 OnePlusOSS `android_kernel_oneplus_sm8475` techpack/ipa 的 `IPA_HW_v*` 枚举即可定案（GPL，可离线）。若它解码 = 5.1 则三条证据闭合。

### 观察项（不占 Top 3）

- **lx 兼容层的 bus 抽象**：读 `[UP-K] docs/driver-review/wifi-stack.md`（36 KB）确认 cfg80211/mac80211 上半与 PCI/MHI 下半的隔离度 → v0.6 工作量评估的直接输入；
- **vendor DXE patch 清单对照**：上游 5 patch（ButtonsDxe/DALSYSDxe/TzDxeLA/UsbConfigDxe/UsbMsdDxe）vs 我们 udonPkg 的实际差异表——特别是 UsbConfigDxe"EBS 反初始化移除"与我们 阶段 21–24 结论（start_ex 端点墙 = vendor UsbDeviceDxe 固有行为）的交叉印证；产出一页 `docs/research/` 对照表（可选）；
- **Metal 性能锚**：109.6 fps（滑动基准）/100–104 fps（真实手指）/m2v 50–57 fps——v0.5 验收线的对照基准；帧率墙在 SpringBoard 主线程而非 GPU，PHK110 只会更好 [推断]；
- **hakios-mt6768**（MTK 第二族）：证明上游设备抽象已跨 SoC 厂——若未来 PHK110 之后扩设备，范式已备；
- **PKG110 文档的 Windows 工程坑清单**：flock shim、7z `:` 文件名 NTFS 限制、modem 链必须 system 镜像——后两条与我们 wave16c/wave18 经验同构，可在 wave 报告互引。

---

## ⑥ 信息缺口（诚实清单）

1. **PHK110 `/vendor/firmware/` 真实文件清单**（a730 zap/GMU/SQE 真名、wlan 目录形态、adsp/modem 分段数）——需一次真机验证 `su -c ls` + 拉取；本轮零手机未做。缓解：a730_zap.mbn 主线存在性已证（linux-firmware），GMU/SQE 名为 [待核]。
2. **`qcom,ipa-hw-ver=0x16` 的 vendor 枚举解码**——需 OnePlusOSS sm8475 techpack/ipa 源码（GPL，公开；本地未拉）。两条独立外部证据已指向 v5.1，但 DTB 数值的精确对应未闭合。
3. **wifi/lx 对 ath11k PCI 的覆盖度**——`wifi-stack.md`/`wifi-bringup.md`（共 69 KB）未逐字读；lx bus 层是否已含 MHI 假身未知（上游 redwood 只用 AHB/WPSS 路径）。
4. **主线 SM8450 IPA v5.1 系列的合入状态**——patchew v2（2026-09）显示 changes-requested（依赖另一个未合 patch + 系列拆分要求），**未合入 net-next**；引用时注意它当前是"公开系列"非"主线代码"。
5. **`hakios.camera.c` 对 sensormodule/tuned bin 的消费方式**（内核直读还是经用户态）未读（165 KB）；PHK110 相机在 v1.0 之后，未影响近期路程。
6. **`tools/soc-args.py` 未对我们 fdt 实跑对拍**（soc.args 手工版 vs 工具生成版）——零手机可做，留给下一波顺手项。
7. **hackios-xnu-userland 仓未本轮深查**——landscape（§3-A/B）已普查其角色，本轮无新事件（push 停在 10-25）。
8. **zendot 文章作者身份/与上游关系未考**——文章内容与上游官方文档逐项一致、无独家爆料，判定为第三方导读；未深挖作者背景（对本项目无行动价值）。

---

## 附录 A：本轮取证来源清单

**网络（代理 7897）**
- zendot 文章 zh/en：zendot.org/posts/oosexgang-hackios-xnu-kernel（webReader ×3 + curl 原始 HTML 63,840 B 存档核对）
- GitHub API：orgs/oosexgang/repos；repos/hakios-xnu-kernel & hakios-sm7325 的 git/trees HEAD recursive（52 + ~1000 entries；JSON 存档于 `%TEMP%/f14/`）
- raw.githubusercontent.com：sm7325 仓 README/device.conf/soc.args/soc.conf/sc7280.config/redwood.config/redwood_defconfig/pull-firmware.sh/pull-firmware-root.sh/pull-soc.sh/uefi README×2/redwood.toml；主仓 drivers/README.md、devices/README.md、devices/manifest.conf、socs/README.md、VERSION、boot-args.lst、CHANGELOG.md、docs/port-pkg110.md、docs/devices/redwood.md、docs/porting/drivers.md
- WebSearch ×4：a730 zap（Arch linux-firmware-qcom 文件表：`qcom/a730_zap.mbn`）；ath11k QCA6490/WCN6750 固件（amss.bin/m3.bin/board-2.bin；bdwlan.elf 提取先例；CodeLinaro ath11k-firmware）；`qcom,ipa-hw-ver`/sm8450 IPA（patchew 20260909-sm8450-ipa-v2 系列：ipa_data-v5.1.c，"Verified on SM7475/SM8450/SM8475"）；OnePlus Ace 2/11R 规格（Wi-Fi 6；FastConnect 6900 营销名；主线 sm8475 无独立 dtsi，经 sm8450.dtsi 系）+ WebFetch patchew 系列页（状态 = 未合、changes-requested、8 文件 +537/−8）

**本地（WSL 只读）**
- `~/hakios/kernel/`：VERSION（2.1.13）、CHANGELOG.md（头 30 行）、drivers/ 全清单+字节数、wifi/lx/ 全清单、devices/phk110/ 全 32 文件+字节数（pull-firmware.sh 占位、device.conf、soc.args、sm8475.config、phk110.config、phk110Pkg 全套、DTB/DTS）
- `devices/phk110/uefi/files/Resources/DTBs/phk110.dts` grep：GPU（adreno-gpu-gen7-4-0/Adreno730v3/chipid 0x7030002/kgsl@3d00000/gen7-gmu@3d69000/adreno-smmu@3da0000/zap-shader）、WiFi（cnss-qca6490@b0000000、wlan-en、6 路供电）、IPA（@3e00000、reg 0x84000/0xfc000、cfg-offset 0x140000、hw-ver 0x16、wdi3-over-gsi）、remoteproc（cape-adsp-pas@03000000/cape-cdsp-pas@32300000/cape-modem-pas@04080000/slpi/spss）、固件名字串（spss1*.mdt/slpi/ipa_fws/trustedvm/cpusys_vm/evass/vpu20_4v）、触摸（synaptics-s3910 + tcm-spi-hbp）、bootargs（oplus 22803、NT37705 面板）、触感（hv-haptics@f000 + pm8350b-swr-haptics）、音频（wcd938x+lpass-cdc+swr）
- 本仓：docs/STATUS.md、docs/research/landscape-2026-11-08.md、docs/research/f13-virtual-display.md、docs/waves/wave1-hwmap.md（IPA/WiFi/触感/音频节）

**上游驱动文件头深读（本地树，= 上游同字节）**
- `drivers/gpu/hakios.adreno.c`（头 80 行：22 步法、a660 固件、chipid 0x06030500、fuse 唯一身份源）
- `drivers/wifi/hakios.wifi.c`（头 60 行：16 步法、WPSS PIL、TZ image 6、wlfw=ath11k stand-in）
- `drivers/audio/hakios.adsp.c`（头 60 行：11 步法、TZ image 1、APR、battmgr 同 DSP）
- `drivers/modem/hakios.mpss.c`（头 40 行：TZ image 4、QMI WDA/NAS、QMAP、85 MB→246 MB）
- `drivers/modem/hakios.ipa.c`（头 60 行 + 版本 grep：**IPA 4.11 + GSI 2.11 硬编码**；reg 布局自 ipa_data-v4.11.c）
- `drivers/README.md`（上游：12 子系统地图 + 驱动三规则 + driver-review 审计制度 + provenance.allow 写白名单）

## 附录 B：术语速查

SM7325 = 骁龙 778G = yupik = SC7280 族；SM8475 = 骁龙 8+ Gen 1 = cape（taro 族）；Adreno 642L（a660 族固件，chipid 0x06030500）→ Adreno 730v3（gen7，chipid 0x7030002）；WCN6750/QCA6490 = FastConnect 6700/6900 营销名下的 ath11k 芯片族（AHB=WPSS-PIL / PCIe=CNSS+MHI 两种挂法）；WPSS/ADSP/MPSS/CDSP = SoC 内 Hexagon 远程处理器，固件皆 .mdt+.bNN 签名分段经 TZ（PAS）认证加载；IPA = 调制解调器数据路径加速器（GSI = 其 DMA 引擎）。
