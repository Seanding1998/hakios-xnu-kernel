# Wave 12 — 触感与按键：S3910 TCM 驱动 + 电源/音量键 + 300 s 常驻 + 8 核同起（`udon-hakios-grafted-v7…v9.img`，Boot #14–#16）

Date: 2026-11-03. Agent: Wave 12（全循环：调研 → 实现 → 三轮自刷自取证 → 交接 v10）。
目标：v0.3「触感」主体——真机 Synaptics S3910 的 TCM probe（本轮硬验收目标，**未达，阻塞点已定位到
寄存器级**）、电源/音量键（**已达，真机按键事件取证**）、cmdline 升级（`loader_return_after=300` +
`small_cores_after=0`，**均已达**）。

## Result summary

**一句话结论**：✅ 调研/实现/构建全绿（v7/v8/v9 三轮镜像自检均 32/32、v6 基线 27/27、QEMU 冒烟到
标准终点）；✅ **按键全链真机达成**（SPMI v7 仲裁器适配 + 真机三键 press/release 事件取证，t=265 s
时 30,006 次总线读仅 2 失败）；✅ **首个完整 300 s 常驻会话零 panic**（t=300.36 s `loader_return_after
expired` 干净返回）+ 8 核同起（7 AP 在 8 ms 内全部上线）；🟡 **S3910 TCM probe 未达**：驱动三轮迭代
修掉两个 panic 级 bug（RPMh 双重 TCS 寻址、GCC 映射越界）后干净推进到"双轨上电成功 → GENI 时钟
检测"，被 **wrap1 s_ahb 分支停摆**（`0x28008 = 0x80000002`，投票后不清 bit31）阻塞——现已定性为
**cape/sm8475 的 GCC ≠ mainline sm8450**（FDT 时钟索引 m/s_ahb=134/135 vs mainline 118/119 铁证），
v10 内核（已构建未刷写）已改为"s_ahb 告警不阻断 + 引擎直接探活 + bitbang 回退"，下轮首刷即验。

| Artifact | Path（仓库根相对；Windows 侧只新增） | Size | SHA-256 |
| --- | --- | --- | --- |
| **当前刷在 boot_b（Boot #16）** | `device-layer/udon-hakios-grafted-v9.img` | 201,326,592 B (192 MiB) | `d0d96ab578b1100dd1eef315d387ba5fc0aef472cbfde4b1d0ba45963926f243` |
| payload v9（kernel 换 v9 内核） | `device-layer/udon-hakios-payload-v9.bin` | 14,944,472 B | `5fc5721cafe04489b60da7de9fd23aff2305cc62f2ce569618bf82b6b7ea4880` |
| **v10 内核（已构建未刷写，下轮交接件）** | `device-layer/hakios-kernel-v10.bin` | 14,859,888 B | `75e2a481c292c6d1ed74f0b35aa1a48ae9d472da7dad974f8a2c31e529cf5108` |
| 内核 v9（Boot #16 上机版） | `device-layer/hakios-kernel-v9.bin` | 14,859,800 B | `f56468c25894d8a65545a804e20574be666d578c6c0961ccd1a623f41f62052d` |
| 内核 v8（Boot #15 上机版） | `device-layer/hakios-kernel-v8.bin` | 14,859,800 B | `e5df0e7b2b937c45f6216352a50036f934693a87f2bc95a6dfcf5f33e32a5ff3` |
| 内核 v7（Boot #14 上机版） | `device-layer/hakios-kernel-v7` | 14,859,704 B | `5168dc26d8b924c6071aaf4f358dcf3735650add58dac829d83d3c7bb803c837` |
| 新 cmdline（375 B 含 NUL，v7–v9 共用） | `device-layer/udon-hakios-cmdline-v7.bin` | 375 B | `61534c3a75c91d6564873c27b07c1f82ef3c7e0f02360a5ad79e940e402816f3` |
| payload v7 / v8（历史轮） | `device-layer/udon-hakios-payload-v7.bin` / `-v8.bin` | 14,944,408 / 14,944,408 B | `f912150d…42d` / `f198ac61…ac0` |
| 镜像 v7 / v8（历史轮） | `device-layer/udon-hakios-grafted-v7.img` / `-v8.img` | 192 MiB | `a3282d0e…b7d` / `278a34fe…d89` |
| **S3910 驱动源码（v10 终态，新增文件，device repo）** | `wave12-scripts/hakios.s3910.c`（= WSL `~/hakios/kernel/devices/phk110/drivers/input/hakios.s3910.c`，树上 `bsd/dev/hakios.s3910.c`） | 1,545 行 | `4dab7e0c730969e6b11a6b50e77e8e43851cf018496eec8deedf5b0178c5f272` |
| device-repo 驱动 conf | `wave12-scripts/conf`（= WSL `devices/phk110/drivers/input/conf`） | 648 B | `5f8dbe8747058f953fd95744a78eda48d992f5926ad8f5bc85f893bfa551a142` |
| repack / cmdline / 自检脚本 | `wave12-scripts/repack-payload-v7.py`、`make-cmdline-v7.py`、`verify-udon-hakios-v7.py` | — | `ada855dd…` / `9abb3fd0…` / `496400d0…` |
| 迭代修复脚本（四连，按序） | `wave12-scripts/fix2-rpmhwait.py`、`fix3-buttons-v7.py`、`fix4-gccsize.py`、`fix5-v10.py`（fix1 并入 fix3 前身） | — | `1373554a…` / `a92e65f8…` / `e35c49ca…` / `80beb4d2…` |
| buttons.c / configs 接线脚本 | `wave12-scripts/patch-buttons.py`、`patch-configs.py`、`patch-buttons-on.py`、`patch-argnames.py` | — | `47526bfb…` / `843b1c5b…` / `c34a03e9…` / `e2412a21…` |
| QEMU 冒烟全链日志 | `device-layer/qemu-open-w12.log` | 377,944 B | `72d58f195b0ede35455612ecfe5e6edd9e2f37b1f8432e6a3c8c2dff5a23b11b` |
| Boot #14 logdump（v7） | `logdump-v7.bin`（仓库根） | 65,536 B | `a01bc603928a8c07237bf9375e86282ce76ad4ace444a0ebb8f223e1165368b7` |
| **Boot #14 内核日志（panic 取证）** | `intel/m3-boot1/b14-kernel-log.txt` | 33,746 B | `85c7e0bfc953a05f006b0895fd83ac12bf568096eddef394e92f7abb3557e232` |
| Boot #15 logdump（v8） | `logdump-v8.bin`（仓库根） | 65,536 B | `af4cd4c15a07faf7354ea94ab31eb71deb71c6d46f86b726a5d854b256c6999b` |
| **Boot #15 内核日志（按键 v7 + 第二 panic 取证）** | `intel/m3-boot1/b15-kernel-log.txt` | 37,618 B | `024d4c308f8b70fbae100778737741cb3da2aae0d70035909b9bf9050888f34d` |
| Boot #16 logdump（v9，含 loader 全量日志） | `logdump-v9.bin`（仓库根） | 65,536 B | `5e9301adb6f6e03702361d325f13b6f19d703ad510d8231e5c31ed8f47ed531f` |
| **Boot #16 日志（按键真机事件 + 300 s 会话 + s3910 阻塞点）** | `intel/m3-boot1/b16-kernel-log.txt` | 35,892 B | `ace841cd677c42860337c31217fdf90b92d247d740fb71296424ff32f5e6099e` |

