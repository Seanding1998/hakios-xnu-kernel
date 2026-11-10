# 阶段 21-2 · 2026-11-08 · USB 稳定性加固与一次构建回归的定位

> 2026-11-08 · 执行记录全循环：v16b 施工（§2）→ 构建/自检（§3）→ 守护固化（§4）→ 自刷 + E2E（§5）→ 判定（§6）→ **F10 冻屏解剖与根因（§7，照片证据 + 指令级定位）→ 预算内修正 v16b'（§7.5，54/54 全绿，待刷）**
> **判定：本轮 N1→N2→N3 未执行——v16b 第一次刷写 boot 冻结在 EDK2 异常断言屏（F10）。冻屏照片（§7）给出指令级根因：F10 = 我本轮的构建回归——重编 loader 时裸调 `./build.sh` 漏带 `PAYLOAD_BASE=0xF4000000`，loader 编进了 redwood 默认基址 0xF0000000（udon 上未映射），efi_main→parse_payload 第一次读 `ph->magic` 即同步外部 abort（ESR EC=0x25 / FAR=0xF0000000）。v16b 的 6 个 source hunks 本身无罪（v16 同位指令 = 0xF4000000，真机验证 12 循环无恙）。修正版 v16b'（loader `6c7fdb62…`，PAYLOAD_BASE 指令级钉死进 verify）54/54 全绿已入库，按"改动引入→修复算第 2 轮修正"口径成立，待刷写刷写。手机已回到安卓（安卓在线 slot a）。**

## 0. 一句话结论

v16b（修复预算第 2 轮施工单 ②+③）全部落地：loader.c 六 hunk（去 lazy churn / settle 25s / 3 tries / 冷启动判据行）+ 守护固化进 loader_talk.py（hunt5 范式成为默认行为）+ 四件套自检 + 刷写一次通过。但第一次刷写后的 boot **冻结在 EDK2 异常断言屏**（屏上 `ASSERT ... CpuExceptionHandlerLib.c(438): 0 == 1`，新记账 **F10**）：logdump 与 v16 时代逐字节相同（kernel 会话的 flush beat 根本没跑过）、全程零 `18d1:d00d` 出现、catch 循环 200 轮零 serving——**v16b 的行为变更（25s settle、3 tries、零 lazy churn）从未获得真机验证检验**。冻屏照片（§7）指令级定案：崩点 = loader 自身的 `parse_payload` 首读（`PAYLOAD_BASE` 被裸构建编成 redwood 默认 0xF0000000，udon 未映射）= **本轮构建回归**，与 6 个 source hunks 无关；修正版 v16b'（`e33ec417…`，54/54，F10 pin 双层钉死）已入库待刷写。收尾状态：已停下、手机回到安卓，刷写时机待定。

## 1. 使命执行对照

| 使命项 | 交付 | 状态 |
|---|---|---|
| ② v16b loader 加固 | `patch-loader-v16b.py`（6 hunks，全部唯一性断言）→ WSL loader.c | ✅（§2） |
| ③ host 守护固化 | `loader_talk.py` 管道守护（自检/手术/随机延迟/代际节流，默认行为）+ `catch-and-run.sh` v2 | ✅（§4；另在真实现场击退一次 F9，§4.3） |
| 构建四件套 | cmdline/payload/graft/kernel v16b' + verify 54/54 全绿（含 F10 pin） | ✅（§3） |
| 自刷 + E2E 闭环 | 刷写 OKAY；E2E **未执行**（F10 冻结） | ◑→❌（§5） |
| 判定 | v0.4「达尔文」**不宣告**（推迟）；后续①冷启动 | ✅（§6/§8） |
| 手机收尾 | set_active a 回安卓（SSH 判定前移已执行） | ✅ |

## 2. v16b loader.c 施工（patch-loader-v16b.py，全部 hunk 唯一性断言）

按 wave21_1 §6 施工单②，六 hunks（`wave21-scripts/patch-loader-v16b.py`，sha `12ed4aef…`）：

