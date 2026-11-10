# USB bulk 端点 "endpoint[2] not configured" 的专项排查

> 2026-11-08 · F12 执行记录 · 本地反汇编（radare2 5.9.8 / WSL Fedora 44）+ 外部调研 · 零手机交互 · 零刷写
> 证据基准：`~/hakios/uefi-udon/Binaries/udon/QcomPkg/Drivers/`（udon = PHK110 平台，只读，反汇编副本在 WSL `~/f12`）
> 地址约定：UsbfnDwc3Dxe.efi / UsbDeviceDxe.efi 均为 PE32+ AArch64，`.text` paddr 0x1000 → vaddr = 文件偏移 + 0x10000。下文全部用 **vaddr**；引用字符串时同时给文件偏移。

---

## 0. 一句话结论

**照片签名四行循环的每一行都已定位到指令级。判据 = `DwcPrepareURB` 读 `EP 表[phys_idx].state@+0x18`，为 0 即打 "physical endpoint[%d] not configured" 并返回 0x8000000C。该 state 只被 `DwcConfigureEP` 置 1；而 bulk（phys[2] = 端点地址 0x01）的武装只发生在 vendor UsbfnDwc 的 ep0 状态机收到 host SET_CONFIG 之后（且前置 DEPSTARTCFG 成功 + speed 字段非 0）。我们 loader 的描述符与 vendor 期望完全一致 —— **修复不在描述符侧**，在"SET_CONFIG 武装链路从未成功执行"这一 vendor 行为侧；loader 侧最优解 = **post-start_ex bulk 探针 + 失败即 stop/start 重掷**（loader.c 小改，建议并入 阶段 21.5）。**

---

## 1. 故障签名逐行归因（照片 ↔ 反汇编）

| 照片行 | 归属 | 证据 |
|---|---|---|
| `UsbDeviceSend: Failed to submit data transfer: Device Error` | **UsbDeviceDxe** `UsbDeviceSend`（fcn.000116d0）：epnum=`addr&0xF`（0x116e4）、dir=`addr>>7`（0x116ec `ubfx w2,w0,7,1`），调 `UsbFn->Transfer`（vtable +0x50，0x116f8→0x11708）；失败打 fmt 0x1a743 + 名字 0x1a76b（"UsbDeviceSend"），%r=EFI_ERROR(Device Error=0x80000007 的可读名) | udon UsbDeviceDxe.efi @0x1172c-0x11744 |
| `DwcPrepareURB:Trb: physical endpoint[2] not configured` | **UsbfnDwc3Dxe** `DwcPrepareURB`（fcn.0001950c）：判据分支 @0x19584-0x19588（`ldr w8,[EP+0x18]; cbz` → 打印 @0x195ec-0x1960c，fmt @0x22f48=`%a:%a: physical endpoint[%d] not configured\n`，%a1="DwcPrepareURB"@0x22ed8、%a2="Trb"@0x22c18 —— 与照片逐字吻合），返回 **0x8000000C**（`mov w8,2; movk 0x8000<<16; add w19,w8,0xa` @0x19610-0x19618） | udon UsbfnDwc3Dxe.efi |
| `UsbfnDwcSubmitUrbNode: PrepareUrb Failed: 0x8000000C` | `UsbfnDwcSubmitUrbNode`（fcn.00015768，名字串 0x21f45）：调 DwcPrepareURB @0x15828，失败打 fmt 0x21f5b=`%a: PrepareUrb Failed: 0x%08x` | 同上 |
| `UsbfnDwcTransfer: Failed to submit transfer` | `UsbfnDwcTransfer`（fcn.000155a8，fmt 0x21b40=`%a: Failed to submit transfer`，名字 0x21cd9） | 同上 |
| `usbDevSsm: Failed to prepare data transfer: 0x8000000B/C` | **我们的 loader**（xnuloader，"usbDevSsm" 为 loader 侧 tag；vendor 两二进制中均无此串）——打印 UsbDeviceSend/Receive 的返回码。**0xC=DwcPrepareURB not-configured；0xB 的确切产生点未定案**（候选：UsbfnDwcTransfer "Cannot find active xfer" 0x21b5f 路径、UsbfnDwcSubmitUrbNode 的 URB 节点分配失败路径 0x21fd6 "no free URB nodes"；两二进制均无 `0x80000002+9` 直译 pattern，0xB 或由 UsbDeviceDxe 上层路径合成——开放微项，不阻塞主结论） | loader.c:3749/3761 |

