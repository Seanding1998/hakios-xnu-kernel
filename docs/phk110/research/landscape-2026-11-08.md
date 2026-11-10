# 同类项目生态盘点与进度基线（2026-11-08）

> 执行：生态专项调研。方法：exa 网络检索（中英文交叉）+ 本仓文档只读 + WSL 构建树/20F66 sysimage 只读取证。
> 红线遵守：**零手机交互、零构建、零 clone**（只 grep/strings 本地已有文件）；仓库只写本报告 + STATUS 队列行。
> 一句话：**v0.4 卡点（launchd `failed to query hardware target: 22`）的源头已在本仓证据内定位**——loader 的 identity.h 是 IPSW 到货前的占位符；生态侧无此问题的现成公开解，但有完整的同构方案（UniXNU MobileGestalt 身份契约 / vphone DT 风险分级）为修复路径背书。

---

## 1. 进度审计：我们在哪（基线节）

### 1.1 版本里程碑（STATUS.md / PLAN.md 口径）

| 版本 | 状态 | 达成点 |
|---|---|---|
| v0.1 黑匣子 | ✅ Boot #12（2026-11-03） | UEFI→loader→XNU→用户态 hello 全链 + 26,846B 日志取证，GICR stride 修复 |
| v0.2 第一缕光 | ✅（随 udon 底座顺带） | udonPkg 原生 NT37705 显示栈，1240×2772 出画 |
| v0.3 触感 | ✅ Boot #13–21（2026-11-03） | 常驻 300s 零 panic / 8 核同起 / SPMI v7 按键真机事件 / S3910 TouchComm v1 probe PASS（20ms 节拍 + 9 字节分帧收割） |
| v0.4 达尔文 | 🔄 进行中（存储战完毕） | 物料锁定 20F66 → UFS S0–S2（Boot #22）→ P0 carve + 12G HFS+ 数据卷（阶段 16c，全 adb 通道）→ S3–S8 两刷完成（Boot #23 v12 / Boot #24 v13）：真实 init 链、system.apfs 换根、双 cryptex 步进、dyld 共享缓存跑通 hello_dyn、**Apple launchd 接管 pid 1 → 0.6 s 后 `failed to query hardware target: 22` 退场**（§2 专项已定位） |
| v0.5 图形 / v0.6 连接 | 未启动 | 主路线 freedreno（§3-I：Mesa 26 时代 a730 实证面更宽）；WiFi = ath11k_pci 路线（WCN6750） |

### 1.2 真机启动台账

STATUS.md Boot 表在案 **24 次（#1–#24，截至 2026-11-04 快照）**；任务简报口径"25 次"未见第 25 次记录，按文档为准。零变砖、boot_a 原厂未动、v11 stub 镜像为救援回退首选，A/B fallback 安全网全程有效。

### 1.3 技术资产清单（可复用大件）

1. **bitbang TCM 触摸驱动**（S3910，TouchComm v1）：GENI 引擎探活 → FIFO 禁用自动降级 bitbang → v1 帧分帧收割 + 20 ms 重武装节拍；probe 全链 ~1.0 s；真人点屏验证待做（v10f 三件已备脚本）。
2. **SPMI v7 按键链**（taro 仲裁器）：power/volume 三键毫秒级取证；RPMh 双轨上电（PON/GPIO channel 逐字吻合）真机验证。
3. **UFS mailbox 栈**（hakios.ufs.c/ufshc.c 经 loader 页 faa41000 + 4096 KB buffer）：只读 129/130 分区发布 + darwin 写路径（12501 MB）+ ufs_check FNV 16/16 @ ~500 MB/s（R1/DALSYSDxe 清白）。
4. **loader 桥接网络方案**（阶段 19 方案 A，阶段 21 待建）：共享页 net 环 + 内核 en0 link 驱动 + loader `oem netrx/nettx` + 阶段 13 loader_talk.py 扩 ProxyCommand；生态对照见 §3-D（Bergamota CDC-ECM 证明真 USB 网卡可行但其内核有 USB 栈，我们否决内核 gadget 的理由不变）。
5. **P0 双系统工具链**（已 PHK110 化并实测）：userdata-carve-phk110.py / darwin-write-phk110.py / p0-carve-run.sh / mkdatavol 同源（上游 v0.8 工具家族见 §3-A）。
6. **取证与通道资产**：logdump 落盘回读链、WSL Linux adb + `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037` 复用配方（CRLF footgun 已记录）、graft 验收 + N 项自检流程。
7. **20F66 sysimage 全套**（rootfs + cryptex-os/app + trust cache + var.skel + `DeviceTree.d22ap.im4p`）——最后这件是 §2 修复的关键输入，已在盘。

### 1.4 生态横向定位（我们在地图上的位置）

- **上游 HakiOS（redwood 参考机）**：全 UI + GPU GL=1 + Metal ~110 fps + Wi-Fi + HFS+ /var 持久化 + U-Boot 双系统（§3-A）。同内核、同代用户态——我们落后其约"一个生态位"（他们的 launchd 全通依赖的正是我们没有的那步，§2）。
- **UniXNU-udon（同款 PHK110，takasugl）**：iPadOS 17.7.11 → 117 进程 / 176 s，卡 ReportCrash（7 个信号退出未解）；Native UFS root ✅、32 MiB APFS RAM Data seed（§3-B）。**我们已在这台机器的公开记录上走得最远**（launchd 真身接管 + 双 cryptex 步进），且我们与他们是不同用户态（iOS 16.5 iPhone X vs iPadOS 17.7.11 iPad7,1），不构成冲突。
- **ios-sweet（SM7150）**：与我们同为 `fastboot boot` + iPhone X 16.x 用户态路线，已到主屏（CPU 渲染 20–30 fps，无 GPU）（§3-C）。

