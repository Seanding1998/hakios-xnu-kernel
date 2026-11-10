# 无 GPU 显示路线预研：先让桌面出画

日期：2026-11-08 ｜ 纯调研设计，零手机交互，零刷写 ｜ `~/hakios/kernel`（WSL）与 `upstream/` 树只读 ｜ ios-sweet 浅 clone 于 WSL `~/hakios/refs/ios-sweet`（代理 7897）

**引用缩写**

| 缩写 | 指什么 |
|---|---|
| `[SWEET]` | WSL `~/hakios/refs/ios-sweet`（dipa-studio/ios-sweet，depth-1 clone，2026-11-08） |
| `[TREE]` | WSL `~/hakios/kernel`（HakiOS 内核树 v2.1.13，xnu-8796.121.2 / Darwin 22.5，PHK110 开发树） |
| `[REPO]` | 本仓（Windows hakios-phk110） |
| b25 | Boot #25（阶段 20，v14 内核，2026-11-08，真实 launchd 28 进程那次） |

---

## 0. 摘要（先读这五条）

1. **外援结论的方向正确，但对我们是"旧闻"**：ios-sweet 证明的路线（内核假 IOMobileFramebuffer/IOSurface + CPU 渲染 → iOS 桌面）在我们自己的树里**已经全部存在并且已经在手机上跑过**。上游 HakiOS 有 `MiniIOSurface`（注册名同 Apple：`IOCoreSurfaceRoot`）+ `MiniIOMobileFramebuffer`（含假 disp0 节点、假 IOAcceleratorES、CPU 缩放上屏、屏录）三个内核内建假驱动，由平台专家无条件启动（`[TREE] xnu/files/iokit/Kernel/GenericARMPE.cpp:302-305`，conf 门 = 仅 `iokitcpp`，`[TREE] xnu/hakios.patch:1934-1944`）。
2. **证据**：b25 的 logdump（`[REPO] logdump-v14.bin`）里有 **`MiniIOSurface: backboardd[16] created surface 1: 1125x2436 'BGRA' …`、`MiniIOMobileFramebuffer: backboardd[16] selector 5 (… structure 1132 in …)`（= SwapEnd）、8 次 `swap N layer 0: surface M (1125x2436 'BGRA') from 0,0 1125x2436 to 0,0 …`** ——backboardd 已经在我们的虚拟显示上做真实 1125×2436 帧提交；SpringBoard[12] 也在建 CA 图层和 LA08 资产 surface。任务书里"无 IOMobileFramebuffer/IOSurface 服务"的现状描述**过时**（v13 logdump 0 条 → v14 起 20-42 条统计行；v14/v15/v16/v17 logdump 全部实测，§B.0）。
3. **ios-sweet 踩过的坑我们各有一一对应的现成解**：display-scale=0 → 我们的 loader.c 早写死 `display-scale=3`（`[TREE] xnuloader/loader.c:3486`）；refresh=0 → MiniIOMFB 发布完整 TimingElements（`[TREE] …MiniIOMobileFramebuffer.cpp:470-487` 一带）；CoreAnimation 找不到 GPU 干等 30 s → 上游发布"无 Metal/GL 属性"的假 IOAcceleratorES 让两个框架立刻放弃（`MiniIOMobileFramebuffer.cpp:1697-1733`）——比 ios-sweet（让它反复轮询不处理）更主动。
4. **战略翻转**：这条路线**不是 v0.5 GPU 战的竞品，而是它的前置验收通道**。上游设计里 GPU 只换"渲染器"（HakiosGPU/Mesa/Metal 往 IOSurface 里画），换"呈现"（IOMFB swap → panel memcpy）不变：swap 路径已带 GPU fence 挂钩（`MiniIOMobileFramebuffer.cpp:1164` "the GPU is not done with surface %u … shown as it is"；`drivers/gpu/hakios.gpu.cpp:484`）。插到 v0.5 之前**零返工**。
5. **阶段 23 真正的活**：不是"建虚拟显示"，而是（a）把 b25 已到 1125×2436 帧提交的链路**走完最后一公里**——给足驻留时间（b25 只驻留 120 s，上游 QEMU 上主屏要 ~5 分钟、redwood 真机 SpringBoard 就绪后还要等 30-40 s 应用注册）+ 用现成的 `rec_secs` 屏录通道**零交互取证出画**；（b）按判定协议处理残余进程不稳；（c）可选：触摸真指点（阶段 12c 遗留）。预估内核改动 ≈ 0 行（纯 cmdline + 判定），镜像/脚本 ≈ 200-400 行。

---

## A. ios-sweet 深度考古

### A.1 平台与实现形态（问题 1）

