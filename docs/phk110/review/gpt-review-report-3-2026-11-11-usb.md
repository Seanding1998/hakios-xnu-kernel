# 外部评审报告三 · USB 专项（2026-11-11）

审阅日期：2026-11-11（北京时间）。范围：阶段 38 loader 七个修改块、vendor FD 方案、SETUP_PENDING 墙行、A1/A2/A3 与 DWC3 生命周期认知。按导读逐项检查，**只新增本报告，没有修改源码、构建镜像或操作手机**。

## 结论与证据边界

**本轮结论：不接受“USB 对自愈已完成”或“loader 已实现 FD 层最小等效”的表述。** OUT 提交退避和提交失败路径补查服务窗确实修中了两处问题；IN 请求归属、直接拒绝限流、半启动残留检测仍有可达缺陷。65/65 是工件与标记检查，不能证明这些状态转换正确。

**FD 全量重编不是视觉限频的必要条件。** 仓内 loader 已有 `mirror_install → mirror_shim_write` 的运行时写回调切口，可以在 FD 不变的条件下治理三型墙行。但这个旧切口的写回调 ABI 有错误，必须先修正并验证。把 vendor 端点状态机改成 Samsung 版行为的“少量字节手术”，在本项目当前证据与回滚约束下不可作为可交付修复；具体替代路线和工作量见后文。

严重性定义：P0＝阻断本阶段“修复完成/自愈成立”的结论，或存在冻结、请求归属错误；P1＝会漏治、误治或导致验收失真，必须补齐；P2＝机制解释、边界和记账需要纠正。P0 不表示已经在本次真机上目击了每一条故障。

| 问题 | 审阅判断 |
|---|---|
| Q1 七 hunk | 两处方向正确，单飞布尔量没有完成请求隔离；IN 门漏掉直接提交失败；重建检测同时存在漏诊和误诊。不能整体通过。 |
| Q2 FD/字节手术 | 定点消音在技术上可做，但不是带计数的限频，更不恢复端点。完整状态机改写不适合当前约束。首选修正现有 loader 写回调后限频，保留 FD 原字节。 |
| Q3 第三型墙行 | EP0 旧控制传输遇到新 SETUP 的抢占/快进处理；不是 bulk 环满的另一种编号，也不能据此断定全局事件队列损坏。现有提交门不能覆盖它。 |
| Q4 验收 | 必须增加取消尾声乱序、纯 0xC、历史错误后的健康恢复、无新 OUT 的读者恢复、无主机到期退出、三型墙行总输出预算和版本绑定。A2 的打印链不是自愈证据。 |
| Q5 生命周期 | 端点已配置、活动传输、TRB/URB 所有权、软件完成通知、总线配置代际是不同层。END_TRANSFER 不等于拆除端点，也不自动证明 loader 已收干净尾声；start_ex 不是端点对原子重建。 |

本报告使用以下冻结点；行号均指实际读取的 WSL 源码，不指 Windows 仓的旧 upstream 镜像：

| 对象 | 路径与校验值 |
|---|---|
| 主仓 HEAD | `466c0e2b3b6380b65ad3145df9d43fbab6f19731`，主仓与 WSL 树原本都有其他工作中的修改 |
| 当前 loader 源码 | `/home/cyrux/hakios/kernel/xnuloader/loader.c`；SHA256 `facebefbc5d3aff505b35a7ef2156ec2135ff199e17dd70289f8dfcbac6f9ae7` |
| 改前备份 | 同目录 `loader.c.v37-orig`；SHA256 `3ac1274089ce9e5e694e944c794f26bfdac5b42c549154cc65a40e4365bb9eda` |
| 已有 loader.efi | 同目录；SHA256 `3f595c52c4f13557706cc0121bd0a35387a891fab3b34acc0861cc29eb64a7ab`，本轮没有重编 |
| UsbFn blob | `/home/cyrux/hakios/uefi-udon/Binaries/udon/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.efi`；98304 B；SHA256 `9785ccf2894b46cd67d3f134c9c234af4fd8dcb6799bcbcadb6ca267d195f26f` |
| UsbDevice blob | 相邻 `UsbDeviceDxe/UsbDeviceDxe.efi`；69632 B；SHA256 `5694c0e42eac9f6657aed0c107c7647d73b4b3bf9a1a9217c570e5f6fecefd16` |
| 本轮采样的 v34 镜像 | `device-layer/udon-hakios-grafted-v34.img`；201326592 B；实算 SHA256 `03d424016d3a50933c9abd3b41b6820f204c370b3ae888530edcc6dcc7d7c766` |
| 导读指定回滚 v33 | `device-layer/udon-hakios-grafted-v33.img`；201326592 B；实算 SHA256 `6d5efeb52acbcdb41b80a250743e366fbd97f66691ff0ba66c4a0c6cf3785495` |

后文 `xnuloader/*` 的源码根为 `/home/cyrux/hakios/kernel/`；`Silicon/*` 的根为 `/home/cyrux/hakios/uefi-udon/`。blob 地址均为 radare2 的静态 VA，本次两个 PE 的 ImageBase 均为 `0x10000`，不是运行时加载绝对地址。涉及 `.text` 的下列地址，文件偏移＝VA−`0x10000`；正式补丁仍须按 PE 节表转换，不能把这个等式推广到任意 PE。

导读“未真机验证”已落后于并行流水：`wave38-scripts/progress.log` 的 phase 7 记载另一执行方 19:51:34—19:52:03 刷入上述 v34；phase 8 记载 SSH 成功；phase 9 又开始把 GL ramdisk 装入同名 v34。本报告不接管该执行过程。**后续同名 v34 若换包，不能继承这里采样镜像的哈希或验收归属。**

## P0：必须先处理的缺陷

### P0-1：`usb_in_expect` 只能表示“现在有人等”，不能证明完成事件属于这一条请求

