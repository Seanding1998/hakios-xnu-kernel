# HakiOS → PHK110（一加 Ace 2 / SM8475 "Cape"）移植项目 · 总体规划

> 版本：1.1（2026-11-10：吸收 F14/F15/Wave 30 情报——WCN6750 口径勘误、IPA v5.1 勘误、MHI GPL 工作项、情报节奏入协议）· 维护者：ZCode 主代理（orchestrator）
> 技术基线事实见 `M0-PROGRESS.md`，本文件只管"怎么走、谁来做、何时算完成"

---

## 1. 愿景与范围

**目标**：在一加 Ace 2（PHK110，骁龙 8+ Gen 1 / SM8475 / BL 已解锁）上，把 HakiOS 从"POCO X5 Pro 专属研究平台"扩展为可日常使用的第二系统（`fastboot boot` RAM 启动，不碰分区，重启回 ColorOS）。

**终点定义（v1.0）**：功能状态等效于上游 `docs/devices/redwood.md` 设备页 —— 显示/触摸/按钮/8 核/GPU(OpenGL ES)/Wi-Fi/存储(/var 持久化)/音频/电池/振动/热管理可用，蜂窝半通，蓝牙缺失步一。

**明确不做**：刷写任何分区、替代 ColorOS 的日常系统、Apple 服务、绕过任何厂商安全机制。

## 2. 技术基线（已验证事实，详细见 M0-PROGRESS.md）

| 事实 | 值 |
|---|---|
| BL | orange（真解锁，getprop 伪装），`fastboot boot` 可用 |
| CPU | 3×A510 + 4×A710 + 1×X2(cpu7)，`CONFIG_BOOTCPU=7`；**16GB SKU**（15.78GiB RAM，ddr-regions: 2GB + 6GB@0x800000000 + 8GB@0x980000000） |
| soc.args | **16/16 已补全**（Wave1-A）：soc_cmd_db=0x80860000、soc_mpss_mem=0x8bc00000、modem_ipa_fw_at=0x8b910000、soc_pas_mpss=4（待真机验证） |
| xbl | **加密**（OPPO sec-boot），厂商 DXE 不可本地提取 |
| UEFI 模板 | **`Platforms/Realme/ingresPkg`（Poco F4 GT = SM8475 同硅，上游状态全✅）+ `Binaries/ingres`（9.3MB）**。⚠️ 修正：早前误判 bitraPkg——bitra 是 GT Neo 2/SM8250(Kona)，不可用 |
| 面板/触摸 | NT37705 / Synaptics S3910(TCM v2 over SPI)。**一加官方 GPL 源码已找到**（OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475，branch sm8475_v_15.0.0_ace_2）：panel dtsi 全序列 4077 行已存 `intel/wave1b-scripts/`；S3910 驱动源码同仓库 |
| 内存风险 | **payload 固定地址 0xF0000000 在 Cape 上是 RAM 缺口**（0xF0000000-0xF13FFFFF 非 RAM）→ v0.1 必须把 BootShim.S/XnuLoader.h 的 XNU_PAYLOAD_BASE 改为有效 RAM 地址（设备级覆盖机制，见 wave1-phk110pkg-spec §4）；loader 6GB 窗口 0x840000000-0xA40000000 无需改动 |
| 构建链 | WSL Fedora44（mirrored 网络）+ theos + clang22；内核已编译成功；qemu-open 全链路验收通过 |
| 调试通道 | 无串口 → **盲启 + logfs/logdump 分区回读**（UEFI 常驻 logfs 服务；分区已确认存在） |

## 3. 版本计划（每个版本 = 可验证的交付物 + 明确验收标准）

