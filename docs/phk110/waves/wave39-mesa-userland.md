# 阶段 39 · 2026-11-11 · Mesa 25.0.7 交叉构建打通与 GL 首帧载体

> 2026-11-11 · 阶段 39 Mesa 用户态执行记录（接 wave37 完成、wave35 §5 施工单 #6）
> 任务书：①从内核源读出 HakiosGPU 服务的用户态对接面写成接口备忘；②拉取/钉住 Mesa 25.0.7（SHA 记账）+ freedreno FD725 编译需求评估 + Darwin/arm64 交叉构建路径设计与**实作**；③shim 设计文档 + 最小实现骨架（不做真机验证）；④照 raphael 模板出首帧计划（一次刷写+一次会话能验什么）；⑤交付 wave 文档 + 可构建产物（WSL 树内）+ STATUS 判定行 + git 提交。
> 红线执行：**零手机** ✓（wave38 占用设备做 USB 自愈真机判定；本轮无任何 adb/fastboot/usbipd/刷写调用）✓；**内核驱动只读** ✓（`hakios.adreno.c`/`hakios.gpu.cpp` 零改动，本轮对 WSL 树的全部写入 = 构建产物 + 用户态镜像构建，见 §2.4/§5 树状态注记）；`wsl --shutdown` ×0 ✓。
> 证据分级：**[实证]** = 文件/字节/行号/sha 可复现；**[实测]** = 本轮构建实测；**[MESA]** = `~/hakios/kernel/xnu-deps/build/mesa/mesa-25.0.7`（本轮解包+patch 后的源树，tarball sha256 钉 592272df）；**[转述]** = 上游 redwood 的真机结果（consulting-2026-11-03 "Mesa 25.0.7 freedreno, GL=1 smooth, wallpaper drawn" 与 mk-mesa.sh 头注；我们未复现）；**[待机]** = 需真机会话定案。

---

## 0. 判定（先行，八条）

1. **Mesa 25.0.7 交叉构建在本树首绿 [实测]**：`ninja 1134/1134`，产物 `~/hakios/kernel/xnu-deps/build/mesa/out/libOSMesa.8.dylib` **14,855,048 字节**（与上游 mk-mesa.sh 头注记录的 redwood 构建字节数逐字相同——同一 pin 同一 patch 族在另一台宿主上的呼应）、`Mach-O 64-bit arm64`（TWOLEVEL/DYLDLINK）、**1296 个 gl\* 导出**；`strings` 内含 **"FD725"** 身份串 = freedreno 设备表已编进库。交叉构建路径（meson cross darwin/ios/aarch64 + xnu-clang + iPhoneOS16.5.sdk + theos ld64）**实作可行，非纸面设计**。
2. **首帧载体已建成 [实测]**：GL=test root.apfs（v25 配方唯一 delta = GL）= **`c2780842…`，8,089,600 字节**（旧 pin `156b5be1` = v25/v33 ramdisk，仍在 device-layer payload bins 里钉着）：`bin/gl_test`（sha `0836948e`）+ `bin/u2f_test` + `lib/libOSMesa.8.dylib`（与 mk-mesa 产物**字节同源** `e0bd033a`）+ `fw/` 8 件 a730 固件全带。payload 预算毫无压力（内核 15.1 MB + 新 ramdisk 8.1 MB ≪ 64 MB 窗口）。
3. **接口备忘（§1）[实证]**：HakiosGPU = **IOService "HakiosGPU" + IOUserClient "HakiosGPUUserClient"**，`externalMethod` 选择器 = **Linux msm DRM ioctl 号原样**（0x40 GET_PARAM … 0x4c SUBMITQUEUE_QUERY），外加两个自有请求 0x7e（IOSurface 作 buffer）/0x7f（像素直接上屏）；buffer 内存 = `clientMemoryForType(handle)`（mmap 的等价物）。用户态替身 = `tools/mesa/hakios-drm/hakios.drm.c`（上游已备，redwood 真机验证过 [转述]）。
4. **PHK110 的 shim 代码 delta = 零 [实证]**：协议面（msm DRM uapi）跨 a6xx/a7xx 不变；FD725 差异全部在**参数值**，而 v33 内核已全部就位（chipid 0x07030002 / GMEM 2 MiB / HBB 16）。上游 shim 对 PHK110 **不需要一行新代码**——本轮以"编进绿的库 + FD725 串在库内"为骨架状态证据（§3.5），诚实结论而非省工。
5. **关键设计事实（本轮源码内证实，对内核 TODO-DEV 的消账有直接价值）[MESA 实证]**：25.0.7 的 freedreno msm 后端只查 10 个内核参数（GPU_ID/GMEM_SIZE/CHIP_ID/GMEM_BASE/MAX_FREQ/TIMESTAMP/PRIORITIES/FAULTS/SUSPENDS/VA_SIZE）；**HIGHEST_BANK_BIT / UBWC_SWIZZLE / MACROTILE_MODE 在 GL 链不查内核**——来自 Mesa 设备表（FD725 条目自带 HBB=16）。内核 `hakios_gpu_parameter` 的 `UBWC_SWIZZLE=6 [TODO-DEV]` **不挡 GL 首帧**；它只被 Turnip 查（`tu_knl_drm_msm.cc:143`）——记为**备胎路线**（Turnip+metal2vulkan）的风险项。
6. **FD725 身份链全通 [MESA 实证]**：`freedreno_devices.py:1047-1048` = `GPUId(0x07030002, "FD725")` + `0xffff07030002` no-speedbin fallback；CHIP.A7XX + a7xx_base + a7xx_gen1 + a730 magic regs + HBB16。内核 CHIP_ID 参数 = `0x07030002 | speed_bin<<32`，cape 熔丝零暴露 → speed_bin=0 → 精确命中表项。`cmdbuf_start_a725_quirk`（FD725 条目携带的属性）**只被 Turnip 用**（tu_cmd_buffer.cc），freedreno GL 无视——GL 首帧无此变量。
7. **环境增量三件（WSL 宿主差异，已固化进 `wave39-scripts/build-mesa.sh`）[实测]**：①`patch` 未装（dnf install patch）；②`meson`/`ninja` 未装（pip --user → ~/.local/bin）；③**WSL 会话收割后台进程** + `| tail` 管道吞退出码——两者叠加造成 mk-mesa.sh 首跑"exit 0 假绿"（根因链：set -e 死于 patch 127 → 管道返回 tail 的 0）。教训入 §2.4。
8. **air_run 一并建成 [实测]**：9,909,136 B Mach-O arm64 PIE（AIR=1 目标）——上游定性"唯一能判定 Adreno 是否吃窗口服务器之外的工作"的 Metal 翻译画图测试器，供后续 Metal 路线探针波使用。

