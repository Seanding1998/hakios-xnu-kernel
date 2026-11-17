# HakiOS（PHK110）系统能力快照 — 2026-11-17

> 本文是 **v0.5.1「日用化」**（2026-11-13 → 2026-11-17）当日的能力快照：刷入的系统构成、能/不能（每行带实测证据）、日用验收四项、v0.6 三线（音频 / PCIe-WiFi-蓝牙 / 相机）探测结论、回退与恢复路径、复现命令。
> 与前一版快照 [SYSTEM-REPORT-2026-11-12.md](SYSTEM-REPORT-2026-11-12.md)（v0.5 真·首帧）逐项对照阅读；原始证据（分区 sha、日志原文、执行命令、镜像 sha 全表）在同日新增的 [EVIDENCE-2026-11-17.md](EVIDENCE-2026-11-17.md)；逐日工程记录见 [STATUS.md](STATUS.md)。
> 纪律：**只有真机硬验收行才算数**；读不到的写 CANNOT，没实测的写 UNVERIFIED，不把推断润色成结论。

## 一、刷入的系统构成

| 层 | 内容（2026-11-16 01:07 实测状态） |
|---|---|
| 机型 | 一加 Ace 2 / **PHK110** / **SM8475**（cape / Udon 板）/ 16 GB；GPU = **Adreno 730** |
| boot_b（实验槽，现役） | **`udon-hakios-grafted-v101-daily-gpu.img`**，192 MiB = 201,326,592 B；graft `68c1c6af5561dc992400f53468db6ee09308445311f842549779cb76eb95e3cb` |
| boot_a（日常安卓） | **从未写**；sha `b573b1441505ff19d04d67699d74cb8c7421118653e38885825a0ccd45eca96f`（2026-11-16 01:07 复核未变） |
| misc | `85094313ebd62c04d8ce35eb11ea19d48b616d54b762b98b3b6fb0a832037187` |
| 内核 | v70-daily 线内核 `be610f26…`（15,144,936 B），payload `d2eee9ea…` 血统；cmdline 唯一改动 = `loader_return_after` 1800 → **86400** |
| GPU 档位 | cmdline 带 **`adreno_speed=5`**（= 13 档表第 5 档 **710 MHz**）；v61/v98 血统无此 token，默认第 12 档 **283 MHz** |
| 显示 | 1240×2772 面板；`fb_hz=120 ca_vbl=1`；`fb_flip=1`；`fb_gap_win=16`；壁纸钩子 `wallpaper_pic=1` |
| 用户态 | iOS 16.5（20F66）sysimage + Procursus 引导生态：launchd pid 1、SpringBoard/backboardd、sshd；签名强制关闭（越狱态）；**409 daemons** job 表已装配 |
| 启动链 | `ABL（手机自带）→ boot_b → XnuLoader → XNU → loader 窗口（USB gadget 18d1:d00d）→ ABL 启动活动槽` |
| 会话形态 | `loader_return_after=86400` ⇒ 一代最长 **24 h**；到期回 loader 窗口，再由 ABL 按 retry 回落 |

**镜像是 192 MiB 的 graft 完整镜像**（UEFI 底座 + AVB 嫁接 + payload）；payload 里只换 cmdline 一个 token，其余六项 entry 与 v70-daily 逐字节相同。

## 二、能力表（能 / 不能 / 证据）

