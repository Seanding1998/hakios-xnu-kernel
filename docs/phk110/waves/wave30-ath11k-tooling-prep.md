# 阶段 30 · 2026-11-10 · WiFi（ath11k）工具链准备

> 2026-11-10 · 阶段 30 工具链前置
> 任务书：把 F15 确认的"固定源码管线范式"（fork 的 `tools/mk-ath10k.py` + 16 个 `check-wifi-*.py`）提前做成 PHK110 v0.6 WiFi 前置工具链；另做 Mu-Silicium nuwaPkg 快查
> 红线执行：零手机零刷写零 fastboot/adb ✓（全程只碰主机侧 + 上游克隆）；上游浅 clone 全部放 `wave30-scripts/upstream-scratch/`（不入库，已加 .gitignore）✓；未改动 WSL 构建树任何产物 ✓（本波无 WSL 写操作）

## 0. 判定（先行，六条）

1. **fork 管线范式 = 证实可搬**。`tools/mk-ath10k.py`（191 行）是一条完整的"固定源码 → 主机侧编 .o → 链入 XNU"流水线：4 个上游归档（linux/freebsd/wpa_supplicant/mbedtls）全部 SHA256 锁定 → tar 定向抽取（strip-components 定位）→ 逐文件 patch → clang `-target arm64-apple-ios16.5 -mkernel` 按 FreeBSD 内核码编译 → `ld64 -r` 合体 → 未定义符号门 → 只导出 4 个入口（`lx_prepare/lx_start/lx_stop/lx_transmit`）。`xnu-build.sh` 用 `HAKIOS_OBJECTS=$WIFI_OBJECT` 把 `ath11k.o`/`ath10k.o` 链进 XNU 并按 mtime 失效缓存内核。**这四样（SHA 锁、许可门、stub 阶梯、单入口导出）就是我们要搬的全部骨架**，本波已照搬为可运行的 `wave30-scripts/mk-ath11k.py`。
2. **本波把管线真跑到了"源码就绪"**：`mk-ath11k.py --verify` 真实拉取 linux-7.0.14.tar.xz（157,262,664 B）+ freebsd-15.1-src.txz（253,039,000 B），SHA256 与 fork 锁定值逐字节一致；抽出 22 个 ath11k 文件（20 core + mhi + pci），**逐文件许可证门 22/22 通过**（fork 规则：每文件必须自带 `SPDX-License-Identifier: BSD-3-Clause-Clear` 或 ISC 全文）；`compile-plan.json` 已产出。编译/链接步按任务书**故意拒绝**（`--build` 返回解释性错误），等内核侧 `hakios.lx.h` 出现。
3. **决定性新发现（修正 F14 的两个隐含假设）**：上游 linux 7.0.14 的 ath11k **根本没有 `ATH11K_HW_QCA6490` 这个 hw_rev**——PHK110 DTB 里的 `qcom,cnss-qca6490` 在 ath11k 世界里的身份是 **WCN6750 hw1.0**（`core.h` 枚举 + `core.c` hw_params 表在证）；固件目录因此是 **`WCN6750/hw1.0/`**（`core.c:582`，F14 写的 "QCA6490/hw1.0" 不存在）。且 **ath11k_pci 模块对 WCN6750 是"core 就绪、胶水缺失"**：`pci.c` 设备 ID 表只有 QCA6390/WCN6855/QCN9074，`mhi.c` 的 hw_rev switch 没有 WCN6750 case（default 直接报 `failed assign mhi_config`）。→ **管线必须携带 2 个一行级补丁**（见 §2.3，已写成 check 脚本的 GAP 清单）。
4. **GPL 边界是 ath11k-PCI 路线与 ath10k-SNOC 路线的结构性差异**：ath11k 全树 BSD-3-Clause-Clear（许可门可过），但它依赖的 **drivers/bus/mhi（MHI 主机栈）是 GPL-2.0-only**——不能像 ath11k 一样链入。fork 自己的答案是把总线协议在手写垫层里重实现（`wifi/lx/src/lx_bus.c` 为 WCN6750 手写了 ahb.c 探测序 + 1ms CE 轮询线程，270ms 到 "unified ready" 真机实证）；我们的 MHI 协议实现同样应住在 wifi/lx 层（MHI 环形通道协议本身有公开规范形态，ath11k/mhi.c 的调用面就是需求文档）。
5. **check-wifi-*.py 的判定模式 = "宿主编译内核真实函数 + mock 环境 + ASan/UBSan + assert"**：脚本用 regex 从 `hakios.wifi.c` 里抽出真实交付到手机的函数（MDT 解析器、QRTR 状态机、SMMU 页表……）连同其常量，镶进生成的 C harness，mock 掉硬件边界（image_file/rd/kmem_alloc 等），`cc -fsanitize=address,undefined` 原生跑 assert，`puts("PASS: ...")` 收尾。**测的是真机验证的那份代码，不是测试替身**。本波 5 个 `check-phk110-wifi-*.py` 已按此范式立起（内核代码未写前先测 DTB/固件清单/环算术/上游契约；e2e 脚本挂 wave27 通道）。
6. **nuwaPkg 情报修正（F15 §5.3 两处失实）**：Mu-Silicium `Platforms/Xiaomi/nuwaPkg`（仅 13 文件）**不是 Redmi K60/SM8475，而是小米 13 Pro/SM8550**——`nuwa.dsc` 注释 `0 = SM8550-AB / 1 = SM8550-AC`、`!include KailuaPkg/KailuaPkg.dsc.inc`、FDT `sm8550-xiaomi-nuwa.dtb`、SMBIOS `PcdSmbiosSystemModel|"13 Pro"` 四处互证。"同 SoC 备胎"降级为"**同生态模板备胎**"（kalama vs cape 隔一代，但它是一套完整能出 UEFI 的 Qualcomm 设备包模板，vendor DXE 全集见 §4）。

