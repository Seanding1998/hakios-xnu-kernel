# 阶段 41 · 2026-11-11 · GPU 修复四项：fence 事件字段化、NC_MODE vendor 公式、gl_test 结构化验收、并发 binning 编译期门

> 2026-11-11 · 阶段 41 GPU 修复执行记录（衔接 wave40-gpu-verify.md 的修复顺序裁决）
> 任务书：对 wave40 全表 CONFIRMED 的外审报告四实施修复——P0 fence 事件（:3567 尾包 + :2983 孪生同刀）、P1-a NC_MODE DDR 条件同步（含 GRAS）、P1-b gl_test 真断言 + GL 载体重建、并发 binning 前置硬条件；每项带隔离自测；内核重建记账，**不打包不刷写**。
> 红线执行：零设备（无 adb/fastboot/usbipd/刷写/wsl --shutdown）✓；`wave38-scripts/` 零触碰（runner 判据问题只写规范，见 §6）✓；修改域 = `~/hakios/kernel/drivers/gpu/hakios.adreno.c`（外审确认后的授权修复）+ `~/hakios/kernel/userland/src/gl_test.c`（wave39 已退役）+ 阶段日志/STATUS/README + `wave41-scripts/` ✓。
> 证据分级：[实证] = 文件/字节/sha/行号可复现；[实测] = 本阶段隔离测试结果；[VENDOR] = `~/hakios/refs/kernel_oneplus_sm8475`（GPL 寄存器事实源）；[MESA] = `~/hakios/kernel/xnu-deps/build/mesa/mesa-25.0.7`（本机构建，tar sha 592272df 钉位）。

---

## 0. 判定（先行）

1. **修复单四项全部落地，隔离自测全绿（26/26 事件字/NC_MODE 判据 + gl_test 三场景负例/正例/软件对照），内核重建绿，GL 载体重建绿。设备级验证留待 v36 刷写轮**（版本与刷写时机由当时的工作安排在 wave38 v35 判定轮之后统一排）。
2. **P0 fence 事件字段化**：提交尾包与 step_frame 孪生事件改经 `ring_fence_event()`，首字由 `EVENT_CACHE_FLUSH`（0x04，bit27=0）改为 `FENCE_EVENT(EVENT_CACHE_CLEAN)` = **`0x08000031`** = `CACHE_CLEAN | WRITE_SRC(EV_WRITE_USER_32B=0) << 20 | WRITE_DST(EV_DST_RAM=0) << 24 | WRITE_ENABLED(BIT(27))`，全部命名宏字段化构造，零魔数散布 [实证 §2]。
3. **P1-a NC_MODE 同步**：五寄存器改按 vendor 公式从 `gpu_highest_bank_bit` 运行时计算——**带 vendor 同款 DDR 类型条件分支**（`ddr_type == 0x7 → HBB=14`；本机 dts `ddr_device_type=<0x08>` 不触发，`adreno_ddr_type=` boot-arg 可免重编纠正），补上 vendor 第五寄存器 **GRAS_NC_MODE_CNTL（word 0x8602）**；Mesa 的 GET_PARAM HBB 同源（`hakios_gpu_parameter` 返回同一变量）[实证 §3]。
4. **并发 binning 硬门**：内核侧 CP 启动前发 `CP_THREAD_CONTROL(bit27=CONCURRENT_BIN_DISABLE)`（vendor `gen7_cp_init_cmds` 同款），并以 `#define CONCURRENT_BINNING 0` + `#if CONCURRENT_BINNING → #error` 构成硬前置：BV/BR 完成事件 + CP_WAIT_TIMESTAMP 就位前翻开关 = 编译期失败 [实证 §4]。
5. **P1-b gl_test 从诊断打印机变验收器**：RENDER/READBACK/GL_ERROR/PRESENT 四段结构化判定 + 五采样点 barycentric 逐像素 RGBA 断言 + 覆盖率 25–27% 窗（26% 几何值）+ 上屏返回值判定 + 编译失败传播 + **任何失败非零退出**（1 上下文/程序、2 像素、3 面板、4 GL error）；阶段日志 fflush。外审负例（error 0x502 + 全 0x55 + 100% 覆盖 + 无服务）在旧代码 exit 0，新代码 **exit 4 全 FAIL 线** [实测 §5]。
6. **产物记账（不打包不刷写）**：内核 `hakios-kernel` **55a8d40f → `2f1af1cc`**（构建绿：仅已知 kext symbol-set 类失败，`tools/make-kernel.sh` 判定通过）；GL 载体 root.apfs **c2780842 → `51a030c3`**（APFS 含时间戳非字节可复现，以最后构建为准；gl_test 二进制 `802522ff` 三连构建复现）；源码 `hakios.adreno.c` b4795014 → **`356f5bf4`**、`gl_test.c` 724d6e96 → **`5f5d27d5`**。备份链续 `hakios.adreno.c.v41-orig` / `gl_test.c.v41-orig`。
7. **runner 判据规范转入 wave38**（本阶段不执行，见 §6）：`rc=%s` 未代换 bug 修法 + 完成判据 = `GL_RC=<0>`（解析值）∧ `RENDER_PASS backend=hw` ∧ `READBACK_PASS` ∧ `PRESENT_CALL_OK` ∧ rc==0；"输出含 gl_test:"即 DONE 的判据废止；softpipe 对照单列。

