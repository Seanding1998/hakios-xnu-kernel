# HakiOS → PHK110 移植项目文档索引

**项目**：把 HakiOS（Apple XNU on 安卓高通手机，上游 github.com/oosexgang）移植到一加 Ace 2（PHK110 / SM8475 Cape / 16GB / ColorOS 16）。
**启动链**：`ABL → boot_b(Mu-Silicium UEFI + AVB footer graft) → BootShim → XnuLoader → XNU 内核 → Darwin`
**安全红线**：boot_a（日常安卓）绝对禁刷；boot_b 刷写+验证循环 = 一揽子授权（2026-11-03）；P0（userdata carve）已获用户批准（2026-11-03），其余破坏性操作逐次批准。
**路径约定**：波次报告在 `docs/waves/`，独立调研在 `docs/research/`，文中引用一律 repo 根相对路径。

## 阅读顺序

1. **[STATUS.md](STATUS.md)** — 当前状态唯一权威快照（每次续接先读）
2. **[PLAN.md](PLAN.md)** — 版本计划 v0.1→v1.0（v0.1/v0.2/v0.3 已达成段内含达成记录）
3. **本页** — 文档目录
4. **[M0-PROGRESS.md](M0-PROGRESS.md)** — 编年体全记录（M0 情报 → Boot #6，细节查找用）

## 版本里程碑（截至 2026-11-10 晨）

| 版本 | 状态 | 达成点 |
|---|---|---|
| v0.1 黑匣子 | ✅ Boot #12 | UEFI→loader→内核→用户态全链 + 26KB 日志取证 |
| v0.2 第一缕光 | ✅ | udon 底座原生 NT37705 显示栈顺带达成 |
| v0.3 触感 | ✅ Boot #21 | 常驻 300 s / 8 核 / 按键 / S3910 TCM probe |
| 🌟 iOS 桌面真机出画 | ✅ 2026-11-09 | SpringBoard 渲染上屏（用户目视 + logdump 双源：MiniIOMFB 111 行/swap 20 次/backboardd 544/SpringBoard 1249，b25 基线数倍）；CPU 渲染（卡 = 无 GPU 预期），MiniIOMFB+MiniIOSurface 内核假驱动链路全部实证 |
| **🏆 SSH 进 Darwin shell** | **✅ 2026-11-10** | **WAVE21-SSH-OK + v0.4 SSH 门 PASS**（`verdict27-20261110-060630.txt`）：3 独立 SSH 连接（uname Darwin 22.5.0 / uid=0 root / 各异随机标记 rc=0）+ 256KiB 校验传输 + 退出后管理通道 OKAY + boot_b=v23 绑定 |
| v0.4 达尔文 | 🔄 只差 /var 项目门 | S0-S8 ✅ + P0 ✅ + launchd 28 进程/sshd :22 ✅（Boot #25）+ USB serving 打通（Boot #38 H4 修复）+ SSH 数据面全通（TCP/KEX/auth/exec/256KiB 传输 ✅）+ v23 1800s 会话帽端到端实证；**剩余 = /var 重启持久复验 + 可重复步骤归档（Wave 28 进行中）→ 达标即宣告** |
| v0.5 GPU | ⏳ 计划 | freedreno 主路线；呈现通道已就绪（F13 虚拟显示路线 = 桌面出画已实证） |

## 波次报告（`docs/waves/`，45 篇；`docs/wave17-ssh-bootstrap.md` 为早期放错位置的 wave17 报告）

