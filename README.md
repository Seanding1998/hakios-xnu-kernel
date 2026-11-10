# HakiOS on OnePlus Ace 2（PHK110）——设备移植分支

> **谱系**：本分支是 [oosexgang/hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel)（上游，参考设备 POCO X5 Pro / redwood）的**设备移植分支**，维护 **HakiOS on OnePlus Ace 2（PHK110 / SM8475）**。上游视角的 README 原样保留在 [README-UPSTREAM.md](README-UPSTREAM.md)；GitHub 的 "forked from" 徽章即谱系声明。

把 HakiOS——让 Apple 的 XNU 内核直接跑在安卓高通手机上的开源项目——移植到一加 Ace 2（PHK110，骁龙 8+ Gen 1 / SM8475，16 GB 内存）。上游的参考设备是 POCO X5 Pro（SM7325）；社区在 SM8475 上已有 K60（mondrian）、MIX Fold 2、POCO F5 Pro 等同 SoC 先例，本分支把上游扩展到 PHK110，是目前唯一持续维护的 PHK110 移植。所有改动只落在备用启动槽 `boot_b` 上（手机出厂有 A/B 两个 boot 槽：`boot_a` 跑日常安卓，`boot_b` 空置，本分支把它用作实验槽）；一次失败的实验会由 bootloader 自带的 A/B 回退机制自动退回安卓，`boot_a` 从未被刷写或修改。除首页 README 的呈现层替换（上游原 README 原样保留为 [README-UPSTREAM.md](README-UPSTREAM.md)）外，本分支不改上游任何已有文件，所有内容以新增形式存在（`devices/phk110/`、`docs/phk110/`、`waveNN-scripts/`、`logs/`）。

## 当前状态（2026-11-10，全部来自真机实测；"Boot #N" 是历次刷写启动的编号，全表见 [docs/phk110/STATUS.md](docs/phk110/STATUS.md)）

| 部件 | 状态 | 实测依据 |
|---|---|---|
| 显示 | ✅ 工作 | UEFI framebuffer 1240×2772，内核帧缓冲控制台滚动输出（Boot #7 起） |
| CPU | ✅ 工作 | 8 核全部上线，7 个应用核心 8 ms 内齐起（Boot #13/#14） |
| 按键 | ✅ 工作 | 电源 + 双音量键，经 PMIC 的 SPMI 总线读取（仲裁器版本 v7，上游驱动原本只认 v5），真机按键事件带毫秒时戳（Boot #16） |
| 触摸 | ◑ 驱动探针已通过 | Synaptics S3910 触摸控制器（TouchComm v1 协议）：读到部件号 "S3910PA0B0-15.2"、面板 1240×2772、报告配置读取完成（Boot #21）；真人点屏的事件流尚未记录 |
| 存储 | ✅ 工作 | UFS 129 个分区只读枚举 + darwin 数据卷可写；`/private/var` 内容跨启动保留，文件系统日志跨启动重放验证过（Boot #22–#24） |
| 用户态 | ✅ 工作 | 真 Apple launchd 以 pid 1 运行，28 个进程（含 SpringBoard、backboardd），Procursus 命令行前缀挂到 `/jb`（Boot #25） |
| USB 服务通道 | ✅ 工作 | loader 的 USB 命令服务可用（getvar / oem log / oem upload，216 KB 上传做过长度+内容双重校验）；此前的阻塞定位到 vendor USB 驱动的复位流程缺陷并修复（Boot #38） |
| SSH | ✅ 工作 | 经 loader 提供的 USB 网络通道（内核 `en0`，10.0.0.2/30）建立过 3 条独立 SSH 会话：root shell、256 KiB 校验传输、干净断开且 loader 仍存活（2026-11-10） |
| GPU | ❌ 未实现 | WindowServer / CoreAnimation 未启动（按路线排在 v0.5） |
| WiFi | ❌ 未实现 | ath11k 路线的检查与打包工具已备好（[wave30-scripts/](wave30-scripts/)），尚未上机 |
| /var 持久化复验 | ◑ 进行中 | 回归门已建，验证在跑（发布时点未出结论） |

## 快捷入口

