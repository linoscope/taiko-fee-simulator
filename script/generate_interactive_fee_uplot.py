#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path

L1_BLOCK_TIME_SECONDS = 12
BLOB_GAS_PER_BLOB = 131_072

DEFAULT_POST_EVERY_BLOCKS = 10
DEFAULT_L2_GAS_PER_L2_BLOCK = 10_000_000
DEFAULT_L2_BLOCK_TIME_SECONDS = 2
DEFAULT_L1_GAS_USED = 100_000
DEFAULT_NUM_BLOBS = 2
DEFAULT_PRIORITY_FEE_GWEI = 1.0
DEFAULT_MIN_FEE_GWEI = 0.0
DEFAULT_MAX_FEE_GWEI = 1.0
DEFAULT_INITIAL_VAULT_ETH = 10.0
DEFAULT_TARGET_VAULT_ETH = 10.0

DEFAULT_L2_GAS_PER_L1_BLOCK = (
    DEFAULT_L2_GAS_PER_L2_BLOCK * (L1_BLOCK_TIME_SECONDS / DEFAULT_L2_BLOCK_TIME_SECONDS)
)
DEFAULT_L2_GAS_PER_PROPOSAL = DEFAULT_L2_GAS_PER_L1_BLOCK * DEFAULT_POST_EVERY_BLOCKS
DEFAULT_ALPHA_GAS = DEFAULT_L1_GAS_USED / DEFAULT_L2_GAS_PER_PROPOSAL
DEFAULT_ALPHA_BLOB = (DEFAULT_NUM_BLOBS * BLOB_GAS_PER_BLOB) / DEFAULT_L2_GAS_PER_PROPOSAL


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
  const BLOB_GAS_PER_BLOB = {BLOB_GAS_PER_BLOB};
  const L1_BLOCK_TIME_SECONDS = {L1_BLOCK_TIME_SECONDS};
  const DEFAULT_ALPHA_GAS = {DEFAULT_ALPHA_GAS:.12f};
  const DEFAULT_ALPHA_BLOB = {DEFAULT_ALPHA_BLOB:.12f};

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const status = document.getElementById('status');

  const postEveryBlocksInput = document.getElementById('postEveryBlocks');
  const l2GasPerL2BlockInput = document.getElementById('l2GasPerL2Block');
  const l2BlockTimeSecInput = document.getElementById('l2BlockTimeSec');
  const l1GasUsedInput = document.getElementById('l1GasUsed');
  const numBlobsInput = document.getElementById('numBlobs');
  const priorityFeeGweiInput = document.getElementById('priorityFeeGwei');
  const autoAlphaInput = document.getElementById('autoAlpha');
  const alphaGasInput = document.getElementById('alphaGas');
  const alphaBlobInput = document.getElementById('alphaBlob');
  const minFeeGweiInput = document.getElementById('minFeeGwei');
  const maxFeeGweiInput = document.getElementById('maxFeeGwei');
  const initialVaultEthInput = document.getElementById('initialVaultEth');
  const targetVaultEthInput = document.getElementById('targetVaultEth');

  const derivedL2GasPerL1BlockText = document.getElementById('derivedL2GasPerL1Block');
  const derivedL2GasPerProposalText = document.getElementById('derivedL2GasPerProposal');
  const latestPostingCost = document.getElementById('latestPostingCost');
  const latestRequiredFee = document.getElementById('latestRequiredFee');
  const latestChargedFee = document.getElementById('latestChargedFee');
  const latestGasComponentFee = document.getElementById('latestGasComponentFee');
  const latestBlobComponentFee = document.getElementById('latestBlobComponentFee');
  const latestVaultValue = document.getElementById('latestVaultValue');
  const latestVaultGap = document.getElementById('latestVaultGap');

  const baseWrap = document.getElementById('basePlot');
  const blobWrap = document.getElementById('blobPlot');
  const costWrap = document.getElementById('costPlot');
  const reqWrap = document.getElementById('requiredFeePlot');
  const vaultWrap = document.getElementById('vaultPlot');

  function setStatus(msg) {{
    status.textContent = msg || '';
  }}

  function formatNum(x, frac = 4) {{
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

  function parsePositive(inputEl, fallback) {{
    const v = Number(inputEl.value);
    return Number.isFinite(v) && v >= 0 ? v : fallback;
  }}

  function parsePositiveInt(inputEl, fallback) {{
    const v = Number(inputEl.value);
    if (!Number.isFinite(v) || v < 1) return fallback;
    return Math.floor(v);
  }}

  let derivedGasCostEth = [];
  let derivedBlobCostEth = [];
  let derivedPostingCostEth = [];
  let derivedRequiredFeeGwei = [];
  let derivedGasFeeComponentGwei = [];
  let derivedBlobFeeComponentGwei = [];
  let derivedChargedFeeGwei = [];
  let derivedVaultEth = [];
  let derivedVaultTargetEth = [];

  function recalcDerivedSeries() {{
    const postEveryBlocks = parsePositiveInt(postEveryBlocksInput, 10);
    const l2GasPerL2Block = parsePositive(l2GasPerL2BlockInput, 0);
    const l2BlockTimeSec = parsePositive(l2BlockTimeSecInput, 12);
    const l2BlocksPerL1Block = l2BlockTimeSec > 0 ? (L1_BLOCK_TIME_SECONDS / l2BlockTimeSec) : 0;
    const l2GasPerL1Block = l2GasPerL2Block * l2BlocksPerL1Block;
    const l1GasUsed = parsePositive(l1GasUsedInput, 0);
    const numBlobs = parsePositive(numBlobsInput, 0);
    const priorityFeeGwei = parsePositive(priorityFeeGweiInput, 0);
    const minFeeGwei = parsePositive(minFeeGweiInput, 0);
    const maxFeeGwei = parsePositive(maxFeeGweiInput, 10);
    const initialVaultEth = parsePositive(initialVaultEthInput, 0);
    const targetVaultEth = parsePositive(targetVaultEthInput, 0);

    const l2GasPerProposal = l2GasPerL1Block * postEveryBlocks;
    const autoAlphaEnabled = autoAlphaInput.checked;
    const autoAlphaGas = l2GasPerProposal > 0 ? (l1GasUsed / l2GasPerProposal) : 0;
    const autoAlphaBlob =
      l2GasPerProposal > 0 ? ((numBlobs * BLOB_GAS_PER_BLOB) / l2GasPerProposal) : 0;
    if (autoAlphaEnabled) {{
      alphaGasInput.value = autoAlphaGas.toFixed(6);
      alphaBlobInput.value = autoAlphaBlob.toFixed(6);
    }}
    alphaGasInput.disabled = autoAlphaEnabled;
    alphaBlobInput.disabled = autoAlphaEnabled;
    const alphaGas = autoAlphaEnabled ? autoAlphaGas : parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS);
    const alphaBlob = autoAlphaEnabled ? autoAlphaBlob : parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB);

    const priorityFeeWei = priorityFeeGwei * 1e9;
    const minFeeWei = minFeeGwei * 1e9;
    const maxFeeWei = Math.max(minFeeWei, maxFeeGwei * 1e9);

    derivedL2GasPerL1BlockText.textContent = `${{formatNum(l2GasPerL1Block, 0)}} gas/L1 block`;
    derivedL2GasPerProposalText.textContent = `${{formatNum(l2GasPerProposal, 0)}} gas/proposal`;

    const n = blocks.length;
    derivedGasCostEth = new Array(n);
    derivedBlobCostEth = new Array(n);
    derivedPostingCostEth = new Array(n);
    derivedRequiredFeeGwei = new Array(n);
    derivedGasFeeComponentGwei = new Array(n);
    derivedBlobFeeComponentGwei = new Array(n);
    derivedChargedFeeGwei = new Array(n);
    derivedVaultEth = new Array(n);
    derivedVaultTargetEth = new Array(n);

    let vault = initialVaultEth;
    let pendingRevenueEth = 0;

    for (let i = 0; i < n; i++) {{
      const baseFeeWei = baseFeeGwei[i] * 1e9;
      const blobBaseFeeWei = blobFeeGwei[i] * 1e9;

      const gasCostWei = l1GasUsed * (baseFeeWei + priorityFeeWei);
      const blobCostWei = numBlobs * BLOB_GAS_PER_BLOB * blobBaseFeeWei;
      const totalCostWei = gasCostWei + blobCostWei;

      derivedGasCostEth[i] = gasCostWei / 1e18;
      derivedBlobCostEth[i] = blobCostWei / 1e18;
      derivedPostingCostEth[i] = totalCostWei / 1e18;
      const gasComponentWei = alphaGas * (baseFeeWei + priorityFeeWei);
      const blobComponentWei = alphaBlob * blobBaseFeeWei;
      const chargedFeeWeiPerL2Gas = Math.max(
        minFeeWei,
        Math.min(maxFeeWei, gasComponentWei + blobComponentWei)
      );
      derivedGasFeeComponentGwei[i] = gasComponentWei / 1e9;
      derivedBlobFeeComponentGwei[i] = blobComponentWei / 1e9;
      derivedChargedFeeGwei[i] = chargedFeeWeiPerL2Gas / 1e9;

      if (l2GasPerProposal > 0) {{
        const breakEvenFeeWeiPerL2Gas = totalCostWei / l2GasPerProposal;
        derivedRequiredFeeGwei[i] = breakEvenFeeWeiPerL2Gas / 1e9;
      }} else {{
        derivedRequiredFeeGwei[i] = null;
      }}

      const l2RevenueEthPerBlock =
        (chargedFeeWeiPerL2Gas * l2GasPerL1Block) / 1e18;
      // Post-time settlement: revenue is recognized only at posting blocks.
      pendingRevenueEth += l2RevenueEthPerBlock;

      // Fixed-cadence posting event: deduct fixed-resource posting cost at post blocks.
      const posted = ((i + 1) % postEveryBlocks) === 0;
      if (posted) {{
        vault += pendingRevenueEth;
        pendingRevenueEth = 0;
        vault -= derivedPostingCostEth[i];
      }}

      derivedVaultEth[i] = vault;
      derivedVaultTargetEth[i] = targetVaultEth;
    }}

    if (costPlot && requiredFeePlot && vaultPlot) {{
      costPlot.setData([blocks, derivedGasCostEth, derivedBlobCostEth, derivedPostingCostEth]);
      requiredFeePlot.setData([
        blocks,
        derivedGasFeeComponentGwei,
        derivedBlobFeeComponentGwei,
        derivedChargedFeeGwei
      ]);
      vaultPlot.setData([blocks, derivedVaultTargetEth, derivedVaultEth]);
    }}

    const lastIdx = n - 1;
    latestPostingCost.textContent = `${{formatNum(derivedPostingCostEth[lastIdx], 6)}} ETH`;
    if (derivedRequiredFeeGwei[lastIdx] == null || derivedChargedFeeGwei[lastIdx] == null) {{
      latestRequiredFee.textContent = 'n/a';
      latestChargedFee.textContent = 'n/a';
      latestGasComponentFee.textContent = 'n/a';
      latestBlobComponentFee.textContent = 'n/a';
    }} else {{
      latestRequiredFee.textContent = `${{formatNum(derivedRequiredFeeGwei[lastIdx], 4)}} gwei/L2gas`;
      latestChargedFee.textContent = `${{formatNum(derivedChargedFeeGwei[lastIdx], 4)}} gwei/L2gas`;
      latestGasComponentFee.textContent = `${{formatNum(derivedGasFeeComponentGwei[lastIdx], 4)}} gwei/L2gas`;
      latestBlobComponentFee.textContent = `${{formatNum(derivedBlobFeeComponentGwei[lastIdx], 4)}} gwei/L2gas`;
    }}
    latestVaultValue.textContent = `${{formatNum(derivedVaultEth[lastIdx], 6)}} ETH`;
    latestVaultGap.textContent = `${{formatNum(derivedVaultEth[lastIdx] - targetVaultEth, 6)}} ETH`;
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
  let costPlot;
  let requiredFeePlot;
  let vaultPlot;

  function allPlots() {{
    return [basePlot, blobPlot, costPlot, requiredFeePlot, vaultPlot].filter(Boolean);
  }}

  function onSetScale(u, key) {{
    if (key !== 'x' || syncing) return;
    const min = u.scales.x.min;
    const max = u.scales.x.max;
    applyRange(min, max, u);
  }}

  function makeOpts(title, yLabel, strokeColor, width, height) {{
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
        {{ label: yLabel }}
      ],
      cursor: {{
        drag: {{ x: true, y: false, setScale: true }}
      }},
      hooks: {{
        setScale: [onSetScale]
      }}
    }};
  }}

  function makeCostOpts(width, height) {{
    return {{
      title: 'Hypothetical Posting Cost (if posted at this block)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'Gas cost (ETH)', stroke: '#2563eb', width: 1 }},
        {{ label: 'Blob cost (ETH)', stroke: '#ea580c', width: 1 }},
        {{ label: 'Total cost (ETH)', stroke: '#7c3aed', width: 1.4 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'ETH' }}
      ],
      cursor: {{
        drag: {{ x: true, y: false, setScale: true }}
      }},
      hooks: {{
        setScale: [onSetScale]
      }}
    }};
  }}

  function makeRequiredFeeOpts(width, height) {{
    return {{
      title: 'Decoupled L2 Fee (alpha pass-through + clamped total)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'Gas component fee (gwei/L2 gas)', stroke: '#2563eb', width: 1 }},
        {{ label: 'Blob component fee (gwei/L2 gas)', stroke: '#ea580c', width: 1 }},
        {{ label: 'Charged fee (clamped total)', stroke: '#16a34a', width: 1.4 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'gwei / L2 gas' }}
      ],
      cursor: {{
        drag: {{ x: true, y: false, setScale: true }}
      }},
      hooks: {{
        setScale: [onSetScale]
      }}
    }};
  }}

  function makeVaultOpts(width, height) {{
    return {{
      title: 'Vault Value vs Target',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'Target vault (ETH)', stroke: '#dc2626', width: 1 }},
        {{ label: 'Current vault (ETH)', stroke: '#0f766e', width: 1.4 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'ETH' }}
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
    for (const p of allPlots()) {{
      if (p !== sourcePlot) p.setScale('x', {{ min: minB, max: maxB }});
    }}
    syncing = false;
  }}

  function resizePlots() {{
    const width = Math.max(480, baseWrap.clientWidth - 8);
    for (const p of allPlots()) {{
      p.setSize({{ width, height: 320 }});
    }}
  }}

  const width = Math.max(480, baseWrap.clientWidth - 8);

  basePlot = new uPlot(
    makeOpts('L1 Base Fee', 'gwei', '#1d4ed8', width, 320),
    [blocks, baseFeeGwei],
    baseWrap
  );

  blobPlot = new uPlot(
    makeOpts('L1 Blob Base Fee', 'gwei', '#ea580c', width, 320),
    [blocks, blobFeeGwei],
    blobWrap
  );

  costPlot = new uPlot(
    makeCostOpts(width, 320),
    [blocks, [], [], []],
    costWrap
  );

  requiredFeePlot = new uPlot(
    makeRequiredFeeOpts(width, 320),
    [blocks, [], [], []],
    reqWrap
  );

  vaultPlot = new uPlot(
    makeVaultOpts(width, 320),
    [blocks, [], []],
    vaultWrap
  );

  recalcDerivedSeries();
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

  document.getElementById('recalcBtn').addEventListener('click', recalcDerivedSeries);

  minInput.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  }});

  maxInput.addEventListener('keydown', function (e) {{
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  }});

  [
    postEveryBlocksInput,
    l2GasPerL2BlockInput,
    l2BlockTimeSecInput,
    l1GasUsedInput,
    numBlobsInput,
    priorityFeeGweiInput,
    autoAlphaInput,
    alphaGasInput,
    alphaBlobInput,
    minFeeGweiInput,
    maxFeeGweiInput,
    initialVaultEthInput,
    targetVaultEthInput
  ].forEach(function (el) {{
    el.addEventListener('keydown', function (e) {{
      if (e.key === 'Enter') recalcDerivedSeries();
    }});
    el.addEventListener('change', recalcDerivedSeries);
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
    .assumptions {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      margin-bottom: 8px;
      background: #f8fafc;
    }}
    .assumptions-title {{ font-size: 13px; color: var(--muted); margin-bottom: 8px; }}
    label {{ font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }}
    input[type=number] {{ width: 150px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; }}
    button {{ border: 1px solid var(--line); background: #fff; color: var(--text); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 13px; }}
    button.primary {{ border-color: transparent; background: var(--accent); color: #fff; }}
    .range-text {{ margin-left: auto; font-size: 12px; color: var(--muted); }}
    .status {{ margin: 4px 0 0; min-height: 18px; font-size: 12px; color: #b45309; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--muted); margin: 6px 0; }}
    .plot {{ width: 100%; min-height: 336px; margin-top: 10px; border: 1px solid var(--line); border-radius: 10px; padding: 6px; background: #fff; }}
    .formula {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #334155; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>{title}</h1>
      <p class=\"sub\">Drag horizontally inside any chart to zoom. Block range controls and zoom are synchronized across all charts.</p>

      <div class=\"controls\">
        <label>Min block <input id=\"minBlock\" type=\"number\" /></label>
        <label>Max block <input id=\"maxBlock\" type=\"number\" /></label>
        <button class=\"primary\" id=\"applyBtn\">Apply range</button>
        <button id=\"resetBtn\">Reset full range</button>
        <button id=\"tail20kBtn\">Last 20k blocks</button>
        <button id=\"tail5kBtn\">Last 5k blocks</button>
        <span class=\"range-text\" id=\"rangeText\"></span>
      </div>

      <div class=\"assumptions\">
        <div class=\"assumptions-title\">L2 posting assumptions</div>
        <div class=\"controls\">
          <label>Post every N L1 blocks <input id=\"postEveryBlocks\" type=\"number\" min=\"1\" step=\"1\" value=\"{DEFAULT_POST_EVERY_BLOCKS}\" /></label>
          <label>L2 gas / L2 block <input id=\"l2GasPerL2Block\" type=\"number\" min=\"0\" step=\"100000\" value=\"{DEFAULT_L2_GAS_PER_L2_BLOCK}\" /></label>
          <label>L2 block time (s) <input id=\"l2BlockTimeSec\" type=\"number\" min=\"0.1\" step=\"0.1\" value=\"{DEFAULT_L2_BLOCK_TIME_SECONDS}\" /></label>
          <label>L1 gas used <input id=\"l1GasUsed\" type=\"number\" min=\"0\" step=\"1000\" value=\"{DEFAULT_L1_GAS_USED}\" /></label>
          <label>Blobs <input id=\"numBlobs\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_NUM_BLOBS}\" /></label>
          <label>Priority fee (gwei) <input id=\"priorityFeeGwei\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_PRIORITY_FEE_GWEI:g}\" /></label>
          <label><input id=\"autoAlpha\" type=\"checkbox\" checked /> Auto alpha</label>
          <label>Alpha gas <input id=\"alphaGas\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_GAS:.6f}\" /></label>
          <label>Alpha blob <input id=\"alphaBlob\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_BLOB:.6f}\" /></label>
          <label>Min fee (gwei/L2 gas) <input id=\"minFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MIN_FEE_GWEI:g}\" /></label>
          <label>Max fee (gwei/L2 gas) <input id=\"maxFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MAX_FEE_GWEI:.1f}\" /></label>
          <label>Initial vault (ETH) <input id=\"initialVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_INITIAL_VAULT_ETH:g}\" /></label>
          <label>Target vault (ETH) <input id=\"targetVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_TARGET_VAULT_ETH:g}\" /></label>
          <button class=\"primary\" id=\"recalcBtn\">Recompute derived charts</button>
        </div>
        <div class=\"formula\">cost_wei(post_t) = l1GasUsed * (baseFee_t + priorityFee) + numBlobs * 131072 * blobBaseFee_t</div>
        <div class=\"formula\">fee_wei = clamp(alpha_gas * (baseFee + priorityFee) + alpha_blob * blobBaseFee, minFee, maxFee)</div>
        <div class=\"formula\">auto alpha uses alpha_gas = l1GasUsed / l2GasPerProposal, alpha_blob = (numBlobs * 131072) / l2GasPerProposal</div>
        <div class=\"formula\">Assume L1 block time = 12s; derived <strong id=\"derivedL2GasPerL1Block\">-</strong> and <strong id=\"derivedL2GasPerProposal\">-</strong></div>
        <div class=\"formula\">posting events at (i + 1) % postEveryBlocks == 0</div>
        <div class=\"metrics\">
          <span>Latest hypothetical posting cost: <strong id=\"latestPostingCost\">-</strong></span>
          <span>Latest required L2 fee (cost-side reference): <strong id=\"latestRequiredFee\">-</strong></span>
          <span>Latest charged L2 fee: <strong id=\"latestChargedFee\">-</strong></span>
          <span>Latest gas component fee: <strong id=\"latestGasComponentFee\">-</strong></span>
          <span>Latest blob component fee: <strong id=\"latestBlobComponentFee\">-</strong></span>
          <span>Latest vault value: <strong id=\"latestVaultValue\">-</strong></span>
          <span>Vault - target: <strong id=\"latestVaultGap\">-</strong></span>
        </div>
      </div>

      <div class=\"status\" id=\"status\"></div>
      <div id=\"basePlot\" class=\"plot\"></div>
      <div id=\"blobPlot\" class=\"plot\"></div>
      <div id=\"costPlot\" class=\"plot\"></div>
      <div id=\"requiredFeePlot\" class=\"plot\"></div>
      <div id=\"vaultPlot\" class=\"plot\"></div>
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
    parser.add_argument("--title", default="Ethereum + L2 Posting Cost Explorer", help="Page title")
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
