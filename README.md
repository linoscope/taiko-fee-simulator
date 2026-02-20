# taiko-fee-simulator

Local research workspace for Taiko fee-mechanism simulation and historical L1 fee analysis.

This repo contains:
- Data fetchers for Ethereum L1 base/blob fee history.
- An interactive browser simulator (`uPlot`) for controller tuning.

## Repository Layout

- `script/`
  - `fetch_eth_l1_fee_history.py`: fetches L1 base/blob fee history to CSV + summary JSON.
  - `generate_interactive_fee_uplot.py`: generates interactive dataset payload JS files and manifest artifacts.
  - `run_deterministic_pipeline.sh`: fixed-sequence local pipeline for generation + core tests + visual regression.
- `config/`
  - `interactive_manifest.json`: source-of-truth dataset metadata, labels, initial dataset, and range presets.
- `data/`
  - Raw fetched CSV/JSON datasets.
  - `plots/`: generated interactive pages and static assets.
- `data/plots/tests/`
  - Node tests for simulation core behavior.

## Prerequisites

- Python 3.10+
- Node.js 18+ (for tests)

Install Python dependencies:

```bash
python3 -m pip install requests
```

## Quick Start (Open Existing Interactive Simulator)

The main checked-in page is:

- `data/plots/fee_history_interactive.html`

Recommended local serving:

```bash
cd data/plots
python3 -m http.server 8000
```

Then open:

- `http://127.0.0.1:8000/fee_history_interactive.html`
- Example with preset query params:
  - `http://127.0.0.1:8000/fee_history_interactive.html?dataset=current365&min=21771899&max=24399899`

## Regenerate L1 Fee Data

Fetch a rolling N-day window (default 365):

```bash
python3 script/fetch_eth_l1_fee_history.py \
  --days 365 \
  --rpc https://ethereum-rpc.publicnode.com \
  --out-dir data
```

Fetch an explicit block range:

```bash
python3 script/fetch_eth_l1_fee_history.py \
  --start-block 11565019 \
  --end-block 13916165 \
  --rpc https://ethereum-rpc.publicnode.com \
  --out-dir data
```

## Regenerate Interactive Fee Simulator

Refresh multi-dataset payload files consumed by the static UI:

```bash
python3 script/generate_interactive_fee_uplot.py \
  --manifest-config config/interactive_manifest.json \
  --max-points 160000 \
  --out-js data/plots/fee_history_interactive_app.js \
  --out-manifest-js data/plots/fee_history_interactive_manifest.js
```

Notes:
- Canonical dataset/preset metadata lives in `config/interactive_manifest.json`.
- `--dataset` format `<id>|<csv_path>` is still supported for payload-only generation.
- Time anchors come from each dataset summary JSON only.
- The script does not overwrite `data/plots/fee_history_interactive.html` or `data/plots/fee_history_interactive_app.js`.

## Tests

Run the deterministic full pipeline (generation + core tests + visual regression):

```bash
npm run pipeline:deterministic
```

Run simulator core tests:

```bash
node --test data/plots/tests/*.test.js
```

Run visual regression screenshot tests (Playwright):

```bash
npm install
npm run visual:install
npm run visual:test
```

Create/update screenshot baselines intentionally:

```bash
npm run visual:update
```

Inspect visual diffs:

```bash
npm run visual:report
```

Visual tests live in `tests/visual/` and target:
- `data/plots/fee_history_interactive.html`

## Notes

- Generated outputs can be large (especially full-range datasets).
- Interactive UI source files are static in `data/plots/`; payload files are regenerated from CSV data.
