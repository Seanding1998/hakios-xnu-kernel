# 阶段 45 · 2026-11-12 · v36 上机四门判定：GPU 真·首帧达成

> 2026-11-12 · 阶段 45 执行记录（衔接 wave42 交接：v35 已刷入、循环中；配方 = loader `5de055ea` 冻结 + 内核 `5b77b418`（wave41 GPU 修复 + wave43 电量驱动同树）+ 载体 `51a030c3`（wave41 结构化验收器 gl_test）+ cmdline `gpu=1` 追加 `fuelgauge=2`）。
> 使命：组装 v36 → 三门刷入 boot_b → 门 A（步进回归）→ 门 B（fence nonce 探针，P0 设备级首测）→ 门 C（gl_test 真·首帧轮，wave41 §6 判据）→ 门 D（电量 S1-S3）→ 完成登记。
> 红线执行：boot_a 零字节未触碰 ✓（两次刷写尝试都在 boot_b 的 **download 阶段**失败，分区写从未发生——fastboot 语义 = download 进 RAM 暂存，`Writing 'boot_b'` 行从未出现）；零变砖 ✓（boot_b 仍为 v35 `6558d303`，v36a 的 identity/slot 两门先 PASS 过 = ABL 可用性当时在证）；wsl --shutdown 零次 ✓；verify 绿的产物零重跑（loader/kernel/载体三个冻结品 sha 首尾一致）✓；wave42/43/44-scripts 零触碰（可执行引用除外，如 revive-v26.py/tunnel25w.py 的既有调用路径）✓。
> 证据分级：[实证] = 文件/字节/sha/行号可复现；[实测] = 本阶段设备实测；[W42] = wave42-report.md §8 的交接事实。

---

## 0. 判定（先行）

> **08:41 续命令更新：用户强制重启解楔 → 新鲜 fastboot（busid 1-1）直刷 OKAY → boot_b = v36 `e6ca0b43` 真机验证成功 → 四门全部有终态：A PASS / B PASS / C hardware-DONE（用户目击屏幕三角形，人机双确认）/ D PARTIAL（S1 逐字命中、S2 阴性档案、S3 燃油计无应答不喂）。真·首帧达成。§8 是补跑轮全文。**

