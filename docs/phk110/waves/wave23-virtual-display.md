# Wave 23：虚拟显示出画取证（v19 cmdline-only 刷写 + v19b 四项补丁 + 屏录提取链）——施工/刷写/取证/判定报告

> 2026-11-09 00:40 → 02:xx · Wave 23 执行子代理
> 施工单出处：`docs/research/f13-virtual-display.md` §B.6（Wave 23.x）；判据基线：`docs/waves/wave22-host-visibility.md` §7；外部审阅两轮：`docs/review/gpt-review-report-2026-11-09.md`、`docs/review/gpt-review-report-2-2026-11-09.md`

## 0. 一句话结论

**出画判定未完成（无 mp4 / 无日志级出画铁证），本波把"提取链为何拿不到"从疑似收敛为三层实锤，并把全部修复面移交 Wave 24（Exp-1 诊断刷写）**：①cmdline-only 的 v19（rec_secs/rec_ring/rec_mb + loader_return_after=300）一次刷写上机，屏录在机内每循环重新武装（内核侧链路工作，见 §5 logdump 判读）；②提取失败的原因不在屏录本身，而在 serving 窗：Round 1 两循环 bulk 对 un-armed（DwcPrepareURB phys[2] 状态 0，用户屏摄四行链实锤），loader 返回后 `usb_ready=0` 直接重启，240 s 服务窗从未打开；③v19b（软化重掷 + 服务相位提前 + raw 码透传 + settle 5s）由协调方刷入上机，但审阅抓到其 5 处实现缺陷（§6），结论一律打折；④提取脚本两处协议 bug（缺 `upload`、FAIL 冒号错位）由审阅抓获、已修复并 8/8 单测（§4）；⑤**本波最重要的工程发现 = cmdline 真实预算**：loader 组合头 110 字符（f13 的"预算余 228"作废，en0_addr 被置换下机，§1）。

## 1. T1 案头核实（零手机，全部树内实证）

| 项 | 核实结果 |
|---|---|
| 屏录 boot-args | `rec_secs`（默认 0）/ `rec_start`（默认 0）/ `rec_mb`（默认 **480**）/ `rec_ring`（默认 0）/ `rec_step`（2-8，默认 3）——`MiniIOMobileFramebuffer.cpp:118-142`；`fb_hz`（默认 60，:162）；`surftrace`（默认 **24**）与 `surftrace_of`——`MiniIOSurface.cpp:94-99`。f13 拼写全部正确，默认值三处（rec_mb/surftrace）与 f13 假设不同 |
| 提取命令链 | `oem recording`（loader.c:4678）只 stage 并回 OKAY → **真正发数据要后续 `upload`**（:4643，`DATA<hexlen>` + 1 MiB 块 + 尾部 `OKAY`）→ `tools/recording.py`（RWREC003 头 {magic,width,height,frames,oldest}+began@24，帧=8B 纳秒 + w×h×3 RGB，需 ffmpeg）。fastboot 等价 = `fastboot oem recording` + `fastboot get_staged` |
| 提取时机 | 录像缓冲**只在内核返回后**交给 loader（loader.c:3844-3852 `the kernel left a screen recording`）；内核运行期 `oem recording` 被 busy 门拒（:4435）；返回后 `if (usb_ready) usb_command_loop()`（**240 s 服务窗**，:5115-5119）——`usb_ready=0` 则直接 `reboot()` |
| **cmdline 真实预算** | **607 上限是组合后的**：loader 先拼 110 字符头（`debug=0x8 `(10) + `rd=md0 `(7) + `ufs_shared_pa=0x<16hex> `(33) + `hakios_kver=<47> `(60)），payload cmdline 排最后、超长砍尾（loader.c:3368-3452，`BOOT_LINE_LENGTH=608`）。**地面真值**：logdump-v18.bin @83231 的 v15 时代组合行恰 581 = 110+471。v18 余量实为 **26 字符**，f13 §B.6 的"预算余 228"不成立 |
| F6（vnode 表） | 无 boot-arg 可调：`desiredvnodes = sane_size/64K+1024`，帽 CONFIG_VNODES，唯一覆盖口 = **设备树属性** `kern.maxvnodes`（`PE_get_default`，unix_startup.c:200-215）——需 loader 改动，本轮红线禁止。按施工单接受风险：panic→stackshot→干净返回，`loader_recording` 照常移交，rec_ring 保尾帧 |
| busy 门 | `oem recording` 在内核运行期回 `FAILa kernel is running (oem stop ends it)`（:4437；fb_reply 无冒号，见 §4） |

