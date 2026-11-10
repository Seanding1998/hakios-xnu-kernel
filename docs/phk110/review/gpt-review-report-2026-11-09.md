# HakiOS / PHK110 USB 核心审阅报告

**我的判断是，下一轮应先修正观测与事件消费方式，再用一次诊断刷写区分设备侧失败路径。现有证据支持继续使用 vendor 栈，但尚不足以把 fetch23 的稳定可打开窗口定性为“H1/H2 导致 bulk 始终未武装”。**

在限定只比较 H1、H2、H3，并且已经确认真实 SET_CONFIGURATION 到达设备、随后设备侧 OUT 提交仍返回未配置错误的条件下，我的暂定概率排序是 **H1 > H2 > H3**。当前材料不足以给出有意义的百分比。若把候选范围展开，**没有有效 OUT 接收请求、事件被错误消费、主机配置状态与设备内部状态脱节**，必须与 H1 同级优先排查。

本次全程只读，报告直接交付在聊天中。审阅依据包括导读、Wave 22、F12、F13、主机脚本、日志，以及 WSL 中的实际代码。外部源码核验通过 Clash `7897` 端口访问。

需要先固定版本边界。

- fetch23 对应的 **v19 初版保留 v18 loader**，其构建脚本明确携带 `553289a4…`，只修改 cmdline。
- 本次实际读取的 WSL `loader.c` 已包含 **v19b / Wave 23 Round 2** 改动，文件 SHA-256 为 `a53209dc1c2cdec5628b33b66d48b971bbd5be578e0cedb7a77e2edef0cee122`，前后读取一致。
- 以下对 v19b 的代码发现，不能直接当作早先 fetch23 会话的成因。外部 libusb、Linux、usbipd 源码用于核验语义，本次没有核验本机运行中的 DLL、驱动与这些上游版本完全一致。版本依据见构建脚本。[v19 构建脚本](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/make-payload-v19.sh:2)、[v19b 构建脚本](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/make-payload-v19b.sh:2)

---

## 一、根因排序与依据

### 1. fetch23 的事实强度需要下调一层

| 命题 | 本次审阅结论 |
|---|---|
| Windows 连续多次能够打开并 claim 设备 | **成立**。日志有连续成功记录 |
| 这些记录属于同一个始终未重建的 devnode、同一设备代际 | **证据不足**。缺少 instance ID、地址、设备代际关联记录 |
| 该窗口内真实重新发送了 SET_CONFIGURATION | **证据不足**。fetch23 没有对应调用结果行，更没有总线完成记录 |
| bulk-OUT 多次零字节超时 | **成立** |
| bulk-OUT 全部超时 | **存在反例线索**。日志中有一次 `oem recording did not stage: NONE b''` |
| 因而 bulk 端点始终未配置 | **推导不成立**。未提交接收、控制器停顿、接收状态失配等也能产生该主机观测 |

整份日志中，重复 `open+claim` 覆盖 **00:57:29 至 01:01:22**，超时记录延续到 01:01:30。00:57:49 的 `NONE` 行尤其需要保留。按现存脚本控制流，只有 `send()` 没有抛出 OUT 错误，才会进入 staging 应答判定。不过脚本在该时段之后修改过，因此这条应归为“需核对当时脚本版本的成功 OUT 线索”。它已经足以挑战“全超时”的概括。[fetch23 原始日志](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/fetch23.log:7)、[现存 send 与 staging 控制流](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/fetch-recording-23.py:119)

