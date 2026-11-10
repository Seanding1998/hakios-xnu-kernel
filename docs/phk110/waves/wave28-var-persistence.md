# 阶段 28 · 2026-11-10 · /var 持久化回归门与步骤归档

> 2026-11-10 06:33 → 09:27（时间盒收尾；结论未到手，如实记录）· 阶段 28 执行记录
> 任务书：v0.4 验收最后两门 = ①重启后 /var 内容保留（PLAN v0.4 原文）②可重复步骤归档；零刷写
> 红线执行：零刷写 ✓（全程无 fastboot write，无 set_active）；loader 相位禁 usbipd attach ✓（守望器单一 Windows-libusb 所有者；~07:30 一起**外来 attach 事故**见 §3，已 detach 恢复）；PID 精确 kill ✓（每次 taskkill 按 PID）；boot_b 只读 ✓

## 0. 结论（**PENDING —— 结论未到手，时间盒耗尽，如实记录**）

**两个 SSH 会话（写标记 → 整 boot 循环 → 复读对照）未能开始**：阶段 27 判定会话返回后，loader 进入
bulk 全聋态（06:40:45 → 09:25 收尾，~165 min 无变化，§2-§3），带内零刷写杠杆穷尽（§3），
判定所需的第一会话标记包未能写入。**本轮不编造任何结果——verdict28-var.txt 故意缺席**。

- 已交付：四件工具 + runbook + 判定器（语法验证 + 子命令实测 + 判定管线合成包双向往返单测，§4）——**判定通路已建成，一条命令即可现场行使**
- 已交付：半启动状态时间线取证 + loader.c 源码级服务窗机制定位（§2，修正 wave27 §4 的"保存窗"模型）
- 已交付：外来 usbipd attach 事故的即时恢复 + 取证（§3，嫌疑与复发监控记录在案）
- 后续可用：物理解锁一键流程 + 恢复三命令（§5/§6）
- 收尾纪律：**零 detached 常驻进程**（wave26 孤儿 hunter 教训）——守望器已按 PID 全清，复工即一条命令

## 1. 开局（06:33-06:41）：抢会话失败的三次实录

接续点判断：阶段 27 verdict（06:19:51）会话 exec 估 ~06:16 → 1800s 帽 ~06:46 到期 → 06:33 时点
会话应活。实录三次全败，三次形态互异（这个序列本身就是数据）：

| 时刻 | 动作 | 现场回答 | 判读 |
|---|---|---|---|
| 06:35:31 | probe-phase（`oem recording`） | `FAILno recording` = **loader 应答** | 会话已提前返回；loader 在服务相位；探测重启了 exec 钟 |
| 06:40:15 | 标记包 recon（tunnel 六轮） | round1-2 `getvar -> Response(DATA, usb: the console mirror…)`；round3-5 `None` | **loader 应答了两轮后中途变聋** —— 窗口在会话中途关闭 |
| 06:43 起守望器 w1 | 连续 claim+getvar arming | 全 `claim ok but getvar -> None` / `bulk-OUT failed LIBUSB_ERROR_TIMEOUT` | bulk 对全聋，ep0 枚举正常 |

## 2. 机制定位（源码级）：聋态 = `usb_command_loop` 的 240s 服务窗到期

`loader.c:5610-5624`（v23 loader 字节的源）usb_mode 路径：

```c
usb_start();
run_kernel(0, 0);            /* 内核会话（v23 = loader_return_after=1800） */
usb_service_secs = 240;
usb_service_mark = READ_SYSREG(CNTVCT_EL0);
flush_log();
if (usb_ready) { usb_command_loop(); }
reboot();
```

**会话返回后 loader 只服务 240 秒，然后 reboot()**。06:40:45 聋态起点 = 窗到期时刻（若
06:36:45 返回）或最后一次应答命令刷新 mark 后 240s（06:40:25 应答 → 06:44:25 到期）——
两解都与"round1-2 应答、round3-5 None"（窗口在尝试中途关闭）吻合。**wave27 §4 的
"保存窗"概念需要修正：不是 HFS 脏状态保存耗时，而是这个固定 240s 服务窗 +
`usb_ready` 门槛**（zombie boot 时 `usb_ready`=false → 无服务窗 → 立即 reboot()）。

聋后的 reboot() 预测节点掉落 → 新 loader 代 → arming 重来。实测：**唯一一次掉落 07:22:58
（21s 后原地址回来）**，与 ~06:53+1800s 的会话尾 reboot 预测吻合；~07:53 预测窗无掉落
（模型不完全成立——下一波值得拉 logdump 验证 reboot 是否真发生）。

## 3. 事件时间线（零刷写纪律下的全部现场处置）

