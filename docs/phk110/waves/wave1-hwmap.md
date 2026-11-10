# 阶段 1 · 2026-11-02 · PHK110 硬件清单与上游驱动集的对应关系

> 版本：1.0（2026-11-02）· 调查代理 B（只读取证 + GPL 源码调查）
> 服务于：R1（NT37705 面板序列）、R2（S3910 触摸驱动）、v0.2「第一缕光」、v0.3「触感」、v0.6「连接」、v0.7「全网」

---

## 0. 证据源与方法

| 证据源 | 内容 |
|---|---|
| `intel/phk110-fdt.dtb` | 手机真实设备树（4470 节点 / 28409 属性）。解析工具：`intel/wave1b-scripts/fdt_dump.py`（全量 dump → `fdt-full.txt`）、`fdt_phandle.py`（phandle→节点解析） |
| `upstream/hakios-xnu-kernel/drivers/**`（每文件头注释） | redwood 驱动的硬件参数与数字来源 |
| `upstream/hakios-sm7325/device.conf` | redwood 官方 status 表 |
| **OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475**（GitHub，GPL 官方源） | PHK110（项目代号 **udon-22803**，板级 **cape**）的显示面板 DTSI、触摸驱动、按键/充电/haptic overlay、音频 overlay |
| OnePlusOSS/android_kernel_oneplus_sm8475 | 通用内核树（u_14.0.0 分支 = kernel 5.10.168；含 PHK110/11R/AcePro 分支；techpack 为 stub，模块在上一仓库） |
| 公开主线 Linux | panel-novatek-nt37705.c（Fairphone Gen6 上游化驱动，协议参考）；ipa v4.5 数据（SM8450） |

**判定档位**：`相同`（直接复用）/ `需适配`（改参数/表/基址）/ `需新写`（驱动架构不同，参照骨架+源码重写）。

**调查中已落盘的 GPL 源文件副本**（`intel/wave1b-scripts/`，供后续代理直接使用）：
`phk110-panel-nt37705.dtsi`（4077 行，完整面板 init 序列）、`udon-22803-cape-overlay.dts`、`udon_22803_tp_config.dtsi`、`udon_22803_common.dtsi`、`cape_overlay_common.dtsi`、`cape-pmic-overlay.dtsi`、`udon_audio.dtsi`、`synaptics_touchcom_core_dev.h`、`fdt-full.txt`。

**运行时取证说明**：调查期间 adb（192.168.43.29:42621）从在线（`ro.product.device=OP5913L1`）转为离线（10061 连接拒绝，疑似无线调试随熄屏关闭）。运行时交叉验证项未执行，全部结论改由 FDT + GPL 源码双源支撑；恢复 adb 后的重跑清单见 §7。

---

## 1. 上游 redwood 驱动集盘点

`drivers/` 共 48 个 hakios.* 文件，子系统分布：audio 7、bluetooth 1、camera 2、core 5、gpu 2、haptic 1、input 4、modem 5、net 2、power 6、storage 7、wifi 6。每文件头注释自述其数字来源（Xiaomi MiCode `hakios-s-oss`、Android 运行时设备树、vendor 固件等）。

`device.conf` status 表（上游自述）：

