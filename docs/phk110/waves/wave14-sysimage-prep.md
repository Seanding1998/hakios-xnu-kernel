# 阶段 14 · 2026-11-03 · 用户空间准备：iOS 16.5（20F66）镜像解包与盘点

> 2026-11-03 · 纯 WSL 工作（零手机交互、零刷写）· 执行记录产出
> 输入：`~/hakios/ipsw/iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw`（6,165,698,198 B，sha256 `c1091c40…` 已验证，只读未动）
> 产物根：**`~/hakios/sysimage-20F66/`**（WSL，kernel 树外新目录，`~/hakios/kernel` 全程只读未写）

---

## 0. 执行摘要

| 项 | 结论 |
|---|---|
| 磁盘 | 解包前 930G 可用 → 解包后 917G 可用（本阶段净耗 ~13G），**充足** |
| 解包 | upstream `sysimage/unpack.sh` 链 **EXIT=0 跑通**，产物齐全且通过脚本内建校验（43 文件 dyld cache 完整、零残留 decmpfs 压缩、App cryptex 完整性哨兵 `webbookmarksd` 在位）|
| 切片 | **抽查全部 arm64（cputype 0x0100000C / subtype 0），零 arm64e** ✅ |
| sshd | iOS 系统镜像**确认无** sshd/dropbear/launchctl/sh/ls/reboot —— upstream 解法 = **Procursus rootless bootstrap（openssh-server）+ `rc.jobs.ssh`**，明确记录 |
| HFS+ | v0.4 data volume 命令链已实测跑通（12GB 模板已建好），且 **fork 的 `userland/src/init.c` 已内建 `var_hfs=DEV` 挂载支持** |
| QEMU 对照 | 按红线跳过（全链会写 kernel 树产物，阶段 12a 并行中）；以 unpack 内建校验 + HFS+ 实物模板替代自洽验证 |

---

## 1. 磁盘检查

```
WSL /（/dev/sdd，ext4 虚拟盘）: 1007G 总量
解包前：27G 已用 / 930G 可用（3%）
解包后：39G 已用 / 917G 可用（5%）
```

脚本预估（运行中 ~8GB，完成后 5.3GB）实际为 13GB（KEEP=1 保留了 4.7G rootfs.dmg + 2.6G cryptex-os.dmg 两张 dmg 以便后续改 select-system.py 时免重读 IPSW）。余量无压力。

## 2. 工具链（WSL 侧全部现成/已补装）

| 工具 | 状态 | 用途 |
|---|---|---|
| python3 3.14.8 | ✅ 现成 | `ipsw-member.py`（zipfile 流式抽取 dmg，不解整个 IPSW）、select/mkvarskel |
| 7-Zip 25.01 | ✅ 现成 | 读 APFS 卷并解出 rootfs/cryptex（需 ≥23，已满足）|
| gcc (cc) 16.0.1 | ✅ 现成 | 未用到（unzbm 已有预编译产物）|
| **unzbm** | ✅ 复用 `kernel/xnu-deps/host/bin/unzbm`（只读引用） | 解 7z 留下的 LZBITMAP（com.apple.decmpfs）文件 |
| **hfsplus-tools 540.1** | ✅ **本阶段新装**（`dnf install hfsplus-tools`，走 127.0.0.1:7897 代理）| `mkfs.hfsplus` 建 HFS+ data volume |
| lz4 1.10.0 | ✅ 本阶段新装 | upstream qemu 文档列的依赖（后续阶段用）|
| qemu-system-aarch64 | ✅ 现成 | 对照实验备用（未跑，见 §8）|

## 3. 解包命令链（含踩坑记录）

### 3.1 脚本理解（`kernel/sysimage/unpack.sh`，只读参考）

它不做 pzb/xar/yaa、**不做 dmg 解密**——iPhone X 时代的 IPSW 里 dmg 成员本身就是 zip 成员且未加密（AES 卷密钥体系是 newerSoC 的）。链路：

1. `ipsw-member.py IPSW <member> out` —— Python `zipfile` 从 IPSW（ZIP64）**流式**抽 3 个 dmg 成员 + DeviceTree（4.7GB rootfs dmg 不占内存）：
   - `096-04088-077.dmg` = rootfs（APFS，4,728,546,953 B）
   - `096-04666-078.dmg` = OS cryptex（2,726,297,600 B）
   - `096-03536-083.dmg` = App cryptex（10,485,760 B）
