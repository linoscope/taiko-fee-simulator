#!/usr/bin/env python3

"""Generate dataset payload JS files for the interactive fee simulator.

This script intentionally does NOT generate or overwrite UI source files:
- data/plots/fee_history_interactive.html
- data/plots/fee_history_interactive_app.js

It only refreshes dataset payload files consumed by the static UI.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

L1_BLOCK_TIME_SECONDS = 12
DEFAULT_MAX_DATA_POINTS = 160_000


def read_fee_csv(csv_path: Path):
    blocks: list[int] = []
    base: list[float] = []
    blob: list[float] = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            blocks.append(int(row["block_number"]))
            base.append(int(row["base_fee_per_gas_wei"]) / 1e9)
            blob.append(int(row["base_fee_per_blob_gas_wei"]) / 1e9)

    if not blocks:
        raise ValueError(f"No rows found in {csv_path}")

    return blocks, base, blob


def read_time_anchor(csv_path: Path, min_block: int, max_block: int):
    summary_path = csv_path.with_name(csv_path.stem + "_summary.json")
    default = {
        "has_anchor": False,
        "anchor_block": 0,
        "anchor_ts_sec": 0,
        "seconds_per_block": float(L1_BLOCK_TIME_SECONDS),
        "source": "default_12s",
    }

    summary: dict = {}
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
        return {
            "has_anchor": True,
            "anchor_block": int(start_block),
            "anchor_ts_sec": int(start_ts),
            "seconds_per_block": float(seconds_per_block),
            "source": "summary_start_anchor",
        }

    if end_block is not None and end_ts is not None:
        return {
            "has_anchor": True,
            "anchor_block": int(end_block),
            "anchor_ts_sec": int(end_ts),
            "seconds_per_block": float(seconds_per_block),
            "source": "summary_end_anchor",
        }

    return default


def sanitize_dataset_id(dataset_id: str):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", dataset_id.strip())
    return cleaned or "dataset"


def build_dataset_payload_js(dataset_id, blocks, base, blob, time_anchor):
    payload = {
        "blocks": blocks,
        "baseFeeGwei": base,
        "blobFeeGwei": blob,
        "timeAnchor": time_anchor,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    dataset_id_json = json.dumps(str(dataset_id))
    return f"""(function () {{
  if (!window.__feeDatasetPayloads) {{
    window.__feeDatasetPayloads = Object.create(null);
  }}
  window.__feeDatasetPayloads[{dataset_id_json}] = {payload_json};
}})();
"""


def downsample_series(blocks, base, blob, max_points: int):
    n = len(blocks)
    if max_points <= 0 or n <= max_points:
        return blocks, base, blob

    step = max(1, (n - 1) // max_points + 1)
    idxs = list(range(0, n, step))
    if idxs[-1] != n - 1:
        idxs.append(n - 1)

    return [blocks[i] for i in idxs], [base[i] for i in idxs], [blob[i] for i in idxs]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate dataset payload JS files for the interactive fee simulator "
            "(static HTML/JS mode)."
        )
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help="Dataset spec in the form '<id>|<csv_path>' (repeatable).",
    )
    parser.add_argument(
        "--out-js",
        required=True,
        help=(
            "Static app JS path used only to derive payload filenames and output directory. "
            "This file is no longer overwritten."
        ),
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=DEFAULT_MAX_DATA_POINTS,
        help=(
            "Maximum points per dataset payload for browser rendering/simulation. "
            "Use 0 to disable downsampling."
        ),
    )
    args = parser.parse_args()

    out_js = Path(args.out_js).resolve()
    out_dir = out_js.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.dataset:
        parser.error("Provide at least one --dataset value.")

    dataset_specs = []
    for raw in args.dataset:
        parts = raw.split("|", 1)
        if len(parts) != 2:
            parser.error(
                f"Invalid --dataset value '{raw}'. Expected '<id>|<csv_path>'."
            )
        dataset_id, csv_raw = (parts[0].strip(), parts[1].strip())
        if not dataset_id or not csv_raw:
            parser.error(
                f"Invalid --dataset value '{raw}'. id and csv_path must be non-empty."
            )
        dataset_specs.append(
            {
                "id": dataset_id,
                "csv_path": Path(csv_raw).resolve(),
            }
        )

    ids = [spec["id"] for spec in dataset_specs]
    if len(set(ids)) != len(ids):
        parser.error("Duplicate dataset ids are not allowed.")

    used_payload_names: set[str] = set()
    written_payloads: list[Path] = []
    for spec in dataset_specs:
        blocks, base, blob = read_fee_csv(spec["csv_path"])
        time_anchor = read_time_anchor(spec["csv_path"], blocks[0], blocks[-1])
        blocks, base, blob = downsample_series(blocks, base, blob, max(args.max_points, 0))

        safe_id = sanitize_dataset_id(spec["id"])
        payload_name = f"{out_js.stem}_data_{safe_id}.js"
        if payload_name in used_payload_names:
            parser.error(
                f"Dataset id collision after sanitization for '{spec['id']}'. "
                "Please use distinct ids."
            )
        used_payload_names.add(payload_name)

        payload_path = out_dir / payload_name
        payload_path.write_text(build_dataset_payload_js(spec["id"], blocks, base, blob, time_anchor))
        written_payloads.append(payload_path)

    for payload_path in written_payloads:
        print(payload_path)


if __name__ == "__main__":
    main()
