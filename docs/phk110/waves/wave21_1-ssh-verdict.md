# 阶段 21-1 · 2026-11-08 · USB 服务通道修复轮与在线判据

> 2026-11-08 · 执行记录全循环：取证 → loader.c 补丁 → v16 构建/自检 → 自刷 → E2E 集中修复 → 判定
> **判定：本轮 v0.4「SSH 进 Darwin shell」未宣告。USB 服务器在线判据（≥1 次成功 start）已达成并有 logdump 行级证据；N1→N2→N3 数据面闭合仍被 host 侧 catch 阻塞。修复用了 1 轮（v16），第 2 轮留给下一阶段并给出施工单（§6）。**
> 镜像：boot_b = **v16**（`2e1a2532…`）；收尾时手机经 ABL 自动回退到安卓（slot a，本阶段已两次实证 ABL ~8 轮自动回退）。

## 0. 一句话结论

v16 把 阶段 21 施工单 §6 的前三项全部落地：①**status 码取证通路建成**（失败必打 `usb: try failed: start_ex %x`，屏上即见 `0x800000B`/`0x800000C`——再也不会丢码）；②**延迟首试**（init event → 5s settle → 首试）+ 20s 安全节拍重试真机验证；③F6 vnode panic 绕过（`loader_return_after=180`）真机验证（logdump 零 `vnode table is full`）。**loader USB 服务器在线判据达成**：最后一轮 boot 的 logdump 行级证明 `usb: the platform is asked up; five quiet seconds before the first try` → `usb: started`（**首试即成、零失败行**）。但 host 侧 catch（usbipd 管道生命周期 + 半启动 zombie 态识别）未能在轮内闭合 N1→N2→N3，SSH 判定留待 §6 施工单。

## 1. 判定阶梯实况

| 阶梯 | 设计验收 | 本轮实况 | 判定 |
|---|---|---|---|
| 前置 | loader USB 服务器可用（≥1 次 `usb: started`） | **logdump-v16-run1.bin 行级证据**：settle 行 + `usb: started` 同轮、零 try-failed；v16 真机验证 ~60 min 内该行至少 1 次落盘 | ✅ |
| F6 | vnode panic 不再出现（180s 窗） | logdump 零 `vnode table is full`（v15 @218s 必现 → 本轮 0 次） | ✅ |
| 取证 | `start failed` 具体码到手 | 屏幕实时码 `0x800000B`/`0x800000C`（屏幕读数）+ 二进制反查定位（§3）；logdump 端零失败码（成功的 boot 无失败行，失败的 boot 的 logdump 被后续覆盖） | ✅（码本体）/ ◻（码→失败轮的逐轮对账，见 §5） |
| N1 | 环回对账 | 数据面三端代码不变（v15 已刷入真机实证）；本轮无 serving 窗被 host 抓到 | ☐ |
| N2 | `ping 10.0.0.2` | 同上 | ☐ |
| N3 | `ssh root@10.0.0.2` Darwin shell | 同上 | ☐ 未闭环 |

## 2. 取证（步骤 1 的完整记录）

