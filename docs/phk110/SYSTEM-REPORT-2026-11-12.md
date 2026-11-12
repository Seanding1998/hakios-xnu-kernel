# HakiOS（PHK110）系统能力快照 — 2026-11-12

> 本文是 v0.5「真·首帧」宣告（2026-11-12）当日的能力快照：刷入的系统构成、已验证的能力、主要修复史、已知边界。
> 逐日工程记录见 [STATUS.md](STATUS.md)（最新态）与 [M0-PROGRESS.md](M0-PROGRESS.md)（编年体全记录）；各阶段判定原文在 [waves/](waves/)，判定文件本体在 `waveNN-scripts/`（如 [wave45-scripts/verdict45-gatec.txt](../../wave45-scripts/verdict45-gatec.txt)）。

## 一、刷入的系统构成

boot_b 槽（日常安卓在 slot a，从未刷写）： graft `e6ca0b43`（v36，payload `0a70ec0a`）

| 层 | 内容 |
|---|---|
| 内核 | XNU Darwin 22.5.0（iOS 16.5 代，xnu-8796.121.2 自编译，8 核全开，`sha256 5b77b418`） |
| GPU 内核驱动 | 自研 Adreno 730 驱动（gen7/a7xx 形态）：21 步上电步进、GMU 4.0.7、fence 事件字段化 `0x08000031` |
| 用户态 | iOS 16.5 IPSW（20F66）sysimage + Procursus 引导生态：launchd pid 1、约 28 个进程、sshd、Sileo 系工具；签名强制关闭（越狱态） |
| GPU 用户态 | Mesa 25.0.7 freedreno（设备身份 FD725 = Adreno 730），OpenGL ES 3.2 |
| 电量 | 自研燃油计驱动（PM8350B 充电器观察 + bq27541 电量计位带 I2C），boot-arg `fuelgauge=2` |
| USB | 自研 loader gadget（18d1:d00d 服务窗）+ 四代自愈修复 + 编译器常量折叠根治 |
| 数据 | 12.5 GB darwin 数据分区（APFS），/var 跨重启持久（SSH host keys / 安装内容幸存） |

**启动链**：`ABL（手机自带）→ boot_b（UEFI 底座 + AVB 嫁接）→ BootShim → XnuLoader → XNU 内核 → Darwin`

**运行形态**：常驻循环制。内核会话约 10 分钟一代，到期自动重启换世代；数据不丢，全程零人工。回安卓 = 切槽（`set_active a`，秒级，可逆）。

## 二、已验证的能力（全部真机硬验收）

| 能力 | 验收证据 |
|---|---|
| 进 iOS 桌面并触摸操作 | 锁屏 → SpringBoard → 触摸/按键/背光全通；目前 CPU 软渲染（帧率约 10 fps 级） |
| SSH 进 Darwin shell | root 直连；256 KiB 传输双向内容 SHA 逐字一致；管理通道存活（`verdict27` 系 + `verdict42-w42ssh9.txt`） |
| GPU 硬件渲染上屏 | OpenGL ES 3.2 真硬件（`RENDER backend=hw renderer=FD725`）：1080×2400 三角形 19 ms 出图、五采样点像素与几何真值逐字一致、面板呈现确认（`verdict45-gatec.txt`；人眼目击 8 秒） |
| GPU fence 机制 | 双 nonce 写回内存逐字命中、序号递增、超时 0；一次 WPTR 丢失按预案重发自愈（`verdict45-gateb.txt`） |
| 数据持久 | 标记/文件/host keys 跨内核世代死亡幸存（`verdict34` 6/6 + `verdict42-var.txt` 复验） |
| 电力总线 | PMIC 仲裁器握手逐字命中（版本 0x70000000 / 768 通道，`verdict45-gated.txt` S1） |
| 安全边界 | boot_a 零刷写；全程零变砖；所有刷写走三重身份门（机型/槽位/镜像 SHA）+ OKAY 断言 |

### 方法链八步进度（硬件域 × 方法链，与首页 README 同步维护）

方法链八步：①看同型先例 → ②对官方物料 → ③取私有实现细节 → ④广域调查 → ⑤方案成文 → ⑥深挖修复 → ⑦隔离核验 → ⑧真机判定。逐格状态（图例：**✓** 完成 · **◐** 部分 · **✗** 未完成 · **—** 未建立记录）：

