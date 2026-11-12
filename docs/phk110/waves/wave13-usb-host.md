# 阶段 13 · 2026-11-03 · Windows 主机直连 loader USB 的工具链

Date: 2026-11-03. Scope: 纯 Windows 侧。修通「主机 → libusb → loader USB gadget
(18d1:d00d, product/serial `xnuloader`, bulk, 纯 ASCII 命令协议)」工具链并验证到
协议层自洽（selftest 24/24），真机联调留给后续刷 usbmode 镜像的阶段。
红线遵守：未碰手机（无 adb/fastboot/usbipd attach）、未碰 WSL、未改 ~/hakios 与
仓库既有文件（只新增 `wave13-scripts/` 与本文档）、未安装任何全局软件。

## Result summary

**一句话结论**：✅ libusb 通道修通——ctypes 直载
`intel/usb-driver/libusb-1.0.dll`（实测 1.0.27.11882 x64）枚举/初始化全通，
selftest 24/24；注册表实证 18d1:d00d 的 `xnuloader` 串号实例已绑 **WinUSB**
(oem63.inf)，libusb 1.0.27 原生 WinUSB 后端即可驱动它，**无需 UsbDk/libusbK**；
pyusb「坏」是误报（旧 API 名 `usb.backend.libusb10` → 1.2+ 已改名
`usb.backend.libusb1`）；usbipd attach 失败主嫌疑坐实为 **hrdevmon（火绒
Devmon Kext）挂在 USB 类 UpperFilters**。

| # | 项 | 结果 |
| --- | --- | --- |
| 1 | ctypes 载 dll + libusb_init | ✅ 1.0.27.11882 |
| 2 | libusb 枚举（device list） | ✅ 8 devices visible |
| 3 | 协议解析器（OKAY/FAIL/DATA/异常/500 组 fuzz） | ✅ 17/17 |
| 4 | 无设备安全 DLL 检查（version/init/errname/exit） | ✅ 7/7 |
| 5 | pyusb 对比路径（`libusb1.get_backend` 载同一 dll） | ✅ 同样枚举 8 设备 |
| 6 | 18d1:d00d 在场验证（probe/cmd/log） | ⏸ 本轮不可达（手机 boot_b=v6 非 usb 模式，预期内），留真机清单 |
| 7 | usbipd/hrdevmon 归因（只读取证） | ✅ §4 |
| 8 | 红线 | ✅ |

## 1. 交付物 `wave13-scripts/loader_talk.py`

纯标准库（ctypes），**零第三方依赖**（pyusb 只是对比路径）。运行环境：系统
`python` = 3.13.15 x64（`<host>\AppData\Local\Programs\Python\Python313`），
建议 `-I` 隔离模式。DLL 默认解析到 `<repo>/intel/usb-driver/libusb-1.0.dll`，
可用 `--dll` 或环境变量 `LOADER_TALK_LIBUSB` 覆盖。

```sh
cd <host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110

python -I wave13-scripts/loader_talk.py selftest        # 无设备自测（协议+DLL 安全路径）
python -I wave13-scripts/loader_talk.py dllinfo         # libusb 版本/后端信息
python -I wave13-scripts/loader_talk.py list            # 枚举 USB 设备（vid/pid/class/speed）
python -I wave13-scripts/loader_talk.py probe           # 找 18d1:d00d → open + claim interface
python -I wave13-scripts/loader_talk.py cmd getvar      # bulk-out 发 ASCII + bulk-in 收应答
python -I wave13-scripts/loader_talk.py cmd "oem log" --timeout 5000
python -I wave13-scripts/loader_talk.py log --out log.out   # oem log → DATA 落盘
# 通用参数： --vid/--pid(16进制) --iface N --timeout ms --nl(命令加换行) --libusb-debug 0-4
# 退出码： 0 成功 / 1 设备或协议失败 / 2 用法错误 / 3 selftest 失败
```

### 1.1 ctypes 绑定要点（复用经验）

- **dll 架构**：`intel/usb-driver/libusb-1.0.dll` 是 PE32+ x64（`file` 确认），
  与 x64 Python 匹配；`intel/usb-driver/libusb/` 下另有 MinGW64/VS2013-2022 整套
  SDK（含 `include/libusb.h` 与 `libusb-1.0.def`，本阶段结构体布局以此头文件为准）。