---

## 1. 接口备忘：HakiosGPU 的用户态对接面（内核侧事实源 = 本轮逐行读源）

### 1.1 服务与客户端形态

- 内核侧两文件分工（都只读，37 号完成态）：`drivers/gpu/hakios.adreno.c` = 22 步唤醒机 + 提交/围栏/地址分配的实现层（步 21 `THE GPU STAYS ON` → `HakiosGPUStart()`，boot-arg `adreno_keep=1`）；`drivers/gpu/hakios.gpu.cpp`（1,218 行）= **IOKit 服务/用户客户端协议层**。
- 服务注册：`HakiosGPU : IOService`，`setProperty(kIOUserClientClassKey, "HakiosGPUUserClient")` + `setName("HakiosGPU")` + `registerService()`；挂在 `IOService::getPlatform()` 下。用户态匹配：`IOServiceMatching("HakiosGPU")` → `IOServiceOpen(..., type 0, &connection)`。
- 打开门槛：`HakiosGPUUserClient::start` 要求 `hakios_gpu_ready()`（= `gpu_kept`，即 adreno=21 + adreno_keep=1 走完）——**GPU 没被内核留在系统手里时，打开直接失败**；请求面同理（`kHakiosShow` 例外，见 1.4）。

### 1.2 请求面（externalMethod 选择器表 = msm DRM ioctl 号）

每个请求 = 一把选择器（ioctl 号低字节）+ 一份入出兼用的结构体（`IOConnectCallStructMethod`）。[实证] hakios.gpu.cpp:106-121 枚举 + :1150-1218 dispatch：

