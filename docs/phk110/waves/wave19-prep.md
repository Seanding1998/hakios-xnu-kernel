# Wave 19 预研 — v0.4 两大开放问题：SSH 数据面 + 真实 launchd 系统卷

> 2026-11-04 · 纯调研设计（零手机交互、零刷写、零构建；`~/hakios/kernel` 与 upstream 克隆全程只读）
> fork 内核 = WSL `~/hakios/kernel`（= upstream `hakios-xnu-kernel` @ 96ffbc5 + phk110 设备层）；fork UEFI = WSL `~/hakios/uefi-udon`
> 下文 `kernel/` 前缀均指 fork 内核树（与 upstream 同源，证据行号两边一致）

---

## 0. 执行摘要

| 问题 | 结论 |
|---|---|
| **Q1 SSH 数据面** | **任务前提被证伪：upstream 没有"USB SSH"**——redwood 的 SSH 走 WiFi（`rc.jobs.ssh` + `wifi=1`），USB 通道只是 loader 管理面（fastboot 协议，经 vendor `EFI_USB_DEVICE_PROTOCOL`）。整个生态（HakiOS fork/upstream、UniXNU-udon、udon Binaries）**不存在任何现成 USB 网卡（NCM/EEM/RNDIS）实现**。v0.4 推荐方案 = **方案 A「loader 桥接网络」**：复用 fork 内三个现成资产（`hakios.net.c` en0 骨架 + loader 共享页 mailbox 模式 + loader 的 `download:`/`upload`/staged 原语 + Wave13 `loader_talk.py`），内核↔loader 加一页共享环，主机侧 `ssh -o ProxyCommand` 直进 Darwin shell。三端工作量 ≈ 内核 400–700 行 + loader 150–300 行 + 主机脚本 ~300 行，零 UEFI 二进制改动 |
| **Q2 真实 launchd** | **切换机制 100% 现成于树内**，由 boot-arg `root_apfs=DEV` + `var_hfs=DEV` 驱动（`kernel/userland/src/init.c` flash_root + kern.hakios_switch_root），PHK110 的 P0 布局（Wave16c）与 upstream 布局常量（`BLOCK_WRITE_FIRST=2042368`）**逐块对齐**。施工 = ①config 2 行（`CONFIG_ROOT_APFS/VAR_HFS` 现未开）→ ②`FLASHBOOT=1 CRYPTEXES=flash` 构建 userland 三镜像 → ③system.apfs+双 cryptex 灌 darwin 前段（0..2,042,367 现为全零，就绪）→ ④payload 双 ramdisk（loader 已支持 md0/md1）→ ⑤cmdline 追加 2 个 boot-arg。stub 救援链（v11）保留为回退镜像，不做运行时切换 |

---

## 问题 1：SSH 数据面怎么到主机？

### 1.1 上游"USB SSH"调研 —— 前提证伪（证据）