未动的构件（逐字节校验）：loader.efi（`66c6b342…`，v5/v6 同——**loader.c 零改动**）、ramdisk
（`4f72da61…`，v6 驻留 stub 原样）、kernel.ver（`afd473f5…`，v6 同）、BootShim（`108ce972…`）、
SILICIUM_UEFI.fd（`8924cb67…`，禁重建条款遵守）、stock-boot-a.img。v1–v6 镜像全部原样（v6 基线
本轮复跑自检 **27/27 通过**）。

---

## 1. 调研结论（A1–A4）

### 1.1 live FDT：触摸挂在哪（铁证）

来源：`intel/live-fdt.dtb`（= `intel/phk110-fdt.dtb`）反编译全文 `intel/wave1b-scripts/fdt-full.txt`。

| 项 | 值 | FDT 证据 |
| --- | --- | --- |
| **总线** | GENI SPI，QUPV3 第二组（wrap1）**SE4**，控制器 `0x09900000`（size 0x4000） | `/soc/spi@990000`，compatible `qcom,spi-geni`，status **ok**，GIC SPI 中断 0x25d=605 level-high |
| **触摸节点** | `/soc/spi@990000/synaptics_tcm_hbp@0`，compatible `synaptics,tcm-spi-hbp`，**status = okay** | 同总线其它触摸节点（synaptics-s3910/focaltech/goodix）全部 disabled |
| spi-max-frequency | 15 MHz（HBP 节点 0xe4e1c0；Oplus S3910 节点 12 MHz） | |
| spi-mode | 0（delay 全 0） | GENI 编程同 goodix 先例 |
| **INT** | **TLMM GPIO 21**，`interrupts = <21 0x2008>`（bit3=8 → **level-low**，低=有报告） | interrupt-parent = tlmm（phandle 0x3c = `/soc/pinctrl@f000000`，基址 0x0f100000） |
| **RESET** | **TLMM GPIO 20**，active low（reset-active-ms=10，reset-delay-ms=80） | |
| **供电** | vdd（模拟 2.8 V）= **L3C**（`rpmh-regulator-ldoc3/regulator-pm8350c-l3`）+ 负载开关 **TLMM GPIO 97**；vcc（I/O 1.8 V）= **L4H**（`rpmh-regulator-ldoh4/regulator-pm8450-l4`） | cmd-db 资源名 = **`ldoc3`** / **`ldoh4`** |
| 时序 | power-on-state=1，power-delay-ms=200，irq-on-state=0 | |
| 面板 | 1240×2772（NT37705，v0.2 显示波次对象） | |
| RPMh RSC | apps_rsc = `/soc/rsc@17a00000`，4 DRV 窗口 +0x10000×n，**drv-id=2 → APPS RSC = 0x17a20000**（= soc.args `soc_rsc`），tcs-offset 0xd00 | 与 goodix 的 TCS 布局同构 |
| **GCC（ cape）** | `clock-controller@100000`，compatible `qcom,cape-gcc`，reg size **0x1f4200** | ⚠ 时钟索引 **0x5e/0x86/0x87**（se-clk/m-ahb/s-ahb）≠ mainline sm8450 表的 94/118/119 → **cape GCC ≠ sm8450 GCC**（§7.4 阻塞点分析的关键证据） |

### 1.2 live FDT：按键（PMIC 侧）

