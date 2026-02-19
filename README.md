# taiko-fee-simulator

Local research workspace for Taiko fee-mechanism simulation and historical L1 fee analysis.

This repo contains:
- Data fetchers for Ethereum L1 base/blob fee history.
- An interactive browser simulator (`uPlot`) for controller tuning.

## Repository Layout

- `script/`
  - `fetch_eth_l1_fee_history.py`: fetches L1 base/blob fee history to CSV + summary JSON.
  - `fetch_eth_gas_used_history.py`: fetches L1 gas used history and writes CSV + PNG.
  - `generate_interactive_fee_uplot.py`: generates interactive dataset payload JS files (data only).
  - `generate_interactive_gas_used_uplot.py`: generates interactive gas-used plots.
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
python3 -m pip install requests matplotlib
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
  --dataset "current365|Current 365d|data/eth_l1_fee_365d_20260206T195430Z.csv" \
  --dataset "prior365|Prior 365d|data/eth_l1_fee_365d_20260207T042312Z.csv" \
  --dataset "year2021|Year 2021|data/eth_l1_fee_blocks_11565019_13916165_20260207T065924Z.csv" \
  --max-points 160000 \
  --no-rpc-anchor \
  --out-js data/plots/fee_history_interactive_app.js
```

Notes:
- `--dataset` format: `<id>|<label>|<csv_path>` (repeatable).
- `--no-rpc-anchor` avoids live RPC timestamp lookups and uses summary/cache only.
- The script does not overwrite `data/plots/fee_history_interactive.html` or `data/plots/fee_history_interactive_app.js`.

## Gas-Used History Utility

```bash
python3 script/fetch_eth_gas_used_history.py \
  --hours 6 \
  --rpc https://ethereum-rpc.publicnode.com \
  --out-dir data \
  --plot-dir data/plots
```

## Tests

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
