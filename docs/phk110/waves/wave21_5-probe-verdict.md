# 阶段 21-5 · 2026-11-08 · bulk 探针与重掷机制：阻塞点移到主机侧

> 2026-11-08 · 阶段 21.5 执行记录全循环：v17 施工（§1）→ 构建/自检/自刷（§2-§3）→ **Boot #34 现场判决：判别器字面量被现场纠正**（§4-§5）→ **v17b 第 2 轮（现场修正版）**（§6）→ 教训（§7）→ 红线执行（§8）
> 判据基线：`docs/research/f12-ep2-not-configured.md`（阶段 21.4 指令级归因）

## 0. 一句话结论

**v0.4「达尔文」未宣告；两轮刷写预算全部用完；但探针机制按设计完整执行并留下了完整判别记录**：v17b（Boot #35）的 logdump 显示 **3 代际 × 6 拍 = 18 次探针全部应答 `0x8000000000000007`（未武装）**，两次重掷精确触发（"the pair is un-armed after generation 1/2" → 25s 安静 → start_ex 内部 StopController 重启 → 新代际），终判行 "the pair never armed across 3 generations … the session goes on over ep0 alone" 逐字到手，会话照跑（en0 @123.6s 上线、10.0.0.2/30、1 帧发出 0 收到、`loader_return_after expired` 干净返回）→ 手机循环自动回退到安卓（22:04，logdump 自动拉取）。**然而判别记录同时暴露了判别器的结构盲区**：主机在整个两轮里从未枚举成功（`0000:0002` 恒现 = UEFI/loader 相位 gadget ep0 不应答主机描述符请求；同口 ABL gadget 与安卓 USB 枚举正常 = 口/线无罪）——**无主机就没有 SET_CONFIG，未武装是"无主机"的预期正常态**；因此 18×"未武装"不能分辨"墙恒在（H1/H2）"与"主机从未到场"，**真正的阻塞已上游化为"主机可见性"（ep0 枚举路径），bulk 武装路径（阶段 21.4 的 T2/H1/H2/H3）在主机可见性恢复之前无法被行使**。下一阶段攻击面由此改写。

## 1. 施工内容（v17 = 阶段 21.4 首选修复的落地）

`patch-loader-v17.py`（`a89a627e…`）对 WSL 构建树 `~/hakios/kernel/xnuloader/loader.c`（v16b+v16c 态）施加 3 hunks（每 hunk 唯一性断言）：

- **hunk 0**：`usb_rx_queued` 前置声明；**hunk 1**：`usb_start()` 局部变量扩充；
- **hunk 2**：**arm-probe 阶段**——start 链成功（usb_ready=1）后，对 bulk OUT 对以 5s 节拍提交 0 长度探针（每代际 ≤6 拍）；每拍 `USB->handle_event` 泵送（ep0 状态机 = SET_CONFIG 武装链只在 dispatch 下推进，不泵则探针说谎）；探针成功（=0）即 `abort_xfer` 收回并判 armed；失败即打印代码（判别器记录）；代际满窗仍败 → stop + init 事件重signal + 25s 安静 + start 链重来（≤2 次重掷）；终判无头会话。

## 2. 构建与自检（两轮四件套，sha 只新增）

| 件 | v17（第 1 轮） | v17b（第 2 轮） |
|---|---|---|
| cmdline | `675e917817c462ca`（= v16 字节逐字节） | 同左（共用 `udon-hakios-cmdline-v17.bin`） |
| payload | `d9461af64e592cda` | `44df105c4c46881d` |
| graft | `505ac2b055a1a389` | `467b54c01cf7f2a1` |
| kernel | `17c905ec240a8b00`（v15/v16 逐字节不变） | 同左 |
| loader.efi | `47acf7b058a73069`（76,800 B，零警告） | `d368c8aa93821035`（76,800 B，零警告） |
| verify | 57/57（`verify-udon-hakios-v17.py`） | **59/59**（`verify-udon-hakios-v17b.py`：+退判别行消失断言 +v17 终判行消失断言） |

