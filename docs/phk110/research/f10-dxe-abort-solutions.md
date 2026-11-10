# DXE 阶段 Data Abort（FAR=0xF0000000）的外部先例与修复模式调研

**日期**：2026-11-08 ｜ **性质**：F10 专项调研（外部先例 + 独立本地字节扫描；驱动身份反汇编见另篇，本报告不重复）
**案例**：SM8475 (PHK110/udon) Mu-Silicium 系 UEFI（DEBUG，FD sha 8924cb67），BdsDxe 调用 DXE 驱动（加载基址 0xFA58E000，EntryPoint+0x60）解引用 FAR=**0xF0000000** → Synchronous external abort (EC 0x25) → EDK2 默认处理器 `ASSERT(FALSE)` @ CpuExceptionHandlerLib.c(438) 死循环。间歇性：#31（暖）/ #32（冷）均中。

> ## ⚠ 结案更正（2026-11-08，照片定案——本报告成文于定案之前）
> **F10 已闭环，真因与本报告的工作假设不同**：崩点驱动 = **本项目自产 `xnuloader/loader.efi`**（BDS 经 gBS LoadImage/StartImage 启动 payload 内 loader，非 vendor DXE）；根因 = 本轮构建回归，裸 `./build.sh` 漏带 `PAYLOAD_BASE=0xF4000000` → loader.c:23 的 **redwood 上游默认基址 0xF0000000** 编进 loader，parse_payload 首读 `ph->magic` 即访问**未映射地址**（udon uefiplat.cfg 无此映射 → L0 translation fault），冷/暖无关、v16b 6 hunks 无罪。修正版 v16b'（`e33ec417…`，54/54 自检，F10 指令级钉死）已入库待刷写。教训已钉流程：编 loader 必须 `PAYLOAD_BASE=0xF4000000 ./build.sh`（详见 `docs/STATUS.md` 更新⑪、`docs/waves/wave21_2-ssh-catch.md` §7）。
> **因此本报告以下内容的地位调整为**：①§2 外部先例库、§3 本地扫描数据、§3.3 vendor 常量普查（DALSYSDxe 含 18 处 0xF0000000 记录）= **仍有效的参考档案**（将来 vendor DXE 域再出 0xF0000000 类异常时直接可用）；②§0-1 的"TZApps 触碰"机制假设、§6 修复建议 = **对本案例已被裁决取代**（0xF0000000 实为"未映射"而非"TZ secure 区访问"；但注意 §3.2 的 TZApps 边界事实仍准确——若当时 loader 落在 0xEA–0xF14 区内则会是另一种 abort 签名）。"0xF0000000 = redwood 系 loader 的历史默认 payload 基址"这一语义，比本报告检索到的任何外部语义都更贴合本案，且已由反汇编代理证实。

---

## 0. 一页结论（TL;DR）

1. **0xF0000000 落在本机 TZApps carveout 内部**：udonPkg `MemoryMapLib.c:35` 定义 `TZApps Reserved = 0xEA000000, size 0x07400000`，即 0xEA000000–0xF13FFFFF。0xF0000000 位于其中段。**对 TZ/hyp 拥有的物理区做 NS 访问 = Synchronous External Abort**——这一机制在本机已有 UniXNU BRINGUP 原文证据（SM8475 SMMU 编程 external abort，见 §2.2），并与 Mu-Silicium 上游 OnePlus 15 同型案例 #2120（TZ carveout SEA，§2.1）互证。
2. **本地扫描（§3）**：全部源码构建模块 **零** movk/movz 0xF0000000 立即数；word 命中全为 ADRP 指令编码噪声。唯一物化 0xF0000000 的二进制 = **vendor `Binaries/udon/.../DALSYSDxe.efi`**（18 处 qword `0x00000000F0000000`，嵌在重复描述符表内；且 DALSYSDxe 确认在编，`DXE.inc:29` + `APRIORI.inc:17` 早期派发位次）。UsbConfigDxe 二进制本身不含该常量，但断言屏 USB 状态行字符串（`ConnectSts` / `Data Role`）**归属 `UsbConfigDxe.patched.efi`**。
3. **生态先例**：Mu-Silicium/MU-Qcom、edk2-msm（Renegade 系）公开 issue 中**未找到**与本案同型的"BdsDxe 调驱动入口即 Data Abort @ sm8450/sm8475"直接记录（搜索词组合见 §4"未找到清单"）；但同机制先例（TZ carveout SEA → MemoryMapLib 标 Reserved）与同诱因先例（暖重启 USB 控制器带病重入）均有官方级修复记录。
4. **修复模式库（§5）按适用度排序**：① DXE.inc 注释 DALSYSDxe 做 A/B 定性（1 行，最快）→ ② APRIORI/DEPEX 时序调整 → ③ .patched.efi 字节手术（树内成熟范式）→ ④ MemoryMap 收紧 → ⑤ 源码级 DWC3 复位（成本高）。

