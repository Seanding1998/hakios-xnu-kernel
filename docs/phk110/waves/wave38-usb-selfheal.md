# 阶段 38 · 2026-11-11 · USB 错误墙的两个 loader 侧根因与整对自愈修复

> 2026-11-11 · 阶段 38 执行记录 · **不需要手机的准备工作**（阶段 37 在用手机：零 adb/fastboot/usbipd/logdump，禁 wsl --shutdown；产物做到"可刷状态"即收尾）
> 使命：落实 wave34 §5 的 USB 对自愈设计（①无消费者不排队 ②堵死整对 END_TRANSFER 重建 ③打印限频）；根除用户投诉的"错误墙刷屏"（0xB → 0xC 墙机制已定案，见 wave31 ×2 / wave36 §3.4 第三轮 / f12 指令级归因）。
> 产物：**payload `9662823f…` / graft `742bce63…`（192 MiB，verify 65/65 全绿，FD `8924cb67` + shim `108ce972` 钉位不动）——可刷未刷**。版本号（v28…）刷写前与当时的工作安排确认，不抢号。

## 0. 判定（离线相）

**WAVE38-USB-SELFHEAL（离线）= DONE（可刷状态）**。四个施工单全部落地：①无消费者不排队 + 排空陈旧 TRB + 打印限频（loader.c 七 hunk，主刀）；②FD 层整对重建评估完毕——超出范围，loader 侧最小等效已实现（服务窗半启动残留重建 `usb_pair_rebuild`），FD 完整方案留档设计段（§5）不硬上；③离线构建 + verify 65/65（v27 的 62 检全保留 + wave38 语义钉 3 条 + entry/PAYLOAD_BASE 双钉位）；④回归门预案 + 真机验收行成文（§6）。**真机判定待 阶段 37 退役后由当时的工作安排授权刷写执行**。

## 1. 设计（风暴的两张脸，源码级定案）

已定案机制（wave34 §5 / f12 / wave31 / wave36）：bulk-IN（phys[3] = EpIndex 3 = 0x81）武装但无消费者 → TRB 环/URB 节点堆满 → vendor 栈每次提交失败打 4 行调试墙（`UsbDeviceSend` → `DwcPrepareURB:Trb: physical endpoint[N] not configured` → `UsbfnDwcSubmitUrbNode: PrepareUrb Failed` → `usbDevSsm: Failed to prepare data transfer`）**直写 framebuffer**（FrameBufferSerialPortLib）→ 转换点拆除 → 0xC 残留 → bulk 对死 / ep0 独活。本阶段把 **loader 自己给这堵墙喂食的两条提交路径** 定位到源码级：

**脸 1（IN 侧泄漏 = 0xB 风暴的泵）**：`usb_tx()` 提交 bulk-IN 应答后 `usb_wait(USB_EP_IN)` 的各放弃出口（会话相 `run_active` 3 s 界 / 服务窗相窗限 / 断线）**返回 -1 但不碰控制器**——已提交的 TRB 仍挂在环上。宿主半死形态（写 OUT 正常、不读 IN——usbipd 拔离 / 隧道消费者死亡 / probe24 中途崩）下，每条宿主命令 → `fb_reply` → 又一条 IN 提交 → 环/URB 池逐条堆满 → 之后**每次提交** vendor 必答 `no free URB nodes` 族 0xB 墙印。环堆满次序 = IN（ep3）先于 OUT（ep2）被注销——与用户屏摄的 0x8B→0x8C 时序吻合。

**脸 2（服务窗热旋 = 刷屏不止的引擎）**：`usb_command_loop()` 的 `usb_rx()` 提交路径**完全无门**（wave24 的 `usb_wall_gate` 只保护 `usb_arm_rx` 的武装路径）。半启动状态下 OUT 提交被拒 → `n <= 0` → `continue` 热旋 → 每旋一次被拒提交 = vendor 又 4 行墙印；且窗限检查在 `usb_wait` 里、提交失败提前 return **永远到不了** → 窗永不过期 → 手机永不出服务窗 → **墙刷到天荒地老**（用户投诉的直接机制）。