| 键 | 硬件 | FDT 证据 | linux,code |
| --- | --- | --- | --- |
| **电源** | PMK8350 PON（`pon_hlos@1300`，slave 0，peripheral 0x13 = **id 0x013**）KPDPWR_N 位 0x80 | compatible `qcom,pmk8350-pwrkey` | 0x74=116 KEY_POWER |
| **音量上** | **同一 PON 块的 RESIN_N 位 0x40** | `pon_hlos@1300/resin`（`qcom,pmk8350-resin`） | 0x73=115 **KEY_VOLUMEUP** |
| **音量下** | **PM8350 GPIO6**（`qcom,pm8350@1` → slave **1**，pinctrl@8800 → peripheral 0x8d = **id 0x18d**，active low） | `gpio_keys/vol_down` | 0x72=114 KEY_VOLUMEDOWN |

- **与参考机（redwood）相反**：redwood 是 RESIN=音量下、PM7325 GPIO6=音量上；PHK110 是 RESIN=
  音量上、PM8350 GPIO6=音量下。外设 id 两机相同（0x013 / 0x18d）→ buttons.c 只需 `buttons_map=1` 换序。
- SPMI 仲裁器（taro）：reg-names `cnfg,core,chnls,obsrvr,intr` = **0xc42d000 / 0xc400000 / 0xc500000 /
  0xc440000 / 0xc4c0000**，`qcom,ee=0`。⚠ redwood 的 core=0xc440000 在 taro 恰是 obsrvr 基址——地址必须换。

### 1.3 GPL S3910 源码：TCM 协议要点（branch `oneplus/sm8475_v_15.0.0_ace_2`）

两个驱动族研读（只读参考，未引入代码）：`vendor/oplus/kernel/touchpanel/synaptics_hbp/`（真机生效
节点的绑定驱动，官方 TouchCom 套件 + tcm/ core v1/v2）与
`vendor/oplus/kernel/touchpanel/oplus_touchscreen_v2/Synaptics/Syna_tcm_S3910/`（Oplus S3910 变体，v1 裸帧）。

- **v2 包格式**：头 4 B `{code, len_lo, len_hi, byte3}`，byte3 = HOST_PRIMARY<<7 | 序号翻转<<6 |
  **CRC-6**（对头部前 26 bit，查表式）；payload 后跟 **CRC-16/CCITT**（init 0xFFFF，余式须为 0）。
- **命令流**：write [4B 头+payload+CRC16] → TAT 100–200 µs → read 4B 头（CRC-6 校验）→ payload+2B
  CRC；STATUS_ACK(0x07)=已收，响应经 `CMD_TCM2_GET_REPORT(0x0a)` 取回；STATUS_RETRY_REQUESTED(0x08)/
  包损 → 重发 ≤5 次；续读用 `CMD_TCM2_ACK(0x07)`。
- **关键命令/报告**：IDENTIFY=0x02、RESET=0x04、ENABLE_REPORT=0x05、GET_APPLICATION_INFO=0x20、
  GET_TOUCH_REPORT_CONFIG=0x25、RUN_APPLICATION_FIRMWARE=0x14；REPORT_IDENTIFY=0x10、REPORT_TOUCH=0x11。
- **v1 裸帧**（Oplus S3910 驱动）：`[0xA5, code, len_lo, len_hi, payload..., 0x5A]`，无校验和；复位后
  固件**自推** REPORT_IDENTIFY（读是无副作用的）。
- **协议探测策略**（本驱动实现）：先给 v1 一秒（被动读，0xA5 头 + version==1），无则走 v2 CMD_IDENTIFY
  （CRC-6 头校验）。
- **固件交互需求：无需刷固件**。正常路径 = 复位 → flash 固件自举 → identify → app info →
  配置/使能报告；仅 bootloader 模式（0x0b/0x04）时才发 CMD_RUN_APPLICATION_FIRMWARE（一条命令）。
  本驱动同此，**零闪存写**。

### 1.4 fork 基础设施调研

- **驱动骨架**：`drivers/input/hakios.goodix.c`（1,538 行）= 完整范本：TLMM 直写、RPMh（cmd-db +
  RSC TCS 槽）调压器、GCC 投票开 GENI 时钟（DFS 预设表择速）、GENI SPI FIFO 轮询、125 Hz 轮询
  INT 线、`hakios_touch_post(HAKIOS_TOUCH_DOWN/MOVE/UP, id, x, y)`（0–65535 归一化）→ `/dev/hakios-touch`。
- **按键**：`drivers/input/hakios.buttons.c` 已存在（SPMI observer 只读轮询 60 Hz、双读确认、
  `HAKIOS_BUTTON_*` 进同一队列）——只差 taro 地址 + 键位换序（本轮补齐）。
- **输入层**：XNU 侧队列即 `/dev/hakios-touch` 字符设备（mockfs 用户态直接读）；按键 = 同队列
  HAKIOS_BUTTON_DOWN/UP 记录。**上报层 = /dev/hakios-touch**（与 goodix 同构）。
- **配置机制**：`tools/hakios-config.py` 支持设备仓库自有驱动（`devices/<name>/drivers/<sub>/{conf,<file>}`）；
  `drivers-check.py` 校验一致；`tools/boot-args.py` 从源码自动生成 boot-args 文档（343 项，--check 绿）。

### 1.5 架构裁定（A4）

