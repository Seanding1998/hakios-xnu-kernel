# 阶段 22 · 2026-11-08 · 主机第一次看到设备：泵送前移与主动上拉

> 2026-11-08 深夜 → 11-09 凌晨 · 阶段 22 执行记录全循环：vendor 反汇编定案（§1）→ v18 施工（§2）→ 构建/自检/自刷（§3）→ Boot #36 判决（§4-§5）→ 第 2 轮零刷写采样与 Windows 侧直连发现（§6）→ 终判与 v19 施工单（§7）→ 红线执行（§8）
> 任务书：`docs/waves/wave21_5-probe-verdict.md` §6 施工单四项；判据基线：`docs/research/f12-ep2-not-configured.md`

## 0. 一句话结论

**v0.4「达尔文」未宣告，但 阶段 22 拿下两项设备侧历史首胜并明确后续工作**：①**loader 相位的 gadget 首次被主机成功枚举**（v15 以来主机第一次"看见"我们的设备——Windows 总线出现 `18d1:d00d xnuloader` 且 Windows libusb 能 open+claim，设备处于 CONFIGURED 态）；②**bulk 对首次武装成功**（logdump 判别器逐字：`usb: bulk probe gen 0 beat 0: 8000000000000007` → **`usb: the bulk pair answered: armed at generation 0, beat 1`** → `usb: started` → 完整会话干净返回）——**F12 的"SET_CONFIG 武装链从未确定"之墙被 v18 打破，T2 可以确定**。结构性根因（指令级新证）：vendor 唯一拉高 pull-up 的 connect 路径只被泵送盲窗的平台回调驱动，而我们自己的 start_ex 开头会断开已有 connect 且从不重新拉高——**主机只被展示在"零泵送窗"，泵送窗里总线恒死**。剩余阻塞（精确化）：主机侧时序/管道——多数周期枚举仍中途夭折（死 devnode `0000:0002` 回现），usbipd→WSL 的 vhci 重放在 present 窗内从不完成（F9 慢性形态，probe18b 实手术实证），**重掷的显式 detach 本身就是刚成功枚举的杀手**（本报告首要嫌疑，v19 施工单第一项）；Windows 侧 libusb 直连通路已被打通（open+claim 成功 + getvar 写入落地），是 v19 的首选 host 通道。

## 1. vendor 反汇编定案（本轮最高价值产出，本地 ~/f12 只读，指令级）

**"主机不可见"的结构性根因 = pull-up 的断言者与泵送者永远不相遇**：

| 事实 | 指令级证据（UsbfnDwc3Dxe.efi，vaddr 基准） |
|---|---|
| vendor 唯一"拉高 pull-up"的代码 = connect 实现 fcn.000161e0 的收尾 | 0x1632c-0x1635c：读 DCTL(0xC704) → `orr w1, w8, 0x80000000`（RUN_STOP bit31）→ 写回 |
| connect 只被平台 bring-up 回调路径驱动（= 我们 usb_init_kick 信号的那个 GUID 事件的固件侧监听者） | fcn.0001609c（0x160c4-0x160d4：ctx[0x181] 非零时 `bl fcn.000161e0`，arg2=1 走 connect 分支）；该回调只在 boot 窗的 settle 阶段开火——**泵送为零**（loader 尚未 locate 协议、事件环未配置） |
| **我们自己的 start_ex 会断开已有 connect，且从不重新展示** | start_ex 的 [+0x90] = fcn.00012580：**开头** 0x125e0 `bl fcn.0001609c` → ctx[0x181] 非零 → fcn.000161e0(dev, **0**) = vendor StopController（fcn.00014b00 @0x14dbc `and w1, w0, 0x7fffffff` 清 RUN_STOP——真 detach）；**尾部** fcn.00016080 只复位状态字段（[0x184] speed=0 等），无任何 DCTL 写 |
| vendor 正常 fastboot 会话的形态（对照） | ABL 的会话走 fcn.000161e0 的 connect 路径：**config（fcn.00013868）+ RUN_STOP=1 紧挨着**（0x16320 → 0x1632c）——设备展示与配置在同一口气里，且 ABL 的 pump 紧随其后；我们的路径把这两步拆在了两个世界（config 在泵送窗，present 在盲窗） |

净效应（v15 以来每个 boot）：主机只在"零泵送窗"看到设备（SETUP 无人派发 → 描述符读超时 → Windows 死 devnode `0000:0002` 固化），而泵送存活的全部窗口（探针阶段/run/service）**总线是死的**（RUN_STOP=0，pull-up 不存在）。阶段 21.5 的"40+ 分钟恒 0000:0002"由此完整解释——**泵送稀疏只是半个病灶，"present 从未发生在泵送窗"是另外半个**。

