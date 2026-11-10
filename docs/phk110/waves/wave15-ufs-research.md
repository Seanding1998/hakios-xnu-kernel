# 阶段 15 · 2026-11-03 · 存储路线研究：UFS 驱动的实施级设计

> 2026-11-03 · 执行记录产出 · 输入 = upstream 三仓（只读克隆）+ 本机 live FDT + fork 工作树（只读）+ GPL 内核/DT（新 shallow clone）
> 结论先行：**"难点"在 upstream 的架构里已经填平了 90%** ——fork 里躺着一整套与 upstream 字节相同、实机验证过的存储栈（内核驱动 + loader 服务 + 工具链），差的只是 1 个 config 开关、4 个 boot-args、和一块要 carve 出来的 `darwin` 分区。预计内核/loader **零行代码改动**。

---

## 0. 执行摘要

| 问题（consulting 判定的难点） | upstream/fork 的实际答案 | 状态 |
|---|---|---|
| UFS 控制器 init（链路启动/UIC/PHY/时钟/电源） | **vendor UFSDxe 在 UEFI 里做，内核/loader 永不 init**。fork 的 udon Binaries 已含 UFSDxe 且已刷入真机工作 | ✅ 已在跑（logdump 分区读写 Boot #8–#17 全成功 = UEFI UFS 写路径实证） |
| SMMU/DMA | **不碰**。DMA 映射是 UEFI 建的、内核沿用；内核 native 路径直填物理地址；本机（udon）固件甚至把 UFS IOMMU fault 标为 non-fatal（官方 DT） | ✅ 风险大幅降级 |
| write ordering / flush / FUA | **单请求 mailbox 串行**（一次一个、无乱序）+ loader 每写 flush+读回（慢路）或 journal flush 点（fast 路）；无 FUA 概念 | ✅ 机制现成 |
| HFS+ /var | 内核内建 hfs-627.100.6 + `var_hfs=DEV` 挂载（init.c:825-860）+ 12G 模板（阶段 14） | ✅ 全内建 |
| 真正缺的东西 | ①`CONFIG_HAKIOS_UFS` 在 phk110.config 被关（:38）②`darwin` 分区不存在（P0 carve，需单独确认）③cmdline 未带 ufs args ④darwin-write 工具的 redwood GPT 常量需换 PHK110 | 📋 施工单 §4 |

**S0–S8 每步 upstream 都是实机走过的**（CHANGELOG.md:35-39 + docs/devices/redwood.md:24），fork 侧文件与 upstream **逐字节相同**（diff 实测全 0，见 §3.1）。

---

## 1. upstream 存储架构考古（最重要）

### 1.1 三层接力总览

```
[UEFI]  vendor UFSDxe（闭源 DXE）= 唯一 init 者：控制器+PHY+时钟+RPMh 电源+链路+SCSI 探测，UEFI 永不退出
   │  EFI_BLOCK_IO / ReadBlocks-WriteBlocks
[Loader] xnuloader/loader.c 常驻 core 0：ufs=2 → 发布 mailbox 页（loader_block）+ 可选 hc_area（native 交接）
   │  共享内存 mailbox（ufs_shared_pa=）+ 原子 request/answer 对
[Kernel] hakios.ufs.c  = 块/字符设备层（每 GPT 分区一个 devfs 节点）+ 唯一写通道 + native 读写切换
         hakios.ufshc.c = native 只读直驱（换 transfer list 进控制器，白名单只放读命令）
```

**没有 IOKit 块设备栈**。PLAN.md v0.4 段写的"IOBlockStorageDevice → IOBlockStorageDriver → IOMedia → GPT scheme"是咨询语言；upstream 实际用的是 BSD `bdevsw/cdevsw` + `devfs_make_node` + loader 侧 GPT 解析（hakios.ufs.c:1082-1107, :1742-1757）。**fork 不需要、也不应该去搭 IOKit 块栈**——施工单按事实架构写。

### 1.2 UEFI 层：谁 init 了控制器

证据链（redwood 设备仓 `upstream/hakios-sm7325/`）：

| 证据 | 文件:行 | 内容 |
|---|---|---|
| UFSDxe 在 DXE 列表 | `uefi/files/Platforms/Xiaomi/redwoodPkg/Include/DXE.inc:50` | `INF Binaries/redwood/QcomPkg/Drivers/UFSDxe/UFSDxe.inf` |
| DALSYSDxe UFS 缓存一致性 patch | `uefi/files/Binaries/redwood/README.md`（"DALSYSDxe…Enabled Cache Coherence for UFS"，Gustave Monce） | Mu-Silicium 内存布局下 vendor DXE 需要 patch 的先例 |
| 配套依赖全家桶 | DXE.inc:27-31, 46-57 | HALIOMMUDxe / ClockDxe / RpmhDxe / CmdDbDxe / PwrUtilsDxe / NpaDxe（UFS 的时钟与电压投票全在 UEFI） |

**内核视角的合同**（hakios.ufshc.c 头注释 :1-49，逐字）："Qualcomm's UFSDxe reads synchronously on core 0, and its transfer request list has room for one request only… **Nothing else of the controller is changed: no reset, no link startup, no UIC command, no interrupt enable, aggregation, clock or power setting**; the task management list is not touched; IS and UTRLCNR are only read."

