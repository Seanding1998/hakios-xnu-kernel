# 阶段 35 · 2026-11-10 · GPU 预置调研：同 SoC 先例、固件物料与 Mesa 版本裁决

> 2026-11-11 · 阶段 35 GPU 预置执行记录
> 任务书：① MIX Fold 2（zizhan）GPU 案例深挖到"能用证据逐项回答用了什么栈"；② 读上游 hakios.adreno.c + 我们的 DTB 事实，产出 a6xx→gen7 补丁计划与补丁骨架（scratch，不 apply）；③ 实装 pull-firmware-root.sh（Magisk root 暂存法，--dry-run 无手机自测）；④ Mesa/freedreno 选型矩阵（25.0.7 vs Mesa 26 a7xx）。
> 红线执行：零手机零 adb 零 fastboot ✓（本轮无任何设备调用；pull 脚本只写不跑）；`~/hakios/` 构建树绝对只读 ✓（全部取证经 wsl.exe cat/grep/sed 只读完成，无 touch/无构建/无 checkout）；补丁骨架全部在仓外 `scratch/wave35/patches/`（不入库）✓
> 证据分级沿用 F14/F15/F16：**[实证]** = 文件/行号/字节/页面可复现；**[实测转述]** = 作者文档/控制台自述的真机结果（我们未复现）；**[推断]** = 类比/待核；**[待核 TODO-DEV]** = 需一次真机验证探针定案。
> 引用缩写：`[DTB]` = `devices/phk110/uefi/files/Resources/DTBs/phk110.dts`（本机设备树文本，阶段 1 在盘）；`[ADRENO]` = WSL `~/hakios/kernel/drivers/gpu/hakios.adreno.c`（v2.1.13 树，167,033 B，F14 §3.2 判其与上游 HEAD 字节级一致）；`[GPU.CPP]` = 同目录 `hakios.gpu.cpp`；`[UP]` = mainline Linux（torvalds/linux master，2026-11-11 抓取：`drivers/gpu/drm/msm/adreno/`）；`[VENDOR]` = 本机 vendor 内核参照 `~/hakios/refs/kernel_oneplus_sm8475/drivers/gpu/msm/`（阶段 15 入盘的 PHK110 自己的 GPL 内核源，只读参照）；`[ZIZHAN]` = github.com/qiumochen/UniXNU-zizhan；`[MESA]` = Mesa 源（GitLab raw，mesa-25.0.7 tag + main）。

---

## 0. 判定（先行，八条）

