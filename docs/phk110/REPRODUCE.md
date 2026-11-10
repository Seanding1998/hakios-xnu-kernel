# 复现指南（零刷写优先）

本文给想在同型号机（一加 Ace 2 / PHK110 / SM8475）上复跑验证的人一条从零
路径。**所有命令为英文原样**；每条注明前置条件与风险。工具脚本都随本分支
发布，但脚本头部的工作区路径已被脱敏为 `<host>`，复跑前按你的布局改写
`REPO`/`R`/`PY` 等变量。发布集不含任何镜像二进制（boot 镜像、UEFI FD、
payload）——刷写级复现需要先按 [PORT-NOTES.md](../../devices/phk110/PORT-NOTES.md)
自建镜像，不在本文范围。

## 0. 前置条件（主机）

- Windows + WSL2；Windows 侧 `usbipd-win`（USB serving 管道）、Python 3.11+
  （`pyusb`/`ctypes` 直连工具用）；WSL 侧 Linux `adb`（二进制安全的拉取通道）
  与 `fastboot`。
- WSL adb 复用 Windows USB 数据面的配方（CRLF 教训见
  [waves/wave16c-p0-exec.md](waves/wave16c-p0-exec.md)）：
  `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037`。
- 手机：解锁 BL（orange）、ColorOS 正常、`fastboot` 可见（product=`taro`）。
- ⚠️ 风险总说明：以下多数操作是**零刷写**（不动任何分区）；涉及刷写的
  命令不在本文。对分区的一切写操作（P0 carve/灌卷）必须先读完
  [waves/wave16b-p0-prep.md](waves/wave16b-p0-prep.md) + [waves/wave16c-p0-exec.md](waves/wave16c-p0-exec.md)
  并自备校验，本文不重复。

## 1. 相位探测（手机在 slot b 循环态；只读）

```sh
python3 wave27-scripts/probe-phase-v27.py
```

- 前置：手机正处于 slot b loader 循环（或刚 `set_active b`）；主机能看到
  `18d1:d00d xnuloader` USB 节点。
- 行为：对每个可打开的 d00d 发 `oem recording` 询问相位后立即离线，不改设备态。
- 风险：无（只读；失败只是"看不见"）。

## 2. logdump 取证（手机回安卓后；零刷写）

```sh
bash wave27-scripts/logdump-pull-v27.sh <RUNID>
```

- 前置：手机已回安卓（slot a），adb 在线；WSL adb 通道按上文配方。
- 行为：`exec-out` 二进制安全拉取 512 MB logdump 分区，带 201326592 字节
  尺寸闸，产物 `logdump-v23-wave27-<RUNID>.bin`。
- 风险：无（只读拉取；~1 分钟）。

## 3. Android 态 march（手机掉出 slot b 循环时；零刷写）

```sh
bash wave27-scripts/march-android-v27.sh <RUNID>
```

- 前置：手机当前在安卓；`getvar product` = `taro` 作为身份闸。
- 行为：拉 logdump 取证 → 把手机送回 slot b loader 循环（`set_active b` +
  reboot 链），交给并行的 SSH hunt 抓新一代会话。每条 adb/fastboot 调用
  exit-code 检查，kill 一律按精确 PID。
- 风险：低——只切活动槽位（与日常 `fastboot set_active` 同级），不写分区；
  失败安全态 = 安卓，重跑即可。

## 4. SSH E2E hunt（宽窗，零刷写）

```sh
python3 wave27-scripts/timed-ssh-v27.py
```

- 前置：USB serving 管道已通（usbipd attach 到位或直连 WinUSB 后端）；
  密钥在 `wave21-scripts/id_ed25519_phk110`（发布集不含私钥——复跑需自备
  同名密钥并注入镜像的 `authorized_keys`，见 [wave17-ssh-bootstrap.md](../wave17-ssh-bootstrap.md)）。
- 行为：相位感知的宽窗 SSH 猎取——loader 相位真空 250 s 让内核 exec，落到
  新会话 ~10 s 处发起连接（设计细节见
  [waves/wave27-phaseB-wide-window.md](waves/wave27-phaseB-wide-window.md)）。
- 风险：无刷写；失败模式 = 错过窗口（继续等下一代会话）。
- 判定参考：`wave27-scripts/verdict27-20261110-060630.txt`（3 独立连接 +
  256 KiB 校验传输 + 干净退出 + loader 存活）。

## 5. 复位循环 / hot reset（hunt 卡死时）

```sh
bash wave27-scripts/reset-cycle-v27.sh
```

- 前置：hunt 进程在跑；`revive-v26.py`（wave26-scripts）就位。
- 行为：暂停 hunt → hot reset → 观察 90 s 节点消失 → 复启 hunt（消失 =
  新一代在前面）。
- 风险：低（kill 按精确 PID；hot reset 不刷写）。

## 6. UFS/存储回归门（镜像侧 boot-args 已含 ufs=2…；零刷写）

`wave28-scripts/`（mark/hunt 系列）+ `wave18-scripts/verify-udon-hakios-v12.py`
一类的**自检脚本**是刷写前清单：对镜像条目逐字节断言（fd/shim/loader.efi/
ramdisk/cmdline 与基线 cmp）。用法模式（以 v12 为例）：

```sh
python3 wave18-scripts/verify-udon-hakios-v12.py <payload-dir>
```

- 前置：本地有对应代际的镜像条目；跑在刷写**之前**。
- 行为：全绿 = 条目与基线逐字节一致；任何红 = 停刷。
- 风险：无（纯读）。**纪律：不自检全绿不刷写**（F10 构建回归就是被它拦住的
  反例教材，见 [waves/wave21_2-ssh-catch.md](waves/wave21_2-ssh-catch.md) §7）。

## 7. WiFi 工具（案头检查，未上机）

```sh
python3 wave30-scripts/check-phk110-wifi-dtb.py <dtb-file>
python3 wave30-scripts/mk-ath11k.py --help
```

- 前置：从你自己手机拉的 DTB/firmware 文件（发布集不含任何厂商固件）。
- 行为：DTB 节点/固件文件/MHI/WLFW 配置的静态检查器与 ath11k 打包器。
- 风险：无（纯本机文件检查）。

## 8. 一图流

```
[安卓 slot a] --set_active b--> [slot b loader 循环]
      ^                              |
      | ABL 兜底 / set_active a       v
      +---- 兜底回安卓 <--- probe-phase / timed-ssh hunt / (1800s 帽到期)
             |                        |
             +-- logdump-pull (取证) <-+   （全部零刷写）
```