1. **`usb_lazy_start()` 退役**：函数体清空（保留 watch-loop 调用点与两个前置声明，最小 diff）——运行期不再碰控制器。F8（半启动 zombie）的"工厂"关闭：v15.3 的 20s 退避与 v16 的 20s 节拍在全部观察轮里零成功、且每次失败的 start_ex 都复位 DWC3，能把主机已经枚举中的会话拆掉。boot 期三试全败的会话 = 无 USB 服务器（v15.3 的安全行为），下一 boot 用全新硅片重试。
2. watch-loop 前置声明注释更新（"retired in 21.2"）。
3. `usb_init_kick` / `usb_start_attempt` 注释更新（25s settle；boot 窗专用）。
4. **settle 5s → 25s**（TimerRelative `250000000`；stall 回退 5→25×1s）+ **重试节拍 20s→25s**（TimerPeriodic `250000000`）+ **boot 窗重试 3 次封顶**（`tries >= 3 ||` 90s 界）——时间轴 = 25/50/75s，每一试都是干净代际，无 churn 连锁。
5. **放弃行换新**（施工单②d）：`usb: warm-boot start failed after %d tries; the next cold boot is the clean try` ——§8 冷启动判据卡的读取目标（屏/logdump 双通道）。
6. main() 的 bring-up 注释更新。

不变项（预算内最小改）：USB 服务器行为、netmode/netstat、失败码打印（v16 取证通路）、`usb_ready` 门控、服务窗 240s、180s 会话窗全部原样。

## 3. 构建/自检（v16b 四件套 + 构建链，全部入库；sha 只新增）

> ⚠ 本节为最终态（§7.5 修正后）。首版构建（loader `f445f187…`，payload `083f5fcf…`，graft `bfaae151…`，自检 51/51）因裸调 `./build.sh` 漏带 `PAYLOAD_BASE=0xF4000000` 而**内容错误**（Boot #31 冻屏的直接原因，§7）——51/51 当时未检 payload 基址 = verify 缺口，已补（现 54/54）。

| 件 | sha256（前 16） | 说明 |
|---|---|---|
| `device-layer/udon-hakios-cmdline-v16b.bin` | `675e917817c462ca` | **= v16 字节逐字节相同**（`make-cmdline-v16b.py` 断言：21.2 不动任何 boot-arg；180s 保持；预算 593/608） |
| `device-layer/udon-hakios-payload-v16b.bin` | `af0344d480b9bf6a` | 23,385,608 B；7 条目；**kernel/kernel.ver/resident/ramdisk/cmdline 与 v16 条目逐字节全等**，仅 loader.efi 换新（`make-payload-v16b.sh`） |
| `device-layer/udon-hakios-grafted-v16b.img` | `e33ec417efef97ea` | 192 MiB；FD `8924cb67…`（取自 WSL 构建树）/shim `108ce972…` 未动；`udon-hakios-grafted-v16b.report.json` 随件更新 |
| `device-layer/hakios-kernel-v16b.bin` | `17c905ec240a8b00` | = v15/v16 内核（复用声明件） |
| `wave21-scripts/verify-udon-hakios-v16b.py` | — | **54/54 全绿**（v16 的 49 检 + settle/判据行断言 + 退役行反断言 + cmdline=v16 断言 + loader 钉 `6c7fdb62…` + **F10 pin：entry 0x2140 / @0x2190 movk 0x72AA0AB3 / @0x2198 movz 0x52BE8008 = PAYLOAD_BASE 0xF4000000**） |
| `wave21-scripts/make-cmdline-v16b.py` / `make-payload-v16b.sh` | — | 构建链（payload 脚本内含同款 F10 pin 与拒绝名单 `f445f187`） |