---

## 1. 仓库/上游谱系速览（调研中确认的事实）

- `Robotix22/MU-Qcom` 已 301 重定向至 **`Project-Silicium/Mu-Silicium`**（MU-Qcom = 本项目底座直系上游的旧名）。本地 `uefi-udon` = Mu-Silicium 结构（Mu_Basecore + Silicon/QcomPkg + Platforms/OnePlus/udonPkg）+ Renegade 系 `Binaries/` vendor 预编译 DXE。
- **Binaries/udon 的 vendor DXE 实为 senna_bc（三星 Z Flip4，同代 SM8475）原厂件移植**（`docs/PLAN.md:83`、`docs/README.md:36/66`；`docs/STATUS.md:149`："udon FD 的 DALSYSDxe = senna_bc 原厂原版"）——即本案嫌疑二进制并非 PHK110 原厂件，是同 SoC 邻机件的移植。
- edk2-msm（Renegade 系，`edk2-porting/edk2-msm`）对 SM8450/SM8475 均有支持线（sm8475 初始支持 PR #339，Xiaomi Pad 6 Max "yudi"，自述"只能 boot，按键/触摸不工作"）。

## 2. 外部先例（带出处）

### 2.1 Mu-Silicium / MU-Qcom（底座直系上游）

| # | 先例 | 内容 | 对本案意义 | 出处 |
|---|------|------|-----------|------|
| M1 | **Issue #2120（OnePlus 15 "infiniti"）**：Synchronous External Abort (DFSC 0x10) | 根因 = `RamManagerDxe` 把 XBL RAM 表里的 **TZ/hyp carveout（Gunyah_Hyp 0x80000000 / Tz_Reserved 0x80E00000 等）当 conventional RAM 暴露**，首个 CPU 写入即 SEA。修复 = `MemoryMapLib.c` 把这些 carveout 标 `EfiReservedMemoryType`（对齐 downstream GKI no-map）。维护者以 zip 构建件验证通过 | **同机制同病**：TZ/hyp 拥有区被当普通内存用 → SEA。修法范式 = 内存描述符层收紧，不碰驱动二进制 | https://github.com/Project-Silicium/Mu-Silicium/issues/2120 |
| M2 | Status.md：SM8450 设备 USB 状态普遍 ⚠️/❌（如 gts8 "USB: No USB Host & Power"） | USB DXE 在 sm8450 代设备上稳定性差是生态常态，但公开 issue 少有带异常签名的记录 | 支持本案"USB 域问题"方向，但无直接同型签名 | https://github.com/MoonisReal/Mu-Qcom/blob/main/Status.md（镜像）；上游 Status.md 无 udon 条目（udon 非官方支持机） |
| M3 | Release notes（v3.8/v3.9/v4.1）反复出现内存/时序类修复 | "Fixed KEP Crashes"、"Fixed RamManagerDxe Loading too Late"、"Removed Memory Protection"、"Removed leftover CPU Vector Memory Regions"、"Fixed Incorrect Stack Position in SEC" | 上游高频病灶 = 内存描述符/加载时序，不是驱动逻辑本身；修复常落 MemoryMapLib/SEC/加载序 | https://github.com/Project-Silicium/Mu-Silicium/releases |
| M4 | Qualcomm 官方 UEFI 样本日志：`DALSys.efi` 在 DXE 早期加载，且暖态打印 **"Module cannot re-initialize DAL module environments"** | 官方文档样本日志直接记录 DAL 模块**重入（re-init）失败**是已知态 | DAL 子系统暖态重入问题被 Qualcomm 官方日志条目化；本案 DALSYSDxe 在 APRIORI 早期位次 + 暖 boot 场景吻合 | https://docs.qualcomm.com/doc/80-80022-4/topic/uefi-log.html |