**证据：** `xnuloader/loader.c:4331–4338、4352–4388`（`usb_pump`），`:4864–4874`（`usb_wait`），`:4938–4980`（`usb_tx`）；`xnuloader/efi.h:254–256` 的完成通知还带 `data_buffer`，目前没有使用。

七 hunk 的关键假设是：放弃 A 后把 `usb_in_expect` 清零，则 A 的尾声一定被吞掉。代码没有保证尾声在下一次置一之前到达：

1. A 等待超时，`:4966` 清零，`:4979` 调 abort，随即返回；abort 返回码没有检查，也没有完成归属隔离。
2. B 在下一次 `usb_tx` 提交，`:4964` 又将同一个布尔量置一。
3. 此后才由 pump 取到 A 的 Cancelled/CompleteOK。`:4376` 发现标记为一，把它交给 B。
4. 旧 Cancelled 导致 B 被误取消；旧 OK 则使 B 被误报成功，并在 `:4972–4974` 清掉健康判断台账，B 自己可能仍在控制器中。

另有不依赖晚取消的路径：同一次 pump 先拿到 OK、再拿到 Disconnected，`usb_wait` 在 `:4866` 优先按断线返回，`usb_done_in.live` 没被消费；下一请求不清槽就可能取走这份旧 OK。Connected 分支在等待期间无条件清 `usb_in_expect`，也会把随后到达的当前正常完成判成 stray。Connected 事件本身没有请求 ID，不能当成“全部旧请求及通知已经退役”的证明。

本轮用真实函数加替身协议复现了上述晚 Cancelled、晚 OK、Connected→OK、OK→Disconnected 四种顺序。其中新请求仅发 5 B，却返回旧请求的 17 B，并把 `usb_in_ok` 加一。**这是事件顺序竞态，不需要假设两个 C 线程同时执行。**

**修正要求：** 把请求管理改为至少“空闲→已提交→取消中→已确认退役”的状态机；取消中禁止新提交和复用该 DMA 缓冲区；检查 abort 结果。匹配明确的端点、缓冲区和配置代际，旧 done 槽随退役处理。这里没有协议级 request cookie，不能只加一个本地 generation 计数就宣称完成匹配；同一指针反复使用仍然分不出 A/B。须证明 vendor 已终止硬件访问且旧软件通知已收束，再开放新请求；不能仅依靠一次空 pump 或固定等几毫秒。收束超时要走有界故障退出。合法的新请求短传输也必须由上层按预期长度判断，不能用 `r >= 0` 代表整段已交付。

### P0-2：IN 直接提交失败完全绕开新门，已经满环/未配置时可能永远不 Engage

**证据：** `xnuloader/loader.c:4933–4963`（`usb_tx` 的 send-error 分支），`:4980–4997`（仅 wait 失败才递增 `usb_in_stale`）。

`gated` 只来自“此前已成功入队、但等待失败”的次数。若 `USB->send(IN)` 从第一下就返回错误，`usb_in_stale` 保持零，失败分支既不计连续错误，也不设置下一拍。因此每条命令乃至一条 `upload` 的多个应答仍可继续撞 vendor 打印点。

隔离测试连续调用 1000 次、每次让 IN 提交直接拒绝，结果是 **1000 次真实 send、stale=0、gate_next=0**。这条路径覆盖“进入本代码前已环满”和“IN 未配置”等形态，正是需要止血的情形。OUT 门并不能替 IN 门限流。

**修正要求：** 将直接提交失败纳入独立的失败计数与退避，保留错误类型；按一次故障周期统一限制尝试。不要把“入队失败”“等待超时”“断线”“Cancelled”全写成“读者没有读”。A1 反证也必须允许“新门本身漏覆盖”这一解释，不能照 `docs/waves/wave38-usb-selfheal.md:90` 一见 Engage 缺席就判定有第三条提交路径。

### P0-3：`usb_pair_rebuild` 对最典型的纯 0xC 半启动残留可能完全不可达，“双半确认”不成立

**证据：** `xnuloader/loader.c:5420–5421` 的必要条件，`:4980` 的 stale 唯一递增位置，`:5458–5462` 的调用入口；改前历史见 `docs/waves/wave28-var-persistence.md:44–52`。

纯故障状态可以是：服务窗开始时 `usb_in_stale=0`，两个 bulk 都已经未配置，OUT 每次提交都拒绝。因为收不到命令，根本不会产生三条成功入队后未读的 IN 应答；重建检测永久被 `<3` 拦住。即使是“一条未读应答之后 bulk 对被拆除”，剩余两条历史也不一定有机会出现。隔离测试确认了 stale=0、OUT 有拒绝码、无接收站立时，重建次数为零。

反方向也会误诊：`usb_arm_code` 是“历史最后错误”，`usb_gate_reset` 明确保留它（`:4248–4252`）；`usb_rx` 成功不清它、不更新当前 OUT 健康证据（`:4913–4920`）。三个历史 IN 失败加一个很早的 OUT 拒绝，不等于此刻两边都死。`usb_rx_queued` 对同步接收路径也不是可靠的“硬件无接收”标记，详见 P1-2。隔离测试在只保留旧错误码的条件下就触发了重建。

**修正要求：** 检测使用同一代际内、带时间戳的“最新进展/失败”，而不是累计台账作布尔真值。允许配置丢失/持续 OUT 拒绝在没有三条 IN 历史时进入有界恢复；端点未配置是配置失败证据，不必再通过提交三条不可能的 IN 请求来证明。为 host 刚插入、SET_CONFIG 尚未完成保留宽限期，以真实配置状态与最新成功读写否决误重建。若拿不到可信的 vendor 状态，选择服务窗内到期重启这条可验证的降级路线，**不要把不完备的启发式称为“双半确认”**。`run_active` 硬闸应保留。

### P0-4：已有 vendor 日志 hook 的 ABI 写成了三参数；在真正挂接成功时，自检调用有冻结风险（旧缺陷）

