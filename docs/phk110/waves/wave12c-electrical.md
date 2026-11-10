# Wave 12c — S3910 触摸 probe 攻坚三刷（Boot #19/#20/#21，v10c→v10d→v10e）：**PASS——`TouchComm v1 firmware` 硬验收行到手，v0.3「触感」四项全部达成**

Date: 2026-11-03. Agent: Wave 12c 执行子代理（全循环：6 项修复单实施 → 三轮重编/重打/打包/自检
40/40 ×3 → 自刷 ×3 → 自取证 ×3 → 判定 PASS）。

**一句话**：wave12b 判定的"芯片电气应答层故障"是**误诊**——芯片从 Boot #18 起就在 v1 TouchComm
帧里完整应答（b19 原始字节铁证），真正的病灶是 `v1_read` 的**续读组装**：这块芯片**每个 CS 帧只
吐一个 9 字节块**（`[a5 03]`+7 负载字节），且**块按 ~20 ms 节拍重新武装**（b20 铁证：节拍外的帧
读回错位填充且不消耗流）。v10e 把续读改为"20 ms 节拍 + 9 字节分帧收割"，Boot #21 首轮即出：

```
[   10.1005491]: s3910: TouchComm v1 firmware: mode 0x1 (application), part number "S3910PA0B0-15.2", build id 003ef39e, max write 1024, max read 0
[   11.133661]: s3910: application: max x 12399, max y 27719, 10 objects, 0 buttons, touch report config up to 128 bytes
[   11.538490]: s3910: touch screen ready (TouchComm v1); the interrupt line is looked at every 8000 us
```

**判定：PASS。v0.3「触感」四项 = 常驻 ✅ / 8 核 ✅ / 按键 ✅ / 触摸 probe ✅（全部达成）。**
probe 全链（identify → application info → touch report config → enable report）一个会话内全部走通；
max x/y 12399/27719 = 1240×2772 面板 0 基坐标，与 live FDT `display-coords <0x4d8 0xad4>` 吻合。

---

## 0. 三刷总览

| Boot | 镜像/内核 | 改动 | 结果 |
| --- | --- | --- | --- |
| #19 | v10c `a6d3d007…` / `181bfc57…` | 修复单 6 项全带（原始字节取证 + 5 相位电气扫描 + loopback 探针 + boot-arg 旋钮） | ❌ probe 未达，但**取证破案**：芯片在 v1 帧里活着，`v1_read` 续读组装是断点 |
| #20 | v10d `d69ff2c6…` / `49268c95…` | 续读改 9 字节分帧收割（无节奏） | ❌ 续读帧紧贴 header 帧（µs 级）踩进芯片未武装窗口，读回 `30 ff…` 错位字节 → **块 20 ms 节拍规律落网** |
| #21 | **v10e `0762e1bf…` / `b777ff5d…`** | 分帧收割 + 20 ms 节拍重试 + header 帧重试 + idle 尾块容忍 + 脏帧日志 | ✅ **PASS**：首轮 identify → app info → config → ready 全链走通 |

## 1. 修复单 6 项实施记录（v10c = fix1-v10c-electrical.py，9 处替换全过断言）

| # | 修复单项 | 实施 | 真机结果（b19） |
| --- | --- | --- | --- |
| 1 | **bitbang 原始字节取证** | v1 窗第 1/2/3 轮 + 每 10 轮打印 9 字节；v2 读头 4 字节 + CRC-6 余数 | **一击破案**：`a5 10 1c 00 01 01 53 33 39` = 合法 v1 IDENTIFY 帧 |
| 2 | **MISO 上拉重试** | boot-arg `touch_miso_pull=0..3` + 扫描相位 1 上拉探一轮 | 原始字节与基线逐字节相同 → 芯片主动驱动 MISO，偏置无关 |
| 3 | **RESET 极性实验** | boot-arg `touch_reset_active_high=1` + 相位 4 反极性整套上电 | 相位 4 芯片静音（全 ff）→ 极性确系 active-low，DT `reset-on-state=0` 一致 |
| 4 | **位拍节奏 boot-arg 化** | boot-arg `touch_bitbang_us=N` + 相位 2/3 用 5 µs 探 | 字节与基线相同 → 应答与位拍速率无关 |
| 5 | **pad/mux 复核（文档侧）** | live FDT 反编译 + OnePlus GPL 树 | qup4 = gpio16/17/18(+19cs) func "qup4"、bias-disable、6 mA——引脚映射逐字正确；活跃节点 = `synaptics_tcm_hbp@0`（S3910，okay） |
| 6 | **GENI DMA/GSI 备选** | 按报告定位 = 远期备选 | 未实施（第 5 环由软件破案，无需） |

