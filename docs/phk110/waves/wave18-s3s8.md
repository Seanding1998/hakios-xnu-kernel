# Wave 18 报告：v0.4 存储闭环 —— S3-S8 开写（Boot #23 v12）+ 真实 init 链换装收官（Boot #24 v13）

> 2026-11-04 · 执行子代理产出 · 两刷闭环 · 输入 = Wave15 §4 施工单（S3-S8）+ Wave19-prep Q2 八步单（真实 init 链）+ Wave17 Procursus/ssh 物料 + Wave16c P0 现场
> 用户暂停一次（Boot #23 后手机交还），唤醒后按主代理裁定把 S6-S8 与 Wave 20 真实 init 链合并实施
> 结论先行：**S3 ✅ S4 ✅ S5 ✅ S6 ✅ S7 ✅ S8 ✅（S1 补行使 ✅ / R1 清白）——v0.4 存储六步全闭环**。Boot #23（v12，cmdline-only）拿到 S3/S4/S5 硬验收行 + ufs_check FNV 16/16 全等；Boot #24（v13，双 ramdisk 真实 init 链 + darwin 前段灌卷）拿到 `/private/var: HFS Plus from /dev/ufs_darwin_data, kept between boots` + 骨架 112 目录/22 文件 + 跨 boot journal replay 物证 + **Apple launchd 真身接管 pid 1**（起 ~0.6 s 后因 `failed to query hardware target: 22` 退出 = Wave 20 的第一个定位点）。HFS+ 数据卷物理被写（全卷 sha 88c1cd99… → 6e40eaef…）。

---

## 0. 执行摘要

| 刷 | 镜像 | 判定 |
|---|---|---|
| **Boot #23** | v12（`udon-hakios-grafted-v12.img`，sha `d07b2e27…`）= v11 内核字节不动 + cmdline 追加 `ufs_write=1 var_hfs=ufs_darwin_data ufs_check=1`（428 B） | **S3 ✅ / S4 ✅ / S5 ✅ / S1 ✅（补行使）/ R1 清白**；S6-S8 ❌ 结构性缺口（stub 不跑 init.c）→ 定根因，暂停点收束 |
| **Boot #24** | v13（`udon-hakios-grafted-v13.img`，sha `465308f1…`）= 双 ramdisk（resident=flashboot.apfs 4 MB → md0 root；ramdisk=root.apfs 4 MB → md1 /redwood）+ 同款 v11 内核字节 + cmdline 追加 ` root_apfs=ufs_darwin`（449 B）+ **darwin 前段灌卷**（system.apfs 2.47 GB @块 0 + cryptex-os 2.7 GB @604420 + cryptex-app 10 MB @1270020） | **S6 ✅ / S7 ✅ / S8 ✅ / 真实 init 跑起 ✅ / Apple launchd 接管 pid 1（超预期，起后即亡 = Wave 20 事项）** |

两刷均零构建事故、刷写一次通过、失败重试 0 次；手机以安卓在线收尾（slot a）。

---

## 1. Boot #23（v12）：S3-S5 开写 + S1 补行使 + R1 判决

### 1.1 施工（照 Wave15 §S3-S5 单）

- config 2 行：`devices/phk110/configs/phk110.config` 追加 `CONFIG_UFS_WRITE=y` + `CONFIG_VAR_STORE=y`；`make kernel` 产物与 v11 **字节级相同**（sha `a7f4641f…`）——铁证这两个 CONFIG 是**运行期 boot-arg**（docs/boot-args.md:309 ufs_write=KL / :432 var_store=U），非编译门；写路径/check/saver 代码已随 CONFIG_HAKIOS_UFS=y 全量编入 v11 内核，v5 代 loader 亦自带 darwin 写 offer（`wave18-scripts/strings-check-v12.sh` 双向取证）。
- cmdline v12 = v10e/v11 字节 + ` ufs_write=1 var_hfs=ufs_darwin_data ufs_check=1`（428 B，预算 427+68=495<608）。
- repack（基 = v11 payload，**仅 cmdline 换新**，loader.efi 66c6b342 / kernel a7f4641f / ramdisk 4f72da61 / kernel.ver afd473f5 四 entry cmp 断言字节等）→ 46/46 自检全绿 → 标准通道一次刷入（getvar taro ✓ / flash OKAY 4.9s+0.55s / set_active b）。