## 2. 施工内容（v18 = 泵送前移 + 自主 present，`wave22-scripts/patch-loader-v18.py` 4 hunks，+52 行）

1. **usb_wait_pumped(tick, slices)**（新 helper）：20ms 一拍（periodic timer + wait_for_event 每拍派发固件事件队列/看门狗——settle 窗遗产保留），每拍 `handle_event` 泵送 + 记 Connected + ~1s 节拍 pet WDT。**只在 start_ex 成功（vendor 事件缓冲已配置）后使用**——缓冲未配置前 vendor 事件环指针不属于 loader，不碰（红线级保守）。
2. **usb_present()**（新 helper，platform_phk110 only，DCTL@0x0A600000+0xC704）：每次 start_ex 成功后 5ms 静默 + `DCTL |= bit31`——**vendor connect 自己的收尾单 bit 写**（fcn.000161e0 同款），现在落在泵送窗。整个会话期 pull-up 保持高（run/service 相位本就 ms 级泵送——主机随时可枚举）；每个 re-throw 的 start_ex 先真断开（detach→attach 成对）。
3. 探针 beat 间隙（5s）改 `usb_wait_pumped(tick, 250)`——v17b 形态是每间隙一次泵送（SETUP 落进间隙必死）。
4. re-throw 静默窗（25s）改 `usb_wait_pumped(tick, 1250)`——平台回调的 connect 恰落此窗，现在落点有泵送。

v17b 机制全保留：18 探针判别器（任何非零 = 未武装，Boot #34 校准的 7 形）、两次重掷、终判 ep0 独活。

## 3. 构建与自检（第 1 轮刷写件，v18 四件套，sha 只新增）

| 件 | 值 |
|---|---|
| loader.efi | `553289a417183a55…`（77,312 B，零警告，PAYLOAD_BASE 双层钉死：RVA 0x2190 movk 0x72AA0AB3 + 0x2198 movz 0x52BE8008 + 布局鲁棒双断言） |
| payload | `3f5036772f51367c…`（23,387,656 B；kernel `17c905ec…`/kernel.ver `afd473f5…`/resident/ramdisk/cmdline = v16 条目逐字节） |
| graft | `f49f3a45282f6691…`（`device-layer/udon-hakios-grafted-v18.img`，192 MiB）+ `udon-hakios-grafted-v18.report.json` |
| cmdline | = v17/v16 字节逐字节复用（`udon-hakios-cmdline-v17.bin`，`675e9178…` 文件件；loader_return_after=180） |
| FD / shim | `8924cb67…` / `108ce972…`（WSL 树件未动，零重建） |
| verify | **60/60**（`wave22-scripts/verify-udon-hakios-v18.py`：v17b 机制全保留断言 + 阶段 22 present 行新增断言 + 退休行缺席断言） |

配套新脚本（Windows device-layer 只新增）：`patch-loader-v18.py` / `make-payload-v18.sh` / `make-graft-v18.sh` / `mk-verify-v18.py` / `run-verify-v18.sh` / `auto-logdump-18.sh` / `watch18.sh`·`watch18b.sh` / `probe18.sh`·`probe18b.sh`·`probe18c.sh` / `probe18w.py` / `catch18b.sh` / `handback18.sh`（均在 `wave22-scripts/`）。

## 4. 第 1 轮自刷（Boot #36，22:33:50）

手机在安卓（22d9:2765 @2-2，adb SERIAL_REDACTED）→ 标准通道：`adb reboot bootloader` → d00d 上总线（Shared (forced) 自动生效）→ usbipd attach → `getvar product` = **taro** ✓ → graft sha `f49f3a45…` 复核 ✓ → `flash boot_b`（4.8s/0.6s 全 OKAY）→ `set_active b` ✓ → `reboot` @22:33:50。

**boot 后总线形态（watch18，20s 采样，22:35:40 起）**：22:36:20 `(blank) → 18d1:d00d xnuloader Shared`——**loader 相位枚举成功，历史首次**（v17b 两轮恒 `0000:0002`），且该标签**稳定保持至 22:42:04**（≈6 分钟 = 一个完整会话期）；此后每周期 present 一次（周期 ~7 分钟），部分窗口在中途被重掷的 detach 打断回 `0000:0002`。catch-and-run 22:35:40 起 200 探测零 serving（22:59:25 退出——其 pass 只覆盖到 ~22:59，见 §6 时序教训）。

## 5. Boot #36 判决（logdump-v18.bin，23:19 自动拉取，sha `78e3aecc34ab1170`，512MB）

**判别记录（新会话头，offset 455-800，逐字）**：

