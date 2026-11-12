# 阶段 40 · 2026-11-11 · GPU 外部评审报告四的独立验证：四项核心结论全部确认

日期：2026-11-11。使命：对 `docs/review/gpt-review-report-4-2026-11-11-gpu.md` 的全部核心结论逐条独立核查，出 CONFIRMED / REFUTED / PARTIAL 判定，并对报告四自身的错误一视同仁纠错。

**纪律遵守：零设备操作（无 adb/fastboot/usbipd/刷写/wsl --shutdown）；`drivers/gpu/hakios.adreno.c` 零字节改动（只读，本轮无任何写入）；只新增本文件与 STATUS 一段；未触碰 wave38-scripts/ 在途文件。**

方法：WSL 树源码逐行读证（`~/hakios/kernel/`）、同机 vendor 源（`~/hakios/refs/kernel_oneplus_sm8475/`）、本机构建的 Mesa 25.0.7 源（`~/hakios/kernel/xnu-deps/build/mesa/mesa-25.0.7/`）、Linux v6.12 官方 tag 源码（经用户指定 127.0.0.1:7897 代理拉取 `raw.githubusercontent.com/torvalds/linux/v6.12`）、仓内日志/脚本/文档、sha256 实算。未重复报告四的隔离复现程序（其结论以静态源码读证等价复核，见各节）。

## 0. 判定（先行）

| # | 报告四条目 | 判定 | 一句话裁决 |
|---|---|---|---|
| 1 | **P0-1**：用户态 submit 尾部 fence 事件仍是 a6xx 式，首字 `0x00000004` 缺 WRITE_ENABLED(bit27) | **CONFIRMED（源码级；设备级未测）** | 三方（vendor / Linux v6.12 a7xx / Mesa）对照一致；完成判定只读该事件应写的 RAM 字，全文件无第二写者 |
| 2 | **P0 附带**：wave37 的 0x600dc0de 测试没走用户态 fence 路径，覆盖不到 | **CONFIRMED** | 步 21 = `CP_SET_SECURE_MODE + CP_MEM_WRITE`（:2877-2901），不经 `hakios_gpu_submit`；gpu=1 自动路径停步 21（:3844），步 22 从未真机验证 |
| 3 | **P1-1 (a)**：FD725/HBB=16 已进软件查表，NC_MODE 硬件编码仍按 HBB=14 旧值，GRAS 缺失 | **CONFIRMED（算术逐格复现）** | `0x812/0x2/0x22/0x200000`+GRAS 缺写 = bank_bit=1（HBB=14）编码；vendor 公式 + MAL=32 → 应为 `0x816/0x6/0x26/0x60/0x600000`；Mesa FD725 HBB=16 |
| 4 | **P1-2 (b)**：gl_test 无自动像素断言，GL 错误/全底纹/覆盖率 100%/上屏失败仍退出 0 | **CONFIRMED（两文档冲突裁决：报告四胜）** | 源码只有 printf；wave39 §4.1:186"逐采样点 RGBA 断言"措辞与源码不符 |
| 5 | **P1-3**：runner 把"输出含 gl_test 字样"当完成，吞掉远端退出码 | **CONFIRMED** | `rc == 0 and ("GL_RC=0" in out or "gl_test:" in out)`——`no OpenGL ES context`/softpipe 均被接受为 DONE |
| 6 | **P1-4**：GL 尚无远端执行证据（两份 stdout 0 B，失败停在 USB open/banner 阶段） | **CONFIRMED** | `gltest-w38gl{1,2}-gl.out` 实测 0 B；err = LIBUSB open/bulk 失败或 banner 超时；SYN→RST\|ACK 样本在 wave27 日志 |
| 7 | **冻结点**：报告四表内 sha | **CONFIRMED（5/5 全中）** | 驱动×2 + drm shim + gl_test + v34 镜像（192 MiB）全部逐字节复现；loader 系漂移属 wave38 在途域（见 §5） |
| 8 | 报告四自身错误 | **无颠覆性错误；2 处引用边界修正 + 1 处重要遗漏（不推翻）** | 见 §6 |

