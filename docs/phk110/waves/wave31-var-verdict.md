# 阶段 31 · 2026-11-11 · /var 持久化回归判定：内存盘遮蔽了真实挂载

> 2026-11-10 20:56 → 24:0x（时间盒内）· 阶段 31 执行记录 · 零刷写（0 次刷写，fastboot 仅 march 内 getvar/set_active/reboot）
> 任务书：接续 阶段 28 未竟的 /var 持久判定 = v0.4 宣告前最后一道门。判定优先于一切。
> 上游：阶段 28 两轮（round 2 于 11:28 判定仍缺席）→ 用户插回手机 → state=android → 本阶段 march 复工。

## 0. 判定（FINAL）

**WAVE28-VAR-REGRESSED** —— `wave28-scripts/verdict28-var.txt`（2026-11-10 23:25:09 落盘）：

| 行 | 结果 | 写侧（w31a，gen2） | 读侧（w31b2，gen3，跨 boot） |
|---|---|---|---|
| root marker 内容 | **FAIL** | 243 B（utc 1970-01-01T00:09:47Z） | 5 B（文件不存在） |
| jb marker utc | **FAIL** | 1970-01-01T00:09:47Z | MISSING |
| blob sha256（64 KiB） | **FAIL** | `428909c4…09f5`（65536 B，与远端 `sha256sum` 逐字对拍全等） | MISSING/0 B |
| ssh host keys | PASS（弱） | 2 把（ed25519 pub + authorized_keys） | 2 把逐字相同（每 boot 播种所致，无判别力） |

**v0.4 项目门（/var 持久回归）未过 —— 不宣告 v0.4。** 阶段 28 的"判定 pending"行就此收尾：判定已到手，方向为 REGRESSED，机制已破到源码行级（§2）。

读侧合法性（为何 w31b2 是真跨 boot 读）：写入发生（22:20:05-22:22）时 kernel = gen2（boot ≈22:10:30，launchd lstart 08:00:49）；读取发生（22:47:59）时 kernel = gen3（boot 22:45:35，uptime 2 min）——BOOTPROOF 判别成立。同会话假读（w31b 第一次，22:34:20，读侧 pid1 lstart 08:00:49 早于 marker mtime 08:09:47）已按证据丢弃，未进入 verdict。

## 1. 过程时间线（全部前台短切片，零 detached；progress.log 逐行在案）

