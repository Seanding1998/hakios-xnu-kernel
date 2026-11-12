# 阶段 17 · 2026-11-03 · SSH 引导链机制备忘（sshd / 密钥 / libiosexec）

> 2026-11-04 · 纯 WSL + 网络（零手机交互、零内核树写入）· 执行记录产出
> 产物根：**`~/hakios/procursus-prep/`**（WSL 新目录）；报告仓库侧仅新增本文件
> 上游输入：`~/hakios/kernel/tools/mk-jb.sh`、`userland/build.sh`、`userland/src/init.c`、`userland/rc.jobs.ssh`（全程只读，脚本复制到产物根执行）

---

## 0. 执行摘要

| 项 | 结论 |
|---|---|
| **机制（使命 1）** | **不是** HFS+ 卷离线预置、**不是** init 从分区解包 tar、**不是** USB 安装。是 **构建期把 bootstrap 前缀离线预置进系统 APFS 镜像（`/jb`，只读）+ 设备侧 init 每次 boot 自动嫁接（graft）到 `/private/var/jb`**。HFS+ 数据卷只是嫁接地，唯一的"离线种子"是 ssh 密钥（经镜像内 `etc/var.skel` 通道，init 开机时种子进卷） |
| **下载核验（使命 2）** | `mk-jb.sh` 副本运行 **EXIT=0**：bootstrap `1800` 套件快照（20,792,571 B，sha256 `a99b39bb…`）+ 7 个 .deb 全部落 `jb/debs/`，sha256 全记录；前缀 `jb/root/var/jb` = **130M / 6,926 条目 / 70 包**；openssh-server **9.7p1-1**（仓库最新，已预置解包）；sshd 抽查 = 纯 **arm64**（cputype 0x0c000001 subtype 0，零 arm64e） |
| **预置落地（使命 3）** | 机制 = 系统镜像侧预置，HFS+ 离线写入**不需要也不可行**（WSL2 内核无 hfsplus 文件系统，实测记录见 §6）；`jb/` 与 `ssh/` 两个 build.sh 输入目录已就位，下一阶段拷入 kernel 树顶层跑一次 `RC_JOBS=rc.jobs.ssh userland/build.sh` 即完成全部接线 |
| **密钥（使命 4）** | host key（ed25519）+ 登录密钥对已生成于 `procursus-prep/{ssh,keys}/`，公钥/指纹见 §5 留档；`ssh/` 目录布局严格对齐 build.sh:392-403 的 `../ssh` 读取约定 |
| 磁盘 | 本阶段净耗 **~156M**（130M 前缀 + 26M debs + 密钥/日志），WSL 916G 可用，无压力 |
| 红线 | 零手机调用 ✅；kernel 树只读（脚本副本执行，ROOT 解析为 procursus-prep）✅；`var-hfs-data.img` 原件未动（仅 sparse 读复制）✅；下载全走 127.0.0.1:7897 ✅ |

---

## 1. 机制说明（带 文件:行号，使命 1 核心）

### 1.1 一句话

**bootstrap（/var/jb 前缀）随系统镜像走**：主机侧 `mk-jb.sh` 产出前缀树 → `build.sh` 把它塞进 system.apfs 的 `/jb`（只读）→ 设备侧 init（launchd 前身）每次 boot 把 `/jb` **嫁接**到 `/private/var/jb`（目录实建、文件变符号链接指向 `/jb` 孪生，四个顶层树真实拷贝）→ 场景作业 `rc.jobs.ssh` 起 sshd。**全程无任何"设备侧解包 tar"或"USB 安装"环节，无需要写 HFS+ 卷的离线步骤。**

### 1.2 主机侧：`tools/mk-jb.sh` 产出前缀树

`~/hakios/kernel/tools/mk-jb.sh`（239 行，本阶段复制到 `procursus-prep/tools/` 执行）：

