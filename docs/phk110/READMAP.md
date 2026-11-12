# 这批文档怎么读

项目一共写下了 70 篇阶段日志和调研记录（外加 7 篇外部评审、进度快照与计划）。很少有人需要
从头读到尾，所以这里按主题分了组：你想弄明白哪件事，就去看对应的那几篇。
每篇都标注了日期，写法是工程师写给工程师——做法、命令、日志证据、结论，
以及当时判断错了什么、后来怎么纠正的。

只想知道"系统现在能做什么、证据在哪"的，直接看一页式汇总
[SYSTEM-REPORT-2026-11-12.md](SYSTEM-REPORT-2026-11-12.md)。

两件事先说明白：

- **文件名保留了 `waveN-…` 前缀**，这是内部沿用下来的命名；每篇标题已改为
  "阶段 N · 日期 · 主题"。引用路径不变，外链不会断。
- **"Boot #N"** 是历次刷写启动的编号（从第一次 ABL 拒收镜像算起），各篇之间
  用它互相引用时间线。完整对照表在 [STATUS.md](STATUS.md)。

背景知识（用到时再查即可）：日志通过手机上一个专门的分区落盘（`logdump`），
回到安卓侧整块拉回；`*.keylines.txt` 是从中提取的关键行文本，收在仓库的
`logs/`。boot 镜像的做法是把我们的内核与 loader 塞进一台现成的 UEFI 底座
（graft），手机把它当普通 boot 镜像引导。

时间线主线与里程碑在 [STATUS.md](STATUS.md)；更早的逐日记录在
[M0-PROGRESS.md](M0-PROGRESS.md)。

## 一、让手机跑起来：UEFI、loader、内核的第一次呼吸（11 月 1–3 日）

这是最早的 11 个阶段，从零开始：摸清硬件、把 UEFI 底座建起来、让内核的
日志第一次落盘、修好中断控制器、内核第一次跑进用户态、第一次在真机上
常驻 60 秒。

- [waves/wave1-hwmap.md](waves/wave1-hwmap.md)（11-02）— 摸底：PHK110 的硬件清单，以及上游 redwood 的驱动哪些能对上、哪些对不上。
- [waves/wave1-phk110pkg-spec.md](waves/wave1-phk110pkg-spec.md)（11-02）— UEFI 平台包（phk110Pkg）的逐文件适配方案；对上游 redwood 平台包做了哪些修改、为什么。
- [waves/wave1-socargs.md](waves/wave1-socargs.md)（11-02）— 从手机自己的设备树提取 SM8475 的 SoC 启动参数表，附内存图与 loader 加载窗口的分析。
- [waves/wave2-phk110pkg.md](waves/wave2-phk110pkg.md)（11-02）— 按上面的方案把平台包文件构造出来。
- [waves/wave2-soclayer.md](waves/wave2-soclayer.md)（11-02）— sm8475 SoC 层与设备配置的填充，内核配置系统验证。
- [waves/wave2-uefienv.md](waves/wave2-uefienv.md)（11-02）— UEFI 构建环境搭建（WSL Fedora），用 ingres 衍生底座验证工具链。
- [waves/wave3-integration.md](waves/wave3-integration.md)（11-02）— 内核 + 平台包的集成打包链走通，产出第一份 boot 镜像。
- [waves/wave3-research-external.md](waves/wave3-research-external.md)（11-02）— 查了一圈外部案例：别家怎么在高通手机上用 `fastboot boot` 引导自制 UEFI；由此发现 uefi-udon 这个关键底座。
- [waves/wave4-udon-rebuild.md](waves/wave4-udon-rebuild.md)（11-02）— 把 uefi-udon（udonPkg）完整重建一遍，装上 AVB footer，第一次在 PHK110 上点亮 UEFI 菜单（Boot #6）。
- [waves/wave5-udon-hakios.md](waves/wave5-udon-hakios.md)（11-02）— 把 HakiOS payload 嫁接进 udonPkg 底座；内核日志第一次滚过屏幕，随后在 qemu-virt 回退处冻结（Boot #7）。
- [waves/wave6-platform-phk110.md](waves/wave6-platform-phk110.md)（11-03）— loader 平台表 `platform_phk110`：内核第一次"知道"自己是 PHK110，干净返回（Boot #8）。
- [waves/wave7-usbmode.md](waves/wave7-usbmode.md)（11-03）— USB 模式启动镜像：免手操作的引导链走通，主机第一次看见 `xnuloader` 设备（Boot #9）。
- [waves/wave7b-klogdump.md](waves/wave7b-klogdump.md)（11-03）— 内核日志落盘缺一块的修复；第一次拿到内核日志，并从中读出第一个真 bug：中断控制器地址配错（Boot #10）。
- [waves/wave8-usb-start-fix.md](waves/wave8-usb-start-fix.md)（11-03）— loader 的 `usb_start()` 在 PHK110 上失败的根因分析，与 usbmode 驻留镜像 v3。
- [waves/wave9-interrupt-controller.md](waves/wave9-interrupt-controller.md)（11-03）— 中断控制器修复：设备树链路全通，内核仍在计时器之后 0.15 ms 处 abort（Boot #11）——残局交给阶段 10。
- [waves/wave10-post-gic-abort.md](waves/wave10-post-gic-abort.md)（11-03）— 修复 GIC 重分配器扫描步进；内核一路跑进用户态，Darwin 横幅与 "Hello from user space" 都出来了（Boot #12）。
- [waves/wave11-resident.md](waves/wave11-resident.md)（11-03）— 用驻留 stub launchd 让内核在真机上常驻 60 秒、8 核全上线，第一次全流程闭环：分析、构建、刷写、取证（Boot #13）。