| 选择器 | msm 语义 | 内核行为（本机） | 返回 |
|---|---|---|---|
| 0x09 | DRM_IOCTL_GEM_CLOSE | freeBuffer（busy 时进 fLeft 池延后释放）| — |
| 0x40 | MSM_GET_PARAM | `hakios_gpu_parameter`（§1.5 值表）| 不认识的参数 = BadArgument |
| 0x41 | MSM_SET_PARAM | no-op（"程序的名字，给 Linux 的用户列表用"）| Success |
| 0x42 | MSM_GEM_NEW | gemNew：页对齐零页新 buffer（write-combined；`gpu_cached=1` 时普通内存+提交前刷缓存）；≥256 KiB 的回收 buffer 进 keep 池按尺寸/flags 原样复用（`gpu_keep` TUNABLE，=2 时归还前清零）| handle 回填 |
| 0x43 | MSM_GEM_INFO | GET_OFFSET=handle<<32（占位）/ GET_IOVA=GPU 地址 / SET_NAME（不留）/ GET_FLAGS | — |
| 0x44 | MSM_GEM_CPU_PREP | 等 `hakios_gpu_last()`（GPU 全空）——按超时（`msm_timespec` 换算，`GPU_PATIENCE_MS` 5 s 帽）| 忙 = Busy（含"过去时刻"诊断行）|
| 0x45 | MSM_GEM_CPU_FINI | no-op | Success |
| 0x46 | MSM_GEM_SUBMIT | submit：copyin bos/cmds → 逐 buffer 刷缓存（surface seed 或 `gpu_cached` 或首次 seen）→ CMD_BUF 型命令逐条校验（4 字节对齐、无 reloc、界内）→ `hakios_gpu_submit(addresses, words, count)` → fence 回填；`MSM_SUBMIT_FENCE_FD_OUT` 给 -1（无 fd fence）| fence=0 = Timeout（环满）|
| 0x47 | MSM_WAIT_FENCE | 拒绝"未来围栏"（`fence - last > 0` = BadArgument，防一个烂等待判死 GPU）→ gpuWait（200 µs 轮询，**无中断**）| 超时 = Timeout |
| 0x48 | MSM_GEM_MADVISE | retained=1 恒真 | Success |
| 0x4a/0x4b | SUBMITQUEUE_NEW/CLOSE | NEW：id = 客户端内自增号；CLOSE：no-op | id 回填 |
| 0x4c | SUBMITQUEUE_QUERY | faults = 0 拷出 | Success |
| **0x7e** | （自有）HakiosSurface | IOSurface 的内存作 buffer（kHakiosDescribe=0xffffffff 只描述不占 handle；像素从共享状态后一页起）| 宽高/rowBytes/格式/planes 回填 |
| **0x7f** | （自有）HakiosShow | 调用者像素（32bpp 蓝先）copyin → `MiniIOMobileFramebufferShow` 直上屏（**测试器专用**；此请求在 GPU 未 ready 时也可用）| ≤4096²，rowBytes≥4×width |

超范围选择器 = Unsupported + `IOLog` 行（诊断可读）。

### 1.3 内存模型（Linux mmap 的等价物）

- `clientMemoryForType(type=handle)` 返回 buffer 的 IOMemoryDescriptor → 用户态 `IOConnectMapMemory64(connection, handle, ..., kIOMapAnywhere)`；标记 `b->seen`（首次映射后提交前刷缓存路径用）。
- buffer 内存 = 有线内核内存，逐页进 3D 核 SMMU 上下文（`hakios_gpu_map(address+offset, phys, readonly)`）；新建即零、write-combined（GPU 读写的内存不过本核缓存——Linux 对 freedreno 同款）。GPU VA 窗 = `0x20000000 + 0xe0000000`（低于 4 GB，Linux 的保守同款）[实证] hakios.adreno.c:3240-3241。
- 配额：每客户端 8192 个 handle / 单 buffer ≤256 MiB / 提交 ≤128 命令块、8192 BO。
- 释放纪律：GPU 还在用就先挂 fLeft（64 个）等 `reap()`；自有大 buffer 进 fKept（48 个/160 MiB/60 s 寿命）按同尺寸同 flags 秒还——上游按 CoreAnimation 模糊纹理的实测教训（6.8 ms vs 9.3-10 ms/帧）[转述 mk 头注]。

### 1.4 语义边界（hakios.gpu.cpp 头注原文归纳，[实证]）

无中断（200 µs 轮询等待）；单地址空间（所有客户端共享 GPU VA，客户端走了把自己的 buffer 拿走）；GPU 停答无恢复（`hakios_gpu_report("no answer")` 一次，此后不再等）；无 fd 化的 buffer/fence（syncobj 族全 ENOSYS——`hakios.drm.c` 尾部 NONE 桩一一对应）。

### 1.5 内核参数面（GET_PARAM 值表，v33 树 [实证] hakios.adreno.c:3239-3360）

| 参数 | 值 | 对 Mesa 的意义 |
|---|---|---|
| 0x01 GPU_ID | 0 | freedreno 以 CHIP_ID 为准（`gpu_id || chip_id` 判存活）|
| 0x02 GMEM_SIZE | **2 MiB**（=FD725 vendor/mainline 值）| fd_pipe->gmem |
| 0x03 CHIP_ID | **0x07030002**（speed_bin=0 在高位）| **FD725 表项精确命中** |
| 0x04 MAX_FREQ | core_kHz×1000（283 MHz 现值）| 管道信息 |
| 0x05 TIMESTAMP | mach_absolute_time() | — |
| 0x06 GMEM_BASE / 0x08 PP_PGTABLE / 0x09 FAULTS / 0x0a SUSPENDS / 0x11 RAYTRACING | 0 | 合法零值（RAYTRACING=0 = a7xx_gen1 无 BV 面向 GL 的暴露位）|
| 0x07 PRIORITIES | 1 | submitqueue 优先级档位 |
| 0x10 HIGHEST_BANK_BIT | 16 | **GL 链不查**（设备表同值 16，双源一致）|
| 0x12 UBWC_SWIZZLE | 6 [TODO-DEV：vendor=6，本机 DT ubwc-mode=0x04] | **GL 链不查**（Turnip 查——备胎路线风险项）|
| 0x13 MACROTILE_MODE | 1 | 同上 |
| 其余（含 VA_START/VA_SIZE） | false（EINVAL） | freedreno 容忍：softpin 地址内核自派 [转述=上游 redwood 同款] |

