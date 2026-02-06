#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path


def read_fee_csv(csv_path: Path):
    blocks = []
    base = []
    blob = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            blocks.append(int(row["block_number"]))
            base.append(int(row["base_fee_per_gas_wei"]) / 1e9)
            blob.append(int(row["base_fee_per_blob_gas_wei"]) / 1e9)
    if not blocks:
        raise ValueError(f"No rows found in {csv_path}")
    return blocks, base, blob


def build_app_js(blocks, base, blob):
    blocks_json = json.dumps(blocks, separators=(",", ":"))
    base_json = json.dumps(base, separators=(",", ":"))
    blob_json = json.dumps(blob, separators=(",", ":"))

    return f"""(function () {{
  const blocks = {blocks_json};
  const baseFeeGwei = {base_json};
  const blobFeeGwei = {blob_json};

  const MIN_BLOCK = blocks[0];
  const MAX_BLOCK = blocks[blocks.length - 1];

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const status = document.getElementById('status');
  const baseWrap = document.getElementById('basePlot');
  const blobWrap = document.getElementById('blobPlot');

  function setStatus(msg) {{
    status.textContent = msg || '';
  }}

  function clampRange(a, b) {{
    let x = Number(a);
    let y = Number(b);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return [MIN_BLOCK, MAX_BLOCK];
    if (x > y) {{ const t = x; x = y; y = t; }}
    x = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(x)));
    y = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(y)));
    if (x === y) y = Math.min(MAX_BLOCK, x + 1);
    return [x, y];
  }}

  function updateRangeText(a, b) {{
    rangeText.textContent = `Showing blocks ${{a.toLocaleString()}} - ${{b.toLocaleString()}} (${{(b - a + 1).toLocaleString()}} blocks)`;
  }}

  minInput.value = MIN_BLOCK;
  maxInput.value = MAX_BLOCK;

  if (!window.uPlot) {{
    setStatus('uPlot failed to load. Open this file from its folder so local JS files resolve.');
    return;
  }}

  setStatus('Rendering charts...');

  let syncing = false;
  let basePlot;
  let blobPlot;

  function onSetScale(u, key) {{
    if (key !== 'x' || syncing) return;
    const min = u.scales.x.min;
    const max = u.scales.x.max;
    applyRange(min, max, u);
  }}

  function makeOpts(title, strokeColor, width, height) {{
    return {{
      title,
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: title, stroke: strokeColor, width: 1 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'gwei' }}
      ],
      cursor: {{
        drag: {{ x: true, y: false, setScale: true }}
      }},
      hooks: {{
        setScale: [onSetScale]
      }}
    }};
  }}

  function applyRange(minVal, maxVal, sourcePlot) {{
    const [minB, maxB] = clampRange(minVal, maxVal);
    minInput.value = minB;
    maxInput.value = maxB;
    updateRangeText(minB, maxB);

    syncing = true;
    if (sourcePlot !== basePlot) basePlot.setScale('x', {{ min: minB, max: maxB }});
    if (sourcePlot !== blobPlot) blobPlot.setScale('x', {{ min: minB, max: maxB }});
    syncing = false;
  }}

  function resizePlots() {{
    const width = Math.max(480, baseWrap.clientWidth - 8);
    basePlot.setSize({{ width, height: 360 }});
    blobPlot.setSize({{ width, height: 360 }});
  }}

  const width = Math.max(480, baseWrap.clientWidth - 8);
  basePlot = new uPlot(
    makeOpts('L1 Base Fee (gwei)', '#1d4ed8', width, 360),
    [blocks, baseFeeGwei],
    baseWrap
  );

  blobPlot = new uPlot(
    makeOpts('L1 Blob Base Fee (gwei)', '#ea580c', width, 360),
    [blocks, blobFeeGwei],
    blobWrap
  );

  updateRangeText(MIN_BLOCK, MAX_BLOCK);

  document.getElementById('applyBtn').addEventListener('click', function () {{
    applyRange(minInput.value, maxInput.value, null);
  }});

  document.getElementById('resetBtn').addEventListener('click', function () {{
    applyRange(MIN_BLOCK, MAX_BLOCK, null);
  }});

  document.getElementById('tail20kBtn').addEventListener('click', function () {{
    applyRange(MAX_BLOCK - 20000, MAX_BLOCK, null);
  }});

  document.getElementById('tail5kBtn').addEventListener('click', function () {{
    applyRange(MAX_BLOCK - 5000, MAX_BLOCK, null);
  }});

  minInput.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  }});

  maxInput.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  }});

  let resizeTimer;
  window.addEventListener('resize', function () {{
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizePlots, 120);
  }});

  setStatus('');
}})();
"""


def build_html(title, js_filename):
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <link rel=\"stylesheet\" href=\"./uPlot.min.css\" />
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
    .wrap {{ max-width: 1400px; margin: 20px auto; padding: 0 16px 24px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    }}
    h1 {{ margin: 0 0 12px; font-size: 22px; }}
    .sub {{ margin: 0 0 14px; color: var(--muted); font-size: 13px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
    label {{ font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }}
    input[type=number] {{ width: 140px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--text); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 13px; }}
    button.primary {{ border-color: transparent; background: var(--accent); color: #fff; }}
    .range-text {{ margin-left: auto; font-size: 12px; color: var(--muted); }}
    .status {{ margin: 4px 0 0; min-height: 18px; font-size: 12px; color: #b45309; }}
    .plot {{ width: 100%; min-height: 376px; margin-top: 10px; border: 1px solid var(--line); border-radius: 10px; padding: 6px; background: #fff; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>{title}</h1>
      <p class=\"sub\">Drag horizontally inside either chart to zoom. Double-click chart to reset its zoom. Apply block range inputs to control both charts together.</p>

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

  <script src=\"./uPlot.iife.min.js\"></script>
  <script src=\"./{js_filename}\"></script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate interactive uPlot HTML for fee history")
    parser.add_argument("--csv", required=True, help="Path to fee history CSV")
    parser.add_argument("--out-html", required=True, help="Output HTML path")
    parser.add_argument("--out-js", required=True, help="Output JS path")
    parser.add_argument("--title", default="Ethereum L1 Fee History Explorer (uPlot)", help="Page title")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    out_html = Path(args.out_html).resolve()
    out_js = Path(args.out_js).resolve()

    blocks, base, blob = read_fee_csv(csv_path)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_js.parent.mkdir(parents=True, exist_ok=True)

    out_js.write_text(build_app_js(blocks, base, blob))
    out_html.write_text(build_html(args.title, out_js.name))

    print(out_html)
    print(out_js)


if __name__ == "__main__":
    main()
