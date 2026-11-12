#!/usr/bin/env bash
# Wave 44 - how Linux derives UBWC swizzle / macrotile / bank spread from the encoder version
# (include/linux/soc/qcom/ubwc.h, master, through the authenticated gh api). Excerpts only.
set -u
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
T="$(mktemp)"
gh api "repos/torvalds/linux/contents/include/linux/soc/qcom/ubwc.h" --jq '[.sha, .size] | @tsv' | sed 's/^/blob sha, bytes: /'
gh api "repos/torvalds/linux/contents/include/linux/soc/qcom/ubwc.h" --jq .content | base64 -d > "$T"
echo "lines: $(wc -l < "$T")"
grep -n -E 'UBWC_[0-9]_[0-9]|UBWC_SWIZZLE_ENABLE_LVL' "$T" | head -20
grep -n -A16 -E 'static inline .*qcom_ubwc_(swizzle|macrotile_mode|bank_spread)' "$T"
rm -f "$T"