1. **MIX Fold 2 GPU 案例证实，且栈形态与我们不同**：`qiumochen/UniXNU-zizhan`（MIX Fold 2，zizhan，SM8475，iPadOS 18.7.10/22H374，Darwin 24.6.0/XNU 11417.140.69）自述 GPU = "**Adreno 730 with Turnip and metal2vulkan**"，合成滑动 95.3 fps（基线 56.7–58.4），其进度台账 GPU-01 状态 **DEVICE_VERIFIED**（冷启动画布失败单列回归项，壁纸 GPU 访问仍禁用，不宣称全局 120 fps）[实测转述，README + docs/progress/STATUS.md 在证]。**它不是 hakios.adreno 适配、不是 freedreno GL、不是 ios-sweet 假驱动**：内核侧 = 自研 XNU 驱动（UniXNU org 的 NativeAdreno/MIT + 对 SM8475 的 PongAdreno 适配层），用户态 = Mesa Turnip（Vulkan）+ metal2vulkan。谱系来自 UniXNU-pong（Nothing Phone 2，SM8450，**同为 Adreno 730**）——pong/zizhan 两代同栈复用，SM8475 只是"换板级数字"。
2. **对 zizhan"能抄的是事实，不是代码"**：它给出一整套 SM8475 GPU 的实测寄存器/固件/序列事实（GMU 0x3d68000+0x37000、RSCC 0x3d50000+0x10000、GMU SID 5、chipid 0x07030002→GMU 打包 0x07030200、HFI 17 头槽/210 dwords/队列@848、GMEM 2 MiB、PAS13、zap b01=代码/b02=证书哈希、SQE 跳首个头 dword、CP_ME_INIT DMS bit11、LPAC stream SID1/0x401、固件名 a730_sqe.fw/gmu_gen70000.bin/a730_zap.*）[实测转述+其引用的 vendor 源在证]。这些已逐条入 阶段 35 补丁骨架。**代码不搬**：其驱动 ABI（NativeAdreno user client 1..16 号请求）与我们上游选定的 msm DRM 协议面不同，且其内核组件许可混杂（MIT + 厂商 GPL 参照），我们按 阶段 15 政策只把 GPL 厂商源当"源码参照"。
3. **PHK110 自己的 vendor gen7 参照已在盘上（本轮最重要的现成资产）**：阶段 15 入盘的 `~/hakios/refs/kernel_oneplus_sm8475/drivers/gpu/msm/`（133 文件）内含完整 gen7 kgsl 驱动族（`adreno_gen7.c/adreno_gen7_gmu.c/adreno_gen7_hfi.c/gen7_reg.h/adreno-gpulist.h` 等）。其中 `adreno-gpulist.h:2112` 的 **`adreno_gpu_core_gen7_4_0` 条目（compatible = "qcom,adreno-gpu-gen7-4-0"——正是我们 DTB 节点的 compatible [DTB:20052]）**直接给出：GMEM 2 MiB、`highest_bank_bit=16`、固件名三件套、GMU 固件版本 GMU_VERSION(4,0,7)、hwcg/gbif/protected_regs 表指针 [VENDOR，实证]。v0.5 的"数字层" ground truth 不需要再找。
4. **chipid 0x07030002 的两个生态口径都核实了**：Mesa 25.0.7 `freedreno_devices.py:1047` 明确 `GPUId(chip_id=0x07030002, name="FD725")`（注释"These are named as Adreno730v3 or Adreno725v1"，CHIP.A7XX + a7xx_gen1，highest_bank_bit=16 与 vendor 一致）[MESA，实证]——上游 25.0.7 pin **认识我们的 GPU**。mainline Linux 的 a7xx_catalog.c 只登记 `0x07030001`（a730），**无 0x07030002 条目** [UP，实证]——mainline msm 对本机 chipid 会 probe 失败；对我们无影响（内核驱动自研、chipid 从 DT 来），但引用 mainline 做寄存器参照时要记得身份表差一档。
5. **任务书输入勘误一处**：任务书写"gen7-gmu@3d6a000"；本机 DTB 实为 **`qcom,gmu@3d69000`，首个 reg 窗 `0x3d68000 + 0x37000`**（"rscc"窗 `0x3d50000 + 0x10000`、gmu_pdc `0xb290000+0x10000`、gmu_ao_blk_dec0 `0x3d40000`）[DTB:20301-20304]。0x3d6a000 是 mainline sm8450.dtsi 的节点编号，不是这台手机 vendor DTB 的数——gen7 寄存器字偏移重算必须用 0x3d68000 基（补丁 0002 已按 DTB 落）。
6. **上游 GPU 用户态接口形态核实（任务书问题的直接答案）**：`hakios.adreno.c` 唤醒 GPU 后，`hakios.gpu.cpp` 以 **HakiosGPU（IOKit user client）原样讲 Linux msm DRM 的 ioctl 协议**——原文："A program that opens it speaks the interface of Linux's msm DRM driver, the one Mesa's freedreno knows…（userland: tools/mesa/hakios-drm, which stands in for libdrm inside Mesa）" [GPU.CPP 头注，实证]；`tools/mesa/freedreno-darwin.patch` 把 Mesa 的 meson 配置改到无 DRM 平台用这个替身，IOSurface 以 buffer-handle 形式进出。**结论：没有 kgsl 用户态后端这回事——Mesa freedreno 走 msm_drm 协议、经 shim 到内核；a7xx 的全部差异留在内核侧**，用户态只有参数面（CHIP_ID/GMEM_SIZE/HIGHEST_BANK_BIT 等，`hakios_gpu_parameter` [ADRENO:3257]）随补丁 0005 改值。
7. **固件拉取脚本已实装并自测**：`wave35-scripts/pull-firmware-root.sh`（Magisk root 暂存法：`su -c` 拷 `/data/local/tmp/fw-phk110` → `chmod -R a+rX` → `adb pull` → 删暂存；范围 = fw-gpu/fw-wifi/fw-audio，modem 留 v0.7、haptic 本机无固件文件）。`--dry-run` 无手机自测通过（bash -n + 全 manifest/序列打印，零 adb 调用）；真机实拉与"a730 真名落档"**待设备空闲**[TODO-DEV]。物料名已从两个独立来源预填：本机 vendor gpulist [VENDOR] 与 MIX Fold 2 的 proprietary-files.txt（MIUI V14.0.15.0.TLRCNXM：`a730_sqe.fw, gmu_gen70000.bin, a730_zap.mdt/.b01/.b02`）[ZIZHAN，实证]——ColorOS 真名以手机上第一次 `su -c ls` 为准，脚本第一步就是列名。
8. **Mesa 选型建议（详 §4）**：**首图走 25.0.7 不动 pin**（上游 22 步管线、mesa patch 族、ir3 patch 族全部按它调通，且 FD725 身份在 25.0.7 已在表）；**首图之后做 25.0.7→25.3.3/26.0.x 的 diff 评估**再升（Mesa 26.0.0 的 a7xx 修复批量存在 [实证 relnotes]，landscape 2026-11-08 §3-I 的"Linux 侧 Adreno 730 GL/GLES/Vulkan 实测全通"为社区口径 [实测转述]）。Turnip/m2v 路线与 freedreno GL 路线共享这些建议。

---

## 1. 案例研究：MIX Fold 2（zizhan）的 GPU 是怎么点亮的（任务 1）

### 1.1 项目身份与谱系