**cmdline v19 决策**（一处与施工单的偏离，理由如实记录）：预算差 9 字符，故**去掉 ` en0_addr=10.0.0.2`（−18）**换 ` rec_secs=280 rec_ring=1 rec_mb=256`（+35）+ `loader_return_after=180→300`（0）；`surftrace=24 surftrace_of=backboardd fb_hz=30` 全部落选（surftrace=24 已是默认，b25 未带该参数也出了 surface 行；fb_hz 默认 60）。偏离理由：en0 驱动**无此参数则整体不启动**（hakios.loader_net.c:11 "is what turns this on"），但本波 serving 走 loader USB bulk 命令通道，与 IP 无关；touchscreen=1 不可去（inject.c 虚拟 HID 消费 /dev/hakios-touch）。组合后 **488+110=598/607**，无截断。审阅确认此修正方向正确、余量小（§八-4：最终以 logdump 实印 cmdline 验收）。

## 2. T2 构建（wave23-scripts/ 新目录，Windows device-layer 只新增）

| 件 | v19（Round 1） | v19b（Round 2 四项补丁） |
|---|---|---|
| cmdline | `udon-hakios-cmdline-v19.bin` 489 B（488 字符+NULL），sha `2fbd6c9dfa82852e…` | 不变（v19b 只动 loader） |
| payload | `f38198b9f026e1b4…`（23,387,672 B；loader/kernel/resident/ramdisk/kernel.ver/usb = v18 payload 条目逐字节） | `4d41b93939174c57…`（23,388,184 B；只 loader 换 v19b） |
| loader | **不重编**，v18 `553289a4…`（77,312 B）原样携带 | `9dc2f5db2fd0a5eb…`（77,824 B；`PAYLOAD_BASE=0xF4000000 ./build.sh`；entry RVA 0x2140 不动；XNUP movk 后随 movz 0x52BE8008 实测在 RVA 0x2190） |
| graft | `udon-hakios-grafted-v19.img` **`935360deed1b379b…`**（192 MiB） | `udon-hakios-grafted-v19b.img` **`5468b6f2fc426082…`**（192 MiB） |
| verify | `verify-udon-hakios-v19.py` **55/55**（v18 条目逐字节断言 + PAYLOAD_BASE 双层钉 + 新 cmdline 断言） | `verify-udon-hakios-v19b.py` **48/48**（四项新字符串在场 + 25s 行退役 + 条目对 v19 逐字节） |
| 脚本 | make-cmdline-v19.py / make-payload-v19.sh / make-graft-v19.sh / run-verify-v19.sh | patch-loader-v19.py（8 hunks）/ make-payload-v19b.sh / make-graft-v19b.sh / flash-bootb-v19b.sh |

**v19b 四项内容**（协调方更新单，patch-loader-v19.py 从 v18 树 delta）：
1. **软化重掷**：`host_seen`（代际内 DeviceStateChange 事件即置位）→ 该代际不重掷（不 detach），打印 `kept its host: no re-throw`；gen0 窗 6→24 拍（~120 s）。
2. **服务相位提前**：奇数拍走 `usb_poll_command()`（其 511 B 接收**就是**该拍探针——同一 DwcPrepareURB 门：收下=armed 且主机命令当场服务；拒收=同一堵墙）；`usb_stage_serving` 使 fb_command 拒绝 run 类命令（防 run_kernel 重入）。
3. **raw 码透传**：`usb_probe_raw_code()`——locate `EFI_USBFN_IO_PROTOCOL`（GUID `32d2963a-fe5d-4f30-b633-6e5dc55803cc`，Mu-Silicium EFIUsbfnIo.h；Transfer 在 +0x50，布局以 wave22 [+0x90]=ConfigureEnableEndpointsEx 交叉印证）；只在 wrapped 探针非零后的 beat 0 调一次（un-armed 时提交在排队前被拒，不碰 armed 路）。
4. **settle 25s→5s**（毒窗缓解，v16 有"首试即成"先例；竞态风险由 3-try + 重掷机盖住）。

## 3. Round 1（v19）刷写与循环（预算 1/2，Boot #37）

标准通道一次通过（01 前夜 00:50-00:53）：WSL root fastboot（`sudo -n`——首版脚本漏 root 权限卡死一次，已修）、`getvar product`=taro ✓、graft sha `935360de…` 复核 ✓、`flash boot_b` Sending 4.735s / Writing 0.739s 全 OKAY、`set_active b` ✓、00:53:30 `reboot`。

