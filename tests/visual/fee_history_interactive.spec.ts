import { expect, test, type Page } from '@playwright/test';

const STABILIZE_CSS = `
#hoverText,
#savedRunsActionText,
#status {
  visibility: hidden !important;
}
`;

const MASK_SELECTORS = ['#hoverText', '#savedRunsActionText', '#status'];

function screenshotMasks(page: Page, extraSelectors: string[] = []) {
  return [...MASK_SELECTORS, ...extraSelectors].map((selector) => page.locator(selector));
}

async function waitForSimulatorReady(page: Page, datasetLabel: string) {
  await expect(page.locator('#busyOverlay')).toBeHidden({ timeout: 30_000 });
  await expect(page.locator('#status')).toContainText(`Loaded dataset: ${datasetLabel}`, {
    timeout: 30_000,
  });
  await expect(page.locator('#basePlot .uplot')).toBeVisible({ timeout: 30_000 });
}

async function openSimulator(page: Page, datasetId = 'current365', datasetLabel = 'Current 365d') {
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.goto(`/fee_history_interactive.html?dataset=${datasetId}`, { waitUntil: 'domcontentloaded' });
  await waitForSimulatorReady(page, datasetLabel);
  await page.addStyleTag({ content: STABILIZE_CSS });
}

async function recomputeDerivedCharts(page: Page) {
  await page.click('#recalcBtn');
  await expect(page.locator('#busyOverlay')).toBeHidden({ timeout: 30_000 });
  await expect(page.locator('#paramsDirtyHint')).toHaveText(/^\s*$/);
}

