# 阶段 44 · 2026-11-12 · UniXNU/Adreno740 原生驱动文本调研：八仓只读对照五问

> 2026-11-11 起稿，2026-11-12 收尾 · 阶段 44 执行记录（准备工作波）
> 使命：研读 UniXNU org 的 Adreno740 原生 XNU GPU 驱动及配件仓（AdrenoPM4 / AdrenoFirmware / AirNir / AdrenoMetal / UniXNU 框架 / 板级 UniXNU-sheng / SoC kit UniXNU-sm8550-common），对照我们内核 GPU 驱动（wave37 首亮 + wave41 修复后），为 v0.5 下半场（真·首帧）与 v0.6 排期找参考。五问（fence / GMEM tile / 并发 binning / GMU-HFI / 稳健性与 license）逐答。
> 红线执行：零设备（无 adb/fastboot/usbipd/刷写）✓；`/home/cyrux/hakios/kernel/` 全树只读——驱动源 `hakios.adreno.c` 零字节改动（本轮首尾 sha256 均为 `356f5bf4a9f230f05…`，与 wave41 记账一致）✓；wave42-scripts/、wave43-scripts/ 零触碰 ✓；不做任何移植、不抄代码进内核树 ✓。
> 证据分级：[实证] = 文件/字节/sha/行号可复现；[对方-代码] = UniXNU 仓源码（逐条带 仓@commit:行号）；[对方-硬件] = 对方自称的硬件结果（commit 信息"Run on hardware"或设备记录），非我验证；[VENDOR] = `~/hakios/refs/kernel_oneplus_sm8475`（GPL，同机 kgsl，寄存器事实源）；[UP] = Linux 官方 tag（v6.12 `c3347937…`、master `9b725c1c…`、ubwc_config/ubwc.h，经代理拉取，只留 grep 摘录不进仓）；[MESA] = wave39/40 已核的 mesa 25.0.7 记录。
> 我树行号全部按当前 sha `356f5bf4`（wave41 修复后，3986 行）；任务书里的 :3567/:2983/:3844 是修复前行号，已按现值换算。

---

## 0. 判定（先行）