公共断言：FD `8924cb67…`（WSL 树件）/shim `108ce972…` 未动；kernel/kernel.ver/resident/ramdisk/cmdline = v16 条目逐字节；PAYLOAD_BASE 地址 pin（0x2190 movk + 0x2198 movz）+ 布局鲁棒 pin 双断言；拒绝名单 v16/v16b'/v16c/坏件 f445f187（v17b 再加 v17 47acf7b0）。
配套新脚本（device-layer 只新增）：`patch-loader-v17.py` / `patch-loader-v17b.py`（现场修正 delta）/ `make-cmdline-v17.py` / `make-payload-v17.sh` / `make-payload-v17b.sh` / `verify-udon-hakios-v17.py` / `verify-udon-hakios-v17b.py` / `mk-verify-v17b.py` / `auto-logdump-17.sh`。

## 3. 第 1 轮自刷（Boot #34，19:48）

"已进入 fastboot"的转述当时与实机状态不符（实机在安卓态（22d9:2769）→ 按标准通道从安卓发起：`adb reboot bootloader` → d00d 上总线（"Shared (forced)" 持久共享自动生效）→ `usbipd attach` → `getvar product` = **taro** ✓ → sha 复核 `505ac2b0…` ✓ → `flash boot_b`（4.8s/0.6s 全 OKAY）→ `set_active b` ✓ → `reboot` @19:48:00。

## 4. Boot #34 现场判决（logdump-v17.bin，20:45 安卓回落自动拉取）

**三重现场证据（`logdump-v17.bin` + `v17-session-fresh.txt`）**：

1. **v17 探针开火记录**（新会话头，offset 455-753）：`usb: dwc3 soft reset did not settle in one second`（v16c wake 的 1s 界退出——**v16c 时代同款打印**，logdump-v16c.bin 头部同在，非 v17 新病）→ `usb: dwc3 woken` → `twenty-five quiet seconds` → **`usb: bulk probe gen 0 beat 0: 8000000000000007`** → `a non-wall probe answer stopped the stage` → `usb: started` → 零 `try failed: start_ex`（**首试即成**）。
2. **判别器字面量被现场纠正**：探针在未武装对上的 loader 可见应答 = **0x8000000000000007（EFI_DEVICE_ERROR）**——UsbDeviceSend 在 UsbFn 失败后把 raw 墙码（0x8000000C）包装成 7 才返回（F12 §1 的 `%r=Device Error` 行正是这一层）。v17 的 `!= 0x8000000C` 判"非墙停阶段"因此把**每一拍都会答 7 的未武装对**误判成"另一层问题"→ 阶段 beat 0 即停 → **重掷（修复本体）从未执行**。
3. **会话完整跑通 + 手机自愈**：en0 @63.9s 上线、`en0 has 10.0.0.2/30` @64.4s、`en0 so far 1 frames sent (42 bytes), 0 received` @151.4s（内核侧网环工作；0 received = 主机从未说话）、干净 `== END OF LOG ==` @64380（**不在旧段列表** = 本次新会话）→ recycle → slot b 循环数代 → **~20:45 ABL 自动回退到安卓**。**F11"冻结"假说撤销**（此前 ~1 小时的总线恒 `0000:0002` 是循环态，不是死机态）。
4. **主机侧真相**：整个循环期 Windows 恒 `0000:0002 未知USB设备(设备描述符请求失败)`、零 d00d 窗口——**UEFI/loader 相位的 gadget ep0 不应答主机描述符请求**（同口上 ABL fastboot gadget 19:48 刷写全程可用、安卓 20:45 枚举即成 = 口/线/驱动无罪）；两轮 catch 零 serving 的直接根因即此。**主机从未到达 SET_CONFIG → T2 确定与否在两轮里均未被行使**（en0 的 "1 frame sent" 只是内核侧入环计数，不证 USB 腿）。

## 5. 判别器现状（归因留给下一轮）