| 检查点 | 结果 | 证据 |
|---|---|---|
| redwood 设备文档 | 无 USB 网络/SSH 字样；WiFi 行 = "WCN6750 with Linux's ath11k: radio, driver, a network joined (wifi=1)" | `kernel/docs/devices/redwood.md`（"What works" 表，grep usb/ssh/ncm/ecm 零命中） |
| fork README | SSH 能力行 = "/private/var kept across reboots, Sileo, SSH \| yes"，上下文为 WiFi 可用之后 | `kernel/README.md:22` |
| SSH 启动方式 | `RC_JOBS=rc.jobs.ssh`（scenario 触发），注释逐字："A way in over the network (RC_JOBS=rc.jobs.ssh, **with wifi=1** among XL_CMDLINE …)… configd gives en0 an address, and OpenSSH from the package manager's prefix" | `kernel/userland/rc.jobs.ssh:1-9`（sshd 命令行在 ：10 起） |
| CHANGELOG USB 条目 | 全部是 loader fastboot 通道（U-Boot 下的 DWC3 设备模式），无一条网络 | `kernel/CHANGELOG.md` 2026-10-29 段（"u-boot: the loader's fastboot works under U-Boot…"） |
| loader USB 形态 | **fastboot 协议**服务器，描述符由 loader 自备（class 0xff/0x42/0x03 vendor，VID 0x18D1 PID 0xD00D），经 Qualcomm vendor 的 `EFI_USB_DEVICE_PROTOCOL`（GUID `QCOM_USB_DEVICE_GUID`），EP0 全由固件 UsbDeviceDxe 代答 | `kernel/xnuloader/loader.c:3713-3721`（命令面）、`:3729-3740`（描述符）、`:3767`（GUID）、`:3837-3860`（start_ex + 重试） |
| 系统镜像怎么到设备 | 2.5 GB 不走 fastboot payload 区（63 MiB 上限），走 `xl ramdisk`（loader 会话一次）或 flash 分区 | `kernel/docs/uefi-boot.md:48-51`；`kernel/userland/build.sh:55-59` |
| 内核侧 USB 栈 | **不存在**。`kernel/drivers/` 无 usb 子系统；net 子系统仅 `hakios.net.c`（en0/en1 接口骨架）+ `hakios.virtio_net.c`（QEMU 链路）+ WiFi 链路（`HakiosWLANStart`，drivers/wifi） | `kernel/drivers/README.md`（"Subsystems" 表 net/wifi 行）；`kernel/drivers/net/hakios.net.c:1-21` |
| UniXNU-udon 侧 | 无 NCM/RNDIS/EEM（grep 全仓仅 strncmp 误命中） | Windows 克隆 `upstream/UniXNU-udon` 全仓 grep |

**定性**：upstream 的 v0.4 级数据面 = WiFi；USB 只有管理面（日志/payload/截图，fastboot 协议）。**A 级现成 USB 网络资产 = 不存在**；任何 USB 网络形态都是新写。

### 1.2 fork 现有 USB device 栈盘点与冲突分析

**loader 侧（UEFI 层，真机已证）**：
- Boot #9（Wave7）：PHK110 上 USB gadget 枚举成功，主机见 `xnuloader`，驻留 USB 命令服务器可用。
- Boot #22（Wave16）：loader 驻留循环在内核运行期间同时服务 UFS 块请求 + USB 命令（`block_poll()` + `usb_poll_command()`，`loader.c:2477-2496`）——**loader 的 USB 与 UFS 服务在内核运行时并存**，这是方案 A 的架构基础。
- bulk 传输原语现成：`usb_rx`/`usb_tx`（`loader.c:3930-3951`，`USB_CHUNK = 1 MiB`，`loader.c:3725`）；主机→RAM 整块下载 `download:`（`loader.c:4051-4093`，目的地 `PAYLOAD_BASE=0xF0000000` 或驻留 ramdisk 区）；RAM→主机整块上传 `upload`（`loader.c:4095-4111`，发送 `staged_data`，`oem screenshot` 就是把 `staged_data` 指到内核帧缓冲）。
- 内核运行时单次 USB 事务等待上限 3 s（`usb_wait()`，`loader.c:3886-3890`，`run_active` 分支）——轮询式中继的延迟上界。

**内核侧**：零 USB 控制器代码。若写"DWC3 device mode + NCM"即全新控制器驱动。
**冲突结论**：内核 gadget 与 loader USB 服务器**同争一个 DWC3**。让出机制在树内有先例（UFS：`loader_block.native` hc_area 交接，`loader.c:1590-1608` + `ufs_native=`），但 USB 一旦让出，loader 自身 USB 服务器（logdump/oem log/`oem stop` 救援通道）全部失效——**USB 让渡 = 放弃管理面，否决**；反之 loader 保持 USB 时内核不可能直接挂控制器 → **内核原生 USB 网卡在当前架构下不可行（v0.4）**。

### 1.3 udonPkg UEFI USB 路径 + UMS 评估

`~/hakios/uefi-udon/Platforms/OnePlus/udonPkg/Include/DXE.inc:85-102`——**任务书点名的四个 DXE 全在编**：

