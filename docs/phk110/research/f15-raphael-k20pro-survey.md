# 红米 K20 Pro（SM8150）移植传闻核实与迁移评估

日期：2026-11-10 ｜ 执行：F15 调研（阶段 29）｜ 纯调研：零手机、零刷写、零构建
方法：GitHub REST/raw + git shallow clone（raphael-bringup 分支，depth 60）+ web 页面取证，代理 127.0.0.1:7897；WebSearch 一次
基线：`docs/research/f14-sd778g-zendot-survey.md`（2026-11-09）+ `upstream-manifest.txt`（hakios-xnu-kernel @96ffbc5、hakios-sm7325 @04fbfff）
产出：本报告（git commit，message 前缀 "F15 research:"）

> 证据分级沿用 F14：**[实证]** = 文件/commit/页面可复现来源；**[实测转述]** = 作者文档自述的真机结果（我们未复现）；**[推断]** = 类比/待核。

---

## 0. 摘要（判定先行，六条）

1. **"raphael 支持存在" = 证实，但不在上游官方 org，而在社区 fork**。上游 oosexgang org（7 个仓）无任何 raphael/sm8150 仓；上游 main 的 `devices/manifest.conf` 只登记 redwood+qemu，`docs/devices/` 只有 redwood.md/qemu.md，main README 不提 raphael。raphael 移植的真身在 **HeliumStudio-Dev/hackios-xnu-kernel**（`raphael-bringup` 分支 + 已发布的 `raphael-uefi` Release）与后续接手的 fork **adelholzener69/hakios-xnu-kernel-raphael**（`raphael` 分支）。
2. **"GPU 驱动已修好" = 证实（有边界）**：Adreno 640 经 freedreno FD640 出 OpenGL ES 3.2，1080×2340 三角形绘制+读回无 GL 错误、桌面确认可用 [实测转述]；但 **Metal 明确不可用**（作者自述 "Metal is not available on either"），而上游 redwood 已是"Metal 窗口服务器出画、滑动 100–104 fps"。就 GPU 而言 raphael 反而落后 redwood 半步。
3. **"WiFi 已修好" = 部分证实**：WCN3990/ath10k SNOC 栈，5 GHz WPA3-SAE（H2E/PMF/IGTK）与 2.4 GHz WPA2 的关联、取地址、**真实网页加载**均经真机验证 [实测转述]；但作者原文"连接仍不稳定……此次提交保存已有实现，**不声称已经修复该问题**"，且关闭再开启 WiFi 后无法重连（日志 `failed to power on device: -19`）是文档明写的已知 bug。合拢上游 redwood 的 "wifi works" 口径，raphael WiFi 还差一口气。
4. **"4G 已修好" = 证伪**。作者自己的设备状态表（`devices/raphael/device.conf`，rapheal 分支 tip）：**`cellular missing`**；启动参数 `modem=0`（蜂窝链路不跑）；状态文档工作顺序里蜂窝排第 4 步（在存储持久化之后）；RAPHAEL-WIFI.md："保留这些上游改动，**但不启用 raphael 蜂窝功能**"。SM8150 上 modem 固件（wlanmdsp.mbn 经 MPSS PAS 4）确实被加载——但那是为了 **WiFi 固件跑在 modem DSP 里**，与蜂窝数据/注册无关。
5. **"几乎完全正常" = 夸大**。对照上游 redwood 的验收尾径：raphael 缺 **存储持久化**（旧树验证过 userdata 接管，迁移到新基线后丢失，`storage missing`/RAM-only）、蜂窝、蓝牙、相机、Metal、充电、麦克风（扬声器单声道有）；CPU 只有 7/8 核（core 0 留给 loader）。综合完成度 **≤ redwood**，不存在"远超 redwood"。
6. **时间线判定 = F14（11-09）之前的进展，但 F14 情报口径有盲区**：Helium-Studio 的 7 条 raphael-bringup 提交全部落盘于 **2026-10-25**（UEFI/loader、GT9886 触控+按键、OSM 调频、A640+TE 扫描、userdata 存储、ath10k+WPA3、文档），10-27 发布 raphael-uefi 镜像并完成"迁移到上游重写后的 main"；11-03 起中文圈病毒传播（smzdm 文章）；11-08 adelholzener69 把历史 squash 进 fork 并追加 16 条提交（扬声器音频、触感、手电）。**F14 错过的原因 = 只查官方 org**，没有扫 fork 网络、unixnu.com 设备目录与中文社区；这不是"过去几天的新进展"，而是"过去两周在 fork 生态里持续发生、且已出圈到大众媒体的进展"。

---

## ① 三条主张逐条核实（证据表）

