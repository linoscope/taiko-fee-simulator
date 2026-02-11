#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import time
from datetime import datetime, timezone

import requests


def parse_iso_utc(value: str) -> int:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp())


def rpc_call(session: requests.Session, rpc_url: str, method: str, params: list, rid: int = 1, retries: int = 6):
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    headers = {"content-type": "application/json"}
    last_err = None
    for i in range(retries):
        try:
            resp = session.post(rpc_url, json=payload, headers=headers, timeout=45)
            resp.raise_for_status()
            obj = resp.json()
            if "error" in obj:
                raise RuntimeError(obj["error"])
            return obj["result"]
        except Exception as exc:
            last_err = exc
            time.sleep(0.35 * (i + 1))
    raise last_err


def rpc_batch_get_blocks(
    session: requests.Session,
    rpc_url: str,
    block_numbers: list[int],
    request_batch_size: int,
    min_request_interval_sec: float,
    retries: int = 10,
):
    headers = {"content-type": "application/json"}
    out = []
    last_request_at = 0.0

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
        for retry_i in range(retries):
            try:
                resp = session.post(rpc_url, json=reqs, headers=headers, timeout=60)
                last_request_at = time.monotonic()
                resp.raise_for_status()
                arr = resp.json()
                by_id = {}
                for item in arr:
                    if "error" in item:
                        raise RuntimeError(item["error"])
                    by_id[int(item["id"])] = item["result"]
                missing = [bn for bn in chunk if bn not in by_id]
                if missing:
                    raise RuntimeError(f"Missing block results for IDs: {missing[:5]}")
                out.extend(by_id[bn] for bn in chunk)
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
                if status_code == 429:
                    retry_wait = max(retry_wait, 2.0 * (2**retry_i))
                    if retry_after is not None:
                        retry_wait = max(retry_wait, retry_after)
                    retry_wait = min(retry_wait, 90.0)
                time.sleep(retry_wait)
        else:
            raise last_err

    return out


def block_to_row(block_obj: dict):
    bn = int(block_obj["number"], 16)
    ts = int(block_obj["timestamp"], 16)
    base_fee = int(block_obj.get("baseFeePerGas", "0x0"), 16)
    gas_used = int(block_obj.get("gasUsed", "0x0"), 16)
    gas_limit = int(block_obj.get("gasLimit", "0x0"), 16)
    ratio = (gas_used / gas_limit) if gas_limit else 0.0
    return {
        "block_number": bn,
        "timestamp_unix": ts,
        "timestamp_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "base_fee_per_gas_wei": base_fee,
        "gas_used": gas_used,
        "gas_limit": gas_limit,
        "gas_used_ratio": ratio,
    }


def load_window_from_summary(summary_path: str):
    with open(summary_path) as f:
        j = json.load(f)

    start_key = "window_start_timestamp_utc" if "window_start_timestamp_utc" in j else "assumed_start_timestamp_utc"
    end_key = "window_end_timestamp_utc" if "window_end_timestamp_utc" in j else "latest_block_timestamp_utc"

    start_ts = parse_iso_utc(j[start_key])
    end_ts = parse_iso_utc(j[end_key])
    return start_ts, end_ts, start_key, end_key


def find_first_block_at_or_after_ts(session: requests.Session, rpc_url: str, target_ts: int, lo: int, hi: int):
    while lo < hi:
        mid = (lo + hi) // 2
        blk = rpc_call(session, rpc_url, "eth_getBlockByNumber", [hex(mid), False], rid=mid)
        ts = int(blk["timestamp"], 16)
        if ts < target_ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def find_last_block_at_or_before_ts(session: requests.Session, rpc_url: str, target_ts: int, lo: int, hi: int):
    while lo < hi:
        mid = (lo + hi + 1) // 2
        blk = rpc_call(session, rpc_url, "eth_getBlockByNumber", [hex(mid), False], rid=mid)
        ts = int(blk["timestamp"], 16)
        if ts <= target_ts:
            lo = mid
        else:
            hi = mid - 1
    return lo


