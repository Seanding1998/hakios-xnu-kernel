# 阶段 36 · 2026-11-11 · GPU 内核驱动首次上机：步进机器启动，第 1 步挂起取证

> 2026-11-11 · 阶段 36 GPU 首亮执行记录
> 任务书：v0.5 GPU 首亮——固件实拉 → 应用 阶段 35 补丁骨架 → 构建 v25（Adreno 730 驱动进内核）→ 刷写 → 真机验证拿 GPU 验收行。
> 红线执行：boot_b 刷写在授权内，**每次刷写前三门（taro/slot/sha）全过** ✓；boot_a 零触碰 ✓；usbipd 抢占只做 detach、零 wsl --shutdown ✓；构建树本阶段独占 ✓。
> 证据分级沿用：[实证] = 文件/字节/行号可复现；[实测] = 本阶段真机结果；[VENDOR] = PHK110 自己的 vendor gen7 kgsl 源（GPL，阶段 15 在盘，只作参照）；[PONG] = pong/zizhan 自报；[TODO-DEV] = 待后续波。
> 记账纪律：每个"发现"先对 wave35 文档/骨架 grep 查重——增量显式标注，已知项只写"与 阶段 35 一致"。

---

## 0. 判定（先行）

1. **GPU 首亮判定 = [见 §4 现场判定行]**（console 证据 + SSH 回归）。
2. **SSH 回归 PASS（已落袋）**：v25 世代 09:41:05 连续敲击第 1 发即 HIT（1.9 s，`WAVE21-SSH-OK`，verdict26-w36c.txt）——内核横幅 `Darwin Kernel Version 22.5.0: Wed Nov 11 08:57:07 AM CST 2026` 的时间戳就是本阶段 v25 内核构建时刻（08:57 出的 hakios-kernel），链路身份无歧义：**GPU 增量没有破坏 v24 的会话链**。
3. **固件三件套实拉落库（验收 ✓）**：ColorOS 真名与 SM8475 双源清单**逐字一致**且**多三件**——`a730_sqe.fw` / `gmu_gen70000.bin` / `a730_zap.{mdt,b00,b01,b02,elf,mbn}` 8 件全部 sha256 在档（§1）；wave35 的 [TODO-DEV]"ColorOS 真名"消账。
4. **zap 段语义升级为一手实证**：本阶段实拉的 `a730_zap.mdt` ELF 段表显示 seg1（b01）= PT_LOAD rwx 0x8bc B（代码段），seg0（b00, 0x94 B）/ seg2（b02, 0xd58 B）= PT_NULL 元数据——驱动改为装载 **b01**（wave35 只有 [PONG] 转述 + TODO-DEV，现为本机文件取证）；b01 文件大小 2236 B 与 ELF filesz 互证。
5. **W36 增量（对 wave35 查重后确认为新发现）**：GMU 寄存器块**相对窗偏移统一 +0x800 词**（20+ vendor 锚点全数吻合）；步 16 RSCC/PDC **程序值与 a6xx 逐字相同**（唯一字节差 = hidden_tcs_cmd2_data 0x80000021→0x80000000）；HFI 表头字段值 num_q=num_active=17（vendor init_queues）而队列头几何 12 dword 驱动**本来就对**；dcvs 表几何与 a6xx 相同、gpu.acd 字段被 gen7 重读为 CX 投票；cape 13 档 pwrlevels 从我们自己的 DTB 全表入驱动（§2.2）。
6. **与 阶段 35 一致（一行带过）**：GMU 窗 0x3d68000+0x37000、RSCC 0x3d50000+0x10000、SMMU 窗加宽、PDC 使能词、fence 0x32/0x8a0、GENERAL_10 chipid、GENERAL_8 日志、TCM_RET_CNTL 经 cx_misc(0x39)、CM3_CFG 0x4052、固件名、PAS13、GMEM 2 MiB、HBB 16。
7. **v25 镜像链**：payload `e1ef6e94` / graft `802f1aeb`（verify **61/61**）/ 内核 `abecd557`→`a39c931c`（wave 26 以来首次内核字节变化）/ ramdisk `61323255`→`156b5be1`（fw/ 平铺进 root.apfs）/ cmdline 473→479 B（+` gpu=1`）；其余条目（loader.efi 0ade78b5 / resident / kernel.ver / usb）与 v24 逐字节相同。
8. **固件通道定案**：走 root.apfs `/fw/`（树内自有通道：hakios.image.c 读 "fw/NAME"，build.sh 从 `fw-gpu/` 拷入 `--plain fw` 平铺）——**不加 payload 新条目**，PAYLOAD_BASE 布局与 loader 零改动。理由：树内惯例即此（wave35 §3 迁移路径本就写明 userland/build.sh GPU=1 开关），且 payload 结构变化会连带 loader 风险，与首亮目标无关。

