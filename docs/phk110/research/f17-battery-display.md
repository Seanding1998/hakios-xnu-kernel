# F17 调研报告：桌面 iOS 电量显示修复（PHK110 燃油计）

日期：2026-11-11 ｜ 执行：F17 调研 ｜ 纯准备工作：零手机、零刷写、零构建
产出：本报告（施工单） ｜ 方法：本仓文档与在盘 FDT 反编译全文 + WSL 内核树（`~/hakios/kernel`，v2.1.13 + PHK110 改动）+ GPL 参考仓（`~/hakios/refs/kernel_oneplus_sm8475`，branch `oneplus/sm8475_b_16.0.0_ace_2`；`refs/modules_dt_sm8475` 同分支）+ 参照项目仓（`refs/ios-sweet`）

> 证据分级：**[实证]** = 文件/行号/寄存器/可复现来源；**[实测转述]** = 上游/参照项目自述的真机结果（我们未复现）；**[推断]** = 类比/待核；**[待核]** = 明确需要真机验证核对。
> 引用缩写：`[FDT]` = 本仓 `intel/wave1b-scripts/fdt-full.txt`（live FDT 反编译全文）；`[TREE]` = WSL `~/hakios/kernel`；`[OSS]` = `refs/kernel_oneplus_sm8475`；`[MDT]` = `refs/modules_dt_sm8475`；`[W12]` = `docs/waves/wave12-touch-buttons.md`；`[SWEET]` = `refs/ios-sweet`。

---

## 0. 摘要（先读这八条）

1. **症状定性（两层根因，都已在案）**：桌面电量"错误/空白"= IORegistry 里没有 `IOPMPowerSource` 服务。第一层：PHK110 配置里 **`CONFIG_HAKIOS_BATTERY is not set`**（`[TREE] devices/phk110/configs/phk110.config:36`）——发布电量服务的 `hakios.battery.c/.cpp` 根本没编进内核；第二层：就算打开配置也没有数据源——上游电池数据的两条来路（loader 的 UEFI 充电器缓存页、ADSP 的 battmgr）在 PHK110 都不存在（ADSP 未启动、loader 无此页）。参照项目 ios-sweet 的 NOTES 给了同款症状的独立证据："**No battery detection** … status bar shows empty red battery"；给它一个静态 100% 的 IOPMPowerSource 后"Battery icon OK" [实测转述]。
2. **修法一句话**：新驱动 `hakios.fuelgauge.c`（设备仓 `devices/phk110/drivers/power/`，s3910 同款宿主方式）从两条**只读**总线取数——I2C 上的 TI 燃油计 bq27541（SoC%/电压/电流/温度）+ SPMI 上的 PM8350B 充电器外设（插入/充电状态）——每个采样周期喂给**已经存在**的 `hakios_battery_report()`；它一路点亮 sysctl、`HakiosBattery`（IOPMPowerSource 子类）、powerd、状态栏/锁屏/设置里的电池。消费链一行不用改。
3. **燃油计硬件已定位**：`[FDT] //soc/i2c@980000/bq27541-battery@55`，status = **okay**，地址 0x55；总线 = GENI I2C @0x980000（qup0，**GPIO26=SDA / GPIO27=SCL**，100 kHz）。寄存器图来自同 GPL 仓的通用驱动 `[OSS] drivers/power/supply/bq27xxx_battery.c` 的 `bq27541_regs`：**SoC%=0x2c、电压=0x08、平均电流=0x14、温度=0x06**（0.1 K）、剩余容量=0x10、满充容量=0x12、循环数=0x2a——全部 2 字节小端读。Oplus 的设备树额外注明 `qcom,batt_bq28z610`（bq28z610 寄存器风格，关键寄存器与 bq27541 同址）。
4. **充电插入检测（ExternalConnected）最小路径**：SPMI 只读 PM8350B（slave 3）的 SMB5 族寄存器：USB 插入 = `USBIN_BASE(0x1300)+0x10`（实时中断状态）的 **BIT(4)**（`[OSS] smb5-reg.h` USBIN_PLUGIN_RT_STS_BIT；`smb5-lib.c` 的 `get_prop_usb_present` 同款）；Type-C 附加 = `TYPEC_BASE(0x1500)+0x0b` BIT(0)（CC_ATTACHED_BIT）。充电中 = `CHGR_BASE(0x1000)+0x06` 的状态枚举（1–4=充电各级，5=终止，6=暂停，7=关闭）。这些外设归 ADSP 固件所有，但 **observer 通道对任何外设都可读**（`[W12]` buttons 先例：读归其它系统所有的 PON/GPIO 外设 30,006 次仅 2 失败）。
5. **两条总线在本机都已真机验证过一半以上**：SPMI v7 仲裁器（core 0xc400000 / cnfg 0xc42d000 / obsrvr 0xc440000，ee=0）= `[W12]` 按键全链真机取证；TLMM GPIO 位带 I2C = redwood 的触感驱动 `hakios.haptic.c`（GPIO36/37 手驱 0x5a 成功的整套 start/stop/bit/read/write 函数）+ 扬声器功放同款。PHK110 侧需换的只是 GPIO 号（26/27）与 TLMM 基址不变（同为 0x0f100000）。
6. **上游为什么没这条路**：redwood 的电量走"音频 DSP 的电池管理"（battmgr，GLINK 通道 PMIC_RTR_ADSP_APPS）或 loader 在 UEFI 里轮询高通充电器驱动写共享页——两条都以 ADSP/loader 在跑为前提。PHK110 的 Android 侧同架构（`qcom,pmic_glink/qcom,battery_charger` + Oplus 充电框架），但我们的 ADSP 音频链路未排期，等 battmgr = 等音频战；SPMI+I2C 直读是近期唯一可走之路，而且 ios-sweet 在另一台 iPhone 上证明了"SPMI 直读 → IOPMPowerSource → 状态栏"整条成立 [实测转述]。
7. **诚实边界（重要）**：① 电量百分比是**燃油计原始值**，ColorOS 显示前做过平滑/校准（Oplus 设备树 `qcom,modify-soc-smooth`/`modify-soc-calibration`），数字可能差几个百分点，验收按"与 Android 同刻读数一致"对拍而不是对 ColorOS 显示值；② 电池是双芯串联（`qcom,vbatt_num=2`），燃油计电压字段是整组还是单芯 **[待核]**（真机验证与 `dumpsys battery` 对拍一次即知，百分比不受影响）；③ PM8350B 充电器外设的 SPMI 读权限未实测——预计与按键同（observer 可读），但要真机验证一行日志确认。
8. **分期**：M1 只读显示（I2C 燃油计 4 件套 + SPMI 插入位，`fuelgauge=1`）→ M2 充电态补全（CHGR 状态枚举、USB 电压电流、适配器字典）→ M3 电压估算回退（VADC 的 `pm8350b_vbat_sns` 通道，燃油计不答时回退，学 redwood loader 的 SOC_ESTIMATED 语义）。充电**控制**（协议、限流、VOOC）始终不在本单范围——只读显示。

