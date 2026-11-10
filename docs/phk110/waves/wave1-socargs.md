# Wave 1：PHK110（Cape/SM8475）soc_* 启动参数补全 + 内存映射 + loader 窗口分析

调查代理 A 产出 · 2026-11-02 · 全部结论基于 PHK110 实机（adb 只读取证）与
`intel/phk110-fdt.dtb`（Cape 设备树，含 `__symbols__`）的逐节点解析。
FDT 证据同时用 ABL 基线树（`phk110-fdt.dtb`）与实机 `/sys/firmware/fdt`（`intel/live-fdt.dtb`）
交叉验证过：两份在所有相关节点上**完全一致**。

---

## 1. soc-args.py 的解析逻辑（为何漏 4 个值）

`upstream/hakios-xnu-kernel/tools/soc-args.py` 对每类参数用两种匹配：

| 函数 | 匹配方式 | 读取 |
|---|---|---|
| `find(compatible)` | 第一个含该 compatible 的节点 | reg 按固定 cell 序号 |
| `find_named(leaf)` | **叶子名去掉 `@` 后缀后必须整串等于 leaf** | reserved-memory 取 reg cell 1（2 地址 cell 的低字）；pas-id 取 `qcom,pas-id` |

4 个缺失值全部是 `find_named` **精确叶子名匹配**被 Cape 的 `_region` 命名约定破坏：

| boot-arg | 查找 leaf | Cape 实际叶子名 | 结果 |
|---|---|---|---|
| `soc_cmd_db` | `cmd_db` | `aop_cmd_db_region` | 落空 |
| `soc_mpss_mem` | `mpss` | `mpss_region` | 落空 |
| `modem_ipa_fw_at` | `ipa_gsi` | `ipa_gsi_region` | 落空 |
| `soc_pas_mpss` | `qcom,mss` | `remoteproc-mss`（且无 `qcom,pas-id` 属性） | 落空 |

---

## 2. 四个缺失值的最终值与 FDT 证据

### soc_cmd_db = 0x80860000

- 节点：`/reserved-memory/aop_cmd_db_region@80860000`
- reg = `<0x0 0x80860000 0x0 0x20000>`，compatible = `qcom,cmd-db`
- 与 redwood（0x80860000）相同，也与驱动内置 `CMD_DB_PHYS_DEFAULT`（`hakios.mpss.c:784`）相同
  —— 即使不写也不会错，仍显式写出以保持设备自描述。

### soc_mpss_mem = 0x8bc00000

- 节点：`/reserved-memory/mpss_region@8bc00000`
- reg = `<0x0 0x8bc00000 0x0 0x13200000>`（306 MB）
- phandle 155，被 modem PIL 节点 `/soc/remoteproc-mss@04080000`
  （compatible `qcom,cape-modem-pas`，reg `0x4080000+0x10000`）的 `memory-region` 第一项引用 —— 强证据。
- **与 redwood（0x8b800000）不同，此参数必需**，否则驱动默认地址指向错误区域。
- ⚠ 连带发现：驱动 `MPSS_MEMORY_SIZE = 0x0f600000`（246 MB，编译期常量，`hakios.mpss.c:1049`，
  用于 `SCM_PAS_MEM_SETUP` 与段越界检查）小于 Cape 预留的 306 MB。SM8475 的 modem 镜像
  可能超出 246 MB 窗口 —— modem 起动（wave 2+）时建议按设备放开该常量。

### modem_ipa_fw_at = 0x8b910000

- 节点：`/reserved-memory/ipa_gsi_region@8b910000`，reg = `<0x0 0x8b910000 0x0 0xa000>`；
  配套 `/reserved-memory/ipa_fw_region@8b900000`，reg = `<0x0 0x8b900000 0x0 0x10000>`。
- 驱动语义（`hakios.mpss.c:1801-1810` 注释 + `:2193-2198`）：Android 的 PIL 实际把 IPA 固件
  载入 **ipa_gsi 预留区**（redwood 实测日志 `yupik_ipa_fws: loading from 0x8b710000 to 0x8b717000`），
  而不是名字暗示的 ipa_fw 区；驱动默认 `ipa_fw_memory=0x8b710000, size=0xa000`，
  仅当传入 0x8b700000 时放宽为 0x1a000（fw+gsi 合并区）。
- Cape 布局与 sm8350 家族逐位平行：fw@base+0、gsi@base+0x10000、
  `gpu_microcode_region@8b91a000` 紧跟其后 —— redwood 是 `0x8b710000+0xa000 → 0x8b71a000 gpu_uc`，
  Cape 是 `0x8b910000+0xa000 → 0x8b91a000 gpu_uc`。结构同构 ⇒ **0x8b910000**。
