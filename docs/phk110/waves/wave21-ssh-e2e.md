# 阶段 21 · 2026-11-08 · en0 真机验证：内核拿到 IP，SSH 尚未走通

> 2026-11-08 · 执行记录全循环：三端实施 → 构建 → 自检 → 第三次刷写 → E2E 尝试 → 判定
> **判定：v0.4「SSH 进 Darwin shell」未达成（N1/N2/N3 未闭环）**。三端代码全部真机验证、en0 数据面真机实证（attach + IP 配置 + 网环收发），但 loader USB 命令服务器的可用性被 **vendor UEFI `UsbConfigDxe start_ex` 间歇失败**（Boot #9 已记录的同源顽疾，~1/10 boot 成功率）卡死，三轮修复（v15.1/v15.2/v15.3）未能在本轮内闭环。按红线（失败重试 ≤2 次）停止并报告。
> 镜像：boot_b = **v15.3**（`d117e48c…`，安全——内核侧与 v14 等价 + en0；通道不通时行为等同 v14 循环）。手机已/正在回安卓（`handback.sh` watcher 自动 `set_active a`）。

## 0. 一句话结论

阶段 21 把「SSH 数据面」的三端全部建成并真机验证到最后一环（en0 真机验证、IP 配置成功、网环内核→loader 方向真实流动、`oem netmode/netstat` 真机验证），**SSH 登录本身被 loader USB 服务器的开机成功率挡住**：`start_ex` 在 PHK110 上与平台 init 竞速（Boot #9 遗案），v15.0 一轮侥幸成功证明了全链可行（en0 attach + 10.0.0.2/30 配置 + 网环单向流动 + netmode 真机验证全部 ✔），但可重复性未达成。**v0.4 宣告推迟**，本报告给出下一步的精确施工单。

## 1. 交付物清单（全部入库）

| 端 | 文件 | 内容 | 真机状态 |
|---|---|---|---|
| loader | `kernel/xnuloader/loader.c`（+~330 行）| BLOCK_VERSION 4：`struct loader_block` 尾部网环字段（tx/rx 各 16 slot × 1600 B，128B 对齐门铃，单写者单 cache line）；`net_setup/net_poll/net_rx_push/net_download_feed`；`oem netmode [on/off]`、`oem netstat`；`download:`/`upload` 网模式分支（busy 豁免）；usb-first 流：`usb_start()` → `run_kernel`（watch loop 内 `usb_lazy_start` 持续重试 bring-up）→ 服务窗 240s `usb_command_loop`（v15.3：boot loop 1s 节拍、lazy 20s 退避）| ✔ 真机验证（`usb: started`、`oem netstat` = `tx 1 lost 0 … en0 1`、netmode on/off 应答）|
| kernel | `kernel/drivers/net/hakios.loader_net.c`（新，~270 行）| en0 的 link 驱动：transmit（mbuf→tx slot）+ poll（rx slot→栈）+ 0x88b5/"W21" 环回自测应答；`net_shared_pa` 经 ufs 页（frames_pa）；**内核态 IPv4 配置**（kernel socket `SIOCAIFADDR` 10.0.0.2/30 + `SIOCSIFFLAGS` up，if_utun/if_ipsec 同路）；`net_shared` 字段经 `hakios_ufs_net_ring()`（ufs.c 交出映射）| ✔ 真机验证（attach/link up/10.0.0.2/30 三行验收）|
| kernel-abi | `kernel/xnu/files/bsd/sys/hakios.net.h`（+40 行）| `struct hakios_net_ring`（与 loader 逐字对齐，1024B 静态断言）+ `hakios_ufs_net_ring()`/`hakios_loader_net_init()` 声明 | ✔ |
| kernel-ufs | `kernel/drivers/storage/hakios.ufs.c` | BLOCK_VERSION 3→4；`struct loader_block` 尾部同一网环（embed `struct hakios_net_ring net`）；`hakios_ufs_net_ring()` 访问器 | ✔（页校验通过，S3-S8 回归全绿）|
| kernel-接线 | `drivers/net/conf`（driver LOADER_NET，requires UFS）、`drivers/map`、`drivers/core/hakios.stubs.c`、`drivers/net/hakios.net.c`（init 链挂 `hakios_loader_net_init()`）、`devices/phk110/configs/phk110.config`（CONFIG_HAKIOS_LOADER_NET=y）| 配置/接线五件套 | ✔ |
| host | `wave21-scripts/loader_talk.py`（~700 行，含 阶段 13 继承）| **netmode**（N1 环回）、**ping**（N2 ICMP，用户态构建 echo）、**tunnel**（N3：~200 行微型 TCP，OpenSSH ProxyCommand 传输——wintun 需管理员被拒后的无管理员降级路径）、**tun**（wintun 帧中继，需提权）；双平台（Windows libusb-dll / **WSL libusb-so**——本轮 E2E 主通道）；`connect()` 修复 阶段 13 潜伏 bug：`libusb_free_device_list` 后复用设备指针在 Linux 必崩（重排：全部描述符/claim 在 list 存活期内完成）| ✔ 24/24 selftest（两平台）|
| 构建/自检 | `wave21-scripts/make-cmdline-v15.py`、`make-payload-v15.sh`、`verify-udon-hakios-v15.py`、`flash-b26.sh` | cmdline v15（471B：`loader_return_after 120→300` + `+en0_addr=10.0.0.2`，预算 593/607）；payload **--usb**（7 条目）；graft；verify 48/48（FD/shim 未动、resident/ramdisk 与 v14 字节全等、`usb` 条目、cmdline 逐字节）| ✔ 48/48 |
| 佐证 | `logdump-v15.bin`（512MB，仓库根）；`wave21-scripts/`：session-e2e.sh、catch-and-run.sh、e2e-run.sh、continuous-poll.py、watch-attach.sh、handback.sh、reboot-toward-android2.sh、id_ed25519_phk110、wintun.dll（amd64, `e5da8447…`）| 全链自动化 + 取证 | ✔ |

