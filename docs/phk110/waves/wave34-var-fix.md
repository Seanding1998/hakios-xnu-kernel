# 阶段 34 · 2026-11-11 · /var 持久化修复：init 重入守卫，v0.4 项目门转绿

> 2026-11-11 00:0x → 02:0x · 阶段 34 修复执行记录 · boot_b 刷写 2 次（均用户物理 fastboot 直刷：首次成功 + 幂等重确认，一揽子授权范围内）+ 零刷写重验链
> 任务书：修 init 二跑 bug（wave31 §6.2 修复单）→ 构建 v24 → 刷写 → 重验链 → /var 判定转绿 → v0.4 项目门。

## 0. 判定（FINAL）

**WAVE34-VAR-PERSIST**（`wave28-scripts/verdict34-var.txt`，2026-11-11 01:09）——v0.4 项目门（/var 持久回归）**转绿**。六行全过：

| 行 | 结果 | 写侧（w34a，gen1，boot+197s） | 读侧（w34b，genA，boot+6min，跨内核死亡） |
|---|---|---|---|
| root marker 内容 | **PASS** | 243 B（utc 1970-01-01T00:03:17Z） | 243 B，逐字节 MATCH |
| marker 设备上尺寸（ls） | **PASS** | 243 B | 243 B |
| marker mtime（stat epoch） | **PASS** | 197（= 08:03:17 帧） | 197（同帧同值） |
| jb marker utc | **STRUCTURAL-NA** | RC2=0，53 B 落盘 | 缺席 = init 每 boot 重嫁接所致（设计使然，见 §2） |
| blob sha256（64 KiB） | **PASS** | `a979e8e1…6895035a`（== 远端盘上 sha256sum） | 同 sha，三方全等 |
| ssh host keys | PASS（弱） | 2 指纹（host `6SkuNg4H` / user `khN1rYtf`） | 逐字相同（每 boot 播种，无判别力） |

**判定语义**：VARFS 证据 = `/dev/ufs_darwin_data on /private/var`（**ramfs 遮蔽消失**——wave31 的双挂叠影不复存在，guard 生效）；写入到读取之间隔着一次**完整的内核死亡**（gen1 被用户物理硬杀重启，比干净返回更严苛）；64 KiB blob 的三方 sha 全等在统计上排除任何"同会话自写"可能。跨 boot 合法性四重：亲历的总线历史（gen1 00:44:30 启动 → 死亡 → genA 00:58:50 启动）+ BOOTPROOF（up 0:06 / pid1 lstart 08:00:49 / marker mtime 197）+ mtime 197 与写侧同值 + blob sha 三方全等。

**canonical 工具的机械输出与判定文件的关系（透明入档）**：未改动的 `verdict-var-v28.py` 对同一对工件输出 REGRESSED（3/4 行），全文原样保存为 `verdict28-var-w34-mechanical-3of4.txt`。其两处 artifact 由 `wave34-scripts/verdict-var-v34.py`（判定 runner）文档化修正：①read 侧段捕获把远端回显 `rc=0`（5 B）卷进 ==MARKER-ROOT== → 248 vs 243 的假 DIFFER（设备上文件实为 243 B，同捕获内 ls 为证）；②jb marker 行探测的 /var/jb 是 init 每 boot 清空重嫁接区（init.c：`empty_tree + rmdir + graft_tree`，注释 "the prefix is grafted anew at every boot"）——任何健康系统里该行都不可能过，探的是刷新机制不是卷。blob + hostkeys 行 v28 原样全过。

## 1. 修复（主增量：init.c mount_writable 防重入 guard）

wave31 判决表分支③（主判）的修复单落地，三文件最小增量：

