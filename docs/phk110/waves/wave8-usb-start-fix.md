# Wave 8 — loader `usb_start()` PHK110 失败根因 + usbmode 驻留镜像 v3

Date: 2026-11-03. Agent: Wave 8 (全程未碰手机; WSL 静态分析 + 构建)。目标：修掉 Boot #9 的根因
—— usbmode 镜像里 loader 的 `usb_start()` 在 PHK110 上失败 → 无内核可跑 → 立即复位 → slot b 引导
循环 → ABL fallback fastboot。交付 `udon-hakios-usbmode-grafted-v3.img`。

## Result summary

| Artifact | Path (Windows `device-layer/`) | Size | SHA-256 |
| --- | --- | --- | --- |
| **Flashable image (deliverable)** | `udon-hakios-usbmode-grafted-v3.img` | 201,326,592 B (192 MiB) | `b60964c729bd77e93e586da93bf4882fcb6386b166995817eb88bd8f78ceadf1` |
| loader.efi (usb_start 重试修复) | `udon-hakios-loader-usbmode-v3.efi` | 66,560 B | `9a37b99af31d15f265dd36457fa50e99c6c2ebd43d1df2cc85e1d4a799b7af13` |
| XNUP payload (usb-mode) | `udon-hakios-payload-usbmode-v3.bin` | 66,728 B | `7f7fe8b763ec64b61553396bfa89a06514821b3cb4d71789a3ad0d72978d04da` |
| 打包报告 | `udon-hakios-usbmode-grafted-v3.report.json` | 1,656 B | `53fa99ab0b3990531eeabc2b92dd363848dd89c1bb60dbb9e2853fe686d053f2` |
| udon FD（**未重建**，Wave7 产品原样） | `~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` | 4,194,304 B | `8924cb67e349f7c188c258bde08fe90155d81a9d27ef5d0a965399ffb7a7180f` |
| BootShim（未动，Wave5） | `udon-hakios-BootShim.bin` | 240 B | `108ce972adb82cc9c23967a1d380a27a67ef73a7c131f117561e38e261fa58ba` |

`~/hakios/kernel` 改动：**仅 `xnuloader/loader.c` +76/−8**（`usb_start()` 一个函数；qemu/redwood/phk110
平台条目零触碰）。与 Wave7b 的 write_logs 区（~3609-3638 行）无重叠；本 wave 构建时其改动尚未落盘
（`git diff --stat` = +76/−8 全部为 usb_start），两者叠加后重跑 §4 命令即可合并产出。

---

## 1. `usb_start()` 依赖清单与逐项核对（任务书问题 1/2）

**结论先行：`usb_start()` 是纯 UEFI 协议驱动的，没有任何写死的寄存器/时钟/PHY/中断地址。**
`platform` 结构里也没有也不需要 USB 字段——所以任务书假设 (a)"用了 redwood/qemu 写死地址" 和
(b)"platform_phk110 缺 USB 字段" 都**不成立**（逐项核对表如下）。redwood/QEMU 上它能工作靠的是
固件侧同一套 Qualcomm vendor 驱动（EFI_USB_DEVICE_PROTOCOL 提供方），loader 只是客户端。

| usb_start 实际依赖 | 来源 | PHK110 (taro/cape) 实际值 | 核对 |
| --- | --- | --- | --- |
| `QCOM_USB_DEVICE_GUID` {D9D9CE48-…} 协议（EFI_USB_DEVICE_PROTOCOL，start_ex/send/handle_event/allocate_transfer_buffer） | 固件驱动 `Binaries/udon/QcomPkg/Drivers/UsbDeviceDxe`（depex 仅 SMEM） | udon.fdf DXE.inc:100 已装入 FD | ✅ 在（Boot #9 至少一次走到 start_ex 并枚举成功过） |
| `QCOM_USB_INIT_EVENT_GUID` {1C0CFFCE-…} 事件组（= QcomPkg.dec `gUsbControllerInitGuid`） | 固件驱动 `UsbConfigDxe`（其 .data @0x17048 持有该 GUID，注册回调 `UsbConfigStartControllerCb`） | udon.fdf DXE.inc:101 已装入（用 `UsbConfigDxe.patched.efi`，见 §3.4） | ✅ 在 |
| 时钟/PHY/电源初始化 | 固件驱动 `UsbInitDxe`（EFI_USB_INIT_PROTOCOL）+ `UsbPwrCtrlDxe` + RPM/DAL | udon.fdf DXE.inc:85/102 已装入；UsbfnDwc3Dxe 二进制内建路径串 `BOOT.MXF.2.0/boot_images`（taro 代 XBL 源码树，SoC 代际正确） | ✅ 在（但初始化**何时跑完**正是本 wave 根因，见 §3） |
| DWC3 控制器本体 | 固件驱动 `UsbfnDwc3Dxe`（EFI_USBFN_IO_PROTOCOL，driver-binding） | a600000.dwc3 @0x0A600000（FDT/iomem 实证，与 XBL 同款驱动一致） | ✅ 在 |
| 描述符/BOS/字符串 | loader.c 内 `usb_dev_desc` 等（VID:PID 18d1:d00d，product "xnuloader"） | 无平台相关性 | ✅ |
| 传输缓冲 2×1 MiB | `allocate_transfer_buffer`（固件分配） | — | ✅（Boot #9 未报此错） |