```
:85  Binaries/udon/QcomPkg/Drivers/UsbPwrCtrlDxe
:91  Binaries/udon/QcomPkg/Drivers/UsbfnDwc3Dxe      ← EFI_USBFN_IO（DWC3 function 控制器）
:95-97 MdeModulePkg UsbBusDxe / UsbKbDxe / UsbMassStorageDxe（主机侧栈）
:99  Binaries/udon/QcomPkg/Drivers/UsbMsdDxe         ← Qualcomm MSD 外设驱动 ★
:100 Binaries/udon/QcomPkg/Drivers/UsbDeviceDxe      ← EFI_USB_DEVICE_PROTOCOL（loader fastboot 用）
:101 Binaries/udon/QcomPkg/Drivers/UsbConfigDxe      ← 时钟/PHY（RPM/DAL）
:102 Binaries/udon/QcomPkg/Drivers/UsbInitDxe
```

- UsbMsdDxe 二进制符号（strings 实测）：`UsbMsdStartDevice` / `UsbMsdAssignBlkIoHandle` / `UsbMsdQueryMaxLun` / `UsbMsdEventHandler` / `CheckBlkIoLunAssociation`；DEPEX = TRUE；来源 = senna_bc（RMX3706, 同 SM8475）社区 patched 版（`Binaries/udon/README.md`：UDON Binaries 为 senna_bc verbatim 拷贝，"UsbConfigDxe, UsbMsdDxe" 补丁随带，INF 引用 `.patched.efi`）。
- **现成 API 样板（本仓上游已写好）**：`Platforms/OnePlus/udonPkg/Applications/UdonLogExport/UdonLogExport.c`——"Export the persistent Udon XNU log window as a read-only USB mass-storage disk"：
  - `:359` LocateProtocol(`gEfiUsbMsdProtocolGuid`) → `:365` `Msd->AssignBlkIoHandle(Msd, &mRamBlockIo, 0)` → `:372` `Msd->StartDevice(Msd)` → `:383` 循环 `Msd->EventHandler(Msd)`（Volume Up 退出）→ `:391-392` `StopDevice` + 解绑。
  - `:2-4` 注释：**32 MiB 先拷进 RAM 再以 RAM BlockIo 挂 LUN0**，"Keeping UFS behind the RAM copy avoids relying on macOS accepting the vendor UFS capacity/SCSI behavior directly"。
- **VID 0x05C6 PID 0xF000**：UsbMsdDxe 二进制 strings 无描述符证据，具体 VID/PID 需真机枚举确认（不影响可行性：Windows 对 USB MSD 是类驱动，不挑 VID/PID）。
- **"UFS LU0→USB MassStorage" 可行性评估**：
  - API 层 ✅（UdonLogExport 全链在树内，AssignBlkIoHandle 吃任意 BlockIo——理论上可直挂 UFSDxe 的 darwin 分区 BlockIo）。
  - 阻碍 1（硬）：**Windows 无 HFS+ 写驱动**。"UMS 拖文件"实际形态只能二选一：exFAT RAM 盘中转（退出时 loader 拷回 darwin `ufs_write` 区）或只读导出（Win 需 MacDrive 类第三方才能读 HFS+）。两形态都要新写 UEFI 应用 + 一次 darwin 写回流程。
  - 阻碍 2（未证）：UsbMsdDxe 走 EFI_USBFN_IO（UsbfnDwc3Dxe），loader fastboot 走 EFI_USB_DEVICE_PROTOCOL（UsbDeviceDxe），两栈同争 DWC3 的共存/换手未证；且我们的 graft（BootManager AfterConsole → XnuLoaderMain）开机自动进 loader，UMS 入口需 graft 侧加条件分支。
  - 阻碍 3（价值）：UMS 是**静态文件通道**，不承载 SSH 交互会话——不满足 v0.4 验收（SSH 进 shell）。
  - **定位**：v0.4 的**辅助**文件通道（可选做），非 SSH 替代。

### 1.4 v0.4 数据面方案排序

