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
- SSH 数据面 = loader 提供的 USB 网络：`en0` @ `10.0.0.2/30`（主机侧
  10.0.0.1），验证结论见
  `docs/phk110/waves/wave27-phaseB-wide-window.md`。
- 超过 1800 秒的长会话会撞上 vnode 表耗尽的 panic——这是上游通用问题，
  不是本板特有，先用 `loader_return_after` 上限绕开。

## 6. WiFi（未上机，工具先行）

WCN6750 → Linux `ath11k` 路线。五个静态检查器和打包工具（`mk-ath11k.py`）
在 `wave30-scripts/`，前置研究见
`docs/phk110/waves/wave30-ath11k-tooling-prep.md`。

## 7. 与上游代码的对应关系

本分支**不改上游任何已有文件**（README 的呈现层替换除外，见仓库首页），
全部内容以新增形式存在。内核/loader 侧的移植改动（平台表、GIC 步进、
S3910 驱动、按键 v7、UFS、`hw_target` 回退、loader 补丁链、en0 驱动等）
目前在我们的私有构建树里按阶段演进；本分支以文档、驱动源码快照
（`wave12*-scripts/hakios.s3910*.c`）和补丁脚本（`patch-loader-v*.py`）
的形式记录它们，整理成可直接套用的补丁序列是后续工作。

## 8. 许可

- 文档/脚本/设备层按上游仓根 [`LICENSE`](../../LICENSE) 的 MIT 口径发布。
- GPL 素材（OnePlusOSS sm8475 内核/设备树）**只作研究参照，本仓不分发**其
  任何文件；需要时自行获取：
  - `OnePlusOSS/android_kernel_oneplus_sm8475`（GPL-2.0）
  - `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475`（GPL-2.0）
- 本板 UEFI 的构建方式参考了 Mu-Silicium（K20 Pro 移植
  `HeliumStudio-Dev/hackios-xnu-kernel` 是一个很好的形态范本）。
