# 阶段 43 · 2026-11-12 · 电量显示驱动：燃油计双模式与 62 项自检

> 2026-11-12 · 阶段 43 电量执行记录（施工单 = `docs/research/f17-battery-display.md`）
> 任务书：M1 = phk110.config 开 `CONFIG_HAKIOS_BATTERY` + 给 `hakios_battery_report()` 接安全静态喂食源（ios-sweet SweetBattery 假 100% 先例）；M2 = 真数据源驱动读电压/SoC/温度喂管线（寄存器真值从 PHK110 vendor 源锚定，**不许猜寄存器**）；M3 = 充电态尽力项，做不动如实留 TODO；隔离自测沿 阶段 41 范式；内核增量重建 → **v36 内核候选**记账（阶段 41 GPU 修复 + 本阶段电量修复同树）；不打包不刷写。
> 红线执行：零设备（无 adb/fastboot/usbipd/刷写/wsl --shutdown）✓；`wave42-scripts/` 与 `xnuloader/` 零触碰 ✓；`drivers/gpu/hakios.adreno.c` 零字节未动（改后 sha 仍为 阶段 41 的 `356f5bf4`，本阶段重建天然含其修复——预期不是意外）✓；内核树无 make clean/树级操作，纯增量 ✓。
> 证据分级：[实证] = 文件/字节/sha/行号可复现；[实测] = 本阶段隔离测试结果；[VENDOR] = `~/hakios/refs/kernel_oneplus_sm8475`（GPL 寄存器事实源）；[FDT] = 本仓 `intel/wave1b-scripts/fdt-full.txt`。

---

## 0. 判定（先行）