1. **Q1 fence：我树 wave41 的 `0x08000031` 首字获得对方同代原生驱动逐位佐证，形状完全同族；差异只有一位——对方主 fence 带 IRQ 位（bit31）**，因为他们的完成判定是"中断唤醒 + 完成趟扫"，我们是轮询。BV fence 则同样不带 bit31（[对方-代码] NativeAdrenoRing.cpp:290 `RingFenceEvent|RingFenceEnable`；主 fence :292 `|RingFenceIrq`；tests/test_ring.cpp:101/104 逐字断言）。**没有我们没移植的"第三个字段"**：bit31 = 中断型变体，bit20-22/24 的 WRITE_SRC/WRITE_DST 我们已按字段移植且取值相同（0=EV_WRITE_USER_32B、0=EV_DST_RAM）。
2. **Q1 完成判定**：对方 `fenceValue()` 读 fence 页 +4 的 RAM 字（NativeAdrenoRing.cpp:468-475，`fence_[1]`），读前做 CPU cache 维护（`cache_.acquire`）；`value>seqno_`（GPU 写了从未发出的编号）→ poison（:639/:657）。我树 `hakios_gpu_done` 读 `CORE_SCRATCH+0x40`（:3522-3528，`to_memory` 后判 `(int32_t)(*word - fence) >= 0`）——同一设计，无对方的"GPU 越号 poison"哨兵。
3. **Q2 GMEM tile：census 记的"GMEM tile 渲染为默认"当天就被更新了**。时间线（[对方-硬件] 均为对方自称）：12:39 AdrenoMetal `20be9f9` 把 `TU_DEBUG` 从 `sysmem,nocb` 改为 **`gmem,nocb`**（全 pass 进 tile 内存，并发 binning 关闭；三跑 410-550 s 无 hang）→ 23:36 `9ddfaf2` 改为 **Turnip 自选 + `tu_allow_concurrent_binning=true`**（每个 pass 由 Turnip 按规则选 GMEM/sysmem，并发 binning 开）→ 23:40 框架仓 `2c2e69f` bump 子模块 → 23:42 文档 `75f3542`。**GMEM 是用户态（Turnip）渲染模式决策，内核驱动的 GMEM 角色只有三件：UCHE GMEM 窗寄存器、`gmem_bytes/gmem_base` 经 ABI 报给用户态、抢占时 GMEM save/restore**（NativeAdrenoABI.h:153-161、NativeAdrenoPreempt.cpp:16/99）。对我们：wave39 已消账"GL 链不查 UBWC 参数"；本轮再消一笔——`UBWC_SWIZZLE=6` 这个 [TODO-DEV] 的值本身与多方参考一致（§3-4），TODO 可降级。
4. **Q3 BV/BR：对方给出 wave41 硬门条款的实机验证版本**。他们的框架提交正是按 wave41 写的门顺序走的：先有 BV fence+CP_WAIT_TIMESTAMP 三段尾包（早已在 emitFramedFence，:279-311），23:27 才上"BV 进度计入 GPU 进度"（`2a91aa1a`：BV 的 CP_BV_RB_RPTR 0x0a66/CP_BV_IB1_BASE 0x0a6d 等五词进 hangcheck 与 stall 采样——"BR 等可见性 pass 时 BR 自己的词全静止"），23:36 才开并发 binning。**开闸条件清单比 wave41 的三条多两条：BV RPTR shadow 地址寄存器（CP_BV_RB_RPTR_ADDR 0x0a98）要编程；hang/stall 检测必须读 BV 进度，否则会把正常工作的 GPU 当 hang 处置。**
5. **Q4 GMU/HFI/PM4：三层全同构，两处小差异**。PM4 包头编码与我树 `ring_command`/`ring_register` 逐位相同（AdrenoPM4.c:20-30 vs 我树 :2582-2592）；HFI 消息 id（PERF=4/58 词、BW=3/159 词、CORE_FW_START=14、START=10）与我树 :2107-2114/:2411-2437 一致，GMU 冷启动寄存器序列（AHB fence range `0x32<<18|0x8a0`、版本门 `≤0x20010004→0x1ff/0x100`）同构（ShengGmu.c:98/167/174）。差异：①队列表 `num_q/num_active_q` 字段对方=3（Linux/AdrenoFirmware.c:36 `shared[4]=3;shared[5]=3`；同机 vendor 非 hwsched 路径 adreno_gen7_hfi.c:17/189 同为 3），我树写 17（:1956，hwsched 文件 adreno_gen7_hwsched_hfi.c:21 的值；gen7_4_0 绑定非 hwsched 的 `adreno_gen7_gmu_gpudev`，adreno-gpulist.h:2112/:2121；wave35 引的 zizhan 事实表述是"17 头槽/210 dwords"——槽数与表尺寸，未见其计数字段值）——我树步 16/17 真机已绿说明固件容忍，属低优先观察项；②对方 HFI 启动多两个可选级（ACD enable=FEATURE 11/msg 11 feature 12、ACD 表 msg 7；IFPC=feature 9 data 0x1680），我树未发（无对应参考事实，不动）。
6. **新发现（前序阶段日志未登记）：我树 CP_ME_INIT 是 a6xx 形状，同机 vendor、Linux a7xx_cp_init、Adreno740 三方都是 a7xx 形状**。我树：`CP_ME_INIT, 8` 字、mask `0x0000082f`、后五字全 0（:2933-2942）；三方：7 字、mask `BIT(0)|BIT(1)|BIT(3)|BIT(6)|BIT(8)`（+vendor 的 DMS bit11 条件）+ operation mode `0x2` + pwrup reglist 地址 + BIT(31)（[VENDOR] adreno_gen7.c:101-148；[UP v6.12] a7xx_cp_init；[对方-代码] NativeAdrenoCpInit.cpp:48-55）。我树步 20 真机绿（"THE 3D CORE TAKES COMMANDS"）证明 CP 收下这个形状，但 mask 管辖的语义（BIT(6)=跨抢占关闭 perf 计数 save/restore、BIT(8)=pwrup reglist 登记、operation mode 序数）在步 20/21 的测试面之外。**定性：源码级偏差 CONFIRMED，设备级后果未测；非 bug 判定**（证据等级与 wave40 对 NC_MODE 的"配置不一致 CONFIRMED、像素级后果未定"同款）。
7. **同机 hw_init 的低优先偏差一揽子**（§3 详表，全部 [VENDOR]+[对方-硬件] 双源在证、我树未写或写法不同）：UCHE_CACHE_WAYS（0x4 vs 0x800000）、UCHE_CMDQ_CONFIG（未写 vs 0x6690e）、RBBM_GBIF_CLIENT_QOS_CNTL（3→0 两写 vs 0x2120212）、UCHE_GBIF_GX_CONFIG（未写 vs 0x10240e0）、CP_APRIV_CNTL（0x6e 无 ICACHE 位，BV/LPAC APRIV 未写 vs 0x6f/0x0f/0x0f）、CP_BV/LPAC_CHICKEN_DBG（未写 vs 0x1）、RB_CMP_DBG_ECO_CNTL bit11（未写 vs 置 1）、CP 保护表（全树无 CP_PROTECT 写入 vs vendor gen7_protect_init/sheng 46 条）、HWCG 表（wave37 已知刻意不做）、GRAS_NC_MODE_CNTL（直写一次 vs Linux master/sheng 按 pipe 经 CP_APERTURE_CNTL_HOST 写 BR+BV——我树与 [VENDOR]:503 直写一致，[UP v6.12]:602 也是直写）。
8. **Q5 稳健性：三条全部可借鉴，且对方把"证据等级"写进了 commit 纪律**——每条提交标注 "Run on hardware" / "Not run on hardware"（如 a7c83cf ring switch CP 状态保持 = **Not run on hardware**）。对我树：panic-free 我树已达标（grep `panic(` = 0 命中，超时全部有界），可借鉴的是**失败留痕的结构**（固定长 volatile 计数器数组 + poison 一票否决 + "No register may be touched before every argument is acceptable"）与 stall 分级（先采样判"是否在动"，动则什么都不做；50ms 无进度才 re-kick WPTR+TLB 失效；200ms 才 GBIF drain）。
9. **License 边界（Q5 后半，逐仓查清）**：UniXNU org 八仓全数可商用再许可——Adreno740/AdrenoPM4/AirNir/AdrenoMetal = **MIT**（LICENSE sha 8803ca32/9bcaf670/9b9bc8a5/424da216）；UniXNU/UniXNU-sheng/UniXNU-sm8550-common/AdrenoFirmware = **BSD-2-Clause-Patent**（GitHub 检测器标 NOASSERTION，LICENSE 原文带 `SPDX-License-Identifier: BSD-2-Clause-Patent` 行；框架仓与 AdrenoFirmware 两份全文读过，sheng/sm8550-common 与框架仓是**同一个 git blob `f63d2a6e`**，AdrenoFirmware 去版权行后正文哈希相同——四份是同一文本；四个 MIT 仓去版权行后正文亦相同，Adreno740 那份全文读过。机械比对见 evidence/license-blob-compare.txt）。**知识层 OK 无疑；代码层：MIT/BSD 均允许引入内核树**（我树为 BSD 类内核），但本阶段按红线零移植；未来引用时须带 attribution 与 sha 钉位。**PongAdreno 线（A730/同 SoC）的仓 license 全部 NOASSERTION 未读到原文——在查清前不得引入**（§6）。
10. **前提勘误（对任务书/census，不是对代码）**：census 2026-11-11 §3-1 "同 SoC 仍无人打通硬件层"与本项目自己的 wave35 §0-1（zizhan = "Adreno 730 with Turnip and metal2vulkan"，GPU-01 **DEVICE_VERIFIED**）及 F16 普查（zizhan A730 渲染、derived from UniXNU-pong）**自相矛盾**；且"全生态同代 7xx 原生驱动只有这一份在动"不成立——`drivers/PongAdreno/`（A730 专用，约 110 个 GPU 文件）公开存在于 `qiumochen/UniXNU-zizhan` 与 `Emilelu/UniXNU-mondrian`（后者 2026-11-11T16:25Z 仍在推送），`Chengdong-Yu/UniXNU-pong` 15:31Z 活跃。**坐标修正：K60 线本身没通（census 口径，我未复验）；但同 SoC 的 pong→zizhan/diting 线自报已通（A730 渲染/1030 个完成 command buffer），且其 A730 内核驱动 = Adreno740 仓 NativeAdreno 的同源核心 + SM8475 板级层**——这使 Adreno740 仓对我们参考价值更高（同核心），PongAdreno 的 SM8475 数字层则是下一份要读的。
11. **WPTR 丢弃现象是对方实机调过的坑，直接写进我们的 fence 探针预案**：GMU 在 GPU domain 未就绪时丢弃 CP_RB_WPTR 写并在 AHB fence status 置位，对方把它做成 fenced write（重试≤200 次，NativeAdrenoRing.cpp:114-135；[VENDOR] adreno_gen7.c:150 gen7_fenced_write 只用于 preempt 路径 WRITEDROPPED0/1）；i491 案例"fence 几乎每次提交都 stall，直到 stall handler 重写 WPTR（5361/5397）"。我树 `ring_send` 是裸写（:2618）。v36 真机 fence 探针若超时不回，除 bit27 外这是第二候选因。
12. **可执行增量清单（§5 详列）**：v36 判定轮预案新增两条观察项（WPTR fenced write、CP_ME_INIT 形状）+ 一条不变式（步 20-21 回归）；并发 binning 开闸清单补 BV RPTR shadow + BV 进度检测两条；UBWC TODO-DEV 降级理由在案。