2. `7z l -slt rootfs.dmg` 技术清单 → `select-system.py` 选出 **43,230 文件 / 2,881 MB**（manifest 59,644 条目，保留 owner/mode/symlink）→ `mkvarskel.py` 生成 `/private/var` 骨架
3. `7z x` 批量解出 → `font_trim.py` 现场裁两个巨型字体（emoji 130→59MB，PingFang 74→26MB）
4. cryptex 同法解出，dyld shared cache 单独搬到 `20F66__iPhone10,3_6/`（43 文件校验），`.symbols`（0.6GB）有意丢弃
5. 7z 解不动的 LZBITMAP 文件由 `unzbm` 补刀，最后校验零残留

### 3.2 独立运行布局（红线适配）

脚本设计为在 `kernel/sysimage/` 内运行并向 `../xnu-deps`、`../tools` 写/读。为不污染 kernel 树（阶段 12a 并行构建中），复制脚本到新目录、symlink 只读依赖到上一级：

```
~/hakios/sysimage-20F66/
├── work/                        # 运行目录（脚本副本 + 全部解包产物）
│   ├── unpack.sh, ipsw-member.py, select-system.py, mkvarskel.py   # kernel 树副本
│   └── <全部产物，见 §4>
├── xnu-deps -> ~/hakios/kernel/xnu-deps    # symlink：../xnu-deps/host/bin/unzbm 只读解析
├── tools -> ~/hakios/kernel/tools          # symlink：../tools/font_trim.py 只读执行
├── var-hfs-data.img           # v0.4 HFS+ data volume 模板（12G sparse，实际占 36M）
└── WAVE14-NOTES.md            # 本阶段运行记录
```

**踩坑（已修复）**：首次运行失败——symlink 建在了 `work/` 里，而脚本引用 `../xnu-deps`（相对脚本所在目录的**上一级**）；`[ ! -x ../xnu-deps/host/bin/unzbm ]` 为真触发重编译，`cc` 在 `sysimage-20F66/xnu-deps/` 下误建目录树。修复 = symlink 移到上级 + `rm -rf` 误建目录 + 重跑 EXIT=0。kernel 树未被写入（`ls -la` 事后核验 `xnu-deps/` 全部文件时间戳仍为 Nov 2）。

### 3.3 复现命令

```bash
cd ~/hakios/sysimage-20F66/work
KEEP=1 bash unpack.sh ~/hakios/ipsw/iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw
# 幂等：.done-rootfs / .done-cryptex / .done-cryptex-app 标记 + KEEP=1 留 dmg，重跑秒过
```

## 4. 产物清单（`~/hakios/sysimage-20F66/work/`）

| 产物 | 路径 | 大小 | 内容/说明 |
|---|---|---|---|
| **rootfs 树** | `work/rootfs/` | 2.9G（43,230 文件） | 顶层：`Applications/ bin/ Library/ private/ sbin/ System/ usr/` |
| 选择清单 | `work/system.files` | 3.9MB（43,230 行） | 7z 批量解压清单 |
| **系统清单** | `work/system.manifest` | 5.9MB（59,644 条目） | `mode(uid gid) path [linktarget]` 制表符分隔——mkapfs.py 建镜像直接吃 |
| **/private/var 骨架** | `work/var.skel` | 4.8KB（112 行） | `d mode uid gid path` / `l target path`——init 每次启动重建（v0.4 HFS+ 卷首装种子） |
| **dyld shared cache** | `work/20F66__iPhone10,3_6/` | 2.6G（43 文件） | 主文件 + `.01`–`.42` subcache（含 2×`.dylddata`、2×`.dyldlinkedit`），**无 `.develop` 变体、无 `.symbols`**（IPSW 只带 release cache；.symbols 0.6G 被 unpack.sh 有意丢弃——永不映射） |
| OS cryptex 树 | `work/cryptex/` | 26M | System/Library/{Frameworks 6.6M, PrivateFrameworks, CoreServices, Caches, Accounts} + usr/lib（libstdc++、libobjc-trampolines、swift/ 等 5 dylib）——16.5 **确有 OS cryptex 结构** |
| App cryptex | `work/cryptex-app/` + `.dmg` | 11M + 10M | Safari 守护进程束（webbookmarksd、safarifetcherd、webinspectord…）；`.dmg` 原样保留（FLASHBOOT=1 路径直接内存驻留） |
| cryptex-os dmg | `work/cryptex-os.dmg` | 2.6G | KEEP=1 保留（改 select-system 后免重读 IPSW） |
| rootfs dmg | `work/rootfs.dmg` | 4.5G | 同上 |
| 设备树 | `work/DeviceTree.d22ap.im4p` | 33,694 B | d22ap = iPhone10,3（iPhone X），供 `xnuloader/mkidentity.sh` |
| **BuildManifest** | `work/BuildManifest.plist` | 449,650 B | 本阶段从 IPSW 补抽（元数据记录用） |
| **trust cache ×3** | `work/096-*.dmg.trustcache` | 66,265 / 1,511 / 767 B | 分别对应 rootfs / OS cryptex / App cryptex 三卷的 CDHash 列表，本阶段从 IPSW `Firmware/` 补抽 |
| **HFS+ data volume 模板** | `~/hakios/sysimage-20F66/var-hfs-data.img` | 12G sparse（实占 36M） | `mkfs.hfsplus -s -J -U 0 -G 0 -M 755 -v Data`，8192k journal——UFS/挂载阶段可直接拿去灌 var.skel |