### 1.3 Loader 层（fork 已含，字节同 upstream）

`~/hakios/kernel/xnuloader/loader.c`（与 upstream diff = 仅 PHK110 平台补丁，存储段 0 diff）：

| 机制 | 位置 | 说明 |
|---|---|---|
| mailbox 页 `struct loader_block` | loader.c:1619-1677 | magic "RDWBLOCK" v3；parts 表 + ask/answer（128B 对齐）+ buffer_pa + native 交接区 + take_back/list_in 门铃 |
| `block_poll` | loader.c:2190（run loop 调用 :2477/:2487） | kernel 运行期间 core 0 服务块请求；写 = WriteBlocks 后 flush + 读回比对才置 answered |
| `hc_area` 提供 native 列表内存 | loader.c:1765, :2072-2083 | `block_shared.native.{hc_pa,area_pa,ucd_offset,ucd_size,slots,uefi_utrlba}` |
| `hc_take_back` | loader.c:1815, :1904 | 每次从 run 返回先收回控制器（换回 UEFI 的列表），防内核悬死 |
| darwin 三重验证 | loader.c:1938（`block_is_darwin`） | name/type GUID/unique GUID/unit/大小/4096 块全查 |
| HC_PA 常量 | loader.c:1746 | `0x1d84000ULL` —— **与本机 live FDT ufshc@1d84000 完全一致（taro=lahaina 同布局），零改动** |

### 1.4 内核层逐文件清单（含可复用度评级）

评级规则：A = fork 已有且 upstream 实机验证，直接用；B = fork 已有但需 PHK110 化常量；C = 仅参考不移植。

| 文件 | 行数 | 角色 | 评级 | 关键行 |
|---|---|---|---|---|
| `drivers/storage/hakios.ufs.c` | 1891 | mailbox 块/字符设备、读写分发、native 切换与回退、数据卷、var 握手 | **A**（fork 与 upstream diff=0） | mailbox 请求 :320-423；读写路径选择 :560-591；写（唯一写通道）:601-663；DKIOCSYNCHRONIZECACHE→flush :826-828, :705-720；native 对拍 :1490-1596；init :1710-1891 |
| `drivers/storage/hakios.ufshc.c` | 1351 | native 只读直驱：列表交换、白名单、doorbell 轮询、quiesce | **A** | 白名单 :252-311（只放 READ(10/16)/TUR/INQUIRY/RC(10/16)/REQ SENSE）；白名单自检 :367-456；slot 放置+读回校验 :477-517；doorbell 门禁 :521-538；poller :598-629；switch in/out :967-1092；probe（只读核状态）:1149-1308；quiesce :1316-1351 |
| `drivers/storage/hakios.ufshc.h` | 32 | loader 交接结构 | **A** | :11-20 `struct ufshc_loader` |
| `drivers/storage/conf` | 24 | 驱动装配 | **A** | :14-19 `driver UFS` → `bsd/dev/hakios.ufs.c`+`ufshc.c` |
| `userland/src/init.c` | — | var_hfs 挂载 + var.skel 骨架 | **A**（fork 与 upstream diff=0） | mount_data_volume :825-860（mount :855；失败回落 :856-857；成功 :859） |
| `userland/src/var_store.c` | — | packed store 打包/写卷（HFS+ 未挂载时的回退） | **A** | DEVICE="/dev/rufs_darwin" :54；var_busy/var_save 握手 :171, :1278-1307 |
| `xnuloader/loader.c`（存储段） | — | mailbox + native 交接 | **A** | 见 §1.3 |
| `tools/userdata-carve.py` | — | GPT 手术：userdata 尾部切 darwin | **B**（redwood 常量） | 全文；f2fs 缩 + 双表 CRC |
| `tools/darwin-write.py` | — | adb root 写镜像入 darwin（严格身份校验） | **B** | :29-34 常量（redwood: PARTN=34, FIRST/LBA 25374720..30617594, sda34） |
| `tools/mkdatavol.py` | — | darwin 全盘 sparse 镜像，只写 HFS+ 卷块，其余 DONT_CARE | **A**（常量与内核 UFS_WRITE_FIRST 对齐） | :27-29 DATA_FIRST=2042368 |
| `qemu/run-hfs-test.sh` | 30 行 | HFS+ 全链 QEMU 验证（hfs_test.c 当 init，两轮持久） | **B**（fork 可跑，供 S6 前自洽验证） | :13 mkfs.hfsplus -s -J；:22 grep hfs_test/^hfs:/^jnl: |
| UniXNU-udon `integration/NativeUfs.patch`（对 core 04b748e6） | ~110 行 diff（base ≈2000 行） | IOKit C++ 全量自-init UFS（UIC/NOP/队列/SMMU bypass/发布 window） | **C**（仅后备证据） | smmuBypassStream 直返 "firmware leaves the SMMU outside the kernel; skip the takeover"（patch L281-287）；hostBringUp 全 bring-up；**价值 = 证明本机同款 udon 内核级自 init 可行**（UFSDxe 路线死掉时的存在性证明） |

### 1.5 upstream 的 S0–S8 实机答案（对照我们分步）