---

## 2. Mesa 25.0.7 构建管线（实作绿）

### 2.1 管线（树自带 `tools/mk-mesa.sh`，本轮零脚本改动跑通）

pin：`VERSION=25.0.7`、`SHA256=592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6`（本轮下载后 **逐字命中** [实测]）。流程 = 下载 archive.mesa3d.org tar.xz → sha 校验 → 解包 → `tools/mesa/*.patch` 七件按序打（组合 sha `5e2cbbf7…` 写入源树 `.hakios-patches` 作失效缓存）→ `hakios-drm`/`air` 两目录拷进源树 → venv（mako/pyyaml/packaging）→ meson cross.ini（`system=darwin / subsystem=ios / cpu_family=aarch64`，`needs_exe_wrapper=true`，编译器 = xnu-deps 的 xnu-clang 包装器 → `/usr/bin/clang -target arm64-apple-ios16.5 --ld-path=ld64`，SDK = `~/theos/sdks/iPhoneOS16.5.sdk`）→ ninja（DRIVERS=`softpipe,freedreno`，`freedreno-kmds=msm`，llvm=disabled，osmesa=true，gles2，opengl，其余全关）→ llvm-strip + `install_name_tool -id /redwood/lib/libOSMesa.8.dylib` + 导出表 + `built-from`（patch+shim 组合 sha `376fd2cf…`，userland/build.sh 以此判 Mesa 过期）。

patch 族七件（本轮全数过 patch 无 fuzz [实测]）：`freedreno-darwin.patch`（shim 接线，§3.3 逐条）、`osmesa-es-profile.patch`（OSMESA_ES_PROFILE 常量 + 上下文属性）、`ir3-round-default.patch`（cov 舍入）、`ir3-shift-split.patch`（SSBO 偏移移位）、`ir3-ssbo-subdword.patch`（SSBO 亚字访问）、`air-frontend.patch` + `air-ir3.patch`（AIR/Metal 前端，air_run 用）。

### 2.2 本轮实测产物（WSL 树内路径清单 + sha 记账，[实测]）

| 产物 | 路径（WSL `~/hakios/kernel/…`） | 字节 | sha256（前 8） |
|---|---|---|---|
| **libOSMesa.8.dylib** | `xnu-deps/build/mesa/out/libOSMesa.8.dylib` | 14,855,048 | `e0bd033a` |
| air_run | `xnu-deps/build/mesa/out/air_run` | 9,909,136 | `feba09e0` |
| exported-gl.txt（1296 行）| `xnu-deps/build/mesa/out/exported-gl.txt` | 23,277 | `b87ad902` |
| gl.xml | `xnu-deps/build/mesa/out/gl.xml` | 2,752,127 | `efce4436` |
| built-from | `xnu-deps/build/mesa/out/built-from` | 68 | `22bca0a5` |
| mesa tar.xz | `xnu-deps/build/mesa/mesa-25.0.7.tar.xz` | 46,849,080 | `592272df`（=pin）|
| **root.apfs（GL=test）** | `userland/root.apfs` | 8,089,600 | `c2780842` |
| gl_test（进镜像）| `userland/obj/gl_test` | — | `0836948e` |
| libOSMesa（进镜像，拷贝验证 = e0bd033a 同源）| `userland/obj/libOSMesa.8.dylib` | 14,855,048 | `e0bd033a` |

复现入口：**`wave39-scripts/build-mesa.sh`**（环境自检+构建+记账；`AIR=1` 加 air_run；`IMAGE=1` 加 GL=test root.apfs）——本轮端到端实跑通过 [实测]。注意构建**不可逐字节复现**（树头注原文；布局会漂）——同 hash 只回答"同一个文件"，回答不了"同一份代码"；判 patch 是否在构建里 = 读 `xnu-deps/build/mesa/mesa-25.0.7` 源树（mk-mesa.sh 头注的规则）。

### 2.3 freedreno 对 FD725 的编译需求评估（结论：25.0.7 零额外需求）

- **身份**：`freedreno_devices.py:1047` `GPUId(chip_id=0x07030002, name="FD725")`（"Adreno730v3 or Adreno725v1"），+ :1048 `0xffff07030002` no-speedbin fallback；A6xxGPUInfo(CHIP.A7XX, [a7xx_base, a7xx_gen1], num_ccu=4, highest_bank_bit=16, magic_regs=a730_magic_regs) [MESA 实证]。内核 CHIP_ID 命中即配齐 GL 需要的全部设备参数（HBB/GL 初值/magic regs 来自表，不来自内核）。
- **a7xx 代码路径**：25.0.7 的 GL 用 fd6 一族吃 a7xx（CHIP.A7XX 世代判别），`cmdbuf_start_a725_quirk` 属性只被 Turnip 读（grep 全源树：`tu_device.cc`/`tu_cmd_buffer.cc`/`freedreno_dev_info.h`）——GL 构建与运行都无此依赖。
- **构建开关**：`freedreno-kmds=msm`（仅 msm 后端，无 kgsl/virtio）✓；llvm=disabled（ir3 编译器无 LLVM 依赖）✓；fd725 无需任何 meson 选项调整——与上游 redwood（a642L）用**同一条命令**构建，差异只在运行时内核应答的 chip_id。
- **升版注记**（wave35 §4 建议 #2 的落实位）：25.3.3/26.0.x 升级评估仍是独立准备工作项；本轮不升——首图变量最少原则。

