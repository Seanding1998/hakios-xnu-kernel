# 阶段 6 · 2026-11-03 · loader 平台表 platform_phk110 与整镜像重建

Date: 2026-11-03. Agent: 阶段 6 (全程未碰手机; WSL 构建全链)。目标：修掉 Boot #7 的根因
—— loader 平台表无 SM8475 条目 → FB 基址匹配失败 → 回落 `qemu-virt` 配置 → 内核拿到 QEMU 的
fb/GIC/拓扑 → Data Abort → EDK2 `CpuExceptionHandlerLib.c(438)` 冻结。

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-grafted-v2.img` | 201,326,592 B (192 MiB) | `6fb33fc1e9250dfdc5c85d87d8939070a17e0853b59e8a469662afe30d066452` |
| Packaging report | `udon-hakios-grafted-v2.report.json` | — | `b52b99a8455f6c305f5a618a1ef982cdcc50800af689da4e6f83dccabafdc020` |
| loader.efi (stage 1, 平台表已加 phk110) | `udon-hakios-loader-v2.efi` | 66,048 B | `63e51e0770286711c3d56e0d9bf79f2f50dbbd07c084b6c74a7fd6cc960e5b51` |
| XNUP payload (cmdline +`cpus=8 bootcpu=7`) | `udon-hakios-payload-v2.bin` | 14,924,408 B | `51aede89a15afcae0177667e90f3d6133d74aef3f1f1992c9309c1392acd4c57` |

WSL 中间产物：`/tmp/wave6/`（loader.dis/new.dis、xnup-payload.bin、unsigned.img）。
内核仓改动：`~/hakios/kernel/xnuloader/loader.c` **仅 +22 行**（含 阶段 3 存量 6 行 PAYLOAD_BASE
#ifndef 时 `git diff --stat` 为 +28），redwood/qemu 条目零触碰。
阶段 5 原型 `udon-hakios-grafted.img`（sha `7b97f1e3…`）**未覆盖**，BootShim 与 阶段 5 **逐字节相同**
（240 B，`108ce972…`——纯汇编无时间戳）。

---

## 1. 平台表 diff（`xnuloader/loader.c`，两处）

### 1.1 新条目（紧跟 `platform_redwood` 之后）

```c
static const struct platform platform_phk110 = {
	/*
	 * OnePlus Ace 2 (PHK110), Snapdragon 8+ Gen 1 (SM8475), booted through the udon
	 * UEFI: its SimpleFb hands the framebuffer out at the "Display Reserved" address
	 * of the firmware's memory map (Platforms/OnePlus/udonPkg .../MemoryMapLib.c),
	 * and that address is how this platform is recognized.
	 */
	/* io_base must be non-zero: XNU treats a zero SoC base as "no SoC" and skips clock setup. */
	.name = "phk110", .io_base = 0x00400000, .io_size = 0x3FC00000,
	.gic_dist = 0x17A00000, .gic_redist = 0x17A60000, .uart = 0, .log_other_cpu = 1,
	.cores = 8, .core_shift = 8,
	/*
	 * Cores 0-3 are Cortex-A510s, 4-6 Cortex-A710s and 7 the Cortex-X2 the firmware
	 * starts on. The device's FDT numbers them in the second affinity field (cpu reg
	 * 0x000, 0x100, ..., 0x700) and groups them the same way: EPSS freq-domain 0 =
	 * cpu0-3, 1 = cpu4-6, 2 = cpu7; the idle states split at the same place.
	 */
	.small_cores = 0x0f,
};
```

### 1.2 选台分支（`efi_main` 内，原 `if/else` 中插入一路）

```c
		if (SCREEN.base == 0xE1000000ULL) {
			PLAT = &platform_redwood;
		} else if (SCREEN.base == 0xB8000000ULL) {
			PLAT = &platform_phk110;        /* udon SimpleFb's "Display Reserved" */
		} else {
			ramfb_phone_screen();
		}
