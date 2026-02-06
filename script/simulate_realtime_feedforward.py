#!/usr/bin/env python3

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt

BLOB_GAS_PER_BLOB = 131_072


@dataclass
class Row:
    block_number: int
    base_fee_wei: int
    blob_fee_wei: int


def load_rows(csv_path: Path) -> list[Row]:
    rows: list[Row] = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                Row(
                    block_number=int(r["block_number"]),
                    base_fee_wei=int(r["base_fee_per_gas_wei"]),
                    blob_fee_wei=int(r["base_fee_per_blob_gas_wei"]),
                )
            )
    if not rows:
        raise ValueError(f"No data rows found in {csv_path}")
    rows.sort(key=lambda x: x.block_number)
    return rows


def eth(x_wei: float) -> float:
    return x_wei / 1e18


def gwei(x_wei: float) -> float:
    return x_wei / 1e9


def run_simulation(
    rows: list[Row],
    post_every_blocks: int,
    l2_gas_per_l1_block: float,
    l1_gas_used: int,
    num_blobs: int,
    priority_fee_gwei: float,
    gas_price_multiplier: float,
    blob_price_multiplier: float,
):
    if post_every_blocks <= 0:
        raise ValueError("post_every_blocks must be > 0")
    if l2_gas_per_l1_block <= 0:
        raise ValueError("l2_gas_per_l1_block must be > 0")

    # OP/Scroll-style realtime feedforward pricing: charge each block based on current L1 prices.
    l2_gas_per_batch = l2_gas_per_l1_block * post_every_blocks
    gas_per_l2_gas = l1_gas_used / l2_gas_per_batch
    blob_gas_per_l2_gas = (num_blobs * BLOB_GAS_PER_BLOB) / l2_gas_per_batch

    priority_fee_wei = priority_fee_gwei * 1e9

    timeseries = []
    batches = []

    cumulative_revenue_wei = 0.0
    cumulative_cost_wei = 0.0
    pending_batch_revenue_wei = 0.0

    for idx, row in enumerate(rows):
        current_block = row.block_number

        l2_fee_per_gas_wei = (
            gas_price_multiplier * gas_per_l2_gas * (row.base_fee_wei + priority_fee_wei)
            + blob_price_multiplier * blob_gas_per_l2_gas * row.blob_fee_wei
        )

        block_revenue_wei = l2_fee_per_gas_wei * l2_gas_per_l1_block
        pending_batch_revenue_wei += block_revenue_wei
        cumulative_revenue_wei += block_revenue_wei

        post_cost_wei = 0.0
        batch_revenue_wei = 0.0
        batch_net_wei = 0.0
        posted = ((idx + 1) % post_every_blocks) == 0

        if posted:
            post_cost_wei = (
                l1_gas_used * (row.base_fee_wei + priority_fee_wei)
                + num_blobs * BLOB_GAS_PER_BLOB * row.blob_fee_wei
            )
            cumulative_cost_wei += post_cost_wei

            batch_revenue_wei = pending_batch_revenue_wei
            batch_net_wei = batch_revenue_wei - post_cost_wei

            batches.append(
                {
                    "batch_index": len(batches) + 1,
                    "post_block": current_block,
                    "batch_revenue_eth": eth(batch_revenue_wei),
                    "batch_cost_eth": eth(post_cost_wei),
                    "batch_net_eth": eth(batch_net_wei),
                    "batch_revenue_to_cost": (batch_revenue_wei / post_cost_wei) if post_cost_wei > 0 else None,
                }
            )

            pending_batch_revenue_wei = 0.0

        timeseries.append(
            {
                "block_number": current_block,
                "base_fee_gwei": gwei(row.base_fee_wei),
                "blob_fee_gwei": gwei(row.blob_fee_wei),
                "l2_fee_per_gas_gwei": gwei(l2_fee_per_gas_wei),
                "block_revenue_eth": eth(block_revenue_wei),
                "post_cost_eth": eth(post_cost_wei),
                "batch_revenue_eth": eth(batch_revenue_wei),
                "batch_net_eth": eth(batch_net_wei),
                "cumulative_revenue_eth": eth(cumulative_revenue_wei),
                "cumulative_cost_eth": eth(cumulative_cost_wei),
                "cumulative_net_eth": eth(cumulative_revenue_wei - cumulative_cost_wei),
                "posted": posted,
            }
        )

    summary = {
        "sample_count": len(rows),
        "start_block": rows[0].block_number,
        "end_block": rows[-1].block_number,
        "post_every_blocks": post_every_blocks,
        "l2_gas_per_l1_block": l2_gas_per_l1_block,
        "l1_gas_used": l1_gas_used,
        "num_blobs": num_blobs,
        "priority_fee_gwei": priority_fee_gwei,
        "gas_price_multiplier": gas_price_multiplier,
        "blob_price_multiplier": blob_price_multiplier,
        "implied_gas_per_l2_gas": gas_per_l2_gas,
        "implied_blob_gas_per_l2_gas": blob_gas_per_l2_gas,
        "batches_count": len(batches),
        "total_revenue_eth": eth(cumulative_revenue_wei),
        "total_cost_eth": eth(cumulative_cost_wei),
        "total_net_eth": eth(cumulative_revenue_wei - cumulative_cost_wei),
        "avg_batch_revenue_to_cost": (
            sum(b["batch_revenue_to_cost"] for b in batches if b["batch_revenue_to_cost"] is not None)
            / max(1, sum(1 for b in batches if b["batch_revenue_to_cost"] is not None))
        ),
    }

    return timeseries, batches, summary


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(obj, f, indent=2)


