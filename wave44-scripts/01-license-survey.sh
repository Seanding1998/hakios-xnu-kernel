#!/usr/bin/env bash
# Wave 44 - license survey of the UniXNU org (read-only, gh api through the local proxy).
# Output is archived under wave44-scripts/evidence/.
set -u
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
OUT="$(dirname "$0")/evidence"
mkdir -p "$OUT"

# Without arguments: the org-wide table plus per-repo detail for the GPU-relevant repos.
# With arguments: per-repo detail only for the named repos (used to regenerate a single
# evidence file after a transient API failure, without disturbing the rest of the archive).
if [ "$#" -eq 0 ]; then
  # 1. org-wide table: name, spdx, size(KB), pushed_at, default branch, fork, archived
  gh api "orgs/UniXNU/repos?per_page=100" \
    --jq '.[] | [.name, (.license.spdx_id // "NONE"), .size, .pushed_at, .default_branch, (.fork|tostring), (.archived|tostring)] | @tsv' \
    | sort > "$OUT/org-repos.tsv"
fi

# 2. per-repo detail for the GPU-relevant repos
for r in ${*:-Adreno740 AdrenoPM4 AdrenoFirmware AirNir AdrenoMetal UniXNU}; do
  {
    echo "=== $r: repos API license field ==="
    gh api "repos/UniXNU/$r" --jq '{license: .license, default_branch, pushed_at, size}'
    echo "=== $r: /license endpoint ==="
    gh api "repos/UniXNU/$r/license" --jq '{path: .path, sha: .sha, size: .size, spdx: .license.spdx_id, name: .license.name}' 2>&1
    echo "=== $r: root listing ==="
    gh api "repos/UniXNU/$r/contents" --jq '.[] | [.type, .name, .size] | @tsv' 2>&1
    echo "=== $r: HEAD ==="
    gh api "repos/UniXNU/$r/commits?per_page=1" --jq '.[0] | [.sha, .commit.committer.date, (.commit.message | split("\n")[0])] | @tsv' 2>&1
  } > "$OUT/license-$r.txt"
done
echo done