---

## 1. 固件实拉（wave35 脚本首跑真拉）

`wave35-scripts/pull-firmware-root.sh` 真跑三处现场修复（脚本已改，注释在位）：

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | 手机侧 `/system/bin/sh: no closing quote` | 嵌套 `su -c 'sh -c "..."'` 引号层级在手机 shell 炸 | 改平铺单行，主机侧只展开常量路径 |
| 2 | `adb pull` 报 `C:/Program Files/Git/data/...` | Git Bash MSYS 路径改写（adb 是原生 Windows 程序） | `MSYS_NO_PATHCONV=1` |
| 3 | 本地落点同病 `/c/Users/...` adb 不认 | 同上（禁转换后本地参数也裸奔） | 先 `cd $OUT` 再用相对路径拉 |

**清点与 sha256（fw-gpu，验收基线）**：

```
a730_sqe.fw      4f8b288f340ff5b4881bed8dfea90bb4a1b967556ca2df6d07f4ed4e4a28d071
gmu_gen70000.bin b2d3f0e2a98fd6259ab9ffef16df63265542e6cc9a970d53d476e823d432042a
a730_zap.mdt     9df98f792bba155ff78aac3590c7c242f7eb49b65dae31e61eb818df2deb7426
a730_zap.b00     72686cdeedc16a47b320a91121763f8522fbd5cad26d0239ca12332f9b9fd661
a730_zap.b01     1fc98f97cf354b9704b20d0848f7b2739638539a57d88ecf5cc71ca1c5c4e6b9
a730_zap.b02     2061223025a29915b99ed6c2f17bcc268ee7247af53bf572cb797e43eb8e7652
a730_zap.elf     e84f060fed76c31347c939ef6f2015ca248c65ca8e325c6b4f01a154285daa22
a730_zap.mbn     905b1311dc9cd343b533ebd78cbfaf1bc7f50d34dc7dd27a03b2194092b26635
```

- audio：`adsp.mdt` + b00..b23/b25 共 26 件（TZ PAS image 1，v0.6 用）。
- WiFi（如实记档，**非本阶段验收项**）：`/vendor/firmware/wlan/qca_cld/{kiwi,qca6490,qca6750}` 在手机上就是**空目录**（qca6750/ 下仅一个 qca6490 条目，疑符号链接未随 cp/pull 落地）；真实 MAC 候选找到 = **`/vendor/firmware_mnt/wlan_mac.bin`**（wave35 TODO-DEV 的 MAC 路径消账）+ `WCNSS_qcom_cfg.ini` 同层。WCN6750 固件真身在 v0.6 波另查（firmware_mnt/image 无 wlan 命中）。

## 2. gen7 参数层（骨架 → 落地）

### 2.1 施工

`wave36-scripts/apply-adreno-v25.py`：44 处精确锚替换（每处断言恰一次命中；任何残留 a660/旧基址名 = 拒绝写出）。留档：
- `wave36-scripts/patches/wave36-adreno-a730-parameter-layer.diff`（全量 unified diff）
- `~/hakios/kernel/drivers/gpu/hakios.adreno.c.v24-orig`（原文件备份）
- 构建期一处修复：步 2 熔丝打印引用了后文才定义的 `GPU_CHIP_ID`（前向引用编译错）→ 打印改字面量 `0x7030002`。

### 2.2 已知 vs 增量记账（工作纪律）