### 1.2 判定（Wave15 §4 逐字，`intel/m3-boot1/b23-kernel-log.txt`）

| 步 | 判定 | 证据行 |
|---|---|---|
| **S3** | ✅ | :325 `ufs: /dev/rufs_darwin takes writes, whole blocks from 2042368 on (12501 MB of it); everything else of the storage is read only`。12501 = (5,242,875−2,042,368) 块 ×4096 = 13,109,276,672 B = 12,501.98 MiB 取整——**与 P0 灌卷几何逐字节吻合**。本轮尚无用户态写者（4K/256K/越界矩阵移交真实 init 波——b24 的骨架写入即首次真实写） |
| **S4** | ✅ | :326 `ufs: /dev/ufs_darwin_data: the same 12501 MB as a block device, for the data volume; writes flushed when the file system asks`——**fast 路文案**（loader 给 BLOCK_CAN_FAST，write_caps 生效），R5 前哨答案：flush 语义 = HFS journal 问时 BLOCK_OP_FLUSH（b24 的 journal replay 即其真机行使） |
| **S5** | ✅ | :326 同行（数据卷块设备发布）；S0 行 :324 = **130 partitions**（darwin 在列，129→130）；last_parti×4 EEXIST 同 b22（良性 F1） |
| **S1** | ✅（补行使） | :379-396 `ufs_check=1` 真跑完：**16 份 FNV（8 参考分区 × a/b）对拍 adb 直读基线 16/16 全等**；`check done: 568 requests, 0 errors, 586735616 bytes, 474 ms waiting`——mailbox 实测 ~460-530 MB/s（modem 214 MB/465 ms） |
| **R1** | **清白** | 16/16 哈希全等（含 214 MB modem 双槽）→ UFSDxe DMA → 共享 buffer → 内核读全程缓存一致，**udon FD 无需打 DALSYSDxe coherence patch**（wave16 §3 处理路径解除） |
| S6-S8 | ❌→定根因 | 0 条 `kept between boots`/`writable filesystem`/var.skel 行。根因 = **process 1 = wave11 驻留 stub（16,528 B 裸 Mach-O，mockfs 直接当 /sbin/launchd）**，init.c `mount_writable()`（mount("hfs","/private/var") 与骨架的唯一调用者）从未运行；mockfs root 无 /private/var 挂点且 mkdir=err。`var_hfs` 在 stub 链 inert |
| 回归 | 全绿 | 零 panic、7/7 核、TouchComm probe PASS、按键链、stub 心跳、60 s 干净返回；F2（+26.6 s 枚举平移）同 b22 |

### 1.3 R1 对拍方法（可复用）

基线不走 host 固件镜像，而走**第三可信路径**：安卓 adb root 直读分区（`wave18-scripts/fnv-baseline.sh` 拉 16 份镜像入 `intel/fnv-baseline/`）+ 主机 FNV-1a（`fnv-compare.py`，公式 = loader/kernel 同款 0xcbf29ce484222325 / 0x100000001b3）。loader 侧 survey 的 fnv 行因 logdump 32 KB 窗口截断不可见，此法绕开该限制。

---

## 2. 暂停点与唤醒后路线裁定

用户暂停（Boot #23 后手机交还，安卓在线）。唤醒后主代理裁定：S6-S8 与 Wave 20 真实 init 链**合并实施**，按 Wave19-prep Q2 八步单执行（`docs/waves/wave19-prep.md` §2.3）。两条候选路线的代码级评估结论：