### 2.4 环境增量与教训（本轮踩坑全录，[实测]）

1. `patch` 缺失 → mk-mesa.sh `set -e` 死在打补丁步；**`| tail` 管道把退出码吞成 0** → 首跑假绿。教训：管线验证必须验产物（ls + file + strings），不信退出码。已装 `patch-2.8`。
2. `meson`/`ninja` 缺失 → `pip install --user meson ninja`（python3.14/pip26）落 `~/.local/bin`，须显式入 PATH（mk-mesa.sh 不加）。
3. **WSL 会话收割后台进程**：`wsl.exe -e bash -c "… nohup cmd &"` 在 wsl.exe 退出时连 nohup 子进程一并回收——构建类工作必须在**前台单次 wsl.exe 调用**内完成（Bash 工具 600 s 帽内 ninja 全绿 = 本轮实测形态）。
4. 构建资源实测：20 核 / ninja 全绿 ~6-7 分钟（首次）；增量重跑（patch 集不变）= 秒级（`.hakios-patches` 失效缓存生效）。

### 2.5 Darwin host/target 支持度如实评估

- **target（darwin/ios/aarch64）**：实作绿——meson cross file + xnu-clang（clang 22.1.8 宿主 + cctools ld64 + iPhoneOS16.5.sdk）。Mesa 上游 meson 对 `host_machine.system()=='darwin'` 有分叉位（freedreno-darwin.patch 利用之），osmesa target 无 DRM/EGL/GLX 依赖，与 iOS SDK 自包含。ld64 跑时有一行 `libtinfo.so.6 no version information` 噪声（无害，产物正确）。
- **host（WSL Linux 侧工具链）**：meson/ninja/bison/flex/python3+venv 全数可用；无 macOS 宿主依赖。
- **上游构建系统对 Darwin 的原生根**：softpipe/sw 路径本来就是跨平台的；freedreno 走 darwin 分叉 = **上游树的 fork 私有 patch**（非 Mesa 官方支持面）——如实记录：这是上游 redwood 项目的资产，非 Mesa 官方 Darwin 支持主张 [MESA]。

---

## 3. shim 设计：freedreno 的内核对接层（drm-like ioctl → HakiosGPU 服务操作）

### 3.1 架构（四层，[实证] 源码定位）

```
gl_test / eagl (GL ES 调用)
  → Mesa gallium: fd6_context / fdl / ir3        （a7xx 绘制准备，纯用户态）
  → Mesa freedreno drm 层: src/freedreno/drm/     （fd_bo/fd_pipe/fd_submit 抽象）
      msm 后端: msm_pipe/msm_bo/msm_ringbuffer_sp （msm DRM 语义）
  → 替身 libdrm: src/hakios-drm/hakios.drm.c      （xf86drm.h 签名 → IOKit 调用）
  → 内核: HakiosGPUUserClient::externalMethod     （选择器 = ioctl 号，§1.2 表）
      → hakios.adreno.c 实现层（submit/fence/地址/SMMU）
```

### 3.2 请求映射表（hakios.drm.c 的全部对接函数，[实证]）

| libdrm 调用 | 替身实现 | 内核落点 |
|---|---|---|
| `drmOpenWithType("msm")` | `IOServiceMatching("HakiosGPU")+IOServiceOpen`；fd = `/dev/null` 的 dup（"一个 GPU、一进程一连接"）；非 msm 名拒开 | 服务 start 门（GPU ready）|
| `drmIoctl(fd, request, arg)` | `IOConnectCallStructMethod(conn, request & 0xff, arg, IOCPARM_LEN(request), …)`；IOReturn→errno 映射表（NoMemory→ENOMEM/Timeout→ETIMEDOUT/Busy→EBUSY/…）| §1.2 选择器直通 |
| `drmCommandWrite[Read]` | 同上（`DRM_COMMAND_BASE + index`）| — |
| `drmGetVersion` | 恒报 `msm 1.7`（"softpin，不更新"）| —（fd_device_version=minor 7 → SOFTPIN 路径）|
| `drmGetCap` | 恒 0 | — |
| `hakios_drm_map/unmap(fd, handle)` | `IOConnectMapMemory64/UnmapMemory64` | clientMemoryForType（§1.3）|
| `hakios_drm_surface(fd, *)` | 0x7e 请求（kHakiosDescribe 描述模式）| surfaceBuffer |
| `drmPrimeFDToHandle` | 0x7e 请求（"fd"=IOSurface ID）| 同上占 handle |
| `drmPrimeHandleToFD`/`drmSyncobj*` | ENOSYS 桩 | 内核语义边界（§1.4）|

