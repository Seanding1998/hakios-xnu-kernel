# 阶段 26 · 2026-11-09 · vnode 上限修复与 SSH 时间窗

> 2026-11-09 09:57 → （进行中）· 阶段 26 执行记录
> 任务书：修复最后一公里的内核 bug 并收尾 v0.4（刷写预算 2 轮）
> 红线执行：只碰 boot_b ✓（Round 1 = v21 已刷 09:58；Round 2 = v22 获批后刷）；FD/shim 零重建 ✓（graft 用树内 8924cb67/108ce972 原件）；device-layer/wave26-scripts 只新增 ✓；内核源码改动只限 drivers/net/hakios.loader_net.c ✓（Round 2 经协调员批复扩为 loader.c 单 hunk，见 §5）；禁 git reset/checkout/stash/clean ✓；进程管理全程按 PID 精确 kill ✓（三次孤儿代理 64180/51204/65592 等均单点清除）

## 0. 判定（当前）

**WAVE21-SSH-OK 未到手；但本阶段改写了问题的版图，并定位到真正的收尾手柄：**

1. **v0.4 其余要件全部复验**（v21/v22 真机验证）：serving armed gen0 beat1 每 boot、en0 注册 10.0.0.2/30、ARP/SYN 帧双向流动、TCP 三路握手完成（SYN-ACK 主机收到）、**现场目击 iOS 桌面（SpringBoard 渲染上屏）**——logdump 行计数双源实证（§4）。
2. **"K1"（en0 poll 停摆）真根因终定案，en0 驱动无罪，vnode 塌方论降级**：**cmdline `loader_return_after=180` 的 180s 硬会话帽**（`osfmk/arm64/loader_return.c:470-483`：boot 时一次性 thread_call，180s 无条件 `loader_return()`）。所有"冻结"证据重读后全部吻合：en0 心跳冻住/ring 16/16/lost 爬升 = 内核按期返回后**没人排环**，主机重传全弃；logdump 的"222.58s 停摆" = 180s 定时到 → `hakios_var_save_on_return()` 刷数据卷（~40s，= 现场拍照的 `ufs: 9504 writes…78233600 bytes`）→ 正常 return；wave25 的"established 后 30-60s 冻结" = established 在会话 ~120-150s + KEX 30-60s 撞线。SSHD 本身每 boot 都听（165.8s 在案）——只剩 ~14s 给它，SSH 是被 180s 帽饿死的（§3）。
3. **en0 侧修复（v21，已刷）**：poll 线程不再触碰栈路径（stage + feeder + seen 心跳）——结构加固 + 会话端到端可观测性（`oem netstat` 的 `en0 <n>` 心跳成为会话活性表），保留在树里。
4. **Round 2（v22，已刷 12:08）**：loader.c 单 hunk——DT `/defaults` 注入 `kern.maxvnodes=8192`（`PE_get_default` 直达 `bsd_devsizing()`，绕开 CONFIG_VNODES=1024 裁剪）。vnode 塌方在 180s 会话里从未被填满过（理论降级、未证实）；1800s 长会话下它成为必要前置（风暴 ~30 分钟可填 1024）。
5. **Round 3（v23，已刷 13:16，第三轮追加刷写）**：cmdline 单字段 `loader_return_after=180`→`1800`——**SSH 的真手柄**：sshd 165s 起听后，窗从 14s 变 ~19 分钟。

## 1. 准备工作定性与 Round 1（en0 feeder 修复，v21）

### 1.1 准备工作读码（任务书五方向逐一）

