#!/usr/bin/env bash
# Nightly refresh, e.g. crontab: 30 2 * * * /path/to/geekom-map/nightly.sh >> ~/logs/geekom-map.log 2>&1
# Any failure stops the chain; build_vault.py swaps atomically, so the vault stays intact.
# Drop the model steps (digest, model_links, journal) to run with no network at all.
set -euo pipefail
cd "$(dirname "$0")"
echo "== $(date -Is) start"
python3 inventory.py
python3 digest.py --changed
python3 links.py
python3 model_links.py
python3 journal.py
python3 build_vault.py
echo "== $(date -Is) ok"
