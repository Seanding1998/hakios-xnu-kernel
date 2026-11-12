# 阶段 36 交接 · 2026-11-11 · GPU 首亮下一轮的设备状态与任务单

> 2026-11-11 11:20 · 阶段 36 执行记录写于收尾时。接手者：本文是唯一的交接文档，先读完再操作设备。
> 详细阶段日志（判定/增量记账/施工过程）在 `docs/waves/wave36-gpu-firstlight.md`（§6/§7 判定段为交接前快照，**以本文为准**——本文写于其后的 v26 现场轮之后）。

---

## 1. 设备精确状态（写此段那一刻：2026-11-11 11:18:33）

```
usbipd list（原样）:
2-2    22d9:2765  一加 Ace 2, ADB Interface    Shared     <- 手机在安卓，Windows adb 可用
2-3    3277:00d1  FHD Camera                   Not shared
```

- **相位**：安卓（ColorOS），`sys.boot_completed=1`（11:07:08 达成）。
- **槽位**：**active slot = a**（我在 11:03 用 `fastboot set_active a` 切过去的，为的是进安卓做 logdump 取证——用户指正：active=b 只会循环 Darwin，永远到不了安卓）。
- **boot_b 内容 = v26（graft c55300e1，未激活）**。boot_a 零触碰（全程只切过槽标志，从未刷写）。
- **我最后一条设备命令**：`adb reboot bootloader` → 输出 `error: more than one device/emulator` + `< waiting for any device >`（adb 看到了多个设备条目——原因未查，接手者先 `adb devices` 看；大概率一条 stale emulator 或双条目，用 `adb -s <serial>` 消歧）。**切回 b 未执行**。
- 磁盘上的镜像与机上状态无关地放在：`device-layer/udon-hakios-grafted-v26.img`（sha256 `c55300e1e...`，完整 64 位值见 verify-v26.log 末行）。

## 2. 已定案（带证据路径）

### 2.1 v25 cmdline NUL bug（本轮最大定位根因，已修复未验于 v25——修复体就是 v26）
- 根因：payload 的 cmdline 条目是 **NUL 结尾的 C 字符串**；v24 条目 473 B = 472 字符 + 尾 NUL。make-payload-v25.sh 用 `v24bytes + b" gpu=1"` 拼接，把 ` gpu=1` 放在了 **NUL 之后**。loader 按 C 字符串读（xnuloader/loader.c:3053 `pi->cmdline = text`，:3618 逐字符拷贝遇 NUL 即停）→ `gpu=1` 从未进内核。
- 反向证据：`wave36-scripts/console-v25-gen2-100608.txt`（482,527 B，gen2 服务窗 oem log 首拉）内核 bootargs 实收 echo 全文长 582 字符，**含 `gpu=1` 零次**（预算 582/607 根本没用完，不是长度问题）；`grep -c adreno: = 0`。
- 教训：往 cmdline 追加参数必须 `split(NUL)[0] + new + NUL`；mkpayload 的字节断言只保证字节相等，保证不了语义。

### 2.2 v26 已刷写并真机验证（gpu=1 首次真正进内核）
- payload `6349203c` / graft **`c55300e1`** / verify-udon-hakios-v26.py **ALL 61 CHECKS PASSED**（`wave36-scripts/verify-v26.log` 末行含 graft 全 sha）/ 10:27:55 FLASH CONFIRMED（`wave36-scripts/progress.log` 有记录；门 = taro ✓ slot b ✓ graft sha ✓，OKAY×2）。
- cmdline 478 B = 476 字符 + 尾 NUL：`loader_return_after=600`（用户提速令）+ `gpu=1` 在 NUL 之前。
- 内核 = `a39c931c`（gen7 参数层 44 处替换，wave 26 以来首次内核字节变化；驱动字符串在二进制内已验）；ramdisk = `156b5be1`（a730 固件 8 件平铺进 root.apfs `/fw/`，字节级验证在像）。

### 2.3 v26 现场 = **步 1 挂起**（GPU 验收行未达成，六分支判定 = 分支"进入步进机器但首步挂起"）
- 主证据：`wave36-scripts/logdump-v25-wave36-v26gen1.bin`（512 MB 尺寸门 PASS，sha256 `cc0420d1...`）。
- adreno 行全集（只有这 4 行，另两条是其无时间戳重复）：
  ```
  [   49.296270]: adreno: steps up to 21, without those in mask 0x1c00; step 21 is the new one and waits 0 ms after each announcement
  [   49.296275]: adreno: step 1: read the GPU's clocks in the global clock controller (registers the touch screen driver uses too)
  ```