- **平台**：Xiaomi Redmi Note 10 Pro（代号 `sweet`，Qualcomm SM7150 / Snapdragon 732G），用户空间 = **iPhone X (iPhone10,3/D22AP) 的 iOS 16.7.16 (20H392) 未修改 rootfs**；内核 = xnu-8796（macOS 13.5 配置构建，经 GitHub macOS runner 的 blacktop/darwin-xnu-build + 81 个 patch）。`[SWEET] README.md`（头两段 + "How it boots"）。无串口（该板 debug UART 走 SPI），内核 console 画进 ABL splash framebuffer `0x9c000000` + userdata 尾部 4 MiB 持久日志环（README "There is no serial port…" 段）。
- **虚拟显示的实现物形态 = XNU 源码 patch（内核内建假 IOKit 驱动），不是 kext、不是用户态服务**：
  - patch 0046 `xnu/patches/0046-sweet-iosurface-iomfb.patch`（1449 行）新增两个文件 `iokit/Kernel/arm/SweetSurface.{h,cpp}` 和 `SweetFramebuffer.cpp`，并在 `iokit/KernelConfigTables.cpp` 里以 **IOKit personality 表**注册（`IOClass=IOCoreSurfaceRoot, IOProviderClass=IOResources`；`IOClass=AppleCLCD, IOProviderClass=IOPlatformDevice, IONameMatch='sweet,display'`）。"kext"形态被否定：它们直接编进内核镜像（`iokit/conf/files.arm64: optional iokitcpp`），与 AppleCLCD/IOMobileFramebuffer 这类闭源 kext 的**用户侧 ABI**（IOServiceOpen type 0 + IOConnectCallMethod 选择器 + trap）对齐。
  - 为什么必须做在内核：IOMobileFramebuffer.framework（用户态，backboardd 进程内）和 IOSurface.framework 用 IOServiceOpen 打开内核 IOService；XNU 8796 开源树里**没有**它们的源码或桩（IOMobileFramebuffer/IOSurface 是闭源 kext，xnu 只含 IOKit 内核核心 IOService/IOUserClient/IOMemoryDescriptor 等），所以只能自己写假的。上游 HakiOS 独立得出同一结论（[TREE] xnu/README.md "What is added" 表："replacements for closed drivers: surfaces, the display, the key store"）。

### A.2 IOSurface 服务怎么实现（问题 2）

`[SWEET] xnu/patches/0046…patch` SweetSurface.cpp 文件头注释（他们靠反汇编 iOS 16.7 IOSurface.framework 逆向出 ABI）：

- 用户态入口：`IOServiceNameMatching("IOCoreSurfaceRoot")` → IOServiceOpen type 0 → 用户客户端选择器：**sel 13**（limits，0x18 字节，+0x16 u16 必须为 1 = ABI 版本，+0/+4 行对齐掩码）、**sel 0**（create：标量入 [父 surface id]，结构入 = 序列化属性字典，结构出 = 0xa68 字节"lock result"）、**sel 4**（按 id lookup）、**sel 34**（按 mach port lookup）、**sel 35**（建 port）；**trap 0/1**（use count ±）、**trap 2/3**（lock/unlock，带 seed 出参）、**trap 4/5**（release）。
- **lock result（0xa68 B）**就是"surface 在你地址空间的哪"：+0 像素地址、+8 共享状态页（registry id、+0xc seed）、+0x10 时间戳、+0x18 id / 尺寸 / 行距 / 格式、+0x68 起每 plane 0x80。实现把每块 surface 的 wired 内核内存 **map 进每个 create/lookup 的任务**（`createMappingInTask`，kIOMapAnywhere）。
- 工程约束：id 表 4096 项、尺寸上限 16384、单 surface ≤256 MiB、总 wired ≤1.5 GiB（`SWEET_SURFACE_WIRED_MAX`）；Values/notifications/accelerators/shared events 等"不认识的选择器 = 记一次日志后**接受并忽略**"（default case 全零返回 kIOReturnSuccess）。
- 对照上游我们的实现：`[TREE] xnu/files/iokit/Kernel/MiniIOSurface.cpp`（1937 行）覆盖同样 ABI（文件头 33-57 行选择器枚举到 sel 44；trap 0-5 含额外的 Detach；表 16384 项、512 MiB、行对齐 64），注册名同为 `IOCoreSurfaceRoot`（:836-854），差异 = **不认识的选择器"记一次日志后拒绝"**（文件头 :8 "logged once and refused"）vs ios-sweet 的"忽略"——这是 阶段 23 若遇新调用方的一个候选放宽点（b25 日志已见 sel 40/41 被拒）。

### A.3 `/chosen/display-scale` 等 display 属性是谁注入的（问题 3）

- **注入者 = 他们自写的 ADT 生成器 `tools/mkadt.py`**（shim 启动 → 打包 kernel+ADT+boot-args 进 payload）。不是 DeviceTree im4p（im4p 只用来取 /product 真节点）。
- 陷阱全过程（`[SWEET] NOTES.md:85,84,86`，boot 0053n→0053s）：
  1. SpringBoard 死于 `FBSDisplayMode cannot be configured as requested : <FBSDisplayMode … infxinf@0x (1080x2400/0) 60Hz …>`——像素尺寸与 60 Hz 都合法，**scale=0**；
  2. 根因：**libMobileGestalt `MGIOMFBSupport.c`（sub_19c560a54）从 `IODeviceTree:/chosen` 读 `display-scale`（u32，默认 0）与 `display-rotation`**；像素尺寸走 IOMobileFramebufferGetDisplaySize（IOMFB sel 8/28）；
  3. 修复 = mkadt `/chosen/display-scale = 3`（1080×2400 @3x = 360×800 pt）→ 当天 SpringBoard/backboardd 双双只 exec 一次不再崩（NOTES.md:84）。
  4. 注意缓存陷阱：MobileGestalt 磁盘缓存（`/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/...`）可能把 scale 0 缓存住，重刷干净镜像才可信（NOTES.md:85 括注）。
