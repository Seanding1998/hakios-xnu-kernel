# 外部评审报告三（2026-11-09）

> 审阅者（ChatGPT，本地阅读）基于提交 87bbdaf、阶段 23-26 报告、原始日志、当前 WSL 代码；含三项内存报文验证（不触手机/文件只读）。原文为粘贴归档的三段长文，本档为要点全保真归档（原文过长，结构化重录；全部 file:line 引用以原文为准，均已复核入档）。

## 一、阶段位置认定（审阅者判断，我方接受）

- USB 端点墙：**已解决**（probe24.log 实证：3,336 写完成 / 2,919 应答 / 216,995B 上传校验；两类计数对应不同协议步骤，不得互算成功率）。
- H4 归因边界收窄（我方采纳）：**复位流程缺陷确认，v20 组合改动消除已观测墙**；"GCTL 是唯一根因"缺单变量对照，不追加刷写换取唯一归因。
- 180s 会话帽：**有源码支持**（loader_return.c:459 定时回调 / :432 保存+返回路径）；"en0 驱动死锁"定案证据不足的旧判已被推翻。
- SSH：**未验收**（横幅到手，登录+执行命令无证据）。
- 桌面出画：成立（本轮未独立查验照片/屏录）。

## 二、三个主机侧确定性缺陷（内存报文验证复现，P1×3）

1. **ARP 回复发送者/目标 IP 写反**（`wave21-scripts/loader_talk.py:326 _on_arp`）：回复把请求的 sender_ip 放回发送者字段、target_ip 放回目标字段（RFC 826 应交换）；且 opcode≠1 直接早退 → `arp learned: []` 之谜。修复 = request/reply 分别处理 + 双向报文字节验证。
2. **三次握手最后 ACK 序号差一**（`loader_talk.py:466` SYN-ACK 处理 + `tunnel25w.py:382` wrapper 事后 `tun.seq += 1`）：ACK 在 seq 消耗前发出（0x10000000 应为 0x10000001）；本地 `established` 只证明走到赋值分支。修复 = 握手统一进连接状态机（SYN 序号消耗/SYN-ACK 验证/最终 ACK/状态转换一体）。
3. **其他端口的 RST 误杀当前连接**（`loader_talk.py:450`）：只查源 IP 不匹配四元组，跨端口 RST 使当前连接 CLOSED（`reset by peer` 需回看四元组）。修复 = 四元组 + 长度 + 序号验证先行，无关报文丢弃。

## 三、"建连后停滞"重判（manual-attempt-2.err）

- established 后：tcp_in 冻在 30、3 段未确认、`acked` 字段（实为 (tun.seq-tun.acked)&0xffffffff = 1480 字节跨度，非网络 ACK）冻结、loader 推帧 161→234、en0 心跳 14,673→30,533、环 0 0 → 最终 `reset by peer`。
- **en0 心跳只覆盖 poll；feeder→hakios_net_input→TCP 是盲区**（stage 满丢帧时共享环仍可显示空——`net_fed_dropped` 存在但 netstat 未展示）。
- 字段语义修正：tcp_in 在端口过滤前累计，不能单独代表有效段数。
- sshd 表述修正（我方文档矛盾已改）：exec ≠ LISTEN；两条未决分支 = 逐会话 LISTEN 差异 + 建连后停滞。

## 四、其他修正（全部采纳）

- vnode 运行期真值：init.c `sysctlbyname` 调至 **32768**（init.c:1495；日志 `init: up to 32768 vnodes`）——loader DT 8192 只覆盖 init 前；应记录实际 kern.maxvnodes + 用量曲线。
- XPC 空壳 daemon 降级为候选：lookup 成功 ≠ 风暴消失（客户端可能继续业务请求）；先单服务有界对照（lookup/后续 IPC/CPU/存活）。
- H4 单变量对照缺失如实保留边界。
- timed-ssh 日志仍有 PARTIAL / `OKAYxnuloaderxnuloader` 重复应答 / claim 成功但 getvar 无应答窗口 = 命令事务同步分支，单独标记。

## 五、执行计划（审阅建议，我方采纳为 阶段 26 Phase A-D）

**Phase A（0 刷 0 手机）**：修 ARP / 握手状态机 / 四元组 RST 验证 / DATA+终端 OKAY 事务消费 / Runbook 加固（per-run ID、verdict 新鲜性、退出码门、getvar 身份门、四态处理、loader 期禁 usbipd attach）+ **8 项定向回归**（ARP 字段/reply 学习/SYN-ACK→ACK/错 ACK 不建立/跨端口不影响/ACK 一致性/事务异常识别/旧 verdict 不放行）。闸门 = 回归全绿。
**Phase B（0 刷，v23 真机验证）**：B1 固定实验身份；B2 先验管理通道（固定命令 + 校验上传，再 netmode）；B3 Pipe25.push / Link.on_frame 前后全字段报文留痕（时间/方向/四元组/flags/seq/ack/window/payload/校验和/SND.UNA/NXT/RCV.NXT）；B4 单连接判决表（6 分支：RST→查监听；SYN-ACK+数据推进→SSH 层；三段重传不推进→对照发送与设备输入；ACK 到但本地不动→修主机 ACK；数据到未交 stdout→修 ProxyCommand 排空；USB 失同步→事务恢复）。闸门 = 每次失败必须落入明确分支。
**Phase C（1 刷，条件）**：仅当证据指向内核盲区——分层计数器（poll/stage prod-cons-丢弃/feeder 进出/网络输入成败/TCP 按连接统计）。判别：stage 涨 feeder 不涨 = feeder 块；feeder 涨 TCP 丢涨 = 报文/校验和/TCP 状态；栈收了无应用进展 = sshd/socket；内核回 loader 才停 = 会话生命周期。
**Phase D（1 刷，条件）**：只修 C 锁定分支。用户态镜像修改单独说明写入范围（boot_b 研究授权不自动覆盖其它持久镜像）。

## 六、v0.4 验收门（采纳）

- **最小功能**：uname=Darwin + id 预期 + 本次随机标记完整返回 + SSH rc=0 + stdout/stderr/设备代际/脚本身份归档。
- **稳定性**：同一长会话 ≥3 次独立 SSH 连接 + 一次内容校验传输 + 桌面运行期连接推进 + 客户端正常退出后管理通道仍可用。
- **项目门**：结合已有存储证据完成 /var 持久回归 + 可重复启动/登录/退出/恢复步骤归档。
- 达标才宣告 v0.4；CPU 出画与 GPU 加速分开记录（后者按 v0.5 验收）。

## 七、Runbook 具体问题（采纳）

verdict26.txt 跨运行复用风险（须 per-run ID + 绑定设备身份/退出码/输出）；SSH 验收过弱（分号连接不依赖前命令成功、rc 未入判定）；`set -u` 不够（adb/fastboot 走 `| tail` 丢退出码）；getvar 未作身份门；boot_b 回读固定临时文件名（旧残留风险）；loader 状态误入 usbipd attach 分支（应四态分别处理，loader 诊断期单一 Windows-libusb 所有者）。