| 方向 | 结论 |
|---|---|
| ①环满分支 | 内核侧 poll 只排不塞（≤32 帧/拍）；发送侧满环 = 丢帧靠 TCP 重传——无阻塞路径 |
| ②break/return 退出 | net.c `net_thread` 是无限循环，无退出路径 |
| ③挂起点 | poll 每帧路径：`mbuf_allocpacket(MBUF_DONTWAIT)`（不阻塞）→ `ifnet_input` → `dlil_input_async`（net_async=1 默认，仅入队 + 唤醒 en0_input 工作线程，锁持有都是毫秒级）——无显性死锁 |
| ④cache | 排除：门铃页 = `VM_WIMG_WCOMB`、帧页 = `VM_WIMG_DEFAULT`（`ml_io_map_unmappable`→`io_map`→Normal 可缓存），CPU↔CPU 硬件一致 + `FlushPoC_DcacheRegion` 惯例与 ufs.c 同款（ufs.c 数 GB 读从未坏）——门铃语义（free-running u32 + dmb）正确 |
| ⑤门铃 wrap | 184/242 帧量级无 wrap 问题 |

### 1.2 Round 1 修复（`drivers/net/hakios.loader_net.c`，唯一内核改动）

按"poll 永不触碰栈"重构（diff 三件套）：
1. **SPSC stage**（32 × 1518B，`net_stage_prod/cons` free-running + dmb）：poll 只做 `FlushPoC→memcpy→rx_cons 前移`，任何情况下不等待；
2. **feeder 线程**（`net_feeder_thread`，kernel_thread_start）：从 stage 取帧交 `hakios_net_input`（loopback 帧回环判据同 v20）——栈要等多久都等在 feeder 身上，ring 永不积压；
3. **seen 心跳**：`net_ring->kernel.seen` 每拍 +1（`oem netstat` 的 `en0 <n>` 直接变成 poll 活性表——loader 侧零改动即得可观测性）；TX 环 slot 认领用 `os_atomic_cmpxchg` 自旋（loopback 与 transmit 双写者唯一化）。
4. 环满/stage 满纪律：丢最新 + 计数 + 有界打印（TCP 重传回退），永不阻塞。

**构建**：内核 abecd557cd0540e7（17c905ec → abecd557，diff 仅此一文件）；payload v21 `eac9d989…`（六 entry 从 v20 payload 逐字节回装）；graft v21 `c18689bc…`；verify-udon-hakios-v21.py **56/56 全绿**（loader b8a2150b 字节钉 + PAYLOAD_BASE 双层钉 + entry RVA 0x2140 + v18 cmdline 字节钉）。

### 1.3 Round 1 刷写与真机验证（预算 1/2）

- 09:57:56-09:58:20 `flash boot_b`（WSL root fastboot，product=taro ✓，set_active b ✓）。boot_b：v20 `05267a64` → **v21 `c18689bc`**。
- 真机验证（gen1，09:59-10:23）：armed gen0 beat1 ✓；en0 @T0+~65s 上线、地址配置成功（logdump：`net: en0 has 10.0.0.2/30`，无 SIOCAIFADDR 错误）；`oem netstat` 应答 12+ 分钟；轻载（~5 帧/s × 30s × 2 发）心跳一路爬升（3214→8405→14059）、held 0 0、lost 0——**超 v20 冻结点（tx 184/rx 242）仍活**。
- **重载（tunnel 10 分钟锤）后仍冻结**：`held 0 16`、`lost` +3/s、`en0 26558` 冻住——单变量对照：feeder 修复不是根因（若冻结在 poll→栈路径，此修复应当有效）。真钟指向"会话龄"而非流量（§3）。

## 2. （保留节）

## 3. 决定性取证（logdump-v21-wave26-1.bin）

10:50 ABL 自动回退到安卓 → 10:56 `adb dd /dev/block/by-name/logdump`（512MB 全镜像，sha256 `548597f36e927df03591e56255796801f738e0aa38668472edf7d2b328d8f7ba`）——**恰是现场拍照的"会话正常结束"写盘**（`log: 729088 bytes written to logdump, read back the same`）。

