#!/usr/bin/env python3

import argparse
from pathlib import Path


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>L1 + L2 Fee History (Synced)</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #dbe3ef;
      --accent: #0f766e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
      color: var(--text);
      background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 35%, var(--bg) 100%);
    }
    .wrap { max-width: 1440px; margin: 18px auto; padding: 0 16px 24px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }
    h1 { margin: 0; font-size: 22px; }
    .muted { color: var(--muted); font-size: 13px; }
    select {
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 250px;
      font-size: 14px;
      background: #fff;
      color: var(--text);
    }
    iframe {
      width: 100%;
      min-height: 2200px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="row">
        <h1>L1 + L2 Fee History (Synced)</h1>
      </div>
      <div class="row">
        <label for="datasetSelect"><strong>Dataset:</strong></label>
        <select id="datasetSelect">
          <option value="current365">Current 365d (2025-02 to 2026-02)</option>
          <option value="prior365">Prior 365d (2024-02 to 2025-02)</option>
        </select>
        <span class="muted" id="datasetFileText"></span>
      </div>
      <iframe id="plotFrame" loading="eager"></iframe>
    </div>
  </div>
  <script>
    (function () {
      const pages = {
        current365: "__CURRENT_PAGE__",
        prior365: "__PRIOR_PAGE__"
      };
      const select = document.getElementById("datasetSelect");
      const frame = document.getElementById("plotFrame");
      const fileText = document.getElementById("datasetFileText");

      function getInitialDataset() {
        const params = new URLSearchParams(window.location.search);
        const v = params.get("dataset");
        if (v && pages[v]) return v;
        return "current365";
      }

      function setDataset(datasetId, pushState) {
        if (!pages[datasetId]) datasetId = "current365";
        select.value = datasetId;
        frame.src = pages[datasetId];
        fileText.textContent = "File: " + pages[datasetId];
        if (pushState) {
          const url = new URL(window.location.href);
          url.searchParams.set("dataset", datasetId);
          history.replaceState({}, "", url);
        }
      }

      select.addEventListener("change", function () {
        setDataset(select.value, true);
      });

      setDataset(getInitialDataset(), true);
    })();
  </script>
</body>
</html>
"""


def main():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate dataset switcher HTML for synced L1/L2 fee plots.")
    parser.add_argument(
        "--out-html",
        default=str(project_root / "data" / "plots" / "fee_history_l1_l2_synced.html"),
        help="Output switcher HTML path",
    )
    parser.add_argument(
        "--current-page",
        default="fee_history_l1_l2_synced_current365.html",
        help="Relative page path for current365 dataset",
    )
    parser.add_argument(
        "--prior-page",
        default="fee_history_l1_l2_synced_prior365.html",
        help="Relative page path for prior365 dataset",
    )
    args = parser.parse_args()

    html = (
        HTML_TEMPLATE.replace("__CURRENT_PAGE__", args.current_page)
        .replace("__PRIOR_PAGE__", args.prior_page)
    )
    out = Path(args.out_html).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()