修复设计（对 wave34 §5 三条）：
- ①**无消费者不排队**：IN 侧单飞不变量（`usb_in_expect`，同时只许一条 IN 在挂）+ 排空（放弃即 `abort_xfer` = 该端点自己的 END_TRANSFER，陈旧 TRB 退役；其 Cancelled 尾声被 pump 吞掉不污染后续 wait）+ IN 门（连续 3 条未读应答 → 提交冻结，倍退避 1 s→30 s 封顶，每拍放行一条探测——**不提交 = vendor 无从打印**，风暴在源头断流）。OUT 侧：`usb_rx` 的提交纳入既有 `usb_wall_gate`（与武装路径同门同拍）。
- ③**打印限频**：IN 门 Engage 一行、vendor 拒探测每退避拍至多一行（≥2 s→30 s）、读恢复一行、重建各一行——每级失败计数 + 每级 N 秒至多一行；OUT 侧沿用 wave24 门的原拍。结构级 hunk（单飞不变量/杂项吞没/rx 门/10 s 界）零新增打印（打印预算纪律）。
- ②**整对重建**：见 §3 与 §5。

## 2. 实现（loader.c 七 hunk，`wave38-scripts/patch-loader-v38.py` 全部唯一性断言）

应用对象 = WSL 树 `~/hakios/kernel/xnuloader/loader.c`（备份 `loader.c.v37-orig`，sha `3ac12740…`）。构建 = `PAYLOAD_BASE=0xF4000000 ./build.sh`，**零警告**，loader.efi 86,016 B。

| # | hunk | 内容 |
|---|---|---|
| 1 | IN 台账声明 | `usb_in_expect`（单飞旗）/ `usb_in_stray`（无主完成吞没计数）/ `usb_in_stale`（未读应答数）/ `usb_in_ok` / `usb_in_refused` / `usb_in_gate_next,backoff` + `USB_IN_STALE_GATE 3` |
| 2 | pump 的 Connected 分支 | 新枚举 = 新读者：`usb_in_expect/stale/gate_next` 清零（门抬起、台账关卷） |
| 3 | pump 的 IN 完成分支 | `!usb_in_expect` 时的完成 = 被弃传输的尾声 → 吞没计数，**绝不**落进 `usb_done_in` 去回答未来的 wait |
| 4 | `usb_wait` | IN 侧 10 s 界（任何相位）：10 s 没被取走的应答不会来了——此前一条未读应答把服务窗整个坐满 240 s（聋窗形态） |
| 5 | `usb_rx` | 提交过 `usb_wall_gate`：退避期内直接拒（零提交零打印），拒绝走门（计数 + 拍打印）——脸 2 的热旋风暴断流 |
| 6 | `usb_tx` 重写 | 门检（冻结期拒 + 单飞不变量拒，静默计数）→ 提交 → wait → 成功（门抬、stale 清零）或失败（**abort_xfer 排空陈旧 TRB** + stale++；==1 一行；==GATE 门起一行；>GATE 退避倍增并刷新拍，vendor 拒探测拍一行） |
| 7 | `usb_pair_rebuild` + 循环 | 服务窗半启动残留重建（见 §3）+ `usb_command_loop` 的 `n<=0` 路径：先 `usb_pair_rebuild()` 再查窗限，非窗退的 `continue` 前加 `usb_wait_pumped(NULL, 50)`（安静且继续泵送的 1 s——热旋熄火） |

**重建探测器（双半一致才动手）**：`run_active == 0`（会话相绝不重建——start_ex 复位 DWC3 会杀死隧道，wave21.2 教训）∧ `usb_in_stale >= 3`（IN 半确认死）∧ `!usb_rx_queued` ∧ `usb_arm_code != 0`（OUT 半确认在墙上）∧ 距上次 ≥60 s ∧ 本窗 ≤2 次。序列 = `abort_xfer(IN)` + `abort_xfer(OUT)`（**对的双 END_TRANSFER**，陈旧 TRB 全退）→ 台账复位 → `signal_event(usb_init_event)` + `usb_start_attempt()`（vendor 的 start_ex 自带 StopController → 重建 ep0 + 描述符集；**下一次枚举的 SET_CONFIG walk 重新武装 bulk 对**——与 bring-up 重掷同一已证路径）。失败两次数 → `usb_ready = 0`，交给窗限 reboot 回退。