**物理↔逻辑映射（照片 "endpoint[2]" 正名）**：`phys_idx = epnum*2 + dir`（DwcPrepareURB @0x19548 `add w9, w3, w2, lsl 1`；dir: 0=OUT/RX、1=IN/TX）。**phys[2] = 逻辑 EP1-OUT = 端点地址 0x01**（即我们 loader 的 `USB_EP_OUT`，host→device 方向，fastboot 命令/数据下行端口）。phys[3] = 0x81（`USB_EP_IN`）。WAVE21.2 记录的 "ep2" 即此 phys 编号，不是"2 号端点"。

---

## 2. DwcPrepareURB "not configured" 判据完整伪代码（从指令级提取）

```
// fcn.0001950c @vaddr0x1950c  (usbf 设备结构 ctx; EP 表基 = ctx+0x1f0, 每物理端点 stride 0x20)
EFI_STATUS DwcPrepareURB(ctx, urb, epnum w2, dir w3, xferType w4, totalLen w5, w6, w7):
    if (!ctx || !urb)                    return 0x80000002      // @0x19518-0x1951c
    if ((epnum & 0xff) > 0xf)            return 0x80000002      // @0x19520-28
    if ((dir   & 0xff) > 1)              return 0x80000002      // @0x1952c-34
    if (((xferType-1) & 0xff) > 7)       return 0x80000002      // @0x19538-44 (type 1..8)
    idx = (epnum << 1) + dir                                    // @0x19548
    if (dir == 0 && type == ISO && totalLen % MaxPktOf(idx) != 0)   // @0x1954c-0x19578
        return 0x80000002 + 8            // "total transaction length[%d] not a multiple of..." fmt 0x22ee6
    epState = *(u32*)(ctx + idx*32 + 0x18)                      // @0x19580-0x19584 ★判据字段
    if (epState == 0):                                           // @0x19588 cbz
        DEBUG_ERROR("%a:%a: physical endpoint[%d] not configured", "DwcPrepareURB", "Trb", idx)
        return 0x8000000C                                        // ★照片签名行
    ...TRB ring 填充（@0x19590 起：urb[0..0x14] = epnum/dir/type/len/zlt 等）
    return 0
```

- 该 state 的**唯一置位者** = `DwcConfigureEP`（fcn.00018df0）：入口校验（epnum≤15、dir≤1、epnum<[ctx+9]、trbbuf 非 0、trbsize≥0x30 且 16 对齐、maxpkt≤0x400、trbbuf 16 对齐）→ 读 state（`ldr w8,[x25,0x18]!` @0x18e78）→ **非 0 即打 "already configured"（fmt 0x22d01）并返回 0x80000004**（这就是 "StartEx 先武装 + SET_CONFIG 再武装" 会撞的墙）→ 置 1（`mov w8,1; str w8,[x25]` @0x18f38-0x18f44）。
- 同族旁证（同驱动家族开源重写版）：`~/hakios/uefi-udon/Silicon/Samsung/SamsungPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.c` L527 `if (!Endpoint->Enabled) DEBUG "DWC3: Physical EP %u is not configured"` —— 语义一一对应（Samsung 版用 EFI_NOT_READY，Qualcomm BOOT 版用 EFIERR(12)=0x8000000C）。

---

## 3. ep2（bulk）武装时机图 —— 谁在什么时候配置 bulk

### 3.1 三条武装触发链（全部位于 vendor 栈内，loader 无法直接调用）