```
usb: dwc3 soft reset did not settle in one second        ← v16c 同款（非新病）
usb: dwc3 woken (phy suspend off + core soft reset)
usb: the platform is asked up; twenty-five quiet seconds before the first try
usb: the gadget is presented to the host (the pull-up is ours)     ← 阶段 22 present 行
usb: bulk probe gen 0 beat 0: 8000000000000007                     ← beat 0：未武装（7 形）
usb: the bulk pair answered: armed at generation 0, beat 1         ← ★beat 1：武装！
usb: started                                                        ← start_ex 首试即成，零重掷
payload entry 'loader.efi' size 12e00 ...                           ← 0x12e00 = 77,312 = v18 本尊
→ 内核会话：en0 @~69s 上线 + 10.0.0.2/30 → 1 帧发出 0 收到 → loader_return_after expired → 干净 END OF LOG
```

**判读**：
1. **T2 确定实锤**：present 后 ≤5s 内主机的 SET_CONFIG 到达、UsbFn ep0 状态机 case 9 walk 走完、DwcConfigureEP 置 state=1——probe 直接读到武装态。**F12 的墙（SET_CONFIG 武装链从未成功）被 v18 打破**；H1/H2/H3 在"主机可见"的前提下**不是恒阻塞**（至少一个会话全链通过）。
2. **零重掷**：`un-armed after generation`/`never armed`/`asked up again` 全 0 hits——武装成功 → 探针阶段一次通过 → 无 detach → 会话全程 pull-up 高（对应 22:36-22:42 的 6 分钟稳定标签）。
3. **新鲜度纪律**：本 dump 只含**一个** v18 会话（loader.efi size 0x12e00 验明正身）；dump 后段（@168212/@548686/@751830 等 END OF LOG + Stackshot）为更早年代陈旧字节（v10-v12 时代 loader_return_after=300 段），按 wave21_3 纪律不与本次混读。
4. **现场目视（三次，全部入档）**：~23:26 "还是在同样的错误循环"、~23:26+ "总是出现 usb 的错误代码"（现场两次读屏）——屏幕错误码墙持续刷 = 未武装周期探针码的可见形态（v18 的 present/重掷阶段 DwcPrepareURB 墙码经 UsbDeviceSend 包装后的 7 形，与 v16b 时代同族）；与"至少一个会话武装"并存 = **武装是时机依赖的（每周期一次机会，命中即整场稳定，未命中则错误码墙刷一整场）**。

## 6. 第 2 轮（零刷写，23:23:44 set_active b + reboot——刷写预算仍 1/2）与 Windows 侧直连发现

**动机**：logdump 证明 armed 会话存在，但 round-1 的 catch 在 22:59 就退出（200 pass 只覆盖 24 分钟，错过了 armed 会话期）——serving 从未在 armed 窗被采样。第 2 轮不刷写（镜像已在 boot_b），换持久采样。

**结果（三件）**：
1. **catch18b（1200 pass 持久采样，~8s/pass）**：660+ pass 零 serving。
2. **probe18b（23:40:42 窗口捕获）**：guardian 的真手术（usbipd.exe detach→attach）后 **WSL 侧三次 "device 18d1:d00d not found on this bus"**——usbipd attach 的 vhci 重放在 present 窗内从不产出设备（F9 慢性形态实证）。注意 probe18c 的 attach 调到了 Linux 版 usbipd（脚本 PATH 漂移，其"30s 不出现"判词作废），但 probe18b 的手术走的是 guardian 自己的 `_usbipd_exe()`（usbipd.exe 绝对路径），证据有效。
3. **probe18w（Windows 侧 libusb 直连，23:49-00:02）——本轮第二历史首胜**：
   - 23:57:02 `gadget visible on the WINDOWS bus`（pass 229，2s 采样捕到窗口）；
   - 23:57:02 **`open+claim ok (iface 0, ep 0x01/0x81) -- device already CONFIGURED`**——Windows libusb 打开成功 + **活动配置存在（= Windows 自己已发 SET_CONFIG 且设备处于 CONFIGURED 态）**。历史上的"Windows 侧 libusb 全盲"判词（wave8 时代）作废——当时设备从未枚举成功；枚举成功后 WinUSB/libusb 通路即通；
   - 23:57:11 `getvar:result -> NO RESPONSE (the write landed, nothing came back)`——**bulk OUT 写入成功落地**（= 端点收下了数据 = 该会话 armed 路径活性佐证），但无回——写点落在探针阶段（present 23:56:45 → 探针期至 ~23:57:40，服务相位尚未开始），且 ~23:57:36 gadget 离线（该周期随后夭折——**本周期 CONFIGURED 却未武装/未走到服务**：T2 确定的时机依赖性的另一面，与 logdump 单会话武装互为印证）。