| 我们的步 | upstream 实现位置 | 写序/安全设计 |
|---|---|---|
| S0 UFS init | UFSDxe（UEFI 内）；内核只读探状态 ufshc.c:1149-1250 | 内核永不做 reset/UIC/时钟 |
| S1 READ CAPACITY | loader ReadBlocks；内核 native 只到 READ(10) | — |
| S2 GPT | loader.c:1347/1938 解析+验证 | 160 分区上限（BLOCK_MAX_PARTS=160, ufs.c:73） |
| S3 读写回读 | 读 = mailbox 或 native+对拍（ufs.c:1406-1463 逐字节）；写 = loader 代写**每写 flush+读回**（ufs.c:389-396 "the loader has flushed, read the blocks back and found them the same"） | 写边界三重防线：内核 UFS_WRITE_FIRST 上限（ufs.c:90, :615-620）+ loader 同款（loader.c:1938）+ 写前插槽内容回读校验（ufshc.c:507-515） |
| S4 flush/FUA | 无 FUA：单请求串行 mailbox；fast 路径（BLOCK_CAN_FAST）只串行写，HFS journal 问 flush（DKIOCSYNCHRONIZECACHE）时 BLOCK_OP_FLUSH（ufs.c:699-720） | CHANGELOG:37 "a flush and a read back after every write made the system crawl" → 改 fast 路径的原因 |
| S5 设备发布 | devfs：`/dev/ufs_<name>`+`/dev/rufs_<name>`（ufs.c:1742-1757）+ `/dev/ufs_darwin_data`（:1805-1810） | **非 IOMedia** |
| S6 HFS+ mount | init.c:825-860（mount :855，成功行 :859） | 失败回落内存盘（不死机） |
| S7 /var | init.c empty_tree + var.skel | var_kept=1 语义 |
| S8 重启持久 | hakios_var_save_on_return（ufs.c:1117-1139）→ var saver（var_store.c）→ VAR_SAVE_DONE → loader 收回 → logdump | 20s 上限（var_save_ms）；panic 不走此路（store 保持旧档，var_store.c 头注释 :193-206） |

### 1.6 SMMU/DMA 策略（consulting 难点的裁决落地）

**upstream 选了"第三条路：不碰"**，且有两层独立证据：

1. **mailbox 模式（主路线）**：内核只经共享 buffer 与 UFSDxe 交换数据；DMA 是 UFSDxe 的事，它的 SMMU 映射 UEFI 建好、ExitBootServices 不拆（UsbConfigDxe patch 先例说明 Silicium 系对"UEFI 资源留给 OS"已有成熟做法；UFS 无人动它）。内核侧 buffer 用 `ml_io_map_unmappable`/cacheable 映射 + FlushPoC_DcacheRegion 手工一致性（ufs.c:340-341, :405；ufshc.c:793-794, :828）——**一致性靠 cache 管理，不靠 SMMU 操作**。
2. **native 模式**：PRDT 直填物理地址（ufshc.c:493-496 `s->data_pa`），命令/列表全在 loader 内存（kvtophys），**全程零 SMMU 代码**。能 work 说明该流的 SMMU 映射在 UEFI 之后仍然有效（或直通）。
3. **本机官方佐证**：udon overlay 把 UFS 的 IOMMU fault 设为**非致命**——`refs/modules_dt_sm8475/.../oplace/udon-22803-cape-overlay.dts:66-68` `&ufshc_mem{ qcom,iommu-faults = "non-fatal"; };`（vendor 自己都不怕 UFS IOMMU fault）。GPL arm-smmu.c:2254 解析该属性。
4. **UniXNU-udon 佐证**：同机同 UFS 流，内核级驱动直接跳过 SMMU takeover（§1.4 C 项）。

→ **S 系列施工不需要任何 SMMU/DT/IOMMU 工作**。loader DT 无需加 UFS 节点（loader 只消费 EFI_BLOCK_IO protocol，不经 DT；kernel DT 树只有 GIC/timer/console）。

---

## 2. 本机硬件盘点（live FDT + GPL 代际确认）

来源：`intel/live-fdt.dtb`（4470 节点，wave15-scripts/fdt_ufs_nodes.py 提取）+ `refs/modules_dt_sm8475`（cape.dtsi，GPL DT）。

### 2.1 ufshc@1d84000（/soc/ufshc@1d84000）