**T1 = loader `USB->start_ex()`（唯一入口，UsbDeviceDxe fcn.00011d1c）**
```
UsbDeviceStartEx(descriptor_set):                          // loader.c:3681
  UsbFn->StopController()                                  // [+0x78] @0x11d44
  UsbFn->[+0x70] (=恒返 0 的 stub, fcn.00013300)            // @0x11d54
  UsbDevDescInitDescriptors(&set → 0x1f498/0x1f4a8 全局)    // fcn.00013d18 @0x11d80
  状态复位 + Alloc 16KB（fcn.000120c8 @0x11d90）
  UsbFn->ConfigureEnableEndpointsEx(...)                   // [+0x90] @0x11dac ★全固件唯一调用点
     └ impl fcn.00013868：DEPSTARTCFG(StartNewConfig)（失败 fmt 0x213dc/0x21410 "DEPSTARTCFG Fails"）
        + ConfigureEventBuffer + **只装 ep0 对**（DwcConfigureEP(ep0, dir, maxpkt=0x200 硬编码) @0x13ecc-0x13edc）
        + 控制状态机激活（失败 fmt 0x2153c "Failed to activate control state machine"）
  失败 → "%a: Failed to configure and enable endpoints: %r"（fmt 0x1a8c4）→ loader 打 "usb: start failed %x"
```

**T2 = host SET_CONFIG → UsbfnDwc ep0 控制状态机（bulk 的正牌武装点）**
```
UsbfnDwc ep0 SM（fcn.000165b0）case bRequest==9 @0x1672c:
  speed = dev->[0x184]                                     // 只有 T3 会写非 0 值
  ifaceTable = (speed & ~1) == 4 ? dev->SSinfo[0x1b0] : dev->FSHSinfo[0x1a8]   // @0x16740-0x16754
  cfgInfo->bConfigurationValue([+5]) != wValue → 打印 + 拒绝                 // @0x167c4-0x167cc
  UsbfnDwcSetConfigIfc(dev)                                 // @0x167d4 ★DEPSTARTCFG/StartNewConfig（fcn.00014030，
                                                            //   含 TX FIFO 重分配，失败 fmt 0x215b9/0x215ed）
  逐接口 fcn.00016960(dev, ifcNum, altSetting=0) @0x16808:
     每 EP：epnum=addr&0xF；dir=addr>>7；type=attr&3
     maxpkt = Table[0x20930 + type*0x30 + speed*8]          // @0x16a8c-0x16a90 ★speed 索引！
     UsbfnDwcConfigEndpoints(ctx, epnum, dir, type, maxpkt, ...)  // @0x16a94
        ├ DwcUpdateEPMaxPktSize ×2（fcn.0001925c，写 DEPCFG mps 位）
        ├ DEPCMD SetEPConfig + XferRscConfig（fcn.0001aa10 @0x143c0/0x14420；TRB 0x50B 分配 @0x144f8）
        └ DwcConfigureEP → state=1                          // @0x14548
```

**T3 = ConnectDone 重武装（fcn.00014ed0，名字串 0x21e21）**
```
UsbfnDwcHandleConnectDone:   从硬件读速度 → 表 0x2203c 查值 → dev->[0x184] = speed   // @0x151a8-0x151bc
   （全固件唯一非 0 写入点）→ 随后用 0x20930 表按真速度重走 EP 配置（@0x15210+）
```

### 3.2 maxpacket 速度表（vaddr 0x20930，type×speed，8B/项，`bfi`/`ldr` 直证）

| type \ speed | 0(未知) | 1(LS) | 2(FS) | 3(HS) | 4(SS) | 5(SSP) |
|---|---|---|---|---|---|---|
| control | 0 | 8 | 64 | 64 | 512 | 512 |
| iso | 0 | 0 | 1023 | 1024 | 1024 | 1024 |
| **bulk** | **0** | **0** | **64** | **512** | **1024** | **1024** |

- 表证据：0x20930-0x209c0 hex（0x20990 bulk 行：`0000…/0000…/4000…/0200…/0400…/0400…`）。
- **T1 阶段 speed=0**（CreateUsbfnInstance fcn.00011590 初始化 `str wzr,[x20,0x184]` @0x116fc）→ 若 T1 走到 bulk（经 Ex impl 的 walk），bulk maxpkt = **0** —— vendor 设计上 T1 就不该武装 bulk（impl 只装 ep0 对），bulk 全靠 T2 在 speed 已知后武装。
- 对照开源同族：Samsung 版用 `Dwc3MaxPacketSizeForSpeed(bulk, Dev->Platform.MaximumSpeed)`（**控制器能力上限**，SS=1024，无 speed=0 陷阱）并在 ConfigureEnableEndpoints **一次性装完所有 bulk EP** —— Qualcomm BOOT 版（我们机上跑的）把 bulk 武装推迟到 T2 且依赖协商速度，这就是本故障的结构性脆弱点。