**证据链：**

- `xnuloader/loader.c:364–375` 把 writer 定义为 `(void *dev, const char *buf, uint64_t len)`；`:428–430` 自检也传三个参数。v37 备份有完全相同代码，**不是七 hunk 新引入**。
- `Silicon/Qualcomm/QcomPkg/Library/PlatformPeiLib/ShimLibraries/EFISerialPort.h:27–32、104–113` 的 `EFI_SIO_WRITE` 实际是两参数 `(Buffer, NumberOfBytes)`。
- `…/PlatformPeiLib/ShimLoader.c:28–37` 把 `SioLib.Write` 接到 `SerialPortWrite`；`Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib/FrameBufferSerialPortLib.c:298–300` 也是两参数。
- 实际 UsbFn blob 的 `0x1f288–0x1f2a0` 从表 `+0x10` 取 writer，恢复 `x0=Buffer、x1=Length` 后 `br x2`；UsbDevice blob 的 `0x19040–0x19058` 相同。这不是仅拿头文件猜 ABI。

正常 vendor 调用进入当前 wrapper 后，形参会错位：`dev` 实为 Buffer，`buf` 实为 Length，第三形参不是合法长度；镜面捕获条件不可信。原样转发可能碰巧保住头两个寄存器，**不等于 wrapper 正确**。自检则更危险：把 `dev` 接口表当 Buffer，把字符串地址当 NumberOfBytes，原 framebuffer writer 可能执行极长的读写循环或异常。

当前真机是否走到了这个错误自检，不在本轮证据内；hook 找不到门时没有该执行路径，不能拿“曾经启动成功”反证 ABI 正确。

**修正要求：** 先改成准确的两参数、字节数返回值约定，自检用真实文本 Buffer/Length；再以替身 writer 断言转发和返回值，然后验证真日志进入镜面。HOB 遍历还须修正 `loader.c:403` 对所有 HOB 都要求 `hlen>=0x18` 的判断：通用 HOB 头只有 8 B，存在合法短 HOB，只有读 GUID 扩展及数据时才要求相应长度。增加 PHIT 结束地址边界，不能一边修查找一边触发错误 ABI 自检。此项是后文“无需 FD 改写”路线的先决条件。

## P1：恢复实现、可观测性与验收缺口

### P1-1：重建没有形成事务，失败后仍继续调用 USB，成功也只证明 start_ex 返回

**证据：** `xnuloader/loader.c:5430–5445`（`usb_pair_rebuild`），`:4624–4650`（`usb_start_attempt`），`:5451–5471`（循环）。

两次 abort 结果全被丢弃；软件 done 槽没有清理/隔离；旧 RX/TX 分配未处理，`usb_start_attempt` 又覆盖全局指针申请两份 1 MiB 缓冲区。两次成功重建可额外遗失 4 MiB 分配，且旧事件可能仍指向旧缓冲区。这里应先保留旧指针，在已确认停止 DMA 后按 vendor 分配契约释放或明确复用；不能直接加 free 而造成仍在 DMA 的内存被释放。

重建失败将 `usb_ready=0`，但 `usb_command_loop` 没有再次检查 ready，下一轮照样 `usb_rx`、失败后又泵事件。部分重置后的控制器是否可用并未确认。`usb_start_attempt` 成功后的那句 rebuild-in 也没有等待新的 SET_CONFIG、bulk 提交或命令往返，不能是 A2 完成标记。

它与旧重掷路径也不相同：旧路径 `:4802–4807` 有 kick 后的 pumped settle，新增路径 `:5437–5440` 直接 signal→start。不能借旧路径成功记录替新时序背书。另外 `usb_pair_rebuilds` 是全局累计，不是自动逐窗复位；达到两次只会禁止后续重建，源码不会按文档说法自动把 ready 置零。

**建议：** 以恢复状态机管理 quiesce、取消、停栈、缓冲区、台账和重新枚举；每一步有失败结果与时限。恢复失败后进入明确的安静退出/重启等待态，不再调用未确认有效的 USB 入口。先查服务窗到期再开始新重建。启动返回之后继续泵 EP0，以新的配置与真实往返另记“恢复成功”。

### P1-2：OUT 也缺请求所有权，`!usb_rx_queued` 不是“控制器里没有接收”（旧缺陷仍影响新检测）

**证据：** `xnuloader/loader.c:4905–4920`，`:4877–4893`，`:4356–4362`，`:5379–5393`。

`usb_rx` 在接管站立接收时，等待尚未开始就把 queued 清零；自己提交成功时根本不将其置一。除 `usb_data_timeout` 分支外，会话 3 s 界、服务窗界和断线退出没有统一退役 OUT。隔离测试两次调用 `usb_rx` 均超时，得到 send=2、abort=0。下一提交可能与上一请求共用同一个 buffer，违反 vendor 头文件的同端点前一传输完成前不得再次 Send 的约定（`EFIUsbDevice.h:150–157`）。

另一个已有顺序问题是 `usb_poll_command` 收到完成后先 re-arm，再复制旧命令缓冲区（`:5379–5392`）；硬件可以在软件处理上一命令前写下一笔。同样不能只把 gen 打到日志上就认为有请求隔离。

**建议：** 将命令接收、数据接收和同步 wait 纳入同一个 OUT 生命周期；先消费完成及复制数据，再复用 buffer 或 re-arm。正常空闲 OUT 站立无需为了“没有包”反复取消，但阶段切换、超时及重建必须知道是哪一笔仍在挂。

### P1-3：当前 sampler 把协议表地址当端点状态，不能支撑生命周期判决（旧偏移错误）

**证据：** `xnuloader/loader.c:4277–4292`；实际 UsbFn blob `0x15798` 的 `add x23,x0,#0x1f0`，`:0x15814–0x15828` 把此上下文传给 DwcPrepareURB；DwcPrepareURB `0x19548、0x19580–0x19588` 再按 phys×0x20 与 state+0x18 取值。与 `docs/research/f12-ep2-not-configured.md:32、41` 自己的伪代码亦可交叉核对。