| 参数 | 值 | FDT 证据 | GPL 对应（cape.dtsi:1906-1954） |
|---|---|---|---|
| compatible | `qcom,ufshc` | live FDT | 同 |
| reg[0] ufs_mem | **0x1d84000 + 0x3000** | 同上 | = loader.c:1746 HC_PA / ufshc.c:76 UFSHC_PHYS，**零改动** |
| reg[1] ufs_ice | 0x1d88000 + 0x8000 | 同上 | inline crypto 引擎（我们不用；UFSDxe 内部可用） |
| reg[2] ufs_ice_hwkm | 0x1d90000 + 0x9000 | 同上 | HW Key Manager（不用） |
| interrupts | GIC_SPI 265 (0x109) LEVEL_HIGH | live FDT `interrupts: 0x0 0x109 0x4` | cape.dtsi:1912；**内核 mailbox/native 均轮询不用中断**（ufshc.c 头注释） |
| lanes-per-direction | 2 | 同 | cape.dtsi:1919 |
| dev-ref-clk-freq | 0 = 19.2 MHz | cape.dtsi:1920 | 与 阶段 12a GENI 探活同款 ref 时钟源 |
| clocks ×9 | core=GCC_UFS_PHY_AXI_CLK(GCC 151/0x97)、bus_aggr=GCC_AGGRE_UFS_PHY_AXI_CLK(10)、iface=GCC_UFS_PHY_AHB_CLK(150)、unipro=GCC_UFS_PHY_UNIPRO_CORE_CLK(166)、ice=GCC_UFS_PHY_ICE_CORE_CLK(154)、ref=RPMH_CXO_CLK(rpmhclk 0)、tx_sym0=GCC 164、rx_sym0=GCC 160、rx_sym1=GCC 162 | live FDT clocks 序列 | cape.dtsi:1921-1940 |
| freq-table-hz | 75M/850M（core、unipro、ice），余 0/0 | live FDT | cape.dtsi:1941-1950 |
| resets | `<gcc 25>`（0x24 0x19）名 "rst" | live FDT | = GCC_UFS_PHY_BCR；GPL ufs-qcom.c:4002 `devm_reset_control_get(hba->dev, "rst")` |
| reset provider | ufshc 自身（#reset-cells=1） | cape.dtsi:1915 | ufs-qcom.c:2556-2585 ufs_qcom_reset_ops（PHY 的 resets=<&ufshc_mem 0>，cape.dtsi:1902） |
| supplies | vcc=pm8350_l7（phandle 759）、vccq=pm8350_l9（760）、vdd-hba=GDSC@187004（46，UFS PHY GDSC power domain） | live FDT 解析 | — |
| interconnects | ufs-ddr（aggre1_noc→EBI1）、cpu-ufs（gem_noc→SLAVE_UFS_MEM_CFG） | cape.dtsi:1952-1954 | vendor 驱动投票用；**我们不走（UEFI 已投票）** |
| qos0/qos1 子节点 | mask 0xf0/0x0f, vote 0x2c | live FDT | prime/silver mask（cape.dtsi:1917-1918 qcom,prime-mask=0x70/silver=0x0f） |
| udon overlay | `qcom,iommu-faults = "non-fatal"` | refs/modules_dt_sm8475 oplus/udon-22803-cape-overlay.dts:66-68 | arm-smmu.c:2254 |

### 2.2 ufsphy_mem@1d80000

| 参数 | 值 | 证据 |
|---|---|---|
| compatible | **`qcom,ufs-phy-qmp-v4-cape`** | live FDT；GPL `drivers/phy/qualcomm/phy-qcom-ufs-qmp-v4-cape.c`（320 行）= **SM8475 代际证据** |
| reg | 0x1d80000 + 0x2000（phy_mem） | live FDT + cape.dtsi:1884 |
| clocks ×9 | ref_clk_src=RPMH_CXO、ref_aux=GCC 157、qref=GCC 149、rx_sym0/1_mux=GCC 161/163、tx_sym0_mux=GCC 165、rx_sym0/1_phy=UFS_PHY_RX_SYMBOL_0/1_CLK(GCC 4/5)、tx_sym0_phy=GCC 6 | live FDT + cape.dtsi:1889-1901 |
| resets | `<&ufshc_mem 0>`（控制器做 PHY reset provider） | cape.dtsi:1902 |
| lanes | 2 | live FDT |
| supplies | vdda-phy=pm8350_l5（560）、vdda-pll=pm8350c_l10（561） | live FDT |

### 2.3 GPL 驱动路径（SM8475 代际确认 + 深后备参考）

clone：`~/hakios/refs/kernel_oneplus_sm8475` @ `c84a1a097ee0e040b56492ab782573dd8c03aa7f`（branch `oneplus/sm8475_b_16.0.0_ace_2`，PHK110_16.0.3.501(CN01)）：

| 文件 | 行数 | 说明 |
|---|---|---|
| `drivers/scsi/ufs/ufs-qcom.c` | 6205 | 高通 host glue（UIC/DME/时钟/PHY reset provider/ICE） |
| `drivers/scsi/ufs/ufshcd.c` | 9561 | JESD223 UFSHCI 核心栈 |
| `drivers/phy/qualcomm/phy-qcom-ufs-qmp-v4-cape.c`(+.h) | 320 | **cape 专属 PHY 序列** |
| `drivers/scsi/ufs/ufs-qcom-ice.c` | 289 | inline crypto |

合计 16375 行——**移植此栈不可行亦不需要**；用途限定为 S3+ 调试时的寄存器语义字典（UIC 命令值、PA_HSSeries、DME_ 常量）。

### 2.4 与参考机（redwood/SM7325）的差异表

| 项 | redwood | PHK110（本机） | 影响 |
|---|---|---|---|
| ufshc 基址 | 0x1d84000 | **0x1d84000（相同）** | loader/内核常量零改 |
| PHY compatible | qmp-v4（yupik 代） | qmp-v4-**cape** | 仅 UFSDxe 关心；我们不做 PHY |
| GPT | darwin=sda34, LBA 25374720..30617594 | darwin 不存在（P0 carve 出来） | userdata-carve/darwin-write 常量 PHK110 化 |
| UFS 写上界常量 | UFS_WRITE_FIRST=2042368 / UFS_DARWIN_MIN=5242875（20GiB） | **建议 carve 时对齐同款 20GiB darwin** → 内核/loader/mkdatavol 常量全部零改 | P0 设计约束（§4） |