| 项 | 事实 | 证据 |
|---|---|---|
| 仓库 | `qiumochen/UniXNU-zizhan`，非 fork，自述"Derived from UniXNU-pong"，uniXNU format 2 四层仓（board.toml/porting.toml/drivers/dts/patches/…） | [ZIZHAN] 仓库 README_EN + contents API |
| 目标系统 | iPadOS 18.7.10（22H374），Darwin 24.6.0 / XNU 11417.140.69，iPad7,11 (J171AP) 输入 | README_EN:5 |
| 基座 | `Chengdong-Yu/UniXNU-pong`（Nothing Phone 2，**SM8450，Adreno 730**），"SoC 层、PongPlatform24 组件和多数驱动复用，zizhan 改动 = pong `64ddf28` 之后的提交" | README_EN:7 |
| 固件仓 | `qiumochen/uefi-zizhan`（uefi-pong + `Platforms/Xiaomi/zizhanPkg`） | README_EN:9 |
| 证明材料 | 内屏 iPadOS 主屏照片（2160×1916@120Hz 路径）、dated 进度文档 40 篇、porting.toml 106 KB 结构化移植台账 | README_EN:13 + docs/progress/ |

谱系要点：** pong 是第一台 Adreno 730 的 UniXNU 机器**（SM8450 与 SM8475 的 GPU 同族 gen7-4-0 口径），zizhan 的 GPU 层几乎原样继承、只换板级数字——这恰好证明"同族 GPU 换板级参数"是可行工作量模型，与我们 F14 §2.3 判定的"新写参数层（方法论同）"一致。

### 1.2 GPU 栈逐项（任务书四选一的答案：都不是/自研+Turnip）

| 任务书候选 | zizhan 实况 |
|---|---|
| hakios.adreno 适配？ | **否**——无 hakios.adreno.c 痕迹；其内核驱动自述引用"Earlier port redwood_adreno.c: separation of platform power…Its A642L register/firmware values are not applicable here"（读过同族 a6xx 前辈的做法，明确说 a6xx 数字不适用）[PongAdreno README "Sources and differences"] |
| freedreno（GL）？ | **否（内核侧协议面不同）**——其用户态没有 freedreno GL 描述；README 只报 Turnip（Vulkan）；内核对外 ABI = NativeAdreno user client 自定义 16 请求（BO 分配/导入、VA 窗、提交、真 fence/状态/计数器）[PongAdreno README v96 段 + UPSTREAM-PORT.md]，不是 msm DRM ioctl 协议 |
| Turnip？ | **是（用户态）**——"metal/ and turnip/ contain the iOS16.6.1 userspace bridge and Vulkan library" [PongAdreno README:188-189]；iPadOS 18 窗户服务器吃 Metal，链路 = Metal → metal2vulkan → Turnip → 其内核驱动 |
| ios-sweet 系假驱动？ | **否**——Zizhan 属 UniXNU（takasugl/UniXNU 同名字空间的另一 org 谱系，F16 §⑦-6 待摸清项），非 dipa-studio/ios-sweet 基座 |

内核侧改动形态（drivers/PongAdreno/，26 文件 + submit/ 52 文件）：`PongAdrenoPlatform.cpp`（GCC/APSS DRV2 TCS3/command-db 适配、GMU SID5/0x405 上下文、 ramoops 诊断 pmsg）+ `PongAdrenoGmu.c`（资源窗/固件装载计划/RSCC-PDC 序列/GMU chip-id 换算 0x07030200）+ `PongAdrenoHfi.c`（vendor HFI 队列序列化与 ACK 匹配）+ `PongAdrenoPower.c`（58 词 PERF/159 词 BW 载荷）+ `PongAdrenoClocks.c`（CX GDSC + cape 200 MHz GMU/150 MHz HUB/XO）+ `PongAdrenoSmmu.c/ArmSmmu4K`（租约式流上下文）+ `PongAdrenoZap.c`（ELF32 MDT 规划 + PAS13 shutdown/init/mem-setup/auth-reset）+ `PongAdrenoCp.cpp`（gen7-4-0 HWCG/GBIF/protection/restore）+ `submit/`（NativeAdreno 的 PM4/ring/CP-init/timer/IRQ 等 52 文件，MIT）。[ZIZHAN drivers/PongAdreno 目录清单 + README，实证文件层；运行结果为实测转述]

### 1.3 它的"能抄清单"与"抄不得清单"

**能抄（已全部进 §2 的差异表与补丁骨架）**：SM8475 GPU 全套板级事实（寄存器窗、GMU 打包 chipid、HFI 布局、PAS13、zap 分段语义、GMEM、CP init 要求、IRQ SPI300/INTID332、ACTLR 0x32b、LPAC 流、GPUCC PLL 值、固件文件名与大小语义）；方法论（把 vendor gen7 驱动当"寄存器事实来源"、用 ramoops pmsg 记每阶段结果、"GMU 完成不算硬件加速，CP 真执行才算"的验收纪律）。

**抄不得/不适用**：(a) 内核驱动代码本身（ABI 不同 + 许可混层，且 ours 有 msm-drm 协议面的历史包袱/资产）；(b) display 路径（PongAdrenoScanout 97 KB 是它自己的 Mini framebuffer 适配，我们已有 23.x MiniIOMFB 出画链）；(c) iPadOS 18 用户态的一切（我们 16.5 线）；(d) 它的 WiFi（zizhan 是 QCA6490 形态实验配置，我们是 WCN6750——同 ath11k 族但不是同一个 hw_rev，wave30 已辨）。

