# 阶段 24 · 2026-11-09 · USB 端点问题的诊断：复位流程缺陷定案

> 2026-11-09 02:30 → 04:xx · 阶段 24 执行记录
> 施工单：`docs/waves/wave24-exp1-design.md`（6 设备侧项 + 判决表）+ `docs/waves/wave23-virtual-display.md` §7（Exp-1 十一项终稿）；判据基线：`docs/research/f12-ep2-not-configured.md`；外部审阅两轮：`docs/review/gpt-review-report-2026-11-09.md`、`gpt-review-report-2-2026-11-09.md`

## 0. 一句话结论

**判决表确定：GCTL bit11 分支命中（P1-1 复位流程分支），H1/H2/H3 不再需要分辨**——准备工作核实确认两项结构事实（vendor 打印走 Qualcomm shim "SerialPort Lib" 控制台而非 ConOut；UsbFn 协议接口 = 实例+8，vendor 自己的 Transfer 走 `usb_fn-8` 并校验 'usbf' 签名），据此写 v20 诊断 loader（`wave24-scripts/patch-loader-v24.py`，14 hunks）一次刷写真机验证（Boot #38，预算 1/2），**每一个观测到的 boot（主机侧实录 cycles 1-3 + logdump 全文的最终会话）全部 gen 0 beat 1 首试武装、四检查点通道全程闭合**（真实 OUT 提交成功 → 主机写完成 → 设备收到完成事件 → IN 应答，分开记录在设备侧 log 与主机侧 probe24.log），其中每次 boot 的 wake 采样都实锤 **GCTL bit11（CORESOFTRESET）等待自清超时仍为 1、由 loader 显式清除**（旧码超时后不清——每一代历史 boot 都带着半复位的 core 跑 bring-up）。墙（0x8000000C 错误屏）在所有会话中一次都没有回来：复位流程修对后墙消失，判决表"设备已配置但从未留下有效 OUT 接收""H1/H2/H3 walk 失败"各行不再需要触发。

## 1. T1 准备工作核实（零手机，全部树内实证）——两项改变施工的决定性事实

| 项 | 核实结果（指令级） |
|---|---|
| **④ 前置准备工作：vendor 打印走哪条门** | **不走 ConOut**。UsbfnDwc3Dxe.efi 反汇编（WSL ~/f12，radare2）：DebugPrint = fcn.0001c044（属性掩码检查 → `AsciiVSPrint` 512B 缓冲 → `AsciiStrLen` → fcn.0001f258）→ 惰性初始化 fcn.0001f218：`GetFirstGuidHob(gEfiShimLibraryHobGuid BEDAEABC-5E70-4D66-9733-213D072B9D04)`（HOB 列表经 DxeCore 配置表 `gEfiHobListGuid 7739f24c-93d7-11d4-9a3a-0090273fc14d` 找到，fcn.0001d2b0=GetHobList、fcn.0001d494/0001d430=GetNextGuidHob）→ shim 块 = `*(u64*)(hob+0x18)` → `shim[0x10]` 为"按名字找控制台设备"的 locator，以 `("SerialPort Lib", 0, &slot)` 调用（名字串 @0x25b2b）→ 输出 = `[slot+0x10](buf, len)`。**结论：改钩该层（设计预稿 ④ 的"若走独立 DebugLib 路径则改钩该层"分支）** |
| **⑥ b 前置准备工作：speed 字段对象布局** | `CreateUsbfnInstance fcn.00011590`：分配 0xe18 实例 → vtable 装配 [x20+0x10..0xa8] → **`InstallMultipleProtocolInterfaces(&Handle, &gEfiUsbfnIoProtocolGuid, x20+8, NULL)`（@0x119ec-0x11a0c）**——协议接口 = 实例+8（'usbf' 签名在 +0x00）。旁证：vendor 自己的 Transfer（fcn.000130bc）入口 `ldr x10, [x8, -8]!; cmp 'usbf'`——**取接口指针减 8 即实例并验签**。因此：speed = 接口-8 + 0x184；物理端点表 = 接口-8 + 0（stride 0x20，state @+0x18、maxpkt @+0x30；phys[2] = EP1-OUT、phys[3] = EP1-IN）。**读取必须先过 'usbf' 签名门**（终稿"先核验对象布局再读"的落实）。UsbDeviceDxe 侧 +0x1f8：**放弃直读**——准备工作无法把 UsbDevice 协议接口锚到其实例（两个二进制的 vtable 装配都查证了：UsbFn 侧有 Install 卖证，UsbDevice 侧没有；盲读违反风险登记），H3 改由镜像的 "Unknown USB Speed" 行覆盖 |
| 附带事实 1 | 本 FD（SILICIUM_UEFI.fd，1 FV + 2 LZMA 压缩节）**raw 搜索找不到任何 vendor USB 字符串/GUID**（"DwcPrepareURB"/UsbfnIo GUID 等）——vendor 栈在压缩节里，运行时解压。**gEfiHobListGuid 在 FD 中完全不存在**：Mu 的 DxeCore 不发布 HOB 列表配置表 |
| 附带事实 2 | 真机验证实证（见 §4）：loader 的 `LocateProtocol(UsbfnIo)` 在 t+1.0 返回 NOT FOUND 且被一次性负缓存 → **vendor 字段采样全程未激活**（"the UsbFn layer is not here" 行在 log）；UsbDevice 协议（QCOM_USB_DEVICE_GUID）正常在位、USB 服务器正常。UsbFn 不在位的机理（压缩节晚解压/不同 GUID）未定案——见 §7 风险 |

