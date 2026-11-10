# 阶段 10 · 2026-11-03 · GIC 重分配器步进修复：内核首次跑进用户态

Date: 2026-11-03. Agent: 阶段 10（全程未碰手机；kernel + loader 双修复 + 全量重编内核 + 重建交付 v5）。
目标：Boot #11 真机内核日志里，阶段 9 的 DT/GIC 地址修复已生效（`found interrupt-controller` /
`gPicBase` / `gTimerBase` 全部打出），但 `gTimerBase` 之后 ~139 µs 仍见
`Unclassified kernel abort (fault_code=0x10)`——找到精确位置，修掉，让下一轮不再出现。

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-grafted-v5.img` | 201,326,592 B (192 MiB) | `6828bc5fe43a7b925f3e763941a53b2e69b4769d95720b15a6d994a3103828b6` |
| Packaging report | `udon-hakios-grafted-v5.report.json` | 1,660 B | `2e4a5755bc234a93336a7ce8e32fc63ea26c1cd0247e06d50f373081ac7ea644` |
| loader.efi (stage-1, +redistributor-stride 属性) | `udon-hakios-loader-v5.efi` | 67,584 B | `66c6b342098a48ea0cdedbc3a2c11d8766dbd20cb5482a08e246083f290058b9` |
| XNUP payload (loader.efi + kernel 条目都换新) | `udon-hakios-payload-v5.bin` | 14,925,960 B | `ce0b6755e68c841bd6c553da24be3a57fd81992f4708d922f430b3d9834462cf` |
| 内核 Mach-O（全量重编，+24 B vs v4） | `hakios-kernel-v5` | 14,841,392 B | `210d01734e7828e8cc353dffffc19efdeb6a13bdf776f57fe375c39134aebf1f` |

自检：`wave5-scripts/verify-udon-hakios.py` **ALL 21 CHECKS PASSED**（§7）。v1/v2/v3/v4 全部原样
（抽验 v4 img/payload/loader、v3 img、BootShim 的 sha256 与 阶段 9 报告逐位一致）。
FD 未重建（sha `8924cb67…` = 阶段 7 FD，Boot #9 验证过的挂点版）。

**一句话结论**：abort 不在 GIC 地址（阶段 9 已修对），而在 **GICR 扫描步进**：内核
`gic_find_redistributor()` 以硬编码 0x20000（一帧 RD+SGI 两页）步进扫 redistributor 区，而
SM8475 的 GIC-700 给每个 PE 一个 **0x40000 的槽**，槽内后半（+0x20000..+0x40000）未分配——
第 2 步读 `0x171A0008`（PE0 槽内的保留垫）→ 互连不解码 → 同步外部中止（FSC 0x10）。
这是 阶段 9 报告预告的残余风险 #1，本轮兑现修复：**内核按 DT 的 `redistributor-stride`
步进（phk110 = 0x40000），loader 给 phk110 的 DT 写入该属性**。QEMU/redwood 无此属性 →
行为逐字节不变（QEMU 冒烟全链通过）。

---

## 1. abort 精确位置（证据链，文件:行号为 v5 修复后的工作区状态；v4 行号在括号里）

### 1.1 位置：`gic_find_redistributor()` 第二次 GICR_TYPER 读，PA = 0x171A0008

- 调用链：`arm_init.c → PE_init_cpu() → pe_init_fiq()（pexpert/arm/pe_fiq.c:177-179）→
  gic_v3_irq_cpu_init()（osfmk/arm64/gic_v3_irq.c:427）→ gic_find_redistributor()（:399）`。
  这是 `gTimerBase` 打印（pe_identify_machine.c:551）之后**第一处会访问 GIC MMIO 的代码**。
  中间的 `pe_arm_init_timer`/`ml_init_timebase`（machine_routines.c:858-870，arm64 只重存缺省
  timebase 函数指针）、`pe_arm_init_debug`/`ml_init_arm_debug_interface`（只存指针 +
  do_debugid 读 ID 寄存器）都不碰 MMIO——阶段 9 已审计，v4 未改。
- `gic_v3_irq_cpu_init` 里先于一切 GIC MMIO 的是系统寄存器 `ICC_SRE_EL1` 读改写（:467），
  随后 :471 `gicr = … = gic_find_redistributor()`。
- 扫描循环（v4 行号 :402-403）`for (frame = gicr_base; frame + 0x20000 <= gicr_base + 0x200000;
  frame += 0x20000) { typer = *(volatile uint64_t *)(frame + 0x8); … }`：
  - 第 1 读 PA **0x17180008** = PE0 的 GICR_TYPER（真寄存器）→ affinity 0x00000000 ≠ 本核
    （cmdline `bootcpu=7`，`core_shift=8` → MPIDR Aff1=7，affinity 0x00000700）→ 不匹配，
    LAST=0（8 个 PE，PE0 非最后）→ 继续。
  - 第 2 读 PA **0x171A0008** = gicr_base+0x20000+8——按本机 live FDT
    （`intel/live-fdt.dtb`: `redistributor-stride = <0x00 0x40000>`，
    `#redistributor-regions = <0x01>`，`reg = <0x17100000 0x10000 0x17180000 0x200000>`），
    PE0 的槽是 [0x17180000, 0x171C0000)，其中 RD 页 [0,0x10000)、SGI 页 [0x10000,0x20000)，
    **[0x20000,0x40000) 未分配**。读它 → taro 互连（NoC）送错误响应 → 数据中止
    FSC=0b010000（`proc_reg.h:1775 FSC_SYNC_EXT_ABORT = 0x10`）→
    `sleh.c:1508 handle_kernel_abort` 非 translation/alignment/parity →
    `sleh.c:1628` 打印 `Unclassified kernel abort (fault_code=0x10)` → 早期 panic 挂死
    （与 Boot #10 同一签名、同一打印点，只是地址从 0x17A60008 换成了 0x171A0008）。