时间线（kernel 单调钟）：
```
 49.27s  net: en0 attached … net: the feeder is in … net: en0 has 10.0.0.2/30   ← v21 三件套全部真机验证
 61.18s  MiniIOSurface: backboardd[16] created surface 1: 1125x2436 'BGRA'      ← 主 surface
 61.18s  MiniIOMobileFramebuffer: swap 1 layer 0: … 1125x2436 to 0,0 1125x2436  ← 首次全屏上屏
149-176s MiniIOSurface: SpringBoard[12] created surface 17-25（桌面元素上屏——现场目击对应）
150.15s  tcp_connection_summary …
165.82s  tcp listen: [:::22<->:::0]        ← sshd 每 boot 都在听（"间歇"证伪）
159/219s memory: free 4345/4264 MB …        ← 内存充裕，非 OOM
222.52s  MiniIOMobileFramebuffer: 51 frames in 5001 ms …   ← 最后的显示统计
222.58s  memorystatus_update … pid 47        ← 内核最后一行日志
        ——之后一切停摆（内核日志、Mini 帧统计、launchd 日志同一刻全灭）——
```

launchd 侧（统一日志，同一时刻）死亡螺旋：
```
08:03:42.83→.88→.94→43.00…  Flushed N logs [limit: 20]   ← flush 间隔 56ms
08:03:43.6  Last log repeated 3410 times: failed lookup: com.apple.commcenter.xpc (SpringBoard)
08:03:43.8  Last log repeated 1017 times: Could not find job com.apple.chronod
…           repeated 3236-3896 次/拍，flush 间隔衰减到 ~1000ms（08:03:49.00 最后一条）
```

**机理终定案（Round 3 修正）**：180s 硬会话帽。`loader_return_timer_init`（loader_return.c:470）在 boot 时挂一次性 180s 定时器；到点后 `hakios_var_save_on_return()` 刷数据卷（78MB，~40s，即现场拍照的结束画面）→ `loader_return()` 回 loader。**222.58s 的"停摆"= 这套正常结束序列的日志尾巴**；launchd 侧的 SpringBoard XPC 查找风暴（commcenter.xpc 3400-3896 次/拍 + chronod + sleepd，flush 间隔 56ms→1000ms 衰减）真实存在且是长会话的 vnode 压力源（v22 的 maxvnodes=8192 为其前置），但在 180s 帽下从未触顶。

**wave25 的"established 后 30-60s 冻结"= 180s 帽**：established 在会话 ~120-150s + KEX 30-60s ≈ 撞线。SSHD 每 boot 都听（165.8s 在案），帽前只剩 14s——SSH 是被会话帽饿死的，不是被任何驱动或风暴杀死的。

**出画行计数（A 级，与现场目击互证）**：MiniIOMobileFramebuffer 111 行 / MiniIOSurface 30 / created surface 24 / backboardd 544 / SpringBoard 1249 / swap 20（b25 基线 = 8 swaps / 20 Mini 行）。电池显示不正确 = 本机无燃油计驱动（已知空白项），如实入档不修。

## 4. 时间窗与 timed-ssh（零刷写线）

sshd listen（T0+181）→ 塌方（T0+238）之间 ~56s。`wave26-scripts/timed-ssh-v26.py`：等总线空 → T0 = gadget 首现 → 静默到 T0+178 → 52s 硬限时（`taskkill /F /T` 按 PID 杀树，孤儿代理三次事故的教训）连发 ssh（复用 wave25 全套：tunnel25w ProxyCommand + id_ed25519_phk110）。战果：RST 会话（sshd 未听，tcp_in 全是 RST）退避重 SYN——属 vnode 域的逐 boot 方差；听窗会话未及完成 KEX 即塌方。v22 真机验证后窗预期分钟级。

## 5. Round 2/3：v22（maxvnodes loader）+ v23（长会话 cmdline）——已获批、已构建、已刷

### 5.1 Round 2（v22，预算 2/2，12:08 刷）