| # | 传闻主张 | 判定 | 一手证据 | 备注 |
|---|---|---|---|---|
| 1 | raphael 支持存在 | **证实（社区 fork，非上游）** | ① 官方侧证据（均为负面）：org 仓列表（仅 7 仓，push 至 2026-11-10）https://github.com/orgs/oosexgang/repositories ；main `devices/manifest.conf`（redwood+qemu+uefi，无 raphael）https://raw.githubusercontent.com/oosexgang/hakios-xnu-kernel/main/devices/manifest.conf ；`docs/devices/`（index/qemu/redwood）https://github.com/oosexgang/hakios-xnu-kernel/tree/main/docs/devices 。② fork 侧证据（正面）：https://github.com/HeliumStudio-Dev/hackios-xnu-kernel （标题自述 "HackiOS XNU kernel for Redmi K20 Pro aka Mi 9T Pro (raphael)"，`raphael-bringup` 分支 @57722468a3）；https://github.com/adelholzener69/hakios-xnu-kernel-raphael/tree/raphael （squash 基座 = 上游 main tip 63fc2b4633，fork 独有 `raphael` 分支 @3233e83714） | Helium-Studio 主账号 https://github.com/Helium-Studio 的 /hackios-xnu-kernel 301 → HeliumStudio-Dev（重定向验证）。上游 PR 列表页 JS 渲染无法匿名确认"有无 raphael PR"，但 manifest/设备页/README/org 四处皆无 → 未被上游收编 [实证] |
| 2 | GPU 已修好 | **证实（GLES 层）** | `devices/raphael/kit/extract-gpu-firmware.sh`：固件 = `a640_gmu.bin`、**`a630_sqe.fw`**、`a640_zap.mdt/.b00/.b01/.b02`（"the a660_* files of other phones must not be used"）https://github.com/adelholzener69/hakios-xnu-kernel-raphael/blob/raphael/devices/raphael/kit/extract-gpu-firmware.sh ；`device.conf`：`gpu works Adreno 640 through GLES (gpu=1); needs fw-gpu/` ；`docs/RAPHAEL.md`：A640 全部初始化步骤、TZ zap shader 认证、`freedreno / FD640 / OpenGL ES 3.2`、三角形绘制 42 ms/回读 25 ms、CoreAnimation accelerated renderer（2026-10-23 真机日志 `logs/011423-run.log`）[实测转述] | 边界：Metal 不可用（zh README："图形路径 Mesa/Freedreno，OpenGL ES；**当前不提供 Metal 驱动**"）；默认 GPU 时钟 257/427 MHz；"不保证所有场景稳定 60 FPS" |
| 3 | WiFi 已修好 | **部分证实（首次连接可用，重连 bug 未修）** | `docs/RAPHAEL-WIFI.md`（中文，作者亲笔）："已通过 2.4 GHz WPA2、5 GHz WPA3 SAE 的关联和实际网页加载……**连接仍不稳定；关闭再开启 Wi-Fi 后无法正常扫描。此次提交保存已有实现，不声称已经修复该问题**" https://github.com/adelholzener69/hakios-xnu-kernel-raphael/blob/raphael/docs/RAPHAEL-WIFI.md ；zh README 实测表："Wi-Fi 关闭后重新开启 **仍有问题**：……`failed to power on device: -19`" https://github.com/HeliumStudio-Dev/hackios-xnu-kernel/blob/raphael-bringup/README.raphael.zh.md（fork 内同名文件） | redwood 口径 "wifi works (radio/驱动/入网)" vs raphael "partly"——raphael 不高于 redwood |
| 4 | 4G 已修好 | **证伪** | `device.conf`：`status cellular missing` ；`docs/RAPHAEL-K20PRO.md` L23："Bluetooth, cellular, cameras……\*\*no\*\*" ；实测 XL_CMDLINE 含 **`modem=0`**（L125）；`docs/RAPHAEL-K20PRO-STATUS.md` 工作顺序："3. Storage persistence. 4. Cellular, then cameras"，且"NV partitions pulled in step 3 are **already the first ingredient**"（= NV 只是备料，未开始） | SM8150 的 WiFi 依赖 MPSS（PAS 4）签名装载 `wlanmdsp.mbn` + TFTP/PD mapper——modem PIL 链路因此真机通过 [实测转述]，但这是 **WiFi 的载体**，不是蜂窝；蜂窝的 NAS/QMI WDS/IPA 链路在 raphael 上明确"不启用" |
| 5 | "几乎完全正常" | **夸大** | 见 §③ 完成度总表：缺 storage 持久化/cellular/BT/相机/Metal/充电/麦克风/第 8 核；wifi 重连 bug | 与 redwood 对比：redwood 有 storage 持久化、相机、Metal 出画、麦克风、8/8 核 |

**消息源推测**：中文圈 2026-11-03 起的病毒传播（smzdm 文章 https://post.smzdm.com/p/aomqr29m ，"2019 年的红米 K20 Pro 启动 iOS 16.5、弹出式前摄收起"——全文被腾讯验证码墙挡住未能直读，仅搜索摘要可见 [待核]）；以及 HeliumStudio-Dev 仓的中文测试指南（README.raphael.zh.md，561 行，本身就是面向中文读者写的）。UniXNU 生态的 unixnu.com 设备目录另有 raphael 条目（见 §②-3），口径为"compile-only"，与"几乎完全正常"不符。

---

## ② 谁在哪个仓哪条分支哪个 commit 做的（时间线全解）

### 2.1 人与仓

| 角色 | 谁 | 仓/分支 | 性质 |
|---|---|---|---|
| 原始 bringup | **Helium-Studio**（17 岁开发者，账号 2020-07 建；公开仓为 Zundamon Kernel/AnyKernel3 等 raphael 刷机生态；文档引用自己的 `zundamon-miui-5.4` defconfig 与 "Helium A640 notes"） | HeliumStudio-Dev/hackios-xnu-kernel，`raphael-bringup` 分支（@57722468a3）；Release `raphael-uefi`（2026-10-27T11:25Z 发布 DEBUG r5 UEFI 镜像，GPG 已验证签名） | 公开 fork（基座 = 上游重写前 main 8851317 时代） |
| squash+接手 | **adelholzener69** | adelholzener69/hakios-xnu-kernel-raphael，`raphael` 分支（@3233e83714，无 Release） | 公开 fork（基座 = 上游 main tip 63fc2b4633，2026-11-06） |
| AI 协作 | squash 提交 co-author：`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` [实证] | — | 与我们同为 AI 协作工程范式 |
| 上游官方 | oosexgang（shimoku/shimoku74） | hakios-xnu-kernel main | **未收编 raphael**；但 11-06 合并了 dlz3388461878-cmd 的两个社区 PR（#53 soc-args 寄存器宽度解码、#54 var-store 旧档回退）——raphael fork 的基座恰好包含它们，说明 fork 圈子与上游在互馈 |

