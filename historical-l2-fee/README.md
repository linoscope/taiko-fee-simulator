# historical-l2-fee

Standalone workspace for historical L1/L2 fee comparison (Arbitrum, Base, Scroll, Optimism) using synced UTC-time plots.

## Structure

- `historical-l2-fee/scripts/`
  - `fetch_arbitrum_fee_history.py`
  - `fetch_base_fee_history.py`
  - `fetch_scroll_fee_history.py`
  - `fetch_optimism_fee_history.py`
  - `generate_synced_l1_l2_fee_uplot.py`
  - `generate_synced_l1_l2_switcher_html.py`
  - `patch_l2_prefix_to_l1_window.py`
- `historical-l2-fee/data/l1/`
  - L1 window summaries used for aligned fetches.
  - Symlinked L1 CSVs used to build synced plots.
- `historical-l2-fee/data/l2/`
  - L2 historical CSVs and fetch summaries for synced datasets.
- `historical-l2-fee/data/plots/`
  - Generated HTML/JS outputs and dataset summaries.

## Main Output

- `historical-l2-fee/data/plots/fee_history_l1_l2_synced.html`

## Regenerate Plots

Run from repository root:

```bash
python3 historical-l2-fee/scripts/generate_synced_l1_l2_fee_uplot.py \
  --l1-csv historical-l2-fee/data/l1/eth_l1_fee_365d_20260206T195430Z.csv \
  --l1-summary historical-l2-fee/data/l1/eth_l1_fee_365d_20260206T195430Z_summary_true_window.json \
  --l2-csv historical-l2-fee/data/l2/arb1_fee_302486616_429334875_step479_20260211T134828Z.csv \
  --l2-base-csv historical-l2-fee/data/l2/base_fee_25933902_41808552_step60_20260211T135212Z.csv \
  --l2-scroll-csv historical-l2-fee/data/l2/scroll_fee_13188273_29645724_step62_20260211T135027Z.csv \
  --l2-optimism-csv historical-l2-fee/data/l2/optimism_fee_131529187_147403837_step60_20260211T150257Z.csv \
  --no-l1-rpc-anchor \
  --title "L1 + L2 Fee History (Synced by Time) - current365" \
  --out-html historical-l2-fee/data/plots/fee_history_l1_l2_synced_current365.html \
  --out-data-js historical-l2-fee/data/plots/fee_history_l1_l2_synced_data_current365.js \
  --out-summary historical-l2-fee/data/plots/fee_history_l1_l2_synced_current365_summary.json

python3 historical-l2-fee/scripts/generate_synced_l1_l2_fee_uplot.py \
  --l1-csv historical-l2-fee/data/l1/eth_l1_fee_365d_20260207T042811Z.csv \
  --l1-summary historical-l2-fee/data/l1/eth_l1_fee_365d_20260207T042811Z_summary_true_window.json \
  --l2-csv historical-l2-fee/data/l2/arb1_fee_merged_20260211T131033Z.csv \
  --l2-base-csv historical-l2-fee/data/l2/base_fee_merged_20260211T131033Z.csv \
  --l2-scroll-csv historical-l2-fee/data/l2/scroll_fee_merged_20260211T131033Z.csv \
  --l2-optimism-csv historical-l2-fee/data/l2/optimism_fee_115658365_131529181_step60_20260211T151518Z.csv \
  --no-l1-rpc-anchor \
  --title "L1 + L2 Fee History (Synced by Time) - prior365" \
  --out-html historical-l2-fee/data/plots/fee_history_l1_l2_synced_prior365.html \
  --out-data-js historical-l2-fee/data/plots/fee_history_l1_l2_synced_data_prior365.js \
  --out-summary historical-l2-fee/data/plots/fee_history_l1_l2_synced_prior365_summary.json

python3 historical-l2-fee/scripts/generate_synced_l1_l2_switcher_html.py \
  --out-html historical-l2-fee/data/plots/fee_history_l1_l2_synced.html \
  --current-page fee_history_l1_l2_synced_current365.html \
  --prior-page fee_history_l1_l2_synced_prior365.html
```