**回归面自查（SSH 语义保护）**：健康隧道路径（upload/download 高频轮询，应答亚秒完成）**零行为变化**——门只在 3×10 s 的连续读者死亡后才 Engage，且首次成功应答即抬；`usb_pair_rebuild` 有 `run_active` 硬闸；会话相唯一新增行为 = 应答放弃时排空 TRB（原本就是死应答）。wave24-26 的全部机制标记（镜面/单消费者/武装门/采样器/timeline/DWC3 wake）逐字节未动。

## 3. FD 层整对重建评估（施工单②，结论：不硬上，loader 侧最小等效已实现）

改动量评估（零接触设备，纯树内勘察）：

| 方案 | 落点 | 源可得性 | 代价 | 结论 |
|---|---|---|---|---|
| FD 内 FrameBufferSerialPortLib 限频 | `Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib/FrameBufferSerialPortLib.c`（**源码在树**；唯一 framebuffer 出口 = `SerialPortWrite` @L298，每字节 `WriteFrameBuffer` + 全帧 cache flush） | ✅ 源码 | **FD 重编 → FD 字节锚 `8924cb67` 失效** → wave21 以来全部 graft/verify 钉位链断裂 + 全 FD 面漂移风险（wave34 §1 同款结论，维持） | 留档设计（§5.1），不硬上 |
| FD 内 UsbFnDwc 整对重建/武装语义 | udon 的 `UsbfnDwc3Dxe.efi`/`UsbDeviceDxe.efi` = **Binaries/udon 裸 vendor blob（98,304/69,632 B，无源码）**；源码只有 Samsung 家族参照（`Silicon/Samsung/SamsungPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.c`，L180-245 ConfigureEnableEndpoints 一次装满含 bulk、L511/L527 Transfer 判 Enabled） | ❌ 只能字节手术 | f12 §6 末选：T2 speed==0 fallback / SetConfigIfc 重试等指令级改写——违反"零 vendor 风险"，且同样碎 FD 锚 | 留档设计（§5.2），不硬上 |
| **loader 侧最小等效（本阶段已实现）** | `usb_pair_rebuild`（hunk 7） | ✅ 我们的代码 | 零 FD 触碰：对的双 END_TRANSFER 可达（`abort_xfer`）+ 整体重配可达（start_ex 自带 StopController 的已证路径） | **已实现** |

结论：**"整对 END_TRANSFER 重建"的可达语义已全数落地在 loader 侧**（§2 hunk 7）；FD 层完整方案按施工单原文写成设计段（§5）留档，待未来某波主动重编 FD 时一并实施（届时 FD 锚迁移是当时的工作安排级决策）。

## 4. 离线验证（构建链 + 65/65）

