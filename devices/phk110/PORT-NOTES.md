# PHK110 移植笔记（redwood → SM8475）

上游参考设备是 POCO X5 Pro（`redwood` / SM7325 / yupik）。本设备是一加 Ace 2
（`PHK110` / SM8475 / cape，一加内部板名 "Udon"）。移植不是逐文件改写，而是
按阶段实测推进：每一条差异都有 Boot 编号与内核/loader 日志背书，全部记录在
[`docs/phk110/`](../../docs/phk110/STATUS.md)。本文只汇总与上游**不同**的点，
给其他想在这颗 SoC（骁龙 8+ Gen 1）上移植的人做参考。

## 1. SoC 层（soc_* 启动参数）

把手机自己的扁平设备树（`/sys/firmware/fdt`）喂给上游 `tools/soc-args.py`
提取，方法与逐节点证据见 `docs/phk110/waves/wave1-socargs.md`，数值见本目录
[`soc.args`](soc.args)。与 redwood 的关键差别：

| 参数 | redwood (SM7325) | PHK110 (SM8475) |
|---|---|---|
| `soc_ipa_base` | `0x1e40000` | `0x3e40000` |
| `soc_ipcc` | `0x408000` | `0xed18000`（全树唯一 `qcom,ipcc` 节点） |
| `soc_rsc` | `0x18220000` | `0x17a20000` |
| `soc_mpss_mem` | `0x8b800000` | `0x8bc00000` |
| `modem_ipa_fw_at` | `0x8b710000` | `0x8b910000` |
| `soc_ipa_fw` | `yupik_ipa_fws` | `ipa_fws` |
| `soc_aoss` | `0xc300000` | `0xc300000`（相同） |

## 2. UEFI / loader 内存图

- UEFI 底座 = takasugl `uefi-udon` 的 udonPkg **按本板重建**（上游 redwood 用
  自己的 hakios-uefi）；`FD_BASE=0xA7100000`、`FD_SIZE=0x400000`
  （`docs/phk110/waves/wave4-udon-rebuild.md`）。
- **`PAYLOAD_BASE=0xF4000000` 在这块板上不能改**：沿用 redwood 默认的
  `0xF0000000` 会让 loader 在读 payload 魔数时直接撞进一个未映射地址、
  冻屏在 assert 上，而且冻屏时一个字节的日志都来不及写。定位过程（用户拍到
  冻屏画面后逐条指令对出来的）见
  `docs/phk110/waves/wave21_2-ssh-catch.md` 第 7 节。
- 中断控制器：GIC v3 结构相同，但 **GIC 重分配器的扫描步进不同**，沿用
  redwood 的步进会在读计时器寄存器后 0.15 ms 处早期 abort（fault_code=0x10）；
  修复后 `gic: v3` 横幅与用户态一次到位
  （`docs/phk110/waves/wave10-post-gic-abort.md`）。
- 平台表：loader 侧新增 `platform_phk110`
  （`docs/phk110/waves/wave6-platform-phk110.md`）。

## 3. 输入设备

- **触摸**：不是 Goodix/FocalTech。本机是 Synaptics S3910，走 TouchComm v1
  协议，挂在 GENI SPI 端口（SE4）上。端口固件把 FIFO 接口关了，所以读方向
  只能 bitbang；芯片每个片选帧只给一个 9 字节块、按约 20 ms 的节拍重新武装。
  上游驱动不能直接用；我们的驱动改了五版，各版源码快照都在
  `wave12*-scripts/hakios.s3910*.c`（最终版 = 20 ms 节拍 + 分帧收割）。
  中间有一轮把问题误诊成"芯片电气故障"，后来靠原始字节取证翻过来——
  全过程在 `docs/phk110/waves/wave12c-electrical.md`。
- **按键**：PMIC 的 SPMI 仲裁器是 **v7**（redwood 是 v5），上游 buttons.c
  需要版本适配；三个键（电源/音量+/音量-）的真机事件已带毫秒时戳取证
  （`docs/phk110/waves/wave12-touch-buttons.md`）。