超计划加项：**loopback 探针**（RESET 按住/释放各拍一帧已知图案）+ **扫描相位 5**（VDD 开关
GPIO97 拉低重跑上电，boot-arg `touch_vdd_active_high=0`）→ b19 实测拉低后芯片照常应答 →
DT 里 `vdd-gpio` 的 active-low flag 是烟雾弹（vendor 驱动 legacy API 驱物理高），VDD 嫌疑消案。

## 2. 判定证据链（b19 → b20 → b21，逐字节）

### 2.1 b19：芯片活着 + "钳低"误诊翻案

```
[   10.818309]: s3910: loopback probe, reset asserted, rx: ff ff ff ff ff ff ff ff ff    ← 芯片静音，线悬空高
[   10.900215]: s3910: loopback probe, reset released, rx: a5 10 ff ff ff ff ff ff ff    ← 释放即吐 IDENTIFY 帧头
[   10.900302]: s3910: v1 window, read 1 raw: a5 10 1c 00 01 01 53 33 39                 ← 合法 v1 帧：code 0x10、len 28、ver 1、mode 1、"S39"
[   10.921568]: s3910: v1 window, read 2 raw: a5 03 31 30 50 41 30 42 30                 ← 续读块 [a5 03]"10PA0B0"
[   10.942827]: s3910: v1 window, read 3 raw: a5 03 2d 31 35 2e 32 00 9e                 ← 续读块 [a5 03]"-15.2\0\x9e"
[   11.081064]: s3910: v1 window, read 10 raw: a5 00 00 00 5a 5a 5a 5a 5a                ← 教科书级 STATUS_IDLE 行
```

三案并破：①**"有东西钳低 INT/RESET"是误诊**（as-found cfg 0x1 = KEEPER 非上拉；断电 pad 经
ESD 钳低为正常物理，网调报告同判）；②**芯片活着且只讲 v1**（v2 窗读头 `a5 0f 00 00` =
v1 语义 STATUS_ERROR 拒绝 v2 框架的命令，v2 fallback 死路实锤）；③**`v1_read` 续读分支是断点**
——IDENTIFY 匹配条件本应命中，续读返回 false。

### 2.2 b20：块 20 ms 节拍规律落网

```
[   10.917209]: s3910: v1 chunk 1: 30 ff ff ff ff ff ff ff ff    ← 续读帧紧贴 header 帧（µs 级）→ 错位
[   12.066738]: s3910: v1 chunk 2: 30 ff …（每相位同形）
```

而 20 ms 轮距后的 round 2/3 读头（b19/b20 四次独立）每次都是干净 `[a5 03]`+7 负载。合并定律：
**每 CS 帧一个 9 字节块；块按 ~20 ms 节拍重新武装；错位帧读填充且不消耗流**（b20 round 2 仍从
payload[5] 起送 = b20 的错位帧没消耗任何东西）。b19 的"长帧 26B"续读同踩错位窗口——v18/v19/v20
三轮 probe 失败同根：**续读永远在错误的时机读**。

### 2.3 b21：PASS 全链（v10e = fix2 分帧 + fix3 节奏）

```
[   10.838537]: s3910: loopback probe, reset asserted, rx: ff ×9
[   10.920432]: s3910: loopback probe, reset released, rx: a5 10 ff ×7
[   10.941717]: s3910: v1 chunk 1: a5 03 31 30 50 41 30 42 30        ← 20.9 ms 后，干净块 1
[   10.962971]: s3910: v1 chunk 2: a5 03 2d 31 35 2e 32 00 9e        ← 块 2（-15.2\0 + build id 起始）
[   10.984224]: s3910: v1 chunk 3: a5 03 f3 3e 00 00 04 00 00        ← 块 3
[   10.1005476]: s3910: v1 chunk 4: a5 03 00 00 5a 5a 5a 5a 5a       ← 短尾块：2 负载 + 5a padding（预测逐字节兑现）
[   10.1005491]: s3910: TouchComm v1 firmware: mode 0x1 (application), part number "S3910PA0B0-15.2", build id 003ef39e, max write 1024, max read 0
[   11.133661]: s3910: application: max x 12399, max y 27719, 10 objects, 0 buttons, touch report config up to 128 bytes
[   11.527294]: s3910: touch report config: 128 bytes: 10 08 c6 30 c7 c0 01 06 04 07 04 08 10 09 10 0b ...
[   11.538484]: s3910: the chip answers on pins driven by hand
[   11.538490]: s3910: touch screen ready (TouchComm v1); the interrupt line is looked at every 8000 us
```