## 1. 基线与冻结点

| 工件 | 改前 sha256 | 改后 sha256 |
|---|---|---|
| `~/hakios/kernel/drivers/gpu/hakios.adreno.c` | `b479501498cb6ba8…`（= 报告四/wave40 冻结值） | `356f5bf4a9f230f054b10a20b54dde982db398762802fc0a1732bb7c9b30ea3e` |
| `~/hakios/kernel/userland/src/gl_test.c` | `724d6e96475d1ac6…`（= 报告四/wave40 冻结值） | `5f5d27d5d99623ed4183bb1fc6df5c2b9759acafc68186210d298a887d2d6d28` |
| `~/hakios/kernel/hakios-kernel`（构建产物） | `55a8d40f…`（v33 内核链尾） | `2f1af1cc94354d6560225e50e22b3780c13516f97e4816c3adc93e9e37b4587f` |
| `~/hakios/kernel/userland/root.apfs`（GL 载体） | `c2780842ade9ece1…`（wave39 首帧载体） | `51a030c34e98d0a3e2a69ebae0279ae669782a8ad62aa9483a5086a7e8017f65` |
| `~/hakios/kernel/userland/obj/gl_test` | —（wave39 期 0836948e 记录为载体内容物） | `802522ff26958bc3f57afdf4af63e0a3639f3b3c154833695c1da5459e37799c` |

备份：`hakios.adreno.c.v41-orig`（备份链 …v32-orig 之后续刀；v33 代修复的改前态即 v32-orig，树中本无 v33-orig 文件，已注明）、`gl_test.c.v41-orig`。构建日志：`/tmp/wave41-kernel-build.log`、`/tmp/wave41-glcarrier-build*.log`（WSL /tmp）。

## 2. P0：fence 事件字段化构造（外审报告四 P0-1 / wave40 §1）

**改前事实**（wave40 已冻结）：`hakios_gpu_submit` 尾部 `ring_command(CP_EVENT_WRITE, 4); ring(EVENT_CACHE_FLUSH)`（:3567-3571，`EVENT_CACHE_FLUSH` = 0x04 @:2926）——首字 `0x00000004`，WRITE_ENABLED(bit27)=0，完成编号写回从未被请求；`hakios_gpu_done`（:3452-3457）唯一依赖的 `GPU_FENCE_AT` RAM 字全文件只有这一个写者。同形旧写还有 step_frame 的孪生事件（:2983-2991，首字 0x1d/0x04）。

**修复**（三方对照无歧义，wave40 §6.2"形状已无歧义、按字段写、不留魔数"照单）：