- GCC 时钟控制器的设备树尺寸比 mainline sm8450 大（`GCC_SIZE=0x1f4200`）；
  用 mainline 的 `0x60000` 会读越界 abort（Boot #15）。

## 4. 存储

- UFS 栈一次点亮：`ufs=2` 只读枚举 129 个分区，`ufs_write=1
  var_hfs=ufs_darwin_data` 打开写路径，`/private/var` 跨启动保留
  （`docs/phk110/waves/wave16-ufs-s0s2.md`、`wave18-s3s8.md`）。
- 一加把一个哨兵分区 `last_parti` 重复放在多个 LUN 上，名字撞车会让 devfs
  报 EEXIST；枚举器需要容忍这种情况。
- 数据卷准备走 adb 通道（不经 fastboot）：
  `devices/phk110/tools/userdata-carve-phk110.py`（勘察）+
  `devices/phk110/tools/darwin-write-phk110.py`（灌卷），
  执行记录在 `docs/phk110/waves/wave16b-p0-prep.md`、`wave16c-p0-exec.md`。
- 身份链：loader 的真身份要从本机的 `DeviceTree.d22ap.im4p` 重新生成，内核
  再加 `hw_target=D22ap` boot-arg 回落保护；否则内核答不出 `hw.target`，dyld 里
  的 libignition 直接带 launchd 一起死
  （`docs/phk110/waves/wave20-launchd.md`；Emilelu/UniXNU-mondrian 卡住的
  也是这一关）。

## 5. USB / 网络 / SSH

- vendor `UsbConfigDxe` 的 `start_ex` 在本机约九成的启动上失败；根因在
  2026-11-09 定位为**复位流程缺陷**（CORESOFTRESET 超时后不复位，半复位的
  控制器被带进后续每次启动），显式清除后问题不再出现
  （`docs/phk110/waves/wave24-exp1-diagnostic.md`）。这是移植期耗时最长的
  一个问题，先后有 12 篇阶段日志记录全程。
- 错误墙的收尾（2026-11-11~12）：更高负载下错误墙以另外两种形态回归，四代
  修复（IN 泄漏、服务窗热旋、请求生命周期、整对自愈）后解决；最深一层根因
  不在本板而在工具链——**LLVM -O1 的跨过程常量折叠把修复函数整段优化删除**，
  四个状态戳改 volatile 根治。全程见
  `docs/phk110/waves/wave38-usb-selfheal.md` 与两轮外部评审
  （`docs/phk110/review/`）。v35 判定轮的 SSH 双向内容 SHA 524288/524288
  与 /var 复验是这条修复链的机器侧证据。
- SSH 数据面 = loader 提供的 USB 网络：`en0` @ `10.0.0.2/30`（主机侧
  10.0.0.1），验证结论见
  `docs/phk110/waves/wave27-phaseB-wide-window.md`。
- 超过 1800 秒的长会话会撞上 vnode 表耗尽的 panic——这是上游通用问题，
  不是本板特有，先用 `loader_return_after` 上限绕开。

## 6. GPU（Adreno 730，v0.5 已达成硬件渲染首帧）

上游 redwood 是 SM7325（无本节问题）；本节是 SM8475 上点亮 Adreno 730
（a7xx 形态）时撞到的本板差异，全部修复都有本机设备树或厂商源码锚定：

- **时钟**：本机 GCC 是 `qcom,cape-gcc`（厂商实为 gcc-waipio.c 的 cape
  fixup），PLL_VOTE/GPU CBCR 偏移与 sc7280 模板不同（阶段 37 v28）。
- **熔丝**：cape 不向 AP 暴露 qfprom 熔丝节点，驱动需按"零访问"路径走
  （v30，活 FDT 地面真值定案）。
- **GPUCC**：GDSC/syscon 用手机自家 DTB 的一手地址，分支时钟用
  gpucc-waipio（v29/v30）。
