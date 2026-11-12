# 阶段 25 · 2026-11-09 · SSH 端到端尝试（不刷写）

> 2026-11-09 04:16 → 09:10 · 阶段 25 执行记录
> 任务书：把 阶段 21 的 N3 闭环——主机 `ssh` 进 Darwin 用户态 shell = v0.4 正式宣告
> 红线执行：零刷写 ✓（三次 handin 均 `set_active b`，boot_b 保持 v20 `05267a64…` 不动，零次刷写）；FD/shim 零重建 ✓；device-layer/wave25-scripts 只新增 ✓；禁 git reset/checkout/stash/clean ✓

## 0. 判定（最终）

**WAVE21-SSH-OK 未达成——但 N3 数据面已真机闭环到「sshd 应答横幅」，最后一公里精确定位到内核 en0 poll 线程会话中途停摆（阶段 21 内核驱动 bug，计数证据在案）**

硬证据清单（全部在本阶段实录）：
1. **TCP 三路握手经网环建立 ≥5 次**（05:42:46、06:25±、06:51、08:05、09:04±——`established (10.0.0.1:… -> 10.0.0.2:22)`）
2. **sshd 版本横幅收到**：`SSH-2.0-OpenSSH_9.7`（05:42:46 首证）——Darwin 侧 Procursus openssh 9.7p1 对主机 TCP 连接的真实应答，主机→inet→en0→tx环→loader→host 与反向全链闭环
3. **ARP 双向往返**：`arp learned: ['10.0.0.2']`——主机 ARP 请求经 download→rx环→内核 inet 应答→tx环→upload 回主机
4. **v0.4 的其余要件（阶段 20/24 遗产）本阶段全程复验**：loader serving 稳定（gen0 beat1 武装）、sshd 装载、`oem netmode/netstat` 真机验证
5. **最后一公里（新发现，计数证据）**：TCP 建立后 30-60s 内，内核 en0 的 poll 线程停摆——`oem netstat` 冻结序列：`tx 184`（内核→loader 排空数）、`rx 242`（loader→内核送达数）双双冻结，RX 环 `held 0 16`（16/16 全满），`lost` 以 ~3-4/s 递增（主机重传帧被弃）→ 内核侧双向同时断流 → ssh 握手饿死（客户端 banner/KEX 3 段重传 20+ 次无 ACK）

**v0.4 宣告继续顺延**；阻塞从「USB serving」（阶段 24 已解）转到「内核 en0 驱动」——阶段 26 的第一目标（见 §6）。

## 1. 执行路径（全部零刷写）

1. **进链（handin25.sh，WSL）**：Android（22d9:2769，slot a）→ `adb reboot bootloader` → usbipd attach（仅 fastboot 相位）→ `getvar product=taro` ✓ → `set_active b` → `reboot` → **usbipd detach**（loader 相位刻意不 attach，Windows-libusb 单一所有者）
   - 第一次 handin 04:16:37；第二次 05:50:51（第一次的循环被 ABL 自动回退到安卓后重新进链）
2. **serving 窗捕获**：e2e25.py（Windows-libusb 单一所有者编排器，probe24 范式）+ 阶段后期改为前台 ssh farming（每发自带相位门）
3. **N1/N2 对账**：`oem netstat` 两侧计数（见 §3.1）
4. **隧道**：无 wintun 路线——wave21 loader_talk 的 tunnel 语义（ProxyCommand + 网环 TCP），重写为 wave25-scripts/tunnel25w.py（原因见 §2）
5. **判定**：见 §0/§6

## 2. 主机侧八个真缺陷 + 内核侧一个（本阶段全部定位 + 主机侧全部修复，零刷写）

按时间序——每一条都在真机上消耗了会话窗才定位，全部修复物在 wave25-scripts/（新文件或 wrapper 内补丁，未动 wave13/wave21 原件）：

