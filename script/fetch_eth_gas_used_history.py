#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import time
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import requests


def rpc_call(session: requests.Session, rpc_url: str, method: str, params: list, rid: int = 1, retries: int = 6):
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    headers = {"content-type": "application/json"}
    err = None
    for i in range(retries):
        try:
            r = session.post(rpc_url, json=payload, headers=headers, timeout=45)
            r.raise_for_status()
            j = r.json()
            if "error" in j:
                raise RuntimeError(j["error"])
            return j["result"]
        except Exception as e:
            err = e
            time.sleep(0.25 * (i + 1))
    raise err


def rpc_batch_get_blocks(
    session: requests.Session, rpc_url: str, block_numbers: list[int], retries: int = 6
) -> list[dict]:
    headers = {"content-type": "application/json"}
    reqs = [
        {
            "jsonrpc": "2.0",
            "id": i + 1,
            "method": "eth_getBlockByNumber",
            "params": [hex(bn), False],
        }
        for i, bn in enumerate(block_numbers)
    ]
    err = None
    for i in range(retries):
        try:
            r = session.post(rpc_url, json=reqs, headers=headers, timeout=60)
            r.raise_for_status()
            res = r.json()
            if not isinstance(res, list):
                raise RuntimeError(f"Unexpected batch response type: {type(res)}")
            by_id = {}
            for item in res:
                if "error" in item:
                    raise RuntimeError(item["error"])
                by_id[item["id"]] = item["result"]
            return [by_id[i + 1] for i in range(len(block_numbers))]
        except Exception as e:
            err = e
            time.sleep(0.25 * (i + 1))
    raise err


def main():
    parser = argparse.ArgumentParser(description="Fetch Ethereum L1 gasUsed history and plot it")
    parser.add_argument("--days", type=int, default=1, help="Number of days to fetch (default: 1)")
    parser.add_argument("--hours", type=float, default=None, help="Number of hours to fetch (overrides --days)")
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
    parser.add_argument(
        "--plot-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "plots"),
        help="Output directory for plot PNG",
    )
    parser.add_argument("--blocks-per-day", type=int, default=7200, help="Assumed blocks/day")
    parser.add_argument("--chunk", type=int, default=200, help="Blocks per batch RPC call")
    args = parser.parse_args()

    session = requests.Session()
    latest = int(rpc_call(session, args.rpc, "eth_blockNumber", []), 16)
    latest_blk = rpc_call(session, args.rpc, "eth_getBlockByNumber", [hex(latest), False], rid=2)
    latest_ts = int(latest_blk["timestamp"], 16)

    if args.hours is not None:
        blocks_to_fetch = max(1, int(round(args.hours * args.blocks_per_day / 24)))
        window_label = f"{args.hours:g}h"
        window_days = args.hours / 24
        window_hours = args.hours
    else:
        blocks_to_fetch = args.days * args.blocks_per_day
        window_label = f"{args.days}d"
        window_days = args.days
        window_hours = args.days * 24

    start_block = max(0, latest - blocks_to_fetch)
    block_numbers = list(range(start_block, latest + 1))
    total_blocks = len(block_numbers)
    expected_calls = math.ceil(total_blocks / args.chunk)
    print(f"Collecting gasUsed for {total_blocks} blocks over {window_label}, expected_calls={expected_calls}")

    rows = []
    calls = 0
    for i in range(0, total_blocks, args.chunk):
        chunk_bns = block_numbers[i : i + args.chunk]
        blocks = rpc_batch_get_blocks(session, args.rpc, chunk_bns)
        for blk in blocks:
            if blk is None:
                continue
            gas_used = int(blk["gasUsed"], 16)
            gas_limit = int(blk["gasLimit"], 16)
            ts = int(blk["timestamp"], 16)
            rows.append(
                {
                    "block_number": int(blk["number"], 16),
                    "timestamp_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                    "gas_used": gas_used,
                    "gas_limit": gas_limit,
                    "gas_used_ratio": (gas_used / gas_limit) if gas_limit > 0 else 0.0,
                }
            )
        calls += 1
        if calls % 10 == 0 or (i + args.chunk >= total_blocks):
            print(f"Progress calls={calls}/{expected_calls} blocks={min(i + args.chunk, total_blocks)}/{total_blocks}")

    rows.sort(key=lambda x: x["block_number"])

    out_dir = os.path.abspath(args.out_dir)
    plot_dir = os.path.abspath(args.plot_dir)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(plot_dir, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"eth_l1_gas_used_{window_label}_{stamp}"
    csv_path = os.path.join(out_dir, base_name + ".csv")
    summary_path = os.path.join(out_dir, base_name + "_summary.json")
    plot_path = os.path.join(plot_dir, base_name + ".png")

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "block_number",
                "timestamp_utc",
                "gas_used",
                "gas_limit",
                "gas_used_ratio",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    gas_used_values = [r["gas_used"] for r in rows]
    ratio_values = [r["gas_used_ratio"] for r in rows]
    summary = {
        "rpc": args.rpc,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "window_hours": window_hours,
        "start_block": rows[0]["block_number"] if rows else None,
        "end_block": rows[-1]["block_number"] if rows else None,
        "sample_count": len(rows),
        "latest_block_timestamp_utc": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
        "gas_used": {
            "min": min(gas_used_values) if gas_used_values else None,
            "max": max(gas_used_values) if gas_used_values else None,
            "mean": (sum(gas_used_values) / len(gas_used_values)) if gas_used_values else None,
        },
        "gas_used_ratio": {
            "min": min(ratio_values) if ratio_values else None,
            "max": max(ratio_values) if ratio_values else None,
            "mean": (sum(ratio_values) / len(ratio_values)) if ratio_values else None,
        },
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    x = [r["block_number"] for r in rows]
    y = [r["gas_used"] for r in rows]
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(x, y, color="#2563eb", linewidth=1.0)
    ax.set_title(f"Ethereum L1 Gas Used History ({window_label})")
    ax.set_xlabel("L1 block number")
    ax.set_ylabel("Gas used")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)

    print(f"WROTE {csv_path}")
    print(f"WROTE {summary_path}")
    print(f"WROTE {plot_path}")


if __name__ == "__main__":
    main()