| 时刻 | 事件 |
|---|---|
| 20:56 | 接手。卫生检查：零残留进程、安卓 2-2 Shared、adb 通、槽 b + boot_b=v23 |
| 21:32-21:35 | **march（w31-march）**：logdump 顺带拉取 + adb reboot bootloader + taro/槽门验身 + `set_active b` + reboot。T0=21:35:30 |
| 21:41:50-21:42:04 | write 切片：knock **HIT**（T0+388，gen1 kernel+148s，Darwin 22.5.0 应答）但 marker 包 recon 失败（`oem netmode on` 无应答）——back-to-back 隧道把 netmode 泵留在 ON，IN 环被泵帧淹没 |
| 21:43:11-21:43:39 | 手动补发 write 包：getvar → **PARTIAL ×12**（泵帧堵死命令通道）→ 判本会话不可用，任何会话都能承载 write，等下一代 |
| 21:46-22:13 | 静默（服务窗期间探测会续 240s 窗；两次帽预测 22:09:30/22:21 均未见节点掉落——掉落间隙短于 10s 轮询） |
| 22:14:07 | 切片 A：knock **HIT**（gen2，活会话）→ marker 包 recon：ssh 真跑通了，死因 = **远端 shell 是 zsh**，`echo ==RECON==` 的行首 `=` 触发 zsh `=cmd` 展开整行中止。工具首跑真机暴露的首个 bug |
| 22:15-22:16 | 修复：所有 section 标记加引号（语义零变化，verdict 解析器不动） |
| 22:16:53-22:17:00 | write 包 v2：**recon rc=0（三件套落盘 RC1/2/3=0）**；blob 读回 62104/65536（隧道泵丢 ~3.4KiB）；hostkeys find 静默空 + fingerprint() 空集崩溃 |
| 22:18-22:19 | 探明 /var/root/.ssh 实况（.pub 存在，find 是假阴性）+ 远端有 sha256sum/cksum/ssh-keygen |
| 22:20:05-22:22 | write 包 v3（最终）：marker 重写（utc 00:09:47）+ hostkeys 显式路径 291 B + **远端盘上 sha256** 298 B 到手；blob 改 **4×16KiB 分块**逐块重试 → 全部首试精确，拼装 65536 B，**本地 sha == 远端盘上 sha（428909c4…）传输完整性三方全等**。WRITE RUN（w31a）闭环 |
| 22:23-22:34 | 等节点掉落：10s×9min 零掉落（两次帽预测皆过 → 改用带内代际判别策略） |
| 22:34:20 | read 切片（w31b）#1：HIT → 读包 rc=0 → **BOOTPROOF 判别：同会话假读**（pid1 lstart 08:00:49 < marker mtime 08:09:47；uptime 23min）→ 丢弃 |
| 22:35-22:46 | 静默。源码取证：sysctl/ls -lT 机上不可用 → BOOTPROOF 升级为 pid1-lstart vs mtime + stat %Y |
| 22:47:59 | read 切片（w31b2）：HIT（gen3，boot 22:45:35）→ 读包 rc=0 → **markers 全缺席**（uptime 2 min） |
| 22:48-22:59 | 复核 ×2（uptime 3 min / 11 min）：markers 仍缺席；**mount 表证据：hfs（ufs_darwin_data, journaled）与 ramfs 双双叠挂 /private/var，ramfs 在上遮蔽；df=ramfs** |
| 22:57-23:24 | oem log 取证尝试 ×3：第一次 0 B（会话中 mirror 空）+ 二三两次被 §4 的 usbipd 抢占事故干扰；23:00 的四次拉取内容 = en0 泵帧（haki 魔数），非控制台 |
| 23:05-23:12 | 源码级机制定位（§2）：init.c userland/src/init.c mount_data_volume()/mount_writable() |
| 23:25:09 | **verdict-var-v28 → verdict28-var.txt = WAVE28-VAR-REGRESSED** |
| 23:53:40 | gen4 帽到期返回（用户目视确认重启）——服务窗 240s 期间 agent 被重启打断，窗错过 |
| 00:00-00:02 | 补拉 ×2：probe24 通道干净但 getvar 无应答（gen5 已入 exec、pair un-armed）→ 按指令不再等，init 双跑行对登记为待补验（§6.2） |

## 2. 机制（源码行级）

### 2.1 直接机制：ramfs 遮蔽 hfs 的双重挂载

`kernel/userland/src/init.c`（gen 已刷入 v23 的 init 链）：

- `mount_writable()`（L905）：`var_kept = mount_data_volume();` → 成功走 kept 分支；**失败走 else 分支 `mount("ramfs", "/private/var", 0, NULL)`**（L929-931，"mount a memory filesystem on /private/var"）。
- `mount_data_volume()`（L834）：boot-arg `var_hfs` → `mount("hfs", "/private/var", ...)`；失败打印 `HFS Plus from /dev/…: <err>; a memory filesystem instead, empty at every boot` 并 return 0。
- 全树唯一 ramfs 作者 = 此 else 分支（内核侧 grep ramfs 零挂点；restore_var 有 var_store=1 门且 v23 cmdline 无此 arg）。

### 2.2 机器侧证据（gen3，活会话内实测）

```
MOUNTLINE:
/dev/ufs_darwin_data on /private/var (hfs, local, journaled)
ramfs on /private/var (ramfs, local)          <- 后挂者遮蔽，df 见下
DF: ramfs 1.5Gi 159Mi … /private/var
markers 在 gen3 uptime 2/3/11/13 min 四次读取全部缺席
```

hfs 在 mount 表且在前（先挂）= **数据卷机制本身活着**（v18/v20 时代的 S6-S8 回归全绿与此相容）；ramfs 在后 = 可见 /var 是每次 boot 清空的内存盘。

### 2.3 主判模型：mount_writable 二次执行（行对终验待补，登记在案）