| 功能 | 状态 | 上游实现要点 |
|---|---|---|
| display | works | UEFI framebuffer + GPU 画帧（内核无 DSI 驱动） |
| touch | works | Goodix GT9916 / FocalTech FT3680，SPI SE13，自驱时序/供电/时钟 |
| buttons | works | PMIC PON（power/resin）+ PMIC GPIO（vol up），SPMI arbiter |
| cpu | works | 8 核 + EPSS cpufreq（cpus=8 bootcpu=7 cpufreq=1） |
| gpu | works | Adreno 642L（a6xx），Mesa freedreno 经 msm DRM 接口 |
| storage | works | UFS 经 UEFI 常驻 UFSDxe（loader 页）+ 内核直驱 UFSHC 读 |
| audio | works | ADSP 固件加载 + ASM/ADM/AFE；扬声器 AW88261×2 走 PRI_TDM_RX_0；麦克风 WCD938x AMIC1 |
| battery | partial | ADSP battmgr（PMIC GLINK）只读 |
| haptic | works | Awinic AW86927，I2C qup9，chip id 0x9270 |
| camera | works | 手写 OV02B10 宏距 + S5KHM2SD 广角（CCI/CSI 直驱） |
| torch | partial | PM8350C flash LED 寄存器直写 |
| wifi | works | WCN6750 = WPSS（Hexagon）PIL 加载 wpss.mdt + ath11k 移植 |
| bluetooth | missing | 只读侦察（GPIO 84/85/86） |
| cellular | partial | MPSS PIL + QMI + IPA 4.11/GSI 2.11 + QMAP + en1 |
| thermal | partial | TSENS 状态字直读（27/27 传感器） |
| pmic/socinfo | — | SPMI arbiter 枚举（pmic=1）；SMEM item 137（socinfo=1） |

---

## 2. 映射总表：redwood 驱动 → PHK110 硬件

### 2.1 显示（v0.2 核心，R1 缓解已闭环）

| 项 | redwood | PHK110（FDT + GPL 双证） | 判定 |
|---|---|---|---|
| 面板 | （UEFI fb，内核不碰 DSI） | **NT37705**（Novatek DDIC），天马模组（`oplus,mdss-dsi-manufacture="TIANMA1240"`），1240×2772 DSC cmd，bpp30，4 lane | — |
| panel 节点 | — | `qcom,mdss_dsi_oplus22803_nt37705_1240_2772_dsc_cmd`（cmdline 主选）；同节点 GPL dtsi 完整 init/off/HBM/AOD/qsync 序列 | — |
| DSI 控制器 | — | `qcom,mdss_dsi_ctrl0@ae94000`，compatible `qcom,dsi-ctrl-hw-v2.6`，reg ae94000/4K + dsi-phy-base ae36000；vdda-1p2 | — |
| 时序（120Hz 档） | — | 1240×2772，hfp40 hbp50 hs8，vfp2 vbp8 vs2，DSC：bpc10 bpp8、slice 620×12×2 encoders、scr v1；时钟 0x413b3800 | — |
| 复位/TE GPIO | — | reset=tlmm 3（上拉态 seq `<1 2> <0 5> <1 10>`）；TE=tlmm 86；dynTE=tlmm 23；panel-vout=tlmm 90 | — |
| 供电 | — | `dsi_panel_oplus_optimization_pwr_supply`：vddio 1.8V + vci 3.0V；另有 Iris（oplus,iris7）电源轨（`dsi_iris_pwr_supply`） | — |
| 特性 | — | qsync min 24fps、ADFR、OFP、温度补偿、HBM one-pulse、bl ctl=DCS（4095 级） | — |

**判定：内核侧显示路径 `相同`（继续吃 UEFI fb）；v0.2 真正工作在 UEFI DisplayDxe 面板序列 → `需适配`（bitra DisplayDxe 骨架 + udon RAW 面板配置，序列源见 §4）。**
分辨率/stride 换算 1240×2772（fb 侧 XNU 无需感知面板型号）。

### 2.2 触摸（v0.3 核心，R2 深度分析见 §3）

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 芯片 | Goodix GT9916 / FocalTech FT3680 | **Synaptics S3910**（TouchComm，HBP 传输） | **需新写** |
| 总线 | SPI SE13（0x994000） | SPI **SE4**（`spi@990000`，max 50MHz，驱动用 **15MHz**） | — |
| 中断 | — | tlmm GPIO 21，低有效（flags 0x2008） | — |
| 复位 | — | tlmm GPIO 20，高有效，reset-active 10ms / delay 50ms | — |
| 供电 | PM8350C LDO2（RPMh）+GPIO | vdd 2.8V = **PM8350C L3**（L3C）；vcc 1.8V = **PM8450 L4**（L4H）；enable1v8 gpio=tlmm 97 | — |
| 规模 | — | 10 指，TX16×RX36，1240×2772，int-mode 1，tp_ic_type=2 | — |

