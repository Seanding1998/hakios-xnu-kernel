# 阶段 27 · 2026-11-10 · 宽窗 SSH 验证：三条独立会话全部通过

> 2026-11-10 00:50 → 06:20（完成：**v0.4 SSH 门 PASS**）· 阶段 27 执行记录
> 任务书：v23 长会话（1800s）宽窗内捕获 WAVE21-SSH-OK；零刷写；接管 阶段 26 未竟工作
> 红线执行：零刷写 ✓（全程无 fastboot write）；loader 相位禁 usbipd attach ✓（单一 Windows-libusb 所有者）；PID 精确 kill ✓（每次 taskkill 均按 PID，见日志）；boot_b 只读 ✓；进程树清杀仅限本波自启的 ssh/proxy 树

## 0. 判定（终局 → 详见 §7）

**WAVE21-SSH-OK 到手（06:17:39 首 HIT / 06:19:51 完整门）：`=== v0.4 SSH GATE: PASS (hit + 3 conns + verified transfer + mgmt) ===`**。以下 §1-§6 为达到该判定过程中的滚动记录（保留原貌）。

会话 3（03:03-03:32）首次实现**完整 SSH 对话到 userauth**：
- ARP 双向（Phase A 修复首次实战生效：reply 学习 + 字段交换）
- 三次握手逐字段验证（SYN→SYN-ACK ack=ISN+1→ACK→ESTABLISHED）
- banner 双向（phone 21B `SSH-2.0-OpenSSH_...` / host 33B）
- sshd KEXINIT 1072B 分段到达并被逐段 ACK
- KEX 完成 → NEWKEYS → userauth 消息交换（SSH-REACHED ×9 连发）
- 唯一剩余失败 = 主机侧私钥文件 ACL（见 §3.3）

## 1. 起点清理（阶段 26 遗留）

1. `wave26-scripts/timed-ssh-v26.py` 语法坏死（`return` 后死代码含循环外 `break`）——已修复（回归第 8 项恢复）。
2. **孤儿 arming hunter（PID 76156，wave26 遗留进程）**：占住 libusb context 令所有 open 得 LIBUSB_ERROR_ACCESS，总线上呈"死 devnode"形态 1 小时+；01:10 按 PID 精确 kill 后节点立即恢复可开。**教训：wave26 式"持续 probe"主机进程退场时必须随 wave 清杀；其 context 会拒绝其他 opener。**
3. `wave25-scripts/tunnel25w.py` 的 B3 trace_frame 伪头部对 IN 帧用 HOST_IP 当源 → 入站帧校验和恒错（B3 证据污染）——已修（用包自身 IP）。

## 2. 工具（wave27-scripts/）

| 件 | 用途 |
|---|---|
| `timed-ssh-v27.py` | 相位感知播种器：loader-phase 应答→250s 真静默（不顶死 exec 钟）→ENTRY_GUARD 75s 后进洞；DEAD-PAIR→arming 压力；六分支分类（B1 NOLISTEN/B2 SSH-REACHED/B3·B4 STALL/B5/B6 USB-DESYNC/域态 LOADER/DEAD-PAIR/NO-DEVICE）；HIT→验收包（3 独立连接+256KB wc -c 校验传输+管理通道） |
| `probe-phase-v27.py` | 一次性相位探针（单命令即离线） |
| `probe-wedge-v27.py` | 楔死诊断（四命令逐一试探） |
| `probe-mss-v27.py` | MSS 尺寸阶梯（活会话实测 ACK 阈值） |
| `logdump-pull-v27.sh` / `march-android-v27.sh` | Android 态 logdump 取证 + 零刷写回归槽 b 循环（taro 门+槽门） |

## 3. 本波修复（全部主机侧，零刷写）

### 3.1 相位感知占空比（timed-ssh-v27）
wave26 continuous 模式每 55s 探一次会把 loader 的 240s 服务窗永远顶住（内核永不 exec）。修复：loader 应答→真静默 250s→exec→ENTRY_GUARD 75s（en0 在 kernel+49s attach，早进的 upload 会楔死 loader 整个会话——k001 实证）→敲门。

### 3.2 pump 推序 + 清洁退出（tunnel25w）
- **推序**：老 pump_once 先 fetch（upload）后 push——我们的 ARP 请求永远留在 link.out，内核无帧可给 upload → 死锁（wave25/26 靠内核自己的 ARP 重试流量偶然存活）。改 push-first。
- **清洁退出**：45s 无推进→netmode off 干净离场（对端存活）；seeder 的 taskkill 降为冻结后备（190s）。k001/k006/k022 三次楔死全部来自 kill 打进事务中间。

### 3.3 MSS 尺寸阶梯（probe-mss-v27，活会话实测）
**160B ACKed / 170B 起静默丢弃**——loader 的 host→kernel 环路对帧长有 ~160B 上限。wave21 的 netmode ping 只验过 100B 帧（--size 默认 100），MSS=1400 从未被真实 KEXINIT 检验过。修复：`lt21.MSS=160`。修复后 140B-160B 段全部被 ACK（SND.UNA 正常推进）。

### 3.4 私钥 ACL（会话 3 的 auth 门槛）
Win32-OpenSSH 拒载 `id_ed25519_phk110`（"bad permissions"——ACL 过宽，历史上从未暴露因为 ssh 从未活到这一步）。修复：`/inheritance:r` + `CYRUX\<host>:R` + `SYSTEM:R` + `Administrators:R`，移除畸形 ACE。

## 4. 代际钟（实测汇编）