---

## 1. raphael fork 管线精读（任务 1 交付）

克隆：`HeliumStudio-Dev/hackios-xnu-kernel` @ `raphael-bringup`（depth 60，tip `5772246`），本地路径 `wave30-scripts/upstream-scratch/raphael-fork/`。

### 1.1 三源汇合（仓库里的原话级概括）

`mk-ath11k.sh` 头注释把架构说尽了（fork 仓库原文，我们翻译）：

| 源 | 是什么 | 许可 | 在管线里的角色 |
|---|---|---|---|
| **Linux 的 ath11k/ath10k** | kernel.org 固定 release 的 `drivers/net/wireless/ath/ath11k`（或 ath10k） | BSD-3-Clause-Clear（ath/ 下那一个头是 ISC） | 不改的驱动源码，逐文件许可门 |
| **FreeBSD 的 LinuxKPI** | 15.1-RELEASE 的头文件（`compat/linuxkpi/common/include` 等），**只用头不用 .c**（其功能在 wifi/lx/src 里重写） | BSD-2-Clause | Linux 驱动编译所依赖的 API 形状 |
| **wifi/lx（自己的）** | LinuxKPI 缺的头（device tree/platform device）、FreeBSD 里"在 XNU 下不能用"的头、以及底下的函数实现（锁/睡眠/work/内存/firmware/总线）——全部写在内核 `bsd/dev/hakios.lx.c` 提供的少数调用上 | 项目自有 | 垫层与粘合 |

### 1.2 固定源码 + 锁定机制（`mk-ath10k.py`）

- `SOURCES` 字典四元组（文件名, URL, SHA256）：`linux-7.0.14.tar.xz`（kernel.org）、`freebsd-15.1-src.txz`（freebsd.org）、`wpa_supplicant-2.11.tar.gz`（w1.fi）、`mbedtls-3.6.7.tar.bz2`（GitHub）。四个 SHA256 在 fork 的 py 和 sh 两条管线里**完全一致**（同一份锁用两次）。
- 下载走 curl → `.partial` → `hashlib.file_digest` 校验 → 原子改名进 `cache/`。
- `extract()` 的**stamp 缓存**：`stamp = 源SHA + repr(strip,members) + sha256(补丁拼接)`；`.source` 文件不匹配就整目录重抽重打补丁——**补丁集变化自动失效**，这是"补丁也是锁定对象"的关键设计。
- `mk-ath11k.sh` 的许可门（sh 版独有）：解出的每个 `ath11k/*.[ch]` 头 6 行必须含 BSD-3-Clause-Clear SPDX 或 ISC 许可原文，否则 `exit 1`——"the licence is checked, not assumed"。