**总裁决：报告四的可信度经独立复核成立，其"先裁决 submit/fence，再裁决布局配置，最后扩大图形负载"的顺序建议采纳；本轮另有 1 项报告四未提的 vendor 行为发现（DDR 类型运行时覆盖，§3-3），方向上反而强化 P1-a 对本机的结论，但修复实现必须带上该条件。**

## 1. P0：提交尾部 fence 事件（CONFIRMED）

### 1-1 现状（HakiOS 源码，`drivers/gpu/hakios.adreno.c`）

- `hakios_gpu_submit`（:3533-3573）尾部：:3567 `ring_command(CP_EVENT_WRITE, 4)` → :3568 `ring(EVENT_CACHE_FLUSH)` → :3569-3571 `ring(地址低 32)`/`ring(0)`/`ring(gpu_fence)`。`EVENT_CACHE_FLUSH` 定义于 :2926 = **`0x04`** → 事件首字实际生成值 = `0x00000004`，bit27=0，bit31=0。报告四引用行号 3567-3571 **精确**。
- 包形：CP_EVENT_WRITE=0x46（:2516，gen7 type-7），4 参数 + header 共 5 dword。与 vendor 完成尾包形同构，只差首参 dword。
- 完成判定只依赖该事件写回：`hakios_gpu_done`（:3452-3457）读 `core_scratch.memory + GPU_FENCE_AT`（:3242 = 0x40）的 RAM 字。grep 全文件：`GPU_FENCE_AT` 仅 5 处（定义 :3242 / done :3454 / 统计 :3484 / submit 事件地址 :3569 / report :3584）——**该 RAM 字的唯一写者就是这条 CP_EVENT_WRITE**。:3566 `ring_register(CP_SCRATCH_REG2, gpu_fence)` 写的是 CP 硬件寄存器（0x0885），`hakios_gpu_done` 不读它。
- 等待与停答：`hakios.gpu.cpp:190-214` `gpuWait`；超时 ≥1000 ms → :210-213 `gGPUReported = true` + `hakios_gpu_report("no answer")`，此后一切等待提前失败。报告四引用 :190-214 **精确**。另 `hakios.adreno.c:3296` 步 22 侧另有 5 s 轮询上限（`waited < 5000`），与报告四"5 s timeout"表述一致。
- 同形旧写还有两处：step_frame 的 `EVENT_FLUSH_COLOR`(:2984)/`EVENT_CACHE_FLUSH`(:2989) 事件写回（:2983-2991，首字同为 `0x1d`/`0x04` 无 bit27）——报告四建议 3 要求一并审的点属实。

### 1-2 三方对照

| 来源 | 位置 | 完成事件首字 |
|---|---|---|
| vendor kgsl（同机 `kernel_oneplus_sm8475`） | `adreno_gen7_ringbuffer.c:368-390`：drawctxt 路径两包 `CACHE_CLEAN \| BIT(31) \| BIT(27)` + 一包 `CACHE_CLEAN \| BIT(27)`；非 drawctxt 一包 `CACHE_CLEAN \| BIT(31) \| BIT(27)` | `0x31\|BIT(27)` = `0x08000031`（轮询型不带 IRQ 位） |
| vendor 常量 | `adreno_pm4types.h:168` `#define CACHE_CLEAN 0x31` | 行号**精确** |
| Linux v6.12（官方 tag 实拉） | `a6xx_gpu.c`：`a7xx_submit` = :281 起（报告引 281-405 ✓）；BV fence :369-374 `CACHE_CLEAN \| BIT(27)`；主 fence :390-396 `CACHE_CLEAN \| CP_EVENT_WRITE_0_IRQ \| BIT(27)` | 同上 |
| Linux v6.12 旧 a6xx 路径（对照） | 同文件 :267-276：`OUT_PKT7(CP_EVENT_WRITE, 4)` + `CP_EVENT_WRITE_0_EVENT(CACHE_FLUSH_TS) \| IRQ` + lo/hi/seqno，无 bit27 | 与 HakiOS 尾部**逐参同构**（连 :265-266 预写 `CP_SCRATCH_REG(2)` 都对上 :3566） |
| 本机 Mesa 25.0.7 | `adreno_pm4.xml:1651` 起 `CP_EVENT_WRITE7` 域：`WRITE_ENABLED` pos=27、`WRITE_SRC` low20-22、`WRITE_DST` pos24（报告引 1651-1689 ✓）；`fd6_emit.h:202-229` `__event_write` A7XX 分支按代生成 WRITE_SRC/DST/ENABLED（✓）；`fd6_fence_write` :241-247 = `FD_CACHE_CLEAN` + `EV_WRITE_USER_32B` + `EV_DST_RAM`（✓） | bit27 是字段化语义位，非 IRQ 附属 |