**状态边界（诚实）**：GPU-01 DEVICE_VERIFIED 的含义是"正常启动覆盖 + 真 CP 完成计数（g380/g381：CP1843/1843、1777/1777）+ 四张完整主屏采样"，**冷启动画布失败（g342）根因未解决**，动态壁纸 GPU 访问保持禁用（GPU-02 TODO），"95.3 fps"是合成滚动单场景、非全局 120 fps [ZIZHAN STATUS.md，实测转述]。这些限制不影响"SM8475 GPU 可以在此类栈上点亮到日常可见"的结论成立。

---

## 2. a6xx→gen7 适配设计（任务 2）

### 2.1 上游接口形态（先答"怎么对接 Mesa"）

`hakios.adreno.c` 是 22 步唤醒法（步法全文 [ADRENO:1-95]）：外部时钟/RPMh 名 → 熔丝 → gpucc → CX 开关 → GMU 寄存器窗 → GMU-RPMh 通道 → GPU SMMU → GMU 内存读写 → TZ 问询 → zap 签名（PAS13） → GMU 页表+固件 → GMU 配置+出复位 → HFI 队列 → GV 表+3D 核上电 → 3D 核上下文+SQE 微码 → zap 装载 → 3D 核寄存器+CP 首命令 → 出安全模式 → 画三色图。

用户态对接（本轮逐字核实，非转述）：
- `hakios.gpu.cpp` 头注："A program that opens it speaks the interface of Linux's msm DRM driver, the one Mesa's freedreno knows: every request of that interface is a call of the user client with the request's number as the selector and the request's structure passed in and back (userland: tools/mesa/hakios-drm, which stands in for libdrm inside Mesa). What Linux does with mmap() on the device is the client memory of the type that is the buffer's handle." [GPU.CPP:3-6]
- 参数面 `hakios_gpu_parameter` [ADRENO:3257-3295]：0x01 GPU_ID / 0x02 GMEM_SIZE（现 512 KiB = 642L 值）/ 0x03 CHIP_ID（GPU_CHIP_ID|bin<<32）/ 0x04 MAX_FREQ / 0x07 PRIORITIES / 0x10 HIGHEST_BANK_BIT（现 14）/ 0x12 UBWC_SWIZZLE / 0x13 MACROTILE_MODE。
- Mesa 接线：`tools/mesa/freedreno-darwin.patch` 改 meson（"No DRM on this system: freedreno's requests go to the kernel's driver through a stand-in for libdrm"）+ freedreno_bo.c 的 IOSurface 导入分支；`tools/mk-mesa.sh` pin Mesa **25.0.7**（SHA256 592272df…），DRIVERS="softpipe,freedreno"，用 xnu-clang 对 iPhoneOS16.5 SDK 出 libOSMesa.8.dylib。

**对 v0.5 的直接结论**：a7xx 化是**纯内核侧 + 参数值**工程。msm DRM uapi 的请求编号/结构跨 a6xx/a7xx 不变（freedreno 以 DRM 参数取 chipid/GMEM/HBB 再查自己的设备表——FD725 条目在 25.0.7 已备 [MESA]）；Turnip 路线（上游 11-03 已全链真机验证，F14 §3.3）同理经 HakiosGPU。不存在"给 Mesa 加 kgsl 后端"的工作项。

### 2.2 a6xx(642L/redwood) → gen7(730/PHK110) 差异清单

逐层列出，全部带证据；"同"表示该层无需改动。