1. **M1+M2 全落地，M3 尽力项按边界交付（USB 口电压/电流与 VADC 回退如实留 TODO），隔离自测全绿（62/62：vendor 寄存器机械对拍 + 40 断言场景验收器），内核重建绿 → v36 候选 `5b77b418`。设备级验证（桌面图标/百分比/充电态）留待 v36 判定轮**（组装与刷写时机归当时的工作安排）。
2. **两层根因同刀拔除**：`devices/phk110/configs/phk110.config` 的 `# CONFIG_HAKIOS_BATTERY is not set` → **`CONFIG_HAKIOS_BATTERY=y`**（消费端 `hakios.battery.c/.cpp` 自此编入内核，`CC hakios.battery.o` / `C++ hakios.battery.cpo` 在构建日志 :820/:865）；数据源 = 新驱动 **`devices/phk110/drivers/power/hakios.fuelgauge.c`**（948 行，`CC hakios.fuelgauge.o` :846），经 `hakios_battery_report()` 喂既有管线——消费链一行未改 [实证 §2/§6]。
3. **驱动双模（一个 boot-arg 分层 M1/M2）**：`fuelgauge=1` = 静态喂食（SweetBattery 先例：present + 100%（`fuelgauge_static_soc=` 可调）+ 不在充 + 放电态；零总线触碰，日志每行带 "static" 字样）；`fuelgauge=2` = 真读数（SPMI v7 observer 读 PM8350B 充电器四块 + 位带 I2C 读 bq27541 燃油计，默认 5 s 轮询）。**静态 vs 时间模型的取舍**：选静态——时间模型要被告知容量/功耗/起点且误差复利，"估到 0% 而手机还活着"比"如实说满电"更撒谎，且会误触发 battguard 的低电回交；真值是 `fuelgauge=2` 的职责 [§2.1]。
4. **寄存器全部锚定、机械对拍**：bq27541 表（TEMP 0x06/VOLT 0x08/AI 0x14/RC 0x10/FCC 0x12/CYCT 0x2a/SOC 0x2c/DCAP 0x3c）逐项对上 `[VENDOR] bq27xxx_battery.c:385` 的 `bq27541_regs`；SMB5 套（CHGR 状态 0x1006 低 3 位、USBIN 实时中断 0x1310 BIT(4)、TYPEC 0x150b BIT(0)、type/subtype 0x04/0x05）逐项对上 `smb5-reg.h:11/30/24/233/359/365`；状态枚举 INHIBIT=0..DISABLED=7 对上 vendor enum；POWER_SUPPLY_STATUS_*/USB_TYPE_C 对上 `power_supply.h`。**自测的 32 项寄存器对拍全 PASS——对拍是机械的（解析 vendor 原文），不是人眼抄写** [实证 §4]。
5. **诚实边界（设计决定，非缺陷）**：管线 `hakios_battery_report()` 的百分比钳到 0..100、"未知"骑不进去（battery.cpp:126 `percent = percent < 0 ? 0 : ...`）——F17 §4.2 的"燃油计不答 → SOC=−1"语义在此管线上不可表达，会显示成 0%（空电池）。本阶段落法：**gauge 首个过窗 SOC 之前一律不喂**（无服务 = 维持现状图标，好过 0% 错数）；单寄存器读失败 = 该字段保 last-good + 分钟行标 stale；SPMI 全哑 = gauge 独立可喂（插拔位读"口上无线"）[§2.3]。
6. **施工纠偏一笔（在案）**：初版把 `driver FUELGAUGE` 块放进了 common 仓 `drivers/power/conf`，`tools/drivers-check.py` 当场拒绝（"which drivers/map does not list"）——按 S3910 先例**设备仓驱动块必须放设备仓 conf**（`drivers-check.py:91` 对 `d.origin` 驱动跳过 map 检查）。已修：common conf 复位基线（sha 复归 `7935332f`），块落 `devices/phk110/drivers/power/conf`（`38250a22`）；补丁器源码同步改正 + `fix-wiring-v43.py` 留档纠偏动作 [§3.2]。
7. **产物记账（不打包不刷写）**：内核 `hakios-kernel` **`2f1af1cc` → `5b77b418`**（make-kernel 判定过：rc=0，唯一失败 = 已知 kext symbol-set 类，零 `error:` 行；构建含 阶段 41 全部 GPU 修复——同树预期）；驱动 `d0ea41b6`、设备 conf `38250a22`；备份链续 7 个 `.v43-orig`；6 份 diff 留档 `wave43-scripts/diffs/`；构建日志 `/tmp/wave43-kernel-build.log` 名下未落盘（后台会话被收），正式日志 = 树内 `xnu-build.log`（CC 行号即出自它）。**v36 组装清单见 §8，交当时的工作安排。**

## 1. 基线与冻结点

| 工件 | 改前 sha256（前 16） | 改后 sha256（前 16） |
|---|---|---|
| `~/hakios/kernel/hakios-kernel`（构建产物） | `2f1af1cc94354d65`（= 阶段 41 链尾） | **`5b77b418b8c59974`** |
| `drivers/power/conf`（common） | `7935332f74cbc6bb` | `7935332f74cbc6bb`（复位基线，净变化零） |
| `drivers/core/hakios.stubs.c` | `77619eb5362d6118` | `32ba38f8ff293c63` |
| `drivers/input/hakios.input.c` | `805bfb777c28367f` | `8d023496b4a87ddd` |
| `xnu/files/bsd/sys/hakios.input.h`（树内副本同步） | `e4d240135b656be3` | `88af8ce990954107` |
| `devices/phk110/configs/phk110.config` | `cf2c51d2e0328145` | `0c9a370a8da4c952` |
| `configs/common_defconfig` | `38ce95e66291adc1` | `6bb5c33c4b448607` |
| `devices/qemu/configs/qemu_defconfig` | `ddc9ed56d2202971` | `210a796910a9f72e` |
| `devices/phk110/drivers/power/hakios.fuelgauge.c`（新） | —（canonical 在 Windows 仓 `wave43-scripts/`） | `d0ea41b6e3b4148b` |
| `devices/phk110/drivers/power/conf`（新） | — | `38250a226e5974ab` |
| `drivers/gpu/hakios.adreno.c`（红线对账） | `356f5bf4a9f230f0`（阶段 41 修后值） | `356f5bf4a9f230f0`（零字节未动） |

