#!/usr/bin/env python3
"""Wave 42 wrap-up: add the wave42 row to docs/README.md's wave table."""
path = "docs/README.md"
src = open(path, encoding="utf-8").read()
anchor = "| wave41-gpu-fix | GPU 修复波（外审四授权修复，零设备）："
assert src.count(anchor) == 1, "anchor"
row = ("| wave42-usb-verdict | USB 修复收官波（Wave 38 域判定轮）：解 LLVM 22.1.8 -O1 消除阻断"
       "（法证 = IPSCCPass 把 GEN-4 四时间戳全局常量折叠为 0，守卫全折叠函数体删除；optnone/fn-ptr "
       "实测不保护；根治 = 时间戳全局 volatile 语义修复 + 撤死重 hardening；三级反汇编断言 obj 符号/"
       "COFF 重定位/efi ADRP+ADD 精确绑定全绿；GEN 全链 49/0 + 22/22 终态重跑）"
       "→ v35 打包（payload 82add009 / graft 6558d303 / verify 69/69，F10 布局钉改语义常量钉）"
       "→ 三门刷写 CONFIRMED → 判定：门1 SSH 全语义 + 双向内容 SHA 524288/524288 MATCH 全绿"
       "（verdict42-w42ssh9）、门2 /var PERSIST 裁定绿（marker 逐字同 + mtime 保留 619==619 + "
       "blob 三方一致；v34 判定器 197 硬编码裁定修正）、门3 gl_test 诊断性完成（旧载体 PATH 不可达 "
       "127 如实标注待 v36）；野外新根因首证 = ABL 启动回退翻 active-slot 致循环中断（纯切槽恢复）；"
       "主机侧双缺陷修复入档（auto-attach 抢设备看护 + ssh 二进制 stdout UTF-8 膨胀） | 判定轮收官 |\n")
src = src.replace(anchor, row + anchor)
open(path, "w", encoding="utf-8", newline="").write(src)
print("README wave table updated")