1. **首轮拉取**（`logdump-v16-base.bin`，`fd0c9558…`，10:48）：内容 = v15.3 最后一轮执行（04:57 成功链）：`usb: started` 首试、4 会话、en0 ×4、SpringBoard 跑满 300s+、尾端 stackshot。**`usb: start failed` 全分区 0 命中**。
2. **历史全查**：17 份 logdump（v3…v15）逐份 grep `usb: start failed` = **全部 0 命中**。机理：`write_logs` 每次 boot 从 LBA 0 覆盖（loader.c `write_logs` → `bio->write_blocks(…, 0, …)`），失败轮的日志必被最后一个成功轮覆盖——**status 码在 logdump 通道上结构性不可追溯**，只有屏是活通道（这就是补丁加失败码打印的依据）。
3. **补丁后闭环**：屏上实时出现 `0x800000B` 与 `0x800000C`（"一直在报"）——取证通路生效，码族与 Boot #9 时代的 `0x80000000C` 同源。
4. **二进制反查**（senna_bc vendor 驱动，`llvm-objdump` 全反汇编 grep 立即数）：
   - `UsbDeviceDxe.efi` / `UsbfnDwc3Dxe.efi`：**无** `mov w?, #0xb/0xc` 返回构造（两码不出自这两层）。
   - `UsbConfigDxe.efi`：**命中**。状态译码器 `@.text 0x11038`（跳表 `0x16ca3` 区，selector w2 ≤ 6）：case 入口 `0x11088` → bit2 置位 → **`0x110d4: mov w0,#0xb; ret`**；bit3 置位 → **`0x11090: mov w0,#0xc; ret`**；相邻 case 返回 1/2/4/6/7/9/0xa/0xf/0x11/0x12。调用点 `@0x11240`：`bl 0x11038`，入参 = 以 **12 字节步进**的 core 状态表扫描（`madd x21, x9, #0xc, x10`）——即 per-core 状态机（DevSm 族）状态不符译码。**结论：两码 = vendor 自定义"core 状态不符预期"族，非标准 EFI status**（EFIERR(11)/EFIERR(12) 的 vendor 语义占用）。
5. **真机验证终验拉取**（`logdump-v16-run1.bin`，`8ae7fc82…`，12:33，v16 最后一轮链）：`payload entry 'loader.efi' size 12800` = **75,776 B = v16 loader 字节机上确认**；`usb: the platform is asked up; five quiet seconds before the first try` + `usb: started`（**首试即成**）；4 会话 × en0 attach + `en0 has 10.0.0.2/30`；**零** `vnode table is full`；零 try-failed 行。
6. **收尾拉取**（`logdump-v16-final.bin`，`ec271f52…`，13:10，安卓回退回归后的最后一轮链）：**同一健康形态复现**——settle 行 + `usb: started`（又是首试即成、零 try-failed）、4 会话 × en0、零 vnode panic、loader 字节 0x12800。**v16 的 USB 首试成功在两份独立 logdump 中复现**——start 成功率并非 ~1/10，host 侧 catch（F8/F9）才是 N1-N3 闭合的真实瓶颈，§5 的 host 活跃度候选假设进一步加权。

## 3. 修复（v16，修补丁脚本 `wave21-scripts/patch-loader-v16.py`）

三处改动（每处带唯一性断言，diff = +55/−20 行左右，全部在 `usb_start`/`usb_start_attempt` 域内）：

1. **`usb_init_kick()` 新助手**：init event（create once + signal）从 `usb_start_attempt` 内提出，供 `usb_start` 在**首试前**独立 signal（重试路径每失败重新 signal 的原行为保留）。
2. **失败码打印**：`usb_start_attempt` 失败路径 `print("usb: try failed: start_ex %x\n", s)` ——屏/logdump/staged 三通道取证。
3. **`usb_start()` 重排**：create EVT_TIMER → **settle 窗 5s**（`TimerRelative` 50,000,000 + `wait_for_event`——泵固件事件队列含喂狗；tick 建不起则 5×1s stall 回退）→ 首试 → 失败后 **20s 节拍**重试（`TimerPeriodic` 200,000,000，原 1s/10,000,000 churn 弃用——v15.2 教训"每个 start_ex 都复位 DWC3"）→ 30s boot 窗放弃、交给 watch loop 的 `usb_lazy_start`（20s 退避，不变）。

## 4. 构建/自检/刷写（v16 四件套 + 修补丁脚本，全部入库）