| 路线 | 评估 | 裁定 |
|---|---|---|
| root.apfs ramdisk（upstream FLASHBOOT=1 CRYPTEXES=flash 链） | **在机 loader（66c6b342）已含 `resident` 条目解析与 RAMDisk/RAMDisk1 双 md 写 DT**（strings 取证 ×2/×1）；mkpayload.py 原生 `resident=FILE` 条目；init.c `mount_writable()` 在 main 中**无条件运行**（flash_root 失败也跑）；换根后 init→rc→`exec /sbin/launchd.darwin`（flash_root_mode=1 时改写为 /sbin/launchd） | **✅ 采用**（零 loader/内核字节改动、上游 redwood 实机验证） |
| stub 扩展（给驻留 stub 加 mount 等价逻辑） | stub = 裸 syscall 程序，mockfs root 无 /private/var 且 mkdir=err，骨架/var.skel 通道全缺 | ❌（工作量大、非上游验证路径） |

关键核验（全部落到文件:行，见 wave19-prep 引用 + 本波复核）：

- **APFS 多容器步进**：内核 `apfs_mount_common`（apfs_vfsops.c:985-1075）"containers lie back to back, each saying in its superblock how big it is (nx_block_count)"——cryptex 紧跟 system.apfs **真实尺寸**之后即可，无需上游 1,374,208 固定边界。
- **双 ramdisk 内存布局**：loader.c:2999-3012 resident 条目 memcpy 到 `phys_base+RESIDENT_RD_OFFSET`，"it is the root (md0), the payload ramdisk is md1"；DT `RAMDisk`/`RAMDisk1`（:3347-3358）。
- **CONFIG_ROOT_APFS/VAR_HFS**（common_defconfig:1122/1128）同为运行期参数，phk110.config 覆盖后 `make kernel` 仍字节不动（sha `a7f4641f` 三验）。

---

## 3. v13 施工（真实 init 链）

### 3.1 构建（WSL kernel 树，`FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh userland/build.sh`，约 5 分钟）

