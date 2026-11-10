# 阶段 16c · 2026-11-04 · darwin 分区与数据卷就位（全程 adb）

> 2026-11-04 · 执行记录 · 前代（同一 wave16c 执行线）已完成 preflight/backup/resize/dryrun/carve/verify-android 六步并验证（`backups-slotb/p0-run/RESUME-NOTE.txt` + `RECERT-BASELINE.txt`），卡在第 6 步 volume 的 fastboot 通道（usbipd→WSL bulk 数据面被打线事件打死，已弃用）。强制重启手机回安卓（唯一物理动作）后，本波以**纯 adb 软件通道**完成灌卷 + verify-volume + 收尾。零 fastboot、零 usbipd、零 git reset。

## 0. 执行摘要

**P0 完成。** darwin 分区（sda15，20 GiB，carve 产物）内 HFS+ 空数据卷 12G 落盘并通过三重全卷 sha256 全等验证；verify-volume PASS（卷头签名 `HX`）；`adb reboot` 回安卓后盘上签名字节级复验在位、userdata 数据面完好。**S3-S8 全部解锁**（wave15-ufs-research.md §4 施工单的 S0-S2 已由 阶段 16 Boot #22 达成）。

| 项 | 值 |
|---|---|
| 写入工具 | `tools/darwin-write-phk110.py write`（未改一字节；guarded-dd + 身份三重校验 + 读回 sha）|
| 通道 | WSL Fedora44 Linux adb 客户端 37.0.0p1 → `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037` → Windows adb 服务器 37.0.1（USB 数据面）|
| 镜像 | WSL `~/p0-darwin-vol.raw` = 13,109,276,672 B（= 3,200,507 块 × 4096 精确）|
| 全卷 sha256 | `88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8`（源文件 / 写后读回 / 独立重读 三方全等）|
| 写入位置 | darwin 块 2,042,368..5,242,874（字节 8,365,539,328..21,474,815,999；恰收尾于分区末块）|
| dd 实测 | 3,200,507+0 records in/out，13,109,276,672 bytes，47.517 s，263 MB/s（2026-11-04 10:04:02）|
| verify-volume | PASS：块 2,042,368 签名 **`HX`**（HFS+X 日志式）；darwin 块 0 sum = 全零哈希（未来 Darwin rootfs 区零触碰）|
| 耗时 | push ~80 s（~164 MB/s 稳态）→ dd 47.5 s → 读回 sha ~51 s；全程 ~4 分钟 |

## 1. 前代六步（本波零重做，引用登记）

证据全部在 `backups-slotb/p0-run/`（gitignore 内，MANIFEST-p0.sha256 + RESUME-NOTE.txt 登记）：

| 步骤 | 判定 | 关键证据 |
|---|---|---|
| 0 preflight | PASS（00:47）| GPT 基线哈希过（head 8dc1919b… / tail 7ed16c87…）；userdata=sda14、sda 4096 扇区、dm"userdata"在位 |
| 1 backup | PASS（00:55）| 三件拉取+哈希+重认证：**RECERT-BASELINE** = dm-super 整块哈希漂移仅 1 字节（offset 3786: 0x07→0x08，f2fs 结构字段全等，ColorOS 计数器嫌疑，放行；RECERT_DM_SUPER_SHA=4990b8bf…）|
| 2 resize | PASS（00:57，resize-rc=0）| f2fs 57,757,967 → **52,515,087 块 / 102,224 段**（= 预期精确值）；/data 数据完好 |
| 3 dryrun | PASS（00:58）| carve 工具 --dry-run EXIT=0，死规矩 5,242,875 块命中 |
| 4 carve | PASS（01:00）| gpt-head.new `eee081b0…` / gpt-tail.new `0f492dc1…` 双副本写 sda，读回 cmp 全等；userdata 缩至 LBA …56,271,866，新增 darwin 56,271,872..61,514,746 |
| 5 verify-android | PASS（01:02）| sda15 = 21,474,816,000 B；PARTNAME=darwin；darwin-write check 全链过；/data 200G/41G；用户数据抽查（DCIM 42 / Download 7 / 437 pkgs）|
| （卷产物）mkdatavol | EXIT=0（01:03）| darwin.simg 53,464 B（sha256 `d82f845c…`，本波补记）；simg2img + tail 裁剪 → WSL `~/p0-darwin-vol.raw` 13,109,276,672 B，sha256 `88c1cd99…` 已登记 |

