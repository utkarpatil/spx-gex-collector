#!/usr/bin/env bash
# One-time setup on a fresh Oracle Cloud (Ubuntu) VM.
# Run from inside the cloned repo:  cd ~/spx-gex-collector && bash vm_setup.sh
set -e

echo ">> installing python + git ..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv git

cd "$(dirname "$0")"
echo ">> creating venv + installing deps ..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

chmod +x vm_tick.sh

# quick self-test (writes only if market is open)
echo ">> test run ..."
./venv/bin/python collect_gex.py || true

# install cron: every 5 min, 13:00-21:59 UTC, Mon-Fri (covers US market hours both DST).
DIR="$(pwd)"
LINE="*/5 13-21 * * 1-5 $DIR/vm_tick.sh >> $HOME/collector-cron.log 2>&1"
( crontab -l 2>/dev/null | grep -v vm_tick.sh ; echo "$LINE" ) | crontab -

echo ""
echo "=========================================================="
echo " Setup complete. Cron installed:"
crontab -l | grep vm_tick.sh
echo ""
echo " It will collect every 5 min during market hours and push to GitHub."
echo " Logs: ~/collector-cron.log   and   data/collected/collector.log"
echo "=========================================================="