### 2.2 Renegade / edk2-msm + 本地内证（最强机制先例）

| # | 先例 | 内容 | 出处 |
|---|------|------|------|
| R1 | **UniXNU BRINGUP 原文（本地文档多点多级引用）**："SMMU programming is deliberately skipped on **SM8475** because it caused an **external abort**" | 同机（udon/PHK110 系）真机实测：**未经固件/TZ 配置就触碰固件拥有域 → external abort**，upstream 的对策是"整条路径不碰" | `docs/README.md:64`、`docs/waves/wave3-research-external.md:35`、`docs/waves/wave10-post-gic-abort.md:97`、`docs/waves/wave16-ufs-s0s2.md:105` |
| R2 | edk2-msm PR #339 "Add initial sm8475 support"（merged 2023-09） | SM8475 在 Renegade 系只有"能 boot"级支持 | https://github.com/edk2-porting/edk2-msm/pull/339 |
| R3 | 2Petro/edk2-msm-sm8450 自述 "(broken)" | SM8450 的独立 edk2 移植长期处于 broken 状态（生态面证据） | https://github.com/2Petro/edk2-msm-sm8450 |

### 2.3 暖重启 USB/DWC3 间歇性问题（跨生态）

| # | 先例 | 内容 | 修复模式 | 出处 |
|---|------|------|---------|------|
| U1 | **SM8450 DWC3 设备模式初始化**：runstop 置位前 GEVNTADR{LO/HI} 寄存器写**间歇性失败** → 事件地址为 0 → 控制器写 0 地址 → SMMU fault 系统崩 | Qualcomm HW 团队确认：清 GUSB3PIPECTL.SUSPHY 即愈；mainline 以 `snps,dis_u3_susphy_quirk` 落地（sm8450.dtsi，对 SM8350/8450/QCS615 一年零复发） | 控制器 quirk/复位类 | https://lists.openwall.net/linux-kernel/2025/03/25/747 |
| U2 | SM8250/SM8450 USB GDSC：suspend/唤醒后控制器不工作 | `usb30_prim_gdsc` pwrsts `PWRSTS_OFF_ON` → `PWRSTS_RET_ON`（retention） | 电源域状态类 | https://www.spinics.net/lists/linux-arm-msm/msg238705.html ；https://github.com/cupid-development/android_kernel_xiaomi_sm8450/commit/1a79539f4e8b24e234c2e7fc2050e416e9ce212d |
| U3 | tianocore edk2 #10443（Bugzilla 4556）：**OS 暖重启后** XHCI + Gen2x2 设备 → Stop Endpoint Failed / 5–7 分钟卡死 | EDK2 官方 USB 栈对暖态控制器遗留状态处理不良的官方记录；修复方向 = 补 endpoint reset 路径（XHCI spec 4.8.3） | 控制器状态重建 | https://github.com/tianocore/edk2/issues/10443 |
| U4 | pcengines apu2 #177："USB3 does not survive soft reboot"（冷启动即愈；**软重启两次反而恢复**） | 社区判控制器硬件状态 bug；规避 = 冷启动/热插拔 | 暖态规避 | https://github.com/pcengines/apu2-documentation/issues/177 |
| U5 | qcom uefisecapp/QSEECOM（X13s）：req/rsp **TZ 共享缓冲布局违规 → 间歇性 hard reset**（kzalloc 相邻时多数不触发 = 间歇模式，修复后 3 小时零复发） | TZ 共享内存布局/映射违规的间歇性表现先例——与"TZApps 区内指针被触碰"高度同构 | TZ 缓冲布局修正 | https://lists.openwall.net/linux-kernel/2024/04/06/195 |
| U6 | Gunyah metadata 区未被 efi map 正确保留 → 内核分配到 hyp 拥有页 → **spurious Synchronous External Abort (ESR 0x96000010)** | 最新（2026-03）mainline 修复：补 reserved-memory carveout（no-map） | 内存保留修正 | https://github.com/ayufan-rock64/linux-mainline-kernel/commit/85d98669fa7f1d3041d962515e45ee6e392db6f8 |