| 项 | 裁定 | 理由 |
| --- | --- | --- |
| 驱动数量 | **1 个新文件** `hakios.s3910.c`（供电/时钟/GPIO/GENI SPI/TCM v1+v2/触点解析/bitbang 回退）+ **复用** `hakios.buttons.c`（最小 patch） | goodix 先例：自包含 + boot-arg 门控；按键 infra 已在 |
| GENI SPI 控制器 | 内嵌于 s3910.c（寄存器同 IP），**外加 bitbang 回退**（v10） | GENI 时钟链路在 cape 上有未解之谜（§7.4），bitbang 只依赖 TLMM，保 TCM probe 可达 |
| DT 节点 | **无**（loader.c 零改动 → loader.efi 保持 v6 逐字节 `66c6b342…`） | goodix 同款：地址硬编码 + boot-arg 覆盖 |
| 输入上报 | `hakios_touch_post()` → `/dev/hakios-touch` | 与参考机用户态契约一致 |
| 触摸验收 | probe 级证据（TCM 固件握手）= 本轮硬验收目标；点按上报需真人配合 | 任务书设定 |
| cmdline | `loader_return_after=300` + `small_cores_after=0` + 驱动参数 | 均为已核实 boot-arg（GenericARMPE.cpp:269 / loader_return.c:464） |

## 2. 驱动实现

### 2.1 `hakios.s3910.c`（终态 1,545 行，CONFIG_HAKIOS_S3910，boot-arg `touchscreen=1`）

分段（对齐 goodix.c 结构）：

1. **GPIO**（TLMM 0x0f100000）：MISO=16/MOSI=17/CLK=18/CS=19（function **1** = "qup4"，由
   pinctrl-sm8450.c PINGROUP(16..19, qup4, …) funcs 序推得）、INT=21（输入）、RESET=20（低=复位）、
   VDD 负载开关=97（高=开）。
2. **供电（RPMh）**：cmd-db（0x80860000）查 **`ldoc3`**（3008 mV）/ **`ldoh4`**（1800 mV），经 APPS
   RSC DRV2（0x17a20000+0xd00）写 VRM {电压, 使能, HPM}；查名失败不阻断；写走 `hakios_rsc_lock`。
3. **时钟（GCC 0x100000，映射 0x1f4200 = FDT 原值）**：投票 **0x62008** bits {18,19,20,21,26}
   （mainline sm8450 表）；CBCR 0x28004/0x28008/0x284dc；RCG 0x284e4(+4 cfg,+0x14 dfsr,+0x1c perf…)。
   DFSR bit0=1 走 PERF 预设，否则直配 GPLL0。**s_ahb 分支停摆只告警不阻断（v10，见 §7.4）**。
4. **GENI SPI**（SE 0x09900000）：FIFO 模式轮询全双工；`touch_spi_hz` 默认 10 MHz，divider 钳制 ≥2。
5. **bitbang 回退（v10）**：引擎不可用时同四脚 GPIO 手驱（CS/CLK/MOSI/MISO，mode 0，goodix 同款
   实现）——只依赖 TLMM，TCM probe 与 GENI 时钟解耦。
6. **TCM 协议**：CRC-6/CRC-16（表驱动）；v1（0xA5/0x5A）与 v2（CRC-6 头 + CRC-16 包 + ACK 续读 +
   GET_REPORT）双实现；协议探测 v1 先（被动读 1 s）后 v2。
7. **probe 序列**：power_on（复位低 → GPIO97 → RPMh 双轨 → 200 ms → 复位高 → 100 ms）→ clocks →
   geni/bitbang → chip_identify（打印 **TouchComm 版本/模式/部件号/build id/最大包长**）→ 非应用
   模式则 RUN_APPLICATION_FIRMWARE → chip_app_info（轮询 BOOTING/UPDATING → **打印 max_x/max_y/
   对象数/按键数**）→ GET_TOUCH_REPORT_CONFIG（存表）→ ENABLE_REPORT(REPORT_TOUCH)。
8. **轮询线程**：125 Hz 看 INT（`touch_poll_us` 可调；80 ms 兜底读）；REPORT_TOUCH 按 config 逐位
   走查（0=LIFT→UP，缺席者补 UP；按 app_info 归一化，`touch_flip` 镜像）；REPORT_IDENTIFY 重现=
   芯片自行复位；60 s 状态汇总。

### 2.2 `hakios.buttons.c`（最小 patch，默认行为不变）

- 仲裁器地址变量化：`buttons_core=`/`buttons_cnfg=`/`buttons_obs=`（hex，默认 = redwood 原值）。
- **SPMI v7 支持**（Boot #14 发现仲裁器 = 0x70000000）：接受 v7——APID→PPID 表 core+0x2000、
  owner 表 cnfg+0、observer 通道 obsrvr+0x8000×ee+0x20×apid、通道数 features&0x7ff（本机 768）、
  ARB_MAX_CHANNELS 提至 1024、core 映射窗 0x1100→0x3000。v5 路径逐字节不变（redwood 不受影响）。
- `buttons_map=1`（taro 键位）：RESIN 源=volume up/VOLUME_UP，GPIO6(0x18d) 源=volume down/VOLUME_DOWN。

### 2.3 接线（common 仓库最小改动，qemu/redwood 行为不变）

- `drivers/core/hakios.stubs.c`：`#ifndef HAKIOS_S3910 void hakios_s3910_init(void) {}`。
- `xnu/files/bsd/sys/hakios.input.h` 声明 + `drivers/input/hakios.input.c` 在 goodix 后调用。
- `devices/phk110/drivers/input/{conf,hakios.s3910.c}`（`driver S3910`，**default n**）。
- 配置：phk110.config → `CONFIG_HAKIOS_S3910=y`、`CONFIG_HAKIOS_BUTTONS=y` + 4 个新 arg 名；
  common_defconfig、qemu_defconfig → 显式 `# CONFIG_HAKIOS_S3910 is not set`。