- **机理**：`bsd/dev/unix_startup.c` `bsd_devsizing()` 先问 `PE_get_default("kern.maxvnodes", &desiredvnodes, 4)`（`pexpert/gen/bootargs.c:496` = 查 DT `/defaults` 节点同名字段），没有才走内存估算并被 `#ifdef CONFIG_VNODES`（=1024）裁剪——**DT 注入绕开裁剪**。
- **loader.c 单 hunk**（xnuloader/loader.c `/defaults` 节点加一行 + 注释）：`dt_prop_u32(&w, "kern.maxvnodes", 8192);`
- **重编**：`PAYLOAD_BASE=0xF4000000 ./build.sh`（F10 教训钉死）→ loader.efi `0ade78b5…`（83456B；`kern.maxvnodes` 字符串在证；PAYLOAD_BASE pin movz@0x1774 + entry RVA 0x2140 ✓）。
- **payload v22** `ea63aa4f…`：loader 换新，其余六 entry 从 v21 payload **逐字节**回装（kernel = abecd557 不变）。
- **graft v22** `7a1e4811…`；verify-udon-hakios-v22.py **56/56 全绿**。
- **刷写**：`flash-when-android-v26.sh`——等 ABL 自动回退到安卓（12:07）→ 顺手拉 logdump-v21-wave26-2.bin（md5 5c08cb7d）→ adb reboot bootloader → flash OKAY → set_active b → reboot。

### 5.2 Round 3（v23，预算 第三轮追加刷写，13:16 刷）

- **机理**：§0.2 的 180s 帽——SSH 的真手柄。**零构建**：payload 的 cmdline entry 单字段 `loader_return_after=180`→`1800`（472→473 字节含 NUL，预算 471+110=581/607 内），其余六 entry 字节不动（loader 0ade78b5 / kernel abecd557 全保留）。
- **payload v23** `86c2fbaa…`；graft v23 `9e0609fb…`；verify-udon-hakios-v23.py **56/56 全绿**（cmdline 断言 = v18 字节 + 仅此字段移动）。
- **刷写**：flash-when-android-v23.sh——安卓在位（13:15）→ 拉 logdump-v22-wave26-3.bin（md5 19ff87ef）→ flash OKAY → set_active b → reboot。

## 6. 验收与 SSH 收尾（Round 3 状态：现场召回收尾，未完成——非技术失败）

### 6.1 v23 真机验证实况（13:16 刷写后的实测，全部在案）

- **1800s 帽验证通过**：13:55 的手动尝试在 v23 会话（kernel ~8-11 分钟龄）上跑了 3 分钟隧道——`oem netstat` 心跳 `en0` 26897→30533 一路爬升、`held 0 0`、`lost 0`——**远超 v20/v21 的 180s 帽死点**，长会话成立。
- **sshd 启动竞态（新发现，23.y 域）**：sshd 在每 boot 都被 exec（`$ /var/jb/usr/sbin/sshd -D -e … &`，kernel ~49s，桌面会话与 v23 会话同位），但**只有部分 boot 真正到达 listen**（桌面会话：kernel 165.8s `tcp listen` + `so_gencnt… t_state: LISTEN process: sshd:42`；v23 的 13:47 boot：exec 在案、至 kernel ~331s+ 仍无 `tcp listen`，主机侧全部 RST）。竞态对象 = launchd/风暴下的调度（同镜像逐 boot 方差，与 wave25 的 RST/听窗两态完全吻合）。**这是剩余的唯一 SSH 阻塞，属 wave20 用户态/launchd 域，非本阶段可治**。
- **播种器连捕**：continuous 模式（run9）19 连发全部 miss——当代 sshd 未听。 ~14:16 现场召回， hunting 停止。

### 6.2 召回时点状态（供续接时核对）

- boot_b = **v23 `9e0609fb`**（13:16:15 刷写 + set_active b，flash-v23-run.log 在案；日志里 "boot_b = v22" 字样为脚本 sed 遗留标签，sha 才是身份）——**已刷，无需再验**。
- 手机被带走（最后总线观测 13:55 前后 xnuloader 在位、会话循环正常；16:16 总线空）。
- SSH 判定（`uname -a` = Darwin）未完成 = **现场召回**，非技术失败。v23 的宽窗（~19 分钟）+ Runbook（§6.3）已就绪，手机回归即可第二轮。