**任务书问题 1 的答案**：usb_start 依赖的全部"平台数据"都在固件侧（udon FD 的 vendor USB 驱动栈），
loader 侧唯一平台相关的是选台用的 FB 基址（0xB8000000，Wave6 已核）。**问题 2**：无需逐地址核对
FDT/iomem——loader 从不直接摸 DWC3/PHY 寄存器。

## 2. Boot #9 失败时序重构（实证部分）

链条（全部源码/二进制实证，标注见括号）：

1. ABL → shim → udon FD（0xA7100000）→ DXE dispatch：UsbPwrCtrl/UsbfnDwc3（binding 注册）→
   **UsbDeviceDxe entry** → **UsbConfigDxe entry**（ChipInfo+PlatformInfo+SMEM depex 后）→ …
   到此为止**没有任何人摸过 DWC3 硬件**（UsbfnDwc3 是 driver-binding，实例要等 ConnectController；
   修 xBL 上由 XBL BDS 触发的 `gUsbControllerInitGuid` 事件负责这一步）。
2. `BdsEntry`：`PlatformBootManagerBeforeConsole` → 驱动项 → **connect consoles** →
   `PlatformBootManagerAfterConsole`（`SiliciumPkg/Library/BootManagerLib/BootManager.c:129`，
   Wave7 graft）→ **`XnuLoaderMain()` 在这里直接进 loader**。
3. 关键时序事实：stock 固件里给 USB 供电开钟的事件 `gUsbControllerInitGuid` 是由
   `DeviceBootManagerOnDemandConInConnect`（ConIn 懒连接回调，`Mu_Basecore BdsEntry.c:72`）触发的——
   **graft 抢在它之前**，所以 loader 是本次引导里**第一个**信号该事件的（loader.c 的
   create_event_ex+signal 即 stock `QcomPkg/Library/PlatformBootManagerLib/PlatformBootManager.c:53-60`
   同款动作，但发生在 boot 早期）。
4. 事件分发是**同步**的：`SignalEvent` 只排队，真正的回调在下一个"降 TPL"的 boot services 调用里跑
   （本 loader 里就是紧随的 `locate_protocol`——DxeCore `CoreLocateProtocol` 拿/放
   `gProtocolDatabaseLock`，`CoreReleaseLock → CoreRestoreTpl → CoreDispatchEventNotifies`，
   本仓库 Mu_Basecore 源码核实）。即 StartEx 执行时 UsbConfigDxe 的 start 回调**已经跑完**。
5. 所以失败不在 loader 的排队/时序，而在**固件初始化链或 start_ex 本身**：`UsbDeviceStartEx` 内部
   依次是 UsbDevDescInitDescriptors → **UsbfnIo->StartController**（DWC3 核软复位、事件缓冲等；
   UsbfnDwc3Dxe 字符串里有 `DwcWaitRegBit failed` / `Unable to reset the device core`）→
   DevSmInitialize → ConfigureEnableEndpoints。任一步失败 → loader 屏显 `usb: start failed %x`。

### 3. 根因（按任务书优先假设排序后的裁定）

- (a) 写死地址不对 —— **排除**（§1，协议驱动）。
- (b) platform_phk110 缺字段 —— **排除**（结构无 USB 字段；且 Boot #8 同 loader 同 FD 非 usb 路径正常）。
- (c) 初始化序列缺 taro 特定步骤 —— **不成立为"缺步骤"**：FD 用的就是 taro 代 vendor 驱动
  （BOOT.MXF.2.0 boot_images），步骤都在；问题在**完成时刻**而非步骤缺失。
- (d) **时序/边界条件 —— 采纳（与全部实证一致）**：第一次 StartEx 落在固件平台初始化（时钟/PHY，
  经 RPM/DAL 的异步资源请求）仍在途的窗口里失败；同一次通电里稍后（或上一次 fastboot 会话留下的
  供电/钟状态还在的那次引导）就能成。**"成功那一次"与失败次唯一的已知区别就是时序**——硬件、驱动、
  描述符、协议全部相同。

