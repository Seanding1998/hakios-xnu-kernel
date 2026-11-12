# 阶段 16b · 2026-11-03 · 数据卷准备工具的适配（只勘察，不写盘）

> 2026-11-03 · P0 准备产出 · 输入 = docs/waves/wave15-ufs-research.md §4 P0 段（施工蓝本）+ fork `~/hakios/kernel/tools/`（只读）+ 真机 adb（**全程只读**：ls / blockdev --getsize64 / dd if= 备份件 → /data/local/tmp → pull）
> 结论先行：**P0 可以按 GIB=20 一次落位**——20 GiB = 整 10,240 个 f2fs 段，carve 后 darwin = LBA 56,271,872..61,514,746 = **5,242,875 块（4096），与 redwood 的 UFS_DARWIN_MIN 一块不差**，内核/loader/mkdatavol 全部零改动；且 **20 GiB 尾段（段 102224..112463）当前零数据**（最后有数据的段 = 58,005），f2fs 缩减无需搬移任何数据。dry-run 全绿（双表 CRC、仅 2 个 entry 变化、死规矩精确命中）。

---

## 0. 交付物

| 文件 | 说明 |
|---|---|
| `tools/userdata-carve-phk110.py` | GPT 手术工具 PHK110 版（fork userdata-carve.py 为底，~40 行改动）：PHK110 实测值注释/校验、**死规矩断言 `law()`**（darwin ≠ 5,242,875 块即拒绝，wipe 路径同样断言）、**固定 unique GUID**（6E9D0187-62E7-4887-B50E-FB241BF4BE6D，供 darwin-write-phk110 严格校验）、`--dry-run` 旗标、metadata-encrypted userdata 的 dm 读取说明、SHA256 产物登记。安全机制全保留：双表 CRC、读回校验、"只改 2 个 entry"不变量、table-before-header 写序 |
| `tools/darwin-write-phk110.py` | darwin 写入工具 PHK110 版（fork darwin-write.py 为底，仅常量+注释）：PARTN=15 / FIRST=56,271,872 / LAST=61,514,746 / NODE=sda15 / UNIQUE=6E9D0187…。guarded-dd、身份三重校验（GPT+sysfs+blockdev）、PROTECTED=1374208、selftest、读回比对全部原样 |
| `wave16-scripts/p0-carve-run.sh` | P0 执行总脚本（**本阶段未执行破坏性步骤**）：10 个子命令分步带检查点，每步失败即停 + 回退指引；内建独立 GPT 验证器（不信工具自述）、哈希链、dm 设备自动发现、fastboot/adb 双通道灌卷、rollback-gpt 一键回退；通道纪律承 upstream darwin-write.py——文本走 `adb shell`（phone()），**二进制读回一律走 `adb exec-out`（phone_bin()，防 CRLF 损坏）** |
| `backups-slotb/`：gpt-sda-head.bin / gpt-sda-tail.bin / userdata-meta-before-dm.bin / userdata-meta-before-raw-ciphertext.bin / segment_info-before.txt / MANIFEST-p0.sha256 | 勘察备份件（哈希登记见 §5） |
| `backups-slotb/p0-staging/`、`p0-staging-run/` | carve 工具输入分检目录 + 产物分检目录（gpt-head.new / gpt-tail.new / darwin-guid.txt，仅供执行波交叉核对；执行波会重新生成） |

红线遵守：adb 只用了 `ls` / `blockdev --getsize64` / `dd if=`（块设备**零写入**，备份件落 /data/local/tmp 后 pull）/ `df` / `cat`（proc/sysfs）；f2fs resize、carve、flash 一概未做；未碰 boot_b；未 commit；未动 mkdatavol.py（DATA_FIRST=2042368 保持）。

---

## 1. 真机勘察表（2026-11-03，Android 16 在跑，Magisk root）

设备：OnePlus Ace 2 Pro（`ro.product.device = OP5913L1`，codename **udon**），Android 16，kernel `5.10.236-android12-9`，DT model `Qualcomm Technologies, Inc. Cape MTP, Udon`。

