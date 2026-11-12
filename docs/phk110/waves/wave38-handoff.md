# 阶段 38 交接 · 2026-11-11 · USB 修复四代后的设备状态与 v34 判定任务单

> 2026-11-11 22:5x · 阶段 38 执行记录写于交接线。接手代理：本文是唯一交接文档，先读完再碰任何东西。
> 阶段日志主线 = `docs/waves/wave38-usb-selfheal.md`（离线相四段已提交）；外审施工单 = `docs/review/gpt-review-report-3-2026-11-11-usb.md`（P0×4 + P1×6，逐条带行号）。

---

## 1. 设备精确状态（停手那一刻 2026-11-11 22:5x）

- **手机在安卓**：`usbipd list` → `2-2 = 22d9:2769 一加 Ace 2, Shared`（注意 PID 是 **2769** 非惯常的 2765）。boot_a 零触碰（全程只 set_active，从未刷写）。
- **boot_b = v34-GL**：graft **`1b952ea6dccdf78cd7846fe5d670adf3e8edbd8aa1275571708bd36dde6dd92d`**（= v33 内核 `55a8d40f` + wave38 受审 loader `3f595c52` + wave39 GL ramdisk `c2780842` + gpu=1 cmdline）。三门刷写 CONFIRMED 于 20:31:48（watcher 自动接用户 fastboot）。
- **21:20 前后设备自行回落安卓**（世代循环中断——原因未查，gen2 后的世代没有 SSH 会话证据；GL runner 的日志显示 21:22 后无任何 d00d）。我停手前没有对设备发过任何直接命令（最后设备操作 = 20:31 刷写重启；20:14 有一次 `usbipd detach 2-2` 释放陈旧 attach）。
- **早前形态记录**：19:53-20:07 gen1 期间总线 = `0000:0002 设备描述符请求失败`（wave31/36 半启动残留形态），20:07:25 世代切换自愈为 `18d1:d00d xnuloader` 干净枚举 → SSH HIT。v34-GL 后续世代未再观察到该形态（未取证）。

## 2. 已定案（带证据路径）

### 2.1 修复链四代（代码全部完成；测试状态逐代标注）

| 代 | 内容 | loader sha | patch 文件（wave38-scripts/） | 测试 | 状态 |
|---|---|---|---|---|---|
| 受审 | 七 hunk（wave34 §5 设计的初版落地） | `3f595c52`（已刷入真机 = v34 两刷） | patch-loader-v38.py | 外审否决（报告三） | 历史 |
| GEN-1 | P0-2：IN 直接提交失败纳入独立故障计数+退避 | `940fa345` | patch-loader-v38b-p02.py | **14/14** | ✅ 完成且绿 |
| GEN-2 | P0-4：写回调 ABI 三参→二参 + 探针修正 + HOB 短块/PHIT 修正；P1-5：跨调用行组装 + 三型墙共享 2s 显示预算 + 首因保留 + 返回消费字节数 | `c388576c` | patch-loader-v38c-p04.py + v38c2-fix.py + v38c3-fmt.py（harness 抓出三缺陷后的修复轮） | **22/22**（mirror-harness）+ P0-2 回归 14/14 | ✅ 完成且绿 |
| GEN-3 | P0-1/P1-2：IN/OUT 请求生命周期状态机（IDLE→SUBMITTED→CANCELLING→IDLE；完成按端点排他归属；有界退役收束 usb_retire_drain；Connected 不裸清在等请求；OUT 站立恢复；usb_poll_command 先服务后 re-arm；短应答不记成功） | `a4e90351` | patch-loader-v38e-p01.py + v38e2-p12.py + v38e3-decl.py + v38e4-disc.py + v38e5-fix.py | **35 PASS / 0 FAIL**（usb-suite：T1-T4 + TC1-TC7，含审阅四反例等效） | ✅ 完成且绿 |
| GEN-4 | P0-3/P1-1：重建检测改"同代际时间戳最新进展/失败"判据（纯 0xC 半启动残留可达：近墙 120s + 无进展 120s + 150s bring-up 宽限 + 30s 枚举宽限 + run_active 硬闸 + 上限 2/窗）；重建事务化（abort 结果检查 + 双端 drain + kick 后 5s pumped settle + 窗限先行 + ready 检查 + 每窗计数复位 + 诚实措辞） | **`95f1f555`**（= v35 指定 loader） | patch-loader-v38f-p03.py + v38f2-loop.py + **v38g-optnone.py** + **v38h-volatile.py**（两个 hardening，见 §4 警告） | USB 套件 **49 PASS / 0 FAIL**（TD1-TD7 + 全前代回归）——**注意：这是 volatile/optnone hardening 之前的 49/0**，hardening 后未重跑，见 §4 | ⚠ 代码完；**-O1 二进制含函数消除问题未解决（§4，v35 打包的阻断项）** |