- :17 `SUITE=1800`（rootless 发行套件名；:8-9 注释明确"1800 是发行名，不要求 Darwin userland 18"）
- :19 `MIRROR=https://apt.procurs.us`
- :27 下载 `bootstraps/1800/bootstrap-iphoneos-arm64.tar.zst`
- :32-33 `zstd -dc | tar -xf` 到 `jb/root/`，断言 `var/jb` 存在
- :38-44 **setuid/setgid 位还原**（普通用户解包会丢位：login/su/sudo/passwd/chpass/newgrp/quota）
- :46-68 Sileo .deb 叠加进前缀（ar x → data.tar 解包）；:59 `giveMeRoot` 4755；:64-68 dpkg status 登记"已安装"
- :80-99 ElleKit 0.4.5（ellekit.space）叠加 + MobileSubstrate/DynamicLibraries → TweakInject 链接
- :111 `PREINSTALL="debianutils launchctl preferenceloader openssh-server openssh-client openssh-sftp-server libssl3 libmd0"` —— **openssh 全家取自仓库最新版**（bootstrap 快照里没有 sshd，仓库版更新）
- :113-114 取 `Packages` 索引 → `tools/jb-preinstall.py`：解 deb data.tar（zst/lzma/其他交 tarfile）进前缀，**路径过滤只进 `var/jb/` 且防 `..`**（jb-preinstall.py:151-153），替换旧版文件（:157-158），dpkg status 旧条目替换/新条目追加（:165-171）
- :119-124 写 apt 源 `etc/apt/sources.list.d/procursus.sources`
- :132-134 写 `etc/apt/apt.conf.d/10redwood.conf`：`Acquire::https::CaInfo "/var/jb/etc/ssl/certs/cacert.pem"`（绕过本 port 不可用的 trustd，:126-130 注释）
- :141-158 删 `shshd` / `libkrw0` / `libdimentio0`（依赖 libkrw 插件，本 port 无内核写入通道，且 apt 因依赖不满足拒绝一切安装）
- :169-189 剥掉 `firmware` 依赖（Sileo 的索引自洽问题，2 处记录）
- :196-235 生成 `/var/jb/prep.sh`（每 boot 由 rc.jobs.sileo 跑：`usr/libexec/firmware` 登记 + uicache 注册 app + `pwd_mkdb` + 5 个 postinst）——**SSH 场景不跑它也无碍**（firmware 依赖已剥，见 §8 风险 6）

### 1.3 主机侧：`userland/build.sh` 消费前缀与密钥

`~/hakios/kernel/userland/build.sh`（692 行）：

- **系统镜像模式**（v0.4 路线）:650-665：`rm -rf sysroot/jb; cp -a ../jb/root/var/jb sysroot/jb` → `/jb` 进 system.apfs（mkapfs 只读镜像）；前缀的 .app 复制进 `sysroot/Applications`；`SILEO_BIN` 五命令链接进 `sysroot/bin`
- **flashboot 模式**（小 boot 卷）:559-567：`flashboot/jb` + 空目录 `flashboot/jb-rw`（init 在其上挂 ramfs 作可写副本）+ `flashboot/jb-bin`
- **ssh 密钥** :386-403：`[ -z "$SHARE" ] && [ -f ../ssh/authorized_keys ]` 时，把 `../ssh/{authorized_keys,ssh_host_ed25519_key,ssh_host_ed25519_key.pub}` 拷进镜像 `root/var/root/.ssh/`，并向 `root/etc/var.skel` 追加：
  - `d 700 0 0 /private/var/root/.ssh`（:394）
  - `f 600 0 0 /private/var/root/.ssh/<k> /var/root/.ssh/<k>`（:403，六字段：类型 mode uid gid 目标路径 镜像内源路径）
- **场景选择** :407：`cp ${RC_JOBS:-rc.jobs} root/etc/rc.jobs` —— `RC_JOBS=rc.jobs.ssh` 是构建期环境变量

### 1.4 设备侧：`userland/src/init.c` 嫁接钩子（fork 现成，无需新增代码）

`~/hakios/kernel/userland/src/init.c`（1,568 行；:1549 `mount_writable()` 在 main 调用）：