- 探针判别式已现场修正：**任何非零应答 = 未武装**（7 形/0xC 形/64 位/32 位一网打尽，逐拍上记录）；armed（=0）只在真武装时出现。
- 但 ep0 不应答主机的层（= 主机连枚举都完不成）**在探针上游**——探针码只能证"bulk 未武装"，不能分辨 H1（DEPSTARTCFG/walk 翻车）/H2（speed==0）/H3（STALL），因为**三者的共同上游 = 主机 SET_CONFIG 从未到达**。下一轮归因的输入 = v17b logdump 的**逐拍探针码序列**（gen0-2 × beat0-5，若主机在某代际的 re-enumeration 后终于枚举成功，armed 出现的代际/拍位直接指示 T2 是否能确定）。
- 屏幕照片仍是 vendor 前导错误行（`DEPSTARTCFG Fails` / `Failed to set config for ep` / `Unknown USB Speed`）的唯一活通道——若未来轮次有人盯屏，任一行即一票定案。

## 6. 第 2 轮：v17b（现场修正版，Boot #35）——判别记录完整落地

**修正内容**（`patch-loader-v17b.py`，对 v17 后 loader.c 的 delta）：
1. **判别器现场修正**：任何非零探针应答 = 未武装 → **继续打满 6 拍**（每拍码上记录），代际满窗未 armed 才判墙；
2. **去显式 `USB->stop()`**（loader 史上首次调用 = 未证调用；重掷改骑 **start_ex 自己开头的内部 StopController**——v15 以来每 boot 必经的已证路径；终判态 = 服务器保持 up 的 v16c 已证形态，回收链已证可回安卓）。

**流程记录**：v17b 补丁 → `PAYLOAD_BASE=0xF4000000 ./build.sh` 零警告（`d368c8aa…`）→ payload `44df105c…` → graft `467b54c0…` → **verify 59/59** → 手机已在安卓（slot `_a`）→ 标准通道：`adb reboot bootloader` → d00d attach（getvar product = **taro** ✓ / sha 复核 `467b54c0` ✓）→ flash OKAY（4.9s/0.7s）→ `set_active b` ✓ → reboot @**20:59:02**。

**Boot #35 判别记录（logdump-v17b.bin，22:03 自动拉取，`v17b-session-fresh.txt`）——修复机制首次完整执行**：

```
usb: dwc3 soft reset did not settle in one second        ← v16c 同款（非新病）
usb: dwc3 woken (phy suspend off + core soft reset)
usb: the platform is asked up; twenty-five quiet seconds before the first try
usb: bulk probe gen 0 beat 0..5: 8000000000000007        ← gen 0：六拍全未武装
usb: the pair is un-armed after generation 1 (last 80000000000…)
usb: the platform is asked up again; twenty-five quiet seconds before the re-throw's try
usb: bulk probe gen 1 beat 0..5: 8000000000000007        ← gen 1（重掷 1）：六拍全未武装
usb: the pair is un-armed after generation 2 (last 80000000000…)
usb: the platform is asked up again; …
usb: bulk probe gen 2 beat 0..5: 8000000000000007        ← gen 2（重掷 2）：六拍全未武装
usb: the pair never armed across 3 generations (last …): the session goes on over ep0 alone (v16c's proven state)
usb: started                                             ← start_ex 三代际全部首试即成（零 try failed 行）
payload entries → kernel 会话：en0 @123.6s 上线 / 10.0.0.2/30 @124.1s / 1 帧发出 0 收到 @211.3s
--- loader_return_after expired --- → 干净 END OF LOG → 循环回退 → 22:04 回安卓（logdump 自动拉取）
```

