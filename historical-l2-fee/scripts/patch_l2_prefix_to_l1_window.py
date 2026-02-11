#!/usr/bin/env python3

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]


CHAIN_CONFIGS = [
    {
        "name": "arbitrum",
        "summary_key": "l2_arb_csv",
        "fetch_script": "fetch_arbitrum_fee_history.py",
        "rpc": "https://arb1.arbitrum.io/rpc",
        "out_prefix": "arb1_fee",
        "request_batch_size": 40,
        "min_request_interval": 1.0,
    },
    {
        "name": "base",
        "summary_key": "l2_base_csv",
        "fetch_script": "fetch_base_fee_history.py",
        "rpc": "https://mainnet.base.org",
        "out_prefix": "base_fee",
        "request_batch_size": 10,
        "min_request_interval": 0.8,
    },
    {
        "name": "scroll",
        "summary_key": "l2_scroll_csv",
        "fetch_script": "fetch_scroll_fee_history.py",
        "rpc": "https://scroll-rpc.publicnode.com",
        "out_prefix": "scroll_fee",
        "request_batch_size": 60,
        "min_request_interval": 0.8,
    },
]


def rpc_call(session: requests.Session, rpc_url: str, method: str, params: list, rid: int = 1, retries: int = 6):
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    last_err = None
    for i in range(retries):
        try:
            resp = session.post(rpc_url, json=payload, timeout=45)
            resp.raise_for_status()
            obj = resp.json()
            if "error" in obj:
                raise RuntimeError(obj["error"])
            return obj["result"]
        except Exception as exc:
            last_err = exc
            time.sleep(0.4 * (i + 1))
    raise last_err


def read_first_last_row(csv_path: Path):
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        first = next(reader, None)
        if first is None:
            raise ValueError(f"CSV has no rows: {csv_path}")
        last = first
        for row in reader:
            last = row
    return first, last


def parse_csv_first_ts(csv_path: Path):
    first, _ = read_first_last_row(csv_path)
    if "timestamp_unix" not in first or not first["timestamp_unix"]:
        raise ValueError(f"CSV is missing timestamp_unix in first row: {csv_path}")
    return int(first["timestamp_unix"])


def run_fetch_prefix(
    fetch_script: Path,
    start_ts: int,
    end_ts: int,
    sample_seconds: int,
    out_dir: Path,
    request_batch_size: int,
    min_request_interval: float,
):
    cmd = [
        sys.executable,
        "-u",
        str(fetch_script),
        "--start-ts",
        str(start_ts),
        "--end-ts",
        str(end_ts),
        "--sample-seconds",
        str(sample_seconds),
        "--request-batch-size",
        str(request_batch_size),
        "--min-request-interval",
        str(min_request_interval),
        "--out-dir",
        str(out_dir),
    ]
    print("RUN", " ".join(cmd))
    wrote_csv = None
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line:
            print(" ", line)
        m = re.match(r"^WROTE\s+(.+\.csv)\s*$", line)
        if m:
            wrote_csv = Path(m.group(1)).resolve()

    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"Fetch command failed ({rc}): {' '.join(cmd)}")
    if wrote_csv is None:
        raise RuntimeError("Could not parse output CSV path from fetch output.")
    return wrote_csv


def merge_l2_csv(prefix_csv: Path, existing_csv: Path, merged_csv: Path):
    with existing_csv.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
    if not fieldnames:
        raise ValueError(f"Failed to read CSV header: {existing_csv}")

    seen_blocks = set()
    rows_written = 0
    first_row = None
    last_row = None

    with merged_csv.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()

        for path in (prefix_csv, existing_csv):
            with path.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    block_number = int(row["block_number"])
                    if block_number in seen_blocks:
                        continue
                    seen_blocks.add(block_number)
                    writer.writerow(row)
                    rows_written += 1
                    if first_row is None:
                        first_row = row
                    last_row = row

    if first_row is None or last_row is None:
        raise ValueError(f"Merged CSV is empty: {merged_csv}")

    return {
        "rows_written": rows_written,
        "first_block": int(first_row["block_number"]),
        "last_block": int(last_row["block_number"]),
        "first_timestamp_unix": int(first_row["timestamp_unix"]),
        "last_timestamp_unix": int(last_row["timestamp_unix"]),
    }