1. 命名字段宏（新，置于 CP 操作码区）：
   - `CP_EVENT_WRITE7_SRC(src)` = `src << 20`（Mesa `event_write_src`：0 = `EV_WRITE_USER_32B`，payload 首字）
   - `CP_EVENT_WRITE7_DST(dst)` = `dst << 24`（`event_write_dst`：0 = `EV_DST_RAM`）
   - `CP_EVENT_WRITE7_WRITE_ENABLED` = `1u << 27`
   - `FENCE_EVENT(event)` = `event | SRC(EV_WRITE_USER_32B) | DST(EV_DST_RAM) | WRITE_ENABLED`
   - `EVENT_CACHE_CLEAN 0x31`（[VENDOR `adreno_pm4types.h:168` CACHE_CLEAN]；[MESA `adreno_pm4.xml` vgt_event_type A7XX `CACHE_CLEAN=49`]）
   - `CP_THREAD_CONTROL 0x17` + `CP_THREAD_CONTROL_CONCURRENT_BIN_DISABLE (1u<<27)`（[VENDOR `adreno_pm4types.h:171`]；[MESA `CONCURRENT_BIN_DISABLE` pos=27]）
   - 参考形态三方一致：vendor `adreno_gen7_ringbuffer.c:368-390` 完成事件 `CACHE_CLEAN | BIT(27)`（BIT(31) 为中断型，轮询等待不请求）；Linux v6.12 `a7xx_submit` BV fence :369-374 / 主 fence :390-396；Mesa `fd6_emit.h` `__event_write` A7XX 分支按 `needs_seqno` 置 WRITE_ENABLED。
2. 统一构造器 `ring_fence_event(event, address, word)`：type-7 头 + 4 参数（FENCE_EVENT / 地址低 32 / 高 32 / 用户字），置于 `ring_register` 之后；三处调用 = step_frame 孪生×2 + 提交尾包×1。
3. **提交尾包**（原 :3566-3571）：`ring_register(CP_SCRATCH_REG2, gpu_fence)` 保留（a6xx/a7xx 路径均预写，`hakios_gpu_done` 不读它，无害），尾包换 `ring_fence_event(EVENT_CACHE_CLEAN, CORE_SCRATCH_ADDRESS + GPU_FENCE_AT, gpu_fence)`。目标首字 **0x08000031**（wave40 表格值逐字）。
4. **step_frame 孪生同刀**（原 :2983-2991）：事件 id 换成第七代自己的名字——Mesa `fd_gpu_events<A7XX>` 表是裁决依据：a7xx 带 WRITE_ENABLED 的 cache 写回事件 = **CLEAN 系**（`FD_CACHE_CLEAN → CACHE_CLEAN(49)`、`FD_CCU_CLEAN_COLOR → CCU_CLEAN_COLOR(32)`，均 needs_seqno=true）；旧 0x1d（a6xx PC_CCU_FLUSH_COLOR_TS）在 a7xx 名为 CCU_FLUSH_COLOR = clean+invalidate（Mesa freedreno_gpu_event.h 术语注记），Mesa 不给它配写回。故：
   - 孪生一：`EVENT_FLUSH_COLOR 0x1d` → **`EVENT_CCU_CLEAN_COLOR 0x20`**（32），哨兵 0x0c0c0c0c 不变；
   - 孪生二：`EVENT_CACHE_FLUSH 0x04` → **`EVENT_CACHE_CLEAN 0x31`**（49），哨兵 0x0d0e0d0e 不变；
   - 旧 define（0x1d/0x04）全文件摘除，补丁器有"第六代事件 id 不得残留"断言。
5. 提交头部的 `EVENT_INVALIDATE_DEPTH/COLOR`（1 参、无写回）保持不动——a7xx 仍有效（CCU_INVALIDATE_DEPTH=24/COLOR=25 同号），失效语义无需 write-back。

**边界如实**：a7xx SQE 固件对 0x31|BIT(27) 形包是否真写回属固件行为，只能真机裁决（wave40 §1-4 同款边界）；本阶段交付 = 源码级契约闭合 + 离线单元证明构造字与三方参考逐位相等。