### v0.1 「黑匣子」— UEFI 盲启上机 ✅ **达成（2026-11-03，Boot #12）**
- **内容**：phk110Pkg（基于 bitraPkg 改造）→ SILICIUM_UEFI.fd → mkxnuimg 打 bootimg → `fastboot boot` 真机盲启 → logfs 回读 UEFI 日志
- **验收**：①手机不变砖、重启回 ColorOS；②logfs 日志含 HakiOS UEFI banner；③内存映射初始化成功（含 12GB 识别，loader 6GB 上限问题在此验证）；④CPU/时钟/PMIC DXE 全部 Dispatch 成功
- **依赖**：Wave1（调查）→ Wave2（构造）→ Wave3（构建+QEMU 验证）→ Wave4（上机，需用户逐次批准）
- **🎯 实际达成（远超原始验收线，路线经 udon 底座转向）**：Boot #6 UEFI 点亮 → Boot #8 内核干净返回 → Boot #10 内核日志取证（717B）→ Boot #11 GIC 映射打通 → **Boot #12：GIC v3 初始化 + Darwin 22.5.0 横幅 + 8 驱动 + BSD + md0 + 多核调度 + 用户态 "Hello from user space on Darwin!"（= M1 QEMU 验收级）**，26KB 内核日志全量落盘，panic（initproc/launchd 缺席 = v0.4 边界）后干净返回、ABL 自动兜底回安卓，零变砖。技术终态：boot_b 槽 + AVB graft + udonPkg + Wave7 自动挂点 + logdump 取证闭环

### v0.2 「第一缕光」— 显示点亮 ✅ **达成（2026-11-03，随 udon 底座顺带达成）**
- **内容**：NT37705 面板让 DisplayDxe 出画（原计划三条路线：①OnePlus GPL panel init 序列→RAW 配置；②bitra DisplayDxe 试验；③Mu-Silicium 开源显示路径）
- **验收**：屏幕可见 HakiOS logo；XNU banner 上屏
- **🎯 实际达成（路线转向红利）**：udonPkg 底座自带本机原生显示栈——厂商 DisplayDxe（含 NT37705 init）+ splash fb @0xB8000000 1240×2772 32bpp。Boot #6 UniXNU 菜单出画（用户拍照实证）→ Boot #7/8 XNU banner + 内核日志上屏滚动 → Boot #12 同链验证。GPL panel init 序列副本（intel/wave1b-scripts/）保留作后续内核态显示驱动（v0.5+ GPU 路线）参考

