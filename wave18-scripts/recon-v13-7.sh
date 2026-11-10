#!/bin/bash
K=~/hakios/kernel
echo "===== cache dir (dyld) ====="
ls -la ~/hakios/sysimage-20F66/20F66__iPhone10,3_6/ | head -10
echo "===== build.sh head (1-30 + 80-160 essentials) ====="
sed -n '80,100p' $K/userland/build.sh
echo "===== rootfs dir ====="
ls ~/hakios/sysimage-20F66/work/rootfs/ | head
echo "===== fw-audio / jb presence in kernel tree top ====="
ls -d ~/hakios/kernel/../fw-audio ~/hakios/kernel/jb ~/hakios/kernel/ssh 2>&1
echo "===== wave17 jb/ssh artifacts ====="
ls ~/hakios/procursus-prep/ 2>/dev/null
du -sh ~/hakios/procursus-prep/ssh ~/hakios/procursus-prep/jb 2>/dev/null
echo "===== df space ====="
df -h /home | tail -1
