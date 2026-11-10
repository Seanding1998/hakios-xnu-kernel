# PHK110 移植笔记（redwood → SM8475）

上游参考机是 POCO X5 Pro（`redwood` / SM7325 / yupik）。本设备是一加 Ace 2
（`PHK110` / SM8475 / cape / 一加内部称 "Udon" 板）。移植不是逐文件改写，而是
按波次实测推进：每一条差异都有 Boot 编号与内核/loader 日志背书，全部记录在
[`docs/phk110/`](../../docs/phk110/STATUS.md)。本文只汇总与上游 **不同** 的点，
给后来移植第二台 SM8475/骁龙 8+ Gen 1 设备的人抄近路。

## 1. SoC 层（soc_* 启动参数）

以手机自己的扁平设备树（`/sys/firmware/fdt`）喂给上游 `tools/soc-args.py`
得出，方法与逐节点证据见 `docs/phk110/waves/wave1-socargs.md`，数值见本目录
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

- UEFI 底座 = takasugl `uefi-udon` 的 udonPkg **本板重建**（上游 redwood 用
  自己的 hakios-uefi）；`FD_BASE=0xA7100000`、`FD_SIZE=0x400000`
  （`docs/phk110/waves/wave4-udon-rebuild.md`）。
- **`PAYLOAD_BASE=0xF4000000` 是生死线**：沿用 redwood 默认 `0xF0000000`
  会在 `parse_payload` 读 magic 时直接 assert 冻屏（该地址在本板未映射、
  落 TZApps Reserved；日志一个字都来不及打）。判案过程见
  `docs/phk110/waves/wave21_2-ssh-catch.md` §7（发现 F10）。
- 中断控制器：GIC v3 结构相同，但 **GICR 扫描步进不同**，沿用上游 redwood
  步进会在 `gTimerBase` 后 ~0.15 ms 早期 abort（fault_code=0x10）；Wave 10
  修复后 `gic: v3` 横幅与用户态一次到位（`docs/phk110/waves/wave10-post-gic-abort.md`）。
- 平台表：loader 侧新增 `platform_phk110`（`docs/phk110/waves/wave6-platform-phk110.md`）。

## 3. 输入设备

- **触摸**：不是 Goodix/FocalTech。本机是 Synaptics S3910 TouchComm **v1**，
  挂 GENI SPI（SE4）。SE 固件把 FIFO 接口关了（`GENI_IF_DISABLE_RO` bit0=1），
  所以读方向走 bitbang；芯片每个 CS 帧只给一个 9 字节块、按 ~20 ms 节拍重新
  武装。上游驱动不能直接用；我们的驱动演进五版都在
  `wave12*-scripts/hakios.s3910*.c`（最终版 v10e = 20 ms 节拍 + 分帧收割）。
  攻坚全过程（含"电气层故障"误诊的翻案）见 `docs/phk110/waves/wave12c-electrical.md`。
- **按键**：PMIC SPMI 仲裁器是 **v7**（redwood 是 v5），上游 buttons.c 需要
  版本适配；三个键（power/vol+/vol-）真机事件已取证
  （`docs/phk110/waves/wave12-touch-buttons.md`）。
- GCC 时钟控制器的 FDT 尺寸比 mainline sm8450 大（`GCC_SIZE=0x1f4200`，
  用 mainline 的 `0x60000` 会读越界 abort，Boot #15）。

## 4. 存储

- UFS 栈（上游 S0-S8 阶梯）在本机**一次点亮**：`ufs=2` 只读枚举 129 个分区，
  `ufs_write=1 var_hfs=ufs_darwin_data` 开写，`/private/var` 跨 boot 保持
  （`docs/phk110/waves/wave16-ufs-s0s2.md`、`wave18-s3s8.md`）。
- 一加多 LUN 哨兵分区 `last_parti` ×4 重名 → devfs EEXIST；枚举器需要容忍
  （良性，F1）。
- 数据卷准备走 adb 通道（零 fastboot）：
  `devices/phk110/tools/userdata-carve-phk110.py`（勘察）+
  `devices/phk110/tools/darwin-write-phk110.py`（灌卷），
  执行记录 `docs/phk110/waves/wave16b-p0-prep.md`、`wave16c-p0-exec.md`。
- 身份链：loader 真身份从本机 `DeviceTree.d22ap.im4p` 重建 + 内核
  `hw_target=D22ap` boot-arg fallback，否则 dyld 内嵌 libignition 对
  `hw.target` 的 EINVAL(22) 即死、launchd 起不来
  （`docs/phk110/waves/wave20-launchd.md`；同样的坑 Emilelu/UniXNU-mondrian
  也踩过）。

## 5. USB / 网络 / SSH

- vendor `UsbConfigDxe start_ex` 间歇失败是本机常态（~9/10 boot）；
  Wave 24 判决表落槌的根因 = **复位流程缺陷**（CORESOFTRESET 超时后不显式
  解除，每代 boot 带半复位 core 跑 bring-up），显式清除后错误墙零复现
  （`docs/phk110/waves/wave24-exp1-diagnostic.md`）。这是移植期最长的一堵墙，
  12 篇波告全程记录。
- SSH 数据面 = loader 桥接网络：`en0` @ `10.0.0.2/30`（host 10.0.0.1），
  最终 `WAVE21-SSH-OK` 判定见 `docs/phk110/waves/wave27-phaseB-wide-window.md`。
- 长会话（>1800 s）会撞预存的 `panic: vnode table is full`（F6）——这是
  上游通用问题不是本板特有，用 `loader_return_after` 帽绕过。

## 6. WiFi（未通，工具先行）

WCN6750 → Linux `ath11k` 路线。案头工具五件（DTB/fw/MHI/WLFW/E2E 检查器 +
`mk-ath11k.py` 打包器）在 `wave30-scripts/`，前置研究
`docs/phk110/waves/wave30-ath11k-tooling-prep.md`。尚未上机。

## 7. 与上游代码的对应关系

本分支**不改上游任何已有文件**，全部内容以新增形式存在。内核/loader 侧的
移植补丁（platform 表、GICR 步进、S3910 驱动、buttons v7、UFS、hw_target
fallback 等）目前在我们的私有工作区里按波次演进，发布集里以波告 + 驱动源码
快照（`wave12*-scripts/hakios.s3910*.c`）+ 补丁脚本（`patch-loader-v*.py`）
形式呈现；整理成上游可收的单一只读补丁序列是后续工作。

## 8. 许可

- 文档/脚本/设备层按上游仓根 [`LICENSE`](../../LICENSE) 的 MIT 口径发布。
- GPL 素材（OnePlusOSS sm8475 内核/dts）**只作研究参照，本仓不再分发**其
  任何文件；需要时自行 clone：
  - `OnePlusOSS/android_kernel_oneplus_sm8475`（GPL-2.0）
  - `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475`（GPL-2.0）
- 本板 UEFI 参考了 Mu-Silicium 的构建方式（raphael fork
  `HeliumStudio-Dev/hackios-xnu-kernel` 是"第二台设备移植"形状的范例）。
