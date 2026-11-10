# TouchComm over SPI 的外部先例与已知问题调研

Date: 2026-11-03. 纯调研（WebFetch/WebSearch + 本地源码 + OnePlusOSS 官方仓库），未触碰手机/WSL/构建树。
设备：OnePlus Ace 2（PHK110，OPPO 项目号 22803，内部代号 **udon**，SM8475/"taro-cape"），触摸 IC = Synaptics S3910，TouchComm v1 over SPI（QUPv3 SE4）。

**结论先行（一行版）**：S3910 是 **TCM v1 固件**（b20 真机已实证 identify: version=1, mode=0x01 application, part "S3910PA0B0-2-15.2"）；电气链（GPIO 映射/SPI mode 0/RESET 低有效/供电/时钟）经三方交叉验证**全部正确**；当前唯一失败点 = **v1 identify 包跨事务续读**，而真机读方向与全部三个 vendor 参考实现的唯一系统性差异是：**vendor 读事务时 MOSI 打 0xFF，我们打 0x00**，外加 CS 无 setup/hold 延迟。

---

## 0. 误诊修正（置顶）

### 0.1 "as-found INT/RESET 上拉读低 = 有东西钳低" → **误诊，是芯片断电的正常表现**

b17/b18 的 as-found 行：`reset 0x1/0, int 0x1/0`（TLMM 上拉 + 读低）。当时记录推断"最自洽的解释是芯片 I/O 域在驱动两线为低"。

**修正**：as-found 时 vdd 行是 `vdd 0x1/0`——**ldoc3/ldoh4/GPIO97 都还没上**（本驱动自己的 as-found 快照，b20 log t=10.507）。一片双轨（VDD 模拟 3.0V + VCC IO 1.8V）都断电的 CMOS 器件，其 pad 会通过 ESD 二极管把挂在它上面的线钳到 ~0.3-0.7V，TLMM 内部上拉读出低**完全正常**。这不是"芯片把线按低"，是"芯片没电"。旁证：

- b20 上电+复位后：`reset 0x2c3/3`（推高）、`int 0/1`（读高）——INT idle = 高，与 vendor 定义一致（见 0.3）；
- b20 实验 4（RESET 极性反转）后全窗读 FF = 芯片按死在复位里 → RESET 确是低有效（vendor DT `reset-on-state=0` + `reset-gpio <&tlmm 20 0x1>`，见 §3）；
- b20 实验 5（GPIO97 拉低）芯片**依然活着** → 该负载开关不门控触摸轨道（或默认导通），轨道本身（L3C/L4H）已够。GPIO97 语义值得后续复核，但不阻塞。

### 0.2 "MISO 无 TCM 结构 = 芯片电气层死" → **已推翻（b20）**：芯片活着，而且在说话

b20（v10c，Boot #20）baseline 一轮内真机日志（`intel/m3-boot1/b20-kernel-log.txt:342-348`）：

```
loopback probe, reset released, rx: a5 10 ff ff ff ff ff ff ff
v1 window, read 1 raw: a5 10 1c 00 01 01 53 33 39      ← [A5][REPORT_IDENTIFY=0x10][len=0x001c=28][ver=01][mode=01]['S','3','9']
v1 window, read 2 raw: a5 03 31 30 50 41 30 42 30      ← [A5][STATUS_CONTINUED_READ=0x03]['1','0','P','A','0','B','0']
v1 window, read 3 raw: a5 03 2d 31 35 2e 32 00 9e      ← 续读 "-15.2..."
v1 window, read 10..50 raw: a5 00 00 00 5a 5a 5a 5a 5a ← idle 帧 [A5][STATUS_IDLE=0x00][len=0][padding 0x5A]
```

part number 拼出 **"S3910PA0B0-2-15.2"**，mode=0x01（application firmware）。芯片活着、固件完好、TCM **v1**。b18 的 50/50 无 0xA5 与 b20 的"read 1 即中"之间的差异来源 = v10c 在窗口前插入的 loopback probe（其中包含一次完整的 reset assert→release 脉冲，~82 ms 窗）；即**芯片需要的可能只是"上电稳定后的一次干净复位脉冲"**——b18 首次释放复位的时序未让固件起来（见 §5 根因 3 备注）。

### 0.3 "INT 低电平是异常" → **不是**：本机 ATTN 声明态就是低

vendor 权威定义（OnePlusOSS udon-22803 devicetree + Syna TCM 绑定文档）：

