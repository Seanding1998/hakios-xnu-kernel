# 阶段 37 · 2026-11-11 · v0.5 GPU 内核侧首亮：21 步全绿，3D 核接受命令并写内存

> 2026-11-11 · 阶段 37 GPU 首亮执行记录（衔接 wave36-handoff.md）
> 任务书：定位 v26 内核 adreno 驱动步 1 挂点 → 按概率序修复重验 → 验收行（驱动 probe + 固件加载 + GMU/ring 初始化 + 零 panic）。
> 红线执行：boot_a 只切槽绝不刷写（本轮 set_active a↔b 均为标志翻转）✓；每次刷写三门（graft sha 钉 / getvar product=taro / current-slot 核对，OKAY 断言）✓；NEED USER 协议（物理按键，每次窗前预告时刻）✓；600s 会话帽 + 服务窗纪律（取证窗前 loader 静默，守望器仅主机侧轮询）✓；一世代一修复（归因纪律）✓。
> 证据分级：[实证] = 文件/字节/行号/寄存器读值可复现；[实测] = 本阶段真机结果；[VENDOR] = `~/hakios/refs/kernel_oneplus_sm8475`（GPL，只作寄存器事实源）；[DTB] = `Mu-Silicium/Resources/DTBs/phk110.dts` 与手机活树 `/sys/firmware/fdt`（后者为一手真值，F14 pull-soc 配方拉取）。

---

## 0. 判定（先行）

1. **🏆 v0.5 GPU 首亮达成（六分支 A = 验收行全到手）**。v33 世代 22 步机器 18 步 done（步 10/11/12 按 gpu=1 设计跳过，zap 认证在步 19 完成）、**零 panic**、**`adreno: 21: the page reads 0x600dc0de: THE 3D CORE WRITES OUR MEMORY ON COMMAND`**（3D 核亲手写入魔法字）+ **`THE GPU STAYS ON for the system to draw with: the service HakiosGPU`**（keep=1 生效，GPU 留给系统）。验收行清单见 §5。
2. **W37 增量 = 五代五修复，全部机器实证**（对 wave35/36 记账查重后确认新发现）：
   ① **gcc cape 化**（v28）：驱动携带 sc7280("yupik") 偏移，本机 gcc = `qcom,cape-gcc`（[DTB] phk110.dts:785-787，reg 0x100000+**0x1f4200**）；其 vendor 驱动 = `gcc-waipio.c` 的 `gcc_cape_fixup`（f16 普查独立佐证 cape 机器装 gcc-waipio.ko）。GPU 偏移换表：PLL_VOTE 0x52000→0x62000、cfg_ahb 0x71004→0x81004、memnoc 0x7100c→0x81010、snoc_dvm 0x71018→0x81018、ddrss 0x71154→0x81154；映射 0x80000→0x1f4200（原尺寸连 0x81xxx 都罩不住）。
   ② **熔丝 cape 原生化**（v30）：手机活设备树 `/sys/firmware/fdt`（1,200,263 B）qfprom/speed_bin/efuse **零命中**——cape 不向 AP 暴露熔丝；vendor 自身路径同构（`adreno_read_speed_bin` nvmem 缺席即 return 0，chipid 由 DT 直带）。步 2 = 零访问 + speed_bin 0（wave36 [TODO-DEV] "cape qfprom cell" 以最强形式消账：根本没有 cell）。
   ③ **gpucc cape 化**（v29→v30 生效）：`qcom,cape-gpucc`（phk110.dts:838，reg 0x3d90000+**0xa000**）→ gpucc-waipio.c（cape fixup）+ debugcc-waipio.c + **GDSC/syscon 用手机自家 DTB 一手地址**（cx_gdsc 0x9108、gx_gdsc 0x905c、gx_sw_reset 0x9058、cx_hw_ctrl 0x953c、gx_domain 0x9504）；branches/RCG 用 waipio（ahb 0x911c、cx_gmu 0x913c、cxo 0x9144、gx_gmu 0x90bc、cxo_aon 0x9004、hub_aon 0x93e8、hub_cx_int 0x9148、gmu_rcgr 0x9318、hub_rcgr 0x93ec、smmu_vote 0x7000）；PLL1 0x0100→0x1000；debug 组 0x9564/0x9270/0x9274 + 选择值逐个重映射（gx_gfx3d→0x25 measure_only cx_gfx3d；0x0b 不变）。**CB 时钟 cape 不存在**（gpucc-waipio 全表无此 branch）——步 3 读保留（in-map 无害）、步 5 写摘除（v31，写未知寄存器 = 实危害）。
   ④ **zap 三段布局**（v32）：cape 的 a730_zap.mdt = 三段（0=头自身 148B、1=代码 b01 2236B、**2=hashes 3416B**），文件恰为"头+表+段2"（148+3416=3564=实际大小）；旧校验按 sc7280 两段式从段 1 读 hashes（2236）故拒收。修复 = 通用地找"p_filesz 使头+表+filesz==size"的段。修复后 TZ 三连（签名 0x42000201 / 内存 0x8b91a000 / 认证 0x42000205）全过：**TRUSTZONE HAS AUTHENTICATED AND STARTED THE ZAP SHADER**。
   ⑤ **步 20 address-mode 表摘除**（v33）：a6xx 十二寄存器 64 位寻址列表（mainline a6xx_gpu.c 同表）第六写（word 0xbe05 → 0x3d2f814）重置手机（v32 实证：该写打印后下一打印永未落地，手机提前回安卓）；vendor gen7_start（adreno_gen7.c:422）**一个都不写**（gen7 64 位原生）。同表其余成员（qsb_side 等）经 vendor 交叉核对为 gen7 合法（gen7_0_0_gbif_regs 含 QSB_SIDE 0x71620），保留。