签名通过只能证明 `inst=usb_fn-8` 是 UsbFn 实例，不能把 `inst` 当 DWC 上下文。采样缺了 **`+0x1f0`**：

| 当前采样 | 实际所处位置 | 按本版 blob 计算的正确位置 |
|---|---|---|
| `inst+0x58`，打印 phys[2] state | Transfer 函数指针低 32 位；vtable 装配 `0x11650–0x11654` 可证 | `inst+0x1f0+2*0x20+0x18 = inst+0x248` |
| `inst+0x78`，打印 phys[3] state | StopController 函数指针低 32 位；装配 `0x11674–0x1167c` 可证 | `inst+0x268` |
| `inst+0x70`，打印 phys[2] maxpkt | 也在协议函数表区 | 必须从 DWC 上下文及相应字段重新推导，不能继续用现值 |

`inst+0x184` 的 speed 字段是另一条独立推导，不随上述错误一并否定；MMIO 的 DALEPENA 也仍有独立参考价值。修正采样要绑定完整 blob SHA、校验内存边界和字段语义。已配置状态可能不止值 1，不能把所有非 1 都判未配置。此前这三项错误读数不能用于证明“拆除时 phys[2]/phys[3] 变成零”。

### P1-4：门内静默丢回复且调用者继续推进，健康读者恢复后仍可能协议失步

**证据：** `xnuloader/loader.c:4942–4944`；`:5003–5023`（两个回复 helper 忽略返回），`:5175–5195`（DATA 未成功也开始收数据），`:5263–5268`（net upload 失败仍清 `net_stage_len` 并发 OKAY）。

“每拍探测”目前只表示下次 `usb_tx` 有资格提交，**没有定时器主动补发被丢的那份应答**。fastboot 客户端通常等本条回复后才发下一命令；只恢复 IN 读取、没有新 OUT，就未必有新的探测。客户端等待 DATA、设备却已进入数据接收的失步也未被门处理覆盖。把一次 `r>=0` 当整块成功则还会掩盖短传输。

**建议：** 回复失败逐层传播，停止当前命令阶段；明确选择“保留这一条待发回复、按期重试”或“结束该协议会话，要求 host 重开并重试整条命令”。数据没有确认交付前不清 stage。测试读者暂停后恢复、DATA/正文/最终 OKAY 三个阶段分别失败，以及无新 OUT 的恢复。

### P1-5：A1 的“每 ≥2 s 至多一行带计数”目前没有实现，第三型墙也不受两个提交门约束

**证据：** `xnuloader/loader.c:4230–4243` 首个 OUT 失败退避是 1 s；一次拒绝调用内部仍可能打印整组 vendor 行；`:4951–4960` 限的是提交次数；`mirror_shim_write:375` 无条件原样转发。设计与验收原文见 `docs/waves/wave38-usb-selfheal.md:72、87、90`。

提交限流会把无限热旋变成稀疏的多行突发，这是有价值的止血，但不能等同每两秒一行。IN/OUT 两套独立拍还可能重叠；loader 自己的计数行不自动合并 vendor 的数行。第三型 SETUP_PENDING 是 pump 内 EP0 工作产生的日志，纵使 bulk 一个也不提交，host 反复控制探测仍可触发。

§5.1 的“连续同前缀 >3 才抑制、前缀变化就放行”也会被四行 A→B→C→D→A 的墙绕过；`SerialPortWrite` 收到的是格式化字节，通常没有原始 `%` 占位符。按调用块直接等同一整行也不可靠。

**建议：** 修正 P0-4 后，在现有 loader 写门实现跨调用的有界行组装、按错误族记数，并对三型 USB 墙行设一个共享显示预算。若 A1 是严格要求，稳定期最多每 2 s 一条聚合摘要，不能每类各一条。详细首因及抑制总数进入独立有界记录；显示过滤后返回已消费字节数，避免调用者因短写重试。不得在 writer 中睡 2 s，亦不得通过会递归进入同一 writer 的 print 输出摘要。未知错误/断言的呈现策略要明确测试，不能用全局 DEBUG_ERROR 关闭冒充限频。

### P1-6：现有 A3 功能记录值得保留，但版本元数据失真；A2 的“跨代际重新枚举”不是本函数自愈证据

**证据：** `wave27-scripts/timed-ssh-v27.py:270–292`；`wave27-scripts/verdict27-w38-ssh1.txt:6`；`wave38-scripts/progress.log` phase 8/9；`wave38-scripts/verify-udon-hakios-wave38.py:159–175`。

本轮读取到 `w38-ssh1` 的三次独立命令 rc=0、Darwin 输出、262144/262144 B 计数传输，以及退出后的 `OKAYxnuloader`；这是功能正向观测。可是判定器 `:292` 硬写“boot_b=v23、9e0609fb、1800 s”，与实际试验的 v34/600 s 不一致。应根据真实刷写记录、包哈希、boot/session ID 修复归属；不必为改一行元数据否认已有会话输出，也不能保留错误镜像栏就宣布新件完整验收。

传输代码 `:270` 后的判据为 `wc -c` 字节数一致，不是内容哈希，报告应如实称“长度验证”。建议另加双向内容校验。A3 最小 HIT 也不能替代 verdict27 已定义的三连接、传输、退出后管理活性完整语义。

phase 8 的 dead devnode→新代际枚举，可能是重启或 host guardian 干预后的新一轮，也可能是栈重建；没有同一 boot 内的触发、执行、配置和往返链，不能归因给 `usb_pair_rebuild`。§6 的四句日志主要是尝试与返回值，不是效果证明。65/65 中新增三项只是检查字符串存在，`:172–175` 也明确说明无打印 hunk 没有运行时语义检查。

