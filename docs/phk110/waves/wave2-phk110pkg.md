# Wave2 报告：phk110Pkg（UEFI 平台包）文件构造

实现代理 D · 2026-11-02 · 按规格书 `docs/waves/wave1-phk110pkg-spec.md` §9 顺序机械执行。
模板 = 上游 `Platforms/Xiaomi/ingresPkg`（Mu-Silicium BASE e51cd87，HEAD 6b3d90b），内存数据 = `docs/waves/wave1-socargs.md` + `intel/fdt-reserved-dump.txt` + `intel/iomem-full.txt`（FDT 全文反编译复核过）。

---

## 1. 交付清单（全部落地）

### WSL `~/hakios/kernel/devices/phk110/uefi/files/`（17 个文件）

```
Binaries/phk110/README.md                       git 可见唯一 Binaries 文件（来源/风险/补丁候选）
BootShim/BootShim.S                             设备覆盖：hakios.patch 版 + PAYLOAD_BASE 缺省 0xC0000000
Platforms/OnePlus/phk110Pkg/
  phk110.dec                                    0 字节
  phk110.dsc                                    GUID FC404216-2E78-44CB-B3E3-FF90E329B77B（uuidgen 新生成）
  phk110.fdf                                    纯改名 + 注释内 DTB 模板路径中性化
  DeviceBuild.py                                8 处字符串改名（PackagesPath: Platforms/OnePlus）
  Include/{APRIORI,DXE,RAW}.inc                 仅 Binaries/ingres/→Binaries/phk110/ 机械替换（50/50/44 处）
  Library/MemoryMapLib/{MemoryMapLib.c,.inf}    .inf 纯复制；.c 见 §2（本任务核心工作量）
  Library/ConfigurationMapLib/{*.c,*.inf}       纯复制（规格 §6.6：v1 原样，SharedIMEM 0x146AA000 经 DT 复核正确）
Resources/Configs/phk110.toml                   base=0xA7100000 size=0x300000 gzip append_dtb header_version=1
Resources/DTBs/phk110.dtb                       = intel/phk110-fdt.dtb（1,200,263 B）
Resources/DTBs/phk110.dts                       dtc 反编译（41,820 行）
Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h
                                                设备覆盖：XNU_PAYLOAD_BASE 0xC0000000（其余与全局版一致）
```

### WSL `~/hakios/Mu-Silicium/Binaries/phk110/`（本地填充，不 commit）

- `cp -r Binaries/ingres/.`：**321 → 322 文件（+README.md），9.3MB，文件清单 diff 除 README 外逐项相同，无嵌套 .git**。
- 未动 XBLCore（"完整复制"，规格 §6.11 标注可留可删）。

### Windows `docs/waves/wave2-phk110pkg.md`

本报告。

---

## 2. 内存映射定稿（MemoryMapLib.c，45 行描述符）

对拍脚本重放 Silicium `ValidateMemoryMap`（0x80000000 以上两两不重叠）+ 全行落点对 DT `/memory` 五段、DT reserved-memory 41 节点、非 RAM 段 0xEA000000-0xF13FFFFF 交叉验证：**PASS**（脚本按生成后的 .c 文本重新解析，不是手抄表）。

### 2.1 占位符 P-1~P-7 的最终解答