### v0.3 「触感」— XNU 真机常驻 + 输入（**进行中，前半已达成 2026-11-03 Boot #13**）
- **内容**：XNU 上机常驻运行；**新写 Synaptics S3910 触摸驱动**（参照 drivers/*/hakios.goodix 骨架 + Linux synaptics_tcm 协议）；电源/音量键（PMIC）；8 核全开
- **验收**：8 核在线（bootcpu=7）、屏幕触摸可点、电源键响应
- **🎯 全部达成（2026-11-03，Boot #13→#21 三波）**：✅ XNU 常驻（stub launchd + 300s 长会话零 panic）；✅ 8 核全开（`small_cores_after=0` 同起，7 AP 8ms 内上线）；✅ 电源/音量键（SPMI v7 仲裁器适配，**真人按键毫秒级取证**）；✅ S3910 触摸（Boot #21：`TouchComm v1 firmware: mode 0x1, S3910PA0B0-15.2` + `touch screen ready`，probe 链 identify→app-info→config→enable 全通，max x/y 与 1240×2772 面板吻合；攻坚三刷 v10c→d→e，root cause = 续读分帧 9B/CS 帧 + 20ms 重武装节拍）。**已知边界**：坐标流（真人点屏上报）待下一次会话验证——驱动已 ready，boot-arg 可选触发

### v0.4 「达尔文」— 用户空间可用（**方案定稿 2026-11-03，外援咨询 + upstream 验证**）
- **🎯 实际进展（2026-11-10 晨，详 docs/STATUS.md 更新㉖）**：存储六步 S0-S8 ✅（Boot #22-24）+ P0 carve 12G HFS+ ✅ + **Apple launchd 真身 28 进程全跑（Boot #25，hw_target EINVAL 双修复）** + **iOS 桌面真机出画（2026-11-09，用户目视 + logdump 双源）** + USB serving 打通（H4 = 复位流程缺陷已修，v20 后墙零复现）+ **🏆 SSH 进 Darwin shell 达成（2026-11-10，Wave 27：3 独立连接 uname Darwin/uid=0 root/各异标记 rc=0 + 256KiB 校验传输 + 退出后管理通道 OKAY，verdict27-20261110-060630.txt）** + v23 1800s 会话帽端到端实证；**验收剩余 = /var 重启持久复验 + 可重复步骤归档（Wave 28 进行中），达标即宣告 v0.4**。技术史注：SSH 曾被三个主机侧确定性协议缺陷阻塞（ARP 字段写反/握手 ACK 序号差一/跨端口 RST 误杀，外部审阅定位）+ MSS≈160B 环上限（wave21 ping 只验过 100B）——全部主机侧修复，零刷写达成。原"深水区 UFS+SMMU"被 Wave15 预研削平（vendor UFSDxe 沿用 + 只读/有界写路径，R1 数据面 FNV 清白）。
- **物料矩阵（锁定，不得混装）**：IPSW = `iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw`（iPhone X / A11 / **arm64** 切片，禁碰 arm64e——CPU_SUBTYPE 不同 + shared cache AUTH 区需 PAC，本机 PAC 未验证）；dyld = 同 IPSW 的 `dyld_shared_cache_arm64`（不重建、不拆 loose dylib）；trust/identity/SystemOS 全取同一 20F66 set。**upstream qemu.md 用的正是这一份**（已核验）。
- **安全策略（⚠ 关键认知修正）**：DEVELOPMENT ≠ 安全机制自动关闭——`config_enforce_signed_code` 仍在 KERNEL_BASE，AMFI/MACF/Sandbox 照常编译。v0.4 显式处理：`cs_enforcement_disable=1` boot-arg（DEVELOPMENT 非 SECURE_KERNEL 可用）+ HakiOS 式最小 policy stub（miniamfi/kern_minimac 类，upstream 同版本实测可行）；stock 信任链（AMFI/trust cache）后置到 fidelity 阶段。
- **存储（深水区大幅削平）**：`/private/var` = Apple OSS **HFS+（hfs-627.100.6）编进内核**，UFS 上独立 journaled HFS+ 分区——**upstream 已实机完成**（12GB journaled、重启保留、Sileo/Procursus/SSH 可用，CHANGELOG 已核验）。APFS 持久 Data 后置 v0.6+；linux-apfs-rw 移植与自写 FS 均不进主线（无先例）。分层：UFS transport → IOBlockStorageDevice → IOBlockStorageDriver → IOMedia → GPT scheme → VFS。分步：S0 UFS 控制器 init → S1 READ CAPACITY → S2 GPT → S3 有界读写回读 → S4 cache flush/FUA/顺序 → S5 IOMedia 发布 → S6 HFS+ 挂载 → S7 /private/var → S8 重启持久测试。**真正深水区 = UFS + SMMU/DMA + write ordering**。
- **验收**：launchd（真身）→ sshd → SSH 进 Darwin shell；重启后 /var 内容保留。
- **依赖**：用户提供 20F66 IPSW（约 7.4GB+，ipsw.me 或 Apple 官方渠道均可）。
- 参考：UniXNU-udon（takasugl，本机同款 udon）已走通 native UFS → iPadOS 用户空间（117 进程）——路径先例强度高。

### v0.5 「图形」— GPU（Adreno 730 / a7xx）（**路线裁决 2026-11-03**）
- **主路线（低风险，upstream 已实机证明）**：跟随 upstream 架构——hakios.adreno.c 内核 GPU 驱动的 a6xx→a7xx 适配 + Mesa freedreno 对接。**upstream CHANGELOG 已核验：Mesa 25.0.7 freedreno，GL=1 流畅绘制、壁纸上屏（参考机实机 GPU 渲染达成）**。我们的工作 = 驱动适配 + Mesa 版本跟进（freedreno 已有 a7xx 支持）。**F15 佐证（2026-11-10）**：第三方 raphael fork（SD855 / Adreno 640）freedreno GLES 3.2 真机绘制达成 = freedreno-on-XNU 第三台机先例，主路线信心上调（同时其 Metal 缺席佐证 Metal 移植非平凡，维持 upstream"metal 先行 buffers/libraries"策略）。
- **前置物料（F14 Top3 勘定，2026-11-09；详情 docs/research/f14-sd778g-zendot-survey.md）**：①**pull-firmware-root.sh 模板化 = v0.5 开工第一步**（从我们安卓拉 GPU/WiFi/音频固件：Magisk root + vfat fmask=0337 root 暂存法，上游同族实测 837 文件 313MB/10.7s）；②选择性版本落差同步（gpu.cpp +4KB / fb_beam sc7280 门控陷阱 / metal.args 范式）；③工具先例 = Wave 30 已把固定源码管线范式跑通（`wave30-scripts/mk-ath11k.py` 源码就绪，03310d7）。PHK110 固件物料清单已勘定：a730_zap.mbn 主线同族在案（GPU 侧固件仅 ~137KB 级）。
- **实验备选（外援建议，待实测）**：最小 KGSL 兼容 ABI → Turnip-KGSL → Vulkan → Zink → GL。Mesa 官方立场：freedreno Gallium 不支持 KGSL，KGSL 系统应用 Zink+Turnip。**止损条件**：若 KGSL shim 开始大量模拟 dma-buf/sync_file/Linux fd 语义 → 停止兼容，改走 `tu_knl_darwin.cc` 原生 IOKit UserClient 路线（UniXNU 在 Nothing Phone 2/SM8475 已证）。已知无第三个项目证明"原版 Turnip-KGSL 在 Darwin ABI 下无修改运行"。
- **Metal**：buffers/libraries 先行（对齐 hakios-metal 现状）。
- **验收**：OpenGL ES 应用渲染；桌面可交互帧率。
- 分步（若走备选路线）：G0 电源/GMU/SMMU+单命令流 → G1 最小 KGSL ABI → G2 Vulkan 烟测 → G3 Zink/GL → G4 WSI/IOSurface/显示集成。

### v0.6 「连接」— Wi-Fi + 音频
- **内容**：Wi-Fi = **WCN6750 hw1.0**（⚠ Wave 30 勘误 2026-11-10：主线 ath11k **无 QCA6490 hw_rev**，勿按 qca6490 形态开工；固件目录 `WCN6750/hw1.0/`、IPCR 通道 20/21 复用 qca6390 表）走 PCIe/MHI——redwood 的 WPSS PIL 路线作废；ath11k_pci 补 **2 个一行级补丁**（pci.c 设备 ID 表 + mhi.c hw_rev case；`check-phk110-wifi-mhi.py` 自动检测缺口）；**GPL 边界（新增工作项）：drivers/bus/mhi = GPL-2.0 不可链 → MHI 协议须在 wifi/lx 层自实现**（raphael fork lx_bus.c 手写总线先例在证；ath11k 本体 BSD/ISC 可链，Wave 30 许可门 22/22 已验）；工具链已就位 = Wave 30（mk-ath11k.py 固定源码管线源码就绪 + check-phk110-wifi-{dtb,fw,mhi,wlfw,e2e} 五门，03310d7；施工单 docs/waves/wave30-ath11k-tooling-prep.md）；音频：TFA9874×2 扬声器（非 redwood 的 AW88261/TDM），经 ADSP TERT_MI2S
- **验收**：加入 Wi-Fi 热点；播放声音

### v0.7 「全网」— 蜂窝（IPA v5.1）
- **内容**：PHK110 IPA = **v5.1**（⚠ F14 勘误 2026-11-09：wave1 的"IPA 4.5 / hw-ver 0x16"**证伪**——SM8450 IPA v5.1 自述 "Verified on SM8475 with modem working"；我们内核 `hakios.ipa.c` 硬编码 redwood 的 4.11 待移植；主线 `ipa_data-v5.1.c` 系列可参照，代际比 redwood 新，风险维持下调）；modem 驱动适配（注意 MPSS_MEMORY_SIZE 246MB 常量 < Cape 306MB 预留，需放开）。**外部参考现状（F15）**：公网零 raphael 蜂窝参考（fork 自认 `cellular missing`）；**抖音视频疑似 SM8150 私人蜂窝构建先行**（用户信源 2026-11-10，porter 定位中）——若坐实则 SM8150 蜂窝先例存在，事件驱动跟进
- **验收**：SIM 绑定 + 数据注册（语音通话不做入版）

### v1.0 「日常」— 等效 redwood + 稳定
- **内容**：电池电量显示、热管理（thermal stop 生效）、充电部分、双启动体验打磨（tools/modem-cycle-win.sh 式 Windows 一键脚本）
- **验收**：对照 docs/devices/redwood.md 状态表逐项等效

### v0.8+ 「双系统」— 持久共存（用户明确关心的方向，2026-11-02 补入）
- **上游已有完整设计**（docs/dual-boot.md + u-boot.md）：U-Boot 进 `boot_a` 每次开机出菜单；`darwin` 分区（20GiB，从 userdata 尾部切）放系统卷 + HFS+ 数据卷；Android 走 slot b 不动；配套工具链齐全（backup-partitions.py / userdata-carve.py / sparse-split.py / mkdatavol.py / hakios-install.img）
- **PHK110 移植 = 同一套工具 + 我们的 phk110Pkg + U-Boot 设备文件**（u-boot 路线 redwood 已验证）
- **性质变更警告**：从"零刷写"变"真刷写"——需备份分区表、抹 userdata 数据、替换 boot_a。OPPO 特有风险：ColorOS OTA 会覆盖 boot_a/校验失败、反回滚、UFS 分区表手术风险。**每一步刷写必须用户逐次批准 + 全分区备份先行**。排期：仅在 v0.4（RAM 版 Darwin 稳定）之后启动
- **验收**：开机菜单双选；安卓 OTA 前能一键恢复原 boot；数据卷跨启动保留

### v1.x 「三系统」（可选远期路线，需单独立项）（**情报更新 2026-11-03 外援咨询**）
- **Windows on ARM**：我们正在建的 phk110Pkg（Mu-Silicium）本身就是 Project Silicium 给 SM8450/8475 手机装 Windows ARM 的同一底座。三系统 = 同一个 UEFI 底座 + ESP 放 Windows 引导 + UEFI 菜单/BootNext 变量选择（用户提到的 K20 三系统架构同源：Renegade/Silicium 系 UEFI 常驻 boot 分区，Windows 默认，脚本/面具模块设下次引导项）
- **SM8475 可行性已证实**：Mu-Silicium Status 表 Nothing Phone 2（pong，同代 8+ Gen 1）Windows Boot ✅（CPU/存储/fb/USB Host 工作，但 GPU/触摸/WiFi/BT/电池/音频全 ❌）、Galaxy Z Flip 4（b4q）✅。**⚠ 但 Ace 2/udon 本机无公开 Windows entry**；同族 senna_bc 显示 Display/Storage ✅ 而 Windows Boot ❌——"UEFI 起来"≠"Windows 起来"。
- **当前裁决**：只保留"Mu-Silicium boot experiment"一项实验位；**不排 Windows 驱动 wave**（Adreno WDDM 是巨坑），直到 udon 实机进 Windows PE。xbl 签名链在已能 Mu-Silicium 启动后不再是长期瓶颈。
- **前置**：v0.8 双系统稳定 + Windows ARM64 镜像与许可问题（社区惯例自备镜像）+ Windows 侧驱动工作量另行评估
- **现状**：暂只登记方向，不排期；HakiOS 侧工作（WS-A~F）完全复用，无浪费

> 版本串规则沿用上游：`2.1.13-hakios-darwin22.5-sc7280-g<hash>` → 我们的构建会带 `sm8475`。

## 4. 工作流分解（WS）与依赖

```
WS-A UEFI 固件线    bitraPkg→phk110Pkg→.fd→bootimg→盲启     → v0.1, v0.2
WS-B 内核 SoC 线    sm8475 层填充→真机内核启动               → v0.1(日志), v0.3
WS-C 驱动线         S3910 触摸/面板序列/haptic/buttons       → v0.2, v0.3
WS-D 用户空间线     IPSW→sysimage→SSH→/var                  → v0.4
WS-E GPU 线         a7xx 内核侧 + Mesa                       → v0.5
WS-F 连接线         WiFi→音频→IPA v5                         → v0.6, v0.7
```
依赖：WS-A/WS-B 并行起步；WS-C 依赖 WS-A 的显示框架与 WS-B 的驱动骨架；WS-D 可与 WS-C 并行（不碰真机）；WS-E 在 v0.3 稳定后启动；WS-F 最后。

## 5. 子代理编排协议（用户已授权）

**角色分工**：
- **主代理（我）**：规划、派发、集成、验收、风险决策、所有涉及真机的高危操作、用户沟通。不直接写批量代码。
- **Explore 代理**：只读调查（代码考古、文档梳理），产出结论报告。
- **general-purpose 代理**：按工作流分派实现任务，每代理独占一个文件域（避免同树写冲突），产出 = 代码/配置 + 验证证据 + 报告（`docs/waves/waveN-*.md`）。

**波次计划**：
| 波次 | 任务 | 代理 | 状态 |
|---|---|---|---|
| **Wave 1**（调查，3 并行）✅ 完成 2026-11-02 | A: soc_args 16/16 补全 + 16GB 内存映射 + loader 0xF0000000 缺口发现 | general-purpose | 报告 docs/waves/wave1-socargs.md |
| | B: 硬件映射全表 + GPL 源码渠道闭环（R1/R2 解除）+ WiFi/IPA 架构修正 | general-purpose | 报告 docs/waves/wave1-hwmap.md |
| | C: 模板改判 ingresPkg + phk110Pkg 逐文件规格 + Binaries 策略 | general-purpose | 报告 docs/waves/wave1-phk110pkg-spec.md |
| **Wave 2**（实现，3 并行） | D: phk110Pkg 文件构造（按 C 规格 §9）/ E: sm8475 层+设备配置填充（按 A 数据）/ F: UEFI 构建环境（子模块+依赖） | general-purpose ×3 | 本轮启动 |
| **Wave 3**（集成） | bootimg 打包 + QEMU 验证 UEFI FD + v0.1 上机清单 | 主代理亲自 | Wave2 验收后 |
| **Wave 4+** | 按 WS-C/D/E 推进 v0.2-v0.5 | 按需 | 版本门驱动 |

**代理纪律**：
- 允许：WSL 构建、仓库文件读写、adb root **只读**（getprop/cat/ls/dd→/data/local/tmp）
- 禁止（对手机）：reboot、fastboot、flash、写分区、改系统文件、动服务 —— 违者任务作废
- 所有真机 fastboot boot 由主代理亲自执行，且每次先获用户同意

## 6. 风险登记册

| # | 风险 | 影响 | 概率 | 缓解 |
|---|---|---|---|---|
| R1 | NT37705 面板 init 序列获取（在内核 panel 驱动里，不在 DTB） | v0.2 卡住 | 中 | **OnePlus GPL 内核源码**（官方 releases 含 PHK110，panel driver 全序）；Oplus 同系（bitra 已有 OplusProject.inf 说明序列结构相近） |
| R2 | S3910 触摸驱动从零写 | v0.3 延期 | 高 | Linux synaptics_tcm 主流协议参考 + goodix 骨架；v0.3 前 v0.2 已可无触摸验证内核 |
| R3 | IPA v5 移植量 | v0.7 卡住 | 高 | 排期最后；上游 redwood 蜂窝也仅 partial；先做"半通"目标 |
| R4 | a7xx GPU 工作量 | v0.5 延期 | 中高 | Mesa freedreno 已有 a7xx 基础支持（23+），比 a6xx→a7xx 全新实现乐观 |
| R5 | bitra DXE 与 Oplus 板型差异（PlatformInfo/ProjectInfo 读 SMEM 板 ID 不符） | v0.1 阻塞 | 中 | phk110Pkg 配置层覆盖 + 逐驱动 patch（redwood Binaries README 已有 5 个同类 patch 先例） |
| R6 | 12GB 内存 vs loader 6GB 单窗口上限 | v0.1 阻塞 | 低 | v0.1 首验；必要时改 xnuloader 多窗口/提高上限（loader.c:27 已知位置） |
| R7 | 手机是主力机，测试窗口受限 | 全程摩擦 | 确定 | 测试全部 RAM-only + 用户逐次批准；构建/分析全部离机进行 |

## 7. 验证与安全协议

1. 每个版本门 = 可重复的验收命令 + 日志证据存 `docs/vX.Y-evidence/`
2. 真机操作前：确认 adb 在线 → 执行 → 重启回安卓 → **用户手动解锁** → logfs 回读 → 存档
3. 一切手机内提取物放 `intel/`（git 外），源码改动放 WSL 工作树，逐波同步回工作区 `device-layer/`
4. 主代理每次会话开始读 `M0-PROGRESS.md` + 本文件对齐状态
5. **生态情报节奏（F15 后新设，2026-11-10）**：每周双扫（上游官方 org + 主仓 forks?sort=newest）+ unixnu.com 双周 + **中文短视频平台（抖音/B站）事件驱动**——F14 教训 = 只扫官方 org 漏掉整个 fork 网络/私人构建层；调研报告间相互勘误直接改源头文件头部（F14/F15 勘误先例）

## 8. 会话预算（tokens 不设限，但按波次设验收闸）

- Wave1 ≈ 3 并行调查代理，产出 3 份规格书
- Wave2 ≈ 3 并行实现代理 + 集成验收
- 每个版本目标 2-4 波完成；R1/R3/R4 是长杆，允许跨多波
