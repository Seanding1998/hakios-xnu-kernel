# Wave 11 — 常驻改造：XNU 在 PHK110 真机 60 秒常驻 + 8 核全上线（`udon-hakios-grafted-v6.img`，Boot #13）

Date: 2026-11-03. Agent: Wave 11（项目首个全循环波次：分析 → 构建 v6 → 自己刷写 → 自己取证）。
目标：Boot #12 已达 v0.1（内核进用户态后 hello 退出 → panic `initproc failed to start` → 干净返回，
CORE 4-6 PC=0）。本轮让 XNU **常驻**运行：给 process 1 换一个**不退出**的 stub launchd、把取证窗口
`loader_return_after` 从 20 s 加到 60 s，并核验 8 核（物理 0x700/600/500/400/300/200/100）全部上线。

## Result summary

**一句话结论**：✅✅✅ 全达成，Boot #13 是项目第一次**无 panic 的完整内核会话**——驻留 stub 生效
（心跳 t=10/20/30/40/50 s，全程零 panic 零 stackshot），60 s 定时器触发 `--- loader_return_after
expired ---` 干净返回落盘，**7 个 AP 全部上线**（"GenericARMPE: the slower cores started too:
7 processors running"）= 8 物理核全部被内核接管。Boot #12 的 CORE 4-6 PC=0 之谜同时破案：
**不是 PSCI 失败，是内核设计使然**——慢核默认 `small_cores_after=28` 秒才唤醒（GenericARMPE.cpp
为锁屏时序做的调优），b12 的 panic 发生在 t≈10.5 s，根本没等到 28 s。

| Artifact | Path（仓库根相对；Windows 侧只新增） | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image（本波交付）** | `device-layer/udon-hakios-grafted-v6.img` | 201,326,592 B (192 MiB) | `c69c64c463b98fa123cd9f30e2968f7eac331b033ab5a0ba9208105d7628550e` |
| Packaging report | `device-layer/udon-hakios-grafted-v6.report.json` | 1,660 B | `20ae489df4c26c87d3d7bf8f267506e7097b9ceb378260292641923d4643eedc` |
| XNUP payload v6（仅 ramdisk+cmdline 与 v5 不同） | `device-layer/udon-hakios-payload-v6.bin` | 14,925,960 B | `c329dcfd706a1d18cac31fcbc8d194cc261cee5f32bf0b59c8e570eabde650bf` |
| **新 ramdisk = 驻留 stub launchd** | `device-layer/udon-hakios-ramdisk-v6.bin` | 16,528 B | `4f72da6165a81a1ec6adf616cba169072cbdeb6fc613812bbd73fb334393821a` |
| stub 源码（构建树副本同内容） | `wave11-scripts/resident.c`（= WSL `~/hakios/kernel/userland/src/resident.c`） | 5,247 B | `22e8f5d555ef8e2e43d29c1efa8354543f75a2c189f6007753ef4770e22c3f24` |
| repack 脚本 | `wave11-scripts/repack-payload-v6.py` | — | `27f1580946e02e9c58e426be48fb76497f33b8d846c59fa1ad9e627f4328854b` |
| 自检脚本（v5 版 21 项形状 + 条目级 cmp） | `wave11-scripts/verify-udon-hakios-v6.py` | — | `b2f5b5bf4ecae8e43c2dfa4dbf1454832a170d3e241ea6299f1f2d394831d320` |
| Boot #13 全量 logdump（65,536 B 分区原始） | `logdump-v6.bin`（仓库根，与 v3/v4/v5 同列） | 65,536 B | `13d2844141cb969d1a336e12bb73ee8006f256e02b33e0f697821e80c4b1ea04` |
| **Boot #13 内核日志（提取段）** | `intel/m3-boot1/b13-kernel-log.txt` | 19,542 B | `67a7d34fca8f986ecec43564b764f9046a014d094cecf2e9ca7e84034802a357` |

未动的构件（逐字节校验）：loader.efi（`66c6b342…`，v5 同）、kernel（`210d0173…`，v5 同，**未重编内核**）、
kernel.ver（`afd473f5…`，v5 同）、BootShim（`108ce972…`）、SILICIUM_UEFI.fd（Build 路径 sha
`8924cb67…`，禁重建条款遵守）、stock-boot-a.img。v1–v5 镜像全部原样（v5 基线本轮复跑自检 21/21 通过）。