def iso_utc(ts: int):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(
        description="Patch L2 CSVs to match true L1 CSV window by fetching only missing prefix ranges and merging."
    )
    parser.add_argument(
        "--synced-summary",
        default=str(PROJECT_ROOT / "data" / "plots" / "fee_history_l1_l2_synced_summary.json"),
        help="Path to synced summary JSON that points to current L1/L2 CSV files.",
    )
    parser.add_argument(
        "--l1-rpc",
        default="https://ethereum-rpc.publicnode.com",
        help="Ethereum RPC for resolving true L1 start/end block timestamps.",
    )
    parser.add_argument(
        "--sample-seconds",
        type=int,
        default=60,
        help="Target L2 sample interval for prefix fetches.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "data" / "l2"),
        help="Directory to place merged CSV/summary files.",
    )
    args = parser.parse_args()

    synced_summary_path = Path(args.synced_summary).resolve()
    if not synced_summary_path.exists():
        raise FileNotFoundError(f"Missing synced summary: {synced_summary_path}")

    with synced_summary_path.open() as f:
        synced = json.load(f)

    l1_csv = Path(synced["l1_csv"]).resolve()
    if not l1_csv.exists():
        raise FileNotFoundError(f"Missing L1 CSV from synced summary: {l1_csv}")

    l1_first_row, l1_last_row = read_first_last_row(l1_csv)
    l1_first_block = int(l1_first_row["block_number"])
    l1_last_block = int(l1_last_row["block_number"])

    session = requests.Session()
    l1_first_block_obj = rpc_call(session, args.l1_rpc, "eth_getBlockByNumber", [hex(l1_first_block), False], rid=l1_first_block)
    l1_last_block_obj = rpc_call(session, args.l1_rpc, "eth_getBlockByNumber", [hex(l1_last_block), False], rid=l1_last_block)
    l1_start_ts = int(l1_first_block_obj["timestamp"], 16)
    l1_end_ts = int(l1_last_block_obj["timestamp"], 16)

    print(
        "L1 true window from boundary blocks:",
        f"{l1_start_ts} ({iso_utc(l1_start_ts)}) -> {l1_end_ts} ({iso_utc(l1_end_ts)})",
    )

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    merged_paths = {}
    per_chain = {}

    for chain in CHAIN_CONFIGS:
        existing_csv = Path(synced[chain["summary_key"]]).resolve()
        if not existing_csv.exists():
            raise FileNotFoundError(f"Missing {chain['name']} CSV from synced summary: {existing_csv}")

        existing_first_ts = parse_csv_first_ts(existing_csv)
        if existing_first_ts <= l1_start_ts:
            print(f"[{chain['name']}] already aligned at start (first_ts={existing_first_ts})")
            merged_paths[chain["summary_key"]] = str(existing_csv)
            per_chain[chain["name"]] = {
                "status": "already_aligned",
                "existing_csv": str(existing_csv),
                "existing_first_ts": existing_first_ts,
            }
            continue

        missing_start_ts = l1_start_ts
        missing_end_ts = existing_first_ts - 1
        print(
            f"[{chain['name']}] missing prefix:",
            f"{missing_start_ts} ({iso_utc(missing_start_ts)}) -> {missing_end_ts} ({iso_utc(missing_end_ts)})",
        )

        fetch_script = (PROJECT_ROOT / "scripts" / chain["fetch_script"]).resolve()
        prefix_csv = run_fetch_prefix(
            fetch_script=fetch_script,
            start_ts=missing_start_ts,
            end_ts=missing_end_ts,
            sample_seconds=args.sample_seconds,
            out_dir=out_dir,
            request_batch_size=int(chain["request_batch_size"]),
            min_request_interval=float(chain["min_request_interval"]),
        )

        merged_name = f"{chain['out_prefix']}_merged_{stamp}.csv"
        merged_csv = out_dir / merged_name
        merged_meta = merge_l2_csv(prefix_csv=prefix_csv, existing_csv=existing_csv, merged_csv=merged_csv)

        merged_paths[chain["summary_key"]] = str(merged_csv)
        per_chain[chain["name"]] = {
            "status": "patched_prefix",
            "existing_csv": str(existing_csv),
            "prefix_csv": str(prefix_csv),
            "merged_csv": str(merged_csv),
            "missing_start_ts": missing_start_ts,
            "missing_end_ts": missing_end_ts,
            **merged_meta,
        }
        print(
            f"[{chain['name']}] merged -> {merged_csv} "
            f"(rows={merged_meta['rows_written']}, "
            f"first_ts={merged_meta['first_timestamp_unix']}, last_ts={merged_meta['last_timestamp_unix']})"
        )

    out_summary = out_dir / f"l2_prefix_patch_{stamp}_summary.json"
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "synced_summary_input": str(synced_summary_path),
        "l1_csv": str(l1_csv),
        "l1_start_block": l1_first_block,
        "l1_end_block": l1_last_block,
        "l1_start_ts": l1_start_ts,
        "l1_end_ts": l1_end_ts,
        "l1_start_utc": iso_utc(l1_start_ts),
        "l1_end_utc": iso_utc(l1_end_ts),
        "sample_seconds": args.sample_seconds,
        "chains": per_chain,
        "merged_paths": merged_paths,
    }
    with out_summary.open("w") as f:
        json.dump(result, f, indent=2)

    print(f"WROTE {out_summary}")
    for key, value in merged_paths.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
