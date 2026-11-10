# 阶段 2 · 2026-11-02 · sm8475 SoC 层与设备配置填充

> 2026-11-02 · 输入：`docs/waves/wave1-socargs.md`（代理 A）、`docs/waves/wave1-hwmap.md`（代理 B）、
> `upstream/hakios-sm7325/`（redwood 范本）、`upstream/hakios-xnu-kernel/docs/porting/index.md` + `docs/configs.md` + `docs/porting/repositories.md`。
> 全部改动限于 WSL `~/hakios/kernel/devices/phk110/`（未触碰 `uefi/**`、upstream/、手机）。

**结论先行：`tools/hakios-device.py check phk110` 通过；`make phk110_defconfig` → `make config` → `make kernel` 三步全部按预期完成，
内核产物 `hakios-kernel`（14,841,368 B ≈ 14.8 MB）已生成，四个 SoC 家族驱动（cpufreq/thermal/socinfo/pmic）确认编入，
SOC=sm8475 / CPUS=8 / BOOTCPU=7 全部生效（`kernel.ver=2.1.13-hakios-darwin22.5-sm8475-g96ffbc53`）。
除 make-kernel 声明"属正常"的 kext symbol-set 检查外无任何构建错误，无需上游改动。**

---

## 1. 各文件最终内容

全部位于 WSL `~/hakios/kernel/devices/phk110/`（下文路径省略前缀）。写入方式：Windows 暂存目录起草 → `tr -d '\r'` 拷入 WSL（保证 LF）。

### 1.1 `soc.args` — 完整 16 行 + 溯源注释

结构：文件头注释（数据来源 = soc-args.py 对 phk110-fdt.dtb 的输出 ∪ 人工补的 4 个，指向 wave1-socargs.md）；
12 个工具所得值 + 4 个手工值，每个手工值前面有独立注释块给证据：

| 值 | 注释要点 |
|---|---|
| `soc_cmd_db=0x80860000` | `/reserved-memory/aop_cmd_db_region@80860000`；与内核内置默认（CMD_DB_PHYS_DEFAULT）相同，仍写出保持自描述 |
| `soc_mpss_mem=0x8bc00000` | `mpss_region@8bc00000`（306 MB），remoteproc-mss@04080000 的 memory-region 首项；**与 redwood（0x8b800000）不同，必需** |
| `modem_ipa_fw_at=0x8b910000` | `ipa_gsi_region`（PIL 实际把 IPA 固件载 gsi 区，hakios.mpss.c 注释 + redwood 日志旁证）；给出真机验证法 `dmesg \| grep ipa_fws`，若载 0x8b900000 则改值 |
| `soc_pas_mpss=0x4` | Cape FDT 无 `qcom,pas-id`；4 = 驱动默认 PAS_MPSS_DEFAULT。**注释明确写"沿用驱动默认、未真机验证"，首次 modem SCM_PAS_INIT_IMAGE/MEM_SETUP 步骤须复核** |

行序按 wave1-socargs.md §3b 的规范排布。运行链路验证：经 `tools/soc-only-changes.sh` 解析得 16 行实参、压平 338 字符（见 §3 注意事项）。

### 1.2 `soc/soc.conf` — 仿 sc7280/soc.conf 全六字段

```
soc sm8475
	title       Qualcomm SM8475 family (Snapdragon 8+ Gen 1; cape, taro)
	vendor      Qualcomm
	cores       8, the biggest is core 7
	gpu         Adreno 730
	maintainer  PHK110 port, led by ZCode agent (README.md)
```

### 1.3 `soc/configs/sm8475.config` — SoC 家族片段（仿 sc7280.config 写法）

注释块写 SoC 家族事实：8 核（3×A510+4×A710+1×X2）、EPSS@0x17d91000 与 SC7280 同址、双 TSENS v2（c222000/c223000，各 16 传感器，
对比参考家族 27——首次真机运行核对计数与热区表）、SMEM item 137、SPMI arbiter@0xc42d000；THERMAL 默认 105 °C 交还 loader 的说明照抄规范。
设置项：

