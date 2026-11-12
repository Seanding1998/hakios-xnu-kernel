#!/usr/bin/env bash
# Wave 44 - are the LICENSE files of the eight clones the same texts? (git blob ids, sizes, and the
# bodies compared with their copyright lines taken out.) Read-only.
set -u
R=/home/cyrux/hakios/refs
ALL="UniXNU-UniXNU UniXNU-UniXNU-sheng UniXNU-UniXNU-sm8550-common UniXNU-AdrenoFirmware UniXNU-Adreno740 UniXNU-AdrenoPM4 UniXNU-AirNir UniXNU-AdrenoMetal"
for d in $ALL; do
  printf '%-30s blob %s  %5s bytes  spdx-line: %s\n' "$d" "$(runuser -u cyrux -- git -C $R/$d rev-parse HEAD:LICENSE | cut -c1-8)" \
    "$(wc -c < $R/$d/LICENSE)" "$(grep -m1 'SPDX-License-Identifier' $R/$d/LICENSE || echo '(none; first line: '"$(head -1 $R/$d/LICENSE)"')')"
done
echo "--- bodies without their copyright lines (same hash = same text)"
for d in $ALL; do
  printf '%-30s %s  | %s\n' "$d" "$(grep -v '^Copyright' $R/$d/LICENSE | sha256sum | cut -c1-12)" "$(grep -m1 '^Copyright' $R/$d/LICENSE)"
done