- 时间轴吻合：b11 日志 `gTimerBase` 10.347332 → abort 10.347471（139 µs）——正是
  `PE_init_cpu` 的 GIC 首读窗口（QEMU 同窗口 GIC 打印在 +1.1 ms；真机上一两笔 MMIO 读即中止，
  早于一切后续打印，日志在 abort 行后无任何字节，`intel/m3-boot1/b11-logdump-v4.bin` 同构）。

### 1.2 反证：不是 hyp stage-2 拦 GIC（三个独立证据）

1. **我们自己的 UEFI 固件就在真机上以 0x40000 步进读写 GICR**：udonPkg → PalimaPkg
   （`uefi-udon/Silicon/Qualcomm/PalimaPkg/PalimaPkg.dsc.inc:50-51`）定义
   `PcdGicDistributorBase|0x17100000`、`PcdGicRedistributorsBase|0x17180000`；
   `PalimaPkg/Library/PlatformSecLib/PlatformRegisters.h:10` `GICR_STRIDE_SIZE = 0x40000`；
   `PlatformSec.c:27` `MmioAnd32(GICR_BASE + i*0x40000 + 0x14, ~GIC_WAKER_PROCESSORSLEEP)`
   在 SEC/PlatformInitialize 对每核做 GICR_WAKER 读改写——Boot #8-#11 每次都跑通（UEFI 是
   我们的内核日志的载体）。EL1 直访 GICR RD 页在这台机器上是已验证行为。
2. **设备自己的 Android 内核**在同一 hyp（QHEE）下、同一 EL1 直接驱动 GICD+GICR 全部 8 核
   （live FDT 就是交给它用的）——GICD/GICR 不是 QHEE 的 trap-and-emulate 区域。
3. **ICC_* 系统寄存器路径**同理 Android 已证；且 `CNTP_CTL_EL0` 的物理 timer 陷阱
   （takasugl 在 unixnu-core 也独立撞到并绕开，见 §2）本 fork 已有对应处理
   （`machine_routines.c:2348-2360 _enable_virtual_timer`：非 `APPLE_ARM64_ARCH_FAMILY`
   分支不写 CNTP_CTL_EL0）——本轮 v4→v5 该处无变化，不参与本次 abort。

排除项：GICD_CTLR 首读在扫描之后（gic_v3_irq.c:503，未到达）；GICR_WAKER 在找到帧之后
（:473，未到达）；pexpert 的 gPicBase/gTimerBase 映射本身不产生访问（ml_io_map 只建 PTE）。

## 2. unixnu-core 对照发现（takasugl 的 PHK110/XNU bring-up）

读了 `~/hakios/unixnu-core`（UniXNU 构建仓 + 60 个 xnu-10063.141.1 补丁）与
`~/hakios/unixnu-udon`（udon 设备仓，`docs/BRINGUP-2026-10-25.md`，1211 行）。结论：

1. **他们的内核从不碰 GIC MMIO**：全仓（patches/kits/drivers/package/docs）grep
   `GICR|ICC_|GICD|gic` 零命中（除文档里"ArmCpu 提供 GIC 路径"一句；`drivers/ArmCpu`
   目录是空的，sources 不在这两个 checkout 里）。他们的 UFS 驱动是**轮询**的
   （`drivers/NativeUfs/TransferPoll.h`），bring-up 全程没有可对照的 GIC 初始化代码可抄。
   他们绕开的路线（UEFI 里做硬件、内核轮询、fabricated ADT 假装 iPad）与本项目的
   "内核自己驱动 GIC" 是不同架构，不适用。
