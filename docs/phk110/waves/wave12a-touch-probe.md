# 阶段 12a · 2026-11-03 · 触摸探针第一轮：GENI 引擎被固件关闭的寄存器级确认

Date: 2026-11-03. Agent: 阶段 12a 执行记录（全循环：重打 → 构建 → 自刷 → 自取证 → 判定）。
任务书判定标准的三分支落位：**分支 2（probe 仍被阻）**——但阻塞点已从"cape GCC 时钟停摆"推进到
**两个全新且可一击修复的事实**：GENI 引擎本身活着（v10 的 s_ahb 告警不阻断 + 直接探活设计完全兑现），
FIFO 接口被 SE 固件关闭（`GENI_IF_DISABLE_RO=0x1`），而 bitbang 回退被驱动里**一处硬编码直呼**
（`v1_read` 直接调 `geni_transfer`，绕过 `spi_xfer`）完全屏蔽——修复为一行改动 + 会话窗已自动恢复。

## Result summary

**一句话结论**：✅ 构建全绿（v10 payload/镜像自检 **34/34**，条目级 cmp：kernel==v10 构建件、
cmdline==v9 仅翻 300→60、loader.efi/ramdisk/kernel.ver 逐字节=v9）→ ✅ 第一次刷写成功（Boot #17，
product=taro、刷前 sha 对包、OKAY）→ ✅ **零 panic 完整 60 s 会话**（`loader_return_after expired`
干净返回，cmdline 60 真机验证兑现）→ ✅ **v10 三项新行为全部真机验证**：s_ahb 停摆降级为告警（不再阻断）、
GENI 直接探活成功（`firmware 0x102` = SPI 协议，引擎可达且有时钟）、FIFO 被拒后按设计转 bitbang。
🟡 **TCM probe 未达**：固件版本行没打出来。根因两条（下详）：①SE 固件把 FIFO 接口关了
（`interface 0x1`），引擎路径死；②`v1_read()` 源码第 787 行**硬编码 `geni_transfer`** 没走
`spi_xfer` 抽象 → bitbang 回退在"读"方向从未被测试，每个 v1 探测轮空烧 ~1.47 s 引擎超时，
50 轮 ≈ 73.5 s > 60 s 会话窗 → 会话结束时驱动还卡在 v1 窗口里，连最终判决行都没来得及打。

**判定：v0.3「触感」四项 = 常驻 ✅ / 8 核 ✅ / 按键 ✅ / 触摸 probe ❌（差一行固件版本，阻塞点已定位到
一行代码 + 一个寄存器位）。**

| Artifact | Path | Size | SHA-256 |
| --- | --- | --- | --- |
| **本波镜像（现刷在 boot_b，Boot #17）** | `device-layer/udon-hakios-grafted-v10.img` | 201,326,592 B (192 MiB) | `a5bd42dca06c8398e1465a205f1b9bb06015b4ce69fc08b453bdc9e8f95b5bfb` |
| payload v10（kernel 换 v10 + cmdline 300→60） | `device-layer/udon-hakios-payload-v10.bin` | 14,944,584 B | `1e4abe33c68ad8237bfe0ff0a8567b1dfac1bb2ca5ab2184a85826e25bc681ac` |
| cmdline v10（374 B = v9 的 375 B 翻 300→60） | `device-layer/udon-hakios-cmdline-v10.bin` | 374 B | `81a56ccfb81699550b0ae30f457e03b2556af9df167c885a84e2907b829e572b` |
| 打包报告 | `device-layer/udon-hakios-grafted-v10.report.json` | — | fd `8924cb67…` / shim `108ce972…` / container `1f147ae1…` |
| 本波脚本（cmdline/repack/verify） | `wave12-scripts/`→ `wave12a-scripts/make-cmdline-v10.py`、`repack-payload-v10.py`、`verify-udon-hakios-v10.py` | — | 只新增，未动 v7/v9 任何文件 |
| Boot #17 logdump | `logdump-v10.bin`（仓库根） | 131,072 B | `c01cc7605a3a1a21a949bb91a93da14c0452610fbfae26edb037aab3099da41d` |
| **Boot #17 内核日志（判定证据）** | `intel/m3-boot1/b17-kernel-log.txt` | 24,771 B | `3c4b68e2b698a223a2192fee705a832354c9591863e6c4fbb70e4c9f19b9f4ed` |