3. **v31 生产步走已到步 19**（GMU fw 4.0.7 = vendor `GMU_VERSION(4,0,7)` 精确命中；3D 核 283 MHz = DTB initial-pwrlevel 精确命中；SQE 75924 B 装载；SMMU ctx 编程全录）——v33 补上 19-21。**步 5 频率计（cape debug 组）实测 ahb 150000020 Hz / 3D 核 282999740 Hz / 19.2 MHz 晶振**——频率计数器这条"vendor 是唯一来源"的路在 cape 上一次走通。
4. **cmdline 探针纪律**：v27 探针只加 `adreno_only=1`（**未加 adreno_fine**）——预算铁律（wave23：607 为组合后上限，loader 110 字符头在前、payload 段排最后、超长砍尾），497 字符 payload 预算内 491 才放得下；且 gpu=1 路径 pause_ms=0 时 adreno_fine 本为惰性参数。定位靠 adreno_only 强制 newest_step=K 的逐访问打印，两代探针（v27/v29）各一刀定案挂点。
5. **世代链（七刷七判，一世代一修复）**：v27 探针（挂 0x152000）→ v28 gcc（步 1 绿）→ v29 步走（挂步 2）→ v30 熔丝+gpucc（步 3 绿）→ v31 生产全走（至步 19 布局拒收）→ v32 zap（19 绿，20 死）→ v33（**全绿到 21 + STAYS ON**）。内核链 a39c931c → e3852a0f → c2ea0ca2 → 95fd7568 → a696adb0 → ee283c74 → **55a8d40f**；boot_b = v33 graft `6d5efeb5…`（payload cb447ade，verify 62/62 每代全绿）。

## 1. 挂点定位方法论（交接文档 §2.3-4 修正的验证）