**判读（探针证据 + 结构盲区）**：
- **修复机制全部按设计执行**：18 次探针（3 代际 × 6 拍）逐拍上记录；两次重掷精确触发（init 重signal + 25s 安静 + start_ex 内部 StopController 重启 = 给主机的新枚举世代）；终判态 = ep0 独活（服务器保持 up），会话照跑、回收链走通。零 stop() 调用、零新 vendor 调用、零警告。
- **"bulk 从未武装" = 结构性盲区下的预期态**：主机在两轮全程从未枚举成功（`0000:0002`）——无主机就没有 SET_CONFIG，未武装正是"无主机"的**正常态**；因此 18×"未武装"**不能**证明"墙恒在"，也同样不能证伪 H1/H2/H3——**判别器的有效域 = 主机可见之后**。
- **阻塞的上游化（本轮最重要结论）**：v0.4 的 SSH 数据面阻塞从"bulk 武装路径"**上游化为"主机可见性"**——UEFI/loader 相位的 gadget ep0 不应答主机描述符请求（两轮 40+ 分钟总线观察恒 `0000:0002`；同口 ABL fastboot gadget 刷写全程可用、安卓 USB 枚举即成 = 口/线/驱动全部无罪）。v15/v16 时代服务会话成立过 = 该管线曾经可用；v16b' 以来再未服务 = **主机 attach 的时机落在了 boot 窗（泵送稀疏期），失败枚举被 Windows 固化为死 devnode 后不再重试** 是当前最强工作假说（解释 v16 会话期可服务/闪返死窗不可服务的分野），待下一轮以"泵送前移/强制重枚举"实验定案。

**下一阶段施工单（主机可见性优先）**：
1. **泵送前移**：gadget 一上电就持续泵 handle_event（settle 窗与 kernel boot 间隙全部覆盖）——消除"主机 attach 时无人值守"的死窗；~10 行。
2. **强制重枚举联动**：主机侧 watcher 见 `0000:0002` 恒现即拔插一次数据线（或 pnputil restart-device，管理员）——Windows 死 devnode 只在重附时刷新；
3. 若 1+2 后主机仍不可见 → ep0 应答路径的 vendor 侧行为深挖（对照 v15/v16 可用世代的 boot 时序差异）；
4. 主机可见后，探针判别器（已在 v17b 就位）直接行使 H1/H2/H3 分辨——bulk 路径的归因条件届时自动成立。

## 7. 教训（新 landmine 记账）

1. **🔴 探针/判别设计必须先校准"错误码穿过包装层的形态"**：F12 §1 早已记录 UsbDeviceSend 打 `%r=Device Error`（= 包装层证据），但修复设计仍按 raw 0x8000000C 写判别式——**判别器上线前应先拿一次真实失败码校准**（哪怕 1 次 boot）。
2. **🟡 "唯一新增 vendor 调用"红线级审查保留**：v17b 已移除显式 stop()（回到全已证路径）；该原则继续有效。
3. **🟢 总线形态学**：`0000:0002 描述符请求失败` 恒现 ≠ 死机——Boot #34 证明它可以只是"该相位 gadget ep0 不应答 + 手机在循环"。判读先看会话证据（logdump END OF LOG 是否新增），再下冻结结论。
4. WSL /tmp 跨调用清除：常驻任务一律 agent 侧 background 承载、日志落 /mnt/c（本轮执行，早期 nohup 损失 ~18 分钟覆盖的教训沿用 阶段 20 记账）。

## 8. 红线执行与预算

- 只碰 boot_b ✓（两轮 flash 目标均仅 boot_b；userdata/darwin 未触碰；darwin 卷条目逐字节断言钉死）；禁 git reset/checkout/stash/clean ✓；Windows device-layer 只新增 ✓；git add 不 commit ✓。
- **刷写预算 2/2 轮已用**（v17 Boot #34 + v17b Boot #35）→ 按红线本轮停止刷写，后续工作：①v17b 循环的 logdump 判读（拉取器常驻自动落盘 `logdump-v17b.bin` + keylines）；②若 armed 从未出现且 ep0 不应答形态持续，下一攻击面 = 主机可见性（ep0 枚举路径）而非 bulk 武装路径——阶段 21.4 的 H1/H2/H3 分辨计划改由"先让主机看到设备"子课题领路；③判定后交还：手机将随循环自动回退到安卓（`set_active a` 可在下次 fastboot 窗口顺手执行）。