- boot-args 文档重新生成（343 参数）；`tools/drivers-check.py` 绿。
- 内核仓 git：仅叠加未提交改动，**未 reset/checkout/stash/clean、未 commit**。

## 3. cmdline（B 项两改 + 驱动参数）

```
serial=0 loader_return_after=300 small_cores_after=0 touchscreen=1 buttons=1 buttons_map=1 buttons_core=0xc400000 buttons_cnfg=0xc42d000 buttons_obs=0xc440000 cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws
```

- `loader_return_after=60 → 300`：内核自带 boot-arg（loader_return.c:464），1 MB ring 支持长会话。
- `small_cores_after=0`：内核源码核实可覆盖（GenericARMPE.cpp:269 `PE_parse_boot_argn`），0 = 立即
  run() 全部核。
- 长度：375 B；loader 预算 `BOOT_LINE_LENGTH=608`，实际 **451/607**（b16 屏证，无截断）。

## 4. 构建与打包（四轮镜像，同一管线）

每轮 = `repack-payload-vN.py`（保序断言 + 未动条目逐字节断言 + cmdline 预算断言）→
`wave4-scripts/package-udon-boot.py`（FD `8924cb67…` 原样）→ `verify-udon-hakios-v7.py` 32 项。
kernel 变化：v7（初版驱动）→ v8（+rpmh_wait 修复 + buttons v7）→ v9（+GCC_SIZE=0x1f4200）→
**v10（+s_ahb 告警不阻断 + bitbang 回退，已构建未刷写）**。loader/ramdisk/kernel.ver 四轮均保持
v6 原字节。v7/v8/v9 自检均 **ALL 32 CHECKS PASSED**（v8: `278a34fe…`，v9: `d0d96ab5…`）。

## 5. QEMU 冒烟（kernel 共享路径改动 → 全链跑）

`make defconfig`（open 内核，s3910 不在构建清单——default n 生效）→ `make qemu-open` 全链 300 s
（`device-layer/qemu-open-w12.log`）：`Hello from user space on Darwin!` → `panic: initproc failed
to start`（qemu-open 标准终点）→ Stackshot Succeeded → `== END OF LOG ==` → DXE ResetSystem 干净
复位。共享文件（input.c 新调用、buttons.c 改造、stubs、header）在 open 配置编译且零异常。此后
.config 恢复 phk110、内核重编、loader 还原（qemu-open 重建的 placeholder loader 仅差 PE
TimeDateStamp 2 字节，payload 一律用 v6 loader 原字节）。注：buttons.c 的 v7 分支改动在 QEMU 冒烟
之后，但其对 v5 仲裁器（QEMU/参考机）路径是纯默认值（常量与 redwood 逐位一致，版本门拒非匹配值），
行为不变。

## 6. 自检

- v7/v8/v9 三镜像 `verify-udon-hakios-v7.py`（21 形状 + 11 条目级）均 **ALL 32 CHECKS PASSED**；
  条目级断言：kernel == 本轮构建文件且 ≠ v6；cmdline == 本轮文件且含全部新参数、显式拒绝 =60/=20；
  loader.efi/ramdisk/kernel.ver 与 v6 逐字节相等。
- v6 基线复跑 `verify-udon-hakios-v6.py`：**ALL 27 CHECKS PASSED**（`c69c64c4…`）——v6 完好可回退。
- `tools/drivers-check.py`（49 文件）、`tools/boot-args.py --check`（343 参数）绿。
- 刷前 sha256 校验三轮全对（fastboot 侧 `sha256sum` 与打包报告一致）。

## 7. 刷写与取证全记录（Boot #14–#16，用户一揽子授权 boot_b 循环）

### 7.0 流程通道（三轮同法）

手机在安卓 → `adb devices`（`SERIAL_REDACTED device`）→ `adb shell getprop sys.boot_completed`=1 →
`adb reboot bootloader` → sleep 8–10 → `usbipd list`（三轮均 `2-2  18d1:d00d  Android  Shared
(forced)`，**每次重枚举都重新 attach**）→ `usbipd attach --wsl --busid 2-2` → WSL root
`timeout 15 fastboot getvar product` = `taro` ✓ → 刷前 `sha256sum` 对包 → `fastboot flash boot_b`
（Sending ~4.7 s / Writing ~0.6 s，全 OKAY）→ `fastboot set_active b` → `fastboot reboot`。

| Boot | 镜像 | 刷写时刻 | adb 回安卓 | 结果 |
| --- | --- | --- | --- | --- |
| **#14** | v7 `a3282d0e…` | 19:16 | 19:17:07（~1 min） | 内核 t≈10.49 s data-abort panic（§7.1）→ panic 快循环 → ABL 兜底回安卓 |
| **#15** | v8 `278a34fe…` | 19:31 | 19:32:29（~1.5 min） | RPMh 双轨上电成功 + 按键 SPMI v7 全链 probe 成功；t≈10.81 s 第二个 data-abort（§7.2） |
| **#16** | v9 `d0d96ab5…` | 19:47 | ~20:2x（主代理手动切回，见 §8 流程教训） | **零 panic**：完整 300 s 会话（t=300.36 s expired 干净返回）+ 按键真机事件（§7.3）；s3910 卡 s_ahb 时钟（§7.4） |

### 7.1 Boot #14（v7）——首个内核级取证：driver 执行到了真机

`b14-kernel-log.txt` 关键行（panic dump 的 Boot args 行**逐字可见全部新参数** = cmdline 上机铁证）：