loader.efi v16b = **`6c7fdb62…`**（75,264 B，`-Wall -Wextra` 零警告，`PAYLOAD_BASE=0xF4000000 ./build.sh`）。构建注记：①`device-layer/udon-hakios-SILICIUM_UEFI.fd` 是 wave2 时代旧件（`de4df6ac…`），graft 必须用 WSL 构建树的 FD（`8924cb67…`）——verify 的 FD 钉死断言当场拦下（首版 51 检中 FAIL 后换件重 graft）；②**`build.sh` 的 PAYLOAD_BASE 是大杀器级 landmine**（§7/§9）。

## 4. host 守护固化（loader_talk.py + catch-and-run.sh）

### 4.1 守护进 loader_talk.py（默认行为）

`guardian()` 在**每个开设备模式**（probe/cmd/log/netmode/ping/tunnel/tun）dispatch 前自检（`LOADER_TALK_NO_GUARD=1` 关闭）：

- **F9 直检**：Windows `usbipd list` 显示 `18d1:d00d` 而 WSL `lsusb` 看不见 → **一代际一次 detach→attach 手术** + 术后**随机 4-9s 暂停**（避开 loader start 窗的去同步化）；同代际 30s 内不二次手术。
- **F8/死管道双击确认**：代际（dark→visible 拉伸）内 ≥2 次 bulk 操作无应答、且过 52s（v16b 的三试 = boot 后 25/50/75s，约在代际首见后 52s 全部出尽——手术绝不打断一记可能成功的 start_ex）→ 一次手术；此后本代际纯探测，绝不按 miss 手术（hunt v4 的教训固化）。
- 代际簿记经 `/tmp/loader_talk_guardian.state`（gen/phase/began/misses/last-surgery，跨进程；/tmp 被清 = 自动视为新代际，安全退化）。
- 结果回写：`rc==1`（传输层失败）记 miss，`rc==0` 或 FAIL/DATA 应答（管道活着）记 hit。
- `usbipd.exe` 在 sudo secure_path 下不可见 → `_usbipd_exe()` 解析到 `/mnt/c/Program Files/usbipd-win/usbipd.exe`。

### 4.2 catch-and-run.sh v2

纯探测循环（200 × ~13s）：`getvar:result` 8s 超时 → serving 即进 E2E；idle 则 `oem run` + 55s survey；N1 netmode 环回 → N2 ICMP → N3 `ssh -i id_ed25519_phk110` + `ProxyCommand=…tunnel 10.0.0.2 22` 捕获 `uname -a; ls /`；**手术全部交给守护**（脚本内零 usbipd 调用）。N3 PASS 判据 = 输出含 `WAVE21-SSH-OK`。

### 4.3 守护的实战首胜（刷写通道）

交还安卓前，fastboot gadget 出现 **Windows `Shared (forced)` / WSL 盲** 的教科书 F9 形态 → 手工执行守护同款手术（detach→attach）一次治愈，fastboot 立即可用（getvar taro ✓ → set_active a ✓）。

## 5. 自刷 + E2E 实况（Boot #31，刷的是坏件 bfaae151）

1. 13:37 刷写：WSL root fastboot，`Sending 'boot_b' (196608 KB) OKAY [4.9s]` / `Writing OKAY [0.6s]` + `set_active b` + `reboot`（本地 sha `bfaae151…` 对包——此件含错误 PAYLOAD_BASE，§7）。
2. 13:41 起守护化 catch 循环（后台，200 轮）：**全程零 `18d1:d00d` 出现**（Windows 与 WSL 双侧均无）——因为 loader 在 parse_payload 即崩，USB 服务器从未尝试启动。
3. 13:56 循环退出（200 轮无 serving）。
4. ~13:5x 屏上出现 EDK2 断言屏；随后强启进 fastboot 模式。
5. 13:58 手术治愈 fastboot 管道（§4.3）→ `getvar product=taro` → **`set_active a` + `reboot` 交还安卓**（boot_completed=1，slot a）。
6. 14:01 安卓侧拉 logdump（512 MB，`logdump-v16b.bin`）= **sha `ec271f52…` 与 logdump-v16-final.bin 逐字节相同**——crashed boot 零落盘（内核会话 beat flush 未跑，§7）。

