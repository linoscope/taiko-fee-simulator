(function () {
  const BLOB_GAS_PER_BLOB = 131072;

  function toNumber(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
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

  function estimateDynamicBlobs(l2GasPerProposal, blobModel) {
    if (!(l2GasPerProposal > 0)) {
      return Math.max(0, toNumber(blobModel.minBlobsPerProposal, 0));
    }
    const txGas = Math.max(1, toNumber(blobModel.txGas, 1));
    const txBytes = Math.max(0, toNumber(blobModel.txBytes, 0));
    const batchOverheadBytes = Math.max(0, toNumber(blobModel.batchOverheadBytes, 0));
    const compressionRatio = Math.max(1e-9, toNumber(blobModel.compressionRatio, 1));
    const blobUtilization = clampNum(toNumber(blobModel.blobUtilization, 1), 1e-9, 1);
    const minBlobs = Math.max(0, toNumber(blobModel.minBlobsPerProposal, 0));

    const txCount = l2GasPerProposal / txGas;
    const uncompressedBytes = batchOverheadBytes + txCount * txBytes;
    const compressedBytes = uncompressedBytes / compressionRatio;
    const bytesPerBlob = BLOB_GAS_PER_BLOB * blobUtilization;
    const blobs = compressedBytes > 0 ? Math.ceil(compressedBytes / bytesPerBlob) : 0;
    return Math.max(minBlobs, blobs);
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
        : { rho: 0.94, sigma: 0.08, jumpProb: 0.01, jumpSigma: 0.20, lo: 0.45, hi: 2.0 };

    const rng = makeRng(0x1234abcd);
    let x = 0;
    for (let i = 0; i < n; i++) {
      x = cfg.rho * x + cfg.sigma * gaussian(rng);
      if (cfg.jumpProb > 0 && rng() < cfg.jumpProb) x += cfg.jumpSigma * gaussian(rng);
      const m = clampNum(Math.exp(x), cfg.lo, cfg.hi);
      out[i] = baseGasPerL1Block * m;
    }

    let sum = 0;
    for (let i = 0; i < n; i++) sum += out[i];
    const avg = n > 0 ? (sum / n) : baseGasPerL1Block;
    if (avg > 0) {
      const scale = baseGasPerL1Block / avg;
      for (let i = 0; i < n; i++) out[i] *= scale;
    }
    return out;
  }

  function createMechanismState(mechanism, cfg) {
    if (mechanism === 'taiko') {
      return {
        integralState: 0,
        derivFiltered: 0,
        epsilonPrev: 0,
      };
    }
    if (mechanism === 'arbitrum') {
      const minFeeGwei = cfg.minFeeWei / 1e9;
      const maxFeeGwei = cfg.maxFeeWei / 1e9;
      return {
        arbPriceGwei: clampNum(cfg.arbInitialPriceGwei, minFeeGwei, maxFeeGwei),
        arbLastSurplusEth: cfg.initialVaultEth - cfg.targetVaultEth,
      };
    }
    return {
      eip1559FeeWeiPerL2Gas: cfg.minFeeWei,
    };
  }

  function computeFeeForStep(mechanism, state, step, cfg) {
    if (mechanism === 'taiko') {
      const gasComponentWei = cfg.alphaGas * (step.baseFeeFfWei + cfg.priorityFeeWei);
      const blobComponentWei = cfg.alphaBlob * step.blobBaseFeeFfWei;

      state.integralState = clampNum(state.integralState + step.epsilon, cfg.iMin, cfg.iMax);

      const deRaw = step.localIndex > 0 ? (step.epsilon - state.epsilonPrev) : 0;
      state.derivFiltered = cfg.derivBeta * state.derivFiltered + (1 - cfg.derivBeta) * deRaw;
      const pTermWeiRaw = cfg.kp * step.epsilon * cfg.feeRangeWei;
      const pTermWei = Math.max(cfg.pTermMinWei, pTermWeiRaw);
      const iTermWei = cfg.ki * state.integralState * cfg.feeRangeWei;
      const dTermWei = cfg.kd * state.derivFiltered * cfg.feeRangeWei;
      const feedbackWei = pTermWei + iTermWei + dTermWei;
      const feedforwardWei = gasComponentWei + blobComponentWei;
      const chargedFeeWeiPerL2Gas = clampNum(feedforwardWei + feedbackWei, cfg.minFeeWei, cfg.maxFeeWei);

      return {
        chargedFeeWeiPerL2Gas,
        gasComponentWei,
        blobComponentWei,
        feedforwardWei,
        pTermWei,
        iTermWei,
        dTermWei,
        feedbackWei,
        integralState: state.integralState,
        derivative: state.derivFiltered,
      };
    }

    if (mechanism === 'arbitrum') {
      const chargedFeeWeiPerL2Gas = clampNum(state.arbPriceGwei * 1e9, cfg.minFeeWei, cfg.maxFeeWei);
      return {
        chargedFeeWeiPerL2Gas,
        gasComponentWei: 0,
        blobComponentWei: 0,
        feedforwardWei: 0,
        pTermWei: 0,
        iTermWei: 0,
        dTermWei: 0,
        feedbackWei: 0,
        integralState: 0,
        derivative: 0,
      };
    }

    const chargedFeeWeiPerL2Gas = clampNum(state.eip1559FeeWeiPerL2Gas, cfg.minFeeWei, cfg.maxFeeWei);
    return {
      chargedFeeWeiPerL2Gas,
      gasComponentWei: 0,
      blobComponentWei: 0,
      feedforwardWei: 0,
      pTermWei: 0,
      iTermWei: 0,
      dTermWei: 0,
      feedbackWei: 0,
      integralState: 0,
      derivative: 0,
    };
  }

  function applyPostUpdate(mechanism, state, step, cfg) {
    if (mechanism === 'arbitrum') {
      const unitsAllocated = Math.max(0, step.l2GasPerProposal);
      const surplusEth = step.vault - cfg.targetVaultEth;
      if (unitsAllocated > 0 && cfg.arbEquilUnits > 0 && cfg.arbInertia > 0) {
        const inertiaUnits = cfg.arbEquilUnits / cfg.arbInertia;
        const desiredDerivativeGwei = -(surplusEth * 1e9) / cfg.arbEquilUnits;
        const actualDerivativeGwei = ((surplusEth - state.arbLastSurplusEth) * 1e9) / unitsAllocated;
        const changeDerivativeGwei = desiredDerivativeGwei - actualDerivativeGwei;
        const denom = inertiaUnits + unitsAllocated;
        const priceChangeGwei = denom > 0 ? (changeDerivativeGwei * unitsAllocated) / denom : 0;
        state.arbPriceGwei = Math.max(0, state.arbPriceGwei + priceChangeGwei);
      }
      state.arbLastSurplusEth = surplusEth;
      return;
    }

    if (mechanism === 'eip1559') {
      if (cfg.targetVaultEth > 0) {
        let errorRatio = (cfg.targetVaultEth - step.vault) / cfg.targetVaultEth;
        errorRatio = clampNum(errorRatio, -8, 1);
        const adjustmentFactor = 1 + (errorRatio / cfg.eip1559Denominator);
        const nextFeeWeiPerL2Gas = state.eip1559FeeWeiPerL2Gas * adjustmentFactor;
        if (Number.isFinite(nextFeeWeiPerL2Gas)) {
          state.eip1559FeeWeiPerL2Gas = clampNum(nextFeeWeiPerL2Gas, cfg.minFeeWei, cfg.maxFeeWei);
        }
      } else {
        state.eip1559FeeWeiPerL2Gas = clampNum(state.eip1559FeeWeiPerL2Gas, cfg.minFeeWei, cfg.maxFeeWei);
      }
    }
  }

  function normalizeMechanism(mechanism) {
    if (mechanism === 'arbitrum') return 'arbitrum';
    if (mechanism === 'eip1559') return 'eip1559';
    return 'taiko';
  }

  function simulateSeries(rawCfg) {
    const cfg = Object.assign({}, rawCfg || {});
    const mechanism = normalizeMechanism(cfg.mechanism);
    const baseFeeGwei = Array.isArray(cfg.baseFeeGwei) ? cfg.baseFeeGwei : [];
    const blobFeeGwei = Array.isArray(cfg.blobFeeGwei) ? cfg.blobFeeGwei : [];
    const l2GasPerL1BlockSeries = Array.isArray(cfg.l2GasPerL1BlockSeries) ? cfg.l2GasPerL1BlockSeries : [];
    const blocks = Array.isArray(cfg.blocks) ? cfg.blocks : null;

    const seriesLen = Math.min(baseFeeGwei.length, blobFeeGwei.length, l2GasPerL1BlockSeries.length);
    const fullLength = Math.max(0, Math.min(seriesLen, Math.floor(toNumber(cfg.fullLength, seriesLen))));
    const rangeStart = clampNum(Math.floor(toNumber(cfg.rangeStart, 0)), 0, Math.max(0, fullLength - 1));
    const rangeEnd = clampNum(Math.floor(toNumber(cfg.rangeEnd, fullLength - 1)), rangeStart, Math.max(0, fullLength - 1));
    const blockIndexOffset = Math.floor(toNumber(cfg.blockIndexOffset, 0));
    const collectBreakdown = cfg.collectBreakdown === true;

    const postEveryBlocks = Math.max(1, Math.floor(toNumber(cfg.postEveryBlocks, 10)));
    const l1GasUsed = Math.max(0, toNumber(cfg.l1GasUsed, 0));
    const blobMode = cfg.blobMode === 'dynamic' ? 'dynamic' : 'fixed';
    const fixedNumBlobs = Math.max(0, toNumber(cfg.fixedNumBlobs, 0));
    const blobModel = cfg.blobModel || {};
    const priorityFeeWei = Math.max(0, toNumber(cfg.priorityFeeWei, 0));
    const dffBlocks = Math.max(0, Math.floor(toNumber(cfg.dffBlocks, 5)));
    const dfbBlocks = Math.max(1, Math.floor(toNumber(cfg.dfbBlocks, 5)));
    const derivBeta = clampNum(toNumber(cfg.derivBeta, 0.8), 0, 1);
    const kp = Math.max(0, toNumber(cfg.kp, 0));
    const ki = Math.max(0, toNumber(cfg.ki, 0));
    const kd = Math.max(0, toNumber(cfg.kd, 0));
    const pTermMinWei = toNumber(cfg.pTermMinWei, 0);
    const iMin = toNumber(cfg.iMin, 0);
    const iMax = toNumber(cfg.iMax, 10);
    const minFeeWei = Math.max(0, toNumber(cfg.minFeeWei, 0));
    const maxFeeWei = Math.max(minFeeWei, toNumber(cfg.maxFeeWei, minFeeWei));
    const feeRangeWei = Math.max(0, maxFeeWei - minFeeWei);
    const initialVaultEth = Math.max(0, toNumber(cfg.initialVaultEth, 0));
    const targetVaultEth = Math.max(0, toNumber(cfg.targetVaultEth, 0));
    const alphaGas = Math.max(0, toNumber(cfg.alphaGas, 0));
    const alphaBlob = Math.max(0, toNumber(cfg.alphaBlob, 0));
    const eip1559Denominator = Math.max(1, Math.floor(toNumber(cfg.eip1559Denominator, 8)));
    const arbInitialPriceGwei = Math.max(0, toNumber(cfg.arbInitialPriceGwei, 0));
    const arbInertia = Math.max(1, Math.floor(toNumber(cfg.arbInertia, 10)));
    const arbEquilUnits = Math.max(1, toNumber(cfg.arbEquilUnits, 1));

    const simCfg = {
      alphaGas,
      alphaBlob,
      kp,
      ki,
      kd,
      pTermMinWei,
      iMin: Math.min(iMin, iMax),
      iMax: Math.max(iMin, iMax),
      derivBeta,
      minFeeWei,
      maxFeeWei,
      feeRangeWei,
      initialVaultEth,
      targetVaultEth,
      priorityFeeWei,
      postEveryBlocks,
      l1GasUsed,
      blobMode,
      fixedNumBlobs,
      blobModel,
      dffBlocks,
      dfbBlocks,
      eip1559Denominator,
      arbInitialPriceGwei,
      arbInertia,
      arbEquilUnits,
    };

    const chargedFeeGwei = new Array(fullLength).fill(null);
    const vaultEth = new Array(fullLength).fill(null);
    const localN = fullLength > 0 ? (rangeEnd - rangeStart + 1) : 0;
    const localVaultSeries = new Array(localN).fill(initialVaultEth);
    const out = {
      chargedFeeGwei,
      vaultEth,
    };

    if (collectBreakdown) {
      out.gasCostEth = new Array(fullLength).fill(null);
      out.blobCostEth = new Array(fullLength).fill(null);
      out.postingCostEth = new Array(fullLength).fill(null);
      out.requiredFeeGwei = new Array(fullLength).fill(null);
      out.gasFeeComponentGwei = new Array(fullLength).fill(null);
      out.blobFeeComponentGwei = new Array(fullLength).fill(null);
      out.feedforwardFeeGwei = new Array(fullLength).fill(null);
      out.pTermFeeGwei = new Array(fullLength).fill(null);
      out.iTermFeeGwei = new Array(fullLength).fill(null);
      out.dTermFeeGwei = new Array(fullLength).fill(null);
      out.feedbackFeeGwei = new Array(fullLength).fill(null);
      out.postingRevenueAtPostEth = new Array(fullLength).fill(null);
      out.postingPnLEth = new Array(fullLength).fill(null);
      out.postBreakEvenFlag = new Array(fullLength).fill(null);
      out.deficitEth = new Array(fullLength).fill(null);
      out.epsilon = new Array(fullLength).fill(null);
      out.derivative = new Array(fullLength).fill(null);
      out.integral = new Array(fullLength).fill(null);
      out.clampState = new Array(fullLength).fill(null);
      out.postingPnLBlocks = [];
    }

    let vault = initialVaultEth;
    let pendingRevenueEth = 0;
    const mechState = createMechanismState(mechanism, simCfg);

    for (let local = 0; local < localN; local++) {
      const i = rangeStart + local;
      const globalIndex = blockIndexOffset + i;
      const baseFeeWei = toNumber(baseFeeGwei[i], 0) * 1e9;
      const blobBaseFeeWei = toNumber(blobFeeGwei[i], 0) * 1e9;
      const ffIndex = Math.max(rangeStart, i - dffBlocks);
      const baseFeeFfWei = toNumber(baseFeeGwei[ffIndex], 0) * 1e9;
      const blobBaseFeeFfWei = toNumber(blobFeeGwei[ffIndex], 0) * 1e9;

      const l2GasPerL1Block = Math.max(0, toNumber(l2GasPerL1BlockSeries[i], 0));
      const l2GasPerProposal = l2GasPerL1Block * postEveryBlocks;
      const numBlobs = blobMode === 'dynamic'
        ? estimateDynamicBlobs(l2GasPerProposal, blobModel)
        : fixedNumBlobs;
      const gasCostWei = l1GasUsed * (baseFeeWei + priorityFeeWei);
      const blobCostWei = numBlobs * BLOB_GAS_PER_BLOB * blobBaseFeeWei;
      const totalCostWei = gasCostWei + blobCostWei;

      const fbLocal = local - dfbBlocks;
      const observedVault = fbLocal >= 0 ? localVaultSeries[fbLocal] : initialVaultEth;
      const deficitEth = targetVaultEth - observedVault;
      const epsilon = targetVaultEth > 0 ? (deficitEth / targetVaultEth) : 0;

      const feeParts = computeFeeForStep(
        mechanism,
        mechState,
        {
          localIndex: local,
          epsilon,
          baseFeeFfWei,
          blobBaseFeeFfWei,
        },
        simCfg
      );
      const chargedFeeWeiPerL2Gas = feeParts.chargedFeeWeiPerL2Gas;
      chargedFeeGwei[i] = chargedFeeWeiPerL2Gas / 1e9;

      const l2RevenueEthPerBlock = (chargedFeeWeiPerL2Gas * l2GasPerL1Block) / 1e18;
      pendingRevenueEth += l2RevenueEthPerBlock;

      const posted = ((globalIndex + 1) % postEveryBlocks) === 0;
      if (posted) {
        const postingRevenueEth = pendingRevenueEth;
        pendingRevenueEth = 0;
        vault += postingRevenueEth;
        vault -= totalCostWei / 1e18;

        applyPostUpdate(
          mechanism,
          mechState,
          {
            vault,
            l2GasPerProposal,
          },
          simCfg
        );

        if (collectBreakdown) {
          out.postingRevenueAtPostEth[i] = postingRevenueEth;
          out.postingPnLEth[i] = postingRevenueEth - (totalCostWei / 1e18);
          out.postBreakEvenFlag[i] = postingRevenueEth + 1e-12 >= (totalCostWei / 1e18);
          const postingBlock = blocks && Number.isFinite(blocks[i]) ? blocks[i] : globalIndex;
          out.postingPnLBlocks.push(postingBlock);
        }
      } else if (collectBreakdown) {
        out.postingRevenueAtPostEth[i] = null;
        out.postingPnLEth[i] = null;
        out.postBreakEvenFlag[i] = null;
      }

      if (mechanism === 'taiko') {
        mechState.epsilonPrev = epsilon;
      }

      localVaultSeries[local] = vault;
      vaultEth[i] = vault;

      if (collectBreakdown) {
        let clampState = 'none';
        if (chargedFeeWeiPerL2Gas <= minFeeWei + 1e-9) clampState = 'min';
        else if (chargedFeeWeiPerL2Gas >= maxFeeWei - 1e-9) clampState = 'max';

        out.gasCostEth[i] = gasCostWei / 1e18;
        out.blobCostEth[i] = blobCostWei / 1e18;
        out.postingCostEth[i] = totalCostWei / 1e18;
        out.requiredFeeGwei[i] = l2GasPerProposal > 0 ? (totalCostWei / l2GasPerProposal) / 1e9 : null;
        out.gasFeeComponentGwei[i] = feeParts.gasComponentWei / 1e9;
        out.blobFeeComponentGwei[i] = feeParts.blobComponentWei / 1e9;
        out.feedforwardFeeGwei[i] = feeParts.feedforwardWei / 1e9;
        out.pTermFeeGwei[i] = feeParts.pTermWei / 1e9;
        out.iTermFeeGwei[i] = feeParts.iTermWei / 1e9;
        out.dTermFeeGwei[i] = feeParts.dTermWei / 1e9;
        out.feedbackFeeGwei[i] = feeParts.feedbackWei / 1e9;
        out.deficitEth[i] = deficitEth;
        out.epsilon[i] = epsilon;
        out.derivative[i] = feeParts.derivative;
        out.integral[i] = feeParts.integralState;
        out.clampState[i] = clampState;
      }
    }

    return out;
  }

  window.FeeSimCore = {
    constants: {
      BLOB_GAS_PER_BLOB,
    },
    clampNum,
    estimateDynamicBlobs,
    buildL2GasSeries,
    simulateSeries,
  };
})();
