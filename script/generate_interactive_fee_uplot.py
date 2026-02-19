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
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

L1_BLOCK_TIME_SECONDS = 12
DEFAULT_MAX_DATA_POINTS = 160_000
DEFAULT_TIMESTAMP_CACHE = (
    Path(__file__).resolve().parents[1] / "data" / "eth_block_timestamp_cache.json"
)


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
        out: dict[str, int] = {}
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
            "summary_start_anchor"
            if start_ts_source == "summary"
            else "cache_start_anchor"
            if start_ts_source == "cache"
            else "rpc_start_anchor"
            if start_ts_source == "rpc"
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
            "summary_end_anchor"
            if end_ts_source == "summary"
            else "cache_end_anchor"
            if end_ts_source == "cache"
            else "rpc_end_anchor"
            if end_ts_source == "rpc"
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
        return blocks, base, blob, 1

    step = max(1, (n - 1) // max_points + 1)
    idxs = list(range(0, n, step))
    if idxs[-1] != n - 1:
        idxs.append(n - 1)

    return (
        [blocks[i] for i in idxs],
        [base[i] for i in idxs],
        [blob[i] for i in idxs],
        step,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate dataset payload JS files for the interactive fee simulator "
            "(static HTML/JS mode)."
        )
    )
    parser.add_argument(
        "--csv",
        help="Path to fee history CSV (legacy single-dataset mode if --dataset is not provided)",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help="Dataset spec in the form '<id>|<label>|<csv_path>' (repeatable)",
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
        "--out-html",
        default=None,
        help="Deprecated/no-op in static UI mode. Kept only for CLI compatibility.",
    )
    parser.add_argument(
        "--initial-dataset",
        default=None,
        help="Deprecated/no-op in static UI mode. Kept only for CLI compatibility.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Deprecated/no-op in static UI mode. Kept only for CLI compatibility.",
    )
    parser.add_argument(
        "--range-option",
        action="append",
        default=[],
        help="Deprecated/no-op in static UI mode. Kept only for CLI compatibility.",
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
    args = parser.parse_args()

    out_js = Path(args.out_js).resolve()
    out_dir = out_js.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.out_html:
        print(
            f"[info] Ignoring --out-html={args.out_html!r}; HTML generation was removed.",
            file=sys.stderr,
        )
    if args.initial_dataset:
        print(
            "[info] Ignoring --initial-dataset; static HTML/JS now own UI defaults.",
            file=sys.stderr,
        )
    if args.title:
        print(
            "[info] Ignoring --title; static HTML/JS now own UI title/content.",
            file=sys.stderr,
        )
    if args.range_option:
        print(
            "[info] Ignoring --range-option; static HTML/JS now own representative ranges.",
            file=sys.stderr,
        )

    cache_path = Path(args.timestamp_cache).resolve() if args.timestamp_cache else None
    ts_cache = load_timestamp_cache(cache_path)
    rpc_url = None if args.no_rpc_anchor else args.rpc

    dataset_specs = []
    if args.dataset:
        for raw in args.dataset:
            parts = raw.split("|", 2)
            if len(parts) != 3:
                parser.error(
                    f"Invalid --dataset value '{raw}'. Expected '<id>|<label>|<csv_path>'."
                )
            dataset_id, label, csv_raw = (parts[0].strip(), parts[1].strip(), parts[2].strip())
            if not dataset_id or not label or not csv_raw:
                parser.error(
                    f"Invalid --dataset value '{raw}'. id, label, and csv_path must be non-empty."
                )
            dataset_specs.append(
                {
                    "id": dataset_id,
                    "label": label,
                    "csv_path": Path(csv_raw).resolve(),
                }
            )
    else:
        if not args.csv:
            parser.error("Provide --csv for single-dataset mode or at least one --dataset.")
        dataset_specs.append(
            {
                "id": "default",
                "label": "Default range",
                "csv_path": Path(args.csv).resolve(),
            }
        )

    ids = [spec["id"] for spec in dataset_specs]
    if len(set(ids)) != len(ids):
        parser.error("Duplicate dataset ids are not allowed.")

    used_payload_names: set[str] = set()
    written_payloads: list[Path] = []
    for spec in dataset_specs:
        blocks, base, blob = read_fee_csv(spec["csv_path"])
        time_anchor = read_time_anchor(spec["csv_path"], blocks[0], blocks[-1], rpc_url, ts_cache)
        blocks, base, blob, _sample_step = downsample_series(blocks, base, blob, max(args.max_points, 0))

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

    save_timestamp_cache(cache_path, ts_cache)

    for payload_path in written_payloads:
        print(payload_path)


if __name__ == "__main__":
    main()