### 2.2 commit 级时间线

| 日期 | 事件 | 证据 |
|---|---|---|
| ≤2026-10-23 | raphael-bringup 已在私有/早期树推进（壁纸/触控 GENI I2C 残留修复/RenderBox Metal buffer 对齐/UFS 只读对照 6 LUN 426446848 字节/GPU 频率实验） | `docs/RAPHAEL.md` "第二阶段（2026-10-23）" [实测转述] |
| **2026-10-25** | Helium-Studio 在公开 fork 落盘 7 条 bringup 提交：① UEFI+XNU loader（28939ed）② GT9886 触控+按键（4c71627）③ SM8150 **OSM** 调频（d17aab6）④ **Adreno 640 + TE 扫描**（8a3135e）⑤ userdata 系统卷+var 存储（79f4333）⑥ **ath10k + WPA3**（aa21593）⑦ 文档（5772246） | shallow clone 实取 git log [实证]；同日上游自身正做 IPA 2.0 数据路径/NAS 注册重试/DPM Open Port（shimoku74，10-25）——见 §⑥ 附带情报 |
| 2026-10-27 | ① 发布 raphael-uefi Release（DEBUG r5，10:25 UTC）② "统一 main，GLES-only"：上游重写历史后 rebase --onto 新 main，放弃 Metal、只保留 GLES；`docs/UPSTREAM-BASELINE-20261027.md` | Release 页 + UPSTREAM-BASELINE 文档 [实证] |
| 2026-11-03 前后 | 中文圈病毒传播（smzdm） | WebSearch 摘要；原文验证码墙 [待核] |
| 2026-11-06 | 上游合并 dlz 两 PR（soc-args/var-store）→ main tip 63fc2b4633 | 上游 commit 列表 [实证] |
| **2026-11-08** | adelholzener69 一次性 squash 全部历史为 `fdf53f296b`（177 文件：devices/raphael 全套 + `drivers/gpu/hakios.adreno.c` +576/−82 + `drivers/wifi/hakios.wifi.c` +1406/−82 + `wifi/lx/ath10k/` 等），随后 6 小时内 16 条提交：扬声器音频（TFA9874+MI2S+防爆破 backlog，215b2ed8）、手电（PM8150L flash v2 + Control Center 调光，c3929b9e/7241b3c）、ERM 触感（PM8150B，75c9ab5）、WiFi 扫描重试（745c74c）、modem 分段 8 字节对齐放宽（8d01742）、音频服务内存锁定上限（3233e83） | fork commit 列表 [实证] |
| 2026-11-10（今天） | 上游 main 的 **mtk 分支**新推"bluetoothd of iOS 16.5 on the MT6631: HCI over…"（蓝牙在 MTK 第二台真机打通）；hakios-mt6768 同步推送 | 上游 mtk 分支 tip c36d664121 [实证] |

### 2.3 生态里的其他 raphael 条目（核实"该项目"边界）

- **UniXNU 家族（takasugl 系，我们 upstream-manifest 另一条线）**：unixnu.com 设备目录有 **3 个 raphael 条目**：`raphael-guowenye`（guowenye/UniXNU-raphael，"Independent Redmi K20 Pro port; **compile-only default** with separately gated native handset bring-up"；显示侧真机过了 1080×2340 framebuffer 映射与 SpringBoard 观察，但 "**No native UI frame yet**"，发布锚 2026-11-05，SoC 仓 guowenye/UniXNU-sm8150-common @c77321d8）+ jackyhowh + JohnLeeeeeee678 两个条目（未深查）。https://unixnu.com/zh/devices/raphael-guowenye [实证]
- **Mu-Silicium（Project-Silicium）**：`Platforms/Xiaomi` 36 个设备包中 **无 raphaelPkg**（alioth…sweet_k6a 全列 grep 无 raphael）——raphael 的 UEFI 是 fork 自带 `raphaelPkg`+`mu-silicium.patch`（684 行）打到 Mu-Silicium BASE **e51cd877** 上的。注意列表里 **有 cepheusPkg（小米 9，SM8150 同 SoC）和 nuwaPkg（Redmi K60，SM8475！）**——后者对 PHK110 是潜在 UEFI 备胎（见 §⑤）。https://github.com/Project-Silicium/Mu-Silicium/tree/main/Platforms/Xiaomi [实证]
- **hackios.net / zendot.org**：两站抓取均无 raphael/K20/8150 字样 [实证]（zendot posts 索引 200、hackios.net 首页 200，grep 空）。

---

## ③ 完成度总表（对照上游 redwood 设备页验收尾径）

判定口径 = 上游 `docs/devices/redwood.md` 的 works/partly/missing 三档 + fork 自身 `devices/raphael/device.conf`（raphael 分支 tip，由 tools/docs-gen.py 生成的权威表）。

