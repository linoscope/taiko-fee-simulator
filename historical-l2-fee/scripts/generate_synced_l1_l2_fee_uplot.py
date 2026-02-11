#!/usr/bin/env python3

import argparse
import csv
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def parse_iso_to_unix(raw: str | None):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(dt.timestamp())


def unix_to_iso(ts: int):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def count_csv_rows(csv_path: Path):
    with csv_path.open(newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def compute_stride(total_rows: int, max_points: int):
    if total_rows <= 0:
        return 1
    if max_points <= 0:
        return 1
    return max(1, math.ceil(total_rows / max_points))


def summarize_segment_stats(values: list[float]):
    if not values:
        return {"min": None, "p50": None, "p90": None, "max": None}
    sorted_vals = sorted(values)
    p90_idx = int(0.9 * (len(sorted_vals) - 1))
    return {
        "min": min(sorted_vals),
        "p50": statistics.median(sorted_vals),
        "p90": sorted_vals[p90_idx],
        "max": max(sorted_vals),
    }


def read_sampled_rows(csv_path: Path, stride: int):
    sampled = []
    last_row = None
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            last_row = row
            if idx % stride == 0:
                sampled.append(row)
    if last_row is not None:
        if not sampled or sampled[-1] != last_row:
            sampled.append(last_row)
    return sampled


def rpc_batch_get_block_timestamps(
    rpc_url: str,
    block_numbers: list[int],
    request_batch_size: int,
    min_request_interval_sec: float,
    retries: int = 8,
):
    if not block_numbers:
        return {}

    session = requests.Session()
    headers = {"content-type": "application/json"}
    out = {}
    last_request_at = 0.0

    def rpc_single_block_timestamp(block_number: int):
        payload = {
            "jsonrpc": "2.0",
            "id": block_number,
            "method": "eth_getBlockByNumber",
            "params": [hex(block_number), False],
        }
        last_exc = None
        for retry_i in range(retries):
            try:
                resp = session.post(rpc_url, json=payload, headers=headers, timeout=60)
                resp.raise_for_status()
                item = resp.json()
                if "error" in item:
                    raise RuntimeError(item["error"])
                result = item.get("result")
                if not result or "timestamp" not in result:
                    raise RuntimeError(f"Missing timestamp for block {block_number}")
                return int(result["timestamp"], 16)
            except Exception as exc:
                last_exc = exc
                retry_wait = 0.8 * (retry_i + 1)
                status_code = None
                retry_after = None
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    status_code = exc.response.status_code
                    retry_after_raw = exc.response.headers.get("Retry-After")
                    if retry_after_raw:
                        try:
                            retry_after = float(retry_after_raw)
                        except ValueError:
                            retry_after = None
                if status_code == 429:
                    retry_wait = max(retry_wait, 2.0 * (2**retry_i))
                    if retry_after is not None:
                        retry_wait = max(retry_wait, retry_after)
                    retry_wait = min(retry_wait, 90.0)
                time.sleep(retry_wait)
        raise RuntimeError(
            f"Failed fetching block timestamp for {block_number} from {rpc_url}"
        ) from last_exc

    for i in range(0, len(block_numbers), request_batch_size):
        now = time.monotonic()
        wait = min_request_interval_sec - (now - last_request_at)
        if wait > 0:
            time.sleep(wait)

        chunk = block_numbers[i : i + request_batch_size]
        reqs = [
            {
                "jsonrpc": "2.0",
                "id": bn,
                "method": "eth_getBlockByNumber",
                "params": [hex(bn), False],
            }
            for bn in chunk
        ]

        last_err = None
        fallback_to_single = False
        for retry_i in range(retries):
            try:
                resp = session.post(rpc_url, json=reqs, headers=headers, timeout=60)
                last_request_at = time.monotonic()
                resp.raise_for_status()
                arr = resp.json()
                if not isinstance(arr, list):
                    raise RuntimeError(f"Expected batch array response, got: {type(arr)}")

                by_id = {}
                for item in arr:
                    if "error" in item:
                        raise RuntimeError(item["error"])
                    bid = int(item["id"])
                    result = item.get("result")
                    if not result or "timestamp" not in result:
                        raise RuntimeError(f"Missing timestamp for block id={bid}")
                    by_id[bid] = int(result["timestamp"], 16)

                missing = [bn for bn in chunk if bn not in by_id]
                if missing:
                    raise RuntimeError(f"Missing block results for ids: {missing[:5]}")

                out.update(by_id)
                break
            except Exception as exc:
                last_err = exc
                retry_wait = 0.8 * (retry_i + 1)
                status_code = None
                retry_after = None
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    status_code = exc.response.status_code
                    retry_after_raw = exc.response.headers.get("Retry-After")
                    if retry_after_raw:
                        try:
                            retry_after = float(retry_after_raw)
                        except ValueError:
                            retry_after = None
                if status_code == 400:
                    # Some public RPC providers do not support JSON-RPC batching.
                    fallback_to_single = True
                    break
                if status_code == 429:
                    retry_wait = max(retry_wait, 2.0 * (2**retry_i))
                    if retry_after is not None:
                        retry_wait = max(retry_wait, retry_after)
                    retry_wait = min(retry_wait, 90.0)
                time.sleep(retry_wait)

        if fallback_to_single:
            per_call_interval = min_request_interval_sec
            for bn in chunk:
                now = time.monotonic()
                wait = per_call_interval - (now - last_request_at)
                if wait > 0:
                    time.sleep(wait)
                out[bn] = rpc_single_block_timestamp(bn)
                last_request_at = time.monotonic()
            continue

        if len(out) < i + len(chunk):
            raise RuntimeError(
                f"Failed fetching block timestamps from {rpc_url} after retries; "
                f"chunk start={chunk[0]} size={len(chunk)}"
            ) from last_err

    return out


def build_anchor_blocks(first_block: int, last_block: int, anchor_stride_blocks: int):
    if first_block > last_block:
        raise ValueError(f"Invalid block range: {first_block}..{last_block}")
    stride = max(1, int(anchor_stride_blocks))
    anchors = {first_block, last_block}
    aligned = ((first_block + stride - 1) // stride) * stride
    for bn in range(aligned, last_block, stride):
        anchors.add(bn)
    return sorted(anchors)


def interpolate_blocks_from_anchor_timestamps(blocks: list[int], anchor_ts_by_block: dict[int, int]):
    if not blocks:
        return [], {"min": None, "p50": None, "p90": None, "max": None}
    anchor_blocks = sorted(anchor_ts_by_block.keys())
    if len(anchor_blocks) < 2:
        only = anchor_blocks[0]
        return [anchor_ts_by_block[only] for _ in blocks], {"min": None, "p50": None, "p90": None, "max": None}

    min_anchor = anchor_blocks[0]
    max_anchor = anchor_blocks[-1]
    if blocks[0] < min_anchor or blocks[-1] > max_anchor:
        raise ValueError(
            f"Anchor range {min_anchor}..{max_anchor} does not cover block range {blocks[0]}..{blocks[-1]}"
        )

    x_sec = []
    seg_idx = 0
    last_seg_idx = len(anchor_blocks) - 2

    for block in blocks:
        while seg_idx < last_seg_idx and block > anchor_blocks[seg_idx + 1]:
            seg_idx += 1
        left_block = anchor_blocks[seg_idx]
        right_block = anchor_blocks[seg_idx + 1]
        left_ts = anchor_ts_by_block[left_block]
        right_ts = anchor_ts_by_block[right_block]

        if block <= left_block:
            ts = left_ts
        elif block >= right_block:
            ts = right_ts
        else:
            span_blocks = right_block - left_block
            if span_blocks <= 0:
                ts = left_ts
            else:
                frac = (block - left_block) / span_blocks
                ts = left_ts + frac * (right_ts - left_ts)
        x_sec.append(int(round(ts)))

    spb_values = []
    for i in range(1, len(anchor_blocks)):
        db = anchor_blocks[i] - anchor_blocks[i - 1]
        dt = anchor_ts_by_block[anchor_blocks[i]] - anchor_ts_by_block[anchor_blocks[i - 1]]
        if db > 0 and dt >= 0:
            spb_values.append(dt / db)

    return x_sec, summarize_segment_stats(spb_values)


def resolve_l1_time_mapping(summary_path: Path, first_block: int, last_block: int):
    if not summary_path.exists():
        raise FileNotFoundError(f"L1 summary file not found: {summary_path}")

    with summary_path.open() as f:
        summary = json.load(f)

    start_block = int(summary.get("start_block", first_block))
    end_block = int(summary.get("end_block", last_block))

    start_ts = parse_iso_to_unix(summary.get("window_start_timestamp_utc"))
    if start_ts is None:
        start_ts = parse_iso_to_unix(summary.get("assumed_start_timestamp_utc"))

    end_ts = parse_iso_to_unix(summary.get("window_end_timestamp_utc"))
    if end_ts is None:
        end_ts = parse_iso_to_unix(summary.get("latest_block_timestamp_utc"))

    if start_ts is None and end_ts is None:
        raise ValueError(
            f"Could not resolve timestamps from summary: {summary_path}. "
            "Expected at least one of window_start/assumed_start and window_end/latest."
        )

    if start_ts is None:
        span_blocks = end_block - start_block
        start_ts = end_ts - int(round(span_blocks * 12))
    if end_ts is None:
        span_blocks = end_block - start_block
        end_ts = start_ts + int(round(span_blocks * 12))

    span_blocks = end_block - start_block
    if span_blocks <= 0:
        sec_per_block = 12.0
    else:
        sec_per_block = (end_ts - start_ts) / span_blocks
        if sec_per_block <= 0:
            sec_per_block = 12.0

    return {
        "method": "global_linear_from_summary_window",
        "start_block": start_block,
        "end_block": end_block,
        "start_ts": int(start_ts),
        "end_ts": int(end_ts),
        "seconds_per_block": float(sec_per_block),
    }


def l1_block_to_estimated_ts(block_number: int, time_map: dict):
    offset_blocks = block_number - time_map["start_block"]
    ts = time_map["start_ts"] + offset_blocks * time_map["seconds_per_block"]
    return int(round(ts))


def read_l1_sampled_series(
    csv_path: Path,
    summary_path: Path,
    target_points: int,
    l1_rpc: str | None,
    l1_anchor_stride_blocks: int,
    l1_request_batch_size: int,
    l1_min_request_interval: float,
):
    total_rows = count_csv_rows(csv_path)
    stride = compute_stride(total_rows, target_points)
    sampled_rows = read_sampled_rows(csv_path, stride)
    if not sampled_rows:
        raise ValueError(f"No rows read from L1 CSV: {csv_path}")

    first_block = int(sampled_rows[0]["block_number"])
    last_block = int(sampled_rows[-1]["block_number"])
    blocks = [int(row["block_number"]) for row in sampled_rows]

    x_sec = None
    time_map = None
    if l1_rpc:
        anchor_blocks = build_anchor_blocks(first_block, last_block, l1_anchor_stride_blocks)
        anchor_ts = rpc_batch_get_block_timestamps(
            rpc_url=l1_rpc,
            block_numbers=anchor_blocks,
            request_batch_size=max(1, int(l1_request_batch_size)),
            min_request_interval_sec=max(0.0, float(l1_min_request_interval)),
        )
        x_sec, segment_stats = interpolate_blocks_from_anchor_timestamps(blocks, anchor_ts)
        spb_values = []
        for i in range(1, len(anchor_blocks)):
            db = anchor_blocks[i] - anchor_blocks[i - 1]
            dt = anchor_ts[anchor_blocks[i]] - anchor_ts[anchor_blocks[i - 1]]
            if db > 0 and dt >= 0:
                spb_values.append(dt / db)
        time_map = {
            "method": "sampled_anchor_timestamps_from_rpc_interpolation",
            "rpc_url": l1_rpc,
            "start_block": first_block,
            "end_block": last_block,
            "start_ts": int(anchor_ts[anchor_blocks[0]]),
            "end_ts": int(anchor_ts[anchor_blocks[-1]]),
            "anchor_count": len(anchor_blocks),
            "anchor_stride_blocks": max(1, int(l1_anchor_stride_blocks)),
            "seconds_per_block_estimate": (statistics.mean(spb_values) if spb_values else None),
            "segment_seconds_per_block_stats": segment_stats,
        }
    else:
        time_map = resolve_l1_time_mapping(summary_path, first_block, last_block)
        x_sec = [l1_block_to_estimated_ts(block_number, time_map) for block_number in blocks]

    base_fee_gwei = []
    blob_fee_gwei = []

    for idx, row in enumerate(sampled_rows):
        block_number = blocks[idx]
        base_fee_wei = int(row["base_fee_per_gas_wei"])
        blob_fee_wei = int(row["base_fee_per_blob_gas_wei"])

        base_fee_gwei.append(round(base_fee_wei / 1e9, 9))
        blob_fee_gwei.append(round(blob_fee_wei / 1e9, 9))

    return {
        "blocks": blocks,
        "x_sec": x_sec,
        "base_fee_gwei": base_fee_gwei,
        "blob_fee_gwei": blob_fee_gwei,
        "row_count_total": total_rows,
        "row_count_sampled": len(sampled_rows),
        "stride": stride,
        "time_map": time_map,
    }


def parse_l2_row_timestamp(row: dict):
    if row.get("timestamp_unix"):
        return int(row["timestamp_unix"])
    if row.get("timestamp_utc"):
        ts = parse_iso_to_unix(row["timestamp_utc"])
        if ts is not None:
            return ts
    raise ValueError("L2 row is missing timestamp_unix/timestamp_utc")


def read_l2_sampled_series(csv_path: Path, target_points: int):
    total_rows = count_csv_rows(csv_path)
    stride = compute_stride(total_rows, target_points)
    sampled_rows = read_sampled_rows(csv_path, stride)
    if not sampled_rows:
        raise ValueError(f"No rows read from L2 CSV: {csv_path}")

    blocks = []
    x_sec = []
    base_fee_gwei = []

    for row in sampled_rows:
        blocks.append(int(row["block_number"]))
        x_sec.append(parse_l2_row_timestamp(row))
        base_fee_gwei.append(round(int(row["base_fee_per_gas_wei"]) / 1e9, 9))

    segment_spb = []
    for i in range(1, len(blocks)):
        db = blocks[i] - blocks[i - 1]
        dt = x_sec[i] - x_sec[i - 1]
        if db > 0 and dt >= 0:
            segment_spb.append(dt / db)

    segment_stats = summarize_segment_stats(segment_spb)

    return {
        "blocks": blocks,
        "x_sec": x_sec,
        "base_fee_gwei": base_fee_gwei,
        "row_count_total": total_rows,
        "row_count_sampled": len(sampled_rows),
        "stride": stride,
        "segment_seconds_per_block_stats": segment_stats,
    }


def read_json(path: Path):
    with path.open() as f:
        return json.load(f)


def find_latest_nontrivial_csv(data_dir: Path, pattern: str):
    candidates = sorted(data_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            if count_csv_rows(path) >= 2:
                return path
        except Exception:
            continue
    return None


def build_html(title: str, data_js_filename: str):
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <link rel="stylesheet" href="./uPlot.min.css" />
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #dbe3ef;
      --accent: #0f766e;
      --accent-2: #2563eb;
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
    h1 { margin: 0 0 10px; font-size: 22px; }
    .sub { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
    label { font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }
    input[type=datetime-local] { padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; min-width: 210px; }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      padding: 6px 10px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
    }
    button.primary { border-color: transparent; background: var(--accent); color: #fff; }
    .meta { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
    .range-text { margin-left: auto; font-size: 12px; color: var(--muted); }
    .status { margin: 4px 0 0; min-height: 18px; font-size: 12px; color: #b45309; }
    .plot {
      width: 100%;
      min-height: 300px;
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 6px;
      background: #fff;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>__TITLE__</h1>
      <p class="sub">
        Drag in any chart to zoom x-range. All charts stay synchronized on UTC timestamps.
      </p>
      <div class="controls">
        <label>Start (local) <input id="startTime" type="datetime-local" /></label>
        <label>End (local) <input id="endTime" type="datetime-local" /></label>
        <button class="primary" id="applyBtn">Apply range</button>
        <button id="resetBtn">Reset full range</button>
        <button id="last30dBtn">Last 30d</button>
        <button id="last7dBtn">Last 7d</button>
        <span class="range-text" id="rangeText"></span>
      </div>
      <div class="meta">
        <span id="metaL1"></span>
        <span id="metaL2Arb"></span>
        <span id="metaL2Base"></span>
        <span id="metaL2Op"></span>
        <span id="metaL2Scroll"></span>
      </div>
      <div class="status" id="status"></div>
      <div id="l1BasePlot" class="plot"></div>
      <div id="l1BlobPlot" class="plot"></div>
      <div id="l2ArbBasePlot" class="plot"></div>
      <div id="l2BaseBasePlot" class="plot"></div>
      <div id="l2OpBasePlot" class="plot"></div>
      <div id="l2ScrollBasePlot" class="plot"></div>
    </div>
  </div>
  <script src="./uPlot.iife.min.js"></script>
  <script src="./__DATA_JS__"></script>
  <script>
(function () {
  const payload = window.__l1L2SyncedPayload;
  const statusEl = document.getElementById('status');
  const rangeTextEl = document.getElementById('rangeText');
  const metaL1El = document.getElementById('metaL1');
  const metaL2ArbEl = document.getElementById('metaL2Arb');
  const metaL2BaseEl = document.getElementById('metaL2Base');
  const metaL2OpEl = document.getElementById('metaL2Op');
  const metaL2ScrollEl = document.getElementById('metaL2Scroll');
  const startInput = document.getElementById('startTime');
  const endInput = document.getElementById('endTime');

  function setStatus(msg) {
    statusEl.textContent = msg || '';
  }

  if (!payload) {
    setStatus('Missing data payload. Ensure data JS is loaded.');
    return;
  }
  if (!window.uPlot) {
    setStatus('uPlot failed to load. Open this file from data/plots so local JS files resolve.');
    return;
  }

  const l1 = payload.l1;
  const l2Arb = payload.l2Arb;
  const l2BaseChain = payload.l2Base;
  const l2ScrollChain = payload.l2Scroll;
  const l2OpChain = payload.l2Optimism;
  const meta = payload.meta || {};

  const l1X = l1.xSec;
  const l1Base = l1.baseFeeGwei;
  const l1Blob = l1.blobFeeGwei;
  const l2ArbX = l2Arb.xSec;
  const l2ArbBase = l2Arb.baseFeeGwei;
  const l2BaseX = l2BaseChain.xSec;
  const l2BaseFee = l2BaseChain.baseFeeGwei;
  const l2ScrollX = l2ScrollChain.xSec;
  const l2ScrollFee = l2ScrollChain.baseFeeGwei;
  const l2OpX = l2OpChain.xSec;
  const l2OpFee = l2OpChain.baseFeeGwei;

  if (!l1X.length || !l2ArbX.length || !l2BaseX.length || !l2ScrollX.length || !l2OpX.length) {
    setStatus('Dataset is empty.');
    return;
  }

  const MIN_X = Math.max(l1X[0], l2ArbX[0], l2BaseX[0], l2ScrollX[0], l2OpX[0]);
  const MAX_X = Math.min(
    l1X[l1X.length - 1],
    l2ArbX[l2ArbX.length - 1],
    l2BaseX[l2BaseX.length - 1],
    l2ScrollX[l2ScrollX.length - 1],
    l2OpX[l2OpX.length - 1]
  );

  if (!(MIN_X < MAX_X)) {
    setStatus('Invalid time overlap between datasets.');
    return;
  }

  metaL1El.textContent = `L1: ${l1X.length.toLocaleString()} points (stride ${meta.l1.stride} blocks)`;
  metaL2ArbEl.textContent = `L2 Arbitrum: ${l2ArbX.length.toLocaleString()} points (stride ${meta.l2Arbitrum.stride} sampled rows)`;
  metaL2BaseEl.textContent = `L2 Base: ${l2BaseX.length.toLocaleString()} points (stride ${meta.l2Base.stride} sampled rows)`;
  metaL2OpEl.textContent = `L2 Optimism: ${l2OpX.length.toLocaleString()} points (stride ${meta.l2Optimism.stride} sampled rows)`;
  metaL2ScrollEl.textContent = `L2 Scroll: ${l2ScrollX.length.toLocaleString()} points (stride ${meta.l2Scroll.stride} sampled rows)`;

  const l1BaseWrap = document.getElementById('l1BasePlot');
  const l1BlobWrap = document.getElementById('l1BlobPlot');
  const l2ArbBaseWrap = document.getElementById('l2ArbBasePlot');
  const l2BaseBaseWrap = document.getElementById('l2BaseBasePlot');
  const l2OpBaseWrap = document.getElementById('l2OpBasePlot');
  const l2ScrollBaseWrap = document.getElementById('l2ScrollBasePlot');

  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function secToUtcIso(sec) {
    return new Date(sec * 1000).toISOString().replace('.000Z', 'Z');
  }

  function secToLocalInputValue(sec) {
    const d = new Date(sec * 1000);
    return (
      String(d.getFullYear()) + '-' +
      pad2(d.getMonth() + 1) + '-' +
      pad2(d.getDate()) + 'T' +
      pad2(d.getHours()) + ':' +
      pad2(d.getMinutes())
    );
  }

  function localInputValueToSec(value) {
    if (!value) return null;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return null;
    return Math.floor(ms / 1000);
  }

  function formatAxisSec(sec) {
    const d = new Date(sec * 1000);
    return (
      String(d.getUTCFullYear()) + '-' +
      pad2(d.getUTCMonth() + 1) + '-' +
      pad2(d.getUTCDate()) + '\\n' +
      pad2(d.getUTCHours()) + ':' +
      pad2(d.getUTCMinutes()) + ':' +
      pad2(d.getUTCSeconds())
    );
  }

  function formatGwei(value, maxDecimals) {
    if (!Number.isFinite(value)) return '--';
    const abs = Math.abs(value);
    let decimals = 2;
    if (abs === 0) decimals = 0;
    else if (abs < 1e-6) decimals = Math.min(maxDecimals, 9);
    else if (abs < 1e-5) decimals = Math.min(maxDecimals, 8);
    else if (abs < 1e-4) decimals = Math.min(maxDecimals, 7);
    else if (abs < 1e-3) decimals = Math.min(maxDecimals, 6);
    else if (abs < 1e-2) decimals = Math.min(maxDecimals, 5);
    else if (abs < 1e-1) decimals = Math.min(maxDecimals, 4);
    else if (abs < 1) decimals = Math.min(maxDecimals, 4);
    else if (abs < 10) decimals = Math.min(maxDecimals, 3);
    else if (abs < 100) decimals = Math.min(maxDecimals, 2);
    else if (abs < 1000) decimals = Math.min(maxDecimals, 1);
    else decimals = 0;
    return value.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: decimals,
    });
  }

  function clampRange(a, b) {
    let lo = Number(a);
    let hi = Number(b);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [MIN_X, MAX_X];
    if (lo > hi) {
      const t = lo;
      lo = hi;
      hi = t;
    }
    lo = Math.max(MIN_X, Math.min(MAX_X, Math.floor(lo)));
    hi = Math.max(MIN_X, Math.min(MAX_X, Math.floor(hi)));
    if (lo === hi) hi = Math.min(MAX_X, lo + 1);
    return [lo, hi];
  }

  function updateRangeUi(lo, hi) {
    startInput.value = secToLocalInputValue(lo);
    endInput.value = secToLocalInputValue(hi);
    const days = (hi - lo) / 86400;
    rangeTextEl.textContent = `UTC ${secToUtcIso(lo)} -> ${secToUtcIso(hi)} (${days.toFixed(2)} days)`;
  }

  function makeOpts(title, seriesLabel, strokeColor, width, height, valueMaxDecimals) {
    const maxDecimals = Number.isFinite(valueMaxDecimals) ? valueMaxDecimals : 4;
    return {
      title: title,
      width: width,
      height: height,
      scales: { x: { time: false } },
      series: [
        {},
        {
          label: seriesLabel,
          stroke: strokeColor,
          width: 1.2,
          value: (u, v) => formatGwei(v, maxDecimals)
        }
      ],
      axes: [
        { label: 'UTC time', values: (u, splits) => splits.map(formatAxisSec) },
        { label: 'gwei', values: (u, splits) => splits.map((v) => formatGwei(v, maxDecimals)) }
      ],
      cursor: { drag: { x: true, y: false, setScale: true } },
      hooks: { setScale: [onSetScale] }
    };
  }

  function plotWidthFor(wrap) {
    return Math.max(540, wrap.clientWidth - 8);
  }

  let syncing = false;
  let l1BasePlot = null;
  let l1BlobPlot = null;
  let l2ArbBasePlot = null;
  let l2BaseBasePlot = null;
  let l2OpBasePlot = null;
  let l2ScrollBasePlot = null;
  

  function allPlots() {
    return [l1BasePlot, l1BlobPlot, l2ArbBasePlot, l2BaseBasePlot, l2OpBasePlot, l2ScrollBasePlot].filter(Boolean);
  }

  function setAllXRange(minSec, maxSec, sourcePlot) {
    const clamped = clampRange(minSec, maxSec);
    const lo = clamped[0];
    const hi = clamped[1];

    syncing = true;
    for (const p of allPlots()) {
      if (sourcePlot && p === sourcePlot) continue;
      p.setScale('x', { min: lo, max: hi });
    }
    syncing = false;
    updateRangeUi(lo, hi);
  }

  function onSetScale(u, key) {
    if (key !== 'x' || syncing) return;
    const lo = u.scales.x.min;
    const hi = u.scales.x.max;
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
    setAllXRange(lo, hi, u);
  }

  function resizePlots() {
    const w1 = plotWidthFor(l1BaseWrap);
    const w2 = plotWidthFor(l1BlobWrap);
    const w3 = plotWidthFor(l2ArbBaseWrap);
    const w4 = plotWidthFor(l2BaseBaseWrap);
    const w5 = plotWidthFor(l2OpBaseWrap);
    const w6 = plotWidthFor(l2ScrollBaseWrap);
    if (l1BasePlot) l1BasePlot.setSize({ width: w1, height: 300 });
    if (l1BlobPlot) l1BlobPlot.setSize({ width: w2, height: 300 });
    if (l2ArbBasePlot) l2ArbBasePlot.setSize({ width: w3, height: 300 });
    if (l2BaseBasePlot) l2BaseBasePlot.setSize({ width: w4, height: 300 });
    if (l2OpBasePlot) l2OpBasePlot.setSize({ width: w5, height: 300 });
    if (l2ScrollBasePlot) l2ScrollBasePlot.setSize({ width: w6, height: 300 });
  }

  l1BasePlot = new uPlot(
    makeOpts('L1 Base Fee History', 'L1 base fee (gwei)', '#2563eb', plotWidthFor(l1BaseWrap), 300, 4),
    [l1X, l1Base],
    l1BaseWrap
  );

  l1BlobPlot = new uPlot(
    makeOpts('L1 Blob Fee History', 'L1 blob fee (gwei)', '#f97316', plotWidthFor(l1BlobWrap), 300, 4),
    [l1X, l1Blob],
    l1BlobWrap
  );

  l2ArbBasePlot = new uPlot(
    makeOpts('L2 Base Fee History (Arbitrum)', 'L2 base fee (gwei)', '#0f766e', plotWidthFor(l2ArbBaseWrap), 300, 5),
    [l2ArbX, l2ArbBase],
    l2ArbBaseWrap
  );

  l2BaseBasePlot = new uPlot(
    makeOpts('L2 Base Fee History (Base)', 'L2 base fee (gwei)', '#dc2626', plotWidthFor(l2BaseBaseWrap), 300, 5),
    [l2BaseX, l2BaseFee],
    l2BaseBaseWrap
  );

  l2OpBasePlot = new uPlot(
    makeOpts('L2 Base Fee History (Optimism)', 'L2 base fee (gwei)', '#0891b2', plotWidthFor(l2OpBaseWrap), 300, 5),
    [l2OpX, l2OpFee],
    l2OpBaseWrap
  );

  l2ScrollBasePlot = new uPlot(
    makeOpts('L2 Base Fee History (Scroll)', 'L2 base fee (gwei)', '#16a34a', plotWidthFor(l2ScrollBaseWrap), 300, 9),
    [l2ScrollX, l2ScrollFee],
    l2ScrollBaseWrap
  );

  updateRangeUi(MIN_X, MAX_X);
  setAllXRange(MIN_X, MAX_X, null);

  document.getElementById('applyBtn').addEventListener('click', function () {
    const startSec = localInputValueToSec(startInput.value);
    const endSec = localInputValueToSec(endInput.value);
    setAllXRange(startSec, endSec, null);
  });

  document.getElementById('resetBtn').addEventListener('click', function () {
    setAllXRange(MIN_X, MAX_X, null);
  });

  document.getElementById('last30dBtn').addEventListener('click', function () {
    setAllXRange(MAX_X - 30 * 86400, MAX_X, null);
  });

  document.getElementById('last7dBtn').addEventListener('click', function () {
    setAllXRange(MAX_X - 7 * 86400, MAX_X, null);
  });

  startInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      const startSec = localInputValueToSec(startInput.value);
      const endSec = localInputValueToSec(endInput.value);
      setAllXRange(startSec, endSec, null);
    }
  });

  endInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      const startSec = localInputValueToSec(startInput.value);
      const endSec = localInputValueToSec(endInput.value);
      setAllXRange(startSec, endSec, null);
    }
  });

  let resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizePlots, 120);
  });

  setStatus('');
})();
  </script>
