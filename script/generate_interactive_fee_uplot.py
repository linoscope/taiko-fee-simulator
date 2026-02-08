#!/usr/bin/env python3

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

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
DEFAULT_D_FF_BLOCKS = 5
DEFAULT_D_FB_BLOCKS = 5
DEFAULT_KP = 0.1
DEFAULT_KI = 0.0
DEFAULT_KD = 0.0
DEFAULT_DERIV_BETA = 0.8
DEFAULT_I_MIN = -5.0
DEFAULT_I_MAX = 5.0
DEFAULT_DEFICIT_DEADBAND_PCT = 5.0

DEFAULT_HEALTH_WEIGHT = 0.75
DEFAULT_UX_WEIGHT = 0.25

DEFAULT_HEALTH_W_DRAW = 0.35
DEFAULT_HEALTH_W_UNDER = 0.25
DEFAULT_HEALTH_W_AREA = 0.20
DEFAULT_HEALTH_W_GAP = 0.10
DEFAULT_HEALTH_W_STREAK = 0.10

DEFAULT_UX_W_STD = 0.30
DEFAULT_UX_W_P95 = 0.30
DEFAULT_UX_W_P99 = 0.20
DEFAULT_UX_W_MAXSTEP = 0.10
DEFAULT_UX_W_CLAMP = 0.10
DEFAULT_SWEEP_KP_VALUES = [0.0, 0.02, 0.05, 0.10, 0.20, 0.40]
DEFAULT_SWEEP_KI_VALUES = [0.0, 0.001, 0.002, 0.005, 0.010]
DEFAULT_SWEEP_KD_VALUES = [0.0, 0.010, 0.020, 0.050, 0.100]
DEFAULT_SWEEP_MAX_BLOCKS = 120_000

DEFAULT_L2_GAS_PER_L1_BLOCK = (
    DEFAULT_L2_GAS_PER_L2_BLOCK * (L1_BLOCK_TIME_SECONDS / DEFAULT_L2_BLOCK_TIME_SECONDS)
)
DEFAULT_L2_GAS_PER_PROPOSAL = DEFAULT_L2_GAS_PER_L1_BLOCK * DEFAULT_POST_EVERY_BLOCKS
DEFAULT_ALPHA_GAS = DEFAULT_L1_GAS_USED / DEFAULT_L2_GAS_PER_PROPOSAL
DEFAULT_ALPHA_BLOB = (DEFAULT_NUM_BLOBS * BLOB_GAS_PER_BLOB) / DEFAULT_L2_GAS_PER_PROPOSAL
DEFAULT_TIMESTAMP_CACHE = (
    Path(__file__).resolve().parents[1] / "data" / "eth_block_timestamp_cache.json"
)


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


def rpc_block_timestamp(block_number: int, rpc_url: str, timeout_sec: int = 20):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBlockByNumber",
        "params": [hex(block_number), False],
    }
    try:
        resp = requests.post(rpc_url, json=payload, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result")
        if not result or "timestamp" not in result:
            return None
        return int(result["timestamp"], 16)
    except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError):
        return None


def load_timestamp_cache(cache_path: Path | None):
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text())
        if not isinstance(raw, dict):
            return {}
        out = {}
        for k, v in raw.items():
            try:
                out[str(k)] = int(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def save_timestamp_cache(cache_path: Path | None, cache: dict):
    if cache_path is None:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, separators=(",", ":"), sort_keys=True))


def get_block_timestamp_cached(block_number: int, rpc_url: str | None, cache: dict):
    key = str(block_number)
    if key in cache:
        try:
            return int(cache[key]), "cache"
        except Exception:
            pass

    if not rpc_url:
        return None, "none"

    ts = rpc_block_timestamp(block_number, rpc_url)
    if ts is not None:
        cache[key] = int(ts)
        return int(ts), "rpc"

    return None, "rpc_failed"


def read_time_anchor(
    csv_path: Path,
    min_block: int,
    max_block: int,
    rpc_url: str | None,
    ts_cache: dict,
):
    summary_path = csv_path.with_name(csv_path.stem + "_summary.json")
    default = {
        "has_anchor": False,
        "anchor_block": 0,
        "anchor_ts_sec": 0,
        "seconds_per_block": float(L1_BLOCK_TIME_SECONDS),
        "source": "default_12s",
    }

    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
        except Exception:
            summary = {}

    def get_int(keys):
        for k in keys:
            if k in summary:
                try:
                    return int(summary[k])
                except Exception:
                    pass
        return None

    def get_ts(keys):
        for k in keys:
            raw = summary.get(k)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                return int(dt.astimezone(timezone.utc).timestamp())
            except Exception:
                continue
        return None

    start_block = get_int(["window_start_block", "start_block"])
    end_block = get_int(["window_end_block", "end_block"])
    if start_block is None:
        start_block = min_block
    if end_block is None:
        end_block = max_block
    start_ts = get_ts(["window_start_timestamp_utc"])
    end_ts = get_ts(["window_end_timestamp_utc", "latest_block_timestamp_utc"])
    start_ts_source = "summary" if start_ts is not None else "missing"
    end_ts_source = "summary" if end_ts is not None else "missing"

    if start_ts is None and start_block is not None:
        start_ts, start_ts_source = get_block_timestamp_cached(start_block, rpc_url, ts_cache)
    if end_ts is None and end_block is not None:
        end_ts, end_ts_source = get_block_timestamp_cached(end_block, rpc_url, ts_cache)

    seconds_per_block = float(L1_BLOCK_TIME_SECONDS)
    if (
        start_block is not None
        and end_block is not None
        and start_ts is not None
        and end_ts is not None
        and end_block > start_block
        and end_ts > start_ts
    ):
        seconds_per_block = (end_ts - start_ts) / (end_block - start_block)

    if start_block is not None and start_ts is not None:
        anchor_source = (
            "summary_start_anchor" if start_ts_source == "summary"
            else "cache_start_anchor" if start_ts_source == "cache"
            else "rpc_start_anchor" if start_ts_source == "rpc"
            else "start_anchor"
        )
        return {
            "has_anchor": True,
            "anchor_block": int(start_block),
            "anchor_ts_sec": int(start_ts),
            "seconds_per_block": float(seconds_per_block),
            "source": anchor_source,
        }

    if end_block is not None and end_ts is not None:
        anchor_source = (
            "summary_end_anchor" if end_ts_source == "summary"
            else "cache_end_anchor" if end_ts_source == "cache"
            else "rpc_end_anchor" if end_ts_source == "rpc"
            else "end_anchor"
        )
        return {
            "has_anchor": True,
            "anchor_block": int(end_block),
            "anchor_ts_sec": int(end_ts),
            "seconds_per_block": float(seconds_per_block),
            "source": anchor_source,
        }

    return default