1. **v36 打包全绿**：payload `udon-hakios-payload-v36.bin` = **`0a70ec0a`**（27,496,536 B）、graft `udon-hakios-grafted-v36.img` = **`e6ca0b43…`**（192 MiB），**verify-udon-hakios-v36.py 72/72 全绿**（`wave45-scripts/verify-v36.log`）。四件组装件逐字钉位：loader `5de055ea`（90,112 B，冻结，字节等于 v35 payload 条目）＋内核 `5b77b418`（15,121,752 B，≠v35 条目，wave41/43 字符串钉：`the gauge answers`/`the PMIC arbiter is version`/`adreno_ddr_type`/`gras_nc_mode_cntl`/`fuelgauge_poll_us`）＋载体 `51a030c3`（8,089,600 B NXSB，**容器内 `/bin/gl_test` 经树内 apfs.py 真实抽取 = `802522ff` 69,408 B——wave41 结构化验收器二进制逐字节在证**）＋cmdline 489 字符 = v35 文本逐字节 + ` fuelgauge=2`（110+489=599/607 预算内）。
2. **真机验证 = CONFIRMED（08:41，用户到场后）**：用户长按电源强制重启解除了楔死 gadget → 新鲜 ABL fastboot 出现在 busid 1-1 → 事先挂好的捕捉器 `fastboot-catch-v45.sh` 三门全过、OKAY 断言、直刷（`wave45-scripts/flash-v36-fast084101.log` + `fastboot-catch-v45.log`）。**boot_b = v36 `e6ca0b43` 已刷入、循环中**（链式守望器按看护进程卫生规则先行结束，防止重复刷写）。07:00 前的 BLOCKED 全记录保留在 §3（半启动残留看护的根因定位 + 楔死取证——两段式根因对 wave46 仍是有效输入）。
3. **门 A = PASS（步进回归）**：步 1-21 全 `done`（10/11/12 被 gpu=1 的 skip mask 0x1c00 跳过，逐字符合预期）；**步 20 `THE 3D CORE TAKES COMMANDS` ✓、步 21 `the page reads 0x600dc0de: THE 3D CORE WRITES OUR MEMORY ON COMMAND` ✓、`THE GPU STAYS ON for the system to draw with: the service HakiosGPU` ✓**——wave41 修复后的内核（CP_THREAD_CONTROL 两字包增量）步进机完整复现。证据源 = `/dev/ufs_logdump`（logdump 分区的 ufs 块节点，上一世代的 loader 块 + 内核日志；每世代同 boot 路径）。
4. **门 B = PASS（fence nonce 探针，P0 设备级首测）**：`FENCE_PROBE: PASS the device writes the fence number back and runs the IB (the wave41 fence event works on this hardware)`——双 nonce `0x45f000c0/0x45f000c1` 写回内存逐字命中、fence 序号 2→3 递增、**wave44 §5-3 预测的 WPTR 重写分支真实触发一次**（fence 1 首轮未完成 → 重发 → 完成）、timeouts 0；附赠 NC_MODE 契约双读：chip id `0x7030002` ✓、highest bank bit `16` ✓（`w45-gates0842-probe-run-01.out`）。
5. **门 C = hardware-DONE（真·首帧，wave41 §6 判据全绿 + 用户目击）**：`RENDER backend=hw renderer=FD725`（真硬件 freedreno）、五采样点逐字命中（235,12,8)/(12,235,8)/(10,10,235)/(68,69,118)/(26,26,51) alpha 255、覆盖率 **26% 正中几何窗**、`PRESENT_CALL_OK`、`GL_RC=0`、1080×2400 drawn 19 ms readback 26 ms（`w45-gates0842-gl-01.out`）。**用户在场目击了屏幕上的三角形**。softpipe 对照无（不需要）。
6. **门 D = PARTIAL（wave43 §7 口径）**：**S1 总线 PASS**（`fuelgauge: the PMIC arbiter is version 0x70000000, 768 channels` 逐字命中）；**S2 外设档案 = 阴性记录**（PM8350B 四块 0x10/0x12/0x13/0x15 均不在本机仲裁器表——记而不判按设计完成，阴性是 wave46 的修复输入）；**S3 燃油计 FAIL**（`the gauge does not answer, or answers nonsense: nothing is fed to the battery`——bq27541 无应答 → 按 wave43 诚实边界不喂 → `battery_soc = -1` 未喂哨兵、`battery_present = 0`、温度 -273 哨兵）。sysctl 读链本身 10/10 oids 双采样在证（验收器 `battery_probe 325c24d8`，因载体无 /usr/sbin/sysctl 而 sysctlbyname 直读）。fuelgauge=1 备用静态模式本轮未行使（真读数主路径已走到 S3 才停，静态不救 S3）。
7. **遗留 wave46 输入**：①S2 阴性 = 本机仲裁器表里没有 SMB5 四块（buttons.c walk 的表布局假设在 PHK110 上不成立——对照 buttons 的实际表找充电块真位置）；②S3 = bq27541 I2C（GPIO26/27）无应答（上拉/复用/休眠态三查）；③USB 口电压/电流与 VADC 回退仍为 wave43 的 TODO。

## 1. 基线与冻结点（首尾对账）