- `synaptics,irq-gpio = <&tlmm 21 0x2008>`；`interrupts = <21 0x2008>` —— 0x2008 低 4 位 = 0x8 = **IRQ_TYPE_LEVEL_LOW**（0x2000 是欧加家族 DT 惯用的附加位）；
- `synaptics,irq-on-state = <0>` —— Syna 官方绑定文档明确定义 "active state of interrupt signal"，即 **ATTN 声明 = 低，idle = 高**；
- HBP 驱动 ISR 防抖检查同样按此语义：`if (gpio_get_value(attn->irq_gpio) != attn->irq_on_state) ... spurious`（attentions 不在声明态就当假中断丢弃）。

所以：芯片上电且**有报告待取**时 INT 读低是**正常**；只有"芯片上电后 INT 恒低且读不出数据"或"上电后恒低"才异常。b20 上电后 INT 读高（无待取报告或固件未起），不构成任何异常证据。

### 0.4 "STATUS_PACKET_CORRUPTED(0xfe) = 线路损坏" → **部分误诊**：0xfe 是 host 自造状态；且本机根本不说 v2

- `0xfe` **不是设备返回码**。Syna core（synaptics_touchcom_core_dev.h，即本仓 intel/wave1b-scripts 那份）枚举注释原文："0xfe: **self-defined** status for a corrupted packet."——它是 host 在 CRC-6/CRC-16 校验失败时自己填的状态。
- b20 的 v2 回退读到的 4 字节头是 `a5 0f 00 00` = **v1 帧** `[A5][STATUS_ERROR=0x0f][len=0]`——STATUS_ERROR 在 v1 里是"generic communication error, probably incorrect payload"。即芯片（v1 固件）收到了我们 v2 框架的 CMD_IDENTIFY 字节、按 v1 语义解析后**回了 STATUS_ERROR**，我们的 v2 CRC-6 检查对 v1 帧必然失败 → 6/6 次 0xfe。**这是"拿 v2 协议问 v1 芯片"的必然结果，不是电气故障。** v2 fallback 在本机上应视为死路（或改为收到 `a5` 首字节时立即转 v1 解析）。

---

## 1. TCM 协议深挖（按任务书问题逐条）

### 1.1 SPI mode（CPOL/CPHA）

**Mode 0（CPOL=0, CPHA=0）**，两处独立权威：

- 本机 DT（enabled 的 `synaptics,tcm-spi-hbp` 节点）：`synaptics,spi-mode = <0>`（udon_22803_extra_config.dtsi L236，见 §3）；Syna 平台驱动按 DT 值映射 `SPI_MODE_0..3`（syna_tcm2_platform_spi.c L1319-1328：`case 0: spi->mode = SPI_MODE_0`）。
- OPPO S3910 v1 驱动硬编码：`spi->mode = SPI_MODE_0; spi->bits_per_word = 8; spi->max_speed_hz = 15 * 1000 * 1000;`（synaptics_tcm_S3910.c L8090-8092）。

我们的 bitbang 是 CPOL=0/CPHA=0（MOSI 先于上升沿、上升沿采样、下降沿翻转）——**一致，无需改**。

### 1.2 最高时钟

- 本机 DT：HBP 节点 `spi-max-frequency = <15000000>`（15 MHz）；OPPO 节点 12 MHz（disabled）；OPPO S3910 驱动 probe 也是 15 MHz。
- 参考：Pixel 系 Syna TCM 驱动同族亦为 10-15 MHz 量级。
- 我们 bitbang 半周期 ≈ 1 次 MMIO 写（~几十 ns → 等效 ~8-16 MHz），**不超速**；且 b20 实验 2/3 已用 5 µs 半周期（~100 kHz）扫过，续读失败模式**完全不变**——**速率因素已被真机排除**。

### 1.3 CS 帧格式