## 3. P1-a：NC_MODE DDR 条件同步（外审报告四 P1-1 / wave40 §2）

**改前事实**：`step_core_start` 硬编码 `0x812 / 0x2 / 0x22 / 0x200000`（= bank_bit 1 = HBB 14 编码），GRAS_NC_MODE_CNTL 零写；注释自认"highest bank bit 14"（Linux a6xx 套底），而驱动参数表（:3351-3353）、dts、Mesa FD725 三方都说 16。

**修复**（vendor 公式 + vendor 同款运行时条件，不裸硬编码——wave40 §2-3 的约束照单）：

```c
static uint32_t gpu_highest_bank_bit = 16;      /* gen7_4_0 / Mesa FD725；文件头注释记 phk110 dts chipid 0x7030002 */

/* step_core_start 内： */
uint32_t ddr_type = 0x8, bank_bit;              /* dt: ddr_device_type (phk110.dts:22) */
PE_parse_boot_argn("adreno_ddr_type", &ddr_type, sizeof(ddr_type));
if (ddr_type == 0x7) {                          /* [VENDOR adreno_gen7.c gen7_init] "If the memory type is DDR 4" */
    gpu_highest_bank_bit = 14;
}
bank_bit = (gpu_highest_bank_bit - 13) & 3;     /* [VENDOR adreno_gen7.c gen7_gpu_init :488-507] */
put(&gpu, "rb_nc_mode_cntl",   GPU_WORD(0x8e08), 1u << 11 | 1u << 4 | bank_bit << 1);
put(&gpu, "tpl1_nc_mode_cntl", GPU_WORD(0xb604), bank_bit << 1);
put(&gpu, "sp_nc_mode_cntl",   GPU_WORD(0xae02), 2u << 4 | bank_bit << 1);
put(&gpu, "gras_nc_mode_cntl", GPU_WORD(0x8602), bank_bit << 5);   /* 新增：vendor 第五寄存器（gen7_reg.h:726） */
put(&gpu, "uche_mode_cntl",    GPU_WORD(0x0e01), bank_bit << 21);
put(&gpu, "rbbm_nc_mode_cntl", GPU_WORD(0x0534), 1);               /* 不变 */
```

- MAL（qcom,min-access-length）：本机 dts = `<0x20>`（32，phk110.dts:20066）→ 64 字节访问位（bit3）不加——vendor 公式的 `(mal == 64) ? BIT(3) : 0` 分支以注释留档，值不激活。
- 本机应值（HBB=16 → bank_bit=3，MAL=32）：**RB `0x816` / TPL1 `0x6` / SP `0x26` / GRAS `0x60` / UCHE `0x600000`**——与报告四表格、wave40 验算逐格相同。
- DDR 类型 0x7 分支（HBB=14 → bank_bit=1）在离线自测里复算出**旧表原值**（0x812/0x2/0x22/0x20/0x200000）——证明该分支语义真实、不是装饰（见 §5）。
- `hakios_gpu_parameter` case 0x10（HIGHEST_BANK_BIT）改返回 `gpu_highest_bank_bit`——内核寄存器编码与 Mesa 咨询值同源，未来 DDR 覆盖触发时两边一起翻转。freedreno GL 链不查该参数（wave39 消账），此项为契约一致性而非功能依赖。

## 4. 并发 binning 前置硬条件（wave40 §6.2 补强 2）

- 事实：内核全文件无 `CP_THREAD_CONTROL`/binning 字样（wave40 未提；本阶段 grep 复核）；Mesa A7XX 路径每次 restore 发 `CP_THREAD_CONTROL(THREAD=BR | CONCURRENT_BIN_DISABLE)`（fd6_emit.cc:1109-1112）；vendor 自己的 CP 启动第一条就是 `CP_THREAD_CONTROL, BIT(27)`（`gen7_cp_init_cmds`，"Disable concurrent binning before sending CP init"）。
- 修复：`step_core_start` 在 `CP_ME_INIT` 前插入同款两字包 `ring_command(CP_THREAD_CONTROL, 1); ring(CP_THREAD_CONTROL_CONCURRENT_BIN_DISABLE)`，并在注释中写明硬条件——启用并发 binning 必须先有 BV/BR 各自的完成事件 + `CP_WAIT_TIMESTAMP` 三段序（vendor `adreno_gen7_ringbuffer.c` 的 drawctxt 双包形态），否则 binning 流可越过喂它的渲染流。
- 门本体：