- :834-862 `mount_data_volume()`：boot-arg `var_hfs=DEV` → `mount("hfs", "/private/var", 0, &hfs_mount_args{fspec=/dev/DEV})`；失败打印原因并回落内存盘（`var_kept=0`）。**v0.4 的 HFS+ 数据卷挂载点**
- :922-963 **var.skel 处理 = 密钥/文件的"卷外→卷"通道**：逐行解析镜像内 `etc/var.skel`；`d` 行 mkdir（kept 卷容忍 EEXIST，:946-948）；**`f` 行从镜像 `in_image(f[5])` 拷到数据卷 `f[4]`，kept 卷上已存在则不覆盖**（:954-966）——ssh 密钥走此通道：卷上没有就种子（首 boot），有了就保留（host key 跨 boot 稳定；即使回落 ramfs，种子仍来自镜像，指纹也不漂移）
- :988-989 探测前缀源：`/jb`（系统镜像模式）或 `/private/preboot/jb`（flash 模式）
- :997-1003 kept 卷上先清掉上一次 boot 的 `/private/var/jb`（每次重新嫁接）
- :1010-1016 flash 模式：`/private/preboot/jb-rw` 挂 ramfs，`/private/var/jb` 为指向其 `procursus` 的符号链接（LaunchServices 只认 preboot 路径）
- :1018 `graft_tree(jb, to, 1, …)`（:721-780）：目录实建，文件/链接变符号链接指向 `/jb` 孪生；**`graft_copy = {Library, etc, var, tmp}` 四个顶层树经 `copy_tree`（:658-707）真实拷贝**（dpkg 库、apt 配置等"被覆写"的部分可写；114M 程序库留只读镜像共享，:640-656 注释详述此内存权衡）
- :1024-1041 `mobile(501)` 归属目录（Sileo 数据库等）
- :1049-1062 `/var/jb/usr/sbin/pwd_mkdb -p /var/jb/etc/master.passwd` → 生成 `/var/jb/etc/pwd.db`：libiosexec 的 `ie_getpwnam` 读它；**没有它 sshd 拒绝一切登录 "Invalid user root"**（:1036-1047 注释即此实测案例）
- :1067 打印 `/var/jb from /jb, in /private/var/jb: N directories, N files and links, users resolvable`

### 1.5 设备侧：`userland/rc.jobs.ssh` 起 sshd

`~/hakios/kernel/userland/rc.jobs.ssh`（24 行）：

- :18 `sshd -D -e -h /var/root/.ssh/ssh_host_ed25519_key -o UsePAM=no -o PasswordAuthentication=no -o PermitRootLogin=prohibit-password -o AuthorizedKeysFile=/var/root/.ssh/authorized_keys &`
  - **key-only 全在命令行**，前缀包里 sshd_config 的 `PermitRootLogin yes` 被覆盖，无需改文件
  - host key 路径 `/var/root/.ssh/`（数据卷），不是前缀内
- :9-12 host key 必须主机侧生成的原因：手机上 `ssh-keygen` 要问 uid 0 是谁（经 libiosexec → init 建的 pwd.db），首次 boot 有先有蛋问题
- :7-8 **dropbear 明确否决**：Procursus 的 dropbear 包依赖 libtomcrypt1/libtommath1，仓库任何套件都没有
- :24 `rwtouch wait 900`：sshd 存活窗口 15 分钟；`XL_SECS` 须大于它
- 触发链：构建期 `RC_JOBS=rc.jobs.ssh`（build.sh:407）+ 运行期 `XL_CMDLINE` 含 `wifi=1`（radio 连网，configd 给 en0 地址）+ 长 XL_SECS（:2 注释）

---

## 2. Bootstrap 版本与哈希（使命 2）

获取方式：`mk-jb.sh` 副本原样运行（代理 `http://127.0.0.1:7897`，2026-11-04），EXIT=0，日志 `procursus-prep/logs/mk-jb.log`。全表见 `procursus-prep/logs/debs-sha256.txt`：