| 部分 | redwood（上游官方，main@63fc2b46） | raphael（fork 自述，2026-11-08 tip） | raphael 相对 redwood |
|---|---|---|---|
| display | works（UEFI fb + GPU 画帧） | works（UEFI fb + **TE 门控三缓冲 page flip** + **面板 DCS 亮度**（brightness=1 brightness_dcs=1，亮度滑条经 backboardd→`kern.hakios.brightness`→DSI 0x51）） | **亮度控制 redwood 没有**——raphael 独有 |
| touch | works（GT9916/FT3680 SPI） | works（**Goodix GT9886**） | 平 |
| buttons | works | works | 平 |
| cpu | works（8/8 核，大核 2.4 GHz） | works（**7/8 核**，core 0 留给 loader/UEFI 写通道；OSM 3 域 1785/2419/2841 MHz） | raphael 少 1 核 |
| gpu | works（642L GLES + **Metal 窗口服务器出画**，滑动 100–104 fps） | works（640 GLES；**Metal 无**） | raphael 差半步（无 Metal） |
| storage | works（UFS 经 loader 读；/private/var 持久 var_store=1 ufs_write=1） | **missing**（RAM-only，重启全丢；旧树验证过的 userdata 接管在 10-27 基线迁移后**未随行**，ROADMAP 第 3 步） | **redwood 优** |
| audio | works（扬声器+麦克风经 ADSP） | works（**仅扬声器**：ADSP MI2S + TFA9874 功放 + 30 s 静音休眠；WCD9341 SLIMbus 耳机/麦克风"much harder"，CONFIG_HAKIOS_MIC 未设） | raphael 缺麦克风 |
| battery | partly（电量经 ADSP battmgr；不充电） | works（电量经 loader/高通 charger 驱动，只读，commit 84647ba） | 平（都不充电；raphael 电量链更浅） |
| haptic | works（AW86927） | works（PM8150B ERM，haptic=5，/dev/hakios-haptic） | 平 |
| torch | partly（PM8350C，torch=N） | works（PM8150L，torch=3，Control Center 调光，≤100 mA） | raphael 略好 |
| wifi | works（WCN6750/ath11k） | **partly**（WCN3990/ath10k SNOC；WPA2+WPA3 关联+网页加载；入网慢、开关后扫描空/-19 无法重连） | **redwood 优** |
| bluetooth | missing（只读侦察 bt=1） | missing | 平 |
| cellular | **partly**（modem 起、见网、SIM 绑定、IPA+en1 就位；**注册未达成**） | **missing**（modem=0，明确不启用） | redwood 优（但都无 4G 数据） |
| camera | works（Camera.app cam=5） | missing | redwood 优 |
| thermal | partly（27/27 传感器） | 表中未列（CONFIG_HAKIOS_THERMAL 未设） | raphael 未查 |

**结论表**：raphael = display/touch/buttons/cpu(7)/gpu(GLES)/audio(扬声器)/battery(只读)/haptic/torch 九项 works + wifi partly + storage/cellular/BT/camera 四项 missing。"几乎完全正常"不成立；且以 redwood 的口径衡量，**没有一项超越 redwood（除亮度与手电两个小项）**。

---

## ④ 逐驱动深挖（文件级证据）

### 4.1 WiFi（唯一真打通的"无线"链）

**栈判定**：**ICNSS + MPSS(PAS 4) + ath10k SNOC**（不是 redwood 的 WPSS/ath11k，也不是 PHK110 的 CNSS+MHI/ath11k-PCI）。RAPHAEL-WIFI.md 原文："本机使用 WCN399x / ICNSS、MPSS（PAS 4）和 ath10k SNOC。**不要使用 redwood 的 WCN6750 / WPSS / ath11k 配置**，也不要同时启动 qcacld 与 ath10k。" [实证]

- **控制链**：MPSS 签名装载（wlanmdsp.mbn）→ SMEM/SMP2P/GLINK/QRTR → RMTFS（只读 NV 快照 modemst1/2+fsg/fsc，写只改 RAM 副本）→ TFTP（只导出 wlanmdsp.mbn + server_check.txt）→ PD mapper → PDR → DMS（WLAN MAC 校验后经 WLFW 0x33 提交）→ **BDF**（按 `ro.boot.hwc` 选 `bd_f11cn.bin`/`bd_f11gl.bin`，拒绝缺省 0xff→通用 bdwlan.bin 的路径）→ MSA/SMMU（SID 0x640，MSA 区 `0x8bc00000+0x180000` 恒等映射）→ 五路 PMIC 供电（含 **PM8150L L10C 3312 mV/HPM**，外设 0x549）→ AOSS QMP QDSS 时钟投票。
- **主机路径**：12 路 level-high CE 中断、NAPI、HTC/WMI、数据收发。
- **调试工作**（docs/RAPHAEL.md 10-24 节，对我们 WiFi 战的参考价值最高的部分）：固件 early crash（SMP2P wlan bit1 → WLAN PD DOWN/UP）→ 对照本机 6.12 分支 4 条 commit（`4c37abf82a78` ICNSS/MSA/SID/CE、`f48d0a8dfc4e` L10C 供电、`ad7584e9454f` 6.12 用 ICNSS+qcacld 的配置辨伪、`0ad06c1c3f64` QDSS 时钟投票）→ 修好后两轮真机 `0x21 FW_READY`（step 14）；再修 BDF 选择（cnss-daemon 机型逻辑核对）→ 扫描 dwell ≥120 ms → WPA3 SAE H2E 真机联网。
- **代码与构建**：`drivers/wifi/hakios.wifi.c` +1406/−82（ICNSS 步法）；`wifi/lx/ath10k/{host.c 14.7 KB, include/, patches/icnss-bootstrap.patch 1.5 KB}`；`tools/mk-ath10k.py`（**固定源码管线**：linux **7.0.14** tar.xz + freebsd 15.1 src + wpa_supplicant 2.11 + mbedtls 3.6.7，全部 SHA256 锁定 → 编出 `ath10k.o` → `WIFI_OBJECT=... make kernel` 链入 XNU）；`device.conf` 选 `WIFI_ATH10K=1`。启动参数 `wifi_step=15 wifi_lx=2 wifi_bdf=... wifi_smmu=2 wifi_keep=1 ...`。
- **验收尾具范式**：`tools/check-wifi-{mdt,smem,doorbell,proxy,memory,rmtfs,tftp,pd,pdr,qrtr,icnss,dms,diag,dump,microdump,smmu}.py` 十六项主机回归 + `tools/wpa-test/run.sh` + `mk-ath10k.py --sae-test`（195 项 WPA2 检查、WPA3 SAE/PMF 检查）——"ASan/UBSan 通过不能替代实机扫描、重新关联及网络稳定性验证"。