### 3.3 正常 fastboot 会话时序（推断，供对照）

```
loader start_ex ──► T1: DEPSTARTCFG + ep0 对武装 + 描述符表建成 ──► Run/Stop（ep0 可枚举）
host attach ─────► 总线复位 → ConnectDone(T3): dev.speed = 真实速度; 重武装
host SET_CONFIG(1) ──► T2: SetConfigIfc(DEPSTARTCFG) → walk → bulk phys[2]/phys[3] state=1  ✅
loader send(0x01/0x81) ──► DwcPrepareURB state!=0 ──► 正常传输
```
失败 boot（Boot #31-33 签名）：T1 完成（枚举活、描述符全读通）→ **T2 从未成功确定**（speed 未知 / DEPSTARTCFG 翻车 / walk 中断三选一，见 §5）→ bulk state 恒 0 → 每次提交撞 §2 判据 → 0x8000000C 刷屏。

---

## 4. 描述符对照表：我们 loader vs UsbfnDwc 期望

结论先行：**完全一致，描述符侧无罪**。host 能全量读通描述符本身即证明 `UsbDevDescInitDescriptors` + `UpdateDeviceInfo` 接受了我们的描述符集；bulk 提交死在 state 字段，而 state 只由武装链写，与描述符字节无关。

| 项 | 我们（loader.c:3612-3646, efi.h:260-282） | UsbfnDwc 期望（反汇编判据） | 判定 |
|---|---|---|---|
| bulk OUT 地址 | `USB_EP_OUT = 0x01` | `epnum = addr & 0xF`（0x16a84）→ 1；phys = 1*2+0 = **2** | ✅（照片 endpoint[2] 即它） |
| bulk IN 地址 | `USB_EP_IN = 0x81` | dir = `addr >> 7`（0x16a88）→ 1；phys = 3 | ✅ |
| 类型 | attr=2（bulk） | `attr & 3` → 2 → 0x20930 bulk 行 | ✅ |
| maxpacket | HS 512 / SS 1024（cfg 0x00,0x02 / 0x00,0x04） | 表按 speed 取 512/1024；≤0x400 校验（@0x18e50） | ✅ |
| SS companion | 6,0x30,4,0,0,0 ×2 | MaxBurst 字节被读入 DEPCMD 参数（fcn.00016960 @0x16a7c `[x9+2]`） | ✅ |
| config 值 | 1（usb_cfg_desc[5]=1；ss 同） | T2 比对 `bConfigurationValue`（@0x167c4） | ✅ |
| 接口 | 1 个（ff/42/03 fastboot），2 EP | walk 按 `bInterfaceNumber`+`bAlternateSetting` 匹配（fcn.00016960 @0x169c0-0x169d4） | ✅ |
| 设备描述符 | FS 0x0200/64 + SS 0x0300/2^9 + qualifier + BOS(3 caps) + 5 strings | UsbDevDescInitDescriptors/UpdateDeviceInfo 已接受（枚举为证） | ✅ |
| 协议结构体 | `usb_device_descriptor_set`（efi.h:260）= ABL EFIUsbDevice.h 原样 | UsbDeviceStartEx fcn.00011d1c 按同布局读 | ✅ |
| 物理↔逻辑映射 | 我们声明 ep1 对（0x01/0x81） | vendor 无固定映射表，全由描述符 bEndpointAddress 经 `epnum*2+dir` 决定 | ✅ 一致（**改描述符换端点号不解决任何事**：无论 0x01 还是 0x02，T2 没确定就没有 state） |

---

## 5. 根因判定：T2 为什么没确定（三候选 + 证据与排除）

**已排除**：
- ❌ 描述符/映射侧（§4 全表 ✅）——任务书原假设"修复在 loader 描述符"不成立。
- ❌ host 时序（host 侧 set_configuration 被收下、描述符全读通；且 0xB/0xC 为设备侧打印）。
- ❌ 暖态 SUSPHY/CSFTRST（阶段 21.2 v16c 三变体 53f5e077 已证墙恒在）。
- ❌ start_ex 失败残留（F8 zombie 是"USB 服务器不启动"形态；本轮 loader 在跑 UsbDeviceSend = start_ex 已返回 OK = T1 全绿）。