- **每个事务一次 CS↓…CS↑**；TCM 把 CS 边沿当帧界：**v1 的每个读事务都以 [A5][code] 重新开帧**（b20 read 2/3 实证 [A5][03]），v2 每 packet 亦独立 CS 帧。
- CS idle = 高：udon DT `qupv3_se4_spi_cs_sleep` 显式 `output-high`（udon_22803_tp_config.dtsi L287-299）。
- **CS 时序参数（重要）**：vendor 引擎路径对 Syna 有 µs 级建立/保持要求——Syna 平台驱动的 MTK 配置段明确 `cs_setuptime = 5000, cs_holdtime = 3000`（ns：5 µs setup / 3 µs hold，syna_tcm2_platform_spi.c 末尾 `st_spi_ctrdata`）；Qualcomm GENI 引擎自身也有 CS setup/hold 可编程项。**我们 bitbang 的 CS↓ 后立即打第一个时钟、末位后立即 CS↑，setup/hold = 0**——这是与全部 vendor 参考的又一系统性差异（修复候选，见 §5）。
- 事务间 bus turn-around：Syna core v2 明确 `TAT_DELAY_US_MIN/MAX = 100/200 µs`（core_dev.h L130-131；core_v2.c `syna_pal_sleep_us(TAT_DELAY_US_MIN, TAT_DELAY_US_MAX)`）；读失败重试间隔 `RD_RETRY_US = 5-10 ms`、连续写间隔 `WR_DELAY_US = 500-1000 µs`。我们在写→读间有 150 µs，事务之间没有间隔。

### 1.4 RESET 后固件启动时序（vendor 权威 ms 数）

| 参数 | 值 | 出处 |
| --- | --- | --- |
| power-on 后等待 | **200 ms** | `synaptics,power-delay-ms = <200>`；core 默认 `.power_on_delay_ms = 200` |
| RESET 声明时长 | **10 ms** | `synaptics,reset-active-ms = <10>`；OPPO v1 驱动 `POWEWRUP_TO_RESET_TIME 10` |
| RESET 释放后等待 | **80 ms** | `synaptics,reset-delay-ms = <80>`；OPPO v1 驱动 `RESET_TO_NORMAL_TIME 80`；core 默认 `.reset_delay_ms = 80` |
| 回退长等待 | 200 ms | core_dev.h `RESET_DELAY_MS (200)`（"default time after reset in case it's not set properly"） |
| fw mode switch | 200 ms | `FW_MODE_SWITCH_DELAY_MS` |
| 复位后使能 IRQ 前再等 | 15 ms | core_dev.h `RST_ENABLE_IRQ_DELAY_MS`；fw update 后同样 `msleep(RST_ENABLE_IRQ_DELAY_MS)` 再 hw_reset |
| 命令响应超时 / 轮询间隔 | 3000 ms / 20 ms | `CMD_RESPONSE_TIMEOUT_MS` / `CMD_RESPONSE_POLLING_DELAY_MS` |
| 读重试间隔 | 5-10 ms | `RD_RETRY_US_MIN/MAX` |

HBP 驱动 probe 顺序（syna_tcm2.c `syna_tcm2_probe` → connect）：`ops_power_on(true)` → `ops_hw_reset()`（低 10 ms + 高等 80 ms）→ **立即** `syna_tcm_detect_device()`——vendor 认为复位后 80 ms 固件就绪。我们等了 100 ms 且探测窗拉长到 ~1 s，**等待时间不是瓶颈**（b20 也证明 80 ms 脉冲后即活）。
我们 power_on 的"复位先按住 → 上电 → 200 ms → 释放 → 100 ms"与 vendor "上电 → 200 ms → 脉冲 10 ms → 等 80 ms"兼容（更保守）。**b18 与 b20 的差别提示：复位脉冲最好在电源就绪后重打一次**——v10c 的 loopback probe 正好实现了这一点，应保留为固定步骤。

### 1.5 TCM 电源模式（BURNING/BRICKED/SLEEP）

- **公开驱动代码里没有 BURNING/BRICKED 概念**（OnePlusOSS 两仓 + Pixel synaptics_touch 全文 grep 无 bricked/burn）——这组词来自 Synaptics NDA 级 TCM/芯片手册，**网上无公开文档，存疑**。
- 驱动可证的睡眠机制只有：`CMD_ENTER_DEEP_SLEEP` / `CMD_EXIT_DEEP_SLEEP`（0x2c/0x2d，OPPO v1 驱动 suspend/resume 即用这对；syna_tcm2.c 的 `pwr_state`/`LOW_PWR` 也是固件级状态机）——**deep sleep 是固件态，SPI 总线接口仍然活着**（唤醒 = 总线上发 CMD_EXIT_DEEP_SLEEP，或硬件复位）。
- 工程结论（对"固件崩死、总线不理"的状态）：**唯一的可靠恢复 = 硬件 RESET 脚脉冲**（vendor 所有驱动的通用行为：reset_occurrence 回调 + hw_reset）；我们已有 GPIO20 通道，不受影响。本机场景是刚硬件复位，与睡眠态无关。

