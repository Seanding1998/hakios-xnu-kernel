# Wave 9 — 中断控制器根因修复（`udon-hakios-grafted-v4.img`）

Date: 2026-11-03. Agent: Wave 9（全程未碰手机；loader.c 单点修复 + 重建交付 v4）。
目标：Boot #10 真机内核日志里 `pe_arm_map_interrupt_controller: failed to find the
interrupt-controller.` → `pe_arm_init_debug: failed to find cpu-debug-interface` →
`Unclassified kernel abort (fault_code=0x10)` 三连，找到根因并让下一轮不再出现。

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-grafted-v4.img` | 201,326,592 B (192 MiB) | `4ea69530cdf92dbf77b34ba9ce44de858765b961c982dd42b52e2997f62e2695` |
| Packaging report | `udon-hakios-grafted-v4.report.json` | — | `8a580d095a4a3e2bb5158ac63705d4bdaaf61e2dab15061597e2a070a2cb0433` |
| loader.efi (stage-1, GIC 地址修复) | `udon-hakios-loader-v4.efi` | 66,560 B | `5223ba3762a4b5d769128dfedb8a8d02f9a9f4706f967965b6382eac97825459` |
| XNUP payload (仅 loader.efi 条目换新) | `udon-hakios-payload-v4.bin` | 14,924,920 B | `29e465d636f288975612f114a18091cff795732d17f46ab5166b80464d2b7c72` |

自检：`wave5-scripts/verify-udon-hakios.py` **21/21 PASS**（§5）。v1/v2/v3 文件零触碰。

**一句话结论**：abort 的根因不是 pexpert 那两行 fail（它们在 QEMU 也打印、无害），而是
`platform_phk110` 抄了 **redwood（SM8350）的 GIC 地址 0x17A00000/0x17A60000**，而 SM8475
(taro) 的 GIC 实际在 **0x17100000 / 0x17180000（GICR 区 0x200000，stride 0x40000）**——
这是设备自己的 live FDT（Wave 2 抓的 `intel/live-fdt.dtb`，`intc@17100000`）的实证。内核
第一次读 redistributor（0x17A60000，taro 上不解码的地址）→ 同步外部中止（FSC 0x10）→
早期 panic 挂死。任务书里"Cape FDT 实证 0x17A00000"是把别的 SoC 的树当成了本机的。

---

## 1. 根因链（带 文件:行号；行号为修复前工作区状态）

### 1.1 事实一：那两行 fail 是死代码路径，且 QEMU 也打印

- QEMU 全链验收日志 `~/hakios/kernel/logs/qemu-open.log:3689-3692`：
  `pe_arm_init_interrupts → soc_phys: 0x8000000 → failed to find the interrupt-controller.`
  → `failed to find cpu-debug-interface` → **紧接着 6.769247 `gic: v3, distributor …`
  内核正常跑完 25 驱动 + 用户态 hello**。两行 fail 在能跑通的 QEMU 上同样存在。
- 为什么无害：这 fork 的中断系统不靠 pexpert 那条 Apple 路径。
  `pexpert/arm/pe_init.c:427` 调 `pe_arm_init_interrupts(args)` 且**返回值被丢弃**；
  pexpert 失败后，真正的 GIC 初始化走 fork 自己的驱动
  `osfmk/arm64/gic_v3_irq.c:417 gic_v3_irq_cpu_init()`（由 `PE_init_cpu → pe_init_fiq`，
  `pexpert/arm/pe_fiq.c:172-181`，`GENERIC_GIC_V3_IRQ` 定义于
  `pexpert/pexpert/arm64/BCM2837.h:14`，即本内核 machine config 的通用 GICv3 配置）。
- pexpert 找 intc 的方式是**按属性**：`pe_identify_machine.c:535`
  `SecureDTFindEntry("interrupt-controller", "master", …)`（`pexpert/gen/device_tree.c:309`
  是 strcmp 值比较），而 loader 写的是 `device_type = "interrupt-controller"`
  （`loader.c:3473`）+ `compatible = "arm,gic-v3"`——任何平台上都不会命中。这是 v1 起
  就有的、纯日志噪音。

### 1.2 事实二：`soc_phys: 0x400000` 本身是对的（任务书误读）

- `pe_identify_machine.c:178 pe_arm_get_soc_base_phys()` 读 `/arm-io` 的 `ranges` 取
  `ranges[1]`（窗基址）为 `gPESoCBasePhys`——所以 0x400000 就是平台表 `io_base`，**它本
  来就该是窗口基址，不是 GIC**。GIC 地址 = 窗基址 + gic 节点 reg 偏移。