```c
#define CONCURRENT_BINNING 0
#if CONCURRENT_BINNING
#error "concurrent binning needs the BV and BR completion events and CP_WAIT_TIMESTAMP first (see the comment above)"
#endif
```

翻开关 = 编译失败，位置就在启用点旁边。这不是装饰性 TODO：wave40 的原话是"应写成硬条件"。

## 5. 隔离自测（零设备）

### 5-1 事件字/NC_MODE 单元断言（`wave41-scripts/selftest-wave41.py`）

生成器从**补丁后的驱动源码原文**提取（非复写）：`odd_parity` 函数体、`FENCE_EVENT` 宏块（含 CP_EVENT_WRITE7_* 四宏）、两个事件 id 的 `#define` 值、五条 NC_MODE `put()` 表达式、DDR 分支 + bank_bit 公式——编译成独立 C 验收器，按 ring_command + ring 的包形（type-7 头、奇偶校验位）构造完整 5-dword 包逐位断言。结果 **26/26 全过** [实测]：

- fence 首字 = `0x08000031` ✓（含 WRITE_SRC=0/WRITE_DST=0/WRITE_ENABLED=1/IRQ=0 逐字段 + 地址/载荷占位字）；
- 包头 = `7<<28 | 4 | 奇偶(4)<<15 | 0x46<<16 | 奇偶(0x46)<<23` ✓；
- 孪生 colour 首字 = `0x08000020` ✓；
- 旧 0x04 字 bit27=0 ✓（缺口回放）；
- NC_MODE 本机分支（dts 0x08 不触发）= `0x816/0x6/0x26/0x60/0x600000` ✓；
- NC_MODE DDR 分支（0x7 → HBB14）= `0x812/0x2/0x22/0x20/0x200000` ✓（旧表原值回归，条件分支语义在证）。

### 5-2 gl_test 替身三场景（`wave41-scripts/gltest-stubtest.py`）

报告四方法学固化为常备测试：取**当前** gl_test.c，剥框架 include/GL extern，换替身（GL/IOKit/mach 时钟全桩），几何精确的合成图按像素中心 barycentric 现算。三场景 [实测]：

| 场景 | 旧程序行为（报告四负例） | 新程序行为 | 判定 |
|---|---|---|---|
| `error`（GL error 0x502 + 读回失败全 0x55 + 无 GPU 服务） | 打印 100%、"on the panel"，**exit 0** | `GL_ERROR_FAIL` + 5×`READBACK_FAIL`（含 0x55 检出）+ 100% 覆盖 FAIL + `PRESENT_CALL_FAIL`，**exit 4** | PASS |
| `hw`（FD725 + 几何精确图 + 面板调用成功） | —（无断言） | `RENDER backend=hw` + `RENDER_PASS backend=hw` + `READBACK_PASS samples 5/5 coverage 26%` + `PRESENT_CALL_OK`，exit 0 | PASS |
| `sw`（renderer=softpipe） | —（会被 runner 记 DONE） | 断言照过、exit 0，但 backend 线 = **sw**（runner 不得据此记硬件 DONE，§6） | PASS |

合成图覆盖 673,920/2,592,000 = **恰 26.0%**；五采样点替身输出 (68,69,118)/(235,12,8)/(12,235,8)/(10,10,235) 与判定常量一致（判定常量另经独立 Python barycentric 验算纠偏：红/绿角真值 (235,12,8)/(12,235,8)，首版手算 (232,15,8) 已弃）。栅格化对几何面积的偏差上界 = 半周长 ≈ 2051 px ≈ 0.08%，故覆盖率窗 [25%, 27%] 极宽安全。