---

## 3. fork 侧差距分析

### 3.1 文件级 diff（fork WSL `~/hakios/kernel` vs upstream 克隆）

```
SAME  drivers/storage/hakios.ufs.c
SAME  drivers/storage/hakios.ufshc.c
SAME  drivers/storage/hakios.ufshc.h
SAME  drivers/storage/conf
SAME  userland/src/init.c
SAME  userland/src/var_store.c
SAME  tools/userdata-carve.py
SAME  tools/darwin-write.py
DIFF  xnuloader/loader.c   (201 行 = PAYLOAD_BASE 参数化 + klog flush 修复 + GICR stride + platform_phk110 —— 全是已刷入真机验证的 PHK110 平台件，存储段 0 diff)
DIFF  configs/common_defconfig (7 行 = S3910/buttons 条目，与本波无关)
```

### 3.2 配置链现状

| 文件:行 | 现值 | 施工动作 |
|---|---|---|
| `configs/common_defconfig:95` | `CONFIG_HAKIOS_UFS=y` | （已开，common 层） |
| `:175` | `CONFIG_UFS=2` | 已开（mailbox 服务） |
| `:178` | `# CONFIG_UFS_WRITE is not set` | phk110 层覆盖开（S3） |
| `:180` | `# CONFIG_VAR_STORE is not set` | 同上（可选，HFS+ 直写不依赖它） |
| `:277` | `# CONFIG_UFS_NATIVE is not set` | 进阶档再开（config 开了才认 ufs_native= boot-arg；建议直接开上，运行时由 boot-arg 决定是否启用） |
| **`devices/phk110/configs/phk110.config:38`** | **`# CONFIG_HAKIOS_UFS is not set`** ← 唯一的关 | **改为 `CONFIG_HAKIOS_UFS=y`（S0 施工第一行）** |

链上调用点已接好：`drivers/input/hakios.input.c:234` 调 `hakios_ufs_init()`（CONFIG 关时落到 `drivers/core/hakios.stubs.c:53` 空实现——现 PHK110 内核即此状态）。

### 3.3 IOKit 块设备层问答

- fork/upstream 内核里有没有 IOBlockStorageDevice/IOMedia/GPT scheme？——**没有，也不需要**。存储设备 = bdevsw/cdevsw + devfs（§1.1）；GPT 由 loader 解析进 mailbox 页。xnu 树里 IOKit storage 头存在（Apple 源自带）但无驱动实现。
- PLAN.md v0.4 的分层语句建议改为："UFS(UEFI UFSDxe) → loader mailbox → bdevsw/cdevsw 块设备 → HFS+ VFS"（本报告 §1.1 图）。

### 3.4 "goodix/s3910 骨架能否套 UFS？"

不适用，是两条不同的路径：s3910 模式 = "新写 device-repo 驱动 + MMIO/RPMh 自起"（适配 redwood 没有的硬件）；UFS 模式 = "upstream 现成驱动 + loader 服务"（redwood 有、本机同款硬件、同基址）。UFS 的 fork 差距只有 **config 开关 + 分区 + boot-args**，无需任何新驱动文件。

### 3.5 UEFI 侧（fork WSL `~/hakios/uefi-udon`）

`Platforms/OnePlus/udonPkg/Include/DXE.inc` 已含完整 vendor 存储栈：

```
:29-30  DALSYSDxe + HALIOMMUDxe
:45     Binaries/udon/QcomPkg/Drivers/UFSDxe/UFSDxe.inf
:46-49  CmdDbDxe/PwrUtilsDxe/RpmhDxe/NpaDxe
:52     ClockDxe :53 SPMIDxe :57 SmemDxe
```

Binaries/udon（提取自本机原厂 FD）已就位。**真机验证实证**：loader 每轮把内核日志写进 `logdump` 分区（loader.c:43 `LOG_PARTITION u"logdump"`，write_logs :363-434 走 EFI_BLOCK_IO=UFSDxe），Boot #8–#17 全部成功落盘并被回读（logdump-v3…v10.bin，最大 131,072B）——**UEFI 的 UFS 读、写、flush、GPT 分区定位在本机全部工作，S0 的验收其实在 Boot #8 就过了**。

施工首日核查项（一行 diff 的事）：对照 `Binaries/udon/QcomPkg/Drivers/DALSYSDxe` 是否已含 redwood 同款 cache-coherence patch（redwood Binaries README 列此 patch 为必需；我们的是原厂原版。logdump 工作说明原厂版在其自身内存布局下正常，但 ufs mailbox 的共享 buffer 在 payload 窗口，属新布局——S1 对拍数据错时第一嫌疑）。

---

## 4. S0–S8 施工单（照单施工版）