**一个使缺口精确化的观察**：HakiOS 首字 `0x04` 中 WRITE_SRC=0=`EV_WRITE_USER_32B`、WRITE_DST=0=`EV_DST_RAM`——恰好就是"写 32 位用户值进 RAM"的正确 src/dst 选择。即现行首字与 `0x08000031` 之间**唯一缺失的语义位就是 WRITE_ENABLED(bit27)**（外加事件 id 0x04 vs 0x31 的选择差异）。报告四的参考尾包（`0x31u | (1u<<27)` 四参数）与 vendor 轮询型逐字一致，采纳无歧义。

### 1-3 wave37 覆盖缺口（报告四附带声明，CONFIRMED）

- 步 21 `step_core_commands`（:2877-2901）：`CP_SET_SECURE_MODE(0x66)` + `CP_MEM_WRITE(0x3d)` 写 `0x600dc0de` 到 scratch 页 + `scratch[0]` 判定。**不经 `hakios_gpu_submit`，不含 fence 尾包**。报告引 :2877-2900 **精确**。
- gpu=1 自动路径 `last_step = 21`（:3844；报告引区间 3839-3848 ✓）。步 22（含 :2983-2991 两个事件写回）**从未在真机执行**（wave37 文档 §5-1 自认："步 22（三色图上屏）不在 gpu=1 使命内"）。
- 因此：**"步 21 魔法字成功"与"fence 尾包缺 bit27"可以同时成立，且当前不存在任何真机反证**（步 22 若真机验证并观察到 `0x0c0c0c0c/0x0d0e0d0e` 写回，本可反向削弱 P0——该证据从未产生）。报告四"不能代表提交完成已通过"的边界表述准确。

### 1-4 本轮未能验证的部分（如实）

A7xx SQE 固件对旧形包（无 bit27）是否真的不写回，属固件行为，只能真机裁决；报告四同样声明其隔离复现"不模拟 GPU 是否接受兼容事件"。P0 的定性 = **源码级契约缺口确认，设备级后果未测**。这也是把 fence 验证排在第一位（最小 BO/IB → submit → fence）的理由。

## 2. P1-a：NC_MODE 编码与 HBB 声明不一致（CONFIRMED）

### 2-1 现值 = HBB=14 编码（`hakios.adreno.c:2807-2811`）

```c
put(&gpu, "rb_nc_mode_cntl",   GPU_WORD(0x8e08), 1u << 11 | 1u << 4 | 1u << 1);  /* = 0x812 */
put(&gpu, "tpl1_nc_mode_cntl", GPU_WORD(0xb604), 1u << 1);                        /* = 0x2   */
put(&gpu, "sp_nc_mode_cntl",   GPU_WORD(0xae02), 2u << 4 | 1u << 1);              /* = 0x22  */
put(&gpu, "uche_mode_cntl",    GPU_WORD(0x0e01), 1u << 21);                       /* = 0x200000 */
put(&gpu, "rbbm_nc_mode_cntl", GPU_WORD(0x0534), 1);
```
上方注释（:2801-2805）原文即"highest bank bit 14"；`GRAS_NC_MODE_CNTL`(0x8602) **驱动零命中**（grep 全文件无此寄存器）。报告四表格与行号（:2803-2810/实际 2807-2811，区间吻合）属实。

### 2-2 vendor 公式与验算

