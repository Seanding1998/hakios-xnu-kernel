# 阶段 3 · 2026-11-02 · 内核与平台包的集成打包：第一份 boot 镜像

实现代理（阶段 3 集成）· 2026-11-02 · **结论先行：`xnu-phk110.img`（7,882,752 B）已产出并拷到 Windows
`device-layer/`，镜像内 shim/FD/payload 三层常量逐字节验证通过；全程未碰手机（无 adb/fastboot 调用）。**

一条链：内核仓 3 个全局文件参数化（redwood 默认逐指令不变，已证）→ `uefi/apply.sh phk110` 生成构建树
（BASE e51cd87 + hakios.patch + phk110Pkg 覆盖 + 厂商 blob）→ venv + `build_uefi.py -d phk110 -r RELEASE`
一次通过（49 images verified）→ mkpayload + 参数化后的 mkxnuimg 打包。

---

## 1. 内核仓全局文件的 phk110 参数化（redwood 默认不变，已自证）

改动的 3 个文件（`git diff --stat`：44 insertions, 15 deletions；`devices/phk110/**` 零触碰）：

### 1.1 `xnuloader/loader.c`（+6 行）

`PAYLOAD_BASE 0xF0000000ULL` 加 `#ifndef` 守卫（PANIC_LOG_BASE 是 PAYLOAD_BASE 派生值，随之正确平移）：

```c
#ifndef PAYLOAD_BASE
#define PAYLOAD_BASE        0xF0000000ULL
#endif
```

### 1.2 `xnuloader/build.sh`（+5 行）

环境变量直通编译期 define（收纯 hex，脚本内补 ULL 后缀）：

```sh
PAYLOAD_BASE=0xC0000000 ./build.sh      # → clang ... -DPAYLOAD_BASE=0xC0000000ULL
```

### 1.3 顶层 `mkxnuimg.py`（任务书写的 tools/ 实际在仓根）

| 硬编码（原） | 参数化后 | redwood 默认 |
|---|---|---|
| `FD_BASE, FD_SIZE = 0x9FD00000, 0x200000` | `--fd-base/--fd-size` | 不变 |
| `PAYLOAD_BASE, PAYLOAD_MAX = 0xF0000000, 0x04000000` | `--payload-base/--payload-max` | 不变 |
| `Build/redwoodPkg/...` | `Build/{device}Pkg/...`（`--device`） | redwood |
| `Resources/DTBs/redwood.dtb` | `Resources/DTBs/{device}.dtb`（`--dtb` 可显式覆盖） | redwood |
| `xnu-redwood.img` 默认输出 | `xnu-{device}.img` | redwood |
| prebuilt 回退分支 | 仅 `--device redwood` 走 prebuilt；其他设备报错并提示构建命令 | 不变 |

### 1.4 不变性自证（两项）

1. **loader**：改动前留档 `loader.efi` → 无 env 重建 → `llvm-objdump -d` 反汇编逐指令 diff，**除文件名头行外
   0 差异**（cmp 的 byte 129 差异是 lld-link 时间戳，非代码）。
2. **mkxnuimg**：原版存为 `mkxnuimg-orig.py` 做同条件 A/B：无 MU 树、无 prebuilt 时两者输出逐字符相同、
   exit=1 相同；`--device phk110` 走新分支（正确报 FD 缺失 + 构建提示）。phk110 覆盖跑即任务 4 的真实打包。

### 1.5 链路理清（任务书要求写明的 BootShim 链）

- `hakios.patch` 给 BASE 的 `BootShim/BootShim.S` 加 `#ifdef PAYLOAD_BASE` XNUP 拷贝块；
- `apply.sh` 随后用 `devices/phk110/uefi/files/BootShim/BootShim.S` **整文件覆盖**（同 patch 内容 +
  `#ifndef PAYLOAD_BASE` 缺省 0xC0000000）——即 mkxnuimg/build_uefi 编译的就是这份设备版；
- `build_uefi.py` 编 shim 用 `-DFD_BASE=0xa7100000 -DFD_SIZE=0x300000`，**不传 PAYLOAD_BASE** → 设备缺省
  0xC0000000 生效（构建日志实证）；