---

## 1. 勘察结论（改哪里、为什么）

### 1.1 panic 机制（b12 遗留的最后一环）

- ramdisk 不是文件系统镜像——**就是 hello 那一个静态 arm64 Mach-O**（16,528 B）。内核 mockfs 把
  它呈现为 `/sbin/launchd`（`userland/src/hello.c` 头注释原文："the kernel's mockfs presents the
  ramdisk (this very file) as /sbin/launchd, so this runs as process 1"）；b13 日志实证：
  `load_init_program: attempting to load /sbin/launchd`。
- b12 的 panic 链：hello 打印完即 `SYS_exit` → bsd/kern/kern_exit.c:1812 路径：process 1（initproc）
  带着退出 → `initproc_spawned == FALSE` → prefix 取 `"initproc failed to start"` →
  `panic("initproc failed to start -- no exit reason available -- (signal 0, exit status 0)")`。
  b12 的 "Panicked task … pid 1: launchd" 佐证（进程名是 mockfs 给的 launchd）。
- **结论：任何 process 1 的退出都是 panic。修复 = process 1 永不退出**（不需要真的 init/launchd 双进程）。

### 1.2 60 s 窗口机制（loader_return_after）

内核自带（**无需动 loader.c，本轮 loader.c 零改动**）：
`osfmk/arm64/loader_return.c` 的 `loader_return_timer_init()`（STARTUP EARLY_BOOT 挂 thread_call，
`clock_interval_to_deadline(seconds)` 延迟触发）→ `loader_return_timer()` 打印
`--- loader_return_after expired ---` → 停 GPU/WiFi/ADSP/MPSS → `loader_return()` 把日志交回 loader
落盘。b13 的横幅与干净返回实证该路径按 60 s 正确触发。

### 1.3 b12 CORE 4-6 PC=0 之谜（先破案，后取证验证）

`iokit/Kernel/GenericARMPE.cpp`（:259-290）：慢核（DT `l2_access_penalty != 0`，即物理
0x300/0x200/0x100 → logical 4/5/6）由独立的 thread_call **默认 28 秒后**才 `run()`（boot-arg
`small_cores_after=S` 可调，0 = 立即）。注释给了调优依据（全 7 核一起起会让锁屏晚 1.5 s）。
b12 panic 在 t≈10.47 s < 28 s → 慢核还没被唤醒，PC=0。**预言**：60 s 窗口内它们必然在 t≈38 s 上线
——b13 实证命中（见 §4）。

## 2. 驻留 stub（实现细节）

- **路径/格式**：与 hello 完全同构的裸 syscall 静态 arm64 Mach-O（无 libc 无 dyld；入口 `start` →
  符号 `_start`）。内核 mockfs 把 ramdisk 原样呈现为 `/sbin/launchd`，所以"新 ramdisk = 新 process 1"。
- **改动**（`wave11-scripts/resident.c`，对 hello.c 做减法+加法）：
  - 删 `SYS_exit` 与 `hello_wait` 解析；初始输出全部保留（Hello 行 / pid/uid/console fd / kernel.ver /
    soc sysctl 四连——这些都是 b12 实证过的 syscall 面）。
  - 加一行驻留横幅 `launchd stub resident (wave11): not exiting, sleeping forever`。
  - 无限循环：每秒 `select(0,0,0,0,{1,0})` 睡 1 s；每 5 s 打 thermal 两行；每 10 s 打心跳
    `launchd stub alive: t=N s`。**零 MMIO**（只 write /dev/console、sysctl 读、select 睡眠）。
- **工具链**（userland/build.sh:24-25 原样）：`xnu-clang -arch arm64 -Os -static -nostdlib
  -ffreestanding -fno-stack-protector -fno-builtin -Wall -Wextra -Wl,-e,_start
  -Wl,-pagezero_size,0x100000000`（xnu-clang = `~/hakios/kernel/xnu-deps/host/bin/xnu-clang`）。
- **确定性验证**：先重编 hello.c → sha `b23d1415…` 与 v5 ramdisk 逐位一致 → 工具链确定性证明成立 →
  再编 resident.c → 16,528 B（与 hello 同尺寸纯属布局巧合），sha `4f72da61…`。
