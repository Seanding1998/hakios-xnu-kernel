# 阶段 21 · 2026-11-08 · 设计稿：经 loader USB 通道的网络（SSH 数据面）

> 2026-11-08 · 设计稿（基于 wave19-prep 方案 A + 源码实证）。实施阶段开始前如有 阶段 20 新事实再修订。
> 三端预估：loader.c ~200-300 行 / 内核 en0 ~150-250 行 / loader_talk.py ~300-400 行。

## 0. 目标

Darwin 用户空间（launchd + sshd，阶段 20 产物）的 sshd 监听 TCP:22；主机 `ssh -o ProxyCommand="python loader_talk.py tunnel %h 10.0.0.2" 10.0.0.2` 免 WiFi/免内核 USB 栈直连。方案 A（wave19-prep）：零 UEFI 二进制改动，复用 loader 现有 USB 字节管线。

## 1. 通道事实（源码实证）

- loader USB 命令服务器（loader.c:3960-4046）已有**双向字节管道**：
  - `download:<hex>` → 设备 RAM 暂存（`max-download-size` = 0x03f00000 即 60MB；`oem ramdisk` 模式 0xffffffff）
  - `upload` → 把 `staged_data/staged_len`（:322-323）流向主机
  - `oem log` / `oem run[:cp]` / `oem ramdisk` / `oem clearscreen` / `reboot` 等命令族
- loader 在内核运行期间**常驻 core 0**（block_poll 轮询 mailbox，loader.c:2190/:2477）——网环的设备侧排空可以挂在同一轮询里
- 主机侧 loader_talk.py（wave13）：ctypes+libusb 直连 18d1:d00d，bulk-out 发 ASCII 命令、bulk-in 收 OKAY/FAIL/DATA 流——`cmd`/`log` 已通，缺 `tunnel` 模式

## 2. 架构（L3 raw-IP over ring，推荐）

```
[Darwin] TCP:22 ← sshd
   ↑ en0 (10.0.0.2/32, 轮询无中断)
[内核] en0 驱动：IP 帧 ⇄ 共享页网环（tx/rx 环 + 门铃字）
   ↑ 同一 4K 网环页（loader_block 扩展区，物理地址经既有 ufs_shared_pa 同款机制告知）
[Loader/core0] block_poll 扩展：排空 tx 环 → staged_data 切网模式；rx 环写入 ← download 数据
   ↑ USB bulk：loader_talk 轮询 `upload`（取 rx）/ `download:<hex>`（投 tx）
[主机] loader_talk.py tunnel 模式：
   - wintun 适配器 10.0.0.1/30（Windows 侧 TUN）⇄ 网环帧搬运 + ssh 直连 10.0.0.2
   - （无 wintun 时的降级：本地 127.0.0.1:2222 端口转发 + Darwin 侧极简 TCP relay——备选，多做Darwin侧代码，不推荐）
```

**为什么 L3 raw-IP 而非以太网帧**：省 ARP/最小帧头/校验和一套；XNU inet 栈对 raw-IP ifnet 支持成熟（utun 同族）；Windows 侧 wintun 是 TUN 标准件（单 dll，无驱动安装）。

## 3. 三端施工单

### 3.1 loader.c（~200-300 行）
1. `loader_block` 扩展 `net` 区：`net_tx_head/net_rx_head` 门铃 + 两个 16KB 环（放 ufs mailbox 页同款对齐）；物理地址告知内核（boot-args `net_shared_pa=` 或复用 native 交接区旁路）
2. `block_poll` 循环内新增：`net_poll()`——tx 环有数据 → 拷入 staged 缓冲网模式区；`oem netmode` 命令切换 `staged_data` 指向网 rx 区（log 与 net 分时复用既有 upload 管道）
3. `download:` 数据落点新增网模式分支 → 写 rx 环 + 门铃
4. `oem netstat` 调试命令（环水位/丢弃计数）
5. 零 UEFI 二进制改动（loader.efi 是 payload 条目）

### 3.2 内核 en0 驱动（~150-250 行，仿 hakios.ufs.c mailbox 范式）
1. `drivers/net/hakios.en0.c`：ifnet 注册（`en0`）、`if_output` → tx 环、轮询线程（100-250ms）读 rx 环 → `if_input`
2. IP 地址配置：boot-args `en0_addr=10.0.0.2` 或 init/launchd 前的极简 ifconfig 等价物（fork 用户态现有能力 survey）
3. 无中断、无 DMA（纯共享内存 + cache 管理同 ufs.c :340/:405 惯例）
4. 冲突面：内核零 USB 栈（wave19-prep 已证）——en0 不碰 DWC3，与 loader 的 USB 独占无冲突 ✓

### 3.3 loader_talk.py（~300-400 行）
1. `netmode`：握手 `oem netmode` → 进入搬运循环（`upload` 拉帧 → wintun 注入；wintun 出帧 → `download:`）
2. `tunnel`：wintun 适配器生命周期 + `ssh -o ProxyCommand` 包装器输出
3. 自测模式：环回帧（loader 端 echo）验证管道
4. 依赖：wintun.dll（~100KB，单文件；下载走代理）

## 4. 分阶段实施

| 阶段 | 内容 | 验收 |
|---|---|---|
| N1 | loader 网环 + `oem netmode/netstat` + loader_talk `netmode` 搬运循环 + 内核 en0 tx/rx 环（**不含 inet**，先裸帧环回） | 主机发任意帧 → Darwin 侧环回原样回传（`oem netstat` 计数对账） |
| N2 | 内核 ifnet + inet 栈接线 + 主机 wintun + 地址 10.0.0.1/2 | 主机 `ping 10.0.0.2` 通（ICMP over 桥） |
| N3 | sshd 起来（阶段 20 产物）+ `ssh 10.0.0.2` | **v0.4 达成：SSH shell** |

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| USB bulk 吞吐不足 | SSH 文本流量 KB 级，60MB 管道余量巨大；fastboot bulk 实测可达 MB/s 级 |
| 轮询延迟（250ms）→ SSH 卡顿 | 可调：block_poll 节奏 / upload 轮询间隔；SSH 交互在 100-300ms RTT 可用 |
| loader core-0 预算 | net_poll 摊入既有 block_poll 空转周期（mailbox 每写已有 flush+读回，增量极小） |
| XNU ifnet 最小实现未知数 | 先查 fork/upstream 有无网络驱动先例（redwood v0.6 WiFi 未做——可能无先例，需读 XNU ifnet API；阶段 21 实施首日任务） |
| wintun 与火绒 | 用户态 dll，无内核组件，预判无冲突（hrdevmon 只拦 usbipd 的 VBoxUSB） |

## 6. 备选降级链

B = UMS 文件通道（无实时 SSH，仅传文件）；C = 内核 DWC3+NCM（v0.5+，先做内核 USB 栈）；若 XNU ifnet 实现代价超估 → 退 B 并把 v0.4 SSH 验收改为"sshd 监听日志 + UMS 取回 /var 内容证据"。