备份：7 个 `.v43-orig`（stubs.c / input.c / input.h / phk110.config / common_defconfig / qemu_defconfig / power/conf——最后者即复位凭据）。drivers-check 现报 11 个"备份不在 map"问题 = 既有 `.vNN-orig` 族噪音（v24 起在案 8 个 + 本阶段同族 3 个），非本阶段新类别。

## 2. M1+M2：驱动设计（`hakios.fuelgauge.c`，948 行）

### 2.1 双模与取舍

- **`fuelgauge=1`（M1，静态）**：`present=1`、`percent=fuelgauge_static_soc×100`（默认 100）、`external=0`、`status=DISCHARGING(2)`、细节字段全零、温度 = 管线自己的"未知"哨兵 `TEMP_NOT_KNOWN(-27350)`（喂进 `hakios_battery_report` 后其 64 位舍入恰回 `-273`——即 `hakios.battery.c` 开机的初始值，不伪造体温）。**为何不用简单时间模型**：需要容量+功耗+起点三输入且误差复利；估穿 0% 而机器仍活着 = 更大的谎，且 battguard（`battery_stop=`）会在假 0% 上交还运行中的会话。真值归 `fuelgauge=2`；静态模式每一行日志自带 "static" 字样，永不冒充真读数。
- **`fuelgauge=2`（M2，真读数）**：SPMI 侧轮询 USBIN 实时中断（插拔位）/TYPEC misc（CC 附着）/CHGR 状态机；I2C 侧位带读 bq27541 的 SOC/VOLT/AI/TEMP 每 拍 + RC/FCC/DCAP/CYCT 每分钟。`fuelgauge_poll_us=`（默认 5 s，10 万–6000 万 µs 窗）、`fuelgauge_steps=1..5` 分步停、`fuelgauge_core=/cnfg=/obs=` 仲裁器三窗覆盖（默认即本机值 0xc400000/0xc42d000/0xc440000，Boot #14–16 同款）。
- **总线互不绑架**：仲裁器拒绝/版本不符 → 充电器读数缺，gauge 独立续喂（插拔位读"无"）；gauge 哑 → 不喂（见 §0.5）。步骤 3 的 type/subtype 档案行"记而不判"——GPL 树无权威 SMB5 type/subtype 表（`smb5-lib.c` 只查 SDAM），F17 §6.2 照办。

### 2.2 状态合成（vendor 表为权威 + F17 风险表一条收紧）

`power_status()` 逐字实现 `smblib_get_prop_batt_status`（smb5-lib.c:2027 起，无 DC 输入分支）：口上无物 = TERMINATE/INHIBIT→FULL(4) 否则 DISCHARGING(2)；口上有物 = TRICKLE/PRE/FULLON/TAPER→CHARGING(1)、TERMINATE/INHIBIT→FULL(4)、PAUSE/DISABLE→NOT_CHARGING(3)。收紧一条（F17 §4.5"charging 误报"对策）：**枚举声称充电而 gauge 电流 ≤ −50 mA（符号正=进电）→ 判 NOT_CHARGING，日志说一次**——ADSP 不在时状态机可能是固件遗留态，电流表是硬件测的。

### 2.3 管线喂食与未知语义

`feed()` 组 `struct hakios_battery_state`（size/present/percent×100/voltage×1000/current×1000/temp/external/status/capacities×1000/cycles/usb_type）→ `hakios_battery_report()`。`usb_type` = CC 附着 → `POWER_SUPPLY_USB_TYPE_C(5)`（family_code(5) = `0xe0004009` USBC，battery.cpp 在案）；否则 0 → USBUnknown。**SOC 未过窗不喂**（§0.5）。静态模式温度哨兵与舍入对拍在自测 S9 逐字验证。

