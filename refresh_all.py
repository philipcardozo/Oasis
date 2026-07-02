"""Refresh generated graph data in the right order.

Run: python3 refresh_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run(script: str) -> None:
    subprocess.run([sys.executable, script], cwd=ROOT, check=True)


def main() -> None:
    run("refresh_gov_contracts.py")
    run("expand_us.py")
    run("refresh_filings.py")
    run("refresh_prices.py")
    run("expand_us.py")
    run("refresh_news.py")
    run("refresh_edge_candidates.py")
    run("expand_us.py")


if __name__ == "__main__":
    main()