| 硬件域 | ① 同型 | ② 官方 | ③ 反编译 | ④ 广域 | ⑤ 方案 | ⑥ 深挖 | ⑦ 核验 | ⑧ 上机 | 当前状态 |
|---|---|---|---|---|---|---|---|---|---|
| 触摸（Synaptics S3910 / TouchComm v1） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通（真人点屏事件流未记录） |
| GPU（Adreno 730 / freedreno FD725） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通（硬件渲染首帧 + 人眼目击） |
| bootchain（ABL → boot_b → loader → XNU） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通 |
| display（NT37705 原生面板） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通（GPU 加速另见 GPU 行） |
| storage（UFS + APFS/HFS+ 数据卷） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通（/var 跨重启持久） |
| buttons（SPMI v7 仲裁器） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通 |
| USB（loader 服务窗 + en0） | ✓ | ✓ | ✓ ² | ✓ | ✓ | ✓ | ✓ | ✓ | 八步全通（gadget 韧性强化进行中） |
| 电量（PM8350B + bq27541） | ✓ | ✓ | ✓ ¹ | ✓ | ✓ | ✓ | ◐ | ◐ | 修复中（S2/S3） |
| wifi（WCN6750 / ath11k） | ✓ | ✓ | — | ✓ | ✓ | ◐ | ✗ | ✗ | 预备完成，待内核树排期 |
| audio（TFA9874 / ADSP） | — | ✓ | — | ◐ | — | — | ✗ | ✗ | 案头预备中 |
| CPU 多核 | — | — | — | — | — | — | — | ✓ | device-verified（早于八步记录） |
| 电源 | — | — | — | — | — | — | — | ✓ | device-verified（早于八步记录） |
| 诊断（logdump / 探针通道） | — | — | — | — | — | — | — | ✓ | device-verified（早于八步记录） |
| 蓝牙 | — | — | — | — | — | — | — | — | planned |
| 基带 | — | — | — | — | — | — | — | — | planned |
| DSP | — | — | — | — | — | — | — | — | planned |

**列语义**：

- **① 同型**：同 SoC / 同机型的外部先例项目，公开可查（takasugl/UniXNU-udon = 同款 PHK110 在跑；MIX Fold 2 的 Adreno 730 自研驱动先例；K60 线触摸芯片 ack 全通）。
- **② 官方**：厂商/官方公开物料对本域的覆盖确认（GPL 内核源、设备树、固件清单；USB 行以手机自带 vendor UEFI 二进制为一手物料）。
- **③ 反编译——本仓纪律**：优先以**厂商 GPL 源码、上游公开源码或真机黑盒寄存器级探测**替代反编译取证，绝不虚标。凡标 ✓¹ 的格均属此类，**未做过反编译**。唯一例外是 USB 行（✓²）：vendor UsbFnDwc/UsbConfigDxe **无源码**，该域实际以反汇编取证（radare2 静态分析），如实标注。无官方源且无私有细节需求的域如实标 —。
- **④ 广域**：同类移植项目普查与外部案例调查。
- **⑤ 方案**：实施级方案 / 施工单成文。
- **⑥ 深挖**：寄存器级 / 协议级 / 二进制级的深水定位与修复。
- **⑦ 核验**：隔离判定（自检套件、探针、验收器、判定文件）。
- **⑧ 上机**：真机刷写验证，有验收行 / 判定文件 / 人证背书。

**各行关键证据（公开侧路径，相对仓库根）**：

| 行 | 证据 |
|---|---|
| 触摸 | `docs/phk110/waves/` 的 wave12-touch-buttons / wave12a / wave12b / wave12c、`docs/phk110/research/research-tcm-miso.md`、`wave12*-scripts/`（驱动源码快照）、`wave1-hwmap.md`（GPL 源渠道） |
| GPU | `docs/phk110/waves/` 的 wave35 / 36 / 36-handoff / 37 / 39 / 40 / 41 / 44 / 45、`wave45-scripts/verdict45-gate{a,b,c,d}.txt`、`wave41-scripts/diffs/`、`docs/phk110/research/f16-k60-sm8475-census.md` |
| bootchain | `docs/phk110/waves/` 的 wave1-phk110pkg-spec / wave3-research-external / wave4 / wave5 / wave21_2 §7、`wave5-scripts/verify-udon-hakios.py`（每代自检，至 v36 = 72/72，`wave45-scripts/verify-v36.log`） |
| display | `docs/phk110/waves/` 的 wave4 / wave5 / wave6、`docs/phk110/research/f13-virtual-display.md`、`research/landscape-2026-11-08.md`（udon 同机先例） |
| storage | `docs/phk110/waves/` 的 wave15–wave18 / wave31 / wave34、`wave28-scripts/verdict34-var.txt`、`wave42-scripts/verdict42-var.txt` |
| buttons | `docs/phk110/waves/wave12-touch-buttons.md`（SPMI v7 适配 + 真机按键毫秒时戳）、`wave1-hwmap.md` |
| USB | `docs/phk110/waves/` 的 wave13 / wave21 系列 / wave22 / wave24 / wave38、`wave42-scripts/verdict42-w42ssh9.txt`（双向 SHA 524288/524288）、`docs/phk110/review/gpt-review-report-3-2026-11-11-usb.md` |
| 电量 | `docs/phk110/research/f17-battery-display.md`、`waves/wave43-battery.md`、`wave45-scripts/verdict45-gated.txt`、`wave43-scripts/` |
| wifi | `docs/phk110/waves/wave30-ath11k-tooling-prep.md`（施工单 7 项）、`research/f14` / `f15`、`research/ecosystem-census-2026-11-11.md`、`wave30-scripts/` |
| audio | `docs/phk110/PLAN.md` v0.6 节（TFA9874×2 / ADSP TERT_MI2S 器件勘定）、`research/f17`（ADSP 旁注）；情报波在途，发布后补格 |
| CPU 多核 / 电源 / 诊断 | `docs/phk110/waves/` 的 wave10 / wave11 / wave12（Boot #12–#16 判定行）、`wave45-scripts/verdict45-gated.txt`（PMIC 握手） |
| 蓝牙 / 基带 / DSP | `docs/phk110/PLAN.md` v0.6 / v0.7 节（规划口径） |