## 1. 物证台账

### 1-1 clone 台账（全部在 `/home/cyrux/hakios/refs/`，各自新目录，chown cyrux:cyrux 与同目录其他仓一致；只读不执行，零 submodule 递归）

| 仓 | HEAD（clone 时） | 提交时间(本地) | commit 数 | 大小 |
|---|---|---|---|---|
| UniXNU-Adreno740 | `2a91aa1a14a33e97…` | 2026-11-11T23:27:40+08:00 | 158 | 2.1M |
| UniXNU-AdrenoPM4 | `282606b528b25952…` | 2026-10-25T02:03:54+08:00 | 3 | 324K |
| UniXNU-AdrenoFirmware | `20ad3d7aca14bd46…` | 2026-10-25T02:03:54+08:00 | 3 | 304K |
| UniXNU-AirNir | `b356371a74cd158c…` | 2026-10-25T02:03:54+08:00 | 3 | 424K |
| UniXNU-AdrenoMetal | `54ac1a006d274a9b…` | 2026-11-11T23:36:55+08:00 | 289 | 3.2M |
| UniXNU-UniXNU | `75f35420137371d1…` | 2026-11-11T23:42:47+08:00 | 810 | 52M |
| UniXNU-UniXNU-sheng | `14bf88adfadd1f86…` | 2026-11-11T23:41:31+08:00 | 611 | 8.9M |
| UniXNU-UniXNU-sm8550-common | `97665e2857848308…` | 2026-11-07T16:54:29+08:00 | 9 | 368K |

与 gh api 当场 HEAD 逐一对上（wave44-scripts/evidence/license-*.txt、clone-ledger.txt）。框架仓 HEAD 的子模块指针：drivers/Adreno740 = `2a91aa1a`、drivers/AdrenoMetal = `54ac1a00`（`git ls-tree HEAD drivers/`）——框架当夜自持。

### 1-2 我树冻结点

`/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c` = `356f5bf4a9f230f054b10a20b54dde982db398762802fc0a1732bb7c9b30ea3e`（3986 行；本轮首查与收尾复查一致）。零写入、零备份链新增。

### 1-3 今日四条关键提交（对方）

| commit | 时间(+08) | 标题 | 硬件证据标注 |
|---|---|---|---|
| `2a91aa1a` | 23:27:40 | fix(submit): count the BV thread's progress as GPU progress | （消息无显式标注；test_submit.cpp:331 新增 BV 断言） |
| `9578923` | 19:41:46 | fix(submit): leave a working GPU alone in the stall handler | Run on hardware: 四样本动着的 job 全部未处置；两跑无 hang |
| `4a3921a` | 17:20:22 | feat(vm): record the mapping a failed map met | Run on hardware: 窗口首地址的拒收 map 显示同尺寸映射在场 |
| `a7c83cf` | 10:47:43 | feat(submit): keep the CP state of a ring switch that never finished | **Not run on hardware**（原文） |

## 2. 五问逐答

### 2-1 Q1：fence/完成信号

**对方做法**（[对方-代码] Adreno740@2a91aa1a）：

- 两种提交两种尾包。内核 bring-up 提交（`emitFence`，NativeAdrenoRing.cpp:259-272，`RingFenceWords=7` "kernel bring-up submissions: TYPE4 scratch + TYPE7 event"）：`TYPE4 CP_SCRATCH(2)` 写 seqno + `TYPE7 CP_EVENT_WRITE(4)`。用户提交（`emitFramedFence`，:279-311，31 词）：见 §2-3 三段序。
- 常量（:20-23）：`RingFenceOpcode=0x46`（CP_EVENT_WRITE7）、`RingFenceEvent=0x31`（CACHE_CLEAN）、`RingFenceEnable=1u<<27`（WRITE_ENABLED）、`RingFenceIrq=1u<<31`；文件头注释（:7-12）声明值全部来自钉死的 Linux a6xx.xml/adreno_pm4.xml，"not guessed"。
- **首字**：主 fence = `0x31|BIT(27)|BIT(31)` = `0x88000031`（:292，tests/test_ring.cpp:104 `ring[38]==(0x31u|(1u<<27)|(1u<<31))`）；BV fence = `0x31|BIT(27)` = `0x08000031` **不带 IRQ**（:290，test:101）。写回地址 = fence 页 +4（`msm_rbmemptrs.fence`；布局注释在 restart() :430 "+0 rptr, +4 fence, +8 bv_rptr, +12 bv_fence"），写回字 = 32 位 seqno。**与我树 `ring_fence_event(EVENT_CACHE_CLEAN, CORE_SCRATCH_ADDRESS+GPU_FENCE_AT, gpu_fence)`（:3636-3637）逐字段同构，仅差：①bit31；②写回地址在他们 fence 页 +4、在我们 scratch 页 +0x40（同一"memptrs 页内 fence 字"概念）。**
- 完成判定：`fenceValue()` = cache acquire 后读 `fence_[1]`（:468-475）；`wait()` 循环 `value>=fence` → complete、`value>seqno_` → poison（:646-663）；README "Fence waits"：等待者睡眠，完成趟扫 ring 上的 fence 并唤醒，GPU 中断处理器 `native_adreno_gpu_interrupt(status)` 驱动该趟（IRQ enable 集 `kEnable` 含 `IrqBitCpFence=BIT(20)`，NativeAdrenoIrq.cpp:31/50）。我树 = 纯轮询（`hakios_gpu_done` :3522-3528；`hakios.gpu.cpp` gpuWait 以 `GPU_ASK_AGAIN_US`=200us（:172）间隔轮询 + ≥1000ms 超时置 `gGPUReported` 一票否决（:190-214，置位 :211））——**轮询/中断的选择差异，不是字段缺失**。
- 我树 wave41 对照（[实证] `ring_fence_event` :2598-2606；`FENCE_EVENT` 宏 :2540-2541；`CP_EVENT_WRITE7_SRC/DST/WRITE_ENABLED` :2537-2539）：首字 `0x08000031` 与对方 BV fence、vendor 非 IRQ 型（[VENDOR] adreno_gen7_ringbuffer.c:347/387 `CACHE_CLEAN | BIT(27)`）、Linux a7xx BV fence（[UP v6.12] :370）三方一致。**Q1 末小问"有无我们没移植的第三个字段"：无**——bit31 是中断型变体（我们要不要走中断完成是架构决策不是补丁），WRITE_SRC/DST 我们已按字段移植且值相同。