- **display 组其余属性（mkadt.py 全文核实）**：
  - `/arm-io/disp0`：`device_type="display-subsystem"`（IOMobileFramebuffer.framework **数 /arm-io 子里 device_type 以 display-subsystem 开头的节点数**来决定等几个服务，0 → 无显示列表，节点比服务多 → 等 30 s；NOTES.md:98,112）+ `compatible="sweet,display"`（内核 AppleCLCD 的 IONameMatch）+ `canvas-width/height`（u32，框架从 service 的 IODeviceTree 父节点按 4 字节 CFData 读，NOTES.md:113,115）。
  - `/chosen` 显示相关只此两个（display-scale、display-rotation 隐含默认）；另有两个**非显示但同天必需**：`unique-chip-id`(8B)+`chip-id`(u32 0x8015) → XNU 由此生成 IOPlatformUUID（gethostuuid），缺它 = CFPreferences ByHost 写不进 = 数据迁移永不记完成（NOTES.md "ROOT CAUSE of the endless migration" 段）。
- **我们的成本 ≈ 0**：`display-scale=3` 与 `display-rotation=0` 我们的 loader **早已写入**（`[TREE] xnuloader/loader.c:3486-3487`，注释原文"what MobileGestalt answers main screen scale from"）；`unique-chip-id`/`chip-id 0x8015` 也在（loader.c:3535-3536 一带）；`/arm-io` 节点在（loader.c:3656），而 **disp0 子节点上游内核自己运行期发布**（`MiniIOMobileFramebuffer.cpp:1666-1693 publishDisplayNode()`：向 /arm-io attach `disp0`/`display-subsystem` 节点）——loader DT 一行都不用改。

### A.4 CPU 渲染主屏的实现（问题 4）

- **iOS 有没有 CPU 渲染回退路径？有，且无需显式触发到"能出画"的程度**。时间线（NOTES.md:84→:96→:66）：
  1. boot 0053s（display-scale 修好后）：backboardd 反复找 `IOProviderClass IOAcceleratorES`（0 命中）与 AGXAccelerator/IOAcceleratorESLegacy——**不死、进入等待**，系统静默 idle；
  2. boot 0053s 长跑：**首批 iOS 像素 = 数据迁移进度条**，由 backboardd 用 CoreGraphics 画进 IOSurface（"ProgressUI-style CoreGraphics drawing into IOSurfaces (no GPU used)"），双缓冲交替 swap——CPU 路径在有实际内容要画时自然工作；
  3. boot 0057u：Setup "Hello" 动画完整渲染（"Rendered by iOS 16.7 SpringBoard/Setup through CoreAnimation -> backboardd -> kernel IOSurface -> kernel AppleCLCD swaps -> ABL panel memory"）→ 最终主屏（NOTES.md:66）。
- **渲染器选择机制**（NOTES.md:116,156，QuartzCore 符号考古）：CA 有四个渲染器 `sw_new_context`（CA::OGL::SWContext，完整 CPU 光栅器含 blur/图片/IOSurface-backed surface）、`gles_new_context`、`metal_new_context`、`new_null_context`；CA 先试 Metal（CAMetalContextCreate）再 GLES，再 SW。仓库内**没有任何 CA_* 环境变量被设置**（本报告全库 grep：tools/、NOTES.md 排除考古段后 0 命中）——即 ios-sweet **没有显式触发**，渲染器自然落到 SW；NOTES.md:57 甚至注明"渲染器选择话题被安全分类器截断……rendering already works"。可确认的机制缺口：CA 每进程会**等一个 IOAccelerator 类服务最多 30 s** 才继续。
- **上游 HakiOS 对这缺口有确定性解**（比 ios-sweet 强）：`[TREE] MiniIOMobileFramebuffer.cpp:1697-1733 publishAccelerator()` 发布一个**不带 MetalPluginName/GL 属性的假 IOAcceleratorES**（名 "sgx"），注释原文："CoreAnimation waits half a minute for a service of this class … An accelerator without the properties that name its Metal and OpenGL ES drivers is passed over by both, which leaves CoreAnimation with its software renderer"。用户侧再配 `inject.c`（DYLD_INSERT 进 backboardd 的库）虚拟 HID 服务 + 免等光感 + 替 CA 摆开关（`[TREE] userland/src/inject.c:1-26`；`CONFIG_CAENV`/`CONFIG_CA_VBL` 门，`configs/common_defconfig:1100-1102`）。
- **渲染输出怎么到屏幕（"从 IOSurface 内容到 panel 内存"的搬运）**：
  - 触发点：CoreAnimation/backboardd 调 IOMFB 用户客户端 **sel 4 SwapBegin（返回 swap id）→ sel 5 SwapEnd（0x46c B 记录：+0x50 swap id、+0x54 起 4 层各一个 IOSurface id、+0x64/+0xc4 每层源矩形/目标矩形、+0x104 使能层掩码）**；
  - 内核在 SwapEnd 里**按 id 找到 surface（已 map 进内核），逐层把使能层的像素 memcpy 进 panel 内存（ABL 留下的连续 splash framebuffer）**——ios-sweet 无缩放、矩形裁剪（0046 swap()）；0061 加逻辑坐标系（呈现 1125×2436，面板 1080×2400 居中显示，`fOffX/fOffY` 平移+裁剪），GetDisplaySize 返回逻辑尺寸，HID 触摸坐标同映射（0061 SweetHID.cpp hunk）；
  - 节流：backboardd 60 Hz 提交 × 每帧全屏 10 MB memcpy = 单核 600 MB/s 把整机饿死（boot 0055n，167k swaps），0056 改为 **swap 只记最新记录，vsync 定时器按 `sweetfb_hz`（默认 10 Hz）把最新帧 blit 上屏**；0068 修 IOSurface 已映射 surface lookup 返回 -1（backboardd snapshot 崩）；0079 加 IOMFB sel 12 kern_RequestPowerChange 显示灭/亮（6 个 vsync 渐隐）。
  - vsync：无真 vsync，用 60 Hz IOTimerEventSource 造（type 5 通知，(count, mach_absolute_time, 0) 两个 32 位半字，走 IOConnectSetNotificationPort 注册的 port，`sendAsyncResult64WithOptions(… kIOUserNotifyOptionCanDrop)`）。

