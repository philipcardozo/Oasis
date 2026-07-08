"""Refresh generated graph data in the right order.

Run: python3 refresh_all.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
UNIVERSE = ROOT / "graph" / "data" / "universe.json"


def run(script: str) -> None:
    subprocess.run([sys.executable, script], cwd=ROOT, check=True)


def main() -> None:
    start_time = time.time()
    
    if not UNIVERSE.exists():
        print("Bootstrap: running expand_us.py first...")
        run("expand_us.py")
        
    run("refresh_gleif.py")
    run("refresh_sec_addresses.py")
    run("refresh_gov_contracts.py")
    run("refresh_filings.py")
    run("refresh_prices.py")
    run("refresh_news.py")
    run("refresh_edge_candidates.py")
    run("expand_us.py")
    
    elapsed = time.time() - start_time
    print(f"Refresh completed in {elapsed:.1f} seconds.")


if __name__ == "__main__":
    main()
