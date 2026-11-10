# 阶段 21-3 · 2026-11-08 · 冷启动对照实验：排除环境因素

> 2026-11-08 · 冷启动判据卡 v2（wave21_2 §8）的关键实验。流程：set_active b（零刷写）→ 物理断电冷启动 → 拉取 logdump（14:01）并判读"读数 1 成立" → 逐字节复核 → **判定反转**。
> **判定：冷启动对 logdump 分区零写入——`logdump-v16b.bin`（14:01）与 `logdump-v16-final.bin`（13:10）cmp 零差异、md5 同为 `714ceb2e…`，CPU_ON 依旧未达。当时的"读数 1 成立 / 暖复位假说证实"判读被判伪（全部证据行均为 v15.3/v16 时代陈旧字节，见 §3）。判据卡实际读数 = ③形态（死亡在冷态复现，bytes 级）；暖复位假说证伪——本轮冷 boot 前零 fastboot 传输（仅 getvar/set_active），"192MB 传输残骸"变量根本不存在，冷态照样死。死点二叉开放：DXE 期异常（#31 同型）或 v16b loader 早期死亡（#32 无屏幕证据，不排除），屏幕照片是分叉的唯一裁决。后续转入 v16b-c 诊断构建（已备方案升级为唯一前进路线）+ 索取冷启动屏照片。手机已回安卓（slot a）交还。**

## 0. 一句话结论

冷启动没有改变任何字节。512 MB 的 logdump 分区在 F10 轮（#31）之后又经历了整整一次断电冷启动（#32），落盘字节与 13:10 的 v16 时代完成件**全等**。write_logs 从 LBA 0 整分区覆盖的机制（wave21_1 §2 取证钉死）决定了：任何一次跑过内核 beat 的 boot 都会把分区整段换成自己的会话——全等 = beat 从未执行 = CPU_ON 从未到达。判据卡的三读数里，①②宣告不成立，③形态在 bytes 级成立。**v16b 的代码连续两轮（#31 暖、#32 冷）零执行证据；暖态救不了它，冷态也没救成。**

## 1. 判据卡三读数 vs 实际读数

| 读数（wave21_2 §8 卡 v2） | 预言 | 实况 | 判定 |
|---|---|---|---|
| ① settle 行 → `usb: started` → catch-and-run 接手 E2E | 屏见 v16b settle 行，loader serving，N1→N2→N3 | catch-v16b.log 收束行 `[catch 13:56:25] 200 passes without a serving loader: no verdict this round`——零 serving；logdump 零新字节，N1/N2/N3 无从谈起 | ❌ **未发生** |
| ② 判据行 `warm-boot start failed after 3 tries` → 暖复位假说证实 | 三试全败行落屏/落盘 | v16b 的 settle 判别行 `twenty-five quiet seconds` **全分区 0 命中**——v16b 连第一行打印都没打出来，判据行无从谈起 | ❌ **不适用**（"成立"的判读系陈旧字节误读） |
| ③ F10 复现 → DXE 崩与暖态无关 → v16b-c 路线 | 冷态也死 | 零字节 + 零 serving + 手机事后自发回安卓（回退链走通） | ✅ **bytes 级成立**（"是否 #31 同型"待屏幕证据，见 §5 死点二叉） |

## 2. 证据链（五重证据）