```
CONFIG_SOC="sm8475"   CONFIG_CPUS=8   CONFIG_BOOTCPU=7
CONFIG_CPUFREQ=y  CONFIG_SOCINFO=y  CONFIG_THERMAL=y
# the drivers of this SoC family: a device with it gets them from here, ...
CONFIG_HAKIOS_CPUFREQ=y  CONFIG_HAKIOS_SOCINFO=y  CONFIG_HAKIOS_THERMAL=y  CONFIG_HAKIOS_PMIC=y
```

### 1.4 `configs/phk110.config` — 设备片段，起始最小化

- `CONFIG_DEVICE="phk110"`；所有手机驱动显式 `# CONFIG_HAKIOS_* is not set`（haptic、goodix、modem/QMI、wifi、adsp 族等全部关——
  文件头注释逐条给出 wave1-hwmap 的判定：S3910 触摸需新写（v0.3）、PM8350B haptic 架构不同（v0.3 可选）、Wi-Fi 走 PCIe/MHI 非 WPSS（v0.6）、
  IPA 4.5（v0.7，地址已在 soc.args）。
- **相对骨架的关键修正**：删掉了骨架里的 `# CONFIG_HAKIOS_CPUFREQ/SOCINFO/THERMAL/PMIC is not set` 四行——
  `hakios-config.py` 的 overlay 规则是"含入文件先行、本文件胜出"，设备片段不 unset 才能让 `sm8475.config` 的 `=y` 生效
  （repositories.md："so that the device has them whatever it leaves out of its own"；redwood 的 redwood.config 同样不 unset SoC 驱动）。
- `CONFIG_FIRMWARE` 保持 common 内核的 "device"（骨架注释保留）；本配置不使能任何要固件的驱动，`needs` 判"nothing needed"，检查不报错。

### 1.5 `configs/phk110_defconfig` — include 顺序确认正确

```
#include common_defconfig
#include sm8475.config
#include phk110.config
```

与 redwood_defconfig 模式逐行同构（common → SoC → 设备）；头注释改为如实描述"本配置尚不需要拉固件"。
`make` 输出证实解析顺序：`made from defconfig, common_defconfig, sm8475.config, phk110.config, phk110_defconfig`。

### 1.6 `device.conf` — 补全 + 诚实的最小状态

```
device phk110
	title       OnePlus Ace 2
	vendor      OnePlus
	soc         sm8475
	defconfig   phk110_defconfig
	firmware    pull-firmware.sh
	maintainer  PHK110 port, led by ZCode agent (README.md)
	status      display     partial   UEFI's framebuffer, through the loader (to be checked on the phone)
	status      touch       missing   Synaptics S3910 (TouchComm over SPI-HBP), a driver of its own to write; not the reference's Goodix
	status      cpu         missing   nothing seen on the phone yet; what the SoC family says to expect: 8 cores, bootcpu=7, EPSS clocks (cpus=8 bootcpu=7 cpufreq=1)
	status      storage     missing   UFS at the same address as the reference's (ufshc@1d84000); read through the loader's UEFI pages until the kernel drives it, not yet seen
```

**关于"unknown"级别**：任务书建议标 unknown，但工具只接受 `works|partial|missing`（`hakios-device.py` STATES 元组，写 unknown 直接报错）。
按 porting/index.md §4 的规范落位：未在真机见过的 = `missing`（附说明，cpu 一行写明"预期 cpus=8 bootcpu=7，但 nothing seen"）；
display 保留 new-device 模板的 `partial + to be checked`（"written and not yet seen"）。文件头注释声明本表全部不是结果。

### 1.7 `pull-firmware.sh` — 占位（新增）

device.conf 的 `firmware` 键要求文件存在（工具 `os.path.isfile` 检查），故新增占位脚本：注释写明四个将来的固件目录
（fw-gpu/fw-wifi/fw-dsp + modem 的 /vendor/firmware_mnt，指向 redwood 的脚本为范本），执行时打印"nothing in configs/phk110.config
wants firmware"并 `exit 1`（绝不静默成功）。已 `chmod +x`。

### 1.8 `README.md` — 与实态同步（骨架陈旧信息修正）