### 4.2 4G/蜂窝（证伪细节）

- `device.conf`：`cellular missing`；`CONFIG_HAKIOS_QMI=y / CONFIG_HAKIOS_MODEM=y` 在 config 里（**为 WiFi 的 MPSS 链服务**），但运行参数 `modem=0`（蜂窝步法不跑）。
- `docs/RAPHAEL-K20PRO-STATUS.md`：Cellular 行 = "**no**｜modem bring-up（第 3 步拉到的 NV 分区已是第一份原料）"；工作顺序：扬声器→触感/手电→**存储持久化→蜂窝→相机**。即蜂窝排在存储之后，连第二步都没到。
- UPSTREAM-BASELINE-20261027.md："最新提交主要涉及蜂窝 MPSS/IPA……**保留这些上游改动，但不启用 raphael 蜂窝功能**"——上游 redwood 的 IPA/QMI 蜂窝代码被原样带着，但 raphael 没开。
- "Shows 4G" 到什么程度：**没有任何注册/数据/VoLTE 证据**。搜索与文档均未见 raphael 蜂窝实测记录。→ 该"4G"信息为误传或与上游 redwood 的状态条（modem 见网、SIM 绑定）混淆。

### 4.3 GPU

- **内核侧**：同一 `hakios.adreno.c`（上游文件）被 fork 扩 **+576/−82 行**以支持 Adreno 640：固件族 `a640_gmu.bin / a630_sqe.fw / a640_zap.mdt+b00–b02`（**SQE 用 a630 的**——低配芯片混用高/低配固件名的又一实例，与 redwood 642L 用 a660 固件同构）；固件从 **vendor.img 离线解包**（simg2img+7z，`extract-gpu-firmware.sh`，GMU 文件 SHA256 前缀 `3ff0c027…` 与 V12.5.2.0 比对）。
- **真机结果** [实测转述]：A640 全部初始化 + TrustZone zap 认证 + freedreno FD640 OpenGL ES 3.2；1080×2340 三角形绘制 42 ms/回读 25 ms，GL error 0；CoreAnimation accelerated renderer；桌面"基本流畅"。
- **性能**：默认 257/427 MHz，提到更高频后仍有 32–34 ms 长帧；作者明言"不能据此声称稳定 60 fps"。用户态 = Mesa（版本未在文档中给出，文档引用 Mesa 源构建）+ GLES；**无 Turnip/Metal**（上游 2.3.x 的 Turnip+AdrenoMetal+m2v 链未进入 raphael 基线）。
- **配套显示**：DSI 命令模式（Samsung EA8076）TE 相位测量（INTF_TEAR_INT_COUNT_VAL − VSYNC_INIT_VAL，150 ms 观察三边沿）→ 三缓冲 page flip（0x9c000000/0x9ca00000/0x9d400000，36 MiB 显示保留区）→ VIG0/CTL0 flush + INTF1 TE 中断确认；`fb_scan=1`；`hakios.display.c/hakios.brightness.c` 为 raphael 独有驱动。

### 4.4 其他值得一提的实现点（对 PHK110 有迁移价值的）

- **OSM 调频**（SM8150 用 OSM 非 EPSS）：三个 OSM 域 0x18323000/0x18325800/0x18327800，硬件 LUT 读法（+0x110，32 B/行；性能请求 +0x920），50 ms 负载采样双档调速，真机上限 1785/2419/2841 MHz。
- **DCS 亮度链**：backboardd 滑条值 → `kern.hakios.brightness` sysctl → 内核 → DSI 控制器 DCS 0x51 → 面板。**上游 redwood 没有亮度控制**，这是全生态第一个面板亮度实现。
- **UEFI 逐机化**：UEFI 从目标手机自己的 XBL 提取构建（`tools/extract-raphael-uefi.py`→`kit/build-uefi-image.sh`），三个 vendor DXE（DALSYSDxe/UsbConfigDxe/ButtonsDxe）**先验字节同一性再打单字节 patch**（`check-xbl.py` + `raphael-firmware-patches.json`）；"官方发布的 UEFI 内嵌作者的 XBL，XBL 不同的手机黑屏"——这就是他们 fork 存在的主要理由。
- **固件拉取变体**：`kit/pull-firmware.sh` 走 **TWRP + adb root**（非 redwood 的 adb/Magisk 法）：只读挂载 modem 分区拉 `modem.mdt+wlanmdsp.mbn+BDF+modem.bNN`（→ fw-raphael/，WiFi 用）、adsp.mdt 全段（→ fw-audio/）、XBL 两镜像（→ UEFI 构建）；umask 077、git-ignore、逐目录报文件数。
- **var_store 保守化**：恢复时跳过快照、列出库存、`var_skip=` 参数（11-08 的上游 PR #54 同主题）。

---

## ⑤ 对 PHK110（SM8475 / Adreno 730 / WCN6750-qca6490-PCI / IPA 5.1）的可迁移性评估

### 5.1 能直接抄（模式/工作流，与 SoC 解耦）

