#!/usr/bin/env python3
"""Append the v16b'/v16c post-script to the STATUS.md Boot #31 row."""
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "STATUS.md")
p = os.path.abspath(p)
src = open(p, encoding="utf-8").read()

anchor = ('按协调者"纯案头不碰手机"指令止步待刷。文档 `docs/waves/wave21_2-ssh-catch.md` §7；'
          '日志 `logdump-v16b.bin`（`ec271f52…`，仓库根） |')
add = ('按协调者"纯案头不碰手机"指令止步待刷。文档 `docs/waves/wave21_2-ssh-catch.md` §7；'
       '日志 `logdump-v16b.bin`（`ec271f52…`，仓库根）。'
       '**【v16b-prime 上机 + 端点墙 + v16c（后记）】**：批准后 v16b-prime（`e33ec417…`）刷写 OKAY → '
       '**F10 断言屏绝迹，loader 每 boot 活到 USB 服务器**（PAYLOAD_BASE 修复真机生效）——但新形态 = '
       '端点墙（`UsbDeviceSend → DwcPrepareURB:Trb: physical endpoint[2] not configured → 0x8000000C` '
       '持续刷屏，SSM 未达 CONFIGURED，bulk 未武装；F8 的设备侧内部视图）。'
       'host 侧 SET_CONFIG 实验（ensure_configured：libusb_set_configuration(1) 被设备收下+描述符全读通+'
       '仍无 bulk 应答）裁决 = 设备侧 → **v16c 三变体（DWC3 唤醒：SUSPHY bit6 清 GUSB3PIPECTL/GUSB2PHYCFG + '
       'DCTL 软断开 + GCTL.CSFTRST + start_ex 后再清 SUSPHY——覆盖 vendor init 的 SUSPHY 复置）** '
       'loader `ee8204e8→e3f51cd4→45437cd3`、graft 最终 **`53f5e077…`**（verify 53/53）全部上机 → '
       '**错误墙恒在，三重修复全无效** → 主代理收口判定：**端点未配置 = vendor UsbDeviceDxe/UsbfnDwc 栈'
       '在 loader 场景的固有行为**（最可能 = configuration/interface 布局不一致或需明示 ActivateEndpoints），'
       '非暖态顽疾。下一波 = 反汇编 UsbfnDwcSubmitUrbNode/DwcPrepareURB 的 ep2 配置判据'
       '（详见 wave21_2 §7.6）。守护实战二胜：两次 F9 手术治愈刷写/探测管道。文件新增：patch-loader-v16c.py / '
       'make-payload-v16c.sh / verify-udon-hakios-v16c.py / mk-verify-v16c.py / usbfn-disasm-scan.py / '
       'usbfn-reg-enum.py / watch-setconfig.sh / payload-v16c.bin / grafted-v16c.img（cce46f83→53f5e077 两代）/ '
       'report.json |')
n = src.count(anchor)
assert n == 1, "anchor occurrences: %d" % n
src = src.replace(anchor, add)
open(p, "w", encoding="utf-8", newline="").write(src)
print("STATUS #31 row extended")