**接手者最需要的一行**：GEN-3/GEN-4 源码语义已被离线套件验证（gcc -O0 抽取真实函数执行），但 **ship-grade -O1 二进制里 `usb_pair_rebuild` 被 LLVM 22.1.8 整体消除**（见 §4），v35 打包被此阻断。

### 2.2 外审报告三的采纳与禁令

- 报告 = `docs/review/gpt-review-report-3-2026-11-11-usb.md`。九反例隔离测试台 = `wave38-scripts/usb-harness.py`（从 WSL loader.c 抽取真实函数 + 假时钟 + 替身 USB/BS；fake_handle_event 每泵推 0.5s 假钟；ECODE() 镜像 64 位符号扩展的 vendor 状态码）+ `wave38-scripts/mirror-harness.py`（mirror 段同法）。用法：`python3 usb-harness.py /home/cyrux/hakios/kernel/xnuloader/loader.c /tmp/x/test.c && gcc -O0 -o /tmp/x/test /tmp/x/test.c && /tmp/x/test`。
- **禁令方案（一个都不许做）**：强写 state=1 / EFI_ERROR 改成功 / 任意 Transfer 失败就重配整对 / 只多装一次 bulk 不处理 SET_CONFIG；FD 完整状态机字节手术已正式撤销（判不可交付）；定点消音仅限等长替换诊断调用且不满足 A1。
- FD 视觉限频的替代路线（报告 Q2 首选）已实现于 loader 写回调（GEN-2 的 P1-5），FD 字节未动。

### 2.3 v34-GL 野外观测（语义已按外审重分类）

- 两次 SSH HIT：`wave27-scripts/verdict27-w38-ssh1.txt`（20:11，graft 03d42401 时代）+ `verdict27-w38-ssh2.txt`（20:36，graft 1b952ea6 = v34-GL）：hit + 3 连接 + 262144/262144 B 长度校验传输 + 退出后 getvar OKAYxnuloader。**语义 = 最小门野外观测，非修订版 A3**（双向内容 SHA 校验未做）。
- **P1-6 元数据修正已做**：两份 verdict 文件尾部追加 CORRECTION 块（真实包哈希 + 野外观测语义 + 长度≠内容声明）。timed-ssh-v27.py 的硬编码 boot 行（:292）未改源（下轮修）。
- 20:07:25 的 0000:0002→xnuloader 世代自愈 = 野外观测，不归属 usb_pair_rebuild（当时机上 loader 尚无该函数的可达形态）。
- gl_test 首帧尝试：**未完成**（两次 runner 会话错过 kernel session：w38gl1 的 25s 快重试造成 netmode on/off 刷新 240s 闲置窗的 livelock；w38gl2 改 260s 静默后手机已回安卓）。gltest-run-v38.py 已修好待用（wave39-mesa-userland.md §4.5 会话序：klog tail → gl_test 8 → fill → u2f_test）。

### 2.4 v34 三门安全刹车事件（如实登记）

20:30:37 用户物理 fastboot 出现，watcher 开火 flash-bootb-v34.sh，**门 1（graft sha 钉）正确拒绝**——EXPECT_SHA 还是换 ramdisk 前的 `03d42401`（GL 载体 graft 是 `1b952ea6`）。boot_b 未动。修正 EXPECT_SHA 后 20:31:48 一次通过。教训入档：**同名换包必须同步改刷写脚本锚**。

### 2.5 v35 版本号已定（当时的工作安排令）