## 6. 判定

| 阶梯 | 设计验收 | 本轮实况 | 判定 |
|---|---|---|---|
| 前置 | v16b loader USB 服务器可用 | 崩在 parse_payload（§7），USB 从未尝试 | ☐ 不可判 |
| N1/N2/N3 | 环回 / ICMP / SSH | 未执行 | ☐ |
| v0.4「达尔文」宣告 | N3 shell | — | **不宣告（推迟）** |
| F10 根因 | — | 指令级闭环（§7）：构建回归非 source 回归 | ✅ 已定位 |
| 预算内修正 | — | v16b'（loader `6c7fdb62…`）54/54 全绿已入库，待刷写刷 | ✅ 就绪 |

**红线执行**：修复预算第 2 轮未达 → 停止，转入收尾。按当时口径，F10 根因 = 本轮构建回归 → 修正算第 2 轮预算内（已完成构建+自检）；**刷写与冷启动时机待定**（本轮止步于纯软件准备、未碰手机）。

## 7. PAYLOAD_BASE 问题解剖（冻屏照片 → 指令级根因；本波最重要的新知）

**F10 = EDK2 异常断言冻结屏**：`ASSERT [ArmCpuDxe] CpuExceptionHandlerLib.c(438): ((BOOLEAN)(0==1))`（= `DumpCpuContext` 尾 `ASSERT (FALSE); CpuDeadLoop ();`）。两张高清照片给出完整寄存器/栈帧现场：

```
Synchronous Exception at 0x00000000FA5901A0
PC 0xFA5901A0 / 0xFA590198（同镜像 2 帧，无符号）
PC 0xFB3269D4 / 0xFB31F578（0xFB313000+…）[1] BdsDxe.pdb
PC 0xFEC45894 / 0xFEC46260 / 0xFEC46250（0xFEC45000+…）[2] DxeCore.pdb
PC 0xA71029BC（FD 区）[2] DxeCore.pdb
SP 0xA764B710  ELR 0xFA5901A0  SPSR 0x205  FPSR 0x10
ESR 0x96000010（EC 0x25 Data abort / IL 1 / ISS 0x10 = L0 translation fault）  FAR 0xF0000000
ConnectSts: Detach, Data Role: UNKNOWN, Lane: OPEN, CoreNum: 0
屏顶：ConvertPages failed A1000000-A198AFFF + Loading driver at 0x000FA58E000 EntryPoint=0x000FA590140
```

**定位根因五步**：

1. **崩点镜像 = 我们自己的 loader.efi**。`Loading driver at 0xFA58E000 EntryPoint=0xFA590140` → 入口 RVA = 0x2140。全 FD 99 个 PE（FFS/FV/nested-FV/TE 全扫，含 lfanew=0 的 GenFv 对齐件）无一 entry=0x2140；但 **`xnuloader/loader.efi` 的 AddressOfEntryPoint = 0x2140 精确命中**。加载机制 = BDS 的 boot 链把 payload 里的 loader.efi `gBS->LoadImage/StartImage`（BdsDxe 栈帧 `ldr x9,[x9,#0xc8]`→`blr` = LoadImage、`ldr x8,[x23,#0x948]; ldr x8,[x8,#0xd0]`→`blr` = StartImage，Boot Services 偏移逐字吻合）——这就是 Boot #9 以来"AfterConsole 自动进 loader"的真实机制首次被看见。
2. **故障指令 = parse_payload 的 magic 读**。v16b loader.efi @RVA 0x2188-0x21A4 反汇编：
   `mov w19,#0x4e58; movk w19,#0x5055,lsl 16`（w19 = 0x50554E58 = **'XNUP' magic**）→ `blr x8` → **`mov w8,#-0x10000000`（= 0xF0000000）→ `ldr w8,[x8]` @0x21A0（= `ph->magic`，FAR 精确命中）→ `cmp w8,w19`**。逐字对应 `parse_payload` 首行 `struct payload_header *ph = (struct payload_header *)PAYLOAD_BASE; if (ph->magic != PAYLOAD_MAGIC)`。