**已知（wave35 文档/骨架已有，本阶段只是落地）**：地址窗（gmu/rscc/smmu/pdc）、fence 范围 0x32/0x8a0、chipid 投递寄存器 GENERAL_10、日志寄存器 GENERAL_8、TCM 保持走 CX_MISC、固件名三件、PAS13、GMEM 2 MiB、HBB 16、CP_ME_INIT DMS bit11、UBWC 6 暂留。

**增量（wave35 零命中，grep 核实）**：

1. **统一 +0x800 词移**：GMU 块基址从 0x3d6a000 移到 0x3d68000（窗起点前移 0x2000 字节 = 0x800 词）后，vendor `gen7_reg.h` 的每个字地址 − 0x1a000（GPU 块前段）= a6xx 相对偏移 **+0x800**。20+ 锚点验证：CM3 0x50xx→0x58xx、ALWAYS_ON 0x5088→0x5888、PWR_COL 0x50c0→0x58c0、RPMH_POWER_STATE 0x50ec→0x58ec、HFI 0x518x→0x598x、GENERAL 0x51cc→0x59cc、ICACHE 0x4c00→0x5400、AO/RSCC-ctrl/FENCE 0x93xx→0x9bxx。未列入 vendor 头的寄存器按此规律推导（运行期步 6/14/15 的读回即真伪检验）。DTCM 0x1c00→0x2400（版本词 0x33f8）、ITCM 0x0c00→0x1400。
2. **步 16 程序值层与 a6xx 逐字相同**（wave35 无此值）：`gen7_load_rsc_ucode` 的五个程序字 `0xeaaae5a0, 0xe1a1ebab, 0xa2e0a581, 0xecac82e2, 0x0020edad`、PDC_SEQ_START/MATCH 0x4520/0x4510/0x4514、PDC_SLAVE_ID=1 全部 = 驱动现有 a6xx 常数；**唯一字节差** hidden_tcs_cmd2_data `0x80000021`（a650+）→ gen7 `0x80000000` [VENDOR]。步 16 = 一处值改 + rscc 基址（0002）。
3. **HFI 表头字段值**：vendor init_queues 写 `num_q = num_active_q = 17`（a6xx 驱动写 3/3）、version=0；队列头 12 dword/17 槽/表 210 dwords/队列自 848 字节起——**驱动的结构定义本来就是 gen7 形状**（12 dword 头），零结构改动，只改字段值。
4. **dcvs 表**：几何与 a6xx 相同（3 头 + 16×3 + 4×2 dwords），但 gpu 条目第二 word 被 gen7 固件重读为 **CX 投票**（`to_cx_hlvl`：cx.lvl ARC 表中首个 ≥ 该档 cx-floor 的序号）；GMU 档 2→3（{0, 19200, 200000} kHz，cx 投票 {0, 0x40, 0xc0}）。
5. **cape 速度表全量**：13 档从我们自己的 DTB（phk110.dts:20081-20230）入表——900/860/810/760/710/645/580/510/440/370/325/283/220 MHz，`qcom,level`/`qcom,cx-level` 配对（0x1a0..0x30）；默认请求档 = DTB `qcom,initial-pwrlevel` 0x0b（283 MHz），表内 +1 偏移 = 索引 12。
6. **zap 语义一手化**（见 §0-4）。

### 2.3 config 与固件落位

- `devices/phk110/configs/phk110.config` + 树根 `.config`：`# CONFIG_HAKIOS_ADRENO is not set` → `CONFIG_HAKIOS_ADRENO=y`（树内既有的开关名，phk110 片段继承自 common_defconfig 的默认开）。
- 固件 → `~/hakios/kernel/fw-gpu/`（8 件全放；build.sh 只按 `fw-gpu/*` 平铺拷入 `root/fw/`）。

## 3. v25 构建（内核 wave 26 以来首次字节变化）