- `mkxnuimg.py` 打包时**显式传** `-DPAYLOAD_BASE=0xC0000000` → `#ifndef` 让位，同值。两条路径殊途同归。

---

## 2. apply.sh phk110：构建树生成（报错→修复全记录）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 拷入 uefi/ | tar 上游 `hakios-uefi`（Windows）→ `~/hakios/kernel/uefi/`（去 .git） | OK，BASE=`e51cd877…` |
| apply.sh | `cd ~/hakios/kernel && ./uefi/apply.sh phk110` | 见下，两次环境问题后完成 |
| 产物 | `~/hakios/kernel/Mu-Silicium/`（~5GB，BASE + 6 子模块全 init + patch + 全局 files + banner + phk110 覆盖） | OK |

**问题 1（CRLF）**：Windows 检出的 uefi/ 是 CRLF，`apply.sh` 报 `bad interpreter`；全局 `tr -d '\r'` 修复后
`git apply` 反而失败（BootManager.c/BootManagerLib.inf/Sec.c "patch does not apply"）——**hakios.patch 本身是
CRLF/LF 混合**（299 行 CRLF = EDK2 系文件区，360 行 LF = BootShim.S 区），EDK2 文件在 Mu-Silicium 仓库内就是
CRLF，patch 上下文必须保留 CRLF。修复：改用 `git archive HEAD`（仓库内原始字节，不经 autocrlf）重新拷入，
不做任何行尾转换。

**问题 2（相对路径）**：resume 脚本用 `git -C Mu-Silicium apply uefi/hakios.patch` 相对路径没打上（apply.sh
原版用绝对路径）——patch 静默未应用，后续文件拷贝照常执行。修复：树先 `git checkout -- .` 回 BASE，按
apply.sh 原序重做：`git -C Mu-Silicium apply --whitespace=nowarn <绝对路径>/hakios.patch` → `cp -r uefi/files/.`
→ `banner.py` → `cp -r devices/phk110/uefi/files/.`。

**apply 后核验（全 PASS）**：
- hakios.patch 5 处全生效：BootManager.c:208 `XnuLoaderMain ();`、BootManagerLib.inf:17 `XnuLoader.c`、
  Sec.c:47 HakiOS 横幅、SiliciumPkg.dsc.inc:39 `PcdFirmwareVendor|L"HakiOS"`、BootShim.S XNUP 块；
- V-3：Mu 树 XnuLoader.h == 设备覆盖版（0xC0000000）`diff -q` 为空；
- V-8：`Silicium-ACPI/Platforms/Xiaomi/ingres/` 有 AcpiTables.inf/SSDT.asl/SSDT.aml（BASE 版路径与 phk110.dsc
  引用一致，**无需修 dsc/fdf**，任务书预警的 BASE≠HEAD 差异未发生——phk110Pkg 对 BASE 一次构建通过）；
- 厂商 blob：`Binaries/phk110/` 从 阶段 2-D 的 F 树（`~/hakios/Mu-Silicium/Binaries/phk110`，322 文件）整目录
  拷入（apply.sh 只带来 README.md，提交外本地填充，与 D 的流程一致）；84 个 INF 引用按 PackagesPath 解析
  **missing=0**；
- `git status` 汇总：9 M（patch 4 文件 + BootShim.S 设备版 + Binaries 子模块）+ 6 ??（phk110Pkg、DTBs、
  toml、XnuLoader.c/h、banner 图），与 apply.sh 设计的树形一致。

---

## 3. venv + 构建 phk110 UEFI（一次通过）

```
cd ~/hakios/kernel
python3 -m venv venv && venv/bin/pip install -r Mu-Silicium/pip-requirements.txt   # venv 在仓根（uefi/README.md 布局）
cd Mu-Silicium
CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu- ../venv/bin/python3 build_uefi.py -d phk110 -r RELEASE
```

- shim 编译行（构建日志原文）：`clang --target=aarch64-linux-gnu -c BootShim.S -o BootShim.elf
  -DREQUIRES_KERNEL_HEADER=1 -DFD_BASE=0xa7100000 -DFD_SIZE=0x300000`