顺带的两个实证发现（不动 uefi-udon，仅记录）：

1. **`UsbConfigDxe.patched.efi` 补丁**（udon.fdf 实际用的是它，INF `Binaries.AARCH64 PE32` 指向
   `.patched.efi`）：与原版仅差 **4 字节**（RVA 0x5348，`cbz w8,0x5380` → `b 0x5380`）：强制跳过一个
   条件分支守卫的 vendor 调用（该调用传串 `"USB0"`，邻近错误串 "Failed to attach USB Arid 0x0 HAL
   IOMMU domain"——HALIOMMU 域挂接/NPA 资源类）。这是 senna_bc bring-up 适配补丁，与本失败无时序
   关联；若后续要动 FD 侧，这里是第一个要理解的点。
2. FD 是 DEBUG_CLANGPDB 构建，vendor 驱动的 `DEBUG((…))`（含 UsbConfigInit 失败原因）只上 FD 的
   串口调试口，屏上看不到——所以 Boot #9 的诊断只能靠 loader 自己打印。

### 3.5 实证 vs 假设（任务书问题 7）

**实证**：usb_start 协议驱动、无地址依赖；graft 在 USB init 事件之前运行；事件回调同步完成；
StartEx 内部失败步骤候选集（StartController/DevSm/Endpoints）；驱动的 taro 代际；patched.efi 的
4 字节 diff；"成功那一次"存在。

**假设（需要真机一次引导即可裁决）**：失败的具体 EFI 状态码（Boot #9 照片未带到 code）；"RPM/DAL
时钟资源在途"是哪一级（UsbConfig 回调内 vs UsbfnIo StartController 的 DwcWaitRegBit 超时）。**本
修复把每次尝试的状态码打到屏上**：若 v3 仍失败，屏上 `usb: try N: <code>` 的 code 直接裁决下一步
（TIMEOUT 0x8000000000000012 → 时钟在途假设成立，FD 侧查 UsbInitDxe；NOT_FOUND 0xE → UsbFnIo
binding 未连接，FD 侧查 ConnectController 路径）。

## 4. 修复（loader.c，仅 `usb_start()`）

思路：**把"信号一次+失败即弃"改成"10 秒内有节律地重试"**，每次失败重发 init 事件（让 UsbConfigDxe
回调在新状态下再跑一遍），等待用 `EVT_TIMER + wait_for_event(250ms)`——wait_for_event 会泵固件的
事件队列（它的 QcomWDogDxe 喂狗定时器也在里面跑，PHK110 上 `wdt_pet()` 是 redwood-SMC 专用、
空操作，真狗由固件喂，Boot #8 的 20 s 驻留已证安全）。首次失败/每次重试的状态码都上屏，成功打
`usb: started (retried)`。失败路径补齐 event/tick 的 close_event 清理。

```c
	for (;;) {
		efi_status s = USB->start_ex(&set);
		tries++;
		if (!EFI_ERROR(s)) break;
		if (READ_SYSREG(CNTVCT_EL0) - began > 10 * freq) {   /* 10 s deadline */
			print("usb: start failed %x (%d tries)\n", s, (uint64_t)tries);
			...close..., return 0;
		}
		if (tries == 1) print("usb: start failed %x, retrying\n", s);
		else            print("usb: try %d: %x\n", (uint64_t)tries, s);
		if (event != NULL) BS->signal_event(event);          /* re-kick UsbConfigDxe start cb */
		...create EVT_TIMER tick (once); set_timer periodic 250 ms; wait_for_event(tick)...
	}
	/* success: close event, cancel+close tick, allocate_transfer_buffer, "usb: started%s" */
```

完整 diff 见 `git diff`（`xnuloader/loader.c` +76/−8，单函数），WSL 快照：
`/tmp/wave8-loader.c.pre-wave8`（改前备份）。

## 5. 重建链（全 WSL，可重放）