- 固件文件名：Cape 为 `ipa_fws`（`/soc/qcom,ipa_fws` 的 `qcom,firmware-name`），
  经 soc-args 输出为 `soc_ipa_fw=ipa_fws`（redwood 是 `yupik_ipa_fws`）。
- 验证途径（wave 2）：刚开机时 `su -c dmesg | grep ipa_fws` 应出现
  `ipa_fws: loading from 0x8b910000 to 0x8b91xxxx`；若 vendor PIL 改载 ipa_fw_region，
  则改传 0x8b900000（此时驱动仍按 0xa000 收口）。

### soc_pas_mpss = 0x4（沿用，待真机验证）

- Cape FDT **没有** modem 的 `qcom,pas-id`。全树带 `qcom,pas-id` 的节点只有：
  `/soc/qcom,ipa_fws`（15 = 0xf ✓ 与驱动默认一致）、`qcom,gh_vm_loader_sec@...`（35/28）、
  `qcom,guestvm_loader@...`（35/28）。
- Cape modem 节点 `/soc/remoteproc-mss@04080000`（compatible `qcom,cape-modem-pas`）不含
  pas-id 属性 —— vendor 驱动按 PIL 惯例硬编码。MPSS = 4 是高通全 SoC 通用的 PIL 镜像 ID；
  驱动默认即 4（`PAS_MPSS_DEFAULT`，`hakios.mpss.c:1050`），redwood 也是 4。
- 结论：显式写 `soc_pas_mpss=0x4`，行为与默认相同、零风险；真机首个 modem 步骤
  （`SCM_PAS_INIT_IMAGE`/`SCM_PAS_MEM_SETUP`）若失败再回查此值。

---

## 3. 可直接使用的 soc.args 文本块

### 3a. 追加进 `devices/phk110/soc.args` 的 4 行（本次产出）

```
soc_cmd_db=0x80860000
soc_mpss_mem=0x8bc00000
modem_ipa_fw_at=0x8b910000
soc_pas_mpss=0x4
```

### 3b. 建议的完整 `devices/phk110/soc.args`（soc-args.py 在 Cape FDT 的输出 ∪ 上面 4 行）

```
soc_ipa_base=0x3e40000
soc_gsi_base=0x3e04000
soc_ipcc=0xed18000
soc_aoss=0xc300000
soc_rsc=0x17a20000
soc_apps_smmu=0x15000000
soc_cmd_db=0x80860000
soc_mpss_mem=0x8bc00000
modem_ipa_fw_at=0x8b910000
soc_smem=0x80900000
soc_imem=0x14600000
soc_ipa_stream=0x5c0
soc_ipa_stream_uc=0x5c2
soc_pas_mpss=0x4
soc_pas_ipa=0xf
soc_ipa_fw=ipa_fws
```

复核过的易错项：
- `soc_ipcc=0xed18000`：Cape 全树**只有这一个** `qcom,ipcc` 节点（SM7325 的 0x408000 在 SM8475
  vendor 树不存在）——不是 find() 选错实例。
- `soc_rsc=0x17a20000`：`/soc/rsc@17a00000` 有 4 对 reg（tcs-waste/drv-0/drv-1/drv-2），
  cell 4 = 第三对首地址 = drv-2（AP 侧），与工具取法一致；另一实例 `/soc/rsc@af20000`（DDR RSC）未被选。
- `soc_aoss=0xc300000`：Cape 与 redwood 相同（taro/yupik AOSS QMP 同地址）。

---

## 4. 完整内存映射

### 4a. 实机 /proc/iomem 的 System RAM（全量原文：`intel/iomem-full.txt`）

| # | 范围 | 大小 | 说明 |
|---|---|---|---|
| 1 | 0x808f4000–0x808fffff | 48 KB | 低 bank 零散 |
| 2 | 0x80d00000–0x856fffff | 74 MB | |
| 3 | 0x8b91c000–0x8b9fffff | 912 KB | ipa_gsi/gpu_uc 结束后 |
| 4 | 0xa0400000–0xa6dfffff | 106 MB | |
| 5 | 0xa6e40000–0xa6efffff | 48 KB | |
| 6 | 0xa7000000–0xe05fffff | 916 MB | |
| 7 | 0xe5700000–0xe87fffff | 49 MB | |
| 8 | 0xf1400000–0xffffffff | 236 MB | 4GB 顶段 |
| 9 | 0x800000000–0x8382fffff | 903.25 MB | 高 bank 首段 |
| 10 | 0x840000000–0xb7fffffff | **13 GB** | 高 bank 主体 |

System RAM 合计 `0x3E2300000` ≈ **15.78 GiB** ⇒ 本机是 16 GB SKU（任务书"12GB+"）。
低 bank 合计 `0x6a000000+0xec00000` ≈ 1.89 GiB；高 bank ≈ 13.88 GiB。