- **构建树叠加**：源码复制为 WSL `~/hakios/kernel/userland/src/resident.c`（新增文件，不改 build.sh，
  不碰任何既有文件）。

## 3. cmdline 与 payload v6 组装

- **cmdline**：v5 条目（248 B 含结尾 NUL）仅做 `loader_return_after=20` → `loader_return_after=60`
  等长替换，其余逐字节不动：
  `serial=0 loader_return_after=60 cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws`
- **payload**：`wave11-scripts/repack-payload-v6.py` 解析 v5 XNUP（magic `0x50554E58`，条目
  `<16sII name,size,rsv>+data pad16`，空名终止），**保序**重建：`loader.efi / kernel / ramdisk(新) /
  cmdline(新) / kernel.ver`，脚本内置断言：条目集与顺序一致、未动条目逐字节相等、只有 ramdisk+cmdline
  不同、读回遍历与意图一致。
- **打包**：`wave4-scripts/package-udon-boot.py` 原样（--fd Build 路径 SILICIUM_UEFI.fd sha `8924cb67…`
  --shim `udon-hakios-BootShim.bin` --stock `stock-boot-a.img` --payload v6）→
  grafted-v6.img + report.json。

## 4. 自检（verify）

- `wave11-scripts/verify-udon-hakios-v6.py`（wave5 脚本的 21 项形状断言 + 本波条目级断言，cmdline
  期望改为 `loader_return_after=60` 且显式拒绝 `=20`）：**ALL 27 CHECKS PASSED**：
  - 形状 21 项：ANDROID! magic / header diff 仅 kernel_size,ramdisk_size / 页对齐零填充 / gzip
    round-trip == shim+FD+payload(+pad) / shim 头 (text_offset 0xA7100000, image_size, ARMd) /
    FD `_FVH` 且逐字节等于源 / XNUP magic/Size/容器逐字节 / 条目集 {loader.efi, kernel, ramdisk,
    cmdline, kernel.ver} / cmdline=60 / graft footer+vbmeta+零填充+192 MiB。
  - 条目级 6 项：ramdisk == `udon-hakios-ramdisk-v6.bin`；ramdisk ≠ v5 hello；loader.efi / kernel /
    kernel.ver 与 v5 **逐字节相等**；cmdline 与 v5 仅 loader_return_after 一处不同。
- v5 基线复跑：`wave5-scripts/verify-udon-hakios.py` 对 v5 镜像 **ALL 21 CHECKS PASSED**
  （final sha `6828bc5f…`）——v5 完好可回退。

## 5. 刷写全记录（用户一揽子授权，boot_b 循环）

| 步骤 | 时间 | 命令/结果 |
| --- | --- | --- |
| 确认安卓在线 | ~17:50 | `adb devices` → `SERIAL_REDACTED device`，`getprop sys.boot_completed` 后期=1 |
| 进 bootloader | ~17:50 | `adb reboot bootloader`，sleep 8 |
| USB 枚举 | | `usbipd list` → `2-2  18d1:d00d  Android  Shared (forced)` |
| attach WSL | | `usbipd attach --wsl --busid 2-2`（每次重枚举必做） |
| 鉴别应答方 | | WSL `timeout 15 fastboot getvar product` → `product: taro` ✓（ABL fastboot） |
| 刷前校验 | | WSL `sha256sum` v6 img → `c69c64c4…`（与打包报告一致） |
| **刷写** | ~17:52 | `fastboot flash boot_b /mnt/c/.../udon-hakios-grafted-v6.img` → Sending OKAY 4.890s / Writing OKAY 0.585s |
| 激活+重启 | ~17:52 | `fastboot set_active b` OKAY 0.163s → `fastboot reboot` OKAY |

启动链全自动（无菜单），与 v5 相同。

## 6. 取证全记录与 8 核结论

### 6.1 回安卓轮询（预期行为变化兑现）

- 17:52:28 起每 20 s 轮询 `adb devices`，**前 5 分钟无 adb 也无 18d1:d00d**（USB 全程未枚举 = 手机在
  boot_b 循环里：每轮 60 s 内核常驻 + 返回 + 复位，ABL 引导重试计数耗尽才兜底）。