DTB 中同一 SPI 总线上共存 4 个触摸节点：`focaltech@0`(disabled)、`synaptics_tcm@0`(disabled, 'synaptics-s3910', 12MHz)、`synaptics_tcm_hbp@0`(**status=okay**, 'synaptics,tcm-spi-hbp', 15MHz)、`goodix_gt9966@0`（残留引用）。**唯一使能的是 HBP 版**，GPL overlay `udon_22803_tp_config.dtsi` 与之逐字一致。firmware-name：`firmware_name = "Hbp"`（v15 overlay；DTB 中为 'Hbp\0Hbp\0'）。

### 2.3 按钮（v0.3）

| 键 | redwood | PHK110（cape_overlay_common.dtsi + FDT 一致） | 判定 |
|---|---|---|---|
| 电源 | PMK8350 KPDPWR_N (116) | PMK8350 KPDPWR_N (116)，中断 [0,0x13,7] | `需适配` |
| 音量+ | PM7325 GPIO6（active low） | **PMK8350 RESIN**（`pon_hlos@1300/resin`，code **115 KEY_VOLUMEUP**，pon-type=1，EDGE_BOTH） | `需适配`（映射与 redwood 相反：resin 在 redwood 是音量-） |
| 音量− | PM7325 RESIN | **PM8350 GPIO6** 经 gpio-keys（active low，pull-up，debounce 15ms，code 114） | `需适配`（redwood 无 gpio-keys 路径，需给 gpio6 加读取逻辑） |

PMIC 从机基址：PHK110 spmi arbiter `qcom,spmi-pmic-arb@c42d000`（core c42d000 / obsvr c400000 / chnls c500000 / intr c440000 — redwood 同布局，redwood 文档记的 "spmi@c440000" 是 intr 区）。芯片组：PMK8350@0、PM8350@1、PM8350C@2、PM8350B@3、PMR735A@4、PMR735B@5、PM8450@7、PM8010@8/@9(+i/j)。**hakios.pmic/buttons 的 observer 通道逻辑可复用，从机号与外设表换掉即可。**

### 2.4 CPU/频率

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| EPSS | `qcom,cpufreq-hw-epss` @0x17d91000，3 freq-domain | **同址** 0x17d91000/92000/93000，3 domain，LUT row 4B，dcvsh 中断 [30,31,19] | `相同`（真机首验时核对 LUT 行数） |
| CPU 拓扑 | 1×A710? (sm7325) | 3×A510 + 4×A710 + 1×X2(cpu7)（阶段 1-A 已证） | `相同`（CONFIG_BOOTCPU=7 沿用） |

### 2.5 GPU（v0.5）

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 芯片 | Adreno 642L（a6xx/gen4），chipid… | **Adreno 730v3**（a7xx/gen7），compatible `qcom,adreno-gpu-gen7-4-0` + `qcom,kgsl-3d0`，`qcom,gpu-model="Adreno730v3"`，chipid **0x07030002** | **需适配（大）** |
| 基址 | — | `qcom,kgsl-3d0@3d00000`（reg 3d00000/256K，rscc 3d50000，qdss 10900000）；SMMU `kgsl-smmu@3da0000`（2 TBU） | — |
| 频点 | — | 顶档 **900MHz**（0x35a4e900），pwrlevels 12 档，initial level 11 | — |
| zap | — | `gpu_microcode_region@8b91a000`（reserved-memory #228） | — |
| 用户态 | Mesa freedreno（a6xx 路径） | Mesa freedreno 已有 a7xx 基础（PLAN R4 判断成立） | — |