mount 表要求 hfs 先挂成功、ramfs 后挂——但代码里 ramfs 只在 hfs mount **失败**时挂。单次 pass 逻辑上不可能两者并存 → **mount_writable 执行了 ≥2 次**（第一遍 hfs 成功；第二遍 EBUSY → else → ramfs 遮蔽）。旁证：
- wave23 v19 已记录 init/launchd 域不稳（init[1] 837 wakes/s spin）；
- march 顺带拉取的旧 logdump 尾部显示**同一会话内两次 en0 配置行**（08:01:15 与 08:03:49，中间夹 launchd "uncorking" 序列）= 启动序列重放先例；
- `main()`（L1531）只有一个 `mount_writable()` 调用点且 "init FILE" 命令执行器模式不调它 → 二次执行 = pid1 级重跑（init 亡后重启或等价机制），gen4 控制台的 `=== init: process ===` 头计数与 `-- writable filesystem --` 行对直接裁决。

### 2.4 写入为何丢失（判决表分支归属）

gen2 与 gen3 同镜像 → gen2 同样在 boot 后 ~3 min 内被 ramfs 遮蔽 → **gen2 587s 的 marker/blob 写入（RC1/2/3=0 + sync）全部落进 ramfs** → 随 kernel 死亡蒸发。数据卷上不存在 wave28 痕迹（可由 Android 侧 12 GB 原始读字符串搜索终验，本阶段未做——用户协助非必需，见 §5）。

## 3. 六分支式判决表（REGRESSED → 故障环定位）

| # | 分支 | 判 | 依据 |
|---|---|---|---|
| ① | var_hfs boot-arg 缺失 → mount_data_volume 静默 return 0 → 全 ramfs | **排除** | mount 表 hfs 在（说明首挂发生）；历史 S6 "kept between boots" 行在案；march 的 cmdline 沿 v22 字节含 var_hfs |
| ② | 数据卷不存在/不可写 → 首挂失败 → 全 ramfs | **排除** | mount 表 hfs journaled 在挂；v18 S8 卷写 + 安卓侧 sha 改写先例 |
| ③ | **hfs 首挂成功后 mount_writable 二次执行 → EBUSY → ramfs 回退遮蔽** | **✅ 主判** | 双挂共存的唯一代码路径；else 分支是唯一 ramfs 作者；旁证 2.3；gen4 控制台行对落锤（§2.3） |
| ④ | 外部子系统（内核/launchd 域/rc job）挂 ramfs 遮蔽 | **排除（弱）** | 内核 grep 零 ramfs 挂点；restore_var 有 arg 门；rc.jobs.ssh 只跑 sshd |
| ⑤ | 写路径本身不持久（sync/journal 丢失） | **不适用** | 写从未到达卷（进的是 ramfs）；v18/v20 卷写持久先例仍然成立 |
| ⑥ | 卷内容其实持久、只是可见性被遮蔽（"假 REGRESSED"） | **排除** | gen2 的写在被遮蔽后进行（同镜像 ≤3 min 遮蔽 vs 587 s 写入），从未触卷；可见 /var 的内容跨 boot 确实不保留 = 验收语义本身 FAIL |

**结论表述（进 STATUS）**：/var 持久化在 v23 上的真相 = 数据卷活着、init 双跑把回退 ramfs 叠挂在其上、**可见 /var 是每 boot 清空的内存盘** ——验收语义（重启后 /var 内容保留）FAIL；修复方向 = mount_writable 防重入 guard（已挂检测，statfs f_mntfromname ~5 行级）或根治 init 二跑（wave23 init-spin 遗案）。

## 4. 事故登记

**23:12 usbipd 持久绑定 auto-attach 抢占（wave13 footgun 复发，非 07:30 幽灵）**：本阶段源码取证的 WSL grep 调用唤醒了 WSL distro → **Persisted 绑定 b67ab332（xnuloader，wave26 时代遗留）自动 attach** → VBoxUSB 抢占 ~7 min（probe24 LIBUSB_ERROR_NOT_SUPPORTED / ACCESS）。处置：`usbipd detach --busid 2-2` + **`wsl --shutdown`**（非管理员 `unbind` 被拒：Access denied）。处置后：d00d 回 Shared，**b67ab332 已从 Persisted 消失**（wsl shutdown 带走）；但出现了**新 Persisted 绑定**（`ebd3f1a8` 一加 Ace 2 + `269e72e4` ADB Interface + 两条死 devnode）——**下一阶段 Android 相位前需管理员 PowerShell 清理**，否则 adb 通道会被同款抢占。教训入档：**loader 相位存活期间禁 WSL distro 唤醒**（等价于禁 usbipd attach 的推论条款）。