## 二、触摸与按键（11 月 3 日）

输入设备是移植里差异最大的部分，值得单独一组。触摸芯片不是上游认识的
型号，驱动是本项目新写的，前后五版才探针通过；按键则卡在 SPMI 仲裁器
版本上。

- [waves/wave12-touch-buttons.md](waves/wave12-touch-buttons.md)（11-03）— S3910 触摸驱动初版 + 按键适配（电源/双音量键事件取证），300 秒会话零 panic（Boot #14–#16）。
- [waves/wave12a-touch-probe.md](waves/wave12a-touch-probe.md)（11-03）— 触摸探针第一轮：探针没过，但把 GENI 引擎被固件关闭、需要 bitbang 读方向这两个事实钉死在寄存器级（Boot #17）。
- [waves/wave12b-probe-verdict.md](waves/wave12b-probe-verdict.md)（11-03）— 第二轮：一行修复让软件链端到端走通，探针仍失败——问题第一次被收到芯片的电气应答层（Boot #18）。
- [waves/wave12c-electrical.md](waves/wave12c-electrical.md)（11-03）— 第三轮：原始字节取证推翻了"芯片电气故障"的误诊，找到"每帧 9 字节、约 20 ms 重新武装"的规律，探针通过，部件号与面板参数全部读到（Boot #19–#21）。想学"怎么从日志里断案"的，读这篇。
- [research/research-tcm-miso.md](research/research-tcm-miso.md) — 写驱动前后的外部功课：TouchComm over SPI 有哪些已知坑。

## 三、USB 服务通道与 SSH（11 月 8–12 日）

SSH 是 v0.4 的最后一关，也是耗时最长的一段：手机侧的 USB 服务通道时好时坏，
前前后后七个阶段才把两侧的问题都清干净；之后错误墙又在更高负载下回来过，
又用四代修复（含一次"编译器把修复代码优化删除"的根因定位）才彻底解决。