- stuart：6 子模块 resolve（apply.sh 已 init，秒过）→ 4 个 Mu_Basecore 补丁应用 → `stuart_build` 27 秒
  → **"Postbuild Image Validation Finished — 0049 Images Verified" → Success**（日志
  `/tmp/build_phk110.log` + `Build/BUILDLOG_phk110Pkg.txt`；LTO 阶段的 `make: Error 1 (ignored)` 噪音与
  F 的 ingres 构建同款，无害）；
- 产物：`Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd` = **3,145,728 B = 0x300000**（恰为 toml
  size；mkxnuimg 的 `assert len(fd)==FD_SIZE` 通过）；副产物 `Mu-phk110.img`（2,211,840 B）；
- V-6：`BUILD_REPORT.TXT` 实证 `*F PcdFvBaseAddress : FIXED (UINT64) = 0xA7100000`、
  `*P/*M PcdCPUCoresStackBase : FIXED = 0xA760D000`——FD 簇原位保留按设计落地。

## 4. 打包 bootimg

**payload**（`xnuloader/mkpayload.py`，XNUP 容器 5 条目，14,924,392 B）：

```
loader.efi=xnuloader/loader.efi   # 66,048 B —— UEFI 侧 XnuLoader.c 是 stage 0，只认 payload 里的
                                  # "loader.efi" 条目并 LoadImage/StartImage（hakios.patch 的设计），
                                  # 所以一次性 boot.img 的 payload 必须自带独立 loader
kernel=hakios-kernel              # 14,841,368 B（E 的产物）
ramdisk=userland/hello            # 16,528 B（mockfs 最小根；root.apfs 尚不存在，pkg110 实录无根会 panic）
--cmdline "…"                     # 见下
```

**cmdline（230 字符，含 serial=0；loader 另自动加 `debug=0x8 ` `cpus=1 ` `rd=md0 `，合计 ~257 < 607 上限）**：

```
serial=0 loader_return_after=20 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000
soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0
soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws
```

- **soc_* 只放与内核默认（=redwood 值）不同的 9 项**：与 redwood 的 `soc.args` 逐行 diff 得出（任务书 5 项
  清单里 `soc_cmd_db=0x80860000` 与内核默认相同 → 按"只放差异"原则舍去；diff 出的 ipa/gsi/stream 族 4 项
  也是差异项且字符预算富余，一并带上保持自描述）。
- **serial=0**：任务书建议 serial=3，但 loader 平台表不认识 SM8475（见 §6 风险 1），PLAT 落 qemu_virt 后
  loader 会自动加 `serial=3` → 内核往 qemu 的 uart 地址 0x09000000 写 console（SM8475 上是未知 MMIO）。
  redwood 实跑路径本质是 uart=0 纯屏显，`serial=0` 抑制串口镜像该已知好路径（loader.c:3120 检测 payload
  自带 serial= 即跳过）。
- **loader_return_after=20**：内核 20 秒后回交 loader → loader 把 log 写入 `logdump` 分区 → 冷重启回
  Android（loader.c:3067 解析该参数；redwood `xl run` 同款机制）。
- **cpus/bootcpu 未放（任务书口径）但原因不同**：它们**不是**编译期 CONFIG——loader.c:3128 缺省写 `cpus=1`、
  内核 hakios.patch:2520 运行时 `PE_parse_boot_argn("cpus")`。放 `cpus=8 bootcpu=7` 在当前 loader 下反而
  有害：qemu_virt 几何（core_shift=0、psci_hvc=1）会让 PSCI 走 HVC、MPIDR 换算全错。等风险 1 修掉后再放
  （见 §6 修复建议）。

**mkxnuimg 打包**：

```
./mkxnuimg.py --device phk110 --fd-base 0xA7100000 --fd-size 0x300000 --payload-base 0xC0000000 \
             -p run-payload.bin -o xnu-phk110.img
# payload: 14924392 bytes, bytesum=5294ce9a
# xnu-phk110.img: 7882752 bytes (shim 176, uncompressed 18070304)
```

**镜像内容逐项校验（全部 PASS）**：