## 2. T2 施工（wave24-scripts/ 新目录，Windows device-layer 只新增；WSL loader.c delta）

`patch-loader-v24.py`（14 hunks，211,320 → 227,289 B）在 v18+v19b 树上：

| # | 项 | 实现 |
|---|---|---|
| ① | **统一事件消费入口** | `usb_pump()` 成为唯一 handle_event 调用点（原 4 处：wait_pumped/stage/usb_wait/poll_command 全部收尾）；有界排空（8 事件/次）+ 积压形态记录（calls/events/max-drain/max-gap）；状态事件统一进 host book（Connected 置 usb_host_seen + 首次采样，Disconnected 退役常驻接收且**不算主机在场**、不跨代盲清）；TransferNotification 按 endpoint 落入 pending store（usb_done_out/in），由调用方服务——F1 三缺陷（等待降级丢状态、传输完成被等待 helper 丢弃、usb_rx_queued 失真）全部消除 |
| ② | **持续真实 RX** | `usb_arm_rx()`：511B 非零长 OUT 接收常驻（= 命令通道自己的接收），零长度探针退役（无争用）；请求带代际身份 usb_rx_gen（start_ex/re-throw 都 bump）；提交返回码 = checkpoint-1；完成经 pump 路由 = checkpoint-3；Disconnected/abort 退役 |
| ③ | **失败限频+首错粘性** | `usb_wall_gate()`：**在提交源头限频**（每次被拒的提交都会触发 vendor 四行墙 = 刷屏源；被拒后下一次提交等退避 1s→30s，泵送不停）；首次拒绝全行打印，重复按退避节拍打印并累计计数 |
| ④ | **ConOut 镜像 → 改钩 shim 门** | 准备工作判定 vendor 不走 ConOut（§1）。`mirror_install()`：配置表找 HOB 列表 → GUID HOB 找 shim 块 → locator("SerialPort Lib") → 包 `[dev+0x10]` 写成员（thunk 抄环 + 原调用照发 + 单一 in-flight 防递归 + put_char 自打印标志防双记）；前导错误粘性清单（DEPSTARTCFG Fails / Failed to set config for ep / DwcConfigureEP failed / Unknown USB Speed）在镜像流上一次性 sticky 打印；镜像预算（ring 尾部留 6KB）超限丢弃+粘性说明；ConOut 门同样包（shim 写成员可能自己画到控制台），找不到门只打一行、不影响原打印。**真机验证结果：vendor 门 NOT FOUND（gEfiHobListGuid 配置表不存在，§1 附带事实 1），按设计优雅降级；console 门 hooked** |
| ⑤ | **GCTL bit11 显式清除** | `usb_dwc3_wake()`：等待自清超时后 `*gctl &= ~(1<<11)` + 打印 "cleared by hand (GCTL now %x)"——Linux CORESOFTRESET 语义；present 前读回（⑥ d） |
| ⑥ | **六项采样** | (a) 单调时间线 usb_t0 起 [t+N.Ns] 前缀（present/Connected/armed/throw/give-up 各点）；(b) 双层 speed：**UsbFn 层（接口-8 +0x184）经 'usbf' 签名门后读，UsbDeviceDxe +0x1f8 放弃直读**（准备工作无法锚实例，H3 由镜像行覆盖）；(c) phys[2]/phys[3] state+maxpkt 同门读取，采样点 = present 前 / 首次主机进展后（first-host）/ 失败末端（throw/give-up）/ armed 后；(d) GCTL/DCTL/DSTS/DALEPENA 三时点；(e) raw 码移到失败窗口末端（一次/代，入队即 abort 收回——不再是 beat 0 的第二次独立提交）；(f) 探针采样已随零长探针退役，名义窗口与 wall time 由 [t+..] 时间线分开记录 |
| 终稿 8 | 前导错误粘性清单 | 镜像流扫描 + sticky（见 ④） |
| 终稿 10 | 缓冲分配拆开判错 | start_ex / RX 缓冲 / TX 缓冲三步各自打印返回码，RX 失败不拖 TX、TX 失败释放 RX（free_transfer_buffer），P2-5 落实 |
| 终稿 9 | 四检查点分开验收 | CP1 = usb_arm_rx 提交码（设备侧 log）；CP2 = 主机侧 probe24.py send() 成功行；CP3 = usb_pump 完成路由行（设备侧 log）；CP4 = usb_tx 完成（设备侧计数）+ 主机侧 reply 行。全部带 [t+..] 时间戳 |
| 附带修正 | F1/F3 家族 | usb_wait_pumped 的 stall 降级 200000→20000（20ms 切片，旧码 stall 出 10 倍时长）；usb_present 注释 5ms→50ms（stall 单位微秒） |

