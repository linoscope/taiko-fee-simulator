#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[pipeline] Step 1/3: regenerate interactive dataset payloads"
python3 script/generate_interactive_fee_uplot.py \
  --dataset "current365|data/eth_l1_fee_365d_20260206T195430Z.csv" \
  --dataset "prior365|data/eth_l1_fee_365d_20260207T042312Z.csv" \
  --dataset "year2021|data/eth_l1_fee_blocks_11565019_13916165_20260207T065924Z.csv" \
  --max-points 160000 \
  --out-js data/plots/fee_history_interactive_app.js

echo "[pipeline] Step 2/3: run simulation core tests"
node --test data/plots/tests/*.test.js

echo "[pipeline] Step 3/3: run Playwright visual regression tests"
npm run visual:test

echo "[pipeline] Done."
