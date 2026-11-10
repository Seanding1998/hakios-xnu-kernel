# 阅读地图（45 篇波告 + 12 篇调研/评审）

不想按时间顺序读 45 篇？按主题挑。每篇一行导读取自该报告自身标题（不美化）。
时间顺序与里程碑主线见 [STATUS.md](STATUS.md)，编年体见 [M0-PROGRESS.md](M0-PROGRESS.md)。

## A. 启动链：UEFI → loader → 内核第一口气（Wave 1–11）

| 篇 | 一句话 |
|---|---|
| [waves/wave1-hwmap.md](waves/wave1-hwmap.md) | PHK110 硬件清单 → redwood 驱动集映射规格书 |
| [waves/wave1-phk110pkg-spec.md](waves/wave1-phk110pkg-spec.md) | phk110Pkg（UEFI 平台包）逐文件适配方案 |
| [waves/wave1-socargs.md](waves/wave1-socargs.md) | SM8475 soc_* 启动参数补全 + 内存映射 + loader 窗口分析 |
| [waves/wave2-phk110pkg.md](waves/wave2-phk110pkg.md) | phk110Pkg 文件构造 |
| [waves/wave2-soclayer.md](waves/wave2-soclayer.md) | sm8475 SoC 层与 phk110 设备配置填充 + 配置系统验证 |
| [waves/wave2-uefienv.md](waves/wave2-uefienv.md) | Mu-Silicium UEFI 构建环境就绪报告（WSL Fedora） |
| [waves/wave3-integration.md](waves/wave3-integration.md) | UEFI 平台包 + 内核 + 打包链全通，boot.img 已产出 |
| [waves/wave3-research-external.md](waves/wave3-research-external.md) | 高通手机 `fastboot boot` 自定义 UEFI 外部案例研究 |
| [waves/wave4-udon-rebuild.md](waves/wave4-udon-rebuild.md) | uefi-udon (udonPkg) full rebuild + boot_v4 打包 + graft |
| [waves/wave5-udon-hakios.md](waves/wave5-udon-hakios.md) | HakiOS payload grafted into the udonPkg UEFI base |
| [waves/wave6-platform-phk110.md](waves/wave6-platform-phk110.md) | loader 平台表 `platform_phk110` + 完整镜像重建 |
| [waves/wave7-usbmode.md](waves/wave7-usbmode.md) | USB-mode grafted boot image（XnuLoaderMain graft） |
| [waves/wave7b-klogdump.md](waves/wave7b-klogdump.md) | 内核日志落盘缺口修复 |
| [waves/wave8-usb-start-fix.md](waves/wave8-usb-start-fix.md) | loader `usb_start()` PHK110 失败根因 + usbmode 驻留镜像 v3 |
| [waves/wave9-interrupt-controller.md](waves/wave9-interrupt-controller.md) | 中断控制器（GIC）根因修复 |
| [waves/wave10-post-gic-abort.md](waves/wave10-post-gic-abort.md) | GICR 扫描步进修复 → v0.1 达成（内核跑进用户态） |
| [waves/wave11-resident.md](waves/wave11-resident.md) | XNU 真机 60 s 常驻 + 8 核全上线 |

## B. 输入：触摸（S3910 TouchComm）与按键（Wave 12 系）

| 篇 | 一句话 |
|---|---|
| [waves/wave12-touch-buttons.md](waves/wave12-touch-buttons.md) | S3910 TCM 驱动 + 电源/音量键 + 300 s 常驻 + 8 核同起 |
| [waves/wave12a-touch-probe.md](waves/wave12a-touch-probe.md) | v10 首刷：probe 未达，但两大新事实寄存器级定性 |
| [waves/wave12b-probe-verdict.md](waves/wave12b-probe-verdict.md) | v10b 一行修复首刷：软件链全通，断点移到芯片电气层 |
| [waves/wave12c-electrical.md](waves/wave12c-electrical.md) | 三刷攻坚：**probe PASS**——"电气故障"误诊翻案全记录 |
| [research/research-tcm-miso.md](research/research-tcm-miso.md) | S3910 TouchComm over SPI 外部先例与已知坑调研 |

## C. 主机侧工具与 USB 通道（Wave 13 起，贯穿到 Wave 27）

