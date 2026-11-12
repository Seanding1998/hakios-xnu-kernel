# 生态普查 2026-11-11：同类 HakiOS/UniXNU 移植今日进展

> 普查由只读调查完成（零设备纯准备工作，gh api + WebSearch，物证纪律：一律 GitHub API ISO 时间戳）。
> 调查窗口：2026-11-10T00:00Z 起。上游 F16 普查（docs/research/f16-k60-sm8475-census.md）的增量更新。

## 1. 今日有实质进展的线

### 1.1 K60 线（mondrian / SM8475，与我们同 SoC）——今日全场最活跃

**Emilelu/UniXNU-mondrian（主线）14 commit（11-10T14:01Z → 11-11T03:57Z）**：
- 触控 Goodix m11a：电源链打通+固件命令协议 `4dc48c6e` → 内嵌 config 三阶段下载 `9f9fff73` → config 偏移修正 2 字节（1486→1488）对齐实机 `9d058fe7` → **config 修正后芯片 ack 全通** `2ae99990`（17:35Z）
- launchd 链：xpc 缓存目录绑定 `2101281b`/`20a3842b`、合入 yibiya 缓存链+诊断工具 `4653cf58`
- **Metal 客户端装载链突破（内核侧）**：`05765736` 0404 补丁——51MB Metal bundle 从 FAT payload 部署到 Data 卷、bind 到 /System/Library/Extensions；`29827f51` init blob v24dp——**实测 launchd pid 282（syncdefaultsd 崩溃），日志 122,685B/1939 行**
- 11-09 README 基线对照：launchd 稳定（禁 8 个 App-cryptex job）、锁屏/SpringBoard ✅、背光 DCS ✅、UFS/APFS 三窗 ✅；**GPU scanout 仍 ❌（卡 libPongAdrenoPlatform.a 的 -force_load 作用域）**
- release 仍 v0.1.2-first-frame（11-09），今日无新 release

**yibiya/UniXNU-mondrian（新协作者，upstream-fix 分支 28+ commit 至 11-10T14:12Z，tip `522c6ead`）**：
- **120Hz 生效** `1285ccf0`；按键 `7e13afd8`、触摸 SE 门控 `9c25b7f`、无按键自动回 fastboot `03c7c3dc`
- Data 窗/用户态难点：2GiB Data 窗安装器 `53ef046a`、IPSW resource fork 修复 `96008141`、seed 卷 UUID 绑定 `6295ab44`、dyld 指向 union 挂载共享缓存 `640e02c4`、**launchd prelink helper** `522c6ead`、pid 26 shared-region 诊断 `69b7cfda`、公开仓可构建化 8 补丁 `2c9eac9e`
- 注：Emilelu 引用的 "yibiya/upstream-fix" 是分支非独立仓（404）；该仓 pushed_at 11-11T12:43Z 有推送动作但 tip 未动

**与我们的直接交叉**：Emilelu 仓 **issue #3**（Seanding1998 于 11-10T15:21Z 开，open，0 回复）= 我们 wave20 的 launchd 定位与双层修复（hw_target= boot-arg fallback，Boot #25）。**截至查证时点 Emilelu 未回应**；其 15:50Z 的 merge 标注来源是 yibiya 分支，因果无法断定。

### 1.2 UniXNU 官方 org（unixnu.com 背后，F16 普查漏网的一整条线）

`UniXNU` GitHub org：2026-10-19 创建，**32 个组件化公开仓**，主线 = 小米 Pad 6S Pro（sheng / SM8550）。仓内无 SM8475 设备。
- **今日 X 宣布："macOS 27.3 on Xiaomi Pad 6S Pro with touchscreen and almost everything working"** [WebSearch 转述，与 GitHub 证据互洽]
- `UniXNU/UniXNU`（框架）今日 20+ commit：macOS 27.3 内存窗/内核策略/GPU 栈 `f29c06a7`/`268bfa1c`、**GMEM tile 渲染为默认渲染模式** `01eb8692`+`e5f76cfe`、Turnip row-pitch perf `6061e102`、metal2vulkan `de46854a`
- **`UniXNU/Adreno740`（原生 XNU Adreno 740 GPU 驱动）今日 8+ commit**，最新 `2a91aa1a`（15:27Z）：BV 线程进度计入 GPU 进度、stall handler 不动正常 GPU、失败映射记录、ring switch CP 状态保持、GMEM/pool 内存管理。配套 AdrenoPM4 / AdrenoFirmware / AirNir（PM4 编码、GMU 固件 HFI、AIR→NIR→IR3 编译器套件，10-24 建）
- `UniXNU-sheng`：GPU governor 休眠可见性 `abfc15a6`、**wifi-aj=2 无人值守入网** `c5ffb46d`、WiFi 字节请求免 copyout、低 DRAM bank 采纳记录
- `QcaBluetooth`（WCN7850）：macOS 27.3 daemon 适配器 `548444ae`、UART clock 停摆时控制字节排队修复 `986d6319`
- `Ath12kWifi`：RX 计数器诊断、包元数据移出 DMA 窗、macOS supplicant 构建
- `ShengUfs`：verified-root 表页缓存等 7 条
- `QcomDwc3`：窗口内零 commit（USB 无新货）

### 1.3 上游 oosexgang mtk 线——全生态第一个 bluetoothd + MTK 第二台真机