v35 = loader `95f1f555`（GEN-4 终态源码构建；注意 LLVM 时间戳非确定性——重跑 build.sh 即漂移，见 §4 警告）+ v33 内核 `55a8d40f` + GL ramdisk `c2780842` + gpu=1 cmdline。**打包被 §4 的 -O1 消除问题阻断**：现 loader.efi（90624 B，22:46 构建，sha `9d2799a7…` 时间戳敏感）中 usb_pair_rebuild 被消除。

## 3. 未定案/待办（命令级）

### 3.1 【阻断项】GEN-4 恢复函数的 -O1 消除（接手第一件事）

现象链（全部有据）：
1. loader.c（WSL `~/hakios/kernel/xnuloader/loader.c`，md5 `091063cb`，256321 B）源级正确：usb_pair_rebuild 定义 5821-5822、调用 5914、volatile 指针 `usb_pair_rebuild_fn` 引用 ×2。
2. **-O0 编译含全部字符串**（clang -O0 → obj grep "the pair reads dead" = 1）。
3. **-O1 编译 obj 中：usb_pair_rebuild 折叠为 3 指令 stub（`mrs CNTFRQ; mrs CNTVCT; ret`）——IPSCCP 把全块判 unreachable**；非 static 外链变体同样折叠；`used`/`optnone`/`noinline` 三属性叠加仍折叠；volatile 间接调用仍被剪。
4. gen-3 源（loader.c.v38-p01gen3）在 -O1 下**保留**旧重建函数与字符串（o1g3.obj 验证）→ 消除由 GEN-4 的 delta 触发。
5. 已试无效：optnone+noinline（11 函数）、volatile 函数指针间接调用、/OPT:NOREF（lld-link 非引用 GC 问题）。

下一步 bisect（从便宜到贵）：
- a. `clang -O1 -mllvm -inline-threshold=0` 或 `-fno-inline-functions` 试一版：确认是否 inlining 链（usb_command_loop 内联进 efi_main 后 IPSCCP 折叠）触发。
- b. 二分 GEN-4 hunks：仅 stamps（f-p03 hunk 1-4）不上函数重写；仅函数重写不上 f2-loop；仅 f2-loop——定位触发 hunk。
- c. 若确证 IPSCCP 对该函数不可救：**整 loader 降 -O0 打包**（loader 会变大至 ~200-300 KB，64MB payload 窗口毫无压力；watch-loop 的 `for (volatile int i<300/20000)` 忙等 pause 会变长——需对照 wave21 的节拍语义评估，20ms tick 与 5s settle 是墙钟不受影响，但 20000 次迭代空转会从 ~3ms 变 ~15-30ms，影响 watch 循环节奏与 net_poll 轮询密度——须评估）。
- d. 或 `-O1 -mllvm -ipsccp-*` 系列开关排查（LLVM 22.1.8，Fedora /usr/sbin/clang）。

确认修复后：重跑 `usb-harness.py`（gcc -O0 源级语义 49/0 应不变）→ 重编 loader（记新 sha；**build.sh 非确定性，verify 绿后禁重跑**）→ `make-payload-wave38fix.sh`（v35 语义：v33 内核/GL ramdisk/cmdline + 新 loader；**注意该脚本现从 loader.efi 直接取件 + 断言锚 95f1f555 需换成新 sha**；其输出名已是 udon-hakios-payload-wave38fix.bin，但上一轮运行断言失败留下了一个未验证的半成品 bin——重跑会覆盖）→ graft（make-graft-v34.sh 改 payload 名 → graft 实值 sha）→ verify（copy verify-udon-hakios-v34.py，loader 锚换新 sha + gen-4 新字符串钉："the pair reads dead in this generation"/"bounded recovery %d of 2"/"the recovery's bring-up is back"）→ 刷写（flash-bootb-v34.sh 改 EXPECT_SHA）→ 判定。

### 3.2 判定会话全流程（v35 真机验证后）