| 篇 | 一句话 |
|---|---|
| [waves/wave13-usb-host.md](waves/wave13-usb-host.md) | Windows 主机直连 loader USB gadget 工具链（免刷写迭代铺路） |
| [waves/wave21-net-design.md](waves/wave21-net-design.md) | loader 桥接网络（SSH 数据面）设计预稿 |
| [waves/wave21-ssh-e2e.md](waves/wave21-ssh-e2e.md) | loader 桥接网络 → en0 上机；SSH 未通，v0.4 推迟 |
| [waves/wave21_1-ssh-verdict.md](waves/wave21_1-ssh-verdict.md) | USB 服务器修复轮 + 在线判据达成 |
| [waves/wave21_2-ssh-catch.md](waves/wave21_2-ssh-catch.md) | 加固 + host 管道守护 + E2E 抓取（含 F10 冻屏判案） |
| [waves/wave21_3-coldboot.md](waves/wave21_3-coldboot.md) | 冷启动判据试验（取证轮反转 + 转述判伪教训） |
| [waves/wave21_5-probe-verdict.md](waves/wave21_5-probe-verdict.md) | bulk 探针 + 重掷修复：阻塞上游化为"主机可见性" |
| [waves/wave22-host-visibility.md](waves/wave22-host-visibility.md) | 泵送前移 + 自主 present：主机首次看见我们 |
| [waves/wave24-exp1-design.md](waves/wave24-exp1-design.md) | Exp-1 诊断刷写设计（端点未配置根因分辨） |
| [waves/wave24-exp1-diagnostic.md](waves/wave24-exp1-diagnostic.md) | 判决表落槌：H4 复位流程缺陷；USB serving 打通 |
| [waves/wave25-ssh-e2e.md](waves/wave25-ssh-e2e.md) | SSH E2E（零刷写战） |
| [waves/wave26-k1-fix.md](waves/wave26-k1-fix.md) | K1 修复 + maxvnodes + SSH 时间窗 |
| [waves/wave27-phaseB-wide-window.md](waves/wave27-phaseB-wide-window.md) | 宽窗 SSH 续战（零刷写）：**WAVE21-SSH-OK 判定落槌** |
| [waves/wave28-var-persistence.md](waves/wave28-var-persistence.md) | /var 持久回归门 + 可重复步骤归档（零刷写） |
| [research/f12-ep2-not-configured.md](research/f12-ep2-not-configured.md) | bulk 端点 "endpoint[2] not configured" 深挖 |

## D. 存储：UFS 与数据卷（Wave 15–18）

| 篇 | 一句话 |
|---|---|
| [waves/wave15-ufs-research.md](waves/wave15-ufs-research.md) | UFS 驱动实施级设计（纯调研，零刷写） |
| [waves/wave16-ufs-s0s2.md](waves/wave16-ufs-s0s2.md) | UFS 存储栈 S0-S2 只读验证（零行内核改动） |
| [waves/wave16b-p0-prep.md](waves/wave16b-p0-prep.md) | darwin carve 工具 PHK110 化（只勘察、零刷写） |
| [waves/wave16c-p0-exec.md](waves/wave16c-p0-exec.md) | P0 执行收官：darwin 分区 + 数据卷就位（全 adb、零 fastboot） |
| [waves/wave18-s3s8.md](waves/wave18-s3s8.md) | S3-S8 开写 + 真实 init 链换装收官（launchd 首次接管） |

## E. 用户态与身份链（Wave 14 / 19 / 20）

| 篇 | 一句话 |
|---|---|
| [waves/wave14-sysimage-prep.md](waves/wave14-sysimage-prep.md) | v0.4 用户空间前置：20F66 IPSW 解包、盘点、就绪化（含 SSH bootstrap） |
| [waves/wave19-prep.md](waves/wave19-prep.md) | SSH 数据面 + 真实 launchd 系统卷两大开放问题预研 |
| [waves/wave20-launchd.md](waves/wave20-launchd.md) | launchd 存活 + /jb 接线（hw_target EINVAL 破案，28 进程） |
| [docs root: wave17-ssh-bootstrap.md](../wave17-ssh-bootstrap.md) | SSH 引导链机制备忘（sshd/密钥/libiosexec 细节） |

## F. 显示与取证（Wave 23）

| 篇 | 一句话 |
|---|---|
| [waves/wave23-virtual-display.md](waves/wave23-virtual-display.md) | 虚拟显示出画取证（屏录链内核侧工作） |
| [research/f13-virtual-display.md](research/f13-virtual-display.md) | 无 GPU 先见 iOS 桌面预研 |