| 文件 | 大小 (B) | sha256 |
|---|---|---|
| bootstrap.tar.zst（1800 套件，`apt.procurs.us/bootstraps/1800/bootstrap-iphoneos-arm64.tar.zst`） | 20,792,571 | `a99b39bb0344ee3b42bb961325038dceae7daaec500976f3b822cf36cccf020a` |
| openssh-server_9.7p1-1_iphoneos-arm64.deb | 381,430 | `98ee1f2ee0987bccb12a24f84010238920d2677c1c17141fb90b54a34934dd9c` |
| openssh-client_9.7p1-1_iphoneos-arm64.deb | 740,078 | `fe5431b7dcbd164854df6e6cd881c573499eaa685c40b99146bb4106e17f16bc` |
| openssh-sftp-server_9.7p1-1_iphoneos-arm64.deb | 40,642 | `b2569cbde386c19b454a3e25d314b54c266431a5a21f67490c59454be223aa4e` |
| sileo.deb（2.5.1） | 2,909,972 | `8e3c90e5a7d32f4ca207a0ac30d3cfa8a13dca86a2b4e11cb3f9e5c68d7bc97a` |
| ellekit_0.4.5_iphoneos-arm64.deb | 372,334 | `dde2cac0a26aba812cfd43a1928a7e56f35e5018257792a7f071f34098a1b1a4` |
| debianutils_5.19_iphoneos-arm64.deb | 68,128 | `fd0515ccc41989fd23e90cac8db99c1bd45a3239e014efa2a48f08e815902823` |
| launchctl_1:1.2.0_iphoneos-arm64.deb | 52,032 | `1ba223fed06d40d58e6d944e566519ee43d59af7d704fe2f9722d3e27cb428d3` |
| preferenceloader_2.2.6-1_iphoneos-arm64.deb | 30,260 | `96733512819f7bfddb7b010df1e2b81f3a19edd2209102b958f39d0d3d242de0` |
| Packages（仓库索引） | 1,403,916 | `3976968ecb1fde0a74c77f02f5d1a8d7e2fd1edab641924a95270f7172c7f722` |

快照年代：bootstrap 内部条目 mtime 至 2024-06~10（1800 套件现役快照）；openssh 等经 jb-preinstall.py 取到仓库最新（9.7p1-1）。

## 3. 解包抽查（`jb/root/var/jb`，130M / 6,926 条目 / dpkg 库 70 包）

- 顶层齐全：`Applications bin boot dev etc lib Library mnt sbin System tmp usr var` + `.procursus_strapped`（Procursus 官方 strapped 标记）+ `prep.sh`（fork 版，mk-jb.sh:196-235 生成）
- **sshd**：`usr/sbin/sshd`，806,512 B；Mach-O 头实测 magic `0xcffaedfe`（MH_MAGIC_64）、**cputype `0x0c000001`（arm64）**、cpusubtype 0 —— 纯 arm64，零 arm64e，与本项目内核（xnu-8796.121.2 arm64）路线一致
- **ssh 配套**：`etc/ssh/{sshd_config,ssh_config,moduli}`；`usr/libexec/{sftp-server,ssh-keysign,ssh-sk-helper,sshd-keygen-wrapper,ssh-pkcs11-helper}`；`etc/master.passwd`（2,652 B，init pwd_mkdb 消费）
- **strust-procursus：本 snapshot 不存在**（全树 `find -iname "*strust*"` 零命中）。该信任缓存工具属于更新的 Procursus bootstrap；v0.4 不消费 trust cache（`cs_enforcement_disable=1` + miniamfi stub，wave14 §5.1），**无影响**；若未来走 AMFI 正门需换新 bootstrap 或单取该工具
- Sileo 全套在位（`Applications/Sileo.app` + `giveMeRoot` 4755），apt 源与 CaInfo 配置由 mk-jb.sh 写好——v0.4 SSH 场景用不上但不碍事，Sileo 生态后续阶段免重做

## 4. 预置/安装步骤（给 P0 后的 v0.4 波，逐条执行）

**本阶段已完成（产物即交付物）**：`~/hakios/procursus-prep/` 下 `jb/root/var/jb`（前缀树 = build.sh 的 `../jb` 输入）、`ssh/`（build.sh 的 `../ssh` 输入）、`keys/`（登录密钥对）、`logs/`（哈希台账）。

**下一阶段执行（构建窗口期，与 阶段 12a 协调，勿并行写 kernel 树）**：