```

这一路同时让 PHK110 **避开** `ramfb_phone_screen()`（那是 QEMU fw_cfg 专用机制，Boot #7 在真机上
空跑过一次：FW_CFG 读不到 → select==0 → 提前 return，无害但无意义）。

---

## 2. 字段来源清单（逐字段证据）

| 字段 | 值 | 来源 |
| --- | --- | --- |
| **FB key（选台）** | `0xB8000000` | **源码实证**：`uefi-udon/Silicon/Silicium/SiliciumPkg/Drivers/SimpleFbDxe/SimpleFb.c` → `GetFrameBufferInfos()` 按名 `LocateMemoryRegionByName("Display Reserved")` → `*BaseAddress = FrameBufferRegion.Address` 原样进 `Mode->FrameBufferBase`；`udonPkg/Library/MemoryMapLib/MemoryMapLib.c:30` `{"Display Reserved", 0xB8000000, 0x02B00000, …}`。loader 的 `SCREEN.base = GOP->mode->fb_base`（loader.c:4367），故 key = 0xB8000000。任务书预期值与源码一致 |
| `io_base/io_size` | `0x00400000 / 0x3FC00000` | 照抄 redwood（同为 Qualcomm 8+ Gen 1 系外设窗）；udon MemoryMapLib 寄存器区 `IPC_ROUTER_TOP 0x00400000 … APSS_HM 0x17000000+0x02000000` 全部落入窗内；非零要求见 loader.c 注释（XNU 把 0 当 "no SoC"） |
| `gic_dist/gic_redist` | `0x17A00000 / 0x17A60000` | Cape FDT `intc@17a00000`（阶段 3 §5.3 已核）；redwood 同值 |
| `uart` | `0` | PHK110 无串口（任务书 + wave1）；屏显 console 路径（loader 只自动加 `debug=0x8`，不加 `serial=3`） |
| `psci_hvc` | 0（SMC，缺省） | 真机 Qualcomm TF-A PSCI 走 SMC；redwood 同 |
| `log_other_cpu` | `1` | bootcpu=7 时内核在 loader 之外的核上跑，需要日志分区跟记（loader.c:2351/2363 的语义，redwood 同值） |
| `cores` | `8` | 任务书 + wave1 §2.4 |
| `core_shift` | `8` | **真机 FDT 实证**（`intel/wave1b-scripts/fdt-full.txt`，阶段 1-B 抓的真机树）：`/cpus/cpu@0/100/200/…/700` 的 `reg = 0x0/0x100/…/0x700` → MPIDR 第二 affinity 字段编号，与 redwood 完全同构；`bootcpu=7` → `kernel_mpidr=0x700` 与 FDT `cpu@700` 精确一致 |
| `small_cores` | `0x0f`（cpu0-3） | **⚠ 与任务书口径不同，见 §3 偏差说明** |
| `timeout_scale` | 0（缺省） | 真机硬件不需要 qemu 的 20 倍放宽；redwood 同（不设） |

**bootcpu=7 不是 platform 结构字段**——loader.c 的机制是 payload cmdline 解析（loader.c:3022
`kernel_mpidr = (c[8]-'0') << PLAT->core_shift`）+ `run_on_other_cpu()`（PSCI CPU_ON 到 0x700，
loader 自己留在核 0 看护）。所以它走 **§4 的 cmdline 变更**实现。

---

## 3. 突出偏差：small_cores 任务书写 "3"，按真机 FDT 证据取 4 位掩码 0x0f

任务书 PHK110 事实写 "3×A510(cpu0-2) + 4×A710(cpu3-6) + 1×X2(cpu7)"（即 3 小核 → 掩码 0x07）。
但 wave1 文档该结论（"阶段 1-A 已证"）无一手来源引用，而**同一份真机 FDT**（wave1b fdt-full.txt）
有三组独立证据都指向 **4 小核（cpu0-3）+ 3 大核（cpu4-6）+ 1 prime（cpu7）**：

1. **EPSS freq-domain**：`qcom,freq-domain = <…,0,4>` cpu@0/100/200/300 同 domain **0**；
   cpu@400/500/600 domain **1**；cpu@700 domain **2**。若是 3+4 分组，cpu@300 应随 domain 1。
2. **cpu-idle-states**：cpu0-3 同用 phandle #4，cpu4-7 同用 #d——正好在 3/4 边界处分组。
3. **公开规格**：SM8475（SD 8+ Gen 1）= 1×X2 + 3×A710 + 4×A510。

字段语义是 bitmask（loader.c:569 "a bit for each of the slower cores"；loader.c:3412
`plat->small_cores & (1u << core)` → DT 里给该 cpu 标 `small-core`），只影响 XNU 调度器小核
伙伴选择，**不影响启动路径**。**取 `0x0f`（与 redwood 恰好同值），标"待真机验证"**：首跑 log 里
可读 `MIDR=%x` 逐核比对（A510 MIDR 高字节与 A710/X2 可区分）后回填。若任务书口径才是对的，
改一行重打包即可。

---

## 4. payload cmdline 变更：+`cpus=8 bootcpu=7`

阶段 3 §6 遗留项（"cpus=8 bootcpu=7 上命令行 | 依赖平台表修复"）与 阶段 5 §6.2（"intentionally
absent … Fix belongs to the kernel repo"）在本 wave 兑现。新 cmdline（248 B，阶段 5 为 231 B）：

```
serial=0 loader_return_after=20 cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000
soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000
soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws
```

loader 侧连锁行为（源码核实）：`cpus=` 在场 → 不再追加 `cpus=1`（loader.c:3134）；`more_cores=1`
→ 用 `PSCI_AFFINITY_INFO` 逐核探测后生成 DT cpu 列表，顺序 = 0x700, 0x600, 0x500, 0x400,
0x300, 0x200, 0x100（loader.c:3361 注释原话即描述 phone boot core 7 的拓扑）；`bootcpu=7` →
`run_on_other_cpu(0x700)` 经 SMC CPU_ON 把内核放到 X2 上。失败路径：PSCI 报错 → 屏打
`core 700 did not start: PSCI error N` → 结束 run → 冷复位（无二次尝试，有明确诊断可截屏）。
未加 `cpufreq=1`（不在本 wave 范围；EPSS 同址但属内核驱动侧，留待后续）。

---

## 5. 重建链（全 WSL，可重放）

```
a. loader.efi   cd ~/hakios/kernel/xnuloader && PAYLOAD_BASE=0xF4000000 ./build.sh
   验证：strings 有 "phk110"；disasm 新增 movz w12,#0xb800,lsl#16（0xB8000000，仅新二进制有；
   注意 objdump 把它渲染成 mov w12,#-0x48000000）；PAYLOAD_BASE movk #0xf400 保持；
   对比旧 loader.dis diff = 新常量 + 链接抖动。产物 66,048 B。