---

## 1. iOS 侧消费链（桌面电量到底读什么）

### 1.1 内核发布层 [实证，`[TREE] drivers/power/hakios.battery.cpp` 头注 + 实现]

上游在内核里建一个 `IOPMPowerSource` 子类 `HakiosBattery`：

- 首次电量数据到达时 `OSTypeAlloc` → 填好属性 → `attach(IOService::getPlatform())` → `setName("HakiosBattery")` → `start()` → `registerService()`（`hakios.battery.cpp:207-233`）。
- 用户态 **powerd** 找到该类的每个服务（第一个命名 "InternalBattery-0"），监听 `kIOPMMessageBatteryStatusHasChanged`，然后读它的属性。头注原文给出最小集合：
  - **是否装了电池**：`BatteryInstalled`；
  - **CurrentCapacity 和 MaxCapacity——两者缺一 powerd 就放弃电池**；
  - 充电器是否在、是否充电：`ExternalConnected` / `IsCharging`；
  - 细节视图用的：电压、电流（`Amperage`/`InstantAmperage`）、循环数、适配器字典（`AdapterDetails`：Watts/Amperage/Voltage/Family）。
- 从这些 powerd 生成电源列表（`IOPSCopyPowerSourcesInfo`）并发通知；"状态栏电池、锁屏 Charging、Batteries 小组件、设置 > 电池，一切由此而来"（头注原文）。
- 容量语义：学苹果新机——`CurrentCapacity` 直接放燃油计百分比（`MaxCapacity`=100）；mAh 级数据放 `AppleRawCurrentCapacity` / `AppleRawMaxCapacity`（燃油计学到的满充值）/ `NominalChargeCapacity` / `DesignCapacity`（设计值）。
- 适配器族码映射（`family_code()`，battery.cpp:102-113）：Linux 的 POWER_SUPPLY_USB_TYPE 1/2/3/5/6-8 → IOKit 族码 0xe0004000/4004/4005/4009/400a，未知 → 0xe0004007。

### 1.2 数据通路 [实证，`drivers/power/hakios.battery.c`]

