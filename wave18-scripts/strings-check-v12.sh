#!/bin/bash
# Wave 18 helper: confirm the write-path strings live in the UNCHANGED binaries
# (the v5-era loader inside payload-v11 and the v11 kernel), so a cmdline-only
# v12 is legitimate: CONFIG_UFS_WRITE / CONFIG_VAR_STORE are runtime boot-args
# (docs/boot-args.md:309 ufs_write KL, :432 var_store U), not compile gates.
D=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer
for s in "may be written this run" "no write will be served" "fnv" "its blocks from" "the data volume is asked for" "kept between boots" "takes writes" "everything else of the storage is read only" "for the data volume" "the saver did not answer"; do
  a=$(grep -ac "$s" "$D/udon-hakios-payload-v11.bin")
  b=$(grep -ac "$s" "$D/hakios-kernel-v11.bin")
  printf '%-48s payload:%s kernel:%s\n' "$s" "$a" "$b"
done
