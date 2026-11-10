# 外部评审意见（2026-11-09）

> 给有本地文件阅读能力的 AI（ChatGPT 等）的审阅入口。本文只做导航与提问，所有细节都在所引文件里。
> 项目语言：中文（代码注释/日志为英文）。仓库根：`<host>\.zcode\workspace\9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7\hakios-phk110`（下称 `[REPO]`）。
> 构建树在 WSL FedoraLinux-44：`/home/<host>/hakios/`（下称 `[WSL]`，Windows 侧可用 `\\wsl.localhost\FedoraLinux-44\home\<host>\...` 直读）。

## 0. 一段话项目背景

把 **HakiOS**（github.com/oosexgang：Apple XNU 内核直接跑在安卓高通手机上）从唯一参考机 POCO X5 Pro 5G 移植到 **一加 Ace 2（PHK110 / SM8475 / 16GB）**。启动链 = `ABL → boot_b(Mu-Silicium UEFI + AVB graft) → BootShim → XnuLoader(loader.efi) → XNU 内核 → Darwin 用户态(20F66 IPSW)`。boot_b 刷写循环为一揽子授权的非破坏性双系统研究平台（slot a 安卓日常不动）。方法论 = 分析编排与阶段执行分离，一切结论以真机实测为准；36 次 boot 的全记录在 `[REPO]/docs/STATUS.md`（唯一权威快照）。

## 1. 当前位置（一页纸）

| 里程碑 | 状态 | 证据 |
|---|---|---|
| v0.1 全链启动 | ✅ Boot #12 | wave10 |
| v0.2 显示 | ✅ | wave4-6（udon 原生面板栈） |
| v0.3 触摸/按键/常驻/8核 | ✅ Boot #21 | wave11-12c |
| v0.4 存储（UFS S0-S8 + P0 carve + HFS+ /var） | ✅ Boot #22-24 | wave15-18, 16b/16c |
| v0.4 用户态（launchd 28 进程 / sshd :22 / SpringBoard） | ✅ Boot #25 (v14) | wave20 |
| **v0.4 完成 = 主机↔loader 的 USB 管道（SSH 数据面）** | **🔄 唯一剩余，本文重点** | wave19/21/21_1/21_2/21_5/22 |
| iOS 桌面出画（无 GPU CPU 渲染路线） | 🔄 阶段 23.x 进行中 | docs/research/f13 + wave23-scripts/ |
| v0.5 GPU（freedreno） | ⏳ | PLAN.md；呈现通道依赖上行的出画 |

**核心矛盾一句话**：loader 相位的 USB gadget，主机（Windows）大多数时候枚举不出来（死 devnode `0000:0002`），少数时候枚举成功且 bulk 端点对武装成功（v15 以来首次在 Boot #36 证据）；SSH 数据面需要一个**持续可用**的管道，所以"武装成功率"是 v0.4 的最后一道墙。

## 2. 阻塞问题五分钟版（编年）

按时间顺序，每一步都有完整阶段日志（`[REPO]/docs/waves/`）：