```
buttons: step 1: map the PMIC arbiter (0xc400000, 0xc42d000, 0xc440000) and read its version
buttons: PMIC arbiter version 0x70000000, 768 channels
buttons: this driver knows version 5 of the arbiter only: no buttons
psci: cpu 1 ends the system: the return to the boot loader is the boot processor's to make
[10.394803-10.401721]: arm_cpu_init(): cpu 1..6 online（8 ms 内全部上线！）
[10.402562]: GenericARMPE: 7 of 7 processors are running
[10.494139]: s3910: as found: votes 0x1000600, clocks 0 0x80000002 0x80004220, ... int 0x1/0, vdd 0x1/0
panic(cpu 1): Kernel data abort. at pc 0xfffffff007489af8, lr 0xfffffff0074899f4
  esr: 0x96000005  far: 0xfffffffcec249a04
```

- **8 核同起达成**（`small_cores_after=0` 生效：7 AP 在 10.394–10.402 s 8 ms 内全部上线，对比 b13
  的慢核 38 s 延迟）。
- 按键：仲裁器 = **version 7**（0x70000000）——驱动当时只认 v5，安全拒绝（原设计行为）。
- s3910：`as found` 行 = 驱动完成了全部 MMIO 映射与初始状态读取（GCC/TLMM 真机可达）。
- panic 定位：符号表解析 pc → **`_rail_on+0x294`**；反汇编显示 `rpmh_wait` 被内联后计算
  `rsc + (低32位(rsc) + 0xd04 + 0xd00)` 的野地址——**调用点 `rpmh_wait(TCS(TCS_IRQ_STATUS), …)` 把
  已经展开过 TCS() 的地址又传给了再展开 TCS() 的函数**（goodix.c 同款模式的潜伏 bug，参考机上因
  ldoc2 查名失败未触达）。far 验算：`0xfffffffbf6124000 + 0xF6125A04 = 0xfffffffcec249a04` 与 far
  **逐位吻合** → 修复 = `rpmh_wait(TCS_IRQ_STATUS, …)`（fix2）。

### 7.2 Boot #15（v8）——RPMh 双轨上电成功 + 按键 SPMI v7 全链 probe

`b15-kernel-log.txt`：

```
buttons: version 7: APID->PPID table at core+0x2000, owner table at cnfg+0, observer channels at obsrvr+0x8000*system+0x20*apid
buttons: channel 407 is the PMK8350's power-on block (0x1001300); written by system 0
buttons: channel 434 is GPIO6 of the PM7325 (0x1018d00); written by system 0
buttons: the PMK8350's power-on block says type 0x1, subtype 0x9 (the read took 6 us)
buttons: GPIO6 of the PM7325 says type 0x10, subtype 0x11 (the read took 5 us)
buttons: power-on block: status 0x18 (power released, volume down released); interrupts: edge 0, high 0, low 0, enabled 0
buttons: volume up's pin: mode 0 (input), pull 0 (up), enabled; level high (released)
buttons: step 5: watching power volume-up volume-down, every 16 ms
s3910: the analog supply on (ldoc3 at 3008 mV)
s3910: the I/O supply on (ldoh4 at 1800 mV)
panic(cpu 1): Kernel data abort. at pc 0xfffffff007488904 ... esr 0x96000010 far 0xfffffffb56c7e008
```

- **SPMI v7 表全部命中**：PON=通道 407、GPIO6=通道 434，type/subtype 与 PMK8350 HLOS-PON /
  PM8350-LV-GPIO 规格逐字吻合，总线读 5–6 µs。按键硬件路径真机打通（仅剩事件轮询未长跑）。
- **RPMh 调压器真机写成功**（cmd-db 找到 `ldoc3`/`ldoh4`，TCS 写完成）——PHK110 的 RPMh 通道首次
  全链验证（比 goodix 在参考机的验证更进一步：两个 VRM 资源都写成功）。
- 第二个 panic 定位：pc → `clocks_on` 附近，far − gcc 映射基址 = **0x62008** = sm8450 的 APCS 投票
  寄存器 → **`GCC_SIZE=0x60000` 映射越界**（cape FDT 给 GCC 0x1f4200，投票寄存器在 0x62008 > 0x60000）。
  修复 = GCC_SIZE 取 FDT 原值 0x1f4200（fix4）。
- 8 核同起再次达成（10.403–10.410 s）。

### 7.3 Boot #16（v9）——**零 panic 完整 300 s 会话 + 按键真机事件**（本波按键交付的验收证据）

`logdump-v9.bin` 这次拉到的是 **loader 全量日志**（wave7b 心跳机制每 2 s 落盘），含最后一轮
loader 日志 + 完整内核会话：

- **loader 头部屏证**：`payload entry 'kernel' size e2be18`（=14,859,800 = v9 内核 ✓）、ramdisk
  `4090`（=16,528 = v6 驻留 stub ✓）、**`cmdline: 451 of 607 characters`**（无截断）、
  `jumping to 8434194a8`、`cores for the kernel: 700 600 500 400 300 200 100`。
- **`--- loader_return_after expired ---`（t=300.36 s）**：**项目首个完整 300 s 常驻会话零 panic**
  ——`loader_return_after=300` 设计兑现（此前纪录 b13 = 60 s）。
- **按键真机事件（用户现场按键被逐字记录）**：
  ```
  buttons: power PRESSED at 15.918 s (00:00:15.918 UTC)
  buttons: power released at 16.020 s, after 102 ms
  buttons: volume down PRESSED at 16.326 s
  buttons: volume up PRESSED at 16.633 s / released at 16.769 s, after 136 ms
  buttons: so far 1 presses of power, 1 of volume up, 1 of volume down; now none held;
           1256 reads of the bus, 6 us each (the longest 8), 0 failed
  ```
  另一轮（300 s 完整会话）的分钟汇总：t=21/74/138/202/265 s 五连，**30,006 次总线读、平均 6 µs、
  最长 8 µs、仅 2 次 dropped**（`transfer was dropped` 两行，驱动按设计限报并继续）——SPMI v7
  长跑稳定。