### A.5 对我们内核（8796 + PAN + 非苹果 DT）的适配风险清单（问题 5）

| # | 风险 | 事实核对 | 结论 |
|---|---|---|---|
| R-A.1 | ios-sweet = xnu-8796.**0/13.5** 配置 + iOS 16.**7** 用户空间；我们 = xnu-8796.**121.2**（Darwin 22.5）+ iOS 16.**5**（20F66） | `[TREE] VERSION`（XNU = xnu-8796.121.2）；[REPO] sysimage/ `20F66__iPhone10,3_6` | ABI 由用户空间决定；上游 Mini 驱动**就是按 16.5 用户空间反推的**（MiniIOMFB 文件头："worked out from the user-space side of Darwin userland 16.5"）——我们比 ios-sweet 更贴 |
| R-A.2 | 非苹果 DT：ios-sweet 需要 mkadt 造 /chosen/display-scale、/arm-io/disp0、/product | loader.c:3486 已有 scale；disp0 内核运行期发布；/product 来自 identity.h | identity.h 目前仍是 **mkidentity 占位版**（[REPO] docs/STATUS.md 2026-11-08 生态审计 ②；F5 hw.target 树侧真值未做）——**阶段 23 前置或并行项**：`xnuloader/mkidentity.sh` 用在盘的 `sysimage-20F66/work/DeviceTree.d22ap.im4p` 重生成，MobileGestalt 的 /product 属性（ios-sweet 教训：缺它报 "iPod"/布局异常）才完整 |
| R-A.3 | PAN（内核域防问用户内存）：两树都基于 Apple 主线 arm64 pmap，surface 实现全用 IOMemoryDescriptor/copyout，不裸穿 | ios-sweet patch 0006 用 open-source pmap；[TREE] 同族 | 无新增风险；上游已在同类硬件上跑通（见 B.0） |
| R-A.4 | 无 kext 加载设施：ios-sweet 形态是内核内建，无需 kextload | 两树同构 | 风险不适用（这正是选内核内建形态的理由，§B.2） |
| R-A.5 | MiniIOSurface"拒绝"语义 vs ios-sweet"忽略"语义 | [TREE] MiniIOSurface.cpp:8；b25 log 有 sel 40/41 not implemented | 观察项：若 23.x 判定中出现新 "not implemented" 后跟崩溃，放宽该选择器为全零成功（每处 ~5 行） |
| R-A.6 | 颜色域陷阱（非显示服务但同类）：iPhone X 面板 P3 → WebKit 画 'w30r'/'b3a8' 10bit → 全黑页 | [TREE] loader.c:546-559 已改写 `artwork-display-gamut` 为 sRGB（gamut=p3 boot-arg 可还原） | 已解除；勿在 23.x 顺手"修回" P3 |
| R-A.7 | 进程侧坑（ios-sweet 全史）：数据迁移（IOPlatformUUID）、/private/var/containers 目录、HFS RENAME_SWAP、AKS sel 35/101、mediaserverd VirtualAudio、Setup 跳过、pid_hibernate syscall 435、边缘手势 48px FromEdgeTip、PRIV_WORK_INTERVAL entitlement | 上游树各有对应物：launchd 注入（kern_minimac DYLD_INSERT 白名单，`xnu/files/bsd/kern/kern_minimac.c:68`）+ inject_sb.c 强制 SBSetupManager reason 0 + 自带 purplebuddy SetupDone（`userland/mkjobs.py:160-170`）+ bindfs/HFS 树内解 | 已预置；23.x 判定若再撞，按 ios-sweet 的签名表（§B.4）对号 |

---

## B. PHK110 施工单（照单施工版）

### B.0 现状重述（先修正底账，这是本报告最重要产出）