- **加载**：`os.add_dll_directory(<dll 目录>)` + `ctypes.CDLL(绝对路径)`，依赖
  解析不外溢 PATH。
- **结构体布局**：libusb.h 中 device/config/interface/endpoint descriptor 均
  **非 packed**（只有 control_setup 是 `LIBUSB_PACKED`）→ ctypes.Structure 默认
  自然对齐恰好等于 MSVC x64 布局（Endpoint=32B、InterfaceDescriptor=40B、
  Config=40B、Interface=16B、DeviceDescriptor=18B）。遍历 active config 用
  `libusb_get_active_config_descriptor`，索引 `cfg.interface[i].altsetting[a]`
  即得**实例**（不是指针——再取 `.contents` 会 AttributeError，本阶段踩过已修）。
- **argtypes 深度约定**：出参统一 `byref(c_void_p 实例)` 配 `POINTER(c_void_p)`
  一层；设备数组用 `POINTER(POINTER(c_void_p))` 实例 + 三层 POINTER 传 byref
  （libusb_get_device_list），free_list 直传两层实例。`libusb_set_option` 是
  variadic——**不设 argtypes**。
- **实测版本**：`libusb_get_version()` → `1.0.27.11882`，rc=""，与任务书"1.0.27"一致。

### 1.2 协议解析器语义（`LoaderProto`）

依据 loader.c:3960-4035 的协议面（本阶段不可达 WSL，按任务书转述实现，语义从宽）：

| 帧 | 解析 | 备注 |
| --- | --- | --- |
| `OKAY` | `("OKAY", None)` | 可带尾随文本（getvar 风格 `OKAY<value>`），CR/LF/尾空白剥除 |
| `FAIL:<reason>` | `("FAIL", reason)` | reason 原样保留 |
| `DATA<hexlen>` + payload | `("DATA", bytes)` | hex 位数从宽（8 位标准，任意位兼容）；payload **跨 chunk 累积**，收满即返回 |
| 垃圾字节 | `("PARTIAL", raw)` | 不抛异常不卡死，raw 保留取证 |
| 半个帧头（`OK`/`FAIL`/`DATA0`…） | 等下一个 chunk | 前缀匹配 `OKAY`/`FAIL:`/`DATA` |

**已声明的近似**：OKAY/FAIL 按「一次 bulk write 一帧」在首个 chunk 边界完成
（loader 每条应答一行，实测场景足够）；若真机发现多 chunk 应答行，只需把
`_parse()` 的 OKAY/FAIL 分支改为行终结符聚合——不影响 DATA 主路径（`oem log`
大负载本来就是跨 chunk 的，已覆盖）。命令编码默认**纯 ASCII 无终结符**
（fastboot 风格）；`--nl` 可追加 `\n`。

### 1.3 selftest 24 项（全绿）

- 解析 17 项：OKAY / OKAY+value / FAIL / FAIL 前缀等待(`FAIL`→`:`) /
  DATA 内联 / DATA 仅头 / DATA 半截 / DATA 跨 3 chunk / DATA 坏 hex /
  垃圾字节 / 空 feed / 帧头裂开(`OK`+`AY`) / OKAY 不卡死 / 编码 3 项 /
  **500 组随机字节 fuzz（零异常零卡死）**。
- DLL 安全路径 7 项（无设备也能跑）：load（1.0.27.11882）/ 版本形状 /
  init / device list（8 台可见）/ errname(-7)=LIBUSB_ERROR_TIMEOUT /
  HAS_CAPABILITY=1 / exit。

### 1.4 真机态验证（本轮结果 = 预期内失败）

- `list`：libusb 可见 8 台——手机 ADB `22d9:2765`（high-speed，string 读
  ACCESS=驱动非 WinUSB/被占用）、4 台 AMD hub、指纹 `2808:1579`、摄像头
  `3277:00d1`、蓝牙 `8087:0032`。**18d1:d00d 不在**（手机在 Android，
  loader gadget 只在 usbmode 镜像里驻留——与任务书背景一致）。
- `probe`/`cmd`/`log`：走"device 18d1:d00d not found"明确失败路径并打印
  预期场景提示，退出码 1。代码路径已全部跑通，只差真机枚举。

## 2. libusb ↔ WinUSB 兼容性结论（本轮核心技术验证）

**结论：Zadig 的 WinUSB 绑定 + 现成 libusb-1.0.dll 即可，无需任何额外后端。**