### 3.3 freedreno-darwin.patch 差异面逐条（七处，[实证] patch 文本）

1. **meson.build 根**：darwin+freedreno → `dep_libdrm = declare_dependency(include src/hakios-drm, link IOKit+CoreFoundation)`（无 HAVE_LIBDRM 副作用）。
2. **freedreno_bo.c**：import 路径 `__APPLE__` 分支 = IOSurface ID 经 `hakios_drm_surface` 取 size（替代 lseek-fd）；`fd_bo_map` = `hakios_drm_map`（替代 os_mmap）；fini = `hakios_drm_unmap`。
3. **freedreno/drm/meson.build**：darwin 时把 `hakios.drm.c` 编进 libfreedreno_drm；virtio 时才链 libvdrm（修 TODO）。
4. **msm_priv.h**：超时基准钟 = `CLOCK_MONOTONIC_RAW`（内核用 mach_continuous_time 口径；普通 MONOTONIC 在 Darwin 是"日期减启动日期"，错钟会"超时还没开始就过了"）。
5. **ir3_disk_cache.c**：darwin 无 build-id 注 → 磁盘缓存整体关闭。
6. **fd6_draw.cc + freedreno_batch.h**：读 framebuffer 的首绘制前加 CCU color flush + UCHE invalidate（a642L CoreAnimation 阴影实测教训的 barrier 修复，gen7 同表驱动路径共享）[转述 patch 注]。
7. **osmesa_target.c + osmesa.c**：`osmesa_create_screen()` 先试 GPU 屏（`drmOpenWithType("msm")` → `fd_drm_screen_create_renderonly`；`OSMESA_SOFTWARE=1` 强制软管）败了才落 null winsys；`osmesa_surface_resource` = IOSurface → BGRA 纹理（仅 'BGRA' 且 0 planes 过闸）——window server 出画链的纹理注入点。

### 3.4 PHK110 delta 分析（结论：协议层零代码 delta；风险两项各就各位）

- 协议不变性：msm uapi 的请求号/结构跨代不变；fd6 用 GET_PARAM 的 CHIP_ID 查表自适应——FD725 参数面 v33 已全数就位（§1.5），无内核改动需求（内核只读纪律下也不允许）。
- 风险 A（GL 无关）：`UBWC_SWIZZLE=6 [TODO-DEV]` ——只影响 Turnip 路线；GL 链查表自洽。**消账方式**（未来波）：真机 `/sys/firmware/fdt` 的 ubwc-mode=0x04 与 vendor 6 的差异在 Turnip 备胎启用前用一次参数对照会话定案。
- 风险 B（GL 运行时，[待机]）：a7xx_gen1 的 GL 运行时行为（GMEM 2 MiB 分块、fd6 每批 flush 序列）在本机无真机数据——上游 redwood 证据是 a642L；fd6 a7xx 代码在 Linux 侧有社区真机验证口径（landscape §3-I，二手），本机首会话 = 直接证据（§4.4 分支表覆盖）。
- BGRA 闸门：`osmesa_surface_resource` 只收 'BGRA'/单平面——window server 出画格式与本机面板链（MiniIOMFB）兼容性属显示波域，本轮不越界。

### 3.5 骨架状态（"最小实现"的诚实形态）

- **shim 本体 = 上游资产，已编进绿的库**：`libOSMesa.8.dylib` 内 `hakios.drm.c` 与 freedreno msm 后端共存（built-from `376fd2cf` 锚 patch+shim 组合；FD725 串在库 = 设备表同库证据）。**本轮零新增 shim 代码**——因为对 FD725 不需要；这本身就是设计结论（§3.4），不是省工。
- **本轮新增的可运行骨架 = `wave39-scripts/build-mesa.sh`**（复现入口：环境自检 → mk-mesa → 记账 → 可选 IMAGE=1 出 GL=test root.apfs），端到端实跑绿。
- **（备胎路线留档）**：Turnip 接线若启用，对接面 = 同一 HakiosGPU 服务的 0x40-0x4c + 0x10/0x12/0x13 参数（Turnip 查 HBB/UBWC/MACROTILE）——按 consulting 裁决列实验备选，本阶段不施工。

---

## 4. 首帧计划（raphael 模板：三角形绘制 → 读回验证 → 上屏）

### 4.1 载体与语义（全部上游现成件 [实证] 源码）