## 3. 构建（第 1 轮刷写件，v20 四件套）

| 件 | 值 |
|---|---|
| loader.efi | **`b8a2150be0d1a7db…`**（83,456 B；PAYLOAD_BASE=0xF4000000，entry RVA 0x2140 保持；零警告） |
| payload | `8dcde75be8f44725…`（23,393,800 B；kernel `17c905ec…`/kernel.ver/resident/ramdisk/usb/cmdline = **v18 payload 条目逐字节**——cmdline 即 v18 字节（sha `675e9178…`，471 字符，loader_return_after=180 + en0_addr=10.0.0.2，无 rec_*——USB 诊断与显示实验零混做） |
| graft | `udon-hakios-grafted-v20.img` **`05267a64c85a5a08…`**（192 MiB）+ report.json |
| FD / shim | `8924cb67…` / `108ce972…`（WSL 树件未动，零重建） |
| verify | `verify-udon-hakios-v20.py` **54/54**：v18 机制断言（present/armed/never-armed/re-throw/wake 保留）+ 新行为断言（镜像门/单消费者/常驻 RX/门/采样器/时间线/GCTL 手清/raw look 迁移/缓冲拆分）+ **PAYLOAD_BASE 双层钉**（本构建的新排布：`movz #0xF400,lsl#16` 与 XNUP magic `movk #0x5055,lsl#16` 相邻 ≤6 指令，钉 RVA 0x2380）+ cmdline=v18 字节 + rec_* 缺席断言 |
| 脚本 | patch-loader-v24.py / make-payload-v24.sh / make-graft-v24.sh / verify-udon-hakios-v20.py / run-verify-v24.sh / flash-bootb-v24.sh / **probe24.py**（协议层=fetch-recording-23 v2.1 原样复用：stage→upload、FAIL 无冒号、尾 OKAY 消费、getvar 活性检查、单一 Windows-libusb 所有者；每循环 getvar×4 + **oem log+upload（长度+内容校验，6 标记）** + oem recording；每次会话记录 libusb 版本/总线路径/速度/配置/端点参数）/ auto-logdump-24.sh |

## 4. Round 1 刷写与循环（Boot #38，预算 1/2；Round 2 未动用）

标准通道一次通过（02:45-02:50）：手机在安卓（22d9:2769 @2-2，adb SERIAL_REDACTED）→ WSL adb（ADB_SERVER_SOCKET=tcp:127.0.0.1:5037）`reboot bootloader` → d00d 上总线 → usbipd attach（警告照旧但 WSL fastboot 可见）→ `getvar product`=taro ✓ → graft sha `05267a64…` 复核 ✓ → `flash boot_b` Sending 4.971s / Writing 0.678s 全 OKAY → `set_active b` ✓ → 02:50 `reboot`。