> 图例：📂=要写/改的文件（路径:行）；📐=预计行数；✅=验收证据（日志行，逐字可 grep）；⚠️=风险（编号见 §5）。
> 顺序原则：P0（装机一次性，需单独确认）→ S0-S2（只读，boot_b 循环授权内）→ S3-S4（开写）→ S5-S7（文件系统）→ S8（持久闭环）→ N（进阶 native）。

### P0 · darwin 分区 carve（装机前置，**破坏性，需单独确认**）
- 📂 `tools/userdata-carve.py` → 复制为 `tools/userdata-carve-phk110.py`（或加 `--phone` 参数）📐 ~40 行改动：GPT 头位置/LUN 名（本机 `/dev/block/sda` 假设需真机核）+ GIB 参数
- 📂 `tools/darwin-write.py` :29-34 常量 → PHK110 版（PARTN/FIRST/LAST/NODE 由 P0 实测的 GPT 填）📐 ~10 行
- 📂 `tools/mkdatavol.py` :27-29 → **不改**（DATA_FIRST=2042368 保持，见下约束）
- **设计约束**：carve 出的 darwin 必须 = 5,242,875 块（20GiB，块 4096），即 redwood 的 UFS_DARWIN_MIN——这样 `ufs.c:91 UFS_DARWIN_MIN`、`loader.c` 的 darwin 校验、`mkdatavol.py` 的 DARWIN_BLOCKS 全部零改动。
- 步骤：①adb root 备份 GPT 头尾 + f2fs segment_info（backup-partitions.py 同款）②f2fs 缩 20GiB（F2FS_IOC_RESIZE_FS，安卓自家内核做）③写新 GPT 双表（工具产 + CRC 校验 + 读回核对）④`mkdatavol.py darwin.simg`（12G 卷 at UFS_WRITE_FIRST）⑤`fastboot flash darwin darwin.simg`（fastboot 通道现成）或 adb dd（darwin-write.py）
- ✅ 安卓侧：`ls /dev/block/by-name/darwin` + `blockdev --getsize64` = 21,474,844,160；UFS 内核侧 S2 起可见
- ⚠️ R6（f2fs resize 拒绝 → `--wipe` 路线 = fastboot -w 抹数据，升级审批）；R7（GPT 手术错表 → 双 CRC + 读回 + 只改两 entry 的设计不变量）

### S0 · UFS init + 枚举（只读）—— 大半已达成
- 📂 `devices/phk110/configs/phk110.config:38` `# CONFIG_HAKIOS_UFS is not set` → `CONFIG_HAKIOS_UFS=y` 📐 1 行
- 📂 `configs/common_defconfig:277` `# CONFIG_UFS_NATIVE` → `CONFIG_UFS_NATIVE=y`（编进，运行期 boot-arg 控）📐 1 行（可选，N 步前需要）
- 📂 `wave15-scripts/repack-payload-v11.py`（仿 wave12 同名流程）cmdline 追加 `ufs=2` 📐 ~15 行脚本
- ✅ 证据：loader 日志 `ufs: N partitions of the phone's storage as /dev/ufs_NAME and /dev/rufs_NAME, read only, through the loader's page at 0x… and its … KB buffer`（ufs.c:1759-1760）；N ≈ 本机分区数（P0 后含 darwin）；现有 `logdump` 写入继续成功（= UEFI UFSDxe 活性）
- ⚠️ R4（分区数 >160 截断——BLOCK_MAX_PARTS=160，ufs.c:73；先 ufs=1 survey 数一数）
- 注：不新增 loader DT 节点、不加新 boot-arg 到 loader（`ufs=` 由 XL_CMDLINE 进内核 cmdline，loader.c:3086 解析）

### S1 · mailbox 首读对拍（只读）
- 施工：随 S0 自动（ufs=2 即服务）；加验：cmdline 临时 `ufs_check=1`（内核起 40s 后全参考分区 FNV 对拍 host 侧 ufs-survey.py）📐 0 行
- ✅ `ufs: check: … fnv <hash> over <bytes> …`（ufs.c:1198）与 loader 自身 survey 哈希一致；`kern.hakios.ufs_requests` >0
- ⚠️ R1（数据错 → DALSYSDxe coherence 嫌疑链）R2（stale logdump 掩盖真实输出——检查 `== KERNEL LOG ==` 段）

### S2 · GPT 可见性（只读）
- 施工：0 行（loader 侧 GPT 解析 + darwin 身份验证已在每次 block_start 跑）
- ✅ loader 日志 darwin 枚举行（loader.c block_is_darwin 通过才会 offer write_part）；内核读 darwin block 1 = "EFI PART"（可由 ufs_check 的 GPT crc 行旁证，ufs.c:1541-1543）
- ⚠️ R4

### S3 · 有界读写回读（**第一个开写实验**）
- 📂 `configs/common_defconfig:178` → 在 phk110.config 覆盖：`CONFIG_UFS_WRITE=y`（+ `CONFIG_VAR_STORE=y` :180，S8 用）📐 2 行
- 📂 cmdline 追加 `ufs_write=1` 📐 1 行（loader+kernel 双侧同名 boot-arg，loader.c block_write_requested / ufs.c:1768）
- 测试矩阵（xnu 用户态或 sysctl 读数）：①4K 单块写→读回比对 ②256K（buffer 一次写满）③跨 buffer 两块 ④越界拒绝：offset=UFS_WRITE_FIRST-1 块处写 → EROFS（ufs.c:615-620）
- ✅ `ufs: /dev/rufs_darwin takes writes, whole blocks from 2042368 on (…MB of it); everything else of the storage is read only`（ufs.c:1802-1804）+ `kern.hakios.ufs_writes` 增长且 `ufs_write_errors=0` `ufs_write_refused` 仅在拒绝测试增
- ⚠️ R1 R3（§5 详列死法）