1. **Boot #9 遗案**：vendor `UsbConfigDxe start_ex` 间歇失败（~9/10 boot，wave7/wave8）。
2. **wave19-prep**：SSH 数据面方案定稿 = loader 桥接网络（共享页网环 + 内核 en0 + loader bulk 管道复用，零内核 USB 栈）。
3. **wave21（v15.x, Boot #26-29）**：三端全真机验证，en0 数据面实证（内核态 10.0.0.2/30 配置成功）；阻塞 = start_ex 间歇失败 + F7 usbipd stale export。
4. **wave21_1（v16, Boot #30）**：延迟首试 + 失败码打印 → `usb: started` 首试即成；新发现 **F8**（半启动 zombie：ep0 可枚举但 bulk 未武装）与 **F9**（usbipd→WSL vhci 管道生命周期）。
5. **wave21_2（v16b/v16c, Boot #31-33）**：**F10** 构建回归定位根因（PAYLOAD_BASE 漏带 → 冻屏，照片+反汇编定案）；v16b' 修复后新形态 = **端点墙**（`physical endpoint[2] not configured` / `0x8000000C` 持续刷屏）；三重 DWC3 唤醒修复无效 → 定性 vendor 栈固有行为。
6. **wave21_4 → docs/research/f12-ep2-not-configured.md**：端点墙**指令级归因**（vendor UsbfnDwc3Dxe 反汇编）：bulk 武装唯一路径 = host SET_CONFIG → ep0 状态机 case 9 → DEPSTARTCFG → 描述符 walk → DwcConfigureEP；三重前置 = speed 字段（仅 ConnectDone 写非 0）+ maxpkt 速度表（**bulk@speed0=0 陷阱列**）+ DEPSTARTCFG 成功。根因三候选 **H1/H2/H3**（见 §5）。
7. **wave21_5（v17/v17b, Boot #34-35）**：探针机制（0 长度 bulk 探针 + 判别器 + 重掷）两轮完整执行；主机全程未枚举 → 阻塞**上游化**为"主机可见性"。
8. **wave22（v18, Boot #36）**：根因定案到指令级（vendor 唯一拉高 pull-up 的 connect 只被泵送盲窗的平台回调驱动；我们自己的 start_ex 开头会断开 connect 且从不重新展示）→ 修复 = **泵送前移（usb_wait_pumped，20ms 节拍）+ 自主 present（usb_present：start_ex 成功后 DCTL|=bit31）**。真机：**两项历史首胜**（loader 相位枚举成功 6 分钟 + logdump 判别器逐字 `the bulk pair answered: armed at generation 0, beat 1`）。**剩余阻塞精确化**（§5）+ v19 施工单（§6）。
9. **wave23-scripts（v19, 2026-11-09 凌晨，运行中）**：cmdline-only（loader_return_after 180→300 + rec 屏录参数，见 `wave23-scripts/make-cmdline-v19.py` 有个重要的 **cmdline 预算发现**：loader 会加 110 字符头，真实余量 26 字符）；提取通道 = **Windows 侧 libusb 直连**（`wave22-scripts/probe18w.py` 骨架，open+claim 实证成功——旧"Windows libusb 全盲"判词作废）。

## 3. 术语表

| 术语 | 含义 |
|---|---|
| logdump | 专用分区，loader 在会话结束时把日志落盘（write_logs 从 LBA 0 整分区覆盖）→ 手机回安卓后 dd 出来取证 |
| `0x8000000C` | vendor DwcPrepareURB 的墙码（bulk EP 状态字节为 0 = 未武装） |
| `0x8000000B` | 同族错误码（UsbConfigDxe 译码器 @.text 0x11038 的另一分支，语义未定案） |
| `0x8000000000000007`（7 形） | UsbDeviceSend 把墙码包装成 EFI_DEVICE_ERROR 后 loader 看到的形态 |
| F6/F7/F8/F9/F10 | 项目内发现编号：vnode 表耗尽 / usbipd stale export / 半启动 zombie / usbipd→WSL vhci 管道生命周期 / PAYLOAD_BASE 构建回归 |
| H1/H2/H3 | SET_CONFIG walk 失败三候选（见 §5） |
| present/pull-up | DWC3 DCTL.RUN_STOP（bit31）：拉高 = 设备上总线（attach） |
| 泵送 (pump) | 调 vendor `handle_event` 派发 USB 事件环（ep0 SETUP/ConnectDone 等只在泵送时前进） |
| serving 窗 | 主机管道可用的时段（usbipd attach 完成 + 设备枚举 + bulk 武装三者对齐） |
| 死 devnode `0000:0002` | Windows 枚举中途失败留下的坏设备节点（"描述符请求失败"），不重试 |

## 4. 推荐阅读路径

**只想审 USB 阻塞问题（约 60-90 分钟）**：
1. `docs/STATUS.md` 的 Boot 表 #26-36 行 + "下一步队列"（15 分钟版全景）
2. `docs/waves/wave22-host-visibility.md`（**最新判定 + 结构性根因 + v19 施工单**，本审阅的主对象）
3. `docs/research/f12-ep2-not-configured.md`（vendor 反汇编指令级事实表）
4. 代码：`[WSL]/kernel/xnuloader/loader.c` 的 USB 段（行号地图见 §4.1）+ `[REPO]/wave22-scripts/patch-loader-v18.py`（v18 delta 全文，含设计动机注释）
5. 真机数据：`[REPO]/logdump-v18.bin.keylines.txt`（armed 会话判别记录）+ `wave22-scripts/bus18-watch.log`（Windows 总线观测）+ `wave23-scripts/fetch23.log`（**最新反常数据**，见 §5-D）