- 汇聚点是**一个函数**：`hakios_battery_report(const struct hakios_battery_state *b)`（`bsd/dev/hakios.battery.c:131-159`）。它更新 `kern.hakios.battery_*` 一组 sysctl（soc/voltage_mv/current_ma/temperature_c/present/charger_present/charging/soc_estimated/full_uah/design_uah/cycles/from_dsp），随后调 `HakiosBatteryReport(b, sizeof(*b))`（C++ 侧）。**任何驱动任何时候调它都会点亮整条链**；没有初始化顺序要求（服务在第一次 report 时才创建）。
- 输入结构（`bsd/sys/hakios.input.h`，与 cpp 内复制体以 `size` 字段互校）：

```c
struct hakios_battery_state {
    uint32_t size;                  /* sizeof(struct hakios_battery_state) */
    int32_t percent_hundredths;     /* 0..10000，百分之一刻度 */
    int32_t voltage_uv;
    int32_t current_ua;             /* >0 = 在进电 */
    int32_t temperature_hundredths; /* 摄氏百分之一度 */
    int32_t present;                /* 有电池 = 1 */
    int32_t external;               /* USB 口上有充电器/电脑 = 1 */
    int32_t status;                 /* Linux POWER_SUPPLY_STATUS_*：1 charging, 2 discharging, 3 not charging, 4 full */
    int32_t charge_uah, full_uah, design_uah, cycles;   /* 未知填 0 */
    int32_t usb_type;               /* Linux POWER_SUPPLY_USB_TYPE_* */
    int32_t usb_voltage_uv, usb_current_ua;             /* 口上给的 */
};
```

- 附件驱动 `hakios.battguard.c`（`battery_stop=<percent>`）：读同一个 sysctl，在"有电池、没插充电器、电量 ≤ 阈值"时把会话干净交回 loader。电池数据一通，这个无人值守保护也自动活过来（插着线跑台架不会误停）。

### 1.3 用户态侧的独立印证 [实测转述，`[SWEET]`]

- `NOTES.md`：无电池服务时"status bar shows empty red battery"（与 PHK110 症状同款）；issue 清单里 "3. Battery: AppleSmartBattery/IOPMPowerSource style service" = 修法定性。
- patch `0062-sweet-touch-power-battery.patch`：`SweetBattery : IOPMPowerSource`，发布键 = `setBatteryInstalled(true)` + `setCurrentCapacity`/`setMaxCapacity` + `setExternalConnected` + `setIsCharging` + 自定义百分比键；30 s 轮询 SPMI；"Battery icon OK（静态 100%）"——**仅一个静态服务就修好了图标**，证明 UI 只认 IOPMPowerSource 服务这一条链。
- 同 patch 的 SPMI 读做了**外设白名单**：只放行 periph 0x10/0x11/0x12/0x13/0x48、slave 0——0x10/0x11/0x12/0x13 正是 SMB 族充电器外设基址（CHGR/DCDC/BATIF/USBIN），与我们第 3 节的取数清单同族，另一台高通机上的同路实证。

---

## 2. 上游现状（redwood 怎么做、为什么我们不能直接抄）

### 2.1 redwood 的两条来路 [实证 + 实测转述]

| 来路 | 机制 | 前提 | PHK110 现状 |
| --- | --- | --- | --- |
| **loader 共享页** | xnuloader 在核 0 持有驻留 UEFI 的高通充电器驱动上下文，轮询后写一页 `struct loader_battery`（magic `RDDBATT!`、version 1、序号双读快照），XNU 侧 `hakios.battery.c` 每 5 s 读（`battery_shared_pa=` boot-arg） | 驻留 UEFI 里得有匹配的 Qualcomm 充电器 DXE | 我们的 loader 无此页——boot-arg 不给就一行日志退出（battery.c:186-188） |
| **ADSP battmgr** | `hakios.adsp.c`（adsp=1，battmgr=0 可关）经 GLINK 通道 `PMIC_RTR_ADSP_APPS` 按属性号问 DSP，答案交 `hakios_battery_report()`；属性号 ≤9 与 Linux `qcom_battmgr.c`（sm8350）一致，其后为本机固件私有（`battmgr=2` 逐属性对拍 `dumpsys battery` 校出） | ADSP 装载并 GLINK 在线 | PHK110 音频/ADSP 链路未排期；等它 = 等音频战 |

上游状态表（`docs/devices/redwood.md`，v2.3.4）自述 battery = "partial：电量经音频 DSP（battmgr）进 UI；本内核下不充电"——**上游自己也没做充电，电量是只读显示**，与我们的分期一致。

### 2.2 上游内核里现成但不适用的驱动 [实证]

`[OSS] drivers/power/supply/qcom/` 有整套 QG（`qpnp-qg.c`/`qg-soc.c`，Qualcomm 燃油计）与 SMB5（`qpnp-smb5.c`/`smb5-lib.c`）驱动，但：

