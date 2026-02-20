(function () {
  const BLOB_GAS_PER_BLOB = 131072;
  const ERC20_TRANSFER_GAS = 70000;
  const L1_BLOCK_TIME_SECONDS = 12;
  const DEFAULT_FEE_MECHANISM = "taiko";
  const DEFAULT_BLOB_MODE = "dynamic";
  const DEFAULT_TX_GAS = 70000;
  const DEFAULT_TX_BYTES = 120;
  const DEFAULT_BATCH_OVERHEAD_BYTES = 1200;
  const DEFAULT_COMPRESSION_RATIO = 1;
  const DEFAULT_BLOB_UTILIZATION = 0.95;
  const DEFAULT_MIN_BLOBS_PER_PROPOSAL = 1;
  const DEFAULT_ALPHA_GAS = 0;
  const DEFAULT_ALPHA_BLOB = 0;
  const DEFAULT_EIP1559_DENOMINATOR = 8;
  const DEFAULT_ARB_INITIAL_PRICE_GWEI = 0.001000000000;
  const DEFAULT_ARB_INERTIA = 10;
  const DEFAULT_ARB_EQUIL_UNITS = 96000000;
  const TPS_PRESETS = Object.freeze([0.5, 1, 2, 5, 10, 20, 50, 100, 200]);
  const DEMAND_MULTIPLIERS = Object.freeze({ low: 0.7, base: 1.0, high: 1.4 });
  const SWEEP_MODES = Object.freeze(['pdi', 'pdi+ff']);
  const SWEEP_ALPHA_VARIANTS = Object.freeze(['current', 'zero']);
  const SWEEP_KP_VALUES = Object.freeze([0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6]);
  const SWEEP_KI_VALUES = Object.freeze([0.0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.2, 0.5, 1.0]);
  const SWEEP_KD_VALUES = Object.freeze([0.0]);
  const SWEEP_I_MAX_VALUES = Object.freeze([5.0, 10.0, 100.0]);
  const SWEEP_MAX_BLOCKS = 200000;
  const MAX_SAVED_RUNS = 6;
  const SAVED_RUNS_STORAGE_KEY = 'fee_history_interactive_saved_runs_v1';
  const SAVED_RUN_COLORS = Object.freeze([
    '#0ea5e9',
    '#f97316',
    '#a855f7',
    '#22c55e',
    '#e11d48',
    '#14b8a6'
  ]);
  const simCore = window.FeeSimCore || null;
  const DATASET_MANIFEST = (window.__feeDatasetManifest && Array.isArray(window.__feeDatasetManifest.datasets))
    ? window.__feeDatasetManifest.datasets.slice()
    : [];
  const DATASET_BY_ID = Object.create(null);
  for (const meta of DATASET_MANIFEST) {
    if (meta && meta.id) DATASET_BY_ID[String(meta.id)] = meta;
  }
  const RANGE_PRESETS = (window.__feeRangePresets && Array.isArray(window.__feeRangePresets))
    ? window.__feeRangePresets.slice()
    : [];
  const RANGE_PRESET_BY_ID = Object.create(null);
  for (const item of RANGE_PRESETS) {
    if (!item || item.id == null) continue;
    const id = String(item.id);
    const datasetId = item.dataset_id == null ? '' : String(item.dataset_id);
    const minBlock = Number(item.min_block);
    const maxBlock = Number(item.max_block);
    if (!datasetId || !Number.isFinite(minBlock) || !Number.isFinite(maxBlock)) continue;
    RANGE_PRESET_BY_ID[id] = {
      id,
      label: item.label == null ? id : String(item.label),
      dataset_id: datasetId,
      min_block: Math.floor(Math.min(minBlock, maxBlock)),
      max_block: Math.floor(Math.max(minBlock, maxBlock)),
    };
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
  const busySpinner = document.getElementById('busySpinner');
  const busyOverlay = document.getElementById('busyOverlay');
  const datasetRangeInput = document.getElementById('datasetRange');
  const rangePresetInput = document.getElementById('rangePreset');
  const paramsCard = document.getElementById('paramsCard');
  const paramsDirtyHint = document.getElementById('paramsDirtyHint');

  const postEveryBlocksInput = document.getElementById('postEveryBlocks');
  const l2GasPerL2BlockInput = document.getElementById('l2GasPerL2Block');
  const l2TpsInput = document.getElementById('l2Tps');
  const l2BlockTimeSecInput = document.getElementById('l2BlockTimeSec');
  const l2GasScenarioInput = document.getElementById('l2GasScenario');
  const l2DemandRegimeInput = document.getElementById('l2DemandRegime');
  const l1GasUsedInput = document.getElementById('l1GasUsed');
  const blobModeInput = document.getElementById('blobMode');
  const blobFixedLabel = document.getElementById('blobFixedLabel');
  const blobEstimateLabel = document.getElementById('blobEstimateLabel');
  const numBlobsEstimatedInput = document.getElementById('numBlobsEstimated');
  const blobDynamicGroup = document.getElementById('blobDynamicGroup');
  const numBlobsInput = document.getElementById('numBlobs');
  const txGasInput = document.getElementById('txGas');
  const txBytesInput = document.getElementById('txBytes');
  const batchOverheadBytesInput = document.getElementById('batchOverheadBytes');
  const compressionRatioInput = document.getElementById('compressionRatio');
  const blobUtilizationInput = document.getElementById('blobUtilization');
  const minBlobsPerProposalInput = document.getElementById('minBlobsPerProposal');
  const priorityFeeGweiInput = document.getElementById('priorityFeeGwei');
  const feeMechanismInput = document.getElementById('feeMechanism');
  const taikoParamsGroup = document.getElementById('taikoParamsGroup');
  const eip1559ParamsGroup = document.getElementById('eip1559ParamsGroup');
  const arbitrumParamsGroup = document.getElementById('arbitrumParamsGroup');
  const eip1559DenominatorInput = document.getElementById('eip1559Denominator');
  const autoAlphaInput = document.getElementById('autoAlpha');
  const alphaGasInput = document.getElementById('alphaGas');
  const alphaBlobInput = document.getElementById('alphaBlob');
  const controllerModeInput = document.getElementById('controllerMode');
  const arbInitialPriceGweiInput = document.getElementById('arbInitialPriceGwei');
  const arbInertiaInput = document.getElementById('arbInertia');
  const arbEquilUnitsInput = document.getElementById('arbEquilUnits');
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
  const scoreCard = document.getElementById('scoreCard');
  const controllerHelpBtn = document.getElementById('controllerHelpBtn');
  const controllerHelpModal = document.getElementById('controllerHelpModal');
  const controllerHelpClose = document.getElementById('controllerHelpClose');
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
  const saveRunBtn = document.getElementById('saveRunBtn');
  const toggleCurrentRunBtn = document.getElementById('toggleCurrentRunBtn');
  const recomputeSavedRunsBtn = document.getElementById('recomputeSavedRunsBtn');
  const updateAssumptionsRecomputeSavedRunsBtn = document.getElementById('updateAssumptionsRecomputeSavedRunsBtn');
  const clearSavedRunsBtn = document.getElementById('clearSavedRunsBtn');
  const savedRunsStatus = document.getElementById('savedRunsStatus');
  const savedRunsActionText = document.getElementById('savedRunsActionText');
  const savedRunsList = document.getElementById('savedRunsList');

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

  let uiBusyCount = 0;
  let recalcPending = false;
  let recalcNeedsRerun = false;
  let paramsDirty = false;

  function setUiBusy(active) {
    uiBusyCount += active ? 1 : -1;
    if (uiBusyCount < 0) uiBusyCount = 0;
    const show = uiBusyCount > 0;
    if (busySpinner) busySpinner.style.display = show ? 'inline-block' : 'none';
    if (busyOverlay) busyOverlay.style.display = show ? 'inline-flex' : 'none';
  }

  function clearParamsStale() {
    paramsDirty = false;
    if (paramsCard) paramsCard.classList.remove('stale');
    if (paramsDirtyHint) paramsDirtyHint.textContent = '';
  }

  function markParamsStale(reason) {
    paramsDirty = true;
    if (paramsCard) paramsCard.classList.add('stale');
    if (paramsDirtyHint) paramsDirtyHint.textContent = 'Stale: click Recompute derived charts';
    updateBlobEstimatePreview();
    markScoreStale('parameter change pending recompute');
    markSweepStale('parameter change pending recompute');
    if (reason) setStatus(reason);
  }

  function scheduleRecalc(statusMsg = 'Recomputing derived charts...') {
    setStatus(statusMsg);
    if (recalcPending) {
      recalcNeedsRerun = true;
      return;
    }
    recalcPending = true;
    setUiBusy(true);

    function runOnce() {
      try {
        recalcDerivedSeries();
        clearParamsStale();
      } finally {
        if (recalcNeedsRerun) {
          recalcNeedsRerun = false;
          window.setTimeout(runOnce, 0);
        } else {
          recalcPending = false;
          setUiBusy(false);
        }
      }
    }

    window.setTimeout(runOnce, 0);
  }

  function runBusyUiTask(statusMsg, task) {
    if (statusMsg) setStatus(statusMsg);
    setUiBusy(true);
    window.setTimeout(function () {
      try {
        task();
      } finally {
        setUiBusy(false);
      }
    }, 0);
  }

  function runAsyncUiTask(statusMsg, task) {
    if (statusMsg) setStatus(statusMsg);
    setUiBusy(true);
    window.setTimeout(async function () {
      try {
        await task();
      } finally {
        setUiBusy(false);
      }
    }, 0);
  }

  function setStatus(msg) {
    status.textContent = msg || '';
  }

  if (!simCore) {
    setStatus('Simulation core failed to load. Ensure fee_history_sim_core.js is served.');
    return;
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

  function selectedRangeFromQuery() {
    try {
      const params = new URLSearchParams(window.location.search || '');
      const minRaw = params.get('min');
      const maxRaw = params.get('max');
      if (minRaw == null || maxRaw == null) return null;
      const minVal = Number(minRaw);
      const maxVal = Number(maxRaw);
      if (!Number.isFinite(minVal) || !Number.isFinite(maxVal)) return null;
      return { min: minVal, max: maxVal };
    } catch (e) {
      return null;
    }
  }

  function updateUrlQueryState(datasetId, minBlock = null, maxBlock = null) {
    try {
      const url = new URL(window.location.href);
      if (datasetId != null && datasetId !== '') {
        url.searchParams.set('dataset', String(datasetId));
      } else {
        url.searchParams.delete('dataset');
      }
      if (Number.isFinite(minBlock) && Number.isFinite(maxBlock)) {
        url.searchParams.set('min', String(Math.trunc(minBlock)));
        url.searchParams.set('max', String(Math.trunc(maxBlock)));
      } else {
        url.searchParams.delete('min');
        url.searchParams.delete('max');
      }
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

  function getRangePresetMeta(presetId) {
    if (!presetId) return null;
    return RANGE_PRESET_BY_ID[String(presetId)] || null;
  }

  function setRangePresetOptions() {
    if (!rangePresetInput) return;

    const grouped = Object.create(null);
    for (const item of RANGE_PRESETS) {
      const preset = getRangePresetMeta(item && item.id);
      if (!preset) continue;
      if (!getDatasetMeta(preset.dataset_id)) continue;
      const key = preset.dataset_id;
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(preset);
    }

    const datasetOrder = DATASET_MANIFEST
      .map(function (meta) { return meta && meta.id ? String(meta.id) : ''; })
      .filter(Boolean);

    const fragments = ['<option value="">Custom / manual range</option>'];
    for (const datasetId of datasetOrder) {
      const presets = grouped[datasetId];
      if (!presets || !presets.length) continue;
      const meta = getDatasetMeta(datasetId);
      const groupLabel = htmlEscape((meta && meta.label) ? String(meta.label) : datasetId);
      fragments.push(`<optgroup label="${groupLabel}">`);
      for (const preset of presets) {
        const blocks = `${preset.min_block.toLocaleString()}-${preset.max_block.toLocaleString()}`;
        fragments.push(
          `<option value="${htmlEscape(preset.id)}">${htmlEscape(preset.label)} [${blocks}]</option>`
        );
      }
      fragments.push('</optgroup>');
    }
    rangePresetInput.innerHTML = fragments.join('');
    rangePresetInput.disabled = fragments.length <= 1;
    rangePresetInput.value = '';
  }

  function refreshRangePresetSelection() {
    if (!rangePresetInput) return;
    if (!activeDatasetId || !datasetReady) {
      rangePresetInput.value = '';
      return;
    }
    const curMin = Number(minInput.value);
    const curMax = Number(maxInput.value);
    if (!Number.isFinite(curMin) || !Number.isFinite(curMax)) {
      rangePresetInput.value = '';
      return;
    }
    const minB = Math.trunc(Math.min(curMin, curMax));
    const maxB = Math.trunc(Math.max(curMin, curMax));
    for (const item of RANGE_PRESETS) {
      const preset = getRangePresetMeta(item && item.id);
      if (!preset) continue;
      if (preset.dataset_id === activeDatasetId && preset.min_block === minB && preset.max_block === maxB) {
        rangePresetInput.value = preset.id;
        return;
      }
    }
    rangePresetInput.value = '';
  }

  async function applyRangePresetById(presetId) {
    const preset = getRangePresetMeta(presetId);
    if (!preset) return;

    if (preset.dataset_id !== activeDatasetId) {
      await activateDataset(preset.dataset_id, false);
    }

    applyRange(preset.min_block, preset.max_block, null);
    if (rangePresetInput) rangePresetInput.value = preset.id;
    setStatus(`Applied representative range: ${preset.label}`);
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
    setUiBusy(true);
    try {
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

      let nextMin = MIN_BLOCK;
      let nextMax = MAX_BLOCK;
      const queryDatasetId = selectedDatasetFromQuery();
      const queryRange = queryDatasetId === id ? selectedRangeFromQuery() : null;
      if (preserveRange) {
        const savedRange = datasetRangeById[id];
        if (savedRange && savedRange.length === 2) {
          const clipped = clampRange(savedRange[0], savedRange[1]);
          nextMin = clipped[0];
          nextMax = clipped[1];
        } else if (queryRange) {
          const clipped = clampRange(queryRange.min, queryRange.max);
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
      } else {
        if (queryRange) {
          const clipped = clampRange(queryRange.min, queryRange.max);
          nextMin = clipped[0];
          nextMax = clipped[1];
        }
      }
      minInput.value = nextMin;
      maxInput.value = nextMax;

      if (basePlot) basePlot.setData([blocks, baseFeeGwei]);
      if (blobPlot) blobPlot.setData([blocks, blobFeeGwei]);

      datasetReady = true;
      markSweepStale('dataset changed');
      recalcDerivedSeries();
      clearParamsStale();
      applyRange(nextMin, nextMax, null);
      if (savedRunManager.hasRuns()) {
        rerunSavedRunsForCurrentRange();
        renderSavedRunsList();
        refreshComparisonPlots();
      }
      setStatus(`Loaded dataset: ${meta.label || id}`);
    } finally {
      setUiBusy(false);
    }
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

  function formatFeeGwei(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return 'n/a';
    const abs = Math.abs(n);
    if (abs > 0 && abs < 1e-4) return `${formatNum(n, 9)} gwei/L2gas`;
    if (abs > 0 && abs < 1e-2) return `${formatNum(n, 6)} gwei/L2gas`;
    return `${formatNum(n, 4)} gwei/L2gas`;
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
    if (scoreCard) scoreCard.classList.add('stale');
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
    const v = Number(inputEl && inputEl.value);
    return Number.isFinite(v) && v >= 0 ? v : fallback;
  }

  function parsePositiveInt(inputEl, fallback) {
    const v = Number(inputEl && inputEl.value);
    if (!Number.isFinite(v) || v < 1) return fallback;
    return Math.floor(v);
  }

  function parseNonNegativeInt(inputEl, fallback) {
    const v = Number(inputEl && inputEl.value);
    if (!Number.isFinite(v) || v < 0) return fallback;
    return Math.floor(v);
  }

  function parseNumber(inputEl, fallback) {
    const v = Number(inputEl && inputEl.value);
    return Number.isFinite(v) ? v : fallback;
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

  function htmlEscape(raw) {
    return String(raw)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function currentBlobMode() {
    if (!blobModeInput) return DEFAULT_BLOB_MODE;
    return blobModeInput.value === 'dynamic' ? 'dynamic' : 'fixed';
  }

  function parseBlobModelInputs() {
    const txGas = Math.max(1, parsePositive(txGasInput, DEFAULT_TX_GAS));
    const txBytes = parsePositive(txBytesInput, DEFAULT_TX_BYTES);
    const batchOverheadBytes = parsePositive(batchOverheadBytesInput, DEFAULT_BATCH_OVERHEAD_BYTES);
    const compressionRatio = Math.max(1e-9, parsePositive(compressionRatioInput, DEFAULT_COMPRESSION_RATIO));
    const blobUtilization = clampNum(
      parsePositive(blobUtilizationInput, DEFAULT_BLOB_UTILIZATION),
      1e-9,
      1
    );
    const minBlobsPerProposal = parsePositive(
      minBlobsPerProposalInput,
      DEFAULT_MIN_BLOBS_PER_PROPOSAL
    );
    return {
      txGas,
      txBytes,
      batchOverheadBytes,
      compressionRatio,
      blobUtilization,
      minBlobsPerProposal
    };
  }

  function normalizeFeeMechanism(raw) {
    if (raw === 'arbitrum') return 'arbitrum';
    if (raw === 'eip1559') return 'eip1559';
    return 'taiko';
  }

  function normalizeBlobModel(rawLike) {
    const raw = rawLike || {};
    return {
      txGas: Math.max(1, Number(raw.txGas) || DEFAULT_TX_GAS),
      txBytes: Math.max(0, Number(raw.txBytes) || DEFAULT_TX_BYTES),
      batchOverheadBytes: Math.max(0, Number(raw.batchOverheadBytes) || DEFAULT_BATCH_OVERHEAD_BYTES),
      compressionRatio: Math.max(1e-9, Number(raw.compressionRatio) || DEFAULT_COMPRESSION_RATIO),
      blobUtilization: clampNum(Number(raw.blobUtilization) || DEFAULT_BLOB_UTILIZATION, 1e-9, 1),
      minBlobsPerProposal: Math.max(0, Number(raw.minBlobsPerProposal) || DEFAULT_MIN_BLOBS_PER_PROPOSAL),
    };
  }

  function normalizeRunParams(rawLike) {
    const raw = rawLike || {};
    const mechanism = normalizeFeeMechanism(raw.feeMechanism);
    const blobMode = raw.blobMode === 'dynamic' ? 'dynamic' : 'fixed';
    const blobModel = normalizeBlobModel(raw.blobModel);
    const minFeeGwei = Math.max(0, Number(raw.minFeeGwei) || 0.01);
    const maxFeeGwei = Math.max(minFeeGwei, Number(raw.maxFeeGwei) || 1.0);
    const iMinRaw = Number(raw.iMin);
    const iMaxRaw = Number(raw.iMax);
    const iMin = Number.isFinite(iMinRaw) ? iMinRaw : 0;
    const iMax = Number.isFinite(iMaxRaw) ? iMaxRaw : 10;
    const dffRaw = Number(raw.dffBlocks);
    const dfbRaw = Number(raw.dfbBlocks);
    const eipCfg = raw.eip1559 || {};
    const arbCfg = raw.arbitrum || {};
    return {
      postEveryBlocks: Math.max(1, Math.floor(Number(raw.postEveryBlocks) || 10)),
      l2GasPerL2Block: Math.max(0, Number(raw.l2GasPerL2Block) || 0),
      l2Tps: Number.isFinite(Number(raw.l2Tps)) ? Math.max(0, Number(raw.l2Tps)) : NaN,
      l2BlockTimeSec: Math.max(0.1, Number(raw.l2BlockTimeSec) || 2),
      l2GasScenario: raw.l2GasScenario || 'normal',
      l2DemandRegime: raw.l2DemandRegime || 'base',
      l1GasUsed: Math.max(0, Number(raw.l1GasUsed) || 0),
      blobMode,
      fixedNumBlobs: Math.max(0, Number(raw.fixedNumBlobs) || 0),
      blobModel,
      priorityFeeGwei: Math.max(0, Number(raw.priorityFeeGwei) || 0),
      feeMechanism: mechanism,
      controllerMode: raw.controllerMode || 'ff',
      autoAlphaEnabled: raw.autoAlphaEnabled === true,
      alphaGas: Math.max(0, Number(raw.alphaGas) || 0),
      alphaBlob: Math.max(0, Number(raw.alphaBlob) || 0),
      kp: Math.max(0, Number(raw.kp) || 0),
      pTermMinGwei: Number(raw.pTermMinGwei) || 0,
      ki: Math.max(0, Number(raw.ki) || 0),
      kd: Math.max(0, Number(raw.kd) || 0),
      iMin: Math.min(iMin, iMax),
      iMax: Math.max(iMin, iMax),
      dffBlocks: Number.isFinite(dffRaw) ? Math.max(0, Math.floor(dffRaw)) : 5,
      dfbBlocks: Number.isFinite(dfbRaw) ? Math.max(1, Math.floor(dfbRaw)) : 5,
      derivBeta: clampNum(Number.isFinite(Number(raw.derivBeta)) ? Number(raw.derivBeta) : 0.8, 0, 1),
      minFeeGwei,
      maxFeeGwei,
      initialVaultEth: Math.max(0, Number(raw.initialVaultEth) || 0),
      targetVaultEth: Math.max(0, Number(raw.targetVaultEth) || 0),
      eip1559: {
        maxChangeDenominator: Math.max(
          1,
          Math.floor(Number(eipCfg.maxChangeDenominator) || DEFAULT_EIP1559_DENOMINATOR)
        )
      },
      arbitrum: {
        initialPriceGwei: Math.max(0, Number(arbCfg.initialPriceGwei) || DEFAULT_ARB_INITIAL_PRICE_GWEI),
        inertia: Math.max(1, Math.floor(Number(arbCfg.inertia) || DEFAULT_ARB_INERTIA)),
        equilUnits: Math.max(1, Number(arbCfg.equilUnits) || DEFAULT_ARB_EQUIL_UNITS),
      }
    };
  }

  function deriveDemandScalars(runParams) {
    const demandMultiplier = DEMAND_MULTIPLIERS[runParams.l2DemandRegime] || 1.0;
    const l2BlocksPerL1Block = runParams.l2BlockTimeSec > 0
      ? (L1_BLOCK_TIME_SECONDS / runParams.l2BlockTimeSec)
      : 0;
    const l2GasPerL1BlockBase = runParams.l2GasPerL2Block * l2BlocksPerL1Block;
    const l2GasPerL1BlockTarget = l2GasPerL1BlockBase * demandMultiplier;
    const l2GasPerProposalBase = l2GasPerL1BlockBase * runParams.postEveryBlocks;
    return {
      demandMultiplier,
      l2BlocksPerL1Block,
      l2GasPerL1BlockBase,
      l2GasPerL1BlockTarget,
      l2GasPerProposalBase,
    };
  }

  function buildCoreControllerConfig(runParams) {
    const minFeeWei = runParams.minFeeGwei * 1e9;
    const maxFeeWei = Math.max(minFeeWei, runParams.maxFeeGwei * 1e9);
    return {
      mechanism: runParams.feeMechanism,
      controllerMode: runParams.controllerMode,
      postEveryBlocks: runParams.postEveryBlocks,
      l1GasUsed: runParams.l1GasUsed,
      blobMode: runParams.blobMode,
      fixedNumBlobs: runParams.fixedNumBlobs,
      blobModel: runParams.blobModel,
      priorityFeeWei: runParams.priorityFeeGwei * 1e9,
      dffBlocks: runParams.dffBlocks,
      dfbBlocks: runParams.dfbBlocks,
      derivBeta: runParams.derivBeta,
      kp: runParams.kp,
      ki: runParams.ki,
      kd: runParams.kd,
      pTermMinWei: runParams.pTermMinGwei * 1e9,
      iMin: runParams.iMin,
      iMax: runParams.iMax,
      minFeeWei,
      maxFeeWei,
      alphaGas: runParams.alphaGas,
      alphaBlob: runParams.alphaBlob,
      initialVaultEth: runParams.initialVaultEth,
      targetVaultEth: runParams.targetVaultEth,
      eip1559Denominator: runParams.eip1559.maxChangeDenominator,
      arbInitialPriceGwei: runParams.arbitrum.initialPriceGwei,
      arbInertia: runParams.arbitrum.inertia,
      arbEquilUnits: runParams.arbitrum.equilUnits,
    };
  }

  function estimateDynamicBlobs(l2GasPerProposal, blobModel) {
    return simCore.estimateDynamicBlobs(l2GasPerProposal, blobModel);
  }

  function updateBlobEstimatePreview() {
    if (!numBlobsEstimatedInput) return;
    if (currentBlobMode() !== 'dynamic') {
      numBlobsEstimatedInput.value = '-';
      return;
    }

    const postEveryBlocks = parsePositiveInt(postEveryBlocksInput, 10);
    const l2GasPerL2Block = parsePositive(l2GasPerL2BlockInput, 0);
    const l2BlockTimeSec = parsePositive(l2BlockTimeSecInput, 2);
    const l2DemandRegime = l2DemandRegimeInput ? (l2DemandRegimeInput.value || 'base') : 'base';
    const demandMultiplier = DEMAND_MULTIPLIERS[l2DemandRegime] || 1.0;
    const l2BlocksPerL1Block = l2BlockTimeSec > 0 ? (L1_BLOCK_TIME_SECONDS / l2BlockTimeSec) : 0;
    const l2GasPerL1BlockBase = l2GasPerL2Block * l2BlocksPerL1Block;
    const l2GasPerL1BlockTarget = l2GasPerL1BlockBase * demandMultiplier;
    const l2GasPerProposal = l2GasPerL1BlockTarget * postEveryBlocks;
    const blobModel = parseBlobModelInputs();
    const estimated = estimateDynamicBlobs(l2GasPerProposal, blobModel);
    numBlobsEstimatedInput.value = formatNum(estimated, 2);
  }

  function computeScoredMetrics({
    chargedFeeSeries,
    vaultSeries,
    requiredFeeSeries,
    clampStateSeries,
    postBreakEvenSeries,
    targetSeries = null,
    targetVaultEth,
    maxFeeGwei,
    deadbandPct,
    scoreCfg,
    i0,
    i1,
    skipNullSeries = false,
    fallbackTargetDenomToOne = false,
  }) {
    const start = Math.floor(Number(i0));
    const end = Math.floor(Number(i1));
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
    const n = end - start + 1;
    if (n <= 0) return null;

    const targetVault = Number.isFinite(Number(targetVaultEth)) ? Number(targetVaultEth) : 0;
    const feeScale = Number(maxFeeGwei) > 0 ? Number(maxFeeGwei) : 1;
    const deadbandFrac = Number(deadbandPct) / 100;

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
    let feeCount = 0;
    let breakEvenFeeSum = 0;
    let breakEvenFeeCount = 0;
    const feeSteps = [];
    let maxStep = 0;
    let feePrev = null;

    for (let i = start; i <= end; i++) {
      const fee = chargedFeeSeries[i];
      const vault = vaultSeries[i];
      if (skipNullSeries && (fee == null || vault == null)) continue;

      const targetRaw = targetSeries ? targetSeries[i] : targetVault;
      const target = Number.isFinite(Number(targetRaw)) ? Number(targetRaw) : targetVault;
      const gap = vault - target;
      const deadbandFloor = target * (1 - deadbandFrac);

      if (vault < deadbandFloor) {
        underCount += 1;
        curStreak += 1;
        if (curStreak > worstStreak) worstStreak = curStreak;
      } else {
        curStreak = 0;
      }

      maxDrawdownEth = Math.max(maxDrawdownEth, Math.max(0, -gap));
      deficitAreaBand += Math.max(0, deadbandFloor - vault);

      if (clampStateSeries[i] === 'max') clampMaxCount += 1;
      const postBreakEven = postBreakEvenSeries[i];
      if (postBreakEven != null) {
        postCount += 1;
        if (postBreakEven) postBreakEvenCount += 1;
      }

      feeSum += fee;
      feeSqSum += fee * fee;
      feeCount += 1;
      const breakEvenFee = requiredFeeSeries[i];
      if (breakEvenFee != null && Number.isFinite(breakEvenFee)) {
        breakEvenFeeSum += breakEvenFee;
        breakEvenFeeCount += 1;
      }

      if (feePrev != null) {
        const step = Math.abs(fee - feePrev);
        feeSteps.push(step);
        if (step > maxStep) maxStep = step;
      }
      feePrev = fee;
    }

    const feeStatsCount = skipNullSeries ? feeCount : n;
    const feeMean = feeStatsCount > 0 ? (feeSum / feeStatsCount) : 0;
    const feeVar = feeStatsCount > 0 ? Math.max(0, (feeSqSum / feeStatsCount) - feeMean * feeMean) : 0;
    const feeStd = Math.sqrt(feeVar);
    const stepP95 = percentile(feeSteps, 95);
    const stepP99 = percentile(feeSteps, 99);
    const clampMaxRatio = clampMaxCount / n;
    const breakEvenFeeMean = breakEvenFeeCount > 0 ? (breakEvenFeeSum / breakEvenFeeCount) : 0;
    const underTargetRatio = underCount / n;
    const postBreakEvenRatio = postCount > 0 ? (postBreakEvenCount / postCount) : 1;
    const dPost = 1 - postBreakEvenRatio;

    const targetDenom = targetVault > 0 ? targetVault : (fallbackTargetDenomToOne ? 1 : 0);
    const dDraw = targetDenom > 0 ? (maxDrawdownEth / targetDenom) : 0;
    const dUnder = underTargetRatio;
    const dArea = targetDenom > 0 ? (deficitAreaBand / (targetDenom * n)) : 0;
    const dStreak = n > 0 ? (worstStreak / n) : 0;

    const uStd = feeStd / feeScale;
    const uP95 = stepP95 / feeScale;
    const uP99 = stepP99 / feeScale;
    const uMax = maxStep / feeScale;
    const uClamp = clampMaxRatio;
    const uLevel = breakEvenFeeMean > 0
      ? Math.max(0, feeMean - breakEvenFeeMean) / breakEvenFeeMean
      : 0;

    const healthBadness = normalizedWeightedSum(
      [dDraw, dUnder, dArea, dStreak, dPost],
      [scoreCfg.wDraw, scoreCfg.wUnder, scoreCfg.wArea, scoreCfg.wStreak, scoreCfg.wPostBE]
    );
    const uxBadness = normalizedWeightedSum(
      [uStd, uP95, uP99, uMax, uClamp, uLevel],
      [scoreCfg.wStd, scoreCfg.wP95, scoreCfg.wP99, scoreCfg.wMaxStep, scoreCfg.wClamp, scoreCfg.wLevel]
    );
    const totalBadness = normalizedWeightedSum(
      [healthBadness, uxBadness],
      [scoreCfg.wHealth, scoreCfg.wUx]
    );

    return {
      n,
      deadbandPct,
      maxDrawdownEth,
      underTargetRatio,
      postBreakEvenRatio,
      deficitAreaBand,
      worstStreak,
      feeStd,
      stepP95,
      stepP99,
      maxStep,
      clampMaxRatio,
      uLevel,
      dDraw,
      dUnder,
      dArea,
      dStreak,
      dPost,
      uStd,
      uP95,
      uP99,
      uMax,
      uClamp,
      healthBadness,
      uxBadness,
      totalBadness,
    };
  }

  function updateScorecard(minBlock, maxBlock, maxFeeGwei, targetVaultEth) {
    if (!derivedVaultEth.length || !derivedChargedFeeGwei.length) return null;
    const i0 = lowerBound(blocks, minBlock);
    const i1 = upperBound(blocks, maxBlock) - 1;
    if (i0 < 0 || i1 < i0 || i1 >= blocks.length) return null;

    const scoreCfg = parseScoringWeights();
    const metrics = computeScoredMetrics({
      chargedFeeSeries: derivedChargedFeeGwei,
      vaultSeries: derivedVaultEth,
      requiredFeeSeries: derivedRequiredFeeGwei,
      clampStateSeries: derivedClampState,
      postBreakEvenSeries: derivedPostBreakEvenFlag,
      targetSeries: derivedVaultTargetEth,
      targetVaultEth,
      maxFeeGwei,
      deadbandPct: scoreCfg.deadbandPct,
      scoreCfg,
      i0,
      i1,
      skipNullSeries: false,
      fallbackTargetDenomToOne: false,
    });
    if (!metrics) return null;

    scoreHealthBadness.textContent = formatNum(metrics.healthBadness, 6);
    scoreUxBadness.textContent = formatNum(metrics.uxBadness, 6);
    scoreTotalBadness.textContent = formatNum(metrics.totalBadness, 6);
    scoreWeightSummary.textContent =
      `overall weights: health=${formatNum(scoreCfg.wHealth, 3)}, ux=${formatNum(scoreCfg.wUx, 3)}`;

    healthMaxDrawdown.textContent = `${formatNum(metrics.maxDrawdownEth, 6)} ETH`;
    healthUnderTargetRatio.textContent = `${formatNum(metrics.underTargetRatio, 4)}`;
    healthPostBreakEvenRatio.textContent = `${formatNum(metrics.postBreakEvenRatio, 4)}`;
    healthDeficitAreaBand.textContent = `${formatNum(metrics.deficitAreaBand, 6)} ETH*block`;
    healthWorstDeficitStreak.textContent = `${formatNum(metrics.worstStreak, 0)} blocks`;

    uxFeeStd.textContent = `${formatNum(metrics.feeStd, 6)} gwei/L2gas`;
    uxFeeStepP95.textContent = `${formatNum(metrics.stepP95, 6)} gwei/L2gas`;
    uxFeeStepP99.textContent = `${formatNum(metrics.stepP99, 6)} gwei/L2gas`;
    uxFeeStepMax.textContent = `${formatNum(metrics.maxStep, 6)} gwei/L2gas`;
    uxClampMaxRatio.textContent = `${formatNum(metrics.clampMaxRatio, 4)}`;
    uxFeeLevelMean.textContent = `${formatNum(metrics.uLevel, 4)}`;

    healthFormulaLine.textContent =
      `health_badness = wDraw*dDraw + wUnder*dUnder + wArea*dArea + wStreak*dStreak + wPostBE*dPost ` +
      `(dDraw=${formatNum(metrics.dDraw, 4)}, dUnder=${formatNum(metrics.dUnder, 4)}, dArea=${formatNum(metrics.dArea, 4)}, dStreak=${formatNum(metrics.dStreak, 4)}, dPost=${formatNum(metrics.dPost, 4)})`;
    uxFormulaLine.textContent =
      `ux_badness = wStd*uStd + wP95*uP95 + wP99*uP99 + wMax*uMax + wClamp*uClamp + wLevel*uLevel ` +
      `(uStd=${formatNum(metrics.uStd, 4)}, uP95=${formatNum(metrics.uP95, 4)}, uP99=${formatNum(metrics.uP99, 4)}, uMax=${formatNum(metrics.uMax, 4)}, uClamp=${formatNum(metrics.uClamp, 4)}, uLevel=${formatNum(metrics.uLevel, 4)})`;
    totalFormulaLine.textContent =
      `total_badness = wHealth*health_badness + wUx*ux_badness = ${formatNum(metrics.totalBadness, 6)} ` +
      `(deadband=${formatNum(metrics.deadbandPct, 2)}%, blocks=${metrics.n.toLocaleString()})`;

    if (scoreStatus) {
      scoreStatus.textContent =
        `Scored blocks ${blocks[i0].toLocaleString()}-${blocks[i1].toLocaleString()} ` +
        `(${metrics.n.toLocaleString()} blocks).`;
    }
    if (scoreCard) scoreCard.classList.remove('stale');
    return {
      i0,
      i1,
      n: metrics.n,
      healthBadness: metrics.healthBadness,
      uxBadness: metrics.uxBadness,
      totalBadness: metrics.totalBadness
    };
  }

  function scoreCurrentRangeNow() {
    const mechanism = currentFeeMechanism();
    const [minB, maxB] = clampRange(minInput.value, maxInput.value);
    const score = updateScorecard(
      minB,
      maxB,
      parsePositive(maxFeeGweiInput, 1.0),
      parsePositive(targetVaultEthInput, 10.0)
    );
    if (!score) return;

    sweepScoredHistory.push({
      uxBadness: score.uxBadness,
      healthBadness: score.healthBadness,
      totalBadness: score.totalBadness,
      mode: mechanism === 'taiko'
        ? (controllerModeInput.value || 'ff')
        : (mechanism === 'eip1559' ? 'eip1559' : 'arbitrum'),
      alphaVariant: mechanism === 'taiko' ? (autoAlphaInput.checked ? 'auto' : 'current') : 'n/a',
      alphaGas: parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS),
      alphaBlob: parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB),
      kp: parsePositive(kpInput, 0),
      ki: parsePositive(kiInput, 0),
      kd: parsePositive(kdInput, 0),
      iMax: parseNumber(iMaxInput, 0),
      scoredRangeMin: minB,
      scoredRangeMax: maxB
    });
    if (sweepScoredHistory.length > 256) sweepScoredHistory.shift();

    renderSweepScatter(sweepResults, sweepBestCandidate, sweepCurrentPoint, sweepScoredHistory);
  }

  function ensureFeedforwardDefaults() {
    const alphaGasNow = parsePositive(alphaGasInput, 0);
    const alphaBlobNow = parsePositive(alphaBlobInput, 0);
    if (!autoAlphaInput.checked && alphaGasNow === 0 && alphaBlobNow === 0) {
      alphaGasInput.value = DEFAULT_ALPHA_GAS.toFixed(6);
      alphaBlobInput.value = DEFAULT_ALPHA_BLOB.toFixed(6);
    }
  }

  function syncAutoAlphaInputs() {
    const autoAlphaEnabled = autoAlphaInput.checked;
    alphaGasInput.disabled = autoAlphaEnabled;
    alphaBlobInput.disabled = autoAlphaEnabled;
    if (!autoAlphaEnabled) ensureFeedforwardDefaults();
  }

  function syncBlobModeUi() {
    const mode = currentBlobMode();
    const dynamic = mode === 'dynamic';
    if (blobFixedLabel) blobFixedLabel.classList.toggle('hidden', dynamic);
    if (blobEstimateLabel) blobEstimateLabel.classList.toggle('hidden', !dynamic);
    if (blobDynamicGroup) blobDynamicGroup.classList.toggle('hidden', !dynamic);
    if (numBlobsInput) {
      numBlobsInput.disabled = dynamic;
      numBlobsInput.title = dynamic ? 'Disabled when Blob model = dynamic' : '';
    }
    updateBlobEstimatePreview();
  }

  function currentFeeMechanism() {
    if (!feeMechanismInput) return DEFAULT_FEE_MECHANISM;
    if (feeMechanismInput.value === 'arbitrum') return 'arbitrum';
    if (feeMechanismInput.value === 'eip1559') return 'eip1559';
    return 'taiko';
  }

  function syncFeeMechanismUi() {
    const mechanism = currentFeeMechanism();
    if (taikoParamsGroup) taikoParamsGroup.classList.toggle('hidden', mechanism !== 'taiko');
    if (eip1559ParamsGroup) eip1559ParamsGroup.classList.toggle('hidden', mechanism !== 'eip1559');
    if (arbitrumParamsGroup) arbitrumParamsGroup.classList.toggle('hidden', mechanism !== 'arbitrum');
    if (mechanism === 'taiko') {
      syncAutoAlphaInputs();
    } else {
      alphaGasInput.disabled = true;
      alphaBlobInput.disabled = true;
    }
  }

  function disableFeedforward() {
    autoAlphaInput.checked = false;
    alphaGasInput.value = '0';
    alphaBlobInput.value = '0';
    syncAutoAlphaInputs();
  }

  function applyControllerModePreset(mode) {
    if (mode === 'ff') {
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

  function getTpsCustomOption() {
    if (!l2TpsInput) return null;
    return l2TpsInput.querySelector('option[value="custom"]');
  }

  function setCustomTpsLabel(tps) {
    const customOpt = getTpsCustomOption();
    if (!customOpt) return;
    const safeTps = Number.isFinite(tps) ? Math.max(0, tps) : 0;
    customOpt.textContent = `custom (${formatNum(safeTps, 3)} tps)`;
    customOpt.dataset.tps = String(safeTps);
  }

  function computeTpsFromGasAndBlockTime() {
    const gasPerL2Block = parsePositive(l2GasPerL2BlockInput, 0);
    const l2BlockTimeSec = parsePositive(l2BlockTimeSecInput, 2);
    if (l2BlockTimeSec <= 0 || ERC20_TRANSFER_GAS <= 0) return 0;
    return gasPerL2Block / (ERC20_TRANSFER_GAS * l2BlockTimeSec);
  }

  function selectedTpsValue() {
    if (!l2TpsInput) return null;
    const raw = l2TpsInput.value;
    if (raw === 'custom') {
      const customOpt = getTpsCustomOption();
      if (!customOpt) return null;
      const fromDataset = Number(customOpt.dataset.tps);
      return Number.isFinite(fromDataset) && fromDataset >= 0 ? fromDataset : null;
    }
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
  }

  function syncTpsFromL2Gas() {
    if (!l2TpsInput) return;
    const tps = computeTpsFromGasAndBlockTime();
    setCustomTpsLabel(tps);
    let presetMatch = null;
    for (const preset of TPS_PRESETS) {
      const tolerance = Math.max(1e-6, Math.abs(preset) * 1e-3);
      if (Math.abs(tps - preset) <= tolerance) {
        presetMatch = preset;
        break;
      }
    }
    if (presetMatch !== null) {
      l2TpsInput.value = String(presetMatch);
    } else {
      l2TpsInput.value = 'custom';
    }
    updateBlobEstimatePreview();
  }

  function syncL2GasFromTps() {
    if (!l2TpsInput) return false;
    const tps = selectedTpsValue();
    if (tps == null) {
      syncTpsFromL2Gas();
      return false;
    }
    const l2BlockTimeSec = parsePositive(l2BlockTimeSecInput, 2);
    const gasPerL2Block = Math.max(0, tps * l2BlockTimeSec * ERC20_TRANSFER_GAS);
    l2GasPerL2BlockInput.value = String(Math.round(gasPerL2Block));
    setCustomTpsLabel(tps);
    updateBlobEstimatePreview();
    return true;
  }

  function clampNum(x, lo, hi) {
    return Math.max(lo, Math.min(hi, x));
  }

  function buildL2GasSeries(n, baseGasPerL1Block, scenario) {
    return simCore.buildL2GasSeries(n, baseGasPerL1Block, scenario);
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
  let sweepScoredHistory = [];
  let sweepRunSeq = 0;
  let sweepPoints = [];
  const savedRunManager = createSavedRunManager();
  let currentRunSnapshot = null;

  function currentRangeSnapshot() {
    if (!datasetReady || !blocks.length) return null;
    const clipped = clampRange(minInput.value, maxInput.value);
    return { minBlock: clipped[0], maxBlock: clipped[1] };
  }

  function currentTpsSnapshot() {
    const selected = selectedTpsValue();
    if (Number.isFinite(selected)) return Math.max(0, selected);
    return Math.max(0, computeTpsFromGasAndBlockTime());
  }

  function currentRangeIndices() {
    if (!datasetReady || !blocks.length) return null;
    const [minB, maxB] = clampRange(minInput.value, maxInput.value);
    const i0 = lowerBound(blocks, minB);
    const i1 = upperBound(blocks, maxB) - 1;
    if (i0 < 0 || i1 < i0 || i1 >= blocks.length) return null;
    return { minB, maxB, i0, i1, n: i1 - i0 + 1 };
  }

  function refreshSavedRunsStatus() {
    const savedRuns = savedRunManager.getRuns();
    if (!savedRunsStatus) return;
    savedRunsStatus.textContent = `${savedRuns.length} / ${MAX_SAVED_RUNS} saved`;
    if (clearSavedRunsBtn) clearSavedRunsBtn.disabled = savedRuns.length === 0;
    if (recomputeSavedRunsBtn) recomputeSavedRunsBtn.disabled = savedRuns.length === 0;
    if (updateAssumptionsRecomputeSavedRunsBtn) {
      updateAssumptionsRecomputeSavedRunsBtn.disabled = savedRuns.length === 0;
    }
  }

  function setSavedRunsActionText(message) {
    if (!savedRunsActionText) return;
    savedRunsActionText.textContent = message ? String(message) : '';
  }

  function formatClockTime(tsMs) {
    const ts = Number(tsMs);
    if (!Number.isFinite(ts) || ts <= 0) return 'n/a';
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (_) {
      return 'n/a';
    }
  }

  function normalizeRunName(raw) {
    if (raw == null) return '';
    const s = String(raw).trim();
    if (!s) return '';
    return s.slice(0, 80);
  }

  function runDisplayName(run, fallbackIndex) {
    const named = run && typeof run.name === 'string' ? normalizeRunName(run.name) : '';
    if (named) return named;
    if (run && Number.isFinite(Number(run.id))) return `Run #${run.id}`;
    return `Run ${Number(fallbackIndex) + 1}`;
  }

  function sanitizeSavedRun(runLike) {
    if (!runLike || typeof runLike !== 'object') return null;
    const id = Math.floor(Number(runLike.id));
    if (!Number.isFinite(id) || id <= 0) return null;
    const params = runLike.params;
    if (!params || typeof params !== 'object' || Array.isArray(params)) return null;

    const minBlockNum = Math.floor(Number(runLike.minBlock));
    const maxBlockNum = Math.floor(Number(runLike.maxBlock));
    const lastRecomputedAtNum = Number(runLike.lastRecomputedAt);
    const tpsNum = Number(runLike.tps);

    return {
      id,
      visible: runLike.visible !== false,
      solidLine: runLike.solidLine === true,
      name: normalizeRunName(runLike.name),
      datasetId: runLike.datasetId == null ? '' : String(runLike.datasetId),
      minBlock: Number.isFinite(minBlockNum) ? minBlockNum : 0,
      maxBlock: Number.isFinite(maxBlockNum) ? maxBlockNum : 0,
      lastRecomputedAt: Number.isFinite(lastRecomputedAtNum) ? lastRecomputedAtNum : 0,
      tps: Number.isFinite(tpsNum) ? tpsNum : NaN,
      params,
      series: { chargedFee: [], vault: [] },
    };
  }

  function createSavedRunManager() {
    let runs = [];
    let seq = 0;
    let showCurrent = true;

    function persist() {
      if (typeof window === 'undefined' || !window.localStorage) return;
      try {
        const payload = {
          savedRunSeq: seq,
          showCurrentRun: showCurrent,
          runs: runs.map(function (run) {
            return {
              id: run.id,
              visible: run.visible !== false,
              solidLine: run.solidLine === true,
              name: normalizeRunName(run.name),
              datasetId: run.datasetId == null ? '' : String(run.datasetId),
              minBlock: run.minBlock,
              maxBlock: run.maxBlock,
              lastRecomputedAt: run.lastRecomputedAt || 0,
              tps: run.tps,
              params: run.params,
            };
          })
        };
        window.localStorage.setItem(SAVED_RUNS_STORAGE_KEY, JSON.stringify(payload));
      } catch (_) {
        // Storage may be unavailable or full; keep in-memory behavior.
      }
    }

    function loadFromStorage() {
      if (typeof window === 'undefined' || !window.localStorage) return;
      try {
        const raw = window.localStorage.getItem(SAVED_RUNS_STORAGE_KEY);
        if (!raw) return;

        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return;

        const incomingRuns = Array.isArray(parsed.runs) ? parsed.runs : [];
        const clippedRuns = incomingRuns.slice(-MAX_SAVED_RUNS);
        const loadedRuns = [];
        let maxId = 0;

        for (const item of clippedRuns) {
          const run = sanitizeSavedRun(item);
          if (!run) continue;
          loadedRuns.push(run);
          if (run.id > maxId) maxId = run.id;
        }

        runs = loadedRuns;
        const seqNum = Math.floor(Number(parsed.savedRunSeq));
        seq = Math.max(maxId, Number.isFinite(seqNum) ? seqNum : 0);
        showCurrent = parsed.showCurrentRun !== false;
      } catch (_) {
        // Ignore bad storage payload and keep defaults.
      }
    }

    function getRuns() {
      return runs;
    }

    function hasRuns() {
      return runs.length > 0;
    }

    function getShowCurrentRun() {
      return showCurrent;
    }

    function toggleShowCurrentRun() {
      showCurrent = !showCurrent;
      persist();
      return showCurrent;
    }

    function updateRunById(runId, updateFn) {
      const run = runs.find(function (r) { return r.id === runId; });
      if (!run) return false;
      updateFn(run);
      persist();
      return true;
    }

    function deleteRun(runId) {
      const before = runs.length;
      runs = runs.filter(function (r) { return r.id !== runId; });
      if (runs.length !== before) {
        persist();
        return true;
      }
      return false;
    }

    function clear() {
      runs = [];
      persist();
    }

    function addRun(run) {
      const nextId = ++seq;
      const fullRun = {
        ...run,
        id: nextId,
      };
      let evicted = null;
      if (runs.length >= MAX_SAVED_RUNS) {
        evicted = runs.shift();
      }
      runs.push(fullRun);
      persist();
      return { run: fullRun, evicted };
    }

    function recomputeForRange(rangeInfo, replayFn, datasetId) {
      if (!rangeInfo || !runs.length) return 0;
      let rerunCount = 0;
      const nowTs = Date.now();
      for (const run of runs) {
        if (!run) continue;
        run.series = replayFn(run, rangeInfo);
        run.datasetId = datasetId;
        run.minBlock = rangeInfo.minB;
        run.maxBlock = rangeInfo.maxB;
        run.lastRecomputedAt = nowTs;
        rerunCount += 1;
      }
      if (rerunCount > 0) persist();
      return rerunCount;
    }

    return {
      loadFromStorage,
      persist,
      getRuns,
      hasRuns,
      getShowCurrentRun,
      toggleShowCurrentRun,
      updateRunById,
      deleteRun,
      clear,
      addRun,
      recomputeForRange,
    };
  }

  function syncCurrentRunButtonLabel() {
    if (!toggleCurrentRunBtn) return;
    toggleCurrentRunBtn.textContent = savedRunManager.getShowCurrentRun() ? 'Hide current run' : 'Show current run';
  }

  function runMatchesCurrentView(run) {
    if (!datasetReady || !blocks.length) return false;
    if (!run || !run.series) return false;
    const n = blocks.length;
    return (
      Array.isArray(run.series.chargedFee)
      && Array.isArray(run.series.vault)
      && run.series.chargedFee.length === n
      && run.series.vault.length === n
    );
  }

  function replaySavedRunForRange(run, rangeInfo) {
    const n = blocks.length;
    const hidden = new Array(n).fill(null);
    if (!run || !run.params || !rangeInfo) {
      return { chargedFee: hidden.slice(), vault: hidden.slice() };
    }

    const runParams = normalizeRunParams(run.params);
    const demandScalars = deriveDemandScalars(runParams);
    const localGasSeries = buildL2GasSeries(
      rangeInfo.n,
      demandScalars.l2GasPerL1BlockTarget,
      runParams.l2GasScenario
    );
    const baseFeeSlice = baseFeeGwei.slice(rangeInfo.i0, rangeInfo.i1 + 1);
    const blobFeeSlice = blobFeeGwei.slice(rangeInfo.i0, rangeInfo.i1 + 1);
    const controllerCfg = buildCoreControllerConfig(runParams);
    const replay = simCore.simulateSeries({
      ...controllerCfg,
      baseFeeGwei: baseFeeSlice,
      blobFeeGwei: blobFeeSlice,
      l2GasPerL1BlockSeries: localGasSeries,
      fullLength: rangeInfo.n,
      rangeStart: 0,
      rangeEnd: rangeInfo.n - 1,
      blockIndexOffset: rangeInfo.i0,
      collectBreakdown: false
    });

    const chargedFee = new Array(n).fill(null);
    const vaultSeries = new Array(n).fill(null);
    for (let local = 0; local < rangeInfo.n; local++) {
      const i = rangeInfo.i0 + local;
      chargedFee[i] = replay.chargedFeeGwei[local];
      vaultSeries[i] = replay.vaultEth[local];
    }
    return { chargedFee, vault: vaultSeries };
  }

  function rerunSavedRunsForCurrentRange() {
    const rangeInfo = currentRangeIndices();
    return savedRunManager.recomputeForRange(rangeInfo, replaySavedRunForRange, activeDatasetId);
  }

  function recomputeSavedRunsNow() {
    if (!savedRunManager.hasRuns()) {
      setSavedRunsActionText('No saved runs to recompute.');
      setStatus('No saved runs to recompute.');
      return;
    }
    const rerunCount = rerunSavedRunsForCurrentRange();
    renderSavedRunsList();
    refreshComparisonPlots();

    if (!rerunCount) {
      setSavedRunsActionText('No runs could be recomputed.');
      setStatus('No saved runs could be recomputed for current view.');
      return;
    }

    const suffix = rerunCount === 1 ? '' : 's';
    setSavedRunsActionText(`Recomputed ${rerunCount} run${suffix} (${formatClockTime(Date.now())}).`);
    setStatus(`Recomputed ${rerunCount} saved run${suffix} for current view.`);
  }

  function readAssumptionOverridesFromUi() {
    syncTpsFromL2Gas();
    updateBlobEstimatePreview();
    return {
      postEveryBlocks: parsePositiveInt(postEveryBlocksInput, 10),
      l2GasPerL2Block: parsePositive(l2GasPerL2BlockInput, 0),
      l2Tps: currentTpsSnapshot(),
      l2BlockTimeSec: parsePositive(l2BlockTimeSecInput, 2),
      l2GasScenario: l2GasScenarioInput.value || 'normal',
      l2DemandRegime: l2DemandRegimeInput.value || 'base',
      l1GasUsed: parsePositive(l1GasUsedInput, 0),
      blobMode: currentBlobMode(),
      fixedNumBlobs: parsePositive(numBlobsInput, 0),
      blobModel: parseBlobModelInputs(),
      priorityFeeGwei: parsePositive(priorityFeeGweiInput, 0),
    };
  }

  function updateAssumptionsAndRecomputeSavedRunsNow() {
    if (!savedRunManager.hasRuns()) {
      setSavedRunsActionText('No saved runs to update.');
      setStatus('No saved runs to update.');
      return;
    }
    const rangeInfo = currentRangeIndices();
    if (!rangeInfo) {
      setSavedRunsActionText('No valid range selected.');
      setStatus('Cannot update saved runs: invalid current range.');
      return;
    }

    const assumptions = readAssumptionOverridesFromUi();
    const savedRuns = savedRunManager.getRuns();
    const nowTs = Date.now();
    let updatedCount = 0;

    for (const run of savedRuns) {
      if (!run || !run.params) continue;
      const mergedParams = normalizeRunParams({ ...run.params, ...assumptions });
      run.params = mergedParams;
      run.tps = Number.isFinite(mergedParams.l2Tps) ? mergedParams.l2Tps : run.tps;
      run.series = replaySavedRunForRange(run, rangeInfo);
      run.datasetId = activeDatasetId;
      run.minBlock = rangeInfo.minB;
      run.maxBlock = rangeInfo.maxB;
      run.lastRecomputedAt = nowTs;
      updatedCount += 1;
    }

    if (updatedCount > 0) {
      savedRunManager.persist();
    }
    renderSavedRunsList();
    refreshComparisonPlots();

    if (!updatedCount) {
      setSavedRunsActionText('No runs were updated.');
      setStatus('No saved runs were updated.');
      return;
    }

    const suffix = updatedCount === 1 ? '' : 's';
    setSavedRunsActionText(
      `Updated assumptions + recomputed ${updatedCount} run${suffix} (${formatClockTime(nowTs)}).`
    );
    setStatus(`Updated L2/L1 assumptions and recomputed ${updatedCount} saved run${suffix}.`);
  }

  function overlaySeriesForRuns(field, n) {
    const savedRuns = savedRunManager.getRuns();
    const hidden = new Array(n).fill(null);
    const out = [];
    for (let i = 0; i < MAX_SAVED_RUNS; i++) {
      const run = savedRuns[i];
      if (
        run
        && run.visible
        && runMatchesCurrentView(run)
        && run.series
        && Array.isArray(run.series[field])
        && run.series[field].length === n
      ) {
        out.push(run.series[field]);
      } else {
        out.push(hidden);
      }
    }
    return out;
  }

  function syncSavedRunSeriesPresentation() {
    const savedRuns = savedRunManager.getRuns();
    const applyToPlot = function (plot, startIndex, metricLabel) {
      if (!plot || !Array.isArray(plot.series)) return;
      let needsRedraw = false;
      const legendLabels = (
        plot.root && plot.root.querySelectorAll
          ? plot.root.querySelectorAll('.u-legend .u-series .u-label')
          : null
      );
      for (let i = 0; i < MAX_SAVED_RUNS; i++) {
        const slot = plot.series[startIndex + i];
        if (!slot) continue;
        let label = `Saved run ${i + 1} ${metricLabel}`;
        let dash = [6, 4];
        let width = 1.1;
        let show = false;
        const run = savedRuns[i];
        if (run) {
          const name = runDisplayName(run, i);
          label = `${name} ${metricLabel}`;
          dash = run.solidLine ? [] : [6, 4];
          width = run.solidLine ? 1.4 : 1.1;
          show = Boolean(run.visible && runMatchesCurrentView(run));
        }

        if (
          slot.label === label
          && String(slot.width) === String(width)
          && Boolean(slot.show !== false) === show
          && Array.isArray(slot.dash)
          && Array.isArray(dash)
          && slot.dash.length === dash.length
          && slot.dash.every(function (v, idx) { return v === dash[idx]; })
        ) {
          continue;
        }

        if (typeof plot.setSeries === 'function') {
          plot.setSeries(startIndex + i, { label, show });
        }

        // uPlot setSeries does not reliably apply dash/width updates for existing series.
        // Mutate slot style directly and force redraw when style changes.
        if (!slot.dash || slot.dash.length !== dash.length || slot.dash.some(function (v, idx) { return v !== dash[idx]; })) {
          slot.dash = dash.slice();
          needsRedraw = true;
        }
        if (String(slot.width) !== String(width)) {
          slot.width = width;
          needsRedraw = true;
        }
        if (slot.label !== label) slot.label = label;
        if (Boolean(slot.show !== false) !== show) slot.show = show;

        if (legendLabels && legendLabels[startIndex + i]) {
          const el = legendLabels[startIndex + i];
          if (el.textContent !== label) el.textContent = label;
          const row = el.closest('.u-series');
          if (row && row.style) row.style.display = show ? '' : 'none';
        }
      }

      if (needsRedraw && typeof plot.redraw === 'function') {
        plot.redraw();
      }
    };

    applyToPlot(requiredFeePlot, 4, 'charged fee');
    applyToPlot(chargedFeeOnlyPlot, 2, 'charged fee');
    applyToPlot(vaultPlot, 3, 'vault');
  }

  function renderSavedRunsList() {
    const savedRuns = savedRunManager.getRuns();
    refreshSavedRunsStatus();
    if (!savedRunsList) return;
    if (!savedRuns.length) {
      savedRunsList.innerHTML = '<div class="formula">No saved runs yet.</div>';
      return;
    }

    const rows = savedRuns.map(function (run, idx) {
      const activeText = runMatchesCurrentView(run) ? 'replayed for current view' : 'needs recompute for current view';
      const recomputeText = formatClockTime(run.lastRecomputedAt);
      const tpsText = Number.isFinite(run.tps) ? formatNum(run.tps, 3) : 'n/a';
      const displayName = runDisplayName(run, idx);
      const rawName = normalizeRunName(run.name);
      const paramsJson = htmlEscape(JSON.stringify(run.params, null, 2));
      const slotColor = SAVED_RUN_COLORS[idx % SAVED_RUN_COLORS.length];
      return `
        <div class="saved-run" data-run-id="${run.id}">
          <div class="saved-run-head">
            <span class="saved-run-swatch" style="background:${slotColor};"></span>
            <strong>${htmlEscape(displayName)}</strong>
            <span>TPS ${tpsText}</span>
            <label><input type="checkbox" data-action="toggle" data-run-id="${run.id}" ${run.visible ? 'checked' : ''}/> show</label>
            <label><input type="checkbox" data-action="lineStyle" data-run-id="${run.id}" ${run.solidLine ? 'checked' : ''}/> solid line</label>
            <label>name <input class="saved-run-name" type="text" data-action="name" data-run-id="${run.id}" value="${htmlEscape(rawName)}" placeholder="Run #${run.id}" /></label>
            <button data-action="delete" data-run-id="${run.id}">Delete</button>
          </div>
          <div class="saved-run-meta">
            ${htmlEscape(run.datasetId)} | blocks ${run.minBlock.toLocaleString()}-${run.maxBlock.toLocaleString()} | ${activeText} | recomputed ${recomputeText}
          </div>
          <details>
            <summary>Full params</summary>
            <pre>${paramsJson}</pre>
          </details>
        </div>
      `;
    });
    savedRunsList.innerHTML = rows.join('');
  }

  function deleteSavedRun(runId) {
    savedRunManager.deleteRun(runId);
    renderSavedRunsList();
    refreshComparisonPlots();
    setSavedRunsActionText(`Deleted run #${runId}.`);
  }

  function clearSavedRuns() {
    savedRunManager.clear();
    renderSavedRunsList();
    refreshComparisonPlots();
    setSavedRunsActionText('Cleared saved runs.');
  }

  function toggleCurrentRunView() {
    const showCurrentRun = savedRunManager.toggleShowCurrentRun();
    syncCurrentRunButtonLabel();
    refreshComparisonPlots();
    if (showCurrentRun) {
      setStatus('Current run is visible.');
    } else {
      setStatus('Current run hidden. Showing saved runs only.');
    }
  }

  function saveCurrentRun() {
    const snap = currentRunSnapshot;
    const range = currentRangeSnapshot();
    if (!snap || !range) {
      setStatus('No computed run to save. Recompute first.');
      return;
    }
    if (
      snap.datasetId !== activeDatasetId
      || snap.minBlock !== range.minBlock
      || snap.maxBlock !== range.maxBlock
    ) {
      setStatus('Current computed results do not match selected range. Recompute then save.');
      return;
    }

    const rangeInfo = currentRangeIndices();
    const run = {
      visible: true,
      solidLine: false,
      name: '',
      datasetId: snap.datasetId,
      minBlock: rangeInfo ? rangeInfo.minB : snap.minBlock,
      maxBlock: rangeInfo ? rangeInfo.maxB : snap.maxBlock,
      lastRecomputedAt: Date.now(),
      tps: snap.tps,
      params: snap.params,
      series: {
        chargedFee: snap.series.chargedFee.slice(),
        vault: snap.series.vault.slice(),
      }
    };
    if (rangeInfo) {
      run.series = replaySavedRunForRange(run, rangeInfo);
    }
    const saved = savedRunManager.addRun(run);
    renderSavedRunsList();
    refreshComparisonPlots();

    const runId = saved.run.id;
    const evicted = saved.evicted;
    if (evicted) {
      setStatus(`Saved run #${runId}. Removed oldest run #${evicted.id} (cap ${MAX_SAVED_RUNS}).`);
    } else {
      setStatus(`Saved run #${runId} (TPS ${formatNum(run.tps, 3)}).`);
    }
    setSavedRunsActionText(`Saved run #${runId}.`);
  }

  function refreshComparisonPlots() {
    const savedRuns = savedRunManager.getRuns();
    const showCurrentRun = savedRunManager.getShowCurrentRun();
    if (!blocks.length) return;
    const n = blocks.length;
    if (!derivedChargedFeeGwei.length || !derivedVaultEth.length) {
      renderSavedRunsList();
      return;
    }

    const hidden = new Array(n).fill(null);
    const currentCharged = showCurrentRun ? derivedChargedFeeGwei : hidden;
    const currentVault = showCurrentRun ? derivedVaultEth : hidden;
    const compareCharged = overlaySeriesForRuns('chargedFee', n);
    const compareVault = overlaySeriesForRuns('vault', n);
    setLegendSeriesVisibility(requiredFeePlot, 3, showCurrentRun);
    setLegendSeriesVisibility(chargedFeeOnlyPlot, 1, showCurrentRun);
    setLegendSeriesVisibility(vaultPlot, 2, showCurrentRun);
    syncSavedRunSeriesPresentation();

    if (requiredFeePlot) {
      requiredFeePlot.setData([
        blocks,
        derivedGasFeeComponentGwei,
        derivedBlobFeeComponentGwei,
        currentCharged,
        ...compareCharged
      ], false);
    }

    if (chargedFeeOnlyPlot) {
      chargedFeeOnlyPlot.setData([
        blocks,
        currentCharged,
        ...compareCharged
      ], false);
    }

    if (vaultPlot) {
      vaultPlot.setData([
        blocks,
        derivedVaultTargetEth,
        currentVault,
        ...compareVault
      ], false);
    }

    renderSavedRunsList();
  }

  function setLegendSeriesVisibility(plot, seriesIndex, show) {
    if (!plot || typeof plot.setSeries !== 'function') return;
    plot.setSeries(seriesIndex, { show });
    const legendRows = plot.root?.querySelectorAll
      ? plot.root.querySelectorAll('.u-legend .u-series')
      : null;
    if (!legendRows || !legendRows[seriesIndex] || !legendRows[seriesIndex].style) return;
    legendRows[seriesIndex].style.display = show ? '' : 'none';
  }

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

  function resetSweepState(reason) {
    sweepResults = [];
    sweepBestCandidate = null;
    sweepCurrentPoint = null;
    sweepScoredHistory = [];
    sweepPoints = [];
    if (sweepApplyBestBtn) sweepApplyBestBtn.disabled = true;
    if (sweepBestMode) sweepBestMode.textContent = '-';
    if (sweepBestAlphaVariant) sweepBestAlphaVariant.textContent = '-';
    if (sweepBestKp) sweepBestKp.textContent = '-';
    if (sweepBestKi) sweepBestKi.textContent = '-';
    if (sweepBestImax) sweepBestImax.textContent = '-';
    if (sweepBestHealth) sweepBestHealth.textContent = '-';
    if (sweepBestUx) sweepBestUx.textContent = '-';
    if (sweepBestTotal) sweepBestTotal.textContent = '-';
    if (sweepCandidateCount) sweepCandidateCount.textContent = '-';
    if (sweepRangeCount) sweepRangeCount.textContent = '-';
    renderSweepScatter([], null, null, []);
    setSweepHoverText('Hover point: -');
    markSweepStale(reason || 'range changed');
  }

  function markSweepStale(reason) {
    if (sweepRunning) return;
    const why = reason ? ` (${reason})` : '';
    setSweepStatus(`Sweep stale${why}. Run parameter sweep to refresh.`);
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
      deadbandPct: parsePositive(deficitDeadbandPctInput, 5.0),
      wHealth: parsePositive(scoreWeightHealthInput, 0.75),
      wUx: parsePositive(scoreWeightUxInput, 0.25),
      wDraw: parsePositive(healthWDrawInput, 0.35),
      wUnder: parsePositive(healthWUnderInput, 0.25),
      wArea: parsePositive(healthWAreaInput, 0.2),
      wStreak: parsePositive(healthWStreakInput, 0.1),
      wPostBE: parsePositive(healthWPostBEInput, 0.2),
      wStd: parsePositive(uxWStdInput, 0.2),
      wP95: parsePositive(uxWP95Input, 0.2),
      wP99: parsePositive(uxWP99Input, 0.1),
      wMaxStep: parsePositive(uxWMaxStepInput, 0.05),
      wClamp: parsePositive(uxWClampInput, 0.05),
      wLevel: parsePositive(uxWLevelInput, 0.4)
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
    syncTpsFromL2Gas();
    updateBlobEstimatePreview();
    let runParams = normalizeRunParams({
      postEveryBlocks: parsePositiveInt(postEveryBlocksInput, 10),
      l2GasPerL2Block: parsePositive(l2GasPerL2BlockInput, 0),
      l2Tps: currentTpsSnapshot(),
      l2BlockTimeSec: parsePositive(l2BlockTimeSecInput, 2),
      l2GasScenario: l2GasScenarioInput.value || 'constant',
      l2DemandRegime: l2DemandRegimeInput.value || 'base',
      l1GasUsed: parsePositive(l1GasUsedInput, 0),
      blobMode: currentBlobMode(),
      fixedNumBlobs: parsePositive(numBlobsInput, 0),
      blobModel: parseBlobModelInputs(),
      priorityFeeGwei: parsePositive(priorityFeeGweiInput, 0),
      feeMechanism: currentFeeMechanism(),
      controllerMode: controllerModeInput.value || 'ff',
      autoAlphaEnabled: autoAlphaInput.checked,
      alphaGas: parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS),
      alphaBlob: parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB),
      kp: parsePositive(kpInput, 0),
      pTermMinGwei: parseNumber(pMinGweiInput, 0.0),
      ki: parsePositive(kiInput, 0),
      kd: parsePositive(kdInput, 0),
      iMin: parseNumber(iMinInput, -5),
      iMax: parseNumber(iMaxInput, 5),
      dffBlocks: parseNonNegativeInt(dffBlocksInput, 5),
      dfbBlocks: parsePositiveInt(dfbBlocksInput, 5),
      derivBeta: clampNum(parseNumber(dSmoothBetaInput, 0.8), 0, 1),
      minFeeGwei: parsePositive(minFeeGweiInput, 0.01),
      maxFeeGwei: parsePositive(maxFeeGweiInput, 1),
      initialVaultEth: parsePositive(initialVaultEthInput, 0),
      targetVaultEth: parsePositive(targetVaultEthInput, 0),
      eip1559: {
        maxChangeDenominator: parsePositiveInt(eip1559DenominatorInput, DEFAULT_EIP1559_DENOMINATOR)
      },
      arbitrum: {
        initialPriceGwei: parsePositive(arbInitialPriceGweiInput, DEFAULT_ARB_INITIAL_PRICE_GWEI),
        inertia: parsePositiveInt(arbInertiaInput, DEFAULT_ARB_INERTIA),
        equilUnits: parsePositive(arbEquilUnitsInput, DEFAULT_ARB_EQUIL_UNITS),
      }
    });

    const demandScalars = deriveDemandScalars(runParams);
    const l2GasPerProposalBase = demandScalars.l2GasPerProposalBase;
    const autoAlphaGas = l2GasPerProposalBase > 0 ? (runParams.l1GasUsed / l2GasPerProposalBase) : 0;
    let expectedBlobsBase = runParams.fixedNumBlobs;
    if (runParams.blobMode === 'dynamic') {
      expectedBlobsBase = estimateDynamicBlobs(l2GasPerProposalBase, runParams.blobModel);
    }
    const autoAlphaBlob =
      l2GasPerProposalBase > 0 ? ((expectedBlobsBase * BLOB_GAS_PER_BLOB) / l2GasPerProposalBase) : 0;
    if (runParams.feeMechanism === 'taiko') {
      if (runParams.autoAlphaEnabled) {
        alphaGasInput.value = autoAlphaGas.toFixed(6);
        alphaBlobInput.value = autoAlphaBlob.toFixed(6);
        runParams = normalizeRunParams({
          ...runParams,
          alphaGas: autoAlphaGas,
          alphaBlob: autoAlphaBlob
        });
      }
      alphaGasInput.disabled = runParams.autoAlphaEnabled;
      alphaBlobInput.disabled = runParams.autoAlphaEnabled;
    } else {
      alphaGasInput.disabled = true;
      alphaBlobInput.disabled = true;
    }
    const controllerCfg = buildCoreControllerConfig(runParams);
    const feeMechanism = runParams.feeMechanism;
    const targetVaultEth = runParams.targetVaultEth;
    const maxFeeGwei = runParams.maxFeeGwei;
    const {
      postEveryBlocks,
      l1GasUsed,
      blobMode,
      fixedNumBlobs,
      blobModel,
      controllerMode,
      kp,
      ki,
      kd,
      dffBlocks,
      dfbBlocks,
      derivBeta,
      iMin,
      iMax,
      alphaGas,
      alphaBlob
    } = runParams;
    const {
      priorityFeeWei,
      pTermMinWei,
      minFeeWei,
      maxFeeWei
    } = controllerCfg;

    derivedL2GasPerL1BlockText.textContent =
      `${formatNum(demandScalars.l2GasPerL1BlockBase, 0)} gas/L1 block (base), ` +
      `${formatNum(demandScalars.l2GasPerL1BlockTarget, 0)} gas/L1 block (target)`;
    derivedL2GasPerProposalText.textContent = `${formatNum(l2GasPerProposalBase, 0)} gas/proposal (base)`;

    const n = blocks.length;
    derivedL2GasPerL1Block = buildL2GasSeries(n, demandScalars.l2GasPerL1BlockTarget, runParams.l2GasScenario);
    derivedL2GasPerL1BlockBase = new Array(n).fill(demandScalars.l2GasPerL1BlockTarget);
    if (demandScalars.l2BlocksPerL1Block > 0) {
      derivedL2GasPerL2Block = derivedL2GasPerL1Block.map(function (x) {
        return x / demandScalars.l2BlocksPerL1Block;
      });
      derivedL2GasPerL2BlockBase = derivedL2GasPerL1BlockBase.map(function (x) {
        return x / demandScalars.l2BlocksPerL1Block;
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

    const simulation = simCore.simulateSeries({
      ...controllerCfg,
      baseFeeGwei,
      blobFeeGwei,
      l2GasPerL1BlockSeries: derivedL2GasPerL1Block,
      blocks,
      fullLength: n,
      rangeStart: 0,
      rangeEnd: n - 1,
      blockIndexOffset: 0,
      collectBreakdown: true,
    });

    derivedGasCostEth = simulation.gasCostEth;
    derivedBlobCostEth = simulation.blobCostEth;
    derivedPostingCostEth = simulation.postingCostEth;
    derivedRequiredFeeGwei = simulation.requiredFeeGwei;
    derivedGasFeeComponentGwei = simulation.gasFeeComponentGwei;
    derivedBlobFeeComponentGwei = simulation.blobFeeComponentGwei;
    derivedFeedforwardFeeGwei = simulation.feedforwardFeeGwei;
    derivedPTermFeeGwei = simulation.pTermFeeGwei;
    derivedITermFeeGwei = simulation.iTermFeeGwei;
    derivedDTermFeeGwei = simulation.dTermFeeGwei;
    derivedFeedbackFeeGwei = simulation.feedbackFeeGwei;
    derivedChargedFeeGwei = simulation.chargedFeeGwei;
    derivedPostingRevenueAtPostEth = simulation.postingRevenueAtPostEth;
    derivedPostingPnLEth = simulation.postingPnLEth;
    derivedPostingPnLBlocks = simulation.postingPnLBlocks;
    derivedPostBreakEvenFlag = simulation.postBreakEvenFlag;
    derivedDeficitEth = simulation.deficitEth;
    derivedEpsilon = simulation.epsilon;
    derivedDerivative = simulation.derivative;
    derivedIntegral = simulation.integral;
    derivedClampState = simulation.clampState;
    derivedVaultEth = simulation.vaultEth;
    derivedVaultTargetEth = new Array(n).fill(targetVaultEth);

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
      refreshComparisonPlots();

      if (preservedRange) {
        applyRange(preservedRange[0], preservedRange[1], null);
      }
    }

    const runRange = currentRangeSnapshot() || { minBlock: MIN_BLOCK, maxBlock: MAX_BLOCK };
    currentRunSnapshot = {
      datasetId: activeDatasetId,
      minBlock: runRange.minBlock,
      maxBlock: runRange.maxBlock,
      tps: currentTpsSnapshot(),
      params: runParams,
      series: {
        chargedFee: derivedChargedFeeGwei.slice(),
        vault: derivedVaultEth.slice()
      }
    };

    const lastIdx = n - 1;
    latestPostingCost.textContent = `${formatNum(derivedPostingCostEth[lastIdx], 6)} ETH`;
    if (derivedRequiredFeeGwei[lastIdx] == null || derivedChargedFeeGwei[lastIdx] == null) {
      latestRequiredFee.textContent = 'n/a';
      latestChargedFee.textContent = 'n/a';
      latestGasComponentFee.textContent = 'n/a';
      latestBlobComponentFee.textContent = 'n/a';
      latestL2GasUsed.textContent = 'n/a';
    } else {
      latestRequiredFee.textContent = formatFeeGwei(derivedRequiredFeeGwei[lastIdx]);
      latestChargedFee.textContent = formatFeeGwei(derivedChargedFeeGwei[lastIdx]);
      latestGasComponentFee.textContent = formatFeeGwei(derivedGasFeeComponentGwei[lastIdx]);
      latestBlobComponentFee.textContent = formatFeeGwei(derivedBlobFeeComponentGwei[lastIdx]);
      latestL2GasUsed.textContent = `${formatNum(derivedL2GasPerL2Block[lastIdx], 0)} gas/L2 block`;
    }
    latestDeficitEth.textContent = `${formatNum(derivedDeficitEth[lastIdx], 6)} ETH`;
    latestEpsilon.textContent = `${formatNum(derivedEpsilon[lastIdx], 6)}`;
    latestDerivative.textContent = `${formatNum(derivedDerivative[lastIdx], 6)}`;
    latestIntegral.textContent = `${formatNum(derivedIntegral[lastIdx], 6)}`;
    latestFfTerm.textContent = formatFeeGwei(derivedFeedforwardFeeGwei[lastIdx]);
    latestDTerm.textContent = formatFeeGwei(derivedDTermFeeGwei[lastIdx]);
    latestFbTerm.textContent = formatFeeGwei(derivedFeedbackFeeGwei[lastIdx]);
    latestClampState.textContent = derivedClampState[lastIdx];
    latestVaultValue.textContent = `${formatNum(derivedVaultEth[lastIdx], 6)} ETH`;
    latestVaultGap.textContent = `${formatNum(derivedVaultEth[lastIdx] - targetVaultEth, 6)} ETH`;
    if (sweepResults.length) {
      const sweepRange = getSweepRangeIndices();
      if (sweepRange && feeMechanism === 'taiko') {
        const sweepScoreCfg = parseScoringWeights();
        const sweepSimCfg = {
          postEveryBlocks,
          l1GasUsed,
          blobMode,
          fixedNumBlobs,
          blobModel: {
            txGas: blobModel.txGas,
            txBytes: blobModel.txBytes,
            batchOverheadBytes: blobModel.batchOverheadBytes,
            compressionRatio: blobModel.compressionRatio,
            blobUtilization: blobModel.blobUtilization,
            minBlobsPerProposal: blobModel.minBlobsPerProposal
          },
          priorityFeeWei,
          dffBlocks,
          dfbBlocks,
          derivBeta,
          iMin,
          iMax,
          minFeeWei,
          maxFeeWei,
          maxFeeGwei,
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
      renderSweepScatter(sweepResults, sweepBestCandidate, sweepCurrentPoint, sweepScoredHistory);
    }
    markScoreStale('recomputed charts');
  }

  function evaluateSweepCandidate(i0, i1, candidate, simCfg, scoreCfg) {
    const candidateAlphaGas = Number.isFinite(candidate.alphaGas)
      ? Math.max(0, candidate.alphaGas)
      : Math.max(0, simCfg.alphaGas);
    const candidateAlphaBlob = Number.isFinite(candidate.alphaBlob)
      ? Math.max(0, candidate.alphaBlob)
      : Math.max(0, simCfg.alphaBlob);
    const candidateAlphaVariant = candidate.alphaVariant || 'current';
    const n = i1 - i0 + 1;

    const iMaxSweep = Number.isFinite(candidate.iMax) ? candidate.iMax : simCfg.iMax;
    const simulation = simCore.simulateSeries({
      mechanism: 'taiko',
      controllerMode: candidate.mode,
      baseFeeGwei: baseFeeGwei.slice(i0, i1 + 1),
      blobFeeGwei: blobFeeGwei.slice(i0, i1 + 1),
      l2GasPerL1BlockSeries: simCfg.l2GasPerL1BlockSeries.slice(i0, i1 + 1),
      fullLength: n,
      rangeStart: 0,
      rangeEnd: n - 1,
      blockIndexOffset: i0,
      postEveryBlocks: simCfg.postEveryBlocks,
      l1GasUsed: simCfg.l1GasUsed,
      blobMode: simCfg.blobMode,
      fixedNumBlobs: simCfg.fixedNumBlobs,
      blobModel: simCfg.blobModel,
      priorityFeeWei: simCfg.priorityFeeWei,
      dffBlocks: simCfg.dffBlocks,
      dfbBlocks: simCfg.dfbBlocks,
      derivBeta: simCfg.derivBeta,
      kp: candidate.kp,
      ki: candidate.ki,
      kd: candidate.kd,
      pTermMinWei: simCfg.pTermMinWei,
      iMin: simCfg.iMin,
      iMax: iMaxSweep,
      minFeeWei: simCfg.minFeeWei,
      maxFeeWei: simCfg.maxFeeWei,
      alphaGas: candidateAlphaGas,
      alphaBlob: candidateAlphaBlob,
      initialVaultEth: simCfg.initialVaultEth,
      targetVaultEth: simCfg.targetVaultEth,
      collectBreakdown: true
    });

    const metrics = computeScoredMetrics({
      chargedFeeSeries: simulation.chargedFeeGwei,
      vaultSeries: simulation.vaultEth,
      requiredFeeSeries: simulation.requiredFeeGwei,
      clampStateSeries: simulation.clampState,
      postBreakEvenSeries: simulation.postBreakEvenFlag,
      targetVaultEth: simCfg.targetVaultEth,
      maxFeeGwei: simCfg.maxFeeGwei,
      deadbandPct: scoreCfg.deadbandPct,
      scoreCfg,
      i0: 0,
      i1: n - 1,
      skipNullSeries: true,
      fallbackTargetDenomToOne: true,
    });

    return {
      mode: candidate.mode,
      alphaVariant: candidateAlphaVariant,
      alphaGas: candidateAlphaGas,
      alphaBlob: candidateAlphaBlob,
      kp: candidate.kp,
      ki: candidate.ki,
      kd: candidate.kd,
      iMax: iMaxSweep,
      nBlocks: metrics.n,
      healthBadness: metrics.healthBadness,
      uxBadness: metrics.uxBadness,
      totalBadness: metrics.totalBadness,
      maxDrawdownEth: metrics.maxDrawdownEth,
      underTargetRatio: metrics.underTargetRatio,
      postBreakEvenRatio: metrics.postBreakEvenRatio,
      feeStd: metrics.feeStd,
      stepP95: metrics.stepP95,
      stepP99: metrics.stepP99,
      maxStep: metrics.maxStep,
      clampMaxRatio: metrics.clampMaxRatio,
      uLevel: metrics.uLevel
    };
  }

  function renderSweepScatter(results, best, currentPoint, scoredHistory) {
    if (!sweepPlot) return;
    const points = [];
    const scoredPoints = Array.isArray(scoredHistory) ? scoredHistory : [];
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
        isCurrent: false,
        isScored: false,
        isLatestScored: false
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
        isCurrent: true,
        isScored: false,
        isLatestScored: false
      });
    }
    for (let i = 0; i < scoredPoints.length; i++) {
      const p = scoredPoints[i];
      if (!Number.isFinite(p.uxBadness) || !Number.isFinite(p.healthBadness)) continue;
      points.push({
        ux: p.uxBadness,
        health: p.healthBadness,
        total: p.totalBadness,
        mode: p.mode || '-',
        alphaVariant: p.alphaVariant || 'current',
        alphaGas: p.alphaGas,
        alphaBlob: p.alphaBlob,
        kp: p.kp,
        ki: p.ki,
        kd: p.kd,
        iMax: p.iMax,
        isBest: false,
        isCurrent: false,
        isScored: true,
        isLatestScored: i === scoredPoints.length - 1
      });
    }
    // Always include the origin as a visual reference point for the tradeoff chart.
    points.push({
      ux: 0,
      health: 0,
      total: 0,
      mode: 'origin',
      alphaVariant: '-',
      alphaGas: 0,
      alphaBlob: 0,
      kp: 0,
      ki: 0,
      kd: 0,
      iMax: 0,
      isBest: false,
      isCurrent: false,
      isScored: false,
      isLatestScored: false,
      isOrigin: true
    });
    points.sort(function (a, b) {
      if (a.ux !== b.ux) return a.ux - b.ux;
      return a.health - b.health;
    });

    const x = new Array(points.length);
    const allY = new Array(points.length);
    const bestY = new Array(points.length);
    const currentY = new Array(points.length);
    const scoredY = new Array(points.length);
    const latestScoredY = new Array(points.length);
    const originY = new Array(points.length);

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
      scoredY[i] = p.isScored && !p.isLatestScored ? p.health : null;
      latestScoredY[i] = p.isLatestScored ? p.health : null;
      originY[i] = p.isOrigin ? p.health : null;
      if (p.ux < xMin) xMin = p.ux;
      if (p.ux > xMax) xMax = p.ux;
      if (p.health < yMin) yMin = p.health;
      if (p.health > yMax) yMax = p.health;
    }

    sweepPoints = points;
    sweepPlot.setData([x, allY, bestY, currentY, scoredY, latestScoredY, originY]);
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
    if (p.isOrigin) tagParts.push('origin');
    if (p.isBest) tagParts.push('best');
    if (p.isCurrent) tagParts.push('current');
    if (p.isScored) tagParts.push('scored');
    if (p.isLatestScored) tagParts.push('latest');
    const tagText = tagParts.length ? ` (${tagParts.join(', ')})` : '';
    setSweepHoverText(
      `Hover point ${rankPart}${tagText}: mode=${p.mode}, alpha=${p.alphaVariant}, ` +
      `Kp=${formatNum(p.kp, 4)}, Ki=${formatNum(p.ki, 4)}, Kd=${formatNum(p.kd, 4)}, Imax=${formatNum(p.iMax, 4)}, ` +
      `health=${formatNum(p.health, 6)}, UX=${formatNum(p.ux, 6)}, total=${formatNum(p.total, 6)}`
    );
  }

  async function runParameterSweep() {
    if (sweepRunning) return;
    if (currentFeeMechanism() !== 'taiko') {
      setSweepStatus('Sweep currently supports Taiko mechanism only. Switch Fee mechanism to "Taiko (P/I/D + FF)".');
      return;
    }
    recalcDerivedSeries();
    clearParamsStale();

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

    const runParams = normalizeRunParams({
      postEveryBlocks: parsePositiveInt(postEveryBlocksInput, 10),
      l1GasUsed: parsePositive(l1GasUsedInput, 0),
      blobMode: currentBlobMode(),
      fixedNumBlobs: parsePositive(numBlobsInput, 0),
      blobModel: parseBlobModelInputs(),
      priorityFeeGwei: parsePositive(priorityFeeGweiInput, 0),
      dffBlocks: parseNonNegativeInt(dffBlocksInput, 5),
      dfbBlocks: parsePositiveInt(dfbBlocksInput, 5),
      derivBeta: clampNum(parseNumber(dSmoothBetaInput, 0.8), 0, 1),
      pTermMinGwei: parseNumber(pMinGweiInput, 0.0),
      iMin: parseNumber(iMinInput, -5),
      iMax: parseNumber(iMaxInput, 5),
      minFeeGwei: parsePositive(minFeeGweiInput, 0.01),
      maxFeeGwei: parsePositive(maxFeeGweiInput, 1.0),
      initialVaultEth: parsePositive(initialVaultEthInput, 0),
      targetVaultEth: parsePositive(targetVaultEthInput, 0),
      alphaGas: parsePositive(alphaGasInput, DEFAULT_ALPHA_GAS),
      alphaBlob: parsePositive(alphaBlobInput, DEFAULT_ALPHA_BLOB),
    });
    const controllerCfg = buildCoreControllerConfig(runParams);
    const alphaGasFixed = runParams.alphaGas;
    const alphaBlobFixed = runParams.alphaBlob;
    const scoreCfg = parseScoringWeights();
    const simCfg = {
      postEveryBlocks: runParams.postEveryBlocks,
      l1GasUsed: runParams.l1GasUsed,
      blobMode: runParams.blobMode,
      fixedNumBlobs: runParams.fixedNumBlobs,
      blobModel: runParams.blobModel,
      priorityFeeWei: controllerCfg.priorityFeeWei,
      dffBlocks: runParams.dffBlocks,
      dfbBlocks: runParams.dfbBlocks,
      derivBeta: runParams.derivBeta,
      iMin: runParams.iMin,
      iMax: runParams.iMax,
      minFeeWei: controllerCfg.minFeeWei,
      maxFeeWei: controllerCfg.maxFeeWei,
      maxFeeGwei: runParams.maxFeeGwei,
      pTermMinWei: controllerCfg.pTermMinWei,
      initialVaultEth: runParams.initialVaultEth,
      targetVaultEth: runParams.targetVaultEth,
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
    renderSweepScatter(sweepResults, sweepBestCandidate, sweepCurrentPoint, sweepScoredHistory);

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
    if (feeMechanismInput) feeMechanismInput.value = 'taiko';
    syncFeeMechanismUi();
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
    scheduleRecalc('Applied best params. Recomputing derived charts...');
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
    const series = [
      { value: function (u, v) { return formatBlockWithApprox(v); } },
      { label: 'Gas component fee (gwei/L2 gas)', stroke: '#2563eb', width: 1 },
      { label: 'Blob component fee (gwei/L2 gas)', stroke: '#ea580c', width: 1 },
      { label: 'Charged fee (clamped total)', stroke: '#16a34a', width: 1.4 }
    ];
    for (let i = 0; i < MAX_SAVED_RUNS; i++) {
      series.push({
        label: `Saved run ${i + 1} charged fee`,
        stroke: SAVED_RUN_COLORS[i % SAVED_RUN_COLORS.length],
        width: 1.1,
        dash: [6, 4]
      });
    }
    return {
      title: 'L2 Fee Components (feedforward + clamped total)',
      width,
      height,
      scales: { x: { time: false } },
      series,
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
    const series = [
      { value: function (u, v) { return formatBlockWithApprox(v); } },
      { label: 'Charged fee (gwei/L2 gas)', stroke: '#16a34a', width: 1.4 }
    ];
    for (let i = 0; i < MAX_SAVED_RUNS; i++) {
      series.push({
        label: `Saved run ${i + 1} charged fee`,
        stroke: SAVED_RUN_COLORS[i % SAVED_RUN_COLORS.length],
        width: 1.1,
        dash: [6, 4]
      });
    }
    return {
      title: 'L2 Charged Fee (clamped total only)',
      width,
      height,
      scales: { x: { time: false } },
      series,
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
    const series = [
      { value: function (u, v) { return formatBlockWithApprox(v); } },
      { label: 'Target vault (ETH)', stroke: '#dc2626', width: 1 },
      { label: 'Current vault (ETH)', stroke: '#0f766e', width: 1.4 }
    ];
    for (let i = 0; i < MAX_SAVED_RUNS; i++) {
      series.push({
        label: `Saved run ${i + 1} vault`,
        stroke: SAVED_RUN_COLORS[i % SAVED_RUN_COLORS.length],
        width: 1.1,
        dash: [6, 4]
      });
    }
    return {
      title: 'Vault Value vs Target',
      width,
      height,
      scales: { x: { time: false } },
      series,
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
          label: 'UX badness',
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
          stroke: '#0284c7',
          width: 0,
          points: { show: true, size: 7, stroke: '#0284c7', fill: '#38bdf8' }
        },
        {
          label: 'Scored points (history)',
          stroke: '#a16207',
          width: 0,
          points: { show: true, size: 6, stroke: '#a16207', fill: '#fde68a' }
        },
        {
          label: 'Scored point (latest)',
          stroke: '#ca8a04',
          width: 0,
          points: { show: true, size: 8, stroke: '#ca8a04', fill: '#facc15' }
        },
        {
          label: 'Origin (0,0)',
          stroke: '#111827',
          width: 0,
          points: { show: true, size: 8, stroke: '#111827', fill: '#ffffff' }
        }
      ],
      axes: [
        {
          label: 'UX badness',
          values: function (u, vals) {
            return vals.map(function (v) {
              if (!Number.isFinite(v)) return '';
              const av = Math.abs(v);
              if (av > 0 && av < 0.001) return formatNum(v, 6);
              return formatNum(v, 4);
            });
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
        drag: { x: false, y: false, setScale: false }
      },
      hooks: {
        setCursor: [onSetSweepCursor]
      }
    };
  }

  function applyRange(minVal, maxVal, sourcePlot) {
    if (!datasetReady || !blocks.length) return;
    const prevRange = activeDatasetId && Array.isArray(datasetRangeById[activeDatasetId])
      ? datasetRangeById[activeDatasetId]
      : [Number(minInput.value), Number(maxInput.value)];
    const prevMin = Number(prevRange[0]);
    const prevMax = Number(prevRange[1]);
    const [minB, maxB] = clampRange(minVal, maxVal);

    const rangeChanged = !Number.isFinite(prevMin) || !Number.isFinite(prevMax) || prevMin !== minB || prevMax !== maxB;
    minInput.value = minB;
    maxInput.value = maxB;
    if (activeDatasetId) datasetRangeById[activeDatasetId] = [minB, maxB];
    updateUrlQueryState(activeDatasetId, minB, maxB);
    updateRangeText(minB, maxB);

    syncing = true;
    for (const p of allPlots()) {
      if (p !== sourcePlot) p.setScale('x', { min: minB, max: maxB });
    }
    syncing = false;
    if (rangeChanged) rerunSavedRunsForCurrentRange();
    if (rangeChanged) resetSweepState('range changed');
    markScoreStale('range changed');
    refreshRangePresetSelection();
    refreshComparisonPlots();
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
    Array.from({ length: 4 + MAX_SAVED_RUNS }, function () { return []; }),
    reqWrap
  );

  chargedFeeOnlyPlot = new uPlot(
    makeChargedFeeOnlyOpts(width, 320),
    Array.from({ length: 2 + MAX_SAVED_RUNS }, function () { return []; }),
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
    Array.from({ length: 3 + MAX_SAVED_RUNS }, function () { return []; }),
    vaultWrap
  );

  sweepPlot = new uPlot(
    makeSweepOpts(sweepSize, sweepSize),
    [[], [], [], [], [], [], []],
    sweepWrap
  );

  setSweepUiState(false);
  setSweepStatus('Sweep idle. Taiko-only sweep: Kp/Ki/Imax across pdi + pdi+ff with Kd fixed at 0 and alpha variants (current, zero).');
  setSweepHoverText('Hover point: -');
  minInput.value = '';
  maxInput.value = '';
  if (rangeText) rangeText.textContent = 'Loading dataset...';
  if (rangeDateText) rangeDateText.textContent = '';

  document.getElementById('applyBtn').addEventListener('click', function () {
    runBusyUiTask('Applying range...', function () {
      applyRange(minInput.value, maxInput.value, null);
    });
  });

  document.getElementById('resetBtn').addEventListener('click', function () {
    runBusyUiTask('Resetting to full range...', function () {
      applyRange(MIN_BLOCK, MAX_BLOCK, null);
    });
  });

  document.getElementById('tail20kBtn').addEventListener('click', function () {
    runBusyUiTask('Applying last 20k range...', function () {
      applyRange(MAX_BLOCK - 20000, MAX_BLOCK, null);
    });
  });

  document.getElementById('tail5kBtn').addEventListener('click', function () {
    runBusyUiTask('Applying last 5k range...', function () {
      applyRange(MAX_BLOCK - 5000, MAX_BLOCK, null);
    });
  });

  document.getElementById('recalcBtn').addEventListener('click', function () {
    scheduleRecalc('Recomputing derived charts...');
  });

  saveRunBtn.addEventListener('click', function () {
    saveCurrentRun();
  });

  toggleCurrentRunBtn.addEventListener('click', function () {
    toggleCurrentRunView();
  });

  clearSavedRunsBtn.addEventListener('click', function () {
    clearSavedRuns();
  });

  recomputeSavedRunsBtn.addEventListener('click', function () {
    recomputeSavedRunsNow();
  });

  updateAssumptionsRecomputeSavedRunsBtn.addEventListener('click', function () {
    updateAssumptionsAndRecomputeSavedRunsNow();
  });

  savedRunsList.addEventListener('click', function (e) {
    const target = e.target;
    if (!(target instanceof Element)) return;
    const action = target.getAttribute('data-action');
    if (action !== 'delete') return;
    const runId = Number(target.getAttribute('data-run-id'));
    if (!Number.isFinite(runId)) return;
    deleteSavedRun(runId);
  });

  savedRunsList.addEventListener('change', function (e) {
    const target = e.target;
    if (!(target instanceof Element)) return;
    const action = target.getAttribute('data-action');
    const runId = Number(target.getAttribute('data-run-id'));
    if (!Number.isFinite(runId)) return;
    let changed = false;
    if (action === 'toggle') {
      changed = savedRunManager.updateRunById(runId, function (run) {
        run.visible = Boolean(target.checked);
      });
    } else if (action === 'lineStyle') {
      changed = savedRunManager.updateRunById(runId, function (run) {
        run.solidLine = Boolean(target.checked);
      });
    } else if (action === 'name') {
      changed = savedRunManager.updateRunById(runId, function (run) {
        run.name = normalizeRunName(target.value);
      });
    } else {
      return;
    }
    if (!changed) return;
    renderSavedRunsList();
    refreshComparisonPlots();
  });

  scoreBtn.addEventListener('click', function () {
    if (scoreStatus) scoreStatus.textContent = 'Scoring current range...';
    setUiBusy(true);
    window.setTimeout(function () {
      try {
        scoreCurrentRangeNow();
      } finally {
        setUiBusy(false);
      }
    }, 0);
  });

  function setScoreHelpOpen(isOpen) {
    if (isOpen) {
      scoreHelpModal.classList.add('open');
      scoreHelpModal.setAttribute('aria-hidden', 'false');
    } else {
      scoreHelpModal.classList.remove('open');
      scoreHelpModal.setAttribute('aria-hidden', 'true');
    }
  }

  function setControllerHelpOpen(isOpen) {
    if (isOpen) {
      controllerHelpModal.classList.add('open');
      controllerHelpModal.setAttribute('aria-hidden', 'false');
    } else {
      controllerHelpModal.classList.remove('open');
      controllerHelpModal.setAttribute('aria-hidden', 'true');
    }
  }

  controllerHelpBtn.addEventListener('click', function () {
    setControllerHelpOpen(true);
  });
  controllerHelpClose.addEventListener('click', function () {
    setControllerHelpOpen(false);
  });
  controllerHelpModal.addEventListener('click', function (e) {
    if (e.target === controllerHelpModal) {
      setControllerHelpOpen(false);
    }
  });
  scoreHelpBtn.addEventListener('click', function () {
    setScoreHelpOpen(true);
  });
  scoreHelpClose.addEventListener('click', function () {
    setScoreHelpOpen(false);
  });
  scoreHelpModal.addEventListener('click', function (e) {
    if (e.target === scoreHelpModal) {
      setScoreHelpOpen(false);
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (controllerHelpModal.classList.contains('open')) setControllerHelpOpen(false);
    if (scoreHelpModal.classList.contains('open')) setScoreHelpOpen(false);
  });

  sweepBtn.addEventListener('click', function () {
    runParameterSweep();
  });

  sweepCancelBtn.addEventListener('click', function () {
    if (!sweepRunning) return;
    sweepCancelRequested = true;
    setSweepStatus('Cancel requested. Finishing current candidate...');
  });

  sweepApplyBestBtn.addEventListener('click', function () {
    applySweepBestCandidate();
  });

  feeMechanismInput.addEventListener('change', function () {
    syncFeeMechanismUi();
    markParamsStale('Fee mechanism changed. Click Recompute derived charts.');
  });

  controllerModeInput.addEventListener('change', function () {
    applyControllerModePreset(controllerModeInput.value || 'ff');
    markParamsStale('Controller mode changed. Click Recompute derived charts.');
  });

  autoAlphaInput.addEventListener('change', function () {
    syncAutoAlphaInputs();
    markParamsStale('Auto alpha changed. Click Recompute derived charts.');
  });

  blobModeInput.addEventListener('change', function () {
    syncBlobModeUi();
    markParamsStale('Blob model changed. Click Recompute derived charts.');
  });

  l2TpsInput.addEventListener('change', function () {
    if (syncL2GasFromTps()) {
      markParamsStale('Parameter changes pending. Click Recompute derived charts.');
    }
  });

  function bindInputAndChange(inputEl, handler) {
    inputEl.addEventListener('input', handler);
    inputEl.addEventListener('change', handler);
  }

  function syncThroughputFromBlockTimeInput() {
    if (l2TpsInput && l2TpsInput.value !== 'custom') {
      syncL2GasFromTps();
    } else {
      syncTpsFromL2Gas();
    }
  }

  bindInputAndChange(l2GasPerL2BlockInput, syncTpsFromL2Gas);
  bindInputAndChange(l2BlockTimeSecInput, syncThroughputFromBlockTimeInput);

  minInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      runBusyUiTask('Applying range...', function () {
        applyRange(minInput.value, maxInput.value, null);
      });
    }
  });

  maxInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      runBusyUiTask('Applying range...', function () {
        applyRange(minInput.value, maxInput.value, null);
      });
    }
  });

  [
    postEveryBlocksInput,
    l2GasPerL2BlockInput,
    l2BlockTimeSecInput,
    l2GasScenarioInput,
    l2DemandRegimeInput,
    l1GasUsedInput,
    blobModeInput,
    numBlobsInput,
    txGasInput,
    txBytesInput,
    batchOverheadBytesInput,
    compressionRatioInput,
    blobUtilizationInput,
    minBlobsPerProposalInput,
    priorityFeeGweiInput,
    alphaGasInput,
    alphaBlobInput,
    eip1559DenominatorInput,
    arbInitialPriceGweiInput,
    arbInertiaInput,
    arbEquilUnitsInput,
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
      if (e.key === 'Enter') markParamsStale('Parameter changes pending. Click Recompute derived charts.');
    });
    el.addEventListener('change', function () {
      markParamsStale('Parameter changes pending. Click Recompute derived charts.');
    });
  });

  [
    deficitDeadbandPctInput,
    scoreWeightHealthInput,
    scoreWeightUxInput,
    healthWDrawInput,
    healthWUnderInput,
    healthWAreaInput,
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

  rangePresetInput.addEventListener('change', function () {
    const presetId = rangePresetInput.value ? String(rangePresetInput.value) : '';
    if (!presetId) return;
    runAsyncUiTask('Applying representative range...', async function () {
      await applyRangePresetById(presetId);
    });
  });

  async function initDatasets() {
    setDatasetRangeOptions();
    setRangePresetOptions();
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

  savedRunManager.loadFromStorage();
  markScoreStale('not computed yet');
  renderSavedRunsList();
  syncCurrentRunButtonLabel();
  syncFeeMechanismUi();
  syncBlobModeUi();
  initDatasets();
})();