b. udon FD      融合重放 apply-wave5-fusion.py → 6 处编辑全 "already present, skipped"
   （含 XnuLoader.c/h 从 upstream 原样重写）→ JOBS=$(nproc) ./scripts/build-udon-firmware.sh
   → Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd（4 MiB，27 s 增量）。
   FvMain 解压 8,060,936 B；与 阶段 5 FD 的 FvMain 仅差 8 字节 = BdsDxe 的 RSDS PDB GUID
   （DEBUG 链接时间派生；阶段 5 记录的 FvMain sha 5dc409e1… 在旧 FD 上复现成功，提取器已校准）。
   PEI 部分 47 字节差 = __DATE__/__TIME__ 字符串（"Nov  2 2026" vs "15:24:26"）+ 连带的 4 条
   PC 相对寻址立即数微调。均为 EDK2 DEBUG 构建固有非重现性，功能等同。
   FvMain 内字符串实证 hook 在位："loader.efi" ×1、"XNULOADER LOG v1" ×1、"XNU Payload" ×45。
c. BootShim     cd ~/hakios/uefi-udon/BootShim && make REQUIRES_KERNEL_HEADER=1
   FD_BASE=0xA7100000 FD_SIZE=0x400000 'CFLAGS=… -DPAYLOAD_BASE=0xF4000000'
   → 240 B，sha 与 阶段 5 逐字节相同（108ce972…）。
d. XNUP         mkpayload.py …（cmdline 见 §4）→ 14,924,408 B；容器自检：magic/size/5 条目、
   loader.efi 条目内含 "phk110"。