| 想做什么 | 去哪 |
|---|---|
| **下载可刷写的启动镜像**（含适用机型、刷写步骤、风险说明） | **[Releases → v0.4-ssh-v23](https://github.com/Seanding1998/hakios-xnu-kernel/releases/tag/v0.4-ssh-v23)** |
| 5 分钟看懂整个项目（按主题分组的阶段日志索引） | [docs/phk110/READMAP.md](docs/phk110/READMAP.md) |
| 在同机（PHK110）上复跑验证（不刷写的操作优先） | [docs/phk110/REPRODUCE.md](docs/phk110/REPRODUCE.md) |
| 权威进度快照 | [docs/phk110/STATUS.md](docs/phk110/STATUS.md) |
| 与上游参考设备（redwood）的差异逐项说明 | [devices/phk110/PORT-NOTES.md](devices/phk110/PORT-NOTES.md) |
| 设备页（按上游设备页格式写，中文版在旁） | [devices/phk110/README.md](devices/phk110/README.md) / [README.zh.md](devices/phk110/README.zh.md) |

## 克隆之后能做什么 / 还不能做什么（诚实清单）

**能（clone 即得）**：

| 能做的事 | 依据 |
|---|---|
| 读全套移植文档，理解每一步怎么来的、为什么 | `docs/phk110/`（60+ 篇） |
| 在同机型或同类机型上复用主机侧工具与方法：loader USB 直连、相位探测、日志分区取证、不刷写的状态机循环、SSH 连接窗口控制 | `waveNN-scripts/`（脚本头部的工作区路径已脱敏为占位符，按 [REPRODUCE.md](docs/phk110/REPRODUCE.md) 的说明改写后可用） |
| 用 Release 里的启动镜像在 PHK110 上复现当前内核层状态 | 见 Release 说明的前置条件与刷写步骤 |
| 以本设备的配置与 SoC 参数为起点做自己的 SM8475 移植 | `devices/phk110/` |
| 读触摸驱动五个版本的源码快照和全部主机侧补丁脚本，理解每一步修复 | `wave12*-scripts/`、`wave21-scripts/` |

**不能（clone 得不到，如实告知）**：

| 得不到的东西 | 现状 |
|---|---|
| **内核 / UEFI / loader 的 PHK110 源码增量**（平台表、中断控制器扫描步进、S3910 驱动本体、按键 v7 适配、UFS 集成、`hw_target` 回退、loader 侧一系列补丁、en0 网络驱动等） | 这些改动目前在本地构建树里，本分支只有文档叙述、驱动源码快照和二进制补丁脚本，**不是可以直接 `git apply` 的补丁序列**。整理成可重建形式是后续工作；clone 之后从源码构建，目前**不能**得到同样的镜像 |
| 从源码重建所需的非公开输入 | UEFI 底座要从你自己的手机 XBL 提取（上游同样不分发）；Apple IPSW 与 ColorOS 固件自备 |
| 数据卷内容 | system.apfs / root.apfs 等由你自己的 IPSW 和工具生成（`devices/phk110/tools/` 是做法） |

**一句话**：这里发布的是**文档 + 方法 + 主机侧工具 + 一份验证过的启动镜像**；源码级"clone → build → 同样字节"还差补丁序列导出这一步，全部源码增量的清单见 [devices/phk110/PORT-NOTES.md](devices/phk110/PORT-NOTES.md) 第 7 节。

## 这个分支里有什么

| 目录 | 内容 |
|---|---|
| `devices/phk110/` | 设备配置、SoC 参数、设备页（中英）、移植笔记、数据卷工具（`tools/`） |
| `docs/phk110/` | 全套项目文档：进度快照 / 计划 / 阅读地图 / 复现指南 / 46 篇阶段日志 / 8 篇调研 / 4 篇评审记录 |
| `waveNN-scripts/` | 主机侧工具 25 组（loader 直连、SSH 连接窗口控制、日志分区拉取、镜像自检脚本、触摸驱动源码快照、WiFi 检查器等） |
| `logs/` | 内核日志关键行提取件（`*.keylines.txt`，对应日志分区二进制的文本证据） |
| **GitHub Release** | 已在真机上验证的启动镜像 `udon-hakios-grafted-v23.img`（192 MB，SHA256 `9e0609fb…`，绑定本分支 commit）——只在 Release 资产里，不进 git 树 |

**git 树里不含**：其他任何镜像或固件二进制（UEFI FD、payload、厂商固件、IPSW 衍生物）、任何私钥、任何分区备份。需要的原始材料（Apple IPSW、一加固件）请自备——本仓按上游口径不含它们。

## 诚实的未解清单

- `/var` 持久化的长程复验进行中（回归门已建，验证在跑）
- GPU / WindowServer 未启动（路线排在 v0.5，上游同样未到）
- WiFi / 蜂窝 / 音频 / 电池 / 振动 / 相机未实现（WiFi 工具先行）
- 真人点屏的事件驱动未验证（驱动探针已通过）
- 超过 1800 秒的长会话会触发一个早就存在的 vnode 表耗尽 panic——目前用会话时长上限绕开，根治需要改内核的 vnode 上限注入
- 内核 / loader 侧的移植补丁尚未整理成可以直接套用的补丁序列（当前以文档 + 源码快照 + 补丁脚本的形式在 `waveNN-scripts/`）

## 许可与致谢

本分支的内容按上游仓根 [`LICENSE`](LICENSE) 的口径发布：文档 / 脚本 / 设备层（即本分支的全部新增内容）为 MIT；上游内核侧保持 Apple Public Source License v2.0（`LICENSE.APSL`）。致谢：

- **[oosexgang/hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel)**（以及 hakios-metal / hakios-sm7325 / hakios-uefi）——一切工作的基座
- **takasugl/uefi-udon**（与 UniXNU-udon）——本机 UEFI 底座（udonPkg）的来源
- **OnePlusOSS**（`android_kernel_oneplus_sm8475`、`android_kernel_modules_and_devicetree_oneplus_sm8475`，GPL-2.0）——SM8475 设备树与驱动的研究参照；**本分支不再分发其任何文件**，SoC 参数等数值是从手机自带的设备树提取的
- **Mu-Silicium** 与 **HeliumStudio-Dev/hackios-xnu-kernel**（K20 Pro / SM8150 移植）——设备移植形态与 UEFI 构建方式的参考
- Apple 的 macOS / iOS 镜像（IPSW）不属于本仓也不由本仓分发，使用者自备自己的副本

## 出处与脱敏说明

本分支由私有工作区在 commit `1ed67796af8d10fb9c8da5b6d7c246c87c025854`（2026-11-10，"docs close-out before Wave 31"）的 `git archive` 快照整理而来，整理时做过一次脱敏：手机 serial、主机用户名/路径全部替换为 `SERIAL_REDACTED` / `<host>`；SSH 私钥与全部镜像固件二进制未入选（入选/排除准则即上文"这个分支里有什么"与其后的"不含"清单）。发布集内脚本头部的工作区路径也已是 `<host>` 占位，复跑前按本机布局改写。

---

上游（POCO X5 Pro / redwood / SM7325）的原始 README 未删改，保存在 [README-UPSTREAM.md](README-UPSTREAM.md)；上游其余内容（`docs/`、`devices/`、`tools/`、内核与 loader 源码树等）在本分支目录树中保持原位原样。
