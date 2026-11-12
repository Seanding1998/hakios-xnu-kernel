# 外部评审导读（2026-11-11）：USB 错误墙的问题史与评审问题清单

> 交给外部 AI 审阅人（ChatGPT 等，有本仓文件读取权限）。本轮专审一个用户直接投诉的问题：**Darwin 会话/服务窗相位手机屏幕错误墙刷屏（0x8B → 0x8C）+ loader 半启动状态**。项目里已做了一轮源码级修复（阶段 38，离线完成、未真机验证验证），你要做的是**审它、补它、以及评估我们自己判为"难点"的 vendor 层方案**。所有结论以仓内文件为准，你的最终产出 = `docs/review/gpt-review-report-3-2026-11-11-usb.md`。

## 1. 项目 30 秒速览

把 Apple XNU（HakiOS 上游）移植到一加 Ace 2（PHK110 / SM8475 / 高通 Cape 平台）。启动链：`ABL → boot_b（Mu-Silicium UEFI + AVB graft）→ BootShim → XnuLoader → XNU 内核 → Darwin`。boot_b 每次刷写走既定授权（三门：graft sha → `getvar product=taro` → current-slot）；boot_a（日常安卓）**绝对禁刷**。

**USB 服务器有两个相位**：
- **loader 相位**：XnuLoader 内置 USB fastboot 命令服务器（gadget `18d1:d00d`，serial xnuloader 风格），内核会话结束后还守一个**固定 240 秒服务窗**（`loader.c:5617` usb_service_secs）
- **内核会话相位**：loader 桥接网络（en0 10.0.0.2/30）承 SSH 隧道；会话帽现值 600 秒（`loader_return_after=600`）

## 2. 问题史（时间序，全部有档案）

| 阶段 | 现象 | 档案 |
|---|---|---|
| 阶段 21.2 起 | 主机侧提交失败：`DwcPrepareURB:Trb: physical endpoint[2] not configured` / `UsbfnDwcSubmitUrbNode: PrepareUrb Failed: 0x8000000C` | `docs/research/f12-ep2-not-configured.md`、`docs/waves/wave21_2-ssh-catch.md` |
| 阶段 28 | 内核会话返回后 bulk 对全聋 165 分钟（ep0 仍可枚举）= **半启动状态**；~3h15m 自发解体 | `docs/waves/wave28-var-persistence.md` |
| 用户屏摄定案 | 墙时序 = **先 0xB 后 0xC**：`TRB ring of EpIndex 3 is full`（bulk-IN 武装无消费者，堆满后每次提交 vendor 无限打印直写 framebuffer）→ 转换点拆除 → 0xC（端点未配置）= 拆除后残骸 | STATUS「USB 错误墙时序模型」段 |
| 阶段 31/36/37 | 半启动状态三轮复现；**会话末端从不出现干净可抓的 fastboot 窗**（半启动残留枚举 → EDL），可抓窗只能由用户物理按键制造 | `wave37-scripts/progress.log` |
| 2026-11-11 屏摄 | 第三型墙行：`DwcGetNextEvent:Evt: DWC_TRB_STS_SETUP_PENDING Pending Setup received; possible fast-forward condition`（loader 相位主机 SETUP 探测时打） | 本导读新增，未深挖 |
| 用户投诉 | 刷屏体验差 → 阶段 38 立项 | `docs/waves/wave38-usb-selfheal.md` |

## 3. 已做的修复（阶段 38，离线 DONE，**未真机验证**）

两张 loader 侧脸的源码级定案（全部在 `~/hakios/kernel/xnuloader/loader.c`，我们的代码；七 hunk，补丁器 `wave38-scripts/patch-loader-v38.py` 带唯一性断言；改前备份 `loader.c.v37-orig`）：

1. **IN 侧泄漏（0xB 风暴的泵）**：`usb_tx` 应答超时放弃时**不排空 TRB** → 半死读者（usbipd detach / 隧道死）下每条主机命令堆一条 → 环/URB 池耗尽 → 每次提交 vendor 打一行 0xB。修复：单飞不变量（`usb_in_expect`）+ 弃答即 `abort_xfer`（对自身 END_TRANSFER 排空）+ **IN 门**（3 条未读起冻结提交，1s→30s 倍退避、每拍放一条探测——不提交 = vendor 无从打印）
2. **服务窗热旋（刷屏引擎）**：`usb_command_loop` 的 `usb_rx` 提交无门 + 窗限检查在提交失败路径上永不可达 → 半启动状态每旋 4 行墙印、窗永不过期。修复：rx 提交纳入既有墙门 + 循环安静泵送 1s + IN 10s 界
3. **`usb_pair_rebuild`**（整对重建的 loader 侧最小等效）：服务窗相、双半确认（IN 门起 ∧ OUT 在墙 ∧ 无站立接收）→ 对双 `abort_xfer` + `start_ex` 整体重掷（SET_CONFIG replay 重武装 bulk 对），≤2 次/60s 间隔，**会话相硬闸**（不杀隧道）
4. **FD 层评估（我们判为难点，未动手）**：FrameBufferSerialPortLib 限频源码在树（`SerialPortWrite` @ L298）但 FD 重编碎全波锚 `8924cb67`；udon 的 UsbFnDwc = **vendor blob 无源码**，只能字节手术——完整设计段在 `docs/waves/wave38-usb-selfheal.md` §5