| # | raphael 资产 | PHK110 用法 | 价值 |
|---|---|---|---|
| 1 | **`tools/mk-ath10k.py` 固定源码构建管线**（tarball+SHA256 锁定 → 主机侧编出驱动 .o → `WIFI_OBJECT=` 链入 XNU；构建可复现、可 CI） | 给 v0.6 的 ath11k-PCI 对象做同款 `mk-ath11k.py`；源码锁 linux 6.x/7.x + 固件版本，主机回归 `check-wifi-*.py` 范式照搬 | 高——把"Linux 驱动源码级移植"从手工作业变成可审计管线 |
| 2 | **主机回归检查族范式**（16 个 check-wifi-*.py + wpa-test + sae-test；"构建通过 ≠ 验收"纪律） | 我们的 v0.5/v0.6/v0.7 各战前先写 `tools/check-phk110-*.py`（GPU 固件校验/WPA 重放/SMMU 映射等） | 高——零手机成本，先在主机把协议边界走通 |
| 3 | **BDF/固件显式选择 + 拒绝缺省**（`wifi_bdf=bd_f11cn.bin` 按机型/区域显式给，拒绝 0xff 缺省路径） | PHK110 的 board-2.bin/bdwlan 变体选择（qca6490 hw1.0）用同款纪律；`pull-firmware.sh` 里按 `ro.boot.hwc`/机型 prop 分支 | 高——少走 cnss-daemon 选错 BDF 的弯路（raphael 已代踩） |
| 4 | **UEFI vendor DXE"字节校验+单字节 patch JSON"**（`check-xbl.py`/`raphael-firmware-patches.json`） | 我们的 udon UEFI 的 UsbConfigDxe/DALSYSDxe 手术改造成同款 JSON 清单+校验脚本；任何 ColorOS 固件升级后先跑校验再 patch | 中高——与上游 redwood README 的 5-patch 清单互补 |
| 5 | **DCS 亮度链**（`hakios.brightness.c` + backboardd→sysctl→DSI 0x51） | PHK110 NT37705 面板未来要亮度时，这是全树唯一先例（redwood 无）；读其 sysctl 挂点与 backboardd 注入方式即可 | 中（v1.0 后） |
| 6 | **固件拉取的 TWRP 变体** | 备用路径；PHK110 主路径仍是 Magisk root（wave16c 配方），但"只读挂载分区 + cat 逐文件 + umask 077 + 逐目录报数"的脚本结构可抄 | 中 |
| 7 | **per-device BDF 之外的"私有输入永不入库"纪律**（fw-*/git-ignore/umask 077/Release 只放 UEFI 不放固件） | 我们的 pull-firmware 落地时照办（ColorOS 固件同样含身份/校准数据） | 高（合规面） |

### 5.2 不能抄/不适用（跨代差异，明确边界）

| raphael 做法 | PHK110 为什么不适用 |
|---|---|
| ath10k SNOC / ICNSS 控制链 / MPSS-wlanmdsp | SM8475 WiFi = **CNSS-qca6490 + PCIe + MHI + ath11k**，挂在 PCIe0 上；ICNSS/MPSS-wlan 整条是 SM8150 专有。但 §4.1 的"控制链清单逐项真机验证"方法论通用 |
| OSM 调频三域 | SM8475 = EPSS（我们 wave1 已建 sm8475.config，基址同 SC7280 族） |
| a640/a630 固件族、A640 初始化参数 | Adreno **730/gen7**（chipid 0x7030002）——a6xx 内换参（642L→640）的先例成立，但 6xx→7xx 仍是"新写参数层"（F14 §2.3 已判定）；raphael 连 Turnip/Metal 都没上，**对我们 v0.5 无增量** |
| TE 门控命令模式显示 | PHK110 面板经 ABL/UEFI fb（NT37705），我们已有 23.x MiniIOMFB 出画链；TE 相位法仅当我们转命令模式自管刷新时才有用 |
| **蜂窝：零参考** | raphael 没有蜂窝。PHK110 v0.7 的 IPA 5.1 参考仍是 F14 锁定的主线 sm8450 IPA v5.1 系列 + 上游 redwood 的 IPA 4.11 代码与 10-25 时代的 DPM/WDS 时序 commit |
| var_store 的存储持久化 | raphael 自己也没跑通（迁移后 missing）；PHK110 的 UFS 写参照上游 redwood（v0.4 已 S0–S8 全通）即可，无需抄 raphael |

### 5.3 意外情报：Mu-Silicium `nuwaPkg`（Redmi K60 / SM8475）

Mu-Silicium 上游 `Platforms/Xiaomi` 有 **nuwaPkg = Redmi K60（SM8475，与 PHK110 同 SoC cape/taro 族）** 和 cepheusPkg（Mi 9/SM8150，raphael UEFI 的同族基座来源）。含义：若我们的 udon UEFI（takasugl 线）出现推进困难，**SM8475 的 Mu-Silicium 设备包是现成的第二 UEFI 基座**（raphael 正是"Mu-Silicium 同族包 + 自带 Pkg + patch"起家的）。 [推断，未验证 nuwaPkg 成熟度]

### 5.4 "如果我们抄它，下一个波该干什么"——Top 3

1. **把"固定源码驱动对象管线"立起来（v0.5/v0.6 共用前置）**：以 `tools/mk-ath10k.py` 为模板写 `tools/mk-ath11k.py`（拉 ath11k/mac80211 源 + SHA256 锁 + 补丁集进 `wifi/lx/ath11k/patches/`，主机编 .o），同时把 raphael 的 `check-wifi-*.py` 范式改造成我们的 `tools/check-phk110-wifi-*.py`（CNSS 供电序列/MHI/QRTR/WDI 各一）。产出物与手机无关，本周即可开始。
2. **UEFI patch 管理收编成"清单+校验"（v0.x 工程质量项，半天）**：把我们 阶段 18–24 的 udon UEFI 手术（UsbConfigDxe start_ex/DALSYSDxe 等）写成 `devices/phk110/uefi/firmware-patches.json` + `check-xbl.py` 式的模块哈希校验脚本；顺带登记 Mu-Silicium nuwaPkg @commit 为 UEFI 备胎锚点（一行 BASE 文件）。
3. **修正情报面 + 亮度/sysctl 注入侦察（本阶段完成）**：① 在 STATUS/landscape 里补记"raphael fork 生态（两仓+release+smzdm 出圈）"与"上游 mtk 蓝牙打通"，把跟进范围从官方 org 扩到 fork 网络 + unixnu.com；② 亮度链虽排在 v1.0 后，但读一遍 `hakios.brightness.c` 的 sysctl 挂点与 backboardd 注入法成本极低，先入档（PHK110 亮度是 redwood 也没有的能力，将来是加分项）。

