#!/bin/bash
# Probe the shipped loader binary for the fix-chain strings.
set -u
cd /home/cyrux/hakios/kernel/xnuloader
echo "loader.efi size: $(stat -c%s loader.efi 2>/dev/null)"
for s in 'the pair reads dead in this generation' 'reads dead' 'bounded recovery' \
         'rebuild' 'the recovery' 'the recovery' 'usb_pair_rebuild' \
         'the IN gate is up' 'a reply came back unread' 'display budget' \
         'the service window is over'; do
  printf '%-42s -> %s\n' "$s" "$(strings -a loader.efi | grep -cF -- "$s")"
done
llvm-objdump -t loader.efi 2>/dev/null | grep -ciE 'pair_rebuild|recovery'