| 工件 | 本阶段首查 sha256（前16） | 本阶段尾查 | 状态 |
|---|---|---|---|
| `~/hakios/kernel/hakios-kernel`（v36 内核，冻结品） | `5b77b418b8c59974` | 同（verify 内字节等断言） | 冻结未动 ✓ |
| `~/hakios/kernel/userland/root.apfs`（v36 载体，冻结品） | `51a030c34e98d0a3` | 同 | 冻结未动 ✓ |
| `~/hakios/kernel/xnuloader/loader.efi`（冻结品） | `5de055ea897d7241` | 同（90,112 B） | 冻结未动 ✓ |
| `device-layer/udon-hakios-payload-v35.bin`（v35 基准） | `82add009`（W42 记账） | 同（被 assert 消费） | ✓ |
| `device-layer/udon-hakios-grafted-v35.img` | `6558d303…` | （机上 boot_b 仍为它） | ✓ |
| FD `8924cb67` / shim `108ce972` | W42 钉 | verify PASS 逐字 | ✓ |

## 2. v36 组装账（[实证]）

- **配方执行**（当时的工作安排定，未擅改组件）：make-payload-v36.sh 从 **v35 payload 实物**（不是树）提取七条目，逐条 assert v35 锚（kernel `55a8d40f` / loader `5de055ea` / ramdisk `c2780842` / cmdline 478 B 尾 `gpu=1`）；swap 三件：kernel ← 树 `hakios-kernel`（sha 钉）、ramdisk ← 树 `root.apfs`（sha 钉）、cmdline ← v35 文本 + ` fuelgauge=2` + NUL（wave43 §8 追加规则）；loader/resident/kernel.ver/usb **字节等于 v35 条目**（打包后逐条目再 assert）。
- **payload v36** = `0a70ec0aabad…`（27,496,536 B）；**graft v36** = `e6ca0b43372634c8c8ab1a459d6c63902bcb77599415d8a9fa82696a3655b7de`（192 MiB，`udon-hakios-grafted-v36.img.report.json` 在案）。FD/shim/stock 三方输入 sha 钉先于打包（wave34 刹车教训内建）。
- **verify 72/72 全绿**（`run-verify-v36.sh` → `verify-v36.log`，"ALL 72 CHECKS PASSED"）：v35 verify 家族语义逐条保留 + v36 新钉——①kernel ≠ v35 条目且 sha `5b77b418` + wave41/43 五字符串；②ramdisk = 传入的 root.apfs 字节等（51a030c3）且 ≠ v35 条目；③**`/bin/gl_test` 验收器内容钉**：树内 `tools/apfs/apfs.py` Container→Volume.lookup→Inode.contents 真实抽取，sha `802522ff` 69,408 B（wave41 三连构建可复现值；APFS 压缩使字节 grep 不可能，抽取是唯一诚实路径）；④cmdline = v35 文本 + ` fuelgauge=2`（两处独立断言：graft 条目字节等 payload 条目；条目文本逐字节 = v35+追加）；⑤loader 冻结钉（字节等 v35 条目 + 90,112 B + GEN-1..4 串族 + F10 语义常量钉 XNUP/PAYLOAD_BASE movz/movk ≤16 条邻近全保留）。
- **cmdline 实值**（verify 日志逐字）：`serial=0 loader_return_after=600 small_cores_after=0 touchscreen=1 buttons=1 buttons_map=1 buttons_core=0xc400000 buttons_cnfg=0xc42d000 buttons_obs=0xc440000 cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws ufs=2 ufs_write=1 var_hfs=ufs_darwin_data root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2 gpu=1 fuelgauge=2`（489 字符）。

## 3. 真机验证时序与楔死取证（[实测]，wave46 修复输入）

