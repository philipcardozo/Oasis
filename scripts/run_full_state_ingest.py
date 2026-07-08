#!/usr/bin/env python3
"""Orchestrate full-state terrain ingestion, one DEM tile at a time.

Runs a dry-run to discover available tiles, skips any already in the registry,
then processes each pending tile independently (one raw file on disk at a time).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_sources import TERRAIN_COVERAGE_PATH  # noqa: E402
from scripts.ingest_usgs_terrain import STATE_BBOXES, STATE_KEYS, STATE_LABELS, _tilejson_label  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def source_tile(row: dict) -> str:
    if row.get("product_tile"):
        return row["product_tile"]
    text = f"{row.get('raw_file_path', '')} {row.get('id', '')}"
    m = re.search(r"n\d{2}w\d{3}", text, re.I)
    return m.group(0).lower() if m else ""


def registry_processed_tiles() -> set[str]:
    if not TERRAIN_COVERAGE_PATH.exists():
        return set()
    data = json.loads(TERRAIN_COVERAGE_PATH.read_text())
    return {
        source_tile(s)
        for s in data.get("sources", [])
        if s.get("public_tilejson") == "/tiles/terrain-rgb/tiles.json" and source_tile(s)
    }


def run_ingest(*extra: str) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / "ingest_usgs_terrain.py")] + list(extra)
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def coverage_snapshot(state_key: str) -> tuple[int, int, float]:
    data = json.loads(TERRAIN_COVERAGE_PATH.read_text())
    total = int(data.get(f"{state_key}_available_products_total") or 0)
    processed = int(data.get(f"{state_key}_available_products_processed") or 0)
    pct = float(data.get(f"{state_key}_available_products_coverage_pct") or 0.0)
    return total, processed, pct


def main() -> None:
    parser = argparse.ArgumentParser(description="Full-state terrain ingestion (tile by tile).")
    parser.add_argument("--state", required=True, choices=sorted(STATE_BBOXES))
    parser.add_argument("--minzoom", type=int, default=6)
    parser.add_argument("--maxzoom", type=int, default=11)
    args = parser.parse_args()

    state = args.state
    state_key = STATE_KEYS[state]
    label = STATE_LABELS.get(state, state)
    print(f"\n{'='*60}")
    print(f"Full ingestion for {label} ({state})  started {now_iso()}")
    print(f"{'='*60}", flush=True)

    # Step 1: dry-run to discover all available tiles
    print(f"\n[1/3] Dry-run discovery for {state}...", flush=True)
    rc = run_ingest("--state", state)
    if rc != 0:
        raise SystemExit(f"Dry-run failed (exit {rc}). Check TNMAccess connectivity.")

    data = json.loads(TERRAIN_COVERAGE_PATH.read_text())
    available: list[str] = data.get("last_job", {}).get("available_product_tiles", [])
    if not available:
        raise SystemExit("No available product tiles discovered. Check state bbox / TNMAccess.")

    print(f"Discovered {len(available)} available DEM tiles for {state}:", flush=True)
    print("  " + "  ".join(available), flush=True)

    # Step 2: identify pending tiles
    already_done = registry_processed_tiles()
    pending = [t for t in available if t not in already_done]
    skipped = sorted(set(available) & already_done)

    print(f"\n[2/3] Processing plan:")
    print(f"  Already in registry (skip): {len(skipped)} -- {skipped}")
    print(f"  Need to download+process:   {len(pending)} -- {sorted(pending)}", flush=True)

    if not pending:
        print(f"\nAll {len(available)} tiles already processed. {label} is complete.")
    else:
        for i, tile in enumerate(pending, 1):
            ts = now_iso()
            print(f"\n{'─'*50}")
            print(f"Tile {i}/{len(pending)}: {tile}  [{ts}]")
            print(f"{'─'*50}", flush=True)
            rc = run_ingest(
                "--state", state,
                "--tiles", tile,
                "--no-dry-run",
                "--minzoom", str(args.minzoom),
                "--maxzoom", str(args.maxzoom),
                "--incremental",
                "--delete-raw-after-process",
                "--max-products", "1",
            )
            if rc != 0:
                print(f"WARNING: tile {tile} failed (exit {rc}) -- continuing.", flush=True)
            done_now = len(registry_processed_tiles() & set(available))
            pct = round(100 * done_now / len(available), 1)
            print(f"  Progress: {done_now}/{len(available)} = {pct}%", flush=True)

    # Step 3: final verification
    print(f"\n[3/3] Final verification for {label}...")
    total, processed_count, pct = coverage_snapshot(state_key)
    print(f"  Registry: {processed_count}/{total} = {pct}%")

    if pct >= 100.0:
        tj_path = ROOT / "graph" / "tiles" / "terrain-rgb" / "tiles.json"
        if tj_path.exists():
            tj = json.loads(tj_path.read_text())
            name, desc = _tilejson_label(state)
            tj["name"] = name
            tj["description"] = desc
            tj_path.write_text(json.dumps(tj, indent=2) + "\n")
        print(f"  DONE: {label} is at 100%  {now_iso()}")
    else:
        missing = sorted(set(available) - registry_processed_tiles())
        print(f"  NOT COMPLETE -- missing: {missing}")
        sys.exit(1)


if __name__ == "__main__":
    main()