| 能力 | 状态 | 实测证据（可核对） |
|---|---|---|
| 进 iOS 桌面 + 触摸/按键 | ✅ 能 | 锁屏 → SpringBoard；`launchd` 行 1,072 条（用户态起来了）；触摸 `touch_chunk_ms=1` 步进续包 |
| 8 核 / 电源 | ✅ 能 | `cpus=8 bootcpu=7`，7 个应用核齐起（v0.3 起保持） |
| GPU 硬件渲染（GL=1 桌面） | ✅ 能 | `RENDER backend=hw renderer=FD725`（v36 门 C）；v0.5.1 线把 3D 核从默认 **283 MHz**（日志 `adreno: 17: the speed wanted: 283 MHz`、`measured … 282999888 Hz`，即 282,999,888 Hz）改成 `adreno_speed=5` = **710 MHz**（v70 线 FINDINGS 实测 `710,002,888 Hz`） |
| 自定义壁纸 | ✅ 能 | `/redwood/share/wallpaper.png` = **4,901,648 B** 在 carrier 中（两次列出）；用户真机确认生效 |
| 锁屏 / 主屏壁纸可编辑 | ✅ 能 | 用户真机确认（编辑入口可用） |
| 亮度滑块 | ✅ 能 | 滑块生效；**92% 厂商上限 顶档 `0xCA3`**；boot 默认 800‰ = `0xA1C`；回退开关 `panel_bright_off=1` |
| Photos 打开 + 建库 | ✅ 能 | 409 daemons 装配后能打开并建库；console 出现 `PhotosPosterProvider` |
| 抗撕裂（panel gap 等待） | ✅ 能（v0.5.1 判定线） | `panel gap: 9583 waits, 0 timeouts, line 1..2772, broken=0`；每窗口 `0 gave up`；最好窗口 **531 frames in 5013 ms（约 105 帧/秒）** |
| SSH / loader 服务窗 | ✅ 能 | loader gadget `18d1:d00d`（起机 t+24 s 可见）；双向内容 SHA 524288/524288（v0.4 判定线，保持） |
| /var 跨重启持久 | ✅ 能 | 标记/文件/host keys 幸存（v0.4 判定线，保持） |
| 电量显示（含充电图标） | ❌ 不能 | 本机 SPMI 仲裁表**没有 PM8350B 充电块**（`0x10/0x12/0x13/0x15`）⇒ `charger_look()` 永远读不到 VBUS；现行判据 = 电量计净电流（实测采样 −278 mA 属净放电） |
| 声音（音频出声） | ❌ 不能 | 内核音频帧在写（`hakios: audio: playing` / `peak 48% of full scale`），但无 codec/ADSP 出声链；ADSP 卡在 **AOP 邮箱握手**（见 §四） |
| Wi-Fi | ❌ 不能 | PCIe 链路 `0x72c = 0x8200000`（**bit 4 = 0，链路未起**）；PHY 只读探测后按设计停在 `-15`，`17cb:1103` 未读到 |
| 蓝牙 | ❌ 不能 | 随 Wi-Fi（同一 PCIe/WCN6750 通道），独立驱动未上机 |
| 相机 | ❌ 不能 | `camera=1` 只读探测跑满 494 s（四个基址映射成功），但 switch `status 0x88000`（off）⇒ 按设计不读寄存器、不占引脚；**Camera.app 与图标在，409 plists 里没有 camera job**（`applecamerad` 不 spawn） |
| 蜂窝（4G/5G） | ❌ 不能 | 排 v0.7（IPA/modem 线），本轮未动 |
| iOS 内关机 | ❌ 不能（根因已定位） | 关机与重启在 `halt_all_cpus` **合流**；`PE_halt_restart=NULL`（全树无 handler）；loader `reboot()` 只有 `EfiResetCold`（无 `EfiResetShutdown`）；BSD 优雅关机段无超时 |
| Notes 画图 | ❌ 不能 | 抓到框架层 **userabort**（无 NSException 文案）；`v78-notes-trace`（`applog=1 systrace=1`）**已构建未上机** ⇒ 下一步 UNVERIFIED |
| spurious interrupt `0x105` | ❓ 未捕获 | 用户屏幕目击；已落盘 **8 份** console 全 **0 命中** ⇒ 无法给上下文 |
| 桌面 GPU 加速（窗口服务器） | ✅ 能（v0.5 起） | GL=1 桌面生效：加速器行、8/8 EAGL、FD725、12,000 帧统计、0 GPU fault（2026-11-13 判定） |

**读法**：✅ = 有本机日志/判定行背书；❌ = 已实测到边界并写明卡点；❓ = 有现象但无落盘证据。**没有一条来自推断。**

## 三、日用验收（四项，全部真机实测）

