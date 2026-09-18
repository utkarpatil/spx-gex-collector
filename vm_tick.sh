#!/usr/bin/env bash
# One collection tick on the VM: collect, then commit+push if there's new data.
# collect_gex.py self-guards US market hours, so off-hours ticks do nothing.
cd "$(dirname "$0")"
./venv/bin/python collect_gex.py
git add data/collected
if ! git diff --cached --quiet; then
  git commit -q -m "data $(date -u +%Y-%m-%dT%H:%MZ)"
  git pull -q --rebase --autostash origin main || true
  git push -q origin main || true
fi