- **18:00:12 adb 回来**（`SERIAL_REDACTED device`）——从 reboot 起约 **8 分钟**，对比 b11/12 的 ~20-80 s：
  常驻生效后单轮时长 ×3，循环总时长 ×6+，**正是"常驻生效"的旁证**（任务书预期兑现：5 分钟未回属预期）。
- 回安卓后 `getprop sys.boot_completed` = 1（slot a 安卓完整起来）。

### 6.2 logdump 提取

`adb shell su -c "dd if=/dev/block/by-name/logdump of=/data/local/tmp/logdump-v6.bin bs=4096 count=16"`
→ `MSYS_NO_PATHCONV=1 adb pull`（注意：Git Bash 下 pull 目标必须用 Windows 路径形式，`/c/...` 会被
adb.exe 拒绝）→ `logdump-v6.bin` 65,536 B → python 提取 `== KERNEL LOG ==` 段 raw 19,239 B（解码替换字符后落盘 19,542 B）→
`intel/m3-boot1/b13-kernel-log.txt`（以 `== END OF LOG ==` 干净收尾）。

### 6.3 Boot #13 内核日志要点（对照 b12）

| 证据 | b13 内容 |
| --- | --- |
| 驻留横幅 | `launchd stub resident (wave11): not exiting, sleeping forever` |
| 心跳 | `launchd stub alive: t=10s / 20s / 30s / 40s / 50s`（60 s 心跳未及打印——定时器先到） |
| 每 5 s thermal | `kern.hakios.thermal_max_mc=-273000`、`kern.hakios.thermal_hottest=`（传感器枚举仍空，与 b12 相同，非本轮回归） |
| **定时返回** | `--- loader_return_after expired ---`（60 s 整；之前最后一行内核周期内存报表 t=60.369 s，free 6071 MB） |
| **panic** | **无**（全日志 14 处 "panic" 字样全是 `panic_trace` 调试使能打印；无 stackshot、无 `initproc failed`——b12 的两样都没有了） |
| 内核日志尺寸 | 19,542 B vs b12 26,846 B（差值 = panic dump + stackshot 不存在了） |

### 6.4 8 核上线证据（本波核心交付）

| Logical | 物理 MPIDR | 上线时刻 | 日志行 |
| --- | --- | --- | --- |
| cpu 0 | 0x700（bootcpu=7）| t=0 | （boot CPU，gic v3 横幅 "cpu 0's redistributor"）|
| cpu 1 | 0x600 | **10.375 s** | `arm_cpu_init(): cpu 1 online` |
| cpu 2 | 0x500 | **10.376 s** | `arm_cpu_init(): cpu 2 online` |
| cpu 3 | 0x400 | **10.378 s** | `arm_cpu_init(): cpu 3 online` + `GenericARMPE: 4 of 7 processors are running` |
| cpu 4 | 0x300（慢）| **38.380 s** | `arm_cpu_init(): cpu 4 online` |
| cpu 5 | 0x200（慢）| **38.382 s** | `arm_cpu_init(): cpu 5 online` |
| cpu 6 | 0x100（慢）| **38.383 s** | `arm_cpu_init(): cpu 6 online` + `GenericARMPE: the slower cores started too: 7 processors running` |

- 大核 1-3 在 t≈10.37-10.38 s 各 ~1 ms 依次上线（与 b12 相同）；慢核 4-6 在 t≈38.38 s 成批上线。
- **PSCI CPU_ON 无一失败**：日志无任何 `psci: cpu … was not started` / `has not joined` / exception 行。
- **8/8 物理核被内核接管 = 本波 8 核验证达成**；每核 GICR redistributor 打印 + panic dump 时代
  （CORE 0-6 PC 全非零）的条件也已具备——本轮无 panic，故以 `arm_cpu_init(): online` 行 + "7
  processors running" 为准。

### 6.5 屏显确认与已知噪音（用户现场目击，Boot #13 引导顶部）

用户在 v6 引导现场拍了屏：cmdline 可见 `loader_return_after=60`（= v6 上机生效的屏证）、loader
输出完整（display 1240x2772 at B8000000 / platform phk110 / payload 条目 / jumping to 0x8434194a8 /
log: 4096 bytes written to logdump）、内核已跳转；60 s 内核持续输出不复位——肉眼判据达成。
引导顶部两行报错定性（**已知良性噪音**，历轮均在）：