---

## 2. 专项定位根因：launchd `failed to query hardware target: 22`（本报告最高价值产出）

### 2.1 证据链（全部本地只读取证 + 公开资料交叉，每步给文件/行号或链接）

| # | 证据 | 出处 |
|---|---|---|
| E1 | 20F66 rootfs `sbin/launchd`（525,088 B）中 **`hardware target` 字符串 0 命中** | `grep -aoc` 实测（WSL `~/hakios/sysimage-20F66/work/rootfs/sbin/launchd`） |
| E2 | rootfs `usr/lib/dyld` 中存在完整字符串组：`hw.target` / `hardware target string too long: actual = %lu, expected < %lu` / **`failed to query hardware target: %d`** / VM 回退值 `x86legacyap`、`unknownap` / 相邻 boot-info 标签（`initproc`、`root device info`、`can haz debugger`、`single user`、`userspace reboot`、`secure boot level`、`security.mac.img4.ignition_blob`、`XPC_USERSPACE_REBOOTED`） | `strings -a` 实测（同目录）；该字符串组与 arianvp 公开的 macOS ignition strings（`libignition`，无此句）互补，定位到 iOS 16.5 pid-1 引导家族代码 |
| E3 | xnu-8796.121.2 内核：`pexpert/arm/pe_init.c:432-436` 从 SecureDT 根读 `target-type` → `gTargetTypeBuffer`（读不到则保持空）；`bsd/kern/kern_mib.c:502` `case HW_TARGET:`（同 :525 `case HW_PRODUCT:` 模式）——**PE 取不到串即 `return EINVAL`**；`:999` `SYSCTL_PROC(_hw, HW_TARGET, target, … CTLFLAG_MASKED …)` 注册 `hw.target` sysctl | WSL `~/hakios/kernel/xnu-src/xnu-8796.121.2/`（逐行读过） |
| E4 | 我们构建树的 `xnuloader/identity.h` = **`mkidentity.py --placeholder` 占位版**：`/* placeholder: no properties (built without an IPSW) */`，`identity_root[] = { { "hakios-placeholder", 0, 0 } }`，四张身份表（root/product/haptics/camera）全为空，`grep -ac 'target-type'` = 0 | WSL `~/hakios/kernel/xnuloader/identity.h`（全文读过） |
| E5 | `mkidentity.sh` 用法注释：正常模式 = 从 IPSW 的 `DeviceTree.d22ap.im4p`（或整个 IPSW）生成 identity.h；**`--placeholder` 语义 = "an Apple-free user space, not Darwin"**——即占位版官方明示不支持 Darwin 用户空间 | WSL `~/hakios/kernel/xnuloader/mkidentity.sh` 头注释 |
| E6 | loader 侧意图存在但数据缺位：`loader.c:3283` 注释"identity is the iPhone's (model, compatible, target-type …)"，`dt_identity(&w, identity_root, …)` 在 3287/3380/3388/3398 行调用——写入的是 E4 的空表；`chosen` 侧 random-seed/dram-base/size/display-scale=3/chip-id 0x8015(A11)/board-id 6/unique-chip-id/boot-manifest-hash（"redwood" 占位 48B）等常量另有写入 | WSL `~/hakios/kernel/xnuloader/loader.c`（3265–3340 逐行读过） |
| E7 | 在机 loader.efi 血统：v13 = v11 提取件 = v10e = … = **v6 时代构建（2026-11-02）**；IPSW 20F66 入库 = 2026-11-03（阶段 14）。即：**loader 构建时 IPSW 尚不在库，identity.h 只能是占位版**（STATUS.md 关键镜像清单各行"提取件原样"链） | STATUS.md Boot 表 + 镜像清单；阶段 14 记录 |
| E8 | 生态同构证据：UniXNU 官方文档 **`target-type`（ADT 根属性）→ sysctl `hw.target`**、`model` → `hw.product`/`hw.machine`（MobileGestalt identity 表）；UniXNU ADT 契约要求 `/chosen` 的 random-seed/unique-chip-id/chip-id/boot-manifest-hash 等，缺失的后果各有专述（chip-id 缺 → `gethostuuid(0)` 永久等待——与我们 b24 未卡此步一致） | unixnu.com/guide/mobilegestalt、unixnu.com/porting/device-tree |
| E9 | vphone 研究文档独立佐证："**hardware target reports as vphone600ap**"（= DT `target-type`/`compatible` 身份链的运行时读数），并给出 DT 身份属性改写的风险分级（`compatible[0]` 动不得——IOKit 平台专家绑定第一项，改名必 panic） | lakr233/vphone-cli research/firmware_manifest_and_origins.md |

### 2.2 根因定性