</body>
</html>
"""
    return html.replace("__TITLE__", title).replace("__DATA_JS__", data_js_filename)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a synced uPlot HTML for L1 base/blob + L2 (Arbitrum/Base/Scroll/Optimism) base fee histories on timestamp axis."
    )
    project_root = Path(__file__).resolve().parents[1]
    l1_data_dir = project_root / "data" / "l1"
    l2_data_dir = project_root / "data" / "l2"
    plots_dir = project_root / "data" / "plots"

    parser.add_argument("--l1-csv", default=None, help="Path to L1 fee CSV")
    parser.add_argument("--l1-summary", default=None, help="Path to L1 summary JSON")
    parser.add_argument("--l2-csv", default=None, help="Path to sampled Arbitrum fee CSV")
    parser.add_argument("--l2-base-csv", default=None, help="Path to sampled Base fee CSV")
    parser.add_argument("--l2-scroll-csv", default=None, help="Path to sampled Scroll fee CSV")
    parser.add_argument("--l2-optimism-csv", default=None, help="Path to sampled Optimism fee CSV")
    parser.add_argument(
        "--l1-rpc",
        default=None,
        help="Optional L1 RPC URL for timestamp anchors (default: from L1 summary rpc field)",
    )
    parser.add_argument(
        "--no-l1-rpc-anchor",
        action="store_true",
        help="Disable L1 RPC timestamp anchoring and use linear summary mapping fallback",
    )
    parser.add_argument(
        "--l1-anchor-stride-blocks",
        type=int,
        default=5_000,
        help="L1 anchor spacing in blocks when building timestamp interpolation",
    )
    parser.add_argument(
        "--l1-request-batch-size",
        type=int,
        default=120,
        help="eth_getBlockByNumber calls per L1 RPC batch request",
    )
    parser.add_argument(
        "--l1-min-request-interval",
        type=float,
        default=0.35,
        help="Minimum seconds between L1 batch RPC requests",
    )
    parser.add_argument("--l1-max-points", type=int, default=260_000, help="Max points to keep for L1 series")
    parser.add_argument("--l2-max-points", type=int, default=300_000, help="Max points to keep for L2 series")
    parser.add_argument(
        "--title",
        default="L1 + L2 Fee History (Synced by Time)",
        help="HTML title",
    )
    parser.add_argument(
        "--out-html",
        default=str(plots_dir / "fee_history_l1_l2_synced_current365.html"),
        help="Output HTML path",
    )
    parser.add_argument(
        "--out-data-js",
        default=str(plots_dir / "fee_history_l1_l2_synced_data_current365.js"),
        help="Output data JS path",
    )
    parser.add_argument(
        "--out-summary",
        default=str(plots_dir / "fee_history_l1_l2_synced_current365_summary.json"),
        help="Output summary JSON path",
    )
    args = parser.parse_args()

    if args.l1_csv:
        l1_csv_path = Path(args.l1_csv).resolve()
    else:
        l1_csv_path = find_latest_nontrivial_csv(l1_data_dir, "eth_l1_fee_365d_*.csv")
    if l1_csv_path is None:
        raise FileNotFoundError("Could not resolve L1 CSV. Pass --l1-csv.")

    if args.l1_summary:
        l1_summary_path = Path(args.l1_summary).resolve()
    else:
        l1_summary_path = l1_csv_path.with_name(l1_csv_path.stem + "_summary.json")
    if not l1_summary_path.exists():
        raise FileNotFoundError(
            f"Could not resolve L1 summary JSON at {l1_summary_path}. Pass --l1-summary."
        )

    if args.l2_csv:
        l2_arb_csv_path = Path(args.l2_csv).resolve()
    else:
        l2_arb_csv_path = find_latest_nontrivial_csv(l2_data_dir, "arb1_fee_*_step*_*.csv")
    if l2_arb_csv_path is None:
        raise FileNotFoundError("Could not resolve Arbitrum L2 CSV. Pass --l2-csv.")

    if args.l2_base_csv:
        l2_base_csv_path = Path(args.l2_base_csv).resolve()
    else:
        l2_base_csv_path = find_latest_nontrivial_csv(l2_data_dir, "base_fee_*_step*_*.csv")
    if l2_base_csv_path is None:
        raise FileNotFoundError("Could not resolve Base L2 CSV. Pass --l2-base-csv.")

    if args.l2_scroll_csv:
        l2_scroll_csv_path = Path(args.l2_scroll_csv).resolve()
    else:
        l2_scroll_csv_path = find_latest_nontrivial_csv(l2_data_dir, "scroll_fee_*_step*_*.csv")
    if l2_scroll_csv_path is None:
        raise FileNotFoundError("Could not resolve Scroll L2 CSV. Pass --l2-scroll-csv.")

    if args.l2_optimism_csv:
        l2_optimism_csv_path = Path(args.l2_optimism_csv).resolve()
    else:
        l2_optimism_csv_path = find_latest_nontrivial_csv(l2_data_dir, "optimism_fee_*_step*_*.csv")
    if l2_optimism_csv_path is None:
        raise FileNotFoundError("Could not resolve Optimism L2 CSV. Pass --l2-optimism-csv.")

    l1_summary = read_json(l1_summary_path)
    if args.no_l1_rpc_anchor:
        l1_rpc = None
    else:
        l1_rpc = args.l1_rpc or l1_summary.get("rpc")

    l1 = read_l1_sampled_series(
        l1_csv_path,
        l1_summary_path,
        args.l1_max_points,
        l1_rpc=l1_rpc,
        l1_anchor_stride_blocks=args.l1_anchor_stride_blocks,
        l1_request_batch_size=args.l1_request_batch_size,
        l1_min_request_interval=args.l1_min_request_interval,
    )
    l2_arb = read_l2_sampled_series(l2_arb_csv_path, args.l2_max_points)
    l2_base = read_l2_sampled_series(l2_base_csv_path, args.l2_max_points)
    l2_scroll = read_l2_sampled_series(l2_scroll_csv_path, args.l2_max_points)
    l2_optimism = read_l2_sampled_series(l2_optimism_csv_path, args.l2_max_points)

    window_min = max(
        l1["x_sec"][0],
        l2_arb["x_sec"][0],
        l2_base["x_sec"][0],
        l2_scroll["x_sec"][0],
        l2_optimism["x_sec"][0],
    )
    window_max = min(
        l1["x_sec"][-1],
        l2_arb["x_sec"][-1],
        l2_base["x_sec"][-1],
        l2_scroll["x_sec"][-1],
        l2_optimism["x_sec"][-1],
    )
    if not (window_min < window_max):
        raise ValueError("No overlapping timestamp range between L1 and L2 series.")

    payload = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "title": args.title,
            "window": {
                "start_ts": window_min,
                "end_ts": window_max,
                "start_utc": unix_to_iso(window_min),
                "end_utc": unix_to_iso(window_max),
            },
            "l1": {
                "source_csv": str(l1_csv_path),
                "source_summary": str(l1_summary_path),
                "row_count_total": l1["row_count_total"],
                "row_count_sampled": l1["row_count_sampled"],
                "stride": l1["stride"],
                "time_mapping_method": l1["time_map"]["method"],
                "summary_window_start_utc": l1_summary.get("window_start_timestamp_utc")
                or l1_summary.get("assumed_start_timestamp_utc"),
                "summary_window_end_utc": l1_summary.get("window_end_timestamp_utc"),
                "seconds_per_block_estimate": l1["time_map"].get("seconds_per_block")
                or l1["time_map"].get("seconds_per_block_estimate"),
                "anchor_count": l1["time_map"].get("anchor_count"),
                "anchor_stride_blocks": l1["time_map"].get("anchor_stride_blocks"),
                "segment_seconds_per_block_stats": l1["time_map"].get("segment_seconds_per_block_stats"),
            },
            "l2Arbitrum": {
                "source_csv": str(l2_arb_csv_path),
                "row_count_total": l2_arb["row_count_total"],
                "row_count_sampled": l2_arb["row_count_sampled"],
                "stride": l2_arb["stride"],
                "time_mapping_method": "sampled anchor timestamps from RPC; interpolation between anchors for unsampled blocks",
                "segment_seconds_per_block_stats": l2_arb["segment_seconds_per_block_stats"],
            },
            "l2Base": {
                "source_csv": str(l2_base_csv_path),
                "row_count_total": l2_base["row_count_total"],
                "row_count_sampled": l2_base["row_count_sampled"],
                "stride": l2_base["stride"],
                "time_mapping_method": "sampled anchor timestamps from RPC; interpolation between anchors for unsampled blocks",
                "segment_seconds_per_block_stats": l2_base["segment_seconds_per_block_stats"],
            },
            "l2Scroll": {
                "source_csv": str(l2_scroll_csv_path),
                "row_count_total": l2_scroll["row_count_total"],
                "row_count_sampled": l2_scroll["row_count_sampled"],
                "stride": l2_scroll["stride"],
                "time_mapping_method": "sampled anchor timestamps from RPC; interpolation between anchors for unsampled blocks",
                "segment_seconds_per_block_stats": l2_scroll["segment_seconds_per_block_stats"],
            },
            "l2Optimism": {
                "source_csv": str(l2_optimism_csv_path),
                "row_count_total": l2_optimism["row_count_total"],
                "row_count_sampled": l2_optimism["row_count_sampled"],
                "stride": l2_optimism["stride"],
                "time_mapping_method": "sampled anchor timestamps from RPC; interpolation between anchors for unsampled blocks",
                "segment_seconds_per_block_stats": l2_optimism["segment_seconds_per_block_stats"],
            },
        },
        "l1": {
            "xSec": l1["x_sec"],
            "baseFeeGwei": l1["base_fee_gwei"],
            "blobFeeGwei": l1["blob_fee_gwei"],
        },
        "l2Arb": {
            "xSec": l2_arb["x_sec"],
            "baseFeeGwei": l2_arb["base_fee_gwei"],
        },
        "l2Base": {
            "xSec": l2_base["x_sec"],
            "baseFeeGwei": l2_base["base_fee_gwei"],
        },
        "l2Scroll": {
            "xSec": l2_scroll["x_sec"],
            "baseFeeGwei": l2_scroll["base_fee_gwei"],
        },
        "l2Optimism": {
            "xSec": l2_optimism["x_sec"],
            "baseFeeGwei": l2_optimism["base_fee_gwei"],
        },
    }

    out_html_path = Path(args.out_html).resolve()
    out_data_js_path = Path(args.out_data_js).resolve()
    out_summary_path = Path(args.out_summary).resolve()

    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_data_js_path.parent.mkdir(parents=True, exist_ok=True)
    out_summary_path.parent.mkdir(parents=True, exist_ok=True)

    data_js_payload = json.dumps(payload, separators=(",", ":"))
    data_js = "(function(){window.__l1L2SyncedPayload=" + data_js_payload + ";})();\n"
    out_data_js_path.write_text(data_js)

    html = build_html(args.title, out_data_js_path.name)
    out_html_path.write_text(html)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "html": str(out_html_path),
        "data_js": str(out_data_js_path),
        "l1_csv": str(l1_csv_path),
        "l1_summary": str(l1_summary_path),
        "l2_arb_csv": str(l2_arb_csv_path),
        "l2_base_csv": str(l2_base_csv_path),
        "l2_scroll_csv": str(l2_scroll_csv_path),
        "l2_optimism_csv": str(l2_optimism_csv_path),
        "window_start_utc": unix_to_iso(window_min),
        "window_end_utc": unix_to_iso(window_max),
        "l1_points": len(l1["x_sec"]),
        "l2_arb_points": len(l2_arb["x_sec"]),
        "l2_base_points": len(l2_base["x_sec"]),
        "l2_scroll_points": len(l2_scroll["x_sec"]),
        "l2_optimism_points": len(l2_optimism["x_sec"]),
        "l1_stride": l1["stride"],
        "l2_arb_stride": l2_arb["stride"],
        "l2_base_stride": l2_base["stride"],
        "l2_scroll_stride": l2_scroll["stride"],
        "l2_optimism_stride": l2_optimism["stride"],
        "l1_time_mapping_method": l1["time_map"]["method"],
        "l1_seconds_per_block_estimate": l1["time_map"].get("seconds_per_block")
        or l1["time_map"].get("seconds_per_block_estimate"),
        "l1_anchor_count": l1["time_map"].get("anchor_count"),
        "l1_anchor_stride_blocks": l1["time_map"].get("anchor_stride_blocks"),
        "l1_segment_seconds_per_block_stats": l1["time_map"].get("segment_seconds_per_block_stats"),
        "l2_arb_segment_seconds_per_block_stats": l2_arb["segment_seconds_per_block_stats"],
        "l2_base_segment_seconds_per_block_stats": l2_base["segment_seconds_per_block_stats"],
        "l2_scroll_segment_seconds_per_block_stats": l2_scroll["segment_seconds_per_block_stats"],
        "l2_optimism_segment_seconds_per_block_stats": l2_optimism["segment_seconds_per_block_stats"],
    }
    out_summary_path.write_text(json.dumps(summary, indent=2))

    print(f"WROTE {out_data_js_path}")
    print(f"WROTE {out_html_path}")
    print(f"WROTE {out_summary_path}")


if __name__ == "__main__":
    main()