- `kernel/userland/libmini/mini.h`：`SYS_statfs64 = 345` 进枚举；`struct statfs64`（按 bsd/sys/mount.h `__DARWIN_STRUCT_STATFS64`，2168 B，f_mntfromname@1112，hfs_test.c 的 +72/2168 实测偏移互证）+ `mstatfs64()` 声明。
- `kernel/userland/libmini/mini.c`：`mstatfs64()` = `SC(SYS_statfs64, path, fs, 0,0,0,0)`。
- `kernel/userland/src/init.c` `mount_writable()`（L913-928，guard 在 banner 行之后、`mount_data_volume()` 之前）：statfs64 读 `/private/var` 的 `f_mntfromname`，是 `/dev/ufs_darwin_data`（卷已在挂）或 `ramfs`（首跑回退已在挂）则置 `var_kept`、打一行 `  /private/var already mounted from …; the re-entry guard keeps it, skipping the fallback` 并直接返回——二跑不再把回退 ramfs 叠上遮蔽卷。

两处工程教训（如实入档）：
1. **C prototype-scope 陷阱**：`struct statfs64` 首次出现在函数原型里时拥有原型作用域，其后的文件级定义成了另一个类型 → "conflicting types"。修法 = 结构体定义放原型之前。
2. **clang known-library-function**：`statfs64` 是 clang 内建库函数名，裸定义触发 "conflicting types"（与声明内容无关，AST dump 两个 FunctionDecl 打印相同仍判 invalid）。改名 `mstatfs64` 解决。

**shim 增量（次项）= 如实跳过**：任务书预期 "vendor 打印走 shim SerialPort（我们的代码）"，实测 **BootShim（graft 的 shim 输入）= 240 字节纯拷贝跳板（BootShim.S：FD 搬运 + 可选 XNUP payload 搬运 + 跳转），无任何打印路径**。vendor 0xB/0xC 墙印真实路径 = `uefi-udon/Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib/`（我们的代码没错，但编在 FD 里）。改它 = FD 重编 → FD 字节锚（8924cb67，v11 以来从未变过）失效 + 全 FD 面漂移风险，与 "有界" 相悖。限频设计段见 §5；FD 保持逐字节复用。

## 2. v24 构建（59/59 自检）

- root.apfs 重建（v13 配方原样：`FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh`；userland/src 自 2026-11-04 冻结、零提交漂移，唯一语义增量 = init.c guard；ssh key/plist 为每轮构建再生性输出）：`4abd3d5468c81b6e → 61323255adc3153e`。
- payload v24 = **`c9e0943b`**：v23 payload 七条目逐字节复用（loader.efi `0ade78b5` / kernel `abecd557` / resident / cmdline 473B / kernel.ver / usb），**唯一 delta = ramdisk = 新 root.apfs**（mkpayload 断言逐条目对拍 + verify 双层钉死）。
- graft v24 = **`91d8f1a4`**（FD `8924cb67` + shim `108ce972` 锚点校验后打包）。
- **verify 59/59**（`wave34-scripts/verify-udon-hakios-v24.py`，v23 全部检查保留 + ramdisk==root.apfs 文件对拍 + loader 全套 阶段 24-26 机制标记 + PAYLOAD_BASE pin @RVA 0x2374 + vbmeta/footer/192MiB 全套）。
- 树注记：`userland/system.apfs` 因 FLASHBOOT=1 顺带重编（`93cca9b6 → 7f6e9c07`），**不进 payload、不参与任何交付**（darwin 分区上的卷仍是 wave16c/18 时代的 dd 原件）；`userland/flashboot.apfs` 同理重编（`ec674648 → a0896cab`）但 payload 的 resident 条目仍用 v23 提取件逐字节。

## 3. 刷写（boot_b = v24，1/1 次）

