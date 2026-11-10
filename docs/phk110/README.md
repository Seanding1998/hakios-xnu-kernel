# HakiOS → PHK110 移植文档索引

**项目**：把 HakiOS（Apple XNU 跑在安卓高通手机上，上游 github.com/oosexgang）移植到一加 Ace 2（PHK110 / SM8475 / 16GB / ColorOS 16）。
**启动链**：`ABL → boot_b（Mu-Silicium UEFI + AVB footer 嫁接）→ BootShim → XnuLoader → XNU 内核 → Darwin`
**操作边界**：`boot_a`（日常安卓）从不刷写；`boot_b` 的刷写与验证是本项目的实验循环，可由 A/B 回退恢复；破坏性操作单独确认。
**路径约定**：阶段日志在 `waves/`，独立调研在 `research/`，文中引用一律 repo 根相对路径。

## 阅读顺序

1. **[STATUS.md](STATUS.md)** — 当前状态快照（续接工作先读）
2. **[PLAN.md](PLAN.md)** — 版本计划 v0.1→v1.0
3. **[READMAP.md](READMAP.md)** — 按主题分组的阅读地图
4. **本页** — 文档目录
5. **[M0-PROGRESS.md](M0-PROGRESS.md)** — 逐日记录（M0 情报期 → Boot #6，细节查找用）

## 版本里程碑（截至 2026-11-10）

| 版本 | 状态 | 达成点 |
|---|---|---|
| v0.1 黑盒启动链 | ✅ Boot #12 | UEFI→loader→内核→用户态全链 + 26KB 日志取证 |
| v0.2 第一帧显示 | ✅ | udon 底座原生 NT37705 显示栈顺带达成 |
| v0.3 触感 | ✅ Boot #21 | 常驻 300 s / 8 核 / 按键 / S3910 触摸探针 |
| iOS 桌面上屏 | ✅ 2026-11-09 | SpringBoard 渲染上屏（屏幕目视 + logdump 双源：MiniIOMFB 111 行/swap 20 次/backboardd 544/SpringBoard 1249）；CPU 渲染（卡顿符合"无 GPU"预期），MiniIOMFB+MiniIOSurface 假驱动链路全部实证 |
| **SSH 进 Darwin shell** | **✅ 2026-11-10** | **WAVE21-SSH-OK + v0.4 SSH 门通过**（`verdict27-20261110-060630.txt`）：3 条独立 SSH 连接（uname Darwin 22.5.0 / uid=0 root / 各异随机标记 rc=0）+ 256KiB 校验传输 + 退出后管理通道 OKAY + boot_b=v23 绑定 |
| v0.4 达尔文 | 🔄 只差 /var 复验门 | S0-S8 ✅ + 数据卷 ✅ + launchd 28 进程/sshd :22 ✅（Boot #25）+ USB 服务通道打通（Boot #38，复位流程缺陷修复）+ SSH 数据面全通 + 1800s 会话上限端到端实证；**剩余 = /var 重启持久复验 + 可重复步骤归档（阶段 28 进行中）** |
| v0.5 GPU | ⏳ 计划 | freedreno 主路线；呈现通道已就绪（无 GPU 显示路线 = 桌面出画已实证） |

## 阶段日志（`waves/`，45 篇；`wave17-ssh-bootstrap.md` 在 docs 根）

"Boot #N" 是历次刷写启动的编号。按主题找文件请看 [READMAP.md](READMAP.md)。