| 层 | redwood（a6xx/a642L） | PHK110（gen7/a730v3） | 判定 | 证据 |
|---|---|---|---|---|
| 身份 | chipid 0x06030500，无 chip-id 寄存器，熔丝唯一身份源 | chipid **0x07030002**（Adreno730v3），gen7 同样无可读 chip-id 寄存器 | 换值 | [ADRENO:56-58]；[UP a6xx_gmu.c 注释"a6xx could read the chip id from the GMU, but gen7 can't"]；[DTB:20062-20063] |
| GMU chipid 打包 | 半字交换 0x06030500→0x06035000，写 GMU_HFI_SFR_ADDR | 新打包 minor/patch 各占 4 bit：0x07030002→**0x07030200**，写 **GMU_GENERAL_10**（GMU 日志窗→GENERAL_8） | 换值+换寄存器 | [ADRENO:1881]；[UP a6xx_gmu.c:1012-1036]；[PONG "GMU chip-id conversion to 0x07030200"] |
| 固件文件名 | a660_zap.mdt/.b00-.b02、a660_gmu.bin、a660_sqe.fw | **a730_zap.mdt/.b01（代码）/.b02（证书哈希元数据）**、**gmu_gen70000.bin**、**a730_sqe.fw**（vendor 装载头选 b01；SQE 跳首个头 dword——上游代码已有 +4 跳过 [ADRENO:2577]） | 换值+zap 分段语义 | [VENDOR adreno-gpulist.h:2064-2067/2129-2132]；[ZIZHAN proprietary-files.txt]；[PONG zap 段] |
| PAS 镜像号 | PAS_GPU=13 | 13（不变） | 同 | [ADRENO:1515]；[PONG "PAS13 shutdown/init/mem-setup/auth-reset"] |
| zap 保留窗 | gpu_micro_code@8b71a000 | **0x8b91a000 + 0x2000**（与我们 DTB 保留内存一致 [DTB:150]） | 换值 | [PONG "Reservation is 0x8b91a000/0x2000"]；[DTB] |
| GMU 窗口 | gmu 0x3d6a000+0x34000 | **gmu 0x3d68000+0x37000**、gmu_pdc 0xb290000+0x10000（redwood 步 19 的 0xb294500/0xb294520 在此窗内）、gmu_ao_blk_dec0 0x3d40000；**mbox "aop"**（redwood gmu 节点无此 mbox） | 换值+新窗 | [DTB:20301-20312]；[ADRENO:890, 2018] |
| RSCC（GMU 的 RPMh 序列器） | rscc 0x3de0000+0x2000 | **0x3d50000+0x10000**；SEQ_MEM_0_DRV0 字偏移 0x180 不变（GEN7_6_0 变体 0x154 非本机，勿借） | 换基址，偏移大部同 | [ADRENO:976]；[DTB:20055]；[VENDOR gen7_reg.h:1211/1218]；[PONG "RSCC sequencer memory starts at dword 0x180"] |
| HFI | a6xx 布局（步 16 起 4.0 族表） | **17 保留头槽、表 210 dwords、队列存储自字节 848（16B 对齐）、3 活跃队列、debug 优先级 40**；vendor 序列化器 adreno_gen7_hfi.c 为完整参照 | 换布局 | [PONG "In particular…17 header slots"]；[VENDOR adreno_gen7_hfi.c] |
| TCM 保持 | GMU_GENERAL_7=1 | **CX_MISC 窗（REG_A7XX_CX_MISC_TCM_RET_CNTL=1）**；cx_misc 基址不变（0x3d9e000 [DTB]） | 换寄存器 | [UP a6xx_gmu.c:970-975] |
| AHB fence 范围 | lower 0xa0 / upper 0xa | lower **0x8a0** / upper **0x32** | 换值 | [UP a6xx_gmu.c:988-1002] |
| GMU 计时器 | （a6xx 无此差异项） | 偏移 **0x16220/0x16224**（A740/sheng 是 0x14220/24——不可跨代借） | 换值 | [PONG "The GMU timer's offset…"] |
| 时钟 | gpucc-sc7280（gpucc 基址 0x3d90000 两代同址 [DTB:838]） | **cape-gpucc：LUCID_OLE PLL0 L/alpha 0x1d/0xb000、PLL1 0x34/0x1555**；初始 GMU 200 MHz/HUB 150 MHz 取 GPLL0；**CM3 引导前先放 CX GBIF halt** | 换 PLL 表+时序 | [DTB:838-840]；[PONG "Pong's Cape GPUCC…"/"CX GBIF halt"]；[VENDOR drivers/clk/qcom gpucc-waipio + cape fixup] |
| GV/速度 | 3 速表 {315/450/550 MHz @ level 64/128/192} [ADRENO:2290] | vendor DT 13 档 pwrlevel（顶 **900 MHz** = 0x35a4e900 [DTB:20088]）；GMU 侧为 **58 词 PERF / 159 词 BW** 载荷（command-db aux 数据构建） | 换表+换载荷形态 | [PONG PongAdrenoPower]；[DTB qcom,gpu-pwrlevels] |
| GPU SMMU | 0x3da0000，两流（核流+空上下文流 hack adreno_stream1） | 同基址，窗加宽 0x40000；**QSMMU V500、ACTLR 0x32b、3 级表、21 ctx bank/24 SMR**；流 = **gfx3d_user SID0/0x400 + gfx3d_lpac SID1/0x400（gen7 新增 LPAC：A730 固件在处理 PM4 前启动 BR/BV/LPAC，BR 于 PC0xa2 等 THREAD_SYNC 信号量）**+ gmu SID5/0x405；secure SID2/0x402 不租 | 换流布局 | [DTB:19756-19790]；[PONG LPAC/SID 段] |
| GBIF/CX | gbif = kgsl_base+4*0x3c00 | 基址同（kgsl 0x3d00000+0x40000 [DTB:20053]），表换 gen7_0_0_gbif_regs | 换表 | [VENDOR adreno-gpulist.h gbif 字段] |
| 保护寄存器 | a6xx 表 | **a730 protect 48 条**（mainline a7xx_catalog.c 与 vendor gen7_0_0_protected_regs 双源在证） | 换表 | [UP a7xx_catalog.c:137-189]；[VENDOR] |
| HWSCH/HWCG | a6xx reglist | **a7xx 表 + 新寄存器域（REG_A7XX_RBBM_CLOCK_MODE2_GRAS/_BV_GRAS）**；vendor gen7_0_0_hwcg_regs | 换表 | [UP a7xx_catalog.c:22-52]；[VENDOR] |
| CP 命令流 | PM4，CP_ME_INIT、CP_SET_SECURE_MODE（步 20/21） | PM4 不变；**CP_ME_INIT 关 DMS bit11**；GMEM **2 MiB**、uche_gmem_alignment 0；含 vendor 终结动态恢复三元组 `PIPE_NONE, RBBM_PERFCTR_CNTL, 1`（即使计数器关闭） | 换 init 要求 | [PONG CP 段/submit/]；[VENDOR gmem_size]；[UP gmem=SZ_2M] |
| IRQ | 单 GPU SPI | SPI 300/INTID 332（DTB kgsl_3d0_irq <0 0x12c 4> [DTB:20056]，与 pong 同线）；第二线 freq_limiter SPI286（0x11e）redwood 未用，先不接 | 同+记录 | [DTB:20056-20057]；[PONG "SPI300/INTID332"] |
| 最高 bank 位/UBWC | HBB 14、UBWC_SWIZZLE 6、MACROTILE 1 | **HBB 16**（vendor=Mesa 双证）；ubwc-mode DTB=0x04；swizzle/macro 值待真机定 | 换值（HBB 已定，UBWC TODO-DEV） | [VENDOR highest_bank_bit=16]；[MESA 25.0.7 FD725 highest_bank_bit=16]；[DTB:20066] |
| GMEM | 512 KiB（参数面） | **2 MiB** | 换值 | [ADRENO:3269]；[VENDOR/UP] |
| GMU 固件版本门 | GMU_STARTED_MASK 0x1ff（>0x20010004） | vendor 期望 GMU_VERSION(4,0,7)；首引导读 DTCM 版本词记录，先不硬门 | 待真机 | [VENDOR adreno-gpulist.h:2126]；[ADRENO:1882-1884] |