产物：payload `9662823f…` / graft `742bce63…`，verify 65/65（`wave38-scripts/verify-wave38.log`）。**注意**：loader 构建不可复现（PE TimeDateStamp）——verify 绿后禁重跑 build.sh。该产物原样已与 v33 内核互斥（它带 v26 内核），**正在重基线为 v34 = v33 内核（55a8d40f）+ wave38 loader.efi（3f595c52）+ gpu=1 cmdline**，离线+真机判定进行中。

## 4. 请你审的五个问题（按优先级）

**Q1（P0）· loader.c 七 hunk 审读**：正确性、竞态、不变量完整性。重点怀疑位：`usb_in_expect` 单飞不变量在 pump 的 stray-completion 吞噬路径上是否完备；`abort_xfer` 对"自身队列中尚未完成的 transfer"调用是否合法（DWC3 语义层面）；IN 门"3 条未读冻结"与 10s 界的组合是否可能把健康读者也冻结；`usb_pair_rebuild` 的双半确认条件是否有假阴性（活着被拆）。
**Q2（P0）· FD 层字节手术可行性**：uefi-udon FD 内 FrameBufferSerialPortLib 加限频、vendor UsbFnDwc blob 的端点拆除/重建路径——字节 patch 的锚点怎么选、风险多大、有没有比"整 FD 重编"更小的切法。参考：`docs/waves/wave38-usb-selfheal.md` §5（我们的设计段）。
**Q3（P1）· 第三型墙行解读**：`DWC_TRB_STS_SETUP_PENDING Pending Setup received; possible fast-forward condition` 在此架构下意味着什么（主机 SETUP 期间事件队列快进？对墙治理有无影响）。
**Q4（P1）· 验收计划充分性**：A1（墙消失或限频为每 ≥2s 一行带计数）/ A2（半启动残留自愈行链：`a reply came back unread` → `the IN gate is up` → `the bulk pair reads dead both ways … rebuild` → `the pair's rebuild is in`）/ A3（SSH HIT）+ 双回归门（SSH E2E verdict27 语义 + /var verdict34 语义）。漏了什么场景？
**Q5（P2）· 认知纠错**：我们对 DWC3 端点生命周期（END_TRANSFER 语义 / 双半重建 / TRB 排空与 StartXfer 关系 / SET_CONFIG replay 重武装）有没有理解性错误。

## 5. 文件地图（按此读）

| 主题 | 路径 |
|---|---|
| 修复本体 | `~/hakios/kernel/xnuloader/loader.c`（现文本）+ 同目录 `loader.c.v37-orig`（改前备份）+ `wave38-scripts/patch-loader-v38.py`（七 hunk 补丁器，断言式） |
| 阶段日志与 FD 设计段 | `docs/waves/wave38-usb-selfheal.md`（§5 FD 层设计 / §6 真机预案） |
| 验像 | `wave38-scripts/verify-udon-hakios-wave38.py` + `wave38-scripts/verify-wave38.log` |
| 端点墙归因 | `docs/research/f12-ep2-not-configured.md`、`docs/waves/wave21_2-ssh-catch.md` |
| 自愈设计源头 | `docs/waves/wave34-var-fix.md` §5 |
| 服务窗机制 | loader.c `usb_service_secs`（约 :5617）+ `docs/waves/wave28-var-persistence.md` |
| 时序模型总账 | `docs/STATUS.md`「USB 错误墙时序模型」段 + 本文 §2 |
| 流水 | `wave38-scripts/progress.log` |

## 6. 约束（审方案时必须尊重）

- boot_a 绝对禁刷；boot_b 刷写循环 = 既有授权，但每次三门 + OKAY 断言
- 零变砖 = 铁律；任何"试试看"级方案必须先离线验证 + 回滚路径（回滚 = 重刷 v33 原样）
- WSL 是共享资源，禁 wsl --shutdown；usbipd 持久绑定（269e72e4 等）待管理员清理——审阅不用管操作，但方案别依赖它们
- 用户态可接受墙行**限频**（每 ≥2s 一行带计数），不接受无限连刷

## 7. 产出要求

写 `docs/review/gpt-review-report-3-2026-11-11-usb.md`：中文为主；结论按 **P0/P1/P2** 分级；每条给**文件 + 行号/函数名级**证据或推理链；"我们的方案错了/不可行"请直说，不要委婉；若 Q2 判定字节手术不可行，给出替代路线（含工作量级估计）。
