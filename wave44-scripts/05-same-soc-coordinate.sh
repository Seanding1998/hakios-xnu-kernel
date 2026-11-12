#!/usr/bin/env bash
# Wave 44 - where the same SoC (SM8475 / Adreno 730) stands, by the repositories the UniXNU framework's
# device records name (devices.toml at 75f35420). Metadata only: nothing is cloned, no source is read.
set -u
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
for r in Chengdong-Yu/UniXNU-pong dddqmmx/UniXNU-diting qiumochen/UniXNU-zizhan Emilelu/UniXNU-mondrian; do
  echo "=== $r"
  gh api "repos/$r" --jq '{license: (.license.spdx_id // "NONE"), pushed_at, size, default_branch, fork, archived, description}' 2>&1
  echo "--- /license endpoint"
  gh api "repos/$r/license" --jq '{path, spdx: .license.spdx_id}' 2>&1 | head -3
  echo "--- paths that name the GPU (tree of the default branch, first 25)"
  gh api "repos/$r/git/trees/HEAD?recursive=1" --jq '[.tree[] | select(.type=="blob") | .path | select(test("(?i)adreno|a730|gmu|turnip"))] | (length|tostring), (.[0:25][])' 2>&1
done
