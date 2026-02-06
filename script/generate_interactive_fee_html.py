#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path


def read_fee_csv(csv_path: Path):
    block_numbers = []
    base_fee_gwei = []
    blob_fee_gwei = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            block_numbers.append(int(row["block_number"]))
            base_fee_gwei.append(int(row["base_fee_per_gas_wei"]) / 1e9)
            blob_fee_gwei.append(int(row["base_fee_per_blob_gas_wei"]) / 1e9)

    if not block_numbers:
        raise ValueError(f"No rows found in {csv_path}")

    return block_numbers, base_fee_gwei, blob_fee_gwei


def build_html(block_numbers, base_fee_gwei, blob_fee_gwei, title):
    block_json = json.dumps(block_numbers, separators=(",", ":"))
    base_json = json.dumps(base_fee_gwei, separators=(",", ":"))
    blob_json = json.dumps(blob_fee_gwei, separators=(",", ":"))

    min_block = block_numbers[0]
    max_block = block_numbers[-1]

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <script src=\"./plotly-2.35.2.min.js\"></script>
  <script>
    if (!window.Plotly) {{
      const s = document.createElement('script');
      s.src = 'https://cdn.plot.ly/plotly-2.35.2.min.js';
      document.head.appendChild(s);
    }}
  </script>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #dbe3ef;
      --accent: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
      color: var(--text);
      background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 35%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 20px auto;
      padding: 0 16px 24px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    .sub {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }}
    label {{
      font-size: 13px;
      color: var(--muted);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    input[type=number] {{
      width: 140px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      padding: 6px 10px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
    }}
    button.primary {{
      border-color: transparent;
      background: var(--accent);
      color: #fff;
    }}
    .range-text {{
      margin-left: auto;
      font-size: 12px;
      color: var(--muted);
    }}
    .status {{
      margin: 4px 0 0;
      min-height: 18px;
      font-size: 12px;
      color: #b45309;
    }}
    .plot {{
      width: 100%;
      height: 420px;
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      overflow: hidden;
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>{title}</h1>
      <p class=\"sub\">Interactive 30-day Ethereum L1 fee history. Use block range controls, built-in zoom, or range sliders. Both charts stay synchronized.</p>

      <div class=\"controls\">
        <label>Min block <input id=\"minBlock\" type=\"number\" /></label>
        <label>Max block <input id=\"maxBlock\" type=\"number\" /></label>
        <button class=\"primary\" id=\"applyBtn\">Apply range</button>
        <button id=\"resetBtn\">Reset full range</button>
        <button id=\"tail20kBtn\">Last 20k blocks</button>
        <button id=\"tail5kBtn\">Last 5k blocks</button>
        <span class=\"range-text\" id=\"rangeText\"></span>
      </div>
      <div class=\"status\" id=\"status\"></div>

      <div id=\"basePlot\" class=\"plot\"></div>
      <div id=\"blobPlot\" class=\"plot\"></div>
    </div>
  </div>

  <script>
    const blocks = {block_json};
    const baseFeeGwei = {base_json};
    const blobFeeGwei = {blob_json};

    const MIN_BLOCK = {min_block};
    const MAX_BLOCK = {max_block};

    const minInput = document.getElementById('minBlock');
    const maxInput = document.getElementById('maxBlock');
    const rangeText = document.getElementById('rangeText');
    const status = document.getElementById('status');
    const baseDiv = document.getElementById('basePlot');
    const blobDiv = document.getElementById('blobPlot');

    minInput.value = MIN_BLOCK;
    maxInput.value = MAX_BLOCK;

    const sharedConfig = {{ responsive: true, displaylogo: false }};

    const baseTrace = {{
      x: blocks,
      y: baseFeeGwei,
      type: 'scattergl',
      mode: 'lines',
      line: {{ width: 1, color: '#1d4ed8' }},
      name: 'Base fee',
      hovertemplate: 'Block %{{x}}<br>Base fee: %{{y:.6f}} gwei<extra></extra>'
    }};

    const blobTrace = {{
      x: blocks,
      y: blobFeeGwei,
      type: 'scattergl',
      mode: 'lines',
      line: {{ width: 1, color: '#ea580c' }},
      name: 'Blob base fee',
      hovertemplate: 'Block %{{x}}<br>Blob fee: %{{y:.6f}} gwei<extra></extra>'
    }};

    const baseLayout = {{
      title: 'L1 Base Fee (gwei)',
      margin: {{ l: 70, r: 20, t: 48, b: 58 }},
      paper_bgcolor: '#ffffff',
      plot_bgcolor: '#ffffff',
      xaxis: {{
        title: 'L1 block number',
        range: [MIN_BLOCK, MAX_BLOCK],
        rangeslider: {{ visible: true }}
      }},
      yaxis: {{ title: 'gwei' }}
    }};

    const blobLayout = {{
      title: 'L1 Blob Base Fee (gwei)',
      margin: {{ l: 70, r: 20, t: 48, b: 58 }},
      paper_bgcolor: '#ffffff',
      plot_bgcolor: '#ffffff',
      xaxis: {{
        title: 'L1 block number',
        range: [MIN_BLOCK, MAX_BLOCK],
        rangeslider: {{ visible: true }}
      }},
      yaxis: {{ title: 'gwei' }}
    }};

    let syncing = false;

    function setStatus(msg) {{
      status.textContent = msg || '';
    }}

    function clampRange(minVal, maxVal) {{
      let a = Number(minVal);
      let b = Number(maxVal);
      if (!Number.isFinite(a) || !Number.isFinite(b)) return [MIN_BLOCK, MAX_BLOCK];
      if (a > b) [a, b] = [b, a];
      a = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(a)));
      b = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(b)));
      if (a === b) b = Math.min(MAX_BLOCK, a + 1);
      return [a, b];
    }}

    function updateRangeText(a, b) {{
      rangeText.textContent = `Showing blocks ${{a.toLocaleString()}} - ${{b.toLocaleString()}} (${{(b-a+1).toLocaleString()}} blocks)`;
    }}

    async function applyRange(a, b) {{
      const [minB, maxB] = clampRange(a, b);
      minInput.value = minB;
      maxInput.value = maxB;
      updateRangeText(minB, maxB);

      syncing = true;
      await Promise.all([
        Plotly.relayout(baseDiv, {{ 'xaxis.range': [minB, maxB] }}),
        Plotly.relayout(blobDiv, {{ 'xaxis.range': [minB, maxB] }})
      ]);
      syncing = false;
    }}

    function readRangeFromRelayout(evt) {{
      if (evt['xaxis.range[0]'] !== undefined && evt['xaxis.range[1]'] !== undefined) {{
        return [evt['xaxis.range[0]'], evt['xaxis.range[1]']];
      }}
      if (evt['xaxis.range'] !== undefined && Array.isArray(evt['xaxis.range'])) {{
        return [evt['xaxis.range'][0], evt['xaxis.range'][1]];
      }}
      if (evt['xaxis.autorange']) {{
        return [MIN_BLOCK, MAX_BLOCK];
      }}
      return null;
    }}

    function bindSync(srcDiv, otherDiv) {{
      srcDiv.on('plotly_relayout', async (evt) => {{
        if (syncing) return;
        const r = readRangeFromRelayout(evt);
        if (!r) return;
        const [a, b] = clampRange(r[0], r[1]);
        syncing = true;
        minInput.value = a;
        maxInput.value = b;
        updateRangeText(a, b);
        await Plotly.relayout(otherDiv, {{ 'xaxis.range': [a, b] }});
        syncing = false;
      }});
    }}

    function bindControls() {{
      document.getElementById('applyBtn').addEventListener('click', () => applyRange(minInput.value, maxInput.value));
      document.getElementById('resetBtn').addEventListener('click', () => applyRange(MIN_BLOCK, MAX_BLOCK));
      document.getElementById('tail20kBtn').addEventListener('click', () => applyRange(MAX_BLOCK - 20000, MAX_BLOCK));
      document.getElementById('tail5kBtn').addEventListener('click', () => applyRange(MAX_BLOCK - 5000, MAX_BLOCK));
      minInput.addEventListener('keydown', (e) => {{ if (e.key === 'Enter') applyRange(minInput.value, maxInput.value); }});
      maxInput.addEventListener('keydown', (e) => {{ if (e.key === 'Enter') applyRange(minInput.value, maxInput.value); }});
      updateRangeText(MIN_BLOCK, MAX_BLOCK);
    }}

    function waitForPlotly(maxAttempts = 80) {{
      return new Promise((resolve, reject) => {{
        let attempts = 0;
        const t = setInterval(() => {{
          if (window.Plotly) {{
            clearInterval(t);
            resolve();
            return;
          }}
          attempts += 1;
          if (attempts >= maxAttempts) {{
            clearInterval(t);
            reject(new Error('Plotly failed to load'));
          }}
        }}, 100);
      }});
    }}

    async function init() {{
      bindControls();
      setStatus('Loading chart engine...');
      try {{
        await waitForPlotly();
        setStatus('Rendering charts...');
        await Plotly.newPlot(baseDiv, [baseTrace], baseLayout, sharedConfig);
        await Plotly.newPlot(blobDiv, [blobTrace], blobLayout, sharedConfig);
        bindSync(baseDiv, blobDiv);
        bindSync(blobDiv, baseDiv);
        setStatus('');
      }} catch (err) {{
        console.error(err);
        setStatus('Interactive charts failed to load. If you are in an IDE preview, open this file in a regular browser.');
      }}
    }}

    init();
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate interactive HTML for fee history")
    parser.add_argument("--csv", required=True, help="Path to fee history CSV")
    parser.add_argument("--out", required=True, help="Output HTML path")
    parser.add_argument("--title", default="Ethereum L1 Fee History Explorer", help="HTML page title")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    out_path = Path(args.out).resolve()

    blocks, base, blob = read_fee_csv(csv_path)
    html = build_html(blocks, base, blob, args.title)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)

    print(out_path)


if __name__ == "__main__":
    main()