| 校验 | 结果 |
|---|---|
| bootimg 头 | magic `ANDROID!`，header_version=1，page_size=2048，kernel_size=7,877,563，ramdisk=`dummy`（5B 占位，UEFI 不消费它） |
| 内核段 gunzip | 18,070,304 B = shim(176B) + FD(0x300000) + XNUP 容器 + 对齐；`_FVH` 位于 0xb0+40（FD 起点=shim 长 ✓） |
| shim 内嵌头 | FD_BASE `a7100000`、FD_SIZE `00300000` 逐字节 ✓ |
| shim PAYLOAD_BASE | 指令字 `d2b80005` = `movz x5,#0xc000,lsl#16` = 0xC0000000 ✓（XNUP 拷贝目标） |
| XNUP 容器 | magic 50554e58、5 条目齐全、cmdline 原文回读一致 |
| DTB | gzip 流后紧跟 `d00dfeed`（phk110.dtb，1,200,263 B） |

---

## 5. 产物清单与真机验证清单

### 5.1 产物（Windows `device-layer/`，sha256）

| 文件 | 大小 | sha256 |
|---|---|---|
| `xnu-phk110.img` | 7,882,752 B | `047cbcde9fbbb97292a1347ad7a8e89ea9144d6c94afc6506f50cb7318449d12` |
| `SILICIUM_UEFI.fd` | 3,145,728 B | `c89cea1790496b1fdbb885f793b50499e4a8f5176615ca102f73dd45c36e180c` |
| `xnu-phk110-payload.bin` | 14,924,392 B | `17c0d8ec697a0e1e49205d4c2c7f16ebb30d033296d369212115828f1d19456c` |

WSL 源：`~/hakios/kernel/{xnu-phk110.img, run-payload.bin}`、
`~/hakios/kernel/Mu-Silicium/Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`。
（device-layer/ 里旧的 `hakios-kernel`/`payload.bin` 是前序 wave 的 qemu 产物，未动。）

### 5.2 真机验证步骤（RAM boot，零写入分区）

```sh
# 手机进 bootloader（fastboot）后：
fastboot boot device-layer/xnu-phk110.img
```

**预期现象（时间线）**：

1. 屏亮 → HakiOS 横幅（BootLogo.bmp，黑底 h+红点）→ UEFI 静默启动（日志只进 serial/logdump，屏无文）；
2. BDS 找不到可引导项 → `PlatformBootManagerUnableToBoot` → `XnuLoaderMain()` → 从 0xC0000000 容器里
   StartImage 独立 loader.efi；
3. 屏出现 `== XNULOADER v3 ==` 横幅与 `kernel.ver=2.1.13-hakios-darwin22.5-sm8475-g96ffbc53`，
   **并有 `platform qemu-virt` 一行**（= §6 风险 1 的标志，首跑必然如此，不是故障）；
   display 行应为 `1240 x 2772`（V-1 验证点）；
4. loader 找到 0xC0000000 的 XNUP → 单核（cpus=1、核 0）启动内核 → 内核 verbose 日志上屏
   （debug=0x8、屏显 console）；预期内核起来后跑 userland/hello（mockfs 根）；
5. **20 秒后**内核回交 loader → loader 尝试把 log 写入 `logdump` 分区 → 冷重启回 Android。

**log 回读**：

```sh
# 若 OnePlus GPT 有 logdump 分区（OPPO 系常见，待实机确认）：
adb shell su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/logdump.bin'
adb pull /data/local/tmp/logdump.bin
# 首跑看三点：payload 行（base=0xC0000000 magic=50554e58）、内存窗 physBase（预期 0x840000000 高 bank 6GB）、
# "log: N bytes written to logdump" 行。若无 logdump 分区，loader 会在屏上打 NOT WRITTEN，日志只能靠截屏。
```

**挂死恢复**：电源键 ~15 秒（回 Android）或 电源+音量下（bootloader）。本次 boot 未写任何分区，
反复重试无积累风险。

### 5.3 风险点（按优先级）