3. **0xF0000000 是 redwood 默认 payload 基址**：`loader.c:22-23 #ifndef PAYLOAD_BASE → 0xF0000000ULL`；build.sh 需 `PAYLOAD_BASE=0xF4000000 ./build.sh` 显式覆盖（STATUS 地址表：0xF4000000 = XNU Payload）。udon 的 `Binaries/udon/RawFiles/uefiplat.cfg` MemoryMap 里 0xF0000000 **无任何区域**（落在 "TZApps Reserved" 0xEA000000-0xF1400000 内，NS 侧未映射）→ 一读即 L0 translation fault。对照组：Samsung 系机型（q2q/r9qb2/a52sxq）的同名 cfg 恰有 `0xF0000000 "SEC Debug"` 映射。
4. **v16 对照 = 我的构建回归，非 source 回归**：从 payload-v16 提取的 v16 loader.efi 同位指令 = **`mov w8,#-0xc000000`（= 0xF4000000）**——上一轮构建带了正确的 PAYLOAD_BASE；我本轮裸调 `./build.sh` 漏带 → v16b 编进 0xF0000000。**v16b 的 6 个 source hunks 无罪**（且 v16b hunks 尚未执行到——崩点在 parse_payload，早于一切 USB/打印路径；`print("no payload at %x")` 在 magic 读之后，永远来不及打）。
5. **静默冻屏的解释**：异常走 EDK2 默认 dump+ASSERT 死循环（loader 的 exception hook 在 hook 安装前不可用；且 hook 只覆盖 sync/SError 类、本崩正是 sync——若 hook 已安装会打 "UEFI EXCEPTION"+reset；此处崩在 efi_main+0x60，install_exception_hook 尚未执行）。

## 7.5 预算内修正（v16b'，已构建待刷写刷）

按当时口径（"若核实 = 你的改动引入 → 修复后算第 2 轮修复预算内的修正"）：

1. **重编**：`PAYLOAD_BASE=0xF4000000 ./build.sh` → loader.efi = **`6c7fdb62…`**（75,264 B；entry 0x2140 @0x2198 = `movz w8,#0xF4000000`，word 0x52BE8008，与 v16 同位一致）。
2. **钉死防复发**（双层）：
   - `make-payload-v16b.sh`：新增断言——entry 必须 0x2140、@0x2190 = `movk w19,#0x5055,lsl16`（0x72AA0AB3）、**@0x2198 = `movz w8,#0xF4000000`（0x52BE8008）**；并把坏件 sha `f445f187` 列入拒绝名单。
   - `verify-udon-hakios-v16b.py`：同样的 F10 pin 两条 + loader sha 钉 `6c7fdb62`。
3. **重建产物**：payload = **`af0344d4…`**（23,385,608 B）；graft = **`e33ec417…`**（192 MiB，FD/shim 未动）；自检 **54/54 全绿**（51 + F10 pin 3 检）。
4. cmd/kernel/resident/ramdisk 四条目与 v16 逐字节不变（未受影响）。

**E2E 前景**：F10 修正后，v16b 的真正行为变更（settle 25s / 3 tries / 零 lazy churn）首次获得真机验证资格。§8 冷启动卡照旧最优（冷启动 + 修正版 v16b 一次同时给 USB 冷电源域与 E2E 窗口）；即使暖刷，v16b' 的 USB 行为与 v16 同基线 + 增强的 boot 窗。

## 7.6 v16b' 真机验证 + 端点墙 + SET_CONFIG 实验 + v16c（DWC3 唤醒）——F10 修复链的收尾

