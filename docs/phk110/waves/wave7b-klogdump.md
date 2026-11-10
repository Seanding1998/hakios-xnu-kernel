# 阶段 7b · 2026-11-03 · 内核日志落盘缺失的修复

Date: 2026-11-03. Agent: 阶段 7b（全程未碰手机；loader.c 单点修复 + 重建交付 v3）。
目标：Boot #8 实测 loader 打印 `kernel returned: log at 843ae89c0, 717 bytes` 后，logdump 里只有
loader 自己的日志块，内核 717 B 未落盘——让内核日志真正进 logdump。

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-grafted-v3.img` | 201,326,592 B (192 MiB) | `621db6f5128ce7972e41fdf6cae58afe779e6ace93bb4080d2203398b50089b2` |
| Packaging report | `udon-hakios-grafted-v3.report.json` | — | `46d2bb6197bc9855436964e115f912a6dc33f25321d91e461cb9d568f2e4c86f` |
| loader.efi (stage-1, klog 保留修复) | `udon-hakios-loader-v3.efi` | 66,048 B | `a8ca535822ab44fabe3a4102c79eeef6379fc8a5e8bae1017c519a8e5dc3e248` |
| XNUP payload (仅 loader.efi 条目换新) | `udon-hakios-payload-v3.bin` | 14,924,408 B | `ae8762d6024012b45e01a4da38c21ed77d99dbae0904442ffa9ff9da33bb48d6` |

自检：`wave5-scripts/verify-udon-hakios.py` **21/21 PASS**（§5）。
单元证据：`wave7b-scripts/klogdump_sim.py` **SIMULATION PASS**（§6）。

---

## 1. 根因：不是 compose 丢 klog，是 reboot() 的 flush 把刚写的块覆盖回 loader-only

`write_logs`/`compose_logs` 本身**一直**会带 klog（`compose_logs` 把 loader 日志 +
`\n== KERNEL LOG ==\n` + klog + `\n== END OF LOG ==\n` 组进 out_buf 再 write_blocks LBA0），
任务书猜想 (a)(b)(c) 均不成立。真正的时序缺口：

```
efi_main (loader.c ~4393)
  run_kernel(0, 0)
    └─ 内核干净返回 → print("kernel returned: log at %x, %d bytes")   (~3609)
    └─ write_logs(klog, 717)   →  compose(带 klog) → logdump 落盘 ✓    (~3623)
  reboot()                                                             (~4396, 无条件落到这)
    └─ hc_take_back("before the reset") + flush_log()                  (~622-623)
        └─ write_logs(NULL, 0) → compose_logs(NULL,0) → out_buf = 纯 loader 日志
        └─ write_blocks(LBA 0, 4096) ← 把刚写的组合块整个覆盖掉 ✗
    └─ cold reset
```

Boot #8 里组合块与 loader-only 块都圆整到 4096 B（组合后 staged_len≈log_len+752 仍在一块内），
所以 reboot 的 flush 是**完整覆盖**：logdump 最终 = loader-only 4096 B 块，且因 `kernel returned…`
那行在 log_buf 里，回读块末尾恰好有这行——与 M0-PROGRESS 的 Boot #8 现场逐字吻合
（"loader 只写自己的 4096 块"）。~1 秒后内核日志被自己的 loader 抹掉。

## 2. 修复（`~/hakios/kernel/xnuloader/loader.c`，+16 行，两处）

```c
 static const char *staged_data = out_buf;   /* what "upload" sends: normally the log in out_buf */
 static uint64_t staged_len;
