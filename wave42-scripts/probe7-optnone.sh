#!/bin/bash
# Wave 42 probe 7: identify the 11 optnone functions + where the stamp globals live.
cd ~/hakios/kernel/xnuloader
for ln in 4449 4474 4535 4665 5111 5126 5156 5222 5271 5759 5821; do
  sed -n "${ln},$((ln + 1))p" loader.c | tr '\n' ' ' | cut -c1-110
  echo " [L$ln]"
done
echo "== stamp global declarations context =="
grep -n "usb_pair_last_progress\|usb_pair_born_at\|usb_wall_last_at\|usb_last_connected_at" loader.c | head -12