| 件 | v24 | v25 | 说明 |
|---|---|---|---|
| kernel | abecd557 | **a39c931c** | gen7 参数层 + CONFIG_HAKIOS_ADRENO=y（二进制含 a730 名串/genera_10/tcm_ret_cntl 行验证） |
| ramdisk | 61323255 | **156b5be1** | root.apfs 重编（v13 配方 FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh），fw/ 三件字节级验证在像内；wave34 init guard 随同一份 userland 源在像（guard 串非平文属 APFS 压缩存储常态，v24 同profile） |
| cmdline | 473 B | **479 B** | +` gpu=1`（预算 581/607） |
| loader.efi | 0ade78b5 | 同（逐字节） | PAYLOAD_BASE 双层钉死未动 |
| resident / kernel.ver / usb | — | 同（逐字节） | 与 v23/v24 链一致 |

- payload v25 = `e1ef6e94`（23,570,872 B）；graft v25 = `802f1aeb`（FD 8924cb67 + shim 108ce972 未动，与 wave 21 以来所有 graft 同配方）。
- **verify-udon-hakios-v25.py：ALL 61 CHECKS PASSED**（61 条 PASS 行 0 FAIL；make-verify-v25.py 从 v24 verify 生成，delta/carry 结构翻转 + gen7 标记断言：内核须含 `gmu_gen70000.bin/a730_sqe.fw/a730_zap.mdt/a730_zap.b01/"an Adreno 730v3 (chip id 0x7030002)"/tcm_ret_cntl/general_10`，ramdisk 须含 fw 平铺标记）。
- 教训一行：`make kernel 2>&1 | tail` 吞退出码——第一次构建实际失败（hakios.adreno.o 前向引用）而被当成功；改捕获 `MAKE_RC=$?`。

## 4. 真机验证（两世代）

**世代 1（09:17）**：`flash-bootb-v36.sh` 三门全过（graft sha 802f1aeb 钉 / getvar product=taro / current-slot b）→ `fastboot flash boot_b` OKAY×2（5.662 s）→ set_active b + reboot → FLASH CONFIRMED。**随后 loader gadget 破损枚举**（2-2 = `0000:0002 描述符请求失败`，wave31 半启动残留形态；usbipd unbind/bind 需管理员被拒）。会话窗口（SSH 敲击）因此错过。处理 = 带内等待 + 报告；**用户硬杀重启**（现场令：手机已在 fastboot）。

**世代 2（09:33:45，现场令通道）**：fastboot 三门全过（serial 3c268ac3 / taro / slot b）→ 免刷直接 `fastboot reboot`（boot_b 已是 v25，硬杀不擦分区）→ xnuloader 干净枚举 → **SSH HIT 09:41:05**（1.9 s，第 1 发；verdict26-w36c.txt 绑定：`product b'xnuloader'` + `phase: the kernel session is live -- tunneling` + `netmode on -> OKAY`；内核横幅时间戳 = v25 构建时刻 08:57:07）。

**世代 1 教训（入账）**：会话相位前后 usbipd 的持久绑定（b67ab332 xnuloader 等）在设备重枚举时有竞态；本阶段未用管理员通道清理，靠世代切换自愈。后续波如再现半启动状态：管理员 `usbipd unbind/bind` 或用户重插 = 最快通道。

**GPU 验收行（console 证据）**：[见 §6 —— logdump 提取结果]

## 5. 用户侧旁证（（现场旁证，入档））

v24 世代用户在 iOS 储存页面实测看到 **~12.5 GB**（= ufs_darwin_data 数据卷标称容量，12,501 MB carve）——init guard 生效的**肉眼级独立验证**：储存页读到的是真 hfs 卷而非 ramfs 遮蔽层（遮蔽时代该页不可能显示稳定卷容量）。13 GB = 设计内；用户预期的大容量接入（v0.8 darwin 20 GiB/扩容）已在 PLAN 排期，非本阶段事项。

## 6. 现场判定行（logdump 提取）

**v26 gen1（gpu=1 首次进内核）的 adreno 行全集**（`wave36-scripts/logdump-v25-wave36-v26gen1.bin`，512 MB 尺寸门 PASS，sha256 cc0420d1…；安卓态 dd `/dev/block/by-name/logdump`）：