| 文件 | 内容 | Boot |
|---|---|---|
| wave1-hwmap | 硬件驱动映射 + GPL 源渠道 | — |
| wave1-phk110pkg-spec | 平台包规格 + redwood 5 补丁记录（DALSYSDxe UFS coherence 在列） | — |
| wave1-socargs | SM8475 启动参数表 + 内存映射 | — |
| wave2-phk110pkg | phk110Pkg 构造 | — |
| wave2-soclayer | sm8475 层 + 内核编译 | — |
| wave2-uefienv | UEFI 构建环境 + ingres 验证 | — |
| wave3-integration | boot 镜像集成打包 | — |
| wave3-research-external | 外部案例调研（发现 uefi-udon） | — |
| wave4-udon-rebuild | udonPkg 重建（senna_bc 填充） | #6 UEFI 点亮 |
| wave5-udon-hakios | HakiOS 融合 | #7 内核日志上屏 |
| wave6-platform-phk110 | platform_phk110 平台表 | #8 干净返回 |
| wave7-usbmode | AfterConsole 挂点 + USB 驻留 | #9 gadget 枚举 |
| wave7b-klogdump | 内核日志落盘修复 | #10 内核日志取证 |
| wave8-usb-start-fix | usb_start 时序重试修复 | （并入后续镜像） |
| wave9-interrupt-controller | GIC 地址修复（SoC 参数抄错） | #11 映射打通 |
| wave10-post-gic-abort | GIC 重分配器步进修复 | #12 **v0.1** |
| wave11-resident | 驻留 stub + 8 核 | #13 **常驻+8核** |
| wave12-touch-buttons | S3910 驱动 + SPMI v7 按键 | #14-16 **按键达成** |
| wave12a-touch-probe | GENI 探活 + 双阻塞定位 | #17 |
| wave12b-probe-verdict | bitbang 链闭环 | #18 |
| wave12c-electrical | 电气三轮 + 分帧节拍规律（探针通过） | #19-21 **触摸达成** |
| wave13-usb-host | loader_talk.py 直连工具 + 两个主机侧问题定位 | — |
| wave14-sysimage-prep | 20F66 sysimage 解包 + SSH 路线 | — |
| wave15-ufs-research | UFS 预研 + S0-S8 任务单 | — |
| wave16-ufs-s0s2 | UFS 栈点亮 | #22 **S0-S2** |
| wave16b-p0-prep | 数据卷工具 + dry-run + 备份 | — |
| wave16c-p0-exec | 数据卷执行完成（全 adb 通道） | #22+ darwin 12G HFS+ 落盘 |
| wave17（在 docs 根） | Procursus SSH bootstrap 物料 | — |
| wave18-s3s8 | 存储闭环（v12/v13）+ launchd pid 1 | #23-24 **S3-S8** |
| wave19-prep | v0.4 两大开放问题（SSH 数据面方案 A + 换根机制） | — |
| wave20-launchd | launchd 存活 + /jb 接线 | #25 **v0.4 用户态全绿** |
| wave21-net-design | loader 桥接网络设计稿 | — |
| wave21-ssh-e2e | loader 桥接四刷（v15.x，en0 实证） | #26-29 |
| wave21_1-ssh-verdict | USB 服务通道在线判据 | #30 |
| wave21_2-ssh-catch | 构建回归定位（PAYLOAD_BASE）+ 端点墙 + v16c | #31-33 |
| wave21_3-coldboot | 冷启动对照实验（陈旧字节误读的纠正） | #32 |
| wave21_5-probe-verdict | 探针机制两轮（v17/v17b）+ 阻塞点移到主机侧 | #34-35 |
| wave22-host-visibility | 泵送前移+主动上拉（v18）：bulk 首次武装 | #36 |
| wave23-virtual-display | 无 GPU 出画取证（v19 屏录版）+ cmdline 实际上限 | #37 |
| wave24-exp1-design | USB 端点诊断刷写设计稿 | — |
| wave24-exp1-diagnostic | 诊断结论：复位流程缺陷，错误墙零复现 | #38 **USB 通道打通** |
| wave25-ssh-e2e | SSH 端到端（零刷写）：闭环到 sshd 横幅 + 9 缺陷修复 | — |
| wave26-k1-fix | 180s 会话帽结论 + 三轮 v21/v22/v23 + 桌面出画取证 | #39+ |
| wave27-phaseB-wide-window | **宽窗 SSH 验证完成：WAVE21-SSH-OK**；八项主机侧修复（MSS≈160B 环上限/推序死锁/相位占空比/ACL）+ 代际钟 | **3 SSH 连接 + 256KiB 校验传输** |
| wave28-var-persistence | /var 持久复验（结论未出，如实记录）：工具四件全交付 + loader 半启动新发现（bulk 无响应 165min，~3h15m 自发解体）+ 固定 240s 服务窗机制 | 结论 pending |
| wave30-ath11k-tooling-prep | WiFi 工具链前置（不需要手机）：`mk-ath11k.py` 骨架 + 5 个检查器 + 上游缺口清单 | — |