### 2.3 补丁骨架（scratch，不 apply）

五文件 + README，全在 `workspace 根/scratch/wave35/patches/`（仓外，不入库）：每个 hunk 带本地树逐字锚（2026-11-11 只读核对），`@@` 行号为近似值，应用前 `patch -l` 或重锚；`[TODO-DEV]` 项留待真机验证。

| 文件 | 内容 | 状态 |
|---|---|---|
| 0001-a730-identity.patch | GPU_CHIP_ID 0x07030002、GMU_CHIP 0x07030200、熔丝 cell 偏移 TODO-DEV | 骨架完成 |
| 0002-a730-address-map.patch | gmu/rscc/smmu 窗按 DTB；pdc 新窗；gcc/gpucc/gbif/cx_misc 同址注记 | 骨架完成 |
| 0003-a730-firmware-names.patch | 三个 image_file 名换 a730 族；zap b01/b02 语义注记；ColorOS 真名 TODO-DEV | 骨架完成 |
| 0004-a730-gmu-rscc.patch | chipid 投递寄存器、TCM/CX_MISC、fence 范围、HFI 布局、RSCC/PDC、cape PLL/时钟、GV 载荷、GMU 版本门（9 子项，多项 TODO-DEV） | 骨架（议题清单型） |
| 0005-a730-smmu-cp-params.patch | 流布局（LPAC 决策点）、CP init 要求、参数面 GMEM/HBB 换值、UBWC TODO-DEV | 骨架完成 |

施工纪律沿用驱动自带 22 步法：五个补丁按 0001→0005 顺序、每补丁之间用 `adreno=N` 分步门控开机（上游已经把"一步一停、读先行于写、失败即止"的观测协议写死在驱动头，跨 SoC 移植正是它的用武之地）。

---

## 3. pull-firmware-root.sh（任务 3，F14 Top3#1 实装）

产物：`wave35-scripts/pull-firmware-root.sh`（136 行）+ `.gitignore` 两条（fw-stage/fw-phk110 永不入库）。

- **方法**（照 F14 §4.1-B 的上游 root 变体）：`su -c`（Magisk/KernelSU）把固件拷进 `/data/local/tmp/fw-phk110/{gpu,wifi,audio}` → `chmod -R a+rX` → `adb pull` → 手机侧删暂存。手机零改动。
- **范围**（按任务书物料清单）：fw-gpu（a730_sqe.fw/gmu_gen70000.bin/a730_zap.*）+ fw-wifi（`/vendor/firmware/wlan` 整目录拷贝——本机 WCN6750 走 PCIe/MHI，**不是 redwood 的 wpss.\***，F14 §2.3 已辨）+ fw-audio（adsp.\*，TZ image 1）。modem.\*+image/ 留 v0.7；haptic 不拉（PM8350B HV 无固件文件）；vendor DTB 已在盘（阶段 1）不拉。
- **WiFi 纪律**：ath11k 侧门 `wave30-scripts/check-phk110-wifi-fw.py` 要求 `WCN6750/hw1.0/{amss,m3,board-2}.bin` 并**拒绝"通用 bdwlan.bin 而无设备 board-2.bin"**（raphael 教训条款）；脚本头注与收尾提示都指向该门——Android 侧拉回的是 qca6490 族 vendor 文件（BDF = bdwlan.elf.<variant> 候选），映射/改名在主机侧做，门不放宽。
- **自测（无手机部分）**：`bash -n` 通过；`--dry-run` 全程零 adb，打印 manifest（GPU 固定文件+glob、wifi 目录、MAC 候选路径 [TODO-DEV]、audio glob、明确"不拉"清单）、真跑六步序列、主机侧收尾清单（sha256 注册表回填、wifi-fw 门、GPU 进小镜像 `userland/build.sh GPU=1`）。真机探测段（第 2 步 `su -c ls /vendor/firmware` 报真名）**标注待设备**[TODO-DEV]。
- **迁移路径**：长期归属 = WSL 树 `devices/phk110/pull-firmware.sh`（占位脚本自己写明"参照 devices/redwood/pull-firmware.sh 写"）；树解冻后复制过去，保持 fw-*/ 输出布局与上游 consumer（userland/build.sh 的 GPU=/ADSP= 开关）兼容。
- **诚实边界**：真拉路径未真机验证验证（adb pull 目录语义按上游同款假设）；`/vendor/firmware/wlan` 在 ColorOS 的存在性/形态未核（F14 候选位 `/vendor/firmware/wlan` [待核]）；MAC 文件真实路径未核。