**候选（按可能性排序）**：
- **H1（首要嫌疑）：T2 的 `UsbfnDwcSetConfigIfc`（DEPSTARTCFG）或 walk 中段翻车** —— 与 `UsbConfigDxe start_ex 间歇失败`（Boot #9 遗案）同族：同一 DWC3 core 的 StartNewConfig/DEPCMD 写通道间歇性失败。此路径 vendor 会打 `DEPSTARTCFG Fails`（0x21410）/ `Failed to set config for ep %d, dir %d`（0x2165e）/ `DwcConfigureEP failed for ep %d, dir %d`（0x2170b）——**下一轮 boot 照片若拍到这三行之一即 H1 定案**（四行循环是 loader 周期 flush 的尾部噪声，前导错误行更靠前）。
- **H2：`dev->[0x184] speed == 0` 时 SET_CONFIG 到达**（ConnectDone 的速度写入丢失/未处理）→ walk 用 speed=0 → bulk maxpkt=0（表 §3.2）→ DEPCFG/资源分配以 mps=0 落枪失败 → state 保持 0。特征：可解释 0xB/0xC 交替（两个方向在不同深度失败）。
- **H3：UsbDeviceDxe 层 SET_CONFIG 先被拒**（`Dev_Configured_SetupPkt`→fcn.00012778 case 9 @0x12914：`dev->[0x1f8] speed==0` → 打 0x1b2e1 `"USB_REQ_SET_CONFIG: Unknown USB Speed"`；config 值 > [0x25b]/[0x249] → "New config (%d) out of the range" 0x1b30c）→ ep0 STALL，UsbDeviceDxe **从不**在 SET_CONFIG 调 ConfigureEnableEndpoints（全文件仅 StartEx 一处 `[x0+0x90]` @0x11dac）。host 侧 set_configuration"被收下"可能是 usbipd/Windows 内核侧记账假象。若 H3，则 stall 后下一 SETUP 会清 stall，枚举照常活——与观测吻合。

> 三者的共同点：**bulk 武装唯一通道 = T2，且它单点依赖（speed 字段 + DEPSTARTCFG + 描述符表三重前置）**。任何一环 miss → 本故障。这与 vendor 正常 fastboot（ABL 内建）大概率一致的流程能工作并不矛盾——ABL 的会话是"先插线后起栈"的强时序，我们是"先起栈后插线/插拔不定"的弱时序。

---

## 6. 修复方案排序

### 首选（loader.c 小改，零 vendor 风险，建议并入 阶段 21.5）："bulk 探针 + stop/start 重掷"
T1 之后 loader 自己验墙，发现即重掷（把 v16b 的"start_ex 失败重试"推广为"bulk 死也重试"）：
```c
/* usb_start() 成功路径末尾（loader.c:3691 "usb: started" 前）插入：*/
for (tries = 0; tries < 3; tries++) {
    efi_status s = USB->send(USB_EP_OUT, 0, usb_rx_buf);   /* 0 长度提交 = 纯探针 */
    if (!EFI_ERROR(s)) { USB->abort_xfer(USB_EP_OUT); break; }   /* state=1 → 活 */
    print("usb: bulk not armed (%x), restart %d\n", s, tries);
    USB->stop();
    /* 复用既有 start_ex 全链（含 settle 节奏，≥20s 教训仍然有效） */
    ...重新 locate/start_ex...
}
```
- 依据：探针直接命中 §2 判据（state==0 → 0x8000000C），判定零歧义；`UsbDeviceStop`（vendor 提供，fcn.000116d0 同层）+ 重 start_ex = 重新掷 T1，且**重掷会把 ConnectDone/SET_CONFIG 链整个重来一遍**——对 H1/H2/H3 三种根因都有效或无害。
- 注意事项：①重掷窗口内 host 侧会见到枚举抖动——hunt5 守护（每代际一次手术 + 5s 纯探测）已能容忍；②`USB->send(ep,0,buf)` 0 长度路径需先过 UsbDeviceSend→UsbFnTransfer 的参数校验（`*BufferSize==0 && Buffer==NULL` 型拒绝在 Samsung 版可见 @UsbfnDwc3Dxe.c L511；我们传非 NULL buf，安全）；③探针失败码打印直接取证（0xC=未武装、0xB=其它，失败谱系一目了然）。