- SoC 表中 4 个 `(not found)` 行填上实值与来源注记（mpss_mem 标 DIFFERS FROM REFERENCE；pas_mpss 标 NOT YET VERIFIED）。
- "Cellular … IPA layout is for IPA 4.11"（new-device 模板照抄 redwood 的错话）→ 改为"this phone's IPA is a 4.5 … ipa_data-v4.5.c is the map"。
- 配置示例里 `sc7280.config` 占位 → `sm8475.config (the SM8475 family, in soc/configs/)`。
- 触摸/GPU/Wi-Fi/音频/haptic 各条按 wave1-hwmap 的判定改写。
- 新增一段运行注意：run 脚本只发与 redwood 不同的值（8/16 条）；无 redwood 检出时全 16 条约 338 字符，提示 `sync redwood` 或设 `SOC_DEFAULTS`。

---

## 2. 验证三步的实际输出（WSL `~/hakios/kernel`）

### 2.1 `tools/hakios-device.py check phk110`

```
hakios-device: 1 repositories checked (phk110), all hold together
```

`list`：`device phk110  OnePlus Ace 2  (not in the manifest)  [0 works, 1 partial, 3 missing]`（状态计数与 device.conf 一致）。

### 2.2 `make phk110_defconfig`

```
tools/hakios-config.py defconfig phk110
hakios-config: .config made from defconfig, common_defconfig, sm8475.config, phk110.config, phk110_defconfig
hakios-config: 52 characters of boot-arguments; kernel.ver=2.1.13-hakios-darwin22.5-sm8475-g96ffbc53
```

### 2.3 `make config`（合并结果确认）

```
HakiOS configuration .config, kernel.ver=2.1.13-hakios-darwin22.5-sm8475-g96ffbc53
drivers built in: virtio_sound socinfo virtio_input virtio_net cpufreq thermal pmic virtio_blk
drivers left out: adsp speaker sound mic bt camera torch adreno haptic goodix buttons qmi modem battery battguard ufs wifi
  CONFIG_DEVICE        = "phk110"       (a fact about the build)
  CONFIG_SOC           = "sm8475"       (a fact about the build)
  CONFIG_FIRMWARE      = "device"       (a fact about the build)
  CONFIG_CPUS          = 8              -> cpus=8
  CONFIG_BOOTCPU       = 7              -> bootcpu=7
  CONFIG_CPUFREQ       = y              -> cpufreq=1
  CONFIG_UFS           = 2              -> ufs=2
  CONFIG_SOCINFO       = y              -> socinfo=1
  CONFIG_THERMAL       = y              -> thermal=1
boot-arguments: cpus=8 bootcpu=7 cpufreq=1 ufs=2 socinfo=1 thermal=1
firmware wanted from the phone: none
```

SOC=sm8475 / CPUS=8 / BOOTCPU=7 生效 ✓；无 PROBLEM 行（类型/依赖/固件/命令行长度检查全过）✓。
CONFIG_UFS=2 来自 common 内核（UFS 参数符号），无对应驱动编入，v0.1 真机验证只是带参不带驱动，属新设备默认形态。

### 2.4 `make kernel`

构建日志（xnu-build.log）中四个 SoC 驱动确认编译：`CC hakios.socinfo.o`（:973）、`CC hakios.cpufreq.o`（:980）、
`CC hakios.thermal.o`（:981）、`CC hakios.pmic.o`（:987）。结尾（预期中的 kext symbol-set 检查失败 + make-kernel 判定行）：

```
exported name not in import list: IOService::Terminate(unsigned long long, IORPC)
make[5]: *** [.../BUILD/obj/DEVELOPMENT_ARM64_BCM2837/config/Makefile:121: check_all_exports] Error 1
...(仅 check_all_exports / config_all / all 链，全部属于 symbol-set 步骤)...
make-kernel: built: hakios-kernel (xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837)
make-kernel: (exit status 2 is the kext symbol-set checks failing, as they do on this configuration; see tools/make-kernel.sh)
```

`make-kernel.sh` 的 judge 判定为"只失败在 symbol-set 步骤"（无任何 compile/link 级意外失败目标）。

### 2.5 产物