1. **md5 同体（决定性）**：`logdump-v16b.bin` ≡ `logdump-v16-final.bin`，md5 均 `714ceb2ea68e7192cb790a63096def3b`，512,870,912 B cmp 零输出。write_logs 每次 boot 从 LBA 0 整分区重写（wave21_1 §2 取证链钉死的机制）→ 任何到达 beat 的 boot 必然整段替换分区内容 → 与 13:10 字节全等在物理上排除"本次会话曾落盘"。
2. **判别字符串缺席**：v16b 的 settle 行是 `usb: the platform is asked up; twenty-five quiet seconds before the first try`（patch-loader-v16b.py 把 five 行改写二十五行 + make-payload-v16b.sh 断言 `asked up; five quiet seconds` 不得残留）。全分区 grep `twenty-five` **0 命中**；`five quiet seconds` 仅 1 命中 @字节 476 = S1 会话头。**v16b 的 loader 代码从未执行到第一行打印**——该判别行的设计价值在本轮兑现（以缺席的方式一 grep 定案）。
3. **S1 会话头属于 v16**：@476 `usb: the platform is asked up; five quiet seconds before the first try` → @516 `usb: started`——wave21_1 §2 取证已逐字文档化的 v16 时代成功 boot 形态（`logdump-v16-run1/final` 双份独立复现）。不是本次冷启动的输出。
4. **零 serving（窗口相关，佐证级）**：catch-and-run 守护循环全程零应答（收束行 13:56:25）。v15.x 时代至少一次 serving 窗被 host 探到过（wave21-ssh-e2e.md §3 真机实证 + STATUS.md #26-29 行 F7 记录"唯一 serving 窗恰逢新鲜 detach→attach"），故"可探"成立；本次 200 轮零探到。软点如实标注：若现场冷 boot 晚于 catch 收束（13:56:25），此条降权——但零字节判定不受影响。
5. **回安卓路径旁证**：14:01 的拉取走 adb 通道（wave21_1 收尾拉取同款先例）→ 手机在 14:01 已回安卓 = 冷 boot 死亡后回退链走通（ABL ~8 轮自动回退配方，wave21_1 记录；或按强启配方人工介入）。回退链的前提是 slot b 一次次失败——与零字节互洽。

## 3. 判读复核表（当时的判读 → 逐行回源）

初步取证把 5 个陈旧会话（S1-S5）读成了本次冷启动。logdump 是覆盖+追加混合的记录体，任何读数必须先做会话分段（END OF LOG 偏移表：65013 / 75482 / 168212 / 548686 / 751830）+ 与上一轮 dump cmp。逐行判伪：

| 转述"冷启动读数" | 字节位置 | 真实归属 |
|---|---|---|
| `usb: started` 首试成功 | @516（S1 头） | v16 时代 boot（wave21_1 §2 取证同一行） |
| settle 25s 修复在冷启动下有效 | —— | **该行不存在**：`twenty-five` 0 命中；修复从未真机验证执行（wave21_2 §0 结论在冷态下继续成立） |
| `/private/var: HFS Plus … kept between boots`（S6） | @36099（S1） | S6 验收行自 v13 起常驻 payload，v16 时代会话同样打印——归 v16 时代会话 |
| `net: en0 attached … link up` | @55975/148209/433094/630053（S1/S3/S4/S5） | v15/v16 时代 4 会话 × en0（wave21-ssh-e2e.md §3 同源） |
| `net: en0 has 10.0.0.2/30` | @59637/153925/438872/635773 | 同上，v15 时代内核态配置验收行 |
| TouchComm v1 firmware | @59437（S1）/153725（S3） | v10e 起常驻 payload 的 probe 行，归 v16 时代会话 |
| `hardware target : d22ap` | @82145（S3） | wave20 验收行，归 v16 时代会话（非本次，wave20 修复的"实锤"仍在 wave20 自己的 Boot #25） |
| `tcp listen: [0.0.0.0:22] sshd @163.5s` | @744171/744313（S5 尾） | v14/v15 时代会话的 sshd 监听（STATUS.md #25 行 / wave20 b25 日志同源） |
| `en0 so far 1 frames sent (42 bytes)` | @63882/165491/451313/741885 | v15/v16 时代 4 会话的 en0 帧（wave21-ssh-e2e.md §3 同源） |
| 会话存活 212s+ | S5 末时间戳 1970-01-01 08:03:47 = 会话 +227s | v15.3 时代 300s 窗会话的尾段 |
| **新发现 post-return panic（CORE 1 / pid 1: init / return 后 ~30s）** | @66481/67102（S2 内）：`CORE 1 is the one that panicked… Panicked task …: pid 1: init` + 7 核 PC/LR dump | **不是新发现**——wave21-ssh-e2e.md §4/§5 已文档：vnode 表耗尽 @218s → pid 1 panic → stackshot → clean PSCI return。"阶段 20.5 课题"登记撤销 |
| **新发现 init[1] CPU 唤醒风暴（~838 次/s @119s）** | S5 launchd 重复日志（`Last log repeated 2977 times` 等） | 同一 v15 时代链的 launchd 收尾形态——非新发现，并入上条撤销 |
| Boot #26/27 编号 | —— | 台账修正：#26-29 已被 阶段 21 v15.x 占用，#30 = v16，#31 = v16b F10，本次冷启动 = **Boot #32** |