低 bank 的大孔洞（dominant 预留，全部 < 4GB）：
`0x80000000–0x808f3fff`（hyp/aop/cmd_db/tme/uefi_log/xbl）、`0x80900000–0x80cfffff`（smem/cpucp/cdsp_heap）、
`0x85700000–0x8b91bfff`（adsp/slpi/cdsp/ipa fw+gsi/gpu_uc）、`0x8ba00000–0x8bbfffff`（spss/spu）、
`0x8bc00000–0x8ee00000`（**mpss 306MB**）、`0x8ee00000–0xa03fffff`（~292MB，DT 未列名的厂商动态预留，
含 mem_dump/ramoops 动态分配候选）、`0xe0600000–0xe56fffff`（cpusys_vm/hyp_reserved/trust_ui_vm）、
`0xe8800000–0xf13fffff`（tz_stat/tags/qtee/qheebsp + UEFI 自留）。
高 bank 唯一孔洞：`0x838300000–0x83ffffff`（8.25 MB，DT 未列名）。

### 4b. FDT /memory reg（ABL 基线树与实机 /sys/firmware/fdt 完全相同，5 段，乱序）

| 段 | 起点 | 大小 | 终点 |
|---|---|---|---|
| 1 | 0x80000000 | 0x6a000000 (1.656 GB) | 0xe9ffffff |
| 2 | 0xf1400000 | 0xec00000 (236 MB) | 0xffffffff |
| 3 | 0x800000000 | 0x38300000 (903.25 MB) | 0x8382fffff |
| 4 | 0x980000000 | 0x200000000 (8 GB) | 0xb7fffffff |
| 5 | 0x840000000 | 0x140000000 (5 GB) | 0x97fffffff |

合计 = 0x3E2300000，与 /proc/iomem 完全吻合（段 4+5 即 iomem 的连续 13GB）。

### 4c. FDT `/ddr-regions`（硬件 DDR 视图，合计 16 GB；`ddr_device_type=8` → LPDDR5）

| region | 起点 | 大小 |
|---|---|---|
| region0 | 0x80000000 | 0x80000000 (2 GB) |
| region1 | 0x800000000 | 0x180000000 (6 GB) |
| region2 | 0x980000000 | 0x200000000 (8 GB) |

硬件上高 bank 为连续 14 GB（0x800000000–0xb7fffffff）；Linux 视图仅少了 0x838300000–0x83ffffff
（8.25 MB）与低 bank 的 QCOM/UEFI carveout。每 region 后 6 个 u32 为保留/等级字段（末位 0x400）。

---

## 5. loader 内存窗口分析与 v0.1 结论

### 5a. choose_window() 机制（`xnuloader/loader.c:2761-2816`）

1. 取 UEFI GetMemoryMap，遍历 `EfiConventionalMemory` 块；
2. 与 payload 区（`PAYLOAD_BASE=0xF0000000`，64 MB）重叠时收缩该块；
3. 32 MB 对齐（`BASE_ALIGN`，16K 页的 L2 block）；
4. 取最大块，封顶 `MAX_MEM_SIZE = 0x180000000`（6 GB）；
5. `allocate_pages(AllocateAddress, EfiLoaderData)` 一次性占住，作为 XNU 的
   `[physBase, physBase+memSize)`；`ba->physBase = win_base; ba->memSize = win_size`（`:3087-3089`）。
   另有 `forced_base` 测试后门（payload 文本强制，`:2799-2801`，直接假设 6 GB 空闲）。

### 5b. PHK110 上预期的窗口

高 bank `0x840000000–0xb7fffffff`（13 GB）在 DT 中**没有任何 carveout**（全部 QCOM 预留 < 4GB），
UEFI（ABL）自身驻留低 bank；预期最大 conventional 块即高 bank ≈ 13 GB ⇒
**窗口 = 0x840000000 … 0xA40000000（6 GB），physBase = 0x840000000（33 GiB，32MB 对齐 ✓）**。
payload（0xF0000000+64MB）与窗口不相交；6 GB cap 截断而非分配失败。

### 5c. physBase > 32 位是否安全 —— 逐项核查