**想审全项目**：加读 `docs/PLAN.md`（版本计划）、`docs/M0-PROGRESS.md`（编年体）、`docs/README.md`（37 篇阶段日志目录）、`docs/research/f13-virtual-display.md`（并行线）、`docs/research/landscape-2026-11-08.md`（生态对比）。

### 4.1 loader.c USB 段行号地图（[WSL]/kernel/xnuloader/loader.c，共 5129 行）

| 行 | 内容 |
|---|---|
| 3912-3955 | usb_connected / 事件类型 / 静态状态 |
| 4017-4070 | `usb_wait_pumped()`（v18 泵送前移 helper） |
| 4063-4095 | `usb_present()`（v18 自主 present：DCTL 0x0A60C704 \|= bit31） |
| 4097-4131 | `usb_start_attempt()`（init kick → locate_protocol → 描述符注册 → start_ex → susphy_off → present） |
| 4133-4300 | `usb_start()`（25s settle 窗 → 3 tries → **探针循环**：6 拍/代际 × 3 代际、判别器、重掷、终判） |
| 4300-4360 | usb_wait（传输等待 + run_active 3s 上限） |
| 4749-4800 | `usb_poll_command()`（内核运行期的命令服务，每 pass 泵一次 handle_event） |
| 2236, 2650-2670 | block_poll / 主 watch 循环（内核运行期 core 0 常驻） |

## 5. 未决问题清单（请审阅者重点看）

**A. 设备侧 walk 失败三候选（F12 命名，至今未分辨）**
- **H1**：DEPSTARTCFG/描述符 walk 本身翻车（与 start_ex 间歇失败同族）
- **H2**：SET_CONFIG 到达时 speed 字段仍为 0 → maxpkt 速度表 bulk@speed0=0 陷阱 → 端点武装失败
- **H3**：UsbDeviceDxe 层 "Unknown USB Speed" STALL（speed==0 时 SET_CONFIG 被拒）
- 分辨手段受限：raw 失败码被 UsbDeviceSend 包装成 7 形（logdump 看不到 raw）；vendor 的**前导错误行只上屏不进 logdump**（屏摄是唯一活通道）。v19 Round 2 计划加 raw 码透传。

**B. 结构异常窗（2026-11-09 审码发现，未修复）**
每个 boot 的最初 25s settle 窗：`usb_init_kick` 唤起的 vendor 平台回调会在该窗内拉高 pull-up（wave22 §1 指令级证实），而该窗**按设计不能泵送**（start_ex 未配置事件环，ring 不属于 loader）→ 主机第一眼看到的 attach 注定 5s 控制超时 → 死 devnode。每个 boot 都先送 Windows 一个坏枚举。缓解候选：settle 25s→5s（v16 的 5s 版有"首试即成"实证）。

**C. 重掷 detach 杀枚举（wave22 首要嫌疑）**
armed 会话恰是零重掷会话（gen0 直接武装）；重掷的 start_ex 开头断开 connect = 真 detach，可能把刚建好的 Windows 枚举赶成死节点。v19 施工单第一项 = 软化重掷（代际内见主机事件不重掷）。

**D. 最新反常数据（2026-11-09 00:59-01:02，`wave23-scripts/fetch23.log`）**
一个会话里设备被 Windows **稳定枚举 2.5 分钟**（open+claim 每 10s 成功、libusb_set_configuration(1) 已发），但 **bulk-OUT 全部 LIBUSB_ERROR_TIMEOUT** = bulk 始终未武装。这把"时机窗口太短"解释打薄——**设备侧 walk 失败本身（H1/H2）在稳定窗内也在发生**成为首要嫌疑。请审阅者给出：这个数据形态下 H1/H2/H3 的概率排序与判别实验设计。

**E. 主机侧已知变量**
- usbipd-win 有残留持久共享 `b67ab332→xnuloader`（管理员 `usbipd unbind` 可清，主机侧待办）；整夜 hunt 脚本的 attach 手术与设备自身枚举时序对撞（F9）。
- **提问**：usbipd 的 bind/Shared 状态、或 attach 到 WSL 的 vhci 重放，是否会改变 Windows 自身对该设备的枚举行为（0000:0002 的成因清单里排第几）？

