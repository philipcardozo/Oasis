"""Ingest congressional Periodic Transaction Report (PTR) filings (prompt 13).

DATA-AVAILABILITY NOTE: the free structured transaction datasets (House/Senate
Stock Watcher S3 dumps) are offline (HTTP 403 as of 2026-07). The durable official
source is the House Clerk financial-disclosure XML index, which lists PTR *filings*
(who filed, when, linkable PDF) but NOT transaction rows — ticker/amount live only
inside the PDFs. So this ingests filing-level provenance and resolves each filer to
a POL_ node. Transaction-level ticker resolution + POL_->company TRADED edges need a
transaction source (dead) or PDF parsing (brittle, new dep) — deferred, see review file.

Output: data/store/pol_trades.parquet + data/raw/political/unresolved_filers.json.
Idempotent; raw ZIPs cached under data/raw/political/.
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from build_store import download, write_parquet

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "political"
CLERK = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_PDF = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"


def _name_index() -> dict:
    """(last, first-token) -> (bioguide, POL_ id) from the cached legislators YAML."""
    leg = yaml.safe_load((RAW / "legislators-current.yaml").read_text("utf-8"))
    idx = {}
    for m in leg:
        bg, nm = m["id"]["bioguide"], m["name"]
        idx[(nm.get("last", "").lower(), nm.get("first", "").split()[0].lower())] = (bg, f"POL_{bg}")
    return idx


def _ptr_filings(year: int):
    path = RAW / f"{year}FD.zip"
    if not path.exists():
        try:
            download(CLERK.format(year=year), path)
        except subprocess.CalledProcessError:
            return  # year not published yet
    with zipfile.ZipFile(path) as z:
        xml = z.read(next(n for n in z.namelist() if n.endswith(".xml")))
    for m in ET.fromstring(xml).findall("Member"):
        g = lambda t: (m.findtext(t) or "").strip()
        if g("FilingType") != "P":  # P = Periodic Transaction Report (stock trades)
            continue
        yield {"last": g("Last"), "first": g("First"), "date": g("FilingDate"),
               "doc": g("DocID"), "year": g("Year") or str(year)}


def build(years: list[int] | None = None) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    years = years or [date.today().year, date.today().year - 1]
    if not (RAW / "legislators-current.yaml").exists():
        import refresh_politicians  # ensure the name index source exists
        refresh_politicians.build()
    idx = _name_index()

    rows, unresolved = [], []
    for year in years:
        for f in _ptr_filings(year):
            if not f["doc"]:
                continue
            hit = idx.get((f["last"].lower(), f["first"].split()[0].lower() if f["first"] else ""))
            row = {
                "politician_bioguide": hit[0] if hit else None,
                "politician_id": hit[1] if hit else None,
                "filer_name": f"{f['first']} {f['last']}".strip(),
                "filing_type": "PTR", "disclosure_date": f["date"], "doc_id": f["doc"],
                "source_url": PTR_PDF.format(year=f["year"], doc=f["doc"]),
                # transaction-level fields unavailable from the free index (PDF-only):
                "ticker": None, "asset_name": None, "tx_type": None, "amount_range": None,
            }
            rows.append(row)
            if not hit:
                unresolved.append({"filer": row["filer_name"], "reason": "no legislator name match", "doc_id": f["doc"]})

    resolved = sum(1 for r in rows if r["politician_id"])
    rate = resolved / len(rows) if rows else 0.0
    write_parquet(rows, ROOT / "data" / "store" / "pol_trades.parquet")
    (RAW / "unresolved_filers.json").write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), "utf-8")
    print(f"PTR filings: {len(rows)} | filer-resolved to a legislator: {resolved} ({rate:.0%}) | "
          f"unresolved: {len(unresolved)} -> {RAW / 'unresolved_filers.json'}")
    print("NOTE: transaction-level ticker resolution + POL_->company TRADED edges are blocked "
          "(free transaction datasets offline; PDFs unparsed). Filing provenance only.")
    return {"filings": len(rows), "resolved": resolved, "rate": rate}


if __name__ == "__main__":
    build()