- **live FDT 里没有它们的节点**（pm8350b@3 下只有 temp-alarm/pbs/pinctrl/bcl/hv-haptics；无 qg@、无 charger@）——充电与燃油计算法在 ADSP 固件里跑，AP 侧只留 GLINK 接口（`qcom,pmic_glink/qcom,battery_charger`，`oplus,chg_ops='plat-pmic'`）。redwood 同样如此（其文档原话：选 PM7325B + `qcom,battery-charger` over GLINK/ADSP，"not the local PM7250B/QG layout"）。
- 通用 `ti,bq27541` 兼容串虽在 `[OSS] bq27xxx_battery_i2c.c`，但设备树的兼容串是 `oplus,bq27541-battery`（**不匹配**，Oplus 私有驱动不在 GPL 仓）——不过寄存器图是同一个 TI 芯片族，通用驱动的 `bq27541_regs` 表就是我们要的权威。

### 2.3 ios-sweet 的对应物 [实测转述]

iPhone（PM6150，SDM 平台）上：内核 `bsd/dev/sweet_spmi.c`（SPMI v5 observer 只读 + 外设白名单）→ `SweetBattery`（IOPMPowerSource，30 s 轮询，电压推算 SoC、标注未校准）→ 状态栏图标正常。这是"没有 ADSP/loader 参与也能显示"的直接先例。

---

## 3. PHK110 硬件图（寄存器级）

### 3.1 总线与设备（live FDT 为权威）[实证 `[FDT]`]

| 项 | 值 | FDT 证据 |
| --- | --- | --- |
| 燃油计 | **TI bq27541（Oplus 变体，兼容串 `oplus,bq27541-battery`）**，I2C 地址 **0x55**，status **okay** | `//soc/i2c@980000/bq27541-battery@55`：`reg=<0x55>`、`qcom,modify-soc-smooth`、`qcom,modify-soc-calibration`、`qcom,batt_bq28z610`、`qcom,sha1_key_index=<1>` |
| I2C 控制器 | GENI I2C @ **0x980000**（size 0x4000），目标速率 **100 kHz**（`qcom,clk-freq-out=0x186a0`），GIC SPI 601（0x259 level-high），status okay | `//soc/i2c@980000`；同地址的 `spi@980000` 兄弟节点 disabled |
| 引脚 | **GPIO26（SDA）/ GPIO27（SCL）**，function **qup0**，drive 2，bias pull-up | `pinctrl@f000000/qupv3_se0_i2c_pins/qupv3_se0_i2c_active`（phandle 0xc3 = i2c@980000 的 pinctrl-0） |
| SPMI 仲裁器 | taro v7：**core 0xc400000 / cnfg 0xc42d000 / obsrvr 0xc440000**，ee=0，768 通道 | `[W12]` §1.2 + Boot #14–16 真机取证；cmdline `buttons_core/cnfg/obs` 同值 |
| PMIC 布局 | slave 0 = PMK8350（VADC @0x3100），slave 1 = PM8350，slave 2 = PM8350C，**slave 3 = PM8350B（充电器/燃油计电源芯片）** | `[FDT]` `qcom,spmi@c42d000/qcom,pm8350b@3` 等 |
| 备用电压源 | PMK8350 VADC 有 **`pm8350b_vbat_sns`** 通道（电池电压采样），另有 `batt1_con_therm_adc`（电池座热敏） | `[FDT]` vadc@3100 子节点 |
| ADSP 充电接口 | `qcom,pmic_glink/qcom,battery_charger`（`oplus,chg_ops='plat-pmic'`，`qcom,fg_info_package_read_support`——燃油计细节包走 ADSP 缓冲） | `[FDT]` 9702 行起；ADSP 不跑则全链死 |

### 3.2 bq27541 寄存器图 [实证 `[OSS] bq27xxx_battery.c` `bq27541_regs`（385 行起）]

读法：SMB 标准读字——写命令寄存器地址 → repeated start → 读 2 字节小端（通用驱动的 `i2c_smbus_read_word_data`；我们用 haptic 的位带原语同构实现）。

| 寄存器 | 地址 | 单位/语义 |
| --- | --- | --- |
| CTRL | 0x00 | 控制命令（本单不用） |
| **TEMP** | 0x06 | 0.1 K（十分之一开尔文；摄氏 = 读数/10 − 273.15，通用驱动即 `value − 2731` 后以 0.1 ℃ 用） |
| VOLT | 0x08 | mV（**[待核]** 双芯下整组或单芯，真机验证对拍） |
| FLAGS | 0x0a | 状态位（bit1 SOCF 终态阈值、bit2 SOC1） |
| NAC / RC | 0x0c / 0x10 | 名义/剩余容量 mAh（→ `charge_uah`） |
| FCC | 0x12 | 满充容量 mAh（→ `full_uah`） |
| **AI** | 0x14 | 平均电流，**有符号 mA**（→ `current_ua`，>0 在进电） |
| CYCT | 0x2a | 循环数（→ `cycles`） |
| **SOC** | 0x2c | **百分比 0–100**（→ `percent_hundredths` ×100） |
| DCAP | 0x3c | 设计容量 mAh（→ `design_uah`） |