| 文件 | 一句话 | 真机 |
|---|---|---|
| wave1-hwmap | 硬件驱动映射 + GPL 源渠道（UFS 首判 works） | — |
| wave1-phk110pkg-spec | 平台包规格 + redwood 5 补丁记录（DALSYSDxe UFS coherence 在列） | — |
| wave1-socargs | soc_args 补全 + 内存映射 | — |
| wave2-phk110pkg | phk110Pkg 构造 | — |
| wave2-soclayer | sm8475 层 + 内核编译 | — |
| wave2-uefienv | UEFI 构建环境 + ingres 验证 | — |
| wave3-integration | bootimg 集成打包 | — |
| wave3-research-external | 外部案例（发现 uefi-udon 金矿） | — |
| wave4-udon-rebuild | udonPkg 重建（senna_bc 填充） | #6 UEFI 点亮 |
| wave5-udon-hakios | HakiOS 融合 | #7 内核上屏 |
| wave6-platform-phk110 | platform_phk110 平台表 | #8 干净返回 |
| wave7-usbmode | AfterConsole 挂点 + USB 驻留 | #9 gadget 枚举 |
| wave7b-klogdump | klog→logdump 落盘修复 | #10 内核日志取证 |
| wave8-usb-start-fix | usb_start 时序重试修复 | （并入后续镜像） |
| wave9-interrupt-controller | GIC 地址案（抄错 SoC） | #11 映射打通 |
| wave10-post-gic-abort | GICR stride 修复 | #12 **v0.1** |
| wave11-resident | 驻留 stub + 8 核 | #13 **常驻+8核** |
| wave12-touch-buttons | S3910 驱动 + SPMI v7 按键 | #14-16 **按键达成** |
| wave12a-touch-probe | GENI 探活 + 双阻塞定位 | #17 |
| wave12b-probe-verdict | bitbang 链闭环 | #18 |
| wave12c-electrical | 电气三轮 + 分帧节拍破案 | #19-21 **触摸达成** |
| wave13-usb-host | loader_talk.py 直连工具 + 双破案（hrdevmon/usbipd） | — |
| wave14-sysimage-prep | 20F66 sysimage 解包 + SSH 路线 | — |
| wave15-ufs-research | UFS 预研 + S0-S8 施工单 | — |
| wave16-ufs-s0s2 | UFS 栈点亮 | #22 **S0-S2** |
| wave16b-p0-prep | P0 carve 工具 + dry-run + 备份 | — |
| wave16c-p0-exec | P0 执行收官（全 adb 通道） | #22+ darwin 12G HFS+ 落盘 |
| wave17（在 docs/ 根） | Procursus SSH bootstrap 物料 | — |
| wave18-s3s8 | 存储闭环两刷（v12/v13）+ launchd 接管 pid 1 | #23-24 **S3-S8** |
| wave19-prep | v0.4 两大开放问题（SSH 数据面方案 A + 换根机制） | — |
| wave20-launchd | launchd 存活 + /jb 接线 | #25 **v0.4 用户态全绿** |
| wave21-net-design | loader 桥接网络设计预稿 | — |
| wave21-ssh-e2e | loader 桥接四刷（v15.x，en0 实证） | #26-29 |
| wave21_1-ssh-verdict | USB 服务器在线判据 + F8/F9 | #30 |
| wave21_2-ssh-catch | F10 构建回归破案 + 端点墙 + v16c | #31-33 |
| wave21_3-coldboot | 冷启动判据试验（陈旧字节误读翻案） | #32 |
| wave21_5-probe-verdict | 探针机制两轮（v17/v17b）+ 阻塞上游化 | #34-35 |
| wave22-host-visibility | 泵送前移+自主 present（v18）：两历史首胜 | #36 **bulk 首次武装** |
| wave23-virtual-display | 无 GPU 出画取证（v19 屏录版 + 提取协议修复）+ cmdline 真实预算发现 | #37 |
| wave24-exp1-design | Exp-1 诊断刷写设计预稿（主代理合并外部审阅） | — |
| wave24-exp1-diagnostic | Exp-1 判决表落槌：根因 H4 复位流程缺陷，墙零复现 | #38 **USB serving 打通** |
| wave25-ssh-e2e | SSH E2E 零刷写：闭环到 sshd 横幅 + 9 缺陷修复 | — |
| wave26-k1-fix | K1 定案（180s 会话帽非 bug）+ 三轮 v21/v22/v23 + 桌面出画取证 + Runbook | #39+ **桌面出画/1800s 实证** |
| wave27-phaseB-wide-window | **宽窗 SSH 收官：WAVE21-SSH-OK + v0.4 SSH 门 PASS**；八项主机侧修复（MSS≈160B 环上限/推序死锁/相位占空比/ACL）+ 代际钟 + 六分支台账 | **🏆 3 SSH 连接 + 256KiB 校验传输** |
| wave28-var-persistence | /var 持久判定波（判定未到手如实入档）：工具四件全交付单测过 + **loader 僵尸态新发现**（bulk 聋 165min，~3h15m 自发解体）+ 固定 240s 服务窗机制（loader.c:5617，修正 wave27 保存窗模型）；round 2 被用户叫停收编 | 判定 pending |
| wave30-ath11k-tooling-prep | WiFi 工具链前置（零手机案头波）：fork 固定源码管线精读 + `mk-ath11k.py` 骨架真跑到源码就绪（SHA 锁+许可门 22/22）+ 5 个 check-phk110-wifi 门 + 上游缺口补丁清单（pci id/mhi config）+ nuwaPkg 情报修正（实为小米 13 Pro/SM8550） | — |