| # | 验收项 | 判定 | 数字/证据 |
|---|---|---|---|
| 1 | **壁纸**（含锁屏/主屏可编辑） | ✅ | `/redwood/share/wallpaper.png` 4,901,648 B；用户真机确认；F-11「通知栏纯黑」已澄清 = **壁纸缺失所致**，恢复默认壁纸后正常（**不是缺陷**，本条 2026-11-15 关闭） |
| 2 | **亮度** | ✅ | 滑块生效；92% 上限（顶档 `0xCA3`）；日志 `asked→sent (dsi status 0)`；回退 `panel_bright_off=1` |
| 3 | **Photos** | ✅ | 409 daemons 后能打开并建库；`PhotosPosterProvider` 出现在 console |
| 4 | **抗撕裂** | ✅ | `9583 waits, 0 timeouts, 0 gave up`；最好窗口 `531 frames in 5013 ms`（≈105 帧/秒）；空闲窗口 10 帧/秒属正常 |

**四项全绿 = v0.5.1「日用化」的判定线**。注意这四项是**日用观感**线，不是 v1.0 功能线：声音/相机/蜂窝/Wi-Fi 仍在 v0.6/v0.7 队列里（见 §四、§八）。

## 四、v0.6 三线探测结论（只写实测，不写推测）

### 4.1 音频 / ADSP（`v102-audio-daily` 血统，真机 679 s 会话）

| 步 | 内容 | 结果 |
|---|---|---|
| step 1 | SMEM 分区与 item | **通过**：分区 `0x80acf000` / `0x30000`（自由 `0x2bfa0`）；item **478 / 479 在**；**443 / 480 / 423 不在**；doorbell 读作 `0xffffffff` |
| step 2 | 固件加载 | **通过**：命中路径 **`md1:/fw`**；`adsp.mdt` **5,404 B**（4,520 B 哈希）+ `adsp.b01…b23`；**24 段 / 17,652,400 B 全部 whole**；落到 **`0x86300000`**（carveout `0x2800000`） |
| step 3 | AOP 邮箱 | **失败**：mailbox magic `0x4d41494c` / version `0x1`；our mailbox `0x128`、size `0x2d8`；写 4 个 `0xffff` 后 **1 s 内 AOP 不应答** → 回滚 `0xffff0000` → `step 3: FAILED` → `THE AUDIO DSP DID NOT COME UP` |

**结论：卡在 AOP 邮箱握手，不是固件问题。** 固件与 SMEM 都已就位到"能过"的粒度；下一层是 AOP/SMP2P 通道配对与门铃时序（研究已给出候选：IPCC 基址在 cape 应为 `0x0ed18000`，`rsc` 为 `0x17a20000`，见 §七）。
**CANNOT**：该版内核没打印 IPCC 基址行 / mailbox 前值 / 6 次状态轮询（`v105` 本代 console 未被 compose 进 logdump，属"未捕获"，不是"没打"）。

### 4.2 PCIe / Wi-Fi / 蓝牙

| 步 | 读数（逐字） | 含义 |
|---|---|---|
| 1/6 开关 | `0x7b004 = 0xf822f001`，**bit 31 = 1** | 控制器可读（电源门这条链被打通） |
| 2/6 时钟分支 | `0x7b020=0x220`、`0x7b028=0x200220`、`0x7b030=0`、`0x7b034=0x220`、`0x7b03c=0` | 五条分支已释放 |
| 3/6 链路 | `0x72c = 0x8200000`，**bit 4 = 0** | **链路未起**（Pong/ZiZhan 判据里 bit4 = link up） |
| 4/6 PHY | 曾 **data abort**：`pc 0xfffffff0074dd708`、`esr 0x96000046`、`far 0xfffffff21cb3c01c`、`x27=0x7c01c` | 根因 = **基址加了两遍**（宏 `GCC_PCIE_0_PHY_BCR` 已含 `gcc`，代码又加一次 ⇒ `2*gcc + 0x7c01c`） |