另一个重要限制是 **Windows WinUSB 后端的配置调用可能在本地完成**。我核对的 libusb v1.0.29 实现，在同配置号 SET_CONFIGURATION 请求上会走同步完成分支，未调用底层 `ControlTransfer`。因此 API 返回成功、活动配置描述符可读，都不能单独证明设备刚刚处理过一次新的 SET_CONFIGURATION。`open_and_claim()` 本身也只执行 open、读取活动配置、claim。[项目 open_and_claim](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave13-scripts/loader_talk.py:552)、[libusb WinUSB 配置请求处理](https://github.com/libusb/libusb/blob/v1.0.29/libusb/os/windows_winusb.c#L3014-L3031)

### 2. H1 / H2 / H3 的条件概率排序

**暂排 H1 > H2 > H3，H1 与 H2 的差距目前无法量化。**

| 排名 | 假设 | 支持与限制 | 足以显著改变判断的观测 |
|---|---|---|---|
| 1 | **H1，DEPSTARTCFG 或 walk 中段失败** | F12 已定位真实失败路径。若真实配置请求已处理、speed 有效、bulk 状态仍未建立，H1 最直接。当前缺同一会话的前导失败码 |
| 2 | **H2，UsbfnDwc speed 为 0，walk 取到 maxpkt=0** | 零列陷阱有指令级依据。但它还要求解释 ConnectDone 为何没有在配置请求前留下有效速度，或为何随后被清零 |
| 3 | **H3，UsbDeviceDxe Unknown USB Speed 导致 STALL** | 字符串及条件存在。如果同一代际 SET_CONFIGURATION 的状态阶段真实成功，H3 会显著下降。只有主机配置缓存时，H3 仍不能排除 |

H2 与 H3 还涉及**两个不同层的 speed 字段**。F12 给出的 UsbfnDwc 字段为 `+0x184`，UsbDeviceDxe 字段为 `+0x1f8`。读取其中一个，不能代替另一个。两层状态失配还可能让这些假设在同一启动中相继出现。[F12 武装链与速度表](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f12-ep2-not-configured.md:72)、[F12 H1–H3 与上层 speed 字段](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f12-ep2-not-configured.md:146)

### 3. 扩展候选后的排查顺序

针对“稳定可打开、bulk 零字节超时”的窗口，我会按以下顺序投入实验资源。这是**信息增益排序**，不是已证实的故障发生率。

1. **有效 OUT 接收请求是否存在，事件是否交给了正确消费者。** 端点配置完成、提交接收成功、收到完成事件、命令被执行，是四个不同检查点。
2. **H1。**
3. **H2，以及 vendor 两层状态失配。**
4. **H3。**
5. **主机驱动、usbipd 所有权切换、配置缓存等干扰。**

针对 `0000:0002` 的早期枚举失败，则应另排一张表。**未服务的展示窗口、控制器重初始化与再次展示的生命周期、固件异步回调**优先于 bulk walk。首次设备描述符阶段的失败，发生在 bulk 配置之前，不能直接由 H1–H3 解释。

### 4. Wave 22 首胜应保留，但验收措辞应更精确

`armed at generation 0, beat 1` 证明 **该次 OUT 零长度提交被接受**，结合 F12 的状态判据，这是有价值的设备侧进展。现有探针没有独立测试 IN，也没有等待真实数据完成，因此“bulk pair 已完成双向验证”超出了证据。主机成功写入也还需要与设备侧接收完成和命令应答关联。[v18 判别记录](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/logdump-v18.bin.keylines.txt:1)、[当前探针接受后立即 abort](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4303>)

---

## 二、§5-F 六个代码级问题

### F1. 每 20ms 调一次 handle_event，排空速率是否足够

**没有证据证明正常 20ms 节拍本身足以造成 5 秒超时。更紧迫的问题是事件消费方式。**

正常路径约为每秒 50 次调用。即便保守假设每次只推进一个事件，十余个事件也不足以单独解释数秒停顿。并且“一次公共 API 调用”与“一个硬件事件”不能直接等同。同族 Samsung 实现会在内部处理事件，直到产生待返回消息时退出，说明需要区分内部事件推进与外部消息派发。[loader 定时与调用位置](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4039>)、[Samsung 内部事件循环](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\uefi-udon\Silicon\Samsung\SamsungPkg\Drivers\UsbfnDwc3Dxe\Dwc3Endpoint.c:809>)

实际代码有三个明确问题。

- **等待降级路径是 200ms。** `BS->stall(200000)` 的单位为微秒。250 个切片会从约 5 秒变成约 50 秒，1250 个切片会从约 25 秒变成约 250 秒。`set_timer()` 的返回值没有检查，等待实际节拍也没有记录。[loader.c:4040–4054](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4040>)
- **状态事件被 helper 消费后，未累计到 host_seen。** 等待循环只更新 `usb_connected`，`host_seen` 只在每个 beat 的单独调用处设置。大多数状态事件会落在等待循环内，软化重掷可能因此漏判。[等待中的状态消费](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4054>)、[beat 中的 host_seen](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4278>)
- **TransferNotification 也可能被 helper 丢弃。** v19b 奇数拍提交真实接收后，后续等待循环会继续调用 handle_event，却没有把传输完成交给命令服务，也没有据此清理 `usb_rx_queued`。这会产生“主机写入完成，命令没有执行”及接收标志过期的问题。[奇数拍服务](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4287>)、[命令服务对完成事件的依赖](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4839>)

**裁决**——建立单一事件消费入口，统一更新状态并路由传输完成。可以增加有上限的连续排空，但应先测最大调用间隔、积压量和错误返回，避免仅把频率调快后继续丢事件。

### F2. usb_present 只写 RUN_STOP，是否漏了 config

**尚不能认定漏了必需的 config 步骤，也不支持直接补调一次 vendor config。**

实际调用顺序是 `start_ex(&usb_set)` 成功、分配传输缓冲、关闭 SUSPHY，然后 `usb_present()`。F12 已说明 start_ex 路径包含事件缓冲、EP0 和控制状态机配置。Wave 22 也存在成功提交的会话，说明当前拆分流程至少具有可行路径。[loader 启动顺序](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4156>)、[F12 T1 路径](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f12-ep2-not-configured.md:58)

仍未回答的是，**vendor connect 的 config 与 start_ex 实际完成的配置是否具有相同后置条件**。尤其需要比较事件缓冲、EP0 SETUP 接收、速度复位、控制器运行状态，以及异步回调是否随后再改这些对象。再次 config 也可能重置已经建立的状态。对此目前证据不足，宜先比较 present 前的寄存器和状态快照。[Wave 22 vendor connect 与 start_ex 对照](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/waves/wave22-host-visibility.md:14)

### F3. five milliseconds 注释与 stall(50000)

**实际为 50ms，注释错误。** 该调用位于 `usb_present()`，不在 `usb_start_attempt()` 函数体中。它增加了 45ms 的实际静默时间。在秒级故障中优先级较低，正常路径下也发生在本次 RUN_STOP 拉高之前。若 vendor 已提前展示设备，则这段时间仍可能处于主机可见但无人服务的窗口。[loader.c:4083–4092](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4083>)

应一并修正 F1 中的 200ms 降级路径，后者对实验时序的影响大得多。

### F4. DEPSTARTCFG 是否“只许一次”

**不存在笼统的“每 boot 只许一次”语义。关键是资源索引、生命周期和现存端点状态。**

Linux DWC3 明确区分资源索引 `0` 与 `2`。前者重置全部端点资源，用于上电或软复位初始化，后者重置非控制端点资源，用于 SET_CONFIGURATION 或休眠恢复。这直接支持初始化后在配置阶段再次执行该类命令。[Linux DWC3 start_config 语义](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/gadget.c#L537-L570)

本地 Samsung 同族实现也在 EP0 初始化时启动配置，并在 SET_CONFIG / SET_INTERFACE 时重建非控制端点。但它的具体资源管理策略不能直接证明 Qualcomm blob 正确。下一步应取证 vendor T2 的资源索引、命令状态，以及是否在旧 transfer 仍活跃时重新分配资源。F12 已指出 `DwcConfigureEP` 对已配置状态有单独拒绝分支，这值得保留为 H1 子类。[Samsung 初始化配置](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\uefi-udon\Silicon\Samsung\SamsungPkg\Drivers\UsbfnDwc3Dxe\Dwc3Endpoint.c:126>)、[Samsung 标准请求处理](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\uefi-udon\Silicon\Samsung\SamsungPkg\Drivers\UsbfnDwc3Dxe\Dwc3Endpoint.c:468>)、[F12 已配置拒绝分支](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f12-ep2-not-configured.md:49)

### F5. beat 0 立即探测、beat 1 命中的解释

**beat 0 未配置通常是预期状态，不能作为失败根因证据。** present 后，主机还要完成连接检测、复位、描述符读取和配置。beat 1 命中只表明 OUT 提交在两次采样之间变得可接受，不能据此推导 Windows 的典型枚举耗时为 5 秒。[探针节拍与提交](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4266>)、[v18 beat 记录](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/logdump-v18.bin.keylines.txt:2)

v19b 的 raw 探针只在 **beat 0** 调用，恰好最容易采到正常的“配置尚未发生”。应该把关键采样移到首次真实配置证据之后，或持续失败窗口末端。当前 gen0 的 24 拍含立即执行的 beat 0，正常切片下最后一拍约为 115 秒，名义窗口与实际 wall time也应分别记录。[raw 调用条件](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4317>)

### F6. 直接寄存器驱动 DWC3 gadget 的成本与风险

**技术上可行，当前优先级低，风险高。**

最小替代范围已经包含 EP0 三阶段状态机、复位与 ConnectDone、速度相关描述符、端点资源、TRB/DMA 缓存一致性、取消与重连，以及 Qualcomm 平台初始化后的所有权交接。现有 loader 的协议调用分布在启动、等待、收发和命令循环中。[协议接口](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\efi.h:271>)、[loader 收发路径](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4400>)

工程估算上，熟悉 DWC3 的工程师借用已有平台初始化，做固定描述符、USB2 EP0+bulk 原型属于**多日至一两周级**工作。达到可靠重连、连续传输、错误恢复和跨启动一致性，通常应按**数周级**安排。这是估算，项目材料无法给出工期保证。

建议把它保留为后备路线。启动条件应是诊断证据反复锁定 vendor 内部不可绕过故障，或该栈长期无法提供可验证的所有权与恢复机制。当前已有可提交会话，仍有数个低成本可修问题。

---

## 三、结构毒窗的最优修复策略

**最优策略是建立“初始化期间不展示，状态准备完成后只展示一次”的生命周期。25 秒缩到 5 秒可作缓解。**

目前的风险链条有代码和反汇编摘要支持。

1. loader 发出平台 init event。
2. vendor 回调可能在等待期启动控制器并展示设备。
3. loader 此时没有服务本次枚举。
4. start_ex 又断开并重新配置。
5. loader 再写 RUN_STOP 展示设备。

但“每 boot 首枚举必死、Windows 随后永不重试”仍比现有证据更强。缺少逐次、带时间的主机控制请求与设备状态对应记录。20 秒总线采样也无法还原这一过程的细节。[init 与 settle](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4205>)、[vendor 展示路径摘要](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/waves/wave22-host-visibility.md:14)

推荐执行方按下列顺序设计修复。

- **明确 vendor bring-up 完成条件。** 固定等待时间只能近似这一条件。
- **初始化期间抑制对主机展示。** 优先选择已有协议或角色控制支持的方式。若只能由 loader 在回调完成后断开，应保留明确的干净断开阶段，并核实异步回调不会再次拉高 RUN_STOP。
- **start_ex 成功后检查 EP0、事件缓冲与复位状态，立即进入统一 pump，再展示一次。**
- **成功启动后停止重复 init kick。** 恢复动作应进入明确的恢复状态，避免在已有效的事件环上重新触发平台配置。
- **失败恢复有明确边界。** 仅在持续无进展、已确认的断开或控制器故障条件下重建，记录重建原因。

现有重掷路径先 `usb_init_kick()`，随后对旧的成功启动状态泵送 25 秒，再调用 start_ex。回调若在该窗口重新配置控制器，旧事件环与当前硬件的对应关系需要补证。[重掷顺序](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4344>)

**5 秒仍可能覆盖完整的一次枚举失败期限。** 因而不能把等待缩短五倍解释为失败概率降低五倍。v16 的一次首试成功支持它值得对照，但不足以证明毒窗已被消除。

---

## 四、判别实验设计，按信息增益与刷写次数排序

以下面向**下一次可用的两轮预算**。当前波已用轮数应由执行方记录决定，本报告不构成追加刷写。

### 实验 0，零刷写，先使主机结果可信

| 工作 | 预期观测与价值 |
|---|---|
| 单一 Windows libusb 客户端持有设备，诊断时停止 attach/detach 手术 | 排除双所有者、反复打开关闭和恢复脚本相互干扰 |
| 修正屏录提取协议，使用固定只读 getvar 作为首个活性检查 | 避免把应用协议等待误认成 USB 失败 |
| 记录 DLL 版本、驱动服务、设备路径、速度、配置、端点参数和 transferred 字节数 | 区分缓存状态、设备代际与真实数据进展 |
| 使用已有 USB 捕获或 ETW 手段，记录首次枚举及配置请求完成状态 | 核实 SET_CONFIGURATION 是否真正进入下层请求链，是否 STALL、超时或成功 |
| 将 host 时间线与 present、start_ex、重掷、kernel-run 相位关联 | 判断失败发生在哪一个生命周期阶段 |

若需要区分物理总线上的连续 NAK 与驱动内部挂起，单靠应用日志不足，必要时需控制器事件或硬件分析仪。主机 URB 捕获能够先解决“是否真的提交配置请求、完成状态是什么”这一层。

### 实验 1，第一轮刷写，做能够分叉的诊断版本

目标是一次失败也能取得有效结论。

**必要调整**

- 统一事件消费，避免 F1 的状态和传输完成丢失。
- 保留一条真实、非零长度的 OUT 接收请求，记录提交返回值及完成事件。避免零长度探针与真实接收争用。
- 提供一个固定的稳定观测窗口，期间不自动重初始化控制器。
- 保持其他无关变量固定，尤其把 USB 诊断与 300 秒显示实验分开。

**关键取证字段**

- 会话、generation、单调时钟、当前服务相位。
- start_ex、缓冲分配、接收提交、abort 的各自返回码。
- DeviceStateChange 与传输完成事件的顺序、状态和字节数。
- present 前后、首次主机进展后及失败末端的 GCTL、DCTL、DSTS、DALEPENA、事件计数。
- 经对象布局核验后读取的两个 vendor speed 字段、phys[2]/phys[3] 状态。
- vendor 前导错误行，尤其 DEPSTARTCFG、端点配置失败、Unknown USB Speed。

私有对象读取必须先核验所属实例、结构布局与地址范围。若当前无法安全获得，第一轮仍可通过前导错误屏摄和主机捕获分辨部分分支，但 **H1/H2 可能继续证据不足**。

| 第一轮观测 | 判决 |
|---|---|
| 真实接收提交成功，主机写成功，设备报告完成 | “未配置”假设下降，继续检查命令派发与 IN 应答 |
| 真实配置请求已到达，Usbfn speed 有效，DEPSTARTCFG 或 walk 有明确失败 | **H1 显著上升** |
| 处理配置时 Usbfn speed 为 0，硬件速度已有效，bulk 参数取到 0 | **H2 显著上升** |
| 上层 speed 为 0，出现 Unknown USB Speed，配置控制请求失败 | **H3 显著上升** |
| 设备已配置但从未留下有效 OUT 接收 | 优先修接收生命周期 |
| GCTL bit11 在 present 前仍为 1 | 优先处理复位流程，暂缓解释 walk |
| 设备侧持续推进，但主机所有权切换后才失效 | 主机驱动与 usbipd 路径上升 |

### 实验 2，第二轮刷写，只处理第一轮锁定的分支

- **H1 被支持**——针对资源配置索引、旧 transfer、命令超时或端点重复配置中的一个明确子因做单变量修改。
- **H2 被支持**——修复速度事件与状态复位顺序。使用真实协商速度，不能直接把未知速度强制为 SS。
- **H3 被支持**——处理 UsbDeviceDxe 的速度传播与控制状态，验证真实配置请求完成。
- **接收生命周期被支持**——保持持续有效 RX，验证主机写入、设备完成、命令执行、IN 应答四点闭环。
- **初始化毒窗或复位被支持**——实施受控展示或正确复位序列，与第一轮使用相同主机环境对照。

第二轮至少应验收**带关联标识的多次双向命令应答、一个有长度与内容校验的上传，以及受控重连后的恢复**。仅再次出现 `armed` 日志，仍不足以验收 SSH 数据面。

---

## 五、v19 施工单逐项裁决

| 项目 | 裁决 | 建议顺序及必要修正 |
|---|---|---|
| 软化重掷、gen0 延长 | **同意方向，当前实现需修正** | 放在统一事件消费之后。host_seen 漏收等待内事件，而且当前任意 DeviceStateChange 都设为 1，Disconnected 也算“保住主机”。进入下一代还会清零，可能再次重掷 |
| 探针阶段提前服务 | **高优先级同意，当前奇数拍方案存在缺陷** | 与统一 pump 一起完成。真实 RX 完成不能被等待 helper 丢弃，`usb_rx_queued` 不能单独作为仍有效的证明 |
| Windows libusb 直连 | **同意，零刷写工作第一项** | 先修提取协议，再用于 E2E。日志需区分 open、OUT 完成、命令应答、上传完成 |
| usbipd 事件驱动 attach | **后移** | Windows 直连诊断期间保持单一所有者。未来事件驱动能减少盲目手术，但不能保证 vhci 重放成功 |
| raw 失败码 | **提升为必需诊断项，但当前实现不足以分 H1/H2** | 在有意义的失败时点采样。0xC 是末端未配置状态，H1/H2/H3 都能汇聚到这里 |
| settle 25s→5s | **同意作为缓解，对照实施** | 当前 WSL 已是 5 秒。最终方案仍需受控展示，并修正计时降级路径 |

软化重掷的具体问题位于 `host_seen` 更新、每代清零和重掷条件。提前服务的完成事件问题见 F1。[host_seen 生命周期](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4263>)、[重掷判断](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4335>)

**建议施工顺序为，主机协议与观测修正 → 统一事件消费和真实 RX → 诊断取证 → 按进展软化重掷及受控展示 → settle 对照 → usbipd 路径恢复。**

### 当前 raw helper 还有两个限制

第一，它执行的是**第二次独立提交**，没有取得第一次调用的原始返回值。第一次失败与第二次成功可以发生在状态变化边界。第二次若成功，当前 helper 没有接管或取消该 transfer，会留下未登记的请求。第二，它只在 beat 0 运行，无法解释几十秒后仍然失败的原因。[raw helper](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4105>)、[调用条件](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4317>)

此外，“任何非零都等于未武装”应收窄。F12 的 0xC 有明确状态判据，其他错误还可能来自资源、参数、活动 transfer 或控制器提交失败。

---

## 六、遗漏候选与确定代码缺陷

### 1. P1，GCTL 复位流程没有显式解除

实际代码置 `GCTL` bit11，等待它自行清零，超时后直接继续。Linux 的 GCTL CORESOFTRESET 流程会显式清除此位。DCTL 的自清软复位位是 bit30，不能与 GCTL bit11 混用。当前代码还把 DCTL bit18 注释为 CS，该解释也应核对。[loader 复位实现](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:3996>)、[Linux 显式解除 GCTL 复位](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/core.c#L193-L214)、[DWC3 DCTL 定义](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/dwc3/core.h#L447-L463)

**已确定的是 loader 自己没有完成解除动作。** vendor 随后是否清位，现有材料不足。因此应先读取 bring-up 后及 present 前的 GCTL，再决定其根因权重。它也意味着此前“三重唤醒修复无效”不能完整排除复位生命周期问题。

### 2. P1，屏录提取缺少 upload 命令

`fetch_staged()` 发 staging 命令并收到 `OKAY` 后，直接进入读取 DATA。loader 的 `oem recording` 只设置 `staged_data/staged_len` 并回复 OKAY，真正发送数据的是后续 `upload`。按现存代码，即使 USB 完全畅通，这条提取链也会等待超时。[主机 fetch_staged](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/fetch-recording-23.py:129)、[loader recording staging](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4755>)、[loader upload](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4720>)

### 3. P1，FAIL 解析与终帧处理不匹配

主机解析器识别 `FAIL:`，loader 的 `fb_reply("FAIL", text)` 拼接为四字节 `FAIL` 后直接跟正文。正常的“内核运行中”“没有 recording”等响应会被误分类。上传读取还应验证准确 DATA 长度，并消费末尾 OKAY，避免下一条命令读取到前一次终帧。[主机响应解析](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/fetch-recording-23.py:76)、[loader 回复格式](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4464>)

### 4. P2，接收布尔状态缺少代际与请求身份

当前 `usb_rx_queued` 不能表明它属于哪次启动、哪次请求，是否已完成、取消或被复位。`usb_poll_command()` 又会在任意 DeviceStateChange 时清零它。需要让请求状态跟随事件生命周期变化，避免重复提交与过期请求判断。[RX 提交及清理](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4839>)

### 5. P2，错误归因与缓冲分配资源

`usb_start_attempt()` 把 start_ex 和两个缓冲分配串在一个条件中，但失败只打印 start_ex 的 `s`。分配失败可能显示为 start_ex 成功码，部分成功的分配也没有在该路径释放。尚无证据证明它造成当前故障，但会污染诊断并在重试中积累资源。[loader.c:4156–4167](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:4156>)

### 6. 后续候选，按观测触发排查

- **协商速度与实际返回描述符。** 现存非 SS 配置描述符固定 bulk MPS=512。若出现 FS 回落，需要核对 vendor 是否重写了实际返回值，不能笼统排除所有速度下的描述符问题。
- **EP0 正常、bulk DMA 不正常。** 若配置与接收提交均成功，但真实数据不前进，应检查 DMA 地址、TRB、缓存一致性与资源索引。
- **事件积压、长阻塞或丢事件。** 应记录最大 pump 间隔与错误状态，不能由循环设计的名义频率代替。
- **异步平台回调覆盖当前配置。** 特别关注 re-kick 后继续使用旧事件环的窗口。

这些候选目前均未定案，应该由第一轮诊断结果决定是否展开。

---

## 七、usbipd 对 Windows 枚举的影响与排序

必须区分三种状态。

| 状态 | 对 Windows 的影响判断 |
|---|---|
| 普通 bind / Shared，未 attach | 主要是持久共享登记。单凭这一状态，不能解释持续的描述符超时 |
| Shared forced | 会切换设备驱动绑定，属于更强变量，需要单独记录 |
| attach / detach 到 WSL | 涉及设备所有权交接。附加期间 Windows 不能同时使用该设备，Linux 侧请求也经 Windows 导出驱动执行 |

usbipd 上游实现中，普通 bind 持久化实例，force 分支调用驱动切换。WSL 文档明确说明 attach 期间设备不能由 Windows 使用。当前上游还会截获 Linux 侧 SET_CONFIGURATION，转为驱动 IOCTL，因此 vhci 侧观察到一次配置调用，也不能直接等同于原始控制请求未经改动地到达设备。[bind 与 force 实现](https://github.com/dorssel/usbipd-win/blob/master/Usbipd/CommandHandlersCli.cs#L161-L204)、[WSL 所有权说明](https://github.com/dorssel/usbipd-win/wiki/WSL-support)、[SET_CONFIGURATION 处理](https://github.com/dorssel/usbipd-win/blob/master/Usbipd/AttachedEndpoint.cs#L270-L284)

**在本项目 `0000:0002` 的解释顺序中，我暂将“活跃 attach/detach 手术或强制驱动切换”列第三，将“仅残留普通 Shared 登记”列更后。**

1. 展示期间 EP0 没有被有效服务。
2. 控制器复位、配置与再次展示的生命周期失配。
3. 活跃 usbipd 手术或驱动所有权切换。
4. 其他主机、连接和速度相关问题。
5. 单独的普通 Shared 持久登记。

这是当前证据下的条件排序。若捕获显示每次描述符失败都紧随 attach、驱动重启或端口操作，第三项应立即上升。反过来，设备首次描述符已经失败时，随后无法完成 vhci attach 也可能只是后果。

本地日志已有 **Shared 状态下成功枚举并保持数分钟**的记录，因此 Shared 本身不是充分致因。20 秒采样能证明状态变化，不能确定每次变化的调用先后关系。[本地总线记录](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave22-scripts/bus18-watch.log:3)

---

## 八、整体路线与 §5-G 风险

### 1. loader 桥接网络路线仍值得继续

现有材料已支持 loader 常驻、共享页网络接口及至少一次设备侧 OUT 可提交路径。当前应优先取得稳定的双向管理命令，再验收网络与 SSH。将“可打开”“端点提交被接受”“传输完成”“SSH 可用”分层验收，能够减少错误归因。

### 2. 23.x 的取证依赖需要重新表述

F13 将屏录实验描述为与 USB 阻塞近乎独立，但现有 recording 保存在本次运行的内存中，仍通过 loader 的 USB staging/upload 提取。logdump 能回安卓后读取，并不自动证明 recording 也有同样的持久化通道。USB 提取失败时，只能说显示取证未完成。[F13 顺序判断](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f13-virtual-display.md:198)、[屏录内存生命周期](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnu\files\iokit\Kernel\MiniIOMobileFramebuffer.cpp:118>)

### 3. 300 秒显示实验可以做探索，但不能替代 USB 诊断基线

F6 已有约 218 秒 vnode 耗尽记录。v19 恢复 300 秒，可能让 T+280 采样窗根本无法到达。F13 自己也登记了这一风险。我的裁决是，**USB 诊断保持短、可回收的内核会话，长驻留显示实验单独解释结果**。若长会话触发 F6，应保留触发前录屏和日志作为部分证据，不能据此判显示路线失败。[F6 记录](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/waves/wave21-ssh-e2e.md:57)、[F13 判定窗与风险](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/research/f13-virtual-display.md:130)

PID 稳定性也需要正向采样或可靠的退出、重启记录。日志中只出现一次 exec，可能来自日志覆盖范围或截断，不能单独证明全过程存活。

### 4. cmdline 预算修正方向正确，但余量很小

v19 builder 已把 loader 前缀计入，得到约 `598/607`。实际前缀仍随版本字符串及条件分支变化，最终应核验当次 logdump 打印出的完整 cmdline、截断警告和关键参数。WSL 源码已经有对应输出，可以直接作为验收依据。[v19 预算计算](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave23-scripts/make-cmdline-v19.py:15)、[loader 实际长度与截断输出](<\\wsl.localhost\FedoraLinux-44\home\<host>\hakios\kernel\xnuloader\loader.c:3436>)

### 5. “boot_b 非破坏性”应按已有平台边界解释

boot_b 隔离保护了引导镜像，但运行中的 XNU 仍会访问共享硬件与可写 Darwin 数据卷。项目状态也记录了既有 GPT 调整和 `/var` 持久写入。因此后续复位、DMA 或原生 DWC3 接管实验，应继续把共享资源所有权和数据卷一致性列入验收。仅凭刷写目标为 boot_b，无法覆盖运行期的全部影响范围。[项目状态与存储布局](<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/docs/STATUS.md:26)

**当前最值得避免的预算浪费，是用 beat 0 的末端错误码继续猜 H1/H2，或让存在协议缺陷的提取脚本把成功窗口判成失败。先完成零刷写修正，再用一轮取得“配置请求、速度状态、端点状态、真实 RX、完成事件”的同会话证据，第二轮才有条件成为针对性修复。**