### 2.4 复用件落位（F17 §1 的三件全部复用）

- SPMI v7：`buttons.c` 的仲裁器表 walk / observer 读 / find_channel / `hakios_spmi_lock()` 原样收窄——四外设 id 0x310/0x312/0x313/0x315 = slave3 | SMB5 基址÷0x100；
- 位带 I2C：`haptic.c` 的 start/stop/bit/write/read + **bus_take/bus_give_back 借还礼节**（总线不在静息态即"not touched"，踩不到别的驱动的会话）——PIN_SDA=26/PIN_SCL=27（[FDT] qupv3_se0_i2c，100 kHz `qcom,clk-freq-out=0x186a0`）、TLMM 基址 0x0f100000 不变、地址 0x55（[FDT] `bq27541-battery@55` status okay）；
- 读字 = SMBus read-word（写命令寄存器 → repeated start → 2 字节小端），同 `i2c_smbus_read_word_data`；温度 `value−2731` 换算同 vendor（`bq27xxx_battery.c:2120`）。

### 2.5 合理性窗口（F17 §4.2 step 4 的"验货"）

SOC ≤ 100；VOLT 2500–9500 mV（**双芯口径宽取**：整组 ~8.9 V 与单芯 ~4.5 V 都过窗，口径待真机验证对拍后如有需要再修 `voltage_uv`，百分比不受影响）；|AI| ≤ 10 A（VOOC 快充 5 A+ 级只挡乱值）；温度 −60–90 ℃（百分之一度）。窗外值 = 不信 + 不更新（S10 场景五连测）。

## 3. 接线（补丁器纪律：基线 sha 钉 + 唯一锚 + 永不重跑 + .v43-orig 链）

### 3.1 七处落点（`wave43-scripts/apply-wave43-wiring.py`）

1. `devices/phk110/drivers/power/conf`（新，设备仓）：`driver FUELGAUGE / file bsd/dev/hakios.fuelgauge.c / requires BATTERY / default n / help×3`——**设备仓 conf**，S3910 同款宿主（§0.6 纠偏后形态）；
2. `drivers/core/hakios.stubs.c`：BATTERY 块后补 `#ifndef HAKIOS_FUELGAUGE void hakios_fuelgauge_init(void) {} #endif`；
3. `drivers/input/hakios.input.c`：`hakios_battery_init();` 之后一行 `hakios_fuelgauge_init();`（锚唯一性在案：恰 1 次）；
4. `xnu/files/bsd/sys/hakios.input.h`：电池声明后补原型一行；树内副本（`xnu-src/…/bsd/sys/hakios.input.h`）改前 cmp 断言与仓内全等，改后 cp 同步；
5. `devices/phk110/configs/phk110.config`：BATTERY 翻 y + FUELGAUGE=y + 三行注释（根因第一层修复）；
6. `configs/common_defconfig`：`# CONFIG_HAKIOS_FUELGAUGE is not set`（common 命名每一符号的纪律；S3910 同款先例）；
7. `devices/qemu/configs/qemu_defconfig`：同上 not-set 行（QEMU 无此硬件）。

`requires BATTERY` 由 `tools/hakios-config.py` 的 requires 链强制：FUELGAUGE=y 而 BATTERY=n 的配置直接拒绝构建。

### 3.2 纠偏记录

初版 W1 误落 common `drivers/power/conf` → `tools/drivers-check.py` 报 "builds bsd/dev/hakios.fuelgauge.c, which drivers/map does not list"（其 `check_conf` 对 origin 驱动跳过 map，正是设备仓 conf 的设计通道）。处置：`fix-wiring-v43.py` 恢复 common conf 基线（备份 sha 三方核对）+ 建设备仓 conf；补丁器 W1 段改为建设备仓 conf 的正确形态（重复运行安全）。纠偏后 drivers-check 余 11 问题 = 纯 `.vNN-orig` 备份族既有噪音。

