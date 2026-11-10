# 一加 Ace 2（`PHK110`）

HakiOS 的 SM8475（"cape"）移植，从上游 `redwood`（SM7325）参考机出发。
下表只写这台真机上实际看到过的状态（Boot #1–#39）；完整日志线索在
[`docs/phk110/STATUS.md`](../../docs/phk110/STATUS.md) 与
[`docs/phk110/waves/`](../../docs/phk110/waves/)。英文版见 [README.md](README.md)，
移植差异汇总见 [PORT-NOTES.md](PORT-NOTES.md)。

| | |
|---|---|
| 厂商 | OnePlus |
| SoC | `SM8475`（骁龙 8+ Gen 1，"cape"），16 GB 内存 |
| 配置 | loader cmdline = `soc.args` + `device.conf` 里的 boot-args |
| 维护者 | PHK110 移植团队（本分支） |
| 基座 | [hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel)（redwood 参考机） |
| UEFI | takasugl udonPkg 本板重建（`FD_BASE=0xA7100000`、`PAYLOAD_BASE=0xF4000000`） |
| 启动路径 | 只用 `boot_b` 槽位、RAM 级；日常安卓 `boot_a` 从不触碰 |

## 实测状态

| 部件 | 状态 | 说明 |
|---|---|---|
| 显示 | ✅ 工作 | UEFI framebuffer 1240×2772；内核 fb 控制台滚动；屏录 boot-arg 通路存在（rec_secs/rec_ring） |
| 按键 | ✅ 工作 | 电源 + 双音量键，PMIC SPMI **v7** 仲裁器（上游驱动只认 v5）；真机按键事件带毫秒时戳（Boot #16） |
| CPU | ✅ 工作 | 8 核全上（`small_cores_after=0` 时 7 个 AP 核 8 ms 窗内齐上；大核 1–3、慢核 4–6） |
| 触摸 | ◑ probe 通过 | Synaptics S3910 TouchComm **v1**（GENI SPI，SE 固件禁了 FIFO 接口 → bitbang 读方向）：`part number "S3910PA0B0-15.2"`、1240×2772 面板、report config 读取、`touch screen ready`（probe ~1.0 s，Boot #21）；9 字节块按 ~20 ms 节拍重新武装 |
| 存储 | ✅ 工作 | UFS：129 分区只读（`ufs=2`）+ `ufs_darwin_data` 写路径（`ufs_write=1 var_hfs=…`），`/private/var` 跨 boot 保持、journal replay 跨会话复验（Boot #22–#24） |
| 用户态 | ✅ 工作 | 真 Apple launchd 接管 pid 1：`hardware target : d22ap` 被接受、28 进程（SpringBoard/backboardd）、Procursus `/var/jb` 前缀嫁接（Boot #25） |
| SSH | ✅ 工作 | `WAVE21-SSH-OK` 判定：经 loader USB 网络（`en0`，10.0.0.2/30）3 条独立 SSH 会话、root shell、256 KiB 校验传输、干净 FIN/ACK 退出且 loader 存活（2026-11-10） |
| USB serving | ✅ 工作 | loader USB 命令服务器（getvar / oem log / oem upload，216 KB 长度+内容双校验）——前提是修复 vendor 复位流程缺陷（CORESOFTRESET 超时后半复位 core 常驻，"H4" 根因，Wave 24） |
| 会话上限 | ◑ 部分 | 1800 s 帽端到端实证；更长会话撞预存 `panic: vnode table is full`（F6） |
| GPU | ❌ 未通 | WindowServer/CoreAnimation 未起——计划内 v0.5 边界 |
| WiFi | 工具先行 | WCN6750/ath11k 工具链已备（Wave 30），未上机 |
| 蜂窝 / 音频 / 电池 / 振动 / 相机 | ❌ 未尝试 | — |

## 安全边界

移植只走 `boot_b` 槽位：刷写与引导它**从不写入**日常安卓的 `boot_a` 槽位。
会话失败或内核崩溃时由 bootloader 自身的 A/B fallback 兜底回安卓；手动回安卓
= `fastboot set_active a` + reboot。200 GB userdata 卷仅在尾部挖出 20 GB
`darwin` 卷（P0 操作前后数据卷头/签名双重校验，Wave 16b/16c）。