**建议：** 固定每次试验的完整 graft/payload/loader/kernel/ramdisk 哈希、host 工具版本、boot ID、相位和干预事件。流水已记录 GL ramdisk 再封包，后续新 SHA 必须有自己的归属和必要回归，文件名 v34 相同不构成继承依据。

## 七个 hunk 的逐块判定（Q1）

| hunk | 结论 | 当前源码证据与需要补齐之处 |
|---|---|---|
| 1 IN 台账 | 部分正确，不能构成单飞证明 | `loader.c:4177–4183` 的 bool 只防同步重入；没有取消中状态、请求身份、预期长度和代际绑定，见 P0-1。 |
| 2 Connected 清台账 | 不通过 | `:4331–4338` 在 wait 中清 expect 会吞掉当前完成；Connected 也不证明“新 reader 已经开始取 bulk”。必须按真实配置转换退役旧代并让在等者明确失败。 |
| 3 吞 stray | 不通过 | `:4376–4383` 仅在没有新 waiter 时有效；一旦 B 已提交，A 尾声仍落进 B。还应只接收明确的 `USB_EP_IN`，不把所有非 OUT 通知都视为 IN。 |
| 4 IN 10 s 界 | 有界等待方向正确，判词与覆盖不准确 | `:4877–4885` 会话相先由 3 s 返回，10 s 主要约束服务窗/启动服务阶段；不是“任意相位三次都是 3×10 s”。VM 暂停、USBIP 抖动、用户慢读、大块上传都可触界，超时不能证明 reader 永久死亡。 |
| 5 usb_rx 墙门 | 修正了提交拒绝热旋源，仍缺 OUT 生命周期 | `:4905–4920` 覆盖 direct-send 失败，但成功路径不复位当前健康台账、站立标记也不完整；限提交不等于限显示行。 |
| 6 usb_tx 重写 | 不通过 | `:4931–4999` 三个关键问题：直接拒绝不入门、abort 结果忽略、旧完成可污染新 wait；回复失败未上传到协议层。 |
| 7 重建与服务循环 | 局部修正成立，整体自愈不通过 | `:5413–5482` 在 n<=0 路径补查服务窗、加 pumped 等待可消除失败热旋；但重建条件漏诊/误诊、重建非事务、失败后仍用 USB。不能称 FD 层等效。 |

`usb_in_gate_backoff` 在正常成功及 Connected 时没有清零（`:4336–4338、4972–4974`），下一轮故障会继承旧退避；累计计数与本轮故障计数应分开。若这属于有意保守策略，必须把重新接线后的最坏恢复等待写进验收，而不是继续声称每次从 1 s 起步。

## FD 层路线裁决与工作量（Q2）

### 首选：沿用并修好现有 loader 的共享 writer hook，FD 保持不变

这不是尚未发现的理论注入点，**当前源码已经安装了它**（`loader.c:379–430`，`efi_main:5736` 在 USB bring-up 前调用）。完整链路为：

```text
UsbFn DebugPrint @0x1c044
  → 已格式化字节的输出 @0x1f258
  → 从 Shim HOB 得到 LoadLib("SerialPort Lib", 0, &SioLib)
  → 每次输出从 SioLib+0x10 再取 Write
  → loader 安装的 wrapper
  → 按显示预算决定是否调用原来的两参数 SerialPortWrite
```

UsbFn `0x26048` 处 GUID 字节实读为 `BEDAEABC-5E70-4D66-9733-213D072B9D04`，与 `QcomPkg.dec:13`、`PlatformPei.c:96–97` 和 loader 完全匹配。`ShimLoader.c:56–77` 返回共享接口表地址，blob 缓存的是接口表指针、每次写再取成员，因此晚于驱动启动替换 Write 仍有静态可行性。UsbDevice 的 `0x18fd0/0x19010` 有相同的运行时查表链。

实施顺序：修正两参数 ABI及 HOB 遍历→验证捕获与原样透传→实现有界聚合与严格显示预算→覆盖 SETUP_PENDING 在内的三型墙→记录 hook 失配及安全退化。hook 的内存可写性、实机上的表版本、重入/TPL、退出或重启前的有效期都要验证，不能声称“零风险”。它只覆盖安装之后经这个门输出的日志，不覆盖更早的固件阶段及直接链接的其他显示路径；这恰好与本轮 loader/会话服务窗范围相符。

这里的 Shim HOB/`ShimLoader.c` 与 graft 的 240 B **BootShim.S 拷贝跳板不是同一个 shim**。“BootShim 没有打印路径”不能推出“loader 无法控制 vendor 打印”。

**工程量估计：** 熟悉该仓的一名工程师约 1—2 人日完成 ABI/HOB/聚合器与离线测试，另留 1 人日做现有 boot_b 试验流程中的三型屏幕与控制面验证。修复 USB 请求生命周期、错误门和恢复状态机约另需 2—4 人日，真机故障注入/回归再约 1—2 人日。估计不含等待设备可用、硬件根因研究或用户物理干预时间；不是交付承诺。

### 备选：源码重编/定向替换有关固件组件

`FrameBufferSerialPortLib.inf` 的 `MODULE_TYPE=BASE`、`LIBRARY_CLASS=SerialPortLib` 说明它是静态库，不是一份可直接替换的独立 DXE PE。`SiliciumPkg.dsc.inc:161–166` 映射了库，`PlatformPeiLib.inf` 又消费该库并提供 `SioLib`。要修 FD 侧源码，先由 map/构建依赖定位提供共享 writer 的实际镜像，重编受影响镜像，再重新封装对应 FV/FD；不能笼统说“单模块 .c 改了，替一份同名 efi 即可”。

FD SHA 改变是预期的版本迁移与验像成本，**不是技术上无法修改的理由**。可在独立构建目录重编，比较每个 FFS/PE、GUID、DEPEX、FV 布局，要求允许清单以外的组件不漂移；不满足这个边界就退回首选路线。保留 FD 旧件和 v33 原像，不在并行执行方的已钉位构建目录直接重编。