`adreno_gen7.c:488-492`：`bank_bit = (highest_bank_bit - 13) & 3`；:493-507 五寄存器（RB=`BIT(11)|BIT(4)|MAL64?BIT(3):0|bank_bit<<1`、TPL1/SP 同 MAL 项、GRAS=`bank_bit<<5`、UCHE=`bank_bit<<21`）。寄存器 word index：`gen7_reg.h:726(GRAS 0x8602)/741(RB 0x8e08)/826(UCHE 0xe01)/865(SP 0xae02)/910(TPL1 0xb604)`——报告四引的五个行号**逐字精确**。

gen7_4_0 表（`adreno-gpulist.h:2111-2139`）：`highest_bank_bit = 16`（:2138）、`gmem_size = SZ_2M`、`gmu_fw_version = GMU_VERSION(4,0,7)`——与报告四引一致。MAL：本机 DTB `Mu-Silicium/Resources/DTBs/phk110.dts:20066` `qcom,min-access-length = <0x20>`（=32，不加 BIT(3)）——**精确命中**。

**验算（HBB=16 → bank_bit=3，MAL=32）**：

| 寄存器 | 驱动现值（bank_bit=1） | vendor 公式应值（bank_bit=3） | 报告四所列 |
|---|---:|---:|---:|
| RB_NC_MODE_CNTL 0x8e08 | `0x812` | `0x800|0x10|0x6` = **`0x816`** | `0x816` ✓ |
| TPL1_NC_MODE_CNTL 0xb604 | `0x2` | **`0x6`** | `0x6` ✓ |
| SP_NC_MODE_CNTL 0xae02 | `0x22` | `0x20|0x6` = **`0x26`** | `0x26` ✓ |
| GRAS_NC_MODE_CNTL 0x8602 | 未写 | `3<<5` = **`0x60`** | `0x60` ✓ |
| UCHE_MODE_CNTL 0x0e01 | `0x200000` | `3<<21` = **`0x600000`** | `0x600000` ✓ |

逐格全中。Mesa 侧 FD725（`freedreno_devices.py:1044-1062`，`highest_bank_bit = 16`，chip_id `0x07030002` 双枚）✓；a730_raw_magic_regs `[UCHE_CACHE_WAYS, 0x00840004]`（:939-940）+ `fd6_emit.cc:881-896` 逐个 `WRITE(magic_reg.reg, value)` ✓——报告四"UCHE_CACHE_WAYS 须按初始化后/首 restore 后分别看值"的分阶段提醒在源码层成立。

### 2-3 报告四未提的 vendor 行为（本轮新发现，不推翻、但约束修复实现）

`adreno_gen7.c:206` 先取表值 16，**:212-216 有运行时覆盖**：

```c
/* If the memory type is DDR 4, override the existing configuration */
if (of_fdt_get_ddrtype() == 0x7)
    adreno_dev->highest_bank_bit = 14;
```

即 vendor 的 bank_bit 并非纯查表——DDR 类型 0x7 时硬降 HBB=14。**本机** `phk110.dts:22` `ddr_device_type = <0x08>` ≠ 0x07 → 覆盖不触发 → 本机 vendor 语义仍是 16 → bank_bit=3 → 报告四的应值表对本机成立。但修复实现（wave 侧改 `hakios.adreno.c`）应**带同样的 DDR 类型条件或显式注明"本机 dts 0x08 不触发 14 覆盖"的依据**，不要裸硬编码"因为 FD725 表=16 所以写 16 编码"——否则未来换 DDR 类型机型时这组值会错第二次。

### 2-4 定性边界

报告四自评"这是源码配置不一致的事实；是否导致贴图/压缩/GMEM 读回错误还需真机证据"——采纳。P1-a 判定 = **配置不一致 CONFIRMED，像素级后果未定**。

## 3. P1-b：gl_test / runner 误报缺口（CONFIRMED；两文档冲突裁决）

### 3-1 gl_test 源码事实（`userland/src/gl_test.c`，367 行）