```bash
# 1. 拷入 kernel 树顶层（build.sh 以相对路径 ../jb、../ssh 消费；TREE 内只增两个新顶层目录）
cp -a ~/hakios/procursus-prep/jb  ~/hakios/kernel/jb
cp -a ~/hakios/procursus-prep/ssh ~/hakios/kernel/ssh
# 可选核验：sha256sum ~/hakios/kernel/jb/debs/* 对照 procursus-prep/logs/debs-sha256.txt

# 2. 构建镜像（RC_JOBS 换成 ssh 场景；其余参数按当阶段 build.sh 惯例）
cd ~/hakios/kernel/userland
RC_JOBS=rc.jobs.ssh bash build.sh     # build.sh:407 烤 rc.jobs.ssh；:650-665 放 /jb；:392-403 放密钥+var.skel

# 3. 刷写启动时 XL_CMDLINE 需含：wifi=1 var_hfs=<UFS data 分区节点>（wave16/16b 定位的 darwin data 分区）
#    XL_SECS >= 1200（rc.jobs.ssh:24 wait 900 + 登录余量）

# 4. 设备起来、屏幕解锁滑动后（rc.jobs.ssh:15-22 自带解锁+开 switcher），主机侧：
ssh -i ~/hakios/procursus-prep/keys/id_ed25519_phk110 root@<手机IP>
#    首次进 shell 注意：shell 是 /var/jb/bin/sh（16.5 rootfs 无 /bin/sh，status 127——wave14 §5.1）
#    文件传输：sftp 直接可用（openssh-sftp-server 已预置，Subsystem 指向 /var/jb/usr/libexec/sftp-server）
```

**无需任何设备侧手动安装步骤**：init 嫁接（§1.4）与 var.skel 密钥种子全自动；唯一开关是构建期 RC_JOBS 与运行期 boot-args。

## 5. SSH 密钥交付（使命 4）

| 文件（`~/hakios/procursus-prep/`） | 用途 | sha256 |
|---|---|---|
| `ssh/ssh_host_ed25519_key` | host 私钥，构建期进镜像 → init 种子进数据卷 `/private/var/root/.ssh/` | `d4803fb0…f792cb7688` |
| `ssh/ssh_host_ed25519_key.pub` | host 公钥（客户端 known_hosts 留档） | `e8f6f3ce…06f77fd6ec` |
| `ssh/authorized_keys` | = 用户公钥，同通道进 `/private/var/root/.ssh/authorized_keys` | `0a2ebcd9…a275bee964` |
| `keys/id_ed25519_phk110` | 用户私钥（登录用，勿入镜像） | `473b643c…3a440835` |
| `keys/id_ed25519_phk110.pub` | 用户公钥（留档） | 同 authorized_keys |

公钥留档：

```
host: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBJzzK2T9zVi5NVhkWdb7PMmdjYdOfJMWLMB43q4jOcQ hakios-phk110-host-v0.4
      SHA256:6SkuNg4H50sjyKK5PQ3eX23nIEBR/Z9d7TqFGMPND6k
user: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDj9jT2NReWL1Joq4rSfSZQLza2G4U0Qxr9s3L6o8eee hakios-phk110-user-20261104
      SHA256:khN1rYtfAQCpXD8HTD8CZUJ0pdO+fZtoVE2ZEx8+kmI
```

客户端主机名校验（防 MITM）：`ssh-keygen -R <ip>; echo "…host pub 行…" > known_hosts_custom` 或用 `-o UserKnownHostsFile=` 指向留档文件。注意 SHARE=1 构建（build.sh:392）会静默丢弃密钥——v0.4 内部验证波**勿用 SHARE=1**。

## 6. HFS+ rw 能力调查结论（使命 3 附带，实测）

- **WSL2 内核 `6.18.54.1-microsoft-standard-WSL2` 不含 hfsplus 文件系统**：`/proc/filesystems` 无 hfs/hfsplus，`modprobe hfsplus` FATAL（无模块目录）→ **Linux 内核侧挂载（ro 与 rw 均不可能）**
- 用户态 hfsprogs 540.1 可用（wave14 装的 `hfsplus-tools`）：本阶段对副本 `fsck.hfsplus -q` **EXIT=0 FILESYSTEM CLEAN**；mkfs 能建卷（wave14 已证）
- 即使内核有 hfsplus，upstream Linux 也拒绝 journaled 卷 rw 挂载；已知绕法（清卷头 journal 位 @1024+16 attributes bit0x2、或 hpmount 类用户态工具）要么破坏 `-J` 语义（fork 内核 var_kept 期待日志卷，init.c:836-838 注释），要么同样拒 journaled 卷——**均不采**
- **结论：不需要也不应做 HFS+ 离线写入。** 机制上 bootstrap 走镜像 `/jb`、密钥走 var.skel 种子通道（init.c:954-966），HFS+ 卷只是设备侧 init 的挂载/嫁接地。任务书中"卷外通道"的猜想**成立且已是现成机制**（var.skel 'f' 行 + in_image()，init.c:29、:954-966；build.sh:400-403 供货）
- `var-hfs-data.img` 原件未动；副本 `procursus-prep/var-hfs-data-jb.img`（12G sparse，实占 52K）为 fsck 验证过的工作副本，供后续阶段实验（挂载/灌 var.skel 对照）用