### 4.1 Mach-O 切片核查（magic + cputype/cpusubtype 逐文件读）

| 文件 | 大小 | 结果 |
|---|---|---|
| `rootfs/sbin/launchd` | 525,088 B | **MH_MAGIC_64 arm64 subtype=0** ✅ |
| `rootfs/usr/lib/dyld` | 922,912 B | MH_MAGIC_64 arm64 subtype=0 ✅ |
| `rootfs/bin/df`、`bin/ps` | 69,616 / 88,752 B | arm64 subtype=0 ✅（/bin 仅此两个） |
| `rootfs/sbin/{fsck,mount,mount_lifs,mount_nfs,umount}` | 71–92KB | arm64 subtype=0 ✅ |
| `rootfs/usr/sbin/{mediaserverd,wifid,ioreg,syslogd}` | 166KB–2.6MB | arm64 subtype=0 ✅ |
| `cryptex/usr/lib/libstdc++.6.dylib` | 819,568 B | arm64 subtype=0 ✅ |
| `…/hfs.fs/fsck_hfs` | 290,480 B | arm64 subtype=0 ✅ |
| `20F66__iPhone10,3_6/dyld_shared_cache_arm64` | 393,216 B | **"dyld v1  arm64"** cache header（非 Mach-O，格式正确）✅ |
| `dyld_shared_cache_arm64.42.dyldlinkedit` | 333,955,072 B | 同上 ✅ |

**零 arm64e（0x0200000C）命中**——与内核 xnu-8796.121.2 arm64 路线一致，无切片风险。

### 4.2 IPSW 元数据（91 个 zip 成员）

- `BuildManifest.plist`（449,650 B）已入库
- Trust cache 按 dmg 卷组织于 `Firmware/`：rootfs 66KB、OS cryptex 1.5KB、App cryptex 767B（+2 个未识别卷 5.7KB×2），3 个主卷的已补抽入库
- **无 RestoreOctagon**（iPhone X / A11 无 Octagon 结构，确认）
- 无独立 SystemOS 卷镜像（16.5 的"SystemOS"角色由 OS cryptex dmg 承担，rootfs.dmg 仍是传统完整根文件系统——**"16.5 应该还是传统 sysimg"的疑问答案是：两者并存**：完整 rootfs + 16.4 引入的 cryptex 结构）

## 5. 缺失项与 upstream 解法（报告核心结论）

### 5.1 iOS 系统镜像里没有的东西（逐一确认）