**在机 loader.efi 内嵌的 identity.h 是占位版 → ADT 根节点没有任何 Apple 身份属性（含 `target-type`）→ 内核 `pe_init.c` 初始化时 `gTargetTypeBuffer` 保持空 → pid-1 引导家族（dyld/launchd 侧）查询 `sysctl hw.target` → kern_mib.c handler 对空串返回 EINVAL(22) → "failed to query hardware target: 22" → 进程退场 → `panic: initproc failed to start`。**

- 归因注记（诚实边界）：E1+E2 只证明字符串载体在 dyld 侧而非 sbin/launchd，**发起查询的确切用户态二进制未逐帧证明**（需 launchd 段日志/崩溃帧）；但 E3 的内核机制（空串→EINVAL）与 E8/E9 的生态契约共同锁死因果链，修复路径不依赖该归因细节。
- 与 b24 日志完全吻合：0.6 s = launchd 起来 + ignition 完成 cryptex graft（c=1 @2361 MB / c=2 @4961 MB 均成功，说明 dyld/共享缓存/信任链工作正常）→ 首次触发 `hw.target` 查询即退场。
- **上游 redwood 为什么没这个问题**：他们的构建流程在 IPSW 在场时跑 `mkidentity.sh`（mkidentity.sh 头注释："The header is not in the repository … from their own copy of the firmware"）——身份表按苹果合规要求在构建者本机生成；我们 11-02 构建 loader 时 IPSW 未到货（11-03 才入库，阶段 14），走了占位分支。**这不是上游 bug，是我们构建序列缺一步。**

### 2.3 修复候选（阶段 20，供后续采纳；未执行任何构建）

```
# 1. 身份输入已在盘：~/hakios/sysimage-20F66/work/DeviceTree.d22ap.im4p
# 2. 重生成 identity.h（mkidentity.sh 无参 = 找 sysimage/DeviceTree.d22ap.im4p 或 $IPSW）
cp ~/hakios/sysimage-20F66/work/DeviceTree.d22ap.im4p ~/hakios/sysimage-20F66/
cd ~/hakios/kernel && xnuloader/mkidentity.sh     # 四张表（root/product/haptics/camera）一次补齐
# 3. 重编 loader.efi（xnuloader/build.sh）→ mkpayload → repack → v14 第一次刷写
```

- 预期直接效应：`hw.target`/`hw.model`/`hw.product` 有值 → EINVAL 消失 → launchd 越过 0.6 s 关口（下一步卡点未知，但物证链往前推一节）。
- 预期间接效应：MobileGestalt 的 `MGCopyAnswer` 全链（Settings About、序列号/MLB 占位、display-scale）拿到真数据——identity_product/haptics/camera 三张占位表同一命令一并修复。
- 风险与回归：loader.efi sha 变化 → 按既有流程全量自检 + graft 验收（阶段 19 R-A4"loader.efi 需同刷"已知）；`compatible` 属性由 mkidentity.py 从 D22AP 原版 DT 抄录，符合 E9 的"compatible[0] 绑定平台专家"约束（内核是我们自己的，AppleDT kext 匹配路径无 Apple 原版 kext 可匹配，风险低于 vphone 场景）。
- 验证行建议：内核日志无 `failed to query hardware target`；可用 `sysctl hw.target`（sshd 通后）交叉验证取值 = D22AP 家族字符串。

### 2.4 为什么搜不到现成解（生态检索结论）

- grep.app 全库 `"failed to query hardware target"` = **0 结果**；oosexgang/hakios-xnu-kernel issues 搜 `hardware target` = **0 结果**；HakiOS 官网文档/CHANGELOG 无此错误条目（检索记录 2026-11-08）。
- 结论：该错误在公开生态**零文档**——ios-sweet 家族把 `hardware_target` 当**构建变量**（MeowTech/ios-beryllium workflow：`hardware_target=beryllium`，构建期选身份集），说明他们同样意识到身份必须构建期喂对；UniXNU/vphone 从正面（ADT 契约）与反面（DT 改写风险表）给出了完整的身份方法论。**本专项的正确策略是"对照法修复"，无需发明任何新机制。**

---

## 3. 同类项目普查表（2025 下半年 – 2026-11-08）

> 证据等级：**实证** = 有日志/照片/可复现仓库；**宣传** = 无可验证证据。
> 相关度：高 = 当前阶段直接用得上；中 = 战略储备/对照；低 = 生态背景。