### 2-2 Q2：GMEM tile 渲染

**"GMEM 为默认"具体指什么**（[对方-代码] AdrenoMetal@54ac1a00、UniXNU@75f35420）：

- `01eb8692`（框架仓）只是子模块 bump；实体改动在 AdrenoMetal `20be9f9`（12:39）：`setenv("TU_DEBUG", "gmem,nocb", 0)`——**Turnip（Vulkan）的调试开关**：每个 pass 尽量在 tile 内存（GMEM）渲染，attachments 每 tile load/store 一次，memoryless attachment 不占内存；`nocb` = 并发 binning 关闭。配套 Mesa 补丁 `turnip-gmem-memory-side-swap.patch`（GMEM load/store 按图像自身 byte swap 处理色彩序，"0.0% of lock screen tiles exchanged"）——此前 sysmem 时代 "one home screen frame came out with red and blue exchanged" 的坑就是它修的（20be9f9 diff 摘文）。**Run on hardware: 三跑 410-550 s 无 hang 无 crash**（对方自称）。
- 同日 23:36 `9ddfaf2`：`TU_DEBUG` 不再强制，改 `setenv("tu_allow_concurrent_binning", "true")`——Turnip 按 pass 自选（memoryless/feedback loop 进 GMEM、少 draw 的 pass 进 sysmem、其余按带宽），并发 binning 开。文档 `75f3542`："Turnip chooses tile memory or system memory for each render pass, and concurrent binning is on"。**注意框架仓 docs/porting/gpu.md:110 在 HEAD 仍写旧口径（gmem,nocb 默认、binning 保持关闭）——框架仓两份文档 HEAD 互相矛盾**（gpu.md 是 e5f76cfe 的旧文，adreno-metal.md 是新文）。
- 与内核的关系：内核只暴露事实（`NativeAdrenoAbiDeviceInfo`：`gmem_bytes`、`gmem_base`、`highest_bank_bit`、`ubwc_swizzle`、`macrotile_mode`、`ubwc_version`，NativeAdrenoABI.h:153-161；板级填充 `gDeviceInfo = {0x43050a01, 3<<20, 0x1000000, …, 16, 6, 1, 4, …}` GpuPowerProbe.cpp:1042-1044）+ 抢占时 GMEM save/restore（`RB_CONTEXT_SWITCH_GMEM_SAVE_RESTORE_ENABLE 0x8e50=1`，NativeAdrenoPreempt.cpp:99）。分块/resolve/load-store 的 PM4 全在 Turnip 侧。

**对我们**：

- wave39 已裁定"freedreno GL 链不查 UBWC 参数（TODO-DEV 亦消账）"（README wave39 行）。本轮再消一笔**值本身**：`UBWC_SWIZZLE=6`、`MACROTILE_MODE=1`（我树 :3424-3428）与三方一致——[UP master] `ubwc_config.c`：`"qcom,sm8450"` 与 `"qcom,sm8550"` 同指 `ubwc_4_0_hbb16 { .ubwc_enc_version=UBWC_4_0, .highest_bank_bit=16 }`；helper（ubwc.h@master，blob `b09ae05c`）：`qcom_ubwc_swizzle` 非 1.0 版本一律 `LVL2|LVL3 = BIT(1)|BIT(2) = 6`、`qcom_ubwc_macrotile_mode` = `enc_version ≥ UBWC_3_1` → true=1；sheng 板级同值（6/1）。**原注释"the reference's 6; this phone's dt says ubwc-mode <0x04>"是把两个量纲并置**：dt 的 `qcom,ubwc-mode` 是 UBWC **版本**枚举（[VENDOR] msm_kgsl.h:248 `KGSL_UBWC_4_0=4`），4.0 版本推导出的 swizzle 恰是 6——不冲突。
- 首帧路径启示：GMEM 直渲（sysmem）是我们步 22（2D blit 三色带）的现有形态，保持不动即可首帧；tile 模式是**性能**项（对方 12:39 前的实测：GMEM 与 sysmem 的 GPU 时间 "17.8ms mean / 56.1ms p95 vs 17.1 / 52.1——no better"，20be9f9 diff 原文），排 v0.6。GMEM 模式的已知坑（红蓝交换、行距按 tile-aligned width 判定——`6061e102` "Turnip tests an attachment's row pitch, not its width"）值得在我们排期时当已知风险表抄录。
- **GMEM 大小差**：sheng A740 = 3 MiB（`UCHE_GMEM_RANGE 0x1000000..+3MiB`，GpuPowerProbe.cpp:1609-1610）；我树 2 MiB（`GMEM_SIZE` param :3406-3407，[VENDOR] gpulist gen7_4_0 gmem_size=SZ_2M）——chip 差异，非偏差，不动。

### 2-3 Q3：并发 binning / BV-BR

**对方三段尾包**（emitFramedFence，:279-311；[VENDOR] 同构 adreno_gen7_ringbuffer.c:333-365，gate 在 `is_concurrent_binning(drawctxt)`；[UP v6.12] :354-400）：

```
CP_SCRATCH(2)←seqno; CP_THREAD_CONTROL(SYNC_THREADS|BR)
[CP_REG_TO_MEM always-on 时间戳（end）]
CP_EVENT_WRITE(CCU_INVALIDATE_DEPTH 0x18) 1参; CP_EVENT_WRITE(CCU_INVALIDATE_COLOR 0x19) 1参
CP_THREAD_CONTROL(BV=2)
CP_EVENT_WRITE4  BV fence: 0x31|BIT27 → fence页+12 (bv_fence)
CP_THREAD_CONTROL(BR=1)
CP_WAIT_TIMESTAMP(0, bv, seqno)          ← BR 在此等 BV 的编号
CP_EVENT_WRITE4  主 fence: 0x31|BIT27|BIT31 → fence页+4
CP_THREAD_CONTROL(BOTH=3); CP_SET_MARKER(0x100 IFPC enable)
```

与 wave41 硬门注释列的三要素（BV 完成事件 + BR 完成事件 + CP_WAIT_TIMESTAMP，我树 :2919-2929）**逐条对应**。注释里另有两句对我树是增量事实：