证据链（全部只读取证）：

1. 注册表 `HKLM\SYSTEM\CurrentControlSet\Enum\USB\VID_18D1&PID_D00D` 下有
   **两个设备实例**（按 serial 区分，驱动绑定互不影响）：
   - **`\xnuloader`**（loader gadget，serial=xnuloader）：
     `Service=WinUSB`、`Mfg=@oem63.inf,%vendorname%;Google Inc.`、
     `FriendlyName=xnuloader`、ClassGUID=`{88bae032-5a81-49f0-bc3d-a4ff138216d6}`
     （WinUSB 设备类）→ **Zadig/oem63.inf 的 WinUSB 绑定在位**。
   - **`\SERIAL_REDACTED`**（手机 ADB 串号 = ABL fastboot gadget）：
     `Service=VBoxUSB`、`DeviceDesc=@oem64.inf...;VirtualBox USB Driver`、
     `FriendlyName=USBIP Shared Device` → usbipd `bind --force` 的产物，**只
     影响 fastboot 实例**，与 xnuloader 实例的 WinUSB 不冲突。
2. libusb 1.0.27 Windows 后端**原生驱动 winusb.sys**（还有 libusb0/libusbK）。
   实测它枚举出了本机 WinUSB 绑定设备（`Get-PnpDevice` 实证现存一台
   `ADB Interface` Service=WINUSB，即 22d9:2765，出现在 libusb list 里）。
   UsbDk 后端在 libusb 1.0.24+ 已被移除（头文件里 `LIBUSB_OPTION_USE_USBDK`
   只是兼容 no-op）→ **装 UsbDk/libusbK 都不需要**。
3. 唯一实测到的 open 失败模式：string descriptor 读 `LIBUSB_ERROR_ACCESS`
   （adb.exe 持有接口时）——属占用冲突，不是 WinUSB 不兼容。

待真机闭环的一点（下一步阶段）：loader gadget 枚举出现后跑
`python -I wave13-scripts/loader_talk.py probe`，预期输出
`OPEN+CLAIM OK (interface 0, class=vendor)` + bulk IN/OUT 端点表；此步是
"WinUSB 绑定下 libusb open+claim"的最终直接证明（机制上已无悬念：同后端、
同绑定形式、枚举已通）。

**⚠ footgun**：`usbipd list` 显示一条 **Persisted 共享记录
`b67ab332-4d35-4c04-9bb1-81abc1d63239 → xnuloader`**。若对 xnuloader 实例再
做 `usbipd bind/attach`，会把 WinUSB 换成 VBoxUSB、毁掉 libusb 通道
（attach 期间驱动被换走）。建议后续执行 `usbipd delete b67ab332-…`（本阶段未
执行——属配置变更，只留结论）；usbipd 域内只允许动 `SERIAL_REDACTED`（fastboot）实例。

## 3. pyusb 导入 bug 诊断（次要，已闭环）

**结论一句话：pyusb 没坏、也没装错 python——是 API 名变了。**

- `pyusb 1.3.1` 完好安装在 Python313 site-packages（`import usb` 正常，
  `usb.__version__=1.3.1`，`usb/backend/` 目录完整含 `libusb1.py`）。
- 报错的 `import usb.backend.libusb10`：pyusb **1.2.0 起该模块改名**
  `libusb10 → libusb1`，旧名自然 ModuleNotFoundError。实测
  `import usb.backend.libusb1` OK。
- 对比路径全通：
  `usb.backend.libusb1.get_backend(find_library=lambda p: r'intel\usb-driver\libusb-1.0.dll')`
  → 枚举到与 ctypes 完全一致的 8 台设备。
- Python314（`py`）未装 pyusb（无关紧要，主路径不依赖）。
- 项目主交付仍用 ctypes：无 pip 依赖、无包遮蔽风险、结构体透明。

## 4. usbipd 失败归因（只读取证，未做任何 bind/attach）