+/*
+ * The kernel log of the last run, as write_logs received it from run_kernel. A plain flush
+ * (flush_log: the periodic beats, and the one reboot() does right before the cold reset) must
+ * keep writing it behind the loader log. Without this the reset's flush recomposed the buffer
+ * with the loader log alone, overwriting the very block that had the kernel's bytes (Boot #8:
+ * "kernel returned: log at ..., 717 bytes" on screen, logdump with the loader's log only).
+ */
+static const char *run_klog;
+static uint64_t run_klog_len;
```

```c
 static void
 write_logs(const char *klog, uint64_t klog_len)
 {
 	efi_block_io *bio = find_log_partition();
+	int echo = klog != NULL;    /* the run's own log goes to the console when there is no partition */
+
+	if (klog != NULL && klog_len != 0) {
+		run_klog = klog;        /* a run handed its log over: it stays until the next run */
+		run_klog_len = klog_len;
+	} else if (klog == NULL && run_klog != NULL) {
+		klog = run_klog;        /* a plain flush: the last run's log keeps its place */
+		klog_len = run_klog_len;
+	}
 
 	compose_logs(klog, klog_len);
 	if (bio == NULL) {
 		/* No log partition (QEMU): echo the returned kernel log on the console instead. */
-		if (klog != NULL) {
+		if (echo) {
```

语义与边界：

- run 交出的 klog（干净返回、`OTHER_CPU_HUNG` 两路）被记住；其后**任何**裸 flush（reboot 的、
  `log_other_cpu` 周期性的、USB `fastboot reboot` 的、UEFI exception 路径的）都继续把它写在
  loader 日志后面——正是 `compose_logs` 注释里写的契约（"the kernel log of the last run"）。
- 记忆门槛 `klog != NULL && klog_len != 0`：klog 为 NULL/0 长度时行为与旧代码逐字节一致
  （§6 模拟已证 no-run flush 与零长 klog 两场景 new==old）。
- QEMU 无分区回显由 `echo`（原始实参）门控：只有 run 自己那次写会回显，后续 flush 不重复刷屏。
- redwood/QEMU 场景无 logdump 分区（bio==NULL 路径原样），行为不变；有分区的 redwood 顺带受益
  （同缺口同修）。
- 已知留痕（记录，不影响本 wave）：`run_klog` 指向内核 mailbox（PA）。若经 USB `oem run` 连跑
  第二轮，第二轮进行中的周期 flush 会拿旧指针组进 mailbox 的**当前**内容（mailbox 常被新 run
  复用）——读内存无害，仅语义上属"进行中"日志；下一次 run 返回的 write_logs 会覆盖记忆。

## 3. 重建链（全 WSL；FD 未重建，按计划复用现成 FD）

```
a. loader.efi   cd ~/hakios/kernel && PAYLOAD_BASE=0xF4000000 xnuloader/build.sh
   → 66,048 B（与 v2 同尺寸，graft 布局不变），sha a8ca5358…（v2 是 63e51e07…）。
   strings 复核：phk110 / KERNEL LOG / logdump / "log: %d bytes written" 全在。
   objdump 对比 v2：仅链接抖动（bl 目标整体平移）+ write_logs 新增 run_klog 存取。
b. udon FD      未重建（按计划：跳过 build-udon-firmware.sh）。
   ⚠ 身份澄清：device-layer/udon-hakios-SILICIUM_UEFI.fd 实为 **Wave-5 FD**（de4df6ac…），
   不是 Wave-6 版（5283e85b…，现仅存于 v2 镜像内；WSL Build 树里是 阶段 7-usbmode 重建版
   8924cb67…，hook 已前移、未真机验证）。wave6 报告已证 阶段 5→阶段 6 FD 功能等同
   （FvMain 仅差 8 B = BdsDxe RSDS PDB GUID 的 DEBUG 链接噪声 + PEI 时间戳），Boot #7/#8
   同一条 UnableToBoot→XnuLoader 链都经 阶段 5 系 FD 跑通，故复用 阶段 5 FD 是最保守选择。
c. XNUP v3      从 v2 payload 逐条目提取（loader.efi 66,048 / kernel 14,841,368 / ramdisk
   16,528 / cmdline 248 / kernel.ver 48）→ mkpayload.py --no-version 仅换 loader.efi 条目。
   自检：总尺寸 14,924,408 与 v2 相同；kernel/ramdisk/cmdline/kernel.ver 逐字节相等；
   loader.efi 条目 == 新构建；cmdline 原样（serial=0 loader_return_after=20 cpus=8 bootcpu=7 …）。
d. 打包+graft   python -I wave4-scripts/package-udon-boot.py --fd <阶段 5 FD> --shim
   device-layer/udon-hakios-BootShim.bin（108ce972…，阶段 5 起逐字节未变） --stock
   stock-boot-a.img --payload udon-hakios-payload-v3.bin --out …-grafted-v3.img
   --report …-v3.report.json → 192 MiB；kernel_gzip 6,784,834（v2 6,762,632，loader 变更
   导致 gzip 窗口重排，wave6 已知现象）。
```

## 4. Git 状态（阶段 8 叠加须知）

计划的 commit **未能执行**：WSL kernel 仓无 git identity（`git commit` 报 empty ident，
未擅自配置 git 身份）。已按指令完成 `git diff > /tmp/wave7b-loader.patch`（229 行 = 阶段 6 +28
+ wave7b 本修复 + 仓内既有 build.sh/mkxnuimg.py/provenance.allow 改动）并 `git add -A`
（改动全部在 index 里，阶段 8 可直接在其上提交/叠加）。修复正文即 §2 两段。

## 5. 独立自检（wave5-scripts/verify-udon-hakios.py — 21/21 PASS）

```
PASS ANDROID! magic / header diff vs stock is kernel_size/ramdisk_size only
  kernel_size=6784834 ramdisk_size=0 (stock 48114492/1455342)
PASS kernel zero-padded to page
PASS gunzip == shim+fd+payload(+pad) 19118960 B
PASS text_offset == 0xA7100000 / image_size == shim+fd 0x4000f0 / ARMd magic @0x38
PASS _FVH at shim+0x28 / FD bytes equal source
PASS magic XNUP 50554e58 / Size == len-8 14924400 / container byte-equal to source
PASS entries {loader.efi 66048, kernel 14841368, ramdisk 16528, cmdline 248, kernel.ver 48}
PASS cmdline has serial=0 + loader_return_after=20
PASS footer AVBf v1.0 / orig_size == vbmeta_offset == content end 6791168
PASS vbmeta size 2432 == stock bytes / zero fill / final size 192 MiB
final sha256: 621db6f5128ce7972e41fdf6cae58afe779e6ace93bb4080d2203398b50089b2
```

## 6. 单元证据（wave7b-scripts/klogdump_sim.py — SIMULATION PASS）

本地模拟 write_logs/compose_logs/reboot-flush 全路径对假 logdump（含 compose 的 memset 全缓冲
清零 + 长度圆整语义，klog≠NULL 但 len=0 时 C 仍写空段节的细节也照抄）：

```
OLD flow logdump (Boot #8):  kernel log section present: False   ← 复现现场
NEW flow logdump:            kernel log section present: True
NEW block: loader log 101 B | b'43ae89c0, 717 bytes\n' | klog 60 B | b'\n== END OF LOG ==\n'
no-run flush: new flow byte-identical to old flow: True          ← NULL klog 行为不变
zero-length klog: new flow byte-identical to old flow: True      ← 0 长度行为不变
```

## 7. 刷写说明

```sh
fastboot flash boot_b device-layer/udon-hakios-grafted-v3.img
fastboot set_active b
fastboot reboot
```

- 屏上时间线与 Boot #8 一致（阶段 5 系 FD）：UniXNU 菜单 → 手动选 **Return to firmware** →
  `XNULOADER` banner → `platform phk110` → 内核日志上屏滚动 → 20 s 后干净返回 →
  `log: N bytes written to logdump` → 冷复位循环（已知无害；退出进 fastboot 重刷 backup）。
- **本轮验证点**：循环一轮回安卓（set_active a）后 `dd if=/dev/block/by-name/logdump`
  应见 4096 B 块 = loader 日志 + `\n== KERNEL LOG ==\n` + 内核 717 B + `\n== END OF LOG ==\n`
  （`strings`/`grep -a "== KERNEL LOG =="` 直接可判）。若组合后 staged_len 越过 4K 边界则块为
  8192 B，同样有效。
- 回退：重刷 `backups-slotb/backup-boot_b.img`。

## 8. 待真机验证清单

1. logdump 块内 `== KERNEL LOG ==` 段与 717 B 内核日志在位（本 wave 主目标）。
2. `run_klog` 记忆路径在真机的持久性（复位前 flush 组块、回读一致——loader 自带 read-back
   打印 `read back the same` 可直接核对）。
3. wave6 遗留：small_cores 0x0f vs 0x07（MIDR 逐核比对）；PSCI CPU_ON 0x700 应答值。