---

## ⑥ 时间线判定与跟进节奏建议

### 6.1 这是 F14 之后的新进展吗？

**不是。** 三段式：
- raphael 的 WiFi/GPU/触控/OSM 真机验证 = **2026-10-23～10-27**（早于 F14 十三天）；
- 11-08 的 fork squash+音频/触感/手电 = F14 前一天发生，但发生在 **fork**（F14 的 org 扫描看不到）；
- 我们直到今天（11-10）才看见，是因为 **触发源（11-03 smzdm 病毒传播）不在我们的扫描面里**。
- F14 的方法论盲区：只扫了 `orgs/oosexgang/repos`。ralphel 类社区工作住在 **fork 网络**（`/forks?sort=newest` 一个调用即可见）与**第三方设备目录**（unixnu.com）。

### 6.2 跟进节奏建议

| 面 | 频率 | 动作（全部 ≤5 次调用） |
|---|---|---|
| 官方 org（oosexgang） | 每周 | repos 列表（按 pushed 排序）+ main 的 manifest.conf/docs/devices + CHANGELOG 头部 |
| **fork 网络** | 每周（新增，本轮教训） | 主仓 `/forks?sort=newest` 取前 30，看 push 日期 > 上次锚点的 fork 名（名字里带设备代号的一票即可判） |
| UniXNU 线（takasugl + unixnu.com） | 双周 | takasugl repos pushed + unixnu.com 设备索引页 grep 新设备名 |
| 事件驱动 | 触发即查 | 任何中文社区/媒体出现"HakiOS/黑果iOS/XX 手机跑 iOS"——立即按本报告 §①–② 的路径核仓核 commit（0.5 天） |

理由：本轮实证显示"官方 org 沉默 ≠ 生态沉默"（fork 6 小时 16 commit、病毒传播 1 天出圈、上游 2 天后合并社区 PR）；每周双面扫 + 事件驱动，最坏滞后可压到 ~7 天（本轮实际滞后 7 天：10-25 工作 → 11-10 才吸收）。F14→F15 间隔 1 天内的深扫不必常态化。

### 6.3 附带情报（本轮顺带证实，修正 F14/landscape 旧结论）

1. **上游 redwood 蜂窝比 F14 记录的更活跃**：重写前 main（10-24/10-25，raphael-bringup 克隆的历史层可见）有 IPA "2.0 数据路径 + en1"、QMI DPM Open Port 次序修正、WDS Start Network Interface 注册后重试、NAS 信号缓存、运营商名进 SpringBoard、状态栏信号条注入等 commit——但当前官方 `docs/devices/redwood.md`（main@63fc2b46）仍写 "cellular partly… **no registration yet**"。解读：注册/数据会话代码在树上且测试周期里见过注册，官方验收尾径仍保守 [推断]。对我们 v0.7：**DPM Open Port → WDA → WDS bind/IP-family/start 的时序顺序是现成参考**（`docs/cellular.md` 亦在该时代已存在）。
2. **上游 mtk 分支蓝牙打通**（11-10 push："bluetoothd of iOS 16.5 on the MT6631: HCI over …"）——上游把蓝牙从"侦察"推到了"协议栈真机验证"，MTK 优先；QC 侧（我们）尚未见同级别动作。蓝牙对 PHK110 仍不排期，但"上游能跑 bluetoothd"改变了 F14"蓝牙只有第一步侦察"的判断。
3. 社区 fork 动能：上游主仓 fork 列表里出现 bramble（Pixel 6a）/a52sxq（Galaxy A52s）/garnet 等设备名 fork——"设备代号命名的 fork"可作为新设备支持的先行指标（raphael 即如此被发现）。

---

## ⑦ 诚实边界 / 未找到清单

1. **smzdm 文章全文不可读**（腾讯验证码墙）；"11-03 病毒传播"仅据搜索摘要与文章存在性 [待核]。
2. **所有"真机可用"声明均为作者文档自述 [实测转述]**：我们未复现任何一项；作者自己也写明"单次绘制读回成功不代表所有渲染路径正确""此次提交保存已有实现，不声称已经修复该问题（WiFi 重连）"。可信度加成项：run log 文件名+SHA256+字节级读回数字齐备、真机验收表保守（7/8 核不称八核）、GPU GMU 固件给了 SHA256。
3. **hakios.adreno.c/wifi.c 的 +576/+1406 行 diff 未逐行读**（时间盒所限，判定不依赖它）；`docs/RAPHAEL-K20PRO.md`、`RAPHAEL-K20PRO-SOUND/THEOS/TROUBLESHOOTING.md`、`ROADMAP.md`（fork 列了但 404——README 引用了不存在的路径 [实证：404]）未全文读。
4. **上游 PR/issues 是否讨论过 raphael 未确证**（GitHub PR 列表页 JS 渲染，匿名 curl 只见查询回显）；manifest/设备页/README/org 四处均无 raphael 是硬证据，"未收编"判定由此支撑。
5. **dlz3388461878-cmd 身份未查**（账号 2026-10 建，2 个仓，PR #53/#54 被 11-06 合并；是否 raphael 圈子成员未证）。
6. **adelholzener69 fork 无 Release、无真机日志入库**；其 11-08 的音频/触感/手电三项 works 仅有 device.conf 背书，无 run log 细节（低于 Helium-Studio 侧文档的证据密度）[待核]。
7. **Mu-Silicium nuwaPkg 成熟度未查**（仅确认存在）；作为 PHK110 UEFI 备胎的可行性是 [推断]。
8. F14 遗留的相关项未动：`ipa-hw-ver=0x16` 枚举解码、lx 层对 ath11k-PCI 的覆盖度——本轮不受影响。