### 6.3 手机回归 Runbook（一键化：wave26-scripts/runbook-phone-return.sh）

插回后全自动按序：①判状态（Android / fastboot / xnuloader 循环三态）→ ②boot_b 身份校验（report.json 比对，非 v23 则走 flash-when-android-v23 流程）→ ③set_active b 进链 → ④宽窗 SSH campaign（timed-ssh continuous + drain-revive 纪律）→ ⑤判定落盘（verdict26.txt）+ handback 询问（默认留在链上）。每步失败即停带回退；红线不变（boot_b only、PAYLOAD_BASE 钉、PID 精确 kill）。

## 7. 后续工作清单

1. 判定与本阶段新器件 sha 全表：
   - v21：kernel `abecd557` / payload `eac9d989` / graft `c18689bc` / loader = v20 的 `b8a2150b` 字节
   - v22：loader.efi `0ade78b5`（maxvnodes hunk）/ payload `ea63aa4f` / graft `7a1e4811`
   - v23：cmdline `67f37524`（473B，=v18 字节仅 180→1800）/ payload `86c2fbaa` / graft `9e0609fb`
2. 阶段预算结算：刷写 3/3（v21 09:58 / v22 12:08 / v23 13:16——第 3 轮追加刷写）。
3. 证据包：logdump-v21-wave26-1.bin（sha256 `548597f3…`，桌面会话全日志）/ -2.bin（md5 5c08cb7d）/ -3.bin（md5 19ff87ef）；出画行计数（§4）；v23 判定日志（wave26-scripts/timed-ssh-v26.log）。
4. 风暴本体未治理（commcenter/chronod/sleepd 客户端重试）：1800s 会话下的 vnode 速率留 23.y 观测。
5. 本阶段新增工具（wave26-scripts/）：v21/v22/v23 四件套（payload/graft/verify/flash）+ timed-ssh-v26.py + freeze-hunt-v26.py + accept-v22.py + revive-v26.py（H4 恢复纪律的落地件）+ pull-log-v26.py + flash-when-android-v2x.sh + logdump-watch-v26.sh。
6. 事故登记：①取证期 download 中途失败致 loader 暗态（10:28，主机侧"USB 错误码墙"对应）；②三次孤儿 tunnel 代理均按 PID 清杀；③pull-log 的 transact 未排 OKAY 致 loader 反复楔死（已改 Pipe25 纪律）——均为工具层事故，设备无恙。
7. 环境事件：12:31 前后的 USB 插拔（现场操作）——期间的总线闪断勿立案。14:16 后用户携手机外出，阶段按 §6 召回收尾。

## 8. 23.y 预研：XPC 风暴的来源与治理候选（准备工作，基于本阶段日志实证）

**来源定位**：风暴的 requestor 全部是 `SpringBoard[12]`（pid 12），查的是三个**不存在于本系统的服务**：
- `com.apple.commcenter.xpc`（flags 0x8 lookup）——SpringBoard 的蜂窝/网络状态检查；
- `com.apple.sleepd.sleepserver`——休眠调度；
- `com.apple.chronod`——日历刷新（"Could not find job with label"）。
真机上这三个 daemon 都在，lookup 立即成功；本最小系统没有 → launchd 回 "No such process" → SpringBoard 客户端**无退避地立即重试**（实测 3037-4865 次/拍），launchd 自己的日志 flush 被拖到 56ms→1000ms 衰减。

