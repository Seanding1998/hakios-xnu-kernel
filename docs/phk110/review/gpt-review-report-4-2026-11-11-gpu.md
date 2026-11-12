# 外部评审报告四 · GPU 专项（2026-11-11）

日期：2026-11-11，北京时间。范围：阶段 37 v27→v33 的 GPU 修复、阶段 39 Mesa 25.0.7/GL 测试载体，以及当前 GL 执行器。方法：本地源码、修复前备份、同机 vendor 实现、实际 Mesa 源码、已有日志与隔离反例测试。**本轮只新增本报告；没有修改驱动、用户态代码或执行器，没有重新构建内核/镜像，没有连接或操作手机。**

## 结论

**找到两项应优先处理的 GPU 运行时问题，以及两处会掩盖失败的验收尾具缺陷。**

1. **P0：内核的用户态提交尾部仍发 a6xx 式 fence 事件。** 实际发出的事件首字为 `0x00000004`，没有 A7xx 完成写回所需的 `WRITE_ENABLED` 位；同机 vendor 与 Linux a7xx 路径使用 `CACHE_CLEAN | BIT(27)`。这是当前最应先隔离验证的代码缺口。
2. **P1：内核声明 FD725/HBB=16，但硬件的 NC_MODE bank 编码仍是 HBB=14 对应的旧值，GRAS 配置亦缺。** 软件查表正确不代表硬件配置已经同步。这是渲染/读回错误的高优先级候选，尚无真机像素证据定案。
3. **P1：gl_test 没有报告所声称的像素自动断言。** 它可以在 `GL_INVALID_OPERATION`、覆盖率 100%、上屏返回错误的情况下依旧退出 0。
4. **P1：执行器把“有 gl_test 字样”当成完成条件。** 上下文创建失败、程序退出 1 的输出也会被接受并继续跑性能测试；软件回退也不被排除。

另一个当前阻塞是取证通道：读取到的 `gltest-w38gl1-gl.out` 与 `gltest-w38gl2-gl.out` 均为 0 B；w38gl2 日志中的失败包括 `LIBUSB_ERROR_NOT_SUPPORTED` 和 SSH banner 前超时，后续 stderr 还出现 SYN→RST|ACK。这些失败样本没有证明 gl_test 在远端开始执行，不能算 GPU 绘制挂死，也不能算首帧失败的设备侧证据。

**对既有成果的判断：阶段 37 的硬件 bring-up 成功有独立价值，可以保留。它证明 CP 能执行命令并写一个字，不能代表 Mesa 的提交完成、着色、纹理/GMEM、像素读回和桌面加速已通过。** `docs/waves/wave37-gpu-firstlight.md` §5 本身也说明 gpu=1 没有走步 22；后续报告的“用户态零代码需求”应改为“接口骨架可复用，运行时仍须核验”。

## 审阅基线与路径

主源码根：`/home/cyrux/hakios/kernel/`（WSL FedoraLinux-44）。下文 `drivers/*`、`userland/*`、`tools/*` 都相对此根。**不要对照 Windows 仓旧 upstream 镜像套用这些行号。**

同机 vendor 源码根：`/home/cyrux/hakios/refs/kernel_oneplus_sm8475/`，下文以 `vendor/` 标记。Mesa 根：`/home/cyrux/hakios/kernel/xnu-deps/build/mesa/mesa-25.0.7/`，以 `Mesa/` 标记。Mesa tarball 的既有 SHA 记录为 `592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6`；本轮直接检查的是本地已应用 Darwin 补丁的源码。