**工程量估计：** 构建/容器依赖梳理与确定性差异审计约 2—4 人日，回归另计。因静态库可能进入 SEC/其他共享组件，它不应被描述为“零风险纯增益”。

### 字节手术的可做与不可做

只针对上述完整 SHA 的 UsbFn blob，本轮直接复核了这些锚点：

| 目的 | 可核对的静态锚点 | 裁决 |
|---|---|---|
| 识别未配置 | `0x19584` 读 state、`0x19588 cbz → 0x195ec`，`0x1960c` 调 DebugPrint，`0x19610–0x19618` 形成 0x8000000C | 可以识别并仅改诊断调用；**不得绕过 state 检查或把返回值改成功**。 |
| 识别环满 | 字符串 VA `0x22fe6`（文件 `0x12fe6`）；`0x196c8–0x196d8` 检查 ring 数量/指针；`0x196fc` 调 DebugPrint，`0x19700–0x1970c` 形成 0x8000000B | 能确认至少这条 0xB 是 TRB ring full；消音不会释放资源。 |
| 识别 SETUP_PENDING | 字符串 VA `0x23397`（文件 `0x13397`）；`0x1a850–0x1a858` 检查 TRB 状态，`0x1a880` 保存 pending 标志，`0x1a884` 调 DebugPrint | 定点消音只能改打印调用，不能跳过 pending 标志和后续 ring 同步。 |
| 改 bulk 配置行为 | SET_CONFIG `0x1672c` 分支；配置 walk `0x16960`；速度表 `0x20930` | 这些是认识路径的入口，**不是已找到安全补丁位**。涉及资源、TRB、FIFO、DALEPENA、状态机及重复配置。 |

如果确需定点诊断消音，可以对精确的 DebugPrint `BL` 做等长替换并保留失败返回及所有状态操作；上表不是已经产出的补丁。本轮没有写任何固件 patch。它仍有三项限制：多层 wrapper 继续打印其他行；没有时间戳/抑制计数；若清掉唯一首因将损害下一轮根因定位。因此它不能单独满足 A1，也不是自愈方案。

实现带时间/计数的 binary limiter 则需要有证明的代码及状态存储、AArch64 ABI、相对分支/重定位与执行缓存处理；本轮没有验证可用 code cave，不能声称只 NOP 几条就能做。直接改 `SerialPortWrite` 机器码也不能绕开定位其**真正提供者**、多份静态库副本和版本适配的问题。

正式的最小 FD 替换必须：按 SHA 和 PE 节表定位→核验旧指令、xref 与控制流→只允许清单内字节变化→重算 FFS/FV 所需校验并处理压缩容器→提取重封装后的 PE 再对拍→重做 graft/布局/哈希检查。一个字节变化也会改变整个 FD SHA，验像迁移无法通过“改得少”免除。PE 的签名字段状态也不能代表整个启动链所有认证策略已被证明无关。

**明确不接受的方案：**

- 把 `DwcPrepareURB` 的未配置分支抹掉、强写 state=1，或把 EFI_ERROR 改成功：会把没有准备好的 TRB/资源交给硬件。
- speed=0 就强制取 SS 列、统一 maxpacket=1024：HS bulk 是 512，未知速度应先查真实协商/ConnectDone 及描述符，不能伪装成 SS。Samsung 家族的能力上限策略需要其后续速度重配配套，不能单摘一行移植到 Qualcomm blob。
- 在任意 Transfer 失败中就重配整对端点：失败可能只是资源暂缺、控制阶段未完成、取消或 reset 竞态；另一个方向可以仍活着。
- 只在 start_ex 多装一次 bulk，却不处理 SET_CONFIG 再装：现有 DwcConfigureEP 对重复配置会拒绝（F12 §2，blob `0x18e78–0x18eac`）。

**完整 vendor 状态机 surgery 在当前约束下不可交付，不建议尝试刷机验证猜测。** 若未来专门立项，先补精确代际/寄存器/请求队列取证，证明是哪个配置转换失败，再做可离线验证的定点修改；无法形成这个证明时，走源码驱动替换或保留 loader 侧降级重启。定点消音约 1—2 人日加容器验证；完整状态机逆向与改写至少 2—4 人周起，替换为可维护驱动还涉及高通 PHY/时钟/事件/缓存集成，约数周以上。本轮信息不足以承诺“零变砖”；v33 回滚是必要的退路，不是任意固件改写无风险的保证。

## 第三型墙行：SETUP_PENDING fast-forward 的实际含义（Q3，P1）

本次不是只按字符串解释。实际 UsbFn blob 的 `DwcGetNextEvent` 所在函数 `0x1a4cc`，在 `0x1a844–0x1a858` 先限定控制端点路径，再读 TRB size 的高位状态；命中后输出该行并保留 pending 标记 `w22`（`0x1a880`）。标记参与随后完成长度/ring 同步计算（`0x1a91c–0x1a97c`）与完成/清理分支（`0x1a9a8–0x1aa08`）。**打印不是这个机制本身，抹掉打印时不能连标志或清理流程一起跳过。**

