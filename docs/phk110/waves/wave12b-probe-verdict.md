# Wave 12b — S3910 TCM probe 判定战（Boot #18，v10b 一行修复首刷）：软件链全通，断点移到芯片电气层

Date: 2026-11-03. Agent: Wave 12b 执行子代理（全循环：先验 → 一行修复 → 重编 → 重打 → 自检 →
自刷 ×2 → 自取证 → 判定）。
任务书判定标准落位：**FAIL（TCM probe 未达）**——`s3910: TouchComm vN firmware…` 硬验收行没有打出。
但本轮拿到的不是又一次"被阻"，而是**三层闭环证据**：

1. **阻塞 B（L787 硬编码）修复时序级证实**：v1 探测窗从 b17 的 ~73.5 s（8 条引擎超时投诉）缩到
   **1.07 s 零投诉零引擎调用**（50 轮 × ~20 ms 设计值精准落位）——`v1_read → spi_xfer →
   bitbang_transfer → TLMM 引脚` 这条调用链**真机端到端走通**（先验结论也兑现：bitbang 后端
   与 FIFO 禁用引擎完全解耦，读方向无需补齐）；
2. **bitbang 链 1–4 环寄存器级证实**：`no answer` 判决行自带的 `show_state` 全套寄存器显示
   CS/CLK/MOSI 已按 GPIO 输出驱动（cfg 0x280）、MISO GPIO 输入（cfg 0）、RESET 释放
   （0x2c3/3）、VDD 推高（0x200/3）、GCC 四项时钟投票全部在位（votes 0x443e87c0）；
3. **断链点收窄到第 5 环（芯片应答侧）**：v1 窗 50/50 轮无一 0xA5 帧 + v2 CMD_IDENTIFY
   6/6 次 `STATUS_PACKET_CORRUPTED`(0xfe)（CRC-6 首查即败）——MISO 返回的数据没有任何
   TouchComm 帧结构。软件侧已无一处可修，嫌疑全部移到**引脚极性/上拉偏置/供电实况**。

**判定：v0.3「触感」四项 = 常驻 ✅ / 8 核 ✅ / 按键 ✅ / 触摸 probe ❌（阻塞点从"软件路径"
正式换人到"芯片电气应答"，软件链全部闭环）。**

---

## 0. 刷写前提先验（任务书硬要求，刷前完成）

**问题**：`spi_xfer` 抽象在 FIFO 被禁（阻塞 A）的引擎上走什么后端？bitbang 读方向是否完整？

**答（读源码确证，`wave12-scripts/hakios.s3910.c` = WSL 构建源，sha `4dab7e0c…`）**：

- `spi_xfer` 是**函数指针**（L436），不是固定函数。`bring_up()` 的分支逻辑（L1437–1454）：
  `geni_spi_init()` 返回非 NULL problem（PHK110 上即 `GENI_IF_DISABLE_RO bit0=1`）→
  **跳过引擎分支**，直接 `spi_xfer = bitbang_transfer`（L1449）+ `bitbang_init()`（L1450）。
  bitbang 后端是纯 TLMM GPIO 位拍（goodix 式），**不碰 GENI 寄存器、不碰 GCC 时钟**——
  阻塞 A（FIFO 禁用）对它零影响。`clocks_on()` 的失败/告警也不阻断（v10 已降级）。
- **bitbang 读方向完整，无缺口需补**：`bitbang_transfer`（L603–621）逐字节 8 次全双工位拍
  （MOSI 置位 → CLK↑ → 采样 `gpio_get(MISO)`=GPIO_IO bit0 输入位 → CLK↓），`rx` 非空则
  `rx[i] = in`；`bitbang_init()`（L594–600）把 MISO16 配为 GPIO 输入、CS19/CLK18/MOSI17
  配为 GPIO 输出。CPOL=0/CPHA=0（MOSI 先于上升沿置位、上升沿采样），与引擎路径的
  mode 0 一致。