e. 打包         python3 -I wave4-scripts/package-udon-boot.py --fd … --shim …
   --payload /tmp/wave6/xnup-payload.bin --stock device-layer/stock-boot-a.img
   --out device-layer/udon-hakios-grafted-v2.img --report …-v2.report.json
   → 192 MiB；kernel_gzip 6,762,632 B（阶段 5 6,762,817——payload 变化导致 gzip 窗口重排）。
```

## 6. 独立自检（wave5-scripts/verify-udon-hakios.py — **21/21 PASS**）

header diff vs stock 仅 bytes 8..14（kernel_size 6,762,632 / ramdisk_size 0）；gzip round-trip ==
shim+FD+XNUP(+pad) 19,118,960 B；shim 头 text_offset 0xA7100000 / image_size 0x4000F0 / "ARMd"；
`_FVH` @shim+0x28；XNUP magic/Size/逐字节等于源容器；entries {loader.efi 66,048 / kernel
14,841,368 / ramdisk 16,528 / **cmdline 248** / kernel.ver 48}；cmdline 含 serial=0 +
loader_return_after=20（子串断言，新增两项不破坏）；stock OEM vbmeta（2,432 B，25314ab1…）在
graft 偏移逐字节一致；vbmeta 后零填充；192 MiB。

---

## 7. 刷写说明

```sh
fastboot flash boot_b device-layer/udon-hakios-grafted-v2.img
fastboot set_active b
fastboot reboot
```

**预期屏幕时间线**（与 Boot #7 对比，关键差别是 `platform` 行）：

1. ABL splash → udon/Silicium UEFI（SimpleFb 画面，wave 4 同款）；底部 `[Volume Up] Boot Manager`
   倒计时 ~3 s，可无视。
2. 无可引导项 → `PlatformBootManagerUnableToBoot` → `XnuLoaderMain()` → 0xF4000000 找到 XNUP →
   独立 loader.efi：`== XNULOADER v3 ==`、`kernel.ver=…`、`payload base=F4000000 magic=50554e58`、
   **`platform phk110`（不再是 qemu-virt！）**、`display 1240 x 2772 at b8000000`。
3. `bootcpu=7`：屏上应出现 `core 700: the firmware answers 0 to the request to start it` →
   内核在 X2 上启动，verbose 日志上屏滚动（`debug=0x8`）。
4. 多核路径新现象：`cores for the kernel, in the order it takes them: 700 600 500 400 300 200 100`
   （PSCI AFFINITY_INFO 探测结果；若有核不在 off 态会打 "is not off… not the kernel's to take"）。
5. 内核起来后跑 `userland/hello`（mockfs 根）；20 s（`loader_return_after=20`）回交 loader →
   log 写 `logdump` 分区（`log: N bytes written to logdump`，无该分区则 NOT WRITTEN）→ 冷复位 →
   slot b 仍是本镜像 → 循环（wave 5 已知行为，无害；退出需进 fastboot 重刷 backup）。

**若仍异常，记录新现场**（与 Boot #7 的 EDK2 `CpuExceptionHandlerLib.c(438)` 冻结区分）：

- `core 700 did not start: PSCI error N` / `core 700 was started but never arrived` → PSCI/TF-A
  接口问题（平台表无误，查 psci_hvc conduit）；
- 内核日志滚动后中断在具体驱动 → 平台表已生效（GIC/拓扑已对），剩余为外设基址级问题
  （对照 wave1 hwmap 定位）；
- 屏无任何新输出、直接复位 → 用 `dd if=/dev/block/by-name/logdump` 取 loader 日志看走到哪步。

**回退**：`fastboot flash boot_b backups-slotb/backup-boot_b.img`（阶段 5 原型
`udon-hakios-grafted.img` 与 wave4 `udon-uefi-grafted.img` 均在盘上可重刷）。

## 8. 待真机验证清单

1. **small_cores=0x0f vs 0x07**（§3）：首跑屏显 `MIDR=%x` 逐核比对微架构位段后定稿。
2. PSCI CPU_ON 0x700（bootcpu=7）在 udon 固件下的实际应答值（屏上直接可读）。
3. `logdump` 分区是否存在、可写（wave3 §5.2 同一项仍未真机验证）。
4. EPSS LUT 行数 / `modem_ipa_fw_at=0x8b910000` / `soc_pas_mpss`（wave1 既有未验项，未变）。