### 3.3 配置链验证

`tools/hakios-config.py defconfig phk110_defconfig` → `.config` 行 26 `CONFIG_HAKIOS_BATTERY=y` + 行 35 `CONFIG_HAKIOS_FUELGAUGE=y`；`check` 绿（42 符号、boot-args 111 字符）；`boot-args.py --check` **绿**（重生成 `docs/boot-args.md`/`configs/boot-args.lst`/`configs/symbols.tsv`——顺带入账 阶段 41 的 `adreno_ddr_type` 遗漏，345 参数目录化）；`docs-check.py` 绿（51 页 137 链接）。**目录盲区如实记录**：`boot-args.py` 的扫描根是 tracked 的 `xnu/`+`drivers/`+`wifi/lx/src/`，`devices/` 仓文件（本阶段驱动、S3910）在扫描外——`fuelgauge=` 系参数不在目录中是**仓库既有属性**（S3910 的 `touch_spi_hz` 先例同况，其目录行挂在共读它的 goodix.c 名下），非本阶段引入；v36 cmdline 经打包流程传参不经 CONFIG_BOOTARGS 检查，不受阻。驱动头注 = 参数的权威文档。

## 4. 隔离自测（零设备，`wave43-scripts/selftest-wave43.py`）

**62/62 全绿**（Python 侧 32 项 + gcc -O0 C 验收器 30 项/40 断言，验收器 rc=0）：

- **寄存器机械对拍（不许猜寄存器的执行件）**：解析 `[VENDOR]` 原文而非抄写——bq27541_regs 八地址逐项、SMB5 基址/偏移/位/掩码逐项（含行号引用打印）、充电状态枚举八值、POWER_SUPPLY_STATUS_*/USB_TYPE_C、peripheral id×4、SPMI v7 表四值（对 buttons.c）、仲裁器三窗、I2C 地址/引脚/速率（对 [FDT] 原文）；
- **管线孪生结构纪律**：judge 的 `struct hakios_battery_state` **逐字提取自 `xnu/files/bsd/sys/hakios.input.h`**（非手抄），15 字段 11 行核对；喂食 mock 重放 battery.cpp 的 size 守卫（refused 计数）；
- **场景验收器（40 断言）**：S1 放电基线（63%/7871 mV/−412 mA/28.00 ℃，容量三件、循环数、usb_type=0 逐字段）/ S2 充电 + Type-C / S3 terminated=FULL / S4a/b paused+disabled=NOT_CHARGING / S5 vendor 无插拔分支 / S6 风险表收紧（FULLON+−500 mA→NOT_CHARGING + 说一次）/ S7 乱 SOC 不喂（captured 计数不动）/ S8 单字段 stale 保留 / S9 温度未知哨兵 + 舍入回 −273 / S10 五窗（2.4 V 拒/9.6 V 拒/4.4 V 单芯过/−32 A 拒/怪温拒）/ S11 静态模式两例（100% 全零细节 + 77% 可调）/ S12 充电器块全哑时插拔位独立降级。
- 开发期内自测自身抓出的 bug 两枚（验收器对拍器的价值实证）：驱动温度字段"千分之一度"命名/打印/窗口错位（fix-temp-v43.py 修正为百分之一度，自测 S1/S9/S10e 复验）；vendor 枚举解析器吞错位（`= 0` 显式行跳过 → token 法重写）。

## 5. M3 充电态：交付边界（能做的做了，做不动的如实 TODO）

**已交付（随 M2）**：①ExternalConnected = USBIN 实时中断 BIT(4)（vendor `get_prop_usb_present` :3323 原样）；②IsCharging/Full/NotCharging = CHGR 状态枚举 vendor 表 + AI 交叉收紧（§2.2）；③Type-C 附着 → usb_type=5 → 适配器字典 Family = kIOPSFamilyCodeUSBC；④适配器字典壳（Watts/Amperage/Voltage 键）随 battery.cpp 的 external 分支自动出现（数值暂零）。