- [waves/wave13-usb-host.md](waves/wave13-usb-host.md)（11-03）— Windows 主机直连 loader USB 的工具链（`loader_talk.py`，零依赖），免刷写迭代从这里开始。
- [waves/wave21-net-design.md](waves/wave21-net-design.md)（11-08）— 设计稿：怎么借 loader 的 USB 通道给内核提供网络（SSH 数据面）。
- [waves/wave21-ssh-e2e.md](waves/wave21-ssh-e2e.md)（11-08）— en0 上机：内核拿到 10.0.0.2/30，网络环真实流动；SSH 没通，原因收到 USB 服务通道（Boot #26–#29）。
- [waves/wave21_1-ssh-verdict.md](waves/wave21_1-ssh-verdict.md)（11-08）— USB 服务通道第一轮修复与在线判据；发现半启动的"假在线"形态（Boot #30）。
- [waves/wave21_2-ssh-catch.md](waves/wave21_2-ssh-catch.md)（11-08）— 第二轮加固；一次构建回归造成的冻屏被现场拍屏照片逐指令定位（PAYLOAD_BASE 用错地址），靠一张照片定案的一篇（Boot #31）。
- [waves/wave21_3-coldboot.md](waves/wave21_3-coldboot.md)（11-08）— 冷启动对照实验：把"暖复位假说"证伪，冻屏与冷热无关（Boot #32）。
- [waves/wave21_5-probe-verdict.md](waves/wave21_5-probe-verdict.md)（11-08）— 给 USB 通道装探针与重掷机制；结论：设备侧正常，阻塞在主机侧"看得见设备"这一环（Boot #34/#35）。
- [waves/wave22-host-visibility.md](waves/wave22-host-visibility.md)（11-08）— 主机第一次真正枚举到我们的设备并稳定六分钟：修的是"只在无人泵送的窗口把设备亮给主机"的结构问题（Boot #36）。
- [waves/wave23-virtual-display.md](waves/wave23-virtual-display.md)（11-09）— 插曲：为无 GPU 的显示路线做屏幕录制链取证，顺带抓到 launchd 卡顿与 vnode 表耗尽（Boot #37）。
- [waves/wave24-exp1-design.md](waves/wave24-exp1-design.md)（11-09）— 诊断刷写的设计稿：怎么用一次刷写分辨 USB 端点问题的几种候选根因。
- [waves/wave24-exp1-diagnostic.md](waves/wave24-exp1-diagnostic.md)（11-09）— 诊断结果：根因是 vendor 复位流程缺陷（超时后不复位），显式清除后错误墙不再出现；USB 服务通道就此打通（Boot #38）。
- [waves/wave25-ssh-e2e.md](waves/wave25-ssh-e2e.md)（11-09）— 通道打通后的 SSH 端到端尝试（不刷写）。
- [waves/wave26-k1-fix.md](waves/wave26-k1-fix.md)（11-09）— vnode 上限修复与 SSH 时间窗规律（Boot #39 系）。
- [waves/wave27-phaseB-wide-window.md](waves/wave27-phaseB-wide-window.md)（11-10）— 验证完成：三条独立 SSH 会话 + 256 KiB 校验传输 + 干净退出后 loader 存活，v0.4 的 SSH 关门（2026-11-10 晨）。
- [research/f12-ep2-not-configured.md](research/f12-ep2-not-configured.md) — "endpoint[2] not configured" 这堵墙的专项排查记录。

错误墙的收尾（v0.4 宣告之后、v0.5 期间）单独成段：

- [waves/wave38-usb-selfheal.md](waves/wave38-usb-selfheal.md)（11-11）— 错误墙的两个 loader 侧根因（应答放弃不排空、服务窗热旋）与整对自愈修复；离线完成待上机。
- [review/gpt-review-2026-11-11-usb-wall.md](review/gpt-review-2026-11-11-usb-wall.md) / [review/gpt-review-report-3-2026-11-11-usb.md](review/gpt-review-report-3-2026-11-11-usb.md) — USB 专项外部评审：导读（问题史与五问）与报告三（对修复包的逐条审定与分代路线）。
- [waves/wave38-handoff.md](waves/wave38-handoff.md)（11-11）— 交接页：修复四代完成时的设备状态与 v34 判定任务单。
- 阶段 42 的上机判定（SSH 双向内容 SHA 524288/524288、/var 复验、LLVM 常量折叠删码的根治）记录在 [waves/wave38-usb-selfheal.md](waves/wave38-usb-selfheal.md) §8 与 [wave42-scripts/verdict42-*.txt](../../wave42-scripts/)。

## 四、存储：UFS 与数据卷，以及 /var 持久化（11 月 3–11 日）

让内核看见手机的 UFS 存储、在尾部挖一个 darwin 卷、把 /private/var 挂上并
让它跨启动保留。上游的验收阶梯（S0–S8）在本机一次点亮，没改一行内核代码
就过了只读阶段。/var 的持久化则经历了一次完整的"判定失败 → 根因到行 →
修复 → 翻绿"：