```
[   49.296270]: adreno: steps up to 21, without those in mask 0x1c00; step 21 is the new one and waits 0 ms after each announcement
[   49.296275]: adreno: step 1: read the GPU's clocks in the global clock controller (registers the touch screen driver uses too)
```

解读（证据分级 [实测]）：`gpu=1` 自启路径生效——boot-arg 解析 ✓、`start_by_itself()` 固件预检 **通过**（缺 fw 会打 "THE GPU IS NOT STARTED: the small image has no fw/…"，无此行 = a730 三件套在 root.apfs/fw/ 被找到）✓、步进机器进入 ✓；**步 1 内部挂起**（announce 后零行直到世代结束，每代同样挂），零 panic。**更正**：`get()` 只在 `step == newest_step`（=21）时逐访问打印，步 1 读本来就静默——挂点定位（5 条 gcc 读 vs cmd_db 读）必须走 `adreno_only=1 adreno_fine=1` 逐步协议 = 下一阶段首探针；首要嫌疑 = sc7280 的 gcc gpu 偏移在 kodiak gcc 里的差异（对照 vendor `gcc-sm8475.c`，宏名不同需人读）。

## 7. 判定表（六分支式）

| 分支 | 判定 |
|---|---|
| A 验收行全到手 | ✗ |
| **B 进入步进机器但早期步挂起（本阶段实况）** | **✓——probe 行到手（steps up to 21 + 固件预检过），步 1 内部挂起，零 panic** |
| C 驱动未进入（boot-arg/固件预检失败） | ✗（被 B 排除） |
| D GMU 行到手、CP 层失败 | ✗（未及） |
| E 镜像/链路问题（cmdline/固件缺失） | ✗（v26 已修 cmdline NUL bug，固件在像） |
| F 设备/取证层失败 | ✗（logdump 主证据路径打通） |

**v0.5 GPU 首亮判定：未达成（B 分支）。** 已落袋的里程碑：cmdline NUL bug 定位根因与修复、gpu=1 递达内核、a730 固件预检通过、SSH 回归 HIT（v25 gen2）、步 1 挂起现场取证。下一阶段单一焦点 = 步 1 挂点定位（详见 `docs/waves/wave36-handoff.md` §3.1 命令级步骤）。

## 8. 后续工作（下一阶段）

- Mesa 用户态（25.0.7 + FD725 出 libOSMesa → eagl 首帧）= wave35 §5 施工单 #6，本阶段未动（判定优先级：验收行 > Mesa）。
- 步 17+ 的 HFI 表如果 §6 显示被 GMU 拒收：按 GMU 错误串（hfi_send 打印 `THE GMU REPORTS AN ERROR: ...`）逐项对 vendor gen7_rpmh.c 修表——dcvs cx 投票编码与 GMU 频率对是首要嫌疑。
- UBWC_SWIZZLE=6 暂留 [TODO-DEV]：dt ubwc-mode 0x04，真值待 Mesa 用户态波 probe。
- cape QFPROM 速度 bin 格 [TODO-DEV]：步 2 两路读已保留、不门控。
- WiFi 真身在 v0.6 查（MAC 路径已定位 /vendor/firmware_mnt/wlan_mac.bin）。
- wave35-scripts/pull-firmware-root.sh 的三处修复随本阶段提交（脚本所有权 wave35，修复记录在 §1）。

## 9. 诚实边界

1. 步 18-21（CP/命令处理器层）的 a6xx 寄存器级 hw_init 表未做 a730 重推导（wave35 0005 议题 + zizhan submit/ 层）——若 §6 显示步 17 后失败，属预期内的下一阶段工作量，不构成本阶段判定失败。
2. GMU 未列入 vendor 头的寄存器偏移按 +0x800 规律推导——运行期读回是唯一裁决；若 §6 显示步 6/14/15 某步失败，优先怀疑推导寄存器。
3. 世代 1 的 SSH 敲击窗口因 USB 半启动状态错过，SSH 回归证据来自世代 2（同一镜像、同一 payload sha）。
4. timed-ssh-v26 的世代边界模式在本阶段卡死（libusb 层，T0 行未出）——continuous 模式好用；工具病灶留给后续波（不影响本阶段判定）。