| 件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-cmdline-v16.bin` | `675e917817c462ca` | 471 B：`loader_return_after 300→180`（F6 绕过），`en0_addr=10.0.0.2` 保留，其余逐字节钉死；预算 593/608 |
| `device-layer/udon-hakios-payload-v16.bin` | `bd2f26dcab50cf74` | 23,386,120 B；7 条目（`usb` 在列）；**kernel/kernel.ver/resident/ramdisk 与 v15 条目逐字节全等**（en0 驱动在内核，内核不动——17c905ec 复用），loader/cmdline 为新字节 |
| `device-layer/udon-hakios-grafted-v16.img` | `2e1a2532261efe92` | 192 MiB；FD `8924cb67…`/shim `108ce972…` 未动；`udon-hakios-grafted-v16.report.json` = `62c95696…` |
| `device-layer/hakios-kernel-v16.bin` | `17c905ec240a8b00` | = v15 内核（复用声明件） |
| `wave21-scripts/patch-loader-v16.py` | — | 带唯一性断言的补丁脚本（3 hunks，见 §3） |
| `wave21-scripts/make-cmdline-v16.py` / `make-payload-v16.sh` / `verify-udon-hakios-v16.py` | — | 构建/自检链；**verify 49/49 全绿**（v15 的 48 检 + settle 行断言 + loader 字节钉死 `d612958d…`） |
| `logdump-v16-run1.bin` | `8ae7fc82ae32947d` | v16 真机验证取证基线（512 MB） |
| `logdump-v16-final.bin` | `ec271f52079db4f9` | v16 收尾轮取证（512 MB，首试成功形态复现） |

刷写：WSL root fastboot 标准通道（`Sending 'boot_b' (196608 KB) OKAY` / `Writing OKAY`）+ `set_active b`；loader.efi v16 = `d612958d…`（75,776 B，-Wall -Wextra 零警告）。

## 5. E2E 集中修复实录（hunt v1→v5，~2.5 h，~12 个 boot 循环）

**host 侧渠道病理（本阶段最大新知，比任何单个失败都值钱）**：

- **F8（新）＝半启动 zombie 态**：失败的 start_ex 把 DWC3 留在"ep0 可枚举、bulk 端点未武装"态——host 能读描述符（loader_talk dump 全通过）但 `bulk-OUT` 写超时（`LIBUSB_ERROR_TIMEOUT 0/13`）。该态可存续整个 180s 会话，host 侧无法从"可见性"区分 zombie 与真 serving（两者都是 `18d1:d00d`）。唯一一次"OUT 进 IN 超时"（11:42:37）= lazy 重试刚武装了 RX 又被下一次 20s 复位打断的瞬间。
- **F9（新）＝usbipd 管道生命周期**：每次 loader 复位设备消失→导出死；重现时持久绑定 auto-attach 可能挂到**已消失的旧设备实例**（Windows 显示 `Attached`、WSL `lsusb` 看不见）——管道死。唯一复活法 = `detach→attach` 手术。但手术本身有双刃：落进 loader 的 start_ex 窗口 = 枚举被拽走（start 失败新诱因）。
- ** hunt 版本学**：v1（90 轮盲扫）→ v2/v3（fresh-every-N-miss / 修复分类器）→ v4（每 miss 手术——**手术风暴反而毒化 start**）→ **v5（终版：每 dark→visible 代际仅一次手术 + 5s 纯探测 + 应答即整链 E2E）**，400 轮 × 5s 预算。v5 在线期间未再抓到 serving 窗。
- **成功率观察**：v16 在机上 ~12 循环中，logdump 证实 ≥1 次 `usb: started`（最后一轮链，首试即成）；hunt 视角 0 次可应答窗。v15.3 时代 05:02 的可应答窗（getvar/oem 全通）发生在 watcher 活跃 fresh-attach 期——**host 活跃度与 start 成功率的正相关**是本轮最强（但未证实）的因果候选：probe/surgery 的 host 传输活动本身可能在给 DWC3 喂枚举事件；死管道 = 零枚举驱动 = start_ex 内部等待超时（0xB/0xC）。反证也存在（boot #1 的 7.5 min 连续可见窗内 probe 全超时——该窗可能是 zombie 而非 serving）。
- **ABL 回退观察**：boot_b 连续循环 ~8 轮（~50 min）后 ABL 自动回安卓并 `set_active a`（两次实证：12:02、收尾时）——**ABL 回退本身就是热循环清零器**，下一轮 E2E 的"回到 v16"操作 = `adb reboot bootloader → set_active b → fastboot reboot`（本轮已演练 2 次，`wait-android-flash-v153.sh` 模式可复用）。

## 6. 下一阶段施工单（阶段 21.2 建议，按序；修复预算第 2 轮）

1. **【先做，零代码】冷启动判据卡**：现场一次强制断电（长按电源 10s+ / 任何断电方式）→ 上电后首个 loader boot 的 start_ex 是"冷电源域首试"。若冷启首试成功（logdump/hunt 双确认），根因坐实 = **热复位（PSCI reset）留下 USB 电源域半初始化态**，操作配方 = "冷启动 → 单轮 E2E（150s 预算内）"，一轮闭环。本轮已排队待安排，未及执行。
2. **v16b loader 加固（单刷一次带齐）**：
   a. **去掉会话内 lazy churn**：`usb_lazy_start` 的 20s 重试在全部观察中零成功、且是 F8 zombie 的复位源——改为"boot 期只试，运行期不再碰控制器"；
   b. **settle 5s → 25s**（首试延迟加长一档；boot 期多等不占 180s 会话预算）；
   c. boot 期重试从 2 次放宽到 3 次（5s/30s/55s，60s 窗放弃）——每一次都是干净代际，无 churn 连锁；
   d. （可选）boot 期全失败时打印一次性 `usb: warm-boot start failed; the next cold boot is the clean try` 行，给下一轮取证对账。
3. **host 侧管道守护固化**（`wave21-scripts/`）：hunt5 终版范式 + `usbipd` auto-attach 死管道检测（`Attached` 但 `lsusb` 无 → 手术）；探测期间禁止对 start 窗口手术。
4. **status 码语义深挖**（若 1/2 后仍失败才做）：UsbConfigDxe `@0x11038` 译码器入参（core 状态表 12B 步进结构）静态重建，把 0xB/0xC 映射到具体 DevSm 状态名；对照 `UsbPwrCtrlDxe` 的 rail 序（`UsbConfigDxe` 依赖它的 `Failed to toggle controller mode` 路径）。
5. N1→N2→N3 执行册（`wave21-scripts/hunt5-v16.sh` 终版范式直接复用：抓到应答即 oem run → 50s → N1(40s) → N2 → N3 tunnel ssh，总预算 ~150s < 180s）。

## 7. 安全与回滚状态

- boot_b = v16（`2e1a2532…`）；**收尾完成：手机已回安卓（slot a 活跃，adb 在线，`sys.boot_completed=1`），回到安卓**；userdata/darwin 未触碰。v16 的"USB 不通"行为 = v15.3 的安全行为（one-shot 会话 + ABL 自动回退到安卓），无新增风险；F6 已消除（180s 窗）。
- 回退链完整：v15.3（`d117e48c…`）、v14（`1932412a…`）可随时重刷；下一轮从安卓直接 `adb reboot bootloader → set_active b → fastboot reboot` 即回到 v16 循环（`wait-android-flash-v153.sh` 模式，本轮已演练 2 次）。

## 8. 本阶段教训（方法论）

- **logdump 是从 LBA 0 覆盖写的**——"等失败轮的日志进 logdump"在结构上不可能；失败取证必须当轮在场（屏/打印），或轮后立即拉盘且该轮必须是最后一轮。
- **hunt 的手术（detach/attach）是双刃剑**：既是管道唯一的复活法，也是 start_ex 的杀死枚举。手术必须按设备代际（dark→visible）节流，绝不按 miss 节流。
- **可见 ≠ 可用**：zombie 态（F8）让 `18d1:d00d` 的"在总线"完全失去语义；只有 `getvar` 应答才算 serving。
- **pkill 自匹配**：`pkill -f hunt-v16.sh` 会杀掉包含该串的调用 shell 自身（`-c` 参数也在 cmdline 里）——用 `pkill -f 'hunt[0-9]-v16'` 括号正则规避。
- WSL VM 生命周期 = usbip 生命周期：keepalive 会话是基础设施，不是可选项。