| 时刻 | 事件 |
|---|---|
| 04:35–05:49 | watcher `await-android-and-flash-v36.sh` 武装；设备继续 v35 槽 b 世代循环（xnuloader gadget 驻留；期间一次 0000:0002 描述符失败半启动状态，[W42 §8.4 同款]跨窗自愈至干净枚举） |
| 05:49:50 | xnuloader 仍在总线（v35 loader 窗活跃）——这是 v35 世代循环的最后可见态 |
| ~05:50 | **世代转换：gadget 变为 18d1:d00d "Android"（ABL fastboot），非 adb 命令路径**——loader 窗到期冷复位后 ABL 自己选择了 fastboot（与 [W42 §8.4] 的"回退翻槽到 a"不同路；本次 ABL 停在 fastboot，未翻槽引导 Android） |
| 05:50:23–39 | **v36a 刷写**（`flash-v36-v36a.log`）：graft sha 钉 PASS → attach 2-2 OK → `getvar product: taro` PASS → `current-slot`（b，无需 set_active）→ `Sending 'boot_b' (196608 KB)` **FAILED (Write to device failed in SendBuffer() (Success))** @05:50:40。`Writing 'boot_b'` 行从未出现 = download 阶段死，boot_b 零写入 |
| 05:51–06:03 | 楔死形态确立：`usbipd attach` 一次 `Device in error state`、多次 `used by Windows`；WSL fastboot 偶见 `3c268ac3 fastboot` 后即失；WSL dmesg：`vhci_hcd: connection closed` → `usb 1-1: USB disconnect`（attach 后 ~1 s） |
| 06:03–06:36 | 自救全家桶逐项尝试并留档：adb kill-server（无效果）/ `pnputil /restart-device` + `Disable-PnpDevice`（**Access denied**，shell 无管理员）/ `usbipd bind --force`（**requires administrator**）/ `--auto-attach` 看护（连接保活成立，lsusb 稳定见 `18d1:d00d Google Inc. Xiaomi Mi/Redmi 2 (fastboot)`，但 getvar 仍 `Status read failed (No such device)`）/ sysfs `authorized` 0→1 端口复位竞速（未落）/ `fastboot reboot` 竞速 ×15+（三次打出 `Rebooting` INFO 回显但无 OKAY，总线无重枚举特征）/ Windows 侧 fastboot.exe（驱动不同，零可见） |
| **06:35-06:37** | **定位根因**：`ps -ef` 揪出 11 个前波半启动残留看护进程（wave21 ×5 自 Nov 8、wave42 ×2 自 00:42/01:53、各自 tee）——它们每 2 s 无条件 detach 2-2 上的任何 Attached 18d1:d00d；全部结束。此后三次干净重试（v36c/d/e/f）：一次 `already attached to a client`（本阶段自己早先误建的 `--auto-attach` 孤儿 usbipd.exe，pid 22488，已结束）→ 最后 stale vhci 活连接上 `fastboot devices` **稳定可见**（`3c268ac3 fastboot`，lsusb 1-1 在位）但 `getvar` 无应答、sudo 端口复位（authorized 0→1）后同样无应答——设备侧 fastboot 应用坏态确认，需整机断电复位 |
| 06:50 起 | `unwedge-reboot-loop-v45.sh` + `await-android-and-flash-v36.sh` 双看护重新武装（半启动残留已清场，看护不再自相残杀；若 ABL gadget 自愈或在任何窗里应答一次 `fastboot reboot`，手机即脱困） |

**楔死定性（06:37 修订版）**：两段式——①**主机侧（已定位根因，07 分结束在案）**：五个前波半启动残留看护（wave21 ×5 + wave42 ×2）每 2 s 无条件 detach 2-2 上的 Attached 18d1:d00d；v36a 的写入与之后 45 min 的全部"flap"症状（`vhci_hcd: connection closed`、`Device in error state`、`used by Windows`、`already attached to a client`——包括本阶段自己误建的 `--auto-attach` 孤儿进程两次）都是这场自相残杀的表症；wave42 23:51 刷写成功与本次失败的差异 = **半启动残留看护当时不在场**（其 ps 启动时刻 00:42/01:53 均晚于 23:51）。②**设备侧（残余，未解）**：半启动残留结束后的干净活连接上 ABL fastboot 应用仍不应答（枚举健康、bulk 无响应、sudo 端口复位无效）——ABL gadget 实现在"传输夭折 + 反复总线 churn"后的自愈能力缺失（与 wave38 在 loader 侧修的 DWC3 abort/configure 家族同源），**归因等级 = 假设**（无串口/无 ABL 日志）；整机断电复位即清零。修复建议留给 wave46：①刷写窗一律走 **adb reboot bootloader 的干净 ABL**（W42 23:51 的已证路径——本次失败的直接诱因是"世代回退半路的 ABL fastboot"，它从未被刷写验证过）；②半启动残留看护的进程卫生纪律（下节）。