- **s3910 probe 推进与阻塞点**（内核日志段 t=10.44–10.77）：
  ```
  s3910: as found: votes 0x400287c0, clocks 0 0x80000002 0x80004220, rate cfg 0x100000 dfs 0x8020
  s3910: the analog supply on (ldoc3 at 3008 mV)
  s3910: the I/O supply on (ldoh4 at 1800 mV)
  s3910: clocks stay off: 0 0x80000002 0x4220      ← 0x28008 分支投票后不清 bit31
  s3910: its clocks cannot be turned on; no SPI
  s3910: no touch screen
  ```
  注意 **SE4 分支响应了投票**（0x80004220 → 0x4220，bit31 清 = 引擎时钟开）、M_AHB 已开（0）、
  只有 **0x28008 读数固定 0x80000002**（halted + HWCG 位），投票前后不变 → 驱动按设计干净放弃，
  内核继续常驻 300 s（零影响）。
- `launchd stub alive: t=10s…t=290s` 心跳连续（300 s 内 29 跳全数在案）+ 每分钟内存报表
  （free 6069 MB 恒定）→ 会话质量与 b13 相同等级。

### 7.4 S3910 的剩余阻塞点：cape GCC ≠ mainline sm8450（寄存器级定性）

证据链：
1. `0x28008` 读数投票前后恒为 0x80000002（bit31=halted + bit1=HWCG），而同一位图的 bit26（SE4）
   投票立即生效（`0x80004220 → 0x4220`）——若 0x28008 真是 wrap_1_s_ahb，同一写不可能单它不响应。
2. **FDT 铁证**：cape GCC 时钟引用索引 m-ahb=**0x86(134)**、s-ahb=**0x87(135)**，而 mainline
   gcc-sm8450.c 的表里这两个是 118/119（134/135 在 mainline 是 UFS PHY 时钟）；se-clk=0x5e(94)
   与 mainline 一致 → **cape 的 GCC 表中段（含 wrap1 AHB 时钟族）与 sm8450 不同**，mainline 的
   CBCR 偏移（0x28004/0x28008）对 cape 不可信。
3. 结论：需要**权威的 cape/sm8475 GCC 时钟定义**（OnePlusOSS/android_kernel_oneplus_sm8475 的
   `drivers/clk/qcom/gcc-sm8450.c`（cape 分支版）或 LineageOS/android_kernel_motorola_sm8475 同文件；
   本轮 GitHub API 限流未取到，路径已记录）重新推导 wrap1 AHB/SE 族偏移与投票位。
4. **v10 的对策（已构建未刷写）**：(a) s_ahb 停摆降级为告警不阻断——SE4 分支已开、M_AHB 已开，
   引擎是否可用交给 `GENI_FW_REVISION_RO` 探活（SPI 协议版本字节）直接判定；(b) 引擎探活失败则
   **bitbang 回退**（同四脚 GPIO 手驱，只依赖 TLMM，goodix 在参考机已验证的同款实现）——TCM probe
   与 GCC 时钟谜团完全解耦。下轮首刷 v10 即得 TCM probe 证据（预期日志：
   `s3910: TouchComm vN firmware: mode 0x01 (application), part number "…", build id …`）。

### 7.5 用户屏显情报与 UEFI 层报错分析（主代理转发）

用户在 v7 引导现场拍屏确认 `jumping to 8434194a8`（内核已跳转）且 cmdline 上机；另比 v6 时代多出
一组 UEFI 级报错：

```
UsbPwrCtrlLib.GetTypeCPortStatus Port[0]: Failed, Error[Device Error]
UsbConfigPortsQueryConnectionChange: GetTypeCPortStatus returned ERROR (0x7), switching platform to UM...
ReadRealTimeIRQStatus: GetPonRtStatus failed for Power Button, Status = (0x7)
PollPowerKey: ReadRealTimeIRQStatus failed for Power Button, Status = (0x7)
PollButtonArray: PollPowerKey failed Status = (0x7)
ButtonsDxe - PollButtonKeys failed status:0x00000007
```

分析（0x7 = EFI_DEVICE_ERROR）：

1. **这些是 FD 内置的 vendor DXE 驱动**（Oplus/高通 UEFI 的 USB 电源控制库与 ButtonsDxe），跑在
   DXE 阶段——**FD 自 Wave 7 起逐字节未动（8924cb67…），v5/v6/v7/v8/v9 的 UEFI 阶段完全相同**，
   故这组报错不是 payload/内核改动引起的；v6 时代屏拍未含顶部行或 Type-C 状态随线缆状态变化，
   更可能是"一直在、这次拍到"。它们发生在 loader 跳内核**之前**，与本轮内核改动无因果。
2. **① 是否预示内核按键驱动同样失败？——不**。Boot #15/#16 的内核日志给出直接反证：内核侧
   SPMI v7 observer 通道读**同一个 PON RT status 寄存器（0x1310）成功**（type/subtype 6 µs、
   RT 状态 5–6 µs、30,006 次读仅 2 次 dropped）且**真机按键事件全部捕获**。两者访问机制不同：
   DXE ButtonsDxe 走 UEFI 自己的 SPMI/PON 栈（其表/时序可能仍是 v5 假设或依赖未初始化的
   Type-C/USB 电源前置条件），内核驱动走 observer 通道 + v7 表 walk（本轮实装）。`switching
   platform to UM` = UEFI 因读不到 Type-C 状态而按 USB 模式继续——引导链照常走到 loader。