| # | 方案 | 满足 SSH | 复用度 | 新增代码 | 风险 | 判定 |
|---|---|---|---|---|---|---|
| **A** | **loader 桥接网络**（fastboot 通道承载 net 数据，共享页中转，内核 en0 走 BSD 栈，主机 `ssh -o ProxyCommand`） | ✅ 真 SSH 会话 | 高（三个现成资产 + loader_talk.py） | 内核 link 驱动 ~400-700 行 + loader ~150-300 行 + 主机脚本 ~300 行 | 中低（轮询延迟；半双工） | **v0.4 主选** |
| B | UEFI UMS 文件通道（UdonLogExport 模式扩展） | ❌（只拖文件） | 高（API 样板在树内） | UEFI 应用 ~200-400 行 | 中（双 USB 栈共存未证；入口绕 graft） | 辅助，可并行可后置 |
| C | 内核 DWC3 device-mode + NCM/EEM/RNDIS | ✅（真 USB NIC，Win RNDIS 即插即用） | 零 | ~2-4k 行全新控制器驱动 | 高 | **v0.5+ 再议**（WiFi v0.6 后价值下降） |
| D | WiFi（ath11k）提前 | ✅ | 中（upstream 全套 wifi= 驱动在树内） | wcn6750 bring-up（v0.6 计划体量） | 高（计划外提前） | 否决（破坏 v0.4→v0.6 计划） |
| E | cellular/IPA en1 | ✅ | 低 | upstream 定性 "no registration yet" | 高 | 否决 |

### 1.5 方案 A 施工单（三端）

**架构**（三个现成先例拼装，全部 fork 自己的模式）：
```
Windows: ssh -o ProxyCommand="python loader_net.py" ──libusb/WinUSB──► loader fastboot bulk
loader : resident loop（usb_poll_command + block_poll 并存，loader.c:2477-2496）
          新增 oem net 命令 ⇄ struct loader_net 共享页（仿 loader_block，loader.c:1552-1676 模式）
kernel : drivers/net/hakios.usbnet.c（link 驱动，仿 hakios.ufs.c 的 mailbox 读法）
          → 挂进现有 hakios.net.c en0（"What carries the frames is a link driver's business"，hakios.net.c:7-9）
Darwin : configd/SSH 全走现成 BSD 栈（en0 上 configd 照 USB-Ethernet 方式配置，docs/cellular.md:43 同构）
```

**内核侧新增/改动**：
1. `kernel/drivers/net/hakios.usbnet.c`（新）：共享页收发环 + `hakios_net_link` 注册（对齐 `kernel/xnu/files/sys/hakios.net.h` 的 link 接口）；boot-arg `net_shared_pa=`（loader 写进 cmdline，同 `ufs_shared_pa=` 先例，`loader.c:1554`）。
2. `kernel/drivers/net/conf` + `kernel/drivers/map` 登记；`CONFIG` 名进 `kernel/docs/boot-args.md`（drivers/README.md 的规矩）；缺位 stub 进 `kernel/drivers/core/hakios.stubs.c`。
3. 不动 `hakios.net.c`/`hakios.virtio_net.c`。

**loader 侧**（`kernel/xnuloader/loader.c`，随后续 kernel 构建一起重编 loader.efi）：
1. `struct loader_net`（共享页：magic/version/rx 环/tx 环/容量/水位，cache line 对齐仿 `loader_block` `loader.c:1667-1676` 的 `_Static_assert` 纪律）。
2. 两个 oem 命令（或 resident loop 内推）：`oem netrx` = 把 `staged_data` 指向 rx 环 → 现成 `upload` 泵（loader.c:4104-4111 原样复用，只换 staged 指针）；`oem nettx <n>` = `download:` 收 N 字节入 tx 环（download 处理器 loader.c:4051+ 已有整块接收）。
3. cmdline 追加 `net_shared_pa=<phys>`（boot-args 组装处 loader.c:3201 `rd=md0` 同段）。

**主机侧**（Windows 仓 `wave19-scripts/` 或后续波次）：
1. `loader_talk.py`（Wave13，selftest 24/24）扩 `net` 子命令：轮询 `oem netrx`（DATA 帧收）/`oem nettx`（download: 帧发）。
2. `loader_net.py`：stdin/stdout 字节流 ⇄ 帧通道——`ssh -o ProxyCommand` 即用，**零 Windows 驱动/零 TUN**。SSH 交互流量对延迟不敏感，fastboot 半双工轮询（每次事务 ms 级 + 3 s 上界）够用。