**循环形态（fetch23.log + Windows 总线）**：
- 00:56:43 采样器上枪 → gadget `18d1:d00d xnuloader` 在总线，open+claim 全成；
- 00:57:37-01:01:30：~24 次 `oem recording` bulk-OUT 写**全部吞没**（LIBUSB_ERROR_TIMEOUT，un-armed 会话，loader.c:4839 的反复重提交也不存在——内核运行期 usb_poll_command 同样提交失败）；
- **00:57:49 异常行 `oem recording did not stage: NONE b''`**（审阅点名的"潜在成功 OUT 线索"，已核对当时脚本版本 = v1 首版，控制流为 send 成功→read 8s 超时）：**该次 13 B bulk-OUT 写被设备收下（ACK 完成）**，只是 8 s 内无应答。4 分钟窗口 24 次写中仅此一次——不可复现的一次性 OUT 完成，与"transient 武装窗/一次性接收在队"相容，如实入档；
- 01:02:16 gadget 消失（→ `0000:0002` 死节点）：内核 ~300 s 会话结束返回，loader `flush_log()` 写 logdump 后 **`usb_ready=0` → 直接 reboot()，240 s 服务窗从未打开**——Round 1 两循环均 un-armed，录像提取无一机会；
- 01:07-01:16 第二循环同形态（un-armed）。

## 4. 提取脚本协议修复（审阅 §六-2/§六-3，P1 两处 + 活性检查）

v1 的两处 P1 **全部成立、已修复**（fetch-recording-23.py v2/v2.1）：
1. **缺 `upload`**：stage OKAY 后 v1 直接读 DATA——USB 全通也会超时。v2：stage OKAY → `upload` → `DATA<len>` 全长校验流式落盘 → **消费尾部 OKAY**（loader.c:4661）。
2. **FAIL 解析错位**：`fb_reply("FAIL", text)` = 4 B `FAIL` 直接跟正文**无冒号**（loader.c:4465-4475 实证；loader_talk 文档串是错的）。v2 解析 `FAIL<text>`，"kernel is running"/"still arming"/"no recording" 正确分类。
3. 新增固定只读 `getvar:version` 作每 episode 首个活性检查（写被吞=un-armed；OKAY=armed 且协议活着——"USB 死"与"应用协议等待"分开）；DATA 计数失配回 UNDERRUN；设备被他主持有（usbipd attach → NOT_SUPPORTED/ACCESS）时 20 s 退避不争抢（单一 Windows-libusb 所有者纪律）。
4. **8/8 线红单测**（OKAY 裸/带尾、FAIL 无冒号两种真文本、DATA 内联/分块+尾 OKAY、OKAY 分块、UNDERRUN、getvar 版本）全过；脚本 v2.1 已上枪守 v19b 循环。

## 5. v19b 上机（协调方刷写，预算 2/2 用毕）与判读边界

v19b（graft `5468b6f2…`）由协调方刷入 boot_b 并进入循环（本子代理未刷，预算内授权归协调方）。手机在机期间 Windows 总线形态：偶发 xnuloader episode（01:15:46 一例，写被吞；01:25/01:33 同）+ 持续 `0000:000x` 死节点；01:33 起 ABL fastboot gadget（`Android`）attached 于 WSL。

**判读边界（审阅 §一、§五，全部采纳）**：v19b 的 5 处实现缺陷使"v19b 循环仍 un-armed"这一观测**不能当作任何假设的证据**：
- `host_seen` 生命周期错：等待 helper（usb_wait_pumped）内消费的状态事件不计入（漏收）+ Disconnected 也算"主机在场"（假阳性）+ 每代清零；
- TransferNotification 被等待 helper 丢弃：奇数拍真实 RX 完成不路由、`usb_rx_queued` 失真（"主机写入完成但命令未执行"与"接收标志过期"两条新故障面）；
- raw 探针只在 beat 0（恰是最差的采样点——present 后配置大概率未发生，§五-F5）；
- `BS->stall(200000)` 降级路 = **200 ms/片**（250 片=50 s 非 5 s；1250 片=250 s）——set_timer 返回值未查（F3 同族：usb_present 的 stall(50000) 实为 50 ms，注释错）；
- GCTL bit11 置位后等自清、超时不主动清（Linux 显式清 CORESOFTRESET；"三重唤醒无效"的旧结论不能完全排除复位生命周期问题）。
以上全部并入 Wave 24 修复，**不得用作本波任何方向的结论**（审阅明令）。

