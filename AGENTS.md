# AGENT.md

## Visual Regression Tests (Playwright)

### How to run

```bash
npm run visual:test
```

If baselines must be intentionally updated:

```bash
npm run visual:update
```

To review results in the Playwright HTML report:

```bash
npm run visual:report
```

HTML report location:

`/home/lin/workspace/taiko-fee-simulator/playwright-report/index.html`

### Policy

- Always run visual tests when touching anything that can impact UI (HTML, CSS, frontend JS, rendering logic, chart layout, viewport behavior, or UI state flows).
- If a visual regression is detected, ask the user whether the regression is expected or not, and point them to the Playwright HTML report path above for review before updating snapshots.