**boot-args 增量**：`net_shared_pa=<hex>`（loader 注入，不占 cmdline 手工预算）。
**风险登记**：
- R-A1 半双工轮询延迟：TTY 交互可感知但可用；批量传输慢（scp 限速）→ v0.4 验收只要求 shell 可达，文件走方案 B 或 darwin-write。
- R-A2 loader 驻留循环单核（core 0）负载：同 UFS 服务并存已证 60 s 会话零 panic（Boot #22），net 轮询加一等量 poll 即可。
- R-A3 `usb_wait` 3 s 上界（loader.c:3886）会把掉线主机的等待截断为 -1：中继协议要容忍 `FAIL`/超时重试（loader_talk.py 协议层已有 PARTIAL 容错）。
- R-A4 loader.efi 重编：v11 镜像的 loader（sha 66c6b342…）是旧版二进制，方案 A 需要 loader 段升级 → 首次上机镜像 = loader+kernel 同刷，自检清单加 loader sha 断言（现有 42/42 流程原样扩）。

---

## 问题 2：真实 launchd 的系统卷路径

### 2.1 fork/upstream 现成机制（全部在树内，零新设计）

**总开关 = boot-arg `root_apfs=<dev>`**（`kernel/userland/src/init.c:1541-1545` main 里读，`boot_arg()` 实现在 `:77-95`）→ `flash_root(dev)`（`:177-270`）：

| 步 | 动作 | 证据 |
|---|---|---|
| 1 | 挂 `/dev/<dev>`（darwin 分区 = APFS 容器）只读到 `/flash` | `init.c:187` `mount("apfs", "/flash", MNT_RDONLY, devpath)` |
| 2 | synthetic 目录 `/flash/redwood`（`kern.apfs_synthetic` sysctl） | `init.c:105-116, 196` |
| 3 | **launchd 任务裁剪**：镜像的 `/LaunchDaemons` bindfs 到卷的 `/System/Library/LaunchDaemons`；空目录盖住 NanoLaunchDaemons/LaunchAngels/`xpc/launchd.plist`（"our launchd jobs, not Darwin's 500"） | `init.c:197-201`；背景 `kernel/userland/build.sh:91`（"491 LaunchDaemons…" 2026-10-19 事故记录） |
| 4 | 音频 HAL 插件裁剪 + `/fw` 固件绑定 | `init.c:202-207` |
| 5 | Sileo 五件套 union 盖 `/flash/bin`（`/jb-bin`） | `init.c:208-220` |
| 6 | 首启 App：卷的 `/private/var/staged_system_apps` → synthetic 进 `/Applications` | `init.c:222-251` |
| 7 | **换根**：`sysctl kern.hakios_switch_root = "/flash private/preboot"`——卷变 `/`，RAM boot 卷挪到 `/private/preboot` | `init.c:253-261` |
| 8 | cryptex 挂载：md0 `,c=1`/`,c=2`，EINVAL 则 flash 设备同名容器 → `/private/preboot/Cryptexes/{OS,App}`（卷的 `/System/Cryptexes` 指过来；内核共享缓存取自 Cryptexes/OS） | `init.c:141-175`（mount_cryptex）+ `:264-267` |
| 9 | 镜像绑回 `/redwood`；`flash_root_mode=1` | `init.c:268-270` |
| 10 | 数据卷：`mount_writable()` → `mount_data_volume()`，boot-arg **`var_hfs=<dev>`** → `mount("hfs", "/private/var", …)`；失败回落 ramfs | `init.c:834-860`（mount_data_volume）、`:905-935`（mount_writable） |
| 11 | 交接：rc.launchd `exec /sbin/launchd.darwin`，flash_root_mode 下 init 把 argv 改写为 `/sbin/launchd`（= 卷上 Apple 真 launchd） | `kernel/userland/rc.launchd:1-2`；`init.c:1329-1333` |
| 12 | boot-args 保持 `rd=md0`（launchd 据此跳过真机 boot 任务） | `init.c:118-137` 注释；loader 侧 `loader.c:3201` |