**v16b'（`e33ec417…`）刷写后（Boot #33+ 一连串暖循环）**：F10 断言屏**绝迹**——loader 每 boot 都活着跑到 USB 服务器（`xnuloader` gadget 每轮上总线，Windows 枚举成功）。**PAYLOAD_BASE 修复真机生效**。但新形态 = 屏上"错误墙"：`UsbDeviceSend → DwcPrepareURB:Trb: physical endpoint[2] not configured → UsbfnDwcSubmitUrbNode: PrepareUrb Failed: 0x8000000C → usbDevSsm: Failed to prepare data transfer` 四行一循环持续刷屏——设备 SSM 未达 CONFIGURED，bulk 端点未武装（F8 的设备侧内部视图）。host 侧 hunt1（200 轮）/hunt2（200 轮）全部零 serving。

**SET_CONFIG 实验（零刷写的主机侧判别实验）**：loader_talk.py `ensure_configured()`——connect 时显式 `libusb_set_configuration(1)` + auto_detach_kernel_driver（netmode/ping/tunnel 三路接线）。结果：跨多代际探针一致 = **`set_configuration(1): ok`（设备收下了 SET_CONFIG）+ 描述符/字符串读取全通（ep0 活着）+ OPEN+CLAIM OK + getvar 仍 NO RESPONSE**。按当时的判定分支：**设备侧 DWC3 暖态病坐实**（SET_CONFIG 被收下但 SSM 仍不前进）→ 转 DWC3 CSFTRST + SUSPHY（Qualcomm SM8450 暖态顽疾的官方修法：SUSPHY 门控的寄存器域丢写——GEVNTADR 类——SSM 推不进）。

**v16c 三变体（`patch-loader-v16c.py`，全程 `PAYLOAD_BASE=0xF4000000 ./build.sh`——F10 pin 每版验证）**：`usb_dwc3_susphy_off()`（清 `GUSB3PIPECTL(0)(0xC2C0).SUSPHY(bit6)` + `GUSB2PHYCFG(0)(0xC200).SUSPHY(bit6)`——Linux dwc3 的 dis_u3/u2_susphy）+ `usb_dwc3_wake()`（DCTL(0xC704) RUN_STOP/CS 软断开让主机见真实拔插 → `GCTL(0xC110).CSFTRST(bit11)` 自清轮询 → 再清 SUSPHY；仅 platform_phk110）+ **第三变体新增：start_ex 成功后再清一次 SUSPHY**（vendor 自己的 init 按 snps 默认把 SUSPHY 重新置 1，会把前清覆盖——SET_CONFIG 时刻的 DEPCFG 写再次落入门控域）。三变体 loader = `ee8204e8…` → `e3f51cd4…` → **`45437cd3…`**（最终，75,776 B，零警告）；payload 最终 = `4a2a90ff…`；graft 最终 = **`53f5e077…`**（verify-udon-hakios-v16c.py 53/53，F10 pin 布局无关搜索式 + DWC3 wake 行钉死）。刷写链：cce46f83（e3f51cd4 变体，一次 OKAY）→ **53f5e077（45437cd3 变体，一次 OKAY，双侧 sha 对包）**。

**判定（屏幕实时读数，收尾）**：三变体全部真机验证后**错误墙恒在**（ep[2] not configured / 0x8000000B/C 不变）——基址✓ + 前清✓ + 后清✓ 三重叠加全无效 → **端点未配置不是暖态顽疾，而是 vendor UsbDeviceDxe/UsbfnDwc 栈在 loader 场景下的固有行为**。最可能：UsbfnDwc 期望的 configuration/interface 布局与 loader_talk/Windows 枚举路径不一致，或 vendor 栈需要明示的 ActivateEndpoints 类调用而 fastboot 协议路径没走它。静态扫描佐证：vendor 五模块均不硬编码 0x0A6C110 类绝对地址（运行期从 config/protocol 取基址）——寄存器操作全部经 vendor 栈自己的句柄，loader 侧 MMIO 直写是否真触达同一寄存器域待反汇编 UsbfnDwcSubmitUrbNode/DwcPrepareURB 定案。**下一波方案**：反汇编 UsbfnDwcSubmitUrbNode/DwcPrepareURB 找 ep2 配置判据 + 对照 vendor 正常 fastboot 会话的 ep2 配置路径。