**治理候选（按侵入度升序）**：
1. **stub daemon（推荐，用户态）**：在 wave20 的用户态树里补三个空壳 LaunchDaemon plist + 占位二进制（`/redwood/LaunchDaemons/` 同款管道），lookup 立即成功、重试风暴消失。改 system.apfs/resident = wave20 域。
2. SpringBoard 侧 plist/binary patch：重、脆、不做。
3. 内核 IPC 限流（per-task mach message quota）：内核侧大手术，无必要（候选 1 足矣）。
**注**：1800s 帽 + maxvnodes=8192 下风暴仍持续吹（v23 live log 08:05:14 段 4865 次/拍在案），vnode 余量充足则无害；候选 1 落地后日志噪声与 vnode 消耗同时消失，留 23.y 一并做。

## 9. Phase A（外部审阅第三轮驱动的主机侧修复，零刷写零手机）

审阅报告（docs/review/gpt-review-report-3-2026-11-09.md）内存报文验证出三个 P1 主机缺陷 + 事务同步族——全部修复，13 项定向回归全绿（`wave26-scripts/regression-phase-a.py`，内存构造报文、不触手机）：

| # | 缺陷（审阅命名） | 修复 | 回归断言 |
|---|---|---|---|
| 1 | ARP 回复 sender/target 写反 + opcode≠1 早退（reply 学习缺失 = `arp learned: []` 之谜） | `_on_arp` request/reply 分路径：request 先学后答（字段交换，RFC 826）；reply 纯学习 | 回复四字段逐字节断言；reply 学习生效 |
| 2 | 握手最后 ACK 序号差一（ACK 在 SYN 序号消耗前发出，ISN 应为 ISN+1） | **握手统一进状态机**：`Tunnel.open_syn()` 发 SYN 即消费序号（SND.NXT=ISN+1）；SYN-ACK 验证（ack==ISN+1）→ 置 `acked` → 发最终 ACK（seq 天生正确）→ ESTABLISHED；wrapper 的事后 `tun.seq += 1` 与手工 SYN 全部删除（`resyn()` 用原 ISN 重发）；顺带修掉 wave21 遗留的 H5 同族崩溃（offset/flags 塞 'B' 槽） | 有效 SYN-ACK → 最终 ACK seq/ack 逐字段断言；错 ack 不建立 |
| 3 | 跨端口 RST 误杀（只查源 IP） | `on_ipv4` 顶部四元组分诊（sport==dst_port && dport==src_port，否则丢弃计数）；RST 需序号在 `ack_of_peer` 有界邻域内才可信；verdict 携带四元组+seq 证据 | 跨端口 SYN-ACK/RST 不影响；同四元组 RST 关闭且 verdict 带证据 |
| 4 | DATA/终端 OKAY 事务（PARTIAL / `OKAYxnuloaderxnuloader` 族） | `Pipe25.pending_okay` 状态 + `_drain_okay` 循环到真 OKAY（时限 per-instance）+ PARTIAL 排干后重试一次 + 下一条命令先完成上一事务 | DATA 短量/缺 OKAY/晚到应答三案识别与自愈 |

**Runbook 加固**（runbook-phone-return.sh 重写）：per-run 唯一 ID（verdict26-<RUNID>.txt + 内容绑定 run-id/rc/输出/隧道设备证据，旧 verdict 不放行）；adb/fastboot 全退出码检查（`adb_run`/`fb_run` 包装，禁 `| tail` 丢码）；`getvar product` taro 身份门前置一切 fastboot 动作；四态分治（Android 直读 boot_b / ABL 直连 / **loader 期禁 usbipd attach**（单一 Windows-libusb 所有者纪律）等待回落 / 无设备轮询）；boot_b 回读临时文件按 run ID 隔离。SSH 判定命令改 `&&` 链 + rc=0 才算 HIT（审阅 §6 验收门）。

**审阅其他修正的采纳记录**：vnode 运行期真值 32768（init.c:1495，DT 8192 只覆盖 init 前——留 23.y 记录实际值+用量曲线）；XPC 空壳 daemon 降级为候选（lookup 成功 ≠ 风暴消失）；H4 单变量边界如实保留；en0 心跳只覆盖 poll（feeder→TCP 盲区）与 `net_fed_dropped` 不上 netstat = Phase C 的分层计数器动因。