| # | 项目 | 仓库/主页 | 最新动态（日期） | 相关度 | 证据 | 一句话 |
|---|---|---|---|---|---|---|
| A | **HakiOS 上游** | github.com/oosexgang/hakios-xnu-kernel（1930★/332F）+ hackios-web.vercel.app | 2.3.4（11-05）；U-Boot 双系统（10-29） | **高** | 实证 | 我们的直接上游；Metal 110 fps + HFS+ 持久化 + boot_a 菜单双系统全套 |
| B | **UniXNU** | github.com/UniXNU/UniXNU + unixnu.com（~2.1k★） | sheng 全 UI + GPU Metal 组合；udon 官方页 | **高** | 实证 | OpenCore 式 UEFI + 234 机目录；**MobileGestalt/ADT 身份契约 = §2 修复背书** |
| C | **ios-sweet** | github.com/dipa-studio/ios-sweet | 主屏达成（10-18） | **高** | 实证 | 同路线最近亲：SM7150 + iPhone X 16.7.16 用户态 + Hactivation |
| D | **Bergamota** | github.com/ry-diffusion/Bergamota | iOS 18.7.8 SpringBoard（xnu-11215.81.4，10-23 起） | **高** | 实证 | **Renegade arm64e→arm64 全量重写器** + CDC-ECM USB SSH |
| E | MeowTech/ios-beryllium | github.com/MeowTechOpenSource/ios-beryllium | launchd PID 1 确认（10-22 前后） | 中 | 实证 | ios-sweet fork；`hardware_target=` 构建变量旁证 |
| F | **vphone** | github.com/lakr233/vphone-cli | 研究文档活跃（2026-10/11） | 中 | 实证 | PCC 壳包 iPhone 虚拟机；**DT 身份 13 属性风险分级表** |
| G | Corellium / Project Sandcastle | projectsandcastle.org | Sandcastle 停滞；商业平台 7.14.0（10-08） | 低 | 实证 | 方向已反转（iPhone 跑 Android）；闭源商用不可借鉴 |
| H | Mu-Silicium / MU-Qcom | github.com/Project-Silicium/Mu-Silicium | v4.1（11-01） | 中 | 实证 | 我们的 UEFI 底座上游；Exynos 大扩张；**udon 仍无 Windows entry** |
| I | **Mesa freedreno/Turnip** | docs.mesa3d.org + 社区构建 | 26.0.0（02-11）/25.3.3（01-01） | **高** | 实证 | **Adreno 730 GL/GLES/Vulkan 实测全通**（Linux 侧）；a7xx 修复大批 |
| J | Procursus | github.com/ProcursusTeam/Procursus | 最后 commit 05-30 | 中 | 实证 | OpenSSH pin 9.7p1 不变；阶段 17 /jb 物料无需变更 |
| K | **中文圈（K20 Pro 常驻固件等）** | 酷安打包 + B站 + IT之家/smzdm | 固件包 11-03 报道 | 中高 | 实证 | raphael/SM8150 HakiOS 常驻 + 双系统 Magisk 模块；三系统视频 18 万播放 |
| L | LightTouch | gametechwiki 条目 | Windows 启动器未完 | 低 | 宣传 | 全系统 iOS 模拟器（launchd/锁屏/Home）；互证 launchd 可满足 |
| M | 外围移植尝试 | scion-starlte（Galaxy S9 Exynos 9810）、HD2 iOS 7（j0sh1x，10-07）、Pixel 6/Galaxy S7 尝试 | 10 月 | 低 | 实证/宣传混合 | HakiOS 已被移植出高通域（Exynos）；Tensor/Exynos 老机未成 |

### 分项目详情与可借鉴物

**A. HakiOS 上游（oosexgang）——相关度：高**
- 动态：①改名 HackiOS→HakiOS（10-30，商标合规重构；仓库重组为 kernel + per-device + uefi + metal 四仓；Telegram 公告 licensing 大重构）；②**2.3.4（11-05）**：Metal pipeline variant 邻近匹配修复（壁纸红顶/状态栏白带）、触摸 lift 5 ms（原 88–169 ms）；③**U-Boot v2026.07 自研引导（10-29）**：boot_a 菜单（Android 10 s 默认/HakiOS/fastboot/U-Boot shell），`hakios sum`/`hakios reboot bootloader`；HFS+ 数据卷落 `darwin` 分区（~12 GB journaled 跨重启）；**loader 接受任意手机的 darwin 分区（name/type/unit，≥20 GiB）**；GL=1 GPU + `fb_hz=120`；Wi-Fi 控制器寻址修复（ios-sapphire port 发现）；④新设备：`hakios-mt6768`（Infinix Hot 20，MTK Helio G85，自带 loader，实验）+ 社区 scion-starlte（Galaxy S9/Exynos 9810，非 UniXNU 树）；⑤SEP 加进 mtk 分支（hackios.net 11-05 15:13 UTC）；⑥`tools/hakios-device.py new` 一键生成设备仓。
- 可借鉴物：v0.8 双系统全套（见 Top 3 #3）；Metal 双路径架构（hakios-metal 直编 AIR→NIR→ir3 为主 + UniXNU AdrenoMetal/metal2vulkan 为辅，`tools/mk-m2v.sh` 已可直接拉取构建——v0.5 备选路线同款）；CIMetalDeviceGetLimits 的 `dedicatedMemorySize/sharedMemorySize` 必答教训（缺则 CIContext 全炸，iconservicesagent 死）。
- 出处：hackios-web.vercel.app/en/changelog、/en、/en/docs/comparison、/en/docs/dual-boot、/en/docs/metal-plan、t.me/s/oosexgangdevs、hackios.net/en/news。