- **唯一直呼点就是阻塞 B 本尊**：全文件 `geni_transfer` 共 3 处——L542（定义）、L787
  （v1_read 首读，**唯一绕过抽象的调用**）、L1439（引擎分支赋值）。修复后剩余 2 处均为合法。
- **历史病灶确认**：v10 自己的 `fix5-v10.py` 第 3 步曾试图替换
  `'return geni_transfer(NULL, buf, V1_MIN_READ);'`，但源码实际是
  `'if (!geni_transfer(...)) {'` 形态——`str.replace` 不匹配**静默跳过**（无断言），
  其余 6 处替换全部命中。这解释了为什么 v10 上机后 bitbang 读方向从未被走到。

**判决：以"bitbang 路径端到端可达 v1_read"为前提的刷写条件成立**。调用链（修复后）：

```
hakios_s3910_init (touchscreen=1)
└─ kernel_thread s3910_thread (L1469)
   └─ bring_up (L1415)
      ├─ power_on: GPIO97(VDD 负载开关)↑ + RPMh ldoc3 3008 mV / ldoh4 1800 mV
      │            + GPIO20(REST, 低有效) 低→高                            [b18 t=10.495 实证]
      ├─ clocks_on: GCC 投票 SE4/CORE_2X/CORE/M_AHB/S_AHB → SE4 分支解锁 OK
      │            （cape s_ahb 0x80000002 只告警不阻断）                   [b18 t=10.801 实证]
      ├─ geni_spi_init(10 MHz): FW_REV 0x102 = SPI 协议固件 ✓；
      │            IF_DISABLE_RO(0x064) bit0=1 → 拒绝（阻塞 A）            [b18 t=10.801 实证]
      ├─ spi_xfer = bitbang_transfer (L1449)；bitbang_init() (L1450)        ← 后端选定
      │     CS19/CLK18/MOSI17 = GPIO 输出（cfg 0x280）；MISO16 = GPIO 输入（cfg 0）
      └─ chip_probe (L1343)
         └─ chip_identify (L1032)：protocol==0 → v1 被动窗 50 轮 × 20 ms
            └─ v1_read (L783)
               ├─ L787【v10b 修复行】spi_xfer(NULL, buf, 9)   ← 不再直呼 geni_transfer
               │    → bitbang_transfer (L603)：CS↓ → 每字节 8×[MOSI→CLK↑→采样 MISO→CLK↓] → CS↑
               │       物理引脚：TLMM GPIO 19(CS)/18(CLK)/17(MOSI)/16(MISO)，qup4 四线的 GPIO func=0
               └─ (长消息续读) L806 spi_xfer(NULL, buf+9, …) → bitbang_transfer
```

## 1. 修复与构建（M1）

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| 修复 | `wave12b-scripts/fix1-spi-xfer.py` → WSL 树 `devices/phk110/drivers/input/hakios.s3910.c` L787 `geni_transfer`→`spi_xfer`（断言唯一性——针对 fix5 的静默跳过病根） | 源 sha `4dab7e0c…`→`6fef5d80…`；修后 `geni_transfer` 仅剩 L542 定义 + L1439 引擎赋值 |
| 重编 | `make kernel`（增量；`sync-drivers.sh` 自动把新源拷入 xnu 树，`hakios.s3910.o` 20:55 重编） | `hakios-kernel`（Mach-O）14,859,856 B，sha `e56f989b…`（≠v10 `75e2a481…`）；exit 2 = 已知 kext symbol-set 检查，make-kernel 判定接受 |
| 交接件 | `device-layer/hakios-kernel-v10b.bin`（只新增） | sha `e56f989ba7546822bd78ef6aed369af1775cfa130fa35ca14ad3d1b5649427da` |
| 重打 | `wave12b-scripts/repack-payload-v10b.py`：基座 = v9 payload；kernel→v10b；**cmdline = v10 字节逐字节不动**（`loader_return_after=60 touchscreen=1 buttons=1 small_cores_after=0`）；loader.efi/ramdisk/kernel.ver 断言 = v9/v6 原件 | `udon-hakios-payload-v10b.bin` 14,944,552 B，sha `4cf40c41…`；五条目回读 cmp 全过 |
| 打包 | `wave4-scripts/package-udon-boot.py`（原样）+ FD（WSL 构建输出原样取字节 `8924cb67…`）+ shim `108ce972…` | `udon-hakios-grafted-v10b.img` 192 MiB，sha `d08e5481…` + report.json `d3a91f32…` |
| 自检 | `wave12b-scripts/verify-udon-hakios-v10b.py`（v10 的 34 项 + v10b 条目级升级：kernel==v10b 件且 ≠v9≠v10、cmdline==v10 字节==v9 翻 300→60） | **ALL 35 CHECKS PASSED**（FD `8924cb67` 钉死；loader.efi `66c6b342`/ramdisk `4f72da61`/kernel.ver `afd473f5` 未动条目 cmp 逐字节过） |