- **蓝牙打通** `c36d6641`（11-10T09:57Z，mtk 分支）：iOS 16.5 bluetoothd 跑在 MT6631 上——HCI over STP on BTIF、Skywalk 管道；实测 6/6 HCI 命令应答、扫描见 6 个真 BLE 设备、Settings 可被发现为 "iPhone"
- **电池真实百分比** `8427bcc8`（11-10T11:46Z）：MT6358 电量计，五次对拍 iOS 100/99/99/98 vs Android 99/99/99/98（**对 F17 电量施工单是正面范式**）
- **MTK 第二台真机到主屏** `a9627984`：x6826b clone 全链构建，SpringBoard CPU 渲染 10fps，36 检查 0 失败；附 mtk-porting.md 十二步移植指南 `b2838633`
- main 分支零新提交（tip 63fc2b46 仍 11-06 PR #53）

### 1.4 小动作 / 窗口外前一天

- `zhouzhoublm/uefi-unicorn`（小米 12S Pro）：今日仅 dependabot/issue 评论，实质停 11-05
- `Project-Silicium/Mu-Silicium`：常规状态更新，无 SM8475 内容
- **qiumochen/UniXNU-zizhan（MIX Fold 2 / 同 SoC）**：11-09 五条——"exact-SHA cloud kernel success"、DSI 命令重放改无符号寄存器 `de1ce138`、Weather 交接；**11-10 起无活动**

## 2. 今日无活动但值得一提

- **boomoodxf/UniXNU-ace2（同机 PHK110 唯一他人移植）：pushed_at 10-26，16 天零推送——确认仍休眠**
- K20 Pro（raphael）线：GPU GLES 边界/WiFi 重连 bug/蜂窝缺失三项均无推进（HeliumStudio 10-27、adelholzener69 11-08、guowenye 11-06）
- K60 其余线（Amor1120iy 11-08、XTOM0706 11-01 等 forks）：全部今日无动作
- SM8475 散装（thor×2/unicorn×3/mayfly/liuqin）：均无
- takasugl（udon 上游锚）：uefi-udon 停 11-08、UniXNU-udon 停 10-25
- hackios.net 200 无新内容；unixnu.com udon 仍只 takasugl 一条、mondrian 仍 5 源
- 外围传闻（非同 SoC、无代码在案）：红米 Note 12 4G（SM6225）iOS 16.7.16 用户态三件套 [X 帖转述]；B站称小米 17 Pro/K90 Pro Max 基于 UniXNU [视频转述]

## 3. 对我们项目的启示

1. **GPU：K60 线未通硬件层（本普查口径），但"同 SoC 无人打通"表述过强（2026-11-12 勘误，阶段 44 对账）**——wave35 §0-1 本就记录 zizhan（MIX Fold 2 / SM8475 / A730）GPU-01 = DEVICE_VERIFIED，且 UniXNU 框架仓设备记录自报 pong / diting-dddqmmx（均 SM8475/A730）GPU 栏 implemented（后者自报 60 秒 1030 个 command buffer）；本普查未独立验证其硬件证据，准确坐标 = **K60/mondrian 用户态 scanout 卡 -force_load，zizhan→pong→diting 线自报已通**。UniXNU/Adreno740（7xx 同代原生驱动）与 **PongAdreno（A730 专用，公开于 zizhan/mondrian 仓）** 同为 v0.5 直接参考——见 wave44 §4（Adreno740 是 A730 线的同源核心，PongAdreno 更近，其四仓 license 原文未读前不得引入代码）。
2. **USB：今日无他人突破可学**（org 的 QcomDwc3 零提交）。
3. **WiFi：v0.6 组织方式有了新锚**——sheng 线 ath12k"无人值守入网 + macOS supplicant + 无线守护进程"形态；芯片族不同（ath12k vs 我们 ath11k/qca6490），驱动代码不可搬。
4. **蓝牙：上界被打破**——MTK 线（MT6631 真 BLE）与 org QcaBluetooth 同日证明 bluetoothd 可跑非苹果硬件；PHK110 BT 不排期，但未来两条线都是现成参考。
5. **电池：MT6358 五次对拍范式**（`8427bcc8`）正好给 F17 电量施工单当验收范式参照。
6. **launchd/用户态：K60 正沿我们的 issue #3 + yibiya prelink 方向推进**（SIGSEGV 循环 → pid 282）；**建议把 yibiya/UniXNU-mondrian 的 upstream-fix 分支挂进监控清单**。
7. **同机赛道**：boomoodxf 仍休眠，PHK110 公开赛道依旧我们独苗；我们给 Emilelu 的 issue #3 尚无回应。

## 4. 查证清单

上游 oosexgang 全 org（main+mtk+mt6768+sm7325+uefi+metal+userland+web）、Emilelu 全层仓、yibiya 分支、qiumochen/zizhan、boomoodxf/ace2、SM8475 散装 9 仓、UniXNU org 32 仓（重点 Adreno740/sheng/QcaBluetooth/Ath12kWifi/QcomDwc3/ShengUfs）、takasugl×3、raphael 4 线、基座 ios-sweet/Mu-Silicium、我们镜像 Seanding1998/phk110-port、unixnu.com/hackios.net、WebSearch×3（中英）。