**B. UniXNU（takasugl / UniXNU org）——相关度：高**
- 动态：①**sheng 参考机（SM8550）**：iPadOS 17 全 UI + **GPU Metal 组合验证**（AdrenoMetal = `MTLAddDevice` → metal2vulkan AIR→SPIR-V → Turnip NIR→IR3 → 内核 NativeAdreno 驱动；"GPU composition verified on sheng with A740"；preempt mode 2 双 ring、GMEM transient-attachments patch、pipeline 缓存复用全公开）；②**macOS 26.5 on sheng**（CrossDarwin/macOS-ForSheng，XNU 12377.121.6 ARM64E，基于 UniXNU + Snapintosh）；③iOS 27 profile 活跃维护；④**udon（我们同款）官方设备页**：iPadOS 17.7.11 (21H461) → **117 进程 / 176 s**，Native UFS root ✅、dyld cache `54 files/62 mappings/kr=0`、32 MiB APFS RAM Data seed、180 s 诊断定时器；**卡 ReportCrash（7 个信号退出未解）**；GPU/audio/WiFi/suspend 未动；⑤外围扩张：Odin3（SM8750 手持，microSD 启动 + OpenABL）、Orange Pi 5（RK3588）、Nothing Phone 3a（SM7635）。
- 可借鉴物：**MobileGestalt identity 表 + ADT 契约**（§2 修复背书 + 我们未来任何"改身份"需求的权威手册）；GPU 参照（AdrenoMetal MIT，上游 HakiOS 已采纳同款）；`UNIXNU_UNIQUE_CHIP_ID` 平台种子实践；udon 页的 porting.toml 证据制方法论。
- 诚实边界：udon 页明示未达完整 UI；pbxscience 独立评测确认其"先开源后宣布"的信誉结构，但 Metal 首创声明未独立确认。
- 出处：unixnu.com/devices/udon、/devices/、/guide/mobilegestalt、/porting/device-tree、/porting/gpu、/drivers/adreno-metal、github.com/takasugl/UniXNU-udon、github.com/UniXNU/UniXNU-sheng、github.com/UniXNU/AdrenoMetal、github.com/CrossDarwin/macOS-ForSheng、github.com/darkplace/UniXNU-Odin3、pbxscience.com 评测。

**C. ios-sweet（dipa-studio）——相关度：高**
- 动态：2026-10-18 到 iOS 主屏（锁屏/设置/控制中心/通知中心/触摸/实体键）；iOS 16.7.16 (20H392) iPhone X (iPhone10,3/D22AP) **未修改用户态**；存储 = 自写 UFS 驱动 + userdata 内 journaled HFS+ root 读写；显示 = 内核 IOSurface + IOMobileFramebuffer（AppleCLCD）服务、CoreAnimation 软渲、帧拷贝进 bootloader fb；触摸 Goodix GT9896 I²C(GENI) + RPMh 供电 → HID digitizer；电池 IOPMPowerSource（静态 100%）；激活 = mobileactivationd 原生 **Hactivation**（DT security status 选择，零 Apple 服务器）；构建 = GitHub macOS runner（blacktop/darwin-xnu-build）。
- 可借鉴物：①内核 IOSurface+IMFB 服务设计 = 我们 v0.5 显示集成（WSI 之前）的对照实现；②Hactivation 路径 = Apple 服务边界的既成先例；③fork 生态情报（Android Authority：Redmi Note 12 Pro fork 声称 sound/WiFi/wallpaper 可用——**宣传级**；LG V60 官方 fork；Pixel 6 Tensor/Galaxy S7 尝试未成）。
- 出处：github.com/dipa-studio/ios-sweet、androidauthority.com（10-21）、decrypt.co（10-19）、xiaoyi.vc / jam.kim（中文报道 10-19/20）。

**D. Bergamota（ry-diffusion）——相关度：高**
- 动态：Poco F1（SDM845）跑 **iOS 18.7.8 (22H352) iPhone XR (iPhone11,8) 用户态到 SpringBoard**；内核 xnu-11215.81.4（iOS 18 代，10-23 换代）；**Renegade**：把每个 arm64e Mach-O 和整个 dyld shared cache 重写为无 PAC CPU 可跑（Poco F1 无 PAC）；USB **CDC-ECM 网卡**：SSH `root@192.168.7.2` + UDP 5140 内核日志 + Mac 侧共享网络；Enxerto 引导（boot 分区 logo/进度条/自带 fastboot/关机充电屏）；电池真实 fuel gauge；进行中 = Adreno 630 GPU（freedreno GLES → Metal）。四件套：Bergamota（Mac 控制面）/ Enxerto（引导）/ Heartwood（内核）/ Renegade（补丁器）。
- 可借鉴物：①**Renegade = 我们未来上 18.x 代用户态（arm64e IPSW）的唯一公开钥匙**（战略储备，Top 3 #2）；②CDC-ECM 数据面 = 阶段 21 方案对照（他们内核有 USB 栈，我们的 loader 桥接决策不变，但其 `ssh -o ProxyCommand` 用户体验目标一致）；③ing 出货纪律（identity 文件、BUILD 文档）。
- 证据边界：README 自述 + 仓库公开（可复现性高）；TechEBlog（11-01）报道第三方用户 Orailnoor 的 Poco F1 演示视频（GPU 加速 60 fps 声明）——**视频证据，未独立复核**。
- 出处：github.com/ry-diffusion/Bergamota、techeblog.com（11-01）。

**E. MeowTechOpenSource/ios-beryllium——相关度：中**：ios-sweet → Poco F1 fork；Apple launchd PID 1 + boot tasks 真机确认，卡 exec mount 后；构建流 `hardware_target=beryllium`（§2.4 旁证）；验证纪律范文（明确区分"flash 成功"≠"XNU mount 成功"）。出处：github.com/MeowTechOpenSource/ios-beryllium。