- "User command streams synchronize the BR and BV threads themselves (Turnip waits on BV timestamps), so the IBs must run with both threads enabled."（:25-28）——用户 IB 跑 BOTH 线程，同步责任在用户态。
- **BV 进度计入 hangcheck**（`2a91aa1a`）：`bvProgressState()` 读 CP_BV_RB_RPTR 0x0a66 / CP_BV_IB1_BASE 0x0a6d / CP_BV_IB2_BASE 0x0a71 / CP_BV_IB1_REM 0x0a70 / CP_BV_IB2_REM 0x0a74 + CP_BV_ROQ_AVAIL_IB1/2 0x0a90/0x0a91 高半（Ring.cpp:523-535）；`madeProgress()` 与 noteStall 采样都加 BV 五词（Submit.cpp:966-980、:739-786 diff）——"BR waits for the visibility pass, so BR's own words stand still while the GPU works"。**没有这条，开并发 binning 的第一后果就是把正常 GPU 当 hang 修**（9578923 的教训同源：四个 stall 样本全是 100-160ms 的"tiled passes"在跑）。
- 抢占/双环需要 BV RPTR shadow：hw init 编程 `CP_BV_RB_RPTR_ADDR 0x0a98`（[UP v6.12] :1141；A740HwInit.h:35；sheng 同）；msm_rbmemptrs +8 = bv_rptr（Ring.cpp:93）。

**开闸条件对照表**（wave41 `#error` 门 vs 对方实践）：

| 条件 | wave41 门 | 对方 | 判定 |
|---|---|---|---|
| BV 完成事件（0x31\|BIT27 写 bv_fence） | 要求存在 | :290 实装 | 我树待补 |
| BR 主完成事件 | 要求存在 | :292 实装 | 我树已有同形（无 IRQ 位） |
| CP_WAIT_TIMESTAMP 前置 | 要求存在 | :300 实装 | 我树待补 |
| BV RPTR shadow 寄存器编程 | 未列 | hw init 必须（A740HwInit.h:35） | **门清单补一条** |
| hang/stall 检测读 BV 进度 | 未列 | 2a91aa1a 专项修复 | **门清单补一条** |
| 用户 IB 线程模式 BOTH | 未列 | :252/:302 BOTH | 门清单备注（Mesa 会自带 CP_THREAD_CONTROL） |
| 同步责任在用户态（Turnip 等 BV 时间戳） | 未列 | :25-28 注释 | 门清单备注 |

### 2-4 Q4：GMU/HFI/固件与 PM4 编码

**PM4 编码层（AdrenoPM4@282606b5）**：type-7 头 `0x70000000|count|odd(count)<<15|opcode<<16|odd(opcode)<<23`，type-4 头 `0x40000000|count|odd(count)<<7|reg<<8|odd(reg)<<27`（AdrenoPM4.c:20-30）——与我树 `ring_command`（:2582-2587）/`ring_register`（:2589-2596）**逐位相同**。对方增量 = 参数域校验（opcode≤127、count≤0x3fff、reg≤0x3ffff，"No silent masking"）+ 结构化解码器 `AdrenoPM4Plan`（逐包 round-trip 验头），并把"编码成功 ≠ 授权提交"写进每个 API 的契约注释——一个可借鉴的"包形验收器"思路，与我树 wave41 隔离自测的构造器同族。

**HFI 传输（AdrenoFirmware@20ad3d7a）**：表头 `shared[0..5] = {0, 168, 6, 12, 3, 3}`（AdrenoHfi.c:36；168=字节、6=首队列头词偏移、12=队头词数、3/3=队列数）——**Linux mainline 口径（num_q=3）**；我树 `hfi->words=210`（词）+ `queues=active_queues=17`（:1953/:1956）——**同机 vendor 口径的 size 字段（210 词 = 表头 6 + 17 槽×12）+ hwsched 文件的计数字段（adreno_gen7_hwsched_hfi.c:21）**；vendor 非 hwsched（gen7_4_0 绑定的 `adreno_gen7_gmu_gpudev` 路径）`num_q = HFI_QUEUE_MAX = HFI_QUEUE_DEFAULT_CNT = 3`（adreno_gen7_hfi.c:17/189-190）。我树步 16 "QUEUES ARE UP" + 步 17 HFI 全应答在真机成立 → 固件容忍两种计数；观察项，不回退。发送/应答：头 `(seq<<20)|(count<<8)|id`、`0xfafafafa` 填充到 4 词边界（AdrenoHfi.c:46-60，头 :57、填充 :60 vs 我树 hfi_send :2234-2252 同构）。

**HFI 启动序列（AdrenoHfiStartup.c:59-85）**：PERF(4) 58 词 → BW(3) 159 词 → [ACD enable = msg 11 feature 12 → ACD 表 = msg 7 36 词] → [IFPC = msg 11 feature 9, {1, 0x1680}] → CORE_FW_START(14) 1 词 → START(10) 0 词；每条命令等 ACK，"Only matching actual ACKs advance"。我树步 17：PERF(4)/BW(3)/CORE_FW_START(14)/GX_BW_PERF_VOTE(30)/START(10)（:2411-2437）——id 与载荷尺寸相同，多一个 GX vote（DCVS，对方放板级 `startGpuDcvs`），少 ACD/IFPC 两可选级（我树无 ACD 参考事实，wave37 观察项口径继续有效）。

**GMU 冷启动（Sm8550Platform/ShengGmu.c:96-205）**：先校验全停（SYSRESET=1 在位、TCM_RET=0、RSCC busy=0、HFI_CTRL_STATUS bit0=0）→ RSC setup 表 → FALNEXT/FAL=1 + TCM_RET=1 → ITCM/DTCM 写入 → **TCM 逐词读回比对** → 寄存器组（FW_INIT_RESULT=0、BOOT_CONFIG=2、HFI_QTBL_ADDR/INFO、AHB_FENCE_RANGE_0=`0x80000000|(0x32<<18)|0x8a0`、CM3_CFG=0x4052、GENERAL_10=chipid、GENERAL_8=log|3、SYS/ICACHE/DCACHE=1、QSB_SIDE0-3=0x71620）→ 释放 reset → 轮询 FW_INIT_RESULT（`≤0x20010004 ? 0xbabeface : 0x100`，mask `0x1ff`）→ HFI_CTRL_INIT=1 → 轮询 HFI_CTRL_STATUS。**与我树步 14-16（:1822/:1939/:2046）同构**（wave35 已换的 0x32/0x8a0、GMU_STARTED 0x100、GMU_FAILED 0xe00、chipid 打包 0x07030200 全数命中）；对方多出：固件整文件 sha256 先验、TCM 读回验证、"15 个块数断言"（a740 固件块数==15，:98）——都属于"加载后校验"的工程化，我树 zap 三段布局校验（wave37 ④）同思路。