| 文件 | 大小 |
|---|---|
| `~/hakios/kernel/hakios-kernel`（构建树根，工具链取用的名字） | **14,841,368 B ≈ 14.2 MiB** |
| `~/hakios/kernel/xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`（原件，同字节） | 同上 |

与 qemu-open 那次（~15.7 MB）同量级、略小：配置不同（open 单核 profile vs phk110；两边驱动集不同），judge 通过 + 四驱动编入是本判定依据，
大小差异不构成问题。SOC 名已进版本串（`…-sm8475-g96ffbc53`），内核内版本由 loader 经 `kernel.ver=` 传入（hakios.version.c 的机制）。

---

## 3. 遇到的问题与处置

| # | 问题 | 处置 | 留给 |
|---|---|---|---|
| 1 | 骨架 `phk110.config` unset 了 4 个 SoC 家族驱动，按 overlay 规则会覆盖 `sm8475.config` 的 `=y`（设备片段胜出） | 删掉这四行 unset；`make config` 证实 cpufreq/thermal/socinfo/pmic 编入 | 已闭环 |
| 2 | 任务书建议 status 标 "unknown"，但 `hakios-device.py` 只接受 works/partial/missing（写 unknown 报错） | 未验证项一律 `missing` + 说明注记；cpu 注记写明预期值（expected 8 cores bootcpu=7）；display 沿用模板 `partial` | 已闭环（规范内最接近 unknown 的写法） |
| 3 | `device.conf` 增加 `firmware pull-firmware.sh` 后工具要求该文件存在 | 新增占位脚本，exit 1 防静默；`needs` 输出 "nothing of the phone's own is needed" | 已闭环 |
| 4 | 命令行预算：本树未检出 redwood，`soc_only_changes` 无参照文件时把全部 16 条 soc_*（338 字符）发上内核命令行；52（配置）+338+~260（运行自身）≈650 > 607 上限，可能丢尾巴（loader 会警告） | README 增加说明：真机验证前 `tools/hakios-device.py sync redwood`（对照后只发 8 条，≈200 字符，总长 ≈512，安全）或设 `SOC_DEFAULTS`；不改脚本（非本文件域） | wave 2 真机验证执行者 |
| 5 | WSL 调用时 Git Bash 的 MSYS 路径转换与引号展开把带 `$var` 的内联循环打碎 | 全部改为脚本文件（Windows 暂存 → `wsl bash /mnt/c/...`）执行 | 环境备忘 |
| 6 | （转录 wave1-socargs.md §2，未动上游）驱动编译期常量 `MPSS_MEMORY_SIZE=0x0f600000`（246 MB）< Cape `mpss_region` 的 306 MB；modem 启动（wave 2+）可能越界检查失败 | 不动 upstream/；soc.args 注释与报告均记录此点 | 阶段 3 / 决策 |

除此之外 `make kernel` 无任何配置性或上游代码错误——本 wave 没有需要改上游的项。

## 4. 交付清单（绝对路径，均在 WSL）

- `/home/<host>/hakios/kernel/devices/phk110/soc.args`（16 行 + 溯源注释）
- `/home/<host>/hakios/kernel/devices/phk110/soc/soc.conf`
- `/home/<host>/hakios/kernel/devices/phk110/soc/configs/sm8475.config`
- `/home/<host>/hakios/kernel/devices/phk110/configs/phk110.config`
- `/home/<host>/hakios/kernel/devices/phk110/configs/phk110_defconfig`
- `/home/<host>/hakios/kernel/devices/phk110/device.conf`
- `/home/<host>/hakios/kernel/devices/phk110/pull-firmware.sh`（新增占位）
- `/home/<host>/hakios/kernel/devices/phk110/README.md`（同步实态）
- 构建产物：`/home/<host>/hakios/kernel/hakios-kernel`（14,841,368 B）

未触碰：`devices/phk110/uefi/**`（代理 D 域）、`upstream/**`、手机（本 wave 纯本地构建验证）。
manifest（`devices/manifest.conf`）未加 phk110 条目——按 repositories.md 的发布流程，等真机验证验证后再决定（`list` 显示 "(not in the manifest)" 属预期）。