**设备名**：`dev` = ufs=2 发布的节点名。PHK110 取 `ufs_darwin`（Wave16c 划出的 20 GiB darwin 分区，ufs=2 → `/dev/ufs_darwin`，Wave16 S0 验收行 "/dev/ufs_NAME"）；数据卷用内核合成切片 **`/dev/ufs_darwin_data`** = darwin 自 `UFS_WRITE_FIRST=2042368` 块起的可写区（`kernel/drivers/storage/hakios.ufs.c:31` + `:222-226`；loader 写界 `loader.c:1598` `BLOCK_WRITE_FIRST 2042368ULL`——**Wave16c 灌卷恰收口 2,042,368..5,242,874 = 该界逐块吻合**，见 wave16c-p0-exec.md）。

**config 门**：`CONFIG_ROOT_APFS` / `CONFIG_VAR_HFS`（读的是 user space init.c）——`kernel/configs/common_defconfig:1122` / `:1128` 现均为 `not set`（boot-args 总表 `kernel/docs/boot-args.md:428-431`）。

**stage0 链**（内核启动的第一程序 = 被顶替的 /sbin/launchd）：`kernel/userland/src/stage0.c:1-31`——挂 md1 小镜像（root.apfs）到 `/redwood` → `execve /redwood/sbin/init`。

### 2.2 系统镜像产出流程（`kernel/userland/build.sh`）

| 镜像 | md | 产出 | 内容/要点 | 证据 |
|---|---|---|---|---|
| **system.apfs** | flash darwin 前段（from PC） | `FLASHBOOT=1` 同跑产出 | rootfs 硬链拷贝 → LaunchDaemons 四删一链（`/redwood/LaunchDaemons`）→ `mv sbin/launchd sbin/launchd.darwin; cp obj/stage0 sbin/launchd`（**Apple launchd 保留为 .darwin**）→ /fw、/jb、HakiosAudio/Metal 链接、双 cryptex 内嵌（RAM boot 路线）→ `mkapfs.py -z`（zlib，5.4 GB 文件 → **2.5 GB 镜像**） | `build.sh:55-60`（产物头注）、`:596-616`（换位）、`:649-668`（**/jb 嵌入点**：`../jb/root/var/jb` → `sysroot/jb` + SILEO_BIN 五链接）、`:694-695`（mkapfs+check） |
| **flashboot.apfs** | md0（RAM 驻留） | `FLASHBOOT=1 CRYPTEXES=flash` | 20 MB 级三容器/单容器 boot 卷：stage0 为 `/sbin/launchd` + `/redwood` 空挂点 + `/fw` + `/jb`；`CRYPTEXES=flash` 时 **cryptex 不进 RAM**（"2.6 GB against 1 GB: too much for the phone's memory beside Darwin"），init 从 flash 挂 | `build.sh:515-560` |
| **root.apfs** | md1（第二 ramdisk） | 每次 userland 构建 | 小镜像：init/rc/LaunchDaemons/测试件 | `build.sh:5, 158, 406-413` |
| delivery | — | — | 上游两通道：`xl ramdisk`（loader 会话一次，`uefi-boot.md:48`）或 flash 分区（`docs/install.md` 路线，`tools/darwin-write.py`）。**PHK110 走 flash 通道**（Wave16c adb 配方已证 263 MB/s 稳态） | `docs/uefi-boot.md:48-53`；`tools/darwin-write.py:7-25` |

**payload 双 ramdisk**：loader 原生支持两条：`"RAMDisk" becomes /dev/md0, the root…; "RAMDisk1" becomes /dev/md1`（`loader.c:3347-3348`；`:3052` "it is the root (md0), the payload ramdisk is md1"）→ flash boot 的 payload = RAMDisk=flashboot.apfs + RAMDisk1=root.apfs + kernel + cmdline。**需核验项**：v11 在机的 loader.efi（sha 66c6b342…）是否已含此版本行为（在机 loader 已证含 UFS block service v3 = 较新；构建时以 `kernel/xnuloader/build.sh` 重编 + mkpayload.py 打双 ramdisk 为准）。

### 2.3 真实 launchd 切换施工单（v0.4）

