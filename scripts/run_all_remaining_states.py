#!/usr/bin/env python3
"""Orchestrate ingestion for all 34 remaining US states in pairs.

Pairs order:
1. Ohio and Kentucky
2. Tennessee and Alabama
3. Mississippi and Louisiana
4. Arkansas and Missouri
5. Indiana and Illinois
6. Michigan and Wisconsin
7. Minnesota and Iowa
8. North Dakota and South Dakota
9. Nebraska and Kansas
10. Oklahoma and Texas
11. New Mexico and Colorado
12. Wyoming and Montana
13. Idaho and Utah
14. Arizona and Nevada
15. California and Oregon
16. Washington and New Hampshire
17. Hawaii and Alaska
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingest_usgs_terrain import STATE_KEYS, STATE_LABELS
from scripts.run_full_state_ingest import coverage_snapshot


PAIRS = [
    ("OH", "KY", "Ohio and Kentucky"),
    ("TN", "AL", "Tennessee and Alabama"),
    ("MS", "LA", "Mississippi and Louisiana"),
    ("AR", "MO", "Arkansas and Missouri"),
    ("IN", "IL", "Indiana and Illinois"),
    ("MI", "WI", "Michigan and Wisconsin"),
    ("MN", "IA", "Minnesota and Iowa"),
    ("ND", "SD", "North Dakota and South Dakota"),
    ("NE", "KS", "Nebraska and Kansas"),
    ("OK", "TX", "Oklahoma and Texas"),
    ("NM", "CO", "New Mexico and Colorado"),
    ("WY", "MT", "Wyoming and Montana"),
    ("ID", "UT", "Idaho and Utah"),
    ("AZ", "NV", "Arizona and Nevada"),
    ("CA", "OR", "California and Oregon"),
    ("WA", "NH", "Washington and New Hampshire"),
    ("HI", "AK", "Hawaii and Alaska"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_state_complete(state: str) -> bool:
    state_key = STATE_KEYS.get(state)
    if not state_key:
        return False
    total, processed_count, pct = coverage_snapshot(state_key)
    return total > 0 and pct >= 100.0


def process_state(state: str, max_retries: int = 1000) -> bool:
    state_key = STATE_KEYS[state]
    label = STATE_LABELS[state]

    if is_state_complete(state):
        total, processed_count, pct = coverage_snapshot(state_key)
        print(f"✅ [{now_iso()}] {label} ({state}) is already 100% complete ({processed_count}/{total} tiles). Skipping!", flush=True)
        return True

    attempt = 1
    while not is_state_complete(state) and attempt <= max_retries:
        print(f"\n{'='*60}", flush=True)
        print(f"🚀 Starting ingestion for {label} ({state}) - Attempt {attempt}/{max_retries}  [{now_iso()}]", flush=True)
        print(f"{'='*60}", flush=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_full_state_ingest.py"),
            "--state", state,
            "--minzoom", "6",
            "--maxzoom", "11",
        ]
        res = subprocess.run(cmd, cwd=ROOT)
        if res.returncode == 0 or is_state_complete(state):
            print(f"🎉 [{now_iso()}] {label} ({state}) successfully completed 100% coverage!", flush=True)
            return True
        sleep_secs = min(30 * attempt, 300)
        print(f"⚠️ [{now_iso()}] {label} ({state}) failed or incomplete (exit {res.returncode}). Retrying in {sleep_secs} seconds...", flush=True)
        time.sleep(sleep_secs)
        attempt += 1

    print(f"❌ [{now_iso()}] ERROR: {label} ({state}) failed to reach 100% after {max_retries} attempts.", flush=True)
    return False


def main() -> None:
    print(f"=== MASTER 34-STATE TERRAIN INGESTION ORCHESTRATOR ===", flush=True)
    print(f"Total pairs to process: {len(PAIRS)}", flush=True)

    completed_pairs = 0
    for idx, (s1, s2, pair_name) in enumerate(PAIRS, 1):
        print(f"\n\n############################################################", flush=True)
        print(f"### PAIR {idx}/{len(PAIRS)}: {pair_name} ({s1} & {s2})", flush=True)
        print(f"############################################################\n", flush=True)

        ok1 = process_state(s1)
        if not ok1:
            print(f"\n⚠️ PAIR {idx}/{len(PAIRS)} INCOMPLETE ({s1} failed): Check logs for errors.", flush=True)
            sys.exit(1)
        ok2 = process_state(s2)
        if not ok2:
            print(f"\n⚠️ PAIR {idx}/{len(PAIRS)} INCOMPLETE ({s2} failed): Check logs for errors.", flush=True)
            sys.exit(1)

        completed_pairs += 1
        print(f"\n🏆 PAIR {idx}/{len(PAIRS)} COMPLETE: {pair_name} is now at 100% coverage!", flush=True)

    print(f"\n\n============================================================", flush=True)
    print(f"🎉🎉🎉 ALL {len(PAIRS)} PAIRS (34 STATES) ARE 100% COMPLETE! 🎉🎉🎉", flush=True)
    print(f"============================================================", flush=True)


if __name__ == "__main__":
    main()