### 5-3 判定常量的几何依据（归档）

角 A(-0.8,-0.6) 红 / B(0.8,-0.6) 绿 / C(0,0.7) 蓝（NDC，w=1）；清屏 (0.1,0.1,0.2,1.0)。像素判定点（GL 底原点坐标）：(2,2) 清屏 26,26,51 ±3；(w/2,h/2) 69,69,118 ±20；(w·0.15,h·0.22) 235,12,8 ±30；(w·0.85,h·0.22) 12,235,8 ±30；(w/2,h·0.80) 10,10,235 ±30；alpha 全 255（≥254）。覆盖率判据 = `coloured` 计数（通道>60；三角形内任意点 max 通道 ≥85、背景 max=51，无歧义）∈[25,27]%。

## 6. runner 判据规范（转入 wave38 执行——本阶段不改 `wave38-scripts/`）

对 `wave38-scripts/gltest-run-v38.py`（wave40 §3-3 确认的两缺陷）的修复规范：

1. **`rc=%s` 未代换 bug**（:125-128 LOADER_SILENCE 提示行字面打印 `rc=%s`）：改 f-string/% 代换真实 rc，并按失败阶段收窄文案（连接阶段/会话阶段/远端命令阶段分三句，不再用一句固定诊断）。
2. **完成判据**（废止 :118 的 `rc == 0 and ("GL_RC=0" in out or "gl_test:" in out)`）：
   - 远端 shell 先存真实 rc 再回显：`gl_test … 2>&1; echo GL_RC=$?`，runner 从输出**解析 `GL_RC=(\d+)` 的数值**（不是子串存在性）；
   - 硬件 DONE = `GL_RC == 0` ∧ 输出含 `RENDER_PASS backend=hw` ∧ `READBACK_PASS samples` ∧ `PRESENT_CALL_OK` ∧ 不含任何 `_FAIL` 行；
   - `gl_test:` 字样本身**永远不构成完成条件**（"no OpenGL ES context" 正是 gl_test 的失败分支 C 输出）；
   - `RENDER backend=sw` / renderer≠FD725 → 记为**软件对照**结果（独立状态，绝不并入硬件 DONE）；无 GPU 服务的 `PRESENT_CALL_FAIL`（rc=3）同样不是硬件 DONE；
   - 每次 attempt 独立 stdout/stderr 文件（RUN_ID+tag+序号），不覆盖同名文件。
3. 结构化判据行的机器含义（gl_test 侧已实现）：`RENDER_PASS` = 上下文+编译+链接+FBO 过；`READBACK_PASS samples 5/5 coverage NN%` = 五采样点 + 覆盖率窗全过；`PRESENT_CALL_OK` = 面板调用返回 0；退出码 0=全过 / 1=上下文或程序 / 2=像素 / 3=面板 / 4=GL error。

## 7. 构建与记账（不打包不刷写）

- 内核：`tools/make-kernel.sh -j8`（经 `xnu/sync-drivers.sh` 同步补丁后驱动）→ rc=0；日志中唯一失败 = kext symbol-set/check_all_exports 类（本配置已知，判定函数放行），`CC hakios.adreno.o` 在案。`hakios-kernel` = **2f1af1cc**。
- GL 载体：`cd userland && GL=test FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh ./build.sh`（wave39 §2 同配方）→ rc=0；`root.apfs` = **51a030c3**（8,089,600 B）。APFS 镜像含构建时间戳，**非字节可复现**（连构三次 005a892c/6c959300/51a030c3 而 gl_test obj 三连同 = 802522ff）——记账以最后构建为准，内容物 sha 另行钉住：obj/gl_test `802522ff`、obj/libOSMesa.8.dylib `e0bd033a`（与 wave39 记录同源）。
- **不打包、不刷写、不 graft**：v36（= v35 修后链 + 本阶段内核 2f1af1cc + 本阶段载体 51a030c3）的版本号与刷写时机由当时的工作安排在 wave38 v35 判定轮之后统一排；本阶段产物已在 WSL 树就位（`~/hakios/kernel/hakios-kernel`、`~/hakios/kernel/userland/root.apfs`）。