- :328 `memset(drawn, 0x55, …)` 后 :329 `glReadPixels`——读回失败则全幅保持 `0x55`（即"85 85 85 85"底纹）。
- :337-341 打印 `glGetError()`、五采样点 RGBA、覆盖率百分比——**只 printf，无任何条件失败退出**。
- :344-356 找不到 HakiosGPU 服务 → 打印后 :355 **`return 0`**；:357-365 上屏 `IOConnectCallStructMethod` 返回值只打印（:362 "the picture is on the panel (%#x)"），循环结束 :366 **`return 0`**。
- 有判定的只有：无上下文 :273 `return 1`、FBO 不全 :293 `return 1`、链接失败 :308-310 `return 1`；shader 编译失败 :129-133 只打印继续。
- 报告四引用段（:322-350、352-367）与行为描述逐条吻合；其"隔离反例"输出形态（error 0x502 / 全 0x55 / 100% / exit 0）在源码层完全成立。

### 3-2 两文档冲突裁决（报告四 vs wave39 §4.1）

- **wave39 `wave39-mesa-userland.md:186`** 原文："glReadPixels 全幅读回 → **逐采样点 RGBA 断言**（角/中心/三色角邻近）+ **彩色像素占比 vs 26% 几何预期** + `glGetError()`"——把 gl_test 的**打印行为**描述成"断言"。源码无断言。**裁决：报告四成立；wave39:186 措辞失实，应改为"逐采样点打印（人工判读）"**。
- **wave39:202**（§4.3 判定行清单第 3 条）"`error 0x0` + 三色角邻近像素命中各自颜色 = 三角形真被 3D 核画出来"——这是**人工判读规则**（期望输出样例 + 判读映射），本身不声称程序自动断言。报告四把 :186、:202 并列引作"报告所声称的像素自动断言"，**引用面偏宽**：失实的只是 :186；:202 作为判读清单与"程序无断言"不矛盾。实质裁决不变，但纠错落点应缩到 :186。
- wave39 自身对波域的声明是诚实的（§5-1"零真机"、§5-2"构建绿 ≠ 画得对"、§6 判定 E"首帧真机达成 = 不在本阶段域"）——wave39 没有宣称首帧已过；冲突仅限 :186 一词。

### 3-3 runner 判据（`wave38-scripts/gltest-run-v38.py`）

- 远端命令：`gl_test 8[ W H]; echo GL_RC=$?`（steps 数组，:106-109）——SSH rc 恒为 echo 的 0。
- 完成判据（:118）：`if rc == 0 and ("GL_RC=0" in out or "gl_test:" in out):` → **`gl_test: no OpenGL ES context` + `GL_RC=1` 被接受**（输出含 "gl_test:"），softpipe 输出 + GL_RC=0 同样被接受 → `done_gl=True` → 接着跑 fill/u2f → `return 0`（DONE）。报告四的 AST 抽取结论与源码一致。
- 这与 wave39 §4.4-C（`no OpenGL ES context` = 失败分支 C，dyld/SDK 域）**自相矛盾**：runner（wave38 域"只执行"）把 wave39 判定表里的失败分支停止成了 DONE。报告四"不应把失败尝试停止为 DONE"成立。
- 同 run-id 内重试覆盖同名 out/err（:80-81 `gltest-%s-%s.out` 只含 RUN_ID+tag）✓ 报告四成立。
- **本轮新发现（报告四未提）**：:125-128 的 LOADER_SILENCE 提示行 `"session not ready (rc=%s); LOADER SILENCE …"` 是**未做 % 代换的普通字符串**——w38gl2 日志里该行 `rc=%s` 字面打印（见 `gltest-run-v38-w38gl2.log` 逐行）。修"固定诊断句按失败阶段收窄"（报告四建议）时应顺带修此格式化 bug。

### 3-4 GL 执行证据现状（报告四 P1-4，CONFIRMED）