- loader 侧（`loader.c:3457-3459, 3475`）：`/arm-io` `ranges = {0, io_base, io_size}`；
  `/arm-io/gic` `reg = {gic_dist - io_base, 0x10000, gic_redist - io_base, 0x100000}`。
  内核侧（`gic_v3_irq.c:428-438`）按路径 `/arm-io/gic` 读回 reg 再加 `soc_base` 还原
  绝对地址。QEMU 上这套算术闭环（0x8000000 + 0 / 0xA0000 → 打印的 gicd/gicr 虚地址）。
  **所以"0x400000 混进 GIC"的猜想不成立——错的是 `gic_dist/gic_redist` 两个常量本身。**

### 1.3 根因：`platform_phk110` 的 GIC 常量是 redwood/SM8350 的

- `loader.c:615-632`（修复前）：`.gic_dist = 0x17A00000, .gic_redist = 0x17A60000`，
  与 `platform_redwood`（`loader.c:602-613`）逐位相同——Wave 6 建条目时"照抄 redwood"
  （wave6 doc §表格明说 gic 两项 "Cape FDT intc@17a00000 …；redwood 同值"）。
- 0x17A00000/0x17A60000 是 **SM8350 (lahaina)** 的 GIC（上游 sm8350.dtsi
  `intc@17a00000`，reg `<0x17a00000 0x10000>, <0x17a60000 0x100000>`——redwood 条目对它
  自己是准的）。SM8475 是 taro/SM8450 家族，GIC 在 **0x17100000**。
- 本机铁证：`intel/live-fdt.dtb`（Wave 2 从真机抓的、设备固件交给它自己内核的树），
  `dtc` 解出：
  ```
  intc: interrupt-controller@17100000 {
      compatible = "arm,gic-v3";
      redistributor-stride = <0x00 0x40000>;
      reg = <0x17100000 0x10000 0x17180000 0x200000>;
  ```
  → **GICD 0x17100000 (0x10000)，GICR 0x17180000 (0x200000)，8 个 PE 每 PE 0x40000**。
  （顺带：Wave 3 引的 "Cape FDT 0x17A00000" 是别家 SoC 的树，对 PHK110 是错误权威。）

### 1.4 abort 的完整链路

1. 内核（v3 payload 的 kernel 条目 = `hakios-kernel`，14,841,368 B，尺寸逐字节同 v3）
   `gic_v3_irq.c:428-438`：按 DT 把 GICD 映到 **0x17A00000**、GICR 映到 **0x17A60000**
   （0x400000 + 0x17600000 / 0x17620000）。
2. `arm_init.c:636 → PE_init_cpu() → pe_init_fiq() → gic_v3_irq_cpu_init()`：
   `gic_v3_irq.c:403` 第一次 MMIO 读 `*(volatile uint64_t *)(frame + GICR_TYPER)`，即
   **0x17A60000**——taro 互连不解码该地址。
3. ARMv8 数据中止 FSC=0b010000：`osfmk/arm64/proc_reg.h:1775
   FSC_SYNC_EXT_ABORT = 0x10`。`sleh.c:1584-1628 handle_kernel_abort`：
   非 translation/alignment/parity → 打印 `Unclassified kernel abort (fault_code=0x10)`
   后 `panic_with_thread_kernel_state("Kernel data abort.")`。超早期 panic 挂死（日志到
   此为止，60 s 后 loader 侧看门狗复位）——`intel/m3-boot1/b10-logdump-v3.bin` 全量复核：
   0x9d4 处 `== END OF LOG ==` 前最后一条就是 abort 行，其后无任何字节。
   时间轴吻合：abort 在 pe_arm_init_debug 之后 135 µs，正是 PE_init_cpu 的 GIC 首读窗口
   （QEMU 同窗口 1.1 ms 后打出 `gic: v3 …`）。

### 1.5 第二处必改：GICR 区大小 0x100000 → 0x200000

`loader.c:3475` 硬编码 `reg[3] = 0x100000`。内核不改的前提下
`gic_v3_irq.c:402` 在 `[gicr_base, gicr_base+reg[3])` 内每 0x20000 步进找 redistributor，
到 `panic("gic: no redistributor for MPIDR …")`。本机 bootcpu=7，PE7 的帧在
+0x1C0000..0x1E0000，0x100000 的窗口根本够不着 → 就算改了地址不改大小，8 核一拉照样
panic。taro 真实 GICR 区是 0x200000（stride 0x40000）；内核 0x20000 步进扫描时偶数步
命中各 PE 的 RD 帧（GICR_TYPER 真身），奇数步落在本 PE 槽内 SGI 页 +8（保留区，读 0，
无 LAST 位），扫描仍能正确命中每核——但窗口必须 ≥0x1E0000，取真值 0x200000。