## 8. 留档路径

| 件 | 路径 |
|---|---|
| 内核补丁器（9 hunk，唯一锚断言 + 基线 sha 钉 + 永不重跑检查） | `wave41-scripts/apply-wave41-kernel.py` |
| gl_test 补丁器（5 hunk，同款纪律） | `wave41-scripts/apply-wave41-gltest.py` |
| diff 留档 | `wave41-scripts/diffs/hakios.adreno.c.v41.diff`（191 行）、`wave41-scripts/diffs/gl_test.c.v41.diff`（176 行） |
| 事件字/NC_MODE 离线单元测试 | `wave41-scripts/selftest-wave41.py`（→ /tmp/wave41-selftest.c） |
| gl_test 替身三场景测试 | `wave41-scripts/gltest-stubtest.py`（→ /tmp/wave41-gltest-stub.c） |
| 备份 | `~/hakios/kernel/drivers/gpu/hakios.adreno.c.v41-orig`、`~/hakios/kernel/userland/src/gl_test.c.v41-orig` |

补丁器范式沿 `apply-*-v28..v33.py` 家族：锚必须恰出现一次、基线 sha 不符即拒绝、结构标记计数断言（ring_fence_event 定义 1/调用 3、gpu_highest_bank_bit 恰 4、第六代事件 id 零残留、GRAS 在位、CONCURRENT_BINNING 在位、静默 return 0 已死）。

## 9. 判定表（六分支式）

| 分支 | 判定 |
|---|---|
| **A 四项修复全落地 + 隔离自测全绿 + 双构建绿** | **✓——本阶段实况（§0-1/§5/§7）** |
| B 补丁锚失配/基线漂移 | ✗（基线 sha 钉位命中 b4795014/724d6e96；补丁器一次通过） |
| C 自测负例仍 exit 0 | ✗（error 场景 exit 4，报告四负例被拒收） |
| D 构建失败 | ✗（内核 rc=0、载体 rc=0；仅已知 symbol-set 类失败） |
| E 设备级反证出现 | 未行使（零设备波；fence 写回与 NC_MODE 像素后果留待 v36 真机裁决） |
| F 域外触碰 | ✗（wave38-scripts 零改动；设备零操作；loader 系零触碰） |

## 10. 转入与下一步

1. **当时的工作安排**：v36 组合排期（v35 修后链 + 内核 2f1af1cc + 载体 51a030c3），刷写窗排 wave38 v35 判定轮之后；v36 真机判定建议门 = ①步 20-21 回归（CP_THREAD_CONTROL 新增两字包后 `THE 3D CORE TAKES COMMANDS`/`0x600dc0de` 必须原样复现——这是本阶段唯一的内核行为变化点，vendor gen7_cp_init_cmds 同序，风险最低但必须回验）；②最小 BO/IB fence 探针（wave40 §6.4 的设计：两次 nonce CP_MEM_WRITE 经真实 submit→fence，编号递增）裁决 P0 设备级；③gl_test 首帧轮直接用 §6 判据（新载体已带验收器，runner 按 §6 改造后即可辨真假 DONE）。
2. **wave38**：按 §6 规范改 runner（`rc=%s` bug + 完成判据 + per-attempt 文件）；与 wave39 §4.4-C 失败分支表对齐。
3. **观察项不动**：RBBM_GBIF_CLIENT_QOS_CNTL、UCHE_CACHE_WAYS（Mesa raw-magic restore 会改写，分阶段看值）、UCHE_CMDQ_CONFIG——wave37 §5 的清单继续有效；NC_MODE 修正后若出现新的贴图/GMEM 读回异常，先查 UBWC_SWIZZLE(0x06) 与 MACROTILE 分层，勿回退本阶段（vendor 公式在证）。
4. **adreno_ddr_type boot-arg**：本机不传 = dts 0x08 语义（HBB 16）；传 0x7 = vendor DDR-4 语义（HBB 14）。给未来换内存机型/排查用，v36 不需要。