3. **② 内核按键驱动是轮询（16 ms 读 RT status/GPIO 电平），不依赖中断**——即使 PON 的 IRQ 路由
   在 UEFI/固件层有问题也不影响；波内取证（t=265 s 时 30,006 读 2 失败）证明长跑可用。
4. `ConvertPages failed …A1000000-A196BFFF` / `Loading driver at …` 两行维持 wave11 的"已知良性
   噪音"定性，不再展开。

### 7.6 流程教训：长会话镜像的回安卓等待

v9（`loader_return_after=300`）每轮 = 300 s 内核 + 引导开销 ≈ 5.2 min，ABL 兜底要重试计数耗尽
（~8 轮 ≈ 40+ min）才自动回安卓。本轮验证的快速通道：**`fastboot set_active a` + `reboot` 直接
切回安卓，30 s 内完成**（主代理已执行）。后续波次约定：长会话（≥300 s）镜像刷写验证后由主代理
或执行代理直接 set_active a 切回，不等 ABL 兜底；logdump 是独立分区，切槽不影响其内容（本轮
实测：切槽后拉到的 logdump 即最后会话的完整日志）。

## 8. 下一轮预期（Touch probe 冲刺 + 点按上报）

1. **首刷 v10**（`device-layer/hakios-kernel-v10.bin` 已构建、自检编译零错；重打 payload 即可，
   cmdline 不变）：预期日志要么 `s3910: serial engine: firmware 0x…01`（引擎活着 → TCM probe 直接
   跑）要么 `s3910: … trying the pins by hand` → `s3910: the chip answers on pins driven by hand`
   → TCM probe 跑。**硬验收行 = `s3910: TouchComm vN firmware: mode 0x01 (application), part
   number "…", build id …`**。
2. **cape GCC 时钟表研究**（并行）：取 OnePlusOSS/android_kernel_oneplus_sm8475（branch
   oneplus/sm8475_s_12.1_oneplus_10t_5g）`drivers/clk/qcom/gcc-sm8450.c`（cape 版）或
   LineageOS/android_kernel_motorola_sm8475 同文件，把 wrap1 AHB/SE 族 CBCR/RCG/投票位换成 cape
   权威值（注意本波已证：投票寄存器 0x62008 与 SE4 CBCR 0x284dc 行为正确，错误集中在 AHB 族）。
3. **点按上报验证**（probe 达成后）：300 s 窗口内真人点屏即可——`s3910: finger N at X, Y` 行 +
   每分钟状态行计数即证据；配合动作清单：① set_active b 重启后不按键等内核起来（~10 s）；
   ② 屏上滚动日志出现后指尖点/滑几次（慢、间隔 1 s）；③ 等 300 s 定时返回，主代理切回安卓拉
   logdump。坐标翻转备选 `touch_flip=1/2/3`；INT 不触发备选 `touch_poll_us=2000`。
4. **流程**：长会话镜像验证后立即 `set_active a` 切回（§7.6），不等兜底。
5. 若 v10 的 TCM probe 达成，v0.3 触摸剩余项 = 显示联动（v0.2 NT37705）后的坐标标定（flip/归一化
   核对）与报告速率（DC 动态配置）。

## 9. 回退方式

- **重刷 v6**（复检 27/27、sha `c69c64c4…` 未动）：`adb reboot bootloader` → `usbipd attach --wsl
  --busid <X>` → WSL root `fastboot flash boot_b /mnt/c/.../device-layer/udon-hakios-grafted-v6.img`
  → `set_active b` → `reboot`（= Boot #13 行为：60 s 常驻 + 8 核上线）。
- 兜底红线未动：slot a 原厂安卓未刷过；`backups-slotb/` 原厂备份 + `set_active a` 回日常系统。

## 10. 本波自检表

| # | 项 | 结果 |
| --- | --- | --- |
| 1 | live FDT 触摸/按键/仲裁器/GCC 提取（含 cape ≠ sm8450 发现） | ✅ §1.1/1.2/7.4 |
| 2 | GPL 双驱动族协议研读（v1+v2 双实现） | ✅ §1.3 |
| 3 | S3910 驱动四轮编译全 0 error | ✅ §4 |
| 4 | buttons.c taro 化 + SPMI v7（默认行为不变） | ✅ §2.2 |
| 5 | drivers-check / boot-args --check | ✅ §6 |
| 6 | QEMU 冒烟全链到标准终点 | ✅ §5 |
| 7 | v7/v8/v9 三镜像自检 32 项 | ✅ §6 |
| 8 | v6 基线复检 27 项 | ✅ §6 |
| 9 | 刷前 sha 校验 + product=taro 三轮 | ✅ §7.0 |
| 10 | 按键真机事件取证（三键 press/release + 30,006 读统计） | ✅ §7.3 |
| 11 | 300 s 完整会话零 panic + 8 核同起 | ✅ §7.3/7.1 |
| 12 | 两个 panic 根因寄存器级定位并修复（far 逐位验算） | ✅ §7.1/7.2 |
| 13 | v10 交接件构建（s_ahb 非致命 + bitbang 回退） | ✅ §7.4/§8 |
| 14 | 红线（只 boot_b / 禁重建 FD / loader.c 零改动 / 只新增 / 无 git reset） | ✅ |