### 1.6 STATUS_PACKET_CORRUPTED 的社区/源码先例

- 定义与语义：host 自造状态（见 0.4），触发条件 = 头 CRC-6 残差 ≠ 0 / 序列位不匹配 / 载荷 CRC-16 ≠ 0（Pixel synaptics_touch `synaptics_touchcom_core_v2.c` L516-526、L1474；本仓 core_dev.h L324 注释）。社区日志里的 "packet corrupted" 一律对应 CRC/截断，驱动惯例处理 = **重读 + 最终复位**（realme 开源 synaptics_tcm 驱动同构）。
- 本机 6/6 的真实成因已定案（0.4）：v2 框架问 v1 芯片。**与"电气噪声/相位错"无关**（那些在 b20 已排除：全实验相位均复现同一帧）。

### 1.7 TCM v1/v2 探测的权威流程（vendor 版）

`syna_tcm_detect_device()`（Pixel 同源 `func_base.c`，与 HBP 驱动一致）：

1. **先写 1 字节 magic `0x07`**（= CMD_TCM2_ACK）到总线；
2. 再 clock 出 4 字节；
3. v1 判据：`data[0] == 0xA5`（且 code 合法时读剩余 identify）；
4. v2 判据：`syna_tcm_crc6(data, 32) == 0`（CRC-6 残差校验）。

要点：**vendor 从不做"无写入的裸被动读"**——探测永远先写后读。我们的 v1 被动裸读窗在 b20 已证明能工作（read 1 即中），但 0x07 预写 + 4 字节头是 vendor 惯例，值得在修复轮顺手对齐。

### 1.8 v1 消息格式（本机实证 + vendor 源码）

- 帧 = `[A5][code][len_lo][len_hi][payload(len)][0x5A padding]`；续读事务头 = `[A5][STATUS_CONTINUED_READ=0x03][chunk...]`。
- identify payload 本机 = **28 字节**（0x1c；v1 标准 24 + 4 扩展），我们的窗口判据 `payload_length >= 24 && buf[4]==1` 兼容。
- OPPO v1 驱动的读序列（PREDICTIVE_READING，`MIN_READ_LENGTH = 9`，`RD_CHUNK_SIZE = 0/2048` 两档）：**首事务读 9 字节**（4 头 + 5 载荷），剩余 24+2 字节**单事务**续读 `[A5][03]+rest`——与我们 v1_read 的 9+26 形状**完全一致**。差异只剩两处：**读时 MOSI 内容**与 **ATTN 对齐**（vendor 是 ATTN 中断后读，消息已完全就绪；我们是被动轮询）。
- v2 帧格式核对（已排除嫌疑）：TX 头字节 3 = `HOST_PRIMARY<<7 | seq<<6 | crc6(26 bits)`；RX 校验 = `crc6(32 bits)==0` + seq 位 + CRC-16 残差——我们 v10b/v10c 的实现与 Syna 参考**逐位一致**（对照 Pixel `synaptics_touchcom_core_v2.c` L516/L592/L639、L1474）。

---

## 2. 通用 SPI bring-up 坑（对照我们的症状）

