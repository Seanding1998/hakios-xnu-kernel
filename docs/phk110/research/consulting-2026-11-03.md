# 外援咨询记录 — 2026-11-03（ChatGPT 转答，主代理逐条裁决）

> 性质：外部 AI 意见 = **待验证假设来源**，非真理。凡 upstream 主张已在本仓克隆（2026-11-02 depth-1）逐字核验 ✓；凡属推测标"待实测"。

## Q1 GPU（v0.5）
- 外援：KGSL shim → Turnip → Zink 最短；Mesa 官方"freedreno Gallium 不支持 KGSL"；pivot 条件 = shim 膨胀即改 tu_knl_darwin；两个实机先例（HakiOS=msm/freedreno，UniXNU=Turnip@Nothing Phone 2 SM8475）；无第三例"原版 Turnip-KGSL 无修改跑通"。
- **主代理裁决**：**主路线改判 upstream freedreno 架构**（CHANGELOG ✓ "Mesa 25.0.7 freedreno，GL=1 smooth，wallpaper drawn"——参考机 GPU 渲染已达成，v1.0=等效 upstream，同架构风险最低）；Turnip-KGSL/Zink 列为实验备选 + 采纳其止损条件。待实测：a6xx→a7xx 驱动 delta、KGSL shim 在 Darwin ABI 的真实补差量。

## Q2 Darwin 用户空间（v0.4）
- 外援：**DEVELOPMENT ≠ 安全自动关**（`config_enforce_signed_code` 在 KERNEL_BASE；cs_enforcement_disable=1 可用需 debugger 门）；HakiOS 同版本实测 = 显式 stub（miniamfi 类）；dyld4 理论可无 cache，但 stock IPSW 用户空间应**保留原 shared cache**。
- **裁决**：全部采纳（与 upstream 源码级主张一致性强）。待实测：cs_enforcement_disable=1 在我们 boot-args 注入链路上的有效性。

## Q3 IPSW（v0.4 物料）
- 外援：锁定 `iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw`（arm64，禁 arm64e）；同 set 一致性（shared cache/trust/identity）；可选 PAC probe（ID_AA64ISAR1_EL1 等）作未来门槛。
- **裁决**：强采纳——**upstream qemu.md 原文核验 ✓ 同一份 IPSW**。物料需求已通知用户。

## Q4 存储（v0.4 深水区）
- 外援：APFS 不做 v0.4 门槛——**Apple OSS HFS+（hfs-627.100.6）编内核 + UFS journaled HFS+ /private/var**（HakiOS 10-29 实机：12GB、重启保留、Sileo/SSH 可用）；块存储分层 IOBlockStorageDevice→IOMedia→GPT→VFS；linux-apfs-rw 反向移植无先例不进主线；真深水区 = UFS+SMMU/DMA+write ordering；UniXNU K60/SM8475 有 UFS root+APFS Data seed 但持久 Data 多机未验证。
- **裁决**：强采纳——CHANGELOG ✓（hfs-627.100.6、12GB journaled 保留、GPU/存储全部实机）。v0.4 存储计划重写为 S0-S8 分步（见 PLAN）。

## Q5 Windows（v1.x 远期）
- 外援：SM8475 Windows Boot 已证实（pong ✅、b4q ✅），但 udon/Ace 2 无公开 entry；senna_bc=Display ✅/Windows ❌；Windows"能用"=驱动巨山（Adreno WDDM…）；Mu-Silicium 仍活跃（v4.1）。
- **裁决**：情报采纳。v1.x 段已更新：只保留 Mu-Silicium boot 实验位，不排 Windows 驱动 wave，直到 udon 实机进 Windows PE。

## 对排期的净影响
1. v0.4 最大的"深水区"从 APFS 逆向 → **UFS transport + SMMU/DMA + write ordering**（可控数倍）
2. v0.4 物料现在就能锁：用户下载 iPhone X 16.5 20F66 IPSW
3. v0.5 主路线 = upstream freedreno 同架构适配（低风险），Turnip 路线降为备选
4. Windows（v1.x）从"待评估"变"已证实可行但本机未证"——维持实验位
5. 新情报：UniXNU-udon（本机同款）已 native UFS → iPadOS 用户空间 117 进程——v0.4 路径先例强度上调