## 4. 时间线重建（2026-11-08 下午）

| 时刻 | 事件 | 证据 |
|---|---|---|
| ~13:1x | wave21_2 完成 + 本代理第一段布置：getvar taro → `set_active b`（验证 current-slot: b）→ 手机留 fastboot，等待冷启动 | 本代理第一段回合 |
| ~13:13 | catch-and-run 守护循环启动（200 轮 × ~13s 预算） | catch-v16b.log 末行时刻反推（±1 轮） |
| 13:2x–13:5x | 物理冷启动：拔线 → 长按电源 10s+ 强关 → 上电（不按键）→ 等待 → 插回数据线 | 按此流程执行 |
| （窗口内） | **Boot #32：ABL 引 boot_b（v16b `bfaae151…`）→ 死于 CPU_ON 之前**——settle 行未打出、USB 未 serving、beat 未跑、logdump 零写入 | §2 五重证据 |
| 至 13:56:25 | catch 200 轮零应答收束 | catch-v16b.log 末行 |
| ~13:5x–14:01 | 回退链走通（人工强启/ABL 自动回退），手机回安卓 | adb 通道拉取成立 |
| 14:01 | logdump 拉取 → 与 13:10 字节全等 | 文件 mtime + md5 `714ceb2e…` |
| ~14:0x–14:3x | 手机 reboot bootloader（交接准备）；本代理唤醒时管道呈 F9 残留导出形态（Windows Attached / WSL 瞎），detach→attach 手术一次治愈 | 本代理二段回合现场记录 |
| 14:31–14:35 | 确认 ABL fastboot 在线 → `set_active a` + reboot → **安卓 16 在线**（boot_completed=1，bootreason=bootloader，slot=_a）——交还完成 | 本代理二段回合 |

## 5. 判定与假说状态

**判据卡结算**：读数①②不成立，读数③形态 bytes 级成立。**暖复位假说：证伪。**

| 假说（wave21_2 §7.5/§8） | 本轮前 | 本轮后 |
|---|---|---|
| 冷启动给 DWC3 干净状态 → v16b settle 25s + 3 tries 成功（暖复位 USB start 假设） | 待验证 | **证伪**——冷态同样死在 beat 之前；且本轮冷 boot 前只有 getvar/set_active 轻量 fastboot 流量（红线零刷写），"192MB 传输残骸"变量不存在，死因与它无关 |
| F10 触发候选："fastboot 192MB 传输 + 暖复位重入态" vendor USB DXE abort | 主候选 | **画像修正**："192MB 传输 + 暖复位"既不必要（本轮全冷、无传输、仍死）也不充分（v16 时代暖复位多轮未踩中）。F10 触发条件回到开放集合 |
| v16b 行为变更（settle 25s + 3 tries）从未真机验证执行 | 成立（F10 挡路） | **继续成立**——连续两轮零执行证据；v16b-c 解锁前无法被检验 |

**死点二叉（#32 特有的开放问题，屏幕照片裁决）**：
- **叉 A（#31 同型）**：DXE 期 EDK2 异常断言冻屏（冷态复现）→ 病灶在 vendor DXE 栈/FD 层，与 v16b 代码无关。
- **叉 B**：v16b loader app 已被 BDS 启动、在自己的早期（首行打印之前）死亡——若死法是异常+reset（loader hook 路径，屏见 `UEFI EXCEPTION type=…`）则手机会自发循环回退（与 14:01 已回安卓的时间线更顺），且这是 **v16b 六 hunks 第一次真正执行**的可能性：崩在 usb_init_kick 退役后的新初始化流里。零字节与"死在首行打印前"完全相容——#32 没有屏幕证据，叉 A/B 不可判。