- [waves/wave15-ufs-research.md](waves/wave15-ufs-research.md)（11-03）— 动手前的功课：UFS 驱动的实施级设计与风险清单。
- [waves/wave16-ufs-s0s2.md](waves/wave16-ufs-s0s2.md)（11-04）— 只读枚举一次点亮：129 个分区、6 个 LUN 的 GPT 校验全过（Boot #22）。
- [waves/wave16b-p0-prep.md](waves/wave16b-p0-prep.md)（11-03）— 数据卷工具的 PHK110 适配：只勘察、不写盘。
- [waves/wave16c-p0-exec.md](waves/wave16c-p0-exec.md)（11-04）— darwin 分区与 12 GB HFS+ 数据卷就位，全程走 adb，不经 fastboot；前后校验和三方比对。
- [waves/wave18-s3s8.md](waves/wave18-s3s8.md)（11-04）— 写路径打开：/private/var 跨启动保留、日志跨启动重放、数据卷哈希在安卓侧回读复验（Boot #23/#24）。
- [waves/wave31-var-verdict.md](waves/wave31-var-verdict.md)（11-11）— /var 持久回归判定 FAIL：写进去的东西重启后消失——init 二次运行把内存盘叠在真实卷上（Boot #40）。
- [waves/wave34-var-fix.md](waves/wave34-var-fix.md)（11-11）— 一行守卫修复遮蔽问题；写→内核死亡→读全部幸存，v0.4 的最后一门转绿（Boot #41）。

## 五、用户态与身份链（11 月 3–8 日）

launchd 起不来的一段，根因在设备身份：内核答不出 "你是谁"，dyld 里的
libignition 就拒绝继续。

- [waves/wave14-sysimage-prep.md](waves/wave14-sysimage-prep.md)（11-03）— 用户空间前置：iOS 16.5（20F66）镜像解包、盘点、就绪化，含 SSH bootstrap 的做法。
- [wave17-ssh-bootstrap.md](wave17-ssh-bootstrap.md)（11-03）— SSH 引导链机制备忘：sshd、密钥、libiosexec 细节（这篇早年在目录树里放错位置，文件名保留）。
- [waves/wave19-prep.md](waves/wave19-prep.md)（11-04）— 动手前把 SSH 数据面与真实 launchd 系统卷这两个开放问题摊开。
- [waves/wave20-launchd.md](waves/wave20-launchd.md)（11-08）— launchd 存活：`hw.target` 查询失败的根因（loader 占位身份 → 设备树无 `model` → EINVAL）与双层修复；28 个进程跑起来，sshd 监听 :22（Boot #25）。Emilelu/UniXNU-mondrian 卡过的正是这一关。

## 六、显示：无 GPU 先见桌面（11 月 9 日）

- [waves/wave23-virtual-display.md](waves/wave23-virtual-display.md)（11-09）— 在没有 GPU 驱动的情况下，屏幕录制链内核侧工作正常（Boot #37 的取证）。
- [research/f13-virtual-display.md](research/f13-virtual-display.md) — 无 GPU 显示的路线预研。

## 七、WiFi：工具先行（11 月 10 日，尚未上机）

- [waves/wave30-ath11k-tooling-prep.md](waves/wave30-ath11k-tooling-prep.md)（11-10）— ath11k 路线的检查器与打包工具；配套脚本在 [wave30-scripts/](../../wave30-scripts/)。

## 八、GPU：从内核侧首亮到真·首帧（11 月 10–12 日）

v0.5 的全程。主线是自研 Adreno 730 内核驱动（a7xx 形态）加 Mesa freedreno
用户态；中间穿插了一轮 GPU 专项外部评审，评审发现的三个缺陷经独立验证后
全部修复，最后在 v36 上以四门判定完成——硬件渲染首帧上屏，人眼可见。