## 5. 判定通路资产（本阶段新增/修复）

| 件 | 变更 | 验证 |
|---|---|---|
| mark-var-v28.py | ①section 标记加引号（zsh `=cmd` 展开防御）②hostkeys 改显式路径（find 假阴性）③blob 真字节从 .out 回读（ssh_step 返回解码 str 的坑）④fingerprint 空集防护 ⑤READ_CMD 加 BOOTPROOF（uptime/pid1-lstart/marker-mtime）+ VARFS（df 行）+ disksha | py_compile ✓；真机三跑（write v3 rc=0 全绿） |
| blob 分块拉取法 | 4×16KiB dd + 逐块重试到尺寸精确 → 拼装后本地 sha 对拍远端 sha256sum | 4 块首试精确；三方 sha 全等（长流直读必丢 ~3.5KiB，两次独立复现） |
| verdict-var-v28.py | 无改动（原判定管线直接行使） | 真机输入下四行表确定 ✓ |
| hunt-var-v28.py / runbook | 无改动（切片化使用：直接驱动 hunt + deadline ≤9.5 min 前台运行） | 本阶段 5 个切片 |
| probe24.py | 无改动（--once 行使） | 服窗窗 mirror 语义确认：会话中 stage = net 环垃圾（23:00 文件为证），仅 post-return 有效 |

**未做（如实）**：Android 侧 12 GB 卷原始读终验（wave28 markers 不在卷上的直接实证）——需用户物理协助进 fastboot；本阶段判定不依赖它（分支⑤已由镜像对称性 + 源码闭死），列为可选复核。

## 6. 后续工作（下一阶段）

1. **修复单（v0.4 项目门重验的最小路径）**：mount_writable 防重入 guard——`if (statfs("/private/var").f_mntfromname == 已挂) skip`（~5 行）或根治 init 二跑；修后一次零刷写重验（march → write → boot cycle → read → verdict）即可把项目门转绿。
2. **init 双跑行对终验（本阶段登记为待补）**：gen4 服务窗（23:53:40-23:57:40）被 agent 重启打断错过；00:00-00:02 两次补拉均 getvar 无应答（gen5 已入 exec、pair un-armed；oem log mirror 仅 post-return 有效——会话中 stage 出的是 en0 泵帧，23:00 四文件为证）。下一任一世代返回后的 240s 服务窗内 `probe24 --once` 即可拿到：`-- writable filesystem --` 出现次数（×2 = 双跑定案）+ `kept between boots` + `Resource busy; a memory filesystem instead` 行对 + `=== init: process ===` 头计数。若 console 只有一遍 init，④分支重开（找 ramfs 真作者）。**注意：gen 生命周期与帽模型不齐（两次帽预测落空 + gen3 超预测存活），拉取前先用 SSH uptime 探明该代相位，勿按预测窗盲等。**
3. **Android 相位前**：管理员 PowerShell 清 Persisted 绑定（`269e72e4`/`ebd3f1a8`/两条死 devnode）；USB 事故恢复配方 = `usbipd detach --busid 2-2` + `wsl --shutdown`。
4. **可重复步骤归档**（v0.4 第二门）已部分达成：march→write→cycle→read→verdict 全链本阶段实跑一遍且逐步留痕（progress.log + 本文档 §1 时间线）；REGRESSED 修复后的重验跑将把该链再走一遍并转绿。
5. gen 间会话寿命：gen1 ~2-30 min（通道堵死不可用）、gen2 满 1800s 帽、gen3 13+ min 存活至今——**cap/寿命模型仍不齐**（两次帽预测落空 + gen3 超预测存活），重验前值得拉 logdump 对钟。