### 2.6 存储 UFS

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 控制器 | UFSDxe（UEFI 常驻）+ 内核 UFSHC | **同址** `ufshc@1d84000`（ufs_mem/ufs_ice/ufs_ice_hwkm 三区），2 lane，ICE+HWKM | `相同`（loader 路径不动；内核直驱走同一寄存器布局） |
| 供电/reset | — | vcc=PM8350 L7，vccq=PM8350 L9，HBA=GDSC 187004，reset=tlmm 210 高有效 | — |

### 2.7 音频（v0.6）

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| ADSP | remoteproc `qcom,sc7280-adsp-pas` @0x03000000，adsp.mdt+b02..b36 | **同址** `remoteproc-adsp@03000000`，compatible `qcom,cape-adsp-pas`，PIL+TZ 流程同族（cx/mx AOP 供电） | `需适配`（固件来自 PHK110 /vendor/firmware_mnt；compatible/电压路径换名） |
| 扬声器 | AW88261×2，I2C qup3（0x35/0x34），PRI_TDM_RX_0（AFE 0x9000） | **TFA9874×2**（NXP），I2C `qupv3_se13`（@0xa94000，400kHz，0x34/0x35，reset=tlmm 50，vdd=PM8350 S10），走 **TERT_MI2S**（data pin gpio124；AFE 端口按 q6afe TERTIARY_MI2S_RX，具体码值复核对 q6afe 头） | `需适配`（AFE 端口/组配置全换；TFA9874 需要 init 序列——GPL `vendor/qcom/opensource/audio-kernel`/Oplus tfa98xx 代码可参照） |
| 麦克风 | WCD938x AMIC1 → TX macro | WCD938x 同 codec，但 micbias 2.7V、AMIC1/2/4/5 + VA DMIC0-4，dmic01/23/45/67 gpio 组 disabled（路由见 udon_audio.dtsi） | `需适配` |
| WSA | 无 | wsa-macro+WSA883x 节点 **disabled**（本项目不用） | 忽略 |
| 证明 | — | 音频 overlay：`vendor/qcom/proprietary/audio-devicetree/oplus/udon_22803_audio_overlay_common.dtsi`（sound card=`waipio_snd`） | — |

### 2.8 电池/充电

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 架构 | PM7325B + `qcom,battery-charger` 经 PMIC GLINK/ADSP（UEFI/loader 持有） | **同架构**：`qcom,pmic_glink/qcom,battery_charger`（ADSP battmgr）；充电硬件 PM8350B + SMB139x×2 + SC8517（SVOOC/VOOC，i2c@988000）+ BQ27541 电量计（i2c@980000,0x55） | `需适配`（battmgr opcode/PSY 名与 redwood 同族，需真机核对；vooc 策略节点 voocphy_type=2） |

### 2.9 触觉马达

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 芯片 | **Awinic AW86927**，I2C qup9（0xa84000，0x5a），reset GPIO35，irq GPIO18 | **Qualcomm PM8350B HV-haptics**（SPMI slave3 @f000/f100/f200，compatible `qcom,hv-haptics`）+ SoundWire 从机 `swr_haptics@f0170220`（rx-macro SWR）；LRA=**ELA0809**（`vibrator-type=809`），周期 5882µs（~170Hz），vmax 1260mV，fifo-vmax 8500mV，brake 校准存 PMK8350 SDAM@9d00，PBS @1900 触发 | **需新写**（与 AW86927 完全不同架构；参照 Linux `qti-haptics`/`msm-hv-haptics`/`swr-haptics` 家族 + GPL overlay 参数。建议 v0.3 降级为可选，v1.0 再补） |