| 件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-payload-wave38.bin` | `9662823ffa0f30ae` | 23,573,432 B，7 条目；**唯一 delta = loader.efi = wave38 自愈构建 `3f595c52…`（86,016 B）+ cmdline 换回 v26 字节（478 B，gpu=1 在内，wave37 的 `adreno_only=1` 探测参数不携带——那是 wave37 的域）**；kernel `a39c931c` / ramdisk `156b5be1` / resident / kernel.ver / usb 与 v26、v27 双向字节等（断言在 make 与 verify 两层） |
| `device-layer/udon-hakios-grafted-wave38.img` | **`742bce63e26efecc…`** | 192 MiB；FD `8924cb67…` + shim `108ce972…` 钉位不动（graft 脚本双断言）；`udon-hakios-grafted-wave38.img.report.json` 随件 |
| `wave38-scripts/patch-loader-v38.py` | — | 7 hunk 补丁器，全 hunk 唯一性断言（已应用；重跑必 MISS——守卫即断言） |
| `wave38-scripts/make-payload-v38.sh` / `make-graft-v38.sh` | — | 构建链（v27 配方 + wave38 条目替换；FD/shim 锚断言内嵌） |
| `wave38-scripts/verify-udon-hakios-wave38.py` | — | **65/65 全绿**（`verify-wave38.log`）：v27 的 62 检全保留，loader 钉换 `3f595c52` + wave38 语义钉 3 条（IN 门四行 / 排空行 / 重建三行）+ cmdline 改判（== v26 字节；无 adreno_only/adreno_fine）+ entry RVA 0x2140 + PAYLOAD_BASE=0xF4000000 布局无关钉 |

⚠ **构建不可复现发现（操作级新知）**：同源码两次 `./build.sh` 产出不同 sha（`c82a35e4` vs `3f595c52`，PE TimeDateStamp 所致）——**钉位必须钉实际入包 artifact；verify 绿之后到刷写之前绝不可重跑 build.sh**（重编即漂移、verify 作废）。verify 钉的是 `device-layer/udon-hakios-payload-wave38.bin` 内嵌的那一份。

WSL 树增量（未 commit，随本阶段交付）：`~/hakios/kernel/xnuloader/loader.c`（7 hunks）+ `loader.c.v37-orig`（回滚件）+ `loader.efi`（`3f595c52`）。

## 5. FD 层完整方案（设计段留档，本阶段不实施）

### 5.1 FrameBufferSerialPortLib 限频（视觉刷屏的 FD 侧终极治理）

落点 = `SerialPortWrite`（`FrameBufferSerialPortLib.c:298`，vendor DEBUG 直写 framebuffer 的唯一出口）。设计：模块级静态度（跨字节流）——①同前缀行（截到首个 `%`/`:` 前 24 字节）连续出现 >3 次 → 抑制后续同性行；②每 5 s 允许一条"节拍行"（原行 + `(xN suppressed)`）；③流切换（前缀变化）或 2 s 静默后 → 放行并补一行抑制计数。成本：SiliciumPkg 单模块 + FD 全量重编；**实施时机 = 下一次当时的工作安排授权的 FD 重编波**（与 f12 §6 末选的 vendor 字节手术互斥立项：先做本条——零风险纯增益——观察墙是否已足够安静，再决定是否动 vendor blob）。

### 5.2 UsbFnDwc 整对重建语义（vendor 栈内的根治形态）

以 SamsungPkg 家族源码为蓝本（本地镜像在树）：①`ConfigureEnableEndpointsEx` 一次装满全部端点含 bulk（maxpacket 用控制器能力上限而非协商速度表——消除 f12 §3.2 的 speed=0 陷阱）；②Transfer 失败路径对整对做 END_TRANSFER + `DwcConfigureEP` 重walk（对应我们 loader 侧 `usb_pair_rebuild` 的 vendor 内建版）；③转换点拆除（StopController/总线复位）后把 EP 表 state 字节显式重置语义化（消除 0xC 残留的隐式态）。udon 侧无源码 → 只能 AArch64 字节 surgery（判据地址 f12 §8 已全备：DwcPrepareURB 判据 @0x19584-88、ep0 SM case 9 @0x1672c、速度表 @0x20930）——**高风险档，仅当 §5.1 + loader 侧自愈双双不够用时立项**。

## 6. 真机预案（阶段 37 退役后，当时的工作安排授权执行）

**刷写**：`wave37-scripts/flash-bootb-v36.sh` 配方改 `EXPECT_SHA=742bce63e26efecc12023d8fdc446344302cbb92f7638f0905e6ff5488a2d841` + `IMG=$R/device-layer/udon-hakios-grafted-wave38.img`（三门：graft sha 钉 → `getvar product=taro` → `current-slot` 核对，OKAY×2 断言；WSL root fastboot，镜像走 /mnt/c）。**刷前检查**：verify-wave38.log 仍在且末行 sha == 742bce63（若中途有人重编过 loader → payload/graft 必须全链重做）。

**回归门（刷写后必验，缺一不可）**：
1. **SSH E2E 门（verdict27 语义）**：隧道接线 → N3 `ssh -i id_ed25519_phk110 -o ProxyCommand="…tunnel 10.0.0.2 22"` 捕获 `uname -a; ls /`，判据 = 输出含 `WAVE21-SSH-OK` 语义的 HIT（loader_talk.py 守护化默认行为，guardian 自检照旧）。**这是 loader USB 路径改动的第一回归门**——门只许 HELP 不许 HURT：健康会话里新门零触发。
2. **/var 门（verdict34 语义）**：march→write→cycle→read（`wave34-scripts/verdict-var-v34.py` 判据）：root marker 243 B 逐字同 + blob sha 三方全等 + VARFS = `/dev/ufs_darwin_data`。证明新 loader 的会话/服务窗语义与 v24 等价（/var 写读链全在新代码路径上跑过）。

**验收行（本阶段使命的判定）**：
- **A1（0xB 风暴消失或限频生效）**：会话/服务窗相位屏上不再出现连刷的 `physical endpoint[N] not configured` / `PrepareUrb Failed` 墙（根治形态），或退化为每 ≥2 s 至多一行（限频形态，行内带 `x%d unread / x%d turned away` 计数 = 新门在工作）。
- **A2（半启动状态不再出现 / 可自愈）**：服务窗结束/读者死亡后，日志出现 `a reply came back unread` →（第三次起）`the IN gate is up` → 双半确认后 `the bulk pair reads dead both ways … rebuild 1 of 2` → `the pair's rebuild is in`；宿主重连（usbipd attach）后 SET_CONFIG 能重新武装（checkpoint-1 复现）即真自愈；两次重建后窗限 reboot 干净退出（不再无限刷墙）。`0000:0002 描述符失败` 死 devnode 形态不再持续到窗末。
- **A3（SSH 回归 HIT）**：门 1 全绿。
- 反证记录位：若屏上墙照旧连刷（限频未生效）→ 抓屏 + `oem log` console，检查 `the IN gate is up` 是否在案——不在案 = 风暴另有第三张脸（回填本档 §1）；在案但墙仍连刷 = vendor 在无人提交时也打（推翻 f12 的"每提交一墙"模型，另立项）。