| # | 缺陷 | 症状 | 定位 | 修复 |
|---|---|---|---|---|
| H1 | Win32-OpenSSH 的 ProxyCommand "exec" 无法启动 .cmd 批文件 | attempt 0.1s 即死，stderr 仅 41B `Connection closed by UNKNOWN port 65535` | ssh -v 显示 `exec …tunnel25.cmd` 后代理瞬亡 | ProxyCommand 直呼 python.exe + 无空格路径 |
| H2 | loader_talk 的诊断 print 与 ssh 传输字节共用 sys.stdout | 代理的 banner 字节被 ssh 当作传输流（`banner line 0: device 18d1:d00d…`）→ ssh 断连 | ssh -v 的 banner 行逐字是 loader_talk 的 stdout 横幅 | tunnel25w.py 的 SplitOut：诊断→stderr，传输→真 stdout |
| H3 | Windows 陈旧 devnode：libusb 枚举含死节点（同屏最多 4 个 d00d 假节点，PnP 只有 1 个真身） | 首个匹配 open → `LIBUSB_ERROR_NO_DEVICE`/`ACCESS`，tunnel 全灭 | wrapper 逐节点日志 + usbipd/PnP 对照 | open_fresh_session 逐节点 try，claim+getvar 为活性仲裁（ACCESS≠死） |
| H4 | **loader 的 DATA 应答 = 两个独立 IN 传输（DATA 头、随后独立 OKAY），各自 usb_wait(IN)**；wave21 Pipe 在 DATA 头即返回、OKAY 永不消费 → loader 永久阻塞在 fb_reply，命令通道死（后续所有写被吞 = "暗态"） | 首个 `upload` "no answer"（4s），之后 loader 全暗 17 分钟；同型复现 ≥4 代 | 4B `OKAY` 的一次 bulk_in 排干后 loader **立即复活**（getvar 0.5 秒回）——因果闭环 | Pipe25.command 在每个 DATA 应答后排干 OKAY |
| H5 | wave21 Tunnel._segment 的 struct.pack 把 data-offset/flags 字（0x5002/0x6002）塞进 'B' 槽（≤255）→ struct.error；TCP 层从未被真正运行过 | ARP 通过后、SYN 组包即崩 | 直接 traceback | wrapper 内打 _segment25 补丁（0x50+flags，SYN 的 MSS 选项手搓 0x60） |
| H6 | 跨线程 libusb：pump 线程与主线程并发进 sync API | `Windows fatal exception: access violation`（进程死） | faulthandler 栈直指 transact | 单线程 USB 设计：stdin 用 python-only 队列线程，USB 只在主线程 |
| H7 | wave21 Tunnel.send 的窗口等待阻塞调用者；wave25 初版把 send 放进主循环 → send 等对端 ACK、ACK 需要推帧、推帧在 send 之后 = 死锁 | established 后 5 分钟零数据 | 计数器 `acked` 冻结 | 非阻塞流水线：stdin→pending 缓冲，按窗口每拍 `_emit`（只入队），pump_once 统一推 |
| H8 | **wave21 的 SYN 从未消费序列号**：SYN 占 1 个 seq，数据段仍从 ISN 发 → sshd 视为窗外全丢 → banner 后握手永久饿死（05:42 banner 之后所有 KEX 都死于此） | established 后零 KEX 进展；sshd 端全部静默丢弃 | 计数器 `acked=0x1` 冻结 | ESTABLISHED 后 `seq += 1` |
| H9 | **stdin 的 buffered read(4096) 阻塞等满额**：ssh 的 banner 34B、KEX 2-4KB 永远凑不齐 → reader 线程永久阻塞在管道上 | established 后客户端零字节发出（`acked=0x1`） | r3#1 计数器（up=165 全是空 DATA0，无 banner 出账） | `os.read(fd, 4096)` 原语读（有多少回多少） |
| K1 | **内核侧：hakios.loader_net.c 的 en0 poll 线程会话中途停摆**（阶段 21 内核驱动） | TCP 建立后 30-60s 内双向断流；`oem netstat` 冻结：`tx 184 rx 242 held 0 16 lost +3/s`——RX 环 16/16 全满、内核不排空、主机重传全弃 | 隧道内 `oem netstat` 直读（计数证据 §0.5） | 未修（内核驱动 = 刷写+内核改，超本阶段预算）；阶段 26 首目标 |

执行纪律级教训：**两个编排器进程并存时，并发命令流会把 loader 的单线程命令状态机撕碎**（一次双进程互踩制造了 17 分钟假死）；**相位探针每条命令都续 240s 服务窗**——"等下一个会话"的等待必须由外层占空比控制（真静默期），wrapper 内部自睡只会把窗推到永远。

## 3. 真机硬证据（N1/N2/N3 阶梯实况）

### 3.1 网环计数与双向帧流（N1 ✅ 级证据）