| 证据 | 来源 | 说明 |
|---|---|---|
| `MiniIOSurface: backboardd[16] created surface 1/3: 1125x2436 'BGRA', 4608 bytes per row … 11239424 bytes`；`SpringBoard[12] created surface 4-10 (LA08/BGRA)` | [REPO] `logdump-v14.bin`（Boot #25） | backboardd 建**双缓冲** 1125×2436 BGRA 主 surface；SpringBoard 建资产 surface（锁屏类 LA08） |
| `MiniIOMobileFramebuffer: backboardd[16] selector 4/5/79/50/12`、`MobileGestaltHelper[30] selector 8`（GetDisplaySize）、8 次 `swap N layer 0: surface M (1125x2436 'BGRA') from 0,0 1125x2436 to 0,0 1125x2436` | 同上 | **SwapBegin/SwapEnd 全链真实发生**，GetDisplaySize 已答 1125×2436 |
| `MiniIOSurface: selector 40/41 not implemented`；`MiniIOMobileFramebuffer: selector 84/68/57/55/50 not implemented` | 同上 | 未实现选择器清单（默认回零成功，非致命） |
| `SpringBoard[12:243] <CATransformLayer …> - changing property allowsGroupOpacity …`×若丢、`trying to set state of nil layer`×10、`SpringBoard[12], error = 3: No such process`×492 | 同上 | SpringBoard **活着且在做 CA 工作**（非 crash-loop：同 PID 12 贯穿）；error=3 是对已死伴侣进程的 mach 通信噪音 |
| mini 统计行计数：v13=0，v14=20，v15/v16-final/v17/v17b=42（`frames drawn again filtered` 出自 `MiniIOMobileFramebuffer.cpp:1299`） | [REPO] logdump-v13/v14/v15/v16-final/v17*.bin 实测 grep | **v14 起该栈在每个内核里运行**（v13→v14 之间树被更新到含 Mini 显示的版本；kernel.ver 同串 `-dirty` 掩盖具体 commit，如实标注为"未知，不追"） |
| 上游自身已到主屏：QEMU "black… Apple logo at about one minute, **the home screen at about five**"；redwood 真机笔记含主屏滚动/控制中心/设置、`fbscale=2` 时"峰值 28 帧/秒"、"SpringBoard 早 7 秒就绪" | [TREE] docs/getting-started/qemu.md:38；docs/ru/notes.md:396,365 | "无 GPU CPU 渲染主屏"在上游**等效目标（redwood）上已发生**，PHK110 只差验证与时间窗 |
| b25 从未启用屏录（`recording`/`RWREC` 计数 = 0） | [REPO] logdump-v14.bin grep | 23.x 的取证通道尚未用过 |

### B.1 显示身份（施工单 1）

**结论：loader 侧已就绪，只差 identity.h 重生成（F5 项，非本波新增）。**

| 项 | 状态 | 出处 |
|---|---|---|
| `/chosen/display-scale=3, display-rotation=0` | **已有**（MobileGestalt 主屏缩放真值来源，注释即为此写） | [TREE] xnuloader/loader.c:3485-3487 |
| `/chosen/unique-chip-id + chip-id 0x8015`（IOPlatformUUID/ByHost，ios-sweet 迁移死循环的根） | **已有** | loader.c:3535-3536 一带 |
| `/arm-io`（含 ranges/#address-cells） | **已有** | loader.c:3656 |
| `/arm-io/disp0{display-subsystem,canvas-*}` | **不需要 loader 写**：内核 `publishDisplayNode()` 运行期 attach（compatible=`redwood,framebuffer`，name=disp0） | MiniIOMFB.cpp:1666-1693 |
| 面板 1240×2772 vs 逻辑 1125×2436 | **驱动处理**：逻辑尺寸 = 375×812 pt × scale（MiniIOMFB.cpp:110-113,536-546，从 /chosen display-scale 与 /product artwork-scale-factor 读），`present()/drawRows()` 缩放到 fBase（= vinfo.v_baseaddr = 0xB8000000，:529-532）；`fbwidth/fbheight/fbscale` boot-arg 可改 | 同左 |
| /product 完整属性（MobileGestalt 布局/艺术字缩放） | **待做 = 既有 F5**：mkidentity.sh 重生成 identity.h（输入已在盘）；gamut 强制 sRGB 已有 | loader.c:546-559；[REPO] STATUS 2026-11-08 审计② |

**合法值格式对照表（ios-sweet mkadt ↔ 我们 loader，全部已满足）**：display-scale u32(3)↔u32(3)；display-rotation↔0；canvas-width/height↔（内核发布，等价）；unique-chip-id 8B↔8B；chip-id↔0x8015（两树同为 A11 常数，因用户空间是 iPhone X 的）。**新增 0 行**。

### B.2 虚拟 IOMobileFramebuffer/AppleCLCD：实现形态选择（施工单 2）

三形态评估（前提：无 IOKit 用户客户端基础设施的**说法不成立**——上游树有完整 IOKit 内核核心 + 两个真用户客户端先例：MiniIOSurface、HakiosGPU）：

| 形态 | 评估 | 结论 |
|---|---|---|
| **XNU 内核内建假驱动（GenericARMPE 直启）** | 上游已实现且 b25 已刷入真机（MiniIOMFB 1775 行，选择器覆盖 3/4/5/6/7/8/12/20/25/28/29/52/57/72/73/74/77/79/81/82，其余回零成功；TimingElements 发布修复 refresh=0 类死法；vsync 60 Hz 定时器 + CanDrop 通知；GPU fence 挂钩） | **采用（现状即此）** |
| kext（仿 ios-sweet 独立模块） | 两树都无 kext 装载/签名设施；上游所有"假 kext"（IOSurface/IOMFB/KeyStore/IONetworkStack）都走内建；收益仅模块化，代价是新建 kext 基础设施 | 否决 |
| 用户态服务 | IOMobileFramebuffer.framework 用 IOServiceOpen（内核端口）说话，用户态假服务无 IOKit 注册面；configd 案例（ios-sweet NOTES.md 2026-10-18 段：SCNetworkInterface 需要 IONetworkInterface→controller 的 IOKit 链）反证用户态替身必须配内核 IOKit 桩 | 否决 |