注：设备树的 `qcom,batt_bq28z610` 指向 bq28z610 寄存器表——其中 TEMP/VOLT/AI/FLAGS/RC/FCC/SOC 与 bq27541 表**逐项同址**（同文件 bq28z610_regs 可证），差异只在 TTF/AE 等，本单不用。Oplus 驱动的 sha1 认证/平滑/校准属于其私有算法层，我们读原始值即可（差异见 §0.7）。

### 3.3 PM8350B 充电器外设（SPMI 只读）[寄存器布局实证 `[OSS] smb5-reg.h` / `smb5-lib.c`；外设基址 [推断，待真机验证以 type/subtype 复核]]

SMB5 族寄存器布局（每外设 256 寄存器，基址×0x100；spmi_read 一次 1–8 字节，`reg` = 基址内偏移）：

| 外设 | 基址 | SPMI id（slave 3） | 关键寄存器 | 用途 |
| --- | --- | --- | --- | --- |
| CHGR | 0x1000 | **0x310** | `+0x06` BATTERY_CHARGER_STATUS_1，低 3 位状态枚举：0 inhibit / 1 trickle / 2 pre / 3 fullon / 4 taper / 5 terminate / 6 pause / 7 disable | **IsCharging**（1–4 在充，5/7 停）；ADSP 固件真实状态机 |
| BATIF | 0x1200 | **0x312** | `+0x82` ADC 通道使能（IBAT BIT6）等 | 备用（电流走 bq27541） |
| USBIN | 0x1300 | **0x313** | `+0x10` INT_RT_STS，**BIT(4)=USBIN_PLUGIN** | **ExternalConnected 最小实现**（`smb5-lib.c get_prop_usb_present` 原样） |
| TYPEC | 0x1500 | **0x315** | `+0x0b` TYPE_C_MISC_STATUS，BIT(0)=CC_ATTACHED | Type-C 层插入佐证 |

- 每个外设 0x04/0x05 有 type/subtype——真机验证第一步读它们确认外设身份（`[W12]` 按键驱动同法：PON=type 1/subtype 9 对规格吻合才信）。**PHK110 的充电器外设归 ADSP 所有，observer 通道按 buttons 先例可读，但这一步必须在第一次刷写日志里拿到实证**。
- ios-sweet 的白名单（periph 0x10–0x13）是同一布局在另一片 PMIC 上的运行实证 [实测转述]。

### 3.4 电池 profile 要点 [实证 `[MDT] oplus_chg/oplus-chg-22803.dtsi`（PHK110 = Oplus 项目 22803，`udon-22803-cape-overlay.dts` 引它）]

- 双芯串联：`qcom,vbatt_num=<2>`；满充浮压 4465 mV/芯（`qcom,default_temp_normal_vfloat_mv`），关机电压 3300 mV/芯，标称 5000 mAh（`qcom,batt_capacity_mah=0x1388`，与 Ace Pro 的 4800/双芯 2430×2 口径一致）。
- JEITA 阈值全套在 DT（cold 6 ℃ / cool 25 ℃ / … / hot 44 ℃，`decidegc` 字段）——我们只读不控，不涉及。
- 充电插入相关 GPIO（Oplus 框架自用）：dischg = PM8350C GPIO9、chargerid 切换 = TLMM64、ship = TLMM126、mcu-en = TLMM92——本单不用（读 USBIN/TYPEC 寄存器即够）。

---

## 4. 修复施工单

### 4.1 文件与接线（对齐既有机制，common 仓库最小改动）