**最终取证（logdump-v16c.bin，`183bb0fc…`，安卓回稳后 adb 拉取）——v16c 事后报告全记录，两个决定性读数**：

1. **`usb: dwc3 soft reset did not settle in one second`** —— CSFTRST 位写进去后**从未自清**（1s 轮询超时）= **寄存器域门控的指令级实锤**：loader 的 SUSPHY 前清没能解开门控（要么 SUSPHY 位/寄存器位置对这块硅片不对，要么门控在 wrapper/GCC 层——GCC USB 时钟投票/pipe_clk，不是 PHY suspend 位能解的）。这解释了端点墙的机理：SSM 的 DEPCFG 写与 CSFTRST 同域同命运（丢写）——而 ep0 枚举却活着（vendor 栈的 ep0 路径可能走不同的寄存器窗口/中断驱动路径）。下一波反汇编 UsbfnDwcSubmitUrbNode/DwcPrepareURB 时，用"CSFTRST 丢写"作为寄存器真伪的试金石。
2. **`usb: started` 首试成功、`try failed: start_ex` 零命中、`no payload` 零命中、`UEFI EXCEPTION` 零命中** —— v16c 的 bring-up 链完全健康：PAYLOAD_BASE 修复持续生效、25s settle 后 start_ex 在安定的平台上一发即中（v16 结论复现）、DWC3 wake 未引发任何新异常（安全失败）。

**手机状态**：ABL 回退链走通（bootloader → set_active a → Android boot_completed=1）——手机已回到安卓。

## 8. 冷启动判据卡（v2；F10 已除名；v16c 刷入后此卡只剩暖复位 start 假设）

**操作**（一次物理动作，手机当前安卓 slot a 在线；**先刷修正版 v16b' = `e33ec417…`**）：
1. （手机在安卓时）`adb reboot bootloader` → `fastboot flash boot_b udon-hakios-grafted-v16b.img`（修正版）→ `fastboot set_active b` → **拔线**；
2. **强制断电**：长按电源 10s+ 至关机（或任何断电方式）；
3. **上电开机**（不按键、不进 fastboot）→ ABL 直引 boot_b = v16b' loader（USB 电源域全冷）；
4. 观察屏：
   - `usb: the platform is asked up; twenty-five quiet seconds before the first try` → `usb: started`（首试成功）→ **E2E 自动接管**（catch-and-run 守护循环已就绪）；
   - `usb: warm-boot start failed after 3 tries; the next cold boot is the clean try`（v16b 判据行）→ 三试全败坐实"暖复位残留"假设；
   - `no payload at …` 行 → 理论不应出现（基址已钉）；若现 = 新回归。
   - F10 断言屏 → 不应再出现（根因已除）；若现 = 另有它病。

**为什么冷启动仍值得**：wave21_1 的 ①卡假设（暖复位留 USB 电源域半初始化态 → start_ex 输）仍未检验；冷启动 + 修正版 v16b' 一次同时给出干净 USB 电源域与 25s settle 三试的增强 boot 窗。即使不做冷启动，暖刷 v16b' 也已回到 v16 同基线。

## 9. 本波教训

