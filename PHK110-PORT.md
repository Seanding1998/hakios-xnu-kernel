# PHK110 移植（HakiOS on OnePlus Ace 2）

这是 [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel)（Apple XNU 内核
直接跑在安卓高通手机上）向**一加 Ace 2（PHK110 / 骁龙 8+ Gen 1 SM8475 /
16 GB）**的移植分支。上游唯一参考机是 POCO X5 Pro（redwood / SM7325）；本
分支把它带上了第二台真机，并且**不改上游任何已有文件**——所有内容以新增
形式存在（`devices/phk110/`、`docs/phk110/`、`wave*-scripts/`、`logs/`）。
启动只走 `boot_b` 槽位（RAM 级引导），日常安卓 `boot_a` 从未被刷写或修改；
会话失败由 bootloader 自身的 A/B fallback 兜底回安卓。

## 当前状态（2026-11-10，全部为真机实测，判定依据见括号）

| 部件 | 状态 | 实测依据 |
|---|---|---|
| 显示 | ✅ 工作 | UEFI framebuffer 1240×2772，内核 fb 控制台滚动（Boot #7 起） |
| 8 核 | ✅ 工作 | 7 AP 核全上线，`small_cores_after=0` 时 8 ms 窗齐上（Boot #13/#14） |
| 按键 | ✅ 工作 | 电源+双音量键，SPMI v7 仲裁器，真机事件毫秒时戳（Boot #16） |
| 触摸 | ◑ probe 通过 | S3910 TouchComm v1：`part "S3910PA0B0-15.2"`、`touch screen ready`（Boot #21）；真人点屏事件待验 |
| 存储 | ✅ 工作 | UFS 129 分区只读 + darwin 卷写路径，`/private/var` 跨 boot 保持、journal replay 复验（Boot #22–#24） |
| 用户态 | ✅ 工作 | 真 Apple launchd 接管 pid 1，28 进程（SpringBoard/backboardd），Procursus /jb（Boot #25） |
| USB serving | ✅ 工作 | loader USB 命令服务器，getvar/oem log/upload 216 KB 双校验；根因修复 = H4 复位流程缺陷（Wave 24） |
| SSH | ✅ 工作 | `WAVE21-SSH-OK`：3 独立会话、root shell、256 KiB 校验传输、干净退出 loader 存活（2026-11-10，Boot #39 系） |
| GPU | ❌ 未通 | WindowServer/CoreAnimation 未起——计划内 v0.5 边界 |
| WiFi | ❌ 未通 | ath11k 工具链已备（Wave 30），未上机 |
| /var 持久化判定 | ◑ 进行中 | Wave 28 回归门已建，Wave 31 判定跑在本机（发布时点未收口） |

## 5 分钟快读路径

1. 这台机器怎么 Boot 起来的 → [`devices/phk110/device.conf`](devices/phk110/device.conf)
   + [`devices/phk110/soc.args`](devices/phk110/soc.args)（每个数值都指向波告）
2. 与上游 redwood 有什么不同 → [`devices/phk110/PORT-NOTES.md`](devices/phk110/PORT-NOTES.md)
3. 全项目走到哪了 → [`docs/phk110/STATUS.md`](docs/phk110/STATUS.md)（唯一权威快照）
4. 只有一刻钟？→ [`docs/phk110/READMAP.md`](docs/phk110/READMAP.md) 挑一个主题
   （启动链 / 触摸 / USB / SSH / 存储 / 用户态 / WiFi / 调研）
5. 想动手复跑 → [`docs/phk110/REPRODUCE.md`](docs/phk110/REPRODUCE.md)（零刷写优先）
6. 设备页（上游 PR 形状）→ [`devices/phk110/README.md`](devices/phk110/README.md)（中文版 [README.zh.md](devices/phk110/README.zh.md)）

## 这个分支里有什么

| 目录 | 内容 |
|---|---|
| `devices/phk110/` | 设备配置四件套 + 中文设备页 + 移植笔记 + 数据卷工具（`tools/`） |
| `docs/phk110/` | 全套项目文档：STATUS / PLAN / README / 阅读地图 / 复现指南 / 45 篇波告 / 8 篇调研 / 4 篇评审 |
| `waveNN-scripts/` | 主机侧工具 22 组（loader 直连 `loader_talk.py`、SSH 宽窗 hunt `timed-ssh-v27.py`、march/logdump-pull/复位循环、自检 verify 系列、S3910 驱动五版源码快照、ath11k 检查器等） |
| `logs/` | 内核日志关键行提取件（`*.keylines.txt`，对应 logdump 二进制的文本证据） |

**不含**：任何镜像/固件二进制（boot 镜像、UEFI FD、payload、厂商固件、IPSW
衍生物）、任何私钥、任何分区备份。需要的原始材料（Apple IPSW、一加固件）
请自备——本仓按上游口径不含它们。

## 诚实的未解清单

- `/var` 持久化的长程回归判定进行中（Wave 28 建门，Wave 31 跑判定）
- GPU/WindowServer 未起（v0.5 边界，上游同样未到）
- WiFi/蜂窝/音频/电池/振动/相机未开（WiFi 工具先行）
- 真人点屏事件驱动未验（probe 已通）
- >1800 s 长会话撞预存 vnode 表耗尽 panic（F6，上游通用问题，用 `loader_return_after` 帽绕过）
- 内核/loader 侧移植补丁尚未整理成上游可收的单一补丁序列（当前以波告+源码快照+补丁脚本形式在 `wave*-scripts/`）

## 许可与致谢

本分支的内容按上游仓根 [`LICENSE`](LICENSE) 的口径发布：文档/脚本/设备层
（即本分支的全部新增内容）为 MIT；上游内核侧保持 Apple Public Source License
v2.0（`LICENSE.APSL`）。致谢：

- **[oosexgang/hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel)**（以及 hakios-metal / hakios-sm7325 / hakios-uefi）——一切工作的基座
- **takasugl/uefi-udon**（与 UniXNU-udon）——本机 UEFI 底座（udonPkg）的来源
- **OnePlusOSS**（`android_kernel_oneplus_sm8475`、`android_kernel_modules_and_devicetree_oneplus_sm8475`，GPL-2.0）——SM8475 dts/驱动研究参照；**本分支不再分发其任何文件**，soc.args 等数值是从手机自带的 FDT 提取的
- **Mu-Silicium** 与 **HeliumStudio-Dev/hackios-xnu-kernel**（raphael/SM8150 移植）——"第二台设备移植"形状与 UEFI 构建方式的参考
- Apple 的 macOS/iOS 镜像（IPSW）不属于本仓也不由本仓分发，使用者自备自己的副本

## 出处与脱敏说明

本分支由私有工作区在 commit `1ed67796af8d10fb9c8da5b6d7c246c87c025854`
（2026-11-10，"docs close-out before Wave 31"）的 `git archive` 快照整理而来，
整理时做过一次脱敏：手机 serial、主机用户名/路径全部替换为
`SERIAL_REDACTED`/`<host>`；SSH 私钥与全部镜像/固件二进制未入选（入选/排除
准则即上文"这个分支里有什么"与其后的"不含"清单）。发布集内脚本头部的
工作区路径也已是 `<host>` 占位，复跑前按本机布局改写。