## 2. 修复（`~/hakios/kernel/xnuloader/loader.c`，qemu/redwood 字节级不变）

三处，全部平台条件化（新字段缺省 0 = 旧行为）：

1. `struct platform`（loader.c:581, 589）新增两字段：
   `uint64_t gic_redist_size;`（0 → 0x100000，即现状）与
   `int pexpert_compat;`（0 → 不写 pexpert 兼容节点/属性）。
2. `platform_phk110`（loader.c:617-648）：
   `.gic_dist = 0x17100000, .gic_redist = 0x17180000, .gic_redist_size = 0x200000`，
   `.pexpert_compat = 1`；注释写明 live FDT 出处与 Boot #10 abort。
3. DT 构造（loader.c:3487-3531）：
   - gic 节点 `reg[3] = gic_redist_size ? : 0x100000`（qemu/redwood 取 0 → 0x100000，
     与旧字面量逐位相同）；
   - `pexpert_compat` 时 gic 节点加属性 `"interrupt-controller" = "master"`——
     `SecureDTFindEntry("interrupt-controller","master")` 命中，pexpert 打印
     `found interrupt-controller` + `gPicBase:`（ml_io_map 只建映射，fork 的 FIQ 走
     自己的 GIC 驱动，永不访问）；
   - `pexpert_compat` 时补两个节点：`/arm-io/timer`（device_type=timer）与
     `/arm-io/cpu-debug-interface`（device_type=cpu-debug-interface），reg 各
     `{0, 0x1000}`（SoC 窗口首页，可解码）。作用：
     `pe_arm_map_interrupt_controller` 打印 `found timer`+`gTimerBase:`，
     `pe_arm_init_debug` 不再打 fail 行。安全性已核：arm64 的 `pe_arm_init_timer`
     只调 `ml_init_timebase(args, &empty_funcs, 0, 0)`
     （machine_routines.c:841-860，仅当 BootCpuData 且原值为 NULL 时存入，存入值与
     从未运行时的缺省逐位相同）；`ml_init_arm_debug_interface`
     （machine_routines.c:1592-1596）只存指针 + `do_debugid()`
     （machine_cpuid.c:74，读 ID_AA64DFR0_EL1 系统寄存器，不碰映射）；panic_trace
     缺省关闭（TUNABLE panic_trace_disabled），映射不会被访问。

**副作用面（pexpert 成功路径）**：`gPicBase/gTimerBase` 全仓无其他读者
（grep 仅 pe_identify_machine.c 自身）；`interrupt-controller`="master" 属性无其他
消费者。qemu/redwood 不设 `pexpert_compat` → DT 字节级与 v3 一致 →
**按任务书规则免跑 QEMU 冒烟**（条件化路径与旧路径输出同一字节序列，是可静态证明的）。

## 3. 重建链（全 WSL；FD 未重建，按主代理指令复用 Wave7 FD）

```
a. loader.efi   cd ~/hakios/kernel && PAYLOAD_BASE=0xF4000000 xnuloader/build.sh
   → 66,560 B（v3 66,048，+512；XNUP 条目尺寸独立，graft 布局自适应），
   sha 5223ba37…。strings 复核：phk110 / "KERNEL LOG"（Wave7b）/ "usb: try"（Wave8）/
   master / interrupt-controller / cpu-debug-interface 全在。
b. FD           未重建。复用 ~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/
   SILICIUM_UEFI.fd，sha256 8924cb67e349f7c188c258bde08fe90155d81a9d27ef5d0a965399ffb7a7180f
   （与主代理给定的 Wave7 FD 哈希逐位一致，Boot #9 真机已验证的挂点版）。
c. XNUP v4      从 device-layer/udon-hakios-payload-v3.bin 提取五条目（loader.efi 66,048 /
   kernel 14,841,368 / ramdisk 16,528 / cmdline 248 / kernel.ver 48）→
   python3 xnuloader/mkpayload.py -o payload-v4.bin --no-version
     loader.efi=<新> kernel=<提取> ramdisk=<提取> cmdline=<提取> kernel.ver=<提取>
   → 14,924,920 B；程序化断言 kernel/ramdisk/cmdline/kernel.ver 四条目 v3==v4 逐字节相等，
   loader.efi 条目 == 新构建。cmdline 原样（serial=0 loader_return_after=20 cpus=8
   bootcpu=7 soc_* 全串未动）。
d. 打包+graft   python3 -I wave4-scripts/package-udon-boot.py --fd <Wave7 FD> --shim
   device-layer/udon-hakios-BootShim.bin --stock device-layer/stock-boot-a.img
   --payload payload-v4.bin --out device-layer/udon-hakios-grafted-v4.img
   --report device-layer/udon-hakios-grafted-v4.report.json
   → 192 MiB；kernel_gzip 6,763,786（v3 6,784,834，loader 变更致 gzip 窗口重排，已知现象）；
   stock OEM vbmeta（2,432 B，25314ab1…）原样在位。
```