| 文件/工件 | 本轮实算 SHA256 |
|---|---|
| `drivers/gpu/hakios.adreno.c` | `b479501498cb6ba8e71080f829a0735b945bfef9914f7dc790c761b76cc07eea` |
| `drivers/gpu/hakios.gpu.cpp` | `14845d51addce44587af7218e6d9be6c03fb907751e94f9c42b35eff3bb529e4` |
| `tools/mesa/hakios-drm/hakios.drm.c` | `a8b07414527c14d9f6097a2175fa9f49892d98d14f4a03db8387955ca07af46a` |
| `userland/src/gl_test.c` | `724d6e96475d1ac64aeadfed094ba1fe61481c4ab3353acbeb4472edaeae25f3` |
| 采样时的 `device-layer/udon-hakios-grafted-v34.img`，192 MiB | `1b952ea6dccdf78cd7846fe5d670adf3e8edbd8aa1275571708bd36dde6dd92d` |

该 v34 是流水中 20:31:48 刷入的 GL 载体，不能与上一份 USB 报告采样的 `03d42401…` 包混为一件。并行执行方继续修改 loader/生成候选件，本报告不是那些新候选件的验收。GPU 两个源码哈希在本轮前后读取一致。

## P0-1：用户态 submit 的 fence 事件未按 gen7 格式移植

**证据：**

- `drivers/gpu/hakios.adreno.c:3533–3573`，`hakios_gpu_submit`。
- 末尾 `:3567–3571` 发 `CP_EVENT_WRITE`、4 个参数，首参数是 `EVENT_CACHE_FLUSH`；`:2926` 将其定义为 `0x04`。
- `:3452–3457` 的 `hakios_gpu_done` 只靠 scratch 中的完成编号判定；`drivers/gpu/hakios.gpu.cpp:190–214` 超时后会设全局 `gGPUReported`，之后等待提前失败。
- 同机 `vendor/drivers/gpu/msm/adreno_gen7_ringbuffer.c:367–390` 的完成事件用 `CACHE_CLEAN | BIT(27)`，中断型记录另加 BIT(31)；`adreno_pm4types.h:168` 定义 `CACHE_CLEAN=0x31`。
- 本地 `Mesa/src/freedreno/registers/adreno/adreno_pm4.xml:1651–1689` 定义 A7xx `CP_EVENT_WRITE7`，写源、写目的地与 `WRITE_ENABLED`（bit 27）是明确字段；`Mesa/src/gallium/drivers/freedreno/a6xx/fd6_emit.h:202–229、241–247` 按代际生成，并在 fence 写回时用 `FD_CACHE_CLEAN`、32 位用户值和 RAM 目标。