**镜像链**（device-layer/）：payload v15.3 `60f96953…`（23,385,608B）→ grafted **v15.3 `d117e48c…`**（192MiB）= **当前 boot_b**；kernel `17c905ec…`（14,920,984B，v14 以来 +344B = en0 驱动 + ufs v4）；loader `0f7f4028…`（v15.3，77,056B 级）；kernel.ver 仍钉 afd473f5；resident/ramdisk 与 v14 条目字节全等（**darwin 前段未动**）。

## 2. 判定阶梯实况

| 阶梯 | 设计验收 | 实况 | 判定 |
|---|---|---|---|
| N1 | 主机发帧 → en0 计数/回传 → `oem netstat` 对账 | 环回帧机制已实现（kernel 0x88b5 回声 + host netmode 测试器）；`oem netstat` 真机验证应答（`tx 1 lost 0 rx 0 lost 0 held 0 0 en0 1`）；但环回帧未在稳定会话中完成对账 | ☐ 未闭环 |
| N2 | `ping 10.0.0.2` 通 | en0 IP 配置真机成功（`net: en0 has 10.0.0.2/30`）——ICMP 应答方就绪；主机侧无 wintun（管理员拒绝）→ 用户态 ICMP over tunnel 未跑 | ☐ 未闭环 |
| N3 | `ssh 10.0.0.2` Darwin shell | sshd 就绪（v14 遗产，b25 实证监听 :22）；数据面未接通 | ☐ 未闭环 |
| **前置** | loader USB 服务器可用 | **间歇成功**（logdump 实证 `usb: started`；但 ~9/10 boot `start_ex` 失败）| ✗ 病根 |

## 3. 真机实证（本波拿到手的硬证据）

1. **en0 数据面全链真机验证**（v15 会话，logdump `logdump-v15.bin`）：
   - `[37.614063]: ifnet_attach: All kernel threads created for interface en0 …`
   - `[37.614072]: net: en0 attached on the loader's USB channel, address 02:68:61:6b:69:02, link up`
   - `[37.614081]: net: en0 is on the loader's channel: 16 slots of 1600 bytes at faaea000, sending to the host over its USB`
   - `[38.110003]: skip attaching fsw to en0 using legacy TX model` + **`net: en0 has 10.0.0.2/30 on the loader's channel (the host is 10.0.0.1)`** ← 内核态 SIOCAIFADDR 一次点亮
2. **网环内核→loader 方向真实流动**：`oem netstat` → `tx 1 lost 0 rx 0 lost 0 held 0 0 en0 1`（en0 发出的 1 帧被 core 0 排空；en0 的 `seen=1`）。
3. **netmode 真机验证**：`oem netmode on` → `the pipes carry frames (oem netstat)`；`off` → `the pipes carry logs and payloads`。
4. **v15 会话本身**：S6/S7/S8 回归全绿（`/private/var: HFS Plus … kept between boots` + `112 directories, 22 files`）、clean PSCI return。
5. **loader USB 服务器可用性已被单点证明**：05:02 窗口，`getvar:product`=xnuloader、`getvar:result`=idle、`oem netstat`、`oem run`（会话内 serving）、`oem stop`/`reboot` 语义——**整个协议栈（含 serving 中的 netmode）在该窗口全部工作**。

## 4. 没有达成的根因链（给下一波的施工单）