前置盘点（全部已就绪）：
- Wave14：20F66（iPhone10,3 / iOS 16.5）rootfs 树 + `system.manifest` + `var.skel` + dyld cache 2.6 G + OS/App cryptex + trust cache ×3 + 12 G HFS+ 模板，`~/hakios/sysimage-20F66/work/`。
- Wave16c：darwin 20 GiB 落位，前段块 0..2,042,367 **当前全零**（灌卷从 2,042,368 起）= system.apfs + cryptex 的空位；`tools/darwin-write-phk110.py`（PARTN=15/FIRST=56271872/LAST=61514746/PROTECTED=1374208）已交付并实战过。
- Wave16：`ufs=2` 上机（129 节点 → `/dev/ufs_darwin`、`/dev/ufs_darwin_data` 可用）。
- 工具链：`aarch64-linux-gnu-gcc` 在 PATH；`kernel/xnu-deps/` 已 build（SDK/host 工具在位）；`kernel/prebuilt/userland/` 备选（PREBUILT=1）。

**步骤**：

1. **config**（+2 行）：`devices/phk110/configs/phk110_defconfig` 追加 `CONFIG_ROOT_APFS=y` + `CONFIG_VAR_HFS=y`（覆盖 `configs/common_defconfig:1122/1128`）。
2. **userland 构建**（WSL，写 kernel 树 = 施工波执行，非本轮）：`FLASHBOOT=1 CRYPTEXES=flash bash userland/build.sh`，DARWIN 指 `~/hakios/sysimage-20F66/work`（unpack.sh 的产出布局）；可选 `tools/mk-jb.sh` 先备 `/jb`（PREINSTALL 默认含 openssh-server，`mk-jb.sh:113-115`；构建时 build.sh 自动嵌 /jb，`build.sh:649-668`）→ 产物：`flashboot.apfs`（md0）+ `root.apfs`（md1）+ `system.apfs`（2.5 GB）。
3. **灌 darwin 前段**（adb 通道，用户批准门）：system.apfs @ 块 0 + OS cryptex + App cryptex 依上游布局排在 cryptex 区（全在 0..2,042,367 内）；工具 = `darwin-write-phk110.py`（PROTECTED 语义反转为"本次写入目标即前段"，identity/skip 校验逐条过）。
4. **payload**：mkpayload.py 打双 ramdisk（RAMDisk=flashboot.apfs、RAMDisk1=root.apfs）+ v11 内核（+ROOT_APFS/VAR_HFS 重编后）+ cmdline。
5. **cmdline**（v11 基础追加，预算余 228 字符）：` root_apfs=ufs_darwin var_hfs=ufs_darwin_data`（40 字符，预算足）。
6. **启动顺序**（验收断言链）：UEFI graft → loader → `oem run` → 内核 rd=md0 起 → stage0（/sbin/launchd 位）挂 md1 → exec init → `-- the Darwin root volume on /dev/ufs_darwin as the root --`（init.c:186）→ 换根行 → cryptex 两行 → `/private/var: HFS Plus from /dev/ufs_darwin_data, kept between boots`（init.c:855）→ rc.launchd → **Apple launchd 接管 PID 1**。
7. **stub 并存/救援策略**（建议采纳）：**双镜像版本制，不做运行时切换**——v11（stub + mockfs + 无 root_apfs）保留为回退镜像；新版本（v12+）才是真 launchd。stub 链的可贵处：launchd 起不来时仍能拿到完整内核日志 + 60 s 干净返回（loader_return_after 兜底保留两版都带）。救援语义 = 刷回 v11。
8. **验收行**：launchd 横幅/任务装载日志 +（与 Q1 会师）`ssh` 进 shell 后 `ps -p 1` 看到 launchd。

**风险登记**：
- R-B1 Apple launchd 在本内核的兼容性：upstream redwood 实机已证（README:22 "Sileo, SSH yes"）；minimac（AMFI/Sandbox stand-in，`kernel/xnu/files/bsd/kern/kern_minimac.c`）全 ad-hoc 视为 platform binary 的行为是 launchd 能起的前提，树内已与 upstream 同版。
- R-B2 20F66 = iPhone X 16.5 = upstream 同代用户态（Wave14 全 arm64 零 arm64e 抽查过），无代际风险。
- R-B3 cryptex 走 flash（CRYPTEXES=flash）依赖 mount_cryptex 的 EINVAL 回落路径（`init.c:141-175`）——flashboot 单容器时 md0 无 c=1/c=2，回落 `flashdev,c=1/c=2`；这是上游主线用法，但 PHK110 是首跑 → 首刷把三行 cryptex 日志都当验收点。
- R-B4 dyld cache 2.6 G 在 flash cryptex 内、`vm_unix.c` 从 Cryptexes/OS 取共享缓存（init.c:135-137 注释）——若 PHK110 内存压力（16 GB 优于 redwood 8 GB，风险反而低）。
- R-B5 system.apfs 灌卷 2.5 GB+2.6 G@263 MB/s ≈ 20 s×N 分段（darwin-write-phk110 分段 readback 断言全保留）。
- R-B6 首启 App synthetic 绑定（init.c:222-251）依赖卷内 `/private/var/staged_system_apps` 存在——20F66 rootfs 是否带该目录需构建后在镜像上确认（upstream select-system.py 的行为，Wave14 未单列）。