2. **同款陷阱的独立印证**：`patches/xnu/zzzzzzz-skip-physical-timer.patch`——他们删掉了
   `_enable_virtual_timer` 里的 `CNTP_CTL_EL0` 写，注释 "The physical timer is not
   accessible at EL1 on this non-Apple platform"。我们 fork 的同函数已有同样的 `#else` 分支，
   措辞一致（"e.g. Qualcomm's"）——两个项目在同一台机器上各自撞到同一个 EL1 物理计时器陷阱。
3. **同类外部中止的先例**：BRINGUP 文档第 8 行："SMMU programming is deliberately skipped
   on SM8475 because it caused an external abort"——SM8475 上"未经 QHEE/固件配置就访问"的
   MMIO → 同步外部中止，是他们已记录的设备行为家族，与 §1.1 的机制判断一致。
4. **boot 链不同**：UniXNU 走 ABL → boot_b（Mu-Silicium UEFI + DarwinBoot）→ FAT payload →
   XNU；我们走 fastboot boot → BootShim/FD（UEFI）→ loader.efi → XNU。两者最终都在
   EL1、QHEE 在上——EL 姿态相同，进一步排除"我们比他们少了 hyp 逃逸步骤"的假设。

所以本轮修复没有可照抄的 unixnu 代码；采取的是**设备自身证据**（live FDT 的
`redistributor-stride` + 我们固件 PlatformSecLib 的同款步进）——两者数值一致（0x40000），
这本身就是双源交叉验证。

## 3. 修复（diff 摘要；qemu/redwood 平台行为逐字节不变）

### 3.1 内核 `xnu-src/xnu-8796.121.2/osfmk/arm64/gic_v3_irq.c`（+16/-2）

1. :85 新增 `static vm_size_t gicr_stride;`——PE 帧间距，缺省 0 = 0x20000（现状）。
2. :446-453 `gic_v3_irq_cpu_init` 的 DT 块在读完 `reg` 后追加读 `redistributor-stride`
   （接受 4 或 8 字节；< 0x20000 视为无意义忽略，保持缺省）。
3. :410 `vm_size_t stride = gicr_stride != 0 ? gicr_stride : GICR_FRAME_SIZE;`，
   :412 扫描循环以 `stride` 步进与判界（原式 `frame + GICR_FRAME_SIZE <= …` 在缺省时
   逐字符等价）。RD/SGI 页内偏移（`GICR_SGI_BASE` 等）不动——帧内部两页布局是架构规定的。
4. 文件头注释（:26-27）补 `redistributor-stride` 语义。

### 3.2 loader `xnuloader/loader.c`（+21/-7，叠加在 阶段 7b staged + 阶段 8/9 unstaged 之上）

1. :582 `struct platform` 新增 `uint64_t gic_redist_stride;`（0 → 不写属性 = 旧行为）。
2. :640 `platform_phk110` 增加 `.gic_redist_stride = 0x40000,`，注释更新为 Boot #10/#11
   双 abort 语义与 PalimaPkg PlatformSecLib 步进出处。
3. :3504-3508 DT 构造：gic 节点在 `reg` 之后按条件追加
   `dt_prop("redistributor-stride", u64 0x40000)`。qemu-virt/redwood 平台字段为 0 →
   DT 字节级与 v4 相同（与 阶段 9 `gic_redist_size` 同款条件化模式）。

副作用面：`redistributor-stride` 属性在内核里只有 `gic_v3_irq_cpu_init` 一个读者（全仓 grep
只有本文件命中）；pexpert 不读该属性。QEMU 冒烟证明缺省路径无回归（§6）。

## 4. unixnu-core 以外，本轮新核对的其它证据

- `intel/live-fdt.dtb`（dtc 反编译）：`interrupt-controller@17100000` 节点如 §1.1 所引
  ——stride 0x40000、regions 1、reg 0x200000，8 PE 每槽 0x40000，槽内后半无资源。
- Boot #11 存档 `intel/m3-boot1/b11-kernel-log.txt` 全文复核：abort 行后无字节，
  时间戳窗口与 GIC 首读吻合。

## 5. 重建链（全 WSL；FD 未重建，复用 阶段 7 FD）

