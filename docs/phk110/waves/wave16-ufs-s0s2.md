# Wave 16 报告：v0.4 第一战 —— UFS 存储栈 S0-S2 只读验证（Boot #22，零行代码改动）

> 2026-11-04 · 执行子代理产出 · 输入 = Wave15 施工单（docs/waves/wave15-ufs-research.md §4）+ fork 树（config/cmdline 叠加，禁重置）+ Boot #21 v10e 现场
> 结论先行：**S0 ✅ / S1 ☑（注明）/ S2 ✅（附一项良性发现）——UFS 存储栈一次点亮**。内核/loader **零行代码改动**（只动 config 2 行 + cmdline 追加 6 字节），`ufs=2` 上机即出 S0 验收行：**129 个分区以 /dev/ufs_NAME + /dev/rufs_NAME 发布、loader 页 0xfaa41000、4096 KB buffer**；6 个 UFS LUN GPT 头/表 CRC 全过；darwin 缺席符合预期（P0 未做）；零 panic、60 s 干净返回、v0.3 全部回归项无损。

---

## 0. 执行摘要

| 项 | 结果 |
|---|---|
| 施工量 | config 2 行（`phk110.config:38` → `CONFIG_HAKIOS_UFS=y`；`common_defconfig:277` → `CONFIG_UFS_NATIVE=y`）+ cmdline 追加 ` ufs=2`（374→380 B）——**代码 0 行**，Wave15 预判兑现 |
| 内核 | v11 增量重编（14,860,288 → 14,920,640 B，+60,352 B = hakios.ufs.c + ufshc.c 编入；sha `a7f4641f…`） |
| 镜像 | `udon-hakios-grafted-v11.img`（192 MiB，sha `f97b5e6e…`），verify **42/42 全绿**（fd/shim/loader.efi/ramdisk/kernel.ver 全部 cmp 断言未动） |
| 刷写 | 标准通道一次通过：adb → bootloader（busid 2-2, 18d1:d00d）→ usbipd attach → WSL root fastboot：getvar `taro` ✓ → sha 对包 ✓ → flash boot_b（Sending 4.9 s / Writing 0.6 s 全 OKAY）→ set_active b → reboot |
| 回安卓 | ~12 min 8 轮兜底自发回（60 s × 8 循环，与 v10e 家族行为一致） |
| 判定 | **S0 ✅ / S1 ☑（sysctl 不可读，已注明）/ S2 ✅（附发现 F1）；无新 panic；R4 解除；R1 本轮未被行使（无数据读）** |

---

## 1. 施工记录（照 Wave15 §4 S0 单）

### 1.1 config 开关（2 行）

```
devices/phk110/configs/phk110.config:38   # CONFIG_HAKIOS_UFS is not set  →  CONFIG_HAKIOS_UFS=y
configs/common_defconfig:277              # CONFIG_UFS_NATIVE is not set  →  CONFIG_UFS_NATIVE=y
```

`make phk110_defconfig` 重生成 .config（`CONFIG_HAKIOS_UFS=y` 落 :30）；`hakios-config.py args` = `cpus=8 bootcpu=7 cpufreq=1 ufs=2 socinfo=1 thermal=1 ufs_native=1`（65 字符，预算 607）。CONFIG_UFS_WRITE / CONFIG_VAR_STORE / ufs_native boot-arg **本轮全部不开**（S3+/N 的事；native 编进而 boot-arg 关 = 死代码在筒）。

### 1.2 构建（增量）

- `make kernel`（tools/make-kernel.sh 判定通过：只有 kext symbol-set 步骤失败，与 Wave2 以来的配置性 exit 2 同款）。
- **插曲（构建环境，非代码）**：首轮失败 `hakios.s3910.o: Operation not permitted` —— Wave12c 曾以 root 构建，BUILD/obj 下 8 个产物 root 拥有。`chown -R <host>` 修复后重跑即过。产物 `hakios-kernel` 14,920,640 B（+60,352 B = UFS 驱动体积），UFS 日志串（`ufs: no node for` / `partitions of the phone` / `ufs_requests` / `native:`）全部在链接产物内。

### 1.3 cmdline（6 字节）