| 顾虑 | 证据 | 结论 |
|---|---|---|
| boot_args 宽度 | `struct boot_args.physBase/memSize` 均为 u64（`loader.c:57-58`）；DT 写 `dram-base/dram-size` 用 `dt_prop_u64`（`:3240-3241`） | 无截断 |
| 内核对高 physBase 的运算 | `hakios.patch:2170`：`cpu_data_paddr = args->physBase + (&BootCpuData - args->virtBase)`，纯 64 位指针算术 | 安全 |
| bootstrap 页表覆盖 | `hakios.patch`（pmap.h）：`start.s maps all of memSize`；4K 分支 20 页覆盖 8 GB；loader 注释同口径"cover 8" | 6 GB < 8 GB ✓ |
| 内核链接基址映射 | `KERNEL_VIRT_BASE = 0xFFFFFFF004000000` + 6 GB → 最高 VA `0xFFFFFFF184000000`，无回绕，TTBR1 范围内；phystokv 偏移 `0xFFFFFFE7C4000000` 为普通 64 位差值 | 安全 |
| SoC PA 能力 | SM8475 PARANGE ≥ 44 bit；Apple 自家 A 系/M 系本来就是高 DRAM 基址跑 XNU | 安全 |
| redwood 先例 | SM7325 8GB 机型高 bank 同样 > 32 位，`physBase=0x800000000` 一级已是 HakiOS 实跑配置 | 已验证过的路径 |

### 5d. v0.1 结论

- **loader 无需改动**：choose_window 自动落高 bank；6 GB 对 v0.1（内核 + root image ≤ 768MB 的
  RESIDENT_RD 预算）绰绰有余；不建议 v0.1 动 `MAX_MEM_SIZE`，也不建议用 forced_base（若强制，
  `forced_base=0x840000000` 在本机可行——高 bank 有 13 GB，allocate 6 GB 能成）。
- 后续如需 >6 GB：上限是 bootstrap 页表的 8 GB 覆盖；先把 `MAX_MEM_SIZE` 提到 0x200000000 之前，
  按 16K 页实际配置核对 `BOOTSTRAP_TABLE_SIZE` 分支（patch 注释的算术是 4K 页口径）。
- ⚠ 与本任务无关但同属上机风险的已存问题：payload 固定在 `0xF0000000`，而 Cape 的 DT 里
  `0xF0000000–0xF13fffff` 不在 RAM 内（RAM 从 0xf1400000 起）——payload 放置由 boot shim 负责，
  上机前需确认 shim 在 Cape 上的落位逻辑避开该 20 MB 缺口。

---

## 6. 命令与中间数据

只读取证，未写手机任何分区/文件（除 `/data/local/tmp` 中转）：

| 产物 | 来源 |
|---|---|
| `intel/iomem-full.txt` | `adb shell su -c 'cat /proc/iomem > /data/local/tmp/iomem-full.txt'` + `adb pull`（331 行全量） |
| `intel/live-fdt.dtb` | `su -c 'cat /sys/firmware/fdt > /data/local/tmp/live-fdt'` + pull（1,200,263 B） |
| `intel/phk110-fdt.dtb` | 已有（ABL 基线树） |
| `intel/parse_fdt_phk110.py` | 本次新写的 FDT 解析器（walker 复用 soc-args.py，含 #address-cells/#size-cells 跟踪） |
| `intel/fdt-reserved-dump.txt` / `intel/fdt-live-dump.txt` | 解析器对两份 FDT 的全量输出（reserved-memory/pas-id/memory/ddr-regions/__symbols__） |
| soc-args 输出 | `wsl python3 upstream/hakios-xnu-kernel/tools/soc-args.py intel/phk110-fdt.dtb`（缺 4 值实锤 + 12 个已得值） |
| 驱动证据 | `drivers/modem/hakios.mpss.c`：784-786（cmd_db 默认）、1047-1051（mpss/pas 默认）、1801-1810（ipa fw 加载语义）、2193-2198（boot-arg 解析）、287、6324-6340（soc_override） |
| loader/kernel 证据 | `xnuloader/loader.c`：24-42（常量）、2761-2816（choose_window）、3087-3089、3240；`xnu/hakios.patch`：cpu_data_paddr（~2170）、BOOTSTRAP_TABLE_SIZE（~2346） |
| IPCC/RSC 复核 | 对 Cape FDT 全树枚举 `qcom,ipcc`/`qcom,rpmh-rsc` 节点 reg |

未尽事项：调查尾声无线 adb 掉线（`adb connect` 被拒），pstore（上次开机的 PIL 日志）与
`ro.product.device` 复核未取到；pstore 只是 `modem_ipa_fw_at`/`soc_pas_mpss` 的锦上添花证据，
wave 2 上机时可补。

自主决策记录：
1. `modem_ipa_fw_at` 取 ipa_gsi_region（0x8b910000）而非 ipa_fw_region（0x8b900000）——依据
   驱动注释的 PIL 实际行为 + 两 SoC 布局同构（gpu_uc 都在 gsi 基址 +0xa000 后）；已给 wave 2 验证方法。
2. `soc_pas_mpss` 沿用 4（FDT 无该属性，驱动默认与高通 PIL 常量一致）。
3. 实机判定为 16GB SKU（任务书"12GB+"不冲突），内存分析按实机 iomem。
4. `soc_cmd_db` 虽与驱动默认相同仍显式写入，保持设备文件自描述。