**维护规则（常设）**：这张表是活的维护物——**每次发布轮必须同步刷新状态格，新翻格必须指到当轮新增的证据文件**；没有对应证据文件的新声明不翻格。本表在首页 README 与 [docs/phk110/SYSTEM-REPORT-2026-11-12.md](docs/phk110/SYSTEM-REPORT-2026-11-12.md) 各存一份，两处须同轮同步。

## 三、主要修复史（问题 → 根因 → 结果）

| 问题 | 根因 | 结果 |
|---|---|---|
| 内核启动即崩 | 中断控制器地址照抄了别家 SoC | 改本机设备树实地址 + stride，v0.1 达成 |
| launchd 早期死亡 | 设备身份链未建立 | 设备树真身份 + boot-arg 回退双层修复 |
| /var 重启即丢 | init 二次运行以内存盘遮蔽真实挂载 | 挂载防重入守卫，持久化达成 |
| USB 错误墙（端点风暴刷屏） | 泄漏/竞态/检测器误诊四代修复后，发现是**编译器把修复代码整段优化删除**（跨过程常量折叠把状态戳折叠为常量 0） | 四个状态戳声明 volatile（语义正确且根治），船级二进制反汇编级断言在案 |
| SSH 传输字节不一致 | 主机侧 UTF-8 解码把合法字节流膨胀为替换符（假象）+ 一次间歇竞态 | raw-bytes 管道；复验连续七轮传输 PASS |
| GPU 上电步进第 1 步挂死 | 五处寄存器/固件假设错（时钟、熔丝、GPUCC、zap 布局、旧代 address-mode 表） | 五代修复全部以本机设备树/vendor 源锚定，步 1-21 全绿 |
| GPU fence 永不完成 | 完成事件首字缺 WRITE_ENABLED 位（第 6 代写法残留） | 按三方参照字段化重建，设备级探针定案 |
| GPU NC_MODE 寄存器编错 | 按错误的高端位 assumptions 编码 | vendor 公式 + DDR 条件重算，硬件值逐格命中 |
| GL 测试假绿 | 测试只有打印无断言、失败也退 0 | 重写为四段结构化验收器（像素真值 + 覆盖窗 + 分级退出码） |
| 循环中断 | ABL 启动回退把活动槽翻向 a | `set_active b` 即恢复；根治排后续 |
| 刷写被掐死 | 11 个历史遗留看护进程每 2 秒强制拔 USB | 清场 + 看护进程卫生纪律入册 |

## 四、已知边界（诚实清单）

| 项 | 现状 | 计划 |
|---|---|---|
| 电量显示 | 数据链未通（充电块通道表布局与本机不符 + 电量计芯片无应答）——按"宁可不显示不显示假值"原则当前不显示 | 修复中（仲裁器表取证 + 电量计三查） |
| 桌面 GPU 加速 | GPU 硬件出图已证，窗口服务器仍走 CPU 渲染 | 接入即为桌面丝滑化（下一步） |
| Wi-Fi / 蓝牙 | 未开始（工具链与蓝图预备中） | v0.6 |
| 音频 | 未开始（情报占位） | v0.6 |
| 蜂窝 | 目标半通，未排期 | v0.6+ |
| 连续驻留 | 循环制（10 分钟世代），无挂起/恢复 | 后续版本方向 |
| Windows 报"USB 描述符请求失败" | iOS 侧枚举的是自家 loader gadget，属枚举层正常现象，装驱动无效也无需装 | 已定性（不修） |

## 五、版本里程碑

| 版本 | 日期 | 达成点 |
|---|---|---|
| v0.1 黑匣子 | 2026-11-03 | UEFI→loader→内核→用户态全链 + 26 KB 日志取证 |
| v0.2 第一缕光 | 2026-11-04 | 原生面板显示栈 |
| v0.3 触感 | 2026-11-05 | 常驻循环 / 8 核 / 按键 / 触摸 |
| iOS 桌面出画 | 2026-11-09 | SpringBoard 渲染上屏（CPU 渲染） |
| v0.4 达尔文 | 2026-11-11 | launchd 全家桶 + 触摸 + USB 服务 + SSH root shell + /var 持久；三级验收门全绿 |
| v0.5 GPU 内核侧首亮 | 2026-11-11 | GPU 上电步进 21 步全绿，3D 核接受命令并写内存 |
| **v0.5 真·首帧** | **2026-11-12** | **GPU 硬件渲染上屏（Mesa 25.0.7 / OpenGL ES 3.2），四门判定 3 绿 1 部分达成** |

## 六、下一步

1. 电量显示修复（进行中）
2. 桌面窗口服务器接入 GPU（GL=1 后续）
3. v0.6：Wi-Fi / 音频（预备进行中）
4. 远期：v0.8 双系统共存 → v1.0 日常可用