暂停原因（RESUME-NOTE）：fastboot flash darwin 两次挂死（bulk URB 全零数据；手机侧 ABL fastboot 数据端点被中断的上传打死）→ fastboot 通道弃用 → 随后强制重启回安卓。**本波即从这里接续。**

## 2. 本波执行逐步（全证据）

### 2.0 现场核实（preflight 断言，全过）

- `adb devices` → `SERIAL_REDACTED device`（安卓在线，slot a）
- `adb shell su -c "blockdev --getsize64 /dev/block/sda15"` → **21,474,816,000**（= 5,242,875 × 4096 精确）
- `/dev/block/by-name/darwin -> /dev/block/sda15`（symlink 在位）
- 工具只读身份链 `check` → PASS（见 §4 日志 10:02:00 行：entry 15 / LUN 0 / LBA 56271872..61514746 / 类型+unique GUID 全对 + GPT 双 CRC 过）
- WSL 暂存镜像复核：13,109,276,672 B，sha256sum = `88c1cd99…bd8`（与前代登记值逐字同）

### 2.1 通道决策（本波唯一的计划外工作）

| 候选 | 结果 |
|---|---|
| Windows Git Bash 直跑工具 | ❌ **REFUSED**（日志 09:57:40 行，只读安全拒绝）：Windows adb.exe `shell` 对输出打 CRLF（`hi\r\n` 实测），身份解析每个字段带 `\r`。工具零写入，仅记录 |
| WSL Linux adb 直跑 | ❌ `/usr/sbin/adb`（Fedora android-tools）无设备 —— usbipd 通道已弃用（前代教训），不复 attach |
| **WSL Linux 客户端 + Windows adb 服务器（TCP）** | ✅ **采用**：`.wslconfig` 本就 `networkingMode=mirrored` + `hostAddressLoopback=true` → `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037 adb devices` 从 WSL 直接列出手机。Linux 客户端 `shell` 输出干净 `\n`（实测 `hi\n`），`exec-out` 二进制干净；**镜像原生 WSL 读，数据面走 Windows USB，零物理动作、零 usbipd** |

数据面探针：1 MB 随机文件 push → 手机端 sha256 端到端全等（`42a8beff…cd228` 双方一致，PUSH-CHANNEL-OK，137.4 MB/s 瞬时）。

### 2.2 灌卷（选项 B：预暂存镜像通道；工具链原样）

命令（工具、参数、镜像路径 = RESUME-NOTE 选项 B 原样，仅注入通道 env）：

```
ADB_SERVER_SOCKET=tcp:127.0.0.1:5037 DARWIN_WRITE=yes \
python3 -I darwin-write-phk110.py write /home/<host>/p0-darwin-vol.raw 2042368
```

工具内部全链（`logs/darwin-write-phk110.log`）：

1. `prepare`：镜像整 4096 倍数 → 3,200,507 块；范围门：块 ≥ 1,374,208（rootfs.apfs 保护区）且 2,042,368+3,200,507 = **5,242,875 = darwin 末块**，恰收尾 ✅
2. `identity()` 第一次：全链身份 + GPT 双 CRC ✅（10:02:43 计划行登记）
3. 本地 sha256(镜像) = `88c1cd99…` → `adb push` → `/data/local/tmp/darwin-write.img`（~80 s）
4. 手机端 `sha256sum` 暂存副本 = `88c1cd99…` ✅ → `identity()` 第二次（写前复查）✅
5. **guarded-dd**：同 shell 内先 `readlink -f` = sda15 且 `getsize64` = 21,474,816,000 才落 dd；`dd … of=/dev/block/by-name/darwin bs=4096 seek=2042368 count=3200507 conv=notrunc,fsync`
   → 10:04:02：**3200507+0 records in/out, 13,109,276,672 bytes, 47.517 s, 263 MB/s** ✅