### 2.4 EDK2 通用机制（BdsDxe 调驱动入口即崩的根因谱）

- **默认异常处理器行为**：AArch64 的 EDK2 异常路径 = 打印上下文 + `ASSERT (FALSE); CpuDeadLoop ();`（本地 `Mu_Basecore/UefiCpuPkg/Library/CpuExceptionHandlerLib/AArch64/CpuExceptionHandlerLib.c` ~L437-438，即本案死循环出处）；且该打印路径自身在 DEBUG 构建还有二次崩风险（DumpModuleImageInfo/PeCoffLoaderGetPdbPointer，tianocore #10883）。出处：https://github.com/tianocore/edk2/issues/10883
- **"DEPEX 满足 ≠ 依赖产物可用"**：DXE 派发器只按 protocol 安装情况评估 DEPEX（本地 `Mu_Basecore/MdeModulePkg/Core/Dxe/` 派发逻辑）；vendor QCOM 驱动链隐式依赖（EnvDxe→SmemDxe→ScmDxe→DALSys→…）中前序失败/未产出时，后继入口读到的全局指针是垃圾值 → 首次解引用即崩。社区常见修法 = 补 DEPEX / 调 APRIORI 序 / FV 剪除。
- **加载基址/重定位冲突**：驱动落点与内存描述符冲突会改写其 .data/.bss（本案 0xFA58E000 是否与任何保留区重叠，属反汇编代理验证项；本地 MemoryMap 已确认 TZApps/XNU Payload/DXE Heap 边界与 0xFA58E000 不重叠——0xEA000000–0xF1400000 之外）。

### 2.5 0xF0000000 的外部语义

- **未找到**任何公开 Qualcomm 项目/文档把 0xF0000000 记载为 PCD/HOB/配置默认值（GitHub issue/commit 搜索、grep.app【被 Vercel 安全盾拦截】、exa 全网检索，见 §4）。
- **本机语义锚点（最硬）**：TZApps carveout 0xEA000000–0xF13FFFFF 的中段（§3.2）；且 vendor DALSYSDxe.efi 数据表中 18 处 `0x00000000F0000000` 记录（§3.3）——stock XBL DAL/QSEE 描述表把 0xF0000000 用作某共享/TZ 块基址的实证。MPSS/modem 基址未检索到 0xF0000000 关联。
- 注意勿与 TLMM（SM8450/8475 pinctrl @ 0x0F100000，区域 0x0F000000–0x0FFFFFFF，本机 `MemoryMapLib.c` 亦有 `{"TLMM", 0x0F000000, ...}` 条目）混淆——位数不同（0x0F000000 ≈ 240MB vs 0xF0000000 ≈ 3.75GB）。

## 3. 独立本地扫描（与反汇编互补的笨办法，只读）

**方法**：Python 只读扫描（脚本入库 `wave21-scripts/f10_scan_f0000000.py` / `f10_scan2_context.py`，结果 JSON 同目录），三类 pattern：
- WORD：4 字节 `00 00 00 F0`（LE 0xF0000000）
- QWORD：8 字节 `00 00 00 F0 00 00 00 00`（0x00000000F0000000）
- MOVK/MOVZ 立即数编码：`movk xN,#0xF000,lsl#16`=`(Rd) 00 9E F2`、`movk wN,...`=`(Rd) 00 9E 72`、`movz xN,#0xF0,lsl#24`=`(Rd) 1E A0 D2`