redwood upstream 先例：`MiniIOMobileFramebuffer.cpp` 本身 + `docs/ru/notes.md` 主屏实录 + `docs/metal-plan.md`（GPU 后同样经由该服务）。

### B.3 IOSurface root（施工单 3）

同上结论：**已有** `MiniIOSurface`（注册名 `IOCoreSurfaceRoot`，Apple 同名，framework 无感）。与 ios-sweet 的差异表：覆盖选择器 0-44 vs 0/4/13/34/35；trap 含 Detach；表 16384 vs 4096；单面上限 512 MiB vs 256 MiB；不认识调用**拒绝** vs **忽略**（R-A.5 观察项）；自带成本统计（MiniIOSurfaceCost）与 `surftrace/surftrace_of` 取证。**新增 0 行**；23.x 若判定需要，放宽语义 ~10 行。

### B.4 backboardd/SpringBoard 稳定性判定协议（施工单 4）

全程零交互，单次 boot 产出全部证据（自动 logdump 已有：loader 收尾写 logdump 分区，阶段 7b 起）：

1. **采样**：boot 一次，`loader_return_after=300`（b25 的 120 s 不够 SpringBoard 就绪——上游 QEMU 主屏 ~5 min、真机 SpringBoard 就绪后还需 30-40 s 应用注册；[TREE] docs/ru/notes.md:86）。单份连续内核日志（persistent console log 链路 v14 已证）取 **T+60/T+150/T+280 三窗**：
   - PID 稳定性：三窗内 `exec backboardd` / `exec SpringBoard` 出现次数 = 各 1 次（同一 PID 连续出现 = 稳定；PID 变化或重复 exec = crash-loop）；
   - crash 三日志串（照外援签名）：(a) `CRASH <name>` / ReportCrash .ips 行，(b) `exited …`/`exit reason` 行，(c) 该进程随后再次 `exec` —— 三串齐 = crash-loop 确认；只有 (b) 无 (a)(c) = 单次退出；
   - 中间态识别表：`FBSDisplayMode cannot be configured`（scale/refresh 缺）→ 查 TimingElements/scale；`Failed to create work interval`（PRIV_WORK_INTERVAL entitlement）→ 上游 CAENV/CA_VBL 或补 entitle；`No status bar visual provider for screen`（非 iPhone pt 尺寸）→ 逻辑尺寸须 375×812@3x；`persona`/container EACCES（ios-sweet 0051n 同款）→ containermanagerd 注入是否生效；`IOAccelerator` 轮询静默 = 预期（等待态非死亡）；MiniIOSurface/IOMFB `not implemented` 后紧跟该进程 CRASH = R-A.5 放宽点。
2. **对照（防误判）**：b25 logdump（v14）作基线——同日志位若 b25 已有而本轮变差 = 回归；本轮新增 = 前进量。
3. **出画判定**：cmdline 加 `rec_secs=280 rec_mb=256 rec_ring=1`（kernel 侧现成，[TREE] docs/boot-args.md:80-84；内存教训：640 MB 会挤死进程至 respawn，256 安全，docs/ru/notes.md:355）。自动返回后 `fastboot oem recording`（loader.c:4683-4694 已实现该 handler）→ `xl recording out.mp4`（[TREE] xl:267-270）→ `tools/recording.py`（RWREC003 解码，tools/recording.py）出 mp4/逐帧 PNG。**验收 = 帧序列出现锁屏/主屏内容**（无需盯着手机；若在场目视面板亦可作旁证）。
4. **备选静帧**：`oem screenshot`（loader.c:4673-4681，stage 原始 framebuffer，`getvar screen` 给几何）。

### B.5 CPU 渲染出画路径（施工单 5）

**谁做 blit、什么时候、怎么转换（全部现成，含文件:行）**：

```
[进程] SpringBoard/CoreAnimation (CPU 渲染器 CA::OGL::SWContext)
   │  画进 IOSurface（MiniIOSurface wired 内存，每客户 createMappingInTask 映射）
   ▼
[进程] backboardd（窗口服务器合成各层）
   │  IOMFB 用户客户端: sel 4 SwapBegin → sel 5 SwapEnd(0x46c 记录: 层掩码+每层 surface id+源/目标矩形)
   ▼
[内核] MiniIOMobileFramebuffer externalMethod sel 5 → swap 线程队列（fb_queue=2）
   │  等该 surface 的 GPU fence（无 GPU 时 fence=0 立即过；有 GPU 时 hakios_gpu_done, :1164）
   ▼
[内核] present() → drawRows()（fb_threads=3 个 pri=92 线程并行）
   │  BGRA 8bit 逐层缩放: fb_filter=2 = 帧流动时 nearest(1.7ms/帧)、静止 40ms 后 bilinear 重画
   │  逻辑 1125×2436 → 面板 1240×2772（fBase=vinfo.v_baseaddr=0xB8000000, v_rowbytes）
   ▼
[硬件] ABL/UEFI SimpleFb 留下的 DPU 连续扫出 0xB8000000（无需刷新 kick，同 ios-sweet "continuous splash"）
```

格式转换：只有 BGRA→BGRA 与分辨率重采样（无 tile/压缩/YUV 路径；LA08 等 client 侧格式在合成时已被 CA 消化）。节流默认 fb_hz=60 上游值；我们可先 `fb_hz=30` 减 CPU 争用（ios-sweet 同参数），`fbscale=2` 为后备降载（上游真机 19→28 fps，代价是顶部红条=服务性提示，可接受作对照轮）。console 叠加：上游内核 console 与 GUI 共存由 fb_pri/静音机制处理，无需 sweetfb_noconsole 等价物（23.x 若见文字叠帧，查 console 静音 boot-arg 再定）。

