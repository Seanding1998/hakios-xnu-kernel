# 一加 Ace 2（`PHK110`）

HakiOS 的 SM8475（"cape"）移植，从上游 `redwood`（SM7325）参考设备出发。
下表只写这台真机上实际验证过的状态；完整记录在
[`docs/phk110/STATUS.md`](../../docs/phk110/STATUS.md) 与
[`docs/phk110/waves/`](../../docs/phk110/waves/)（"Boot #N" 指那份时间线）。
英文版见 [README.md](README.md)，与上游参考设备的差异逐项说明见
[PORT-NOTES.md](PORT-NOTES.md)。

| | |
|---|---|
| 厂商 | OnePlus |
| SoC | `SM8475`（骁龙 8+ Gen 1，"cape"），16 GB 内存 |
| 配置 | loader cmdline = `soc.args` + `device.conf` 里的 boot-args |
| 维护者 | PHK110 移植团队（本分支） |
| 基座 | [hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel)（redwood 参考设备） |
| UEFI | takasugl udonPkg 本板重建（`FD_BASE=0xA7100000`、`PAYLOAD_BASE=0xF4000000`） |
| 启动路径 | 只用 `boot_b` 槽位；日常安卓的 `boot_a` 从不触碰 |

## 实测状态

| 部件 | 状态 | 说明 |
|---|---|---|
| 显示 | ✅ 工作 | UEFI framebuffer 1240×2772；内核帧缓冲控制台滚动输出；屏幕录制参数通路存在（rec_secs/rec_ring） |
| 按键 | ✅ 工作 | 电源 + 双音量键，经 PMIC 的 SPMI 总线读取（仲裁器协议 v7，上游驱动原本只认 v5）；真机事件带毫秒时戳（Boot #16） |
| CPU | ✅ 工作 | 8 核全部上线；`small_cores_after=0` 时 7 个应用核心 8 ms 内齐起（大核 1–3，小核 4–6） |
| 触摸 | ◑ 驱动探针通过 | Synaptics S3910，GENI SPI 口上的 TouchComm v1 协议（端口固件禁用了 FIFO 接口，读方向用 bitbang）：读到部件号 "S3910PA0B0-15.2"、面板 1240×2772、报告配置读取完成、`touch screen ready`（探针约 1.0 s，Boot #21）；芯片每个片选帧只给一个 9 字节块、约 20 ms 重新武装 |
| 存储 | ✅ 工作 | UFS：129 个分区只读枚举（`ufs=2`）+ `ufs_darwin_data` 可写（`ufs_write=1 var_hfs=…`）；`/private/var` 跨启动保留，文件系统日志重放双向验证（Boot #22–#24） |
| 用户态 | ✅ 工作 | 真 Apple launchd 以 pid 1 运行：`hardware target : d22ap` 被接受、28 个进程（SpringBoard/backboardd）、Procursus 前缀嫁接到 `/var/jb`（Boot #25） |
| SSH | ✅ 工作 | 经 loader 的 USB 网络通道（`en0`，10.0.0.2/30）建立 3 条独立 SSH 会话、root shell、256 KiB 校验传输、干净断开后 loader 仍存活（2026-11-10） |
| USB 服务通道 | ✅ 工作 | loader 的 USB 命令服务（getvar / oem log / oem upload，216 KB 上传做了长度+内容双重校验）；此前阻塞在 vendor USB 驱动的复位流程缺陷——CORESOFTRESET 超时后核心处于半复位状态并带进后续每次启动（2026-11-09 在阶段 24 定位并修复） |
| 会话上限 | ◑ 部分 | 1800 s 会话上限端到端验证过；更长会话会撞上一个早就存在的 `panic: vnode table is full` |
| GPU | ❌ 未实现 | WindowServer / CoreAnimation 未启动（按路线排在 v0.5） |
| WiFi | 工具先行 | WCN6750 / ath11k 的检查器与打包工具已备（`wave30-scripts/`），尚未上机 |
| 蜂窝 / 音频 / 电池 / 振动 / 相机 | ❌ 未尝试 | — |

## 安全边界

移植只走 `boot_b` 槽位：刷写与引导它**从不写入**日常安卓的 `boot_a` 槽位。
会话失败或内核崩溃时，由 bootloader 自带的 A/B 回退自动退回安卓；手动回安卓
= `fastboot set_active a` + reboot。200 GB 的 userdata 卷只在尾部挖出 20 GB
`darwin` 卷，操作前后对数据卷头与签名做过双重校验（阶段 16b/16c）。