### 3.1 进程卫生教训（wave46 起生效）

看护脚本是长命进程，会跨波存活并咬自己人：本阶段接手时树上有 5 个 Nov 8 的 `wave21-scripts/watch-attach.sh` + 2 个 wave42 看护仍在跑。**纪律：①每个看护必须在启动时把自己的 pid + 域写进 `waveNN-scripts/progress.log`，收尾时杀掉；②接手波先用 `ps -ef | grep watch` 清场再动手；③detach 看护必须带 gadget 名过滤（本阶段 `watch-attach-v45.sh` 只 detach xnuloader 名），永不无条件 detach。**

## 4. 设备无损的证据链（零变砖红线对账）

1. fastboot 刷写协议 = download（RAM 暂存）→ OKAY → Writing（分区写）。v36a 的输出只有 `Sending … FAILED`，`Writing 'boot_b'` 不存在 → **boot_b 分区零字节改动**，仍为 v35 `6558d303`。
2. v36a 的 identity/slot 两门 PASS 发生在写入尝试**之前**——当时 ABL 响应正常，反证楔死由大传输夭折触发，而非 ABL 全死。
3. boot_a：本阶段所有 fastboot 交互零 `flash boot_a`（grep flash 日志在案）；resume 类 set_active 只发生在 v36a 的 slot 门内（返回已是 b，未执行）。
4. 手机供电 = USB 主机口（ABL fastboot 充电），电量不耗尽风险无。
5. 门禁回退链完好：watcher（Android 窗→刷）+ unwedge loop（fastboot 复原）双看护到用户醒来。

## 5. 判定表（六分支式）

| 分支 | 判定 |
|---|---|
| A 打包+verify 全绿 | **✓——v36 payload `0a70ec0a` / graft `e6ca0b43` / 72/72（§2）** |
| B 真机验证三门 CONFIRMED | **✓——08:41 用户强制重启解楔 → 新鲜 fastboot（1-1）→ 三门全过 OKAY 断言，boot_b = v36 已刷入循环（§0.2；07:00 前的 BLOCKED 全记录保留在 §3，半启动残留看护的根因定位对 wave46 有效）** |
| C 门 A 步进回归 | **✓ PASS——步 1-21 全 done（10-12 按 skip mask 跳过）；步 20/21 真值行逐字复现 + THE GPU STAYS ON（`verdict45-gatea.txt`，证据源 `/dev/ufs_logdump`）** |
| D 门 B fence 探针 | **✓ PASS——双 nonce 写回 + fence 2→3 递增 + WPTR 重写分支真实触发一次 + timeouts 0；NC_MODE 契约 chip id/HBB 双读同证（`w45-gates0842-probe-run-01.out`）** |
| E 门 C gl_test / 门 D 电量 | **C = hardware-DONE（FD725 真硬件、五采样点+26% 正中、PRESENT_CALL_OK、GL_RC=0，用户目击三角形）；D = PARTIAL（S1 逐字命中 / S2 阴性档案 / S3 gauge 无应答不喂——wave43 口径，§8.3）** |
| F 编造/域外触碰 | **✗——每行判定都带盘上物证文件；wave42/43/44-scripts 零改动；boot_a 零触碰；冻结三品零重建** |

## 6. 交接清单（wave46 / 用户晨起）