| 占位符 | 规格预期 | 最终值 | 依据 |
|---|---|---|---|
| P-1 FD_BASE | 低 4G 空闲 ≥14MB 窗 | **0xA7100000（=ingres 原值，不搬迁）** | wave1 数据出来后实证 PHK110 的 0xA7000000-0xA7FFFFFF 是 System RAM（iomem 段 6），整簇可原位保留 → 无需"整块搬迁"，风险归零 |
| P-2 XNU_PAYLOAD_BASE | 0xE5700000-0xE87FFFFF 内 64MB 对齐 | **0xC0000000 / 0x04000000（64MB）** | 见 §2.2；规格候选窗口装不下 64MB |
| P-3 STACK | 由 FD 簇推导 | **0xA760D000（=ingres 原值）** | FD 簇原位保留，机械推导即恒等 |
| P-4 reserved-memory 各行 | 按 DT 重算 | PIL Reserved **0x85700000/0x1AD00000**（Cape carve 精确端点 0x85700000-0xA03FFFFF，含 adsp/slpi/cdsp/ipa/mpss 306MB/cvp/camera/video）；新增 **TME 0x808A0000/0x54000**、**CPUCP 0x80B00000/0x100000**、**CDSP Secure Heap 0x80C00000/0x100000**（Cape 独有，模板图上是空洞）；**HYP Reserved 缩为 0x830000000/0x8300000**（Cape /memory 第三段止于 0x8382FFFFF，wave1 的"高 bank 唯一孔洞 8.25MB"实为 125MB 算术误差，已按 DT 修正）；**MTE Reserved 整行删除**（Cape DT 无任何 MTE/tag-storage 节点） |
| P-5 Display Reserved | 按 non_secure_display_region size=0xA400000 必改 | **保留 0xB8000000/0x2B00000（=DT splash_region/cont_splash 精确同址）** | 偏离规格：`non_secure_display_region` 在 Cape DT 无 reg（动态 shared-dma-pool），无法固定地址预留；SimpleFb 路径只需要 cont_splash（SimpleFb.c 直接用本行地址 + dsc PCD）。尺寸之争留给将来翻回厂商 DisplayDxe 时再议 |
| P-6 IMEM/Cookie | soc_imem=0x14600000 | **IMEM Base 0x14600000/0xAA000**；**Cookie 0x146AA000/0x16000 不变** | soc_imem 是 msm-imem 节点地址 2MB 向下取整（soc-args.py:132-134）；DT 实证 `/soc/qcom,msm-imem@146aa000` + `tz-log@146AA720` → ConfigurationMapLib 的 SharedIMEMBaseAddr=0x146AA000、PilSubsysDbgCookie=0x146AA6DC（=pil@6dc 偏移）**逐位吻合，无需改动** |
| P-7 AOSS/MMIO 微调 | AOSS=0xC300000 | **AOSS 行保持 0x0B000000/0x4000000 伞形**（覆盖 0xC300000 及 0xB000000-0xEFFFFFF 全部外设：spmi/thermal/ipcc/rsc drv-0）；QUP/USB/TLMM(=pinctrl@f000000 精确)/SMMU(=apps-smmu@15000000 精确)/APSS_HM(含 rsc@17a00000 drv-2=0x17a20000、cpufreq) 全部经 iomem 对拍一致，不变 |

### 2.2 XNU Payload = 0xC0000000/64MB 的依据（写进了 .c/.h/.S 三处注释）

1. **真 RAM**：DT `/memory` 段 0x80000000+0x6A000000 内；iomem System RAM 段 0xA7000000-0xE05FFFFF 内；16GB SKU /ddr-regions region0 内。该范围内 **无任何 DT reserved-memory 节点**（41 节点全查）。
2. **不与硬保留重叠**：下方 OEM VM 行止于 0xBFFFFFFF，上方 qhee/TrustZone-VM 簇（VM PIL 行）起于 0xE0000000；TZ 三件套 tz_stat(0xE8800000)/tags(0xE8900000)/qtee(0xE9B00000) 完全避开。
3. **为什么不是任务书示例 0xE6000000**：0xE5700000-0xE87FFFFF 空窗只有 49MB，唯一的 64MB 对齐基址 0xE6000000 会跨进 tz_stat/tags/qtee（TrustZone 所有，写入即事故）；且 0xEA000000-0xF13FFFFF 在 Cape DT 里根本被 /memory 除名（非 RAM）。
4. **为什么不是全局/redwood 的 0xF0000000**：同上第 3 点，落在除名段内，无 RAM。
5. **约束满足**：64MB 对齐（BootShim.S `movz #(PAYLOAD_BASE>>16),lsl#16` 要求低 16 位清零，已反汇编验证 `mov x5, #0xc0000000`）；维持 XNU_PAYLOAD_MAX_SIZE=0x04000000 与全局一致（kernel 侧 loader.c 的 MAX 常量不用改，只改 BASE）。
6. **来源**：顶替被删的 MTE Reserved 行位置（0xC0000000 起），该行 Cape 无对应保留。