**样本**：`Build/udonPkg/DEBUG_CLANGPDB/AARCH64/**` 全部 .efi（223 文件）+ `Binaries/{udon,9707f,enchilada}` 全部 .efi（721 文件）+ `FV/SILICIUM_UEFI.fd`（4,194,304 B）。

### 3.1 总体分布

| 样本域 | movk/movz 0xF0000000 立即数 | word 命中性质 |
|---|---|---|
| 源码构建模块（223 .efi） | **0**（全零） | 每文件 6–46 处，**全部为 ADRP 指令编码噪声**（0xF0000000 恰是 `adrp x0, pc+0x3000` 的编码；上下文样本均为 `...adrp x0 + add x0...` 指令流，非数据） |
| `SILICIUM_UEFI.fd` 原始字节 | 0 | 10 处 word（3 处 4 对齐），同上 ADRP 型。**注意**：FvMain 为 LZMA 压缩（`udon.fdf` "This FV gets compressed"），FD 级扫描存在盲区——以未压缩的原材料（构建产物 + vendor 二进制）扫描为准 |
| vendor `Binaries/udon`（本机实际嵌入件） | 仅 DALSYSDxe.efi 1 处疑似（见 3.3） | 见 3.3 |
| vendor `Binaries/enchilada`（sdm845 对照组） | **UsbConfigDxe.efi / UsbConfigDxeWp.efi 各 2 处 movk32**（0xF000xxxx 上半立即数）；DALSYSDxe 200 word/4 qword | 生态对照：sdm845 时代的 UsbConfigDxe 曾持有 0xF000xxxx 常量；sm8475 代（udon）已不再有 |

### 3.2 关键命中文件清单（udon，与本案相关项）

| 文件（`Binaries/udon/`） | word | qword(0xF0000000) | movk32 | 备注 |
|---|---|---|---|---|
| **QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.efi** | 200 | **18** | 1（存疑） | **全 udon 唯一物化 0xF0000000 的驱动**；在编：`DXE.inc:29` + `APRIORI.inc:17`（APRIORI 第 17 行 = 早期派发位次） |
| QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.efi | 8 | 2 | 0 | 在编 `DXE.inc:100` |
| QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.efi | 1 | 0 | 0 | 在编 `DXE.inc:101`；**二进制不含 0xF0000000** |
| QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.patched.efi | 1 | 0 | 0 | **含 ASCII 字符串 `ConnectSts`、`Data Role`**（全 udon 唯一命中）→ 断言屏 USB 状态行归属 |
| QcomPkg/Drivers/TzDxe/TzDxeLA(.patched).efi | 14 | 2 | 0 | **未在编**（`DXE.inc:14` 被注释；APRIORI.inc:51 残留引用无害） |
| QcomPkg/Drivers/ClockDxe/ClockDxe.efi | 69 | 2 | 0 | qword 命中未见结构化表，判噪声 |
| 其余（ShmBridgeDxeLA/ScmDxeLA/UsbInitDxe/UsbfnDwc3Dxe 等） | 0–25 | 0 | 0 | 无嫌疑 |

### 3.3 DALSYSDxe qword 上下文（0xF0000000 是描述符表字段）

18 处 qword 全部为**非对齐偏移、嵌在 24 字节左右步长的重复结构中**，形如
`{0x0000000004000000, 0x000000008A200000, 0x00000000F0000000, 0x0000000004000000, 0x000000008A3C0000, ...}`（样本偏移 0x25386 / 0x26e0e / 0x296c6 / 0x29ac7 / 0x29adf / 0x2b4de / 0x2b80e…）——解读为 stock XBL 的 DAL/QSEE **内存描述符表**，其中 0xF0000000 以第三字段身份反复出现（地址/上限/目标基址语义，精确字段含义需反汇编代理定案）。
唯一 movk32 命中 @0x780e 的上下文（`...0x728C0000, 0x729E0000, 0x72AA0000...` 连续三个"movk 编码"形态）更像 32 位数据表而非指令流，**如实降级为存疑**。

