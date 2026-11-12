# 阶段 20 · 2026-11-08 · launchd 存活：hw.target 修复与 /jb 前缀接线

> 2026-11-08 · 执行记录 · 全循环：根因 → 双修复（内核 boot-arg + loader 真身份）→ /jb 接线 → 三镜像 → 双通道刷写 → b25 取证 → **判定阶梯三级全过，v0.4 用户态全绿**
> 核心结论：**Apple launchd 真身不再死**——`hardware target : d22ap` 被接受，launchd 域完整跑起来（SpringBoard/backboardd/sshd 等 28 个进程），**sshd 监听 0.0.0.0:22（pid 40）**，零 panic 会话 120 s 后 PSCI 干净返回。SSH 登录本身（网络三端）= 阶段 21。

## 0. 一句话

b24 死亡点（`failed to query hardware target: 22`，0.6 s 退场）已定位根因并双修复：内核 `hw.target` sysctl 的 EINVAL（`kern_mib.c` `PEGetTargetName` false→EINVAL）由 **hw_target boot-arg fallback**（kern_mib 补丁）与 **loader 真身份**（mkidentity.sh 从 `DeviceTree.d22ap.im4p` 重生成 identity.h，替代 v6 占位身份）双层封堵；Procursus /jb（130 MB）按 阶段 18 预案落 system.apfs（flashboot 守卫 1 行），b25 会话里 **/jb → /var/jb 嫁接 439 目录 / 6,416 文件、sshd 起来并监听 ：22**。

## 1. 根因链（文件:行号级，全部本仓库/本地取证）

死亡串 `failed to query hardware target: 22`（errno 22 = EINVAL）**不在 launchd 本体**，在 dyld 内嵌的 libignition（20F66 `usr/lib/dyld` strings + 反汇编实证）：

1. **dyld 侧**（`usr/lib/dyld` `_configuration_init` @0x60abc，llvm-objdump 反汇编）：
   - `sysctlbyname("security.mac.img4.ignition_blob")` → 容忍 ENOENT（缺省继续）
   - `sysctlbyname("hw.osenvironment")` → 容忍 errno 1/2/22
   - `sysctlbyname("hw.target", buf, &256)` → **errno 容忍表：0/无→"x86legacyap"，1(EPERM)→"unknownap"，2(ENOENT)→"x86legacyap"，其余（含 22/EINVAL）→ `ignition_halt`**（0x611cc → "failed to query hardware target: %d" @0x7b4d5）= b24 的死因
2. **内核侧**：`bsd/kern/kern_mib.c:999` `SYSCTL_PROC(_hw, HW_TARGET, target, …sysctl_hw_generic)`；`kern_mib.c:502-508`：
   ```c
   case HW_TARGET:
       if (!PEGetTargetName(dummy, 64)) return EINVAL;   // ← errno 22 的出处
   ```
3. **PEGetTargetName**（`iokit/Kernel/IOPlatformExpert.cpp:944`）→ `gIOPlatform->getTargetName()`；arm64 下 `IODTPlatformExpert::getTargetName`（:1813）转调 `getModelName` = 读 **loader 交进来的设备树的根节点 `model` 属性**。
4. **为什么 model 缺失**：机上 loader.efi = v6 时代构建，其 `xnuloader/identity.h` 是 `mkidentity.sh --placeholder` 占位版（实证：`identity_root[] = { { "hakios-placeholder", 0, 0 } }`，无任何 Apple 身份属性）→ 内核侧 `GenericARMPE: platform "device-tree"`（b24 L1147，平台专家在跑）但树里无 `model` → `getModelName` false → EINVAL。与生态审计波（`docs/research/landscape-2026-11-08.md`）独立会诊，结论一致，两案合并。
5. b24 佐证：panic dump `Hardware Model: Not set yet`（`pe_init.c:433` 的 `gModelTypeBuffer` 同样读不到树属性）。

## 2. 修复（双层，均最小改动）

### 2.1 内核：hw_target boot-arg fallback（首选层，b25 实际生效层）

`bsd/kern/kern_mib.c` case HW_TARGET（+10 行注释 +4 行代码）：