- 相位：手机在 v23 循环里已退化为死 devnode（0000:0002 描述符失败，wave21.5 同款，无 d00d/安卓/adb）——**用户物理强启直达 fastboot**（电源+音量下，ABL gadget `18d1:d00d Android` 上总线 2-2，与 xnuloader 串号区分）。
- attempt 1 失败（无损，如实登记）：rev1 脚本把 Git-Bash `/c/` 路径传进 WSL fastboot（需 `/mnt/c/`）且管道掩盖错误码 → flash 未执行，set_active b + reboot 把手机送回 v23 循环。
- attempt 2 成功（rev2：路径修正 + OKAY/退出码断言 + attach 前先唤醒 distro）：taro 门 ✓ slot 门 ✓ sha 钉死 ✓ → **Sending OKAY 4.795s / Writing OKAY 0.548s / set_active b / reboot 00:43:37** → boot_b = v24 `91d8f1a4`，slot b 循环重启。

## 4. 零刷写重验链（march→write→cycle→read→verdict）

| 步 | 时刻 | 结果 |
|---|---|---|
| write（w34a，gen1，boot 00:44:30） | 00:46:40-00:47:03 | **全绿**：HIT 后 marker 包 rc=0（四步共 11 s，gen1 隧道极快），RC1/2/3=0；双 marker（/var 243B utc 00:03:17Z + /var/jb 53B）+ blob 65536B 读回 sha == 远端盘上 sha256sum（`a979e8e1`，三方全等）+ hostkey 双指纹；uname 横幅 = v24 gen1 |
| boot cycle（内核死亡） | ~00:5x | gen1 被用户物理硬杀重启（电源+音量下 → fastboot；v24 幂等重刷确认）→ genA 00:58:50 启动——比 1800s 帽干净返回更强的死亡形态（瞬时断电级） |
| read（w34b，genA，BOOTPROOF） | 01:04:41-01:04:53 | **全绿**：HIT 即中（12 s 包）——root marker 243B 逐字同 + blob sha 三方全等 + VARFS = ufs_darwin_data（ramfs 消失）+ up 0:06 / pid1 lstart 08:00:49 / marker mtime 197 |
| verdict | 01:06-01:09 | v28 机械件 3/4（两 artifact 见 §0）→ **verdict34-var.txt = WAVE34-VAR-PERSIST** |
| 服务窗行对（白捡） | 01:29-01:35（窗 1，已废）→ 01:59:53（genB 窗，**CLOSED**） | 窗 1：probe24 ep#1 在 genA 仍在会话中把 in-session mirror（13,776B haki 泵帧）消费掉（stage-once 语义）→ 后续全 0 B（cap 再证漂移 +36s）。窗 2（genB）：`probe24 --once` 首拉即中 **1,066,176 B** console（内容检查 5/6 标记 OK，存 `wave34-scripts/udon-console-v24-genB-015953.txt`）——**init 双跑行对完整到手（wave31 §6.2 待补项闭环）**：`=== init: process 1, started as /redwood/sbin/init ===` **×2**（双跑直接目击）+ `-- writable filesystem --` **×2**（L433/L947，两代间距）+ 第一遍 `HFS Plus from /dev/ufs_darwin_data, kept between boots` + 第二遍 **guard 行逐字** `/private/var already mounted from /dev/ufs_darwin_data, kept between boots; the re-entry guard keeps it, skipping the fallback` + `Resource busy` **×0**（wave31 时代的 EBUSY→ramfs 路径零执行）。六分支判决表③主判 = 源码 + 真机 console 双重定案 |

## 5. 后续工作（下一阶段）