**回滚**：boot_b 现件（v27 `d61d454a`，wave37 的已刷入版）不动即回滚态；wave38 刷入后回滚 = 重刷 v27 镜像（flash-bootb-v37.sh 原样）。boot_a 零触碰纪律不变。

## 7. 转入与纪律

1. **产物可刷未刷**：版本号（v28?）刷写前与当时的工作安排确认；`wave38-` 前缀件名保持。
2. wave37 若已占用 v28 → 本阶段产物顺延，只换件名不改字节（verify 对件名无关，sha 钉不变）。
3. probe24 的 TypeError 崩溃（wave31/wave36 沿用账）与本阶段无交——但注意 probe24 崩溃正是"读者中途死亡"的现实成因之一，修复它 = 减少本阶段门的触发源（建议下一阶段顺手修）。
4. 大 bin 不进 git：payload/graft 在 `device-layer/`（gitignore 域），sha 已记账于本档 §4 与 progress.log。
5. 波内零设备操作记录：本阶段全部动作 = WSL 树构建 + 仓内文档/git；usbipd/adb/fastboot/logdump 零调用，wsl --shutdown 零次。

## 8. 阶段 42 修复完成（v35 判定轮：解 LLVM 阻断 → v35 打包 → 真机验证三门 → 三门判定）

> 2026-11-11/12 · 阶段 42 执行记录（交接文档 = `wave38-handoff.md` §3.1 的阻断项 + §3.2 判定全流程）。
> 外审报告三的 GEN-1..4 分代修复链在本阶段完成 **ship-grade 二进制落地 + 真机验证判定**。

### 8.1 解阻断：-O1 消除的根因（forensics + 根治）

- **复现**：交接树 loader.c（md5 `091063cb` = GEN-4+hardening）在 ship flags（`PAYLOAD_BASE=0xF4000000` build.sh）下编译，gen-4 三特征串 0 存活；gen-3 备份的旧检测器同条件存活（校准成立）。binary 级复核：在树 loader.efi `9d2799a7`/loader.obj `d3f94cda` 均为消除形态。
- **凶手 pass 实锤**（`-print-after-all` + `-filter-print-funcs`）：前端 IR 完整正确；**IPSCCPPass** 把 GEN-4 四个时间戳全局（`usb_pair_last_progress` / `usb_pair_born_at` / `usb_wall_last_at` / `usb_last_connected_at`）常量折叠为 0 初始化值（它们的非零存储全在恢复函数体内，而该函数在同一次 solve 中未被标可执行——volatile fn-ptr 调用点=未知被调方，不授予可执行边；直调形态同样死于折叠，V1 实验=95f1f555 形态复现消除），每个检测守卫全部折叠进"无近期拒绝→早退"路径，守卫之后函数体整体删除（残余 stub = `mrs CNTFRQ; mrs CNTVCT; ret`）。**optnone 不保护**（实测）；fn-ptr 间接调用不保护（实测）。
- **根治（源码语义级）**：四时间戳全局改 `volatile`——它们本就是跨上下文状态（pump 的 Connected 路径 vs 服务窗循环；本文件对这类旗标的一贯规范即 volatile：`other_cpu_stage`、net prod/cons 对）。同时撤 v38g 的 10 函数 optnone（全在 USB 热路径，纯死重）与 v38h 的 fn-ptr 间接（死重），恢复 49/0 套件验证过的直调形态；`usb_pair_rebuild` 保 noinline（符号可验证 + 不占热循环 icache）。补丁件 `wave42-scripts/patch-loader-v42-stamps-volatile.py`；备份链 +`loader.c.v38-gen4hard`；loader.c md5 `091063cb` → **`af695732`**。
- **验收（三级反汇编断言，非退出码）**：① obj 级 `usb_pair_rebuild` @0xd99c 实体 + 完整守卫链反汇编；② obj COFF 重定位表：五条 gen-4 打印串 + 事务调用（abort×2 经 USB 结构、signal_event、start_attempt、volatile 全局×4）全部落在函数 extent 内（`probe9-relocs.sh`）；③ 出货 efi（无符号表）级：ADRP+ADD 对**逐字面量精确绑定**（`probe10-efi-assert.py`；注意字面量真起点在可搜索子串前 15 B——`usb: [t+%d.%d] ` 前缀）。
- **GEN 全链在终态源码重跑**：usb-harness **49/0** + mirror-harness **22/22**（`wave42-scripts/*-results-v42.txt`）。
- **构建冻结**：loader.efi = **`5de055ea`**（90112 B）；verify 绿后零重跑。