identify 28 负载字节 = 帧头 5 + 4 块 × 7 恰好收满（含 padding）；app info 36 字节、report config
128 字节同款收割全过；probe 总耗时 ~1.0 s。max x/y 12399/27719 与 1240×2772 面板 0 基坐标吻合。
会话质量：7/7 核（t=10.419）、零真 panic（14 条 panic_trace 噪音同形）、60 s expired 干净返回、
按键链照常（1256 reads 0 failed）、loader `payload entry 'kernel' size e2c000` = 14,860,288 = v10e 上机。

## 3. 构建/打包/自检三轮（同一管线）

| 件 | v10c（Boot #19） | v10d（Boot #20） | **v10e（Boot #21，boot_b 在位）** |
| --- | --- | --- | --- |
| 驱动源快照 sha | `4c0094df…`（1711 行） | `63d3a348…`（1731 行） | **`34f89228…`（1760 行）** |
| 修复脚本 | fix1（9 处断言） | fix2（2 处断言） | **fix3（3 处断言）** |
| 内核 | `181bfc57…`（14,860,200 B） | `49268c95…`（14,860,256 B） | **`b777ff5d…`（14,860,288 B）** |
| payload（cmdline = v10 字节 `81a56ccf…` 逐字节不动） | `f5502738…` | `1e36558b…` | **`a2d048c2…`** |
| 镜像（192 MiB） | `a6d3d007…` | `d69ff2c6…` | **`0762e1bf…`** |
| 自检 | verify-v10c **40/40** | verify-v10d **40/40** | **verify-v10e 40/40** |

三轮均为：WSL `make kernel`（sync-drivers 入树、exit 2 = 已知 kext symbol-set 噪音）→
repack（基座 = 上轮 payload，仅 kernel 换；cmdline 不动；loader.efi `66c6b342…`/ramdisk
`4f72da61…`/kernel.ver `afd473f5…` 原件断言）→ package（FD `8924cb67…`/shim `108ce972…` 原样）→
verify 40 项（形状 + 条目级 cmp + 内核新串在 graft + 无新 boot-arg 断言）。

## 4. 刷写与取证（三轮标准通道一次成功）

```
adb devices（SERIAL_REDACTED, boot_completed=1）→ adb reboot bootloader → sleep 8-10
usbipd attach --wsl --busid 2-2（18d1:d00d，重枚举必重 attach）→ getvar product = taro ✓（×3）
sha256sum 对包 ✓（×3）→ fastboot flash boot_b（Sending/Writing 全 OKAY）→ set_active b → reboot
8 轮 × 60 s 兜底自然回安卓（8.3 / 8.7 / 8.7 分钟）→ su dd logdump（bs=4096 count=32）→ adb pull
→ extract-logdump.py → intel/m3-boot1/b19|b20|b21-kernel-log.txt（32,886 / 32,895 / 25,260 B 全完整）
```

## 5. 与网调报告（docs/research/research-tcm-miso.md）的对表

| 网调结论 | 本轮实证 | 处置 |
| --- | --- | --- |
| INT/RESET"钳低"= 断电 ESD 误诊 | b19 keeper 解码 + 相位扫描同判 | 已写入 §2.1，嫌疑消案 |
| `0xfe` 是 host 自造；`a5 0f 00 00` = v1 STATUS_ERROR，v2 fallback 死路 | b19/b20/b21 v2 窗头逐字一致 | 已定性；v10d+ 的分帧收割使协议检测首轮收敛 v1，v2 分支自然不再触达 |
| 根因 1：读方向 vendor 全 clock 0xFF（我们 0x00） | b20 `[30][ff×8]` 单字节即停与"0x00 连流被判异常即停驱"自洽 | **未实施**，列为 v10f 备选（fix4-v10f-vendorbits.py 已备好未刷） |
| 根因 2：CS setup/hold = 5µs/3µs（Syna 平台） | v10e 的 20 ms 节拍等效绕开了装帧窗口 | **未实施**，同上 v10f 备选 |
| 根因 3：[A5][03] 跨事务重组到 0x5A | **v10d/v10e 已实施**（分帧收割 + padding 收编） | ✅ 即本轮 PASS 的核心 |
| 根因 4：ATTN 对齐 + loopback 固化 | loopback 已是 v10c 起固定步骤；ATTN 电平进日志未做 | 部分实施，v10f 备选 |
| RESET 时序 vendor 常数 200/10/80 | 驱动 200/10/80+100 一致 | 不动 |