| 缺失 | 证据 | upstream 解法 |
|---|---|---|
| **sshd / dropbear** | `find rootfs cryptex* -iname '*ssh*' -o -iname '*dropbear*'` 仅误命中 shortcutssharing | **Procursus rootless bootstrap 里的 OpenSSH server**：`tools/mk-jb.sh` 从 `https://apt.procurs.us` 取 `bootstraps/1800/bootstrap-iphoneos-arm64.tar.zst`（+ Sileo deb），解出 `jb/root/var/jb` 前缀（~124MB）；`userland/build.sh` 把它放进镜像 `/jb`，init 每次启动嫁接到 `/private/var/jb`（`userland/src/init.c:985-1034`）。**dropbear 被明确否决**：其 Procursus 包依赖 libtomcrypt1/libtommath1，仓库任何套件都没有（`rc.jobs.ssh:7-8` 注释）|
| SSH 启动方式 | — | `userland/rc.jobs.ssh:18`：`/var/jb/usr/sbin/sshd -D -e -h /var/root/.ssh/ssh_host_ed25519_key -o UsePAM=no -o PasswordAuthentication=no -o PermitRootLogin=prohibit-password -o AuthorizedKeysFile=/var/root/.ssh/authorized_keys &`。host key **在主机侧生成随镜像走**（手机上 ssh-keygen 会问 uid 0 是谁——经 libiosexec，由 init 嫁接前缀时答）。RC_JOBS=rc.jobs.ssh + `wifi=1` 进 XL_CMDLINE |
| **sh / ls / reboot / cp / mv / rm / mkdir / cat** | `rootfs.slt` 全镜像 grep 零命中；`/bin` 实测仅 df+ps（2 个文件）；`/usr/bin` 仅 23 个诊断工具 | 同样来自 Procursus 前缀 `/var/jb/bin`（`init.c:208-217`：init 把前缀的 sh/mv/cp/rm/mkdir/chmod 符号链接叠进 /bin，SILEO_BIN 机制）。**Shell 的正确预期 = `/var/jb/bin/sh`，不是 /bin/sh**（`build.sh` 头注释：`/bin/sh` 在 16.5 rootfs 上 status 127）|
| **launchctl** | rootfs.slt + cryptex-os.dmg 全 grep 零命中 | launchd job 加载走 **init/rc 机制**（`stage0.c` 作 `/sbin/launchd` 引导，真 launchd 改名 `/sbin/launchd.darwin`；JOBS/REST 环境由 `mkjobs.py` 编进 rc）；如需 launchctl 本体，Procursus 前缀有 |
| **独立 TrustCache 文件** | rootfs/ 全树 find 零命中（镜像内 /usr/standalone 仅 44 条目且为 firmware，被 select-system 有意排除）| iOS 16 静态信任链编在 **kernelcache 内**（不在 rootfs）。本项目路线 = `cs_enforcement_disable=1` + miniamfi 式 stub，**不消费 trust cache**；已入库的 3 个 `.trustcache`（CDHash 列表）仅作审计参考。若后续要走 AMFI 正门，可用 `xnu-deps/host/bin/tcnorm` 类工具（upstream codesign 工具链在 host/bin 有 codesign/ld64/otool 全套）|

### 5.2 upstream 的 Sileo/Procursus 生态（CHANGELOG 情报的落实）

`docs/ru/notes.md` §"Sileo и пакеты"（683-779 行）：upstream 实机已跑通 Sileo 2.5.1 + dpkg + apt（rootless 前缀 `/var/jb`），含 setuid 位还原清单（login/su/sudo/passwd/chpass/newgrp/quota + Sileo 的 giveMeRoot 4755）、sileolists 目录、`/bin` 五链接等嫁接细节全部在 `init.c` 与 `mk-jb.sh`。**对本项目的意义：SSH shell 不需要自己编译任何东西，`mk-jb.sh` + `rc.jobs.ssh` 是现成链**。注意 `mk-jb.sh` 需要网络（走 7897 代理）+ `zstd`（WSL 需确认，构建阶段装）。

## 6. v0.4 接线清单（后续阶段拿来即用）

### 直接可用（零改动）
1. **launchd**：`work/rootfs/sbin/launchd`（arm64）→ build.sh 链自动改名 `/sbin/launchd.darwin` 并以 stage0 引导
2. **dyld shared cache**：`work/20F66__iPhone10,3_6/`（43 文件）→ build.sh 原样放进 system image
3. **rootfs 全树 + manifest**：`work/rootfs/` + `work/system.manifest` → `userland/build.sh` 直接消费（它 cd 到 kernel 树内运行；产物落 kernel/userland/——**运行时机由后续阶段与 阶段 12a 协调，勿并行跑**）
4. **App cryptex dmg**：`work/cryptex-app.dmg` 原样内存驻留路径（FLASHBOOT=1）
5. **HFS+ data volume**：`~/hakios/sysimage-20F66/var-hfs-data.img`（12G 已格式化）或自建（§6.1）；内容种子 = `work/var.skel`（112 行，init 语义）
6. **DeviceTree**：`work/DeviceTree.d22ap.im4p` → `xnuloader/mkidentity.sh`