## 调研报告（`docs/research/`）

| 文件 | 一句话 |
|---|---|
| consulting-2026-11-03 | 外援 5 问定稿（IPSW 锁 20F66 / DEVELOPMENT≠安全关 / HFS+ /var / freedreno 主路线 / Windows 情报），全部 upstream 逐字核验 |
| research-tcm-miso | TCM 电气三误诊翻案 + vendor 逐项核验表 + 根因排序（直接促成 Boot #21 PASS） |
| landscape-2026-11-08 | 生态审计 + EINVAL 源头定位（identity.h 占位版）+ 13 项生态普查 + Top3 借鉴 |
| f10-dxe-abort-solutions | F10 外部调研（0xF0000000 普查 + 修复模式 6 式；真因见 wave21_2 §7 照片裁决） |
| f12-ep2-not-configured | **bulk 端点墙指令级归因**（DwcPrepareURB/Walk/三重前置 + H1-H3 + 修复单） |
| f13-virtual-display | **无 GPU 先见 iOS 桌面路线**（Mini 驱动已在树 + ios-sweet 考古 + 23.x 施工单 + 战略翻转） |
| f14-sd778g-zendot-survey | SD778G 同代驱动对照 + zendot 文章考古（拉固件工作流 + IPA 版本证伪 + PHK110 物料清单） |
| f15-raphael-k20pro-survey | **K20 Pro 进展核实 = 社区 fork 半真半假**（GPU GLES 证实有边界 / WiFi 部分证实带已知 bug / **4G 证伪**；F14 口径盲区 = fork 网络；PHK110 迁移 Top3 + nuwaPkg 备胎锚点） |

## 审阅导读（外部 AI 审阅入口）

- **[review/gpt-review-2026-11-09.md](review/gpt-review-2026-11-09.md)** — 给外部 AI（ChatGPT 等）的审阅导读：阅读路径、代码行号地图、未决问题清单、v19 施工单
- **[review/gpt-review-report-2026-11-09.md](review/gpt-review-report-2026-11-09.md)** — 外部审阅报告第一轮（USB 核心审阅：H1>H2>H3 排序、P1 缺陷清单、实验阶梯）
- **[review/gpt-review-report-2-2026-11-09.md](review/gpt-review-report-2-2026-11-09.md)** — 外部审阅第二轮（USB 错误墙屏摄裁决：F12 尾部实锤 + 刷屏源定位 + 六项取证指令）

## 外部关键参考

- **takasugl/uefi-udon + UniXNU-udon**：PHK110（udon）同款机完整实现；`docs/BRINGUP-2026-10-25.md` 方法论金矿（含 **SM8475 UFS SMMU 操作 external abort 实测**——"不碰 SMMU"的同机铁证）
- **OnePlusOSS** sm8475 双仓（PHK110 同源，clone SHA 见 `upstream-manifest.txt`）：内核仓 + modules/devicetree 仓（触摸 dtsi / cape-pinctrl / vendor touchpanel 驱动）
- **Project-Silicium / Mu-Silicium**：UEFI 底座上游；Binaries/Device-Binaries（senna_bc 等）
- 上游 HakiOS：oosexgang/hakios-xnu-kernel（redwood 参考机：GPU GL=1 / HFS+ /var 均实机达成）

## 本机环境备忘

- WSL 发行版 **FedoraLinux-44**（fastboot 必须 `--user root`）；手机 fastboot = usbipd attach（18d1:d00d，busid 历史值 2-2，**USB 重枚举后必须重新 attach**）
- 网络代理 `http://127.0.0.1:7897`；Git Bash 下 adb pull 需 `MSYS_NO_PATHCONV=1`
- 取证链：logdump 分区 dd → `MSYS_NO_PATHCONV=1 adb pull` → python 提取 `== KERNEL LOG ==`（存档 `intel/m3-boot1/`）
- 构建树：WSL `~/hakios/{kernel, uefi-udon, sysimage-20F66, ipsw, refs, procursus-prep}`；Windows 仓 `device-layer/`（镜像产物）+ `wave*-scripts/`（各波工具）
- 应答方鉴别：`fastboot getvar product` 答 `taro` = ABL（可刷）；loader 服务器答 xnuloader 风格（免刷写通道，见 wave13）