**循环形态（probe24.log + 总线采样）——三循环全部同一武装形态**：

| 循环 | boot≈ | armed | 关键行（设备侧 log，[t+] 单调） |
|---|---|---|---|
| 1 | 02:45:50 | **gen 0 beat 1**（t+11.2 checkpoint-1，t+11.3 armed） | 镜像行（vendor 门 NOT FOUND / console 门 hooked）→ wake：**"soft reset did not settle in one second" + "cleared by hand (GCTL now 102000)"** → t+1.0 sample wake GCTL 102000 DCTL f00000 DSTS 0 DALEPENA 0 → t+6.0 start_ex + sample present GCTL 102001（bit11=0）→ t+6.2 首拒 7（beat 0，未枚举正常态）→ **t+8.9 sample first-host: DCTL 90f00000 DSTS 1277（HS）DALEPENA f（四条物理端点全使能=walk 确定）** → t+11.2 checkpoint-1（511B submit 0）→ armed gen 0 beat 1 → usb started → 内核 180s 会话（SpringBoard 活）→ 返回 → 服务窗 240s（探针每条命令推窗） |
| 2 | ~03:00 | **gen 0 beat 1**（t+11.2） | 同一形态逐行（含 cleared by hand、first-host DALEPENA f、cp1、armed beat 1）；内核 SpringBoard/backboardd init 全走 |
| 3 | ~03:08:40 | **gen 0 beat 1**（t+11.2） | 同一形态；内核 live log 370KB 经 USB 上传取回 |
| N（自由循环） | ~03:4x | **gen 0 beat 1** | logdump-v20 全文在案（§8）：与前三循环逐行同形态，loader_return_after 干净过期 |

主机侧四检查点（probe24.log，每循环数十回合）：

- **CP1（设备侧）**：`checkpoint-1: the standing receive is in (gen 2, 511 bytes, submit 0)` ——三循环逐字复现；
- **CP2（主机侧）**：`CP2-host: wrote N bytes on ep 0x01 (...): the host's write completed` ——数百次，零吞写（对照 wave23 的 24 连吞）；
- **CP3（设备侧）**：usb_pump 完成路由（usb_done_out；打印节流 ≤3 次 + 每 16 次——oem log 捕获在 run 相位取的头部段未含后期 CP3 行，最终 logdump 为准）；
- **CP4（两侧）**：设备侧 usb_tx 计数 + 主机侧 `CP4-host: reply OKAY/FAIL/DATA`——getvar 四问全答、**oem log+upload 长度+内容校验通过（216,995 B 首捕，6 标记中 5 中，`== XNULOADER/checkpoint-1/sample/the console mirror` 逐字在场）**；
- **受控重连恢复**：三循环 = 三次完整 detach→attach（reboot 链），每次枚举→武装→命令服务自动恢复；循环 3→4 过渡窗口的 `0000:0002` 死节点（03:15-03:16，settle 异常窗的一次注定枚举，wave22 结构性形态）**自愈**（03:17 起 xnuloader 重新在位）；
- 证据快照：`wave24-scripts/udon-oemlog-v20.txt`（cycle 1 首捕 216,995 B）、`-cycle1-postreturn.txt`、`-cycle2-key.txt`、`-cycle3-key.txt`（370,897 B）；probe24.log 全程。

**循环间观测（判决面）**：三次 boot 的拒绝码只有 beat 0 的一次 7 形（未枚举的正常态），**没有任何一次 0x8000000C 墙、没有任何 re-throw、没有任何"kept its host"**——与 v18 时代"武装是每周期一次的机会，未命中则错误码墙刷一整场"的时机依赖形态形成对照。

## 5. 判决表确定

