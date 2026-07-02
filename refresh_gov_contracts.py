"""Refresh government-contract edges from USAspending.

Writes graph/data/gov_contracts.json, which expand_us.py overlays onto the
curated graph. The numbers are current-federal-year obligations to date, not
lifetime contract value.

Run:   python3 refresh_gov_contracts.py
Deps:  pip install requests
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "graph" / "data" / "gov_contracts.json"
QUERY_PATH = ROOT / "graph" / "data" / "gov_contract_queries.json"
API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/"
UA = {"User-Agent": "BusinessGraph/0.1 (veratori@veratori.com)"}
CONTRACT_AWARD_TYPES = ["A", "B", "C", "D"]


def federal_fiscal_year(today: date) -> tuple[int, str, str]:
    if today.month >= 10:
        fy = today.year + 1
        start_year = today.year
    else:
        fy = today.year
        start_year = today.year - 1
    return fy, f"{start_year}-10-01", f"{start_year + 1}-09-30"


def fetch_total(query: dict, start: str, end: str, max_pages: int = 25) -> tuple[float, int]:
    total = 0.0
    records = 0
    page = 1
    while page <= max_pages:
        payload = {
            "filters": {
                "time_period": [{"start_date": start, "end_date": end}],
                "award_type_codes": CONTRACT_AWARD_TYPES,
                "keywords": query["keywords"],
                "agencies": [{
                    "type": "awarding",
                    "tier": "toptier",
                    "name": query["agency"],
                }],
            },
            "limit": 100,
            "page": page,
        }
        r = requests.post(API_URL, json=payload, timeout=45, headers=UA)
        r.raise_for_status()
        data = r.json()
        rows = data.get("results", [])
        for row in rows:
            total += float(row.get("amount") or 0.0)
        records += len(rows)
        meta = data.get("page_metadata") or {}
        if not meta.get("hasNext"):
            break
        page += 1
        time.sleep(0.2)
    return total, records


def main() -> None:
    today = date.today()
    fy, start, end = federal_fiscal_year(today)
    links = []

    for query in json.load(QUERY_PATH.open()):
        try:
            total, records = fetch_total(query, start, end)
        except requests.RequestException as exc:
            print(f"  failed {query['recipient_name']}: {exc}")
            continue

        val_bn = total / 1_000_000_000
        links.append({
            "from": query["agency_id"],
            "to": query["recipient_id"],
            "rel": "contracts",
            "src": f"USAspending API FY{fy}",
            "source_url": API_URL,
            "val": round(val_bn, 3),
            "detail": f"FY{fy} obligations from {query['agency']}: ${val_bn:.2f}B to date across {records} recipient records",
            "start": start,
            "end": end,
            "as_of": today.isoformat(),
            "confidence": query.get("confidence", 0.9),
        })
        print(f"  {query['agency']} -> {query['recipient_name']}: ${val_bn:.2f}B ({records} records)")
        time.sleep(0.2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": today.isoformat(),
        "source": API_URL,
        "fiscal_year": fy,
        "period": {"start": start, "end": end},
        "links": links,
    }, indent=2))
    print(f"Wrote {len(links)} generated contract links -> {OUT}")


if __name__ == "__main__":
    main()