- 解读（三条硬事实 + 一条更正）：
  1. `gpu=1` 自启路径生效：boot-arg 解析 ✓、`start_by_itself()` 的**固件预检通过**（若无 fw 会打印 "THE GPU IS NOT STARTED: the small image has no fw/..."——没有这行，说明 a730 三件套在 root.apfs/fw/ 被找到）✓、步进机器进入 ✓。
  2. **步 1 内部挂起**：announce 后零行直到世代结束（每代同样挂，切槽才停）。挂点在 5 条 gcc 读（0x100000+{0x52000,0x71004,0x7100c,0x71018,0x71154}）或 cmd_db 映射读（0x80860000）之间。
  3. **零 panic**（无 panic/abort 行——是挂起不是炸）。
  4. **更正（写给下一位防止误判）**：`get()` 只在 `step == newest_step`（=21）时打印 "about to read"，步 1 的读**本来就静默**——"announce 后没行"≠"挂在第一条读"；精确定位必须用驱动自带的逐步协议：`adreno_only=1 adreno_fine=1`（在 payload cmdline 加这两个参数重刷，或临时 boot-arg 试验件）。下一步嫌疑：sc7280 的 gcc gpu 偏移在 kodiak（sm8475）gcc 里不同——对照 `~/hakios/refs/kernel_oneplus_sm8475/drivers/clk/qcom/gcc-sm8475.c`（我的 grep 没打中同名宏，宏名不同，需人读）。
- SSH 回归（v25 gen2 世代）：HIT（`wave26-scripts/verdict26-w36c.txt`，09:41:05 第 1 发 1.9s，内核横幅时间戳 = v25 构建时刻 08:57:07）。**v26 世代未测**（每次 SSH 敲击会延长 loader 窗口——wave21 记账 "every loader command extends the window"，v26 的 12 次敲击把会话拖过了 600s 帽，此机制下一位要记住）。

### 2.4 固件实拉（wave35 脚本首跑，已定案）
- `wave35-scripts/pull-firmware-root.sh` 真拉成功（3 处现场修复在脚本里：su 引号嵌套→平铺 / MSYS 路径改写→MSYS_NO_PATHCONV / 本地落点→相对路径）。
- fw-gpu 8 件（ColorOS 真名 = SM8475 双源清单 + 多出 b00/elf/mbn）：sha256 全表在 `wave36-scripts/progress.log` phase 2 与 `docs/waves/wave36-gpu-firstlight.md` §1。
- zap 语义一手实证：`a730_zap.mdt` ELF seg1(b01)=PT_LOAD rwx 0x8bc=2236 B 代码段；b00/b02=PT_NULL 元数据。驱动已改读 b01。
- WiFi：`/vendor/firmware/wlan/qca_cld/*` 手机上是空目录；MAC 候选 = `/vendor/firmware_mnt/wlan_mac.bin`。audio 26 件已拉。**WiFi 固件真身未解决（v0.6 事项）**。

### 2.5 v25 控制台复盘结论
- gen2 console（482 KB）抓到的是 v25 内核双 boot（gpu=1 缺失 → 步进机器从未进入 → SSH/init/launchd 全正常）——这张 console 本身没有 GPU 行是**符合预期的**（gpu=1 没进内核），不是取证失败。
- 10:04-10:06 的取证窗被上下文重载吃掉（已入复盘：**有定时取证的代理禁硬杀**）。

## 3. 未定案 / 待办（命令级）

### 3.1 v26 GPU 验收行（主任务，接手者第一件事）
当前安卓态下已有一份 logdump（§2.3 的 bin）——它只到步 1 挂起。要继续推进：
1. **定位步 1 挂点**：改 payload cmdline 加 `adreno_only=1 adreno_fine=1`（两者与 gpu=1 并存会走 adreno_only 分支——读驱动：`adreno_only=K` 只跑步 K 且强制 newest_step=K → get() 会逐访问打印）。重打包（参照 `wave36-scripts/make-payload-v26.sh`，改 cmdline 一行）→ 三门 → flash → 等挂起 → logdump dd 看挂在哪个寄存器。
2. **挂点确认后的修复方向**（按概率序）：gcc gpu 时钟偏移 kodiak 化（对照 vendor gcc-sm8475.c，注意它的宏名不同）；gcc 基址复核（我们的 DTB clock-controller@100000）；cmd_db 读挂起（0x80860000 在 Darwin 早期是否上电——soc.args 说 0x80860000 ✓，但读挂可能）。
3. 验收行标准（任务书原文）：驱动 probe 行 + 固件加载行 + GMU/ring 初始化行 + 零 panic。步序预告（全过后的行）：步 12 zap 签名 → 步 14 "THE GMU'S FIRMWARE IS LOADED" → 步 15 "THE GMU'S FIRMWARE RUNS" → 步 16 "THE GMU'S MESSAGE QUEUES ARE UP" → 步 17 "THE 3D CORE HAS POWER AND ANSWERS" → 步 21 后 "THE GPU STAYS ON"。
4. logdump dd 命令（安卓下，root）：`bash wave36-scripts/logdump-pull-v36.sh <RUNID>`（配方 = wave27 逐字：wsl adb exec-out su dd，512 MB 尺寸门）。
5. **槽位纪律**：现在 active=a。进 Darwin 环 = `adb reboot bootloader` → `fastboot set_active b` → `fastboot reboot`（adb 报 "more than one device" 时用 `adb devices` 消歧）。进安卓 = `fastboot set_active a` → reboot。**boot_a 只切槽绝不刷写**。