**F. vphone（lakr233）——相关度：中**：Apple PCC 壳包 iPhone 核心的虚拟 iPhone（DFU 身份 vresearch101ap / 运行时 vphone600）。可借鉴物：**DT 身份重写 13 属性风险分级表**（`target-sub-type`/`fdr-product-type` = HIGH（restore 链依赖）；`compatible[1]`/`sub-product-type`/`unique-model` = LOW（纯用户态读取，改后 `hw.machine/hw.product/hw.model` 生效）；`compatible[0]` 绝对不动；`gestalt-variants` 节点名 = libMobileGestalt 字面查找）；补丁手法（launchd_cache_loader NOP 校验、mobileactivationd `should_hactivate=true`）。出处：github.com/lakr233/vphone-cli（research/firmware_manifest_and_origins.md）。

**G. Corellium / Project Sandcastle——相关度：低**：Sandcastle 状态页停滞（iPhone 7/7+/iPod touch 7，GPU/音频全 ❌）；Corellium 商业平台 7.14.0（10-08）iOS 26/27 全支持 + MCP servers + Metal 兼容投资——闭源商用，无借鉴物。出处：projectsandcastle.org/status、support.corellium.com/releases。

**H. Mu-Silicium / MU-Qcom（Project-Silicium）——相关度：中（v1.x 三系统）**：v4.1（2026-11-01）：KEP（Winload patch）修复、Windows "Rubidium" semester、Exynos 大扩张（S5E9810/9830/8895 UFS/MSHC/SD、Hypervisor loader、CNTFRQ_EL0 KEP patch）、新设备 OnePlus 15（infiniti，Linux Boot ✅ Windows ❌）/OnePlus 13R Ace 5（giulia）/13s（macan）/gts9wifi/dreamlte/annibale/salami/b5q；v3.7（06-28）renoir/garnet/netrani/cedros；senna_bc = Realme GT Neo5/GT3（我们 UEFI 底座同源）。**udon/Ace 2 至今无 Windows entry**——PLAN v1.x"只登记不排期"裁决继续成立。可借鉴物：KEP 思路（引导期内核 patch，与 graft 同源）留档。出处：github.com/Project-Silicium/Mu-Silicium/releases、Robotix22/MU-Qcom Status.md。

**I. Mesa freedreno/Turnip——相关度：高（v0.5）**：Mesa 26.0.0（2026-02-11）Turnip a7xx 大批修复（BV/binning、LRZ 元数据、softfloat32/64、MSRTSS、VK_QCOM_subpass_shader_resolve、VK_EXT_custom_resolve）；25.3.3 稳定线（01-01）；文档 freedreno GL = Adreno 2xx–8xx、Turnip Vulkan 1.3/1.4 = a6xx+a7xx。**社区实测兼容表（lfdevs/mesa-for-android-container）：Adreno 730 GL/GLES/Vulkan 全 ✔**（实测确认名单内）——我们 v0.5 freedreno 主路线的 Linux 侧实证又厚了一层；上游 HakiOS 用 25.0.7。可借鉴物：v0.5 时把 Mesa pin 从 25.0.7 升 25.3.x/26.x 的 diff 评估；`TU_DEBUG=sysmem` 旋钮（Bergamota/UniXNU 均在用）。出处：docs.mesa3d.org/relnotes/26.0.0.html、/drivers/freedreno.html、lists.freedesktop.org 25.3.3、github.com/lfdevs/mesa-for-android-container、github.com/The412Banner/Banners-Turnip（26.3.0 周构建）。

**J. Procursus——相关度：中（v0.4 /jb）**：最后 commit 2026-05-30（uikittools 2.1.8）；launchctl 1.2.0（2025-09）；OpenSSH recipe pin **9.7p1**（nextjailbreak 2026-10-22 核对）；镜像站 lastupdate 2026-07。结论：无重大更新，阶段 17 物料（mk-jb.sh openssh-server + rc.jobs.ssh）**无需变更**。出处：github.com/ProcursusTeam/Procursus/commits、nextjailbreak.com、procurs.us、docs.procurs.us。

**K. 中文圈——相关度：中高（真实性基准）**：
- **K20 Pro（raphael/SM8150）酷安社区常驻固件**：基于 HakiOS 打包为"可常驻刷入"测试固件，双系统 + 数据持久化，Magisk 模块或"音量上+电源"进 iOS；亮度/声音已修，相机能用但一般，App Store 打不开，**侧载 >50% 失败、能侧载的基本打不开**；十来分钟明显发热。smzdm 2026-11-03 长文 + IT之家 11-03 报道测试固件包；**B站演示（iOS+Windows+安卓三系统共存）播放超 18 万**。真实性评估：**真**（基于已开源代码，多源交叉、社区充分复现）；"日常可用"边界被一致确认（打电话/蓝牙/充电/应用生态全缺）。
- 防诈基准：hackios.net 中文核实站逐条对官方仓库核对，明确"网盘转存刷机包全是二次搬运/任何付费下载是骗局"；早期媒体（AI ECO HK 10-19，开源前）持"未验证"怀疑——后被开源复现推翻，时间线完整。
- 其他：HTC HD2 跑 iOS 7（j0sh1x，10-07，视频证据）——怀旧实验；B站具体 BV 号未捕获（搜索引擎未给直链，如实记录）。
- 出处：post.smzdm.com/p/aomqr29m/（11-03）、post.smzdm.com/p/ad7mevlp/（10-29）、hackios.net、aieco.hk（10-19）。