- `wave38-scripts/gltest-w38gl1-gl.out` = **0 B**、`gltest-w38gl2-gl.out` = **0 B**（klog.out 两份亦 0 B）；err 内容：w38gl1 = `bulk-OUT failed: LIBUSB_ERROR_TIMEOUT`（pair dead）→ `Connection timed out during banner exchange`；w38gl2 = `open failed (LIBUSB_ERROR_NOT_SUPPORTED)`×10 → banner 超时。runner 日志 `gltest-run-v38-w38gl2.log` 全程 `rc=255 / out 0 B`。报告四"失败样本没有证明 gl_test 在远端开始执行"属实。
- "后续样本能发 TCP SYN 但收到 RST|ACK"：仓内 `wave27-scripts/tssh27-w38-ssh1-k001.err:33-38` 有逐包记录（`flags=SYN … state=SYN_SENT` → `flags=RST|ACK …`）✓。
- **结论采纳：GL 当前没有任何"远端已执行/首帧失败"的设备侧证据；按"GPU 挂了/画错"假设继续调寄存器/着色器是无据操作**。USB 通道（wave38 在途域）仍是取证前置。

## 4. 冻结点校验

| 工件 | 记录来源 | 记录 sha256（前 16） | 本轮实算 | 结果 |
|---|---|---|---|---|
| `drivers/gpu/hakios.adreno.c` | 报告四表 | `b479501498cb6ba8` | 同 | **✓** |
| `drivers/gpu/hakios.gpu.cpp` | 报告四表 | `14845d51addce445` | 同 | **✓** |
| `tools/mesa/hakios-drm/hakios.drm.c` | 报告四表 | `a8b07414527c14d9` | 同 | **✓** |
| `userland/src/gl_test.c` | 报告四表 | `724d6e96475d1ac6` | 同 | **✓** |
| `device-layer/udon-hakios-grafted-v34.img`（192 MiB，Windows 仓侧） | 报告四表 | `1b952ea6dccdf78c` | 同 | **✓** |
| Mesa tarball `mesa-25.0.7.tar.xz` | 报告四引既有记录 | `592272df3cf01e85` | 同 | **✓** |
| `xnuloader/loader.c` | 报告三表 | `facebefbc5d3aff5` | `03b7606ff6f00982` | **漂移**：wave38 七 hunk 入树（wave38 备份 `loader.c.v37-orig`=`3ac12740`，亦 ≠ facebefb）+ wave38 在途增量；wave38 修复域，本阶段只读未碰 |
| `xnuloader/loader.efi` | 报告三表 / wave38 钉 | `3f595c52c4f13557` | `95f1f5552daa06d8` | **漂移**：在途重建（PE 时间戳不可复现已由 wave38 §64 行预警） |
| v34 镜像（报告三采样值） | 报告三表 | `03d424016d3a5093` | — | 该路径现文件 = `1b952ea6`（报告四已明确两件不可混同）；`03d42401` 为报告三时点采样，之后被 20:31:48 GL 载体替换 |
| `device-layer/udon-hakios-grafted-wave38.img` | wave38 STATUS 台账 | `742bce63e26efecc` | 同 | ✓（wave38 台账自洽；另有在途新件 `udon-hakios-payload-wave38fix.bin`，wave38 域，未碰） |

**结论：报告四的冻结点表 5/5 逐字节成立（含"驱动两源码在本轮前后读取一致"声明）；漂移仅发生在 loader 系——那是 wave38 在途工作域，报告四自己也预警了"并行执行方继续修改 loader"。**

## 5. 对报告四自身的纠错（一视同仁）