6. 读回：手机端 `dd | sha256sum`（13 GB 重读）→ 10:04:53：**sha256 `88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8` -- the same** ✅
7. `finally` 清理暂存副本 ✅（手机端 `/data/local/tmp/` 复查无 darwin-write.img）；工具 **EXIT=0**

### 2.3 verify-volume（脚本子命令原样）+ 独立复核

- `p0-carve-run.sh verify-volume` → **PASS**：
  - 卷头签名（块 2,042,368 内偏移 1024）：**`HX`**（HFS+X 日志式；脚本白名单 H+/HX）
  - `sum 2042368 1` = `337114380f94…033ab`（真实卷头，非零）
  - `sum 0 1` = 全零哈希（**未来 Darwin volume 区 0..1,374,207 零触碰**，与本步无关性证明）
- 独立全卷复读（write 之后数分钟，`sum 2042368 3200507`）：sha256 = `88c1cd99…bd8` ✅ —— **第三方全卷哈希证据**（源文件 / 写后读回 / 独立重读 三方全等）

### 2.4 `adb reboot` 回安卓终验（脚本既定流程；软件通道非物理动作）

- 回安卓 ~30 s，`sys.boot_completed=1`，`ro.boot.slot_suffix=_a`（slot a 活跃不变）
- 盘上复验（重启 = 穿透任何缓存，证明物理在盘态）：
  - `blockdev --getsize64 sda15` = 21,474,816,000 ✅；`by-name/darwin -> sda15` ✅；`PARTNAME=darwin` ✅
  - 卷头字节级：`H X \0 005 200 \0 ! \0`（'HX' 签名 + HFS+ 版本 5 + 属性域）✅
  - 工具 `check` 全链 PASS ✅
  - `/data`（dm-73）：**200G / 41G 用 / 160G 余** —— 用户数据面完好 ✅

## 3. 卷几何（权威登记）

| 项 | 值 |
|---|---|
| 分区 | `/dev/block/sda15` = LUN 0 entry 15，LBA **56,271,872..61,514,746**（512B LBA），= **5,242,875 块 × 4096 = 21,474,816,000 B = 20 GiB**（与内核 UFS_DARWIN_MIN / loader BLOCK_DARWIN_MIN / mkdatavol DARWIN_BLOCKS 逐块同）|
| 分区类型 GUID | `7C3457EF-0000-11AA-AA11-00306543ECAC`（Apple APFS）|
| 分区 unique GUID | `6E9D0187-62E7-4887-B50E-FB241BF4BE6D`（carve 打的固定 GUID；loader 不查、darwin-write 严查）|
| HFS+ 数据卷 | darwin 块 **2,042,368..5,242,874**（3,200,507 块 = **13,109,276,672 B**）；darwin 字节 8,365,539,328..21,474,815,999；内核视角 = `/dev/ufs_darwin_data`（`var_hfs=ufs_darwin_data`）|
| 保护区 | darwin 块 0..1,374,207（未来 Darwin rootfs.apfs 区）本波**零写入**（工具范围门 + 块 0 全零 sum 双证）|
| 卷头 | 偏移 1024 签名 `HX`（HFS+X 日志式）、版本 5（mkfs.hfsplus 带日志产物；mkdatavol.py 零改动）|
| darwin 块 0..2,042,367 | 未来 Darwin rootfs 区，**从未成为写入目标**（前代 fastboot 半途分析 + 本波工具范围门双证）|