`wave16-scripts/make-cmdline-v11.py`：v10e 字节（=v10 家族，374 B）尾部 NUL 前追加 ` ufs=2` → 380 B（sha `0fc7fd6f…`）。其余逐字节不动；断言无 `ufs_write`/`var_hfs`/`ufs_native`；预算 379+68 < 608 ✓。

### 1.4 payload / 打包 / 自检

- `wave16-scripts/repack-payload-v11.py`：基 = v10e payload（Boot #21 字节），kernel + cmdline 两 entry 换新，loader.efi（66c6b342）/ ramdisk（4f72da61）/ kernel.ver（afd473f5）cmp 断言字节等 → payload `d680072e…`。
- 打包：`wave4-scripts/package-udon-boot.py`，FD 取自 v10e 镜像内提取件（`wave16-scripts/fd-8924cb67.bin`，sha 即 report 的 8924cb67——树内散装 .fd 无一匹配，提取件为字节级权威），shim 108ce972 未动 → `udon-hakios-grafted-v11.img` + report.json。
- 自检：`wave16-scripts/verify-udon-hakios-v11.py`（v10e 版改造）**42/42 PASS**，final sha `f97b5e6eaeab11afbc832e538c8c86ee3455311a89701a3a89b954bc9cd658a7`。

---

## 2. 判定（Wave15 §4 验收行逐字对）

### S0 ✅ UFS init + 枚举

证据行（`intel/m3-boot1/b22-kernel-log.txt` :324，t=37.087 s）：

```
[   37.087004]: ufs: 129 partitions of the phone's storage as /dev/ufs_NAME and /dev/rufs_NAME, read only, through the loader's page at faa41000 and its 4096 KB buffer
```

- 与 Wave15 §S0 预测行逐字吻合（ufs.c:1759）。**N = 129**（devfs 节点数；表内共 133 项，4 项因同名被 devfs 拒绝，见 F1）。
- loader 侧 6 个 LUN（unit 0-5）全部枚举且 GPT 校验通过（logdump loader 段）：
  - `ufs: unit 0: … 61514752 blocks of 4096 (240292 MB)` + `GPT header crc right (e6d54133), table of 32 entries crc right (98d6498e)`
  - unit 1/2: 8 MB、unit 3: 32 MB、**unit 4: 3144 MB、table of 96 entries**、unit 5: 572 MB——六个 LUN 的 header/table CRC 全部 `crc right`。
  - survey 读到 userdata 超级块与 super tables（`ufs: part userdata: lba 3756780..61514746, 231031868 KB` 等分区行）。
- **darwin 缺席 ✓**：分区列表尾部 = `… rawdump, splash_odm, userdata`（unit 0 尾），全 logdump 无 darwin 分区行——P0 前预期行为，upstream 写路径不会被 offer（`block_write_requested=0`）。
- **UEFI 活性旁证 ✓**：本轮 logdump 写入/回读成功（128 KiB 完整落盘）= UFSDxe 读、写、flush、GPT 定位持续工作。

### S1 ☑ mailbox 首读（机制上链，数据读未行使）

- `kern.hakios.ufs_requests` **sysctl 不可读**：loader 返回时的 sysctl dump 只含固定集（soc_name/soc_id/pmic_peripherals/thermal_*），无 ufs 键；本轮无用户态 shell、未开 `ufs_check=1`，无任何 /dev/ufs_* 读者 → 无块数据请求发生，计数保持 0 是设计内行为。
- **mailbox 页交付成功的间接证据（S0 行本身）**：loader 页 0xfaa41000 + 4096 KB buffer 的 parts 表被内核完整解析出 133 项（名字/LBA/块大小全部 sane 且与 survey 交叉一致）——mailbox 共享内存路径（loader 写 → 内核映射读）端到端工作。
- 数据对拍（FNV/ufs_check）移交 S3 附带行使；R1（DALSYSDxe coherence）本轮**未被行使**——mailbox 页是 loader CPU 写（非 UFSDxe DMA 窗），F1 的 129 项元数据正确不构成 R1 证据。

### S2 ✅ GPT 可见性（附发现 F1）