1. **loader 平台表没有 SM8475（首跑的最大不确定性）**：`xnuloader/loader.c` 只有 qemu_virt/redwood 两平台，
   以 `SCREEN.base==0xE1000000`（redwood 的 splash 地址）识别手机；PHK110 的 FB 在 0xB8000000 → PLAT 落
   qemu_virt：io 窗 0x08000000+0x08000000、GIC 0x08000000、DT `arm-io`=qemu-virt 全是错值 → SoC 驱动
   （cpufreq/thermal/socinfo/pmic）不会 attach，v0.1 预期就是"内核横幅+log 上屏"这一步。**修复（~10 行，
   内核侧后续做，本 wave 越权不改）**：加 `platform_phk110`（照抄 platform_redwood：io_base 0x00400000、
   io_size 0x3FC00000、gic_dist 0x17A00000/gic_redist 0x17A60000 —— 与 Cape DT `intc@17a00000` 精确一致、
   uart 0、cores 8、core_shift 8、small_cores 0x0f）+ loader.c:4346 处按 `SCREEN.base==0xB8000000` 选台；
   之后 cmdline 再放 `cpus=8 bootcpu=7`（内核才是 8 核大核启动）。
2. **单核 + qemu 平台的次生影响**：PSCI 一次都不会被调（无 CPU_ON、无 SYSTEM_OFF——重启走看门狗/冷复位
   回退）；串口已关（serial=0）规避未知 MMIO 写。
3. **payload 窗**：0xC0000000..0xC3FFFFFF 按 阶段 2-D 的 DT/iomem 证据是真 RAM；loader.efi 的 PE 首选基址
   0xA1000000 落在 0xA0400000-0xA6DFFFFF（真 RAM 段 4），UEFI 拿不到首选地址会自动重定位，无碍。
4. **V-1/V-2/V-4/V-6/V-7**（阶段 2-D §5）仍需首跑 logfs/屏显复核，其中 V-2/V-6 已在构建侧闭环
   （FD 固定地址 + payload 常量逐字节验证），其余等真机验证。
5. `modem_ipa_fw_at=0x8b910000`、`soc_pas_mpss=0x4` 仍是未真机验证值（wave1 §2/§3 已标注验证法）。

---

## 6. 遗留问题 / 待办

| 项 | 状态 |
|---|---|
| loader.c 加 phk110 平台表 + FB 选台（§5.3 风险 1） | 内核侧下一 wave；本 wave 严守任务边界未动 |
| `cpus=8 bootcpu=7` 上命令行 | 依赖上项；当前加了也是错的几何 |
| `tools/provenance.allow` 两行（阶段 2-D §5.3/规格 §6.13） | **本 wave 已加**（`pending …/phk110.dtb` + `vendor …/Binaries/phk110/*`）；`provenance-check.py` 的 2 个 FAIL（`tools/mkdatavol.py:7`、`tools/sparse-split.py:8` 缺 flash 行）**是本仓既有问题**（stash 复核过），另有 redwood dtb 行的 stale warn 属同类（文件未提交时必 warn） |
| `devices/manifest.conf` 登记 | 按流程等真机验证后再定 |
| userland/root.apfs（真根镜像） | 未构建（redwood 流程另行构建）；v0.1 用 hello/mockfs |
| `Mu-phk110.img`（build_uefi 自产的无 payload 镜像） | 留在 MU 树作参考，真机验证用 `xnu-phk110.img` |
| 20 核/8GB 下全量重建 | venv 在 `~/hakios/kernel/venv`，MU 树 `Build/` 存在时增量构建跳过 setup/update，改文件后直接重跑 §3 命令 |

## 7. 复跑手册（WSL，全部可重入）

```sh
# 树已就绪时增量重建 UEFI（~40 秒）：
cd ~/hakios/kernel/Mu-Silicium && CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu- ../venv/bin/python3 build_uefi.py -d phk110 -r RELEASE
# 打包（含 payload）：
cd ~/hakios/kernel && bash <host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave3-scripts/t4c-final.sh
# 从零重建树：rm -rf ~/hakios/kernel/Mu-Silicium && ./uefi/apply.sh phk110   （然后重跑 t2g-binaries.sh 补厂商 blob）
```
