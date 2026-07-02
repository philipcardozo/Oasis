"""Resumable crawl of SEC submissions to capture each US public company's SIC
code, industry description, and exchange. Writes a cache consumed by
expand_us.py. Safe to stop and restart; it skips already-cached CIKs.

Run:   python crawl_sic.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
TICKERS = Path("/tmp/sec_tickers.json")
CACHE = ROOT / "graph" / "data" / "sic_cache.json"
UA = {"User-Agent": "BusinessGraph/0.1 (veratori@veratori.com)"}
RATE = 1.0 / 8  # ~8 requests/sec, under SEC's 10/sec ceiling


def main() -> None:
    tickers = json.load(TICKERS.open())
    cache = {}
    if CACHE.exists():
        cache = json.load(CACHE.open())
    CACHE.parent.mkdir(parents=True, exist_ok=True)

    rows = list(tickers.values())
    total = len(rows)
    done = 0
    for i, row in enumerate(rows):
        cik = str(row["cik_str"]).zfill(10)
        if cik in cache:
            continue
        try:
            r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                             headers=UA, timeout=30)
            time.sleep(RATE)
            if r.status_code == 200:
                d = r.json()
                ex = d.get("exchanges") or []
                cache[cik] = {"sic": d.get("sic"),
                              "sicDescription": d.get("sicDescription"),
                              "exchange": ex[0] if ex else None}
            else:
                cache[cik] = {"sic": None, "sicDescription": None, "exchange": None}
        except Exception:
            cache[cik] = {"sic": None, "sicDescription": None, "exchange": None}
        done += 1
        if done % 200 == 0:
            CACHE.write_text(json.dumps(cache))
            print(f"  {i+1}/{total} processed ({done} new this run)")

    CACHE.write_text(json.dumps(cache))
    print(f"Done. {len(cache)}/{total} CIKs cached -> {CACHE}")


if __name__ == "__main__":
    main()