## 2. 刷写与取证全记录（Boot #18，两段式）

**第一段（20:59–21:08）——首刷成功，循环被外部打断**：

```
20:5x  adb devices → SERIAL_REDACTED device, sys.boot_completed=1（安卓在线）
       adb reboot bootloader → sleep 8 → usbipd list → 2-2 18d1:d00d Shared (forced)
       usbipd attach --wsl --busid 2-2
       WSL root: fastboot getvar product → taro ✓
       sha256sum（WSL 侧）= d08e5481… ✓
       fastboot flash boot_b → Sending OKAY 4.812s / Writing OKAY 0.522s
       fastboot set_active b → OKAY；fastboot reboot → OKAY（Boot #18 启动）
21:0x  【主代理介入】用户嫌兜底循环慢，主代理 set_active a + reboot 切回安卓（打断于 ~t=24 s，
       当轮会话未到 60 s 收尾写）；adb 21:08:43 恢复
       拉 logdump 考古：内容 = 被打断轮的流式缓冲（loader 心跳 12 条至 t=24 s，kernel size
       e2be50 = v10b 字节已上机）+ 上一轮完整收尾写残尾（双 == END OF LOG ==）——无完整内核日志段
```

**第二段（21:14–21:25）——干净完整循环**（主代理更正消息确认使命不变、权限完整后执行）：

```
21:14  adb reboot bootloader → usbipd attach（重枚举必重 attach，busid 2-2）
       getvar product → taro ✓（boot_b 字节已验证 = v10b，同字节无重刷信息增量，故不重刷）
       fastboot set_active b → OKAY；fastboot reboot → OKAY
       8 轮 × 60 s 兜底自然走完（无人工干预）
21:25:05 adb 恢复, sys.boot_completed=1（引导链自发回 slot a；boot_b 保留 v10b 字节）
       su dd logdump（bs=4096 count=32 = 128 KB）→ MSYS_NO_PATHCONV adb pull
       → extract-logdump.py → intel/m3-boot1/b18-kernel-log.txt（== KERNEL LOG == 6383,
         == END OF LOG == 30712, 24,345 B 完整）
```

上机身份三重确认（loader 日志）：`payload entry 'kernel' size e2be50`（hex = 14,859,856 =
**v10b 构建件**）、`cmdline: 450 of 607` 全参数串逐字 = 设计值（`loader_return_after=60
small_cores_after=0 touchscreen=1 buttons=1 …`）、ramdisk/kernel.ver 尺寸 = v6 原件。

## 3. 判定证据（b18-kernel-log.txt 原文）

### 3.1 会话质量（基线全绿）

```
[   10.403691]: GenericARMPE: 7 of 7 processors are running          ← 8 核同起
launchd stub alive: t=10s … t=50s（5 条心跳全在）
[   60.390676]: memory: free 6071, …
--- loader_return_after expired ---                                  ← 60 s 干净返回
```

