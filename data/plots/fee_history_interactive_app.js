(function () {
  const BLOB_GAS_PER_BLOB = 131072;
  const L1_BLOCK_TIME_SECONDS = 12;
  const DEFAULT_ALPHA_GAS = 0.000166666667;
  const DEFAULT_ALPHA_BLOB = 0.000436906667;
  const DEMAND_MULTIPLIERS = Object.freeze({ low: 0.7, base: 1.0, high: 1.4 });
  const SWEEP_MODES = Object.freeze(['pdi', 'pdi+ff']);
  const SWEEP_ALPHA_VARIANTS = Object.freeze(['current', 'zero']);
  const SWEEP_KP_VALUES = Object.freeze([0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6]);
  const SWEEP_KI_VALUES = Object.freeze([0.0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.2, 0.5, 1.0]);
  const SWEEP_KD_VALUES = Object.freeze([0.0]);
  const SWEEP_I_MAX_VALUES = Object.freeze([5.0, 10.0, 100.0]);
  const SWEEP_MAX_BLOCKS = 180000;
  const DATASET_MANIFEST = (window.__feeDatasetManifest && Array.isArray(window.__feeDatasetManifest.datasets))
    ? window.__feeDatasetManifest.datasets.slice()
    : [];
  const DATASET_BY_ID = Object.create(null);
  for (const meta of DATASET_MANIFEST) {
    if (meta && meta.id) DATASET_BY_ID[String(meta.id)] = meta;
  }

  let activeDatasetId = null;
  let blocks = [];
  let baseFeeGwei = [];
  let blobFeeGwei = [];
  let MIN_BLOCK = 0;
  let MAX_BLOCK = 1;
  let HAS_BLOCK_TIME_ANCHOR = false;
  let BLOCK_TIME_APPROX_SECONDS = L1_BLOCK_TIME_SECONDS;
  let ANCHOR_BLOCK = 0;
  let ANCHOR_TIMESTAMP_SEC = 0;
  let TIME_ANCHOR_SOURCE = 'none';
  let datasetReady = false;
  const datasetRangeById = Object.create(null);

  const minInput = document.getElementById('minBlock');
  const maxInput = document.getElementById('maxBlock');
  const rangeText = document.getElementById('rangeText');
  const rangeDateText = document.getElementById('rangeDateText');
  const hoverText = document.getElementById('hoverText');
  const status = document.getElementById('status');
  const datasetRangeInput = document.getElementById('datasetRange');

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
  const pMinGweiInput = document.getElementById('pMinGwei');
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
  const healthWPostBEInput = document.getElementById('healthWPostBE');
  const uxWStdInput = document.getElementById('uxWStd');
  const uxWP95Input = document.getElementById('uxWP95');
  const uxWP99Input = document.getElementById('uxWP99');
  const uxWMaxStepInput = document.getElementById('uxWMaxStep');
  const uxWClampInput = document.getElementById('uxWClamp');
  const uxWLevelInput = document.getElementById('uxWLevel');

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
  const healthPostBreakEvenRatio = document.getElementById('healthPostBreakEvenRatio');
  const healthDeficitAreaBand = document.getElementById('healthDeficitAreaBand');
  const healthWorstDeficitStreak = document.getElementById('healthWorstDeficitStreak');
  const uxFeeStd = document.getElementById('uxFeeStd');
  const uxFeeStepP95 = document.getElementById('uxFeeStepP95');
  const uxFeeStepP99 = document.getElementById('uxFeeStepP99');
  const uxFeeStepMax = document.getElementById('uxFeeStepMax');
  const uxClampMaxRatio = document.getElementById('uxClampMaxRatio');
  const uxFeeLevelMean = document.getElementById('uxFeeLevelMean');
  const healthFormulaLine = document.getElementById('healthFormulaLine');
  const uxFormulaLine = document.getElementById('uxFormulaLine');
  const totalFormulaLine = document.getElementById('totalFormulaLine');
  const scoreBtn = document.getElementById('scoreBtn');
  const scoreStatus = document.getElementById('scoreStatus');
  const scoreHelpBtn = document.getElementById('scoreHelpBtn');
  const scoreHelpModal = document.getElementById('scoreHelpModal');
  const scoreHelpClose = document.getElementById('scoreHelpClose');
  const sweepBtn = document.getElementById('sweepBtn');
  const sweepCancelBtn = document.getElementById('sweepCancelBtn');
  const sweepApplyBestBtn = document.getElementById('sweepApplyBestBtn');
  const sweepStatus = document.getElementById('sweepStatus');
  const sweepSpinner = document.getElementById('sweepSpinner');
  const sweepBestMode = document.getElementById('sweepBestMode');
  const sweepBestAlphaVariant = document.getElementById('sweepBestAlphaVariant');
  const sweepBestKp = document.getElementById('sweepBestKp');
  const sweepBestKi = document.getElementById('sweepBestKi');
  const sweepBestImax = document.getElementById('sweepBestImax');
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
  const proposalPLWrap = document.getElementById('proposalPLPlot');
  const reqWrap = document.getElementById('requiredFeePlot');
  const chargedOnlyWrap = document.getElementById('chargedFeeOnlyPlot');
  const controllerWrap = document.getElementById('controllerPlot');
  const feedbackWrap = document.getElementById('feedbackPlot');
  const vaultWrap = document.getElementById('vaultPlot');
  const sweepWrap = document.getElementById('sweepPlot');

  function setStatus(msg) {
    status.textContent = msg || '';
  }

  function getDatasetMeta(datasetId) {
    if (!datasetId) return null;
    return DATASET_BY_ID[String(datasetId)] || null;
  }

  function selectedDatasetFromQuery() {
    try {
      const params = new URLSearchParams(window.location.search || '');
      const id = params.get('dataset');
      return id ? String(id) : null;
    } catch (e) {
      return null;
    }
  }

  function updateDatasetQuery(datasetId) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('dataset', String(datasetId));
      window.history.replaceState(null, '', url.toString());
    } catch (e) {
      // ignore URL update failures
    }
  }

  function setDatasetRangeOptions() {
    if (!datasetRangeInput) return;
    if (!DATASET_MANIFEST.length) {
      datasetRangeInput.innerHTML = '';
      return;
    }
    datasetRangeInput.innerHTML = DATASET_MANIFEST.map(function (meta) {
      const label = meta && meta.label ? String(meta.label) : String(meta.id);
      const id = meta && meta.id ? String(meta.id) : '';
      return `<option value="${id}">${label}</option>`;
    }).join('');
  }

  function ensureDatasetLoaded(datasetId) {
    const id = String(datasetId || '');
    if (!id) return Promise.reject(new Error('missing dataset id'));
    if (!window.__feeDatasetPayloads) window.__feeDatasetPayloads = Object.create(null);
    const cached = window.__feeDatasetPayloads[id];
    if (cached) return Promise.resolve(cached);

    const meta = getDatasetMeta(id);
    if (!meta || !meta.data_js) {
      return Promise.reject(new Error(`dataset metadata missing for "${id}"`));
    }

    const scriptSrc = String(meta.data_js);
    return new Promise(function (resolve, reject) {
      const tag = document.createElement('script');
      tag.src = scriptSrc;
      tag.async = true;
      tag.onload = function () {
        const payload = window.__feeDatasetPayloads && window.__feeDatasetPayloads[id];
        if (payload) resolve(payload);
        else reject(new Error(`dataset payload not found after loading "${scriptSrc}"`));
      };
      tag.onerror = function () {
        reject(new Error(`failed to load dataset script "${scriptSrc}"`));
      };
      document.head.appendChild(tag);
    });
  }

  async function activateDataset(datasetId, preserveRange = true) {
    const id = String(datasetId || '');
    const meta = getDatasetMeta(id);
    if (!meta) throw new Error(`unknown dataset "${id}"`);

    const prevActiveId = activeDatasetId;
    const prevRange = datasetReady ? clampRange(minInput.value, maxInput.value) : null;
    if (datasetReady && prevActiveId && prevRange) {
      datasetRangeById[prevActiveId] = [prevRange[0], prevRange[1]];
    }
    const payload = await ensureDatasetLoaded(id);
    const payloadBlocks = Array.isArray(payload.blocks) ? payload.blocks : [];
    const payloadBase = Array.isArray(payload.baseFeeGwei) ? payload.baseFeeGwei : [];
    const payloadBlob = Array.isArray(payload.blobFeeGwei) ? payload.blobFeeGwei : [];
    if (!payloadBlocks.length || payloadBase.length !== payloadBlocks.length || payloadBlob.length !== payloadBlocks.length) {
      throw new Error(`invalid dataset payload for "${id}"`);
    }

    blocks = payloadBlocks;
    baseFeeGwei = payloadBase;
    blobFeeGwei = payloadBlob;

    MIN_BLOCK = blocks[0];
    MAX_BLOCK = blocks[blocks.length - 1];

    const anchor = payload.timeAnchor || {};
    HAS_BLOCK_TIME_ANCHOR = Boolean(anchor.has_anchor);
    BLOCK_TIME_APPROX_SECONDS = Number(anchor.seconds_per_block);
    if (!Number.isFinite(BLOCK_TIME_APPROX_SECONDS) || BLOCK_TIME_APPROX_SECONDS <= 0) {
      BLOCK_TIME_APPROX_SECONDS = L1_BLOCK_TIME_SECONDS;
    }
    ANCHOR_BLOCK = Number.isFinite(Number(anchor.anchor_block)) ? Number(anchor.anchor_block) : MIN_BLOCK;
    ANCHOR_TIMESTAMP_SEC = Number.isFinite(Number(anchor.anchor_ts_sec)) ? Number(anchor.anchor_ts_sec) : 0;
    TIME_ANCHOR_SOURCE = anchor.source ? String(anchor.source) : 'none';

    activeDatasetId = id;
    if (datasetRangeInput) datasetRangeInput.value = id;
    updateDatasetQuery(id);

    let nextMin = MIN_BLOCK;
    let nextMax = MAX_BLOCK;
    if (preserveRange) {
      const savedRange = datasetRangeById[id];
      if (savedRange && savedRange.length === 2) {
        const clipped = clampRange(savedRange[0], savedRange[1]);
        nextMin = clipped[0];
        nextMax = clipped[1];
      } else if (prevRange) {
        const overlapMin = Math.max(prevRange[0], MIN_BLOCK);
        const overlapMax = Math.min(prevRange[1], MAX_BLOCK);
        if (overlapMin <= overlapMax) {
          const clipped = clampRange(overlapMin, overlapMax);
          nextMin = clipped[0];
          nextMax = clipped[1];
        }
      }
    }
    minInput.value = nextMin;
    maxInput.value = nextMax;

    if (basePlot) basePlot.setData([blocks, baseFeeGwei]);
    if (blobPlot) blobPlot.setData([blocks, blobFeeGwei]);

    datasetReady = true;
    markSweepStale('dataset changed');
    recalcDerivedSeries();
    applyRange(nextMin, nextMax, null);
    setStatus(`Loaded dataset: ${meta.label || id}`);
  }

  function resolveInitialDatasetId() {
    const fromQuery = selectedDatasetFromQuery();
    if (fromQuery && getDatasetMeta(fromQuery)) return fromQuery;
    const fromWindow = window.__feeInitialDatasetId ? String(window.__feeInitialDatasetId) : null;
    if (fromWindow && getDatasetMeta(fromWindow)) return fromWindow;
    if (DATASET_MANIFEST.length && DATASET_MANIFEST[0] && DATASET_MANIFEST[0].id) {
      return String(DATASET_MANIFEST[0].id);
    }
    return null;
  }

  function formatNum(x, frac = 4) {
    return Number(x).toLocaleString(undefined, { maximumFractionDigits: frac });
  }

  function clampRange(a, b) {
    let x = Number(a);
    let y = Number(b);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return [MIN_BLOCK, MAX_BLOCK];
    if (x > y) { const t = x; x = y; y = t; }
    x = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(x)));
    y = Math.max(MIN_BLOCK, Math.min(MAX_BLOCK, Math.floor(y)));
    if (x === y) y = Math.min(MAX_BLOCK, x + 1);
    return [x, y];
  }

  function blockToApproxUnixMs(blockNum) {
    if (!HAS_BLOCK_TIME_ANCHOR) return null;
    return (ANCHOR_TIMESTAMP_SEC + (blockNum - ANCHOR_BLOCK) * BLOCK_TIME_APPROX_SECONDS) * 1000;
  }

  function fmtApproxUtc(ms) {
    if (!Number.isFinite(ms)) return 'n/a';
    const iso = new Date(ms).toISOString();
    return `${iso.slice(0, 16).replace('T', ' ')} UTC`;
  }

  function fmtApproxSpan(msA, msB) {
    if (!Number.isFinite(msA) || !Number.isFinite(msB)) return 'n/a';
    const sec = Math.max(0, Math.round((msB - msA) / 1000));
    const days = Math.floor(sec / 86400);
    const hours = Math.floor((sec % 86400) / 3600);
    return `${days}d ${hours}h`;
  }

  function formatBlockWithApprox(blockNum) {
    if (!Number.isFinite(blockNum)) return '';
    const ms = blockToApproxUnixMs(blockNum);
    if (!Number.isFinite(ms)) return Number(blockNum).toLocaleString();
    return `${Number(blockNum).toLocaleString()} (~${fmtApproxUtc(ms)})`;
  }

  function updateRangeText(a, b) {
    rangeText.textContent = `Showing blocks ${a.toLocaleString()} - ${b.toLocaleString()} (${(b - a + 1).toLocaleString()} blocks)`;
    if (!rangeDateText) return;
    const msA = blockToApproxUnixMs(a);
    const msB = blockToApproxUnixMs(b);
    if (!Number.isFinite(msA) || !Number.isFinite(msB)) {
      rangeDateText.textContent = 'Approx UTC range unavailable (missing anchor timestamp).';
      return;
    }
    rangeDateText.textContent =
      `Approx UTC: ${fmtApproxUtc(msA)} → ${fmtApproxUtc(msB)} (${fmtApproxSpan(msA, msB)})` +
      `, using ~${BLOCK_TIME_APPROX_SECONDS.toFixed(2)}s/block (${TIME_ANCHOR_SOURCE})`;
  }

  function markScoreStale(reason) {
    if (!scoreStatus) return;
    const why = reason ? ` (${reason})` : '';
    scoreStatus.textContent = `Score is stale${why}. Click "Score current range" to compute.`;
  }

  function onSetCursor(u) {
    if (!hoverText) return;
    const idx = u && u.cursor ? u.cursor.idx : null;
    if (idx == null || idx < 0 || idx >= blocks.length) {
      hoverText.textContent = '';
      return;
    }
    const b = blocks[idx];
    const ms = blockToApproxUnixMs(b);
    if (!Number.isFinite(ms)) {
      hoverText.textContent = `Hover: block ${b.toLocaleString()}`;
      return;
    }
    hoverText.textContent = `Hover: block ${b.toLocaleString()} (~${fmtApproxUtc(ms)})`;
  }

  function getCurrentXRange() {
    for (const p of allPlots()) {
      if (!p || !p.scales || !p.scales.x) continue;
      const min = p.scales.x.min;
      const max = p.scales.x.max;
      if (Number.isFinite(min) && Number.isFinite(max)) return [min, max];
    }
    return null;
  }

  function parsePositive(inputEl, fallback) {
    const v = Number(inputEl.value);
    return Number.isFinite(v) && v >= 0 ? v : fallback;
  }

  function parsePositiveInt(inputEl, fallback) {
    const v = Number(inputEl.value);
    if (!Number.isFinite(v) || v < 1) return fallback;
    return Math.floor(v);
  }

  function parseNonNegativeInt(inputEl, fallback) {
    const v = Number(inputEl.value);
    if (!Number.isFinite(v) || v < 0) return fallback;
    return Math.floor(v);
  }

  function parseNumber(inputEl, fallback) {
    const v = Number(inputEl.value);
    return Number.isFinite(v) ? v : fallback;
  }

  function parseWeight(inputEl, fallback) {
    const v = Number(inputEl.value);
    return Number.isFinite(v) && v >= 0 ? v : fallback;
  }

  function lowerBound(arr, x) {
    let lo = 0;
    let hi = arr.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] < x) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  function upperBound(arr, x) {
    let lo = 0;
    let hi = arr.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] <= x) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  function percentile(values, p) {
    if (!values.length) return 0;
    const s = values.slice().sort(function (a, b) { return a - b; });
    const k = (s.length - 1) * (p / 100);
    const lo = Math.floor(k);
    const hi = Math.ceil(k);
    if (lo === hi) return s[lo];
    const w = k - lo;
    return s[lo] * (1 - w) + s[hi] * w;
  }

  function normalizedWeightedSum(values, weights) {
    let sumW = 0;
    let sum = 0;
    for (let i = 0; i < values.length; i++) {
      const w = Math.max(0, weights[i] || 0);
      sumW += w;
      sum += w * values[i];
    }
    return sumW > 0 ? (sum / sumW) : 0;
  }

  function getModeFlags(mode) {
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
    return { usesFeedforward, usesP, usesI, usesD };
  }

  function updateScorecard(minBlock, maxBlock, maxFeeGwei, targetVaultEth) {
    if (!derivedVaultEth.length || !derivedChargedFeeGwei.length) return;
    const i0 = lowerBound(blocks, minBlock);
    const i1 = upperBound(blocks, maxBlock) - 1;
    if (i0 < 0 || i1 < i0 || i1 >= blocks.length) return;

    const n = i1 - i0 + 1;
    if (n <= 0) return;

    const deadbandPct = parsePositive(deficitDeadbandPctInput, 5.0);
    const deadbandEth = targetVaultEth * (deadbandPct / 100);
    const feeScale = maxFeeGwei > 0 ? maxFeeGwei : 1;

    let maxDrawdownEth = 0;
    let underCount = 0;
    let deficitAreaBand = 0;
    let worstStreak = 0;
    let curStreak = 0;
    let postCount = 0;
    let postBreakEvenCount = 0;
    let clampMaxCount = 0;

    let feeSum = 0;
    let feeSqSum = 0;
    let breakEvenFeeSum = 0;
    let breakEvenFeeCount = 0;
    const feeSteps = [];
    let maxStep = 0;

    for (let i = i0; i <= i1; i++) {
      const target = derivedVaultTargetEth[i];
      const vault = derivedVaultEth[i];
      const gap = vault - target;
      const deficitEth = target - vault;

      if (gap < 0) {
        underCount += 1;
        curStreak += 1;
        if (curStreak > worstStreak) worstStreak = curStreak;
      } else {
        curStreak = 0;
      }

      maxDrawdownEth = Math.max(maxDrawdownEth, Math.max(0, -gap));
      deficitAreaBand += Math.max(0, deficitEth - deadbandEth);

      if (derivedClampState[i] === 'max') clampMaxCount += 1;
      const postBreakEven = derivedPostBreakEvenFlag[i];
      if (postBreakEven != null) {
        postCount += 1;
        if (postBreakEven) postBreakEvenCount += 1;
      }

      const fee = derivedChargedFeeGwei[i];
      feeSum += fee;
      feeSqSum += fee * fee;
      const breakEvenFee = derivedRequiredFeeGwei[i];
      if (breakEvenFee != null && Number.isFinite(breakEvenFee)) {
        breakEvenFeeSum += breakEvenFee;
        breakEvenFeeCount += 1;
      }
      if (i > i0) {
        const step = Math.abs(fee - derivedChargedFeeGwei[i - 1]);
        feeSteps.push(step);
        if (step > maxStep) maxStep = step;
      }
    }

    const feeMean = feeSum / n;
    const feeVar = Math.max(0, (feeSqSum / n) - feeMean * feeMean);
    const feeStd = Math.sqrt(feeVar);
    const stepP95 = percentile(feeSteps, 95);
    const stepP99 = percentile(feeSteps, 99);
    const clampMaxRatio = clampMaxCount / n;
    const breakEvenFeeMean = breakEvenFeeCount > 0 ? (breakEvenFeeSum / breakEvenFeeCount) : 0;
    const underTargetRatio = underCount / n;
    const postBreakEvenRatio = postCount > 0 ? (postBreakEvenCount / postCount) : 1;
    const dPost = 1 - postBreakEvenRatio;

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
    const uLevel = breakEvenFeeMean > 0
      ? Math.max(0, feeMean - breakEvenFeeMean) / breakEvenFeeMean
      : 0;

    const wDraw = parseWeight(healthWDrawInput, 0.35);
    const wUnder = parseWeight(healthWUnderInput, 0.25);
    const wArea = parseWeight(healthWAreaInput, 0.2);
    const wGap = parseWeight(healthWGapInput, 0.1);
    const wStreak = parseWeight(healthWStreakInput, 0.1);
    const wPostBE = parseWeight(healthWPostBEInput, 0.2);

    const wStd = parseWeight(uxWStdInput, 0.2);
    const wP95 = parseWeight(uxWP95Input, 0.2);
    const wP99 = parseWeight(uxWP99Input, 0.1);
    const wMax = parseWeight(uxWMaxStepInput, 0.05);
    const wClamp = parseWeight(uxWClampInput, 0.05);
    const wLevel = parseWeight(uxWLevelInput, 0.4);

    const wHealth = parseWeight(scoreWeightHealthInput, 0.75);
    const wUx = parseWeight(scoreWeightUxInput, 0.25);

    const healthBadness = normalizedWeightedSum(
      [dDraw, dUnder, dArea, dGap, dStreak, dPost],
      [wDraw, wUnder, wArea, wGap, wStreak, wPostBE]
    );
    const uxBadness = normalizedWeightedSum(
      [uStd, uP95, uP99, uMax, uClamp, uLevel],
      [wStd, wP95, wP99, wMax, wClamp, wLevel]
    );
    const totalBadness = normalizedWeightedSum([healthBadness, uxBadness], [wHealth, wUx]);

    scoreHealthBadness.textContent = formatNum(healthBadness, 6);
    scoreUxBadness.textContent = formatNum(uxBadness, 6);
    scoreTotalBadness.textContent = formatNum(totalBadness, 6);
    scoreWeightSummary.textContent =
      `overall weights: health=${formatNum(wHealth, 3)}, ux=${formatNum(wUx, 3)}`;

    healthMaxDrawdown.textContent = `${formatNum(maxDrawdownEth, 6)} ETH`;
    healthUnderTargetRatio.textContent = `${formatNum(underTargetRatio, 4)}`;
    healthAbsFinalGap.textContent = `${formatNum(absFinalGapEth, 6)} ETH`;
    healthPostBreakEvenRatio.textContent = `${formatNum(postBreakEvenRatio, 4)}`;
    healthDeficitAreaBand.textContent = `${formatNum(deficitAreaBand, 6)} ETH*block`;
    healthWorstDeficitStreak.textContent = `${formatNum(worstStreak, 0)} blocks`;

    uxFeeStd.textContent = `${formatNum(feeStd, 6)} gwei/L2gas`;
    uxFeeStepP95.textContent = `${formatNum(stepP95, 6)} gwei/L2gas`;
    uxFeeStepP99.textContent = `${formatNum(stepP99, 6)} gwei/L2gas`;
    uxFeeStepMax.textContent = `${formatNum(maxStep, 6)} gwei/L2gas`;
    uxClampMaxRatio.textContent = `${formatNum(clampMaxRatio, 4)}`;
    uxFeeLevelMean.textContent = `${formatNum(uLevel, 4)}`;

    healthFormulaLine.textContent =
      `health_badness = wDraw*dDraw + wUnder*dUnder + wArea*dArea + wGap*dGap + wStreak*dStreak + wPostBE*dPost ` +
      `(dDraw=${formatNum(dDraw, 4)}, dUnder=${formatNum(dUnder, 4)}, dArea=${formatNum(dArea, 4)}, dGap=${formatNum(dGap, 4)}, dStreak=${formatNum(dStreak, 4)}, dPost=${formatNum(dPost, 4)})`;
    uxFormulaLine.textContent =
      `ux_badness = wStd*uStd + wP95*uP95 + wP99*uP99 + wMax*uMax + wClamp*uClamp + wLevel*uLevel ` +
      `(uStd=${formatNum(uStd, 4)}, uP95=${formatNum(uP95, 4)}, uP99=${formatNum(uP99, 4)}, uMax=${formatNum(uMax, 4)}, uClamp=${formatNum(uClamp, 4)}, uLevel=${formatNum(uLevel, 4)})`;
    totalFormulaLine.textContent =
      `total_badness = wHealth*health_badness + wUx*ux_badness = ${formatNum(totalBadness, 6)} ` +
      `(deadband=${formatNum(deadbandPct, 2)}%, blocks=${n.toLocaleString()})`;

    if (scoreStatus) {
      scoreStatus.textContent =
        `Scored blocks ${blocks[i0].toLocaleString()}-${blocks[i1].toLocaleString()} ` +
        `(${n.toLocaleString()} blocks).`;
    }
  }

  function scoreCurrentRangeNow() {
    const [minB, maxB] = clampRange(minInput.value, maxInput.value);
    updateScorecard(
      minB,
      maxB,
      parsePositive(maxFeeGweiInput, 1.0),
      parsePositive(targetVaultEthInput, 10.0)
    );
  }

  function ensureFeedforwardDefaults() {
    const alphaGasNow = parsePositive(alphaGasInput, 0);
    const alphaBlobNow = parsePositive(alphaBlobInput, 0);
    if (!autoAlphaInput.checked && alphaGasNow === 0 && alphaBlobNow === 0) {
      alphaGasInput.value = DEFAULT_ALPHA_GAS.toFixed(6);
      alphaBlobInput.value = DEFAULT_ALPHA_BLOB.toFixed(6);
    }
  }

  function disableFeedforward() {
    autoAlphaInput.checked = false;
    alphaGasInput.value = '0';
    alphaBlobInput.value = '0';
  }

  function applyControllerModePreset(mode) {
    if (mode === 'alpha-only') {
      kpInput.value = '0';
      kiInput.value = '0';
      kdInput.value = '0';
      ensureFeedforwardDefaults();
      return;
    }

    if (mode === 'p') {
      disableFeedforward();
      kiInput.value = '0';
      kdInput.value = '0';
      return;
    }

    if (mode === 'pi') {
      disableFeedforward();
      kdInput.value = '0';
      return;
    }

    if (mode === 'pd') {
      disableFeedforward();
      kiInput.value = '0';
      return;
    }

    if (mode === 'pdi') {
      disableFeedforward();
      return;
    }

    if (mode === 'pi+ff') {
      kdInput.value = '0';
      ensureFeedforwardDefaults();
      return;
    }

    if (mode === 'pdi+ff') {
      ensureFeedforwardDefaults();
    }
  }

  function clampNum(x, lo, hi) {
    return Math.max(lo, Math.min(hi, x));
  }

  function makeRng(seed) {
    let s = seed >>> 0;
    return function () {
      s = (1664525 * s + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  function gaussian(rng) {
    const u1 = Math.max(1e-12, rng());
    const u2 = rng();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }

  function buildL2GasSeries(n, baseGasPerL1Block, scenario) {
    const out = new Array(n);
    if (scenario === 'constant') {
      for (let i = 0; i < n; i++) out[i] = baseGasPerL1Block;
      return out;
    }

    const cfg = scenario === 'steady'
      ? { rho: 0.97, sigma: 0.03, jumpProb: 0.0, jumpSigma: 0.0, lo: 0.75, hi: 1.35 }
      : scenario === 'bursty'
        ? { rho: 0.90, sigma: 0.16, jumpProb: 0.035, jumpSigma: 0.45, lo: 0.25, hi: 3.5 }
        : { rho: 0.94, sigma: 0.08, jumpProb: 0.01, jumpSigma: 0.20, lo: 0.45, hi: 2.0 }; // normal

    const rng = makeRng(0x1234abcd);
    let x = 0;
    for (let i = 0; i < n; i++) {
      x = cfg.rho * x + cfg.sigma * gaussian(rng);
      if (cfg.jumpProb > 0 && rng() < cfg.jumpProb) x += cfg.jumpSigma * gaussian(rng);
      const m = clampNum(Math.exp(x), cfg.lo, cfg.hi);
      out[i] = baseGasPerL1Block * m;
    }

    // Mean-neutralize scenario throughput so randomness adds volatility, not systematic bias.
    let sum = 0;
    for (let i = 0; i < n; i++) sum += out[i];
    const avg = n > 0 ? (sum / n) : baseGasPerL1Block;
    if (avg > 0) {
      const scale = baseGasPerL1Block / avg;
      for (let i = 0; i < n; i++) out[i] *= scale;
    }

    return out;
  }

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
  let derivedPostingRevenueAtPostEth = [];
  let derivedPostingPnLEth = [];
  let derivedPostingPnLBlocks = [];
  let derivedPostBreakEvenFlag = [];
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
  let sweepResults = [];
  let sweepCurrentPoint = null;
  let sweepRunSeq = 0;
  let sweepPoints = [];

  function setSweepUiState(running) {
    sweepRunning = running;
    if (sweepBtn) sweepBtn.disabled = running;
    if (sweepCancelBtn) sweepCancelBtn.disabled = !running;
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = running || !sweepBestCandidate;
    if (sweepSpinner) sweepSpinner.style.display = running ? 'inline-block' : 'none';
  }

  function setSweepStatus(msg) {
    if (sweepStatus) sweepStatus.textContent = msg || '';
  }

  function setSweepHoverText(msg) {
    if (!sweepHover) return;
    sweepHover.textContent = msg || 'Hover point: -';
  }

  function markSweepStale(reason) {
    if (sweepRunning) return;
    sweepBestCandidate = null;
    sweepResults = [];
    sweepCurrentPoint = null;
    sweepPoints = [];
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = true;
    if (sweepBestAlphaVariant) sweepBestAlphaVariant.textContent = '-';
    const why = reason ? ` (${reason})` : '';
    setSweepStatus(`Sweep stale${why}. Run parameter sweep to refresh.`);
    setSweepHoverText('Hover point: -');
    if (sweepPlot) sweepPlot.setData([[], [], [], []]);
  }

  function getSweepRangeIndices() {
    if (!datasetReady || !blocks.length) return null;
    const [minB, maxB] = clampRange(minInput.value, maxInput.value);
    const i0 = lowerBound(blocks, minB);
    const i1 = upperBound(blocks, maxB) - 1;
    if (i0 >= blocks.length || i1 < i0) return null;
    return { minB, maxB, i0, i1, n: i1 - i0 + 1 };
  }

  function parseScoringWeights() {
    return {
      deadbandPct: parseWeight(deficitDeadbandPctInput, 5.0),
      wHealth: parseWeight(scoreWeightHealthInput, 0.75),
      wUx: parseWeight(scoreWeightUxInput, 0.25),
      wDraw: parseWeight(healthWDrawInput, 0.35),
      wUnder: parseWeight(healthWUnderInput, 0.25),
      wArea: parseWeight(healthWAreaInput, 0.2),
      wGap: parseWeight(healthWGapInput, 0.1),
      wStreak: parseWeight(healthWStreakInput, 0.1),
      wPostBE: parseWeight(healthWPostBEInput, 0.2),
      wStd: parseWeight(uxWStdInput, 0.2),
      wP95: parseWeight(uxWP95Input, 0.2),
      wP99: parseWeight(uxWP99Input, 0.1),
      wMaxStep: parseWeight(uxWMaxStepInput, 0.05),
      wClamp: parseWeight(uxWClampInput, 0.05),
      wLevel: parseWeight(uxWLevelInput, 0.4)
    };
  }

  function buildSweepCandidates() {
    const out = [];
    for (const mode of SWEEP_MODES) {
      for (const kp of SWEEP_KP_VALUES) {
        for (const ki of SWEEP_KI_VALUES) {
          for (const kd of SWEEP_KD_VALUES) {
            for (const iMax of SWEEP_I_MAX_VALUES) {
              for (const alphaVariant of SWEEP_ALPHA_VARIANTS) {
                out.push({
                  mode,
                  alphaVariant,
                  kp,
                  ki,
                  kd,
                  iMax
                });
              }
            }
          }
        }
      }
    }
    return out;
  }

  function recalcDerivedSeries() {
    if (!datasetReady || !blocks.length) {
      setStatus('Loading dataset...');
      return;
    }
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
    const dffBlocks = parseNonNegativeInt(dffBlocksInput, 5);
    const dfbBlocks = parseNonNegativeInt(dfbBlocksInput, 5);
    const derivBeta = clampNum(parseNumber(dSmoothBetaInput, 0.8), 0, 1);
    const kp = parsePositive(kpInput, 0);
    const pTermMinGwei = parseNumber(pMinGweiInput, 0.0);
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
    if (autoAlphaEnabled) {
      alphaGasInput.value = autoAlphaGas.toFixed(6);
      alphaBlobInput.value = autoAlphaBlob.toFixed(6);
    }
    alphaGasInput.disabled = autoAlphaEnabled;
    alphaBlobInput.disabled = autoAlphaEnabled;
    const alphaGas = autoAlphaEnabled ? autoAlphaGas : parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS);
    const alphaBlob = autoAlphaEnabled ? autoAlphaBlob : parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB);

    const priorityFeeWei = priorityFeeGwei * 1e9;
    const pTermMinWei = pTermMinGwei * 1e9;
    const minFeeWei = minFeeGwei * 1e9;
    const maxFeeWei = Math.max(minFeeWei, maxFeeGwei * 1e9);
    const feeRangeWei = maxFeeWei - minFeeWei;
    const modeFlags = getModeFlags(controllerMode);
    const modeUsesFeedforward = modeFlags.usesFeedforward;
    const modeUsesP = modeFlags.usesP;
    const modeUsesI = modeFlags.usesI;
    const modeUsesD = modeFlags.usesD;

    derivedL2GasPerL1BlockText.textContent =
      `${formatNum(l2GasPerL1BlockBase, 0)} gas/L1 block (base), ` +
      `${formatNum(l2GasPerL1BlockTarget, 0)} gas/L1 block (target)`;
    derivedL2GasPerProposalText.textContent = `${formatNum(l2GasPerProposalBase, 0)} gas/proposal (base)`;

    const n = blocks.length;
    derivedL2GasPerL1Block = buildL2GasSeries(n, l2GasPerL1BlockTarget, l2GasScenario);
    derivedL2GasPerL1BlockBase = new Array(n).fill(l2GasPerL1BlockTarget);
    if (l2BlocksPerL1Block > 0) {
      derivedL2GasPerL2Block = derivedL2GasPerL1Block.map(function (x) {
        return x / l2BlocksPerL1Block;
      });
      derivedL2GasPerL2BlockBase = derivedL2GasPerL1BlockBase.map(function (x) {
        return x / l2BlocksPerL1Block;
      });
    } else {
      derivedL2GasPerL2Block = new Array(n).fill(0);
      derivedL2GasPerL2BlockBase = new Array(n).fill(0);
    }
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
    derivedPostingRevenueAtPostEth = new Array(n);
    derivedPostingPnLEth = new Array(n);
    derivedPostingPnLBlocks = [];
    derivedPostBreakEvenFlag = new Array(n);
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

    for (let i = 0; i < n; i++) {
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

      if (modeUsesI) {
        integralState = clampNum(integralState + epsilon, iMin, iMax);
      } else {
        integralState = 0;
      }

      const deRaw = i > 0 ? (epsilon - epsilonPrev) : 0;
      derivFiltered = derivBeta * derivFiltered + (1 - derivBeta) * deRaw;

      const pTermWeiRaw = modeUsesP ? (kp * epsilon * feeRangeWei) : 0;
      const pTermWei = modeUsesP ? Math.max(pTermMinWei, pTermWeiRaw) : 0;
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

      if (l2GasPerProposal_i > 0) {
        const breakEvenFeeWeiPerL2Gas = totalCostWei / l2GasPerProposal_i;
        derivedRequiredFeeGwei[i] = breakEvenFeeWeiPerL2Gas / 1e9;
      } else {
        derivedRequiredFeeGwei[i] = null;
      }

      const l2RevenueEthPerBlock =
        (chargedFeeWeiPerL2Gas * l2GasPerL1Block_i) / 1e18;
      // Post-time settlement: revenue is recognized only at posting blocks.
      pendingRevenueEth += l2RevenueEthPerBlock;

      // Fixed-cadence posting event: deduct fixed-resource posting cost at post blocks.
      const posted = ((i + 1) % postEveryBlocks) === 0;
      if (posted) {
        const postingRevenueEth = pendingRevenueEth;
        derivedPostingRevenueAtPostEth[i] = postingRevenueEth;
        derivedPostingPnLEth[i] = postingRevenueEth - derivedPostingCostEth[i];
        derivedPostingPnLBlocks.push(blocks[i]);
        derivedPostBreakEvenFlag[i] = postingRevenueEth + 1e-12 >= derivedPostingCostEth[i];
        vault += postingRevenueEth;
        pendingRevenueEth = 0;
        vault -= derivedPostingCostEth[i];
      } else {
        derivedPostingRevenueAtPostEth[i] = null;
        derivedPostingPnLEth[i] = null;
        derivedPostBreakEvenFlag[i] = null;
      }

      derivedVaultEth[i] = vault;
      derivedVaultTargetEth[i] = targetVaultEth;
      epsilonPrev = epsilon;
    }

    const preservedRange = getCurrentXRange();

    if (l2GasPlot && costPlot && proposalPLPlot && requiredFeePlot && chargedFeeOnlyPlot && controllerPlot && feedbackPlot && vaultPlot) {
      l2GasPlot.setData([blocks, derivedL2GasPerL2Block, derivedL2GasPerL2BlockBase]);
      costPlot.setData([blocks, derivedGasCostEth, derivedBlobCostEth, derivedPostingCostEth]);
      const proposalPnLValues = [];
      for (let i = 0; i < derivedPostingPnLEth.length; i++) {
        const v = derivedPostingPnLEth[i];
        if (v != null) proposalPnLValues.push(v);
      }
      proposalPLPlot.setData([
        derivedPostingPnLBlocks,
        proposalPnLValues,
        new Array(proposalPnLValues.length).fill(0)
      ]);
      requiredFeePlot.setData([
        blocks,
        derivedGasFeeComponentGwei,
        derivedBlobFeeComponentGwei,
        derivedChargedFeeGwei
      ]);
      chargedFeeOnlyPlot.setData([blocks, derivedChargedFeeGwei]);
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

      if (preservedRange) {
        applyRange(preservedRange[0], preservedRange[1], null);
      }
    }

    const lastIdx = n - 1;
    latestPostingCost.textContent = `${formatNum(derivedPostingCostEth[lastIdx], 6)} ETH`;
    if (derivedRequiredFeeGwei[lastIdx] == null || derivedChargedFeeGwei[lastIdx] == null) {
      latestRequiredFee.textContent = 'n/a';
      latestChargedFee.textContent = 'n/a';
      latestGasComponentFee.textContent = 'n/a';
      latestBlobComponentFee.textContent = 'n/a';
      latestL2GasUsed.textContent = 'n/a';
    } else {
      latestRequiredFee.textContent = `${formatNum(derivedRequiredFeeGwei[lastIdx], 4)} gwei/L2gas`;
      latestChargedFee.textContent = `${formatNum(derivedChargedFeeGwei[lastIdx], 4)} gwei/L2gas`;
      latestGasComponentFee.textContent = `${formatNum(derivedGasFeeComponentGwei[lastIdx], 4)} gwei/L2gas`;
      latestBlobComponentFee.textContent = `${formatNum(derivedBlobFeeComponentGwei[lastIdx], 4)} gwei/L2gas`;
      latestL2GasUsed.textContent = `${formatNum(derivedL2GasPerL2Block[lastIdx], 0)} gas/L2 block`;
    }
    latestDeficitEth.textContent = `${formatNum(derivedDeficitEth[lastIdx], 6)} ETH`;
    latestEpsilon.textContent = `${formatNum(derivedEpsilon[lastIdx], 6)}`;
    latestDerivative.textContent = `${formatNum(derivedDerivative[lastIdx], 6)}`;
    latestIntegral.textContent = `${formatNum(derivedIntegral[lastIdx], 6)}`;
    latestFfTerm.textContent = `${formatNum(derivedFeedforwardFeeGwei[lastIdx], 4)} gwei/L2gas`;
    latestDTerm.textContent = `${formatNum(derivedDTermFeeGwei[lastIdx], 4)} gwei/L2gas`;
    latestFbTerm.textContent = `${formatNum(derivedFeedbackFeeGwei[lastIdx], 4)} gwei/L2gas`;
    latestClampState.textContent = derivedClampState[lastIdx];
    latestVaultValue.textContent = `${formatNum(derivedVaultEth[lastIdx], 6)} ETH`;
    latestVaultGap.textContent = `${formatNum(derivedVaultEth[lastIdx] - targetVaultEth, 6)} ETH`;
    if (sweepResults.length) {
      const sweepRange = getSweepRangeIndices();
      if (sweepRange) {
        const sweepScoreCfg = parseScoringWeights();
        const sweepSimCfg = {
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
          pTermMinWei,
          initialVaultEth,
          targetVaultEth,
          alphaGas,
          alphaBlob,
          l2GasPerL1BlockSeries: derivedL2GasPerL1Block
        };
        sweepCurrentPoint = evaluateSweepCandidate(
          sweepRange.i0,
          sweepRange.i1,
          {
            mode: controllerMode,
            alphaVariant: 'current',
            alphaGas,
            alphaBlob,
            kp,
            ki,
            kd
          },
          sweepSimCfg,
          sweepScoreCfg
        );
      } else {
        sweepCurrentPoint = null;
      }
      renderSweepScatter(sweepResults, sweepBestCandidate, sweepCurrentPoint);
    }
    markScoreStale('recomputed charts');
  }

  function evaluateSweepCandidate(i0, i1, candidate, simCfg, scoreCfg) {
    const modeFlags = getModeFlags(candidate.mode);
    const candidateAlphaGas = Number.isFinite(candidate.alphaGas)
      ? Math.max(0, candidate.alphaGas)
      : Math.max(0, simCfg.alphaGas);
    const candidateAlphaBlob = Number.isFinite(candidate.alphaBlob)
      ? Math.max(0, candidate.alphaBlob)
      : Math.max(0, simCfg.alphaBlob);
    const candidateAlphaVariant = candidate.alphaVariant || 'current';
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
    let breakEvenFeeSum = 0;
    let breakEvenFeeCount = 0;
    let clampMaxCount = 0;
    let maxDrawdownEth = 0;
    let underTargetCount = 0;
    let deficitAreaBand = 0;
    let worstStreak = 0;
    let currentStreak = 0;
    let postCount = 0;
    let postBreakEvenCount = 0;

    for (let local = 0; local < n; local++) {
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
      const iMaxSweep = Number.isFinite(candidate.iMax) ? candidate.iMax : simCfg.iMax;
      if (modeFlags.usesI) {
        integralState = clampNum(integralState + epsilon, simCfg.iMin, iMaxSweep);
      } else {
        integralState = 0;
      }
      const deRaw = local > 0 ? (epsilon - epsilonPrev) : 0;
      derivFiltered =
        simCfg.derivBeta * derivFiltered + (1 - simCfg.derivBeta) * deRaw;

      const feedforwardWei = modeFlags.usesFeedforward
        ? (
            candidateAlphaGas * (baseFeeFfWei + simCfg.priorityFeeWei) +
            candidateAlphaBlob * blobBaseFeeFfWei
          )
        : 0;
      const pTermWeiRaw = modeFlags.usesP ? (candidate.kp * epsilon * simCfg.feeRangeWei) : 0;
      const pTermWei = modeFlags.usesP ? Math.max(simCfg.pTermMinWei, pTermWeiRaw) : 0;
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

      const l2GasPerProposal_i = simCfg.l2GasPerL1BlockSeries[i] * simCfg.postEveryBlocks;
      if (l2GasPerProposal_i > 0) {
        const breakEvenFeeWeiPerL2Gas = totalCostWei / l2GasPerProposal_i;
        breakEvenFeeSum += breakEvenFeeWeiPerL2Gas / 1e9;
        breakEvenFeeCount += 1;
      }

      const l2RevenueEthPerBlock =
        (chargedFeeWeiPerL2Gas * simCfg.l2GasPerL1BlockSeries[i]) / 1e18;
      pendingRevenueEth += l2RevenueEthPerBlock;

      const posted = ((i + 1) % simCfg.postEveryBlocks) === 0;
      if (posted) {
        const postingRevenueEth = pendingRevenueEth;
        if (postingRevenueEth + 1e-12 >= totalCostWei / 1e18) postBreakEvenCount += 1;
        postCount += 1;
        vault += postingRevenueEth;
        pendingRevenueEth = 0;
        vault -= totalCostWei / 1e18;
      }
      vaultSeries[local] = vault;

      // Keep health metric consistent with score card: max under-target gap.
      const gap = vault - simCfg.targetVaultEth;
      if (-gap > maxDrawdownEth) maxDrawdownEth = -gap;

      if (vault < simCfg.targetVaultEth) {
        underTargetCount += 1;
        currentStreak += 1;
        if (currentStreak > worstStreak) worstStreak = currentStreak;
      } else {
        currentStreak = 0;
      }

      if (vault < deadbandFloor) deficitAreaBand += (deadbandFloor - vault);
      epsilonPrev = epsilon;
    }

    const lastVault = vaultSeries[n - 1];
    const underTargetRatio = n > 0 ? (underTargetCount / n) : 0;
    const postBreakEvenRatio = postCount > 0 ? (postBreakEvenCount / postCount) : 1;
    const dPost = 1 - postBreakEvenRatio;
    const absFinalGapEth = Math.abs(lastVault - simCfg.targetVaultEth);
    const meanFee = feeCount > 0 ? (feeSum / feeCount) : 0;
    const variance = feeCount > 0 ? Math.max(0, (feeSumSq / feeCount) - meanFee * meanFee) : 0;
    const feeStd = Math.sqrt(variance);
    const stepP95 = percentile(feeSteps, 95);
    const stepP99 = percentile(feeSteps, 99);
    const maxStep = feeSteps.length ? Math.max.apply(null, feeSteps) : 0;
    const clampMaxRatio = n > 0 ? (clampMaxCount / n) : 0;
    const breakEvenFeeMean = breakEvenFeeCount > 0 ? (breakEvenFeeSum / breakEvenFeeCount) : 0;

    const dDraw = maxDrawdownEth / targetDenom;
    const dUnder = underTargetRatio;
    const dArea = deficitAreaBand / (targetDenom * n);
    const dGap = absFinalGapEth / targetDenom;
    const dStreak = n > 0 ? (worstStreak / n) : 0;
    const healthBadness = normalizedWeightedSum(
      [dDraw, dUnder, dArea, dGap, dStreak, dPost],
      [scoreCfg.wDraw, scoreCfg.wUnder, scoreCfg.wArea, scoreCfg.wGap, scoreCfg.wStreak, scoreCfg.wPostBE]
    );

    const uStd = feeStd / feeDenom;
    const uP95 = stepP95 / feeDenom;
    const uP99 = stepP99 / feeDenom;
    const uMax = maxStep / feeDenom;
    const uClamp = clampMaxRatio;
    const uLevel = breakEvenFeeMean > 0
      ? Math.max(0, meanFee - breakEvenFeeMean) / breakEvenFeeMean
      : 0;
    const uxBadness = normalizedWeightedSum(
      [uStd, uP95, uP99, uMax, uClamp, uLevel],
      [scoreCfg.wStd, scoreCfg.wP95, scoreCfg.wP99, scoreCfg.wMaxStep, scoreCfg.wClamp, scoreCfg.wLevel]
    );

    const totalBadness = normalizedWeightedSum(
      [healthBadness, uxBadness],
      [scoreCfg.wHealth, scoreCfg.wUx]
    );

    return {
      mode: candidate.mode,
      alphaVariant: candidateAlphaVariant,
      alphaGas: candidateAlphaGas,
      alphaBlob: candidateAlphaBlob,
      kp: candidate.kp,
      ki: candidate.ki,
      kd: candidate.kd,
      iMax: Number.isFinite(candidate.iMax) ? candidate.iMax : simCfg.iMax,
      nBlocks: n,
      healthBadness,
      uxBadness,
      totalBadness,
      maxDrawdownEth,
      underTargetRatio,
      postBreakEvenRatio,
      absFinalGapEth,
      feeStd,
      stepP95,
      stepP99,
      maxStep,
      clampMaxRatio,
      uLevel
    };
  }

  function renderSweepScatter(results, best, currentPoint) {
    if (!sweepPlot) return;
    const points = [];
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      const isBest = Boolean(
        best &&
        r.mode === best.mode &&
        r.alphaVariant === best.alphaVariant &&
        r.kp === best.kp &&
        r.ki === best.ki &&
        r.kd === best.kd &&
        r.iMax === best.iMax
      );
      points.push({
        ux: r.uxBadness,
        health: r.healthBadness,
        total: r.totalBadness,
        mode: r.mode,
        alphaVariant: r.alphaVariant || 'current',
        alphaGas: r.alphaGas,
        alphaBlob: r.alphaBlob,
        kp: r.kp,
        ki: r.ki,
        kd: r.kd,
        iMax: r.iMax,
        isBest,
        isCurrent: false
      });
    }
    if (
      currentPoint &&
      Number.isFinite(currentPoint.uxBadness) &&
      Number.isFinite(currentPoint.healthBadness)
    ) {
      points.push({
        ux: currentPoint.uxBadness,
        health: currentPoint.healthBadness,
        total: currentPoint.totalBadness,
        mode: currentPoint.mode,
        alphaVariant: currentPoint.alphaVariant || 'current',
        alphaGas: currentPoint.alphaGas,
        alphaBlob: currentPoint.alphaBlob,
        kp: currentPoint.kp,
        ki: currentPoint.ki,
        kd: currentPoint.kd,
        iMax: currentPoint.iMax,
        isBest: false,
        isCurrent: true
      });
    }
    points.sort(function (a, b) {
      if (a.ux !== b.ux) return a.ux - b.ux;
      return a.health - b.health;
    });

    const x = new Array(points.length);
    const allY = new Array(points.length);
    const bestY = new Array(points.length);
    const currentY = new Array(points.length);

    let xMin = Infinity;
    let xMax = -Infinity;
    let yMin = Infinity;
    let yMax = -Infinity;

    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      p.rank = i + 1;
      x[i] = p.ux;
      allY[i] = p.health;
      bestY[i] = p.isBest ? p.health : null;
      currentY[i] = p.isCurrent ? p.health : null;
      if (p.ux < xMin) xMin = p.ux;
      if (p.ux > xMax) xMax = p.ux;
      if (p.health < yMin) yMin = p.health;
      if (p.health > yMax) yMax = p.health;
    }

    sweepPoints = points;
    sweepPlot.setData([x, allY, bestY, currentY]);
    if (points.length) {
      const xSpan = Math.max(xMax - xMin, 1e-9);
      const ySpan = Math.max(yMax - yMin, 1e-9);
      const xPad = xSpan * 0.08;
      const yPad = ySpan * 0.08;
      sweepPlot.batch(function () {
        sweepPlot.setScale('x', { min: xMin - xPad, max: xMax + xPad });
        sweepPlot.setScale('y', { min: yMin - yPad, max: yMax + yPad });
      });
    }
  }

  function onSetSweepCursor(u) {
    const idx = u && u.cursor ? u.cursor.idx : null;
    if (idx == null || idx < 0 || idx >= sweepPoints.length) {
      setSweepHoverText('Hover point: -');
      return;
    }
    const p = sweepPoints[idx];
    if (!p) {
      setSweepHoverText('Hover point: -');
      return;
    }
    const rankPart = Number.isFinite(p.rank) ? `#${p.rank}` : '-';
    const tagParts = [];
    if (p.isBest) tagParts.push('best');
    if (p.isCurrent) tagParts.push('current');
    const tagText = tagParts.length ? ` (${tagParts.join(', ')})` : '';
    setSweepHoverText(
      `Hover point ${rankPart}${tagText}: mode=${p.mode}, alpha=${p.alphaVariant}, ` +
      `Kp=${formatNum(p.kp, 4)}, Ki=${formatNum(p.ki, 4)}, Kd=${formatNum(p.kd, 4)}, Imax=${formatNum(p.iMax, 4)}, ` +
      `health=${formatNum(p.health, 6)}, UX=${formatNum(p.ux, 6)}, total=${formatNum(p.total, 6)}`
    );
  }

  async function runParameterSweep() {
    if (sweepRunning) return;
    recalcDerivedSeries();

    const range = getSweepRangeIndices();
    if (!range) {
      setSweepStatus('Sweep failed: invalid selected range.');
      return;
    }
    if (range.n > SWEEP_MAX_BLOCKS) {
      setSweepStatus(
        `Sweep range too large (${range.n.toLocaleString()} blocks). ` +
        `Please zoom to <= ${SWEEP_MAX_BLOCKS.toLocaleString()} blocks.`
      );
      return;
    }

    const candidates = buildSweepCandidates();
    if (!candidates.length) {
      setSweepStatus('No sweep candidates configured.');
      return;
    }

    const postEveryBlocks = parsePositiveInt(postEveryBlocksInput, 10);
    const l1GasUsed = parsePositive(l1GasUsedInput, 0);
    const numBlobs = parsePositive(numBlobsInput, 0);
    const priorityFeeWei = parsePositive(priorityFeeGweiInput, 0) * 1e9;
    const dffBlocks = parseNonNegativeInt(dffBlocksInput, 5);
    const dfbBlocks = parseNonNegativeInt(dfbBlocksInput, 5);
    const derivBeta = clampNum(parseNumber(dSmoothBetaInput, 0.8), 0, 1);
    const pTermMinGwei = parseNumber(pMinGweiInput, 0.0);
    const iMinRaw = parseNumber(iMinInput, -5);
    const iMaxRaw = parseNumber(iMaxInput, 5);
    const iMin = Math.min(iMinRaw, iMaxRaw);
    const iMax = Math.max(iMinRaw, iMaxRaw);
    const minFeeWei = parsePositive(minFeeGweiInput, 0) * 1e9;
    const maxFeeGwei = parsePositive(maxFeeGweiInput, 1.0);
    const maxFeeWei = Math.max(minFeeWei, maxFeeGwei * 1e9);
    const pTermMinWei = pTermMinGwei * 1e9;
    const initialVaultEth = parsePositive(initialVaultEthInput, 0);
    const targetVaultEth = parsePositive(targetVaultEthInput, 0);
    const alphaGasFixed = parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS);
    const alphaBlobFixed = parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB);
    const scoreCfg = parseScoringWeights();
    const simCfg = {
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
      pTermMinWei,
      initialVaultEth,
      targetVaultEth,
      alphaGas: alphaGasFixed,
      alphaBlob: alphaBlobFixed,
      l2GasPerL1BlockSeries: derivedL2GasPerL1Block
    };

    sweepCancelRequested = false;
    const runId = ++sweepRunSeq;
    setSweepUiState(true);
    if (sweepCandidateCount) sweepCandidateCount.textContent = `${candidates.length} candidates`;
    if (sweepRangeCount) sweepRangeCount.textContent = `${range.n.toLocaleString()} blocks`;
    setSweepStatus(
      `Running sweep on blocks ${range.minB.toLocaleString()}-${range.maxB.toLocaleString()}...`
    );

    const started = performance.now();
    let lastYield = started;
    const results = [];
    setSweepHoverText('Hover point: -');
    for (let idx = 0; idx < candidates.length; idx++) {
      if (sweepCancelRequested || runId !== sweepRunSeq) break;
      const cand = candidates[idx];
      const useZeroAlpha = cand.alphaVariant === 'zero';
      const result = evaluateSweepCandidate(
        range.i0,
        range.i1,
        {
          mode: cand.mode,
          alphaVariant: cand.alphaVariant,
          alphaGas: useZeroAlpha ? 0 : alphaGasFixed,
          alphaBlob: useZeroAlpha ? 0 : alphaBlobFixed,
          kp: cand.kp,
          ki: cand.ki,
          kd: cand.kd,
          iMax: cand.iMax
        },
        simCfg,
        scoreCfg
      );
      results.push(result);

      if ((idx + 1) % 5 === 0 || idx + 1 === candidates.length) {
        setSweepStatus(
          `Sweep progress: ${(idx + 1).toLocaleString()} / ${candidates.length.toLocaleString()} candidates`
        );
        const now = performance.now();
        if (now - lastYield > 24) {
          await new Promise(function (resolve) { setTimeout(resolve, 0); });
          lastYield = performance.now();
        }
      }
    }

    if (runId !== sweepRunSeq) return;

    const elapsedSec = (performance.now() - started) / 1000;
    if (!results.length) {
      setSweepStatus('Sweep did not produce results.');
      setSweepHoverText('Hover point: -');
      setSweepUiState(false);
      return;
    }

    results.sort(function (a, b) {
      return a.totalBadness - b.totalBadness;
    });
    sweepResults = results;
    sweepCurrentPoint = null;
    sweepBestCandidate = results[0];
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = false;
    if (sweepBestMode) sweepBestMode.textContent = sweepBestCandidate.mode;
    if (sweepBestAlphaVariant) sweepBestAlphaVariant.textContent = sweepBestCandidate.alphaVariant || 'current';
    if (sweepBestKp) sweepBestKp.textContent = formatNum(sweepBestCandidate.kp, 4);
    if (sweepBestKi) sweepBestKi.textContent = formatNum(sweepBestCandidate.ki, 4);
    if (sweepBestImax) sweepBestImax.textContent = formatNum(sweepBestCandidate.iMax, 4);
    if (sweepBestHealth) sweepBestHealth.textContent = formatNum(sweepBestCandidate.healthBadness, 6);
    if (sweepBestUx) sweepBestUx.textContent = formatNum(sweepBestCandidate.uxBadness, 6);
    if (sweepBestTotal) sweepBestTotal.textContent = formatNum(sweepBestCandidate.totalBadness, 6);
    renderSweepScatter(sweepResults, sweepBestCandidate, sweepCurrentPoint);

    if (sweepCancelRequested) {
      setSweepStatus(
        `Sweep canceled after ${results.length.toLocaleString()} candidates in ${formatNum(elapsedSec, 2)}s.`
      );
    } else {
      setSweepStatus(
        `Sweep complete: ${results.length.toLocaleString()} candidates in ${formatNum(elapsedSec, 2)}s.`
      );
    }
    setSweepUiState(false);
  }

  function applySweepBestCandidate() {
    if (!sweepBestCandidate) return;
    controllerModeInput.value = sweepBestCandidate.mode;
    applyControllerModePreset(sweepBestCandidate.mode);
    if (sweepBestCandidate.alphaVariant === 'zero') {
      autoAlphaInput.checked = false;
      alphaGasInput.value = '0';
      alphaBlobInput.value = '0';
    } else if (Number.isFinite(sweepBestCandidate.alphaGas) && Number.isFinite(sweepBestCandidate.alphaBlob)) {
      autoAlphaInput.checked = false;
      alphaGasInput.value = `${sweepBestCandidate.alphaGas}`;
      alphaBlobInput.value = `${sweepBestCandidate.alphaBlob}`;
    }
    kpInput.value = `${sweepBestCandidate.kp}`;
    kiInput.value = `${sweepBestCandidate.ki}`;
    kdInput.value = `${sweepBestCandidate.kd}`;
    iMaxInput.value = `${sweepBestCandidate.iMax}`;
    recalcDerivedSeries();
    scoreCurrentRangeNow();
  }

  if (!window.uPlot) {
    setStatus('uPlot failed to load. Open this file from its folder so local JS files resolve.');
    return;
  }

  setStatus('Preparing charts...');

  let syncing = false;
  let basePlot;
  let blobPlot;
  let l2GasPlot;
  let costPlot;
  let proposalPLPlot;
  let requiredFeePlot;
  let chargedFeeOnlyPlot;
  let controllerPlot;
  let feedbackPlot;
  let vaultPlot;

  function allPlots() {
    return [
      basePlot,
      blobPlot,
      l2GasPlot,
      costPlot,
      proposalPLPlot,
      requiredFeePlot,
      chargedFeeOnlyPlot,
      controllerPlot,
      feedbackPlot,
      vaultPlot
    ].filter(Boolean);
  }

  function onSetScale(u, key) {
    if (key !== 'x' || syncing) return;
    const min = u.scales.x.min;
    const max = u.scales.x.max;
    applyRange(min, max, u);
  }

  function makeOpts(title, yLabel, strokeColor, width, height) {
    return {
      title,
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: title, stroke: strokeColor, width: 1 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: yLabel }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeCostOpts(width, height) {
    return {
      title: 'Hypothetical Posting Cost (if posted at this block)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        {
          label: 'Gas cost (ETH)',
          stroke: '#2563eb',
          width: 1,
          value: function (u, v) { return formatNum(v, 9); }
        },
        {
          label: 'Blob cost (ETH)',
          stroke: '#ea580c',
          width: 1,
          value: function (u, v) { return formatNum(v, 9); }
        },
        {
          label: 'Total cost (ETH)',
          stroke: '#7c3aed',
          width: 1.4,
          value: function (u, v) { return formatNum(v, 9); }
        }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'ETH' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeProposalPLOpts(width, height) {
    return {
      title: 'Per-Proposal P/L (revenue - posting cost)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        {
          label: 'Proposal P/L (ETH)',
          stroke: '#d97706',
          width: 0,
          points: { show: true, size: 4, stroke: '#b45309', fill: '#f59e0b' },
          value: function (u, v) { return formatNum(v, 9); }
        },
        {
          label: 'Break-even line (ETH)',
          stroke: '#64748b',
          width: 1,
          value: function (u, v) { return formatNum(v, 6); }
        }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'ETH / proposal' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeRequiredFeeOpts(width, height) {
    return {
      title: 'L2 Fee Components (feedforward + clamped total)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'Gas component fee (gwei/L2 gas)', stroke: '#2563eb', width: 1 },
        { label: 'Blob component fee (gwei/L2 gas)', stroke: '#ea580c', width: 1 },
        { label: 'Charged fee (clamped total)', stroke: '#16a34a', width: 1.4 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'gwei / L2 gas' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeChargedFeeOnlyOpts(width, height) {
    return {
      title: 'L2 Charged Fee (clamped total only)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'Charged fee (gwei/L2 gas)', stroke: '#16a34a', width: 1.4 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'gwei / L2 gas' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeVaultOpts(width, height) {
    return {
      title: 'Vault Value vs Target',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'Target vault (ETH)', stroke: '#dc2626', width: 1 },
        { label: 'Current vault (ETH)', stroke: '#0f766e', width: 1.4 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'ETH' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeControllerOpts(width, height) {
    return {
      title: 'Controller Components (Feedforward + P/I/D)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'FF term (gwei/L2 gas)', stroke: '#334155', width: 1.2 },
        { label: 'P term (gwei/L2 gas)', stroke: '#2563eb', width: 1.0 },
        { label: 'I term (gwei/L2 gas)', stroke: '#f59e0b', width: 1.0 },
        { label: 'D term (gwei/L2 gas)', stroke: '#ec4899', width: 1.0 },
        { label: 'FB total (gwei/L2 gas)', stroke: '#7c3aed', width: 1.0 },
        { label: 'Charged fee (gwei/L2 gas)', stroke: '#16a34a', width: 1.4 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'gwei / L2 gas' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeFeedbackOpts(width, height) {
    return {
      title: 'Feedback State (D, epsilon, dE, I)',
      width,
      height,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'Deficit D (ETH)', stroke: '#dc2626', width: 1.2 },
        { label: 'Normalized deficit epsilon', stroke: '#0891b2', width: 1.0 },
        { label: 'Filtered derivative dE_f', stroke: '#ec4899', width: 1.0 },
        { label: 'Integral I', stroke: '#7c2d12', width: 1.0 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'Mixed units' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    };
  }

  function makeSweepOpts(width, height) {
    return {
      title: 'Sweep Tradeoff: Health vs UX (lower is better)',
      width,
      height,
      scales: { x: {}, y: {} },
      series: [
        {
          value: function (u, v) {
            if (!Number.isFinite(v)) return '';
            return formatNum(v, 6);
          }
        },
        {
          label: 'Candidates (pdi/pdi+ff)',
          stroke: '#64748b',
          width: 0,
          points: { show: true, size: 4, stroke: '#64748b', fill: '#94a3b8' }
        },
        {
          label: 'Best weighted score',
          stroke: '#dc2626',
          width: 0,
          points: { show: true, size: 7, stroke: '#dc2626', fill: '#ef4444' }
        },
        {
          label: 'Current settings (last recompute)',
          stroke: '#ca8a04',
          width: 0,
          points: { show: true, size: 7, stroke: '#ca8a04', fill: '#facc15' }
        }
      ],
      axes: [
        {
          label: 'UX badness',
          values: function (u, vals) {
            return vals.map(function (v) { return formatNum(v, 4); });
          }
        },
        {
          label: 'Health badness',
          values: function (u, vals) {
            return vals.map(function (v) { return formatNum(v, 4); });
          }
        }
      ],
      cursor: {
        drag: { x: true, y: true, setScale: true }
      },
      hooks: {
        setCursor: [onSetSweepCursor]
      }
    };
  }

  function applyRange(minVal, maxVal, sourcePlot) {
    if (!datasetReady || !blocks.length) return;
    const [minB, maxB] = clampRange(minVal, maxVal);
    minInput.value = minB;
    maxInput.value = maxB;
    if (activeDatasetId) datasetRangeById[activeDatasetId] = [minB, maxB];
    updateRangeText(minB, maxB);

    syncing = true;
    for (const p of allPlots()) {
      if (p !== sourcePlot) p.setScale('x', { min: minB, max: maxB });
    }
    syncing = false;
    markScoreStale('range changed');
  }

  function resizePlots() {
    const width = Math.max(480, baseWrap.clientWidth - 8);
    for (const p of allPlots()) {
      p.setSize({ width, height: 320 });
    }
    if (sweepPlot) {
      const sweepSize = Math.min(width, 560);
      sweepPlot.setSize({ width: sweepSize, height: sweepSize });
    }
  }

  const width = Math.max(480, baseWrap.clientWidth - 8);
  const sweepSize = Math.min(width, 560);

  basePlot = new uPlot(
    makeOpts('L1 Base Fee', 'gwei', '#1d4ed8', width, 320),
    [[], []],
    baseWrap
  );

  blobPlot = new uPlot(
    makeOpts('L1 Blob Base Fee', 'gwei', '#ea580c', width, 320),
    [[], []],
    blobWrap
  );

  l2GasPlot = new uPlot(
    {
      title: 'L2 Gas Used (Scenario)',
      width,
      height: 320,
      scales: { x: { time: false } },
      series: [
        { value: function (u, v) { return formatBlockWithApprox(v); } },
        { label: 'L2 gas / L2 block (scenario)', stroke: '#0f766e', width: 1.4 },
        { label: 'L2 gas / L2 block (target)', stroke: '#94a3b8', width: 1.0 }
      ],
      axes: [
        { label: 'L1 Block Number' },
        { label: 'gas / L2 block' }
      ],
      cursor: {
        drag: { x: true, y: false, setScale: true }
      },
      hooks: {
        setScale: [onSetScale],
        setCursor: [onSetCursor]
      }
    },
    [[], [], []],
    l2GasWrap
  );

  costPlot = new uPlot(
    makeCostOpts(width, 320),
    [[], [], [], []],
    costWrap
  );

  proposalPLPlot = new uPlot(
    makeProposalPLOpts(width, 320),
    [[], [], []],
    proposalPLWrap
  );

  requiredFeePlot = new uPlot(
    makeRequiredFeeOpts(width, 320),
    [[], [], [], []],
    reqWrap
  );

  chargedFeeOnlyPlot = new uPlot(
    makeChargedFeeOnlyOpts(width, 320),
    [[], []],
    chargedOnlyWrap
  );

  controllerPlot = new uPlot(
    makeControllerOpts(width, 320),
    [[], [], [], [], [], [], []],
    controllerWrap
  );

  feedbackPlot = new uPlot(
    makeFeedbackOpts(width, 320),
    [[], [], [], [], []],
    feedbackWrap
  );

  vaultPlot = new uPlot(
    makeVaultOpts(width, 320),
    [[], [], []],
    vaultWrap
  );

  sweepPlot = new uPlot(
    makeSweepOpts(sweepSize, sweepSize),
    [[], [], [], []],
    sweepWrap
  );

  setSweepUiState(false);
  setSweepStatus('Sweep idle. Sweeps Kp/Ki/Imax across pdi + pdi+ff with Kd fixed at 0 and alpha variants (current, zero).');
  setSweepHoverText('Hover point: -');
  minInput.value = '';
  maxInput.value = '';
  if (rangeText) rangeText.textContent = 'Loading dataset...';
  if (rangeDateText) rangeDateText.textContent = '';

  document.getElementById('applyBtn').addEventListener('click', function () {
    applyRange(minInput.value, maxInput.value, null);
  });

  document.getElementById('resetBtn').addEventListener('click', function () {
    applyRange(MIN_BLOCK, MAX_BLOCK, null);
  });

  document.getElementById('tail20kBtn').addEventListener('click', function () {
    applyRange(MAX_BLOCK - 20000, MAX_BLOCK, null);
  });

  document.getElementById('tail5kBtn').addEventListener('click', function () {
    applyRange(MAX_BLOCK - 5000, MAX_BLOCK, null);
  });

  document.getElementById('recalcBtn').addEventListener('click', recalcDerivedSeries);

  if (scoreBtn) {
    scoreBtn.addEventListener('click', function () {
      if (scoreStatus) scoreStatus.textContent = 'Scoring current range...';
      window.setTimeout(function () {
        scoreCurrentRangeNow();
      }, 0);
    });
  }

  function setScoreHelpOpen(isOpen) {
    if (!scoreHelpModal) return;
    if (isOpen) {
      scoreHelpModal.classList.add('open');
      scoreHelpModal.setAttribute('aria-hidden', 'false');
    } else {
      scoreHelpModal.classList.remove('open');
      scoreHelpModal.setAttribute('aria-hidden', 'true');
    }
  }

  if (scoreHelpBtn && scoreHelpModal) {
    scoreHelpBtn.addEventListener('click', function () {
      setScoreHelpOpen(true);
    });
    if (scoreHelpClose) {
      scoreHelpClose.addEventListener('click', function () {
        setScoreHelpOpen(false);
      });
    }
    scoreHelpModal.addEventListener('click', function (e) {
      if (e.target === scoreHelpModal) {
        setScoreHelpOpen(false);
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && scoreHelpModal.classList.contains('open')) {
        setScoreHelpOpen(false);
      }
    });
  }

  if (sweepBtn) {
    sweepBtn.addEventListener('click', function () {
      runParameterSweep();
    });
  }

  if (sweepCancelBtn) {
    sweepCancelBtn.addEventListener('click', function () {
      if (!sweepRunning) return;
      sweepCancelRequested = true;
      setSweepStatus('Cancel requested. Finishing current candidate...');
    });
  }

  if (sweepApplyBestBtn) {
    sweepApplyBestBtn.addEventListener('click', function () {
      applySweepBestCandidate();
    });
  }

  controllerModeInput.addEventListener('change', function () {
    applyControllerModePreset(controllerModeInput.value || 'alpha-only');
    recalcDerivedSeries();
  });

  minInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  });

  maxInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') applyRange(minInput.value, maxInput.value, null);
  });

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
    pMinGweiInput,
    kiInput,
    kdInput,
    iMinInput,
    iMaxInput,
    minFeeGweiInput,
    maxFeeGweiInput,
    initialVaultEthInput,
    targetVaultEthInput
  ].forEach(function (el) {
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') recalcDerivedSeries();
    });
    el.addEventListener('change', recalcDerivedSeries);
  });

  [
    deficitDeadbandPctInput,
    scoreWeightHealthInput,
    scoreWeightUxInput,
    healthWDrawInput,
    healthWUnderInput,
    healthWAreaInput,
    healthWGapInput,
    healthWStreakInput,
    healthWPostBEInput,
    uxWStdInput,
    uxWP95Input,
    uxWP99Input,
    uxWMaxStepInput,
    uxWClampInput,
    uxWLevelInput
  ].forEach(function (el) {
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        markScoreStale('score settings changed');
      }
    });
    el.addEventListener('change', function () {
      markScoreStale('score settings changed');
    });
  });

  let resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizePlots, 120);
  });

  if (datasetRangeInput) {
    datasetRangeInput.addEventListener('change', async function () {
      const nextId = datasetRangeInput.value ? String(datasetRangeInput.value) : '';
      if (!nextId || nextId === activeDatasetId) return;
      try {
        setStatus(`Switching dataset to "${nextId}"...`);
        await activateDataset(nextId, true);
      } catch (err) {
        setStatus(`Dataset switch failed: ${err && err.message ? err.message : err}`);
      }
    });
  }

  async function initDatasets() {
    setDatasetRangeOptions();
    const initialId = resolveInitialDatasetId();
    if (!initialId) {
      setStatus('No dataset configured. Regenerate with --dataset entries.');
      return;
    }
    try {
      setStatus(`Loading dataset "${initialId}"...`);
      await activateDataset(initialId, false);
    } catch (err) {
      setStatus(`Dataset load failed: ${err && err.message ? err.message : err}`);
    }
  }

  markScoreStale('not computed yet');
  initDatasets();
})();