### 2.3 高位 bank 三行（规格 §6.8 清单之外、但必须加）

MemoryInitPeiLib 只给**表内**行建资源 HOB —— 不列高 bank，DXE 分配器与 XnuLoader 的 choose_window 就永远看不到 13.9GB，XNU 内存窗会卡死在低 bank 小块（wave1-socargs §5b 预期窗口 0x840000000+6GB 将无法成立）。故按 DT /memory 精确补：

- `High RAM 0x800000000/0x3000000`（Conv）
- `HYP Reserved 0x830000000/0x8300000`（Reserv，缩到 DT 真实 RAM 端点 0x8382FFFFF）
- `XNU Bank 0x840000000/0x34000000`（Conv，13GB 主段）

同族先例：redwood 实跑 physBase=0x800000000 亦要求高 bank 进入 UEFI map。

---

## 3. 设备级覆盖文件（规格 §6.12）

| 文件 | 全局版 | 设备版差异 |
|---|---|---|
| `Silicon/.../XnuLoader.h` | XNU_PAYLOAD_BASE 0xF0000000 | **0xC0000000ULL** + 8 行依据注释；MAX_SIZE/MAGIC/结构体逐字节同全局 |
| `BootShim/BootShim.S` | hakios.patch 版（`#ifdef PAYLOAD_BASE` 参数化拷贝块） | 同一 patch 内容 + **`#ifndef PAYLOAD_BASE` 缺省 0xC0000000**。事实修正：拷贝目标是 mkxnuimg 的 `-DPAYLOAD_BASE` 编译期 define，不是源内常量；缺省值保证 phk110 树漏传 flag 时 shim 仍指向正确地址，显式传参时 `#ifndef` 让位 |

烟测（clang aarch64，两种模式）：`REQUIRES_KERNEL_HEADER=1 + -DPAYLOAD_BASE=0xC0000000` 与仅 `FD_BASE/FD_SIZE`（走缺省）**均汇编通过**，产物反汇编 `mov x5, #0xc0000000` 正确。

副作用说明（有意为之）：build_uefi.py 的 UEFI-only BootShim（不传 PAYLOAD_BASE）现在也会编入 XNUP 探测块——FD 后读 8 字节、仅 magic==0x50554E58 才动作，纯 UEFI 镜像上无 payload 段，误判概率可忽略且动作无害（拷到预留区）。redwood/其他设备不受影响（apply.sh 按设备单树工作）。

---

## 4. 与规格书的全部偏离（含理由）

| # | 偏离 | 理由 |
|---|---|---|
| 1 | P-2 payload 落点改为 0xC0000000，不在任务书给的 0xE5700000-0xE87FFFFF 窗内 | 窗口 49MB 装不下 64MB；唯一 64MB 对齐基址撞 TZ。wave1 的 fdt-reserved-dump 是更细的新证据（tz_stat/tags/qtee 逐节点） |
| 2 | §6.8-3 "FD 簇整块搬迁"未执行，原位保留 | wave1 数据实证原址即空闲 System RAM；搬迁无收益只有算错风险。P-1/P-3 因此恒等 |
| 3 | P-5 Display Reserved 未改 0xA400000 | non_secure_display_region 无固定 reg；cont_splash 精确同址 0xB8000000/0x2B00000，SimpleFb 语义恰好需要它 |
| 4 | 新增高 bank 三行（§6.8 未列） | 不加则 13GB 不可用（MemoryInitPeiLib 只按表建 HOB），loader 6GB 窗无法成立——是 wave1-socargs §5b 结论的硬件前提 |
| 5 | 删除 MTE Reserved 行（而非缩容） | Cape DT 无 MTE 节点；缩容留 64MB 是编造值，删除是 DT 诚实解；该位置由 XNU Payload 顶替 |
| 6 | BootShim.S 覆盖以 `#ifndef` 缺省而非替换常量 | PAYLOAD_BASE 本是编译期 define（全局 hakios.patch 亦然）；覆盖文件补缺省值，机制不变 |
| 7 | MTE/新增行在 grep 禁词之外引入 "TME/CPUCP" 命名 | DT 节点名直译（tme_*, cpucp_fw, cdsp_secure_heap），与 redwood 的 CPUCP 行命名惯例一致 |
| 8 | grep 禁词校验存在 4 处例外（见 §6） | dsc/fdf 的 `ingres/AcpiTables.inf` 是规格 §6.2/6.3 明文要求保留（ACPI 复用，V-8 验证存在性）；Binaries README 的来源标注是 §6.11 交付要求本身 |