- **R4 解除**：表内 133 项 GPT 分区（129 节点 + 4 拒绝）< BLOCK_MAX_PARTS=160，无任何截断征兆（无 "too many"、无尾部丢失——unit 0 列表完整走到 userdata）。
- **无真实枚举错误**：4 条 `ufs: no node for ufs_last_parti (the same name twice?)` 的根因是 **devfs 层 EEXIST**（内核同刻打印 `devfs: ufs_last_parti: name slot allocation failed (Errno=17)`）——OnePlus 多 LUN GPT 的哨兵分区 `last_parti` 在 4 个 LUN 上重名，驱动逐项发布时后 4 个同名节点被 devfs 拒绝。**枚举本身看到并尝试了全部 4 个**；129 个其余节点全部发布成功。
- 内核侧无 `ufs: no partition information: the block service is off`（loader 侧 block service 确认开启的镜像证据 = 129 分区行存在，b21 对照为 0 条 ufs 行）。

### 无新 panic / 回归全绿

- `panic:` 0 条；`--- loader_return_after expired ---` 干净返回（:62）；`== END OF LOG ==` 完整（26,919 B 提取件）。
- 8 核：cpu_number 0-6 注册 + `arm_cpu_init(): cpu 1..6 online` ×6（+boot core）= 与 b21 逐条同款。
- 触摸：`s3910: TouchComm v1 firmware: mode 0x1 (application), part number "S3910PA0B0-15.2"` + `touch screen ready (TouchComm v1)`（:363/:375）——v10e PASS 行为原样。
- 按键：arbiter v7、双外设通道 407/434、PMK8350 type/subtype 逐字同款（2 条 "transfer was dropped" 与 b21 家族同频）。
- launchd stub 心跳 t=10..50 s + 内存状态行，会话节奏与 b21 一致。

---

## 3. 风险登记观察（R1-R4 + 新发现）

| # | 观察 | 本轮证据 | 对 S3+ 的含义 |
|---|---|---|---|
| R1 | DALSYSDxe coherence 嫌疑 | **未被行使**：本轮 mailbox 页为 loader CPU 写/内核映射读（UFSDxe DMA 不经手），133 项元数据全对。FNV 对拍（ufs_check=1）或首个数据卷读才会真正行使。**主代理补情报（2026-11-04，源头 wave1-phk110pkg-spec.md:102/:326）**：redwood Binaries README 把 "DALSYSDxe UFS cache coherence" 列为 5 个必需二进制补丁之一；**我们 udon FD 里的 DALSYSDxe 是 senna_bc 原厂原版（Wave 4 填充，无此 patch）**——logdump 自身 DMA 一直正常，但 S3 起的块数据读会把 UFSDxe DMA 写进 4096 KB 共享 buffer（payload 窗口新布局），正是该 patch 针对的场景 | S3 首刷带 `ufs_check=1`（cmdline 余 228 字符）一次定位；**若 FNV 对拍不一致 → 第一嫌疑坐实**，处理路径 = 对照 redwood Binaries README 给 udon DALSYSDxe 打同款 patch（graft 流程加一步，FD sha 将变） |
| R2 | stale logdump | 未发生（`== KERNEL LOG ==` 完整 + END OF LOG 在位） | 例行检查即可 |
| R3 | UIC/doorbell 超时 | 不适用（native 未激活——CONFIG 编进但无 boot-arg，`native:` 串在筒未出声） | N 步阶梯时再议 |
| R4 | GPT 枚举差异 | **解除**（133 < 160；6 LUN CRC 全过） | 无需扩 BLOCK_MAX_PARTS |
| **F1（新）** | devfs 同名拒绝：`last_parti` ×4（Errno=17） | :313/:316/:321/:323 | 良性——4 个 0 尺寸哨兵分区无节点不影响读写路径；若 S3+ 需要精确计数/全部节点，可在 ufs.c 发布处对重名做去重（如 `ufs_last_parti_1..4`），1 行级改动 |
| **F2（新）** | ufs=2 使 loader 在内核 entry 前多花 ~26.6 s（b22 首条 dmesg t=36.97 s vs b21 t=10.39 s；会话尾部 86.99 s vs 60.41 s，同一 +26.6 s 平移；心跳/expired 相对节奏与 b21 完全一致） | b22 vs b21 对照 | 纯 wall-clock 平移，无功能影响；来源 = block_start 的 6-LUN GPT/survey 同步读（UFSDxe 慢路）。S8 持久化的 var_save_ms 上限核算时记入这笔固定开销 |

