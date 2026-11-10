# 复现指南

想在同型号机（一加 Ace 2 / PHK110 / SM8475）上复跑本文的验证动作，从这里
开始。多数操作**不刷写任何分区**——只是从主机侧或经 adb 与手机交互；涉及
刷写的准备工作（数据卷）单独一节说明，本文不展开。

两点说明：

- 命令都是原样可用的英文；工具脚本随本分支发布，但脚本头部的工作区路径
  已被脱敏成 `<host>`（脚本里是 `HOST-REDACTED`），复跑前按你的目录布局改写
  `REPO` / `R` / `PY` 这些变量。
- 手机侧前提：bootloader 已解锁、ColorOS 正常运行、`fastboot` 能看到手机
  （`getvar product` 应为 `taro`）。WSL adb 复用 Windows USB 数据面的配方
  是 `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037`（为什么必须用 Linux adb 客户端：
  Windows adb.exe 的 shell 会把二进制流里的 LF 改成 CRLF，损坏拉取内容，
  详见 [waves/wave16c-p0-exec.md](waves/wave16c-p0-exec.md)）。

## 1. 相位探测（手机在 slot b 循环时；只读）

```sh
python3 wave27-scripts/probe-phase-v27.py
```

前提：手机正处于 slot b 的 loader 循环（或刚 `fastboot set_active b`），
主机能看到 `18d1:d00d xnuloader` 这个 USB 设备。

它做什么：对每个能打开的 d00d 设备发一条 `oem recording` 询问当前相位，
然后立即离线——答案是 loader 相位（内核未启动 / 会话已结束）还是内核
会话进行中。不改变手机状态，失败也只是"看不见"。

## 2. 拉取日志分区（手机已回安卓时；只读）

```sh
bash wave27-scripts/logdump-pull-v27.sh <RUNID>
```

前提：手机回到安卓（slot a），adb 在线，WSL adb 通道按上文配方。

它做什么：用 `exec-out` 二进制安全地把 512 MB 的日志分区（logdump——内核
和 loader 把日志写在这里，回到安卓后可以整块读回）拉到本地，带 201326592
字节的尺寸闸，产物名 `logdump-v23-wave27-<RUNID>.bin`。约一分钟，只读。

## 3. 把手机送回 slot b 循环（手机掉出循环时；不刷写）

```sh
bash wave27-scripts/march-android-v27.sh <RUNID>
```

前提：手机当前在安卓；`getvar product` = `taro` 作为身份检查。

它做什么：先拉一份日志分区取证，然后用 `set_active b` + 重启把手机送回
slot b 的 loader 循环，交给并行运行的 SSH 连接脚本去抓新一代会话。脚本里
每条 adb/fastboot 调用都检查退出码，结束进程一律按精确 PID。风险与
`fastboot set_active` 同级：只切换活动槽位，不写分区；任何一步失败的安全
状态就是安卓，重跑即可。

## 4. SSH 端到端（宽窗连接；不刷写）

```sh
python3 wave27-scripts/timed-ssh-v27.py
```

前提：USB 服务通道已建立（usbipd attach 到位，或用直连的 WinUSB 后端）；
SSH 私钥放在 `wave21-scripts/id_ed25519_phk110`——本分支不含私钥（只发布了
公钥），复跑需要自备同名密钥，并按
[wave17-ssh-bootstrap.md](../wave17-ssh-bootstrap.md) 的做法把你的公钥注入
镜像的 `authorized_keys`。

它做什么：按相位感知的节奏等待并建立 SSH 连接——loader 相位时保持静默
250 秒让内核启动，落到新会话开始后约 10 秒的位置发起连接。设计细节见
[waves/wave27-phaseB-wide-window.md](waves/wave27-phaseB-wide-window.md)。
失败模式是错过窗口（等下一代会话即可），不刷写。

判定通过的参考样例：`wave27-scripts/verdict27-20261110-060630.txt`（三条
独立连接 + 256 KiB 校验传输 + 干净退出 + loader 存活）。

## 5. 复位循环（连接脚本卡住时）

```sh
bash wave27-scripts/reset-cycle-v27.sh
```

前提：SSH 连接脚本在跑；`wave26-scripts/revive-v26.py`（热复位）在位。

它做什么：暂停连接脚本 → 热复位 → 观察 90 秒内 USB 节点是否消失 → 复启
连接脚本（消失说明新一代会话在前面）。结束进程按精确 PID，不刷写。

## 6. 镜像自检（刷写前跑；只读）

```sh
python3 wave18-scripts/verify-udon-hakios-v12.py <payload-dir>
```

前提：本地有对应版本的镜像条目；在刷写**之前**跑。

它做什么：对镜像的每个条目（UEFI FD、shim、loader.efi、内存盘、cmdline）
做逐字节断言，与基线比较。输出全绿 = 条目与基线逐字节一致；任何一项红 =
停止刷写。各版本都有对应的 `verify-udon-hakios-vN.py`。这条纪律救过我们
一次：2026-11-08 的一轮构建回归（PAYLOAD_BASE 编译成默认值）就是靠这类
逐字节检查定位的，见
[waves/wave21_2-ssh-catch.md](waves/wave21_2-ssh-catch.md) 第 7 节。

## 7. WiFi 工具（本机文件检查，未涉及手机）

```sh
python3 wave30-scripts/check-phk110-wifi-dtb.py <dtb-file>
python3 wave30-scripts/mk-ath11k.py --help
```

前提：从你自己手机导出的 DTB / 固件文件（本分支不含任何厂商固件）。

它做什么：对设备树节点、固件文件、MHI/WLFW 配置做静态检查，以及 ath11k
固件打包。纯本机文件检查，无风险；WiFi 路线尚未在真机上进行。

## 操作关系一图

```
[安卓 slot a] --fastboot set_active b--> [slot b loader 循环]
      ^                                        |
      | ABL 自动回退 / set_active a             v
      +----- 自动退回安卓 <---- probe-phase / timed-ssh / (1800 s 会话上限)
                |                          |
                +--- logdump-pull (取证) <-+     （以上全部不刷写）
```