**logdump 判读**：[待 Android 返回后自动拉取补齐——见 §8 附记。截至 01:59 手机状态 = ABL fastboot gadget（`18d1:d00d Android`）自 01:33 起持续停在总线并 attached 于 WSL（>25 min 静止）——非循环形态、归属不明的意外态，按红线停手不猜，交主代理裁决；auto-logdump-23.sh（Android 一回即拉）与 fetch23 v2.1 采样器（xNuloader episode 一回即试提取）均在后台值守，主代理处置后无需本子代理在场即可自动取证。]

## 6. 审阅项逐条清单（已验证/已修复/转入下一波）

**已验证（本子代理复核属实）**：
- fb_reply 无冒号（loader.c:4465）✅；upload 才发数据（:4643）✅；服务窗 `if (usb_ready)`（:5117）✅；错误墙刷屏源 = usb_poll_command 未武装时每 pass 重提交 511 B 接收（:4839 一带）✅；cmdline 组合头（110 B 实测）✅；屏摄四行 = DwcPrepareURB phys[2] 状态 0 → 0x8000000C → UsbfnDwcSubmitUrbNode/Transfer/UsbDeviceSend 尾链 ✅（审阅二轮：**对照片中这些提交，"没排队接收"的解释已不够，直接原因 = vendor 软件端点状态为零**；但状态为何为零仍未分辨——Exp-1 目标）。

**已修复（本波）**：提取协议两处 P1 + 活性检查 + 单一所有者纪律（§4）；cmdline 预算（§1）。

**转入 Wave 24（Exp-1，见 §7）**：v19b 五缺陷、统一事件消费入口、持续真实 RX、双层 speed/phys 采样、GCTL bit11、前导错误粘性、四检查点验收、失败提交限频、ConOut 镜像钩子。

**结论修正（写进底账）**：
- 撤回：fetch23"已发 set_configuration"/"2.5 min 稳定窗=同一代际"——libusb WinUSB 对同配置号 set_configuration 本地短路（v1.0.29 windows_winusb.c L3014-3031），无代际证据；**H1/H2 升为首要嫌疑的表述撤回**（现排序 H1>H2>H3 为条件概率暂排，证据不足）。
- 修正：f13"23.x 与 USB 阻塞零耦合"过强——屏录在内存、提取走 loader staging/upload，USB 不通则显示取证只能算未完成（本波即实证）。
- v18 的 `armed at generation 0, beat 1` 措辞应收窄：证明的是"该次 OUT 零长度提交被接受"，未独立验 IN、未等真实数据完成，"bulk pair 双向验证完成"超出证据。

## 7. Wave 24 = Exp-1 诊断刷写施工单（终稿，预算另批）

**零刷写前置（已完成或须保持）**：提取协议 v2 ✅；getvar 活性 ✅；单一 Windows-libusb 所有者（不再 usbipd 手术）✅纪律已立；logdump 验收 cmdline 实印。

**刷写件构造（一轮，失败也产出结论）**：
1. **统一事件消费入口**：单函数统一 handle_event + 状态更新（usb_connected/host_seen）+ TransferNotification 路由（真实 RX 完成交给命令服务并正确清 usb_rx_queued）；有上限的连续排空，记录最大 pump 间隔/积压量/错误返回（F1）。
2. **持续真实 RX**：一条非零长度 OUT 接收常驻（提交返回码 + 完成事件均记录），退役零长度探针与真实接收争用；`usb_rx_queued` 带代际与请求身份（P2-4）。
3. **失败提交限频 + 首错粘性**：持续失败退避（不刷屏）；首错打一次带计数器（审阅二轮第 1 条，升优先级——前导行在屏从毫秒级变几十秒且不被淹没）。
4. **单调时间线**：present / ConnectDone / SET_CONFIGURATION 处理 / reset / init kick / start_ex / 首次 OUT 提交结果，同一会话单调时钟逐条记录（审阅二轮第 2 条）。
5. **双层 speed + 端点状态采样**（先核验对象布局再读）：UsbfnDwc `+0x184` 与 UsbDeviceDxe `+0x1f8` 两层 speed、phys[2]/phys[3] 状态；重点采样**首次配置之后**与**持续失败末端**（审阅二轮第 3 条；raw 探针移出 beat 0）。
6. **GCTL bit11 显式解除**：复位流程按 Linux CORESOFTRESET 语义显式清位；present 前读 GCTL 确认复位已解除（P1-6）；顺修 usb_present 的 50 ms 注释错。
7. **ConOut 镜像钩子（~20-30 行，替代已判死的屏摄路线）**：loader 入口保存 `gST->ConOut->OutputString` 原指针装 thunk，vendor 打到 UEFI 控制台的每行（DwcPrepareURB 四行链 + 前导错误）同步抄进 loader 日志环随 logdump 落盘；thunk 防递归（抄环不重入原打印）；**动手前先案头核实 vendor 打印确实走 ConOut**（屏上错误行与其它控制台输出同一滚动区 = 旁证；若走独立 framebuffer 路径则改钩 DebugLib）。
8. **前导错误粘性保留清单**：`DEPSTARTCFG Fails` / `Failed to set config for ep` / `DwcConfigureEP failed` / `Unknown USB Speed`（审阅二轮第 5 条）。
9. **四检查点分开验收**：真实 OUT 提交成功 → 主机写完成 → 设备收到完成事件 → IN 应答（审阅二轮第 6 条；v18 措辞收窄的落实）。
10. **缓冲分配失败归因**：start_ex 与两次 allocate_transfer_buffer 拆开判错、失败路释放（P2-5）。
11. USB 诊断与 300 s 显示实验**分轮**（审阅 §八-3：USB 诊断用短会话，长驻留显示实验单独解释；F6 触发前的录屏与日志算部分证据，不据以判显示路线失败）。