| 动作 | 文件 | 内容 |
| --- | --- | --- |
| 新驱动 | `devices/phk110/drivers/power/hakios.fuelgauge.c`（设备仓，s3910 同款宿主；common 树 `bsd/dev/` 落位经 `tools/hakios-config.py kernel`） | 全部只读。分段：SPMI（仲裁器映射 + v7 表 walk + `spmi_read`，照 buttons.c 收窄为 fuelgauge 所需）→ TLMM 位带 I2C（照 haptic.c，PIN_SDA=26/PIN_SCL=27）→ bq27541 读字 → 状态合成 → `hakios_battery_report()` → 轮询线程 + 分钟级状态行 |
| 设备仓 conf | `devices/phk110/drivers/power/conf` | `driver FUELGAUGE`（default n）+ 文件行 |
| common 接线 | `drivers/core/hakios.stubs.c`：`#ifndef HAKIOS_FUELGAUGE void hakios_fuelgauge_init(void) {}`；`xnu/files/bsd/sys/hakios.input.h` 声明；调用点在 `drivers/input/hakios.input.c` 的 `hakios_battery_init()` 之后（它已是电池链的调用宿主） | qemu/redwood 配置显式 `# CONFIG_HAKIOS_FUELGAUGE is not set` |
| **打开消费端** | `devices/phk110/configs/phk110.config`：`CONFIG_HAKIOS_BATTERY=y`（连带编入 `hakios.battery.c/.cpp`）+ `CONFIG_HAKIOS_FUELGAUGE=y` | 根因第一层；common_defconfig/qemu_defconfig 不动（phk110 专属） |
| boot-args | `fuelgauge=1`（总开关）+ 可选 `fuelgauge_poll_us=`、`fuelgauge_steps=`（学 buttons 的分步停） | `tools/boot-args.py --check` 重新生成文档 |
| cmdline | 现 451/607，余量足够追加 `fuelgauge=1`（`battery=1` 不需要——那是 loader 缓存路） | 打包管线复用 wave12 流程 |

红底线遵守：只读（PMIC 零写、燃油计零写——bq27541 的认证/校准寄存器一律不碰）、无 DT 节点（loader.c 零改动）、`drivers-check.py` + `boot-args.py --check` 绿。

### 4.2 驱动骨架（分段设计，编号即施工顺序）

```
fuelgauge_init()                        /* fuelgauge=1 才做事 */
 ├─ step 1  map arbiter (0xc400000/0xc42d000/0xc440000, boot-arg 可覆盖)
 │          读 version == 0x70000000, 768 channels        /* [W12] 已证值,不匹配即停 */
 ├─ step 2  表 walk 找 4 个外设的 channel (id 0x310/0x312/0x313/0x315)
 ├─ step 3  每外设读 type/subtype (0x04/0x05),与 SMB5 族预期吻合才标记可信
 │          同时把全 id 的身份行打到日志(= 本机充电器外设首次档案)
 ├─ step 4  map TLMM 0x0f100000, I2C 位带试读 bq27541@0x55
 │          验货:连续读 SOC(0x2c)/VOLT(0x08)/TEMP(0x06)/AI(0x14)
 │          合理性:0<=SOC<=100, 2500mV<=V<=9500mV(双芯口径宽取), |AI|<=10000mA(VOOC 快充电流可达 5A+ 级,只挡乱值)
 ├─ step 5  轮询线程(默认 5 s;fuelgauge_poll_us 可调)
 │          spmi_read USBIN+0x10 → external = BIT4
 │          spmi_read CHGR+0x06  → charging 状态枚举
 │          i2c 读 SOC/VOLT/AI/TEMP(/RC/FCC/CYCT 失败不阻断)
 │          组 struct hakios_battery_state → hakios_battery_report(&b)
 │          status 合成:external && (CHGR 枚举 1..4 || AI>50mA) → 1(charging)
 │                       external && 枚举 5 → 4(full);external 其它 → 3
 │                       !external → 2
 │          usb_type:无 Type-C 解析先填 0(family_code 会落到 USBUnknown)
 └─ 每分钟一行:fuelgauge: 63% 7871mV -412mA 30.1C ext=1 chg=2 (60 reads, 0 failed)
```

设计原则与既有一致：分步可停（`fuelgauge_steps=N`）、每步先说后做、读失败降级不阻断（燃油计不答→SOC 置 −1=未知，powerd 按"未知电量"呈现而不是错误数字）、会话结束零回写。

### 4.3 数据通路总览（改完之后）

```
bq27541@0x55 (I2C GPIO26/27 位带) ─┐
                                   ├─→ hakios.fuelgauge.c ─→ hakios_battery_report()
PM8350B USBIN/CHGR (SPMI v7 obs) ─┘        │
                                            ├─→ kern.hakios.battery_* sysctl（battguard 消费）
                                            └─→ HakiosBatteryReport() → HakiosBattery (IOPMPowerSource)
                                                  → powerd (kIOPMMessageBatteryStatusHasChanged)
                                                  → IOPSCopyPowerSourcesInfo/IOPSNotification
                                                  → 状态栏/锁屏"正在充电"/小组件/设置>电池
```

### 4.4 验收行设计（逐级，全部取自驱动日志与桌面对拍）

