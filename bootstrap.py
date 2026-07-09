"""Rebuild the generated graph and Parquet store without network refreshers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script: str) -> None:
    subprocess.run([sys.executable, script], cwd=ROOT, check=True)


def main() -> None:
    for script in ("expand_us.py", "build_map_geojson.py", "build_store.py"):
        print(f"offline bootstrap: {script}")
        run(script)


if __name__ == "__main__":
    main()