### 次选：时序整形（弱时序 → 强时序）
- loader 不在启动期 start_ex，等 host attach（UsbDeviceEventDeviceStateChange Connected）后再 start_ex——对齐 ABL 的"先插线后起栈"强时序，让 T2 到来时 ConnectDone/speed 必然就绪。缺点：无人插线时 USB 服务器永不就绪，与"免手链路"目标冲突；可与首选叠加（先掷，attach 后再掷一轮）。

### 末选（vendor 行为绕过，高风险回退）
- UsbfnDwc3Dxe.efi 字节手术：把 T2 的 speed==0 分支 fallback 到 speed=4（maxpkt 表列强改 SS），或 SetConfigIfc 失败重试。判据均已定位到指令级（§3.1/§3.2），可做但违反"零 vendor 风险"原则——仅当首选+次选双败且照片证据锁定 H2 时考虑。

---

## 7. 外部调研（B 部分结论）

1. **Renegade / edk2-msm**（github.com/edk2-porting/edk2-msm，master 树全量 tree 列举）：**不含 UsbfnDwc3Dxe/UsbDeviceDxe/UsbConfigDxe 任何源码或二进制**（全仓仅 ACPI usb.asl/dsl 7 个文件）——Renegade 的 fastboot/USB gadget 不走 Qualcomm BOOT UsbFn 栈，任务书里"Renegade fastboot DDR 先例"对**本驱动栈**无直接先例可搬。同族二进制包 edk2-msm-binary（Drivers/sm8150/UsbfnDwc3Dxe）同样是裸 vendor blob。链接：https://github.com/edk2-porting/edk2-msm 、 https://github.com/edk2-porting/edk2-msm-binary/tree/main/Drivers/sm8150/UsbfnDwc3Dxe
2. **开源同族实现（最强旁证，本地即有）**：Mu-Silicium 系 SamsungPkg `UsbfnDwc3Dxe.c`（uefi-uke 上游，同为 SamsungPkg 家族）：`PhysEpNum = (addr & 0x0F) << 1 | DIR_IN`、transfer 期 `!Endpoint->Enabled → "Physical EP %u is not configured"`、ConfigureEnableEndpoints 一次装完（含 bulk，maxpacket 用控制器能力上限非协商速度）。链接：https://github.com/TheArchitectEngineer/uefi-uke/blob/main/Silicon/Samsung/SamsungPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.c ；本地镜像 `~/hakios/uefi-udon/Silicon/Samsung/SamsungPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.c`（只读引用）
3. **精确字符串检索**（"UsbfnDwcSubmitUrbNode"/"physical endpoint not configured"/0x8000000C）：公开网络零命中——BOOT.MXF vendor 代码无 NDA 外泄漏文本，社区 issue/commit 无同型报告（edk2-msm issues 62 open 亦无）。此签名应为我们首发。Linux 侧同型概念参照（物理端点 = 2*epnum+dir）：https://docs.kernel.org/6.2/driver-api/usb/dwc3.html 、LKML dwc3 端点方向补丁 https://lkml.iu.edu/hypermail/linux/kernel/2109.0/04564.html
4. **Qualcomm UsbfnIo.h 语义**：EFI_USBFN_IO 为 Microsoft USB Function 标准 + Qualcomm 私有扩展（本机型协议 vtable 19 槽，'usbf' 签名，消费侧偏移 = 基址-8）；MS 官方文档对 ConfigureEnableEndpoints 的标准语义 = "prepare the USB controller for all endpoints of the supplied configuration"——Qualcomm BOOT 版把它弱化为 ep0-only（bulk 推给 SET_CONFIG/ConnectDone），属 vendor 私有改道。MS spec：https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/ （EFI_USBFN_IO_PROTOCOL 族页）

---

## 8. 证据索引（关键 file:offset 速查）

