#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[pipeline] Step 1/3: regenerate interactive dataset payloads"
python3 script/generate_interactive_fee_uplot.py \
  --manifest-config config/interactive_manifest.json \
  --max-points 160000 \
  --out-js data/plots/fee_history_interactive_app.js \
  --out-manifest-js data/plots/fee_history_interactive_manifest.js

echo "[pipeline] Step 2/3: run simulation core tests"
node --test data/plots/tests/*.test.js

echo "[pipeline] Step 3/3: run Playwright visual regression tests"
npm run visual:test

echo "[pipeline] Done."