**固件身份**：sheng gmu fw = 4.0.7（`GMU_VERSION(4,0,7)`）与我树步 14 读回一致（wave37 §3 "core 0x40000007"）；a730_sqe.fw / gmu_gen70000.bin / a730_zap 同名族（[VENDOR] gpulist gen7_4_0）。

### 2-5 Q5：稳健性三条 + license

**① ring switch CP 状态保持**（`a7c83cf`，**Not run on hardware**——对方自己标了）：switch 超时（watchdog 内 CP 未完成）的前两次，把 CP 的 stall 词组（`stallState()`：RBBM_STATUS/INT、CP_HW_FAULT/INTERRUPT/PROTECT、RPTR/WPTR、IB1/IB2 base+rem、ROQ avail，Ring.cpp:158-166 的 22 寄存器表）与进度词存进 `native_adreno_switch_timeout[2][30]` 再 markPreemptDead（Submit.cpp:278-299）。**可借鉴**：失败即取证，取证先于处置；固定形状、可被板级日志原样打印。我树对应面：`hakios_gpu_report`（:3644 起）打印同类寄存器——已有，但只在"submit 不回"时打，没有"预提交/切换"阶段的快照对（before/after），§5 给了低成本增量建议。

**② stall handler "不动正常 GPU"**（`9578923`，Run on hardware）：第一阶段动作（TLB 失效 + WPTR 重写）前先采样 CP 进度（progressState 6 词 + 500us 后再采样）+ BV 五词；**在动 → 只重置计时器，什么都不做**（"every kick of four runs found it moving, tiled passes of 100 to 160 ms"）；50ms 无进度才动；200ms 还不行才 `drainBus`（GBIF halt/ack 两级，Ring.cpp:176-187，"the way a6xx drains the bus before a reset"）。历史案例全在注释里：int-317（RPTR<WPTR + 双线程停在同一 cache clean → WPTR 从未被取）、i343（206/213 stalls 第二级结束）、i491（WPTR 被 GMU 丢，fenced write 前 5361/5397 次靠 handler 重写）、i553（handler 曾在 6712/6911 个 job 上跑 → 改为 50ms 无进度才动）。**可借鉴**：我树无 stall handler（超时即 `hakios_gpu_report` 一票否决，之后全部等待提前失败）——这是刻意的保守（panic-free 优先）；v0.5 下半场引入"重试"前，对方的分级与"先采样后动"就是现成设计，且每级动作都配计数器。

**③ 失败映射记录**（`4a3921a`，Run on hardware）：`native_adreno_map_met[7]`——最后一个失败的 BoMap 的地址/字节数/句柄是否已映射 + 与之相撞的既有映射（地址/字节/句柄/jobs/kind）固定 7 词记录（UserClient.cpp:603-605）；实机案例"窗口首地址的拒收 map 显示同尺寸映射在场"。**可借鉴**：无 printf、无锁、固定形状，把"失败原因"变成可从板级日志读的一行。我树 `hakios_gpu_address`（:3437 起，线性扫 free 表）失败时返回 0，不留痕。

**④ license 边界表**（Q5 后半；GitHub API license 字段 + /license 端点 + LICENSE 原文逐仓核对；存档 wave44-scripts/evidence/license-*.txt）：

| 仓 | API 字段 | LICENSE 原文 | 版权行 | 知识层 | 代码层能否引入内核树 |
|---|---|---|---|---|---|
| Adreno740 | MIT | MIT（sha `8803ca32`，1082 B） | "NativeAdreno contributors" | OK | **能**（MIT，带 attribution） |
| AdrenoPM4 | MIT | MIT（`9bcaf670`；正文与 Adreno740 那份相同） | "AdrenoPM4 contributors" | OK | 能 |
| AirNir | MIT | MIT（`9b9bc8a5`，正文相同；另有 licenses/SoftFloat-3e.txt 附属，未读） | "AirNir contributors" | OK | 能（SoftFloat 部分另计） |
| AdrenoMetal | MIT | MIT（`424da216`，正文相同） | "NativeMetal contributors" | OK | 能 |
| UniXNU（框架） | NOASSERTION("Other") | **BSD-2-Clause-Patent**（`f63d2a6e`，SPDX 行在文内） | "UniXNU contributors" | OK | 能（BSD-2 + 专利条款） |
| UniXNU-sheng | NOASSERTION | BSD-2-Clause-Patent（blob `f63d2a6e` = 框架仓同一文件） | 同上 | OK | 能 |
| UniXNU-sm8550-common | NOASSERTION | BSD-2-Clause-Patent（blob `f63d2a6e` = 框架仓同一文件） | 同上 | OK | 能 |
| AdrenoFirmware | NOASSERTION | BSD-2-Clause-Patent（`217b4df4`；版权行写 "ArmVirtPlatform contributors"——复制模板笔误，条件不受影响） | 同上 | OK | 能 |
| （对照）PongAdreno 线：zizhan/mondrian/pong/diting | 全部 NOASSERTION | **未读到原文** | 未读 | OK（只读知识） | **未查清前不得引入** |

（GitHub 对带 SPDX 行的 BSD-2-Clause-Patent 检出为 NOASSERTION 是检测器局限；以 LICENSE 原文为准。）

## 3. 新发现：我树 hw_init/CP 层与三方参考的源码级偏差清单

> 定性纪律：全部为"源码级偏差 CONFIRMED、设备级后果未测/非阻断"——我树步 5-21 真机全绿是既成事实，任何一条都不构成"必须改"的判定；每条给出三方值，是否采纳留给后续波按"一世代一修复"排期。证据：[VENDOR] adreno_gen7.c gen7_start（:422 起）、[对方-硬件] sheng GpuPowerProbe.cpp gpuHwInit（:1590-1647）、我树 step_core_start（:2812-2947）。