1. **引用行号质量：高**。抽查 30+ 处（2926/3533/3567-3571/3452-3457/2877-2900/2983-2992/2807-2811/3351-3353/190-214/3839-3848 区间/vendor 484-507、pm4types 168、gpulist 2112-2139、gen7_reg 726·741·826·865·910/dts 20066/Mesa pm4 1651-1689、devices 1045-1062·939-940、fd6_emit.h 202-247·cc 881-896·1110-1112/wave39 186·202/build-mesa 13-15·29·38·40）——**零硬错**，仅个别区间端点±1-2 行（如 NC_MODE 块实为 2807-2811）。
2. **遗漏（不推翻但须补）：** 未提 vendor `adreno_gen7.c:212-216` 的 DDR 类型运行时覆盖（ddrtype==0x7 → HBB=14）。本机 dts `ddr_device_type=0x08`（phk110.dts:22）不触发，P1-a 对本机结论不变且方向被强化；但"vendor 公式"叙述为纯查表略失真，修复实现必须带此条件（见 §2-3）。
3. **引用面偏宽：** P1-2 把 wave39:202 与 :186 并列引作"报告所声称的自动断言"——:202 是人工判读清单，不构成该声明；失实点仅 :186（见 §3-2）。
4. **转述放大（轻微）：** "后续报告的'用户态零代码需求'应改为…"——wave39 原文是"**协议层**零代码 delta"（§3.4、§6-D，指 shim 对接面无需新代码，且 §5-2 自己就声明"构建绿 ≠ 画得对、a7xx 运行时路径首次真机会话才算数"）。报告四要求的措辞收敛方向与 wave39 §5 一致，双方无实质分歧，但转述把 wave39 没说过的话（"运行时零需求"）安在了它头上。
5. **runner 细节可再进一步：** 报告四引 :125-128 固定诊断句——该句还有 `rc=%s` 未代换的格式化 bug（日志中字面打印），修复项应并入其"判据与阶段日志"工程（§3-3）。
6. **方法边界如实：** 报告四明确声明隔离复现"不模拟 GPU 是否接受兼容事件"、"SSH 失败不能用来验证或否定 P0"——本轮复核认可其声明边界，无过度声明。

## 6. 修复顺序评估（对照报告四"次序 1-5"）

**裁决：顺序合理，采纳**——先修验收尾具（否则后续每一步都无法证伪）、再裁 submit/fence（P0）、再同步 NC_MODE（P1-a）、再 Mesa 真渲染、最后桌面加速；且"先 fence 后布局"与"不建议依据零字节 SSH 输出盲调 shader/GMEM"两个排序判断均有本轮证据支撑。补强四点：

1. **次序 1（判据/阶段日志）顺带项**：修 runner 的 `rc=%s` 格式化 bug 与固定诊断句收窄；gl_test 增加 RENDER_PASS/READBACK_PASS/PRESENT_CALL_OK 三段结构化输出 + 非零退出码（报告四 §P1-2 建议照单）；wave39:186 的"断言"措辞同步勘误，避免下一阶段复读者再被误导。
2. **次序 2（fence）形状已无歧义**：轮询语义对齐 vendor 非 IRQ 型 `CACHE_CLEAN | BIT(27)`（0x08000031）；事件 id、WRITE_SRC/EV_WRITE_USER_32B、WRITE_DST/EV_DST_RAM 用命名常量按字段构造（现首字 0x04 的 src/dst 零值恰好已对，只差 bit27——一字修复，但要按字段写、不留魔数）。**BV/BR 与 CP_WAIT_TIMESTAMP 不必一步到位**：HakiOS 内核侧是单线程直提，Mesa 侧 `fd6_emit.cc:1109-1111` 已对 A7XX 发 `CP_THREAD_CONTROL(CONCURRENT_BIN_DISABLE)`，当前组合下 vendor 的 BV fence→WAIT_TIMESTAMP→BR fence 三段非必需；但"启用并发 binning 前必须补 BV→BR 完成约束"应写成硬条件（与报告四建议 2 一致）。**step_frame 的两个事件写回点（:2983-2991）同步补 bit27**，避免修好提交、步 22 复活时二次踩坑（报告四建议 3 落实为同刀）。
3. **次序 3（NC_MODE）必须带条件**：按 §2-3——写明本机 `ddr_device_type=0x08` 不触发 vendor 的 14 覆盖，或实现同款运行时检查；不要裸抄"FD725=16"。
4. **验收判据（最小 BO/IB 测试）设计合理**：两次 nonce CP_MEM_WRITE 经真实 submit→fence、编号递增，正是 1-4 节"设备级未测"缺口的最小闭合路径；与 wave39 §4.5 的会话纪律（先 SSH HIT 再阶段化探针）拼接即可，无需新增域。

## 7. 交付边界

本轮 = 判定，不是修复。未改驱动、未改 gl_test、未改 runner、未碰 wave38-scripts、未触设备。一切"应值/应修"均标注源码依据；设备级后果（fence 是否真不写回、NC_MODE 是否引发像素错）留待真机按 §6 顺序裁决。
