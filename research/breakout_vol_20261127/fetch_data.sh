#!/usr/bin/env bash
# Copy the inputs from the repo's data branches into ./data (run from the repo root's clone).
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p data/snap
for b in data/history-20261114 data/spx-collection; do git fetch -q --depth 1 origin "$b:refs/remotes/origin/$b"; done
git show origin/data/history-20261114:history/SPY_5m_60d.json.gz > data/SPY_5m_60d.json.gz
git ls-tree -r --full-tree --name-only origin/data/spx-collection | grep '^breadth5m/raw/' | while read -r p; do
  git show "origin/data/spx-collection:$p" > "data/snap/$(basename "$p")"; done