| 判决表行 | 结果 |
|---|---|
| 真实接收提交成功，主机写成功，设备报告完成 | **命中（3/3 循环）**——"未配置"假设在修好的复位流程下不再出现；命令派发与 IN 应答同会话验证（getvar 四问 + 216KB 内容校验上传） |
| GCTL bit11 在 present 前仍为 1 → 优先处理复位流程 | **命中（历史形态实锤 + 修复后不再命中）**：三次 boot 的 wake 采样证明旧流程超时后 bit11 仍为 1（"did not settle" 行与 v16/v18/v19 历史 logdump 逐字同款）；显式清除后 present 采样 GCTL bit11=0，walk（DALEPENA f）三循环全确定 |
| 真实配置请求已到达 + speed 有效 + DEPSTARTCFG/walk 明确失败 → H1↑ | 未触发（墙未回来） |
| Usbfn speed=0 → H2↑ | 未触发（且 vendor speed 采样未激活——见 §6 边界） |
| Unknown USB Speed → H3↑ | 未触发（vendor 门镜像未通，该行不可见；但墙未回来，无需分辨） |
| 设备已配置但从未留下有效 OUT 接收 → 修接收生命周期 | 不适用（接收三循环都在位） |
| 设备侧持续推进但主机所有权切换后失效 | 不适用（单一 Windows-libusb 所有者全程，无 usbipd 手术） |

**根因判定（判决表外的新候选 H4，证据链）**：
1. 旧复位流程在**每一个历史 boot**都把 CORESOFTRESET（GCTL bit11）留成置位态（自清等待 1s 超时 → 旧码 break 继续；"did not settle" 行在 v16/v18/v19 logdump 逐字在案）；
2. 半复位的 core 上跑 vendor bring-up/ConnectDone/walk → 端点表状态间歇确定 → 间歇墙（v18 的"武装是每周期一次的机会"时机依赖形态的机理候选）；
3. 显式清位（Linux 语义）后 **3/3 boot 首试武装、墙零复现**；
4. 判决表"优先处理复位流程"行的设计意图（审阅 P1-1）正是此分支。

**结论：墙的根因按判决表落在复位流程分支（H4 = GCTL CORESOFTRESET 未显式解除）；H1/H2/H3 无需再分辨**。3/3 是强相关不是数学证明（历史也有过一次带 bit11 置位武装成功的 Boot #36），但"修复后墙零复现 + 历史逐 boot 实锤置位态"已够下一阶段做单变量收敛（如需再证：把显式清除单变量摘除做对照轮——不在本阶段预算内）。

## 6. 诚实边界（不夸大）

1. **vendor 门镜像未通**：gEfiHobListGuid 配置表在本 FD 不存在（Mu DxeCore 不发布，§1 附带事实 1）——镜像链第一步断，vendor 前导错误行（DEPSTARTCFG Fails 等）不在 log 里。本阶段它们不需要在场（墙零复现），但**若未来再遇墙，这条取证通道仍缺**；续作方案：HOB 直寻（内存扫描/BootShim 交接页）或 shim locator 的其它可达路径——均超出本阶段。
2. **vendor speed/phys 采样未激活**：`LocateProtocol(UsbfnIo)` 在 t+1.0 返回 NOT FOUND 且被一次性负缓存（"the UsbFn layer is not here" 行在 log）。机理未定案（FD 压缩节内晚解压 / FD 内构建的 GUID 与 ~/f12 副本不同皆可能）；'usbf' 签名门未被真实考验。寄存器采样（GCTL/DCTL/DSTS/DALEPENA）全程在场，判决已够。
3. **checkpoint-3 的专属打印行未在 dump 留存**：CP3（完成事件到达 loader）由命令执行的因果链 + 主机侧应答功能性证实（§8），但专属打印行被后续 boot 的日志覆盖（最终会话无主机命令）——四检查点的设备侧持久证据为 CP1（checkpoint-1 行，logdump 在案）+ CP4 设备侧计数；CP3 留在 probe24.log 的会话期行为记录。
4. 3/3 武装是相关不是证明；bit11 置位态的历史实锤（逐 boot "did not settle" 行）+ 修复后零复现，两件合起来够确定，但对照轮（摘除手清）未做。
5. cycle 1 的 first-host DSTS=0x1277：DSTS[1:0]=3（HS）+ DALEPENA=0xf —— 是"ConnectDone 重武装 walk 确定"的强指标，但 speed 解码未经 vendor 字段交叉验证（见边界 2），按寄存器语义如实记录。

## 7. 红线执行与预算