| 级 | 验收行/动作 | 判定 |
| --- | --- | --- |
| S1 总线 | `fuelgauge: the PMIC arbiter is version 7, 768 channels` | 与 `[W12]` 一致 |
| S2 外设 | `fuelgauge: peripheral 0x310 says type 0x.., subtype 0x..` ×4 | type/subtype 与 SMB5 族规格吻合（真机验证建档；值本身首次记录） |
| S3 燃油计 | `fuelgauge: the gauge answers: SOC 63, 7871 mV, -412 mA, 301 C(0.1K)` | 与 Android 侧 `adb shell dumpsys battery` 同刻读数对拍：percent/voltage/current/temp 逐项一致（电压注意双芯口径） |
| S4 发布 | `HakiosBattery: the battery's power source is up: 63%, not on a charger` | battery.cpp 既有日志行 |
| S5 桌面 | 状态栏出现电池且百分比 = S3 读数；`sysctl kern.hakios.battery_soc` = 63 | 桌面对拍 |
| S6 插拔 | 插线：`ext=1`、状态栏转充电态（锁屏 "Charging"）；拔线还原 | 插拔各一次取证 |
| S7 长跑 | 300 s 会话分钟汇总：0 panic、SPMI 失败率 < 万分之（参照 buttons 30,006/2） | `[W12]` 同法 |

### 4.5 风险与对策

| 风险 | 概率/影响 | 对策 |
| --- | --- | --- |
| PM8350B 充电器外设 observer 读被拒（ADSP 独占策略） | 低/插入检测降级 | 读被拒日志可见；回退 = TYPEC/BATIF 同试；再退 = PON 侧 USB 相关位（第一次刷写 step3 的全 id 档案行就是为这类排查备的） |
| bq27541 不应答（上电态未知/Oplus 认证态） | 中/无百分比 | 先只读验货；不应答时 SOC=−1 干净降级（powerd 显示未知而非错值）；M3 用 VADC vbat_sns 电压推算回退（语义学 redwood loader 的 SOC_ESTIMATED，UI 标注未校准） |
| 原始 SOC 与 ColorOS 显示差数个百分点 | 必然/低 | 验收按 Android 同刻原始值（`dumpsys battery`/`/sys/class/power_supply/battery/capacity`）对拍，不对 ColorOS 平滑显示值；报告如实注明 |
| 双芯电压口径（整组 vs 单芯） | 中/仅细节显示 | 真机验证一次对拍定口径；必要时 ×2 或 ÷2 修 `voltage_uv`，百分比不受影响 |
| SPMI 读延遲拖累轮询 | 低（按键实测 6 µs/读） | 5 s 周期下每轮 ~6 读，可忽略 |
| charging 误报（ADSP 停机时 CHGR 枚举为 7=disable 但硬件仍浮充） | 低/显示级 | status 合成加 AI 符号交叉（>50 mA 才算充）；插拔实测定稿 |

### 4.6 分期交付

- **M1（本单主体）**：§4.1–4.4 全部，只读显示 + 插入检测。验收 = S1–S7。
- **M2**：USB 口电压/电流（USBIN 域寄存器）与适配器字典（Watts/Family）补全 → 锁屏/控制中心的"充电器详情"完整。前提：M1 的外设档案行确认可读域。
- **M3**：VADC 电压估算回退（PMK8350 VADC @slave0/0x31，`pm8350b_vbat_sns` 通道；VADC 转换时序参照 `[OSS]` qpnp-vadc 族，本轮未展开——实施时补寄存器时序研究）。
- **明确不做**：充电使能/限流/协议（PD/QC/VOOC）、燃油计认证与校准写入、JEITA 控制。充电控制 = ADSP 固件职责，我们零干预（上游同样"本内核下不充电"）。

---

## 5. 充电插入检测（ExternalConnected）最小实现路径（专答）

1. **首选**：SPMI 读 slave3/0x313 的 `0x10`（实时中断状态），**BIT(4)** = USB 插入——正是 `[OSS] smb5-lib.c:3323 get_prop_usb_present` 的原样逻辑，硬件位、无需 ADSP 配合、无需中断（轮询读）。寄存器来源 `smb5-reg.h:233 USBIN_PLUGIN_RT_STS_BIT`。
2. **佐证**：0x315 的 `0x0b` BIT(0)（CC_ATTACHED）——Type-C 层；与 1) 并读可区分"有 5V 但未协商"等态。
3. **进阶（M2）**：USBIN 域的输入电压/电流寄存器（smb5-reg.h USBIN 段）供适配器字典；Type-C 族码先填 USBUnknown（0xe0004007）。
4. **时间线**：插入位是纯硬件比较器输出，与我们内核启动先后无关；ADSP 在不在都不影响这一位。真机验证若 observer 读被拒，才需要 §4.5 的回退链。