## 7. 磁盘账目

| 项 | 大小 |
|---|---|
| `jb/root/var/jb`（前缀树） | 130M |
| `jb/debs`（10 文件，含 Packages 索引） | 26M |
| `var-hfs-data-jb.img`（sparse） | 52K 实占 |
| 密钥/日志/脚本副本 | <0.1M |
| **净耗** | **~156M**（WSL 916G 可用，解包前 917G） |

## 8. 风险与存疑

1. **sshd 9.7p1 含 CVE-2024-6387（regreSSHion）窗口**：jb-preinstall 已取仓库最新（9.7p1-1），但该 CVE 影响 8.5p1–9.7p1。缓解：key-only + PasswordAuthentication=no + 单用户内网 + 15 分钟窗口（rc.jobs.ssh:24）；后续可试仓库更新版（Packages 索引 2024 快照，未见 9.8+）
2. **RC_JOBS 是替换不是叠加**（build.sh:407 单文件拷贝成 `/etc/rc.jobs`）：`RC_JOBS=rc.jobs.ssh` 时默认 rc.jobs 的场景作业（解锁、springboard 等）不跑。若 v0.4 验收需要"SSH + 其他场景"并存，需自拼组合 rc 文件再以 RC_JOBS 指向它（ssh 段从 rc.jobs.ssh:15-24 摘录即可）
3. **prep.sh 在 ssh 场景不运行**：prep.sh 由 rc.jobs.sileo 场景跑（mk-jb.sh:198 注释）；SSH 场景下 `usr/libexec/firmware` 不登记、app 不 uicache。对 sshd 无影响（firmware 依赖已被 mk-jb.sh:169-189 剥除，登录链不触 app 注册）——但若同镜像后续要跑 Sileo 场景，prep.sh 会补上，闭环
4. **手机侧 apt 走设备直连**（无代理）：procursus.sources 指向 https://apt.procurs.us；upstream 实机已跑通 Sileo/apt（wave14 §5.2 情报），CaInfo 直配证书绕过 trustd——本 port 无回连网络是否同样可升级，留待设备实测
5. **var_hfs=DEV 依赖 UFS 侧**（wave16/16b 范围）：`/dev/ufs_darwin_data` 节点就位前挂载失败自动回落 ramfs；回落时密钥仍从镜像种子，host 指纹不变，SSH 链不受影响（仅持久性丢失）
6. **bootstrap 快照较旧**（2024）：strust-procursus 不在内（§3）。若 v0.5+ 要 AMFI 正门，需换较新 bootstrap 重跑本流程（mk-jb.sh 幂等，重跑即得）
7. `mk-jb.sh` 的 ellekit.space 源若波动会失败（EXIT≠0）——本阶段一次通过；重跑时该文件已在 `jb/debs/` 缓存，get() 跳过

## 9. 红线遵守

- **手机**：零 adb/fastboot/usbipd 调用 ✅
- **kernel 树**：只读 ✅。mk-jb.sh / jb-preinstall.py / rc.jobs.ssh 仅复制到 `procursus-prep/` 执行；副本脚本 ROOT 自解析为 `procursus-prep/`（mk-jb.sh:20-21），全部产物落 `procursus-prep/`，kernel 树零写入（`~/hakios/kernel` mtime 未变）
- **sysimage-20F66**：`var-hfs-data.img` 原件未动（仅 `cp --sparse=always` 读）；`work/`、`WAVE14-NOTES.md`、symlink 均未碰 ✅
- **网络**：全部下载走 `http://127.0.0.1:7897` ✅
- 报告仓库侧：仅新增本文件