### 1.1 LUN 拓扑

| LUN | 节点 | 字节数 | 分区数 | 备注 |
|---|---|---|---|---|
| 0 | sda | 251,964,424,192（61,514,752 × 4096） | 14 | **GPT 目标 LUN**；getss = 4096（与 redwood 同） |
| 1 | sdb | 8,388,608 | 5 | xbl 等 |
| 2 | sdc | 8,388,608 | 5 | xbl_b 等 |
| 3 | sdd | 33,554,432 | 7 | ALIGN_TO_128K/cdt/ddr 等 |
| 4 | sde | 3,296,722,944 | 78 | boot/dtbo/vbmeta/modem/**logdump(sde66)** 等 |
| 5 | sdf | 599,785,472 | 19 | persist 系列/modemst 等 |

全盘分区合计 **129**（不含 6 个整 LUN 节点）；carve 后 130 < 160（`BLOCK_MAX_PARTS`，ufs.c:73）→ **R4 无虞**。loader `block_is_darwin` 要求 unit 0——darwin 落在 sda（LUN 0）✓。

### 1.2 LUN 0 GPT（dd 头尾 8 块实测，双 CRC 全对、双表一致）

| 项 | 值 |
|---|---|
| header | LBA 1，size 92 |
| entries | **32 × 128 B**，LBA 2（主）/ 61,514,747（备） |
| first_usable / last_usable | 6 / **61,514,746** |
| 空余 entry | 15..32（carve 取 **15** → sda15） |

### 1.3 LUN 0 分区表（14 个 entry）

| # | name | LBA | 块数 | 字节 |
|---|---|---|---|---|
| 1 | ssd | 6..7 | 2 | 8,192 |
| 2 | persist | 8..8,199 | 8,192 | 33,554,432 |
| 3 | misc | 8,200..8,455 | 256 | 1,048,576 |
| 4 | keystore | 8,456..8,583 | 128 | 524,288 |
| 5 | frp | 8,584..8,711 | 128 | 524,288 |
| 6 | super | 8,712..3,678,727 | 3,670,016 | 15,032,385,536 |
| 7 | vbmeta_system_a | 3,678,728..3,678,743 | 16 | 65,536 |
| 8 | vbmeta_system_b | 3,678,744..3,678,759 | 16 | 65,536 |
| 9 | vbmeta_vendor_a | 3,678,760..3,678,775 | 16 | 65,536 |
| 10 | vbmeta_vendor_b | 3,678,776..3,678,791 | 16 | 65,536 |
| 11 | metadata | 3,678,792..3,682,887 | 4,096 | 16,777,216 |
| 12 | rawdump | 3,682,888..3,748,423 | 65,536 | 268,435,456 |
| 13 | splash_odm | 3,748,424..3,756,779 | 8,356 | 34,226,176 |
| **14** | **userdata** | **3,756,780..61,514,746** | **57,757,967** | **236,576,632,832（220.33 GiB）** |

### 1.4 userdata 的 f2fs（关键：**metadata 加密**）

| 项 | 值 | 证据 |
|---|---|---|
| 块设备栈 | sda14 ← **dm-73**（dm name "userdata"） | /sys/block/dm-73/slaves + dm/name；`ro.crypto.type=file` + 挂载选项 `inlinecrypt` = **dm-default-key 元数据加密** |
| 原始块 0 | **密文**（sha256 2cfeb786…，无 f2fs magic） | dd if=/dev/block/sda14（只读取证，存 `userdata-meta-before-raw-ciphertext.bin`） |
| dm 层块 0 | **明文 f2fs**（sha256 da2fee90…） | dd if=/dev/block/dm-73 → 存 `userdata-meta-before-dm.bin` |
| magic / log_bs / log_bps | 0xf2f52010 / 12 / 9 → **每段 512 块（2 MiB）** | f2fs 超级块解析 |
| block_count | **57,757,967**（恰好填满分区） | 同上 |
| segment_count_main | **112,464** | 同上 |
| main_blkaddr | **176,128** | 同上 |
| 空闲/脏段 | 91,949 / 1,029 | /sys/fs/f2fs/dm-73/free_segments, dirty_segments |
| segment_info | 11,247 数据行 = 112,464 段，`段类型\|有效块数` 格式（与 carve 工具解析器兼容） | 全文存 `segment_info-before.txt`（787,337 B） |
| **尾段占用** | **段 102,224..112,463（新端以外 10,240 段）零数据；最后有数据段 = 58,005** | tailcheck 脚本实测 |
| /data 现状 | 41G used / 220G（19%）；缩减后 200.33 GiB 仍余 ~160G | df -h /data |

> ⚠️ 与 redwood 的架构差异（工具已适配）：redwood userdata 是"裸 f2fs、无元数据加密"，超级块直接读分区；PHK110 必须经 dm 层读（`/dev/block/dm-N`，dm name "userdata"）和 `/proc/fs/f2fs/dm-N/segment_info`。GPT 本身不加密，头尾备份照旧从 /dev/block/sda 读。

### 1.5 carve 精确计算（GIB=20 → 一次命中死规矩）

```
cut        = 20 GiB = 10,240 段 × 512 块 = 5,242,880 块
new_blocks = 176,128 + (112,464 − 10,240) × 512 = 52,514,816     ← F2FS_IOC_RESIZE_FS 的目标
fs_blocks  = 57,757,967 − 5,242,880            = 52,515,087 块（200.33 GiB，含 slack）
part_end   = 3,756,780 + 52,515,087            = 56,271,867      ← userdata 新末（LBA 56,271,866）
new_start  = roundup(56,271,867, 512)          = 56,271,872（空隙 5 块，2 MiB 对齐）
darwin     = 56,271,872 .. 61,514,746          = 5,242,875 块 = 21,474,816,000 B = 20.000 GiB ✓✓
wipe 路径  同样落位：(61,514,746+1−5,242,880)//512×512 = 56,271,872 ✓
```

> 勘误：wave15 报告 §4 P0 验收行写的 `blockdev --getsize64 = 21,474,844,160` 有笔误；正确期望值 = 5,242,875 × 4096 = **21,474,816,000**（与 redwood darwin 一致）。

---

## 2. 常量映射表（redwood → PHK110）

| 常量 | redwood | PHK110 | 影响文件 |
|---|---|---|---|
| userdata 位置 | entry 33（sda33） | **entry 14（sda14）**，LBA 3,756,780..61,514,746 | 勘察值，工具运行时从 GPT 现读 |
| darwin 位置 | entry 34（sda34），LBA 25,374,720..30,617,594 | **entry 15（sda15）**，LBA **56,271,872..61,514,746** | darwin-write-phk110.py 常量 |
| darwin 大小 | 5,242,875 块 | **5,242,875 块（死规矩，逐块相同）** | 内核 ufs.c `UFS_DARWIN_MIN` / loader `BLOCK_DARWIN_MIN` / mkdatavol `DARWIN_BLOCKS` → **全零改** |
| darwin type GUID | 7C3457EF-0000-11AA-AA11-00306543ECAC | 同（APFS container） | 零改 |
| darwin unique GUID | FD6854AD-24AA-4FC3-94FE-290116858D68 | **6E9D0187-62E7-4887-B50E-FB241BF4BE6D**（carve 时固定打戳） | loader **不查 unique GUID**（loader.c:1592-1596 注释明示"with a GUID of its own"）→ 零改；darwin-write-phk110.py 查（严格身份链） |
| LUN 0 节点 | /dev/block/sda | /dev/block/sda（相同） | carve 打印的 dd 命令零改 |
| 逻辑扇区 | 4096 | 4096（相同） | — |
| f2fs 超级块来源 | 裸分区（明文） | **经 dm 层**（dm name "userdata"，运行时发现） | carve 工具说明 + 执行脚本 `phone_dm()` |
| segment_info 路径 | /proc/fs/f2fs/sda33/ | **/proc/fs/f2fs/dm-N/** | 同上 |
| UFS_WRITE_FIRST / PROTECTED | 2042368 / 1374208 | **不变**（12G 卷起点与 Darwin 卷保护） | mkdatavol/ufs.c/darwin-write 全零改 |
| GIB 参数 | （redwood 当时值） | **20**（整数段、精确命中死规矩） | userdata-carve-phk110.py 调用参数 |

工具改动量：userdata-carve-phk110.py ≈ 45 行（文档 + law() + 固定 GUID + --dry-run + dm 说明 + 哈希打印）；darwin-write-phk110.py ≈ 12 行（常量 + 注释）。与 wave15 预估（~40/10 行）相符。

---

## 3. dry-run 实录（不写盘：无文件产出、手机零接触）

```
$ python3 -I tools/userdata-carve-phk110.py backups-slotb/p0-staging 20 darwin --dry-run
the table now: primary header crc right, table crc right; backup header crc right, table crc right; the two tables the same -> good
f2fs: 57757967 blocks, main area from block 176128, 112464 segments of 512 blocks; the last segment holding data is 58005
userdata: lba 3756780..61514746 (220.33 GiB) -> 3756780..56271866 (200.33 GiB, the f2fs exactly); 5 blocks between it and darwin belong to neither
f2fs-resize: /data 52514816     # = main_blkaddr 176128 + 102224 segments x 512 blocks
darwin: lba 56271872..61514746 (20.000 GiB, 5242875 blocks of 4096), entry 15 (sda15 under Android), type APFS container, unique GUID 6e9d0187-62e7-4887-b50e-fb241bf4be6d (the port's fixed one for this phone)
the new table: primary header crc right, table crc right; backup header crc right, table crc right; the two tables the same -> good
blocks that differ: head [1, 2] (lba [1, 2]), tail [3, 7] (lba [61514747, 61514751]); entries that differ: [14, 15] (userdata -> shorter, 15 -> darwin)

--dry-run: nothing written (the phone was never touched anyway; gpt-head.new/gpt-tail.new not made)
EXIT=0
```

独立复核（verifynew2.py，不信工具自述）：新表 header/table CRC 对、双表一致、**其余 13 个 entry 逐字节相同**、备份表 == 主表、darwin = 5,242,875 块 ✓、GUID/类型 ✓。

`darwin-write-phk110.py selftest`（真机只读）：**本机 refusals 11/11 全拒**（越 PROTECTED、越 BLOCKS、非数字串等）；GPT 现读段因手机在 carve 前无 darwin entry 而按预期报"0 entries named darwin"（中途手机被 阶段 16 循环重启占走断开 adb，执行波 preflight 时会自动重验，脚本 preflight 含同款 GPT 基线哈希断言）。产出 `.new` 文件已复核：

```
gpt-head.new  eee081b02bff10867fd63f5225a199bbcdbcc5891da3c76db63e01d2e27cfc3c
gpt-tail.new  0f492dc1444a5dbf69141b1e827d3942fc52fe80529c16a7b96b092f28ef7d52
darwin-guid.txt  6E9D0187-62E7-4887-B50E-FB241BF4BE6D
```

---

## 4. 执行脚本（wave16-scripts/p0-carve-run.sh）：步骤与每步验收

运行环境：WSL（adb/fastboot/mkfs.hfsplus/clang 俱在），`P0_APPROVED=yes` 可跳过逐键确认（执行时用）。每步一个子命令，失败即停并打印回退路径。

| 步 | 子命令 | 动作 | 验收（不过即停） |
|---|---|---|---|
| 0 | `preflight` | 设备/根/GPT 基线/工具链盘点 | userdata→sda14、无 darwin、sda=251,964,424,192、getss=4096、dm "userdata" 在；GPT 头尾 sha256 = 勘察基线（变了即拒绝，防"GPT 已漂移还按旧数 carve"） |
| 1 | `backup` | **只读**：头尾 8 块 + dm 超级块 + segment_info → `$RUN_DIR`，手机端+宿主端双哈希比对 | 三件哈希 = 基线（8dc1919b…/7ed16c87…/da2fee90…）；f2fs 参数 = (57757967, 112464, 176128)；产物进 `backups-slotb/p0-run/` |
| 2 | `resize` | 建 f2fs-resize（clang 静态 arm64 → /tmp，**不写 fork 树**）→ push → probe → 确认 f2fs 仍 = 57,757,967 → 确认键 `RESIZE` → `/data 52514816` | resize-rc=0；sb-after = (52,515,087, 102,224)；segment_info-after = 102,224 段；df 正常；**打印"4 步前禁重启"横幅**；执行前亲眼验数据 |
| 3 | `dryrun` | carve 工具 `--dry-run`（带 sb-after 二次校验缩减值） | 工具全检通过 + 死规矩命中 |
| 4 | `carve` | 工具真跑（仅宿主侧产物）→ 内建独立验证器（不信工具自述：CRC/entry15/双表一致/死规矩/GUID）→ 确认键 `CARVE` → push → **table→header、主→备** 写入 → 读回 8+8 块 cmp | cmp 双双全等；写后 dm 超级块可读（f2fs 无恙）；失败路径 = `rollback-gpt` |
| 5 | `verify-android` | 重启进安卓后跑 | by-name/darwin 在、`--getsize64` = 21,474,816,000、sysfs sda15 start=450,174,976 size=41,943,000、PARTNAME=darwin、df 正常、`darwin-write-phk110.py check` 全链身份通过；确认数据完好 |
| 6 | `volume` | `mkdatavol.py darwin.simg`（**零改**，mkfs.hfsplus 在 WSL）→ fastboot `getvar all` 探 darwin 可见性 → `fastboot flash darwin`；不可见/失败则 `P0_VOLUME_VIA=adb` 回退：simg2img → 截取 DATA_FIRST 起的卷区 → `darwin-write-phk110.py write`（guarded + 读回） | fastboot 返回 OK / 或工具读回 sha256 相等 |
| 7 | `verify-volume` | 重启进安卓 | darwin 块 2,042,368 的 1024..1025 字节 = **H+/HX**；`sum 2042368 1` 落日志；块 0（未来 Darwin 卷）未被本步触碰 |
| E | `rollback-gpt` | 把第 1 步的 gpt-head.bin/gpt-tail.bin 按 table→header 写回双表 | 重启后 fs_mgr resize.f2fs 把 fs 长回原分区——数据无损，回到 P0 前 |
| - | `status` | 只读现状：darwin 有无、大小、dm 哈希 | — |

fastboot 通道提示已写进脚本（usbipd bind+attach 到 WSL，Windows 侧 libusb 全盲是已知结论）；boot_b 一概不碰。

---

## 5. 风险与回退（P0 段；R6/R7 编号承 wave15 §5）

| # | 风险 | 检测（脚本内建） | 回退 |
|---|---|---|---|
| R6 | f2fs resize 拒绝（ioctl 不支持/段不空/空间不足） | probe 步 + resize-rc + sb-after 断言，任一失败即停 | **重启即自愈**（fs_mgr 把 fs 长回去，零损失）；尾段当前全空（§1.4）使本风险概率很低 |
| R7 | GPT 手术错表 | 双 CRC + 双表一致 + 独立验证器 + 读回 cmp + "只改 2 entry"不变量，五重 | `rollback-gpt`（第 1 步备份件，哈希登记可对）；备表先写纪律保证中途断电也有一份好表 |
| R-new | **GPT 漂移**（勘察后表被 OTA/工具改过） | preflight/backup 双步基线哈希断言 | 重跑勘察重导 carve 数（工具按 DIR 输入现算，无硬编码 LBA 参与计算） |
| R-new | dm 设备号变化（dm-73 → dm-N） | `phone_dm()` 按 dm name "userdata" 现查，不写死号 | — |
| R-new | fastboot 看不见新分区（bootloader GPT 视图缓存） | `getvar all | grep darwin` 探测 + flash 失败即提示 | adb 通道：simg2img + darwin-write-phk110 write（身份/读回全链保留；只写 DATA_FIRST 起，0..2042367 不触碰） |
| R-new | resize 与 carve 之间被重启 | carve 前重读 dm 超级块 = 52,515,087 断言（dryrun 工具内也查 sb-after） | 重启后 fs 已长回 → 从 resize 重来（数据无损） |
| R-new | 阶段 16 boot_b 循环与 P0 撞车 | 脚本头注 + preflight 要求 Android 在位 | 执行波错峰（等 boot_b 波落定） |

备份件哈希（backups-slotb/MANIFEST-p0.sha256，节选）：

```
8dc1919bc32bc1185a4e0c4970cd32a6829ca5adcc0bfc05b9ec4f8b2c24bd5c  gpt-sda-head.bin
7ed16c8724440bc05006cda3df94f72e8aef8e600f31164d643ed7f4d4e3f4af  gpt-sda-tail.bin
2cfeb786b5ad66d48d0c9006488f8114ff8b0d2db7a7da40871525e229afcb5f  userdata-meta-before-raw-ciphertext.bin（密文取证）
da2fee90d10220d3fad9dd9775300758b2bf49c8235c74ff9cd3f3dd44e4b144  userdata-meta-before-dm.bin（明文超级块）
eca0809477f57797367bf2e87ff18fa2f3109037945cdf24b9a6a6906cd17f92  segment_info-before.txt
eee081b02bff10867fd63f5225a199bbcdbcc5891da3c76db63e01d2e27cfc3c  p0-staging-run/gpt-head.new
0f492dc1444a5dbf69141b1e827d3942fc52fe80529c16a7b96b092f28ef7d52  p0-staging-run/gpt-tail.new
```

---

## 6. 执行清单（执行时逐项打勾；逐键确认或 P0_APPROVED=yes）

- [ ] 前提：boot_b 波（阶段 16）落定、无并行刷写；手机进 Android、adb root 可用
- [ ] `p0-carve-run.sh preflight` —— GPT 基线哈希过（否则重跑勘察）
- [ ] `p0-carve-run.sh backup` —— 三件哈希登记进 p0-run/
- [ ] **确认点 A**：明白"接下来缩 20G 文件系统（数据不搬不移），失败可无损重启回退"
- [ ] `p0-carve-run.sh resize` —— sb-after = (52,515,087, 102,224)；**此后到 carve 完成前禁重启/禁 fastboot**
- [ ] 亲眼验 /data 数据完好（相册/文件）
- [ ] `p0-carve-run.sh dryrun` —— 死规矩 5,242,875 命中
- [ ] **确认点 B**：明白"接下来改 GPT（userdata 缩到 200.33 GiB、新增 darwin 20 GiB），错表可 rollback-gpt"
- [ ] `p0-carve-run.sh carve` —— 读回 cmp 全等
- [ ] `adb reboot` → `p0-carve-run.sh verify-android` —— darwin = 21,474,816,000 B；再验数据
- [ ] `p0-carve-run.sh volume`（fastboot 优先；失败 `P0_VOLUME_VIA=adb` 重试）
- [ ] 重启 → `p0-carve-run.sh verify-volume` —— H+/HX 签名在位
- [ ] 收尾登记：本清单勾选结果 + 实测 darwin getsize64 + 卷签名块哈希，回填 STATUS.md
- [ ] （P0 后，S0 波）`devices/phk110/configs/phk110.config:38` → `CONFIG_HAKIOS_UFS=y`，cmdline 加 `ufs=2`，验证 `ufs: N partitions…` 枚举行含 darwin

## 7. 红线遵守

- 手机零块设备写入（dd 全部 if=；备份件写 /data/local/tmp 后 pull）✅
- f2fs resize / carve / flash 未执行（工具与脚本就绪，等执行波）✅
- boot_b 未碰；git 未 commit/reset/checkout/stash/clean；mkdatavol.py 未改 ✅
- 备份件哈希登记（upstream-manifest 风格，MANIFEST-p0.sha256 + 本报告双处）✅