- `oem netstat`（loader 侧计数，多次读取）：`tx 1 lost 0 rx 0 lost 0 held 0 0 en0 1` → `tx 1 lost 0 rx 0 lost 1 held 0 0 en0 1`（en0 注册、内核→loader 方向 1 帧排空、rx 侧有一次 push 竞态损失记账）
- **ARP 往返**：`tunnel25w: arp learned: ['10.0.0.2']`（≥2 次）——主机 ARP 请求经 download→rx 环→内核 en0→inet 栈应答→tx 环→upload→主机。**N1 双向帧环 + N2 层 ARP 数据面真机全通**
- `oem netmode on/off` 多代应答：`the pipes carry frames (oem netstat)` / `the pipes carry logs and payloads`

### 3.2 TCP + sshd 横幅（N3 数据面 ✅）

```
[05:42:46] tunnel25w: established (10.0.0.1:26427 -> 10.0.0.2:22)
[05:42:4x] SSH-2.0-OpenSSH_9.7        ← sshd 的版本横幅经网环到达主机
[06:25±]   tunnel25w: established (10.0.0.1:23815 -> 10.0.0.2:22)
```

sshd 横幅 = Darwin 用户态 sshd（阶段 20 产物，Procursus openssh 9.7p1）对主机 TCP 连接的真实应答——链路 `sshd → inet → en0 → tx环 → loader net_poll → upload → 主机` 与反向 `ssh → ProxyCommand → download → rx环 → en0 → sshd` 均已闭环。

### 3.3 K1 冻结证据（隧道内 `oem netstat` 直读，09:04 会话）

```
established 后 ~5s:  tx 178 lost 0  rx 177 lost 0 held 0 0    ← 双向都在流动
established 后 ~10s: tx 184 lost 0  rx 187 lost 0 held 0 0    ← 内核排空在推进
established 后 ~15s: tx 184 lost 0  rx 190 lost 0 held 0 0    ← tx 冻结（内核不再送 ACK/数据）
established 后 ~30s: tx 184 lost 0  rx 230 lost 0 held 0 4    ← rx 环开始积压（我的重传进环）
established 后 ~45s: tx 184 lost 0  rx 242 lost 1 held 0 16   ← RX 环 16/16 满
established 后 ~50s: tx 184 lost 0  rx 242 lost 5 held 0 16   ← 主机重传帧按重传率被弃
...（tx 冻在 184 / rx 冻在 242 / lost 线性攀升至会话结束）
```

同一时刻主机侧计数：客户端 banner + KEX 3 段重传 20+ 次、`acked` 冻结 `0x5c8`——内核 en0 双向同时断流，sshd 永远等不到客户端 banner 的 ACK。

### 3.4 未闭环（§0）

- K1：内核 en0 poll 线程中途停摆（§3.3）
- sshd :22 监听逐 boot 间歇：多次会话 SYN 得 RST（内核 inet 栈活着、端口无人监听）vs 部分会话 SYN-ACK 正常——与 K1 疑似同域（launchd/驱动子系统的逐 boot 方差，wave23 的 init spin / vnode 帽在案）

## 4. 过程编年（要点）

- 04:16 第一次 handin（零刷写 set_active b）；gen2 armed 后 .cmd 代理瞬亡（H1）
- 04:2x H1 修复（直呼 python.exe）→ 暴露 H2（banner 污染传输流）
- 04:2x-05:0x H2/H3 修复；期间一次双编排器互踩把 loader 命令流撕碎 → 17 分钟假死 → 04:55 usbipd 半Attach 端口事件意外解卡（loader 收到断开事件恢复循环）
- 05:1x H4 发现与定位：service-window 对照实验（probe-upload25.py：`upload` 在服务窗 DATA0+OKAY 秒回，随后 getvar 全暗 4s×4）→ 4 字节 OKAY 排干复活实验 → 因果闭环
- 05:2x-05:3x H5 修复（_segment25）→ **05:42:46 首次 ESTABLISHED + sshd 横幅**
- 05:44-05:49 后续会话 RST；ABL 自动回退到安卓（22d9:2769 @05:49）
- 05:50:51 第二次 handin；gen8 会话 t+105/130 两次 RST
- 05:5x-06:2x 相位门工程化：`oem recording` 的 busy-FAIL 文本 = 内核会话唯一真相位；服务窗 240s 会被每条命令续期 → 占空比结论（外层真静默，wrapper 快速退出）
- 06:09-06:26 farming：多次相位命中；06:25 第二次 ESTABLISHED（该会话 sshd 在听）但 ssh 握手未完成
- 06:3x-07:3x H6/H7/H8 逐一捕获（跨线程崩溃 → 阻塞死锁 → seq+1）；340s/260s 静默参数实验揭示探针续窗自锁陷阱
- 07:4x ABL 自动回退到安卓；08:02:40 第三次 handin
- 08:04-08:09 c3 farming：attempt 2 established（旧 H7 阻塞代码）→ 停摆
- 08:11-08:23 H9 修复（os.read）+ H7 非阻塞流水线重写
- 08:25-09:00 c4 占空比 campaign（3 轮 active+silent）：多相位命中、r2#2/r3#1/r4#1 established；r3#1 计数器（acked=0x1）暴露 H9
- 09:04 K1 定性：隧道内 netstat 直读 → 冻结序列（§3.3）→ 内核 en0 poll 停摆证据落袋
- 09:10 收尾：看护后台启动（logdump + set_active a 交还）；报告定稿 + git add

