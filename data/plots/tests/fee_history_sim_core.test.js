const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadSimCore() {
  const filePath = path.resolve(__dirname, '..', 'fee_history_sim_core.js');
  const src = fs.readFileSync(filePath, 'utf8');
  const context = {
    window: {},
    console,
    Math,
    Number,
    Array,
    Object,
    JSON,
    Date,
  };
  vm.runInNewContext(src, context, { filename: filePath });
  assert.ok(context.window.FeeSimCore, 'FeeSimCore is not attached to window');
  return context.window.FeeSimCore;
}

function approxEqual(a, b, eps = 1e-12) {
  return Math.abs(a - b) <= eps;
}

function assertFiniteOrNullArray(arr, label) {
  assert.ok(Array.isArray(arr), `${label} must be an array`);
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (v == null) continue;
    assert.ok(Number.isFinite(v), `${label}[${i}] must be finite or null`);
  }
}

function baseConfigForMechanism(mechanism) {
  const n = 16;
  return {
    mechanism,
    baseFeeGwei: Array.from({ length: n }, (_, i) => 1 + (i % 3) * 0.25),
    blobFeeGwei: Array.from({ length: n }, (_, i) => 2 + (i % 4) * 0.1),
    l2GasPerL1BlockSeries: Array.from({ length: n }, () => 140000),
    fullLength: n,
    rangeStart: 0,
    rangeEnd: n - 1,
    blockIndexOffset: 0,
    postEveryBlocks: 2,
    l1GasUsed: 100000,
    blobMode: 'fixed',
    fixedNumBlobs: 1,
    blobModel: {
      txGas: 70000,
      txBytes: 120,
      batchOverheadBytes: 1200,
      compressionRatio: 1,
      blobUtilization: 0.95,
      minBlobsPerProposal: 1,
    },
    priorityFeeWei: 1e9,
    dffBlocks: 2,
    dfbBlocks: 2,
    derivBeta: 0.8,
    kp: 1.0,
    ki: 0.1,
    kd: 0.0,
    pTermMinWei: 0,
    iMin: -10,
    iMax: 10,
    minFeeWei: 0.01e9,
    maxFeeWei: 1.0e9,
    alphaGas: 0.01,
    alphaBlob: 0.15,
    initialVaultEth: 10,
    targetVaultEth: 10,
    eip1559Denominator: 8,
    arbInitialPriceGwei: 0.02,
    arbInertia: 10,
    arbEquilUnits: 96000000,
    collectBreakdown: true,
  };
}

test('buildL2GasSeries is deterministic and constant mode stays constant', () => {
  const sim = loadSimCore();
  const one = sim.buildL2GasSeries(128, 42000, 'bursty');
  const two = sim.buildL2GasSeries(128, 42000, 'bursty');
  assert.deepEqual(one, two);

  const constant = sim.buildL2GasSeries(32, 777, 'constant');
  assert.equal(constant.length, 32);
  for (const x of constant) assert.equal(x, 777);
});

test('taiko simulation keeps charged fee clamped and emits finite breakdown values', () => {
  const sim = loadSimCore();
  const cfg = baseConfigForMechanism('taiko');
  const out = sim.simulateSeries(cfg);

  assert.equal(out.chargedFeeGwei.length, cfg.fullLength);
  assert.equal(out.vaultEth.length, cfg.fullLength);
  for (let i = 0; i < out.chargedFeeGwei.length; i++) {
    const v = out.chargedFeeGwei[i];
    assert.ok(Number.isFinite(v), `chargedFeeGwei[${i}] must be finite`);
    assert.ok(v >= 0.01 - 1e-12, `chargedFeeGwei[${i}] below min`);
    assert.ok(v <= 1.0 + 1e-12, `chargedFeeGwei[${i}] above max`);
  }
  assertFiniteOrNullArray(out.requiredFeeGwei, 'requiredFeeGwei');
  assertFiniteOrNullArray(out.postingPnLEth, 'postingPnLEth');
  assertFiniteOrNullArray(out.deficitEth, 'deficitEth');
  assertFiniteOrNullArray(out.epsilon, 'epsilon');
  assertFiniteOrNullArray(out.integral, 'integral');
});