本轮还经 Clash 7897 代理读取 Linux 官方固定版本核对：[Linux v6.12 a7xx_submit](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/msm/adreno/a6xx_gpu.c#L281-L405)。该函数对 BV/BR 完成使用新事件及 bit 27，与其同文件前面的 a6xx 旧路径明确不同。当前 HakiOS 尾部更接近旧 a6xx 路径。

**隔离复现：** 抽取真实 `odd_parity/ring/ring_command/ring_register/ring_time/hakios_gpu_submit`，用内存数组替代 ring、替身寄存器与时钟运行一次 submit，遍历生成的真实包。捕获到末尾事件首字恰为 `0x00000004`，bit 27 为 0；新格式参考首字为 `0x08000031`。测试没有改写被审函数，也没有触碰 GPU。

**影响推理：** Mesa 可能已把 IB 交给 CP，甚至完成了绘制，但内核等待的 scratch 完成编号没有按 A7xx 契约写回，随后出现 5 s timeout、“no answer”、缓冲区延迟回收或 GPU 被全局判停答。这些是代码缺口可导致的表现，**尚不是本机本轮已经抓到的运行时故障**。目前失败的 SSH 尝试不能用来验证或否定它。

**为什么步 21 不覆盖：** `hakios.adreno.c:2877–2900` 发送的是 `CP_SET_SECURE_MODE` 与 `CP_MEM_WRITE`，再通过 ring 读指针/状态检查和 scratch 魔法字判断。它没有走 `hakios_gpu_submit`，也没有用用户态依赖的 fence 尾包。因此写出 `0x600dc0de` 与这条 fence 路径有缺陷可以同时成立。

**建议修复与最小验证：**

1. 引入明确的 A7xx fence/event 生成函数，使用 `CACHE_CLEAN`、32 位 payload、RAM 目标及 WRITE_ENABLED；当前是轮询等待，不应为了抄 Linux 中断路径而盲目添加 IRQ 位。
2. 核对实际使用的 BR/BV/并发 binning 模式。Linux/vendor 的线程同步不能整段照搬，也不能在启用并发后省略 BV→BR 的完成约束。本地 Mesa `fd6_emit.cc:1110–1112` 已有 BR 选择及 concurrent-binning disable，需与内核入口约定一起查清。
3. 同时审 `step_frame:2983–2992` 的两个旧事件写回点；不要以只改用户态提交尾部就宣称步 22 也已正确。
4. 新增比完整 GL 更小的用户态 BO/IB 测试：创建 BO→映射→IB 只执行 CP_MEM_WRITE→**走真实 submit**→wait fence→检查目标字。连续至少两次，编号必须递增且每次写入不同 nonce。这样能在着色器/GMEM介入前单独裁决提交与完成路径。

参考尾包的四个参数 dword 如下；之前另有 type-7 header，加起来共五个 dword。这不是本轮已应用的补丁：

```c
/* A7xx：清理缓存完成后，把本次编号写入 RAM；轮询方式不要求中断位。 */
ring(0x31u | (1u << 27));
ring(fence_address_low);
ring(fence_address_high);
ring(submission_number);
```

实施时应优先用命名常量/字段构造，不把魔数分散到各条路径。

## P1-1：FD725 的 bank bit 只更新了软件参数，没有更新硬件 NC_MODE 组合

**证据：**

- `drivers/gpu/hakios.adreno.c:3351–3353` 返回 HIGHEST_BANK_BIT=16。
- `Mesa/src/freedreno/common/freedreno_devices.py:1045–1062` 的 FD725 条目也为 HBB=16。
- 同机 `vendor/drivers/gpu/msm/adreno-gpulist.h:2112–2139` 的 gen7_4_0 配置：2 MiB GMEM、GMU 4.0.7、HBB=16，与本轮 bring-up 参数相符。
- `vendor/drivers/gpu/msm/adreno_gen7.c:484–507` 计算 `bank_bit=(highest_bank_bit-13)&3`，将它同时编进 RB、TPL1、SP、GRAS、UCHE。
- 本机 DTB `Mu-Silicium/Resources/DTBs/phk110.dts:20066` 的 min-access-length 为 `0x20`，因此这里不加 64 B access 的 bit 3。
- 当前 `hakios.adreno.c:2803–2810` 仍写旧固定值，注释还说 HBB=14，缺 GRAS 那一项。

按同机 vendor 的字段公式，HBB=16 时 bank_bit=3；当前对应字段却是 1：

| 寄存器，word index | 当前实际初始化值 | 按 HBB=16、MAL=32 的 vendor 公式 |
|---|---:|---:|
| RB_NC_MODE_CNTL，0x8e08 | `0x812` | `0x816` |
| TPL1_NC_MODE_CNTL，0xb604 | `0x2` | `0x6` |
| SP_NC_MODE_CNTL，0xae02 | `0x22` | `0x26` |
| GRAS_NC_MODE_CNTL，0x8602 | 本函数没有设置 | `0x60` |
| UCHE_MODE_CNTL，0x0e01 | `0x200000` | `0x600000` |

word index 可由 `vendor/drivers/gpu/msm/gen7_reg.h:726、741、826、865、910` 交叉核对。上述是**源码配置不一致的事实**；它是否导致某种贴图/压缩/GMEM 读回错误，还需真机区分资源布局与继承寄存器状态，不能仅凭差异就宣称已经定位黑屏根因。

**认知纠正：** 阶段 39 报告说“freedreno GL 不查 HIGHEST_BANK_BIT/UBWC_SWIZZLE 的内核 GET_PARAM，所以这些 TODO 不挡 GL”。这只能说明 GET_PARAM 调用链不依赖某个返回值，不能说明 GPU 硬件的内存布局寄存器可随便沿用另一芯片的值。软件的设备表与硬件的 NC_MODE 仍须满足同一个契约。

**建议：** 将这一组配置作为一个明确的 cape/gen7 布局单元修正与核对，保留写前/写后取证；用小尺寸 linear/sysmem 测试和 tiled/GMEM 测试分层验证，再扩大至全屏。不能只改 RB 一个寄存器，更不能用再次通过 CP_MEM_WRITE 代替纹理/渲染目标验证。

**不要把所有 vendor 值差都同等升级：** `UCHE_CACHE_WAYS` 当前是 0x4、vendor 初始化是 0x800000，但 Mesa FD725 的 `a730_raw_magic_regs` 还会写 0x00840004（`freedreno_devices.py:939–940`；`fd6_emit.cc:881–896` 实际发出 raw-magic 写）。因此 CACHE_WAYS 必须按“初始化后、首个 Mesa restore 后”分别看值，不能直接当成本轮已证根因。`UCHE_CMDQ_CONFIG` 缺失则保留为第二梯队配置审计项，位置与字段在 vendor `gen7.c:462–467` 已明确，但没有独立运行时反证。

## P1-2：gl_test 是诊断输出程序，当前不是能拒绝错误图像的验收器

**证据：** `userland/src/gl_test.c:322–350、352–367`。

程序先把 readback 缓冲填成 0x55，再调用 glReadPixels；随后统计覆盖率、打印像素和 `glGetError()`，**没有对错误、像素、覆盖率做条件失败退出**。找不到显示服务时 `:355` 仍返回 0；上屏调用返回非零时 `:362` 仍打印“the picture is on the panel”，最后也返回 0。shader 编译失败只打日志，链接失败会返回 1，但读回与显示不具备同样的判定纪律。

本轮抽取真实 `main`，只把 GL/IOKit 换成替身：不绘制、不写 readback，返回 GL 错误 0x502，上屏调用返回 1。真实 main 输出：

```text
error 0x502
所有采样点：85 85 85 85
256 of 256 pixels inside the triangle (100%; 26% by geometry)
the picture is on the panel (0x1)
进程退出码：0
```

这不是“复现了真 GPU 画错”，而是**复现了验收器遇到明显错误时仍报进程成功**。`docs/waves/wave39-mesa-userland.md:186、202` 的“逐采样点断言”与源码不符。背景 RGBA 应接近 `(26,26,51,255)`，三角形面积预期 26% 的几何解释是对的；但这些正确预期尚未变成机器判据。

**建议：** 增加明确的成功/失败模式：要求硬件测试的 renderer=FD725（软件对照单列）、FBO/编译/链接成功、各阶段 GL error=0、背景和多个三角内样本在合理容差内、覆盖率在约定范围、面板调用成功。分别输出 `RENDER_PASS`、`READBACK_PASS`、`PRESENT_CALL_OK`，进程失败要有非零退出码。面板调用成功也仍不证明肉眼见图，需要独立屏摄。远端非 TTY 时建议显式刷新阶段日志，以区分建上下文、首次 submit、glFinish 和 readback 的挂点。

## P1-3：GL 执行器会把失败输出当完成，且 shell 包装吞掉了远端进程退出码

**证据：** 仓内 `wave38-scripts/gltest-run-v38.py:98–123`。

远端命令为 `gl_test …; echo GL_RC=$?`，所以 SSH 的 rc 通常是 echo 的 0；随后执行器判断：

```python
# 当前判断：只要有 gl_test 字样，即使 GL_RC=1 也进入完成分支。
rc == 0 and ("GL_RC=0" in out or "gl_test:" in out)
```

本轮从实际脚本 AST 抽取这个条件直接求值：`gl_test: no OpenGL ES context\nGL_RC=1` 被接受，`softpipe\nGL_RC=0` 也被接受。随后 `done_gl=True`，运行 fill/u2f，主程序返回 0。脚本虽然自述“只执行、判定归 阶段 39”，也不应把失败尝试停止为“DONE”并把性能测试接在后面；“已尝试”“执行成功”“硬件首帧通过”应是不同状态。

**建议：** shell 先保存实际 rc、输出结构化标记、再 `exit` 相同 rc；runner 同时检查唯一标记与进程结果。只有完整硬件渲染判据通过才跑 fill，软件对照用单独结果。每次 attempt 保留独立 stdout/stderr 文件，当前 `:80–81` 覆盖同名文件会丢掉前几次最有价值的失败细节。

## P1-4：当前 GL 没拿到执行证据，不能沿“GPU 挂了”的假设继续改寄存器

**证据：** `wave38-scripts/gltest-run-v38-w38gl2.log` 的多次 `rc=255/out 0 B`；配套 `gltest-w38gl2-gl.err`；两份 `gltest-w38gl1/2-gl.out` 实读都是 0 B。

审阅期间日志还在被并行执行方追加：早先 stderr 是节点 open 不支持、banner 超时；后续样本能发 TCP SYN，但收到 RST|ACK，仍未建立 SSH 会话。前者应先查实际 host 驱动/USB 归属，后者应查设备相位、en0/sshd 是否就绪；二者都不构成“glFinish 卡住”证据。本轮不操作设备，也不据此确定 VBoxUSB 或某个特定进程就是责任方。

静默 260 s 只能处理“命令刷新了 loader 的空闲窗”这一类相位问题，不会自动修复 host open 不支持。当前 banner 前失败也不能证明每次失败尝试都已向 loader 发了 netmode 命令；执行器 `:125–128` 的固定诊断句应按实际失败阶段收窄。

**建议：** 由设备执行方先取得同一 boot 的最小 SSH nonce 应答，再立即在同一连接内跑阶段化 GPU 探针；明确记录 kernel/session ID、剩余会话时间。或者用已验证的启动 job 自动运行测试并把 stdout/stderr 留到可取证位置。`wave39-scripts/build-mesa.sh:40` 固定 `RC_JOBS=rc.jobs.ssh`，`GL=test` 只带工具，不自动运行 `rc.jobs.gltest`；不能等一个没有配置的启动任务自己产生首帧日志。

## P2：修复范围、声明与次要工程问题

### P2-1：应将“bring-up 通过”和“绘制/桌面加速通过”分级

`hakios.adreno.c:3839–3848` 的 gpu=1 自动路径明确停在步 21，步 22 未执行。阶段 37 的 gcc/gpucc 正名、取消危险熔丝访问、zap 三段适配及删除非法 address-mode 写，有各自的故障前后记录，**没有理由因为后续绘制缺口就整体推翻它们**。

但 `CP_MEM_WRITE` 不会验证 shader 编译/执行、tiled/UBWC 地址、GMEM 分块、CCU 缓存、用户态 fence 或 IOSurface 交换。建议以后分别报告：硬件初始化/CP 写字；真实 submit+fence；硬件 GL 像素；面板呈现；窗口服务器加速。`GL=test` 在 `userland/build.sh:48–49、350–353` 的定义本就保留原窗口服务器路径，因此即使三角形通过，也不能宣称系统桌面已走 GPU。

### P2-2：zap 三段修复针对当前文件有效，“通用 ELF hashes 识别”还不成立

`hakios.adreno.c:1675–1694` 仍假设 ELF32 header=52、phdr=32，通过“某段 filesz 恰好补足文件长度”猜 hashes；没有核验 e_phoff/e_phentsize、完整程序头表边界、hash 标志或唯一候选。循环遍历不可信 segments 时可越界读取。当前有固定的已验证 a730_zap.mdt，不能把这个健壮性缺口写成本轮真机拒载的根因；但未来换固件时应该先按 Qualcomm MDT 格式及 ELF 边界验证，再交给 TrustZone。不要遇到 firmware 版本变化就继续加长度特判。

`step_zap_load:2730–2741` 把多种 SCM 失败解释成“之前已装载”，也属于需要保留实际返回码与状态验证的旧假设；本轮 v33 已记录真实认证成功，不用该 fallback 去否定现有成功记录。

### P2-3：Mesa 包装脚本的示例参数语法与实现不一致

`wave39-scripts/build-mesa.sh:13–15` 写 `build-mesa.sh AIR=1/IMAGE=1`，但脚本没解析 `$@`，实际在 `:29、38` 读环境变量。照示例把赋值放在脚本名后只会成为位置参数，不能启用对应分支。正确用法是 `AIR=1 bash wave39-scripts/build-mesa.sh`、`IMAGE=1 bash wave39-scripts/build-mesa.sh`，或实现明确的参数解析。这不否定已存在的 GL ramdisk，但会让后来复现者漏建测试载体。

## 建议的下一轮顺序与工作量

| 次序 | 内容 | 需要的证据 | 粗略工程量 |
|---|---|---|---|
| 1 | 修正 gl_test/runner 判据与阶段日志 | 错上下文、软件回退、错误像素、上屏失败都不能记硬件 PASS；正常软件对照独立输出 | 0.5—1 人日 |
| 2 | 把 a7xx fence 契约补齐，先走最小真实用户态 submit | 两次以上 nonce CP_MEM_WRITE 经 BO/IB→submit→fence 完成；正常释放及关闭客户端 | 0.5—1.5 人日，真机排期另计 |
| 3 | 同步 HBB=16 的 NC_MODE 配置组 | 正确的配置写后值；小尺寸与全屏、linear 与 tiled/GMEM 分开验证 | 1—2 人日，若出现新硬件故障另估 |
| 4 | Mesa 真渲染与显示 | FD725、编译/链接/FBO/GL error、像素/26% 覆盖率、实际 submit/fence、面板屏摄 | 至少一个完整有效会话，建议复验不同 boot |
| 5 | GL=1/窗口服务器集成及性能 | 真实 IOSurface/合成负载、连续帧、正确读写同步、跨进程与退出回收；随后才跑 fill | 独立后续阶段，不能由一张三角图估完 |

第 1/2/3 项应保持一代一主题与明确组合基线；固定 kernel、loader、ramdisk 和工具哈希，避免把 USB 诊断版、GL 载体和 GPU 变更混成一个不可归因的新包。当前最合理的技术判断是 **先裁决 submit/fence，再裁决布局配置，最后扩大图形负载**。不建议先升 Mesa、换整套固件或依据零字节 SSH 输出盲调 shader/GMEM。

## 本轮验证记录与限制

- 对照了 `hakios.adreno.c.v27-orig` 到当前文件的修复差异；逐段检查 step 19/20/21、用户态 submit/fence/参数、IOKit 请求、Mesa 的实际对应实现与 gl_test/runner。
- 编译运行了真实提交函数的隔离包捕获程序，确认当前首字 `0x00000004` 与 bit 27 缺席；这是机器码生成前的真实 C 路径输出证据，**不模拟 GPU 是否接受兼容事件**。
- 编译运行了真实 gl_test main 的 GL/IOKit 替身反例，确认错误图像、GL 错误、上屏错误仍 exit 0；从实际 runner AST 验证上下文失败及 softpipe 被完成条件接受。
- 临时隔离程序自动清理，没有调用 `build.sh`、设备接口或实际图形库；真实 GPU 的 hang/fault/错误像素仍需真机验证证据。
- 网络核对只访问 Linux 官方固定版本源码，经用户指定 `127.0.0.1:7897` 代理；核心裁决另有本地同机 vendor 与同版 Mesa 两份独立实现交叉支持。

**交付边界：本报告给出已验证的代码缺口与按优先级排列的修复路线，不声称已经替设备完成 GPU 修复或确认了某次黑屏的唯一根因。**