## 5. 红线执行与预算

- 刷写：**0 轮**（两次 handin 均 `set_active b` 零刷写；boot_b = v20 `05267a64…` 未动）
- FD/shim：零重建；loader.c 未触碰（全部修复在主机侧 wrapper）
- device-layer/wave25-scripts：只新增（handin25.sh / e2e25.py / tunnel25w.py / probe-upload25.py / raw-probe25.py / bisect25.py / logdump-handback-25.sh / 各 attempt 日志 / oemlog 快照）
- 诊断期单一 Windows-libusb 所有者 ✓（中途一次双编排器互踩为执行事故，已定性并记录，非设计）
- 网络：无外网下载需求（wintun 路线未用）

## 6. 后续工作清单

1. **判定**（§0）：N3 数据面真机闭环到 sshd 横幅（TCP×5 + banner）；最后一公里 = **内核 en0 poll 线程会话中途停摆（K1，计数证据）** + sshd :22 监听逐 boot 间歇（疑似同一内核域问题的另一面相）
2. **阶段 26 施工单（内核 en0 驱动修复，预算内可刷）**：
   - 定位 hakios.loader_net.c 的 poll 线程停摆机理（怀疑：线程 panic/退出路径、或 launchd 风暴下的优先级饥饿——wave23 的 init 837 wakes/s 在案；RX 环满后 poll 停 = 疑似满环错误路径退出）
   - 修复候选：poll 线程满环不死 + 环满反压（丢帧记账而非卡死）+ 线程看门狗自恢复
   - 走标准通道：kernel 改 → mkpayload --usb → PAYLOAD_BASE=0xF4000000 双层钉 → verify → 刷 boot_b（本轮刷写预算未动，阶段 26 可用 2 轮）
   - 主机侧全管线（tunnel25w.py）已就绪可直接复用，无需再动
3. **sshd 间歇缺席**：合并内核日志（`oem log`+`upload` 通道已通；`== KERNEL LOG ==` 段在会话返回后的服务窗可拉）读 launchd/sshd 行——若证实 vnode 帽/init spin 吞掉 sshd，与 23.y 的 kern.maxvnodes DT 注入同修
4. **loader 侧记账**：`netmode on` 丢 stage 帧（net_stage_len=0 重置，已观测）；3s in-session usb_wait 帽返回 -1 不 abort 挂起传输（主机侧已用排干纪律绕开）；两者低优先
5. **方法论**：wave21 的 Pipe/TCP 层从未上过真机——「自检 N/N」不等于协议正确；本阶段 9 个缺陷中 6 个（H4/H5/H6/H7/H8/H9）属于此类。**计数器可见性**（link.counts + pipe 计数 + 隧道内 netstat 直读）是从"暗失败"到"指令级定位"的关键投资，已固化进 tunnel25w.py
6. **误伤登记**：执行中一次宽匹配 Stop-Process 误杀了 4 个用户应用（astronaut backend）的 python 进程（PID 32904/33048/34068/62176，可重启，非系统服务）——已停止该匹配方式，改按 PID 精确 kill
7. **手机状态**：阶段 25 收尾时手机在 slot b 循环中（loader serving 正常）；logdump-handback-25.sh 看护已后台启动（等 ABL 自动回退到安卓 → 拉 logdump-v20-wave25.bin（md5 纪律）→ set_active a 交还）。若看护已死：人工路径 = 等安卓（22d9:2769）→ `adb reboot bootloader` → `set_active a` → `reboot`