- [research/f16-k60-sm8475-census.md](research/f16-k60-sm8475-census.md) — 同 SoC（K60/mondrian）移植线普查；MIX Fold 2 的自研驱动先例成为 v0.5 的参照。
- [waves/wave35-gpu-prestage.md](waves/wave35-gpu-prestage.md)（11-10）— 动手前的功课：同 SoC 先例核实、a730 固件三件套双源核实、Mesa 25.0.7 的 FD725 身份裁决；固件实拉脚本在 [wave35-scripts/](../../wave35-scripts/)。
- [waves/wave36-gpu-firstlight.md](waves/wave36-gpu-firstlight.md)（11-11）— 驱动第一次上机：固件实拉 + gen7 参数层进内核；启动参数被截断的 bug 在这一轮定位并修复。
- [waves/wave36-handoff.md](waves/wave36-handoff.md)（11-11）— 交接页：第 1 步挂点已知的全部事实与逐步定位协议。
- [waves/wave37-gpu-firstlight.md](waves/wave37-gpu-firstlight.md)（11-11）— 七刷七判：gcc/熔丝/GPUCC/zap 布局/寄存器表五处假设逐一以本机设备树与厂商源码锚定修正，21 步全绿，3D 核接受命令并写内存；全套补丁脚本与判定 runner 在 [wave36-scripts/](../../wave36-scripts/)、[wave37-scripts/](../../wave37-scripts/)。
- [waves/wave39-mesa-userland.md](waves/wave39-mesa-userland.md)（11-11）— 用户态下半场：Mesa 25.0.7 交叉构建本树打通（含 FD725 设备串），内核接口无需新增 shim 的裁决；构建脚本在 [wave39-scripts/](../../wave39-scripts/)。
- [review/gpt-review-report-4-2026-11-11-gpu.md](review/gpt-review-report-4-2026-11-11-gpu.md) — GPU 专项外部评审：fence 完成事件缺位 / NC_MODE 编码错误 / 测试无断言假绿。
- [waves/wave40-gpu-verify.md](waves/wave40-gpu-verify.md)（11-11）— 对评审报告的独立验证：逐条源码级确认，并补了两处评审本身遗漏的细节。
- [waves/wave41-gpu-fix.md](waves/wave41-gpu-fix.md)（11-11）— 四项修复落地：fence 事件按厂商/主线/Mesa 三方参照字段化，NC_MODE 改厂商公式，gl_test 重写为带像素真值断言的验收器；补丁与 diff 在 [wave41-scripts/](../../wave41-scripts/)。
- [waves/wave44-adreno740-survey.md](waves/wave44-adreno740-survey.md)（11-12）— 同代原生驱动八仓只读对照：fence 字段逐位佐证修复方向，另登记 14 行硬件初始化差异。
- [waves/wave45-v36-firstframe.md](waves/wave45-v36-firstframe.md)（11-12）— **完成：v36 上机四门判定**——步进回归 PASS / fence 探针 PASS / 硬件渲染 DONE（面板三角形人眼目击）/ 电量 PARTIAL；判定文件在 [wave45-scripts/](../../wave45-scripts/)。

## 九、电量显示（11 月 11–12 日，数据链未通）

- [research/f17-battery-display.md](research/f17-battery-display.md) — 两层根因（内核配置未开 + 本机无数据源驱动）与分期方案。
- [waves/wave43-battery.md](waves/wave43-battery.md)（11-12）— 燃油计驱动落地：PM8350B 充电器观察 + bq27541 位带，寄存器全部从厂商树机械核对（零猜测），62 项自检；上机判定 PARTIAL，数据链修复进行中。

## 十、调研与外部评审

- [research/f10-dxe-abort-solutions.md](research/f10-dxe-abort-solutions.md) — DXE 阶段 Data Abort（FAR=0xF0000000）的外部先例与修复模式库。
- [research/f14-sd778g-zendot-survey.md](research/f14-sd778g-zendot-survey.md) — SM7325 驱动全景与外部文章考古，兼做物料清单预研。
- [research/f15-raphael-k20pro-survey.md](research/f15-raphael-k20pro-survey.md) — "K20 Pro 的 WiFi/4G/GPU 已经修好"这类传闻的核实，与对本项目的迁移价值评估。
- [research/landscape-2026-11-08.md](research/landscape-2026-11-08.md) — 同类项目生态盘点与进度基线（2026-11-08）。
- [research/ecosystem-census-2026-11-11.md](research/ecosystem-census-2026-11-11.md) — 生态普查（2026-11-11）：各移植线当日进展与 UniXNU 原生 Adreno740 驱动的发现。
- [research/consulting-2026-11-03.md](research/consulting-2026-11-03.md) — 一次外部咨询的意见原文与逐条评估。
- [review/](review/) — 七篇外部评审记录（2026-11-09 三篇 + 2026-11-11 USB/GPU 专项两轮四篇），对本项目方法论与结论的第三方复核意见。