---

## 4. Mesa/freedreno 选型矩阵（任务 4）

| 维度 | 25.0.7（上游 pin） | 25.3.3（2026-01-01 稳定线） | 26.0.0（2026-02-11） |
|---|---|---|---|
| 我们的 GPU 身份 | **FD725=0x07030002 在表**（freedreno_devices.py:1047，CHIP.A7XX/a7xx_gen1/HBB16）[MESA 实证] | 同表（演进不删身份）[推断] | 同表 [推断] |
| a7xx 修复面 | 基线（上游 22 步+ir3 patch 族按它调通） | 25.3 累积修复（a7xx 批量）[landscape §3-I，二手] | **a7xx 大批**：GRAS_LRZ_CB_CNTL 文档化、LRZ 元数据定义、BV ROQ 状态寄存器、concurrent binning 等 [本轮直读 relnotes 实证标题] |
| 上游实证 | redwood 真机 100-104 fps 滑动/F14 §3.3 [实测转述] | 无上游数据 | 无上游数据 |
| 对 v0.5 的判定 | **首图锁定**：pin 不动、patch 族不动、HakiosGPU msm-drm 面+FD725 身份即可 | 升级候选（diff 评估后） | 升级候选（同上；修复面最宽） |

建议（写成可执行项，进 §5 施工单）：
1. **v0.5 首图 = 25.0.7**。理由：设备表认识 0x07030002 [实证]；上游把 meson/ir3/OSMesa 的Darwin patch 族钉在这个版本上（`tools/mesa/*.patch` 是对 25.0.7 源树的，`mk-mesa.sh` 用 patch 集 SHA256 失效缓存）；跨 GPU 代际首图变量越少越好。
2. **首图后做一次升级 diff 评估**（0.5 天准备工作）：`mk-mesa.sh` 换 25.3.3/26.0.x + patch 族重锚，重点读 a7xx 相关 ir3/TU 修复与我们补丁 0005 的参数面是否有新查询（新增 DRM 参数时 shim 要跟上——这是升级的真实工作所在，不是版本号）。
3. **环境变量/开关**（上游管线内，无需新增）：GL 侧经 libOSMesa 上下文（eagl.c），无外部 env 依赖；Turnip 侧 `TU_DEBUG=sysmem`（landscape 记录 Bergamota/UniXNU 在用的旋钮，二手）留给 m2v 路线实验；上游 gpu_cached=1 / adreno_speed=N / adreno_keep=1 为内核侧既有旋钮 [ADRENO 头注]。
4. **Turnip/m2v 路线独立评估**：上游 11-03 起该链在 778G 全链真机验证（50-57 fps）[F14 §3.3 实测转述]，a730 在 Turnip 的支持面 ≥ freedreno GL（社区口径，landscape）；v0.5 顺序建议 GL 首图先行（上游验收线是窗口服务器经 Metal 出画 + 滑动 100-104 fps，路径即 freedreno+HakiosGPU）。

---

## 5. 施工单（转入 v0.5 GPU 工作当日）

| # | 事项 | 前置 | 产物/验收 |
|---|---|---|---|
| 1 | 真拉固件：`bash wave35-scripts/pull-firmware-root.sh`（wave16c WSL adb 配方 + Magisk） | 设备空闲 | 逐目录文件数行；**a730 三件真名落档**；全部文件 sha256；ColorOS 真名回填 0003 patch |
| 2 | WiFi 物料映射：wlan 目录文件 → `WCN6750/hw1.0/` 三件 + BDF 变体；跑 check-phk110-wifi-fw.py | #1 | 门 PASS（或如实 FAIL 记档）；SHA 注册表回填 |
| 3 | 应用补丁 0001+0002+0003 进 `devices/phk110` 驱动路径；`adreno=1..12` 分步开机（身份/地址/时钟/SMMU/TZ 问询/zap 签名） | 树解冻；#1 | 每步一行日志；步 2 熔丝读数（顺带定 cape qfprom cell，消 0001 TODO） |
| 4 | GMU 段（0004）：首装载 gmu_gen70000.bin；DTCM 版本词记录；HFI 表走通；GV 最低档上电 | #3 | GMU_STARTED/真 ACK；HFI 布局 TODO-DEV 消账 |
| 5 | CP 段（0005）：首命令、出安全模式、三色图 | #4 | 三色图上屏 = v0.5 "step 22" 达成线 |
| 6 | 参数面接 Mesa：25.0.7 + FD725 出 libOSMesa；eagl 首帧 | #5 | freedreno GPU 路径 `gpu=1` 生效 |
| 7 | Mesa 升级 diff 评估（25.0.7→25.3.3/26.0.x，patch 族重锚 + 新 DRM 参数对账） | #6 | 选型定案 + 如升级则出第二版 patch 族 |
| 8 | 顺手项：上游 2.3.3 fb_beam/fb_measure sc7280 门控核查 + `metal.args` 范式起步（F14 Top3#2 依赖） | 树解冻 | 23.x 出画链无踩雷结论 |