| 证据 | 内容 |
| --- | --- |
| `usbipd --version` | `5.3.0-54+Branch.master.Sha.aa3db8b8…` |
| `usbipd list` 警告原文 | `usbipd: warning: Unknown USB filter 'hrdevmon' may be incompatible with this software; 'bind --force' may be required.` |
| `sc query hrdevmon` | `KERNEL_DRIVER`，`RUNNING`（STOPPABLE） |
| `sc qc hrdevmon` | `Huorong Internet Security Devmon Kext`，`BOOT_START`，`\SystemRoot\system32\DRIVERS\hrdevmon.sys` |
| 注册表 `HKLM\…\Control\Class\{36FC9E60-C465-11CF-8056-444553540000}` | **`UpperFilters = REG_MULTI_SZ hrdevmon`** —— 火绒设备监控内核驱动挂在 **USB 设备类 UpperFilters**，即每个 USB 设备节点加载时都要过它 |
| Persisted 记录 | `b67ab332-4d35-4c04-9bb1-81abc1d63239 → xnuloader`、`f474f60e-497d-4e01-abec-0b3c96f4be12 → Android`（历史 bind 遗留，见 §2 footgun） |

**归因**：Boot #9「干净枚举仍 Failed to attach」的主嫌疑 = **hrdevmon**。
机理：usbipd attach 需要把设备节点驱动临时换成 VBoxUSB 并由 usbipd 服务独占
重定向；类 UpperFilter 位于功能驱动之上，火绒 Devmon 的设备管控路径（禁止/
拦截未知 USB 设备类操作）与该流程冲突是 usbipd 官方已知冲突类别（警告原文即
点名 unknown USB filter）。`bind --force` 只解决 INF 强制安装，**不解决
filter 冲突**——与"force 过仍 attach 失败"的实测吻合。

**处置选项（均未执行，按需择一）**：
1. 退出/卸载火绒（最彻底）；
2. 把 `hrdevmon` 从上述 USB 类 `UpperFilters` 移除并重启（只解除 USB 类挂钩）；
3. usbipd 侧无需动作——**loader 通道走 WinUSB/libusb，完全绕开 usbipd/VBoxUSB，
   不受此冲突影响**（这正是本阶段选 ctypes-libusb 直连路线的额外好处）。

## 5. 真机联调清单（后续刷 usbmode 镜像后执行）

镜像：`device-layer/udon-hakios-usbmode-grafted.img`（阶段 7 产物，loader v2 +
`usb=1` → USB 命令服务器常驻；刷写方式同 §6 wave7：fastboot flash boot_b +
set_active b，走 `SERIAL_REDACTED` 实例的 usbipd/VBoxUSB fastboot 通道）。

```sh
# 1. 枚举确认：手机起在 usbmode 镜像后，Windows 应出现 18d1:d00d（serial=xnuloader）
python -I wave13-scripts/loader_talk.py list          # 期望: 18d1:d00d 标记 <== LOADER GADGET
# 2. 关键验证：open+claim（WinUSB 绑定下 libusb 的最终证明）
python -I wave13-scripts/loader_talk.py probe         # 期望: OPEN+CLAIM OK + bulk IN/OUT 端点表
# 3. 第一条命令
python -I wave13-scripts/loader_talk.py cmd getvar    # 期望: OKAY 或 OKAY<value>
# 4. 拉内核/引导日志
python -I wave13-scripts/loader_talk.py log --timeout 10000 --out oem-log.out
#   期望: status DATA + 落盘字节流（loader 的 logdump 风格内容）
# 5. 可选：oem screenshot / oem clearscreen / oem run[:checkpoint] / reboot
python -I wave13-scripts/loader_talk.py cmd "oem screenshot"
python -I wave13-scripts/loader_talk.py cmd reboot    # 设备会消失，NO RESPONSE 属正常
```

期望应答对照（loader.c:3960-4035 面）：`getvar`→`OKAY[<value>]`；未知命令→
`FAIL:<reason>`；`oem log`→`DATA<hexlen>`+payload；`reboot`→OKAY 后设备重枚举。
超时默认 2 s，log/screenshot 建议 5-10 s。若 probe 报 ACCESS：确认没有别的
进程（fastboot/旧 libusb 句柄）占用接口；若报 NOT_FOUND：手机没起在 usbmode
镜像（或回到 Android/ABL）。

## 6. 新增文件

| 文件 | 说明 |
| --- | --- |
| `wave13-scripts/loader_talk.py` | 主交付：ctypes libusb 主机工具（list/probe/cmd/log/dllinfo/selftest） |

未改动任何既有文件；`intel/usb-driver/libusb-1.0.dll`（1.0.27.11882 x64）原样
复用，未装任何全局软件。