### 2.4 两问交汇（v0.4 完整验收）

```
真实 launchd（Q2 施工单） + loader 桥接 SSH（Q1 方案 A） + UMS 文件通道（Q1 方案 B，可选）
  = v0.4「SSH 进 Darwin shell」
```

- Q2 给出活的 Darwin（真 launchd + Procursus /jb 的 openssh-server，sshd 由 rc.jobs.ssh 起——**无需 WiFi**：en0 由方案 A 提供，sshd 只管 0.0.0.0:22）。
- Q1 方案 A 是唯一不碰 UEFI 二进制、不动计划表的通路；方案 B 是它的文件面补充（scp 大文件替代）。

---

## 附：本轮调研过的文件索引（证据行号）

| 文件 | 用途 |
|---|---|
| `kernel/xnuloader/loader.c` | fastboot 服务器 :3713-3740；usb_start :3753-3875；usb_rx/tx :3930-3951；resident loop :2450-2500；UFS 共享页模式 :1540-1700；kernel_live :953-965；download/upload :4020-4112；RAMDisk/RAMDisk1 :3347-3348, :3052 |
| `kernel/userland/src/init.c` | root_apfs/flash_root :38-44, :118-270；boot_arg :77-95；mount_cryptex :141-175；mount_data_volume :834-860；mount_writable :905-935；launchd 交接 :1329-1333；main :1541-1545 |
| `kernel/userland/src/stage0.c` | /sbin/launchd 位程序，md1→/redwood→init |
| `kernel/userland/build.sh` | 产物定义 :5-16, :55-70；flashboot :515-560；system.apfs :590-700（/jb :649-668） |
| `kernel/userland/rc.launchd` / `rc.jobs.ssh` | exec 交接 / sshd 起法与 wifi=1 前提 |
| `kernel/drivers/net/hakios.net.c` | en0 骨架 + link 驱动接口（方案 A 内核侧挂点） |
| `kernel/drivers/storage/hakios.ufs.c` | ufs_darwin_data 切片 :31, :222-226；mailbox 读法（方案 A 仿写模板） |
| `kernel/configs/common_defconfig` | CONFIG_ROOT_APFS :1122 / CONFIG_VAR_HFS :1128（现未开） |
| `kernel/docs/devices/redwood.md` / `kernel/README.md:22` / `kernel/CHANGELOG.md` | 上游能力表（Q1 前提证伪） |
| `kernel/docs/uefi-boot.md` / `docs/u-boot.md` / `docs/cellular.md` | 镜像交付通道 / EFI_USB_DEVICE_PROTOCOL / configd-USB-Ethernet 同构 |
| `~/hakios/uefi-udon/Platforms/OnePlus/udonPkg/Include/DXE.inc` | USB DXE 清单 :85-102 |
| `~/hakios/uefi-udon/Platforms/OnePlus/udonPkg/Applications/UdonLogExport/UdonLogExport.c` | EFI_USB_MSD_PROTOCOL 全链样板 :327-392 |
| `~/hakios/uefi-udon/Binaries/udon/`（README/UsbMsdDxe） | senna_bc provenance + MSD 二进制符号 |
| 仓内 `docs/waves/wave13-usb-host.md` / `wave14-sysimage-prep.md` / `wave16-ufs-s0s2.md` / `wave16c-p0-exec.md` | loader_talk.py / sysimage 产物 / ufs=2 / P0 布局（前置资产） |