## 6. 诚实边界

1. **zizhan/pong 全部运行结果为实测转述**（README/进度文档自述）：95.3 fps、GPU-01 DEVICE_VERIFIED、CPU/内存/显示各项，我们未复现；其冷启动画布失败（g342）根因未解决、壁纸 GPU 禁用、非全局 120 fps 均为其文档原话。判定依据取"文档+文件+结构互证"，不取单行自述（F16 对 thor 的教训沿用）。
2. **zizhan 内核代码不搬**：其驱动为 NativeAdreno（MIT）+ 自有适配层，对外 ABI 与我们 msm-drm 面不同；vendor gen7 kgsl（GPL）只作源码参照（阶段 15 政策），无逐字拷贝。
3. **补丁骨架未 apply、多处 TODO-DEV**（熔丝 cell、GENERAL_10/TCM 偏移重算、HFI 表、PDC 序列、cape PLL、UBWC swizzle、LPAC 决策、ColorOS 固件真名）——骨架的 hunk 行号为近似，应用前重锚；0004 是议题清单型骨架（把九个 gen7 差异议题与其证据源钉住），不是可一次 apply 的成品。
4. **Mesa 26 修复面为标题级实证**（relnotes 条目直读），无 26.x 任何真机数据；landscape 的"Linux 侧 Adreno 730 全通"为社区兼容表口径（二手）。
5. **mainline 身份表缺口**（0x07030002 不在 a7xx_catalog）是 master 时点事实；后续内核若补条目，本报告 §0-4 相应失效——不影响我们（驱动自研），只影响"拿 mainline 当运行参照"的场景。
6. **pull 脚本真跑未测**（零手机）：adb pull 目录落位语义按上游同款脚本假设；ColorOS 侧 `/vendor/firmware` 与 `/vendor/firmware/wlan` 的真实形态、MAC 文件路径均 TODO-DEV。
7. **上游设备仓（hakios-sm7325）的 pull-firmware-root.sh 逐字对照基准**来自 pinned commit 04fbfff（upstream-manifest 在案）；上游若更新脚本，以 sync 后为准。
8. 构建树零写入复核：本轮对 `~/hakios/` 只执行过 ls/wc/head/grep/sed 只读命令；`upstream-manifest.txt` 基线未动。

## 附录：本轮取证来源

**仓内（只读）**
- `docs/research/f16-k60-sm8475-census.md`（zizhan 一行结论的出发点）、`docs/research/f14-sd778g-zendot-survey.md`（pull-firmware-root 规范 §4.1/§5-Top3#1、DTB GPU 事实 §2.3）、`docs/research/landscape-2026-11-08.md`（Mesa 26/25.3 证据 §3-I）、`docs/waves/wave30-ath11k-tooling-prep.md`（WiFi 固件门/BDF 纪律/格式模板）
- WSL 只读：`~/hakios/kernel/drivers/gpu/hakios.adreno.c`、`hakios.gpu.cpp`、`tools/mesa/{hakios-drm,freedreno-darwin.patch}`、`tools/mk-mesa.sh`、`devices/phk110/uefi/files/Resources/DTBs/phk110.dts`（GPU 节点 20051-20312、kgsl-smmu 19756、gpucc 838、保留内存 144-150）、`devices/phk110/{pull-firmware.sh,configs/phk110.config}`、`~/hakios/refs/kernel_oneplus_sm8475/drivers/gpu/msm/{adreno-gpulist.h,gen7_reg.h}`、`docs/driver-review/gpu-display.md`

**网络（代理 7897，2026-11-11）**
- GitHub API/raw：qiumochen/UniXNU-zizhan（repo 元数据、根目录、drivers/{PongAdreno,PongMetal} 清单、README_EN.md、proprietary-files.txt、docs/progress/STATUS.md、drivers/PongAdreno/{README.md,UPSTREAM-PORT.md}）
- torvalds/linux raw：drivers/gpu/drm/msm/adreno/{a7xx_catalog,a6xx_catalog,a6xx_gmu,a6xx_gpu,a6xx_gmu.h,adreno_device,adreno_gpu}.c/.h、arch/arm64/boot/dts/qcom/sm8450.dtsi
- GitLab raw：mesa/mesa mesa-25.0.7 `src/freedreno/common/freedreno_devices.py`（FD725=0x07030002 行 1047）；docs.mesa3d.org/relnotes/26.0.0.html（a7xx 条目直读）
- oosexgang/hakios-sm7325@04fbfff raw：pull-firmware-root.sh（2137 B，模板对照）

**仓外 scratch**
- `workspace 根/scratch/wave35/patches/`（README + 0001..0005 补丁骨架）；`/tmp/wave35-net/`（本轮网络取证的原始文件暂存）