1. **用户动作（唯一需要人的一步）**：手机**长按电源 ~10-15 s 强制重启**（或电源+音量下）。楔死 gadget 随整机复位消失。此后全自动：boot_b=v35 循环 → ~1-2 h 内 ABL 回退 Android → watcher 自动 adb reboot bootloader → 三门 → flash v36 → OKAY → 门 A-D 由 `gates-run-v45.py` 自动跑。（若想跳过等待：重启后手动 `adb reboot bootloader` 再跑 `flash-bootb-v36.sh --fb`。）
2. **核对清单**：`usbipd list` 无 18d1:d00d "Android" 残留 → `bash wave45-scripts/flash-bootb-v36.sh`（EXPECT_SHA 已钉 e6ca0b43 全串）→ 见 `FLASH CONFIRMED` → `python wave45-scripts/gates-run-v45.py --deadline-minutes 240`。
3. **判定文件落点**：四门 verdict 写 `wave45-scripts/verdict45-gate{a,b,c,d}.txt`（gates runner 自动），过门后把 §5 表的 NOT RUN 行改判 + 本文档 §7 补证物行。
4. **楔死根本修复（wave46 候选）**：ABL gadget 的 bulk-Out 夭折自愈（对照 wave38 loader 侧 GEN-1..4 的同族修复思路）；短期纪律 = **刷写只走 adb 干净 reboot 的 ABL**（永不刷"世代回退半路"的 fastboot gadget）。
5. **工具复用提示**：`gates-run-v45.py` 的门 A 是 klog HEAD 拉取（步进行在日志头部）；门 B 探针已带 WPTR 重写分支（wave44 §5-3）与 0-patience 轮询（避开内核 1 s no-answer 一票否决栅栏）；门 C 的 gl_test 绝对路径链 `/bin/gl_test`→`/redwood/bin/gl_test`（v35 时代 GL_RC=127 教训内建）。

## 7. 留档路径

| 件 | 路径 |
|---|---|
| payload 组装器（v35 实物提取 + 三件 swap + 逐条目 assert） | `wave45-scripts/make-payload-v36.sh` |
| graft 组装器（FD/shim/stock 三钉） | `wave45-scripts/make-graft-v36.sh` |
| verify（72 检查，含验收器抽取钉） | `wave45-scripts/verify-udon-hakios-v36.py`（适配器 `adapt-verify-v36.py`）、`run-verify-v36.sh`、`verify-v36.log` |
| 刷写链（EXPECT_SHA 钉 + Android 电池快照增量） | `wave45-scripts/flash-bootb-v36.sh`、`flash-v36-watch.log`、`flash-v36-v36a.log`（FAIL 取证） |
| 门 B 验收器（源码 + Mach-O） | `wave45-scripts/fence_probe.c`、`fence_probe`（7843d517，不进 git，构建行在源码头注） |
| 四门猎手 | `wave45-scripts/gates-run-v45.py` |
| 看护三件 | `wave45-scripts/await-android-and-flash-v36.sh`、`unwedge-reboot-loop-v45.sh`、`watch-attach-v45.sh`（+ `unwedge-v45.log`） |
| 流水账 | `wave45-scripts/progress.log` |
| 阶段日志 | `docs/waves/wave45-v36-firstframe.md`（本文） |

## 8. 补跑轮（09:0x–09:20：门 A/D 拉取修复 + 四门终态）

> 续命令的三条：诊断门 A/D 拉取秒败 → 修完补跑 → 全门改判登记。runner 三个 run-id：gates0842（当时的工作安排直起，B/C 两门产出后按卫生纪律结束）、gates0903（marker 修后首跑，抓出两个次级 bug 后止损）、**gates0907（终版，A/D 落判）**。

### 8.1 门 A/D 秒败根因（一句话 + 三层修）

**根因一句话：远端 shell 是 zsh，`==MARKER==` 这类以 `=` 开头的词触发 zsh 的 `=cmd` 路径展开（词展开为"名为 cmd 的命令的路径"），展开失败即中止整条命令行**——`zsh:1: =SYSCTL-1== not found`（`w45-gates0842-battery-01.err` 尾行）→ rc=1、0 stdout、0.3 s，与连接无关（同会话 probe/gl 全过）。只有用了 `==…==` 回显的 klog/battery/klog2 三个拉取中招；knock（`echo WAVE21-SSH-OK`）与 probe/gl（无 `=` 词）全过，完美解释了"部分命令秒败、部分正常"。

