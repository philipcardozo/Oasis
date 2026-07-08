"""Ingest US legislators + committee memberships into Person nodes (prompt 13).

Source: github.com/unitedstates/congress-legislators (public domain, well-maintained).
Output: graph/data/pol_members.json (UI) + data/store/pol_members.parquet.
ID scheme: POL_<bioguide> (fits the PVT_/GOV_ convention in docs/IDS.md).
Idempotent: rebuilds both outputs each run; raw YAML cached under data/raw/political/.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from build_store import download, write_parquet

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "political"
BASE = "https://unitedstates.github.io/congress-legislators/"
FILES = ["legislators-current.yaml", "committees-current.yaml", "committee-membership-current.yaml"]


def _fetch(name: str) -> object:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    if not path.exists():  # cache; delete to force refresh
        download(BASE + name, path)
    return yaml.safe_load(path.read_text("utf-8"))


def _committee_names(committees: list) -> dict:
    names = {}
    for c in committees:
        tid = c.get("thomas_id")
        if tid:
            names[tid] = c.get("name", tid)
        for sub in c.get("subcommittees", []) or []:
            names[(tid or "") + sub.get("thomas_id", "")] = f"{c.get('name', '')}: {sub.get('name', '')}"
    return names


def build() -> dict:
    legislators = _fetch("legislators-current.yaml")
    committees = _fetch("committees-current.yaml")
    membership = _fetch("committee-membership-current.yaml")

    names = _committee_names(committees)
    by_person: dict[str, list] = {}
    for cid, members in membership.items():
        for m in members:
            bg = m.get("bioguide")
            if bg:
                by_person.setdefault(bg, []).append({"id": cid, "name": names.get(cid, cid)})

    today = date.today().isoformat()
    rows = []
    for m in legislators:
        bg = m["id"]["bioguide"]
        term = m["terms"][-1]
        nm = m["name"]
        rows.append({
            "id": f"POL_{bg}", "node_type": "person", "roles": ["politician"], "bioguide": bg,
            "name": nm.get("official_full") or f"{nm.get('first', '')} {nm.get('last', '')}".strip(),
            "chamber": "Senate" if term.get("type") == "sen" else "House",
            "party": term.get("party"), "state": term.get("state"),
            "committees": by_person.get(bg, []),
            "source_url": "https://github.com/unitedstates/congress-legislators", "as_of": today,
        })

    (ROOT / "graph" / "data" / "pol_members.json").write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
    # committees -> JSON blob so read_json_auto keeps a stable column type
    write_parquet([{**r, "committees": json.dumps(r["committees"], ensure_ascii=False)} for r in rows],
                  ROOT / "data" / "store" / "pol_members.parquet")
    with_committees = sum(1 for r in rows if r["committees"])
    print(f"politicians: {len(rows)} ({with_committees} with committee memberships)")
    return {"members": len(rows), "with_committees": with_committees}


if __name__ == "__main__":
    build()
