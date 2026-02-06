#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone

import requests


def pct(arr, p):
    s = sorted(arr)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def logret(arr):
    out = []
    for i in range(1, len(arr)):
        a, b = arr[i - 1], arr[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def stale_err(arr, ks):
    out = {}
    for k in ks:
        errs = []
        hold = arr[0]
        for i, v in enumerate(arr):
            if i % k == 0:
                hold = v
            if v > 0:
                errs.append(abs(hold - v) / v)
        out[str(k)] = {
            "median": statistics.median(errs),
            "p90": pct(errs, 90),
            "mean": statistics.mean(errs),
        }
    return out


def make_rpc(session, rpc_url):
    headers = {"content-type": "application/json"}

    def rpc(method, params, rid=1, retries=6):
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        err = None
        for i in range(retries):
            try:
                r = session.post(rpc_url, json=payload, headers=headers, timeout=35)
                r.raise_for_status()
                j = r.json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                return j["result"]
            except Exception as e:
                err = e
                time.sleep(0.25 * (i + 1))
        raise err

    return rpc


def main():
    parser = argparse.ArgumentParser(description="Fetch Ethereum L1 fee history and export CSV+summary")
    parser.add_argument("--days", type=int, default=365, help="Number of days to fetch (default: 365)")
    parser.add_argument(
        "--rpc",
        default="https://ethereum-rpc.publicnode.com",
        help="Ethereum JSON-RPC endpoint",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data"),
        help="Output directory for CSV and summary JSON",
    )
    parser.add_argument("--blocks-per-day", type=int, default=7200, help="Assumed blocks/day")
    parser.add_argument("--chunk", type=int, default=1024, help="feeHistory blockCount per RPC call")
    args = parser.parse_args()

    session = requests.Session()
    rpc = make_rpc(session, args.rpc)

    latest = int(rpc("eth_blockNumber", []), 16)
    latest_blk = rpc("eth_getBlockByNumber", [hex(latest), False], rid=3)
    latest_ts = int(latest_blk["timestamp"], 16)

    start_block = max(0, latest - args.days * args.blocks_per_day)
    total_blocks = latest - start_block + 1
    expected_calls = (total_blocks + args.chunk - 1) // args.chunk

    print(f"Collecting {total_blocks} blocks over {args.days} days, expected_calls={expected_calls}")

    rows = []
    current_newest = latest
    calls = 0

    while current_newest >= start_block:
        n = min(args.chunk, current_newest - start_block + 1)
        res = rpc("eth_feeHistory", [hex(n), hex(current_newest), []], rid=2)

        oldest = int(res["oldestBlock"], 16)
        bf = res.get("baseFeePerGas", [])
        bbf = res.get("baseFeePerBlobGas", [])
        bur = res.get("blobGasUsedRatio", [])

        if len(bf) < n:
            raise RuntimeError(f"Unexpected baseFeePerGas length {len(bf)} for n={n}")

        for i in range(n):
            block_number = oldest + i
            rows.append(
                {
                    "block_number": block_number,
                    "base_fee_per_gas_wei": int(bf[i], 16),
                    "base_fee_per_blob_gas_wei": int(bbf[i], 16) if i < len(bbf) else 0,
                    "blob_gas_used_ratio": float(bur[i]) if i < len(bur) else 0.0,
                }
            )

        current_newest = oldest - 1
        calls += 1
        if calls % 20 == 0 or current_newest < start_block:
            print(f"Progress calls={calls}/{expected_calls} blocks={len(rows)}/{total_blocks}")

    rows.sort(key=lambda x: x["block_number"])

    base = [r["base_fee_per_gas_wei"] for r in rows]
    blob = [r["base_fee_per_blob_gas_wei"] for r in rows]
    blob_used = [r["blob_gas_used_ratio"] for r in rows]

    base_g = [x / 1e9 for x in base]
    blob_g = [x / 1e9 for x in blob]
    base_lr = logret(base)
    blob_lr = logret(blob)
    ks = [1, 4, 12, 24, 60, 120, 240]

    summary = {
        "rpc": args.rpc,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_days": args.days,
        "start_block": rows[0]["block_number"],
        "end_block": rows[-1]["block_number"],
        "sample_count": len(rows),
        "latest_block_timestamp_utc": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
        "assumed_start_timestamp_utc": datetime.fromtimestamp(
            latest_ts - (rows[-1]["block_number"] - rows[0]["block_number"]) * 12,
            tz=timezone.utc,
        ).isoformat(),
        "base_fee_gwei": {
            "p10": pct(base_g, 10),
            "p50": pct(base_g, 50),
            "p90": pct(base_g, 90),
            "p99": pct(base_g, 99),
            "max": max(base_g),
        },
        "blob_base_fee_gwei": {
            "p10": pct(blob_g, 10),
            "p50": pct(blob_g, 50),
            "p90": pct(blob_g, 90),
            "p99": pct(blob_g, 99),
            "max": max(blob_g),
        },
        "log_return_stdev": {
            "base": statistics.pstdev(base_lr),
            "blob": statistics.pstdev(blob_lr),
        },
        "blob_nonzero_ratio": sum(1 for x in blob if x > 0) / len(blob),
        "blob_gas_used_ratio": {
            "p50": pct(blob_used, 50),
            "p90": pct(blob_used, 90),
        },
        "stale_error": {
            "base": stale_err(base, ks),
            "blob": stale_err(blob, ks),
        },
    }

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"eth_l1_fee_{args.days}d_{stamp}"
    csv_path = os.path.join(out_dir, base_name + ".csv")
    json_path = os.path.join(out_dir, base_name + "_summary.json")

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "block_number",
                "base_fee_per_gas_wei",
                "base_fee_per_blob_gas_wei",
                "blob_gas_used_ratio",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"WROTE {csv_path}")
    print(f"WROTE {json_path}")


if __name__ == "__main__":
    main()