- `adreno_only=K` 强制 newest_step=K → `get()/get8()` 在每次访问前打 `about to read <block> <reg> at <phys>`；挂死访问的下一行（`= value`）永不出 → **logdump 尾行即挂点寄存器**。v27 一刀定案步 1 挂在 gcc PLL_VOTE @0x152000（cape 真值 0x162000）。
- 例外：非 newest 步（v29 步 2 挂）只有 announce 行——挂点 = announce 之后第一条访问，需按步序推算（v29：0x7841e9）。
- loader 侧每 2 秒把日志尾写进 logdump 分区（独立于 USB，半启动残留枚举下照常工作）；挂死为无限期，探针行必落盘。**三代实测：会话末端从不出现干净可抓的 ABL d00d 窗**（半启动残留 0000:0002 → EDL 05c6:9008），可抓的 fastboot 态 = 用户按键创造的——守望器（主机侧 usbipd 3 秒轮询）+ 需人工配合窗口的预约时刻 = 标准流程，四轮零失误。

## 2. 世代明细（每代一个证据级修复）

| 代 | 内核 | graft | 判定 | 修复 |
|---|---|---|---|---|
| v27 探针 | a39c931c | d61d454a | 步 1 挂 @gcc 0x152000（零 panic，adreno_only=1 解析 ✓） | —（定位代） |
| v28 | e3852a0f | 3381b478 | **步 1 绿**：5 读全有值（pll votes 0xe0257f、cfg_ahb=1、memnoc=1、snoc=0x80000001、ddrss=0x300001）+ cmd_db magic OK + gfx/cx/mx 三资源 level 表全出 | gcc 偏移 cape 化（§0-2①） |
| v29 | c2ea0ca2 | 8ccf9a94 | 步 1 复绿 + 步 2 挂 @qfprom 0x7841e9 | 步走 cmdline（adreno=3） |
| v30 | 95fd7568 | a85e68d8 | **步 3 绿**（gpucc 全表读值在案） | 熔丝零访问 + gpucc cape 化 |
| v31 生产 | a696adb0 | aeeeae60 | 至步 19：**GMU fw LOADED(4.0.7)/RUNS/队列 UP/3D 核 283MHz 上电应答/SQE 装载全绿**，19 死于 zap 布局校验 | cb 写摘除 + cmdline 回 gpu=1 |
| v32 | ee283c74 | ace9533a | **步 19 绿（TZ 认证+启动 zap）**，步 20 死于 address-mode 第 6 写 | zap 三段布局 |
| **v33** | **55a8d40f** | **6d5efeb5** | **全绿至步 21 + THE GPU STAYS ON** | address-mode 表摘除 |

七代 logdump 全部落档 `wave37-scripts/logdump-v26-wave37-w37*.bin`（各 512 MB 尺寸门 PASS，sha 见 progress.log phase 3/5/9/11 与 §3）。

## 3. v33 验收行清单（判定证据，logdump f68e4e48955d4b3a）

```
adreno: 5: THE REGISTER BUS OF THE GPU BLOCK HAS ITS CLOCK, whatever its control register says
adreno: 5: measured: ahb, THE ONE IN QUESTION, runs at 149999580 Hz
adreno: 6: the GMU's counter counts at 19199001 Hz: the 19.2 MHz crystal: THE GPU BLOCK IS ALIVE
adreno: 14: THE GMU'S FIRMWARE IS LOADED; its versions, read back from the GMU: core 0x40000007, power 0x40000007, HFI 0x20010000
adreno: 15: THE GMU'S FIRMWARE RUNS
adreno: 16: THE GMU'S MESSAGE QUEUES ARE UP
adreno: 17: THE 3D CORE HAS POWER AND ANSWERS
adreno: 17: measured: the 3D core's clock runs at 282999740 Hz (283 MHz was asked for)
adreno: 19: TRUSTZONE HAS AUTHENTICATED AND STARTED THE ZAP SHADER
adreno: 20: THE 3D CORE TAKES COMMANDS
adreno: 21: the page reads 0x600dc0de: THE 3D CORE WRITES OUR MEMORY ON COMMAND
adreno: THE GPU STAYS ON for the system to draw with: the service HakiosGPU
```
步序：18 步 done（1-9、13-21），10/11/12 = gpu=1 设计跳过（mask 0x1c00），zap 认证由步 19 承担。零 panic 行。任务书验收行四要素（probe/固件加载/GMU-ring/零 panic）全中。