### B.6 分波方案（施工单 6）

**阶段 23.x — 虚拟显示环境确认 + 出画取证（一刷，几乎零代码）**
- 内容：①（可选前置/并行）F5 identity.h 重生成 + loader 重编（不计入本波行数，属既有 F5）；②payload cmdline 追加 `rec_secs=280 rec_ring=1 rec_mb=256 surftrace=24 surftrace_of=backboardd fb_hz=30 loader_return_after=300`（预算余 228 字符，实测增量 ≈ 105 字符，余 ≈123，够；超则去 surftrace_of）；③payload 双 ramdisk/镜像不动；④刷一次，收 logdump + `oem recording`，跑 §B.4 协议。
- 验收：A 级 = 录屏帧含锁屏或主屏内容且 SpringBoard/backboardd 各 exec 一次；B 级 = swap/CA 行较 b25 增多且无新 crash-loop（进 23.y）；F 级 = 同 b25 无进展 → 转 23.y 逐坑修。
- 风险：驻留 300 s 内 vnode 满（预存 F6 218 s 教训，cmdline `loader_return_after=300` 与 F6 阈值关系需在波内先核对 v17 的 vnode 参数）；rec_mb 挤内存（用 256）；面板背光/用户观感不在验收内。
- 行数：cmdline/脚本 ≈ 60-100（mkpayload 侧 + 取证脚本），内核 0，loader 0。

**阶段 23.y — 进程稳定（按判定修，滚动一刷/判定循环，最多 2-3 刷）**
- 候选修法按 §B.4 中间态表：MiniIOMFB/MiniIOSurface 补选择器（每个 ~5-15 行）或放宽"拒绝"→"回零成功"（~10 行）；PRIV_WORK_INTERVAL entitle（inject.c/CAENV，~10-30 行）；containermanagerd/persona 注入核对（0 行，查 inject.conf 是否进我们镜像——b25 已含 INJECT 串，验证即可）；若撞 `Failed to create work interval` 与 SpringBoard 就绪延迟相关，开 `CONFIG_CA_VBL/CAENV`。
- 验收：三窗 PID 稳定 + crash 三日志串为 0 + `SWEET`/Mini 错误行清单较基线单调减少。
- 风险：每轮刷写消耗 flash 预算（协议：先 logdump 判定再决定重刷，避免无效刷）；个别坑可能溯源到 16.5 vs 16.7 差异（对表 ios-sweet 修法时注意版本差）。
- 行数：内核 30-80，镜像 0-40，脚本 0-30。

**阶段 23.z — CPU 渲染出画宣告 + （可选）输入闭环**
- 内容：A 级达成后：屏录 mp4 归档 + 波报告；可选输入闭环 = 阶段 12c 遗留"真人点屏"（S3910 finger 事件 → /dev/hakios-touch → inject.c 虚拟 HID → 解锁滑动），或用上游 `rwtouch`（脚本化触摸，`[TREE] userland/root/bin/rwtouch`）做零交互解锁验证。
- 验收：主屏可交互（z 级）或出画宣告（z0 级）。
- 风险：输入链跨 S3910（阶段 12 真实指点未取证）+ inject HID 两条未合拢链，z 级可能拖；故 z0 先行宣告。
- 行数：脚本 50-150，内核 0-40（触摸坐标映射若有偏差：MiniIOMFB/触摸侧各 ~10 行）。

---

## C. 战略判断

### C.1 值得插到 v0.5 GPU 战之前吗？——值得，且**没有依赖倒置**

- **这不是"另一条路"，是同一条路的正名**：任务书所称"虚拟显示层将来要被真 GPU 替换"的假设与上游设计相反——GPU 到来时**换的是渲染器不是呈现器**：
  - 呈现链（IOSurface → MiniIOMFB swap → panel memcpy → 0xB8000000）原样保留；MiniIOMFB::swap 已有 GPU fence 等待与超时降级（`"the GPU is not done with surface %u after %u ms; shown as it is"`，MiniIOMFB.cpp:1164；fence 源 `drivers/gpu/hakios.gpu.cpp:484`）；
  - GPU 侧入口是 HakiosGPU（msm DRM 接口给 Mesa freedreno；`kHakiosSurface=0x7e` 让 GL 直接把 IOSurface 内存当绘图缓冲，`kHakiosShow=0x7f` 内核测试出画，`drivers/gpu/hakios.gpu.cpp:19-23,85-86,795`）；Metal 路径 = 假 IOAcceleratorES 加上 MetalPluginName 两属性（metal=1，MiniIOMFB.cpp:1712-1720，默认关——"until that device can draw, a screen drawn without it is the working one"）；
  - 实证：上游 redwood 就是先 CPU 主屏、后 GPU（GL=1 实机、Mesa a7xx 组合），两阶段共用同一 MiniIOMFB。
- **v0.5 反而需要 23 先通**：GPU 战的可视验收（"Metal/GL 画的桌面"）以 23.x 的出画取证通道为唯一零交互判定手段。
- **成本对表**：23.x 一刷 ≈ 纯 cmdline；而 v0.5 GPU 战 = 固件 + 寄存器bring-up + SMMU + Mesa 适配（量级 10³ 行）。先摘 23.x 这个"几乎免费的大里程碑"再攻 GPU 是明显占优序。