| # | 项 | 我树 | vendor（同机） | sheng（A740 实机） | 证据行 |
|---|---|---|---|---|---|
| N1 | **CP_ME_INIT** | 8 字、mask 0x82f（a6xx 形 + DMS bit11）、后五字 0 | **7 字、mask BIT(0)\|1\|3\|6\|8(\|11 if !dms)、op-mode 0x2、pwrup reglist、BIT(31)** | NativeAdrenoCpInit.cpp:48-55 同 vendor | 我 :2933-2942；V :101-148；CpInit :43-55；[UP v6.12] a7xx_cp_init |
| N2 | UCHE_CACHE_WAYS | 0x4 | 0x800000 | 1<<23 | 我 :2840；V :460；sheng :1611 |
| N3 | UCHE_CMDQ_CONFIG | 未写 | `6<<16\|6<<12\|9<<8\|BIT3\|BIT2\|2` = 0x6690e | 同 vendor | 我 grep=0；V :462；sheng :1620 |
| N4 | RBBM_GBIF_CLIENT_QOS_CNTL | 先 3 后 0（两写） | 0x2120212（gbif 表） | 0x2120212 | 我 :2834/:2874；V gbif 表 :1814；sheng :1604 |
| N5 | UCHE_GBIF_GX_CONFIG | 未写 | 0x10240e0 | 同 | 我 grep=0；V :432；sheng :1605 |
| N6 | CP_APRIV_CNTL | 0x6e（无 ICACHE bit0） | 0x6f（BR_APRIV_DEFAULT） | 0x6f + BV 0x0f + LPAC 0x0f | 我 :2875；V :418-420/:534-537；sheng :1622-1624 |
| N7 | CP_BV/LPAC_CHICKEN_DBG | 未写（仅 CP_CHICKEN_DBG=1） | gen7_4_0 分支三个都写 1 | —（未见，未读到 sheng 侧） | 我 :2873；V :546-548（CP/BV/LPAC 三写） |
| N8 | RB_CMP_DBG_ECO_CNTL | 未写 | `|=` BIT(11)（禁非 UBWC 读越过写） | sheng :1625 `|=(1u<<11)` | 我 grep=0（我写的 RB_DBG_ECO 0x8e04 是另一寄存器 :2877）；V :526 |
| N9 | CP 保护表 | 全树无 CP_PROTECT 写入（wave37 刻意缓项："只 matters once it draws"） | gen7_protect_init（wave35 记 a730 表 48 条，本轮未数） | CP_PROTECT_CNTL BIT0\|1\|3 + NativeAdrenoA740Protect 46 条 | 我 grep=0；V :528；sheng :1617-1619 + A740HwInit.h:120-168 |
| N10 | HWCG 时钟门控表 | 刻意不做（wave37 观察项） | gen7_hwcg_set(true) | 54 条表 + CLOCK_CNTL=0x8aa8aa82 | A740HwInit.h:62-118；sheng :1601-1602 |
| N11 | GRAS_NC_MODE_CNTL 写法 | 直写一次（bank_bit<<5） | 直写一次（同） | **按 pipe 经 CP_APERTURE_CNTL_HOST 对 BR、BV 各写一次**（Linux master :792-799 同） | 我 :2867；V :503；sheng :1632-1636；[UP v6.12] :602 直写 |
| N12 | WPTR 写 | 裸写（ring_send :2618） | gen7_fenced_write 只在 preempt 路径；常规路径 GMU 在场 | fenced write（AHB fence status 轮询重试≤200） | Ring.cpp:114-135；V :150-180 |
| N13 | HFI num_q/num_active_q | 17（hwsched 值） | 非 hwsched 3 / hwsched 17 | 3（Linux/AdrenoFirmware 口径） | 我 :1956；V gen7_hfi :17/:189 / hwsched :21；AdrenoHfi.c:36 |
| N14 | CP_RB_CNTL bit27 | 置位（不回读 rptr 到内存）+ 直读 CP_RB_RPTR 寄存器 | MSM 默认带 rptr shadow（CP_RB_RPTR_ADDR→memptrs） | shadow 用 preempt 记录报 rptr | 我 :2509；Ring.cpp:136-150/:411-423 |

其中 N1-N6、N8、N9 在"开始画真实内容（步 22 之后的 3D 渲染）"时才可能显影（保护表管的是用户态命令越权、BIT(6) 管抢占计数器、UBWC 相关 N5/N8 管压缩布局）；N2/N3 在步 5-21 已有"现值可用"的实机旁证（wave37 §5-3 口径不变，本轮只补"对方实机也用 vendor 值"这一票）。**优先级排序见 §5。**

## 4. 前提勘误（给当时的工作安排的对账单）

1. **census 2026-11-11 §3-1 "同 SoC 仍无人打通硬件层" 与 wave35 §0-1 / F16 普查矛盾**：wave35 记 zizhan GPU-01 = **DEVICE_VERIFIED**（"Adreno 730 with Turnip and metal2vulkan"，合成滑动 95.3 fps）；本轮又在框架仓 HEAD 设备记录里见到 `docs/devices/pong.md:22`（GPU `implemented`）、`docs/devices/diting-dddqmmx.md:22`（GPU `implemented`；:382 "services81 实际 GPU scanout 完成记录：49 帧/7873ms"；:403 "services134 …real Vulkan device, GPU scanout and 1030 actual completed command buffers at 60s, mean 18.9ms"；:411 "services122 用户确认桌面可启动"）。这些是**对方自报**（设备记录由其仓 porting.toml 生成，我未验证其硬件证据），但"同 SoC 无人通硬件"作为结论性表述应当撤回或改写为"K60 线未通；pong→zizhan/diting 线自报已通"。
2. **"全生态同代 7xx 原生驱动只有这一份在动"不成立**：`drivers/PongAdreno/`（A730 内核驱动目录：PongAdrenoAccelerator/Client/Clocks/Cp/CpProfile/Gmu…+ArmSmmu4K；两仓树内路径含 adreno/a730/gmu/turnip 的文件各 110/111 个，以该目录为主体）公开存在于 `qiumochen/UniXNU-zizhan`（non-fork，描述即 "Adreno 730 rendering"）与 `Emilelu/UniXNU-mondrian`（K60，2026-11-11T16:25Z 仍活跃）；`Chengdong-Yu/UniXNU-pong`（源头，15:31Z 活跃）、`dddqmmx/UniXNU-diting`（fork，11-11T02:04Z）。**且 wave35 §0-1 早已指出 zizhan 内核侧 = "UniXNU org 的 NativeAdreno + PongAdreno 适配层"——即 Adreno740 仓是 A730 线的同源核心，PongAdreno 持有 SM8475 板级数字**。本轮未读 PongAdreno 源码（边界：任务书限 UniXNU org + K60 不深挖），license 原文未读——列 §5 P0 阅读单。
3. 小勘误：wave35 §0-1 写 pong = "Nothing Phone 2，**SM8450**"；框架 devices.toml:2967 记 pong `soc = "SM8475"`（Nothing Phone (2) = Snapdragon 8+ Gen 1 = SM8475，与 mondrian/diting 同 SoC）。

## 5. 行动建议（按优先级）