| 产物 | 尺寸 | 说明 |
|---|---|---|
| **system.apfs** | 2,475,704,320 B（604,420 块） | Darwin 根卷：select-system 20F66 子集 zlib 压缩，`mv sbin/launchd → sbin/launchd.darwin + stage0 → sbin/launchd`，/jb 未嵌（见 §6） |
| **flashboot.apfs** | 4,194,304 B（1024 块） | md0 resident：stage0 为 /sbin/launchd + /redwood 空挂点 + /dev /flash /Cryptexes；CRYPTEXES=flash = boot 卷独立（cryptex 不进 RAM） |
| **root.apfs** | 4,194,304 B（1024 块） | md1：init/sbin + etc/rc + etc/**var.skel**（112 行）+ LaunchDaemons + **ssh 密钥**（`~/hakios/kernel/ssh/` ← Wave17 `procursus-prep/ssh`，16 KB，经 build.sh var.skel f-行通道种子进 HFS+ 卷） |

工作区：`~/hakios/kernel/sysimage/`（build.sh 的 `DARWIN=../sysimage` = **kernel 树内**；首次误建 `~/hakios/sysimage` 致两段静默跳过，搬运合并修复）。**jb（155 MB）不进树**：flashboot /jb 嵌入会顶爆 payload 64 MB 窗口（23.4+155 MB ≫ 64 MB），SSH 数据面本不在本轮验收 → Wave 21 改走 system.apfs 侧 /jb（flash 卷承载零 RAM 成本，init.c `stat("/jb")` 换根后同路径可达）或扩窗。

### 3.2 darwin 前段灌卷（任务书授权范围内：darwin 分区内；数据卷区零触碰）

| 段 | 产物 | 起始块 | 块数 | 读回 sha |
|---|---|---|---|---|
| 容器 0 | system.apfs | **0** | 604,420 | `838729ec…` same |
| 容器 1 | cryptex-os.dmg（Apple 原像） | **604,420** | 665,600 | `2279bf44…` same |
| 容器 2 | cryptex-app.dmg | **1,270,020** | 2,560 | `6b9d1f09…` same |

每段：push → 手机端 sha 对拍 → 同 shell 内身份门（`readlink by-name/darwin = sda15` + `getsize64 = 21,474,816,000`）→ guarded dd（bs=4096 seek/count conv=notrunc,fsync）→ 读回 sha。写前 preflight：darwin 块 0 = 全零哈希 `ad7facb2…`、数据卷头 @2,042,368 = `33711438…`（P0 原值）。总写 5.2 GB 恰在前段只读区（≤1,272,580 < 2,042,368），收口于容器步进布局（容器 2 末 = 4961 MiB，dmesg 实证）。`wave18-scripts/darwin-front-write.sh` 全程留痕。

### 3.3 payload / 打包 / 自检

- `mkpayload.py` 六条目：loader.efi（66c6b342 提取件）/ kernel（a7f4641f）/ **resident**=flashboot.apfs / **ramdisk**=root.apfs / cmdline=v13 / kernel.ver（afd473f5 提取件）——23,377,520 B ≪ 64 MB 窗口。插曲：首版把 kernel.ver 条目插到终止条目之后（loader 解析不可见）→ 改为 mkpayload 原生 item 传入修复；自检堵住。
- 打包 → `udon-hakios-grafted-v13.img`（192 MiB，sha `465308f1…`）→ **verify-udon-hakios-v13.py 42/42 全绿**（FD 8924cb67 / shim 108ce972 / loader.efi / kernel.ver / kernel 字节等断言 + resident/ramdisk == 构建产物 + NXSB 魔数 + cmdline 预算）。
- 刷写一次通过（getvar taro ✓ / OKAY 4.85s+0.70s / set_active b / reboot）。

---

## 4. Boot #24（b24）判定（`intel/m3-boot1/b24-kernel-log.txt`，85.5 KB，含跨周期帧缓冲残页）

### 4.1 硬验收行（console，init run A 段）

```
=== init: process 1, started as /redwood/sbin/init ===

-- the Darwin root volume on /dev/ufs_darwin as the root --
[ ok ] mount the Darwin volume read only                                   ← system.apfs 容器 0 挂载 ✓
[ ok ] our launchd jobs, not Darwin's
[FAIL] a synthetic /redwood on it, for this image                          （File exists，良性）
  0 applications waiting to be installed, 0 of them in /Applications
[FAIL] the first boot's applications in /Applications                      （R-B6 兑现：20F66 无 staged_system_apps，非阻塞）
[ ok ] the Darwin volume is the root, the RAM part of the boot on /private/preboot    ← 换根 ✓
[ ok ] the OS cryptex (/dev/ufs_darwin,c=1) on /private/preboot/Cryptexes/OS          ← 容器步进 c=1 ✓（@2361 MB）
[ ok ] the App cryptex (/dev/ufs_darwin,c=2) on /private/preboot/Cryptexes/App        ← c=2 ✓（@4961 MB）
[ ok ] this image back on /redwood

-- writable filesystem --
  /private/var: HFS Plus from /dev/ufs_darwin_data, kept between boots    ← ★★ S6 验收行逐字到手 ★★
[ ok ] mount the data volume on /private/var
  112 directories, 22 files                                               ← ★★ S7 骨架（112 目录 + 22 文件）★★
[ ok ] create the directories of the data volume
```

### 4.2 逐步判定

| 步 | 判定 | 证据 |
|---|---|---|
| **S6** | ✅ | `  /private/var: HFS Plus from /dev/ufs_darwin_data, kept between boots`（init.c:859 逐字）；回落行 `a memory filesystem instead` 未出现在成功轮 |
| **S7** | ✅ | `112 directories, 22 files` + `[ ok ] create the directories of the data volume`（var.skel 112 目录行 + ssh 密钥等 22 文件种子进卷；`check(ok && made > 50)` 过） |
| **S8** | ✅ | 三重证据：①最后轮 dmesg **`jnl: ufs_darwin_data: replay_journal: from: 876544 to: 1048576` → `journal replay done.` → `hfs: mounted Data on device ufs_darwin_data`**（journal 里躺着上一轮的未落盘状态 = **跨 boot 状态直接物证**）；②console 另一轮 init 以 EEXIST 容忍语义重挂（`112 directories, 11 files`——骨架文件"卷上已有则跳过"路径）；③**数据卷全区域 sha `88c1cd99…`（P0 pristine）→ `6e40eaef…`**、卷头块 `33711438…` → `1e4cd367…`（安卓侧回读，内核经 S3 写路径真写了卷） |
| 真实 init | ✅ | stage0（md0 root 的 /sbin/launchd）→ 挂 md1 于 /redwood → `exec /redwood/sbin/init` → 上述全链 → rc → `exec /sbin/launchd.darwin` |
| **Apple launchd（超预期）** | 起了又亡 | console `Darwin Ignition Sequence Version 1.0.0`（launchd 真身 ignition 输出）→ dmesg `shared_region: … [4(hello_dyn)] check_np`（**dyld 共享缓存从 cryptex 容器加载，动态二进制 hello_dyn 真跑**）→ t=38.17 `pid 1 exited -- exit reason namespace 35 subcode 0x6, description failed to query hardware target: 22` → `panic: initproc failed to start` → stackshot → 返回。**Wave 20 第一定位点**（launchd 硬件目标查询 EINVAL = 内核缺某 sysctl/hostinfo 语义，R-B1 类） |
| loader_return | 未行使 | 最后轮 panic 路径（不走近返回），循环节奏 = panic 循环 ~45 s/轮，300 s 后 ABL 兜底回安卓（F4） |

### 4.3 console forensics 注记（如实记录，不影响判定）

logdump 的 console 段为**帧缓冲滚动环跨周期残留**：可见两个 init 段（A=成功 22 文件；B=`mount /dev/ufs_darwin: No such file or directory` + HFS `Resource busy` → ramfs 回落 11 文件）+ 最后轮 dmesg（switch_root/HFS 全成功）。段间无内核重启行，归属与环覆盖机制待 Wave 20 专查（F3）；**判定以最后轮 dmesg（内核缓冲，权威）+ 物理卷 sha 为准**——两者互相印证全链成功。loader_return_after 未打出行、stub 心跳绝迹（新链无 stub）为交叉旁证。

---

## 5. 风险登记（本波行使结果）

| # | 结果 |
|---|---|
| R1 | **清白**（b23 FNV 16/16；b24 的 5 GB 级读——换根/骨架/dyld cache——零数据错） |
| R2 stale logdump | 未发生（85 KB 完整 + END OF LOG 在位；帧缓冲跨周期残留 = 新注记 F3，非失效） |
| R5 flush 真落盘 | **兑现**：journal replay 机制真机工作，掉电/panic 后卷完好挂载 |
| R-B3 cryptex flash 回落 | 未触发回落——`/dev/ufs_darwin,c=1/c=2` 一次命中（容器步进布局与灌卷逐块吻合） |
| R-B4 dyld cache | 兑现：hello_dyn 经共享缓存跑通 |
| R-B6 staged_system_apps | 兑现为 FAIL（0 apps）——非阻塞， Wave 20 可离线预置 |
| R-B1 launchd 兼容性 | **部分兑现**：launchd 起但 0.6 s 内退（hardware target EINVAL）——Wave 20 主事项 |
| panic 循环回安卓 | ~300 s（比 60 s×8 慢循环快；panic 路径安全网行为正常） |

---

## 6. Wave 20 剩余清单（真实 launchd 收官）

1. **launchd `failed to query hardware target: 22`**：定位 launchd 硬件目标查询（sysctl/hostinfo 路径）在本内核的 EINVAL 缺口并补齐（对照 upstream redwood 内核树 kern_hvg/pe 相关实现）；或过渡方案 = 换 rc 不交接 launchd（init 自己跑场景作业）先解 SSH。
2. **/jb 接线**：155 MB 前缀嵌 system.apfs 侧 /jb（flash 卷承载）+ build.sh flashboot 侧 1 行守卫（../jb 存在但 FLASHBOOT=1 时跳过 flashboot 嵌入），或扩 payload 窗（需动 shim = 升级审批）。
3. **console forensics F3**：帧缓冲滚动环跨周期残留机制专查（logdump console 段的周期归属标注）。
4. **SSH 数据面 = Wave 21 loader 桥接网络**（Wave19-prep 方案 A 三端）；sshd 由 rc.jobs.ssh 起，密钥已在卷上。
5. 可选：`staged_system_apps` 离线预置消掉 b24 的一个 [FAIL]（美观项）。