1. 三门刷写（taro/slot/sha+OKAY 断言；用户按键时按 需人工配合窗口的预约协议——手机现态安卓，`adb reboot bootloader` 通道也可）。
2. 门 1 SSH 完整语义：timed-ssh-v27.py（verdict27 全语义：3 连接不同 nonce + 传输 + 干净退出 + 退出后管理活性）+ **双向内容 SHA 校验**（长度校验不够：host→device 发随机 blob + device `sha256sum` 回读比对；device→host 反向同法——可写在 gltest-run-v38.py 的 ssh_attempt 远程命令里）。
3. 门 2 /var 回归：hunt-var-v28.py --marker-mode write（一世代）→ 世代切换 → --marker-mode read（下一世代）→ verdict34 判定。
4. A2 修订表场景（能做几个做几个，做不到的如实标"待故障注入"）：读者消失/返回（DATA、正文、OKAY 三阶段分别停）需 host 侧故障注入工具——**未建**，如实标注；纯 0xC 半启动残留可达性 = 源级已证（TD1），真机自然发生不可强造（外审禁止强写状态字）。
5. GL 首帧（wave39 §4.5）：gltest-run-v38.py（已修好）→ 六分支判定归 wave39（wave39-mesa-userland.md §4.4）；面板三角 = NEED USER 拍照。
6. 全程纪律：取证窗前 loader 静默；**netmode on/off 等探测命令会刷新 240s 闲置窗**（本次 livelock 实测，见 progress.log phase 12）；600s 帽世代 ~15.5 分钟一个。

### 3.3 GEN-3/4 未竟事项清单

- [ ] hardening（v38g/v38h）后未重跑 USB 套件（源语义不受影响——属性+间接调用不改变 gcc -O0 行为——但严谨起见重跑一遍，49/0 应复现）。
- [ ] TD 测试的 volatile 间接形态未测（TD 直接调 usb_pair_rebuild()；可加一测经 usb_pair_rebuild_fn() 调用验证等价）。
- [ ] 审阅报告三 P1-2 的 `usb_rx` 多调用点 buffer 契约：usb_rx 的 OUT 站立恢复已做，但 download 循环里的连续 usb_rx 依赖队列消费——已被 TD5 覆盖主形态。
- [ ] P1-4（回复失败逐层传播/协议失步）**未做**（外审列为 P1，分代表外——接手者排期）。
- [ ] P1-3（sampler 偏移错：正确位置 inst+0x1f0+phys*0x20+0x18）**未做**（观测性，不阻塞判定）。
- [ ] probe24 的 TypeError 崩溃仍未修（wave31 起挂账；崩溃发生在落盘后，不损取证）。
- [ ] FD 设计段（wave38-usb-selfheal.md §5）与 FD 撤销裁决一致，无需动作。

## 4. 【警告】GEN-4 hardening 的 -O1 消除问题（时间线 + 已试清单）

时间线：GEN-4 源码补丁（f-p03/f2-loop）→ 构建 95f1f555 零警告 → USB 套件 49/0 → **v35 打包时发现载荷断言失败**（"the pair reads dead in this generation" 不在 loader.efi）→ 排查链：二进制里 gen-4 恢复函数整体消失 → -O0 编译存在（源级正确）→ -O1 折叠为 `mrs;mrs;ret` → 非 static 外链仍折叠 → used/optnone/noinline 仍折叠 → volatile 间接调用仍折叠 → /OPT:NOREF 仍折叠 → **未解决，交接**。
已试清单（全部无效）：`__attribute__((optnone, noinline))`（11 函数含 rebuild）、`__attribute__((used))` 全 static-void、volatile 函数指针间接调用（obj 层重定位存在但 -O1 obj 的 efi_main 体里无引用）、/OPT:NOREF 链接选项、非 static 外链。
关键校准数据：gen-3 源在 -O1 保留旧重建（o1g3.obj 验证）→ 触发因子在 GEN-4 delta 内（新检测器的时间戳全局/新事务体/volatile 指针/f2-loop 的循环重排——未定位）。合法编译器不应折叠含不透明外部调用（abort_xfer 经函数指针）与运行时全局分支的函数——疑似 LLVM 22.1.8 的 IPSCCP/inlining 交互 bug 或某处 UB。
备选路线（接手者评估）：整 loader -O0 打包（评估 watch-loop 忙等节奏）；或 `#pragma clang optimize off` 包住 USB 段；或 `-O1 -mllvm` 系列开关排查。