**如实 TODO（锚点在案，等下一阶段）**：①**USB 口电压/电流**（适配器字典的 Watts 真值）= `smb5-lib.c:3525 get_prop_usb_voltage_now` 的 ADC 通道切换舞步（`BATIF_ADC_CHANNEL_EN_REG` 配置-读-恢复 + ADC7 转换），轮询驱动化需 ADC 时序研究——未做，不留半吊子；②**VADC 电压估算回退**（F17 M3 原案：PMK8350 VADC `pm8350b_vbat_sns` 通道，gauge 哑时电压推 SOC）= F17 §6.5 自认"寄存器时序留 M3 实施前补"，本轮未展开——维持 TODO；③Type-C 协商细节（PD 合同瓦数）在 ADSP 固件域，只读观测无路径——与 F17"明确不做"一致。

## 6. 构建（不打包不刷写）

- `tools/make-kernel.sh -j8`：sync-drivers（external-files 把 `devices/phk110/drivers/power/hakios.fuelgauge.c` 落树 `bsd/dev/`）→ `hakios-config.py kernel`（MASTER.hakios/conf files/drivers.h 三件更新）→ 编译。**证据行**：`xnu-build.log` :820 `CC hakios.battery.o`、:846 `CC hakios.fuelgauge.o`、:865 `C++ hakios.battery.cpo`；全日志 `error:` 计数 = **0**；make-kernel 判定过（rc=0，exit 2 = 已知 kext symbol-set 类，与 阶段 41 同款）。
- 产物：`hakios-kernel` = **`5b77b418b8c599747c7febd622484537ce3b7cf4dcb30e128f9d5a6f12b8d5d4`**（v36 内核候选：阶段 41 GPU 修复 + 本阶段电量修复同树）。
- **不打包、不刷写、不 graft**：v36 组装（v35 修后链 + 本内核 + 阶段 41 载体 51a030c3）与刷写时机归当时的工作安排。

## 7. S1–S7 验收对拍清单（全部留待 v36 判定轮，逐条按 F17 §4.4）

| 级 | 验收行/动作 | 判定 | 状态 |
|---|---|---|---|
| S1 总线 | `fuelgauge: the PMIC arbiter is version %#x, %u channels` | 版本 `0x70000000`/768 通道与 [W12] 一致 | **待真机**（驱动行已备，fmt 与 F17 行等价） |
| S2 外设 | `fuelgauge: peripheral 0x3xx (...) says type 0x.., subtype 0x..` ×4 | 第一次刷写建档（记而不判，F17 §6.2）； observer 可读性一次实证 | **待真机** |
| S3 燃油计 | `fuelgauge: the gauge answers: SOC %u, %d mV, %d mA, %d.%02d C` | 与 Android 同刻 `/sys/class/power_supply/battery/{capacity,voltage_now,...}` 对拍；**电压注意双芯口径**（§2.5）；原始值对拍不对 ColorOS 平滑值 | **待真机** |
| S4 发布 | `HakiosBattery: the battery's power source is up: N%, ...`（battery.cpp 既有行） | 首喂触发服务创建 | **待真机** |
| S5 桌面 | 状态栏电池出现且百分比 = S3 读数；`sysctl kern.hakios.battery_soc` 同值 | 桌面对拍 | **待真机** |
| S6 插拔 | 插线 `ext=1`/锁屏 Charging；拔线还原 | 插拔各一次取证；CHGR 枚举 + AI 收紧的实测表现一并记录 | **待真机** |
| S7 长跑 | 300 s 分钟汇总：0 panic、SPMI 失败率对齐 buttons 的 30,006/2 | [W12] 同法 | **待真机** |
| — 备用 | 若 `fuelgauge=2` 总线全哑：`fuelgauge=1` 静态模式单独过 S4/S5（图标不再是红/空，日志带 static） | SweetBattery 先例语义 | 备用路径，cmdline 二选一 |