### 8.2 v35 打包（新 sha 记账）

payload `udon-hakios-payload-v35.bin` = **`82add009`**（27472728 B）＝ v33 内核 `55a8d40f`（字节等断言）+ cmdline（v26/v33 字节 gpu=1，字节等）+ ramdisk **`c2780842`**（wave39 GL=test 载体；**从 v34-GL payload 钉位提取**至 `device-layer/root-apfs-c2780842.bin`——WSL 树 root.apfs 已被 wave41 重建为 `51a030c3`，留给 v36，当时的工作安排变量隔离令）+ resident/kernel.ver/usb 字节等 + loader `5de055ea`。graft `udon-hakios-grafted-v35.img` = **`6558d303`**（192 MiB）。**verify-udon-hakios-v35.py：69/69 全绿**（`wave42-scripts/verify-v35.log`）——loader 钉换 `5de055ea` + GEN-4 新钉 7 条 + GEN-1 措辞钉 2 条；v34 的 F10 布局钉（movz w8,#0xF400 六条内邻近 movk w3,#0x5055）是 `3f595c52` 编译布局的巧合，v35 改**语义常量钉**：0x50554E58 与 0xF4000000 均须由 movz/movk 对构造且一处构造对相距 ≤16 条（probe13/14 forensics）。

### 8.3 真机验证：三门刷写 CONFIRMED

`wave42-scripts/flash-bootb-v35.sh`（EXPECT_SHA=graft 实值全串——v34 安全刹车教训内建）：graft sha 钉 → getvar product=taro → current-slot（b，含 set_active）→ flash boot_b **OKAY**（4.865s+0.694s）→ set_active b + reboot。**23:51:25 FLASH CONFIRMED**（`flash-bootb-v35-w42a.log`）。

### 8.4 判定会话（外审修订表三忠实执行）

**门 1 SSH 完整语义 = 全绿**（`wave42-scripts/verdict42-w42ssh9.txt`）：HIT + 3 独立连接（nonce+Darwin 各自 OK）+ 256 KiB 传输 262144/262144 + **双向内容 SHA（v42 新增，单连接双方向：512 KiB 随机 blob → 设备 sha256sum MATCH → 同连接 cat 回读 → 主机字节级 MATCH，524288/524288）** + 干净退出后管理通道 OKAY。历时 9 次猎守迭代，抓出并修复两个**主机侧真缺陷**（均工具级，与 loader 无关）：①每次隧道关闭诱发持久化 GUID auto-attach 抢设备（≤20 s 故障窗；2 s 看护 + 步级重试治之）；②ssh_attempt 对二进制 stdout 的 UTF-8 decode 膨胀（w42ssh8 事后尸检：524288 B 合法流被 U+FFFD 膨成 951051 B"替身"——设备侧三轮全对，"长度≠内容"教训的主机侧版本）。