## 5. 文件清单（全部在仓 hakios-phk110/ 下）

**wave38-scripts/**（本阶段全部）：
- 补丁家族（全部唯一性断言，顺序应用即当前 WSL loader.c 状态）：`patch-loader-v38.py`（受审七 hunk，已历史化）→ `patch-loader-v38b-p02.py`（GEN-1）→ `patch-loader-v38c-p04.py` + `v38c2-fix.py` + `v38c3-fmt.py`（GEN-2）→ `patch-loader-v38e-p01.py` + `v38e2-p12.py` + `v38e3-decl.py` + `v38e4-disc.py` + `v38e5-fix.py`（GEN-3）→ `patch-loader-v38f-p03.py` + `v38f2-loop.py`（GEN-4）→ `v38g-optnone.py` + `v38h-volatile.py`（hardening）。**勿对当前树重跑任何已应用补丁（断言会 MISS，这正是防重复的守卫）**。
- 测试台：`usb-harness.py`（USB 段抽取 + 49 用例源）、`mirror-harness.py`（mirror 段 + 22 用例源）、`usb-suite-results.txt`（49/0 的运行记录，volatile/optnone hardening 前一版源）。
- 构建/打包：`make-payload-v38.sh`/`make-graft-v38.sh`/`verify-udon-hakios-wave38.py`（wave38 前缀包，历史）；`make-payload-v34.sh`/`make-graft-v34.sh`/`verify-udon-hakios-v34.py` + `verify-v34.log`（v34 两版：首版 65/65 = 03d42401，GL 版 66/66 = 1b952ea6，verify-v34.log 现为 GL 版结果）；`make-payload-wave38fix.sh`（v35 打包用，loader 锚 95f1f555 需按 §3.1 更新；输出 udon-hakios-payload-wave38fix.bin 现存**未验证半成品**，重跑覆盖）；`adapt-verify-v34.py`（一次性适配器，已用毕）。
- 刷写：`flash-bootb-v34.sh`（三门；**EXPECT_SHA 现指 1b952ea6 = v34-GL，v35 刷前改成新 graft 实值**）；`watch-fastboot-flash-v34.sh`（fastboot 监视器，已用毕）。
- 取证/执行：`gltest-run-v38.py`（GL 会话 runner，260s 静默版）、`gltest-run-v38-w38gl{1,2}.log` + `gltest-w38gl{1,2}-*.{out,err}`（两次未完成尝试的证据）、`oemlog-v34-gen2-live.log`（空，loader_talk log 模式协议不匹配——用 probe24）、`probe-o1.sh`/`probe-cal.sh`/`probe-call.sh`/`probe-efi.sh`/`probe-full.sh`/`probe-identity.sh`/`probe-loader.sh`/`probe-loop.sh`（-O1 消除排查的探针家族，接手者复现用）。
- 结果：`usb-suite-results.txt`（49/0）、`verify-wave38.log`（wave38 前缀包 65/65）、`verify-v34.log`（v34-GL 66/66）、`progress.log`（全波流水 + NEED USER 两条）。

**device-layer/**：`udon-hakios-payload-v34.bin`（b35df4bd，第一次刷写包）+ `udon-hakios-grafted-v34.img`（03d42401，已刷入真机）+ `...wave38.img`（742bce63，wave38 前缀历史）+ `udon-hakios-payload-v33.bin` 等沿用品；`udon-hakios-grafted-v34.img.report.json` + `udon-hakios-payload-wave38.bin.report.json` + `udon-hakios-grafted-wave38.img.report.json`（哈希记账）。gitignore 挡 *.img/*.bin；report.json 随 git 走。

**wave27-scripts/**：`verdict27-w38-ssh1.txt` + `verdict27-w38-ssh2.txt`（已追加 P1-6 元数据修正块）；`hunt-phaseB-v27-w38-ssh{1,2}.log`（两次猎守全日志）。

**WSL 树（~/hakios/kernel/xnuloader/，无版本控制）**：`loader.c`（= gen-4 + hardening 终态，md5 091063cb）、备份链 `loader.c.v37-orig`（3ac12740，七 hunk 前）/ `loader.c.v38-review`（gen-1 前）/ `loader.c.v38-p02`（gen-2 前）/ `loader.c.v38-p04gen2`（gen-3 前）/ `loader.c.v38-p01gen3`（gen-4 前）；`loader.efi`（90624 B，22:46 构建，sha 9d2799a7 时间戳敏感——**含被消除的恢复函数，不可用于 v35**）；`loader-3f595c52-pinned.efi`（受审版钉件）；GL 载体 = `~/hakios/kernel/userland/root.apfs`（c2780842，8,089,600 B）。

## 6. 红线与协议（不变 + 本阶段新增）

1. boot_a 只切槽绝不刷写；boot_b 刷写循环 = 一揽子授权；每次刷写前三门（graft sha 钉 → getvar product=taro → current-slot，OKAY×2 断言，exit-code 检查绝不管道吞错）。
2. **同名换包必须同步改刷写脚本 EXPECT_SHA**（20:30 安全刹车事件的教训——门拦下了陈旧锚，boot_b 未动，但用户按键窗口浪费了 50 秒）。
3. 需人工配合窗口的预约协议：物理操作写 progress.log + 叙述明说；用户按键（电源+音量下进 fastboot）时挂 watcher 自动接。
4. 600s 帽 + 世代 ~15.5 分钟；**loader 静默取证窗：netmode on/off 等命令会刷新 240s 闲置窗**——失败探测的快重试会 livelock 装载器在窗相位（本阶段实测），重试节奏 ≥260s。
5. 禁 wsl --shutdown（多代理共享 WSL）；usbipd 抢占只 detach；WSL /tmp 跨调用不存（测试目录每次调用内闭环）。
6. 外审禁令方案清单（§2.2）一个都不许做；FD 字节保持 8924cb67 锚不动。
7. Windows 侧无 python3（harness 都在 WSL 跑）；`wsl.exe bash -lc` 的嵌套引号坑：含单引号/美元符的命令写成脚本文件再 `wsl.exe bash -lc "bash /mnt/c/....sh"`。
8. Windows Git-Bash 会把 `/tmp/...` 参数转换成 `C:/...`——路径必须包在 bash -lc 字符串里。

## 7. 时间线快照（19:51 至今）

- 19:51:34-19:52:03 v34（03d42401，非 GL）三门刷写 CONFIRMED（一次通过）
- 19:52:51 SSH 猎手 w38-ssh1 armed；19:53-20:03 gen1 会话（0000:0002 死 devnode 形态）
- 20:07:25 世代自愈：0000:0002 → xnuloader 干净枚举；20:09:40 k001 HIT
- 20:09-20:11 acc2/acc3 + 262144B 传输 → 20:11:53 verdict27-w38-ssh1 落盘（门 1 PASS，后重分类为野外观测）
- 20:14 usbipd detach 释放陈旧 attach；20:14-20:18 oem log 拉取尝试（loader_talk 协议不符 → 改 probe24，又遇 300s 超时被移后台后停）
- 20:23 v34-GL 重打包（payload b35df4bd→8109b4a4；graft 03d42401→1b952ea6；verify 66/66）
- 20:30:37 用户 fastboot 出现 → watcher 开火 → **门 1 正确拒绝陈旧 EXPECT_SHA**（安全刹车）→ 修锚 → 20:31:48 v34-GL 刷写 CONFIRMED
- 20:33-20:36 门 1 重跑（w38-ssh2）→ HIT + acc + 262144B/50.3s → verdict27-w38-ssh2 PASS
- 20:37-21:50 gltest runner 两轮（w38gl1 25s livelock 教训；w38gl2 260s 静默版——期间手机回安卓，全程 rc=255 空手）
- 21:0x-22:3x 外审报告三到达：读全文 → P1-6 verdict 元数据修正 → GEN-1..GEN-4 分代补丁 + 隔离套件建设 + 全绿（49/0 + 22/22）
- 22:4x v35 打包尝试 → 发现 gen-4 恢复函数被 -O1 消除 → 排查（-O0 存在/-O1 消除、gen-3 对照保留、optnone/used/volatile/OPT:NOREF 全无效）→ **当时的工作安排交接令到达，停手**
- 22:5x 本交接文档落盘 + 提交