### 缺、需构建/取数
1. **sshd**：跑 `tools/mk-jb.sh`（网络+zstd）生成 `jb/` 前缀 → build.sh JB=1 镜像；**或**单取 openssh-server 包最小化灌入 /var（后续 SSH 阶段决策）
2. **host key**：主机侧 `ssh-keygen -t ed25519 -f ssh_host_ed25519_key -N ''` 随镜像走（rc.jobs.ssh 硬编码路径）
3. **PHK110 侧缺口**（非本阶段）：UFS transport、SMMU/DMA、`ufs_darwin_data` 分区定位（init.c `var_hfs=DEV` 期待 `/dev/ufs_darwin_data` 节点 = darwin 卷 + cryptex 之后的分区）

### 需要构建的工具（命令已验证）
**v0.4 12GB HFS+ data volume 创建**（本阶段实测）：
```bash
dnf install -y hfsplus-tools          # 已装（540.1）
truncate -s 12G var-hfs-data.img
mkfs.hfsplus -s -J -U 0 -G 0 -M 755 -v Data var-hfs-data.img
#   -s  = case-sensitive（HFSX；内核 hfs-627.100.6 两种都挂）
#   -J  = journaling（掉电安全；内核 var_kept 语义期待可写日志卷）
#   -U/-G/-M = root:wheel 0755 卷根；-v Data = 卷名
```
上游参照：`kernel/qemu/run-hfs-test.sh`（256MB QEMU 验证链：hfs_test.c 作 init，virtio-blk，跑两轮验持久性）；**fork 的 `userland/src/init.c:825-860` 已内建 `mount_data_volume()`**——boot-arg `var_hfs=DEV` → `mount("hfs", "/private/var", 0, &hfs_mount_args{fspec=/dev/DEV})`，失败自动回落内存盘并打印原因。挂载时 init 用 `var.skel` 重建目录骨架。

### 与内核/安全方案的衔接
- 全部用户态二进制 arm64 纯色 → 无 arm64e 分支风险
- trust cache 不消费（cs_enforcement_disable=1 + miniamfi stub 路线）→ 代码签名豁免由内核侧解决
- 磁盘布局对齐 `init.c` 注释：`ufs_darwin_data` = darwin 卷与 cryptexes 之后的 UFS 分区

## 7. QEMU 对照实验：跳过说明（可选加分项未取）

`docs/getting-started/qemu.md` 的 M1 验收链 = `REST=1 userland/build.sh` → `make loader` → `qemu/run-darwin.sh`（x86 TCG 约 20 分钟/会话）。**跳过原因**：①`build.sh`/`make loader` 均在 kernel 树内产出镜像/loader.efi，与 阶段 12a 并行构建冲突（红线：kernel 树只读）；②需要完整 edk2/Mu 构建链与 7GB 客户机内存。**替代的自洽验证已完成**：unpack.sh EXIT=0 + 三段内建校验（dyld cache 43 文件计数、decmpfs 零残留、App cryptex 哨兵文件）+ §4.1 切片核查 + §6 HFS+ 实物模板。WSL 已具备 qemu-system-aarch64，后续阶段跑全链无工具障碍。

## 8. 磁盘占用账目

| 项 | 大小 |
|---|---|
| `~/hakios/sysimage-20F66/` 总计 | **13G** |
| — work/rootfs | 2.9G |
| — work/20F66__iPhone10,3_6（dyld cache） | 2.6G |
| — work/rootfs.dmg（KEEP） | 4.5G |
| — work/cryptex-os.dmg（KEEP） | 2.6G |
| — work/cryptex + cryptex-app（树+dmg） | ~47M |
| — var-hfs-data.img（sparse） | 36M 实占 |
| 其余（清单/日志/脚本/DeviceTree/BuildManifest/trustcache） | <25M |
| WSL 盘余量 | 917G 可用 |

## 9. 红线遵守

- 手机：零 adb/fastboot/usbipd 调用，零刷写 ✅
- `~/hakios/kernel`：只读（唯一写风险点 unzbm 重编译未触发——symlink 修复后脚本消费已预编译二进制）✅
- IPSW：只读（zipfile 流式读，无写句柄）✅
- Windows 侧仓库：仅新增 `docs/waves/wave14-sysimage-prep.md` + STATUS.md 队列行更新（任务授权交付物）✅