未动构件（逐字节校验，红线遵守）：FD（`8924cb67…`，v4 起从未重建——本波从 WSL 构建输出原样取用）、
BootShim（`108ce972…`）、loader.efi（`66c6b342…`）、ramdisk（`4f72da61…`）、kernel.ver（`afd473f5…`）
——后三者经 repack 断言 + 验证脚本条目级 cmp 双重确认逐字节=v9=v6 原件。

---

## 1. 构建与自检（A 项）

1. `make-cmdline-v10.py`：从 v9 payload 的 cmdline 条目（375 B，sha `61534c3a…`，与 v7 文件逐字节
   相等）只翻 `loader_return_after=300 → 60`，脚本断言：翻转外逐字节相等、全部 21 个家族参数仍在、
   NUL 结尾、loader 预算 374-1+68=441 < 608。产出 374 B（`81a56ccf…`）。
   ⚠ 任务书里"cmdline 家族"的转述（`buttons_np1=1 buttons_core=0x0e000000 buttons_conf=… buttons_iob=…`）
   与 v9 payload 实际字节不符（实际是 `buttons_map=1 buttons_core=0xc400000 buttons_cnfg=0xc42d000
   buttons_obs=0xc440000`）；以 payload 文件为权威按"其余参数逐字节不动"执行。
2. `repack-payload-v10.py`：基座 = v9 payload（= Boot #16 真机验证字节），断言 loader.efi `66c6b342…` /
   ramdisk `4f72da61…` / kernel.ver `afd473f5…` / kernel `f56468c2…` 前缀，kernel → `hakios-kernel-v10.bin`
   （`75e2a481…`，交接件 sha 逐位核对）。回读 walk + 全条目 cmp 通过。
3. `package-udon-boot.py`（v4 波脚本原样）：FD 从 WSL
   `~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` 原样取用
   （sha `8924cb67…` = v4→v9 报告同值，禁重建条款遵守）。
4. `verify-udon-hakios-v10.py`：32 项基线 + 2 项新增（FD=`8924cb67` 钉死、cmdline=仅 token 翻转）
   = **ALL 34 CHECKS PASSED**。条目级：kernel==v10 构建件且 ≠v9；cmdline==本波文件且
   `replace(60→300)==v9 条目`；loader.efi/ramdisk/kernel.ver 逐字节==v9。

## 2. 刷写与取证全记录（Boot #17）

标准通道全程无异常：

```
20:2x  adb devices → SERIAL_REDACTED device, sys.boot_completed=1
       adb reboot bootloader → sleep 8
       usbipd list → 2-2  18d1:d00d  Android  Shared (forced)
       usbipd attach --wsl --busid 2-2
       WSL root: timeout 15 fastboot getvar product → taro ✓
       sha256sum（WSL 侧对包）= a5bd42dc… ✓
       fastboot flash boot_b → Sending OKAY 4.786s / Writing OKAY 0.618s
       fastboot set_active b → OKAY；fastboot reboot → OKAY
20:28  轮询 adb（20 s 间隔）
20:35:19 adb 出现；20:35:40 sys.boot_completed=1   ← 回安卓 ~7 分钟（快于 8 轮回退估算）
       su dd logdump → MSYS_NO_PATHCONV adb pull → extract-logdump.py → b17-kernel-log.txt
```

回安卓后 `ro.boot.slot_suffix = _a`（引导链自己切回 a 槽，boot_b 保留 v10 字节；无需 set_active a）。

## 3. 判定证据（b17-kernel-log.txt 原文逐行）

### 3.1 会话质量：零 panic、60 s 干净返回、8 核同起（基线全绿）

```
[   10.402451]: GenericARMPE: 7 of 7 processors are running
[   10.494099]: bsd_init: bsd_do_post - done
[   60.387860]: memory: free 6071, …
--- loader_return_after expired ---   （60 s 真机验证兑现，本波 cmdline 唯一改动生效）
```
按键链照常工作（ch 407/434、type/subtype 逐字吻合 v9，`1256 reads of the bus, 6 us each … 0 failed`）。