`userland/src/gl_test.c`（367 行）= raphael 式端到端：`OSMesaCreateContextAttribs(ES 2.0 profile, RGBA)` → 打印 `GL_VENDOR / GL_RENDERER / GL_VERSION` → FBO 纹理（默认 1080×2400，**参数可传**）→ GLSL 三角（红绿蓝三顶点）→ `glDrawArrays(GL_TRIANGLES,3)` → `glFinish` → `glReadPixels` 全幅读回 → **逐采样点 RGBA 断言**（角/中心/三色角邻近）+ **彩色像素占比 vs 26% 几何预期** + `glGetError()` → 经 `kHakiosShow(0x7f)` 把图上屏 N 秒。GPU 在 = freedreno 画；不在 = softpipe 画（renderer 字符串即分水岭）。另有 `fill` 模式（`gl_test fill W H`）：10 类帧型 ×16 帧/最短值——性能画像工具，首帧后用。
`rc.jobs.gltest`（上游）：`rwtouch wait 14` → `gl_test 8`——无人值守路径（锁屏画完让位后跑）。

### 4.2 镜像组装（flash 波的配方，本轮已把**可预建件全部建好**）

- v39 payload 三件套：kernel = **v33 `55a8d40f`**（GPU-capable，37 号完成件）+ ramdisk = **`c2780842`（GL=test root.apfs，本轮新出）** + cmdline = v33 字节（`gpu=1`，36 号已验字节）——`wave36-scripts/make-payload-v25.sh` 的配方模式，ramdisk 换 c2780842 即可；loader/resident/FD/shim 钉位沿用（v33 graft `6d5efeb5` 的 FD `8924cb67`/shim `108ce972` 链）。
- ⚠ 排期注记（已按当时的工作安排队列刷新裁决更新，STATUS"队列刷新"段）：wave37 §5-2 记录的互斥（wave38 原 graft `742bce63` 带 v26 内核 vs v33 GPU 修复）**已被 v34 重基线裁决消解**——v34 = v33 内核条目 `55a8d40f` + wave38 loader.efi `3f595c52` + v33 的 gpu=1 cmdline。v39 首帧载体（ramdisk `c2780842`）与 v34 基线**直接兼容**：首帧刷写 = v34 基线 + 本阶段 ramdisk 换入，随 wave38 真机判定排期一并走。
- 预算 [实测]：内核 15.1 MB（树内 `hakios-kernel`，15,097,968 B）+ ramdisk 8.1 MB，远小于 64 MB payload 窗；root.apfs 内余 256 块（1 MB）。
- 面板分辨率：gl_test 默认 1080×2400 = redwood 面板；PHK110 真值从 DTB/显示驱动行读（显示波域），会话内显式传参即可（`gl_test 8 W H`）。

### 4.3 一次刷写 + 一次会话能验什么（判定行清单，全部可从 SSH 会话取证）

前提一次会话 = boot_b v39（gpu=1 + adreno_keep=1 走完步 21 → HakiosGPU 在）+ SSH E2E 通道（verdict27 语义）：

1. **内核侧回归**（logdump/控制台，wave37 §3 清单复现）：`adreno: 21: … THE 3D CORE WRITES OUR MEMORY ON COMMAND` + `THE GPU STAYS ON … the service HakiosGPU`；此后新面孔 = `HakiosGPU: submission N: …`（有客户端真用 GPU 的第一行）+ 5 秒统计行（buffers made / kept / GPU worked µs 分布）。
2. **用户态身份行**（gl_test 输出首行）：`gl_test: Mesa…; **FD725**; OpenGL ES 3.2 Mesa 25.0.7` ——renderer 串 = FD725 ⇒ freedreno 认出本机芯片、msm 后端走通 GET_PARAM/IOVA/submitqueue 全链（**v0.5 用户态身份达成线**）。softpipe 字样 ⇒ 服务/fd 链断（→ 分支 B）。
3. **首帧行**：`gl_test: 1080×2400 drawn in N ms, read back in M ms; error 0x0; … a corner 26 0 0 255 / the middle … / near the red corner …` ——`error 0x0` + 三色角邻近像素命中各自颜色 = **三角形真被 3D 核画出来**（raphael 的 42 ms/25 ms 形态对标）；`coloured ≈26%` = 光栅覆盖几何正确。
4. **上屏行**：`gl_test: the picture is on the panel (0x0), for 8 seconds` ——kHakiosShow 链通（面板可见三色三角，肉眼+控制台双证）。
5. 顺手件：`u2f_test`（镜像里带上）测 GPU 的 uint→float 路径；`gl_test fill` 出帧成本画像。

### 4.4 判定分支（六分支式，照 wave37 格式）