### 4.1 主因：`UsbConfigDxe start_ex` 间歇失败（Boot #9 遗案，非本波引入）
- 证据：`logdump` 里有 `usb: started`（成功 boot）；其余 boot 的 `start_ex` 在 10s 重试窗内全部失败 → loader 走 one-shot（会话跑但 USB 服务器缺席）。
- v15.0 门控（usb_connected 从未置位 → post-session wedge）是**第二个**坑，v15.1 已去除。
- v15.2 懒重试（250ms）反而造成 DWC3 永续复位 → 主机永远无法完成枚举（**每个 start_ex 都重置控制器**）；v15.3 改 20s 退避 + boot loop 1s，20 轮 fresh-attach 纪律化探测仍未抓到 serving 窗（样本不足）。
- **第三个坑（收尾时定位，未及验证）**：**usbipd 的 stale export**——手机侧每次复位重枚举后，WSL 侧旧导出仍显示 `Attached`/`lsusb d00d=1`，但底层管道已死（写入静默丢失）。唯一一次 serving 窗（05:02）恰逢一次**新鲜的** detach→attach。下一波探测纪律：**每轮探测前强制 detach→attach→lsusb 复核**（final-e2e.sh 的 fresh() 已实现，但只有 20 轮机会，未撞上 serving boot）。
- **下一波第一件事**：Android 回退后拉 `logdump`（本波已留 `logdump-v15.bin` 基线方法），读 `usb: start failed %x` 的**具体 status**；对照 vendor UsbConfigDxe 判定是 RPM/DAL 时钟未就绪还是 PHY 路径；候选修复 = ①boot 前先 signal init event 后**sleep 5-10s** 再首次 start_ex（给平台 init 独立完成窗）②彻底去掉 boot-time 重试、只留 session 内 20s 退避 ③UsbConfigDxe 的 start 回调参数审计（loader.c:3984 注释路径）。
- 佐证数据点：成功的 04:57 boot 发生在手机经历 ~50min 静置 wedge 之后——**平台侧某个慢时钟/电源域最终就绪**的假设与数据吻合。

### 4.2 新发现（非阻塞但记账）：`panic: vnode table is full @vfs_subr.c:5705`（~218s）
- v15 的 300s cmdline 让会话跑过了 218s，暴露**vnode 表耗尽**（`1024 desired, 1024 numvnodes, 0 free`）→ pid 1 (launchd) panic → stackshot → clean return。
- v14 的 120s 会话从未到达该点（**预存问题，非本波引入**）。
- 处置：下一波要么调回 `loader_return_after=180`，要么查 vnode 泄漏（launchd 域 28 进程的 vnode 消耗，b25 120s 内健康；218s 恰为临界）。**在修复前，SSH E2E 必须压缩在 180s 内完成**（N1~N3 预算 150s，可行）。

### 4.3 次因记录（均已修但过程烧时）
- 阶段 13 `connect()` 的 `free_device_list` 后指针复用：Windows 容忍、Linux 必崩 → wave21 loader_talk 重排（修复确认有效，probe/cmd 全通）。
- WSL 侧 usbfs 权限：loader_talk 需 root（`sudo`，同 fastboot 惯例）。
- wintun 创建需管理员（ERROR_ACCESS_DENIED）→ 本轮走用户态 TCP/ICMP 降级（设计稿 §2 预案的更优变体：TCP 栈放 host 端 loader_talk，**零 Darwin 侧代码**）。
- `/tmp` 清空 footgun 再现两次（脚本一律落 /mnt/c）。

## 5. 安全与回滚状态

- boot_b = v15.3（`d117e48c…`）；slot a 安卓原装未动；userdata 未触碰。
- v15.3 在「USB 不通」时行为 = v14（one-shot 会话 + 循环自动回退到安卓），无新增风险；会话在 ~218s 有 vnode 表 panic（§4.2，clean PSCI return，无数据风险）。
- `wave21-scripts/handback.sh` watcher 在安卓回归后自动 `adb reboot bootloader → fastboot set_active a → reboot`，手机稳定交还（**若 watcher 已死，人工路径：强关 → 电源+音量下 → `fastboot set_active a && fastboot reboot`**）。截至收稿，手机已在安卓（slot a）。
- 回退链完整：v14（`1932412a…`）可随时重刷。

## 6. 下一波施工单（阶段 21.1 建议，按序）

1. **取status**：安卓回退后 `su -c dd logdump`，grep `usb:`——拿到 `start failed %x` 的具体 EFI status（本波 logdump-v15.bin 只有成功 boot 的日志）。
2. **修 start_ex**：按 §4.1 候选①（init event → 延迟首试）最可能；loader 单点改动 ~20 行。
3. **刷 v15.4** 后：`catch-and-run.sh`（已备）自动跑 N1→N2→N3（E2E 全套已写好，成功率只差 USB 服务器在线）。
4. **vnode panic**：`loader_return_after=180`（cmdline 一行）先绕过；泄漏调查另开。
5. N3 通过后：`logdump` + `set_active a` 交还（本波脚本全可复用）。

## 7. 本波教训（方法论）

- **vendor UEFI bring-up 的间歇性要在第一轮就做懒重试**（Boot #9 的教训写在 loader.c:3984 注释里，但「重试成功」与「重试搅局」的界线——churn 会杀死主机枚举——是本波用第三次刷写换来的新知识：**start_ex 每 20s ≤1 次**是安全节拍）。
- **logdump 是唯一可信的 loader 侧叙事**：USB 层的任何推断（stale export、wedge、state machine）都应尽早用 logdump 落地，而不是用 host 侧行为反推。
- **跨 WSL/Windows 的 USB 编排**（usbipd attach/detach + persisted binding + WSL keepalive）本身就是不稳定源：下一波把 watcher+keepalive 固化为脚本首部（本波已备 watch-attach.sh，但 WSL keepalive 反复死亡造成多次误诊）。