### 3.2 a730 固件实拉 = **已完成**（见 §2.4），产物在 `wave35-scripts/fw-stage/fw-gpu/`（+已复制到 WSL 树 `~/hakios/kernel/fw-gpu/`）。

### 3.3 v26 服务窗 console 拉取 = **拿到过一次**（10:06 的 gen2 v25 console，见 §2.5）；v26 世代的 oem log 首拉**未拿到**——10:47 的尝试打在 ABL 相位上 desync（`DeviceError: desync after a partial reply to 'oem log'`；oem log 只对 xnuloader 协议的 d00d 节点有效，ABL d00d 是 fastboot 协议）。正确时机 = loader 相位（xnuloader 在线）且**会话已返回**（SSH 敲击会延长窗，取证时别敲）。不确定的就不猜：v26 世代是否还有未读 console 残留在 loader RAM——未知。

### 3.4 已知未修（沿用账）
- probe24 的 TypeError 崩溃（登记在案，未修）。
- wave31 半启动状态两轮（0xB ep3 环满 → 0xC ep2 注销）+ 本阶段新增第三轮记录：loader gadget 重枚举破损（2-2 = `0000:0002 描述符请求失败`），usbipd unbind/bind 需管理员，靠世代切换自愈。
- wave34 §5 的 USB 对自愈设计（只读参考，未实现）。

## 4. 文件清单（全部在仓 `hakios-phk110/` 下）