## 调研（`research/`）

| 文件 | 内容 |
|---|---|
| consulting-2026-11-03 | 外部咨询 5 问定稿（IPSW 锁 20F66 / DEVELOPMENT≠安全关 / HFS+ /var / freedreno 主路线 / Windows 情报），逐条对照 upstream 核验 |
| research-tcm-miso | TouchComm 电气三次误诊的纠正 + vendor 逐项核验表 + 根因排序（直接促成 Boot #21 探针通过） |
| landscape-2026-11-08 | 生态盘点 + EINVAL 源头定位（identity.h 占位版）+ 13 项生态普查 |
| f10-dxe-abort-solutions | DXE Data Abort 外部调研（0xF0000000 普查 + 修复模式 6 式；真因见 wave21_2 §7 照片定案） |
| f12-ep2-not-configured | bulk 端点墙指令级归因（DwcPrepareURB/Walk + 三重前置 + 修复单） |
| f13-virtual-display | 无 GPU 先见 iOS 桌面路线（Mini 驱动已在树 + ios-sweet 考古 + 23.x 任务单） |
| f14-sd778g-zendot-survey | SD778G 同代驱动对照 + zendot 文章考古（固件提取工作流 + IPA 版本证伪 + PHK110 物料清单） |
| f15-raphael-k20pro-survey | K20 Pro 进展核实：GPU GLES 证实有边界 / WiFi 部分证实带已知 bug / 4G 证伪；PHK110 迁移建议 |

## 外部评审记录

- **[review/gpt-review-2026-11-09.md](review/gpt-review-2026-11-09.md)** — 外部审阅导读：阅读路径、代码行号地图、未决问题清单
- **[review/gpt-review-report-2026-11-09.md](review/gpt-review-report-2026-11-09.md)** — 外部审阅第一轮（USB 核心：根因排序、缺陷清单、实验阶梯）
- **[review/gpt-review-report-2-2026-11-09.md](review/gpt-review-report-2-2026-11-09.md)** — 外部审阅第二轮（USB 错误墙屏摄定案 + 六项取证指令）
- **[review/gpt-review-report-3-2026-11-09.md](review/gpt-review-report-3-2026-11-09.md)** — 外部审阅第三轮

## 外部关键参考

- **takasugl/uefi-udon + UniXNU-udon**：PHK110（udon）同款机的完整实现；`docs/BRINGUP-2026-10-25.md` 方法论极有参考价值（含 **SM8475 UFS SMMU 操作 external abort 实测**——"不碰 SMMU"的同机证据）
- **OnePlusOSS** sm8475 双仓（PHK110 同源，clone SHA 见 `upstream-manifest.txt`）：内核仓 + modules/devicetree 仓（触摸 dtsi / cape-pinctrl / vendor touchpanel 驱动）
- **Project-Silicium / Mu-Silicium**：UEFI 底座上游；Binaries/Device-Binaries（senna_bc 等）
- 上游 HakiOS：oosexgang/hakios-xnu-kernel（redwood 参考设备：GPU GL=1 / HFS+ /var 均实机达成）

## 本机环境备忘

- WSL 发行版 **FedoraLinux-44**（fastboot 必须 `--user root`）；手机 fastboot = usbipd attach（18d1:d00d，busid 历史值 2-2，**USB 重枚举后必须重新 attach**）
- 网络代理 `http://127.0.0.1:7897`；Git Bash 下 adb pull 需 `MSYS_NO_PATHCONV=1`
- 取证链：logdump 分区 dd → `MSYS_NO_PATHCONV=1 adb pull` → python 提取 `== KERNEL LOG ==`
- 构建树：WSL `~/hakios/{kernel, uefi-udon, sysimage-20F66, ipsw, refs, procursus-prep}`；Windows 仓 `device-layer/`（镜像产物）+ `waveNN-scripts/`（各阶段工具）
- 应答方鉴别：`fastboot getvar product` 答 `taro` = ABL（可刷）；loader 服务器答 xnuloader 风格（免刷写通道，见 wave13）