**P0（下一准备工作波，读码不碰设备）**
1. **读 PongAdreno（A730/SM8475）**：`qiumochen/UniXNU-zizhan` 或 `Emilelu/UniXNU-mondrian` 的 `drivers/PongAdreno/`——同 GPU（A730=0x07030002 同 chipid 族）+ 同 SoC（cape gcc/gpucc/GMU 4.0.7/a730_sqe/zap 三段），是比 Adreno740 更近的寄存器/序列参考；先查四仓 LICENSE 原文（现在全是 NOASSERTION 未读）。重点对照面：它的 fence 形状（A730 是否同 0x31|BIT27）、hw_init 全表、GMU 窗/时钟、SM8475 的 UCHE_CACHE_WAYS/CMDQ/QOS 实测值、GMEM 窗。
2. **对账**：把 §4-1 的 census/wave35 矛盾记入 STATUS（或下轮 census 勘误段），避免下一阶段再被"无人通硬件"误导。

**P1（v36 判定轮预案增补，给 wave38/当时的工作安排）**
3. fence 探针失败分支表加一条：**WPTR 丢弃**——探针超时且 RPTR 未动时，读 `GMU_AHB_FENCE_STATUS`（我树已在读，:2229）并重写一次 WPTR 再等（对方 fenced write ≤200 次的极简版）；若命中，N12 升级为修复项。
4. 回归判据不变式：步 20-21 行原样复现（`THE 3D CORE TAKES COMMANDS` / `0x600dc0de`）——wave41 已列，本轮无新增内核行为（零补丁），只是再次确认这是唯一风险点。

**P2（v0.5 下半场排期时决策，先证据后动作）**
5. **CP_ME_INIT 形状**（N1）：步 22 之后的 3D 渲染若出现 CP 层怪象（perf 计数不齐/抢占语义/IFPC 相关），先对照 N1 换 a7xx 七字形状再查别处；换形状本身是一世代一修复的合格候选（三方参考 + 离线验收器可先行构造）。
6. **UCHE_CACHE_WAYS / UCHE_CMDQ_CONFIG**（N2/N3）：同上触发条件（贴图/压缩布局异常）下按 vendor 值换算并验证；我树 wave41 §10-3 "勿回退 NC_MODE"纪律继续有效。
7. **CP 保护表 + APRIV + BV/LPAC**（N6-N9）：引入用户态 GPU 客户端（HakiosGPU 真实多客户端）之前是**安全前置**而非性能项——保护表是"用户程序命令不得碰寄存器"的门；对方板级 46 条表直接来自 a730_protect（与 wave35 引的 mainline a7xx_catalog 同源，可交叉）。
8. **UBWC TODO-DEV 降级**：`UBWC_SWIZZLE=6`/`MACROTILE=1` 值本身多方一致（§2-2），注释里的"dt 0x04"疑虑可消（版本枚举）；真机首帧后如出现红蓝交换，按对方 GMEM swap 系补丁的教训查内存侧字节序，不动这两个参数。

**P3（v0.6 性能/稳健波）**
9. 并发 binning 开闸清单按 §2-3 表补全（BV RPTR shadow + BV 进度检测两项是 wave41 门的新增前置）；届时 Mesa 侧 `tu_allow_concurrent_binning`/freedreno 侧行为另案。
10. stall handler 引入时抄对方的分级设计（采样→50ms→GBIF drain）+ 固定形状计数器；`native_adreno_map_met` 式失败留痕可低成本加在 `hakios_gpu_address`。
11. GMEM tile 渲染作为性能项排期时，先读对方 Mesa 补丁族（`turnip-gmem-memory-side-swap.patch` / `turnip-gmem-mutable-swap.patch` / `turnip-render-mode-for-attachment-memory.patch`，UniXNU/patches/mesa/）与 6061e102 的行距判定修正——我们走 freedreno GL，坑位相同但实现不同，只抄知识。

## 6. 诚实边界（未读到/未验证）

- **未读 PongAdreno 源码**（zizhan/mondrian/pong/diting 四仓未 clone；license 原文未读）。§4 全部来自元数据（GitHub API）与框架仓已归档的设备记录文字。
- **对方"Run on hardware"声明一律转述**（commit 信息/README/设备记录），未做独立验证；`2a91aa1a`（BV 进度）无显式硬件标注。
- 我们驱动的设备级行为（fence 是否真写回、NC_MODE/ME_INIT 的像素级后果）依旧未测——本轮零设备，一切"应值"都以源码级为界。
- Adreno740 的 GMU 侧（OOB/DCVS/RSC）与 IFPC 只读到接口名（板级 `startGpuDcvs`、prologue SET_MARKER 0x101/0x100），未深读；我树 IFPC 全程未启用（grep 无命中），相应包（SET_MARKER 线程框架）我树不发的理由成立。
- Linux `a6xx_gpu.c` v6.12 与 master 的 sha（`c3347937…`/`9b725c1c…`）与 grep 摘录在 evidence 档；GPL 原文件留在 /tmp 临时目录未入仓（tmpfs 随 WSL 回收清空，脚本每次自取）。
- AirNir（AIR→NIR→IR3 编译器套件）只读了 README/头（属 Turnip/metal2vulkan 用户态编译链），与 freedreno GL 主路线无交集，未深读。

## 7. 产物清单

| 件 | 路径 |
|---|---|
| 本阶段日志 | `docs/waves/wave44-adreno740-survey.md` |
| 取证脚本（七个） | `wave44-scripts/01-license-survey.sh`、`02-clone-refs.sh`、`03-linux-crosscheck.sh`、`04-ubwc-helpers.sh`、`05-same-soc-coordinate.sh`、`06-line-anchors.sh`、`07-license-blob-compare.sh` |
| 证据存档 | `wave44-scripts/evidence/`（org-repos.tsv、license-Adreno740/AdrenoPM4/AdrenoFirmware/AirNir/AdrenoMetal/UniXNU.txt、clone-ledger.txt、linux-crosscheck.txt、linux-ubwc-helpers.txt、same-soc-coordinate.txt、line-anchors.txt、license-blob-compare.txt） |
| 参考仓（WSL，不在本仓） | `/home/cyrux/hakios/refs/UniXNU-{Adreno740,AdrenoPM4,AdrenoFirmware,AirNir,AdrenoMetal,UniXNU,UniXNU-sheng,UniXNU-sm8550-common}`（sha 见 §1-1；chown cyrux:cyrux） |

STATUS.md 一句话现状段与 README.md 阶段表已同步登记；本阶段零内核树写入、零设备操作、wave38/42/43-scripts 零触碰。