**v16 冷启动对照实验（新增施工单首位，需批准——涉及一次刷写）**：`fastboot flash boot_b v16 镜像 + set_active b + 断电冷启`。v16 冷活 → F10 锁定 v16b 载入路径差异（叉 B 加权）；v16 冷死 → 病灶在 FD/DXE 环境层（叉 A 加权）。一次实验把二叉收窄成单叉。

## 6. 后续任务单（v16b-c 升级要点）

wave21_2 已备方案（hook 状态打印 + usb_start 后 flush 检查点）升级为**唯一前进路线**，本轮追加四项：

1. **打印下沉到 DXE 层**：若叉 A 成立，loader app 内的打印一行都不会出现——UsbConfigDxe/UsbFnDwc3Dxe 的 Start/Stop 事件需要 vendor FD 层的前置探针（0x11038 译码器旁），落屏通道（DXE 期 write_logs 不可用，屏/UART 是唯一活通道，§9 老教训）。
2. **flush 检查点双前移**：loader app 入口第一行打印后立即 flush 一次（把"loader 活着"钉进分区，直接裁决叉 A/B）；usb_start 返回后立即 flush（原 §9 已备）。
3. **v16 冷启动对照实验**（§5 末段，需批准）。
4. **屏幕照片制度化**：F10 的 ELR 反查（wave21_2 §7 遗留）仍缺一张屏照片——下次冷 boot 请拍摄/assert 全文转述（强启配方已告知）。DumpCpuContext 的 ESR/ELR 可把死点钉到函数级；叉 A/B 的裁决也全靠它。

## 7. 本波教训

- **转述证据必须逐字节回源**：logdump 一次 cmp 就能终结"读数"——判据卡 v3 应内置"先 cmp 后读数"规则：任何会话级结论必须（a）END OF LOG 分段（b）与上一轮 dump 比对（c）判别字符串 grep 三件齐。
- **判别字符串是取证的生命线**：`twenty-five quiet seconds` 全分区零命中，一条 grep 终结转述的"读数 1"。v16b 的判据行设计在本轮兑现了它作为"行为在机证明"的价值——尽管代码从未执行。
- **拉取通道本身是证据**：14:01 的 adb 通道 = "手机当时在安卓"这一关键推论的来源。wave 记录应注明每次拉取的通道与时刻。
- **F9 残留导出在 WSL VM 生命周期上再现**：跨命令间隙 WSL VM 退出后，usbipd 仍报 Attached 而 vhci 盲——每代际一次 detach→attach 手术的老配方继续有效；跨命令必须同链先唤醒 WSL 再 attach。

## 8. 安全与回滚状态

- 手机：**安卓在线（slot a，boot_completed=1，bootreason=bootloader = 交接 reboot），回到安卓**；userdata/darwin 未触碰。
- **boot_b = v16b（`bfaae151…`）仍在**——v16b-c 与冷启动对照实验的现成试验件；回退链完整：v16（`2e1a2532…`）、v15.3（`d117e48c…`）。
- 本轮零刷写（红线达成）：fastboot 通道只走了 getvar / set_active；`set_active a` 交还不算写入。

## 9. 交付清单（git add，未 commit）

| 件 | 说明 |
|---|---|
| `docs/waves/wave21_3-coldboot.md` | 本报告 |
| `docs/STATUS.md` | Boot #32 行新增 + v16b 镜像行注记（冷启动判读指针） |
| `logdump-v16b.bin` | **无需重新入账**——本次拉取与已入账字节全等（md5 `714ceb2e…`），是对"零字节判读"的复测而非新证据 |
| `wave21-scripts/catch-v16b.log` | 已入账（wave21_2 交付），无新字节 |