**判决表**（审阅 §四-实验1）照录执行：真实配置到达+speed 有效+walk 明确失败 → H1↑；配置时 Usbfn speed=0 → H2↑；上层 speed=0+Unknown USB Speed → H3↑；已配置但从未留有效 OUT 接收 → 先修接收生命周期；GCTL bit11 present 前仍 1 → 先修复位流程；设备侧推进但主机所有权切换后失效 → 主机/usbipd 路上升。

## 8. 判定（对照 f13 §B.6 验收阶梯）

- **A 级（录屏帧含锁屏/主屏 + SpringBoard/backboardd 各 exec 一次）：未达成**——录像未提取（serving 窗未开）；屏摄目视旁证不可用（错误墙，无 iOS 画面——但注意：该屏打是 loader 相位的 USB 错误码，**不是内核会话的画面**，两者不可混读）。
- **B/C 级**：待 logdump 判读补齐（swap/CA 行计数 vs b25 基线、三窗 PID、crash 串、recording 行、cmdline 实印 598/607 验收）。[logdump 拉取后补]
- **出画判定：未完成**。屏录链路（内核侧）逐循环武装、缓冲逐循环重置（每循环重新 280 s 武装），提取面阻塞已从"未知"收敛为"loader 相位 USB serving"（Wave 22-24 同一根），与显示栈本身无涉——按 f13 §C.2 的耦合修正表述。

## 9. 红线执行与预算

- 刷写：Round 1 = 本子代理（v19，Boot #37，预算 1/2）；v19b 上机 = 协调方（预算 2/2 用毕）。**本子代理此后零刷写**，后续全部零刷写（提取尝试/logdump/报告/Exp-1 施工单）。
- 只碰 boot_b ✓（flash 目标唯一；userdata/darwin/GPT 未触碰）；FD `8924cb67`/shim `108ce972` 未重建 ✓；Windows device-layer 与 wave23-scripts/ 只新增 ✓；loader.c 补丁有 WSL `~/loader.c.v18bak` 备份、未动 git 状态 ✓；禁 git reset/checkout/stash/clean ✓。
- 网络：代理 7897 未用（全部本地证据）；WSL fastboot 全程 `sudo -n`（root 红线，首版脚本踩坑一次已修）。
- git add 不 commit ✓（主代理统一提交）。

## 10. 移交清单（给主代理）

1. **Wave 24**：§7 Exp-1 终稿施工单（一轮诊断刷写 + 判决表）；预算与轮次由主代理批。
2. **v19b 仍在机**：其循环继续重置屏录缓冲——若 Exp-1 前需再尝试零刷写提取，v2.1 采样器（fetch23.log）继续守 Windows 总线，但按审阅边界，v19b 的 un-armed 观测不作为证据。
3. **logdump**：auto-logdump-23.sh 已在后台守（Android 一回总线即拉 `logdump-v19.bin` + keylines，含 recording/swap/三窗/crash/loader.efi size 0x12f00=v19b 验明正身 token）；`fetch-recording-23.py` v2.1 继续守提取。
4. **用户侧**：usbipd 残留 Shared (forced) 绑定仍在 busid 2-2（WinUSB→VBoxUSB footgun，STATUS 既有记录）；管理员清理待用户方便。
