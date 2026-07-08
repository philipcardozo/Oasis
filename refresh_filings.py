"""Cache latest SEC filings for connected listed companies and securities.

Run after expand_us.py has built graph/data/universe.json:
    python3 refresh_filings.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).parent
GRAPH = ROOT / "graph" / "data" / "universe.json"
OUT = ROOT / "graph" / "data" / "filings.json"
UA = {"User-Agent": "BusinessGraph/0.1 (veratori@veratori.com)"}
RATE = 1.0 / 8
FORMS = ("10-K", "10-Q", "8-K")


def filing_url(cik: str, accession: str, doc: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{doc}"


def pick_filings(recent: dict, cik: str) -> list[dict]:
    out, seen = [], set()
    for i, form in enumerate(recent.get("form", [])):
        if form not in FORMS or form in seen:
            continue
        accession = recent["accessionNumber"][i]
        doc = recent["primaryDocument"][i]
        if accession and doc:
            out.append({
                "form": form,
                "accessionNumber": accession,
                "filingDate": recent["filingDate"][i],
                "url": filing_url(cik, accession, doc),
            })
            seen.add(form)
        if len(seen) == len(FORMS):
            break
    return out


def fetch_submissions(cik: str) -> dict:
    import requests

    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> None:
    if OUT.exists():
        mtime = OUT.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24:
            print(f"Filings cache is fresh ({age_hours:.1f} hours old). Skipping refresh.")
            return

    graph = json.load(GRAPH.open())
    nodes = sorted(
        (
            n
            for n in graph["nodes"]
            if n.get("kind") in {"public", "security"} and n.get("deg", 0) > 0 and str(n.get("cik") or "").isdigit()
        ),
        key=lambda n: n["id"],
    )
    filings = {}
    for i, node in enumerate(nodes, 1):
        cik = node["cik"]
        try:
            filings[node["id"]] = pick_filings(fetch_submissions(cik).get("filings", {}).get("recent", {}), cik)
        except Exception as exc:
            print(f"  failed {node['id']}: {exc}")
            filings[node["id"]] = []
        print(f"  {i}/{len(nodes)} {node['id']}: {len(filings[node['id']])} filings")
        time.sleep(RATE)
    OUT.write_text(json.dumps(filings, indent=2) + "\n")
    print(f"Wrote filings for {len(filings)} companies -> {OUT}")


if __name__ == "__main__":
    main()