**修复（已真机验证）**：GCC 访问收成唯一一条路 **`gcc_read()/gcc_write()` → `window_check/read/write`**（偏移一律是窗口内真实偏移，写前查窗口、写后回读），并新增 `pcie_phy_probe=1`（只读后停）/`pcie_phy_reset=1`（才允许写）。修复后只读探测：**`gcc 0x7c01c = 0`（bit0 clear，PHY 已 out of reset）**、**`parf 0x40 = 0x900`**，随后按 `pcie_phy_probe=1` **停在 `-15`**，ECAM/BAR0 未读、**零写**，会话跑满 496 s 无 panic。

**结论**：PCIe 从"console 之前猝死"推进到"能按设计停在 PHY 之后"。**CANNOT**：`17cb:1103`（WCN6750 的 vendor:device）仍未读到——训练/链路建立未执行。

### 4.3 相机

- `camera=1`（只读）跑满 **494 s**；四个基址映射成功：`camcc 0xade0000+0x20000`、`csiphy 0xace8000+0x2000`、`cci 0xac15000+0x1000`、`cpas 0xac13000+0x1000`。
- switch **`control 0x22f001`、`status 0x88000`（off）**；`cci0`/`csiphy2` 分支均 `0x80000000` ⇒ 驱动**按设计不读寄存器、不占引脚**。
- 引脚计划已落文：**CCI0 GPIO110/111、reset GPIO120、MCLK0 GPIO100**。
- **`camera=2`（上电 + 扫 chip ID）尚未上机 ⇒ UNVERIFIED**（镜像 `v108-camera-2` 已构建，graft `8e92ed46…`）。
- 另有一条硬阻塞：**Camera.app 与图标在，但 409 plists 里没有 camera job**（`applecamerad` 不 spawn）。

### 4.4 附记（同日实测的四个边界）

| 项 | 结论 |
|---|---|
| 充电 | 本机 SPMI 仲裁表没有 PM8350B 充电块（`0x10/0x12/0x13/0x15`）⇒ 读不到 VBUS；**"电量计净电流判据"就是这套硬件/固件下的上限**（要真读 VBUS 得走 loader 的 ChargerEx 桥或改 arbiter 配置，非本内核可解） |
| 关机卡死 | 根因 = halt 合流 + loader 只有 `EfiResetCold` + BSD 优雅关机无超时；**快修镜像未验 ⇒ UNVERIFIED** |
| Notes 画图 | 框架层 userabort（无异常文案）；`v78-notes-trace` 已构建未上机 |
| spurious interrupt `0x105` | 用户屏幕目击；8 份已落盘 console **0 命中**（"没出现"而非"没搜"） |

## 五、回退与恢复路径

| 场景 | 操作 | 实测 |
|---|---|---|
| 回安卓（有物理按键） | 三键（电源+音量上+音量下）→ 按住**音量下**进 ABL fastboot → `fastboot set_active a` + `fastboot reboot` | 秒级、零刷写、可逆 |
| 回安卓（无按键，靠超时） | 等 ABL retry 耗尽自动回落 slot a | **实测约 61 分钟**（21:36:29 起 iOS → 22:37:14 回安卓，`22d9:2769 一加 Ace 2`、`sys.boot_completed=1`、`slot=_a`） |
| loader 窗口内主机侧改槽 | attach 后 `fastboot getvar` / `set_active` | **未成立（CANNOT）**：一次 `fastboot getvar current-slot` 等 115.9 s → `FAILED (Status read failed (No such device))`；另以 4 s 节拍 15 次 attach 全未见设备 |
| 回滚 boot_b 到上一版 | `fastboot flash boot_b <v98-daily 或 v70-daily>` | 三件镜像 sha 与回滚路径见 §六/证据文档 |

**为什么 `loader_return_after=86400` 需要谨慎**：24 h 内没有物理按键就回不来（loader 服务窗只在内核返回后才开），所以**测试镜像一律用 360 s 孪生**——同 payload 只改这一个 token。

## 六、复现命令（主机侧；`<host>` = 本机工作区占位）