**wave36-scripts/**（本阶段交付物 + 产物）：
- `apply-adreno-v25.py` — 44 处精确锚补丁应用器（每处断言恰一次；残留名守卫）。驱动已应用，勿重跑（重跑会 MISS）。
- `patches/wave36-adreno-a730-parameter-layer.diff` — 全量 unified diff 留档。
- `make-payload-v25.sh` / `make-payload-v26.sh` — payload 组装（v26 = NUL 修复版配方，含根因注释）。
- `make-graft-v25.sh` / `make-graft-v26.sh` — graft 组装（FD 8924cb67 + shim 108ce972 钉）。
- `make-verify-v25.py` — verify 生成器（v25；注意其中有一处真 NUL 字节的 bug 已由 v26 生成路径绕开——勿再跑）。
- `verify-udon-hakios-v25.py` / `verify-udon-hakios-v26.py` — 61 检查验像器（v26 可用；用法行在文件头）。
- `flash-bootb-v36.sh` / `flash-bootb-v36b.sh` — 三门刷写脚本（v25/v26 版；改 EXPECT_SHA 与 IMG 路径即可复用为 v27）。
- `logdump-pull-v36.sh` — 安卓态 logdump dd（512 MB 尺寸门）。
- `cmdline-v26.bin` — v26 的 cmdline 条目原件（478 B）。
- `console-v25-gen2-100608.txt` — v25 gen2 服务窗 oem log console（482,527 B，NUL bug 反证）。
- `logdump-v25-wave36-v26gen1.bin` — 512 MB logdump（**v26 步 1 挂起的现场**，sha256 cc0420d1…）。
- `verify-v26.log` — v26 verify 全 61 PASS 记录（末行 = graft 完整 sha）。
- `progress.log` — 本阶段逐阶段流水账（含 3 条 NEED USER 与复盘）。
- `fw-stage/` — 固件落库（fw-gpu 8 件 / fw-wifi 空目录 / fw-audio 26 件；gitignore 内，勿提交）。

**device-layer/**：
- `udon-hakios-payload-v25.bin`（e1ef6e94）/ `udon-hakios-payload-v26.bin`（6349203c）
- `udon-hakios-grafted-v25.img`（802f1aeb）+ `.report.json` / `udon-hakios-grafted-v26.img`（c55300e1）+ `.report.json`

**WSL 树（~/hakios/kernel）已改（均属本阶段工作，随仓 git 不管辖，注意树无版本控制）**：
- `drivers/gpu/hakios.adreno.c`（gen7 参数层 + 备份 `.v24-orig`）→ 已同步进 xnu-src（make kernel 时自动）
- `.config` + `devices/phk110/configs/phk110.config`：`CONFIG_HAKIOS_ADRENO=y`
- `fw-gpu/`（8 件 a730 固件）
- `userland/root.apfs`（156b5be1）+ `userland/flashboot.apfs`（重编产物，未入 payload——resident 条目仍 carry v23 时代字节）

## 5. 红线与协议（不变 + 本阶段新增）
1. boot_a 只切槽绝不刷写；`set_active` 不是刷写（只改槽标志，可逆）。
2. boot_b 刷写循环 = 一揽子授权内；**每次刷写前三门**：graft sha 钉 → `getvar product=taro` → `current-slot` 核对，OKAY 断言。
3. NEED USER 协议：物理操作（重启/按键/重插线）写 progress.log `NEED USER: <动作>` + 叙述里明说，用户按键最快；监听切片 ≤5 分钟。
4. 600s 会话帽（v26 cmdline）+ loader 返回窗；**SSH 敲击/loader 命令会延长窗口**（wave21 记账）——取证窗前保持 loader 静默。
5. oem log 服务窗纪律：stage-once；只在 xnuloader 相位的 d00d 节点上有效（ABL d00d = fastboot 协议，打了就 desync）；会话中误拉废窗。
6. usbipd：禁 wsl --shutdown；抢占只做 detach；attach 后若 fastboot 悬死 = 陈旧 attach，detach→重 attach 即活；持久绑定 `ebd3f1a8`/`269e72e4`/`f474f60e`/`b67ab332` 待管理员清理（wave34 §5-4）。
7. fastboot 必须在 WSL 内 root 跑（`sudo -n fastboot`），镜像路径用 /mnt/c；USB 重枚举后要重新 attach。
8. adb "more than one device/emulator" = 用 `adb devices` 消歧后 `adb -s <serial>`（本阶段遗留坑，未查根因）。

## 6. 时间线快照（接手者对表用）
- 08:1x 波起；08:28 固件真拉成功；08:54 补丁/config/fw 落位；08:56 内核 a39c931c；08:57 root.apfs 156b5be1；09:16 payload/graft v25 + verify 61/61；09:17 v25 FLASH CONFIRMED；09:17-10:13 半启动状态 + 用户硬杀；09:31 用户 fastboot 现场令；09:33 v25 gen2 真机验证；09:41 SSH HIT；10:06 gen2 console 拉到（→ NUL bug 定位根因）；10:19 payload v26；10:20 graft v26 c55300e1；10:27 v26 FLASH CONFIRMED；10:38+ v26 gen1 会话超时（SSH 敲击延长窗）；11:02 用户槽位指令 → set_active a；11:07 安卓上线；11:09 logdump dd 完成 = 步 1 挂起现场；11:15 恢复 b 的命令失败（adb 多设备）；11:18 交接态定格。

---

## 7. 阶段 37 完成附录（2026-11-11 追加，原文不覆盖——下一位以本文 + wave37-gpu-firstlight.md 双读）

阶段 37 完成本文档 §3.1 全部待办并超额：**v0.5 GPU 首亮达成（步 21 the page reads 0x600dc0de + THE GPU STAYS ON）**。本文 §2.3 的"更正"被 v27 探针一字验证（挂点 = gcc PLL_VOTE @0x152000；cape 真值 0x62000），§3.1-2 的三个修复方向全部落空/命中情况：gcc 偏移 = 命中（gcc-waipio.c，cape fixup——注意本文写的 gcc-sm8475.c 路径不存在，该树中 waipio 即 cape 基座）；gcc 基址 = 本就正确（0x100000，但映射尺寸 0x80000 太小，DTB 真值 0x1f4200）；cmd_db = 无罪（v28 实读全过）。步 2/3/20 的后续挂点与修复见 `wave37-gpu-firstlight.md` §0-2 与 `wave37-scripts/apply-*-v2x.py` 六份补丁器。
**现态（2026-11-11 19:3x）**：安卓 slot a 静置；boot_b = **v33**（graft `6d5efeb5…`，payload cb447ade，内核 55a8d40f，GPU-capable 全修复版）；`wave36-scripts/flash-bootb-v36*.sh`、`logdump-pull-v36.sh` 的 wave37 直系后裔 = `wave37-scripts/flash-bootb-v3x.sh`、`logdump-pull-v37.sh`、`catch-d00d-switch-a-v37.sh`（复用改 EXPECT_SHA/IMG/RUNID 即可）。守望器 + 需人工配合窗口的预约时刻 = 会话末端半启动残留→EDL 形态下的标准取证流程（四轮零失误）。