## 4. sha256 登记

```
88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8  ~/p0-darwin-vol.raw（WSL 暂存源，3,200,507×4096）
88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8  sda15 块 2042368..5242874 写后读回（write 内置链，10:04:53）
88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8  同范围独立重读（sum，本波第二通道复核）
d82f845c8acdf2745c238d92630096f4ebcdcb9889f079c33f51fb53c460af4f  backups-slotb/p0-run/darwin.simg（mkdatavol 产物 53,464 B，本波补记）
42a8beff10917830f97db2d02acd035c2d6026fd023e10dc5a986facfcacd228  1 MB 通道探针（本地=手机）
337114380f9497f6947632c2b04d169cf765632e17b025b1e0cfd334def033ab  darwin 块 2042368（HFS+ 卷头块）
ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7  darwin 块 0（= 全零哈希，未触碰）
```

`logs/darwin-write-phk110.log` 本波新增行：09:57:40 REFUSED（Windows CRLF，只读安全拒）→ 10:02:00 check PASS → 10:02:43 write 计划 → 10:04:02 dd → 10:04:53 读回 same → verify-volume 与独立 sum 行。

## 5. 通道教训与登记（本波新增）

1. **Windows adb.exe `shell` CRLF footgun**：文本通道必坏（`adb exec-out` 不坏）。darwin-write-phk110.py 的身份解析在 Windows 侧直跑必 REFUSED（安全拒，不落写）。**已在日志留 REFUSED 证据行**；不在本波改工具。
2. **新 adb 数据通道配方（可复用，替代死掉的 usbipd fastboot/adb 路径）**：
   `.wslconfig` 已有 `networkingMode=mirrored` + `hostAddressLoopback=true` → WSL 任意 Linux adb 客户端加 `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037` 即复用 Windows adb 服务器的 USB 数据面：文本干净（Linux 客户端 shell 语义）+ 文件原生 WSL 读 + 零物理动作。本波 13 GB push 稳态 ~164 MB/s、dd 263 MB/s。
   （前代 RESUME-NOTE 登记的两项脚本问题——resize probe 门反逻辑、fastboot 通道依赖——沿登记不改，本波未触发前者、后者已由本配方终结。）

## 6. 红线遵守

- 只碰 sda15(darwin)：工具三重身份门 + guarded-dd 同 shell 复核 + 写前/写后 identity() ✅
- 写入偏移 = 块 2,042,368 起，恰收尾分区末块；保护区 0..1,374,207 零触碰（范围门 + sum 证）✅
- darwin 范围外零扇区写入（全波唯一块设备写 = 该 dd）✅
- 禁 fastboot ✅（零 fastboot 调用）；禁 git reset ✅；boot_a/boot_b/slot 表零触碰（GPT 为前代 carve 已验证产物，本波未动）✅
- 手机临时文件已清（darwin-write.img）；用户数据面全程在线（resize→carve→灌卷→reboot 全链 /data 200G/41G 无损）✅

## 7. P0 完成 → 解锁与下一步

**P0 全链完成（0-7 子命令全 PASS）。** wave15-ufs-research.md §4 施工单：

- ~~P0~~ ✅（本波）· ~~S0~~ ✅ ~~S1~~ ☑ ~~S2~~ ✅（阶段 16 Boot #22）
- **S3（有界读写回读，第一个开写实验）→ S4（flush/写序）→ S5（设备发布）→ S6（HFS+ 挂载）→ S7（/var 内容）→ S8（持久闭环）：全部解锁**
- S3 第一次刷写必带 `ufs_check=1`（cmdline 预算余 228 字符；R1 DALSYSDxe coherence 情报见 STATUS.md 1f 条）——内核将把本卷认作 `/dev/ufs_darwin_data`
- 镜像现状：boot_b 仍为 v11（UFS S0-S2 版）；S3+ 开写属 cmd/配置增量，沿用 boot_b 一揽子授权通道