### 3.2 s3910 段（判定核心，t=10.49–21.24）

```
[   10.493980]: s3910: as found: votes 0x400287c0, clocks 0 0x80000002 0x80004220, rate cfg 0x100000 dfs 0x8020;
                pins cs/clk/mosi/miso cfg 0x1 0x1 0x1 0x1, reset 0x1/0, int 0x1/0, vdd 0x1/0
[   10.494751]: s3910: the analog supply on (ldoc3 at 3008 mV)
[   10.495135]: s3910: the I/O supply on (ldoh4 at 1800 mV)
[   10.800397]: s3910: the wrapper's s_ahb clock still reads halted (0x80000002); trying the engine anyway
[   10.800413]: s3910: serial engine: firmware 0x102, interface 0x1, parameters 0x20102864, source clock 19200000 Hz (select 0)
[   10.800425]: s3910: the bus at 10000000 Hz
[   10.800435]: s3910: the serial engine's FIFO interface is disabled; driving the pins by hand
[   11.002552]: s3910: SPI transfer of 9 bytes failed: status 0, sent 0, received 0     ← 打印为 [   10.1002552]：
[   12.466572]: s3910: SPI transfer of 9 bytes failed: status 0, sent 0, received 0        µs 字段 ≥1e6 失去补零，
[   13.938004]: …（共 8 条，~1.47 s 一条，至 t≈21.24 后静默）                              实际 t=10 s+1.002552 s
[   60.387860]: memory: free 6071, …（会话正常结束，s3910 无任何最终判决行）
```

### 3.3 新事实一（大好消息）：GENI 引擎活着，s_ahb 停摆与引擎可达性解耦成功

`serial engine: firmware 0x102` = `GENI_FW_REVISION_RO`(0x068)=0x102，bits[15:8]=**0x01=SPI 协议固件**
→ v10 的"s_ahb 告警不阻断 + 引擎直接探活"设计**真机兑现**：cape GCC 的 0x28008 分支停摆
（`clocks 0 0x80000002`，与 v9 一致）不妨碍引擎寄存器读写。`source clock 19200000 Hz (select 0)`
= DFSR bit0=0 走直配分支、RCG 切到 19.2 MHz 晶振并完成（`select 0` 未报 config 卡死）。
`parameters 0x20102864` = `SE_HW_PARAM_0`(0xe24)，bits[21:16]=0x10=16 词 FIFO 深度（≥4 合格）。

### 3.4 新事实二：FIFO 接口被 SE 固件关闭（引擎路径死因）

`interface 0x1` = `GENI_IF_DISABLE_RO`(0x064) bit0=1 → `geni_spi_init` 按设计拒绝：
"the serial engine's FIFO interface is disabled"。生产机 SE 的固件由启动链加载，常配成
DMA/GSI-only（mainline geni-se 驱动同有 FIFO/DMA 双路径）。失败形态自洽：`status 0, sent 0,
received 0` = 200 ms 截止期内 `GENI_M_IRQ_STATUS` 恒 0（无 M_CMD_DONE/无错误——命令根本没被执行），
TX FIFO status 读数 ≥ depth-1（sent 不了），RX 恒空。

### 3.5 新事实三（v10b 的那一行）：bitbang 回退被 `v1_read` 的硬编码直呼屏蔽

`wave12-scripts/hakios.s3910.c`（= WSL 树上构建源，双 sha `4dab7e0c…` 核对）：

- L787：`if (!geni_transfer(NULL, buf, V1_MIN_READ))` —— **`v1_read` 直接调 `geni_transfer`**，
  没走 `spi_xfer` 抽象（L436/L806/L837/L865/L874/L894/L912 都走 `spi_xfer`，唯独这一处是写
  bitbang 抽象前留下的）。于是 bitbang 分支的 `chip_identify` → v1 探测窗（50 轮 × sleep 20 ms）
  每轮照样打引擎：每次 `geni_transfer` 烧 200 ms 截止 + `geni_recover`（cancel/abort 各 2000×100 µs）
  ≈ **1.47 s/轮**（与 8 条 complaint 的间隔精确吻合）；