1. **USB 对堵死自愈设计段**（任务书明确只出设计，不写代码）：用户屏摄证据 = 0xB（ep3 bulk-IN 环满）与 0xC（ep2 bulk-OUT 未配置）两面墙轮刷盖 UI——端点号不同 = **ep3 出口堆满先于 ep2 入口被注销**（墙的因果次序第一手证据）。拟议方案：无消费者停止排队（TX 环满即停 submit，不再泵帧进 ep3）+ 堵死确认后对整对端点 END_TRANSFER + 重配置（重建而非单边清理）。落点 = loader USB 服务器层（我们代码），不动 vendor 栈。视觉刷屏治理（本阶段跳过的 shim 限频）落点 = `FrameBufferSerialPortLib`（FD 内，重编 FD 时一并做：同串连发 ≤3 行后抑制 + 累计计数行）。
2. **init 双跑行对终验 = 本阶段已闭环（§4 末行）**：genB 服务窗首拉 1,066,176 B console（`wave34-scripts/udon-console-v24-genB-015953.txt`）——`=== init: process 1 ===` ×2 + `-- writable filesystem --` ×2 + guard 行逐字 + `Resource busy` ×0。配方留档（未来同型取证）：返回后 240s 服务窗首拉 oem log，head 字节判别（haki 帧头 = 会话中垃圾，`== XNULOADER` = 返回后 console；stage-once，会话中误拉即废窗）。
3. **v0.4 项目门状态**：/var 持久回归 = **PASS**（本阶段）；可重复步骤归档 = march→write→cycle→read→verdict 全链再走一遍且工件全留痕（wave28-scripts/*w34a*/*w34b* + verdict34-var.txt + 本文档）。v0.4 三门全绿，**宣告随即在文档与仓库同步发布**。
4. **Persisted usbipd 绑定清理（Android 相位前必做，需管理员）**：`269e72e4`（ADB）/ `ebd3f1a8`（一加 Ace 2）/ `f474f60e`（Android）/ `b67ab332`（xnuloader，wsl --shutdown 后又出现）/ 两条死 devnode（`275b7151`、`a1b81719`）。
5. **wave28 工具的两处捕获语义修正**（如再跑 /var 门）：verdict-var-v34.py 的两条修正可直接回灌 mark-var-v28.py（section 捕获剥尾部 rc 回显；jb marker 换位到 /var/db 或 /var/root——持久面）。
6. **kernel 树工作区**：`userland/{libmini/mini.h,libmini/mini.c,src/init.c}` 带 wave34 修复（未提交，随本阶段 git 提交）；init 修复产物 = root.apfs `61323255`；重编 root.apfs 用 v13 配方（`FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh`）。

## 6. 事故登记

- **00:32 wsl --shutdown 一次（禁令生效前）**：当时收到的纪律是 wave31 配方（抢设备 = detach + wsl --shutdown）；构建落盘 /mnt/c 后执行以断 b67ab332 auto-attach 之根。收到此后明确的操作约束（有并行工作共用 WSL）后未再犯，全流程改 detach-only。**b67ab332（xnuloader）持久绑定仍在 Persisted 列表**（wsl shutdown 后又回来了/未清干净）+ `269e72e4`/`ebd3f1a8`/`f474f60e` + 两条死 devnode——下一阶段 Android 相位前仍需管理员清理。
- **00:41 刷写 attempt 1（无损）**：rev1 脚本把 Git-Bash `/c/` 路径传进 WSL fastboot（WSL 只认 `/mnt/c/`），且 `| tail` 掩盖 fastboot 退出码 → flash 未执行但 set_active b + reboot 已把手机送回循环。rev2 修正（路径 + OKAY/退出码断言 + attach 前先唤醒 distro——`usbipd attach --wsl` 在零 distro 运行时直接报错）后 00:43 一次通过。教训：fastboot 步必须 exit-code + OKAY 双断言，绝不管道吞码。
- **01:29 服务窗窗 1 报废（stage-once）**：probe24 ep#1 在 genA 仍在会话中拉走了 in-session mirror（13,776B haki 泵帧），后续 post-return 拉取全 0 B。配方修正入档 §5.2（首拉判别 head 字节）。cap 模型漂移再证：预测返回 01:28:50，01:29:26 仍 in-session（+36s）。
- **probe24 工具 bug（如实登记，未修）**：每次 attempt 落盘后 `attempt crashed: TypeError('not all arguments converted during string formatting')`——save 之后的一条日志格式化缺参，不影响落盘文件，但令 `--once` 的 got_log 永假、循环跑到 deadline。下一阶段修（wave24-scripts/probe24.py）。