零 panic（`panic_trace` 行为常规 trace 使能噪音，与 b17 同）；按键链照常
（`1256 reads of the bus, 6 us each … 1 failed`）。本轮 v10b 内核对会话零影响。

### 3.2 s3910 判定段（t=10.495–11.869，全程仅 1.37 s，判定核心原文）

```
[   10.495433]: s3910: as found: votes 0x400287c0, clocks 0 0x80000002 0x80004220, rate cfg 0x100000 dfs 0x8020;
                pins cs/clk/mosi/miso cfg 0x1 0x1 0x1 0x1, reset 0x1/0, int 0x1/0, vdd 0x1/0
[   10.496144]: s3910: the analog supply on (ldoc3 at 3008 mV)
[   10.496549]: s3910: the I/O supply on (ldoh4 at 1800 mV)
[   10.801804]: s3910: the wrapper's s_ahb clock still reads halted (0x80000002); trying the engine anyway
[   10.801820]: s3910: serial engine: firmware 0x102, interface 0x1, parameters 0x20102864, source clock 19200000 Hz (select 0)
[   10.801829]: s3910: the bus at 10000000 Hz
[   10.801837]: s3910: the serial engine's FIFO interface is disabled; driving the pins by hand
[   11.868702]: s3910: command 0x2: no usable answer after six tries (last status 0xfe)
[   11.868725]: s3910: no answer: votes 0x443e87c0, clocks 0 0x80000002 0x4220, rate cfg 0x100001 dfs 0x8020;
                pins cs/clk/mosi/miso cfg 0x280 0x280 0x280 0, reset 0x2c3/3, int 0/1, vdd 0x200/3
[   11.868740]: s3910: no touch screen
```

### 3.3 闭环一：阻塞 B 修复时序级证实（本轮最重要软件结论）

| 指标 | b17（v10，直呼引擎） | b18（v10b，走 spi_xfer） |
| --- | --- | --- |
| v1 窗起点 | t=10.80（"driving the pins by hand"后） | t=10.801837（同点） |
| v1 窗+判决行 | **未出现**（预计 ~t=84 > 60 s 会话） | **t=11.868702**（窗长 **1.067 s**） |
| 引擎超时投诉 | 8 条 `SPI transfer of 9 bytes failed: status 0, sent 0, received 0`（~1.47 s/条） | **0 条** |
| 50 轮成本 | 50 × ~1.47 s ≈ 73.5 s | 50 × (位拍 ~µs + sleep 20 ms) ≈ 1.07 s |

50 轮若仍有一轮碰引擎（每次 ≥200 ms 截止），1.07 s 装不下 → **每一轮读都走了 bitbang**。
`v1_read → spi_xfer → bitbang_transfer → 引脚` 链路真机端到端走通，与 §0 先验互证。
判决行能打出，正是 wave12a 修复单 #1 的直接预期（"v1 窗恢复设计值…60 s 会话内必有判决行"）。

### 3.4 闭环二：bitbang 链 1–4 环寄存器级证实（`no answer` 行逐位解码）

TLMM `GPIO_CFG` 位域 = [1:0] pull / [5:2] func / [8:6] drive(=(n+1)×2 mA) / [9] out；`GPIO_IO` bit0=in bit1=out。

| 信号 | cfg | 解码 | 预期（bitbang_init/power_on） | 判 |
| --- | --- | --- | --- | --- |
| CS 19 | 0x280 | out，drive 6 mA，func 0(GPIO)，pull none | `gpio_output(CS, true, PULL_NONE, 6)` | ✓ |
| CLK 18 | 0x280 | out，drive 6 mA，GPIO | `gpio_output(CLK, false, …)` | ✓ |
| MOSI 17 | 0x280 | out，drive 6 mA，GPIO | `gpio_output(MOSI, false, …)` | ✓ |
| MISO 16 | 0x0 | 输入，func 0，pull none，drive 0 | `gpio_configure(MISO, 0, PULL_NONE, 2, false)` | ✓ |
| RESET 20 | 0x2c3 | out，drive 8 mA，pull up | `gpio_output(RESET, true, PULL_UP, 8)`（释放=高） | ✓ |
| INT 21 | 0x0 | 输入 pull none；IO=1 读高 | `gpio_configure(INT, 0, PULL_NONE, 2, false)` | ✓ |
| VDD 97 | 0x200 | out，drive 2 mA；IO=3 推高 | `gpio_output(PIN_VDD, true, PULL_NONE, 2)` | ✓ |