## G. WiFi 工具先行（Wave 30，未上机）

| 篇 | 一句话 |
|---|---|
| [waves/wave30-ath11k-tooling-prep.md](waves/wave30-ath11k-tooling-prep.md) | ath11k 工具链前置（零手机案头波） |

## H. 调研与评审（research/ + review/）

| 篇 | 一句话 |
|---|---|
| [research/f10-dxe-abort-solutions.md](research/f10-dxe-abort-solutions.md) | DXE 期 Data Abort 外部先例 + 修复模式库 |
| [research/f14-sd778g-zendot-survey.md](research/f14-sd778g-zendot-survey.md) | zendot 文章考古 + SM7325 驱动全景 + 物料清单预研 |
| [research/f15-raphael-k20pro-survey.md](research/f15-raphael-k20pro-survey.md) | 红米 K20 Pro（raphael）移植传闻核实 + 迁移评估 |
| [research/landscape-2026-11-08.md](research/landscape-2026-11-08.md) | 生态审计：同类项目普查 + 进度基线 |
| [research/consulting-2026-11-03.md](research/consulting-2026-11-03.md) | 外援咨询记录（逐条裁决） |
| [review/gpt-review-2026-11-09.md](review/gpt-review-2026-11-09.md) 等四篇 | 外部评审报告（方法论/文档/结论复核） |

## 术语小词典

| 术语 | 含义 |
|---|---|
| **波次（Wave NN）** | 本项目的执行单元：一个分析→构建→（如需）刷写→取证的闭环，产出一份波告 |
| **Boot #NN** | 真机刷写/引导会话的全局序号（Boot #1 = 2026-10 首次 ABL 拒镜像，#39 系 = SSH 判定） |
| **F 编号（F1…F14）** | 过程中发现的现象编号（F6 = vnode 表耗尽 panic；F10 = PAYLOAD_BASE 冻屏；F12 = bulk 端点未配置；…） |
| **H 编号（H1…H4）** | 针对同一阻塞的竞争假说编号（H4 = 复位流程缺陷，Wave 24 落槌为根因） |
| **S0–S8** | 存储验收阶梯（S0 只读枚举 → S8 数据卷物理写证），沿用上游口径 |
| **v0.1 / v0.3 / v0.4** | 里程碑：v0.1 = 内核跑进用户态并干净返回；v0.3 = 常驻/8 核/按键/触摸 probe 四项；v0.4 = 存储 + launchd + SSH（2026-11-10 达成） |
| **N1/N2/N3** | SSH 判定的三道门（枚举在线/会话可服务/E2E shell） |
| **taro / cape / Udon** | 高通 SM8475 平台代号 / 一加板级代号（FDT 名）/ 本机 UEFI 底座代号（uefi-udon） |
| **redwood / yupik** | 上游参考机 POCO X5 Pro 的板级代号 / 其 SoC（SM7325）代号 |
| **graft** | 把 HakiOS payload（内核/loader/ramdisk）嫁接进 udonPkg UEFI 底座产出 boot 镜像的工艺 |
| **payload / loader.efi** | UEFI 菜单里被 XnuLoader 加载执行的那一包 / 其中的 EFI loader |
| **logdump** | 内核/loader 日志落盘分区（512 MB，LBA 0 整分区覆盖写）；每轮 boot 后从安卓侧拉回 |
| **keylines** | 从 logdump 二进制提取的关键行文本（`*.keylines.txt`） |
| **兜底回安卓 / march** | A/B fallback：会话异常后 bootloader 自动回 slot a 安卓；march = 用 adb/fastboot 把手机按状态机送回 slot b 循环的零刷写操作 |
| **保存窗 / serving 窗** | 会话结束（`loader_return_after` 到期）后脏数据回写的时间窗 / loader USB 命令服务器在场的可服务时间窗 |
| **set_active a/b** | fastboot 切换 A/B 活动槽位（回安卓 = a，进实验 = b） |
| **probe** | 判定用只读探测（触摸 probe / USB bulk 探针 / `probe-phase-v27.py` 相位探测） |
| **零刷写** | 不动 boot_b 分区的纯主机侧/adb 侧操作（march、logdump 拉取、SSH hunt） |