**L. LightTouch——相关度：低**：Windows 全系统 iOS 模拟器（boot/launchd/Setup/锁屏/Home 达成；GPLv2/LGPL2.1；Android 构建计划中）。互证 launchd 完整可满足；wiki 转述属**宣传级**。出处：emulation.gametechwiki.com。

**M. 外围移植尝试——相关度：低**：scion-starlte（Galaxy S9/Exynos 9810 跑 HakiOS iOS 16.5，UniXNU 目录收录）；HTC HD2 iOS 7；Pixel 6（Tensor）/Galaxy S7（Exynos 8890）尝试未成（Android Authority）。信号：XNU 移植方法论已跨 SoC 厂扩散。出处：unixnu.com/devices/、androidauthority.com。

---

## 4. Top 3 可直接搬进管线的借鉴物

**#1 UniXNU MobileGestalt identity + ADT 身份契约 → 阶段 20（launchd）**
- 内容：unixnu.com/guide/mobilegestalt 的属性表（`model`→hw.product/hw.machine、`target-type`→hw.target、product-name/artwork-*/button-names/home-button-type/certificate-production-status/display-scale）+ /porting/device-tree 的 `/chosen` 契约（random-seed/unique-chip-id/chip-id/osenvironment/root-matching/boot-manifest-hash）。
- 用法：作为 §2.3 修复的**验收对照表**——mkidentity.sh 重生成后逐项核对 identity.h 四张表 vs UniXNU 属性表；对拍差异即下一波 launchd 卡点的排查清单。
- 预期收益：launchd EINVAL 直击（§2 根因）；工作量 0.5–1 天（含重编 loader + repack + 自检）。
- 出处：unixnu.com/guide/mobilegestalt、unixnu.com/porting/device-tree、lakr233/vphone-cli。

**#2 本仓自查产物：`mkidentity.sh` 正规化进构建 SOP → 阶段 20（launchd），防复发**
- 内容：§2 全链。这不是外部借鉴，但它是本次审计**最高价值产出**：把"IPSW 在库后必须重跑 mkidentity.sh 再编 loader"写进 wave14/16/18 式 SOP 与 verify-udon-hakios 自检（可加一条：loader.efi 内嵌 identity.h ≠ placeholder 的断言——占位版 identity_root 只有 `hakios-placeholder` 一项，可 grep 二进制判别）。
- 预期收益：修复 v13 关口 + 防止未来任何 loader 重建再吃一次隐形坑。
- 佐证生态：ios-sweet 家族 `hardware_target=` 构建变量、UniXNU ADT 契约、vphone 风险分级（三方同构）。

**#3 HakiOS 上游 v0.8 双系统全家桶 → v0.8 波（Plan "双系统"节）**
- 内容：U-Boot v2026.07（boot_a 菜单 + loader 日志在 U-Boot 下可写 + fastboot over U-Boot DWC3 修复）+ tools/{backup-partitions,userdata-carve --wipe,sparse-split,mkdatavol}.py + hakios-install.img + 安装/恢复文档（docs/dual-boot.md，含 "Device Error" 恢复全流程）；loader 侧已放宽为"任意手机的 darwin 分区"。
- 用法：我们 P0 工具同源已 PHK110 化（资产 #5），补 U-Boot udon 设备文件 + 安装镜像两件即对接；上游"Android 默认 10 s + HakiOS 不充电警告"的菜单策略直接抄。
- 预期收益：v0.8 从"自研设计"变"上游验收过的安装路径"；估计省 1–2 个阶段。
- 出处：hackios-web.vercel.app/en/docs/dual-boot、/en/changelog（10-29/10-30 条目）。

**战略储备（不占 Top 3）**：Bergamota Renegade（arm64e 重写器）→ 若 v0.5 后想上 iOS 18.x 用户态（xnu-11215 对齐 Heartwood）的唯一公开路径；Mesa 25.0.7→25.3.x/26.x 升级评估 → v0.5 首个预研项；Bergamota CDC-ECM SSH 体验目标 → 阶段 21 验收尾径（`ssh root@…` 一条命令进 Darwin）。

---

## 5. 建议行动（按优先级）

1. **阶段 20 前置取证/修复（0.5–1 天，本报告已完成取证半）**：按 §2.3 三步走（mkidentity.sh 重生成 → loader 重编 → v14 第一次刷写）；验收 = §2.3 验证行。
2. **上游问询（零成本，可与 1 并行）**：Telegram oosexgangdevs 或 kernel 仓 issue 确认：redwood 上 FLASHBOOT=1 CRYPTEXES=flash + rc.jobs.ssh 同链的 launchd 段日志样本（对拍我们 v14 越关后的下一卡点）；顺带问 identity.h 占位判定是否值得加进他们 `make doctor`。
3. **自检加固（1 行）**：verify-udon-hakios 加 "loader.efi 非占位 identity" 断言（§4 #2）。
4. **阶段 21 维持方案 A**：Bergamota CDC-ECM 佐证"真 USB 网卡"体验可行，但我们内核无 USB 栈的否决理由不变；loader 桥接 + ProxyCommand 目标口径不变。
5. **v0.5 预研（0.5 天，可提前）**：Mesa pin 升级 diff 评估（25.0.7 → 25.3.3/26.0.x，a7xx 修复清单已列 §3-I）；把 PLAN v0.5 "实验备选" 更新为 "UniXNU AdrenoMetal 路线（上游 HakiOS 已采纳 mk-m2v.sh），KGSL shim 路线降权"。
6. **v0.8 路线改判建议**：从"自研 U-Boot 移植"改判为"上游 dual-boot 工具链直接验收"（§4 #3）。
7. **披露纪律**：K20 Pro 酷安固件现象说明 HakiOS 传播已出圈；我们未来若公开发布 PHK110 进展，属一揽子对外披露按约定逐次确认。