控制传输包含 SETUP、可选 DATA、STATUS。新的 SETUP 可以在旧 DATA/STATUS 尚未完成时到来，使旧控制事务被抢占；硬件以 SETUP_PENDING 状态告诉驱动同步旧 TRB、放弃旧阶段并处理最新控制事务。这里的 fast-forward 是端点传输/TRB 进度的同步处理，不能直接翻译成“把全局事件队列随便跳到后面”。Linux `dwc3_ep0_complete_data` 会把被新 SETUP 中断的请求以 `-ECONNRESET` 归还，`dwc3_ep0_complete_status` 会标记 pending 并重新准备 SETUP；这是独立开源实现的语义旁证，不能代替本版 Qualcomm 的每个实现细节。[Linux v6.12 ep0.c:859–954](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/ep0.c#L859-L954)

一条偶发记录与 host 重新枚举、重试控制请求相容，不足以证明物理链路坏了；连续大量出现则要检验：EP0 事件处理是否因 framebuffer 绘字/flush 被拖慢、host 是否反复超时重试、SETUP 是否及时被重新准备、reset/配置重放是否竞争。`FrameBufferSerialPortLib.c:314–334` 在关中断区域逐字绘制，换行还走 `:114–115` 的延迟；这条反馈链有源码依据，但**本轮未测其在实机上的耗时，不能写成已证根因**。

这个机制还影响新增 abort 的边界：Linux 说明收到但尚未 DMA 到内存的 SETUP 可能阻止任意端点 END_TRANSFER，驱动需先准备 SETUP TRB、延后停传输；同步死等取消会妨碍 EP0 继续前进。[Linux v6.12 gadget.c:3865–3929](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/gadget.c#L3865-L3929) 不能把 Linux 的处理直接套给 vendor，但足以否定“abort 只是无副作用排空，绝不会与 EP0 竞争”的前提。应把 SETUP_PENDING 与 abort 耗时/返回、后续控制应答一起记录。

## 生命周期认知修正（Q5，P2；涉及执行风险时按前述 P0/P1 处理）

1. **END_TRANSFER 合法用于取消自己当前在挂的 bulk 传输。** `EFIUsbDevice.h:172–186` 就提供这项操作；UsbDevice `0x11c60–0x11cb8` 拆分端点号/方向并调 UsbFn AbortTransfer，后者 `0x12bd8 → 0x15320 → 0x1a128` 进入取消实现。所以“未完成就不能 abort”是错的。问题是必须核验返回与资源/通知退役，不能忽略错误就继续。
2. **END_TRANSFER 通常结束活动传输资源，不等于取消端点配置。** 本版 vendor `0x1a288–0x1a2b4` 的取消收尾在相应条件下把 state 恢复为 1、资源索引设为 0xff 并清理 ring；这与“取消必然把 EP 表拆成零”相反。总线 reset、配置切换、StopController 的拆除是另一类转换，必须逐个取证。
3. **“TRB 排空”不是单一动作。** 硬件停止访问、transfer resource 结束、TRB 索引及 HWO、URB 链表归还、软件完成队列收束各有条件。Linux 在 END_TRANSFER 完成事件后才清 pending 并清理取消请求，说明不能以一个应用层 bool 代替这些关系。[Linux v6.12 gadget.c:3669–3711](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/gadget.c#L3669-L3711)
4. **新的 START_TRANSFER 不会补做端点配置。** 它需要已经配置的端点与合法 TRB/资源；取消干净后可在仍配置的端点上重启传输。若配置已经丢失，必须走配置路径，不能靠无限 send 恢复。
5. **start_ex 是控制器/软件栈级重启尝试，不是两条 END_TRANSFER 的等价封装。** UsbDevice `0x11d44` 先 StopController，随后重建描述符/状态并调用 ConfigureEnableEndpointsEx（F12 §3.1）；实际调用可能失败，成功也主要是 EP0/描述符准备，仍依赖后续事件泵和真实 SET_CONFIG。保留 `run_active` 硬闸是正确的；“服务窗没有任何活通道”则不是必然，管理传输也可能正在进行。
6. **SET_CONFIG replay 不是 loader 发出的直接硬件命令。** 它需要 host 真正重新枚举并发送请求、speed/接口表有效、DEPSTARTCFG 和每个端点的配置都成功；USBIP/Windows 的 `set_configuration(1): ok` 还可能只是驱动记账或同值快路径。必须结合设备侧事件/配置取证与实际 bulk 往返，不能以 host API 返回成功替代。
7. **0xB→0xC 的观察顺序应保留，因果强度须降级。** 本轮静态证明了 ring-full 可产生 0x8000000B、state==0 可产生 0x8000000C。它没有证明“IN 环满自动导致 OUT 注销”，更没有证明是哪次转换点把两个 state 清零。F12 `:23` 曾留开放的 0xB 微项，现在可补上这个具体产生点；不能反过来将所有 0xB 都当 URB 池耗尽。尤其现有 sampler 偏移错误，旧 state 解释必须重审。
8. **240 s 是无活动服务期限，不是固定总窗长。** `loader.c:5473–5474` 每次正长度 OUT 就刷新 mark；半死读者持续写命令时，也会延长窗口，即使没有成功读到回复。新增失败路径检查修复了“提交拒绝绕过窗限”，仍不能推出任意半启动残留一定在总计 240 s 内退出。验收须区分“距最后成功活动的空闲期限”和“绝对最长停留”，并记录最后一次刷新原因。

## 验收计划修订（Q4，P1）

保留 A1/A2/A3 和 /var 回归门，但把“效果”“机制”“无回归”分别验。一次顺风 SSH 成功，不能替故障注入后的恢复；没有出现故障，也不能通过 A2 的恢复分支。

| 验收项 | 必须补入的场景/测量 | 通过条件 |
|---|---|---|
| A1 三型墙总预算 | 会话、服务窗、重新枚举分别观察 ring-full、not-configured、SETUP_PENDING；含四行循环、分片写、IN/OUT 同时退避 | 有统一时间轴的屏摄/显示出口计数；稳定期任意相邻聚合墙行间隔 ≥2 s，含各类抑制计数。若要求零墙，明确记录观察覆盖与持续时间。不能只数 loader print。 |
| A1 首因与性能 | 显示过滤前保留首个配置/取消失败；统计 pump 最大间隙、abort 用时和 EP0 控制往返 | 无递归/阻塞式限频，首因可提取；限频后 EP0 仍持续应答。镜面 hook 失配必须显式报告，不能假装无日志就是无错误。 |
| A2 纯配置丢失 | 初始 stale=0 或 1、OUT 全拒，端点从未武装/会话末端配置丢失 | 能在规定时间内有界恢复或安静重启；不要求先凑三次 IN 未读。源码/隔离注入先行，真机禁止强写状态字制造故障。 |
| A2 读者消失与返回 | OUT 写正常、IN 不读；分别在 DATA、正文、OKAY 阶段停止；恢复时只恢复 IN 不发新 OUT | 同端点最多一个未退役请求；无资源持续增长；恢复有明确协议结果，数据没有未交付先丢弃。 |
| A2 事件交错 | Cancelled/旧 OK 晚于新提交；OK+Disconnected、Connected+OK 同泵；完成槽已有旧值；取消失败 | 完成只归属正确请求；旧代不能报新请求成功，取消失败不允许复用 DMA buffer。 |
| A2 不误杀 | 短暂 OUT 拒绝后恢复、历史 stale≥3、host 刚插入仍在配置、慢读超过边界后恢复 | 当前成功进展否决重建；健康会话中重建数为零；3 s/10 s 的策略与上层 timeout 相容，不误称永久死亡。 |
| A2 真恢复证据 | 同一 boot 内记录恢复原因、abort 返回、start_ex 结果、新配置、CP1、CP3 和 IN 回复；重建期间不能由另一个 host 工具干预 | 用随机 nonce 的 getvar/管理往返及后续数据校验确认；只有 CP1 或 rebuild-in 打印不通过。跨整机 reboot 的新会话单列“降级恢复”。 |
| A2 有界退出 | 无主机、只有 EP0 控制探测、持续 bulk 直接拒绝；第 1/2 次 start_ex 分别失败；接近窗限才触发恢复 | 到期不再开始新恢复；失败后不继续进失效 USB；观察到实际 boot ID/重启边界，无需三小时等待或物理键。明确空闲窗与绝对上限。 |
| A3 完整 SSH | verdict27 的三独立连接、不同 nonce、传输、干净退出和退出后管理活性；在故障恢复后再跑一遍 | HIT 只作最小门；完整语义逐项通过。保留当前长度验证，再增加双向内容 SHA 比对与门/stray 计数记录。 |
| /var 独立回归 | 新包 march→write→真实跨 boot→read，保留 BOOTPROOF、marker 243 B、blob 三方 SHA、VARFS | 不用同一会话假读；最终新 SHA 有自己的 /var 证据。某次 marker 正常不能证明 USB 自愈全部成立。 |
| 版本/回滚门 | 完整 SHA 与 boot/session ID；同名 v34 换 GL ramdisk；回滚镜像离线校验 | 只对确切包签发结果；回滚按导读用 v33 原样，避免沿用阶段日志旧 v27 表述。本轮不执行回滚。boot_a 禁刷与 boot_b 三门/OKAY 约束保持。 |

最小实施顺序建议：先通过 ABI/事件归属/门覆盖的离线测试，再封一份固定哈希包；先确认未注入故障时的 SSH 与 /var，再分别验证 A1 与 A2；最终再走一次恢复后的完整 SSH。失败路径也要记录“无恢复但安静按期退出”，不能为了 A2 打印好看而把它改记为自愈。

## 本轮已做的验证与未做的验证

- 在内存中解析 `wave38-scripts/patch-loader-v38.py` 的七个 `sub(old,new)`，逐块断言 old 唯一，应用到 v37 备份后与当前源码逐字一致；没有运行补丁脚本去写源文件。
- 对上述两个完整 SHA 的 vendor PE 做只读 AArch64 反汇编，复核打印、运行库、取消、TRB ring 与状态字段锚点；没有生成或应用 byte patch。
- 从当前源码抽取真实 `usb_wall_gate/usb_gate_reset`、`usb_pump`、`usb_wait`、`usb_rx`、`usb_tx`、`usb_pair_rebuild`，以假时钟和替身 USB/Boot Services 在临时隔离程序中编译执行。临时目录自动清理，没有调用 loader 构建链。

| 隔离用例 | 实际结果 |
|---|---|
| 1000 次 IN send 直接拒绝 | send=1000，stale=0，gate_next=0；限流缺口复现 |
| A 取消完成晚于 B 提交 | B 误收 A 的 Cancelled，又取消 B；stray=0 |
| A 的旧 OK 晚于 B 提交 | B 请求 5 B，返回旧 17 B；成功计数增加并清 stale |
| Connected 和当前 OK 同泵 | 当前 OK 被吞为 stray，wait 超时并 abort |
| 当前 OK 与 Disconnected 同泵 | done 槽残留，下次请求误收旧 17 B |
| stale=0、OUT 拒绝 | 重建调用数为零 |
| 历史 stale=3、旧 OUT 错误仍留存 | 未验证当前 OUT 即进入重建 |
| 两次 OUT 等待超时 | send=2，abort=0；OUT 挂起状态缺口复现 |
| run_active=1、其他条件满足 | 重建被硬闸阻止；正向验证成立 |

这些用例证明代码接受何种事件顺序及状态组合，**不证明真实 vendor 在每轮 boot 都会产生所有这些顺序，更不替代 DWC3 真机时序测试**。修复后的实现必须让这些反例不能破坏请求归属，并再验证真实取消事件/硬件退役契约。

外部语义核对只使用 Linux 官方源码 v6.12 的 `drivers/usb/dwc3/ep0.c` 与 `gadget.c`，经用户指定 Clash `127.0.0.1:7897` 代理读取；引用紧邻相应解释。对本项目行为的裁决仍以上述本地实际源码、blob 和工件为主。

没有重跑 `build.sh`，没有重建 FD/payload/graft，没有 adb、fastboot、usbipd、控制器 MMIO 或 WSL shutdown 操作。A1 的屏幕效果、A2 的同 boot 真恢复、最终新包的 /var 与镜像归属仍须由设备执行方按修订计划取证。本报告完成即止。