## 4. S3 预备清单（下一战施工单）

1. **P0 darwin carve 用户批准门**（破坏性，照 Wave15 §P0：userdata-carve-phk110 工具化 + 20 GiB 对齐 + 双表 CRC + mkdatavol 12 G 卷）——所有 S3+ 的前置。
2. config：phk110.config 覆盖 `CONFIG_UFS_WRITE=y`（+ 可选 `CONFIG_VAR_STORE=y`）；cmdline 追加 `ufs_write=1`（+ **必刷** `ufs_check=1` 行使 S1 数据对拍，一并坐实/排除 R1）。
   - **R1 应急预案（主代理补情报固化）**：若 ufs_check FNV ≠ host survey 哈希 → DALSYSDxe cache coherence patch 缺失坐实（udon FD 的 DALSYSDxe = senna_bc 原厂原版；redwood Binaries README 列其为 5 必需补丁之一，wave1-phk110pkg-spec.md:102）→ 处理 = 对照 redwood README 给 udon DALSYSDxe 打同款二进制 patch，graft 流程加一步。mailbox 元数据路径（loader CPU 写）不受此影响，S0 行不受污染。
   - **SMMU 路线佐证（UniXNU BRINGUP 原文）**："SMMU programming is deliberately skipped on SM8475 because it caused an external abort"——同款手机真机观测，与 Wave15 §1.6 裁决（不碰 SMMU）互证；若 R1 坐实也不动摇 SMMU 路线，病灶只会在 DALSYSDxe 的 DMA 一致性。
3. 测试矩阵（Wave15 §S3）：4K 单块 → 256K 整 buffer → 跨 buffer 两块 → 越界拒绝（offset=UFS_WRITE_FIRST-1 → EROFS）；验收行 `ufs: /dev/rufs_darwin takes writes, …`（ufs.c:1802）+ `kern.hakios.ufs_writes` 增长、`ufs_write_errors=0`。
4. F1 若顺路修：ufs.c 发布循环重名去重（非阻塞）。
5. 判定行检查 `fast` vs 慢路文案（ufs.c:1808-1809）确认 loader 侧 BLOCK_CAN_FAST 语义（R5 前哨）。

## 5. 交付物清单（全部只新增）

| 文件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-grafted-v11.img` | `f97b5e6eaeab11af` | 当前在 boot_b（Boot #22）；192 MiB |
| `device-layer/udon-hakios-grafted-v11.report.json` | — | 打包报告 |
| `device-layer/udon-hakios-payload-v11.bin` | `d680072ed9f5d359` | XNUP 容器（kernel+cmdline 换新，余 cmp 断言） |
| `device-layer/hakios-kernel-v11.bin` | `a7f4641f84965b9a` | v11 内核（UFS 编入，+60,352 B） |
| `device-layer/udon-hakios-cmdline-v11.bin` | `0fc7fd6f98ebf003` | v10e + ` ufs=2`（380 B） |
| `logdump-v11.bin` | `b5b768b71e2a2c55` | Boot #22 logdump（131,072 B） |
| `intel/m3-boot1/b22-kernel-log.txt` | `027906c5c5bd24c8` | 内核日志提取件（26,919 B，完整） |
| `wave16-scripts/make-cmdline-v11.py` / `repack-payload-v11.py` / `verify-udon-hakios-v11.py` / `fd-8924cb67.bin` | — | 施工/自检四件（fd 为 v10e 镜像提取件） |
| WSL 树内 | — | `devices/phk110/configs/phk110.config`、`configs/common_defconfig` 各 1 行（叠加，未 commit） |

## 6. 红线遵守

- 只刷 boot_b（fastboot flash boot_b 一条；无其他分区/oem/wipe/erase）✅
- 不碰 userdata、不做 P0 carve ✅（loader survey 只读；ufs_write 未开，内核无写通道）
- 禁 git reset/checkout/stash/clean、不 commit ✅（config 2 行直接叠加）
- Windows device-layer 只新增（v11 四件 + report.json）✅
- 失败重试 0 次（构建权限插曲修复后一次通过；刷写一次通过）✅