| 分支 | 症状 | 归因域 | 下一刀 |
|---|---|---|---|
| A | renderer=FD725 + error 0x0 + 26% + 面板见三角 | **v0.5 用户态首帧达成** | GL=1（窗口服务器加速）波 |
| B | renderer=softpipe（画成功但软管） | 服务打开链：fd 0x7e 前的 drmOpen/IOServiceOpen 失败 | `HakiosGPU: request … not known`/服务注册行 logdump；查 IOServiceOpen 返回 |
| C | `no OpenGL ES context`（建上下文就败） | dyld/SDK 层（CF/IOKit 框架或 osmesa 符号） | flashboot 体积/缓存核对；u2f_test 对照 |
| D | context 好但 drawn 长挂/`HakiosGPU: … ring is full` | submit 链（fence/环） | `tl: Q` 行 + gpu_log=1 再刷 |
| E | drawn 快但像素错/coverage 严重偏离 | ir3/编译或 GMEM 路径 | IR3_DBG 打印 + `OSMESA_SOFTWARE=1` 对照（软管同画面应正确）|
| F | SSH 不通/会话 600 s 前死 | loader/系统域（非本阶段） | 按 wave25/27 语义回归 |

### 4.5 会话纪律与顺序

设备 = wave38 域；v39 刷写排在 wave38 真机判定退役后（§4.2 排期注记：与 v34 重基线兼容，ramdisk 换入即成）。会话内顺序：SSH HIT →（可选）`cat /dev/logdump 尾` 验内核行 → `gl_test 8 <W> <H>` → 逐行取证 → `gl_test fill` → `u2f_test`。无人值守备选：RC_JOBS 合并文件（`rc.jobs.ssh` + `rc.jobs.gltest` 拼接）出第二版镜像。

---

## 5. 诚实边界与树状态注记

1. **零真机**：一切"能验什么"是计划不是结果；本阶段无一行设备证据（设备禁令遵守）。
2. **Mesa 运行时未验**：构建绿 ≠ 画得对；a7xx_gen1 运行时路径（fd6 每批序列与 GMEM 2 MiB）首次真机会话才算数（§4.4-E 对照刀已备）。
3. **上游转述边界**：redwood "GL=1 smooth/wallpaper drawn"（consulting）与 mk-mesa.sh 内嵌的 a642L 性能注记均为上游文档自述 [转述]；本轮独立复现的是**构建层**，非其真机层。
4. **树状态变化（可复现、有账）**：本轮在 WSL 树新增/重建了 `xnu-deps/build/mesa/`（Mesa 源+构建，git 树外）、`userland/root.apfs`（156b5be1→c2780842，GL=test；旧 pin 在 device-layer payload bins 且可无 GL 重建复现）、`userland/obj/`（gl_test/u2f_test/libhakios.gl/eagl_gen.h）、`fw-gpu/` 未动。`drivers/gpu/` **零字节改动**（含备份链完整性）；loader 未触碰。
5. build.sh 无 ldid 警告三行（battery/keychain/wifipw test 未签名）——上游已知形态（redwood 同样报），与本阶段 GL 物料无关。
6. Mesa 升版评估（25.3.3/26.0.x）、GL=1 窗口服务器加速、air_run 真机探针、Turnip 备胎参数对照——各自独立后续项，不在本阶段。

## 6. 判定表（六分支式，本阶段域内）

| 分支 | 判定 |
|---|---|
| **A 构建管线通 + 产物齐 + 身份在库** | **✓——本阶段实况（§2.2 表 + FD725 串）** |
| B 构建死于宿主环境 | ✗（三件增量已固化进 wave39-scripts/build-mesa.sh）|
| C FD725 不被 25.0.7 认 | ✗（表项精确命中 + 参数面双源一致）|
| D shim 需要新代码 | ✗（零代码 delta，证据链 §3.4；如实结论）|
| E 首帧真机达成 | —（**不在本阶段域**；载体已建，配方与判定行 §4 齐）|
| F 树/设备红线违规 | ✗（零设备、内核只读、树变化全记账）|

**阶段 39 判定：Mesa 用户态接续完成——构建管线实作绿 + 首帧载体建成 + 首帧配方与判定行转入。** 流水 = `wave39-scripts/progress.log`。

## 附录：本轮取证来源

- **WSL 树（构建产物=证据）**：`~/hakios/kernel/xnu-deps/build/mesa/{out,mesa-25.0.7}`、`~/hakios/kernel/userland/{root.apfs,obj,build-w39-gltest.log}`、`~/hakios/kernel/drivers/gpu/{hakios.gpu.cpp,hakios.adreno.c}`（只读）、`~/hakios/kernel/tools/{mk-mesa.sh,mesa/}`、`~/hakios/kernel/fw-gpu/`（8 件 a730）
- **仓内（只读）**：wave37/wave35/f15/f16/consulting 五份必读 + wave36-scripts/make-payload-v25.sh（payload 配方源）+ docs/STATUS.md（判定行格式）
- **网络**：archive.mesa3d.org（mesa-25.0.7.tar.xz，sha 钉 592272df）
- **新增（入库）**：`docs/waves/wave39-mesa-userland.md`、`wave39-scripts/{progress.log,build-mesa.sh}`