修复三层：①**所有 echo marker 加引号**（`echo '==KLOG-DONE=='`）——ok_check 的 grep 字符串不变；②门 A 的输出路径修正：`/dev/logdump` 在 51a030c3/flash-boot 载体上**不存在**（探查轮 ls 实锤），改走 **`/dev/ufs_logdump`**（logdump GPT 分区的 ufs 块节点，wave16 的 129 分区节点族；loader 在每次复位时把上一世代的 loader 块 + 内核日志合成进去，而每世代以相同方式引导同一个 v36——上一世代的步进行就是本构建的步进证据）；③门 D 的 `/usr/sbin/sysctl` **不在载体 PATH**（探查轮 `command not found` 实锤）→ 照 fence_probe 模式造 **`battery_probe`**（Mach-O arm64 `325c24d8` 65,944 B，`sysctlbyname()` 直读 wave43 注册的 10 个 oid），传输 + sha 钉 + 双采样照门 B 范式。

### 8.2 次级 bug 两枚（gates0903 抓出，gates0907 修掉）

1. 步进行正则漏字面 `step`：驱动行格式是 `adreno: step 1: done`（带 "step" 字样），我写的是 `adreno: (\d+): (done|FAILED)` → steps 恒空 → 门 A 在只有步 1-5 的截断窗口上误报 REGRESSED 并触发止损（MARCH STOP）。正则改 `adreno: (?:step )?(\d+): (done|FAILED)`。
2. grep 截断与窗口错位：`head -80` 把步进行截在步 5（一步的寄存器细目行很多，全 march 数百行）；`tail -c 1M` 读的是 512 MB 分区的尾部而非内核日志尾部（内核日志在分区头部，v23 时代 compose 实测 ASCII 跨度 ~1.4 MB）。修：`head -700` 行帽 + 头 4 MB 抓步进 + 头 8 MB grep fuelgauge/HakiosBattery 取行。

### 8.3 四门终态物证行（全部在盘）

**门 A（`verdict45-gatea.txt`，47 KB adreno 全文 + 判定头）**：
```
verdict: PASS
steps seen: 1=done 2=done 3=done 4=done 5=done 6=done 7=done 8=done 9=done 13=done 14=done 15=done 16=done 17=done 18=done 19=done 20=done 21=done
step 20 THE 3D CORE TAKES COMMANDS: True
step 21 0x600dc0de written: True
THE GPU STAYS ON: True
  adreno: 20: THE 3D CORE TAKES COMMANDS
  adreno: 21: the page reads 0x600dc0de: THE 3D CORE WRITES OUR MEMORY ON COMMAND
  adreno: THE GPU STAYS ON for the system to draw with: the service HakiosGPU
```
（10/11/12 被 `steps up to 21, without those in mask 0x1c00` 跳过 = gpu=1 快速路径的预期形态，与 wave37 一致。）

**门 B（`w45-gates0842-probe-run-01.out`，08:44:58）**：
```
FENCE_PROBE: chip id 0x7030002 (the 0x7030002 family is this phone's)
FENCE_PROBE: highest bank bit 16 (the NC_MODE registers were computed from it; 16 expected)
FENCE_PROBE: round 0 fence 1 not done on the first poll; resubmitting (each resubmit rewrites the WPTR)
FENCE_PROBE: round 0 fence 2 done, memory reads 0x45f000c0 (the nonce, as written)
FENCE_PROBE: round 1 fence 3 done, memory reads 0x45f000c1 (the nonce, as written)
FENCE_PROBE: rounds done 2/2, memory ok 2/2, fence sequence 2 then 3 (increasing), polls 1, timeouts 0
FENCE_PROBE: PASS the device writes the fence number back and runs the IB (the wave41 fence event works on this hardware)
```
（wave44 §0.11 的 WPTR 丢弃现象在真机复现一次且按预案分支自愈——预测命中本身是这条物证的另一层价值。）