### 3.4 内存描述符定位（`Platforms/OnePlus/udonPkg/Library/MemoryMapLib/MemoryMapLib.c`）

```
{"TZApps Reserved", 0xEA000000, 0x07400000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN}   ← L35：0xEA000000–0xF13FFFFF，0xF0000000 在内
{"XNU Payload",     0xF4000000, 0x04000000, ...}   ← 本项目 payload 新基址（已迁移）
{"DXE Heap",        0xF8000000, 0x07C00000, ...}
{"TLMM",            0x0F000000, 0x01000000, ...}   ← 勿与 0xF0000000 混淆（位数不同）
```
FD 基址：`FD_BASE=0xA7100000`（`scripts/build-udon-firmware.sh:45`）。

### 3.5 扫描对反汇编的输入（非重复劳动）

- 0xFA58E000 加载基址**不在** TZApps(0xEA–0xF14)/XNU Payload(0xF4–0xF8)/DXE Heap(0xF8–0xF8+7C) 任一保留区内 → "驱动自身被踩"假设弱化。
- 0xF0000000 的最可信供给源 = DALSYSDxe 描述符表（若崩点驱动为 DALSYSDxe 或其消费者）；UsbConfigDxe 本体无常量，但其命中路径若读 DALSys 产出结构亦可间接触达。

## 4. 搜不到的（如实声明）

- Mu-Silicium / MU-Qcom / edk2-msm / Renegade 公开 issue 中**无**本案同型记录（"BdsDxe 调用驱动入口 + FAR=0xF0000000 + sm8450/sm8475"；检索组合：abort / "external abort" / "data abort" / assert+usb / fastboot / reboot / sm8475，GitHub Search API + exa 双通道）。
- 0xF0000000 作为 Qualcomm PCD/HOB/MEMFD 默认值的**官方记载未找到**；grep.app 全网代码搜索被 Vercel 盾拦截、GitHub code search 未授权（网络均走 127.0.0.1:7897 代理）。
- MU-Qcom 对 sm8450 USB DXE 暖态问题的**专项处理史**未找到（仅 Status 表的 ⚠️ 记录与 release notes 的泛化修复）。搜不到 ≠ 不存在，标注为证据缺口。

## 5. 修复模式库（按本案适用度排序）