- **🔴 `build.sh` 的 PAYLOAD_BASE 是流程级 landmine（本波最大教训）**：裸调 `./build.sh` 会编进 redwood 默认 `0xF0000000`——在 udon 上未映射，loader 第一读即同步 abort + EDK2 DEBUG 冻屏。**每次编 loader 必须 `PAYLOAD_BASE=0xF4000000 ./build.sh`**；现已在 make-payload-v16b.sh（构建时 pin）与 verify-udon-hakios-v16b.py（验收时 pin）双重钉死，坏件 sha `f445f187` 进拒绝名单。
- **verify 只钉 sha 不钉语义 = 缺口**：首版 51/51 全绿挡不住错误基址（sha 是自己刚产出的）。凡带编译期常量的产物，验收必须 pin 语义（指令/常量级），不止字节。
- **loader 的启动机制首次看清**：BDS 经 `gBS->LoadImage/StartImage`（BdsDxe 帧 Boot Services 偏移 0xC8/0xD0）把 payload 里的 loader.efi 当 UEFI 应用启动——Boot #9 "AfterConsole 自动进 loader"之谜的机制侧答案。
- **EDK2 DEBUG assert = 冻结屏**（非 reset、非 panic 循环）：`ASSERT(FALSE)+CpuDeadLoop` 不喂看门狗——手机永久冻屏直到人工强启；且 install_exception_hook 之前的崩（如 efi_main 极早期）hook 不可达。任何"下一版可能崩在 UEFI 层"的刷写都要先给出强启配方。
- **device-layer 里的 FD 提取件是 wave2 旧物**（`udon-hakios-SILICIUM_UEFI.fd` = `de4df6ac…` ≠ 在机 `8924cb67…`）——graft 的 FD 必须取 WSL 构建树；verify 的 FD 钉死断言救了一次错误 graft。
- **守护固化即刻回本**：固化当天就在刷写通道击退一次真 F9（§4.3）。
- WSL `/tmp` 跨调用清空（老 footgun 再证）：备份件放 /tmp 会被吃，patch-apply 要单命令闭环。
- 后台长循环经 `wsl.exe bash -c 'nohup … &'` 会在会话结束时被杀——要用工具的原生 run_in_background。
- 屏幕照片是最高价值取证：两张高清照片一步定位到指令级（此前三条静态推论链都只是逼近）——下次冻屏第一时间拍照。

## 10. 安全与回滚状态

- 手机：**安卓在线（slot a 活跃，boot_completed=1），回到安卓**；userdata/darwin 未触碰。
- **slot b = 坏件 v16b（`bfaae151…`，PAYLOAD_BASE=0xF0000000）仍在分区上**——不可直接引导使用（引 = F10 冻屏）；下次刷写务必刷修正版 **v16b' = `e33ec417…`**。回退链完整：v16（`2e1a2532…`）、v15.3（`d117e48c…`）。
- F10 风险面：只存在于缺 PAYLOAD_BASE 的 loader 构建；修正后该病根已从产物层钉死。
- E2E 物料全备：守护化 loader_talk/catch-and-run + SSH 密钥 + 判据（`WAVE21-SSH-OK`）——修正版刷入后闭环只差执行。

## 11. 交付清单（全部 git add，未 commit）

| 类 | 件 |
|---|---|
| v16b 四件套（修正版 v16b'） | `device-layer/udon-hakios-cmdline-v16b.bin`（`675e9178…`）/ `udon-hakios-payload-v16b.bin`（`af0344d4…`）/ `udon-hakios-grafted-v16b.img`（`e33ec417…`）/ `hakios-kernel-v16b.bin`（`17c905ec…`）+ `udon-hakios-grafted-v16b.report.json`（随件更新） |
| 补丁/构建/自检链 | `wave21-scripts/patch-loader-v16b.py`（`12ed4aef…`）/ `make-cmdline-v16b.py`（`188300d6…`）/ `make-payload-v16b.sh`（含 F10 pin 与 `f445f187` 拒绝名单）/ `verify-udon-hakios-v16b.py`（54/54，loader 钉 `6c7fdb62…` + F10 pin） |
| 守护固化 | `wave21-scripts/loader_talk.py`（guardian/guard_miss/guard_hit + usbipd 路径解析）/ `catch-and-run.sh`（v2 纯探测） |
| 取证 | `logdump-v16b.bin`（`ec271f52…` = v16-final 逐字节相同——F10 零落盘证据）+ `catch-v16b.log` |
| WSL 树（未 commit，统一处理） | `~/hakios/kernel/xnuloader/loader.c`（v16b 六 hunks）+ `loader.efi`（`6c7fdb62…`，PAYLOAD_BASE=0xF4000000 正确构建，待随下一次刷写上线） |