### C.2 与 阶段 22（host visibility / SSH 数据面）的顺序建议

- **23.x 插在 阶段 22 继续集中修复之前**。理由：
  1. 阶段 22 的 host-visibility 是硬件向集中修复（v17 证据链：UEFI 相位 gadget ep0 不应答 = 无 host 预期态；修复面 = loader ~10 行 pump + 重枚举联动， outcome 不确定，消耗 flash 预算 2/2 已用完待回款）；而 23.x 不依赖它——取证走**既有 fastboot 命令通道**（logdump 自动拉取链路 b17→b35 全程工作；`oem recording` 同通道）。
  2. SSH 数据面（阶段 21 方案 A：loader 桥接网络）的 start_ex 阻塞正是 阶段 22 要修的东西；23.x 与之零耦合。
  3. 里程碑价值：23.x 若 A 级 = **v0.7 级"看见 iOS 桌面"**，是项目首个可视化大件；先拿它再回去啃 USB 硬骨头，士气与风险曲线都更优。
- **建议序**：阶段 23.x（一刷取证）→ 阶段 23.y（按判定滚动，可与 阶段 22 交替刷——两者都走"刷写→自动返回→logdump"同一循环，互不占道）→ 阶段 23.z0 出画宣告 → 阶段 22 继续或 v0.5 GPU 开战（由 23.y 结果定：若 23.y 只剩性能/交互级问题，GPU 战优先级提高，因为 Metal 渲染也依赖同一出画链）。

### C.3 与外援结论的对表（签名 → 我们的现成解）

| 外援发现（ios-sweet） | 我们的现状 |
|---|---|
| 虚拟 AppleCLCD/IOMobileFramebuffer + IOSurface 后两进程只启动一次 | 同构栈（Mini*）已在树内且 b25 已服务 backboardd；display-scale/rotation/timing 全齐 |
| backboardd 找不到 GPU 进入等待不死 | 同样成立，且上游假 IOAcceleratorES 把 30 s 等待也消了 |
| /chosen/display-scale=0 → FBSDisplayMode 崩 | loader.c:3486 早已 =3；MiniIOMFB 还把它回写进注册表供 MobileGestalt |
| CPU 渲染回退自然发生（无显式触发） | 同（上游更把选择面做成确定性的） |
| 迁移/UUID/容器/RENAME_SWAP/AKS 等进程坑清单 | 上游 inject/镜像/树内解一一对应（R-A.7），b25 未现致命项 |
| （ios-sweet 缺）屏录取证 | 上游 rec_secs→oem recording→recording.py 全链现成，b25 未用过（23.x 主取证手段） |

---

## 附录：出处与未决

**主要出处**（全部本报告内已带文件:行/URL 级引用）
- [SWEET] README.md；NOTES.md:5-32,57,66,84-86,96,98,112-116,156；xnu/patches/0046,0056,0058,0061,0079；tools/mkadt.py:104-108,186-189
- [TREE] xnuloader/loader.c:546-559,3485-3487,3535-3536,3656,4673-4694；xnu/files/iokit/Kernel/{GenericARMPE.cpp:302-305, MiniIOSurface.cpp:1-120,836-854, MiniIOMobileFramebuffer.cpp:96-113,150-190,470-546,588,586,741-1031,1164,1299,1650-1693,1697-1760}；xnu/hakios.patch:1929-1944；drivers/gpu/hakios.gpu.cpp:1-40,85-86,484,795,1200-1201；drivers/{core,gpu}/conf；xnu/files/bsd/sys/hakios.input.h:1-30；xnu/files/bsd/kern/kern_minimac.c:68；userland/src/inject.c:1-26；userland/build.sh:122-134；userland/mkjobs.py:160-170；userland/root/{etc/inject.conf,LaunchDaemons/com.apple.backboardd.plist,bin/rwtouch}；configs/common_defconfig:345-349,1088-1112；docs/boot-args.md:28-84；docs/getting-started/qemu.md:25-60；docs/concepts/architecture.md；docs/ru/notes.md:86,355,365,396；VERSION
- [REPO] logdump-v13/v14/v15/v16-final/v17/v17b.bin（grep 实测）；docs/STATUS.md（阶段 20/21/21.5 条目）；docs/waves/wave22-host-visibility.md（存在，待执行）

**如实交代的未决**
1. v13(0 条)→v14(20 条) Mini 统计行的树版本跃迁点无法从 `kernel.ver=…-dirty` 判定（不追，不影响结论：v14 起在跑）。
2. b25 的 8 次 swap 是否肉眼可见地上了面板：未取证（当时未开 rec_secs）；23.x 即为此而设。
3. b25 `SpringBoard error = 3 ×492` 与 `nil layer ×10` 的归属（BKS 对已死伴侣进程的 mach 噪音 vs 真问题）：未定性，23.y 判定协议覆盖。
4. 上游 redwood 主屏时点和 PHK110 8 核（A710×3+X2）下的可达帧率：无实测，23.x 屏录顺带产出。
5. ios-sweet 的 CA 渲染器选择逻辑未被其作者完全逆向（分类器截断），上游亦以工程手段绕开而非逆向——SW 渲染"如何被选中"的最后一层机制两边都靠实证而非完备理论，如实记录。