- **zap 固件**：cape 的 a730_zap.mdt 是三段式（头/代码/哈希表），按
  sc7280 两段式读会被信任区拒收（v32）。
- **address-mode 表**：a6xx 时代的十二寄存器 address-mode 表在 a7xx 上
  第 6 写即挂步 20，vendor gen7_start 一个都不写——摘表（v33）。
- **fence 完成事件**：a7xx 必须用 `CACHE_CLEAN|WRITE_ENABLED(bit27)` =
  `0x08000031`（vendor ringbuffer / Linux v6.12 a7xx / Mesa 三方参照）；
  同代原生驱动（UniXNU/Adreno740）逐位佐证（阶段 40/41/44）。
- **NC_MODE 编码**：高端位按本机 HBB=16 用厂商公式 `bank_bit=(HBB-13)&3`
  运行时计算（带 DDR 类型条件），不是 redwood 代的硬编码表（阶段 41）。
- 用户态 = Mesa 25.0.7 freedreno（设备身份 FD725），内核接口沿用 msm DRM
  ioctl 号，**用户态 shim 零新增代码**（阶段 39 裁决）。
- 全程七刷七判与四门判定：`docs/phk110/waves/wave37-gpu-firstlight.md`、
  `wave45-v36-firstframe.md`；补丁脚本与判定 runner 在
  `wave36-scripts/`、`wave37-scripts/`、`wave41-scripts/`、`wave45-scripts/`。

## 7. 电量（驱动已落地，数据链修复中）

本机燃油计链路 = PM8350B 充电器块（SPMI 观察）+ TI bq27541 电量计
（I2C bit-bang over GPIO26/27，地址 0x55）。驱动按 boot-arg `fuelgauge=1/2`
切换静态/真实双模式；"宁可不显示不显示假值"原则 = 电量计首个有效 SOC 前
不喂任何数据。寄存器定义全部从厂商树机械核对（零猜测），62 项自检
（`docs/phk110/waves/wave43-battery.md`；源码快照与脚本在
`wave43-scripts/`）。真机 PARTIAL 现状（充电块通道表布局 + 电量计无应答）
见 `wave45-scripts/verdict45-gated.txt`。

## 8. WiFi（未上机，工具先行）

WCN6750 → Linux `ath11k` 路线。五个静态检查器和打包工具（`mk-ath11k.py`）
在 `wave30-scripts/`，前置研究见
`docs/phk110/waves/wave30-ath11k-tooling-prep.md`。

## 9. 与上游代码的对应关系

本分支**不改上游任何已有文件**（README 的呈现层替换除外，见仓库首页），
全部内容以新增形式存在。内核/loader 侧的移植改动（平台表、GIC 步进、
S3910 驱动、按键 v7、UFS、`hw_target` 回退、loader 补丁链、en0 驱动、
Adreno 730 内核驱动、fence/NC_MODE/gl_test 修复、燃油计驱动等）
目前在我们的私有构建树里按阶段演进；本分支以文档、驱动源码快照
（`wave12*-scripts/hakios.s3910*.c`、`wave43-scripts/`）和补丁脚本
（`patch-loader-v*.py`、`wave36/37/41-scripts/apply-*.py`）
的形式记录它们，整理成可直接套用的补丁序列是后续工作。

## 10. 许可

- 文档/脚本/设备层按上游仓根 [`LICENSE`](../../LICENSE) 的 MIT 口径发布。
- GPL 素材（OnePlusOSS sm8475 内核/设备树）**只作研究参照，本仓不分发**其
  任何文件；需要时自行获取：
  - `OnePlusOSS/android_kernel_oneplus_sm8475`（GPL-2.0）
  - `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475`（GPL-2.0）
- 本板 UEFI 的构建方式参考了 Mu-Silicium（K20 Pro 移植
  `HeliumStudio-Dev/hackios-xnu-kernel` 是一个很好的形态范本）。