def percentile(values: list[float], p: float):
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Arbitrum historical base fee/gas usage over a time window with throttled batched RPC."
    )
    parser.add_argument("--rpc", default="https://arb1.arbitrum.io/rpc", help="Arbitrum JSON-RPC endpoint")
    parser.add_argument(
        "--window-summary",
        default=os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "l1",
            "eth_l1_fee_365d_20260207T042811Z_summary_true_window.json",
        ),
        help="Summary JSON to reuse window bounds from (default: current repo file)",
    )
    parser.add_argument("--start-ts", type=int, default=None, help="Optional start unix timestamp (overrides --window-summary)")
    parser.add_argument("--end-ts", type=int, default=None, help="Optional end unix timestamp (overrides --window-summary)")
    parser.add_argument(
        "--sample-seconds",
        type=int,
        default=60,
        help="Approximate sampling interval in seconds. Blocks are sampled by a derived fixed block stride.",
    )
    parser.add_argument(
        "--request-batch-size",
        type=int,
        default=150,
        help="Number of eth_getBlockByNumber calls per HTTP batch request.",
    )
    parser.add_argument(
        "--min-request-interval",
        type=float,
        default=0.60,
        help="Minimum seconds between batch HTTP requests (throttle).",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "l2"),
        help="Output directory.",
    )
    args = parser.parse_args()

    session = requests.Session()
    chain_head = int(rpc_call(session, args.rpc, "eth_blockNumber", []), 16)
    head_blk = rpc_call(session, args.rpc, "eth_getBlockByNumber", [hex(chain_head), False], rid=2)
    chain_head_ts = int(head_blk["timestamp"], 16)

    if args.start_ts is not None and args.end_ts is not None:
        start_ts = args.start_ts
        end_ts = args.end_ts
        start_src = "cli:start_ts"
        end_src = "cli:end_ts"
    else:
        start_ts, end_ts, start_src, end_src = load_window_from_summary(args.window_summary)

    if start_ts > end_ts:
        raise ValueError(f"start_ts {start_ts} is greater than end_ts {end_ts}")
    if start_ts > chain_head_ts:
        raise ValueError(f"start_ts {start_ts} is above current head timestamp {chain_head_ts}")

    bounded_end_ts = min(end_ts, chain_head_ts)
    if bounded_end_ts != end_ts:
        print(f"Requested end_ts={end_ts} exceeds chain head timestamp; clamped to {bounded_end_ts}")
        end_ts = bounded_end_ts

    print("Locating Arbitrum block bounds for timestamp window...")
    start_block = find_first_block_at_or_after_ts(session, args.rpc, start_ts, 0, chain_head)
    end_block = find_last_block_at_or_before_ts(session, args.rpc, end_ts, start_block, chain_head)

    start_blk_obj = rpc_call(session, args.rpc, "eth_getBlockByNumber", [hex(start_block), False], rid=3)
    end_blk_obj = rpc_call(session, args.rpc, "eth_getBlockByNumber", [hex(end_block), False], rid=4)
    start_block_ts = int(start_blk_obj["timestamp"], 16)
    end_block_ts = int(end_blk_obj["timestamp"], 16)

    window_blocks = end_block - start_block + 1
    window_secs = end_block_ts - start_block_ts
    sec_per_block = (window_secs / window_blocks) if window_blocks > 0 else 0.0
    stride_blocks = max(1, int(round(args.sample_seconds / sec_per_block))) if sec_per_block > 0 else 1

    sample_blocks = list(range(start_block, end_block + 1, stride_blocks))
    if not sample_blocks or sample_blocks[-1] != end_block:
        sample_blocks.append(end_block)

    print(
        f"Window blocks={start_block}..{end_block} ({window_blocks} blocks), "
        f"sec_per_block~{sec_per_block:.6f}, stride_blocks={stride_blocks}, samples={len(sample_blocks)}"
    )
    print(
        f"Throttle: request_batch_size={args.request_batch_size}, min_request_interval={args.min_request_interval:.2f}s"
    )

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_base = f"arb1_fee_{start_block}_{end_block}_step{stride_blocks}_{stamp}"
    csv_path = os.path.join(out_dir, csv_base + ".csv")
    summary_path = os.path.join(out_dir, csv_base + "_summary.json")

    rows_written = 0
    base_fees = []
    gas_ratios = []

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "block_number",
                "timestamp_unix",
                "timestamp_utc",
                "base_fee_per_gas_wei",
                "gas_used",
                "gas_limit",
                "gas_used_ratio",
            ],
        )
        writer.writeheader()

        for i in range(0, len(sample_blocks), args.request_batch_size):
            chunk = sample_blocks[i : i + args.request_batch_size]
            block_objs = rpc_batch_get_blocks(
                session,
                args.rpc,
                chunk,
                request_batch_size=args.request_batch_size,
                min_request_interval_sec=args.min_request_interval,
            )
            for b in block_objs:
                row = block_to_row(b)
                writer.writerow(row)
                rows_written += 1
                base_fees.append(row["base_fee_per_gas_wei"] / 1e9)
                gas_ratios.append(row["gas_used_ratio"])

            if rows_written % 10000 == 0 or rows_written == len(sample_blocks):
                print(f"Progress samples={rows_written}/{len(sample_blocks)}")

    summary = {
        "rpc": args.rpc,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_window": {
            "summary_file": os.path.abspath(args.window_summary) if args.window_summary else None,
            "start_source": start_src,
            "end_source": end_src,
            "requested_start_ts": start_ts,
            "requested_end_ts": end_ts,
            "requested_start_utc": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "requested_end_utc": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
        },
        "chain_head": {
            "block": chain_head,
            "timestamp_unix": chain_head_ts,
            "timestamp_utc": datetime.fromtimestamp(chain_head_ts, tz=timezone.utc).isoformat(),
        },
        "window": {
            "start_block": start_block,
            "end_block": end_block,
            "start_timestamp_unix": start_block_ts,
            "end_timestamp_unix": end_block_ts,
            "start_timestamp_utc": datetime.fromtimestamp(start_block_ts, tz=timezone.utc).isoformat(),
            "end_timestamp_utc": datetime.fromtimestamp(end_block_ts, tz=timezone.utc).isoformat(),
            "block_count": window_blocks,
            "window_seconds": window_secs,
            "seconds_per_block_estimate": sec_per_block,
        },
        "sampling": {
            "sample_seconds_target": args.sample_seconds,
            "sample_stride_blocks": stride_blocks,
            "sample_count": rows_written,
            "request_batch_size": args.request_batch_size,
            "min_request_interval_sec": args.min_request_interval,
        },
        "base_fee_gwei": {
            "p10": percentile(base_fees, 10),
            "p50": percentile(base_fees, 50),
            "p90": percentile(base_fees, 90),
            "p99": percentile(base_fees, 99),
            "max": max(base_fees) if base_fees else 0.0,
        },
        "gas_used_ratio": {
            "p10": percentile(gas_ratios, 10),
            "p50": percentile(gas_ratios, 50),
            "p90": percentile(gas_ratios, 90),
            "p99": percentile(gas_ratios, 99),
            "max": max(gas_ratios) if gas_ratios else 0.0,
        },
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"WROTE {csv_path}")
    print(f"WROTE {summary_path}")


if __name__ == "__main__":
    main()
