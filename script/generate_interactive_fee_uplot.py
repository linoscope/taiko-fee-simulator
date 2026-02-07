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
DEFAULT_CONTROLLER_MODE = "alpha-only"
DEFAULT_D_FF_BLOCKS = 0
DEFAULT_D_FB_BLOCKS = 12
DEFAULT_KP = 0.1
DEFAULT_KI = 0.0
DEFAULT_I_MIN = -5.0
DEFAULT_I_MAX = 5.0

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
  const DEMAND_MULTIPLIERS = Object.freeze({{ low: 0.7, base: 1.0, high: 1.4 }});

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const status = document.getElementById('status');

  const postEveryBlocksInput = document.getElementById('postEveryBlocks');
  const l2GasPerL2BlockInput = document.getElementById('l2GasPerL2Block');
  const l2BlockTimeSecInput = document.getElementById('l2BlockTimeSec');
  const l2GasScenarioInput = document.getElementById('l2GasScenario');
  const l2DemandRegimeInput = document.getElementById('l2DemandRegime');
  const l1GasUsedInput = document.getElementById('l1GasUsed');
  const numBlobsInput = document.getElementById('numBlobs');
  const priorityFeeGweiInput = document.getElementById('priorityFeeGwei');
  const autoAlphaInput = document.getElementById('autoAlpha');
  const alphaGasInput = document.getElementById('alphaGas');
  const alphaBlobInput = document.getElementById('alphaBlob');
  const controllerModeInput = document.getElementById('controllerMode');
  const dffBlocksInput = document.getElementById('dffBlocks');
  const dfbBlocksInput = document.getElementById('dfbBlocks');
  const kpInput = document.getElementById('kp');
  const kiInput = document.getElementById('ki');
  const iMinInput = document.getElementById('iMin');
  const iMaxInput = document.getElementById('iMax');
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
  const latestL2GasUsed = document.getElementById('latestL2GasUsed');
  const latestDeficitEth = document.getElementById('latestDeficitEth');
  const latestEpsilon = document.getElementById('latestEpsilon');
  const latestIntegral = document.getElementById('latestIntegral');
  const latestFfTerm = document.getElementById('latestFfTerm');
  const latestFbTerm = document.getElementById('latestFbTerm');
  const latestClampState = document.getElementById('latestClampState');
  const latestVaultValue = document.getElementById('latestVaultValue');
  const latestVaultGap = document.getElementById('latestVaultGap');

  const l2GasWrap = document.getElementById('l2GasPlot');
  const baseWrap = document.getElementById('basePlot');
  const blobWrap = document.getElementById('blobPlot');
  const costWrap = document.getElementById('costPlot');
  const reqWrap = document.getElementById('requiredFeePlot');
  const controllerWrap = document.getElementById('controllerPlot');
  const feedbackWrap = document.getElementById('feedbackPlot');
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

  function getCurrentXRange() {{
    for (const p of allPlots()) {{
      if (!p || !p.scales || !p.scales.x) continue;
      const min = p.scales.x.min;
      const max = p.scales.x.max;
      if (Number.isFinite(min) && Number.isFinite(max)) return [min, max];
    }}
    return null;
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

  function parseNonNegativeInt(inputEl, fallback) {{
    const v = Number(inputEl.value);
    if (!Number.isFinite(v) || v < 0) return fallback;
    return Math.floor(v);
  }}

  function parseNumber(inputEl, fallback) {{
    const v = Number(inputEl.value);
    return Number.isFinite(v) ? v : fallback;
  }}

  function applyControllerModePreset(mode) {{
    if (mode === 'alpha-only') {{
      kpInput.value = '0';
      kiInput.value = '0';
      const alphaGasNow = parsePositive(alphaGasInput, 0);
      const alphaBlobNow = parsePositive(alphaBlobInput, 0);
      if (!autoAlphaInput.checked && alphaGasNow === 0 && alphaBlobNow === 0) {{
        alphaGasInput.value = DEFAULT_ALPHA_GAS.toFixed(6);
        alphaBlobInput.value = DEFAULT_ALPHA_BLOB.toFixed(6);
      }}
      return;
    }}

    if (mode === 'p') {{
      // P-only preset: disable feedforward and integral contribution.
      autoAlphaInput.checked = false;
      alphaGasInput.value = '0';
      alphaBlobInput.value = '0';
      kiInput.value = '0';
      return;
    }}

    if (mode === 'pi') {{
      // PI-only preset: disable feedforward contribution.
      autoAlphaInput.checked = false;
      alphaGasInput.value = '0';
      alphaBlobInput.value = '0';
      return;
    }}

    if (mode === 'pi+ff') {{
      // PI + feedforward: keep both paths enabled.
      if (!autoAlphaInput.checked) {{
        const alphaGasNow = parsePositive(alphaGasInput, 0);
        const alphaBlobNow = parsePositive(alphaBlobInput, 0);
        if (alphaGasNow === 0 && alphaBlobNow === 0) {{
          alphaGasInput.value = DEFAULT_ALPHA_GAS.toFixed(6);
          alphaBlobInput.value = DEFAULT_ALPHA_BLOB.toFixed(6);
        }}
      }}
    }}
  }}

  function clampNum(x, lo, hi) {{
    return Math.max(lo, Math.min(hi, x));
  }}

  function makeRng(seed) {{
    let s = seed >>> 0;
    return function () {{
      s = (1664525 * s + 1013904223) >>> 0;
      return s / 4294967296;
    }};
  }}

  function gaussian(rng) {{
    const u1 = Math.max(1e-12, rng());
    const u2 = rng();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }}

  function buildL2GasSeries(n, baseGasPerL1Block, scenario) {{
    const out = new Array(n);
    if (scenario === 'constant') {{
      for (let i = 0; i < n; i++) out[i] = baseGasPerL1Block;
      return out;
    }}

    const cfg = scenario === 'steady'
      ? {{ rho: 0.97, sigma: 0.03, jumpProb: 0.0, jumpSigma: 0.0, lo: 0.75, hi: 1.35 }}
      : scenario === 'bursty'
        ? {{ rho: 0.90, sigma: 0.16, jumpProb: 0.035, jumpSigma: 0.45, lo: 0.25, hi: 3.5 }}
        : {{ rho: 0.94, sigma: 0.08, jumpProb: 0.01, jumpSigma: 0.20, lo: 0.45, hi: 2.0 }}; // normal

    const rng = makeRng(0x1234abcd);
    let x = 0;
    for (let i = 0; i < n; i++) {{
      x = cfg.rho * x + cfg.sigma * gaussian(rng);
      if (cfg.jumpProb > 0 && rng() < cfg.jumpProb) x += cfg.jumpSigma * gaussian(rng);
      const m = clampNum(Math.exp(x), cfg.lo, cfg.hi);
      out[i] = baseGasPerL1Block * m;
    }}

    // Mean-neutralize scenario throughput so randomness adds volatility, not systematic bias.
    let sum = 0;
    for (let i = 0; i < n; i++) sum += out[i];
    const avg = n > 0 ? (sum / n) : baseGasPerL1Block;
    if (avg > 0) {{
      const scale = baseGasPerL1Block / avg;
      for (let i = 0; i < n; i++) out[i] *= scale;
    }}

    return out;
  }}

  let derivedL2GasPerL1Block = [];
  let derivedL2GasPerL1BlockBase = [];
  let derivedL2GasPerL2Block = [];
  let derivedL2GasPerL2BlockBase = [];
  let derivedGasCostEth = [];
  let derivedBlobCostEth = [];
  let derivedPostingCostEth = [];
  let derivedRequiredFeeGwei = [];
  let derivedGasFeeComponentGwei = [];
  let derivedBlobFeeComponentGwei = [];
  let derivedFeedforwardFeeGwei = [];
  let derivedPTermFeeGwei = [];
  let derivedITermFeeGwei = [];
  let derivedFeedbackFeeGwei = [];
  let derivedChargedFeeGwei = [];
  let derivedDeficitEth = [];
  let derivedEpsilon = [];
  let derivedIntegral = [];
  let derivedClampState = [];
  let derivedVaultEth = [];
  let derivedVaultTargetEth = [];

  function recalcDerivedSeries() {{
    const postEveryBlocks = parsePositiveInt(postEveryBlocksInput, 10);
    const l2GasPerL2Block = parsePositive(l2GasPerL2BlockInput, 0);
    const l2BlockTimeSec = parsePositive(l2BlockTimeSecInput, 12);
    const l2GasScenario = l2GasScenarioInput.value || 'constant';
    const l2DemandRegime = l2DemandRegimeInput.value || 'base';
    const demandMultiplier = DEMAND_MULTIPLIERS[l2DemandRegime] || 1.0;
    const l2BlocksPerL1Block = l2BlockTimeSec > 0 ? (L1_BLOCK_TIME_SECONDS / l2BlockTimeSec) : 0;
    const l2GasPerL1BlockBase = l2GasPerL2Block * l2BlocksPerL1Block;
    const l2GasPerL1BlockTarget = l2GasPerL1BlockBase * demandMultiplier;
    const l1GasUsed = parsePositive(l1GasUsedInput, 0);
    const numBlobs = parsePositive(numBlobsInput, 0);
    const priorityFeeGwei = parsePositive(priorityFeeGweiInput, 0);
    const controllerMode = controllerModeInput.value || 'alpha-only';
    const dffBlocks = parseNonNegativeInt(dffBlocksInput, 0);
    const dfbBlocks = parseNonNegativeInt(dfbBlocksInput, 12);
    const kp = parsePositive(kpInput, 0);
    const ki = parsePositive(kiInput, 0);
    const iMinRaw = parseNumber(iMinInput, -5);
    const iMaxRaw = parseNumber(iMaxInput, 5);
    const iMin = Math.min(iMinRaw, iMaxRaw);
    const iMax = Math.max(iMinRaw, iMaxRaw);
    const minFeeGwei = parsePositive(minFeeGweiInput, 0);
    const maxFeeGwei = parsePositive(maxFeeGweiInput, 1);
    const initialVaultEth = parsePositive(initialVaultEthInput, 0);
    const targetVaultEth = parsePositive(targetVaultEthInput, 0);

    const l2GasPerProposalBase = l2GasPerL1BlockBase * postEveryBlocks;
    const autoAlphaEnabled = autoAlphaInput.checked;
    const autoAlphaGas = l2GasPerProposalBase > 0 ? (l1GasUsed / l2GasPerProposalBase) : 0;
    const autoAlphaBlob =
      l2GasPerProposalBase > 0 ? ((numBlobs * BLOB_GAS_PER_BLOB) / l2GasPerProposalBase) : 0;
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
    const feeRangeWei = maxFeeWei - minFeeWei;

    derivedL2GasPerL1BlockText.textContent =
      `${{formatNum(l2GasPerL1BlockBase, 0)}} gas/L1 block (base), ` +
      `${{formatNum(l2GasPerL1BlockTarget, 0)}} gas/L1 block (target)`;
    derivedL2GasPerProposalText.textContent = `${{formatNum(l2GasPerProposalBase, 0)}} gas/proposal (base)`;

    const n = blocks.length;
    derivedL2GasPerL1Block = buildL2GasSeries(n, l2GasPerL1BlockTarget, l2GasScenario);
    derivedL2GasPerL1BlockBase = new Array(n).fill(l2GasPerL1BlockTarget);
    if (l2BlocksPerL1Block > 0) {{
      derivedL2GasPerL2Block = derivedL2GasPerL1Block.map(function (x) {{
        return x / l2BlocksPerL1Block;
      }});
      derivedL2GasPerL2BlockBase = derivedL2GasPerL1BlockBase.map(function (x) {{
        return x / l2BlocksPerL1Block;
      }});
    }} else {{
      derivedL2GasPerL2Block = new Array(n).fill(0);
      derivedL2GasPerL2BlockBase = new Array(n).fill(0);
    }}
    derivedGasCostEth = new Array(n);
    derivedBlobCostEth = new Array(n);
    derivedPostingCostEth = new Array(n);
    derivedRequiredFeeGwei = new Array(n);
    derivedGasFeeComponentGwei = new Array(n);
    derivedBlobFeeComponentGwei = new Array(n);
    derivedFeedforwardFeeGwei = new Array(n);
    derivedPTermFeeGwei = new Array(n);
    derivedITermFeeGwei = new Array(n);
    derivedFeedbackFeeGwei = new Array(n);
    derivedChargedFeeGwei = new Array(n);
    derivedDeficitEth = new Array(n);
    derivedEpsilon = new Array(n);
    derivedIntegral = new Array(n);
    derivedClampState = new Array(n);
    derivedVaultEth = new Array(n);
    derivedVaultTargetEth = new Array(n);

    let vault = initialVaultEth;
    let pendingRevenueEth = 0;
    let integralState = 0;

    for (let i = 0; i < n; i++) {{
      const baseFeeWei = baseFeeGwei[i] * 1e9;
      const blobBaseFeeWei = blobFeeGwei[i] * 1e9;
      const ffIndex = Math.max(0, i - dffBlocks);
      const baseFeeFfWei = baseFeeGwei[ffIndex] * 1e9;
      const blobBaseFeeFfWei = blobFeeGwei[ffIndex] * 1e9;

      const gasCostWei = l1GasUsed * (baseFeeWei + priorityFeeWei);
      const blobCostWei = numBlobs * BLOB_GAS_PER_BLOB * blobBaseFeeWei;
      const totalCostWei = gasCostWei + blobCostWei;
      const l2GasPerL1Block_i = derivedL2GasPerL1Block[i];
      const l2GasPerProposal_i = l2GasPerL1Block_i * postEveryBlocks;

      derivedGasCostEth[i] = gasCostWei / 1e18;
      derivedBlobCostEth[i] = blobCostWei / 1e18;
      derivedPostingCostEth[i] = totalCostWei / 1e18;
      const gasComponentWei = alphaGas * (baseFeeFfWei + priorityFeeWei);
      const blobComponentWei = alphaBlob * blobBaseFeeFfWei;

      const fbIndex = i - dfbBlocks;
      const observedVault = fbIndex >= 0 ? derivedVaultEth[fbIndex] : initialVaultEth;
      const deficitEth = targetVaultEth - observedVault;
      const epsilon = targetVaultEth > 0 ? (deficitEth / targetVaultEth) : 0;

      if (controllerMode === 'pi' || controllerMode === 'pi+ff') {{
        integralState = clampNum(integralState + epsilon, iMin, iMax);
      }} else {{
        integralState = 0;
      }}

      const pTermWei = (controllerMode === 'alpha-only') ? 0 : (kp * epsilon * feeRangeWei);
      const iTermWei =
        (controllerMode === 'pi' || controllerMode === 'pi+ff')
          ? (ki * integralState * feeRangeWei)
          : 0;
      const feedbackWei = pTermWei + iTermWei;
      const feedforwardWei = gasComponentWei + blobComponentWei;
      const chargedFeeWeiPerL2Gas = Math.max(
        minFeeWei,
        Math.min(maxFeeWei, feedforwardWei + feedbackWei)
      );

      let clampState = 'none';
      if (chargedFeeWeiPerL2Gas <= minFeeWei + 1e-9) clampState = 'min';
      else if (chargedFeeWeiPerL2Gas >= maxFeeWei - 1e-9) clampState = 'max';

      derivedGasFeeComponentGwei[i] = gasComponentWei / 1e9;
      derivedBlobFeeComponentGwei[i] = blobComponentWei / 1e9;
      derivedFeedforwardFeeGwei[i] = feedforwardWei / 1e9;
      derivedPTermFeeGwei[i] = pTermWei / 1e9;
      derivedITermFeeGwei[i] = iTermWei / 1e9;
      derivedFeedbackFeeGwei[i] = feedbackWei / 1e9;
      derivedChargedFeeGwei[i] = chargedFeeWeiPerL2Gas / 1e9;
      derivedDeficitEth[i] = deficitEth;
      derivedEpsilon[i] = epsilon;
      derivedIntegral[i] = integralState;
      derivedClampState[i] = clampState;

      if (l2GasPerProposal_i > 0) {{
        const breakEvenFeeWeiPerL2Gas = totalCostWei / l2GasPerProposal_i;
        derivedRequiredFeeGwei[i] = breakEvenFeeWeiPerL2Gas / 1e9;
      }} else {{
        derivedRequiredFeeGwei[i] = null;
      }}

      const l2RevenueEthPerBlock =
        (chargedFeeWeiPerL2Gas * l2GasPerL1Block_i) / 1e18;
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

    const preservedRange = getCurrentXRange();

    if (l2GasPlot && costPlot && requiredFeePlot && controllerPlot && feedbackPlot && vaultPlot) {{
      l2GasPlot.setData([blocks, derivedL2GasPerL2Block, derivedL2GasPerL2BlockBase]);
      costPlot.setData([blocks, derivedGasCostEth, derivedBlobCostEth, derivedPostingCostEth]);
      requiredFeePlot.setData([
        blocks,
        derivedGasFeeComponentGwei,
        derivedBlobFeeComponentGwei,
        derivedChargedFeeGwei
      ]);
      controllerPlot.setData([
        blocks,
        derivedFeedforwardFeeGwei,
        derivedPTermFeeGwei,
        derivedITermFeeGwei,
        derivedFeedbackFeeGwei,
        derivedChargedFeeGwei
      ]);
      feedbackPlot.setData([
        blocks,
        derivedDeficitEth,
        derivedEpsilon,
        derivedIntegral
      ]);
      vaultPlot.setData([blocks, derivedVaultTargetEth, derivedVaultEth]);

      if (preservedRange) {{
        applyRange(preservedRange[0], preservedRange[1], null);
      }}
    }}

    const lastIdx = n - 1;
    latestPostingCost.textContent = `${{formatNum(derivedPostingCostEth[lastIdx], 6)}} ETH`;
    if (derivedRequiredFeeGwei[lastIdx] == null || derivedChargedFeeGwei[lastIdx] == null) {{
      latestRequiredFee.textContent = 'n/a';
      latestChargedFee.textContent = 'n/a';
      latestGasComponentFee.textContent = 'n/a';
      latestBlobComponentFee.textContent = 'n/a';
      latestL2GasUsed.textContent = 'n/a';
    }} else {{
      latestRequiredFee.textContent = `${{formatNum(derivedRequiredFeeGwei[lastIdx], 4)}} gwei/L2gas`;
      latestChargedFee.textContent = `${{formatNum(derivedChargedFeeGwei[lastIdx], 4)}} gwei/L2gas`;
      latestGasComponentFee.textContent = `${{formatNum(derivedGasFeeComponentGwei[lastIdx], 4)}} gwei/L2gas`;
      latestBlobComponentFee.textContent = `${{formatNum(derivedBlobFeeComponentGwei[lastIdx], 4)}} gwei/L2gas`;
      latestL2GasUsed.textContent = `${{formatNum(derivedL2GasPerL2Block[lastIdx], 0)}} gas/L2 block`;
    }}
    latestDeficitEth.textContent = `${{formatNum(derivedDeficitEth[lastIdx], 6)}} ETH`;
    latestEpsilon.textContent = `${{formatNum(derivedEpsilon[lastIdx], 6)}}`;
    latestIntegral.textContent = `${{formatNum(derivedIntegral[lastIdx], 6)}}`;
    latestFfTerm.textContent = `${{formatNum(derivedFeedforwardFeeGwei[lastIdx], 4)}} gwei/L2gas`;
    latestFbTerm.textContent = `${{formatNum(derivedFeedbackFeeGwei[lastIdx], 4)}} gwei/L2gas`;
    latestClampState.textContent = derivedClampState[lastIdx];
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
  let l2GasPlot;
  let costPlot;
  let requiredFeePlot;
  let controllerPlot;
  let feedbackPlot;
  let vaultPlot;

  function allPlots() {{
    return [
      basePlot,
      blobPlot,
      l2GasPlot,
      costPlot,
      requiredFeePlot,
      controllerPlot,
      feedbackPlot,
      vaultPlot
    ].filter(Boolean);
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
      title: 'L2 Fee Components (feedforward + clamped total)',
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

  function makeControllerOpts(width, height) {{
    return {{
      title: 'Controller Components (Feedforward + PI)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'FF term (gwei/L2 gas)', stroke: '#334155', width: 1.2 }},
        {{ label: 'P term (gwei/L2 gas)', stroke: '#2563eb', width: 1.0 }},
        {{ label: 'I term (gwei/L2 gas)', stroke: '#f59e0b', width: 1.0 }},
        {{ label: 'FB total (gwei/L2 gas)', stroke: '#7c3aed', width: 1.0 }},
        {{ label: 'Charged fee (gwei/L2 gas)', stroke: '#16a34a', width: 1.4 }}
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

  function makeFeedbackOpts(width, height) {{
    return {{
      title: 'Feedback State (D, epsilon, I)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'Deficit D (ETH)', stroke: '#dc2626', width: 1.2 }},
        {{ label: 'Normalized deficit epsilon', stroke: '#0891b2', width: 1.0 }},
        {{ label: 'Integral I', stroke: '#7c2d12', width: 1.0 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'Mixed units' }}
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

  l2GasPlot = new uPlot(
    {{
      title: 'L2 Gas Used (Scenario)',
      width,
      height: 320,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{}},
        {{ label: 'L2 gas / L2 block (scenario)', stroke: '#0f766e', width: 1.4 }},
        {{ label: 'L2 gas / L2 block (target)', stroke: '#94a3b8', width: 1.0 }}
      ],
      axes: [
        {{ label: 'L1 Block Number' }},
        {{ label: 'gas / L2 block' }}
      ],
      cursor: {{
        drag: {{ x: true, y: false, setScale: true }}
      }},
      hooks: {{
        setScale: [onSetScale]
      }}
    }},
    [blocks, [], []],
    l2GasWrap
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

  controllerPlot = new uPlot(
    makeControllerOpts(width, 320),
    [blocks, [], [], [], [], []],
    controllerWrap
  );

  feedbackPlot = new uPlot(
    makeFeedbackOpts(width, 320),
    [blocks, [], [], []],
    feedbackWrap
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

  controllerModeInput.addEventListener('change', function () {{
    applyControllerModePreset(controllerModeInput.value || 'alpha-only');
    recalcDerivedSeries();
  }});

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
    l2GasScenarioInput,
    l2DemandRegimeInput,
    l1GasUsedInput,
    numBlobsInput,
    priorityFeeGweiInput,
    autoAlphaInput,
    alphaGasInput,
    alphaBlobInput,
    dffBlocksInput,
    dfbBlocksInput,
    kpInput,
    kiInput,
    iMinInput,
    iMaxInput,
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


def build_html(title, js_filename, current_html_name=None, range_options=None):
    range_options = range_options or []
    current_html_name = current_html_name or ""
    range_selector_html = ""
    if range_options:
        opts = []
        for value, label in range_options:
            selected = " selected" if value == current_html_name else ""
            opts.append(f'<option value="{value}"{selected}>{label}</option>')
        options_html = "\n".join(opts)
        range_selector_html = f"""
        <div class=\"controls\">
          <label>Data range
            <select id=\"datasetRange\">
              {options_html}
            </select>
          </label>
        </div>
"""

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
    .wrap {{ max-width: 1800px; margin: 20px auto; padding: 0 16px 24px; }}
    .layout {{
      display: grid;
      grid-template-columns: 440px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    }}
    .sidebar {{
      position: sticky;
      top: 12px;
      max-height: calc(100vh - 24px);
      overflow: auto;
    }}
    .content {{
      min-width: 0;
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
    input[type=number], select {{ width: 150px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; }}
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
    <h1>{title}</h1>
    <p class=\"sub\">Drag horizontally inside any chart to zoom. Block range controls and zoom are synchronized across all charts.</p>

    <div class=\"layout\">
      <aside class=\"panel sidebar\">
        {range_selector_html}
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
            <label>L2 gas scenario
              <select id=\"l2GasScenario\">
                <option value=\"constant\">constant</option>
                <option value=\"steady\">steady</option>
                <option value=\"normal\" selected>normal</option>
                <option value=\"bursty\">bursty</option>
              </select>
            </label>
            <label>Demand regime
              <select id=\"l2DemandRegime\">
                <option value=\"low\">low</option>
                <option value=\"base\" selected>base</option>
                <option value=\"high\">high</option>
              </select>
            </label>
            <label>L1 gas used <input id=\"l1GasUsed\" type=\"number\" min=\"0\" step=\"1000\" value=\"{DEFAULT_L1_GAS_USED}\" /></label>
            <label>Blobs <input id=\"numBlobs\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_NUM_BLOBS}\" /></label>
            <label>Priority fee (gwei) <input id=\"priorityFeeGwei\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_PRIORITY_FEE_GWEI:g}\" /></label>
            <label>Controller mode
              <select id=\"controllerMode\">
                <option value=\"alpha-only\"{" selected" if DEFAULT_CONTROLLER_MODE == "alpha-only" else ""}>alpha-only</option>
                <option value=\"p\"{" selected" if DEFAULT_CONTROLLER_MODE == "p" else ""}>p</option>
                <option value=\"pi\"{" selected" if DEFAULT_CONTROLLER_MODE == "pi" else ""}>pi</option>
                <option value=\"pi+ff\"{" selected" if DEFAULT_CONTROLLER_MODE == "pi+ff" else ""}>pi+ff</option>
              </select>
            </label>
            <label><input id=\"autoAlpha\" type=\"checkbox\" checked /> Auto alpha</label>
            <label>Alpha gas <input id=\"alphaGas\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_GAS:.6f}\" /></label>
            <label>Alpha blob <input id=\"alphaBlob\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_BLOB:.6f}\" /></label>
            <label>Kp <input id=\"kp\" type=\"number\" min=\"0\" step=\"0.001\" value=\"{DEFAULT_KP:g}\" /></label>
            <label>Ki <input id=\"ki\" type=\"number\" min=\"0\" step=\"0.001\" value=\"{DEFAULT_KI:g}\" /></label>
            <label>I min <input id=\"iMin\" type=\"number\" step=\"0.1\" value=\"{DEFAULT_I_MIN:g}\" /></label>
            <label>I max <input id=\"iMax\" type=\"number\" step=\"0.1\" value=\"{DEFAULT_I_MAX:g}\" /></label>
            <label>Feedforward delay d_ff (L1 blocks) <input id=\"dffBlocks\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_D_FF_BLOCKS}\" /></label>
            <label>Feedback delay d_fb (L1 blocks) <input id=\"dfbBlocks\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_D_FB_BLOCKS}\" /></label>
            <label>Min fee (gwei/L2 gas) <input id=\"minFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MIN_FEE_GWEI:g}\" /></label>
            <label>Max fee (gwei/L2 gas) <input id=\"maxFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MAX_FEE_GWEI:.1f}\" /></label>
            <label>Initial vault (ETH) <input id=\"initialVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_INITIAL_VAULT_ETH:g}\" /></label>
            <label>Target vault (ETH) <input id=\"targetVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_TARGET_VAULT_ETH:g}\" /></label>
            <button class=\"primary\" id=\"recalcBtn\">Recompute derived charts</button>
          </div>
          <div class=\"formula\">cost_wei(t_post) = l1GasUsed * (baseFee_t_post + priorityFee) + numBlobs * 131072 * blobBaseFee_t_post</div>
          <div class=\"formula\">FF_t = alpha_gas * (baseFee_(t-d_ff) + priorityFee) + alpha_blob * blobBaseFee_(t-d_ff)</div>
          <div class=\"formula\">D_t = targetVault - vault_(t-d_fb), epsilon_t = D_t / targetVault, I_t = clamp(I_(t-1) + epsilon_t, Imin, Imax)</div>
          <div class=\"formula\">fee_t = clamp(FF_t + Kp*epsilon_t*(maxFee-minFee) + Ki*I_t*(maxFee-minFee), minFee, maxFee)</div>
          <div class=\"formula\">auto alpha uses BASE throughput: alpha_gas = l1GasUsed / l2GasPerProposal_base, alpha_blob = (numBlobs * 131072) / l2GasPerProposal_base</div>
          <div class=\"formula\">Assume L1 block time = 12s; derived <strong id=\"derivedL2GasPerL1Block\">-</strong> and <strong id=\"derivedL2GasPerProposal\">-</strong></div>
          <div class=\"formula\">Demand multipliers: low=0.7x, base=1.0x, high=1.4x (applied to L2 throughput target)</div>
          <div class=\"formula\">L2 gas scenarios are mean-neutralized around the demand-adjusted throughput target</div>
          <div class=\"formula\">posting events at (i + 1) % postEveryBlocks == 0; revenue is settled to vault at post time</div>
          <div class=\"metrics\">
            <span>Latest hypothetical posting cost: <strong id=\"latestPostingCost\">-</strong></span>
            <span>Latest required L2 fee (cost-side reference): <strong id=\"latestRequiredFee\">-</strong></span>
            <span>Latest charged L2 fee: <strong id=\"latestChargedFee\">-</strong></span>
            <span>Latest gas component fee: <strong id=\"latestGasComponentFee\">-</strong></span>
            <span>Latest blob component fee: <strong id=\"latestBlobComponentFee\">-</strong></span>
            <span>Latest deficit D: <strong id=\"latestDeficitEth\">-</strong></span>
            <span>Latest epsilon: <strong id=\"latestEpsilon\">-</strong></span>
            <span>Latest integral I: <strong id=\"latestIntegral\">-</strong></span>
            <span>Latest FF term: <strong id=\"latestFfTerm\">-</strong></span>
            <span>Latest FB term: <strong id=\"latestFbTerm\">-</strong></span>
            <span>Latest clamp state: <strong id=\"latestClampState\">-</strong></span>
            <span>Latest L2 gas used: <strong id=\"latestL2GasUsed\">-</strong></span>
            <span>Latest vault value: <strong id=\"latestVaultValue\">-</strong></span>
            <span>Vault - target: <strong id=\"latestVaultGap\">-</strong></span>
          </div>
        </div>

        <div class=\"status\" id=\"status\"></div>
      </aside>

      <main class=\"content\">
        <div id=\"basePlot\" class=\"plot\"></div>
        <div id=\"blobPlot\" class=\"plot\"></div>
        <div id=\"l2GasPlot\" class=\"plot\"></div>
        <div id=\"costPlot\" class=\"plot\"></div>
        <div id=\"requiredFeePlot\" class=\"plot\"></div>
        <div id=\"controllerPlot\" class=\"plot\"></div>
        <div id=\"feedbackPlot\" class=\"plot\"></div>
        <div id=\"vaultPlot\" class=\"plot\"></div>
      </main>
    </div>
  </div>

  <script>
    (function () {{
      var rangeSel = document.getElementById('datasetRange');
      if (!rangeSel) return;
      rangeSel.addEventListener('change', function () {{
        var target = rangeSel.value;
        if (target) window.location.href = target;
      }});
    }})();
  </script>
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
    parser.add_argument(
        "--range-option",
        action="append",
        default=[],
        help="Optional range switcher option in the form '<html_filename>|<label>'",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    out_html = Path(args.out_html).resolve()
    out_js = Path(args.out_js).resolve()

    blocks, base, blob = read_fee_csv(csv_path)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_js.parent.mkdir(parents=True, exist_ok=True)

    out_js.write_text(build_app_js(blocks, base, blob))
    range_options = []
    for opt in args.range_option:
        if "|" in opt:
            value, label = opt.split("|", 1)
            value = value.strip()
            label = label.strip()
            if value and label:
                range_options.append((value, label))

    out_html.write_text(build_html(args.title, out_js.name, out_html.name, range_options))

    print(out_html)
    print(out_js)


if __name__ == "__main__":
    main()