**时序教训（阶段 19 吸收）**：round-1 catch 的退出时刻（22:59）早于 armed 会话（≥23:0x）；probe18 的手术落进代际 7 之后的空窗；probe18w 的 shot 落在探针阶段。**每一层"差一点"都是时序错位，不是能力缺失**——loader 侧（present/armed/服务相位）与 host 侧（枚举/打开/写入）今晚各自都被单独打通，但从未在同一窗口内对齐。

## 7. 终判与 v19 施工单

**判定：N1/N2/N3 未行使，v0.4「达尔文」不宣告。** 但 阶段 22 不是失败波：两项设备侧历史首胜 + 结构性根因指令级定案 + host 通路打通，剩余问题已从"未知墙"收敛为"已知时序对齐"问题。

**剩余阻塞的精确归因（按嫌疑排序）**：
1. **重掷的显式 detach 杀死刚成功的枚举**（首要嫌疑，本报告 §4 总线形态 + probe18w 23:57:36 离线的直接解释）：v18 的 re-throw 骑 start_ex 内部 StopController = 真 detach；Windows 的枚举/config 需要秒级稳定窗，重掷一确定就把刚建好的 devnode 赶成死节点。v18 拿到的"armed 会话"恰是**没有重掷**的会话（gen0 直接 armed）——旁证自洽。
2. **F9 管道（usbipd→WSL vhci 重放）在 present 窗内不完成**（probe18b 实证）：即使设备被 Windows 枚举，WSL 侧也拿不到。**Windows 侧 libusb 直连（probe18w 已验证 open+claim+写落地）可以整条绕开**——v19 的 E2E 通道首选。
3. **T2 确定的时机依赖**（CONFIGURED ≠ 必 armed）：walk 的三重前置（speed 字段/DEPSTARTCFG/表）在部分周期失败——失败码被 UsbDeviceSend 包装成 7，logdump 只见 7 形；v19 若要分辨 H1/H2，需在探针打印里加 raw 返回码透传（UsbFn->Transfer 的返回值在 UsbDeviceSend 包装前）或走 vendor 前导错误行屏摄。

**v19 施工单（按序）**：
1. **软化重掷**（loader.c 小改）：探针代际内若见到 DeviceStateChange Connected/Configured 事件（主机在场），**不重掷**——保持 present + 持续泵送 + 持续打拍（把 gen0 窗从 30s 拉长到 ~120s）；只在整窗无主机事件时才走重掷。预计 ~15 行。
2. **服务相位提前**：probe 阶段（gen0 起）就让 usb_poll_command 并行读命令（现在服务从 run 相位才开始）——把"写落进探针期"变成可服务。~10 行。
3. **E2E 通道换 Windows 直连**：probe18w 的 open+claim+transact 骨架 + wave21 loader_talk 的协议层（Windows python 已验证可跑 `cmd getvar`）→ netmode/ping/tunnel 全套 Windows 侧执行，彻底绕开 usbipd/WSL。零 loader 改动。
4. **usbipd 到达事件驱动 attach 替代轮询**（后续补充方向）：现在的 guardian 是"轮询 + 手术"；usbipd 有设备到达/共享状态事件面（或至少把 attach 时机绑到 Windows 枚举完成事件——`Get-PnpDevice`/WMI 事件/`pnputil` 触发），把 attach 落在"设备节点就绪"之后而不是 present 窗正中，避开重放枚举与设备自身时序的对撞。
5. **（可选，若 1-4 后 T2 仍间歇）**raw 码透传打印分辨 H1/H2。
6. **阶段 23.x 备选攻击面**（曾提出）：出画取证只需一次 serving 窗提取屏录——与 1-5 正交。

## 8. 红线执行与预算

- 只碰 boot_b ✓（唯一 flash 目标；userdata/darwin 未触碰）；禁 git reset/checkout/stash/clean ✓；Windows device-layer 只新增 ✓（全部新脚本在 wave22-scripts/）；禁重建 FD/BootShim ✓（FD `8924cb67`/shim `108ce972` 逐字节复用）。
- **刷写预算 1/2 轮已用**（v18 Boot #36）；第 2 轮零刷写（set_active b + reboot，非刷写操作）——预算仍余 1 轮留给 v19。
- 手机收尾 ✓：重启回安卓（手机若停在 fastboot 模式则手动重启处理启动的……用你的脚本通道恢复安卓"）——00:21:45 总线上出现 ABL fastboot 坐窗（d00d "Android"，user-initiated 交接点），脚本通道确认 `product: taro` → `set_active a` OKAY → `reboot` OKAY → 00:22:30 `22d9:2769 一加 Ace 2` 回总线；**00:2x 重启回安卓并确认（屏幕回到安卓，槽 a）**——收尾闭环完成，本轮无任何手机侧遗留动作。
- git add 不 commit ✓（见 STATUS 提交纪律）。