---

## 6. 诚实边界（查不到/没做的，不编造）

1. **PHK110 上 PM8350B 充电器外设的 SPMI 可读性未实测**——推理链（observer 全外设可读 + buttons 真机 + ios-sweet 白名单同族）都支持，但第一次刷写 step 2/3 就是为此设计的实证步骤。
2. **SMB5 外设 type/subtype 的预期数值**未在 `[OSS]` 树中找到权威表（qpnp-smb5.c 只对 SDAM 读 type）；施工时以"读到什么记什么"建档，不预设值。
3. **bq27541 在 PHK110 的当前上电/认证态**未知（Oplus 私有驱动做过 sha1 认证与校准写入；我们只读测量寄存器，预期不依赖认证态，但未验证）。
4. **双芯电压口径**（0x08 读数是整组 ~7.7 V 还是单芯 ~3.85 V）待真机验证对拍。
5. **VADC 转换时序**（M3 回退路）本轮未研究——`[FDT]` 已证通道存在，寄存器时序留 M3 实施前补。
6. **ADSP 是否在我们内核下活着/充电是否继续**（自主硬件充电 vs ADSP 托管）未验证——CHGR 状态枚举的第一次刷写读数会直接回答（枚举 7=disable 且电池掉电 = 硬件自主充电也未进行，需在报告中如实跟踪电池消耗）。
7. 本轮零手机：所有"真机验证"均标注来源（`[W12]`/上游文档/ios-sweet NOTES），无一是本轮新证。

## 附录 A：本轮取证来源清单

**在盘（Windows 侧）**
- `intel/wave1b-scripts/fdt-full.txt`：i2c@980000 + bq27541-battery@55 全文；pinctrl qupv3_se0（GPIO26/27 qup0）；qcom,pmic_glink/qcom,battery_charger 全文（9702 起）；vadc@3100 通道表（pm8350b_vbat_sns/batt1_con_therm_adc）；pm8350b@3 外设清单
- `docs/waves/wave12-touch-buttons.md`（SPMI v7 全链真机取证、TLMM 基址、cmdline 预算）、`docs/research/f14-sd778g-zendot-survey.md`（方法论：FDT+GPL 为权威；上游电池=ADSP battmgr 定性）

**WSL 侧（只读）**
- `~/hakios/kernel`：`drivers/power/{hakios.battery.c,hakios.battery.cpp,hakios.battguard.c,hakios.pmic.c}` 全文；`drivers/power/conf`；`drivers/core/hakios.stubs.c`（stub 行）；`drivers/input/hakios.input.c`（调用点 232–233）；`drivers/input/hakios.buttons.c`（SPMI v7/observer/find_channel/peripheral 模型）；`drivers/haptic/hakios.haptic.c`（位带 I2C 全套 + TLMM 宏）；`devices/phk110/configs/phk110.config`（CONFIG 行）；`docs/boot-args.md`（battery 族参数）
- `~/hakios/refs/kernel_oneplus_sm8475`：`drivers/power/supply/bq27xxx_battery.c`（bq27541_regs/bq28z610_regs）、`bq27xxx_battery_i2c.c`（兼容串）、`drivers/power/supply/qcom/{smb5-reg.h,smb5-lib.c,qpnp-smb5.c,Makefile}`、`drivers/power/supply/qcom/` 目录清单（QG 全套在但 DT 无节点）
- `~/hakios/refs/modules_dt_sm8475`：`.../devicetree/oplus/oplus_chg/oplus-chg-22803.dtsi`（external gauge/fg_info/vbatt_num/profile）、`.../oplus/udon-22803-cape-overlay.dts`、`qcom/cape-pmic-overlay.dtsi`（无充电器节点 = ADSP 托管佐证）
- `~/hakios/refs/ios-sweet`：`NOTES.md`（症状/里程碑）、`xnu/patches/0062-sweet-touch-power-battery.patch`（SweetBattery + SPMI 白名单 + 发布键）

## 附录 B：术语速查

燃油计（fuel gauge）= 测量并计算电池剩余电量的芯片，PHK110 上是 TI bq27541 族（I2C 0x55）；SPMI = PMIC 的系统总线，SoC 经"仲裁器"访问各 PMIC 外设，observer 通道是只读旁路；SMB5 = 高通 PM8350B 里的充电器外设族（CHGR/BATIF/USBIN/TYPEC 四块）；battmgr = 高通音频 DSP 固件里的电池管理服务，Android 经 GLINK 问它；IOPMPowerSource = Darwin 内核的电源源服务基类，powerd 从它取电量呈现给整个 UI；双芯（vbatt_num=2）= 两节电芯串联，整组电压约单芯两倍。