> 全部真机动作的红线：**boot_a 永不写**；boot_b 的写/切槽属非破坏动作；`logdump` 只存上一世代。

```bash
# 0) 通道（Windows 主机上 usbipd 不稳时的可用配方）
sudo usbip list -r 127.0.0.1
sudo usbip attach -r 127.0.0.1 -b 2-2        # 之后 fastboot 才看得到设备
sudo fastboot devices
sudo usbip detach -p 00

# 1) 三门 + 双 OKAY（写 boot_b 前）
fastboot getvar product                      # 期望 taro
sha256sum <host>/hakios-phk110/device-layer/udon-hakios-grafted-v101-daily-gpu.img
                                             # 期望 68c1c6af5561dc992400f53468db6ee09308445311f842549779cb76eb95e3cb
fastboot flash boot_b <host>/hakios-phk110/device-layer/udon-hakios-grafted-v101-daily-gpu.img
                                             # 期望 Sending 'boot_b' OKAY + Writing 'boot_b' OKAY

# 2) 切槽进 iOS / 回安卓
fastboot set_active b && fastboot reboot
fastboot set_active a && fastboot reboot     # 回安卓（零刷写）

# 3) 零写 RAM 直启（测试镜像一律这样跑）
fastboot boot <image>.img                    # 期望 Sending 'boot.img' OKAY + Booting OKAY

# 4) 分区 sha 复核（安卓侧，只读）
adb shell 'sha256sum /dev/block/by-name/boot_a /dev/block/by-name/boot_b /dev/block/by-name/misc'

# 5) 日志取证（整分区 512 MiB + 16 MiB 头，双端 sha 对拍）
#    拉取后在主机侧过滤关键行：
grep -aE 'pcie:|adsp:|camss:|panel gap:|adreno:|paper|PhotosPosterProvider' logdump-strings.txt
```

**镜像 sha（graft = 完整镜像 sha256 前 16 位；全值见 [EVIDENCE-2026-11-17.md](EVIDENCE-2026-11-17.md)）**

| 镜像 | sha256（前 16） | 说明 |
|---|---|---|
| `udon-hakios-grafted-v62-long.img` | `ca907aab…` | 回滚版（30 分钟会话） |
| `udon-hakios-grafted-v70-daily.img` | `256f7cf2…` | v70 日用（含 `adreno_speed=5`、壁纸、亮度、409 daemons、关机快修、1800 s） |
| `udon-hakios-grafted-v98-daily.img` | `1de9911a…` | v61 + `loader_return_after=86400` |
| **`udon-hakios-grafted-v101-daily-gpu.img`** | **`68c1c6af…`** | **当前 boot_b / Release 资产**：v70 基线 + 86400，只改 cmdline 一个 token |
| `udon-hakios-grafted-v102-audio-daily.img` | `0c82e52a…` | 音频血统 + ADSP 固件整套 + 86400 |
| `udon-hakios-grafted-v104-pcie-phy-probe.img` | `4ee54f4c…` | PCIe PHY 只读探测（`pcie_phy_probe=1`） |
| `udon-hakios-grafted-v105-audio-aop.img` | `231d00e7…` | AOP 邮箱版（`985e676c` 内核，360 s 孪生） |
| `udon-hakios-grafted-v106-camera-probe.img` | `6b0b36b6…` | `camera=1` 只读探测 |
| `udon-hakios-grafted-v107-pcie-phy-reset.img` | `7c3a52df…` | PHY 复位→训练（`pcie_phy_reset=1`，未上机） |
| `udon-hakios-grafted-v108-camera-2.img` | `8e92ed46…` | `camera=2` 上电 + 扫 chip ID（未上机） |

## 七、参考（研究结论，不是本机实测）