### 2.10 Wi-Fi（v0.6，注意架构差异）

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| 芯片 | WCN6750，**WPSS(Hexagon) PIL** 加载 wpss.mdt，AHB + ath11k | **WCN6750（同芯片）但走 PCIe0/MHI**：`qcom,cnss-qca6490@b0000000`（无 WPSS 节点！），`cnss_pci` 挂 `pcie0_rp`（pcie@1c00000），MHI+QRTR（`mhi_qrtr_cnss`） | **需适配（大）**：redwood 的 WPSS bring-up 整条废弃，改 PCIe 上电+MHI+ath11k pci（qca6490 固件族）；好处是免 PIL 流程 |
| GPIO | 84/85/86 | wlan-en=tlmm 80，bt-en=81，sw-ctrl=82，xo-clk=204 | — |
| 供电 | — | aon=PMR735A S2，io=PM8350 S10，dig=PM8350 S11，rfa1=PM8350C S1，rfa2=PM8350 S12，ant-switch=PMR735A L7；AOP mbox（qmp-aop） | — |
| 固件 | wpss.mdt/b02..b07 | **qca6490 fw**（/vendor/firmware/wlan/qca_cld，ath11k PCI 固件族） | — |

### 2.11 蜂窝（v0.7）

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| MPSS | remoteproc @0x04080000，modem.mdt+b00..b29，246MB 区 | **同址** `remoteproc-mss@04080000`，compatible `qcom,cape-modem-pas`，同 PIL/QMI/GLINK/QRTR 流程 | `需适配` |
| IPA | **IPA 4.11 / GSI 2.11** | **IPA 4.5**（`qcom,ipa@3e00000`，`qcom,ipa-hw-ver=0x16`，GSI 同寄存器区，wdi3-over-gsi 等）——比 redwood **旧一代**；上游主线 Linux `drivers/net/ipa/ipa_data-v4.5.c`（SM8450）可直接参照 | `需适配`（**PLAN R3 "IPA v5" 假设应修正为 IPA 4.5**，主线上游有现成数据文件，工作量或比预估乐观） |

### 2.12 热管理

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| TSENS | tsens26xx @c222000+c223000，15+12=27 传感器 | **同基址**两块：`thermal-sensor@c263000`（srot c263000，base c222000）+ `@c265000`（base c223000），compatible **qcom,tsens-v2**，各 **16** 传感器，uplow/critical 中断 [506/508, 507/509] | `需适配`（读法相同，传感器数 27→32，热区表重排；另有 `qmi-ts-sensors`（QMI 传感器，instance 0x43 cdsp / 0 modem）供 modem/cdsp 热区——内核侧只读路径可先忽略） |

### 2.13 PMIC / socinfo / 杂项

| 项 | redwood | PHK110 | 判定 |
|---|---|---|---|
| pmic 枚举 | PMK8350+PM7325（+PM8350C），arbiter 观察者通道 | 8 颗芯片（见 §2.3），arbiter 同布局 @c42d000 | `需适配`（从机表） |
| socinfo | SMEM item 137 | 同（SM8475 soc_id 值不同——正好用于机型防呆校验） | `相同` |
| torch | PM8350C flash@ee00，ch0 125mA | PM8350C flash@ee00 同块；udon overlay 把 torch0/1 `ires-ua` 改为 **5mA 档**（`qcom,ires-ua=<5000>`） | `需适配` |
| 相机 | OV02B10+S5KHM2SD 手写 | 4×`qcom,cam-sensor`（CCI0 mclk0 宽主摄+reset3、CCI1×2）+ OIS + 2×eeprom，具体型号在 sensormodule bin（运行时才可知） | `需新写`（v1.0 后再说；GPL `vendor/qcom/opensource/camera-kernel` 有完整栈可参照） |
| 指纹 | （无） | `oplus,fp_spi`：irq=tlmm 40，reset=41，pw_en=183；pinctrl `goodix_fp`（Goodix 光学/超声模组） | 超出 redwood 状态表，不排期 |
| 蓝牙 | WCN6750 GPIO 84/85/86 | 同芯片同 GPIO 族（81/82 走 CNSS 节点） | `需适配`（随 Wi-Fi） |
| FM | （无） | RTC6226 @i2c@994000,0x64（disabled 总线上残留） | 忽略 |