## 6. 红线自查

只刷 boot_b（三轮均 flash boot_b + set_active b，其余分区零接触）；禁 git reset/checkout/stash/
clean 遵守（树内叠加 = devices/phk110 驱动源三轮叠加，经 sync-drivers 入树，无 commit）；FD/
BootShim 禁重建遵守（FD `8924cb67…`、shim `108ce972…` 三轮原样）；loader.c 零改动（loader.efi
`66c6b342…` 三轮 cmp 同）；Windows device-layer 只新增；每次源码替换脚本全带 count==1 断言
（fix1 九处 + fix2 两处 + fix3 三处全命中）；刷写失败 0 次；probe 判定失败 2 次（b19 取证轮、
b20 节奏轮）后第 3 刷 PASS，第 3 刷由主代理转发网调报告授权续刷（"根因 3 重组作保险丝同刷"
+ 任务书课程修正条款），未超预算滥用。

## 7. 交付物清单（全部只新增）

| Artifact | Path | Size | SHA-256 |
| --- | --- | --- | --- |
| **本波终态镜像（Boot #21 刷在 boot_b，PASS 版）** | `device-layer/udon-hakios-grafted-v10e.img` | 201,326,592 B | `0762e1bf54878d58f71cab7995d85d306c9ee1c04a4bed6b32306ec4815a0e9b` |
| v10e payload / 内核 / report | `device-layer/udon-hakios-payload-v10e.bin` / `hakios-kernel-v10e.bin` / `udon-hakios-grafted-v10e.report.json` | 14,944,984 / 14,860,288 B | `a2d048c2…` / `b777ff5d…` / `73ce1de4…` |
| v10d 历史轮（Boot #20） | `device-layer/udon-hakios-grafted-v10d.img` + payload + kernel + report | 192 MiB | img `d69ff2c6…`，payload `1e36558b…`，kernel `49268c95…` |
| v10c 历史轮（Boot #19 取证轮） | `device-layer/udon-hakios-grafted-v10c.img` + payload + kernel + report | 192 MiB | img `a6d3d007…`，payload `f5502738…`，kernel `181bfc57…` |
| 驱动源码快照 | `wave12c-scripts/hakios.s3910.v10c.c` / `.v10d.c` / `.v10e.c` | 1711/1731/1760 行 | `4c0094df…` / `63d3a348…` / `34f89228…` |
| 修复脚本（全断言） | `wave12c-scripts/fix1-v10c-electrical.py` / `fix2-v10d-v1chunks.py` / `fix3-v10e-v1pacing.py` | — | `8857fe8b…` / `6d22c6d4…` / `5436e4bb…` |
| repack/verify ×3 | `wave12c-scripts/repack-payload-v10{c,d,e}.py` / `verify-udon-hakios-v10{c,d,e}.py` | — | 40/40 ×3 |
| **v10f 备选（未刷）** | `wave12c-scripts/fix4-v10f-vendorbits.py`（MOSI 0xFF 读填充 + CS setup/hold + ATTN 进日志，boot-arg `touch_read_fill`） | — | 备而未用 |
| Boot logdump / 内核日志 | `logdump-v10c.bin` / `logdump-v10d.bin` / `logdump-v10e.bin` + `intel/m3-boot1/b19|b20|b21-kernel-log.txt` | 128 KiB ×3 | `8ee9d8df…` / `f5278ff3…` / `06fd11c9…`；日志 `ab51972b…` / `4ee92f1c…` / `e3aacdd9…` |

## 8. 下一步（v0.3 收官 → v0.4）

1. **真人点屏验证**：驱动已在 8 ms 轮询 ATTN 并收 touch report（report config 128 B 已收编），
   用户点屏预期出现 `s3910: finger N at x, y (of 12399 x 27719)` 行——下一轮会话或本轮日志尾验；
2. 若坐标/置信异常：`touch_flip` boot-arg 免重编可调；若报告断流，v10f 三件（0xFF 读填充、
   CS 时序、ATTN 日志）脚本已备好即刷；
3. 触摸 probe 达成后，v0.3 全绿 → 转入 v0.4 Darwin IPSW 存储施工（Wave 15 施工单已备）。