```
ConvertPages: failed to find range A1000000 - A196BFFF
Loading driver at 0x000FA5EF000 EntryPoint=0x000FA5F1140
```

- 第一行 = EDK2 DXE `ConvertPages`（Page.c:688）在未登记缝隙带（A1000000-A196BFFF）找不到内存；
  Boot #7 起每轮都有，良性、不影响后续 DXE 调度（照片中其后照常 `Loading driver`）。STATUS.md
  "关键地址速查"原记上界 **A196AFFF**（Boot #8 时代），本轮屏显 **A196BFFF**——同一族噪音、边界漂移
  一页，属 DXE 分配次序差异，记录备查。
- 第二行 = DXE 调度 verbose（加载某 DXE 驱动与其入口点），正常输出。

### 6.6 慢核 28 s 延迟定性（任务书"分析原因"课题，已闭环）

非缺陷、非 PSCI 策略问题：`GenericARMPE.cpp` 有意为之（`small_cores_after=28`，DT 慢核属性
`l2_access_penalty != 0` 触发），为锁屏时序调优（注释：全 7 核同起锁屏晚 1.5 s）。**下一轮若要
8 核尽早上线（如为取证/性能），在 payload cmdline 追加 `small_cores_after=0` 即可**（0 = 立即同起，
不动内核）。b12 的 "CORE 4-6 PC=0" 由此定性：panic 早于 28 s，与唤醒机制无关。

## 7. 下一轮预期

1. **v0.2「第一缕光」**（NT37705 原生面板）：常驻 60 s 窗口正是显示调试需要的用户态稳定期；建议下一
   镜像把 `loader_return_after` 提到 300（loader_return.c 的 1 MB ring 设计支持长会话日志）。
2. **取证节奏**：若仍走 ABL 兜底，每轮 ~75-80 s、回安卓 ~6-9 分钟属正常；如需快速回安卓可在 kernel
   运行期不依赖兜底（先 `fastboot reboot` 或等 ABL 重试计数）。
3. **可选微试验**（cmdline-only，零构建）：`small_cores_after=0`（8 核同起）与 `return_cpu=N`
   （指定核做定时返回）均为现成 boot-arg。
4. usbmode 驻留路径（Wave8 修复已在 v5/v6 内）仍未真机验证，免刷写取证通道值得排队。

## 8. 回退方式

- **重刷 v5**（v5 镜像本轮复检 21/21、sha `6828bc5f…` 未动）：手机进安卓 `adb reboot bootloader` →
  `usbipd attach --wsl --busid <X>`（18d1:d00d）→ WSL root
  `fastboot flash boot_b /mnt/c/.../device-layer/udon-hakios-grafted-v5.img` →
  `fastboot set_active b` → `fastboot reboot`。b12 行为（20 s 循环 + panic 返回）即恢复。
- 兜底红线未动：slot a 原厂安卓未刷过；`backups-slotb/` 原厂备份可用 `fastboot set_active a` 回
  日常系统。

## 9. 本波自检表

| # | 项 | 结果 |
| --- | --- | --- |
| 1 | 工具链确定性（重编 hello == v5 ramdisk 逐位）| ✅ b23d1415… |
| 2 | stub 编译（静态 arm64 Mach-O，16,528 B）| ✅ 4f72da61… |
| 3 | payload v6 保序 + 仅 ramdisk/cmdline 差异断言 | ✅ repack 内置 |
| 4 | v6 打包 report.json 读回断言 | ✅ package 脚本内置 |
| 5 | v6 独立自检（21 项形状 + 6 项条目级） | ✅ ALL 27 CHECKS PASSED |
| 6 | v5 基线复检 | ✅ ALL 21 CHECKS PASSED |
| 7 | 刷前 sha256 校验 | ✅ c69c64c4… |
| 8 | fastboot product 鉴别 | ✅ taro |
| 9 | Boot #13 无 panic、60 s 定时返回 | ✅ banner + END OF LOG |
| 10 | 8/8 核上线 | ✅ §6.4 表 |
| 11 | 红线（只 boot_b / 禁重建 FD / 只新增） | ✅ |