### 1.3 编译机制（`mk-ath10k.py`，flags 全录）

```
clang -target arm64-apple-ios16.5 -mkernel -mgeneral-regs-only -fno-builtin -fno-common
      -ffreestanding -fno-strict-aliasing -funsigned-char -nostdinc -std=gnu17 -O2 -g -w
      -D__FreeBSD__=15 -D_KERNEL -DKLD_MODULE -DHAVE_KERNEL_OPTION_HEADERS
      -include gen/opt_global.h
      -include .../compat/linuxkpi/common/include/linux/kconfig.h -DLINUXKPI_VERSION=70000
      -U__APPLE__ -include wifi/lx/include/lx_prelude.h -include ath10k_prelude.h
      -DCONFIG_ATH10K_SNOC（我们换 -DCONFIG_ATH11K_PCI）
      -DLX_HAKIOS_LX_H=".../bsd/sys/hakios.lx.h"（内核 ABI 头，两侧同编译）
```

- LinuxKPI 头从 freebsd 归档抽 `compat/linuxkpi sys net net80211 ...` 共 38 个路径（strip 2）；`gen/` 里用 awk 跑 `makeobjops.awk`×10 + `vnode_if.awk` hpq 生成方法表，`opt_*.h` 全部 touch 空 + `opt_global.h`=SMP + `opt_inet.h`=INET/INET6。
- Linux 归档只抽 ath 驱动需要的文件（ath10k 全目录 + regd.{c,h} 等 5 个 ath 级文件，strip 5）+ `icnss-bootstrap.patch`。
- 并发 8 线程编译，`.command` 文件记录完整命令行 + `.d` 依赖文件做最小重编，stderr 落 `.err`。
- `crc32_tab` 是**现场生成的 C 源**（256 项查表写进 gen/crc.c）——LinuxKPI 需要它但 FreeBSD 归档不提供。

### 1.4 链接进 XNU 的机制

- `ld64 -r -arch arm64 全部.o → all.o` → `nm -u` 取未定义符号 → **三级门**：① XNU 同名 libc（memcmp…`__stack_chk_guard` 16 名单）放行；② `lx_os_*|qmi_*|hakios_qmi_*|section$` 前缀放行（这是内核 ABI）；③ `ath11k_*|__ath11k_*`（未建部分）**自动生成 stub**（打印自己名字、返回 0，`out/stubs.txt` 留账）——这就是 fork 的"分阶段 bring-up"：跑到哪一步，stub 清单就是 TODO 清单。其它任何未定义 = 构建失败。
- `exported_symbols_list` 只导出 `_lx_prepare/_lx_start/_lx_stop/_lx_transmit` 四名（`hakios.lx.h` 的四入口）。
- `xnu-build.sh`（21 行）：`LX=${WIFI_OBJECT:-$XNUDEPS/build/ath11k/out/ath11k.o}`，有就 `make HAKIOS_OBJECTS="$LX"`；**make 看不见 .o 变化，所以用 mtime 写进 `BUILD/obj/hakios-objects` 戳，变了就删 `BUILD/obj/*/mach.*.unstripped`** 强制重链。

### 1.5 ath10k 侧的假设怎么解（`wifi/lx/ath10k/host.c`，260 行逐条）

raphael 的 WCN3990-SNOC 特定事实全部**硬编码在 host.c**，这是最值得抄的"设备事实清单"写法：