```
a. kernel   cd ~/hakios/kernel && ./tools/make-kernel.sh -j8
            （增量：仅 gic_v3_irq.o 重编 + 重链；exit 2 为已知 kext symbol-set 检查，
              make-kernel 判定通过）→ hakios-kernel 14,841,392 B，sha 210d0173…
b. loader   cp identity.h 备份位（qemu-open 先会临时覆盖，见 §6）→
            cd ~/hakios/kernel && PAYLOAD_BASE=0xF4000000 xnuloader/build.sh
            → loader.efi 67,584 B（v4 66,560，+1024），sha 66c6b342…
            strings 复核：phk110 / redistributor-stride / interrupt-controller /
            cpu-debug-interface / "KERNEL LOG"（阶段 7b）/ "usb: try"（阶段 8）全在。
c. XNUP v5  python3 xnuloader/mkpayload.py -o payload-v5.bin --no-version \
              loader.efi=<b> kernel=hakios-kernel \
              ramdisk=<v4 提取> cmdline=<v4 提取> kernel.ver=<v4 提取>
            （提取用 wave10-scripts/extract-entries.py；五条目 sha 断言：
              ramdisk b23d1415… / cmdline a620615e… / kernel.ver afd473f5… 与 v4 逐字节相等，
              cmp 三连 PASS；loader.efi/kernel == 新构建）
            → 14,925,960 B，sha ce0b6755…
d. 打包     python3 -I wave4-scripts/package-udon-boot.py --fd ~/hakios/uefi-udon/Build/
            udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd（sha 8924cb67… 核对一致）--shim
            device-layer/udon-hakios-BootShim.bin --stock device-layer/stock-boot-a.img
            --payload payload-v5.bin --out device-layer/udon-hakios-grafted-v5.img
            --report device-layer/udon-hakios-grafted-v5.report.json
            → 192 MiB；kernel_gzip 6,764,069（v4 6,763,786；loader+kernel 条目变更致 gzip
              窗口重排，已知现象）；stock OEM vbmeta（2,432 B，25314ab1…）原样在位。
```

## 6. QEMU 冒烟（kernel 文件是 qemu/redwood 共享路径 → 全链跑，M1 验收法）

`make qemu-open` 全链（kernel → loader-open → hello → mkpayload → run）。两处环境适配，
**未改任何 qemu/redwood 语义**：

- 本机 Fedora 44 的 qemu-system-aarch64 升到 10.2.2，要求 64 MB pflash；run.sh 自动找到的
  `QEMU_EFI.fd` 还是 3 MB 旧格式 → 按脚本设计的开关用环境变量
  `QEMU_EFI=/usr/share/edk2/aarch64/QEMU_EFI-pflash.raw
  QEMU_VARS=/usr/share/edk2/aarch64/vars-template-pflash.raw ./run.sh 300`。
  （第一次 `make qemu-open` 因此在 run 一步失败，重跑 run.sh 本身即全链验收；kernel/loader/
  hello/payload 四个构建步都在同一次 make 里完成。）
- `make loader-open` 按 Makefile 定义会重建 placeholder `identity.h`/`loader.efi`——已先备份、
  事后恢复 identity.h（sha 8f3a04e2… 与接手时逐位一致）并以真 identity 重建 loader（§5b）。

验收结果（`~/hakios/kernel/logs/qemu-open-w10.log`）：内核带新 gic_v3_irq.c 跑通——
`gic: v3, distributor 0xfffffff10fa84000, cpu 0's redistributor 0xfffffff10fa94000,
virtual timer on PPI 27`（qemu 无 stride 属性 → 走缺省 0x20000 扫描，找到 cpu0 帧并初始化
全部 8 步内寄存器）→ 8 驱动（.config 集）→ 用户态 `Hello from user space on Darwin! I am
process 1…` → hello 退出 → `initproc failed to start`（qemu-open 验收的标准终点，hello
ramdisk 无 init 可再跑）→ stackshot → `== END OF LOG ==`。与 阶段 9 报告引用的验收日志
（`device-layer/qemu-open.log`，3979 行，原 `logs/qemu-open.log` 的归档副本）同构推进。
注：`make` 失败尝试曾把 `~/hakios/kernel/logs/qemu-open.log` 截断（134 B），已从
device-layer 归档副本逐字节还原（3979 行，3693 行 gic 行等与 阶段 9 文档引用一致）；
新验收日志另存 `logs/qemu-open-w10.log`。old 参考日志与新日志仅内核时间戳/地址随机化差异。

## 7. 自检（verify-udon-hakios.py）

