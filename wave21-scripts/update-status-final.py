#!/usr/bin/env python3
"""Update STATUS.md: image table v16c row + queue update 12 (v16b'/v16c post-script)."""
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "STATUS.md")
p = os.path.abspath(p)
src = open(p, encoding="utf-8").read()

# ---- image table: add v16c row above the v16b row ----
v16b_row_head = "| **udon-hakios-grafted-v16b.img** |"
v16c_row = ("| **udon-hakios-grafted-v16c.img** | **最终变体 `53f5e077…` 已构建验证（53/53）并上机（Boot #33+ 循环）；分区上现存 = cce46f83（e3f51cd4 变体）；活跃槽随 ABL 兜底回 a** | "
            "内核 v15/v16 `17c905ec…` 逐字节复用 + loader v16c `45437cd3…`（75,776 B：v16b-prime 全部 + **DWC3 唤醒**——SUSPHY bit6 清 GUSB3PIPECTL(0xC2C0)/GUSB2PHYCFG(0xC200) + DCTL(0xC704) 软断开 + GCTL(0xC110).CSFTRST + start_ex 成功后再清 SUSPHY（覆盖 vendor init 复置）；PAYLOAD_BASE=0xF4000000 指令级钉死）+ cmdline = v16 字节 + payload 7 条目 `4a2a90ff…`；graft `53f5e077…`；自检 **53/53**；真机：错误墙恒在（三重修复无效）→ 判定 = vendor UsbFnDwc 栈固有行为（wave21_2 §7.6）；文档 wave21_2-ssh-catch.md |\n")
assert src.count(v16b_row_head) == 1
src = src.replace(v16b_row_head, v16c_row + v16b_row_head)

# fix the v16b row: note it's superseded on disk by v16c cycle image... keep as-is (historical)

# ---- queue: add update 12 above update 11 ----
q_anchor = "> **🟡 2026-11-08 更新⑪"
q_new = ("> **🟡 2026-11-08 更新⑫：Wave 21.2 收口（v16b-prime + v16c 三变体上机）= F10（构建回归）根因闭环 + "
         "PAYLOAD_BASE 修复真机生效 + 端点墙定性（vendor UsbFnDwc 栈固有行为）→ N1-N3 仍未达，移交主代理走 "
         "UsbfnDwc 反汇编路线：**\n"
         "> ①v16b-prime（e33ec417）真机：F10 绝迹、loader 每轮活到 USB 服务器（gadget 上总线）= PAYLOAD_BASE 修复生效；"
         "②新形态端点墙（physical endpoint[2] not configured / 0x8000000C 刷屏）：SET_CONFIG 实验（host 显式 "
         "libusb_set_configuration(1) 被收下但 SSM 不前进）裁决设备侧；③v16c 三变体（SUSPHY 前清 + DCTL 软断开 + "
         "CSFTRST + start_ex 后再清——覆盖 vendor init 的 SUSPHY 复置）53f5e077 上机：墙恒在 → 判定 = vendor 栈固有行为"
         "（非暖态顽疾）。④下一波：反汇编 UsbfnDwcSubmitUrbNode/DwcPrepareURB 的 ep2 配置判据 + 对照 vendor 正常 "
         "fastboot 会话的 ep2 路径；logdump 含 v16c wake/try-failed 行待安卓回稳拉取。⑤守护固化（hunt5 → "
         "loader_talk 默认）+ 探针 timeout 包裹已为后续波次常备。手机随 ABL 兜底回安卓交还用户。"
         "详见 `docs/waves/wave21_2-ssh-catch.md` §7.6。\n")
assert src.count(q_anchor) == 1
src = src.replace(q_anchor, q_new + q_anchor)

open(p, "w", encoding="utf-8", newline="").write(src)
print("STATUS image table + queue updated")