---

## 7. 交付物清单（Windows 侧只新增）

| 文件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-grafted-v13.img` | `465308f1f79fb1a5` | **当前在 boot_b**（Boot #24）；192 MiB；自检 42/42 |
| `device-layer/udon-hakios-grafted-v13.report.json` | — | 打包报告 |
| `device-layer/udon-hakios-payload-v13.bin` | `c1788f75eb6b24f2` | 六条目 XNUP（loader.efi/kernel/resident/ramdisk/cmdline/kernel.ver），23,377,520 B |
| `device-layer/udon-hakios-cmdline-v13.bin` | `176da1e2f900d911` | v12 字节 + ` root_apfs=ufs_darwin`（449 B，预算 516<608） |
| `device-layer/udon-hakios-grafted-v12.img` | `d07b2e273eb01ca3` | Boot #23（UFS S3-S5 版，v12 四件套含 payload `9731218e…` / cmdline `da84466f…` 428 B） |
| `logdump-v12.bin` / `logdump-v13.bin` | `d634edef4b61f41a` / `49beeb2ec26da59b` | Boot #23/#24 logdump（131,072 B） |
| `intel/m3-boot1/b23-kernel-log.txt` / `b24-kernel-log.txt` | `a08a044c76218af4` / `f9ff3390816a9ce1` | 内核日志提取件（28,526 B / 91,957 B） |
| `intel/fnv-baseline/`（16 文件） | — | R1 对拍基线（8 参考分区 × a/b，adb 第三可信路径） |
| `wave18-scripts/` | — | make-cmdline-v12/v13、repack-payload-v12、verify-udon-hakios-v12（46 检）/v13（42 检）、strings-check、flash-b23/b24、wait-android、pull-logdump、fnv-baseline、fnv-compare、recon×7、setup-sysimage、build-v13-userland、kernel-v13-check、make-payload-v13、darwin-front-write、front-preflight、b24-postmortem |
| WSL kernel 树（叠加未提交） | — | `phk110.config` +4 行（UFS_WRITE/VAR_STORE/ROOT_APFS/VAR_HFS）；`sysimage/` 硬链接工作区 + `ssh/` 密钥目录；userland 三镜像构建产物；kernel 字节三轮验证不变（`a7f4641f…`） |

---

## 8. 红线遵守

- 只刷 boot_b（每刷各一条 fastboot flash boot_b；无其他分区/oem/wipe/erase）✅
- darwin 之外零分区写入；darwin 内写入 = 授权范围（前段容器 0..1,272,580 + 数据卷由内核经 S3 写路径写入）；数据卷区起始 2,042,368 的 P0 布局未动（卷头仍 `HX`/Data 卷名，内核更新为其挂载写）✅
- 禁 git reset/checkout/stash/clean、不 commit ✅（Windows 仓改动 = 新增文件 + STATUS.md 编辑；kernel 树 = config 4 行叠加 + 新目录）
- Windows device-layer 只新增 ✅
- 失败重试：payload 条目序 bug 与 sysimage 路径误建均**首检即抓、原地修复**，刷写/灌卷零失败零重试 ✅
- 手机临时文件已清（w18seg.bin/w18ld.bin/w18gpt.bin）；回安卓 slot a 在线、/data 数据面无损 ✅