### S4 · flush / 写序（验证，基本 0 行）
- 施工：0 行（loader 的 BLOCK_CAN_FAST + 内核 ufs_data_op/ufs_data_flush 已编进）；确认 loader 侧 fast op 支持（loader.c write_caps）
- ✅ `ufs: /dev/ufs_darwin_data: the same … MB as a block device, for the data volume; writes flushed when the file system asks`（ufs.c:1808-1809 的 fast 文案，若打印的是 "every write flushed and read back (an older loader)" 则 loader 侧未给 FAST——需查 loader.c）
- 写序设计定论（写进设计，不再议）：单写者互斥（ufs_write_mtx ufs.c:622-639）+ mailbox 单请求在飞（结构上无乱序）+ journal flush 点显式 flush；无 FUA/NCQ 语义需要实现。
- ⚠️ R5（HFS journal 语义依赖 DKIOCSYNCHRONIZECACHE 真落 flash——fast 路径下 loader flush 语义要核对 loader.c 的 BLOCK_OP_FLUSH 实现）

### S5 · 设备发布
- 施工：0 行。✅ `ufs: /dev/ufs_darwin_data: the same 12,288 MB as a block device…`（ufs.c:1805-1810）。**明确：不发布 IOMedia，不建 IOKit 栈**（§3.3）

### S6 · HFS+ 挂载
- 📂 cmdline 追加 `var_hfs=ufs_darwin_data` 📐 1 行
- 前置：P0 的卷已灌好（mkdatavol）；init.c:825-860 自动挂
- ✅ `  /private/var: HFS Plus from /dev/ufs_darwin_data, kept between boots`（init.c:859）；失败回落行 `HFS Plus from …: …; a memory filesystem instead`（:856-857 出现即判失败原因）
- 可选前置自洽：`qemu/run-hfs-test.sh`（fork 树，virtio-blk 链）先在 QEMU 过一遍 hfs_test 两轮持久 📐 0 行（跑即可）
- ⚠️ R8（HFS+ 卷 GUID=0 / HFSX case-sensitive——mkdatavol 与 mkfs.hfsplus -s -J -U 0 同款，upstream 实机已证）

### S7 · /var 内容
- 施工：0 行（init empty_tree + `work/var.skel` 112 行骨架由 init 语义重建；Procursus jb 嫁接 = SSH 波的活，不在本单）
- ✅ 挂载后 `/private/var` 下骨架目录在位（klog 或后续 SSH 验）

### S8 · 重启持久
- 施工：0 行（机制全在）；测试协议：
  ①boot #N：写 marker（var_kept 卷上 `echo` 类工具或 var_store saver）②`loader_return_after` 到期干净返回 ③logdump 确认 `var_store:` 行 ④boot #N+1 读 marker 在
- ✅ 关键日志：`var_store: the run is ending: the data volume is asked for`（ufs.c:1127）→ `var_store: the saver has finished after … ms`（:1135）或 HFS+ 直写路径下 boot #N+1 的 S6 挂载行 + marker 内容
- ⚠️ R9（panic 路径不走 saver——journal 回退；R5 flush 真落盘）

### N · native 直驱进阶（可选性能档，S3 稳定后）
- 施工：0 行代码；boot-args 阶梯：`ufs_native=2`（只看）→ `=3`（dry run 换列表进出）→ `ufs_native=1`（真读）→ `ufs_native_check=1`（全盘对拍，ufs.c:1490-1596）
- ✅ `ufs: native: usable: a list of 32 slots at 0x… (the loader's), reads in 31 of them…`（ufshc.c:1304）+ proof 行 `proof: TEST UNIT READY in this list's slot 0 came back here`（:890）+ 对拍 `the same`（:1458）
- ⚠️ R3（UIC/doorbell 超时——native 独有，失败自动回 loader 路径 ufs.c:582-589）

### boot-args 总账（608 字符预算，现用 451）
```
+ufs=2 ufs_write=1 var_hfs=ufs_darwin_data     → ~+50 字符（S0+S3+S6 三波分步加）
（N 步另加 ufs_native=…；S8 不需要新 arg）
```

### 工作量总账
| 类别 | 预计 |
|---|---|
| 内核/loader/UEFI 代码 | **0 行**（全现成，字节级验证） |
| config/cmdline | ~5 行 |
| P0 工具 PHK110 化 + 执行脚本 | ~150-200 行（大半是 redwood 常量替换 + 安卓侧步骤脚本） |
| repack/verify 脚本（仿 wave12 流程） | ~100 行 |
| 真机 boot 次数预估 | S0-S2 一个镜像两刷；S3-S4 一刷；S6-S8 一刷；+N 若做 |

---

## 5. 风险登记（S3 死法优先）