def plot_results(path: Path, timeseries: list[dict], batches: list[dict], title: str):
    blocks = [r["block_number"] for r in timeseries]
    cum_rev = [r["cumulative_revenue_eth"] for r in timeseries]
    cum_cost = [r["cumulative_cost_eth"] for r in timeseries]
    cum_net = [r["cumulative_net_eth"] for r in timeseries]

    batch_idx = [b["batch_index"] for b in batches]
    batch_rev = [b["batch_revenue_eth"] for b in batches]
    batch_cost = [b["batch_cost_eth"] for b in batches]

    fig, axes = plt.subplots(2, 1, figsize=(14, 9), constrained_layout=True)

    axes[0].plot(blocks, cum_rev, label="Cumulative L2 revenue (ETH)", color="#2563eb", linewidth=1.3)
    axes[0].plot(blocks, cum_cost, label="Cumulative L1 posting cost (ETH)", color="#dc2626", linewidth=1.3)
    axes[0].plot(blocks, cum_net, label="Cumulative net (ETH)", color="#16a34a", linewidth=1.3)
    axes[0].set_title(title)
    axes[0].set_xlabel("L1 block number")
    axes[0].set_ylabel("ETH")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].plot(batch_idx, batch_rev, label="Batch revenue (ETH)", color="#2563eb", linewidth=1.2)
    axes[1].plot(batch_idx, batch_cost, label="Batch cost (ETH)", color="#dc2626", linewidth=1.2)
    axes[1].set_title("Per-post batch revenue vs cost")
    axes[1].set_xlabel("Batch index")
    axes[1].set_ylabel("ETH")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="best")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="Simulate OP/Scroll-style realtime feedforward pricing vs batched L1 posting cost"
    )
    parser.add_argument("--csv", required=True, help="Input fee history CSV")
    parser.add_argument("--out-dir", default="data/sim", help="Output directory")
    parser.add_argument("--post-every-blocks", type=int, default=10)
    parser.add_argument("--l2-gas-per-l1-block", type=float, default=12_000_000)
    parser.add_argument("--l1-gas-used", type=int, default=1_000_000)
    parser.add_argument("--num-blobs", type=int, default=2)
    parser.add_argument("--priority-fee-gwei", type=float, default=0.0)
    parser.add_argument("--gas-price-multiplier", type=float, default=1.0)
    parser.add_argument("--blob-price-multiplier", type=float, default=1.0)
    parser.add_argument("--name", default=None, help="Optional output prefix")
    args = parser.parse_args()

    rows = load_rows(Path(args.csv).resolve())
    ts, batches, summary = run_simulation(
        rows=rows,
        post_every_blocks=args.post_every_blocks,
        l2_gas_per_l1_block=args.l2_gas_per_l1_block,
        l1_gas_used=args.l1_gas_used,
        num_blobs=args.num_blobs,
        priority_fee_gwei=args.priority_fee_gwei,
        gas_price_multiplier=args.gas_price_multiplier,
        blob_price_multiplier=args.blob_price_multiplier,
    )

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = args.name or (
        f"realtime_feed_post{args.post_every_blocks}_"
        f"l2gas{int(args.l2_gas_per_l1_block)}_{stamp}"
    )

    timeseries_csv = out_dir / f"{prefix}_timeseries.csv"
    batches_csv = out_dir / f"{prefix}_batches.csv"
    summary_json = out_dir / f"{prefix}_summary.json"
    plot_png = out_dir / f"{prefix}_overview.png"

    write_csv(timeseries_csv, ts)
    write_csv(batches_csv, batches)
    write_json(summary_json, summary)

    plot_results(
        plot_png,
        ts,
        batches,
        title=(
            f"Realtime feedforward vs posting cost (post every {args.post_every_blocks} L1 blocks)"
        ),
    )

    print(timeseries_csv)
    print(batches_csv)
    print(summary_json)
    print(plot_png)
    print(
        "TOTALS",
        f"revenue_eth={summary['total_revenue_eth']:.6f}",
        f"cost_eth={summary['total_cost_eth']:.6f}",
        f"net_eth={summary['total_net_eth']:.6f}",
        f"avg_batch_rev_to_cost={summary['avg_batch_revenue_to_cost']:.4f}",
    )


if __name__ == "__main__":
    main()