votes `0x443e87c0` = as-found `0x400287c0` + QUP1_SE4(0x04000000) + CORE_2X/CORE/M_AHB/S_AHB
(0x003C0000)——时钟投票全链在位。rate cfg 0x100001（引擎被配到 19.2 MHz 晶振后 bit0 更新）。
**链 1（供电/复位）、链 2（时钟决策）、链 3（后端选定）、链 4（引脚配置/驱动）全部证实可达。**

### 3.5 断链第 5 环：MISO 数据返回侧（FAIL 的确切失败点）

- **v1 窗 50/50 轮无一 `0xA5`**：每轮 9 字节读的首字节都 ≠ V1_MARKER → `v1_read` 全 false
  （bitbang 正常返回 true——它只管拍线；是读回的数据无帧）；
- **v2 兜底 CMD_IDENTIFY(0x2) 6/6 次 `STATUS_PACKET_CORRUPTED`**：`tcm_crc6` 对 4 字节头
  首查即败（若 MISO 返回有效 TCM2 帧，CRC-6 应通过）→ status 0xfe 六连 → 放弃；
- 两窗自洽 ⇒ **MISO 返回的字节流没有任何 TouchComm 结构**。0x00（钳低）、0xFF（钳高）、
  悬空噪声、极性反接、位错位（sample shift）五种情形都产生同一日志形态——**当前日志无原始
  字节打印，无法直接区分**（b18 未打 v1 读回值，这是取证盲点，v10c 第一项即补）；
- **电平线索（as-found vs no-answer 对照）**：
  - as-found：`reset 0x1/0`（上拉 + **读低**）、`int 0x1/0`（上拉 + **读低**）——上拉悬空线
    应读高，读低 = 有东西把这两根线钳在低：最自洽的解释是**芯片 I/O 域在驱动两线为低**
    （芯片被按在复位里 + INT 声明），即上电前芯片 VDDIO 已有电（板级常态供电）；
  - no-answer：`reset 0x2c3/3`（推高释放）、`int 0/1`（no-pull 读高）——释放复位后 INT 读高
    与"芯片活着且无报告"和"芯片 I/O 无输出"两种世界都兼容，不能定案；
  - **引脚极性/上拉嫌疑正式挂账**（任务书 FAIL 条款）：MISO no-pull 悬空采样是第一嫌疑；
    as-found 的上拉读低行为说明该板 I/O 域的电平基线与驱动假设（PULL_NONE 可用）未必相符。

## 4. 判定结论与 v10c 修复单

**判定：FAIL**（本轮唯一硬验收 `s3910: TouchComm vN firmware…` 未出现）。失败点 =
bitbang 链第 5 环（芯片应答/MISO 数据返回），软件路径（链 1–4）已全部寄存器级排除。
v0.3 状态：常驻 ✅ / 8 核 ✅ / 按键 ✅ / 触摸 probe ❌（阻塞点定性精度 = 引脚级）。

