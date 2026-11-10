# 阶段 24 · 2026-11-09 · 设计稿：USB 端点问题的诊断刷写

> 2026-11-09 · 设计稿（合并外部 ChatGPT 审阅 `docs/review/gpt-review-report-2026-11-09.md` + 第二轮屏摄裁决 `gpt-review-report-2-2026-11-09.md` + 审码）。实施波开工前如有 阶段 23.x 终报新事实再修订。
> 前置阅读：wave22-host-visibility.md §7（v19 施工单原稿）、f12-ep2-not-configured.md（指令级事实表）。

## 0. 目标

一次诊断刷写分辨 bulk 端点未配置的根因（H1/H2/H3 或新候选），并建立**四检查点验收通道**（真实 OUT 提交成功 → 主机写完成 → 设备收到完成事件 → IN 应答，分开记录）。上一轮裁决（屏摄）：错误墙 = F12 尾部实锤（phys[2] 软件状态 0 → 0x8000000C），**缺的是把状态留在零的那一步**；刷屏源 = `usb_poll_command` 失败重提交，且淹没前导错误。

## 1. 设备侧施工项（loader.c，全部已定案）

| # | 项 | 内容 | 修复对象 |
|---|---|---|---|
| ① | **统一事件消费入口** | 单一 pump 函数：所有 handle_event 调用收尾；统一更新 host_seen/usb_connected（含等待 helper 内的状态事件累计）；TransferNotification 路由到命令服务并维护 usb_rx_queued 生命周期；host_seen 只在 Connected/Configured 置位（Disconnected 不算"主机在场"）、跨代际不盲清 | F1 三缺陷（等待降级 200ms、状态事件丢失、传输完成被丢弃） |
| ② | **持续真实 RX** | 非零长度 OUT 接收请求常驻（不与零长探针争用）；请求带代际/身份标识；完成/取消/复位都更新状态 | "没有有效 OUT 接收"候选 + P2-4 |
| ③ | **失败限频 + 首错粘性** | 持续失败退避（如首错后 1s→5s→30s），首错打一次 + 累计计数器；前导错误（DEPSTARTCFG Fails / Failed to set config for ep / DwcConfigureEP failed / Unknown USB Speed）粘性保留 | 刷屏淹没前导 |
| ④ | **ConOut 镜像** | loader 入口包一层 `gST->ConOut->OutputString`：vendor 屏打全量抄进 loader 日志环 → logdump 取证不再依赖摄像头。**前置准备工作**：确认 vendor 打印确实走 ConOut（屏上错误行与控制台同一滚动区 = 旁证；若走独立 DebugLib/framebuffer 路径则改钩该层）；thunk 防递归（loader 自身 print 不重入）；抄环失败不影响原打印 | 屏摄路线放弃（确认拍不出可用画面） |
| ⑤ | **GCTL bit11 显式清除** | 软复位后超时未自清则主动清位；present 前读回 GCTL 记入日志 | P1-1（Linux 显式清 CORESOFTRESET；现码不清） |
| ⑥ | **六项采样字段** | (a) 同一会话单调时间线：present / ConnectDone / SET_CONFIGURATION / reset / init kick / start_ex / 首次 OUT 提交结果；(b) 双层 speed：UsbfnDwc `+0x184` / UsbDeviceDxe `+0x1f8`（先核验对象布局/实例/地址范围再读）；(c) phys[2]/phys[3] 状态——采样点 = 首次配置证据之后 + 持续失败末端；(d) GCTL/DCTL/DSTS/DALEPENA/事件计数——present 前 / 首次主机进展后 / 失败末端三时点；(e) raw 失败码在**有意义的失败时点**采（不是第二次独立提交——0xC 是末端汇聚态）；(f) 探针关键采样**移出 beat 0**（该点正常态就是未配置），移到首次配置证据后或失败窗末端；名义窗口与实际 wall time 分开记录 | H1/H2/H3 分辨 |

## 2. 主机侧（零刷写，与刷写并行）

1. 提取协议修复已由 阶段 23.x 完成（缺 `upload` 命令 + FAIL 解析错位 + getvar 活性检查）——直接复用其修好的脚本。
2. 诊断期**单一 Windows-libusb 所有者**（停 usbipd attach/detach 手术）。
3. 每次会话记录：DLL 版本 / 设备路径 / 速度 / 配置 / 端点参数 / transferred 字节数——区分设备代际与真实数据进展。

## 3. 判决表（ChatGPT 实验 1，照单执行）

| 第一轮观测 | 判决 |
|---|---|
| 真实接收提交成功，主机写成功，设备报告完成 | "未配置"假设下降，查命令派发与 IN 应答 |
| 真实配置请求已到达，Usbfn speed 有效，DEPSTARTCFG/walk 明确失败 | **H1 上升** |
| 处理配置时 Usbfn speed 为 0，硬件速度已有效，bulk maxpkt 取到 0 | **H2 上升** |
| 上层 speed 为 0，出现 Unknown USB Speed，配置请求失败 | **H3 上升** |
| 设备已配置但从未留下有效 OUT 接收 | 优先修接收生命周期 |
| GCTL bit11 在 present 前仍为 1 | 优先处理复位流程，暂缓解释 walk |
| 设备侧持续推进，但主机所有权切换后才失效 | 主机驱动/usbipd 路径上升 |

## 4. 预算与红线

- 刷写预算 2 轮（本波独立预算）；Exp-2 只做第一轮锁定分支的单变量修复。
- 只碰 boot_b；FD `8924cb67…` / shim `108ce972…` 零重建；device-layer 与 wave24-scripts/ 只新增；禁 git reset/checkout/stash/clean。
- loader 必带 `PAYLOAD_BASE=0xF4000000`（make-payload + verify 双层 pin，RVA 0x2190/0x2198 断言）。
- **验收不以 `armed` 行为准**：至少带关联标识的多次双向命令应答 + 一次有长度/内容校验的上传 + 受控重连恢复。

## 5. 风险登记

- 私有对象（speed 字段/EP 表）读取必须先核验布局与地址范围，读错会污染诊断甚至触发新异常；无法安全获得时，靠 ConOut 镜像的前导错误行 + 主机侧捕获降级分辨（H1/H2 可能继续证据不足，如实报告）。
- ConOut 镜像若 vendor 走独立打印层则 ④ 改钩对应层；准备工作核实是第一项任务。
- 会话时长保持短（≤180s，F6 vnode 耗尽 @218s 前回收）；显示长驻留实验（300s + 屏录）不在本波混做。