| Linux API | host.c 的回答 | 假设内容 |
|---|---|---|
| `device_get_match_data` | 比对全局 `phone` 平台设备 | `ATH10K_HW_WCN3990, dma_mask 35bit, msa_size 0x180000` |
| `platform_get_resource_byname` | 只认 `"membase"` | SNOC 寄存器窗 `0x18800000-0x18ffffff` |
| `platform_get_irq` | `i<12 ? 446+i : -EINVAL` | 12 路 CE 中断 = SPI 446..457 |
| `of_find_property` | 只造一个 `qcom,msa-fixed-perm` 空属性 | MSA 权限由 ICNSS 预先设好，驱动别碰 SCM |
| `of_reserved_mem_region_to_resource` | 固定返回 `0x8bc00000+0x180000` | MSA 共享内存区恒等映射 |
| `devm_regulator_bulk_get` | **逐名核对 5 路轨**（vdd-0.8-cx-mx/vdd-1.8-xo/vdd-1.3-rfa/vdd-3.3-ch0/ch1），名不对 = -EINVAL | 供电由 ICNSS 持有，这里只"借"状态（`lx_os_radio_powered()`） |
| `qcom_register_ssr_notifier` | 只认 `"mpss"` | MPSS 重启通知 |
| `qcom_scm_assign_mem` | 恒 `-EOPNOTSUPP` | 同上，MSA 权限前置 |
| `lkpi_request_irq` | 446..458 界内映射到 `lx_os_irq_attach` 线程上下文执行 | 中断永不进驱动本体（fork 内核把驱动工作放线程） |
| NAPI 族 | 单 NAPI + ordered workqueue（`ath10k-napi`）+ budget 64 | LinuxKPI 的 napi_schedule 变成 queue_work |
| `lx_start()` | 设 `ATH10K_HW_TXRX_ETHERNET` 帧模式 → `ath10k_snoc_host_register()` → 等 `ATH10K_SNOC_FLAG_REGISTERED`（20s 上限）→ 有 2GHz band 才算 ready → 按 boot-arg 依次 `wifi_scan/wifi_join/wifi_keep` | 验收阶梯就在入口函数里 |

### 1.6 垫层的内核 ABI（`xnu/files/bsd/sys/hakios.lx.h`，105 行）