---

## 3. S3910 触摸协议深度分析（R2）

**结论：S3910 走 Synaptics TouchComm（TCM）协议 v2，SPI 传输层为 HBP（High Bandwidth Protocol）变体，GPL 全源码可参照。**

证据链：
1. **FDT**（手机 DTB）：使能节点 `soc/spi@990000/synaptics_tcm_hbp@0`，compatible `synaptics,tcm-spi-hbp`，chip-name `S3910`，15MHz，`firmware_name="Hbp"`，`tp_ic_type=2`（Oplus 框架枚举：Synaptics），reset/irq/vdd 与 §2.2 全量参数。
2. **GPL 驱动源码**（`vendor/oplus/kernel/touchpanel/synaptics_hbp/`，分支 `oneplus/sm8475_v_15.0.0_ace_2`）：`syna_tcm2.c/h`、`syna_tcm2_platform_spi.c`（SPI 传输）、`tcm/synaptics_touchcom_core_v2.c`（TCM v2 核心）+ `_func_reflash.c`（固件升级）+ `_func_touch.c`（报告解析）+ `_func_romboot.c`（bootloader 引导）、`touch_comon_api/`（Oplus 公共框架）。这与主线 Synaptics TouchComm 驱动家族（syna_tcm2）同源。
3. **协议常量**（`synaptics_touchcom_core_dev.h`）：消息头 4 字节（`MESSAGE_HEADER_SIZE`）；应用状态 `APP_STATUS_OK=0x00`、传输状态 `STATUS_OK=0x01`；`CMD_IDENTIFY=0x02`；`DC_CONTROL_LBP_HBP=0x11`（注释 "2-LBP(default),1-HBP"）；报告 `REPORT_HBP_ACTIVE_FRAME=0x23`。即：同一 TCM 命令集，SPI 上有 LBP（逐字节时序）与 HBP（块传输+专用 attention）两种传输模式，**PHK110 用 HBP**。

**HBP 传输要点**（对 v0.3 驱动编写的影响）：地址/长度按 16bit 大端、块传输时 chip 拉低 attention 表示 payload 就绪、读帧 = 读头 4B（payload 长度）→ 读 payload + CRC；上电后走 `CMD_IDENTIFY`（读取 protocol version/build id），随后 app firmware 模式下订阅 touch 报告。**驱动骨架直接套 `hakios.goodix.c`（自驱 SPI 时钟/供电/复位 + 轮询）+ syna_tcm2 的状态机**；FDT 里 `int-mode=1`（中断不禁用）但上游内核无中断框架的先例（goodix 是轮询），v0.3 建议先轮询 attention GPIO 再优化为中断。
固件：FDT `firmware_name="Hbp"` 对应 Oplus 的 vendor 固件装载（`kernelFwUpdate`/`fwupdate_bootloader=1`）；**出厂固件已在芯片内，v0.3 不需要刷固件**，identify 即可工作。

---

## 4. 面板驱动源码获取路线（R1 缓解，已闭环）

**官方渠道（推荐，全部公开 GitHub，GPL）：**

| 仓库 | 分支 | 内容 |
|---|---|---|
| https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475 | **`oneplus/sm8475_v_15.0.0_ace_2`**（ColorOS 15）/ `b_16.0.0_ace_2`（ColorOS 16）/ `u_14.0.0_oneplus_ace_2` | PHK110 全部外设内核模块+设备树 |
| https://github.com/OnePlusOSS/android_kernel_oneplus_sm8475 | `oneplus/sm8475_u_14.0.0_oneplus_ace_2`（kernel **5.10.168**）等 | 通用内核树（techpack 为 stub，显示模块在上表仓库） |

**PHK110（udon-22803）关键文件路径**（`R=android_kernel_modules_and_devicetree_oneplus_sm8475`，`B=oneplus/sm8475_v_15.0.0_ace_2`）：