- 刷写：Round 1 = 本阶段（v20，Boot #38，额度 1/2）；**Round 2 未动用**（锁定分支的单变量修复无必要——修复已在 Round 1 内，墙未回来）。
- 只碰 boot_b ✓（flash 目标唯一）；FD `8924cb67`/shim `108ce972` 零重建 ✓（make-graft-v24.sh 双 pin 断言）；device-layer 只新增（payload-v24/grafted-v20 两件 + report.json）✓；wave24-scripts 只新增 ✓；loader.c delta 在 WSL，`~/loader.c.v19bbak` 全树备份、未动 git 状态 ✓；禁 git reset/checkout/stash/clean ✓。
- 诊断期单一 Windows-libusb 所有者 ✓（probe24.py 全程，无 usbipd attach/detach 手术；仅刷写通道用了一次标准 usbipd attach）。
- 网络：代理 7897 未用（全部本地证据）；WSL fastboot 全程 `sudo -n` ✓。
- 构建必须 PAYLOAD_BASE=0xF4000000 ✓（build.sh 环境变量 + verify 双层钉 0x2380 实测）。

## 8. logdump 判读与收尾

**logdump-v20.bin**（512MB，sha `455397e8a7cd519c`，04:00 拉取——Android 已由 ABL 自行回退到 slot a 回归，03:48:22 22d9:2769 在总线；无需人工 handback）：

- **新鲜度纪律 ✓**：分区头部从 byte 0 就是本阶段会话（第一行 = console-mirror 行），全分区仅**一个**会话头（`loader.efi size 14600` × 1 = 83,456 = 阶段 24 构建验明正身）；其后段（@656121 END OF LOG 之后，含 @751830 的旧 END OF LOG）为更早年代陈旧字节，按纪律不混读。
- **最终会话（自由循环的第 N 个）与前三循环逐行同形态**：mirror 行 → bring-up begins → **"soft reset did not settle in one second" + "cleared by hand (GCTL now 102000)"** → wake 采样（GCTL 102000）→ UsbFn 层未在位行 → start_ex (t+6.0) → present 采样（GCTL 102001，bit11=0）→ beat 0 首拒 7 → **first-host 采样（DCTL 90f00000 DSTS 1277 DALEPENA f）** → **checkpoint-1（gen 2, 511B, submit 0）** → armed 采样 → **armed at generation 0, beat 1** → usb: started → 内核会话（SpringBoard/backboardd/触摸事件全活）→ `--- loader_return_after expired ---` → 干净 END OF LOG。
- **判读落点**：自 由循环到最后一个会话（连同主机侧实录的 cycles 1-3）**每个观测到的 boot 都是 gen 0 beat 1 首试武装、墙零复现、零 re-throw、零 kept-its-host**——复活节拍完全消失。
- CP3 专项说明（诚实边界 3 的落实）：最终会话无主机命令（采样器已停）故无 CP3 行可 dump；CP3 的设备侧证据 = probe24 会话期的完成路由（主机侧 3,336 次 CP2 写全部得到命令执行与应答——完成事件到达是命令执行的唯一路径），专属打印行未能在 dump 留存（会话被后续 boot 覆盖）。

**收尾**：手机在安卓（slot a，boot_completed=1），boot_b 保持 v20 诊断件（未再刷写）；采样器与看护脚本全部退出；无任何手机侧遗留动作。

## 9. 后续工作清单

1. **判决表已确定**（§5）：根因 = 复位流程分支（H4）；Exp-2（若做）= 对照轮或巩固轮：单变量 = GCTL 显式清除（已在树内；其存在本身即修复）。四检查点验收通道已闭合，后续波不再以 armed 行为准。
2. **v20 在机**（boot_b，slot b active）：循环自续（每循环 armed + 内核 180s + 服务窗 240s）；probe24 采样器（150 分钟窗）与 auto-logdump-24.sh 在值守。
3. **镜像 vendor 门的续作面**（若未来需要 vendor 前导错误行）：gEfiHobListGuid 配置表路线已证死（Mu 不发布）；候选 = BootShim 交接页直寻 HOB / 修改 Mu DxeCore 发布 HOB 列表表（FD 重建——超出约定，需单独确认）。
4. **UsbFn locate 未在位**的续查面：压缩节解压时序 vs loader 执行点；FD 内实际构建的 GUID 与 ~/f12 副本比对（解包 FD 的 FFS）。
5. probe24.py 的 oem log 每回合覆盖问题已修（时间戳文件名）；运行中版已带。