| # | 动作 | 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | **bitbang 原始字节取证**：v1 窗首 3 轮 + 每第 10 轮打印读回的 9 字节 hex | `v1_read`/`chip_identify` | 一眼区分 0x00/0xFF/噪声/伪帧；这是下一步一切判断的前提 |
| 2 | **MISO 上拉重试**：boot-arg `touch_miso_pull=1`（PULL_UP）或直接改 `bitbang_init` 配 PULL_UP 探一轮 | `bitbang_init` | as-found 的"上拉读低"暗示该板 I/O 域基线偏；no-pull 悬空采样是第一嫌疑 |
| 3 | **RESET 极性实验**：boot-arg `touch_reset_active_high=1` 时反转 | `power_on` | 防极性反接（树里说低有效，但 cape FDT 复核 + 实验兜底） |
| 4 | **位拍节奏**：boot-arg `touch_bitbang_us=N`（默认 0），CLK 半周期插 N µs | `bitbang_transfer` | 当前半周期 ≈ 1 次 MMIO 写（几十 ns）；芯片若按 100 kHz 级慢速启动应答会跟不上 |
| 5 | （若 1–4 显示恒 0x00/0xFF）**GPIO16 mux 复核**：live FDT qup4 四线 func=1 vs GPIO func=0 的 pad 环路（芯片侧 MISO 是否真连此 pad） | 文档/实验 | 引脚映射最终确认 |
| 6 | （远期备选，不阻 v10c）GENI DMA/GSI 描述符路径 | 新增 | 引擎固件活着（0x102）且 FIFO 被禁——量产机 DMA-only 常态下 DMA 路径可能可写；工作量大，bitbang 证据优先 |

## 5. 红线自查

只刷 boot_b（两次循环均 `flash boot_b`/`set_active b`，其余分区零接触；第一段后引导链与主代理
`set_active a` 均未触碰 boot_b 字节——第二段 loader 日志 kernel size e2be50 复证）；FD/BootShim
禁重建遵守（FD 从 WSL 构建输出原样取字节 `8924cb67…`，shim `108ce972…` 原件）；loader.c 零改动
（loader.efi `66c6b342…` 原样）；Windows device-layer 只新增（hakios-kernel-v10b.bin、
payload-v10b、img-v10b、report.json 四件）；树内改动 = 一行修复（devices/phk110 驱动源，经
sync-drivers 入树），无 git reset/checkout/stash/clean，无 commit；失败未达 2 次重试上限
（第一次取证不完整系外部打断，非刷写失败；第二段一次成功）。

## 6. 交付物清单（全部只新增）

| Artifact | Path | Size | SHA-256 |
| --- | --- | --- | --- |
| **本波镜像（现刷在 boot_b，Boot #18）** | `device-layer/udon-hakios-grafted-v10b.img` | 201,326,592 B (192 MiB) | `d08e54819d60596bdfad3426f31282a2a8e36305f4d92b0121c2e376bd8ba3eb` |
| payload v10b（仅 kernel 换 v10b，cmdline = v10 字节） | `device-layer/udon-hakios-payload-v10b.bin` | 14,944,552 B | `4cf40c41e60dd8c9818af82d1ba012f4d0ff6f09bfe4b846a803faa8ad68d846` |
| 内核交接件 v10b（= 上机件） | `device-layer/hakios-kernel-v10b.bin` | 14,859,856 B | `e56f989ba7546822bd78ef6aed369af1775cfa130fa35ca14ad3d1b5649427da` |
| 打包报告 | `device-layer/udon-hakios-grafted-v10b.report.json` | — | `d3a91f3261863ccbb13f7230b059dbe9c4fdf2eec9b126893afabec48d5938bd` |
| 本波脚本（fix/repack/verify + 修复后源码快照） | `wave12b-scripts/{fix1-spi-xfer.py, repack-payload-v10b.py, verify-udon-hakios-v10b.py, hakios.s3910.v10b.c}` | — | 源码快照 `6fef5d80…`；只新增，未动 v7/v10/v12a 任何文件 |
| Boot #18 logdump | `logdump-v10b.bin`（仓库根） | 131,072 B | `6ea82f1ead1f9eb71eec4de01ebbb06dfc0e080e36eae3671788ae390f93e2bd` |
| **Boot #18 内核日志（判定证据）** | `intel/m3-boot1/b18-kernel-log.txt` | 24,345 B | `44b4ac1d2576be7332f6de1d1da85e515ed2d9428c3213bbf049f88b78fcf9c9`（分段原文见 §3） |