| 排名 | 模式 | 先例 | 对本案实施 | 代价 | 风险 |
|---|---|---|---|---|---|
| 1 | **FV 剪除/除名嫌疑驱动做 A/B** | 本树 TzDxeLA 已用（`DXE.inc:14` 注释）；Mu 上游 "Removed General useless Qcom Drivers"（v3.9） | `DXE.inc:29` 注释 DALSYSDxe（若反汇编证实崩点为其或其消费者）或逐个除名 UsbDeviceDxe/UsbConfigDxe 对照；一轮刷写即定性 | 1 行 + 重打包 FD（零代码） | DALSys 协议消费者（PIL/UsbConfig 等）连锁失败会以**别的**失败形态表现——需与"F10 消失"分开判读；建议单变量一次一驱动 |
| 2 | **APRIORI/DEPEX 时序调整** | EDK2 派发机制（§2.4）；M3"RamManagerDxe Loading too Late"反向先例 | DALSYSDxe 从 `APRIORI.inc:17` 早期位次移到常规派发（依赖 ScmDxe/ShmBridge 产物就绪后），或补显式 DEPEX | 1–2 行 | 弱：时序变化可能只是把崩溃窗口后移；作为模式 1 的对照实验有价值 |
| 3 | **vendor 二进制字节手术（.patched.efi）** | 本树成熟范式：UsbConfigDxe.patched / UsbMsdDxe.patched / TzDxeLA.patched / FeatureEnablerDxe.patched 均在 Binaries 树；redwood README 的 DALSYSDxe UFS coherence patch（`STATUS.md:149`） | 反汇编定案后在 0xF0000000 读取路径前插护栏（范围检查/替换安全值/跳过该 descriptor） | 一次字节手术 + graft 步骤 | 中：偏移计算错会换一种崩；但可逐字节验证（自检含 sha） |
| 4 | **MemoryMap 收紧（Mu-Silicium #2120 模式）** | M1（OnePlus 15 SEA → 标 EfiReservedMemoryType）；U6（no-map carveout） | 把 TZApps 从 `AddMem+Reserv` 改 `HobOnlyNoCacheSetting` 或确认其不被映射进 NS 页表；防 SEA 需"NS 不映射"而非仅 XN（XN 不挡读） | 中（1 行描述符 + 全 boot 回归） | 中高：误伤 SMEM/PIL/DAL 正常路径（它们合法消费 TZ 边界区）；#2120 修复的是"当 RAM 暴露"，本案 TZApps 已是 Reserv，改法需先确认当前映射产物 |
| 5 | **源码级 DWC3/USB 复位 quirk** | U1（dis_u3_susphy）/U2（GDSC retention）/U3（endpoint reset） | 在 vendor UsbInit/UsbConfig 之外源码层做控制器软复位；或 loader 流程规避（现有 20s 节拍已属此类） | 高（新驱动代码） | 中：与 vendor 双栈共存未证（wave19-prep R-B 结论） |
| 6 | **内存保护/PSC 类** | Mu v3.x "Removed Memory Protection"（上游反例：保护反而惹祸被移除） | 不建议 | — | 上游已证负收益 |

## 6. 给 阶段 21.2 主攻代理的三条建议（已被结案裁决取代——F10 真因 = 构建回归，见顶部更正；以下留档仅当未来 vendor DXE 域再现 0xF0000000 类异常时参考）

1. **先跑零成本 A/B 定性轮**：反汇编定位结果出来前/后，第一刷都建议 `DXE.inc:29` 注释 DALSYSDxe（单变量）——一轮刷写分辨"F10 消失（DALSYSDxe 定罪）/ F10 仍在（转向 UsbConfigDxe 族）/ 变成其他失败（DALSys 消费者连锁，改用模式 3）"。同时按既有制度收屏幕照片 + 判据行。
2. **修复落点优先选模式 3（.patched.efi 字节手术），慎选模式 4**：0xF0000000 是 TZApps 区内地址，MemoryMap 层收紧误伤面大（SMEM/PIL/DAL 合法路径都在 TZ 边界上）；而 Binaries 树的 .patched 范式已有四个成功先例且自检可逐字节验证。DALSYSDxe 描述符表（§3.3）是字节手术的第一坐标来源。
3. **间歇性归因按"每 boot 都跑、仅部分 boot 触碰 0xF0000000 路径"建模型**：#32 冷启动也中削弱纯暖态假设——冷/暖各 2–3 次采样 + A/B 矩阵（模式 1 与模式 2 各一刷）比连续修 USB 时序更省预算；若反汇编证实崩点指令读取的指针来自**前次 boot 遗留内存**（TZApps 中段在暖 boot 场景存有 XBL/fastboot 时代的旧数据），则"读了垃圾指针"与"读了合法但未映射/secure 区"两条线都要在 patch 设计里同时堵住（值检查 + 映射检查）。

## 7. 本报告产物与脚本

- 扫描脚本（只读，未动 uefi-udon 树）：`wave21-scripts/f10_scan_f0000000.py`、`wave21-scripts/f10_scan2_context.py`、`wave21-scripts/f10_print_summary.py`
- 扫描结果 JSON：`wave21-scripts/f10_scan_result.json`、`wave21-scripts/f10_scan2_result.json`
- git 未 commit（统一提交）