## 6. 搜不到的（诚实清单）

- `"failed to query hardware target"` 公开解：grep.app 0 命中、GitHub issues（oosexgang 仓）0 命中、HakiOS/UniXNU/ios-sweet 文档 0 条——§2 的解是我们本仓证据链 + 生态同构推出的，**无现成处方**。
- 发起 `hw.target` 查询的确切用户态二进制：字符串载体 = usr/lib/dyld 侧（E1/E2），逐帧归因需 launchd 段日志/崩溃帧，未做（属 阶段 20 第一次刷写后的自然产物）。
- B站 K20 Pro 三系统视频的具体 BV 号：搜索引擎未给直链（smzdm/IT之家转述 + 平台引用标记），未捕获。
- HakiOS 2.3.4 之后（11-06/07/08）更新：未捕获（hackios.net 新闻最后一档 11-05 15:13 UTC）。
- UniXNU 是否内部解决过同款 EINVAL：udon 页只写 "signal exits under investigation"（症状不同：ReportCrash 信号退出），无该错误串——不等于没遇到，但无记录。
- Renegade 是否独立仓库：未确认（在 Bergamota 树内 tools/renegade）。
- Mu-Silicium udon Windows entry：不存在（Status.md 无 udon 行）。
- 第 25 次真机启动：任务简报口径 25 次，STATUS 表在案 24 次（#1–#24），差 1 次无记录支撑。

## 7. 出处索引（按节序）

1. 上游：github.com/oosexgang · github.com/oosexgang/hakios-xnu-kernel · hackios-web.vercel.app/en · /en/changelog · /en/docs/comparison · /en/docs/dual-boot · /en/docs/metal-plan · t.me/s/oosexgangdevs · hackios.net/en/news · hackios.net
2. UniXNU：unixnu.com/devices/udon · /devices/ · /guide/mobilegestalt · /porting/device-tree · /porting/gpu · /drivers/adreno-metal · /concepts/payload · /reference/configuration · /drivers/device-tree-matching · /porting/steps · github.com/UniXNU/UniXNU · /UniXNU-sheng · /AdrenoMetal · github.com/takasugl/UniXNU-udon · github.com/CrossDarwin/macOS-ForSheng · github.com/darkplace/UniXNU-Odin3 · unixnu.com/devices/pong-agxmx666 · /devices/asteroids
3. ios-sweet 系：github.com/dipa-studio/ios-sweet · github.com/MeowTechOpenSource/ios-beryllium · github.com/ry-diffusion/Bergamota · androidauthority.com/ios-on-android-phones-3726001 · decrypt.co/381351 · techeblog.com（Orailnoor）· xiaoyi.vc · jam.kim/archives/6895
4. vphone/虚拟化：github.com/lakr233/vphone-cli（research/firmware_manifest_and_origins.md）· projectsandcastle.org(/status) · support.corellium.com/releases · gist.github.com/arianvp/85a70fc6d9becc6068aec8cecb8a7ae9 · emulation.gametechwiki.com（IOS_emulators）
5. 底座/图形/包生态：github.com/Project-Silicium/Mu-Silicium/releases（v3.7/v4.0/v4.1）· Robotix22/MU-Qcom Status.md · docs.mesa3d.org/relnotes/26.0.0.html · /drivers/freedreno.html · lists.freedesktop.org（25.3.3）· github.com/lfdevs/mesa-for-android-container · github.com/The412Banner/Banners-Turnip · github.com/ProcursusTeam/Procursus(/commits) · nextjailbreak.com · procurs.us · docs.procurs.us · theapplewiki.com/wiki/Procursus
6. 中文圈：post.smzdm.com/p/aomqr29m/ · post.smzdm.com/p/ad7mevlp/ · aieco.hk · quickfinesse.dev/videos/2026-10-24-hackios · pbxscience.com（UniXNU 评测）
7. 检索工具记录：grep.app（`failed to query hardware target` = 0）· github.com/oosexgang/hakios-xnu-kernel/issues?q=hardware+target（= 0）
8. 本地只读取证（WSL，2026-11-08）：`~/hakios/kernel/xnuloader/{identity.h, mkidentity.sh, mkidentity.py, loader.c}` · `~/hakios/kernel/xnu-src/xnu-8796.121.2/{pexpert/arm/pe_init.c:432-436, bsd/kern/kern_mib.c:502,525,999, bsd/sys/sysctl.h:1200}` · `~/hakios/sysimage-20F66/work/rootfs/{sbin/launchd, usr/lib/dyld}` · `~/hakios/sysimage-20F66/work/DeviceTree.d22ap.im4p`