`python3 -I wave5-scripts/verify-udon-hakios.py device-layer/udon-hakios-grafted-v5.img
device-layer/stock-boot-a.img device-layer/udon-hakios-BootShim.bin <阶段 7 FD>
payload-v5.bin` → **ALL 21 CHECKS PASSED**（header diff 仅 bytes 8..14 / gzip round-trip
19,120,512 B / shim 头 0xA7100000 + shim+fd=0x4000f0 / FD _FVH@shim+0x28 / XNUP 逐字节 /
entries {loader.efi 67,584, kernel 14,841,392, ramdisk 16,528, cmdline 248, kernel.ver 48} /
cmdline 含 serial=0+loader_return_after=20+cpus=8+bootcpu=7 / AVBf footer / stock vbmeta
逐字节 / 192 MiB）。另有 v4↔v5 未改动条目 cmp 断言三连 PASS（§5c）。

## 8. Git 状态（kernel 仓与 xnu-src 仓，均未 commit、未 identity、不 commit）

- kernel 仓 `git status --short` = `M mkxnuimg.py / M tools/provenance.allow /
  M xnuloader/build.sh / MM xnuloader/loader.c`——与 阶段 9 接手时同构叠加：
  staged（阶段 7b）原样未动；loader.c unstaged 现含 阶段 8 + 阶段 9 DT 修复 + 本 wave
  （:582 / :640 / :3504-3508 三个 hunk，`git diff xnuloader/loader.c` 中 阶段 8 块之外
  即可辨认）。**未执行任何 git reset/checkout/stash/clean**。
- xnu-src 仓：`gic_v3_irq.c` 为 apply.sh 覆盖产生的未跟踪文件（`??`），本 wave 的改动
  留在树中（该仓无 identity，不 commit）。

## 9. 下一轮（Boot #12）预期内核日志

v5 的 `/arm-io/gic` reg 同 v4（{0x16C00000, 0x10000, 0x16D80000, 0x200000}），新增属性
`redistributor-stride = 0x40000`（8 字节 u64）。内核扫描按 0x40000 步进：读
0x17180008/0x171C0008/…/0x17340008 共 ≤8 次，全在 PE0-7 的 RD 页内（GIC-700 已解码区域，
固件 PlatformSecLib 同款步进）。预期（对照 qemu-open-w10.log 的推进顺序）：

```
pe_arm_init_interrupts: args: 0xfffffff…
pe_arm_map_interrupt_controller: soc_phys:  0x400000
pe_arm_map_interrupt_controller: found interrupt-controller
pe_arm_map_interrupt_controller: gPicBase: 0xfffffff1…
pe_arm_map_interrupt_controller: found timer
pe_arm_map_interrupt_controller: gTimerBase: 0xfffffff1…
（不再有 Unclassified kernel abort —— 第 2 步读的 0x171A0008 已从扫描中消失）
gic: v3, distributor 0xfffffff1…, cpu 0's redistributor 0xfffffff1…, virtual timer on PPI 27
Darwin Kernel Version 22.5.0: …
…（驱动推进、用户态……）
```

- 若 `gic: v3, …` 出现 → GIC 初始化全通过，下一瓶颈才轮到 8 核 PSCI 启动（cpus=8）与
  virtio/ufs 路径。
- 若仍见 `Unclassified kernel abort (fault_code=0x10)`（位置应在 gTimerBase 后同窗口）：
  剩余候选只有 QHEE 对 **GICR 本体**的 trap（§1.2 三证皆反对此情形）；验证手段：把
  cmdline 改 `cpus=1`（只扫到 PE0 帧 0x17180008，Android/固件双重已证地址）交叉定位。
- 若 `panic("gic: no redistributor for MPIDR …")`：说明 TYPER affinity 编码与本核
  MPIDR 不匹配（affinity 打包方向），那是下一个（数据可判定的）wave 的输入，不再是 abort。

## 10. 回退方式

- 只回退镜像：Windows `device-layer/` 重刷 `udon-hakios-grafted-v4.img`
  （4ea69530…，Boot #11 实测镜像）。v1-v4 与 USB-mode 变体全部在位未动（§0 抽验）。
- 代码层：kernel 侧 `gic_v3_irq.c` 是未跟踪文件，`git diff` 不可用——改动集中在
  :85 / :410-412 / :446-453 / :26-27 四块，可按块还原为 v4 行为（stride 恒 0）；
  loader 侧 unstaged 的三个 hunk（:582 / :640 / :3504-3508）可按 hunk 丢弃，
  阶段 7b（staged）与 阶段 8/阶段 9 块不受影响。
- kernel/ramdisk/cmdline/kernel.ver 语义：v5 的 ramdisk/cmdline/kernel.ver 与 v4 逐字节
  相同，kernel 条目仅含 gic_v3_irq.c 增量（+24 B）——重刷 v4 即回到 Boot #11 行为。