```c
if (!PEGetTargetName(dummy, 64)) {
    /* HakiOS: ... launchd/libignition dies on the EINVAL ... */
    if (!PE_parse_boot_argn("hw_target", dummy, sizeof(dummy))) {
        return ENOENT;   /* dyld then falls back to its own "x86legacyap" */
    }
}
```

- 登记：`configs/boot-args.lst` +1 行（`hw_target	k`，haptic_effect 与 hv_wdt_pet 之间保序）；`docs/boot-args.md` +1 行。
- 无 boot-arg 时返 **ENOENT**（dyld 自带 "x86legacyap" 缺省），不再 EINVAL——即不加任何 cmdline 的树也对 launchd 无毒。
- 产物：内核重编 v14，sha `883e99e7…`（v13 = `a7f4641f…` 不变断言取消——**v11 以来首次内核字节变化**，14,920,640 B 与 v11 同长）。

### 2.2 loader：真身份重建（生态审计采纳件，防复发层）

- `xnuloader/mkidentity.sh ~/hakios/sysimage-20F66/work/DeviceTree.d22ap.im4p` → `identity.h` 8,274 B：根节点 6 属性（**target-type "D22"、manufacturer "Apple Inc."、target-sub-type "D22AP"、compatible "D22AP/iPhone10,3/AppleARM"、model "iPhone10,3"、device_type "bootrom"**）+ /product 61 属性等。
- lzfse 解码器缺失 → 自建（github.com/lzfse/lzfse BSD → `xnu-deps/host/bin/lzfse`）。
- loader.efi 重编（`PAYLOAD_BASE=0xF4000000`，与机上在用件同参；loader.c 自 2026-11-03 16:48 未变）：`66c6b342…`（67,584 B）→ **`7ba818d2…`（72,192 B）**，D22AP/iPhone10,3/target-type 字符串入体，RAMDisk1/双 ramdisk 支持串保留。
- `xnu/export.sh` 重产 `xnu/hakios.patch`（diff 验证 = 仅 kern_mib 新 hunk + s3910 config 行补登[树内既有态]）。

### 2.3 /jb 接线（阶段 17 物料执行 + 阶段 18 预案守卫）

- `~/hakios/procursus-prep/jb`（130 MB rootless，openssh 9.7p1）→ `~/hakios/kernel/jb`（build.sh 期望布局 `../jb/root/var/jb`）。
- **flashboot 侧守卫 1 行**（阶段 18 预案）：`userland/build.sh:559` 的 jb 嵌入从 `[ -d ../jb/root/var/jb ]` 改为 `[ -d ../jb/root/var/jb ] && [ -n "$FLASHBOOT_JB" ]`——前缀只进 system.apfs，resident ramdisk 保持 4 MB，payload 64 MB 窗无虞（实际 23.4 MB）。
- 构建：`RC_JOBS=rc.jobs.ssh FLASHBOOT=1 CRYPTEXES=flash SYSTEM=1 userland/build.sh` →
  - `system.apfs` **616,835 块**（2,526,556,160 B；v13 = 604,420）＝ /jb 130 MB 经 zlib 收进 +48,415 块；`/jb/.procursus_strapped`、`/jb/usr/sbin/sshd`（806,512 B）入卷实证（apfs verify.py clines）。
  - `flashboot.apfs`/`root.apfs` 各 1,024 块（root 含 `/etc/rc`=rc.launchd、`/etc/rc.jobs`=rc.jobs.ssh、`/etc/var.skel`、`/LaunchDaemons/com.hakios.demo.plist`）。

## 3. 构建与刷写记录