## 附录 A：本轮取证来源清单

**GitHub API/HTML（代理 7897）**
- orgs/oosexgang/repos?sort=pushed（7 仓，含 11-10 push 时间戳）；repos/oosexgang/hakios-xnu-kernel 的 commits（main + mtk 分支）、branches（main/legacy-hackios/mtk）、forks?sort=newest（30 条）、contents/devices/manifest.conf、contents/docs/devices
- repos/adelholzener69/hakios-xnu-kernel-raphael：branches（raphael@3233e837）、commits?sha=raphael（17 条）、commits/fdf53f296b（177 文件清单+全文 message）
- raw.githubusercontent.com（raphael 分支）：docs/devices/raphael.md、devices/raphael/device.conf、devices/raphael/README.md、devices/raphael/soc.args、devices/raphael/soc/configs/sm8150.config、devices/raphael/configs/raphael.config、devices/raphael/kit/{pull-firmware.sh, extract-gpu-firmware.sh}、devices/raphael/uefi/{BASE, README.md}、docs/{RAPHAEL.md, RAPHAEL-WIFI.md, RAPHAEL-K20PRO-STATUS.md, RAPHAEL-K20PRO.md, UPSTREAM-BASELINE-20261027.md}、README.raphael.zh.md（头 80 行）、tools/mk-ath10k.py（头 60 行）、wifi/lx/ath10k/{,patches/,include/} 清单
- raw.githubusercontent.com（upstream main）：README.md、COMMUNITY.md、docs/devices/redwood.md、devices/manifest.conf
- git shallow clone：github.com/HeliumStudio-Dev/hackios-xnu-kernel @raphael-bringup（depth 60，git log 50 条全录）
- HTML：HeliumStudio-Dev/hackios-xnu-kernel releases 页（raphael-uefi @2026-10-27T11:25Z，GPG verified）、Helium-Studio/hackios-xnu-kernel（301→HeliumStudio-Dev）、adelholzener69 releases（无）、oosexgang PR 搜索页（JS 渲染无结果）
- users API：Helium-Studio（id 67852324，7 公开仓）、takasugl（3 仓：uefi-udon/UniXNU-udon/biliCow）、dlz3388461878-cmd

**Web**
- WebSearch ×1："HakiOS raphael K20 Pro"（命中 HeliumStudio-Dev 仓、unixnu.com/zh/devices/raphael-guowenye、smzdm 文章、r/Mi9T）
- unixnu.com/zh/devices/raphael-guowenye（全文提取：compile-only、显示 bringup 记录、publication20261105、guowenye/UniXNU-raphael + UniXNU-sm8150-common@c77321d8）；zendot.org/posts（无 raphael）；hackios.net（无 raphael）；Project-Silicium/Mu-Silicium Platforms/Xiaomi（36 包，无 raphaelPkg，有 cepheusPkg/nuwaPkg）；smzdm.com（验证码墙）

**本地**
- `upstream-manifest.txt`（基线锚：kernel@96ffbc5、sm7325@04fbfff、UniXNU-udon@ad550a9、uefi-udon@475f9de）
- `docs/research/f14-sd778g-zendot-survey.md`（格式模板与对照基线）

## 补记（2026-11-10 晚，信源修正）

经澄清，原始信源 = **抖音视频**（非 GitHub）。这改写判定的适用范围而不推翻它：

- **公网代码层判定不变**：GitHub 全网（官方 org + 30 forks + unixnu.com）确实没有蜂窝栈——fork 自家 device.conf 写 `cellular missing`、`modem=0`。
- **新假设：私人构建先于开源**。抖音上有 4G 工作的 K20 Pro，最合理的解释 = 某porter（Helium-Studio 本人或另一人）**已私下跑通蜂窝但未 push**。这在此生态有先例（redwood 的蜂窝也是"文档宣称在案、代码迟到"模式）。含义：**SM8150 蜂窝栈"有人做成过"的先例可能真实存在**，v0.7 IPA 参考价值上调，但参考物暂不可得。
- **情报面扩容**：监控源在"官方 org + 主仓 forks + unixnu.com"之外，增加**中文短视频平台（抖音/B站/小红书）**为事件驱动源——此生态的发发布链 = 小圈子先发视频、代码后到（smzdm 11-03 出圈先于多数代码可见度，同构）。
- 待办：拿到抖音链接/作者账号后做 porter 定位（是 Helium-Studio 还是新面孔）+ 视频内容逐项核对（4G 注册状态栏？数据？通话？）。


## 勘误（2026-11-10 晚，阶段 30 实证纠正）

- §5.4 迁移 Top3 第 2 条的 nuwaPkg 表述**失实**：nuwaPkg = **小米 13 Pro / SM8550（kailua）**，**不是** Redmi K60 / SM8475（四处互证：DSC 注释 SOC_TYPE=SM8550-AB、KailuaPkg.dsc.inc、sm8550-xiaomi-nuwa.dtb、SMBIOS "13 Pro"）。价值从"同 SoC UEFI 备胎锚点"降级为"同生态工程模板"（DXE 全集含 UFS/显示/按钮/USB + 46 个 panel XML）。