**门 2 /var 回归（verdict34 语义）= WAVE42-VAR-PERSIST**（`wave42-scripts/verdict42-var.txt`）：写（gen N 02:46，包 rc=0）→ 世代切换（一次完整内核死亡）→ 读（gen N+1 02:56，包 rc=0）。root marker 243 B 逐字同；设备上 ls 尺寸 243/243；**marker mtime 保留**（写时刻 619 == 读侧 stat 619，per-boot 绝对帧——v34 判定器 line 125 硬编码 `==197` 是 w34 实例值，w42 裁定修正记录在 verdict42-var.txt）；/var/jb marker STRUCTURAL-NA（init.c per-boot re-graft，wave34 已定案）；64 KiB blob sha 三方一致；ssh host keys 一致。继承判定器的两处机械伪影均已记录在案。

**门 3 gl_test（v35 载体=纯诊断，不记首帧）= 诊断性完成**：升级 runner（wave41 §6：GL_RC 数值解析、硬件 DONE 四条件、`gl_test:` 字样永不构成完成、softpipe 单列、per-attempt 工件；classifier stub 9/9）。四轮实猎（w42gl1-4）拿到 **v35 载体上 gl_test 的首次真机调用事实**：zsh `command not found`（GL_RC=127）——PATH=`/usr/bin:/bin:/usr/sbin:/sbin:/var/jb/usr/bin` 下不可达；镜像配方显示 `cp obj/gl_test root/bin/`（应在 /bin/gl_test），但每轮发现步都撞上会话尾（多轮会话进入均为末秒态）。六分支判定在 v35 上**不可完成**（命令层未达），如实标注待 v36 新载体（51a030c3，验收器内建）执行；本轮不改六分支表任何行。

**A1/A2（野外观测可行范围，如实）**：
- A2 相关野外事实：v35 世代 1-3 出现 `0000:0002 描述符失败` 纯 0xC 半启动残留形态（23:52-00:21，跨两次窗重启后自愈至干净枚举）。**自愈归因不能给 GEN-4 窗内恢复**（其打印在半启动状态不可野外观测；时序与窗到期重启彩票一致）——按修订表如实记"出现+自愈，归因未证"。
- A1（0xB 墙消失/限频生效）：本轮未取证——loader 打印走 vendor 串口门，主机侧不可见；SSH 会话内无该墙的观测面。**待故障注入/串口侧取证**。
- A2 读者消失/返回三阶段：host 侧故障注入工具**未建**（handoff §3.2 在案），如实标注待建。
- **野外新根因（本阶段首证）**：世代循环中断 = **ABL 启动回退把 active-slot 翻到 a**（resume-slotb-w42r1/r2.log：current-slot at resume = **a** 两次实锤）——`set_active b`（授权的纯切槽，boot_a 零触碰）即恢复循环。此机制解释 wave38 的"21:20 循环中断"。
- 会话进入的运维面新知：持久化 usbipd GUID 在重枚举时 auto-attach 抢设备（Windows libusb 打不开）→ 2 s 看护 detach 循环（`watch-attach-v42.sh`，红线内只 detach）。

### 8.5 交付物清单（wave42-scripts/）

`patch-loader-v42-stamps-volatile.py`（根治补丁）、`probe1-repro.sh`…`probe15-stream.py`（forensics 家族）、`rebuild-dr.dis.log`/`afterall.log`（反汇编/IR 证据）、`make-payload-v35.sh`/`make-graft-v35.sh`/`verify-udon-hakios-v35.py`/`run-verify-v35.sh`（打包链，verify 69/69 = `verify-v35.log`）、`flash-bootb-v35.sh`/`resume-slotb-v42.sh`/`watch-attach-v42.sh`（真机验证链）、`derive-timed-ssh-v42.py`/`timed-ssh-v42.py`/`patch-sha-rt.py`（门 1 工具：v27 协议 + 双向内容 SHA + 重试 + 原始字节管道）、`runner-classify-test.py`（门 3 classifier stub 9/9）、`pin-check-v35.py`、`verdict42-w42ssh9.txt`（门 1）、`verdict42-var.txt` + `verdict42-var-mechanical.txt`（门 2）、`usb-suite-results-v42.txt`/`mirror-suite-results-v42.txt`（49/0 + 22/22）、`hunt-*.log`/`flash-*.log`/`resume-*.log`（全程流水）。progress.log 记账：wave42 phase 1-5。