test.describe('fee_history_interactive visual regression', () => {
  test('current365 default view', async ({ page }) => {
    await openSimulator(page, 'current365', 'Current 365d');
    await expect(page).toHaveScreenshot('fee-history-current365-default.png', {
      mask: screenshotMasks(page),
    });
  });

  test('prior365 switched view', async ({ page }) => {
    await openSimulator(page, 'current365', 'Current 365d');
    await page.selectOption('#datasetRange', 'prior365');
    await waitForSimulatorReady(page, 'Prior 365d');
    await expect(page).toHaveScreenshot('fee-history-prior365-switched.png', {
      mask: screenshotMasks(page),
    });
  });

  test('save current run for taiko p-only and eip1559', async ({ page }) => {
    await openSimulator(page, 'current365', 'Current 365d');

    await page.selectOption('#feeMechanism', 'taiko');
    await page.fill('#ki', '0');
    await page.fill('#kd', '0');
    await page.fill('#alphaGas', '0');
    await page.fill('#alphaBlob', '0');
    await recomputeDerivedCharts(page);
    await page.click('#saveRunBtn');

    await expect(page.locator('#savedRunsStatus')).toHaveText('1 / 6 saved');
    await expect(page.locator('#savedRunsList .saved-run')).toHaveCount(1);
    await expect(page.locator('#savedRunsList')).toContainText('"feeMechanism": "taiko"');
    await expect(page.locator('#savedRunsList')).toContainText('"ki": 0');

    await page.selectOption('#feeMechanism', 'eip1559');
    await recomputeDerivedCharts(page);
    await page.click('#saveRunBtn');

    await expect(page.locator('#savedRunsStatus')).toHaveText('2 / 6 saved');
    await expect(page.locator('#savedRunsList .saved-run')).toHaveCount(2);
    await expect(page.locator('#savedRunsList')).toContainText('"feeMechanism": "eip1559"');

    await page.click('#toggleCurrentRunBtn');
    await expect(page.locator('#toggleCurrentRunBtn')).toHaveText('Show current run');

    await recomputeDerivedCharts(page);
    await expect(page.locator('#toggleCurrentRunBtn')).toHaveText('Hide current run');

    const firstColorInput = page.locator('#savedRunsList input[data-action="color"]').first();
    await firstColorInput.evaluate((el, value) => {
      const input = el as HTMLInputElement;
      input.value = value as string;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, '#ef4444');

    await expect(firstColorInput).toHaveValue('#ef4444');
    await expect(page.locator('#savedRunsList .saved-run-swatch').first()).toHaveCSS(
      'background-color',
      'rgb(239, 68, 68)',
    );

    const savedRunsPayload = await page.evaluate(() => {
      return JSON.parse(window.localStorage.getItem('fee_history_interactive_saved_runs_v1') || '{}');
    });
    expect(savedRunsPayload.runs?.[0]?.color).toBe('#ef4444');

    await page.evaluate(() => {
      const sidebar = document.querySelector('.sidebar');
      if (sidebar) sidebar.scrollTop = 0;
      const plot = document.getElementById('chargedFeeOnlyPlot');
      if (!plot) return;
      const top = plot.getBoundingClientRect().top + window.scrollY - 12;
      window.scrollTo(0, Math.max(0, top));
    });
    await expect(page).toHaveScreenshot('fee-history-saved-runs-taiko-p-and-eip1559.png', {
      mask: screenshotMasks(page, ['#savedRunsList .saved-run-meta']),
    });
  });

  test('saved run opacity dropdown persists and affects chart', async ({ page }) => {
    await openSimulator(page, 'current365', 'Current 365d');

    // Save two runs with different mechanisms
    await page.click('#saveRunBtn');
    await expect(page.locator('#savedRunsStatus')).toHaveText('1 / 6 saved');

    await page.selectOption('#feeMechanism', 'eip1559');
    await recomputeDerivedCharts(page);
    await page.click('#saveRunBtn');
    await expect(page.locator('#savedRunsStatus')).toHaveText('2 / 6 saved');

    // Both runs should default to 100% opacity
    const firstOpacity = page.locator('select[data-action="opacity"]').first();
    const secondOpacity = page.locator('select[data-action="opacity"]').nth(1);
    await expect(firstOpacity).toHaveValue('1');
    await expect(secondOpacity).toHaveValue('1');

    // Change first run to 20%, second to 100%
    await firstOpacity.selectOption('0.2');
    await secondOpacity.selectOption('1');

    // Verify dropdown reflects the change
    await expect(firstOpacity).toHaveValue('0.2');
    await expect(secondOpacity).toHaveValue('1');

    // Verify localStorage persisted the opacity values
    const payload = await page.evaluate(() => {
      return JSON.parse(window.localStorage.getItem('fee_history_interactive_saved_runs_v1') || '{}');
    });
    expect(payload.runs?.[0]?.opacity).toBe(0.2);
    expect(payload.runs?.[1]?.opacity).toBe(1);

    // Verify shared-runs links preserve opacity settings too.
    await page.click('#shareRunsBtn');
    await expect
      .poll(async () => page.evaluate(() => window.location.hash))
      .toContain('sharedRuns=');
    const sharedHash = await page.evaluate(() => window.location.hash);

    await page.goto(`/fee_history_interactive.html?dataset=current365${sharedHash}`, {
      waitUntil: 'domcontentloaded',
    });
    await waitForSimulatorReady(page, 'Current 365d');
    await page.addStyleTag({ content: STABILIZE_CSS });

    const importedFirstOpacity = page.locator('select[data-action="opacity"]').first();
    const importedSecondOpacity = page.locator('select[data-action="opacity"]').nth(1);
    await expect(importedFirstOpacity).toHaveValue('0.2');
    await expect(importedSecondOpacity).toHaveValue('1');

    // Screenshot the charged fee chart to capture different opacity rendering
    await page.evaluate(() => {
      const sidebar = document.querySelector('.sidebar');
      if (sidebar) sidebar.scrollTop = 0;
      const plot = document.getElementById('chargedFeeOnlyPlot');
      if (!plot) return;
      const top = plot.getBoundingClientRect().top + window.scrollY - 12;
      window.scrollTo(0, Math.max(0, top));
    });
    await expect(page).toHaveScreenshot('fee-history-saved-runs-opacity-20-and-100.png', {
      mask: screenshotMasks(page, ['#savedRunsList .saved-run-meta']),
    });
  });
});