- **面板 init 序列（v0.2 的 R1 关键件）**：
  `https://raw.githubusercontent.com/OnePlusOSS/{R}/{B}/vendor/qcom/proprietary/display-devicetree/display/dsi-panel-oplus22803-nt37705-1240-2772-dsc-cmd.dtsi`
  （已验证与手机 DTB 逐字一致；4077 行，含 4 个 timing 档的 on/off/HBM/AOD/qsync/温度补偿全序列。本地副本 `intel/wave1b-scripts/phk110-panel-nt37705.dtsi`）
  UDC 二面板与 Iris 配置：`.../display/pxlw-udon/dsi-panel-oplus22803-nt37705-1240-2772-dsc-cmd-udc-2nd.dtsi`、`pxlw-iris7-cfg-tianma-nt37705-1240-2772-dsc-cmd.dtsi`、`pxlw-iris7.dtsi`
- **显示框架/DSI 主机代码**：`vendor/qcom/opensource/display-drivers/msm/`（dsi_panel.c、dsi_ctrl、dsi_phy）+ `display-drivers/oplus/`（oplus_display_panel*.c：ADFR/OFP/seed/温度补偿框架）
- **项目 overlay 汇总**：`kernel_platform/qcom/proprietary/devicetree/oplus/udon-22803-cape-overlay.dts`（含 haptic 参数、project-id 22803/22881、hw-id 档位）→ include `cape_overlay_common.dtsi`（按键）+ `udon_22803_overlay_common.dtsi`（devinfo/传感器）+ `tp/udon_22803_extra_config.dtsi`（触摸）+ `oplus_chg/oplus-chg-22803.dtsi`（充电）+ `nfc/`、`oplus_uff/`
- **SoC/板级 DTS**：`kernel_platform/qcom/proprietary/devicetree/qcom/cape-*`（cape-pmic-overlay.dtsi 等）
- **触摸驱动**：`vendor/oplus/kernel/touchpanel/synaptics_hbp/`（§3 全清单）
- **音频 overlay**：`vendor/qcom/proprietary/audio-devicetree/oplus/udon_22803_audio_overlay_common.dtsi`；音频内核模块 `vendor/qcom/opensource/audio-kernel/`
- **触摸屏 DTS binding 参考**：`kernel_platform/qcom/proprietary/devicetree/bindings/input/touchscreen/synaptics_tcm_spi.txt`

**备选参照**：
- 上游主线 Linux `drivers/gpu/drm/panel/panel-novatek-nt37705.c`（Fairphone Gen6 / Milos bring-up，Luca Weiss，v4 PATCH 2026-10；命令模式+TE 用法可参照，但 init 序列是 BOE 面板的，**不能**替代 udon 序列）。
- Oplus 同 SoC 机型分支（同仓库 `sm8475_t_13.0.0_ace_pro`/`11r`）可交叉验证面板序列结构；bitra（Realme GT Neo3，SM8475）的 DisplayDxe 已由代理 C 处理。

---

## 5. 与版本门相关的建议排序

**v0.2「第一缕光」（显示）**
1. 用 §4 的 dtsi 抽取 `timing@sdc_fhd_120` 的 on-command（DSC/时钟/复位时序已在 §2.1）→ 生成 Mu-Silicium RAW 面板配置（建议固定 120Hz 单档，qsync/ADFR/OFP 全部先不做）。
2. 面板供电链：vddio 1.8V + vci 3.0V（`dsi_panel_oplus_optimization_pwr_supply`）+ AVDD（Iris 7 电源轨 `dsi_iris_pwr_supply`，若 DisplayDxe 不跑 oplus iris 驱动需评估 AVDD 是否由 PMIC 直给——**风险点，可在真机验证时用 `dmesg`/面板点亮与否二分**）。reset GPIO3，TE GPIO86（cmd 模式必需 TE，DisplayDxe 需配 TE 脚 pinctrl）。
3. DSI-ctrl v2.6 + 4nm D-PHY：bitra DisplayDxe 的控制器驱动大概率同 IP（waipio 系），换地址 ae94000 即可试验（路线②）。