test('taiko clamps dfbBlocks to 1 when callers pass 0', () => {
  const sim = loadSimCore();
  const cfgZero = baseConfigForMechanism('taiko');
  cfgZero.postEveryBlocks = 1;
  cfgZero.initialVaultEth = 1;
  cfgZero.targetVaultEth = 10;
  cfgZero.l1GasUsed = 250000;
  cfgZero.dfbBlocks = 0;

  const cfgOne = { ...cfgZero, dfbBlocks: 1 };
  const outZero = sim.simulateSeries(cfgZero);
  const outOne = sim.simulateSeries(cfgOne);

  assert.deepEqual(outZero.chargedFeeGwei, outOne.chargedFeeGwei);
  assert.deepEqual(outZero.vaultEth, outOne.vaultEth);
  assert.deepEqual(outZero.epsilon, outOne.epsilon);
});

test('eip1559 mode moves fee away from minimum under sustained deficit', () => {
  const sim = loadSimCore();
  const cfg = baseConfigForMechanism('eip1559');
  cfg.postEveryBlocks = 1;
  cfg.initialVaultEth = 1;
  cfg.targetVaultEth = 10;
  cfg.l1GasUsed = 200000;
  cfg.maxFeeWei = 2e9;
  cfg.minFeeWei = 0.01e9;
  cfg.l2GasPerL1BlockSeries = cfg.l2GasPerL1BlockSeries.map(() => 50000);

  const out = sim.simulateSeries(cfg);
  assert.ok(approxEqual(out.chargedFeeGwei[0], 0.01), 'first step should start at min fee');
  const maxSeen = Math.max.apply(null, out.chargedFeeGwei);
  assert.ok(maxSeen > 0.01, 'eip1559 fee should increase above min under deficit');
  assert.ok(maxSeen <= 2.0 + 1e-12, 'eip1559 fee should respect max clamp');
});

test('arbitrum mode responds to surplus/deficit direction', () => {
  const sim = loadSimCore();
  const lowVaultCfg = baseConfigForMechanism('arbitrum');
  lowVaultCfg.postEveryBlocks = 1;
  lowVaultCfg.initialVaultEth = 2;
  lowVaultCfg.targetVaultEth = 10;
  lowVaultCfg.arbInitialPriceGwei = 0.05;
  lowVaultCfg.maxFeeWei = 2e9;

  const highVaultCfg = baseConfigForMechanism('arbitrum');
  highVaultCfg.postEveryBlocks = 1;
  highVaultCfg.initialVaultEth = 20;
  highVaultCfg.targetVaultEth = 10;
  highVaultCfg.arbInitialPriceGwei = 0.05;
  highVaultCfg.maxFeeWei = 2e9;

  const lowOut = sim.simulateSeries(lowVaultCfg);
  const highOut = sim.simulateSeries(highVaultCfg);
  assert.ok(lowOut.chargedFeeGwei[4] > highOut.chargedFeeGwei[4], 'deficit case should charge more than surplus case');
});

test('sliced replay configuration matches full-array ranged simulation', () => {
  const sim = loadSimCore();
  const n = 30;
  const i0 = 7;
  const i1 = 22;
  const fullCfg = baseConfigForMechanism('taiko');
  fullCfg.fullLength = n;
  fullCfg.baseFeeGwei = Array.from({ length: n }, (_, i) => 1 + (i % 7) * 0.2);
  fullCfg.blobFeeGwei = Array.from({ length: n }, (_, i) => 2 + (i % 5) * 0.15);
  fullCfg.l2GasPerL1BlockSeries = Array.from({ length: n }, (_, i) => 100000 + (i % 3) * 5000);
  fullCfg.rangeStart = i0;
  fullCfg.rangeEnd = i1;
  fullCfg.blockIndexOffset = 0;
  fullCfg.collectBreakdown = false;

  const replayCfg = {
    ...fullCfg,
    baseFeeGwei: fullCfg.baseFeeGwei.slice(i0, i1 + 1),
    blobFeeGwei: fullCfg.blobFeeGwei.slice(i0, i1 + 1),
    l2GasPerL1BlockSeries: fullCfg.l2GasPerL1BlockSeries.slice(i0, i1 + 1),
    fullLength: i1 - i0 + 1,
    rangeStart: 0,
    rangeEnd: i1 - i0,
    blockIndexOffset: i0,
  };

  const ranged = sim.simulateSeries(fullCfg);
  const replay = sim.simulateSeries(replayCfg);
  const rangedChargedSlice = ranged.chargedFeeGwei.slice(i0, i1 + 1);
  const rangedVaultSlice = ranged.vaultEth.slice(i0, i1 + 1);

  assert.deepEqual(replay.chargedFeeGwei, rangedChargedSlice);
  assert.deepEqual(replay.vaultEth, rangedVaultSlice);
});