## 4. 已知 vs 增量记账（当时的工作安排纪律，对 wave35/36 查重）

**与 wave35/36 一致（只落地）**：GMU 窗 0x3d68000+0x37000、RSCC 0x3d50000、SMMU/GBIF 表、固件名三件、GMEM/HBB、fence 0x32/0x8a0 等（wave36 参数层已换，本轮零改动）。
**W37 新增量（wave35/36 零命中）**：①gcc-waipio.c 即 cape-gcc 绑定（wave36 grep 未中的原因）+ 全套 GPU 偏移差表（§0-2①）；②DTB gcc/gpucc reg 尺寸（0x1f4200/0xa000）为映射真值；③gpucc GDSC/syscon 以手机自家 DTB 节点为 cape 一手源（gpucc-waipio.c 无 gdsc 结构）；④活 fdt 熔丝零暴露定案；⑤CB 时钟不存在；⑥zap 三段布局（wave36 只到"b01=代码"语义，未及 mdt 文件布局校验）；⑦a6xx address-mode 表在 gen7 不存在；⑧会话末端半启动残留→EDL 形态三连记录（wave38 真机判定的墙分类账可引用；另有当时的工作安排转述的第三型墙印 `DWC_TRB_STS_SETUP_PENDING`，loader 相位主机 SETUP 探测所打，本轮未独立观测）。

## 5. 诚实边界与转入

1. **步 22（三色图上屏）不在 gpu=1 使命内**（last_step=21）——GPU 已 keep=1 留给系统，呈现端下一步 = Mesa 用户态（wave35 §5 施工单 #6：25.0.7 pin + FD725 身份已核）经 HakiosGPU 出首帧。
2. **SSH/系统回归未在本阶段复测**（keep=1 + system starting 已刷入真机；USB 对自愈 = wave38 真机判定波，其 graft 742bce63 待排期——注意其 payload 刻意带 v26 内核，与 v33 的 GPU 修复互斥，排期时当时的工作安排需决策合并基线）。
3. 观察项未动（各自待证据）：RBBM_GBIF_CLIENT_QOS_CNTL 值差（vendor 0x2120212 vs 驱动 3/0）、UCHE_CACHE_WAYS（vendor 0x800000 vs 驱动 4——但步 5-21 全绿说明现值可用）、UCHE_CMDQ_CONFIG/GRAS_NC_MODE_CNTL（vendor 有写、驱动无——步 20-21 已绿说明非必需或 GMU/CP 路径覆盖）、GMU 时钟频率是否恰 200 MHz（measure 只测了 ahb/3D 核/gxo；GMU 版本应答正常为旁证）。
4. raphael fork diff（coordinator 情报）未启用——步 4-21 未再卡，清单留档给后续性能/步 22 波。
5. v27-v33 全链构建/验像/刷写脚本 + 六份补丁器（apply-*-v28/29/30/31/32/33.py，精确锚断言式）+ 七份 verify（62/62 每代）在 `wave37-scripts/`；内核备份链 hakios.adreno.c.v27/v28/v29/v30/v31/v32-orig 在 WSL 树。

## 6. 判定表（六分支式）

| 分支 | 判定 |
|---|---|
| **A 验收行全到手** | **✓——本阶段实况（§3 清单逐行在案）** |
| B 进入步进机器但早期步挂起 | ✗（wave36 的 B 已由五代修复闭环） |
| C 驱动未进入 | ✗ |
| D GMU 行到手、CP 层失败 | ✗（CP 层绿：20 TAKES COMMANDS / 21 WRITES OUR MEMORY） |
| E 镜像/链路问题 | ✗ |
| F 设备/取证层失败 | ✗（七代 logdump 全取证；半启动状态未阻中断） |

**v0.5 GPU 首亮判定：达成。** 设备留驻：安卓 slot a 静置，boot_b = v33（graft 6d5efeb5，GPU-capable，随时 set_active b 复验）。