驱动对象对内核的**全部**索求 = 30 个左右的 `lx_os_*` 调用：内存（alloc/free/**radio_memory**(SMMU 可见)/map_registers）、输出（print/tell/panic）、时间线程锁（nanoseconds/thread/**一锁一条件变量** lock/unlock/sleep/wakeup）、随机、boot-arg 选项（`lx_os_option("wifi_lx")`）、**firmware 按名读取**（`lx_os_firmware(name,&data,&size)`——固件文件名沿 Linux 命名）、rproc boot、radio powered/address/network（SSID+密码由内核注入）、帧通道（net_attach/net_link/net_input）、**MSI 中断**（`lx_os_irq_msi` 拿 address+data → `attach/enable/disable/detach_all/count`，驱动工作全在内核线程）、station ops。**两侧只共享这一个头和 `hakios.sta.h`**，互不见对方头文件。
小陷阱实录：`lx_prelude.h` 必须先 include `<net/mac80211.h>` 再 `#undef WME_AC_*`——FreeBSD 头把接入类别定义成宏，ath11k core.h 又用枚举声明同名，顺序不对就编译冲突。

### 1.7 check-wifi-*.py 判定模式（16 脚本抽 3 个解剖）

- **check-wifi-mdt.py**：从 `hakios.wifi.c` regex 抽 `#define MDT_HASH`…`step_firmware` 全体 + `segment_word/step_image`，镶进 harness，mock `image_file()` 提供 33 段 MPSS 头（含 missing/wrong_size 注错变体），断言解析器对坏段的拒绝。
- **check-wifi-qrtr.py**：抽真实 `qrtr_input/qrtr_close/qrtr_control`，逐字段构造 QRTR v1/v2 包（含 size=UINT32_MAX 溢出注入），断言 peer 锁定、DEL_CLIENT/NEW_SERVER 路由、双重 close 幂等。
- **check-wifi-smmu.py**：抽 `radio_space_find/icnss_smmu_prepare` + 寄存器表，mock `kmem_alloc/rd`，断言 MSA 恒等映射页表。
- 共同收尾：`cc -std=gnu11 -fsanitize=address,undefined` 编译运行，最后一行 `puts("PASS: <覆盖清单>")`，exit code 即判定。脚本 40–159 行/个。

---

## 2. mk-ath11k.py 设计（任务 2 交付）

产物：`wave30-scripts/mk-ath11k.py`（可运行：`--help`/`--dry-run`/`--fetch`/`--verify`/`--build`）。设计原则 = **fork 骨架逐件照搬，设备事实换成 PHK110 的**，编译/链接步按任务书明确拒绝直到内核垫层出现。

### 2.1 ath11k-PCI vs ath10k-SNOC 差异矩阵（管线的差异面）

| 维度 | raphael ath10k（SNOC） | PHK110 ath11k（PCIe/MHI） | 对管线的影响 |
|---|---|---|---|
| 源码位置 | linux tar 内 `ath/ath10k`（子目录抽法一致） | 同树 `ath/ath11k`，**ath11k_pci 是独立模块 = mhi.o + pci.o**（上游 Makefile 实证） | 文件清单 22 个（20 core + mhi + pci）；ath10k 的 snoc.c/qmi_wlfw_v01.c 无对应物 |
| 总线 | 平台设备 0x18800000 寄存器窗 | PCIe0 conf/iatu @0x60000000（DTB reg-names 实证）+ **MHI** | MHI 栈 GPL（§0.4）→ 协议实现住 wifi/lx |
| 中断 | 12 路 level SPI 446..457 | **MSI 经 ITS**（DTB msi-map 实证；`lx_os_irq_msi` 接口就是为此设计） | host.c 的 IRQ 硬编码段整段换掉 |
| 控制 | ICNSS + SMEM/SMP2P + MSA | **CNSS 平台驱动 + QMI WLFW over QRTR-over-MHI**（fork 的 hakios.wlfw.c 545 行 + hakios.qmi.c 是现成参照） | `lx_os_radio_powered()` 语义换成 CNSS 6 路轨+wlan-en GPIO80 序列 |
| 固件 | MPSS PAS 签名装载 wlanmdsp.mdt+bNN（modem DSP 承载） | **WCN6750/hw1.0/{amss.bin,m3.bin,board-2.bin}** 经 MHI BHI 直载，无 PIL | 固件拉取不走 modem 分区；BDF 纪律照抄 fork（拒绝通用 bdwlan.bin） |
| 电源 | 借 ICNSS 状态（5 轨核对名） | 6 路轨（aon/dig/io/rfa1/rfa2/ant-switch）+ wlan-en GPIO 80 + bt-en 81 + sw-ctrl 82（phk110.dts:13446 实证） | check-phk110-wifi-dtb.py 已锁死这些事实 |

### 2.2 本波实跑证据（管线就绪的判定依据）

```
fetch https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.0.14.tar.xz   → 157,262,664 B, SHA256=de9999b7… ✓
fetch https://download.freebsd.org/releases/amd64/15.1-RELEASE/src.txz   → 253,039,000 B, SHA256=cf5762da… ✓
extract (strip 5, 22 成员) → upstream-scratch/build-ath11k/linux-7.0.14/ath11k/
licence gate: 22 files carry BSD-3-Clause-Clear/ISC ✓
compile-plan.json emitted ✓
--build → REFUSED with三条件清单（hakios.lx.h / wifi/lx 实现 / ld64+nm 主机工具）✓
```

### 2.3 上游缺口 = 补丁清单（本波最值钱的一页）

对 staged linux-7.0.14 源码直接读出的三个事实（check-phk110-wifi-mhi.py 自动检测前两个）：

1. **`pci.c` ath11k_pci_id_table 无 WCN6750/QCA6490**（只有 `QCA6390_DEVICE_ID`/`WCN6855_DEVICE_ID=0x1103`/`QCN9074_DEVICE_ID`）→ 补丁 A：加设备 ID + hw_rev 判定分支。PHK110 的 PCI device id 待手机回归后从 PCIe 枚举实测（DTB 不含 PCI id；vendor 侧 qca6490 常见 17cb:1103 系，**此处不下结论**）。
2. **`mhi.c` hw_rev→config switch 无 WCN6750 case**（default 打印 `failed assign mhi_config for unknown hw rev`）→ 补丁 B：`case ATH11K_HW_WCN6750_HW10: ath11k_mhi_config = &ath11k_mhi_config_qca6390;`（WCN6750 的 CE 配置本来就复用 qca6390 表——`core.c` wcn6750 hw_params 里 `host_ce_config = ath11k_host_ce_config_qca6390` 在证；IPCR 通道 = num 20/21、各 64 元素、event_ring 1）。
3. **身份修正链**：`QCA6490` 不是 ath11k hw_rev（core.h 枚举 10 项无它）；固件目录 = `WCN6750/hw1.0`（board_size 256KiB、cal_offset 128KiB、bdf_addr 0x4B0C0000、single_pdev_only）；QMI instance id = `ATH11K_QMI_WLFW_SERVICE_INS_ID_V01_WCN6750`。F14 报告的 "QCA6490/hw1.0 固件族" 命名按此修正。
4. **GPL/MHI 边界**：drivers/bus/mhi GPL-2.0 不进抽取清单；MHI 协议（BHI 引导 + 通道环 + doorbell + IPCR 承载 QRTR）在 wifi/lx 层自实现，参考物 = ath11k/mhi.c 的调用面（`mhi_register_controller/mhi_prepare_for_transfer/mhi_device_get_sync` 等）+ fork lx_bus.c 的"手写总线"先例。MHI 环算术的宿主回归已在 check-phk110-wifi-mhi.py 落地。
5. QMI WLFW 消息 ID **数值**不在 ath11k/*.c（引用自未抽取的内核头/fork 的 qmi_wlfw_v01.c 生成物）——wave31+ 需把 ID 头纳入 SOURCES 再冻结 shim 表；check-phk110-wifi-wlfw.py 已按"查不到就写查不到"处理。

### 2.4 依赖清单与编译命令序列（compile-plan.json 同款）

依赖（主机工具）：curl/tar(xz)/patch/awk + clang（arm64-apple-ios16.5 target）+ 内核 ld64/nm（xnu-deps/setup.sh 产物）。内核侧前置：`bsd/sys/hakios.lx.h`（或我们的同名 ABI 头）+ wifi/lx 移植（lx_os_* 实现 + WCN6750/PCIe/MHI 总线层）+ exported 四入口。命令序列见 `wave30-scripts/upstream-scratch/build-ath11k/compile-plan.json`（extract_freebsd 38 路径 strip2 / compile_each 完整 flags / link ld64 -r + exported_symbols_list）。

---

## 3. check-phk110-wifi 回归范式（任务 3 交付）

五个脚本全部可运行（`--help` + 默认运行，exit 0=PASS/SKIP，1=FAIL），命名与判定对象：

| 脚本 | 判定对象 | 本波实跑 |
|---|---|---|
| `check-phk110-wifi-dtb.py` | phk110.dts 的 wlan/pcie0 节点事实：cnss-qca6490@b0000000、wlan-en GPIO80、bt-en 81、sw-ctrl 82、6 路轨（含 `wlan-ant-switch-supply` 的无 vdd- 前缀变体——写脚本时被真实 DTS 纠正）、rc-num 0、pcie0@1c00000 reg-names 七件套、msi-map | **PASS 21/21** |
| `check-phk110-wifi-fw.py` | `fw-phk110/WCN6750/hw1.0/{amss,m3,board-2}.bin` 门 + SHA256 注册表（本波空）+ **通用 bdwlan.bin 拒绝条款**（raphael BDF 教训）+ QCA6490 旧命名别名捕获 | SKIP×3（预期，零手机） |
| `check-phk110-wifi-mhi.py` | MHI 环算术自检（pow2/门铃回绕）+ staged mhi.c/pci.c 契约（IPCR 20/21、`ath11k_mhi_get_msi` 等真实符号）+ **上游 GAP 自动检测**（§2.3 补丁清单即其输出） | **PASS**（2 GAP 挂账） |
| `check-phk110-wifi-wlfw.py` | qmi.c 指示族（REQUEST_MEM/FW_MEM_READY/FW_READY/COLD_BOOT_CAL_DONE/FW_INIT_DONE）+ 服务 ID/instance + 消息 ID 数值的 TODO-SOURCE 诚实标注 | **PASS** |
| `check-phk110-wifi-e2e.py` | 未来验收门（挂机后启用）：`getvar:wifi-state/wifi-fw/wifi-irq`（loader 通道）+ `kern.hakios.wifi.{scan_done,link,ssid}`（SSH/sysctl，wave22 约定）+ 五级阶梯 driver-attached→fw-ready→scan-heard→joined→frames（rung5 复用 wave27 SSH 门）；零手机时 SKIP | SKIP（dry-run 契约可打印） |

通道约定（真实接口名，来自 wave21/wave27 在库代码）：loader 命令文本 `getvar:<name>` / `oem netmode on|off` / `oem netstat`，帧通道 `upload` / `download:<len-hex>`（`wave21-scripts/loader_talk.py`）；SSH 门 = `wave27-scripts/timed-ssh-v27.py` 相位纪律（ENTRY_GUARD 75s、MSS=160、45s 清洁退出）。e2e 红线：getvar/upload 只读。

---

## 4. nuwaPkg 快查（任务 4 交付，含 F15 情报修正）

克隆：`Project-Silicium/Mu-Silicium` @ main（depth1+sparse，`Platforms/Xiaomi` 子树），`nuwaPkg` 仅 **13 文件**：DeviceBuild.py、FdtBlob/sm8550-xiaomi-nuwa.dtb、Include/{APRIORI,DXE,RAW}.inc、Library/{ConfigurationMapLib,MemoryMapLib}、nuwa.{dec,dsc,fdf}。

**身份（四处互证，F15 §5.3 "Redmi K60/SM8475" 判误）**：`nuwa.dsc` 注释 `# 0 = SM8550-AB / # 1 = SM8550-AC`（SOC_TYPE）；`!include KailuaPkg/KailuaPkg.dsc.inc`（Kailua = SM8550 平台包）；FDT 文件名 `sm8550-xiaomi-nuwa.dtb`；SMBIOS PCD `SystemModel|"13 Pro"` / `RetailModel|"nuwa"`。→ **小米 13 Pro，SM8550（kalama），比我们的 cape/taro 新一代**。

**DXE 覆盖（Include/DXE.inc 全读）**：
- **核心**：CpuDxe/RuntimeDxe/SecurityStub/Watchdog/Capsule/Variable/Metronome/HiiDatabase/ArmGicDxe/TimerDxe/BdsDxe
- **高通平台**：EnvDxe、ShmBridgeDxeLA、TzDxeLA+ScmDxeCompat、ChipInfo、IPCC、PlatformInfo/ProjectInfo、**DALSYSDxe**、HALIOMMU、HWIO、I2C、TLMM、PmicDxeLa、CmdDb、PwrUtils、Rpmh、Npa、ULog、Vcs、Clock、SPMI、ICB、Smem、Rsc、Gpi、SPI、Sdcc、FeatureEnabler、Tsens、Limits、DDRInfo、RNG
- **存储**：**UFSDxe** + DiskIo/Partition/Fat
- **USB**：UsbfnDwc3、XhciPciEmulation+Xhci、UsbBus/Kb/MassStorage、UsbMsd、UsbDevice、**UsbConfigDxe**、UsbInit、UCDxe、UsbPwrCtrl
- **显示**：USE_CUSTOM_DISPLAY_DRIVER=1 → **DisplayDxe（vendor 原生）+ CPRDxe**，配 46 个 panel XML（RAW.inc，true/sharp/boe/r66451/vtdr6130 全系）；否则回退 SimpleFbDxe（1440×3200@32 PCD）
- **按钮/杂项**：ButtonsDxe、ChargerEx、PmicGlink、PIL+PILProxy+SPSS
- 全部 vendor 二进制来自 `Binaries/` 子模块（`Binaries/nuwa/QcomPkg/...`）——**仓库只带胶水，不带 blob**。

**状态标注**：设备包内无 works/partly 状态文件（Mu-Silicium 的设备状态表在 wiki/README 层，未随包入库）；GLinkDxe 一行被注释掉（`#INF ...GLinkDxe`）是包内唯一"未启用"标记；USE_CUSTOM_DISPLAY_DRIVER/SOC_TYPE 是仅有的两个构型开关。

**对 udon 底座的价值（修正后）**：
1. **模板价值（高）**：完整的"Mu 基座 + 设备 Pkg + vendor 二进制子模块"工程范式——phk110Pkg（我们 device-layer 里已有同构骨架）缺什么、binaries 怎么登记、panel XML 怎么 RAW 进 FV，nuwaPkg 是能直接 `stuart_build` 的活样板。
2. **DXE 对照表（中高）**：我们的 UsbConfigDxe/DALSYSDxe 手术对象在 nuwaPkg 里同样在列（同是 QcomPkg vendor DXE 家族），5-patch 清单式对照可行；UsbfnDwc3+Xhci 双栈布局与 wave13/14 经验互证。
3. **不再能说的话**："与 PHK110 同 SoC、可当现成第二 UEFI 基座"（F15 原话）→ **SM8550≠SM8475**，时钟/CNSS/PCIe/内存映射代际不同；作备胎需先过 KailuaPkg→cape 化的移植，工作量不低于我们现在的 udon 路线。真正的同代参考仍是 udon（takasugl 线）与 raphael 的 cepheus（SM8150）式"自研 Pkg + patch"路线。
4. raphael 自己的 UEFI 正是"Mu-Silicium 同族包 + 自带 Pkg + 684 行 patch"起家（F15 已证）——nuwaPkg 的价值在于**方法可抄，底座不可直接换**。

---

## 5. 任务单（留给下一阶段）

| # | 事项 | 前置 | 产物 |
|---|---|---|---|
| 1 | 内核侧 ABI 头落位（仿 `hakios.lx.h` 的 `lx_os_*` 契约；MSI 族按 `lx_os_irq_msi` 保留） | 内核 wave 分支 | `bsd/sys/hakios.lx.h`（WSL 树） |
| 2 | wifi/lx 移植起步：lx_base/锁线程内存 + **WCN6750 PCIe/MHI 总线层**（BHI 引导、通道环、IPCR→QRTR 端点） | #1 | `wifi/lx/src/lx_bus.c` 同位物 |
| 3 | 上游补丁 A/B 入库：pci.c 设备 ID + mhi.c WCN6750 config case（进 `wave30-scripts` 或内核树 patches/） | #2 | `patches/mhi-wcn6750-config.patch` 等 |
| 4 | `mk-ath11k.py --build` 解禁：补 CC 环境探测 + stub 阶梯账本（`out/stubs.txt`）接进 `--verify` 报告 | #1–3 | 首个 `ath11k.o`（哪怕全 stub） |
| 5 | 固件拉取实跑（`pull-firmware` 按本波修正的 `WCN6750/hw1.0` 布局落 `fw-phk110/`），SHA 回填 check-phk110-wifi-fw 注册表 | 手机回归 | fw-phk110/ 3 文件 + SHA 锁 |
| 6 | e2e 门通电：loader 注册 `getvar:wifi-*`、内核注册 `kern.hakios.wifi.*`（名字按本波 e2e 脚本契约） | #4 + 内核 WiFi 首步 | check-phk110-wifi-e2e 从 SKIP 转 PASS 路径 |
| 7 | QMI WLFW 消息 ID 数值源纳入 SOURCES（§2.3-5），冻结 shim 表 | #2 | wlfw id 头 + 回归 |

## 6. 诚实边界

1. fork 的 `check-wifi-*.py` 只解剖了 3/16（mdt/qrtr/smmu）+ 全清单行数统计，其余 13 个按同范式推断——范式判定不依赖它们。
2. `ath11k_mhi_config_qca6490` 独立表在别的树（vendor/ Qualcomm 分支）是否存在未查——本波只对 linux 7.0.14 主线树下判；补丁 B 选 qca6390 表复用有 `core.c` CE 配置复用在证，但**最终以实测 fw-ready 为准**。
3. PHK110 PCI device id（17cb:?）未实测（零手机），§2.3 补丁 A 留白。
4. mk-ath11k.py 的 compile/link 段未真跑（任务书边界 + 主机无 arm64 clang/ld64）；其 flags 与序列是 fork 同款逐字搬运，风险点（WME 宏冲突、crc.c 生成、opt 头集合）已在 §1 记录。
5. QMI WLFW ID 数值未入库（§2.3-5）。
6. nuwaPkg 依据 = 13 文件全文 + 目录清单；Mu-Silicium wiki/README 的设备状态表未读（不在 sparse 子树内），"vendor DXE 全集能用"是结构判断，未构建验证。
7. 上游克隆与缓存全部在 `wave30-scripts/upstream-scratch/`（.gitignore 新增条目，不入库）；`upstream-manifest.txt` 基线（kernel@96ffbc5 等）未动。

## 附录：本波文件清单

- `wave30-scripts/mk-ath11k.py`（骨架管线，可运行）
- `wave30-scripts/check-phk110-wifi-{dtb,fw,mhi,wlfw,e2e}.py`（5 门）
- `wave30-scripts/progress.log`（逐阶段）
- `wave30-scripts/verify-run.log`（--verify 真跑输出）
- `wave30-scripts/upstream-scratch/{raphael-fork,mu-silicium,cache,build-ath11k}/`（不入库）
- `docs/waves/wave30-ath11k-tooling-prep.md`（本文）