def build_app_js(blocks, base, blob, time_anchor):
    blocks_json = json.dumps(blocks, separators=(",", ":"))
    base_json = json.dumps(base, separators=(",", ":"))
    blob_json = json.dumps(blob, separators=(",", ":"))
    has_anchor = "true" if time_anchor["has_anchor"] else "false"

    return f"""(function () {{
  const blocks = {blocks_json};
  const baseFeeGwei = {base_json};
  const blobFeeGwei = {blob_json};

  const MIN_BLOCK = blocks[0];
  const MAX_BLOCK = blocks[blocks.length - 1];
  const BLOB_GAS_PER_BLOB = {BLOB_GAS_PER_BLOB};
  const L1_BLOCK_TIME_SECONDS = {L1_BLOCK_TIME_SECONDS};
  const HAS_BLOCK_TIME_ANCHOR = {has_anchor};
  const BLOCK_TIME_APPROX_SECONDS = {time_anchor["seconds_per_block"]:.6f};
  const ANCHOR_BLOCK = {int(time_anchor["anchor_block"])};
  const ANCHOR_TIMESTAMP_SEC = {int(time_anchor["anchor_ts_sec"])};
  const TIME_ANCHOR_SOURCE = {json.dumps(time_anchor["source"])};
  const DEFAULT_ALPHA_GAS = {DEFAULT_ALPHA_GAS:.12f};
  const DEFAULT_ALPHA_BLOB = {DEFAULT_ALPHA_BLOB:.12f};
  const DEMAND_MULTIPLIERS = Object.freeze({{ low: 0.7, base: 1.0, high: 1.4 }});
  const SWEEP_MODES = Object.freeze(['pdi', 'pdi+ff']);
  const SWEEP_KP_VALUES = Object.freeze({json.dumps(DEFAULT_SWEEP_KP_VALUES)});
  const SWEEP_KI_VALUES = Object.freeze({json.dumps(DEFAULT_SWEEP_KI_VALUES)});
  const SWEEP_KD_VALUES = Object.freeze({json.dumps(DEFAULT_SWEEP_KD_VALUES)});
  const SWEEP_MAX_BLOCKS = {DEFAULT_SWEEP_MAX_BLOCKS};

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const rangeDateText = document.getElementById('rangeDateText');
  const hoverText = document.getElementById('hoverText');
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
  const dSmoothBetaInput = document.getElementById('dSmoothBeta');
  const kpInput = document.getElementById('kp');
  const kiInput = document.getElementById('ki');
  const kdInput = document.getElementById('kd');
  const iMinInput = document.getElementById('iMin');
  const iMaxInput = document.getElementById('iMax');
  const minFeeGweiInput = document.getElementById('minFeeGwei');
  const maxFeeGweiInput = document.getElementById('maxFeeGwei');
  const initialVaultEthInput = document.getElementById('initialVaultEth');
  const targetVaultEthInput = document.getElementById('targetVaultEth');
  const deficitDeadbandPctInput = document.getElementById('deficitDeadbandPct');
  const scoreWeightHealthInput = document.getElementById('scoreWeightHealth');
  const scoreWeightUxInput = document.getElementById('scoreWeightUx');
  const healthWDrawInput = document.getElementById('healthWDraw');
  const healthWUnderInput = document.getElementById('healthWUnder');
  const healthWAreaInput = document.getElementById('healthWArea');
  const healthWGapInput = document.getElementById('healthWGap');
  const healthWStreakInput = document.getElementById('healthWStreak');
  const uxWStdInput = document.getElementById('uxWStd');
  const uxWP95Input = document.getElementById('uxWP95');
  const uxWP99Input = document.getElementById('uxWP99');
  const uxWMaxStepInput = document.getElementById('uxWMaxStep');
  const uxWClampInput = document.getElementById('uxWClamp');

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
  const latestDerivative = document.getElementById('latestDerivative');
  const latestIntegral = document.getElementById('latestIntegral');
  const latestFfTerm = document.getElementById('latestFfTerm');
  const latestDTerm = document.getElementById('latestDTerm');
  const latestFbTerm = document.getElementById('latestFbTerm');
  const latestClampState = document.getElementById('latestClampState');
  const latestVaultValue = document.getElementById('latestVaultValue');
  const latestVaultGap = document.getElementById('latestVaultGap');
  const scoreHealthBadness = document.getElementById('scoreHealthBadness');
  const scoreUxBadness = document.getElementById('scoreUxBadness');
  const scoreTotalBadness = document.getElementById('scoreTotalBadness');
  const scoreWeightSummary = document.getElementById('scoreWeightSummary');
  const healthMaxDrawdown = document.getElementById('healthMaxDrawdown');
  const healthUnderTargetRatio = document.getElementById('healthUnderTargetRatio');
  const healthAbsFinalGap = document.getElementById('healthAbsFinalGap');
  const healthDeficitAreaBand = document.getElementById('healthDeficitAreaBand');
  const healthWorstDeficitStreak = document.getElementById('healthWorstDeficitStreak');
  const uxFeeStd = document.getElementById('uxFeeStd');
  const uxFeeStepP95 = document.getElementById('uxFeeStepP95');
  const uxFeeStepP99 = document.getElementById('uxFeeStepP99');
  const uxFeeStepMax = document.getElementById('uxFeeStepMax');
  const uxClampMaxRatio = document.getElementById('uxClampMaxRatio');
  const healthFormulaLine = document.getElementById('healthFormulaLine');
  const uxFormulaLine = document.getElementById('uxFormulaLine');
  const totalFormulaLine = document.getElementById('totalFormulaLine');
  const scoreBtn = document.getElementById('scoreBtn');
  const scoreStatus = document.getElementById('scoreStatus');
  const sweepBtn = document.getElementById('sweepBtn');
  const sweepCancelBtn = document.getElementById('sweepCancelBtn');
  const sweepApplyBestBtn = document.getElementById('sweepApplyBestBtn');
  const sweepStatus = document.getElementById('sweepStatus');
  const sweepSpinner = document.getElementById('sweepSpinner');
  const sweepBestMode = document.getElementById('sweepBestMode');
  const sweepBestKp = document.getElementById('sweepBestKp');
  const sweepBestKi = document.getElementById('sweepBestKi');
  const sweepBestKd = document.getElementById('sweepBestKd');
  const sweepBestHealth = document.getElementById('sweepBestHealth');
  const sweepBestUx = document.getElementById('sweepBestUx');
  const sweepBestTotal = document.getElementById('sweepBestTotal');
  const sweepCandidateCount = document.getElementById('sweepCandidateCount');
  const sweepRangeCount = document.getElementById('sweepRangeCount');
  const sweepHover = document.getElementById('sweepHover');

  const l2GasWrap = document.getElementById('l2GasPlot');
  const baseWrap = document.getElementById('basePlot');
  const blobWrap = document.getElementById('blobPlot');
  const costWrap = document.getElementById('costPlot');
  const reqWrap = document.getElementById('requiredFeePlot');
  const controllerWrap = document.getElementById('controllerPlot');
  const feedbackWrap = document.getElementById('feedbackPlot');
  const vaultWrap = document.getElementById('vaultPlot');
  const sweepWrap = document.getElementById('sweepPlot');

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

  function blockToApproxUnixMs(blockNum) {{
    if (!HAS_BLOCK_TIME_ANCHOR) return null;
    return (ANCHOR_TIMESTAMP_SEC + (blockNum - ANCHOR_BLOCK) * BLOCK_TIME_APPROX_SECONDS) * 1000;
  }}

  function fmtApproxUtc(ms) {{
    if (!Number.isFinite(ms)) return 'n/a';
    const iso = new Date(ms).toISOString();
    return `${{iso.slice(0, 16).replace('T', ' ')}} UTC`;
  }}

  function fmtApproxSpan(msA, msB) {{
    if (!Number.isFinite(msA) || !Number.isFinite(msB)) return 'n/a';
    const sec = Math.max(0, Math.round((msB - msA) / 1000));
    const days = Math.floor(sec / 86400);
    const hours = Math.floor((sec % 86400) / 3600);
    return `${{days}}d ${{hours}}h`;
  }}

  function formatBlockWithApprox(blockNum) {{
    if (!Number.isFinite(blockNum)) return '';
    const ms = blockToApproxUnixMs(blockNum);
    if (!Number.isFinite(ms)) return Number(blockNum).toLocaleString();
    return `${{Number(blockNum).toLocaleString()}} (~${{fmtApproxUtc(ms)}})`;
  }}

  function updateRangeText(a, b) {{
    rangeText.textContent = `Showing blocks ${{a.toLocaleString()}} - ${{b.toLocaleString()}} (${{(b - a + 1).toLocaleString()}} blocks)`;
    if (!rangeDateText) return;
    const msA = blockToApproxUnixMs(a);
    const msB = blockToApproxUnixMs(b);
    if (!Number.isFinite(msA) || !Number.isFinite(msB)) {{
      rangeDateText.textContent = 'Approx UTC range unavailable (missing anchor timestamp).';
      return;
    }}
    rangeDateText.textContent =
      `Approx UTC: ${{fmtApproxUtc(msA)}} \u2192 ${{fmtApproxUtc(msB)}} (${{fmtApproxSpan(msA, msB)}})` +
      `, using ~${{BLOCK_TIME_APPROX_SECONDS.toFixed(2)}}s/block (${{TIME_ANCHOR_SOURCE}})`;
  }}

  function markScoreStale(reason) {{
    if (!scoreStatus) return;
    const why = reason ? ` (${{reason}})` : '';
    scoreStatus.textContent = `Score is stale${{why}}. Click "Score current range" to compute.`;
  }}

  function onSetCursor(u) {{
    if (!hoverText) return;
    const idx = u && u.cursor ? u.cursor.idx : null;
    if (idx == null || idx < 0 || idx >= blocks.length) {{
      hoverText.textContent = '';
      return;
    }}
    const b = blocks[idx];
    const ms = blockToApproxUnixMs(b);
    if (!Number.isFinite(ms)) {{
      hoverText.textContent = `Hover: block ${{b.toLocaleString()}}`;
      return;
    }}
    hoverText.textContent = `Hover: block ${{b.toLocaleString()}} (~${{fmtApproxUtc(ms)}})`;
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

  function parseWeight(inputEl, fallback) {{
    const v = Number(inputEl.value);
    return Number.isFinite(v) && v >= 0 ? v : fallback;
  }}

  function lowerBound(arr, x) {{
    let lo = 0;
    let hi = arr.length;
    while (lo < hi) {{
      const mid = (lo + hi) >> 1;
      if (arr[mid] < x) lo = mid + 1;
      else hi = mid;
    }}
    return lo;
  }}

  function upperBound(arr, x) {{
    let lo = 0;
    let hi = arr.length;
    while (lo < hi) {{
      const mid = (lo + hi) >> 1;
      if (arr[mid] <= x) lo = mid + 1;
      else hi = mid;
    }}
    return lo;
  }}

  function percentile(values, p) {{
    if (!values.length) return 0;
    const s = values.slice().sort(function (a, b) {{ return a - b; }});
    const k = (s.length - 1) * (p / 100);
    const lo = Math.floor(k);
    const hi = Math.ceil(k);
    if (lo === hi) return s[lo];
    const w = k - lo;
    return s[lo] * (1 - w) + s[hi] * w;
  }}

  function normalizedWeightedSum(values, weights) {{
    let sumW = 0;
    let sum = 0;
    for (let i = 0; i < values.length; i++) {{
      const w = Math.max(0, weights[i] || 0);
      sumW += w;
      sum += w * values[i];
    }}
    return sumW > 0 ? (sum / sumW) : 0;
  }}

  function getModeFlags(mode) {{
    const usesFeedforward = (
      mode === 'alpha-only' ||
      mode === 'pi+ff' ||
      mode === 'pdi+ff'
    );
    const usesP = (
      mode === 'p' ||
      mode === 'pi' ||
      mode === 'pd' ||
      mode === 'pdi' ||
      mode === 'pi+ff' ||
      mode === 'pdi+ff'
    );
    const usesI = (
      mode === 'pi' ||
      mode === 'pdi' ||
      mode === 'pi+ff' ||
      mode === 'pdi+ff'
    );
    const usesD = (
      mode === 'pd' ||
      mode === 'pdi' ||
      mode === 'pdi+ff'
    );
    return {{ usesFeedforward, usesP, usesI, usesD }};
  }}

  function updateScorecard(minBlock, maxBlock, maxFeeGwei, targetVaultEth) {{
    if (!derivedVaultEth.length || !derivedChargedFeeGwei.length) return;
    const i0 = lowerBound(blocks, minBlock);
    const i1 = upperBound(blocks, maxBlock) - 1;
    if (i0 < 0 || i1 < i0 || i1 >= blocks.length) return;

    const n = i1 - i0 + 1;
    if (n <= 0) return;

    const deadbandPct = parsePositive(deficitDeadbandPctInput, {DEFAULT_DEFICIT_DEADBAND_PCT});
    const deadbandEth = targetVaultEth * (deadbandPct / 100);
    const feeScale = maxFeeGwei > 0 ? maxFeeGwei : 1;

    let maxDrawdownEth = 0;
    let underCount = 0;
    let deficitAreaBand = 0;
    let worstStreak = 0;
    let curStreak = 0;
    let clampMaxCount = 0;

    let feeSum = 0;
    let feeSqSum = 0;
    const feeSteps = [];
    let maxStep = 0;

    for (let i = i0; i <= i1; i++) {{
      const target = derivedVaultTargetEth[i];
      const vault = derivedVaultEth[i];
      const gap = vault - target;
      const deficitEth = target - vault;

      if (gap < 0) {{
        underCount += 1;
        curStreak += 1;
        if (curStreak > worstStreak) worstStreak = curStreak;
      }} else {{
        curStreak = 0;
      }}

      maxDrawdownEth = Math.max(maxDrawdownEth, Math.max(0, -gap));
      deficitAreaBand += Math.max(0, deficitEth - deadbandEth);

      if (derivedClampState[i] === 'max') clampMaxCount += 1;

      const fee = derivedChargedFeeGwei[i];
      feeSum += fee;
      feeSqSum += fee * fee;
      if (i > i0) {{
        const step = Math.abs(fee - derivedChargedFeeGwei[i - 1]);
        feeSteps.push(step);
        if (step > maxStep) maxStep = step;
      }}
    }}

    const feeMean = feeSum / n;
    const feeVar = Math.max(0, (feeSqSum / n) - feeMean * feeMean);
    const feeStd = Math.sqrt(feeVar);
    const stepP95 = percentile(feeSteps, 95);
    const stepP99 = percentile(feeSteps, 99);
    const clampMaxRatio = clampMaxCount / n;
    const underTargetRatio = underCount / n;

    const finalGapEth = derivedVaultEth[i1] - derivedVaultTargetEth[i1];
    const absFinalGapEth = Math.abs(finalGapEth);

    const dDraw = targetVaultEth > 0 ? (maxDrawdownEth / targetVaultEth) : 0;
    const dUnder = underTargetRatio;
    const dArea = targetVaultEth > 0 ? (deficitAreaBand / (targetVaultEth * n)) : 0;
    const dGap = targetVaultEth > 0 ? (absFinalGapEth / targetVaultEth) : 0;
    const dStreak = worstStreak / n;

    const uStd = feeStd / feeScale;
    const uP95 = stepP95 / feeScale;
    const uP99 = stepP99 / feeScale;
    const uMax = maxStep / feeScale;
    const uClamp = clampMaxRatio;

    const wDraw = parseWeight(healthWDrawInput, {DEFAULT_HEALTH_W_DRAW});
    const wUnder = parseWeight(healthWUnderInput, {DEFAULT_HEALTH_W_UNDER});
    const wArea = parseWeight(healthWAreaInput, {DEFAULT_HEALTH_W_AREA});
    const wGap = parseWeight(healthWGapInput, {DEFAULT_HEALTH_W_GAP});
    const wStreak = parseWeight(healthWStreakInput, {DEFAULT_HEALTH_W_STREAK});

    const wStd = parseWeight(uxWStdInput, {DEFAULT_UX_W_STD});
    const wP95 = parseWeight(uxWP95Input, {DEFAULT_UX_W_P95});
    const wP99 = parseWeight(uxWP99Input, {DEFAULT_UX_W_P99});
    const wMax = parseWeight(uxWMaxStepInput, {DEFAULT_UX_W_MAXSTEP});
    const wClamp = parseWeight(uxWClampInput, {DEFAULT_UX_W_CLAMP});

    const wHealth = parseWeight(scoreWeightHealthInput, {DEFAULT_HEALTH_WEIGHT});
    const wUx = parseWeight(scoreWeightUxInput, {DEFAULT_UX_WEIGHT});

    const healthBadness = normalizedWeightedSum(
      [dDraw, dUnder, dArea, dGap, dStreak],
      [wDraw, wUnder, wArea, wGap, wStreak]
    );
    const uxBadness = normalizedWeightedSum(
      [uStd, uP95, uP99, uMax, uClamp],
      [wStd, wP95, wP99, wMax, wClamp]
    );
    const totalBadness = normalizedWeightedSum([healthBadness, uxBadness], [wHealth, wUx]);

    scoreHealthBadness.textContent = formatNum(healthBadness, 6);
    scoreUxBadness.textContent = formatNum(uxBadness, 6);
    scoreTotalBadness.textContent = formatNum(totalBadness, 6);
    scoreWeightSummary.textContent =
      `overall weights: health=${{formatNum(wHealth, 3)}}, ux=${{formatNum(wUx, 3)}}`;

    healthMaxDrawdown.textContent = `${{formatNum(maxDrawdownEth, 6)}} ETH`;
    healthUnderTargetRatio.textContent = `${{formatNum(underTargetRatio, 4)}}`;
    healthAbsFinalGap.textContent = `${{formatNum(absFinalGapEth, 6)}} ETH`;
    healthDeficitAreaBand.textContent = `${{formatNum(deficitAreaBand, 6)}} ETH*block`;
    healthWorstDeficitStreak.textContent = `${{formatNum(worstStreak, 0)}} blocks`;

    uxFeeStd.textContent = `${{formatNum(feeStd, 6)}} gwei/L2gas`;
    uxFeeStepP95.textContent = `${{formatNum(stepP95, 6)}} gwei/L2gas`;
    uxFeeStepP99.textContent = `${{formatNum(stepP99, 6)}} gwei/L2gas`;
    uxFeeStepMax.textContent = `${{formatNum(maxStep, 6)}} gwei/L2gas`;
    uxClampMaxRatio.textContent = `${{formatNum(clampMaxRatio, 4)}}`;

    healthFormulaLine.textContent =
      `health_badness = wDraw*dDraw + wUnder*dUnder + wArea*dArea + wGap*dGap + wStreak*dStreak ` +
      `(dDraw=${{formatNum(dDraw, 4)}}, dUnder=${{formatNum(dUnder, 4)}}, dArea=${{formatNum(dArea, 4)}}, dGap=${{formatNum(dGap, 4)}}, dStreak=${{formatNum(dStreak, 4)}})`;
    uxFormulaLine.textContent =
      `ux_badness = wStd*uStd + wP95*uP95 + wP99*uP99 + wMax*uMax + wClamp*uClamp ` +
      `(uStd=${{formatNum(uStd, 4)}}, uP95=${{formatNum(uP95, 4)}}, uP99=${{formatNum(uP99, 4)}}, uMax=${{formatNum(uMax, 4)}}, uClamp=${{formatNum(uClamp, 4)}})`;
    totalFormulaLine.textContent =
      `total_badness = wHealth*health_badness + wUx*ux_badness = ${{formatNum(totalBadness, 6)}} ` +
      `(deadband=${{formatNum(deadbandPct, 2)}}%, blocks=${{n.toLocaleString()}})`;

    if (scoreStatus) {{
      scoreStatus.textContent =
        `Scored blocks ${{blocks[i0].toLocaleString()}}-${{blocks[i1].toLocaleString()}} ` +
        `(${{n.toLocaleString()}} blocks).`;
    }}
  }}

  function ensureFeedforwardDefaults() {{
    const alphaGasNow = parsePositive(alphaGasInput, 0);
    const alphaBlobNow = parsePositive(alphaBlobInput, 0);
    if (!autoAlphaInput.checked && alphaGasNow === 0 && alphaBlobNow === 0) {{
      alphaGasInput.value = DEFAULT_ALPHA_GAS.toFixed(6);
      alphaBlobInput.value = DEFAULT_ALPHA_BLOB.toFixed(6);
    }}
  }}

  function disableFeedforward() {{
    autoAlphaInput.checked = false;
    alphaGasInput.value = '0';
    alphaBlobInput.value = '0';
  }}

  function applyControllerModePreset(mode) {{
    if (mode === 'alpha-only') {{
      kpInput.value = '0';
      kiInput.value = '0';
      kdInput.value = '0';
      ensureFeedforwardDefaults();
      return;
    }}

    if (mode === 'p') {{
      disableFeedforward();
      kiInput.value = '0';
      kdInput.value = '0';
      return;
    }}

    if (mode === 'pi') {{
      disableFeedforward();
      kdInput.value = '0';
      return;
    }}

    if (mode === 'pd') {{
      disableFeedforward();
      kiInput.value = '0';
      return;
    }}

    if (mode === 'pdi') {{
      disableFeedforward();
      return;
    }}

    if (mode === 'pi+ff') {{
      kdInput.value = '0';
      ensureFeedforwardDefaults();
      return;
    }}

    if (mode === 'pdi+ff') {{
      ensureFeedforwardDefaults();
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
  let derivedDTermFeeGwei = [];
  let derivedFeedbackFeeGwei = [];
  let derivedChargedFeeGwei = [];
  let derivedDeficitEth = [];
  let derivedEpsilon = [];
  let derivedDerivative = [];
  let derivedIntegral = [];
  let derivedClampState = [];
  let derivedVaultEth = [];
  let derivedVaultTargetEth = [];
  let sweepPlot;
  let sweepRunning = false;
  let sweepCancelRequested = false;
  let sweepBestCandidate = null;
  let sweepRunSeq = 0;
  let sweepPoints = [];

  function setSweepUiState(running) {{
    sweepRunning = running;
    if (sweepBtn) sweepBtn.disabled = running;
    if (sweepCancelBtn) sweepCancelBtn.disabled = !running;
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = running || !sweepBestCandidate;
    if (sweepSpinner) sweepSpinner.style.display = running ? 'inline-block' : 'none';
  }}

  function setSweepStatus(msg) {{
    if (sweepStatus) sweepStatus.textContent = msg || '';
  }}

  function setSweepHoverText(msg) {{
    if (!sweepHover) return;
    sweepHover.textContent = msg || 'Hover point: -';
  }}

  function markSweepStale(reason) {{
    if (sweepRunning) return;
    sweepBestCandidate = null;
    sweepPoints = [];
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = true;
    const why = reason ? ` (${{reason}})` : '';
    setSweepStatus(`Sweep stale${{why}}. Run parameter sweep to refresh.`);
    setSweepHoverText('Hover point: -');
  }}

  function getSweepRangeIndices() {{
    const [minB, maxB] = clampRange(minInput.value, maxInput.value);
    const i0 = lowerBound(blocks, minB);
    const i1 = upperBound(blocks, maxB) - 1;
    if (i0 >= blocks.length || i1 < i0) return null;
    return {{ minB, maxB, i0, i1, n: i1 - i0 + 1 }};
  }}

  function parseScoringWeights() {{
    return {{
      deadbandPct: parseWeight(deficitDeadbandPctInput, {DEFAULT_DEFICIT_DEADBAND_PCT}),
      wHealth: parseWeight(scoreWeightHealthInput, {DEFAULT_HEALTH_WEIGHT}),
      wUx: parseWeight(scoreWeightUxInput, {DEFAULT_UX_WEIGHT}),
      wDraw: parseWeight(healthWDrawInput, {DEFAULT_HEALTH_W_DRAW}),
      wUnder: parseWeight(healthWUnderInput, {DEFAULT_HEALTH_W_UNDER}),
      wArea: parseWeight(healthWAreaInput, {DEFAULT_HEALTH_W_AREA}),
      wGap: parseWeight(healthWGapInput, {DEFAULT_HEALTH_W_GAP}),
      wStreak: parseWeight(healthWStreakInput, {DEFAULT_HEALTH_W_STREAK}),
      wStd: parseWeight(uxWStdInput, {DEFAULT_UX_W_STD}),
      wP95: parseWeight(uxWP95Input, {DEFAULT_UX_W_P95}),
      wP99: parseWeight(uxWP99Input, {DEFAULT_UX_W_P99}),
      wMaxStep: parseWeight(uxWMaxStepInput, {DEFAULT_UX_W_MAXSTEP}),
      wClamp: parseWeight(uxWClampInput, {DEFAULT_UX_W_CLAMP})
    }};
  }}

  function buildSweepCandidates() {{
    const out = [];
    for (const mode of SWEEP_MODES) {{
      for (const kp of SWEEP_KP_VALUES) {{
        for (const ki of SWEEP_KI_VALUES) {{
          for (const kd of SWEEP_KD_VALUES) {{
            out.push({{
              mode,
              kp,
              ki,
              kd
            }});
          }}
        }}
      }}
    }}
    return out;
  }}

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
    const dffBlocks = parseNonNegativeInt(dffBlocksInput, {DEFAULT_D_FF_BLOCKS});
    const dfbBlocks = parseNonNegativeInt(dfbBlocksInput, {DEFAULT_D_FB_BLOCKS});
    const derivBeta = clampNum(parseNumber(dSmoothBetaInput, {DEFAULT_DERIV_BETA}), 0, 1);
    const kp = parsePositive(kpInput, 0);
    const ki = parsePositive(kiInput, 0);
    const kd = parsePositive(kdInput, 0);
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
    const modeFlags = getModeFlags(controllerMode);
    const modeUsesFeedforward = modeFlags.usesFeedforward;
    const modeUsesP = modeFlags.usesP;
    const modeUsesI = modeFlags.usesI;
    const modeUsesD = modeFlags.usesD;

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
    derivedDTermFeeGwei = new Array(n);
    derivedFeedbackFeeGwei = new Array(n);
    derivedChargedFeeGwei = new Array(n);
    derivedDeficitEth = new Array(n);
    derivedEpsilon = new Array(n);
    derivedDerivative = new Array(n);
    derivedIntegral = new Array(n);
    derivedClampState = new Array(n);
    derivedVaultEth = new Array(n);
    derivedVaultTargetEth = new Array(n);

    let vault = initialVaultEth;
    let pendingRevenueEth = 0;
    let integralState = 0;
    let epsilonPrev = 0;
    let derivFiltered = 0;

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

      if (modeUsesI) {{
        integralState = clampNum(integralState + epsilon, iMin, iMax);
      }} else {{
        integralState = 0;
      }}

      const deRaw = i > 0 ? (epsilon - epsilonPrev) : 0;
      derivFiltered = derivBeta * derivFiltered + (1 - derivBeta) * deRaw;

      const pTermWei = modeUsesP ? (kp * epsilon * feeRangeWei) : 0;
      const iTermWei = modeUsesI ? (ki * integralState * feeRangeWei) : 0;
      const dTermWei = modeUsesD ? (kd * derivFiltered * feeRangeWei) : 0;
      const feedbackWei = pTermWei + iTermWei + dTermWei;
      const feedforwardWei = modeUsesFeedforward ? (gasComponentWei + blobComponentWei) : 0;
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
      derivedDTermFeeGwei[i] = dTermWei / 1e9;
      derivedFeedbackFeeGwei[i] = feedbackWei / 1e9;
      derivedChargedFeeGwei[i] = chargedFeeWeiPerL2Gas / 1e9;
      derivedDeficitEth[i] = deficitEth;
      derivedEpsilon[i] = epsilon;
      derivedDerivative[i] = derivFiltered;
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
      epsilonPrev = epsilon;
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
        derivedDTermFeeGwei,
        derivedFeedbackFeeGwei,
        derivedChargedFeeGwei
      ]);
      feedbackPlot.setData([
        blocks,
        derivedDeficitEth,
        derivedEpsilon,
        derivedDerivative,
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
    latestDerivative.textContent = `${{formatNum(derivedDerivative[lastIdx], 6)}}`;
    latestIntegral.textContent = `${{formatNum(derivedIntegral[lastIdx], 6)}}`;
    latestFfTerm.textContent = `${{formatNum(derivedFeedforwardFeeGwei[lastIdx], 4)}} gwei/L2gas`;
    latestDTerm.textContent = `${{formatNum(derivedDTermFeeGwei[lastIdx], 4)}} gwei/L2gas`;
    latestFbTerm.textContent = `${{formatNum(derivedFeedbackFeeGwei[lastIdx], 4)}} gwei/L2gas`;
    latestClampState.textContent = derivedClampState[lastIdx];
    latestVaultValue.textContent = `${{formatNum(derivedVaultEth[lastIdx], 6)}} ETH`;
    latestVaultGap.textContent = `${{formatNum(derivedVaultEth[lastIdx] - targetVaultEth, 6)}} ETH`;
    markScoreStale('recomputed charts');
  }}

  function evaluateSweepCandidate(i0, i1, candidate, simCfg, scoreCfg) {{
    const modeFlags = getModeFlags(candidate.mode);
    const n = i1 - i0 + 1;
    const targetDenom = simCfg.targetVaultEth > 0 ? simCfg.targetVaultEth : 1;
    const feeDenom = simCfg.maxFeeGwei > 0 ? simCfg.maxFeeGwei : 1;
    const deadbandFloor = simCfg.targetVaultEth * (1 - scoreCfg.deadbandPct / 100);

    const vaultSeries = new Array(n);
    const feeSteps = [];
    let vault = simCfg.initialVaultEth;
    let pendingRevenueEth = 0;
    let integralState = 0;
    let epsilonPrev = 0;
    let derivFiltered = 0;
    let feePrev = null;
    let feeSum = 0;
    let feeSumSq = 0;
    let feeCount = 0;
    let clampMaxCount = 0;
    let peak = vault;
    let maxDrawdownEth = 0;
    let underTargetCount = 0;
    let deficitAreaBand = 0;
    let worstStreak = 0;
    let currentStreak = 0;

    for (let local = 0; local < n; local++) {{
      const i = i0 + local;
      const baseFeeWei = baseFeeGwei[i] * 1e9;
      const blobBaseFeeWei = blobFeeGwei[i] * 1e9;
      const ffIndex = Math.max(0, i - simCfg.dffBlocks);
      const baseFeeFfWei = baseFeeGwei[ffIndex] * 1e9;
      const blobBaseFeeFfWei = blobFeeGwei[ffIndex] * 1e9;

      const gasCostWei = simCfg.l1GasUsed * (baseFeeWei + simCfg.priorityFeeWei);
      const blobCostWei = simCfg.numBlobs * BLOB_GAS_PER_BLOB * blobBaseFeeWei;
      const totalCostWei = gasCostWei + blobCostWei;

      const fbLocal = local - simCfg.dfbBlocks;
      const observedVault = fbLocal >= 0 ? vaultSeries[fbLocal] : simCfg.initialVaultEth;
      const deficitEth = simCfg.targetVaultEth - observedVault;
      const epsilon = targetDenom > 0 ? (deficitEth / targetDenom) : 0;
      if (modeFlags.usesI) {{
        integralState = clampNum(integralState + epsilon, simCfg.iMin, simCfg.iMax);
      }} else {{
        integralState = 0;
      }}
      const deRaw = local > 0 ? (epsilon - epsilonPrev) : 0;
      derivFiltered =
        simCfg.derivBeta * derivFiltered + (1 - simCfg.derivBeta) * deRaw;

      const feedforwardWei = modeFlags.usesFeedforward
        ? (
            simCfg.alphaGas * (baseFeeFfWei + simCfg.priorityFeeWei) +
            simCfg.alphaBlob * blobBaseFeeFfWei
          )
        : 0;
      const pTermWei = modeFlags.usesP ? (candidate.kp * epsilon * simCfg.feeRangeWei) : 0;
      const iTermWei = modeFlags.usesI ? (candidate.ki * integralState * simCfg.feeRangeWei) : 0;
      const dTermWei = modeFlags.usesD ? (candidate.kd * derivFiltered * simCfg.feeRangeWei) : 0;
      const feedbackWei = pTermWei + iTermWei + dTermWei;
      const chargedFeeWeiPerL2Gas = clampNum(
        feedforwardWei + feedbackWei,
        simCfg.minFeeWei,
        simCfg.maxFeeWei
      );

      if (chargedFeeWeiPerL2Gas >= simCfg.maxFeeWei - 1e-9) clampMaxCount += 1;

      const chargedFeeGwei = chargedFeeWeiPerL2Gas / 1e9;
      feeSum += chargedFeeGwei;
      feeSumSq += chargedFeeGwei * chargedFeeGwei;
      feeCount += 1;
      if (feePrev != null) feeSteps.push(Math.abs(chargedFeeGwei - feePrev));
      feePrev = chargedFeeGwei;

      const l2RevenueEthPerBlock =
        (chargedFeeWeiPerL2Gas * simCfg.l2GasPerL1BlockSeries[i]) / 1e18;
      pendingRevenueEth += l2RevenueEthPerBlock;

      const posted = ((i + 1) % simCfg.postEveryBlocks) === 0;
      if (posted) {{
        vault += pendingRevenueEth;
        pendingRevenueEth = 0;
        vault -= totalCostWei / 1e18;
      }}
      vaultSeries[local] = vault;

      if (vault > peak) peak = vault;
      const drawdown = peak - vault;
      if (drawdown > maxDrawdownEth) maxDrawdownEth = drawdown;

      if (vault < simCfg.targetVaultEth) {{
        underTargetCount += 1;
        currentStreak += 1;
        if (currentStreak > worstStreak) worstStreak = currentStreak;
      }} else {{
        currentStreak = 0;
      }}

      if (vault < deadbandFloor) deficitAreaBand += (deadbandFloor - vault);
      epsilonPrev = epsilon;
    }}

    const lastVault = vaultSeries[n - 1];
    const underTargetRatio = n > 0 ? (underTargetCount / n) : 0;
    const absFinalGapEth = Math.abs(lastVault - simCfg.targetVaultEth);
    const meanFee = feeCount > 0 ? (feeSum / feeCount) : 0;
    const variance = feeCount > 0 ? Math.max(0, (feeSumSq / feeCount) - meanFee * meanFee) : 0;
    const feeStd = Math.sqrt(variance);
    const stepP95 = percentile(feeSteps, 95);
    const stepP99 = percentile(feeSteps, 99);
    const maxStep = feeSteps.length ? Math.max.apply(null, feeSteps) : 0;
    const clampMaxRatio = n > 0 ? (clampMaxCount / n) : 0;

    const dDraw = maxDrawdownEth / targetDenom;
    const dUnder = underTargetRatio;
    const dArea = deficitAreaBand / (targetDenom * n);
    const dGap = absFinalGapEth / targetDenom;
    const dStreak = n > 0 ? (worstStreak / n) : 0;
    const healthBadness = normalizedWeightedSum(
      [dDraw, dUnder, dArea, dGap, dStreak],
      [scoreCfg.wDraw, scoreCfg.wUnder, scoreCfg.wArea, scoreCfg.wGap, scoreCfg.wStreak]
    );

    const uStd = feeStd / feeDenom;
    const uP95 = stepP95 / feeDenom;
    const uP99 = stepP99 / feeDenom;
    const uMax = maxStep / feeDenom;
    const uClamp = clampMaxRatio;
    const uxBadness = normalizedWeightedSum(
      [uStd, uP95, uP99, uMax, uClamp],
      [scoreCfg.wStd, scoreCfg.wP95, scoreCfg.wP99, scoreCfg.wMaxStep, scoreCfg.wClamp]
    );

    const totalBadness = normalizedWeightedSum(
      [healthBadness, uxBadness],
      [scoreCfg.wHealth, scoreCfg.wUx]
    );

    return {{
      mode: candidate.mode,
      kp: candidate.kp,
      ki: candidate.ki,
      kd: candidate.kd,
      nBlocks: n,
      healthBadness,
      uxBadness,
      totalBadness,
      maxDrawdownEth,
      underTargetRatio,
      absFinalGapEth,
      feeStd,
      stepP95,
      stepP99,
      maxStep,
      clampMaxRatio
    }};
  }}

  function renderSweepScatter(results, best) {{
    if (!sweepPlot) return;
    const points = [];
    for (let i = 0; i < results.length; i++) {{
      const r = results[i];
      const isBest = Boolean(
        best &&
        r.mode === best.mode &&
        r.kp === best.kp &&
        r.ki === best.ki &&
        r.kd === best.kd
      );
      points.push({{
        ux: r.uxBadness,
        health: r.healthBadness,
        total: r.totalBadness,
        mode: r.mode,
        kp: r.kp,
        ki: r.ki,
        kd: r.kd,
        isBest
      }});
    }}
    points.sort(function (a, b) {{
      if (a.ux !== b.ux) return a.ux - b.ux;
      return a.health - b.health;
    }});

    const x = new Array(points.length);
    const allY = new Array(points.length);
    const bestY = new Array(points.length);

    let xMin = Infinity;
    let xMax = -Infinity;
    let yMin = Infinity;
    let yMax = -Infinity;

    for (let i = 0; i < points.length; i++) {{
      const p = points[i];
      p.rank = i + 1;
      x[i] = p.ux;
      allY[i] = p.health;
      bestY[i] = p.isBest ? p.health : null;
      if (p.ux < xMin) xMin = p.ux;
      if (p.ux > xMax) xMax = p.ux;
      if (p.health < yMin) yMin = p.health;
      if (p.health > yMax) yMax = p.health;
    }}

    sweepPoints = points;
    sweepPlot.setData([x, allY, bestY]);
    if (points.length) {{
      const xSpan = Math.max(xMax - xMin, 1e-9);
      const ySpan = Math.max(yMax - yMin, 1e-9);
      const xPad = xSpan * 0.08;
      const yPad = ySpan * 0.08;
      sweepPlot.batch(function () {{
        sweepPlot.setScale('x', {{ min: xMin - xPad, max: xMax + xPad }});
        sweepPlot.setScale('y', {{ min: yMin - yPad, max: yMax + yPad }});
      }});
    }}
  }}

  function onSetSweepCursor(u) {{
    const idx = u && u.cursor ? u.cursor.idx : null;
    if (idx == null || idx < 0 || idx >= sweepPoints.length) {{
      setSweepHoverText('Hover point: -');
      return;
    }}
    const p = sweepPoints[idx];
    if (!p) {{
      setSweepHoverText('Hover point: -');
      return;
    }}
    const rankPart = Number.isFinite(p.rank) ? `#${{p.rank}}` : '-';
    const bestPart = p.isBest ? ' (best)' : '';
    setSweepHoverText(
      `Hover point ${{rankPart}}${{bestPart}}: mode=${{p.mode}}, ` +
      `Kp=${{formatNum(p.kp, 4)}}, Ki=${{formatNum(p.ki, 4)}}, Kd=${{formatNum(p.kd, 4)}}, ` +
      `health=${{formatNum(p.health, 6)}}, UX=${{formatNum(p.ux, 6)}}, total=${{formatNum(p.total, 6)}}`
    );
  }}

  async function runParameterSweep() {{
    if (sweepRunning) return;
    recalcDerivedSeries();

    const range = getSweepRangeIndices();
    if (!range) {{
      setSweepStatus('Sweep failed: invalid selected range.');
      return;
    }}
    if (range.n > SWEEP_MAX_BLOCKS) {{
      setSweepStatus(
        `Sweep range too large (${{range.n.toLocaleString()}} blocks). ` +
        `Please zoom to <= ${{SWEEP_MAX_BLOCKS.toLocaleString()}} blocks.`
      );
      return;
    }}

    const candidates = buildSweepCandidates();
    if (!candidates.length) {{
      setSweepStatus('No sweep candidates configured.');
      return;
    }}

    const postEveryBlocks = parsePositiveInt(postEveryBlocksInput, 10);
    const l1GasUsed = parsePositive(l1GasUsedInput, 0);
    const numBlobs = parsePositive(numBlobsInput, 0);
    const priorityFeeWei = parsePositive(priorityFeeGweiInput, 0) * 1e9;
    const dffBlocks = parseNonNegativeInt(dffBlocksInput, {DEFAULT_D_FF_BLOCKS});
    const dfbBlocks = parseNonNegativeInt(dfbBlocksInput, {DEFAULT_D_FB_BLOCKS});
    const derivBeta = clampNum(parseNumber(dSmoothBetaInput, {DEFAULT_DERIV_BETA}), 0, 1);
    const iMinRaw = parseNumber(iMinInput, -5);
    const iMaxRaw = parseNumber(iMaxInput, 5);
    const iMin = Math.min(iMinRaw, iMaxRaw);
    const iMax = Math.max(iMinRaw, iMaxRaw);
    const minFeeWei = parsePositive(minFeeGweiInput, 0) * 1e9;
    const maxFeeGwei = parsePositive(maxFeeGweiInput, {DEFAULT_MAX_FEE_GWEI});
    const maxFeeWei = Math.max(minFeeWei, maxFeeGwei * 1e9);
    const initialVaultEth = parsePositive(initialVaultEthInput, 0);
    const targetVaultEth = parsePositive(targetVaultEthInput, 0);
    const alphaGasFixed = parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS);
    const alphaBlobFixed = parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB);
    const scoreCfg = parseScoringWeights();
    const simCfg = {{
      postEveryBlocks,
      l1GasUsed,
      numBlobs,
      priorityFeeWei,
      dffBlocks,
      dfbBlocks,
      derivBeta,
      iMin,
      iMax,
      minFeeWei,
      maxFeeWei,
      maxFeeGwei,
      feeRangeWei: maxFeeWei - minFeeWei,
      initialVaultEth,
      targetVaultEth,
      alphaGas: alphaGasFixed,
      alphaBlob: alphaBlobFixed,
      l2GasPerL1BlockSeries: derivedL2GasPerL1Block
    }};

    sweepCancelRequested = false;
    const runId = ++sweepRunSeq;
    setSweepUiState(true);
    if (sweepCandidateCount) sweepCandidateCount.textContent = `${{candidates.length}} candidates`;
    if (sweepRangeCount) sweepRangeCount.textContent = `${{range.n.toLocaleString()}} blocks`;
    setSweepStatus(
      `Running sweep on blocks ${{range.minB.toLocaleString()}}-${{range.maxB.toLocaleString()}}...`
    );

    const started = performance.now();
    let lastYield = started;
    const results = [];
    setSweepHoverText('Hover point: -');
    for (let idx = 0; idx < candidates.length; idx++) {{
      if (sweepCancelRequested || runId !== sweepRunSeq) break;
      const result = evaluateSweepCandidate(range.i0, range.i1, candidates[idx], simCfg, scoreCfg);
      results.push(result);

      if ((idx + 1) % 5 === 0 || idx + 1 === candidates.length) {{
        setSweepStatus(
          `Sweep progress: ${{(idx + 1).toLocaleString()}} / ${{candidates.length.toLocaleString()}} candidates`
        );
        const now = performance.now();
        if (now - lastYield > 24) {{
          await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
          lastYield = performance.now();
        }}
      }}
    }}

    if (runId !== sweepRunSeq) return;

    const elapsedSec = (performance.now() - started) / 1000;
    if (!results.length) {{
      setSweepStatus('Sweep did not produce results.');
      setSweepHoverText('Hover point: -');
      setSweepUiState(false);
      return;
    }}

    results.sort(function (a, b) {{
      return a.totalBadness - b.totalBadness;
    }});
    sweepBestCandidate = results[0];
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = false;
    if (sweepBestMode) sweepBestMode.textContent = sweepBestCandidate.mode;
    if (sweepBestKp) sweepBestKp.textContent = formatNum(sweepBestCandidate.kp, 4);
    if (sweepBestKi) sweepBestKi.textContent = formatNum(sweepBestCandidate.ki, 4);
    if (sweepBestKd) sweepBestKd.textContent = formatNum(sweepBestCandidate.kd, 4);
    if (sweepBestHealth) sweepBestHealth.textContent = formatNum(sweepBestCandidate.healthBadness, 6);
    if (sweepBestUx) sweepBestUx.textContent = formatNum(sweepBestCandidate.uxBadness, 6);
    if (sweepBestTotal) sweepBestTotal.textContent = formatNum(sweepBestCandidate.totalBadness, 6);
    renderSweepScatter(results, sweepBestCandidate);

    if (sweepCancelRequested) {{
      setSweepStatus(
        `Sweep canceled after ${{results.length.toLocaleString()}} candidates in ${{formatNum(elapsedSec, 2)}}s.`
      );
    }} else {{
      setSweepStatus(
        `Sweep complete: ${{results.length.toLocaleString()}} candidates in ${{formatNum(elapsedSec, 2)}}s.`
      );
    }}
    setSweepUiState(false);
  }}

  function applySweepBestCandidate() {{
    if (!sweepBestCandidate) return;
    controllerModeInput.value = sweepBestCandidate.mode;
    applyControllerModePreset(sweepBestCandidate.mode);
    kpInput.value = `${{sweepBestCandidate.kp}}`;
    kiInput.value = `${{sweepBestCandidate.ki}}`;
    kdInput.value = `${{sweepBestCandidate.kd}}`;
    recalcDerivedSeries();
    markScoreStale('applied sweep best candidate');
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
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
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
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
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
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
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
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }}
    }};
  }}

  function makeControllerOpts(width, height) {{
    return {{
      title: 'Controller Components (Feedforward + P/I/D)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
        {{ label: 'FF term (gwei/L2 gas)', stroke: '#334155', width: 1.2 }},
        {{ label: 'P term (gwei/L2 gas)', stroke: '#2563eb', width: 1.0 }},
        {{ label: 'I term (gwei/L2 gas)', stroke: '#f59e0b', width: 1.0 }},
        {{ label: 'D term (gwei/L2 gas)', stroke: '#ec4899', width: 1.0 }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }}
    }};
  }}

  function makeFeedbackOpts(width, height) {{
    return {{
      title: 'Feedback State (D, epsilon, dE, I)',
      width,
      height,
      scales: {{ x: {{ time: false }} }},
      series: [
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
        {{ label: 'Deficit D (ETH)', stroke: '#dc2626', width: 1.2 }},
        {{ label: 'Normalized deficit epsilon', stroke: '#0891b2', width: 1.0 }},
        {{ label: 'Filtered derivative dE_f', stroke: '#ec4899', width: 1.0 }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }}
    }};
  }}

  function makeSweepOpts(width, height) {{
    return {{
      title: 'Sweep Tradeoff: Health vs UX (lower is better)',
      width,
      height,
      scales: {{ x: {{}}, y: {{}} }},
      series: [
        {{
          value: function (u, v) {{
            if (!Number.isFinite(v)) return '';
            return formatNum(v, 6);
          }}
        }},
        {{
          label: 'Candidates (pdi/pdi+ff)',
          stroke: '#64748b',
          width: 0,
          points: {{ show: true, size: 4, stroke: '#64748b', fill: '#94a3b8' }}
        }},
        {{
          label: 'Best weighted score',
          stroke: '#dc2626',
          width: 0,
          points: {{ show: true, size: 7, stroke: '#dc2626', fill: '#ef4444' }}
        }}
      ],
      axes: [
        {{
          label: 'UX badness',
          values: function (u, vals) {{
            return vals.map(function (v) {{ return formatNum(v, 4); }});
          }}
        }},
        {{
          label: 'Health badness',
          values: function (u, vals) {{
            return vals.map(function (v) {{ return formatNum(v, 4); }});
          }}
        }}
      ],
      cursor: {{
        drag: {{ x: true, y: true, setScale: true }}
      }},
      hooks: {{
        setCursor: [onSetSweepCursor]
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
    markScoreStale('range changed');
  }}

  function resizePlots() {{
    const width = Math.max(480, baseWrap.clientWidth - 8);
    for (const p of allPlots()) {{
      p.setSize({{ width, height: 320 }});
    }}
    if (sweepPlot) {{
      const sweepSize = Math.min(width, 560);
      sweepPlot.setSize({{ width: sweepSize, height: sweepSize }});
    }}
  }}

  const width = Math.max(480, baseWrap.clientWidth - 8);
  const sweepSize = Math.min(width, 560);

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
        {{ value: function (u, v) {{ return formatBlockWithApprox(v); }} }},
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
        setScale: [onSetScale],
        setCursor: [onSetCursor]
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
    [blocks, [], [], [], [], [], []],
    controllerWrap
  );

  feedbackPlot = new uPlot(
    makeFeedbackOpts(width, 320),
    [blocks, [], [], [], []],
    feedbackWrap
  );

  vaultPlot = new uPlot(
    makeVaultOpts(width, 320),
    [blocks, [], []],
    vaultWrap
  );

  sweepPlot = new uPlot(
    makeSweepOpts(sweepSize, sweepSize),
    [[], [], []],
    sweepWrap
  );

  recalcDerivedSeries();
  setSweepUiState(false);
  setSweepStatus('Sweep idle. Uses fixed alpha and sweeps only Kp/Ki/Kd across pdi + pdi+ff.');
  setSweepHoverText('Hover point: -');
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

  if (scoreBtn) {{
    scoreBtn.addEventListener('click', function () {{
      if (scoreStatus) scoreStatus.textContent = 'Scoring current range...';
      window.setTimeout(function () {{
        const [minB, maxB] = clampRange(minInput.value, maxInput.value);
        updateScorecard(
          minB,
          maxB,
          parsePositive(maxFeeGweiInput, {DEFAULT_MAX_FEE_GWEI}),
          parsePositive(targetVaultEthInput, {DEFAULT_TARGET_VAULT_ETH})
        );
      }}, 0);
    }});
  }}

  if (sweepBtn) {{
    sweepBtn.addEventListener('click', function () {{
      runParameterSweep();
    }});
  }}

  if (sweepCancelBtn) {{
    sweepCancelBtn.addEventListener('click', function () {{
      if (!sweepRunning) return;
      sweepCancelRequested = true;
      setSweepStatus('Cancel requested. Finishing current candidate...');
    }});
  }}

  if (sweepApplyBestBtn) {{
    sweepApplyBestBtn.addEventListener('click', function () {{
      applySweepBestCandidate();
    }});
  }}

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
    dSmoothBetaInput,
    kpInput,
    kiInput,
    kdInput,
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

  [
    deficitDeadbandPctInput,
    scoreWeightHealthInput,
    scoreWeightUxInput,
    healthWDrawInput,
    healthWUnderInput,
    healthWAreaInput,
    healthWGapInput,
    healthWStreakInput,
    uxWStdInput,
    uxWP95Input,
    uxWP99Input,
    uxWMaxStepInput,
    uxWClampInput
  ].forEach(function (el) {{
    el.addEventListener('keydown', function (e) {{
      if (e.key === 'Enter') {{
        markScoreStale('score settings changed');
      }}
    }});
    el.addEventListener('change', function () {{
      markScoreStale('score settings changed');
    }});
  }});

  let resizeTimer;
  window.addEventListener('resize', function () {{
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizePlots, 120);
  }});

  markScoreStale('not computed yet');
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
    .range-text {{ font-size: 12px; color: var(--muted); }}
    .range-main {{ margin-left: auto; }}
    .range-sub {{ font-size: 12px; color: var(--muted); }}
    .status {{ margin: 4px 0 0; min-height: 18px; font-size: 12px; color: #b45309; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--muted); margin: 6px 0; }}
    .plot {{ width: 100%; min-height: 336px; margin-top: 10px; border: 1px solid var(--line); border-radius: 10px; padding: 6px; background: #fff; }}
    .formula {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #334155; word-break: break-word; }}
    .score-kpis {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 8px 0;
    }}
    .score-kpi {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 8px;
    }}
    .score-kpi-label {{ font-size: 11px; color: var(--muted); }}
    .score-kpi-value {{ font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 4px; line-height: 1.1; }}
    .score-status {{
      margin: 6px 0;
      font-size: 12px;
      color: #475569;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .sweep-status-line {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 6px 0;
    }}
    .spinner {{
      width: 12px;
      height: 12px;
      border: 2px solid #cbd5e1;
      border-top-color: #0f766e;
      border-radius: 50%;
      display: none;
      animation: spin 0.9s linear infinite;
      flex: 0 0 12px;
    }}
    @keyframes spin {{
      from {{ transform: rotate(0deg); }}
      to {{ transform: rotate(360deg); }}
    }}
    .score-subtitle {{
      font-size: 12px;
      color: #334155;
      margin: 8px 0 4px;
      font-weight: 600;
    }}
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
          <span class=\"range-text range-main\" id=\"rangeText\"></span>
          <span class=\"range-sub\" id=\"rangeDateText\"></span>
          <span class=\"range-sub\" id=\"hoverText\"></span>
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
                <option value=\"pd\"{" selected" if DEFAULT_CONTROLLER_MODE == "pd" else ""}>pd</option>
                <option value=\"pdi\"{" selected" if DEFAULT_CONTROLLER_MODE == "pdi" else ""}>pdi</option>
                <option value=\"pi+ff\"{" selected" if DEFAULT_CONTROLLER_MODE == "pi+ff" else ""}>pi+ff</option>
                <option value=\"pdi+ff\"{" selected" if DEFAULT_CONTROLLER_MODE == "pdi+ff" else ""}>pdi+ff</option>
              </select>
            </label>
            <label><input id=\"autoAlpha\" type=\"checkbox\" checked /> Auto alpha</label>
            <label>Alpha gas <input id=\"alphaGas\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_GAS:.6f}\" /></label>
            <label>Alpha blob <input id=\"alphaBlob\" type=\"number\" min=\"0\" step=\"0.000001\" value=\"{DEFAULT_ALPHA_BLOB:.6f}\" /></label>
            <label>Kp <input id=\"kp\" type=\"number\" min=\"0\" step=\"0.001\" value=\"{DEFAULT_KP:g}\" /></label>
            <label>Ki <input id=\"ki\" type=\"number\" min=\"0\" step=\"0.001\" value=\"{DEFAULT_KI:g}\" /></label>
            <label>Kd <input id=\"kd\" type=\"number\" min=\"0\" step=\"0.001\" value=\"{DEFAULT_KD:g}\" /></label>
            <label>I min <input id=\"iMin\" type=\"number\" step=\"0.1\" value=\"{DEFAULT_I_MIN:g}\" /></label>
            <label>I max <input id=\"iMax\" type=\"number\" step=\"0.1\" value=\"{DEFAULT_I_MAX:g}\" /></label>
            <label>Feedforward delay d_ff (L1 blocks) <input id=\"dffBlocks\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_D_FF_BLOCKS}\" /></label>
            <label>Feedback delay d_fb (L1 blocks) <input id=\"dfbBlocks\" type=\"number\" min=\"0\" step=\"1\" value=\"{DEFAULT_D_FB_BLOCKS}\" /></label>
            <label>D smoothing beta <input id=\"dSmoothBeta\" type=\"number\" min=\"0\" max=\"1\" step=\"0.01\" value=\"{DEFAULT_DERIV_BETA:g}\" /></label>
            <label>Min fee (gwei/L2 gas) <input id=\"minFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MIN_FEE_GWEI:g}\" /></label>
            <label>Max fee (gwei/L2 gas) <input id=\"maxFeeGwei\" type=\"number\" min=\"0\" step=\"0.0001\" value=\"{DEFAULT_MAX_FEE_GWEI:.1f}\" /></label>
            <label>Initial vault (ETH) <input id=\"initialVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_INITIAL_VAULT_ETH:g}\" /></label>
            <label>Target vault (ETH) <input id=\"targetVaultEth\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_TARGET_VAULT_ETH:g}\" /></label>
            <button class=\"primary\" id=\"recalcBtn\">Recompute derived charts</button>
          </div>
          <div class=\"formula\">cost_wei(t_post) = l1GasUsed * (baseFee_t_post + priorityFee) + numBlobs * 131072 * blobBaseFee_t_post</div>
          <div class=\"formula\">FF_t = alpha_gas * (baseFee_(t-d_ff) + priorityFee) + alpha_blob * blobBaseFee_(t-d_ff)</div>
          <div class=\"formula\">de_t = epsilon_t - epsilon_(t-1), de_f_t = beta*de_f_(t-1) + (1-beta)*de_t</div>
          <div class=\"formula\">D_t = targetVault - vault_(t-d_fb), epsilon_t = D_t / targetVault, I_t = clamp(I_(t-1) + epsilon_t, Imin, Imax)</div>
          <div class=\"formula\">fee_t = clamp(FF_t + Kp*epsilon_t*(maxFee-minFee) + Ki*I_t*(maxFee-minFee) + Kd*de_f_t*(maxFee-minFee), minFee, maxFee)</div>
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
            <span>Latest filtered derivative dE_f: <strong id=\"latestDerivative\">-</strong></span>
            <span>Latest integral I: <strong id=\"latestIntegral\">-</strong></span>
            <span>Latest FF term: <strong id=\"latestFfTerm\">-</strong></span>
            <span>Latest D term: <strong id=\"latestDTerm\">-</strong></span>
            <span>Latest FB term: <strong id=\"latestFbTerm\">-</strong></span>
            <span>Latest clamp state: <strong id=\"latestClampState\">-</strong></span>
            <span>Latest L2 gas used: <strong id=\"latestL2GasUsed\">-</strong></span>
            <span>Latest vault value: <strong id=\"latestVaultValue\">-</strong></span>
            <span>Vault - target: <strong id=\"latestVaultGap\">-</strong></span>
          </div>
        </div>

        <div class=\"assumptions score-card\">
          <div class=\"assumptions-title\">Health / UX Scoring</div>
          <div class=\"controls\">
            <label>Deficit deadband (%) <input id=\"deficitDeadbandPct\" type=\"number\" min=\"0\" step=\"0.1\" value=\"{DEFAULT_DEFICIT_DEADBAND_PCT:g}\" /></label>
            <label>Overall health weight <input id=\"scoreWeightHealth\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_WEIGHT:g}\" /></label>
            <label>Overall UX weight <input id=\"scoreWeightUx\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_WEIGHT:g}\" /></label>
            <button class=\"primary\" id=\"scoreBtn\">Score current range</button>
          </div>
          <div class=\"score-status\" id=\"scoreStatus\">Score is stale. Click \"Score current range\" to compute.</div>
          <div class=\"score-kpis\">
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">TOTAL BADNESS</div><div class=\"score-kpi-value\" id=\"scoreTotalBadness\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">HEALTH BADNESS</div><div class=\"score-kpi-value\" id=\"scoreHealthBadness\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">UX BADNESS</div><div class=\"score-kpi-value\" id=\"scoreUxBadness\">-</div></div>
          </div>
          <div class=\"score-subtitle\">Important Health Metrics</div>
          <div class=\"score-kpis\">
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Max drawdown</div><div class=\"score-kpi-value\" id=\"healthMaxDrawdown\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Under-target ratio</div><div class=\"score-kpi-value\" id=\"healthUnderTargetRatio\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Abs final gap</div><div class=\"score-kpi-value\" id=\"healthAbsFinalGap\">-</div></div>
          </div>
          <div class=\"score-subtitle\">Important UX Metrics</div>
          <div class=\"score-kpis\">
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Fee std</div><div class=\"score-kpi-value\" id=\"uxFeeStd\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Fee step p95</div><div class=\"score-kpi-value\" id=\"uxFeeStepP95\">-</div></div>
            <div class=\"score-kpi\"><div class=\"score-kpi-label\">Clamp-max ratio</div><div class=\"score-kpi-value\" id=\"uxClampMaxRatio\">-</div></div>
          </div>
          <div class=\"assumptions-title\">Score Weights (Detailed)</div>
          <div class=\"controls\">
            <label>Health w_draw <input id=\"healthWDraw\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_W_DRAW:g}\" /></label>
            <label>Health w_under <input id=\"healthWUnder\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_W_UNDER:g}\" /></label>
            <label>Health w_area <input id=\"healthWArea\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_W_AREA:g}\" /></label>
            <label>Health w_gap <input id=\"healthWGap\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_W_GAP:g}\" /></label>
            <label>Health w_streak <input id=\"healthWStreak\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_HEALTH_W_STREAK:g}\" /></label>
            <label>UX w_std <input id=\"uxWStd\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_W_STD:g}\" /></label>
            <label>UX w_p95 <input id=\"uxWP95\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_W_P95:g}\" /></label>
            <label>UX w_p99 <input id=\"uxWP99\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_W_P99:g}\" /></label>
            <label>UX w_maxStep <input id=\"uxWMaxStep\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_W_MAXSTEP:g}\" /></label>
            <label>UX w_clamp <input id=\"uxWClamp\" type=\"number\" min=\"0\" step=\"0.01\" value=\"{DEFAULT_UX_W_CLAMP:g}\" /></label>
          </div>
          <div class=\"formula\" id=\"scoreWeightSummary\">overall weights: -</div>
          <div class=\"formula\" id=\"healthFormulaLine\">health_badness = -</div>
          <div class=\"formula\" id=\"uxFormulaLine\">ux_badness = -</div>
          <div class=\"formula\" id=\"totalFormulaLine\">total_badness = -</div>
          <div class=\"metrics\">
            <span>Health deficit area (banded): <strong id=\"healthDeficitAreaBand\">-</strong></span>
            <span>Health worst deficit streak: <strong id=\"healthWorstDeficitStreak\">-</strong></span>
            <span>UX fee step p99: <strong id=\"uxFeeStepP99\">-</strong></span>
            <span>UX fee step max: <strong id=\"uxFeeStepMax\">-</strong></span>
          </div>
          <div class=\"assumptions-title\">Parameter Sweep (fixed alpha)</div>
          <div class=\"formula\">Sweep modes are fixed to pdi + pdi+ff; swept params are Kp, Ki, Kd only.</div>
          <div class=\"controls\">
            <button class=\"primary\" id=\"sweepBtn\">Run parameter sweep</button>
            <button id=\"sweepCancelBtn\" disabled>Cancel sweep</button>
            <button id=\"sweepApplyBestBtn\" disabled>Apply best params</button>
          </div>
          <div class=\"sweep-status-line\">
            <span class=\"spinner\" id=\"sweepSpinner\"></span>
            <div class=\"score-status\" id=\"sweepStatus\">Sweep idle.</div>
          </div>
          <div class=\"metrics\">
            <span>Sweep size: <strong id=\"sweepCandidateCount\">-</strong></span>
            <span>Range size: <strong id=\"sweepRangeCount\">-</strong></span>
            <span>Best mode: <strong id=\"sweepBestMode\">-</strong></span>
            <span>Best Kp: <strong id=\"sweepBestKp\">-</strong></span>
            <span>Best Ki: <strong id=\"sweepBestKi\">-</strong></span>
            <span>Best Kd: <strong id=\"sweepBestKd\">-</strong></span>
            <span>Best health badness: <strong id=\"sweepBestHealth\">-</strong></span>
            <span>Best UX badness: <strong id=\"sweepBestUx\">-</strong></span>
            <span>Best total badness: <strong id=\"sweepBestTotal\">-</strong></span>
          </div>
          <div class=\"formula\" id=\"sweepHover\">Hover point: -</div>
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
        <div id=\"sweepPlot\" class=\"plot\"></div>
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
        "--rpc",
        default="https://ethereum-rpc.publicnode.com",
        help="Optional RPC endpoint used to fill missing anchor timestamps",
    )
    parser.add_argument(
        "--timestamp-cache",
        default=str(DEFAULT_TIMESTAMP_CACHE),
        help="Persistent JSON cache for block timestamp lookups",
    )
    parser.add_argument(
        "--no-rpc-anchor",
        action="store_true",
        help="Disable RPC calls for anchor timestamps; use summary/cache only",
    )
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
    cache_path = Path(args.timestamp_cache).resolve() if args.timestamp_cache else None
    ts_cache = load_timestamp_cache(cache_path)
    rpc_url = None if args.no_rpc_anchor else args.rpc
    time_anchor = read_time_anchor(csv_path, blocks[0], blocks[-1], rpc_url, ts_cache)
    save_timestamp_cache(cache_path, ts_cache)

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_js.parent.mkdir(parents=True, exist_ok=True)

    out_js.write_text(build_app_js(blocks, base, blob, time_anchor))
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