**v0.3「触感」（输入）**
1. 按钮（最便宜）：§2.3 三个键全部经 PMIC（KPDPWR/RESIN/PM8350 GPIO6）——hakios.buttons.c 换从机表 + 反转 resin 语义 + 增加 PM8350 GPIO6 读取（SPMI observer 已有）。
2. S3910：按 §3 实现 `hakios.syna.c`（goodix 骨架 + TCM v2/HBP 状态机），15MHz SPI SE4、GPIO21 轮询、GPIO20 复位、L3C/L4H 上电顺序（hbp 节点：power-on 200ms 延迟）。
3. haptic 降级为可选（PMIC haptics 是新架构，v0.3 验收不依赖）。

**v0.6/v0.7 排期修正**
- Wi-Fi：**放弃 WPSS 路线**，v0.6 直接做 PCIe+MHI（qca6490 固件、ath11k_pci）。CNSS 供电 GPIO80/81/82 与 6 路调节器在上电序列里。
- 蜂窝：R3 的 "IPA v5" 修正为 **IPA 4.5**（`qcom,ipa-hw-ver=0x16`），主线 `ipa_data-v4.5.c` 是现成参照；MPSS PIL 流程同 redwood（换固件）。
- 音频：ADSP PIL 同族；扬声器改 TERT_MI2S + TFA9874（I2C init 序列需从 GPL audio-kernel/Oplus tfa98xx 代码提取，**注意 TFA98xx 固件/校准在 /vendor**）。
- 电池：GLINK/battmgr 直接试 redwood 协议，失败再比对 udon 充电 overlay 的 PSY 名。

**真机差异最小化提示**：UFS（同址）、EPSS cpufreq（同址）、TSENS（同基址）、ADSP/MPSS remoteproc（同址）——这四块在 v0.1 内核日志验证时预计只差参数表。

---

## 6. 运行时取证 pending（adb 恢复后重跑，全部只读）

```bash
adb connect 192.168.43.29:42621
adb -s 192.168.43.29:42621 shell getprop | grep -iE "ro.build.fingerprint|wlan|wcn|display|touch|fingerprint|haptic|panel"
adb -s 192.168.43.29:42621 shell "su -c 'cat /proc/bus/input/devices'"          # 确认触摸设备名(synaptics_tcm_hbp)/gpio-keys 名
adb -s 192.168.43.29:42621 shell "su -c 'ls /sys/bus/spi/devices /sys/bus/i2c/devices'"
adb -s 192.168.43.29:42621 shell "su -c 'ls /sys/class/leds'"                   # haptic: qti-haptics? backlight: lcd-backlight?
adb -s 192.168.43.29:42621 shell "su -c 'cat /proc/device-tree/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_oplus22803_nt37705_1240_2772_dsc_cmd/oplus,mdss-dsi-manufacture'"
adb -s 192.168.43.29:42621 shell getprop ro.vendor.oplus.project  # 期望 22803
```
交叉验证点：触摸 input 名（应为 `synaptics-tcm`/`tp_*`）、leds 里 `qti-haptics`（证明 PMIC haptics）、`/sys/bus/spi/devices` 出现 `spi0.0`（S3910）。

## 7. 本调查未决项

- AVDD/Iris 供电轨的实际来源（UEFI 层是否需要 Iris 初始化）→ 真机验证试验或读 `abl-uefi-extract`。
- TFA9874 的 init/固件装载细节（v0.6 才需要）。
- 相机 4 颗 sensor 型号 → 需运行时 `dumpsys` 或 sensormodule bin 解析。
- 首次真机 logfs 回读后复核：EPSS LUT、TSENS 32 路读数、UFSHC 探测。