**UsbfnDwc3Dxe.efi（udon，98,304B，vaddr=文件+0x10000）**
- DwcPrepareURB = fcn.0001950c；判据 `ldr w8,[x8,0x18]` @0x19584 + `cbz` @0x19588；打印 @0x195ec-0x1960c；返回 0x8000000C @0x19610-0x19618
- 物理端点公式 @0x19548；DwcConfigureEP = fcn.00018df0（state 读 @0x18e78，置 1 @0x18f38-0x18f44，"already configured" 返回 0x80000004 @0x18ea0-0x18eac）
- UsbfnDwcConfigEndpoints = fcn.00014238（DEPCMD 参数 bfi maxpkt@bits35-45 @0x14340；SetEPConfig/XferRsc @0x143c0/0x14420；TRB 0x50 @0x144f8；DwcConfigureEP 调用 @0x14548）
- ep0 SM = fcn.000165b0（case 9 → 0x1672c；speed 门 @0x16740-0x1674c；表 0x1a8/0x1b0 选择 @0x16750/0x167b0；SetConfigIfc @0x167d4；walk @0x16808）
- 描述符 walk = fcn.00016960（speed 分支 @0x1697c-0x1698c；epnum/dir/type/maxpkt 提取 @0x16a7c-0x16a90；表 0x20930 @0x16a8c）
- maxpkt 速度表 @0x20930（bulk 行 0x20990：speed0=0）；UsbfnDwcHandleConnectDone = fcn.00014ed0（速度写 @0x151bc，源表 0x2203c @0x151a8）
- 协议 vtable 装配 @0x115c8-0x116b8（CreateUsbfnInstance fcn.00011590；'usbf' 签名 +0x00；消费侧指针=基址+8；Transfer=消费+0x50=0x130bc；ConfigureEnableEndpointsEx=消费+0x90=0x12580）
- 速度初始化 0 @0x116fc；fcn.0001ec28 = `mov w0,wzr; ret`（恒 0）

**UsbDeviceDxe.efi（udon，69,632B）**
- UsbDeviceSend = fcn.000116d0（epnum @0x116e4；dir bit7 @0x116ec；UsbFn+0x50 @0x116f8）
- UsbDeviceStartEx = fcn.00011d1c（唯一 ConfigureEnableEndpointsEx 调用 @0x11dac；"Failed to configure and enable endpoints" fmt 0x1a8c4 @0x11dc0）
- 标准请求分发 = fcn.00012778（jump 表 0x1ad88；case 9 @0x12914；speed==0 → "Unknown USB Speed" 0x1b2e1 @0x12958；config 越界 0x1b30c @0x12978-0x12988；**此处不武装端点**）
- Dev_Configured_SetupPkt = fcn.000131d8；UsbDeviceDxe speed 字段 [dev+0x1f8]：写 @0x12e88、清 0 @0x12628/0x130fc

**loader（Windows 仓，read 参照）**
- `upstream/hakios-xnu-kernel/xnuloader/loader.c`：3612-3646（端点/描述符）、3681（start_ex）、3749/3761/4024（send(0x01)/send(0x81)）
- `upstream/hakios-xnu-kernel/xnuloader/efi.h`：249-286（协议结构/GUID，= ABL QcomModulePkg EFIUsbDevice.h 镜像）

**同族开源旁证**
- `~/hakios/uefi-udon/Silicon/Samsung/SamsungPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.c` L180-245（ConfigureEnableEndpoints 全装含 bulk）、L511/L527（Transfer 判 `Endpoint->Enabled`）

---

## 9. 交给阶段 21-5 的三行清单

1. loader.c 加 "bulk 探针 + stop/start 重掷"（§6 首选，~20 行）：探针失败码即 H1/H2/H3 在线判别器（0xC 恒在=武装链全死；0xC→成功=重掷治愈；失败码在 0xB/其它间漂移=另一层问题，回填本档 §1 表）。
2. 下一轮 boot 照片检索 vendor 前导错误行：`DEPSTARTCFG Fails` / `Failed to set config for ep %d, dir %d` / `DwcConfigureEP failed` / `USB_REQ_SET_CONFIG: Unknown USB Speed` —— 任一出现即根因定案（§5）。
3. 描述符侧**不改**（§4 全绿）；"此修复属 loader.c 小改"标注成立——但改的是**时序/重掷逻辑**，不是描述符字节。