| 参照 | 结论 | 对本项目的用法 |
|---|---|---|
| **UniXNU-zizhan**（同 SM8475）`drivers/PongWifi/PongWifiPci.cpp` | PCIe **只挂接已存在的 root-port**，不在枚举时碰 DBI/config；MSI 走 **DesignWare → GIC SPI140**（不走 ITS） | 我们的 `hakios.pcie.c` 反而在内核早期"建链+枚举"，这是 v94–v97 在 console 之前猝死的结构性原因 |
| **UniXNU / 上游 `hakios.adsp.c`** 的 AOP QMP | AOP 由 **XBL 拉起**、**不需要载 `aop.mdt`**；内核只做 QMP：邮箱 **`0xc300000` / `0x400B`**、15 个描述符 word、**6 个状态各 1 s、最多 4 轮**、由 **IPCC 门铃**驱动 | 说明 step 3 该改的是"门铃 + 状态轮询"，不是"再找固件" |
| cape 地址勘误 | **IPCC = `0x0ed18000`**（不是 redwood 的 `0x00408000`）、**rsc = `0x17a20000`**（不是 `0x18220000`） | 本轮 step 3 失败与这两个常量的嫌疑直接相关；下一轮先改基址再重跑同一镜像 |

## 八、CANNOT / UNVERIFIED 清单（如实）

**CANNOT（本机/本轮读不到）**

1. `17cb:1103`（WCN6750 的设备 ID）：PCIe 链路未起，配置空间从未读过。
2. `camera=1` 的 `cciN version` / `csiphyN out of reset`：需要 `camera=2` 上电后才会有。
3. v105 的 IPCC 基址行 / mailbox 前值 / 6 次状态轮询：该代 console 未被 compose 进 logdump。
4. loader 窗口内主机侧 `set_active a`：两次尝试均失败（详见 §五）⇒ 实际回安卓靠 ABL retry（约 61 min）。
5. 充电 VBUS：`charger_look()` 在本机 SPMI 仲裁表里没有可用通道。
6. spurious interrupt `0x105` 的上下文：8 份 console 0 命中。

**UNVERIFIED（已构建/已定位，但未上机或未取到本代日志）**

1. `v101-daily-gpu` **自己那一代**会话的 `panel gap` / `710 MHz` / `sound` 行：会话 24 h，`logdump` 只留上一世代 ⇒ 现有 710 MHz 判据来自 v70 线 FINDINGS 的实测（`710,002,888 Hz`），**不是** v101 本代会话。
2. `camera=2`（v108）上电 + chip ID 扫描。
3. 关机快修（v67/v68 线）与关机根治（powerd 注入）。
4. `v78-notes-trace` 的 usertrap pc/lr。
5. `v107` 的 PHY 复位→训练、以及训练成功后的 `0x728` 期望值。

## 九、与 2026-11-12 快照的差异（一表看完）

| 项 | 2026-11-12（v0.5 真·首帧） | 2026-11-17（v0.5.1 日用化） |
|---|---|---|
| boot_b | v36 `e6ca0b43…`，会话约 10 分钟一代 | **v101-daily-gpu `68c1c6af…`**，会话 24 h 帽 |
| 桌面渲染 | GPU 硬件出图已证，窗口服务器仍 CPU | **GL=1 桌面**（CA → EAGL → Mesa/FD725）生效 |
| 壁纸 / 亮度 | 未实现（F-14 / F-15 未修） | **✅ 均真机确认**（含 92% 亮度上限） |
| 抗撕裂 | 未处理 | **✅ `9583 waits, 0 timeouts, 0 gave up`** |
| Photos | 打不开（守护进程整组缺失） | **✅ 409 daemons 后可建库** |
| GPU 档位 | 默认 283 MHz | **`adreno_speed=5` = 710 MHz** |
| 音频 | 未开始 | **推进到 step 3**（固件 24 段全 whole，卡 AOP 邮箱） |
| PCIe/Wi-Fi | 未开始（只有 ath11k 工具与施工单） | **推进到 PHY 之后**（`parf 0x40 = 0x900`，按设计停 `-15`，零写） |
| 相机 | 未开始 | **`camera=1` 只读探测通过**（四基址映射，`camera=2` 待上机） |
| 发布 | Release `v0.5-gpu-firstframe` | Release **`v0.5.1-daily`**（资产 = `v101-daily-gpu`，仅 PHK110） |