| 件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-grafted-v14.img` | `1932412a8d8d3737` | 192 MiB，boot_b 新件 |
| `device-layer/udon-hakios-payload-v14.bin` | `2eb817b68c048daa` | 六条目 23,382,128 B：loader.efi(**7ba818d2** 新)/kernel(**883e99e7** 新)/resident/ramdisk/cmdline(**454 B** v14)/kernel.ver(`afd473f5` 原件) |
| `device-layer/udon-hakios-cmdline-v14.bin` | — | 453 B + NUL：v13 字节 −`ufs_check=1` +`loader_return_after=120` +` hw_target=D22ap`；预算 521<608 |
| `device-layer/hakios-kernel-v14.bin` | `883e99e79a4bcc4b` | hw_target 内核 |
| `device-layer/udon-hakios-loader-v14.efi` | `7ba818d228bf41dd` | 真身份 loader |
| `device-layer/udon-hakios-system-apfs-v14.bin` | `93cca9b622ce0cba` | 616,835 块 /jb 版 |
| 自检 | **47/47 PASS** | `wave20-scripts/verify-udon-hakios-v14.py`（头/gzip/shim/FD/XNUP/cmdline/条目/graft 全断言） |

**darwin 前段三段写入**（`wave20-scripts/darwin-front-write-v14.sh`，WSL adb + `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037` 组合通道，写前范围门 = 末块 1,284,995 < 2,042,368 数据卷界）：

| 段 | 块位 | 块数 | 读回 sha |
|---|---|---|---|
| system.apfs @0 | 0 | 616,835 | `93cca9b622ce0cba…` same |
| cryptex-os.dmg @616,835 | 616,835 | 665,600 | `2279bf443856fcb6…` same |
| cryptex-app.dmg @1,282,435 | 1,282,435 | 2,560 | `6b9d1f09e9b181cd…` same |

写前 preflight：块 0 = v13 system NXSB 页 `6af642a2…`；数据卷头 @2,042,368 = **`1e4cd367…`（b24 后原值，红线未触碰）**。写后复验卷头不变。

**boot_b 刷写**：adb reboot bootloader → usbipd attach 2-2（18d1:d00d）→ WSL root fastboot：getvar product **taro** ✓ → flash boot_b Sending 4.854 s/Writing 0.545 s 全 OKAY → set_active b → reboot。（插曲：首次 getvar 经 usbipd 挂死，kill 重试即愈——通道已知脾气，非设备异常。）

## 4. Boot #25 判定（`intel/m3-boot1/b25-kernel-log.txt`，539,872 B，END OF LOG 完整）

| 判定阶梯 | 结果 | 证据 |
|---|---|---|
| 1. hardware-target 行消失 + launchd 越过死亡点 | ✅ | libignition 配置 dump **`hardware target : d22ap`**（boot-arg 值，dyld_tolower 小写化）；`exit reason` 行 **0 条**；`failed to query` 0 条；launchd syslog 2,000+ 行全时域流动（08:00:40→08:02:36） |
| 2. sshd 进程起来 | ✅ | `$ /var/jb/usr/sbin/sshd -D -e -h /var/root/.ssh/ssh_host_ed25519_key …`（rc.jobs.ssh 原句）→ **`tcp listen: [0.0.0.0:22<->0.0.0.0:0] process: sshd:40`** |
| 3. 零 panic 稳定会话 + S6-S8 回归 | ✅ | `panic(cpu…)` 0 条；会话跑满 120 s 窗（syslog 至 08:02:36 > 08:00:40+116 s）→ `--- loader_return_after expired ---` → **`psci: cpu 3 ends the system`** 干净返回 → END OF LOG；S6 `kept between boots` 逐字、S7 `112 directories, 22 files`、**`/var/jb from /jb, in /private/var/jb: 439 directories, 6416 files and links, users resolvable`**（Procursus 嫁接行）、数据卷继续被内核写（全卷 sha `6e40eaef…`→`ad2fcc0f…`、卷头 `1e4cd367…`→`d5910060…` = 存储栈跨会话存活，b24 同型先例） |
| 超预期 | ✅ | launchd 域内 **28 个进程**（pid 11-42）：**SpringBoard[12]**、backboardd[16]、notifyd/logd/syslogd/containermanagerd/mobilegestalt.xpc 等；com.hakios.demo [18] `service state: running`；MiniIOMobileFramebuffer 10 fps 稳定出帧至 153 s+；3 容器步进新布局命中（System 50,585 files @0 MB / cryptex **@2409 MB** / AppCryptex **@5009 MB**） |

- **hw.target 值 = d22ap（boot-arg 层生效）**：真身份 loader 已已刷入（D22AP/iPhone10,3 入树），但 `PEGetTargetName` 仍 false（IOKit registry 侧 `model` 属性路径未通，见 §5 F5）——双层防御按设计回退，boot-arg 为当前实际生效层。
- S8 注记：第二周期 init 报 `HFS Plus …: Resource busy`（devfs 哨兵 EEXIST 族，b24 已有同型语义）→ 该周期 /private/var 走内存盘，`/var/jb` 嫁接两周期都成功（439 目录/6,416 文件行两见）。
- 回安卓：ABL 回退自发（~20 min，多轮 120 s 会话），slot a 安卓在线、/data 无损、logdump 拉回（`logdump-v14.bin` 512 MB 分区全量，`ffc3e66d…`）。

## 5. 新发现/注记

- **F5（新）**：真身份 loader 刷入后 `PEGetTargetName` 仍走 boot-arg 层——IODTPlatformExpert::getModelName 读的是 IOKit registry provider 的 `model`，与 pe_init 的 SecureDT 根读法不同源；阶段 21+ 若要"树侧真值"需在 GenericARMPE 侧补齐（非阻塞，boot-arg 层已满足 launchd）。
- F3（沿登）：b25 console 环含双周期残页（L43 首周期 + L557 次周期 init 输出并存），周期归属法证仍挂账。
- usbipd fastboot 通道首次 getvar 挂死、kill 重试即愈（wave16c 卡死的"数据端点打死"仅在半途中断后出现；完整重启 bootloader 后通道健康）。
- WSL /tmp 在调用间可能被清（本阶段实测两次）——执行脚本一律落 /mnt/c 持久路径，`/tmp` 只作缓冲。

## 6. 交付清单

- `device-layer/udon-hakios-grafted-v14.img`（`1932412a…`）+ `udon-hakios-payload-v14.bin`（`2eb817b6…`）+ `udon-hakios-cmdline-v14.bin` + `hakios-kernel-v14.bin`（`883e99e7…`）+ `udon-hakios-loader-v14.efi`（`7ba818d2…`）+ `udon-hakios-system-apfs-v14.bin`（`93cca9b6…`，2.5 GB）+ `udon-hakios-grafted-v14.report.json`
- `intel/m3-boot1/b25-kernel-log.txt`（539,872 B，`logdump-v14.bin` 分区全量留根目录）
- `wave20-scripts/`：make-cmdline-v14.py、make-payload-v14.sh、verify-udon-hakios-v14.py（47 检）、graft、front-preflight-v14.sh、darwin-front-write-v14.sh、fastboot-flash-b25.sh、pull-b25-forensics.sh、extract-b25-log.py、wait-android-b25.sh、build-v14-userland.sh（tmp/ 工具件）
- 内核树（WSL，叠加未提交）：`kern_mib.c` HW_TARGET 补丁、`configs/boot-args.lst`/`docs/boot-args.md` hw_target 登记、`xnu/hakios.patch` 重产、`xnuloader/identity.h` 真身份、`userland/build.sh` flashboot jb 守卫、`jb/` 130 MB 物料、userland 三镜像产物
- 手机现状：**安卓在线（slot a，ABL 自发回退）**，boot_b = v14，darwin 前段 = v14 三段（读回全 same），数据卷 = 内核续写健康态

## 7. 交给阶段 21 的清单

1. **SSH 登录三端**（阶段 19-prep 方案 A）：loader 桥接网络（共享页 net 环 + en0 link 驱动 + loader `oem netrx/nettx`）+ 阶段 13 loader_talk.py 扩 ProxyCommand —— sshd 已监听 :22，只差数据面。
2. hw.target 树侧真值（F5）：GenericARMPE registry 侧补 `model` 属性，让 `PEGetTargetName` 主路径生效（boot-arg 层保留为回退）。
3. S8 二周期 `Resource busy`（F1 族语义）专查：init 二次挂 var 的哨兵清理。
4. F3 console 环跨周期残页归属法证。
5. `loader_return_after` 语义观察：b25 会话实际运行 >150 s（syslog 08:00:40→08:02:36，fb 帧到 153 s），expiry 行后才进 return 序列——若 阶段 21 需要长驻 SSH 会话，直接调该 boot-arg 即可，机制已被验证会兜住。