| 代 | exec | return | 返回后行为 |
|---|---|---|---|
| S1 | ~01:10:45 | ~01:40:45 | pair 楔死（k001 早进）；sick ~20min；01:47 热复位→01:49 掉节点→~02:00 Android |
| S2 | 02:10:53（march 重启后） | ~02:41 | pair 楔死（k006，kill 注入器）+ deaf；02:57 热复位被吸收；03:03 loader 自愈并 exec S3 |
| S3 | ~03:03 | 03:32:12 | 返回后 27s 即应答（FAILno recording）→静默→S4 |
| S4 | 03:41:10 | 04:11:10 | k022 楔死（16s kill，已废除）；返回后 sick 33min+ → 04:44 热复位 |
| S5 | （待观察） | | 完整修复栈首个满周期 |

规律：返回后的 loader 有一个"保存窗"（脏状态越多越久：S3 27s / S2 22min / S4 33min+），窗后或自愈 re-arm（S2→S3 自愈 exec）或掉落 Android（S1）。**满 reboot（march 路径）的 240s exec 钟是唯一实测严格守时的路径。**

## 5. 六分支判决台账（B4 门：每次失败必须落格）

| 次序 | 分支 | 证据（文件） | 处置 |
|---|---|---|---|
| run1 k001 | B3 变体（早进楔死） | tssh27-…-k001.err：netmode OKAY 后 upload 无应答 | ENTRY_GUARD 75s |
| run1 k002-k005 | 域态 DEAD-PAIR | getvar None | 复活纪律+快速循环 |
| run2 k006 | B6+B3 变体（kill 注入器+推序死锁） | k006.err：established 后 KEXINIT 无 ACK（当时 MSS 根因未显） | push-first+清洁退出 |
| run3 k008+ | **协议全通** | k008.err：完整对话至 userauth | MSS 阶梯→160 |
| run3 k009-k019 | B2 SSH-REACHED | ACL 拒载私钥 | ACL 重建 |
| run4 k022 | B6（16s kill 注入器 + 首推 netmode 竞态） | k022.err：no download OKAY (None) | 自限期 20s+宽限重试+统一界 |
| run4 k023+ | 域态 DEAD-PAIR（S4 楔死遗产） | getvar None | 等返回+热复位 |

## 6. 证据包

- `logdump-v23-wave27-20261110-0155.bin`（512MB，sha256 6ae00f3c…）：**`loader_return_after=1800` boot-args 在证 + `--- loader_return_after expired ---` 尾行（1800s 帽首次端到端实证）+ en0 up + sshd exec 行**
- 会话 3 完整 SSH 对话 traces：`tssh27-20261110-030630-k008.err` 等（B3 全字段行）
- MSS 阶梯实测：probe-mss-v27 三轮输出（150/160 ok，170+ drop）
- 播种器+分类器单测：classifier 9/9；Phase A 回归 13/13（timed-ssh-v26 修复后恢复全绿）

## 7. 判定（WAVE21-SSH-OK 在案 + v0.4 SSH 门全过）

**06:17:39 HIT，06:19:51 —— `verdict27-20261110-060630.txt`（run-id 20261110-060630）：
`=== v0.4 SSH GATE: PASS (hit + 3 conns + verified transfer + mgmt) ===`**

| 验收项 | 结果 | 证据 |
|---|---|---|
| uname=Darwin | ✓ ×3 连接 | `Darwin localhost 22.5.0 … iPhone10,3 arm Darwin` |
| id 预期（root） | ✓ ×3 | `uid=0(root) gid=0(wheel) groups=0(wheel)` |
| 本次随机标记完整返回 | ✓ ×3（token 各异） | `WAVE21-SSH-OK W27-20261110-060630` / `-acc2` / `-acc3` |
| SSH rc=0 | ✓ ×3 | verdict 逐连接记录 |
| 同会话 ≥3 次独立 SSH 连接 | ✓ | conn1/conn2/conn3 = 三次独立 TCP+KEX+auth+exec，均在 06:17-06:19 同一会话 |
| 内容校验传输 | ✓ | 262144 B 随机字节经 stdin→`wc -c`，phone 端 `count=262144 want=262144`，rc=0 |
| 客户端正常退出后管理通道 | ✓ | 三连接干净退出（FIN/ACK 交换在 trace）后 drain+getvar = `OKAY (alive)` |
| stdout/stderr/设备代际/脚本身份归档 | ✓ | verdict + `tssh27-20261110-060630-*.{out,err}` + run-id + boot_b=v23 graft 9e0609fb 绑定 |
| 桌面运行期连接推进 | ✓（待屏证归档） | 连接发生在桌面会话运行期内（实时观察通道在证会话形态） |

首 HIT（04:58:45，run 050010，`verdict27-20261110-050010.txt`）：conn1 单连接过最小门（Darwin/root/marker/rc=0），conn2 起被会话尾环残留+保存窗打断——两个"附加验收未竟"根因（getvar 误读排队内核帧；保存窗不可抗）已定位并修复（open_fresh_session 先 flush-upload；保存窗纯等待，reset 只用于死局）。次周期（06:17）全栈复跑即完整过门。

## 8. 阶段额度与后续工作

- 刷写预算：**0/3**（零刷写红线全程成立；march 只做 reboot，无 flash）
- 主机侧修复件：tunnel25w（推序/清洁退出/MSS=160/宽限重试/自限期）、timed-ssh-v27（相位占空比/六分支/验收包）、timed-ssh-v26 语法修复、私钥 ACL
- 新知：①MSS ~160B 环上限（wave21 netmode ping 只验过 100B）；②wave26 式常驻 probe 进程会拒绝其他 opener（孤儿 hunter 事故）；③返回后保存窗时长随脏度 27s→33min+；④post-return 有两条路：自愈 re-arm→下一会话（S2→S3）或掉落 Android（S1，march 回环）