未偏离项重申：`!include WaipioPkg/WaipioPkg.dsc.inc`、`PcdSystemMemoryBase 0x80000000`、`PcdPlatformType "LA"`、`USE_CUSTOM_DISPLAY_DRIVER=0`（SimpleFb；salami=OnePlus SM8475 同为 0 的先例）、`[Components] ingres/AcpiTables.inf`、DXE/APRIORI 41 INF 与 RAW 44 项零增删、DeviceBuild.py 六子模块清单不动。

---

## 5. 给 Wave3 集成者的占位符/待验证清单

### 已定稿常量（改任何一处都要三处同步：MemoryMapLib.c / XnuLoader.h / BootShim.S 缺省 + mkxnuimg 变体）

| 常量 | 值 |
|---|---|
| FD_BASE / FD_SIZE（toml + fdf 变量 + shim） | 0xA7100000 / 0x300000 |
| XNU_PAYLOAD_BASE / MAX | 0xC0000000 / 0x04000000 |
| PcdCPUCoresStackBase | 0xA760D000（=MemoryMapLib "UEFI Stack"） |
| FB PCD（V-1） | 1240 × 2772 × 32 |
| PLATFORM_GUID | FC404216-2E78-44CB-B3E3-FF90E329B77B |

### 内核仓全局文件需要 phk110 化（不在本代理文件域，未动）

1. `xnuloader/loader.c`：第 18 行 `PAYLOAD_BASE 0xF0000000ULL`（还有同族 MAX 常量与 PANIC_LOG_BASE 派生）→ 需按 0xC0000000 改或参数化（build.sh 加 `-DPAYLOAD_BASE`）。
2. `mkxnuimg.py`：硬编码 redwood 四件套（FD_BASE=0x9FD00000, FD_SIZE=0x200000, PAYLOAD_BASE=0xF0000000, PAYLOAD_MAX=0x4000000, dtb=redwood.dtb, 输出名）→ 需 phk110 变体（0xA7100000/0x300000/0xC0000000/0x4000000/phk110.dtb）。
3. `tools/provenance.allow` 追加两行（规格 §6.13）：
   `pending devices/phk110/uefi/files/Resources/DTBs/phk110.dtb ...`
   `vendor  devices/phk110/uefi/files/Binaries/phk110/* ...`
4. `devices/manifest.conf`：开源后再登记（本地开发不需要）。

### V-1~V-8 状态与新增验证点

| 项 | 状态 |
|---|---|
| V-1 FB 1240×2772×32 | 首跑 logfs 回读 GOP mode 行确认（dsc 已按规格写死） |
| V-2 payload 窗 | **已按新证据解决**（0xC0000000），首跑验证 loader 打印 payload base=magic 正常 |
| V-3 设备覆盖生效 | apply.sh 拷贝顺序已保证；apply 后 `diff devices/phk110/uefi/files/Silicon/.../XnuLoader.h Mu-Silicium/Silicon/.../XnuLoader.h` 应为空 |
| V-4 ConfigurationMapLib ingres 值 | 首跑日志看 SharedIMEM cookie 校验（0x146AA000 已被 DT msm-imem@146aa000 佐证，风险低） |
| V-5 venv py3.14 | 未动（构建链由集成者执行 §7）；失败预案 python3.13 |
| V-6 FD 簇原位保留后 RamManager/PlatformPei | 风险较原方案更低（零地址搬迁），首跑看 build report FIXED_ADDRESS + 日志 |
| V-7 UsbConfigDxe 去 deinit 补丁 | 首跑 logfs 通道验收，必要时按 §6.7 打补丁 |
| V-8 Silicium-ACPI 含 Platforms/Xiaomi/ingres | **关键**：dsc/fdf 复用 `ingres/AcpiTables.inf`，apply.sh 后 `ls Silicium-ACPI/Platforms/Xiaomi/ingres/` 必须有 AcpiTables.inf/SSDT.asl/SSDT.aml，否则构建即失败 |