```sh
a. loader.efi   cd ~/hakios/kernel/xnuloader && PAYLOAD_BASE=0xF4000000 ./build.sh
                （-Wall -Wextra 零警告；strings 有 "usb: try"/"retrying"/"phk110"；
                 66,560 B —— v2 的 66,048 +512）
b. udon FD      不重建：Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd 与 Wave7 产品
                sha 同为 8924cb67…（融合重放 apply-wave5-fusion.py 因此整步跳过——FD 无改动，
                Wave7 的 graft 已在该 FD 里）
c. XNUP         cd ~/hakios/kernel/xnuloader && python3 mkpayload.py \
                  -o /tmp/wave8/wave8-payload-usb.bin --usb loader.efi=$PWD/loader.efi
                （66,728 B；entries {loader.efi 66,560 / usb "1" / kernel.ver}，无 cmdline）
d. 打包         cd /mnt/c/…/hakios-phk110 && python3 -I wave4-scripts/package-udon-boot.py \
                  --fd ~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
                  --shim device-layer/udon-hakios-BootShim.bin \
                  --stock device-layer/stock-boot-a.img \
                  --payload /tmp/wave8/wave8-payload-usb.bin \
                  --out device-layer/udon-hakios-usbmode-grafted-v3.img \
                  --unsigned-out /tmp/wave8/wave8-usbmode-unsigned.img \
                  --report device-layer/udon-hakios-usbmode-grafted-v3.report.json
                kernel_gzip 1,302,741 B；container 1,310,720 B；vbmeta 2,432 B graft；192 MiB
```

注：device-layer 里另有 Wave7b 的 `udon-hakios-{grafted-v3.img,loader-v3.efi,payload-v3.bin}`（非
usb、write_logs 变体，14:56 产出）——与本 wave 的 `*-usbmode-v3.*` 命名不冲突，互未覆盖。

## 6. 独立自检

`wave5-scripts/verify-udon-hakios.py`：**12 PASS 后在容器条目断言处按预期停**（断言的是 Wave5 内核
容器条目集；usb-mode 容器按设计是 `{loader.efi, usb, kernel.ver}`——与 Wave7 相同的已知偏差，按
Wave7 方式以手动等效检查替代）。

手动等效 18 项（`wave8-scripts/verify-manual.sh`，全部 PASS）：report sha==img sha；header 仅
kernel_size/ramdisk_size 改写；gzip round-trip == shim+FD+XNUP（4,261,280 B）且三件逐字节等于源；
shim 头 0xA7100000/0x4000F0/ARMd；`_FVH` @ shim+0x28；FD 与 Wave7 构建产物逐字节同；XNUP
magic/Size/条目集 {loader.efi, usb, kernel.ver}；usb=="1"；loader.efi 条目逐字节等于
`udon-hakios-loader-usbmode-v3.efi`；cmdline 缺席；container sha == unsigned img；stock OEM vbmeta
2,432 B graft 逐字节一致；AVBf v1.0 footer（大端，orig==voff==1,310,720，vsz==2,432）；vbmeta→
footer 零填充；192 MiB。

## 7. 刷写说明（给主代理）

```sh
fastboot flash boot_b device-layer/udon-hakios-usbmode-grafted-v3.img
fastboot set_active b
fastboot reboot
```

**预期屏幕时间线**：

1. ABL splash → udon/Silicium UEFI 画面，**无菜单**（Wave7 graft）。
2. `== XNULOADER v3 ==` banner、payload 条目表、`platform phk110`、`display 1240 x 2772 at b8000000`。
3. usb-mode 分支：
   - 顺利：`usb: started`（第一次就成）；
   - 时序慢：`usb: start failed <code>, retrying` → 若干行 `usb: try N: <code>` → 最长 10 s 内
     `usb: started (retried)`；
   - 10 s 仍败：`usb: start failed <code> (N tries)` → 与 Boot #9 同样走复位——**但此时屏上有每次
     尝试的 EFI 状态码**，是下一轮 FD 侧定位的直接输入（判读见 §3.5）。
4. 驻留：**不复位**，等待主机。gadget VID:PID `18d1:d00d`，product/serial `xnuloader`。
5. 主机侧验证：Windows `usbipd list` 应见 xnuloader 设备 → `usbipd attach --wsl` → WSL 内
   `fastboot devices` 出现该设备 → `fastboot getvar product` 答 `xnuloader`（battery-voltage 等
   getvar 均可答，Boot #9 那次成功枚举已证协议通路）。
6. 取证（若仍失败）：复位循环后从 Android/adb `dd if=/dev/block/by-name/logdump` 取 loader 日志
   （结构同 b8-logdump.bin），或直接拍屏记下 `usb: try N: <code>`。

**回退**：`fastboot flash boot_b backups-slotb/backup-boot_b.img`；旧 usbmode 镜像
`udon-hakios-usbmode-grafted.img`（v2 同款问题）与 v1/v2 内核镜像均在盘上。

## 8. 待真机验证清单

1. v3 是否稳定枚举（核心验证项）：预期 `usb: started`（可能带 "(retried)"）且不复位。
2. 若仍失败：屏上最后一次 `<code>` 的值（§3.5 判读表）+ logdump 日志。
3. 重试上限 10 s 是否合适（若观察到 "retried" 花了 >5 s，可考虑加长；纯 loader 参数）。
4. Wave7b write_logs 改动落盘后与本改动合并重建（§5 命令原样重跑）。