- 8 条 complaint = `geni_transfer` 里 `complaints++ < 8` 的上限，之后静默；
- **50 轮 × ~1.47 s ≈ 73.5 s > 60 s 会话窗** → `bring_up` 没能在会话内返回：既没有
  "the chip answers on pins driven by hand" 也没有 "no answer" 的 show_state ——
  驱动线程卡在 v1 窗口（约 t≈84 s 才会退出），**bitbang 的读方向从未被真机测试过**。
  bitbang 写方向同样未达（v1 窗口在最前）。

时序旁证：`[   10.1002552]` 的 µs 字段 1002552 ≥ 1e6 失去 6 位补零 → 实际 t=11.002552 s，
在 "driving the pins by hand"（t=10.800）之后——与"bitbang 分支里调引擎"完全自洽。

## 4. 判定与 v10b 修复单（最小改动，预期一行起效）

| # | 修复 | 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | **`geni_transfer` → `spi_xfer`** | `hakios.s3910.c:787`（v1_read 首读） | 一行。此后 bitbang 读路径真正真机验证；v1 窗恢复设计值 50×~20 ms ≈ 1 s，60 s 会话内必有判决行 |
| 2 | （可选护栏）bitbang 模式跳过/缩短 v1 被动窗 | `chip_identify` | 修 #1 后理论上不需要；若要双保险：`protocol==0 && spi_xfer!=geni_transfer` 时把 50 轮降为 5 轮 |
| 3 | （远期，不阻 v10b）GENI DMA/GSI 路径 | 新增 | 若 bitbang 也读 0（MISO 恒 0），引擎 FIFO 已死的情况下 DMA 是另一条真路径；工作量大，先看 bitbang 证据 |
| 4 | （排查备查）bitbang 若仍全零：钉住四个点 | — | 修复 #1 后若 `no answer` 的 show_state 显示 pin cfg 未变 GPIO（func≠0）或 MISO 仍 0，则查 TLMM mux/上拉与 CS/INT 接线；`as found` 行 pins cfg 0x1 复核 gpio_configure 编码（[1:0] pull / [5:2] func / [8:6] drive / [9] out） |

**v10b 预期日志（下一轮第一次刷写即验）**：`s3910: the chip answers on pins driven by hand` →
`s3910: TouchComm vN firmware: mode 0x01 (application), part number "…", build id …`（硬验收行）
→ app info → touch report config → 轮询线程启动。若 bitbang 真读 0，则 `no answer` 行自带
全套寄存器状态（votes/clocks/pins/reset/int/vdd）供第 4 步定位。

## 5. v0.3 状态操作清单（probe 达成后启用）

- **v0.3 四项**：常驻 ✅（Boot #13 起）/ 8 核 ✅（Boot #14 起）/ 按键 ✅（Boot #16 真机事件）/
  **触摸 probe ❌（本轮，差一行固件版本行；v10b 一行修复待第一次刷写）**。
- 点屏验证清单（v10b 刷写轮适用，同 wave12 报告 §8.3）：① set_active b 重启后**不按键**等内核起来
  （~10 s）；② 屏上滚动日志出现后指尖**点/滑几次（慢、间隔 ≥1 s）**；③ 60 s 定时返回后
  拉 logdump 取 `s3910: finger N at X, Y` 行。备选参数：坐标翻转 `touch_flip=1/2/3`；
  INT 不触发时 `touch_poll_us=2000`；总线速率 `touch_spi_hz=12000000/15000000`。

## 6. 红线自查

只刷 boot_b（flash boot_b + set_active b，其余分区零接触）；FD/BootShim 禁重建遵守（原字节取用）；
loader.c 零改动（loader.efi `66c6b342…` 原样）；Windows 侧只新增（wave12a-scripts/ 三脚本 +
device-layer 四件 + 根下 logdump-v10.bin + intel/m3-boot1/b17-kernel-log.txt）；无 git
reset/checkout/stash/clean；失败未重试刷写（阻塞点已在源码级完全定位，同字节重刷无信息增量）。