### 环境注意

- Mu-Silicium 树内 `Mu_Basecore` 有**本任务之前就存在**的本地补丁脏文件（ArmGenericTimer\*、BootManagerMenuApp、UsbBus.h、AuthService.c 等 9 文件，非本代理所改，未触碰）；`M Binaries` 是预期的（子模块内未跟踪的 phk110 目录，规格 §5-2 已预料）。
- 构建前置照规格 §7：dnf 装 nasm/gcc-aarch64-linux-gnu、子模块 init、venv、mu_nasm 垫片。
- 注意：`wsl bash -lc` 传多行脚本会折行，本次全部走 `/mnt/c/.../intel/wave2-scripts/*.sh` 脚本文件执行（gen_platform / fix_dsc / gen_memmap_overlay / gen_binaries / verify_gen / check_consistency / smoke_bootshim / final_sweep，均可复跑）。

---

## 6. 验收自查证据（摘录）

1. **全清单**（`find ~/hakios/kernel/devices/phk110/uefi -type f | sort`）：17 文件，见 §1 树形；无多余产物。
2. **模板 diff 逐行复核**：phk110.dsc 对 ingres.dsc 的 diff 恰为规格 7 处（NAME/GUID/OUTPUT/FLASH/DISPLAY flag/SMBIOS×5/FB×2/Lib 路径×2）；DeviceBuild.py diff 恰为规格 8 处；fdf diff 仅注释内 DTB 路径 1 行；三个 inc 的 Binaries 路径替换计数 50/50/50→50/50/44，residual=0。
3. **INF/RawFiles 存在性**（规格 §6.7 自检，cwd=Mu-Silicium 根）：`unique INFs referenced: 51; missing: 0`；`unique RAWs referenced: 44; missing: 0`。
4. **payload 三处一致**：XnuLoader.h:17 `XNU_PAYLOAD_BASE 0xC0000000ULL`；BootShim.S:25 `#define PAYLOAD_BASE 0xC0000000`；MemoryMapLib.c:65 `{"XNU Payload", 0xC0000000, 0x04000000, ...}`；BootShim 反汇编 `mov x5, #0xc0000000`。
5. **FD/Stack 一致**：MemoryMapLib "UEFI FD" 0xA7100000/0x300000 == toml base/size；"UEFI Stack" 0xA760D000 == dsc PcdCPUCoresStackBase。
6. **内存对拍**：从生成后的 MemoryMapLib.c 反解析 45 行，ValidateMemoryMap 仿真 + DT 五段 /memory + 41 reserved 节点 + 非 RAM 段交叉 → `result: PASS`。
7. **禁词扫描**：全树 grep -i "bitra|ingres|poco|realme" 仅 4 行命中且全部为文档化例外（dsc:78、fdf:96 的 ACPI 复用路径；Binaries README 两行来源标注）。
8. **Binaries 对比**：ingres 321 文件/8,693,679B vs phk110 322 文件/8,695,482B（+README.md），文件清单 diff 相同，嵌套 .git=0。
9. **TOML 合法性**：tomllib 解析 `{'boot_shim': {...True}, 'uefi_fd': {'base': 2802843648(=0xA7100000), 'size': 3145728(=0x300000)}, 'boot_image_kernel': {...}, 'boot_image': {'header_version': 1}}`。