**v36 cmdline 建议**：追加 `fuelgauge=2`（真读数主路径；预算 607 内现约 451+1 词）。若第一次刷写 S3 失败，回退 `fuelgauge=1` 保显示。

## 8. v36 组装清单（交当时的工作安排）

1. **内核**：`~/hakios/kernel/hakios-kernel` = `5b77b418…`（含 阶段 41 GPU 修复 `356f5bf4` + 阶段 43 电量修复 `d0ea41b6`）；
2. **载体**：沿用 阶段 41 的 `userland/root.apfs` = `51a030c3…`（本阶段零 userland 改动）；
3. **cmdline**：在 v35 链基础上追加 `fuelgauge=2`（§7 备用 `fuelgauge=1`）；
4. **真机判定建议门**：S1→S7 顺序走（S2 档案行是第一手资料，先拿）；S3 对拍用 `adb shell cat /sys/class/power_supply/battery/capacity` 与内核日志同刻比对；S6 插拔各一次；
5. **风险提示**：PM8350B observer 可读性与 bq27541 应答态都是第一次刷写实证项（F17 §6.1/6.3）——失败模式与回退链已在驱动内（档案行 + 静态模式），不会 panic。

## 9. 判定表（六分支式）

| 分支 | 判定 |
|---|---|
| **A M1+M2 落地 + M3 边界交付 + 自测全绿 + 构建绿** | **✓——本阶段实况（§0/§4/§6）** |
| B 补丁锚失配/基线漂移 | ✗（七处基线 sha 全命中，锚恰一次；一处施工纠偏由 drivers-check 抓出并按先例归位，§3.2） |
| C 自测负例仍过 | ✗（S7 乱数据不喂、S10 窗外全拒、S12 哑块降级，验收器 40 断言全过） |
| D 构建失败 | ✗（rc=0，零 error 行，仅已知 symbol-set 类；fuelgauge/battery 编译行在案） |
| E 设备级反证出现 | 未行使（零设备波；S1–S7 留 v36 判定轮，§7） |
| F 域外触碰 | ✗（adreno 356f5bf4 零字节、wave42-scripts/xnuloader 零触碰、零设备操作、树级操作零） |

## 10. 留档路径

| 件 | 路径 |
|---|---|
| 驱动 canonical（Windows 仓跟踪件） | `wave43-scripts/hakios.fuelgauge.c`（WSL 安装副本 sha 全等，自测首项断言） |
| 接线补丁器（7 落点，基线 sha 钉 + 唯一锚 + 永不重跑） | `wave43-scripts/apply-wave43-wiring.py` |
| 纠偏脚本（common conf 复位 + 设备 conf 归位） | `wave43-scripts/fix-wiring-v43.py` |
| 温度字段修正器（开发期一次性，留档） | `wave43-scripts/fix-temp-v43.py` |
| 隔离自测（对拍器 + 验收器生成器） | `wave43-scripts/selftest-wave43.py`（→ /tmp/wave43-selftest.c） |
| diff 留档（6 份） | `wave43-scripts/diffs/*.v43.diff` |
| 备份链 | `~/hakios/kernel/{drivers/core/hakios.stubs.c,drivers/input/hakios.input.c,xnu/files/bsd/sys/hakios.input.h,devices/phk110/configs/phk110.config,configs/common_defconfig,devices/qemu/configs/qemu_defconfig,drivers/power/conf}.v43-orig` |
| 构建日志 | WSL 树内 `xnu-build.log`（CC 行 :820/:846/:865） |

补丁器范式沿 `apply-*-v28..v41.py` 家族：锚恰一次、基线 sha 不符即拒、结构标记计数断言（FUELGAUGE 符号逐文件计数、驱动关键串清单、canonical↔安装副本 sha 全等）。