| # | 死法 | 症状特征（日志指纹） | 检测手段 | 概率 | 回退 |
|---|---|---|---|---|---|
| R1 | **SCC/缓存一致性（DALSYSDxe）**：UFSDxe DMA buffer 与 loader/内核缓存线不一致 → 读回数据含旧线 | `ufs_check` FNV ≠ host survey 哈希；两连读结果不同；answer.status=0 但数据错 | S1 的 FNV 对拍 + 双读一致性测试；loader 侧 `FlushPoC` 后仍错即坐实 | 低-中（logdump 已证 UEFI 自身 DMA 正常，但 mailbox buffer 是新布局） | 对照 redwood Binaries README 给 udon DALSYSDxe 打同款 patch（graft 流程加一步）；mailbox 慢路径本身可继续用 |
| R2 | **stale logdump**：内核日志被循环重启覆盖，误判 S 步失败 | `== KERNEL LOG ==` 段缺失/截断；只见 loader 日志 | logdump 头部完整性检查（wave7b 已有方法） | 中（操作面） | 复读/长会话（loader_return_after 拉长）；无技术风险 |
| R3 | **UIC/doorbell 超时**（仅 native）：命令 10s 未完 | `ufs: native: slot %u (…) not done in 10 s (doorbell %08x, IS %08x, HCS %08x): this path is off from now on`（ufshc.c:674-677） | 行即检测；IS_FATAL 位探针 :105 | native 档中；mailbox 档**不可能**（无 UIC） | 结构性安全：hc_off + `ufs_native_fallbacks` 自动回 loader 读（ufs.c:582-589）；列表可逆（switch_out :1063） |
| R4 | **GPT 枚举差异**：分区 >160 / darwin 名不符 / slot 布局意外 | loader 枚举行缺 darwin；`ufs: no node for …`（ufs.c:1751） | S0 先 ufs=1 数分区；P0 后核对 | 低 | BLOCK_MAX_PARTS 扩容（ufs.c:73 + loader 同步）——预计不需 |
| R5 | **flush 未真落盘**：fast 路径 BLOCK_OP_FLUSH 语义与 journal 期待不符 → 掉电/重启丢尾 | S8 marker 重启消失；journal replay 日志 | S8 双轮 + 强制 reset 测试（有意不等 saver） | 低-中 | 回退慢路径（loader 不给 BLOCK_CAN_FAST 即自动全 flush+读回，ufs.c:699-703 已是行为开关） |
| R6 | **f2fs resize 拒绝**（P0） | resize F2FS_IOC_RESIZE_FS 返回错误 | P0 步骤内失败即显式 | 中 | `--wipe` 路线（fastboot -w 抹 userdata 重来）——**需单独确认**（抹数据） |
| R7 | **GPT 手术出错**（P0） | 双表 CRC 不合 / 安卓拒启 | 工具内建读回校验（userdata-carve.py 全程校验）+ 安卓重启验证 | 低（工具保守） | 回写备份的 gpt-head/tail.bin（P0 第①步产物） |
| R8 | **HFS+ 卷参数不合** | S6 回落行打印 errno | 行即检测 | 低 | 重建卷（mkfs.hfsplus 参数对照 run-hfs-test.sh:13） |
| R9 | **panic 打断写** | — | — | 必然会发生 | HFS journal 重放（挂载即修）+ var_store packed 回退（panic 不经 saver，store 保持旧档，var_store.c:193-206 设计注释） |

**S3 最可能死法排序**：R2（操作面，非技术）> R1 > R3（不可能发生于 mailbox 主路线）> R5。mailbox 主路线本质上把 UFS 控制器的复杂性全部留在已经实机验证的 UEFI 代码里——这就是 upstream 架构的精髓，也是"难点削平"的机理。

---

## 6. 仓储登记（upstream-manifest 风格）

本轮新增 shallow clone（WSL `~/hakios/refs/`，代理 127.0.0.1:7897，磁盘余量 916G）：

```
kernel_oneplus_sm8475   c84a1a097ee0e040b56492ab782573dd8c03aa7f  https://github.com/OnePlusOSS/android_kernel_oneplus_sm8475        (branch oneplus/sm8475_b_16.0.0_ace_2, PHK110_16.0.3.501)
modules_dt_sm8475       3c9f70751bfa346b3aca2a901f79a8645bb43116  https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475 (同 branch)
UniXNU-udon NativeUfs core ref: 04b748e613d6d34f6e7868d714db36184722924d (integration/core/NativeUfs.commit，workspace 克隆 ad550a97 内)
```

（已同步两行到 `upstream-manifest.txt`，注明 WSL 路径。）

---

## 7. 红线遵守

- 手机：零 adb/fastboot/usbipd/刷写 ✅（全部结论出自克隆与 FDT 静态分析）
- `~/hakios/kernel`：只读（diff/grep 读取；零写入）✅
- Windows 仓：仅新增 `docs/waves/wave15-ufs-research.md`、`wave15-scripts/fdt_ufs_nodes.py`（FDT 提取脚本）+ `upstream-manifest.txt` 两行 + STATUS.md 队列行（任务授权交付物）✅
- 新 clone 全部在 `~/hakios/refs/`，磁盘充裕 ✅
