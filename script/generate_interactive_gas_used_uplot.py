#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path


def read_gas_csv(csv_path: Path):
    blocks = []
    gas_used = []
    gas_limit = []
    gas_used_ratio = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            blocks.append(int(row["block_number"]))
            gas_used.append(int(row["gas_used"]))
            gas_limit.append(int(row["gas_limit"]))
            gas_used_ratio.append(float(row["gas_used_ratio"]))

    if not blocks:
        raise ValueError(f"No rows found in {csv_path}")

    return blocks, gas_used, gas_limit, gas_used_ratio


def build_app_js(blocks, gas_used, gas_limit, gas_used_ratio):
    blocks_json = json.dumps(blocks, separators=(",", ":"))
    gas_used_json = json.dumps(gas_used, separators=(",", ":"))
    gas_limit_json = json.dumps(gas_limit, separators=(",", ":"))
    gas_used_ratio_json = json.dumps(gas_used_ratio, separators=(",", ":"))

    return f"""(function () {{
  const blocks = {blocks_json};
  const gasUsed = {gas_used_json};
  const gasLimit = {gas_limit_json};
  const gasUsedRatio = {gas_used_ratio_json};

  const MIN_BLOCK = blocks[0];
  const MAX_BLOCK = blocks[blocks.length - 1];

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const status = document.getElementById('status');
  const latestGasUsed = document.getElementById('latestGasUsed');
  const latestGasLimit = document.getElementById('latestGasLimit');
  const latestGasUsedRatio = document.getElementById('latestGasUsedRatio');

  const gasUsedWrap = document.getElementById('gasUsedPlot');
  const ratioWrap = document.getElementById('ratioPlot');

  function setStatus(msg) {{
    status.textContent = msg || '';
  }}

  function formatNum(x, frac = 2) {{
    return Number(x).toLocaleString(undefined, {{ maximumFractionDigits: frac }});
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
  let gasUsedPlot;
  let ratioPlot;

  function allPlots() {{
    return [gasUsedPlot, ratioPlot].filter(Boolean);
  }}

  function onSetScale(u, key) {{
    if (key !== 'x' || syncing) return;
    applyRange(u.scales.x.min, u.scales.x.max, u);
  }}

  function makeOpts(title, yLabel, series, width, height) {{
    return {{
      title,
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series,
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: yLabel }}
      ],
      cursor: {{ drag: {{ x: true, y: false, setScale: true }} }},
      hooks: {{ setScale: [onSetScale] }}
    }};
  }}

  function applyRange(minVal, maxVal, sourcePlot) {{
    const [minB, maxB] = clampRange(minVal, maxVal);
    minInput.value = minB;
    maxInput.value = maxB;
    updateRangeText(minB, maxB);

    syncing = true;
    for (const p of allPlots()) {{
      if (p !== sourcePlot) p.setScale('x', {{ min: minB, max: maxB }});
    }}
    syncing = false;
  }}

  function resizePlots() {{
    const width = Math.max(480, gasUsedWrap.clientWidth - 8);
    for (const p of allPlots()) {{
      p.setSize({{ width, height: 320 }});
    }}
  }}

  const width = Math.max(480, gasUsedWrap.clientWidth - 8);

  gasUsedPlot = new uPlot(
    makeOpts(
      'L1 Gas Used / Gas Limit',
      'Gas',
      [
        {{}},
        {{ label: 'Gas used', stroke: '#2563eb', width: 1.2 }},
        {{ label: 'Gas limit', stroke: '#94a3b8', width: 1.0 }}
      ],
      width,
      320
    ),
    [blocks, gasUsed, gasLimit],
    gasUsedWrap
  );

  ratioPlot = new uPlot(
    makeOpts(
      'L1 Gas Used Ratio',
      'ratio',
      [
        {{}},
        {{ label: 'Gas used ratio', stroke: '#0f766e', width: 1.2 }}
      ],
      width,
      320
    ),
    [blocks, gasUsedRatio],
    ratioWrap
  );

  const lastIdx = blocks.length - 1;
  latestGasUsed.textContent = formatNum(gasUsed[lastIdx], 0);
  latestGasLimit.textContent = formatNum(gasLimit[lastIdx], 0);
  latestGasUsedRatio.textContent = formatNum(gasUsedRatio[lastIdx], 4);

  updateRangeText(MIN_BLOCK, MAX_BLOCK);

  document.getElementById('applyBtn').addEventListener('click', function () {{
    applyRange(minInput.value, maxInput.value, null);
  }});

  document.getElementById('resetBtn').addEventListener('click', function () {{
    applyRange(MIN_BLOCK, MAX_BLOCK, null);
  }});

  document.getElementById('tail2kBtn').addEventListener('click', function () {{
    applyRange(MAX_BLOCK - 2000, MAX_BLOCK, null);
  }});

  document.getElementById('tail500Btn').addEventListener('click', function () {{
    applyRange(MAX_BLOCK - 500, MAX_BLOCK, null);
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
    h1 {{ margin: 0 0 10px; font-size: 22px; }}
    .sub {{ margin: 0 0 12px; color: var(--muted); font-size: 13px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
    label {{ font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }}
    input[type=number] {{ width: 150px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--text); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 13px; }}
    button.primary {{ border-color: transparent; background: var(--accent); color: #fff; }}
    .range-text {{ margin-left: auto; font-size: 12px; color: var(--muted); }}
    .status {{ margin: 4px 0 0; min-height: 18px; font-size: 12px; color: #b45309; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--muted); margin: 6px 0; }}
    .plot {{ width: 100%; min-height: 336px; margin-top: 10px; border: 1px solid var(--line); border-radius: 10px; padding: 6px; background: #fff; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>{title}</h1>
      <p class=\"sub\">Drag horizontally inside either chart to zoom. Block range controls and zoom are synchronized.</p>
      <div class=\"controls\">
        <label>Min block <input id=\"minBlock\" type=\"number\" /></label>
        <label>Max block <input id=\"maxBlock\" type=\"number\" /></label>
        <button class=\"primary\" id=\"applyBtn\">Apply range</button>
        <button id=\"resetBtn\">Reset full range</button>
        <button id=\"tail2kBtn\">Last 2k blocks</button>
        <button id=\"tail500Btn\">Last 500 blocks</button>
        <span class=\"range-text\" id=\"rangeText\"></span>
      </div>
      <div class=\"metrics\">
        <span>Latest gas used: <strong id=\"latestGasUsed\">-</strong></span>
        <span>Latest gas limit: <strong id=\"latestGasLimit\">-</strong></span>
        <span>Latest gas used ratio: <strong id=\"latestGasUsedRatio\">-</strong></span>
      </div>
      <div class=\"status\" id=\"status\"></div>
      <div id=\"gasUsedPlot\" class=\"plot\"></div>
      <div id=\"ratioPlot\" class=\"plot\"></div>
    </div>
  </div>
  <script src=\"./uPlot.iife.min.js\"></script>
  <script src=\"./{js_filename}\"></script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate interactive uPlot HTML for L1 gas used history")
    parser.add_argument("--csv", required=True, help="Path to gas used history CSV")
    parser.add_argument("--out-html", required=True, help="Output HTML path")
    parser.add_argument("--out-js", required=True, help="Output JS path")
    parser.add_argument("--title", default="Ethereum L1 Gas Used Explorer", help="Page title")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    out_html = Path(args.out_html).resolve()
    out_js = Path(args.out_js).resolve()

    blocks, gas_used, gas_limit, gas_used_ratio = read_gas_csv(csv_path)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_js.parent.mkdir(parents=True, exist_ok=True)

    out_js.write_text(build_app_js(blocks, gas_used, gas_limit, gas_used_ratio))
    out_html.write_text(build_html(args.title, out_js.name))

    print(out_html)
    print(out_js)


if __name__ == "__main__":
    main()