**门 C（`w45-gates0842-gl-01.out`，08:45:23，GLBIN=/redwood/bin/gl_test）**：
```
gl_test: freedreno; FD725; OpenGL ES 3.2 Mesa 25.0.7
gl_test: RENDER backend=hw renderer=FD725
gl_test: RENDER_PASS backend=hw renderer=FD725
gl_test: 1080 x 2400 drawn in 19 ms, read back in 26 ms; error 0; red green blue alpha: a corner 26 26 51 255, the middle 68 69 118 255, near the red corner 235 12 8 255, near the green 12 235 8 255, near the blue 10 10 235 255; 673920 of 2592000 pixels inside the triangle (26%; 26% by geometry)
gl_test: READBACK_PASS samples 5/5 coverage 26% (26% by geometry)
gl_test: the picture is on the panel (0), for 8 seconds
gl_test: PRESENT_CALL_OK
GL_RC=0
```
（五采样点真值与 wave41 §5-3 的判定常量逐字一致：红角 (235,12,8)/绿角 (12,235,8)/蓝顶 (10,10,235)/中心 (68,69,118)/清屏角 (26,26,51)；覆盖率 673,920/2,592,000 恰 26.0%。**用户目击屏幕三角形**——人机双确认。fill 160 帧成本画像 + u2f_test 同会话一并落盘（`w45-gates0842-fill-01.out`/`-u2f-01.out`）。）

**门 D（`verdict45-gated.txt`，09:20:29，验收器 `/var/battery_probe` `325c24d8` 双采样）**：
```
S1  fuelgauge: the PMIC arbiter is version 0x70000000, 768 channels   ← 逐字命中 wave43 §7 期望
S2  fuelgauge: no channel of the arbiter is the PM8350B's charger block (slave 3, peripheral 0x10) ×4
    （0x10/0x12/0x13/0x15 四块全不在本机仲裁器表——记而不判，阴性档案）
S3  fuelgauge: the gauge does not answer, or answers nonsense: nothing is fed to the battery
    BATTERY_PROBE: kern.hakios.battery_soc = -1（未喂哨兵）/ present 0 / temp -273 哨兵；10/10 oids 可读，双采样同值
```
判读：**S1 PASS / S2 阴性档案 / S3 FAIL → 门 D = PARTIAL**。runner 初版 PASS 行只判了读链（两采样 battery_soc 可读），已按 wave43 §7 口径改判 PARTIAL 并在 verdict 文件头写明。修复输入（wave46）：①S2 阴性 = buttons.c 仲裁器表 walk 的 SMB5 通道假设在本机不成立；②S3 = bq27541（GPIO26/27 位带 I2C）无应答三查（复用/上拉/休眠态）。

### 8.4 探查轮副产品（disc0857，`w45-discovery-disc0857.txt`）

`/dev/ufs_logdump`+`/dev/rufs_logdump` 在（2,100/17,100 root operator）、`/dev/logdump` 不存在、`/dev/klog`（6,0）在（本轮未用，备用出口）、`sysctl`/`dmesg` 二进制不在载体、PATH = `/usr/bin:/bin:/usr/sbin:/sbin:/var/jb/usr/bin`、`/var/fence_probe` 跨世代持久在证（ls /var 可见）。

## 9. 交付边界（续命令轮）

- runner 三 run-id 的全部 stdout/stderr 留档 `wave45-scripts/w45-gates0842-*`、`w45-gates0903-*`、`w45-gates0907-*`；verdict 文件 `verdict45-gate{a,b,c,d}.txt`（gate D 的 verdict 行为改判后终版）。
- 本轮零刷写、零重启、boot_a 零触碰；全部拉取在 SSH 会话内完成；gates0842/gates0903 两个 runner 按卫生纪律结束前物证已核对在盘。
- `battery_probe`（325c24d8）与 `gates-discover-v45.py`（探查轮工具）入 wave45-scripts；`fence_probe` 二进制仍不入 git（.gitignore）。