未重建 FD / BootShim / kernel Mach-O：kernel 条目从 v3 原样复用（内核源码零改动）。

## 4. Git 状态（kernel 仓，未提交，未 identity，不 commit）

- staged（Wave7b，原样未动）：`mkxnuimg.py`、`tools/provenance.allow`、
  `xnuloader/build.sh`、`xnuloader/loader.c`（+48）。
- unstaged：`xnuloader/loader.c`（+134/-11 = Wave8 usb_start 重试 ~+76/-8 ⊕ 本 wave
  DT 修复 +58/-3）。**未执行任何 git reset/checkout/stash/clean**；
  `git status --short` = `M mkxnuimg.py / M tools/provenance.allow / M xnuloader/build.sh /
  MM xnuloader/loader.c`，与接手时一致叠加。

## 5. 自检

`python3 -I wave5-scripts/verify-udon-hakios.py device-layer/udon-hakios-grafted-v4.img
device-layer/stock-boot-a.img device-layer/udon-hakios-BootShim.bin <Wave7 FD>
payload-v4.bin` → **ALL 21 CHECKS PASSED**（header diff 仅 bytes 8..14 / gzip round-trip
19,119,472 B / shim 头 0xA7100000 + shim+fd=0x4000f0 / FD _FVH@shim+0x28 / XNUP 逐字节 /
entries {loader.efi 66,560, kernel 14,841,368, ramdisk 16,528, cmdline 248, kernel.ver 48} /
cmdline 含 serial=0+loader_return_after=20 / AVBf footer / stock vbmeta 逐字节 / 192 MiB）。

## 6. 下一轮（Boot #11）预期内核日志

修好后 `/arm-io/gic` reg = {0x16C00000, 0x10000, 0x16D80000, 0x200000}，+soc 0x400000 =
0x17100000 / 0x17180000。预期（对照 qemu-open.log 的推进顺序）：

```
pe_arm_init_interrupts: args: 0xfffffff…
pe_arm_map_interrupt_controller: soc_phys:  0x400000          ← 正常，窗口基址
pe_arm_map_interrupt_controller: found interrupt-controller   ← 新增（原 fail 行消失）
pe_arm_map_interrupt_controller: gPicBase: 0xfffffff1…        ← 新增
pe_arm_map_interrupt_controller: found timer                  ← 新增
pe_arm_map_interrupt_controller: gTimerBase: 0xfffffff1…      ← 新增
（"failed to find cpu-debug-interface" 消失——成功路径本就不打日志）
gic: v3, distributor 0xfffffff1…, cpu 0's redistributor 0xfffffff1…, virtual timer on PPI 27
Darwin Kernel Version 22.5.0: …
…（25 驱动推进、用户态……）
```

若仍见 `Unclassified kernel abort (fault_code=0x10)`：说明 0x17180000 的读在 Qualcomm
hyp 的 stage-2 下也不放行（Protected MMIO），那属于下一 wave（loader/UEFI 侧先探针或
借固件自己的 GIC 状态），与本 wave 的 DT 语义修复无关——但按 live FDT 与 ABL→Linux
同链路可访问性判断，大概率能过。

**残余风险（记录）**：内核 GICR 扫描步进 0x20000 硬编码，taro stride 是 0x40000，奇数步
读各 PE 槽内 SGI 页 +8 的保留区。若该处读出非零且 bit4(LAST)=1 的垃圾，扫描会提前断
（panic "no redistributor"）——概率低（保留区惯例 RAZ），真机日志一验便知；根治需改
kernel（下一 wave 决定，本 wave 红线禁改内核）。

## 7. 回退方式

- 只退 DT 行为：Windows `device-layer/` 重刷 `udon-hakios-grafted-v3.img`（621db6f5…，
  v3 = Boot #10 实测镜像，GIC 地址错误的现状）。v1/v2/v3 全部在位未动。
- 代码层：本 wave 改动全部在 unstaged 的 loader.c，`git diff xnuloader/loader.c` 里
  Wave8 块之外的 hunks 即本 wave（`gic_redist_size`/`pexpert_compat` 字段、phk110 条目、
  DT 构造两块），可按 hunk 丢弃；Wave7b（staged）与 Wave8 块不受影响。
- kernel/ramdisk/cmdline/kernel.ver 与 v3 逐字节相同，无需回退考虑。