**F. 代码级问题（对照 §4.1 行号）**
1. `usb_wait_pumped` 每 20ms 只调**一次** `handle_event`（单事件派发）。枚举风暴期（USB RESET → ConnectDone → GET_DESCRIPTOR×N → SET_CONFIGURATION，秒级内十余个事件）这个排空速率够吗？会不会积压导致 5s 主机控制超时？
2. `usb_present()` 只写 DCTL.RUN_STOP；vendor 的 connect（fcn.000161e0）是 **config（fcn.00013868）+ RUN_STOP** 两步。缺 config 步会不会留下半配置态，使后续 SET_CONFIG walk 失败（新 H 候选）？
3. `usb_start_attempt` 的 `BS->stall(50000)` 注释写 "five milliseconds"（stall 单位是 µs，实为 50ms）——行为影响多大？
4. vendor `ConfigureEnableEndpointsEx` 只装 ep0 对；运行期 SET_CONFIG 走 case 9 时的 DEPSTARTCFG 是否有"只许一次"语义？（对照开源同族 SamsungPkg UsbfnDwc3Dxe.c，本地 `[WSL]` 有 clone）
5. 探针在 beat 0 立即开火（present 后无等待），armed 会话是 beat 1（5s）命中——Windows 枚举+SET_CONFIG 的典型耗时与这个节拍的匹配度？
6. 若放弃 vendor UsbDeviceDxe/UsbfnDwc 栈、loader **直接寄存器驱动 DWC3 gadget**（参考 U-Boot dwc3 gadget / Linux dwc3，AArch64 UEFI 裸机），工作量与风险评级？（现状：vendor 栈两历史首胜已证可用，只是成功率低）

**G. 并行线（虚拟显示/出画，阶段 23.x）**
- `docs/research/f13-virtual-display.md`：上游树内核内建 MiniIOSurface/MiniIOMobileFramebuffer 假驱动（b25 logdump 证据 backboardd 已提交 1125×2436 帧）；ios-sweet（SM7150 真机 iOS 16.7 主屏）考古；23.x = cmdline-only 屏录取证。
- 请顺带审：23.x 的判定协议（`make-cmdline-v19.py` 头注释 + f13 §施工单）与 F6（vnode 表耗尽 @218s，v15 时代 300s 会话）风险的权衡是否合理。

## 6. v19 施工单（当前计划，欢迎挑战）

来源 wave22 verdict §7 + 审码增补（按序）：
1. 软化重掷：代际内见主机事件（DeviceStateChange Connected/Configured）不重掷，gen0 窗 30s→~120s（~15 行）
2. 服务相位提前：probe 阶段并行 `usb_poll_command`（~10 行）
3. E2E/提取通道换 Windows libusb 直连（probe18w 骨架已证）——23.x 已在用
4. usbipd 到达事件驱动 attach 替代轮询手术
5. raw 失败码透传打印（分辨 H1/H2）
6. settle 25s→5s（异常窗 B 的缓解）
刷写预算：每波 2 轮（boot_b 一揽子授权内）。

## 7. 关键数据/工件速查

| 文件 | 内容 |
|---|---|
| `[REPO]/logdump-v18.bin` + `.keylines.txt` | Boot #36 全量取证（512MB）+ 关键行提取；**armed 会话判别记录逐字**（`presented to the host` → beat 0 未武装 7 形 → **beat 1 armed** → started） |
| `[REPO]/wave22-scripts/bus18-watch.log` | Windows 总线 20s 采样直方图（xnuloader ↔ 0000:0002 ↔ blank 循环形态） |
| `[REPO]/wave22-scripts/probe18w.py/.log` | Windows libusb 直连骨架 + 首胜记录（open+claim / CONFIGURED / getvar 写落地） |
| `[REPO]/wave23-scripts/fetch23.log` | **最新反常数据**（§5-D：2.5min 稳定枚举 + bulk 全超时） |
| `[REPO]/wave22-scripts/patch-loader-v18.py` | v18 四 hunk 全文（含长注释设计动机） |
| `[REPO]/device-layer/udon-hakios-grafted-v18.img.report.json` | v18 四件套 sha 与自检记录 |
| `[WSL]/f12/` | vendor UsbfnDwc3Dxe/UsbDeviceDxe 反汇编工作区（radare2）；结论已浓缩进 f12 报告与 wave22 §1 |
| `[REPO]/docs/STATUS.md` Boot 表 | 36 次 boot 全记录（每次镜像 sha/刷写/取证/判定） |