| 时刻 | 事件 | 处置 |
|---|---|---|
| 06:35:31 | probe：loader 应答（服务相位） | 按 wave27 纪律真静默 250s → 06:40:15 开火 |
| 06:40:45 | loader 两轮应答后中途变聋 | —— |
| 06:43-06:59 | 守望器 w1 连续 arming，全 DEAD-PAIR（~20 轮） | 病窗达 wave27 S1 先例（20min）→ 决策热复位 |
| 06:59:30 | **热复位 #1**（revive-v26：drain×6 全空 → libusb_reset_device） | `hot reset: 0`，getvar None —— **被吸收**（节点不掉） |
| 07:03-07:17 | 守望器 w1b 继续 arming（S2 先例：吸收后 ~6min 自愈） | 37min 仍聋（超 S4 的 33min+）→ 二次复位决策 |
| 07:18:40 | **热复位 #2** | 同样被吸收 |
| 07:22:58 | **节点掉落**（21s）→ 原地址回来 | 唯一掉落；与半启动残留循环 reboot() 预测吻合 |
| ~07:30 | **外来 usbipd attach 事故**：STATE=Attached，VBoxUSB 抢占 → `LIBUSB_ERROR_NOT_SUPPORTED`（wave13 footgun 同款） | **07:39 detach 恢复 Shared**；守望器 open 立即复原（claim ok）。凶手未落定：嫌疑 = 提权 PowerShell 30432（命令行不可见）；埋伏 30min 无复发 |
| 08:03 | 3 轮纪律用尽，零刷写带内杠杆穷尽 | **升级注记挂 progress.log 顶部**（物理干预请求，§5）；守望器保持武装 |
| 08:22 / 09:24 | 守望器两次被外部停止（harness 回收后台任务） | 均立即重启（w1d 为末代）；09:27 收尾时按 PID 全清（**零 detached 常驻**——wave26 孤儿 hunter 教训） |
| 08:16 | 判定管线合成包单测 | 双向往返 ✓：全匹配 → PERSIST exit0；篡改 blob → REGRESSED exit1 |

带内杠杆清单（全部试过或结构性不可用）：oem reboot/oem 命令族（走 bulk 对 = 死路）、
热复位 libusb_reset_device（×2 吸收）、等 ABL 回退（loader 不崩则永不触发）、
usbipd attach（**红线禁手**，loader 相位单一 Windows-libusb 所有者）。

## 4. 交付件（全部建成 + 语法/子命令级验证；现场行使待会话恢复）

| 件 | 用途 | 验证状态 |
|---|---|---|
| `wave28-scripts/mark-var-v28.py` | /var 标记包（write：recon+marker×2+64KiB blob+hostkey 指纹；read：全复读） | py_compile ✓；ssh 步骤与 wave27 同构（ProxyCommand/tunnel25w/PID kill） |
| `wave28-scripts/hunt-var-v28.py` | wave27 相位感知守望器，HIT 后自动跑标记包（write/read 两模式） | py_compile ✓；DEAD-PAIR/LOADER-PHASE/NO-DEVICE 分类实测工作 |
| `wave28-scripts/runbook-var-gate.sh` | 一步式 runbook：`state/march/write/read/verdict` 五子命令 | bash -n ✓；`state` 子命令实测（`state: loader`）；march/write/read 委托 wave27 已验件 |
| `wave28-scripts/verdict-var-v28.py` | 四行判定表（root marker 内容 / jb marker utc / blob sha256 / host keys）→ `verdict28-var.txt`（PERSIST/REGRESSED） | py_compile ✓；**合成包单测双向往返 ✓**（全匹配 → PERSIST exit0；篡改 blob → REGRESSED exit1） |
| `wave28-scripts/progress.log` | 进度可见性日志（每阶段一行 + 升级注记置顶） | 持续更新中 |

判定协议（两会话齐后运行）：
`bash wave28-scripts/runbook-var-gate.sh write` → 等 boot 循环（1800s 帽 + reboot + arming）
→ `bash wave28-scripts/runbook-var-gate.sh read` → `bash wave28-scripts/runbook-var-gate.sh verdict <WRITE_RUN> <READ_RUN>`

PERSIST 判据 = 四行全 PASS：marker 内容逐字节、jb marker utc 与 root 一致、64KiB blob
sha256 双端全等、ssh host key 集合全等（host key 在 `/var/root/.ssh/`——rc.jobs.ssh 原句
`-h /var/root/.ssh/ssh_host_ed25519_key`；密钥若每 boot 重生 = /var 未持久的天然确证）。

## 5. 升级（progress.log 置顶原文摘要）

**物理干预（一个按键，零风险）**：长按电源 ~10s 强制重启 → 手机冷启 slot b（v23）
→ 新鲜 loader → 武装中的守望器自动抓会话并完成标记写入。备选：电源+音量下 → fastboot →
`set_active a` → 安卓 → `bash wave28-scripts/runbook-var-gate.sh march`（零刷写回链）。

## 6. 后续工作（下一阶段）

1. **会话恢复后的动作序列**：守望器抓到会话 → 标记写入（会话 1）→ 等 `loader_return_after=1800`
   到期返回 → 服务窗 240s 内**立即**发起会话 2（本轮源码定位：服务窗只有 240s，wave27 式
   "慢慢等下一代"会错过）→ 复读 → verdict。
2. **wave27 §4 "保存窗"模型修正**（见 §2）：下一步实验设计应把"返回后可服务时长"当作
   固定 240s 窗 + usb_ready 门槛，而不是可变脏状态窗。
3. **外来 attach 事故**：`usbipd attach` 的来源未定位（提权 PS 30432 嫌疑）。若复发，
   `usbipd detach --busid 2-2` 即时恢复；建议排查是否有 wave26 时代的 autobind/hunter
   变体仍在提权会话里跑。
4. **logdump 待拉**：手机回安卓后 `wave27-scripts/logdump-pull-v27.sh w28` 可验证 06:40 后
   reboot 是否真发生（§2 模型验证）。
5. 预算：刷写 0/3（零刷写红线全程成立）；时间盒内结论未到手，如实记录。