| 症状 | 指向 | 本机裁决 |
| --- | --- | --- |
| MISO 全 0x00 | 线钳低 / 芯片未上电 / CS 极性错致芯片不驱动 | b18 曾见（v1 窗全败、无原始字节打印无法定性）；b20 起 MISO 有真帧，已排除 |
| MISO 全 0xFF | 从设备未驱动（tri-state）+ 上拉/浮空偏上，或芯片在复位 | b20 exp4（复位反转）正是此形态，佐证"FF = 芯片不驱动" |
| 位偏移/杂波伪帧 | CPHA 错、速率不匹配、首字节采样过早 | 已排除：mode 0 正确；速率扫描（100 kHz→~10 MHz）失败模式不变；帧头 A5/03 每窗对齐 |
| MISO 浮空电平 | tri-state 时读数不定（实测可停 ~VDD/2） | [TI E2E 实例](https://e2e.ti.com/support/wireless-connectivity/bluetooth-group/bluetooth/f/bluetooth-forum/1045943/cc2640r2f-spi-miso-pin-state-is-2-5-volts-while-communication-is-not-going-over-spi)；b20 的 [30][FF×8] 中 FF 段即芯片中途停驱 + 偏置上浮 |
| MISO 上拉惯例 | 无强制标准；上拉只为 idle 定义、防浮空中电平 | [Altium](https://resources.altium.com/p/you-dont-need-pull-resistors-spi-lines)、[EE.SE](https://electronics.stackexchange.com/questions/234703/spi-bus-termination-and-pull-up-resistors)；b20 exp1 上拉无变化 → **偏置排除** |
| CS 极性错 | 从设备永不驱动 MISO（全 FF/00） | 本机 CS 低有效、idle 高（DT `cs_sleep output-high`），bitbang 正确 |
| **读方向 MOSI 内容** | **多 TCM/触摸器件读事务要求主机 clock 固定 0xFF dummy**——OPPO v1 `memset(buf, 0xff, length)`、OPPO 通用层 SPIREAD `memset(tx_buf, 0xFF, ...)`、Syna HBP `syna_pal_mem_set(tx_buf, 0xff, rd_len)` | **我们 clock 0x00——三家 vendor 全不一致的唯一读方向差异（修复候选 #1）** |

参考：[Wikipedia SPI（tri-state 规则）](https://en.wikipedia.org/wiki/Serial_Peripheral_Interface)、[Analog Devices SPI 入门](https://www.analog.com/en/resources/analog-dialogue/articles/introduction-to-spi-interface.html)、[Linux spi-gpio 驱动](https://github.com/torvalds/linux/blob/master/drivers/spi/spi-gpio.c)（bitbang 参考实现：其对 idle/mode/延迟的语义与我们一致的、CS 框架相同）。

---

## 3. 本地源码核验表（vendor vs 我们，逐项）

权威本地源：
- 本机 DT（真机面板/TD 同源）：`intel/wave1b-scripts/udon_22803_tp_config.dtsi`（= OnePlusOSS modules 仓 `kernel_platform/qcom/proprietary/devicetree/oplus/tp/udon_22803_extra_config.dtsi` 的 wave1 快照）
- 我们驱动：`wave12b-scripts/hakios.s3910.v10b.c`、`wave12c-scripts/hakios.s3910.v10c.c`（WSL 构建源快照）
- vendor 驱动（OnePlusOSS，本调研下载核对）：`android_kernel_modules_and_devicetree_oneplus_sm8475` 分支 `oneplus/sm8475_u_14.0.0_oneplus_ace_2`：`vendor/oplus/kernel/touchpanel/synaptics_hbp/{syna_tcm2.c, syna_tcm2_platform_spi.c, tcm/synaptics_touchcom_core_v1.c, tcm/synaptics_touchcom_core_v2.c, tcm/synaptics_touchcom_core_dev.h}` + `vendor/oplus/kernel/touchpanel/oplus_touchscreen_v2/Synaptics/Syna_tcm_S3910/{synaptics_tcm_S3910.c,.h, synaptics_tcm_device_S3910.c}`
- vendor DT 权威：同仓 `kernel_platform/qcom/proprietary/devicetree/qcom/cape-pinctrl.dtsi`（sm8475=cape）、`.../oplus/udon_22803_overlay_common.dtsi`

| # | 项目 | vendor（DT/驱动） | 我们（v10c/b20） | 判定（症状吻合度） |
| --- | --- | --- | --- | --- |
| 1 | 引脚：MISO/MOSI/CLK/CS | QUP4 pad0..3 = **gpio16=MISO, 17=MOSI, 18=CLK, 19=CS**（cape-pinctrl `qupv3_se4_spi_active` gpio16-19 func qup4；pad 次序规则由 Galaxy S22 r0q（同 SM8450 die）QUP8 显式标注交叉印证：28=MISO/29=MOSI/30=CLK/31=CS） | MISO16/MOSI17/CLK18/CS19，func 0 bitbang | **一致——MOSI/MISO 接反彻底排除** |
| 2 | SPI mode | 0（DT `spi-mode=<0>` + 两驱动） | CPOL0/CPHA0 | **一致** |
| 3 | 时钟 | 12-15 MHz 引擎 | bitbang ~8-16 MHz（等效），b20 已扫 100 kHz | 一致；速率已真机排除 |
| 4 | CS | 低有效、idle 高、每事务一帧；引擎级 CS setup/hold µs 级（Syna MTK 配置 5µs/3µs 类比） | 低有效/idle 高/每事务一帧 ✓；**setup/hold = 0** | **不一致（候选 #2）** |
| 5 | **读事务 MOSI 内容** | **0xFF**（OPPO v1、OPPO 通用层、Syna HBP 三处一致） | **0x00**（`tx ? tx[i] : 0`） | **不一致（候选 #1，一字节修复）** |
| 6 | RESET | GPIO20，低有效（`reset-on-state=0`、`reset-gpio 0x1`），脉冲 10 ms、后等 80 ms；power 200 ms | GPIO20 低有效；按住→上电→200 ms→释放→等 100 ms | 一致（b20 exp4 反转=死，双向证实）；**vendor 在电源就绪后会再打脉冲（v10c loopback 已等效，保留）** |
| 7 | INT/ATTN | GPIO21，**声明=低**（irq-on-state=0；0x2008=level-low），idle=高 | GPIO21 输入 no-pull，只读极性 | 语义已对齐（0.3）；**尚未在探测里用 ATTN 做事件对齐（候选 #3）** |
| 8 | 供电 | vdd=L3C 3008 mV（pm8350c l3）+ vcc=L4H 1800 mV（pm8450 l4）+ GPIO97 负载开关（wave12-touch-buttons.md §64 已核 cmd-db `ldoc3`/`ldoh4`） | ldoc3 3008 / ldoh4 1800 + GPIO97 | 一致（b20 真机两轨写成功；exp5 显示开关不门控，留复核项不阻塞） |
| 9 | v1 读序列 | 头 9 B（MIN_READ_LENGTH=9）→ 续读 `[A5][03]+24+2` 单事务；读后校验 padding 0x5A；ATTN 事件驱动 | 9 B → `[A5][03]` 检查 + 26 B 单事务；窗口丢弃 0x03 帧 | **形状一致；差异 = 读时序对齐 + 续读失败后无跨事务重组（候选 #3 附带）** |
| 10 | 探测入口 | 先写 0x07 再读 4 B；v1 判 A5、v2 判 CRC6 残差 | 被动裸读 9 B 判 A5；v2 回退发 CMD_IDENTIFY | 探测差异（v1 窗已被 b20 证明可行；v2 回退在本机死路，见 0.4） |
| 11 | v2 帧实现 | TX byte3=`1<<7\|seq<<6\|crc6(26b)`；RX `crc6(32b)==0`+seq+CRC16 | 逐位一致 | 一致（v2 在本机无用武之地） |
| 12 | 复位/超时常数 | power 200/active 10/delay 80/RESET_DELAY 200/mode-switch 200/IRQ-before 15 ms | 200/100（窗口另加 ~1 s） | 一致偏保守 |

---

## 4. 先例搜索（bitbang TCM / Mu-Silicium / 自研 OS 触摸）

1. **bitbang SPI 驱 Synaptics TCM：无公开先例**。Linux `spi-gpio` bitbang 总线上挂触摸的记录都是 RMI4/其它协议（[spi-gpio.c](https://github.com/torvalds/linux/blob/master/drivers/spi/spi-gpio.c)、[ST wiki](https://wiki.st.com/stmpu/wiki/SPI_device_tree_configuration) 等），没有 TCM-over-bitbang 的项目、博客或邮件列表记录。我们这条路径没有可抄的现成答案。
2. **Project-Silicium / Mu-Silicium / MU-Qcom：该平台家族（sm8475）触摸未解决，无可借路径**。Mu-Silicium 的 OnePlus 平台包（如 astonPkg = OnePlus Ace 3/12R，同为 sm8475 兄弟机）的 `DXE.inc` 里**没有任何 TouchDxe**（只有 ButtonsDxe/SPIDxe/GpiDxe 等外围）；MU-Qcom 的 Status.md 中 aston 的 UEFI 状态表传感器/触摸类全部未标 ✅（[Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)、[MU-Qcom Status.md](https://github.com/Robotix22/MU-Qcom/blob/main/Status.md)）。即 Mu 系在 UEFI 阶段不碰触摸 IC——与我们 as-found"芯片完全断电"的状态一致，也不存在"UEFI TouchDxe 已初始化过芯片"的隐藏变量。
3. **自研 OS 驱手机触摸 IC（XNU 侧）**：最接近的公开先例是 Corellium [Project Sandcastle](https://projectsandcastle.org)（反方向：iOS/XNU 跑在 Apple 硬件上），其触摸支持是**用户态 daemon `hx-touchd`**（[repo](https://github.com/corellium/projectsandcastle)）而非 XNU 内核驱动，且"Making Of"称触摸控制器"并不复杂"——但那是 Apple 的 touch（I2C），与 Qualcomm SPI TCM 无可比性。**XNU 直接驱动 Qualcomm 平台 Synaptics TCM 触摸 IC：无公开先例，本项目为第一个**（Linux 侧参考即 OnePlusOSS 上述驱动栈）。

---

## 5. 最可能的 3 个根因排序 + 下一刷实验

前置事实（b20 定案）：电气链全通；芯片 = TCM **v1**（"S3910PA0B0-2-15.2"，mode 0x01）；失败精确收敛在 **v1 identify 的续读事务**——首事务 9 B 每次成功（[A5][10][1c][00]+载荷），紧随的 26 B 续读事务每次只得 `[30][FF×8]`（芯片输出 ~1 字节即停驱），而 20 ms 后的窗口读又能正确收到 `[A5][03]+载荷`（芯片把续读分帧服务的能力在）。

### 根因 1（吻合度最高）：读事务 MOSI 内容 + CS 建立时序与 vendor 系统性不一致

- vendor 三实现读方向全部 clock **0xFF**；我们 clock **0x00**。TCM 器件的 MOSI-in 并非纯 don't-care（探测写 0x07、写命令皆经同一输入路径）；0x00 连流恰是"无效命令/CMD_NONE"的位型，续读中途被设备侧判为异常即停驱——与 [30][FF×25]（输出 1 字节即停）形态自洽。存疑但实验成本 = 1 字节。
- CS↓ → 首时钟之间、末时钟 → CS↑ 之间 vendor 引擎有 µs 级 setup/hold；我们为 0。芯片若在 CS↓ 后需要时间装载 TX 移位寄存器，**续读事务**（要求输出 [A5][03] 新帧头）恰是唯一"每次都要现装帧头"的事务——首事务 9 B（芯片 reset 后已在自由播报）不受影响。这也精确匹配"只有续读死"的分布。

**实验（一次刷带齐，全部可 boot-arg 化）**：
1. `bitbang_transfer` 的 `tx==NULL` 分支改 clock 0xFF（对照：`touch_mosi_idle=0/1` 双值）；
2. CS↓ 后 sleep 5 µs 再打首时钟，末位后 sleep 3 µs 再 CS↑，事务间 sleep 150 µs（TAT）；失败重试间 5-10 ms（RD_RETRY）；
3. 判据 = 续读事务头 2 字节是否为 `A5 03`；成功 → identify 28 字节齐 → `TouchComm v1 firmware: mode 0x01` 硬验收行。

### 根因 2：v1 窗口/续读状态机不识别"分帧服务"（纯软件，保险丝）

芯片已证明会把 identify 拆成多个 `[A5][03]` 帧服务（b20 read 2/3）。若根因 1 的修复后仍有残余失配，正确姿势是 vendor 的回退逻辑：**任何窗口读到 `[A5][03]` 就继续 clock 到 0x5A padding，跨事务重组整包**（OPPO v1 驱动的 continued_read 循环即如此）。当前我们把它当"无载荷状态行"丢弃。改动小，可与根因 1 同刷。

### 根因 3：ATTN 事件对齐缺失（兼"固件未就绪"的独立观测）

vendor 全家是 ATTN（GPIO21，低有效）驱动读：ATTN 声明后消息才保证就绪。我们被动轮询虽在 b20 拿到了帧，但"读早了"永远无法排除。下一刷：探测循环每轮先看 GPIO21——**若 INT 拉低再读**（事件对齐），并打印 INT 状态进日志。附带收益：若复位脉冲后 INT 恒不拉低，即"固件未起/没在宣告"的独立信号，能一键区分"芯片没起"与"读法不对"。另外把 v10c 的 loopback probe（电源就绪后重打 reset 脉冲）固化为固定步骤——b18→b20 的差异证明这一脉冲是活与不活的分水岭。

**v2 fallback 处置**：本机为 v1 固件，v2 探测只会持续制造 0xfe 噪音。建议探测顺序改为：读 4 B → 首字节 0xA5 即走 v1（不再等完整 identify 才定协议）；否则再做 CRC-6 v2 判定（保留，供其它机型）。

---

## 6. 主要出处

本地（仓库内）：
- `intel/wave1b-scripts/synaptics_touchcom_core_dev.h`（Syna core 头：0xfe 自定义、TAT/RD_RETRY/RESET_DELAY/IRQ delay 常数、crc6/16 表）
- `intel/wave1b-scripts/udon_22803_tp_config.dtsi`（udon 触摸 DT：GPIO16-19 qup4、gpio20/21、L3C/L4H/GPIO97、spi-mode=0、15 MHz、reset 10/80 ms、irq-on-state=0）
- `wave12b-scripts/hakios.s3910.v10b.c`、`wave12c-scripts/hakios.s3910.v10c.c`（我们驱动：bitbang 0x00、CS 无延迟、v1 9+26 序列、v2 帧）
- `intel/m3-boot1/b20-kernel-log.txt`（芯片存活实证、v1 identify、[A5][0F] STATUS_ERROR、五相实验扫除）
- `docs/waves/wave12-touch-buttons.md`（ldoc3=pm8350c-l3=L3C、ldoh4=pm8450-l4=L4H 映射）
- `upstream/uefi-udon/Resources/DTBs/r0q.dts`（Galaxy S22 SM8450 QUP8 MISO/MOSI 显式标注，pad 次序交叉印证）

外部（OnePlusOSS 官方 = PHK110 同源栈）：
- modules/devicetree 仓 u14 分支：[`synaptics_hbp/syna_tcm2.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/vendor/oplus/kernel/touchpanel/synaptics_hbp/syna_tcm2.c)、[`syna_tcm2_platform_spi.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/vendor/oplus/kernel/touchpanel/synaptics_hbp/syna_tcm2_platform_spi.c)、[`tcm/synaptics_touchcom_core_v1.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/vendor/oplus/kernel/touchpanel/synaptics_hbp/tcm/synaptics_touchcom_core_v1.c)、[`Syna_tcm_S3910/synaptics_tcm_S3910.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/vendor/oplus/kernel/touchpanel/oplus_touchscreen_v2/Synaptics/Syna_tcm_S3910/synaptics_tcm_S3910.c)、[`cape-pinctrl.dtsi`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/kernel_platform/qcom/proprietary/devicetree/qcom/cape-pinctrl.dtsi)、[`udon_22803_extra_config.dtsi`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475/blob/oneplus/sm8475_u_14.0.0_oneplus_ace_2/kernel_platform/qcom/proprietary/devicetree/oplus/tp/udon_22803_extra_config.dtsi)
- 内核仓 u14 分支（kernel 侧镜像/ bindings）：[android_kernel_oneplus_sm8475](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8475/tree/oneplus/sm8475_u_14.0.0_oneplus_ace_2)
- Syna TCM 绑定（irq-on-state/ spi-mode/ reset 语义）：仓内 `kernel_platform/qcom/proprietary/devicetree/bindings/input/touchscreen/synaptics_tcm_spi.txt`
- Syna 参考实现交叉验证（Pixel 同源）：[android.googlesource.com kernel/google-modules/touch/synaptics_touch](https://android.googlesource.com/kernel/google-modules/touch/synaptics_touch/+/refs/heads/android-gs-akita-android16/syna_gtd/tcm/synaptics_touchcom_core_v2.c)（crc6(32)/crc6(26)/0xFF 读 dummy 的逐位对照）
- 通用：[Wikipedia SPI](https://en.wikipedia.org/wiki/Serial_Peripheral_Interface)、[Altium SPI pull-ups](https://resources.altium.com/p/you-dont-need-pull-resistors-spi-lines)、[TI E2E MISO idle](https://e2e.ti.com/support/wireless-connectivity/bluetooth-group/bluetooth/f/bluetooth-forum/1045943/cc2640r2f-spi-miso-pin-state-is-2-5-volts-while-communication-is-not-going-over-spi)、[spi-gpio.c](https://github.com/torvalds/linux/blob/master/drivers/spi/spi-gpio.c)、[Project Sandcastle](https://projectsandcastle.org)/[repo](https://github.com/corellium/projectsandcastle)、[Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)、[MU-Qcom Status](https://github.com/Robotix22/MU-Qcom/blob/main/Status.md)
- 存疑项：TCM "BURNING/BRICKED" 电源模式无公开文档（NDA 术语，仅工程级推断"总线死用硬复位恢复"）。
